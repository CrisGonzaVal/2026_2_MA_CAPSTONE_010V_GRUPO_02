# Feature 013: Ciclo de vida del ticket

> **Nota de vigencia (19/Oct/2026):** este documento describe la feature tal como
> se cerró. Las migraciones que cita (`database/migraciones/*`) se retiraron del
> repo en la consolidación de la base: hoy `database/` solo tiene
> `01_esquema.sql` y `02_datos_semilla.sql`, y la base se reconstruye con
> `docker compose down -v` + `up -d`. La evidencia y las decisiones siguen siendo
> válidas; los nombres de archivos citados son históricos. Los tests gated
> citados (`test_ciclo_vida_ticket_postgres_013.py` y sus casos de migración)
> conservan solo las pruebas de instalación limpia y del token de versión; los
> casos de migración se retiraron junto con los scripts.

**Estado:** aprobada y cerrada (19/Oct/2026; enmienda del 25/Nov/2026 verificada y cerrada) — con las enmiendas incorporadas: D-4/AC-26 (terminalidad por nombre en cualquier catálogo), AC-18 (403 de matriz vs 404 de ocultamiento), AC-27 (05/Nov/2026: alta fija en `Pendiente` y prioridad `Media`) y AC-28…AC-49 (25/Nov/2026: aprobación del Administrador, etiqueta de proceso, responsables, «Terminados» y confirmación de entrega).  
**Release:** 2.0 — Sprint 6
**Tipo:** Evolución del ciclo de vida del ticket y auditoría

## 1. Problema

El flujo de tickets cubre el camino feliz —emitir, mover por el tablero, despachar— pero no
admite los desvíos reales de la operación diaria:

- **No se puede cancelar un ticket.** Una solicitud emitida por error o que dejó de necesitarse
  solo avanza o queda estancada en `Pendiente`; contamina el tablero, infla el conteo de tickets
  activos del dashboard y nadie puede retirarla con una explicación.
- **No hay rechazo.** Bodega o el Administrador no pueden declinar una solicitud dejando constancia
  del motivo; la única "negativa" disponible es no tocar el ticket.
- **No se puede editar.** Un asunto mal escrito o una cantidad equivocada obligan a emitir un
  ticket nuevo y abandonar el anterior, duplicando la cola.
- **No hay auditoría del ciclo de vida.** El ticket guarda solo su estado actual (y `fecha_cierre`
  cuando se cierra por despacho); nadie puede responder "¿quién movió este ticket, cuándo y por
  qué?". La Feature 005 declaró además que no persiste la autoría del despacho.
- **La vista de detalle está fuera de alcance desde la Feature 004:** los ítems, las cantidades
  entregadas, el historial y el contexto completo del ticket no son visibles en ninguna parte; la
  tarjeta muestra solo lo necesario para mover la columna.

## 2. Objetivo

Incorporar un único estado terminal `Anulado` que absorba la anulación del Solicitante y el
rechazo de Bodega/Administrador —ambos con motivo obligatorio—; permitir editar el ticket
mientras está en `Pendiente`; registrar cada transición en un historial inmutable (quién, cuándo,
de qué estado a qué estado y por qué); y habilitar la vista de detalle del ticket, sin debilitar
la reserva del cierre por despacho (Feature 005) ni el significado de `fecha_cierre`
(Feature 004).

## 3. Alcance

### Dentro

- Estado terminal nuevo `Anulado` en el catálogo `estado_ticket` (replicado por tenant desde la
  010), presente en **toda** instalación: estructura y semilla de instalación nueva, constructor
  de tenants y migración operacional idempotente bajo `database/migraciones/` con token de
  versión `013.1`.
- Anulación de ticket con motivo obligatorio, operada por el dueño Solicitante y por el
  Administrador de la institución.
- Rechazo de ticket con motivo obligatorio, operado por el Bodeguero y por el Administrador.
- Ambas operaciones admitidas desde `Pendiente` y `EnRevision` (ambos inclusive).
- Edición de asunto, descripción, prioridad e ítems detallados mientras el ticket está en
  `Pendiente`, operada por el dueño Solicitante y por el Administrador.
- Historial de transiciones del ticket: fila por transición con actor, marca de tiempo, estado de
  origen, estado de destino y motivo; toda mutación de estado lo registra.
- Vista de detalle del ticket (cabecera, ítems con cantidades, fechas e historial) y todas las
  acciones del ciclo de vida disponibles según estado y rol: transiciones del flujo lineal,
  edición, anulación y rechazo (D-14).
- Tablero Kanban de solo lectura: sin botones de "avanzar"/"retroceder" (derogados de la 004
  en su capa de UI); cada tarjeta ofrece una acción "Gestionar" que abre la vista de detalle
  del ticket, y el tablero añade la columna `Anulado` (D-14).
- Reglas de flujo actualizadas: `Cerrado` y `Anulado` son los dos estados terminales, reconocidos
  por nombre; `Anulado` queda fuera de la secuencia lineal del cambio de estado.
- Ajuste requerido del KPI de "tickets activos" del dashboard (Feature 009) para excluir el
  estado nuevo.
- Contrato de API y matriz de permisos **aditiva** para las operaciones nuevas, con el patrón de
  ocultamiento y códigos de las Features 007/008/011/012.

### Fuera

- Reabrir tickets en `Cerrado` o `Anulado`: ambos son terminales por nombre canónico y no
  admiten salida en ningún catálogo (D-4); la terminalidad no depende de la posición en el
  catálogo.
- Anular o rechazar desde `EnCurso`: el único cierre válido en `EnCurso` sigue siendo el
  despacho transaccional de la Feature 005.
- Editar tickets fuera de `Pendiente`, o editar el estado, el solicitante, la sede instantánea o
  la institución de un ticket.
- Borrado físico de tickets o del historial, y reescritura de filas del historial.
- Migración o reconstrucción de las transiciones ocurridas antes de esta feature.
- Notificaciones, informes, aprobación multi-ronda o flujos con más de un aprobador.
- Operar transiciones, edición, anulación o rechazo desde el tablero Kanban: el tablero es de
  solo lectura (su única acción es abrir el detalle); toda mutación del ciclo de vida se opera
  en la vista de detalle (D-14).
- CRUD del catálogo de estados; cambios a Clerk, a la matriz previa (solo se agregan filas) o al
  despacho de la 005.

## 4. Decisiones

### D-1 — Un único estado terminal nuevo, `Anulado`, compartido por anulación y rechazo

La anulación del Solicitante y el rechazo de Bodega/Administrador llevan al **mismo** estado
`Anulado`; lo que distingue un caso del otro es el actor y el motivo registrados en el historial,
no una fila de catálogo aparte.

**Por qué:** dos estados terminales equivalentes partirían el tablero, el catálogo y los conteos
en dos vocabularios para el mismo significado ("este ticket no se va a despachar"), repitiendo
exactamente la divergencia de vocabulario que la Feature 004 eliminó. El motivo es un dato de la
transición, no una etapa del flujo.

### D-2 — `Anulado` entra al catálogo replicado por tenant, con presencia obligatoria en toda instalación

El estado nuevo debe existir en la estructura y la semilla de instalación nueva, en el
constructor de tenants (cada esquema tenant recibe el catálogo completo) y en una migración
operacional idempotente bajo `database/migraciones/` para bases existentes, que eleva el token
de versión de control y tenants a `013.1` con el mismo procedimiento de las 011/012.

**Por qué:** desde la Feature 010 el catálogo de estados es local a cada tenant y el
enrutamiento exige igualdad exacta de versión. Un estado presente en unas instalaciones y no en
otras produciría comportamientos distintos (un tenant sin `Anulado` rechazaría las anulaciones)
y rompería el control de versión que protege ese desajuste.

### D-3 — Anulación y rechazo solo desde `Pendiente` y `EnRevision`

Hasta `EnRevision` el ticket es una intención sin preparación física. Desde `EnCurso` el ticket
representa material en preparación y su único cierre válido es el despacho transaccional de la
005, que rebaja stock y audita en la misma transacción.

**Por qué:** permitir un cierre sin despacho desde `EnCurso` dejaría el ticket terminado sin la
salida de inventario correspondiente, contra `constitucion.md` §3 (Consistencia Transaccional);
la 005 reservó exactamente ese paso para impedirlo.

### D-4 — `Anulado` queda fuera de la secuencia lineal; los terminales se reconocen por nombre

La 004 gobierna el flujo por ordinalidad (un paso entre contiguos; el último estado del catálogo
es terminal). Con `Anulado` añadido al final del catálogo, la regla ordinal convertiría a
`Cerrado` en estado no-terminal y habilitaría, según el catálogo, el paso contiguo `Cerrado →
Anulado` (canónico) o una transición de salida desde `Cerrado` (catálogo degenerado). Esta
feature declara, **en interpretación literal de esta decisión**: `Cerrado` y `Anulado` son los
dos estados terminales, reconocidos por su **nombre canónico** (misma resolución que el cierre
de la 004, D-3) y **nunca** por su posición en el catálogo; ninguno de los dos admite
**ninguna** transición de salida vía `PATCH /estado`, en **cualquier** catálogo (409); el
cambio de estado tampoco puede llevar **a** `Anulado` (409 con detalle que dirige a la operación
de anulación o rechazo correspondiente); el 409 de salida desde `Cerrado` declara que el cierre
es definitivo y que el despacho transaccional de la 005 es el único camino a él; y `Anulado`
solo se alcanza por anulación o rechazo, que exigen motivo.

**Derogación adicional de la 004 (patrón que la propia 004 usó con la 005, y que esta spec ya
usa en D-14 para la UI):** la regla de terminalidad **ordinal** del D-2 de
`004-tablero-kanban/spec.md` ("el último estado del orden del catálogo es terminal") y su
comportamiento de salida/retroceso desde el último estado quedan **sustituidos**, en el dominio
del ciclo de vida de tickets, por la resolución por nombre canónico: `Cerrado` es terminal
aunque no sea el último del catálogo, y ningún otro estado lo es por ocupar la última
posición. En consecuencia, el caso degenerado del test de la 004
`test_reentrar_en_cerrado_conserva_la_fecha_original` (`backend/tests/funcional/integracion/test_tablero_kanban.py`),
que exige que un `Cerrado` que no es el último del catálogo admita salida (`Cerrado → Archivado`
= 200), **queda derogado**: esa misma petición responde hoy 409. La 004 permanece sin editar
como registro histórico de su release; esta enmienda regula el comportamiento vigente.

**Por qué:** conserva el flujo lineal vigente para los cuatro estados operativos, deroga solo lo
imprescindible de la 004 y no depende de la posición del estado en el catálogo. La terminalidad
ordinal, aplicada al catálogo canónico (`…, Cerrado, Anulado`), dejaba a `Cerrado` con salida
hacia atrás (`Cerrado → EnCurso`, un paso) y permitía que un ticket **ya despachado** volviera a
un estado despachable para despacharse de nuevo —doble rebaja de stock—, rompiendo la reserva de
cierre de la 005 y `constitucion.md` §3 (Consistencia Transaccional).

### D-5 — La anulación no sella `fecha_cierre` ni toca stock; el historial es la fuente de verdad del ciclo de vida

`fecha_cierre` conserva su significado vigente (004 D-3/D-4): cierre por despacho/estado
`Cerrado`. Un ticket anulado queda con `fecha_cierre` **nula**; la fecha de su anulación se
registra en la fila del historial (actor, instante y motivo), que pasa a ser la fuente de verdad
del ciclo de vida completo del ticket. La anulación no escribe movimientos de inventario.

**Por qué:** sellar `fecha_cierre` en una anulación haría que "fecha de cierre" signifique dos
cosas —entregado vs. cancelado—, rompería la regla "todo ticket en `Cerrado` tiene fecha" y
deformara cualquier lectura que derive de esa columna. Agregar una segunda columna de fecha al
ticket sería redundante con el historial, que ya registra el instante exacto de cada transición.
Y no hay movimiento que auditar porque la anulación no mueve stock (`constitucion.md` §2 cubre
los cambios de inventario; aquí no los hay).

### D-6 — Motivo obligatorio, no vacío y de longitud acotada

Anulación y rechazo exigen un motivo de longitud máxima acotada (la misma escala de la
descripción del ticket). Sin motivo válido no se escribe nada; el motivo se persiste en la fila
del historial de esa misma transición.

**Por qué:** el motivo es la única distinción sustantiva entre anulación y rechazo para el
futuro lector del historial, y un ticket descartado sin explicación rompe la trazabilidad del
negocio (¿por qué no se despachó?).

### D-7 — Dos operaciones de API, no una genérica

`anulación` (dueño Solicitante y Administrador) y `rechazo` (Bodeguero y Administrador) son
operaciones distintas hacia el mismo estado.

**Por qué:** los conjuntos de roles autorizados difieren —el Bodeguero no "anula" y el
Solicitante no "rechaza"—; con una sola operación la matriz tendría que conceder todos los roles
juntos o perder la distinción, y el contrato público perdería el significado de cada acción. Que
el estado sea compartido no obliga a compartir la operación.

### D-8 — Autorización por la matriz aditiva y ocultamiento 404, como en 007/008/011/012

El Solicitante solo opera sus propios tickets; Administrador y Bodeguero, los de su institución.
Un ticket inexistente y uno fuera del alcance del rol responden **404 idéntico**, sin revelar
existencia (mismo patrón que el verificado alcance de ticket vigente). El ocultamiento 404
aplica solo a un rol **concedido en la operación** pero fuera del alcance del recurso; una
operación no concedida al rol —p. ej. el Solicitante en `rechazo`— responde **403** según la
matriz, evaluada antes de mirar el recurso y sin revelar si este existe. Superadmin **no opera**
tickets: 403 en toda escritura (anulación, rechazo, edición), y lectura de detalle e historial
con su alcance global actual, igual que su lectura vigente de la lista de tickets. Las
operaciones nuevas se agregan a la matriz (una operación ausente no concede a nadie) y quedan
sujetas al gating de capacidades por institución de la 012.

**Por qué:** consistencia con la matriz y los códigos ya establecidos; la 012 excluyó al
Superadmin de la operación de tickets solo por UI/guard, y esta feature no cambia eso: su
frontera sigue siendo la matriz.

### D-9 — Edición completa, solo en `Pendiente`, con validación íntegra antes de escribir

Campos editables: asunto, descripción, prioridad y el **conjunto completo** de ítems detallados
(reemplazo del conjunto, con las mismas validaciones del alta: productos de la institución,
cantidades positivas, al menos un ítem). Autores: el dueño Solicitante y el Administrador de la
institución. Fuera de `Pendiente` → 409 sin cambios; una validación fallida no escribe nada, ni
cabecera ni ítems parciales. No se editan el estado, el solicitante, la sede instantánea ni la
institución.

**Por qué:** en `Pendiente` el ticket todavía no fue revisado ni preparado; editar después
cambiaría la base sobre la que Bodega ya trabajó. El Administrador comparte la edición porque
administra la institución y debe poder corregir una solicitud mal emitida por cualquiera de ella;
el Bodeguero no la recibe: su rol interviene en la preparación y el despacho, no en el contenido
de la solicitud.

### D-10 — Historial de transiciones inmutable que registra toda transición desde esta feature

Estructura nueva de historial con una fila por transición: ticket, estado de origen, estado de
destino, actor, marca de tiempo y motivo. Toda mutación de estado lo registra: el alta crea la
fila de creación; el cambio de estado de la 004, el despacho de la 005 y la anulación/rechazo de
esta feature, cada una con su fila. El historial es de solo lectura por API: sin operación de
edición, borrado o reescritura. Las transiciones anteriores a esta feature **no se migran ni
reconstruyen**.

**Por qué:** la Trazabilidad Absoluta exige poder responder quién, cuándo, de qué a qué y por
qué; el cambio de estado y su fila de historial ocurren en la misma transacción
(`constitucion.md` §3). No se reconstruyen transiciones pasadas porque no existe registro
persistido de su actor ni de su estado anterior —la 005 declaró expresamente que no persiste
autoría— y fabricar esas filas inventaría trazabilidad: las instalaciones existentes empiezan con
el historial de cada ticket vacío o desde su primera transición posterior, sin datos ficticios.

### D-11 — Un ticket nuevo no puede nacer en `Anulado`

La alta de la 003 permite elegir estado inicial; `Anulado` queda excluido de esa elección y se
rechaza si llega. `Cerrado` sigue admitido con su sellado de fecha (004 AC-17), intacto.

**Por qué:** un ticket nacido anulado no tiene quién lo anulara ni por qué; su historia
arrancaría mintiendo y sin el motivo que D-6 exige a toda anulación.

### D-12 — El KPI de "tickets activos" del dashboard excluye también `Anulado`

La fórmula vigente de la 009 cuenta como activo todo ticket cuyo estado no es exactamente
`Cerrado`; con el estado nuevo, un ticket anulado se contaría como activo para siempre. La regla
pasa a excluir **ambos** nombres canónicos (`Cerrado` y `Anulado`), sin ids fijos, conservando
el ámbito por rol.

**Por qué:** un KPI que presenta como pendiente de atención un ticket que nunca se despachará
deforma el indicador con que el negocio decide. Cambiar la fórmula es requisito de esta feature,
no un refactor opcional.

### D-13 — La vista de detalle sustituye el "fuera de alcance" de la 004

El detalle muestra la cabecera (asunto, prioridad, solicitante y departamento, sede, fechas de
creación y —si existe— de cierre), los ítems con cantidades solicitadas y entregadas, y el
historial completo. Las acciones (avanzar o retroceder en el flujo lineal, editar, anular,
rechazar) se ofrecen solo al rol autorizado y solo en los estados que las admiten; el tablero
no ofrece ninguna mutación (D-14).

**Por qué:** la 004 dejó el detalle fuera de alcance porque las tarjetas bastaban para mover el
flujo; el ciclo de vida completo —motivo, autoría, ítems— no se puede operar ni auditar sin esa
vista.

### D-14 — El tablero Kanban pasa a solo lectura; la acción "Gestionar" abre el detalle

El tablero deja de ofrecer los botones "avanzar"/"retroceder" de la Feature 004: sus tarjetas
son informativas (incluida la nueva columna `Anulado`) y cada una ofrece una única acción —
"Gestionar"— que abre la vista de detalle del ticket, donde viven **todas** las operaciones del
ciclo de vida: las transiciones del flujo lineal (invocando `PATCH /tickets/{id}/estado`), la
edición en `Pendiente`, la anulación y el rechazo con motivo. El backend de transiciones **no
cambia**: `PATCH /estado` conserva íntegro su contrato de la 004/005; lo único que cambia es
el punto de invocación. **Deróganse parcialmente, en su capa de UI,** los AC-9, AC-10, AC-12,
AC-19 y AC-20 de `004-tablero-kanban/spec.md` (transiciones por botón en el tablero y su
feedback 409/404 en el tablero), y del D-2 de esa spec se deroga que "su tarjeta no ofrece
ningún control" como regla del tablero —hoy ninguna tarjeta ofrece controles—, conservándose
su regla de backend (flujo lineal de un paso, terminal por nombre); del D-7 se deroga el
movimiento y la reconsulta de la tarjeta en el tablero, trasladándose la exigencia de mensaje
accesible, sin doble envío y con reconsulta a la vista de detalle (AC-24).

**Por qué:** con el detalle disponible, el ciclo de vida completo no cabe en una tarjeta;
concentrar todas las mutaciones en una sola vista evita dos superficies de escritura con reglas
distintas, hace que el tablero sea seguro para quien solo supervisa la cola y reduce el riesgo
de una transición accidental desde el tablero. Decisión del usuario incorporada antes del plan.

**Derogación parcial de la 004 (patrón que la propia 004 usó con la 005):** los AC y
decisiones de UI listados quedan derogados solo en lo que exigía controles de transición en el
tablero; sus reglas de backend —flujo lineal, orden de validación ticket→estado→flujo, sellado
de `fecha_cierre` y cierre reservado al despacho— permanecen intactas y ahora se verifican
desde la vista de detalle.

## 5. Reglas del flujo

La secuencia lineal de la 004 se conserva para los estados operativos; `Anulado` queda fuera de
ella y solo se alcanza por anulación o rechazo con motivo. La terminalidad de `Cerrado` y
`Anulado` se resuelve **por nombre canónico**, no por ordinalidad del catálogo (D-4): ninguno de
los dos admite salida en ningún catálogo. Estas transiciones se operan
**exclusivamente desde la vista de detalle** (D-14), que invoca `PATCH /estado`; el tablero de
solo lectura no las invoca:

| Desde | Avanzar (cambio de estado) | Retroceder (cambio de estado) | Anular | Rechazar |
|---|---|---|---|---|
| Pendiente | EnRevision | — (es el primero) | Sí, con motivo | Sí, con motivo |
| EnRevision | EnCurso | Pendiente | Sí, con motivo | Sí, con motivo |
| EnCurso | Cerrado (solo vía despacho de la 005) | EnRevision | No (409) | No (409) |
| Cerrado | — (terminal por nombre, en cualquier catálogo) | — (terminal, sin salida: 409) | No (409) | No (409) |
| Anulado | — (terminal) | — (terminal) | — (terminal) | — (terminal) |

Invariantes y orden de validación (extiende el D-8 de la 004):

1. El cambio de estado jamás lleva a `Anulado`, ni sale de `Anulado` ni de `Cerrado`: 409 en
   cualquiera de esos casos y **en cualquier catálogo**, porque la terminalidad se resuelve por
   nombre canónico y no por posición (D-4). El detalle desde `Anulado` dirige a la operación de
   anulación o rechazo correspondiente; el detalle desde `Cerrado` declara que el cierre es
   definitivo y que el despacho de la 005 es el único camino a él.
2. Ante anulación o rechazo el orden es: (1) el ticket existe y está en el alcance del rol →
   **404** (inexistente y ajeno, idénticos); (2) el estado actual admite la operación → **409**;
   (3) el motivo es válido → **422**. Para el cambio de estado se conserva el orden de la 004:
   ticket/alcance (404), estado pedido (404), flujo (409).
3. Ningún rechazo deja escritura parcial: el cambio de estado + su fila de historial, y la
   edición de cabecera + sus ítems, son operaciones atómicas (una sola o ninguna).
4. `Anulado` no sella `fecha_cierre` y no escribe stock ni movimientos; `Cerrado` sigue
   sellando `fecha_cierre` por todos los caminos vigentes (004/005 intactos).
5. Un ticket en `Anulado` no es despachable (409, estado no elegible, ya cubierto por la 005);
   un ticket en `Cerrado` tampoco puede volver a un estado despachable, porque no admite salida
   (invariante 1): no hay camino a una segunda rebaja de stock.

## 6. Contrato de la API

Todas las operaciones son nuevas y aditivas en la matriz central; conservan el patrón vigente
de respuestas, evaluadas en este orden: 401 sesión ausente; 403 rol sin permiso en la matriz de
la operación (o capacidad institucional deshabilitada, 012), resuelto **antes** de
inspeccionar el recurso; 404 inexistente o fuera de alcance del rol concedido (idénticos);
409 conflicto de precondición/flujo; 422 entrada inválida.

### `POST /api/v1/tickets/{ticket_id}/anulacion`

Éxito: **200** con el ticket en `Anulado`, sin `fecha_cierre` y con su historial ya registrando
la transición. Payload: motivo obligatorio. Actores: el dueño Solicitante y el Administrador de
la institución. 409 si el estado actual no admite la operación (EnCurso, Cerrado o ya Anulado)
o si el catálogo del tenant no contiene el estado `Anulado`; 422 si el motivo falta, está vacío
o excede la longitud.

### `POST /api/v1/tickets/{ticket_id}/rechazo`

Mismo contrato, códigos y payload que la anulación; actores: el Bodeguero y el Administrador.

### `PUT /api/v1/tickets/{ticket_id}`

Edición del ticket en `Pendiente` con payload equivalente al de alta (asunto, descripción,
prioridad e ítems detallados completos). Éxito: **200** con el ticket actualizado y su nuevo
conjunto de detalles. 409 si el ticket no está en `Pendiente`; 404 por referencia inexistente o
ajena; 422 por forma inválida. Actores: el dueño Solicitante y el Administrador.

### `GET /api/v1/tickets/{ticket_id}`

Detalle del ticket: cabecera, ítems con cantidades y fechas. **200**; 404 inexistente o fuera de
alcance. Legible por los cuatro roles con su alcance vigente (Solicitante: los suyos;
Administrador y Bodeguero: su institución; Superadmin: global).

### `GET /api/v1/tickets/{ticket_id}/historial`

Lista de transiciones del ticket con estado de origen y destino, actor, marca de tiempo y
motivo, en orden determinista (más reciente primero, con desempate estable). **200**, lista
vacía si no hay transiciones; 404 inexistente o fuera de alcance; operación de solo lectura sin
variantes de escritura.

### `PATCH /api/v1/tickets/{ticket_id}/estado` — incorporación vigente

Conserva su contrato de la 004/005 e incorpora: cualquier petición cuyo destino sea `Anulado` o
cuyo origen sea `Anulado` responde **409** con detalle que dirige a la operación de anulación o
rechazo, sin modificar el ticket; y cualquier petición cuyo origen sea `Cerrado` responde
**409** con un detalle que declare que el cierre es definitivo y que el despacho transaccional
de la 005 es el único camino a `Cerrado`, sin modificar el ticket — **en cualquier catálogo**,
porque la terminalidad se resuelve por nombre canónico y no por posición (D-4, sustituyendo el
comportamiento ordinal de la 004). Sigue siendo el mecanismo de transición del flujo lineal de
los cuatro estados operativos, pero ahora se invoca **desde la vista de detalle** (D-14): el
tablero de solo lectura no lo invoca y su contrato no cambia.

*Enmienda post-cierre (25/Nov/2026): esta operación se conserva como contrato de **legado** y
**no evalúa stock**; la UI ya no la invoca y la aprobación del Administrador
(`POST /tickets/{id}/aprobacion`) es la que lleva el pedido a `EnCurso`. Se concede **solo al
Administrador**; el resto del contrato de transición no cambia. Ver §9.*

## 7. Criterios de aceptación

### Reglas de flujo y estados

- [x] **AC-1** DADO QUE un ticket propio del Solicitante está en `Pendiente` o `EnRevision`,
      CUANDO el Solicitante lo anula con motivo válido, ENTONCES responde 200, el ticket queda
      en `Anulado` con `fecha_cierre` nula, su stock y sus movimientos quedan intactos, y el
      historial registra una fila con el actor, la marca de tiempo, `EnRevision/Pendiente →
      Anulado` y el motivo literal.
  - **Evidencia:** `backend/tests/funcional/e2e/test_ciclo_vida_flujo_013.py` — `test_anulacion_desde_pendiente_responde_200_con_historial_ac_1` y `test_anulacion_desde_en_revision_tambien_es_200_ac_1`; recorrido 4200 con escritura real: `evidencia/README.md` §3.1 #2 (ticket 13 → `Anulado`, `fecha_cierre` NULL, stock/movimientos intactos y fila con motivo literal, todo verificado por SQL).
- [x] **AC-2** SI el ticket está en `EnCurso`, `Cerrado` o ya en `Anulado`, ENTONCES la
      anulación responde 409 y no modifica el ticket ni agrega filas al historial.
  - **Evidencia:** `test_ciclo_vida_flujo_013.py::test_anulacion_desde_estado_inadmisible_responde_409_sin_efectos_ac_2`; recorrido `evidencia/README.md` §3.3 #12–#14 (409 desde `EnCurso`/`Cerrado`/`Anulado`, sin filas nuevas por SQL).
- [x] **AC-3** DADO QUE un ticket de la institución está en `Pendiente` o `EnRevision`,
      CUANDO un Bodeguero o el Administrador lo rechaza con motivo válido, ENTONCES responde 200
      con el ticket en `Anulado` y el historial registrando actor y motivo; SI el estado actual
      no admite el rechazo, ENTONCES responde 409 sin efectos.
  - **Evidencia:** `test_ciclo_vida_flujo_013.py` — `test_rechazo_por_bodeguero_desde_pendiente_es_200_ac_3`, `test_rechazo_por_administrador_desde_en_revision_es_200_ac_3` y `test_rechazo_desde_en_curso_responde_409_sin_efectos_ac_3`; recorrido `evidencia/README.md` §3.1 #7 (rechazo del Bodeguero con motivo literal → `Anulado`) y §3.3 #15.
- [x] **AC-4** MIENTRAS un ticket esté en `Anulado`, NINGUNA operación puede sacarlo de ese
      estado; el cambio de estado hacia `Anulado` o desde `Anulado` responde 409 con un detalle
      que dirija a la operación correspondiente, y el estado nuevo es terminal también para el
      flujo lineal (sin avanzar ni retroceder). La misma imposibilidad de salida aplica a
      `Cerrado` en cualquier catálogo (AC-26).
  - **Evidencia:** `test_ciclo_vida_flujo_013.py` — `test_patch_estado_no_lleva_a_anulado_y_dirige_a_la_operacion_ac_4`, `test_patch_estado_no_sale_de_anulado_ac_4` y `test_alta_en_anulado_responde_409_sin_ticket_d11` (D-11); recorrido `evidencia/README.md` §3.3 #16, #17 y #20. La salida desde `Cerrado` en cualquier catálogo queda cubierta por el AC-26.
- [x] **AC-5** La transición `EnCurso → Cerrado` sigue reservada al despacho transaccional de
      la 005 con su 409 y su detalle literal intactos; el despacho registra su transición en el
      historial; un ticket en `Anulado` no se puede despachar (409, estado no elegible).
  - **Evidencia:** `test_ciclo_vida_flujo_013.py` — `test_en_curso_a_cerrado_sigue_reservado_al_despacho_ac_5`, `test_despacho_registra_su_transicion_en_el_historial_ac_5` y `test_despacho_de_un_anulado_responde_409_sin_movimientos_ac_5`; recorrido `evidencia/README.md` §3.2 #10 (409 con el literal de la 005) y #11 (despacho con fila de historial y rebaja de stock).
- [x] **AC-6** DADO QUE un ticket queda en `Cerrado` por cualquier camino vigente (alta,
      cambio de estado o despacho), ENTONCES conserva `fecha_cierre` no nula; DADO QUE un ticket
      queda en `Anulado`, ENTONCES su `fecha_cierre` permanece nula y la anulación no escribe
      movimientos de inventario.
  - **Evidencia:** `test_ciclo_vida_flujo_013.py` — `test_alta_en_cerrado_sella_fecha_cierre_ac_6` y `test_despacho_sella_fecha_cierre_ac_6`; recorrido `evidencia/README.md` §3.1 #2 (anulado con fecha NULL y stock/movimientos intactos por SQL) y §3.2 #11 (despacho con `fecha_cierre` sellada).
- [x] **AC-7** ANTE una anulación o un rechazo con varios problemas simultáneos, el orden de
      respuesta es 404 (ticket inexistente o fuera de alcance, con detalle idéntico), luego 409
      (estado actual inadmisible) y luego 422 (motivo inválido); el resultado no depende de la
      bandera de la petición.
  - **Evidencia:** `test_ciclo_vida_flujo_013.py` — `test_orden_404_ante_422_con_ticket_inexistente_y_motivo_invalido_ac_7`, `test_orden_409_ante_422_con_estado_inadmisible_y_motivo_invalido_ac_7`, `test_422_de_motivo_invalido_no_modifica_nada_ac_7` y `test_409_de_estado_inadmisible_con_motivo_valido_ac_7`; recorrido `evidencia/README.md` §3.3 #18 (404 idéntico), #12 (409) y #19 (422 sin efectos por SQL).

### Motivo

- [x] **AC-8** SI el motivo de anulación o rechazo falta, está vacío o excede la longitud
      máxima, ENTONCES responde 422 sin modificar estado, fechas ni historial; CON un motivo
      válido, ENTONCES la fila del historial de esa transición contiene el motivo literal.
  - **Evidencia:** `backend/tests/funcional/integracion/test_ciclo_vida_motivo_013.py` (4 tests AC-8: `test_motivo_faltante_responde_422_ac_8`, `test_motivo_vacio_responde_422_ac_8`, `test_motivo_sobre_la_longitud_maxima_responde_422_ac_8`, `test_motivo_en_el_limite_maximo_es_aceptado_y_se_persiste_literal_ac_8`); recorrido `evidencia/README.md` §3.1 #2/#7 (motivos literales persistidos por SQL) y §3.3 #19 (422 sin efectos).

### Historial de transiciones

- [x] **AC-9** Toda mutación de estado registra exactamente una fila de historial: la creación
      del ticket (estado de origen nulo, destino = estado inicial, actor = creador), el cambio
      de estado de la 004, el despacho de la 005, la anulación y el rechazo. Cada fila expone
      ticket, estado de origen, estado de destino, actor, marca de tiempo y motivo (nulo cuando
      la operación no lo exige).
  - **Evidencia:** `backend/tests/funcional/integracion/test_ciclo_vida_historial_013.py` — `test_alta_registra_fila_de_creacion_con_origen_nulo_ac_9`, `test_cambio_de_estado_suma_exactamente_una_fila_ac_9` y `test_anulacion_y_rechazo_suman_exactamente_una_fila_ac_9`; recorrido `evidencia/README.md` §3.1 #1/#4, §3.2 #9 (1 fila por PATCH) y #11 (fila del despacho).
- [x] **AC-10** El historial es de solo lectura: no existe operación pública de creación,
      edición o borrado de sus filas fuera de las transiciones mismas, y su lectura ordena de
      forma determinista (más reciente primero, desempate estable).
  - **Evidencia:** `test_ciclo_vida_historial_013.py` — `test_orden_mas_reciente_primero_con_desempate_por_id_ac_10` y `test_historial_no_expone_operaciones_de_escritura_ac_10` (el OpenAPI no publica variantes de escritura del historial); recorrido `evidencia/README.md` §3.1 #4 (orden `fecha_transicion DESC, id DESC`).
- [x] **AC-11** DADO QUE un cambio de estado (o una anulación/rechazo) se acepta, ENTONCES el
      ticket y su fila de historial quedan persistidos juntos: si la fila no puede registrarse,
      el estado no cambia (y viceversa), sin efectos parciales.
  - **Evidencia:** `test_ciclo_vida_historial_013.py` — `test_transicion_aceptada_persiste_estado_y_fila_juntos_ac_11` y `test_si_la_fila_no_puede_registrarse_el_estado_no_cambia_ac_11` (inserción de historial forzada a fallar).
- [x] **AC-12** El historial NO contiene filas inventadas para transiciones ocurridas antes de
      esta feature: un ticket creado antes de la 013 sin transiciones posteriores muestra su
      historial vacío (o solo las filas de sus transiciones reales posteriores); no se migra ni
      se reconstruye autoría o motivo de transacciones pasadas.
  - **Evidencia:** `test_ciclo_vida_historial_013.py` — `test_ticket_legado_sin_transiciones_muestra_historial_vacio_ac_12` y `test_anulacion_de_legado_no_inventa_fila_de_creacion_ac_12`; gated `test_ciclo_vida_ticket_postgres_013.py::test_instalacion_nueva_no_siembra_historial_fabricado`; en el recorrido los tickets 6–12 pre-013 siguen sin filas inventadas (`evidencia/README.md` §3.4: 8 filas, solo del recorrido).

### Edición en Pendiente

- [x] **AC-13** DADO QUE un ticket propio del Solicitante (o de su institución, para el
      Administrador) está en `Pendiente`, CUANDO se edita con payload válido, ENTONCES responde
      200 con asunto, descripción, prioridad y detalles reflejados tal como se enviaron, con el
      conjunto de ítems reemplazado por completo; el estado, el solicitante, la sede y la
      institución no cambian.
  - **Evidencia:** `backend/tests/funcional/integracion/test_ciclo_vida_edicion_013.py` — `test_edicion_en_pendiente_reemplaza_cabecera_y_detalles_ac_13` y `test_edicion_conserva_estado_solicitante_sede_e_institucion_ac_13`; recorrido `evidencia/README.md` §3.1 #6 (PUT del ticket 14: ítems previos borrados, cabecera nueva y estado/sede/solicitante intactos por SQL).
- [x] **AC-14** SI el ticket no está en `Pendiente`, ENTONCES la edición responde 409 y no
      modifica cabecera ni detalles.
  - **Evidencia:** `test_ciclo_vida_edicion_013.py::test_edicion_fuera_de_pendiente_responde_409_sin_efectos_ac_14`; recorrido `evidencia/README.md` §3.3 #21 (PUT sobre ticket `Anulado` → 409).
- [x] **AC-15** SI la edición trae una referencia inválida (prioridad o producto inexistente,
      producto de otra institución, cantidad no positiva, detalles vacíos), ENTONCES responde
      404 o 422 según el caso y **no** escribe ni la cabecera ni ningún detalle: la validación
      completa del payload precede a la primera escritura (sin detalles parciales).
  - **Evidencia:** `test_ciclo_vida_edicion_013.py` (5 tests AC-15, todos con aserción de ausencia de escritura parcial): `test_edicion_con_prioridad_inexistente_responde_404_sin_escritura_ac_15`, `test_edicion_con_producto_inexistente_responde_404_sin_escritura_ac_15`, `test_edicion_con_producto_ajeno_responde_404_ocultado_sin_escritura_ac_15`, `test_edicion_con_cantidad_no_positiva_responde_422_sin_escritura_ac_15`, `test_edicion_con_detalles_vacios_responde_422_sin_escritura_ac_15`.
- [x] **AC-16** El Bodeguero y el Superadmin no pueden editar tickets (403); el Solicitante solo
      los suyos y el Administrador solo los de su institución; un ticket ajeno responde 404
      idéntico al inexistente.
  - **Evidencia:** `test_ciclo_vida_edicion_013.py` — `test_bodeguero_y_superadmin_no_pueden_editar_ac_16`, `test_solicitante_no_edita_ticket_ajeno_y_el_404_es_identico_ac_16`, `test_administrador_de_otra_institucion_edita_con_404_ocultado_ac_16` y `test_administrador_edita_tickets_de_su_institucion_ac_16`.

### Autorización

- [x] **AC-17** Las operaciones nuevas se declaran en la matriz central con exactamente estos
      roles: anulación (Solicitante, Administrador), rechazo (Bodeguero, Administrador), edición
      (Solicitante, Administrador), lectura de detalle e historial (los cuatro roles); el
      Superadmin obtiene 403 en toda escritura de ticket y una operación ausente de la matriz no
      concede permiso a nadie.
  - **Evidencia:** `backend/tests/funcional/integracion/test_ciclo_vida_autorizacion_013.py` (12 tests AC-17): matriz exacta (`test_matriz_tiene_exactamente_49_operaciones_ac_17`, `test_matriz_conserva_las_44_operaciones_previas_intactas_ac_17`, `test_matriz_declara_las_cinco_operaciones_con_los_roles_exactos_ac_17`), Superadmin sin escritura (`test_superadmin_no_obtiene_ninguna_escritura_nueva_ac_17`, `test_superadmin_obtiene_403_en_toda_escritura_nueva_ac_17`) y gating (`test_capacidad_kanban_apagada_bloquea_anulacion_y_rechazo_sin_mutar_ac_17`, `test_capacidad_tickets_apagada_bloquea_edicion_detalle_e_historial_ac_17`); contrato vivo: `/openapi.json` con **49 operaciones** v1 (51 totales con `GET /` y `/health`), las 5 nuevas aditivas con 401/403/404 (+409/422 en escrituras) — `evidencia/README.md` §4.
- [x] **AC-18** La autorización resuelve en dos pasos, y ninguno revela existencia: (a) SI la
      operación no concede el rol —p. ej. un Solicitante que intenta rechazar, o el Superadmin
      que intenta escribir—, ENTONCES responde 403 por la matriz (AC-17), **antes** de
      inspeccionar el recurso y sin indicar si el ticket existe; (b) DADO QUE el rol sí está
      concedido en la operación pero el ticket está fuera de su alcance —un Solicitante sobre
      un ticket ajeno en anulación o edición, o un Administrador/Bodeguero de otra
      institución—, ENTONCES la respuesta es 404 con detalle idéntico al de un ticket
      inexistente, sin revelar existencia por ninguna vía (lista, detalle, historial o
      mensajes de error).
  - **Evidencia:** `test_ciclo_vida_autorizacion_013.py` — `test_operar_ticket_ajeno_responde_404_identico_ac_18` (el caso `[rechazo]` se ejercita con el Administrador de la otra institución: tras la enmienda, un rol sin la operación —Solicitante en rechazo— recibe 403 matriz, no 404), `test_leer_ajeno_responde_404_identico_ac_18`, `test_rol_sin_permiso_de_escritura_recibe_403_ac_17` y `test_superadmin_obtiene_403_en_toda_escritura_nueva_ac_17`; recorrido `evidencia/README.md` §3.3 #18 (404 con detalle idéntico), #22 y #23 (403 sin mirar el recurso).
- [x] **AC-19** DADO QUE los cuatro roles consultan el detalle y el historial, ENTONCES cada
      uno recibe los tickets de su alcance vigente (Solicitante: propios; Administrador y
      Bodeguero: su institución; Superadmin: global); la lectura de detalle no concede al
      Superadmin ninguna capacidad de escritura.
  - **Evidencia:** `test_ciclo_vida_autorizacion_013.py` — `test_superadmin_lee_detalle_e_historial_ac_19`, `test_solicitante_lee_su_detalle_y_no_el_ajeno_ac_19` y `test_administrador_y_bodeguero_leen_el_detalle_de_su_institucion_ac_19` (más la verificación desechable contra BD real de T12: lector global 200 sin `DetachedInstanceError`); recorrido `evidencia/README.md` §3.1 #3–#4 (Solicitante) y §3.3 #24 (Superadmin global 200).

### Catálogo, instalación y versión

- [x] **AC-20** DADO una instalación nueva, ENTONCES el catálogo de estados incluye `Anulado`
      desde la estructura y la semilla, y el constructor de tenants lo replica en cada esquema;
      DADO una instalación existente, ENTONCES la migración operacional idempotente bajo
      `database/migraciones/` lo añade sin pérdida de datos, es re-ejecutable sin cambios y
      eleva el token de versión de control y de cada tenant existente a `013.1`.
  - **Evidencia:** gated `backend/tests/funcional/sistema/test_ciclo_vida_ticket_postgres_013.py` (7/7 en verde contra PG 16 sobre base desechable): `test_instalacion_nueva_replica_anulado_e_historial_en_control_y_tenants`, `test_instalacion_nueva_no_siembra_historial_fabricado`, `test_migracion_013_transiciona_012_1_preservando_datos_sin_fabricar_historial`, `test_migracion_013_es_idempotente`, `test_migracion_013_aborta_ante_estructura_parcial_sin_marcar_version`; estado real de `apt_erp` en `evidencia/README.md` §1 (versión `013.1`, quinta fila `Anulado`, respaldo previo `respaldos/apt_erp_pre_013.dump`).
- [x] **AC-21** Solo se enrutan tenants cuya versión es exactamente `013.1`; una versión
      distinta, ausente o duplicada deniega cerrado (patrón 010/011/012) y el catálogo
      replicado de todo tenant enrutado contiene el estado `Anulado` presente.
  - **Evidencia:** gated `test_ciclo_vida_ticket_postgres_013.py::test_tenant_en_012_1_deniega_con_el_objetivo_013_1` y `::test_el_codigo_apunta_a_la_version_013_1`; el recorrido entero operó sobre un tenant enrutado en `013.1` (`evidencia/README.md` §1).

### KPI del dashboard

- [x] **AC-22** El KPI de "tickets activos" del dashboard (009) excluye ahora los estados cuyo
      nombre canónico es `Cerrado` o `Anulado` (resolución por nombre, sin ids fijos): un
      ticket anulado no cuenta como activo para ningún rol; el resto de los KPI, el log de
      alertas y el ámbito por rol no cambian.
  - **Evidencia:** `backend/tests/funcional/integracion/test_ciclo_vida_dashboard_013.py` — `test_kpi_tickets_activos_excluye_anulado_por_nombre_ac_22`, `test_kpi_del_solicitante_no_cuenta_sus_anulados_ac_22` y `test_kpi_resto_del_dashboard_intacto_ac_22`; recorrido `evidencia/README.md` §3.3 #25 (`tickets_activos=3` para el Solicitante, contrastado con SQL por estado).

### Interfaz

- [x] **AC-23** DADO QUE un usuario autenticado accede al detalle de un ticket de su alcance,
      ENTONCES la vista muestra cabecera (asunto, prioridad, solicitante y departamento, sede y
      fechas), ítems con cantidades solicitadas y entregadas, y el historial completo; los
      estados vacíos y los errores son visibles y diferenciables.
  - **Evidencia:** `frontend/src/app/features/tickets/ticket-detalle.component.spec.ts` (27 specs, p. ej. `muestra cabecera con asunto, prioridad, estado, solicitante, departamento, sede y fechas`, `muestra los ítems con cantidades solicitadas y entregadas`, `muestra el historial completo con actor, de→a, instante y motivo`, `diferencia el historial vacío de un error`, `muestra un error accesible (role="alert") ante un 404 y permite reintentar`); `ng test` **323 SUCCESS** y `ng build` con chunk lazy `ticket-detalle-component` (T12); 4200 sirvió el chunk y 8080 lo sirve reconstruido (`evidencia/README.md` §1 y §8.2).
- [x] **AC-24** Toda mutación del ciclo de vida se opera desde la vista de detalle: avanzar o
      retroceder un paso en el flujo lineal según estado y rol; editar solo en `Pendiente` y
      solo para el dueño o el Administrador; anular (dueño/Administrador) y rechazar
      (Bodeguero/Administrador) solo en `Pendiente`/`EnRevision`, exigiendo motivo con
      confirmación previa; ninguna acción en `Cerrado` o `Anulado`. El tablero es de solo
      lectura: no ofrece controles de transición (ni de ninguna otra mutación); su única
      acción por tarjeta es "Gestionar", que abre el detalle del ticket, y añade la columna
      `Anulado` con sus tarjetas. Ante 404, 409 o 422 —al operar en el detalle o al abrir
      una tarjeta inexistente/ajena— se muestra un mensaje accesible (`role="alert"`), sin
      doble envío y reconsultando para reflejar el estado real del servidor.
  - **Evidencia:** `ticket-detalle.component.spec.ts` (acciones por estado/rol —p. ej. `Cerrado no ofrece ninguna acción y lo dice como estado terminal`—, `la confirmación exige motivo: vacío o en blanco no envía nada`, `no permite doble envío mientras el cambio de estado está en vuelo`, `muestra el 409 del servidor en un role="alert" y reconsulta la verdad del backend`) + `tickets.component.spec.ts` (`ofrece exactamente una acción «Gestionar» por tarjeta, sin controles de transición`, `surge del catálogo junto a las demás, con sus tarjetas`, `excluye Anulado de la elección de estado inicial`); humo 8080: `evidencia/README.md` §8.2 (chunk `TicketsComponent` con «Gestionar» y `TicketDetalleComponent` con «Historial de transiciones», servidos por HTTP).
- [x] **AC-25** Las suites de backend y frontend quedan en verde —incluidos los casos nuevos de
      flujo, autorización, historial, edición, migración (gated sobre PostgreSQL 16) y contrato
      `/openapi.json`— y el flujo se recorre en los dos puertos: 4200 con escritura real y 8080
      tras reconstruir la imagen (`AGENTS.md` §8.5–§8.6). Sin esto la feature no se cierra.
  - **Evidencia:** suites de cierre (T12): `pytest` SQLite **952 passed / 68 skipped / 0 failed**; gated PostgreSQL 16 **1020 passed / 0 skipped / 0 failed**; `ng test` **323 SUCCESS**; `ng build` limpio. Recorrido 4200 con escritura real: `evidencia/README.md` §3 (tickets 13–15 persistidos en `apt_erp`, migrada a `013.1`). Humo 8080 con imagen reconstruida: `evidencia/README.md` §8 (bundle `main-R6LIXDWJ.js`, `try_files` en `/tickets` y `/tickets/13`, API por proxy con token Clerk).

### Terminalidad por nombre (enmienda de D-4)

- [x] **AC-26** MIENTRAS un ticket esté en `Cerrado` o en `Anulado` —en el catálogo canónico o
      en **cualquier** catálogo degenerado—, NINGUNA operación de cambio de estado puede sacarlo
      de ese estado: `PATCH /estado` responde 409 sin modificar el ticket (el detalle de
      `Anulado` dirige a anulación/rechazo; el de `Cerrado`, a aceptar que el cierre es
      definitivo y que el despacho es el único camino a él). La reentrada en `Cerrado` es
      imposible: ninguna petición de cambio de estado puede llevar un ticket **a** `Cerrado`
      (el único camino vigente a ese estado sigue siendo el despacho transaccional de la 005),
      y, en consecuencia, un ticket ya despachado no puede volver a ningún estado despachable
      —imposible doble rebaja de stock—. Un catálogo en que `Cerrado` no sea el último estado
      no altera nada de esto (la terminalidad no depende de la posición).
  - **Evidencia:** `test_ciclo_vida_flujo_013.py` — `test_catalogo_degenerado_sin_salida_desde_cerrado_ac_26`, `test_catalogo_degenerado_sin_salida_desde_anulado_ac_26`, `test_reentrada_en_cerrado_es_imposible_en_catalogo_degenerado_ac_26` y `test_ticket_despachado_no_vuelve_a_un_estado_despachable_ac_26`; recorrido `evidencia/README.md` §3.3 #10 (409 con el literal del cierre reservado), #16 y #17 (catálogo canónico).

**Cerrada (19/Oct/2026):** AC-1…AC-26 en verde con la evidencia de arriba; `pytest` SQLite 952 passed/68 skipped/0 failed, gated PostgreSQL 16 1020 passed/0 skipped/0 failed, `ng test` 323 SUCCESS y `ng build` limpio; matriz/OpenAPI de **49 operaciones** v1; recorrido funcional en 4200 con escritura real (`evidencia/README.md` §3) y humo en 8080 con la imagen reconstruida (bundle `main-R6LIXDWJ.js`, §8). Enmiendas incorporadas durante la implementación: **D-4/AC-26** (la terminalidad por nombre canónico en cualquier catálogo sustituyó a la ordinal de la 004) y **AC-18** (un rol sin la operación en la matriz —p. ej. Solicitante en rechazo— recibe 403, no el 404 de ocultamiento).

### Enmienda post-cierre (05/Nov/2026): el alta nace siempre en `Pendiente`

La elección de estado inicial del alta (D-11) se retira: todo ticket nuevo nace en el estado
`Pendiente`, resuelto por **nombre canónico** (normalizado, menor `estado_id` ante duplicados) y
no por posición del catálogo. El campo `estado_id` sigue **obligatorio** en `TicketCrear`
—contrato aditivo, el campo no se retira— y debe transportar el id de `Pendiente`: cualquier otro
id (`EnRevision`, `EnCurso`, `Cerrado`, `Anulado` o ajeno al catálogo) responde **409** antes de
cualquier escritura, y un catálogo sin `Pendiente` responde también **409** (fail-closed). Queda
**derogada** la admisión de `Cerrado` en el alta y su sellado de `fecha_cierre` (004 AC-17):
`Cerrado` solo se alcanza por el despacho transaccional de la 005. En la interfaz, el modal de
alta muestra el estado inicial como dato **fijo** —no editable para ningún rol— y el backend
sigue siendo la frontera real. La prioridad se conserva editable y pasa a tener `Media`
predeterminada, resuelta igualmente por nombre canónico. La tarjeta completa del tablero es el
enlace al detalle (sustituye a la acción «Gestionar» de D-14).

**Por qué:** todo ticket debe arrancar en la cola de revisión; permitir nacer en un estado
posterior fabricaba tickets que nunca pasaron por `Pendiente` y abría la puerta al sellado de
cierre sin despacho. La prioridad `Media` evita el envío con el campo vacío sin quitar la
capacidad de priorizar.

- [x] **AC-27** DADO QUE cualquier usuario autenticado abre el modal de alta, ENTONCES el estado
      inicial se muestra fijo en `Pendiente` y no es editable; la prioridad aparece predeterminada
      en `Media` y sigue siendo cambiable. El alta envía siempre el `Pendiente` resuelto del
      catálogo; el backend responde **409** si el `estado_id` no es `Pendiente` (o si el catálogo
      no lo contiene) y **201** con `Pendiente` en el resto de casos, sin sellar `fecha_cierre`
      jamás en el alta.
  - **Evidencia:** `backend/tests/funcional/integracion/test_ciclo_vida_alta_inicial_013.py` (409 en `EnRevision`/`EnCurso`/`Cerrado`/`Anulado` sin efectos, 201 con `Pendiente` y `fecha_cierre` nula con `PATCH /estado` posterior intacto, 409 con catálogo sin `Pendiente`, 404 con id inexistente —la referencia precede a la regla—, 422 sin `estado_id` y resolución por nombre con `Pendiente` fuera de la primera posición) + ajustes en `test_tablero_kanban.py`/`test_ciclo_vida_flujo_013.py`/`test_ticket_sede_011.py` y `test_modal_ticket.py`; `frontend/src/app/features/tickets/tickets.component.spec.ts` (estado fijo sin selector, resolución por nombre en catálogo hostil, `Media` predeterminada y cambiable, vuelta a los valores por defecto tras crear); recorrido `evidencia/README.md` §9 «Enmienda post-cierre (05/Nov/2026)» en 4200 y humo 8080 reconstruido.

## 8. Restricciones

- `constitucion.md` §2 (Trazabilidad Absoluta): el historial de transiciones es inmutable; la
  anulación no mueve stock y por lo tanto no genera movimientos de inventario — la auditoría de
  `movimiento_inventario` sigue cubriendo exclusivamente cambios de existencias.
- `constitucion.md` §3 (Consistencia Transaccional): el cambio de estado y su fila de
  historial son una sola operación; la edición de cabecera y de ítems es otra; ningún rechazo
  deja efectos parciales.
- `AGENTS.md` §7 (cambio de modelo justificado): esta feature **añade un estado al catálogo
  `estado_ticket`** y **crea una estructura de historial de transiciones de ticket**; la
  justificación de modelo correspondiente vivirá en `docs/spec/stack.md` como prerrequisito
  aprobado del plan, antes de tocar modelos, DDL o migraciones. Esta spec decide el qué y el
  porqué, no la implementación.
- `AGENTS.md` §6: identificadores en español (estructuras, columnas, operaciones y mensajes).
- Derogación parcial de la Feature 004, en el patrón que la propia 004 usó con la 005: quedan
  derogados **en su capa de UI** los AC-9, AC-10, AC-12, AC-19 y AC-20 de
  `004-tablero-kanban/spec.md` (transiciones por botón en el tablero y su feedback 409/404 en
  el tablero) y lo concerniente al tablero de sus D-2 (controles en la tarjeta) y D-7
  (movimiento y reconsulta de la tarjeta); el backend de `PATCH /estado` conserva intactos su
  orden de validación, el flujo lineal de un paso entre los cuatro estados operativos y el
  sellado de `fecha_cierre`, y la operación de transición se concentra en la vista de detalle
  (D-14).
- **Derogación adicional de la 004 (enmienda de D-4):** la regla de terminalidad **ordinal** de
  su D-2 y su §5 ("el último estado del orden del catálogo es terminal", con salida desde él en
  catálogos degenerados) quedan **sustituidos**, en el dominio del ciclo de vida de tickets, por
  la resolución por nombre canónico: `Cerrado` y `Anulado` son terminales por nombre y ninguno
  admite transición de salida vía `PATCH /estado` (409) en **cualquier** catálogo (AC-26). Su
  test degenerado `test_reentrar_en_cerrado_conserva_la_fecha_original`
  (`backend/tests/funcional/integracion/test_tablero_kanban.py`), que exige `Cerrado → Archivado` = 200 cuando
  `Cerrado` no es el último del catálogo, queda derogado: esa petición responde hoy 409. El
  resto de la 004 —flujo lineal entre operativos, orden de validación ticket→estado→flujo,
  sellado de `fecha_cierre` y cierre reservado al despacho (005)— permanece intacto. La 004 se
  conserva sin editar: es registro histórico de su release.
- `AGENTS.md` §7: sin dependencias nuevas; la matriz central de permisos solo recibe filas
  aditivas; el gating de capacidades por institución de la 012 se aplica a las operaciones
  nuevas sin modificar la matriz; Clerk sigue siendo la única autoridad de autenticación.
- El catálogo de estados permanece sin CRUD: `Anulado` se siembra, se construye por tenant y se
  migra; no se administra desde la interfaz.
- Concurrencia: se conserva el comportamiento vigente (última escritura gana en el cambio de
  estado; el despacho mantiene su bloqueo); el historial registra ambas transiciones si ambas
  se aceptaron en su momento.
- La migración operacional nunca usa la semilla destructiva y es verificable contra
  PostgreSQL 16; SQLite no acredita el token de versión ni la replicación por esquema.
- **Derogación adicional de la 004 (enmienda post-cierre 05/Nov/2026):** el AC-17 de
  `004-tablero-kanban/spec.md` en lo que admitía **nacer en `Cerrado`** y sellar `fecha_cierre`
  en el alta queda derogado; `Cerrado` solo se alcanza por el despacho transaccional de la 005.
  El resto del AC-17 (sellado de la fecha al cerrar) permanece intacto. La spec de la 004 se
  conserva sin editar: es registro histórico de su release.

## 9. Enmienda post-cierre (25/Nov/2026): aprobación del Administrador, etiqueta de proceso y confirmación de entrega

> **Qué enmienda.** No reescribe los AC-1…AC-27 ni retira la evidencia de la feature cerrada.
> Añade reglas, contrato, interfaz y AC nuevos (AC-28…AC-49). Sustituye «Avanzar» y «Retroceder»
> por una **aprobación semántica** del Administrador que siempre deja el pedido en `EnCurso`
> (el stock solo decide la etiqueta), conserva `EnRevision` como estado heredado y deja el
> `PATCH /estado` como contrato de legado que la UI ya no usa y que se concede **solo al
> Administrador**. Agrega una **etiqueta de proceso**
> derivada (§9.8), dos **responsables** de lectura y **dos** operaciones nuevas —aprobación
> (§9.4) y confirmación de entrega (§9.9)—, que llevan la matriz de **73 a 75** operaciones
> (OpenAPI 75 → 77). No toca Compras, la cadena de la OC, el despacho de la 005 ni el modelo de
> datos.

### 9.1 Problema y objetivo

**El caso reportado (verificado el 25/Nov/2026).** El pedido #10 «falta de papel confort» de
la Sede Maipú está en `EnCurso` y pide 3 unidades de «Papel Premium A4»; su `stock_sede` tiene
64 unidades y el `stock_minimo` del producto es 10. El pedido **no aparece en Compras**, y no
es un fallo: `GET /compras/necesidades` omite las filas `(sede, producto)` en las que
`stock_actual > stock_minimo` y `demanda_tickets <= stock_actual`; aquí 64 > 10 y 3 ≤ 64. La
regla de las Features 020/021 es correcta: comprar lo que el saldo ya cubre duplicaría la
compra.

**Lo que falta es el gobierno del flujo.** (a) La vista de detalle muestra el aviso «Stock
disponible — Listo para despacho» cuando `stock_disponible` es `true`, pero **no ofrece
despachar**, aunque `POST /api/v1/tickets/{ticket_id}/despacho` existe desde la Feature 005;
esa feature excluyó expresamente el frontend («El frontend incluido se limita a ocultar la
transición manual de cierre»), y sin acción la confirmación de stock es un callejón sin
salida. (b) La barra de acciones ofrece «Avanzar» y «Retroceder» genéricos, que no expresan la
decisión del negocio: el Administrador no «avanza un paso», **aprueba** el pedido, y el pedido
aprobado debe quedar en `EnCurso` con independencia del stock; el stock solo decide la etiqueta
(«En confirmación de stock local» o «Por comprar»). (c) `EnRevision` es un estado **heredado**: el flujo
nuevo no lo produce y el tablero lo conserva para los pedidos existentes.

**La expectativa de que el pedido «se avance solo» con la compra no se cumple y no debe
cumplirse.** Emitir, facturar o recepcionar una OC no cambian el estado del pedido (020/021):
la recepción solo incrementa stock y, como mucho, escribe una fila `EnCurso → EnCurso` de
desbloqueo; el cierre es el despacho, que rebaja stock y firma la `SALIDA`
(`constitucion.md` §2/§3). El avance del flujo es la **aprobación humana** del Administrador; no
hay auto-avance por stock ni por compra.

**Objetivo.**

1. Sustituir «Avanzar» y «Retroceder» por **«Aprobar»** (solo Administrador), que siempre lleva
   el pedido de `Pendiente` o `EnRevision` a `EnCurso`; el stock no decide el destino, solo la
   etiqueta. Si no hay stock, el pedido queda «Por comprar» y aparece en Compras para generar la
   OC.
2. Mantener `EnRevision` como estado **heredado**: el flujo nuevo no lo produce, el tablero
   conserva su columna y los pedidos existentes se aprueban con la misma acción.
3. Ofrecer en el detalle la acción **«Despachar»** («Confirmar stock local y despachar») para el
   pedido `EnCurso` cubierto, reutilizando el despacho de la 005 con el `usuario_id` de la sesión.
4. Exponer en el tablero y en el detalle una **etiqueta de proceso** derivada —sin estados
   canónicos nuevos— que diga en qué punto está el pedido, junto con el **último Bodeguero** y
   el **último Administrador** que lo gestionaron.
5. Permitir que el **Solicitante dueño** confirme la entrega después del despacho, sin cambiar
   el estado canónico `Cerrado` ni reabrir el pedido.

Sin estados canónicos, tablas, columnas, capacidades ni versión de esquema nuevos. Se agregan
**dos** operaciones (aprobación y confirmación de entrega) y la matriz pasa de **73 a 75**;
Compras y la cadena de la OC no cambian.

### 9.2 Decisiones

#### D-15 — «Aprobar» sustituye a «Avanzar» y «Retroceder» y siempre lleva a `EnCurso`

La aprobación es una operación semántica propia (`POST /tickets/{id}/aprobacion`), no un paso
genérico del flujo. Solo el Administrador Institucional la ejecuta; el origen es `Pendiente` o
`EnRevision` (heredado) y el destino es **siempre** el `EnCurso` canónico, con stock o sin él.
El stock no decide el destino: decide la etiqueta de proceso después de la aprobación (§9.8). La
aprobación es una **excepción semántica documentada** a la regla de un paso de la 004: el
`PATCH /estado` sigue siendo de un paso, pero la aprobación es una operación propia que va
directo a `EnCurso`.

**Por qué:** el Administrador no «avanza un paso»: decide que el pedido se atiende. Hacer
depender el destino del stock obligaba a dos caminos y a un estado intermedio que el negocio no
quiere; con la aprobación siempre a `EnCurso`, el pedido entra en la cola operativa y Compras
decide si hay que comprar. La excepción se documenta en vez de deformar la regla del `PATCH`,
que se conserva para legado y compatibilidad.

#### D-16 — Una sola fila de historial por aprobación, con el Administrador como actor

La aprobación escribe **exactamente una** fila: origen = el estado real del pedido (`Pendiente` o
`EnRevision`), destino = `EnCurso`, `usuario_id` = el Administrador de la sesión, `motivo`
literal `Aprobación del pedido` y `orden_compra_id` nulo. No se escriben dos filas ni se inventa
un actor «sistema»; si la fila no puede escribirse, la transición se revierte y el pedido
conserva su estado (AC-11 vigente).

**Por qué:** una fila por mutación de estado (AC-9); el estado intermedio no existe; el actor es
quien aprobó y el motivo canónico permite distinguir la aprobación de un `PATCH` de legado.

#### D-17 — La aprobación no evalúa stock; la etiqueta sí, con la simulación de la 020

La aprobación no reserva, no evalúa la cobertura y no incluye el pedido en ninguna simulación de
candidato. Una vez en `EnCurso`, la etiqueta de proceso (§9.8) usa `stock_disponible` —la
simulación todo-o-nada de la 020, solo `EnCurso`— y el estado de las OC que cubren el pedido.
La ausencia de stock no impide aprobar: el pedido queda «Por comprar» y aparece en Compras como
necesidad; cuando se reciba la compra, `stock_disponible` pasará a `true` y la etiqueta a «En
confirmación de stock local» sin cambiar el estado.

**Por qué:** el flujo casi automático que pidió el usuario no necesita una simulación previa:
aprueba y deja que el saldo y la compra decidan la etiqueta. Mantener el candidato fuera de la
simulación conserva el contrato de la 020 y elimina la regla de auto-avance que esta enmienda
sustituye.

#### D-18 — Sin reserva: el despacho sigue siendo la validación real

La aprobación no bloquea ni aparta stock. Dos pedidos pueden quedar en `EnCurso` contra el mismo
saldo y el segundo despacho responderá **409** («Stock insuficiente…») sin efectos, que es la
garantía vigente de la 005 (validación total antes de escribir y bloqueo de las filas en el
despacho). La aprobación serializa por la fila del pedido para que dos aprobaciones concurrentes
produzcan una sola transición y la segunda responda 409 (patrón de la 005; SQLite no acredita el
bloqueo).

**Por qué:** reservar exigiría un estado o una columna persistidos —prohibidos por esta
enmienda— y cambiaría la semántica de stock de las 020/021. El despacho ACID ya es la frontera
que impide una doble rebaja; la aprobación solo decide que el pedido entra en la cola.

#### D-19 — El despacho se ofrece en el detalle y reutiliza el endpoint de la 005

La acción «Despachar» («Confirmar stock local y despachar») vive en la barra de acciones del detalle
(D-14), se ofrece solo a `Administrador` y `Bodeguero`, solo con el pedido en `EnCurso` y solo con
`stock_disponible = true`; pide confirmación previa sin motivo y envía
`POST /api/v1/tickets/{ticket_id}/despacho` con el `usuario_id` de la sesión (`GET /auth/me`).
No hay una segunda ruta de cierre ni un payload nuevo.

**Por qué:** la 005 dejó el frontend fuera y sin esta acción el badge de stock no tiene
continuación posible en la aplicación; reutilizar el endpoint conserva la transacción ACID, los
movimientos `SALIDA`, las cantidades entregadas y el historial, y evita que el cierre tenga dos
implementaciones que puedan divergir. La condición `stock_disponible` es la misma que muestra el
aviso; el servidor sigue validando de nuevo y responde 409 si el saldo cambió entre la lectura y
la confirmación.

#### D-20 — Compras sigue midiendo faltantes reales; la aprobación a `EnCurso` es lo que hace aparecer el pedido

`GET /compras/necesidades` conserva su regla de omisión (fila con `stock_actual > stock_minimo`
y `demanda_tickets <= stock_actual` no se muestra), su demanda de solo pedidos `EnCurso` y su
sugerido neto. Un pedido en `Pendiente` o `EnRevision` **no** cuenta como demanda; al aprobarlo y
quedar en `EnCurso`, entra en la demanda y aparece en Compras cuando su `(sede, producto)` tiene
necesidad neta. Un pedido cubierto por stock sigue sin aparecer. Emitir, facturar, recepcionar o
cancelar una OC no cambian el estado del pedido: la recepción solo puede añadir la fila
`EnCurso → EnCurso` de desbloqueo con su `orden_compra_id` (020/021) y el cierre sigue siendo el
despacho.

**Por qué:** comprar lo que el saldo cubre duplica la compra, y mover el estado con hitos de
compra cerraría pedidos sin la salida de inventario que exige `constitucion.md` §3. El estado
del pedido describe aprobación, preparación y entrega; la compra es logística de reposición y se
sigue en la OC, no en el estado del pedido.

### 9.3 Reglas del flujo

**Flujo principal.** `Pendiente` —**Aprobar** (Administrador)—→ `EnCurso` —**Despachar**
(Bodeguero/Administrador, con `stock_disponible`)—→ `Cerrado` —**Confirmar entrega** (Solicitante
dueño)—→ `Cerrado` con etiqueta «Entregado». En `Pendiente` y `EnRevision` (heredado) también se
puede **Rechazar** (Bodeguero/Administrador) y **Anular** (Solicitante dueño/Administrador); en
`Pendiente` se puede **Editar** (dueño/Administrador). `Anulado` no admite ninguna acción.
`EnRevision` no se produce en el flujo nuevo: solo existe para pedidos heredados.

| Acción | Origen | Destino | Quién | Historial |
|---|---|---|---|---|
| **Aprobar** | `Pendiente` / `EnRevision` | **`EnCurso`** siempre | Administrador | 1: origen → `EnCurso`, motivo `Aprobación del pedido` |
| **Rechazar** | `Pendiente` / `EnRevision` | `Anulado` | Bodeguero / Administrador | 1: origen → `Anulado`, motivo obligatorio |
| **Anular** | `Pendiente` / `EnRevision` | `Anulado` | Solicitante dueño / Administrador | 1: origen → `Anulado`, motivo obligatorio |
| **Editar** | `Pendiente` | `Pendiente` | Solicitante dueño / Administrador | — (no es transición) |
| **Despachar** | `EnCurso` | `Cerrado` | Bodeguero / Administrador | 1: `EnCurso` → `Cerrado` |
| **Confirmar entrega** | `Cerrado` | `Cerrado` (evento) | Solicitante dueño | 1: `Cerrado` → `Cerrado`, motivo canónico |
| **PATCH /estado** (legado) | catálogo | un paso | **Administrador** | 1: origen → destino |

**Aprobación.** `POST /api/v1/tickets/{ticket_id}/aprobacion` (Administrador, capacidad
`kanban`) acepta un pedido en `Pendiente` o `EnRevision` y lo deja **siempre** en `EnCurso`:

- No evalúa stock, no reserva y no incluye el pedido en ninguna simulación. El stock solo decide
  la etiqueta después de la aprobación (§9.8).
- Escribe una **sola** fila de historial: origen real → `EnCurso`, actor = el Administrador de la
  sesión, `motivo` literal `Aprobación del pedido` y `orden_compra_id` nulo. La fila y el cambio
  de estado son una sola transacción; si la fila falla, el pedido conserva su estado.
- Si el pedido ya está `EnCurso`, `Cerrado` o `Anulado`, o su estado no es `Pendiente` ni
  `EnRevision` (incluido un estado fuera del catálogo), responde **409** sin escribir.
- Si el catálogo no contiene `EnCurso`, responde **409** (fail-closed).
- Un pedido de otra institución o inexistente responde **404** idéntico; un rol sin la operación
  (Bodeguero, Solicitante o Superadmin) **403**; sin sesión, **401**. La precedencia es
  **401 → 403 → 404 → 409**.
- No hay payload obligatorio; no se espera **422** por cuerpo.
- Serializa por la fila del pedido (patrón de la 005): dos aprobaciones concurrentes producen una
  sola transición y la segunda responde 409. SQLite no acredita el bloqueo.
- Es una **excepción semántica documentada** a la regla de un paso de la 004: el `PATCH /estado`
  sigue siendo de un paso; la aprobación es una operación propia que va directo a `EnCurso`.

**Por qué `kanban`:** es la capacidad que ya gatea las transiciones del ciclo de vida (anulación
y rechazo) y el tablero; la aprobación es una decisión de flujo, no de contenido ni de lectura.
`tickets` seguiría funcionando, pero mezclaría la decisión de flujo con la edición y la lectura
del pedido, que es lo que la matriz separa. El Administrador es el rol que autoriza la atención
del pedido; el Bodeguero prepara y despacha, y el Solicitante solicita y confirma la entrega.

**Aprobación y Compras.** Al quedar en `EnCurso`, el pedido entra en la demanda de
`GET /compras/necesidades` y aparece como necesidad cuando su `(sede, producto)` tiene necesidad
neta; antes (`Pendiente` o `EnRevision`) no cuenta. La emisión, facturación, recepción y
cancelación de la OC **no** cambian el estado del pedido; la recepción solo puede añadir su fila
`EnCurso → EnCurso` de desbloqueo. La Feature 021 no cambia de algoritmo.

**`PATCH /estado` (legado).** Se conserva para compatibilidad y **solo lo concede el
Administrador**: un paso entre estados contiguos, `EnCurso → Cerrado` reservado al despacho,
`Cerrado` y `Anulado` terminales por nombre y `Anulado` fuera del flujo. Ya **no** evalúa stock ni
salta a `EnCurso`: una petición a `EnRevision` deja el pedido en `EnRevision` y su fila con
`motivo` nulo. La UI no lo usa (ver §9.5).

**Despacho.** `POST /despacho` conserva íntegro su contrato y su semántica: solo desde
`EnCurso`, cierra en `Cerrado`, rebaja `stock_sede`, escribe una `SALIDA` por detalle, fija
`cantidad_entregada`, sella `fecha_cierre` y registra su fila de historial. La enmienda no lo
modifica; solo lo invoca desde la interfaz.

**Confirmación de entrega.** Después del despacho, el Solicitante dueño puede confirmar la
entrega (§9.9); no cambia el estado canónico, no reabre el pedido y no toca stock.

**Concurrencia y etiqueta.** La aprobación no reserva; el despacho valida. Al entrar en
`EnCurso`, el pedido participa en la simulación de la 020 y puede bajar el `stock_disponible` de
pedidos de menor prioridad: es el mismo efecto que produce cualquier pedido `EnCurso`, no un
cambio de la regla. La etiqueta se recalcula al leer y no cambia el estado.

### 9.4 Contrato

#### `POST /api/v1/tickets/{ticket_id}/aprobacion` — nueva

- **Payload:** ninguno. Un cuerpo ausente o vacío es válido; no hay 422 por cuerpo.
- **Roles:** `Administrador`; capacidad `kanban` (justificación en §9.3). Con la capacidad
  apagada, 403.
- **Éxito:** **200** con `TicketRespuesta` con `estado_id` = `EnCurso` y la etiqueta derivada
  (§9.8); el historial registra la fila de D-16. La UI reconsulta el detalle.
- **Errores, en orden:** **401** sin sesión; **403** rol fuera de la matriz o capacidad `kanban`
  apagada; **404** pedido inexistente o de otra institución (idénticos); **409** pedido ya
  `EnCurso`, `Cerrado` o `Anulado`, estado no elegible o catálogo sin `EnCurso`.
- **Sin efectos colaterales:** no toca stock, `fecha_cierre`, OC ni Compras; solo el estado y su
  fila de historial. No reserva stock.
- **Concurrencia:** serializa por la fila del pedido; una petición responde 200 y la otra 409,
  con una sola fila de historial. SQLite no acredita el bloqueo.

#### `PATCH /api/v1/tickets/{ticket_id}/estado` — legado, mismo contrato de transición y rol restringido

- **Petición:** sin cambios. `{"estado_id": <id del destino>}`; **rol `Administrador`
  únicamente**. El `Bodeguero` recibe **403** por matriz; 401/403/404/422 con su orden vigente.
- **Autorización:** la operación deja de concederse al `Bodeguero`. El contrato de transición de
  la 004/005 no cambia: un paso entre estados contiguos, `EnCurso → Cerrado` reservado al despacho
  y `Cerrado`/`Anulado` terminales por nombre. Lo único que cambia es el rol.
- **Éxito:** **200** con `TicketRespuesta`. El destino es el **solicitado**: un paso entre
  estados contiguos; `EnCurso → Cerrado` responde **409** con el detalle que dirige al despacho;
  `Cerrado` y `Anulado` son terminales por nombre y no admiten salida; `Anulado` queda fuera del
  flujo. **Ya no evalúa stock ni salta a `EnCurso`**: una petición a `EnRevision` deja el pedido
  en `EnRevision` con su fila y `motivo` nulo.
- **Uso:** se conserva para compatibilidad y clientes de legado. **La UI no lo invoca** (ver
  §9.5).
- **Historial:** una fila por transición aceptada, con el actor de la sesión y `motivo` nulo; el
  `GET /tickets/{id}/historial` no cambia de forma.
- **Superficie:** no agrega campos a `TicketDespacho` ni cambia su payload. La enmienda sí agrega
  **campos de lectura derivados** a `TicketRespuesta` y `TicketDetalleRespuesta` (§9.8) y **dos**
  operaciones nuevas —aprobación (arriba) y confirmación de entrega (§9.9)—: la matriz pasa de
  **73 a 75** operaciones v1 (`/openapi.json`, de 75 a 77 entradas con `GET /` y `/health`). **El
  `PATCH` conserva su entrada pero pasa de `Administrador`/`Bodeguero` a solo `Administrador`**;
  las demás operaciones conservan roles y códigos. La capacidad `kanban` gatea la aprobación y la
  capacidad `tickets` la confirmación. Las descripciones OpenAPI del `PATCH` dejan de anunciar un
  destino efectivo distinto del solicitado.

#### `POST /api/v1/tickets/{ticket_id}/despacho` — sin cambios

Conserva su contrato de la 005 (`{"usuario_id": <id existente>}`, 200 `Cerrado`, 404, 409, 422,
un solo cierre por pedido). El `usuario_id` que envía la vista es el de la sesión.

#### `POST /api/v1/tickets/{ticket_id}/confirmacion-entrega` — nueva

Se detalla en §9.9: solo `Solicitante` dueño, capacidad `tickets`, fila `Cerrado → Cerrado` con
motivo canónico, 409 si ya está confirmada y sin cambios de estado ni stock.

### 9.5 Interfaz (detalle del pedido)

**Barra de acciones sin «Avanzar» ni «Retroceder».** La barra se arma por estado y rol; no
ofrece transiciones genéricas ni invoca `PATCH /estado`:

| Estado | Acciones ofrecidas |
|---|---|
| `Pendiente` | **Aprobar** (Administrador), **Rechazar** (Bodeguero/Administrador), **Anular** (Solicitante dueño/Administrador), **Editar** (dueño/Administrador) |
| `EnRevision` (heredado) | **Aprobar** (Administrador), **Rechazar** (Bodeguero/Administrador), **Anular** (Solicitante dueño/Administrador) |
| `EnCurso` | **Despachar** / «Confirmar stock local y despachar» (Bodeguero/Administrador, `stock_disponible = true`) |
| `Cerrado` | **Confirmar entrega** (Solicitante dueño, si no está confirmada) |
| `Anulado` | Ninguna |

**Por qué no hay «Avanzar» ni «Retroceder»:** un botón genérico no dice qué decisión se toma y
obliga a conocer la posición del catálogo; las acciones semánticas se leen solas. El
`PATCH /estado` se conserva como contrato de legado, pero ninguna pantalla lo invoca.

**El `PATCH /estado` no aparece en la barra:** es solo del Administrador. El Bodeguero conserva
**Despachar** (`POST /despacho`), **Rechazar** (`POST /rechazo`) y la recepción de compras (su
endpoint de compras), que son operaciones propias y no el `PATCH`.

- **Aprobar.** Solo el Administrador; no pide motivo; se ejecuta con un clic y, al 200, la vista
  muestra el pedido en `EnCurso`, su etiqueta («En confirmación de stock local» o «Por comprar») y
  reconsulta detalle e historial. Un 409 (ya `EnCurso`/terminal/catálogo) se muestra en
  `role="alert"` sin cambiar el estado por cuenta propia. El Bodeguero y el Solicitante no ven el
  botón.
- **Aviso de stock.** Se conserva el badge «Stock disponible — Listo para despacho»
  (`role="status"`) cuando `stock_disponible` es `true`. Un pedido en `EnRevision` no lo muestra
  porque no participa en la simulación de la 020; la vista no agrega un aviso de «sin stock» que
  el servidor no pueda sostener.
- **Despachar.** «Confirmar stock local y despachar» aparece solo si el pedido está en `EnCurso`,
  `stock_disponible` es estrictamente `true` y el rol es `Administrador` o `Bodeguero`. Pide
  confirmación previa en un diálogo nativo `<dialog>` (mismo patrón que anulación y rechazo), sin
  motivo, con «Confirmar»/«Cancelar», `Esc` y foco atrapado. Mientras la petición está en vuelo,
  el indicador de operación deshabilita todos los controles (sin doble envío).
- **Éxito del despacho.** `role="status"` y reconsulta de detalle e historial: el pedido se
  muestra `Cerrado`, con `fecha_cierre`, las cantidades entregadas y la fila del despacho; el
  badge desaparece y la barra pasa a la nota de estado terminal.
- **409 del despacho.** `role="alert"` con el mensaje del servidor (p. ej. «Stock insuficiente
  para el producto …»), sin cambiar el estado por cuenta propia y reconsultando el detalle, que
  retira la acción si ya no aplica. 404 y 403 conservan su tratamiento vigente.
- **Editar, Rechazar y Anular.** Conservan el comportamiento de la 013: edición solo en
  `Pendiente`; rechazo y anulación solo en `Pendiente`/`EnRevision`, con motivo obligatorio y
  confirmación previa; `Anulado` no ofrece nada.
- **Accesibilidad.** Cada acción tiene etiqueta y `aria-label` propios; los mensajes se anuncian
  en regiones vivas (`status`/`alert`); las confirmaciones no dependen solo del color y el foco
  vuelve al botón que las abrió al cancelar.

### 9.6 Fuera de alcance (no-goals)

- **Compras no cambia:** ni la detección de necesidades, ni el sugerido neto, ni el preview de
  cobertura, ni la emisión, facturación, recepción o cancelación de la OC, ni el plan de
  `orden_compra_ticket`. Un pedido cubierto por stock sigue sin aparecer; la aprobación a
  `EnCurso` es lo que hace aparecer al que tiene necesidad neta.
- **Ningún estado canónico nuevo ni cambio de la cadena:** nada de «En OC», «Comprado»,
  «Recibido» o «Entregado» como estado canónico; las etiquetas de proceso son de lectura (§9.8);
  `EnRevision` es heredado y no se produce en el flujo nuevo; `Cerrado` sigue siendo el despacho
  y `Anulado` el terminal negativo; los hitos de compra no mueven el estado.
- **El despacho de la 005 no se reimplementa:** sin cambios de contrato, códigos, transacción,
  bloqueo, observación ni movimientos.
- **Sin DDL ni cambios de modelo:** sin tablas, columnas, índices, semilla, migración, token de
  versión (`026.0`), entidades de dominio ni estructuras auxiliares. La confirmación de entrega
  reutiliza una fila de `historial_transicion_ticket` (§9.9); si el plan concluyera que no basta,
  se detiene como cambio de modelo que exige aprobación en `docs/spec/stack.md`.
- **Autorización acotada:** las **dos** operaciones nuevas son la aprobación
  (`POST /tickets/{id}/aprobacion`, `Administrador`, capacidad `kanban`) y la confirmación de
  entrega (`POST /tickets/{id}/confirmacion-entrega`, `Solicitante`, capacidad `tickets`); la
  matriz pasa de **73 a 75** y no se agregan capacidades, roles ni guards nuevos. Además, el
  `PATCH /estado` deja de concederse al `Bodeguero` y queda solo para el `Administrador` (cambia
  el rol de una entrada existente, no su número).
- **El `PATCH /estado` no se retira:** se conserva para compatibilidad y legado con su regla de
  un paso, pero **solo lo concede el `Administrador`**, la UI no lo usa y no ofrece «Avanzar» ni
  «Retroceder».
- **Sin reserva de stock**, sin bloqueo nuevo en el `PATCH`, sin notificaciones, sin correo, sin
  tablero editable y sin despacho desde el Kanban.
- **Sin simulación de candidato ni auto-avance por stock:** la aprobación no evalúa stock y la
  etiqueta usa `stock_disponible` de la 020 (solo `EnCurso`); `calcular_cobertura_tickets` no
  cambia.

### 9.7 Criterios de aceptación del flujo

- [x] **AC-28 (PATCH de legado, sin auto-avance)** DADO un pedido en `Pendiente`, CUANDO se envía
      `PATCH /api/v1/tickets/{ticket_id}/estado` con el `estado_id` de `EnRevision`, ENTONCES
      queda en `EnRevision`, con una fila `Pendiente → EnRevision` y `motivo` nulo, sin evaluar
      stock ni saltar a `EnCurso`; el `PATCH` conserva su regla de un paso y `EnCurso → Cerrado`
      sigue respondiendo 409 con el detalle del despacho. `Cerrado` y `Anulado` siguen siendo
      terminales.
  - **Evidencia (25/Nov/2026):** `backend/tests/funcional/integracion/test_ciclo_vida_aprobacion_013.py::test_patch_estado_conserva_su_contrato_de_legado_para_el_administrador_ac_49` y `backend/tests/funcional/e2e/test_flujo_aprobacion_entrega_013.py::test_patch_de_legado_solo_administrador_y_cierre_reservado`; vivo (25/Nov/2026): `PATCH` de #9 a `EnRevision` **200** con fila `Pendiente → EnRevision` y `motivo` nulo (historial id 16) y `PATCH` a `Cerrado` **409**. `evidencia/README.md` §10.4-§10.5.
- [x] **AC-29 (aprobación: siempre a `EnCurso`)** DADO un pedido en `Pendiente` o `EnRevision`,
      CUANDO el Administrador lo aprueba, ENTONCES el estado final es **siempre `EnCurso`**, con
      stock o sin él; la etiqueta se rige por la precedencia de AC-38 —«En confirmación de stock
      local» si el stock local está disponible o hay una OC `Recibida`, «Facturado»/«En compra» si
      hay OC `Facturada`/`Emitida`, y «Por comprar» si no hay stock ni OC activa—. No se evalúa
      stock para decidir el destino, no se reserva y `fecha_cierre` sigue nula.
  - **Evidencia (25/Nov/2026):** `test_ciclo_vida_aprobacion_013.py::test_aprobacion_desde_origen_elegible_deja_el_pedido_en_curso_ac_29`, `::test_aprobacion_siempre_lleva_a_en_curso_y_el_stock_solo_cambia_la_etiqueta_ac_29`, `::test_aprobacion_no_toca_stock_ni_movimientos_ac_29`; recorrido 4200: #11 (con stock) queda «En confirmación de stock local» y #12 (sin stock) «Por comprar», ambos **En Curso** y con `fecha_cierre` nula (capturas 03 y 08).
- [x] **AC-30 (aprobación: historial y atomicidad)** DADO que la aprobación se acepta, ENTONCES
      escribe **exactamente una** fila `origen → EnCurso` con el `usuario_id` del Administrador
      de la sesión, `motivo` literal `Aprobación del pedido` y `orden_compra_id` nulo; no hay dos
      filas ni actor «sistema». Si la fila no puede escribirse, el pedido conserva su estado y no
      hay efectos parciales.
  - **Evidencia (25/Nov/2026):** `test_ciclo_vida_aprobacion_013.py::test_aprobacion_escribe_una_sola_fila_con_actor_y_motivo_ac_30` y `::test_si_la_fila_de_historial_falla_el_estado_no_cambia_ac_30`; SQL: historial ids 8 y 12, una fila por pedido, actor Administrador, motivo literal `Aprobación del pedido` y `orden_compra_id` nulo.
- [x] **AC-31 (Compras y 021)** DADO un pedido en `Pendiente` o `EnRevision`, CUANDO el
      Administrador consulta `GET /compras/necesidades`, ENTONCES no aparece en `tickets` ni suma
      `demanda_tickets` (solo `EnCurso`). CUANDO lo aprueba y queda `EnCurso`, ENTONCES pasa a
      contar como demanda y a ser asignable por una OC cuando su `(sede, producto)` tiene
      necesidad neta. Emitir, facturar, recepcionar o cancelar una OC no cambian el estado del
      pedido; la recepción solo puede añadir su fila `EnCurso → EnCurso` de desbloqueo y el
      cierre sigue siendo el despacho. La 021 no cambia de algoritmo.
  - **Evidencia (25/Nov/2026):** `backend/tests/funcional/e2e/test_flujo_aprobacion_entrega_013.py::test_aprobacion_sin_stock_aparece_en_compras_y_la_oc_mueve_la_etiqueta` y suite de la 021; recorrido 4200: la fila no aparece antes de aprobar (captura 07), aparece con #12 en la demanda tras aprobar (09), la OC emitida/facturada mueve la etiqueta a «Facturado» (10/11), la recepción desbloquea (13) y el cierre es el despacho (14).
- [x] **AC-32 (barra de acciones del detalle)** DADO un pedido, ENTONCES la barra de acciones
      ofrece: `Pendiente` → Aprobar (Administrador), Rechazar (Bodeguero/Administrador), Anular
      (Solicitante dueño/Administrador), Editar (dueño/Administrador); `EnRevision` → Aprobar,
      Rechazar, Anular; `EnCurso` → Despachar; `Cerrado` → Confirmar entrega (Solicitante dueño,
      si no está confirmada); `Anulado` → ninguna. No ofrece «Avanzar» ni «Retroceder» y no
      invoca `PATCH /estado`.
  - **Evidencia (25/Nov/2026):** `frontend/src/app/features/tickets/ticket-detalle.component.spec.ts` (acciones por estado/rol, sin Avanzar/Retroceder, sin `PATCH`); recorrido 4200 con las barras semánticas de Pendiente (02), EnCurso (03/13), Cerrado (05/15) y `Anulado` sin acciones, y la del Administrador (02/08).
- [x] **AC-33 (despacho desde el detalle)** DADO un pedido `EnCurso` con `stock_disponible =
      true`, CUANDO un Administrador o Bodeguero pulsa «Confirmar stock local y despachar» y
      confirma, ENTONCES se envía `POST /api/v1/tickets/{ticket_id}/despacho` con el `usuario_id`
      de la sesión, sin doble envío, y al 200 la vista muestra el pedido `Cerrado` con
      `fecha_cierre`, las cantidades entregadas y la fila del despacho; el stock quedó rebajado y
      hay una `SALIDA` por detalle.
  - **Evidencia (25/Nov/2026):** Specs de `ticket-detalle.component.spec.ts` y `ticket.service.spec.ts`; recorrido 4200: despacho de #11 y #12 con diálogo sin motivo, `Cerrado` con `fecha_cierre` y entregado 3/3 (capturas 04 y 14); SQL: `SALIDA` ids 6 y 8 y stock 64→61 y 23→20.
- [x] **AC-34 (409 del despacho y roles)** SI el stock dejó de cubrir el pedido entre la carga y
      la confirmación (o ya fue despachado), ENTONCES el despacho responde **409**, la vista lo
      muestra en `role="alert"` y reconsulta; la acción no se ofrece al Solicitante ni a roles
      sin permiso de despacho, y el tablero sigue sin ofrecer despacho ni transiciones.
  - **Evidencia (25/Nov/2026):** Specs del detalle (409 en `role="alert"` y reconsulta) y suite de la 005 (`test_despacho_transaccional.py`); recorrido 4200: el Solicitante no ve la acción de despacho (capturas 02 y 05) y el tablero no ofrece despacho ni transiciones (06/16).
- [x] **AC-35 (invariantes del modelo)** DADO el caso #10 (pedido `EnCurso` de la Sede Maipú, 3
      unidades, stock 64, mínimo 10), CUANDO el Administrador consulta `GET
      /compras/necesidades`, ENTONCES la fila `(sede, producto)` sigue omitida. Se conservan
      `calcular_cobertura_tickets` y el significado de `stock_disponible` (solo `EnCurso`), los
      códigos de `PATCH /estado` y `POST /despacho`, el token `026.0`, 26/23 tablas, 21 entidades
      de dominio y la ausencia de DDL; no se agrega ninguna tabla, columna, semilla, capacidad ni
      estado canónico. La matriz y el rol del `PATCH` se verifican en AC-44 y AC-49.
  - **Evidencia (25/Nov/2026):** Recorrido 4200: «Papel Premium A4» de Sede Maipú (caso #10) no aparece en Compras (captura 07); `test_flujo_aprobacion_entrega_013.py::test_caso_10_equivalente_omitido_en_compras_y_cierra_normal` y suite 020/021; sin DDL: token `026.0`, 26/23 tablas y 21 entidades (suites de control y gated).
- [x] **AC-36 (sin auto-avance)** DADO un pedido en `Pendiente` o `EnRevision`, ENTONCES la única
      vía a `EnCurso` es la aprobación: un `PATCH` a `EnRevision` no lo deja en `EnCurso` ni
      evalúa stock, y un `PATCH` de `Pendiente` a `EnCurso` sigue siendo 409 por saltarse un paso.
      No existe la regla de auto-avance por stock.
  - **Evidencia (25/Nov/2026):** Vivo: `PATCH` `Pendiente → EnRevision` deja el pedido en `EnRevision` y `PATCH` a `Cerrado` responde **409**; tests de flujo y `test_ciclo_vida_aprobacion_013.py`; en 4200 la única vía a `EnCurso` es «Aprobar» (capturas 03 y 08).

### 9.8 Etiqueta de proceso y responsables

**Problema.** El estado canónico no dice en qué punto operativo está el pedido. Un `EnCurso`
puede estar esperando que se emita la OC, con la compra facturada, con la mercadería recibida o
sin stock y por comprar; un `Cerrado` puede estar despachado o ya entregado. El tablero y el
detalle no lo distinguen, y tampoco dicen quién lo gestionó.

**Decisión.** Se agrega una **etiqueta de proceso derivada**, de solo lectura, que no es un
estado canónico, no se persiste y no altera la máquina de estados, Compras, la OC ni el stock.
La calcula el servidor una sola vez y viaja en el read model del listado y del detalle, para que
tablero y detalle no puedan divergir.

#### D-21 — La etiqueta de proceso la deriva el servidor y se expone en el read model

`TicketRespuesta` (listado y base del detalle) gana estos campos **aditivos**:

| Campo | Tipo | Contenido |
|---|---|---|
| `etiqueta_proceso` | `str` | Etiqueta canónica de proceso (tabla de D-22). |
| `explicacion_proceso` | `str` | Frase corta que dice qué falta o qué sigue. |
| `estado_orden_cobertura` | `str \| None` | Estado de la OC activa más avanzada que cubre el pedido (`Recibida`, `Facturada` o `Emitida`); `None` si no hay. |
| `stock_disponible` | `bool` | La propiedad de la 020; se expone también en el listado (antes solo en el detalle). |
| `entrega_confirmada` | `bool` | `True` si el Solicitante dueño ya confirmó la entrega (§9.9). |
| `gestionado_por_bodeguero` | `GestorProcesoRespuesta \| None` | Último Bodeguero del historial, con `usuario_id`, `nombre` y `apellido`. |
| `gestionado_por_administrador` | `GestorProcesoRespuesta \| None` | Último Administrador del historial, con la misma forma. |

`TicketDetalleRespuesta` agrega `entrega_confirmada_en` y `entrega_confirmada_por_nombre` /
`entrega_confirmada_por_apellido` para la línea «Entregado el … por …», y conserva
`asignaciones` con todas las OC del pedido (incluidas las canceladas). No hay DDL: todos son
campos de lectura derivados de tablas existentes.

**Por qué:** si el frontend derivara la etiqueta por su cuenta, el tablero y el detalle podrían
mostrar cosas distintas para el mismo pedido y cada vista tendría que replicar la precedencia de
OC y stock. Un único cálculo en el servidor mantiene una sola verdad y deja el contrato
verificable.

#### D-22 — Mapeo y precedencia de la etiqueta

| Estado canónico | Condición | `etiqueta_proceso` |
|---|---|---|
| `Pendiente` | — | «En aprobación» |
| `EnRevision` | — | «En revisión» (estado heredado; el detalle muestra el estado canónico `EnRevision`) |
| `Anulado` | — | «Rechazado» (el detalle muestra además el estado canónico `Anulado`) |
| `Cerrado` | `entrega_confirmada = false` | «Despachado» |
| `Cerrado` | `entrega_confirmada = true` | «Entregado» |
| `EnCurso` | OC `Recibida` que cubre el pedido | «En confirmación de stock local» |
| `EnCurso` | si no, OC `Facturada` que cubre | «Facturado» |
| `EnCurso` | si no, OC `Emitida` que cubre | «En compra» |
| `EnCurso` | si no, `stock_disponible = true` | «En confirmación de stock local» |
| `EnCurso` | si no | «Por comprar» |

Precedencia: **Recibida > Facturada > Emitida > stock > sin cobertura**. Una OC `Cancelada` **no
cuenta** como activa y no participa; si solo hay canceladas, se evalúa el stock. «Cubre el
pedido» significa que la OC tiene al menos una fila de plan con `cantidad_asignada > 0` para ese
pedido; la etiqueta describe la **etapa**, no la suficiencia: el badge de stock y la cadena por
producto del detalle dicen si la cantidad alcanza, y el despacho sigue siendo la validación
real. Varias OC del mismo estado no cambian la etiqueta y el orden no depende del orden de las
filas ni de la fecha de la OC.

Frases cortas (`explicacion_proceso`): «En aprobación: pendiente de revisión por Bodega o
Administración.»; «En revisión: estado heredado; se aprueba con la acción Aprobar.»; «En compra:
la orden está emitida y pendiente de facturación.»; «Facturado: la compra está facturada y
pendiente de recepción.»; «En confirmación de stock local: el stock local está disponible; falta
que el Bodeguero lo confirme y despache.»; «Por comprar: no hay stock suficiente ni compra
vigente.»; «Despachado: pendiente de confirmación de entrega.»; «Entregado: confirmado por el
solicitante.»; «Rechazado: el pedido no se despachará.».

**Por qué:** el orden Recibida > Facturada > Emitida es el avance real de la compra y evita que
una OC vieja emitida oculte una recepción; el stock solo decide cuando no hay compra vigente,
porque una OC activa explica mejor la etapa que el saldo. «Por comprar» se elige sobre
«Verificando stock» porque dice qué falta y no insinúa una comprobación en curso. Los estados
fuera del conjunto canónico degradan a su nombre visible con la explicación «Estado no
reconocido por la etiqueta de proceso», sin romper la lectura.

#### D-23 — Los responsables son el último Bodeguero y el último Administrador del historial

Cada pedido expone `gestionado_por_bodeguero` y `gestionado_por_administrador`: el actor de la
última fila de `historial_transicion_ticket` cuyo usuario tiene **vigente** el rol `Bodeguero` o
`Administrador`, con desempate `fecha_transicion DESC`, `historial_transicion_id DESC`. Si no
hay ninguna fila de ese rol, el campo es `null` y la UI muestra «Sin gestión registrada» (`—` en
la tarjeta, con el texto accesible). Incluye la fila de creación si su actor tiene ese rol,
porque también es una transición registrada. El rol se resuelve con el usuario actual: el
historial no persiste el rol del momento. No sustituye al solicitante: este sigue mostrándose
donde ya se muestra.

**Por qué:** «quiénes lo gestionaron» se responde con la evidencia que ya existe (el historial
con actor y fecha) y sin inventar una asignación ni una columna nueva. El desempate por fecha e
id es el mismo orden determinista del historial y evita que dos filas del mismo instante
produzcan respuestas distintas. La aclaración del rol vigente es honesta: el historial guarda el
actor, no su rol histórico, y no se agrega DDL para cambiarlo.

#### D-24 — El tablero agrupa los dos estados terminales en una columna «Terminados»

El tablero deja de renderizar una columna por estado: conserva `Pendiente`, `EnRevision`
(heredado) y `EnCurso` y agrupa `Cerrado` y `Anulado` en una única columna terminal titulada
**«Terminados»**, en la posición que ocupaba `Cerrado`. Su contador suma ambos estados, pero solo las tarjetas
`Cerrado` pueden mostrar «Despachado» o «Entregado»; ninguna `Anulado` cuenta como entregada.
Cada tarjeta `Anulado` muestra «Rechazado» y su detalle el estado canónico `Anulado`; cada
tarjeta `Cerrado` muestra «Despachado» o «Entregado» y su detalle el estado canónico `Cerrado`.
El tablero sigue siendo de solo lectura y la tarjeta sigue siendo el enlace al detalle.

**Interfaz del tablero y del detalle.** La tarjeta muestra la etiqueta de proceso como texto
visible, los dos responsables («Último Bodeguero: …», «Último Administrador: …») y, si el espacio
lo permite, la frase corta como texto secundario o descripción accesible; nunca solo en un tooltip
que dependa del hover. Si falta un responsable, muestra `—` con el texto accesible «Sin gestión
registrada». La descripción accesible de la tarjeta incluye el estado canónico, la etiqueta de
proceso y los responsables. El detalle muestra el estado canónico con su etiqueta actual, la
etiqueta de proceso con su frase, los dos responsables y, si existe, la línea de entrega. La
etiqueta de proceso no reemplaza al estado canónico ni al helper de etiquetas de estado: se
muestran juntos.

**Por qué:** «Cerrado / Anulado» como título leería dos estados como si fueran uno y
reintroduciría en el nombre la división que la columna única busca quitar; «Terminados» describe
la categoría (los dos terminales) sin renombrar ningún estado canónico, y la etiqueta de cada
tarjeta conserva la distinción. Se elige la posición de `Cerrado` para no alterar el orden del
flujo operativo.

### 9.9 Confirmación de entrega

**Problema.** El despacho cierra el pedido, pero no registra que el Solicitante recibió los
insumos. El tablero no distingue «despachado» de «entregado» y el Solicitante no tiene forma de
confirmar la recepción, aunque es el único que puede hacerlo.

**Decisión.** Después del despacho, el pedido queda en `Cerrado` y su etiqueta es «Despachado».
Solo el Solicitante **dueño** puede confirmar la entrega desde el detalle; la operación registra
actor y fecha en una fila de historial `Cerrado → Cerrado`, cambia la etiqueta a «Entregado» y
no altera el estado canónico: `Cerrado` sigue siendo terminal.

#### D-25 — La confirmación se persiste como evento en el historial, sin DDL

La confirmación inserta **una** fila en `historial_transicion_ticket` con
`estado_origen_id = estado_destino_id = <Cerrado canónico>`, `usuario_id` = el Solicitante dueño,
`fecha_transicion` = el instante del servidor, `motivo` literal
`Entrega confirmada por el solicitante` y `orden_compra_id` nulo. No cambia `ticket.estado_id`,
no sella ni borra `fecha_cierre`, no toca stock ni movimientos y no crea columnas ni tablas. La
confirmación existe si y solo si hay una fila `Cerrado → Cerrado` con ese motivo exacto para el
pedido; una segunda petición responde **409**.

**Por qué:** la tabla ya guarda actor, fecha, estados y motivo, y la 021 estableció el precedente
de filas sin cambio de estado (`EnCurso → EnCurso` para el desbloqueo por recepción). Reutilizarla
evita DDL, una migración y una segunda fuente de verdad para la fecha de entrega; `fecha_cierre`
conserva su significado de cierre por despacho (D-5). Si la implementación concluyera que la fila
no basta, se detiene y se eleva como cambio de modelo que exige justificación y aprobación en
`docs/spec/stack.md`; esta spec no lo aprueba.

#### D-26 — Solo confirma el Solicitante dueño; no se delega

La operación se concede **solo** al rol `Solicitante` en la matriz central y el servicio exige
además que el `usuario_id` del pedido sea el de la sesión. Un Administrador, Bodeguero o
Superadmin recibe **403** por matriz; un Solicitante sobre un pedido ajeno recibe **404**
idéntico al inexistente. Si el pedido fue creado por un Administrador o un Bodeguero, su dueño
no tiene el rol `Solicitante`: la operación no se ofrece y el pedido permanece «Despachado» para
siempre. No se inventa una confirmación por otro rol.

**Por qué:** la entrega la recibe quien pidió los insumos; el dueño es el único que puede
atestiguarla sin inferirla. Delegarla al Bodeguero convertiría la confirmación en una segunda
validación del despacho, y permitirla al Administrador borraría la distinción entre quien opera
y quien recibe. El caso del alta administrativa queda explícito y sin una confirmación ficticia.

#### Contrato — `POST /api/v1/tickets/{ticket_id}/confirmacion-entrega`

- **Payload:** ninguno.
- **Roles:** `Solicitante`, con la capacidad `tickets` (la misma que el resto de operaciones de
  pedidos). La matriz pasa de **73 a 75** operaciones v1 (aprobación + confirmación); el
  `PATCH /estado` conserva su entrada pero pasa a solo `Administrador`. `/openapi.json` pasa de 75
  a 77 entradas.
- **Éxito:** **200** con `TicketRespuesta` (`entrega_confirmada = true` y `etiqueta_proceso =
  «Entregado»`); la fila del historial queda escrita en la misma operación. La UI reconsulta el
  detalle para mostrar la fecha y el actor.
- **Errores, en orden:** **401** sin sesión; **403** rol fuera de la matriz (Administrador,
  Bodeguero, Superadmin) o capacidad `tickets` apagada; **404** pedido inexistente o ajeno
  (idénticos); **409** pedido que no está `Cerrado` y **409** pedido ya confirmado. Sin 422: no
  hay cuerpo que validar.
- **Sin efectos colaterales:** no cambia el estado canónico, `fecha_cierre`, el stock, los
  movimientos ni Compras; no reabre el pedido y no admite una segunda confirmación. Se elige
  **409** y no un 200 idempotente para que el doble envío no pase inadvertido y la UI reconsulte
  la verdad del servidor.
- **Concurrencia:** las confirmaciones del mismo pedido se serializan; la primera escribe la fila
  y la segunda, tras esperar, observa la confirmación y responde **409**. Nunca quedan dos filas
  ni dos respuestas 200. La garantía se verifica en PostgreSQL 16; SQLite no acredita el bloqueo.

#### Interfaz

- El detalle muestra «Confirmar entrega» solo si el estado es `Cerrado`, `entrega_confirmada` es
  `false`, el rol es `Solicitante` y el pedido es del usuario de la sesión. Confirmación previa
  con diálogo nativo (mismo patrón que anulación y rechazo), sin motivo; el botón se deshabilita
  durante la petición (sin doble envío).
- Al 200, mensaje `role="status"` y reconsulta de detalle e historial: la etiqueta pasa a
  «Entregado», aparece «Entregado el {fecha} por {nombre} {apellido}» y el botón desaparece.
- Ante 409 (no está `Cerrado` o ya confirmado) se muestra `role="alert"` con el mensaje del
  servidor y se reconsulta; 404 y 403 conservan su tratamiento.
- El tablero no ofrece la confirmación: sigue siendo de solo lectura y la mutación vive en el
  detalle (D-14).

### 9.10 Derogaciones parciales

- **013 AC-24 y D-14, en lo que exigían «Avanzar» y «Retroceder» desde el detalle:** derogados.
  La barra usa acciones semánticas (Aprobar, Rechazar, Anular, Editar, Despachar, Confirmar
  entrega) y no ofrece transiciones genéricas; ninguna pantalla invoca `PATCH /estado`. El
  `PATCH` se conserva como contrato de API para compatibilidad y legado, con su regla de un paso
  y el cierre reservado al despacho, y la 004 sigue vigente para él. La parte de D-14 que
  concentra las mutaciones en el detalle y mantiene el tablero de solo lectura **no** se deroga.
- **013 AC-17 y 004, en lo que concedían `PATCH /estado` al `Bodeguero`:** derogados. La matriz
  restringe esa entrada a **solo `Administrador`**; el `Bodeguero` recibe **403** y conserva sus
  operaciones propias (`POST /despacho`, `POST /rechazo` y la recepción de compras). No cambia el
  número de operaciones (sigue 73 → 75): cambian los roles de una entrada existente.
- **La regla de auto-avance `EnRevision → EnCurso` por stock de esta misma enmienda:** superada.
  La aprobación va **siempre** a `EnCurso`; el stock solo decide la etiqueta y no hay simulación
  del candidato. AC-28, AC-29 y AC-36 se reescriben en consecuencia y no queda ningún texto que
  haga depender el destino del stock.
- **013 AC-24 y D-14, en lo que exigen o mencionan una columna `Anulado` propia:** derogados.
  El tablero agrupa `Cerrado` y `Anulado` en «Terminados» (D-24); las tarjetas `Anulado` ya no
  tienen columna separada y el contador terminal suma ambos estados. La mención equivalente de
  §3 («el tablero añade la columna `Anulado`») queda superada.
- **013 AC-24, en lo que dice «ninguna acción en `Cerrado` o `Anulado`»:** derogado solo para la
  confirmación de entrega del Solicitante dueño (§9.9). El resto de acciones del ciclo de vida
  sigue sin ofrecerse en los dos terminales, y `Anulado` no admite ninguna.
- **004 AC-1, en lo que exige una columna por cada estado del catálogo:** derogado parcialmente.
  El tablero conserva una columna por estado operativo y una columna terminal agrupada; las
  columnas vacías de los estados operativos se conservan.
- **013 AC-9, aclaración sin derogación:** la confirmación de entrega no es una mutación de
  estado; es un evento del ciclo de vida, como las filas `EnCurso → EnCurso` de la 021. AC-9
  conserva su regla de una fila por mutación de estado y el historial sigue siendo de solo
  lectura por API (AC-10).
- **013 AC-23, ampliación sin derogación:** el detalle sigue mostrando cabecera, ítems e
  historial, y añade la etiqueta de proceso con su frase, los dos responsables y la línea de
  entrega.
- **`fecha_cierre` (D-5) y la terminalidad por nombre (D-4/AC-26):** intactas. La confirmación no
  sella `fecha_cierre`, no reabre `Cerrado` y no crea un estado `Entregado`.

### 9.11 Criterios de aceptación de la ampliación

- [x] **AC-37** DADO un pedido en `Pendiente`, `EnRevision`, `Anulado` o `Cerrado`, CUANDO se
      consulta el listado o el detalle, ENTONCES `etiqueta_proceso` es «En aprobación»
      (`Pendiente`), «En revisión» (`EnRevision` heredado), «Rechazado» (`Anulado`), «Despachado»
      (`Cerrado` sin confirmación) o «Entregado» (`Cerrado` con confirmación), y
      `explicacion_proceso` es la frase corta correspondiente. Un estado fuera del conjunto
      canónico degrada a su nombre visible con la explicación «Estado no reconocido por la
      etiqueta de proceso», sin error de lectura.
  - **Evidencia (25/Nov/2026):** `backend/tests/funcional/unitarios/test_ticket_proceso_013.py` e `integracion/test_ticket_proceso_013.py` (etiquetas y frases de los cinco estados, `Cerrado` con/sin confirmación, degradación de estado desconocido); recorrido 4200 con todas las etiquetas: «En aprobación» (02), «En revisión» (17), «Por comprar» (08), «Facturado» (11), «En confirmación de stock local» (03/13), «Despachado» (04/14) y «Entregado» (05/15).
- [x] **AC-38** DADO un pedido `EnCurso`, ENTONCES la etiqueta se decide por la OC activa más
      avanzada que lo cubre, con la escala **Recibida > Facturada > Emitida**: «En confirmación de
      stock local», «Facturado» y «En compra» respectivamente; una OC `Cancelada` no cuenta. Si no
      hay OC activa, `stock_disponible = true` da «En confirmación de stock local» y `false` da
      «Por comprar». Varias OC del mismo estado no cambian la etiqueta y el resultado no depende
      del orden de las filas ni de la fecha de la OC.
  - **Evidencia (25/Nov/2026):** `test_ticket_proceso_013.py::test_ac_38_*` (precedencia Recibida > Facturada > Emitida, cancelada no cuenta, stock y «Por comprar», orden indiferente); recorrido 4200 con la misma OC: «Por comprar» (08) → «Facturado» (11) → «En confirmación de stock local» tras la recepción (13).
- [x] **AC-39** DADO un pedido, ENTONCES `GET /tickets/` y `GET /tickets/{id}` exponen
      `etiqueta_proceso`, `explicacion_proceso`, `estado_orden_cobertura`, `stock_disponible`,
      `entrega_confirmada`, `gestionado_por_bodeguero` y `gestionado_por_administrador`; el
      detalle agrega `entrega_confirmada_en`, `entrega_confirmada_por_nombre` /
      `entrega_confirmada_por_apellido` y conserva `asignaciones`. La etiqueta del mismo pedido
      coincide en listado, tablero y detalle. Todos son campos de lectura derivados: no hay DDL,
      tabla ni columna nueva. El detalle muestra el estado canónico y, junto a él, la etiqueta y
      la frase.
  - **Evidencia (25/Nov/2026):** `test_ticket_proceso_013.py::test_ac_37_*` y `::test_ac_39_*` (campos en listado y detalle, etiqueta coherente, listas conservadas); recorrido 4200: detalle con estado canónico + etiqueta + frase (02) y tablero coincidente (06/16); contrato en `/openapi.json`.
  - **Corrección post-cierre T31 (25/Nov/2026):** el `201` de `POST /tickets/` también publica el read model (mismo helper que listado y detalle), verificado por `test_ac_39_el_201_*` (gestores según el rol del creador y coincidencia con el listado); no cambia el alta (`Pendiente`, AC-27) ni el contrato de la operación.
- [x] **AC-40** DADO un pedido con filas de historial de varios actores, CUANDO se lee su tarjeta
      o su detalle, ENTONCES se muestra el último actor con rol vigente `Bodeguero` y el último
      con rol vigente `Administrador`, por `fecha_transicion DESC` y
      `historial_transicion_id DESC`, con nombre y apellido; si no hay ninguno de ese rol, se
      muestra «Sin gestión registrada» (`—` en la tarjeta con texto accesible). La fila de
      creación cuenta si su actor tiene el rol; el solicitante sigue mostrándose y no se
      sustituye. Un actor cuyo usuario o rol no se resuelve no cuenta.
  - **Evidencia (25/Nov/2026):** `test_ticket_proceso_013.py::test_ac_40_ultimo_gestor_por_fecha_y_desempate_por_id` y `::test_ac_40_sin_historial_o_sin_rol_gestor_queda_en_none`; recorrido 4200: «Sin gestión registrada» antes (02) y «Illanes, Luciano» / «Gonzalez, Cristian» después (03, 04, 16).
- [x] **AC-41** DADO el tablero, ENTONCES no existe una columna `Anulado` separada: las tarjetas
      `Cerrado` y `Anulado` aparecen en la columna terminal «Terminados», cuyo contador suma
      ambos estados, y cada tarjeta muestra su etiqueta de proceso («Despachado», «Entregado» o
      «Rechazado») y los dos responsables. Las columnas `Pendiente`, `EnRevision` (heredado) y
      `EnCurso` se conservan; el tablero sigue siendo de solo lectura y cada tarjeta sigue siendo
      el enlace al detalle. La etiqueta no depende solo del color, los nombres tienen `aria-label`,
      la descripción accesible de la tarjeta incluye el estado canónico y la frase corta es
      accesible sin depender del hover.
  - **Evidencia (25/Nov/2026):** `frontend/src/app/features/tickets/tickets.component.spec.ts` (4 columnas, «Terminados» con Cerrado+Anulado, sin columna `Anulado`, etiqueta/frase/responsables, tarjeta-enlace); recorrido 4200: tablero final con «Terminados» en 2 (16) y la columna heredada (17).
  - **Corrección post-cierre T31 (25/Nov/2026):** la tarjeta insertada tras el alta muestra «En aprobación» de inmediato, no el nombre canónico: el `201` de `POST /tickets/` devuelve el read model y el spec `la tarjeta del pedido recién creado muestra «En aprobación» (T31)` lo fija.
- [x] **AC-42** DADO un pedido `Cerrado` del Solicitante de la sesión y sin confirmación,
      CUANDO pulsa «Confirmar entrega» y confirma, ENTONCES
      `POST /api/v1/tickets/{ticket_id}/confirmacion-entrega` responde **200**, la etiqueta pasa
      a «Entregado», el detalle muestra «Entregado el … por …» y el botón desaparece; el
      historial registra una fila `Cerrado → Cerrado` con `motivo`
      `Entrega confirmada por el solicitante`, el actor dueño y la fecha del servidor. El estado
      canónico sigue en `Cerrado`, `fecha_cierre` no cambia, no hay movimiento de stock y el
      pedido no se reabre.
  - **Evidencia (25/Nov/2026):** `backend/tests/funcional/integracion/test_ciclo_vida_confirmacion_013.py::test_confirmacion_del_dueno_responde_200_con_una_fila_cerrado_cerrado_ac_42`, `::test_la_confirmacion_no_reabre_ni_mueve_el_pedido_ac_42`, `::test_listado_y_detalle_reflejan_la_entrega_confirmada_ac_42`; recorrido 4200 (capturas 05 y 15) y SQL historial ids 10 y 15 con la línea «Entregado el … por …».
- [x] **AC-43** SI el pedido no existe o es de otro Solicitante, ENTONCES 404 idéntico; SI no
      está `Cerrado`, ENTONCES 409 sin escribir; SI ya está confirmado, ENTONCES 409 sin una
      segunda fila; SI el rol no es `Solicitante` (Administrador, Bodeguero o Superadmin),
      ENTONCES 403 por matriz; sin sesión, 401. La precedencia es 401 → 403 → 404 → 409. Si el
      pedido fue creado por un Administrador o Bodeguero, su dueño no tiene el rol `Solicitante`:
      la acción no se ofrece y el pedido permanece «Despachado» (no hay confirmación de otro rol).
  - **Evidencia (25/Nov/2026):** `test_ciclo_vida_confirmacion_013.py::test_confirmacion_ajena_e_inexistente_responden_404_identico_ac_43`, `::test_confirmacion_no_se_concede_a_otros_roles_ac_43`, `::test_confirmacion_sin_sesion_responde_401_ac_43`, `::test_confirmacion_con_la_capacidad_tickets_apagada_responde_403_ac_43`, `::test_confirmacion_de_un_pedido_no_cerrado_responde_409_sin_escribir_ac_43`, `::test_confirmacion_repetida_responde_409_sin_una_segunda_fila_ac_43`, `::test_un_pedido_creado_por_un_administrador_no_admite_confirmacion_ac_43`; vivo: 403 Administrador y 409 repetida; gated PG: `(200, 409)` con una sola fila.
- [x] **AC-44** DADO QUE se publica el contrato, CUANDO se consultan `/openapi.json` y la matriz
      central, ENTONCES esta pasa de **73 a 75** operaciones v1 por **dos** operaciones nuevas:
      `POST /api/v1/tickets/{ticket_id}/aprobacion` (`Administrador`, capacidad `kanban`) y
      `POST /api/v1/tickets/{ticket_id}/confirmacion-entrega` (`Solicitante`, capacidad
      `tickets`). `/openapi.json` publica **77** entradas (75 v1 + `GET /` + `/health`); las 73
      operaciones previas conservan sus roles y códigos **salvo el `PATCH /estado`, que pasa a
      solo `Administrador`** (AC-49). No se agregan capacidades, guards, estados canónicos,
      tablas, columnas, semillas ni versiones de esquema. `PATCH /estado` y `POST /despacho`
      conservan su contrato de transición; el `PATCH` deja de anunciar un destino efectivo
      distinto del solicitado.
  - **Evidencia (25/Nov/2026):** `backend/tests/no_funcional/seguridad/test_permisos_endpoints.py` (inventario rutas↔matriz) y `test_cobertura_021.py::test_openapi_publica_el_preview_y_75_operaciones`; `GET /openapi.json` del backend vivo: **77** entradas (75 v1 + `GET /` + `/health`), aprobación `Administrador`/`kanban` y confirmación `Solicitante`/`tickets`; sin capacidades, estados, tablas ni versiones nuevas.
- [x] **AC-45 (aprobación Admin-only)** DADO un pedido en `Pendiente` o `EnRevision`, CUANDO
      invoca `POST /api/v1/tickets/{ticket_id}/aprobacion` un Administrador, ENTONCES 200; el
      Bodeguero, el Solicitante y el Superadmin reciben 403 por matriz, y el Administrador con la
      capacidad `kanban` apagada también 403. La operación no concede nada a los demás roles.
  - **Evidencia (25/Nov/2026):** `test_ciclo_vida_aprobacion_013.py::test_aprobacion_no_se_concede_a_otros_roles_ac_45`, `::test_aprobacion_con_kanban_apagada_responde_403_sin_mutar_ac_45`, `::test_matriz_declara_la_aprobacion_y_el_patch_solo_para_administrador_ac_44`; vivo: 403 Bodeguero y 409 ya `EnCurso`; 4200: «Aprobar» visible solo con Administrador (02/03).
- [x] **AC-46 (aprobación: estados y códigos)** DADO un pedido, CUANDO se aprueba, ENTONCES:
      inexistente o de otra institución → 404 idéntico; ya `EnCurso`, `Cerrado` o `Anulado` →
      409; estado no elegible → 409; catálogo sin `EnCurso` → 409 sin escribir; sin sesión → 401.
      La precedencia es 401 → 403 → 404 → 409; no hay payload obligatorio ni 422 por cuerpo. Un
      error no escribe historial ni cambia el estado.
  - **Evidencia (25/Nov/2026):** `test_ciclo_vida_aprobacion_013.py::test_aprobacion_de_un_estado_ya_avanzado_o_terminal_responde_409_ac_46`, `::test_aprobacion_de_un_estado_no_elegible_responde_409_sin_escribir_ac_46`, `::test_aprobacion_sin_en_curso_en_el_catalogo_responde_409_sin_escribir_ac_46`, `::test_aprobacion_inexistente_y_ajena_responden_404_identico_ac_46`, `::test_aprobacion_sin_sesion_responde_401_ac_46`; vivo 403/409; sin payload obligatorio.
- [x] **AC-47 (EnRevision heredado)** DADO el flujo nuevo, ENTONCES ningún pedido nuevo pasa por
      `EnRevision` desde la UI; el estado sigue en el catálogo y el tablero conserva su columna
      para los heredados; un pedido existente en `EnRevision` se aprueba, rechaza o anula con las
      mismas acciones. El `PATCH` de legado puede seguir produciendo `EnRevision` por API, pero
      no lo usa ninguna pantalla.
  - **Evidencia (25/Nov/2026):** Recorrido 4200: el alta fija `Pendiente` (D-11) y ninguna pantalla produce `EnRevision`; el tablero conserva la columna con 3 heredados (#3, #4, #9) y #9 ofrece Aprobar/Rechazar/Anular (captura 17); solo el `PATCH` de legado puede producir `EnRevision` (vivo, §10.5 de la evidencia).
- [x] **AC-48 (sin botones genéricos y PATCH de legado)** DADO el detalle de un pedido, ENTONCES
      no ofrece «Avanzar» ni «Retroceder» y no invoca `PATCH /estado`; el `PATCH` sigue disponible
      **solo para el Administrador** en la API, con su regla de un paso, el cierre
      `EnCurso → Cerrado` reservado al despacho y `Cerrado`/`Anulado` terminales, para
      compatibilidad y legado.
  - **Evidencia (25/Nov/2026):** Specs de detalle y tablero (sin Avanzar/Retroceder ni `PATCH`); recorrido 4200 con acciones semánticas (02-05, 08, 13); vivo: `PATCH` **403** para Bodeguero y **200/409** para Administrador.
- [x] **AC-49 (rol del `PATCH` de legado)** DADO un Bodeguero, CUANDO invoca
      `PATCH /api/v1/tickets/{ticket_id}/estado`, ENTONCES recibe **403** por matriz; el
      Administrador conserva la operación con su contrato de un paso, el cierre reservado al
      despacho y la terminalidad. `POST /despacho`, `POST /rechazo` y la recepción de compras
      conservan sus roles (Bodeguero/Administrador donde corresponda). La matriz sigue en **75**
      operaciones: cambian los roles de una entrada existente, no su número.
  - **Evidencia (25/Nov/2026):** Vivo: `PATCH` del Bodeguero **403** y del Administrador **200/409**; `test_ciclo_vida_aprobacion_013.py::test_el_bodeguero_conserva_despacho_y_rechazo_ac_49`; matriz en **75** operaciones (misma cuenta, cambian los roles de una entrada).

**Cierre de la enmienda.** No se marca cerrada hasta que `pytest`, `ng test` y `ng build` estén
en verde, `/openapi.json` publique 75 operaciones v1, y el recorrido se haga en los dos puertos
conforme a `AGENTS.md` §8.5–§8.6: 4200 con escritura real (aprobación, despacho y confirmación de
entrega) y humo en 8080 con la imagen reconstruida.

### 9.12 Relación con las Features 005, 020 y 021

- **005 (despacho transaccional):** se conserva sin cambios. Esta enmienda incorpora en el
  detalle la acción que invoca su endpoint con el `usuario_id` de la sesión y cierra la exclusión
  de frontend de su §3. La aprobación del Administrador es un paso **previo** y la confirmación de
  entrega un evento **posterior** al despacho: ninguna cambia su contrato, su ACID, sus códigos ni
  su bloqueo, que siguen siendo la única vía a `Cerrado`.
- **020 (reabastecimiento):** `calcular_cobertura_tickets`, `stock_disponible`, la recepción, el
  desbloqueo `EnCurso → EnCurso` y la regla de no comprar lo cubierto se conservan. La aprobación
  **no evalúa stock**; la etiqueta de proceso (§9.8) **lee** `stock_disponible` (solo `EnCurso`) y
  el estado de las OC, sin recalcular ni cambiar la simulación de la 020.
- **021 (cobertura automática):** el plan de `orden_compra_ticket`, la necesidad neta parcial, el
  preview y la cadena de la OC no cambian. Un pedido aprobado por el Administrador entra a
  `EnCurso` y participa desde entonces de la demanda y del plan; uno en `Pendiente` o `EnRevision`
  sigue fuera hasta la aprobación. Las OC no intervienen en la decisión de aprobación (no se
  descuenta `plan_previo`). La etiqueta de proceso solo **lee** el estado de las OC que cubren el
  pedido (Recibida > Facturada > Emitida; `Cancelada` no cuenta) y no reescribe el plan; la
  confirmación de entrega reutiliza el precedente de evento sin cambio de estado que la 021
  estrenó con `EnCurso → EnCurso`.
- **Qué enmienda la 013 a sí misma:** el flujo de la UI de D-13/D-14 —que ahora usa acciones
  semánticas y no «Avanzar»/«Retroceder»—, el alcance del detalle (despacho, etiqueta,
  responsables y confirmación de entrega) y las derogaciones parciales de §9.10 (columna
  `Anulado`, «ninguna acción en `Cerrado`», columna por estado de la 004 y avance/retroceso
  genéricos). El `PATCH /estado` conserva su contrato de transición —un paso, cierre reservado y
  terminalidad— y su papel de legado, pero la UI ya no lo usa y **pasa a concederse solo al
  Administrador**; el Bodeguero conserva despacho, rechazo y recepción. Los AC-1…AC-27 no se
  reescriben, salvo las derogaciones expresas de §9.10. La matriz gana **dos** operaciones
  (aprobación y confirmación de entrega), el `PATCH` cambia de rol y el resto del contrato se
  conserva.
