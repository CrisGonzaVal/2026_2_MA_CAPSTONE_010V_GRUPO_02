# Evidencia — Feature 025: Límite de tasa distribuido

**Feature:** `025-limite-tasa-distribuido/`
**Spec:** [../spec.md](../spec.md) · **Plan:** [../plan.md](../plan.md) · **Tareas:** [../tasks.md](../tasks.md)
**Estado:** en implementación.

## 1. Línea base (antes de tocar código)

| Suite | Resultado |
|---|---|
| Backend `pytest -q` | **1596 passed / 88 skipped / 0 failed** (531,89 s) |
| Frontend `ng test --watch=false --browsers=ChromeHeadless` | **549 SUCCESS** (21,119 s) |

```powershell
cd backend
.venv/Scripts/python.exe -m pytest -q

cd ..\frontend
$env:CHROME_BIN = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
npx ng test --watch=false --browsers=ChromeHeadless
```

`pull` del venv antes del cambio: `redis` no figuraba como dependencia directa
(`pip show redis` → *Package(s) not found*).

## 2. Dependencias directas (T1)

`backend/requirements.txt` pasa de diez a once líneas, todas con `==`:

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
redis==8.1.0
```

- `redis==8.1.0` es *pure Python* (`py3-none-any`), MIT, Python ≥ 3.10; no arrastra
  `hiredis` ni `fakeredis`.
- `pip check` sin conflictos tras instalar.
- `pytest tests/funcional/unitarios/test_dependencias_024.py -q` → **4 passed** con once dependencias.
- `Successfully installed redis-8.1.0`; `No broken requirements found.`

## 3. Núcleo y middleware (T3/T4)

- `backend/app/core/limite_tasa.py`: script Lua `INCR` + `PTTL` + `PEXPIRE` atómico,
  `resolver_ip` (par TCP o `X-Real-IP` validada; `X-Forwarded-For` nunca), alcance
  `/api/v1` por segmento y `LimitadorTasa` con ventana fija.
- `backend/app/middleware/limite_tasa.py`: ASGI puro; el 429 lleva `detail` idéntico al de
  nginx más `Retry-After` y `X-RateLimit-*`, y conserva `X-Request-ID` (observabilidad por
  fuera) y `Access-Control-Allow-Origin` (CORS por fuera).
- Orden real de capas: **observabilidad → CORS → limitador → rutas**; el preflight lo corta
  CORS y no consume presupuesto.
- Ajustes de API frente al plan, verificados contra las versiones instaladas:
  `add_event_handler` ya no existe en la app de FastAPI 0.142 (se registra en
  `aplicacion.router`) y `Redis.from_url(timeout=0.2)` **no** es válido en redis-py 8.1.0
  (ver §5, hallazgo de T8).
- Pruebas: **30** unitarias (T3) + **11** de API (T4); **138 passed** con las suites
  heredadas de la 024 y `test_auth.py`.

### 3.1 Fail-open (T5)

- Cualquier error de Redis (conexión, tiempo, respuesta inesperada o cota de 0,5 s) deja
  pasar la petición, incrementa `resultado="error"` y emite un `WARNING` como máximo cada
  10 s con `request_id` y `error_type`; nunca IP, host, mensaje ni traza.
- `redis://192.0.2.1:6379/0` (TEST-NET, inalcanzable): tres evaluaciones reales terminan en
  menos de 1 s con `permitida=True`.
- `/ready` y `/health` responden 200 con el almacén caído y no lo consultan.
- Pruebas: **3** de fail-open; **44 passed** con T3 y T4.

## 4. Servicio Redis en Compose (T7)

- `redis:7.2-alpine` (contenedor `compustock_redis`, Redis **7.2.17**), `restart: unless-stopped`
  y healthcheck `redis-cli ping` → *healthy*.
- `--save ""`, `--appendonly no`, `--maxmemory 64mb`, `--maxmemory-policy allkeys-lru`.
- Puerto solo en loopback: `127.0.0.1:6380->6379/tcp`.
- `/data` en **tmpfs de 64 MB** (`HostConfig.Tmpfs` → `{"/data":"size=64m"}`) y `Mounts` vacío:
  sin volúmenes nombrados ni anónimos.
- El backend **no** declara `depends_on` hacia Redis: el fail-open exige arrancar sin él.
- Verificación: `PONG`; `maxmemory=67108864`; `maxmemory-policy=allkeys-lru`; `save` vacío;
  `appendonly no`; `docker compose config` válido.

## 5. Suite *gated* contra Redis real (T8)

- `backend/tests/no_funcional/rendimiento/test_limite_tasa_redis_025.py`: tres escenarios con `asyncio.run`, sin
  `pytest-asyncio`; cada uno vacía la base 15 al empezar y al terminar (`finally`) y la
  suite se niega a correr si la URL no apunta a `/15`.
- Resultados con `REDIS_TEST_URL=redis://127.0.0.1:6380/15`: **3 passed** (3,91 s).
  Sin la variable: **3 skipped** (0,32 s).
- Escenarios: (a) 3 permitidas, cuarta rechazada, `PTTL` entre 1 y 1000 ms y clave
  `compustock:limite:203.0.113.7` presente; (b) `DEL` y expiración reinician la ventana, los
  rechazos **no** renuevan el TTL y `Retry-After` decrece con él; (c) 20 evaluaciones
  concurrentes con máximo 10 → exactamente 10/10.
- **Dos defectos reales detectados y corregidos aquí:**
  1. `Redis.from_url(timeout=0.2)` lanza `TypeError: AbstractConnection.__init__() got an
     unexpected keyword argument 'timeout'` en redis-py 8.1.0: ese nombre se reenvía a la
     conexión. Se eliminó; `socket_connect_timeout`/`socket_timeout` siguen en 0,2 s y la
     cota dura del *pool* es el `asyncio.wait_for(0.5)` de `evaluar`. La prueba de fail-open
     con `192.0.2.1` ahora mide un `TimeoutError` real a los ~0,22 s, no un `TypeError`
     instantáneo.
  2. El puerto de Compose se publica solo en IPv4 (`127.0.0.1:6380`), pero en Windows
     `localhost` resuelve primero `::1`, donde la conexión se cuelga y agota el timeout. El
     default de `REDIS_URL` y todos los comandos pasan a `127.0.0.1:6380`; el alcance
     (loopback) no cambia.
- Afectados por la corrección: `backend/app/core/limite_tasa.py`,
  `backend/app/core/config.py`, `backend/tests/funcional/unitarios/test_configuracion_025.py`, `spec.md`,
  `plan.md` y `tasks.md`.

## 6. Verificación de cierre backend y contrato (T9)

| Comprobación | Resultado |
|---|---|
| `pytest -q` con `REDIS_TEST_URL` | **1660 passed / 88 skipped / 0 failed** (326,02 s) |
| *Gated* PostgreSQL 16 | **73 passed** (16 archivos `*postgres*.py`, 354,82 s) |
| `pip check` | `No broken requirements found.` |
| `/openapi.json` en vivo | **75 operaciones** |
| `MATRIZ_PERMISOS` | **73** |
| Esquema vivo | `021.1`; **27** tablas en `control` y **24** por tenant (4 tenants) |
| `requirements.txt` | 11 líneas, todas `==`, incluida `redis==8.1.0` |
| Diff protegido | sin cambios en `frontend/`, `database/`, `models/`, `services/` ni `api/` |

## 7. Recorrido funcional en 4200 (T10)

- Backend del host en `::1:8000` con el `.env` raíz (Clerk) y `DB_HOST=127.0.0.1` /
  `DB_PORT=5433`; frontend en 4200 con `proxy.conf.json`. Sin nginx: una sola IP de proxy
  (`::1` en esta sesión) comparte el presupuesto del limitador.
- **Bodeguero** (`bodeguero.test+clerk_test@example.com`): dashboard, tablero, detalle #5,
  inventario y recepción → **11×200**.
- **Administrador** (`admin020.test+clerk_test@example.com`): dashboard, inventario con
  gestión, compras/necesidades, órdenes de compra, pedidos y administración/sedes → **13×200**.
- Total: **24 peticiones funcionales, 24×200, 0×429**; todas same-origin a
  `http://localhost:4200/api/v1/*` y **sin preflight**. Dos 401 ajenos a la 025: un refresco
  del componente de recepción tras el logout y una cuenta Clerk sin mapeo (`admin017`) antes
  de cambiar a `admin020`.
- `X-Request-ID` en todas las respuestas; consola sin errores nuevos (solo el aviso de claves
  dev de Clerk y el *issue* preexistente de campos sin `id`/`name`).

## 8. Humo, 429 y fail-open en 8080 (T11)

- Imagen del backend reconstruida (`docker compose up -d --build backend`); contenedor
  **healthy** y sirviendo por nginx (`server: nginx/1.31.8`). El frontend no se reconstruye:
  no hay cambios en `frontend/`.
- Recarga normal: `auth/me` y `dashboard/` → **2×200**, `x-request-id` presente, sin 429.
- Ráfaga controlada de **130 peticiones a 5 r/s durante 26 s** tras `FLUSHDB`:
  **120×401 + 10×429**. El primer 429:

  ```text
  Retry-After: 37
  X-RateLimit-Limit: 120
  X-RateLimit-Remaining: 0
  X-RateLimit-Reset: 37
  X-Request-ID: 5818b7b9-62e2-4d51-915c-399421801293
  {"detail":"Demasiadas peticiones. Intente nuevamente en unos segundos."}
  ```

  Los 429 son **de la aplicación**: llevan `X-RateLimit-*`; nginx no registró
  `limiting requests` (5 r/s queda por debajo de sus 10 r/s). Un 429 de nginx no lleva esas
  cabeceras.
- Origen permitido (`Origin: http://localhost:4200`) → 429 con
  `Access-Control-Allow-Origin: http://localhost:4200` y `Vary: Origin`; origen ajeno
  (`http://evil.example`) → 429 **sin** ACAO.
- Fail-open con `docker compose stop redis`: **20×401** (la ventana anterior estaba agotada,
  así que sin fail-open habrían sido 429), dashboard 200, `/ready` 200 y `/health` 200.
- Avisos en `docker compose logs backend`: dos `limite_tasa_degradado` separados **10,13 s**,
  con `request_id` y `error_type` (`ConnectionError`, `TimeoutError`), sin IP ni traza.
- `/metrics`: `compustock_rate_limit_requests_total{resultado="error"} 22.0`. Tras
  `docker compose start redis` y `FLUSHDB`, una petición vuelve a 401 y `/ready` sigue 200
  **sin reiniciar el backend**.

## 9. Dos workers (T12)

- `docker compose stop backend`, `FLUSHDB` y uvicorn temporal en `127.0.0.1:8012` con
  `--workers 2` (PIDs 11552 y 26452), `LIMITE_TASA_MAX_PETICIONES=10`,
  `REDIS_URL=redis://127.0.0.1:6380/0`, `DB_HOST=127.0.0.1` y `DB_PORT=5433`.
- 15 peticiones secuenciales a `/api/v1/auth/me`: **10×401 + 5×429**. El reparto exacto
  demuestra que el contador es **compartido entre procesos**; con un contador en memoria
  cada worker habría permitido 10 y el total habría sido 15×401.
- Las cinco rechazadas llevan `x-ratelimit-limit: 10`, `x-ratelimit-remaining: 0`,
  `x-ratelimit-reset: 59`, `retry-after: 59`, `content-type: application/json` y
  `x-request-id`.
- Limpieza: workers detenidos (`curl` a 8012 → exit 7), `FLUSHDB` → `DBSIZE 0`, backend de
  Compose reiniciado y **healthy**. Las variables `REDIS_URL`/`LIMITE_TASA_*` solo vivieron
  en la invocación temporal.
- **El despliegue sigue con un worker** (el `CMD` de la imagen no pasa `--workers`); la prueba
  solo acredita el estado compartido. Las métricas de `prometheus-client` son **por proceso**,
  así que un futuro despliegue multi-worker necesitaría un exportador agregado.

## 10. Suites de frontend y cierre (T13)

- Sin cambios en `frontend/`: la 025 es backend y Compose.
- `ng test --watch=false --browsers=ChromeHeadless` (con `CHROME_BIN` a Edge):
  **549 SUCCESS** (16,59 s).
- `ng build`: limpio (50,66 s), `Initial total 337,30 kB` y `main-2MM7TE6C.js` con el mismo
  hash que la 024, consistente con la ausencia de cambios de frontend.
- 8080 sigue operativo antes del cierre: `auth/me` responde 401 JSON con `X-Request-ID` y el
  dashboard carga con los dos 200 del humo.
