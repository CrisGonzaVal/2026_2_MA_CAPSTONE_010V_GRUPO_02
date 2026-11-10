# Feature 021: Plan Técnico de Implementación

**Basado en:** `spec.md` (aprobada)  
**Arquitectura:** FastAPI + SQLAlchemy 2.0 + Angular 18 Standalone + PostgreSQL 16 multi-tenant por esquemas

---

## 1. Decisiones Técnicas Clave

### DT-1 — `orden_compra_ticket`: una fila por `(OC, pedido, producto)`

La única tabla nueva es `orden_compra_ticket`. Guarda la **intención** de qué
unidades de una OC cubren a qué pedido:

| Columna | Tipo | Regla |
|---|---|---|
| `orden_compra_ticket_id` | identity PK | — |
| `institucion_id` | `VARCHAR(20)` NOT NULL | Ancla multi-tenant |
| `orden_compra_id` | `INTEGER` NOT NULL | OC que asigna |
| `ticket_id` | `INTEGER` NOT NULL | Pedido cubierto |
| `producto_id` | `INTEGER` NOT NULL | Producto asignado |
| `cantidad_asignada` | `INTEGER` NOT NULL | `> 0` |
| `cantidad_faltante` | `INTEGER` NOT NULL | `>= 0`; foto del hueco que dejó esta OC |
| `fecha_asignacion` | `TIMESTAMP` NOT NULL | `CURRENT_TIMESTAMP` |

Restricciones:

- `UNIQUE (orden_compra_id, ticket_id, producto_id)`.
- FK compuesta `(institucion_id, orden_compra_id) → orden_compra(institucion_id, orden_compra_id)`.
- FK compuesta `(orden_compra_id, producto_id) → detalle_orden_compra(orden_compra_id, producto_id)`: impide asignar un producto que no está en el detalle de esa OC.
- FK compuesta `(institucion_id, ticket_id) → ticket(institucion_id, ticket_id)`.
- FK compuesta `(institucion_id, producto_id) → producto(institucion_id, producto_id)`.
- `CHECK (cantidad_asignada > 0)` y `CHECK (cantidad_faltante >= 0)`.

Índices adicionales (la única cubre búsquedas por OC; faltan las de pedido y
producto):

- `(institucion_id, ticket_id)` — detalle del pedido y cadena.
- `(institucion_id, producto_id)` — cálculo de cobertura por producto.

**Por qué una sola tabla:** el plan es un puente entre la compra y el pedido. Una
segunda tabla de «detalle del plan» duplicaría la clave y no aportaría nada; la
fila ya contiene la cantidad asignada y el faltante de esa asignación.

### DT-2 — Un único algoritmo de necesidad neta parcial

Toda lectura y escritura de cobertura usa la misma función determinista. Para
cada clave `(sede, producto)` y cada pedido `EnCurso`:

```
plan_previo      = Σ cantidad_asignada de OC Emitida + Facturada
comprado         = Σ cantidad_asignada de OC Emitida + Facturada + Recibida
comprado_pendiente = Σ cantidad_asignada de OC Emitida + Facturada
recibido         = Σ cantidad_asignada de OC Recibida
entregado        = Σ detalle_ticket.cantidad_entregada del producto
base             = max(0, solicitado - plan_previo - entregado)
stock_cubierto   = min(base, stock_restante)
necesidad_neta   = base - stock_cubierto
asignada         = min(necesidad_neta, cantidad_oc_restante)
faltante         = necesidad_neta - asignada
```

Reglas:

1. Solo pedidos `EnCurso` de la sede de la OC, ordenados por
   `prioridad_id ASC, fecha_creacion ASC, ticket_id ASC`.
2. `plan_previo` **no** incluye OC `Recibida`: su cantidad ya está en
   `stock_actual`. Tampoco incluye `Cancelada` (no cubre) ni `Borrador` (no tiene
   plan).
3. El stock físico se reparte **parcialmente** entre pedidos, en el mismo orden.
   No se reserva: es una simulación de lectura.
4. La cantidad de la OC se reparte parcialmente sobre `necesidad_neta`. La compra
   que sobra es reposición de mínimo y no genera fila.
5. Se devuelve una simulación por **todos** los pedidos que demandan el producto,
   incluidos los que reciben `asignada = 0`. La emisión persiste solo las filas
   con `asignada > 0`; el preview las muestra todas.
6. `faltante` es el hueco **después** de esta OC. En la necesidad (sin compra
   nueva) coincide con `necesidad_neta`.
7. `cobertura` = `total` si `faltante = 0`; `sin_cobertura` si
   `plan_previo + stock_cubierto + entregado + asignada = 0`; `parcial` en el
   resto.

La función se implementa como `_simular_claves(db, institucion_id, claves,
cantidades_oc=None, bloquear=False)` y devuelve
`dict[(sede_id, producto_id), list[SimulacionTicketProducto]]`. Es la misma para
necesidades, preview, emisión y cadena del pedido.

### DT-3 — Necesidades enriquecidas y sugerido neto

`GET /compras/necesidades` conserva su alcance y su filtro de lista, y agrega:

- `stock_comprometido`: suma de `detalle_orden_compra.cantidad_solicitada` de OC
  `Emitida` + `Facturada` de la sede/producto.
- `stock_borrador`: la misma suma para OC `Borrador`.
- `sugerido = max(0, stock_minimo + demanda_tickets - stock_actual - stock_comprometido)`.
- `tickets`: la simulación de DT-2 con `cantidad_oc = 0`, proyectada a
  `ticket_id`, `asunto`, `solicitante_*`, `prioridad_nombre`, `fecha_creacion`,
  `cantidad_solicitada`, `cantidad_cubierta` (`solicitado - faltante`) y
  `cantidad_faltante`.

`stock_borrador` se muestra pero **no** se resta: un borrador no compromete
nada. La fila de necesidad se sigue mostrando con el criterio de la 020
(`stock_actual <= stock_minimo` o `demanda_tickets > stock_actual`), aunque el
sugerido quede en 0 por una OC comprometida.

### DT-4 — Preview de cobertura

Nueva operación `POST /api/v1/compras/cobertura/preview`. Cuerpo:

```json
{
  "sede_id": 1,
  "items": [
    { "producto_id": 2, "cantidad_solicitada": 10 }
  ]
}
```

No persiste ni reserva. Errores: sede inexistente/ajena → 404; producto
ajeno/inexistente → 404; producto inactivo o repetido → 409; cuerpo inválido →
422. El proveedor no participa.

Respuesta por producto: `cantidad_simulada`, `demanda_total`, `cubierto_previo`
(`Σ plan_previo + stock_cubierto + entregado`), `asignado`, `faltante` y
`sin_asignar` (`cantidad_simulada - asignado`). Por pedido: `solicitado`,
`cubierto_plan`, `cubierto_stock`, `necesidad`, `asignada`, `faltante` y
`cobertura`. El preview y la emisión comparten `_simular_claves`; con el mismo
estado devuelven las mismas cantidades.

### DT-5 — Emisión: plan congelado y bloqueo por pedidos

`emitir_orden_compra` conserva las validaciones de la 020 y, antes de confirmar:

1. Bloquea con `SELECT ... FOR UPDATE` los pedidos `EnCurso` de la sede que
   demandan los productos de la OC (solo PostgreSQL; SQLite lo ignora). Así dos
   emisiones concurrentes de la misma sede no leen el mismo `plan_previo`.
2. Ejecuta `_simular_claves` con las cantidades de `detalle_orden_compra`.
3. Inserta una fila por pedido con `asignada > 0`, con
   `cantidad_faltante = faltante` y `fecha_asignacion = utcnow()`.
4. Pasa la OC a `Emitida`, asigna `numero_oc` y `fecha_emision`, y confirma en la
   misma transacción. Si algo falla, no queda ninguna fila del plan.
5. Sin pedidos o sin necesidad neta, el plan queda vacío y la emisión es exitosa.

El plan **no se recalcula** al facturar, recepcionar, cancelar, cerrar o anular.
Es una foto del instante de la emisión.

### DT-6 — Recepción: enlace de auditoría

La recepción de la 020 no cambia su lógica ACID. Se agrega:

1. `historial_transicion_ticket.orden_compra_id` (nullable). Solo la fila
   `EnCurso → EnCurso` que escribe el desbloqueo lo llena con la OC recibida.
2. `HistorialTransicionRespuesta` expone `orden_compra_id` y `numero_oc`.
3. El pedido sigue en `EnCurso`; no se sella `fecha_cierre` ni se escribe un
   estado nuevo. La cadena refleja el aumento de `recibido` por lectura.
4. El plan de la OC no se toca.

### DT-7 — Cancelación: plan conservado, cobertura liberada

`cancelar_orden_compra` conserva las filas de `orden_compra_ticket`. La OC
`Cancelada` deja de sumar en `stock_comprometido`, `comprado` y cobertura activa;
el pedido vuelve a ser asignable por una emisión futura. No se replanifica
ninguna otra OC. La respuesta de la OC cancelada sigue mostrando su `plan`.

### DT-8 — DTOs aditivos y resolución de nombres en el servicio

- `NecesidadReabastecimiento` agrega `stock_comprometido`, `stock_borrador` y
  `tickets: list[NecesidadTicketRespuesta]`.
- `CoberturaPreviewSolicitud`, `CoberturaPreviewRespuesta`,
  `CoberturaPreviewProducto` y `CoberturaPreviewTicket`.
- `PlanOrdenCompraRespuesta` y `OrdenCompraRespuesta.plan`.
- `AsignacionTicketRespuesta` y `CadenaProductoTicketRespuesta` en
  `ticket_schema.py`; `TicketDetalleRespuesta` agrega `asignaciones` y
  `cadena_productos`.
- `HistorialTransicionRespuesta` agrega `orden_compra_id` y `numero_oc`.

Los nombres de pedido, producto, prioridad, estado y solicitante se resuelven en
la capa de servicios, no con propiedades del ORM ni con `from_attributes` sobre
columnas que no existen. Se usa `compra_service.orden_a_respuesta(orden)` para
adjuntar el `plan` resuelto a cada OC, en lugar de repetir
`OrdenCompraRespuesta.model_validate` en los endpoints.

### DT-9 — DDL, semilla y versión

**Control (26 → 27 tablas):**

- `historial_transicion_ticket` agrega `orden_compra_id INTEGER`. Como la tabla
  se crea antes que `orden_compra`, la FK se agrega con `ALTER TABLE` después de
  crear `orden_compra`.
- Nueva tabla `control.orden_compra_ticket` con las columnas y restricciones de
  DT-1, creada después de `factura_compra`.
- La tabla queda vacía en la semilla (paridad estructural).

**Cada tenant (23 → 24 tablas):**

- Misma columna y misma FK en `historial_transicion_ticket`.
- Nueva tabla `%1$I.orden_compra_ticket` en la plantilla, después de
  `factura_compra`; el `ALTER TABLE` de la FK del historial va al final de la
  lista de plantillas, cuando `orden_compra` ya existe.
- El chequeo fail-closed del constructor sube de 23 a **24**.

**Semilla (`02_datos_semilla.sql`):**

- `v_version_objetivo` sube de `020.1` a **`021.1`**.
- Agregar `orden_compra_ticket` a la lista de tablas de la guardia, a la lista de
  `resetear_identidades` y al `DELETE` de la Fase 3, **antes** de
  `detalle_orden_compra` (por la FK).
- No se siembran planes: la tabla nace vacía en control y en los tenants.
- Actualizar los comentarios de conteo 26/23 → 27/24.

**Config:** `VERSION_ESQUEMA_OBJETIVO = "021.1"` en
`backend/app/core/config.py`.

### DT-10 — Contrato: 73 operaciones, sin capacidad nueva

La única operación nueva es
`POST /api/v1/compras/cobertura/preview` (matriz **72 → 73**), autorizada solo
al Administrador y gateada por la capacidad `compras` ya existente. No se agrega
una octava capacidad. Las operaciones existentes conservan sus roles.

Tests que hoy fijan 72 y deben subir a 73 al cierre:

- `backend/tests/api/test_compras_endpoints_020.py`
- `backend/tests/api/test_ciclo_vida_autorizacion_014.py`
- `backend/tests/api/test_detalle_producto_019.py`
- `backend/tests/api/test_filtros_inventario_018.py`

### DT-11 — Helper de etiquetas y renombrado visible

`frontend/src/app/shared/utils/etiqueta-estado.ts` centraliza:

```
EnCurso    → En Curso
EnRevision → En Revisión
```

El resto devuelve el nombre canónico. Se aplica en:

- Tablero: `ColumnaKanban` agrega `etiqueta`; el encabezado usa `columna.etiqueta`.
- Modal de alta: `nombreEstadoInicial`.
- Detalle: badge `etiquetaEstado`.
- Historial: `filasHistorial` aplica el helper a origen y destino.
- Listas nuevas de la 021 (necesidades, plan de OC y asignaciones).

El renombrado de copia visible no toca rutas, API, tablas, columnas, permisos,
capacidades ni identificadores. Los mensajes canónicos del backend se conservan.
El menú de compras queda en el orden **Compras**, **Órdenes de Compra**,
**Recepción de Compras**.

### DT-12 — Vistas de la 021

- **Necesidades:** columnas nuevas `Comprometido` y `Borrador`; una fila
  secundaria por necesidad con los pedidos que componen la demanda (Ticket,
  Asunto, Solicitante, Prioridad, Solicitado, Cubierto, Faltante). Nota visible:
  «Comprometido = OC emitidas/facturadas; Borrador no descuenta el sugerido».
- **Órdenes de compra:** botón «Ver pedidos» por fila que expande un panel con
  el `plan` (pedido, solicitante, producto, asignado, faltante). Una OC sin plan
  muestra «Sin pedidos cubiertos: compra para stock mínimo».
- **Detalle del pedido:** dos tablas nuevas, «Cobertura por producto»
  (Solicitado, Comprado, Recibido, Entregado, Faltante) y «Órdenes de compra que
  cubren el pedido» (OC, estado, producto, asignado, faltante, fecha). Las OC
  canceladas se marcan y no se presentan como cobertura activa.
- **Interfaces y servicio:** `compra.interface.ts`, `index.ts` y
  `ComprasService.previsualizarCobertura()`.

### DT-13 — Estrategia de pruebas

**Backend (SQLite en memoria):**

- Algoritmo puro: prioridad/FIFO, parcial, stock parcial, plan previo, OC
  recibida no se resta, cancelada no cubre, pedido de otra sede excluido,
  pedido sin sede excluido, estados no `EnCurso` excluidos.
- Necesidades: comprometido/borrador/sugerido neto, tickets anidados, filtro de
  sede inválido → `[]`.
- Preview: 200, idempotente, no crea filas ni toca stock, errores 404/409/422,
  coincidencia con el plan emitido.
- Emisión: persiste el plan, una fila por pedido/producto con asignada > 0,
  faltante correcto, sin demanda → plan vacío, segunda emisión → 409.
- Cancelación: conserva el plan, libera cobertura, no replanifica.
- Recepción: historial con `orden_compra_id` solo en la fila de desbloqueo;
  historial expone `numero_oc`; plan intacto.
- Detalle del pedido: asignaciones (incluidas canceladas) y cadena por producto;
  pedido terminal con faltante 0; `stock_disponible` conservado.
- Autorización: 403 para Solicitante, Bodeguero y Superadmin en el preview; 403
  con capacidad `compras` apagada; 200 para Administrador; matriz y OpenAPI 73.

**Backend gated (PostgreSQL 16):**

- Conteos 27/24, versión `021.1`, tabla e índices presentes.
- FK compuesta rechaza OC/pedido/producto de otra institución y producto fuera
  del detalle de la OC.
- `UNIQUE (orden_compra_id, ticket_id, producto_id)` rechaza duplicados.
- Dos emisiones concurrentes de la misma sede no asignan dos veces el mismo
  tramo (bloqueo `FOR UPDATE`); el stock no se toca.
- El `ALTER TABLE` del historial y la tabla nueva sobreviven a `down -v` + `up -d`.

**Frontend (ng test — Edge Headless):**

- Helper `etiquetaEstado`: `EnCurso` → «En Curso», `EnRevision` → «En Revisión»,
  resto igual, nulos y espacios.
- Tablero: encabezados con etiqueta visible y lógica por nombre canónico.
- Detalle: cadena y asignaciones renderizadas; OC cancelada marcada; faltante 0
  en terminal; estado legible.
- Necesidades: columnas nuevas, subfila de pedidos, sugerido 0 → «Cubierto».
- Órdenes: panel de plan expandible y vacío informativo.
- Copia visible: «Pedidos», «Estados de pedidos», «Compras», «Pedidos Activos»,
  títulos de pestaña y capacidad «Pedidos»; sin «ticket» en la copia visible.
- `ng build` sin errores de presupuesto.

### DT-14 — Orden de implementación y riesgos

1. **T0** justifica la 021 en `stack.md` (22 entidades, 27/24, `021.1`, matriz
   73, tabla y columna nuevas, sin capacidad nueva, renombrado visible).
2. **T1** DDL y semilla; `down -v` + `up -d` antes de seguir.
3. **T2** modelos; **T3** schemas.
4. **T4** algoritmo y necesidades; **T5** preview; **T6** emisión; **T7**
   recepción/historial; **T8** detalle del pedido.
5. **T9** endpoints, permisos y capacidad; `/openapi.json`.
6. **T10** helper de etiquetas y renombrado; **T11** vistas de la 021.
7. **T12** cierre: suites, gated, build, 4200, 8080 reconstruido, grep de
   coherencia y actualización de `AGENTS.md`/`MEMORY.md`.

**Riesgos principales:**

- **Orden del DDL:** `historial_transicion_ticket` se crea antes que
  `orden_compra`; la FK debe ir en un `ALTER TABLE` posterior. En la plantilla
  tenant, el `ALTER` va al final del arreglo de plantillas.
- **Borrado de la semilla:** `orden_compra_ticket` debe borrarse antes de
  `detalle_orden_compra`, `ticket` y `producto`; si no, la FK bloquea la Fase 3.
- **Doble conteo:** no restar como `plan_previo` las OC `Recibida` (ya están en
  stock) ni sumar los faltantes históricos de varias OC. La cobertura viva se
  calcula con asignaciones activas.
- **Concurrencia:** sin el bloqueo de pedidos, dos emisiones simultáneas pueden
  asignar el mismo tramo. El `FOR UPDATE` es de la emisión, no del preview.
- **SQLite:** no valida esquemas, FKs compuestas ni concurrencia; esos AC se
  prueban en el gated de PostgreSQL 16.
- **Frontend:** el renombrado es solo de copia; no tocar rutas, claves de
  permisos ni el valor persistido `tickets` de la capacidad.
- **Presupuesto de build:** las tablas nuevas no deben introducir CSS quemado;
  solo Tailwind.

---

## 2. Estructura de Archivos por Capa

### Backend

```
backend/app/
├── models/
│   ├── compra.py                 [MODIFICA] — OrdenCompraTicket + relación plan
│   ├── ticket.py                 [MODIFICA] — orden_compra_id en historial + relación
│   └── __init__.py               [MODIFICA] — exporta OrdenCompraTicket
├── schemas/
│   ├── compra_schema.py          [MODIFICA] — necesidades, preview y plan
│   ├── ticket_schema.py          [MODIFICA] — asignaciones, cadena e historial
├── services/
│   ├── compra_service.py         [MODIFICA] — simulación, preview, emisión, recepción
│   └── ticket_service.py         [MODIFICA] — asignaciones y cadena en el detalle
├── api/v1/endpoints/
│   └── compras.py                [MODIFICA] — POST /compras/cobertura/preview
├── core/
│   ├── permisos.py               [MODIFICA] — 72 → 73
│   ├── capacidades.py            [MODIFICA] — preview → compras
│   └── config.py                 [MODIFICA] — 021.1
```

### Database

```
database/
├── 01_esquema.sql               [MODIFICA] — 27 tablas en control y 24 por tenant
└── 02_datos_semilla.sql         [MODIFICA] — 021.1, guardias y borrado
```

### Frontend

```
frontend/src/app/
├── shared/
│   ├── utils/etiqueta-estado.ts [NUEVO]
│   └── interfaces/
│       ├── compra.interface.ts  [MODIFICA]
│       └── index.ts             [MODIFICA] — detalle del pedido
├── features/compras/
│   ├── services/compras.service.ts [MODIFICA] — preview
│   ├── necesidades/             [MODIFICA] — pedidos y comprometido
│   └── lista-ordenes/           [MODIFICA] — plan expandible
├── features/tickets/
│   ├── tickets.component.*      [MODIFICA] — etiqueta y copia «Pedidos»
│   ├── ticket-detalle.component.* [MODIFICA] — cadena y asignaciones
│   └── tickets.routes.ts        [MODIFICA] — títulos
├── features/dashboard/          [MODIFICA] — «Pedidos Activos»
├── features/administracion/     [MODIFICA] — copia «pedidos»
├── features/compras/recepcion-bodega/ [MODIFICA] — copia «pedidos»
├── features/control/capacidades.component.ts [MODIFICA] — «Pedidos»
└── app.component.html            [MODIFICA] — menú y orden
```

---

## 3. Endpoints REST

| Método | Ruta | Rol | AC |
|---|---|---|---|
| `POST` | `/api/v1/compras/cobertura/preview` | Administrador | AC-2, AC-10, AC-12 |
| `GET` | `/api/v1/compras/necesidades` | Administrador | AC-1 (aditivo) |
| `GET` | `/api/v1/compras/ordenes` | Administrador, Bodeguero | AC-4 (aditivo) |
| `GET` | `/api/v1/tickets/{ticket_id}` | Solicitante, Administrador, Bodeguero | AC-5 (aditivo) |
| `GET` | `/api/v1/tickets/{ticket_id}/historial` | Solicitante, Administrador, Bodeguero | AC-6 (aditivo) |
| `POST` | `/api/v1/compras/ordenes/{orden_id}/emitir` | Administrador | AC-3 (plan) |
| `POST` | `/api/v1/compras/ordenes/{orden_id}/recepcion` | Bodeguero | AC-6 (historial) |
| `POST` | `/api/v1/compras/ordenes/{orden_id}/cancelar` | Administrador | AC-7 (plan conservado) |

**Precedencia de errores:** 401 → 403 (matriz) → 403 (capacidad `compras`) →
409 (regla/estado) → 404 (recurso inexistente/ajeno) → 422 (cuerpo). El preview
añade 409 para producto inactivo/repetido y 404 para sede/producto ajeno.

**Respuestas:** todas las rutas declaran `response_model`, `status_code`
explícito y documentación OpenAPI. La operación nueva responde `200`.

---

## 4. Algoritmo de Cobertura (pseudocódigo)

```
def simular(institucion_id, claves, cantidades_oc, bloquear):
    estado_en_curso = buscar_estado("EnCurso")
    if not estado_en_curso: return {clave: []}

    if bloquear:
        SELECT ticket_id ... FOR UPDATE   # solo PostgreSQL

    tickets = SELECT Ticket
              JOIN DetalleTicket
              WHERE institucion_id, estado_id = EnCurso,
                    (sede_id, producto_id) IN claves
              ORDER BY prioridad_id, fecha_creacion, ticket_id

    plan_previo = SELECT ticket_id, producto_id, SUM(cantidad_asignada)
                  JOIN orden_compra
                  WHERE estado IN ("Emitida", "Facturada")
                  GROUP BY ticket_id, producto_id

    stock = SELECT sede_id, producto_id, stock_actual FROM stock_sede

    por_clave = agrupar(tickets, claves)  # solicitado, entregado por producto

    resultado = {}
    for clave in claves:
        restante_stock = stock.get(clave, 0)
        restante_oc = cantidades_oc.get(clave, 0)
        filas = []
        for ticket in por_clave[clave]:   # orden prioridad/FIFO
            plan = plan_previo.get((ticket.ticket_id, clave.producto), 0)
            base = max(0, solicitado - plan - entregado)
            cubierto = min(base, restante_stock)
            restante_stock -= cubierto
            necesidad = base - cubierto
            asignada = min(necesidad, restante_oc)
            restante_oc -= asignada
            faltante = necesidad - asignada
            filas.append(Simulacion(...))
        resultado[clave] = filas
    return resultado
```

La emisión persiste `asignada > 0`; el preview devuelve todas las filas. La
necesidad usa `cantidades_oc = 0`. La cadena del pedido usa `cantidades_oc = 0`
y busca la fila del pedido.

---

## 5. Estrategia de Tests

### Backend (pytest — SQLite en memoria)

`backend/tests/api/test_cobertura_021.py`:

- **AC-1:** necesidades con `stock_comprometido`, `stock_borrador`, sugerido
  neto, tickets anidados y filtro de sede inválido.
- **AC-2:** preview 200, idempotente, sin filas ni stock, errores 404/409/422.
- **AC-3:** emisión persiste el plan, cantidades y faltantes correctos, plan
  vacío sin demanda, segunda emisión 409.
- **AC-4:** `GET /compras/ordenes` devuelve `plan` en todos los estados.
- **AC-5:** detalle del pedido con asignaciones y cadena; pedido terminal;
  `stock_disponible` intacto.
- **AC-6:** recepción enlaza el historial y conserva el plan.
- **AC-7:** cancelación conserva el plan y libera la cobertura.
- **AC-8:** pedido de otra sede o sin sede no participa.
- **AC-9:** cobertura total/parcial/sin cobertura y faltante.
- **AC-10:** 403 por rol y por capacidad; matriz/OpenAPI 73.
- **AC-11/AC-12:** FK compuestas (gated), preview y emisión coinciden.

`backend/tests/api/test_tickets.py` y `test_compras.py` se amplían con los
campos aditivos sin romper los contratos existentes.

### Backend gated (PostgreSQL 16)

`backend/tests/test_cobertura_postgres_021.py`:

- Conteos 27/24, versión `021.1`, tabla e índices.
- FK compuestas y `UNIQUE` del plan.
- Emisiones concurrentes sin doble asignación.
- `ALTER TABLE` del historial y FK a `orden_compra`.
- Semilla: tabla vacía en control y en cada tenant.

### Frontend (ng test — Edge Headless)

- `etiqueta-estado.spec.ts`: mapa y nulos.
- `tickets.component.spec.ts`: encabezados «En Curso»/«En Revisión» y lógica por
  nombre canónico.
- `ticket-detalle.component.spec.ts`: cadena, asignaciones, OC cancelada,
  terminal con faltante 0.
- `necesidades.component.spec.ts`: columnas nuevas, subfila de pedidos.
- `lista-ordenes.component.spec.ts`: panel de plan expandible y vacío.
- `compras.service.spec.ts`: preview.
- `dashboard.component.spec.ts`: «Pedidos Activos».
- `capacidades.component.spec.ts`: etiqueta «Pedidos».
- `ng build` sin errores de presupuesto.

---

## 6. Orden de Implementación y Riesgos

1. **T0** `stack.md`: justificación de la 021.
2. **T1** DDL/semilla/config; arranque limpio 27/24/`021.1`.
3. **T2** modelos; **T3** schemas.
4. **T4** simulación y necesidades; **T5** preview.
5. **T6** emisión con plan; **T7** recepción e historial; **T8** detalle.
6. **T9** endpoint, permisos y capacidad; OpenAPI 73.
7. **T10** helper de etiquetas y renombrado visible.
8. **T11** vistas de necesidades, OC y detalle.
9. **T12** cierre: suites, gated, build, 4200, 8080 reconstruido, `grep` de
   coherencia y actualización de `AGENTS.md`/`MEMORY.md`.

**Riesgos principales:** orden del DDL del historial; borrado de la semilla;
doble conteo stock/plan; concurrencia de emisión; límites de SQLite; y que el
renombrado visible toque por accidente rutas o valores canónicos.
