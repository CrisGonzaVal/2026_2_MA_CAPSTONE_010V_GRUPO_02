"""T23 (Feature 013; enmienda 26/Nov/2026): concurrencia y filas de historial - gated.

Complemento gated de `test_ciclo_vida_aprobacion_013.py` y
`test_ciclo_vida_confirmacion_013.py`. SQLite no acredita el bloqueo de fila
(`FOR UPDATE`), asi que solo PostgreSQL 16 real demuestra lo que la spec §9.3 y
§9.9 exigen (AC-30, AC-42, AC-43), ya con el catalogo de cuatro estados
(`EnRevision`, `EnCurso`, `Cerrado`, `Anulado`) y el retiro de la enmienda:

  * **Aprobacion concurrente** - dos peticiones simultaneas sobre el mismo
    pedido `EnRevision` se serializan por la fila del ticket: una responde 200 y
    la otra 409, el pedido queda `EnCurso` con **exactamente una** fila
    `EnRevision -> EnCurso` (actor, fecha, motivo literal
    `Aprobación del pedido`, `orden_compra_id` nulo), `fecha_cierre` sigue nula
    y el stock no cambia.
  * **Confirmacion concurrente** - dos peticiones simultaneas del Solicitante
    dueño sobre el mismo pedido `Cerrado` se serializan: una responde 200 y la
    otra 409, con **exactamente una** fila `Cerrado -> Cerrado` (actor, fecha,
    motivo literal `Entrega confirmada por el solicitante`, `orden_compra_id`
    nulo), el estado sigue `Cerrado` y `fecha_cierre`, el stock y los
    movimientos quedan intactos.
  * **Lectura persistida** - el flujo secuencial completo (alta -> aprobar ->
    retirar -> confirmar) deja por SQL el actor, la fecha, el motivo y
    `orden_compra_id NULL` de cada fila; no se crea ninguna tabla ni columna y
    la confirmacion no altera `fecha_cierre`, el stock ni los movimientos.

Seam bajo prueba: el **servicio** (`ticket_service.aprobar_ticket` y
`confirmar_entrega_ticket`) con dos sesiones reales del tenant temporal, una por
hilo, y una barrera justo antes de la operacion. Es el mismo patron de los
modulos gated de concurrencia ya existentes (`test_compras_postgres_020.py`,
`test_ciclo_vida_catalogo_postgres_014.py`): el `FOR UPDATE` vive en el servicio
y una sesion por hilo en `NullPool` reproduce la carrera sin la capa HTTP, que
la suite SQLite ya cubre por contrato. La barrera no fija el orden del lock: no
se asume que peticion gana.

COMO ACTIVARLO
    docker compose -f docker-compose.yml up -d db
    $env:POSTGRES_TEST_URL = "postgresql://postgres:postgres@localhost:5433/postgres"
    cd backend; python -m pytest tests/funcional/sistema/test_ciclo_vida_aprobacion_confirmacion_postgres_013.py

Sin `POSTGRES_TEST_URL` los tests se **saltan**. La URL apunta a una base de
mantenimiento donde el modulo crea y DESTRUYE una base temporal propia; nunca
toca `apt_erp`. No se anade ninguna dependencia nueva.
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
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import joinedload
from sqlalchemy.pool import NullPool

from app.models import (
    Departamento,
    DetalleTicket,
    EstadoTicket,
    MovimientoInventario,
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
_APP_CONCURRENCIA = "compustock_013_t23"

#: Correos de la semilla QA de INST-001 (Feature 013/020). El Solicitante y el
#: Bodeguero comparten el departamento 6 (Biblioteca -> Sede Maipu, sede 2); el
#: Administrador pertenece al departamento 1 (Direccion -> sede 1).
_CORREO_SOLICITANTE = "solicitante.test+clerk_test@example.com"
_CORREO_BODEGUERO = "bodeguero.test+clerk_test@example.com"
_CORREO_ADMINISTRADOR = "admin020.test+clerk_test@example.com"

#: Motivos literales de la spec (D-16/D-25). Fuente independiente del codigo.
MOTIVO_APROBACION = "Aprobación del pedido"
MOTIVO_CONFIRMACION = "Entrega confirmada por el solicitante"

#: Etiqueta que promete la confirmacion (spec D-22/§9.9).
ETIQUETA_ENTREGADO = "Entregado"


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
    nombre = f"compustock_013t23_{uuid4().hex[:12]}"
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
    return IdentidadAutenticada(usuario=usuario, sub=f"t23-{correo}")


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


def _crear_ticket_en_revision(
    motor,
    esquema: str,
    identidad: IdentidadAutenticada,
    *,
    producto_id: int,
    cantidad: int,
) -> int:
    """Alta por el mismo camino de produccion: el ticket nace en `EnRevision`."""
    datos = TicketCrear(
        prioridad_id=2,
        estado_id=_estado_id_por_nombre(motor, esquema, "EnRevision"),
        asunto="Pedido concurrente T23",
        descripcion="Pedido de la prueba gated de concurrencia de la 013.",
        detalles=[
            DetalleTicketCrear(
                producto_id=producto_id,
                cantidad_solicitada=cantidad,
            )
        ],
    )
    with _sesion_tenant(motor, esquema) as db:
        ticket = ticket_service.crear_ticket(db, datos, identidad)
        return ticket.ticket_id


def _retirar(
    motor, esquema: str, identidad: IdentidadAutenticada, ticket_id: int
) -> None:
    with _sesion_tenant(motor, esquema) as db:
        ticket_service.registrar_retiro_ticket(
            db,
            ticket_id,
            TicketRetiro(usuario_id=identidad.usuario.usuario_id),
            identidad,
        )


def _estado_y_cierre(motor, esquema: str, ticket_id: int) -> tuple[str, object]:
    with _sesion_tenant(motor, esquema) as db:
        estado_nombre, fecha_cierre = db.execute(
            select(EstadoTicket.nombre, Ticket.fecha_cierre)
            .join(Ticket, Ticket.estado_id == EstadoTicket.estado_id)
            .where(Ticket.ticket_id == ticket_id)
        ).one()
    return estado_nombre, fecha_cierre


def _sede_y_producto_del_ticket(
    motor, esquema: str, ticket_id: int
) -> tuple[int, int]:
    with _sesion_tenant(motor, esquema) as db:
        sede_id = db.execute(
            select(Ticket.sede_id).where(Ticket.ticket_id == ticket_id)
        ).scalar_one()
        producto_id = db.execute(
            select(DetalleTicket.producto_id)
            .where(DetalleTicket.ticket_id == ticket_id)
            .order_by(DetalleTicket.detalle_ticket_id)
            .limit(1)
        ).scalar_one()
    assert sede_id is not None, "el ticket de la prueba debe tener sede"
    return sede_id, producto_id


def _stock_de_la_sede(motor, esquema: str, ticket_id: int) -> dict[int, int]:
    """Saldo por producto de la sede del ticket (foto comparable)."""
    sede_id, _producto_id = _sede_y_producto_del_ticket(motor, esquema, ticket_id)
    with _sesion_tenant(motor, esquema) as db:
        filas = db.execute(
            select(StockSede.producto_id, StockSede.stock_actual)
            .where(StockSede.sede_id == sede_id)
            .order_by(StockSede.producto_id)
        ).all()
    return {producto_id: stock for producto_id, stock in filas}


def _contar_movimientos_de_la_sede(motor, esquema: str, ticket_id: int) -> int:
    sede_id, _producto_id = _sede_y_producto_del_ticket(motor, esquema, ticket_id)
    with _sesion_tenant(motor, esquema) as db:
        return db.execute(
            select(func.count())
            .select_from(MovimientoInventario)
            .join(
                StockSede,
                MovimientoInventario.stock_sede_id == StockSede.stock_sede_id,
            )
            .where(StockSede.sede_id == sede_id)
        ).scalar_one()


def _columnas_del_esquema(conexion, esquema: str) -> set[tuple[str, str]]:
    """`(tabla, columna)` de un tenant: una foto para detectar DDL."""
    return {
        (tabla, columna)
        for tabla, columna in _ejecutar(
            conexion,
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = %s",
            (esquema,),
        )
    }


def _historial_por_sql(
    conexion, esquema: str, ticket_id: int, motivo: str
) -> list[tuple]:
    """Filas del historial con su motivo, leidas por SQL sobre la base real.

    Devuelve `(usuario_id, fecha_transicion, motivo, orden_compra_id,
    estado_origen, estado_destino)` ordenadas por id.
    """
    return _ejecutar(
        conexion,
        (
            f'SELECT h.usuario_id, h.fecha_transicion, h.motivo, '
            f'h.orden_compra_id, eo.nombre, ed.nombre '
            f'FROM "{esquema}".historial_transicion_ticket h '
            f'JOIN "{esquema}".estado_ticket eo '
            f'ON eo.estado_id = h.estado_origen_id '
            f'JOIN "{esquema}".estado_ticket ed '
            f'ON ed.estado_id = h.estado_destino_id '
            f"WHERE h.ticket_id = %s AND h.motivo = %s "
            f"ORDER BY h.historial_transicion_id"
        ),
        (ticket_id, motivo),
    )


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
# AC-30: aprobacion concurrente
# ---------------------------------------------------------------------------


def test_aprobacion_concurrente_deja_una_sola_transicion_enrevision_encurso_ac_30():
    """AC-30: dos aprobaciones simultaneas -> (200, 409) y una sola fila."""
    with _base_instalada() as (conexion, motor):
        esquema = _esquema_de_institucion(_INSTITUCION)
        solicitante = _identidad_por_correo(motor, esquema, _CORREO_SOLICITANTE)
        administrador = _identidad_por_correo(
            motor, esquema, _CORREO_ADMINISTRADOR
        )
        sede_id = _sede_del_departamento(
            motor, esquema, solicitante.usuario.departamento_id
        )
        producto_id = _producto_con_stock(
            motor, esquema, sede_id=sede_id, cantidad=2
        )
        ticket_id = _crear_ticket_en_revision(
            motor,
            esquema,
            solicitante,
            producto_id=producto_id,
            cantidad=2,
        )
        estado_en_curso_id = _estado_id_por_nombre(motor, esquema, "EnCurso")

        columnas_antes = _columnas_del_esquema(conexion, esquema)
        stock_antes = _stock_de_la_sede(motor, esquema, ticket_id)

        def _aprobar(nombre: str):
            def _tarea() -> str:
                with _sesion_tenant(motor, esquema) as db:
                    respuesta = ticket_service.aprobar_ticket(
                        db, ticket_id, administrador
                    )
                    assert respuesta.estado_id == estado_en_curso_id
                    assert respuesta.etiqueta_proceso
                return f"ok:{nombre}"

            return _tarea

        resultados = _correr_en_paralelo(_aprobar("primera"), _aprobar("segunda"))
        _assert_un_200_y_un_409(resultados)

        estado, fecha_cierre = _estado_y_cierre(motor, esquema, ticket_id)
        assert estado == "EnCurso", estado
        assert fecha_cierre is None, (
            "la aprobacion no sella `fecha_cierre` (D-5)"
        )
        assert _stock_de_la_sede(motor, esquema, ticket_id) == stock_antes, (
            "la aprobacion no toca stock (D-17/D-18)"
        )
        assert _columnas_del_esquema(conexion, esquema) == columnas_antes, (
            "la aprobacion no crea tablas ni columnas (sin DDL)"
        )

        filas = _historial_por_sql(
            conexion, esquema, ticket_id, MOTIVO_APROBACION
        )
        assert len(filas) == 1, filas
        (
            actor_id,
            fecha_transicion,
            motivo,
            orden_compra_id,
            origen,
            destino,
        ) = filas[0]
        assert actor_id == administrador.usuario.usuario_id
        assert fecha_transicion is not None
        assert motivo == MOTIVO_APROBACION
        assert orden_compra_id is None, (
            "la aprobacion deja `orden_compra_id` nulo (D-16)"
        )
        assert (origen, destino) == ("EnRevision", "EnCurso")


# ---------------------------------------------------------------------------
# AC-42/AC-43: confirmacion concurrente
# ---------------------------------------------------------------------------


def test_confirmacion_concurrente_deja_una_sola_fila_cerrado_cerrado_ac_42():
    """AC-42/AC-43: dos confirmaciones simultaneas -> (200, 409) y una fila."""
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
        ticket_id = _crear_ticket_en_revision(
            motor,
            esquema,
            solicitante,
            producto_id=producto_id,
            cantidad=3,
        )
        # Flujo real hasta el retiro: aprobacion y cierre de la 005.
        with _sesion_tenant(motor, esquema) as db:
            ticket_service.aprobar_ticket(db, ticket_id, administrador)
        _retirar(motor, esquema, bodeguero, ticket_id)

        estado_antes, fecha_cierre_antes = _estado_y_cierre(
            motor, esquema, ticket_id
        )
        assert estado_antes == "Cerrado"
        assert fecha_cierre_antes is not None
        stock_antes = _stock_de_la_sede(motor, esquema, ticket_id)
        movimientos_antes = _contar_movimientos_de_la_sede(
            motor, esquema, ticket_id
        )
        columnas_antes = _columnas_del_esquema(conexion, esquema)

        def _confirmar(nombre: str):
            def _tarea() -> str:
                with _sesion_tenant(motor, esquema) as db:
                    respuesta = ticket_service.confirmar_entrega_ticket(
                        db, ticket_id, solicitante
                    )
                    assert respuesta.entrega_confirmada is True
                    assert respuesta.etiqueta_proceso == ETIQUETA_ENTREGADO
                return f"ok:{nombre}"

            return _tarea

        resultados = _correr_en_paralelo(
            _confirmar("primera"), _confirmar("segunda")
        )
        _assert_un_200_y_un_409(resultados)

        estado, fecha_cierre = _estado_y_cierre(motor, esquema, ticket_id)
        assert estado == "Cerrado", "la confirmacion no reabre ni cambia el estado"
        assert fecha_cierre == fecha_cierre_antes, (
            "la confirmacion no sella ni borra `fecha_cierre` (D-5/D-25)"
        )
        assert _stock_de_la_sede(motor, esquema, ticket_id) == stock_antes, (
            "la confirmacion no toca stock"
        )
        assert (
            _contar_movimientos_de_la_sede(motor, esquema, ticket_id)
            == movimientos_antes
        ), "la confirmacion no crea movimientos de inventario"
        assert _columnas_del_esquema(conexion, esquema) == columnas_antes, (
            "la confirmacion no crea tablas ni columnas (sin DDL)"
        )

        filas = _historial_por_sql(
            conexion, esquema, ticket_id, MOTIVO_CONFIRMACION
        )
        assert len(filas) == 1, filas
        (
            actor_id,
            fecha_transicion,
            motivo,
            orden_compra_id,
            origen,
            destino,
        ) = filas[0]
        assert actor_id == solicitante.usuario.usuario_id
        assert fecha_transicion is not None
        assert motivo == MOTIVO_CONFIRMACION
        assert orden_compra_id is None, (
            "la confirmacion deja `orden_compra_id` nulo (D-25)"
        )
        assert (origen, destino) == ("Cerrado", "Cerrado")


# ---------------------------------------------------------------------------
# AC-30/AC-42: lectura persistida del flujo completo y ausencia de DDL
# ---------------------------------------------------------------------------


def test_lectura_persistida_del_flujo_y_sin_ddl_ac_30_ac_42():
    """AC-30/AC-42: el flujo secuencial deja las filas exactas, sin DDL."""
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
        ticket_id = _crear_ticket_en_revision(
            motor,
            esquema,
            solicitante,
            producto_id=producto_id,
            cantidad=2,
        )
        columnas_instalacion = _columnas_del_esquema(conexion, esquema)

        with _sesion_tenant(motor, esquema) as db:
            ticket_service.aprobar_ticket(db, ticket_id, administrador)

        filas_aprobacion = _historial_por_sql(
            conexion, esquema, ticket_id, MOTIVO_APROBACION
        )
        assert len(filas_aprobacion) == 1, filas_aprobacion
        (
            actor_aprobacion,
            fecha_aprobacion,
            motivo_aprobacion,
            orden_aprobacion,
            origen_aprobacion,
            destino_aprobacion,
        ) = filas_aprobacion[0]
        assert actor_aprobacion == administrador.usuario.usuario_id
        assert fecha_aprobacion is not None
        assert motivo_aprobacion == MOTIVO_APROBACION
        assert orden_aprobacion is None
        assert (origen_aprobacion, destino_aprobacion) == (
            "EnRevision",
            "EnCurso",
        )

        _retirar(motor, esquema, bodeguero, ticket_id)
        _estado, fecha_cierre_retiro = _estado_y_cierre(
            motor, esquema, ticket_id
        )
        assert fecha_cierre_retiro is not None
        stock_retiro = _stock_de_la_sede(motor, esquema, ticket_id)
        movimientos_retiro = _contar_movimientos_de_la_sede(
            motor, esquema, ticket_id
        )

        with _sesion_tenant(motor, esquema) as db:
            respuesta = ticket_service.confirmar_entrega_ticket(
                db, ticket_id, solicitante
            )
        assert respuesta.entrega_confirmada is True
        assert respuesta.etiqueta_proceso == ETIQUETA_ENTREGADO

        estado, fecha_cierre = _estado_y_cierre(motor, esquema, ticket_id)
        assert estado == "Cerrado"
        assert fecha_cierre == fecha_cierre_retiro, (
            "la confirmacion no toca `fecha_cierre`"
        )
        assert _stock_de_la_sede(motor, esquema, ticket_id) == stock_retiro
        assert (
            _contar_movimientos_de_la_sede(motor, esquema, ticket_id)
            == movimientos_retiro
        )

        filas_confirmacion = _historial_por_sql(
            conexion, esquema, ticket_id, MOTIVO_CONFIRMACION
        )
        assert len(filas_confirmacion) == 1, filas_confirmacion
        (
            actor_confirmacion,
            fecha_confirmacion,
            motivo_confirmacion,
            orden_confirmacion,
            origen_confirmacion,
            destino_confirmacion,
        ) = filas_confirmacion[0]
        assert actor_confirmacion == solicitante.usuario.usuario_id
        assert fecha_confirmacion is not None
        assert motivo_confirmacion == MOTIVO_CONFIRMACION
        assert orden_confirmacion is None
        assert (origen_confirmacion, destino_confirmacion) == (
            "Cerrado",
            "Cerrado",
        )

        assert _columnas_del_esquema(conexion, esquema) == columnas_instalacion, (
            "el flujo completo no crea tablas ni columnas (sin DDL)"
        )
