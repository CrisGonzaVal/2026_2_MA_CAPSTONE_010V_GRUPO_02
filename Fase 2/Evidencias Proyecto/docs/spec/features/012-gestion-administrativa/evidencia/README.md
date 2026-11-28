# Feature 012 — Evidencia del recorrido real (T13)

Recorrido funcional en **4200** (`npm start`, dev server) contra el backend en
contenedor (`uvicorn --reload`, volumen `./backend/app`) y PostgreSQL **real**
(`compustock_db` / `apt_erp`). Base migrada a **012.1** con
`database/migraciones/003_migracion_gestion_administrativa_012.sql` (respaldo
previo `respaldos/apt_erp_pre_012.dump`; sin borrado de datos).

Sesiones Clerk (instancia dev) con las cuentas `+clerk_test` (código de
verificación fijo `424242`):

- Superadmin: `superadmin.test+clerk_test@example.com` (identidad global en `control`).
- Administrador institucional: `admin.cfsnorte+clerk_test@example.com` (INST-002).

## Estado de la base al iniciar

- `control.version_esquema = 012.1`; 4 instituciones; 6 capacidades habilitadas por
  institución; 4 esquemas `tenant_*`.

> **Nota sobre las capturas:** existen las capturas `01`–`18` **salvo `11`**, que se perdió
> por timeout durante el recorrido (T13). Su contenido (desactivación/reactivación de sede)
> quedó acreditado por la verificación SQL y por la captura `12` de conflicto 409; no
> invalida la evidencia del recorrido.

## Recorrido por rol

### Superadmin (portal `/control`)

| Vista / acción | Resultado observado | AC |
|---|---|---|
| Login Clerk | sin enlace `/tickets`; el destino inicial es `/control/dashboard`; el sidebar ofrece Dashboard SaaS e Instituciones (`02-dashboard-superadmin-nav.png`) | AC-3 |
| Dashboard SaaS | 4 instituciones activas, atribución nombre+id, sedes y usuarios por rol (`03`) | AC-4 |
| Instituciones | listado con RUT/dirección canónicos y estado (`04`) | AC-1 |
| Editar INST-004 | nombre `Municipalidad de Talagante (verif 012)` persistido en `control.institucion` **y** en el espejo tenant (2 columnas); recargado (`05`) | AC-1 |
| Deactivar INST-002 | `control.institucion.activo=false`; tenant, mapas y datos intactos (`17`) | AC-2 |
| Reactivar INST-002 | vuelve a `Activo`; routing restaurado | AC-2 |
| Capacidades INST-002 | las 6 visibles; `kanban` deshabilitada y re-habilitada (`06`) | AC-5 |
| `/tickets` directo | redirige a `/acceso-denegado`, sin Kanban (`07`) | AC-3 |

### Administrador institucional (`/administracion`)

| Vista / acción | Resultado observado | AC |
|---|---|---|
| Dashboard | rol Administrador, institución CFS Norte; nav con Tickets y Administración (`08`) | — |
| Sedes | lista con estado activo/inactivo; crear `Sede QA 012` → `sede_id 4` (`09`,`10`) | AC-6 |
| Sede: editar | `Sede QA 012 Editada` persistido | AC-6 |
| Sede: desactivar/reactivar | `activo=false`→`true` persistido | AC-11 |
| Sede: desactivar con dependencias | **409** `No se puede desactivar la sede: hay departamentos activos asignados a ella; reasigne su sede antes` (`12`) | AC-11 |
| Departamentos | lista con sede asignada o "Sin sede asignada" (`13`) | AC-7 |
| Departamento: crear/asignar sede | `Depto QA 012` creado; sede limitada a las del tenant; `Sede 3` asignada | AC-7 |
| Departamento: desactivar con usuarios | **409** `No se puede desactivar el departamento: tiene usuarios vinculados; reasigne o desactive esos usuarios antes` | AC-11 |
| Departamento: desactivar/reactivar | `activo=false`→`true` | AC-11 |
| Usuarios | lista con rol/departamento/estado reales (`14`) | AC-8 |
| Usuario: editar (sin correo) | `Felipe Soto` editado y revertido; estado activo/inactivo con `mapa_usuario_esquema.activo` | AC-8/AC-11 |
| Usuario Bodeguero + sede | rol Bodeguero → "Sin sede" → asignar `Sede 2` → `usuario.sede_id=2` | AC-9 |
| Encargados | estado vacío; asociar `Felipe Soto`; retirar (`15`) | AC-10 |
| `/tickets` | ruta y Kanban accesibles (`16`) | AC-3 |

### Aislamiento y gating (API directa con token de INST-002)

| Petición | Resultado | AC |
|---|---|---|
| `PATCH /api/v1/tickets/1/estado` (kanban apagada) | **403** sin mutación | AC-5 |
| `PUT /api/v1/organizacion/departamentos/1/sede` (depto de INST-001) | **404** | AC-12 |
| `PUT /api/v1/usuarios/1` (usuario de INST-001) | **404** | AC-12 |
| `GET /api/v1/organizacion/sedes` | **200** (solo INST-002) | AC-1 |
| `PATCH /api/v1/tickets/1/estado` (kanban re-habilitada) | **404** (deja de ser 403 de gating) | AC-5 |
| `/auth/me`, `/organizacion/sedes`, `/usuarios/` con INST-002 inactiva | **401** (token Clerk vigente) | AC-2 |
| Mismos tres con INST-002 reactivada | **401 → 200** | AC-2 |

## Bugs encontrados y corregidos

1. **`GET /auth/me` roto para usuarios de tenant en PostgreSQL (corregido).**
   El endpoint resolvía la identidad con la sesión de **control** (`get_db`), pero
   un rol limitado vive en el esquema de **su** institución (Feature 010): la
   relectura del usuario y de la institución efectiva no encontraba fila y
   respondía **401**. Efecto: el frontend de cualquier usuario no‑Superadmin caía
   en "Identidad no disponible" y `/administracion` no era utilizable. La suite
   ordinaria (SQLite, contexto lógico único) no lo detectaba.
   **Fix:** `GET /auth/me` usa `get_db_negocio` (tenant resuelto; `control` para
   Superadmin). **Test de regresión gated:**
   `tests/funcional/sistema/test_gestion_administrativa_http_postgres_012.py::test_auth_me_resuelve_identidad_de_tenant`
   (rojo sin el fix, verde con él).

## Correcciones posteriores al recorrido original

1. La raíz y el login sin retorno ahora llevan al Superadmin a
   `/control/dashboard`; el acceso a `/control/alta` queda como acción contextual
   `Nueva institución` dentro de la vista `/control/instituciones`.
2. Se retiró la barra interna duplicada del portal de control. La navegación
   principal queda en el sidebar global, sin cambiar rutas ni permisos.

> **Corregido tras T13:** `POST /api/v1/usuarios/` usaba la sesión de **control** (`get_db`) y
> sobre PostgreSQL un Administrador de tenant recibía **403** al dar de alta un usuario local.
> Se corrigió usando `get_db_negocio` (tenant) + `get_db` (control) y se añadió el alta en la
> vista de usuarios (`AC-8`/`AC-9`), con regresión gated
> `test_gestion_administrativa_http_postgres_012.py::test_alta_usuario_por_admin_de_tenant_persiste_en_su_esquema`
> y `ng test` en **292 SUCCESS**. Misma clase de defecto que `/auth/me`.

## Datos de prueba residuales (creados solo por la app)

- INST-002: sede `Sede QA 012 Editada` (`sede_id 4`, activa) y departamento
  `Depto QA 012` (`departamento_id 9`, activo, sede 3). Sin borrado (la
  desactivación es lógica y no se elimina historial).
- INST-004: nombre editado a `Municipalidad de Talagante (verif 012)`.
- `felipe.soto@cfsnorte.cl`: atributos restaurados; `sede_id=2` residual (inerte
  para un Solicitante).

---

# Enmienda T-17 — pestañas ARIA en administración (E17-4, 22/Oct/2026)

Recorrido observado **después** de E17-3, con el mismo backend en contenedor
(`compustock_backend`, `uvicorn --reload`) y la misma base PostgreSQL `apt_erp`
(`012.1`). Sin cambios en `administracion.routes.ts`, rutas hijas, guards,
backend ni contratos: la enmienda afecta solo presentación y semántica de la
barra de administración.

Sesión usada: `admin017.test+clerk_test@example.com` — **Administrador QA014**,
institución *Instituto Profesional Los Alpes*, rol `Administrador` (cookie Clerk
vigente en `localhost:4200` y `localhost:8080`, sin re-login).

## Suites y build (4200)

| Comprobación | Resultado observado |
|---|---|
| `ng test --watch=false --browsers=ChromeHeadless` (`CHROME_BIN` a Edge) | **466 ejecutados: 466 SUCCESS / 0 FAILED** (los 20 casos de la enmienda incluidos) |
| `npx ng build` | **limpio**: `Application bundle generation complete` (29.3 s), inicial **329.56 kB** / 91.66 kB transferido |
| Bundle de producción generado | `main-KWQKKL6Q.js` |
| `git diff --stat` de `sedes/departamentos/usuarios/encargados.component.spec.ts` y `administracion.routes.spec.ts` | **vacío**: ninguna expectativa heredada necesitó adaptación |
| `git status` del feature | modificados solo `administracion-nav.component.ts/.html` y `administracion.component.ts/.html`; nuevo (sin trackear) `administracion-nav.component.spec.ts` |

## Recorrido en 4200 (visual y teclado)

| Comprobación | Resultado observado | Captura |
|---|---|---|
| Deep link `/administracion/sedes` | `role="tablist"` con `aria-label="Secciones de administración institucional"`; 4 `role="tab"`; solo `pestana-administracion-sedes` con `aria-selected="true"` y `tabindex="0"`; `role="tabpanel"` con `aria-labelledby="pestana-administracion-sedes"`; vista de sedes con sus 2 sedes | `19` |
| Deep link `/administracion/departamentos` | seleccionada `…-departamentos`; `aria-labelledby` del panel = `pestana-administracion-departamentos`; listado de departamentos con sede asignada visible | `20` |
| Deep link `/administracion/usuarios` | seleccionada `…-usuarios`; panel enlazado a su pestaña; 10 usuarios listados | `21` |
| Deep link `/administracion/encargados` | seleccionada `…-encargados`; panel enlazado a su pestaña; selector de departamento operativo | `22` |
| `/administracion` sin segmento | redirige a `/administracion/sedes` y la pestaña **Sedes** queda seleccionada (fallback/redirección coherentes) | `24` |
| Clic en la pestaña `Sedes` desde `Usuarios` | ruta → `/administracion/sedes`, `aria-selected` y `tabpanel` migran a sedes, `document.title` = `Sedes \| CompuStock` | — |
| `ArrowRight` con foco en **Encargados** | envuelve a `/administracion/sedes`; foco en `pestana-administracion-sedes`; panel = `pestana-administracion-sedes` | — |
| `ArrowLeft` con foco en **Sedes** | envuelve a `/administracion/encargados`; foco en `pestana-administracion-encargados` | — |
| `ArrowRight` ×3 desde Sedes | Sedes → Departamentos → Usuarios, con foco, ruta, `aria-selected` y panel correctos en cada paso | `23` |
| Presentación | pestaña activa `rgb(29,78,216)` (texto azul) con borde inferior `rgb(37,99,235)`; inactivas `rgb(71,85,105)` (slate) y borde inferior transparente; anillo de foco visible en la pestaña enfocada. Ningún `role="tab"` conserva clases de fondo oscuro (`bg-slate-9*`/`bg-gray-9*`): el resaltado de bloque anterior desapareció | `19`, `23` |
| Consola | única advertencia: `Clerk: … development keys` (preexistente). **Sin errores** | — |

## Humo en 8080 (imagen reconstruida)

`docker compose -f docker-compose.yml build frontend` + `up -d frontend`
(contenedor `compustock_frontend` recreado, `healthy`). Bundle servido por nginx:
**`main-KWQKKL6Q.js`** (el anterior era `main-D6GKPODP.js`), por lo que la imagen
es la recién construida.

| Comprobación | Resultado observado | Captura |
|---|---|---|
| `/administracion/sedes` por deep link HTTP | **200** y router Angular (sin 404 de nginx); tablist de 4 pestañas; sedes seleccionada; panel enlazado | `25` |
| `ArrowRight` desde **Sedes** | `/administracion/departamentos`, foco y selección en la pestaña destino | `26` |
| `/administracion/usuarios` y `/administracion/encargados` directos | **200** con su pestaña seleccionada y panel enlazado (títulos `Usuarios`/`Encargados`) | `27`, `28` |
| Consola | sin mensajes de error | — |

> Las capturas `25`–`28` repiten contenido de `19`–`22` porque el recorrido se hizo
> igual en ambos puertos; sirven como prueba de que el build de producción de la
> imagen nueva presenta la misma barra y navega igual que el dev server.

---

# Enmienda funcional 27/Nov/2026 — recorrido E12-C2 en 4200

Recorrido observado **después** del reset limpio (`docker compose -f docker-compose.yml
down -v` + `up -d`) y con el backend en contenedor contra `apt_erp` recreada. **No se
generaron capturas PNG nuevas de este recorrido**: la evidencia es textual y SQL. Las
capturas `01`–`28` son históricas de T13/T-17: las de administración muestran la barra de
**4 pestañas** y la vista de **Encargados**, ya retiradas por la enmienda; no se reutilizan
como prueba de este recorrido.

> **Snapshot histórico.** Los 15 usuarios, el `Suministros` con dos Bodegueros y el KPI 8 de
> este apartado corresponden a la base de C2; el cierre de la **013** reinició la base
> (13 usuarios, 7 departamentos; `013-ciclo-vida-ticket/evidencia/README.md` §11.3) y el
> **recorrido manual de esta corrección** (ver el último apartado) la dejó en 13 usuarios y
> 8 departamentos con `Suministros` y Ricardo Nilo Solicitante/Biblioteca. Los 15 usuarios de
> C3 también son históricos.

## Reset y estado de partida

| Comprobación | Resultado observado |
|---|---|
| `control` | **25** tablas |
| Cada tenant (`tenant_inst_001…004`) | **22** tablas |
| `version_esquema` | **`026.1`** en control y en los cuatro tenants |
| `departamento_encargado` | ausente (`to_regclass` nulo, 0 relaciones con ese nombre) |
| `/health` del backend | **200** |

## Recorrido 4200 (Administrador, `crise.gonzalez@duocuc.cl`)

Sesión obtenida con un **sign-in token efímero** de Clerk
(`client.signIn.create({ strategy: 'ticket', ticket })`); la secret key no se expuso en la
evidencia ni en archivos.

| Caso | Resultado observado |
|---|---|
| Alta **Bodeguero** `Bodeguero E12 QA` (`bodeguero.e12+clerk_test@example.com`) | Departamento deshabilitado «Suministros (asignación automática)»; Sede obligatoria (sin «Sin asignar»); `POST /api/v1/usuarios/` **201**; el PUT de sede se ejecutó; fila **Bodeguero · Suministros · Sede Maipu**; invitación **Pendiente**; el tenant pasó a **14** usuarios |
| Alta **Solicitante** `Solicitante E12 QA` (`solicitante.e12+clerk_test@example.com`) | Al elegir Solicitante aparecen **Sede (filtro)** y **Departamento**; Sede Maipu filtró a Secretaría/RRHH/Biblioteca; se eligió Biblioteca; `POST` **201**; fila **Solicitante · Biblioteca**, sin sede persistida; **15** usuarios |
| **Edición legacy** `Andres Vargas` (usuario 6) | Departamento bloqueado en Suministros, Sede obligatoria y **motivo exigido**; guardado con «Reasignación organizacional»; `PUT /api/v1/usuarios/6` **200** y `PUT /organizacion/usuarios/6/sede` **200**; mensaje «Usuario «Andres Vargas» actualizado y sede asignada»; fila **Bodeguero · Suministros · Sede Maipu** |
| **3 pestañas** | Sedes/Departamentos/Usuarios con `role=tab`, `aria-selected` y `tabpanel` con `aria-labelledby` correctos; `/administracion/encargados` cayó en el wildcard **`/dashboard`**; la pestaña Departamentos mostró el nuevo departamento **Suministros** («Sin sede asignada») y el **KPI de departamentos subió de 7 a 8** (+1, efecto D-15) |

## Verificación SQL (`tenant_inst_001_038aa2a9`)

```sql
SELECT count(*) FROM "tenant_inst_001_038aa2a9".usuario;       -- 15
SELECT count(*) FROM "tenant_inst_001_038aa2a9".departamento;  -- 8

SELECT u.usuario_id, u.nombre, u.apellido, u.correo,
       u.rol_id, r.nombre_rol, u.departamento_id, d.nombre_dep,
       u.sede_id, s.nombre
FROM "tenant_inst_001_038aa2a9".usuario u
LEFT JOIN "tenant_inst_001_038aa2a9".rol r ON r.rol_id = u.rol_id
LEFT JOIN "tenant_inst_001_038aa2a9".departamento d ON d.departamento_id = u.departamento_id
LEFT JOIN "tenant_inst_001_038aa2a9".sede s ON s.sede_id = u.sede_id
WHERE u.correo IN ('bodeguero.e12+clerk_test@example.com',
                   'solicitante.e12+clerk_test@example.com')
   OR u.usuario_id = 6
ORDER BY u.usuario_id;
```

| usuario_id | nombre | rol | departamento | sede |
|---|---|---|---|---|
| 6 | Andres Vargas (`andres.vargas@losalpes.cl`) | 3 · Bodeguero | 8 · Suministros | 2 · Sede Maipu |
| 17 | Bodeguero E12 QA (`bodeguero.e12+clerk_test@example.com`) | 3 · Bodeguero | 8 · Suministros | 2 · Sede Maipu |
| 18 | Solicitante E12 QA (`solicitante.e12+clerk_test@example.com`) | 4 · Solicitante | 6 · Biblioteca | `NULL` |

El departamento **Suministros** quedó con `departamento_id 8`, `sede_id NULL` y `activo
true`; es el departamento automático creado al dar de alta al Bodeguero (D-15), por eso el
conteo de departamentos pasó de 7 a 8.

## Corrección posterior al recorrido

Los `<select>` de rol y departamento usaban `[value]` y devolvían strings; se corrigió a
`[ngValue]`, se normalizaron los ids y se añadieron casos DOM. Resultado observado:
**`ng test` 671 SUCCESS / 0 FAILED** y **`pytest` SQLite 2163 passed / 127 skipped / 0
failed**. Sin cambios de contrato ni de matriz.

---

# Cierre E12-C3 — 8080 reconstruido y humo (27/Nov/2026)

> **Snapshot histórico.** El humo se hizo sobre la base de C2 (15 usuarios, `Suministros` con
> Bodeguero E12 QA y Andres Vargas, KPI 8). Después, el cierre de la **013** reinició la base y
> el recorrido manual de esta corrección la dejó en 13 usuarios / 8 departamentos. La validez de
> este apartado es la del **build de producción y las 3 pestañas**, no el conteo de usuarios.

## Imagen y build

| Comprobación | Resultado observado |
|---|---|
| `docker compose -f docker-compose.yml build frontend` | imagen `evidenciasproyecto-frontend` reconstruida (**`sha256:7d925c31c9bb…`**, 27/Nov/2026 17:52 UTC); todas las capas `CACHED` porque el código no cambió desde el build de la corrección `[ngValue]` (el contenido es idéntico) |
| `docker compose -f docker-compose.yml up -d --force-recreate frontend` | contenedor `compustock_frontend` **recreado** y `healthy` en 8080; `docker inspect` confirma que corre la imagen `sha256:7d925c31c9bb…` (la anterior era `f0efb1efbceb`) |
| `npx ng build` sobre el código actual | limpio; bundle **`main-IRJLFDU6.js`** (13 336 B) y **`styles-CEN4FPRR.css`** |
| `GET /` en 8080 | sirve **`main-IRJLFDU6.js`**, el mismo hash que produce el build de producción actual |
| Deep links por HTTP (`/administracion/{sedes,departamentos,usuarios,encargados}`, `/dashboard`) | **200** (nginx `try_files` → `index.html`); el router resuelve después |

## Suites de la corrida de C3

| Suite | Resultado observado |
|---|---|
| `pytest` SQLite (`cd backend && pytest -q`) | **2163 passed / 127 skipped / 0 failed** (817.9 s) |
| `pytest` gated PostgreSQL (`POSTGRES_TEST_URL=…/postgres`) | **2287 passed / 3 skipped / 0 failed** (1 066.2 s; los 3 skipped son los de Redis sin `REDIS_TEST_URL`) |
| `ng test --watch=false --browsers=ChromeHeadless` (Edge) | **671 SUCCESS / 0 failed** (44 specs) |
| `npx ng build` | limpio; `main-IRJLFDU6.js` |

> **Incidente de entorno (no de código):** la primera corrida gated de C3 falló 3 pruebas de
> concurrencia de `test_correcciones_postgres_017.py` porque el contenedor `compustock_db` se
> reinició a mitad de la corrida (Docker Desktop, ~15:30). Las 3 pasan en aislamiento
> (**3 passed**, 10.3 s) y la **repetición completa** de la suite terminó en **2287 passed /
> 3 skipped / 0 failed**. No hubo cambios de código entre ambas corridas.

## Humo con sesión real

Sesión: **Cristian Gonzalez** (`crise.gonzalez@duocuc.cl`), rol **Administrador**, institución
*Instituto Profesional Los Alpes* (INST-001), reutilizada del navegador de verificación; no se
expusieron credenciales.

| Comprobación | Resultado observado |
|---|---|
| `/administracion` | redirige a `sedes`; barra con **3 pestañas** (`Sedes`, `Departamentos`, `Usuarios`); `role="tab"`, `aria-selected` en la activa y `role="tabpanel"` con `aria-labelledby="pestana-administracion-<sección>"` en cada deep link |
| `/administracion/departamentos` | 8 departamentos; **Suministros** («Unidad de suministros asignada automáticamente a los Bodegueros», **sin sede asignada**, activo) |
| `/administracion/usuarios` | **«15 usuario(s) en la institución»**; `Bodeguero E12 QA` y `Andres Vargas` en **Bodeguero · Suministros · Sede Maipu**; `Solicitante E12 QA` en **Solicitante · Biblioteca**, sin sede |
| Alta de usuario (modal `Nuevo usuario`) | Rol con **Bodeguero/Solicitante**; Departamento **deshabilitado** con «Suministros (asignación automática)» y `aria-describedby` a «El servidor asigna automáticamente el departamento «Suministros».»; **Sede del Bodeguero \*** con opciones `Selecciona una sede`, `Sede Providencia`, `Sede Maipu` (sin «Sin asignar») |
| Cambio de rol a Solicitante **desde el DOM** | aparece **Sede (filtro de departamentos)** y el Departamento se habilita con los **7** departamentos restantes (sin Suministros); confirma en el build de producción la corrección `[ngValue]` |
| Filtro del Solicitante | con `Sede Maipu`, el combo de Departamento queda en **Secretaría, RRHH, Biblioteca** |
| `/administracion/encargados` | el wildcard vigente redirige a **`/dashboard`**; no renderiza ninguna vista de encargados |
| `/dashboard` | KPI **Departamentos = 8** |

## Capturas

**No se generaron PNG nuevos** en este cierre: la evidencia es textual, DOM y SQL. Las
capturas `01`–`28` siguen en la carpeta como **históricas** de T13/T-17: las de
administración muestran la barra de **4 pestañas** y la vista de **Encargados**, hoy
retiradas, y no se usan como prueba de la enmienda.

---

# Corrección post-validación — cambio de rol manual (4200, 27/Nov/2026)

Cierra el hueco que el reviewer marcó en **AC-32** (y en las notas de AC-28/AC-29): el cambio
de rol **en ambos sentidos** sobre la misma cuenta, observado en el dev server.

- Sesión: **Admin QA** (`admin020.test+clerk_test@example.com`); no se expuso ninguna clave.
- Base de partida: la del cierre de la **013** — **13 usuarios**, **7 departamentos**, sin
  departamento `Suministros`, `Andres Vargas` en Biblioteca y token **`026.1`**
  (`013-ciclo-vida-ticket/evidencia/README.md` §11.3).
- Usuario intervenido: **`Ricardo Nilo`** (`ri.nilo@duocuc.cl`, `usuario_id 16`), entonces
  Solicitante en Biblioteca.

## 1. Solicitante → Bodeguero

| Comprobación | Resultado observado |
|---|---|
| Edición del usuario 16 con rol **Bodeguero** | Departamento **bloqueado** en «Suministros (asignación automática)»; Sede obligatoria (sin «Sin asignar»); se elige **Sede Maipu** |
| Motivo | «Reasignación organizacional» (catálogo D-5) |
| `PUT /api/v1/usuarios/16` | **200** |
| `PUT /api/v1/organizacion/usuarios/16/sede` | **200** |
| Fila resultante | **Bodeguero · Suministros · Sede Maipu** |
| Efecto colateral esperado | se creó el departamento **`Suministros`** (KPI de departamentos **7 → 8**) |

## 2. Bodeguero → Solicitante

| Comprobación | Resultado observado |
|---|---|
| Edición del mismo usuario con rol **Solicitante** | Departamento **habilitado** con «Selecciona un departamento» (**sin** Suministros); Sede como filtro «Todas las sedes» |
| Departamento elegido | **Biblioteca** |
| Motivo | «Cambio de funciones» (catálogo D-5) |
| `PUT /api/v1/usuarios/16` | **200** |
| `PUT .../sede` | **no se llama** (el Solicitante no persiste sede) |
| Fila resultante | **Solicitante · Biblioteca**, sin sede visible |

## 3. Estado final de la base viva (SQL)

```sql
-- tenant_inst_001_038aa2a9 (INST-001, Admin QA)
SELECT count(*) FROM "tenant_inst_001_038aa2a9".usuario;       -- 13
SELECT count(*) FROM "tenant_inst_001_038aa2a9".departamento;  -- 8

SELECT departamento_id, nombre_dep, sede_id, activo, descripcion
FROM "tenant_inst_001_038aa2a9".departamento
WHERE lower(trim(nombre_dep)) = 'suministros';                 -- 8 | Suministros | NULL | true | D-8

SELECT u.usuario_id, u.nombre, u.apellido, u.correo, u.rol_id, r.nombre_rol,
       u.departamento_id, d.nombre_dep, u.sede_id
FROM "tenant_inst_001_038aa2a9".usuario u
LEFT JOIN "tenant_inst_001_038aa2a9".rol r ON r.rol_id = u.rol_id
LEFT JOIN "tenant_inst_001_038aa2a9".departamento d ON d.departamento_id = u.departamento_id
WHERE u.correo = 'ri.nilo@duocuc.cl';

SELECT count(*) FROM "tenant_inst_001_038aa2a9".usuario u
JOIN "tenant_inst_001_038aa2a9".departamento d ON d.departamento_id = u.departamento_id
WHERE lower(trim(d.nombre_dep)) = 'suministros';               -- 0
```

| Verificación | Resultado |
|---|---|
| Usuarios | **13** |
| Departamentos | **8** |
| `Suministros` | `departamento_id 8`, `sede_id NULL`, `activo true`, descripción de D-8, **0 usuarios** |
| `Ricardo Nilo` (16) | **Solicitante (rol 4) · Biblioteca (6)**, `usuario.sede_id = 2` (la columna no se limpia) |
| Token del tenant | **`026.1`** |

## 4. Lectura de la evidencia anterior

La evidencia de **C2** (15 usuarios, Suministros con dos Bodegueros, KPI 8) y de **C3**
(15 usuarios en 8080) es **histórica**: la base fue reiniciada después por el cierre de la
**013** (13 usuarios, 7 departamentos; `013-ciclo-vida-ticket/evidencia/README.md` §11.3). La
base viva hoy es la de la tabla anterior: **13 usuarios y 8 departamentos**, con `Suministros`
creado por este recorrido y `Ricardo Nilo` de vuelta en Solicitante/Biblioteca.



