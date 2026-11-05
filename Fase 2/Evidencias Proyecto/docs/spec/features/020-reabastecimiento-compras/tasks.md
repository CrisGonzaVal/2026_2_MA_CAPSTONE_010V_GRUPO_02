# Feature 020: Lista de Tareas (tasks.md)

**Estado:** cerrada (04/Nov/2026)  
**Spec:** `spec.md` (aprobada, revisión 2 sincronizada con §9)  
**Plan:** `plan.md`

---

## Convenciones
- `[ ]` tarea pendiente · `[x]` tarea completada · `[!]` bloqueada
- Orden de dependencia estricto: no comenzar una tarea sin que las anteriores estén en `[x]`.
- Cada tarea: primero los tests (rojo), luego el código (verde), luego marcar `[x]`.
- **T0 es prerrequisito de T1:** sin la justificación en `stack.md` no se toca el DDL (AGENTS §7).

---

## Bloque 0 — Justificación Normativa

### T0 — Justificación de la Feature 020 en `stack.md`
**AC cubre:** base normativa de todos  
**Archivos:** `docs/spec/stack.md`

- [x] Agregar la sección "Reabastecimiento externo y compras (Feature 020)" después de la sección de la 019.
- [x] Declarar las **4 entidades nuevas** (`proveedor`, `orden_compra`, `detalle_orden_compra`, `factura_compra`) y el paso de **17 a 21 entidades de dominio** (+ `departamento_encargado` auxiliar).
- [x] Declarar **26 tablas en control** (22 + 4) y **23 por tenant** (19 + 4); versión objetivo **`020.1`**.
- [x] Declarar la **séptima capacidad `compras`** (ampliación explícita del conjunto cerrado de la 012) y la matriz **62 → 72**.
- [x] Justificar el catálogo global en `control` con réplica tenant del **mismo `proveedor_id`** y sin FK cross-schema; `control.proveedor` es la única estructura compartida.
- [x] Justificar `stock_disponible` como propiedad calculada (sin columna), la asignación greedy por prioridad/FIFO y la fila de historial con `estado_origen = estado_destino = EnCurso`.
- [x] Justificar la excepción acotada de producto inactivo: la OC nace/emite con productos activos; la recepción registra un producto desactivado después de la emisión; el endpoint genérico conserva su 409.
- [x] Actualizar la nota de vigencia de la base consolidada (fecha y conteos 26/23, versión `020.1`).

**Hecho cuando:** `stack.md` contiene la justificación completa y ningún conteo contradice 21 entidades / 26 tablas de control / 23 por tenant / `020.1` / 7 capacidades / 72 operaciones.

---

## Bloque A — Base de Datos y Modelos

### T1 — DDL: 4 tablas nuevas en control y tenant, capacidad `compras` y versión `020.1`
**AC cubre:** AC-2 (proveedor), AC-3 (OC), AC-5 (factura), AC-14 (integridad)  
**Archivos:** `database/01_esquema.sql`, `database/02_datos_semilla.sql`, `backend/app/core/config.py`, `backend/app/models/control_canonico.py`

- [x] Agregar `control.proveedor` (identity PK, `rut` único, `razon_social`, `nombre_fantasia`, `giro`, `correo`, `telefono`, `activo`).
- [x] Agregar `control.orden_compra` (identity PK, `numero_oc` único, `institucion_id`, `sede_id`, `proveedor_id`, `estado` con CHECK, `total`, `motivo_cancelacion`, `cancelado_por_usuario_id`, `fecha_creacion`, `fecha_emision`, `fecha_recepcion`, `fecha_cancelacion`; `UNIQUE (orden_compra_id, proveedor_id)` y `UNIQUE (institucion_id, orden_compra_id)`).
- [x] Agregar `control.detalle_orden_compra` (identity PK, FK compuesta a `orden_compra(institucion_id, orden_compra_id)` y a `producto(institucion_id, producto_id)`, `cantidad_solicitada > 0`, `precio_unitario >= 0`, `UNIQUE (orden_compra_id, producto_id)`).
- [x] Agregar `control.factura_compra` (identity PK, `orden_compra_id` único, `proveedor_id`, `numero_factura`, `fecha_factura`, `monto_total > 0`, `observaciones`, `fecha_registro`; `UNIQUE (proveedor_id, numero_factura)`; FK compuesta `(orden_compra_id, proveedor_id)`).
- [x] Agregar las mismas 4 tablas a la plantilla tenant, con `proveedor.proveedor_id INTEGER PRIMARY KEY` (sin identidad) y las FKs locales.
- [x] Agregar `compras` a `CAPACIDADES` en `backend/app/models/control_canonico.py`; el `CHECK` de `control.funcion_institucion` se actualiza con la lista de 7.
- [x] Actualizar `VERSION_ESQUEMA_OBJETIVO` a `020.1` en `backend/app/core/config.py`.
- [x] Sembrar 3 proveedores de muestra en `control.proveedor` con IDs explícitos (1, 2, 3).
- [x] Replicar los 3 proveedores en cada tenant con `INSERT INTO <tenant>.proveedor SELECT * FROM control.proveedor` (sin `OVERRIDING SYSTEM VALUE`).
- [x] Agregar `compras` al `VALUES` de `funcion_institucion` en la semilla (28 filas = 4 × 7).
- [x] Subir `v_version_objetivo` a `020.1` en `02_datos_semilla.sql`.
- [x] Agregar las 4 tablas a las listas de guardia (control y tenant), a la verificación de existencia de tablas del tenant y a la replicación.
- [x] Agregar `DELETE FROM control.factura_compra`, `control.detalle_orden_compra` y `control.orden_compra` a la Fase 3; **no** agregar `control.proveedor` a los `DELETE` (es catálogo global).
- [x] Actualizar los comentarios de conteo de la semilla y los docstrings de `control_service._inicializar_capacidades` / `_provisionar_tenant_postgres` (siete capacidades, 23 tablas).
- [x] Verificar arranque limpio: `docker compose down -v` y `docker compose up -d`. Confirmar 4 tenants, **26** tablas en control, **23** por tenant, **28** filas de capacidad, **3** proveedores en control y en cada tenant, versión **`020.1`**.

**Hecho cuando:** `docker compose up -d` arranca sin errores; las consultas de conteo devuelven 26/23/28/3; `SELECT version FROM control.version_esquema` y la de cada tenant devuelven `020.1`; la guardia de la semilla no aborta en la primera ejecución y sí en una segunda.

---

### T2 — Modelos SQLAlchemy
**AC cubre:** base para todos los AC  
**Archivos:** `backend/app/models/compra.py`, `backend/app/models/control_canonico.py`, `backend/app/models/__init__.py`

- [x] Clase `Proveedor` (tenant, `proveedor_id` PK sin identidad) mapea `proveedor`.
- [x] Clase `ProveedorControl` (`BaseControl`, identity PK) mapea `control.proveedor`.
- [x] Clase `OrdenCompra` (tenant) con relationships a `Sede`, `Proveedor`, `DetalleOrdenCompra`, `FacturaCompra` y `Usuario` (cancelador).
- [x] Clase `DetalleOrdenCompra` (tenant) con relationship a `Producto`.
- [x] Clase `FacturaCompra` (tenant) con relationship a `OrdenCompra` y `Proveedor`.
- [x] Registrar `Proveedor`, `OrdenCompra`, `DetalleOrdenCompra` y `FacturaCompra` en `models/__init__.py`; exportar `ProveedorControl`.
- [x] `pytest` en verde (la suite SQLite no valida esquemas multi-tenant, pero los modelos deben importar sin error).

**Hecho cuando:** `cd backend && python -m pytest` pasa sin errores de importación relacionados con `compra.py`; `Base.metadata` incluye las 4 tablas tenant y `BaseControl.metadata` incluye `proveedor`.

---

## Bloque B — Backend: Schemas, Servicio y Endpoints

### T3 — Schemas Pydantic v2 (`backend/app/schemas/compra_schema.py`)
**AC cubre:** contratos de API para todos los AC  
**Archivos:** `backend/app/schemas/compra_schema.py`

- [x] `ProveedorCrear` (RUT no vacío y único, razón social no vacía, contacto opcional) y `ProveedorRespuesta`.
- [x] `OrdenCompraCrear` y `OrdenCompraActualizar` (`sede_id`, `proveedor_id`, `items` con `min_length=1`), `OrdenCompraRespuesta` (proveedor, sede, items y factura anidados).
- [x] `DetalleOrdenCompraCrear` (`producto_id`, `cantidad_solicitada > 0`, `precio_unitario >= 0`) y `DetalleOrdenCompraRespuesta`.
- [x] `FacturaCompraRegistrar` (`numero_factura` 1..50, `fecha_factura`, `monto_total > 0`, `observaciones` ≤ 500) y `FacturaCompraRespuesta`.
- [x] `RecepcionRespuesta` (orden, estado, `fecha_recepcion`, movimientos y tickets desbloqueados); el endpoint no recibe cantidades.
- [x] `NecesidadReabastecimiento` (`sede_id`, `sede_nombre`, `producto_id`, `nombre`, `stock_actual`, `stock_minimo`, `demanda_tickets`, `sugerido`).
- [x] `model_config = ConfigDict(from_attributes=True)` solo en los DTO de entidad; los read models se arman a mano.
- [x] `pytest` en verde.

**Hecho cuando:** `pytest` pasa; todos los schemas importan; ninguno usa `class Config`; `FacturaCompraRegistrar` rechaza fecha futura en el servicio (no en el schema) y `monto_total <= 0` en Pydantic.

---

### T4 — Servicio de compras — Parte 1: catálogo, necesidades y CRUD de OC
**AC cubre:** AC-1, AC-2, AC-3, AC-4, AC-5, AC-12  
**Archivos:** `backend/app/services/compra_service.py`, `backend/tests/api/test_compras.py` (sección T4)

- [x] Tests primero (rojo): necesidades, alta de proveedor (Admin/Superadmin/RUT duplicado), crear OC, editar borrador, emitir, factura (alta/edición/duplicado/futura), cancelar (actor/fecha/motivo), producto inactivo.
- [x] `listar_necesidades_reabastecimiento(db, institucion_id, sede_id=None)` — agrupa por `(sede, producto)`, solo productos activos y tickets `EnCurso`; `sugerido = max(0, stock_minimo + demanda - stock_actual)`; `sede_id` ajeno → `[]`.
- [x] `listar_proveedores(db_control)` — solo activos, orden por razón social.
- [x] `crear_proveedor(db_control, db_tenant, datos, identidad)` — escribe en control; si el actor es Administrador, replica en su tenant; el Superadmin no replica; RUT duplicado → 409.
- [x] `crear_orden_compra(db_tenant, db_control, datos, contexto)` — valida sede de la institución, proveedor activo en control, *upsert* de la réplica, productos activos, sin duplicados y al menos 1 ítem; estado `Borrador`; total calculado.
- [x] `actualizar_orden_compra(...)` — solo `Borrador`; reemplaza sede/proveedor/ítems; recalcula total; 409 en cualquier otro estado.
- [x] `emitir_orden_compra(...)` — solo `Borrador`; valida productos activos; asigna `numero_oc = OC-{AÑO}-{orden_compra_id:06d}` y `fecha_emision`; 409 si ya está emitida.
- [x] `registrar_o_editar_factura(...)` — `Emitida` crea y pasa a `Facturada`; `Facturada` actualiza metadatos; `Recibida`/`Cancelada` → 409; unicidad `(proveedor_id, numero_factura)`; fecha futura → 422.
- [x] `cancelar_orden_compra(...)` — solo `Borrador`/`Emitida`; persiste `motivo_cancelacion`, `fecha_cancelacion` y `cancelado_por_usuario_id`; 409 desde `Facturada`/`Recibida`/`Cancelada`.
- [x] Tests en verde.

**Hecho cuando:** `pytest` pasa; AC-1, AC-2, AC-3, AC-4, AC-5 y AC-12 cubiertos; la OC creada por un Administrador deja la réplica del proveedor en su tenant y la creada por Superadmin no.

---

### T5 — Servicio de compras — Parte 2: recepción ACID y cobertura de tickets
**AC cubre:** AC-7, AC-8, AC-9, AC-10, AC-11  
**Archivos:** `backend/app/services/compra_service.py` (continuación), `backend/app/services/ticket_service.py`, `backend/tests/api/test_compras.py` (sección T5)

- [x] Tests primero (rojo): recepción exitosa, sin factura, concurrente (gated), producto inactivo, prioridad/FIFO, ticket que no cabe completo, fila de historial, creación de fila de stock.
- [x] `calcular_cobertura_tickets(db, sede_id, producto_ids=None)` — solo `EnCurso`; orden `prioridad_id ASC`, `fecha_creacion ASC`, `ticket_id ASC`; asignación por producto y todo o nada por ticket.
- [x] `recepcionar_orden_compra(db_tenant, orden_id, contexto)`:
  - Resuelve la sede del Bodeguero (409 si no tiene) y la OC (404 si es de otra sede o institución).
  - `SELECT FOR UPDATE` sobre la OC; 409 si no está `Facturada` o ya fue recepcionada.
  - Ordena los detalles por `producto_id`, bloquea producto y `stock_sede`, incrementa o crea la fila, e inserta `MovimientoInventario` tipo `ENTRADA` con `stock_sede_id` y `observacion` (OC/Factura/Bodeguero).
  - Calcula cobertura antes/después; inserta `HistorialTransicionTicket` con `estado_origen = estado_destino = EnCurso` para cada ticket que pasa a cubierto.
  - Sella `fecha_recepcion`, cambia a `Recibida` y confirma una sola transacción.
- [x] `obtener_ticket_detalle` calcula `stock_disponible` con `calcular_cobertura_tickets` y lo expone en `TicketDetalleRespuesta`.
- [x] Tests en verde (SQLite) y gated PostgreSQL para concurrencia y esquemas.

**Hecho cuando:** `pytest` pasa; AC-7…AC-11 cubiertos; un producto desactivado después de la emisión se recepciona y el endpoint genérico de movimientos sigue devolviendo 409; la recepción concurrente incrementa el stock una sola vez.

---

### T6 — Endpoints, matriz y capacidad (`backend/app/api/v1/endpoints/compras.py`)
**AC cubre:** AC-6, AC-13, AC-14 (gating y segregación)  
**Archivos:** `backend/app/api/v1/endpoints/compras.py`, `backend/app/api/v1/api.py`, `backend/app/core/permisos.py`, `backend/app/core/capacidades.py`

- [x] Tests primero (rojo): 403 Bodeguero emite OC, 403 Solicitante registra factura, 403 sin capacidad `compras`, 404 OC de otra institución, 200 lista vacía de Bodeguero sin OC en su sede, 409 Bodeguero sin sede, 200/201 de los roles autorizados.
- [x] Agregar las **10** operaciones a `MATRIZ_PERMISOS` (62 → 72) con los roles del plan §4.
- [x] Asociar las 10 operaciones a la capacidad `compras` en `MAPA_OPERACION_CAPACIDAD`.
- [x] Router `/compras` con los 10 endpoints, `response_model`, `status_code` explícito y doc OpenAPI.
- [x] `GET /compras/proveedores` y `POST /compras/proveedores` inyectan `db_control` y `db_negocio`; el POST del Superadmin no replica.
- [x] `GET /compras/ordenes` aplica el ámbito del Bodeguero (sede + `Facturada`) y los filtros del Administrador; las OC ajenas responden 404.
- [x] Registrar el router en `api.py`.
- [x] Tests en verde; `/openapi.json` contiene las 10 rutas.

**Hecho cuando:** `pytest` pasa; `/openapi.json` lista las 10 operaciones; 403 correcto para todos los roles no autorizados; la matriz tiene 72 entradas.

**Evidencia (03/Nov/2026):** `tests/api/test_compras_endpoints_020.py` **26/26** en verde; matriz **72** y `/openapi.json` publica las 10 rutas; suite SQLite completa **1447 passed, 83 skipped**; gated 020 **6/6**. En SQLite la ausencia de réplica del Superadmin no es observable (control y tenant comparten la tabla física `proveedor`); esa evidencia queda en el gated `test_administrador_replica_y_superadmin_no_replica`.

---

## Bloque C — Frontend

### T7 — Interfaces y servicio Angular (`compra.interface.ts` + `compras.service.ts`)
**AC cubre:** base para T8 y T9  
**Archivos:** `frontend/src/app/shared/interfaces/compra.interface.ts`, `frontend/src/app/features/compras/services/compras.service.ts`

- [x] Tests primero (rojo): spec del servicio con spy de `HttpClient`.
- [x] Interfaces TypeScript: `Proveedor`, `OrdenCompra`, `DetalleOrdenCompra`, `FacturaCompra`, `NecesidadReabastecimiento`, `RecepcionRespuesta`.
- [x] `ComprasService` con métodos: `listarNecesidades(sedeId?)`, `listarProveedores()`, `crearProveedor()`, `crearOrden()`, `actualizarOrden()`, `emitirOrden()`, `registrarFactura()`, `editarFactura()`, `listarOrdenes(filtros)`, `recepcionar()`, `cancelarOrden()`.
- [x] Tests en verde.

**Hecho cuando:** `ng test` pasa; el servicio es inyectable con `inject(HttpClient)` y cubre los 10 endpoints.

**Evidencia (03/Nov/2026):** `compras.service.spec.ts` **13/13** en verde (`HttpTestingController`); suite Angular completa **483/483**. Los tipos viven en `shared/interfaces/compra.interface.ts` y se reexportan desde `index.ts`, conservando el punto de importación único del repo. `registrarFactura` y `editarFactura` comparten el mismo `PUT` idempotente (AC-5).

---

### T8 — Vista de Administrador: necesidades, lista y edición de Órdenes de Compra
**AC cubre:** AC-1, AC-2, AC-3, AC-4, AC-5, AC-12  
**Archivos:** `frontend/src/app/features/compras/necesidades/`, `lista-ordenes/`, `nueva-orden/`, `compras.routes.ts`, `frontend/src/app/core/auth/roles.ts`

- [x] Tests primero (rojo): render de componentes, badges de estado, botones habilitados por estado, formulario reactivo.
- [x] `necesidades.component.ts`: tabla por sede/producto con stock, mínimo, demanda y sugerido; filtro por sede.
- [x] `lista-ordenes.component.ts`: tabla reactiva de OCs con badges (`Borrador`, `Emitida`, `Facturada`, `Recibida`, `Cancelada`), filtros por estado y sede, acciones por estado.
- [x] `nueva-orden.component.ts`: crear y editar borrador con selector de proveedor (alta inline), sede de destino y detalle de ítems (producto + cantidad + precio); validación reactiva.
- [x] Modal de registro/edición de factura (número, fecha, monto, observaciones).
- [x] Confirmación de cancelación con campo de motivo (máx. 500).
- [x] `compras.routes.ts` con lazy loading: `/compras`, `/compras/necesidades`, `/compras/nueva`, `/compras/:id/editar`; `ROLES_COMPRAS_ADMIN` en `roles.ts`.
- [x] Enlace en el menú lateral para Administrador: "Órdenes de Compra" y "Necesidades".
- [x] Tests en verde; `ng build` sin errores de presupuesto.

**Hecho cuando:** `ng test` pasa; `ng build` limpio; el Administrador recorre necesidades → crear/editar borrador → emitir → facturar → cancelar.

**Evidencia (04/Nov/2026):** `ng test` **510/510** (39 nuevos: necesidades 6, lista 8, nueva orden 9, rutas 3, navegación 1, servicio 13 previos) y `ng build` limpio (`main-P4V2BVV4.js`, sin avisos de presupuesto). La edición se carga desde el listado institucional (no hay `GET /compras/ordenes/{id}`) y se bloquea fuera de `Borrador`; `registrarFactura`/`editarFactura` comparten el `PUT` idempotente (AC-5).

---

### T9 — Vista de Bodeguero: recepción en bodega + badge de stock en tickets
**AC cubre:** AC-6, AC-7, AC-8, AC-10, AC-11  
**Archivos:** `frontend/src/app/features/compras/recepcion-bodega/`, `frontend/src/app/features/tickets/`, `frontend/src/app/core/auth/roles.ts`

- [x] Tests primero (rojo): render de `recepcion-bodega.component`, botón habilitado solo si `Facturada`, badge de stock en el detalle del ticket.
- [x] `recepcion-bodega.component.ts`: lista de OC `Facturada` de la sede del Bodeguero, detalle de ítems y factura, modal de confirmación simple y mensaje "Orden de compra recepcionada exitosamente".
- [x] Modificación en el componente de detalle de ticket: badge `"Stock disponible — Listo para despacho"` si `stock_disponible == true`.
- [x] `ROLES_COMPRAS_BODEGA` en `roles.ts`; enlace lateral "Recepción de Compras" bajo `compras/recepcion`.
- [x] Tests en verde; `ng build` sin errores.

**Hecho cuando:** `ng test` pasa; `ng build` limpio; el Bodeguero solo ve sus OC facturadas y el Solicitante ve el badge cuando corresponde.

**Evidencia (04/Nov/2026):** `ng test` **518/518** (7 nuevos: recepción 4, rutas 1, navegación 1, badge del ticket 2 —uno por presencia y ausencia—) y `ng build` limpio (`main-DYJHWLAX.js`). El segmento `/compras` pasó a `ROLES_COMPRAS` (Administrador + Bodeguero) y cada vista hija exige su rol con `RolGuard`: `recepcion` es la única del Bodeguero. El panel no envía filtros; el servidor fuerza `Facturada` + sede y responde 409 sin sede.

---

## Bloque D — Cierre

### T10 — Checks de Cierre
**AC cubre:** todos  

- [x] `pytest` SQLite: 0 failed, suite completa en verde.
- [x] `pytest` gated PostgreSQL (`$env:POSTGRES_TEST_URL = "postgresql://postgres:postgres@localhost:5433/postgres"`): 0 failed.
- [x] `ng test --watch=false --browsers=ChromeHeadless`: 0 failed.
- [x] `ng build`: sin errores de compilación ni advertencias de presupuesto críticas.
- [x] Recorrido funcional en 4200: crear/editar OC, emitir, registrar factura, recepcionar en bodega, verificar `stock_sede`, badge en ticket e historial de desbloqueo.
- [x] Reconstruir imagen: `docker compose -f docker-compose.yml build frontend` y `up -d frontend`.
- [x] Recorrido de humo en 8080: vistas de compras presentes y flujo básico funcional.
- [x] `grep` de coherencia sobre `AGENTS.md`, `MEMORY.md`, `.agents/skills/` y `stack.md`: sin rutas ni conteos obsoletos.
- [x] Actualizar `MEMORY.md` y marcar la Feature 020 `[x]` en `roadmap.md` solo después de (a)…(d).
- [x] Verificar que `stack.md` ya contiene la sección 020 de T0 (no volver a agregarla).

**Hecho cuando:** los dos puertos responden, las suites están en verde, `stack.md`/`MEMORY.md`/`roadmap.md` están sincronizados y el grep de coherencia no encuentra afirmaciones obsoletas.

**Evidencia (04–05/Nov/2026):** `pytest` completa con gated PostgreSQL 16 **1533 passed / 18 warnings / 0 failed** (624,36 s); `ng test` **518/518 SUCCESS**; `ng build` limpio (`main-DYJHWLAX.js`, idéntico al de T9) y `/openapi.json` con las **10** operaciones de compras sobre 72 protegidas. Recorrido 4200 con escritura real: necesidades → OC `OC-2026-000001` (borrador editado 6→8, emitido, factura `F-2026-020`) → cancelación de `Borrador #2` con motivo obligatorio → recepción del Bodeguero con `stock_sede` 6→14 → ticket #10 sin badge, OC `OC-2026-000003` con factura `F-2026-021`, recepción con «Se desbloquearon 1 ticket(s)» y `stock_sede` sin fila→3, historial `EnCurso → EnCurso` con motivo OC/Factura y badge «Stock disponible — Listo para despacho». Humo 8080 tras reconstruir la imagen: menú del Administrador, listado con las tres OC y sus estados/facturas, y deep link a `/compras/necesidades` servido por nginx. Grep de coherencia: se corrigieron `MEMORY.md` (7 capacidades, 020 cerrada), `AGENTS.md` §4/§7 (26/23 tablas, `020.1`, 21 entidades, `compras`) y las skills `fastapi-pydantic-v2` y `sdd-workflow` (17→21 entidades); `stack.md` conserva la sección 020 de T0. Detalle y capturas en `evidencia/README.md`.
