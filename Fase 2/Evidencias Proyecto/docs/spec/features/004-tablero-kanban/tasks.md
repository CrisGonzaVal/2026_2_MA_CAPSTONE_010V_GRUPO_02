# Feature 004 — Tasks

**Spec:** [`spec.md`](spec.md) (aprobada) · **Plan:** [`plan.md`](plan.md)

12 tareas en orden de dependencia (T11/T12 incluidas; dentro del rango de 10-15: la spec no necesita dividirse).
Cada casilla se marca `[x]` solo con su `Hecho cuando:` cumplido y la evidencia dejada en la
tarea; si algo falla, la casilla no se marca: se arregla o se documenta el bloqueo.

Leyenda: `[ ]` pendiente · `[x]` hecha y verificada · `[!]` bloqueada (motivo en la línea)

Comandos de verificación (AGENTS.md §5):
- Backend: `cd backend && .venv\Scripts\python.exe -m pytest` (SQLite en memoria, sin contenedor)
- Frontend: `$env:CHROME_BIN = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"; cd frontend && npx ng test --watch=false --browsers=ChromeHeadless`

---

## T1 — Fixture canónico y tests rojos de flujo (AC-9, AC-10, AC-13, AC-14, AC-15 — red)

- [x] Crear `backend/tests/funcional/integracion/test_tablero_kanban.py` con la fixture `datos_flujo_canonico`
      (apoyada en `datos_base`, patrón de `datos_catalogo_ticket`): 4 estados en orden
      canónico `Pendiente → EnRevision → EnCurso → Cerrado` + helper local de payload.
- [x] Tests rojos: avanzar/retroceder un paso; salto, estado repetido y retroceso desde el
      terminal → 409; estado inexistente → 404; ticket inexistente → 404; ticket+estado
      inexistentes → 404 **de ticket** (orden D-8).
- [x] Línea base: la suite previa sigue en verde (`pytest` → 79 passed) con el archivo nuevo
      fallando solo donde falta implementación (no errores de imports ni fixtures).

**Hecho cuando:** los tests de transición nuevos están en rojo por comportamiento
inexistente, la suite previa queda en verde y `spec.md`/`plan.md` no divergen del código
real (contraste de supuestos).

**Evidencia (2026-10-07):** `pytest` → **4 failed, 83 passed** (87 = 79 previos + 8
nuevos; sin errores de colecta). Rojo exacto donde falta T2: salto, repetido y retroceso
desde terminal responden `200` en vez de `409`; estado inexistente revienta la FK en el
`commit` → `500` en vez de `404` (visto con `cliente_sin_excepcion`). Verde: avanzar,
retroceder, 404 de ticket y orden D-8. Frontend: `ng test` → **40 SUCCESS**.
AC cubiertos en fase red: AC-9, AC-10, AC-13, AC-14, AC-15.

## T2 — Flujo lineal y sellado en `actualizar_estado_ticket` (AC-9, AC-10, AC-13…AC-16, AC-18)

- [x] `ticket_service.py`: carga única del catálogo ordenado; 404 de ticket → 404 de estado →
      409 de flujo (mismo índice, distancia ≠ 1, terminal); sellado por `nombre.casefold()`
      solo si `fecha_cierre is None`; un solo `commit` al final.
- [x] Tests verdes de flujo, sellado (nombre en minúsculas), no sobrescritura y sellado
      inmune a reordenar/recrear el catálogo (AC-18).
- [x] `endpoints/tickets.py`: `description` de `PATCH /{ticket_id}/estado` documenta 404,
      409 y sellado; sin lógica en el endpoint.

**Hecho cuando:** `pytest` completo en verde y `grep -rn "ESTADO_CERRADO_ID" backend/app`
→ la constante sigue (su borrado es T5) pero ya no gobierna ningún comportamiento.

**Evidencia (2026-10-07):** rojo primero: `test_tablero_kanban.py` → 8 failed
(los 4 de T1 + 3 de sellado con id 3 / `CERRADO` / reentrada + 1 de OpenAPI), 5 passed.
Implementado en `actualizar_estado_ticket()` y `description` del PATCH → **`pytest` →
92 passed** (79 previos + 13 de la 004; `test_smoke` INGRESADO→CERRADO sigue verde) y
`ng test` → **40 SUCCESS**. `grep -rn "ESTADO_CERRADO_ID" backend/app` → **0**: la
constante se borró de `ticket_service.py` (plan §1, fila del archivo; el comportamiento
queda gobernado solo por `casefold()`), anticipando el grep de AC-25; solo queda el
comentario de `tests/conftest.py` (T5). Verificado también que `/openapi.json` del PATCH
menciona 404, 409 y `fecha_cierre` (test `test_el_contrato_del_patch_documenta_404_409_y_sellado`).
AC verdes: AC-9, AC-10, AC-13, AC-14, AC-15, AC-16, AC-18.

## T3 — Alta en `Cerrado` sella su fecha (AC-17)

- [x] Test rojo: `POST /tickets/` con estado `CERRADO` devuelve `fecha_cierre` con valor;
      con estado normal, `None`. Implementar en `crear_ticket()` (recuperar el estado con
      `db.get`, no solo comprobar existencia) → verde.

**Hecho cuando:** el test de AC-17 pasa y `pytest` completo queda en verde.

**Evidencia (2026-10-07):** test `test_crear_ticket_en_cerrado_sella_fecha_cierre` agregado en
`test_tablero_kanban.py` (líneas 368-383); implementado en `crear_ticket()` con `db.get(EstadoTicket, estado_id)`
y `casefold() == "cerrado"` antes del `try` → **`pytest` 93 passed** (92 previos + 1 nuevo de T3)
y `ng test` **40 SUCCESS**. AC-17 cubierto.

## T4 — `listar_tickets`: orden explícito y sin N+1 (AC-27)

- [x] Tests rojos: `GET /tickets/` ordenado `fecha_creacion DESC, ticket_id DESC` (empate
      incluido); conteo de queries con `before_cursor_execute` que **no crece** de 1 a 3
      tickets con detalles.
- [x] Implementar `select()` + `selectinload(detalles).selectinload(producto)` +
      `order_by` (plan §3.4); filtro `estado_id` con `is not None`.
- [x] `description` de `GET /tickets/` documenta el orden.

**Hecho cuando:** los tests de AC-27 pasan, el N+1 por ticket desapareció y `pytest`
completo queda en verde.

**Evidencia (2026-10-07):** rojo primero con los tests
`test_listar_tickets_ordena_por_fecha_desc_y_ticket_id_desc` y
`test_listar_tickets_no_hace_consultas_por_ticket` → `2 failed, 93 passed` (el orden salía
por rowid ascendente `[1,2,3]` en vez de `[3,2,1]`; el conteo de queries crecía `4 → 6`, no
constante). Implementado en `listar_tickets()` con `select()` +
`selectinload(Ticket.detalles).selectinload(DetalleTicket.producto)` +
`order_by(fecha_creacion DESC, ticket_id DESC)` y `estado_id is not None` → **`pytest` 95
passed** (79 previos + 16 de la 004) y `ng test` **40 SUCCESS**. El conteo de queries queda
constante (1 y 3 tickets: mismo número, ≤ 4). AC-27 cubierto. Nota: el rojo del N+1 fue
`6 vs 4` y no `7 vs 3` porque los tres tickets comparten producto y el lazy `many-to-one` se
resuelve desde el identity map; la aserción es de igualdad, así que es insensible al valor.

## T5 — Previos en verde y limpieza de comentarios (AC-25 parcial)

- [x] Verificar sin reescribir: `test_smoke`, `test_modal_ticket`, `test_transaccion_ticket`
      siguen verdes (el de smoke transiciona INGRESADO→CERRADO, adyacente en su catálogo).
- [x] Borrar `ESTADO_CERRADO_ID` y su comentario de `ticket_service.py`; reescribir los
      comentarios que fijan el id 4 en `database/02_datos_semilla.sql` (L45-48, L220-221) y
      la nota de `tests/conftest.py` (L104-107). **Ni una coma de DDL ni de datos.**

**Hecho cuando:** `grep -rn "ESTADO_CERRADO_ID" backend database` → 0; `git diff` sobre
`01_esquema.sql` y los INSERT de la semilla → vacío (solo comentarios cambiados); `pytest`
completo en verde.

**Evidencia (2026-10-07):** `grep "ESTADO_CERRADO_ID"` en `backend/app`,
`backend/tests/conftest.py` y `database` → **0 resultados** (la constante se había borrado ya
en T2; aquí cayeron los comentarios). `git diff --stat` del proyecto: solo
`backend/tests/conftest.py` (docstring de `datos_base`) y `database/02_datos_semilla.sql`
(2 bloques de comentario); `git diff -- database/01_esquema.sql` → **vacío** y el
`INSERT INTO estado_ticket (4, 'Cerrado', ...)` queda idéntico (AC-26 respetado).
`pytest` → **95 passed, 1 warning** (preexistente); los previos
`test_smoke` + `test_modal_ticket` + `test_transaccion_ticket` → **62 passed**. AC-25 parcial.

## T6 — Tablero real: carga, columnas y tarjetas (AC-1, AC-2, AC-4)

- [x] Tests rojos en `tickets.component.spec.ts`: columnas = estados del catálogo en orden,
      agrupación por `estado_id`, orden `fecha_creacion DESC` con empate por `ticket_id`,
      tarjeta con asunto/prioridad/solicitante/fechas.
- [x] `tickets.component.ts`: quitar los datos demo; cargar `catalogos` + `tickets` al
      construir el componente; `columnas` como `computed` (plan §3.6); estados de carga y
      error del tablero (§7).
- [x] `tickets.component.html`: columnas y tarjetas reales, reemplazando el bloque demo.

**Hecho cuando:** `ng test` verde con los tests de T6 y `grep -n "INGRESADO'" tickets.component.ts`
→ 0 (ningún vocabulario de muestra); el docstring de "datos de muestra" también se actualizó.

**Evidencia (2026-10-07):** rojo primero (superficie pública final con lógica vacía, para que el
rojo fuera de comportamiento y no de compilación): `ng test` → **33 FAILED, 12 SUCCESS**
(`Expected one matching request for .../tickets/catalogos, found none`). Implementado:
`cargarTablero()` con `forkJoin(obtenerCatalogos(), obtenerTickets())` en el `constructor()`,
`reintentarTablero()`, `columnas` como `computed` (una por estado en orden, incluidas vacías;
agrupación por `estado_id`; orden `fecha_creacion DESC` y empate `ticket_id DESC`), modelo
`TarjetaKanban` resuelto (asunto, prioridad tolerante a `Alta`/`Media`/`Baja` con clase neutra,
solicitante, `fechaCreacion`, `fechaCierre` solo si existe) y `DatePipe`; `abrirModal()` reutiliza
el catálogo ya cargado. Catálogo de estados vacío → `errorTablero` propio (distinto del de red).
Eliminado el tablero demo y su docstring de "datos de muestra". Verde: `ng test` → **TOTAL: 45
SUCCESS** (+5 de T6), `pytest` → **95 passed** (backend intacto). `grep` de
`INGRESADO|EN PREPARACIÓN|DESPACHADO|ENTREGADO|datos de muestra` en componente y template → **0**.
Tests reescritos por el cambio de contrato (catálogos ya no se piden solo al abrir el modal):
`no debe pedir catalogos antes de abrir el modal`, `debe pedir los catalogos al abrir el modal`,
`debe distinguir el error de catalogos del de guardado`, `debe limpiar el estado de catalogos al
reabrir el modal` y el demo `debe conservar los datos de muestra` (eliminado). AC-1, AC-2 y AC-4
cubiertos.

## T7 — Filtros, contadores y estados vacíos (AC-3, AC-5, AC-6, AC-7)

- [x] Tests rojos: filtro de prioridad; búsqueda case/acentos-insensible, con `%`/`_`
      literales y vacío = sin filtro; intersección; contadores tras filtrar; vacío con
      mensaje diferenciable del error.
- [x] Implementar señales de filtro y el filtrado dentro del `computed` de columnas
      (plan §3.5) + barra de filtros en el template.

**Hecho cuando:** `ng test` verde con los tests de AC-3, AC-5, AC-6 y AC-7.

**Evidencia (2026-10-07):** rojo primero (superficie pública con lógica vacía): `ng test` →
**7 FAILED, 45 SUCCESS**, fallos de comportamiento (`Expected null to be 1`,
`Expected 6 to be 3`, etc.). Implementado: `filtroPrioridad = signal<number|null>(null)` y
`busqueda = signal('')`; filtrado dentro del `computed` de columnas (intersección
prioridad ∧ búsqueda, plan §3.5) con `normalizar()` (`NFD` + sin diacríticos + `toLowerCase`
+ `trim`), así `%` y `_` son literales por construcción; `hayFiltros` para diferenciar el
vacío por filtros del vacío normal; barra de filtros (`<select>` "Todas las prioridades" +
`<input type="search">`) y `@empty` por columna con dos mensajes. Contadores = `tarjetas.length`
ya filtrado (AC-3). Verde: `ng test` → **TOTAL: 52 SUCCESS** (+7 de T7); `pytest` →
**95 passed** (backend intacto). AC-3, AC-5, AC-6 y AC-7 cubiertos.

## T8 — Botones de transición y movimiento con éxito (AC-9, AC-10, AC-11, AC-12, AC-19)

- [x] Tests rojos: ningún control en el estado terminal; sin "retroceder" en el primero;
      nunca se ofrecen saltos; con éxito, el `PATCH` mueve la tarjeta de columna y actualiza
      contadores sin recarga; botón deshabilitado mientras el envío está en curso.
- [x] Implementar `mover()` con `enProceso` (Set de tickets) y la visibilidad de botones
      por índice en el catálogo (plan §3.6).

**Hecho cuando:** `ng test` verde con los tests de AC-9 a AC-12 y AC-19.

**Evidencia (2026-10-07):** rojo primero (superficie pública con lógica vacía): `ng test` →
**6 FAILED, 52 SUCCESS**, todo dentro de `transiciones del tablero` y por comportamiento
(`Expected true to be false` en primer/terminal, `Expected null to be 2`, `found none` en el
`PATCH`). Implementado: `TarjetaKanban` con `puedeRetroceder` / `puedeAvanzar` /
`estadoAnteriorId` / `estadoSiguienteId` / `enProceso` resueltos por índice en el catálogo
(terminal → ningún control, AC-11; primer estado sin retroceso; ids contiguos, sin saltos,
AC-12); señal `enProceso = signal<Set<number>>` con guarda anti doble envío; `mover()` que en
`next` reemplaza el ticket con `.map` inmutable (la tarjeta cambia de columna y los contadores
se recalculan **sin** `GET /tickets/`, AC-19) y en `error` solo libera el id (la alerta y la
reconsulta son T9); `moverAnterior()`/`moverSiguiente()` para el template, botones con
`[disabled]="tarjeta.enProceso"` y `aria-label` único. Verde: `ng test` → **TOTAL: 58
SUCCESS** (+6 de T8); `pytest` → **95 passed** (backend intacto). AC-9, AC-10, AC-11, AC-12 y
AC-19 cubiertos.

## T9 — Rechazos, alerta, reconsulta y alta reflejada (AC-8, AC-20)

- [x] Tests rojos: con `409`/`404`/error de red la tarjeta **no** se mueve, aparece
      `role="alert"` y se emite la reconsulta `GET /tickets/`; el ticket creado desde el
      modal aparece sin recargar y se excluye si los filtros activos no lo admiten.
- [x] Implementar el manejo de error de `mover()` y la inserción de la respuesta de `POST`
      en `tickets()` (plan §3.6, D-7).

**Hecho cuando:** `ng test` verde con los tests de AC-8 y AC-20.

**Evidencia (2026-10-07):** rojo primero (superficie pública con lógica vacía, tras un primer
rojo de compilación por `errorMovimiento` inexistente): `ng test` → **5 FAILED, 58 SUCCESS**
(`Expected null to be 'Transición no permitida por el flujo'`, `... 'Ticket no encontrado'`,
`... 'No se pudo cambiar el estado'`, `found none` en la reconsulta y `Expected false to be
true` en los dos de AC-8). Implementado: señal `errorMovimiento` (distinta de `errorTablero`)
y rama `error` de `mover()` que fija el `detail` del backend (o un texto propio para 500/red),
libera el id y llama a `reconsultarTickets()` (solo `GET /tickets/`, sin repedir catálogos);
la tarjeta no se toca con la respuesta fallida. Alta del modal: la respuesta del `POST` se
inserta en `tickets()` con `.update` (AC-8) y el `computed` de columnas la admite o la excluye
según los filtros activos (D-6); alerta `role="alert"` en el template, sin duplicar la de alta.
Verde: `ng test` → **TOTAL: 63 SUCCESS** (+5 de T9); `pytest` → **95 passed**. Cuatro tests del
modal se ajustaron para devolver un `Ticket` completo en el `flush` del `POST` (ahora el
componente consume la respuesta íntegra). AC-8 y AC-20 cubiertos.

## T10 — Cierre: suites, recorridos y documentación (AC-21…AC-26)

- [x] **AC-21** `pytest` → verde (número final anotado) y `ng test` → `TOTAL: N SUCCESS`.
- [x] **AC-22** `npx ng build` de producción compila.
- [x] **AC-23** Recorrido en 4200 contra backend real: columnas con tickets semilla, avanzar
      y retroceder con escritura real, y el 409 de dos pestañas (spec AC-23, receta exacta).
- [x] **AC-24** `docker compose -f docker-compose.yml build frontend && up -d frontend` y
      recorrido de humo en 8080 (`AGENTS.md` §8.6).
- [x] **AC-25** Fila 004 cerrada en `roadmap.md`; `MEMORY.md` actualizado;
      `grep -rn "ESTADO_CERRADO_ID" backend frontend database MEMORY.md` → 0
      (`docs/spec/` fuera, es registro histórico).
- [x] **AC-26** `git diff` sin cambios estructurales en modelo ni datos de scripts; sin
      dependencias nuevas en `requirements.txt` ni `package.json`.
- [x] Coherencia final (`AGENTS.md` §8.7): grep de rutas citadas en `AGENTS.md`,
      `MEMORY.md` y `.agents/skills/` por la 004.

**Evidencia de cierre (2026-10-13):** AC-23: recorrido funcional en 4200 contra el backend
real, con avance y retroceso verificados por `SELECT` y 409 de dos pestañas. AC-24: 8080
tras `docker compose -f docker-compose.yml build frontend` +
`up -d --force-recreate frontend`; `up -d` solo no recreaba el contenedor porque `latest`
apuntaba a otro image ID que el contenedor vivo. AC-25: grep → 0, `MEMORY.md` actualizado y
fila 004 cerrada en `roadmap.md`. Suites finales: `pytest` → **95 passed, 1 warning
preexistente**; `ng test` → **63 SUCCESS**. Build de producción exitoso (inicial 312.80 kB,
chunk lazy 65.38 kB). AC-26: sin cambios en esquema ni dependencias; semilla solo con
cambios de comentarios. §8.7: coherencia de las rutas citadas verificada.

**Hecho cuando:** los 6 AC tienen su evidencia pegada en esta tarea, todas las casillas
anteriores están en `[x]` y ninguna ruta citada quedó obsoleta. Ese es el único momento de
marcar la fila 004 en el roadmap.

## T11 — Frontend: filtro de periodo y orden, con pruebas (AC-28, AC-29, AC-30)

**Depende de:** T10 (suites y cierre históricos en verde) y de la aprobación de `spec.md` §8.
**Archivos:** `frontend/src/app/features/tickets/tickets.component.ts`, `.html` y `.spec.ts`.
**Verificación:** `$env:CHROME_BIN = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"; cd frontend && npx ng test --watch=false --browsers=ChromeHeadless`.

- [x] Tests rojos primero en `tickets.component.spec.ts`: reloj fijo con
      `jasmine.clock().mockDate(new Date(2026, 10, 28, 15, 0, 0))` y fixture de tickets de hoy,
      3, 10, 40 y 400 días; matriz de `todo`/`hoy`/`semana`/`mes`/`anio`, bordes exactos (inicio
      incluido, `inicio - 1 ms` excluido), sin cota superior y sin recorte por `fecha_cierre`.
- [x] Tests rojos de orden: «Más recientes» por defecto (`fecha_creacion` DESC, empate
      `ticket_id` DESC), «Más antiguos» (ASC, empate `ticket_id` ASC), dentro de cada columna y
      también en «Terminados»; cambiar solo el orden no emite peticiones ni altera contadores,
      `hayFiltros` o el vacío.
- [x] Tests rojos de combinación y alta: periodo ∧ prioridad ∧ búsqueda antes de agrupar;
      contadores `tarjetas.length`; vacío por filtros con solo el periodo activo; el `POST` con
      `fecha_creacion` actual aparece bajo cualquier periodo vigente, ordenado y sujeto a los
      otros filtros; al remontar vuelven `todo` y `recientes`.
- [x] Implementar `filtroPeriodo` y `orden` como señales, el helper puro
      `inicioDePeriodo(periodo, ahora)` y la cadena de `columnas` del plan §7.2–§7.5 (periodo
      antes de agrupar; orden después, por columna); `hayFiltros` incluye el periodo.
- [x] Plantilla: dos `<select>` nativos con `<label>` visible «Periodo» y «Orden», valores
      estables (`todo/hoy/semana/mes/anio`, `recientes/antiguos`), Tailwind y sin CSS embebido
      (plan §7.6).

**Hecho cuando:** los tests nuevos estaban en rojo antes de implementar y ahora pasan;
`tickets.component.spec.ts` queda en verde y la suite completa de `ng test` termina con
**0 FAILED**. No se reescriben AC-2, AC-6 ni AC-7. `inventario` no aplica: el cambio es solo del
tablero de tickets y su suite no se toca.

**Nota de fase (T11 ejecutada el 28/Nov/2026).** Implementado solo el tablero de tickets.
- **Archivos:** `tickets.component.ts` (tipos `PeriodoTablero`/`OrdenTablero`, helper
  `inicioDePeriodo`, señales `filtroPeriodo`/`orden`, periodo en `columnas` antes de agrupar,
  comparador por columna y `hayFiltros` con periodo), `tickets.component.html` (dos `<select>`
  con `data-testid` estable y `<label>` visible, `sm:flex-wrap` en la barra) y
  `tickets.component.spec.ts` (15 pruebas nuevas con reloj fijo y fixtures relativos).
- **Comandos y conteos:** `npx ng test --watch=false --browsers=ChromeHeadless
  --include=…tickets.component.spec.ts` → **103 SUCCESS**; suite completa → **700 SUCCESS, 0
  FAILED** (baseline 685 + 15). No se ejecutó `ng build` ni se reconstruyó 8080: T11 es
  exclusivamente de pruebas; T12 hará build y puertos.
- **Rojas curadas:** (1) la primera corrida falló por la API nueva aún inexistente
  (`filtroPeriodo`/`orden`/`inicioDePeriodo`), que era el rojo esperado; (2) tras implementar,
  dos pruebas fallaron por fixtures: la prueba del helper dejaba abiertas las dos peticiones del
  arranque y la prueba de alta conservaba `busqueda='papel'`, que excluía al ticket 101 de la
  comprobación de orden. Se corrigieron con `cargarPeriodo()` y limpiando la búsqueda antes de
  comprobar el orden.
- **Decisiones no cubiertas por el plan:** se añadieron `data-testid="filtro-periodo"` y
  `data-testid="filtro-orden"` solo para selectores de prueba estables; `cambiarPeriodo` y
  `cambiarOrden` ignoran valores fuera de los catálogos mediante `PERIODOS_TABLERO`/
  `ORDENES_TABLERO`; la barra usa `sm:flex-wrap` para no romper móvil. No se tocó
  `ticket.service.ts`, backend, `database/`, `stack.md`, la 013/018 ni el 8080.

## T12 — Verificación y evidencia de la enmienda (AC-28…AC-30)

**Depende de:** T11.
**Alcance:** verificación funcional y documental. No crea feature nueva: la 004 conserva su
cierre histórico (AC-1…AC-27 intactos) y esta enmienda se registra como adición.

- [x] `ng test` completo sin `FAILED` y `ng build` de producción compila sin errores.
- [x] Recorrido funcional en 4200 con backend real: los cinco periodos, ambos órdenes,
      combinación con prioridad y búsqueda, contadores y vacío, y un alta visible bajo un periodo
      activo.
- [x] 8080: `docker compose -f docker-compose.yml build frontend` +
      `up -d --force-recreate frontend`; humo de los dos selectores y de un periodo.
- [x] Evidencia en `docs/spec/features/004-tablero-kanban/evidencia/README.md` (nuevo): nombres
      de tests, conteos de suite, build, capturas y resultado de los dos puertos.
- [x] Fila 004 de `roadmap.md` anotada con la enmienda del 27/Nov/2026 sin borrar su cierre
      original; `MEMORY.md` actualizado; línea `Estado:` de `spec.md` actualizada a la enmienda
      aprobada/cerrada con el enlace a la evidencia; grep de coherencia de rutas y textos
      (`AGENTS.md` §8.7).
- [x] Confirmar que no se creó feature nueva, que `spec.md` §8, `plan.md` §7 y estas tareas no
      divergen del código y que `stack.md` sigue intacto.

**Hecho cuando:** los 3 AC tienen su evidencia pegada en esta tarea, todas las casillas de T11
están en `[x]`, la suite y el build están en verde, los dos puertos se recorrieron, el grep no
dejó rutas obsoletas, la línea `Estado:` refleja el cierre y la fila 004 registra la enmienda sin
reescribir su cierre.

**Nota de fase (T12 ejecutada el 28/Nov/2026).** Cierre verificado.
- **Suites/build:** spec del tablero **103 SUCCESS**; `ng test` completo **700 SUCCESS / 0
  FAILED**; `ng build` limpio, bundle **`main-K4LJUM5F.js`**, Initial **340,27 kB**.
- **4200 (Administrador):** Todo 4/3/4=11; Hoy 0/0/0 con vacío por filtros; Semana 4/1/2=7;
  Mes/Año 4/3/4=11. Orden: recientes `[2,1,3,4]` / `[11,5,6]` / `[10,9,7,8]`; antiguos
  `[4,3,1,2]` / `[6,5,11]` / `[8,7,9,10]`. Combinación Semana + Alta + «Toner» → `#2`.
- **4200 (Solicitante):** alta #12 «Cierre T12 periodo y orden» el 28/Nov 03:38; Hoy 1/0/0,
  Semana/Mes/Año/Todo 1/1/2; Terminados recientes `[10,9]` / antiguos `[9,10]`. En la vista
  institucional del Administrador, Todo/Recientes En Revisión `[12,2,1,3,4]` y Antiguos
  `[4,3,1,2,12]`.
- **8080:** imagen `sha256:f39aaf…` idéntica a la construida y recreada con
  `--force-recreate`; sirve **`main-K4LJUM5F.js`**; `main-SHBQMIGH.js`, `main-6T35N3WS.js`,
  `main-IRJLFDU6.js` y `main-72C5Q3DY.js` → 404; Solicitante Todo/Recientes 1/1/2 y
  Hoy/Antiguos 1/0/0.
- **Documentación:** `004/evidencia/README.md` §1–§7; `spec.md` AC-28…AC-30 marcados y
  `Estado:` actualizado; fila 004 del roadmap anotada; `MEMORY.md` actualizado. Capturas
  `t12-01`, `t12-02` y `t12-03`.
- **Decisiones no cubiertas por el plan:** la matriz de periodos se recorrió con Administrador
  (visión institucional de 11 pedidos) y el alta con Solicitante (rol habilitado); se capturaron
  ambos tableros y el humo 8080. No se tocó backend, `database/`, `ticket.service.ts`,
  `stack.md`, la 013/018 ni el refactor externo de la 012. No queda pendiente de T12.
- **Nota de corrección post-validación (veredicto APROBADO).** Se pulieron los cuatro
  menores detectados: (1) docstring de `tickets.component.ts` corregido —el alta inserta el
  `201` en `tickets()` sin reconsultar (AC-8), sin referencia a H-3—; (2) `tasks.md` pasa a
  **12 tareas**; (3) la matriz del Administrador queda fechada **antes del alta de #12**
  (Todo 4/3/4, Hoy 0/0/0, Semana 4/1/2) y **después** pasa a 5/3/4, 1/0/0 y 5/1/2; (4) los
  selects de periodo/orden llevan `id`/`name` (`filtro-periodo`/`periodo`,
  `filtro-orden`/`orden`) y `for` en el label, y se añadieron `id`/`name` a los campos
  preexistentes de la barra y del modal para eliminar el aviso de Chrome. Se añadió la
  prueba del **domingo 29/Nov** y del **cruce al 1/Dic** (lunes 30/Nov). Verificación:
  spec del tablero **104 SUCCESS**, suite completa **701 SUCCESS / 0 FAILED**, build
  **`main-KSHSOEG4.js`** (Initial 340,27 kB), 8080 con imagen `sha256:985ef…`, bundle
  nuevo 200, anteriores 404, selects con `id`/`name` y aviso de Chrome eliminado. Capturas
  `t12-01`…`t12-03` siguen vigentes; no cambió la funcionalidad de periodo/orden ni los AC.
