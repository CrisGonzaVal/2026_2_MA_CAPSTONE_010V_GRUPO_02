"""Middleware de correlacion y acceso de la Feature 024.

Es ASGI puro (no `BaseHTTPMiddleware`) para no alterar el cuerpo ni el estado de
las respuestas y para que `TestClient(app)` y `app.openapi()` sigan funcionando
sobre el objeto FastAPI. Su unica responsabilidad en T4 es:

* resolver `X-Request-ID` (cabecera valida o UUID4 nuevo);
* fijarlo en `scope["state"]` y en el `ContextVar`, reseteandolo en `finally`;
* inyectarlo en toda respuesta, incluidas 4xx, 404, `/health`, `/ready`,
  `/metrics` y el preflight CORS;
* registrar una unica linea de acceso con metodo, plantilla de ruta, estado y
  duracion, sin query string, cabeceras, cuerpo ni PII.
"""

import logging
import time

from starlette.datastructures import MutableHeaders

from app.core.metricas import (
    RUTA_NO_RESUELTA,
    compustock_http_requests_in_flight,
    registrar_peticion,
)
from app.core.observabilidad import (
    IDENTIFICADOR_PETICION,
    LOGGER_ACCESO,
    nivel_de_estado,
    resolver_identificador,
)

_CABECERA_IDENTIFICADOR = b"x-request-id"
_CABECERA_RESPUESTA = "X-Request-ID"
_RUTAS_METRICAS = ("/metrics", "/metrics/")


def _leer_cabecera(scope: dict) -> str | None:
    for nombre, valor in scope.get("headers", []):
        if nombre.lower() == _CABECERA_IDENTIFICADOR:
            return valor.decode("latin-1")
    return None


def _ruta_plantilla(scope: dict) -> str:
    """Plantilla completa de la ruta, sin identificadores reales.

    FastAPI 0.142 anida los routers incluidos: `scope["route"].path` queda
    relativo al router (`/existencias/{producto_id}`) y no incluye el prefijo
    `/api/v1`. Se recupera el prefijo probando los sufijos del path real que
    encajan con la regex de la ruta, de modo que nunca se registra el path
    crudo ni una serie por identificador.
    """
    ruta = scope.get("route")
    plantilla = getattr(ruta, "path", None)
    if not plantilla:
        return RUTA_NO_RESUELTA

    camino = scope.get("path") or ""
    if camino == plantilla or not camino:
        return plantilla

    regex = getattr(ruta, "path_regex", None)
    if regex is not None:
        # Los limites de segmento acotan la busqueda; no se prueba caracter a
        # caracter. El primer sufijo que encaja es el que corresponde al router.
        for indice in range(len(camino) + 1):
            if camino[indice:].startswith("/") and regex.fullmatch(
                camino[indice:]
            ):
                return camino[:indice] + plantilla
    return plantilla


class MiddlewareObservabilidad:
    """Correlaciona cada peticion HTTP y emite su linea de acceso."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        identificador = resolver_identificador(_leer_cabecera(scope))
        scope.setdefault("state", {})["request_id"] = identificador
        token = IDENTIFICADOR_PETICION.set(identificador)
        estado = {"codigo": 500}
        es_metricas = scope.get("path") in _RUTAS_METRICAS
        inicio = time.perf_counter()
        if not es_metricas:
            compustock_http_requests_in_flight.inc()

        async def enviar(mensaje):
            if mensaje["type"] == "http.response.start":
                estado["codigo"] = mensaje["status"]
                MutableHeaders(scope=mensaje)[_CABECERA_RESPUESTA] = identificador
            await send(mensaje)

        try:
            await self.app(scope, receive, enviar)
        except Exception:
            estado["codigo"] = 500
            raise
        finally:
            duracion = time.perf_counter() - inicio
            ruta = _ruta_plantilla(scope)
            if not es_metricas:
                try:
                    compustock_http_requests_in_flight.dec()
                    registrar_peticion(
                        scope.get("method", ""),
                        ruta,
                        estado["codigo"],
                        duracion,
                    )
                except Exception:
                    # La instrumentacion es best-effort: nunca cambia el
                    # resultado de la peticion.
                    pass
            try:
                logging.getLogger(LOGGER_ACCESO).log(
                    nivel_de_estado(estado["codigo"]),
                    "peticion_completada",
                    extra={
                        "request_id": identificador,
                        "method": scope.get("method", ""),
                        "path": ruta,
                        "status": estado["codigo"],
                        "duration_ms": round(duracion * 1000, 3),
                    },
                )
            except Exception:
                # El logging es best-effort: nunca cambia el resultado de la
                # peticion ni enmascara la excepcion original.
                pass
            IDENTIFICADOR_PETICION.reset(token)
