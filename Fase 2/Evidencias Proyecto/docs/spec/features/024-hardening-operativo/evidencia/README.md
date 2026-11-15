# Evidencia — Feature 024: Hardening operativo I

**Feature:** `024-hardening-operativo/`
**Spec:** [../spec.md](../spec.md) · **Plan:** [../plan.md](../plan.md) · **Tareas:** [../tasks.md](../tasks.md)
**Estado:** **cerrada** el 15/Nov/2026. Sin cambios de comportamiento, contrato, DDL ni matriz.

## 1. Línea base (antes de tocar código)

| Suite | Resultado |
|---|---|
| Backend `pytest -q` | **1502 passed / 88 skipped / 0 failed** (269.65 s) |
| Frontend `ng test --watch=false --browsers=ChromeHeadless` | **549 SUCCESS** (14.05 s) |

```powershell
cd backend
.venv/Scripts/python.exe -m pytest -q

cd ..\frontend
$env:CHROME_BIN = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
npx ng test --watch=false --browsers=ChromeHeadless
```

## 2. Dependencias directas (AC-22)

Versiones instaladas en el venv antes del pineo:

```text
fastapi 0.142.2 · uvicorn 0.54.0 · SQLAlchemy 2.1.1 · psycopg2-binary 2.9.13
pydantic 2.13.5 · pydantic-settings 2.15.0 · python-dotenv 1.2.3
PyJWT 2.15.1 · httpx 0.28.1
```

`backend/requirements.txt` queda con diez líneas, todas con `==`:

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

```text
pip install -r requirements.txt  → prometheus-client 0.26.0 instalado
pip check                        → No broken requirements found.
pytest tests/test_dependencias_024.py -q → 4 passed
```

No hay dependencias directas nuevas fuera de `prometheus-client`.

## 3. Configuración, correlación y logging (T2/T3)

Variables nuevas en `backend/app/core/config.py` y en el servicio `backend` del compose:

| Variable | Default | Efecto |
|---|---|---|
| `ALLOWED_ORIGINS` | `http://localhost:4200,http://localhost:8080` | Orígenes CORS con credenciales. Lista vacía impide el arranque. |
| `LOG_LEVEL` | `INFO` | Nivel del logger de la aplicación. |
| `LOG_FORMAT` | `json` | `json` (una línea por petición) o `text` legible. Desconocido cae a `json`. |

- `X-Request-ID` en toda respuesta; UUID entrante válido se respeta, cualquier otro valor se
  sustituye por un UUID4.
- La plantilla de ruta se reconstruye tras el anidado de routers de FastAPI 0.142
  (`/api/v1/tickets/{ticket_id}`), sin query string ni id real.
- El log de acceso propio sustituye al de uvicorn: `--no-access-log` en `backend/Dockerfile`
  y en el comando del compose.

Muestra real (recortada, sin datos personales):

```json
{"timestamp": "2026-11-15T03:13:59.383956+00:00", "level": "INFO", "logger": "compustock.acceso", "message": "peticion_completada", "request_id": "c62fc14f-9c3a-46bc-86a8-543f779db8c7", "method": "GET", "path": "/ready", "status": 200, "duration_ms": 37.37}
{"timestamp": "2026-11-15T03:13:27.236964+00:00", "level": "WARNING", "logger": "compustock.salud", "message": "readiness_fallida", "request_id": "2c02461f-8188-42f1-93f8-b93cc3754152", "error_type": "OperationalError"}
```

Auditoría de `docker compose logs backend` sobre 30 minutos / 244 líneas de acceso:

```text
Bearer=0 · bearer=0 · token=0 · @example.com=0 · password=0 · secret=0 · sk_=0 · dvb_=0
líneas de access log de uvicorn = 0
líneas JSON de acceso = 244
```

Una petición a `/health` con `X-Request-ID` `0786b5e1-…` produjo **una sola** línea JSON
(AC-7).

## 4. Salud y métricas (T5–T7)

| Comprobación | Resultado |
|---|---|
| `/health` con `db` arriba y detenido | 200 `{"status":"healthy"}` en ambos; sin Bearer; en OpenAPI sin `security`. |
| `/ready` con `db` arriba | 200 `{"status":"ready"}` (≈38 ms). |
| `/ready` con `db` detenido | 503 `{"status":"not_ready"}`; el cuerpo no contiene `psycopg2`, `connection`, `postgres` ni `apt_erp`; el fallo queda en el log con su `request_id`. |
| `/ready` con host que no responde (`192.0.2.1`) | 503 en **1.02 s / 1.01 s / 1.02 s** por HTTP real (uvicorn temporal en 8001); TestClient: 1.23 s / 1.01 s / 1.01 s. |
| `/metrics` | 200 sin `Authorization`, cinco familias, `route` como plantilla, ruta desconocida bajo valor reservado, sin autoinstrumentación. |
| `/openapi.json` | **75** operaciones; sin `/metrics` ni `/ready`; `/health` sigue documentado. |
| `MATRIZ_PERMISOS` | **73** operaciones; ninguna entrada operativa. |

`/metrics` no se proxifica: `http://localhost:8080/metrics` y `/metrics/` responden **404**
sin `# HELP` ni `compustock_`.

## 5. Camino real en 4200 (T11)

- `npm start` con `frontend/proxy.conf.json`: 59 peticiones same-origin a
  `http://localhost:4200/api/v1/*`, sin preflight y sin 4xx/5xx.
- Recorrido: login Clerk (`bodeguero.test+clerk_test@example.com`, código `424242`),
  dashboard, tablero, detalle de pedido #5, inventario y recepción de compras.
- `X-Request-ID` presente en las respuestas; consola sin errores nuevos.
- Ráfaga de 60 `fetch` same-origin: **60×401** (sin Bearer) y **0×429** (el dev server no es
  el borde).
- `ng test`: **549 SUCCESS**. `ng build`: limpio (29.3 s), sin `localhost:8000` como URL base.

## 6. Borde nginx en 8080 (T9/T12)

Imagen reconstruida (`docker compose build frontend` + `up -d frontend`). La SPA consume
`http://localhost:8080/api/v1/*` por nginx: `/api/v1/auth/me` → 401 JSON,
`/api/v1/dashboard/` → 200 y el estático `main-2MM7TE6C.js` → 200.

| Prueba | Resultado |
|---|---|
| Recarga normal | 34 peticiones, todas 200/307/204, **0×429**. |
| Ráfaga desde la consola del navegador | **30×401 + 30×429**, 429 con `Content-Type` JSON y `detail`. |
| Ráfaga `httpx` con `Origin: http://evil.example` | **20×401 + 40×429**; los 429 con `Access-Control-Allow-Origin: http://evil.example` y `Vary: Origin`; las respuestas normales sin ACAO. |
| Estáticos | 200, sin límite. |
| `8080/metrics` | 404, sin métricas. |

Cuerpo exacto del 429:

```json
{"detail":"Demasiadas peticiones. Intente nuevamente en unos segundos."}
```

Configuración: `limit_req_zone` 10 r/s, `burst=20 nodelay`, `limit_conn` 20,
`limit_req_status 429`, `limit_conn_status 429` y `error_page 429 = @limite_api`.

## 7. Cierre de suites y contrato (T10/T13)

| Comprobación | Resultado |
|---|---|
| `pytest -q` final | **1596 passed / 88 skipped / 0 failed** (238.87 s). |
| Gated PostgreSQL 16 (`POSTGRES_TEST_URL`) | **73 passed** en los 19 archivos `*postgres*.py` (522.55 s). |
| `ng test` | **549 SUCCESS**. |
| `ng build` | limpio. |
| `pip check` | sin conflictos. |
| Contrato | **75** OpenAPI / **73** matriz. |
| Esquema | `021.1`; **27** tablas de `control` + **24** por tenant. |
| Áreas protegidas | sin cambios en `database/`, `models/**`, `permisos.py`, `capacidades.py`, templates ni `.env`. |
| `frontend/src/**` | único cambio: `shared/config/url-api.ts`. |

## 8. Hallazgos y decisiones de cierre

1. **La imagen del backend necesitó rebuild.** El contenedor quedó *unhealthy* con
   `ModuleNotFoundError: No module named 'prometheus_client'` porque la imagen no tenía la
   dependencia nueva. `docker compose build backend` + `up -d backend` → healthy.
2. **`/ready` con el contenedor `db` detenido tarda 3–7 s.** El retraso es
   `getaddrinfo('db', 5432)` del DNS de Docker Desktop (hasta 7.15 s); `connect_timeout` no
   cubre la resolución de nombres. AC-9 solo exige 503 y se cumple; AC-10 se midió con un
   host que no responde y quedó en ≈1 s. Se documenta como hallazgo, sin deadline por hilo.
3. **Ajuste de timeouts dentro de la contingencia del plan.** `connect_timeout` bajó de 2 a
   **1 s** y `statement_timeout` de 2000 a **1500 ms** en `opciones_motor_readiness` para
   cumplir AC-10 con margen. El valor de 1 s se respeta (≈1.02 s), no se recorta a 2 s.
4. **Deuda de pruebas gated descubierta al ejecutarlas.** `test_instalacion_limpia_postgres.py`
   y `test_ciclo_vida_catalogo_postgres_014.py` congelaban 26/23 tablas y `020.1` desde la
   Feature 020; la 021 añadió `orden_compra_ticket` y subió a `021.1` sin actualizarlos
   (7 fallos preexistentes). Se actualizaron los snapshots a **27/24** y **021.1** y los
   nombres de los tests, sin tocar producción. Resultado: **73 passed**.
5. **`opencode.json`** sigue modificado por la configuración de modelos de la sesión; no forma
   parte de la feature.

## 9. Reproducción

```powershell
# Backend + gated
cd backend
.venv/Scripts/python.exe -m pytest -q
$env:POSTGRES_TEST_URL = "postgresql://postgres:postgres@localhost:5433/postgres"
.venv/Scripts/python.exe -m pytest -q (Get-ChildItem tests -Filter "*postgres*.py" | % { "tests/" + $_.Name })

# Frontend
cd ..\frontend
$env:CHROME_BIN = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
npx ng test --watch=false --browsers=ChromeHeadless
npx ng build

# Borde
docker compose -f docker-compose.yml build frontend
docker compose -f docker-compose.yml up -d frontend
curl.exe -s -o NUL -w "%{http_code}" http://localhost:8080/metrics   # 404
```
