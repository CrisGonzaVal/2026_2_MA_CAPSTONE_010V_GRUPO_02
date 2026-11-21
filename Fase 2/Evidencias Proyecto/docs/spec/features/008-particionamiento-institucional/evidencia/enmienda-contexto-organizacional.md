# Feature 008 — Enmienda: contexto organizacional en la cabecera (20/Nov/2026)

Spec: [`../spec.md`](../spec.md) · Tareas: [`../tasks.md`](../tasks.md)

Esta evidencia cubre **solo** AC-22 y AC-23 de la enmienda del 20/Nov/2026. La evidencia
histórica de AC-1…AC-21 no se altera.

## Entorno y cuentas

- Backend `http://localhost:8000` (contenedor con `uvicorn --reload`), PostgreSQL 16
  `apt_erp`, frontend dev `http://localhost:4200` y borde nginx `http://localhost:8080`
  con la imagen reconstruida.
- Sesiones Clerk reales, código de verificación `424242`:

| Cuenta | Identidad | Contexto esperado |
|---|---|---|
| `bodeguero.test+clerk_test@example.com` | Roberto Díaz, usuario 12 | Bodeguero, sede 2 (Sede Maipu) |
| `solicitante.test+clerk_test@example.com` | Paula Rojas, usuario 11 | Solicitante, departamento 6 (Biblioteca) → sede 2 |
| `admin020.test+clerk_test@example.com` | Admin QA | Administrador, sin sede ni departamento |
| `superadmin.test+clerk_test@example.com` | Superadmin Sistema | Superadmin, sin sede ni departamento |

## AC-22 — `/auth/me` publica sede y departamento

- **Contrato vivo** (`GET /openapi.json` en `localhost:8000`): `IdentidadAutenticadaRespuesta`
  publica **nueve** claves requeridas (`usuario_id`, `sub`, `nombre`, `apellido`, `correo`,
  `rol`, `institucion`, `sede`, `departamento`). `sede` es
  `anyOf[SedeEfectivaRespuesta, null]` con `sede_id`/`nombre` requeridos, y `departamento`
  es `anyOf[DepartamentoEfectivoRespuesta, null]` con `departamento_id`/`nombre` requeridos.
  No se publica `rol_id`. El contrato conserva **75 operaciones** sobre **62 rutas**, sin
  altas ni bajas.
- **Derivación por rol (D-9):** `_contexto_organizacional` en
  `backend/app/services/auth_service.py` aplica la misma regla que
  `inventario_service.sede_del_alcance_por_rol`: el Bodeguero recibe `usuario.sede` y ningún
  departamento; el Solicitante recibe su departamento y la sede de ese departamento, no
  `usuario.sede_id`; Administrador y Superadmin reciben ambos `null`.
- **Asignación faltante (D-10):** el campo aplicable queda `null` y la respuesta sigue siendo
  **200**; no hay 409/403 en `/auth/me`. El 409 permanece en las operaciones de
  inventario/tickets que dependen de la sede.
- **Sin entrada del cliente:** query y body no alteran los campos; el servidor los deriva de
  la identidad autenticada.
- **Tests (rojo → verde):**
  - `backend/tests/api/test_auth_me_institucion.py::test_auth_me_bodeguero_expone_su_sede_sin_departamento`
  - `::test_auth_me_solicitante_expone_departamento_y_sede_del_departamento` (fixture con
    `usuario.sede_id` contradictorio: prevalece la sede del departamento)
  - `::test_auth_me_contexto_organizacional_nulo_sin_asignacion`
  - `::test_auth_me_administrador_y_superadmin_sin_contexto_organizacional`
  - `::test_openapi_auth_me_publica_sede_y_departamento_opcionales`
  - `::test_auth_me_no_acepta_sede_ni_departamento_del_cliente`
  - `backend/tests/api/test_auth.py::test_auth_me_no_expone_rol_id` (set exacto de nueve claves)
  - Rojo inicial: **9 failed / 71 passed** por `KeyError: 'sede'`/`'departamento'`, propiedades
    ausentes en OpenAPI y set de claves incompleto. Verde posterior: **80 passed** en los dos
    archivos.
- **Suites completas:** SQLite en memoria **1667 passed / 105 skipped**; gated PostgreSQL 16
  (base desechable, sin tocar `apt_erp`) **pendiente de registrar en el cierre**.
- **Sin DDL:** no se tocaron `database/`, modelos ni migraciones; sede y departamento ya
  existían y ya estaban relacionados con el usuario.

## AC-23 — Badges de sede y departamento en la cabecera

- **Tipo Angular:** `IdentidadAutenticada` incorpora `sede: SedeEfectiva | null` y
  `departamento: DepartamentoEfectivo | null`, espejo 1:1 del DTO.
- **Componente:** la aplicabilidad por rol vive en la matriz central
  `frontend/src/app/core/auth/roles.ts` (`ROLES_CONTEXTO_SEDE`,
  `ROLES_CONTEXTO_DEPARTAMENTO`, `puedeVerSede`, `puedeVerDepartamento`), cubierta por
  `roles.spec.ts`. `AppComponent` expone `mostrarSede`, `mostrarDepartamento`,
  `contextoSede` y `contextoDepartamento` como `computed()` sobre esa matriz y la
  identidad; el template pinta badges con `aria-label` después de `Institución`, y la
  cabecera usa `min-h-16`, `flex-wrap` y `gap` (solo Tailwind).
- **Pruebas de DOM:** `app.component.spec.ts` cubre Administrador sin badges nuevos,
  Bodeguero con sede, Bodeguero sin sede (`Sede: —`), Solicitante con departamento y sede,
  Solicitante sin asignaciones (ambos `—`), Superadmin sin badges y ausencia de selectores o
  entradas. **30 SUCCESS** en el archivo; suite completa **556 SUCCESS** con Edge.
- **Build de producción:** `npx ng build` OK; bundle inicial **339.16 kB** (94.67 kB de
  transferencia). Imagen Docker del frontend reconstruida
  (`sha256:e6fba304965b2cbe1eda541fc1fd28d27acd58879ec9135ac219484c5fb9db38`).

### Recorrido 4200 (sesiones Clerk reales)

| Rol | Cabecera observada | Resultado |
|---|---|---|
| Administrador | `Rol: Administrador` · `Institución: Instituto Profesional Los Alpes` | Sin `Sede` ni `Departamento` (sin cambios) |
| Bodeguero | `Rol: Bodeguero` · `Institución: …` · `Sede: Sede Maipu` | Sede visible; sin `Departamento` |
| Solicitante | `Rol: Solicitante` · `Institución: …` · `Sede: Sede Maipu` · `Departamento: Biblioteca` | Ambos badges con los valores de `/auth/me` |
| Superadmin | `Rol: Superadmin` · `Institución: Todas las instituciones` | Sin `Sede` ni `Departamento` (sin cambios) |

- **1024 px (peor caso, Solicitante):** la cabecera envuelve a **72 px** de alto, sin
  desbordamiento horizontal (`scrollWidth == innerWidth`) y sin errores de consola.

### Humo 8080 (imagen reconstruida)

- `GET /` → **200**, shell que referencia `main-HEJG5WKB.js` y `styles-ATWLLOTN.css`; ambos
  coinciden con el build del host. `HEAD /main-HEJG5WKB.js` →
  `Cache-Control: max-age=31536000,public, immutable`. Deep link `GET /tickets` → **200** con
  `<app-root>` (`try_files` de nginx).
- Sesión Solicitante en `http://localhost:8080/dashboard`: cabecera con `Sede: Sede Maipu` y
  `Departamento: Biblioteca`; consola sin errores.
- **Hallazgo operativo:** la primera carga del 8080 reutilizó un `index.html` cacheado por el
  navegador que apuntaba al bundle previo (`main-4MJD6WTB.js`), por lo que la vista no mostraba
  los badges aunque el servidor ya publicaba el bundle nuevo. Con recarga forzada
  (`ignoreCache`) se cargó `main-HEJG5WKB.js` y la cabecera mostró ambos badges. No es un
  defecto de la imagen: el `index.html` se sirve sin cache explícito y el bundle con hash e
  inmutable.

## Hallazgos y límites

- `/auth/me` se carga una vez por sesión en `AutenticacionService.identidad`; si un
  administrador cambia la sede o el departamento de un usuario con la sesión abierta, la
  cabecera no se refresca hasta el siguiente inicio de sesión. Es el comportamiento vigente de
  la identidad y queda fuera del alcance de esta enmienda.
- No se observaron errores de consola ni peticiones fallidas atribuibles a los badges.
