# Evidencia — Feature 022: Mantenimiento técnico I

**Fecha de cierre:** 12/Nov/2026
**Alcance:** limpieza de código muerto, coherencia documental y deduplicación
mecánica, sin cambio de comportamiento.
**Cuenta QA usada:** `admin020.test+clerk_test@example.com` (Administrador,
Instituto Profesional Los Alpes), con el código de prueba de Clerk `424242`.
No se transcriben tokens ni secretos.

## 1. Línea base (T1)

| Suite | Resultado base |
|---|---|
| `pytest -q` | **1496 passed, 88 skipped, 0 failed** |
| `ng test --watch=false --browsers=ChromeHeadless` | **537 SUCCESS** |
| `ng build` | Limpio |
| Operaciones | 73 de negocio en `MATRIZ_PERMISOS`, 75 en OpenAPI |

## 2. Cambios por tarea

| Tarea | Resultado |
|---|---|
| **T2** | Eliminado `frontend/src/app/features/administracion/services/usuario.service.ts`; 0 referencias a `UsuarioService`/`usuario.service`; `stack.md` apunta a `administracion.service.ts`. |
| **T3** | `AGENTS.md` §4 y árbol de `stack.md` con `public/`, `shared/{components,config,interfaces,utils}` y las seis features; Notas 1 y 2 corregidas; README raíz con 27/24 y `021.1`; `frontend/README.md` propio. |
| **T4** | Creado `shared/utils/errores-http.ts`; los seis `mensajeDeError*` delegan conservando nombre, firma y textos. Rojo inicial: `Module not found './errores-http'`. |
| **T5** | Creado `auth_service.correo_del_actor`; eliminadas las dos copias de `_correo_actor`; `organizacion_service` y `usuario_service` usan el helper. Rojo inicial: `ImportError: cannot import name 'correo_del_actor'`. |

## 3. Suites finales

| Suite | Resultado |
|---|---|
| `pytest -q` | **1499 passed, 88 skipped, 0 failed** (1496 previos + 3 nuevos) |
| `pytest tests/services/test_auth_service.py -q` | **3 passed** |
| `ng test --watch=false --browsers=ChromeHeadless` | **549 SUCCESS** (537 previos + 12 nuevos) |
| `ng build` | Limpio (21.5 s en host) |
| `docker compose build frontend` | Imagen reconstruida; build de producción limpio (51.4 s) |

## 4. Contrato y áreas protegidas

| Verificación | Resultado |
|---|---|
| `MATRIZ_PERMISOS` | **73** operaciones de negocio |
| `GET /openapi.json` en vivo | **75** operaciones (73 de `/api/v1` + `GET /` + `GET /health`) |
| `database/`, `backend/app/core/permisos.py`, `backend/app/models/`, templates, `.env` | **Sin cambios** (`git diff --name-only`) |
| Versión y tablas | `021.1`, 27 de control / 24 por tenant, intactas |
| `_correo_actor` | **0 referencias** |
| `UsuarioService` / `usuario.service` | **0 referencias** |

## 5. Recorrido funcional — 4200

Sesión de Administrador. Se recorrieron:

| Vista | Comprobación |
|---|---|
| `/dashboard` | Métricas (562 unidades, 6 pedidos activos, 7 departamentos, 3 alertas) y actividad reciente. |
| `/inventario` | Catálogo con 10 insumos, filtros de sede/departamento y pestaña de gestión. |
| `/inventario/4` | Detalle de «Boligrafo Bic Cristal» con stock total y desglose por sede. |
| `/inventario/99999` | Estado controlado «Producto no encontrado» con reintento. |
| `/tickets` | Tablero por estados con 9 pedidos de la semilla. |
| `/tickets/2` | Detalle, ítems, historial y cobertura por producto. |
| `/compras/necesidades` | 4 filas / 33 unidades sugeridas, con pedidos que componen la demanda. |
| `/compras` | `OC-2026-000001`, estado `Recibida`, factura y plan de cobertura. |

**Consola:** solo el aviso preexistente de Clerk en claves de desarrollo. Sin
errores nuevos.

## 6. Humo — 8080

Imagen reconstruida con `docker compose build frontend` y recreada con
`docker compose up -d`.

| Vista | Comprobación |
|---|---|
| `/dashboard` | Carga con la misma sesión y métricas. |
| `/inventario` | Catálogo cargado; posteriormente 10 insumos y filtros activos. |
| `/compras/necesidades` | 4 filas / 33 unidades sugeridas, con el desglose de pedidos. |

**Consola:** solo el aviso preexistente de Clerk. Sin errores nuevos.

## 7. Diff

`git diff --stat`: **16 archivos**, 233 inserciones y 231 eliminaciones
(incluye el borrado de 32 líneas del servicio muerto). Además quedan como
nuevos:

- `backend/tests/services/test_auth_service.py`
- `frontend/src/app/shared/utils/errores-http.ts`
- `frontend/src/app/shared/utils/errores-http.spec.ts`
- `docs/spec/features/022-mantenimiento-tecnico/` (`spec.md`, `plan.md`,
  `tasks.md` y esta evidencia)

## 8. Criterios de aceptación

Los nueve AC de `spec.md` §5 quedaron marcados con su evidencia. El roadmap
registra la 022 como `[x]` el 12/Nov/2026; las Features 015/016 conservan su
sprint y el Hito 2 sigue en el 11/Dic/2026.
