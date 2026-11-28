# Feature 004 — Plan Técnico

Spec: `spec.md` (**aprobada**). Este plan no toca código de negocio hasta que `tasks.md` exista (`AGENTS.md` §7).

## 1. Inventario de archivos

### Backend (seam HTTP, `pytest` sobre SQLite en memoria)

| Archivo | Qué hace |
|---|---|
| `app/services/ticket_service.py` | Núcleo de la feature: reglas de flujo y sellado en `actualizar_estado_ticket()`; sellado de alta en `crear_ticket()`; orden + eager loading en `listar_tickets()`; **borrar** `ESTADO_CERRADO_ID` y su comentario (L29-33) |
| `app/api/v1/endpoints/tickets.py` | Solo documentación OpenAPI: `description` de `PATCH /tickets/{id}/estado` (flujo lineal, 404/409, sellado) y de `GET /tickets/` (orden de respuesta). Sin lógica |
| `tests/funcional/integracion/test_tablero_kanban.py` | **Nuevo**: fixture de catálogo canónico + todos los tests de flujo, sellado, orden y conteo de queries |
| `tests/conftest.py` | Solo el comentario de L104-107 (mención a `ESTADO_CERRADO_ID`, AC-25) |
| `tests/funcional/humo/test_smoke.py` | Verificar que sigue verde (INGRESADO→CERRADO es un paso adyacente en su catálogo de 2 estados); sin cambios salvo que falle |

`app/schemas/ticket_schema.py` **no cambia**: `TicketRespuesta` ya expone todo lo que la tarjeta necesita y el contrato de la 003 se conserva.

### Frontend (seam componente, `ng test`)

| Archivo | Qué hace |
|---|---|
| `features/tickets/tickets.component.ts` | Reemplazar el `columnas` de datos demo por señales reales (`tickets`, filtros, error/carga), `columnas` como `computed`, botones de avanzar/retroceder y `mover()` |
| `features/tickets/tickets.component.html` | Barra de filtros, columnas del catálogo, tarjetas reales con botones, estados vacío (AC-5) y de error (§7), `role="alert"` para rechazos (AC-20) |
| `features/tickets/tickets.component.spec.ts` | Reescribir los tests que asumen el tablero demo (L406-411 esperan 4 columnas fijas) y añadir los del resto de AC de frontend |
| `features/tickets/services/ticket.service.ts` | **Sin cambios**: `obtenerTickets()` y `actualizarEstado()` ya existen |

`shared/interfaces/index.ts` **sin cambios**: `Ticket`, `EstadoTicket`, `Prioridad` y `Solicitante` ya tienen los campos (su comentario L132-134 ya anticipaba esta feature).

### Base de datos y documentación (solo comentarios y cierre)

| Archivo | Qué hace |
|---|---|
| `database/02_datos_semilla.sql` | Reescribir los comentarios que fijan el id 4 (L45-48, L220-221). **Ni una coma de DDL ni de datos** (AC-26) |
| `MEMORY.md` | Actualizar estado de la 004 y limpiar la mención final de la deuda (AC-25) |
| `docs/spec/roadmap.md` | Cierre de la fila 004 **al final**, tras verificación (§8.5) |
| `docs/spec/features/004-tablero-kanban/tasks.md` | Se genera con `/sdd-tasks`; no forma parte de este plan |

## 2. Orden de ejecución (TDD: rojo antes que verde)

1. **Fixture `datos_flujo_canonico`** en `test_tablero_kanban.py`: apoyándose en `datos_base`, inserta 4 estados en orden canónico (`Pendiente → EnRevision → EnCurso → Cerrado`). Tests rojos de transición (AC-9, AC-10, AC-13, AC-14, AC-15).
2. Implementar la validación de flujo + sellado en `actualizar_estado_ticket()` → verde (AC-16, AC-18).
3. Test rojo: alta en estado llamado `Cerrado` sella `fecha_cierre` (AC-17) → implementar en `crear_ticket()` → verde.
4. Tests rojos de `GET /tickets/`: orden `fecha_creacion DESC, ticket_id DESC` y número de queries constante (AC-27) → migrar `listar_tickets()` a `select()` + `selectinload` → verde.
5. **Frontend — tablero**: tests rojos de columnas desde catálogo, agrupación y orden (AC-1, AC-2) → cargar `catalogos` + `tickets` en la construcción del componente y construir el `computed` de columnas → verde.
6. Filtros: tests rojos de prioridad, búsqueda (acentos, mayúsculas, `%`/`_` literales), intersección y contadores (AC-3, AC-6, AC-7) → verde. Vacío vs error (AC-5).
7. Botones y mover: tests rojos de visibilidad según posición en el flujo (AC-11, AC-12), éxito con anti-doble-envío (AC-19) y rechazo con alerta + reconsulta (AC-20) → verde. Alta desde el modal reflejada en el tablero (AC-8).
8. Limpieza documental de comentarios (semilla, conftest, docstring del componente) — AC-25 parcial.
9. Verificación: `pytest` completo + `ng test --watch=false` (AC-21), `ng build` (AC-22), recorrido en 4200 (AC-23) y en 8080 tras `docker compose build frontend` (AC-24), grep y cierres (AC-25, AC-26).

## 3. Decisiones técnicas

### 3.1 El tablero se arma con los dos endpoints existentes y el join en el cliente

`GET /tickets/catalogos` (estados ya ordenados por `estado_id`, prioridades, solicitantes) + `GET /tickets/` (tickets ya ordenados por AC-27). El componente agrupa por `estado_id` y resuelve nombres con el catálogo. Una carga de `catalogos()` al construir el componente, sin tocar el modal.

**Descartada**: endpoint nuevo `GET /tickets/tablero` con read model — DTO y ruta nuevos, duplica información que esas dos consultas ya traen, y la spec no pide contrato nuevo. Consecuencia a favor: `TicketRespuesta` y el modelo no cambian.

### 3.2 Las reglas de flujo viven en el service, contra una sola carga del catálogo

En `actualizar_estado_ticket()`, en este orden (D-8): (1) `db.get(Ticket)` → 404; (2) `select(EstadoTicket).order_by(estado_id)` y buscar el estado pedido → 404 si falta; (3) con los índices en la lista ordenada: mismo índice → 409; distancia ≠ 1 → 409; índice actual = último → 409 (terminal no sale). El mismo `select` alimenta el paso de sellado. Un solo commit al final: estado + fecha atómicos (§7).

**Descartada**: validar en el endpoint (mezcla HTTP con negocio, contra la regla de oro de `stack.md` §2); `CHECK` en el DDL — `AGENTS.md` §7 prohíbe tocar el modelo y en SQLite (la suite) los CHECK no existen (MEMORY).

### 3.3 El cierre se reconoce por nombre en la lista ya cargada

Comparación `nombre.casefold() == "cerrado"` sobre el catálogo cargado en el paso anterior. La fecha se escribe **solo si `ticket.fecha_cierre is None`**: reentrar en `Cerrado` nunca sobrescribe (D-3, AC-16).

**Descartada**: la constante `ESTADO_CERRADO_ID` (es la deuda H-2 que AC-25 elimina); una consulta `WHERE lower(nombre)='cerrado'` aparte — duplica el acceso al catálogo que ya se tiene en mano.

### 3.4 `listar_tickets`: orden explícito y colecciones eager (AC-27)

Migrar de `db.query()` a `select(Ticket).options(selectinload(Ticket.detalles).selectinload(DetalleTicket.producto)).order_by(Ticket.fecha_creacion.desc(), Ticket.ticket_id.desc())`, manteniendo el filtro opcional `estado_id` (y corregiendo su chequeo a `is not None`). El `selectinload` en cadena evita el N+1 de `detalles` **y** del `producto` anidado que `DetalleTicketRespuesta` serializa.

**Descartada**: quitar `detalles` de la respuesta (rompe el contrato que la 003 verificó en OpenAPI); endpoint aparte para el tablero (ya cubierto por 3.1).

### 3.5 Filtros en cliente, sobre el conjunto ya cargado

Todo el filtrado vive en el `computed` de columnas: prioridad por `prioridad_id`, búsqueda sobre `asunto` normalizado (`NFD` + quitar marcas + `toLowerCase`) con el texto recortado. Al no haber `LIKE` en SQL, `%` y `_` son literales por construcción (D-6, AC-7). Intersección = ambos predicados en el mismo filtro; los contadores salen de `filtrados.length`.

**Descartada**: query params de filtro en el backend — la spec dice explícitamente "sobre el conjunto ya cargado", y forzaría a definir acentos y comodines en SQL.

### 3.6 Frontend: señales reales, columnas computadas, botones por posición

- `columnas` deja de ser un `signal` con datos quemados y pasa a `computed` a partir de `tickets()`, `estados()` y las señales de filtro (orden del catálogo = orden de columnas, D-1).
- Validez de los botones = posición en la lista de estados: índice > 0 → "retroceder"; índice < último → "avanzar"; último → ningún control (AC-11, AC-12). El componente nunca compara nombres.
- `mover(ticket, destino)` con `enProceso = signal<Set<number>>`: los botones de esa tarjeta quedan deshabilitados mientras vuelva (AC-19). **Éxito**: la respuesta del `PATCH` reemplaza el ticket en `tickets()` — la tarjeta cambia de columna sin recarga. **Fallo** (404, 409, red): la tarjeta no se toca, se publica el mensaje con `role="alert"` y se vuelve a consultar el tablero entero (`D-7`, AC-20).
- Alta del modal: la respuesta de `POST` se agrega a `tickets()`; los filtros activos la admite o no el mismo `computed` (AC-8).
- Estados de carga y error del tablero propios (§7): error visible con reintento, nunca pantalla en blanco.

**Descartado**: rollback optimista local (puede volver a mentir y no reconsulta); RxJS `BehaviorSubject` — `AGENTS.md` §6 manda signals.

### 3.7 Alta en `Cerrado` sella fecha en `crear_ticket()`

Después de `_verificar_referencia(estado)`, si el estado recuperado (`db.get`, ya no solo comprobación de existencia) pasa el test de nombre, se asigna `fecha_cierre = datetime.utcnow()` antes del `add()`; todo entra en la misma transacción que los detalles (AC-17, D-4).

**Descartada**: rechazar el alta en estado de cierre — cambiaría el formulario de la 003, que está fuera de alcance; sellar en el frontend — el cliente no es fuente de verdad.

## 4. Casos de prueba

### 4.1 Backend — `tests/funcional/integracion/test_tablero_kanban.py` (nuevo)

Fixture `datos_flujo_canonico` (apoyada en `datos_base`, patrón de `datos_catalogo_ticket`): 4 estados en orden canónico con `Cerrado` al final.

- **Flujo**: avanzar `Pendiente→EnRevision` 200; retroceder `EnCurso→EnRevision` 200; salto `Pendiente→EnCurso` 409; estado repetido 409; retroceso desde `Cerrado` 409; id de estado inexistente 404; ticket inexistente 404; combinación ticket+estado inexistentes responde 404 **de ticket** (D-8).
- **Sellado**: transición a `Cerrado` (nombre en minúsculas para probar case-insensitivity) con `fecha_cierre` no nula y respuesta 200; reentrada en `Cerrado` con fecha ya existente no la sobrescribe; transiciones normales no tocan la fecha; cambiar ids/orden del catálogo no rompe el sellado (AC-18).
- **Alta**: `POST` con estado `CERRADO` devuelve `fecha_cierre` con valor; con estado normal, `None` (AC-17).
- **Listado (AC-27)**: `GET /tickets/` ordenado `fecha_creacion DESC, ticket_id DESC` (empates incluidos); conteo de queries con listener `before_cursor_execute` sobre el motor de la fixture: el número de consultas **no crece** al pasar de 1 a 3 tickets con detalles (en vez de un número exacto, que sería frágil ante `PRAGMA` de SQLite).
- **OpenAPI**: `PATCH` documenta 404/409 y `GET /tickets/` documenta el orden (AGENTS §11).

Tests existentes que deben seguir en verde sin reescribirse: `test_smoke` (su catálogo de 2 estados hace `INGRESADO→CERRADO` adyacente), `test_transaccion_ticket`, `test_modal_ticket` (ninguno transiciona saltos). Ojo: `datos_catalogo_ticket` termina en `INGRESADO_TEST`, **no** en un estado llamado `Cerrado` — cualquier test futuro que transicione ahí debe calcular vecinos por posición o usar la fixture canónica.

### 4.2 Frontend — `tickets.component.spec.ts` (`HttpTestingController`, patrón ya presente)

- Carga inicial: dos peticiones (`catalogos`, `tickets`); columnas = estados del catálogo en orden, con contador (AC-1, AC-3); tickets agrupados y ordenados por fecha DESC con empate por `ticket_id` (AC-2).
- Tarjeta muestra asunto, prioridad, solicitante, fecha de creación y, si existe, cierre (AC-4).
- Filtro de prioridad; búsqueda con mayúsculas/acentos, `%`/`_` como texto y vacío = sin filtro; intersección; contadores afectados (AC-6, AC-7); columna vacía con mensaje diferenciable del error (AC-5); alta del modal visible sin recarga y fuera si los filtros la excluyen (AC-8).
- Botones: ninguno en el último estado, sin "retroceder" en el primero, sin saltos ofrecidos (AC-11, AC-12).
- `mover()` con éxito: `PATCH` correcto → la tarjeta cambia de columna, contadores cambian y botón deshabilitado durante el envío (AC-9, AC-10, AC-19). Con `409`: no se mueve, aparece `role="alert"` y se emite la reconsulta `GET /tickets/` (AC-20).

## 5. Cobertura AC → pieza

| AC | Pieza principal |
|---|---|
| AC-1 … AC-8 | Frontend: `computed` de columnas, filtros, alta reflejada (tests 4.2) |
| AC-9, AC-10 | Backend valida + frontend `mover()` (tests 4.1 y 4.2) |
| AC-11, AC-12 | Frontend: visibilidad por índice; backend rechaza lo que llegue igual (4.1) |
| AC-13 … AC-15 | Backend: `actualizar_estado_ticket()` (tests 4.1) |
| AC-16, AC-18 | Backend: sellado por nombre, sin sobrescribir (tests 4.1) |
| AC-17 | Backend: `crear_ticket()` (test 4.1) |
| AC-19, AC-20 | Frontend: anti-doble-envío, alerta y reconsulta (tests 4.2) |
| AC-21, AC-22 | `pytest` + `ng test` + `ng build` |
| AC-23, AC-24 | Recorrido manual en 4200 y 8080 (con `docker compose build frontend`) |
| AC-25, AC-26 | Cierre documental: grep, roadmap, `MEMORY.md`, diff sin cambios estructurales |

## 6. Riesgos

- **Tests previos con supuestos distintos**: los del tablero demo (4 columnas fijas) y cualquier transición que hoy no valida flujo. Se ejecuta `pytest`/`ng test` desde la fase 1 para detectarlos pronto.
- **Conteo de queries en SQLite**: `PRAGMA` y transacciones internas ruidosas; por eso la aserción es "no crece con el número de tickets", no "es igual a N".
- **Terminal ≠ nombre**: en catálogos degenerados el terminal es la última posición, no `Cerrado`; los tests de la 004 usan la fixture canónica y uno aparte prueba el caso degenerado (§7).
- **8080 no ve cambios sin reconstruir** la imagen del frontend (`AGENTS.md` §8.6); el backend sí se recarga solo.
- **Concurrencia**: sin control de versión (límite declarado); dos pestañas lo cubre el recorrido de AC-23.

## 7. Enmienda 27/Nov/2026: filtro de periodo y orden del tablero

Spec: `spec.md` §8 (D-9…D-12, AC-28…AC-30), aprobada por el usuario el 28/Nov/2026; la línea
`Estado:` de la portada se actualiza al cerrar (T12), porque este plan no edita `spec.md`. Es un
cambio **solo de frontend**: no toca backend, `ticket.service.ts`, DDL, permisos, matriz ni
`stack.md`. El tablero sigue con las tres columnas de la 013 §10 (`EnRevision`, `EnCurso` y
«Terminados»). Este plan se ejecuta con **T11** y **T12**; no reabre AC-2, AC-6, AC-7 ni el cierre
histórico de la 004.

### 7.1 Inventario de archivos

| Archivo | Qué hace |
|---|---|
| `frontend/src/app/features/tickets/tickets.component.ts` | Señales `filtroPeriodo` y `orden`; tipos `PeriodoTablero`/`OrdenTablero`; helper puro `inicioDePeriodo(periodo, ahora)`; periodo en el predicado de `columnas` **antes** de agrupar; comparador de orden **después**, dentro de cada columna; `hayFiltros` con el periodo. |
| `frontend/src/app/features/tickets/tickets.component.html` | Dos `<select>` nativos con `<label>` visible «Periodo» y «Orden» en la barra de filtros, valores estables y clases Tailwind; sin CSS embebido. |
| `frontend/src/app/features/tickets/tickets.component.spec.ts` | Reloj fijo con `jasmine.clock().mockDate(...)`; fixture de fechas relativas (hoy, 3, 10, 40 y 400 días); tests de AC-28…AC-30 y regresión de AC-2/AC-6/AC-7. |

**Sin cambios:** `frontend/src/app/features/tickets/services/ticket.service.ts`, cualquier archivo
de `backend/`, `database/`, `stack.md` y la 013/018. No hay endpoint, parámetro ni DTO nuevos.

### 7.2 Estado y cadena de cálculo

```ts
type PeriodoTablero = 'todo' | 'hoy' | 'semana' | 'mes' | 'anio';
type OrdenTablero = 'recientes' | 'antiguos';

readonly filtroPeriodo = signal<PeriodoTablero>('todo');
readonly orden = signal<OrdenTablero>('recientes');
```

`hayFiltros` pasa a incluir el periodo: verdadero si `filtroPeriodo() !== 'todo'`, si
`filtroPrioridad() !== null` o si `busqueda().trim() !== ''`. El orden **no** entra: no recorta
nada. El `computed` de `columnas` mantiene una sola cadena:

1. **Filtrar** el conjunto cargado con la intersección `prioridad ∧ búsqueda ∧ periodo` (D-11).
   Un ticket se conserva solo si cumple los tres; «todas», búsqueda vacía y `todo` son inactivos.
2. **Agrupar** los filtrados en las tres columnas vigentes por `estado_ids` (sin cambio).
3. **Ordenar** las tarjetas de cada grupo con el comparador que elige `orden()` y recién ahí
   resolver `TarjetaKanban`.

Los contadores siguen siendo `tarjetas.length` del grupo ya filtrado y ordenado (misma fórmula de
AC-3): no se agrega una señal de contador. El vacío conserva la distinción de AC-5 y ahora también
es «por filtros» cuando el único filtro activo es el periodo.

**Descartada:** un `computed` aparte para el periodo aplicado después de agrupar —duplicaría el
recorrido y abriría la puerta a que contadores y vacío se desincronicen—; ordenar antes de agrupar
—el `sort` se perdería al repartir en columnas y habría que reordenar igual—.

### 7.3 Periodo: helper puro, calendario local y reloj determinista

`inicioDePeriodo(periodo: PeriodoTablero, ahora: Date): Date | null` es una función pura y
exportada desde el componente:

| `periodo` | Retorno |
|---|---|
| `todo` | `null` (sin recorte) |
| `hoy` | `new Date(anio, mes, dia)` → `00:00:00.000` local de hoy |
| `semana` | lunes local de la semana actual: `new Date(anio, mes, dia - ((getDay() + 6) % 7))` |
| `mes` | `new Date(anio, mes, 1)` → día 1 a las `00:00:00.000` local |
| `anio` | `new Date(anio, 0, 1)` → 1 de enero a las `00:00:00.000` local |

Se construye por **campos de calendario locales**, nunca restando 24 h ni milisegundos: así el
borde de lunes, de día 1 y de 1 de enero no se mueve con un cambio de horario, y el desborde de
mes se resuelve solo (si hoy es martes 1, `dia - 1` cae en el último día del mes anterior). El
predicado es `new Date(ticket.fecha_creacion).getTime() >= inicio.getTime()`: borde **inclusivo**,
**sin cota superior** y **sin mirar `fecha_cierre`**. La comparación usa la misma interpretación
local de la fecha que ya usa la tarjeta al pintarla, de modo que «Hoy» coincide con lo que la
tarjeta muestra como hoy.

`ahora` se recibe por parámetro (inyectable en las pruebas unitarias del helper). En las pruebas
de componente se fija el reloj con `jasmine.clock().install()` +
`jasmine.clock().mockDate(FECHA_FIJA)` en el `beforeEach` del bloque nuevo y se restaura en
`afterEach`; el componente sigue llamando a `new Date()` en producción. `columnas` es `computed`:
se recalcula al cambiar `filtroPeriodo`, por lo que el reloj fijado se aplica al leerlo después del
cambio.

**Descartada:** un `InjectionToken` de reloj en producción —agrega superficie y wiring solo para
probar—; calcular el borde restando milisegundos (`Date.now() - 7*24*3600*1000`) —falla en cambios
de horario y en el borde de lunes—; filtrar por `fecha_cierre` o en el backend —D-9 y AC-27—.

### 7.4 Orden: comparador por columna

`ordenarTarjetas(a: Ticket, b: Ticket, orden: OrdenTablero)` (privado) o el comparador inline
equivalente:

- `recientes`: `Date.parse(b.fecha_creacion) - Date.parse(a.fecha_creacion)` y, si empatan,
  `b.ticket_id - a.ticket_id`.
- `antiguos`: `Date.parse(a.fecha_creacion) - Date.parse(b.fecha_creacion)` y, si empatan,
  `a.ticket_id - b.ticket_id`.

Se aplica a **cada** grupo, incluida «Terminados». El orden es total porque `ticket_id` es único;
no hay empates sin resolver. No cambia la pertenencia, los contadores ni `hayFiltros`, y cambiar
solo el selector no dispara HTTP.

**Descartada:** confiar en el orden de `GET /tickets/` (AC-27 ya entrega recientes, pero no
antiguos, y la agrupación por estado lo rompe); ordenar una vez el arreglo global antes de agrupar
—cada columna necesita su propio orden y el reparto lo invalida—.

### 7.5 Filtros, contadores, vacío y alta

- **Intersección:** el periodo se suma al mismo `.filter()` que ya aplica prioridad y búsqueda
  (plan §3.5), antes de agrupar. No hay un segundo recorrido.
- **Contadores:** `tarjetas.length` del grupo filtrado (AC-3); no cambia la fórmula.
- **Vacío:** `hayFiltros()` decide entre «Ningún pedido coincide con los filtros» (periodo,
  prioridad o búsqueda activos) y «Sin pedidos en esta columna» (sin ninguno), como en AC-5.
- **Alta (AC-8):** la respuesta del `POST` se inserta en `tickets()` como hoy. Su
  `fecha_creacion` es el instante de creación, mayor o igual que el inicio de cualquier periodo
  calendario vigente, así que cae dentro de `hoy`/`semana`/`mes`/`anio` sin lógica especial; el
  mismo `computed` la agrupa, la ordena y la excluye si prioridad o búsqueda no la admiten. Sin
  recarga y sin peticiones adicionales.
- **Sin persistencia:** las señales nacen en `todo` y `recientes` en cada instancia; no se
  sincronizan con URL ni almacenamiento.

### 7.6 Plantilla y accesibilidad

Se agregan dos `<label>` + `<select>` nativos en la barra de filtros existente, junto a
«Prioridad» y «Buscar por asunto»:

- **Periodo:** `<label>` visible «Periodo»; opciones con valores `todo`, `hoy`, `semana`, `mes` y
  `anio` y textos «Todo el tiempo», «Hoy», «Esta semana», «Este mes» y «Este año».
- **Orden:** `<label>` visible «Orden»; valores `recientes` y `antiguos` con textos «Más
  recientes» y «Más antiguos».

Ambos usan clases Tailwind como los controles vecinos, sin `styles` ni CSS embebido. El valor se
lee con `(change)` y se normaliza al tipo de la señal; no se usan `[ngModel]` ni formularios
reactivos para estos dos controles de presentación. Los `<label>` envuelven al `<select>` (patrón
ya usado en la barra) para que el nombre accesible quede asociado sin `id` adicional.

**Descartada:** un desplegable propio con `div`/botones —teclado y ARIA a mano sin ganancia—;
persistir la selección en la URL —D-12—.

### 7.7 Pruebas (`ng test`)

En `tickets.component.spec.ts`, un `describe('periodo y orden del tablero (AC-28…AC-30)')` con
reloj fijo:

- **Reloj:** `FECHA_FIJA = new Date(2026, 10, 28, 15, 0, 0)` (sábado 28/Nov/2026, hora local).
  `beforeEach`: `jasmine.clock().install(); jasmine.clock().mockDate(FECHA_FIJA)`;
  `afterEach`: `jasmine.clock().uninstall()`.
- **Fixture `TICKETS_PERIODO`** construida con `fechaHaceDias(n)` sobre la fecha fija: `0` (hoy),
  `3` (25/Nov), `10` (18/Nov), `40` (19/Oct/2026) y `400` (24/Oct/2025), repartidos entre
  `EnRevision`, `EnCurso` y «Terminados» y con prioridades distintas. La matriz esperada es:
  `todo` → 5; `hoy` → 1; `semana` (lunes 23/Nov) → 2; `mes` (1/Nov) → 3; `anio` (1/Jan/2026) → 4.
- **Bordes unitarios del helper:** `inicioDePeriodo` con `FECHA_FIJA` devuelve
  `new Date(2026, 10, 28)`, `new Date(2026, 10, 23)`, `new Date(2026, 10, 1)` y
  `new Date(2026, 0, 1)`; `todo` → `null`.
- **Bordes de componente:** tickets exactamente en el inicio (incluidos) y en `inicio - 1 ms`
  (excluidos) para hoy, semana, mes y año; un ticket con `fecha_creacion` anterior y
  `fecha_cierre` dentro del periodo no aparece (D-9); un ticket con fecha posterior al reloj fijo
  sigue apareciendo (sin cota superior).
- **Orden:** `recientes` por defecto (AC-2) y `antiguos` en cada columna; desempate con los
  tickets 3 y 4 de `TICKETS` (misma `FECHA_EMPATE`): `antiguos` → `[3, 4]`, `recientes` → `[4, 3]`;
  «Terminados» con `TICKETS_013` (tres terminales) en ambos sentidos; `httpMock.expectNone` al
  cambiar solo el orden.
- **Combinación y vacío:** `mes` + prioridad + búsqueda deja la intersección; contadores por
  columna; una columna vacía con solo `semana` activo muestra «Ningún pedido coincide con los
  filtros»; sin filtros, «Sin pedidos en esta columna».
- **Alta:** el `POST` se responde con un `Ticket` cuya `fecha_creacion` es la fecha fija (no el
  `ticketRespuesta` de 2026-10-07, que quedaría fuera de `hoy`/`semana`/`mes`), se elige `hoy` y se
  comprueba que aparece sin recarga, ordenado y sujeto a prioridad/búsqueda; al remontar el
  componente, `filtroPeriodo()` vuelve a `todo` y `orden()` a `recientes`.
- **Regresión:** los tests de AC-2, AC-6 y AC-7 no se reescriben; el fixture `TICKETS` con fechas
  de octubre de 2026 sigue funcionando porque el valor por defecto es `todo`.

No se toca `inventario.component.spec.ts` ni ninguna suite fuera de tickets.

### 7.8 Cobertura AC → pieza

| AC | Pieza principal |
|---|---|
| AC-28 | `inicioDePeriodo` + predicado de `columnas` + selector de periodo; tests de matriz y bordes |
| AC-29 | Comparador de orden por columna + selector de orden; tests de ambos sentidos y desempate |
| AC-30 | `computed` único, `hayFiltros`, contadores, vacío y alta; tests de combinación y remontaje |
| AC-2, AC-6, AC-7 | Sin cambios: quedan como regresión; `recientes` es su valor por defecto |

### 7.9 Riesgos

- **Zona horaria:** `fecha_creacion` llega sin marca de zona y se interpreta local, igual que la
  pinta la tarjeta. El helper construye bordes locales; no se convierte a UTC ni se resta una
  duración fija. Un test fija el reloj para que el borde no dependa de la hora de ejecución.
- **Bordes de lunes, día 1 y 1 de enero:** se prueban explícitamente con el reloj fijo en sábado
  28/Nov/2026; el cálculo por campos (`dia - desplazamiento`) cubre el cruce de mes.
- **Doble orden (filtro vs presentación):** el periodo filtra antes de agrupar; el orden se aplica
  solo al final, dentro de cada columna. Un test verifica que cambiar el orden no altera
  contadores, vacío ni peticiones.
- **No romper el alta ni los contadores:** el alta se sigue insertando en `tickets()` y el
  `computed` la procesa; los contadores conservan `tarjetas.length`. Los tests de AC-3 y AC-8 se
  ejecutan como regresión.
- **Fixtures viejas con «hoy»:** `TICKETS` y `TICKETS_FILTROS` usan fechas de octubre de 2026; no
  deben usarse para probar `hoy`/`semana` sin recalcularlas. La fixture nueva es relativa al reloj
  fijo.

### 7.10 Línea base y cierre

- **Frontend:** `npx ng test --watch=false --browsers=ChromeHeadless` con
  `$env:CHROME_BIN = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"`; línea base
  **685 SUCCESS / 0 failed** (tras la corrección del shell). Bundle vigente
  **`main-SHBQMIGH.js`**.
- **Backend:** sin cambios; línea base SQLite **2163 passed / 127 skipped / 0 failed**. No se
  ejecuta `pytest` como criterio de esta enmienda, pero no debe alterarse.
- **Cierre:** T12 verifica `ng build`, 4200 con periodos y orden, 8080 reconstruido con
  `--force-recreate frontend`, evidencia en `004-tablero-kanban/evidencia/README.md`, anotación de
  la fila 004 en `roadmap.md` y `MEMORY.md`, y grep de coherencia. La 004 conserva su cierre
  histórico: esta enmienda se registra como adición, no como reapertura. La línea `Estado:` de
  `spec.md` la actualiza T12 al cerrar; este plan no la edita.
