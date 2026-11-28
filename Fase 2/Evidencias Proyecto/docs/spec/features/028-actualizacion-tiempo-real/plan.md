# Plan técnico — Feature 028: Actualización en tiempo real de pedidos y tablero

**Feature:** `028-actualizacion-tiempo-real/`
**Spec:** [spec.md](spec.md) — **aprobada (28/Nov/2026)**
**Plan:** aprobado (28/Nov/2026)
**Hito:** 2 — 11/Dic/2026
**Regla:** este plan implementa la spec aprobada; no la reescribe. Cualquier cambio de alcance
vuelve a la spec y requiere aprobación.

## 0. Resumen ejecutivo

La 028 se implementa con **SSE** sobre el mismo origen y el mismo Bearer de Clerk. Un solo
endpoint (`GET /api/v1/eventos/`) mantiene una conexión por pestaña; el servidor publica un
**sobre interno** por Redis Pub/Sub después del commit de cada mutación y cada conexión lo
transforma en un **frame de invalidación** filtrado por institución, rol, capacidad y dueño. El
cliente no recibe datos: relee por los GET existentes, agrupa ráfagas, resincroniza al abrir y
al volver a foco, y no depende de que el evento llegue.

No hay DDL, entidades nuevas, migraciones, persistencia de eventos ni dependencias nuevas: se
reutiliza el cliente `redis==8.1.0` y el servidor `redis:7.2-alpine` de la 025, y `fetch` nativo
en el navegador.

## 1. Arquitectura de la solución

### 1.1 Componentes y responsabilidades

```text
Servicio de negocio (sync)
  └─ mutación + commit
       └─ evento_service.publicar_*  (best-effort, try/except, cota 0,5 s)
            └─ core.eventos.SobreEvento  (sobre interno: institución, dominios, motivo, dueños)
                 └─ AlmacenRedisEventos.publicar  (cliente sync, socket_timeout 0,5 s)
                      └─ Redis Pub/Sub  (canal compustock:eventos:<institucion_id>)

Navegador (una pestaña)
  └─ TiempoRealService  (fetch + parser SSE + reconexión + visibilidad)
       ├─ tickets.component     (pedidos, inventario)
       ├─ ticket-detalle.component (pedidos, inventario)
       └─ dashboard.component   (pedidos, inventario, dashboard sintético)
            └─ refresco agrupado → GET existentes

Backend SSE (async)
  └─ GET /api/v1/eventos/
       ├─ contexto_tiempo_real  (identidad, institución, rol, capacidades, exp; cierra la sesión)
       └─ generar()  (suscripción Redis async → filtro por conexión → frame)
```

### 1.2 Decisiones técnicas

| ID | Decisión | Por qué / alternativa descartada |
|---|---|---|
| TD-1 | **Publicador sync + suscriptor async.** `AlmacenRedisEventos` usa un cliente `redis.Redis` para publicar y `redis.asyncio` para suscribir. | Los servicios son síncronos (SQLAlchemy sync) y el endpoint SSE es async. Un único cliente sync con `socket_timeout=0,5 s` acota la publicación sin `asyncio.run` ni hilos por mutación. Alternativa descartada: publicar desde el endpoint (se perderían las mutaciones de servicios reutilizados y se acoplaría la ruta a cada caso). |
| TD-2 | **Canal por institución** (`compustock:eventos:<institucion_id>`) y verificación del `institucion_id` del sobre al recibir. | El aislamiento es estructural (no se recibe lo ajeno) y se refuerza con la comprobación. Alternativa descartada: un canal global con filtro en el cliente. |
| TD-3 | **Dependencia de contexto no generadora** que copia la identidad y **cierra la sesión antes de abrir el flujo**. | `get_db` es un generador con `yield`; su cierre ocurre al terminar la respuesta, que en SSE es al cerrar el flujo. La dependencia resuelve y copia todo, y llama `db.close()` antes de devolver. El `finally` de `get_db` vuelve a cerrar (idempotente). Alternativa descartada: sesión propia creada a mano en el endpoint (peor para las costuras de test). |
| TD-4 | `IdentidadAutenticada` gana `expira_en: int \| None = None`, poblado desde `claims["exp"]`. | Es la única forma de cerrar en `exp - 10 s` sin un TTL fijo ni revalidar el token. El default mantiene compatibilidad con los fixtures que construyen la identidad. |
| TD-5 | El endpoint declara `response_class=StreamingResponse`, media type `text/event-stream`, `responses` 200/401/403/429/503 y **no** `response_model`. | El cuerpo no es un documento JSON. La excepción de `AGENTS.md` §6 queda documentada en la descripción y en `responses`. |
| TD-6 | **Almacén de eventos sustituible** a nivel de módulo (`eventos.configurar_almacen`). | Permite un `AlmacenNulo` en la suite heredada (más de 2.000 tests que mutan) y un `BusFalso` en los tests de publicación, sin tocar las firmas de los servicios. La producción crea el almacén Redis de forma perezosa. |
| TD-7 | La marca **`dashboard`** se sintetiza **por conexión** en el suscriptor; nunca viaja en el sobre como dominio de origen. | Una conexión con `dashboard` y sin `tickets`/`inventario` debe refrescar su dashboard sin ver el dominio oculto. Alternativa descartada: enviar el dominio y filtrar en el cliente (fuga). |
| TD-8 | **Frontend con `fetch` + `ReadableStream`**, no `EventSource` ni `HttpClient`. | `EventSource` no permite la cabecera `Authorization`; `HttpClient` puede bufferizar el cuerpo. `fetch` conserva el Bearer y permite cancelar con `AbortController`. |
| TD-9 | **Un hub raíz por pestaña** y un helper de refresco agrupado compartido. | Una conexión por pestaña (límite de 20 conexiones y 120/min) y una sola política de agrupación para las tres vistas. Alternativa descartada: una conexión por componente. |
| TD-10 | **`location = /api/v1/eventos/` en nginx** con `proxy_buffering off`, `proxy_read_timeout` largo y los mismos límites. | La ubicación exacta es más específica que `/api/` y evita que el búfer o el timeout de 60 s corten los latidos. Alternativa descartada: desactivar el búfer en todo `/api/` (afecta al resto sin necesidad). |
| TD-11 | **Cero dependencias nuevas.** | `redis==8.1.0` ya está; el frontend usa APIs nativas; el borde es configuración. |

### 1.3 Flujo de extremo a extremo

1. El usuario ejecuta una mutación (por ejemplo, el Bodeguero registra un retiro).
2. El servicio valida, escribe y **confirma** la transacción (`db.commit()`).
3. Después del commit, el servicio llama a `evento_service.publicar_*` con la institución, el
   motivo y los dueños afectados. La llamada está envuelta en `try/except`; un fallo no cambia la
   respuesta. El intento de publicación tiene una cota de **0,5 s**.
4. El sobre se publica en `compustock:eventos:<institucion_id>`. Si Redis falla o tarda, se
   descarta y se registra un aviso; la mutación ya está confirmada.
5. Cada conexión SSE de esa institución recibe el sobre por su suscripción `redis.asyncio`.
6. El suscriptor aplica, en este orden: institución → audiencia de dueño para `pedidos` →
   visibilidad por rol/capacidad → sustitución `dashboard`. Un Solicitante no dueño no recibe el
   pedido ni la marca.
7. El frame `cambio` sale con los dominios visibles, el motivo (o `cambio` si hay marca) y sin
   identificadores. El cliente agrupa y relee por los GET existentes.
8. Si el bus cae, el flujo sigue abierto con latidos y `estado: degradado`; al volver, `estado:
   recuperado` y el cliente resincroniza. Si el flujo se cierra por `exp - 10 s` o por la vida
   máxima, el cliente reabre con un token vigente y resincroniza.

## 2. Contrato de la API

### 2.1 `GET /api/v1/eventos/`

- **Método y ruta:** `GET /api/v1/eventos/` (barra final canónica).
- **Autenticación:** `Authorization: Bearer <token de Clerk>`. Sin sesión, token inválido o
  vencido: **401**; rol fuera de la matriz: **403**; canal apagado: **503**; límite de tasa:
  **429** con `Retry-After`.
- **Petición:** sin cuerpo ni parámetros de ámbito. `?institucion_id`, `?sede_id`, `?usuario_id`
  y `?dominios` no existen; si llegan, se ignoran.
- **Éxito:** **200** `text/event-stream; charset=utf-8`, `Cache-Control: no-store`,
  `X-Accel-Buffering: no`. La conexión permanece abierta hasta el cierre por credencial, vida
  máxima, cierre de sesión o error.
- **Solo lectura:** no muta datos; cada apertura resincroniza.

### 2.2 Frames

| Frame | `data` | Efecto |
|---|---|---|
| `listo` | `{"dominios": ["pedidos","inventario","dashboard"]}` | Resincronizar las vistas activas una vez |
| `cambio` | `{"dominios": ["pedidos"], "motivo": "retiro"}` | Invalidar las vistas interesadas y agrupar |
| `cambio` sintético | `{"dominios": ["dashboard"], "motivo": "cambio"}` | Refrescar solo el dashboard, sin revelar el dominio oculto |
| `estado` | `{"estado": "degradado"}` / `{"estado": "recuperado"}` | No bloquear la app; al recuperarse, resincronizar |
| Latido | Comentario `: latido` | Mantener viva la conexión |

- `dominios` ∈ `{pedidos, inventario, compras, dashboard}`; `dashboard` es la única marca
  sintética y nunca convive con el dominio oculto que sustituye.
- `motivo` ∈ `{alta, edicion, aprobacion, retiro, confirmacion_entrega, anulacion, rechazo,
  cambio_estado, movimiento, recepcion, emision_oc, facturacion_oc, cancelacion_oc, cambio}`.
- Sin `id:` ni `retry:`; `Last-Event-ID` se ignora. Sin `institucion_id`, `usuario_id` ni ids de
  negocio en el frame.

### 2.3 OpenAPI y gobierno

- La operación se publica con `summary`, `description` (flujo, aislamiento, ciclo de vida y
  excepción de `response_model`), `status_code=200`, `response_class=StreamingResponse` y
  `responses` 200/401/403/429/503.
- **No** declara `response_model` JSON. La excepción se documenta en la descripción y en el
  `responses` 200 con `content: text/event-stream`.
- Se añade **una** fila a `MATRIZ_PERMISOS`: `("GET", "/api/v1/eventos/")` →
  `{Administrador, Bodeguero, Solicitante}`. Matriz **72 → 73**; `/openapi.json` **74 → 75**.
- No se asocia a una capacidad: la visibilidad por dominio se resuelve por conexión. La marca
  `dashboard` usa la capacidad `dashboard` ya existente. El conjunto de **7** capacidades no
  cambia.

## 3. Cambios por archivo

### 3.1 Backend

| Archivo | Acción | Responsabilidad |
|---|---|---|
| `backend/app/core/config.py` | Editar | `TIEMPO_REAL_HABILITADO` (default `true`), `TIEMPO_REAL_LATIDO_SEGUNDOS` (25, 1–30), `MARGEN_RELOJ_SEGUNDOS` (10, >0), `VIDA_MAXIMA_CONEXION_SEGUNDOS` (300, >0), con validadores. |
| `backend/app/core/eventos.py` | **Crear** | `DOMINIOS`, `MOTIVOS`, `SobreEvento` (frozen), `AlmacenEventos` (protocolo), `AlmacenNulo`, `AlmacenRedisEventos`, `SuscripcionEventos`, `ErrorBusEventos`, `configurar_almacen`, `obtener_almacen`, `cerrar_almacen`, `canal_de_institucion`, `serializar/deserializar_sobre`. |
| `backend/app/services/evento_service.py` | **Crear** | `publicar_pedidos`, `publicar_inventario`, `publicar_pedidos_e_inventario`, `publicar_compras`, `_audiencia_de_tickets`, `_publicar` con `try/except` y log; sin lógica de negocio. |
| `backend/app/services/auth_service.py` | Editar | `IdentidadAutenticada.expira_en: int \| None = None`; `resolver_identidad` lo toma de `claims["exp"]`. |
| `backend/app/api/dependencies.py` | Editar | `ContextoTiempoReal` (frozen) y `contexto_tiempo_real`: matriz, institución, rol, capacidades, dominios visibles, `exp`, `request_id`; cierra la sesión antes de devolver. |
| `backend/app/api/v1/endpoints/eventos.py` | **Crear** | Router `/eventos`, ruta, `generar()`, frames, filtro por conexión, heartbeat, cierre y degradación. |
| `backend/app/api/v1/api.py` | Editar | `include_router(eventos.router)`. |
| `backend/app/core/permisos.py` | Editar | Fila `GET /api/v1/eventos/` (72 → 73, en T5). |
| `backend/app/main.py` | Editar | Cierre del almacén de eventos en `shutdown`; nada más (el rate limit y CORS ya están). |
| `backend/app/core/observabilidad.py` | Editar | `LOGGER_TIEMPO_REAL` y `registrar_tiempo_real(resultado, motivo)`; sin PII. |
| `backend/app/services/ticket_service.py` | Editar | Publicación después del commit en alta, edición, aprobación, confirmación, retiro, anulación/rechazo y `PATCH /estado`. |
| `backend/app/services/inventario_service.py` | Editar | Publicación `inventario` después del `commit` de `registrar_movimiento`. |
| `backend/app/services/compra_service/ordenes.py` | Editar | Publicación `compras` (+ `pedidos` con plan) en emisión, facturación y cancelación. |
| `backend/app/services/compra_service/recepcion.py` | Editar | Publicación `inventario` + `compras` (+ `pedidos` si cambia cadena/desbloquea) después del commit. |
| `backend/tests/conftest.py` | Editar | `ALMACEN` nulo por defecto, `TIEMPO_REAL_HABILITADO=False` por defecto, `expira_en` futuro en la identidad de prueba y fixtures de bus. |

No se tocan `database/`, los modelos, los schemas de negocio, los endpoints de tickets, dashboard,
compras o inventario (la publicación vive en los servicios).

### 3.2 Frontend

| Archivo | Acción | Responsabilidad |
|---|---|---|
| `frontend/src/app/core/services/tiempo-real.service.ts` | **Crear** | Hub raíz: conexión, parser SSE, frames, reconexión/backoff, visibilidad, cierre, suscripciones por dominio y resincronización. |
| `frontend/src/app/shared/utils/refresco-agrupado.ts` | **Crear** | Agrupador puro: ventana de silencio 250 ms, espera máxima 1 s, un refresco en vuelo y uno pendiente. |
| `frontend/src/app/app.component.ts` | Editar | Iniciar el hub al montar la shell y detenerlo al destruir. |
| `frontend/src/app/features/tickets/tickets.component.ts` | Editar | Suscripción a `pedidos`/`inventario`, `cargarTablero(silencioso)`, conservación de filtros/orden/búsqueda/scroll. |
| `frontend/src/app/features/tickets/ticket-detalle.component.ts` | Editar | Suscripción a `pedidos`/`inventario`, `cargar(silencioso)`, conservación de diálogo y texto. |
| `frontend/src/app/features/dashboard/dashboard.component.ts` | Editar | Suscripción a `pedidos`/`inventario`/`dashboard`, `cargar(silencioso)`, sin placeholder ni borrado de datos. |
| `frontend/src/app/app.component.spec.ts` y specs de las tres vistas | Editar/Crear | Doble del hub, frames simulados, no doble carga, conservación de estado. |
| `frontend/proxy.conf.json` | Editar | `proxyTimeout: 0` (y `ws: false` si hace falta) para el stream de desarrollo; verificar 4200. |
| `frontend/nginx.conf` | Editar | `location = /api/v1/eventos/` con `proxy_buffering off`, `proxy_cache off`, timeouts largos, `Connection ""`, límites y cabeceras de proxy. |

No se integran la vista de existencias ni el panel de recepciones (fuera de la superficie mínima
de la spec). No se toca `URL_API`: el endpoint es relativo (`/api/v1/eventos/`).

### 3.3 Documentación

| Archivo | Acción |
|---|---|
| `docs/spec/stack.md` | Añadir §1.3 «Actualización en tiempo real (Feature 028)»: SSE, bus, aislamiento, fail-open, límite, sin persistencia, `026.1`. |
| `docs/spec/roadmap.md` | Fila 028 y frase «Siguiente feature» actualizadas (ya hecho en esta fase). |
| `docs/spec/features/028.../evidencia/README.md` | **Crear** al cierre: suites, 4200/8080, capturas, tabla AC. |
| `docs/spec/deuda-tecnica.md` | Revisar; no se espera deuda nueva. |
| `MEMORY.md` | **Solo al cierre** (fuera de esta fase). |

## 4. Identidad y seguridad

### 4.1 Resolución antes del flujo

`contexto_tiempo_real` (en `dependencies.py`) es una dependencia **no generadora**:

1. Recibe `identidad` de `requiere_operacion("GET", "/api/v1/eventos/")` (matriz, 401/403) y
   `db` de `get_db` (la misma sesión cacheada).
2. Resuelve `institucion_id` con `tenant_service.resolver_contexto_solicitud(db, identidad.usuario.correo)`
   sobre el mapa de control (sin abrir sesión de tenant): correo no mapeado o tenant fuera de
   versión → **403**; institución inactiva → **401**; `None` (identidad global) → **403**. No se
   degrada a alcance global.

   > **Corrección T13 (28/Nov/2026).** La versión original de este paso usaba
   > `ambito_service.alcance_institucional(db, identidad)`, que lee `departamento` con la sesión de
   > **control**. En PostgreSQL los departamentos de los usuarios de negocio viven solo en su
   > esquema tenant (`control` conserva únicamente el departamento administrativo), así que toda
   > conexión de Administrador/Bodeguero/Solicitante respondía **403**; la suite SQLite no lo
   > destapaba porque usa un contexto lógico único. El gated de T13 lo reprodujo. Se resuelve con
   > el mismo mapa `correo → esquema` que usa `get_db_negocio`, solo en control y sin sesión
   > tenant. El comportamiento aprobado (resolver la institución desde la identidad, sin sesión
   > tenant y sin degradar a global) no cambia: cambia el mecanismo. En SQLite se conserva
   > `ambito_service` para el contexto lógico único, igual que `get_db_negocio` no resuelve tenant
   > en ese dialecto.
3. Copia `usuario_id`, `rol` (`permisos.nombre_rol_de`), `institucion_id`, `expira_en` y
   `request_id` (de `request.scope["state"]`).
4. Evalúa las capacidades `tickets`, `inventario`, `compras` y `dashboard` con
   `capacidad_service.capacidad_habilitada` y calcula `dominios_visibles` usando las claves de la
   matriz (`GET /tickets/`, `GET /inventario/existencias`, `GET /compras/ordenes`,
   `GET /dashboard/`). Una capacidad ausente cuenta como habilitada (regla 012).
5. En `finally`, `db.close()`. La sesión queda fuera del pool **antes** de que el endpoint
   devuelva el `StreamingResponse`; el `finally` de `get_db` vuelve a cerrar (idempotente).

`ContextoTiempoReal` es un `@dataclass(frozen=True)`; el generador del flujo solo lee esa copia.
No se usa `get_db_negocio` ni se abre una sesión de tenant para escuchar.

### 4.2 Expiración y cierre

- `IdentidadAutenticada.expira_en` es el `exp` del JWT ya validado por `security.validar_token`.
  No se revalida ni se consulta Clerk otra vez.
- El límite de la conexión es
  `min(expira_en - MARGEN_RELOJ_SEGUNDOS, ahora + VIDA_MAXIMA_CONEXION_SEGUNDOS)`.
- Si el límite ya pasó al abrir, se emite `listo` y se cierra; el cliente renueva. Si el token no
  expone `exp` (solo en fixtures antiguos), el límite es `ahora + VIDA_MAXIMA` y se registra un
  aviso; en producción no ocurre porque `resolver_identidad` lo copia.
- Un cierre limpio no envía frame de error: el cliente lo interpreta como renovación.

### 4.3 Credencial, token y logs

- El Bearer viaja solo en `Authorization`; el endpoint no lee URL, cookie ni cuerpo.
- No se crea login, JWT local, ticket de un solo uso ni cookie de sesión.
- El frame no lleva token, correo, institución, usuario ni ids.
- La línea semántica de log (`compustock.tiempo_real`) incluye `request_id`, `route`, `resultado`
  (`abierta`, `cerrada`, `degradada`, `recuperada`) y `motivo`; nunca token, correo, query, IP ni
  datos de negocio.
- La línea de acceso de la 024 sigue saliendo al cerrar el flujo, con la duración total; es
  esperado y no se duplica.

## 5. Publicación

### 5.1 Sobre interno

```text
SobreEvento(
  institucion_id: str,
  dominios: frozenset[str],       # subconjunto de {pedidos, inventario, compras}
  motivo: str,
  usuario_ids: frozenset[int],    # dueños de pedidos; vacío para inventario/compras
)
```

- Canal: `compustock:eventos:<institucion_id>`.
- JSON interno: `{"institucion_id": ..., "dominios": [...], "motivo": ..., "usuario_ids": [...]}`.
- El sobre **nunca** se serializa al frame; el frame lo construye el suscriptor.
- Una mutación con varios dominios (retiro, recepción) produce **un** sobre con el conjunto; no
  se emiten N mensajes. Para `compras` que afecta N pedidos, el sobre lleva el conjunto de
  dueños; el fan-out se resuelve por conexión.

### 5.2 Puntos de publicación

| Mutación | Archivo / función | Después de | Dominios | Dueños |
|---|---|---|---|---|
| Alta | `ticket_service.crear_ticket` | `db.commit()` | `pedidos` | `{ticket.usuario_id}` |
| Edición | `ticket_service.editar_ticket` | `db.commit()` | `pedidos` | `{ticket.usuario_id}` |
| Aprobación | `ticket_service.aprobar_ticket` | `db.commit()` | `pedidos` | `{ticket.usuario_id}` |
| Confirmación | `ticket_service.confirmar_entrega_ticket` | `db.commit()` | `pedidos` | `{ticket.usuario_id}` |
| Retiro | `ticket_service.registrar_retiro_ticket` | `db.commit()` | `pedidos`, `inventario` | `{ticket.usuario_id}` |
| Anulación (EnRevision) | `ticket_service._cambiar_a_anulado` | `db.commit()` | `pedidos` | `{ticket.usuario_id}` |
| Anulación (Cerrado) | `ticket_service._cambiar_a_anulado` | `db.commit()` | `pedidos`, `inventario` | `{ticket.usuario_id}` |
| Rechazo | `ticket_service._cambiar_a_anulado` | `db.commit()` | `pedidos` | `{ticket.usuario_id}` |
| `PATCH /estado` | `ticket_service.actualizar_estado_ticket` | `db.commit()` | `pedidos` | `{ticket.usuario_id}` |
| Movimiento manual | `inventario_service._registrar_movimiento_por_sede` | `db.commit()` | `inventario` | — |
| Emisión de OC | `compra_service.ordenes.emitir_orden_compra` | `_confirmar` | `compras` (+ `pedidos` si `orden.plan` tiene filas) | dueños de `orden.plan` |
| Facturación | `compra_service.ordenes.registrar_o_editar_factura` | `_confirmar` | `compras` (+ `pedidos` si `estado_anterior == Emitida` y hay plan) | dueños del plan |
| Cancelación | `compra_service.ordenes.cancelar_orden_compra` | `_confirmar` | `compras` (+ `pedidos` si `estado_anterior == Emitida` y hay plan) | dueños del plan |
| Recepción | `compra_service.recepcion.recepcionar_orden_compra` | `_confirmar` | `inventario`, `compras` (+ `pedidos` si hay plan o desbloqueados) | dueños del plan ∪ desbloqueados |

Notas:

1. La emisión con plan vacío publica solo `compras`; la cancelación desde `Borrador`, solo
   `compras`; la facturación de una OC ya `Facturada` (corrección), solo `compras`.
2. El alta/edición en `Borrador`, proveedores y preview **no** publican: no cambian
   `GET /tickets/{id}`.
3. La publicación va **después** del commit y antes de la proyección de la respuesta. Si la
   proyección falla, la mutación ya está confirmada y el aviso sigue siendo válido.
4. `_cambiar_a_anulado` conoce la rama (`EnRevision`/`Cerrado`) y publica dentro del mismo
   helper; `anular_ticket` y `rechazar_ticket` no duplican la llamada.

### 5.3 Fail-open y cota

- `evento_service._publicar` envuelve **todo** el camino (consulta de dueños incluida) en
  `try/except Exception`; un fallo registra `WARNING` y retorna. Nunca cambia el status, el
  cuerpo ni la transacción.
- `AlmacenRedisEventos.publicar` usa un cliente sync con `socket_connect_timeout=0,3 s`,
  `socket_timeout=0,5 s`, `max_connections=10`, `Retry(NoBackoff(), 0)` y `decode_responses`.
  La cota de 0,5 s es la del intento; no hay reintento de publicación.
- Un `WARNING` por caída, como máximo cada 10 s (mismo patrón que la 025), con `request_id` y
  `error_type`; sin IP, host, mensaje ni traza.
- Si el bus está caído, la mutación responde igual y `/ready` no cambia.

### 5.4 Suscriptor y filtro

- `AlmacenRedisEventos.suscribir(canal)` crea un `PubSub` async y devuelve una
  `SuscripcionEventos` con `recibir(timeout)` y `cerrar()`.
- `recibir` usa `get_message(ignore_subscribe_messages=True, timeout=...)`; un timeout es
  `None` (latido); un error de Redis levanta `ErrorBusEventos`.
- El bucle del endpoint:
  1. calcula el límite de vida;
  2. suscribe;
  3. emite `listo` con los dominios visibles;
  4. mientras no venza: `recibir(min(latido, restante))`; si hay sobre, filtra y emite `cambio`;
     si no, emite `: latido`;
  5. ante `ErrorBusEventos`: emite `estado: degradado`, cierra el pubsub, reintenta con retroceso
     interno (1, 2, 4, 8, 10 s) sin cerrar el HTTP; al recuperar, `estado: recuperado`;
  6. al vencer, cierra limpiamente.
- Filtro por conexión (`_dominios_visibles_del_sobre`):
  - `pedidos`: si el rol es `Solicitante` y su `usuario_id` no está en `usuario_ids`, se descarta;
    si `pedidos` está en `dominios_visibles`, se añade; si no y `dashboard` está, se añade
    `dashboard`.
  - `inventario`: si está visible, se añade; si no y `dashboard`, se añade `dashboard`.
  - `compras`: si está visible, se añade; si no, se descarta (no afecta al dashboard).
  - Si el conjunto visible queda vacío, **no se emite frame**.
  - Si el conjunto contiene `dashboard` (sintético), el `motivo` se normaliza a `cambio`, aunque
    haya un dominio visible en el mismo frame.
- La marca `dashboard` se añade como máximo una vez. El sobre con `usuario_ids` no se serializa.

## 6. Frontend

### 6.1 `TiempoRealService` (hub raíz)

- Estado: `inactivo | conectando | conectado | degradado | reconectando`; signal `estado` y
  `ultimaConexion`.
- `iniciar()`: idempotente; observa `AutenticacionService.estaAutenticado`/`estadoIdentidad`;
  solo abre con identidad `disponible`; al cerrar sesión aborta y no reintenta.
- `abrirConexion()`:
  - `token = await autenticacion.obtenerToken()`; si `null`, no abre.
  - `fetch(`${URL_API}/eventos/`, {headers: {Authorization: `Bearer ${token}`, Accept:
    'text/event-stream'}, cache: 'no-store', signal})`.
  - `401/403`: cierra y no reintenta; `429`: espera `Retry-After`; `5xx`/red: retroceso.
  - Un `AbortController` por conexión; una sola conexión viva.
- Parser SSE: acumula líneas, interpreta `event:`, `data:`, comentarios `:` y línea vacía;
  `JSON.parse` del `data`; valida `dominios`/`motivo` contra el conjunto cerrado; ignora tipos
  desconocidos. No usa `EventSource`.
- Handlers:
  - `listo` → `resincronizar` (todas las vistas activas) y estado `conectado`.
  - `cambio` → callbacks suscritos a los dominios del frame.
  - `estado: degradado` → estado `degradado`; no bloquea.
  - `estado: recuperado` → `resincronizar` y estado `conectado`.
- Reconexión: retroceso exponencial 1/2/4/8/16/30 s con jitter ±20 %; tope 30 s; mínimo 30 s
  entre aperturas si el token es corto; no reintenta ante 401/403; ante 429 respeta
  `Retry-After`; al reconectar, `listo` dispara la resincronización.
- Visibilidad: `document.hidden` evita refrescos; `visibilitychange` a visible emite una
  resincronización única; no se abre una segunda conexión.
- `alCambio(dominios, callback): () => void` y `alResincronizar(callback): () => void`;
  `detener()` aborta y limpia.
- El servicio no conoce `HttpClient`; el `token.interceptor` no aplica a `fetch`.

### 6.2 Agrupación de refrescos

`crearRefrescoAgrupado(fn, {quietudMs: 250, maxEsperaMs: 1000})`:

- `solicitar()` programa el refresco tras 250 ms de silencio o 1 s desde el primer evento.
- Si ya hay uno en vuelo, marca uno pendiente y lo lanza al terminar; nunca dos a la vez.
- `cancelar()` limpia temporizadores y promesas al destruir la vista.
- Es una función pura con temporizadores inyectables para los tests (`Date`/`setTimeout`
  fake).

### 6.3 Integración por vista

| Vista | Dominios | Cambio |
|---|---|---|
| Tablero | `pedidos`, `inventario` | Suscribe en el constructor/`ngOnInit`; `cargarTablero({silencioso: true})`; no toca `cargandoTablero` ni los signals de filtros/orden/búsqueda; conserva scroll (el `computed` de columnas se recompone). |
| Detalle | `pedidos`, `inventario` | `cargar({silencioso: true})` de detalle + historial; no cierra `<dialog>` ni resetea el formulario/motivo; un fallo mantiene los datos previos. |
| Dashboard | `pedidos`, `inventario`, `dashboard` | `cargar({silencioso: true})`; no muestra el placeholder inicial; conserva `datos` si el refresco falla. |

- Las cargas actuales (`constructor` del tablero, `ngOnInit` del dashboard, carga inicial del
  detalle) se mantienen; el `listo` produce una resincronización adicional (2 GET iniciales como
  máximo). Es el precio de cerrar la carrera entre la lectura y la suscripción.
- `cargando`/`cargandoTablero` solo se activan en la carga inicial y en el reintento manual; el
  refresco silencioso no los enciende.
- La vista de existencias y el panel de recepciones no se suscriben en esta entrega.

### 6.4 Shell

`AppComponent` inyecta `TiempoRealService` y llama `iniciar()` en el constructor; el servicio
reacciona a la sesión y se detiene en `ngOnDestroy`. El shell no cambia de layout.

## 7. Borde

### 7.1 nginx (`frontend/nginx.conf`)

Antes de `location /api/` (la coincidencia exacta es más específica):

```nginx
location = /api/v1/eventos/ {
    limit_req zone=api_peticiones burst=20 nodelay;
    limit_conn api_conexiones 20;

    proxy_pass http://backend:8000;
    proxy_http_version 1.1;
    proxy_set_header Connection "";
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_buffering off;
    proxy_cache off;
    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;
}
```

- `Connection ""` evita el upgrade heredado del template; SSE es HTTP normal.
- El latido de 25 s queda muy por debajo de `proxy_read_timeout`.
- `X-Real-IP` se repite porque el limitador de la 025 lo usa con `LIMITE_TASA_CONFIAR_PROXY=true`.
- `gzip_types` no incluye `text/event-stream`; no se comprime.
- La conexión cuenta una vez en `limit_req` y una conexión en `limit_conn`; el 429 de nginx y el
  de la app conservan el texto común.

### 7.2 Proxy de desarrollo (`frontend/proxy.conf.json`)

- Añadir `"proxyTimeout": 0` (sin timeout de respuesta del proxy) y `"ws": false`.
- Verificar que el dev server no comprime ni bufferiza el flujo; si lo hiciera, desactivar
  `compression` en `angular.json` para `serve` o usar la configuración de proxy sin
  `selfHandleResponse`. Es una verificación de T0/T21, no un cambio de arquitectura.
- `URL_API` sigue siendo relativo; no se abre CORS.

### 7.3 Compose

Sin cambios: `redis` ya existe; `backend` no declara `depends_on` hacia Redis (fail-open). El
backend de Compose corre un worker con `--reload`; el bus soporta más.

## 8. Observabilidad

- **Sin familia de métricas nueva.** `/metrics` no expone SSE; se declara la limitación en
  `stack.md`.
- Línea semántica `compustock.tiempo_real` (JSON, `extra`): `request_id`, `route`
  (`/api/v1/eventos/`), `resultado` (`abierta`, `cerrada`, `degradada`, `recuperada`) y `motivo`
  (`token_expirado`, `vida_maxima`, `sesion`, `bus`, `cliente`, `error`). Sin token, correo,
  query, IP ni ids.
- La línea de acceso de la 024 (`peticion_completada`) seguirá saliendo al cerrar el flujo, con
  `duration_ms` del total; es la evidencia de que el canal no rompe el logging existente.
- La métrica `compustock_http_requests_in_flight` incluirá las conexiones abiertas; es esperado.
  El `registrar_peticion` de cierre usa `route` plantilla y status 200.

## 9. Pruebas por tipo

| Nivel | Archivo(s) | Qué prueba |
|---|---|---|
| Unitarios backend | `tests/funcional/unitarios/test_eventos_028.py` | Constantes/validadores de config; `SobreEvento` y JSON; frames; filtro `_dominios_visibles_del_sobre`; selección de límite `exp`/vida máxima; `AlmacenNulo`. |
| Unitarios backend | `tests/funcional/unitarios/test_evento_service_028.py` | Audiencia de dueños y sobre por mutación con un bus falso; no publicación antes del commit; fail-open con bus que lanza. |
| Integración backend | `tests/funcional/integracion/test_eventos_endpoint_028.py` | 200/401/403/429/503, media type, `listo`, latido con intervalo corto, cierre por token corto, ausencia de `id`/`retry`, `dashboard` sintético, dueño/rol/capacidad, institución. |
| Integración backend | `tests/funcional/integracion/test_publicacion_028.py` | Una prueba por mutación del Anexo A: sobre, dominios, dueños, no publicación en 401/403/404/409/422/rollback; emisión/facturación/cancelación/recepción. |
| Sistema PostgreSQL (gated) | `tests/funcional/sistema/test_pool_tiempo_real_028.py` | Pool pequeño + N flujos ociosos: las peticiones de negocio siguen respondiendo y no se agota el pool; `contexto_tiempo_real` cierra la sesión. |
| Rendimiento / Redis (gated) | `tests/no_funcional/rendimiento/test_bus_eventos_redis_028.py` | Publicación/suscripción real en la base 15; dos instancias de app con el mismo bus; caída de Redis y fail-open; cota 0,5 s. |
| Seguridad / no funcional | `tests/no_funcional/seguridad/test_tiempo_real_028.py` | Aislamiento por institución/rol/dueño, sin ids en el frame, token solo en cabecera, 401/403 y sin PII en logs. |
| Frontend | `frontend/src/app/core/services/tiempo-real.service.spec.ts` | Parser de frames, `listo`/`cambio`/`estado`, JWT, 401/403/429, backoff/jitter, una conexión, visibilidad, `AbortController`. |
| Frontend | `frontend/src/app/shared/utils/refresco-agrupado.spec.ts` | Silencio 250 ms, máximo 1 s, uno en vuelo, uno pendiente, cancelación. |
| Frontend | `tickets.component.spec.ts`, `ticket-detalle.component.spec.ts`, `dashboard.component.spec.ts` | Refresco silencioso, conservación de filtros/orden/búsqueda/scroll/diálogo, no doble carga, datos previos ante fallo, `dashboard` sintético. |
| Frontend | `app.component.spec.ts` | El hub arranca una vez y no rompe el shell. |
| Contrato | `/openapi.json` + `test_contrato_024.py`/`test_permisos_retiro_013.py` | 75 entradas / 73 operaciones; la fila del endpoint; la operación documentada sin `response_model`. |
| Aceptación | `tests/funcional/aceptacion/README.md` y `evidencia/README.md` | Índice de los 32 AC y evidencia del recorrido. |

### 9.1 Estrategia de dobles

- **Suite heredada:** `conftest.py` instala `AlmacenNulo` y `TIEMPO_REAL_HABILITADO=False` al
  importar; las mutaciones publican a un no-op y no abren Redis. Los tests de eventos activan la
  bandera y sustituyen el almacén.
- **Bus falso:** `tests/funcional/integracion/_soporte_eventos_028.py` con
  `BusFalso(publicados, eventos)`; `publicar` guarda el sobre y puede encolar un frame;
  `suscribir` devuelve una suscripción con una cola `asyncio.Queue`.
- **SSE en `TestClient`:** `with client.stream("GET", "/api/v1/eventos/") as respuesta:` y lectura
  de las primeras líneas con un límite; se cierra el contexto. El test no espera al final del
  stream. Si `TestClient` no permite mutar y leer en el mismo hilo, el test separa la mutación
  (servicio + bus falso) de la lectura del stream; la integración completa se hace en 4200.
- **PostgreSQL gated:** `POSTGRES_TEST_URL`; motor temporal, nunca `apt_erp`.
- **Redis gated:** `REDIS_TEST_URL` con `/15`; se vacía al empezar y al terminar; nunca base 0.
- **Frontend:** `fetch` falso con `ReadableStream`; `fakeAsync`/`tick` para el agrupador y el
  backoff; `Subject` para el hub en las vistas.

## 10. Trazabilidad AC → componente → tarea

| AC | Componente | Tareas |
|---|---|---|
| AC-1 | Endpoint/`listo`; hub | T5, T15 |
| AC-2 | Matriz, contexto, endpoint | T2, T5 |
| AC-3 | `exp`, contexto, cierre | T2, T5 |
| AC-4 | Latido, nginx, proxy | T5, T21 |
| AC-5 | Publicación tickets | T8, T9 |
| AC-6 | Movimiento/recepción | T10, T12 |
| AC-7 | Publicación tras commit/fail-open | T4, T8-T12 |
| AC-8 | Almacén, `evento_service`, log | T3, T7, T4 |
| AC-9 | Tablero | T17 |
| AC-10 | Tablero/detalle | T17, T18 |
| AC-11 | Tablero/detalle | T17, T18 |
| AC-12 | Dashboard | T19 |
| AC-13 | Recepción + detalle | T12, T18 |
| AC-14 | Agrupador + vistas | T16, T17, T18 |
| AC-15 | Contexto/filtro | T2, T6 |
| AC-16 | Sobre/filtro | T4, T6 |
| AC-17 | Filtro/capacidades | T6 |
| AC-18 | Frames/sobre | T5, T6, T4 |
| AC-19 | Hub | T15 |
| AC-20 | Agrupador/hub | T16, T15 |
| AC-21 | Borde/límite | T21, T15 |
| AC-22 | Hub | T15 |
| AC-23 | Bus/Redis | T3, T14 |
| AC-24 | Matriz/OpenAPI | T5, T22 |
| AC-25 | Sin DDL/deps | T1, T23 |
| AC-26 | 4200/8080/evidencia | T21, T22, T23 |
| AC-27 | Sobre/fan-out/frames | T4, T6, T5 |
| AC-28 | Marca `dashboard` | T6, T19 |
| AC-29 | Pool/contexto | T13 |
| AC-30 | Compras | T11, T12 |
| AC-31 | Ventana capacidades | T14, T2, T5 |
| AC-32 | Interruptor | T1, T5 |

## 11. Orden de implementación, vertical slice y esfuerzo

### 11.1 Vertical slice temprano (primero)

`T1 → T2 → T3 → T4 → T5 → T6 → T7 → T8 → T17` (backend mínimo + tablero):

- Un alta de pedido publica un sobre y el tablero de otra sesión se actualiza sin recargar.
- Con eso se valida el eslabón más riesgoso (sesión cerrada, bus, filtro, frame, fetch) antes de
  cubrir todas las mutaciones.

### 11.2 Orden crítico

1. **T0** (spike de supuestos) y **T1–T7** (núcleo backend).
2. **T8–T12** (publicación de todas las mutaciones) en paralelo con **T15–T16** (hub frontend).
3. **T17–T20** (vistas) tras T15/T16.
4. **T21** (borde) en paralelo con T17.
5. **T13–T14** (gated) tras T3/T5.
6. **T22–T23** (documentación y cierre) al final.

### 11.3 Estimación

| Fase | Tareas | Esfuerzo |
|---|---|---|
| Núcleo backend | T0–T7 | ~5,25 jornadas |
| Publicación | T8–T12 | ~2,75 jornadas |
| Gated | T13–T14 | ~1,25 jornadas |
| Frontend | T15–T20 | ~2,75 jornadas |
| Borde | T21 | ~0,5 jornada |
| Documentación/cierre | T22–T23 | ~1 jornada |
| **Total** | 24 tareas | **~13,5 jornadas** de un implementador |

Con backend y frontend en paralelo a partir de T5, el camino crítico ronda **10–11 jornadas
calendario**. El Hito 2 (11/Dic) deja un margen estrecho para QA y evidencia; el plan prioriza el
vertical slice.

### 11.4 Si el calendario aprieta

No se recorta en silencio: cualquier recorte deja AC sin cumplir y exige reabrir la spec. Orden
propuesto de recorte **con re-aprobación explícita**:

1. **T11 (AC-30, compras no recepción)**: dejar emisión/facturación/cancelación sin evento y
   conservar la recepción (AC-6/AC-13). Es el recorte menos visible para el flujo de pedidos.
2. **T14 (AC-23, gated multiproceso)**: conservar el bus Redis y el fail-open, pero limitar la
   evidencia al recorrido manual con dos workers.
3. **T13 (AC-29, pool gated)**: conservar el cierre de sesión y la prueba de integración, pero
   sin el gated de pool pequeño.

Lo que **no** se recorta: AC-5/AC-9/AC-10 (pedidos), AC-15/AC-16/AC-18 (aislamiento), AC-26
(dos puertos), AC-32 (interruptor) y el cierre documental. Si ni así entra, el Hito 2 debe
renegociarse; no se declara cerrada una feature con AC sin evidencia.

## 12. Fuera de alcance y no objetivos

- Centro de notificaciones, persistencia, historial, replay, correo, push: 016.
- Polling, WebSocket, login alternativo, cookie de sesión, JWT local.
- Cambios de reglas de negocio, del modelo, del DDL o de la versión `026.1`.
- Vista de existencias y panel de recepciones como superficies suscritas.
- Mutaciones de compras que no cambian `GET /tickets/{id}` (alta/edición en Borrador,
  proveedores, preview).
- Administración, catálogo y organización en tiempo real.
- Rediseño visual; solo se admite un indicador no intrusivo de degradación.
- Dependencias nuevas.

## 13. Cierre (AGENTS §8.5–§8.7)

1. `tasks.md` con todas las casillas `[x]`, incluidas las de cierre.
2. `spec.md` §7 con cada AC marcado y su evidencia.
3. `pytest` (SQLite), gated PostgreSQL y gated Redis en verde; `ng test` y `ng build`.
4. Recorrido funcional en **4200** con dos o tres sesiones y escritura real; **8080** con
   `docker compose build frontend` + `up -d frontend --force-recreate`, canal a través de nginx,
   latido, sin búfer y consola limpia.
5. `/openapi.json` 75/73 y matriz 73.
6. `stack.md` §1.3, `roadmap.md` fila 028, `MEMORY.md` (solo al cierre), `deuda-tecnica.md`,
   `evidencia/README.md`; grep de coherencia en `AGENTS.md`, `MEMORY.md` y `.agents/skills/`.

## 14. Riesgos de implementación

| Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|
| La sesión de `get_db` se retiene y agota el pool | Media | Alto | Contexto copiado + `db.close()` antes del flujo; T0/T13 con pool pequeño. |
| El proxy de desarrollo bufferiza y 4200 no actualiza | Media | Alto | T0 con un stream de prueba; `proxyTimeout: 0`, sin compresión; si falla, documentar y ajustar antes de T17. |
| `TestClient.stream` no permite mutar y leer a la vez | Media | Medio | Separar publicación (servicio + bus falso) de la lectura del stream; el E2E real en 4200. |
| La publicación añade latencia o rompe la suite heredada | Alta | Medio | `AlmacenNulo` en conftest; `try/except`; cota 0,5 s; T4/T7 miden. |
| El cierre en `exp - 10 s` no es estable con tokens cortos | Media | Medio | Leer `exp` del token validado; test con `firmar_token`; mínimo 30 s entre aperturas. |
| El filtro por dueño/dashboard filtra de más o de menos | Media | Alto | Tabla de casos por rol/capacidad/dueño; T6 y AC-27/AC-28. |
| nginx no aplica los límites al location exacto | Media | Medio | Repetir `limit_req`/`limit_conn`; T21 y 8080. |
| Las aserciones 74/72 se relajan | Media | Bajo | Actualización explícita en T5/T22. |
| El calendario no alcanza | Media | Alto | Vertical slice; recortes solo con re-aprobación (§11.4). |

## 15. Preguntas abiertas

Ninguna decisión de producto queda abierta: la spec está aprobada y las cuatro confirmaciones de
§12 están cerradas. Quedan **tres verificaciones técnicas tempranas** (T0), no preguntas de
alcance:

1. ¿El proxy de desarrollo de Angular entrega el stream sin bufferizar en 4200? Si no, el ajuste
   es `proxyTimeout: 0` y desactivar compresión en `serve`; si aun así falla, se documenta y se
   usa el backend directo solo en desarrollo con el origen ya permitido por CORS.
2. ¿`TestClient.stream` permite leer las primeras líneas y cerrar sin bloquear la suite? Si no, se
   usa el bus falso + servicio para la publicación y el E2E real en 4200.
3. ¿El cierre de la sesión en la dependencia de contexto deja el pool libre con el `get_db`
   global? Se verifica con T13 antes de completar las vistas.

Si alguna de las tres falla de forma que obligue a cambiar el contrato o el alcance, se detiene
la implementación y se reabre la spec; no se parchea en silencio.
