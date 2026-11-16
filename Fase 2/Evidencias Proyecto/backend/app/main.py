"""Punto de entrada de la API de CompuStock ERP.

La aplicacion se construye con `crear_app()` para que los tests puedan crear
instancias aisladas cuando necesitan cambiar configuracion por entorno. El
objeto `app` sigue siendo el singleton que consumen uvicorn y la suite.

Feature 024: el middleware de observabilidad es la capa mas externa (se agrega
despues de CORS), de modo que toda respuesta —incluido el preflight— lleva
`X-Request-ID` y una linea de acceso correlacionada.
"""

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse

from app.api.operativo import router_operativo
from app.api.v1.api import api_router
from app.core.config import VERSION_APLICACION, settings
from app.core.cors import CORSEstricto
from app.core.limite_tasa import AlmacenRedis, LimitadorTasa
from app.core.observabilidad import configurar_registro
from app.middleware.limite_tasa import MiddlewareLimiteTasa
from app.middleware.observabilidad import MiddlewareObservabilidad

#: Metodos y cabeceras realmente expuestos (D-6). No incluye `*`: la API no
#: usa `HEAD` ni `TRACE` y no necesita anunciarlos.
METODOS_CORS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
CABECERAS_CORS = ["Authorization", "Content-Type", "Accept"]


def manejador_error_no_controlado(
    request: Request, exc: Exception
) -> PlainTextResponse:
    """Conserva el 500 de Starlette y lo correlaciona con su peticion.

    El `ContextVar` ya se reseteo, pero `scope["state"]` sigue disponible para
    `ServerErrorMiddleware`, que es quien invoca este manejador. No se registra
    el traceback ni el mensaje de la excepcion.
    """
    identificador = request.scope.get("state", {}).get("request_id")
    cabeceras = {"X-Request-ID": identificador} if identificador else None
    return PlainTextResponse(
        "Internal Server Error", status_code=500, headers=cabeceras
    )


def crear_app(cliente_limite=None) -> FastAPI:
    """Construye la aplicacion FastAPI completa.

    `cliente_limite` es la costura de pruebas: recibe un `AlmacenLimite` y
    permite construir dos apps que comparten el mismo estado sin Redis.
    """
    configurar_registro()
    aplicacion = FastAPI(
        title="CompuStock ERP API",
        description="API REST para la gestión centralizada de insumos de ofimática (SaaS Multi-tenant)",
        version=VERSION_APLICACION,
    )

    # Feature 025: el limitador se agrega antes que CORS y observabilidad para
    # que estas dos capas lo envuelvan (Starlette envuelve con el ultimo
    # middleware agregado). El preflight lo corta CORS antes de llegar aqui.
    if settings.LIMITE_TASA_HABILITADO:
        almacen = (
            AlmacenRedis(settings.REDIS_URL)
            if cliente_limite is None
            else cliente_limite
        )
        limitador = LimitadorTasa(
            almacen=almacen,
            maximo=settings.LIMITE_TASA_MAX_PETICIONES,
            ventana_segundos=settings.LIMITE_TASA_VENTANA_SEGUNDOS,
            confiar_proxy=settings.LIMITE_TASA_CONFIAR_PROXY,
        )
        aplicacion.add_middleware(MiddlewareLimiteTasa, limitador=limitador)
        # FastAPI 0.142 ya no expone `add_event_handler` en la app; el router
        # conserva el registro y cierra el cliente Redis al apagar el proceso.
        aplicacion.router.add_event_handler("shutdown", almacen.cerrar)

    #: Feature 024 (D-6): CORS por entorno, sin comodines. La guarda cubre una
    #: instancia mutada en pruebas o un futuro cargador; el fail-fast de la
    #: variable vacia ya ocurre al construir `Settings`.
    origenes = settings.origenes_permitidos
    if not origenes:
        raise ValueError(
            "ALLOWED_ORIGINS no puede quedar vacio: declare al menos un "
            "origen explicito separado por comas."
        )
    aplicacion.add_middleware(
        CORSEstricto,
        allow_origins=origenes,
        allow_credentials=True,
        allow_methods=METODOS_CORS,
        cabeceras_permitidas=CABECERAS_CORS,
    )
    aplicacion.add_middleware(MiddlewareObservabilidad)
    aplicacion.add_exception_handler(Exception, manejador_error_no_controlado)

    aplicacion.include_router(api_router, prefix="/api/v1")
    aplicacion.include_router(router_operativo)

    @aplicacion.get("/", summary="Raiz de la API")
    def leer_raiz():
        return {
            "message": "Bienvenido a la API de CompuStock ERP",
            "status": "online",
            "docs_url": "/docs",
        }

    @aplicacion.get("/health", summary="Estado de salud del servicio")
    def verificar_salud():
        return {"status": "healthy"}

    return aplicacion


app = crear_app()
