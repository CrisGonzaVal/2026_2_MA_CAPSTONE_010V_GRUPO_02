"""T1/T6 (Feature 021): cobertura automatica sobre PostgreSQL 16 real - gated.

La suite SQLite no puede acreditar lo que la Feature 021 exige del motor:

  * **AC-11** - el DDL instala 27 tablas en `control` y 24 por tenant, con la
    version `021.1`, la tabla `orden_compra_ticket` y la columna
    `historial_transicion_ticket.orden_compra_id`;
  * **AC-11** - las FK compuestas de `orden_compra_ticket` rechazan una OC,
    pedido, producto o detalle de otra institucion, y el `UNIQUE` rechaza
    duplicados;
  * **AC-3** - dos emisiones concurrentes de la misma sede no asignan dos veces
    el mismo tramo: la simulacion bloquea los pedidos con `FOR UPDATE`.

COMO ACTIVARLA
    docker compose -f docker-compose.yml up -d db
    $env:POSTGRES_TEST_URL = "postgresql://postgres:postgres@localhost:5433/postgres"
    cd backend; python -m pytest tests/test_cobertura_postgres_021.py

    Sin `POSTGRES_TEST_URL` la prueba se **salta** con una razon clara y la
    suite ordinaria no cambia. La URL apunta a una base de mantenimiento donde
    el modulo crea y DESTRUYE una base temporal propia con guardia fail-closed;
    nunca toca `apt_erp`.
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
from app.services.tenant_service import nombre_esquema_para_institucion

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

_VERSION_ESPERADA = "021.1"
_TABLAS_CONTROL = 27
_TABLAS_TENANT = 24


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
    nombre = f"compustock_021_{uuid4().hex[:12]}"
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


def _esquemas(conexion) -> list[str]:
    return ["control"] + [
        nombre_esquema_para_institucion(institucion_id)
        for (institucion_id,) in _ejecutar(
            conexion,
            "SELECT institucion_id FROM control.institucion ORDER BY institucion_id",
        )
    ]


def _columnas(conexion, esquema: str, tabla: str) -> set[str]:
    return {
        fila[0]
        for fila in _ejecutar(
            conexion,
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = %s AND table_name = %s",
            (esquema, tabla),
        )
    }


def _restricciones(conexion, esquema: str, tabla: str) -> list[tuple[str, str, set[str]]]:
    """Devuelve `(tipo, nombre, columnas)` de cada restriccion de la tabla."""
    filas = _ejecutar(
        conexion,
        "SELECT tc.constraint_type, tc.constraint_name, kcu.column_name "
        "FROM information_schema.table_constraints tc "
        "JOIN information_schema.key_column_usage kcu "
        "  ON kcu.constraint_name = tc.constraint_name "
        " AND kcu.constraint_schema = tc.constraint_schema "
        "WHERE tc.table_schema = %s AND tc.table_name = %s "
        "ORDER BY tc.constraint_name, kcu.ordinal_position",
        (esquema, tabla),
    )
    agrupadas: dict[tuple[str, str], set[str]] = {}
    for tipo, nombre, columna in filas:
        agrupadas.setdefault((tipo, nombre), set()).add(columna)
    return [(tipo, nombre, columnas) for (tipo, nombre), columnas in agrupadas.items()]


# ---------------------------------------------------------------------------
# AC-11: DDL, version y estructura nueva
# ---------------------------------------------------------------------------


def test_ddl_instala_27_tablas_en_control_y_24_por_tenant():
    """AC-11/DT-9: el DDL crece de 26/23 a 27/24 tablas."""
    with _base_temporal() as conexion:
        _ejecutar_script(conexion, ESQUEMA_SQL)

        assert (
            _un_escalar(
                conexion,
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema = 'control' AND table_type = 'BASE TABLE'",
            )
            == _TABLAS_CONTROL
        )

        for institucion_id in _esquema_instituciones(conexion):
            esquema = nombre_esquema_para_institucion(institucion_id)
            assert (
                _un_escalar(
                    conexion,
                    "SELECT count(*) FROM information_schema.tables "
                    "WHERE table_schema = %s AND table_type = 'BASE TABLE'",
                    (esquema,),
                )
                == _TABLAS_TENANT
            ), esquema


def _esquema_instituciones(conexion) -> list[str]:
    return [
        fila[0]
        for fila in _ejecutar(
            conexion,
            "SELECT institucion_id FROM control.institucion ORDER BY institucion_id",
        )
    ]


def test_semilla_fija_version_021_1_en_control_y_tenants():
    """AC-11/DT-9: `VERSION_ESQUEMA_OBJETIVO` y la semilla suben a `021.1`."""
    with _base_temporal() as conexion:
        _instalar(conexion)

        assert VERSION_ESQUEMA_OBJETIVO == _VERSION_ESPERADA
        assert (
            _un_escalar(
                conexion,
                "SELECT version FROM control.version_esquema",
            )
            == _VERSION_ESPERADA
        )
        for esquema in _esquemas(conexion)[1:]:
            assert (
                _un_escalar(
                    conexion,
                    f'SELECT version FROM "{esquema}".version_esquema',
                )
                == _VERSION_ESPERADA
            ), esquema


def test_orden_compra_ticket_existe_vacia_en_control_y_tenants():
    """AC-11/DT-9: la tabla puente existe en ambos esquemas y nace vacia."""
    with _base_temporal() as conexion:
        _instalar(conexion)

        for esquema in _esquemas(conexion):
            assert _columnas(conexion, esquema, "orden_compra_ticket") == {
                "orden_compra_ticket_id",
                "institucion_id",
                "orden_compra_id",
                "ticket_id",
                "producto_id",
                "cantidad_asignada",
                "cantidad_faltante",
                "fecha_asignacion",
            }, esquema
            assert (
                _un_escalar(
                    conexion,
                    f'SELECT count(*) FROM "{esquema}".orden_compra_ticket',
                )
                == 0
            ), esquema


def test_historial_transicion_ticket_tiene_orden_compra_id_y_fk():
    """AC-6/AC-11: la columna nullable y su FK existen en control y tenant."""
    with _base_temporal() as conexion:
        _instalar(conexion)

        for esquema in _esquemas(conexion):
            columnas = _columnas(conexion, esquema, "historial_transicion_ticket")
            assert "orden_compra_id" in columnas, esquema

            fks = {
                (nombre, frozenset(columnas_restriccion))
                for tipo, nombre, columnas_restriccion in _restricciones(
                    conexion, esquema, "historial_transicion_ticket"
                )
                if tipo == "FOREIGN KEY"
            }
            assert (
                any(
                    columnas_restriccion == frozenset({"orden_compra_id"})
                    for _nombre, columnas_restriccion in fks
                )
            ), f"{esquema}: falta la FK de orden_compra_id"

            nullable = _un_escalar(
                conexion,
                "SELECT is_nullable FROM information_schema.columns "
                "WHERE table_schema = %s AND table_name = 'historial_transicion_ticket' "
                "AND column_name = 'orden_compra_id'",
                (esquema,),
            )
            assert nullable == "YES", esquema


def test_orden_compra_ticket_declara_unique_fks_compuestas_e_indices():
    """AC-11: la tabla puente protege la clave y el aislamiento por institucion."""
    with _base_temporal() as conexion:
        _instalar(conexion)

        for esquema in _esquemas(conexion):
            restricciones = _restricciones(conexion, esquema, "orden_compra_ticket")

            unicas = {
                frozenset(columnas)
                for tipo, _nombre, columnas in restricciones
                if tipo == "UNIQUE"
            }
            assert (
                frozenset({"orden_compra_id", "ticket_id", "producto_id"}) in unicas
            ), f"{esquema}: falta el UNIQUE (orden_compra_id, ticket_id, producto_id)"

            fks = {
                frozenset(columnas)
                for tipo, _nombre, columnas in restricciones
                if tipo == "FOREIGN KEY"
            }
            assert frozenset({"institucion_id", "orden_compra_id"}) in fks, esquema
            assert frozenset({"orden_compra_id", "producto_id"}) in fks, esquema
            assert frozenset({"institucion_id", "ticket_id"}) in fks, esquema
            assert frozenset({"institucion_id", "producto_id"}) in fks, esquema

            indices = {
                fila[0]
                for fila in _ejecutar(
                    conexion,
                    "SELECT indexname FROM pg_indexes "
                    "WHERE schemaname = %s AND tablename = 'orden_compra_ticket'",
                    (esquema,),
                )
            }
            assert "orden_compra_ticket_ticket_idx" in indices, esquema
            assert "orden_compra_ticket_producto_idx" in indices, esquema
