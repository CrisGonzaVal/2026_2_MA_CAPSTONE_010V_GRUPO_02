# Feature 020: Plan Técnico de Implementación

**Basado en:** `spec.md` (aprobada, revisión 2 sincronizada con §9)  
**Arquitectura:** FastAPI + SQLAlchemy 2.0 + Angular 18 Standalone + PostgreSQL 16 multi-tenant por esquemas

---

## 1. Decisiones Técnicas Clave

### DT-1 — Proveedor global en `control` y réplica tenant con el mismo ID

El catálogo `proveedor` reside en `control` y es la única estructura compartida. La réplica de cada tenant usa el **mismo `proveedor_id` entero** que control, sin identidad propia:

- `control.proveedor.proveedor_id` es `GENERATED ALWAYS AS IDENTITY`.
- `<tenant>.proveedor.proveedor_id` es `INTEGER PRIMARY KEY` (sin identidad).
- La correspondencia es determinista e idempotente; no hay FK cross-schema.

Al crear o editar una OC, el servicio:

1. Lee el proveedor en una **sesión de control** (`crear_sesion_control`) y exige `activo = true`.
2. Hace *upsert* de la réplica en la sesión tenant con el mismo `proveedor_id` (inserta o actualiza los datos de snapshot).
3. Confirma la OC en la transacción tenant, que referencia la réplica local.

El *upsert* de la réplica puede confirmarse antes de la OC: una réplica sin uso es inofensiva y no requiere una transacción distribuida entre esquemas.

**Alternativa descartada:** FK cross-schema — prohibida por `stack.md` §2.

### DT-2 — Recepción por confirmación total (sin cantidades en el body)

`POST /compras/ordenes/{id}/recepcion` no recibe cantidades. El backend lee `detalle_orden_compra.cantidad_solicitada` y las aplica. No hay ambigüedad de recepciones parciales.

### DT-3 — `stock_sede` como única fuente de saldo (Feature 011)

El incremento ACID actúa sobre `stock_sede`. Si no existe la fila `(sede_id, producto_id)`, el servicio la crea con `stock_actual = cantidad_recibida`. `inventario` legado no participa.

### DT-4 — `usuario_id` del receptor en `observacion`, no en columna nueva

`movimiento_inventario` no tiene columna de autor. La referencia al Bodeguero se porta en `observacion`: `"Recepción OC-2026-000001 / Factura FAC-98421 — Bodeguero: juan.perez@compustock.cl"`. La glosa se trunca a 250 caracteres (largo de la columna). No se toca el DDL de `movimiento_inventario`.

### DT-5 — `stock_disponible` calculado con la misma asignación greedy

`TicketDetalleRespuesta` agrega `stock_disponible: bool`. Se calcula en `ticket_service.obtener_ticket_detalle` con la misma simulación que usa la recepción:

1. Solo tickets `EnCurso` de la sede del ticket.
2. Orden: `prioridad_id` ascendente (Alta=1, Media=2, Baja=3), luego `fecha_creacion` ascendente, luego `ticket_id` ascendente.
3. Asignación por producto y **todo o nada por ticket**: si un ticket no cabe completo, no consume stock y se pasa al siguiente.
4. Un ticket con `sede_id` nulo o en estado distinto de `EnCurso` devuelve `false`.

La simulación es de lectura: no reserva stock. El campo se calcula **solo en el detalle** (`GET /tickets/{ticket_id}`); la lista no lo incluye para no pagar el costo en cada fila.

### DT-6 — Capacidad institucional `compras` y versión `020.1`

Se agrega `compras` al conjunto cerrado `CAPACIDADES` de `control_canonico.py`, al `CHECK` de `control.funcion_institucion` y a la semilla. Pasa de 6 a 7 capacidades; la semilla siembra **28 filas** (4 instituciones × 7). Los endpoints de compras exigen `compras` habilitada; el Superadmin no se gatea porque no tiene tenant. La versión objetivo sube de `014.1` a **`020.1`** en `backend/app/core/config.py` y en `02_datos_semilla.sql`.

### DT-7 — Número de OC derivado del ID, sin carrera

`numero_oc = OC-{AÑO}-{orden_compra_id:06d}` se asigna al emitir. No se usa `SELECT MAX + 1 FOR UPDATE`, que no bloquea filas inexistentes y obliga a manejar colisiones. El `UNIQUE` del número se conserva como defensa. Mientras la OC está en `Borrador`, `numero_oc` es `NULL`.

### DT-8 — Desbloqueo de tickets por prioridad + FIFO

En la transacción ACID de recepción, el servicio:

1. Calcula la cobertura de los tickets `EnCurso` de la sede **antes** de incrementar stock.
2. Incrementa stock y genera los movimientos `ENTRADA`.
3. Recalcula la cobertura **después** del incremento.
4. Por cada ticket que pasa de no cubierto a cubierto, inserta una fila en `historial_transicion_ticket` con `estado_origen_id = estado_destino_id = EnCurso`, actor = Bodeguero y motivo `"Desbloqueo por reabastecimiento: OC … / Factura …"`.

No se cambia el estado del ticket ni se crea una tabla de notificaciones. La misma función de simulación se reutiliza en `obtener_ticket_detalle`.

### DT-9 — Sesión de control y sesión tenant en el catálogo global

Los endpoints de proveedores reciben **dos** sesiones:

- `db_control: Session = Depends(get_db)` — catálogo global.
- `db_negocio: Session = Depends(get_db_negocio)` — tenant del Administrador; para el Superadmin es la sesión de control y no se usa para replicar.

`POST /compras/proveedores` escribe en `control.proveedor`. Si el actor es Administrador, replica en su tenant; si es Superadmin, no replica. `GET /compras/proveedores` lee solo control. Las operaciones de OC usan `db_negocio` (tenant) y `db_control` solo para validar el proveedor.

### DT-10 — Factura con proveedor explícito y FK compuesta

`factura_compra` porta `proveedor_id` para declarar `UNIQUE (proveedor_id, numero_factura)`. Una FK compuesta `(orden_compra_id, proveedor_id) → orden_compra(orden_compra_id, proveedor_id)` impide que la factura y la OC pertenezcan a proveedores distintos. `orden_compra` declara `UNIQUE (orden_compra_id, proveedor_id)` como destino de esa FK.

### DT-11 — Excepción acotada de producto inactivo

- Crear o editar una OC exige que todos los productos estén activos (`409` si alguno no lo está).
- Emitir una OC vuelve a exigir productos activos.
- Recepcionar **sí** permite un producto que se desactivó después de la emisión: la mercadería ya fue despachada y la Trazabilidad Absoluta exige registrarla. El producto sigue inactivo y el endpoint genérico `POST /inventario/movimientos` conserva su `409`.
- La recepción **no** llama a `registrar_movimiento`; escribe `StockSede` y `MovimientoInventario` dentro de su propia transacción, con el mismo orden de bloqueo producto → `stock_sede`.

### DT-12 — Cancelación con actor, fecha y motivo

`orden_compra` agrega `motivo_cancelacion VARCHAR(500)`, `fecha_cancelacion TIMESTAMP` y `cancelado_por_usuario_id INTEGER` (FK a `usuario`). La cancelación solo procede desde `Borrador` o `Emitida`; `Facturada`, `Recibida` o `Cancelada` responden `409`.

### DT-13 — Contrato: 10 operaciones y matriz 72

La feature agrega **10** operaciones a la matriz central (62 → **72**): las 9 del flujo más `PUT /compras/ordenes/{id}` para editar el borrador que exige AC-3. Todas se asocian a la capacidad `compras` en `capacidades.py`.

### DT-14 — Edición del borrador

`PUT /compras/ordenes/{id}` reemplaza sede, proveedor e ítems solo si la OC está en `Borrador`. Recalcula `total`, valida productos activos y no toca stock. Una OC emitida, facturada, recibida o cancelada responde `409`.

---

## 2. Nuevas Entidades y Cambios al DDL

### 2.1 En `control` (esquema global) — 22 → 26 tablas

| Tabla | Acción | Columnas clave |
|---|---|---|
| `proveedor` | **NUEVA** | `proveedor_id` identity PK, `rut VARCHAR(20) NOT NULL UNIQUE`, `razon_social VARCHAR(150) NOT NULL`, `nombre_fantasia VARCHAR(100)`, `giro VARCHAR(100)`, `correo VARCHAR(100)`, `telefono VARCHAR(20)`, `activo BOOLEAN NOT NULL DEFAULT TRUE` |
| `orden_compra` | **NUEVA** | `orden_compra_id` identity PK, `numero_oc VARCHAR(30) UNIQUE`, `institucion_id FK`, `sede_id`, `proveedor_id FK`, `estado VARCHAR(20)` con CHECK, `total NUMERIC(12,2)`, `motivo_cancelacion VARCHAR(500)`, `cancelado_por_usuario_id FK`, `fecha_creacion`, `fecha_emision`, `fecha_recepcion`, `fecha_cancelacion`; `UNIQUE (orden_compra_id, proveedor_id)` y `UNIQUE (institucion_id, orden_compra_id)` |
| `detalle_orden_compra` | **NUEVA** | `detalle_orden_compra_id` identity PK, `orden_compra_id`, `institucion_id`, `producto_id`, `cantidad_solicitada INT CHECK > 0`, `precio_unitario NUMERIC(10,2) CHECK >= 0`; FK compuesta a `orden_compra(institucion_id, orden_compra_id)` y a `producto(institucion_id, producto_id)`; `UNIQUE (orden_compra_id, producto_id)` |
| `factura_compra` | **NUEVA** | `factura_compra_id` identity PK, `orden_compra_id UNIQUE`, `proveedor_id`, `numero_factura VARCHAR(50)`, `fecha_factura DATE`, `monto_total NUMERIC(12,2) CHECK > 0`, `observaciones VARCHAR(500)`, `fecha_registro`; `UNIQUE (proveedor_id, numero_factura)`; FK compuesta `(orden_compra_id, proveedor_id)` |

`control.proveedor` es el catálogo global y **no se vacía** en la Fase 3 de la semilla. Las otras tres tablas de control son de paridad estructural y quedan vacías.

### 2.2 En cada esquema tenant — 19 → 23 tablas

Las cuatro tablas se agregan a la plantilla de `01_esquema.sql` con las mismas columnas y restricciones, con estas diferencias:

- `proveedor.proveedor_id` es `INTEGER PRIMARY KEY` (sin identidad), porque replica el ID de control.
- `proveedor` incluye `UNIQUE (rut)`.
- `orden_compra` usa `institucion_id` + `sede_id` con FK compuesta a `sede(institucion_id, sede_id)`.
- `detalle_orden_compra` y `factura_compra` usan FK compuestas locales; no hay referencias cross-schema.

**Versión de esquema objetivo:** `020.1`  
**Conteo actualizado:** 17 entidades de dominio + 4 nuevas = **21 entidades de dominio** + `departamento_encargado` auxiliar. **26 tablas en control**, **23 por tenant**.

### 2.3 Semilla (`02_datos_semilla.sql`)

- Insertar 3 proveedores de muestra en `control.proveedor` con IDs explícitos (1, 2, 3).
- Replicarlos en cada tenant con `INSERT INTO <tenant>.proveedor SELECT * FROM control.proveedor` (sin `OVERRIDING SYSTEM VALUE`).
- Agregar `compras` al `VALUES` de `funcion_institucion` (28 filas).
- Subir `v_version_objetivo` a `020.1`.
- Agregar las 4 tablas a las listas de guardia (control y tenant), a la verificación de existencia de tablas del tenant y a la replicación.
- Agregar `DELETE FROM control.factura_compra`, `detalle_orden_compra` y `orden_compra` a la Fase 3 (vacías por diseño); **no** agregar `control.proveedor` a los `DELETE`.
- Actualizar los comentarios de conteo (`24 filas = 4 x 6` → `28 filas = 4 x 7`) y el docstring de `control_service._inicializar_capacidades` / `_provisionar_tenant_postgres` (seis → siete; 17 → 23 tablas), aunque el comportamiento ya se deriva de `CAPACIDADES` y `Base.metadata`.

---

## 3. Estructura de Archivos por Capa

### Backend

```
backend/app/
├── models/
│   ├── compra.py                 [NUEVO] — Proveedor (tenant), OrdenCompra, DetalleOrdenCompra, FacturaCompra
│   └── control_canonico.py       [MODIFICA] — ProveedorControl y 'compras' en CAPACIDADES
├── schemas/
│   └── compra_schema.py          [NUEVO] — DTOs Pydantic v2
├── services/
│   └── compra_service.py         [NUEVO] — CRUD de OC, factura, recepción ACID y cobertura de tickets
├── api/v1/endpoints/
│   └── compras.py                [NUEVO] — Router /compras con 10 endpoints
├── api/v1/api.py                 [MODIFICA] — Registra el router
├── core/
│   ├── permisos.py               [MODIFICA] — 10 operaciones nuevas (62 → 72)
│   ├── capacidades.py            [MODIFICA] — Asocia las 10 operaciones a 'compras'
│   └── config.py                 [MODIFICA] — VERSION_ESQUEMA_OBJETIVO = '020.1'
├── services/control_service.py   [MODIFICA] — Comentarios de conteo (comportamiento automático)
└── services/ticket_service.py    [MODIFICA] — stock_disponible en el detalle
```

### Database

```
database/
├── 01_esquema.sql               [MODIFICA] — 4 tablas en control (26) y en la plantilla tenant (23)
└── 02_datos_semilla.sql         [MODIFICA] — 3 proveedores, 7 capacidades, versión 020.1, guardias
```

### Frontend

```
frontend/src/app/
├── features/compras/            [NUEVO]
│   ├── compras.routes.ts
│   ├── necesidades/
│   │   └── necesidades.component.ts
│   ├── lista-ordenes/
│   │   └── lista-ordenes.component.ts
│   ├── nueva-orden/
│   │   └── nueva-orden.component.ts       (crear y editar borrador)
│   ├── recepcion-bodega/
│   │   └── recepcion-bodega.component.ts
│   └── services/
│       └── compras.service.ts
├── shared/interfaces/
│   └── compra.interface.ts      [NUEVO]
├── core/auth/roles.ts           [MODIFICA] — roles de las rutas de compras
├── features/tickets/            [MODIFICA] — badge stock_disponible en el detalle
└── app.routes.ts / layout       [MODIFICA] — lazy loading y enlaces por rol
```

---

## 4. Endpoints REST

| Método | Ruta | Rol | AC |
|---|---|---|---|
| `GET` | `/api/v1/compras/necesidades` | Administrador | AC-1 |
| `GET` | `/api/v1/compras/proveedores` | Administrador, Superadmin | AC-2 |
| `POST` | `/api/v1/compras/proveedores` | Administrador, Superadmin | AC-2 |
| `POST` | `/api/v1/compras/ordenes` | Administrador | AC-3 |
| `GET` | `/api/v1/compras/ordenes` | Administrador (todas), Bodeguero (solo `Facturada` de su sede) | AC-3, AC-6 |
| `PUT` | `/api/v1/compras/ordenes/{orden_id}` | Administrador | AC-3 |
| `POST` | `/api/v1/compras/ordenes/{orden_id}/emitir` | Administrador | AC-4 |
| `PUT` | `/api/v1/compras/ordenes/{orden_id}/factura` | Administrador | AC-5 |
| `POST` | `/api/v1/compras/ordenes/{orden_id}/recepcion` | Bodeguero | AC-7, AC-8, AC-9, AC-10, AC-11 |
| `POST` | `/api/v1/compras/ordenes/{orden_id}/cancelar` | Administrador | AC-12 |

**Query params:** `GET /compras/necesidades?sede_id=` (opcional; filtro de lista, 200/`[]` si no existe o es ajeno) y `GET /compras/ordenes?estado=&sede_id=` (solo Administrador; el Bodeguero queda forzado a `Facturada` + su sede).

**Precedencia de errores:** 401 → 403 (matriz) → 403 (capacidad `compras`) → 409 (Bodeguero sin sede) → 404 (recurso ajeno/inexistente) → 200/201.

**Respuestas:** todas las rutas declaran `response_model`, `status_code` explícito y documentación OpenAPI. `POST` de creación responde `201`; el resto `200`.

---

## 5. Estrategia de Tests

### Backend (pytest — SQLite en memoria)

`tests/api/test_compras.py`:

- **AC-1:** necesidades agrupadas por sede/producto; fórmula `max(0, min + demanda - stock)`; solo `EnCurso`; `sede_id` ajeno → 200/`[]`.
- **AC-2:** 201 al crear proveedor como Administrador; 201 como Superadmin; 409 por RUT duplicado; 403 como Bodeguero/Solicitante; el proveedor creado por Superadmin no crea réplica tenant.
- **AC-3:** 201 al crear OC en Borrador; 422 sin sede/proveedor/ítems; 409 con producto inactivo; `PUT` edita borrador; `PUT` sobre `Emitida` → 409.
- **AC-4:** 200 al emitir; `numero_oc` con formato; 409 si ya emitida; 409 si un producto se desactivó antes de emitir.
- **AC-5:** 200 al registrar factura; 409 por número duplicado del mismo proveedor; 409 si la OC no está `Emitida`; 200 al editar factura en `Facturada`; 409 si la OC ya está `Recibida`; 422 por fecha futura.
- **AC-6:** Administrador ve todas las OC de su institución; Bodeguero solo las `Facturada` de su sede; Bodeguero sin sede → 409; OC ajena por ID → 404.
- **AC-7:** 409 al recepcionar una OC no `Facturada`.
- **AC-8:** 200 al confirmar; `stock_sede` incrementado; fila creada si no existía; OC en `Recibida` con `fecha_recepcion`.
- **AC-9:** `movimiento_inventario` con `tipo_movimiento = 'ENTRADA'`, `stock_sede_id`, cantidad y `observacion` con OC/Factura/Bodeguero; sin `usuario_id`.
- **AC-10:** tickets `EnCurso` desbloqueados por prioridad/FIFO; tickets `Pendiente`, `EnRevision`, `Cerrado` y `Anulado` excluidos; un ticket que no cabe completo no consume stock; fila de historial con `estado_origen = estado_destino = EnCurso`.
- **AC-11:** `GET /tickets/{id}` devuelve `stock_disponible = true/false` con la misma simulación; el badge no cambia el estado.
- **AC-12:** 200 al cancelar desde Borrador/Emitida con motivo; persiste actor/fecha/motivo; 409 desde Facturada/Recibida/Cancelada.
- **AC-13:** 403 para todos los roles sin permiso; 403 del Superadmin en OC/recepción/necesidades; 403 con capacidad `compras` apagada.
- **AC-14:** aislamiento con fixtures de dos instituciones; la réplica usa el mismo ID; no hay fuga de OC/facturas entre tenants.
- **Excepción de producto inactivo:** la recepción de una OC emitida con un producto luego desactivado se registra; `POST /inventario/movimientos` sobre el mismo producto sigue devolviendo 409.

### Backend gated (PostgreSQL 16)

- Creación de esquemas y las 23 tablas por tenant; 26 en control.
- `control.proveedor` conserva los 3 proveedores tras la semilla; cada tenant tiene las 3 réplicas con el mismo ID.
- 28 filas de `funcion_institucion`; versión `020.1` en control y en los 4 tenants.
- Recepción concurrente: dos hilos, uno recibe y el otro recibe `409`; el stock se incrementa una sola vez.
- La FK compuesta de `factura_compra` rechaza un proveedor distinto al de la OC.
- El producto inactivo se puede recepcionar y el movimiento queda auditado.

### Frontend (ng test — Edge Headless)

- `ComprasService` con los 10 métodos y `inject(HttpClient)`.
- `necesidades.component`: tabla por sede/producto y sugerido.
- `lista-ordenes.component`: badges de estado, filtros, acciones por estado.
- `nueva-orden.component`: crear y editar borrador; valida sede, proveedor e ítems; alta de proveedor inline.
- `recepcion-bodega.component`: solo OC `Facturada` de la sede; confirmación simple; mensaje de éxito.
- Detalle de ticket: badge `stock_disponible` visible solo cuando es `true`.
- `ng build` sin errores de presupuesto.

---

## 6. Orden de Implementación y Riesgos

1. **T0** actualiza `stack.md` con la justificación §7 (21 entidades, 26/23, `020.1`, capacidad `compras`, matriz 72, `stock_disponible` y excepción de producto inactivo).
2. **T1** materializa el DDL y la semilla; sin T0 no se toca la base.
3. **T2–T3** modelos y schemas; la suite SQLite debe importar sin errores.
4. **T4–T5** servicios; primero los tests rojos, luego la lógica.
5. **T6** endpoints, matriz y capacidad; verificar `/openapi.json` con 10 rutas nuevas.
6. **T7–T9** frontend; T8 incluye la vista de necesidades y la edición del borrador.
7. **T10** cierre: suites, gated, build, 4200, 8080 reconstruido y grep de coherencia.

**Riesgos principales:**

- **Semilla:** borrar `control.proveedor` en la Fase 3 eliminaría el catálogo global. T1 debe excluirlo explícitamente.
- **Sesiones cruzadas:** el catálogo global se lee/escribe en control; la OC vive en el tenant. No usar la sesión tenant para `control.proveedor` ni la de control para las OC.
- **Historial de tickets:** la fila de desbloqueo usa el mismo estado origen/destino; no se cambia el estado ni se sella `fecha_cierre`.
- **Producto inactivo:** la excepción vive solo en `compra_service`; no relajar `inventario_service` ni el endpoint genérico.
- **SQLite:** no valida esquemas, FK compuestas ni concurrencia; esos AC se prueban en el gated de PostgreSQL 16.
