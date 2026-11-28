"""Seguridad y gobierno del canal SSE de la Feature 028 (T5).

Fija la fila de la matriz (`GET /api/v1/eventos/` para los tres roles
institucionales), el 401 sin credencial, que la credencial solo cuenta en
`Authorization` (URL y cookie no autentican), el 403 del Superadmin por matriz,
el 503 del interruptor sin abrir el flujo ni suscribirse, la publicacion en
`/openapi.json` (media type, respuestas y excepcion de `response_model`), los
conteos absolutos de la 028 (matriz **73**, contrato **75/73**) y que ningun
parametro de ambito del cliente amplia el contexto de la conexion.

`TestClient` bufferiza el `StreamingResponse` (nota de T0): el unico caso que
abre un flujo usa vida maxima y latido de 1 s y lee el cuerpo completo.
"""

import json

import pytest
from fastapi.testclient import TestClient

from app.core import permisos
from app.core.config import settings
from app.main import app

from tests.funcional.integracion._soporte_eventos_028 import instalar_bus

RUTA = "/api/v1/eventos/"
CLAVE = ("GET", RUTA)
METODOS = {"get", "post", "put", "patch", "delete", "options", "head", "trace"}


@pytest.fixture(autouse=True)
def flujo_acotado(monkeypatch):
    """Un flujo abierto en este modulo nunca espera mas de 1 s."""
    monkeypatch.setattr(settings, "VIDA_MAXIMA_CONEXION_SEGUNDOS", 1)
    monkeypatch.setattr(settings, "TIEMPO_REAL_LATIDO_SEGUNDOS", 1)


def _operaciones(esquema: dict):
    for ruta, metodos in esquema["paths"].items():
        for metodo in metodos:
            if metodo.lower() in METODOS:
                yield ruta, metodo.lower()


def _dominios_del_listo(cuerpo: str) -> list[str]:
    for linea in cuerpo.splitlines():
        if linea.startswith("data: "):
            return json.loads(linea[len("data: ") :])["dominios"]
    raise AssertionError(f"el flujo no emitio un frame con datos: {cuerpo!r}")


# ---------------------------------------------------------------------------
# Matriz central
# ---------------------------------------------------------------------------


def test_la_matriz_declara_el_canal_para_los_tres_roles_institucionales():
    """AC-2/AC-24: una fila nueva, solo roles institucionales; matriz 73."""
    assert CLAVE in permisos.MATRIZ_PERMISOS
    assert permisos.MATRIZ_PERMISOS[CLAVE] == frozenset(
        {"Administrador", "Bodeguero", "Solicitante"}
    )
    assert "Superadmin" not in permisos.MATRIZ_PERMISOS[CLAVE]
    assert len(permisos.MATRIZ_PERMISOS) == 73


# ---------------------------------------------------------------------------
# Denegacion previa al flujo
# ---------------------------------------------------------------------------


def test_sin_authorization_responde_401():
    """AC-2: sin Bearer no se autentica; no se abre ningun flujo."""
    with TestClient(app) as cliente:
        respuesta = cliente.get(RUTA)

    assert respuesta.status_code == 401
    assert "detail" in respuesta.json()
    assert respuesta.headers["content-type"].startswith("application/json")


def test_token_en_url_o_cookie_no_autentica():
    """AC-2: solo `Authorization` cuenta; URL y cookie responden 401 como sin credencial."""
    token = "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ0ZXN0LTAyOCJ9.firma-de-prueba"

    # Sin el override de identidad de `cliente`: se ejercita el HTTPBearer real.
    with TestClient(app) as cliente_sin_identidad:
        por_url = cliente_sin_identidad.get(RUTA, params={"token": token})
        por_cookie = cliente_sin_identidad.get(
            RUTA, headers={"Cookie": f"access_token={token}"}
        )
        sin_credencial = cliente_sin_identidad.get(RUTA)

    for respuesta in (por_url, por_cookie):
        assert respuesta.status_code == 401
        assert respuesta.headers["content-type"].startswith("application/json")
        assert respuesta.json() == sin_credencial.json()


def test_superadmin_recibe_403_por_matriz_sin_suscribirse(cliente, actuar_como):
    """AC-2/AC-17: el Superadmin queda fuera del canal; no toca el bus."""
    actuar_como("Superadmin")

    with instalar_bus() as bus:
        respuesta = cliente.get(RUTA)

    assert respuesta.status_code == 403
    assert "detail" in respuesta.json()
    assert bus.suscripciones == []


def test_canal_apagado_responde_503_sin_abrir_el_flujo(cliente, datos_base):
    """AC-32: el interruptor responde 503 con `detail` y no se suscribe."""
    with instalar_bus(habilitado=False) as bus:
        respuesta = cliente.get(RUTA)

    assert respuesta.status_code == 503
    assert "detail" in respuesta.json()
    assert bus.suscripciones == []


# ---------------------------------------------------------------------------
# OpenAPI y conteos
# ---------------------------------------------------------------------------


def test_openapi_publica_la_operacion_sin_response_model_y_con_sus_respuestas(
    cliente,
):
    """AC-24: media type de flujo, 200/401/403/429/503 y frames descritos."""
    esquema = cliente.get("/openapi.json").json()
    operacion = esquema["paths"][RUTA]["get"]

    assert {"200", "401", "403", "429", "503"} <= set(operacion["responses"])
    contenido = operacion["responses"]["200"]["content"]
    assert "text/event-stream" in contenido
    assert "application/json" not in contenido
    assert (
        contenido["text/event-stream"]["schema"]["type"] == "string"
    )
    assert "response_model" in operacion["description"]
    for frame in ("listo", "cambio", "estado", "latido"):
        assert frame in operacion["description"], frame


def test_openapi_y_matriz_suman_una_operacion(cliente):
    """AC-24: matriz 72 -> 73; `/openapi.json` 74 -> 75 (73 v1 + dos tecnicas)."""
    esquema = cliente.get("/openapi.json").json()
    operaciones = list(_operaciones(esquema))

    assert len(operaciones) == 75
    v1 = [ruta for ruta, _ in operaciones if ruta.startswith("/api/v1")]
    assert len(v1) == 73
    assert sorted(
        ruta for ruta, _ in operaciones if not ruta.startswith("/api/v1")
    ) == ["/", "/health"]
    assert len(permisos.MATRIZ_PERMISOS) == 73


# ---------------------------------------------------------------------------
# Ambito
# ---------------------------------------------------------------------------


def test_los_parametros_de_ambito_no_amplian_el_contexto(
    cliente, datos_base, actuar_como
):
    """AC-15/§6.1: `?institucion_id`, `?sede_id`, `?usuario_id` y `?dominios` se ignoran."""
    actuar_como("Solicitante")

    consulta = (
        "?institucion_id=INST02&sede_id=99&usuario_id=99"
        "&dominios=compras,pedidos"
    )
    with instalar_bus() as bus:
        with cliente.stream("GET", f"{RUTA}{consulta}") as respuesta:
            cuerpo = respuesta.read().decode("utf-8")

    assert respuesta.status_code == 200
    assert _dominios_del_listo(cuerpo) == ["pedidos", "inventario", "dashboard"]
    assert "compras" not in _dominios_del_listo(cuerpo)
    assert bus.canales == ["compustock:eventos:INST01"]
