# Evidencia — Feature 028: Actualización en tiempo real de pedidos y tablero

**Feature:** `028-actualizacion-tiempo-real/`
**Spec:** [../spec.md](../spec.md) · **Plan:** [../plan.md](../plan.md) · **Tareas:** [../tasks.md](../tasks.md)
**Estado (28/Nov/2026):** **cerrada** con `@reviewer` **APROBADO**; los 32 AC quedan acreditados
y las excepciones se declaran en §8.3 y §10. La fila 028 del roadmap está en `[x]` (`AGENTS.md`
§8.5–§8.7). El recorrido manual se ejecutó en **4200** (sesiones reales) y en **8080** tras
reconstruir la imagen.

## 1. Resumen y decisiones clave

La 028 añade un canal **SSE** de una sola vía para que un cambio confirmado en un pedido, el
stock o una orden de compra se refleje sin recargar en el tablero, el detalle y el dashboard de
las demás sesiones autorizadas de la misma institución.

- **SSE, no WebSocket ni polling.** Un único endpoint `GET /api/v1/eventos/` por pestaña, sobre el
  mismo origen y con el mismo Bearer de Clerk. El navegador lo consume con `fetch` +
  `ReadableStream`, no con `EventSource` (que no permite enviar `Authorization`).
- **Evento de invalidación, no de datos.** El frame solo lleva `dominios`, `motivo` y `estado`.
  El cliente relee por los GET existentes (`/tickets/`, `/tickets/{id}`,
  `/tickets/{id}/historial`, `/dashboard/`), agrupa ráfagas (250 ms de silencio, 1 s de espera
  máxima) y refresca en silencio, sin perder filtros, orden, búsqueda, scroll, pestaña ni el
  texto de un diálogo abierto.
- **Sobre interno frente a frame.** El mensaje interno del bus (`SobreEvento`: institución,
  dominios de origen, motivo y `usuario_ids` de los dueños) es metadato de enrutamiento y nunca
  se serializa. El frame se construye **por conexión**, aplicando en orden institución →
  audiencia de dueño de `pedidos` → visibilidad por rol/capacidad → marca `dashboard`. Una
  recepción que desbloquea N pedidos publica **un** sobre y cada conexión recibe como máximo un
  frame por evento.
- **Aislamiento en servidor.** Administrador y Bodeguero reciben `pedidos` de su institución; el
  Solicitante solo los suyos; `compras` solo Administrador/Bodeguero; Superadmin 403. La
  institución sale solo de la identidad (mapa de control) y los parámetros de ámbito se ignoran.
- **Marca sintética `dashboard`.** Cuando `pedidos` o `inventario` no es visible pero la conexión
  tiene la capacidad `dashboard`, el servidor la sustituye por `{"dominios":["dashboard"],
  "motivo":"cambio"}`: refresca el dashboard sin nombrar el dominio ni el motivo ocultos.
- **Bus Redis efímero.** Pub/Sub del Redis de la 025 en `compustock:eventos:<institucion_id>`,
  con publicador síncrono y suscriptor `redis.asyncio`; el reparto entre procesos no depende de
  memoria local. Sin persistencia, sin `Last-Event-ID` y sin reproducción: cada apertura
  resincroniza por GET.
- **Publicación después del commit, best-effort y fail-open.** Toda mutación confirmada intenta
  publicar después del `commit`; una rechazada o revertida no publica. Un fallo del bus no cambia
  el status, el cuerpo ni la transacción, y `/ready` sigue midiendo solo la base. La cota del
  intento es **0,5 s**, sin reintento.
- **Vida de la conexión.** Cierre en `min(exp - 10 s, ahora + 300 s)`, con la expiración tomada
  del token validado; el cliente reabre con un token vigente, reevalúa institución y capacidades
  y resincroniza. La conexión no retiene una sesión del pool: el contexto se copia y la sesión se
  cierra antes de la espera.
- **Una conexión por pestaña.** El hub raíz `TiempoRealService` comparte el canal con el tablero,
  el detalle y el dashboard; retroceso 1/2/4/8/16/30 s con jitter, mínimo de 30 s entre
  aperturas, respeto de `Retry-After`, pestaña oculta sin refrescos y una resincronización al
  volver a foco.
- **Sin DDL ni dependencias.** Token **`026.1`**, **25** tablas en `control`, **22** por tenant y
  **21** entidades de dominio. Se reutilizan `redis==8.1.0` y `redis:7.2-alpine` de la 025; el
  frontend usa APIs nativas.

## 2. Suites y build (28/Nov/2026)

Suites **re-ejecutadas en T23 (28/Nov/2026)** sobre el estado final; el cierre añade el test de
AC-2 y deja la suite SQLite en **2323 passed** (T22 había medido 2322).

| Suite | Comando | Resultado real |
|---|---|---|
| Backend SQLite (suite completa) | `cd backend && .venv/Scripts/python.exe -m pytest -q` | **2323 passed / 135 skipped / 0 failed** (524,07 s; 2322 de T23 + el test nuevo de AC-2) |
| Gated PostgreSQL 16 — T13 | `POSTGRES_TEST_URL=postgresql://postgres:postgres@localhost:5433/postgres pytest tests/funcional/sistema/test_pool_tiempo_real_028.py -q` | **4 passed** (28,71 s) |
| Gated Redis — T14 | `REDIS_TEST_URL=redis://127.0.0.1:6380/15 pytest tests/no_funcional/rendimiento/test_bus_eventos_redis_028.py -q` | **4 passed** (2,70 s) |
| Seguridad T14 (SQLite, no gated) | `pytest tests/no_funcional/seguridad/test_tiempo_real_028.py -q` | **4 passed** (4,90 s) |
| Seguridad AC-2 (nuevo) | `pytest tests/no_funcional/seguridad/test_permisos_endpoint_028.py -q` | **8 passed** (7 casos previos + `test_token_en_url_o_cookie_no_autentica`) |
| Frontend | `$env:CHROME_BIN=…msedge.exe; npx ng test --watch=false --browsers=ChromeHeadless` | **758 SUCCESS / 0 failed** (Edge 158.0.0.0, 20,708 s) |
| Build de producción | `cd frontend && npx ng build` | **limpio**, 30,109 s; `main-UJT3LSFR.js` (13,54 kB raw), **Initial total 348,36 kB** (96,61 kB estimados) |

Los 135 skipped corresponden a los módulos gated que no se ejecutan sin `POSTGRES_TEST_URL` /
`REDIS_TEST_URL` (incluidos los 8 de esta feature y los heredados). Los **167 casos nuevos** de
los módulos `*_028*` se reparten así: **159** corren en SQLite y **8** son gated (4 PostgreSQL +
4 Redis); los 159 incluyen el test nuevo de AC-2. Sumado al caso nuevo de `test_auth.py` (T2),
el delta de la suite SQLite es **+160 passed** (2163 → 2323) y **+8 skipped** (127 → 135).

**Casos por módulo (colección real con `pytest --collect-only`):**

| Grupo | Archivos | Casos |
|---|---|---|
| Unitarios | `test_eventos_028.py` (22), `test_almacen_eventos_028.py` (15), `test_evento_service_028.py` (16), `test_contexto_tiempo_real_028.py` (12), `test_filtro_eventos_028.py` (15) | 80 |
| Integración | `test_eventos_endpoint_028.py` (5), `test_eventos_filtro_028.py` (11), `test_eventos_degradacion_028.py` (7), `test_publicacion_tickets_028.py` (14), `test_publicacion_retiro_028.py` (6), `test_publicacion_inventario_028.py` (8), `test_publicacion_compras_028.py` (11), `test_publicacion_recepcion_028.py` (5) | 67 |
| Seguridad | `test_permisos_endpoint_028.py` (8), `test_tiempo_real_028.py` (4) | 12 |
| Sistema (gated PostgreSQL) | `test_pool_tiempo_real_028.py` | 4 |
| Rendimiento (gated Redis) | `test_bus_eventos_redis_028.py` | 4 |

**Frontend:** dos specs nuevos — `tiempo-real.service.spec.ts` (21 casos) y
`refresco-agrupado.spec.ts` (9) — más los casos añadidos a `tickets.component.spec.ts` (112
totales), `ticket-detalle.component.spec.ts` (77), `dashboard.component.spec.ts` (23) y
`app.component.spec.ts` (34). La suite completa pasa de **701** (cierre de la enmienda 004) a
**758 SUCCESS**.

## 3. Contrato y gobierno

| Comprobación | Resultado real (28/Nov/2026) |
|---|---|
| `/openapi.json` | **75 operaciones**; incluye `/api/v1/eventos/` con respuestas **200, 401, 403, 429, 503** |
| Media type del 200 | `text/event-stream`; **sin** `content: application/json` (no hay `response_model` JSON) |
| Seguridad declarada | `HTTPBearer`; la excepción de `response_model` está descrita en la operación |
| `MATRIZ_PERMISOS` | **73** operaciones; `GET /api/v1/eventos/` → `{Administrador, Bodeguero, Solicitante}` |
| Esquema | token **`026.1`**, **25** tablas en `control`, **22** por tenant, **21** entidades |
| Dependencias | sin cambios en `requirements.txt` ni `package.json`; `redis==8.1.0` ya existía |

Comprobación viva contra el backend del Compose (`/openapi.json` y el objeto `app`):

```text
paths: 63 (75 operaciones) · eventos presentes: sí
200: text/event-stream · sin application/json
matriz: 73 · fila eventos: Administrador, Bodeguero, Solicitante
```

## 4. Hallazgos por tarea (los que cambian decisiones)

### 4.1 T0 — supuestos de partida

- **`TestClient` bufferiza SSE.** El transporte de Starlette 1.7 ejecuta la app hasta el final y
  devuelve el cuerpo en `io.BytesIO`; no entrega las primeras líneas ni cancela el generador al
  cerrar el contexto. `stream()` volvió a los 0,015 s y el contexto recién a los 2,062 s con un
  generador de 2,0 s. **Ajuste:** todos los tests del endpoint usan un flujo **acotado** (vida
  máxima, latido o `exp` cortos) y leen el cuerpo completo; el E2E real queda en el recorrido.
- **El proxy de desarrollo de Angular no bufferiza.** Con `ng serve` y un servidor SSE temporal,
  `listo` llegó a **268 ms** y los latidos a **~2 s**, con `content-encoding: null` incluso
  enviando `Accept-Encoding` con gzip. **No hizo falta `proxyTimeout: 0`** ni tocar
  `angular.json`; `proxy.conf.json` quedó igual.
- **`ReadableStream` falso en Karma/Edge** permite consumir frames partidos entre chunks y
  cancelar el `reader`; la lectura debe probarse en specs `async` (con `fakeAsync` la promesa del
  `reader` no se resuelve).

### 4.2 T13 — el 403 de PostgreSQL y el fix dialectal

El gated destapó que `contexto_tiempo_real` resolvía la institución con
`ambito_service.alcance_institucional` sobre la sesión de **control**. En PostgreSQL los
departamentos de los usuarios de negocio viven en su esquema tenant, así que **toda conexión SSE
de Administrador/Bodeguero/Solicitante respondía 403**; SQLite lo ocultaba por su contexto lógico
único. El rojo previo fue **3 failed / 1 passed**, todas por el 403.

Corrección: en PostgreSQL se usa `tenant_service.resolver_contexto_solicitud(db, correo)` (mapa de
control, sin abrir sesión tenant), con `ErrorInstitucionInactiva → 401`, `ErrorTenant → 403` y
`None → 403`; en SQLite se conserva `ambito_service`. El comportamiento aprobado no cambió, solo
el mecanismo. Tras el fix, `test_pool_tiempo_real_028.py` acredita **4 passed**, entre ellos
`GET /api/v1/eventos/` **200** con `listo` para una identidad de tenant real en PostgreSQL.
La deuda del doble camino queda registrada como **DT-18**.

### 4.3 T14 — fan-out, ventana y fail-open

- **Gated Redis (4 passed, base 15):** un sobre publicado se recibe por una suscripción real; dos
  `AlmacenRedisEventos` aislados (como dos procesos) comparten el bus y el frame `cambio` sale del
  Redis real, no de memoria local (`PUBSUB NUMSUB` confirma el suscriptor). Con Redis caído (URL a
  un puerto local cerrado, sin apagar el Redis compartido), la mutación conserva su **201** y su
  latencia (≤ base + 0,5 s) y `/ready` sigue en **200**. El fixture vacía la base **15** al
  empezar y al terminar y exige que la URL termine en `/15`; nunca se toca la base 0.
- **Seguridad (4 passed, SQLite):** con `VIDA_MAXIMA_CONEXION_SEGUNDOS=1`, la conexión vieja
  entrega un `cambio` antes de la ventana, descarta un sobre de otra institución y cierra al
  vencer (~1 s, no 300 s); un sobre posterior ya no se entrega. Con `tickets` apagado, `listo` no
  incluye `pedidos`, un sobre de pedidos solo produce la marca
  `{"dominios":["dashboard"],"motivo":"cambio"}` y `GET /tickets/` responde **403**. La institución
  inactiva (rama PostgreSQL del mapa) responde **401** y un correo sin mapa **403**.
- **Excepción aceptada:** el manual de dos procesos reales (`uvicorn app.main:app --workers 2`)
  no se ejecutó; el gated de dos instancias con Redis real y `PUBSUB NUMSUB` acredita el fan-out y
  el comando está en el docstring del módulo gated.

### 4.4 T21 — borde nginx

- `nginx -t` pasa en un `nginx:alpine` desechable sobre la red de Compose y dentro del contenedor.
- Imagen reconstruida: `evidenciasproyecto-frontend:latest`, ID **`3974188a383e`** (antes
  `985ef772f78f`); el contenedor quedó **healthy** y su `default.conf` contiene el `location`
  (línea 39). Verificado hoy: el contenedor sigue sirviendo la imagen `3974188a383e`.
- Con un upstream SSE temporal y este mismo archivo, `curl -N --trace-time` mostró `event: listo`
  en el primer paquete y un `: latido` cada 1 s, con `Transfer-Encoding: chunked`,
  `Content-Type: text/event-stream; charset=utf-8` y **sin** `Content-Encoding`.
- Contra 8080, `GET /api/v1/eventos/` sin token responde **401** del backend (con
  `x-request-id`). Una ráfaga de 60 peticiones al `location` exacto dio **20×401 + 40×429**, y el
  429 conservó `Content-Type: application/json`, el `detail` y `Access-Control-Allow-Origin:
  http://permitido.example` / `Vary: Origin`. Después de la ráfaga, `/api/v1/tickets/` y
  `/api/v1/dashboard/` siguen en **401**, `/` en **200** y `/metrics` en **404**.
- **Excepción aceptada:** el `curl -N` autenticado y 60 s abiertos en 8080 no se ejecutaron; el
  humo de T23 con sesión real en el navegador es la evidencia equivalente del canal a través de
  nginx. **Riesgo residual:** que el borde no corte un flujo autenticado de más de 60 s solo se
  demuestra con esa prueba, que queda declarada.

### 4.5 T23 — resultado del recorrido manual

Con sesiones reales de Solicitante, Administrador y Bodeguero en **4200** (28/Nov/2026):

- **AC-9/AC-11:** el Solicitante creó un pedido y el Administrador lo vio en su tablero **a los
  pocos segundos, sin recargar**; la edición de prioridad **Media → Alta** se reflejó **al
  momento**, también sin recargar.
- **AC-10:** la aprobación llevó el pedido a `EnCurso` y el Bodeguero lo vio sin recargar; abrió
  el detalle, registró el retiro (`Cerrado`) y el Solicitante recibió la acción de confirmar
  entrega; tras confirmar, Administrador y Bodeguero vieron **«Entregado»**. Todo sin recargar.
- **AC-12:** el dashboard del Administrador actualizó KPI y actividad durante el proceso;
  **tardó unos segundos**, dentro del objetivo de ≤5 s.
- **AC-14:** con **Periodo**, **Orden** y búsqueda activos, y un diálogo de anulación/rechazo
  abierto con motivo escrito, la llegada de un pedido nuevo actualizó el tablero **sin perder**
  filtros, orden, búsqueda, diálogo ni texto.
- **AC-13:** con un pedido `EnCurso` de un insumo con **stock 0**, el Administrador emitió y
  facturó una OC y el Bodeguero la recepcionó; el detalle del pedido pasó a
  `stock_disponible = true` y habilitó **«Registrar retiro»** sin recargar, y el Solicitante vio
  la etiqueta de proceso actualizada.
- **8080:** tras el rebuild de T21 (imagen **`3974188a383e`**), el tablero se actualizó en vivo a
  través de nginx, sin recargar.

**No reportado en esta pasada:** anulación y rechazo manuales, movimiento manual de stock, caída y
reconexión del backend, pestaña oculta, ventana de 3 minutos del límite de tasa, inspección del
log real, `curl -N` autenticado y frames en Network. **No hay capturas nuevas.** El manual de dos
workers no se repitió (ver §8.3).

## 5. Cobertura AC-1…AC-32

Leyenda: **A** = acreditado por tests automatizados; **A+M** = tests automatizados + recorrido
manual confirmado por el usuario el 28/Nov/2026; **M** = solo recorrido manual/documental, sin
test propio. Las excepciones manuales aceptadas por @reviewer se indican en la fila y se
detallan en §8.3 y §10.

| AC | Evidencia | Estado |
|---|---|---|
| **AC-1** | `test_eventos_endpoint_028.py::test_sesion_valida_abre_el_flujo_con_listo_y_sus_cabeceras` (200, `text/event-stream; charset=utf-8`, `Cache-Control: no-store`, `listo`); gated `test_pool_tiempo_real_028.py::test_eventos_abre_para_identidad_de_tenant_postgres_ac_1` (200 + `listo` en PostgreSQL); `tiempo-real.service.spec.ts` (fetch con `Accept: text/event-stream`, sin `EventSource`) | A |
| **AC-2** | `test_permisos_endpoint_028.py::test_token_en_url_o_cookie_no_autentica` (token en query y cookie → 401, mismo cuerpo que sin credencial), `::test_sin_authorization_responde_401`, `::test_superadmin_recibe_403_por_matriz_sin_suscribirse`, `::test_los_parametros_de_ambito_no_amplian_el_contexto`; `test_tiempo_real_028.py` (401 institución inactiva, 403 correo sin mapa); `test_contexto_tiempo_real_028.py` (403 sin institución) | A |
| **AC-3** | `test_eventos_endpoint_028.py::test_el_flujo_se_cierra_en_exp_menos_el_margen`; `test_auth.py::test_resolver_identidad_copia_el_exp_del_token_validado`; `test_contexto_tiempo_real_028.py::test_identidad_construida_sin_expira_en_conserva_el_default`; `tiempo-real.service.spec.ts` (reapertura y mínimo entre aperturas) | A |
| **AC-4** | `test_eventos_endpoint_028.py::test_emite_al_menos_un_latido_con_el_intervalo_corto`; T0 (proxy: `listo` 268 ms, latidos ~2 s, sin `content-encoding`); T21 (nginx: primer paquete `listo`, latido 1 s, chunked, sin `Content-Encoding`) | A (60 s y consola: excepción aceptada) |
| **AC-5** | `test_publicacion_tickets_028.py` (alta, edición, aprobación, confirmación, `PATCH`, anulación, rechazo) y `test_publicacion_retiro_028.py` (retiro y anulación desde `Cerrado`), con el bus falso; los casos `test_la_publicacion_*_ocurre_despues_del_commit` verifican el orden | A+M (alta, edición, aprobación, retiro y confirmación en 4200; anulación y rechazo no reportados) |
| **AC-6** | `test_publicacion_inventario_028.py` (movimiento → `inventario`); `test_publicacion_recepcion_028.py` (recepción → `inventario`+`compras`±`pedidos` y `test_detalle_del_bodeguero_refleja_stock_disponible_tras_la_recepcion`) | A+M (recepción y desbloqueo en 4200; movimiento manual no reportado) |
| **AC-7** | `test_publicacion_*_028.py`: casos 404/409/422, rollback forzado, doble envío 409 y `test_el_bus_caido_no_cambia_el_status_ni_el_cuerpo`; `test_la_publicacion_*_ocurre_despues_del_commit`; conteo de sobres en retiro/recepción | A |
| **AC-8** | `test_eventos_degradacion_028.py` (degradado/recuperado sin cerrar HTTP, retroceso 1/2/4/8/10, mutación con bus colgado dentro de la cota, `/ready` 200, línea de log sin PII); `test_almacen_eventos_028.py` (cota 0,5 s y timeout); gated `test_redis_detenido_conserva_la_respuesta_y_ready_200` | A |
| **AC-9** | `tickets.component.spec.ts` (frame `pedidos` → una recarga silenciosa, tarjeta sin recargar); `test_publicacion_tickets_028.py::test_alta_confirmada_publica_pedidos_con_motivo_alta` | A+M (Solicitante crea; el Administrador ve la tarjeta en segundos sin recargar; sin captura) |
| **AC-10** | Frames por transición: `test_publicacion_tickets_028.py` (aprobación, confirmación, anulación, rechazo), `test_publicacion_retiro_028.py` (retiro); specs de tablero y detalle con recarga silenciosa | A+M (aprobación → retiro → confirmación → «Entregado» en 4200; anulación y rechazo no reportados) |
| **AC-11** | `test_publicacion_tickets_028.py::test_edicion_confirmada_publica_pedidos_con_motivo_edicion`; `tickets.component.spec.ts` y `ticket-detalle.component.spec.ts` (refresco sin recargar) | A+M (prioridad Media → Alta vista al momento por el Administrador) |
| **AC-12** | `dashboard.component.spec.ts` (frame `pedidos`/`inventario`/`dashboard` → un GET, sin placeholder, conserva datos, Solicitante sin actividad); publicación de las mutaciones que lo invalidan | A+M (KPI y actividad se actualizaron en unos segundos, ≤5 s) |
| **AC-13** | `test_publicacion_recepcion_028.py::test_detalle_del_bodeguero_refleja_stock_disponible_tras_la_recepcion`; `ticket-detalle.component.spec.ts` (frame `inventario` actualiza `stock_disponible` y la acción de retiro) | A+M (stock 0 → OC emitida/facturada/recepcionada → `stock_disponible = true` y «Registrar retiro» sin recargar) |
| **AC-14** | `tickets.component.spec.ts` (periodo, orden, búsqueda y scroll), `ticket-detalle.component.spec.ts` (diálogo y motivo escritos), `refresco-agrupado.spec.ts` (ráfaga, uno en vuelo, uno pendiente, `cancelar`) | A+M (Periodo, Orden, búsqueda y diálogo con motivo conservados) |
| **AC-15** | `test_eventos_filtro_028.py::test_la_institucion_ajena_no_recibe_el_sobre_de_otra_institucion`; `test_filtro_eventos_028.py::test_sobre_de_otra_institucion_se_descarta_aunque_el_dominio_sea_visible`; `test_tiempo_real_028.py::test_un_correo_sin_mapa_de_control_no_abre_el_flujo_ac_15`; parámetros de ámbito ignorados | A |
| **AC-16** | `test_eventos_filtro_028.py` (dueño recibe; otro Solicitante no recibe ni la marca; Administrador y Bodeguero sí); `test_filtro_eventos_028.py` (misma matriz a nivel de filtro) | A |
| **AC-17** | `test_filtro_eventos_028.py` (capacidad apagada oculta el dominio; `compras` no sintetiza marca; sin `dashboard` no hay frame); `test_eventos_filtro_028.py`; `test_permisos_endpoint_028.py` (Superadmin 403) | A |
| **AC-18** | `test_eventos_endpoint_028.py::test_el_frame_listo_no_lleva_identificadores_ni_el_flujo_usa_id_o_retry`; `test_filtro_eventos_028.py::test_el_frame_serializado_no_lleva_ids_ni_institucion_ni_usuario`; `test_eventos_degradacion_028.py::test_la_linea_tiempo_real_registra_campos_permitidos_sin_pii` | A |
| **AC-19** | `tiempo-real.service.spec.ts` (401/403 sin reintento, 429 con `Retry-After`, 5xx/red con backoff y jitter, una sola conexión); `listo`/`recuperado` disparan resincronización | A |
| **AC-20** | `refresco-agrupado.spec.ts` (20 solicitudes → 1 ejecución; máximo 1 s; uno en vuelo; `cancelar`); `tiempo-real.service.spec.ts` (tope 30 s, mínimo 30 s entre aperturas, `Retry-After`) | A |
| **AC-21** | `tiempo-real.service.spec.ts` (una apertura y mínimo entre aperturas); T21 (ráfaga 60 en 8080: 20×401 + 40×429; el 429 conserva JSON y CORS); límite de la 025 ya probado | A (precisión aprobada: 4–5 aperturas/0×429; T14/T15/T21) |
| **AC-22** | `tiempo-real.service.spec.ts` (`document.hidden` no refresca; `visibilitychange` → una resincronización; no abre segunda conexión); `app.component.spec.ts` (una sola conexión al navegar) | A |
| **AC-23** | Gated Redis `test_bus_eventos_redis_028.py::test_dos_instancias_aisladas_comparten_el_bus_y_el_cambio_cruza_redis` (**4 passed** en total) | A (excepción aceptada: manual de dos workers no ejecutado; gated + `PUBSUB NUMSUB`) |
| **AC-24** | `test_permisos_endpoint_028.py::test_openapi_publica_la_operacion_sin_response_model_y_con_sus_respuestas`, `::test_openapi_y_matriz_suman_una_operacion`, `::test_la_matriz_declara_el_canal_para_los_tres_roles_institucionales`; aserciones absolutas de `test_contrato_024.py` y `test_permisos_retiro_013.py` ampliadas a **75/73** | A |
| **AC-25** | Suites: **2323/135/0**, gated **4+4+4**, `ng test` **758 SUCCESS**, `ng build` limpio (`main-UJT3LSFR.js`). Sin cambios en `database/`, modelos, `requirements.txt` ni `package.json`; token `026.1`, 25/22 tablas, 21 entidades | A |
| **AC-26** | Recorrido funcional en 4200 con dos o tres sesiones y humo autenticado en 8080; sincronización de `roadmap.md`, `MEMORY.md`, `stack.md` y `deuda-tecnica.md` | **M** (recorrido 4200/8080 y docs confirmados; `@reviewer` APROBADO; sin capturas, excepción aceptada) |
| **AC-27** | `test_publicacion_recepcion_028.py::test_recepcion_con_plan_y_desbloqueo_publica_un_sobre_con_la_union`; `test_publicacion_retiro_028.py::test_el_retiro_publica_un_solo_sobre_y_el_frame_no_lleva_ids`; `test_evento_service_028.py` (audiencia y dueños únicos); `test_filtro_eventos_028.py` (dueño correcto y otro no) | A |
| **AC-28** | `test_eventos_filtro_028.py::test_tickets_apagado_entrega_solo_la_marca_dashboard_sin_el_motivo_real`, `::test_inventario_apagado_entrega_la_marca_dashboard`, `::test_pedidos_e_inventario_apagados_producen_un_solo_frame_dashboard`; `test_filtro_eventos_028.py` (sin `dashboard` no hay frame); `dashboard.component.spec.ts` (la marca refresca solo el dashboard) | A |
| **AC-29** | Gated `test_pool_tiempo_real_028.py::test_cinco_flujos_ociosos_no_agotan_el_pool_ac_29` (pool 2/0/2 s, 5 flujos ociosos, `GET /tickets/` 200 sin `QueuePool limit`); `test_contexto_tiempo_real_028.py::test_contexto_cierra_la_sesion_antes_de_retornar` | A (4 passed con PostgreSQL) |
| **AC-30** | `test_publicacion_compras_028.py` (emisión, facturación, cancelación con y sin plan; corrección de facturada; alta/edición/proveedores/preview no publican); `test_publicacion_recepcion_028.py` | A |
| **AC-31** | `test_tiempo_real_028.py::test_la_conexion_vieja_entrega_antes_de_la_ventana_y_cierra_al_vencer_ac_31`, `::test_la_reapertura_no_incluye_el_dominio_apagado_y_la_lectura_responde_403_ac_31`, `::test_la_reapertura_con_la_institucion_inactiva_responde_401_ac_31` | A |
| **AC-32** | `test_eventos_028.py` (default `True` y validadores de rango); `test_permisos_endpoint_028.py::test_canal_apagado_responde_503_sin_abrir_el_flujo`; `tiempo-real.service.spec.ts` (401/403 no reintenta) y las vistas cargan por sus GET sin depender del canal | A |

## 6. Limitaciones aceptadas y fuera de alcance

- **Sin familia de métricas SSE.** `/metrics` no expone aperturas, conexiones ni eventos; la
  evidencia es la línea JSON `compustock.tiempo_real` (`request_id`, `route`, `resultado`,
  `motivo`). Registrado como riesgo aceptado **R-05** en `deuda-tecnica.md`.
- **Sin persistencia ni reproducción.** No hay tabla, `Last-Event-ID`, búfer ni replay; un evento
  perdido se recupera por relectura. La entrega es best-effort y a lo sumo una vez.
- **Vista de existencias y panel de recepciones fuera de la superficie mínima.** El dominio
  `inventario` se difunde porque alimenta el dashboard y la disponibilidad del pedido; esas dos
  vistas no se suscriben en esta entrega y pueden hacerlo después sin cambio de contrato.
- **Filtro por sede en la señal de inventario:** no existe; la lectura posterior ya está acotada
  por rol y se acepta la actividad agregada dentro de la institución, sin datos ni ids.
- **Recortes del plan no aplicados:** T11 (compras), T14 (gated multiproceso) y T13 (pool) se
  implementaron; no se ejerció ningún recorte de §11.4 del plan.
- **`TestClient` no acredita entrega incremental.** El gated de PostgreSQL usa `uvicorn` real y
  `httpx.Client.stream`; la suite SQLite lee flujos acotados completos. Registrado como **DT-17**.
- **Doble camino de resolución de institución por dialecto.** El camino de producción (mapa de
  control) solo lo acredita el gated; la comprobación de versión usa `control.version_esquema`,
  no el `version_esquema` del esquema tenant. Registrado como **DT-18**.
- **Lectura post-commit en `ticket_service._publicar_pedido`.** Lee `institucion_id` y
  `usuario_id` después del `commit`, fuera del `try` fail-open de `evento_service`. Registrado
  como **DT-19**.
- **La 028 no es la 016.** No hay centro de notificaciones, bandeja, contadores, marcas de leído,
  correo ni push; esas decisiones pertenecen a la Feature 016, que sigue pendiente.

## 7. Reproducción

```powershell
# Backend (SQLite, sin contenedores)
cd backend
.venv\Scripts\python.exe -m pytest -q

# Gated PostgreSQL (T13) — crea bases temporales, nunca toca apt_erp
$env:POSTGRES_TEST_URL = "postgresql://postgres:postgres@localhost:5433/postgres"
.venv\Scripts\python.exe -m pytest tests/funcional/sistema/test_pool_tiempo_real_028.py -q

# Gated Redis (T14) — exige terminar en /15 y usa 127.0.0.1, no localhost
$env:REDIS_TEST_URL = "redis://127.0.0.1:6380/15"
.venv\Scripts\python.exe -m pytest tests/no_funcional/rendimiento/test_bus_eventos_redis_028.py -q

# Seguridad de la ventana y del aislamiento
.venv\Scripts\python.exe -m pytest tests/no_funcional/seguridad/test_tiempo_real_028.py -q

# Frontend
cd ..\frontend
$env:CHROME_BIN = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
npx ng test --watch=false --browsers=ChromeHeadless
npx ng build

# Contrato y canal en el borde (sin token: 401)
curl.exe -s http://localhost:8000/openapi.json
curl.exe -s -o NUL -w "%{http_code}" http://localhost:8080/api/v1/eventos/
```

Frames del contrato (los que fija la suite; **no hay captura autenticada** de T23 y ninguna
captura debe incluir el token):

```text
event: listo
data: {"dominios":["pedidos","inventario","dashboard"]}

: latido

event: cambio
data: {"dominios":["pedidos"],"motivo":"retiro"}

event: cambio
data: {"dominios":["dashboard"],"motivo":"cambio"}

event: estado
data: {"estado":"degradado"}
```

## 8. Recorrido manual de cierre (T23, 28/Nov/2026)

### 8.1 4200 — sesiones reales y escritura

Recorrido ejecutado por el usuario con sesiones reales de **Solicitante, Administrador y
Bodeguero**. Resultados confirmados:

| AC | Observado |
|---|---|
| **AC-9** | El Solicitante creó un pedido y el Administrador lo vio en su tablero **a los pocos segundos, sin recargar**. |
| **AC-10** | Aprobación → `EnCurso`; el Bodeguero lo vio sin recargar, abrió el detalle y registró el retiro → `Cerrado`; el Solicitante vio la acción de confirmar entrega y confirmó; Administrador y Bodeguero vieron **«Entregado»**. Todo sin recargar. |
| **AC-11** | El Solicitante editó la prioridad de **Media a Alta** y el Administrador lo vio **al momento**, sin recargar. |
| **AC-12** | El dashboard del Administrador actualizó KPI y actividad durante el proceso; **tardó unos segundos**, dentro del objetivo de ≤5 s. |
| **AC-14** | Con **Periodo**, **Orden** y búsqueda activos, y un diálogo de anulación/rechazo abierto con motivo escrito, la llegada de un pedido nuevo actualizó el tablero **sin perder** filtros, orden, búsqueda, diálogo ni texto. |
| **AC-13** | Con un pedido `EnCurso` de un insumo con **stock 0**, el Administrador emitió y facturó una OC y el Bodeguero la recepcionó; el detalle pasó a `stock_disponible = true` y habilitó **«Registrar retiro»** sin recargar, y el Solicitante vio la etiqueta de proceso actualizada. |

No se reportaron en esta pasada: anulación y rechazo manuales, movimiento manual de stock, caída y
reconexión del backend, pestaña oculta y vuelta a foco, ventana de 3 minutos del límite de tasa ni
inspección del log real. **No hay capturas nuevas:** es una excepción aceptada y no se inventan
rutas.

### 8.2 8080 — humo a través de nginx

Tras el rebuild de T21 (imagen **`3974188a383e`**), el tablero se actualizó en vivo a través de
nginx, sin recargar. El usuario no registró el hash del bundle ni inspeccionó los frames en
Network. La imagen del contenedor sirve `main-UJT3LSFR.js` (comprobado en el sistema de archivos
del contenedor, no en Network). **El `curl -N` autenticado de T21 no se ejecutó:** el humo con
sesión real es la evidencia equivalente y la prueba de 60 s queda como **excepción aceptada** con
el riesgo residual declarado en §4.4.

### 8.3 Excepciones aceptadas por @reviewer

No son deuda oculta ni pendientes de cierre; quedan declaradas y aprobadas:

1. **T0 `TestClient` bufferiza SSE:** el supuesto era falso; el ajuste (flujos acotados y lectura
   completa) está aplicado y registrado como **DT-17**.
2. **T14 manual de dos workers:** no se ejecutó; el gated de dos instancias con Redis real y
   `PUBSUB NUMSUB` acredita el fan-out y el comando está en el docstring del módulo.
3. **T21 `curl -N` autenticado:** no se ejecutó; el humo 8080 con sesión real es la evidencia
   equivalente y el riesgo de 60 s queda declarado.
4. **AC-4:** no se midieron los 60 s autenticados ni la consola en 8080; la configuración, el
   latido y el borde están cubiertos por tests y T21.
5. **Sin capturas nuevas:** la evidencia manual es la confirmación del usuario.

## 9. Grep de coherencia documental (T22/T23)

Revisión final de rutas y afirmaciones sobre el estado del proyecto en `AGENTS.md`, `MEMORY.md` y
`.agents/skills/` tras la 028 (T23, 28/Nov/2026):

| Archivo | Hallazgo | Acción |
|---|---|---|
| `AGENTS.md` §4 | La enumeración de `app/api/v1/endpoints/` no incluía `eventos`. No era una ruta rota, pero quedaba incompleta. | **Corregido en T23:** `eventos` añadido al listado. |
| `AGENTS.md` §3 | El estado del stack no mencionaba el canal SSE ni el bus Redis de la 028. | **Corregido en T23:** línea «Tiempo real» que remite a `stack.md` §1.3; sin reglas ni prohibiciones nuevas. |
| `MEMORY.md` | Conservaba los conteos previos (2163/127, 701, `main-KSHSOEG4.js`, imagen `985ef7…`) y no mencionaba la 028. | **Corregido en T23:** estado, suites, bundle, imagen y decisiones de la 028; al cierre se añade el veredicto APROBADO y DT-19. |
| `.agents/skills/` | Sin rutas rotas ni afirmaciones obsoletas. La nota de `angular-standalone` sobre `Subject` para streams HTTP largos es condicional y el hub usa `fetch` + signals, así que no se contradice; `fastapi-pydantic-v2` sigue siendo coherente porque el router de eventos no toca la base (el contexto se resuelve en `dependencies.py` y la sesión se cierra allí). | Ninguna; no se editaron skills. |
| `docs/spec/stack.md` · `roadmap.md` · `deuda-tecnica.md` | Sincronizados: §1.3 nueva, fila 028 en `[x]`, DT-17/DT-18/DT-19 y R-05. | `stack.md` sin cambios; `roadmap.md` y `deuda-tecnica.md` actualizados al cierre. |

Las rutas citadas por la 028 existen y corresponden al código actual:
`backend/app/core/eventos.py`, `backend/app/services/evento_service.py`,
`backend/app/api/v1/endpoints/eventos.py`, `frontend/src/app/core/services/tiempo-real.service.ts`,
`frontend/src/app/shared/utils/refresco-agrupado.ts` y los módulos de prueba `*_028*`.

## 10. Validación @reviewer (28/Nov/2026)

**Veredicto: APROBADO, sin bloqueantes.** El informe revisó AC-1…AC-32 y aprobó las precisiones
de **AC-9** (el Solicitante es el único rol que crea), **AC-16** (el Solicitante no dueño puede
recibir `inventario` si la mutación mueve stock, sin revelar el pedido) y **AC-21** (**4–5
aperturas por sesión** en 3 min con **0×429**, con la ventana de renovación de T14/T15/T21). Las
seis filas «parcial» corresponden a verificaciones manuales no ejecutadas o a ambigüedades de
redacción, no a defectos; se aceptan como excepciones.

| Grupo | AC | Resultado |
|---|---|---|
| Acreditados por tests | AC-1, AC-2, AC-3, AC-5, AC-6, AC-7, AC-8, AC-15, AC-16, AC-17, AC-18, AC-19, AC-20, AC-22, AC-24, AC-25, AC-27, AC-28, AC-29, AC-30, AC-31, AC-32 | **Acreditado** |
| Tests + recorrido manual | AC-9, AC-10, AC-11, AC-12, AC-13, AC-14 | **Acreditado (A+M)** |
| Parcial/aceptado | AC-4 (60 s y consola), AC-21 (ventana de 3 min), AC-23 (manual de dos workers) | **Aceptado** |
| Recorrido + documentación | AC-26 (4200/8080; sin capturas) | **Aceptado (M)** |

**Test nuevo de AC-2.** `test_permisos_endpoint_028.py::test_token_en_url_o_cookie_no_autentica`:
un token en `?token=…` o en `Cookie: access_token=…` responde **401** con el mismo cuerpo que sin
credencial; `HTTPBearer` solo lee `Authorization`. El módulo pasa de **7 a 8 passed** y la suite
SQLite de **2322 a 2323 passed / 135 skipped / 0 failed**.

**Excepciones y deuda.** Las excepciones aceptadas son las de §8.3. La deuda abierta queda en
`deuda-tecnica.md`: **DT-17** (`TestClient` bufferiza), **DT-18** (versión de tenant en el camino
sin sesión tenant), **DT-19** (lectura post-commit en `ticket_service`) y **R-05** (SSE sin
métricas). No hay pendientes de cierre de la 028.
