# Feature 012 — Tareas

Spec: [`spec.md`](spec.md) · Plan: [`plan.md`](plan.md)

> Ejecutar en orden, una tarea por llamada, con pruebas primero. T1 bloquea todo cambio de modelo/DDL/routing hasta aprobación explícita de la justificación en `stack.md`. Ante discrepancia con spec/plan, detenerse y preguntar; no ajustar silenciosamente permisos existentes.

## Preparación y modelo

- [x] **T1 — Incorporar y aprobar justificación de cambios control-only (bloqueante).**
  - Archivos: `docs/spec/stack.md` (incorporación/aprobación usuario o coordinador; no ejecutar cambios de modelo antes de ello).
  - Aplicar el texto exacto de plan.md §1: `control.institucion.activo`, `funcion_institucion` con seis IDs cerrados, espejo limitado a `institucion_id`+`nombre`, DDL/seed/constructor/migración y razón de auxiliares sin entidad nueva de dominio.
  - **AC:** AC-1, AC-2, AC-5, AC-13.
  - **Hecho cuando:** texto incorporado y aprobación explícita recibida; sin aprobación, T2–T4 que toquen modelo/DDL quedan bloqueadas.

- [x] **T2 — Cerrar diseño técnico y contratos antes de implementar.**
  - Archivos: pruebas iniciales/backend y Angular, documentación de decisiones en la tarea; inspección de metadata, rutas actuales, operaciones matriz, constructor/DDL.
  - Fijar endpoint/método/ruta por operación, DTOs y asociación capacidad-operación; diseñar cómo distinguir modelo control institucional de espejo tenant. Comparar exactamente las 28 entradas actuales de matriz para asegurar que no se modifican. Redactar pruebas rojas: institución inactiva 401 antes de tenant/version, gating 403 adicional a rol, matriz/OpenAPI y casos de espejo.
  - **AC:** AC-1…AC-5, AC-11…AC-13.
  - **Hecho cuando:** contratos de rutas/capacidades y tests fallan por ausencias previstas, y existe una decisión técnica verificable para que `activo` no se añada al espejo tenant.
  - **Entregado:** decisión documentada en `diseno-tecnico.md` (rutas `/control` + CRUD organizacional, mapa capacidad↔operación en `app/core/capacidades.py`, separación canónico-control (`BaseControl`/`InstitucionControl`/`FuncionInstitucion`) vs espejo tenant de dos columnas en `Institucion`, resolución de institución inactiva→401 antes de versión, 28 entradas de matriz como referencia). Pruebas rojas en `backend/tests/no_funcional/seguridad/test_permisos_012.py`, `test_contrato_control_012.py`, `test_capacidades_gating_012.py`, `test_institucion_inactiva_012.py`, `test_espejo_institucion_012.py` y gated `backend/tests/funcional/sistema/test_gestion_administrativa_postgres_012.py`. Suite SQLite: 701 passed / 50 skipped / 23 failed (solo las pruebas rojas de la 012, ausencias previstas; patrón 010/011); ninguna prueba previa rota.
  - **Hallazgo (reportado, no resuelto):** AC-6/AC-11 requieren estado lógico (activo) en `sede` y `departamento` tenant, no cubierto por la justificación `stack.md` vigente (control-only). Ver `diseno-tecnico.md` §1.2.

- [x] **T3 — Implementar modelos control-only y DDL canónico.**
  - Archivos: modelos control/institución, `models/__init__.py`, `database/01_esquema.sql`, constructor `database/03_construir_tenants_011.sql` o sucesor, `02_datos_semilla.sql` si aplica.
  - Crear `control.institucion.activo` y `control.funcion_institucion` con unicidad/FK/estado explícito; mantener plantilla tenant `institucion` exactamente con `institucion_id` y `nombre`; no sembrar capacidades en tenant ni copiar `activo` al espejo. Preservar guardia seed y el orden initdb.
  - **AC:** AC-1, AC-2, AC-5, AC-13.
  - **Hecho cuando:** pruebas metadata/DDL y PostgreSQL gated confirman control con las columnas/filas esperadas y espejo tenant limitado a los dos campos aprobados.
  - **Entregado:** `app/models/control_canonico.py` (`BaseControl`, `InstitucionControl` con `activo`, `FuncionInstitucion` PK `(institucion_id, funcion)` + CHECK de los seis IDs, `CAPACIDADES`), `Institucion` reducida a `institucion_id`+`nombre`, `activo` en `sede`/`departamento` (tenant) por decisión de usuario justificada en `stack.md`; DDL 01 (control `activo`+`funcion_institucion`, `activo` en sede/departamento), semilla 02 (24 capacidades + guardia/truncado ampliados), constructor 03 (espejo de dos columnas, `activo` en sede/departamento tenant, normalización idempotente de capacidades); `control_service` separa canónico (InstitucionControl) de espejo (Institucion) e inicializa las seis capacidades al aprovisionar. Ajustes de harness: `conftest` crea `BaseControl.metadata` primero, `test_institucion_inactiva_012._preparar` usa `flush`, gated 010 crean `BaseControl`. Suite SQLite: 708 passed / 50 skipped / 16 failed (las 16 rojas son de T4–T7). Gated PostgreSQL: DDL/espejo verdes; versión/migración rojas por T4.

- [x] **T4 — Crear migración PostgreSQL operacional 012.1.**
  - Archivos: `database/migraciones/003_migracion_gestion_administrativa_012.sql`, constante objetivo en `backend/app/core/config.py` solo cuando la migración esté lista.
  - Implementar preflight, `activo` inicial, tabla auxiliar, seis filas por institución, validación de espejo sin alterarlo, versión 012.1 al final, transacción/idempotencia y sin semilla. Probar contra snapshots PostgreSQL 16 derivados de 011.1, fallo y segunda ejecución.
  - **AC:** AC-1, AC-2, AC-5, AC-13, AC-14.
  - **Hecho cuando:** PostgreSQL gated verifica preservación de datos/maps, filas únicas, rollback ante fallo y segunda ejecución sin cambios operativos; ninguna versión se marca parcialmente.
  - **Entregado:** `database/migraciones/003_migracion_gestion_administrativa_012.sql` (bloque `DO` único y atómico, fuera de initdb, sin semilla): preflight de versiones 011.1/012.1 y estado parcial; `ALTER control.institucion ADD COLUMN activo`; `CREATE TABLE IF NOT EXISTS control.funcion_institucion` (PK par, FK local, CHECK de seis IDs); seis filas habilitadas por institución (`ON CONFLICT DO NOTHING`); `activo` en `sede`/`departamento` de control y de cada tenant vía catálogo de esquemas (nunca `search_path`); **reducción del espejo tenant `institucion` a `institucion_id`+`nombre`** (`DROP COLUMN IF EXISTS rut, direccion`, decisión confirmada por el usuario); validación de espejo de dos columnas; `version_esquema` control/tenants a `012.1` al final; verificación global. `VERSION_ESQUEMA_OBJETIVO` de `011.1`→`012.1` en `config.py`; constructor limpio `03_construir_tenants_011.sql` también a `012.1`. Ajuste coherente de tests que fijaban `011.1` por valor (`test_control_modelo_010.py`, `test_control_instituciones_010.py`, `_soporte_sede_011.py`, `test_control_sede_011.py`, gated `test_aprovisionamiento_postgres_010.py`); la migración 002 y sus tests conservan `011.1` (independientes). Nuevos tests gated en `test_gestion_administrativa_postgres_012.py`: transición 011.1→012.1 preservando datos/mapa y aborto ante estado parcial. Suite SQLite: 708 passed / 52 skipped / 16 failed (las 16 rojas siguen siendo las de T5–T7, sin regresiones). Gated PostgreSQL: 758 passed / 16 failed (solo T5–T7); verificación manual sobre clon real de `apt_erp` (011.1) confirma reducción de espejo, 24 capacidades, versiones `012.1`, datos/mapa intactos, segunda ejecución sin cambios y aborto ante parcial sin marcar versión.
  - **Findings:** (1) El espejo tenant real de 011.1 tenía **cuatro** columnas (`institucion_id`, `nombre`, `rut`, `direccion`), no dos como asumía la premisa; el usuario confirmó reducirlo a dos. (2) Ninguna versión se marca parcialmente: el bloque revierte completo; un tenant con estructura 012 sin versionar aborta en cerrado.

## Backend: routing, servicios, endpoints y pruebas

- [x] **T5 — Aplicar estado institucional en routing y componer gating de capacidades.**
  - Archivos: `tenant_service.py`, `dependencies.py`, servicio de control/capacidades, pruebas de routing/gating.
  - Consultar `control.institucion.activo` antes de versión/sesión tenant y denegar institución inactiva como identidad no resoluble 401. Añadir dependencia de capacidad independiente de `requiere_operacion`; capacidad apagada 403 sin mutación; no modificar las 28 operaciones existentes ni gatear `/control`/Superadmin global.
  - **AC:** AC-2, AC-5, AC-13.
  - **Hecho cuando:** tests HTTP/PostgreSQL prueban suspensión con sesión Clerk vigente, reactivación según versión, y cada capacidad deniega adicionalmente a matriz sin consultar/escribir tenant indebidamente.
  - **Entregado:** `app/core/capacidades.py` (mapa central `MAPA_OPERACION_CAPACIDAD` de 35 operaciones + `capacidad_de_operacion`; `CAPACIDADES` reexportado del modelo canónico; `/auth/me` y `/control/*` sin gating), `app/services/capacidad_service.py` (`capacidad_habilitada`), `tenant_service` (`ErrorInstitucionInactiva` + `_institucion_activa`: consulta `InstitucionControl.activo` tras el mapa activo y **antes** de la versión; ausencia de fila canónica no suspende, compatibilidad con legado), `dependencies.requiere_capacidad(metodo, ruta)` (dependencia adicional; 403 sin mutación; identidad global y operaciones sin capacidad no se gatean) y normalización **401** de institución inactiva en `get_contexto_solicitud`/`get_db_negocio`. Default sin fila de capacidad: **habilitada** (D-6: la ausencia no es una desactivación explícita; documentado en `diseno-tecnico.md` §2). Ajustes de harness: `test_capacidades_gating_012._cliente_probe` crea la institución canónica antes de la fila de capacidad (FK), y `test_integracion_multitenant_010`/`test_aislamiento_sede_011` materializan el control vigente (`BaseControl` + `activo`) al montar el esquema de control. Suite SQLite: 716 passed / 52 skipped / 8 failed (solo T6/T7); gated PostgreSQL: 768 passed / 8 failed (solo T6/T7); sin regresiones.

- [x] **T6 — Implementar servicios/DTOs y operaciones administrativas de control SaaS.**
  - Archivos: schemas control, servicios control/global, endpoints control; matriz solo entradas administrativas nuevas de Superadmin.
  - Implementar CRUD lógico de instituciones, sincronización del espejo solo para `institucion_id`/`nombre`, dashboard atribuido y consulta/actualización de seis capacidades; mantener desactivación reversible/no destructiva y fallo completo si institución activa requerida falla. Delegar lógica a services.
  - **AC:** AC-1…AC-5, AC-13.
  - **Hecho cuando:** pruebas de API verifican contrato/estados, homónimos, inactivas excluidas de métricas, capacidades persistidas y matriz con solo operaciones nuevas de control para Superadmin.
  - **Entregado:** `schemas/control_schema.py` ampliado (`InstitucionControlRespuesta`, `InstitucionEdicion`, `InstitucionEstado`, `InstitucionEstadoRespuesta`, `CapacidadFuncional` —Enum de los seis IDs—, `CapacidadRespuesta`, `CapacidadActualizar`, `InstitucionMetricasRespuesta`, `DashboardSaaSRespuesta`; `extra="forbid"` en las entradas). `services/control_service.py` con 7 funciones delegadas (`listar_instituciones`, `obtener_institucion`, `editar_institucion` con `_sincronizar_espejo` solo `institucion_id`+`nombre`, `cambiar_estado_institucion`, `listar_capacidades`, `actualizar_capacidad`, `dashboard_saas` con métricas lógicas SQLite y REPEATABLE READ PostgreSQL reusando `global_service.lectura_global`; inactivas listadas sin métricas; activa sin tenant → `ErrorDashboardSaaS` completo) y sus excepciones. `endpoints/control.py` con las 7 rutas (router delgado, `Depends(requiere_operacion)` + `get_db`, `response_model`/`status_code`/OpenAPI 401/403/404/409/422). `core/permisos.py`: 7 entradas nuevas exclusivas Superadmin (aditivas; las 28 previas intactas). Reconciliación de las suites de transcripción previas (patrón 011) para no regresar: `test_permisos.py`, `test_permisos_008.py`, `test_permisos_010.py` y `test_permisos_endpoints.py` (35 = 28 + 7). Suite SQLite: 749 passed / 52 skipped / 3 failed (solo las 3 de T7 en `test_permisos_012.py`, que exigen el CRUD organizacional). Gated PostgreSQL: 801 passed / 3 failed (idem). Los 5 de `test_contrato_control_012.py` verdes. `diseno-tecnico.md` §1 sin cambios (contrato idéntico).

- [x] **T7 — Implementar CRUD organizacional y operaciones de matriz para Admin Institucional.**
  - Archivos: schemas/servicios organizacionales, endpoints de organización, `api.py`, matriz central y tests.
  - Extender las reglas de 011 para CRUD lógico de sedes/departamentos/usuarios y uso existente de encargados/asignaciones. Validar Clerk preexistente sin crear/modificar identidades; respetar tenant y reglas 011; 404 para ajenos, 409 para dependencias incompatibles; añadir operaciones Admin nuevas sin cambiar roles de las 28 operaciones existentes.
  - **AC:** AC-6…AC-12, AC-13.
  - **Hecho cuando:** pytest cubre listados/mutaciones, límites tenant, Clerk, asociaciones, sedes requeridas y desactivación idempotente o conflicto con motivo concreto; `/openapi.json` refleja el contrato.
  - **Entregado:** `schemas/organizacion_schema.py` (`activo` añadido a `SedeRespuesta`; `SedeCrear`/`SedeEdicion`/`SedeEstado`/`SedeEstadoRespuesta`, `DepartamentoRespuesta`, `DepartamentoCrear`/`DepartamentoEdicion`/`DepartamentoEstado`/`DepartamentoEstadoRespuesta`; `extra="forbid"` en entradas) y `schemas/usuario_schema.py` (`UsuarioEdicion` —sin correo—, `UsuarioEstado`, `UsuarioEstadoRespuesta`). `services/organizacion_service.py` con las 9 operaciones nuevas (`crear_sede` con unicidad de nombre → 409, `editar_sede`, `cambiar_estado_sede`, `listar_departamentos`, `crear_departamento`, `editar_departamento`, `cambiar_estado_departamento`, `editar_usuario`, `cambiar_estado_usuario`) sobre los helpers de 011 (`_sede_en_alcance`/`_departamento_en_alcance`/`_usuario_en_alcance` → 404 indistinguible, `_conflicto` → 409); desactivación lógica idempotente y **determinista** (sede: 409 si hay departamentos activos o Bodegueros asignados; departamento: 409 si hay usuarios vinculados; usuario: 409 si es encargado), reactivación por el mismo endpoint. Estado del usuario local en `mapa_usuario_esquema.activo` (sin columna nueva): `cambiar_estado_usuario` recibe la sesión de tenant (`db`, resuelve usuario/ámbito) y la de control (`db_control`, persiste el mapa; crea la fila con el esquema determinista si no existía). `usuario_service.crear_usuario` valida Clerk con la costura `obtener_verificador_correo_clerk` (422 si no existe, 503 si la frontera falla; sin crear/modificar identidades). `endpoints/organizacion.py` (7 rutas, router delgado, `get_db_negocio`) y `endpoints/usuarios.py` (`PUT /{usuario_id}` y `PATCH /{usuario_id}/estado`, con `get_db_negocio`+`get_db`; `POST /` inyecta la costura Clerk). `core/permisos.py`: 9 entradas nuevas (7 `/organizacion/*` → Administrador; 2 `/usuarios/*` → Superadmin+Administrador); aditivas, las 28 previas intactas (total **44**). El mapa `capacidades.py` ya cubría las 9 rutas (T5). Reconciliación de las suites de transcripción a 44: `test_permisos.py`, `test_permisos_008.py`, `test_permisos_010.py` y `test_permisos_endpoints.py` (payloads/rutas/DTOs/201). Ajuste de harness por la costura Clerk del alta: `conftest._cliente_de_prueba` y `test_rol_asignable_usuarios._cliente` overridean el verificador. Nuevo `backend/tests/funcional/integracion/test_organizacion_crud_012.py` (25 pruebas: contrato/matriz, sedes, departamentos, usuarios, aislamiento 404, 401/403, idempotencia/409, Clerk). Suite SQLite: **813 passed / 52 skipped / 0 failed**; gated PostgreSQL (`POSTGRES_TEST_URL`, :5433): **865 passed / 0 failed / 0 skipped**. Sin regresiones.
  - **Decisión (reportada):** la validación Clerk del alta local (D-3/AC-8) se cableó en la operación existente `POST /api/v1/usuarios/` como exige el diseño §1.2; no cambia ruta, roles ni contrato de éxito, solo añade la condición de identidad preexistente. Requirió stubear la costura en `conftest` y `test_rol_asignable_usuarios` (ajuste de harness, no de semántica).

- [x] **T8 — Completar tests backend de API, gating, migración y regresión.**
  - Archivos: `backend/tests/` (SQLite y pruebas PostgreSQL gated), pruebas de permisos/migración existentes.
  - Cubrir todos los AC de backend, acceso API directo con cada capability off/on, no mutación en 403, espejo exacto, inicialización/re-ejecución, institución activa/inactiva y 401/403/404/409/422. Verificar `/openapi.json` y comparación de entradas existentes de matriz.
  - **AC:** AC-1…AC-5, AC-11…AC-14.
  - **Hecho cuando:** `pytest` SQLite pasa y suite `POSTGRES_TEST_URL` pasa sin skips, incluyendo DDL, migración, routing, namespaces y aislamiento.
  - **Entregado:** **cableado real del gating** por capacidad en los routers según `MAPA_OPERACION_CAPACIDAD` (inventario: 9 rutas catalogo/inventario; tickets: 5 de tickets/kanban; dashboard: 1; organizacion: 13 de `gestion_organizacional`; usuarios: 7 —incluidas las 5 previas—). Sin gatear `/auth/me` ni `/control/*`; sin tocar la matriz (`permisos.py`). Seam nuevo `dependencies.get_contexto_capacidad` (resolución tolerante del contexto; si no resuelve → `None` y no gatea, preservando la precedencia 401/403 de `get_db_negocio`); `requiere_capacidad` pasa a depender de él. Contrato OpenAPI completado en `PUT/PATCH /usuarios/{id}` (404/409/422 documentados). Nuevos tests: `tests/no_funcional/seguridad/test_gating_capacidades_endpoints_012.py` (gating E2E sobre rutas reales: 403 sin mutación por grupo, restauración al habilitar, capacidad adicional a la matriz) y `tests/funcional/integracion/test_contrato_organizacion_012.py` (OpenAPI de las 9 operaciones nuevas: éxito/401/403/404/409/422/response_model/security). Ajuste de harness: umbral no-N+1 de `test_tablero_kanban.py` (5→7 por la sobrecarga fija del gating) y override del seam en la app-sonda de `test_capacidades_gating_012.py`; gated PostgreSQL nuevo `tests/funcional/sistema/test_gestion_administrativa_http_postgres_012.py` (gating HTTP directo, institución inactiva→401 y reactivación, aislamiento cross-tenant 404, dashboard SaaS homónimos/inactiva/fallo completo) con `control.version_esquema` sembrado y colisión de ids entre esquemas. **Resultados:** SQLite `837 passed / 58 skipped / 0 failed`; gated PostgreSQL con `POSTGRES_TEST_URL` `895 passed / 0 failed / 0 skipped`.
  - **Hallazgo:** `POST /organizacion/departamentos` no implementa/documenta `409` (el diseño §1.2 lo listaba); la alta de departamento no tiene regla de conflicto. Registrado en `diseno-tecnico.md` §2.

## Frontend

- [x] **T9 — Construir portal SaaS `/control` del Superadmin.**
  - Archivos: componentes/rutas/servicios/types en `features/control/`, `shared/interfaces/index.ts`, pruebas Angular.
  - Añadir dashboard SaaS, gestión institucional, activación/desactivación, funciones por institución; reusar Clerk/guard/interceptor existentes. Usar standalone, `inject()`, signals/computed y Tailwind; no presentar control de tenant como operación de negocio.
  - **AC:** AC-1, AC-2, AC-4, AC-5.
  - **Hecho cuando:** `ng test` verifica render, carga/éxito/error, activo/inactivo, atribución y las seis capacidades con estados persistidos del servicio.
  - **Entregado:** `shared/interfaces/index.ts` ampliado con los tipos 1:1 de `control_schema.py` (`InstitucionControl`, `InstitucionEdicion`, `InstitucionEstado`, `InstitucionEstadoRespuesta`, `CapacidadFuncional` —seis IDs cerrados—, `CapacidadRespuesta`, `CapacidadActualizar`, `InstitucionMetricas`, `DashboardSaaS`). `ControlService` ampliado con las 7 operaciones de control (listar/obtener/editar/estado/dashboard/capacidades/actualizar-capacidad) sobre los contratos reales. Vistas standalone con `inject()`/`signal()`/`computed()` y solo Tailwind: `DashboardSaasComponent` (KPI de activas + tabla con atribución nombre+id, inactivas sin métricas), `InstitucionesComponent` (listado, edición de atributos canónicos con PUT sin estado, desactivar/reactivar con confirmación y PATCH, navegación a capacidades), `CapacidadesComponent` (las seis capacidades con su estado persistido y toggle `PUT .../capacidades/{funcion}`) y `ControlNavComponent` (navegación del portal). `control.routes.ts` suma `dashboard`, `instituciones` y `instituciones/:institucionId/capacidades`, todas lazy y bajo `ControlSuperadminGuard`; no monta layout operativo tenant. Helper `control-errores.ts` para mensajes 401/403/404/409/422. Pruebas: 31 nuevas (`control.service.spec.ts` 7, `control.routes.spec.ts` actualizado 4, `dashboard-saas.component.spec.ts` 7, `instituciones.component.spec.ts` 10, `capacidades.component.spec.ts` 6). `ng test` **229 SUCCESS / 0 failed** (baseline 198 + 31); `ng build` limpio.

- [x] **T10 — Construir vistas administrativas institucionales y navegación de capacidades.**
  - Archivos: `features/administracion/`, servicios de feature, interfaces compartidas y sus tests.
  - Crear vistas de sedes, departamentos, usuarios y encargados. Reusar APIs/reglas 011 y exponer asignación de sede/departamento/Bodeguero y asociaciones; mostrar estados activos, ausencia de asignación, errores 409/404 y opciones solo del tenant. La disponibilidad de capacidades solo afecta presentación, no autoriza.
  - **AC:** AC-5…AC-12.
  - **Hecho cuando:** pruebas Angular comprueban estados de lista/formulario, asociaciones vacías/existentes, selección limitada a respuestas del tenant, estados activos/inactivos y errores de dependencias.
  - **Entregado:** `shared/interfaces/index.ts` ampliado con los contratos 1:1 de `organizacion_schema.py` y `usuario_schema.py` (`Sede`, `SedeCrear/Edicion/Estado/EstadoRespuesta`, `DepartamentoGestion`, `DepartamentoCrear/Edicion/Estado/EstadoRespuesta`, `AsignacionSedeCrear`, `AsignacionSedeDepartamentoRespuesta`, `AsignacionSedeUsuarioRespuesta`, `Encargado`, `EncargadoCrear`, `UsuarioEdicion`, `UsuarioEstado`, `UsuarioEstadoRespuesta`); `Usuario` gana `sede_id?`/`activo?` opcionales (el `GET /usuarios/` vigente no los publica: la vista renderiza "Estado no informado"/ausencia de asignación en vez de inventarlos). `features/administracion/services/administracion.service.ts` (`AdministracionService`) con las 16 operaciones de sedes/departamentos/usuarios/encargados; `administracion-errores.ts` (mensajes 401/403/404/409/422). Layout `AdministracionComponent` + `AdministracionNavComponent` y `administracion.routes.ts` como segmento lazy con vistas hijas `sedes`, `departamentos`, `usuarios`, `encargados` (todas por `loadComponent`). Vistas standalone con `inject()`/`signal()`/`computed()` y solo Tailwind: `SedesComponent` (lista + crear/editar + activar/desactivar con confirmación, estado y 409), `DepartamentosComponent` (lista con sede asignada/ausencia, crear/editar, activar/desactivar, asignar sede limitada a sedes del tenant, 409), `UsuariosComponent` (lista con rol/departamento/estado/sede, editar sin correo, activar/desactivar, asignar sede de Bodeguero, 409) y `EncargadosComponent` (por departamento: asociar/retirar, candidatos limitados a Solicitantes del mismo departamento, estado vacío). La navegación a `/administracion` para el Administrador ya existía (`app.component.html` vía `puedeAdministrar()`); no se tocó `roles.ts`/`app.routes.ts`. **Hallazgo (reportado):** no existe endpoint de capacidades para el tenant (`/control/...` es solo Superadmin), así que se omitió la presentación condicional por capacidad; el gating real está en el backend (403).
  - **Tests:** `services/administracion.service.spec.ts` (16), `sedes.component.spec.ts` (10), `departamentos.component.spec.ts` (7), `usuarios.component.spec.ts` (8), `encargados.component.spec.ts` (6) y `administracion.routes.spec.ts` (3). `ng test` **279 SUCCESS / 0 failed** (baseline 229 + 50); `ng build` limpio.
  - **Ajuste post-cierre (UX, D-6/AC-10):** el combo de **rol del alta** ofrecía los cuatro roles a un Administrador, aunque el backend solo le permite asignar `Bodeguero`/`Solicitante` (`_validar_rol_asignable` → 403 sin crear fila; Superadmin sí asigna los cuatro). Se alinea **en el frontend**: `core/auth/roles.ts` suma `ROLES_ASIGNABLES_ADMINISTRADOR` y `puedeAsignarRol` (réplica de la regla de servidor), y `usuarios.component.ts` filtra el combo con un `computed` sobre la identidad activa (`AutenticacionService`), con el default del alta en el primer rol asignable. Se prefirió esto a filtrar `GET /usuarios/roles`: el catálogo es compartido (D-5/AC-3 de la 008) y también resuelve el nombre del rol de cada usuario listado; filtrarlo rompería esa resolución y no añadiría autoridad (la frontera sigue en la API). Sin cambios de matriz, contrato del endpoint ni semántica 403/409/422. Tests: `usuarios.component.spec.ts` (+4: Administrador→2, Superadmin→4, default asignable, recálculo al cambiar identidad) y `roles.spec.ts` (+3: constante y `puedeAsignarRol`). `ng test` **299 SUCCESS / 0 failed**; `ng build` limpio; recorrido en 4200 (identidad Administrador) confirma el combo con solo Bodeguero/Solicitante.
  - **Ajuste post-cierre (UX, D-6/AC-10) — rol del combo de edición:** el formulario de **editar usuario** seguía iterando el catálogo completo (`roles()`), así que un Administrador veía `Superadmin` y `Administrador` como opciones cambiables; elegirlas respondía **403** de `_validar_rol_asignable` (la misma regla que el alta). Se añade `rolesEdicion` en `usuarios.component.ts`: filtra con `puedeAsignarRol`, **conserva el rol actual** del usuario editado aunque no sea asignable (para que al editar a otro Administrador el combo muestre su valor persistido en vez de quedar vacío) y **excluye `Superadmin` siempre**, porque es una identidad de control y no un rol de tenant (Feature 017, AC-9/D-10). Sin cambios de backend, matriz ni contrato. Tests: `usuarios.component.spec.ts` (+3: Administrador solo ve Bodeguero/Solicitante en el combo de edición; editar un Administrador mantiene su rol visible sin ofrecer Superadmin; la edición institucional nunca ofrece Superadmin, ni con identidad Superadmin). `ng test` **399 SUCCESS / 0 failed**; `ng build` limpio.


- [x] **T11 — Excluir Superadmin de `/tickets` por navegación y guard solamente.**
  - Archivos: `app.routes.ts`, `core/auth/roles.ts`, guard/tickets, `app.component.ts/html`, pruebas Angular.
  - Ocultar el enlace y denegar ruta directa a Superadmin; mantener `/tickets` disponible para Administrador/Bodeguero/Solicitante conforme a configuración vigente. No tocar permisos backend de tickets ni incorporar esta exclusión a la matriz.
  - **AC:** AC-3.
  - **Hecho cuando:** `ng test` confirma redirección Superadmin a `/acceso-denegado`, ausencia del enlace, Kanban sin render y acceso conservado para los roles de negocio.
  - **Entregado:** `roles.ts` suma `ROLES_TICKETS = ['Administrador','Bodeguero','Solicitante']` (`ROLES_TODOS` menos Superadmin) y el helper `puedeVerTickets`; `ROLES_OPERATIVOS_TICKETS` queda **intacto** (el Superadmin sigue habilitado por matriz backend). `app.routes.ts` protege `/tickets` con `ROLES_TICKETS` en vez de `ROLES_TODOS`. `app.component.ts` expone `puedeVerTickets` (computed sobre la identidad) y `app.component.html` condiciona el enlace `Tickets / Kanban` con `@if`. Sin cambios en backend, `permisos.py`, matriz ni vistas del Kanban. Pruebas nuevas (7): `roles.spec.ts` (2), `app.routes.spec.ts` (1: excluye Superadmin, conserva negocio), `role.guard.spec.ts` (1: `ROLES_TICKETS` deniega Superadmin y concede a negocio), `app.component.spec.ts` (2: sin enlace a Superadmin con `/control` presente; enlace conservado a negocio) y `core/guards/tickets-acceso.spec.ts` (1: navegación real con `RouterTestingHarness`, Superadmin → `/acceso-denegado` y sin `app-tickets`). `ng test` **286 SUCCESS / 0 failed** (baseline 279 + 7); `ng build` limpio.

- [x] **T12 — Integrar y verificar suites frontend/backend, build y contrato API.**
  - Archivos: correcciones solo si se detectan defectos conforme a tareas previas; evidencia en documentación al observar resultados.
  - Ejecutar `pytest`, PostgreSQL gated con `POSTGRES_TEST_URL`, `ng test --watch=false --browsers=ChromeHeadless`, `ng build`; revisar `/openapi.json`, estado de 28 operaciones previas y nuevas entradas. No cerrar casos gated por resultado SQLite.
  - **AC:** AC-1…AC-13.
  - **Hecho cuando:** suites completas pasan, OpenAPI coincide con DTO/estados y la matriz no presenta cambios inadvertidos a operaciones existentes.
  - **Entregado:** cierre del defecto de integración de `GET /usuarios/` detectado en T10: `UsuarioRespuesta` publica `sede_id` (asignación vigente o su ausencia) y `activo` (estado local en `mapa_usuario_esquema.activo`, con la lógica en `usuario_service.listar_usuarios`, no en el router); el listado resuelve el **tenant** (`get_db_negocio`) para la sede y la sesión de **control** (`get_db`) para el mapa, en una sola consulta por lote. Frontend: `Usuario.sede_id`/`activo` documentados como publicados por el listado (el `sede_id` era ya `nullable`; `activo` pasa a `boolean | null` por la respuesta de alta/edición), la vista muestra el estado real activo/inactivo y la sede o su ausencia sin "Estado no informado". Tests nuevos: SQLite `test_listado_usuarios_publica_estado_y_sede` y `test_listado_usuarios_refleja_el_mapa_inactivo` (`test_organizacion_crud_012.py`); gated PostgreSQL `test_listado_usuarios_publica_estado_y_sede_desde_el_tenant` (`test_gestion_administrativa_http_postgres_012.py`); Angular `usuarios.component.spec.ts` sustituye el caso "no informado" por la verificación del estado real. **Resultados:** `pytest` SQLite **839 passed / 59 skipped / 0 failed**; gated `POSTGRES_TEST_URL` **898 passed / 0 failed / 0 skipped**; `ng test` **286 SUCCESS / 0 failed**; `ng build` **limpio**. `/openapi.json`: 44 operaciones de la matriz (+ `/` y `/health` de infraestructura) con `response_model`, código de éxito, 401/403 y `security`; las **28 previas sin cambios** (las 16 nuevas son aditivas; `git diff` de `permisos.py` solo añade). `UsuarioRespuesta` conserva su nombre en el contrato, así que las pruebas de contrato previas siguen verdes.

## Checks de cierre

- [x] **T13 — Recorrer flujo real en 4200 con escritura PostgreSQL.**
  - Levantar backend/frontend dev; verificar Superadmin control (dashboard, alta/edición, desactivar/reactivar, capacidades), luego Admin institucional sedes/departamentos/usuarios/encargados, aislamiento y gating apagado/encendido; verificar datos persistidos y APIs directas.
  - **AC:** AC-1…AC-14.
  - **Hecho cuando:** recorrido completo confirma escritura real, 401/403/404/409 esperados, restauración al reactivar y cada AC queda asociado a evidencia concreta.
  - **Entregado:** recorrido en **4200** contra PostgreSQL real (`apt_erp` migrada a **012.1**; respaldo previo). Sesiones Clerk `+clerk_test`. Evidencia y detalle por AC en `evidencia/README.md` y capturas `evidencia/01…18` (no se generó `11-*.png`: se perdió por timeout en T13 y su contenido quedó acreditado por la verificación SQL y la captura `12`). **Superadmin** (`/control/dashboard`): dashboard SaaS 4 activas con atribución (AC-4); edición de INST-004 persistida en control y espejo de 2 columnas (AC-1); desactivar/reactivar INST-002 con datos intactos (AC-2); 6 capacidades, `kanban` apagada→re-habilitada (AC-5); `/tickets` directo → `/acceso-denegado` sin enlace en nav (AC-3). **Administrador** (`/administracion`): sede crear/editar/desactivar/reactivar y **409** con motivo (AC-6/AC-11); departamento crear/asignar-sede/estado y **409** (AC-7/AC-11); usuarios lista/editar/activar (escritura en `mapa_usuario_esquema.activo`) y **Bodeguero+sede** (AC-8/AC-9); encargados asociar/retirar (AC-10); `/tickets` accesible (AC-3). **API directa (token INST-002):** kanban apagada → `PATCH /tickets/1/estado` **403** sin mutación, restaurada → **404**; depto/usuario ajenos **404** (AC-12); con INST-002 inactiva `/auth/me`+`/organizacion/sedes`+`/usuarios/` → **401** y **200** tras reactivar (AC-2). **Bug corregido:** `GET /auth/me` resolvía con la sesión de `control` y devolvía 401 a todo usuario de tenant en PostgreSQL (el frontend caía en "Identidad no disponible"); pasa a `get_db_negocio` (`auth.py`), con test de regresión gated `test_auth_me_resuelve_identidad_de_tenant` (rojo sin el fix, verde con él). **Suites (conteos verificados):** SQLite `839 passed / 61 skipped / 0 failed`; gated PostgreSQL completa `900 passed / 0 skipped / 0 failed`. El recorrido posterior verificó la redirección inicial a `/control/dashboard`, el sidebar único y la acción `Nueva institución` dentro de `/control/instituciones`.
  - **Corrección post-T13 (verificada):** el hallazgo `POST /usuarios/` usaba sesión de control y devolvía **403** a un Admin de tenant en PostgreSQL. Corregido usando `get_db_negocio` (tenant) + `get_db` (control): `backend/app/api/v1/endpoints/usuarios.py` (`crear_usuario`) y `usuario_service.crear_usuario` (valida y crea en el tenant, registra el mapa en control). Regresión gated `test_gestion_administrativa_http_postgres_012.py::test_alta_usuario_por_admin_de_tenant_persiste_en_su_esquema`; frontend `AdministracionService.crearUsuario` + formulario de alta en `usuarios.component.ts` con casos AC-8/AC-9 en `usuarios.component.spec.ts`. No toca la matriz de permisos ni la semántica de gating. Detalle en `diseno-tecnico.md` §2. **Suites de la corrección post-T13:** `ng test` **292 SUCCESS / 0 failed**; `ng build` **limpio**; gated PostgreSQL del archivo 012 verde.

- [x] **T14 — Reconstruir y recorrer humo en 8080.**
  - Ejecutar `docker compose -f docker-compose.yml build frontend` y luego `docker compose -f docker-compose.yml up -d frontend`; verificar imagen nueva, rutas Angular `/control` y `/administracion`, guard `/tickets`, render y flujo básico sin errores.
  - **AC:** AC-3, AC-4…AC-10, AC-14.
  - **Hecho cuando:** 8080 sirve el build recién reconstruido y el humo confirma vistas/rutas nuevas y guard; no se atribuye evidencia a imagen anterior.
  - **Entregado:** imagen del frontend **reconstruida** (`docker compose -f docker-compose.yml build frontend` + `up -d frontend`), bundle nuevo `main-GAEBNACE.js` (anterior `main-FFSH226A.js`) servido por nginx en 8080. **Superadmin:** navegación sin enlace `Tickets / Kanban` (presentes Dashboard, Inventario, Administración y Control de instituciones); `/control/dashboard` renderiza el Dashboard SaaS con KPI de 4 instituciones activas y atribución por institución (estado, sedes y usuarios por rol) —`evidencia/8080-05-control-dashboard.png`—; navegación directa a `/tickets` → redirección a `/acceso-denegado` (guard OK). **Administrador INST-002:** `/administracion` con las 4 vistas renderizando (sedes, departamentos, usuarios, encargados) —`evidencia/8080-01-admin-sedes.png` a `evidencia/8080-04-admin-encargados.png`—; `/tickets` visible en su navegación; sede "Sede QA 012 Editada" persistida desde el recorrido T13 visible en el listado. Humo de 8080 **verificado** (AC-3, AC-4…AC-10, AC-14).


- [x] **T15 — Registrar evidencia por AC y realizar coherencia documental.**
  - Archivos: `spec.md` solo para anotar evidencias observadas, `MEMORY.md`, `AGENTS.md`/`.agents/skills/` solo mediante grep de comprobación; `roadmap.md` solo si procede tras cierre.
  - Registrar evidencia específica en los 14 AC; actualizar MEMORY (estado, decisiones/razones y errores evitables, breve); grep de rutas/afirmaciones obsoletas según AGENTS §8.7.
  - **AC:** AC-14.
  - **Hecho cuando:** cada AC tiene test/consulta/OpenAPI/recorrido verificable, memoria actualizada y grep no deja contradicciones sin reportar.
  - **Entregado:** `spec.md` §6 con una viñeta **Evidencia** bajo cada AC-1…AC-14 (archivos y métodos de test reales, contrato OpenAPI, y recorrido 4200/8080 con su captura), incluyendo las notas explícitas donde no hay test dedicado (AC-1 sincronización del espejo solo por recorrido; AC-10 sin test backend nuevo porque la API es de la 011). `MEMORY.md` reescrito (≤ ~50 líneas): estado de la 012 en verificación/casi cerrada con suites finales, bloque nuevo "Feature 012 — decisiones clave" (`control.institucion.activo`; `funcion_institucion` 6 capacidades + gating 403 adicional; espejo tenant de 2 columnas; `activo` en sede/departamento; Superadmin fuera de `/tickets` solo por UI; alta de usuario con sesión tenant+control) y errores evitables de la 012 (`/auth/me` y `POST /usuarios/` con sesión de control en PostgreSQL; espejo 011.1 de 4 columnas; harness cross-`MetaData` con `flush`; Karma con Edge `CHROME_BIN`). **Grep de coherencia (AGENTS §8.7):** `AGENTS.md` §4 cita la lista de features del frontend como "(dashboard, inventario, tickets)" sin `control` ni `administracion` (obsolescencia heredada de la 010, no corregida por estar fuera del alcance de escritura de T15); `stack.md` conserva 6 menciones de "12 entidades" históricas (justificaciones 008/010) explícitamente superadas por la sección 011 (14 de dominio) y el comentario del árbol §1; `.agents/skills/*` coherentes (la frase "12 entidades base; desde la 011, 14 de dominio + `departamento_encargado`" ya es la correcta). Solo documentación; sin cambios de código.

- [x] **T16 — Confirmar cierre SDD y actualizar roadmap solo si todos los checks están satisfechos.**
  - Revisar todas las casillas, `pytest` SQLite y gated PostgreSQL, `ng test`, `ng build`, OpenAPI, evidencia por AC y recorridos 4200/8080; marcar roadmap `[x]` solo tras cumplir AGENTS §8.5–§8.7.
  - **AC:** AC-14.
  - **Hecho cuando:** no quedan tareas pendientes, todas las evidencias existen y el estado de roadmap refleja el resultado verificado, nunca la mera implementación.
    - **Entregado:** T1–T15 en `[x]`; reviewer emitió **APROBADO** (14 AC cumplen; SQLite 839/61/0, gated 900/0/0, `ng test` 292 SUCCESS, `ng build` limpio; matriz 44 con las 28 previas intactas; migración 012.1 aplicada). Cierre aplicado: `roadmap.md` fila 012 → `[x]` con resumen y "Siguiente feature" actualizado; `spec.md` estado → **Cerrada (18/Oct/2026)** y AC-6 corregido a 10 casos; capturas 01–18 con la excepción de `11` documentada en `spec.md`, T13 y `evidencia/README.md`; `AGENTS.md` §4 con la lista real de `features/` (añade `control`, `administracion`, `auth`, `acceso-denegado`); `stack.md` con nota de que las menciones a "12 entidades" de las justificaciones 008/010 son históricas; `MEMORY.md` con la 012 cerrada. Sin cambios de código ni ejecución de suites (ya verificadas).

## Correcciones UX posteriores al cierre

- [x] **UX-1 — Entrada inicial y navegación simplificada del Superadmin.**
  - Archivos: `frontend/src/app/core/guards/inicio.guard.ts`, `frontend/src/app/app.routes.ts`, `frontend/src/app/features/auth/login.component.ts`, `frontend/src/app/app.component.html`, `frontend/src/app/features/control/` y sus pruebas/documentación.
  - La raíz y el login sin retorno llevan al Superadmin a `/control/dashboard`; los roles institucionales conservan `/dashboard`. El sidebar global separa Dashboard SaaS e Instituciones, se retira la barra interna duplicada y la vista de instituciones conserva solo `Nueva institución` como acción contextual hacia `/control/alta`.
  - **Verificación:** `ng build` limpio; suite frontend `549 SUCCESS`; imagen frontend Docker reconstruida y contenedor `8080` recreado. El botón contextual requiere `RouterLink` explícito en `InstitucionesComponent`.

## Enmienda T-17 — pestañas ARIA en administración (22/Oct/2026)

> Enmienda aprobada sobre la Feature 012 ya cerrada; ejecutar en el orden indicado. No modificar `spec.md`, rutas, guards, backend ni contratos. El patrón sigue el precedente T17 de Feature 014, adaptado a navegación Router-based con anchors reales.

- [x] **E17-1 — Pruebas rojas para estado de ruta, ARIA y panel.**
  - **Archivos:** crear `frontend/src/app/features/administracion/administracion-nav.component.spec.ts` e incluir el layout real; crear un spec separado del layout solo si el harness impide probar nav+panel en el mismo fixture.
  - Configurar navegación real a `/administracion/sedes`, `/administracion/departamentos`, `/administracion/usuarios` y `/administracion/encargados`; cubrir tablist y cuatro anchors-tab, una sola pestaña seleccionada/tabbable, IDs estables, href auténtico y `tabpanel` cuyo `aria-labelledby` apunta al ID activo.
  - **AC:** AC-15, AC-17, AC-18, AC-19.
  - **Hecho cuando:** los casos nuevos fallan contra el marcado/estado actual por carecer de la semántica aprobada, y las pruebas vigentes continúan ejecutables; no cambiar `administracion.routes.ts`.
  - **Comando:** `cd frontend; $env:CHROME_BIN = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"; npx ng test --watch=false --browsers=ChromeHeadless` (no usar `npm test`).

- [x] **E17-2 — Pruebas rojas de flechas y navegación nativa.**
  - **Archivos:** ampliar `administracion-nav.component.spec.ts`.
  - Probar ArrowRight/ArrowLeft desde cada extremo con wraparound, que foco y ruta activa terminan en la sección destino, que la tecla atendida previene el scroll y que otras teclas no son interceptadas. Afirmar que los elementos son anchors con `href` a las rutas hijas y no botones, sin simular apertura de pestaña desde JS.
  - **AC:** AC-16, AC-18, AC-19.
  - **Hecho cuando:** las pruebas de teclado fallan antes de implementar el manejador y especifican de forma verificable selección, foco y navegación circular sobre cuatro destinos.
  - **Comando:** `cd frontend; $env:CHROME_BIN = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"; npx ng test --watch=false --browsers=ChromeHeadless` (no usar `npm test`).
  - **Entregado:** 10 casos nuevos en `administracion-nav.component.spec.ts` bajo `describe('AC-16: flechas con recorrido circular sobre los cuatro destinos')` más un caso de coherencia (sección «Teclado y navegación nativa»): 8 casos `ArrowRight`/`ArrowLeft` desde cada uno de los cuatro orígenes (incluye wraparound Encargados→Sedes y Sedes→Encargados) que afirman `defaultPrevented` de la tecla, `router.url` igual al destino, `document.activeElement` igual al anchor destino y que el destino es `<a>` con `href` a su ruta hija; 1 caso de no interceptación (`Enter`, `Tab`, `a`: `defaultPrevented` false, ruta y foco intactos); 1 caso de coherencia tras `ArrowRight` (ruta, `aria-selected`/`tabindex` roving, `tabpanel` con `aria-labelledby` del destino, `window.open` no invocado y ausencia de `target` en los cuatro anchors, sin simular apertura de pestaña). Los anchors se localizan por `href` dentro de la barra (no por `role="tab"`) para que el rojo mida comportamiento y no marcado; el `keydown` se dispara en el DOM real sobre el anchor enfocado (`new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true })`) y se espera `harness.fixture.whenStable()` + `detectChanges()` para observar la navegación asíncrona del `routerLink`. **Resultado:** `ng test` **466 ejecutados: 447 SUCCESS / 19 FAILED**; los 19 rojos son los 10 de E17-1 y 9 de los 10 nuevos (los 8 de flechas fallan con «Expected false to be true» en `defaultPrevented`, ruta sin cambiar y foco que no se mueve; el de coherencia arrastra esos tres). El caso de «otras teclas no interceptadas» nace verde por diseño (propiedad negativa: sin manejador no hay interceptación) y queda como trinquete frente a un manejador demasiado amplio en E17-3. Sin cambios en `administracion-nav.component.*`, `administracion.routes.ts`, backend ni inventario.

- [x] **E17-3 — Implementar la navegación accesible sin tocar rutas.**
  - **Archivos:** modificar `administracion-nav.component.ts`, `administracion-nav.component.html` y `administracion.component.html`.
  - Derivar ruta/índice activo de `Router.url` (sin query/fragmento, comparación por segmento), con fallback visual a Sedes solo para URL transitoria no coincidente; enlazar atributos `aria-selected`, `tabindex` y `aria-labelledby` a IDs estables. Mantener `[routerLink]`, manejar ArrowLeft/ArrowRight circularmente en el orden de `enlaces`, enfocar el anchor destino y conservar comportamiento nativo de enlace. Aplicar clases Tailwind de pestaña con borde inferior azul/texto azul activo y foco visible `ring`; replicar localmente el patrón, sin extraer componente ni editar Inventario.
  - **AC:** AC-15, AC-16, AC-17, AC-18.
  - **Hecho cuando:** los tests de E17-1/E17-2 pasan; cada URL muestra la pestaña y panel emparejados; `administracion.routes.ts` y sus cuatro destinos siguen idénticos.
  - **Comando:** `cd frontend; $env:CHROME_BIN = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"; npx ng test --watch=false --browsers=ChromeHeadless` y `npx ng build`.
  - **Entregado:** `administracion-nav.component.ts` expone `ENLACES_ADMINISTRACION`, `resolverEnlaceActivo(url)` (quita query/fragmento y compara exacto o prefijo seguido de `/`, con fallback visual a sedes) y `urlActivaDelRouter(router)` (señal alimentada por `NavigationEnd` sobre `Router.url`, que cubre deep links y atrás/adelante con `OnPush`). La barra la consume para `aria-selected`/`tabindex` roving e IDs `pestana-administracion-*`; `alNavegarPestanas` atiende solo `ArrowRight`/`ArrowLeft`, previene el default únicamente en ellas, calcula el índice circular sobre el enlace enfocado (con el activo como respaldo), enfoca el anchor destino y lo activa con `click()` para que navegue su propio `RouterLink` (sin `navigateByUrl`, sin botones, sin `window.open`). `AdministracionComponent` reutiliza la misma resolución para componer `role="tabpanel"` (`id="panel-administracion"`) con `aria-labelledby` de la sección vigente, envolviendo el `<router-outlet>` intacto. Clases de pestaña copiadas del patrón de inventario (borde inferior 2 px, `border-blue-600 text-blue-700` activo, `border-transparent text-slate-600` inactivo, `hover:text-blue-700`, `focus-visible:ring-2 ring-blue-500 ring-offset-2`), solo Tailwind. **Resultado:** `ng test` **466 ejecutados: 466 SUCCESS** (20 de la enmienda a verde, 446 heredados intactos); `ng build` limpio (329.56 kB inicial, 25.9 s); `git diff` vacío para `administracion.routes.ts` y `administracion.routes.spec.ts`. Sin cambios en vistas hijas, inventario ni backend.

- [x] **E17-4 — Regresión, build y evidencia de recorridos.**
  - **Archivos:** únicamente adaptar expectativas existentes si se demuestra que dependen del marcado sustituido; registrar evidencia en `spec.md` §6 solo después de observarla (no cambiar texto normativo ni la spec en esta planificación); conservar intactos los tests de las vistas hijas salvo ajuste justificado.
  - Ejecutar suite frontend completa y build de producción; recorrer visual y con teclado las cuatro rutas en 4200, incluyendo navegación con flechas circular y enlaces profundos; después reconstruir y comprobar humo en 8080. Sin pruebas backend: el cambio es exclusivamente frontend.
  - **AC:** AC-18, AC-19.
  - **Hecho cuando:** regresión de `sedes`, `departamentos`, `usuarios`, `encargados` y `administracion.routes` verde, `ng test` y `ng build` pasan, las evidencias de 4200/8080 confirman presentación y navegación, y la imagen 8080 es la recién reconstruida.
  - **Comandos:** `cd frontend; $env:CHROME_BIN = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"; npx ng test --watch=false --browsers=ChromeHeadless; npx ng build`; desde la raíz: `docker compose -f docker-compose.yml build frontend` y `docker compose -f docker-compose.yml up -d frontend`. Nunca usar `npm test`.
  - **Entregado:** `ng test` **466 ejecutados: 466 SUCCESS / 0 FAILED**; `ng build` limpio (329.56 kB inicial, 29.3 s) con bundle `main-KWQKKL6Q.js`. **Ninguna expectativa heredada adaptada:** `git diff --stat` de los specs de `sedes`, `departamentos`, `usuarios`, `encargados` y `administracion.routes` está vacío (los cuatro specs no asertan el marcado de la barra). Recorrido en **4200** con sesión Administrador (`admin017.test+clerk_test`): deep links de las cuatro rutas con `tablist`/4 `aria-tab`/una sola `aria-selected` y `tabpanel` con `aria-labelledby` de la ruta vigente; `/administracion` redirige a `sedes` con la pestaña correcta; clic navega; `ArrowRight`/`ArrowLeft` recorren circularmente (Encargados→Sedes y Sedes→Encargados) dejando foco, ruta, selección y panel alineados; activo azul con borde inferior y foco en anillo, sin resaltado oscuro; consola sin errores (solo el aviso preexistente de claves dev de Clerk). **8080** reconstruido (`build frontend` + `up -d`, contenedor recreado `healthy`): sirve `main-KWQKKL6Q.js` (antes `main-D6GKPODP.js`), las cuatro rutas responden **200** y pintan el tablist, y `ArrowRight` navega igual. Evidencia en `evidencia/README.md` §«Enmienda T-17» y capturas `19`–`28`. Sin pruebas backend (cambio exclusivamente frontend) y sin tocar `spec.md`.

### Cierre de enmienda T-17

- [x] **E17-C1 — Tests y build verificados.**
  - **AC:** AC-19.
  - **Hecho cuando:** `ng test` con `CHROME_BIN` a Edge y `--watch=false --browsers=ChromeHeadless` pasa con suite completa y `npx ng build` termina limpio; se anota el resultado observado. No ejecutar `npm test`.
  - **Entregado (22/Oct/2026):** `ng test` **466 ejecutados: 466 SUCCESS / 0 FAILED** (Edge 155, 12.4 s; los 20 casos de la enmienda incluidos); `npx ng build` **limpio** (`Application bundle generation complete`, 33.5 s, inicial **329.56 kB** / 91.66 kB transferido) con bundle `main-KWQKKL6Q.js`. Sin cambios de código.

- [x] **E17-C2 — Recorrido funcional visual y teclado en 4200.**
  - **AC:** AC-15…AC-19.
  - **Hecho cuando:** en el dev server 4200 se visitan directamente y por navegación las cuatro rutas; se comprueban estado activo, semántica/panel asociados, foco, ArrowLeft/ArrowRight y wraparound, y se confirma que el anchor conserva su destino y la vista hija/guard no cambia; evidencia/capturas quedan enlazadas en `spec.md` §6 con resultados observados.
  - **Entregado (22/Oct/2026):** se **valida la evidencia existente de E17-4** (`evidencia/README.md` §«Enmienda T-17», capturas `19`–`24`: deep links de las cuatro rutas con tablist/4 tabs/una sola `aria-selected`/panel enlazado, `/administracion`→`sedes`, clic, `ArrowRight`/`ArrowLeft` con wraparound, presentación azul y consola sin errores), sin repetir el recorrido: no había nada dudoso que re-comprobar. Re-verificación ligera en el dev server vivo: las cuatro rutas `/administracion/{sedes,departamentos,usuarios,encargados}` responden **200**. Sin cambios de código.

- [x] **E17-C3 — Build de producción y humo en 8080.**
  - **AC:** AC-19.
  - **Hecho cuando:** tras `docker compose -f docker-compose.yml build frontend` y `docker compose -f docker-compose.yml up -d frontend`, 8080 sirve el bundle nuevo y el humo confirma el tablist, cuatro rutas/paneles y navegación básica; evidencia del bundle/capturas queda documentada. No atribuir a la imagen anterior.
  - **Entregado (22/Oct/2026):** el contenedor `compustock_frontend` sigue `healthy` y **8080 sirve `main-KWQKKL6Q.js`** (no `main-D6GKPODP.js`), el mismo bundle que produce el build de C1, por lo que la imagen reconstruida en E17-4 es la vigente y **no se reconstruyó de nuevo**. Humo ya documentado en `evidencia/README.md` §«Enmienda T-17» (capturas `25`–`28`: deep links 200, tablist, cuatro paneles y `ArrowRight` operativo). Sin cambios de código.

- [x] **E17-C4 — Evidencia y coherencia de cierre sin reabrir la Feature 012.**
  - **AC:** AC-18, AC-19.
  - No tocar `spec.md` durante la planificación; al ejecutar la enmienda, el usuario/coordinador deberá incorporar bajo AC-15…AC-19 evidencia real de tests/build/4200/8080. Actualizar `MEMORY.md` conforme a AGENTS §10 y hacer grep de coherencia sobre `AGENTS.md`, `MEMORY.md` y `.agents/skills/`; no modificar roadmap ni cambiar el estado de cierre de la Feature 012 por esta presentación.
  - **Hecho cuando:** cada AC de la enmienda tiene evidencia verificable, `MEMORY.md` refleja la presentación y sus decisiones sin datos sensibles, el grep no encuentra rutas/afirmaciones obsoletas (o los hallazgos quedan reportados), y queda explícito que Feature 012 conserva su cierre original.
  - **Entregado (22/Oct/2026):** `spec.md` §«Enmienda T-17» con una línea *Evidencia* bajo **AC-15…AC-19** (nombres reales de los casos de `administracion-nav.component.spec.ts`, suite 466, build `main-KWQKKL6Q.js`, recorrido 4200 y humo 8080 con capturas `19`–`28`); texto normativo y numeración de los AC **sin cambios**. `MEMORY.md` con la enmienda (fecha, alcance, suites, bundle, evidencia) y la decisión «pestañas ARIA sobre Router» (43 líneas, sin datos sensibles). **Grep de coherencia (§8.7):** sin afirmaciones obsoletas — `AGENTS.md`/`MEMORY.md`/`.agents/skills/` no describen la navegación de administración como «barra de enlaces» ni citan `routerLinkActive`; `AGENTS.md` §4 ya lista `administracion` y `control`. Roadmap y estado **«Cerrada (18/Oct/2026)»** de la 012 intactos.

### Matriz de trazabilidad AC ↔ tareas (enmienda)

| AC | Tareas |
|---|---|
| AC-15 | E17-1, E17-3, E17-C2 |
| AC-16 | E17-2, E17-3, E17-C2 |
| AC-17 | E17-1, E17-3, E17-C2 |
| AC-18 | E17-1, E17-2, E17-3, E17-4, E17-C2, E17-C4 |
| AC-19 | E17-1, E17-2, E17-4, E17-C1, E17-C2, E17-C3, E17-C4 |

## Enmienda funcional posterior al cierre (27/Nov/2026) — campos por rol y retiro de encargados

> Spec aprobada: `spec.md`, «Enmienda funcional posterior al cierre (27/Nov/2026)» y «Segundo
> bloque de la enmienda (27/Nov/2026)». AC-20…AC-41. **Enmienda cerrada y verificada
> (27/Nov/2026):** las tareas E12-B*, E12-A* y E12-C* quedan `[x]`; no se crea Feature 028 y la
> Feature 012 conserva su cierre. Las tareas de esta sección se ejecutaron en orden: **B → A → C**.
>
> **Histórico supersedido (no reabrir):** las tareas T7, T8, T10, T12–T16 y E17-1…E17-C4 que
> mencionan encargados o 4 pestañas se conservan como registro y quedan
> **históricas/supersedidas** por esta enmienda; no se borran ni se cambian sus `[x]`.

### Histórico supersedido

| Tarea original | Estado | Motivo |
|---|---|---|
| T7, T8 | Histórica/supersedida | CRUD y pruebas de encargados; la tabla y sus 3 rutas se retiran. |
| T10 | Histórica/supersedida | Vista de encargados; queda el frontend de 3 pestañas (E12-B2). |
| T12–T16 | Histórica/supersedida | Conteos, evidencias y cierre previos a la enmienda; se reemplazan por E12-C1…C3. |
| E17-1…E17-C4 | Histórica/supersedida | Navegación de 4 pestañas; la vigente es de 3 (AC-38). |

### Bloque B — retiro de encargados

- [x] **E12-B1 — Retiro estructural de `departamento_encargado` (DDL, semilla, token, backend y pruebas).**
  - **Archivos:** `database/01_esquema.sql`, `database/02_datos_semilla.sql`,
    `backend/app/core/config.py`; `backend/app/models/organizacion.py`,
    `backend/app/models/__init__.py`; `backend/app/schemas/organizacion_schema.py`;
    `backend/app/services/organizacion_service.py`;
    `backend/app/api/v1/endpoints/organizacion.py`, `backend/app/api/v1/api.py`,
    `backend/app/api/v1/endpoints/usuarios.py`; `backend/app/core/permisos.py`,
    `backend/app/core/capacidades.py`; pruebas inventariadas en `spec.md` §10.3
    (`test_modelo_sede_011.py`, `test_organizacion_011.py`, `test_organizacion_crud_012.py`,
    `test_permisos_endpoints.py`, `test_permisos_012.py`, `test_permisos_010.py`,
    `test_permisos_008.py`, `test_permisos.py`, `test_capacidades_gating_012.py`,
    `_soporte_sede_011.py`,
    `test_instalacion_limpia_postgres.py`, `test_control_postgres_010.py`,
    `test_dashboard_tecnico_postgres_017.py`, `test_ciclo_vida_catalogo_postgres_014.py`,
    `test_gobierno_identidades_017.py`, `test_salud_esquema_postgres_026.py`,
    `test_catalogo_retiro_postgres_013.py`, `test_cobertura_postgres_021.py`,
    `test_validacion_entradas_postgres_027.py`, `test_metricas_024.py`,
    `test_correlacion_024.py`, `test_permisos_retiro_013.py`, `test_contrato_024.py`,
    `test_ciclo_vida_autorizacion_014.py`, `test_ciclo_vida_aprobacion_013.py`,
    `test_ciclo_vida_confirmacion_013.py`, `test_alta_solo_solicitante_007.py`,
    `test_cobertura_021.py`, `test_compras_endpoints_020.py`, `test_detalle_producto_019.py`,
    `test_filtros_inventario_018.py`).
  - **Sub-pasos:** (1) retirar la tabla de `control` y del template tenant y ajustar el
    check/comentario 23→22; (2) retirar las 5 filas, listas, secuencia, copia, `DELETE` y
    token `026.0→026.1` de la semilla; (3) `VERSION_ESQUEMA_OBJETIVO="026.1"` y el comentario
    de versión de `01_esquema.sql`; (4) retirar
    modelo, `__init__`, DTO, servicios, 3 rutas, comentarios de `api.py`/`usuarios.py`,
    3 entradas de matriz y 3 mapeos de capacidad; (5) quitar `_dependencias_usuario` y su 409
    conservando las demás dependencias; (6) actualizar/eliminar las pruebas y los conteos
    75/77→72/74 y 26/23→25/22; (7) `down -v` + `up -d` y verificar 25/22/`026.1`.
  - **AC:** AC-33, AC-34, AC-35, AC-36, AC-37, AC-39.
  - **Hecho cuando:** `pytest` SQLite y gated PostgreSQL quedan verdes; el reset deja 25/22,
    sin `departamento_encargado` ni sus 5 filas, `026.1` en control y tenants; la matriz queda
    en 72 v1, OpenAPI en 74 totales (72 v1 + `GET /` + `/health`) y las 3 rutas no se publican;
    `gestion_organizacional` conserva sedes/departamentos/usuarios; la baja de usuario ya no
    responde 409 por encargado.
  - **Comandos:** `cd backend && pytest`; gated con `POSTGRES_TEST_URL`; desde la raíz
    `docker compose -f docker-compose.yml down -v` y `up -d`.
  - **Evidencia esperada:** conteos 25/22, `026.1`, ausencia de tabla/secuencia, 72/74,
    tests de permisos/capacidad/baja y reset limpio.
  - **Entregado (27/Nov/2026):** tabla puente retirada de punta a punta. **DDL:** `01_esquema.sql`
    ya no crea `control.departamento_encargado` ni su template tenant; cabecera y comentarios a
    **25/22**, check fail-closed y `RAISE NOTICE` a **22** y token de versión a **`026.1`**.
    **Semilla:** sin las 5 asociaciones, sin lista/`setval`/copia/`DELETE` de la tabla,
    `v_version_objetivo = '026.1'`. **Backend:** `config.VERSION_ESQUEMA_OBJETIVO = "026.1"`;
    eliminados `models/organizacion.py` (`DepartamentoEncargado`), su import/`__all__`, los DTO
    `EncargadoCrear`/`EncargadoRespuesta`, `_consulta_encargados`/`listar_encargados`/
    `asociar_encargado`/`retirar_encargado`, `_dependencias_usuario` y su 409 (queda el 409 del
    último Administrador activo), las 3 rutas de `endpoints/organizacion.py`, sus entradas de
    `permisos.py` y `capacidades.py` y los comentarios de `api.py`/`usuarios.py`/`control_service.py`;
    `gestion_organizacional` conserva sedes, departamentos y usuarios. **Pruebas:** se eliminaron
    los 9 casos de la relación N:N (`test_organizacion_011.py`), los 2 de metadata
    (`test_modelo_sede_011.py`) y el 409 por encargado (`test_organizacion_crud_012.py`, sustituido
    por la baja 200 de AC-37); se actualizaron transcripciones y conteos en `test_permisos*.py`,
    `test_capacidades_gating_012.py`, `_soporte_sede_011.py`, `test_contrato_024.py`,
    `test_permisos_retiro_013.py`, `test_ciclo_vida_*013/014.py`, `test_alta_solo_solicitante_007.py`,
    `test_cobertura_021.py`, `test_compras_endpoints_020.py`, `test_detalle_producto_019.py`,
    `test_filtros_inventario_018.py`, `test_correlacion_024.py`, `test_metricas_024.py` y los gated
    `test_instalacion_limpia_postgres.py`, `test_control_postgres_010.py`,
    `test_dashboard_tecnico_postgres_017.py`, `test_ciclo_vida_catalogo_postgres_014.py`,
    `test_gobierno_identidades_017.py`, `test_salud_esquema_postgres_026.py`,
    `test_catalogo_retiro_postgres_013.py`, `test_cobertura_postgres_021.py` y
    `test_validacion_entradas_postgres_027.py`. **Reset** (`down -v` + `up -d`): `control` **25**
    tablas, cada tenant **22**, `to_regclass('control.departamento_encargado')` nulo, 0 relaciones
    ni secuencias con ese nombre, sin las 5 filas y `version_esquema = 026.1` en control y en los
    cuatro tenants; la guardia fail-closed sigue abortando la segunda semilla (gated). **Contrato:**
    matriz **72**, `/openapi.json` **74** = 72 v1 + `GET /` + `/health`; las 3 rutas responden 404 y
    no aparecen en `/openapi.json`; `gestion_organizacional` intacta. **Suites:** `pytest` SQLite
    **2080 passed / 123 skipped**; gated PostgreSQL **2200 passed / 3 skipped** (los 3 de Redis sin
    `REDIS_TEST_URL`); `ng test` **658 SUCCESS / 0 failed**; `npx ng build` limpio. **Grep:** sin
    `DepartamentoEncargado`, `departamento_encargado`, `/encargados` ni «encargado» en
    `backend/app`, `backend/tests` ni `database/`; `frontend/src` conserva las referencias y su
    vista, que son de **E12-B2** (no se tocó el frontend). Sin cambios en `database/README.md`,
    `MEMORY.md`, `AGENTS.md`, skills, diagramas ni informe (D-20/cierre).

- [x] **E12-B2 — Retiro del frontend de encargados y navegación de 3 pestañas.**
  - **Archivos:** eliminar
    `frontend/src/app/features/administracion/encargados.component.ts|html|spec.ts`;
    `frontend/src/app/features/administracion/administracion.routes.ts|spec.ts`;
    `frontend/src/app/features/administracion/administracion-nav.component.ts|html|spec.ts`;
    `frontend/src/app/features/administracion/administracion.component.ts|html`;
    `frontend/src/app/features/administracion/services/administracion.service.ts|spec.ts`;
    `frontend/src/app/shared/interfaces/index.ts`;
    `frontend/src/app/features/administracion/usuarios.component.html|spec.ts`;
    `frontend/src/app/features/control/control.routes.ts`;
    `frontend/src/testing/funcional/README.md`; revisar
    `frontend/src/app/core/guards/superficies-retiradas.spec.ts` (sin cambios esperados).
  - **Sub-pasos:** quitar la ruta hija y el enlace; dejar `ENLACES_ADMINISTRACION` con 3;
    ajustar IDs/ARIA y wraparound **Sedes↔Usuarios**; quitar tipos/métodos/casos de
    encargados; quitar el texto del 409 en `usuarios.component.html`; actualizar el índice de
    testing; verificar que `/administracion/encargados` cae en `**` → `/dashboard`; confirmar
    que `superficies-retiradas.spec.ts` no requiere cambios.
  - **AC:** AC-38, AC-39.
  - **Hecho cuando:** `ng test` y `ng build` quedan verdes; hay 3 pestañas (Sedes,
    Departamentos, Usuarios), deep links y `tabpanel` con `aria-labelledby`; no quedan
    componente, ruta, tipos, métodos ni textos de encargados; el wraparound y los IDs son de 3.
  - **Comandos:** `cd frontend; $env:CHROME_BIN="C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe";
    npx ng test --watch=false --browsers=ChromeHeadless; npx ng build`. Nunca `npm test`.
  - **Evidencia esperada:** specs de nav/routes/usuarios/service verdes, 3 pestañas en 4200 y
    `/administracion/encargados` sin vista.
  - **Entregado (27/Nov/2026):** retiro del frontend de encargados y navegación de **3 pestañas**.
    **Eliminados:** `encargados.component.ts|html|spec.ts`. **Rutas:** `administracion.routes.ts`
    publica solo `sedes`, `departamentos` y `usuarios` (3 hijas por `loadComponent`) y su spec
    espera esas 3. **Navegación:** `ENLACES_ADMINISTRACION` queda con 3 entradas e IDs
    `pestana-administracion-sedes|departamentos|usuarios`; `administracion-nav.component.html`
    no necesitó cambios (itera `enlaces`) y conserva `role="tablist"`, `aria-selected`/`tabindex`
    roving y `tabpanel` con `aria-labelledby` de la sección activa; el wraparound es
    **Sedes↔Usuarios**. Spec de nav: `PESTANAS` de 3, sin mock `listarEncargados`, conteos 3/2,
    hrefs/IDs/textos de 3 y flechas circulares sobre 3 destinos (16 casos: 3×[AC-15 + AC-17 +
    2 flechas] + 4 transversales). **Servicio/tipos:** fuera `listarEncargados`,
    `asociarEncargado`, `retirarEncargado` y sus 3 casos; fuera `Encargado`/`EncargadoCrear` de
    `shared/interfaces/index.ts`. **Textos:** `usuarios.component.html` ya no anuncia el 409 por
    encargado (solo «¿Reactivar…?»/«¿Desactivar…?»); su caso de 409 se **reescribió** al 409
    vigente del último Administrador activo (plan §4 «quitar/reescribir»), conservando la baja
    genérica; `administracion.component.ts|html` y el comentario de `control.routes.ts` ya no
    citan encargados; `testing/funcional/README.md` sin la fila del spec retirado.
    **Wildcard:** no se añadió ninguna ruta; `app.routes.ts` conserva
    `{ path: '**', redirectTo: 'dashboard' }` y, al no existir hija, `/administracion/encargados`
    cae en él (sujeto a autenticación); `superficies-retiradas.spec.ts` no requería cambios.
    **Suites:** `ng test` **645 SUCCESS / 0 failed** (658 − 6 del spec de encargados − 3 del
    servicio − 4 de la cuarta pestaña; 44 specs); `npx ng build` limpio (inicial **339.74 kB**,
    `main-SUOO4M4P.js`, 28.8 s; sin chunk de encargados); `pytest` SQLite **2080 passed /
    123 skipped** sin tocar backend. **Grep:** 0 coincidencias de `encargado` (cualquier caja) y
    `/administracion/encargados` en `frontend/src` ni en el resto de `frontend/`, así que no
    quedan falsos positivos del rol ni históricos que distinguir. **Observación:** el índice
    `testing/funcional/README.md` ya declaraba 42 specs/559 casos antes de esta tarea (hoy 44
    specs/645 casos; faltaban en el índice `rut.spec.ts`, `validacion-http.spec.ts` y
    `ticket.service.spec.ts` desde enmiendas previas): deuda documental preexistente, no tocada.

### Bloque A — alta y edición por rol

- [x] **E12-A1 — Contrato y resolución de «Suministros» en el alta.**
  - **Archivos:** `backend/app/schemas/usuario_schema.py`;
    `backend/app/services/departamento_suministros.py` (nuevo helper);
    `backend/app/services/usuario_service.py`; nuevos tests
    `backend/tests/funcional/unitarios/test_departamento_suministros_012.py` y
    `backend/tests/funcional/integracion/test_alta_suministros_012.py` (o ampliación de los
    existentes de usuarios/organización, conservando el mismo nivel de cobertura).
  - **Sub-pasos:** redeclarar `departamento_id` opcional solo en `UsuarioCrear` y
    `UsuarioEdicion` (`ge=1`); helper de búsqueda normalizada/creación/reactivación con
    `begin_nested()` + `IntegrityError` + relectura; en `crear_usuario`, resolver el rol,
    ignorar ids positivos para Bodeguero, exigir/validar departamento para los demás, rechazar
    «Suministros» para no-Bodeguero y conservar el flujo de dos fases de la 017.
  - **AC:** AC-20, AC-21, AC-23, AC-24, AC-25, AC-26, AC-30, AC-31.
  - **Hecho cuando:** `pytest` verde; alta de Bodeguero sin departamento (o con id positivo
    ajeno/inexistente) resuelve «Suministros»; `0`/negativo → 422 para todos; no-Bodeguero sin
    departamento o con «Suministros» → 422; `UsuarioRespuesta` sigue publicando el id real;
    no hay DDL nuevo del Bloque A.
  - **Comandos:** `cd backend && pytest`.
  - **Evidencia esperada:** tests de helper/alta, 201/422, reutilización/reactivación,
    aislamiento y contrato.
  - **Entregado (27/Nov/2026):** contrato, helper y alta por rol.
    **Contrato:** `departamento_id` pasa a `int | None = Field(default=None, ge=1)`
    **solo** en `UsuarioCrear` (sobrescritura) y `UsuarioEdicion`; `UsuarioBase` y
    `UsuarioRespuesta` conservan el campo obligatorio, `UsuarioCrear` mantiene
    `extra="forbid"` y `0`/negativo responde 422 en todos.
    **Helper:** `backend/app/services/departamento_suministros.py` con
    `resolver_departamento_suministros(db, institucion_id)` y el predicado
    `es_departamento_suministros`: búsqueda `lower(trim(nombre_dep)) == 'suministros'`
    por institución, reutilización sin tocar nombre/descripción/sede, reactivación del
    inactivo, alta con la descripción exacta de D-8, `sede_id=NULL` y `activo=True`;
    sin `commit()` (solo `flush()`), de modo que un alta fallida no confirma la fila.
    **Alta:** `crear_usuario` resuelve el rol una vez contra `rol`; el Bodeguero ignora
    cualquier `departamento_id` positivo (propio, ajeno o inexistente) y resuelve
    «Suministros» en la institución del actor/`institucion_id`, con
    `institucion_para_evidencia` derivada del actor; el no-Bodeguero exige el campo
    (422 con detalle claro y sin mutación), conserva las validaciones vigentes de
    ámbito/existencia (403/404) y rechaza «Suministros» (422) **después** del ámbito;
    se mantienen la precedencia 401→403 y el flujo de dos fases de la 017, y el `201`
    publica el `departamento_id` real persistido.
    **Decisión no cubierta por el plan:** el savepoint de creación se abre solo en
    PostgreSQL. En SQLite, pysqlite emite el `SAVEPOINT` como control de transacción
    exterior y su `RELEASE` confirma en el acto, lo que rompería D-8 (la fila no puede
    confirmarse antes que el usuario); SQLite serializa las escrituras y no acredita la
    carrera, así que allí se conserva el pre-check normalizado dentro de la transacción
    del llamador. `begin_nested()` + `IntegrityError` + relectura queda íntegro para
    PostgreSQL y lo acredita E12-A3.
    **Pruebas:** `backend/tests/funcional/unitarios/test_departamento_suministros_012.py`
    (contrato DTO y helper: creación, reutilización, variantes normalizadas,
    reactivación, aislamiento, no-commit y conflicto sin savepoint) y
    `backend/tests/funcional/integracion/test_alta_suministros_012.py` (HTTP: Bodeguero
    sin departamento y con id positivo propio/ajeno/inexistente → 201 y «Suministros»;
    reutilización, variantes, reactivación y dos altas → una fila; no-Bodeguero sin
    departamento o con «Suministros» → 422 sin mutación; departamento ajeno → 403;
    `0`/negativo → 422 para Bodeguero y Solicitante; Administrador 403 sin crear;
    Solicitante 201 sin crear; aislamiento INST01/INST02; fallo antes del commit no
    confirma «Suministros»). Ajuste: `test_rol_asignable_usuarios.py::
    test_administrador_no_crea_usuario_en_departamento_ajeno` usa Solicitante, porque el
    Bodeguero ya no valida el departamento enviado (D-8).
    **Resultados:** `pytest` **2126 passed / 123 skipped / 0 failed** (2080 base + 46
    casos nuevos); `ng test` **645 SUCCESS**; `npx ng build` limpio (inicial **339.74 kB**,
    `main-SUOO4M4P.js`). Sin cambios de frontend, DDL ni semilla; `/openapi.json` refleja
    el campo opcional por el DTO y E12-A3 documenta el 422 por rol. Pendiente de E12-A2:
    el `PUT /usuarios/{id}` que omite `departamento_id` aún responde 404 desde
    `_departamento_en_alcance(None)`; A2 debe convertirlo en 422 por rol y resolver
    «Suministros» en la edición.

- [x] **E12-A2 — Edición por rol, motivo D-5 y legacy.**
  - **Archivos:** `backend/app/services/organizacion_service.py`; tests
    `backend/tests/funcional/integracion/test_edicion_suministros_012.py` (o ampliación de
    `test_organizacion_crud_012.py`) y los de último Administrador existentes.
  - **Sub-pasos:** resolver «Suministros» para Bodeguero; exigir/validar departamento para
    no-Bodeguero y rechazar «Suministros»; calcular `cambio_efectivo` con el departamento
    resuelto; exigir motivo D-5 en el legacy y en los cambios de rol; cambio desde Bodeguero
    solo a Solicitante; no tocar `usuario.sede_id`; conservar el 409 del último Administrador
    y el `PUT .../sede` fuera de motivos.
  - **AC:** AC-27, AC-28, AC-29, AC-30, AC-31.
  - **Hecho cuando:** `pytest` verde; un Bodeguero legacy en «Biblioteca» pasa a
    «Suministros» con motivo; una edición sin cambios una vez en «Suministros» no exige
    motivo; el cambio de rol y los 422 se comportan según la spec; no se consulta encargados.
  - **Comandos:** `cd backend && pytest`.
  - **Evidencia esperada:** tests de edición legacy, cambio de rol, motivo y último
    Administrador.
  - **Entregado (27/Nov/2026):** edición por rol con «Suministros», motivo D-5 y legacy.
    **Servicio:** `organizacion_service.editar_usuario` resuelve el nombre del rol destino
    una sola vez contra `rol` antes de validar el departamento y calcula `cambio_efectivo`
    contra el **departamento resuelto**. Para Bodeguero ignora cualquier `departamento_id`
    positivo (propio, ajeno o inexistente) y resuelve «Suministros» con el helper de E12-A1
    en la institución del usuario/actor (`_institucion_de_mutacion`), sin llamar a
    `_departamento_en_alcance` con el id del cliente; el legacy «Biblioteca» → «Suministros»
    es efectivo y exige motivo, y un Bodeguero ya en «Suministros» sin más cambios no lo
    exige. Para no-Bodeguero, `departamento_id` ausente/null responde **422** claro y sin
    mutación (antes 404), conserva el 403/404 de existencia/ámbito y rechaza «Suministros»
    con **422 después** del ámbito. Desde Bodeguero solo se permite pasar a Solicitante
    (403 en cualquier otra transición, con `_validar_rol_asignable` como frontera del
    Administrador); al pasar a Bodeguero se resuelve «Suministros» y el cambio de
    rol+departamento exige motivo. `usuario.sede_id` no se toca; no se consulta encargados;
    se conserva el 409 del último Administrador activo y `PUT .../sede` sigue fuera del
    catálogo de motivos. La ruta de control de Administradores (mismo DTO) responde 422 si
    se omite el departamento y 422 si se envía «Suministros», sin cambiar su formulario; el
    `200` publica el `departamento_id` real persistido.
    **Pruebas:** `backend/tests/funcional/integracion/test_edicion_suministros_012.py`
    (24 casos): legacy con/sin motivo, Bodeguero estable sin motivo, cambio de nombre con
    motivo, no-Bodeguero sin departamento (omitido/null), con «Suministros», con ajeno
    (403/404) y con válido; `0`/negativo en edición por ambos roles; Solicitante→Bodeguero
    con/sin motivo; Bodeguero→Solicitante válido (sin limpiar sede) y con «Suministros»
    (422); Bodeguero→Administrador por Administrador (403 sin mutación); último
    Administrador (409 sin mutar); ausencia de 409 por encargado; aislamiento INST01/INST02
    con el id real; usuario ajeno 404 sin resolver «Suministros»; control omite
    departamento (422) y rechaza «Suministros» para Administrador (422). Los tests previos
    de edición/control/último Administrador conservan su cobertura sin cambios.
    **Resultados:** `pytest` **2150 passed / 123 skipped / 0 failed** (2126 base + 24
    nuevos); `ng test` **645 SUCCESS / 0 failed**; `npx ng build` limpio (inicial
    **339.74 kB**, `main-SUOO4M4P.js`, 27.4 s). Sin cambios de DDL, semilla, contratos ni
    frontend.

- [x] **E12-A3 — Concurrencia, contrato/OpenAPI y pruebas gated del Bloque A.**
  - **Archivos:** `backend/tests/funcional/sistema/test_suministros_postgres_012.py` (nuevo,
    gated); `backend/tests/funcional/integracion/test_contrato_usuarios_suministros_012.py`
    (nuevo o ampliación); `spec.md` §10.3 para los tests de conteo.
  - **Sub-pasos:** dos altas concurrentes con dos sesiones/`Barrier`; una sola fila
    «Suministros», ambas 201, sin 500; reutilización/reactivación concurrente; contrato
    OpenAPI (campo opcional, 422 documentado, 72/74); regresión de `PUT .../sede` 409 y
    `gestion_organizacional`.
  - **AC:** AC-22, AC-30, AC-31, AC-35.
  - **Hecho cuando:** gated PostgreSQL verde; SQLite no acredita la carrera pero la suite
    sigue verde; OpenAPI/matriz 72/74 y los 422/409 documentados.
  - **Comandos:** `cd backend; $env:POSTGRES_TEST_URL="postgresql://postgres:postgres@localhost:5433/postgres";
    pytest tests/funcional/sistema/test_suministros_postgres_012.py` y suite completa.
  - **Evidencia esperada:** test gated de carrera con conteo exacto y contrato OpenAPI.
  - **Entregado (27/Nov/2026):** concurrencia, contrato/OpenAPI y verificación gated.
    **Gated:** `backend/tests/funcional/sistema/test_suministros_postgres_012.py`
    (4 casos) sobre base temporal PostgreSQL. Dos altas concurrentes de
    **Bodeguero distintos** con dos `TestClient`/sesiones y una barrera **después
    del pre-check** de cada petición (fuerza el mismo estado inicial y no fija el
    ganador del lock): ambas **201**, una sola fila «Suministros» activa, con
    `sede_id=NULL` y la descripción D-8, ambos usuarios apuntando a ella, sin 500
    ni fila huérfana; reutilización concurrente de una fila activa sin duplicar
    ni tocar nombre/descripción/sede; reactivación concurrente idempotente; y un
    fallo local posterior a la resolución (monkeypatch de
    `_confirmar_usuario_tenant`) que no confirma «Suministros».
    **Contrato:** `backend/tests/funcional/integracion/test_contrato_usuarios_suministros_012.py`
    (8 casos): `departamento_id` opcional solo en `UsuarioCrear`/`UsuarioEdicion`
    y obligatorio en `UsuarioRespuesta`; esquema de entrada `integer(min 1)` o
    `null`; `extra="forbid"` intacto; `/openapi.json` **74** = **72 v1 + `GET /`
    + `/health`**, matriz **72** y sin rutas de encargados; **422 por rol** y por
    «Suministros» documentado en `POST /usuarios/` y `PUT /usuarios/{id}`
    (descripciones de `endpoints/usuarios.py` actualizadas); regresión de
    `PUT /organizacion/usuarios/{id}/sede` **409** a no-Bodeguero y de
    `gestion_organizacional` (mapeo de sedes/departamentos/usuarios + **403**
    real con la capacidad apagada). El helper no requirió cambios.
    **Resultados:** `pytest` SQLite **2158 passed / 127 skipped / 0 failed**
    (2150/123 + 8 del contrato + 4 gated omitidos); gated PostgreSQL completo
    **2282 passed / 3 skipped / 0 failed** (los 3 de Redis sin `REDIS_TEST_URL`);
    `ng test` **645 SUCCESS / 0 failed**; `npx ng build` limpio (inicial
    **339.74 kB**, `main-SUOO4M4P.js`, 29.3 s). `spec.md` §10.3 solo añade los
    nombres de los dos archivos nuevos al inventario de pruebas. Sin cambios de
    DDL, semilla, helper ni frontend.

- [x] **E12-A4 — Frontend: tipos y alta por rol.**
  - **Archivos:** `frontend/src/app/shared/interfaces/index.ts`;
    `frontend/src/app/features/administracion/usuarios.component.ts|html`;
    `frontend/src/app/features/administracion/usuarios.component.spec.ts` (casos de alta).
  - **Sub-pasos:** `departamento_id?` en `UsuarioCrear`/`UsuarioEdicion`; señal reactiva del
    rol; Sede visible para Bodeguero/Solicitante; Bodeguero obligatorio sin «Sin asignar»;
    Solicitante como filtro; Departamento deshabilitado/texto «Suministros (asignación
    automática)» para Bodeguero, obligatorio/filtrado para Solicitante y obligatorio sin
    filtro para Administrador; sincronización
    sede↔departamento; payload que omite departamento para Bodeguero; `PUT .../sede` tras el
    alta con éxito parcial; tenant sin sedes.
  - **AC:** AC-24, AC-25, AC-26, AC-31.
  - **Hecho cuando:** `ng test`/`ng build` verdes; los specs de alta por rol, filtro,
    sincronización, sin sedes y fallo parcial pasan.
  - **Comandos:** `cd frontend; $env:CHROME_BIN=...; npx ng test --watch=false
    --browsers=ChromeHeadless; npx ng build`.
  - **Evidencia esperada:** casos de alta Bodeguero/Solicitante/Admin y éxito parcial.
  - **Entregado (27/Nov/2026):** tipos y alta por rol.
    **Tipos:** `UsuarioCrear` y `UsuarioEdicion` publican `departamento_id?: number | null`
    (contrato opcional de D-12); `Usuario` y `UsuarioRespuesta` no cambian.
    **Alta reactiva:** `rolCreacion` alimenta `creacionEsSolicitante`, `creacionMuestraSede` y
    `creacionBodegueroSinSedes`; al cambiar de rol se recalculan validadores y el estado
    habilitado y se limpia una selección incompatible. **Bodeguero:** Departamento
    **deshabilitado** con «Suministros (asignación automática)» (sin depender del catálogo),
    Sede **obligatoria** y sin «Sin asignar»; el payload **omite** `departamento_id` y nunca
    lleva `sede_id`; tras el 201 se llama a `PUT /organizacion/usuarios/{id}/sede` y, si falla,
    se conserva el mensaje de **éxito parcial** sin revertir el alta y sin perder el enlace de
    invitación; sin sedes en el tenant el botón queda deshabilitado, se muestra un aviso
    (`role="alert"`) y `guardarCreacion()` no emite la petición. **Solicitante:** Sede como
    **filtro** («Todas las sedes») y Departamento obligatorio filtrado por sede; al elegir un
    departamento la sede se sincroniza a la suya (o queda sin filtro si no tiene sede); al
    cambiar de sede se limpia el departamento incompatible y el formulario no se envía; solo
    viaja `departamento_id`. **Administrador/Superadmin:** sin Sede, Departamento habilitado y
    obligatorio. **Decisión no cubierta por el plan:** «Suministros» se excluye del combo del
    alta para todo rol distinto de Bodeguero (el backend responde **422** en ese caso, D-12) y
    el tenant que solo tiene «Suministros» muestra el aviso de que no hay departamentos
    disponibles; A6 conserva la regresión del borde.
    **Pruebas:** 9 casos nuevos y 1 existente reforzado en `usuarios.component.spec.ts`:
    matriz del Bodeguero (disabled/texto/sin «Sin asignar»/required), alta con éxito y payload
    sin departamento, fallo parcial de sede, tenant sin sedes, filtro y sincronización del
    Solicitante, limpieza y no envío con departamento incompatible, payload solo
    `departamento_id` sin `PUT .../sede`, recálculo al cambiar de rol y Administrador sin Sede
    (incluye la exclusión de «Suministros» y el paso Administrador→Bodeguero con sede
    obligatoria). Sin casos de edición (A5).
    **Resultados:** `ng test` **654 SUCCESS / 0 failed** (645 + 9); `npx ng build` limpio
    (inicial **339.96 kB**, `main-5HWV533U.js`, 33.0 s); `pytest` **2158 passed / 127 skipped /
    0 failed** sin tocar backend. Sin cambios de backend, DDL, semilla, spec/plan ni
    documentación de cierre; `spec.md` §5 y `plan.md` §6 no se editan.
  - **Corrección post-recorrido (27/Nov/2026):** el `<select>` de rol del alta usaba
    `[value]="rol.rol_id"`, así que el navegador entregaba el id como **string** y
    `creacionEsSolicitante()` (mapa `rolesPorId` con claves numéricas) no resolvía: al elegir
    Solicitante se habilitaba el Departamento pero la **Sede desaparecía** (AC-24/AC-25). Los
    tests con `setValue` numérico no lo detectaban. **Fix:** `[ngValue]` en el select de rol
    del alta (departamento y sedes ya lo usaban) y normalización con `Number(...)` en
    `nombreRol`, `nombreDepartamento`, `nombreSede`, `esDepartamentoSuministrosId`, los filtros
    de sede de `departamentosCreacion`, las comparaciones de limpieza/sincronización y el
    payload (`rol_id`/`departamento_id` numéricos); sin cambios de lógica de negocio.
    **Prueba de regresión DOM:** `AC-24/AC-25: elegir Solicitante desde el DOM muestra la Sede
    del alta, filtra y envía números` (selecciona la opción real y dispara `change`; comprueba
    Sede visible sin `required`, filtro por sede y tipos numéricos en el payload). Se verificó
    en rojo contra `[value]` (**2 failed / 63 success**) y en verde con el fix. `ng test`
    **65 SUCCESS** en el spec y **671 SUCCESS / 0 failed** en la suite completa del momento;
    `npx ng build` limpio (inicial **339.98 kB**, `main-IRJLFDU6.js`, 34.4 s); `pytest`
    **2163 passed / 127 skipped / 0 failed** sin tocar backend.

- [x] **E12-A5 — Frontend: edición por rol y legacy.**
  - **Archivos:** `frontend/src/app/features/administracion/usuarios.component.ts|html`;
    `frontend/src/app/features/administracion/usuarios.component.spec.ts` (casos de edición).
  - **Sub-pasos:** `sede_id` en `formularioEdicion`; señal del rol de edición; Bodeguero con
    Departamento deshabilitado y Sede obligatoria; Solicitante con Sede-filtro y Departamento
    filtrado; `hayCambiosEdicion` que detecta el legacy «Biblioteca»→«Suministros» y exige
    motivo; guardar en orden `PUT /usuarios` → `PUT .../sede`; éxito parcial; refrescar el
    catálogo para mostrar «Suministros»; tenant con solo «Suministros».
  - **AC:** AC-27, AC-28, AC-29, AC-31.
  - **Hecho cuando:** `ng test`/`ng build` verdes; los specs de edición legacy, cambio de rol,
    motivo, éxito parcial y tenant con solo «Suministros» pasan.
  - **Comandos:** `cd frontend; $env:CHROME_BIN=...; npx ng test --watch=false
    --browsers=ChromeHeadless; npx ng build`.
  - **Evidencia esperada:** casos de edición por rol y recuperación de sede.
  - **Entregado (27/Nov/2026):** edición por rol y legacy.
    **Formulario:** `formularioEdicion` suma `sede_id`; `rolEdicion` alimenta
    `edicionEsBodeguero`, `edicionEsSolicitante`, `edicionMuestraSede`,
    `departamentosEdicion` (sin «Suministros», filtrado por sede para el Solicitante) y
    `edicionBodegueroSinSedes`; `iniciarEdicion` deshabilita el Departamento del Bodeguero
    (con «Suministros (asignación automática)»), exige Sede sin «Sin asignar» y, para el
    Solicitante, inicializa el filtro con la sede de su departamento.
    **Legacy y motivo:** `hayCambiosEdicion` compara el rol destino y, si es Bodeguero,
    resuelve el departamento persistido normalizado (`trim/lower`): un legacy «Biblioteca»
    es cambio efectivo (exige motivo) y uno ya en «Suministros» sin más cambios no lo es;
    el cambio de nombre y los cambios de rol son efectivos. El motivo se exige antes de
    enviar y el backend sigue siendo la frontera.
    **Guardado:** payload de `PUT /usuarios/{id}` omite `departamento_id` para Bodeguero y
    nunca lleva `sede_id`; tras el 200 se llama a `PUT .../sede` en ese orden (idempotente si
    la sede no cambió); si el primero falla no se llama al segundo; si falla la sede, los
    cambios quedan guardados y el mensaje es de éxito parcial («se guardaron, pero la sede
    no se actualizó») con `role="alert"`. El Solicitante solo persiste `departamento_id` y
    no llama al PUT de sede; el paso desde Bodeguero no toca `usuario.sede_id`. Si el tenant
    no tiene sedes o solo tiene «Suministros», el guardado se bloquea y el formulario lo
    indica. Tras guardar se refresca el catálogo y el listado (4 GET) conservando el mensaje
    de éxito, de modo que el usuario muestra «Suministros» aunque la fila naciera en el PUT.
    **Pruebas:** 10 casos nuevos en `usuarios.component.spec.ts` (legacy con/sin motivo,
    nombre en Bodeguero, filtro/sincronización y payload del Solicitante, cambios a/desde
    Bodeguero, tenant con solo «Suministros», tenant sin sedes, éxito parcial, orden y fallo
    del primer PUT, Administrador sin Sede) y 2 casos existentes ajustados (el PUT de
    edición ahora consume la recarga y el caso «sin cambios» pasó a un Bodeguero ya en
    «Suministros»). **Resultados:** `ng test` **664 SUCCESS / 0 failed** (654 + 10);
    `npx ng build` limpio (inicial **339.96 kB**, `main-QH2MR6KT.js`, 27.1 s); `pytest`
    **2158 passed / 127 skipped / 0 failed** sin tocar backend. Sin cambios de DDL, semilla,
    contratos, spec/plan ni documentación de cierre (A6/C3 pendientes).
    **Desviaciones no cubiertas por el plan:** «Suministros» se excluye también del combo de
    edición de Administrador/Superadmin (D-12 lo rechaza con 422; antes se ofrecía); al
    cambiar desde Bodeguero el filtro vuelve a «Todas las sedes» hasta elegir un departamento
    válido; la transición desde Bodeguero a otro rol distinto de Solicitante no se filtra en
    la UI más allá de `rolesEdicion` (la vista institucional es solo del Administrador, cuyo
    combo ya ofrece Bodeguero/Solicitante) y el 403 del backend sigue siendo la frontera.
  - **Corrección post-recorrido (27/Nov/2026):** el `<select>` de rol de la edición sufría el
    mismo defecto que el del alta (`[value]="rol.rol_id"` entregaba un string): al elegir
    Solicitante, `edicionEsSolicitante()` no resolvía y la **Sede de edición desaparecía**;
    además `hayCambiosEdicion` y las comparaciones de sede/departamento podían desalinearse.
    **Fix:** `[ngValue]` en el select de rol de la edición y normalización con `Number(...)`
    en `nombreRol`, `nombreDepartamento`, `nombreSede`, `esDepartamentoSuministrosId`, los
    filtros de `departamentosEdicion`, las comparaciones de `hayCambiosEdicion`, la
    sincronización/limpieza y el payload (`rol_id`, `departamento_id` y la sede del
    `PUT .../sede`); sin cambios de lógica. **Prueba de regresión DOM:**
    `AC-29: elegir Solicitante desde el DOM mantiene la Sede de edición, filtra y envía
    números` (opción real + `change`; Sede visible y habilitada como filtro, departamentos
    filtrados y payload numérico sin tocar el PUT de sede). Se verificó en rojo contra
    `[value]` (**2 failed / 63 success**) y en verde con el fix. `ng test` **65 SUCCESS** en el
    spec y **671 SUCCESS / 0 failed** en la suite completa; `npx ng build` limpio (inicial
    **339.98 kB**, `main-IRJLFDU6.js`, 34.4 s); `pytest` **2163 passed / 127 skipped / 0
    failed** sin tocar backend.

- [x] **E12-A6 — Frontend: regresión cruzada, accesibilidad y bordes.**
  - **Archivos:** `frontend/src/app/features/administracion/usuarios.component.spec.ts`;
    `frontend/src/app/features/administracion/administracion-nav.component.spec.ts` solo
    si la regresión de 3 pestañas lo requiere; sin cambios de contrato.
  - **Sub-pasos:** matriz de roles alta/edición; labels/`aria-describedby`/estado disabled;
    tenant sin sedes; tenant con solo «Suministros»; Bodeguero sin departamento; no-Bodeguero
    con «Suministros»; último Administrador; `ng test` completo.
  - **AC:** AC-24, AC-27, AC-29, AC-31, AC-38.
  - **Hecho cuando:** suite frontend completa verde y build limpio; no se duplican casos ya
    cubiertos en A4/A5.
  - **Comandos:** `cd frontend; $env:CHROME_BIN=...; npx ng test --watch=false
    --browsers=ChromeHeadless; npx ng build`.
  - **Evidencia esperada:** specs de borde/accesibilidad y suite completa.
  - **Entregado (27/Nov/2026):** regresión cruzada, accesibilidad y bordes del frontend.
    **Archivos:** `usuarios.component.ts|html|spec.ts` y `administracion.routes.spec.ts`
    (el borde del wildcard pertenece al contrato de rutas; `administracion-nav.component.ts|spec.ts`
    no requirió cambios y se ejecutó completo). **Defectos reales corregidos:** (1) el aviso
    «No hay departamentos disponibles» del alta no se anunciaba y ahora lleva `role="alert"`
    (la edición ya lo tenía); (2) un rol distinto de Bodeguero con «Suministros» en el control
    (valor heredado o programático; el combo ya lo excluye) podía enviarse y el backend lo
    rechazaba con 422: se añaden `creacionSeleccionaSuministros`/`edicionSeleccionaSuministros`,
    aviso inline `role="alert"`, botón deshabilitado y guardas en `guardarCreacion`/
    `guardarEdicion` que no emiten petición (D-12/AC-24/AC-29). **Casos nuevos (8, sin duplicar
    A4/A5):** a11y del alta (labels `for` asociados, `aria-describedby` del Departamento
    automático, `disabled` con foco visible `focus-visible`, ids únicos y `tabindex` no
    negativo); a11y del aviso de tenant sin sedes en alta y en edición (`role="alert"` +
    descripción de Sede); a11y de la edición del Bodeguero; tenant con solo «Suministros» en
    alta no-Bodeguera (se indica y no se envía); «Suministros» heredado en alta y en edición
    no-Bodeguera (bloqueado y avisado); Administrador→Bodeguero en edición (Sede obligatoria y
    Departamento deshabilitado) junto al **409 del último Administrador activo** sin llamada a
    `PUT .../sede`; y una URL hija no publicada (el contrato exacto de tres vistas prueba que
    `/administracion/encargados` no existe) → wildcard `/dashboard` sin montar la vista.
    **Resultados:** `ng test` **672 SUCCESS / 0 FAILED** (664 base + 8; 63 casos del spec de
    usuarios y 4 del de rutas); `npx ng build` limpio (inicial **339.98 kB**, `main-SDNVCA3X.js`);
    `pytest` SQLite **2158 passed / 127 skipped / 0 failed** sin tocar backend. **Desviación no
    cubierta por el plan:** el borde del wildcard se verificó en `administracion.routes.spec.ts`
    (árbol real de administración + wildcard vigente + dashboard de reemplazo) con una URL hija
    no publicada, en lugar del spec de la barra y sin reescribir el literal retirado: el contrato
    exacto de tres vistas ya prueba que `/administracion/encargados` no tiene ruta y así
    `frontend/src` sigue sin referencias que AC-39 prohíbe. No se tocaron DDL, semilla,
    contratos, A4/A5 ni C. Los cambios visuales (aviso inline y botón deshabilitado) quedan para
    el recorrido de C2 en 4200 y el humo de C3 en 8080.

### Cierre

- [x] **E12-C1 — Suites completas, build, OpenAPI y grep de coherencia.**
  - **Archivos:** solo correcciones si una suite roja demuestra un defecto; evidencia en
    `docs/spec/features/012-gestion-administrativa/spec.md` y
    `docs/spec/features/012-gestion-administrativa/evidencia/README.md` al observar.
  - **Sub-pasos:** `pytest` SQLite; gated PostgreSQL; `ng test`; `ng build`; `/openapi.json`
    (74 = 72 v1 + `GET /` + `/health`, matriz 72); regresión de la 017
    (`test_gobierno_identidades_017.py`, `test_provisionamiento_identidades_017.py`,
    `test_frontera_clerk_017.py`, `test_gobierno_administradores_017.py`,
    `test_gobierno_correcciones_017.py`, `test_aceptacion_invitacion_017.py`); `grep -r` de
    `DepartamentoEncargado`, `departamento_encargado`, `/encargados` y «encargado» en
    `backend/tests`, `frontend/src` y `database/`, revisando los falsos positivos de
    «Bodeguero / Encargado de Suministros».
  - **AC:** AC-31, AC-39, AC-41.
  - **Hecho cuando:** todas las suites verdes, build limpio, OpenAPI/matriz 72/74 y el grep no
    deja referencias vigentes.
  - **Evidencia esperada:** conteos de suites, build, OpenAPI y grep.
  - **Entregado (27/Nov/2026):** suites completas, build, contrato y grep verdes; sin cambios de
    código ni de spec/plan. **Backend SQLite:** `.venv\Scripts\python.exe -m pytest -q`
    **2158 passed / 127 skipped / 0 failed** (374 s). **Gated PostgreSQL:**
    `$env:POSTGRES_TEST_URL="postgresql://postgres:postgres@localhost:5433/postgres"` → **2282
    passed / 3 skipped / 0 failed** (2143 s; los 3 skipped son los gated de Redis sin
    `REDIS_TEST_URL`). **Frontend:** `$env:CHROME_BIN=…msedge.exe; npx ng test --watch=false
    --browsers=ChromeHeadless` → **672 SUCCESS / 0 FAILED** (Edge 158, 21.6 s) y `npx ng build`
    **limpio** (`main-SDNVCA3X.js`, inicial **339.98 kB**, 52.8 s). **OpenAPI:** `/openapi.json`
    en vivo (backend 8000) **200** con **74** operaciones = **72 v1 + `GET /` + `/health`**;
    matriz **72**; las 3 rutas de encargados no se publican y responden **404** (sondeo
    GET/POST/DELETE `/organizacion/departamentos/1/encargados[/1]`); `UsuarioCrear.departamento_id`
    opcional (`anyOf int|null`, fuera de `required`) y `UsuarioRespuesta` lo exige; 422 por
    rol/«Suministros» documentados en `POST /usuarios/` y `PUT /usuarios/{id}`; `PUT
    /organizacion/usuarios/{id}/sede` documenta **409**; `gestion_organizacional` mapea **18**
    operaciones de sedes/departamentos/usuarios (solo `/auth/me` y `/control/*` quedan sin
    capacidad). **Conteos/versión (`apt_erp`, sin reset nuevo):** `control` **25** tablas, **4**
    tenants con **22** cada uno, `to_regclass('control.departamento_encargado')` nulo, 0 relaciones
    con ese nombre y `version_esquema = 026.1` en control y en los cuatro tenants; **21** entidades
    de dominio (21 clases en el metadata tenant; las auxiliares de `control` no cuentan).
    **Regresión AC-41:** las seis suites de la 017 verdes (**99 passed** en ejecución dirigida) y
    tickets/stock/compras/dashboard/autenticación incluidos en las suites completas.
    **Grep:** 0 coincidencias de `DepartamentoEncargado`, `departamento_encargado` ni `/encargados`
    en `backend/tests`, `frontend/src` y `database/`; las únicas menciones de «encargado» son
    ratchets de ausencia ya justificados (`test_contrato_usuarios_suministros_012.py::
    test_openapi_y_matriz_no_publican_las_rutas_de_encargados`,
    `test_edicion_suministros_012.py::test_edicion_de_usuario_no_bloquea_por_encargado`, el fixture
    `Sin.Encargado` y el docstring «no consulta encargados» de `organizacion_service.py`), no
    referencias vigentes; «Bodeguero / Encargado de Suministros» no aparece en esas rutas.
    **Desviación de entorno (no de código):** la primera corrida gated se interrumpió con el disco
    `C:` al 100 % y Docker Desktop atascado; se liberó caché regenerable
    (`frontend/.angular/cache`, 2.4 GB), se reinició Docker Desktop y se repitió la suite completa.
    **Reporte para C3 (no editado):** `AGENTS.md` §4/§7 (26/23/`026.0`, «21 + auxiliar»),
    `MEMORY.md`, `database/README.md`, `docs/spec/stack.md` (árbol con `encargados.component.ts` y
    menciones históricas), skills `sdd-workflow`/`fastapi-pydantic-v2` («22 + auxiliar»), diagramas
    (casos de uso, clases y flujo 03) e informes (`_generar_informe.py`,
    `_generar_planilla_pruebas.py`, `_datos/frontend-specs.json`,
    `_datos/backend-coleccion-027.txt`) todavía citan encargados o cifras viejas;
    `frontend/src/testing/funcional/README.md` declara 42 specs/559 casos (hoy 44/672).

- [x] **E12-C2 — Reset limpio, gated y recorrido funcional en 4200.**
  - **Archivos:** `docs/spec/features/012-gestion-administrativa/evidencia/README.md`
    (capturas/notas) al observar; sin código nuevo.
  - **Sub-pasos:** `down -v` + `up -d`; 25/22/`026.1`, sin `departamento_encargado`; 4200 con
    alta de Bodeguero (Sede obligatoria, «Suministros»), alta de Solicitante (filtro/
    sincronización), edición del Bodeguero legacy con motivo, cambio de rol a/desde Bodeguero,
    tenant sin sedes, tenant con solo «Suministros», éxito parcial de sede, 3 pestañas y
    `/administracion/encargados` → `/dashboard`.
  - **AC:** AC-20…AC-30, AC-33, AC-34, AC-38.
  - **Hecho cuando:** el recorrido 4200 escribe contra PostgreSQL real y cada caso deja el
    estado esperado; el reset es limpio.
  - **Evidencia esperada:** capturas, consultas SQL y resultados del recorrido.
  - **Entregado (27/Nov/2026):** reset limpio (`down -v` + `up -d` sobre volumen recreado) con
    `control` **25** tablas, **4** tenants con **22**, sin `departamento_encargado` y
    `version_esquema = 026.1` en control y en los cuatro tenants; `/health` **200** y dev server
    en 4200. **Recorrido 4200** con sesión Administrador `crise.gonzalez@duocuc.cl` (sign-in
    token efímero; la secret key no se expuso) y **sin capturas PNG nuevas**: la evidencia es
    textual y SQL en `evidencia/README.md`. (1) **Alta Bodeguero** `Bodeguero E12 QA`
    (`bodeguero.e12+clerk_test@example.com`): Departamento deshabilitado «Suministros
    (asignación automática)», Sede obligatoria sin «Sin asignar», `POST /api/v1/usuarios/`
    **201** y PUT de sede; fila **Bodeguero · Suministros · Sede Maipu**, invitación
    **Pendiente**; tenant a **14** usuarios. (2) **Alta Solicitante** `Solicitante E12 QA`
    (`solicitante.e12+clerk_test@example.com`): Sede (filtro) limitó el Departamento a
    Secretaría/RRHH/Biblioteca, se eligió Biblioteca y `POST` **201**; fila **Solicitante ·
    Biblioteca**, sin sede persistida; **15** usuarios. (3) **Edición del Bodeguero legacy**
    `Andres Vargas` (usuario 6): Departamento bloqueado en Suministros, Sede obligatoria y
    motivo exigido, guardado con «Reasignación organizacional»; `PUT /api/v1/usuarios/6`
    **200** y `PUT /organizacion/usuarios/6/sede` **200**, mensaje «Usuario «Andres Vargas»
    actualizado y sede asignada». (4) **3 pestañas** Sedes/Departamentos/Usuarios con
    `role=tab`, `aria-selected` y `tabpanel` con `aria-labelledby`; `/administracion/encargados`
    cayó en el wildcard **`/dashboard`**; la pestaña Departamentos mostró **Suministros** («Sin
    sede asignada») y el **KPI de departamentos 7 → 8**. **SQL real
    (`tenant_inst_001_038aa2a9`):** `usuario` **15**, `departamento` **8**; Bodeguero (id 17)
    `rol=3 Bodeguero`, `departamento_id=8 Suministros`, `sede_id=2 Sede Maipu`; Solicitante
    (id 18) `rol=4 Solicitante`, `departamento_id=6 Biblioteca`, `sede_id=NULL`; Andres Vargas
    (id 6) `rol=3`, `departamento_id=8`, `sede_id=2`; departamento Suministros (id 8) con
    `sede_id=NULL` y `activo=true`. **Corrección post-recorrido:** los `<select>` de
    rol/departamento pasaron de `[value]` a `[ngValue]` (ids normalizados y tests DOM):
    `ng test` **671 SUCCESS / 0 FAILED** y `pytest` SQLite **2163 passed / 127 skipped /
    0 failed**. Los casos de cambio de rol, tenant sin sedes, tenant con solo «Suministros» y
    éxito parcial de sede ya estaban cubiertos por las suites de A1–A6 (C1) y/o el recorrido
    previo de la enmienda; el humo visual de 8080 queda para C3.

- [x] **E12-C3 — 8080 reconstruido, documentación, evidencias y cierre.**
  - **Archivos:** `database/README.md`, `AGENTS.md` §4/§7, `MEMORY.md`, `.agents/skills/*`,
    `docs/diagramas/`, `Informe_Flujos_Actores.docx`, `docs/spec/roadmap.md`,
    `docs/spec/features/012-gestion-administrativa/evidencia/README.md` y la evidencia de
    AC-20…AC-41; no tocar código salvo un defecto observado.
  - **Sub-pasos:** `docker compose -f docker-compose.yml build frontend` + `up -d frontend`;
    humo de 3 pestañas, deep links y flujo básico; actualizar conteos 25/22/`026.1`, 21
    entidades, 72/74 y la lista de features; marcar capturas históricas de encargados;
    regenerar informe/diagramas si citan la figura; completar la evidencia por AC; grep
    `AGENTS.md`/`MEMORY.md`/skills; no reabrir el cierre de la 012.
  - **AC:** AC-40, AC-41.
  - **Hecho cuando:** 8080 sirve el build nuevo, el humo responde, la documentación no repite
    encargados/4 pestañas y cada AC-20…AC-41 tiene evidencia observada.
  - **Comandos:** `docker compose -f docker-compose.yml build frontend`; `up -d frontend`.
  - **Evidencia esperada:** bundle/hash de 8080, capturas de las 3 pestañas, grep de
    coherencia y evidencia por AC.
  - **Entregado (27/Nov/2026):** **8080 reconstruido y verificado**, documentación y evidencias
    de cierre. **8080:** `docker compose -f docker-compose.yml build frontend` (capas `CACHED`:
    el código no cambió desde el build de la corrección `[ngValue]`) + `up -d --force-recreate
    frontend` (contenedor recreado, `healthy`); nginx sirve **`main-IRJLFDU6.js`**, el mismo hash
    que produce el `npx ng build` actual (limpio). Humo con sesión **Administrador**
    (`crise.gonzalez@duocuc.cl`, INST-001): `/administracion` → `sedes` con **3 pestañas** y
    `tabpanel`/`aria-labelledby` por ruta; **15 usuario(s)**; `Bodeguero E12 QA` y `Andres Vargas`
    en **Bodeguero · Suministros · Sede Maipu**; `Solicitante E12 QA` en **Solicitante ·
    Biblioteca** sin sede; departamento **Suministros** activo con su descripción y «Sin sede
    asignada»; alta con Departamento deshabilitado «Suministros (asignación automática)» + Sede
    obligatoria sin «Sin asignar»; cambio a Solicitante **desde el DOM** (Sede-filtro +
    Departamento; Maipú → Secretaría/RRHH/Biblioteca); `/administracion/encargados` → wildcard
    **`/dashboard`**; dashboard con Departamentos **8**; deep links HTTP **200**. **Sin PNG
    nuevos:** la evidencia es textual/DOM/SQL y las capturas `01`–`28` quedan marcadas históricas.
    **Documentación:** `AGENTS.md` §4/§7 (25/22, `026.1`, 21 entidades sin auxiliar, 3 vistas de
    administración), `MEMORY.md` reescrito (31 líneas), `database/README.md`, `docs/spec/stack.md`
    (nota de vigencia implementada, árbol sin `encargados.component.ts`, enmienda y estado),
    `docs/spec/roadmap.md` (enmienda `[x]`, filas 011/012 actualizadas, «Siguiente feature»
    015/016), `.agents/skills/{sdd-workflow,fastapi-pydantic-v2}`, `frontend/src/testing/funcional/README.md`
    (**44 specs / 671 casos**, índice completo con `rut`, `validacion-http` y `ticket.service`:
    la comprobación imprime **0** fuera) y `evidencia/README.md` (secciones C2 y **8080**).
    **Diagramas:** `_generar.py` de `flujos-actores` (paso «Asignar encargados» → «Asignar sede
    del Bodeguero», subtítulo sin encargados), HTML+PNG del flujo `03` (2400×1120), casos de uso
    del Administrador (`A3` retirado, `A1…A5`, **20** casos) y vista general (**25 casos**,
    «Asignar encargados» fuera), clases de organización y catálogo (**5 clases**, sin
    `DepartamentoEncargado`, «21 ENTIDADES · ESTA VISTA: 9»); PNG regenerados a 2x con Edge
    headless y los cuatro HTML pasan `self_check.py` (flujos 12/12). **Informe:**
    `_generar_informe.py` sin encargados y `Informe_Flujos_Actores.docx` regenerado (58 tablas, 12
    imágenes, 334 párrafos; 0 menciones de «encargado» en el texto). **Spec:** AC-20…AC-41 con
    evidencia real y `[x]`; estado de la enmienda → **cerrada y verificada (27/Nov/2026)**;
    §10.5/§10.7 y notas históricas sincronizadas. **Suites re-verificadas en C3:** `pytest` SQLite
    **2163 passed / 127 skipped / 0 failed**; **gated PostgreSQL 2287 passed / 3 skipped / 0
    failed** (la primera corrida gated falló 3 pruebas de concurrencia de
    `test_correcciones_postgres_017.py` porque el contenedor `db` se reinició a mitad; pasan en
    aislamiento y la repetición completa terminó verde); `ng test` **671 SUCCESS / 0 failed**;
    `ng build` limpio (`main-IRJLFDU6.js`); `/openapi.json` **74** (72 v1 + 2 técnicas) y matriz
    **72**; `control` **25** / tenants **22** con `version_esquema = 026.1` y sin
    `departamento_encargado`.
    **Pendiente reportado (no falseado):** `Planilla_Pruebas_Compustock.xlsx` y sus snapshots
    `_datos/backend-coleccion-027.txt` / `_datos/frontend-specs.json` siguen siendo la **línea base
    del cierre 027** y por eso conservan la vista y los casos de `encargados`; el generador quedó
    documentado como artefacto histórico y con el procedimiento de re-baseline, pero no se regeneró
    (exige recalcular conteos por tipo y la narrativa fechada). **Siguiente acción:** re-baselinar
    la planilla cuando se actualice el informe de pruebas.
  - **Corrección post-validación (27/Nov/2026):** el reviewer emitió `CAMBIOS NECESARIOS` solo por
    documentación/evidencia. **AC-32:** se recorrió en 4200 el **cambio de rol en ambos sentidos**
    sobre `Ricardo Nilo` (id 16) —Solicitante → Bodeguero con Sede Maipu, «Reasignación
    organizacional», `PUT /usuarios/16` **200** + `PUT .../sede` **200** y fila Bodeguero ·
    Suministros · Sede Maipu; y Bodeguero → Solicitante con Biblioteca, «Cambio de funciones»,
    `PUT /usuarios/16` **200** sin PUT de sede y fila Solicitante · Biblioteca— y el SQL final
    (13 usuarios, 8 departamentos, `Suministros` activo con `sede_id NULL` y 0 usuarios,
    `usuario.sede_id = 2` residual). Se añadió a `spec.md` (AC-28/AC-29/AC-32) y a
    `evidencia/README.md` §«Corrección post-validación — cambio de rol manual». **AC-40:**
    corregidas las contradicciones —estado del segundo bloque (`spec.md`), nota de la 026,
    `stack.md` sin «queda pendiente», `MEMORY.md` (Features 015/016 pendientes y recorridos
    15/Suministros/KPI 8 como históricos, con la base viva 13/8), frase de `tasks.md` sobre no
    marcar casillas, y evidencia de AC-39 sobre el grep de `database/` (0 en SQL, 1 mención
    histórica en el README)—. No se tocó código, tests, DDL, la enmienda 013 ni la planilla. C3
    sigue `[x]`; la enmienda permanece **cerrada y verificada (27/Nov/2026)**.

### Matriz de trazabilidad AC ↔ tareas (enmienda)

| AC | Tareas |
|---|---|
| AC-20 | E12-A1, E12-A3, E12-C2 |
| AC-21 | E12-A1, E12-A3, E12-C2 |
| AC-22 | E12-A3 |
| AC-23 | E12-A1, E12-A3 |
| AC-24 | E12-A1, E12-A4, E12-A6 |
| AC-25 | E12-A1, E12-A4, E12-C2 |
| AC-26 | E12-A1, E12-A4 |
| AC-27 | E12-A2, E12-A5, E12-A6 |
| AC-28 | E12-A2, E12-A5 |
| AC-29 | E12-A2, E12-A5, E12-A6 |
| AC-30 | E12-A1, E12-A2, E12-A3 |
| AC-31 | E12-A1, E12-A2, E12-A3, E12-A4, E12-A5, E12-A6, E12-C1 |
| AC-33 | E12-B1, E12-C2 |
| AC-34 | E12-B1, E12-C2 |
| AC-35 | E12-B1, E12-A3, E12-C1 |
| AC-36 | E12-B1, E12-C1 |
| AC-37 | E12-B1 |
| AC-38 | E12-B2, E12-A6, E12-C2 |
| AC-39 | E12-B1, E12-B2, E12-C1 |
| AC-40 | E12-C1, E12-C2, E12-C3 |
| AC-41 | E12-A3, E12-C1, E12-C2, E12-C3 |
