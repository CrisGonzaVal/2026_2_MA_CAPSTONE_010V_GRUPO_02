"""T33 (enmienda 26/Nov/2026 de la 013): catalogo y semilla - gated PostgreSQL 16.

Complemento gated de `test_catalogo_estados_013.py`. SQLite no reproduce los
esquemas por tenant ni el DDL de instalacion limpia, asi que el contrato de
D-36 solo se acredita contra PostgreSQL 16 real:

  * la instalacion limpia (`01_esquema.sql` + `02_datos_semilla.sql`) deja
    **cuatro** filas de `estado_ticket` en cada tenant (`EnRevision`, `EnCurso`,
    `Cerrado`, `Anulado`), sin `Pendiente` ni homonimas y sin descripciones de
    despacho;
  * los tickets de la semilla quedan reenumerados: 1-4 y 9 en `EnRevision`,
    5-6 en `EnCurso`, 7-8 y 10 en `Cerrado`, ninguno en `Anulado`; los
    `Cerrado` conservan `fecha_cierre` y `cantidad_entregada = solicitada`;
  * `control.estado_ticket` conserva solo la fila `Anulado` tras la limpieza;
  * el aprovisionamiento de un tenant nuevo replica las cuatro filas, `Anulado`
    incluido (el catalogo de `control_service._ESTADOS_TICKET_TENANT`);
  * la instalacion conserva 25 tablas en `control`, 22 por tenant y el token
    `026.1` desde la enmienda 27/Nov/2026 de la 012.

COMO ACTIVARLAS
    docker compose -f docker-compose.yml up -d db
    $env:POSTGRES_TEST_URL = "postgresql://postgres:postgres@localhost:5433/postgres"
    cd backend; python -m pytest tests/funcional/sistema/test_catalogo_retiro_postgres_013.py

    Sin `POSTGRES_TEST_URL` los tests se **saltan**. La URL apunta a una base de
    mantenimiento donde el test crea y DESTRUYE una base temporal propia; nunca
    toca `apt_erp`.
"""

from __future__ import annotations

import os
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

from app.core.config import VERSION_ESQUEMA_OBJETIVO

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

#: Catalogo canonico de la enmienda (spec §10.7, plan §10.3). El orden y las
#: descripciones son contrato; los ids son solo la semilla.
CATALOGO = (
    ("EnRevision", "Pedido creado, en revision por la Administracion"),
    ("EnCurso", "Aprobado y en preparacion para el retiro"),
    ("Cerrado", "Retirado y con fecha de cierre registrada"),
    (
        "Anulado",
        "Anulado o rechazado con motivo; si hubo retiro, el stock fue devuelto",
    ),
)

#: Reparto de la semilla por institucion: `{ticket_id: estado_id}`.
TICKETS_POR_INSTITUCION = {
    "INST-001": {1: 1, 2: 1, 3: 1, 4: 1, 5: 2, 6: 2, 7: 3, 8: 3},
    "INST-002": {9: 1, 10: 3},
}


# ---------------------------------------------------------------------------
# Conexion y utilidades
# ---------------------------------------------------------------------------


def _sin_driver(url: str) -> str:
    return url.replace("postgresql+psycopg2://", "postgresql://")


def _url_con_base(url: str, nombre: str) -> str:
    partes = urlsplit(url)
    return urlunsplit((partes.scheme, partes.netloc, "/" + nombre, "", ""))


@contextmanager
def _base_temporal():
    """Crea una base efimera y la destruye al salir; nunca toca `apt_erp`."""
    dsn = _sin_driver(_POSTGRES_TEST_URL or "")
    admin = psycopg2.connect(dsn)
    admin.autocommit = True
    nombre = f"compustock_t33_{uuid4().hex[:12]}"
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


def _instalar(conexion) -> None:
    _ejecutar(conexion, ESQUEMA_SQL.read_text(encoding="utf-8"))
    _ejecutar(conexion, SEMILLA_SQL.read_text(encoding="utf-8"))


def _instituciones(conexion) -> list[str]:
    return [
        fila[0]
        for fila in _ejecutar(
            conexion,
            "SELECT institucion_id FROM control.institucion "
            "WHERE institucion_id <> 'CTRL-SAAS' ORDER BY institucion_id",
        )
    ]


def _esquema_de_institucion(institucion_id: str) -> str:
    from app.services.tenant_service import nombre_esquema_para_institucion

    return nombre_esquema_para_institucion(institucion_id)


def _tablas_del_esquema(conexion, esquema: str) -> set[str]:
    filas = _ejecutar(
        conexion,
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = %s AND table_type = 'BASE TABLE'",
        (esquema,),
    )
    return {fila[0] for fila in filas}


def _motor_sqlalchemy(conexion):
    from sqlalchemy import create_engine
    from sqlalchemy.pool import NullPool

    nombre_base = conexion.get_dsn_parameters()["dbname"]
    url = _url_con_base(_sin_driver(_POSTGRES_TEST_URL or ""), nombre_base)
    url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return create_engine(url, poolclass=NullPool, future=True)


# ---------------------------------------------------------------------------
# AC-50/D-36: catalogo replicado por tenant y control limpio
# ---------------------------------------------------------------------------


def test_la_semilla_deja_cuatro_estados_en_cada_tenant_ac_50():
    """AC-50: cuatro filas por tenant, sin `Pendiente` y sin «despacho»."""
    with _base_temporal() as conexion:
        _instalar(conexion)

        for institucion_id in _instituciones(conexion):
            esquema = _esquema_de_institucion(institucion_id)
            filas = _ejecutar(
                conexion,
                f'SELECT estado_id, nombre, descripcion '
                f'FROM "{esquema}".estado_ticket ORDER BY estado_id',
            )
            assert [(nombre, descripcion) for _, nombre, descripcion in filas] == list(
                CATALOGO
            ), esquema
            assert [estado_id for estado_id, _, _ in filas] == [1, 2, 3, 4], esquema
            nombres = [nombre for _, nombre, _ in filas]
            assert len(set(nombres)) == 4, f"homonimas en {esquema}: {nombres}"
            assert "Pendiente" not in nombres, esquema
            assert "Anulado" in nombres, esquema
            for _, nombre, descripcion in filas:
                texto = (descripcion or "").lower()
                assert "despacho" not in texto, (esquema, nombre, descripcion)
                assert "pendiente" not in texto, (esquema, nombre, descripcion)


def test_control_conserva_solo_anulado_tras_la_limpieza_ac_50():
    """AC-50/D-36: `control.estado_ticket` queda solo con `Anulado`."""
    with _base_temporal() as conexion:
        _instalar(conexion)

        filas = _ejecutar(
            conexion, "SELECT nombre FROM control.estado_ticket ORDER BY estado_id"
        )
        assert [fila[0] for fila in filas] == ["Anulado"]


def test_la_semilla_reenumera_los_tickets_y_conserva_los_cerrados_ac_50():
    """AC-50: 1-4/9 -> EnRevision, 5-6 -> EnCurso, 7-8/10 -> Cerrado; ninguno Anulado."""
    with _base_temporal() as conexion:
        _instalar(conexion)

        for institucion_id, esperado in TICKETS_POR_INSTITUCION.items():
            esquema = _esquema_de_institucion(institucion_id)
            filas = _ejecutar(
                conexion,
                f'SELECT ticket_id, estado_id, fecha_cierre '
                f'FROM "{esquema}".ticket ORDER BY ticket_id',
            )
            assert {ticket_id: estado_id for ticket_id, estado_id, _ in filas} == esperado, (
                esquema
            )
            assert 4 not in {estado_id for _, estado_id, _ in filas}, (
                f"{esquema} no puede tener tickets en Anulado"
            )
            for ticket_id, estado_id, fecha_cierre in filas:
                if estado_id == 3:
                    assert fecha_cierre is not None, (esquema, ticket_id)
                else:
                    assert fecha_cierre is None, (esquema, ticket_id)

            detalles = _ejecutar(
                conexion,
                f'SELECT d.ticket_id, d.cantidad_solicitada, '
                f'd.cantidad_entregada, t.estado_id '
                f'FROM "{esquema}".detalle_ticket d '
                f'JOIN "{esquema}".ticket t ON t.ticket_id = d.ticket_id '
                f'ORDER BY d.detalle_ticket_id',
            )
            for ticket_id, solicitada, entregada, estado_id in detalles:
                if estado_id == 3:
                    assert entregada == solicitada, (esquema, ticket_id)
                else:
                    assert entregada == 0, (esquema, ticket_id)

        for institucion_id in ("INST-003", "INST-004"):
            esquema = _esquema_de_institucion(institucion_id)
            assert _un_escalar(conexion, f'SELECT count(*) FROM "{esquema}".ticket') == 0


def test_la_instalacion_conserva_25_y_22_tablas_y_el_token_026_1_ac_50():
    """AC-50/AC-33: el retiro deja 25 tablas en control, 22 por tenant y `026.1`."""
    with _base_temporal() as conexion:
        _instalar(conexion)

        assert len(_tablas_del_esquema(conexion, "control")) == 25
        assert (
            _un_escalar(conexion, "SELECT version FROM control.version_esquema")
            == VERSION_ESQUEMA_OBJETIVO
        )
        for institucion_id in _instituciones(conexion):
            esquema = _esquema_de_institucion(institucion_id)
            assert len(_tablas_del_esquema(conexion, esquema)) == 22, esquema
            assert (
                _un_escalar(conexion, f'SELECT version FROM "{esquema}".version_esquema')
                == VERSION_ESQUEMA_OBJETIVO
            ), esquema


# ---------------------------------------------------------------------------
# AC-50/D-36: catalogo del aprovisionamiento de un tenant nuevo
# ---------------------------------------------------------------------------


def _datos_institucion():
    from app.schemas.control_schema import InstitucionAltaControlCrear

    return InstitucionAltaControlCrear(
        institucion_id="INST-T033",
        nombre="Institucion de prueba T33",
        rut="91.000.000-4",
        direccion="Av. Catalogo 330",
        correo_administrador="admin.t033@ejemplo.cl",
        nombre_administrador="Ada",
        apellido_administrador="Administradora",
        departamento_nombre_administrativo="Administracion",
    )


def test_un_tenant_aprovisionado_incluye_los_cuatro_estados_ac_50():
    """D-36: el catalogo replicado por `control_service` incluye `Anulado`."""
    from sqlalchemy.schema import CreateSchema

    from app.db.database import ESQUEMA_CONTROL, crear_sesion_control
    from app.models import Base, BaseControl
    from app.services import control_service

    with _base_temporal() as conexion:
        engine = _motor_sqlalchemy(conexion)
        try:
            with engine.begin() as conexion_sql:
                conexion_sql.execute(CreateSchema(ESQUEMA_CONTROL))
            motor_control = engine.execution_options(
                schema_translate_map={None: ESQUEMA_CONTROL}
            )
            BaseControl.metadata.create_all(bind=motor_control)
            Base.metadata.create_all(bind=motor_control)

            sesion_control = crear_sesion_control(engine)
            try:
                control_service.aprovisionar_institucion(
                    sesion_control, _datos_institucion(), lambda _correo: True
                )
            finally:
                sesion_control.close()

            esquema = _esquema_de_institucion("INST-T033")
            filas = _ejecutar(
                conexion,
                f'SELECT nombre, descripcion FROM "{esquema}".estado_ticket '
                f'ORDER BY estado_id',
            )
            assert [nombre for nombre, _ in filas] == [nombre for nombre, _ in CATALOGO]
            assert "Anulado" in {nombre for nombre, _ in filas}
            assert "Pendiente" not in {nombre for nombre, _ in filas}
            for nombre, descripcion in filas:
                texto = (descripcion or "").lower()
                assert "despacho" not in texto, (nombre, descripcion)
                assert "pendiente" not in texto, (nombre, descripcion)
        finally:
            engine.dispose()
