# Feature 025: Límite de tasa distribuido con Redis

**Estado:** Borrador para aprobación (15/Nov/2026)
**Release:** 2.0 — Sprint 7 (hardening transversal)
**Tipo:** Endurecimiento operativo; el comportamiento solo cambia para el tráfico que supera el límite
**Sucede a:** Feature 024 (hardening operativo I, cerrada el 15/Nov/2026)

## 1. Problema

La Feature 024 endureció el borde, pero dejó explícitamente fuera el limitador de la aplicación:

> «un limitador en proceso no comparte estado entre procesos, se reinicia con el servicio y no
> protege el puerto de entrada. La alternativa correcta en la app requiere un almacén
> compartido —Redis— que es la Feature 025.»
> — `docs/spec/features/024-hardening-operativo/spec.md`, D-7.

Hoy ese hueco es verificable:

1. **El único límite vive en nginx.** `frontend/nginx.conf` declara `limit_req` a 10 r/s con
   `burst=20` y `limit_conn` 20 sobre `/api/`; `backend/app/main.py` solo monta CORS y
   observabilidad. No hay ninguna defensa de tasa dentro de la API.
2. **El borde no cubre todos los caminos.** El puerto `8000` está publicado en desarrollo
   (`docker-compose.yml`), y cualquier llamada directa a la API —diagnóstico, herramientas,
   un futuro balanceador o una segunda instancia de nginx— esquiva el límite. Con varias
   instancias de nginx, cada una lleva su propia cuenta y el presupuesto real se multiplica.
3. **No existe almacén compartido.** `docker-compose.yml` levanta solo `db`, `backend` y
   `frontend`; `backend/requirements.txt` no tiene cliente Redis; `app/core/metricas.py`
   expone cinco familias y ninguna habla de límites. Un contador en memoria parecería
   suficiente hoy —el backend corre un solo worker— y se rompería en silencio el día que se
   añada `--workers N`.
4. **No hay visibilidad del límite en la aplicación.** Un 429 de nginx no lleva
   `X-Request-ID`, no aparece en `docker compose logs backend` y no incrementa ninguna
   métrica: no se puede responder cuántos clientes se están limitando ni desde qué ruta.
5. **El valor por defecto no puede elegirse a ciegas.** La evidencia de la 024 midió **59
   peticiones** en un recorrido funcional completo en 4200 y **34** en el humo de 8080. Un
   límite de 60/min dejaría al usuario a una petición del 429 y rompería el segundo
   recorrido dentro del mismo minuto. El default se fija en **120/min** (D-8).

**Impacto:** sin esta feature, la protección contra abuso depende de un único proceso de
nginx y desaparece en el acceso directo; la aplicación no puede limitar su propia entrada ni
explicar sus rechazos, y el día que escale horizontalmente el límite se multiplicará por
instancia sin que nadie lo note.

## 2. Objetivo

Añadir un **límite de tasa compartido entre procesos** sobre `/api/v1`, con Redis como
almacén efímero, sin tocar una sola regla de negocio, contrato de API ni dato:

- Redis como servicio interno de Docker Compose, sin persistencia y sin ser dependencia de
  arranque ni de *readiness*;
- ventana fija por IP de cliente, configurable, con 120 peticiones por 60 s por defecto;
- 429 en JSON con `detail`, `Retry-After` y `X-RateLimit-*`, correlacionado por
  `X-Request-ID` y legible por la SPA;
- **fail-open** con latencia acotada: si Redis no responde, la petición sigue, se registra
  una alerta y una métrica, y el borde nginx sigue limitando;
- superficie de métricas y logs acotada, sin IP, usuario, institución ni tenant;
- pruebas unitarias con un falso, pruebas *gated* contra Redis real y prueba de estado
  compartido con dos workers;
- dependencia nueva analizada y pineada, y contrato, datos y permisos intactos.

## 3. Alcance

### 3.1 Dentro de alcance

| Bloque | Contenido |
|---|---|
| **B1 — Infraestructura** | Servicio Redis 7.2 en Compose, sin persistencia, con memoria acotada y puerto solo en loopback. |
| **B2 — Almacén y cliente** | Cliente Redis asíncrono pineado, creación perezosa, timeouts cortos y script Lua atómico de ventana fija. |
| **B3 — Middleware** | Middleware ASGI que limita todo `/api/v1/*`, resuelve la IP del cliente y respeta el orden de capas. |
| **B4 — Política y 429** | 120 peticiones por IP y 60 s configurables, con cuerpo JSON y cabeceras de límite. |
| **B5 — Fail-open** | Cualquier fallo del limitador deja pasar la petición, con aviso acotado y métrica; `/ready` no cambia. |
| **B6 — Observabilidad** | Una familia nueva de métricas, valor reservado de ruta para los 429 y logs sin PII. |
| **B7 — Configuración** | Variables de entorno, validación al arrancar e interruptor de apagado. |
| **B8 — Pruebas y evidencia** | Falso de Redis, suite *gated* contra Redis real, dos workers y recorrido en 4200 y 8080. |

### 3.2 Fuera de alcance

- **Caché de lecturas.** La 024 mencionó «Redis y cualquier caché» como Feature 025; esta
  spec toma **solo el limitador**, decisión explícita del usuario. La caché queda **sin
  feature asignada**: si se retoma, necesita spec propia (TTL, invalidación, consistencia y
  medición de latencia). Se registrará así en `roadmap.md` y `MEMORY.md` para que nadie lea
  «025 = Redis» como «caché hecha».
- **Límite por identidad autenticada**, por institución/tenant o por endpoint. El límite es
  por IP y punto de entrada; resolver la identidad antes del limitador cambiaría el orden de
  dependencias y el costo por petición.
- **Ventana deslizante, *token bucket* o límites adaptativos.** Se elige ventana fija (D-3).
- **Persistencia, réplica, Sentinel, Cluster o autenticación Redis en local.** El
  despliegue de producción (red privada, ACL, TLS) queda documentado como supuesto, no como
  implementación de esta feature.
- **Cambios en los valores del borde nginx.** Se conservan los de la 024; el límite de la
  aplicación es complementario, no un reemplazo.
- **Frontend.** Ningún archivo bajo `frontend/src/**`, `frontend/nginx.conf` ni
  `frontend/angular.json` cambia. El 429 se muestra con el manejo de errores existente que
  ya lee `detail` (024, AC-20).
- **Métricas multiproceso.** La 024 asumió un solo worker de uvicorn; esta feature no cambia
  ese modelo. La prueba de dos workers verifica el estado compartido del limitador, no la
  agregación de métricas.
- **Cabeceras `X-RateLimit-*` en respuestas exitosas.** Solo acompañan al 429.
- **DDL, versión `021.1`, tablas 27/24, matriz de permisos (73), OpenAPI (75),
  `response_model`, textos visibles, `database/`, `backend/app/models/**` y `permisos.py`.**
- **Autenticación y autorización.** No se tocan; el limitador corre antes de Clerk y por eso
  también cuenta los 401.

## 4. Decisiones de diseño

### D-1 — Redis es el almacén compartido; no un contador en proceso ni una tabla

El límite se lleva en Redis, con una clave por IP y TTL igual a la ventana.

- **Por qué Redis:** `INCR` y `PEXPIRE` son atómicos y baratos, el TTL es nativo, no hay
  esquema que mantener y el estado es efímero por definición. Una operación por petición con
  latencia de milisegundos es exactamente su caso de uso.
- **Por qué no un contador en proceso:** se reinicia con el despliegue, no se comparte entre
  workers ni instancias y obliga a que el número de procesos sea un detalle de despliegue
  con efecto en seguridad. Es la razón que la 024 dejó escrita en D-7.
- **Por qué no PostgreSQL:** convertiría cada petición de la API en una escritura
  transaccional sobre la base de negocio, añadiría contención y acoplaría el límite a la
  disponibilidad de la base. El limitador debe ser más barato que el trabajo que protege.
- **Por qué Redis no es una dependencia dura:** el borde nginx sigue siendo la primera
  línea; Redis añade estado compartido y defensa en profundidad. De ahí el fail-open (D-6).

### D-2 — Redis 7.2-alpine, efímero, acotado y solo en loopback

El servicio usa `redis:7.2-alpine`, sin volumen, sin RDB/AOF, con
`maxmemory 64mb` y `maxmemory-policy allkeys-lru`, y publica su puerto únicamente en
`127.0.0.1:${REDIS_PORT:-6380}:6379`.

- **Por qué 7.2 y no la última:** Redis 7.2 es la última línea con licencia **BSD-3-Clause**.
  A partir de 7.4 el servidor pasó a RSALv2/SSPLv1 y Redis 8 añadió AGPLv3; para un proyecto
  de título autohospedado, una licencia permisiva evita una discusión legal que no aporta
  nada a la feature. La matriz de compatibilidad de `redis-py` 8.1 confirma soporte de 7.2.
- **Por qué sin persistencia ni volumen:** un contador de tasa vive como máximo una ventana
  (60 s). Un reinicio de Redis pierde los contadores y se recupera solo en ≤ 60 s; eso es
  equivalente a un fail-open y no justifica un volumen, un `down -v` extra ni I/O de disco.
- **Por qué `maxmemory` y LRU:** el número de claves es el número de IP activas; un cliente
  que falsifique IPs podría inflarlo. Con memoria acotada y expulsión LRU el store nunca
  tumba el host; bajo presión se pierden contadores, que es el modo de fallo más benigno.
- **Por qué el puerto solo en loopback:** `ports: "6380:6379"` publicaría Redis en todas las
  interfaces del host. Las pruebas *gated* y el diagnóstico local solo necesitan
  `127.0.0.1`; en producción Redis no se publica. Sin contraseña en local porque no sale del
  loopback ni de la red interna de Compose; producción exige red privada y ACL (supuesto en
  §9).
- **Por qué el backend no depende de Redis para arrancar:** un `depends_on` con
  `condition: service_healthy` convertiría a Redis en requisito de arranque y contradiría el
  fail-open. El backend arranca, sirve y limita en cuanto Redis esté disponible; mientras
  tanto, falla abierto.

### D-3 — Ventana fija anclada al primer acierto, con script Lua atómico

Cada IP tiene una clave `compustock:limite:<ip>`. La primera petición de la ventana la crea
con `INCR` y le fija `PEXPIRE = ventana`; las siguientes solo incrementan. El script devuelve
el contador y el TTL restante. La ventana empieza con la primera petición de esa IP, no en un
minuto del reloj.

- **Por qué Lua y no `INCR` + `EXPIRE` separados:** entre ambos comandos cabe una caída del
  cliente; una clave sin TTL bloquearía a esa IP para siempre. El script también repara el
  caso anómalo de TTL negativo (`PTTL < 0`) volviendo a fijar la expiración, y devuelve el
  TTL en la misma ida y vuelta.
- **Por qué ventana fija:** memoria O(1) por IP y una operación por petición. Una ventana
  deslizante exige un *sorted set* de marcas de tiempo por IP —memoria proporcional al
  límite— y más operaciones; el borde ya suaviza las ráfagas de menos de un segundo. La
  consecuencia se acepta y se documenta: entre dos ventanas contiguas un cliente puede
  consumir hasta el doble del límite en el peor caso.
- **Por qué anclada y no alineada al reloj:** el `Retry-After` sale directamente del `PTTL`
  y es honesto; alinear al minuto exigiría calcular el borde y regalaría una ventana parcial
  distinta en cada acierto.
- **Por qué la clave lleva la IP sin hashear:** Redis es interno, la clave vive ≤ 60 s y no
  se registra en logs ni métricas. Un hash de una IPv4 se revierte por fuerza bruta, así que
  no sería anonimización real y solo dificultaría el diagnóstico (`redis-cli GET`). La IP no
  sale de Redis.
- **Por qué `EVAL` en cada petición y no `SCRIPT LOAD` + `EVALSHA`:** evita estado de
  arranque y el error `NOSCRIPT` tras un reinicio de Redis; el script son ~200 bytes y
  pesan menos que una ida y vuelta adicional o un fallo por caché fría.

### D-4 — IP del cliente: par por defecto, `X-Real-IP` solo si se confía en el proxy

La IP efectiva es la del par TCP (`scope["client"]`) salvo que
`LIMITE_TASA_CONFIAR_PROXY=true` y la cabecera `X-Real-IP` traiga una IP válida.

- **Por qué `X-Real-IP` y no `X-Forwarded-For`:** nginx **sobrescribe** `X-Real-IP` con
  `$remote_addr`; `X-Forwarded-For` se construye con `$proxy_add_x_forwarded_for`, que
  conserva lo que envió el cliente. Usar la lista permitiría elegir la clave con una cabecera
  falsa.
- **Por qué validar la cabecera con `ipaddress.ip_address`:** un valor arbitrario se
  convertiría en una clave de Redis (inyección, cardinalidad, longitudes absurdas). Si no es
  una IP, se ignora y se usa la del par. La IP del par no se valida porque la provee el
  servidor ASGI; si falta, se agrupa bajo un valor fijo reservado.
- **Por qué `false` por defecto:** el puerto 8000 está publicado en desarrollo; confiar en la
  cabecera por defecto permitiría a cualquiera elegir su propio contador y saltarse el
  límite. En Compose se activa porque quien habla con el backend es nginx, que la
  sobrescribe.
- **Consecuencia en desarrollo:** en 4200 y en el acceso directo a 8000 todas las peticiones
  comparten la IP del par (`127.0.0.1`), así que el presupuesto es único para el
  desarrollador. Es un entorno de una persona y no cambia la verificación.

### D-5 — Orden de middleware y contrato del 429

El orden es **observabilidad → CORS → limitador → rutas**. El limitador se añade antes que
CORS en `crear_app()` para quedar por dentro.

- **Por qué el limitador dentro de CORS:** el preflight lo resuelve CORS antes de llegar al
  limitador, así que **no consume presupuesto**; y el 429 vuelve a atravesar CORS, que le
  añade `Access-Control-Allow-Origin` cuando el origen está permitido. Sin eso, el navegador
  vería un error de CORS y ocultaría la causa real.
- **Por qué observabilidad sigue siendo la capa más externa:** el 429 lleva `X-Request-ID` y
  deja su línea de acceso como cualquier otra respuesta. Si el limitador quedara por fuera,
  el rechazo sería invisible para los logs.
- **Por qué antes de autenticación:** protege también el endpoint más caro y más abusado —el
  login— y no necesita resolver identidad. Contar los 401 es deliberado.
- **Cuerpo del 429:** `{"detail": "Demasiadas peticiones. Intente nuevamente en unos
  segundos."}`, el mismo texto que ya usa nginx, para que la SPA muestre un mensaje único.
- **Cabeceras del 429:** `Retry-After` (segundos, entero ≥ 1), `X-RateLimit-Limit` (máximo
  configurado), `X-RateLimit-Remaining: 0` y `X-RateLimit-Reset` (segundos que faltan para
  reiniciar la ventana, mismo valor que `Retry-After`). No se añaden a las respuestas
  exitosas: ningún consumidor las usa hoy y mantenerlas fuera reduce la superficie.
- **Por qué el contador incrementa también los rechazos:** mide intentos, no solo éxitos. El
  `PEXPIRE` no se renueva, así que martillar el endpoint no prolonga el bloqueo; la ventana
  termina igual.

### D-6 — Fail-open con alerta y latencia acotada

Cualquier error del paso del limitador —Redis caído, timeout, respuesta inesperada o un fallo
del propio código— deja pasar la petición: `resultado="error"`, un `WARNING` como máximo cada
10 s y la petición continúa.

- **Por qué fail-open:** Redis guarda un contador de tasa, no la verdad del negocio. Tumbar
  login, pedidos e inventario porque el store del limitador no responde es peor que operar
  con la protección del borde; además, un fallo de Redis no debe convertirse en un incidente
  del producto.
- **Por qué no fail-closed:** un 503 global por Redis convertiría una pieza de defensa en una
  dependencia de disponibilidad y contradiría el objetivo de la feature.
- **Por qué los timeouts son cortos y sin reintentos:** `socket_connect_timeout` y
  `socket_timeout` de 200 ms, sin reintentos del cliente. Con Redis en un agujero negro, cada
  petición paga como máximo ~0,4 s y nunca se cuelga; el límite de la 024 para `/ready` (2 s)
  es la referencia de cota.
- **Por qué el aviso se limita a uno cada 10 s:** una caída de Redis con 120 peticiones/min
  inundaría el log de warnings y enterraría la línea de acceso. La métrica cuenta **todos**
  los fallos; el log solo avisa de que hay una racha.
- **Qué nunca se registra en el aviso:** IP, host, puerto, cadena de conexión, mensaje de la
  excepción ni traza. Solo `request_id` y `error_type` (el nombre de la clase), que ya están
  en la lista blanca de campos del formateador.
- **Por qué no un cortocircuito local:** añadiría estado por proceso y un segundo modo de
  fallo. Si la latencia del fail-open se vuelve material, se evalúa con su propia spec.
- **`/ready` sigue midiendo solo la base:** incluir Redis lo convertiría en dependencia dura
  y contradiría el fail-open. Con Redis caído y la base arriba, `/ready` responde 200.

### D-7 — Observabilidad del limitador sin cardinalidad ni PII

Se añade **una** familia: `compustock_rate_limit_requests_total{resultado}`, con exactamente
tres valores: `permitida`, `limitada` y `error`.

- **Por qué una familia con etiqueta y no tres contadores:** tres valores cerrados producen
  tres series, una sola expresión de alerta y un nombre estable; tres familias separadas
  fragmentan la consulta sin ganar nada.
- **Por qué `route="rate_limited"` en los 429:** el limitador corre antes del enrutado, así
  que sin una marca el 429 caería en `unmatched` y se confundiría con los 404 de un escáner.
  El limitador deja una marca en `scope["state"]` y la observabilidad usa un valor fijo
  reservado, sin cardinalidad nueva. `unmatched` se conserva para las rutas desconocidas.
- **Por qué no hay etiqueta de IP:** sería cardinalidad no acotada y PII en la superficie de
  métricas. La IP solo vive en la clave de Redis.
- **Duplicación deliberada con `compustock_http_requests_total`:** igual que
  `compustock_http_errors_total` en la 024, el contador dedicado es la señal de alerta; el
  contador HTTP sigue midiendo el resultado real.
- **`/metrics` no se limita ni se autoinstrumenta:** vive fuera de `/api/v1`, y la 024 ya lo
  excluyó de su propia instrumentación.

### D-8 — Configuración y valores por defecto

| Variable | Default | Compose | Propósito |
|---|---|---|---|
| `REDIS_URL` | `redis://127.0.0.1:6380/0` | `redis://redis:6379/0` | Conexión al almacén. |
| `LIMITE_TASA_HABILITADO` | `true` | `true` | Interruptor de apagado. |
| `LIMITE_TASA_MAX_PETICIONES` | `120` | `120` | Peticiones por ventana e IP. |
| `LIMITE_TASA_VENTANA_SEGUNDOS` | `60` | `60` | Duración de la ventana. |
| `LIMITE_TASA_CONFIAR_PROXY` | `false` | `true` | Usar `X-Real-IP` de nginx. |

- **Por qué 120/min:** la 024 midió 59 peticiones en un recorrido completo y 34 en el humo.
  120 permite dos recorridos por minuto con margen para recargas y sigue siendo **5× más
  estricto** que el borde (10 r/s sostenidas = 600/min), de modo que corta el abuso sostenido
  que el borde deja pasar. Es configurable por entorno.
- **Por qué el límite es por IP y no por usuario:** es la única dimensión disponible antes de
  autenticar y la que usa el borde; la limitación por identidad queda fuera (§3.2). Se
  documenta su límite conocido: varios usuarios tras una misma IP de salida (NAT) comparten
  presupuesto, y por eso el default es holgado y configurable.
- **Por qué el interruptor existe:** permite responder a un incidente de Redis sin desplegar
  código (`LIMITE_TASA_HABILITADO=false`), y permite que la suite de 1596 pruebas siga sin
  Redis ni timeouts. Con `false` no se construye middleware ni cliente: cero conexiones.
- **Validación:** máximo y ventana deben ser enteros ≥ 1; con el limitador habilitado,
  `REDIS_URL` debe empezar por `redis://` o `rediss://`. Un valor inválido impide el arranque
  con un mensaje claro, en la línea de `ALLOWED_ORIGINS` de la 024.

### D-9 — `redis-py` 8.1.0 es la única dependencia nueva

Se añade `redis==8.1.0` (cliente oficial, asíncrono). Análisis exigido por `AGENTS.md` §7:

- **Verificación en PyPI (15/Nov/2026):** versión **8.1.0**, publicada el **30/Jul/2026**;
  *wheel* `redis-8.1.0-py3-none-any.whl` (**Python puro**); licencia **MIT**; requiere Python
  ≥ 3.10; su única dependencia obligatoria es `async-timeout>=4.0.3` para
  `python_full_version < "3.11.3"`. El host corre **3.11.3** y la imagen **3.12-slim**, así
  que en los entornos verificados **no arrastra transitivas**. La tabla de compatibilidad
  del cliente confirma soporte de Redis 7.2.
- **Por qué asíncrono:** el middleware es ASGI. Un cliente síncrono bloquearía el bucle de
  eventos en cada petición y, durante un Redis en agujero negro, lo bloquearía hasta el
  timeout para **todas** las peticiones. `redis.asyncio` mantiene el servidor responsivo sin
  añadir un salto a threadpool.
- **Por qué sin `hiredis`:** es una extensión compilada y una dependencia extra para una
  llamada por petición; no hay necesidad medida. Queda como optimización futura.
- **Por qué no `fakeredis` en las pruebas:** sería una dependencia de desarrollo nueva. Un
  falso mínimo en la suite cubre los casos unitarios y la suite *gated* cubre la semántica
  real del script y del TTL.
- **Configuración del cliente:** creación perezosa en el bucle de eventos en la primera
  petición que lo necesita, *pool* de conexiones, timeouts de 200 ms, sin reintentos y sin
  `decode_responses` (el script devuelve enteros).
- **Impacto en la suite de la 024:** `tests/test_dependencias_024.py` afirma exactamente
  diez dependencias directas y pasará a afirmar **once** con `redis==8.1.0`. Es la única
  prueba de una feature cerrada que cambia; su intención (nivel directo exacto y pineado) se
  conserva. No se reescribe ningún `spec.md`, `plan.md` ni `tasks.md` de la 024: son
  históricos.

### D-10 — Estrategia de pruebas: falso, Redis real y dos workers

- **Unitarias con un falso:** un cliente asíncrono de memoria que imita `eval`, con
  excepciones programables. Cubren conteo, 429, cabeceras, orden de capas, fail-open,
  configuración y métricas. No necesitan Docker.
- **Gated contra Redis real:** variable `REDIS_TEST_URL` (análoga a `POSTGRES_TEST_URL`),
  omitidas si falta. Verifican el script Lua, el TTL, el reinicio de ventana, la atomicidad
  bajo concurrencia y el estado compartido entre dos instancias. Usan una base distinta de la
  de la aplicación (índice 15) y la vacían al empezar.
- **Dos workers:** uvicorn temporal con `--workers 2` y `LIMITE_TASA_MAX_PETICIONES=10`;
  15 peticiones deben dar **10 permitidas y 5 rechazadas**. Un contador en proceso habría
  permitido hasta 20. Es evidencia manual de cierre, no una prueba permanente.
- **La suite existente no toca Redis:** `tests/conftest.py` apaga el limitador en la
  configuración **antes** de construir el singleton `app`, de modo que las 1596 pruebas de la
  línea base no pagan timeouts ni emiten avisos. Las pruebas nuevas habilitan el limitador
  explícitamente y le inyectan el falso o el cliente real.

## 5. Requisitos funcionales

### R-1 — Infraestructura Redis

1. `docker-compose.yml` incorpora un servicio `redis` con `image: redis:7.2-alpine`,
   `container_name: compustock_redis`, `restart: unless-stopped` y *healthcheck*
   `redis-cli ping` cada 10 s.
2. El servicio no declara volumen ni persistencia (`--save ""`, `--appendonly no`) y limita
   su memoria a 64 MB con `allkeys-lru`.
3. Su puerto se publica solo en `127.0.0.1:${REDIS_PORT:-6380}:6379`.
4. El backend no declara `depends_on` hacia Redis y arranca aunque Redis no esté.
5. El backend recibe `REDIS_URL` y las cuatro variables `LIMITE_TASA_*` por entorno.

### R-2 — Almacén compartido y cliente

1. El cliente es `redis.asyncio` de `redis==8.1.0`, pineado en `requirements.txt`.
2. Se crea de forma perezosa en la primera petición que necesita límite; con
   `LIMITE_TASA_HABILITADO=false` no se crea ni se abre ninguna conexión.
3. Los timeouts de conexión y de lectura son de 200 ms y el cliente no reintenta.
4. Cada petición limitada ejecuta **un** script Lua que incrementa el contador, fija el TTL
   en la primera petición de la ventana y devuelve contador y TTL restante.
5. La clave es `compustock:limite:<ip>` con TTL igual a la ventana; si el TTL resultara
   negativo, el script lo repara en la misma ejecución.

### R-3 — Alcance del límite

1. Solo se limitan las rutas bajo `/api/v1` (el prefijo se compara por segmento:
   `/api/v1` o `/api/v1/…`). Cualquier otra ruta no se cuenta ni se rechaza.
2. `/`, `/health`, `/ready`, `/metrics`, `/docs`, `/redoc`, `/openapi.json` y los recursos
   de la SPA quedan fuera.
3. El preflight CORS (`OPTIONS` con `Origin` y `Access-Control-Request-Method`) no consume
   presupuesto.
4. Cuentan todas las peticiones a `/api/v1`, sea cual sea el método y aunque terminen en
   401, 403, 404, 422 o 500.
5. El límite corre antes de la autenticación y no exige Bearer.

### R-4 — Identificación del cliente

1. Sin confianza en el proxy, la IP es la del par TCP de `scope["client"]`.
2. Con `LIMITE_TASA_CONFIAR_PROXY=true`, se usa `X-Real-IP` si contiene una IP válida
   (IPv4 o IPv6); si falta o no es válida, se usa la del par.
3. `X-Forwarded-For` no se lee nunca.
4. Si no hay IP de par, se usa un valor fijo reservado, compartido por esos casos.
5. Ninguna respuesta, log o métrica contiene la IP ni la clave de Redis.

### R-5 — Política y respuesta 429

1. Por defecto, 120 peticiones por IP en una ventana de 60 s; ambos valores configurables.
2. La petición número `max + 1` y las siguientes de la misma IP y ventana responden 429.
3. El 429 es JSON con `detail` y `Content-Type` JSON; el texto es
   «Demasiadas peticiones. Intente nuevamente en unos segundos.».
4. El 429 incluye `Retry-After` (entero entre 1 y la ventana), `X-RateLimit-Limit`,
   `X-RateLimit-Remaining: 0` y `X-RateLimit-Reset` (segundos restantes, mismo valor que
   `Retry-After`).
5. El 429 lleva `X-Request-ID` y, si la petición trae un `Origin` permitido, las cabeceras
   CORS que añade el middleware.
6. Los rechazos incrementan el contador de la ventana pero **no** renuevan su TTL.
7. Al expirar la ventana, la siguiente petición de esa IP empieza con presupuesto completo.
8. Las respuestas permitidas no cambian de cuerpo, estado ni cabeceras.

### R-6 — Fail-open

1. Cualquier error del limitador (Redis, timeout, respuesta inesperada o fallo propio) deja
   pasar la petición y no produce 5xx por sí mismo.
2. Cada error incrementa `compustock_rate_limit_requests_total{resultado="error"}`.
3. Se emite como máximo un `WARNING` cada 10 s por proceso, con `request_id` y `error_type`,
   sin IP, host, mensaje de excepción ni traza.
4. Con Redis en un agujero negro, el limitador no añade más de ~0,5 s por petición y nunca
   la cuelga.
5. `/ready` sigue midiendo solo la base: con Redis caído y la base arriba responde 200.
6. Un fallo del limitador no altera el cuerpo ni el estado que habría producido la ruta.

### R-7 — Observabilidad

1. `compustock_rate_limit_requests_total{resultado}` se incrementa una vez por petición
   procesada por el limitador, con `resultado` en `permitida`, `limitada` o `error`.
2. Las cinco familias de la 024 se conservan.
3. Un 429 se registra como `route="rate_limited"` en
   `compustock_http_requests_total` y en el campo `path` de la línea de acceso; la ruta real
   nunca se usa como etiqueta.
4. Las etiquetas de la familia nueva son exactamente `{resultado}`.
5. Ninguna etiqueta ni línea de log contiene IP, usuario, institución, tenant, token ni
   query string.
6. Con el limitador apagado no se incrementa la familia nueva; las de la 024 siguen
   funcionando.

### R-8 — Configuración

1. Los defaults son los de D-8 y se pueden sobrescribir por entorno o `.env`.
2. `LIMITE_TASA_MAX_PETICIONES` y `LIMITE_TASA_VENTANA_SEGUNDOS` deben ser enteros ≥ 1; un
   valor inválido impide el arranque con un mensaje que nombra la variable.
3. Con el limitador habilitado, `REDIS_URL` debe empezar por `redis://` o `rediss://`; si no,
   el arranque falla con un mensaje claro.
4. Con `LIMITE_TASA_HABILITADO=false` no se añade el middleware, no se crea cliente y no se
   abre ninguna conexión.

### R-9 — Contrato, datos y permisos intactos

1. `MATRIZ_PERMISOS` sigue con **73** operaciones y `/openapi.json` con **75**; no aparece
   ninguna ruta nueva.
2. La versión de esquema sigue en `021.1` y las tablas en 27 de control / 24 por tenant.
3. No cambian `database/`, `backend/app/models/**`, `permisos.py`, los endpoints, los
   esquemas, los `response_model`, los textos visibles ni los cuerpos de las rutas de
   negocio.
4. Ningún archivo de `frontend/` cambia.
5. `backend/requirements.txt` pasa a tener **11** dependencias directas, todas con `==`.
6. Los únicos archivos de prueba preexistentes que cambian son `tests/conftest.py`
   (apagado del limitador en la configuración de la suite) y
   `tests/test_dependencias_024.py` (10 → 11); el resto son pruebas nuevas.

### R-10 — Evidencia y documentación

1. `evidencia/README.md` reúne suites, conteos de contrato, salida de Redis (claves y TTL),
   respuestas 429, evidencia de fail-open, prueba de dos workers y recorrido en los dos
   puertos.
2. `docs/spec/stack.md` documenta el límite distribuido, Redis y su frontera operativa.
3. `AGENTS.md` §3 incluye Redis en los servicios de Compose y §5 el comando de la suite
   *gated* de Redis.
4. `README.md` lista el servicio Redis y su puerto local.
5. `roadmap.md` registra la 025 y deja la caché de lecturas explícitamente sin feature
   asignada; `MEMORY.md` recoge estado, decisiones y próximo trabajo.
6. El `grep` de coherencia de `AGENTS.md` §8.7 no deja rutas ni afirmaciones obsoletas.

## 6. Criterios de aceptación

- [x] **AC-1 — Redis operativo y efímero.** `docker compose up -d` deja `compustock_redis`
  *healthy*; `redis-cli ping` responde `PONG`; el servicio no tiene volumen ni persistencia;
  `maxmemory` es 64 MB con `allkeys-lru`; el puerto por defecto se publica solo en
  `127.0.0.1:6380`.
  **Evidencia prevista:** `docker compose ps`, `docker inspect` y `redis-cli CONFIG GET`.
  **Evidencia:** *healthy*; `PONG`; Redis **7.2.17**; `maxmemory=67108864`;
  `maxmemory-policy=allkeys-lru`; `save` vacío; `appendonly no`; tmpfs
  `/data:size=64m`; `Mounts []`; `127.0.0.1:6380->6379/tcp` (evidencia §4).
- [x] **AC-2 — Conteo exacto.** Con máximo 3 y ventana 60 en una app de prueba con falso,
  las tres primeras peticiones a `/api/v1/*` no son 429 y la cuarta sí; las tres primeras
  conservan el estado que produce la ruta (401 sin Bearer).
  **Evidencia prevista:** `tests/api/test_limite_tasa_025.py`.
  **Evidencia:** `tests/api/test_limite_tasa_025.py` **11 passed**; 3×401 y cuarta 429.
- [x] **AC-3 — Contrato del 429.** El 429 tiene `Content-Type` JSON, cuerpo con `detail` y el
  texto de R-5.3, `Retry-After` entero entre 1 y 60, `X-RateLimit-Limit` igual al máximo,
  `X-RateLimit-Remaining: 0`, `X-RateLimit-Reset` entre 1 y 60 y `X-Request-ID` con UUID.
  Con `Origin: http://localhost:4200` incluye `Access-Control-Allow-Origin`; con un origen
  ajeno no lo incluye.
  **Evidencia prevista:** mismas pruebas unitarias más `curl` en 8080.
  **Evidencia:** pruebas de API + 429 real en 8080 con `Retry-After: 37`,
  `X-RateLimit-Limit: 120`, `Remaining: 0`, `Reset: 37`, `X-Request-ID` UUID, ACAO con el
  origen permitido y **sin ACAO** con `http://evil.example` (evidencia §8).
- [x] **AC-4 — Reinicio de ventana y TTL no renovable.** Tras expirar la ventana, la misma IP
  vuelve a disponer del máximo; las peticiones rechazadas no alargan el TTL; el
  `Retry-After` decrece de forma coherente con el TTL restante.
  **Evidencia prevista:** prueba *gated* con ventana de 1 s y `TTL`/`PTTL` leídos de Redis.
  **Evidencia:** escenario (b) de `test_limite_tasa_redis_025.py` en verde con Redis real
  (evidencia §5).
- [x] **AC-5 — Presupuesto por IP.** Con confianza en el proxy activada, dos `X-Real-IP`
  distintas tienen contadores independientes: agotar una no afecta a la otra.
  **Evidencia prevista:** prueba unitaria parametrizada y comprobación de claves en Redis.
  **Evidencia:** pruebas unitarias de `tests/test_limite_tasa_025.py` (30 en T3); claves
  independientes verificadas en el escenario *gated* (evidencia §3 y §5).
- [x] **AC-6 — Confianza en el proxy.** Con `LIMITE_TASA_CONFIAR_PROXY=false`,
  `X-Real-IP` se ignora y todas las peticiones comparten la IP del par; con `true`, una IP
  válida se usa como clave; un valor inválido (`abc`, `1.2.3.4:80`, lista) cae a la IP del
  par; `X-Forwarded-For` nunca se lee.
  **Evidencia prevista:** pruebas unitarias de la resolución de IP.
  **Evidencia:** `resolver_ip` cubierto por las 30 pruebas unitarias de T3 (`abc`,
  `1.2.3.4:80`, lista y `X-Forwarded-For` ignorado).
- [x] **AC-7 — Rutas operativas fuera.** 200 peticiones a `/`, `/health`, `/ready`,
  `/metrics`, `/docs`, `/redoc` y `/openapi.json` no consumen presupuesto ni reciben 429; un
  `/api/v1` inexistente sí cuenta.
  **Evidencia prevista:** prueba unitaria y contraste del contador en `/metrics`.
  **Evidencia:** prueba de API de alcance en T4; solo `/api/v1/*` consume presupuesto.
- [x] **AC-8 — Preflight gratis.** Un `OPTIONS` con `Origin` permitido y
  `Access-Control-Request-Method` responde 200 con las cabeceras CORS exactas, no consume
  presupuesto y no devuelve 429; después de él siguen cabiendo las 120 peticiones de la
  ventana.
  **Evidencia prevista:** prueba unitaria y `curl -X OPTIONS` en 8080.
  **Evidencia:** prueba de API de T4: el preflight responde 200 y el contador no cambia.
- [x] **AC-9 — Fail-open visible.** Con un falso que lanza `ConnectionError`, todas las
  peticiones de `/api/v1` siguen su curso (401, no 429 ni 5xx), la métrica
  `resultado="error"` incrementa y se emite **un** `WARNING` en la ventana de 10 s con
  `request_id` y `error_type`, sin IP, host, mensaje ni traza.
  **Evidencia prevista:** prueba unitaria con captura de logs y de la exposición.
  **Evidencia:** `tests/api/test_limite_tasa_failopen_025.py` **3 passed**; aviso real en
  8080 con dos líneas separadas 10,13 s, `request_id` y `error_type` (evidencia §3.1 y §8).
- [x] **AC-10 — Fail-open acotado.** Con `REDIS_URL` apuntando a un host que no responde
  (`192.0.2.1`), una petición a `/api/v1` termina en menos de 1 s, no es 429 y no es 5xx por
  culpa del limitador.
  **Evidencia prevista:** prueba con cliente real y timeouts de 200 ms; medición repetida
  tres veces.
  **Evidencia:** tres evaluaciones reales terminan en **~0,22 s** con `TimeoutError` y
  `permitida=True`; la cota dura es `asyncio.wait_for(0.5)` (evidencia §3.1 y §5).
- [x] **AC-11 — Readiness intacto.** Con Redis caído y la base disponible, `/ready` responde
  200 `{"status":"ready"}` y no menciona Redis; con la base caída sigue respondiendo 503 como
  en la 024. `/health` sigue en 200.
  **Evidencia prevista:** prueba unitaria con falso caído y comprobación manual con
  `docker compose stop redis`.
  **Evidencia:** con `docker compose stop redis`, `/ready` 200 y `/health` 200; `/ready` no
  consulta Redis (evidencia §8).
- [x] **AC-12 — Métricas del limitador.** Tras una petición permitida y una rechazada,
  `/metrics` incrementa en uno `compustock_rate_limit_requests_total{resultado="permitida"}`
  y `{resultado="limitada"}` respecto de la lectura anterior, la etiqueta es exactamente
  `{resultado}`, las cinco familias de la 024 siguen presentes y el 429 aparece como
  `route="rate_limited"` en `compustock_http_requests_total`.
  **Evidencia prevista:** parser de `tests/soporte_observabilidad_024.py` y `curl /metrics`.
  **Evidencia:** 6 pruebas de T6; seis familias en `/metrics` y `route="rate_limited"` en
  `compustock_http_requests_total` (evidencia §3.2).
- [x] **AC-13 — Sin PII.** Con una IP de prueba (`203.0.113.7`), ni `/metrics` ni las líneas
  de log ni el cuerpo del 429 contienen esa IP, la clave `compustock:limite:` ni un token; la
  etiqueta `route` de los 429 es el valor reservado.
  **Evidencia prevista:** prueba unitaria de exposición y logs.
  **Evidencia:** prueba unitaria de exposición; logs y métricas sin IP, clave ni token
  (evidencia §3.2).
- [x] **AC-14 — Configuración y apagado.** Los defaults son `true`, `120`, `60`, `false` y
  `redis://127.0.0.1:6380/0`; un máximo o una ventana ≤ 0 impiden construir la app; una URL
  que no es Redis con el limitador encendido también; con `LIMITE_TASA_HABILITADO=false` el
  falso no recibe ninguna llamada y no hay middleware.
  **Evidencia prevista:** `tests/test_configuracion_025.py` y una prueba de apagado.
  **Evidencia:** `tests/test_configuracion_025.py` **11 passed**, incluida la prueba de
  apagado sin middleware ni llamadas al falso (evidencia §2).
- [x] **AC-15 — Estado compartido entre instancias.** Dos apps construidas con el mismo
  falso y máximo 3 comparten el contador: 2 peticiones en la primera y 2 en la segunda dan
  como resultado 3 permitidas y 1 rechazada. Ninguna app guarda el contador en proceso.
  **Evidencia prevista:** prueba unitaria con dos `crear_app(cliente_limite=falso)`.
  **Evidencia:** prueba de T4 con dos apps y el mismo falso: 3 permitidas y 1 rechazada.
- [x] **AC-16 — Redis real (gated).** Con `REDIS_TEST_URL`, máximo 3 y ventana 1 s: 3
  permitidas, la cuarta 429, el TTL está entre 1 y 1000 ms y la clave existe con la IP; tras
  vaciar la base o esperar la ventana vuelve a permitir; 20 evaluaciones concurrentes con
  máximo 10 dan exactamente 10 permitidas.
  **Evidencia prevista:** `tests/test_limite_tasa_redis_025.py` (*skipped* sin la variable).
  **Evidencia:** **3 passed** con `REDIS_TEST_URL=redis://127.0.0.1:6380/15` y **3 skipped**
  sin la variable; escenarios (a), (b) y (c) en verde (evidencia §5).
- [x] **AC-17 — Contrato, datos y alcance intactos.** 73 operaciones de matriz, 75 de
  OpenAPI, versión `021.1`, 27/24 tablas; sin cambios en `database/`, modelos, `permisos.py`,
  endpoints, esquemas, `response_model`, textos visibles ni `frontend/`; `requirements.txt`
  con 11 líneas pineadas; solo cambian `tests/conftest.py` y
  `tests/test_dependencias_024.py` entre los archivos preexistentes de prueba.
  **Evidencia prevista:** `git diff --stat` de las áreas protegidas y conteos de contrato.
  **Evidencia:** **75** OpenAPI, **73** matriz, `021.1`, **27/24** tablas; `requirements.txt`
  11 líneas todas `==`; diff protegido vacío (evidencia §6).
- [x] **AC-18 — Suites en verde.** `pytest` con **1596 + nuevas** pasadas, **88** omitidas y
  **0** fallos; *gated* PostgreSQL 16 en **73 passed**; *gated* Redis en verde; `ng test`
  **549 SUCCESS** sin tocar specs; `ng build` limpio.
  **Evidencia prevista:** salidas completas de las suites y del build.
  **Evidencia:** `pytest` **1660 passed / 88 skipped / 0 failed** (326,02 s); *gated*
  PostgreSQL **73 passed** (354,82 s); *gated* Redis **3 passed**; `ng test` **549 SUCCESS**;
  `ng build` limpio (50,66 s) (evidencia §6 y §10).
- [x] **AC-19 — Los dos puertos.** En **4200**, un recorrido funcional completo (login,
  dashboard, pedidos, inventario, compras y administración) hace del orden de 59 peticiones
  sin ningún 429. En **8080**, el humo muestra la aplicación operativa con 0×429; tras
  vaciar el estado del limitador, una ráfaga sostenida de ~5 r/s durante ~26 s (≈130
  peticiones) produce 429 **de la aplicación** con `X-RateLimit-*` —sin que nginx rechace,
  porque 5 r/s está por debajo de sus 10 r/s—; con
  `docker compose stop redis`, un recorrido normal sigue sin 429 (fail-open), el dashboard
  responde 200, `/ready` sigue 200 y el aviso aparece una vez cada 10 s.
  **Evidencia prevista:** pestaña de red y consola en ambos puertos, `curl` y `docker compose
  logs backend`.
  **Evidencia:** 4200 **24×200, 0×429** (11 Bodeguero + 13 Administrador); 8080 humo 2×200;
  ráfaga **120×401 + 10×429** de la app; fail-open **20×401**, dashboard/`/ready`/`/health`
  200 y aviso cada 10 s (evidencia §7 y §8).
- [x] **AC-20 — Dos workers.** Un uvicorn temporal con `--workers 2` y máximo 10 recibe 15
  peticiones: exactamente **10** no limitadas y **5** 429. Un contador en proceso habría
  permitido hasta 20.
  **Evidencia prevista:** ejecución manual con `docker compose exec redis redis-cli FLUSHDB`
  antes y después.
  **Evidencia:** **10×401 + 5×429** entre dos workers, con `X-RateLimit-*` en las cinco
  rechazadas; base 0 vaciada antes y después (evidencia §9).
- [x] **AC-21 — Documentación coherente.** `stack.md` (nuevo apartado del límite distribuido),
  `AGENTS.md` §3/§5, `README.md`, `roadmap.md`, `MEMORY.md` y la evidencia actualizados; el
  `grep` de coherencia no deja afirmaciones obsoletas y la caché de lecturas queda registrada
  como no asignada.
  **Evidencia prevista:** diff documental y grep de `AGENTS.md` §8.7.
  **Evidencia:** `stack.md` §1.2 y «seis familias», `AGENTS.md` §3/§5, `README.md`,
  `roadmap.md`, `MEMORY.md` y evidencia actualizados; caché sin feature asignada (evidencia
  §10).
- [x] **AC-22 — Dependencia analizada y reproducible.** `redis==8.1.0` es la única
  dependencia nueva; *wheel* `py3-none-any`, licencia MIT, Python ≥ 3.10 y sin transitivas
  obligatorias en 3.11.3/3.12; `pip check` sin problemas; la imagen del backend se construye
  y la suite de dependencias pasa a 11/11.
  **Evidencia prevista:** `pip check`, build de la imagen y `test_dependencias_024.py`.
  **Evidencia:** `pip check` limpio; `test_dependencias_024.py` **4 passed** con 11
  dependencias; imagen reconstruida y **healthy** (evidencia §1 y §8).

## 7. Riesgos y mitigación

| Riesgo | Probabilidad | Mitigación |
|---|---|---|
| El límite corta tráfico legítimo de la SPA | Media | Default de 120/min contra 59 medidas; AC-19 exige un recorrido completo sin 429 y el valor es configurable. |
| Varios usuarios tras una misma IP (NAT) comparten presupuesto | Media | Se documenta como límite conocido del esquema por IP; default holgado y configurable; el límite por identidad queda fuera con justificación. |
| Redis caído degrada la API | Media | Fail-open con timeouts de 200 ms y sin reintentos; el borde sigue limitando; AC-9, AC-11 y AC-19 lo verifican. |
| Redis en agujero negro añade latencia a cada petición | Media | Timeouts cortos; AC-10 exige < 1 s por petición; sin cortocircuito local por simplicidad, reevaluable con spec propia. |
| El aviso de fail-open inunda el log | Alta | Un `WARNING` cada 10 s por proceso; la métrica cuenta todos los fallos (R-6.3). |
| Claves sin TTL bloquean una IP para siempre | Baja | Script Lua atómico que fija el TTL y repara `PTTL < 0` en la misma ejecución (D-3); AC-4 y AC-16. |
| Cardinalidad de claves por IPs falsificadas | Baja | Validación de `X-Real-IP`, `trust=false` por defecto y `maxmemory`+LRU; Redis no se publica. |
| El cliente síncrono bloquearía el bucle de eventos | Media | Se usa `redis.asyncio` (D-9); la suite *gated* y los dos workers lo ejercitan. |
| El 429 llega al navegador como error de CORS | Media | CORS envuelve al limitador; AC-3 y AC-8 comprueban ACAO y preflight. |
| Dos límites (nginx y app) confunden al usuario | Baja | Texto de `detail` idéntico y `X-RateLimit-*` solo en el 429 de la app; AC-19 distingue el origen por cabeceras. |
| La suite de 1596 pruebas se vuelve lenta o ruidosa | Alta | `conftest` apaga el limitador antes de importar la app; las pruebas nuevas lo encienden con falso o Redis real (D-10). |
| `test_dependencias_024.py` rompe al añadir Redis | Alta | Se actualiza a 11/11 conservando su intención exacta; se declara en R-9.6 y AC-17 y AC-22. |
| El límite se percibe como «caché» y se cierra la deuda equivocada | Media | §3.2 y R-10.5 dejan la caché de lecturas explícitamente sin feature asignada. |
| La ventana fija permite 2× en el borde entre ventanas | Baja | Consecuencia aceptada y documentada; el borde absorbe ráfagas y el default deja margen. |
| Redis 7.2 queda sin soporte y obliga a saltar de licencia | Baja | Versión pineada y aislada detrás del cliente; un cambio de servidor no toca el código de la app. |
| La prueba de dos workers se confunde con métricas multiproceso | Baja | §3.2 aclara que solo verifica el estado compartido; el modelo de métricas de la 024 no cambia. |

## 8. Plan de verificación de cierre

1. **Suites.** `pytest` completo desde el host (con `redis==8.1.0` instalado) con 0 fallos y
   los 88 `skipped` de la línea base; *gated* PostgreSQL con `POSTGRES_TEST_URL` en 73
   passed; *gated* Redis con `REDIS_TEST_URL=redis://127.0.0.1:6380/15` en verde; `ng test
   --watch=false --browsers=ChromeHeadless` (con `CHROME_BIN`) en 549 SUCCESS; `ng build`
   limpio.
2. **Contrato.** `/openapi.json` en vivo: 75 operaciones, sin rutas nuevas;
   `MATRIZ_PERMISOS`: 73; versión `021.1`; 27/24 tablas.
3. **Redis real.** `docker compose up -d` deja el servicio *healthy*; `redis-cli --scan
   --pattern 'compustock:limite:*'` muestra la clave de la IP de prueba con `TTL` ≤ 60;
   `FLUSHDB` limpia el estado; el servicio no tiene volumen ni persistencia.
4. **429 y fail-open.** Ráfaga controlada contra 8000 y 8080 con las cabeceras de R-5; 429
   con `X-Request-ID` y ACAO; `docker compose stop redis` deja la aplicación operativa, con
   un aviso cada 10 s, `resultado="error"` en `/metrics` y `/ready` en 200.
5. **Dos workers.** uvicorn temporal `--workers 2` en un puerto libre, máximo 10, 15
   peticiones → 10/5; limpiar la base de Redis al terminar.
6. **Recorrido en los dos puertos.** 4200 con el recorrido funcional completo (≈59
   peticiones, 0×429; aquí no hay nginx); 8080 sin rebuild de frontend —no cambia ningún
   archivo de `frontend/`— pero con el backend recreado por `docker compose up -d`; humo con
   0×429 y, tras `FLUSHDB`, la ráfaga de ~5 r/s que produce 429 de la app con
   `X-RateLimit-*`.
7. **Evidencia y documentación.** `evidencia/README.md` con suites, conteos, claves/TTL,
   respuestas y capturas; `stack.md`, `AGENTS.md`, `README.md`, `roadmap.md` y `MEMORY.md`
   actualizados; `grep` de coherencia de `AGENTS.md` §8.7.

## 9. Dependencias y supuestos

- **Dependencia nueva:** `redis==8.1.0` (D-9), verificada en PyPI el 15/Nov/2026:
  publicada el 30/Jul/2026, *wheel* `py3-none-any`, licencia MIT, Python ≥ 3.10, sin
  dependencias obligatorias en 3.11.3/3.12. Es la única dependencia que se añade; el
  frontend no añade ninguna.
- **Servidor Redis:** `redis:7.2-alpine`, la última línea BSD-3-Clause; sin persistencia y
  con memoria acotada (D-2).
- **Línea base al abrir la 025:** `pytest` **1596 passed / 88 skipped / 0 failed**; *gated*
  PostgreSQL **73 passed**; `ng test` **549 SUCCESS**; 73 operaciones de negocio / 75
  OpenAPI; versión `021.1`; 27/24 tablas.
- **Medición que fija el default:** 59 peticiones en el recorrido completo de 4200 y 34 en el
  humo de 8080 (evidencia de la 024). De ahí 120/min y no 60/min.
- **Un solo worker en el despliegue actual:** el backend corre sin `--workers`; la prueba de
  dos workers es una verificación temporal del estado compartido, no un cambio de despliegue.
  Las métricas siguen siendo por proceso, como en la 024.
- **Red y despliegue:** en producción el puerto del backend no se publica, Redis vive en una
  red privada con ACL/TLS y no se expone a Internet; `/metrics` se consume desde la red
  interna. En desarrollo, Redis se publica solo en loopback para las pruebas *gated* y el
  diagnóstico.
- **Supuesto de desarrollo:** el flujo de 4200 no pasa por nginx; el límite de la aplicación
  es el único activo ahí y todas las peticiones comparten la IP del par. El comportamiento
  del borde se sigue verificando en 8080.
- **Datos:** ninguna pieza toca datos de negocio, tenants ni el modelo. Redis solo guarda
  contadores efímeros.
- **Docker disponible** para levantar Redis, detenerlo en la prueba de fail-open y ejecutar
  la suite *gated*.
- **La 024 no se reabre:** su spec, plan y tareas son históricos. El único cambio derivado es
  la prueba de dependencias (10 → 11) y la línea base documental.
