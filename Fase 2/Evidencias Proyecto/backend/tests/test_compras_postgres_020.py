"""T5 (Feature 020): compras sobre PostgreSQL 16 real - gated.

La suite SQLite no puede acreditar lo que la Feature 020 exige del motor:

  * **DT-1/AC-2** - el catalogo global vive en `control.proveedor` y cada tenant
    conserva una replica con el **mismo** `proveedor_id`; el Superadmin crea en
    control y **no** replica, el Administrador crea y replica;
  * **DT-10/AC-14** - la FK compuesta `(orden_compra_id, proveedor_id)` de
    `factura_compra` rechaza una factura de un proveedor distinto al de la OC;
  * **AC-7/AC-9** - dos recepciones concurrentes de la misma OC se serializan:
    una confirma y la otra recibe 409; el stock y el movimiento se escriben una
    sola vez;
  * **AC-11/§9.10** - un producto desactivado despues de la emision se
    recepciona y deja auditoria, mientras que el endpoint generico de
    movimientos conserva su 409.

COMO ACTIVARLA
    docker compose -f docker-compose.yml up -d db
    $env:POSTGRES_TEST_URL = "postgresql://postgres:postgres@localhost:5433/postgres"
    cd backend; python -m pytest tests/test_compras_postgres_020.py

    Sin `POSTGRES_TEST_URL` la prueba se **salta** con una razon clara y la
    suite ordinaria no cambia. La URL apunta a una base de mantenimiento donde
    el modulo crea y DESTRUYE una base temporal propia con guardia fail-closed;
    nunca toca `apt_erp`.
"""

from __future__ import annotations

import os
import threading
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
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
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload
from sqlalchemy.pool import NullPool

from app.models import (
    FacturaCompra,
    MovimientoInventario,
    OrdenCompra,
    Producto,
    Proveedor,
    ProveedorControl,
    Rol,
    Sede,
    StockSede,
    Usuario,
)
from app.schemas.compra_schema import (
    DetalleOrdenCompraCrear,
    FacturaCompraRegistrar,
    OrdenCompraCrear,
    ProveedorCrear,
)
from app.schemas.inventario_schema import MovimientoCrear
from app.services import compra_service, inventario_service
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

RAIZ = Path(__file__).resolve().parents[2]
ESQUEMA_SQL = RAIZ / "database" / "01_esquema.sql"
SEMILLA_SQL = RAIZ / "database" / "02_datos_semilla.sql"

_INSTITUCION = "INST-001"
_PROVEEDORES_SEMILLA = (1, 2, 3)
_APP_CONCURRENCIA = "compustock_020_race"


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
    nombre = f"compustock_020_{uuid4().hex[:12]}"
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


def _un_escalar(conexion, sql: str, params=None):
    return _ejecutar(conexion, sql, params)[0][0]


def _ejecutar_script(conexion, ruta: Path) -> None:
    _ejecutar(conexion, ruta.read_text(encoding="utf-8"))


def _instalar(conexion) -> None:
    _ejecutar_script(conexion, ESQUEMA_SQL)
    _ejecutar_script(conexion, SEMILLA_SQL)


def _esquema_de_institucion(institucion_id: str) -> str:
    from app.services.tenant_service import nombre_esquema_para_institucion

    return nombre_esquema_para_institucion(institucion_id)


def _instituciones(conexion) -> list[str]:
    return [
        fila[0]
        for fila in _ejecutar(
            conexion,
            "SELECT institucion_id FROM control.institucion ORDER BY institucion_id",
        )
    ]


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
def _sesion_control(motor):
    from app.db.database import crear_sesion_control

    db = crear_sesion_control(motor=motor)
    try:
        yield db
    finally:
        db.close()


@contextmanager
def _sesion_tenant(motor, esquema):
    from app.db.database import crear_sesion_esquema

    db = crear_sesion_esquema(esquema, motor=motor)
    try:
        yield db
    finally:
        db.close()


def _identidad(motor, esquema: str, rol: str, *, requiere_sede: bool = False):
    """Identidad suelta con ids persistidos del tenant (sin acoplar la sesion)."""
    with _sesion_tenant(motor, esquema) as db:
        consulta = (
            select(Usuario)
            .options(joinedload(Usuario.rol))
            .join(Usuario.rol)
            .where(Rol.nombre_rol == rol)
            .order_by(Usuario.usuario_id)
        )
        if requiere_sede:
            consulta = consulta.where(Usuario.sede_id.is_not(None))
        actor = db.execute(consulta.limit(1)).scalars().first()
        assert actor is not None, f"la semilla debe tener un {rol} en {esquema}"
        datos = {
            "usuario_id": actor.usuario_id,
            "nombre": actor.nombre,
            "apellido": actor.apellido,
            "correo": actor.correo,
            "departamento_id": actor.departamento_id,
            "rol_id": actor.rol_id,
            "sede_id": actor.sede_id,
        }

    usuario = Usuario(**datos)
    usuario.rol = Rol(rol_id=datos["rol_id"], nombre_rol=rol)
    return IdentidadAutenticada(usuario=usuario, sub=f"test-020-{rol.lower()}")


def _identidad_superadmin() -> IdentidadAutenticada:
    """Identidad SaaS sin tenant: `crear_proveedor` no resuelve institucion."""
    usuario = Usuario(
        nombre="QA",
        apellido="SaaS",
        correo="qa.saas@020.cl",
        departamento_id=None,
        rol_id=1,
    )
    usuario.rol = Rol(rol_id=1, nombre_rol="Superadmin")
    return IdentidadAutenticada(usuario=usuario, sub="test-020-superadmin")


def _primer_producto(motor, esquema: str) -> int:
    with _sesion_tenant(motor, esquema) as db:
        producto_id = db.execute(
            select(Producto.producto_id)
            .where(Producto.institucion_id == _INSTITUCION)
            .where(Producto.activo.is_(True))
            .order_by(Producto.producto_id)
            .limit(1)
        ).scalar_one_or_none()
    assert producto_id is not None, "la semilla debe tener un producto activo"
    return producto_id


def _sede_del_bodeguero(motor, esquema: str) -> int:
    bodeguero = _identidad(motor, esquema, "Bodeguero", requiere_sede=True)
    sede_id = bodeguero.usuario.sede_id
    assert sede_id is not None, "la semilla debe tener un Bodeguero con sede"
    return sede_id


def _reiniciar_stock(motor, esquema: str, sede_id: int, producto_id: int) -> None:
    with _sesion_tenant(motor, esquema) as db:
        fila = db.execute(
            select(StockSede).where(
                StockSede.sede_id == sede_id,
                StockSede.producto_id == producto_id,
            )
        ).scalar_one_or_none()
        if fila is None:
            db.add(
                StockSede(
                    sede_id=sede_id,
                    producto_id=producto_id,
                    institucion_id=_INSTITUCION,
                    stock_actual=0,
                )
            )
        else:
            fila.stock_actual = 0
        db.commit()


def _orden_facturada(
    motor, esquema: str, *, sede_id: int, cantidad: int = 5
) -> tuple[int, int]:
    """OC `Facturada` lista para recepcionar; devuelve `(orden_id, producto_id)`."""
    producto_id = _primer_producto(motor, esquema)
    _reiniciar_stock(motor, esquema, sede_id, producto_id)
    admin = _identidad(motor, esquema, "Administrador")

    with _sesion_control(motor) as db_control, _sesion_tenant(
        motor, esquema
    ) as db_tenant:
        orden = compra_service.crear_orden_compra(
            db_tenant,
            db_control,
            OrdenCompraCrear(
                sede_id=sede_id,
                proveedor_id=_PROVEEDORES_SEMILLA[0],
                items=[
                    DetalleOrdenCompraCrear(
                        producto_id=producto_id,
                        cantidad_solicitada=cantidad,
                        precio_unitario=Decimal("1.50"),
                    )
                ],
            ),
            admin,
        )
        orden_id = orden.orden_compra_id

    with _sesion_tenant(motor, esquema) as db:
        compra_service.emitir_orden_compra(db, orden_id, admin)
        compra_service.registrar_o_editar_factura(
            db,
            orden_id,
            FacturaCompraRegistrar(
                numero_factura=f"FAC-020-{orden_id:06d}",
                fecha_factura=date.today(),
                monto_total=Decimal("7.50"),
            ),
            admin,
        )
    return orden_id, producto_id


def _estado_orden(motor, esquema: str, orden_id: int) -> dict:
    with _sesion_tenant(motor, esquema) as db:
        orden = db.get(OrdenCompra, orden_id)
        assert orden is not None
        return {
            "estado": orden.estado,
            "fecha_recepcion": orden.fecha_recepcion,
            "detalles": len(orden.detalles),
        }


def _stock_y_movimientos(motor, esquema: str, sede_id: int, producto_id: int):
    with _sesion_tenant(motor, esquema) as db:
        stock = db.execute(
            select(StockSede.stock_actual).where(
                StockSede.sede_id == sede_id,
                StockSede.producto_id == producto_id,
            )
        ).scalar_one_or_none()
        stock_sede_id = db.execute(
            select(StockSede.stock_sede_id).where(
                StockSede.sede_id == sede_id,
                StockSede.producto_id == producto_id,
            )
        ).scalar_one_or_none()
        movimientos = []
        if stock_sede_id is not None:
            movimientos = list(
                db.execute(
                    select(MovimientoInventario).where(
                        MovimientoInventario.stock_sede_id == stock_sede_id
                    )
                )
                .scalars()
                .all()
            )
        return stock, movimientos


def _correr_en_paralelo(primera, segunda) -> dict[str, str]:
    """Arranca dos sesiones a la vez con una barrera y devuelve sus resultados."""
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
        hilo.join(timeout=30)

    assert not any(hilo.is_alive() for hilo in hilos), (
        "una carrera quedo colgada: posible deadlock o bloqueo sin liberar"
    )
    assert set(resultados) == {"primera", "segunda"}, resultados
    return resultados


# ---------------------------------------------------------------------------
# DT-1/AC-2: semilla y replica con el mismo ID
# ---------------------------------------------------------------------------


def test_semilla_replica_los_tres_proveedores_con_el_mismo_id():
    """AC-2/DT-1: control conserva 3 y cada tenant los replica con el mismo id."""
    with _base_instalada() as (conexion, motor):
        assert (
            _un_escalar(conexion, "SELECT count(*) FROM control.proveedor") == 3
        )
        assert (
            _un_escalar(
                conexion,
                "SELECT count(*) FROM control.proveedor WHERE activo IS NOT TRUE",
            )
            == 0
        )

        with _sesion_control(motor) as db:
            catalogo = {
                fila.proveedor_id: (fila.rut, fila.razon_social)
                for fila in db.execute(
                    select(ProveedorControl).order_by(ProveedorControl.proveedor_id)
                )
                .scalars()
                .all()
            }
        assert tuple(catalogo) == _PROVEEDORES_SEMILLA

        for institucion_id in _instituciones(conexion):
            esquema = _esquema_de_institucion(institucion_id)
            with _sesion_tenant(motor, esquema) as db:
                replicas = {
                    fila.proveedor_id: (fila.rut, fila.razon_social)
                    for fila in db.execute(
                        select(Proveedor).order_by(Proveedor.proveedor_id)
                    )
                    .scalars()
                    .all()
                }
            assert replicas == catalogo, esquema


def test_factura_compra_usa_una_fk_compuesta_hacia_la_orden():
    """DT-10/AC-14: la FK (orden_compra_id, proveedor_id) tambien existe en el tenant."""
    with _base_instalada() as (conexion, motor):
        for institucion_id in _instituciones(conexion):
            esquema = _esquema_de_institucion(institucion_id)
            columnas = {
                fila[0]
                for fila in _ejecutar(
                    conexion,
                    "SELECT kcu.column_name "
                    "FROM information_schema.table_constraints tc "
                    "JOIN information_schema.key_column_usage kcu "
                    "  ON kcu.constraint_name = tc.constraint_name "
                    " AND kcu.constraint_schema = tc.constraint_schema "
                    "JOIN information_schema.constraint_column_usage ccu "
                    "  ON ccu.constraint_name = tc.constraint_name "
                    " AND ccu.constraint_schema = tc.constraint_schema "
                    "WHERE tc.constraint_type = 'FOREIGN KEY' "
                    "  AND tc.table_schema = %s "
                    "  AND tc.table_name = 'factura_compra' "
                    "  AND ccu.table_name = 'orden_compra'",
                    (esquema,),
                )
            }
            assert {"orden_compra_id", "proveedor_id"} <= columnas, esquema


# ---------------------------------------------------------------------------
# DT-1/AC-2: alta en control y replica segun el rol
# ---------------------------------------------------------------------------


def test_administrador_replica_y_superadmin_no_replica():
    """AC-2: el Administrador crea control + tenant; el Superadmin solo control."""
    with _base_instalada() as (_conexion, motor):
        esquema = _esquema_de_institucion(_INSTITUCION)
        admin = _identidad(motor, esquema, "Administrador")

        with _sesion_control(motor) as db_control, _sesion_tenant(
            motor, esquema
        ) as db_tenant:
            creado = compra_service.crear_proveedor(
                db_control,
                db_tenant,
                ProveedorCrear(
                    rut="91.000.000-1",
                    razon_social="Replica Administrador 020",
                    giro="Papeleria",
                ),
                admin,
            )
            proveedor_admin = creado.proveedor_id

        with _sesion_control(motor) as db:
            assert db.get(ProveedorControl, proveedor_admin) is not None
        with _sesion_tenant(motor, esquema) as db:
            replica = db.get(Proveedor, proveedor_admin)
            assert replica is not None
            assert replica.rut == "91.000.000-1"
            assert replica.razon_social == "Replica Administrador 020"

        with _sesion_control(motor) as db_control, _sesion_tenant(
            motor, esquema
        ) as db_tenant:
            desde_saas = compra_service.crear_proveedor(
                db_control,
                db_tenant,
                ProveedorCrear(
                    rut="92.000.000-2",
                    razon_social="Catalogo Superadmin 020",
                ),
                _identidad_superadmin(),
            )
            proveedor_saas = desde_saas.proveedor_id

        with _sesion_control(motor) as db:
            assert db.get(ProveedorControl, proveedor_saas) is not None
        with _sesion_tenant(motor, esquema) as db:
            assert db.get(Proveedor, proveedor_saas) is None
            assert (
                db.execute(
                    select(func.count())
                    .select_from(Proveedor)
                    .where(Proveedor.rut == "92.000.000-2")
                ).scalar_one()
                == 0
            )


def test_factura_con_proveedor_distinto_al_de_la_orden_viola_la_fk():
    """DT-10: la FK compuesta rechaza una factura de otro proveedor."""
    with _base_instalada() as (_conexion, motor):
        esquema = _esquema_de_institucion(_INSTITUCION)
        admin = _identidad(motor, esquema, "Administrador")
        producto_id = _primer_producto(motor, esquema)
        sede_id = _sede_del_bodeguero(motor, esquema)

        with _sesion_control(motor) as db_control, _sesion_tenant(
            motor, esquema
        ) as db_tenant:
            orden = compra_service.crear_orden_compra(
                db_tenant,
                db_control,
                OrdenCompraCrear(
                    sede_id=sede_id,
                    proveedor_id=_PROVEEDORES_SEMILLA[0],
                    items=[
                        DetalleOrdenCompraCrear(
                            producto_id=producto_id,
                            cantidad_solicitada=1,
                            precio_unitario=Decimal("1.00"),
                        )
                    ],
                ),
                admin,
            )
            orden_id = orden.orden_compra_id

        with _sesion_tenant(motor, esquema) as db:
            db.add(
                FacturaCompra(
                    orden_compra_id=orden_id,
                    proveedor_id=_PROVEEDORES_SEMILLA[1],
                    numero_factura="FAC-FK-020",
                    fecha_factura=date.today(),
                    monto_total=Decimal("1.00"),
                )
            )
            with pytest.raises(IntegrityError):
                db.commit()
            db.rollback()

        with _sesion_tenant(motor, esquema) as db:
            assert (
                db.execute(
                    select(func.count())
                    .select_from(FacturaCompra)
                    .where(FacturaCompra.orden_compra_id == orden_id)
                ).scalar_one()
                == 0
            )


# ---------------------------------------------------------------------------
# AC-7/AC-9: recepcion concurrente
# ---------------------------------------------------------------------------


def test_recepcion_concurrente_incrementa_el_stock_una_sola_vez():
    """AC-7/AC-9: una recepcion gana, la otra recibe 409 y el stock sube una vez."""
    with _base_instalada() as (_conexion, motor):
        esquema = _esquema_de_institucion(_INSTITUCION)
        cantidad = 5
        bodeguero = _identidad(motor, esquema, "Bodeguero", requiere_sede=True)
        sede_id = bodeguero.usuario.sede_id
        assert sede_id is not None
        orden_id, producto_id = _orden_facturada(
            motor, esquema, sede_id=sede_id, cantidad=cantidad
        )

        def _recibir(nombre: str):
            def _tarea() -> str:
                with _sesion_tenant(motor, esquema) as db:
                    resultado = compra_service.recepcionar_orden_compra(
                        db, orden_id, bodeguero
                    )
                    assert resultado.estado == "Recibida"
                return f"ok:{nombre}"

            return _tarea

        resultados = _correr_en_paralelo(
            _recibir("primera"), _recibir("segunda")
        )
        valores = sorted(resultados.values())
        assert valores.count("http:409") == 1, resultados
        assert sum(valor.startswith("ok:") for valor in valores) == 1, resultados

        estado = _estado_orden(motor, esquema, orden_id)
        assert estado["estado"] == "Recibida"
        assert estado["fecha_recepcion"] is not None

        stock, movimientos = _stock_y_movimientos(
            motor, esquema, sede_id, producto_id
        )
        assert stock == cantidad
        entradas = [
            movimiento
            for movimiento in movimientos
            if movimiento.tipo_movimiento == inventario_service.TIPO_ENTRADA
        ]
        assert len(entradas) == 1
        assert entradas[0].cantidad == cantidad
        assert "FAC-020-" in (entradas[0].observacion or "")


# ---------------------------------------------------------------------------
# AC-11/§9.10: producto inactivo despues de la emision
# ---------------------------------------------------------------------------


def test_recepcion_audita_producto_inactivo_y_movimiento_generico_sigue_en_409():
    """AC-11: la recepcion excepcional procede; el endpoint generico responde 409."""
    with _base_instalada() as (_conexion, motor):
        esquema = _esquema_de_institucion(_INSTITUCION)
        bodeguero = _identidad(motor, esquema, "Bodeguero", requiere_sede=True)
        sede_id = bodeguero.usuario.sede_id
        assert sede_id is not None
        orden_id, producto_id = _orden_facturada(
            motor, esquema, sede_id=sede_id, cantidad=3
        )

        with _sesion_tenant(motor, esquema) as db:
            producto = db.get(Producto, producto_id)
            producto.activo = False
            db.commit()

        with _sesion_tenant(motor, esquema) as db:
            resultado = compra_service.recepcionar_orden_compra(
                db, orden_id, bodeguero
            )
            assert resultado.estado == "Recibida"

        stock, movimientos = _stock_y_movimientos(
            motor, esquema, sede_id, producto_id
        )
        assert stock == 3
        assert len(movimientos) == 1
        assert movimientos[0].tipo_movimiento == inventario_service.TIPO_ENTRADA

        with _sesion_tenant(motor, esquema) as db:
            fila = db.execute(
                select(StockSede).where(
                    StockSede.sede_id == sede_id,
                    StockSede.producto_id == producto_id,
                )
            ).scalar_one()
            with pytest.raises(HTTPException) as error:
                inventario_service.registrar_movimiento(
                    db,
                    MovimientoCrear(
                        stock_sede_id=fila.stock_sede_id,
                        tipo_movimiento="ENTRADA",
                        cantidad=1,
                        observacion="Movimiento generico sobre producto inactivo",
                    ),
                    bodeguero,
                )
        assert error.value.status_code == 409
