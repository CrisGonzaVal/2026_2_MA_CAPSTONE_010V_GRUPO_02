"""Feature 027, T11: validacion real sobre PostgreSQL 16 (gated).

Requiere `POSTGRES_TEST_URL` y crea una base temporal desechable; nunca toca
`apt_erp`. Verifica el truncamiento real de `VARCHAR`, los `CHECK` y la red de
seguridad de `IntegrityError`/`DataError`, ademas de que la instalacion limpia
conserva la version y los conteos de la Feature 026.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import pytest

try:
    import psycopg2

    _PSYCOPG2_DISPONIBLE = True
except ImportError:  # pragma: no cover - entorno sin psycopg2
    _PSYCOPG2_DISPONIBLE = False

from fastapi import Request
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.pool import NullPool

from app.core.config import VERSION_ESQUEMA_OBJETIVO
from app.core.errores_bd import clasificar_error_bd, manejador_error_bd
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

RAIZ = Path(__file__).resolve().parents[4]
ESQUEMA_SQL = RAIZ / "database" / "01_esquema.sql"
SEMILLA_SQL = RAIZ / "database" / "02_datos_semilla.sql"


def _sin_driver(url: str) -> str:
    return url.replace("postgresql+psycopg2://", "postgresql://")


def _url_con_base(url: str, nombre: str) -> str:
    partes = urlsplit(url)
    return urlunsplit((partes.scheme, partes.netloc, "/" + nombre, "", ""))


@contextmanager
def _base_temporal():
    dsn = _sin_driver(_POSTGRES_TEST_URL or "")
    admin = psycopg2.connect(dsn)
    admin.autocommit = True
    nombre = f"compustock_027_{uuid4().hex[:12]}"
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


@contextmanager
def _base_instalada():
    with _base_temporal() as conexion:
        with conexion.cursor() as cur:
            cur.execute(ESQUEMA_SQL.read_text(encoding="utf-8"))
            cur.execute(SEMILLA_SQL.read_text(encoding="utf-8"))
        conexion.commit()
        nombre_base = conexion.get_dsn_parameters()["dbname"]
        url = _url_con_base(_sin_driver(_POSTGRES_TEST_URL or ""), nombre_base)
        motor = create_engine(
            url.replace("postgresql://", "postgresql+psycopg2://", 1),
            poolclass=NullPool,
            future=True,
        )
        try:
            yield conexion, motor
        finally:
            motor.dispose()


def _esquema_inst_001() -> str:
    return nombre_esquema_para_institucion("INST-001")


def _catalogo_semilla(conexion) -> tuple[str, int]:
    esquema = _esquema_inst_001()
    with conexion.cursor() as cur:
        cur.execute(
            f'SELECT institucion_id, min(categoria_id) FROM "{esquema}".categoria '
            "GROUP BY institucion_id"
        )
        return cur.fetchone()


def _request(request_id: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/_prueba-error-bd-027",
            "headers": [],
            "state": {"request_id": request_id},
        }
    )


def test_instalacion_limpia_conserva_version_y_conteos():
    with _base_temporal() as conexion:
        with conexion.cursor() as cur:
            cur.execute(ESQUEMA_SQL.read_text(encoding="utf-8"))
            cur.execute(SEMILLA_SQL.read_text(encoding="utf-8"))
        conexion.commit()

        def tablas(esquema: str) -> int:
            with conexion.cursor() as cur:
                cur.execute(
                    "SELECT count(*) FROM information_schema.tables "
                    "WHERE table_schema = %s AND table_type = 'BASE TABLE'",
                    (esquema,),
                )
                return cur.fetchone()[0]

        assert tablas("control") == 25
        for institucion_id in ("INST-001", "INST-002", "INST-003", "INST-004"):
            assert tablas(nombre_esquema_para_institucion(institucion_id)) == 22

        for esquema in ("control", _esquema_inst_001()):
            with conexion.cursor() as cur:
                cur.execute(f'SELECT version FROM "{esquema}".version_esquema')
                assert cur.fetchone()[0] == VERSION_ESQUEMA_OBJETIVO == "026.1"


def test_varchar_150_acepta_y_151_lanza_data_error_traducido():
    with _base_instalada() as (conexion, motor):
        institucion_id, categoria_id = _catalogo_semilla(conexion)
        esquema = _esquema_inst_001()
        sentencia = text(
            f'INSERT INTO "{esquema}".producto '
            "(nombre, categoria_id, institucion_id) "
            "VALUES (:nombre, :categoria_id, :institucion_id) RETURNING producto_id"
        )

        with motor.begin() as conn:
            conn.execute(
                sentencia,
                {
                    "nombre": "a" * 150,
                    "categoria_id": categoria_id,
                    "institucion_id": institucion_id,
                },
            )

        with pytest.raises(DataError) as capturado:
            with motor.begin() as conn:
                conn.execute(
                    sentencia,
                    {
                        "nombre": "a" * 151,
                        "categoria_id": categoria_id,
                        "institucion_id": institucion_id,
                    },
                )

        assert clasificar_error_bd(capturado.value) == (
            422,
            "Uno de los textos supera la longitud permitida.",
        )
        respuesta = manejador_error_bd(
            _request("8a3f8a0e-0270-4a5c-9f6e-0123456789ab"),
            capturado.value,
        )
        assert respuesta.status_code == 422
        assert respuesta.headers["x-request-id"] == "8a3f8a0e-0270-4a5c-9f6e-0123456789ab"
        assert respuesta.body.decode() == (
            '{"detail":"Uno de los textos supera la longitud permitida."}'
        )


def test_check_de_stock_minimo_se_traduce_a_422():
    with _base_instalada() as (conexion, motor):
        institucion_id, categoria_id = _catalogo_semilla(conexion)
        esquema = _esquema_inst_001()

        with pytest.raises(IntegrityError) as capturado:
            with motor.begin() as conn:
                conn.execute(
                    text(
                        f'INSERT INTO "{esquema}".producto '
                        "(nombre, categoria_id, institucion_id, stock_minimo) "
                        "VALUES ('Producto invalido', :categoria_id, "
                        ":institucion_id, -1)"
                    ),
                    {
                        "categoria_id": categoria_id,
                        "institucion_id": institucion_id,
                    },
                )

        assert clasificar_error_bd(capturado.value) == (
            422,
            "Alguno de los valores enviados no cumple las reglas del recurso.",
        )


def test_unicidad_real_de_proveedor_se_traduce_a_409():
    with _base_instalada() as (_conexion, motor):
        with pytest.raises(IntegrityError) as capturado:
            with motor.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO control.proveedor (rut, razon_social) "
                        "VALUES ('765432103', 'Duplicado normalizado')"
                    )
                )

        assert clasificar_error_bd(capturado.value) == (
            409,
            "El valor ya existe o entra en conflicto con un registro existente.",
        )
