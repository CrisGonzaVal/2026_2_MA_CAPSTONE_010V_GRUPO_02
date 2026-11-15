# Plan de implementación — Feature 024: Hardening operativo I

**Feature:** `024-hardening-operativo/`
**Spec:** [spec.md](spec.md)
**Enfoque:** trece tareas secuenciales; cada una deja la suite en verde y no toca el contrato de negocio.
**Regla:** no se reabre ninguna feature anterior. El único cambio bajo `frontend/src/**` es
`shared/config/url-api.ts`; todo lo demás es backend, borde, dependencias o documentación.

## 1. Orden de ejecución

```text
T1 línea base + pineo de dependencias
  → T2 configuración por entorno
  → T3 logging estructurado
  → T4 app factory + X-Request-ID + manejador 500
  → T5 CORS estricto por entorno
  → T6 /health + /ready
  → T7 métricas + /metrics
  → T8 B8: URL relativa + proxy de desarrollo
  → T9 borde nginx + arranque sin access log
  → T10 verificación backend, contrato y áreas protegidas
  → T11 recorrido 4200
  → T12 rebuild, humo y borde 8080
  → T13 cierre documental, evidencia y commit
```

T2–T7 son backend y se pueden probar con `pytest` sin Docker. T8–T9 son cambios de
frontend/borde que solo se validan de verdad en T11–T12. T10 es la puerta de contrato antes de
tocar los puertos; T13 no cierra nada que T10–T12 no hayan verificado.

## 2. Línea base y dependencias (T1)

### 2.1 Línea base

```powershell
cd backend
.venv/Scripts/python.exe -m pytest -q
cd ..\frontend
$env:CHROME_BIN = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
npx ng test --watch=false --browsers=ChromeHeadless
```

Esperado: **1502 passed / 88 skipped / 0 failed** y **549 SUCCESS**. Se registran en
`evidencia/README.md` antes de tocar código.

### 2.2 Versiones instaladas

Verificar con `pip show` las nueve dependencias directas. Las versiones de la spec D-8 son las
que el entorno ejecuta:

```text
fastapi 0.142.2 · uvicorn 0.54.0 · SQLAlchemy 2.1.1 · psycopg2-binary 2.9.13
pydantic 2.13.5 · pydantic-settings 2.15.0 · python-dotenv 1.2.3
PyJWT 2.15.1 · httpx 0.28.1
```

Si alguna no coincide, **no se cambia la versión**: se actualiza la spec antes de pinear. El
pineo fija lo que ya está instalado y verificado.

### 2.3 `backend/requirements.txt`

Diez líneas, todas con `==`:

```text
fastapi==0.142.2
uvicorn==0.54.0
sqlalchemy==2.1.1
psycopg2-binary==2.9.13
pydantic[email]==2.13.5
pydantic-settings==2.15.0
python-dotenv==1.2.3
PyJWT[crypto]==2.15.1
httpx==0.28.1
prometheus-client==0.26.0
```

`prometheus-client` se instala en el venv con `-r requirements.txt` y se comprueba con
`pip check`. Es la única dependencia nueva (D-9) y no arrastra transitivas.

### 2.4 Test de reproducibilidad

`backend/tests/test_dependencias_024.py` lee `requirements.txt` y fija:

- exactamente diez dependencias directas;
- todas con `==`;
- el conjunto nombre→versión de D-8 + `prometheus-client`;
- `prometheus-client` aparece una sola vez.

No consulta la red ni el entorno instalado; el `pip check` de T10 cubre la resolución real.

## 3. Configuración por entorno (T2)

### 3.1 `backend/app/core/config.py`

Añadir la constante de versión de aplicación y tres ajustes:

```python
VERSION_APLICACION = "1.0.0"

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # ... campos existentes ...
    ALLOWED_ORIGINS: str = "http://localhost:4200,http://localhost:8080"
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"

    @field_validator("ALLOWED_ORIGINS")
    @classmethod
    def validar_origenes(cls, valor: str) -> str:
        origenes = [origen.strip() for origen in valor.split(",") if origen.strip()]
        if not origenes:
            raise ValueError(
                "ALLOWED_ORIGINS no puede quedar vacío: declare al menos un origen "
                "explícito separado por comas."
            )
        return ",".join(origenes)

    @property
    def origenes_permitidos(self) -> list[str]:
        return [
            origen.strip()
            for origen in self.ALLOWED_ORIGINS.split(",")
            if origen.strip()
        ]
```

`VERSION_APLICACION` se usa en `FastAPI(version=...)` y en `compustock_app_info`. No cambia el
valor publicado hoy (`1.0.0`).

`LOG_LEVEL` y `LOG_FORMAT` **no** se validan con `Literal`: un valor desconocido no debe romper
el arranque. La normalización ocurre en `core/observabilidad.py` (T3): formato desconocido →
`json`; nivel desconocido → `INFO`.

### 3.2 Pruebas

`backend/tests/test_configuracion_024.py`:

- default de `ALLOWED_ORIGINS` → dos orígenes;
- `" http://a , , http://b "` → `["http://a", "http://b"]`;
- `ALLOWED_ORIGINS=""` y `" , "` → `ValidationError` con el nombre de la variable;
- `Settings(ALLOWED_ORIGINS="http://otro.example")` → solo ese origen;
- `LOG_FORMAT` desconocido → resuelve `json`; `LOG_LEVEL` desconocido → resuelve `INFO`;
- `VERSION_APLICACION == "1.0.0"`.

## 4. Logging estructurado (T3)

### 4.1 `backend/app/core/observabilidad.py` (nuevo)

Contiene la infraestructura compartida por el middleware y los endpoints operativos:

```python
LOGGER_RAIZ = "compustock"
LOGGER_ACCESO = "compustock.acceso"
LOGGER_SALUD = "compustock.salud"

UUID_CANONICO = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
IDENTIFICADOR_PETICION: ContextVar[str | None] = ContextVar(
    "identificador_peticion", default=None
)
CAMPOS_ADICIONALES = (
    "request_id", "method", "path", "status", "duration_ms", "evento", "error_type",
)
```

Funciones:

- `resolver_identificador(cabecera: str | None) -> str`: devuelve la cabecera **idéntica** si
  cumple `UUID_CANONICO`; en cualquier otro caso, `str(uuid.uuid4())`. No usa `uuid.UUID` para
  validar porque acepta formas sin guiones que la spec excluye.
- `identificador_actual() -> str | None`: lee el `ContextVar`.
- `resolver_formato(valor: str | None) -> str`: `"text"` (sin distinguir mayúsculas) o `"json"`
  por defecto.
- `resolver_nivel(valor: str | None) -> int`: mapa `DEBUG/INFO/WARNING/ERROR/CRITICAL`;
  desconocido → `logging.INFO`.
- `nivel_de_estado(status: int) -> int`: `ERROR` para ≥500, `WARNING` para ≥400, `INFO` resto.
- `configurar_registro(nivel=None, formato=None, nombre_logger=LOGGER_RAIZ)`: configura un
  `StreamHandler(sys.stdout)` con formateador JSON o texto, `propagate=False` y reemplazo
  idempotente del handler propio. No toca los loggers de uvicorn.
- `FormateadorJSON` y `FormateadorTexto`.

`FormateadorJSON.format()` emite **solo** estos campos, más los adicionales presentes en el
`LogRecord`:

```json
{"timestamp":"2026-11-14T12:00:00+00:00","level":"INFO","logger":"compustock.acceso",
 "message":"peticion_completada","request_id":"...","method":"GET","path":"/health",
 "status":200,"duration_ms":1.234}
```

`timestamp` es UTC ISO-8601; `message` es un texto fijo (`peticion_completada` o
`readiness_fallida`); nunca se registran cabeceras, cuerpos, query string, correos, tokens,
usuarios, instituciones ni tenants. `FormateadorTexto` produce una línea legible con los mismos
campos y **no** es JSON válido.

### 4.2 Pruebas

`backend/tests/test_configuracion_024.py` (formato/nivel) y
`backend/tests/api/test_correlacion_024.py` (integración):

- formatear un `LogRecord` con los nueve campos → `json.loads` correcto;
- `FormateadorTexto` → `json.loads` falla;
- `nivel_de_estado(200/404/500)` → INFO/WARNING/ERROR;
- `configurar_registro("WARNING", ...)` deja el logger y su handler en WARNING; un INFO no se
  emite y un WARNING sí (se usa un logger de prueba, no el global);
- una petición con `Authorization: Bearer token-secreto`, correo en el cuerpo y
  `?correo=foo@example.com` produce una línea sin token, sin correo, sin query string y sin
  `set-cookie`.

## 5. Correlación y app factory (T4)

### 5.1 `backend/app/middleware/observabilidad.py` (nuevo)

Middleware ASGI puro, no `BaseHTTPMiddleware`:

```python
class MiddlewareObservabilidad:
    def __init__(self, app): self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send); return
        ...
```

Responsabilidades:

1. Resolver el identificador con `resolver_identificador` a partir de
   `scope["headers"]` (`b"x-request-id"`).
2. Guardarlo en `scope.setdefault("state", {})["request_id"]` y en el `ContextVar`; resetear el
   token en `finally` (AC-3: sin fuga entre peticiones).
3. Envolver `send`: en `http.response.start`, fijar `X-Request-ID` con el valor efectivo usando
   `MutableHeaders(scope=mensaje)`. Esto cubre éxitos, 4xx, 404, `/health`, `/ready`, `/metrics`
   y preflight.
4. Medir duración con `time.perf_counter()` y capturar el `status` del mensaje de inicio.
5. En el `finally`, registrar **una** línea de acceso con `LOGGER_ACCESO`, nivel derivado del
   estado y los campos de R-2.1. `path` sale de `scope.get("route").path`; si no hay ruta
   resuelta se usa el valor fijo `RUTA_NO_RESUELTA = "unmatched"`. Nunca se usa
   `scope["path"]` crudo ni `scope["query_string"]`.
6. Si `self.app` lanza, fijar estado 500, dejar que la excepción siga y registrar la línea 500.
   El cuerpo y el estado no se alteran.
7. Si el `path` es `/metrics` (con o sin barra final), no tocar contadores, histograma, gauge en
   vuelo ni errores; sí se asigna `X-Request-ID` y se registra la línea de acceso.

La instrumentación y el logging del `finally` son *best-effort*: cualquier fallo al registrar se
suprime para no cambiar el resultado de la petición. El `ContextVar` se resetea siempre.

### 5.2 `backend/app/main.py`: `crear_app()`

Refactor interno sin cambio de contrato:

```python
def crear_app() -> FastAPI:
    configurar_registro()
    aplicacion = FastAPI(..., version=VERSION_APLICACION)
    # T4 conserva el CORS actual; T5 lo sustituye por CORSEstricto.
    aplicacion.add_middleware(CORSMiddleware, ...)
    aplicacion.add_middleware(MiddlewareObservabilidad)
    aplicacion.add_exception_handler(Exception, manejador_error_no_controlado)
    aplicacion.include_router(api_router, prefix="/api/v1")
    aplicacion.include_router(router_operativo)
    # / y /health se declaran aquí, igual que hoy.
    return aplicacion

app = crear_app()
```

Orden de middlewares: **primero CORS, después observabilidad**, de modo que observabilidad sea
la capa más externa y el preflight también reciba `X-Request-ID`. No se envuelve `app` en un
middleware ASGI externo: la suite usa `app.openapi()` y `TestClient(app)` sobre el objeto
FastAPI.

### 5.3 Manejador de excepción no controlada

`manejador_error_no_controlado(request, exc)`:

- lee `request.scope.get("state", {}).get("request_id")`;
- devuelve `PlainTextResponse("Internal Server Error", status_code=500)` con `X-Request-ID` si
  existe, conservando el cuerpo y el `Content-Type` que Starlette produce hoy;
- no registra traceback ni detalles de la excepción.

El `ContextVar` ya está en el `scope`, así que el manejador —que corre en
`ServerErrorMiddleware`, fuera del middleware de observabilidad— puede correlacionar la
respuesta.

### 5.4 Pruebas

`backend/tests/api/test_correlacion_024.py`:

- cabecera UUID canónica en `/`, `/health`, `/ready`, `/metrics`, una operación autenticada de
  `/api/v1`, 404, 422 y 500;
- UUID entrante válido (incluida mayúscula) devuelto idéntico;
- `"abc"`, `""`, UUID sin guiones y ausencia → UUID4 distinto;
- dos peticiones consecutivas → identificadores distintos y cada línea de log con el suyo;
- 500 con `cliente_sin_excepcion` sobre una ruta temporal `include_in_schema=False` que lanza
  `RuntimeError`; la ruta se elimina en `finally`;
- el cuerpo de `/health` sigue siendo `{"status": "healthy"}`.

## 6. CORS por entorno (T5)

### 6.1 `backend/app/core/cors.py` (nuevo)

`CORSMiddleware` de Starlette añade automáticamente a `Access-Control-Allow-Headers` las
cabeceras *safelisted* (`Accept-Language`, `Content-Language`, etc.). AC-18 exige exactamente
`Authorization, Content-Type, Accept`, así que se usa una subclase mínima:

```python
class CORSEstricto(CORSMiddleware):
    def __init__(self, app, *, cabeceras_permitidas, **kwargs):
        self._cabeceras_permitidas = list(cabeceras_permitidas)
        super().__init__(app, allow_headers=cabeceras_permitidas, **kwargs)

    def preflight_response(self, request_headers):
        respuesta = super().preflight_response(request_headers)
        if respuesta.status_code == 200:
            respuesta.headers["Access-Control-Allow-Headers"] = ", ".join(
                self._cabeceras_permitidas
            )
        return respuesta
```

La validación de método/cabeceras sigue siendo la de Starlette; solo se recorta la cabecera de
respuesta a las tres declaradas. No hay `*` en orígenes, métodos ni cabeceras.

### 6.2 Cableado

En `crear_app()`:

```python
aplicacion.add_middleware(
    CORSEstricto,
    allow_origins=settings.origenes_permitidos,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    cabeceras_permitidas=["Authorization", "Content-Type", "Accept"],
)
```

Antes de construir, `crear_app()` comprueba que `settings.origenes_permitidos` no esté vacío y
levanta `ValueError` con el mismo mensaje de configuración. El fail-fast real de la variable
vacía ya ocurre en `Settings` (T2); esta guarda cubre mutaciones de la instancia en pruebas o en
un futuro cargador.

### 6.3 Pruebas

`backend/tests/api/test_cors_024.py`:

- default: `Origin: http://localhost:4200` y `http://localhost:8080` reciben ACAO y
  `Access-Control-Allow-Credentials: true`;
- origen ajeno no recibe ACAO;
- `monkeypatch.setattr(settings, "ALLOWED_ORIGINS", "http://otro.example")` + `crear_app()`:
  el nuevo origen se permite y el default deja de permitirse;
- `ALLOWED_ORIGINS=""` levanta `ValidationError`/`ValueError` al construir;
- preflight `OPTIONS` con `Access-Control-Request-Method: POST` y
  `Access-Control-Request-Headers: authorization,content-type` devuelve métodos exactamente
  `GET, POST, PUT, PATCH, DELETE, OPTIONS` y cabeceras exactamente
  `Authorization, Content-Type, Accept`;
- ninguna cabecera CORS vale `*`.

## 7. Salud y readiness (T6)

### 7.1 `backend/app/db/database.py`

Añadir un motor dedicado, sin tocar el motor de negocio:

```python
from sqlalchemy.pool import NullPool

def crear_motor_readiness(url: str | None = None) -> Engine:
    cadena = url or settings.DATABASE_URL
    opciones = {"poolclass": NullPool}
    if cadena.startswith("postgresql"):
        opciones["connect_args"] = {
            "connect_timeout": 2,
            "options": "-c statement_timeout=2000",
        }
    return create_engine(cadena, **opciones)

motor_readiness = crear_motor_readiness()
```

`NullPool` evita conservar una conexión muerta entre sondas. Los valores de 2 s son la cota
inicial; si la medición de T12 supera 2 s por overhead, se bajan a 1 s / 1500 ms y se registra
en la evidencia. El motor de negocio y su pool **no** cambian.

### 7.2 `backend/app/services/salud_service.py` (nuevo)

```python
def comprobar_conectividad(motor: Engine) -> tuple[bool, str | None]:
    try:
        with motor.connect() as conexion:
            conexion.execute(select(literal(1)))
        return True, None
    except SQLAlchemyError as exc:
        return False, type(exc).__name__
```

No hay SQL textual: `select(literal(1))` es Core tipado. No se lee ninguna tabla de dominio. El
nombre del error es lo único que se registra; nunca la cadena de conexión ni el mensaje de
psycopg2.

### 7.3 `backend/app/api/operativo.py` (nuevo)

`router_operativo = APIRouter()` con dos rutas, ambas `include_in_schema=False`:

- `GET /ready`: depende de `obtener_motor_readiness` (seam en `app/api/dependencies.py`).
  200 `{"status":"ready"}` o 503 `{"status":"not_ready"}`. En el 503 se registra
  `readiness_fallida` en `LOGGER_SALUD` con `request_id` y `error_type`; el cuerpo no lleva
  detalle.
- `GET /metrics`: `Response(content=metricas.generar_exposicion(), media_type=TIPO_CONTENIDO)`.

`/health` **no** se mueve ni se modifica: sigue en `main.py`, sin base, documentado y con
`{"status":"healthy"}`.

### 7.4 Seam de pruebas

`backend/app/api/dependencies.py`:

```python
def obtener_motor_readiness() -> Engine:
    return motor_readiness
```

`backend/tests/conftest.py` añade el override en `_cliente_de_prueba`:

```python
app.dependency_overrides[dependencies.obtener_motor_readiness] = lambda: motor
```

Así la suite ordinaria usa SQLite en memoria y no toca PostgreSQL.

### 7.5 Pruebas

`backend/tests/api/test_salud_024.py`:

- `/health` 200 con el motor de readiness caído (se overridea a un fake que lanza
  `OperationalError`); no exige Bearer; sigue en OpenAPI sin `security`;
- `/ready` 200 con el motor SQLite de la suite;
- `/ready` 503 con fake caído; el cuerpo no contiene `psycopg2`, `connection`, `postgres` ni el
  nombre de la base;
- el log del 503 contiene el `request_id` de la respuesta y no la cadena de conexión;
- `crear_motor_readiness("postgresql://...")` declara `connect_timeout=2` y
  `statement_timeout=2000`; `/ready` y `/metrics` no aparecen en `/openapi.json`.

La verificación real con `db` detenido y con host inalcanzable se hace en T12.

## 8. Métricas (T7)

### 8.1 `backend/app/core/metricas.py` (nuevo)

Registro propio, nunca el global:

```python
REGISTRO = CollectorRegistry(auto_describe=True)

compustock_http_requests_total = Counter(
    "compustock_http_requests_total", "...", ["method", "route", "status"],
    registry=REGISTRO,
)
compustock_http_request_duration_seconds = Histogram(
    "compustock_http_request_duration_seconds", "...", ["method", "route"],
    registry=REGISTRO,
)
compustock_http_requests_in_flight = Gauge(
    "compustock_http_requests_in_flight", "...", registry=REGISTRO,
)
compustock_http_errors_total = Counter(
    "compustock_http_errors_total", "...", ["status"], registry=REGISTRO,
)
compustock_app_info = Gauge(
    "compustock_app_info", "...", ["version", "schema_version"], registry=REGISTRO,
)
compustock_app_info.labels(
    version=VERSION_APLICACION, schema_version=VERSION_ESQUEMA_OBJETIVO
).set(1)
```

`RUTA_NO_RESUELTA = "unmatched"` vive aquí y lo comparten middleware y métricas.

Funciones:

- `registrar_peticion(method, route, status, duracion)`: incrementa el contador, observa el
  histograma y, si `status >= 400`, incrementa el contador de errores con `status` como texto.
- `generar_exposicion() -> str`: `generate_latest(REGISTRO).decode("utf-8")`.
- `TIPO_CONTENIDO = CONTENT_TYPE_LATEST`.

El histograma lleva solo `method` y `route` (D-4). `route` es siempre plantilla; el valor fijo
`unmatched` evita una serie por ruta escaneada.

### 8.2 Instrumentación

El middleware de T4 llama a `registrar_peticion` solo si el path no es `/metrics`. El gauge en
vuelo se incrementa al entrar y se decrementa en `finally`; `/metrics` no lo toca, así que un
scrape no se cuenta a sí mismo y el gauge vuelve a 0 al terminar.

### 8.3 Pruebas

`backend/tests/api/test_metricas_024.py`:

- tras peticiones controladas, `/metrics` responde con `Content-Type` de Prometheus y las cinco
  familias;
- contador con las etiquetas exactas `method`, `route`, `status`; el histograma con cubetas y
  `_sum`; el gauge en 0 tras la respuesta;
- `GET /api/v1/inventario/existencias/987654` produce
  `route="/api/v1/inventario/existencias/{producto_id}"` y ninguna etiqueta contiene `987654`;
- `/api/v1/desconocido/987654` se agrega bajo `route="unmatched"` y no crea la serie con el
  número;
- ningún nombre ni etiqueta contiene correo, usuario, institución, tenant, token ni query;
- un scrape a `/metrics` no incrementa la serie de `/metrics`; `/metrics` responde 200 sin
  `Authorization`;
- `compustock_app_info` vale 1, `version="1.0.0"` y `schema_version="021.1"`.

Las pruebas comparan **antes/después** de la serie concreta, no valores absolutos: el registro
es de proceso y la suite completa acumula series.

### 8.4 Contrato y matriz

`backend/tests/api/test_contrato_024.py`:

- `/openapi.json` publica **75** operaciones: 73 de `/api/v1` + `/` + `/health`;
- no contiene `/metrics` ni `/ready`;
- `/health` sigue documentado sin `security`;
- `MATRIZ_PERMISOS` sigue con **73** operaciones y ninguna clave de `/metrics` o `/ready`.

## 9. B8: camino real por el borde (T8)

### 9.1 `frontend/src/app/shared/config/url-api.ts`

```ts
/** Raiz relativa de la API. Coincide con el `prefix` de `app/api/v1/api.py`. */
export const URL_API = '/api/v1';
```

Sin esquema, host ni puerto. `localhost:8000` deja de ser URL base bajo `frontend/src/`.

### 9.2 `frontend/proxy.conf.json` (nuevo)

```json
{
  "/api": {
    "target": "http://localhost:8000",
    "secure": false,
    "changeOrigin": true,
    "logLevel": "warn"
  }
}
```

El dev server reenvía `/api` conservando el path; no hay doble prefijo.

### 9.3 `frontend/angular.json`

Añadir en `projects.frontend-app.architect.serve.options`:

```json
"proxyConfig": "proxy.conf.json"
```

No se toca `build` ni `test`. No se modifica ningún otro archivo bajo `frontend/src/**`:
los specs que consumen la API importan `URL_API` y heredan la URL relativa.

### 9.4 Verificación

- `ng test --watch=false --browsers=ChromeHeadless` → **549 SUCCESS** sin tocar specs.
- `ng build` de producción limpio.
- `Get-ChildItem frontend/src -Recurse | Select-String 'localhost:8000'` no devuelve una URL
  base; el único `localhost:8000` del frontend es el `target` de `proxy.conf.json`, fuera de
  `src/`.
- `git diff --name-only -- frontend/src` devuelve **solo** `shared/config/url-api.ts`.

## 10. Borde nginx y arranque (T9)

### 10.1 `frontend/nginx.conf`

Las zonas se declaran al inicio del archivo (contexto `http`, porque el archivo se copia a
`/etc/nginx/conf.d/default.conf`):

```nginx
limit_req_zone $binary_remote_addr zone=api_peticiones:10m rate=10r/s;
limit_conn_zone $binary_remote_addr zone=api_conexiones:10m;
```

Dentro de `server`:

```nginx
limit_req_status 429;
limit_conn_status 429;
error_page 429 = @limite_api;
```

En `location /api/`:

```nginx
limit_req zone=api_peticiones burst=20 nodelay;
limit_conn api_conexiones 20;
```

La carga inicial de la SPA (≈15 peticiones) cabe en `burst=20`; una ráfaga de ≥60 produce 429.
`nodelay` permite que el burst se atienda sin encolar.

Respuesta única de error:

```nginx
location = /metrics {
    return 404;
}

location @limite_api {
    default_type application/json;
    add_header Access-Control-Allow-Origin $http_origin always;
    add_header Vary Origin always;
    return 429 '{"detail":"Demasiadas peticiones. Intente nuevamente en unos segundos."}';
}
```

- `/metrics` se niega explícitamente y no se proxifica.
- El 429 es el **único** lugar donde se refleja `$http_origin`; si la petición no trae `Origin`,
  nginx no emite la cabecera.
- `location /` y la de estáticos no llevan `limit_req` ni `limit_conn`: la SPA y sus recursos no
  quedan limitados.
- `proxy_pass http://backend:8000;` conserva `/api/v1/*` (sin barra final).

### 10.2 `docker-compose.yml` y `backend/Dockerfile`

Añadir `--no-access-log` al arranque de uvicorn en **ambos**:

```yaml
command: >
  sh -c "uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --no-access-log"
```

```dockerfile
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
```

Añadir al servicio `backend` las variables con default local:

```yaml
ALLOWED_ORIGINS: ${ALLOWED_ORIGINS:-http://localhost:4200,http://localhost:8080}
LOG_LEVEL: ${LOG_LEVEL:-INFO}
LOG_FORMAT: ${LOG_FORMAT:-json}
```

No se crea ni se modifica `.env`. El puerto `8000` sigue publicado solo para desarrollo; la
spec D-7 deja registrado que en producción no se publica.

### 10.3 Verificación

- `docker compose config` sin errores y con las tres variables.
- `docker compose build frontend` y `docker compose run --rm frontend nginx -t` (o el arranque
  de T12) valida la sintaxis.
- `docker compose logs backend` muestra una sola línea por petición a `/health`; no hay línea
  de access log de uvicorn.

## 11. Estrategia de pruebas

### 11.1 Archivos nuevos

| Archivo | Cobertura |
|---|---|
| `backend/tests/test_dependencias_024.py` | AC-22 (pineo) |
| `backend/tests/test_configuracion_024.py` | AC-6, AC-17 (validación), AC-10 (config del motor) |
| `backend/tests/api/test_correlacion_024.py` | AC-1, AC-2, AC-3, AC-4, AC-5, AC-7 (estático), AC-8 (health) |
| `backend/tests/api/test_cors_024.py` | AC-17, AC-18 |
| `backend/tests/api/test_salud_024.py` | AC-8, AC-9, AC-10 |
| `backend/tests/api/test_metricas_024.py` | AC-11, AC-12, AC-13, AC-14, AC-16 |
| `backend/tests/api/test_contrato_024.py` | AC-15, AC-23 |

`backend/tests/soporte_observabilidad_024.py` (helper, no test) concentra:

- el regex de UUID canónico;
- un `contextmanager` que adjunta un handler `StringIO` al logger `compustock` y devuelve las
  líneas;
- el parser de la exposición Prometheus (`text_string_to_metric_families`) y un lector de
  series por nombre+etiquetas;
- el fake de motor caído.

### 11.2 Aislamiento

- **Registro de métricas:** es de proceso. Ningún test afirma valores absolutos; todos comparan
  la serie antes y después. No se recarga `app.core.metricas` ni se toca el registro global.
- **Logging:** los tests de integración adjuntan su handler al logger `compustock`; el handler
  de stdout se conserva. Los tests de formato usan instancias directas.
- **ContextVar:** el middleware resetea el token en `finally`; el test de dos peticiones
  consecutivas lo comprueba.
- **Rutas temporales:** la ruta 500 se añade con `include_in_schema=False` y se elimina en
  `finally`, para no alterar el conteo de 75.
- **Readiness:** el override de `obtener_motor_readiness` en `conftest.py` evita PostgreSQL; el
  fake caído se instala y se retira dentro del test.

### 11.3 Pruebas manuales/gated

- `pytest` completo en T10 y T13.
- Tests gated de PostgreSQL 16 si `POSTGRES_TEST_URL` está disponible; no se añaden tests gated
  nuevos.
- `/ready` con `docker compose stop db` y `start db`; `/health` en ambos estados.
- Host inalcanzable para medir la cota de 2 s.
- 4200 y 8080 en T11–T12, incluida la ráfaga de ≥60 `fetch` y el `curl` con `Origin` ajeno.

## 12. Matriz tarea → AC

| Tarea | ACs |
|---|---|
| T1 | AC-22, AC-24 (línea base) |
| T2 | AC-6 (configuración), AC-17 (fail-fast) |
| T3 | AC-4, AC-5, AC-6 |
| T4 | AC-1, AC-2, AC-3, AC-8 (health intacto) |
| T5 | AC-17, AC-18 |
| T6 | AC-8, AC-9, AC-10 |
| T7 | AC-11, AC-12, AC-13, AC-14, AC-15, AC-16 |
| T8 | AC-23 (solo `url-api.ts`), AC-27 |
| T9 | AC-7, AC-19/20/21 (configuración), AC-25 (despliegue) |
| T10 | AC-15, AC-22, AC-23, AC-24 |
| T11 | AC-25, AC-27 |
| T12 | AC-7, AC-9, AC-10, AC-19, AC-20, AC-21, AC-25 |
| T13 | AC-26, AC-23 (diff final), AC-24 (suite final) |

## 13. Verificación de cierre

### 13.1 Backend

```powershell
cd backend
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m pip check
```

Esperado: **0 failed**, **88 skipped**, `passed = 1502 + tests nuevos`; `pip check` sin
problemas. Con `POSTGRES_TEST_URL`, la suite gated sigue en verde.

### 13.2 Contrato y áreas protegidas

- `/openapi.json` en vivo: **75** operaciones, sin `/metrics` ni `/ready`, `/health` sin
  `security`.
- `MATRIZ_PERMISOS`: **73**, sin rutas operativas.
- `VERSION_ESQUEMA_OBJETIVO`: `021.1`; tablas 27/24.
- `git diff --stat` sin cambios en `database/`, `backend/app/models/**`,
  `backend/app/core/permisos.py`, `.env` ni templates; bajo `frontend/src/**` solo
  `shared/config/url-api.ts`.

### 13.3 Frontend

```powershell
cd frontend
$env:CHROME_BIN = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
npx ng test --watch=false --browsers=ChromeHeadless
npx ng build
```

Esperado: **549 SUCCESS** y build limpio. El bundle de producción no contiene
`localhost:8000` como URL base.

### 13.4 Puertos

- **4200:** recorrido login → dashboard → pedidos → inventario → compras con
  `http://localhost:4200/api/v1/*` en la pestaña de red, sin CORS y con `X-Request-ID`.
- **8080:** `docker compose build frontend` + `up -d frontend`; mismo recorrido por
  `http://localhost:8080/api/v1/*`; `/metrics` sin exposición; ráfaga de ≥60 `fetch` → 429 JSON
  con `detail`; carga normal sin 429; estáticos sin 429; `curl` con `Origin` ajeno en el 429
  devuelve ACAO.
- `/ready` 200 con `db` arriba, 503 con `db` detenido, `/health` 200 en ambos.
- `docker compose logs backend`: una línea JSON por petición, sin token ni correo.

### 13.5 Documentación y evidencia

- `docs/spec/stack.md`: frontera operativa, logs, CORS, límites del borde y API por mismo origen
  con proxy de desarrollo.
- `docs/spec/roadmap.md`: fila 024 en `[x]` con fecha de cierre.
- `docs/spec/features/024-hardening-operativo/evidencia/README.md`: suites, conteos, muestras de
  logs redactadas, respuestas de `/health`/`/ready`/`/metrics`, recorridos 4200/8080, 429 y
  `git diff --stat` protegido.
- `MEMORY.md`: estado, decisiones y siguiente trabajo.
- `grep` de coherencia sobre `AGENTS.md`, `MEMORY.md` y `.agents/skills/`, incluida la búsqueda
  de `localhost:8000` en documentación vigente.
- `spec.md` §6 con cada AC marcado y su evidencia; `tasks.md` completo.

## 14. Rollback y guardas de alcance

- **T2–T7:** revertir los archivos nuevos y las líneas añadidas a `config.py`, `database.py`,
  `dependencies.py`, `main.py`, `conftest.py` y `requirements.txt`; la suite anterior vuelve a
  verde sin tocar datos.
- **T8:** restaurar `url-api.ts`, borrar `proxy.conf.json` y quitar `proxyConfig`; `ng test`
  vuelve a la línea base.
- **T9:** restaurar `nginx.conf`, `docker-compose.yml` y `Dockerfile`; reconstruir la imagen si
  se había construido.
- No hay cambios de DDL ni de datos: no se usa `down -v` para revertir la feature. El reset de
  base solo se usa si una verificación de arranque limpio lo exige.
- **Prohibido:** tocar `database/`, `backend/app/models/**`, `permisos.py`, `capacidades.py`,
  templates, `.env`, `package.json`, cualquier otro archivo bajo `frontend/src/**`, el panel de
  métricas del Superadmin, Redis, paginación, CI o load testing.

## 15. Fuera de alcance operativo

- No se crean `verificar.ps1`/`.cmd` ni workflows de GitHub Actions.
- No se añaden *workers* a uvicorn: el registro de métricas es de un solo proceso (supuesto de
  la spec §9).
- No se implementa el agregador multiproceso de `prometheus-client`.
- No se modifica el puerto `8000` publicado en desarrollo; el cambio de producción queda como
  decisión de despliegue documentada.
- No se toca la autenticación, la autorización, la matriz ni ningún `response_model`.
