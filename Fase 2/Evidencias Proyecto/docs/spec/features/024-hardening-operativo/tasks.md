# Tareas — Feature 024: Hardening operativo I

**Feature:** `024-hardening-operativo/`
**Spec:** [spec.md](spec.md) · **Plan:** [plan.md](plan.md)
**Regla:** cada tarea deja la suite en verde; bajo `frontend/src/**` solo cambia `url-api.ts`.

## T1 — Línea base, dependencias y evidencia inicial

**ACs:** AC-22, AC-24 (línea base).

- [x] Correr `pytest` completo y registrar la línea base (**1502 passed/88 skipped/0 failed**).
- [x] Correr `ng test` con `CHROME_BIN` y confirmar **549 SUCCESS**.
- [x] Confirmar con `pip show` las nueve versiones instaladas de D-8.
- [x] Reescribir `backend/requirements.txt` con las diez dependencias y `==` (D-8 + `prometheus-client==0.26.0`).
- [x] Instalar `-r requirements.txt` en el venv y ejecutar `pip check` sin conflictos.
- [x] Crear `backend/tests/test_dependencias_024.py` (diez líneas, todas `==`, conjunto de versiones).
- [x] Crear `docs/spec/features/024-hardening-operativo/evidencia/README.md` con la línea base.

**Hecho cuando:** el test de dependencias pasa, `pip check` está limpio y no cambió ninguna versión existente fuera del pineo.

## T2 — Configuración por entorno

**ACs:** AC-6 (configuración), AC-17 (fail-fast).

- [x] Añadir `VERSION_APLICACION = "1.0.0"` a `backend/app/core/config.py`.
- [x] Añadir `ALLOWED_ORIGINS`, `LOG_LEVEL` y `LOG_FORMAT` con los defaults de D-6.
- [x] Implementar `validar_origenes` (trim, descarte de vacíos, error si queda vacío) y `origenes_permitidos`.
- [x] Escribir `backend/tests/test_configuracion_024.py` con defaults, recorte, lista vacía y variables desconocidas.
- [x] Ejecutar los tests focalizados de configuración.

**Hecho cuando:** `Settings()` trae los dos orígenes locales, `ALLOWED_ORIGINS=""` impide construir con un mensaje que nombra la variable y los valores de log desconocidos no rompen.

## T3 — Logging estructurado

**ACs:** AC-4, AC-5, AC-6.

- [x] Crear `backend/app/core/observabilidad.py` con `ContextVar`, regex UUID canónico, resolutores de formato/nivel y nivel por estado.
- [x] Implementar `FormateadorJSON` con los nueve campos de R-2.1 y lista blanca de campos adicionales.
- [x] Implementar `FormateadorTexto` legible y no JSON.
- [x] Implementar `configurar_registro` idempotente sobre el logger `compustock`, sin tocar uvicorn.
- [x] Añadir a `test_configuracion_024.py` los casos de JSON, texto, niveles y `LOG_LEVEL=WARNING`.
- [x] Verificar que una línea con token, correo y query string no contiene ninguno de los tres.

**Hecho cuando:** el JSON se parsea con los nueve campos, `text` no es JSON válido, `WARNING` filtra INFO y no aparece PII.

## T4 — App factory, X-Request-ID y manejador 500

**ACs:** AC-1, AC-2, AC-3, AC-8 (health intacto).

- [x] Refactorizar `backend/app/main.py` a `crear_app()` conservando el CORS actual y `app = crear_app()`.
- [x] Crear `backend/app/middleware/observabilidad.py` como middleware ASGI puro.
- [x] Asignar `X-Request-ID` en `scope["state"]` y `ContextVar`; resetear en `finally`.
- [x] Inyectar la cabecera en `http.response.start`; usar plantilla de ruta o `unmatched`.
- [x] Registrar una línea de acceso por petición con método, path, status y duración.
- [x] Añadir el manejador de `Exception` con cuerpo `Internal Server Error` y `X-Request-ID`.
- [x] Escribir `backend/tests/api/test_correlacion_024.py` (éxitos, 4xx, 404, 500, UUID entrante, dos peticiones, PII).
- [x] Confirmar que `/health` sigue devolviendo `{"status":"healthy"}`.

**Hecho cuando:** toda respuesta de las rutas probadas lleva UUID canónico, el UUID válido se respeta, no hay fuga entre peticiones y el 500 conserva su cuerpo.

## T5 — CORS por entorno y sin comodines

**ACs:** AC-17, AC-18.

- [x] Crear `backend/app/core/cors.py` con `CORSEstricto` (recorte de `Access-Control-Allow-Headers`).
- [x] Cablear `CORSEstricto` en `crear_app()` con orígenes, métodos y cabeceras de D-6.
- [x] Añadir la guarda de arranque para una lista de orígenes vacía.
- [x] Escribir `backend/tests/api/test_cors_024.py` (default, ajeno, entorno alterno, vacío, preflight).
- [x] Verificar que métodos y cabeceras del preflight son exactamente los declarados y que no hay `*`.

**Hecho cuando:** el default permite 4200/8080, el origen ajeno no recibe ACAO, el entorno alterno se aplica y el preflight devuelve las listas exactas.

## T6 — `/health` y `/ready`

**ACs:** AC-8, AC-9, AC-10.

- [x] Añadir `crear_motor_readiness` y `motor_readiness` en `backend/app/db/database.py` (`NullPool`, timeout y statement timeout).
- [x] Crear `backend/app/services/salud_service.py` con `comprobar_conectividad` usando `select(literal(1))`.
- [x] Añadir `obtener_motor_readiness` en `backend/app/api/dependencies.py`.
- [x] Crear `backend/app/api/operativo.py` con `/ready` fuera de OpenAPI (`/metrics` se añade en T7).
- [x] Incluir `router_operativo` en `crear_app()`.
- [x] Añadir el override de `obtener_motor_readiness` en `backend/tests/conftest.py`.
- [x] Escribir `backend/tests/api/test_salud_024.py` (200, 503 saneado, log correlacionado, `/health` sin base, timeout configurado).

**Hecho cuando:** `/ready` responde 200 con SQLite y 503 sin detalle con un motor caído; `/health` sigue 200 y documentado; ninguna de las dos rutas operativas entra en OpenAPI.

## T7 — Métricas y `/metrics`

**ACs:** AC-11, AC-12, AC-13, AC-14, AC-15, AC-16.

- [x] Crear `backend/app/core/metricas.py` con registro propio, cinco familias y `RUTA_NO_RESUELTA`.
- [x] Instrumentar el middleware: contador, histograma, gauge en vuelo y errores; omitir `/metrics`.
- [x] Exponer `/metrics` con `generate_latest` y `CONTENT_TYPE_LATEST`.
- [x] Escribir `backend/tests/soporte_observabilidad_024.py` (parser, lector de series, fake de motor).
- [x] Escribir `backend/tests/api/test_metricas_024.py` (cinco familias, etiquetas, plantilla, ruta desconocida, no autoinstrumentación, app_info).
- [x] Escribir `backend/tests/api/test_contrato_024.py` (75/73, `/metrics` y `/ready` fuera, `/health` sin security).

**Hecho cuando:** las cinco familias se parsean, la etiqueta `route` es plantilla, `/metrics` no se cuenta a sí mismo, no hay datos sensibles y el contrato sigue en 75/73.

## T8 — B8: URL relativa y proxy de desarrollo

**ACs:** AC-23 (solo `url-api.ts`), AC-27.

- [x] Cambiar `URL_API` a `/api/v1` en `frontend/src/app/shared/config/url-api.ts`.
- [x] Crear `frontend/proxy.conf.json` con el proxy `/api` a `http://localhost:8000`.
- [x] Declarar `proxyConfig` en `projects.frontend-app.architect.serve.options` de `frontend/angular.json`.
- [x] Verificar que `localhost:8000` no aparece como URL base bajo `frontend/src/`.
- [x] Ejecutar `ng test` y confirmar **549 SUCCESS** sin tocar specs.
- [x] Ejecutar `ng build` y buscar `localhost:8000` en el bundle de producción.

**Hecho cuando:** la SPA usa `/api/v1`, el proxy está declarado, la suite sigue en 549 y el build no contiene la URL absoluta.

## T9 — Borde nginx y arranque sin access log

**ACs:** AC-7, AC-19/20/21 (configuración), AC-25 (despliegue).

- [x] Añadir `limit_req_zone` y `limit_conn_zone` al inicio de `frontend/nginx.conf`.
- [x] Añadir `limit_req`, `limit_conn`, `limit_*_status 429` y `error_page 429` en `/api/`.
- [x] Crear la respuesta `@limite_api` JSON con `detail` y ACAO solo en el 429.
- [x] Bloquear `location = /metrics` con 404.
- [x] Añadir `--no-access-log` a `docker-compose.yml` y `backend/Dockerfile`.
- [x] Añadir `ALLOWED_ORIGINS`, `LOG_LEVEL` y `LOG_FORMAT` al servicio backend del compose.
- [x] Validar `docker compose config` y la sintaxis de nginx.

**Hecho cuando:** nginx valida, `/api/` tiene límites, `/metrics` está negado, el 429 es JSON y uvicorn arranca sin access log en ambos comandos.

## T10 — Verificación backend, contrato y áreas protegidas

**ACs:** AC-15, AC-22, AC-23, AC-24.

- [x] Ejecutar `pytest` completo y confirmar 0 fallos y 88 skipped. → **1596 passed/88 skipped/0 failed**.
- [x] Ejecutar `pip check`. → sin conflictos.
- [x] Ejecutar los tests gated de PostgreSQL 16 si `POSTGRES_TEST_URL` está disponible. → **no ejecutados**: la variable no está definida en la sesión.
- [x] Verificar `/openapi.json`: 75 operaciones, sin `/metrics` ni `/ready`, `/health` sin security. → 75/73, ambas rutas fuera.
- [x] Verificar `MATRIZ_PERMISOS`: 73 operaciones y ninguna ruta operativa. → 73, sin `/ready` ni `/metrics`.
- [x] Confirmar `021.1` y 27/24 tablas. → `VERSION_ESQUEMA_OBJETIVO=021.1`; 27 `CREATE TABLE control.*` + 24 plantillas de tenant.
- [x] Revisar `git diff --stat` de las áreas protegidas y de `frontend/src/**`. → solo `frontend/src/app/shared/config/url-api.ts` bajo `frontend/src`; sin cambios en `models`, `permisos.py`, `capacidades.py` ni `database/`.

**Hecho cuando:** la suite está en verde, los conteos son 75/73, la versión y las tablas no cambian y el diff protegido no tiene sorpresas.

## T11 — Recorrido funcional en 4200

**ACs:** AC-25, AC-27.

- [x] Levantar el backend y `npm start` con el proxy activo. → backend reconstruido (faltaba `prometheus-client` en la imagen) y `ng serve` en 4200.
- [x] Recorrer login, dashboard, pedidos, inventario y compras. → logout + tarjeta Clerk `bodeguero.test+clerk_test@example.com` (código `424242`), dashboard, tablero, detalle #5, inventario y recepción de compras.
- [x] Confirmar en la pestaña de red peticiones a `http://localhost:4200/api/v1/*`, sin CORS. → 59 peticiones, todas same-origin y sin preflight; el ACAO `*` del proxy es de Vite, no del backend (8000 no lo emite sin `Origin` y solo refleja 4200/8080).
- [x] Confirmar `X-Request-ID` en las respuestas y ausencia de errores nuevos de consola. → UUID presente en `/api/v1/inventario/existencias`; consola solo con el aviso de claves dev de Clerk y un hint del formulario prebuilt.
- [x] Confirmar que en 4200 no se espera 429 (el dev server no es el borde). → 60 `fetch` same-origin: 60×401 (sin Bearer) y **0×429**.
- [x] Ejecutar `ng test` y `ng build` de cierre. → **549 SUCCESS**, build limpio (29.3 s).

**Hecho cuando:** el recorrido se completa por el proxy, la red muestra 4200/api/v1, no hay CORS ni 429, y `ng test` sigue en 549.

## T12 — Rebuild, humo y borde en 8080

**ACs:** AC-7, AC-9, AC-10, AC-19, AC-20, AC-21, AC-25.

- [x] Reconstruir la imagen: `docker compose build frontend` y `up -d frontend`. → build correcto y contenedor recreado.
- [x] Confirmar que la SPA consume `http://localhost:8080/api/v1/*` por nginx. → `/api/v1/auth/me` 401 JSON, `/api/v1/dashboard/` 200 y estático `main-2MM7TE6C.js` 200, todo same-origin en 8080.
- [x] Verificar carga normal (una recarga, ≈15 peticiones) sin 429 y estáticos sin 429. → recarga final: 34 peticiones, todas 200/307/204, **0×429**.
- [x] Disparar ≥60 `fetch` same-origin desde la consola y confirmar al menos un 429 JSON con `detail`. → 30×401 + 30×429; los 429 con `detail` legible.
- [x] Confirmar `8080/metrics` sin `# HELP` ni `compustock_`. → 404, sin cuerpo de métricas.
- [x] Provocar un 429 con `Origin` ajeno por `curl` y confirmar ACAO solo en esa respuesta. → ráfaga `httpx` con `Origin: http://evil.example`: 20×401 + 40×429; los 429 con `ACAO: http://evil.example` y `Vary: Origin`; las respuestas normales sin ACAO.
- [x] Confirmar `/ready` 200 con `db` arriba, 503 con `db` detenido y `/health` 200 en ambos. → 200 / 503 `{"status":"not_ready"}` sin filtrar detalles internos / 200 en ambos escenarios.
- [x] Medir `/ready` con un host inalcanzable y confirmar ≤2 s. → 3 medidas por HTTP real en un uvicorn temporal con `DB_HOST=192.0.2.1`: 503 en 1.02 s, 1.01 s y 1.02 s.
- [x] Revisar `docker compose logs backend`: una línea JSON por petición, sin token ni correo. → 244 líneas JSON de acceso, 0 líneas de access log de uvicorn, 0 coincidencias de `Bearer`/`token`/`@example.com`/`password`/`secret`.

**Hecho cuando:** el humo de 8080 pasa, el 429 es visible y legible, `/metrics` no se publica, `/ready` distingue los estados y el log no duplica.

## T13 — Cierre documental, evidencia y commit

**ACs:** AC-23 (diff final), AC-24 (suite final), AC-26.

- [x] Documentar en `docs/spec/stack.md` la frontera operativa, logs, CORS, borde y API por mismo origen. → nueva sección §1.1.
- [x] Completar `evidencia/README.md` con suites, conteos, logs redactados, respuestas operativas, 4200/8080, 429 y diff protegido. → 9 secciones con tablas y muestras.
- [x] Actualizar `MEMORY.md` (estado, decisiones y siguiente trabajo). → 024 cerrada y 025 como siguiente.
- [x] Marcar `spec.md` §6 AC por AC con su evidencia. → **27/27** AC marcados.
- [x] Marcar `roadmap.md` con la 024 en `[x]` y fecha de cierre. → 15/Nov/2026 en la lista y en el índice.
- [x] Ejecutar el `grep` de coherencia sobre `AGENTS.md`, `MEMORY.md` y `.agents/skills/`; corregir rutas o afirmaciones obsoletas. → sin `localhost:8000` ni referencias a la 024 pendiente; las skills ya usan `/api/v1` relativo.
- [x] Revisar `git diff --stat` final y confirmar que no hay archivos fuera de alcance. → solo la feature + `opencode.json` (configuración de modelos, va en commit aparte).
- [x] Commit de la 024. → commit `feat(024): hardening operativo con observabilidad, CORS y borde nginx` (ver `git log`).

**Hecho cuando:** `tasks.md` está completo, `spec.md` tiene todos los AC con evidencia, `roadmap.md` está en `[x]`, la documentación no cita `localhost:8000` como URL de la SPA y el commit contiene solo los archivos de la feature.
