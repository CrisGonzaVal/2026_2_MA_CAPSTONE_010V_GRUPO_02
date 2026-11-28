"""AC-1 a AC-5 y AC-8 (health intacto): correlacion por `X-Request-ID`.

Las pruebas usan la interfaz HTTP real (`TestClient`) y, para el 500, una ruta
temporal fuera de OpenAPI que se retira en `finally` para no alterar el conteo
de 75 entradas del contrato (73 v1 + `GET /` + `/health`; la ampliacion
25/Nov/2026 de la 013 llevo el total a 77, la enmienda 27/Nov/2026 de la 012
retiro tres operaciones y la Feature 028 (T5) sumo el canal de tiempo real).
"""

import json
import re
import uuid

import pytest

from app.main import app

from tests.funcional.integracion.soporte_observabilidad_024 import capturar_logs

UUID_CANONICO = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
RUTA_500 = "/_prueba-500-024"


def _es_uuid_canonico(valor: str) -> bool:
    return bool(UUID_CANONICO.fullmatch(valor))


def _lineas_de_acceso(lineas: list[str]) -> list[dict]:
    registros = []
    for linea in lineas:
        try:
            registro = json.loads(linea)
        except json.JSONDecodeError:
            continue
        if registro.get("message") == "peticion_completada":
            registros.append(registro)
    return registros


@pytest.mark.parametrize("ruta", ["/", "/health"])
def test_rutas_publicas_llevan_uuid_canonico(cliente, ruta):
    respuesta = cliente.get(ruta)

    assert respuesta.status_code == 200
    assert _es_uuid_canonico(respuesta.headers["x-request-id"])


def test_operacion_autenticada_lleva_uuid_canonico(cliente, datos_base):
    respuesta = cliente.get("/api/v1/auth/me")

    assert respuesta.status_code == 200, respuesta.text
    assert _es_uuid_canonico(respuesta.headers["x-request-id"])


def test_404_lleva_uuid_canonico(cliente):
    respuesta = cliente.get("/api/v1/ruta-inexistente-024")

    assert respuesta.status_code == 404
    assert _es_uuid_canonico(respuesta.headers["x-request-id"])


def test_422_lleva_uuid_canonico(cliente):
    respuesta = cliente.get("/api/v1/inventario/existencias/no-es-entero")

    assert respuesta.status_code == 422
    assert _es_uuid_canonico(respuesta.headers["x-request-id"])


def test_preflight_lleva_uuid_canonico(cliente):
    respuesta = cliente.options(
        "/api/v1/auth/me",
        headers={
            "Origin": "http://localhost:4200",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert respuesta.status_code == 200
    assert _es_uuid_canonico(respuesta.headers["x-request-id"])
    assert respuesta.headers["access-control-allow-origin"] == "http://localhost:4200"


def test_uuid_entrante_valido_se_devuelve_identico(cliente):
    identificador = "3F1C2A9E-8B7D-4C6E-9F01-2A3B4C5D6E7F"

    respuesta = cliente.get("/health", headers={"X-Request-ID": identificador})

    assert respuesta.headers["x-request-id"] == identificador


@pytest.mark.parametrize(
    "cabecera",
    ["abc", "", "3f1c2a9e8b7d4c6e9f012a3b4c5d6e7f", "{3f1c2a9e-8b7d-4c6e-9f01-2a3b4c5d6e7f}"],
)
def test_uuid_entrante_invalido_se_reemplaza(cliente, cabecera):
    respuesta = cliente.get("/health", headers={"X-Request-ID": cabecera})

    devuelto = respuesta.headers["x-request-id"]
    assert devuelto != cabecera
    assert _es_uuid_canonico(devuelto)


def test_sin_cabecera_entrante_se_genera_uuid(cliente):
    respuesta = cliente.get("/health")

    assert _es_uuid_canonico(respuesta.headers["x-request-id"])


def test_dos_peticiones_consecutivas_no_comparten_identificador(cliente):
    with capturar_logs() as lineas:
        primera = cliente.get("/health")
        segunda = cliente.get("/health")

    identificadores = {
        primera.headers["x-request-id"],
        segunda.headers["x-request-id"],
    }
    assert len(identificadores) == 2

    registradas = _lineas_de_acceso(lineas)
    assert len([r for r in registradas if r["path"] == "/health"]) == 2
    assert {
        r["request_id"] for r in registradas if r["path"] == "/health"
    } == identificadores


def test_el_log_de_acceso_no_contiene_token_correo_ni_query(cliente):
    with capturar_logs() as lineas:
        respuesta = cliente.post(
            "/api/v1/tickets/",
            params={"correo": "foo@example.com"},
            headers={"Authorization": "Bearer token-secreto"},
            json={"correo": "foo@example.com", "token": "token-secreto"},
        )

    # Enmienda 26/Nov/2026 de la Feature 007 (D-11/AC-33): el cliente legacy
    # (Administrador) ya no puede crear tickets. Con un cuerpo JSON parseable,
    # el 403 de matriz se resuelve antes de validar el contrato. Las aserciones
    # del log y de la redaccion de secretos se conservan sin cambios.
    assert respuesta.status_code == 403, respuesta.text

    registradas = _lineas_de_acceso(lineas)
    assert registradas, "debe existir una linea de acceso"
    texto = "\n".join(lineas)
    assert "token-secreto" not in texto
    assert "foo@example.com" not in texto
    assert "correo=" not in texto
    for registro in registradas:
        assert "?" not in registro["path"]
        assert "correo" not in registro
    linea_tickets = [
        registro
        for registro in registradas
        if registro["path"] == "/api/v1/tickets/"
    ]
    assert linea_tickets, "la ruta resuelta debe ser la plantilla"
    assert linea_tickets[0]["request_id"] == respuesta.headers["x-request-id"]


def test_error_500_conserva_cuerpo_y_lleva_identificador(cliente_sin_excepcion):
    async def fallar():
        raise RuntimeError("fallo inyectado de la prueba 024")

    app.add_api_route(RUTA_500, fallar, include_in_schema=False)
    identificador = str(uuid.uuid4())
    try:
        with capturar_logs() as lineas:
            respuesta = cliente_sin_excepcion.get(
                RUTA_500, headers={"X-Request-ID": identificador}
            )
    finally:
        app.router.routes = [
            ruta
            for ruta in app.router.routes
            if getattr(ruta, "path", None) != RUTA_500
        ]

    assert respuesta.status_code == 500
    assert respuesta.text == "Internal Server Error"
    assert respuesta.headers["content-type"].startswith("text/plain")
    assert respuesta.headers["x-request-id"] == identificador

    registrada = [
        json.loads(linea)
        for linea in lineas
        if json.loads(linea).get("message") == "peticion_completada"
    ][-1]
    assert registrada["status"] == 500
    assert registrada["request_id"] == identificador
    assert registrada["path"] == RUTA_500


def test_health_conserva_su_contrato(cliente):
    respuesta = cliente.get("/health")

    assert respuesta.status_code == 200
    assert respuesta.json() == {"status": "healthy"}
