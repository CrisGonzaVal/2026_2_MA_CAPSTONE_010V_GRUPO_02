# Plan de implementación — Feature 025: Límite de tasa distribuido

**Feature:** `025-limite-tasa-distribuido/`
**Spec:** [spec.md](spec.md)
**Enfoque:** trece tareas secuenciales; cada una deja la suite en verde y no toca el contrato de negocio.
**Regla:** no se reabre ninguna feature anterior. No cambia ningún archivo bajo `frontend/`, ni
`database/`, ni `backend/app/models/**`, ni `permisos.py`. El único archivo preexistente de
prueba que cambia por la dependencia nueva es `tests/funcional/unitarios/test_dependencias_024.py`; además,
`tests/conftest.py` apaga el limitador para la suite heredada.

## 1. Orden de ejecución

```text
T1 línea base + redis==8.1.0 + test de dependencias
  → T2 configuración por entorno
  → T3 núcleo: script Lua, IP y almacén Redis
  → T4 middleware, alcance y contrato del 429
  → T5 fail-open y aviso acotado
  → T6 métricas y ruta reservada
  → T7 servicio Redis en Compose
  → T8 pruebas gated contra Redis real
  → T9 verificación backend, contrato y áreas protegidas
  → T10 recorrido funcional en 4200
  → T11 humo, 429 y fail-open en 8080
  → T12 prueba de dos workers
  → T13 cierre documental, evidencia y commit
```

T2–T8 son backend y se prueban con `pytest` sin Docker, salvo T8, que necesita el servicio de
T7. T9 es la puerta de contrato antes de tocar los puertos. T10–T12 son verificación manual y
no cambian código. T13 no cierra nada que T9–T12 no hayan verificado.

## 2. Archivos y frontera

### 2.1 Archivos nuevos

| Archivo | Responsabilidad |
|---|---|
| `backend/app/core/limite_tasa.py` | Constantes, script Lua, resolución de IP, protocolo de almacén y `AlmacenRedis`. |
| `backend/app/middleware/limite_tasa.py` | Middleware ASGI que decide y emite el 429. |
| `backend/tests/no_funcional/rendimiento/soporte_limite_tasa_025.py` | `AlmacenFalso`, reloj controlable y fábricas de app con límite. |
| `backend/tests/funcional/unitarios/test_configuracion_025.py` | Defaults y validaciones de `Settings`. |
| `backend/tests/funcional/unitarios/test_limite_tasa_unidad_025.py` | IP, alcance de ruta, preflight y semántica del limitador con el falso. |
| `backend/tests/no_funcional/rendimiento/test_limite_tasa_025.py` | Conteo, 429, cabeceras, CORS, alcance y estado compartido. |
| `backend/tests/no_funcional/rendimiento/test_limite_tasa_failopen_025.py` | Fail-open, aviso único y `/ready` intacto. |
| `backend/tests/no_funcional/rendimiento/test_metricas_limite_tasa_025.py` | Familia nueva y `route="rate_limited"`. |
| `backend/tests/no_funcional/rendimiento/test_limite_tasa_redis_025.py` | Suite *gated* con `REDIS_TEST_URL`. |
| `docs/spec/features/025-limite-tasa-distribuido/evidencia/README.md` | Evidencia de cierre. |

### 2.2 Archivos modificados

| Archivo | Cambio |
|---|---|
| `backend/app/core/config.py` | Cinco variables y dos validadores. |
| `backend/app/core/metricas.py` | `RUTA_LIMITADA`, contador nuevo y `registrar_limite`. |
| `backend/app/core/observabilidad.py` | `LOGGER_LIMITE` y `request_id`/`error_type` ya admitidos. |
| `backend/app/middleware/observabilidad.py` | `_ruta_plantilla` devuelve `rate_limited` cuando el limitador marcó el rechazo. |
| `backend/app/main.py` | `crear_app(cliente_limite=None)`, cableado y orden de capas. |
| `backend/tests/conftest.py` | Apaga el limitador en el singleton antes de importar `app.main`. |
| `backend/tests/funcional/unitarios/test_dependencias_024.py` | 10 → 11 dependencias; nombre y docstring. |
| `backend/requirements.txt` | `redis==8.1.0`. |
| `docker-compose.yml` | Servicio `redis` y cinco variables en `backend`. |
| `docs/spec/stack.md` | Nuevo apartado §1.2. |
| `AGENTS.md`, `README.md`, `MEMORY.md`, `docs/spec/roadmap.md` | Servicios, comandos y estado. |
| `spec.md`, `tasks.md` | Cierre de la feature. |

### 2.3 Lo que no se toca

`frontend/**` completo, `database/**`, `backend/app/models/**`, `backend/app/core/permisos.py`,
`backend/app/schemas/**`, los endpoints de negocio, los `response_model`, los textos visibles,
`backend/Dockerfile` (no hace falta: `redis` es Python puro), `backend/.dockerignore`,
`package.json`, `frontend/nginx.conf` y cualquier `.env`.

## 3. T1 — Línea base y dependencia

### 3.1 Línea base

```powershell
cd backend
.venv/Scripts/python.exe -m pytest -q
cd ..\frontend
$env:CHROME_BIN = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
npx ng test --watch=false --browsers=ChromeHeadless
```

Esperado: **1596 passed / 88 skipped / 0 failed** y **549 SUCCESS**. Se registran en
`evidencia/README.md` antes de tocar código. Con `POSTGRES_TEST_URL`, la suite *gated* sigue en
**73 passed**.

### 3.2 `backend/requirements.txt`

Se añade una sola línea al final:

```text
redis==8.1.0
```

Verificación de D-9 ya hecha en la spec: *wheel* `py3-none-any`, MIT, Python ≥ 3.10, sin
transitivas obligatorias en 3.11.3/3.12. No se instala `hiredis` ni `fakeredis`.

```powershell
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe -m pip check
```

### 3.3 `backend/tests/funcional/unitarios/test_dependencias_024.py`

La prueba de la feature cerrada cambia **solo el conteo y el conjunto**:

- `VERSIONES_ESPERADAS` incorpora `"redis": "8.1.0"`.
- Las aserciones de longitud pasan de 10 a 11.
- El docstring y los mensajes dicen «once».
- `test_prometheus_client_es_la_unica_dependencia_nueva` se renombra a una afirmación
  equivalente sobre las dos dependencias añadidas desde la línea base de la 024
  (`prometheus-client` y `redis`), sin reescribir la intención: nivel directo exacto y pineado.

No se modifica ningún `spec.md`, `plan.md` ni `tasks.md` de la 024.

### 3.4 Evidencia inicial

`docs/spec/features/025-limite-tasa-distribuido/evidencia/README.md` nace con la línea base, las
versiones instaladas y el estado del árbol (`git status --porcelain`).

**Hecho cuando:** `pytest` sigue en 1596/88/0 antes de añadir código, `pip check` está limpio y
`test_dependencias_024.py` pasa en 11/11.

## 4. T2 — Configuración por entorno

### 4.1 `backend/app/core/config.py`

Después de `LOG_FORMAT`:

```python
    # Feature 025 (D-8): limite de tasa distribuido con Redis.
    REDIS_URL: str = "redis://127.0.0.1:6380/0"
    LIMITE_TASA_HABILITADO: bool = True
    LIMITE_TASA_MAX_PETICIONES: int = 120
    LIMITE_TASA_VENTANA_SEGUNDOS: int = 60
    LIMITE_TASA_CONFIAR_PROXY: bool = False
```

Validaciones:

```python
    @field_validator("LIMITE_TASA_MAX_PETICIONES", "LIMITE_TASA_VENTANA_SEGUNDOS")
    @classmethod
    def validar_limite_positivo(cls, valor: int) -> int:
        if valor < 1:
            raise ValueError(
                "LIMITE_TASA_MAX_PETICIONES y LIMITE_TASA_VENTANA_SEGUNDOS "
                "deben ser enteros mayores o iguales a 1."
            )
        return valor

    @model_validator(mode="after")
    def validar_url_redis(self):
        if self.LIMITE_TASA_HABILITADO and not self.REDIS_URL.startswith(
            ("redis://", "rediss://")
        ):
            raise ValueError(
                "REDIS_URL debe empezar por redis:// o rediss:// cuando "
                "LIMITE_TASA_HABILITADO esta activo."
            )
        return self
```

Se importa `model_validator` de Pydantic v2. El validador de URL solo corre con el limitador
encendido: apagarlo permite arrancar con una URL cualquiera sin abrir conexiones (R-8.4).

### 4.2 Pruebas

`backend/tests/funcional/unitarios/test_configuracion_025.py`, con `monkeypatch.delenv` de las cinco variables
para que un shell de verificación no altere los defaults:

- `Settings()` trae `True`, `120`, `60`, `False` y `redis://127.0.0.1:6380/0`.
- `LIMITE_TASA_MAX_PETICIONES=0` y `LIMITE_TASA_VENTANA_SEGUNDOS=0` lanzan `ValidationError`
  cuyo texto nombra la variable.
- `REDIS_URL="http://x"` con el limitador encendido lanza `ValidationError` con `REDIS_URL`.
- La misma URL con `LIMITE_TASA_HABILITADO=False` construye sin error.
- `rediss://...` se acepta.
- `LIMITE_TASA_HABILITADO="false"` se interpreta como `False`.

No se toca `test_configuracion_024.py`.

**Hecho cuando:** los defaults son los de D-8, los cuatro casos inválidos fallan con mensaje
claro y la suite heredada sigue verde.

## 5. T3 — Núcleo del limitador

### 5.1 `backend/app/core/limite_tasa.py` (nuevo)

Constantes:

```python
LIMITE_PREFIJO_CLAVE = "compustock:limite:"
TEXTO_LIMITE = "Demasiadas peticiones. Intente nuevamente en unos segundos."
IP_RESERVADA = "ip-desconocida"
MILISEGUNDOS_POR_SEGUNDO = 1000
TIEMPO_MAXIMO_EVALUACION = 0.5

SCRIPT_LUA = """
local actual = redis.call('INCR', KEYS[1])
local ttl = redis.call('PTTL', KEYS[1])
if actual == 1 or ttl < 0 then
    redis.call('PEXPIRE', KEYS[1], ARGV[1])
    ttl = tonumber(ARGV[1])
end
return {actual, ttl}
"""
```

El script es atómico y cubre los tres estados: clave nueva (`actual == 1`), clave con TTL
vigente (no lo renueva) y clave anómala sin TTL o con TTL negativo (lo repara). Devuelve dos
enteros: contador y TTL restante en milisegundos.

### 5.2 Resolución de IP y alcance

Funciones puras, sin dependencias de FastAPI:

```python
def resolver_ip(scope: dict, confiar_proxy: bool) -> str:
    """IP del cliente; `X-Real-IP` solo si se confia en el proxy."""

def es_ruta_limitada(camino: str) -> bool:
    """`/api/v1` o cualquier subruta por segmento."""

def es_preflight(scope: dict) -> bool:
    """OPTIONS con Origin y Access-Control-Request-Method."""
```

Reglas de `resolver_ip`:

1. Con `confiar_proxy=True`, busca `x-real-ip`, decodifica `latin-1`, recorta y valida con
   `ipaddress.ip_address`. Si es válida, devuelve `str(direccion)`, que normaliza IPv6.
2. En cualquier otro caso usa `scope["client"][0]`. Si no hay par o el host está vacío,
   devuelve `IP_RESERVADA`.
3. `x-forwarded-for` no se lee nunca, ni siquiera como respaldo.
4. La cabecera inválida (`abc`, `1.2.3.4:80`, una lista) se ignora sin lanzar.

`es_preflight` compara cabeceras en minúsculas y exige las dos: `origin` y
`access-control-request-method`. El preflight no se evalúa ni consume presupuesto.

### 5.3 `AlmacenRedis`

Protocolo mínimo:

```python
class AlmacenLimite(Protocol):
    async def registrar(self, clave: str, ventana_ms: int) -> tuple[int, int]: ...
    async def cerrar(self) -> None: ...
```

Implementación:

```python
class AlmacenRedis:
    def __init__(self, url: str) -> None:
        self._url = url
        self._cliente = None

    def _obtener_cliente(self):
        if self._cliente is None:
            self._cliente = redis.asyncio.Redis.from_url(
                self._url,
                socket_connect_timeout=0.2,
                socket_timeout=0.2,
                max_connections=20,
                retry=Retry(NoBackoff(), 0),
            )
        return self._cliente

    async def registrar(self, clave: str, ventana_ms: int) -> tuple[int, int]:
        respuesta = await self._obtener_cliente().eval(
            SCRIPT_LUA, 1, clave, ventana_ms
        )
        if not isinstance(respuesta, (list, tuple)) or len(respuesta) != 2:
            raise ValueError("respuesta inesperada del script de limite")
        actual, ttl_ms = int(respuesta[0]), int(respuesta[1])
        if actual < 1 or ttl_ms < 0:
            raise ValueError("valores fuera de rango del script de limite")
        return actual, ttl_ms

    async def cerrar(self) -> None:
        if self._cliente is not None:
            await self._cliente.aclose()
```

- El cliente se construye en la **primera** llamada a `registrar`, dentro del bucle de
  eventos; el constructor solo guarda la URL. Con el limitador apagado no se construye ni el
  almacén ni el cliente.
- `Redis.from_url` tampoco conecta al construirse: la primera conexión ocurre en el primer
  `eval`. Así se cumple R-2.2 sin abrir sockets en el arranque.
- `_obtener_cliente` es síncrono, de modo que dos peticiones concurrentes del mismo bucle no
  pueden crear dos clientes: no hay `await` entre la comprobación y la asignación.
- `max_connections=20` acota el *pool*; la espera por una conexión libre no tiene un
  argumento propio en redis-py 8.1.0 (`from_url(timeout=...)` lanza `TypeError` porque ese
  nombre se reenvía a la conexión), así que la cota real la impone el `asyncio.wait_for` de
  0,5 s en `evaluar`. Con Redis en un agujero negro el fail-open sigue siendo una cota.
- Sin `decode_responses`; el script devuelve enteros y `int()` tolera *bytes* si el servidor
  respondiera en RESP2.

### 5.4 `ResultadoLimite` y `LimitadorTasa`

```python
@dataclass(frozen=True)
class ResultadoLimite:
    permitida: bool
    restantes: int
    reinicio_segundos: int

class LimitadorTasa:
    def __init__(self, almacen, maximo, ventana_segundos, confiar_proxy, intervalo_aviso=10.0):
        ...

    async def evaluar(self, scope: dict) -> ResultadoLimite:
        ...
```

Lógica de éxito:

1. `clave = f"{LIMITE_PREFIJO_CLAVE}{resolver_ip(scope, self._confiar_proxy)}"`.
2. `actual, ttl_ms = await self._almacen.registrar(clave, self._ventana_segundos * 1000)`.
3. `permitida = actual <= self._maximo`.
4. `restantes = max(0, self._maximo - actual)`.
5. `reinicio = max(1, min(self._ventana_segundos, ceil(ttl_ms / 1000)))`.
6. Incrementa la métrica con `permitida` o `limitada` y devuelve el resultado.

La IP solo aparece en la clave de Redis; no se registra, no se etiqueta y no viaja en la
respuesta. La emisión de la métrica es *best-effort*: un fallo de instrumentación no puede
convertir un fail-open ni una petición permitida en un 5xx.

### 5.5 Pruebas unitarias

`backend/tests/funcional/unitarios/test_limite_tasa_unidad_025.py`:

- `resolver_ip` sin confianza ignora `X-Real-IP`; con confianza usa una IPv4 y una IPv6
  válidas; `abc`, `1.2.3.4:80` y `"1.1.1.1, 2.2.2.2"` caen al par; sin par devuelve
  `IP_RESERVADA`.
- `X-Forwarded-For` no cambia la IP en ningún modo.
- `es_ruta_limitada("/api/v1")`, `/api/v1/...` sí; `/api/v10`, `/health`, `/metrics`, `/docs`
  y `/` no.
- `es_preflight` exige método, `Origin` y `Access-Control-Request-Method`.
- Con `AlmacenFalso`, 3 permitidas y la cuarta rechazada con `restantes == 0`; el TTL no se
  renueva al rechazar; el reinicio es 60 en la primera petición y decrece con el reloj.
- La clave contiene la IP de prueba y el prefijo.

**Hecho cuando:** las funciones puras y el limitador se prueban sin Docker, y la suite heredada
sigue verde.

## 6. T4 — Middleware, alcance y 429

### 6.1 `backend/app/middleware/limite_tasa.py` (nuevo)

ASGI puro, por la misma razón que el de observabilidad: no altera cuerpos ajenos ni rompe
`TestClient`/`openapi()`.

```python
class MiddlewareLimiteTasa:
    def __init__(self, app, limitador):
        self.app = app
        self.limitador = limitador

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] != "http"
            or not es_ruta_limitada(scope.get("path", ""))
            or es_preflight(scope)
        ):
            await self.app(scope, receive, send)
            return

        resultado = await self.limitador.evaluar(scope)
        if resultado.permitida:
            await self.app(scope, receive, send)
            return

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
```

`X-Request-ID` no se añade aquí: lo inyecta el middleware de observabilidad al interceptar
`http.response.start`. `Access-Control-Allow-Origin` tampoco: lo añade CORS al envolver al
limitador.

### 6.2 `backend/app/main.py`

```python
def crear_app(cliente_limite=None) -> FastAPI:
    ...
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
        aplicacion.add_event_handler("shutdown", almacen.cerrar)

    aplicacion.add_middleware(CORSEstricto, ...)
    aplicacion.add_middleware(MiddlewareObservabilidad)
```

Orden real de capas (de fuera hacia dentro): **observabilidad → CORS → limitador → rutas**.
Starlette envuelve con el último middleware añadido, por eso el limitador se añade **antes** que
CORS y observabilidad. El preflight lo resuelve CORS antes de llegar al limitador; el 429 vuelve
a atravesar CORS y observabilidad.

Con `LIMITE_TASA_HABILITADO=False` no se construye almacén, no se añade middleware y no se
abre ninguna conexión. `cliente_limite` es el *seam* de pruebas: recibe un `AlmacenLimite` y
permite dos apps que comparten el mismo estado.

### 6.3 `backend/tests/conftest.py`

Antes de importar `app.main`:

```python
from app.core.config import settings as configuracion

# Feature 025: la suite heredada no debe abrir conexiones a Redis ni pagar
# timeouts. El apagado se hace sobre el singleton y no con una variable de
# entorno, para que `Settings()` siga exponiendo los defaults reales.
configuracion.LIMITE_TASA_HABILITADO = False

from app.main import app  # noqa: E402
```

Es el único cambio del archivo. Las pruebas nuevas habilitan el limitador con `monkeypatch` y
construyen su propia app.

### 6.4 `backend/app/middleware/observabilidad.py`

`_ruta_plantilla` comprueba primero la marca:

```python
from app.core.metricas import RUTA_LIMITADA, RUTA_NO_RESUELTA, ...

def _ruta_plantilla(scope: dict) -> str:
    if scope.get("state", {}).get("rate_limited"):
        return RUTA_LIMITADA
    ...
```

Así el 429 se registra como `route="rate_limited"` sin tocar el enrutado ni añadir
cardinalidad. `unmatched` se conserva para las rutas desconocidas.

### 6.5 Pruebas

`backend/tests/no_funcional/rendimiento/test_limite_tasa_025.py`, con `crear_app(cliente_limite=falso)` y
`monkeypatch` sobre el singleton para máximo/ventana:

- **AC-2:** máximo 3; tres peticiones a `/api/v1/auth/me` devuelven 401 (sin Bearer) y la
  cuarta 429. Un `POST` a `/api/v1/auth/me` consume presupuesto igual que el `GET`: el límite
  no distingue método.
- **AC-3:** el 429 es `application/json`, `detail` exacto, `Retry-After` entero entre 1 y 60,
  `X-RateLimit-Limit: 3`, `X-RateLimit-Remaining: 0`, `X-RateLimit-Reset` coherente y
  `X-Request-ID` UUID. Con `Origin: http://localhost:4200` lleva ACAO; con
  `http://evil.example` no.
- **AC-5:** con `LIMITE_TASA_CONFIAR_PROXY=True`, dos `X-Real-IP` distintas tienen contadores
  independientes: agotar una no afecta a la otra.
- **AC-6:** con confianza apagada, dos `X-Real-IP` distintas comparten el contador del par;
  con confianza encendida, una IP válida se usa; una inválida cae al par.
- **AC-7:** con máximo 3, 200 peticiones por ruta a `/`, `/health`, `/ready`, `/metrics`,
  `/docs`, `/redoc` y `/openapi.json` no reciben 429 ni incrementan el contador; un
  `/api/v1/inexistente` sí cuenta (404 contado, visible en el falso).
- **AC-8:** con máximo 120, el preflight devuelve 200 con las cabeceras exactas de la 024, no
  incrementa el contador y después de él caben las 120 peticiones; la 121 recibe 429.
- **AC-15:** dos apps con el mismo falso y máximo 3: 2 + 2 peticiones dan 3 permitidas y 1
  rechazada; ninguna app guarda el contador en proceso.
- **AC-14 (apagado):** con `LIMITE_TASA_HABILITADO=False`, `crear_app(cliente_limite=falso)` no
  añade `MiddlewareLimiteTasa`, el falso no recibe ninguna llamada y la petición sigue su curso
  normal.
- Una petición permitida no añade `X-RateLimit-*` ni cambia el cuerpo o el estado de la ruta.

**Hecho cuando:** el 429 respeta el contrato, el preflight y las rutas operativas quedan fuera,
el límite corre antes de Clerk y dos apps comparten el estado.

## 7. T5 — Fail-open

### 7.1 `LimitadorTasa.evaluar`

Todo el paso por Redis queda dentro de `try/except Exception` y con una cota dura de 0,5 s
independiente de los timeouts del cliente:

```python
        try:
            actual, ttl_ms = await asyncio.wait_for(
                self._almacen.registrar(clave, ventana_ms),
                timeout=TIEMPO_MAXIMO_EVALUACION,
            )
            if actual < 1 or ttl_ms < 0:
                raise ValueError("valores fuera de rango del script de limite")
        except Exception as error:
            registrar_limite("error")
            self._avisar(error)
            return ResultadoLimite(
                permitida=True,
                restantes=self._maximo,
                reinicio_segundos=self._ventana_segundos,
            )
```

`TIEMPO_MAXIMO_EVALUACION = 0.5` acota también la resolución de nombres o cualquier espera
ajena a `socket_connect_timeout`/`socket_timeout`: con Redis en un agujero negro la petición
nunca se cuelga y el fail-open sigue siendo una cota. `permitida=True` deja pasar la petición;
el middleware no distingue un fail-open de un permitido normal. Los errores de Redis, los
timeouts, una respuesta inesperada y cualquier fallo del propio código caen en la misma rama.

### 7.2 Aviso acotado

```python
LOGGER_LIMITE = "compustock.limite"

    def _avisar(self, error: Exception) -> None:
        ahora = time.monotonic()
        if ahora - self._ultimo_aviso < self._intervalo_aviso:
            return
        self._ultimo_aviso = ahora
        logging.getLogger(LOGGER_LIMITE).warning(
            "limite_tasa_degradado",
            extra={
                "request_id": identificador_actual(),
                "error_type": type(error).__name__,
            },
        )
```

`_ultimo_aviso` nace en `-inf` para que el primer fallo siempre avise. `request_id` y
`error_type` ya están en `CAMPOS_ADICIONALES`; no se registra IP, host, URL, mensaje de la
excepción ni traza. El aviso es por instancia de limitador y, por tanto, por proceso.

### 7.3 Pruebas

`backend/tests/no_funcional/rendimiento/test_limite_tasa_failopen_025.py`:

- **AC-9:** con `AlmacenFalso(error=ConnectionError("..."))`, 20 peticiones a `/api/v1/auth/me`
  devuelven 401 (ni 429 ni 5xx), la serie `resultado="error"` incrementa 20 y se emite **un**
  `WARNING` capturado con `capturar_logs()`; el JSON tiene `request_id` UUID y
  `error_type="ConnectionError"`, y no contiene la IP de prueba, el host, el mensaje ni `Traceback`.
- **AC-10:** con `AlmacenRedis("redis://192.0.2.1:6379/0")` y `asyncio.run`, tres mediciones de
  `evaluar` terminan en menos de 1 s, con `permitida=True`.
- **AC-11:** con el falso caído, `/ready` responde 200 `{"status":"ready"}` y `/health` 200; no
  se menciona Redis y el falso no recibe ninguna llamada. El 503 por base caída sigue cubierto
  por la suite de la 024.

**Hecho cuando:** un fallo del limitador nunca cambia el estado ni el cuerpo que produciría la
ruta, la métrica cuenta todos los fallos y el log avisa una sola vez por ventana.

## 8. T6 — Métricas y ruta reservada

### 8.1 `backend/app/core/metricas.py`

```python
RUTA_LIMITADA = "rate_limited"

compustock_rate_limit_requests_total = Counter(
    "compustock_rate_limit_requests_total",
    "Peticiones evaluadas por el limitador de tasa por resultado.",
    ["resultado"],
    registry=REGISTRO,
)


def registrar_limite(resultado: str) -> None:
    compustock_rate_limit_requests_total.labels(resultado=resultado).inc()
```

Valores admitidos: `permitida`, `limitada`, `error`. Se importa `time` en
`core/limite_tasa.py`, no aquí. La llamada se aísla en el limitador para que la
instrumentación sea best-effort, igual que en el middleware de la 024.

### 8.2 Pruebas

`backend/tests/no_funcional/rendimiento/test_metricas_limite_tasa_025.py`, con el parser de
`tests/funcional/integracion/soporte_observabilidad_024.py`:

- **AC-12:** lectura antes/después de una petición permitida y una rechazada; las series
  `{resultado="permitida"}` y `{resultado="limitada"}` incrementan exactamente 1. La etiqueta
  es exactamente `{resultado}`. Las cinco familias de la 024 siguen presentes. El 429 aparece
  como `route="rate_limited"` en `compustock_http_requests_total` y en el campo `path` de la
  línea de acceso.
- **AC-13:** con IP `203.0.113.7`, ni la exposición, ni las líneas de log, ni el cuerpo del 429
  contienen la IP, la clave `compustock:limite:` ni un token; la etiqueta `route` del 429 es el
  valor reservado.
- Con `LIMITE_TASA_HABILITADO=False` la familia nueva no incrementa y las cinco de la 024
  siguen funcionando.

**Hecho cuando:** la exposición tiene seis familias, ninguna etiqueta lleva PII y el 429 no se
confunde con un 404.

## 9. T7 — Redis en Compose

### 9.1 `docker-compose.yml`

Nuevo servicio entre `db` y `backend`:

```yaml
  # ============================================
  # REDIS: almacen efimero del limite de tasa
  # ============================================
  redis:
    image: redis:7.2-alpine
    container_name: compustock_redis
    restart: unless-stopped
    command:
      - redis-server
      - --save
      - ""
      - --appendonly
      - "no"
      - --maxmemory
      - 64mb
      - --maxmemory-policy
      - allkeys-lru
    ports:
      - "127.0.0.1:${REDIS_PORT:-6380}:6379"
    tmpfs:
      - /data:size=64m
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - compustock_network
```

La forma de lista conserva el `--save ""` vacío; en forma de cadena YAML se perderían las
comillas. Sin `volumes` y sin `depends_on` del backend hacia Redis.

La imagen oficial de Redis declara `VOLUME /data`. Para que ese `VOLUME` no cree un volumen
anónimo en disco, se sobreescribe con un **tmpfs** de 64 MB: el contenedor no tiene volumen ni
estado persistente, y `docker inspect` muestra un montaje `tmpfs`, no un volumen.

Variables nuevas en `backend.environment`:

```yaml
      REDIS_URL: ${REDIS_URL:-redis://redis:6379/0}
      LIMITE_TASA_HABILITADO: ${LIMITE_TASA_HABILITADO:-true}
      LIMITE_TASA_MAX_PETICIONES: ${LIMITE_TASA_MAX_PETICIONES:-120}
      LIMITE_TASA_VENTANA_SEGUNDOS: ${LIMITE_TASA_VENTANA_SEGUNDOS:-60}
      LIMITE_TASA_CONFIAR_PROXY: ${LIMITE_TASA_CONFIAR_PROXY:-true}
```

`LIMITE_TASA_CONFIAR_PROXY=true` en Compose porque quien habla con el backend es nginx, que
sobrescribe `X-Real-IP`. No se añade `depends_on`: el fail-open exige que el backend arranque
sin Redis.

### 9.2 Verificación

```powershell
docker compose -f docker-compose.yml config
docker compose -f docker-compose.yml up -d redis
docker compose -f docker-compose.yml ps
docker compose -f docker-compose.yml exec redis redis-cli ping
docker compose -f docker-compose.yml exec redis redis-cli CONFIG GET maxmemory
docker compose -f docker-compose.yml exec redis redis-cli CONFIG GET maxmemory-policy
docker compose -f docker-compose.yml exec redis redis-cli CONFIG GET save
docker compose -f docker-compose.yml exec redis redis-cli CONFIG GET appendonly
docker inspect compustock_redis --format "{{json .Mounts}}"
```

Esperado: `PONG`, `67108864`, `allkeys-lru`, `save` vacío, `appendonly no`, un montaje `tmpfs`
en `/data` **sin volúmenes nombrados ni anónimos**, `compustock_redis` *healthy* y
`127.0.0.1:6380->6379/tcp` en `docker compose ps`.

**Hecho cuando:** `docker compose config` valida, Redis queda *healthy*, es efímero y solo
escucha en loopback.

## 10. T8 — Pruebas gated contra Redis real

`backend/tests/no_funcional/rendimiento/test_limite_tasa_redis_025.py`:

```python
URL = os.environ.get("REDIS_TEST_URL")

pytestmark = pytest.mark.skipif(
    not URL, reason="REDIS_TEST_URL no definida: prueba gated de Redis"
)
```

Sin `pytest-asyncio` (no está en `requirements-dev.txt`): cada prueba es síncrona y envuelve su
escenario en `asyncio.run(_escenario())`.

Casos:

- **AC-16:** máximo 3, ventana 1 s: 3 permitidas, la cuarta 429; `PTTL` de la clave entre 1 y
  1000 ms; `EXISTS` de `compustock:limite:203.0.113.7` es 1.
- **AC-4:** tras `DEL` de la clave vuelve a permitir; tras esperar 1,1 s también; varios
  rechazos no aumentan el `PTTL` (comparado con una lectura previa) y `Retry-After` decrece de
  forma coherente con el TTL restante.
- **AC-16 concurrencia:** `asyncio.gather` de 20 evaluaciones con máximo 10 → exactamente 10
  permitidas y 10 rechazadas, sin carreras.
- La base se vacía al empezar y al terminar con `FLUSHDB`.
- La URL de prueba usa el índice 15 (`redis://127.0.0.1:6380/15`), nunca la base 0 de la
  aplicación.

Comando:

```powershell
$env:REDIS_TEST_URL = "redis://127.0.0.1:6380/15"
cd backend
.venv/Scripts/python.exe -m pytest tests/no_funcional/rendimiento/test_limite_tasa_redis_025.py -q
```

**Hecho cuando:** la suite gated pasa con Redis arriba y se omite limpiamente sin la variable.

## 11. T9 — Verificación backend, contrato y áreas protegidas

```powershell
$env:REDIS_TEST_URL = "redis://127.0.0.1:6380/15"
cd backend
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m pip check
```

Esperado: **0 failed**, **88 skipped**, `passed = 1596 + nuevas`; `pip check` limpio.

La corrida completa de cierre define `REDIS_TEST_URL` para que las pruebas *gated* de Redis se
ejecuten y el conteo de omitidas siga siendo el de la línea base (las pruebas *gated* de
PostgreSQL siguen omitidas y se corren aparte). Sin la variable, las nuevas pruebas gated se
omiten y el total de skipped sube en ese número; también es un resultado válido, pero no es el
de AC-18.

Con `POSTGRES_TEST_URL`, la suite *gated* de PostgreSQL sigue en **73 passed**, y la de Redis
en verde (con o sin la otra variable).

Contrato y datos:

- `/openapi.json` en vivo: **75** operaciones, sin rutas nuevas.
- `MATRIZ_PERMISOS`: **73**.
- `VERSION_ESQUEMA_OBJETIVO`: `021.1`.
- `database/`: **27** `CREATE TABLE control.*` + **24** plantillas de tenant.
- `git diff --stat` sin cambios en `database/`, `backend/app/models/**`,
  `backend/app/core/permisos.py`, `backend/app/schemas/**`, endpoints de negocio ni
  `frontend/**`.
- `requirements.txt` con **11** líneas, todas `==`.

**Hecho cuando:** la suite está en verde, los conteos no cambian y el diff protegido no tiene
sorpresas.

## 12. T10 — Recorrido funcional en 4200

Con backend y `npm start` arriba, recorrer login, dashboard, pedidos, inventario, compras y
administración.

- Confirmar en la pestaña de red que las peticiones van a `http://localhost:4200/api/v1/*`.
- Contar las peticiones del recorrido completo (referencia de la 024: **59**) y confirmar
  **0×429**.
- Confirmar `X-Request-ID` en las respuestas y ausencia de errores nuevos de consola.
- Anotar que en 4200 no hay nginx y que todas las peticiones comparten `127.0.0.1`; el
  presupuesto es único para el desarrollador.

**Hecho cuando:** el recorrido se completa por el proxy, sin 429, y el conteo queda registrado
en la evidencia.

## 13. T11 — Humo, 429 y fail-open en 8080

No se reconstruye el frontend: ningún archivo de `frontend/` cambia. Sí se recrea el backend
para que tome las variables nuevas y la dependencia:

```powershell
docker compose -f docker-compose.yml up -d --build backend
```

Pasos:

1. **Humo normal:** una recarga de la SPA (≈34 peticiones en la 024) sin 429; estáticos sin
   429; `X-Request-ID` presente.
2. **Ráfaga de la app:** `docker compose exec redis redis-cli FLUSHDB` y una ráfaga sostenida de
   ~5 r/s durante ~26 s (≈130 peticiones) desde la consola del navegador sobre
   `/api/v1/auth/me` (los 401 cuentan). Debe aparecer **429 de la aplicación** con
   `X-RateLimit-Limit: 120`, `X-RateLimit-Remaining: 0`, `Retry-After` y `X-RateLimit-Reset`.
   nginx no debe rechazar: 5 r/s está por debajo de sus 10 r/s.
3. **Diferencia de bordes:** documentar que el 429 de nginx no lleva `X-RateLimit-*` y el de la
   app sí.
4. **Fail-open:** `docker compose stop redis`; un recorrido normal sigue sin 429, el dashboard
   responde 200, `/ready` sigue 200 y `/health` 200. En `docker compose logs backend` aparece
   `limite_tasa_degradado` como máximo una vez cada 10 s, con `request_id` y `error_type`, sin
   IP ni traza. `/metrics` muestra `resultado="error"`.
5. `docker compose start redis`; confirmar que se recupera sin reiniciar el backend.
6. `curl` del 429 con `Origin: http://localhost:4200` → ACAO; con origen ajeno → sin ACAO.

**Hecho cuando:** el humo pasa, el 429 de la app es visible con sus cabeceras y el fail-open
deja la aplicación operativa.

## 14. T12 — Prueba de dos workers

```powershell
docker compose -f docker-compose.yml stop backend
docker compose -f docker-compose.yml exec redis redis-cli FLUSHDB
cd backend
$env:LIMITE_TASA_HABILITADO = "true"
$env:LIMITE_TASA_MAX_PETICIONES = "10"
$env:LIMITE_TASA_CONFIAR_PROXY = "false"
$env:REDIS_URL = "redis://127.0.0.1:6380/0"
.venv/Scripts/python.exe -m uvicorn app.main:app --workers 2 --port 8010
```

El backend de Compose se detiene durante la prueba para que no consuma el mismo contador de la
base 0; se vuelve a levantar al terminar.

Desde otra terminal, 15 peticiones secuenciales a `http://localhost:8010/api/v1/auth/me`:

- exactamente **10** devuelven 401 (permitidas) y **5** devuelven 429;
- un contador en proceso habría permitido hasta 20;
- las 5 rechazadas llevan `X-RateLimit-*`.

Al terminar: detener uvicorn, `docker compose exec redis redis-cli FLUSHDB`,
`docker compose start backend` y limpiar de la sesión `REDIS_URL` y las variables
`LIMITE_TASA_*` para que no sobreescriban las de Compose en un `up` posterior. Es evidencia
manual de cierre, no una prueba permanente; el despliegue sigue con un worker y las métricas
siguen siendo por proceso.

**Hecho cuando:** el reparto 10/5 demuestra que el estado es compartido entre procesos.

## 15. T13 — Cierre documental, evidencia y commit

### 15.1 Documentación

- `docs/spec/stack.md`: nuevo apartado **§1.2 Límite de tasa distribuido (Feature 025)** después
  de §1.1, con Redis 7.2, ventana fija, fail-open, alcance, 429 y frontera con nginx; además,
  actualizar la frase de §1.1 sobre «cinco familias» para que refleje las seis actuales.
- `AGENTS.md` §3: Redis en el stack y en Compose; §5: comando de la suite *gated* de Redis y
  `REDIS_TEST_URL`.
- `README.md`: servicio Redis y puerto local `6380`.
- `docs/spec/roadmap.md`: 025 en `[x]` con fecha de cierre y nota de que la caché de lecturas
  queda **sin feature asignada**.
- `MEMORY.md`: estado, decisiones y siguiente trabajo (015/016), actualizando también la
  referencia a las «cinco familias» de métricas.

### 15.2 Evidencia

`evidencia/README.md` reúne:

- línea base y suites finales (backend, gated PostgreSQL, gated Redis, frontend);
- conteos 75/73, `021.1` y 27/24;
- `docker compose ps`, `CONFIG GET`, `Mounts` y `redis-cli ping`;
- claves y TTL (`--scan`, `PTTL`) y salida de `FLUSHDB`;
- respuestas 429 de la app y de nginx, con y sin `X-RateLimit-*`;
- fail-open: log redactado, métrica `error`, `/ready` 200;
- prueba de dos workers 10/5;
- recorridos 4200 y 8080 con conteos;
- `git diff --stat` de áreas protegidas.

### 15.3 Cierre

- Marcar `spec.md` §6 AC por AC con su evidencia.
- Completar `tasks.md` con todas las casillas y la sección de Cierre.
- `grep` de coherencia de `AGENTS.md` §8.7 sobre `AGENTS.md`, `MEMORY.md` y `.agents/skills/`.
- `git diff --stat` final: solo archivos de la feature, `requirements.txt`,
  `docker-compose.yml`, documentación y los dos archivos de prueba preexistentes declarados.
- Commit único de la 025.

**Hecho cuando:** la documentación no tiene afirmaciones obsoletas, la evidencia cubre los 22
AC y el commit contiene solo los archivos de la feature.

## 16. Estrategia de pruebas

### 16.1 Archivos y cobertura

| Archivo | ACs |
|---|---|
| `tests/funcional/unitarios/test_dependencias_024.py` | AC-22 |
| `tests/funcional/unitarios/test_configuracion_025.py` | AC-14 |
| `tests/funcional/unitarios/test_limite_tasa_unidad_025.py` | AC-5, AC-6 |
| `tests/no_funcional/rendimiento/test_limite_tasa_025.py` | AC-2, AC-3, AC-5, AC-6, AC-7, AC-8, AC-14 (apagado), AC-15 |
| `tests/no_funcional/rendimiento/test_limite_tasa_failopen_025.py` | AC-9, AC-10, AC-11 |
| `tests/no_funcional/rendimiento/test_metricas_limite_tasa_025.py` | AC-12, AC-13 |
| `tests/no_funcional/rendimiento/test_limite_tasa_redis_025.py` | AC-4, AC-16 |

`tests/no_funcional/rendimiento/soporte_limite_tasa_025.py` (helper, no test) concentra:

- `AlmacenFalso`: contadores por clave, expiración con reloj propio, `avanzar(segundos)`,
  `error` programable, `llamadas` y `cerrar()` no-op;
- `crear_app_con_limite(falso, maximo=..., ventana=..., confiar_proxy=...)` que muta el
  singleton con `monkeypatch` y construye `crear_app(cliente_limite=falso)`;
- un `scope` HTTP mínimo para las pruebas unitarias del limitador.

### 16.2 Aislamiento

- **Suite heredada:** `conftest.py` apaga el limitador en el singleton; no hay conexiones ni
  timeouts. Las pruebas de la 024 que llaman `crear_app()` siguen sin limitador.
- **Pruebas nuevas:** nunca usan el singleton `app` con limitador; construyen una app local con
  el falso y la cierran con `TestClient` como contexto. El `shutdown` llama `cerrar()` del
  falso, que es no-op.
- **Métricas:** el registro es de proceso; ningún test afirma valores absolutos, todos comparan
  antes/después con `valor_de_serie`.
- **Logging:** `capturar_logs()` de la 024 se reutiliza; no se toca el handler de stdout.
- **Reloj:** el falso no duerme; la prueba gated usa `asyncio.sleep` solo donde la ventana real
  de 1 s lo exige.
- **Redis de prueba:** base 15 y `FLUSHDB` al inicio y al final; la base 0 de la aplicación no
  se toca.
- **Rutas:** todas las pruebas usan rutas existentes (`/api/v1/auth/me` sin Bearer → 401), así
  que no se añaden rutas temporales ni cambia el conteo de OpenAPI.
- **Readiness de la app local:** las pruebas de AC-7 que llaman `/ready` overridean
  `dependencies.obtener_motor_readiness` con el motor SQLite del fixture, igual que hace el
  `conftest` sobre el singleton; así la ruta responde 200 sin depender de PostgreSQL.

### 16.3 Pruebas manuales

- Redis *healthy*, efímero y en loopback (T7).
- Ráfaga de ~5 r/s en 8080 (T11).
- Fail-open con `docker compose stop redis` (T11).
- Dos workers 10/5 (T12).
- Recorrido completo en 4200 (T10).

## 17. Matriz tarea → AC

| Tarea | ACs |
|---|---|
| T1 | AC-22, AC-17 (11 dependencias), AC-18 (línea base) |
| T2 | AC-14 |
| T3 | AC-5, AC-6 |
| T4 | AC-2, AC-3, AC-7, AC-8, AC-15 |
| T5 | AC-9, AC-10, AC-11 |
| T6 | AC-12, AC-13 |
| T7 | AC-1 |
| T8 | AC-4, AC-16 |
| T9 | AC-17, AC-18 |
| T10 | AC-19 (4200) |
| T11 | AC-11 (manual), AC-19 (8080) |
| T12 | AC-20 |
| T13 | AC-21, AC-22 (evidencia), AC-17/AC-18 (cierre) |

## 18. Verificación de cierre

### 18.1 Backend

```powershell
$env:REDIS_TEST_URL = "redis://127.0.0.1:6380/15"
cd backend
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m pip check
```

Esperado: **0 failed**, **88 skipped**, `passed = 1596 + nuevas`. Sin `REDIS_TEST_URL`, las
pruebas gated de Redis se omiten y el total de skipped sube; la corrida de cierre usa la
variable para conservar el conteo de AC-18.

### 18.2 Contrato y áreas protegidas

- `/openapi.json`: **75** operaciones.
- `MATRIZ_PERMISOS`: **73**.
- `VERSION_ESQUEMA_OBJETIVO`: `021.1`; tablas **27/24**.
- `git diff --stat` sin cambios en `database/`, `backend/app/models/**`,
  `backend/app/core/permisos.py`, `backend/app/schemas/**`, endpoints de negocio ni
  `frontend/**`.

### 18.3 Frontend

```powershell
cd frontend
$env:CHROME_BIN = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
npx ng test --watch=false --browsers=ChromeHeadless
npx ng build
```

Esperado: **549 SUCCESS** y build limpio, sin tocar specs ni código.

### 18.4 Puertos

- **4200:** recorrido completo, ≈59 peticiones, 0×429.
- **8080:** humo con 0×429; tras `FLUSHDB`, ráfaga de ~5 r/s → 429 de la app con
  `X-RateLimit-*`; fail-open con Redis detenido; `/ready` 200.
- **Dos workers:** 15 peticiones → 10 permitidas y 5 rechazadas.

### 18.5 Documentación y evidencia

- `stack.md` §1.2, `AGENTS.md` §3/§5, `README.md`, `roadmap.md` y `MEMORY.md` actualizados.
- `evidencia/README.md` completo.
- `spec.md` §6 con los 22 AC marcados y su evidencia.
- `grep` de coherencia sin afirmaciones obsoletas.

## 19. Rollback y guardas de alcance

- **T2–T8:** revertir los archivos nuevos y las líneas añadidas a `config.py`, `metricas.py`,
  `observabilidad.py`, `middleware/observabilidad.py`, `main.py`, `conftest.py`,
  `requirements.txt` y `docker-compose.yml`; la suite anterior vuelve a verde sin tocar datos.
- **T7:** `docker compose rm -sf redis` y quitar el servicio; no hay volumen que borrar.
- No hay cambios de DDL ni de datos: no se usa `down -v` para revertir la feature.
- **Prohibido:** tocar `frontend/**`, `database/`, `backend/app/models/**`, `permisos.py`,
  `schemas/**`, endpoints de negocio, `response_model`, textos visibles, `.env`,
  `package.json`, la autenticación, la autorización, el panel de métricas del Superadmin, la
  caché de lecturas, CI o *load testing*.

## 20. Fuera de alcance operativo

- No se implementa caché de lecturas ni ninguna invalidación: queda sin feature asignada.
- No se añaden réplica, Sentinel, Cluster, ACL ni TLS de Redis: producción se documenta como
  supuesto.
- No se limita por usuario, institución, tenant ni endpoint.
- No se añaden cabeceras `X-RateLimit-*` a las respuestas exitosas.
- No se cambia el número de workers del despliegue ni se agregan métricas multiproceso.
- No se toca el borde nginx de la 024.
- No se crean scripts `verificar.ps1`/`.cmd` ni workflows de GitHub Actions.
