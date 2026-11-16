"""AC-14: configuracion por entorno del limite de tasa distribuido.

Fija los defaults de D-8, el rechazo de valores no positivos, la validacion de
`REDIS_URL` solo con el limitador encendido y la lectura booleana de
`LIMITE_TASA_HABILITADO`. Cada prueba limpia las cinco variables para que un
shell de verificacion no altere los defaults.
"""

import pytest
from pydantic import ValidationError

from app.core.config import Settings

VARIABLES = [
    "REDIS_URL",
    "LIMITE_TASA_HABILITADO",
    "LIMITE_TASA_MAX_PETICIONES",
    "LIMITE_TASA_VENTANA_SEGUNDOS",
    "LIMITE_TASA_CONFIAR_PROXY",
]


@pytest.fixture
def entorno_limpio(monkeypatch):
    for variable in VARIABLES:
        monkeypatch.delenv(variable, raising=False)
    return monkeypatch


def test_defaults_del_limite_de_tasa(entorno_limpio):
    configuracion = Settings()

    assert configuracion.REDIS_URL == "redis://127.0.0.1:6380/0"
    assert configuracion.LIMITE_TASA_HABILITADO is True
    assert configuracion.LIMITE_TASA_MAX_PETICIONES == 120
    assert configuracion.LIMITE_TASA_VENTANA_SEGUNDOS == 60
    assert configuracion.LIMITE_TASA_CONFIAR_PROXY is False


@pytest.mark.parametrize(
    ("variable", "valor"),
    [
        ("LIMITE_TASA_MAX_PETICIONES", "0"),
        ("LIMITE_TASA_MAX_PETICIONES", "-1"),
        ("LIMITE_TASA_VENTANA_SEGUNDOS", "0"),
        ("LIMITE_TASA_VENTANA_SEGUNDOS", "-30"),
    ],
)
def test_valores_no_positivos_impiden_construir(entorno_limpio, variable, valor):
    with pytest.raises(ValidationError) as error:
        Settings(**{variable: valor})

    assert variable in str(error.value)


@pytest.mark.parametrize("url", ["http://x", "localhost:6380", "redis:/x"])
def test_url_no_redis_impiden_construir_con_el_limitador_encendido(
    entorno_limpio, url
):
    with pytest.raises(ValidationError) as error:
        Settings(REDIS_URL=url, LIMITE_TASA_HABILITADO="true")

    assert "REDIS_URL" in str(error.value)


def test_url_no_redis_se_acepta_con_el_limitador_apagado(entorno_limpio):
    configuracion = Settings(
        REDIS_URL="http://x", LIMITE_TASA_HABILITADO="false"
    )

    assert configuracion.REDIS_URL == "http://x"
    assert configuracion.LIMITE_TASA_HABILITADO is False


def test_url_rediss_se_acepta_con_el_limitador_encendido(entorno_limpio):
    configuracion = Settings(REDIS_URL="rediss://redis.example:6379/0")

    assert configuracion.REDIS_URL == "rediss://redis.example:6379/0"


def test_habilitado_lee_valores_booleanos_de_texto(entorno_limpio):
    assert Settings(LIMITE_TASA_HABILITADO="false").LIMITE_TASA_HABILITADO is False
    assert Settings(LIMITE_TASA_HABILITADO="true").LIMITE_TASA_HABILITADO is True
