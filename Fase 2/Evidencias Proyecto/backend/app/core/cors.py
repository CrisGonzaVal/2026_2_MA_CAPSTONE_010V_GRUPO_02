"""CORS estricto por entorno (Feature 024, R-5).

`CORSMiddleware` de Starlette agrega automaticamente a
`Access-Control-Allow-Headers` las cabeceras *safelisted* (`Accept-Language`,
`Content-Language`, etc.). La spec exige exactamente `Authorization,
Content-Type, Accept`, asi que esta subclase recorta la respuesta del preflight
a la lista declarada; la validacion de metodo y cabecera sigue siendo la de
Starlette. No se declara ni se refleja `*` en origenes, metodos ni cabeceras.
"""

from starlette.middleware.cors import CORSMiddleware
from starlette.responses import Response


class CORSEstricto(CORSMiddleware):
    """CORS con orígenes explícitos y cabeceras de permiso recortadas."""

    def __init__(self, app, *, cabeceras_permitidas, **kwargs):
        self._cabeceras_permitidas = list(cabeceras_permitidas)
        super().__init__(app, allow_headers=cabeceras_permitidas, **kwargs)

    def preflight_response(self, request_headers) -> Response:
        respuesta = super().preflight_response(request_headers)
        if respuesta.status_code == 200:
            respuesta.headers["Access-Control-Allow-Headers"] = ", ".join(
                self._cabeceras_permitidas
            )
        return respuesta
