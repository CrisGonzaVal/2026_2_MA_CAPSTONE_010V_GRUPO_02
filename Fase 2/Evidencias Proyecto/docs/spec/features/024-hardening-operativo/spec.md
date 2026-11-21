# Feature 024: Hardening operativo I — observabilidad, CORS y borde

**Estado:** Implementada y cerrada (15/Nov/2026)
**Release:** 2.0 — Sprint 7 (hardening transversal)
**Tipo:** Endurecimiento operativo, sin valor de negocio directo y sin cambio de comportamiento observable
**Sucede a:** Feature 023 (mantenimiento técnico II, cerrada el 13/Nov/2026)

## 1. Problema

El sistema funciona y está cubierto por tests, pero **no es operable**: cuando algo falla en
producción no hay forma de correlacionar una respuesta con su traza, de saber si el servicio
puede atender tráfico o de medir latencia. El borde tampoco tiene ninguna defensa. La
evidencia es concreta y verificable en el código actual:

1. **`backend/app/main.py` no tiene observabilidad.** El archivo completo tiene 39 líneas:
   instancia `FastAPI`, monta CORS, incluye el router de v1 y define `/` y `/health`. No hay
   middleware de correlación, no hay un solo `import logging` en todo `backend/app/`
   (verificado por búsqueda), y `/health` devuelve `{"status": "healthy"}` **sin tocar la
   base**: es una cadena literal, así que responde 200 aunque PostgreSQL esté caído y el
   pool exhausto.
2. **CORS está fijado en duro al entorno local.** `main.py` declara
   `allow_origins=["http://localhost:4200", "http://localhost:8080"]`,
   `allow_methods=["*"]` y tres cabeceras. Un despliegue en otro dominio no puede
   configurarse sin editar código, y `allow_methods` concede métodos que la API no usa.
3. **`frontend/nginx.conf` no limita nada.** Tiene gzip, tres cabeceras de seguridad,
   `try_files` para Angular y el proxy a `/api/`; no hay `limit_req`, `limit_conn` ni
   `limit_req_status`. Cualquier cliente puede saturar el borde sin más costo que abrir
   conexiones.
4. **`backend/requirements.txt` no es reproducible.** De sus nueve líneas, solo `PyJWT` y
   `httpx` están pineadas con `==`; el resto usa `>=` (`fastapi>=0.115`, `sqlalchemy>=2.0`,
   `pydantic[email]>=2.0`, `pydantic-settings>=2.0`) o nada (`uvicorn`,
   `psycopg2-binary`, `python-dotenv`). Dos instalaciones en fechas distintas pueden
   producir árboles de dependencias distintos.
5. **El borde no es el camino real de la SPA, y eso es corregible.** `frontend/src/app/shared/config/url-api.ts`
   fija `URL_API = 'http://localhost:8000/api/v1'`: la SPA llama al backend **directo**,
   también cuando se sirve desde 8080. El proxy `/api/` de nginx existe pero hoy no recibe el
   tráfico de la aplicación, así que cualquier defensa puesta sólo en el borde no cubre ese
   camino, y el puerto `8000` está publicado en `docker-compose.yml`. La causa es una sola
   línea —una URL base absoluta— más la ausencia de un proxy en el servidor de desarrollo: sin
   él, una URL relativa rompería 4200. Esta feature corrige ambas cosas (B8).

**Impacto:** ninguna regresión funcional conocida. El costo es operativo: un incidente no
deja rastro correlacionable, un fallo de base no se distingue de un servicio sano, no hay
métrica alguna para decidir si el sistema se degrada, y el borde que se pretende endurecer no
está en el camino del tráfico real.

## 2. Objetivo

Dejar el servicio **observable y defendible en el borde** sin tocar una sola regla de
negocio, contrato de API ni dato:

- toda respuesta lleva un identificador de petición correlacionable con su línea de log;
- los logs son estructurados, parseables y libres de PII;
- la salud se separa en *liveness* (proceso vivo) y *readiness* (puede atender tráfico);
- existe una superficie de métricas operativas estable, de cardinalidad acotada y sin datos
  sensibles;
- el CORS se configura por entorno y sin comodines;
- el borde rechaza ráfagas con una respuesta que la SPA puede mostrar;
- la SPA consume la API por el mismo origen en 8080 y en producción, de modo que el borde
  queda efectivamente en el camino real (y el servidor de desarrollo hace de proxy en 4200);
- las dependencias directas del backend quedan pineadas y reproducibles.

## 3. Alcance

### 3.1 Dentro de alcance

| Bloque | Contenido |
|---|---|
| **B1 — Correlación** | Identificador de petición entrante/saliente y su disponibilidad para los logs. |
| **B2 — Logging** | Log estructurado JSON con la biblioteca estándar, nivel y formato configurables, sin access log duplicado. |
| **B3 — Salud** | `/health` como *liveness* sin base; `/ready` como *readiness* con comprobación de base. |
| **B4 — Métricas** | Exposición en formato Prometheus con las series mínimas y reglas de etiquetado. |
| **B5 — CORS** | Orígenes por entorno, métodos y cabeceras restringidos, credenciales, sin `*`. |
| **B6 — Borde** | Limitación de tasa y de conexiones por IP en nginx, con 429 JSON. |
| **B7 — Reproducibilidad** | Pineo exacto de las nueve dependencias directas y de la dependencia nueva de métricas. |
| **B8 — Camino real por el borde** | URL base relativa de la SPA, proxy de desarrollo para `/api` y verificación de que 8080 sirve la API a través de nginx. |

### 3.2 Fuera de alcance

- **Panel de métricas del Superadmin**: es otra feature; aquí solo se expone el endpoint.
- **Gate local `verificar.ps1`/`.cmd`**: no se crea.
- **GitHub Actions / CI**: requeriría `.github/workflows` en la raíz del repositorio, fuera
  de `Fase 2/Evidencias Proyecto/` (`AGENTS.md` §0).
- **Redis y cualquier caché**: Feature 025.
- **Paginación (026), refactor de servicios grandes (027), ESLint/Prettier y `shared/interfaces`
  (028), load testing (029)**.
- **Desacoplar `HTTPException` de los servicios.**
- **Desacoplar el árbol de dependencias transitivas**: solo se pinea el nivel directo.
- **Cambios de DDL, versión `021.1`, tablas 27/24, matriz de permisos (73 operaciones),
  contratos HTTP, `response_model`, textos visibles o comportamiento de negocio.**
- **Autenticación y autorización**: no se tocan. `/metrics`, `/health` y `/ready` quedan
  fuera de la matriz y sin Clerk **por diseño operativo**, no por concesión de permisos.
- **Frontend Angular**: no se toca salvo la excepción acotada de B8 —la URL base en
  `frontend/src/app/shared/config/url-api.ts`, el nuevo `frontend/proxy.conf.json` y el enlace
  de éste en `frontend/angular.json`—. **Ningún otro archivo bajo `frontend/src/**` cambia**:
  ni componentes, ni servicios, ni templates, ni tests de frontend. Nada de rutas REST,
  contratos, textos visibles ni dependencias de frontend.

## 4. Decisiones de diseño

### D-1 — Identificador de petición propio, opaco y validado

Se adopta la cabecera `X-Request-ID`: se **acepta la del cliente solo si es un UUID válido**
(en cualquier versión, forma canónica con guiones) y en cualquier otro caso se genera un
UUID4 nuevo; la respuesta siempre devuelve el valor efectivo.

- **Por qué no `traceparent` (W3C):** exige propagación de contexto entre servicios y un
  colector que hoy no existe; implementarlo a medias daría una traza que nadie puede
  consumir. Un identificador opaco resuelve el problema real —correlacionar una respuesta
  con su línea de log— sin dependencia ni protocolo.
- **Por qué validar la cabecera entrante:** un cliente puede enviar cualquier cadena; sin
  validación, un valor con saltos de línea o con longitud arbitraria se convierte en
  inyección de log y en un vector de cardinalidad. La validación es de formato, no de
  confianza: no concede nada.
- **Por qué UUID4 y no un contador:** no requiere estado compartido ni coordinación entre
  procesos y no filtra orden ni volumen de tráfico.

### D-2 — Logging con la biblioteca estándar, sin dependencia nueva

Se configura `logging` de la biblioteca estándar con un formateador JSON propio; el default
es `json` y `text` queda como opción local de desarrollo. Nivel por `LOG_LEVEL`.

- **Por qué no `structlog`/`loguru`:** agregan una dependencia y una API nueva a cambio de
  un formateador que son ~30 líneas; `AGENTS.md` §7 exige análisis previo y esta feature ya
  introduce una dependencia por un motivo más fuerte (B4). Se elige la opción con menos
  superficie y cero riesgo de arrastrar transitivas.
- **Por qué el formato es un ajuste y no un flag de despliegue oculto:** un log estructurado
  que solo existe en producción no se puede desarrollar contra él; `text` permite leer en
  local sin renunciar a `json` por defecto.
- **Por qué se desactiva el access log de uvicorn:** sin esa medida cada petición aparece dos
  veces, una en texto plano y otra en JSON, y la ingesta acaba con líneas no parseables. El
  access log propio es el único registro de peticiones.
- **Qué nunca se registra:** tokens, cabeceras completas, cuerpos, correos, query string ni
  identificadores de usuario o institución. El `path` se registra como **plantilla de ruta**
  cuando la ruta resuelve, y sin query string en cualquier caso.

### D-3 — `/health` es *liveness* y `/ready` es *readiness*; no se mezclan

`/health` conserva su contrato exacto (200 `{"status": "healthy"}`, sin base, sin Clerk) y
`/ready` ejecuta una comprobación trivial de conectividad contra la sesión de control.

- **Por qué no se amplía `/health` con la base:** el contenedor usa `/health` como healthcheck
  de Docker. Si `/health` fallara con la base caída, Docker reiniciaría el backend en bucle
  por un fallo que el proceso no puede resolver, y el reinicio destruiría la evidencia del
  incidente. `liveness` responde "el proceso está vivo"; `readiness` responde "puede atender
  tráfico".
- **Por qué `/ready` responde 503 sin detalle:** el cuerpo de un endpoint no autenticado no
  es lugar para el mensaje de `psycopg2`, que puede incluir host, base o usuario. El detalle
  va al log, correlacionado por el identificador de petición.
- **Por qué el readiness es acotado en el tiempo:** una base inalcanzable que no rechaza la
  conexión (blackhole) colgaría la sonda y con ella al orquestador. La sonda debe responder
  en un plazo corto y, si no puede confirmar conectividad, responder 503.
- **Por qué `/ready` no se usa como healthcheck del contenedor:** misma razón que `/health`;
  marcarlo como healthcheck convertiría un fallo de base en un reinicio del proceso.

### D-4 — Métricas con `prometheus-client`, cardinalidad acotada y registro propio

Se expone `GET /metrics` en formato de exposición Prometheus con cinco familias:
`compustock_http_requests_total{method,route,status}`,
`compustock_http_request_duration_seconds{method,route}` (histograma),
`compustock_http_requests_in_flight` (gauge),
`compustock_http_errors_total{status}` y `compustock_app_info{version,schema_version}`.

- **Por qué `prometheus-client`:** formato de exposición, histogramas con cubetas,
  concurrencia y *snapshot* consistente ya resueltos; reimplementarlos a mano significa
  escribir serialización y agregación bajo concurrencia —exactamente donde aparecen los bugs
  sutiles— sin ganar nada.
- **Por qué el histograma no lleva etiqueta de estado:** el estado ya vive en el contador de
  peticiones; duplicarlo multiplica las series del histograma por cada código sin responder
  ninguna pregunta nueva (la latencia por estado se obtiene del log).
- **Por qué el contador de errores existe si `requests_total` ya tiene `status`:** es una
  concesión a la operación, no un requisito de normalización: permite una alerta
  `rate(compustock_http_errors_total[5m]) > 0` sin conocer los códigos posibles.
- **`route` es siempre la plantilla de ruta** (`/api/v1/tickets/{ticket_id}`), nunca la ruta
  real: con identificadores en la etiqueta, un solo cliente genera una serie por ticket y el
  servidor de métricas se cae por cardinalidad, además de filtrar identificadores y permitir
  inyección de etiquetas. Una petición que no resuelve a ninguna ruta se agrega bajo un valor
  fijo reservado, nunca bajo la ruta cruda (un escáner que prueba miles de rutas no puede
  crear miles de series).
- **Por qué `/metrics` no se instrumenta a sí mismo:** el rastreo lo consume el propio
  servidor de métricas; contarlo ensucia la señal y añade series por cada *scrape*.
- **Por qué un registro propio y no el global:** el registro global comparte estado con
  cualquier instrumentación de terceros y, en tests, arrastra series entre casos y falla al
  re-registrar métricas tras recargar el módulo. Un registro propio de la aplicación hace
  determinista lo que se expone.
- **Por qué `schema_version` se lee de la constante y no se escribe:** el token de versión del
  esquema ya existe en la configuración; una copia literal en el módulo de métricas se
  desincroniza en la primera subida de versión y publica una mentira operativa.

### D-5 — `/metrics` se protege por red, no por rol

`/metrics` vive fuera de `/api/v1`, no pasa por Clerk, no entra en `MATRIZ_PERMISOS` ni en el
documento OpenAPI, y no se publica a través del borde.

- **Por qué no por rol:** ningún rol del dominio es "operador de métricas"; el Superadmin es
  un actor de negocio y añadirle una operación de infraestructura ensucia la matriz y ata la
  observabilidad a Clerk (un incidente de autenticación dejaría el sistema ciego). La
  frontera correcta es de red: el endpoint se consume desde la red interna o un *scraper*
  autorizado, y en producción el puerto del backend no se publica.
- **Por qué fuera de OpenAPI:** exponer en el contrato una ruta que no es API REST invita a
  consumirla con credenciales de usuario y rompe el invariante "todo `/openapi.json` es
  contrato con Bearer". El contrato se mantiene en **75 operaciones** y la matriz en **73**.
- **Por qué `/ready` también queda fuera del contrato:** misma naturaleza operativa, sin
  `response_model` de negocio; documentarlo obligaría a tocar las aserciones absolutas del
  contrato sin ganar nada. `/health` se conserva documentado porque ya lo está.
- **Por qué nginx no lo proxifica:** el borde sirve a Internet; una ruta interna que se
  publica por descuido en el `location /` de una SPA se convierte en la vía más simple para
  que un tercero aprenda la topología del servicio. Se niega explícitamente.

### D-6 — CORS por entorno, sin comodines

Los orígenes se leen de `ALLOWED_ORIGINS` (lista separada por comas; default
`http://localhost:4200,http://localhost:8080`), con métodos restringidos a
`GET, POST, PUT, PATCH, DELETE, OPTIONS`, cabeceras `Authorization, Content-Type, Accept` y
`allow_credentials=True`.

- **Por qué `*` es inaceptable aquí:** con credenciales, el navegador rechaza el comodín y el
  servidor no puede emitirlo; un "arreglo" habitual es reflejar el origen recibido, que es
  equivalente a permitir todos. La lista explícita por entorno es la única configuración
  honesta.
- **Por qué restringir métodos:** hoy se declara `*`; la API no usa `HEAD` ni `TRACE` y no
  necesita anunciarlos. La lista es la de los métodos realmente expuestos.
- **Por qué fallar al arrancar con la lista vacía:** un `ALLOWED_ORIGINS=""` en producción
  dejaría la SPA rota con un 200 del backend y un error de CORS en el navegador, que es el
  diagnóstico más caro de encontrar. Fallar rápido y claro es más barato que un fallback
  silencioso al default de desarrollo.
- **Qué cambia con B8 y qué no:** al consumir la API por el mismo origen (`/api/v1`), el
  navegador deja de necesitar CORS en 4200 (proxy del servidor de desarrollo) y en 8080
  (nginx delante del mismo origen). La configuración CORS **no se retira**: sigue siendo
  necesaria para clientes externos, herramientas y un futuro frontend en otro dominio, y por
  eso se mantiene por entorno y con lista explícita. Lo que sí desaparece es la dependencia
  del origen local escrito en código: la lista por defecto existe para el desarrollo, no
  porque el navegador la necesite.

### D-7 — La limitación de tasa va en el borde, no en la aplicación

nginx aplica `limit_req` por IP sobre `/api/`, `limit_conn` por IP y `limit_req_status 429`.

- **Por qué en el borde:** rechazar antes de FastAPI evita gastar un *worker* y una conexión a
  PostgreSQL por petición abusiva; el limitador del borde no compite con el trabajo útil.
- **Por qué no en la aplicación:** un limitador en proceso no comparte estado entre
  procesos, se reinicia con el servicio y no protege el puerto de entrada. La alternativa
  correcta en la app requiere un almacén compartido —Redis— que es la Feature 025.
- **Por qué la respuesta es JSON con `detail`:** los helpers de error de la SPA leen `detail`;
  devolver HTML haría que el usuario viera un mensaje genérico. Se conservan además las
  cabeceras CORS **sólo en esa respuesta de error**, porque un 429 sin
  `Access-Control-Allow-Origin` llega al navegador como error de CORS y oculta la causa real.
- **Por qué hay *burst* y no un límite seco:** la carga inicial de una SPA dispara varias
  peticiones simultáneas legítimas (identidad, dashboard, catálogos). Un límite seco rompe la
  aplicación para el usuario normal; el *burst* absorbe el pico y solo castiga la ráfaga
  sostenida.
- **El borde sí queda en el camino real.** Desde B8 la SPA consume `/api/v1` en el mismo
  origen: en 8080 y en producción la petición pasa por nginx, así que el límite se aplica al
  tráfico real del usuario y no solo a `curl`. Por eso el *burst* deja de ser una precaución
  teórica y pasa a ser un parámetro que hay que verificar contra la carga de arranque real de
  la SPA.
- **Por qué en 4200 no hay límite y por qué es aceptable:** `npm start` sirve la SPA en el
  puerto 4200 desde el servidor de desarrollo de Angular, que reenvía `/api` al backend
  mediante el proxy de desarrollo; **nginx no interviene**. Un límite de tasa en el dev server
  castigaría la recarga en caliente, el *HMR* y la depuración, y no protegería nada: 4200 es un
  entorno local de una sola persona. La consecuencia queda declarada: el comportamiento del
  borde se verifica en 8080, no en 4200, y el 429 no se reproduce en el puerto de desarrollo.
- **Límite que permanece, y es de despliegue:** el puerto `8000` sigue publicado **solo en
  desarrollo** para diagnosticar y para el recorrido directo de la API. En producción no se
  publica: si se publicara, un cliente podría saltarse el borde —y el límite— sin pasar por
  nginx. Es una decisión de despliegue, no un defecto del código, y queda registrada en §10.

### D-8 — Pineo exacto del nivel directo

Las nueve dependencias directas se fijan con `==` a las versiones ya instaladas y
verificadas: `fastapi==0.142.2`, `uvicorn==0.54.0`, `SQLAlchemy==2.1.1`,
`psycopg2-binary==2.9.13`, `pydantic[email]==2.13.5`, `pydantic-settings==2.15.0`,
`python-dotenv==1.2.3`, `PyJWT[crypto]==2.15.1`, `httpx==0.28.1`.

- **Por qué el nivel directo y no un `pip freeze`:** pinear transitivas sin un
  `constraints.txt` mantenido congela conflictos futuros y produce diffs ilegibles; el nivel
  directo elimina la ambigüedad que hoy importa (qué versión de `fastapi` se despliega) sin
  fingir que el árbol está bloqueado.
- **Por qué estas versiones y no las mínimas declaradas:** son las que el proyecto ejecuta y
  con las que las suites están en verde; pinear a la baja sería cambiar el runtime sin
  necesidad y sin verificación.

### D-9 — `prometheus-client` es la única dependencia nueva

Se añade `prometheus-client` pineada. Análisis de dependencia exigido por `AGENTS.md` §7:
cliente **oficial** de Prometheus para Python, **Python puro** (sin extensión compilada, sin
`libpq` ni toolchain), **sin dependencias transitivas** y con licencia permisiva, mantenido
por el proyecto Prometheus. Se instala en la etapa `builder` de la imagen igual que el resto
del árbol, sin cambios de sistema.

- **Alternativa descartada — escribir la exposición a mano:** obliga a implementar
  serialización de histogramas y cubetas bajo concurrencia; más código propio crítico que el
  que se quiere evitar.
- **Alternativa descartada — OpenTelemetry SDK + exporter Prometheus:** resuelve trazas,
  métricas y logs, pero arrastra un SDK completo, un ciclo de vida de proveedores y una
  configuración que excede el objetivo de esta feature; su lugar sería una spec de
  observabilidad distribuida.
- **Versión fijada: `prometheus-client==0.26.0`.** Verificada contra PyPI: publicada el
  **24/Jul/2026**, *wheel* `py3-none-any` (Python puro), licencia `Apache-2.0 AND BSD-2-Clause`,
  requiere Python >= 3.9 y **no declara dependencias de instalación**. Esa combinación —sin
  transitivas, sin extensión compilada, compatible con la imagen `python:3.12-slim` y con el
  intérprete del host— es la que hace aceptable la única dependencia nueva de la feature.

## 5. Requisitos funcionales

### R-1 — Identificador de petición

1. Toda respuesta HTTP, sea cual sea su origen (éxito, error de validación, error de negocio,
   excepción no controlada, ruta inexistente, `/health`, `/ready`, `/metrics`), incluye la
   cabecera `X-Request-ID` con un UUID en forma canónica.
2. Si la petición trae `X-Request-ID` con un UUID válido, se devuelve ese mismo valor, sin
   normalizar mayúsculas ni reescribirlo. Si trae un valor no válido o no lo trae, se genera
   un UUID4.
3. El valor efectivo queda disponible para el registro de logs de la petición en curso y
   **no se filtra** a la petición siguiente.
4. No se altera ningún cuerpo de respuesta ni ningún `response_model`: la cabecera es
   aditiva.

### R-2 — Log estructurado

1. Cada petición produce **una** línea de log con los campos: `timestamp` (UTC ISO-8601),
   `level`, `logger`, `message`, `request_id`, `method`, `path`, `status`, `duration_ms`.
2. `path` es la plantilla de ruta cuando la ruta resuelve y, en cualquier caso, nunca incluye
   query string.
3. El nivel se deriva del resultado: `ERROR` para 5xx, `WARNING` para 4xx, `INFO` para el
   resto.
4. `LOG_FORMAT` admite `json` (default) y `text` (una línea legible, mismos campos).
   `LOG_LEVEL` filtra por nivel. Un valor no reconocido de `LOG_FORMAT` cae a `json`; uno de
   `LOG_LEVEL` inválido no rompe el arranque.
5. No aparecen en el log tokens, cabeceras completas, cuerpos, correos, query string ni
   identificadores de usuario o institución.
6. El access log de uvicorn se desactiva en el comando de arranque (imagen y orquestador), de
   modo que `docker compose logs backend` muestra **una** línea por petición.

### R-3 — Salud

1. `GET /health` conserva exactamente su contrato: 200 `{"status": "healthy"}`, sin base de
   datos, sin Clerk, documentado en OpenAPI.
2. `GET /ready` comprueba conectividad con la base (sesión de control) y responde 200
   `{"status": "ready"}` o 503 `{"status": "not_ready"}`. El cuerpo del 503 no contiene
   mensaje de error, host, base, usuario ni traza.
3. El fallo de la comprobación se registra en el log con el `request_id` de la petición, sin
   credenciales ni cadena de conexión.
4. La respuesta de `/ready` se produce en un plazo acotado (≤ 2 s) aunque la base no
   responda.
5. Ninguno de los dos endpoints exige Bearer ni entra en la matriz de permisos.

### R-4 — Métricas

1. `GET /metrics` responde con `Content-Type` de texto Prometheus y expone como mínimo:
   - `compustock_http_requests_total{method,route,status}` (contador),
   - `compustock_http_request_duration_seconds{method,route}` (histograma),
   - `compustock_http_requests_in_flight` (gauge),
   - `compustock_http_errors_total{status}` (contador, `status` ≥ 400),
   - `compustock_app_info{version,schema_version}` (gauge con valor 1).
2. `route` es siempre la plantilla; ninguna etiqueta contiene un identificador real, un
   correo, un usuario, una institución ni un tenant. Una petición sin ruta resuelta se agrega
   bajo un valor fijo reservado.
3. `/metrics` no se instrumenta a sí mismo.
4. `version` es la versión de la aplicación y `schema_version` es la constante de versión de
   esquema vigente (`021.1`), leída de la fuente única.
5. El endpoint vive fuera de `/api/v1`, no exige Clerk, no figura en `MATRIZ_PERMISOS` ni en
   `/openapi.json`, y no se publica a través de nginx.

### R-5 — CORS

1. Los orígenes se leen de `ALLOWED_ORIGINS` (coma-separados, espacios recortados, entradas
   vacías descartadas); sin la variable, el default es
   `http://localhost:4200,http://localhost:8080`.
2. Una lista resultante vacía impide el arranque con un mensaje de configuración claro.
3. Se permite `GET, POST, PUT, PATCH, DELETE, OPTIONS` y las cabeceras
   `Authorization, Content-Type, Accept`, con `allow_credentials=True`.
4. No se declara ni se refleja `*` en orígenes, métodos ni cabeceras.
5. El preflight `OPTIONS` sigue funcionando y un origen no listado no recibe cabecera de
   permiso.

### R-6 — Borde

1. nginx limita peticiones y conexiones por IP sobre `/api/` y responde **429** con cuerpo
   JSON `{"detail": "..."}` y `Content-Type` JSON cuando se supera el límite.
2. La ráfaga admisible absorbe la carga inicial de la SPA (varias peticiones simultáneas
   legítimas); solo la ráfaga sostenida se rechaza.
3. La respuesta 429 incluye `Access-Control-Allow-Origin` con el origen de la petición
   cuando ésta la trae, y **sólo** en esa respuesta de error.
4. Los recursos estáticos y las rutas de la SPA no quedan sujetos al límite de peticiones.
5. `/metrics` no se proxifica; una petición a `8080/metrics` no devuelve formato de
   exposición Prometheus.

### R-7 — Reproducibilidad

1. Las nueve dependencias directas del backend quedan con `==` y las versiones de D-8.
2. `prometheus-client` se añade pineada (D-9).
3. No se añade ninguna otra dependencia ni se cambia ninguna versión existente.

### R-8 — Camino real por el borde

1. La URL base de la API en la SPA es **relativa** (`/api/v1`): sin esquema, sin host y sin
   puerto. La cadena `localhost:8000` no aparece como URL base en `frontend/src/`.
2. En **8080** y en producción las peticiones de la SPA a `/api/v1/*` se resuelven por el mismo
   origen, es decir, atraviesan nginx y quedan sujetas al límite del borde.
3. En **4200**, `npm start` reenvía `/api` al backend mediante el proxy de desarrollo, de modo
   que la SPA funciona igual tras la URL relativa, sin CORS y sin editar código al cambiar de
   puerto.
4. El prefijo `/api/v1`, las rutas REST, los cuerpos de petición y respuesta y los
   `response_model` no cambian.

## 6. Criterios de aceptación

- [x] **AC-1 — Cabecera en toda respuesta.** DADO cualquier endpoint (`/`, `/health`,
  `/ready`, `/metrics`, una operación autenticada de `/api/v1`, una ruta inexistente y una
  respuesta 4xx de validación), CUANDO se invoca, ENTONCES la respuesta trae `X-Request-ID`
  con un UUID en forma canónica. El cuerpo y el `status` no cambian respecto de la línea base.
  **Evidencia:** `tests/no_funcional/seguridad/test_correlacion_024.py` cubre `/`, `/health`, operación
  autenticada, 404, 422, preflight y 500; las 59 peticiones del recorrido en 4200 llevaron la
  cabecera.
- [x] **AC-2 — Identificador entrante respetado y saneado.** Con `X-Request-ID` de UUID válido
  se devuelve ese valor idéntico; con `abc`, con cadena vacía, con un UUID sin guiones y sin
  cabecera, se devuelve un UUID4 distinto del enviado.
  **Evidencia:** `test_uuid_entrante_valido_se_devuelve_identico`,
  `test_uuid_entrante_invalido_se_reemplaza` (parametrizado) y
  `test_sin_cabecera_entrante_se_genera_uuid`.
- [x] **AC-3 — Sin fuga entre peticiones.** Dos peticiones consecutivas producen
  identificadores distintos y cada línea de log lleva el de su propia respuesta; tras
  terminar la petición el contexto no conserva el valor anterior.
  **Evidencia:** `test_dos_peticiones_consecutivas_no_comparten_identificador`; el
  formateador JSON descarta campos fuera de la lista blanca y cada línea real lleva su UUID.
- [x] **AC-4 — Log JSON parseable y correlacionado.** Con `LOG_FORMAT=json`, cada línea de
  petición se parsea como JSON y contiene los nueve campos de R-2.1; `request_id` coincide
  con la cabecera de esa respuesta; `path` es la plantilla (`/api/v1/tickets/{ticket_id}`)
  y no incluye query string.
  **Evidencia:** `test_formateador_json_emite_los_nueve_campos_parseables`; log real de
  `/api/v1/dashboard/` con `path` de plantilla y sin query string.
- [x] **AC-5 — Sin PII ni secretos.** Una petición que envía `Authorization: Bearer <token>`,
  un correo en el cuerpo y un correo en el query string produce una línea de log que **no
  contiene** el token, el correo, ni el query string; tampoco `set-cookie`.
  **Evidencia:** `test_el_log_de_acceso_no_contiene_token_correo_ni_query`; sobre 244 líneas
  reales, 0 coincidencias de `Bearer`, `token`, `@example.com`, `password`, `secret`, `sk_` y
  `dvb_`.
- [x] **AC-6 — Formato y nivel configurables.** Con `LOG_FORMAT=text` la línea es legible y no
  es JSON válido; con `LOG_FORMAT` desconocido se usa JSON; `LOG_LEVEL=WARNING` suprime las
  líneas `INFO` de petición y conserva las de 4xx/5xx.
  **Evidencia:** `test_formateador_texto_es_legible_y_no_json`,
  `test_formato_de_log_desconocido_no_rompe_el_arranque` y
  `test_configurar_registro_warning_filtra_info_y_deja_handler_al_nivel`.
- [x] **AC-7 — Access log no duplicado.** En la imagen y en el comando del orquestador, el
  arranque de uvicorn incluye la desactivación del access log; una petición a
  `localhost:8000/health` seguida de `docker compose logs backend` muestra **una** sola línea
  de esa petición.
  **Evidencia:** `--no-access-log` en `backend/Dockerfile` y en `docker-compose.yml`; una
  petición a `/health` con `X-Request-ID` `0786b5e1-…` produjo una sola línea JSON y el log de
  30 min tuvo 0 líneas de access log de uvicorn.
- [x] **AC-8 — `/health` intacto.** `GET /health` responde 200 `{"status": "healthy"}` **con
  la base detenida**, no exige Bearer y sigue apareciendo en `/openapi.json` sin `security`.
  **Evidencia:** `test_health_responde_200_aunque_la_base_este_caida` y
  `test_health_sigue_documentado_sin_security_y_ready_no_aparece`; verificado también con
  `db` detenido.
- [x] **AC-9 — `/ready` correcto en ambos estados.** Con base disponible responde 200
  `{"status": "ready"}`; con el contenedor `db` detenido responde 503
  `{"status": "not_ready"}`; el cuerpo del 503 no contiene `psycopg2`, `connection`,
  `postgres`, ni el nombre de la base; el fallo aparece en el log con su `request_id`.
  **Evidencia:** `test_ready_responde_200_con_sqlite` y
  `test_ready_responde_503_saneado_y_correlacionado`; manual con `db` detenido: 503
  `{"status":"not_ready"}`, sin filtraciones y con `readiness_fallida` correlacionado.
- [x] **AC-10 — `/ready` acotado.** Con la base inalcanzable (host que no responde) `/ready`
  no tarda más de 2 s y responde 503.
  **Evidencia:** HTTP real contra un uvicorn temporal con `DB_HOST=192.0.2.1`: 503 en
  **1.02 s / 1.01 s / 1.02 s**; `TestClient`: 1.23 s / 1.01 s / 1.01 s.
- [x] **AC-11 — Métricas con las cinco familias.** Tras N peticiones a rutas conocidas,
  `GET /metrics` devuelve texto de exposición válido con las cinco familias de R-4.1; el
  contador suma exactamente esas peticiones (salvo `/metrics`), el histograma tiene cubetas y
  suma, y el gauge en vuelo vuelve a 0 al terminar.
  **Evidencia:** `test_metrics_expone_las_cinco_familias` y
  `test_contador_y_histograma_usan_etiquetas_acotadas`, con el parser de
  `tests/funcional/integracion/soporte_observabilidad_024.py`.
- [x] **AC-12 — Etiqueta `route` como plantilla.** Una petición a
  `/api/v1/tickets/{id_real}` produce la etiqueta `route="/api/v1/tickets/{ticket_id}"`; en
  ninguna etiqueta `route` aparece el identificador real. Una petición a una ruta inexistente
  con número (`/api/v1/desconocido/987654`) **no** crea una serie con esa ruta: se agrega bajo
  el valor fijo reservado.
  **Evidencia:** `test_ruta_con_identificador_se_agrega_como_plantilla` y
  `test_ruta_no_resuelta_se_agrega_bajo_unmatched`; el log real usa `path: "unmatched"`.
- [x] **AC-13 — Sin datos sensibles ni cardinalidad por identidad.** Ninguna etiqueta ni
  nombre de métrica contiene correo, usuario, institución, tenant, token ni query string; los
  conjuntos de nombres de etiqueta son exactamente los declarados en R-4.1.
  **Evidencia:** `test_exposicion_no_contiene_correo_token_usuario_ni_query` y el contraste
  exacto de etiquetas en `test_contador_y_histograma_usan_etiquetas_acotadas`.
- [x] **AC-14 — `/metrics` no se autoinstrumenta y no está protegido por Clerk.** Un *scrape*
  a `/metrics` no incrementa `compustock_http_requests_total` para esa ruta; el endpoint
  responde 200 sin `Authorization`.
  **Evidencia:** `test_metrics_no_se_instrumenta_a_si_mismo` y `test_metrics_no_exige_bearer`;
  `curl /metrics` → 200 sin `Authorization`.
- [x] **AC-15 — `/metrics` fuera de contrato y de la matriz.** `MATRIZ_PERMISOS` sigue con
  **73** operaciones y ninguna entrada de `/metrics`; `/openapi.json` sigue con **75**
  operaciones y no contiene `/metrics` ni `/ready`; `/health` sigue documentado.
  **Evidencia:** `test_openapi_publica_75_operaciones`,
  `test_rutas_operativas_no_aparecen_en_openapi`,
  `test_health_sigue_documentado_sin_security_y_ready_no_aparece` y
  `test_matriz_conserva_73_operaciones_y_ninguna_ruta_operativa`.
- [x] **AC-16 — `compustock_app_info` fiel.** El gauge vale 1, `version` es la versión de la
  aplicación y `schema_version` es `021.1`, tomada de la constante vigente (cambiar la
  constante cambia la etiqueta sin tocar el módulo de métricas).
  **Evidencia:** `test_app_info_publica_version_y_esquema` y
  `test_version_aplicacion_conserva_el_valor_publicado`.
- [x] **AC-17 — CORS por entorno.** Con el default, `Origin: http://localhost:4200` y
  `Origin: http://localhost:8080` reciben `access-control-allow-origin` y
  `access-control-allow-credentials: true`; un origen ajeno no recibe cabecera de permiso;
  con `ALLOWED_ORIGINS=http://otro.example` el default deja de permitirse y el nuevo se
  permite; `ALLOWED_ORIGINS=""` impide el arranque.
  **Evidencia:** `test_default_permite_los_dos_origenes_locales`,
  `test_origen_ajeno_no_recibe_cabecera_de_permiso`, `test_origenes_se_leen_del_entorno` y
  `test_lista_vacia_impide_construir_la_aplicacion`.
- [x] **AC-18 — CORS sin comodines.** El preflight devuelve métodos exactamente
  `GET, POST, PUT, PATCH, DELETE, OPTIONS` y cabeceras exactamente
  `Authorization, Content-Type, Accept`; ninguna cabecera CORS emitida vale `*`.
  **Evidencia:** `test_preflight_devuelve_metodos_y_cabeceras_exactos`,
  `test_preflight_de_origen_ajeno_no_emite_permiso` y
  `test_ninguna_cabecera_cors_vale_comodin`.
- [x] **AC-19 — 429 con el tráfico real de la SPA en 8080.** Contra `8080`, una ráfaga
  determinista de ≥60 peticiones `fetch` del mismo origen, disparadas desde la consola del
  navegador sobre una ruta de `/api/v1/` (el 401 también cuenta para el límite), produce al
  menos un **429** visible en la pestaña de red, con `Content-Type` JSON y cuerpo con `detail`;
  una carga normal (una sola recarga, ≈15 peticiones) responde completa sin 429, y los recursos
  estáticos no devuelven 429. La recarga en bucle y `curl` se admiten como evidencia
  complementaria, no como única prueba.
  **Evidencia:** ráfaga desde la consola de 8080: **30×401 + 30×429** con `detail`; recarga
  normal: **34 peticiones, 0×429**; estáticos 200.
- [x] **AC-20 — 429 legible por la SPA.** Al ser mismo origen, el navegador lee el 429 sin
  necesidad de CORS y el usuario ve el mensaje del `detail`. Además, una petición 429 con
  `Origin` de otro origen incluye `Access-Control-Allow-Origin` con ese origen; ninguna otra
  respuesta del borde refleja orígenes.
  **Evidencia:** el `fetch` same-origin leyó `{"detail":"Demasiadas peticiones…"}`; ráfaga
  `httpx` con `Origin: http://evil.example`: 20×401 + 40×429, los 429 con
  `Access-Control-Allow-Origin: http://evil.example` y `Vary: Origin`, las normales sin ACAO.
- [x] **AC-21 — `/metrics` no publicado por el borde.** `GET http://localhost:8080/metrics` no
  devuelve formato de exposición Prometheus (ni `# HELP` ni `compustock_`).
  **Evidencia:** `8080/metrics` y `8080/metrics/` → **404** sin `# HELP` ni `compustock_`.
- [x] **AC-22 — Dependencias reproducibles.** `backend/requirements.txt` declara las **10**
  dependencias directas con `==` y las versiones de D-8 más `prometheus-client`; una
  instalación en entorno limpio resuelve sin conflictos y `pip check` no reporta problemas; no
  hay dependencias directas nuevas fuera de `prometheus-client`.
  **Evidencia:** diez líneas con `==`, `pip check` → `No broken requirements found.` y
  `tests/funcional/unitarios/test_dependencias_024.py` → **4 passed**.
- [x] **AC-23 — Contrato, datos y permisos intactos.** Se conservan las **73** operaciones de
  la matriz, las **75** de OpenAPI, la versión `021.1`, las 27/24 tablas, los `response_model`
  y los textos visibles. No cambian `database/`, `backend/app/models/**`, `permisos.py`, los
  templates ni `.env`. Bajo `frontend/src/**` el **único** archivo que cambia es
  `shared/config/url-api.ts`; además aparecen `frontend/proxy.conf.json` y el enlace de éste en
  `frontend/angular.json`. Cualquier otro archivo de `frontend/src/**` con diferencias es una
  violación de alcance.
  **Evidencia:** 75/73, `021.1`, 27 `CREATE TABLE` de `control` + 24 plantillas de tenant;
  `git diff --stat` protegido solo muestra `frontend/src/app/shared/config/url-api.ts` (más
  `proxy.conf.json` y `angular.json`).
- [x] **AC-24 — Suites en verde.** `pytest` en verde sin fallos, con los tests nuevos de
  correlación, logging, salud y métricas y los 88 `skipped` de la línea base; los tests gated
  de PostgreSQL 16 siguen en verde. `ng test` se mantiene en **549 SUCCESS** sin modificar
  ningún spec: los specs de frontend que consumen la API importan `URL_API` y heredan la URL
  relativa, de modo que AC-23 no admite ninguna diferencia adicional bajo `frontend/src/**`.
  **Evidencia:** **1596 passed / 88 skipped / 0 failed** (238.87 s); gated PostgreSQL
  **73 passed** (se actualizaron snapshots obsoletos 26/23→27/24 y `020.1`→`021.1`, deuda de la
  021, sin tocar producción); `ng test` **549 SUCCESS** sin tocar specs.
- [x] **AC-25 — Ambos puertos con el mismo código.** En **4200**, el recorrido funcional
  (login, dashboard, pedidos, inventario y compras) se completa con la URL relativa servida por
  el proxy de desarrollo, sin errores nuevos de consola y con `X-Request-ID` en las respuestas.
  Tras `docker compose build frontend` + `up -d frontend`, el humo en **8080** muestra la
  aplicación operativa consumiendo `http://localhost:8080/api/v1/*` (mismo origen, visible en la
  pestaña de red), `8080/metrics` sin métricas y un 429 reproducible por ráfaga real de la SPA
  con cuerpo JSON.
  **Evidencia:** 4200: 59 peticiones same-origin, 0 4xx/5xx y 0×429; 8080 tras rebuild:
  dashboard 200, 34 peticiones/0×429, `/metrics` 404 y 30×429 en la ráfaga.
- [x] **AC-26 — Documentación coherente.** `stack.md` documenta la frontera operativa
  (`/health` *liveness*, `/ready` *readiness*, `/metrics` por red, formato de log, CORS por
  entorno, límites del borde y la API por mismo origen con proxy de desarrollo); `roadmap.md`
  registra la 024; `MEMORY.md` recoge estado y decisiones; el `grep` de coherencia sobre
  `AGENTS.md`, `MEMORY.md` y `.agents/skills/` no deja rutas ni afirmaciones obsoletas —en
  particular, ninguna que afirme que la SPA llama a `localhost:8000`.
  **Evidencia:** `stack.md` §1.1, `roadmap.md` con la 024 cerrada, `MEMORY.md` actualizado y
  grep de coherencia sin afirmaciones obsoletas.
- [x] **AC-27 — URL relativa y proxy de desarrollo.** `URL_API` vale `/api/v1` y la cadena
  `localhost:8000` no aparece como URL base en `frontend/src/`; `frontend/proxy.conf.json`
  reenvía `/api` al backend y `angular.json` lo declara en la configuración de `serve`; con
  `npm start` en 4200 una pantalla que consume la API (dashboard o inventario) carga datos
  reales sin error de conexión y sin CORS; con `ng build` de producción el bundle no contiene
  `localhost:8000` como URL base.
  **Evidencia:** `url-api.ts` → `/api/v1`; `proxy.conf.json` + `serve.options.proxyConfig`;
  dashboard y 59 peticiones reales en 4200 sin CORS; build de producción sin
  `localhost:8000`.

## 7. Riesgos y mitigación

| Riesgo | Probabilidad | Mitigación |
|---|---|---|
| Explosión de cardinalidad de métricas por rutas con identificadores | Media | `route` siempre plantilla; valor fijo reservado para lo no resuelto; AC-12 lo verifica con una ruta con número. |
| El límite del borde rompe la SPA legítima | Media | Ráfaga admisible dimensionada para la carga inicial; AC-19 verifica ambos lados (429 en abuso, 2xx en normal); los valores quedan como ajuste documentado. |
| Duplicación de líneas de log (uvicorn + middleware) | Alta | Desactivar el access log en imagen y orquestador; AC-7 lo verifica sobre `docker compose logs`. |
| El registro global de `prometheus-client` contamina los tests o falla al re-registrar | Media | Registro propio de la aplicación; AC-11/AC-14 lo comprueban ejecutando la suite completa; el plan fija cómo se aísla entre casos. |
| Un fallo del propio middleware de logs tumba la petición | Baja | El middleware no puede alterar el resultado: si el registro falla, la petición continúa; AC-1 lo cubre con errores y rutas inexistentes. |
| `LOG_FORMAT=text` acaba en producción y se pierde la estructura | Baja | El default es `json`; `text` exige declararlo; AC-4/AC-6 verifican ambos. |
| La sonda `/ready` se cuelga con una base inalcanzable | Media | Plazo acotado con respuesta 503; AC-10 lo verifica con un host que no responde. |
| El healthcheck del contenedor empieza a reiniciar por un fallo de base | Baja | `/ready` **no** se usa como healthcheck; `/health` conserva su contrato sin base (D-3, AC-8). |
| Falsa sensación de protección en el borde | Baja | B8 elimina la causa: la SPA consume `/api/v1` por el mismo origen y en 8080 pasa por nginx; el puerto `8000` solo se publica en desarrollo (D-7, AC-19, AC-27). |
| Olvidar el `proxyConfig` en `angular.json` y romper 4200 | Media | Es el único punto de fallo de B8 en desarrollo y produce un 404 de `/api` en todas las pantallas: AC-27 lo verifica con una pantalla que consume la API; el proxy se declara en la configuración de `serve`, no en `build`. |
| Specs de frontend que asuman la URL absoluta | Baja | Los specs interpolan `URL_API` y heredan el cambio; AC-24 exige **549 SUCCESS** sin tocar specs, y la suite detecta el caso si alguno la escribió a mano. |
| El bundle de producción conserve `localhost:8000` | Baja | La URL se centraliza en un único archivo; AC-27 verifica que el build de producción no la contiene. |
| Doble prefijo al pasar a URL relativa (`/api/v1` + `/api`) | Baja | El proxy y nginx reenvían `/api/` conservando el path; AC-25/AC-27 comprueban que las rutas REST responden 200 y que `/openapi.json` sigue en 75. |
| El pineo exacto rompe la resolución de dependencias en la imagen | Baja | Las versiones son las ya instaladas y verificadas; AC-22 exige instalación limpia y `pip check`. |
| `prometheus-client` introduce código compilado o transitivas | Baja | Análisis de D-9: Python puro, sin transitivas; la instalación en la etapa `builder` lo confirma en el build. |
| Cambio accidental del contrato al añadir rutas técnicas | Media | Ambas quedan fuera de OpenAPI (D-5); AC-15 fija 73/75 y AC-23 el resto de áreas protegidas. |

## 8. Plan de verificación de cierre

1. **Suites.** `pytest` completo desde el host (incluye los tests nuevos de B1–B4 y B5) con 0
   fallos y los 88 `skipped` de la línea base; tests gated de PostgreSQL 16 con
   `POSTGRES_TEST_URL`; `ng test --watch=false --browsers=ChromeHeadless` (con `CHROME_BIN`)
   sin regresiones; `ng build` limpio.
2. **Contrato.** `/openapi.json` en vivo: 75 operaciones, sin `/metrics` ni `/ready`, con
   `/health` sin `security`. `MATRIZ_PERMISOS`: 73 operaciones, sin entradas de las rutas
   operativas.
3. **Observabilidad real.** Con el stack arriba: peticiones a `/api/v1/*` con y sin
   `X-Request-ID`; `docker compose logs backend` con una línea JSON por petición, campos
   completos y sin token ni correo; `/ready` 200 con base arriba y 503 con `db` detenido;
   `/metrics` con las cinco familias y la etiqueta de plantilla.
4. **Recorrido funcional en 4200, a través del proxy de desarrollo.** `npm start` con
   `proxyConfig` activo: login, dashboard, pedidos, detalle, inventario, compras y
   administración; consola sin errores nuevos; pestaña de red mostrando peticiones a
   `http://localhost:4200/api/v1/*` (no a `localhost:8000`) y `X-Request-ID` en las respuestas.
   Aquí **no** se espera 429: el dev server no es el borde (D-7).
5. **Reconstrucción, humo y borde en 8080.** `docker compose build frontend` + `up -d frontend`
   (obligatorio: cambian `nginx.conf`, `url-api.ts` y `angular.json`); humo de la aplicación con
   la pestaña de red mostrando `http://localhost:8080/api/v1/*` servido por nginx, ráfaga real
   de la SPA que produce 429 con cuerpo JSON legible en pantalla, `8080/metrics` sin métricas y
   `8080/api/v1/*` coherente con el contrato.
6. **Evidencia.** `evidencia/README.md` con suites, conteos de contrato, salida de log
   redactada (sin tokens ni correos), respuestas de `/health`, `/ready` y `/metrics`, capturas
   de la pestaña de red en 4200 y 8080, del 429 y `git diff --stat` de las áreas protegidas
   (con `frontend/src/**` limitado a `url-api.ts`).
7. **Documentación.** `stack.md`, `roadmap.md` y `MEMORY.md` actualizados; `grep` de
   coherencia (`AGENTS.md` §8.7), incluida la búsqueda de `localhost:8000` en la documentación
   vigente.

## 9. Dependencias y supuestos

- **Dependencia nueva:** `prometheus-client==0.26.0` (D-9), verificada contra PyPI
  (24/Jul/2026, `py3-none-any`, `Apache-2.0 AND BSD-2-Clause`, Python >= 3.9, sin dependencias
  de instalación). Es la única dependencia que se añade; el frontend no añade ninguna.
- **Versiones instaladas:** las nueve de D-8 son las que el proyecto ejecuta hoy y con las que
  las suites están en verde.
- **Línea base de suites al abrir la 024:** `pytest` **1502 passed / 88 skipped / 0 failed**;
  `ng test` **549 SUCCESS**; 73 operaciones de negocio / 75 OpenAPI; versión `021.1`; 27/24
  tablas.
- **Un solo proceso de uvicorn:** el despliegue actual corre sin `--workers`, así que un
  registro de métricas en proceso refleja todo el tráfico. El modo multiproceso de
  `prometheus-client` queda fuera de alcance y se anota como supuesto: si se añaden *workers*,
  las métricas necesitan el agregador multiproceso.
- **Supuesto de red:** desde B8 la SPA consume `/api/v1` en el **mismo origen**. En 8080 y en
  producción ese origen es nginx, que es quien aplica el límite; el puerto del backend **no se
  publica** en producción y `/metrics` se consume desde la red interna o un *scraper*
  autorizado. En desarrollo el puerto `8000` sigue publicado para diagnosticar, y 4200 llega al
  backend por el proxy del servidor de desarrollo, no por nginx.
- **Supuesto de desarrollo:** el flujo de 4200 exige Node y el servidor de desarrollo de
  Angular; si `proxy.conf.json` no se resuelve, la SPA no alcanza la API. Es una dependencia de
  entorno local, no de despliegue.
- **Supuesto de datos:** ninguna de estas piezas toca datos de negocio, tenants ni el modelo;
  la comprobación de readiness usa una consulta trivial de conectividad sobre la sesión de
  control, sin SQL textual y sin leer ninguna tabla de dominio.
- **Docker disponible** para reconstruir la imagen del frontend y para detener `db` en la
  verificación de `/ready`.
