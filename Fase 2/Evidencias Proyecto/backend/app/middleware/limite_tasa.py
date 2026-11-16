"""Middleware ASGI del limite de tasa distribuido (Feature 025).

Se ejecuta solo sobre `/api/v1/*`, omite el preflight CORS y devuelve un 429
JSON con las cabeceras `X-RateLimit-*` cuando el limitador rechaza. Es ASGI puro
para no alterar cuerpos ajenos ni romper `TestClient`/`openapi()`.

La capa de observabilidad queda por fuera, de modo que el 429 tambien lleva
`X-Request-ID` y una linea de acceso; CORS queda por fuera del limitador, de
modo que el 429 conserva `Access-Control-Allow-Origin` cuando el origen esta
permitido.
"""

from fastapi import status
from fastapi.responses import JSONResponse

from app.core.limite_tasa import TEXTO_LIMITE, es_preflight, es_ruta_limitada


class MiddlewareLimiteTasa:
    """Decide el limite antes de que la peticion alcance las rutas."""

    def __init__(self, app, limitador):
        self.app = app
        self.limitador = limitador

    async def __call__(self, scope, receive, send):
        if (
            scope.get("type") != "http"
            or not es_ruta_limitada(scope.get("path", ""))
            or es_preflight(scope)
        ):
            await self.app(scope, receive, send)
            return

        resultado = await self.limitador.evaluar(scope)
        if resultado.permitida:
            await self.app(scope, receive, send)
            return

        # Marca que la observabilidad traduce a `route="rate_limited"`; el
        # enrutado nunca llega a ejecutarse en un 429.
        scope.setdefault("state", {})["rate_limited"] = True
        respuesta = JSONResponse(
            {"detail": TEXTO_LIMITE},
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            headers={
                "Retry-After": str(resultado.reinicio_segundos),
                "X-RateLimit-Limit": str(self.limitador.maximo),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(resultado.reinicio_segundos),
            },
        )
        await respuesta(scope, receive, send)
