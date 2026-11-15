"""Metricas Prometheus de la Feature 024 (R-4).

Se usa un `CollectorRegistry` propio, nunca el registro global, para que la
suite y cualquier import de terceros no interfieran. `route` es siempre la
plantilla de la ruta (o el valor reservado `unmatched`): ninguna etiqueta lleva
identificadores reales, correos, usuarios, instituciones ni tenants.
"""

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

from app.core.config import VERSION_APLICACION, VERSION_ESQUEMA_OBJETIVO

#: Valor fijo para peticiones sin ruta resuelta. Evita una serie por URL
#: escaneada y lo comparten el middleware y la exposicion.
RUTA_NO_RESUELTA = "unmatched"

TIPO_CONTENIDO = CONTENT_TYPE_LATEST

REGISTRO = CollectorRegistry(auto_describe=True)

compustock_http_requests_total = Counter(
    "compustock_http_requests_total",
    "Peticiones HTTP atendidas por metodo, plantilla de ruta y estado.",
    ["method", "route", "status"],
    registry=REGISTRO,
)

compustock_http_request_duration_seconds = Histogram(
    "compustock_http_request_duration_seconds",
    "Duracion de las peticiones HTTP en segundos por metodo y ruta.",
    ["method", "route"],
    registry=REGISTRO,
)

compustock_http_requests_in_flight = Gauge(
    "compustock_http_requests_in_flight",
    "Peticiones HTTP en curso.",
    registry=REGISTRO,
)

compustock_http_errors_total = Counter(
    "compustock_http_errors_total",
    "Respuestas HTTP con estado 4xx o 5xx.",
    ["status"],
    registry=REGISTRO,
)

compustock_app_info = Gauge(
    "compustock_app_info",
    "Version de la aplicacion y del esquema de datos.",
    ["version", "schema_version"],
    registry=REGISTRO,
)

compustock_app_info.labels(
    version=VERSION_APLICACION,
    schema_version=VERSION_ESQUEMA_OBJETIVO,
).set(1)


def registrar_peticion(
    method: str, route: str, status: int, duracion: float
) -> None:
    """Registra una peticion: contador, histograma y contador de errores."""
    compustock_http_requests_total.labels(
        method=method, route=route, status=str(status)
    ).inc()
    compustock_http_request_duration_seconds.labels(
        method=method, route=route
    ).observe(duracion)
    if status >= 400:
        compustock_http_errors_total.labels(status=str(status)).inc()


def generar_exposicion() -> str:
    """Exposicion en formato texto de Prometheus."""
    return generate_latest(REGISTRO).decode("utf-8")
