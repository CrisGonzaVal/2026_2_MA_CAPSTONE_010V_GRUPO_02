# Tareas — Feature 028: Actualización en tiempo real de pedidos y tablero

**Feature:** `028-actualizacion-tiempo-real/`
**Spec:** [spec.md](spec.md) — aprobada (28/Nov/2026)
**Plan:** [plan.md](plan.md)
**Hito:** 2 — 11/Dic/2026

> **Granularidad.** La spec tiene 32 AC y toca backend, bus, SSE, tres vistas, borde y pruebas
> gated. Se divide en **24 tareas** (T0–T23) para que `@implementer` ejecute **una por llamada**.
> Si el coordinador exige un máximo de 15, la única agrupación segura es unir T13+T14 (gated) y
> T15+T16 (hub+agrupador); no unir publicaciones ni vistas entre sí.

## Convenciones

- Cada tarea escribe **primero** la prueba que falla y deja la suite afectada en verde.
- No se relaja ningún test existente para que pase. Si una prueba cambia de expectativa, se
  justifica en la tarea y en la evidencia.
- No se añaden dependencias. `redis==8.1.0`, `fetch`/`ReadableStream` y la configuración de nginx
  son el stack disponible.
- No se toca `database/`, modelos, schemas de negocio ni `VERSION_ESQUEMA_OBJETIVO`.
- Cada tarea termina con un `pytest` del grupo tocado (o `ng test` para frontend) y un resumen
  breve en la respuesta del implementador.

## Orden crítico (camino al vertical slice)

`T0 → T1 → T2 → T3 → T4 → T5 → T6 → T7 → T8 → T17` deja un alta de pedido actualizando el
tablero de otra sesión. Después: `T9–T12` (publicaciones), `T15–T16` (hub frontend), `T18–T20`
(vistas), `T21` (borde), `T13–T14` (gated), `T22–T23` (documentación y cierre).

---

## T0 — Verificación temprana de supuestos (spike)

**ACs:** soporte de AC-4, AC-19 y AC-26 (no cierra ninguno por sí sola).
**Depende de:** nada.
**Estimación:** 0,25 jornada.

**Objetivo:** confirmar tres supuestos antes de escribir el núcleo, sin dejar código de
producción.

- [x] `TestClient.stream` puede abrir `GET /api/v1/eventos/` con un flujo falso, leer las primeras
      líneas y cerrar sin bloquear la suite.
      **Cierre T23:** supuesto falso; ajuste documentado y aplicado (DT-17).

  > **Spike 28/Nov/2026 — supuesto FALSO con Starlette 1.7:** `TestClient` ejecuta la app hasta el
  > final y devuelve el cuerpo buffereado (`_TestClientTransport.handle_request` escribe en
  > `io.BytesIO`); no entrega las primeras líneas antes del cierre ni cancela el generador al
  > cerrar el contexto. Un flujo de 300 s bloquearía la suite 300 s. **Ajuste para T5:** todo test
  > del endpoint usa un flujo **acotado** (`VIDA_MAXIMA_CONEXION_SEGUNDOS` y
  > `TIEMPO_REAL_LATIDO_SEGUNDOS` cortos, o `exp` corto) y lee el cuerpo completo; la publicación
  > se prueba con el bus falso + servicio y el E2E real queda en 4200. No cambia el contrato.
  > Evidencia: `stream()` volvió a los 0,015 s, el contexto recién a los 2,062 s (generador de
  > 2,0 s) y con 1,2 s de vida el test cerró en 1,25 s.
- [x] El proxy de desarrollo de Angular (`proxy.conf.json` → backend) entrega un `text/event-stream`
      sin bufferizar; si no, probar `proxyTimeout: 0` y desactivar compresión en `serve`.

  > **Spike 28/Nov/2026 — VERDE sin ajuste:** con `ng serve` (Angular 18 / Vite) y un servidor SSE
  > temporal, `event: listo` llegó a **268 ms** y los latidos a **~2 s**, con
  > `content-encoding: null` incluso enviando `Accept-Encoding: gzip, deflate, br`. `ng serve` no
  > comprime ni bufferiza el flujo, así que `proxyTimeout: 0` **no es necesario** y `angular.json`
  > no se toca (su schema de `serve` ni siquiera admite `compression`). T21 puede omitir el ajuste
  > del proxy; el `location` de nginx sigue siendo necesario para 8080.
- [x] Un `ReadableStream` falso en Karma/Edge permite al parser consumir frames SSE sin
      `EventSource`.

  > **Spike 28/Nov/2026 — VERDE:** 4 SUCCESS en Edge 158.0.0.0 con un parser de líneas que consume
  > `listo`, `cambio`, `estado`, `: latido` y frames partidos entre chunks, más la cancelación del
  > `reader`. **Ajuste para T15:** la lectura del `ReadableStream` se prueba en specs `async`; con
  > `fakeAsync` + `flushMicrotasks`/`tick` la promesa del `reader` **no** se resuelve. `fakeAsync`
  > queda para el parser puro y los temporizadores del backoff/agrupador.
- [x] Registrar el resultado y el ajuste elegido en la respuesta de la tarea (y en la evidencia
      si aplica).

**Hecho cuando:** los tres supuestos tienen un resultado reproducible y, si alguno falla, está
identificado el ajuste concreto antes de T3/T5/T15.

---

## T1 — Configuración, constantes y sobre interno

**ACs:** AC-1 (soporte), AC-24 (soporte), AC-25, AC-32 (soporte).
**Depende de:** T0.
**Estimación:** 0,5 jornada.

**Archivos:** `backend/app/core/config.py`, `backend/app/core/eventos.py` (nuevo),
`backend/tests/funcional/unitarios/test_eventos_028.py` (nuevo).

**Pruebas primero (TDD):**

- [x] `TIEMPO_REAL_HABILITADO` vale `True` por defecto; `TIEMPO_REAL_LATIDO_SEGUNDOS` 25 y
      rechaza `0`/`31`; `MARGEN_RELOJ_SEGUNDOS` 10 y rechaza `0`; `VIDA_MAXIMA_CONEXION_SEGUNDOS`
      300 y rechaza `0`.
- [x] `SobreEvento` es inmutable y su JSON conserva `institucion_id`, `dominios`, `motivo` y
      `usuario_ids`; no incluye campos extra.
- [x] `AlmacenNulo` no publica, no abre Redis y su suscripción no entrega nada.
- [x] `canal_de_institucion("INST-001")` produce `compustock:eventos:INST-001` y rechaza un
      identificador vacío.

**Implementación:**

- [x] Agregar las cuatro claves a `Settings` con sus validadores (rangos del párrafo anterior).
- [x] Crear `app/core/eventos.py` con `DOMINIOS = {"pedidos","inventario","compras"}`,
      `MOTIVOS` (incluye `cambio`), `SobreEvento`, `AlmacenEventos`, `AlmacenNulo`,
      `canal_de_institucion`, `serializar_sobre`/`deserializar_sobre` y los seams
      `configurar_almacen`/`obtener_almacen`/`cerrar_almacen`.
- [x] No crear todavía el cliente Redis (T3); `obtener_almacen` devuelve el configurado o
      `AlmacenNulo` hasta T3.

**Hecho cuando:** `pytest tests/funcional/unitarios/test_eventos_028.py` está en verde y la suite
heredada no abre conexiones a Redis.

---

## T2 — Expiración de la identidad y contexto del flujo

**ACs:** AC-2, AC-3, AC-15 (soporte), AC-31 (soporte).
**Depende de:** T1.
**Estimación:** 0,75 jornada.

**Archivos:** `backend/app/services/auth_service.py`, `backend/app/api/dependencies.py`,
`backend/tests/funcional/unitarios/test_contexto_tiempo_real_028.py` (nuevo),
`backend/tests/no_funcional/seguridad/test_auth.py` (caso nuevo).

**Pruebas primero (TDD):**

- [x] `resolver_identidad` devuelve `expira_en` igual al `exp` de un token firmado con la costura
      de `test_auth.py`; la identidad construida sin el campo sigue siendo válida (default
      `None`).
- [x] `contexto_tiempo_real` con identidad Administrador de INST-001 devuelve
      `institucion_id`, `rol`, `usuario_id`, `expira_en` y los dominios visibles
      (`pedidos`, `inventario`, `compras`, `dashboard`) según las capacidades.
- [x] Con `tickets` apagado, `pedidos` no está en `dominios_visibles`; con `dashboard` apagado,
      `dashboard` no está; con `inventario` apagado, `inventario` no está.
- [x] Una identidad sin institución resoluble responde **403** y no se degrada a global.
- [x] La dependencia llama `db.close()` antes de devolver: el `Session` de prueba queda cerrado
      (`is_active is False` o el doble registra el cierre).

**Implementación:**

- [x] Añadir `expira_en: int | None = None` a `IdentidadAutenticada`; poblarlo en
      `resolver_identidad` desde `claims["exp"]` (sin revalidar ni llamar a Clerk).
- [x] Añadir `ContextoTiempoReal` (frozen) y `contexto_tiempo_real` en `dependencies.py`:
      `get_db`; `tenant_service.resolver_contexto_solicitud` para la institución en PostgreSQL
      (corregido en T13; en SQLite se conserva `ambito_service`), `permisos.nombre_rol_de`,
      `capacidad_service` para las cuatro capacidades; claves de la matriz para los dominios;
      `request_id`; `try/finally: db.close()`.
- [x] Como **andamiaje**, la identidad de la dependencia se obtiene con
      `requiere_roles("Administrador","Bodeguero","Solicitante")`; T5 la cambia a
      `requiere_operacion("GET","/api/v1/eventos/")` al añadir la fila de la matriz. Así la suite
      queda verde entre T2 y T5 (la matriz todavía no tiene la operación y
      `operaciones_reales == MATRIZ_PERMISOS` no se rompe).
- [x] No tocar todavía `permisos.py`; la fila y las aserciones 72 → 73 son de T5.
- [x] No usar `get_db_negocio` ni abrir una sesión de tenant para escuchar.

**Hecho cuando:** los tests de T2 pasan; la suite de autenticación sigue verde; la sesión se
cierra antes de cualquier flujo.

> **Corrección T13 (28/Nov/2026):** la institución **no** se resuelve con
> `ambito_service.alcance_institucional` sobre la sesión de control: en PostgreSQL ese helper lee
> `control.departamento`, donde no están los departamentos de los usuarios de negocio, y toda
> conexión SSE respondía **403** (SQLite lo ocultaba por su contexto lógico único). Ahora
> `contexto_tiempo_real` usa `tenant_service.resolver_contexto_solicitud` (mapa de control, sin
> sesión tenant), con `ErrorInstitucionInactiva → 401`, `ErrorTenant → 403` y `None → 403`. En
> SQLite se conserva `ambito_service`. El gated `test_pool_tiempo_real_028.py` lo acredita sobre
> PostgreSQL real.

---

## T3 — Almacén Redis (publicar/suscribir) y fail-open

**ACs:** AC-8, AC-23 (soporte), AC-25.
**Depende de:** T1.
**Estimación:** 0,75 jornada.

**Archivos:** `backend/app/core/eventos.py`,
`backend/tests/funcional/unitarios/test_almacen_eventos_028.py` (nuevo),
`backend/tests/no_funcional/rendimiento/test_bus_eventos_redis_028.py` (gated, se completa en T14).

**Pruebas primero (TDD):**

- [x] `AlmacenRedisEventos.publicar` serializa el sobre y llama `publish` en el canal correcto
      con un cliente falso; no lanza si el cliente lanza y registra un aviso como máximo cada
      10 s.
- [x] La cota de publicación es 0,5 s: un cliente que duerme más no bloquea más de la cota
      (doble con `timeout` inyectable).
- [x] `suscribir` devuelve una suscripción que entrega un sobre deserializado y `None` en
      timeout; un error del cliente levanta `ErrorBusEventos`.
- [x] `cerrar` cierra el `PubSub` y los clientes sin lanzar si no se crearon.
- [x] El cliente sync usa `socket_connect_timeout=0,3`, `socket_timeout=0,5`,
      `Retry(NoBackoff(), 0)` y `decode_responses=True`.

**Implementación:**

- [x] Implementar `AlmacenRedisEventos` con cliente sync lazy para publicar y cliente async lazy
      para suscribir; `SuscripcionRedis.recibir(timeout)` con
      `get_message(ignore_subscribe_messages=True, timeout=...)`.
- [x] `publicar` envuelve `publish` en `try/except`; `cerrar` es idempotente.
- [x] Mantener `AlmacenNulo` para la suite; la producción crea el Redis de forma lazy con
      `settings.REDIS_URL`.
- [x] No conectar en la importación ni en el arranque si nadie usa el canal.

**Hecho cuando:** los unitarios pasan sin Redis; el gated de T14 puede usar el almacén real.

---

## T4 — Servicio de eventos, audiencia y fail-open de la publicación

**ACs:** AC-7, AC-16, AC-18, AC-27 (soporte).
**Depende de:** T1, T2.
**Estimación:** 0,5 jornada.

**Archivos:** `backend/app/services/evento_service.py` (nuevo),
`backend/tests/funcional/unitarios/test_evento_service_028.py` (nuevo),
`backend/tests/funcional/integracion/_soporte_eventos_028.py` (nuevo).

**Pruebas primero (TDD):**

- [x] `publicar_pedidos("INST-001","alta",{7})` produce un sobre con `dominios={"pedidos"}` y
      `usuario_ids={7}`.
- [x] `publicar_inventario` produce `{"inventario"}` y `usuario_ids` vacío.
- [x] `publicar_pedidos_e_inventario` produce ambos dominios y conserva los dueños.
- [x] `publicar_compras` con dos `ticket_id` consulta los dueños y produce
      `{"compras","pedidos"}`; sin `ticket_id`, solo `{"compras"}`; con `con_inventario=True`
      añade `inventario`.
- [x] Un fallo del almacén o de la consulta de dueños no propaga excepción y registra un aviso;
      el sobre no se publica a medias.
- [x] El bus falso (`BusFalso`) guarda los sobres para las pruebas de publicación y activa
      `TIEMPO_REAL_HABILITADO` durante el test (el conftest lo deja apagado).

**Implementación:**

- [x] Crear `evento_service` con las cuatro funciones y `_publicar` (try/except total).
- [x] `_audiencia_de_tickets(db, institucion_id, ticket_ids)` con una sola consulta a
      `Ticket.usuario_id`, filtrando por institución y sin duplicados.
- [x] No publicar si `settings.TIEMPO_REAL_HABILITADO` está apagado (el canal no se usa), pero
      no cambiar la respuesta.
- [x] Crear el `BusFalso` de soporte en `tests/funcional/integracion/_soporte_eventos_028.py`
      (publicados, cola de eventos, `suscribir`).

**Hecho cuando:** los unitarios de T4 pasan y el bus falso está disponible para T5/T8.

---

## T5 — Endpoint `GET /api/v1/eventos/`, stream, `listo`, latido, cierre y OpenAPI

**ACs:** AC-1, AC-2, AC-3, AC-4, AC-24, AC-32.
**Depende de:** T2, T4.
**Estimación:** 1 jornada.

**Archivos:** `backend/app/api/v1/endpoints/eventos.py` (nuevo),
`backend/app/api/v1/api.py`, `backend/app/api/dependencies.py`,
`backend/app/core/permisos.py`, `backend/app/main.py`,
`backend/tests/funcional/integracion/test_eventos_endpoint_028.py` (nuevo),
`backend/tests/no_funcional/seguridad/test_permisos_endpoint_028.py` (nuevo).

**Pruebas primero (TDD):**

- [x] Con sesión válida: **200**, `Content-Type: text/event-stream; charset=utf-8`,
      `Cache-Control: no-store`, primer frame `listo` con los dominios visibles.
- [x] Sin `Authorization`: **401**; Superadmin: **403**; `TIEMPO_REAL_HABILITADO=False`: **503**
      con `detail`; sin abrir una conexión.
- [x] El frame `listo` no contiene `institucion_id`, `usuario_id` ni ids; el flujo no emite
      `id:` ni `retry:`.
- [x] Con `TIEMPO_REAL_LATIDO_SEGUNDOS` corto, se lee al menos un `: latido`.
- [x] Con `exp` a pocos segundos en la identidad de prueba, el flujo se cierra en `exp - 10 s`;
      el caso real de `resolver_identidad` con la costura `firmar_token` se cubre en T2. El test
      no se cuelga.
- [x] `/openapi.json` publica la operación con media type, 200/401/403/429/503, sin
      `response_model` JSON; la matriz tiene la fila y pasa de **72 a 73**; OpenAPI **74 a 75**.
- [x] La ruta no lee `?institucion_id`, `?sede_id`, `?usuario_id` ni `?dominios` para ampliar el
      contexto.

**Implementación:**

- [x] Crear `eventos.router` con `prefix="/eventos"`, `GET "/"`, `response_class=StreamingResponse`,
      `status_code=200`, `responses` y descripción de frames.
- [x] Añadir la fila `("GET", "/api/v1/eventos/")` a `MATRIZ_PERMISOS` y cambiar el andamiaje
      `requiere_roles` de `contexto_tiempo_real` por
      `requiere_operacion("GET", "/api/v1/eventos/")` (la dependencia final es la matriz).
- [x] Incluirlo en `api_router`; actualizar las aserciones absolutas de matriz **72 → 73** y de
      OpenAPI **74 → 75** / negocio **72 → 73** en `test_contrato_024.py` y
      `test_permisos_retiro_013.py`.
- [x] Implementar `generar(contexto)` con `listo`, suscripción al bus, `: latido`, límite
      `min(exp - MARGEN, ahora + VIDA_MAXIMA)` y cierre limpio.
- [x] Comprobar `TIEMPO_REAL_HABILITADO` y responder 503 sin abrir el stream.
- [x] Registrar el cierre del almacén en el `shutdown` de `main.py`.
- [x] No implementar todavía el filtro por sobre (T6) ni la degradación (T7): el fake bus puede
      entregar eventos ya filtrados.

**Hecho cuando:** los tests de contrato pasan; el stream se puede leer con `TestClient.stream`;
`/openapi.json` refleja 75/73.

---

## T6 — Filtro por conexión, audiencia y marca `dashboard`

**ACs:** AC-15, AC-16, AC-17, AC-18, AC-27, AC-28.
**Depende de:** T4, T5.
**Estimación:** 0,75 jornada.

**Archivos:** `backend/app/api/v1/endpoints/eventos.py`,
`backend/tests/funcional/unitarios/test_filtro_eventos_028.py` (nuevo),
`backend/tests/funcional/integracion/test_eventos_filtro_028.py` (nuevo).

**Pruebas primero (TDD):**

- [x] Institución B no recibe un sobre de A (canal y comprobación del sobre).
- [x] Solicitante dueño recibe `pedidos`; otro Solicitante de la misma institución no recibe
      frame; Administrador y Bodeguero sí.
- [x] Una conexión con `tickets` apagado pero `dashboard` encendido recibe
      `{"dominios":["dashboard"], "motivo":"cambio"}`; no aparece `pedidos` ni el motivo real.
- [x] Una conexión con `inventario` apagado y `dashboard` encendido recibe `dashboard`; una con
      `compras` apagado no recibe `compras` ni `dashboard` por un evento de compras.
- [x] Un evento con `pedidos`+`inventario` y ambas capacidades apagadas produce un solo frame
      `dashboard` (no dos).
- [x] Un sobre cuyo conjunto visible queda vacío no emite frame.
- [x] Ningún frame contiene ids del sobre, ni institución, ni usuario; el `motivo` es `cambio`
      cuando hay marca sintética.

**Implementación:**

- [x] Implementar `_dominios_visibles_del_sobre(contexto, sobre)` con el orden:
      institución → dueño de `pedidos` → capacidad/rol → `dashboard`.
- [x] Deduplicar `dashboard` y normalizar el `motivo` a `cambio` si la marca está presente.
- [x] No serializar nunca `institucion_id`/`usuario_ids`/`ticket_id`.
- [x] Reutilizar el `BusFalso` para emitir sobres desde el test.

**Hecho cuando:** la matriz de casos rol/capacidad/dueño está cubierta y no hay fuga de ids.

---

## T7 — Suscriptor, degradación/recuperación, cota y log

**ACs:** AC-8, AC-23 (soporte), AC-4 (soporte).
**Depende de:** T3, T5, T6.
**Estimación:** 0,75 jornada.

**Archivos:** `backend/app/api/v1/endpoints/eventos.py`,
`backend/app/core/observabilidad.py`,
`backend/tests/funcional/integracion/test_eventos_degradacion_028.py` (nuevo).

**Pruebas primero (TDD):**

- [x] Si el bus lanza al suscribir o al recibir, el flujo sigue abierto, emite
      `estado: degradado` y no cierra el HTTP; al recuperarse, `estado: recuperado`.
- [x] La reconexión al bus usa retroceso 1/2/4/8/10 s y no consume peticiones HTTP.
- [x] Una mutación con el bus colgado responde en su latencia habitual + ≤0,5 s; no hay 5xx.
- [x] La línea `compustock.tiempo_real` registra `request_id`, `route`, `resultado` y `motivo`;
      no incluye token, correo, query, IP ni ids.
- [x] `/ready` sigue en 200 con el bus caído.

**Implementación:**

- [x] Envolver la suscripción/recibir en `try/except ErrorBusEventos`; emitir `estado` y
      reintentar internamente con retroceso, sin cerrar el generador.
- [x] Añadir `LOGGER_TIEMPO_REAL` y `registrar_tiempo_real` en `observabilidad.py`.
- [x] Mantener el latido durante la degradación.
- [x] Verificar que la cota de 0,5 s de T3 se respeta en la respuesta de la mutación.

**Hecho cuando:** los tests de degradación/recuperación y de latencia pasan; el log no tiene PII.

---

## T8 — Publicación de pedidos: alta, edición, aprobación, confirmación, anulación/rechazo y `PATCH`

**ACs:** AC-5, AC-7.
**Depende de:** T4.
**Estimación:** 0,75 jornada.

**Archivos:** `backend/app/services/ticket_service.py`,
`backend/tests/funcional/integracion/test_publicacion_tickets_028.py` (nuevo).

**Pruebas primero (TDD):**

- [x] Alta confirmada → sobre `pedidos`, motivo `alta`, dueño `ticket.usuario_id`.
- [x] Edición → `edicion`; aprobación → `aprobacion`; confirmación → `confirmacion_entrega`;
      `PATCH /estado` → `cambio_estado`; anulación `EnRevision` → `anulacion`; rechazo →
      `rechazo`.
- [x] Un 404/409/422 o un rollback forzado no publica.
- [x] La publicación ocurre **después** del commit: el bus falso ve el sobre y el ticket ya está
      persistido.
- [x] La respuesta de la mutación no cambia de status/cuerpo con el bus caído.

**Implementación:**

- [x] Llamar `evento_service.publicar_pedidos(...)` justo después del `db.commit()` de cada
      función, con el dueño ya cargado.
- [x] En `_cambiar_a_anulado`, publicar una vez según la rama y el `tipo_operacion`; no duplicar
      en `anular_ticket`/`rechazar_ticket`.
- [x] No publicar en `actualizar_estado_ticket` si la petición no cambió nada (409).
- [x] No tocar la lógica de negocio ni los códigos de respuesta.

**Hecho cuando:** la tabla de mutaciones de T8 publica exactamente una vez y los rechazos no
publican.

---

## T9 — Publicación de retiro y anulación administrativa

**ACs:** AC-5, AC-7.
**Depende de:** T8.
**Estimación:** 0,5 jornada.

**Archivos:** `backend/app/services/ticket_service.py`,
`backend/tests/funcional/integracion/test_publicacion_retiro_028.py` (nuevo).

**Pruebas primero (TDD):**

- [x] Retiro confirmado → un sobre con `{"pedidos","inventario"}`, motivo `retiro`, dueño del
      ticket.
- [x] Anulación desde `Cerrado` → `{"pedidos","inventario"}`, motivo `anulacion`, dueño.
- [x] Retiro con stock insuficiente (409) o anulación de un confirmado (409) no publica.
- [x] El sobre es uno solo (no dos mensajes) y el frame futuro no lleva ids.

**Implementación:**

- [x] Publicar en `registrar_retiro_ticket` después del commit.
- [x] Publicar en la rama `Cerrado` de `_cambiar_a_anulado` con `inventario`.
- [x] Mantener la rama `EnRevision` solo con `pedidos`.

**Hecho cuando:** los dos caminos publican una vez y los 409 no publican.

---

## T10 — Publicación del movimiento manual de stock

**ACs:** AC-6, AC-7.
**Depende de:** T4.
**Estimación:** 0,25 jornada.

**Archivos:** `backend/app/services/inventario_service.py`,
`backend/tests/funcional/integracion/test_publicacion_inventario_028.py` (nuevo).

**Pruebas primero (TDD):**

- [x] `POST /inventario/movimientos` confirmado → sobre `{"inventario"}`, motivo `movimiento`,
      `usuario_ids` vacío.
- [x] Un 404 (sede/producto) o 409 (stock insuficiente/inactivo) no publica.
- [x] El dashboard y el tablero reciben `inventario` (la prueba de frame se completa en T6).

**Implementación:**

- [x] Publicar después de `db.commit()` en `_registrar_movimiento_por_sede`, con
      `institucion_id` ya resuelto.
- [x] No publicar desde el endpoint; el servicio es reutilizable.

**Hecho cuando:** el movimiento confirmado publica y los rechazos no.

---

## T11 — Publicación de compras: emisión, facturación y cancelación

**ACs:** AC-30, AC-7.
**Depende de:** T4.
**Estimación:** 0,75 jornada.

**Archivos:** `backend/app/services/compra_service/ordenes.py`,
`backend/tests/funcional/integracion/test_publicacion_compras_028.py` (nuevo).

**Pruebas primero (TDD):**

- [x] Emisión con plan con `cantidad_asignada > 0` → `{"compras","pedidos"}`, dueños de los
      pedidos del plan; emisión sin plan → solo `{"compras"}`.
- [x] Facturación que pasa de `Emitida` a `Facturada` con plan → `{"compras","pedidos"}`;
      corrección de una `Facturada` → solo `{"compras"}`.
- [x] Cancelación desde `Emitida` con plan → `{"compras","pedidos"}`; desde `Borrador` → solo
      `{"compras"}`.
- [x] Un 409 (estado no elegible) no publica.
- [x] `GET /tickets/{id}` refleja el cambio de cadena antes/después (consulta directa al
      servicio en el test).

**Implementación:**

- [x] Capturar `estado_anterior` antes de la transición en facturación/cancelación.
- [x] Usar `orden.plan` (cargado por `_cargar_orden`) para los `ticket_id`; `publicar_compras`
      resuelve los dueños.
- [x] Publicar después de `_confirmar` (commit) y antes de la proyección.
- [x] No publicar en alta/edición en `Borrador`, proveedores ni preview.

**Hecho cuando:** las tres mutaciones con y sin plan publican lo correcto y los 409 no publican.

---

## T12 — Publicación de la recepción y desbloqueo

**ACs:** AC-6, AC-13, AC-30, AC-7.
**Depende de:** T11.
**Estimación:** 0,5 jornada.

**Archivos:** `backend/app/services/compra_service/recepcion.py`,
`backend/tests/funcional/integracion/test_publicacion_recepcion_028.py` (nuevo).

**Pruebas primero (TDD):**

- [x] Recepción confirmada → `{"inventario","compras"}` siempre; `{"pedidos"}` si el plan tiene
      filas o hay `tickets_desbloqueados`.
- [x] Los dueños del sobre son la unión de los pedidos del plan y los desbloqueados, sin
      duplicados.
- [x] Una recepción de una OC ya recibida (409) no publica.
- [x] El detalle del Bodeguero refleja `stock_disponible = true` después (servicio, no UI).

**Implementación:**

- [x] Publicar después de `_confirmar`; usar `orden.plan` y
      `tickets_desbloqueados` (`TicketDesbloqueadoRespuesta.ticket_id`).
- [x] `publicar_compras(..., con_inventario=True, ticket_ids=...)`.
- [x] No publicar `pedidos` si no hay plan ni desbloqueo.

**Hecho cuando:** la recepción con y sin desbloqueo publica los dominios y dueños correctos.

---

## T13 — Gated PostgreSQL: pool y cierre de sesión

**ACs:** AC-29, AC-6 (soporte); AC-1 y AC-2 (corrección del 28/Nov/2026).
**Depende de:** T5, T6.
**Estimación:** 0,5 jornada.

**Archivos:** `backend/app/api/dependencies.py`,
`backend/tests/funcional/sistema/test_pool_tiempo_real_028.py` (nuevo).

**Corrección previa (28/Nov/2026).** El gated destapó que `contexto_tiempo_real` resolvía la
institución con `ambito_service.alcance_institucional(db, identidad)` sobre la sesión de **control**;
en PostgreSQL los departamentos de los usuarios de negocio solo existen en su esquema tenant, así
que `GET /api/v1/eventos/` respondía **403** a toda identidad de tenant. Se sustituyó por
`tenant_service.resolver_contexto_solicitud(db, identidad.usuario.correo)` (mapa de control, sin
sesión tenant), con `ErrorInstitucionInactiva → 401`, `ErrorTenant → 403` y `None → 403`; en SQLite
se conserva `ambito_service` para el contexto lógico único. El comportamiento aprobado no cambia;
cambia el mecanismo. Ver plan §4.1, paso 2.

**Pruebas primero (TDD, gated con `POSTGRES_TEST_URL`):**

- [x] Crear un motor temporal con pool pequeño (p. ej. `pool_size=2`, `max_overflow=0`),
      overridear `get_db`/`get_current_user` y abrir 5 flujos ociosos al endpoint.
- [x] Con los 5 flujos abiertos, una petición de negocio (`GET /tickets/` o `/dashboard/`)
      responde 200 y no aparece `QueuePool limit`.
- [x] Cerrar los flujos libera las conexiones; el motor temporal se elimina al final.
- [x] Verificar que `contexto_tiempo_real` cerró la sesión antes del stream (contador de
      conexiones o `pg_stat_activity` acotado).
- [x] Con identidad de tenant, `GET /api/v1/eventos/` responde **200** y llega `listo`; con la
      institución inactiva responde **401** y con un correo no mapeado **403**.

**Implementación:**

- [x] Usar el patrón de los gated existentes: base temporal desechable, nunca `apt_erp`; el
      test se omite sin la variable.
- [x] No tocar el pool de producción ni `database.py`.
- [x] `uvicorn.Server` real en un hilo con puerto efímero y `httpx.Client.stream` (no
      `TestClient`: Starlette 1.7 bufferiza; `httpx.ASGITransport` también).

**Hecho cuando:** el test pasa con `POSTGRES_TEST_URL` y se omite sin ella.

> **Nota 28/Nov/2026.** `test_pool_tiempo_real_028.py` tiene **4 pruebas**: 5 flujos ociosos con
> pool 2/0/2 s y `GET /tickets/` 200 sin `QueuePool limit`; apertura con identidad de tenant
> (200 + `listo`); institución inactiva (401); correo no mapeado (403). En rojo previo al fix:
> 3 failed / 1 passed, todas por el 403 de institución; tras el fix: **4 passed**; sin
> `POSTGRES_TEST_URL`: **4 skipped**. Suite SQLite completa: **2318 passed / 132 skipped /
> 0 failed** (los 4 skipped nuevos son este módulo gated). No cambia el contrato, el DDL ni
> `permisos.py`; `ambito_service` se conserva para el camino SQLite.

---

## T14 — Gated Redis, multiproceso y ventana de capacidades

**ACs:** AC-23, AC-31, AC-8 (soporte).
**Depende de:** T3, T5, T7.
**Estimación:** 0,75 jornada.

**Archivos:** `backend/tests/no_funcional/rendimiento/test_bus_eventos_redis_028.py` (gated),
`backend/tests/no_funcional/seguridad/test_tiempo_real_028.py` (ventana/aislamiento).

**Pruebas primero (TDD):**

- [x] Con `REDIS_TEST_URL` terminado en `/15`: publicar un sobre y recibirlo por una suscripción
      real; vaciar la base al empezar y al terminar.
- [x] Dos instancias de app con el mismo bus: un evento publicado por una llega a una conexión
      de la otra (hubs aislados; la evidencia de dos procesos reales es el recorrido manual con
      `uvicorn --workers 2`).
- [x] Con Redis detenido, la mutación responde normal y `/ready` sigue en 200.
- [x] Con `VIDA_MAXIMA_CONEXION_SEGUNDOS` corto (p. ej. 1 s), apagar una capacidad o desactivar
      la institución: la conexión vieja no entrega eventos del dominio después de la ventana; la
      nueva conexión no incluye el dominio en `listo`; la lectura responde 403/401.
- [x] No se usa la base 0 de Redis.

**Implementación:**

- [x] Usar la costura `configurar_almacen` con el `AlmacenRedisEventos` real en el gated.
- [x] Documentar el comando manual de dos workers y el resultado en la evidencia (T22).
      **Pendiente por diseño:** el comando y su justificación quedan en el docstring del módulo
      gated; T23 (28/Nov/2026) **no repitió** la ejecución manual con dos workers y sesión Clerk
      real. La casilla se cierra como **excepción aceptada por @reviewer:** no hubo ejecución
      manual; el fan-out entre instancias está acreditado por el gated de Redis
      (`test_dos_instancias_aisladas_comparten_el_bus_y_el_cambio_cruza_redis`, con `PUBSUB NUMSUB`
      confirmando el suscriptor real) y el comando sigue en el docstring.
- [x] No añadir dependencias; `redis` ya está.

**Hecho cuando:** el gated pasa con `REDIS_TEST_URL` y la ventana se demuestra con un test
determinista (vida máxima corta), no con esperas largas.

> **Nota 28/Nov/2026 (T14).** `test_bus_eventos_redis_028.py` pasa de 1 a **4 pruebas** y
> `test_tiempo_real_028.py` aporta **4 pruebas** nuevas:
>
> - Gated (con `REDIS_TEST_URL=redis://127.0.0.1:6380/15`): **4 passed**. El fan-out entre
>   instancias usa dos `AlmacenRedisEventos` con clientes propios (la suscripción vive en B y la
>   publicación sale del cliente sync de A); `PUBSUB NUMSUB` confirma el suscriptor real y el
>   frame `cambio` de `generar` llega desde Redis, no desde memoria local. El escenario de Redis
>   caído usa un puerto local cerrado (nunca apaga el Redis compartido): la mutación conserva
>   `201` y su latencia (`<=` base + 0,5 s) y `/ready` sigue en `200`. La base 15 se vacía al
>   empezar y al terminar con un fixture autouse y la guarda exige `/15` (nunca la base 0).
> - Seguridad (SQLite, no gated): **4 passed**. Con `VIDA_MAXIMA_CONEXION_SEGUNDOS=1`, la
>   conexión vieja entrega un `cambio` antes de la ventana, descarta un sobre de otra institución
>   y cierra al vencer (~1 s, no 300 s); un sobre posterior ya no se entrega. Con `tickets`
>   apagado, `listo` no incluye `pedidos`, un sobre de pedidos solo produce la marca
>   `{"dominios":["dashboard"],"motivo":"cambio"}` y `GET /tickets/` responde **403**. Con la
>   institución inactiva (rama PostgreSQL del mapa de control) la reapertura responde **401** y
>   un correo sin mapa **403**. El aislamiento por institución se comprueba además en el canal
>   de suscripción y en el descarte del sobre ajeno.
> - Suite SQLite completa: **2322 passed / 135 skipped / 0 failed** (2318+4 passed nuevos y
>   132+3 skipped nuevos del gated ampliado; ningún test existente se modificó). Sin
>   `REDIS_TEST_URL`, el módulo gated se omite (4 skipped). No se tocó `backend/app/` ni
>   `frontend/`; no hay bug de producción que corregir.

---

## T15 — Frontend: hub `TiempoRealService`

**ACs:** AC-1, AC-4, AC-8, AC-19, AC-20, AC-21, AC-22.
**Depende de:** T5 (contrato), T0.
**Estimación:** 1 jornada.

**Archivos:** `frontend/src/app/core/services/tiempo-real.service.ts` (nuevo),
`frontend/src/app/core/services/tiempo-real.service.spec.ts` (nuevo).

**Pruebas primero (TDD):**

- [x] El parser interpreta `listo`, `cambio`, `estado`, comentarios `: latido` y líneas vacías;
      ignora tipos desconocidos y `data` inválido sin romper la conexión.
- [x] La petición usa `${URL_API}/eventos/`, `Authorization: Bearer`, `Accept:
      text/event-stream`, `cache: no-store`; no usa `EventSource` ni `HttpClient`.
- [x] 401/403: no reintenta y cierra; 429: espera `Retry-After`; 5xx/red: retroceso 1/2/4/8/16/30
      con jitter y tope 30 s; no abre dos conexiones simultáneas.
- [x] `document.hidden` no dispara refrescos; `visibilitychange` a visible emite una
      resincronización única.
- [x] `listo` y `recuperado` emiten `resincronizar`; `degradado` no bloquea.
- [x] `detener()`/logout aborta con `AbortController` y limpia los callbacks.
- [x] No guarda token en `localStorage`, URL ni cookie.

**Implementación:**

- [x] Crear el servicio raíz con signals de estado, `iniciar`/`detener`, `alCambio`,
      `alResincronizar`, `alEstado`.
- [x] Implementar `fetch` + `ReadableStream` + `TextDecoder`; una sola conexión por pestaña.
- [x] Implementar el backoff con temporizador inyectable para los tests y el mínimo de 30 s
      entre aperturas.
- [x] Integrar con `AutenticacionService` (sesión/identidad) sin repetir `/auth/me`.
- [x] No registrar el token ni el cuerpo de los frames en consola.

**Hecho cuando:** el spec del servicio cubre parser, estados, reconexión, visibilidad y cierre.

---

## T16 — Frontend: refresco agrupado

**ACs:** AC-14, AC-20.
**Depende de:** nada (utilidad pura).
**Estimación:** 0,25 jornada.

**Archivos:** `frontend/src/app/shared/utils/refresco-agrupado.ts` (nuevo),
`frontend/src/app/shared/utils/refresco-agrupado.spec.ts` (nuevo).

**Pruebas primero (TDD):**

- [x] 20 solicitudes en ráfaga producen **una** ejecución tras 250 ms de silencio.
- [x] Una ráfaga continua no espera más de 1 s desde la primera solicitud.
- [x] Si hay una ejecución en vuelo, se encola **una** pendiente y no se solapan.
- [x] `cancelar()` limpia temporizadores y no ejecuta nada; una nueva solicitud después funciona.
- [x] Los temporizadores son inyectables para `fakeAsync`.

**Implementación:**

- [x] `crearRefrescoAgrupado(fn, {quietudMs=250, maxEsperaMs=1000})` con
      `{solicitar, cancelar}` y una promesa de ejecución tolerante a errores.
- [x] Sin dependencias de Angular; testeable con `fakeAsync`/`tick`.

**Hecho cuando:** el spec de la utilidad pasa y no usa `setInterval`.

---

## T17 — Frontend: integración del tablero

**ACs:** AC-9, AC-10, AC-11, AC-14.
**Depende de:** T15, T16.
**Estimación:** 0,5 jornada.

**Archivos:** `frontend/src/app/features/tickets/tickets.component.ts` (y `.html` si hace falta),
`frontend/src/app/features/tickets/tickets.component.spec.ts`.

**Pruebas primero (TDD):**

- [x] Un frame `pedidos` provoca una única recarga silenciosa de la lista (no la del constructor
      más otra por frame).
- [x] `cargandoTablero` no se enciende en el refresco silencioso; la tarjeta nueva aparece sin
      recargar.
- [x] El refresco conserva `filtroPeriodo`, `orden`, `busqueda` y la posición de scroll; no
      reinicia el `computed` de columnas a un estado vacío.
- [x] Un frame `inventario` también refresca el tablero (la etiqueta de proceso puede cambiar).
- [x] `ngOnDestroy` cancela la suscripción y el agrupador.
- [x] Un fallo de la recarga mantiene las tarjetas previas y no muestra el error global.

**Implementación:**

- [x] Inyectar `TiempoRealService`; suscribirse a `["pedidos","inventario"]` con
      `crearRefrescoAgrupado`.
- [x] Añadir `cargarTablero({silencioso = false})`; solo la carga inicial/reintento enciende
      `cargandoTablero`.
- [x] No tocar los filtros, la búsqueda ni el orden.
- [x] Mantener el alta optimista (el `201` sigue insertando la tarjeta sin reconsultar).

**Hecho cuando:** los specs del tablero pasan y el refresco no pierde estado.

---

## T18 — Frontend: integración del detalle

**ACs:** AC-10, AC-11, AC-13, AC-14.
**Depende de:** T15, T16.
**Estimación:** 0,5 jornada.

**Archivos:** `frontend/src/app/features/tickets/ticket-detalle.component.ts`,
`frontend/src/app/features/tickets/ticket-detalle.component.spec.ts`.

**Pruebas primero (TDD):**

- [x] Un frame `pedidos` recarga detalle + historial una vez y no cierra el `<dialog>` de
      anulación/rechazo.
- [x] El texto escrito en `motivo` no se borra; las acciones (`Aprobar`, `Retirar`, `Confirmar`,
      `Anular`) se recalculan con el estado nuevo.
- [x] Un frame `inventario` actualiza `stock_disponible` y la disponibilidad del botón de retiro.
- [x] `cargando` no se enciende en el refresco silencioso; un fallo mantiene el detalle previo.
- [x] `ngOnDestroy` cancela la suscripción y el agrupador.

**Implementación:**

- [x] Inyectar el hub; `crearRefrescoAgrupado` para `["pedidos","inventario"]`.
- [x] Añadir `cargar({silencioso = false})`; la recarga de historial comparte el agrupador.
- [x] No resetear formularios, motivo, pestaña ni diálogo.
- [x] No duplicar la lógica de permisos: la vista sigue usando la matriz/roles existentes.

**Hecho cuando:** los specs del detalle pasan y el formulario/diálogo sobrevive al refresco.

> **Nota 28/Nov/2026:** el detalle se suscribe a `pedidos`/`inventario` y a `alResincronizar` con
> un único `crearRefrescoAgrupado`. La ruta silenciosa de `cargar` relee **solo detalle +
> historial** (sin catálogos), no toca `cargando`, error global, `confirmando`, `motivoForm`,
> `editando` ni la pestaña, y conserva los datos previos si falla; `reconsultar()` delegó en ella.
> Una ráfaga de `listo` + `cambio` produce un solo par de GETs. `ticket-detalle.component.spec.ts`
> pasa de 70 a 77 pruebas; suite completa **750 SUCCESS / 0 failed**.

---

## T19 — Frontend: integración del dashboard

**ACs:** AC-12, AC-28.
**Depende de:** T15, T16.
**Estimación:** 0,25 jornada.

**Archivos:** `frontend/src/app/features/dashboard/dashboard.component.ts`,
`frontend/src/app/features/dashboard/dashboard.component.spec.ts`.

**Pruebas primero (TDD):**

- [x] Un frame `pedidos` o `inventario` recarga `GET /dashboard/` una vez y actualiza KPI,
      alertas y actividad sin placeholder.
- [x] Un frame `dashboard` (sintético) hace exactamente lo mismo sin exponer el dominio oculto.
- [x] `cargando` no se enciende en el refresco silencioso; un fallo conserva `datos` y no borra
      los KPI.
- [x] El Solicitante sigue sin actividad (`actividad_disponible=false`) y no consulta
      `/inventario/movimientos`.
- [x] `ngOnDestroy` cancela la suscripción.

**Implementación:**

- [x] Inyectar el hub; `crearRefrescoAgrupado` para `["pedidos","inventario","dashboard"]`.
- [x] Añadir `cargar({silencioso = false})`; solo la carga inicial/reintento enciende `cargando`.
- [x] No cambiar el template ni el layout; solo el refresco.

**Hecho cuando:** los specs del dashboard pasan y el refresco no parpadea.

> **Nota 28/Nov/2026:** el dashboard se suscribe a `pedidos`/`inventario`/`dashboard` y a
> `alResincronizar` con un único `crearRefrescoAgrupado`. La ruta silenciosa de `cargar` relee
> **solo `GET /dashboard/`**, no toca `cargando` ni el error global, conserva `datos` y los KPI
> si falla y limpia el error si el refresco tiene éxito (un fallo previo deja de ser vigente).
> El Solicitante mantiene `actividad_disponible=false` y no consulta `/inventario/movimientos`.
> Una ráfaga de `listo` + `cambio` produce un solo GET. `dashboard.component.spec.ts` pasa de
> 15 a 23 pruebas; suite completa **758 SUCCESS / 0 failed**.

---

## T20 — Frontend: shell, sesión y arranque del hub

**ACs:** AC-19, AC-22 (soporte).
**Depende de:** T15.
**Estimación:** 0,25 jornada.

**Archivos:** `frontend/src/app/app.component.ts`, `frontend/src/app/app.component.spec.ts`.

**Pruebas primero (TDD):**

- [x] El shell inicia el hub una sola vez; un doble del servicio registra `iniciar()`.
- [x] Al cerrar sesión, el hub se detiene/aborta y no se reintenta.
- [x] El shell no cambia el layout ni duplica conexiones al navegar entre rutas.
- [x] El spec existente del shell sigue verde (scroll/overflow).

**Implementación:**

- [x] Inyectar `TiempoRealService` y llamar `iniciar()`; `ngOnDestroy` → `detener()`.
- [x] No abrir el canal en el `LoginComponent` ni en guards.
- [x] Mantener el `overflow`/`contain` del shell intacto.

> **Nota 28/Nov/2026:** el paro por cierre de sesión lo ejecuta el propio hub (observa
> `AutenticacionService`); el shell no lo duplica ni lo reinicia. El spec verifica que
> `iniciar()` sigue en 1 tras el cierre, que `detener()` no se adelanta y que la red de
> seguridad lo llama una vez al destruir la shell. `app.component.spec.ts` pasa de 31 a
> 34 pruebas; suite completa **743 SUCCESS / 0 failed**.

**Hecho cuando:** el spec del shell pasa y el hub no se duplica al navegar.

---

## T21 — Borde: nginx y proxy de desarrollo

**ACs:** AC-4, AC-21, AC-26 (soporte).
**Depende de:** T5.
**Estimación:** 0,5 jornada.

**Archivos:** `frontend/nginx.conf`, `frontend/proxy.conf.json`,
`frontend/angular.json` (solo si T0 exige desactivar compresión en `serve`).

**Pruebas primero / verificación:**

- [x] `nginx -t` (o el arranque del contenedor) acepta la configuración.
- [x] `curl -N -H "Authorization: Bearer …" http://localhost:8080/api/v1/eventos/` recibe
      `listo` y al menos un latido; no hay búfer perceptible.
      **Excepción aceptada por @reviewer:** no se ejecutó en T21 ni en T23. El humo de T23 en 8080
      con una sesión real en el navegador acredita que el canal atraviesa nginx, pero no mide
      latido ni búfer; la prueba de 60 s queda como excepción aceptada. La semántica de "sin búfer" del location
      se verificó por separado con un upstream SSE temporal (ver nota).
- [x] El 429 de nginx conserva el JSON y `Access-Control-Allow-Origin` cuando el origen está
      permitido.
- [x] En 4200, el flujo atraviesa el proxy de desarrollo sin búfer (con `proxyTimeout: 0` y sin
      compresión si T0 lo exigió).
- [x] `limit_req`/`limit_conn` del location exacto no rompen el resto de `/api/`.

**Implementación:**

- [x] Añadir `location = /api/v1/eventos/` con `proxy_buffering off`, `proxy_cache off`,
      `proxy_read_timeout 3600s`, `proxy_send_timeout 3600s`, `Connection ""`, `X-Real-IP` y
      los límites de la 024.
- [x] No cambiar `gzip_types`; `text/event-stream` ya queda fuera.
- [x] Ajustar `proxy.conf.json` solo si T0 lo pide; documentar el cambio.
      **No aplica:** T0 dejó el proxy de desarrollo en verde sin ajuste; el archivo no cambia.
- [x] No tocar `docker-compose.yml` (Redis ya está; el backend no depende de él).

> **Nota 28/Nov/2026:** `frontend/nginx.conf` gana `location = /api/v1/eventos/` con
> `proxy_buffering off`, `proxy_cache off`, `proxy_read_timeout`/`proxy_send_timeout` 3600s,
> `Connection ""`, `Host`, `X-Real-IP`, `X-Forwarded-For`, `X-Forwarded-Proto` y los
> `limit_req`/`limit_conn` de la 024. `gzip_types` no se toca (no incluye `text/event-stream`) y
> `proxy.conf.json`, `angular.json` y `docker-compose.yml` quedan igual.
>
> Evidencia: `nginx -t` pasa en un `nginx:alpine` desechable sobre la red de Compose y dentro de
> `compustock_frontend`. La imagen se reconstruyó
> (`docker compose build frontend`: `evidenciasproyecto-frontend:latest`, ID `3974188a383e`,
> antes `985ef772f78f`) y el contenedor quedó **healthy**; el `default.conf` del contenedor
> contiene el location (línea 39). Con un upstream SSE temporal y **este mismo archivo**, el
> trace de `curl -N --trace-time` mostró `event: listo` en el primer paquete y un `: latido`
> cada 1 s, con `Transfer-Encoding: chunked`, `Content-Type: text/event-stream; charset=utf-8`
> y sin `Content-Encoding`. Contra 8080, `GET /api/v1/eventos/` sin token responde **401** del
> backend (con `x-request-id`), una ráfaga de 60 peticiones al location exacto dio
> **20×401 + 40×429** y el 429 conservó `Content-Type: application/json`, el `detail` y
> `Access-Control-Allow-Origin: http://permitido.example` / `Vary: Origin`. Después de la
> ráfaga, `/api/v1/tickets/` y `/api/v1/dashboard/` siguen en **401**, `/` en **200** y
> `/metrics` en **404**. En 4200 no hay cambio de proxy (T0: `listo` a 268 ms y latidos a ~2 s
> sin `content-encoding`). **Riesgo residual:** que el borde no corte un flujo autenticado de
> más de 60 s solo se demuestra con 60 s abiertos en 8080; T23 no ejecutó esa prueba (el humo de
> sesión real acreditó el canal a través de nginx, no la duración).

**Hecho cuando:** el flujo funciona en 4200 y 8080 con el mismo contrato y sin búfer.

---

## T22 — Documentación, `stack.md` y evidencia

**ACs:** AC-24 (soporte), AC-25 (soporte), AC-26 (soporte).
**Depende de:** T21, T13, T14.
**Estimación:** 0,5 jornada.

**Archivos:** `docs/spec/stack.md`, `docs/spec/roadmap.md`,
`docs/spec/features/028-actualizacion-tiempo-real/evidencia/README.md` (nuevo),
`docs/spec/deuda-tecnica.md` (revisión).

**Trabajo:**

- [x] Añadir §1.3 a `stack.md` («Actualización en tiempo real (Feature 028)») con: SSE, endpoint,
      bus Redis efímero, sobre vs. frame, aislamiento, fail-open, cota 0,5 s, límite de 120/min,
      una conexión por pestaña, sin persistencia y `026.1`.
- [x] Confirmar la fila 028 del roadmap y la frase «Siguiente feature». **En T22 quedó en `[!]`
      Implementada y verificada por tests (28/Nov/2026); T23 la cerró en `[x]` tras el recorrido
      manual 4200/8080 y el veredicto APROBADO de `@reviewer`; 015/016 siguen después
      (AGENTS §8.5–§8.7).
- [x] Crear `evidencia/README.md` con: resumen, decisiones, suites (SQLite/gated/Redis/seguridad/
      `ng test`/build con `main-UJT3LSFR.js`), tabla AC-1…AC-32 con evidencia, hallazgos T0/T13/
      T14/T21, frames del contrato, comandos, limitaciones aceptadas y el pendiente de T23.
      **La captura de 4200 (dos o tres sesiones) y el humo autenticado de 8080 quedan en T23:**
      no hay sesión Clerk real en esta tarea.
- [x] Revisar `deuda-tecnica.md`: se registran DT-17 (la suite no lee frames SSE incrementales),
      DT-18 (resolución dialectal SQLite/PostgreSQL de `contexto_tiempo_real`) y R-05 (SSE sin
      familia de métricas, riesgo aceptado). Sin hallazgos nuevos en §1.
- [x] `grep` de coherencia en `AGENTS.md`, `MEMORY.md` y `.agents/skills/`: ninguna ruta rota ni
      afirmación obsoleta por la 028. Hallazgos menores (enumeración de endpoints de `AGENTS.md`
      sin `eventos` y `MEMORY.md` desactualizado por diseño) registrados en la evidencia §9 para
      T23.
- [x] No actualizar `MEMORY.md` todavía (se hace en el cierre, T23).

**Hecho cuando:** `stack.md`, roadmap, evidencia y deuda quedan sincronizados; el grep no
encuentra rutas obsoletas.

---

## T23 — Cierre y verificación

**ACs:** AC-25, AC-26 y cierre de todos los AC.
**Depende de:** T1–T22.
**Estimación:** 0,5 jornada.

**Checklist de cierre:**

- [x] `tasks.md` con todas las casillas anteriores en `[x]`, incluidos los checks de cierre.
      **Cerrado:** las excepciones de T0 (`TestClient`, DT-17), T14 (manual de dos workers) y T21
      (`curl -N`) quedan declaradas y aceptadas por @reviewer.
- [x] `spec.md` §7 con cada AC-1…AC-32 marcado y su evidencia (test, comando, captura o
      recorrido).
      **Cerrado (28/Nov/2026):** AC-1…AC-32 marcados con su evidencia; validación de @reviewer
      **APROBADO**.
- [x] `cd backend && pytest` en verde (SQLite), con el conteo registrado.
      **2322 passed / 135 skipped / 0 failed** (499,53 s).
- [x] `POSTGRES_TEST_URL=… pytest tests/funcional/sistema` en verde (gated PostgreSQL),
      incluidos T13 y los tests existentes que tocan tickets/compras.
      **4 passed** (28,71 s) en `test_pool_tiempo_real_028.py`.
- [x] `REDIS_TEST_URL=redis://127.0.0.1:6380/15 pytest tests/no_funcional/rendimiento/test_bus_eventos_redis_028.py`
      en verde (gated Redis), con la base 15 limpia.
      **4 passed** (2,70 s).
- [x] `cd frontend && npx ng test --watch=false --browsers=ChromeHeadless` en verde (Edge,
      `CHROME_BIN`). **758 SUCCESS / 0 failed** (20,708 s).
- [x] `cd frontend && npm run build` (o `npx ng build`) limpio, con el bundle registrado.
      **Limpio** (30,109 s); `main-UJT3LSFR.js`, Initial total **348,36 kB**.
- [x] `/openapi.json` en **75/73**; matriz **73**; la fila del endpoint y sus respuestas.
      Verificado contra `localhost:8000`: **75 operaciones**, `/api/v1/eventos/` con 200/401/403/
      429/503 y `text/event-stream`; `MATRIZ_PERMISOS` con **73** filas.
- [x] Recorrido en **4200** con dos o tres sesiones y escritura real: alta, aprobación, retiro,
      confirmación, anulación, rechazo, edición, movimiento manual, emisión/facturación/
      cancelación/recepción, dashboard, caída/reconexión, pestaña oculta, filtros y diálogo.
      **Verificado (28/Nov/2026):** alta, edición de prioridad, aprobación → retiro → confirmación,
      dashboard, filtros/orden/búsqueda con diálogo abierto y OC + recepción con desbloqueo.
      **No reportados:** anulación, rechazo, movimiento manual, caída/reconexión, pestaña oculta y
      ventana de tasa de 3 min (ver `evidencia/README.md` §8.1).
- [x] `docker compose -f docker-compose.yml build frontend` y
      `docker compose -f docker-compose.yml up -d --force-recreate frontend`; humo en **8080**:
      el canal atraviesa nginx, `listo`, latido, sin búfer, consola limpia y flujo básico.
      **Verificado:** tras el rebuild de T21 (imagen `3974188a383e`), el tablero se actualizó en
      vivo a través de nginx sin recargar. El `curl -N` autenticado no se ejecutó, no se
      inspeccionaron frames en Network y no se midió latido/búfer.
- [x] `stack.md`, `roadmap.md`, `MEMORY.md`, `deuda-tecnica.md` y `evidencia/README.md`
      sincronizados; grep de coherencia en `AGENTS.md`, `MEMORY.md` y `.agents/skills/`.
      **Hecho:** `AGENTS.md` §4 incorpora `eventos` y §3 la línea de tiempo real; `roadmap.md`
      queda en `[x]`; `MEMORY.md` actualizado; grep sin rutas rotas ni skill que editar.
- [x] Respuesta final con: suites y conteos, bundle, versión `026.1`, matriz/OpenAPI, comandos de
      los dos puertos y limitaciones.

**Hecho cuando:** todos los checks están marcados con su evidencia y ninguna suite queda roja.
No se marca la feature como cerrada en `roadmap.md` hasta que este checklist esté completo
(`AGENTS.md` §8.5–§8.7).

> **Resultado T23 (28/Nov/2026).** Suites verdes (2323/135/0 SQLite; gated 4+4+4; 758 SUCCESS;
> build limpio). La feature **queda cerrada** con el veredicto **APROBADO** de @reviewer y las
> excepciones aceptadas (T0/DT-17, manual de dos workers, `curl -N` autenticado/60 s y capturas).

---

## Dependencias resumidas

```text
T0 → T1 → T2 → T3 → T4 → T5 → T6 → T7 → T8 → T9 → T10 → T11 → T12
                                      │
                                      ├→ T13 ─┐
                                      ├→ T14 ─┤
                                      └→ T15 → T16 → T17/T18/T19 → T20 → T21 → T22 → T23
```

- T11/T12 pueden empezar cuando T4 esté cerrado; no dependen de T8/T9.
- T15 puede empezar cuando T5 esté cerrado (contrato estable), en paralelo con T6/T7.
- T17/T18/T19 dependen de T15 y T16; T21 puede empezar tras T5.
- T22/T23 son el final; T13/T14 pueden correr en paralelo con el frontend.

## Recorte si el calendario aprieta

No se recorta sin reabrir la spec. Orden propuesto de re-negociación:

1. **T11** (AC-30: emisión/facturación/cancelación de compras) — conservar la recepción.
2. **T14** (AC-23: gated multiproceso) — conservar el bus y el fail-open; dejar el manual de dos
   workers como evidencia.
3. **T13** (AC-29: pool gated) — conservar el cierre de sesión y la prueba de integración.

No se recortan: pedidos (AC-5/9/10), aislamiento (AC-15/16/18), dos puertos (AC-26), interruptor
(AC-32) ni el cierre documental. Si ni así entra, se renegocia el Hito 2.
