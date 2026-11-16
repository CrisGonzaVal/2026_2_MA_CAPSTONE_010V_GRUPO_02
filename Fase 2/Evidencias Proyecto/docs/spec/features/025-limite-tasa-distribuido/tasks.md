# Tareas — Feature 025: Límite de tasa distribuido

**Feature:** `025-limite-tasa-distribuido/`
**Spec:** [spec.md](spec.md) · **Plan:** [plan.md](plan.md)
**Regla:** cada tarea deja la suite en verde; no se toca `frontend/`, `database/`, modelos, permisos, esquemas ni contratos.

## T1 — Línea base, `redis==8.1.0` y dependencias

**ACs:** AC-22, AC-17 (11 líneas), AC-18 (línea base).

- [x] Correr `pytest` completo desde el host y registrar la línea base (**1596 passed/88 skipped/0 failed**). → 531,89 s.
- [x] Correr `ng test` con `CHROME_BIN` y confirmar **549 SUCCESS**. → 21,119 s.
- [x] Confirmar con `pip show` el estado actual de `redis` (no debe figurar como dependencia directa) y que las diez dependencias actuales conservan su versión. → *Package(s) not found*.
- [x] Añadir `redis==8.1.0` como undécima línea de `backend/requirements.txt`. → hecho.
- [x] Instalar `-r requirements.txt` en el venv y ejecutar `pip check` sin conflictos. → `Successfully installed redis-8.1.0`; `No broken requirements found.`
- [x] Actualizar `backend/tests/test_dependencias_024.py` a once dependencias, incluyendo `redis==8.1.0`, conservando su intención. → hecho.
- [x] Crear `docs/spec/features/025-limite-tasa-distribuido/evidencia/README.md` con la línea base y el estado del árbol. → hecho.
- [x] Ejecutar el test de dependencias y confirmar 11/11. → **4 passed** con 11 dependencias declaradas.

**Hecho cuando:** `pytest` sigue en 1596/88/0 antes de tocar código, `pip check` está limpio y la prueba de dependencias pasa con once líneas pineadas.

## T2 — Configuración por entorno

**ACs:** AC-14.

- [x] Añadir `REDIS_URL`, `LIMITE_TASA_HABILITADO`, `LIMITE_TASA_MAX_PETICIONES`, `LIMITE_TASA_VENTANA_SEGUNDOS` y `LIMITE_TASA_CONFIAR_PROXY` a `backend/app/core/config.py` con los defaults de D-8. → hecho.
- [x] Implementar `validar_limite_positivo` para máximo y ventana (enteros ≥ 1). → hecho.
- [x] Implementar `validar_url_redis` con `model_validator(mode="after")`, solo activo con el limitador encendido. → hecho.
- [x] Escribir `backend/tests/test_configuracion_025.py` con defaults (limpiando las cinco variables de entorno), cuatro casos inválidos, `rediss://` y apagado con URL no Redis. → 11 pruebas.
- [x] Ejecutar los tests focalizados de configuración. → **58 passed** (11 nuevas + 47 de la 024).

**Hecho cuando:** `Settings()` trae `True/120/60/False/redis://127.0.0.1:6380/0`, los valores inválidos impiden construir con un mensaje que nombra la variable y la suite heredada sigue verde.

## T3 — Núcleo: script Lua, IP y almacén

**ACs:** AC-5, AC-6.

- [x] Crear `backend/app/core/limite_tasa.py` con `LIMITE_PREFIJO_CLAVE`, `TEXTO_LIMITE`, `IP_RESERVADA`, `TIEMPO_MAXIMO_EVALUACION` y `SCRIPT_LUA`. → hecho.
- [x] Implementar `resolver_ip` (par TCP por defecto, `X-Real-IP` validada con `ipaddress` solo con confianza, `X-Forwarded-For` nunca, `IP_RESERVADA` sin par). → hecho.
- [x] Implementar `es_ruta_limitada` por segmento y `es_preflight` (método, `Origin` y `Access-Control-Request-Method`). → hecho.
- [x] Definir el protocolo `AlmacenLimite` e implementar `AlmacenRedis` con `redis.asyncio`, cliente creado en la primera evaluación, timeouts de 200 ms, pool de 20 y cero reintentos. → `from_url` **no** acepta `timeout` en 8.1.0; la cota del *pool* queda en `asyncio.wait_for(0.5)`, corregido en T8.
- [x] Implementar `ResultadoLimite` y `LimitadorTasa.evaluar` con la clave por IP, el contador y el reinicio derivado del TTL. → incluye la métrica best-effort; la familia se creó aquí y T6 la verifica.
- [x] Escribir `backend/tests/soporte_limite_tasa_025.py` con `AlmacenFalso` (reloj propio, `avanzar`, `error`, `llamadas` y `cerrar` no-op) y las fábricas de app. → hecho.
- [x] Escribir `backend/tests/test_limite_tasa_unidad_025.py` con IP, rutas, preflight, conteo, no renovación del TTL y clave con prefijo. → 30 pruebas.
- [x] Ejecutar los tests unitarios focalizados. → **30 passed**.

**Hecho cuando:** la IP se resuelve según la confianza, el preflight y las rutas operativas quedan fuera, y el falso reproduce el conteo y la expiración sin Docker.

## T4 — Middleware, alcance y contrato del 429

**ACs:** AC-2, AC-3, AC-7, AC-8, AC-14 (apagado), AC-15.

- [x] Crear `backend/app/middleware/limite_tasa.py` como ASGI puro que filtra `/api/v1`, omite el preflight y emite el 429. → hecho.
- [x] Añadir `rate_limited` a `scope["state"]` en el rechazo. → hecho.
- [x] Emitir el 429 JSON con `detail`, `Retry-After`, `X-RateLimit-Limit`, `X-RateLimit-Remaining: 0` y `X-RateLimit-Reset`. → hecho.
- [x] Extender `crear_app(cliente_limite=None)` para construir el limitador y añadirlo **antes** de CORS y observabilidad; registrar `cerrar` en el `shutdown`. → FastAPI 0.142 ya no expone `add_event_handler` en la app: se usa `aplicacion.router.add_event_handler`.
- [x] Apagar el limitador en `backend/tests/conftest.py` antes de importar `app.main`, mutando el singleton. → hecho.
- [x] Añadir la marca `rate_limited` a `_ruta_plantilla` en `backend/app/middleware/observabilidad.py`. → hecho.
- [x] Escribir `backend/tests/api/test_limite_tasa_025.py` (conteo, cabeceras, CORS, dos IP, confianza, rutas fuera, preflight, dos apps con el mismo falso). → 11 pruebas.
- [x] Confirmar que un `POST` a `/api/v1` consume presupuesto igual que un `GET`. → 405 contado, después 429.
- [x] Confirmar que con `LIMITE_TASA_HABILITADO=false` no hay middleware y el falso no recibe llamadas. → hecho.
- [x] Ejecutar los tests de API focalizados. → **11 passed**; **138 passed** con las suites heredadas (024 + auth).

**Hecho cuando:** el 429 respeta el contrato, el preflight no consume presupuesto, las rutas operativas no se limitan, el límite corre antes de Clerk y dos apps comparten el contador.

## T5 — Fail-open

**ACs:** AC-9, AC-10, AC-11.

- [x] Envolver el paso por Redis de `LimitadorTasa.evaluar` en `try/except Exception` con `asyncio.wait_for` de 0,5 s y devolver `permitida=True` con `resultado="error"`. → hecho.
- [x] Añadir `LOGGER_LIMITE = "compustock.limite"` a `backend/app/core/observabilidad.py`. → hecho.
- [x] Implementar el aviso acotado a uno cada 10 s, con `request_id` y `error_type`, sin IP, host, mensaje ni traza. → `intervalo_aviso` configurable; `_ultimo_aviso` nace en `-inf`.
- [x] Escribir `backend/tests/api/test_limite_tasa_failopen_025.py` con falso que lanza, captura de log, métrica `error`, medición de cota con `192.0.2.1` y `/ready` 200 sin llamar al almacén. → 3 pruebas.
- [x] Ejecutar los tests de fail-open focalizados. → **3 passed**; **44 passed** con T3 y T4.

**Hecho cuando:** un fallo del limitador nunca cambia el estado ni el cuerpo de la ruta, la métrica cuenta todos los fallos y el log avisa una sola vez por ventana.

## T6 — Métricas y ruta reservada

**ACs:** AC-12, AC-13.

- [x] Añadir `RUTA_LIMITADA = "rate_limited"` a `backend/app/core/metricas.py`. → hecho.
- [x] Añadir `compustock_rate_limit_requests_total{resultado}` y `registrar_limite`. → creados en T3 (el limitador los consume) y verificados aquí.
- [x] Incrementar la familia con `permitida`, `limitada` y `error` en el limitador. → hecho.
- [x] Escribir `backend/tests/api/test_metricas_limite_tasa_025.py` (incrementos, etiqueta exacta, cinco familias de la 024, `route="rate_limited"`, sin PII y apagado). → 6 pruebas.
- [x] Ejecutar los tests de métricas focalizados. → **6 passed**.

**Hecho cuando:** `/metrics` expone seis familias, la etiqueta nueva es exactamente `{resultado}`, el 429 se registra como `rate_limited` y ninguna superficie contiene la IP ni la clave.

## T7 — Servicio Redis en Compose

**ACs:** AC-1.

- [x] Añadir el servicio `redis` con `redis:7.2-alpine`, `container_name: compustock_redis`, `restart: unless-stopped` y healthcheck `redis-cli ping`. → hecho.
- [x] Configurar `--save ""`, `--appendonly no`, `--maxmemory 64mb` y `--maxmemory-policy allkeys-lru` en forma de lista. → hecho.
- [x] Publicar el puerto solo en `127.0.0.1:${REDIS_PORT:-6380}:6379`, sin volúmenes y con `/data` en un tmpfs de 64 MB (la imagen declara `VOLUME /data`). → hecho.
- [x] Añadir `REDIS_URL` y las cuatro variables `LIMITE_TASA_*` al servicio `backend`, con `LIMITE_TASA_CONFIAR_PROXY=true`. → hecho; el backend se recrea en T11 para tomarlas.
- [x] Confirmar que el backend **no** declara `depends_on` hacia Redis. → solo depende de `db`.
- [x] Validar `docker compose config` y levantar el servicio. → `config OK`; `compustock_redis` arriba.
- [x] Verificar `PONG`, `maxmemory`, `maxmemory-policy`, `save`, `appendonly`, el tmpfs de `/data`, la ausencia de volúmenes y el mapeo de puertos. → `PONG`; `67108864`; `allkeys-lru`; `save` vacío; `appendonly no`; tmpfs `/data:size=64m`; `Mounts []`; `127.0.0.1:6380->6379/tcp`; Redis **7.2.17**; *healthy*.

**Hecho cuando:** `docker compose config` valida, `compustock_redis` queda *healthy*, es efímero y escucha solo en loopback.

## T8 — Pruebas gated contra Redis real

**ACs:** AC-4, AC-16.

- [x] Crear `backend/tests/test_limite_tasa_redis_025.py` con omisión limpia si falta `REDIS_TEST_URL`. → 3 pruebas; **3 skipped** sin la variable.
- [x] Implementar los escenarios con `asyncio.run` (sin `pytest-asyncio`). → hecho.
- [x] Verificar 3 permitidas y cuarta rechazada con ventana de 1 s, `PTTL` entre 1 y 1000 ms y clave con la IP. → hecho.
- [x] Verificar reinicio por `DEL`, por expiración, que los rechazos no renuevan el TTL y que `Retry-After` decrece con el TTL. → hecho.
- [x] Verificar 20 evaluaciones concurrentes con máximo 10 → 10 permitidas y 10 rechazadas. → hecho.
- [x] Vaciar la base 15 al empezar y al terminar. → `flushdb()` en `finally`; nunca toca la base 0.
- [x] Ejecutar la suite gated con `REDIS_TEST_URL=redis://127.0.0.1:6380/15` y comprobar la omisión sin la variable. → **3 passed**; **3 skipped** sin la variable.

**Desvío corregido en T8.** Dos hallazgos contra las versiones reales: (1) `Redis.from_url(timeout=0.2)` **no** es válido en redis-py 8.1.0 — ese nombre viaja al constructor de la conexión y lanza `TypeError`; se eliminó y la cota del *pool* queda en el `asyncio.wait_for(0.5)` de `evaluar`, con `socket_connect_timeout`/`socket_timeout` de 0,2 s. (2) El puerto de Compose se publica solo en IPv4 (`127.0.0.1`) y en Windows `localhost` resuelve primero `::1`, donde la conexión se cuelga hasta agotar el timeout; el default y los comandos pasan a `127.0.0.1:6380` (mismo loopback, sin cambiar el alcance).

**Hecho cuando:** la semántica real del script y del TTL queda verificada y la suite se omite limpiamente cuando no hay Redis de prueba.

## T9 — Verificación backend, contrato y áreas protegidas

**ACs:** AC-17, AC-18.

- [x] Ejecutar `pytest` completo con `REDIS_TEST_URL=redis://127.0.0.1:6380/15` y confirmar 0 fallos y 88 skipped. → **1660 passed / 88 skipped / 0 failed** (326,02 s; +64 pruebas nuevas sobre la línea base de 1596).
- [x] Ejecutar `pip check`. → `No broken requirements found.`
- [x] Ejecutar los tests gated de PostgreSQL 16 con `POSTGRES_TEST_URL` y confirmar 73 passed. → **73 passed** en los 16 archivos `*postgres*.py` (354,82 s).
- [x] Verificar `/openapi.json`: 75 operaciones y ninguna ruta nueva. → **75 operaciones** con uvicorn temporal en 8011.
- [x] Verificar `MATRIZ_PERMISOS`: 73 operaciones. → **73**.
- [x] Confirmar versión `021.1` y tablas 27/24. → `021.1`; **27** en `control` y **24** en cada uno de los 4 tenants.
- [x] Revisar `git diff --stat` de áreas protegidas y de `frontend/`. → **sin cambios** en `frontend/`, `database/`, `models/`, `services/` ni `api/`.
- [x] Confirmar `requirements.txt` con 11 líneas, todas `==`. → 11 líneas, todas `==`, incluida `redis==8.1.0`.

**Hecho cuando:** la suite está en verde, los conteos son 75/73, la versión y las tablas no cambian y el diff protegido no tiene sorpresas.

## T10 — Recorrido funcional en 4200

**ACs:** AC-19 (4200).

- [x] Levantar backend y `npm start` con el proxy activo. → host uvicorn en `::1:8000` con el `.env` raíz (Clerk) y `DB_HOST=127.0.0.1`/`DB_PORT=5433`; dev server existente en 4200 con `proxy.conf.json`.
- [x] Recorrer login, dashboard, pedidos, inventario, compras y administración. → Bodeguero: dashboard, tablero, detalle #5, inventario y recepción (11×200). Administrador (`admin020.test+clerk_test@example.com`): dashboard, inventario con gestión, compras/necesidades, órdenes de compra, pedidos y administración/sedes (13×200).
- [x] Confirmar peticiones a `http://localhost:4200/api/v1/*`, sin CORS. → todas same-origin por el proxy; **0 preflight**.
- [x] Contar las peticiones del recorrido completo (referencia de la 024: 59) y confirmar **0×429**. → **24 peticiones funcionales (24×200, 0×429)**; dos 401 ajenos a la 025: refresco tras logout y cuenta Clerk sin mapeo (`admin017`).
- [x] Confirmar `X-Request-ID` y ausencia de errores nuevos en consola. → `x-request-id` en todas las respuestas; consola sin errores (solo el aviso de claves dev de Clerk y el *issue* preexistente de campos sin `id`/`name`).
- [x] Registrar que en 4200 no hay nginx y que el presupuesto es único para `127.0.0.1`. → sin nginx; una sola IP de proxy (`::1` en esta sesión) comparte el presupuesto.

**Hecho cuando:** el recorrido se completa por el proxy, sin 429, y el conteo queda en la evidencia.

## T11 — Humo, 429 y fail-open en 8080

**ACs:** AC-11 (manual), AC-19 (8080).

- [x] Recrear el backend con `docker compose up -d --build backend` (no se reconstruye el frontend: no cambia ningún archivo de `frontend/`). → imagen reconstruida; contenedor **healthy**.
- [x] Confirmar una recarga normal sin 429 y con `X-Request-ID`. → 2×200 en 8080 (`auth/me` + `dashboard/`), `x-request-id: 7840edef-…`, `server: nginx/1.31.8`.
- [x] Vaciar Redis con `FLUSHDB` y disparar una ráfaga de ~5 r/s durante ~26 s (≈130 peticiones) a `/api/v1/auth/me`. → **130 peticiones en 26 s**: **120×401 + 10×429**.
- [x] Confirmar al menos un **429 de la aplicación** con `X-RateLimit-Limit: 120`, `X-RateLimit-Remaining: 0`, `Retry-After` y `X-RateLimit-Reset`, sin 429 de nginx. → `Retry-After: 37`, `X-RateLimit-Limit: 120`, `X-RateLimit-Remaining: 0`, `X-RateLimit-Reset: 37`, `X-Request-ID` y `detail` compartido; nginx sin `limiting requests`.
- [x] Documentar la diferencia: el 429 de nginx no lleva `X-RateLimit-*`; el de la app sí. → registrado en la evidencia.
- [x] Detener Redis y confirmar fail-open: recorrido normal sin 429, dashboard 200, `/ready` 200, `/health` 200. → **20×401** con Redis detenido (la ventana previa estaba agotada), dashboard 200, `/ready` 200 y `/health` 200.
- [x] Confirmar en `docker compose logs backend` el aviso `limite_tasa_degradado` como máximo cada 10 s, con `request_id` y `error_type`, sin IP ni traza. → dos avisos separados **10,13 s**, `ConnectionError` y `TimeoutError`, sin IP ni traza.
- [x] Confirmar `resultado="error"` en `/metrics` y que `docker compose start redis` recupera sin reiniciar el backend. → `…{resultado="error"} 22.0`; tras `start redis` + `FLUSHDB`, 401 y `/ready` 200 sin reiniciar.
- [x] Probar el 429 con `Origin: http://localhost:4200` (ACAO) y con un origen ajeno (sin ACAO). → ACAO `http://localhost:4200` con `Vary: Origin`; origen ajeno **sin ACAO**.

**Hecho cuando:** el humo pasa, el 429 de la app es visible y legible con sus cabeceras, y el fail-open deja la aplicación operativa.

## T12 — Prueba de dos workers

**ACs:** AC-20.

- [x] Detener temporalmente `compustock_backend` para aislar el contador compartido. → `docker compose stop backend`.
- [x] Vaciar la base 0 con `docker compose exec redis redis-cli FLUSHDB`. → `OK`; `DBSIZE` final 0.
- [x] Levantar un uvicorn temporal con `--workers 2`, puerto libre y `LIMITE_TASA_MAX_PETICIONES=10`. → `127.0.0.1:8012`, workers 11552 y 26452, `REDIS_URL=redis://127.0.0.1:6380/0`.
- [x] Enviar 15 peticiones a `/api/v1/auth/me` y confirmar exactamente 10×401 y 5×429. → **estado=401 veces=10**; **estado=429 veces=5**.
- [x] Confirmar `X-RateLimit-*` en las cinco rechazadas. → `x-ratelimit-limit: 10`, `x-ratelimit-remaining: 0`, `x-ratelimit-reset: 59`, `retry-after: 59`, `x-request-id` en las cinco.
- [x] Detener uvicorn, vaciar la base 0, volver a levantar el backend de Compose y limpiar `REDIS_URL` y `LIMITE_TASA_*` de la sesión. → workers detenidos; 8012 cerrado (curl exit 7); `FLUSHDB` → `DBSIZE 0`; backend de Compose **healthy**; variables solo en la invocación temporal.
- [x] Registrar la evidencia y aclarar que el despliegue sigue con un worker y las métricas son por proceso. → registrado en `evidencia/README.md` §9.

**Hecho cuando:** el reparto 10/5 demuestra que el estado es compartido entre procesos.

## T13 — Cierre documental, evidencia y commit

**ACs:** AC-21, AC-22 (evidencia), AC-17/AC-18 (cierre).

- [x] Documentar en `docs/spec/stack.md` el nuevo apartado §1.2 con Redis, ventana fija, fail-open, alcance, 429 y frontera con nginx; actualizar la frase de §1.1 sobre «cinco familias» a seis. → §1.2 escrito y §1.1 dice «seis familias».
- [x] Actualizar `AGENTS.md` §3 (Redis en el stack y en Compose) y §5 (suite gated de Redis y `REDIS_TEST_URL`). → hecho; §5 incluye el aviso de `127.0.0.1` frente a `localhost` y `up -d` nombra los cuatro servicios.
- [x] Añadir el servicio Redis y el puerto `6380` a `README.md`. → servicio `compustock_redis` en `127.0.0.1:6380`, efímero y con el aviso de IPv4/`localhost`.
- [x] Completar `evidencia/README.md` con suites, conteos, Redis real, claves y TTL, 429, fail-open, dos workers, recorridos 4200/8080 y diff protegido. → §1–§10.
- [x] Marcar `spec.md` §6 AC por AC con su evidencia. → **22/22** AC marcados con su evidencia.
- [x] Marcar `roadmap.md` con la 025 en `[x]` y fecha de cierre; registrar que la caché de lecturas queda sin feature asignada. → fila 025, Sprint 7 y «Siguiente feature» (015/016); caché sin feature asignada.
- [x] Actualizar `MEMORY.md` con estado, decisiones y siguiente trabajo, incluida la referencia a las «cinco familias» de métricas. → hecho; seis familias desde la 025 y 025 cerrada.
- [x] Ejecutar el `grep` de coherencia sobre `AGENTS.md`, `MEMORY.md` y `.agents/skills/` y corregir rutas o afirmaciones obsoletas. → skills sin afirmaciones obsoletas; corregidos «cinco familias» en `MEMORY.md` y los comandos de `AGENTS.md` §5.
- [x] Revisar `git diff --stat` final y confirmar que solo hay archivos de la feature, dependencias, Compose, documentación y los dos archivos de prueba preexistentes declarados. → 14 modificados + 10 sin seguimiento, todos de la 025; diff protegido vacío.
- [x] Commit de la 025. → commit de la feature.

**Hecho cuando:** `tasks.md` está completo, `spec.md` tiene los 22 AC con evidencia, `roadmap.md` está en `[x]`, la documentación no tiene afirmaciones obsoletas y el commit contiene solo los archivos de la feature.

## Cierre

- [x] `tasks.md` con todas las casillas marcadas, incluidas las de esta sección.
- [x] `spec.md` §6 con los **22 AC** marcados y su evidencia de verificación.
- [x] Backend: `pytest` con `REDIS_TEST_URL` en **0 failed** y **88 skipped**; *gated* PostgreSQL en **73 passed**; *gated* Redis en verde; `pip check` limpio. → **1660/88/0**, **73 passed**, **3 passed** y `pip check` limpio.
- [x] Frontend: `ng test` en **549 SUCCESS** y `ng build` limpio, sin cambios en `frontend/`. → 549 SUCCESS (16,59 s) y build limpio (50,66 s).
- [x] Contrato y datos: **75** operaciones OpenAPI, **73** de matriz, versión **`021.1`**, tablas **27/24**. → confirmado en vivo.
- [x] Recorrido completo en **4200** con **0×429** y humo en **8080** con **0×429**; 429 de la app tras `FLUSHDB` con `X-RateLimit-*`; fail-open con Redis detenido. → 4200 **24×200/0×429**; 8080 humo 2×200; ráfaga **120×401+10×429** de la app; fail-open verificado.
- [x] Dos workers: 15 peticiones → **10 permitidas y 5 rechazadas**. → **10×401 + 5×429**.
- [x] `requirements.txt` con **11** dependencias pineadas y `redis==8.1.0` como única nueva. → 11 líneas, todas `==`.
- [x] Documentación coherente: `stack.md`, `AGENTS.md`, `README.md`, `roadmap.md`, `MEMORY.md` y evidencia; `grep` de `AGENTS.md` §8.7 sin hallazgos obsoletos. → grep ejecutado; sin afirmaciones obsoletas.
- [x] `git status` sin archivos fuera de alcance y commit de la 025 publicado. → commit de la feature.
