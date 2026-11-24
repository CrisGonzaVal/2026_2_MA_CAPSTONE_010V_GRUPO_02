"""Configuracion de la conexion a PostgreSQL a partir del entorno.

Fija que `config.py` no inventa ninguna conexion, que la cadena completa
(`DB_URL`) tiene prioridad sobre los componentes `DB_*`, que el esquema
`postgres://` que entregan algunos proveedores se normaliza y que la contrasena
se escapa al componer la URL. `_env_file=None` desactiva los `.env` locales y
`DB_URL=""` el valor que fija `conftest` para la suite.
"""

import pytest
from sqlalchemy.engine import make_url

from app.core.config import Settings
from app.db import database


def test_sin_configuracion_no_inventa_una_conexion():
    configuracion = Settings(_env_file=None, DB_URL="")

    assert configuracion.DB_URL == ""
    assert (
        configuracion.DB_USER,
        configuracion.DB_PASSWORD,
        configuracion.DB_HOST,
        configuracion.DB_PORT,
        configuracion.DB_NAME,
    ) == ("", "", "", "", "")


def test_compone_la_url_cuando_estan_los_cuatro_componentes():
    configuracion = Settings(
        _env_file=None,
        DB_URL="",
        DB_USER="postgres",
        DB_PASSWORD="",
        DB_HOST="localhost",
        DB_PORT="5433",
        DB_NAME="apt_erp",
    )

    assert configuracion.DB_URL == (
        "postgresql+psycopg2://postgres:@localhost:5433/apt_erp"
    )


def test_no_compone_la_url_si_falta_un_componente():
    configuracion = Settings(
        _env_file=None,
        DB_URL="",
        DB_USER="postgres",
        DB_HOST="localhost",
        DB_NAME="apt_erp",
    )

    assert configuracion.DB_URL == ""


def test_la_url_completa_tiene_prioridad_sobre_los_componentes():
    configuracion = Settings(
        _env_file=None,
        DB_URL="postgresql://u:p@neon.example/neondb?sslmode=require",
        DB_HOST="ignorado",
        DB_NAME="ignorada",
    )

    assert configuracion.DB_URL == (
        "postgresql://u:p@neon.example/neondb?sslmode=require"
    )


def test_normaliza_el_esquema_postgres_que_entregan_los_proveedores():
    configuracion = Settings(_env_file=None, DB_URL="postgres://u:p@h:5432/db")

    assert configuracion.DB_URL == "postgresql+psycopg2://u:p@h:5432/db"


def test_recorta_espacios_y_conserva_el_esquema_postgresql():
    configuracion = Settings(_env_file=None, DB_URL="  postgresql://u:p@h/db  ")

    assert configuracion.DB_URL == "postgresql://u:p@h/db"


def test_escapa_los_caracteres_especiales_de_la_contrasena():
    configuracion = Settings(
        _env_file=None,
        DB_URL="",
        DB_USER="postgres",
        DB_PASSWORD="p@ss:word/1",
        DB_HOST="localhost",
        DB_PORT="5433",
        DB_NAME="apt_erp",
    )

    assert "p%40ss%3Aword%2F1" in configuracion.DB_URL
    assert make_url(configuracion.DB_URL).password == "p@ss:word/1"


def test_sin_url_el_motor_falla_con_un_mensaje_accionable(monkeypatch):
    monkeypatch.setattr(database.settings, "DB_URL", "")

    with pytest.raises(RuntimeError, match="DB_URL"):
        database.resolver_url_base_datos()
