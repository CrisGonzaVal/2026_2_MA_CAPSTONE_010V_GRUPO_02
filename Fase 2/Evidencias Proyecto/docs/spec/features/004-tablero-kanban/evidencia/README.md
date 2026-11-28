# Evidencia — Enmienda 27/Nov/2026: filtro de periodo y orden del tablero

Cierre de **T11/T12** de la Feature 004 (**AC-28…AC-30**). Cambio **solo de frontend**:
`tickets.component.ts`, `.html` y `.spec.ts`. No se tocaron backend, `ticket.service.ts`,
`database/`, `stack.md`, la matriz, la 013 ni la 018. La 004 conserva intacto su cierre
histórico (AC-1…AC-27).

## 1. Suites y build

| Verificación | Comando | Resultado |
|---|---|---|
| Spec del tablero | `npx ng test --watch=false --browsers=ChromeHeadless --include=src/app/features/tickets/tickets.component.spec.ts` | **104 SUCCESS / 0 FAILED** |
| Suite completa | `$env:CHROME_BIN="C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"; npx ng test --watch=false --browsers=ChromeHeadless` | **701 SUCCESS / 0 FAILED** |
| Build de producción | `npx ng build` | limpio; **`main-KSHSOEG4.js`**, Initial **340,27 kB** (94,06 kB transferidos) |

`pytest` no se ejecutó: no hubo cambios de backend ni de contrato.

## 2. Contrato y pruebas

- `inicioDePeriodo(periodo, ahora)`: `todo` → `null`; `hoy` → medianoche local; `semana` →
  lunes local (lunes–domingo); `mes` → día 1; `anio` → 1 de enero. Todo por campos locales y a
  las `00:00:00.000`.
- Defaults: `filtroPeriodo='todo'` y `orden='recientes'`; no hay persistencia.
- `columnas`: periodo ∧ prioridad ∧ búsqueda **antes de agrupar**; orden dentro de cada
  columna, incluida «Terminados».
- Órdenes: recientes = `fecha_creacion` DESC y `ticket_id` DESC; antiguos = ASC y `ticket_id`
  ASC.
- `hayFiltros` incluye el periodo; el orden no. Contadores = `tarjetas.length`.
- Pruebas nuevas: 16 en el bloque `periodo y orden del tablero (AC-28…AC-30)`, con reloj fijo
  `jasmine.clock().mockDate(new Date(2026, 10, 28, 15, 0, 0))` y fixture de 0/3/10/40/400
  días. Matriz: **Todo 5 / Hoy 1 / Semana 2 / Mes 3 / Año 4**. Cubren bordes exactos,
  `inicio - 1 ms`, sin cota superior, sin `fecha_cierre`, orden con empate, cambio de orden sin
  HTTP, combinación, contadores, vacío, alta y remontaje.
- No se reescribieron las aserciones de AC-2, AC-6 ni AC-7.

## 3. Recorrido 4200 — Administrador

Backend real (`:8000`), `ng serve` en `:4200`, sesión Clerk de `admin020.test+clerk_test@example.com`.

| Periodo | En Revisión | En Curso | Terminados | Total / observación |
|---|---:|---:|---:|---|
| Todo el tiempo | 4 | 3 | 4 | 11 |
| Hoy | 0 | 0 | 0 | 0; las tres columnas muestran «Ningún pedido coincide con los filtros» |
| Esta semana | 4 | 1 | 2 | 7 |
| Este mes | 4 | 3 | 4 | 11 |
| Este año | 4 | 3 | 4 | 11 |

Estos conteos son **antes del alta de #12**. Después del alta, el tablero institucional pasa a
**Todo 5/3/4 = 12**, **Hoy 1/0/0 = 1** y **Semana 5/1/2 = 8**; Mes y Año 5/3/4 = 12.

Orden con **Todo el tiempo**:

| Columna | Más recientes | Más antiguos |
|---|---|---|
| En Revisión | `#2, #1, #3, #4` | `#4, #3, #1, #2` |
| En Curso | `#11, #5, #6` | `#6, #5, #11` |
| Terminados | `#10, #9, #7, #8` | `#8, #7, #9, #10` |

Combinación: **Esta semana + Alta + «Toner»** → En Revisión `#2`, En Curso 0, Terminados 0.
Al limpiar los filtros vuelve a 4/3/4.

Captura: [t12-01-4200-periodo-semana-antiguos.png](t12-01-4200-periodo-semana-antiguos.png)
(«Esta semana» + «Más antiguos»).

## 4. Recorrido 4200 — Solicitante y alta

Sesión `solicitante.test+clerk_test@example.com` (Paula Rojas, Biblioteca, Sede Maipú).
Antes del alta, el tablero propio mostraba Todo/Recientes **0 / 1 / 2 = 3**.

Se creó el pedido **#12 «Cierre T12 periodo y orden»** desde el modal: `201`, sin recarga del
listado, `fecha_creacion` **28/Nov/2026 03:38**, estado inicial `EnRevision`. Después del alta:

| Periodo | En Revisión | En Curso | Terminados | Total |
|---|---:|---:|---:|---:|
| Hoy | 1 (`#12`) | 0 | 0 | 1; vacío en las otras dos |
| Esta semana | 1 (`#12`) | 1 (`#11`) | 2 (`#10`, `#9`) | 4 |
| Este mes | 1 | 1 | 2 | 4 |
| Este año | 1 | 1 | 2 | 4 |
| Todo el tiempo | 1 | 1 | 2 | 4 |

En «Terminados», «Más recientes» = `#10, #9` y «Más antiguos» = `#9, #10`. El pedido #12
aparece bajo todos los periodos vigentes y en «En Revisión» según el orden elegido. En la
vista institucional del Administrador, con **Todo el tiempo**, «Más recientes» deja En
Revisión `[#12, #2, #1, #3, #4]` y «Más antiguos» `[#4, #3, #1, #2, #12]`; #12 queda primero
y último respectivamente.

Captura: [t12-02-4200-alta-hoy.png](t12-02-4200-alta-hoy.png) (Hoy + Más recientes, con #12 y
los vacíos por filtro).

## 5. Humo 8080

- Imagen final del contenedor: **`sha256:985ef772f78fddd9d3ca3f1554317e32c45e473d20765c8850626f4c2785536e`**, idéntica a la imagen construida; contenedor **healthy**, recreado con `up -d --force-recreate frontend`.
- `index.html` sirve **`main-KSHSOEG4.js`** (200). Bundles anteriores: `main-VSYNPI67.js`, `main-K4LJUM5F.js`, `main-SHBQMIGH.js`, `main-6T35N3WS.js`, `main-IRJLFDU6.js` y `main-72C5Q3DY.js` → **404**.
- Sesión Solicitante compartida desde `localhost`: default **Todo / Más recientes** con
  **1 / 1 / 2 = 4**; al cambiar a **Hoy / Más antiguos**, **1 / 0 / 0** con los dos vacíos por
  filtro. `#12` visible. Red: `GET /main-KSHSOEG4.js` → **200**.

Las capturas `t12-01`, `t12-02` y `t12-03` siguen siendo válidas: el pulido solo añadió
`id`/`name` y corrigió copy; no cambió la vista ni la lógica de periodo/orden.
- Captura: [t12-03-8080-periodo-orden.png](t12-03-8080-periodo-orden.png).

## 6. Mapeo AC-28…AC-30

| AC | Evidencia |
|---|---|
| AC-28 | Tests `inicioDePeriodo...`, default, matriz, bordes exactos, sin cota superior, sin `fecha_cierre` y contrato del selector; 4200 Admin 4/3/4, 0/0/0, 4/1/2 y 4/3/4; 8080 Hoy 1/0/0; `t12-01`/`t12-02`/`t12-03` |
| AC-29 | Tests de «Más recientes» por defecto, «Más antiguos» con empate ASC, Terminados, `httpMock.expectNone` y contrato del selector; 4200 Admin invierte las tres columnas (incluida Terminados); 8080 selector presente |
| AC-30 | Test de intersección periodo ∧ prioridad ∧ búsqueda; contadores/vacío; alta #12 sin recarga bajo cualquier periodo; remontaje `todo`/`recientes`; 4200 Semana + Alta + «Toner» → `#2`; 4200 Solicitante #12; 8080 Hoy 1/0/0 |

## 7. Datos residuales y alcance

- Queda el pedido **#12** en `EnRevision`/«En revisión» con fecha **28/Nov/2026 03:38**, creado
  para la verificación del alta. No se reseteó la base.
- No hay cambios de API, DTO, matriz, DDL ni `stack.md`; no se creó una feature nueva.
- La 013, la 018, `AGENTS.md`, `.agents/skills/` y el refactor externo de la 012 no se tocan.
