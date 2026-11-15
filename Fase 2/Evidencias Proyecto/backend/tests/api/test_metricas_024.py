"""AC-11 a AC-16: metricas Prometheus, etiquetas y no autoinstrumentacion.

El registro es de proceso: ninguna prueba afirma valores absolutos; se compara
la presencia de la serie y el valor antes/despues de la peticion controlada.
"""

from fastapi.testclient import TestClient

from app.main import crear_app

from tests.soporte_observabilidad_024 import (
    leer_familias,
    leer_muestras,
    valor_de_serie,
)

FAMILIAS = {
    "compustock_http_requests_total",
    "compustock_http_request_duration_seconds",
    "compustock_http_requests_in_flight",
    "compustock_http_errors_total",
    "compustock_app_info",
}


def _exposicion(cliente) -> str:
    respuesta = cliente.get("/metrics")
    assert respuesta.status_code == 200
    assert respuesta.headers["content-type"].startswith("text/plain")
    assert "version=" in respuesta.headers["content-type"]
    return respuesta.text


def test_metrics_expone_las_cinco_familias(cliente):
    cliente.get("/ruta-inexistente-para-errores-024")
    texto = _exposicion(cliente)

    for familia in FAMILIAS:
        assert f"# HELP {familia}" in texto
    assert set(leer_familias(texto)) >= {
        "compustock_http_requests",
        "compustock_http_request_duration_seconds",
        "compustock_http_requests_in_flight",
        "compustock_http_errors",
        "compustock_app_info",
    }


def test_contador_y_histograma_usan_etiquetas_acotadas(cliente):
    cliente.get("/health")
    texto = _exposicion(cliente)

    contador = [
        muestra
        for muestra in leer_muestras(texto, "compustock_http_requests_total")
        if muestra.labels.get("route") == "/health"
        and muestra.labels.get("status") == "200"
    ]
    assert contador, "debe existir la serie de /health"
    assert set(contador[0].labels) == {"method", "route", "status"}
    assert contador[0].labels["method"] == "GET"

    histograma = [
        muestra
        for muestra in leer_muestras(
            texto, "compustock_http_request_duration_seconds_sum"
        )
        if muestra.labels.get("route") == "/health"
    ]
    assert histograma, "el histograma debe observar /health"
    assert set(histograma[0].labels) == {"method", "route"}

    cubetas = [
        muestra
        for muestra in leer_muestras(
            texto, "compustock_http_request_duration_seconds_bucket"
        )
        if muestra.labels.get("route") == "/health"
    ]
    assert len(cubetas) >= 2
    assert valor_de_serie(texto, "compustock_http_requests_in_flight") == 0


def test_ruta_con_identificador_se_agrega_como_plantilla(cliente, datos_base):
    respuesta = cliente.get("/api/v1/inventario/existencias/987654")
    texto = _exposicion(cliente)

    assert respuesta.status_code in (404, 422), respuesta.text
    assert (
        valor_de_serie(
            texto,
            "compustock_http_requests_total",
            method="GET",
            route="/api/v1/inventario/existencias/{producto_id}",
        )
        is not None
    )
    assert "987654" not in texto


def test_ruta_no_resuelta_se_agrega_bajo_unmatched(cliente):
    cliente.get("/api/v1/desconocido/987654")
    texto = _exposicion(cliente)

    assert (
        valor_de_serie(
            texto,
            "compustock_http_requests_total",
            route="unmatched",
            status="404",
        )
        is not None
    )
    assert "987654" not in texto


def test_exposicion_no_contiene_correo_token_usuario_ni_query(cliente, datos_base):
    cliente.get(
        "/api/v1/auth/me",
        params={"correo": "foo@example.com"},
        headers={"Authorization": "Bearer token-secreto"},
    )
    texto = _exposicion(cliente)

    assert "foo@example.com" not in texto
    assert "token-secreto" not in texto
    assert "correo" not in texto
    series = [
        muestra
        for muestra in leer_muestras(texto, "compustock_http_requests_total")
        if muestra.labels.get("route") == "/api/v1/auth/me"
    ]
    assert series
    assert set(series[0].labels) == {"method", "route", "status"}


def test_metrics_no_se_instrumenta_a_si_mismo(cliente):
    _exposicion(cliente)
    texto = _exposicion(cliente)

    assert (
        valor_de_serie(
            texto, "compustock_http_requests_total", route="/metrics"
        )
        is None
    )
    assert valor_de_serie(texto, "compustock_http_requests_in_flight") == 0


def test_metrics_no_exige_bearer():
    with TestClient(crear_app()) as cliente_sin_identidad:
        respuesta = cliente_sin_identidad.get("/metrics")

    assert respuesta.status_code == 200
    assert "compustock_app_info" in respuesta.text


def test_app_info_publica_version_y_esquema(cliente):
    texto = _exposicion(cliente)

    muestras = [
        muestra
        for muestra in leer_muestras(texto, "compustock_app_info")
        if muestra.labels.get("version") == "1.0.0"
        and muestra.labels.get("schema_version") == "021.1"
    ]
    assert muestras
    assert muestras[0].value == 1
