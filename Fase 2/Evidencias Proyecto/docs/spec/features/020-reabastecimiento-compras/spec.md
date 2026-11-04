# Feature 020: Reabastecimiento externo y compras de insumos

**Estado:** aprobado (revisión 2, sincronizada con §9)  
**Release:** 2.0  
**Tipo:** Flujo operativo de reabastecimiento (Procure-to-Stock-to-Desk) y control de existencias

---

## 1. Problema

El sistema Compustock ERP actualmente solo contempla la salida de inventario mediante el despacho transaccional de tickets aprobados (Feature 005). Sin embargo, carece de un flujo formal para la entrada de insumos provenientes de compras o abastecimiento externo:

1. **Quiebre de stock sin reposición formal:** Cuando los insumos alcanzan su stock crítico o se agotan en una sede, no existe un circuito digital para consolidar la necesidad, cotizar o emitir órdenes de compra a proveedores.
2. **Falta de entidad Proveedor:** No existe un registro centralizado ni homologado de proveedores externos de insumos de ofimática al que las instituciones puedan recurrir.
3. **Ausencia de control previo y respaldo tributario:** No hay un mecanismo de control de costos ni de registro de facturas de compra emitidas por proveedores. Esto expone a que en bodega se reciban bultos sin verificar su respaldo tributario oficial o que la administración desconozca qué se adquirió.
4. **Recepción informal en bodega:** Los encargados de bodega no cuentan con una herramienta en el sistema para cotejar la llegada física de mercadería contra una orden autorizada y facturada, imposibilitando registrar la entrada conforme.
5. **Ruptura de la Trazabilidad Absoluta:** Al no haber un flujo de entrada formal, cualquier ajuste de stock carece de justificación de origen, violando el principio constitucional de que ningún insumo puede aumentar su saldo sin un movimiento inmutable y justificado en auditoría (`constitucion.md` §4).
6. **Desconexión con los solicitantes en espera:** Los funcionarios que emitieron tickets que no pudieron ser despachados por falta de stock quedan en un limbo operativo: cuando los productos finalmente llegan a la bodega, el sistema no reactiva los requerimientos ni notifica a los solicitantes afectados.

---

## 2. Objetivo

Implementar el ciclo completo de reabastecimiento externo (*Procure-to-Stock-to-Desk*), permitiendo:
1. Detectar y consolidar las necesidades de reposición de insumos por sede a partir de stock crítico y tickets en espera.
2. Disponer de un catálogo global de proveedores externos homologados.
3. Permitir al Administrador Institucional generar y emitir Órdenes de Compra (OC) dirigidas a un proveedor y destinadas a una sede específica.
4. Registrar los datos de la Factura tributaria de respaldo del proveedor como llave de activación obligatoria para autorizar la recepción física.
5. Permitir al Bodeguero de la sede destino registrar la recepción física conforme de los insumos.
6. Ejecutar el recálculo e incremento automático de existencias físicas mediante una transacción ACID que genere movimientos inmutables de auditoría de tipo `ENTRADA`.
7. Desbloquear automáticamente los tickets que esperaban dicho insumo en la sede receptora y notificar a los funcionarios solicitantes que sus productos ya se encuentran disponibles para preparación.

---

## 3. Actores del Sistema

- **Superadmin:** Administra y homologa el catálogo maestro y global de proveedores externos en la plataforma SaaS.
- **Administrador Institucional:** Consulta las alertas de stock crítico y tickets en espera por sede; consulta proveedores externos; emite, gestiona y anula Órdenes de Compra; y registra/audita la Factura de compra y control de costos.
- **Bodeguero / Encargado de Suministros:** Visualiza las órdenes de compra facturadas con destino exclusivo a su sede asignada; coteja la mercadería física contra la factura/OC y confirma la recepción física, incrementando las existencias.
- **Solicitante (Funcionario):** Recibe aviso y visualiza en sus tickets pendientes que el stock de insumos solicitados ha arribado a la sede y su pedido se encuentra listo para preparación.

---

## 4. Alcance

### 4.1 Dentro de alcance

- **Detección y consolidación de necesidades por sede:**
  - Panel o vista de consolidación de insumos con saldo menor o igual al mínimo (`stock_actual <= stock_minimo`) o con tickets en estado `EnCurso` cuya demanda supera el saldo de la sede.
  - Sugerencia de reposición calculada como `max(0, stock_minimo + demanda_en_curso - stock_actual)`: el saldo por encima del mínimo descuenta demanda antes de comprar. Solo cuentan los tickets `EnCurso` (aprobados); `Pendiente` y `EnRevision` no se compran por adelantado.
- **Catálogo global de Proveedores:**
  - Estructura general de proveedores (RUT/identificador fiscal, razón social, nombre de fantasía, giro, contacto, correo, teléfono y estado activo).
  - Consulta de proveedores disponibles para todas las instituciones al momento de emitir una compra.
  - **Alta de proveedores:** El Administrador Institucional puede proponer y crear nuevos proveedores que quedan disponibles en el catálogo global compartido para todas las instituciones del SaaS. El Superadmin también puede crear y consultar el catálogo global mediante la misma API; la interfaz dedicada del panel SaaS queda fuera de alcance en este incremento.
- **Ciclo de vida de la Orden de Compra (OC):**
  - Registro de OC asociada obligatoriamente a una institución, una sede de destino y un proveedor externo.
  - Edición de la OC mientras está en `Borrador`: sede, proveedor e ítems son editables; al emitir quedan bloqueados.
  - Detalle de ítems ordenados: producto, cantidad solicitada y costo unitario pactado/estimado.
  - Estados formales: `Borrador`, `Emitida`, `Facturada`, `Recibida` (Completada) y `Cancelada`.
- **Registro y validación de Factura del Proveedor:**
  - Registro de respaldo tributario: número de factura, fecha de emisión, monto total e información complementaria.
  - Validación de unicidad de factura por proveedor.
  - Llave de activación: la orden solo pasa al estado `Facturada` cuando cuenta con factura registrada, habilitando la acción de recepción en bodega.
- **Recepción física en bodega:**
  - Vista exclusiva para el Bodeguero con las órdenes en estado `Facturada` asignadas a su sede.
  - Registro de conformidad de recepción física de mercadería mediante una confirmación simple, sin cantidades en el cuerpo: el backend usa las cantidades de `detalle_orden_compra`.
- **Transacción ACID de incremento de existencias y auditoría:**
  - Incremento atómico del `stock_actual` en el stock de la sede receptora por cada producto recibido; si no existe la fila `(sede, producto)`, se crea con el saldo recibido.
  - Registro inmutable obligatorio de auditoría en los movimientos de inventario con tipo `ENTRADA`, fecha/hora, sede, cantidad recibida y una glosa que referencia la OC, la Factura y el Bodeguero receptor. La tabla canónica **no** tiene columna de autor: el actor viaja en `observacion`.
- **Desbloqueo de tickets y aviso al Solicitante:**
  - Identificación automática de tickets en estado `EnCurso` de la sede destino para los productos reabastecidos, en orden de prioridad (Alta → Media → Baja) y FIFO.
  - Exposición de la condición "Stock disponible / Listo para despacho" como propiedad calculada `stock_disponible` en el DTO de detalle del ticket; **no** se agrega una columna ni se cambia el estado.
  - Registro del hito de desbloqueo en el historial de transiciones del ticket y aviso visible para el Solicitante como badge en el detalle de su ticket.

### 4.2 Fuera de alcance

- Pasarelas de pago electrónico en línea (Webpay, Stripe, etc.) o transferencias bancarias automatizadas (el pago financiero ocurre fuera del sistema ERP).
- Integración telemática con webservices del Servicio de Impuestos Internos (SII) o emisión directa de DTEs electrónicos (la factura se registra por sus metadatos de respaldo).
- Recepciones parciales multi-etapa con múltiples facturas divididas para una misma orden (en esta versión la recepción es unitaria y total por OC/Factura).
- Devoluciones a proveedores o emisión de Notas de Crédito comerciales.
- Baja o reactivación de proveedores del catálogo global: `activo` se crea en `true` y no se expone una operación de cambio de estado en esta versión.
- Interfaz dedicada del Superadmin para gestionar el catálogo global desde el panel SaaS: la API queda disponible, pero la vista se difiere.
- Notificaciones push o correo electrónico: el aviso al Solicitante es el badge calculado en el detalle del ticket.
- Integración directa con plataformas de licitación pública externa (ej. Mercado Público).

---

## 5. Decisiones de Diseño de Negocio

### D-1 — Proveedor como catálogo global compartido en plataforma

El requerimiento establece que el proveedor es una entidad general/global que abastece a distintas instituciones. Los proveedores (distribuidores de papelería, tecnología, insumos de aseo y ofimática) no pertenecen a una institución en particular.

**Por qué:** Evita la duplicación inconsistente de razones sociales, RUTs y contactos entre múltiples instituciones del sistema y sienta una base homogénea de proveedores homologados a nivel SaaS.

### D-2 — Orden de Compra anclada a una Institución y con Sede de destino obligatoria

Toda Orden de Compra pertenece a la institución que la emite y debe especificar de manera obligatoria e inmutable la sede física de destino donde el proveedor despachará los materiales.

**Por qué:** En un modelo con inventario descentralizado por sedes (`stock_sede`), el material no entra a un "éter institucional", sino a una bodega física concreta con estanterías y bodegueros responsables asignados.

### D-3 — Factura de Respaldo como "Llave de Activación" para Bodega

El Bodeguero de la sede destino no puede ejecutar la recepción en el sistema si la Orden de Compra se encuentra únicamente en estado `Emitida`. Es requisito indispensable que el Administrador Institucional ingrese previamente los datos de la Factura de compra oficial enviada por el proveedor (número, fecha, monto total), lo que transiciona la OC a estado `Facturada`.

**Por qué:** Protege contra recepciones de palabra, mercancía no autorizada presupuestariamente o desajustes contables. Garantiza que el ingreso a bodega cuente con respaldo tributario y administrativo antes de tocar el inventario físico.

### D-4 — Recepción física y actualización transaccional indivisible (ACID)

La confirmación de recepción física en bodega por parte del Bodeguero ejecuta una única transacción ACID que en un solo paso indivisible:
1. Cambia el estado de la OC a `Recibida`.
2. Aumenta el stock físico de la sede (`stock_actual`) para cada insumo.
3. Inserta las filas inmutables de tipo `ENTRADA` en los movimientos de inventario con referencia explícita a la OC y Factura.
4. Identifica y desbloquea los tickets en espera de stock en esa sede.
5. Genera el aviso de reabastecimiento al solicitante.

**Por qué:** Cumple estrictamente con el principio constitucional de *Trazabilidad Absoluta* y *Consistencia Transaccional* (`constitucion.md` §4): el inventario jamás puede aumentar sin su correspondiente movimiento auditado, y no puede quedar mercadería recepcionada sin impactar el stock ni tickets sin actualizar.

### D-5 — Recepción total conforme por Orden de Compra (versión base)

En este incremento, la recepción de la OC/Factura se realiza por el total de las cantidades indicadas en la orden. No se habilitan recepciones parciales divididas en múltiples entregas.

**Por qué:** Mantiene el modelo de dominio simple, determinista y confiable en su primer ciclo de reabastecimiento, evitando complejidad de saldos remanentes, estados mixtos y múltiples facturas para una misma orden.
  - **Corrección de factura:** El Administrador puede reeditar los metadatos de la factura (número, fecha, monto) mientras la OC esté en estado `Facturada` y no haya sido recepcionada. El proveedor asociado no es editable una vez emitida la OC.

### D-6 — Condición operativa de tickets en espera de stock (propiedad calculada)

Un ticket en estado `EnCurso` cuyos insumos solicitados superan el stock físico disponible en su sede no puede ser despachado en el flujo Kanban. El sistema expone esta condición como una **propiedad calculada en el DTO de lectura del ticket** (`stock_disponible: bool`): cuando el nuevo stock de la sede cubre la demanda del ticket, la propiedad retorna `true`. No se agrega ninguna columna nueva al DDL ni se modifica el catálogo de `estado_ticket`.

Al concretarse la recepción física de la OC, el servicio evalúa la cola de tickets en `EnCurso` de esa sede y producto, en orden de **prioridad descendente** (Alta > Media > Baja) con **FIFO como desempate** entre tickets de igual prioridad. Solo se desbloquean los tickets cuya demanda individual pueda ser satisfecha por el stock disponible acumulado hasta ese punto (asignación greedy por orden de prioridad/antigüedad). El stock sobrante no desbloquea tickets cuya demanda supere el remanente.

**Por qué:** Transparenta el motivo por el cual un ticket no avanza sin alterar el modelo de estados aprobado en la Feature 013. La priorización por prioridad de ticket respeta la intención con que el Administrador catalogó la urgencia de cada requerimiento.

### D-7 — Separación de roles: Administración vs. Bodega vs. Solicitante

- El Administrador Institucional es la única autoridad autorizada para comprometer recursos de compra, emitir OCs y validar el control de costos/facturas.
- El Bodeguero no tiene atribución para emitir compras a proveedores ni modificar precios, sino únicamente para verificar físicamente la mercadería en su sede y confirmar la recepción.
- El Solicitante no interviene en el proceso de compras; únicamente recibe avisos transparentes cuando su material solicitado ha arribado.

**Por qué:** Establece un principio de segregación de funciones (SoD - *Segregation of Duties*), previniendo compras discrecionales desde bodega y garantizando control financiero institucional.

### D-8 — Cancelación restrictiva de Órdenes de Compra con motivo obligatorio

Una Orden de Compra solo puede ser cancelada por el Administrador Institucional si se encuentra en estado `Borrador` o `Emitida`, exigiendo un motivo justificado de cancelación. Si la orden ya cuenta con factura (`Facturada`) o ya fue recepcionada físicamente (`Recibida`), no puede ser cancelada directamente en este flujo.

**Por qué:** Una vez emitida la factura existen obligaciones tributarias y comerciales que no pueden descartarse con un simple borrado, protegiendo la consistencia documental.

---

## 6. Reglas del Flujo de Estados

```
[Borrador] 
   │
   │ (Admin Institucional formaliza)
   ▼
[Emitida] 
   │
   │ (Proveedor entrega factura / Admin registra factura de respaldo)
   ▼
[Facturada]  ◄── "Llave de Activación" para Bodega
   │
   │ (Bodeguero de la sede destino coteja y confirma recepción física)
   ▼
[Recibida]   ──► (Transacción ACID: Stock ↑ + Movimiento 'ENTRADA' + Tickets Desbloqueados + Aviso Solicitante)
```
*(Cancelación posible únicamente desde `Borrador` o `Emitida` hacia `Cancelada` con motivo obligatorio).*

### 6.1 Ciclo de vida de la Orden de Compra (OC)

1. **Estado `Borrador`:**
   - La orden ha sido creada preliminarmente por el Administrador Institucional.
   - Permite agregar, modificar o quitar productos, cambiar cantidades solicitadas y costos unitarios estimados.
   - Sede de destino y proveedor deben estar asignados.
   - No genera compromisos externos ni habilita recepciones.
2. **Estado `Emitida`:**
   - El Administrador formaliza la orden. Pasa a estar bloqueada para modificación de ítems, cantidades o sede destino.
   - Queda lista para ser remitida al proveedor seleccionado.
   - Aún **no** habilita la recepción física en bodega.
3. **Estado `Facturada`:**
   - El Administrador registra los datos de la factura comercial/tributaria emitida por el proveedor (número, fecha, monto).
   - Este estado actúa como **llave de activación**: aparece visible y habilitada en la bandeja del Bodeguero de la sede destino para su recepción física.
4. **Estado `Recibida` (Terminal positivo):**
   - El Bodeguero de la sede confirma que los insumos físicos han ingresado a las dependencias de la bodega conforme a la factura y OC.
   - Se ejecuta el incremento de stock y auditoría. La orden queda cerrada e inmutable.
5. **Estado `Cancelada` (Terminal negativo):**
   - Transición disponible únicamente desde `Borrador` o `Emitida`.
   - Requiere registro obligatorio de un motivo de cancelación (texto no vacío de hasta 500 caracteres).
   - No tiene marcha atrás.

### 6.2 Ciclo y validaciones de la Factura de respaldo

- **Metadatos obligatorios:**
  - `numero_factura`: Texto no vacío (ej. "FAC-98421").
  - `fecha_factura`: Fecha válida de emisión (no puede ser futura).
  - `monto_total`: Valor numérico positivo mayor a cero, correspondiente al total facturado.
  - `observaciones`: Opcional, para indicar condiciones de despacho o guía de despacho asociada.
- **Validación de unicidad:** No puede registrarse dos veces el mismo número de factura para un mismo proveedor.
- **Consistencia:** El registro de la factura debe estar vinculado a una OC en estado `Emitida`.

### 6.3 Recepción física de mercadería en bodega

- **Ámbito estricto por sede:** El Bodeguero solo puede visualizar y accionar órdenes de compra en estado `Facturada` cuya `sede_id` de destino coincida exactamente con su sede asignada.
- Un Bodeguero asignado a la "Sede Maipú" no puede ver ni recepcionar órdenes con destino a "Sede Providencia".
- El Administrador Institucional tiene visibilidad de todas las órdenes de su institución y puede auditar su estado.

### 6.4 Incremento transaccional de stock y auditoría inmutable

Al confirmar la recepción física, en una única transacción:
1. Para cada ítem de la orden, se incrementa `stock_sede.stock_actual = stock_actual + detalle_orden_compra.cantidad_solicitada` en la sede receptora. No se reciben cantidades del cliente.
2. Si un producto no poseía previamente una fila de existencias en esa sede, se inicializa con saldo igual a la cantidad recibida.
3. Se inserta obligatoriamente un registro en los movimientos de inventario con:
   - Tipo de movimiento: `ENTRADA`.
   - Cantidad: positiva, correspondiente a las unidades de `detalle_orden_compra`.
   - `stock_sede_id`: la fila de la sede receptora; `inventario_id` queda nulo.
   - Fecha y hora: marca de tiempo exacta del sistema.
   - Motivo/Glosa: referencia explícita y no vacía a la OC, la Factura y el Bodeguero receptor, por ejemplo: `"Recepción OC-2026-000001 / Factura FAC-98421 — Bodeguero: juan.perez@compustock.cl"`. La tabla `movimiento_inventario` **no** tiene columna de autor; el actor se porta en `observacion`.
4. El bloqueo se toma en el orden OC → producto → `stock_sede`, con los detalles ordenados por `producto_id`, para serializar la recepción con la baja de catálogo de la Feature 014 y evitar interbloqueos.

**Producto inactivo:** la creación y emisión de una OC exigen que todos sus productos estén activos. Si un producto se desactiva después de la emisión y antes de la recepción, la recepción **sí** se registra: la mercadería ya fue despachada por el proveedor y la Trazabilidad Absoluta exige reflejarla. El producto sigue inactivo (no aparece en el catálogo operativo ni admite nuevos tickets) y puede reactivarse después. Esta excepción es exclusiva de la recepción de compras; `POST /inventario/movimientos` sigue rechazando con 409 todo movimiento sobre un producto inactivo.

### 6.5 Desbloqueo de tickets y aviso de reabastecimiento al Solicitante

1. Solo participan los tickets en estado `EnCurso` de la sede receptora. Quedan excluidos `Pendiente` y `EnRevision` (aún no aprobados) y los terminales `Cerrado` y `Anulado`.
2. La disponibilidad se calcula con una **asignación greedy determinista** por producto: los tickets se ordenan por prioridad (Alta → Media → Baja, es decir `prioridad_id` ascendente en el catálogo canónico) y, a igual prioridad, por `fecha_creacion` ascendente y `ticket_id` ascendente (FIFO). Un ticket se considera cubierto solo si **todos** sus detalles caben en el saldo remanente; si no cabe, no consume stock y se pasa al siguiente. El saldo no se reserva: es una simulación de lectura.
3. `stock_disponible` es una propiedad calculada del DTO de detalle del ticket (`GET /tickets/{ticket_id}`), no una columna ni un estado. Se calcula con la misma simulación, de modo que el badge y el hito de recepción siempre coinciden.
4. Al recepcionar, el servicio compara la cobertura antes y después del incremento. Por cada ticket que pasa de no cubierto a cubierto, registra una fila en `historial_transicion_ticket` con `estado_origen = estado_destino = EnCurso`, actor = Bodeguero, y motivo `"Desbloqueo por reabastecimiento: OC {numero_oc} / Factura {numero_factura}"`. No se cambia el estado del ticket.
5. El Solicitante ve el aviso como badge `"Stock disponible — Listo para despacho"` en el detalle de su ticket cuando `stock_disponible == true`. No hay tabla de notificaciones ni envío de correo.

---

## 7. Criterios de Aceptación (AC)

### AC-1 — Detección y consolidación de necesidades de insumos por sede
- **DADO QUE** existen productos activos con stock físico en nivel crítico (`stock_actual <= stock_minimo`) o tickets en estado `EnCurso` en una sede cuya demanda supera las existencias,
- **CUANDO** el Administrador Institucional consulta la sección de necesidades de abastecimiento para esa sede (o para todas las sedes de su institución),
- **ENTONCES** el sistema presenta el listado consolidado por `(sede, producto)`, indicando el stock actual de la sede, el stock mínimo, la cantidad total demandada por tickets `EnCurso` y una cantidad sugerida `max(0, stock_minimo + demanda_en_curso - stock_actual)`. Un `sede_id` inexistente o ajeno a la institución se comporta como filtro de lista y devuelve `200` con `[]`.

### AC-2 — Consulta y alta del catálogo maestro de Proveedores
- **DADO QUE** un Administrador Institucional va a generar una Orden de Compra,
- **CUANDO** accede a la selección de proveedores,
- **ENTONCES** visualiza el catálogo de proveedores activos homologados globalmente (RUT, razón social, giro, contacto), pudiendo seleccionar el proveedor adecuado.
- **DADO QUE** un Administrador Institucional o un Superadmin registra un proveedor con RUT único, razón social no vacía y datos de contacto válidos,
- **CUANDO** confirma el alta,
- **ENTONCES** la fila queda en `control.proveedor` con `activo = true` y disponible para todas las instituciones; un RUT duplicado responde `409`. El Superadmin opera solo sobre `control` y no crea réplicas tenant.

### AC-3 — Creación y edición de Orden de Compra en estado Borrador
- **DADO QUE** el Administrador Institucional selecciona un proveedor activo y una sede de destino de su institución,
- **CUANDO** ingresa los ítems con sus productos activos, cantidades mayores a cero y costos estimados,
- **ENTONCES** la Orden de Compra queda registrada en estado `Borrador`, permitiendo su posterior edición de sede, proveedor o ítems sin alterar aún el inventario ni habilitar bodega. `PUT /compras/ordenes/{id}` solo acepta órdenes en `Borrador`; una orden `Emitida`, `Facturada`, `Recibida` o `Cancelada` responde `409`.

### AC-4 — Emisión formal de la Orden de Compra
- **DADO QUE** una Orden de Compra se encuentra en estado `Borrador`, contiene al menos un ítem con cantidad mayor a cero y todos sus productos están activos,
- **CUANDO** el Administrador Institucional ejecuta la acción "Emitir Orden de Compra",
- **ENTONCES** la orden pasa a estado `Emitida`, sus ítems, sede y proveedor quedan bloqueados para edición, y se le asigna `numero_oc = OC-{AÑO}-{orden_compra_id:06d}`. Una segunda emisión responde `409`.

### AC-5 — Registro y corrección de la Factura del Proveedor como llave de activación
- **DADO QUE** una Orden de Compra se encuentra en estado `Emitida`,
- **CUANDO** el Administrador Institucional ingresa el número de factura, una fecha de emisión no futura y un monto total mayor a cero,
- **ENTONCES** el sistema valida que el número no esté duplicado para el proveedor de la orden, asocia la factura a la orden y transiciona el estado de la OC a `Facturada`.
- **DADO QUE** una Orden de Compra está en estado `Facturada` y aún no fue recepcionada,
- **CUANDO** el Administrador reedita los metadatos de la factura,
- **ENTONCES** la factura se actualiza sin cambiar el proveedor ni la OC; si la orden ya está `Recibida`, responde `409`.

### AC-6 — Visualización de órdenes facturadas acotada al Bodeguero de la sede
- **DADO QUE** existen órdenes de compra en estado `Facturada`,
- **CUANDO** un Bodeguero accede a su panel de recepciones de bodega,
- **ENTONCES** visualiza única y exclusivamente las órdenes cuya sede de destino coincide con su sede asignada; si no tiene sede asignada responde `409` y una orden de otra sede o institución responde `404`. El listado fuera de ámbito devuelve `200` con `[]`.

### AC-7 — Bloqueo de recepción física si la OC no está Facturada
- **DADO QUE** una Orden de Compra se encuentra en estado `Borrador` o `Emitida` (sin factura registrada),
- **CUANDO** el Bodeguero intenta accionar la recepción en bodega,
- **ENTONCES** la operación es rechazada con `409` (la orden requiere contar con factura registrada para habilitar el ingreso físico a bodega).

### AC-8 — Confirmación de recepción física y aumento atómico de existencias
- **DADO QUE** una Orden de Compra se encuentra en estado `Facturada` y el Bodeguero autorizado de la sede destino confirma la llegada física conforme de la mercadería,
- **CUANDO** se procesa la confirmación de recepción (sin cantidades en el cuerpo; se usan las de `detalle_orden_compra`),
- **ENTONCES** en una única transacción atómica:
  1. El estado de la OC cambia a `Recibida` y se sella `fecha_recepcion`.
  2. Cada producto incrementa su `stock_actual` en la sede en la cantidad exacta de su detalle; si no existe la fila de stock, se crea.
  3. Una OC que no esté `Facturada` responde `409`; una segunda recepción concurrente también responde `409` ("Orden ya recepcionada").

### AC-9 — Registro obligatorio de auditoría inmutable de tipo ENTRADA
- **DADO QUE** se ejecuta con éxito la recepción física de la orden,
- **CUANDO** se consultan los movimientos de inventario de los productos involucrados en esa sede,
- **ENTONCES** existe un registro inmutable con `tipo_movimiento = 'ENTRADA'`, `stock_sede_id` de la sede receptora, la cantidad exacta recibida, la fecha/hora de confirmación y una glosa no vacía que cita el número de OC, el número de Factura y el correo del Bodeguero receptor. `movimiento_inventario` no tiene `usuario_id`: el actor queda en `observacion`.

### AC-10 — Desbloqueo automático de tickets en espera de stock
- **DADO QUE** existen tickets en estado `EnCurso` de la sede receptora cuyos detalles incluyen los insumos ingresados y que, antes de la recepción, no alcanzaban cobertura,
- **CUANDO** el nuevo stock, asignado en orden de prioridad (Alta → Media → Baja) y FIFO, cubre **todos** los detalles del ticket,
- **ENTONCES** `stock_disponible` pasa a `true` para ese ticket y se registra una fila en `historial_transicion_ticket` con `estado_origen = estado_destino = EnCurso`, actor Bodeguero y motivo de desbloqueo. No se cambia el estado del ticket ni se agrega una columna nueva.

### AC-11 — Aviso de reabastecimiento al Solicitante
- **DADO QUE** el ticket de un Solicitante quedó con `stock_disponible = true` tras el reabastecimiento físico,
- **CUANDO** el Solicitante consulta la vista de detalle de su ticket,
- **ENTONCES** visualiza el badge "Stock disponible — Listo para despacho". El aviso es la propiedad calculada del DTO; no hay tabla de notificaciones, correo ni cambio de estado.

### AC-12 — Cancelación de Orden de Compra con motivo justificado
- **DADO QUE** una Orden de Compra se encuentra en estado `Borrador` o `Emitida`,
- **CUANDO** el Administrador Institucional ejecuta la cancelación proporcionando un motivo no vacío de hasta 500 caracteres,
- **ENTONCES** la orden pasa a estado `Cancelada` y persiste `motivo_cancelacion`, `fecha_cancelacion` y `cancelado_por_usuario_id`; si la orden está `Facturada`, `Recibida` o ya `Cancelada`, responde `409`.

### AC-13 — Segregación de roles y denegación estricta
- **DADO QUE** un Solicitante intenta crear/editar/emitir una OC, registrar facturas o confirmar recepciones físicas,
- **ENTONCES** el sistema responde 403 Denegado.
- **DADO QUE** un Bodeguero intenta crear/editar/emitir una OC o registrar facturas de proveedores,
- **ENTONCES** el sistema responde 403 Denegado.
- **DADO QUE** un Superadmin intenta crear/editar/emitir una OC, recepcionar mercadería o consultar necesidades de una institución particular,
- **ENTONCES** el sistema responde 403 Denegado por separación de responsabilidades SaaS/tenant. El Superadmin solo puede listar y crear proveedores en `control`.

### AC-14 — Integridad referencial y aislamiento multi-tenant
- **DADO QUE** una institución opera sus compras,
- **CUANDO** consulta órdenes de compra, facturas o movimientos de entrada,
- **ENTONCES** únicamente visualiza y manipula registros propios de su institución; bajo ninguna circunstancia se mezclan órdenes de compra o recepciones entre instituciones distintas.
- **DADO QUE** el catálogo de proveedores es global,
- **CUANDO** una institución selecciona un proveedor,
- **ENTONCES** la OC referencia una réplica local con el **mismo `proveedor_id`** que `control.proveedor`, sin FK cross-schema. `control.proveedor` es la única estructura compartida; órdenes, detalles, facturas y recepciones viven solo en el esquema tenant.

---

## 8. Restricciones y Consideraciones de Diseño

1. **Constitución del Sistema:**
   - Principio 1 (*Prioridad a la Operación*): El reabastecimiento resuelve la causa raíz del desabastecimiento operativo de las sedes.
   - Principio 2 (*Trazabilidad Absoluta*): Toda entrada debe generar movimiento `ENTRADA` inmutable vinculado al actor físico que recepciona.
   - Principio 3 (*Consistencia Transaccional*): La recepción física, el alza de saldo, el movimiento de auditoría y el desbloqueo de tickets deben ocurrir en una única transacción ACID indivisible.
2. **Modelo de Inventario Descentralizado (Feature 011):**
   - El saldo físico pertenece a `(sede_id, producto_id)`. Las órdenes de compra deben fijar de manera estricta la `sede_id` de destino; no existen compras "flotantes" sin sede asignada.
3. **Aislamiento Multi-Tenant (Feature 010):**
   - El catálogo de `proveedor` reside en el esquema `control` (global). La réplica tenant usa el **mismo `proveedor_id` entero** que control (sin identidad propia), de modo que la correspondencia es determinista e idempotente. Al crear una OC, el servicio valida el proveedor activo en control y hace *upsert* de la réplica en el tenant antes de confirmar la transacción; no hay FK cross-schema.
   - Las lecturas y altas del catálogo global usan una **sesión de control** (`crear_sesion_control`) independiente de la sesión tenant. El Superadmin solo opera sobre control; el Administrador lee control y replica en su tenant.
   - Las órdenes de compra, facturas, detalles y recepciones pertenecen estrictamente al esquema tenant de la institución correspondiente.
4. **Seguridad y Control de Acceso (Feature 007 / Feature 012):**
   - Las nuevas operaciones se incorporan de manera aditiva a la matriz central de permisos del backend y a la capacidad institucional `compras` (séptima capacidad, ampliación explícita del conjunto cerrado de la 012).
   - Precedencia de errores: **401** sesión ausente → **403** matriz de roles → **403** capacidad `compras` deshabilitada → **409** sede no resoluble (Bodeguero sin sede) → **404** recurso inexistente o ajeno → **200/201**.

---

## 9. Decisiones Adicionales Tomadas (Post-QA)

Las siguientes resoluciones responden a las observaciones del agente QA y a las decisiones del usuario. La spec queda sin puntos abiertos.

1. **Gobernanza del Catálogo de Proveedores:** El Administrador Institucional puede crear y proponer nuevos proveedores en el catálogo global (disponibles para todas las instituciones). El Superadmin también puede crear y consultar el catálogo desde la API; la interfaz dedicada del panel SaaS se difiere. La baja/reactivación de proveedores queda fuera de alcance: `activo` nace en `true`.

2. **Corrección de Factura:** El Administrador puede reeditar los metadatos de la factura (número, fecha, monto) mientras la OC esté en estado `Facturada` y no haya sido recepcionada. El proveedor no es editable después de la emisión.

3. **Aviso al Solicitante:** La condición de stock disponible es una propiedad calculada (`stock_disponible: bool`) en el DTO de detalle del ticket. No agrega columnas al DDL ni cambia el estado. Se calcula con la misma asignación greedy de §9.4. El aviso se visualiza como badge en la vista de detalle del ticket.

4. **Desbloqueo por Prioridad:** Solo participan tickets `EnCurso` (no `Pendiente` ni `EnRevision`; los terminales `Cerrado`/`Anulado` quedan fuera). El orden es prioridad Alta → Media → Baja, que en el catálogo canónico es `prioridad_id` **ascendente** (Alta=1, Media=2, Baja=3), con FIFO por `fecha_creacion` y `ticket_id` como desempate. La asignación es por producto y **todo o nada por ticket**: si un ticket no cabe completo, no consume stock y se evalúa el siguiente. `stock_disponible` usa exactamente la misma simulación.

5. **Recepción total por confirmación simple:** El endpoint de recepción no recibe cantidades en el body. El backend usa las cantidades de `detalle_orden_compra`. No es necesario que el Bodeguero re-ingrese unidades.

6. **Recepción concurrente:** La transacción ACID usa `SELECT FOR UPDATE` sobre la OC y bloquea producto → `stock_sede` en orden de `producto_id`. El segundo intento responde **409 Conflict** ("Orden ya recepcionada").

7. **Restricciones de error HTTP estandarizadas:** Bodeguero sin sede → 409. OC de otra sede o de otra institución consultada por ID → 404. Listado de Bodeguero fuera de ámbito → 200 lista vacía. `sede_id` inexistente o ajeno en necesidades → 200 lista vacía.

8. **Sin `usuario_id` en `movimiento_inventario`:** La tabla canónica no incluye columna de autor. La referencia al Bodeguero se porta en `observacion` (texto: "Recepción OC #X / Factura #Y — Bodeguero: correo"). Si en el futuro se necesita FK a usuario, se tramita como un cambio de modelo en `stack.md`. **Esto NO altera el DDL de `movimiento_inventario` en esta feature.**

9. **Tickets en estados terminales excluidos:** El cálculo de cobertura filtra explícitamente `estado != 'Anulado' AND estado != 'Cerrado'` y solo considera `EnCurso`.

10. **Productos inactivos:** La creación y emisión de una OC exigen productos activos. La recepción es válida si el producto se desactiva **después** de la emisión y antes de la llegada, porque la mercadería ya fue despachada y debe auditarse. El producto sigue inactivo y el endpoint genérico `POST /inventario/movimientos` conserva su 409 para productos inactivos. La excepción vive solo en `compra_service`.

11. **Factura con proveedor explícito:** `factura_compra` porta `proveedor_id` (no solo `orden_compra_id`) para poder declarar `UNIQUE(proveedor_id, numero_factura)`. Una FK compuesta `(orden_compra_id, proveedor_id) → orden_compra(orden_compra_id, proveedor_id)` garantiza que la factura y la OC pertenecen al mismo proveedor. `orden_compra` expone la clave única `(orden_compra_id, proveedor_id)`.

12. **Edición de la OC en Borrador:** `PUT /compras/ordenes/{id}` reemplaza sede, proveedor e ítems solo en `Borrador`; al emitir, todo queda bloqueado. Es la operación que exige AC-3 y no crea una entidad nueva.

13. **Cancelación con actor y fecha:** `orden_compra` agrega `motivo_cancelacion`, `fecha_cancelacion` y `cancelado_por_usuario_id` para cumplir AC-12. `fecha_recepcion` sella la recepción.

14. **Número de OC sin carrera:** `numero_oc = OC-{AÑO}-{orden_compra_id:06d}` se deriva del ID identity al emitir; no se usa `SELECT MAX + 1`, que no bloquea filas inexistentes. El `UNIQUE` del número se conserva como defensa.

15. **Contrato de la feature:** 10 operaciones nuevas en la matriz (62 → **72**), 4 entidades de dominio nuevas (17 → **21**), 26 tablas en control, 23 por tenant, versión **`020.1`** y séptima capacidad **`compras`** (28 filas de capacidad en la semilla: 4 instituciones × 7).

16. **Interfaz del Superadmin:** La API de proveedores queda disponible para el Superadmin, pero la vista dedicada del panel SaaS no forma parte de las tareas de esta feature. El Administrador crea proveedores desde el formulario de OC y los consulta en el selector.


