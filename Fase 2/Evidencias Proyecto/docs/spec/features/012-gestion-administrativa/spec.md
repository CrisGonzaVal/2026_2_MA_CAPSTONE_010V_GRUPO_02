# Feature 012: Gestión administrativa

> **Nota de vigencia (19/Oct/2026):** este documento describe la feature tal como
> se cerró. Las migraciones que cita (`database/migraciones/*`) se retiraron del
> repo en la consolidación de la base: hoy `database/` solo tiene
> `01_esquema.sql` y `02_datos_semilla.sql`, y la base se reconstruye con
> `docker compose down -v` + `up -d`. La evidencia y las decisiones siguen siendo
> válidas; los nombres de archivos citados son históricos. Los tests gated
> citados (`test_gestion_administrativa_postgres_012.py` y sus casos de
> migración) conservan solo las pruebas de instalación limpia; los casos de
> migración se retiraron junto con los scripts.

**Estado:** Cerrada (18/Oct/2026)  
**Release:** 2.0 — Sprint 5  
**Tipo:** Administración institucional y control SaaS

> **Enmienda de presentación posterior al cierre (22/Oct/2026):** la Feature 012
> permanece cerrada. La enmienda T-17 cambia únicamente la semántica ARIA y
> presentación de la navegación administrativa para alinearla con las pestañas
> accesibles de inventario; no reabre las decisiones de negocio ni modifica las
> rutas hijas. Se incorpora como ajuste de presentación, siguiendo el precedente
> de la enmienda T17 de la Feature 014.

> **Enmienda funcional posterior al cierre (27/Nov/2026):** la Feature 012 permanece
> cerrada. La enmienda tiene **dos bloques**: (a) alta y edición de usuarios según rol
> (Bodeguero sin Departamento editable y con Sede obligatoria **en la interfaz**; Solicitante
> con Sede como filtro y Departamento obligatorio) y el contrato de `departamento_id` en los
> DTO de entrada; y (b) **eliminación completa del concepto de encargado de departamento**
> (`departamento_encargado`), con retiro de su tabla, vista y operaciones y cambio de
> DDL/semilla, conteos **25/22** y token **`026.1`**. **Estado de la enmienda: cerrada y
> verificada (27/Nov/2026)**; ver los dos bloques más abajo y la evidencia de AC-20…AC-41. No
> reabre AC-1…AC-9, AC-11…AC-14; AC-10 y AC-15…AC-19 quedan retirados/supersedidos por el
> Bloque B.

## 1. Problema

La Feature 010 habilitó el portal `/control` para aprovisionar una institución y su primer Administrador, pero no ofrece la gestión cotidiana posterior. La Feature 011 introdujo sedes y asociaciones organizacionales por tenant y dejó expresamente para esta feature sus pantallas administrativas. Sin una interfaz unificada, el Superadmin no puede mantener el registro global ni supervisar el estado de la plataforma, y los Administradores Institucionales carecen de UI para gestionar sus instituciones, sedes, departamentos, usuarios y encargados.

El Superadmin tiene identidad global en `control`, no un catálogo ni un tenant operativo propio. Por tanto, su panel debe ofrecer visión SaaS y administración de instituciones, no mostrar el tablero Kanban operativo de tickets de un tenant.

> **Nota histórica (27/Nov/2026):** las menciones de este apartado y del objetivo a los
> «encargados de departamento» describen el estado previo a la enmienda funcional; el Bloque B
> retiró la tabla, la vista y las operaciones, y el alcance vigente es sedes, departamentos y
> usuarios (ver §10.5).

## 2. Objetivo

Proveer interfaces administrativas reales para que el Superadmin gestione instituciones y supervise la plataforma SaaS, y para que los Administradores Institucionales administren las sedes, departamentos, usuarios y encargados de departamento de su propio tenant, respetando Clerk, la matriz central de permisos y el aislamiento multi-tenant.

> **Contexto histórico (27/Nov/2026):** las menciones a «encargados» en §1 y §2 describen el
> alcance original de la Feature 012. El Bloque B retira la vista y el concepto de encargado
> de departamento; la evidencia histórica de AC-10 se conserva sin reescribir.

## 3. Alcance

### Dentro

- UI administrativa para crear, consultar, modificar y desactivar instituciones desde el portal `/control` del Superadmin, complementando el aprovisionamiento inicial de la Feature 010.
- Dashboard global del Superadmin con instituciones activas, sedes por institución y conteo de usuarios por rol por institución, con atribución institucional visible.
- Vista y administración por Superadmin de las capacidades funcionales por tenant, usando una fuente de verdad persistida y explícita. «Capacidad funcional por tenant» significa disponibilidad global de una función del producto para una institución; no es un permiso o capacidad de rol.
- Hacer de `/control` la vista administrativa SaaS del Superadmin y excluir al Superadmin de la navegación y ruta `/tickets`, donde se encuentra el Kanban operativo.
- UI para que el Administrador Institucional administre sedes, departamentos, usuarios y asociaciones de encargados de departamento en su tenant.
- Uso de las reglas y APIs organizacionales de la Feature 011, incluidas asignaciones departamento-sede, Bodeguero-sede y asociaciones de encargados.
- Aplicar límites por institución y protección de datos en las lecturas y escrituras administrativas.
- Mantener coherentes el registro institucional fuente de verdad en `control` y la fila `institucion` espejo del tenant.

### Fuera

- Crear, invitar, modificar credenciales o eliminar identidades en Clerk; la gestión de usuarios de esta feature administra identidades locales ya existentes en Clerk y su vinculación local. El usuario local solo puede autenticarse si su correo primario verificado coincide con su asociación vigente.
- CRUD de permisos o modificación de la matriz central de autorización; los roles existentes y sus capacidades no se redefinen.
- Cambios a la matriz central de permisos o a las capacidades/permisos asociados a los roles. El guard de ruta de `/tickets` para Superadmin es solo navegación/UI, no sustituye ni modifica dicha matriz.
- Escritura del Superadmin en datos operativos de tenants (catálogo, stock, tickets o movimientos).
- Operación Kanban de tickets por Superadmin. El Kanban y `/tickets` continúan disponibles para los roles de negocio permitidos por las reglas vigentes; esta feature solo cambia navegación y guard de ruta para excluir al Superadmin.
- Transferencias de stock, cambio de ciclo de vida de tickets/catálogos, informes o notificaciones.
- Borrado físico de institución, tenant o historial operativo.
- Selector de tenant o elección de institución por parte del cliente para ampliar su ámbito.
- Sistema de planes, cobros, licenciamiento, cuotas comerciales o configuración variable de productos; las capacidades funcionales por tenant son un conjunto cerrado y estable, no se derivan de permisos de rol.

## 4. Actores, requisitos funcionales y decisiones

### Actores

- **Superadmin:** consulta el panorama global, administra el registro institucional en control y accede a las funciones activas por institución. No opera un tenant como usuario de negocio.
- **Administrador Institucional:** administra las entidades organizacionales y usuarios locales de su institución; no accede a datos de otras instituciones.
- **Clerk:** autoridad externa de autenticación; no se modifica su ciclo de identidad en esta feature.

### D-1 — Superadmin administra el registro canónico y no los datos de negocio del tenant

Las altas, modificaciones y desactivaciones de instituciones se realizan sobre el registro fuente de verdad en `control`. Se sincronizan en la fila espejo del tenant únicamente `institucion_id` y `nombre`; cualquier atributo que no forme parte de esa pareja no es sincronizable por esta operación y permanece exclusivamente en control, sin copiarse ni rechazarse por ello. El Superadmin no obtiene escritura sobre sedes, departamentos, usuarios o datos operativos de los tenants por el solo hecho de poder administrar el registro institucional global.

**Por qué:** Feature 010 define `control` como autoridad del registro institucional y establece el espejo local para satisfacer las FK tenant. La separación mantiene la frontera entre administración SaaS y operación de negocio.

### D-2 — Desactivación lógica de institución, sin borrado ni pérdida de historial

La acción «desactivar» es lógica y reversible mediante modificación/reactivación; no elimina la fila institucional, el esquema tenant, los datos, los mapas de identidad ni el historial. El estado de ciclo de vida se persiste como atributo `activo` del registro fuente de verdad `control.institucion`; no se reutiliza `mapa_usuario_esquema.activo`, que representa el estado de una asociación usuario-esquema. Una institución desactivada deja de considerarse activa en el panel y no admite operaciones de negocio de sus usuarios locales hasta ser reactivada; el acceso Superadmin al registro y su reactivación permanecen disponibles. En cada resolución de identidad→esquema de Feature 010 se consulta ese estado en control; si `control.institucion.activo` es falso, el correo local no resuelve al tenant, la sesión se deniega y la operación tenant devuelve 401 conforme al patrón de identidad local no resoluble, también para sesiones previamente emitidas.

**Por qué:** el borrado físico contradice la preservación de datos y las reglas de migración/versionado de la Feature 010. El estado en el registro institucional fuente de verdad permite suspender toda la institución sin confundirlo con la habilitación individual de un usuario en el mapa. Este cambio del modelo de control debe justificarse formalmente en `stack.md` antes de planificar la implementación.

### D-3 — Usuario local y Clerk son ciclos de vida distintos

El CRUD local crea, modifica, lista y desactiva registros `usuario` en el tenant, pero no crea ni elimina cuentas Clerk, ni modifica sus credenciales. El alta local vincula un correo que ya exista en Clerk y que no esté asignado a otra identidad local activa; si la identidad no existe, la operación informa el rechazo y no crea un usuario autenticable. Desactivar la asociación local impide que el correo resuelva al tenant, sin borrar la identidad de Clerk.

**Por qué:** Clerk es la única autoridad de autenticación; la fila local representa rol, organización y ámbito de Compustock, no una credencial paralela. El aprovisionamiento de 010 ya establece que el correo administrador debe existir previamente en Clerk.

### D-4 — Ámbito de administración institucional

El Administrador Institucional solo lista o modifica sedes, departamentos y usuarios de su tenant. Las operaciones de sedes/departamentos reutilizan las reglas de integridad de Feature 011: departamentos con una sede para operaciones dependientes y Bodegueros asignados a una sede para operar stock. *(Histórico: la asociación de encargados de departamento, con rol Solicitante, quedó retirada por el Bloque B de la enmienda; ver §10.5.)* La UI no puede convertir estas relaciones en privilegios adicionales.

**Por qué:** la resolución de tenant de Feature 010 es exclusiva del correo verificado y la Feature 011 definió las precondiciones organizacionales. *(Histórico: la semántica de encargado pertenece a la 011 y se retira con el Bloque B.)*

### D-5 — Panel global con atribución y completitud

El dashboard del Superadmin presenta las métricas agrupadas por institución: cantidad de instituciones activas, sedes por institución y conteos de usuarios por cada rol por institución. Cada fila o valor desglosado identifica inequívocamente la institución. Las instituciones desactivadas se excluyen de la cantidad de activas, pero se listan identificadas con estado inactivo y sin atribuirles métricas operativas actuales; no provocan por sí solas un fallo del agregado. Solo las instituciones activas son requeridas para el agregado; una activa inaccesible o incompatible causa error completo, no parcial.

**Por qué:** las lecturas globales de 010 exigen atribución institucional y fallar completas para evitar métricas engañosas.

### D-6 — Funciones activas por institución

Cada institución tiene un conjunto individual de capacidades funcionales habilitadas o deshabilitadas, administrado por Superadmin y consultable desde su panel. La fuente de verdad se persiste explícitamente en el esquema `control`, separada de los catálogos y datos operativos tenant. Se elige una estructura auxiliar `funcion_institucion` con una fila por par institución-capacidad, identificador estable de capacidad, estado habilitado y referencia a la institución de control; la clave del par impide duplicados. El conjunto cerrado de identificadores es: `catalogo` (consulta/gestión del catálogo institucional), `inventario` (existencias y movimientos), `tickets` (creación y gestión del flujo de tickets), `kanban` (tablero operativo de tickets), `dashboard` (dashboard analítico del tenant) y `gestion_organizacional` (sedes, departamentos y usuarios; las rutas de encargados se retiran en el Bloque B). No se crea una tabla o catálogo administrable de capacidades: la tabla auxiliar persiste el estado de cada identificador para cada institución.

La desactivación de una capacidad funcional por tenant es una bandera de disponibilidad, no un permiso de usuario ni una capacidad de rol. Al deshabilitarse, la función deja de estar disponible para usuarios de esa institución tanto en navegación como en operaciones backend asociadas; el backend aplica este gating como condición adicional a la matriz central de permisos y responde 403 sin mutar datos, incluso ante invocación directa de la API. La matriz central no cambia y su denegación por rol sigue siendo 403. La activación o desactivación no elimina datos ni historial. No se infiere el estado a partir de actividad, datos presentes, roles ni funciones globalmente disponibles.

**Por qué:** una fila explícita por institución y capacidad permite administrar de forma inequívoca la disponibilidad por tenant, evita deducirla de datos incidentales y separa configuración SaaS de la autorización por rol y del contenido operativo. Es una estructura auxiliar nueva en `control`, no una entidad de dominio tenant; su incorporación requiere justificación y aprobación formal en `stack.md` antes de implementar, por el cambio al modelo/DDL de control.

### D-7 — Contratos administrativos y denegación segura

Toda operación administrativa de API conserva autenticación Clerk y autorización en servidor mediante la matriz central; los guards de Angular son navegación y no autorización. Una sesión ausente/inválida o identidad local que no resuelve —incluida la institución desactivada— devuelve 401; un rol sin permiso o una capacidad funcional por tenant deshabilitada devuelve 403; una entidad inexistente o ajena al tenant 404, un conflicto de estado/asociación 409 y una entrada inválida 422. El gating de capacidad es una condición adicional aplicada en backend, no un cambio de la matriz. Las rutas exitosas publican contrato explícito y las mutaciones no aceptan del cliente el esquema tenant como autoridad.

**Por qué:** es el patrón normativo de autorización y routing de las Features 007 y 010, además de los códigos establecidos en la 011.

## 5. Reglas del flujo

1. Clerk autentica al usuario y el correo primario verificado resuelve su identidad local y ámbito conforme a Feature 010. El cliente no elige institución ni esquema.
2. Superadmin accede a `/control`; el portal muestra el dashboard SaaS y las funciones de institución. La navegación no muestra `/tickets` y su guard de ruta excluye a Superadmin; la matriz central de permisos backend permanece sin cambios por esta decisión de UI. `/tickets` y el Kanban siguen disponibles para los roles de negocio autorizados.
3. El Superadmin crea una institución usando el aprovisionamiento de Feature 010, consulta y modifica sus atributos canónicos, y puede desactivarla o reactivarla sin borrar sus datos.
4. El estado de institución se determina por `control.institucion.activo`; la resolución de identidad de Feature 010 consulta ese estado antes de seleccionar esquema. Si es falso, el correo local no resuelve y la API responde 401; la versión del tenant solo se evalúa para instituciones activas. La reactivación vuelve a permitir routing si la versión es la objetivo.
5. Superadmin consulta y modifica las seis capacidades funcionales enumeradas en D-6 por institución. Una capacidad deshabilitada no aparece como disponible en la UI y las operaciones backend asociadas responden 403 sin mutación; habilitarla restaura la disponibilidad conforme al rol del usuario.
6. El dashboard global cuenta solo instituciones activas en el indicador de activas. Lista también las desactivadas con estado, excluidas de métricas actuales de sedes/usuarios; solo una falla de institución activa requerida produce error explícito, nunca un resultado parcial.
7. Administrador Institucional usa la sección administrativa de su tenant para crear/consultar/modificar/desactivar sedes, departamentos y usuarios; gestiona las asociaciones de encargados previstas por la Feature 011.
8. La desactivación de sedes, departamentos o usuarios no borra historial referencial ni permite dejar operaciones dependientes en un estado silenciosamente válido. Si una entidad tiene dependencias incompatibles, la operación se rechaza con conflicto y explica qué debe resolverse.
9. El alta de usuario local requiere identidad Clerk preexistente; la edición local no cambia credenciales ni identidad de Clerk. La desactivación local impide resolver el usuario local.
10. Las reglas de sede obligatorias de departamentos y Bodegueros para operaciones dependientes siguen respondiendo 409 cuando falta una asignación, sin sede por defecto.
11. Los intentos de acceso cross-tenant no revelan existencia de entidades y no producen lecturas ni mutaciones cruzadas.

## 6. Criterios de aceptación

- **AC-1 — CRUD administrativo institucional.** DADO un Superadmin autenticado, CUANDO crea, consulta o modifica el registro de una institución, ENTONCES el registro canónico se mantiene en control y solo `institucion_id` y `nombre` se reflejan en la fila espejo tenant; cualquier otro atributo permanece en control y no se copia ni causa rechazo por falta de espejo. La respuesta indica el estado persistido; identidad sin sesión devuelve 401 y cualquier rol distinto de Superadmin devuelve 403.
  - **Evidencia:** `backend/tests/funcional/integracion/test_espejo_institucion_012.py` (`test_espejo_institucion_tiene_exactamente_dos_columnas`, `test_espejo_institucion_no_expone_activo`, `test_canonico_control_declara_institucion_con_activo`); `backend/tests/funcional/integracion/test_contrato_control_012.py` (OpenAPI/401/403/response_model de las 7 rutas `/control`); gated `backend/tests/funcional/sistema/test_gestion_administrativa_postgres_012.py::test_espejo_tenant_solo_tiene_dos_columnas_y_no_capacidades` y `::test_migracion_012_transiciona_una_instalacion_011_1_preservando_datos`; frontend `frontend/src/app/features/control/instituciones.component.spec.ts` (casos `AC-1: …`) y `features/control/services/control.service.spec.ts` (`edita una institución con PUT y solo los atributos canónicos`). Recorrido 4200: `evidencia/README.md` (edición de INST-004 persistida en `control.institucion` y espejo de dos columnas, capturas `04`, `05`). **Nota:** la sincronización real del espejo al editar se observa por la ruta HTTP en el recorrido 4200; no existe una prueba HTTP SQLite dedicada de `editar_institucion` (solo OpenAPI + metadata + migración gated).
- **AC-2 — Desactivación y reactivación de institución.** DADO una institución operativa con usuarios y datos, CUANDO Superadmin la desactiva, ENTONCES `control.institucion.activo` queda falso y permanecen registro, tenant, datos, mapas e historial; la institución deja de contarse como activa y sus identidades locales no resuelven a esquema: la API tenant responde 401, incluso con sesión Clerk previamente emitida. CUANDO la reactiva, ENTONCES el routing vuelve a funcionar si la versión tenant es la objetivo, sin recrear ni duplicar datos.
  - **Evidencia:** `backend/tests/no_funcional/seguridad/test_institucion_inactiva_012.py` (`test_institucion_inactiva_no_resuelve_tenant`, `test_contexto_solicitud_deniega_institucion_inactiva`, `test_http_institucion_inactiva_responde_401`, `test_http_institucion_activa_responde_200`); gated `backend/tests/funcional/sistema/test_gestion_administrativa_http_postgres_012.py::test_institucion_inactiva_deniega_401_y_reactivacion_restaura`; frontend `frontend/src/app/features/control/instituciones.component.spec.ts` (casos `AC-2: desactivar exige confirmación…`, `…reactivar persiste el estado con PATCH { activo: true }`). Recorrido 4200: `evidencia/README.md` (desactivar/reactivar INST-002 con datos intactos, captura `17`; `/auth/me` + `/organizacion/sedes` + `/usuarios/` 401 con sesión Clerk vigente → 200 tras reactivar). Recorrido 8080: estado activo/inactivo en `8080-05-control-dashboard.png`.
- **AC-3 — Navegación administrativa del Superadmin.** DADO un Superadmin autenticado, CUANDO observa la navegación, ENTONCES no aparece enlace a `/tickets`; si navega directamente a `/tickets`, el guard lo redirige a `/acceso-denegado` y no se renderiza el Kanban operativo. `/control` renderiza la vista administrativa SaaS. DADO un Administrador, Bodeguero o Solicitante permitido por la configuración vigente, CUANDO navega a `/tickets`, ENTONCES la ruta y el Kanban siguen disponibles. Este cambio es exclusivamente de navegación/UI: no modifica la matriz central del backend. Los roles de negocio no acceden a las vistas protegidas de control.
  - **Evidencia:** frontend `frontend/src/app/core/auth/roles.spec.ts` (`los roles con acceso a /tickets excluyen solo al Superadmin`, `puedeVerTickets concede a los roles de negocio y nunca al Superadmin`); `frontend/src/app/app.routes.spec.ts` (`excluye solo al Superadmin de /tickets y conserva a los roles de negocio`); `frontend/src/app/core/guards/role.guard.spec.ts` (`con ROLES_TICKETS deniega al Superadmin y conserva a los roles de negocio`); `frontend/src/app/core/guards/tickets-acceso.spec.ts` (`redirige al Superadmin a /acceso-denegado y no renderiza el Kanban`); `frontend/src/app/app.component.spec.ts` (`oculta el enlace de tickets y expone Dashboard SaaS/Instituciones al Superadmin`). Recorrido 4200: `evidencia/README.md` (nav de Superadmin sin `/tickets`, `/tickets` directo → `/acceso-denegado`, captura `07`; `/tickets` accesible para el Administrador, captura `16`). Recorrido 8080: `8080-05-control-dashboard.png` (nav sin Tickets) y guard verificado. Matriz backend intacta por `backend/tests/no_funcional/seguridad/test_permisos_012.py`.
- **AC-4 — Métricas institucionales globales.** DADO al menos dos instituciones con nombres repetidos y datos operativos, CUANDO Superadmin consulta el dashboard, ENTONCES observa el conteo de activas y métricas de sedes/usuarios por institución activa, con atribución inequívoca y sin fusionar homónimos. Las instituciones desactivadas aparecen identificadas como inactivas, quedan excluidas del conteo de activas y de las métricas actuales, y no provocan fallo. Una institución activa requerida inaccesible o incompatible causa error explícito sin presentar agregado parcial.
  - **Evidencia:** gated `backend/tests/funcional/sistema/test_gestion_administrativa_http_postgres_012.py::test_dashboard_saas_homonimos_e_inactiva_sin_metricas` y `::test_dashboard_saas_activa_incompatible_falla_completo`; frontend `frontend/src/app/features/control/dashboard-saas.component.spec.ts` (6 casos `AC-4: …`: KPI de activas, atribución nombre+id, inactiva sin métricas, error recuperable, vacío) y `features/control/services/control.service.spec.ts` (`consulta el dashboard SaaS con GET /control/dashboard`). Recorrido 4200: `evidencia/README.md` (Dashboard SaaS con 4 activas, atribución por institución, captura `03`). Recorrido 8080: `8080-05-control-dashboard.png`.
- **AC-5 — Capacidades funcionales por institución.** DADO una institución y los identificadores cerrados `catalogo`, `inventario`, `tickets`, `kanban`, `dashboard` y `gestion_organizacional`, CUANDO Superadmin consulta, habilita o deshabilita una capacidad, ENTONCES el estado queda persistido en control y se muestra en la vista administrativa. Si se deshabilita, usuarios del tenant no ven la función como disponible y las operaciones backend asociadas responden 403 sin mutación; si se habilita, vuelve a estar disponible solo para roles autorizados por la matriz. Este gating backend es adicional a la matriz central y no la modifica; tampoco se eliminan datos al deshabilitar.
  - **Evidencia:** `backend/tests/no_funcional/seguridad/test_capacidades_gating_012.py` (`test_mapa_central_cubre_las_operaciones_asociadas`, `test_conjunto_cerrado_de_capacidades`, `test_capacidad_apagada_responde_403`, `test_capacidad_encendida_no_bloquea`); `backend/tests/no_funcional/seguridad/test_gating_capacidades_endpoints_012.py` (gating E2E: `test_catalogo_apagado_bloquea_lectura_y_escritura_sin_mutar`, `test_capacidad_apagada_deniega_adicionalmente_al_rol_autorizado`, `test_capacidad_habilitada_no_concede_permiso_de_rol`, `test_gestion_organizacional_apagada_no_crea_sede`); gated `backend/tests/funcional/sistema/test_gestion_administrativa_http_postgres_012.py::test_gating_capacidad_catalogo_403_y_habilitada_restaura` y `::test_gating_gestion_organizacional_403_sin_mutar_y_habilitada_crea`; frontend `frontend/src/app/features/control/capacidades.component.spec.ts` (6 casos `AC-5: …`) y `features/control/services/control.service.spec.ts` (`actualiza una capacidad con PUT …`). Recorrido 4200: `evidencia/README.md` (las 6 capacidades, `kanban` apagada → `PATCH /tickets/1/estado` **403** sin mutación, re-habilitada, captura `06`).
- **AC-6 — UI de sedes.** DADO un Administrador Institucional, CUANDO abre la vista de sedes, ENTONCES la vista se renderiza con lista y formulario observables y muestra estado activo/inactivo por sede. `ng test` incluye pruebas de renderizado y estados de esta vista. Las lecturas y escrituras respetan el contrato, errores y aislamiento ya establecidos por Feature 011. La sede “Sede Central” de tenants nuevos se conserva y no se duplica por apertura de la UI.
  - **Evidencia:** `backend/tests/funcional/integracion/test_organizacion_crud_012.py` (`test_listar_sedes_expone_estado_activo`, `test_crear_sede_responde_201_y_persiste`, `test_crear_sede_duplicada_responde_409_sin_crear`, `test_editar_sede_actualiza_y_sede_ajena_responde_404`); gated `backend/tests/funcional/sistema/test_gestion_administrativa_http_postgres_012.py::test_sede_ajena_se_oculta_404_y_no_aparece_en_el_listado`; frontend `frontend/src/app/features/administracion/sedes.component.spec.ts` (10 casos, `AC-6`/`AC-6/AC-11`). Recorrido 4200: `evidencia/README.md` (lista con estado; `Sede QA 012` creada y editada, capturas `09`, `10`). Conservación de “Sede Central” cubierta por la suite de aprovisionamiento de la 011 (`test_control_sede_011.py`).
- **AC-7 — UI de departamentos y asignación de sede.** DADO un Administrador Institucional, CUANDO abre la vista de departamentos, ENTONCES se renderiza la lista/formulario y se muestra la sede asignada o la ausencia de asignación; `ng test` verifica renderizado y visualización. La UI consume las reglas de Feature 011 sin duplicar su contrato API; una sede ajena no se ofrece como opción.
  - **Evidencia:** `backend/tests/funcional/integracion/test_organizacion_crud_012.py` (`test_listar_departamentos_solo_del_tenant`, `test_crear_y_editar_departamento`, `test_editar_departamento_ajeno_responde_404`); frontend `frontend/src/app/features/administracion/departamentos.component.spec.ts` (7 casos, `AC-7`: sede asignada/ausencia, crear con POST, asignar sede limitada al tenant). Recorrido 4200: `evidencia/README.md` (lista con sede o "Sin sede asignada"; `Depto QA 012` creado y sede asignada, captura `13`).
- **AC-8 — UI de usuarios locales vinculados a Clerk.** DADO un Administrador Institucional, CUANDO abre la vista de usuarios, ENTONCES se renderiza el listado/formulario con rol, sede/departamento aplicables y estado activo/inactivo; `ng test` verifica renderizado y los estados. El alta y edición consumen las reglas de vinculación local con Clerk de Feature 011/contrato vigente, sin crear ni modificar identidades Clerk.
  - **Evidencia:** `backend/tests/funcional/integracion/test_organizacion_crud_012.py` (`test_editar_usuario_actualiza_atributos`, `test_alta_usuario_con_correo_inexistente_en_clerk_responde_422`, `test_alta_usuario_con_correo_existente_en_clerk_responde_201`, `test_listado_usuarios_publica_estado_y_sede`, `test_listado_usuarios_refleja_el_mapa_inactivo`); gated `backend/tests/funcional/sistema/test_gestion_administrativa_http_postgres_012.py::test_listado_usuarios_publica_estado_y_sede_desde_el_tenant`, `::test_alta_usuario_por_admin_de_tenant_persiste_en_su_esquema` y `::test_auth_me_resuelve_identidad_de_tenant` (regresión); frontend `frontend/src/app/features/administracion/usuarios.component.spec.ts` (13 casos, `AC-8`). Recorrido 4200: `evidencia/README.md` (lista con rol/departamento/estado reales, edición sin correo, captura `14`; corrección post-T13 de alta con formulario). **Ajuste post-cierre (21/Oct/2026):** el combo de rol de la edición usa `rolesEdicion` (misma regla `puedeAsignarRol` que el alta, conservando visible el rol actual no asignable y excluyendo `Superadmin` por ser identidad de control), verificado por `AC-8/AC-10: el combo de rol de la edición no ofrece Superadmin a un Administrador`, `AC-8/AC-10: al editar un Administrador se conserva visible su rol actual, sin Superadmin` y `AC-8/AC-10: la edición institucional nunca ofrece Superadmin, ni con identidad Superadmin`.
- **AC-9 — Asignación de Bodeguero y sede.** DADO un Administrador Institucional, CUANDO visualiza o edita la sede de un usuario Bodeguero, ENTONCES la UI muestra la asignación vigente o su ausencia y limita opciones a sedes del tenant; el backend conserva el 409 de Feature 011 si una identidad sin sede intenta operar stock.
  - **Evidencia:** `backend/tests/funcional/integracion/test_organizacion_crud_012.py` (`test_editar_usuario_actualiza_atributos`); el 409 de stock sin sede se conserva por la suite de la 011 (`backend/tests/funcional/integracion/test_organizacion_011.py`). Frontend `frontend/src/app/features/administracion/usuarios.component.spec.ts` (`AC-9: asigna sede a un Bodeguero con opciones limitadas al tenant`, `AC-9: el alta de un Bodeguero con sede la asigna tras crear`). Recorrido 4200: `evidencia/README.md` (rol Bodeguero → "Sin sede" → asignar `Sede 2` → `usuario.sede_id=2`).
- **AC-10 — Encargados de departamento.** DADO un departamento, CUANDO el Administrador Institucional abre su gestión de encargados, ENTONCES la UI muestra asociaciones existentes y permite seleccionar usuarios Solicitantes del mismo departamento; `ng test` verifica renderizado y estado vacío/asociado. Las reglas y respuestas API son las de Feature 011; el rol y los permisos del usuario no cambian.
  - **Evidencia:** API/reglas de encargados son de Feature 011 (`backend/tests/funcional/integracion/test_organizacion_011.py`); la 012 aporta la vista: `frontend/src/app/features/administracion/encargados.component.spec.ts` (6 casos, `AC-10`: listado de existentes, estado vacío, candidatos = Solicitantes del mismo departamento no asociados, asociar con POST, retirar con DELETE). Recorrido 4200: `evidencia/README.md` (estado vacío → asociar `Felipe Soto` → retirar, captura `15`). Recorrido 8080: `8080-04-admin-encargados.png`. **Nota:** la 012 no añade operaciones backend de encargados; no hay test backend nuevo para AC-10.
- **AC-11 — Desactivación de objetos organizacionales.** DADO una sede, departamento o usuario referenciado, CUANDO la entidad puede desactivarse preservando referencias y sin dejar inválidas operaciones existentes, ENTONCES se conserva la entidad y sus referencias históricas, queda inactiva y se bloquean usos futuros incompatibles. CUANDO sus dependencias hacen insegura la desactivación sin resolverlas antes, ENTONCES responde 409 con el motivo concreto y no cambia el estado. La UI muestra inequívocamente activo/inactivo y el resultado correspondiente.
  - **Evidencia:** `backend/tests/funcional/integracion/test_organizacion_crud_012.py` (`test_desactivar_sede_sin_dependencias_es_idempotente_y_reactivable`, `test_desactivar_sede_con_dependencias_responde_409`, `test_desactivar_departamento_sin_usuarios_es_idempotente`, `test_desactivar_departamento_con_usuarios_responde_409`, `test_estado_usuario_persiste_en_mapa_y_es_idempotente`, `test_desactivar_usuario_encargado_responde_409`); frontend `frontend/src/app/features/administracion/sedes.component.spec.ts` (`AC-11: …`), `departamentos.component.spec.ts` (`AC-11: …`) y `usuarios.component.spec.ts` (`AC-8/AC-11: un usuario inactivo…`). Recorrido 4200: `evidencia/README.md` (desactivar/reactivar + **409** con motivo de sede y departamento, captura `12`). Recorrido 8080: vistas de administración (`8080-01`…`8080-04`).
- **AC-12 — Aislamiento por tenant.** DADO administradores de dos instituciones y entidades con identificadores coincidentes, CUANDO uno lista, consulta, edita o desactiva un ID perteneciente al otro tenant, ENTONCES no obtiene datos ni modifica registros y recibe 404; no hay filtración mediante búsqueda, formulario, URL o payload.
  - **Evidencia:** `backend/tests/funcional/integracion/test_organizacion_crud_012.py` (`test_editar_sede_actualiza_y_sede_ajena_responde_404`, `test_editar_departamento_ajeno_responde_404`, `test_editar_usuario_ajeno_responde_404`); gated `backend/tests/funcional/sistema/test_gestion_administrativa_http_postgres_012.py::test_sede_ajena_se_oculta_404_y_no_aparece_en_el_listado`; frontend `frontend/src/app/features/administracion/departamentos.component.spec.ts` (`AC-7: … limita las opciones a las sedes del tenant`). Recorrido 4200 API directa: `evidencia/README.md` (`PUT /organizacion/departamentos/1/sede` y `PUT /usuarios/1` de INST-001 con token de INST-002 → **404**).
- **AC-13 — Contrato API y permisos.** DADO cada operación API nueva o protegida por gating de capacidad, CUANDO se inspeccionan respuestas HTTP y `/openapi.json`, ENTONCES toda operación administrativa tiene permiso explícito en la matriz central, `response_model`, código de éxito, errores documentados y autorización servidor-side; identidad ausente/no resoluble devuelve 401, rol sin permiso o capacidad funcional deshabilitada devuelve 403, y aplican 404/409/422 según contrato. El gating no altera la matriz. Las operaciones CRUD de Feature 011 conservan su contrato y no se vuelven a especificar aquí.
  - **Evidencia:** `backend/tests/no_funcional/seguridad/test_permisos_012.py` (`test_baseline_010_tiene_28_operaciones`, `test_matriz_012_transcrita_es_aditiva`, `test_matriz_central_conserva_las_28_operaciones`, `test_matriz_central_es_la_esperada_para_012` —44 operaciones—, `test_operaciones_control_012_son_solo_superadmin`, `test_operaciones_organizacion_012_conservan_sus_roles`); `backend/tests/funcional/integracion/test_contrato_control_012.py` y `backend/tests/funcional/integracion/test_contrato_organizacion_012.py` (OpenAPI: rutas, código de éxito, 401/403/404/409/422, `response_model`, Bearer); `backend/tests/funcional/integracion/test_organizacion_crud_012.py` (`test_matriz_declara_las_operaciones_organizacionales_012`, `test_openapi_publica_las_rutas_organizacionales_012`, `test_organizacion_denegada_a_roles_no_autorizados`, `test_crud_organizacional_sin_sesion_responde_401`); gating adicional a la matriz: `backend/tests/no_funcional/seguridad/test_gating_capacidades_endpoints_012.py::test_capacidad_apagada_deniega_adicionalmente_al_rol_autorizado`. Reconciliación de transcripción ops previas: `test_permisos.py`, `test_permisos_008.py`, `test_permisos_010.py`, `test_permisos_endpoints.py` (35→44). Verificación `/openapi.json` en T12 (44 operaciones con `response_model`/401/403; las 28 previas sin cambios).
- **AC-14 — Cierre de verificación.** DADO que se propone cerrar la feature, CUANDO se revisan las evidencias, ENTONCES pytest y pruebas gated PostgreSQL cubren persistencia/aislamiento/control, `ng test` y build pasan, el flujo se recorre en 4200 con escritura real y en 8080 tras reconstrucción, y cada AC tiene evidencia verificable. Este criterio no añade comportamiento de negocio.
  - **Evidencia:** suites de cierre (T12–T14): `pytest` SQLite **839 passed / 61 skipped / 0 failed**; gated PostgreSQL (`POSTGRES_TEST_URL`, tras la corrección post-T13) **900 passed / 0 skipped / 0 failed**; `ng test` **292 SUCCESS / 0 failed**; `ng build` limpio. Recorrido 4200 con escritura real: `docs/spec/features/012-gestion-administrativa/evidencia/README.md` (capturas `01`–`18`, salvo `11`; base `apt_erp` migrada a **012.1** con respaldo previo). Recorrido 8080 con imagen reconstruida (bundle `main-GAEBNACE.js`): `evidencia/8080-01`…`8080-05`. Cada AC-1…AC-13 enlaza arriba a su test/OpenAPI/recorrido verificable.

### Enmienda T-17 (presentación): pestañas ARIA en administración — 22/Oct/2026

> **Nota de vigencia (27/Nov/2026):** los AC-15…AC-19 describen la enmienda T-17 con
> **4 pestañas** y son **históricos**. El Bloque B retira la pestaña, la ruta y el
> componente de Encargados; la navegación vigente pasa a **3 pestañas** (Sedes,
> Departamentos, Usuarios) y se verifica en AC-38. En particular, la afirmación de AC-18
> «`administracion.routes.ts` no cambia» ya no describe el estado vigente.

#### Problema

La vista administrativa presenta sus cuatro secciones como una barra de enlaces, mientras que inventario ya utiliza semántica ARIA de pestañas. Esta inconsistencia hace menos uniforme la navegación por teclado y la interpretación del área administrativa por lectores de pantalla.

#### Qué cambia

La navegación de administración se presenta como `role="tablist"`; cada sección conserva su enlace real `routerLink` y pasa a `role="tab"`, con `aria-selected` determinado por la ruta activa, `tabindex` 0 para la pestaña activa y -1 para las demás, y navegación con flechas que mueve el foco y sigue la sección correspondiente. El `router-outlet` queda contenido en un panel `role="tabpanel"` cuyo `aria-labelledby` identifica la pestaña activa. La presentación sigue el patrón visual de inventario: pestañas con borde inferior de 2 px, borde azul y texto azul para la activa, y borde transparente y texto gris para las inactivas; se conservan el indicador de foco visible y las clases Tailwind.

#### Qué no cambia

Las rutas hijas de `/administracion` para sedes, departamentos, usuarios y encargados, sus guards, sus deep links y sus destinos `routerLinkActive` (o su equivalente basado en la ruta activa) permanecen intactos. Los enlaces siguen siendo enlaces reales y admiten las acciones de navegador propias, incluido abrir en otra pestaña mediante clic central o menú contextual. No cambian backend, matriz de permisos, modelos, dependencias ni el comportamiento de navegación existente; el cambio se limita a presentación y accesibilidad del frontend.

#### Por qué una enmienda

Es un ajuste de presentación posterior al cierre de la Feature 012, sin nueva capacidad de negocio ni cambio de contrato. Se documenta como enmienda a la feature cerrada, análoga a la enmienda de presentación T17 de la Feature 014, en lugar de abrir una feature independiente.

#### Criterios de aceptación de la enmienda

- **AC-15 — Semántica ARIA y estado activo.** *(Histórico T-17: 4 pestañas; el Bloque B deja 3, ver AC-38.)* DADO el layout de administración, CUANDO se renderiza cualquiera de sus cuatro rutas, ENTONCES la barra declara `role="tablist"`, cada sección declara `role="tab"` y solo la pestaña correspondiente a la ruta activa expone `aria-selected="true"`; las demás exponen `false`.
  - *Evidencia:* `frontend/src/app/features/administracion/administracion-nav.component.spec.ts` — `AC-15: <ruta> deja una sola pestaña seleccionada y tabbable` (un caso por cada una de las cuatro rutas) y `AC-15/AC-18: las cuatro pestañas son anchors reales con su href y sus IDs estables`; `describe('navegación de administración como pestañas ARIA (enmienda T-17)')` sobre el layout real con navegación de `Router`. Recorrido 4200: `evidencia/README.md` §«Enmienda T-17», capturas `19`–`22` (tablist, cuatro `role="tab"`, una sola `aria-selected="true"` por ruta).
- **AC-16 — Teclado y foco.** *(Histórico T-17: wraparound con 4 pestañas; la navegación vigente de 3 se verifica en AC-38.)* DADO el foco dentro de la barra de pestañas, CUANDO se pulsa flecha derecha o izquierda, ENTONCES se activa y recibe el foco la pestaña siguiente o anterior, con recorrido circular; la pestaña activa tiene `tabindex="0"` y las otras `tabindex="-1"`. Los enlaces mantienen su comportamiento nativo de navegación y apertura en pestaña nueva.
  - *Evidencia:* `administracion-nav.component.spec.ts` — `describe('AC-16: flechas con recorrido circular sobre los cuatro destinos')` (8 casos: `ArrowRight`/`ArrowLeft` desde cada uno de los cuatro orígenes, con wraparound Encargados↔Sedes, que afirman `defaultPrevented`, `router.url`, `document.activeElement` y el `href` del destino), `AC-16: Enter, Tab y una letra no se interceptan` y `AC-16/AC-18: tras ArrowRight, ARIA, panel y URL quedan coherentes con el destino` (sin `window.open` ni `target`). Recorrido 4200: `evidencia/README.md` §«Enmienda T-17» (flechas con wraparound, foco en el anchor destino, captura `23`).
- **AC-17 — Panel asociado.** *(Histórico T-17: 4 rutas; el Bloque B deja 3, ver AC-38.)* DADO cualquiera de las cuatro rutas, CUANDO se muestra su vista hija, ENTONCES el contenedor del `router-outlet` tiene `role="tabpanel"` y su `aria-labelledby` apunta al identificador de la pestaña asociada a esa ruta.
  - *Evidencia:* `administracion-nav.component.spec.ts` — `AC-17: el panel de <ruta> se etiqueta con su pestaña activa` (un caso por ruta) y `AC-17: la entrada /administracion redirige a sedes y su panel apunta a esa pestaña`. Recorrido 4200: `evidencia/README.md` §«Enmienda T-17», capturas `19`–`22` y `24` (`role="tabpanel"` con `aria-labelledby="pestana-administracion-<sección>"` en cada deep link y en la redirección).
- **AC-18 — Rutas y regresión funcional.** *(Histórico T-17: el Bloque B retira la ruta de
  encargados; el estado vigente se verifica en AC-38.)* DADO acceso directo por deep link o
  navegación mediante `routerLink`, CUANDO se visita sedes, departamentos, usuarios o
  encargados, ENTONCES se mantienen ruta, guard, vista y destino actuales;
  `administracion.routes.ts` no cambia. Las pruebas existentes de las cuatro vistas y de las
  rutas siguen pasando.
  - *Evidencia:* `administracion-nav.component.spec.ts` — `AC-15/AC-18: las cuatro pestañas son anchors reales con su href y sus IDs estables` y `AC-16/AC-18: tras ArrowRight, ARIA, panel y URL quedan coherentes con el destino`; `git diff` vacío para `administracion.routes.ts` y para los specs heredados (`sedes`, `departamentos`, `usuarios`, `encargados`, `administracion.routes`), que siguen verdes dentro de la suite. Recorrido 4200: `evidencia/README.md` §«Enmienda T-17» (deep links de las cuatro rutas y `/administracion` → `sedes`, capturas `19`–`22` y `24`); humo 8080 con el mismo tablist y navegación (capturas `25`–`28`). En la re-verificación de cierre (22/Oct/2026) las cuatro rutas responden **200** en 4200 y en 8080.
- **AC-19 — Pruebas y verificación visual.** DADO la implementación de la enmienda, CUANDO se ejecutan las pruebas de navegación, ENTONCES verifican estado activo por ruta, semántica ARIA, navegación con flechas y foco; las pruebas existentes de administración continúan en verde. `ng test` y `ng build` pasan, y el flujo se comprueba visualmente y con teclado en 4200. Si la enmienda se cierra con recorrido, se reconstruye el frontend y se hace comprobación de humo en 8080 conforme a AGENTS.md §8.5–§8.6.
  - *Evidencia:* `ng test --watch=false --browsers=ChromeHeadless` (`CHROME_BIN` a Edge) **466 ejecutados: 466 SUCCESS / 0 FAILED** (20 casos de la enmienda + 446 heredados), re-ejecutado en el cierre E17-C1 el 22/Oct/2026; `npx ng build` **limpio** (329.56 kB inicial / 91.66 kB transferido, ~33 s) con bundle `main-KWQKKL6Q.js`. Recorrido visual y de teclado en 4200: `evidencia/README.md` §«Enmienda T-17» (capturas `19`–`24`; consola sin errores salvo el aviso preexistente de claves dev de Clerk). Humo 8080 con imagen reconstruida (`build frontend` + `up -d frontend`, contenedor `healthy`) sirviendo `main-KWQKKL6Q.js` (anterior `main-D6GKPODP.js`): deep links 200, tablist y flechas operativas (capturas `25`–`28`).

## 7. Restricciones

- Clerk continúa siendo la única autoridad de autenticación; no se emiten JWT locales ni se gestionan credenciales Clerk en el CRUD local.
- La identidad global del Superadmin y el registro fuente de verdad de instituciones permanecen en `control`; la fila tenant `institucion` es espejo.
- El estado de institución reside en `control.institucion.activo`; `mapa_usuario_esquema.activo` continúa representando exclusivamente la asociación local usuario-esquema. Su cambio de modelo/DDL requiere justificación formal en `docs/spec/stack.md` antes de implementar.
- El esquema efectivo depende exclusivamente de la resolución confiable de Feature 010. No se acepta el tenant desde parámetros, cabeceras o cuerpo.
- Superadmin no adquiere permisos de escritura de negocio en tenants. Los permisos administrativos nuevos deben limitarse a las operaciones descritas y declararse en la matriz central. Excluir a Superadmin de `/tickets` solo cambia la navegación/UI y no modifica la matriz.
- La autorización real es del backend; la UI/guards no sustituyen la matriz central.
- Los encargados son usuarios Solicitantes del mismo departamento y tenant; ser encargado no agrega privilegios.
- Los departamentos y Bodegueros mantienen las precondiciones operativas de sede de Feature 011; si falta asignación, se conserva el rechazo 409 sin fallback.
- Desactivación no significa borrado físico. Ningún dato histórico de tickets, stock o movimientos se elimina para satisfacer el CRUD.
- La persistencia de capacidades habilitadas por tenant añade la estructura auxiliar `funcion_institucion` en el esquema `control`, con una fila por institución-capacidad y estado explícito. Es un cambio de modelo/DDL que debe justificarse y aprobarse formalmente en `docs/spec/stack.md` antes de implementar; esta spec define la decisión, pero no actualiza `stack.md`.
- Las capacidades constituyen un conjunto pequeño y estable, cerrado y derivado de las funciones del producto; esta feature no incluye planes, cobros ni licenciamiento, y no crea un catálogo de capacidades editable.
- «Capacidad funcional por tenant» es exclusivamente la disponibilidad institucional de una función de producto (`catalogo`, `inventario`, `tickets`, `kanban`, `dashboard`, `gestion_organizacional`); no significa capacidad o permiso de rol. Deshabilitarla impide su uso en ese tenant para cualquier rol mediante 403 adicional a la matriz central; habilitarla no concede permisos que la matriz no otorgue.
- Los identificadores de dominio y de código siguen las convenciones en español de AGENTS.md §6; esta especificación no prescribe nombres de archivos ni arquitectura.

## Enmienda UX posterior al cierre — entrada y navegación del Superadmin

La ruta raíz (`/`) resuelve el destino inicial según el rol local: el Superadmin
entra a `/control/dashboard`, mientras que los roles institucionales conservan
`/dashboard`. El mismo destino se aplica al finalizar el login sin una ruta de
retorno explícita.

El menú lateral global es la única navegación principal del portal SaaS. Expone
`Dashboard SaaS` (`/control/dashboard`) e `Instituciones`
(`/control/instituciones`). La barra interna duplicada del portal de control se
retira; dentro de la vista de instituciones se conserva únicamente la acción
contextual `Nueva institución`, que navega a `/control/alta`.

Esta enmienda no cambia rutas backend, contratos, permisos ni el alcance global
del Superadmin. La autorización continúa en `ControlSuperadminGuard` y en la
matriz central del backend.

## Enmienda funcional posterior al cierre (27/Nov/2026): alta y edición de usuarios según rol

> **Estado de la enmienda:** **cerrada y verificada (27/Nov/2026)**. AC-20…AC-41 quedan
> evidenciados con archivos y métodos reales, conteos de suites, reset, recorridos 4200/8080 y
> grep de coherencia; no reabre el cierre original de la Feature 012 ni retira la evidencia de
> AC-1…AC-19. La **corrección post-validación del 27/Nov/2026** completó el único hueco del
> recorrido manual: el **cambio de rol en ambos sentidos** sobre `Ricardo Nilo` (ver AC-28,
> AC-29 y AC-32).

> **Qué enmienda.** Tiene **dos bloques** sobre el alta y la edición de usuarios y la
> administración institucional. **Bloque A:** para un **Bodeguero**, el Departamento deja
> de elegirse y el servidor resuelve (o crea) el departamento **«Suministros»**, mientras la
> Sede pasa a ser obligatoria en la interfaz y se sigue persistiendo con
> `PUT /organizacion/usuarios/{id}/sede`; para un **Solicitante**, Sede y Departamento quedan
> habilitados, la Sede actúa como filtro de los departamentos y el único dato que viaja al
> backend es `departamento_id`. `departamento_id` pasa a ser **opcional** en
> `UsuarioCrear`/`UsuarioEdicion` y el servicio lo exige (422) para todo rol distinto de
> Bodeguero, incluido el rechazo explícito de «Suministros» para esos roles. **Bloque B:**
> elimina por completo el concepto de **encargado de departamento** y la tabla
> `departamento_encargado` (control y tenant), su semilla, modelo, esquemas, servicios,
> 3 operaciones, vista, ruta, pestaña, tipos y pruebas; conserva la capacidad
> `gestion_organizacional` para sedes, departamentos y usuarios, y retira el 409 de baja de
> usuario por ser encargado. El Bloque B **sí cambia el DDL y la semilla**, deja **25 tablas
> en control / 22 por tenant**, mantiene **21 entidades de dominio** y sube el token a
> **`026.1`**; exige reset (`down -v` + `up -d`) y no hay migración. No cambia el flujo de
> invitación de Clerk de la 017, ni los roles, ni el resto de la matriz de permisos. No se
> crea una Feature 028: es una enmienda a la 012.

### 1. Problema y motivación

**El síntoma reportado.** Al dar de alta un usuario, el formulario pide siempre un
Departamento (con el primero preseleccionado) y solo muestra la Sede cuando el rol es
Bodeguero, como opción **«Sin asignar»**. La expectativa del usuario es la contraria:
para un **Bodeguero** debe habilitarse la **Sede** y no el Departamento; para un
**Solicitante** deben habilitarse **ambos**. En la edición, la Sede ni siquiera aparece:
solo se cambia por la acción separada «Asignar sede».

**Por qué el departamento del Bodeguero no aporta.** El contexto organizacional del
Bodeguero se deriva de `usuario.sede` (la cabecera `/auth/me` le muestra Sede, no
Departamento); su departamento es una columna `NOT NULL` heredada que no participa del
alcance, del stock, del Kanban ni de la autoría de tickets. Hoy la semilla lo deja en
«Biblioteca» (INST-001) y el Administrador debe elegir un departamento que no significa
nada para el rol. En cambio, el Solicitante sí depende de su departamento: la autoría del
ticket y su sede operativa salen de `departamento.sede_id`.

**Tres consecuencias del comportamiento actual.**

1. El alta permite crear un Bodeguero **sin sede** («Sin asignar»), y sus operaciones de
   stock responden 409 hasta que alguien recuerde asignarla por la acción separada.
2. El combo de Departamento del alta y de la edición no se filtra por sede: un Solicitante
   puede quedar en un departamento de otra sede sin que el formulario lo advierta, y la
   Sede no se muestra para revisarlo.
3. El Bodeguero existente conserva un departamento sin significado y la edición de su rol
   no puede corregirlo desde el mismo formulario.

**Base verificada al redactar la enmienda.**

- `usuario.departamento_id` es `NOT NULL`; `usuario.sede_id` es nullable. La institución
  del usuario se deriva hoy de `departamento_id -> departamento.institucion_id`.
- `departamento` tiene `activo` y `sede_id` nullable; la unicidad vigente es
  `(institucion_id, lower(trim(nombre_dep)))`.
- El Bodeguero resuelve su contexto por `usuario.sede`; el Solicitante, por su departamento
  y la sede de ese departamento.
- La semilla tiene un Bodeguero en «Biblioteca» (INST-001) y no crea un departamento
  «Suministros»; si un tenant ya tuviera uno creado a mano, la resolución lo reutiliza
  (D-8).
- El alta actual muestra Departamento siempre y Sede solo para Bodeguero, opcional; la
  edición no muestra Sede.

**Objetivo.**

1. Que el alta y la edición de un **Bodeguero** oculten el Departamento, resuelvan «Suministros»
   en el servidor y exijan una Sede **en la interfaz**, sin crear un segundo flujo de alta; la
   API conserva el alta de dos llamadas y el 409 de stock sin sede.
2. Que el alta y la edición de un **Solicitante** habiliten Sede y Departamento, filtren
   los departamentos por sede y sincronicen la sede con el departamento elegido, sin
   persistir `usuario.sede_id`.
3. Que el contrato deje de exigir `departamento_id` en la entrada y lo valide por rol en
   el servicio, con 422 claro cuando falte para un rol que lo necesita.
4. Conservar sin cambios el flujo de invitación de la 017, los roles, los permisos, el
   modelo de datos salvo el retiro de `departamento_encargado` del Bloque B, las operaciones
   de los dos bloques y la semántica del 409 de stock sin sede.

El Bloque A no requiere DDL, semilla, migración ni reset: «Suministros» es una fila de datos,
no una estructura nueva. El Bloque B sí cambia el DDL y la semilla y exige reset (ver su
sección).

### 2. Decisiones

#### D-8 — «Suministros» es un departamento de asignación automática que resuelve el servidor

El alta y la edición de un usuario con rol `Bodeguero` no reciben un departamento elegido
por el cliente. El servidor resuelve un departamento dedicado llamado exactamente
`Suministros` en la institución del usuario y lo usa como `departamento_id`. Se busca por
nombre normalizado `lower(trim(nombre_dep)) == 'suministros'` dentro de la institución (la
unicidad vigente es `(institucion_id, lower(trim(nombre_dep)))`). Si no existe, se crea con
`descripcion = "Unidad de suministros asignada automáticamente a los Bodegueros"`,
`sede_id = NULL` y `activo = true`. Si existe y está activo, se reutiliza **sin tocar**
nombre, descripción ni sede. Si existe inactivo, se reactiva (`activo = true`) y se
reutiliza. La creación o reactivación y la escritura del usuario ocurren en la **misma
transacción del tenant**: si el alta no confirma el usuario, «Suministros» no queda confirmado.
El `departamento_id` que envíe el cliente para un Bodeguero se ignora en su existencia y
ámbito; el `ge=1` del contrato sí se aplica y un `0` o negativo responde **422**
(D-12/AC-20/AC-23/§4).

El registro que crea esta enmienda **no lleva sede** (`sede_id = NULL`): la sede operativa
del Bodeguero sigue siendo `usuario.sede_id`. Un «Suministros» preexistente creado a mano se
reutiliza tal cual; su `sede_id`, si lo tuviera, no participa de la sede del Bodeguero. La
creación de «Suministros» **no toca el DDL ni la semilla**: la fila nace del uso y no requiere
migración ni reset. El Bloque B sí retira `departamento_encargado` y exige reset (ver su
sección).
La fila aparece en la vista de departamentos como cualquier otra y **no recibe protección
especial**: si se renombra desde el CRUD vigente, la siguiente resolución crea un
«Suministros» nuevo y los Bodegueros existentes no se mueven solos; si se desactiva, el 409 vigente
lo impide mientras tenga usuarios vinculados.

**Por qué:** el departamento es obligatorio en el modelo pero no tiene significado
operativo para el Bodeguero. Una fila dedicada satisface el `NOT NULL` sin inventar un
departamento por usuario ni relajar el DDL, y resolverla en el servidor evita que el
cliente elija un valor que el rol no usa. No migrar los datos existentes conserva el
principio de que cada cambio de usuario pasa por una edición motivada.

#### D-9 — Concurrencia e idempotencia de «Suministros»

Dos altas o ediciones concurrentes que necesiten «Suministros» en una institución que aún no lo
tiene **no pueden duplicarlo ni terminar en 500**. La primera transacción que confirme la
fila gana; la otra detecta el conflicto de unicidad y **relee** la fila confirmada para
reutilizarla dentro de la misma petición, de modo que ambas operaciones terminen con su
usuario creado o editado apuntando al mismo `departamento_id`. Dos reactivaciones
concurrentes son idempotentes. El mecanismo concreto —`begin_nested()`/savepoint o captura
de `IntegrityError` con relectura— se decide en `plan.md`; esta spec exige el resultado.
SQLite serializa y no acredita la carrera: la verificación es PostgreSQL gated.

**Por qué:** el índice único por nombre normalizado ya es la garantía del modelo; el
patrón de pre-check más captura de `IntegrityError` es el que usan la 012 y la 026 para
los conflictos B2. Un 500 por una carrera de dos administradores sería un fallo de
contrato, no un caso de negocio.

#### D-10 — La Sede del Bodeguero es obligatoria y se persiste con `PUT .../sede`

Para el rol Bodeguero, la Sede es **obligatoria** en el alta y en la edición, y el combo
deja de ofrecer «Sin asignar». La obligatoriedad es de la **interfaz**: `UsuarioCrear` y
`UsuarioEdicion` no llevan `sede_id` y el backend no rechaza el `POST` por falta de sede
(la precondición operativa de la 011 sigue siendo un 409 al operar stock sin sede). El alta
sigue siendo de dos llamadas: se crea el usuario y después se persiste la sede con
`PUT /organizacion/usuarios/{id}/sede`. Si la segunda llamada falla, el mensaje sigue
siendo de **éxito parcial** («usuario creado, sede no asignada»), el enlace de invitación
—si vino— se conserva visible y la asignación se puede reintentar con la acción «Asignar
sede» o reabriendo la edición; el alta no se revierte.

En la edición, la Sede forma parte del mismo formulario y, al guardar, se persiste con el
mismo `PUT`. La llamada es idempotente si la sede no cambió; si falla, no revierte la
edición y se informa como éxito parcial de la sede, no como pérdida de los cambios. Si el
tenant no tiene sedes, el formulario no permite guardar un Bodeguero y lo indica.
`PUT .../sede` conserva su contrato: solo Administrador, 409 si el usuario no es Bodeguero,
y sigue fuera del catálogo de motivos (017 D-7).

**Por qué:** el contrato de la 011 no incluye `sede_id` en el alta, y el flujo de dos
llamadas ya es el patrón establecido. Hacerla obligatoria en la interfaz cierra el hueco de
«Bodeguero creado sin sede» sin cambiar la API ni duplicar la asignación dentro de
`POST /usuarios/`. Mantener el PUT fuera de motivos conserva la decisión de la 017.

#### D-11 — En el Solicitante, la Sede es filtro y el Departamento es el dato persistido

Para el rol Solicitante, Sede y Departamento están **habilitados** en el alta y en la
edición. La Sede es un **filtro de la vista**, no un dato persistido: al backend solo viaja
`departamento_id`. Sin filtro se listan los departamentos del tenant; con una sede elegida
se listan solo los departamentos cuyo `sede_id` coincide. Al elegir un departamento, la
Sede se sincroniza a la del departamento (o queda vacía si el departamento no tiene sede).
Al cambiar la sede después de elegir un departamento, una selección que ya no pertenece a
la sede se limpia y el formulario no se envía hasta elegir un departamento válido. En la
edición, la Sede arranca con la sede del departamento actual; en el alta, sin filtro.

Los departamentos sin sede siguen siendo elegibles cuando no hay filtro (criterio vigente);
esta enmienda no cambia la elegibilidad por estado (`activo`). `usuario.sede_id` no se
persiste para el Solicitante y `PUT .../sede` sigue respondiendo **409**: la sede operativa
se deriva de `departamento.sede_id` como hoy.

**Por qué:** el usuario pidió habilitar ambos controles, pero solo el departamento es el
dato que el modelo usa para el Solicitante. Filtrar por sede y sincronizar al elegir el
departamento evita combinaciones contradictorias sin crear una segunda fuente de verdad
para su sede.

#### D-12 — `departamento_id` opcional en la entrada y validado por rol en el servicio

`departamento_id` pasa a ser **opcional en la entrada** de `UsuarioCrear` y `UsuarioEdicion`
(valor por defecto `None`), con `ge=1` cuando venga. `UsuarioBase` y `UsuarioRespuesta`
**conservan `departamento_id` obligatorio**; la opcionalidad se declara sobrescribiendo el
campo **solo en `UsuarioCrear`**, y `UsuarioEdicion` ya es independiente. `UsuarioRespuesta`
no cambia de forma y sigue publicando el `departamento_id` real persistido (el de
«Suministros» para un Bodeguero). La columna `usuario.departamento_id` sigue `NOT NULL`.

La validación de presencia es del **servicio**, no del DTO, porque el nombre del rol se
resuelve contra la tabla `rol`: para un rol distinto de Bodeguero, un `departamento_id`
ausente o `null` responde **422** con un `detail` claro (por ejemplo, «El departamento es
obligatorio para el rol indicado») y sin mutación. Para Bodeguero, el campo puede omitirse y
**cualquier id positivo se ignora** (aunque sea ajeno o inexistente) porque el servidor
resuelve «Suministros»; un `0` o negativo responde **422 para todos los roles** por el
`ge=1` del contrato. Para un rol distinto de Bodeguero, `0` o negativo también es **422**,
un departamento de otra institución conserva el 403/404 vigente y un departamento del ámbito
llamado «Suministros» responde **422** con un `detail` claro y sin mutación; un departamento
ajeno conserva el 403/404 sin revelar su nombre. La precedencia existente 401 → 403 (rol no
asignable) se mantiene; los 409/422/503 del alta con invitación de la 017 no cambian.

La ruta de control de Administradores usa los mismos DTO: su formulario sigue enviando el
departamento y un cliente que lo omita recibe 422; la vista de control no cambia.
`/openapi.json` publica el campo como opcional en la entrada y documenta el 422 por rol.
El Bloque A no agrega ni quita operaciones; el Bloque B retira las 3 rutas de encargados y
deja la matriz en **72** operaciones v1 y OpenAPI en **74** totales = 72 v1 + `GET /` +
`/health` (AC-35).

**Por qué:** el campo no puede ser obligatorio para todos porque el Bodeguero puede omitirlo,
pero cuando viene `ge=1` se aplica a todos; el nombre del rol solo se conoce en el servicio;
y mantener el `departamento_id` real en la respuesta preserva el listado y la edición sin
inventar un campo nuevo.

#### D-13 — Edición por rol: resolución, cambio efectivo y motivo D-5

La edición se resuelve por rol:

- **Bodeguero:** Departamento deshabilitado; al guardar se resuelve «Suministros». Si el
  departamento persistido no es «Suministros», el cambio es **efectivo** y exige motivo del
  catálogo D-5 (017 D-7); el formulario lo refleja antes de enviar y, si el backend
  responde 422 por motivo, no se llama a la sede. La Sede es editable y obligatoria y se
  persiste como en D-10.
- **Cambio de rol a Bodeguero:** se aplica lo anterior; el cambio de rol y de departamento
  es efectivo y exige motivo.
- **Cambio desde Bodeguero a Solicitante:** Departamento habilitado y
  obligatorio; debe elegirse uno distinto de «Suministros» (la vista no lo ofrece); **no** se
  llama a `PUT .../sede`; si el usuario tenía `usuario.sede_id`, la columna no se limpia
  (no participa del contexto del nuevo rol y la vista no la muestra). Limpiarla exigiría
  cambiar el contrato de `PUT .../sede` y queda fuera de esta enmienda.
- **Solicitante:** Sede y Departamento como en D-11; departamento obligatorio; cambio
  efectivo si cambia.
- **Administrador y Superadmin:** sin cambios (D-14).

El orden es: primero `PUT /api/v1/usuarios/{id}` (con motivo si hay cambio efectivo) y
después `PUT /organizacion/usuarios/{id}/sede` si corresponde. Si el primero falla, no hay
cambios ni segunda llamada. Si el primero confirma y el segundo falla, el mensaje es de
éxito parcial («cambios guardados, sede no actualizada») y la asignación se puede
reintentar. Una edición sin cambio efectivo —incluido un Bodeguero que ya está en «Suministros»
y no cambia nada más— no exige motivo ni genera registro, conforme a 017 D-7.

El cambio de rol **no consulta encargados**: con la eliminación de `departamento_encargado`
(Bloque B) no hay asociación que bloquee ni que retirar. La edición solo evalúa las reglas de
rol, departamento, sede y último Administrador activo; el cambio de rol del último
Administrador activo conserva su 409.

**Por qué:** un solo formulario y un solo guardado evitan que la sede y el departamento se
persistan por caminos distintos; el backend sigue siendo la autoridad del cambio efectivo;
y el motivo protege la reasignación organizacional, que es exactamente lo que la 017 quiso
justificar.

#### D-14 — La matriz de campos por rol es normativa y no reabre roles ni control

La matriz de la sección 5 reemplaza la descripción genérica de AC-8/AC-9 para el alta y la
edición de usuarios. **Administrador y Superadmin no cambian**: Departamento habilitado y
obligatorio, Sede no se muestra. Los roles asignables y la vista de control de
Administradores de la 017 quedan intactos; el Bloque B solo retira las 3 operaciones de
encargados de la matriz. En la vista
institucional el rol Superadmin no se ofrece (017 AC-9); su fila de la matriz describe el
comportamiento del mismo DTO cuando lo usa la ruta de control, no una opción nueva.

**Por qué:** la enmienda es sobre los campos organizacionales de dos roles; ampliar el
alcance a los roles administrativos o al portal de control introduciría cambios de 017 que
nadie pidió.

#### D-15 — Legacy y efectos observables

Los Bodegueros existentes (por ejemplo, el de la semilla en «Biblioteca») **conservan su
departamento hasta que se editen**. No se migran datos de Bodegueros por script y el Bloque A
no toca la semilla: el primer guardado de una edición de ese Bodeguero resuelve «Suministros»,
lo que constituye un cambio efectivo y exige motivo. El alta de un Bodeguero siempre termina
en «Suministros».

El conteo de departamentos por institución (dashboard SaaS de la 017 y cualquier conteo que
derive de la tabla) **aumenta en uno** la primera vez que se crea «Suministros» en un tenant.
Es un efecto esperado y debe quedar documentado en la evidencia; no es una regresión. El
Bloque A no cambia el resto de métricas, el token ni los conteos; el Bloque B deja el token
en **`026.1`**, las tablas en **25/22** y las entidades en **21**, y exige reset.

**Por qué:** mover los datos existentes por script contradeciría la regla de que cada
cambio de usuario pasa por una edición motivada y haría que el motivo no refleje el cambio
real. Documentar el conteo evita que QA lo interprete como un defecto.

### 3. Reglas del flujo

1. El Administrador abre el alta. El rol elegido determina los controles y validadores
   según la matriz de la sección 5; cambiarlo recalcula los controles y no conserva una
   selección incompatible.
2. **Alta de Bodeguero:** el formulario exige una Sede y no envía Departamento. La API crea
   el usuario con «Suministros» resuelto y después se asigna la sede con `PUT .../sede`. Si la
   segunda llamada falla, el resultado es de éxito parcial y se puede reintentar.
3. **Alta de Solicitante:** el formulario habilita Sede (filtro) y Departamento
   (obligatorio). Solo viaja `departamento_id`; el usuario se crea sin `usuario.sede_id` y
   su sede operativa se deriva de `departamento.sede_id`.
4. **Alta de Administrador o Superadmin:** sin cambios. No se crea «Suministros».
5. **Edición:** se resuelve por rol según D-13. Para un Bodeguero se resuelve «Suministros»; si
   el departamento cambia, el formulario exige motivo antes de enviar y el backend lo
   vuelve a exigir. Después se persiste la sede si corresponde.
6. **Cambio de rol:** a Bodeguero exige sede y resuelve «Suministros»; desde Bodeguero habilita
   el Departamento, exige uno válido distinto de «Suministros» y no toca la sede. Ambos son
   cambios efectivos y exigen motivo.
7. **Concurrencia:** dos altas o ediciones simultáneas no duplican «Suministros» ni producen
   500; la perdedora relee y reutiliza (D-9).
8. **Permisos y aislamiento:** el Bloque A conserva los roles y la matriz; el Bloque B retira
   solo las 3 rutas de encargados (AC-35);
   «Suministros» se resuelve en la institución del usuario y nunca se reutiliza el de otro
   tenant. `PUT .../sede` sigue siendo solo para Administrador y solo para Bodeguero (409
   en otro caso); el 409 de stock sin sede se conserva.

### 4. Contrato de la API

- **`UsuarioCrear` y `UsuarioEdicion`:** `departamento_id` es opcional (`None` por
  defecto); cuando viene, `ge=1`. `UsuarioBase` y `UsuarioRespuesta` conservan el campo
  obligatorio; la opcionalidad se declara sobrescribiendo el campo **solo en `UsuarioCrear`**,
  y `UsuarioEdicion` es independiente. `UsuarioEdicionConMotivo` y el resto de la 017 no
  cambian de forma.
- **`UsuarioRespuesta`:** sin cambios de forma; publica el `departamento_id` real
  persistido. El `201` del alta y el `200` de la edición devuelven el valor resuelto.
- **Validación por rol (servicio):** el nombre del rol se resuelve contra la tabla `rol`.
  Bodeguero → «Suministros», ignorando cualquier id **positivo** (aunque sea ajeno o
  inexistente); `0` o negativo → **422 para todos**. Cualquier otro rol con el campo ausente o
  `null` → **422** con `detail` claro y sin mutación; para los demás roles, `0`/negativo y
  «Suministros» → **422**, y se conservan las validaciones vigentes de ámbito y existencia del
  departamento.
- **Rutas:** no hay rutas nuevas ni cambios de método o rol. `POST /api/v1/usuarios/`,
  `PUT /api/v1/usuarios/{id}` y `PUT /api/v1/organizacion/usuarios/{id}/sede` conservan sus
  permisos y códigos. La ruta de control de Administradores conserva su formulario y su
  contrato, con la única diferencia de que el campo es opcional en el DTO y su omisión
  responde 422.
- **OpenAPI y matriz:** la entrada publica `departamento_id` como opcional y el 422 por rol
  queda documentado. El Bloque A no agrega ni quita operaciones; el Bloque B retira 3 y deja
  la matriz en **72** operaciones v1 y `/openapi.json` en **74** totales = 72 v1 + `GET /` +
  `/health` (AC-35).
- **Tipos del frontend:** `UsuarioCrear` y `UsuarioEdicion` reflejan la opcionalidad; el
  formulario del Bodeguero omite el campo y el del Solicitante/Administrador lo envía.

### 5. Matriz de campos por rol

| Rol | Alta: Sede | Alta: Departamento | Edición: Sede | Edición: Departamento | Persistencia |
|---|---|---|---|---|---|
| **Bodeguero** | Habilitada y **obligatoria**; sin «Sin asignar» | **Deshabilitado**; muestra «Suministros (asignación automática)» | Habilitada y **obligatoria**; editable en el mismo formulario | **Deshabilitado**; se resuelve «Suministros» al guardar | `usuario.sede_id` vía `PUT .../sede`; `departamento_id` = «Suministros» resuelto por el servidor |
| **Solicitante** | Habilitada como **filtro** (no persistida) | Habilitado y **obligatorio**; filtrado por la sede | Habilitada como **filtro**, inicializada con la sede del departamento actual | Habilitado y **obligatorio**; filtrado; no puede ser «Suministros» | Solo `departamento_id`; la sede se deriva de `departamento.sede_id` |
| **Administrador** | No se muestra | Habilitado y **obligatorio** | No se muestra | Habilitado y **obligatorio** | Sin cambios (control de Administradores de la 017) |
| **Superadmin** | No se muestra; no asignable en la vista institucional | Habilitado y **obligatorio** cuando aplique | No se muestra | Habilitado y **obligatorio** cuando aplique | Sin cambios; el alta de Administradores sigue en `/control` |

La Sede del formulario **nunca** viaja en `UsuarioCrear`/`UsuarioEdicion`: se persiste solo
con `PUT .../sede` y solo para Bodeguero. El Departamento del Bodeguero no se elige: lo
resuelve el servidor. El control deshabilitado del Bodeguero muestra el texto «Suministros
(asignación automática)» sin depender de que el departamento exista todavía en el listado.

### 6. Fuera de alcance

- **Esquema, semilla, versión y reset:** la resolución de «Suministros» del Bloque A es una
  fila de datos y no toca el DDL. El **Bloque B sí retira `departamento_encargado`**: cambia
  `database/01_esquema.sql` y `database/02_datos_semilla.sql`, deja **25 tablas en control**
  y **22 por tenant**, mantiene **21 entidades de dominio** y sube el token a **`026.1`**;
  exige reset (`down -v` + `up -d`) y no hay migración. Queda fuera cualquier otro cambio de
  DDL, semilla, versión o migración.
- **Flujo de invitación de Clerk de la 017:** no cambian el orden validar → invitar →
  tenant → mapa, los estados `pendiente`/`aceptada`/`revocada`/`expirada`, el reenvío, las
  constancias ni los 409/503. Solo cambia el campo organizacional `departamento_id` del
  alta/edición y su validación por rol.
- **Matriz de permisos, roles asignables y guards:** el Bloque B retira las 3 operaciones de
  encargados (matriz 75 → 72; OpenAPI 77 → 74) y conserva los roles y el resto de la matriz;
  no se agregan operaciones ni roles. La autorización sigue siendo la de 007/017.
- **CRUD de departamentos:** no se modifica. «Suministros» no recibe protección especial; puede
  renombrarse o desactivarse según las reglas vigentes (409 si tiene usuarios). Si se
  renombra, la próxima resolución crea un «Suministros» nuevo y no se migran los Bodegueros.
- **Migración de los Bodegueros existentes:** no hay script; conservan su departamento
  hasta que se editen.
- **Comportamiento de Administrador y Superadmin y vista de control de Administradores:**
  sin cambios; no se rediseña el portal `/control`.
- **Listado de usuarios:** no agrega columnas ni la sede derivada del Solicitante; sigue
  mostrando la sede asignada solo del Bodeguero. La sede derivada se ve en `/auth/me`
  (enmienda 008).
- **Flujos de tickets, stock, compras, autoría de tickets, cabecera `/auth/me` y contexto
  organizacional:** sin cambios; la enmienda solo corrige qué campos se piden y en qué
  orden se persisten.
- **Bodeguero / Encargado de Suministros:** no se toca; el Bloque B elimina únicamente el
  **encargado de departamento**, que es una figura distinta.
- **Departamentos inactivos:** no se cambia la elegibilidad por estado; el combo conserva
  el criterio vigente.
- **Features 015 y 016:** siguen fuera; esta enmienda no las adelanta.
- **Una eventual limpieza de `usuario.sede_id` al dejar de ser Bodeguero:** fuera; requiere
  cambiar el contrato de `PUT .../sede` y no tiene efecto operativo hoy.

### 7. Supersesión

Este primer bloque supersede solo los literales siguientes; todo lo demás de la 012, la 017
y la 027 permanece vigente salvo lo que retira el Bloque B.

- **Feature 012, AC-9, literal:** «DADO un Administrador Institucional, CUANDO visualiza o
  edita la sede de un usuario Bodeguero, ENTONCES la UI muestra la asignación vigente o su
  ausencia y limita opciones a sedes del tenant». Queda supersedida la parte «o su ausencia»
  **solo para el alta y la edición**: el formulario exige Sede y no ofrece «Sin asignar»; el
  listado sigue mostrando «Sin sede asignada» para un Bodeguero legacy o un alta con fallo
  parcial. El límite a sedes del tenant y el 409 de stock se conservan.
- **Feature 012, AC-8, literal:** «la vista de usuarios … con rol, sede/departamento
  aplicables». Queda precisada por la matriz de la sección 5: «aplicables» significa Sede
  obligatoria y Departamento deshabilitado para Bodeguero, y Sede como filtro y
  Departamento obligatorio para Solicitante. No se retira el AC.
- **Feature 012, §5 regla 10, literal:** «Las reglas de sede obligatorias de departamentos y
  Bodegueros para operaciones dependientes siguen respondiendo 409 cuando falta una
  asignación, sin sede por defecto». **No se supersede:** el 409 se conserva; la enmienda
  solo evita crear Bodegueros sin sede desde la interfaz.
- **Feature 027, R-4, literal:** «`UsuarioBase`/`UsuarioCrear` aceptan `nombre` y `apellido`
  de hasta 100, `departamento_id >= 1` y `rol_id >= 1`». Queda supersedida la
  **obligatoriedad de `departamento_id` en la entrada**: `UsuarioBase` y `UsuarioRespuesta`
  conservan el campo obligatorio; la opcionalidad se declara sobrescribiendo el campo **solo
  en `UsuarioCrear`**, y `UsuarioEdicion` ya es independiente. El servicio responde 422
  cuando falta para un rol distinto de Bodeguero. Se conserva `ge=1` cuando el campo viene y
  el `NOT NULL` del DDL.
- **Feature 027, Anexo A, fila `UsuarioBase | departamento_id, rol_id | ge=1`:** queda
  precisada en el mismo sentido; `rol_id` no cambia.
- **Feature 027, AC-4, literal:** «`POST/PUT /usuarios/` … rechaza … ids `<1` … con 422».
  Se conserva para un `departamento_id` presente con valor `0` o negativo; se agrega el 422
  por ausencia cuando el rol lo exige. El resto del AC no cambia.
- **Feature 017, D-10, tabla de contratos:** la fila de `POST/PUT` de usuarios conserva
  método, ruta, éxito y errores; solo cambia la forma del DTO de entrada (`departamento_id`
  opcional). El flujo de invitación, los estados y el reenvío no se tocan.
- **Feature 017, D-7, literal:** «La edición exige motivo solo si cambia efectivamente un
  atributo». **No se supersede**; se aplica al nuevo cambio automático de departamento: un
  Bodeguero legacy que pasa a «Suministros» cambia efectivamente y exige motivo. `PUT .../sede`
  sigue fuera del catálogo de motivos.

La 017 **no se reescribe**: su flujo de invitación y sus AC siguen siendo la autoridad. La
027 **no se reescribe**: su validación de longitudes, RUT, `extra="forbid"`, errores de BD
y parser 422 sigue vigente. No se crea una Feature 028.

### 8. Criterios de aceptación

> **Los AC-20…AC-32 están implementados y verificados (27/Nov/2026).** La evidencia cita el
> archivo y método reales, el conteo de la suite y el recorrido observado. La **corrección
> post-validación del 27/Nov/2026** añadió el cambio de rol manual en ambos sentidos
> (AC-28/AC-29/AC-32), que era el único hueco del recorrido.

- [x] **AC-20 — Alta de Bodeguero con «Suministros» y sede obligatoria en la interfaz.** DADO
      un Administrador autenticado en una institución sin departamento «Suministros», CUANDO da
      de alta un usuario con rol Bodeguero, elige una sede y no envía departamento o envía un
      id **positivo** cualquiera (aunque sea ajeno o inexistente), ENTONCES la API responde
      **201**; el usuario queda con `departamento_id` = «Suministros» de su institución y, tras
      la segunda llamada, `sede_id` = la elegida; «Suministros» existe una sola vez, activa, con
      `sede_id = NULL` y la descripción de unidad de suministros asignada automáticamente; el
      departamento enviado por el cliente no se usa. Un `departamento_id` `0` o negativo
      responde **422 para todos los roles** (AC-23). El formulario de alta no ofrece «Sin
      asignar» y no permite enviar un Bodeguero sin sede. SI el tenant no tiene sedes, ENTONCES
      el formulario no permite guardar un Bodeguero y lo indica; no se crea el usuario. SI el
      `PUT .../sede` falla, ENTONCES el usuario existe con «Suministros» y sin sede, el mensaje
      es de éxito parcial, el enlace de invitación se conserva si vino y la asignación se puede
      reintentar sin recrear el usuario; el alta no se revierte.
  - **Evidencia:** **API:** `backend/tests/funcional/integracion/test_alta_suministros_012.py`
    (`test_alta_bodeguero_sin_departamento_resuelve_suministros[None|departamento0]`,
    `test_alta_bodeguero_ignora_cualquier_departamento_positivo[propio|ajeno|inexistente]`,
    `test_departamento_id_no_positivo_responde_422_para_todos[0|-1]`) y
    `tests/funcional/unitarios/test_departamento_suministros_012.py::test_crea_suministros_con_los_valores_de_la_spec`.
    **UI:** `usuarios.component.spec.ts` (`AC-9/AC-20: el alta de un Bodeguero con sede la asigna
    tras crear y omite departamento_id`, `AC-20: si falla la asignación de sede tras el alta…
    informa éxito parcial y conserva el enlace`, `AC-20: sin sedes en el tenant, el alta de
    Bodeguero no se envía y lo indica`, `AC-24: el alta de Bodeguero deshabilita el Departamento
    y exige Sede sin «Sin asignar»`). **4200:** alta de `Bodeguero E12 QA` → **201** y fila
    Bodeguero · Suministros · Sede Maipu (C2). **8080:** la fila real y el formulario con
    Departamento deshabilitado «Suministros (asignación automática)» y `Sede del Bodeguero *` sin
    «Sin asignar» (C3).
- [x] **AC-21 — Ciclo de vida de «Suministros»: creación, reutilización, reactivación y
      renombre.** DADO un departamento «Suministros» activo, CUANDO otra alta o edición de
      Bodeguero lo requiere, ENTONCES se reutiliza sin duplicar y sin modificar su descripción
      ni su sede. DADO un departamento existente con el nombre escrito con mayúsculas o
      espacios exteriores (`" SUMINISTROS "`), CUANDO se resuelve, ENTONCES se reutiliza la
      misma fila por la comparación `lower(trim(nombre_dep)) == 'suministros'`. DADO un
      departamento «Suministros» inactivo, CUANDO una alta o edición de Bodeguero lo requiere,
      ENTONCES se reactiva y se reutiliza en la misma transacción. DADO que el alta falla antes
      de confirmar el usuario (403/409/422/503 de la frontera), ENTONCES no se confirma un
      «Suministros» nuevo. Un «Suministros» preexistente creado a mano se reutiliza tal cual; su
      `sede_id` no participa de la sede del Bodeguero. SI el «Suministros» existente se renombra
      desde el CRUD de departamentos, ENTONCES la siguiente resolución crea una fila nueva
      «Suministros» y los Bodegueros existentes permanecen en el departamento renombrado, sin
      migración automática.
  - **Evidencia:** `test_departamento_suministros_012.py`
    (`test_crea_suministros_con_los_valores_de_la_spec`,
    `test_reutiliza_suministros_activo_sin_tocar_descripcion_ni_sede`,
    `test_encuentra_por_nombre_normalizado_y_conserva_el_nombre[ SUMINISTROS |suministros|SuMiNiStRoS]`,
    `test_reactiva_suministros_inactivo_sin_duplicar_ni_reescribir`,
    `test_no_reutiliza_el_suministros_de_otra_institucion`,
    `test_no_confirma_la_creacion_antes_del_commit_del_llamador`) y
    `test_alta_suministros_012.py` (`test_alta_bodeguero_reutiliza_suministros_activo_sin_modificarlo`,
    `…reutiliza_variantes_normalizadas[…]`, `…reactiva_suministros_inactivo`,
    `test_dos_altas_bodeguero_comparten_un_solo_suministros`,
    `test_alta_fallida_antes_del_commit_no_confirma_suministros`). El **renombre** no tiene test
    dedicado: una fila renombrada deja de coincidir con `lower(trim(nombre_dep)) = 'suministros'`
    y la resolución recorre la misma rama de creación que cubre
    `test_crea_suministros_con_los_valores_de_la_spec`; los Bodegueros existentes no se migran
    (no hay DDL ni script).
- [x] **AC-22 — Concurrencia de dos altas sin duplicar ni 500.** DADA una institución sin
      «Suministros» y dos altas concurrentes de usuarios Bodeguero **distintos**, CUANDO se
      ejecutan, ENTONCES ambas terminan **201**, existe una sola fila «Suministros» y ambos
      usuarios apuntan a ella; ninguna responde 500 y no queda una fila huérfana. La
      verificación es PostgreSQL gated (SQLite no acredita la carrera).
  - **Evidencia:** gated PostgreSQL `tests/funcional/sistema/test_suministros_postgres_012.py`
    (4 casos): `test_dos_altas_concurrentes_responden_201_y_comparten_una_sola_fila`,
    `test_reutilizacion_concurrente_no_duplica_ni_modifica_la_fila`,
    `test_reactivacion_concurrente_es_idempotente` y `test_fallo_local_no_confirma_suministros`
    (dos `TestClient`/sesiones con `Barrier` después del pre-check). SQLite no acredita la
    carrera; el test se omite sin `POSTGRES_TEST_URL` y corrió verde en la suite gated
    (2287 passed / 3 skipped, 27/Nov/2026).
- [x] **AC-23 — Contrato opcional y 422 por rol.** DADO `POST /api/v1/usuarios/` o
      `PUT /api/v1/usuarios/{id}` con `departamento_id` ausente o `null`, CUANDO el rol no
      es Bodeguero, ENTONCES **422** con detalle claro y sin mutación; CUANDO el rol es
      Bodeguero, ENTONCES se acepta y se resuelve «Suministros». Un `departamento_id` `0` o
      negativo responde **422 para todos los roles** por el `ge=1` del contrato; para un rol
      distinto de Bodeguero, un departamento del ámbito llamado «Suministros» responde **422**
      sin mutación. `UsuarioBase` y `UsuarioRespuesta` conservan `departamento_id` obligatorio;
      solo la entrada de `UsuarioCrear` lo hace opcional y `UsuarioEdicion` es independiente.
      `UsuarioRespuesta` publica el `departamento_id` real; `/openapi.json` muestra el campo
      opcional en la entrada y el 422 documentado. La ruta de control de Administradores
      responde 422 si se omite el departamento y no cambia su formulario.
  - **Evidencia:** contrato `tests/funcional/integracion/test_contrato_usuarios_suministros_012.py`
    (8 casos; `test_usuario_crear_hace_opcional_el_departamento_y_la_respuesta_lo_exige`,
    `test_esquema_de_entrada_admite_entero_minimo_1_o_nulo`,
    `test_openapi_publica_el_departamento_opcional_en_las_entradas`,
    `test_openapi_documenta_el_422_por_rol_y_por_suministros`); esquema/`ge=1` en
    `test_departamento_suministros_012.py` (`test_departamento_id_opcional_solo_en_las_entradas`,
    `test_departamento_id_menor_que_uno_responde_422[0|-1]`, `test_la_respuesta_sigue_exigiendo_departamento`,
    `test_usuario_crear_conserva_extra_forbid`); integración 422 sin mutación en
    `test_alta_suministros_012.py::test_alta_no_bodeguero_sin_departamento_responde_422_sin_mutar`,
    `…_con_suministros_responde_422_sin_mutar`, `test_departamento_id_no_positivo_responde_422_para_todos`
    y en `test_edicion_suministros_012.py::test_no_bodeguero_sin_departamento_responde_422_sin_mutar`,
    `test_control_omite_departamento_responde_422_sin_mutar`,
    `test_control_rechaza_suministros_para_administrador_422`. `/openapi.json` en vivo: **74** =
    72 v1 + `GET /` + `/health`.
- [x] **AC-24 — Matriz de campos por rol en la interfaz.** PARA cada rol, CUANDO se abre el
      alta y la edición, ENTONCES los controles se comportan según la sección 5: Bodeguero
      con Sede obligatoria **en la interfaz** y Departamento deshabilitado mostrando
      «Suministros (asignación automática)»; Solicitante con Sede como filtro y Departamento
      obligatorio filtrado y sincronizado; Administrador con Departamento obligatorio y sin
      Sede; Superadmin sin Sede y con Departamento obligatorio solo si el mismo DTO se usa
      desde `/control`, sin ser asignable en la vista institucional. Cambiar el rol recalcula
      controles y validadores y no envía una selección incompatible; la Sede nunca viaja en
      `UsuarioCrear`/`UsuarioEdicion`.
  - **Evidencia:** `usuarios.component.spec.ts` — `AC-24: el alta de Bodeguero deshabilita el
    Departamento y exige Sede sin «Sin asignar»`, `AC-24: cambiar de rol recalcula los controles…`,
    `AC-24/AC-26: el alta de Administrador no muestra Sede…`, `AC-24: al pasar de Administrador a
    Bodeguero la Sede pasa a ser obligatoria`, `AC-24: el alta asocia labels y describe el
    Departamento automático del Bodeguero`, `AC-24: el alta no Bodeguera bloquea el «Suministros»
    heredado y lo indica`, `AC-24/AC-27: un Administrador que pasa a Bodeguero exige sede y el 409
    del último Administrador no llama a la sede` y los dos casos DOM de regresión
    `AC-24/AC-25: elegir Solicitante desde el DOM…` y `AC-29: elegir Solicitante desde el DOM…`
    (rojo con `[value]`, verde con `[ngValue]`). **8080 (C3):** desde el DOM, el alta Bodeguera
    muestra Departamento deshabilitado y Sede obligatoria, y al pasar a Solicitante aparecen Sede
    (filtro) y Departamento habilitado.
- [x] **AC-25 — Alta de Solicitante con filtro y sincronización.** DADO el alta con rol
      Solicitante, CUANDO se elige una sede, ENTONCES el combo de departamentos lista solo
      los departamentos de esa sede; al elegir un departamento la sede se sincroniza; al
      cambiar la sede después, una selección incompatible se limpia y el formulario no se
      envía; el payload lleva solo `departamento_id`; el usuario se crea sin
      `usuario.sede_id`; `/auth/me` deriva su departamento y la sede de ese departamento; y
      `PUT .../sede` responde **409**.
  - **Evidencia:** `usuarios.component.spec.ts` —
    `AC-25: en el alta de Solicitante la Sede filtra los departamentos y se sincroniza`,
    `AC-25: cambiar la Sede limpia un departamento incompatible y no se envía sin departamento`,
    `AC-25: el alta de Solicitante envía solo departamento_id y no llama a la sede`;
    `test_alta_suministros_012.py::test_alta_solicitante_valido_no_crea_suministros`;
    `/auth/me` con la sede del departamento en
    `tests/no_funcional/seguridad/test_auth_me_institucion.py::test_auth_me_solicitante_expone_departamento_y_sede_del_departamento`;
    409 de sede en `test_contrato_usuarios_suministros_012.py::test_put_sede_conserva_el_409_para_no_bodeguero`.
    **4200:** alta de `Solicitante E12 QA` (Maipú → Secretaría/RRHH/Biblioteca; fila Solicitante ·
    Biblioteca, sin sede); **8080 (C3):** el filtro por Maipú devuelve esas tres opciones.
- [x] **AC-26 — Alta de Administrador sin regresión.** DADO el alta o la edición de un
      Administrador (incluido el alta desde `/control`), ENTONCES la Sede no se muestra, el
      Departamento sigue habilitado y obligatorio, el flujo funciona como antes, la vista de
      control no cambia y no se crea «Suministros».
  - **Evidencia:** `usuarios.component.spec.ts` —
    `AC-24/AC-26: el alta de Administrador no muestra Sede, exige Departamento y no ofrece
    «Suministros»` y `AC-26: la edición de un Administrador no muestra Sede y mantiene el
    Departamento obligatorio`; `test_alta_suministros_012.py::test_alta_de_administrador_denegada_no_crea_suministros`;
    `test_edicion_suministros_012.py::test_control_omite_departamento_responde_422_sin_mutar` y
    `test_control_rechaza_suministros_para_administrador_422`. Las suites de `/control`
    (`dashboard-saas`, `instituciones`, `capacidades`, `alta-institucion`,
    `administradores-control`) siguen verdes en `ng test` (671) y la vista de control no cambió.
    **8080 (C3):** el alta de Administrador conserva su formulario (Departamento obligatorio, sin
    Sede) y no crea «Suministros».
- [x] **AC-27 — Edición de Bodeguero legacy.** DADO un Bodeguero con departamento
      «Biblioteca» (semilla), CUANDO el Administrador abre la edición, ENTONCES el
      Departamento se muestra deshabilitado con «Suministros (asignación automática)» y la Sede
      es editable y obligatoria **en la interfaz**; al guardar —aunque no se cambie ningún otro
      campo— se exige motivo del catálogo D-5 porque el departamento cambia; se llama primero a
      `PUT /usuarios/{id}` con el motivo y después a `PUT .../sede` (la segunda llamada es
      idempotente si la sede no cambió); el usuario queda con «Suministros» y con la sede elegida; el listado muestra
      «Suministros» (no «—») tras guardar. SI el segundo PUT falla, ENTONCES los
      cambios del usuario quedan guardados, el mensaje es de éxito parcial y la sede se
      puede reintentar. Una vez que el usuario está en «Suministros», una edición sin cambios no
      exige motivo.
  - **Evidencia:** `test_edicion_suministros_012.py` —
    `test_bodeguero_legacy_pasa_a_suministros_con_motivo`,
    `test_bodeguero_legacy_sin_motivo_responde_422_sin_mutar`,
    `test_bodeguero_ya_en_suministros_sin_cambios_no_exige_motivo`,
    `test_bodeguero_en_suministros_cambio_de_nombre_exige_motivo` y
    `test_editar_ultimo_administrador_a_bodeguero_conserva_409`;
    `usuarios.component.spec.ts` — `AC-27: un Bodeguero legacy en «Biblioteca» exige motivo y
    guarda la sede después del usuario`, `AC-27: …sin cambios no exige motivo`,
    `AC-27: si falla el PUT de sede, los cambios quedan guardados y el mensaje es de éxito
    parcial`, `AC-27: si el PUT del usuario falla, no se llama al PUT de sede`,
    `AC-27: sin sedes en el tenant…` y el de accesibilidad.
    **4200:** `Andres Vargas` (usuario 6) con «Reasignación organizacional» → `PUT /usuarios/6`
    **200** + `PUT /organizacion/usuarios/6/sede` **200**, fila Bodeguero · Suministros · Sede
    Maipu; **8080 (C3):** la fila y el listado muestran Suministros y Sede Maipu.
- [x] **AC-28 — Cambio de rol a Bodeguero.** DADO un Solicitante, CUANDO se cambia su rol a
      Bodeguero, ENTONCES el Departamento se deshabilita, la Sede pasa a ser obligatoria, el
      guardado exige motivo por el cambio de rol y departamento, y el usuario queda en
      «Suministros» con la sede elegida; si el segundo PUT falla, se informa éxito parcial y se
      puede reintentar. El cambio de rol no consulta encargados: no hay asociación que
      bloquee ni que retirar (Bloque B).
  - **Evidencia:** `test_edicion_suministros_012.py` —
    `test_solicitante_a_bodeguero_resuelve_suministros_con_motivo` y
    `test_solicitante_a_bodeguero_sin_motivo_responde_422_sin_mutar`;
    `usuarios.component.spec.ts` — `AC-28: cambiar un Solicitante a Bodeguero deshabilita el
    Departamento y persiste la sede elegida`. La edición no consulta encargados: no queda ruta,
    tabla ni asociación (`test_edicion_de_usuario_no_bloquea_por_encargado`).
    **4200 — corrección post-validación (27/Nov/2026):** `Ricardo Nilo` (id 16) pasó de
    Solicitante a Bodeguero con el Departamento bloqueado en «Suministros (asignación
    automática)», Sede Maipu obligatoria y motivo «Reasignación organizacional»; `PUT
    /api/v1/usuarios/16` **200** y `PUT /api/v1/organizacion/usuarios/16/sede` **200**; la fila
    quedó **Bodeguero · Suministros · Sede Maipu**. Detalle y SQL en `evidencia/README.md`
    §«Corrección post-validación — cambio de rol manual».
- [x] **AC-29 — Cambio de rol desde Bodeguero a Solicitante.** DADO un Bodeguero, CUANDO se
      cambia a Solicitante, ENTONCES el Departamento se habilita y debe elegirse uno válido
      distinto de «Suministros»; el formulario no ofrece «Suministros» ni permite guardar con
      él; no se llama a `PUT .../sede`; el cambio es efectivo y exige motivo; el usuario queda
      con el departamento elegido y su `usuario.sede_id` anterior no se modifica. SI el tenant
      solo tiene «Suministros» como departamento, ENTONCES el cambio no se puede guardar hasta
      crear o elegir otro, y el formulario lo indica. SI un cliente de API envía «Suministros»
      para un rol distinto de Bodeguero, ENTONCES **422** con detalle claro y sin mutación.
  - **Evidencia:** `test_edicion_suministros_012.py` —
    `test_bodeguero_a_solicitante_con_departamento_valido_responde_200`,
    `test_bodeguero_a_solicitante_con_suministros_responde_422_sin_mutar` y
    `test_bodeguero_a_administrador_por_administrador_responde_403_sin_mutar`;
    `usuarios.component.spec.ts` — `AC-29: en la edición del Solicitante la Sede filtra,
    sincroniza y solo viaja departamento_id`, `AC-29: cambiar un Bodeguero a Solicitante no
    ofrece «Suministros» y no toca la sede`, `AC-29: si el tenant solo tiene «Suministros», el
    cambio a Solicitante no se puede guardar y lo indica`, `AC-29: la edición no Bodeguera bloquea
    el «Suministros» heredado` y el caso DOM. **4200 — corrección post-validación (27/Nov/2026):**
    el mismo usuario pasó de Bodeguero a Solicitante con el Departamento habilitado («Selecciona
    un departamento», sin Suministros), Sede como filtro «Todas las sedes» y motivo «Cambio de
    funciones»; `PUT /api/v1/usuarios/16` **200** y **sin** `PUT .../sede`; la fila quedó
    **Solicitante · Biblioteca**, con `usuario.sede_id = 2` residual (la columna no se limpia).
- [x] **AC-30 — Permisos y aislamiento.** DADAS las rutas de alta, edición y sede, CUANDO se
      invocan, ENTONCES conservan sus roles (Administrador; Superadmin 403 en las rutas de
      tenant; `PUT .../sede` solo Administrador); el Bloque A no cambia la matriz ni agrega
      operaciones y el Bloque B la deja en 72 operaciones v1 / 74 OpenAPI (AC-35). «Suministros»
      se resuelve en la institución del usuario; un «Suministros» de otra institución no se
      reutiliza; un usuario ajeno sigue 403/404 y, para un rol distinto de Bodeguero, un
      departamento ajeno conserva el 403/404; para Bodeguero se ignora cualquier id positivo y
      un `0`/negativo responde 422 para todos. El 409 de `PUT .../sede` a no-Bodeguero y el 409
      de stock sin sede se conservan.
  - **Evidencia:** `test_alta_suministros_012.py` —
    `test_alta_no_bodeguero_con_departamento_ajeno_conserva_403_sin_mutar`,
    `test_suministros_se_resuelve_en_la_institucion_del_actor`,
    `test_alta_de_administrador_denegada_no_crea_suministros`; `test_edicion_suministros_012.py` —
    `test_no_bodeguero_con_departamento_ajeno_conserva_403_o_404`,
    `test_editar_usuario_ajeno_responde_404_sin_resolver_suministros`,
    `test_bodeguero_a_administrador_por_administrador_responde_403_sin_mutar`;
    `test_contrato_usuarios_suministros_012.py::test_put_sede_conserva_el_409_para_no_bodeguero`
    y `test_gestion_organizacional_sigue_gateando_las_tres_superficies`; matriz **72**
    (`app/core/permisos.py`) y `/openapi.json` **74**; suites de permisos
    (`test_permisos*.py`, `test_permisos_endpoints.py`) verdes. El 409 de stock sin sede se
    conserva en las suites de inventario/retiro.
- [x] **AC-31 — Pruebas automatizadas.** DADA la implementación, CUANDO se ejecutan las
      suites, ENTONCES `pytest` cubre la resolución crear/reutilizar/reactivar, el contrato
      201/422, la edición con motivo y los permisos; la suite gated PostgreSQL cubre la
      unicidad y la concurrencia de «Suministros»; `ng test` cubre la matriz por rol, el filtro y
      la sincronización del Solicitante, el fallo parcial y la visualización de «Suministros»
      tras guardar. Los conteos quedan registrados en la evidencia.
  - **Evidencia:** **`pytest` SQLite 2163 passed / 127 skipped / 0 failed** (27/Nov/2026);
    **gated PostgreSQL 2287 passed / 3 skipped / 0 failed** (los 3 de Redis sin
    `REDIS_TEST_URL`); **`ng test` 671 SUCCESS / 0 failed** (44 specs) y `ng build` limpio
    (`main-IRJLFDU6.js`). Archivos nuevos del Bloque A:
    `test_departamento_suministros_012.py` (unitaria),
    `test_alta_suministros_012.py`, `test_edicion_suministros_012.py` y
    `test_contrato_usuarios_suministros_012.py` (integración) y
    `test_suministros_postgres_012.py` (sistema, gated). Sin duplicados: la cobertura por rol,
    filtro, sincronización, éxito parcial y «Suministros» tras guardar está en
    `usuarios.component.spec.ts`.
- [x] **AC-32 — Recorrido y cierre.** DADO que se propone cerrar la enmienda, CUANDO se
      revisan las evidencias, ENTONCES 4200 se recorre con escritura real (alta de
      Bodeguero, alta de Solicitante, edición del Bodeguero legacy con motivo, cambio de rol
      en ambos sentidos y el conteo de departamentos +1), 8080 se reconstruye con
      `docker compose -f docker-compose.yml build frontend` + `up -d frontend` y el humo
      confirma las vistas y el flujo; `pytest`, gated PostgreSQL, `ng test` y `ng build`
      están en verde; el Bloque A no cambia el esquema por sí solo y el cierre conjunto
      (retiro de `departamento_encargado`, token `026.1`, 25/22, 21 entidades y reset) se
      verifica en AC-40/AC-41; `evidencia/README.md`, `MEMORY.md` y `roadmap.md` quedan
      sincronizados. Se marcó al observar los resultados (27/Nov/2026).
  - **Evidencia:** **4200 (C2):** escritura real contra PostgreSQL con alta de Bodeguero, alta de
    Solicitante, edición del Bodeguero legacy con motivo, **3 pestañas**, wildcard
    `/administracion/encargados` → `/dashboard` y KPI de departamentos **7 → 8**; SQL verificado
    en `tenant_inst_001_038aa2a9` (15 usuarios, 8 departamentos, Suministros `sede_id NULL`).
    **8080 (C3):** imagen reconstruida, contenedor recreado, bundle `main-IRJLFDU6.js`, 15
    usuarios, Suministros con su descripción, 3 pestañas, wildcard y dashboard con **8**.
    **4200 — corrección post-validación (27/Nov/2026):** sobre `Ricardo Nilo`
    (`ri.nilo@duocuc.cl`, id 16) se recorrió el **cambio de rol en ambos sentidos**. (1)
    Solicitante → Bodeguero: Departamento bloqueado «Suministros (asignación automática)», Sede
    Maipu obligatoria y motivo «Reasignación organizacional»; `PUT /api/v1/usuarios/16` **200** y
    `PUT /api/v1/organizacion/usuarios/16/sede` **200**; fila **Bodeguero · Suministros · Sede
    Maipu** y creación del departamento `Suministros` (KPI **7 → 8**). (2) Bodeguero →
    Solicitante: Departamento habilitado con «Selecciona un departamento» (sin Suministros), Sede
    como filtro «Todas las sedes», se elige Biblioteca y motivo «Cambio de funciones»; `PUT
    /api/v1/usuarios/16` **200** y **sin** `PUT .../sede`; fila **Solicitante · Biblioteca**, sin
    sede visible. **SQL final** (ver `evidencia/README.md`): 13 usuarios, 8 departamentos,
    `Suministros` activo con `sede_id NULL` y 0 usuarios, y Ricardo Nilo Solicitante/Biblioteca
    con `usuario.sede_id = 2` (la columna no se limpia). Suites en verde (AC-31); reset limpio
    (AC-33/AC-34). `evidencia/README.md`, `MEMORY.md` y `roadmap.md` sincronizados en C3.

## Segundo bloque de la enmienda (27/Nov/2026): eliminación del concepto de encargado de departamento

> **Estado del segundo bloque:** **cerrado y verificado (27/Nov/2026)**, dentro de la misma
> enmienda. No crea una
> Feature 028 ni una carpeta nueva. **Sí cambia el DDL y la semilla**, deja **25 tablas en
> `control`** y **22 por tenant**, mantiene **21 entidades de dominio** y sube el token a
> **`026.1`**; exige reset (`down -v` + `up -d`) y no hay migración. No se conserva la
> tabla como histórico ni se archiva.

> **Qué elimina.** El concepto de **encargado de departamento** y todos sus artefactos: la
> tabla `departamento_encargado` en `control` y en el template tenant, sus 5 filas de
> semilla, el modelo y su exportación, los DTO `EncargadoCrear`/`EncargadoRespuesta`, las
> funciones de servicio y las 3 operaciones de API, sus entradas de matriz y de capacidad,
> la vista `Encargados`, su ruta, su pestaña, sus tipos y sus pruebas. La capacidad
> `gestion_organizacional` **se conserva** para sedes, departamentos y usuarios. El rol
> **Bodeguero / Encargado de Suministros** no se toca: la eliminación es solo del
> «encargado de departamento».

### 10.1 Contexto y motivación

La figura de encargado de departamento **no concede permisos ni la usa ningún flujo
operativo**. No participa en tickets, stock, compras, dashboard, autenticación, autorización
ni en la cabecera `/auth/me`; su único efecto funcional era el **409 al desactivar un usuario
que era encargado** y una cuarta vista administrativa que el negocio ya no quiere. El usuario
decidió simplificar y retirarla por completo.

Su retiro también simplifica el esquema: `departamento_encargado` era la única tabla puente
auxiliar del modelo. Al quitarla, el DDL baja a **25/22**, el token sube a **`026.1`** y el
modelo de dominio se mantiene en **21 entidades** (la tabla auxiliar nunca se contó como
entidad). No hay datos de producción que preservar: la base se reconstruye con
`down -v` + `up -d`, según `AGENTS.md` §8.8.

### 10.2 Decisiones del Bloque B

#### D-16 — Retiro completo, sin histórico, sin archivo y sin migración

Se elimina la tabla de `control` y del template tenant, sus constraints, su secuencia, sus 5
filas de semilla, su modelo y exportación, sus DTO, sus funciones de servicio, sus 3 rutas,
sus entradas de matriz y de capacidad, la vista `Encargados`, su ruta, su pestaña, sus tipos
y sus pruebas. No se conserva una tabla de archivo ni un histórico de las asociaciones: los
datos son semilla QA y la base se reconstruye. No se escribe migración; el cambio se aplica
en `01_esquema.sql` y `02_datos_semilla.sql` y se verifica con `down -v` + `up -d`.

**Por qué:** la tabla no tiene atributos propios ni valor de negocio; conservarla como
histórico mantendría vivo el concepto que se retira y obligaría a que modelo, DDL,
documentación y pruebas siguieran mencionándolo. La reconstrucción es el procedimiento
vigente del proyecto y no hay datos que migrar.

#### D-17 — `gestion_organizacional` se conserva; matriz 72 y OpenAPI 74

La capacidad `gestion_organizacional` sigue existiendo y sigue gateando las rutas de sedes,
departamentos y usuarios. Solo se retiran de `MATRIZ_PERMISOS` y de
`MAPA_OPERACION_CAPACIDAD` las **3** operaciones de encargados: `GET`, `POST` y `DELETE` de
`/api/v1/organizacion/departamentos/{departamento_id}/encargados`. Las demás operaciones
conservan sus roles y códigos. La matriz pasa de **75 a 72** operaciones v1 y `/openapi.json`
de **77 a 74** entradas totales = **72 v1 + `GET /` + `/health`** (no 74 v1 ni 76 totales). No
se agrega ninguna operación ni capacidad.

**Por qué:** la capacidad describe la gestión organizacional completa; quitarla rompería
sedes, departamentos y usuarios, que no se retiran. Las 3 rutas son las únicas que dependen
de la tabla eliminada.

#### D-18 — La baja de usuario deja de bloquear por encargado

Se elimina la comprobación de `_dependencias_usuario` que devolvía **409** cuando el usuario
era encargado y su prueba. Desactivar a un usuario que era encargado ya no se bloquea por
esa causa. Las demás dependencias de baja se conservan: el último Administrador activo, las
reglas de continuidad administrativa y cualquier otra precondición vigente. El docstring y
la documentación OpenAPI del `PATCH .../estado` dejan de anunciar el 409 por encargado.

**Por qué:** sin la tabla no hay fila dependiente que preserve integridad; mantener la
comprobación sería código muerto y un 409 imposible de explicar. Las demás reglas son
independientes y no se tocan.

#### D-19 — Token `026.1` y reset obligatorio

El esquema cambia después de la 026 (se retira una tabla), así que la siguiente revisión de
la convención `NNN.x` es **`026.1`**: el número identifica la feature que cambió el esquema
por última vez y el minor la revisión. La 027 no cambió el esquema; `028.0` exigiría una
Feature 028, que esta enmienda no crea, y `012.x` sería engañoso porque el baseline ya es
026. La versión se fija en `02_datos_semilla.sql`, `backend/app/core/config.py`
(`VERSION_ESQUEMA_OBJETIVO`), el comentario de `01_esquema.sql` y las pruebas gated de
instalación limpia y de versión. `stack.md` se actualiza en esta enmienda (nota de vigencia y
sección); la sincronización de `database/README.md`, `AGENTS.md` y `MEMORY.md` se hace en el
cierre (D-20). No hay migración: el volumen se recrea.

Conteos: **26 → 25** tablas en `control`, **23 → 22** por tenant, **21 entidades de dominio**
sin cambio. La semilla deja de insertar las 5 asociaciones y de listar la tabla en sus
listas, copias, secuencias y guardas. La instalación limpia debe declarar la versión `026.1`
en control y en cada tenant.

**Por qué:** el token es la forma en que el routing detecta un esquema incompatible; dejar
`026.0` haría que un esquema sin la tabla se anunciara como la versión anterior. `026.1` es
la revisión inmediata de la última feature que cambió el esquema y no inventa una feature
nueva.

#### D-20 — Documentación, evidencias y cierre

Los cambios normativos de `docs/spec/**` se hacen en esta enmienda (011, 012, 017, 026, 027,
`stack.md`, `roadmap.md`). Los siguientes quedan como **tareas de la fase 3/cierre**, no se
editan ahora: `AGENTS.md` §4/§7 (21 entidades + auxiliar → 21; 26/23 → 25/22; lista de
features del frontend), `MEMORY.md`, `.agents/skills/*` (sdd-workflow y cualquier skill que
repita «21 + auxiliar»), `docs/diagramas/` (ER y flujos que citen encargados),
`Informe_Flujos_Actores.docx`, `database/README.md` y el índice
`frontend/src/testing/funcional/README.md`.

Las capturas y recorridos de 011/012/8080 que muestran Encargados quedan **obsoletos**: se
marcan como históricos en su evidencia (no se borra el cierre histórico) y se agregó el
recorrido nuevo en 4200 (C2) y 8080 (C3) con **3 pestañas**. La evidencia quedó registrada en
`evidencia/README.md` y en la de AC-20…AC-41.

**Por qué:** el retiro es observable en esquema, API y UI; dejar documentación, diagramas o
capturas que sigan mostrando la figura haría que el reviewer y las próximas features
trabajaran sobre un estado inexistente.

### 10.3 Alcance exacto e inventario de impacto (verificado en el repo)

**DDL y semilla**

- `database/01_esquema.sql`: comentario de cabecera que cuenta la tabla auxiliar; comentario
  y `CREATE TABLE control.departamento_encargado` con sus constraints; `CREATE TABLE
  %1$I.departamento_encargado` del template tenant. Se retiran la tabla, sus constraints y
  cualquier índice/secuencia asociada. Además, el check **fail-closed de 23 tablas por
  tenant** (líneas 1433-1443) y el comentario «23 tablas» (línea 1027) pasan a **22**; sin
  este cambio el reset limpio falla.
- `database/02_datos_semilla.sql`: listas de tablas que incluyen `departamento_encargado`;
  `INSERT` de las **5** asociaciones; `setval` de su secuencia; lista de tablas/secuencias;
  copia `control → tenant`; `DELETE` de la tabla; guardas y conteos; token `026.0` → `026.1`.
- `database/README.md`: 26/23 y `026.0` → 25/22 y `026.1` (actualizado en C3).
- Conteos: `control` **26 → 25**, tenant **23 → 22**, entidades **21** (sin cambio); la
  semilla deja de tener 5 asociaciones.

**Backend**

- `backend/app/models/organizacion.py`: clase `DepartamentoEncargado`, relaciones/imports y
  comentarios; `models/__init__.py`: docstring, import y `__all__`.
- `backend/app/schemas/organizacion_schema.py`: `EncargadoCrear`, `EncargadoRespuesta` y sus
  referencias.
- `backend/app/services/organizacion_service.py`: `_consulta_encargados`,
  `listar_encargados`, `asociar_encargado`, `retirar_encargado`, `_dependencias_usuario` y
  sus usos, imports de `DepartamentoEncargado` y comentarios.
- `backend/app/api/v1/endpoints/organizacion.py`: las 3 rutas, `RUTA_ENCARGADOS`,
  `_encargado_respuesta` e imports; `backend/app/api/v1/api.py`: comentario;
  `backend/app/api/v1/endpoints/usuarios.py`: docstring del 409 por encargado.
- `backend/app/core/permisos.py`: 3 entradas y el comentario de la línea 83 («gestión de
  encargados»); `backend/app/core/capacidades.py`: 3 mapeos y el comentario de
  `gestion_organizacional`.
- `backend/app/core/config.py`: `VERSION_ESQUEMA_OBJETIVO` de `026.0` a `026.1`.
- Contrato: OpenAPI total **77 → 74** = **75 → 72 operaciones v1 + `GET /` + `/health`**;
  matriz **75 → 72**. No confundir matriz 72 con OpenAPI 74 (el total incluye las dos rutas
  técnicas).
- Pruebas que crean `DepartamentoEncargado` o esperan `/encargados`:
  `test_permisos_endpoints.py`, `test_permisos_012.py`, `test_permisos_010.py`,
  `test_permisos_008.py`, `test_permisos.py`, `test_capacidades_gating_012.py`,
  `test_modelo_sede_011.py`, `test_organizacion_011.py`, `test_organizacion_crud_012.py`,
  `_soporte_sede_011.py`, `test_instalacion_limpia_postgres.py` (5 filas y conteos),
  `test_control_postgres_010.py`, `test_dashboard_tecnico_postgres_017.py`,
  `test_ciclo_vida_catalogo_postgres_014.py` y `test_gobierno_identidades_017.py`.
- Pruebas que fijan **75/77, 26/23 o `026.0`** y deben actualizarse a **72 operaciones v1 /
  74 totales, 25/22 o `026.1`** (inventario verificado por QA): `test_permisos_retiro_013.py` (51, 147-149),
  `test_contrato_024.py` (39, 64), `test_ciclo_vida_autorizacion_014.py` (143, 198),
  `test_ciclo_vida_aprobacion_013.py` (620), `test_ciclo_vida_confirmacion_013.py` (456),
  `test_alta_solo_solicitante_007.py` (564), `test_cobertura_021.py` (1443, 1460),
  `test_compras_endpoints_020.py` (63, 190-228), `test_detalle_producto_019.py` (135,
  987-990), `test_filtros_inventario_018.py` (104, 895-905, 997),
  `test_metricas_024.py` (165, `schema_version == "026.0"`),
  `test_salud_esquema_postgres_026.py` (65, 381-392),
  `test_catalogo_retiro_postgres_013.py` (17-18, 266-277),
  `test_cobertura_postgres_021.py` (5-6, 60, 173, 212),
  `test_validacion_entradas_postgres_027.py` (147-154) y el comentario
  `test_correlacion_024.py` (4-6, «77 operaciones»).
- Pruebas del Bloque A (E12-A3, no alteran los conteos normativos de arriba):
  `backend/tests/funcional/integracion/test_contrato_usuarios_suministros_012.py`
  (contrato opcional/OpenAPI 72/74, 422 por rol y por «Suministros», regresión de
  `PUT .../sede` y de `gestion_organizacional`) y
  `backend/tests/funcional/sistema/test_suministros_postgres_012.py` (gated:
  concurrencia, reutilización/reactivación y fallo local sin confirmar).
- Verificación: `grep -r "DepartamentoEncargado\|departamento_encargado\|/encargados\|encargado"
  backend/tests frontend/src database` y revisar los falsos positivos de «Bodeguero /
  Encargado de Suministros». El grep de cierre no se limita a `backend/tests`.

**Frontend**

- `features/administracion/encargados.component.ts|html|spec.ts` (se retiran).
- `features/administracion/administracion.routes.ts|spec.ts` (ruta y lista de hijas).
- `features/administracion/administracion-nav.component.ts|spec.ts`: 4 → **3** pestañas,
  IDs ARIA, wraparound Sedes↔Usuarios y mock `listarEncargados`.
- `features/administracion/services/administracion.service.ts`: métodos de encargados e
  import; `services/administracion.service.spec.ts`: docstring y 3 casos de encargados
  (122-146); `shared/interfaces/index.ts`: `Encargado`, `EncargadoCrear`.
- `features/administracion/administracion.component.ts` y `.html`: comentario/texto de
  «encargados»; `features/control/control.routes.ts`: comentario.
- `features/administracion/usuarios.component.html`: texto del 409 por encargado en el
  diálogo de baja; `features/administracion/usuarios.component.spec.ts`: caso del 409 por
  encargado.
- `frontend/src/testing/funcional/README.md`: fila del spec retirado.
- `superficies-retiradas.spec.ts`: la búsqueda no encontró referencias a encargados; no se
  espera cambio.
- La ruta `/administracion/encargados` deja de existir y no renderiza la vista; no hay
  pestaña ni enlace. Una visita directa cae en el wildcard vigente (`**` → `/dashboard`),
  sujeto a la autenticación.

**Documentación y evidencias**

- 011 `spec.md`: AC-4/AC-5, §3, D-4, §5 pasos 4/6, §7 y evidencia.
- 012 `spec.md`: AC-10, parte de AC-11, §3 «Dentro», D-4, §5 paso 7, §7, T-17 AC-15…AC-19
  (4 → 3 pestañas) y evidencia. §1/§2: contexto histórico con «encargados»; se añade nota de
  contexto y no se reescribe la evidencia histórica de AC-10.
- 017 `spec.md`: §8 «15 entidades + `departamento_encargado`»; nota de §11.
- 022 `spec.md`: línea 79 (`EncargadoCrear`); 026 `spec.md`: D-6, conteos, AC-19, índice P1
  `departamento_encargado(usuario_id)` (línea 80) y «única tabla auxiliar»; 027 `spec.md`:
  AC-13 y §2 (conteos `026.0`/26/23).
- 013 `evidencia/README.md`: línea 64 (`departamento_encargado` asocia el departamento 6);
  012 `diseno-tecnico.md`: líneas 374-376; 012 `plan.md` (87, 163) y `tasks.md` (84, 107,
  125, 146): registros históricos, no se reescriben.
- `stack.md`, `roadmap.md`, `AGENTS.md` §4/§7, `MEMORY.md`, `.agents/skills/*`,
  `docs/diagramas/`, `Informe_Flujos_Actores.docx` y `database/README.md`.
- Generadores y datos del informe: `docs/informes/_generar_informe.py` (73, 123, 270, 275,
  350), `docs/informes/_generar_planilla_pruebas.py` (261, 309),
  `docs/informes/_datos/frontend-specs.json` (1898-1973, 2263-2290) y
  `docs/informes/_datos/backend-coleccion-027.txt` (1425-1426, 1785-1793, 1920-1922). Si no
  se actualizan, el informe regenerado reintroduce la figura.
- Evidencias 011/012/8080 con Encargados: marcar históricas/obsoletas; nuevo recorrido
  4200/8080 con 3 pestañas.

### 10.4 Criterios de aceptación del Bloque B

> **Los AC-33…AC-41 están implementados y verificados (27/Nov/2026).** La evidencia cita el
> archivo y método reales, el conteo de la suite, el reset y el recorrido observado.

- [x] **AC-33 — Tabla ausente y conteos 25/22.** DADO el esquema reconstruido, CUANDO se
      inspecciona `information_schema`, ENTONCES `departamento_encargado` no existe en
      `control` ni en ningún `tenant_*`, no queda su secuencia ni índice, `control` tiene
      **25** tablas, cada tenant **22** y el modelo conserva **21** entidades de dominio.
  - **Evidencia:** gated
    `test_salud_esquema_postgres_026.py::test_arranque_limpio_deja_25_tablas_en_control_y_22_por_tenant`
    y `test_instalacion_limpia_postgres.py::test_instalacion_limpia_crea_control_y_tenants_versionados`;
    consulta real sobre `apt_erp` (C1/C3): `control` **25** tablas, `tenant_inst_001…004` **22**
    cada uno, `to_regclass('control.departamento_encargado')` nulo y **0** tablas/columnas con
    ese nombre en `information_schema`; **21** clases en el metadata tenant (las auxiliares de
    `control` no cuentan).
- [x] **AC-34 — Semilla sin asociaciones y token `026.1`.** DADO `down -v` + `up -d`,
      ENTONCES `01_esquema.sql` y `02_datos_semilla.sql` no crean ni insertan
      `departamento_encargado`, no hay 5 asociaciones, la guardia fail-closed sigue y
      `control` y todos los tenants declaran `026.1`.
  - **Evidencia:** reset observado en C2 (`down -v` + `up -d` sobre volumen recreado) y en C3:
    `version_esquema = 026.1` en `control` y en los cuatro tenants, sin las 5 asociaciones ni
    rastros de la tabla; guardia fail-closed en
    `test_instalacion_limpia_postgres.py::test_guardia_fail_closed_aborta_la_segunda_semilla` y
    token en `test_salud_esquema_postgres_026.py::test_version_026_1_en_control_y_en_cada_tenant`.
    `01_esquema.sql`/`02_datos_semilla.sql` no mencionan `departamento_encargado` (grep de C1).
- [x] **AC-35 — Endpoints retirados y OpenAPI 74.** DADO el backend, ENTONCES las 3 rutas
      `/api/v1/organizacion/departamentos/{departamento_id}/encargados...` no existen en la
      aplicación ni en `/openapi.json` (404/405 según el caso, sin operación publicada);
      OpenAPI total queda en **74** = **72 operaciones v1 + `GET /` + `/health`** (antes 77 =
      75 v1 + las dos técnicas); la matriz queda en **72**, no en 74; no hay operaciones nuevas.
  - **Evidencia:** `test_contrato_usuarios_suministros_012.py::test_openapi_publica_74_operaciones_72_v1_y_matriz_72`
    y `::test_openapi_y_matriz_no_publican_las_rutas_de_encargados`; sondeo HTTP en C1 de
    `GET/POST/DELETE /api/v1/organizacion/departamentos/1/encargados[/1]` → **404**; `/openapi.json`
    en vivo (27/Nov/2026) con **74** operaciones = **72 v1 + `GET /` + `/health`** y matriz **72**
    (`len(MATRIZ_PERMISOS)`), sin operaciones nuevas.
- [x] **AC-36 — Permisos y capacidad intacta.** DADO `gestion_organizacional`, ENTONCES las
      rutas de sedes, departamentos y usuarios siguen gateadas y con sus roles; las 3 rutas
      de encargados ya no están en la matriz ni en el mapeo; apagar la capacidad sigue
      bloqueando las **operaciones/API** de esas 3 superficies. El gating es backend: no se
      promete un bloqueo de UI que el frontend no implementa.
  - **Evidencia:** `test_contrato_usuarios_suministros_012.py::test_gestion_organizacional_sigue_gateando_las_tres_superficies`
    (mapeo de sedes/departamentos/usuarios + **403** real con la capacidad apagada);
    `tests/no_funcional/seguridad/test_capacidades_gating_012.py` y
    `test_gating_capacidades_endpoints_012.py` verdes; `test_permisos_012.py` con las entradas de
    `/organizacion/*` y `/usuarios/*` y sin las 3 de encargados; gated
    `test_gestion_administrativa_http_postgres_012.py::test_gating_gestion_organizacional_403_sin_mutar_y_habilitada_crea`.
    El gating es de backend (no se promete bloqueo de UI).
- [x] **AC-37 — Baja de usuario sin 409 por encargado.** DADO un usuario cualquiera, CUANDO se
      desactiva, ENTONCES la operación no consulta la tabla retirada ni responde 409 por
      encargado; la baja funciona si no hay otra dependencia y el 409 del último Administrador
      activo se conserva.
  - **Evidencia:** `test_organizacion_crud_012.py::test_desactivar_usuario_sin_dependencias_responde_200`
    (sustituye al antiguo 409 por encargado) y
    `test_edicion_suministros_012.py::test_edicion_de_usuario_no_bloquea_por_encargado`; el 409 del
    **último Administrador activo** sigue en `test_editar_ultimo_administrador_a_bodeguero_conserva_409`
    y en la suite de gobierno de Administradores de la 017 (verde).
- [x] **AC-38 — Frontend con 3 pestañas y sin artefactos de encargados.** DADO
      `/administracion`, ENTONCES hay 3 pestañas (Sedes, Departamentos, Usuarios), sin
      pestaña, ruta, componente, tipos, métodos de servicio ni textos de Encargados;
      `usuarios.component.html` no conserva el texto del 409 por encargado y
      `administracion.service.spec.ts` no conserva sus 3 casos; `/administracion/encargados`
      no renderiza la vista y cae en el wildcard vigente (`**` → `/dashboard`); los deep links
      a sedes/departamentos/usuarios renderizan su vista y un `role="tabpanel"` con
      `aria-labelledby` de la pestaña activa; ARIA, IDs y wraparound funcionan con 3
      pestañas; `ng test` verde.
  - **Evidencia:** `administracion.routes.spec.ts` (3 hijas y el wildcard con una URL no
    publicada), `administracion-nav.component.spec.ts` (3 tabs, IDs, `aria-selected`/`tabindex`
    roving, `tabpanel` con `aria-labelledby` y flechas circulares Sedes↔Usuarios) y
    `administracion.service.spec.ts` (sin los 3 casos de encargados); `ng test` **671 SUCCESS** y
    `ng build` limpio. **4200 (C2):** 3 pestañas y `/administracion/encargados` → `/dashboard`;
    **8080 (C3):** tablist de 3 en cada deep link y la misma redirección, sin vista ni textos de
    encargados.
- [x] **AC-39 — Pruebas y conteos.** DADA la implementación, ENTONCES `pytest` SQLite,
      gated PostgreSQL y `ng test` están en verde; no quedan referencias a
      `DepartamentoEncargado`, `departamento_encargado`, `/encargados` ni a la figura de
      encargado de departamento (incluido el singular «encargado») en `backend/tests`,
      `frontend/src` ni `database/`; los falsos positivos de «Bodeguero / Encargado de
      Suministros» se revisan y no cuentan. Los conteos son **25/22**,
      **21** entidades, **`026.1`**, OpenAPI **74** (72 v1 + 2 técnicas) y matriz **72**. Se
      actualizan las pruebas de conteo/versión inventariadas en §10.3
      (`test_permisos_retiro_013`, `test_contrato_024`, `test_ciclo_vida_autorizacion_014`,
      `test_ciclo_vida_aprobacion_013`, `test_ciclo_vida_confirmacion_013`,
      `test_alta_solo_solicitante_007`, `test_cobertura_021`, `test_compras_endpoints_020`,
      `test_detalle_producto_019`, `test_filtros_inventario_018`, `test_metricas_024`,
      `test_salud_esquema_postgres_026`, `test_catalogo_retiro_postgres_013`,
      `test_cobertura_postgres_021`, `test_validacion_entradas_postgres_027` y
      `test_correlacion_024`).
  - **Evidencia:** suites de C1/C3 (SQLite **2163/127/0**, gated **2287/3/0**, `ng test` **671**);
    **grep de cierre:** 0 coincidencias de `DepartamentoEncargado`, `departamento_encargado` y
    `/encargados` en `backend/tests`, `frontend/src` y los **scripts SQL de `database/`**; queda
    **1 mención histórica en `database/README.md`** (la nota que declara el retiro). Las menciones
    de «encargado» que quedan son ratchets de ausencia (`test_openapi_y_matriz_no_publican_las_rutas_de_encargados`,
    `test_edicion_de_usuario_no_bloquea_por_encargado`, el fixture `Sin.Encargado` y el docstring
    «no consulta encargados») y el nombre del rol «Bodeguero / Encargado de Suministros», no
    supersedido. Conteos **25/22**, **21** entidades, **`026.1`**, OpenAPI **74** y matriz **72**.
- [x] **AC-40 — Documentación, evidencias y cierre.** DADO el cierre, ENTONCES 011/012/017/
      026/027/stack/roadmap están sincronizados; `AGENTS.md`, `MEMORY.md`, skills, diagramas
      y el informe se actualizan como tareas de cierre; las capturas con Encargados quedan
      marcadas históricas; 4200 y 8080 se recorren con 3 pestañas; el reset es limpio; no hay
      otro DDL ni migración.
  - **Evidencia:** C3 (27/Nov/2026): `AGENTS.md` §4/§7 (25/22, `026.1`, 21 entidades sin
    auxiliar, 3 vistas de administración), `MEMORY.md`, `database/README.md`, `docs/spec/stack.md`
    (nota de vigencia implementada, árbol sin `encargados.component.ts`, enmienda marcada como
    implementada y conteos históricos declarados), `roadmap.md`,
    `.agents/skills/sdd-workflow` y `fastapi-pydantic-v2`, `frontend/src/testing/funcional/README.md`
    (44 specs / 671 casos) y `evidencia/README.md` (secciones C2 y 8080). La supersesión de las
    specs cerradas de 011/012/017/026/027 —incluidas la relación N:N, 26/23 y `026.0`— queda
    declarada en §10.5 y en la nota de vigencia de `stack.md`; esas specs no se reescriben.
    Diagramas actualizados en HTML+PNG (casos de uso del Administrador y general sin «Asignar
    encargados», clases sin `DepartamentoEncargado`, flujo 03 con «Asignar sede del Bodeguero») e
    `Informe_Flujos_Actores.docx` regenerado; la planilla de pruebas se mantiene como línea base
    del cierre 027 (pendiente reportado). Capturas `01`-`28` marcadas **históricas**. 4200 y 8080
    con 3 pestañas; reset limpio; no hay otro DDL ni migración.
    **Corrección post-validación (27/Nov/2026):** se corrigieron las contradicciones documentales
    detectadas por el reviewer —estado del segundo bloque en esta spec, nota de la 026 (de
    «objetivo» a implementado), `stack.md` sin el «queda pendiente», `MEMORY.md`
    (015/016 pendientes y recorridos 15/Suministros/KPI 8 como **históricos**), la frase de
    `tasks.md` sobre no marcar casillas, la evidencia de AC-39 sobre el grep de `database/` y la
    subsección de evidencia del cambio de rol manual. No se editó la evidencia de la 013: solo se
    la referencia (`013-ciclo-vida-ticket/evidencia/README.md` §11.3).
- [x] **AC-41 — Regresión de flujos no tocados.** DADO el cierre, CUANDO se ejecutan las
      suites existentes, ENTONCES la 017 conserva el orden validar → invitar → confirmar
      tenant → confirmar mapa, los estados `pendiente`/`aceptada`/`revocada`/`expirada`, el
      reenvío, las constancias y los 409/503 (`test_gobierno_identidades_017.py`,
      `test_provisionamiento_identidades_017.py`, `test_frontera_clerk_017.py`,
      `test_gobierno_administradores_017.py`, `test_gobierno_correcciones_017.py` y
      `test_aceptacion_invitacion_017.py`); las suites de tickets, stock, compras, dashboard y
      autenticación siguen verdes sin cambios de comportamiento. No se crea un test nuevo si
      las suites existentes cubren el caso. SI se intenta el cambio de rol del último
      Administrador activo, ENTONCES conserva su 409.
  - **Evidencia:** C1 ejecutó las seis suites de la 017 —`test_gobierno_identidades_017.py`,
    `test_provisionamiento_identidades_017.py`, `test_frontera_clerk_017.py`,
    `test_gobierno_administradores_017.py`, `test_gobierno_correcciones_017.py` y
    `test_aceptacion_invitacion_017.py`— con **99 passed** en ejecución dirigida; tickets, stock,
    compras, dashboard y autenticación quedan incluidos en las suites completas (SQLite
    **2163/127/0** y gated **2287/3/0**). El 409 del último Administrador activo se conserva sin
    cambio. No se creó un test nuevo para esta regresión.

### 10.5 Supersesión del Bloque B

- **Feature 011, AC-4 y AC-5** y las demás menciones a encargados de departamento (§3
  «Dentro», D-4, §5 pasos 4/6, §7, evidencia de AC-4/AC-5): la relación N:N, su API y su
  semántica quedan **retiradas**. Lo demás de la 011 (sede, stock por sede, snapshot de sede
  en ticket y precondiciones) sigue vigente.
- **Feature 012, AC-10** y la parte de **AC-11** que cita el 409 por encargado: la vista, la
  asociación y su prueba quedan retiradas. **§3 «Dentro»**, **D-4**, **§5 paso 7**, **§7**
  («Los encargados son usuarios Solicitantes…») y la evidencia de AC-10/AC-11 que dependa de
  encargados quedan precisados por este bloque.
- **Feature 012, D-6, literal:** el paréntesis de `gestion_organizacional` que incluía
  «encargados» queda precisado: la capacidad se conserva para sedes, departamentos y
  usuarios; solo se retiran las 3 rutas de encargados.
- **Feature 012, enmienda T-17, AC-15…AC-19:** la navegación administrativa pasa de **4 a 3**
  pestañas; los IDs `pestana-administracion-encargados`, el wraparound con Encargados y las
  capturas con 4 pestañas quedan superados. El patrón ARIA, los enlaces reales, el foco y los
  deep links de las 3 vistas restantes se conservan.
- **Feature 017, §8:** la mención «15 entidades de dominio + `departamento_encargado`» queda
  superada; el **objetivo** es **21 entidades** sin tabla auxiliar y **25/22** con `026.1`;
  el actual sigue 26/23 y `026.0` hasta el reset. El flujo de invitación no cambia.
- **Feature 026, D-6/conteos/AC-19:** las menciones a `departamento_encargado` como única
  tabla auxiliar, **26/23** y **`026.0`** son históricas de su cierre; el **estado objetivo
  de la enmienda** es **25/22** y **`026.1`**, y el actual sigue en 26/23 y `026.0` hasta el
  reset. La 026 no se reescribe.
- **Feature 027, AC-13/§2:** el «sin cambio de esquema» y los conteos `026.0`/26/23 son
  históricos de su cierre; el **estado objetivo de la enmienda** es **`026.1`/25/22**, y el
  actual sigue en 26/23 y `026.0` hasta el reset. La 027 no se reescribe.
- **`stack.md`:** la nota de vigencia y la sección nueva fijan el objetivo 25/22, `026.1` y
  la retirada; las menciones históricas a «única tabla auxiliar» quedan superadas.
- **Referencias documentales adicionales:** `022` spec (línea 79, `EncargadoCrear`), `026`
  spec (línea 80, índice P1 `departamento_encargado(usuario_id)`), `013` evidencia (línea 64),
  `012/diseno-tecnico.md` (374-376), `012/plan.md` (87, 163), `012/tasks.md` (84, 107, 125,
  146), `012` spec §1/§2 (contexto histórico con «encargados»; nota añadida) y el comentario
  `permisos.py:83` quedan **históricos** y se actualizan o marcan en el cierre; la
  013/022/026 no se reescriben.
- **No se supersede:** el rol **Bodeguero / Encargado de Suministros**, la capacidad
  `gestion_organizacional`, las reglas de sedes/departamentos/usuarios, el flujo de tickets,
  stock, compras, autenticación ni las features 015/016.

### 10.6 Fuera de alcance del Bloque B

- **Otros cambios de esquema:** solo se retira `departamento_encargado`; no se tocan otras
  tablas, columnas, índices, checks, secuencias ni la semilla fuera de las referencias a esa
  tabla. No hay migración; el reset es obligatorio.
- **Tickets, stock, compras, dashboard, autenticación y Clerk:** sin cambios.
- **Capacidad `gestion_organizacional`:** se conserva; no se elimina ni se renombra.
- **Roles y permisos restantes:** se conservan; solo se retiran las 3 operaciones de
  encargados. No se agregan roles, capacidades ni operaciones.
- **Vista administrativa restante:** no se rediseña; solo se quita la pestaña, la ruta y el
  componente de Encargados.
- **Bodeguero / Encargado de Suministros:** no se toca; la eliminación es del encargado de
  departamento.
- **Histórico/archivo de la tabla:** no se conserva; no se archiva.
- **Features 015 y 016:** siguen fuera.
- **`AGENTS.md`, `MEMORY.md`, skills, diagramas e informe:** se actualizan en la fase
  3/cierre, no en esta fase de spec.

### 10.7 Evidencias y tareas de cierre (cumplidas el 27/Nov/2026)

- **Evidencias:** AC-33…AC-41 quedaron evidenciados en la sección 10.4; las capturas
  011/012/8080 con Encargados se marcan históricas/obsoletas; el recorrido 4200 (C2) y 8080 (C3)
  con 3 pestañas y el reset observado están registrados en `evidencia/README.md`.
- **Tareas de cierre (ejecutadas en C3):** `AGENTS.md` §4/§7 (21 entidades sin auxiliar,
  25/22, lista de features), `MEMORY.md`, `.agents/skills/*` (sdd-workflow y
  fastapi-pydantic-v2), `docs/diagramas/` (casos de uso, clases y flujo 03),
  `Informe_Flujos_Actores.docx`, `database/README.md` y
  `frontend/src/testing/funcional/README.md`.
