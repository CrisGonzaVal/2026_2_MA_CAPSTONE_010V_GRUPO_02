"""AC-17 y AC-18: CORS por entorno, sin comodines y con preflight exacto."""

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import CABECERAS_CORS, METODOS_CORS, crear_app

METODOS_ESPERADOS = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
CABECERAS_ESPERADAS = "Authorization, Content-Type, Accept"


@pytest.mark.parametrize(
    "origen",
    ["http://localhost:4200", "http://localhost:8080"],
)
def test_default_permite_los_dos_origenes_locales(origen):
    with TestClient(crear_app()) as cliente:
        respuesta = cliente.get("/health", headers={"Origin": origen})

    assert respuesta.status_code == 200
    assert respuesta.headers["access-control-allow-origin"] == origen
    assert respuesta.headers["access-control-allow-credentials"] == "true"


def test_origen_ajeno_no_recibe_cabecera_de_permiso():
    with TestClient(crear_app()) as cliente:
        respuesta = cliente.get(
            "/health", headers={"Origin": "http://evil.example"}
        )

    assert respuesta.status_code == 200
    assert "access-control-allow-origin" not in respuesta.headers


def test_origenes_se_leen_del_entorno(monkeypatch):
    monkeypatch.setattr(settings, "ALLOWED_ORIGINS", "http://otro.example")

    with TestClient(crear_app()) as cliente:
        permitido = cliente.get(
            "/health", headers={"Origin": "http://otro.example"}
        )
        anterior = cliente.get(
            "/health", headers={"Origin": "http://localhost:4200"}
        )

    assert permitido.headers["access-control-allow-origin"] == "http://otro.example"
    assert "access-control-allow-origin" not in anterior.headers


def test_lista_vacia_impide_construir_la_aplicacion(monkeypatch):
    monkeypatch.setattr(settings, "ALLOWED_ORIGINS", " , ")

    with pytest.raises(ValueError) as error:
        crear_app()

    assert "ALLOWED_ORIGINS" in str(error.value)


def test_preflight_devuelve_metodos_y_cabeceras_exactos():
    with TestClient(crear_app()) as cliente:
        respuesta = cliente.options(
            "/api/v1/auth/me",
            headers={
                "Origin": "http://localhost:4200",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )

    assert respuesta.status_code == 200
    assert respuesta.headers["access-control-allow-origin"] == "http://localhost:4200"
    assert respuesta.headers["access-control-allow-methods"] == METODOS_ESPERADOS
    assert respuesta.headers["access-control-allow-headers"] == CABECERAS_ESPERADAS
    assert respuesta.headers["access-control-allow-credentials"] == "true"


def test_preflight_de_origen_ajeno_no_emite_permiso():
    with TestClient(crear_app()) as cliente:
        respuesta = cliente.options(
            "/api/v1/auth/me",
            headers={
                "Origin": "http://evil.example",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert respuesta.status_code == 400
    assert "access-control-allow-origin" not in respuesta.headers


def test_ninguna_cabecera_cors_vale_comodin():
    with TestClient(crear_app()) as cliente:
        respuesta = cliente.options(
            "/api/v1/auth/me",
            headers={
                "Origin": "http://localhost:4200",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization",
            },
        )

    cors = {
        nombre: valor
        for nombre, valor in respuesta.headers.items()
        if nombre.lower().startswith("access-control")
    }
    assert cors
    for nombre, valor in cors.items():
        assert "*" not in valor, f"{nombre} no puede declarar ni reflejar comodin"

    assert set(METODOS_CORS) == {
        "GET",
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
        "OPTIONS",
    }
    assert CABECERAS_CORS == ["Authorization", "Content-Type", "Accept"]
