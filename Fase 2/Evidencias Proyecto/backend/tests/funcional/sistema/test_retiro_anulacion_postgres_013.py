"""T38 (Feature 013; enmienda 26/Nov/2026): concurrencia del retiro y su anulacion - gated.

Complemento gated de `test_retiro_transaccional_013.py`,
`test_retiro_sede_013.py`, `test_anulacion_retiro_013.py` y
`test_confirmacion_anulacion_013.py`. SQLite no acredita el bloqueo de fila
(`FOR UPDATE`), asi que solo PostgreSQL 16 real demuestra lo que la spec §10.8
exige (AC-57, AC-58, AC-59, AC-61):

  * **Retiro concurrente** - dos peticiones simultaneas sobre el mismo pedido
    `EnCurso` se serializan por la fila del ticket: una responde 200 y la otra
    409, con **un solo juego** de `SALIDA` (una por detalle) y una sola rebaja
    de stock.
  * **Anulacion del retiro concurrente** - dos anulaciones administrativas del
    mismo pedido `Cerrado` se serializan: una responde 200 y la otra 409, con
    **una sola** `ENTRADA` y una sola devolucion de stock.
  * **Cruce confirmacion/anulacion** - ambas bloquean el ticket. Secuencialmente
    la que llega segundo responde 409; en paralelo una gana y la otra pierde,
    con un unico efecto (confirmacion o devolucion, nunca las dos).
  * **Persistencia** - la anulacion crea la fila `stock_sede` si falta y deja por
    SQL el stock devuelto, `cantidad_entregada = 0`, `fecha_cierre` nula y la
    fila `Cerrado -> Anulado` con actor y motivo literal.

Seam bajo prueba: el **servicio** (`ticket_service.registrar_retiro_ticket`,
`anular_ticket` y `confirmar_entrega_ticket`) con dos sesiones reales del tenant
temporal, una por hilo, y una barrera justo antes de la operacion. Es el mismo
patron de `test_ciclo_vida_aprobacion_confirmacion_postgres_013.py`: el
`FOR UPDATE` vive en el servicio y una sesion por hilo en `NullPool` reproduce
la carrera sin la capa HTTP, que la suite SQLite ya cubre por contrato. La
barrera no fija el orden del lock: no se asume que peticion gana.

COMO ACTIVARLO
    docker compose -f docker-compose.yml up -d db
    $env:POSTGRES_TEST_URL = "postgresql://postgres:postgres@localhost:5433/postgres"
    cd backend; python -m pytest tests/funcional/sistema/test_retiro_anulacion_postgres_013.py

Sin `POSTGRES_TEST_URL` los tests se **saltan**. La URL apunta a una base de
mantenimiento donde el modulo crea y DESTRUYE una base temporal propia
(`compustock_t38_*`); nunca toca `apt_erp`. No se anade ninguna dependencia.
"""

from __future__ import annotations

import os
import threading
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import pytest

try:  # `psycopg2` es dependencia declarada; el guard evita un error de coleccion.
    import psycopg2

    _PSYCOPG2_DISPONIBLE = True
except ImportError:  # pragma: no cover - entorno sin la dependencia
    _PSYCOPG2_DISPONIBLE = False

from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import joinedload
from sqlalchemy.pool import NullPool

from app.models import (
    Departamento,
    EstadoTicket,
    Producto,
    Rol,
    StockSede,
    Ticket,
    Usuario,
)
from app.schemas.ticket_schema import (
    DetalleTicketCrear,
    TicketCrear,
    TicketRetiro,
)
from app.services import ticket_service
from app.services.auth_service import IdentidadAutenticada

_POSTGRES_TEST_URL = os.environ.get("POSTGRES_TEST_URL")

pytestmark = pytest.mark.skipif(
    not _POSTGRES_TEST_URL or not _PSYCOPG2_DISPONIBLE,
    reason=(
        "Requiere PostgreSQL 16 real: exporta POSTGRES_TEST_URL="
        "postgresql://postgres:postgres@localhost:5433/postgres y levanta el "
        "contenedor `db` (docker compose up -d db)."
    ),
)

RAIZ = Path(__file__).resolve().parents[4]
ESQUEMA_SQL = RAIZ / "database" / "01_esquema.sql"
SEMILLA_SQL = RAIZ / "database" / "02_datos_semilla.sql"

_INSTITUCION = "INST-001"
_APP_CONCURRENCIA = "compustock_t38_retiro"

#: Correos de la semilla QA de INST-001. El Solicitante (departamento 6,
#: Biblioteca -> Sede Maipu, sede 2) es el dueño del pedido; el Bodeguero
#: comparte departamento y sede, la precondicion del retiro; el Administrador
#: vive en Direccion (departamento 1) y ejecuta la anulacion administrativa.
_CORREO_SOLICITANTE = "solicitante.test+clerk_test@example.com"
_CORREO_BODEGUERO = "bodeguero.test+clerk_test@example.com"
_CORREO_ADMINISTRADOR = "admin020.test+clerk_test@example.com"

#: Motivo literal de la anulacion de la prueba (viaja al historial).
MOTIVO_ANULACION = "Retiro registrado por error en la bodega"

#: Observaciones literales de la enmienda (D-29/D-32). Fuente independiente.
PREFIJO_SALIDA = "Salida por retiro del ticket #{ticket_id};"
PREFIJO_ENTRADA = "Devolución por anulación del retiro del ticket #{ticket_id};"


# ---------------------------------------------------------------------------
# Base temporal y utilidades
# ---------------------------------------------------------------------------


def _sin_driver(url: str) -> str:
    return url.replace("postgresql+psycopg2://", "postgresql://")


def _url_con_base(url: str, nombre: str) -> str:
    partes = urlsplit(url)
    return urlunsplit((partes.scheme, partes.netloc, "/" + nombre, "", ""))


@contextmanager
def _base_temporal():
    """Crea una base PostgreSQL efimera y la destruye al salir (nunca `apt_erp`)."""
    dsn = _sin_driver(_POSTGRES_TEST_URL or "")
    admin = psycopg2.connect(dsn)
    admin.autocommit = True
    nombre = f"compustock_t38_{uuid4().hex[:12]}"
    with admin.cursor() as cur:
        cur.execute(f'CREATE DATABASE "{nombre}"')
    try:
        conexion = psycopg2.connect(_url_con_base(dsn, nombre))
        try:
            yield conexion
        finally:
            conexion.close()
    finally:
        with admin.cursor() as cur:
            cur.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (nombre,),
            )
            cur.execute(f'DROP DATABASE IF EXISTS "{nombre}"')
        admin.close()


def _ejecutar(conexion, sql: str, params=None):
    with conexion.cursor() as cur:
        if params is None:
            cur.execute(sql)
        else:
            cur.execute(sql, params)
        filas = cur.fetchall() if cur.description else []
    conexion.commit()
    return filas


def _ejecutar_script(conexion, ruta: Path) -> None:
    _ejecutar(conexion, ruta.read_text(encoding="utf-8"))


def _instalar(conexion) -> None:
    _ejecutar_script(conexion, ESQUEMA_SQL)
    _ejecutar_script(conexion, SEMILLA_SQL)


def _esquema_de_institucion(institucion_id: str) -> str:
    from app.services.tenant_service import nombre_esquema_para_institucion

    return nombre_esquema_para_institucion(institucion_id)


def _motor_de(conexion):
    """Motor sin pool: cada sesion abre su propia conexion real."""
    nombre_base = conexion.get_dsn_parameters()["dbname"]
    url = _url_con_base(_sin_driver(_POSTGRES_TEST_URL or ""), nombre_base)
    url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return create_engine(
        url,
        poolclass=NullPool,
        future=True,
        connect_args={"application_name": _APP_CONCURRENCIA},
    )


@contextmanager
def _base_instalada():
    with _base_temporal() as conexion:
        _instalar(conexion)
        motor = _motor_de(conexion)
        try:
            yield conexion, motor
        finally:
            motor.dispose()


@contextmanager
def _sesion_tenant(motor, esquema):
    from app.db.database import crear_sesion_esquema

    db = crear_sesion_esquema(esquema, motor=motor)
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Identidades y siembra
# ---------------------------------------------------------------------------


def _identidad_por_correo(motor, esquema: str, correo: str) -> IdentidadAutenticada:
    """Identidad suelta con los ids persistidos del usuario sembrado."""
    with _sesion_tenant(motor, esquema) as db:
        actor = db.execute(
            select(Usuario)
            .options(joinedload(Usuario.rol))
            .where(Usuario.correo == correo)
        ).scalar_one_or_none()
        assert actor is not None, f"la semilla debe tener el usuario {correo}"
        datos = {
            "usuario_id": actor.usuario_id,
            "nombre": actor.nombre,
            "apellido": actor.apellido,
            "correo": actor.correo,
            "departamento_id": actor.departamento_id,
            "rol_id": actor.rol_id,
            "sede_id": actor.sede_id,
            "rol_nombre": actor.rol.nombre_rol,
        }

    datos_usuario = {clave: datos[clave] for clave in datos if clave != "rol_nombre"}
    usuario = Usuario(**datos_usuario)
    usuario.rol = Rol(rol_id=datos["rol_id"], nombre_rol=datos["rol_nombre"])
    return IdentidadAutenticada(usuario=usuario, sub=f"t38-{correo}")


def _sede_del_departamento(motor, esquema: str, departamento_id: int) -> int:
    with _sesion_tenant(motor, esquema) as db:
        sede_id = db.execute(
            select(Departamento.sede_id).where(
                Departamento.departamento_id == departamento_id
            )
        ).scalar_one_or_none()
    assert sede_id is not None, "la semilla debe dar sede al departamento del usuario"
    return sede_id


def _producto_con_stock(
    motor, esquema: str, *, sede_id: int, cantidad: int
) -> int:
    """Primer producto activo de INST-001 con saldo suficiente en la sede."""
    with _sesion_tenant(motor, esquema) as db:
        producto_id = db.execute(
            select(StockSede.producto_id)
            .join(Producto, Producto.producto_id == StockSede.producto_id)
            .where(StockSede.sede_id == sede_id)
            .where(StockSede.stock_actual >= cantidad + 5)
            .where(Producto.activo.is_(True))
            .where(Producto.institucion_id == _INSTITUCION)
            .order_by(StockSede.producto_id)
            .limit(1)
        ).scalar_one_or_none()
    assert producto_id is not None, (
        f"la semilla debe tener stock suficiente en la sede {sede_id}"
    )
    return producto_id


def _estado_id_por_nombre(motor, esquema: str, nombre: str) -> int:
    with _sesion_tenant(motor, esquema) as db:
        estado_id = db.execute(
            select(EstadoTicket.estado_id).where(EstadoTicket.nombre == nombre)
        ).scalar_one_or_none()
    assert estado_id is not None, f"la semilla debe tener el estado {nombre}"
    return estado_id


def _crear_ticket_en_curso(
    motor,
    esquema: str,
    solicitante: IdentidadAutenticada,
    administrador: IdentidadAutenticada,
    *,
    producto_id: int,
    cantidad: int,
) -> int:
    """Alta real en `EnRevision` y aprobacion: deja el pedido `EnCurso`."""
    datos = TicketCrear(
        prioridad_id=2,
        estado_id=_estado_id_por_nombre(motor, esquema, "EnRevision"),
        asunto="Pedido concurrente T38",
        descripcion="Pedido de la prueba gated de retiro y anulacion de la 013.",
        detalles=[
            DetalleTicketCrear(
                producto_id=producto_id,
                cantidad_solicitada=cantidad,
            )
        ],
    )
    with _sesion_tenant(motor, esquema) as db:
        ticket = ticket_service.crear_ticket(db, datos, solicitante)
        ticket_id = ticket.ticket_id
    with _sesion_tenant(motor, esquema) as db:
        ticket_service.aprobar_ticket(db, ticket_id, administrador)
    return ticket_id


def _retirar(
    motor, esquema: str, identidad: IdentidadAutenticada, ticket_id: int
) -> Ticket:
    with _sesion_tenant(motor, esquema) as db:
        return ticket_service.registrar_retiro_ticket(
            db,
            ticket_id,
            TicketRetiro(usuario_id=identidad.usuario.usuario_id),
            identidad,
        )


def _anular(
    motor, esquema: str, identidad: IdentidadAutenticada, ticket_id: int
) -> Ticket:
    with _sesion_tenant(motor, esquema) as db:
        return ticket_service.anular_ticket(db, ticket_id, MOTIVO_ANULACION, identidad)


def _confirmar(
    motor, esquema: str, identidad: IdentidadAutenticada, ticket_id: int
):
    with _sesion_tenant(motor, esquema) as db:
        return ticket_service.confirmar_entrega_ticket(db, ticket_id, identidad)


# ---------------------------------------------------------------------------
# Lectura persistida
# ---------------------------------------------------------------------------


def _estado_y_cierre(motor, esquema: str, ticket_id: int) -> tuple[str, object]:
    with _sesion_tenant(motor, esquema) as db:
        estado_nombre, fecha_cierre = db.execute(
            select(EstadoTicket.nombre, Ticket.fecha_cierre)
            .join(Ticket, Ticket.estado_id == EstadoTicket.estado_id)
            .where(Ticket.ticket_id == ticket_id)
        ).one()
    return estado_nombre, fecha_cierre


def _stock_de_producto(
    motor, esquema: str, *, sede_id: int, producto_id: int
) -> int | None:
    with _sesion_tenant(motor, esquema) as db:
        return db.execute(
            select(StockSede.stock_actual).where(
                StockSede.sede_id == sede_id,
                StockSede.producto_id == producto_id,
            )
        ).scalar_one_or_none()


def _entregas_del_ticket(
    conexion, esquema: str, ticket_id: int
) -> list[int]:
    filas = _ejecutar(
        conexion,
        (
            f'SELECT cantidad_entregada FROM "{esquema}".detalle_ticket '
            f"WHERE ticket_id = %s ORDER BY detalle_ticket_id"
        ),
        (ticket_id,),
    )
    return [fila[0] for fila in filas]


def _movimientos_con_prefijo(
    conexion, esquema: str, *, tipo: str, prefijo: str
) -> list[tuple[int, int]]:
    """`(cantidad, producto_id)` de los movimientos del ticket con esa observacion."""
    return _ejecutar(
        conexion,
        (
            f'SELECT m.cantidad, ss.producto_id '
            f'FROM "{esquema}".movimiento_inventario m '
            f'JOIN "{esquema}".stock_sede ss '
            f"ON ss.stock_sede_id = m.stock_sede_id "
            f"WHERE m.tipo_movimiento = %s AND m.observacion LIKE %s "
            f"ORDER BY m.movimiento_id"
        ),
        (tipo, prefijo + "%"),
    )


def _historial_cerrado_anulado(
    conexion, esquema: str, ticket_id: int
) -> list[tuple]:
    return _ejecutar(
        conexion,
        (
            f'SELECT h.usuario_id, h.motivo, eo.nombre, ed.nombre '
            f'FROM "{esquema}".historial_transicion_ticket h '
            f'JOIN "{esquema}".estado_ticket eo '
            f"ON eo.estado_id = h.estado_origen_id "
            f'JOIN "{esquema}".estado_ticket ed '
            f"ON ed.estado_id = h.estado_destino_id "
            f"WHERE h.ticket_id = %s AND eo.nombre = 'Cerrado' "
            f"AND ed.nombre = 'Anulado' "
            f"ORDER BY h.historial_transicion_id"
        ),
        (ticket_id,),
    )


def _contar_confirmaciones(conexion, esquema: str, ticket_id: int) -> int:
    filas = _ejecutar(
        conexion,
        (
            f'SELECT count(*) FROM "{esquema}".historial_transicion_ticket '
            f"WHERE ticket_id = %s "
            f"AND motivo = 'Entrega confirmada por el solicitante'"
        ),
        (ticket_id,),
    )
    return filas[0][0]


# ---------------------------------------------------------------------------
# Carrera
# ---------------------------------------------------------------------------


def _correr_en_paralelo(primera, segunda) -> dict[str, str]:
    """Arranca dos operaciones a la vez con una barrera y devuelve sus resultados."""
    barrera = threading.Barrier(2)
    resultados: dict[str, str] = {}
    candado = threading.Lock()

    def _ejecutar(nombre: str, tarea) -> None:
        try:
            barrera.wait(timeout=15)
            resultado = tarea()
        except HTTPException as exc:
            resultado = f"http:{exc.status_code}"
        except Exception as exc:  # pragma: no cover - diagnostico de carrera
            resultado = f"error:{type(exc).__name__}:{exc}"
        with candado:
            resultados[nombre] = resultado

    hilos = [
        threading.Thread(target=_ejecutar, args=("primera", primera)),
        threading.Thread(target=_ejecutar, args=("segunda", segunda)),
    ]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join(timeout=60)

    assert not any(hilo.is_alive() for hilo in hilos), (
        "una carrera quedo colgada: posible deadlock o bloqueo sin liberar"
    )
    assert set(resultados) == {"primera", "segunda"}, resultados
    return resultados


def _assert_un_200_y_un_409(resultados: dict[str, str]) -> None:
    """La carrera deja un ganador y un perdedor, sin importar el orden."""
    valores = sorted(resultados.values())
    assert valores.count("http:409") == 1, resultados
    assert sum(valor.startswith("ok:") for valor in valores) == 1, resultados


# ---------------------------------------------------------------------------
# AC-57: retiro concurrente
# ---------------------------------------------------------------------------


def test_retiro_concurrente_registra_una_sola_salida_ac_57():
    """AC-57/D-9: dos retiros simultaneos -> (200, 409) y un solo juego de SALIDA."""
    with _base_instalada() as (conexion, motor):
        esquema = _esquema_de_institucion(_INSTITUCION)
        solicitante = _identidad_por_correo(motor, esquema, _CORREO_SOLICITANTE)
        bodeguero = _identidad_por_correo(motor, esquema, _CORREO_BODEGUERO)
        administrador = _identidad_por_correo(
            motor, esquema, _CORREO_ADMINISTRADOR
        )
        sede_id = _sede_del_departamento(
            motor, esquema, solicitante.usuario.departamento_id
        )
        producto_id = _producto_con_stock(
            motor, esquema, sede_id=sede_id, cantidad=3
        )
        ticket_id = _crear_ticket_en_curso(
            motor,
            esquema,
            solicitante,
            administrador,
            producto_id=producto_id,
            cantidad=3,
        )
        stock_antes = _stock_de_producto(
            motor, esquema, sede_id=sede_id, producto_id=producto_id
        )

        def _retirar_en_hilo(nombre: str):
            def _tarea() -> str:
                ticket = _retirar(motor, esquema, bodeguero, ticket_id)
                assert ticket.estado_id == _estado_id_por_nombre(
                    motor, esquema, "Cerrado"
                )
                return f"ok:{nombre}"

            return _tarea

        resultados = _correr_en_paralelo(
            _retirar_en_hilo("primera"), _retirar_en_hilo("segunda")
        )
        _assert_un_200_y_un_409(resultados)

        estado, fecha_cierre = _estado_y_cierre(motor, esquema, ticket_id)
        assert estado == "Cerrado", estado
        assert fecha_cierre is not None, "el retiro sella `fecha_cierre` (D-29)"

        prefijo = PREFIJO_SALIDA.format(ticket_id=ticket_id)
        salidas = _movimientos_con_prefijo(
            conexion, esquema, tipo="SALIDA", prefijo=prefijo
        )
        assert len(salidas) == 1, f"un solo juego de SALIDA: {salidas}"
        assert salidas[0] == (3, producto_id)
        assert _entregas_del_ticket(conexion, esquema, ticket_id) == [3], (
            "la entrega se fija una sola vez"
        )
        assert _stock_de_producto(
            motor, esquema, sede_id=sede_id, producto_id=producto_id
        ) == stock_antes - 3, "una sola rebaja de stock"


# ---------------------------------------------------------------------------
# AC-58/AC-59: anulacion del retiro concurrente
# ---------------------------------------------------------------------------


def test_anulacion_concurrente_devuelve_el_stock_una_sola_vez_ac_58_ac_59():
    """AC-58/AC-59: dos anulaciones simultaneas -> (200, 409) y una ENTRADA."""
    with _base_instalada() as (conexion, motor):
        esquema = _esquema_de_institucion(_INSTITUCION)
        solicitante = _identidad_por_correo(motor, esquema, _CORREO_SOLICITANTE)
        bodeguero = _identidad_por_correo(motor, esquema, _CORREO_BODEGUERO)
        administrador = _identidad_por_correo(
            motor, esquema, _CORREO_ADMINISTRADOR
        )
        sede_id = _sede_del_departamento(
            motor, esquema, solicitante.usuario.departamento_id
        )
        producto_id = _producto_con_stock(
            motor, esquema, sede_id=sede_id, cantidad=3
        )
        ticket_id = _crear_ticket_en_curso(
            motor,
            esquema,
            solicitante,
            administrador,
            producto_id=producto_id,
            cantidad=3,
        )
        _retirar(motor, esquema, bodeguero, ticket_id)
        stock_retirado = _stock_de_producto(
            motor, esquema, sede_id=sede_id, producto_id=producto_id
        )

        def _anular_en_hilo(nombre: str):
            def _tarea() -> str:
                ticket = _anular(motor, esquema, administrador, ticket_id)
                assert ticket.estado_id == _estado_id_por_nombre(
                    motor, esquema, "Anulado"
                )
                return f"ok:{nombre}"

            return _tarea

        resultados = _correr_en_paralelo(
            _anular_en_hilo("primera"), _anular_en_hilo("segunda")
        )
        _assert_un_200_y_un_409(resultados)

        estado, fecha_cierre = _estado_y_cierre(motor, esquema, ticket_id)
        assert estado == "Anulado", estado
        assert fecha_cierre is None, "la anulacion deja `fecha_cierre` nula (D-32)"

        prefijo = PREFIJO_ENTRADA.format(ticket_id=ticket_id)
        entradas = _movimientos_con_prefijo(
            conexion, esquema, tipo="ENTRADA", prefijo=prefijo
        )
        assert len(entradas) == 1, f"una sola ENTRADA: {entradas}"
        assert entradas[0] == (3, producto_id)
        assert _entregas_del_ticket(conexion, esquema, ticket_id) == [0], (
            "las cantidades entregadas se resetean una sola vez"
        )
        assert _stock_de_producto(
            motor, esquema, sede_id=sede_id, producto_id=producto_id
        ) == stock_retirado + 3, "una sola devolucion"

        filas = _historial_cerrado_anulado(conexion, esquema, ticket_id)
        assert len(filas) == 1, filas
        actor_id, motivo, origen, destino = filas[0]
        assert actor_id == administrador.usuario.usuario_id
        assert motivo == MOTIVO_ANULACION
        assert (origen, destino) == ("Cerrado", "Anulado")


def test_la_anulacion_crea_el_stock_y_registra_el_cierre_ac_58():
    """D-32: sin fila `stock_sede`, la anulacion la crea y persiste el cierre."""
    with _base_instalada() as (conexion, motor):
        esquema = _esquema_de_institucion(_INSTITUCION)
        solicitante = _identidad_por_correo(motor, esquema, _CORREO_SOLICITANTE)
        bodeguero = _identidad_por_correo(motor, esquema, _CORREO_BODEGUERO)
        administrador = _identidad_por_correo(
            motor, esquema, _CORREO_ADMINISTRADOR
        )
        sede_id = _sede_del_departamento(
            motor, esquema, solicitante.usuario.departamento_id
        )
        producto_id = _producto_con_stock(
            motor, esquema, sede_id=sede_id, cantidad=2
        )
        ticket_id = _crear_ticket_en_curso(
            motor,
            esquema,
            solicitante,
            administrador,
            producto_id=producto_id,
            cantidad=2,
        )
        _retirar(motor, esquema, bodeguero, ticket_id)

        # Se retira la fila de saldo para forzar el camino "crear si falta"; su
        # SALIDA se borra antes para no romper la FK de auditoria.
        stock_sede_id = _ejecutar(
            conexion,
            (
                f'SELECT stock_sede_id FROM "{esquema}".stock_sede '
                f"WHERE sede_id = %s AND producto_id = %s"
            ),
            (sede_id, producto_id),
        )[0][0]
        _ejecutar(
            conexion,
            f'DELETE FROM "{esquema}".movimiento_inventario WHERE stock_sede_id = %s',
            (stock_sede_id,),
        )
        _ejecutar(
            conexion,
            f'DELETE FROM "{esquema}".stock_sede WHERE stock_sede_id = %s',
            (stock_sede_id,),
        )
        assert _stock_de_producto(
            motor, esquema, sede_id=sede_id, producto_id=producto_id
        ) is None

        _anular(motor, esquema, administrador, ticket_id)

        estado, fecha_cierre = _estado_y_cierre(motor, esquema, ticket_id)
        assert estado == "Anulado", estado
        assert fecha_cierre is None
        assert _stock_de_producto(
            motor, esquema, sede_id=sede_id, producto_id=producto_id
        ) == 2, "la fila creada arranca en 0 y suma lo entregado"

        prefijo = PREFIJO_ENTRADA.format(ticket_id=ticket_id)
        entradas = _movimientos_con_prefijo(
            conexion, esquema, tipo="ENTRADA", prefijo=prefijo
        )
        assert entradas == [(2, producto_id)], entradas
        assert _entregas_del_ticket(conexion, esquema, ticket_id) == [0]
        assert len(_historial_cerrado_anulado(conexion, esquema, ticket_id)) == 1


# ---------------------------------------------------------------------------
# AC-61: confirmacion vs anulacion
# ---------------------------------------------------------------------------


def test_la_confirmacion_previa_bloquea_la_anulacion_ac_61():
    """D-34: confirmado no se anula; la fila canonica queda intacta."""
    with _base_instalada() as (conexion, motor):
        esquema = _esquema_de_institucion(_INSTITUCION)
        solicitante = _identidad_por_correo(motor, esquema, _CORREO_SOLICITANTE)
        bodeguero = _identidad_por_correo(motor, esquema, _CORREO_BODEGUERO)
        administrador = _identidad_por_correo(
            motor, esquema, _CORREO_ADMINISTRADOR
        )
        sede_id = _sede_del_departamento(
            motor, esquema, solicitante.usuario.departamento_id
        )
        producto_id = _producto_con_stock(
            motor, esquema, sede_id=sede_id, cantidad=3
        )
        ticket_id = _crear_ticket_en_curso(
            motor,
            esquema,
            solicitante,
            administrador,
            producto_id=producto_id,
            cantidad=3,
        )
        _retirar(motor, esquema, bodeguero, ticket_id)
        respuesta = _confirmar(motor, esquema, solicitante, ticket_id)
        assert respuesta.entrega_confirmada is True
        stock_confirmado = _stock_de_producto(
            motor, esquema, sede_id=sede_id, producto_id=producto_id
        )
        filas_antes = _ejecutar(
            conexion,
            (
                f'SELECT historial_transicion_id, motivo '
                f'FROM "{esquema}".historial_transicion_ticket '
                f"WHERE ticket_id = %s ORDER BY historial_transicion_id"
            ),
            (ticket_id,),
        )

        with pytest.raises(HTTPException) as excinfo:
            _anular(motor, esquema, administrador, ticket_id)
        assert excinfo.value.status_code == 409

        estado, fecha_cierre = _estado_y_cierre(motor, esquema, ticket_id)
        assert estado == "Cerrado", estado
        assert fecha_cierre is not None
        assert _stock_de_producto(
            motor, esquema, sede_id=sede_id, producto_id=producto_id
        ) == stock_confirmado, "el 409 no devuelve stock"
        prefijo = PREFIJO_ENTRADA.format(ticket_id=ticket_id)
        assert (
            _movimientos_con_prefijo(
                conexion, esquema, tipo="ENTRADA", prefijo=prefijo
            )
            == []
        ), "el 409 no crea ENTRADA"
        assert _contar_confirmaciones(conexion, esquema, ticket_id) == 1
        assert (
            _ejecutar(
                conexion,
                (
                    f'SELECT historial_transicion_id, motivo '
                    f'FROM "{esquema}".historial_transicion_ticket '
                    f"WHERE ticket_id = %s ORDER BY historial_transicion_id"
                ),
                (ticket_id,),
            )
            == filas_antes
        ), "la confirmacion es inmutable: el 409 no borra ni reescribe su fila"


def test_la_anulacion_previa_bloquea_la_confirmacion_ac_61():
    """AC-61: si la anulacion gana, la confirmacion ve `Anulado` y responde 409."""
    with _base_instalada() as (conexion, motor):
        esquema = _esquema_de_institucion(_INSTITUCION)
        solicitante = _identidad_por_correo(motor, esquema, _CORREO_SOLICITANTE)
        bodeguero = _identidad_por_correo(motor, esquema, _CORREO_BODEGUERO)
        administrador = _identidad_por_correo(
            motor, esquema, _CORREO_ADMINISTRADOR
        )
        sede_id = _sede_del_departamento(
            motor, esquema, solicitante.usuario.departamento_id
        )
        producto_id = _producto_con_stock(
            motor, esquema, sede_id=sede_id, cantidad=3
        )
        ticket_id = _crear_ticket_en_curso(
            motor,
            esquema,
            solicitante,
            administrador,
            producto_id=producto_id,
            cantidad=3,
        )
        _retirar(motor, esquema, bodeguero, ticket_id)
        _anular(motor, esquema, administrador, ticket_id)

        with pytest.raises(HTTPException) as excinfo:
            _confirmar(motor, esquema, solicitante, ticket_id)
        assert excinfo.value.status_code == 409

        estado, fecha_cierre = _estado_y_cierre(motor, esquema, ticket_id)
        assert estado == "Anulado", estado
        assert fecha_cierre is None
        assert _contar_confirmaciones(conexion, esquema, ticket_id) == 0
        assert _entregas_del_ticket(conexion, esquema, ticket_id) == [0]


def test_confirmacion_y_anulacion_en_paralelo_nunca_dan_doble_efecto_ac_61():
    """D-34: confirmacion y anulacion compiten por el ticket; solo una gana."""
    with _base_instalada() as (conexion, motor):
        esquema = _esquema_de_institucion(_INSTITUCION)
        solicitante = _identidad_por_correo(motor, esquema, _CORREO_SOLICITANTE)
        bodeguero = _identidad_por_correo(motor, esquema, _CORREO_BODEGUERO)
        administrador = _identidad_por_correo(
            motor, esquema, _CORREO_ADMINISTRADOR
        )
        sede_id = _sede_del_departamento(
            motor, esquema, solicitante.usuario.departamento_id
        )
        producto_id = _producto_con_stock(
            motor, esquema, sede_id=sede_id, cantidad=3
        )
        ticket_id = _crear_ticket_en_curso(
            motor,
            esquema,
            solicitante,
            administrador,
            producto_id=producto_id,
            cantidad=3,
        )
        _retirar(motor, esquema, bodeguero, ticket_id)
        stock_tras_retiro = _stock_de_producto(
            motor, esquema, sede_id=sede_id, producto_id=producto_id
        )

        def _confirmar_en_hilo() -> str:
            respuesta = _confirmar(motor, esquema, solicitante, ticket_id)
            assert respuesta.entrega_confirmada is True
            return "ok:confirmacion"

        def _anular_en_hilo() -> str:
            _anular(motor, esquema, administrador, ticket_id)
            return "ok:anulacion"

        resultados = _correr_en_paralelo(
            _confirmar_en_hilo, _anular_en_hilo
        )
        _assert_un_200_y_un_409(resultados)

        estado, fecha_cierre = _estado_y_cierre(motor, esquema, ticket_id)
        prefijo = PREFIJO_ENTRADA.format(ticket_id=ticket_id)
        entradas = _movimientos_con_prefijo(
            conexion, esquema, tipo="ENTRADA", prefijo=prefijo
        )
        confirmaciones = _contar_confirmaciones(conexion, esquema, ticket_id)
        entregas = _entregas_del_ticket(conexion, esquema, ticket_id)
        stock = _stock_de_producto(
            motor, esquema, sede_id=sede_id, producto_id=producto_id
        )

        assert not (entradas and confirmaciones), (
            "nunca se aceptan las dos: "
            f"entradas={entradas}, confirmaciones={confirmaciones}"
        )
        if estado == "Cerrado":
            # Gano la confirmacion: stock intacto, entrega vigente y una fila.
            assert confirmaciones == 1, resultados
            assert entradas == []
            assert fecha_cierre is not None
            assert entregas == [3]
            assert stock == stock_tras_retiro, "la confirmacion no devuelve stock"
        else:
            # Gano la anulacion: stock devuelto, entrega reseteada y una ENTRADA.
            assert estado == "Anulado", (estado, resultados)
            assert confirmaciones == 0, resultados
            assert entradas == [(3, producto_id)], entradas
            assert fecha_cierre is None
            assert entregas == [0]
            assert stock == stock_tras_retiro + 3, "la anulacion devuelve lo entregado"
