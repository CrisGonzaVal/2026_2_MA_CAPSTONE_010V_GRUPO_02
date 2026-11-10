# Feature 021: Lista de Tareas (tasks.md)

**Estado:** pendiente  
**Spec:** `spec.md` (aprobada)  
**Plan:** `plan.md`

---

## Convenciones
- `[ ]` tarea pendiente · `[x]` tarea completada · `[!]` bloqueada
- Orden de dependencia estricto: no comenzar una tarea sin que las anteriores estén en `[x]`.
- Cada tarea: primero los tests (rojo), luego el código (verde), luego marcar `[x]`.
- **T0 es prerrequisito de T1:** sin la justificación en `stack.md` no se toca el DDL (AGENTS §7).
- Los tests gated de PostgreSQL se ejecutan solo con
  `$env:POSTGRES_TEST_URL = "postgresql://postgres:postgres@localhost:5433/postgres"`.
  La suite ordinaria corre sobre SQLite en memoria y no necesita el contenedor `db`.

---

## Bloque 0 — Justificación Normativa

### T0 — Justificación de la Feature 021 en `stack.md`
**AC cubre:** base normativa de todos  
**Archivos:** `docs/spec/stack.md`

- [x] Agregar la sección «Cobertura automática de pedidos por órdenes de compra (Feature 021)» después de la sección de la 020.
- [x] Declarar la **entidad nueva** `orden_compra_ticket` y el paso de **21 a 22 entidades de dominio** (más `departamento_encargado`, que sigue siendo el puente auxiliar).
- [x] Declarar **27 tablas en `control`** (26 + 1) y **24 por tenant** (23 + 1); versión objetivo **`021.1`**.
- [x] Justificar la columna nullable `historial_transicion_ticket.orden_compra_id` como enlace de auditoría de la recepción, sin cambiar el estado del pedido.
- [x] Justificar el plan congelado al emitir (`orden_compra_ticket`), la asignación automática por prioridad/FIFO, la necesidad neta parcial y la no reserva de stock.
- [x] Justificar que una OC pertenece a una sola sede y que los traspasos entre sedes quedan fuera de alcance.
- [x] Declarar la matriz **72 → 73** con una sola operación (`POST /compras/cobertura/preview`) y **sin capacidad nueva** (se reutiliza `compras`).
- [x] Registrar el renombrado de copia visible (Tickets → Pedidos, Sistema de Tickets → Estados de pedidos, Necesidades → Compras) como cambio de presentación, sin tocar rutas, API, tablas, columnas, permisos ni capacidades.
- [x] Actualizar todas las menciones de conteo y versión del documento (26/23 → 27/24, `020.1` → `021.1`, 21 → 22 entidades, 72 → 73 operaciones).
- [x] Actualizar la nota de vigencia de la base consolidada.

**Hecho cuando:** `stack.md` contiene la justificación completa y ningún conteo contradice 22 entidades / 27 tablas de control / 24 por tenant / `021.1` / 7 capacidades / 73 operaciones.

---

## Bloque A — Base de Datos y Modelos

### T1 — DDL, semilla, versión `021.1` y arranque limpio
**AC cubre:** AC-11 (integridad), AC-12 (contrato/DDL)  
**Archivos:** `database/01_esquema.sql`, `database/02_datos_semilla.sql`, `backend/app/core/config.py`, `backend/tests/test_cobertura_postgres_021.py`

- [x] Tests gated primero (rojo): `27` tablas en `control`, `24` por tenant, versión `021.1`, existencia de `orden_compra_ticket`, columna `orden_compra_id` y sus índices.
- [x] En `control.historial_transicion_ticket`, agregar la columna nullable `orden_compra_id INTEGER` **sin FK inline** (la tabla se crea antes que `orden_compra`).
- [x] Después de crear `control.orden_compra`, agregar con `ALTER TABLE ... ADD CONSTRAINT` la FK `(orden_compra_id) → orden_compra(orden_compra_id)`.
- [x] Crear `control.orden_compra_ticket` después de `factura_compra`, con identity PK, `institucion_id`, `orden_compra_id`, `ticket_id`, `producto_id`, `cantidad_asignada > 0`, `cantidad_faltante >= 0`, `fecha_asignacion`, `UNIQUE (orden_compra_id, ticket_id, producto_id)` y las FKs compuestas de DT-1.
- [x] Agregar los índices `(institucion_id, ticket_id)` y `(institucion_id, producto_id)`.
- [x] En la plantilla tenant, agregar `orden_compra_id` a `historial_transicion_ticket` (nullable, sin FK inline) y la tabla `%1$I.orden_compra_ticket` después de `factura_compra`.
- [x] Agregar al final del arreglo de plantillas tenant el `ALTER TABLE` de la FK del historial, cuando `orden_compra` ya existe.
- [x] Subir el chequeo fail-closed del constructor de `23` a **`24`** y actualizar los `RAISE NOTICE` y comentarios de conteo (26 → 27, 23 → 24).
- [x] Subir `VERSION_ESQUEMA_OBJETIVO` a **`021.1`** en `backend/app/core/config.py`.
- [x] En `02_datos_semilla.sql`, subir `v_version_objetivo` a **`021.1`**.
- [x] Agregar `orden_compra_ticket` a la lista de tablas de la guardia (control y tenant) y a la verificación de existencia del tenant.
- [x] Agregar `orden_compra_ticket:orden_compra_ticket_id` a `resetear_identidades`, aunque la tabla nazca vacía.
- [x] Agregar el `DELETE FROM ... orden_compra_ticket` en la Fase 3 **antes** de `detalle_orden_compra`, `ticket` y `producto`.
- [x] Actualizar los comentarios de conteo y versión de la semilla (26/23 → 27/24, `020.1` → `021.1`).
- [x] Verificar arranque limpio: `docker compose -f docker-compose.yml down -v` y `up -d`; confirmar 4 tenants, **27** tablas en `control`, **24** por tenant, **`021.1`**, tabla nueva vacía en control y en cada tenant, y guardia que no aborta en la primera ejecución.
- [x] Tests gated en verde.

**Evidencia (07/Nov/2026):** `docker compose down -v` + `up -d` arrancó sin errores; `control` **27** tablas, 4 tenants con **24** cada uno (96 en total), versión **`021.1`** en control y tenants, `control.orden_compra_ticket` vacía. `tests/test_cobertura_postgres_021.py` **5 passed** (conteos, versión, tabla, columna/FK del historial, `UNIQUE`/FKs/índices).

**Hecho cuando:** el arranque limpio no aborta; los conteos devuelven 27/24; `control.version_esquema` y cada tenant devuelven `021.1`; la FK del historial y la tabla nueva existen; una segunda ejecución de la semilla aborta por la guardia.

---

### T2 — Modelos SQLAlchemy
**AC cubre:** base para todos los AC  
**Archivos:** `backend/app/models/compra.py`, `backend/app/models/ticket.py`, `backend/app/models/__init__.py`, `backend/tests/api/test_cobertura_021.py` (sección modelos)

- [x] Tests primero (rojo): importación de `OrdenCompraTicket`, creación de una fila con sus FKs lógicas y lectura de `orden.plan` e `historial.orden_compra_id`.
- [x] Clase `OrdenCompraTicket` mapea `orden_compra_ticket` con PK identity, columnas de DT-1, `UniqueConstraint`, FKs compuestas y `CheckConstraint`.
- [x] `OrdenCompra` agrega la relación `plan` (`OrdenCompraTicket`) con `cascade` de lectura y sin borrado en cascada del pedido.
- [x] `HistorialTransicionTicket` agrega `orden_compra_id` nullable y la relación a `OrdenCompra`.
- [x] Registrar `OrdenCompraTicket` en `models/__init__.py`.
- [x] `pytest` sin errores de importación ni de configuración de mappers.

**Evidencia (07/Nov/2026):** `tests/api/test_cobertura_021.py` **1 passed**; `Base.metadata` incluye `orden_compra_ticket`; el plan se lee desde `OrdenCompra.plan` y el historial expone `orden_compra_id` con su relación.

---

## Bloque B — Backend: Schemas, Servicio y Endpoints

### T3 — Schemas Pydantic v2
**AC cubre:** contratos de API de AC-1, AC-2, AC-4, AC-5, AC-6, AC-9, AC-10  
**Archivos:** `backend/app/schemas/compra_schema.py`, `backend/app/schemas/ticket_schema.py`, `backend/tests/api/test_cobertura_021.py` (sección schemas)

- [x] Tests primero (rojo): validación de `CoberturaPreviewSolicitud` (items no vacío, cantidades `> 0`), DTOs de respuesta y campos aditivos sin romper los contratos existentes.
- [x] `NecesidadTicketRespuesta` con `ticket_id`, `asunto`, `solicitante_*`, `prioridad_nombre`, `fecha_creacion`, `cantidad_solicitada`, `cantidad_cubierta` y `cantidad_faltante`.
- [x] `NecesidadReabastecimiento` agrega `stock_comprometido`, `stock_borrador` y `tickets`.
- [x] `CoberturaPreviewSolicitud`, `CoberturaPreviewProducto`, `CoberturaPreviewTicket` y `CoberturaPreviewRespuesta`.
- [x] `PlanOrdenCompraRespuesta` y `OrdenCompraRespuesta.plan`.
- [x] `AsignacionTicketRespuesta` y `CadenaProductoTicketRespuesta` en `ticket_schema.py`.
- [x] `TicketDetalleRespuesta` agrega `asignaciones` y `cadena_productos`.
- [x] `HistorialTransicionRespuesta` agrega `orden_compra_id` y `numero_oc`.
- [x] Solo Pydantic v2 (`ConfigDict`, `model_validate`); los read models se arman a mano.
- [x] `pytest` en verde.

**Evidencia (07/Nov/2026):** `tests/api/test_cobertura_021.py` **5 passed** (4 de schemas + el de modelos de T2); `test_compras.py`, `test_compras_endpoints_020.py`, `test_tablero_kanban.py`, `test_tickets_alcance.py` y `test_tickets_institucional.py` **110 passed** sin regresiones. `PlanOrdenCompraRespuesta` declara `from_attributes` para que `OrdenCompraRespuesta.model_validate` siga funcionando mientras T6 introduce `orden_a_respuesta`.

---

### T4 — Simulación de cobertura y necesidades enriquecidas
**AC cubre:** AC-1, AC-8, AC-9  
**Archivos:** `backend/app/services/compra_service.py`, `backend/tests/api/test_cobertura_021.py` (sección algoritmo/necesidades)

- [x] Tests primero (rojo): prioridad/FIFO, asignación parcial, stock parcial, `plan_previo`, OC `Recibida` que no se resta, OC `Cancelada` que no cubre, pedido de otra sede o sin sede excluido, estados no `EnCurso` excluidos, faltante y cobertura total/parcial/sin cobertura.
- [x] Implementar `_simular_claves(db, institucion_id, claves, cantidades_oc=None, bloquear=False)` con la fórmula de DT-2, devolviendo `dict[(sede_id, producto_id), list[SimulacionTicketProducto]]`.
- [x] El bloqueo `SELECT ... FOR UPDATE` se aplica solo cuando `bloquear=True` y solo en PostgreSQL (SQLite lo ignora).
- [x] `listar_necesidades_reabastecimiento` calcula `stock_comprometido` (OC `Emitida` + `Facturada`), `stock_borrador` (OC `Borrador`) y `sugerido = max(0, stock_minimo + demanda_tickets - stock_actual - stock_comprometido)`.
- [x] La necesidad anida `tickets` con la simulación sin compra nueva (`cantidades_oc = 0`), incluyendo los pedidos que reciben `asignada = 0`.
- [x] Conservar el criterio de fila de la 020 (`stock_actual <= stock_minimo` o `demanda_tickets > stock_actual`) y el filtro de sede inválida → `[]`.
- [x] Agregar `orden_a_respuesta(orden)` para resolver nombres y adjuntar `plan` sin usar `from_attributes` sobre columnas inexistentes.
- [x] No modificar `calcular_cobertura_tickets` ni `stock_disponible`: la simulación parcial es una función nueva.
- [x] Tests en verde.

**Evidencia (07/Nov/2026):** `tests/api/test_cobertura_021.py` **12 passed** (T2 + T3 + 7 de T4). Cubre prioridad sobre FIFO, faltante parcial, reparto parcial de stock, `plan_previo` de OC `Emitida`, OC `Recibida` que no se resta, exclusión de otra sede/sin sede/estados no `EnCurso`, necesidades con comprometido/borrador/sugerido neto y `orden_a_respuesta` con nombres resueltos. `test_compras.py` + `test_compras_endpoints_020.py` **45 passed** sin regresiones.

---

### T5 — Preview de cobertura (`POST /compras/cobertura/preview`)
**AC cubre:** AC-2, AC-10, AC-12  
**Archivos:** `backend/app/services/compra_service.py`, `backend/app/api/v1/endpoints/compras.py`, `backend/tests/api/test_cobertura_021.py` (sección preview)

- [x] Tests primero (rojo): 200 con asignación y faltante, idempotencia, no crea filas en `orden_compra_ticket`, no toca `stock_sede`, sede inexistente/ajena → 404, producto ajeno/inexistente → 404, producto inactivo o repetido → 409, cuerpo inválido → 422.
- [x] Implementar `previsualizar_cobertura(db, datos, identidad)` reutilizando `_simular_claves` con las cantidades simuladas.
- [x] Resolver `cubierto_previo`, `asignado`, `faltante`, `sin_asignar` por producto y `solicitado`, `cubierto_plan`, `cubierto_stock`, `necesidad`, `asignada`, `faltante`, `cobertura` por pedido.
- [x] Endpoint `POST /compras/cobertura/preview` con `response_model`, `status_code=200` y documentación OpenAPI.
- [x] Verificar que preview y emisión comparten la misma simulación: con el mismo estado, las cantidades coinciden.
- [x] Tests en verde.

**Evidencia (07/Nov/2026):** `tests/api/test_cobertura_021.py` **22 passed** (10 nuevos de T5). El preview no persiste `orden_compra_ticket` ni cambia `stock_sede`; es idempotente; sin demanda deja `sin_asignar = cantidad_simulada`; sede inexistente/ajena y producto ajeno/inexistente dan 404; producto inactivo o repetido, 409; cuerpo inválido, 422. HTTP: 200 para Administrador y 403 para Bodeguero/Solicitante/Superadmin. Matriz **73** (preview → `compras`) y los cuatro tests de cardinalidad actualizados; `test_compras.py`, `test_compras_endpoints_020.py`, `test_ciclo_vida_autorizacion_014.py`, `test_detalle_producto_019.py` y `test_filtros_inventario_018.py` **186 passed** en conjunto.

---

### T6 — Emisión con plan congelado y cancelación
**AC cubre:** AC-3, AC-4, AC-7, AC-9  
**Archivos:** `backend/app/services/compra_service.py`, `backend/tests/api/test_cobertura_021.py` (sección emisión/cancelación)

- [x] Tests primero (rojo): la emisión persiste una fila por `(OC, pedido, producto)` con `asignada > 0`, el `faltante` correcto, plan vacío sin demanda, segunda emisión → 409, plan congelado tras facturar/recepcionar, cancelación que conserva el plan y libera la cobertura.
- [x] `emitir_orden_compra` bloquea los pedidos `EnCurso` de la sede que demandan los productos de la OC (`FOR UPDATE` solo en PostgreSQL).
- [x] Ejecuta `_simular_claves` con las cantidades de `detalle_orden_compra` e inserta el plan con `fecha_asignacion = utcnow()`.
- [x] El plan y el cambio a `Emitida` (`numero_oc`, `fecha_emision`) se confirman en la misma transacción; si algo falla, no queda ninguna fila.
- [x] Solo se persisten filas con `asignada > 0`; las OC sin pedidos o sin necesidad neta emiten con plan vacío.
- [x] `GET /compras/ordenes` y las respuestas de emisión/cancelación adjuntan `plan` mediante `orden_a_respuesta`.
- [x] `cancelar_orden_compra` conserva las filas y la OC `Cancelada` deja de sumar en `stock_comprometido`, `comprado` y cobertura activa; no replanifica otras OC.
- [x] Tests en verde.

**Evidencia (07/Nov/2026):** `tests/api/test_cobertura_021.py` **28 passed** (6 nuevos de T6). La emisión reparte por prioridad/FIFO y persiste solo `asignada > 0` (`(ticket_alta, 5, 0)`, `(ticket_baja, 1, 3)`); sin demanda emite con plan vacío; una segunda OC resta el plan previo y re-emitir da 409; el plan no cambia al facturar ni con pedidos nuevos; la cancelación conserva la fila y libera la cobertura (`plan_previo = 0`, `stock_comprometido = 0`); la respuesta HTTP de emisión y `GET /compras/ordenes` exponen `plan` con nombres resueltos. `test_compras.py`, `test_compras_endpoints_020.py` y `test_tablero_kanban.py` **92 passed** en conjunto.

---

### T7 — Recepción: enlace de auditoría en el historial
**AC cubre:** AC-6, AC-7  
**Archivos:** `backend/app/services/compra_service.py`, `backend/app/schemas/ticket_schema.py`, `backend/app/services/ticket_service.py`, `backend/tests/api/test_cobertura_021.py` (sección recepción)

- [x] Tests primero (rojo): la fila `EnCurso → EnCurso` del desbloqueo lleva `orden_compra_id`; las demás filas lo dejan `null`; el historial expone `numero_oc`; el plan de la OC queda intacto; el pedido sigue `EnCurso`.
- [x] `recepcionar_orden_compra` escribe `orden_compra_id` solo en las filas de desbloqueo que crea.
- [x] `HistorialTransicionRespuesta` resuelve `numero_oc` en el servicio; el `orden_compra_id` se conserva aunque la OC luego se cancele.
- [x] No se sella `fecha_cierre` ni se escribe un estado nuevo: `Cerrado` sigue siendo el despacho.
- [x] Tests en verde.

**Evidencia (07/Nov/2026):** `tests/api/test_cobertura_021.py` **30 passed** (2 nuevos de T7). La fila de creación del pedido queda con `orden_compra_id` y `numero_oc` nulos; la fila `EnCurso → EnCurso` del desbloqueo lleva la OC (`numero_oc` resuelto en el DTO), el plan congelado de la OC no cambia y el pedido sigue `EnCurso`. HTTP: `GET /tickets/{id}/historial` como Solicitante publica `orden_compra_id`/`numero_oc`; la recepción como Bodeguero responde 200. `test_ciclo_vida_historial_013.py`, `test_ciclo_vida_flujo_013.py`, `test_compras.py`, `test_compras_endpoints_020.py` y `test_despacho_transaccional.py` **108 passed** en conjunto.

---

### T8 — Detalle del pedido: asignaciones y cadena por producto
**AC cubre:** AC-5, AC-7, AC-9  
**Archivos:** `backend/app/services/ticket_service.py`, `backend/tests/api/test_cobertura_021.py` (sección detalle)

- [x] Tests primero (rojo): asignaciones incluidas las de OC canceladas, cadena por producto, pedido terminal con faltante 0 y `stock_disponible` intacto.
- [x] `obtener_ticket_detalle` agrega `asignaciones` con OC, estado, producto, `cantidad_asignada`, `cantidad_faltante` y fecha.
- [x] Agrega `cadena_productos` con solicitado → comprado → recibido → entregado → faltante, reutilizando `_simular_claves` con `cantidades_oc = 0` para el faltante vivo.
- [x] Las OC canceladas se exponen marcadas y no se presentan como cobertura activa.
- [x] Se conserva el alcance de la 013/017, el 404 idéntico y `stock_disponible` de la 020.
- [x] Tests en verde.

**Evidencia (07/Nov/2026):** `tests/api/test_cobertura_021.py` **34 passed** (4 nuevos de T8). `comprado` incluye las OC activas (`Emitida` + `Facturada` + `Recibida`) y `recibido` solo la `Recibida`; una OC cancelada se expone marcada y no suma; el faltante usa la simulación parcial de stock de `_simular_claves` y queda 0 en pedidos `Cerrado`/`Anulado`; `stock_disponible` no cambia. HTTP: `GET /tickets/{id}` publica `asignaciones` y `cadena_productos`. `test_ciclo_vida_flujo_013.py`, `test_ciclo_vida_historial_013.py`, `test_gobierno_lecturas_017.py`, `test_despacho_dtos.py`, `test_modal_ticket.py`, `test_tickets_alcance.py`, `test_tickets_institucional.py` y `test_compras.py` **223 passed** en conjunto.

---

### T9 — Endpoint, matriz 73 y capacidad `compras`
**AC cubre:** AC-10, AC-12  
**Archivos:** `backend/app/core/permisos.py`, `backend/app/core/capacidades.py`, `backend/app/api/v1/endpoints/compras.py`, `backend/tests/api/test_compras_endpoints_020.py`, `backend/tests/api/test_ciclo_vida_autorizacion_014.py`, `backend/tests/api/test_detalle_producto_019.py`, `backend/tests/api/test_filtros_inventario_018.py`, `backend/tests/api/test_cobertura_021.py`

- [x] Tests primero (rojo): 403 Solicitante/Bodeguero/Superadmin en el preview, 403 con la capacidad `compras` apagada, 200 Administrador, matriz y OpenAPI **73**.
- [x] Agregar `POST /api/v1/compras/cobertura/preview` a `MATRIZ_PERMISOS` con `_COMPRAS_ADMINISTRACION` (72 → 73).
- [x] Asociar la operación a la capacidad `compras` en `MAPA_OPERACION_CAPACIDAD`; no crear capacidad nueva.
- [x] Confirmar que el endpoint declara `response_model`, `status_code` y documentación OpenAPI.
- [x] Actualizar los cuatro tests que hoy fijan 72 a **73**, sin alterar los roles de las rutas existentes.
- [x] Verificar `/openapi.json`: publica la operación nueva y **73** operaciones v1.
- [x] Tests en verde.

**Evidencia (07/Nov/2026):** `tests/api/test_cobertura_021.py` **37 passed**; matriz con `("POST", "/api/v1/compras/cobertura/preview")` → `Administrador` y capacidad `compras`; `/openapi.json` publica la ruta con 200/401/403/404/409/422 y **73** operaciones v1; con la capacidad apagada responde 403. Los cuatro tests de cardinalidad (020, 014, 019, 018) quedaron en 73 y `test_gobierno_identidades_017.py` en 24 tablas tenant. Suite completa de backend: **1495 passed, 1 failed → corregido**, 88 skipped. Gated PostgreSQL 16 de la 021: **5 passed**.

---

## Bloque C — Frontend

### T10 — Helper de etiquetas y renombrado de copia visible
**AC cubre:** V-1, V-2, V-3, V-4  
**Archivos:** `frontend/src/app/shared/utils/etiqueta-estado.ts` (nuevo), `frontend/src/app/shared/utils/etiqueta-estado.spec.ts` (nuevo), `frontend/src/app/app.component.html`, `frontend/src/app/features/tickets/*`, `frontend/src/app/features/dashboard/*`, `frontend/src/app/features/administracion/departamentos.component.html`, `frontend/src/app/features/compras/recepcion-bodega/*`, `frontend/src/app/features/control/capacidades.component.ts` y `.spec.ts`

- [x] Tests primero (rojo): helper con `EnCurso → En Curso`, `EnRevision → En Revisión`, resto igual, `null`/vacíos y espacios; copia visible sin «ticket».
- [x] Crear `etiquetaEstado(nombre)` y aplicarlo al tablero (`ColumnaKanban.etiqueta`), al modal de alta, al badge del detalle, al historial y a las listas de la 021.
- [x] Conservar la lógica por **nombre canónico** (`EnCurso`, `Cerrado`, `Anulado`): el helper es solo de presentación.
- [x] Menú lateral: `Tickets` → **`Pedidos`**; orden de compras **`Compras`**, **`Órdenes de Compra`**, **`Recepción de Compras`**.
- [x] Título **`Estados de pedidos`**; botón **`+ Crear pedido`**; modal, mensajes, detalle, dashboard (`Pedidos Activos`) y recepción en «pedido(s)».
- [x] Capacidad de Control `Tickets` → **`Pedidos`**, conservando el valor persistido `tickets`.
- [x] Títulos de pestaña de `tickets.routes.ts` en «Pedidos» y «Detalle del pedido».
- [x] Actualizar los specs que fijan la copia anterior y los textos de error propios del frontend; no tocar los mensajes canónicos del backend.
- [x] No cambiar rutas (`/tickets`), claves de API, tablas, columnas, permisos, capacidades ni identificadores.
- [x] `ng test` en verde.

**Evidencia (07/Nov/2026):** `etiqueta-estado.spec.ts` **4 passed** (rojo → verde) y suite completa de frontend **528 passed**. El helper separa `EnCurso`/`EnRevision` en tablero, modal, badge, historial y notas; la copia visible quedó en Pedidos/Estados de pedidos/Compras/Pedidos Activos/pedido(s); menú de compras en orden Compras → Órdenes de Compra → Recepción de Compras; capacidad `tickets` rotulada «Pedidos»; títulos «Pedidos | CompuStock» y «Detalle del pedido | CompuStock». Rutas, API y valores persistidos intactos.

---

### T11 — Vistas de la 021
**AC cubre:** AC-1, AC-2, AC-4, AC-5, AC-9  
**Archivos:** `frontend/src/app/shared/interfaces/compra.interface.ts`, `frontend/src/app/shared/interfaces/index.ts`, `frontend/src/app/features/compras/services/compras.service.ts`, `frontend/src/app/features/compras/necesidades/*`, `frontend/src/app/features/compras/lista-ordenes/*`, `frontend/src/app/features/tickets/ticket-detalle.component.*`

- [x] Tests primero (rojo): interfaces, `previsualizarCobertura`, columnas nuevas de necesidades, subfila de pedidos, panel de plan y tablas del detalle.
- [x] `compra.interface.ts` agrega tipos de necesidades, preview, plan y asignaciones; `index.ts` agrega los tipos del detalle del pedido.
- [x] `ComprasService.previsualizarCobertura()` llama a `POST /compras/cobertura/preview`.
- [x] **Necesidades:** columnas `Comprometido` y `Borrador`; subfila por pedido con Ticket, Asunto, Solicitante, Prioridad, Solicitado, Cubierto y Faltante; nota «Comprometido = OC emitidas/facturadas; Borrador no descuenta el sugerido»; sugerido 0 se presenta como cubierto.
- [x] **Órdenes de compra:** botón «Ver pedidos» que expande el `plan` (pedido, solicitante, producto, asignado, faltante); sin plan, «Sin pedidos cubiertos: compra para stock mínimo».
- [x] **Detalle del pedido:** tabla «Cobertura por producto» (Solicitado, Comprado, Recibido, Entregado, Faltante) y tabla «Órdenes de compra que cubren el pedido» (OC, estado, producto, asignado, faltante, fecha); OC cancelada marcada.
- [x] Solo Tailwind, sin CSS quemado; estados con palabras separadas.
- [x] `ng test` en verde y `ng build` sin errores de presupuesto.

**Evidencia (07/Nov/2026):** `compras.service.spec.ts` **14 passed** (preview); `necesidades.component.spec.ts` **9 passed** (comprometido/borrador, subfila de pedidos y sugerido 0 como cubierto); `lista-ordenes.component.spec.ts` + `ticket-detalle.component.spec.ts` **45 passed** (plan de la OC, cobertura por producto, OC que cubren el pedido, cancelada marcada e historial con `numero_oc`). Suite completa de frontend **537 passed**; `ng build` completa sin errores de presupuesto (initial total 337.32 kB, 93.63 kB transferidos).

**Hecho cuando:** el Administrador ve los pedidos detrás de cada necesidad y el plan de cada OC; el detalle del pedido muestra cobertura y OC; `ng test` y `ng build` pasan.

---

## Bloque D — Cierre

### T12 — Checks de Cierre
**AC cubre:** todos  

- [x] `pytest` SQLite: 0 failed, suite completa en verde.
- [x] `pytest` gated PostgreSQL (`$env:POSTGRES_TEST_URL = "postgresql://postgres:postgres@localhost:5433/postgres"`): 0 failed.
- [x] `ng test --watch=false --browsers=ChromeHeadless`: 0 failed.
- [x] `ng build`: sin errores de compilación ni advertencias de presupuesto críticas.
- [x] `/openapi.json`: **73** operaciones v1 y la ruta de preview presente.
- [x] Recorrido funcional en 4200 con escritura real: crear pedido → verlo en necesidades → crear OC → preview → emitir (plan persistido) → facturar → recepcionar → verificar `stock_sede`, historial con OC, cadena y `Cerrado` por despacho.
- [x] Reconstruir imagen: `docker compose -f docker-compose.yml build frontend` y `up -d frontend`.
- [x] Recorrido de humo en 8080: «Pedidos», «Estados de pedidos», «Compras», plan de OC y tablas del detalle presentes; flujo básico responde.
- [x] `grep` de coherencia sobre `AGENTS.md`, `MEMORY.md`, `.agents/skills/` y `stack.md`: sin rutas ni conteos obsoletos (21 → 22 entidades, 26/23 → 27/24, `020.1` → `021.1`, 72 → 73).
- [x] Actualizar `AGENTS.md` §4/§7 (22 entidades, 27/24 tablas, `021.1`).
- [x] Actualizar `MEMORY.md` con el estado de la 021 y sus decisiones.
- [x] Marcar la Feature 021 `[x]` en `roadmap.md` solo después de (a) `tasks.md` completo, (b) AC de `spec.md` §5 con evidencia, (c) tests en verde y (d) recorrido en los dos puertos.
- [x] Anexar en `spec.md` §5 la evidencia de verificación de cada AC y en este archivo la línea **Evidencia** con fechas, conteos y hallazgos.

**Hecho cuando:** los dos puertos responden, las suites están en verde, `stack.md`/`AGENTS.md`/`MEMORY.md`/`roadmap.md` están sincronizados y el grep de coherencia no encuentra afirmaciones obsoletas.

**Evidencia (08/Nov/2026):**

- **Backend:** suite completa **1496 passed, 88 skipped, 0 failed**; gated PostgreSQL 021 **5 passed**; `test_cobertura_021.py` **37 passed**. `test_gobierno_identidades_017.py` se ajustó a las 24 tablas del tenant.
- **Frontend:** `ng test` **537 passed**; `ng build` limpio (337.32 kB iniciales, 93.63 kB transferidos).
- **Contrato:** `/openapi.json` con **73** operaciones v1 y **75** HTTP totales (incluye `GET /` y `GET /health`); `MATRIZ_PERMISOS` = 73; preview presente y única operación nueva.
- **Esquema:** `control` **27** tablas, tenant **24**; `version_esquema` **`021.1`** en control y tenant.
- **Recorrido 4200 con escritura real:** pedido #9 (producto 9 × 15) creado por Solicitante y llevado a `EnCurso` por el Administrador; necesidad con stock 6, mínimo 12, demanda 15, comprometido 0, sugerido 21 y pedido #9 cubierta 6 / faltante 9; preview parcial 5 (asignada 5, faltante 4) y total 21 (asignada 9, faltante 0, sin asignar 12); OC 1 `OC-2026-000001` (21 × 250 = 5250) emitida con plan, factura `F-021-0001`; recepción del Bodeguero con `ENTRADA` 21 (stock 6 → 27), historial `EnCurso → EnCurso` con `orden_compra_id=1` y `numero_oc`, `stock_disponible=true` y cadena 15/9/9/0/0; despacho con `SALIDA` 15 (stock 27 → 12), pedido `Cerrado` y cadena 15/9/9/15/0.
- **Verificación SQL:** `orden_compra_ticket` con 1 fila (OC 1, pedido 9, producto 9, asignada 9, faltante 0); historial con `orden_compra_id=1` solo en la fila de desbloqueo; `stock_sede` sede 2/producto 9 = 12; movimientos 11 `ENTRADA` 21 y 12 `SALIDA` 15.
- **Humo 8080:** imagen reconstruida (`build frontend` + `up -d frontend`) y recorrido de humo sin errores de consola; «Pedidos», «Estados de pedidos», «+ Crear pedido», «En Revisión», «Compras», Comprometido/Borrador, subfilas de pedidos, plan de OC y tablas de cobertura presentes.
- **Capturas:** `evidencia/4200-01…04` y `evidencia/8080-01…04`; las dos `04` se recapturaron tras `scrollIntoView` porque el detalle usa scroll interno y `fullPage` no lo incluía.
