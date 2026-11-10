# Feature 021: Cobertura automática de tickets por órdenes de compra

**Estado:** propuesta (pendiente de aprobación)  
**Release:** 2.0  
**Tipo:** Trazabilidad de cobertura, plan de compra y lectura de pedidos

> **Convención de nombres de esta spec.** La entidad canónica sigue siendo
> `ticket` (`/tickets`, tablas, permisos y DTO del backend). En la copia visible
> de la SPA se llama **pedido**. Una **necesidad** es la fila `(sede, producto)`
> de `GET /compras/necesidades`; el **plan** son las filas de
> `orden_compra_ticket`; la **cobertura** es la suma de asignaciones activas.

---

## 1. Problema

La Feature 020 cerró el ciclo *Procure-to-Stock-to-Desk*, pero la lectura del
reabastecimiento quedó en el agregado y perdió el vínculo con el pedido que
origina la compra:

1. **La necesidad oculta sus pedidos.** `GET /compras/necesidades` consolida por
   `(sede, producto)` y entrega una única cifra de demanda. El Administrador no
   puede ver qué pedidos concretos componen esa demanda, cuáles ya están
   cubiertos, cuáles son prioritarios ni cuánto falta por cubrir en cada uno.
2. **No existe vínculo entre el pedido y la OC.** Al emitir una orden de compra,
   el sistema no registra qué pedidos pretende cubrir ni en qué cantidades. El
   pedido no queda marcado como asignado a una OC y la OC no muestra los pedidos
   que cubre.
3. **La recepción solo enciende un booleano.** Tras la recepción, el pedido
   expone `stock_disponible`, pero no refleja cuánto se compró, cuánto se recibió,
   cuánto se entregó ni cuánto sigue faltando por producto. El Administrador no
   puede auditar el efecto real de la compra sobre cada pedido.
4. **No hay evidencia del plan.** La OC guarda las cantidades compradas
   (`detalle_orden_compra`), pero no la intención de a qué pedido iba destinada
   cada unidad. Sin ese plan no existe una comparación *planificado vs real*.
5. **La copia visible es incoherente.** El menú dice «Tickets» y «Necesidades»,
   la vista se titula «Sistema de Tickets» y los estados aparecen pegados
   (`EnCurso`, `EnRevision`). El usuario pidió leer «Pedidos», «Compras» y
   estados con palabras separadas.

---

## 2. Objetivo

1. Ver, dentro de cada necesidad `(sede, producto)`, los pedidos `EnCurso` que la
   componen, con su demanda, su cobertura y su faltante.
2. Incorporar a la necesidad el stock ya comprometido por OC `Emitida` o
   `Facturada` y el stock en borradores, y descontar el comprometido del
   sugerido.
3. Permitir una previsualización de la cobertura automática antes de emitir.
4. Al emitir una OC, asignar automáticamente sus cantidades a los pedidos
   `EnCurso` de su sede y persistir el plan en `orden_compra_ticket`.
5. Mostrar en la OC los pedidos cubiertos y, en el pedido, las OC que lo cubren
   y la cadena por producto `Solicitado → Comprado → Recibido → Entregado →
   Faltante`.
6. Mantener `Cerrado` como estado de despacho: la recepción de la OC deja el
   pedido en `EnCurso` con lo recibido y `stock_disponible`; el cierre ocurre solo
   al despachar.
7. Renombrar la copia visible a «Pedidos», «Estados de pedidos» y «Compras», y
   separar las palabras de los estados.

---

## 3. Actores del Sistema

- **Administrador Institucional:** consulta necesidades con sus pedidos, simula
  la cobertura, emite OC, ve el plan y audita el avance comprado/recibido.
- **Bodeguero / Encargado de Suministros:** recepciona la OC facturada de su sede
  y ve qué pedidos se desbloquearon y qué plan cubría la orden.
- **Solicitante (Funcionario):** en el detalle de su pedido ve las OC que lo
  cubren, lo comprado, lo recibido, lo entregado y el faltante.
- **Superadmin:** sin cambios. No opera compras de un tenant ni ve sus pedidos;
  conserva solo el catálogo global de proveedores de la Feature 020.

---

## 4. Alcance

### 4.1 Dentro de alcance

- **Necesidades enriquecidas:** `GET /compras/necesidades` agrega
  `stock_comprometido` (OC `Emitida` + `Facturada`), `stock_borrador` (OC
  `Borrador`) y una lista `tickets` con los pedidos `EnCurso` que demandan ese
  producto en esa sede, cada uno con solicitado, cubierto y faltante.
- **Sugerido neto:** `sugerido = max(0, stock_minimo + demanda_tickets -
  stock_actual - stock_comprometido)`. Esta fórmula **enmienda AC-1 y §4.1 de la
  Feature 020**; el resto de la 020 sigue vigente.
- **Preview de cobertura:** nueva operación
  `POST /compras/cobertura/preview`, de solo lectura, que simula el plan de una
  compra hipotética sin persistir ni reservar stock.
- **Asignación automática al emitir:** al pasar una OC de `Borrador` a `Emitida`,
  el servicio calcula el plan y lo persiste en `orden_compra_ticket` dentro de la
  misma transacción de la emisión.
- **Plan visible en la OC:** `GET /compras/ordenes` agrega `plan` a cada OC, con
  los pedidos cubiertos, el producto, `cantidad_asignada` y `cantidad_faltante`.
- **Pedido enriquecido:** `GET /tickets/{ticket_id}` agrega `asignaciones` (OC
  que cubren el pedido) y `cadena_productos` (solicitado, comprado, recibido,
  entregado y faltante por producto).
- **Auditoría de recepción:** la fila `EnCurso → EnCurso` que escribe la
  recepción en `historial_transicion_ticket` porta el `orden_compra_id` de la OC
  recibida; el resto de las filas conserva `NULL`.
- **Cancelación con plan conservado:** una OC cancelada conserva sus filas de
  plan para auditoría, pero deja de contar en la cobertura activa; el pedido
  vuelve a ser asignable por una emisión futura.
- **Una OC, una sede:** el plan solo considera pedidos de la sede de la OC. No
  hay traspasos entre sedes.
- **Cambios visuales de lectura:** renombrado a «Pedidos», opción «Compras»,
  título «Estados de pedidos» y estados con palabras separadas.

### 4.2 Fuera de alcance

- Asignación manual de pedidos a una OC: el camino queda como mejora futura; en
  esta versión la asignación es automática y no editable.
- Traspasos de cantidades entre sedes o compras «flotantes» sin sede.
- Reserva de stock: el plan es una intención, no descuenta ni bloquea saldo.
- Un nuevo estado de pedido o un cambio en el ciclo de vida de la Feature 013.
  `Cerrado` sigue siendo el estado de despacho.
- Modificar `calcular_cobertura_tickets` ni `stock_disponible` de la Feature 020:
  la simulación de necesidad neta parcial de esta feature es una función aparte.
- Replanificación automática al cancelar una OC, cerrar un pedido o recibir otra
  compra. El plan es una foto congelada al emitir; los cambios posteriores se
  leen, no se reescriben.
- Recepciones parciales de OC (siguen fuera de alcance desde la 020).
- Notificaciones push, correo o una tabla de notificaciones.
- Renombrar rutas, endpoints, tablas, columnas, permisos, capacidades o
  identificadores canónicos de `ticket`. El renombrado es solo de copia visible.
- Interfaz dedicada del Superadmin para compras o pedidos.
- Migraciones: la base se reconstruye con `down -v` + `up -d` (AGENTS §8.8).

---

## 5. Decisiones de Diseño de Negocio

### D-1 — El pedido es la unidad de cobertura, no el agregado

La necesidad sigue existiendo por `(sede, producto)` porque es la unidad de
decisión de compra, pero ahora anida los pedidos que la componen. El plan de la
OC se expresa por `(pedido, producto)`, no por producto agregado.

**Por qué:** el Administrador necesita saber a quién beneficia la compra y el
Solicitante necesita ver el efecto sobre su pedido. Una cifra agregada no
permite ninguna de las dos cosas.

### D-2 — Asignación automática, congelada al emitir

El plan se calcula una sola vez, al emitir la OC, y no se modifica después. No
hay selección manual, no hay `modo_asignacion` y no se persiste un plan en
`Borrador`.

**Por qué:** la emisión es el acto que compromete la compra. Calcular el plan en
ese instante lo hace determinista y auditable; un plan editable o un borrador
persistido introducirían estados intermedios que nadie reconcilia.

### D-3 — Una fila por `(OC, pedido, producto)`

`orden_compra_ticket` guarda `cantidad_asignada` (> 0) y `cantidad_faltante`
(>= 0). La clave única es `(orden_compra_id, ticket_id, producto_id)`. Varias OC
pueden cubrir el mismo pedido/producto, cada una con su fila.

**Por qué:** una sola tabla permite la cobertura parcial y la trazabilidad de
qué OC cubrió qué. La fila no es un detalle de la OC: es el puente entre la
compra y el pedido, y por eso no se duplica en dos tablas.

### D-4 — Necesidad neta parcial: stock, planes previos y compra nueva

El plan se calcula por producto y en orden de prioridad/FIFO
(`prioridad_id` ascendente, `fecha_creacion`, `ticket_id`). Para cada pedido:

1. `plan_previo` = suma de `cantidad_asignada` de OC **`Emitida` + `Facturada`**
   para ese `(pedido, producto)`. Las OC `Recibida` **no** se restan aquí porque
   su cantidad ya está en `stock_actual`; las `Cancelada` se excluyen y los
   `Borrador` no tienen plan.
2. `necesidad_para_stock = max(0, solicitado - plan_previo - entregado)`.
   En un pedido `EnCurso` el entregado es 0 en la práctica (el despacho es
   total), pero la fórmula lo contempla para no comprar unidades ya entregadas.
3. El stock físico de la sede se reparte parcialmente entre los pedidos en ese
   mismo orden: `stock_cubierto` y `necesidad_neta = necesidad_para_stock -
   stock_cubierto`.
4. La cantidad de la nueva OC se reparte parcialmente sobre las
   `necesidad_neta`: `asignada` y `faltante = necesidad_neta - asignada`.

No se reserva stock: el stock es una simulación de lectura y la asignación es
una intención. La simulación es **parcial** (puede cubrir una parte de un
pedido), a diferencia de la asignación todo-o-nada de
`calcular_cobertura_tickets`, que no se toca.

**Por qué:** si el stock ya cubre parte del pedido, comprar esa parte sería
duplicar. Restar primero los planes pendientes evita que dos OC cubran el mismo
tramo; no restar las OC recibidas evita descontar dos veces una mercadería que
ya está en el saldo.

### D-5 — `stock_comprometido` y `stock_borrador` no son lo mismo

- `stock_comprometido` = suma de `detalle_orden_compra.cantidad_solicitada` de
  OC `Emitida` + `Facturada` para la sede/producto. Es compra comprometida
  completa, aunque parte no esté asignada a un pedido (compra para el mínimo).
- `stock_borrador` = la misma suma para OC `Borrador`. Se muestra aparte y **no**
  se resta del sugerido: un borrador aún no compromete nada.
- El plan (`cantidad_asignada`) es solo la parte de la compra earmarcada a
  pedidos. Por eso `stock_comprometido` puede ser mayor que la suma del plan; la
  diferencia es reposición de mínimo, no cobertura de un pedido.

**Por qué:** el sugerido debe evitar comprar dos veces la misma reposición, pero
no debe confundir una intención de borrador con una compra comprometida.

### D-6 — `Cerrado` sigue siendo el despacho; la recepción no cierra

La recepción de la OC incrementa stock y deja el pedido en `EnCurso`, con
`stock_disponible` y los campos de recibido actualizados. El pedido se cierra
solo cuando el Bodeguero lo despacha, porque el despacho es el único acto que
rebaja el inventario y escribe el movimiento `SALIDA`.

**Por qué:** cerrar al recepcionar dejaría stock incrementado sin la salida
correspondiente. La recepción es una entrada; el cierre es una entrega.

### D-7 — Cadena por producto y definición de «Faltante»

Cada producto del pedido muestra:

| Columna | Definición |
|---|---|
| **Solicitado** | Suma de `detalle_ticket.cantidad_solicitada` del producto. |
| **Comprado** | Suma de `cantidad_asignada` de OC activas (`Emitida` + `Facturada` + `Recibida`). |
| **Recibido** | Suma de `cantidad_asignada` de OC `Recibida` (parte del comprado que ya llegó). |
| **Entregado** | Suma de `detalle_ticket.cantidad_entregada` del producto. |
| **Faltante** | `0` si el pedido es terminal (`Cerrado`/`Anulado`); si no, `max(0, solicitado - comprado_pendiente - stock_cubierto - entregado)`, donde `comprado_pendiente` son las OC `Emitida` + `Facturada` y `stock_cubierto` es la simulación parcial de stock de D-4. |

`Recibido` es informativo: sus unidades ya están en `stock_cubierto` o en
`Entregado`, por eso no se restan otra vez en la fórmula. `Comprado` sí incluye
lo recibido para mostrar la cobertura total de compra.

**Por qué:** la cadena separa la intención (comprado), la llegada física
(recibido) y la entrega (entregado). El faltante es lo que aún falta cubrir con
stock o con una compra futura; no es un estado nuevo ni una columna persistida.

### D-8 — Cancelación: plan conservado, cobertura liberada, sin replanificación

Al cancelar una OC `Borrador` o `Emitida` (regla de la 020), sus filas de
`orden_compra_ticket` se conservan. La cancelada deja de sumar en
`cantidad_cubierta`, `comprado` y `stock_comprometido`; el pedido vuelve a
aparecer como asignable en la necesidad. Una emisión futura puede asignarlo. No
se recalculan automáticamente los planes de otras OC.

**Por qué:** borrar el plan destruiría la evidencia de que la compra existió y
fue cancelada. Replanificar en cascada convertiría una cancelación en una
reescritura silenciosa de planes ajenos.

### D-9 — Una OC pertenece a una sola sede

El plan solo considera pedidos cuyo `ticket.sede_id` coincide con
`orden_compra.sede_id` y cuya institución es la de la OC. Un pedido de otra sede
nunca se asigna, aunque demande el mismo producto. `sede_id` sigue siendo
inmutable después de la emisión (020).

**Por qué:** el stock es descentralizado por sede (Feature 011). Aceptar pedidos
de otra sede obligaría a inventar un traspaso que esta feature no modela.

### D-10 — Preview y emisión comparten el mismo algoritmo

`POST /compras/cobertura/preview` y la emisión usan la misma función
determinista. El preview no persiste ni reserva; la emisión persiste el
resultado. Dado el mismo estado, el preview y el plan emitido coinciden.

**Por qué:** el Administrador debe poder confiar en que lo que ve antes de
emitir es exactamente lo que quedará registrado.

### D-11 — Auditoría del plan y de la recepción

El plan es inmutable después de la emisión: no hay endpoint para editarlo y la
recepción, la cancelación o el cierre del pedido no reescriben sus filas. La
recepción agrega el vínculo `historial_transicion_ticket.orden_compra_id` **solo**
en la fila `EnCurso → EnCurso` que ella misma escribe; las demás filas del
historial lo dejan `NULL`.

**Por qué:** el plan es la evidencia de la intención y el historial es la
evidencia del desbloqueo. Enlazar la recepción con la OC permite reconstruir por
qué se desbloqueó un pedido sin inventar un estado nuevo.

### D-12 — Renombrado visible sin tocar lo canónico

La SPA muestra «pedido(s)», «Compras» y «Estados de pedidos». Las rutas
(`/tickets`, `/compras/necesidades`), la API (`/api/v1/tickets/*`), las tablas,
las columnas, los permisos, las capacidades y los identificadores de código
siguen iguales. Los mensajes canónicos del backend tampoco se renombran: son
parte del contrato de la API.

**Por qué:** el cambio es de lectura para el usuario, no de dominio. Renombrar
la API o la base rompería contratos, tests y datos sin beneficio funcional.

### D-13 — Contrato mínimo: una operación, una entidad, sin capacidad nueva

La feature agrega **una** operación a la matriz (72 → **73**), **una** entidad de
dominio (21 → **22**), una tabla por esquema (`control` 26 → **27**, tenant 23 →
**24**), sube la versión a **`021.1`** y no agrega capacidades: la nueva
operación se gatea con la capacidad `compras` ya existente.

**Por qué:** la cobertura es una lectura/acción de compras, no una función
institucional nueva. El resto de los cambios son campos aditivos en DTO de
lectura y una tabla de puente.

---

## 6. Reglas del Flujo

### 6.1 Necesidades y cobertura

`GET /compras/necesidades` mantiene el alcance y los filtros de la 020: solo
productos y categorías activos, demanda de pedidos `EnCurso` de la sede, y un
`sede_id` inexistente o ajeno devuelve `200` con `[]`. Cada fila
`(sede, producto)` expone:

- `stock_actual`, `stock_minimo`, `demanda_tickets` (suma bruta de
  `cantidad_solicitada` de los pedidos `EnCurso`).
- `stock_comprometido` y `stock_borrador` (D-5).
- `sugerido = max(0, stock_minimo + demanda_tickets - stock_actual -
  stock_comprometido)`.
- `tickets`: los pedidos `EnCurso` de la sede que demandan el producto, en orden
  prioridad/FIFO, cada uno con `ticket_id`, `asunto`, `solicitante`, `prioridad`,
  `fecha_creacion`, `cantidad_solicitada`, `cantidad_cubierta` y
  `cantidad_faltante`.
  - `cantidad_cubierta = cantidad_solicitada - cantidad_faltante`.
  - `cantidad_faltante` es la necesidad neta de D-4 **antes** de una nueva OC:
    `max(0, solicitada - plan_previo - stock_cubierto - entregado)`; en un pedido
    `EnCurso` el entregado es 0 en la práctica (el despacho es total).
  - Los pedidos con demanda 0 no aparecen; los estados distintos de `EnCurso`
    (`Pendiente`, `EnRevision`, `Cerrado`, `Anulado`) quedan fuera.

La lista `tickets` es la composición de la demanda, no el sugerido: la suma de
sus faltantes puede no coincidir con `sugerido` porque el sugerido también
reconstruye el stock mínimo.

### 6.2 Cálculo del plan al emitir

Al emitir una OC `Borrador` con al menos un ítem y productos activos (reglas de
la 020), en la misma transacción:

1. Se validan la sede y los ítems con la misma precedencia de la 020: sede
   inexistente/ajena → 404; producto ajeno → 404; producto inactivo o repetido →
   409; cuerpo inválido → 422.
2. Para cada producto del detalle de la OC, se cargan los pedidos `EnCurso` de
   la sede con ese producto y se ordenan por `prioridad_id` ascendente,
   `fecha_creacion` ascendente y `ticket_id` ascendente.
3. Se aplica D-4 con `cantidad_solicitada` como tope de la OC para ese producto.
4. Por cada pedido con `asignada > 0` se inserta una fila
   `(orden_compra_id, ticket_id, producto_id, institucion_id,
   cantidad_asignada, cantidad_faltante, fecha_asignacion)`.
5. La suma de `cantidad_asignada` por producto nunca supera la
   `cantidad_solicitada` del detalle. La compra que no alcanza a asignarse queda
   como reposición de stock y no genera fila.
6. Si no hay pedidos o no hay necesidad neta, el plan queda vacío y la emisión
   igualmente es exitosa.
7. Si la emisión falla, no se persiste ninguna fila del plan.

El plan no se recalcula al facturar, recepcionar, cancelar, cerrar o anular un
pedido. Es una foto del estado al emitir.

### 6.3 Preview de cobertura

`POST /compras/cobertura/preview` recibe `sede_id` y una lista de
`(producto_id, cantidad_solicitada)`; no recibe proveedor porque el proveedor no
afecta la cobertura. Ejecuta exactamente el algoritmo de 6.2 sin persistir ni
reservar. Devuelve, por producto:

- `cantidad_simulada`, `demanda_total`, `cubierto_previo` (stock + planes
  pendientes), `asignado`, `faltante` y `sin_asignar` (compra que no encontró
  necesidad).
- `tickets`: todos los pedidos que demandan el producto, incluidos los que
  reciben `asignada = 0`, con `solicitado`, `cubierto_plan`, `cubierto_stock`,
  `necesidad`, `asignada`, `faltante` y la etiqueta de cobertura
  (`total`/`parcial`/`sin_cobertura`).

Una segunda llamada con el mismo estado devuelve el mismo resultado. Un
`sede_id` inexistente o ajeno responde `404` (no es un filtro de lista, es una
simulación con una sede concreta); un producto ajeno responde `404`, uno
inactivo o repetido `409`, y un cuerpo inválido `422`.

### 6.4 Plan visible en la OC

`GET /compras/ordenes` agrega `plan` a cada OC. Cada fila incluye
`orden_compra_ticket_id`, `orden_compra_id`, `ticket_id`, `producto_id`,
`cantidad_asignada`, `cantidad_faltante`, `fecha_asignacion`, un resumen del
pedido (`asunto`, `estado_nombre`, `prioridad_nombre`, `solicitante_nombre`,
`fecha_creacion`) y el producto resuelto. Una OC `Borrador` tiene `plan` vacío;
una `Emitida`, `Facturada`, `Recibida` o `Cancelada` conserva su plan para
auditoría.

La vista de OC muestra los pedidos cubiertos, la cantidad asignada y el faltante
que la orden dejó. La comparación *planificado vs real* se lee con el detalle de
la OC (cantidad comprada) y el estado de la OC (recibida o no).

### 6.5 Pedido: asignaciones y cadena por producto

`GET /tickets/{ticket_id}` agrega:

- `asignaciones`: todas las filas del plan del pedido, incluidas las de OC
  canceladas para auditoría, con `orden_compra_id`, `numero_oc`, `estado_orden`,
  `producto_id`, `producto_nombre`, `cantidad_asignada`, `cantidad_faltante` y
  `fecha_asignacion`. La UI marca las canceladas y no las suma a la cobertura
  activa.
- `cadena_productos`: una fila por producto del pedido con `producto_id`,
  `producto_nombre`, `solicitado`, `comprado`, `recibido`, `entregado` y
  `faltante`, según D-7. El orden es el de los detalles del pedido.

El alcance de la lectura no cambia (Features 013 y 017): el Solicitante ve los
suyos; Administrador y Bodeguero, los de su institución; el **Superadmin no
tiene esta lectura** y recibe `403` sin datos. Un pedido inexistente o ajeno
sigue respondiendo `404` idéntico. `stock_disponible` de la 020 se conserva y no
se recalcula con el plan.

### 6.6 Recepción

La recepción conserva el comportamiento ACID de la 020 (stock, movimiento
`ENTRADA`, desbloqueo y aviso). Además:

1. La fila `EnCurso → EnCurso` que se escribe por cada pedido desbloqueado porta
   `orden_compra_id = orden.orden_compra_id`.
2. Las filas del historial que no son de recepción mantienen
   `orden_compra_id = NULL`.
3. `GET /tickets/{ticket_id}/historial` expone `orden_compra_id` y `numero_oc`
   para que la UI muestre «Desbloqueo por OC-…».
4. El pedido sigue en `EnCurso`; `stock_disponible` y la cadena de recibido se
   actualizan por lectura, no por una escritura de estado.
5. El plan de la OC no se modifica.

Si el pedido ya estaba `Cerrado` o `Anulado`, la recepción no lo desbloquea ni
le escribe historial (regla de la 020), pero el plan de la OC permanece.

### 6.7 Cancelación

La cancelación de la 020 se mantiene: solo `Borrador` o `Emitida`, motivo no
vacío, actor y fecha. Si la OC tenía plan:

- Las filas de `orden_compra_ticket` se conservan.
- La OC cancelada deja de sumar en `cantidad_cubierta`, `comprado` y
  `stock_comprometido`.
- El pedido vuelve a ser asignable por una emisión futura; no se replanifica
  automáticamente ninguna otra OC.
- La respuesta de la OC cancelada sigue mostrando su `plan` para auditoría.

### 6.8 Copia visible

- **V-1:** el menú «Tickets» pasa a «Pedidos»; la vista «Sistema de Tickets» a
  «Estados de pedidos»; el botón «+ Crear Ticket» a «+ Crear pedido»; el modal,
  el detalle, el dashboard, la recepción y los textos de departamentos usan
  «pedido(s)» en lugar de «ticket(s)». Los títulos de pestaña pasan a «Pedidos |
  CompuStock» y «Detalle del pedido | CompuStock».
- **V-2:** la opción «Necesidades» pasa a «Compras» y el orden del menú es
  «Compras», «Órdenes de Compra», «Recepción de Compras». La ruta
  `/compras/necesidades` y el endpoint no cambian.
- **V-3:** los estados se muestran con palabras separadas: `EnCurso` → «En
  Curso», `EnRevision` → «En Revisión»; el resto se muestra igual. El helper
  `frontend/src/app/shared/utils/etiqueta-estado.ts` centraliza el mapa y se
  aplica al tablero, al detalle, al historial, al estado inicial y a las nuevas
  listas de la 021. `ColumnaKanban` conserva `estado` canónico y agrega
  `etiqueta`.
- **V-4:** en Control de instituciones, la capacidad `tickets` se rotula
  «Pedidos»; el valor persistido y la API siguen siendo `tickets`.

---

## 7. Criterios de Aceptación (AC)

### AC-1 — Necesidades con pedidos, comprometido y sugerido neto

- **DADO QUE** existen productos activos con stock crítico o pedidos `EnCurso`
  en una sede,
- **CUANDO** el Administrador consulta `GET /compras/necesidades` (con o sin
  `sede_id`),
- **ENTONCES** cada fila `(sede, producto)` incluye `stock_actual`,
  `stock_minimo`, `demanda_tickets`, `stock_comprometido`, `stock_borrador`,
  `sugerido` y `tickets`.
  - `stock_comprometido` suma las cantidades de `detalle_orden_compra` de OC
    `Emitida` + `Facturada` de la sede/producto.
  - `stock_borrador` suma las de OC `Borrador`.
  - `sugerido = max(0, stock_minimo + demanda_tickets - stock_actual -
    stock_comprometido)`.
  - `tickets` lista solo pedidos `EnCurso` de la sede que demandan el producto,
    con `cantidad_solicitada`, `cantidad_cubierta` y `cantidad_faltante`.
  - Un `sede_id` inexistente o ajeno devuelve `200` con `[]`; un pedido
    `Pendiente`, `EnRevision`, `Cerrado` o `Anulado` no aparece; un pedido sin
    sede no participa.

### AC-2 — Preview de cobertura automática

- **DADO QUE** el Administrador prepara una compra con una sede y al menos un
  producto con cantidad mayor a cero,
- **CUANDO** invoca `POST /compras/cobertura/preview`,
- **ENTONCES** recibe `200` con la simulación por producto y por pedido, sin que
  se cree ninguna fila en `orden_compra_ticket` ni se modifique stock.
  - La simulación usa prioridad/FIFO, necesidad neta parcial y el mismo algoritmo
    de la emisión.
  - Devuelve `cantidad_simulada`, `demanda_total`, `cubierto_previo`, `asignado`,
    `faltante` y `sin_asignar` por producto, y `solicitado`, `cubierto_plan`,
    `cubierto_stock`, `necesidad`, `asignada`, `faltante` y `cobertura` por
    pedido.
  - Dos llamadas con el mismo estado devuelven el mismo resultado.
  - Sede inexistente/ajena → `404`; producto ajeno → `404`; producto inactivo o
    repetido → `409`; cuerpo inválido → `422`.

### AC-3 — Asignación automática y persistencia del plan al emitir

- **DADO QUE** una OC está en `Borrador` con al menos un ítem y productos
  activos,
- **CUANDO** el Administrador la emite con `POST
  /compras/ordenes/{id}/emitir`,
- **ENTONCES** en la misma transacción la OC pasa a `Emitida` y se persiste el
  plan en `orden_compra_ticket`:
  - Solo participan pedidos `EnCurso` de la sede de la OC.
  - Se aplica prioridad/FIFO y necesidad neta parcial de D-4.
  - Cada fila tiene `cantidad_asignada > 0`, `cantidad_faltante >= 0`,
    `institucion_id` y `fecha_asignacion`.
  - La suma asignada por producto no supera la cantidad del detalle de la OC.
  - Si no hay demanda, el plan queda vacío y la emisión es exitosa.
  - Si la emisión falla, no queda ninguna fila del plan.
  - Una segunda emisión responde `409` (regla de la 020).

### AC-4 — La OC muestra los pedidos cubiertos

- **DADO QUE** una OC fue emitida,
- **CUANDO** el Administrador consulta `GET /compras/ordenes`,
- **ENTONCES** la OC incluye `plan` con sus filas `(pedido, producto,
  cantidad_asignada, cantidad_faltante)` y el resumen del pedido y del producto.
  - Una OC `Borrador` devuelve `plan` vacío.
  - Una OC `Emitida`, `Facturada`, `Recibida` o `Cancelada` conserva y devuelve
    su plan.
  - La vista de OC permite ver qué pedidos cubre, cuánto asigna y cuánto deja
    faltante.

### AC-5 — El pedido muestra asignaciones y cadena por producto

- **DADO QUE** un pedido existe y tiene o no plan,
- **CUANDO** un actor autorizado consulta `GET /tickets/{ticket_id}`,
- **ENTONCES** la respuesta agrega:
  - `asignaciones` con todas las filas del plan del pedido (incluidas las OC
    canceladas, identificadas por `estado_orden`).
  - `cadena_productos` con `solicitado`, `comprado`, `recibido`, `entregado` y
    `faltante` por producto, según D-7.
  - Un pedido sin asignaciones devuelve listas vacías y conserva su cadena.
  - El alcance por rol y el `404` de pedido inexistente/ajeno no cambian.
  - `stock_disponible` se conserva como propiedad de la 020.

### AC-6 — Recepción: enlace de auditoría y actualización de recibido

- **DADO QUE** una OC `Facturada` de la sede del Bodeguero se recepciona,
- **CUANDO** se completa `POST /compras/ordenes/{id}/recepcion`,
- **ENTONCES** además del comportamiento de la 020:
  - Cada fila `EnCurso → EnCurso` escrita por el desbloqueo porta
    `orden_compra_id` de la OC recibida.
  - Las demás filas del historial conservan `orden_compra_id = NULL`.
  - `GET /tickets/{ticket_id}/historial` expone `orden_compra_id` y `numero_oc`
    en la fila de desbloqueo.
  - La cadena del pedido refleja el aumento de `recibido` para los productos de
    la OC.
  - El pedido sigue en `EnCurso`; no se asigna `fecha_cierre` ni se cambia a
    `Cerrado`.
  - El plan de la OC no se modifica.

### AC-7 — Cancelación: plan conservado y cobertura liberada

- **DADO QUE** una OC `Borrador` o `Emitida` con plan se cancela con motivo,
- **CUANDO** se completa `POST /compras/ordenes/{id}/cancelar`,
- **ENTONCES** la OC pasa a `Cancelada` y:
  - Sus filas de `orden_compra_ticket` se conservan y se devuelven en `plan`.
  - Deja de sumar en `cantidad_cubierta`, `comprado` y `stock_comprometido`.
  - El pedido vuelve a ser asignable por una emisión futura.
  - No se replanifican automáticamente otras OC.
  - Una OC `Facturada`, `Recibida` o ya `Cancelada` sigue respondiendo `409`
    (regla de la 020).

### AC-8 — Una OC, una sede; sin traspasos

- **DADO QUE** una OC tiene `sede_id = S`,
- **CUANDO** se calcula su preview o su plan,
- **ENTONCES** solo participan pedidos con `sede_id = S` y de la misma
  institución. Un pedido de otra sede no se asigna aunque demande el mismo
  producto, y no existe ningún traspaso de cantidades entre sedes.
  - Un pedido sin `sede_id` no participa.
  - `sede_id` no cambia después de la emisión.

### AC-9 — Cobertura total, parcial y faltante

- **DADO QUE** un pedido/producto tiene demanda `D` y una cobertura
  `C = plan_previo + stock_cubierto + entregado` (con `comprado_pendiente` y
  `stock_cubierto` de D-4),
- **CUANDO** se lee una necesidad, un preview, una OC o el detalle del pedido,
- **ENTONCES**:
  - En la **necesidad** (sin compra nueva), `faltante = max(0, D - C)`; en el
    **preview**, el faltante se calcula después de repartir la compra simulada:
    `faltante = max(0, D - C - asignada)`. En la cadena del pedido se aplica D-7
    y un pedido terminal muestra `0`.
  - La etiqueta es «Cobertura total» si `faltante = 0`, «Cobertura parcial» si
    `0 < C < D`, y «Sin cobertura» si `C = 0`.
  - El `cantidad_faltante` persistido en una fila del plan es la foto de lo que
    esa OC dejó sin cubrir al emitirse; no se suman los faltantes de varias OC
    para calcular la cobertura viva. La cobertura viva se calcula sumando
    `cantidad_asignada` de las OC activas y restando de la demanda.

### AC-10 — Roles, capacidad y contrato

- **DADO QUE** un actor intenta usar la nueva operación,
- **CUANDO** invoca `POST /compras/cobertura/preview`,
- **ENTONCES** solo el Administrador Institucional recibe `200`; Solicitante,
  Bodeguero y Superadmin reciben `403`. Con la capacidad `compras` deshabilitada,
  el Administrador también recibe `403`.
- **DADO QUE** se publica el contrato,
- **CUANDO** se consulta `/openapi.json`,
- **ENTONCES** la operación nueva aparece y la matriz central pasa de 72 a 73
  operaciones; las operaciones existentes conservan sus roles.
- **DADO QUE** se revisa el modelo,
- **ENTONCES** se declara la 22.ª entidad de dominio (`orden_compra_ticket`), 27
  tablas en `control`, 24 por tenant y versión `021.1`, sin capacidad nueva.

### AC-11 — Integridad multi-tenant y esquema

- **DADO QUE** una institución opera sus compras,
- **CUANDO** se persiste o consulta un plan,
- **ENTONCES** cada fila de `orden_compra_ticket` pertenece a la institución de
  su OC y sus FKs compuestas impiden mezclar OC, pedido, producto o detalle de
  otra institución. La clave única `(orden_compra_id, ticket_id, producto_id)`
  impide duplicados.
  - La tabla existe en `control` por paridad estructural y queda vacía en la
    semilla; cada tenant tiene la suya.
  - El plan de una institución no es visible para otra.
  - El DDL de instalación limpia crea la tabla y la columna
    `historial_transicion_ticket.orden_compra_id` con su FK; la semilla sube a
    `021.1` y verifica los conteos.

### AC-12 — Preview y emisión consistentes

- **DADO QUE** el estado de pedidos, stock y planes no cambia entre una
  previsualización y la emisión,
- **CUANDO** se compara el preview con el plan persistido,
- **ENTONCES** las cantidades `asignada` y `faltante` por `(pedido, producto)`
  coinciden, salvo que la emisión persiste solo las filas con `asignada > 0`.
  - El preview no crea filas, no reserva stock y es idempotente.
  - Un cambio de estado entre ambas lecturas puede cambiar el resultado; el plan
    emitido es la foto del instante de la emisión.

### AC-13 — Auditoría planificado vs real

- **DADO QUE** una OC fue emitida,
- **CUANDO** se factura, recepciona, cancela o el pedido cambia de estado,
- **ENTONCES** las filas de `orden_compra_ticket` no se actualizan ni se borran.
  - El detalle de la OC conserva la cantidad comprada (real de compra).
  - El plan conserva la asignación (intención).
  - La cadena del pedido conserva `comprado`, `recibido`, `entregado` y
    `faltante` (real de avance).
  - La cancelación conserva el plan y lo excluye de la cobertura activa.

### V-1 — Copia visible «Pedidos»

- **DADO QUE** un usuario navega la SPA,
- **CUANDO** abre el menú, el tablero, el modal, el detalle, el dashboard, la
  recepción o los textos de departamentos,
- **ENTONCES** lee «Pedidos», «Estados de pedidos», «+ Crear pedido», «Crear
  pedido de requerimiento», «Pedido #…», «Pedidos Activos» y las variantes en
  singular/plural, sin «ticket» en la copia visible.
  - Las rutas `/tickets`, la API `/api/v1/tickets/*`, las interfaces, las tablas
    y los identificadores canónicos no cambian.
  - Los títulos de pestaña son «Pedidos | CompuStock» y «Detalle del pedido |
    CompuStock».

### V-2 — Menú «Compras»

- **DADO QUE** un Administrador ve el menú de compras,
- **CUANDO** lo despliega,
- **ENTONCES** lee, en este orden, «Compras», «Órdenes de Compra» y «Recepción de
  Compras».
  - «Compras» navega a `/compras/necesidades`; la ruta y el endpoint no cambian.
  - La vista de necesidades se titula «Compras» y su subtítulo explica que
    muestra necesidades y los pedidos que las componen.

### V-3 — Estados con palabras separadas

- **DADO QUE** la SPA muestra un estado de pedido,
- **CUANDO** el estado canónico es `EnCurso` o `EnRevision`,
- **ENTONCES** lo muestra como «En Curso» o «En Revisión»; cualquier otro estado
  se muestra igual.
  - El helper `frontend/src/app/shared/utils/etiqueta-estado.ts` centraliza el
    mapa.
  - Se aplica al tablero, al detalle, al historial, al estado inicial y a las
    nuevas listas de la 021.
  - `ColumnaKanban` conserva `estado` canónico y agrega `etiqueta`; la lógica de
    roles, guards y tests sigue usando el nombre canónico.

### V-4 — Capacidad «Pedidos»

- **DADO QUE** un Superadmin abre Control de instituciones,
- **CUANDO** revisa las capacidades,
- **ENTONCES** la capacidad `tickets` se rotula «Pedidos».
  - El valor persistido, la API y el `CHECK` siguen siendo `tickets`.
  - El cambio es solo de etiqueta visible.

---

## 8. Restricciones y Consideraciones de Diseño

1. **No modificar la simulación de la 020.** `calcular_cobertura_tickets`,
   `stock_disponible`, el desbloqueo todo-o-nada y la recepción ACID se
   conservan. La necesidad neta parcial es una función nueva y separada.
2. **No agregar un estado de pedido.** `Cerrado` sigue siendo el despacho y
   `Anulado` el terminal negativo. La recepción no cierra, no asigna
   `fecha_cierre` y no escribe un estado nuevo.
3. **No reservar stock.** El plan es una intención; el stock físico solo cambia
   con la recepción (`ENTRADA`) y el despacho (`SALIDA`).
4. **Una sola tabla nueva.** No se agrega una segunda tabla de plan ni una tabla
   de notificaciones. `orden_compra_ticket` es la 22.ª entidad de dominio.
5. **Sin asignación manual.** No se expone un endpoint para mover filas de plan;
   la emisión es la única escritura.
6. **Sin migraciones.** El DDL y la semilla se actualizan; la base se reconstruye
   con `down -v` + `up -d`. La versión sube a `021.1`.
7. **Sin paquetes nuevos.** Todo se resuelve con FastAPI, SQLAlchemy, Pydantic
   v2, Angular 18 y Tailwind ya instalados.
8. **Precedencia de errores.** Se conserva 401 → 403 matriz → 403 capacidad →
   409 (estado/regla) → 404 (recurso inexistente/ajeno) → 422 (cuerpo), con las
   particularidades del preview en AC-2.
9. **Aislamiento multi-tenant.** Las FKs compuestas por institución y el filtro
   por `institucion_id` son obligatorios; no hay FK cross-schema.
10. **Compatibilidad con la 020.** La única enmienda funcional es AC-1/§4.1
    (sugerido neto y campos nuevos); el resto de la 020 sigue vigente.
11. **Copia visible.** El renombrado no toca rutas, API, tablas, columnas,
    permisos, capacidades ni identificadores. Los mensajes canónicos del backend
    no se renombran.
12. **Accesibilidad.** Las nuevas tablas y listas usan encabezados, `caption`,
    `aria-label`, estados de carga y error visibles, y no dependen solo del color.

---

## 9. Decisiones Adicionales Tomadas (Post-QA)

Las siguientes resoluciones responden a las decisiones del usuario y a las
preguntas de diseño que la spec deja cerradas:

1. **Opción A para `Cerrado`.** La recepción no cierra el pedido; el cierre es el
   despacho de la 005, que rebaja stock y escribe `SALIDA`. La recepción solo
   incrementa stock, actualiza `recibido` y enciende `stock_disponible`.
2. **Plan congelado al emitir.** No hay plan en `Borrador`, no hay selección
   manual, no hay reserva y no hay replanificación automática. La emisión es el
   único punto de escritura.
3. **`cantidad_faltante` es una foto.** La fila del plan guarda el hueco que esa
   OC dejó al emitirse. La cobertura viva se calcula sumando asignaciones de OC
   activas; no se suman faltantes históricos.
4. **Las OC `Recibida` no se restan como plan previo.** Su cantidad ya está en
   `stock_actual`; restarlas otra vez duplicaría la cobertura. Sí se muestran en
   `comprado`/`recibido` de la cadena.
5. **`stock_comprometido` es la compra completa.** Incluye la parte no asignada a
   pedidos (reposición de mínimo); el plan es solo la parte earmarcada. La UI
   debe explicar la diferencia cuando muestre ambos números.
6. **La cancelación no replanifica.** Conserva el plan y libera la cobertura; el
   pedido vuelve a la necesidad y una emisión futura lo asigna.
7. **El renombrado es de copia visible.** La SPA usa «pedido»; la API, las rutas,
   las tablas, los permisos y los mensajes canónicos del backend no cambian.
8. **Menú de compras.** «Compras» (necesidades), «Órdenes de Compra» y
   «Recepción de Compras», en ese orden.
9. **Helper de estados.** `frontend/src/app/shared/utils/etiqueta-estado.ts`
   centraliza `EnCurso` → «En Curso» y `EnRevision` → «En Revisión»; el valor
   canónico sigue siendo el que usan la lógica y los guards.
10. **Un solo endpoint nuevo.** `POST /compras/cobertura/preview`; los cambios de
    `GET /compras/necesidades`, `GET /compras/ordenes` y `GET /tickets/{id}` son
    aditivos sobre operaciones existentes.

---

## 10. Estado de Verificación por AC

Verificado el **08/Nov/2026** con la suite de backend (SQLite + gated PostgreSQL
16), `ng test`, `ng build`, `/openapi.json` y el recorrido funcional en 4200 con
escritura real, más el humo en 8080 con la imagen reconstruida (AGENTS §8.5–§8.6).

| AC | Estado | Evidencia |
|---|---|---|
| AC-1 | ✅ Verificado | `test_necesidad_agrega_comprometido_borrador_y_tickets_sin_romper_la_020`, `test_necesidades_enriquecidas_con_comprometido_borrador_y_pedidos`, `test_necesidades_con_sede_ajena_devuelve_lista_vacia`. Recorrido 4200: necesidad de sede 2/producto 9 con stock 6, mínimo 12, demanda 15, comprometido 0, borrador 0, sugerido 21 y pedido #9 (cubierta 6 / faltante 9); captura `4200-02`. |
| AC-2 | ✅ Verificado | `test_preview_reparte_la_compra_y_no_persiste_ni_reserva`, `test_preview_es_idempotente`, `test_preview_sin_demanda_deja_la_compra_sin_asignar`, `test_preview_rechaza_sede_inexistente_y_ajena_con_404`, `test_preview_rechaza_producto_ajeno_inexistente_inactivo_y_repetido`, `test_preview_http_responde_200_con_la_forma_documentada`, `test_preview_http_rechaza_cuerpo_invalido_con_422`, `test_preview_solicitud_rechaza_items_vacios_y_cantidades_no_positivas`. Recorrido: preview de 5 → asignada 5/faltante 4; de 21 → asignada 9/faltante 0/sin asignar 12. |
| AC-3 | ✅ Verificado | `test_emision_persiste_el_plan_para_los_pedidos_con_asignacion`, `test_emision_sin_demanda_emite_con_plan_vacio`, `test_emision_resta_el_plan_previo_y_rechaza_la_segunda_emision`, `test_simulacion_asigna_por_prioridad_y_fifo_con_faltante_parcial`; gated `test_emisiones_concurrentes_no_duplican_la_asignacion`. Recorrido: OC 1 emitida en la misma transacción con plan (pedido 9, asignada 9, faltante 0). |
| AC-4 | ✅ Verificado | `test_orden_compra_respuesta_serializa_el_plan_y_conserva_sus_campos`, `test_orden_a_respuesta_resuelve_el_resumen_del_plan`, `test_emision_http_devuelve_el_plan_y_el_listado_lo_incluye`, `test_plan_congelado_no_cambia_al_facturar_ni_con_pedidos_nuevos`. Capturas `4200-03` y `8080-03`: panel «Pedidos cubiertos por esta OC» con pedido, producto, asignado y faltante. |
| AC-5 | ✅ Verificado | `test_detalle_pedido_expone_asignaciones_cadena_e_historial_con_oc`, `test_detalle_expone_asignaciones_y_cadena_por_producto`, `test_detalle_http_incluye_asignaciones_y_cadena`, `test_detalle_de_pedido_terminal_deja_el_faltante_en_cero`. Recorrido: detalle con asignación OC `Recibida`, `stock_disponible=true` y cadena 15/9/9/0/0 antes del despacho; captura `4200-04`. |
| AC-6 | ✅ Verificado | `test_recepcion_enlaza_la_oc_solo_en_la_fila_de_desbloqueo`, `test_recepcion_http_historial_expone_numero_oc`; gated `test_historial_transicion_ticket_tiene_orden_compra_id_y_fk`. Recorrido: `ENTRADA` 21 (stock 6 → 27), historial `EnCurso → EnCurso` con `orden_compra_id=1` y `numero_oc`, y el pedido permanece en `EnCurso`. |
| AC-7 | ✅ Verificado | `test_cancelacion_conserva_el_plan_y_libera_la_cobertura`, `test_detalle_marca_oc_cancelada_y_no_la_suma_a_la_cobertura`. |
| AC-8 | ✅ Verificado | `test_simulacion_excluye_otra_sede_sin_sede_y_estados_no_en_curso`; AC-2 cubre la sede inexistente/ajena. |
| AC-9 | ✅ Verificado | `test_simulacion_asigna_por_prioridad_y_fifo_con_faltante_parcial`, `test_simulacion_reparte_stock_parcial_antes_de_la_compra`, `test_simulacion_resta_plan_previo_y_no_resta_oc_recibida`, `test_preview_reparte_la_compra_y_no_persiste_ni_reserva`, `test_detalle_de_pedido_terminal_deja_el_faltante_en_cero`. Recorrido: cobertura parcial 5/4 y total 9/0; tras el despacho la cadena queda 15/9/9/15/0. |
| AC-10 | ✅ Verificado | `test_preview_http_deniega_roles_no_administradores`, `test_preview_con_capacidad_compras_apagada_responde_403`, `test_matriz_declara_el_preview_con_su_rol_y_la_matriz_llega_a_73`, `test_openapi_publica_el_preview_y_73_operaciones`; `/openapi.json` con 73 operaciones v1. |
| AC-11 | ✅ Verificado | Gated PostgreSQL 021 **5 passed**: 27 tablas en `control` y 24 por tenant, semilla `021.1`, tabla vacía en ambos esquemas, columna `historial_transicion_ticket.orden_compra_id` con FK, y `UNIQUE`/FKs compuestas/índices. `test_modelo_orden_compra_ticket_expone_plan_y_historial_enlaza_oc`. |
| AC-12 | ✅ Verificado | `test_preview_es_idempotente`, `test_preview_http_responde_200_con_la_forma_documentada`, `test_emision_persiste_el_plan_para_los_pedidos_con_asignacion`. Recorrido: el preview de 21 anticipó asignada 9/faltante 0 y el plan emitido persistió exactamente esa foto. |
| AC-13 | ✅ Verificado | `test_plan_congelado_no_cambia_al_facturar_ni_con_pedidos_nuevos`, `test_cancelacion_conserva_el_plan_y_libera_la_cobertura`, `test_detalle_marca_oc_cancelada_y_no_la_suma_a_la_cobertura`. SQL: la fila de `orden_compra_ticket` sigue intacta tras facturar, recepcionar y despachar. |
| V-1 | ✅ Verificado | `ng test` **537 passed** y recorrido en 4200/8080: menú «Pedidos», título «Estados de pedidos», «+ Crear pedido», «Crear pedido de requerimiento», «Pedido #…» y «Pedidos Activos»; capturas `4200-01` y `8080-01`. Rutas `/tickets` y API sin cambios. |
| V-2 | ✅ Verificado | Recorrido en 4200/8080: menú en orden «Compras» → «Órdenes de Compra» → «Recepción de Compras»; «Compras» navega a `/compras/necesidades`, que se titula «Compras» y explica los pedidos que componen la demanda; capturas `4200-02` y `8080-02`. |
| V-3 | ✅ Verificado | `etiqueta-estado.spec.ts` (4 tests) y `ticket-detalle.component.spec.ts` («En Curso → En Curso»); recorrido en ambos puertos con «En Revisión» y «En Curso» en el tablero y el historial. |
| V-4 | ✅ Verificado | `frontend/src/app/features/control/capacidades.component.spec.ts:116` exige la etiqueta «Pedidos» para la capacidad `tickets`; el valor persistido y la API no cambian. |
