# Feature 007 — Plan Técnico

Spec: [`spec.md`](spec.md), aprobada como fuente de requisitos (AC-1…AC-17). Este plan concreta la autorización de la identidad Clerk ya resuelta en Feature 006, la política institucional temporal de 007 y el retiro seguro de `usuario.password`; no cambia la autenticación ni añade particionamiento de catálogo/stock reservado a 008.

## 1. Enfoque técnico por componente

### Backend: identidad, permisos y ámbito institucional

Mantener `get_current_user` como dependencia agregada de autenticación: su resultado contiene el usuario SQLAlchemy vinculado y el `sub` Clerk verificado. Añadir una dependencia de autorización de rol en `backend/app/api/dependencies.py`, parametrizable con uno o varios roles permitidos, que dependa de `get_current_user` y reutilice esa identidad. La dependencia solo aplica el permiso general; si faltan credenciales o Clerk falla, continúa el 401 actual; identidad autenticada sin permiso obtiene 403. Rol faltante/desconocido nunca concede.

La política completa, centralizada y explícita por operación, vive en `backend/app/core/` como matriz de permisos de roles/rutas; los endpoints la declaran al aplicar la dependencia. No se usa un único permiso por router porque la matriz diferencia verbos, recursos y reglas especiales. Las reglas por objeto/institución se aplican en servicios antes de leer o mutar datos: se pasa la identidad ya resuelta (usuario local y rol) a servicios y se obtiene institución por `Usuario.departamento_id → Departamento.institucion_id`. Solo `Superadmin` omite el filtro. Un ámbito necesario sin resolver resulta en 403; no se transforma en alcance global.

Para entidades y colecciones, los servicios filtran en consulta ORM/Core tipado. Tickets: Administrador/Bodeguero por institución; Solicitante por `usuario_id`; un ticket ajeno/inexistente en operación permitida se oculta como 404. Inventario y movimientos: roles limitados por institución; cuando `departamento_id` explícito apunta a otra institución, 403. Catálogo maestro de categoría/producto conserva su lectura compartida; `GET /tickets/catalogos` conserva productos y `stock_total` global y filtra únicamente el conjunto de solicitantes según la matriz (Solicitante solo él mismo; Administrador/Bodeguero su institución; Superadmin global).

Para `POST /tickets/`, añadir identidad al servicio: Solicitante queda atribuido al usuario autenticado sin poder elegir otro; los demás roles conservan el DTO/contrato existente con `usuario_id` obligatorio, y Administrador/Bodeguero validan institución del solicitante. Para cambios de estado/despacho, después de autorización de rol comprobar ámbito del ticket y el inventario afectado dentro de la lógica transaccional existente; preservar atomicidad de Feature 005. Para `POST /usuarios/`, el servicio aplica la restricción del rol asignable por Administrador y el ámbito institucional de datos; Superadmin conserva libertad total de rol.

### Frontend: guards y estado de denegación

`AutenticacionService` conserva la señal de identidad ya cargada desde `/auth/me`; el `RolGuard` lee esa identidad mediante inyección, espera inicialización/carga según el estado expuesto y compara `rol` exacto (los cuatro literales; ningún alias `Admin`). Las rutas protegidas reciben datos explícitos de roles permitidos por sección/capacidad y combinan guard de sesión existente y guard de rol. `/login`, `/health` público y redirección raíz mantienen contrato vigente. La denegación retorna navegación a una vista/estado dedicado, no al login, no cierra sesión y no invoca la operación. Dashboard/inventario/tickets/administración siguen siendo lazy-loaded. La capa visual de tickets evita ofrecer capacidad operativa al Solicitante cuando aplique, pero la frontera de seguridad real permanece en API.

La ruta tickets distingue vista y capacidad sin inventar endpoints: los cuatro roles pueden entrar a tickets; solo Solicitante queda sin Kanban/cambios de estado/despacho según AC-3, AC-6 y AC-7. La implementación deberá resolver esto con rutas/metadata y controles de vista existentes, manteniendo los casos permitidos y usando el guard a nivel de ruta/capacidad. No se crearán datos de rol alternativos ni se inferirá permiso desde Clerk.

### Base de datos y retiro de contraseña

En instalaciones nuevas, quitar columna y valores de `usuario.password` de `database/01_esquema.sql` y `database/02_datos_semilla.sql`; quitar el atributo de `Usuario` y de `UsuarioCrear`, y actualizar todos los tests/fixtures que lo exijan. Corregir comentarios obsoletos en semilla y docstrings señalados por AC-11.

Crear un script SQL versionado e idempotente bajo `database/` posterior a los scripts de inicialización (prefijo que garantice orden y nombre que identifique migración). Su única operación de esquema será `ALTER TABLE usuario DROP COLUMN IF EXISTS password`; no reinicializa ni actualiza filas. El directorio `/docker-entrypoint-initdb.d` solo se ejecuta con volumen nuevo, por lo que la migración debe aplicarse explícitamente a bases ya inicializadas: incluir instrucciones de operación reproducibles en la cabecera del script/tarea para ejecutar `psql` contra la BD existente con `ON_ERROR_STOP=1`, desde el host o `docker exec` al contenedor `db`, y verificar el catálogo antes/después. No se debe confiar en renombrar scripts de init ni en destruir volúmenes. Validar migración en PostgreSQL 16 con usuario y relaciones preexistentes, ejecutar segunda vez y confirmar preservación; SQLite no sustituye esa evidencia de DDL PostgreSQL.

## 2. Archivos que se crean o modifican

| Archivo | Responsabilidad | AC |
|---|---|---|
| `backend/app/core/permisos.py` (nuevo) | Matriz explícita rol-operación y literales de roles, sin alias ni permisos implícitos. | AC-1, AC-7…AC-10 |
| `backend/app/api/dependencies.py` | Dependencia parametrizable de rol que conserva 401 de autenticación y deniega rol con 403. | AC-1, AC-9, AC-15 |
| `backend/app/api/v1/api.py` | Mantener seguridad agregada de sesión y declarar/registrar autorización por operación sin dejar rutas de negocio fuera. | AC-9, AC-15 |
| `backend/app/api/v1/endpoints/usuarios.py` | Inyectar identidad/autorización por ruta y transportar contexto al servicio. | AC-8…AC-10, AC-15 |
| `backend/app/api/v1/endpoints/inventario.py` | Permisos por operación y contexto de identidad a consultas/mutaciones. | AC-7…AC-9, AC-15 |
| `backend/app/api/v1/endpoints/tickets.py` | Permisos por operación y contexto de identidad a lectura, creación, estado y despacho. | AC-6…AC-9, AC-15 |
| `backend/app/services/usuario_service.py` | Límites institucionales y rol asignable; listados institucionales. | AC-8, AC-10, AC-15 |
| `backend/app/services/inventario_service.py` | Filtros por institución en stock/movimientos y denegación de departamento ajeno; catálogo compartido. | AC-7…AC-9, AC-15 |
| `backend/app/services/ticket_service.py` | Propiedad, filtros institucionales, atribución de solicitante y comprobación de ámbito previa a operación transaccional. | AC-6…AC-9, AC-15 |
| `backend/app/models/usuario.py` y `backend/app/models/institucion.py` | Eliminar atributo ORM `password`; corregir el `__init__.py` de modelos solo si el proyecto requiere registrar la matriz/dependencias nuevas (sin alterar entidades). | AC-8, AC-12, AC-14 |
| `backend/app/schemas/usuario_schema.py` | Quitar contraseña de `UsuarioCrear`; conservar los demás campos del contrato. | AC-12, AC-14 |
| `backend/app/schemas/ticket_schema.py` | Corregir docstring de `TicketDespacho` que califica autenticación como decorativa. | AC-11 |
| `backend/tests/conftest.py`, `backend/tests/funcional/integracion/*.py` y `backend/tests/` (nuevos tests de permisos/migración si aplica) | Fixtures sin contraseña y cobertura HTTP/servicios para matriz, filtros, propiedad, migración y OpenAPI/denegaciones. | AC-6…AC-16 |
| `frontend/src/app/core/guards/role.guard.ts` | Implementar comparación de rol local, espera de identidad y resultado de denegación. | AC-1…AC-5, AC-15 |
| `frontend/src/app/core/guards/role.guard.spec.ts` | Tests de roles exactos, estado de carga, rol inválido y navegación denegada. | AC-1…AC-5, AC-15 |
| `frontend/src/app/core/services/auth.service.ts` | Exponer estado de carga/identidad suficiente para que el guard espere sin repetir `/auth/me`. | AC-2, AC-4, AC-15 |
| `frontend/src/app/app.routes.ts` y rutas de features | Asociar rol(es) permitidos; conservar sesión, login, raíz y rutas públicas. | AC-2…AC-5, AC-15 |
| `frontend/src/app/features/` vistas/rutas existentes | Ocultar/desactivar capacidades operativas no autorizadas y presentar denegación dedicada donde corresponda. | AC-2, AC-3, AC-5, AC-15 |
| `frontend/src/app/features/` vista de acceso denegado (nueva si no existe) | Mensaje accesible de permiso insuficiente, sin cerrar sesión ni redirigir a login. | AC-2, AC-15 |
| `frontend/src/app/app.component.ts` / `.html` | Agregar navegación al estado dedicado sin cambiar el flujo de sesión o identidad existente. | AC-2, AC-4 |
| `frontend/src/app/app.routes.spec.ts`, specs frontend afectados y vista de tickets | Cubrir matriz de rutas, guard, estado de denegación, espera de identidad/rol y ocultación de controles operativos. | AC-1…AC-5, AC-15 |
| `database/01_esquema.sql` y `database/02_datos_semilla.sql` | Omitir `password` en instalación nueva y retirar comentarios falsos sobre autenticación. | AC-11, AC-12 |
| `database/03_migracion_retiro_password.sql` (nuevo; nombre final sujeto a orden alfabético) | Migración explícita, versionada e idempotente para base ya inicializada. | AC-13, AC-16 |
| `docs/spec/stack.md`, `docs/spec/roadmap.md`, `docs/spec/features/007-control-acceso-roles/spec.md`, `MEMORY.md`, `AGENTS.md`, `.agents/skills/**` | Solo en cierre: actualizar arquitectura/estado/evidencia, AC y referencias realmente obsoletas; roadmap únicamente tras verificación completa. | AC-11, AC-17 |

## Enmienda de autoatribución de tickets (22/Oct/2026)

> Plan de cambio posterior al cierre, limitado a AC-6 actualizado y AC-18…AC-20. La matriz de permisos y toda la autorización no relacionada con la atribución permanecen cerradas/intactas.

### Decisiones técnicas por capa

- **Schema:** `TicketCrear.usuario_id` se hace opcional. Si se recibe se ignora silenciosamente, incluso si es ajeno o inexistente; no se deja que FastAPI ni servicio lo conviertan en 422/403/404. Mantener `TicketDespacho.usuario_id` requerido porque es otro contrato y no forma parte de la enmienda.
- **Servicio y precedencia:** identidad ya autenticada y rol autorizado continúan siendo resueltos por los mecanismos existentes. En `crear_ticket`: 1) reemplazar incondicionalmente el usuario de entrada por `identidad.usuario.usuario_id`; 2) resolver institución efectiva de sesión y la institución de ese usuario; 3) validar prioridad/estado; 4) validar productos respecto de esa institución (404 por producto ajeno se mantiene); 5) resolver sede desde `departamento.sede_id` de la identidad (409 si no existe/no resoluble); 6) validar reglas restantes del estado inicial y escribir cabecera/detalles/historial transaccionalmente. Ninguna validación, consulta o autorización toma como fuente `payload.usuario_id`.
- **Identidades sin sede:** se aplica 409 a cualquier rol con permiso vigente cuyo departamento no tenga sede resoluble, incluyendo Administrador/Bodeguero; no fallback a `usuario.sede_id`. La semilla de `02_datos_semilla.sql` actualmente tiene sede departamental para Admin roles 2 (usuarios 1/3/4/10) y Bodeguero rol 3 (6/7/12); las sedes en `usuario.sede_id` de bodegueros 6/7/12 no sustituyen ese vínculo.
- **API y matriz:** sin cambio de ruta, permiso, rol autorizado, status exitoso ni contrato de listado. OpenAPI deberá anunciar `usuario_id` opcional/ignorado y no justificar 404 de solicitante payload. Superadmin mantiene 403.
- **Frontend aunque la feature 007 no era dueña original del modal:** su contrato exige UI congruente; el trabajo compartido se implementa en tickets: `AutenticacionService.identidad()` entrega `IdentidadAutenticada` con `nombre`, `apellido`, `correo` (también `usuario_id`, `sub`, `rol`, `institucion`), sin departamento. Se pinta nombre + apellido y correo como identificador, solo informativo; no llamada adicional. El formulario omite `usuario_id` del body; no usa el catálogo como autoridad. `solicitantes` se conserva en GET catálogo para listados/detalle.

### Archivos de la enmienda

| Archivo | Responsabilidad | AC |
|---|---|---|
| `backend/app/schemas/ticket_schema.py` | Opcionalidad del campo de alta, manteniendo intacto DTO de despacho. | AC-6, AC-18 |
| `backend/app/services/ticket_service.py` | Autoatribución para los roles autorizados y ámbito de sesión; conservar productos/sede/ACID. | AC-6, AC-18, AC-20 |
| `backend/app/api/v1/endpoints/tickets.py` | Precisión documental en OpenAPI; sin cambio de matriz/ruta/status. | AC-6, AC-18 |
| `backend/tests/funcional/integracion/test_tickets_alcance.py`, `test_tickets_institucional.py`, `test_modal_ticket.py`, `test_ticket_sede_011.py`, `test_transaccion_ticket.py` y cualquier test de alta encontrado con grep | Reescribir expectativas antiguas de payload autor; mantener test de despacho y casos de producto ajeno. | AC-6, AC-18, AC-20 |
| `frontend/src/app/features/tickets/tickets.component.ts`, `.html`, `.spec.ts`, `frontend/src/app/shared/interfaces/index.ts` | Campo de autor informativo de identidad, sin selector/control, body omite usuario_id, contrato opcional. | AC-19 |

### TDD, orden y pruebas

La enmienda es un solo cambio transversal; `008/tasks.md` es el único orquestador con las tareas E22-1 backend → E22-2 frontend → E22-3 regresión → E22-4 verificación/cierre. Las secciones E22 de 003 y 007 enlazan esas tareas y registran su AC, no crean ejecución paralela.

1. **Rojo backend:** reemplazar el test histórico del `usuario_id` obligatorio (eliminado); actualizar `test_administrador_crea_para_solicitante_propio_201`, `test_solicitante_crea_y_se_atribuye_su_identidad`, `test_administrador_ignora_solicitante_de_otra_institucion_y_atribuye_a_sesion`. Afirmar ausencia/valor propio/ajeno/inexistente e identidad resultante. Cubrir Administrador y Bodeguero, autoría e institución/sede de sesión, 409 sin sede sin escrituras y producto ajeno 404.
2. **Verde servicio/schema y OpenAPI:** opcionalidad de entrada y orden de validaciones anterior a escritura; actualizar solo expectativas vencidas. Mantener intactos tests de matriz, Superadmin 403, propiedad/listado, PATCH/despacho 403 y aislamiento de otras operaciones.
3. **Rojo/verde Angular:** pruebas de `tickets.component.spec.ts`: eliminar `formulario.controls.usuario_id.setValue(5)`, expectativa de cuerpo con campo y expectativas del selector; añadir identidad visible y ausencia de selector/campo, y conservar catálogo de solicitantes para las vistas. No solicitar `/auth/me` desde modal: usar signal existente.
4. **Tests a conservar explícitamente:** `test_crear_ticket_con_producto_ajeno_404_sin_parcial`; `test_crear_ticket_puebla_institucion_en_ticket_y_detalle` (adaptar solo para afirmar anclas respecto de identidad); despacho sigue requiriendo el campo de actor propio de `TicketDespacho`.
5. **Verificación:** `pytest` SQLite y gated PG16 pertinente; frontend `ng test --watch=false --browsers=ChromeHeadless` con `CHROME_BIN` configurado a Edge. Inspeccionar `/openapi.json`. Nunca ejecutar `npm test`.

### Riesgos y alcance no tocado

| Riesgo | Mitigación |
|---|---|
| AC-11 de 008 sigue esperando 404 por usuario ajeno | La tarea transversal actualiza esas expectativas y confirma 404 para producto ajeno separado. |
| Pruebas heredadas afirman `usuario_id` obligatorio para Admin/Bodeguero | Buscar todos los POST de alta que mandan el campo; probar omisión y valores inválidos/ajenos ignorados, sin alterar payload de despacho. |
| Rol autorizado sin sede departamental | 409 de servicio previo a cualquier escritura; pruebas por rol y sin fallback a sede del usuario. |
| UI aún ofrece autor alternativo o desaparece el catálogo | Test DOM comprueba campo read-only y no-select; GET catálogo conserva `solicitantes`. |
| Evidencia de AC-6/15 describe semántica antigua | Reescritura de evidencia solo en implementación/cierre, no declarar verificación aquí. |

Sin cambios a la matriz, guards, autenticación Clerk, DDL/modelos, dependencias, catálogo `solicitantes` como read model, Superadmin 403, reglas de producto, prioridad/estado, transacción, historial o despacho.

### Trazabilidad de enmienda AC ↔ componentes

| AC | Componentes |
|---|---|
| AC-6 actualizado | schema, servicio, tests backend, OpenAPI; conserva autorización/propiedad/matriz |
| AC-18 | servicio, tests API por rol/institución y conservación de 404 por producto |
| AC-19 | UI compartida de tickets y tests Angular |
| AC-20 | servicio, tests de sede con/sin asignación y no mutación |

Los paths de documentación del cierre son condicionales a que la revisión encuentre referencias obsoletas o cambios de arquitectura permanentes; el implementador no altera requisitos aprobados, salvo registrar evidencia al cierre conforme al flujo SDD.

## 3. Decisiones técnicas

### 3.1 Dependencia de rol sobre la identidad Clerk local

La dependencia de autorización depende de `get_current_user`, no vuelve a validar Clerk ni consulta una identidad paralela. Recibe los roles permitidos como parámetro de fábrica/declaración y compara el nombre local exacto. La identidad inyectada al endpoint/servicio se obtiene de la misma dependencia para evitar doble resolución en una petición (FastAPI cachea dependencias equivalentes) y permite mantener la lógica HTTP ligera.

**Alternativa descartada:** validar rol dentro de cada endpoint de forma manual, porque duplica política y facilita omisiones; también se descarta reutilizar rol/claims de Clerk porque Feature 006 establece el rol local como fuente.

### 3.2 Matriz central por operación y filtros en servicios

Una matriz central expresa permisos por operación, con las excepciones específicas reflejadas en rutas/servicios. La dependencia aplica permiso general; los servicios aplican alcance de datos, atribución y ocultación 404 porque estas reglas necesitan entidad/contexto de base de datos y deben preceder a mutaciones.

**Alternativa descartada:** roles amplios por router o permisos por nombre de pantalla: no representan diferencias de método HTTP, filtrado, rol asignable y ticket ajeno exigidas por D-3.

### 3.3 Servicio recibe identidad, no solo `usuario_id`

Pasar `IdentidadAutenticada` a los servicios que operan con permisos/datos limitados; el servicio resuelve con ORM las relaciones departamento/institución y rol según sea necesario. No enviar flags de confianza (`es_superadmin`, institución elegida por cliente) desde frontend ni aceptar el `departamento_id` del solicitante como fuente de alcance.

**Alternativa descartada:** calcular institución en frontend/endpoint y pasarla como dato confiable, pues abre bypass y mezcla regla de dominio con transporte.

### 3.4 Filtros ORM sin alterar contrato de catálogo global

Aplicar filtros de institución usando joins explícitos por Departamento para inventario/movimientos/tickets/usuarios. Los filtros agregados se llevan a las consultas Core/ORM existentes; conservar `stock_total` global en `GET /tickets/catalogos` y `GET /inventario/existencias` salvo el filtro de departamento ya solicitado/regulado, sin presentar el agregado de catálogo como valor institucional. Departamentos ajenos explícitos dan 403, no una lista vacía.

**Alternativa descartada:** particionar producto/categoría o cambiar el significado de `stock_total` en esta entrega; eso contradice el límite aprobado que asigna ese trabajo a 008.

### 3.5 Migración SQL idempotente y aplicable a volumen existente

Mantener DDL base limpio para volúmenes nuevos y un script numerado posterior a `02_datos_semilla.sql`, con `DROP COLUMN IF EXISTS`, diseñado para ejecutar tanto manualmente en una instancia ya creada como en una instalación nueva si se invoca explícitamente. Incluir comando `docker exec ... psql ... -v ON_ERROR_STOP=1` en instrucciones del script/tarea. Verificar en PostgreSQL 16; tests SQLite cubren el resto del backend, no demuestran semántica del DDL PostgreSQL.

**Alternativa descartada:** modificar solo `01_esquema.sql`, que no se vuelve a ejecutar en volúmenes existentes; usar initdb para la migración, que tampoco se ejecuta en esos volúmenes; resetear volumen, que perdería datos y está expresamente prohibido.

### 3.6 Sin dependencia nueva; TDD y validación por ambas suites

Usar FastAPI `Depends`, SQLAlchemy ORM/Core tipado y el harness actual; Angular signals y guards standalone ya instalados. Backend: `pytest` con pruebas HTTP por roles y servicios; frontend: `ng test --watch=false --browsers=ChromeHeadless` con `CHROME_BIN` configurado a Edge en esta máquina. PostgreSQL 16 real para idempotencia y preservación de migración; `/openapi.json` para seguridad/status/contratos. No añadir paquetes.

**Alternativa descartada:** incorporar motor genérico de políticas/ACL o migrador nuevo, innecesario para la matriz fija de cuatro roles y sin justificación de dependencias.

## 4. Estrategia de integración y riesgos

Orden de integración: (1) tests backend de dependencia/matriz y 401/403; (2) contexto/ámbito institucional y pruebas de servicios; (3) atribución/propiedad/creación y transición/despacho conservando ACID; (4) retiro ORM/schema/fixtures y migración PostgreSQL; (5) guard y vistas Angular con tests; (6) regresión completa y contrato OpenAPI; (7) verificación manual 4200 y build/smoke 8080; (8) evidencia por AC y coherencia documental.

Riesgos principales: cobertura incompleta entre los 18 endpoints de D-3; fuga por rutas directas pese al guard; consultas de instituciones sin resolver tratadas erróneamente como globales; filtrar solo lista pero no mutación por id; que Solicitante seleccione `usuario_id` o enumere solicitantes ajenos; pérdida de atomicidad al añadir control pre-despacho; discrepancia PostgreSQL/SQLite; y falso resultado al probar 8080 sin reconstruir. Mitigación: pruebas parametrizadas para cada endpoint/rol, pruebas de no mutación, tests con instituciones/departamentos cruzados, pruebas PostgreSQL para migración, y cierre condicionado a evidencia real en los dos puertos.

## 5. Cobertura AC → piezas

| AC | Pieza principal |
|---|---|
| AC-1 | Literales/matriz backend y guard Angular exactos; pruebas de rol ausente/desconocido. |
| AC-2 | `RolGuard`, denegación dedicada, rutas y tests de navegación/espera. |
| AC-3 | Configuración de rutas/capacidades de dashboard, inventario y tickets/administración; pruebas por rol. |
| AC-4 | `AutenticacionGuard` conservado y regresión de redirección a login con retorno. |
| AC-5 | Tabla de rutas de UI, guard sesión+rol y prueba de rutas públicas/raíz. |
| AC-6 | Servicio/endpoints de tickets: propiedad, atribución, 403 general y 404 oculto. |
| AC-7 | Permisos Bodeguero, filtros institucionales, prohibición usuarios/productos y mutaciones no autorizadas. |
| AC-8 | Filtros de institución, resolución departamento/institución, parámetro ajeno y acceso global exclusivo. |
| AC-9 | Matriz backend completa, 401/403/404, catálogo global y filtro de solicitantes. |
| AC-10 | Regla de rol asignable en creación de usuario sin mutación al denegar. |
| AC-11 | DDL/semilla/docstrings corregidos. |
| AC-12 | Modelo, schema y fixtures sin contraseña; revisión de referencias/runtime. |
| AC-13 | Migración PostgreSQL idempotente con preservación de datos y relaciones. |
| AC-14 | Suite integrada sin consultas/uso de `usuario.password`; Clerk y operaciones funcionales. |
| AC-15 | Pruebas backend/frontend y OpenAPI de denegaciones. |
| AC-16 | Verificación de migración en PostgreSQL y suites completas verdes. |
| AC-17 | Evidencia por AC, OpenAPI, recorrido 4200 y 8080 reconstruido, grep de coherencia. |

---

## Enmienda de alta reservada al Solicitante (26/Nov/2026)

> Plan de la enmienda aprobada en `spec.md` (D-11…D-18, AC-21…AC-34). Cambia **una fila** de
> la matriz y su contrato; no crea operaciones, DDL, capacidades ni flujos. La implementación
> va en una sola pasada: backend y contrato → pruebas → suites → frontend/documentación →
> cierre. No existe feature 028: todo pertenece a la 007.

### Enfoque técnico por capa

- **Autorización.** La fila `("POST", "/api/v1/tickets/")` de `MATRIZ_PERMISOS` queda en
  `frozenset({_SOLICITANTE})`. Se elimina `_ESCRITURA_TICKETS` porque su único uso era esa
  fila y su nombre promete tres roles. Ninguna otra entrada se toca; la matriz sigue con 75
  operaciones. `requiere_operacion` ya produce el 403 antes del cuerpo y antes de
  `get_db_negocio`; no se modifica la dependencia ni su orden.
- **Contrato.** En `backend/app/api/v1/endpoints/tickets.py` se actualiza **solo la
  `description`** de `crear_ticket`: declara que únicamente el Solicitante crea y por qué
  Administrador, Bodeguero y Superadmin reciben 403. No se añade `respuesta_conflicto()` ni
  el 409 a `responses` (hoy el 409 vive solo en la descripción); no cambian `response_model`,
  `status_code=201`, `responses` ni las dependencias.
- **Servicio.** En `backend/app/services/ticket_service.py` se actualiza **solo el docstring**
  de `crear_ticket`, que enumera Administrador/Bodeguero/Solicitante. No se añade comprobación
  de rol: la autoatribución, el orden de validaciones, la institución/sede, `Pendiente`, la
  transacción y el historial de creación quedan intactos (D-12).
- **Pruebas backend.** Un archivo nuevo de aceptación cubre AC-21…AC-25, AC-28 y AC-31 con la
  app real; AC-26/AC-27 se añaden al arnés de institución inactiva; las seis transcripciones
  de la matriz y `test_correlacion_024.py` se actualizan; las suites que hacen altas pasan a
  un cliente Solicitante, y los fixtures históricos de autoría Admin/Bodeguero se siembran por
  ORM.
- **Presentación.** Solo comentarios y títulos de pruebas en `roles.ts`, `roles.spec.ts`,
  `tickets.component.ts` y `tickets.component.spec.ts`. El botón ya está oculto desde el
  25/Nov/2026; **no** se añade guarda de apertura ni cambia comportamiento.
- **Documentación.** Se anota la transcripción de `012-gestion-administrativa/diseno-tecnico.md`;
  al implementar se actualizan la fila de la 007 en `roadmap.md` y `MEMORY.md`, sin anunciar
  una feature 028. La nota de la 003 ya está hecha en `spec.md`.
- **Cierre.** `pytest`, `ng test` (Edge/ChromeHeadless), `/openapi.json`, recorrido 4200 y humo
  8080 tras reconstruir la imagen, grep de coherencia y evidencia AC por AC.

### Archivos que se modifican

| Archivo | Responsabilidad | AC |
|---|---|---|
| `backend/app/core/permisos.py` | Fila del alta a `{Solicitante}`; retirar `_ESCRITURA_TICKETS`; comentario que cita la enmienda. Sin tocar otra fila. | AC-21…AC-29 |
| `backend/app/api/v1/endpoints/tickets.py` | Descripción del alta con el rol autorizado y el 403. Sin cambios de contrato declarado. | AC-29 |
| `backend/app/services/ticket_service.py` | Docstring de `crear_ticket` alineado con el rol único. Sin lógica nueva. | AC-34 |
| `backend/tests/conftest.py` | Identidad mutable, `actuar_como`, usuarios persistidos de Bodeguero/Solicitante y restauración de overrides. | AC-21…AC-33 |
| `backend/tests/funcional/integracion/test_alta_solo_solicitante_007.py` (nuevo) | Aceptación AC-21…AC-25, AC-28, AC-31. | AC-21…AC-25, AC-28, AC-31 |
| `backend/tests/no_funcional/seguridad/test_institucion_inactiva_012.py` (dos casos nuevos al final) | AC-26/AC-27 con la app real y el endpoint de alta, reutilizando `_preparar`. | AC-26, AC-27 |
| `backend/tests/no_funcional/seguridad/test_permisos.py`, `test_permisos_008.py`, `test_permisos_010.py`, `test_permisos_012.py`, `test_permisos_endpoints.py` | Transcripciones históricas con la restricción documentada. | AC-29, AC-33 |
| `backend/tests/funcional/integracion/test_ciclo_vida_autorizacion_013.py` | Sexta transcripción: `RESTRINGIDAS_013` incluye el alta. | AC-29, AC-33 |
| `backend/tests/no_funcional/seguridad/test_correlacion_024.py` | El POST del cliente legacy pasa a esperar 403. | AC-33 |
| `backend/tests/funcional/**` (14 suites del inventario) | Altas vivas con Solicitante; operaciones conservadas por rol. | AC-21, AC-30, AC-33 |
| `frontend/src/app/core/auth/roles.ts`, `roles.spec.ts`, `frontend/src/app/features/tickets/tickets.component.ts`, `tickets.component.spec.ts` | Comentarios y títulos dejan de hablar de demo; sin cambio de comportamiento. | AC-32, AC-34 |
| `docs/spec/features/012-gestion-administrativa/diseno-tecnico.md` | Nota de superación de su transcripción de `POST /tickets/`. | AC-34 |
| `docs/spec/roadmap.md`, `MEMORY.md` | Fila/estado de la 007 con la enmienda; sin feature 028. | AC-34 |

### Decisiones técnicas

#### DT-1 — Fila de matriz con `frozenset({_SOLICITANTE})`

Se reutiliza el literal existente y se elimina `_ESCRITURA_TICKETS`, que solo alimentaba esta
fila. El comentario cita la enmienda del 26/Nov/2026 y el 403 de Administrador/Bodeguero.

**Alternativa descartada:** conservar `_ESCRITURA_TICKETS` con un solo rol. Dejaría un nombre
que sugiere tres roles y una constante sin uso real; el lector tendría que comprobar que ya no
significa lo que dice.

#### DT-2 — Sin comprobación de rol en `crear_ticket`

La matriz y la dependencia del endpoint son la única frontera. El servicio sigue recibiendo la
identidad ya resuelta y autoatribuyendo; no pregunta por el rol.

**Alternativa descartada:** `if rol != "Solicitante"` en el servicio. Duplicaría la política,
divergiría de la matriz y bloquearía la creación interna sin sesión (ticket automático de la
016), que no tiene rol de sesión.

#### DT-3 — Solo la descripción del contrato; el 409 no se declara

`POST /tickets/` mantiene `responses` con 201, 401, 403, 404 y 422. El 409 sigue únicamente en
la descripción y esta enmienda no lo convierte en respuesta declarada.

**Alternativa descartada:** añadir `respuesta_conflicto()` para documentar el 409. Cambiaría el
contrato declarado en una enmienda cuyo alcance es una fila de roles y obligaría a revisar
todas las aserciones de OpenAPI; el 409 ya está explicado en la descripción.

#### DT-4 — Identidad mutable + `actuar_como(rol)` en `conftest`

`_cliente_de_prueba` deja de fijar `identidad_de_prueba` directamente y recibe un contenedor
`identidad_actual = {"actual": identidad_de_prueba()}`. El override es
`lambda: identidad_actual["actual"]`, de modo que el rol se lee en cada petición. Un fixture
`actuar_como(rol)` cambia el contenido del contenedor y devuelve la identidad; el `TestClient`
es el mismo. Así un test crea con Solicitante y aprueba/despacha con Administrador/Bodeguero
sin abrir un segundo cliente ni pisar overrides.

El fixture `cliente` conserva su valor por defecto (Administrador) y su firma; `cliente` y
`cliente_sin_excepcion` comparten el contenedor. `_cliente_de_prueba` guarda y **restaura** los
overrides que instala en lugar de `app.dependency_overrides.clear()`, para que un cliente
anidado o un helper que ya overridea `get_current_user` no borre el estado del otro. Se añade
un fixture de conveniencia `cliente_solicitante` que cambia el contenedor y devuelve el mismo
`cliente`.

**Alternativa descartada:** un `cliente_como(rol)` que construye un `TestClient` por rol. Los
`with` anidados comparten `app.dependency_overrides` y el `clear()` del interior borraría la
identidad del exterior; además reinstalaría la frontera Clerk en cada nivel. El contenedor
mutable evita ambos problemas con un solo cliente.

#### DT-5 — Usuarios persistidos mínimos y sede por suite

`datos_base` **no** se amplía globalmente: añadir un rol/usuario Solicitante cambiaría conteos
de catálogos y de administración en muchas suites. El helper
`identidad_persistida(datos_base, rol)` garantiza, de forma idempotente:

- **Administrador:** reutiliza `datos_base["usuario_id"]` (Ana, INST01, departamento
  `datos_base["departamento_id"]`).
- **Bodeguero:** busca o crea un usuario con `datos_base["rol_bodeguero_id"]` en ese mismo
  departamento; expone `datos_base["usuario_bodeguero_id"]`.
- **Solicitante:** busca o crea el rol `Solicitante` (si `dos_instituciones` ya lo creó, lo
  reutiliza) y un usuario en el mismo departamento; expone
  `datos_base["usuario_solicitante_id"]` y `datos_base["rol_solicitante_id"]`.
- **Superadmin:** identidad suelta con `Rol("Superadmin")`, sin persistencia: el 403 de matriz
  ocurre antes de la base.

La identidad es un `Usuario` suelto con el `usuario_id` real y el `departamento_id` real (el
patrón de `_soporte_sede_011.cliente`/`cliente_con_rol`). La **sede no se autoasigna**: cada
suite sigue resolviéndola con `asegurar_sede_de_departamento` o su helper, para no romper los
casos que esperan 409 sin sede. El alta del Solicitante necesita un producto de su institución
y el estado `Pendiente`, que ya provee `datos_base`.

**Alternativa descartada:** agregar el Solicitante a `datos_base` para todas las suites. Es
más simple de escribir, pero altera el catálogo base de rol/usuarios que usan las pruebas de
administración y de catálogo de tickets; el coste de regresión supera el ahorro.

#### DT-6 — Fixtures históricos por ORM, no por alta de Solicitante

Los tickets con autoría Administrador/Bodeguero que prueban AC-31/AC-43 se siembran por ORM
con `Ticket`/`DetalleTicket`/`HistorialTransicionTicket`, siguiendo
`test_ciclo_vida_confirmacion_013.py::_sembrar_cerrado`. No se crean con el alta del
Solicitante ni se reasignan después.

**Alternativa descartada:** crear el ticket con el Solicitante y actualizar `usuario_id` a
Administrador. Produciría un historial de creación con un actor que no es el autor y
falsificaría el escenario que AC-31/AC-43 quieren probar.

#### DT-7 — Transcripciones de matriz por restricción documentada

Las cinco `test_permisos*.py` y `test_ciclo_vida_autorizacion_013.py` conservan sus baselines
históricos y aplican la nueva restricción con el mismo patrón de `RESTRINGIDAS_013` (un mapa
`("POST", "/api/v1/tickets/") -> {"Solicitante"}`). `test_permisos_008.py` documenta la
excepción a `OPERACIONES_AJUSTADAS` porque su aserción actual exige que el Administrador
conserve todas esas escrituras.

**Alternativa descartada:** reescribir los baselines con el valor nuevo. Perdería la
trazabilidad de que la 007/008/010/012/013 transcribieron tres roles y haría indistinguible un
cambio de regla de un error de transcripción.

### Harness de identidad Solicitante (diseño concreto)

```python
@pytest.fixture
def identidad_actual():
    return {"actual": identidad_de_prueba()}          # Administrador por defecto

@pytest.fixture
def cliente(motor, identidad_actual):
    with _cliente_de_prueba(motor, identidad_actual) as c:
        yield c

@pytest.fixture
def actuar_como(datos_base, identidad_actual):
    def _cambiar(rol: str):
        identidad_actual["actual"] = identidad_persistida(datos_base, rol)
        return identidad_actual["actual"]
    return _cambiar

@pytest.fixture
def cliente_solicitante(cliente, actuar_como):
    actuar_como("Solicitante")
    return cliente
```

`_cliente_de_prueba` cambia su override por
`app.dependency_overrides[get_current_user] = lambda: identidad_actual["actual"]` y restaura
las claves que tocó en el `finally`. `cliente_sin_excepcion` recibe el mismo contenedor.
`identidad_persistida(datos_base, rol)` es el helper descrito en DT-5; para `Superadmin`
devuelve una identidad suelta.

Reglas de uso:

- Un test puede alternar `actuar_como("Solicitante")` → alta, `actuar_como("Administrador")` →
  aprobación/despacho, `actuar_como("Bodeguero")` → rechazo/recepción, sin recrear el cliente.
- No se anidan `cliente` y `cliente_sin_excepcion` en el mismo test; si se necesita un 500, se
  usa el segundo como único cliente.
- Las pruebas de 401 no usan `cliente` (que inyecta identidad): usan un cliente sin override
  de `get_current_user` o la variante `SIN_AUTENTICAR` de `_soporte_sede_011`.
- Las suites que ya usan `cliente_con_rol`/`_soporte_sede_011.cliente` pueden conservarlo;
  no se migran a la fuerza. El contenedor es para las suites que usan el `cliente` de
  `conftest`.

### Estrategia de pruebas

#### Backend

1. **Nuevo `test_alta_solo_solicitante_007.py`** (integración, app real):
   - AC-21: Solicitante con sede y payload válido → 201; autoría de sesión; `usuario_id` del
     payload omitido/propio/ajeno/inexistente ignorado; institución/sede/`Pendiente`/historial;
     422/404/409 del alta con las reglas vigentes.
   - AC-22/AC-23: Administrador y Bodeguero con payload válido → 403 y conteos de `Ticket`,
     `DetalleTicket` e `HistorialTransicionTicket` sin cambios.
   - AC-24: payload JSON parseable pero inválido para el contrato (asunto corto, `detalles`
     vacío, cantidad no positiva, campo extra, `estado_id` ausente) → 403 para
     Administrador/Bodeguero; mismo caso con Solicitante → 422. Un JSON malformado no se usa
     para afirmar 403.
   - AC-25: Superadmin → 403 con JSON parseable válido o inválido.
   - AC-28: capacidad `tickets` apagada → 403 para Solicitante y para Admin/Bodeguero;
     rehabilitada → 201. Reutilizar el patrón `_sembrar_contexto_capacidades` de
     `test_ciclo_vida_confirmacion_013.py` (promoverlo a `_soporte_ciclo_vida_013.py` si se
     importa desde dos archivos) y usar su correo de contexto en la identidad del Solicitante;
     si el correo no resuelve contexto, el gating no se aplica y el test mediría otra cosa.
   - AC-31: ticket histórico sembrado por ORM con autor Administrador; se lee, conserva autor y
     el Administrador puede aprobarlo/despacharlo según estado; sin confirmación de entrega.
2. **AC-26/AC-27** en `test_institucion_inactiva_012.py` (dos casos nuevos al final, con
   `TestClient(app)` real y overrides de `get_db`/`get_current_user`, reutilizando
   `_preparar`): 401 sin/invalid token; con institución inactiva, Administrador/Bodeguero →
   403 por matriz y Solicitante → 401 del contexto de tenant; sin filas. No reordenar
   dependencias.
3. **Matriz y contrato.** Actualizar las seis transcripciones; `test_permisos_endpoints.py`
   pasa `MATRIZ_D3[("POST", "/api/v1/tickets/")]` a `{"Solicitante"}` y sus casos
   permitidos/denegados se regeneran; el caso permitido usa Solicitante. En
   `test_permisos_008.py`, además de la comparación viva, `CASOS_AJUSTADOS` debe esperar 403
   para Administrador/Bodeguero y 200 para Solicitante en el alta, y
   `test_administrador_conserva_las_escrituras_institucionales` excluye esa entrada.
   `test_correlacion_024.py` cambia `(400, 401, 422)` por 403.
4. **Suites de altas vivas.** Adaptar con `actuar_como`/`cliente_solicitante` y, donde falte,
   `asegurar_sede_de_departamento`:

   | Suite | Cambio |
   |---|---|
   | `humo/test_smoke.py` | Alta por Solicitante; el resto de humo conserva Admin. |
   | `e2e/test_transaccion_ticket.py` | Alta por Solicitante; casos de detalle inválido siguen esperando 422/404. |
   | `integracion/test_modal_ticket.py` | Alta por Solicitante; catálogo y payload sin `usuario_id` intactos. |
   | `integracion/test_tablero_kanban.py` | Alta por Solicitante; transiciones con Admin/Bodeguero. |
   | `e2e/test_despacho_transaccional.py` | Helpers `abrir_ticket_en_curso`/`crear_ticket_en_estado` crean por Solicitante y despachan por Bodeguero/Admin. |
   | `integracion/test_ciclo_vida_alta_inicial_013.py` | Alta por Solicitante; 422/404/409 del alta intactos. |
   | `integracion/test_ciclo_vida_historial_013.py` | `_crear_ticket_via_api` con Solicitante; ya tiene `_cliente_solicitante`. |
   | `e2e/test_flujo_aprobacion_entrega_013.py` | `_alta` por Solicitante; aprobación/despacho/confirmación por rol. |
   | `integracion/test_ticket_proceso_013.py` | `test_ac_39_el_201_del_alta_publica_el_read_model` crea por Solicitante; la etiqueta se lee con Admin. |
   | `integracion/test_ticket_sede_011.py` | `cliente_con_rol(..., "Administrador")` del alta pasa a Solicitante; el despacho conserva Bodeguero/Admin. |
   | `integracion/test_historial_movimientos.py` | Alta por Solicitante; el historial de stock y el despacho no cambian. |
   | `integracion/test_validacion_entradas_027.py` | Alta por Solicitante para 422/404/409; los 403 de Admin/Bodeguero se añaden en el archivo nuevo. |
   | `integracion/test_tickets_alcance.py` | Reemplazar la parametrización de alta por rol: Solicitante 201; Admin/Bodeguero 403. `test_administrador_crea_para_solicitante_propio_201` y `test_administrador_ignora_solicitante_de_otra_institucion_y_atribuye_a_sesion` pasan a denegación 403 (o se retiran como alta) y la autoatribución se conserva con Solicitante. Conservar propiedad/listado. |
   | `integracion/test_tickets_institucional.py` | Alta por Solicitante; producto ajeno 404 sin parcial. |
   | `no_funcional/seguridad/test_correlacion_024.py` | Solo la expectativa de estado, no las aserciones de log. |

5. **Fixtures históricos.** Auditar los escenarios que necesitan autoría Admin/Bodeguero
   (AC-31 y AC-43) y sembrarlos por ORM; no convertirlos en altas de Solicitante. Las suites
   de cobertura 021 y Compras no se tocan: siembran por ORM o no hacen POST de tickets.

#### Frontend

- `roles.ts`: el comentario de `ROLES_CREACION_TICKETS` pasa de «cambio de demo» a espejo de la
  matriz.
- `tickets.component.ts`: el comentario de `puedeCrearPedido` deja de decir que la API admite a
  los tres roles.
- `roles.spec.ts`: el título de la prueba deja de decir «demo 25/Nov/2026».
- `tickets.component.spec.ts`: el `describe` de alta por rol deja de decir «demo»; los casos de
  botón visible/oculto se conservan sin cambios de expectativa.
- Sin guarda de apertura, sin cambios de template ni de servicio.

#### Contrato y cierre

- `/openapi.json`: 75 operaciones v1 y 77 totales (75 + `GET /` + `/health`); `POST` declara
  201/401/403/404/422, la descripción nombra al Solicitante y el 409 sigue solo en el texto.
- 4200: Solicitante crea; Administrador y Bodeguero reciben 403 por API; el tablero y las
  operaciones de su rol siguen funcionando.
- 8080: `docker compose -f docker-compose.yml build frontend` + `up -d frontend`; humo de la
  vista y del botón.
- Grep final en `docs/`, `backend/` y `frontend/`.

### Trazabilidad AC-21…AC-34

| AC | Componentes / pruebas |
|---|---|
| AC-21 | `permisos.py` (fila), `crear_ticket` sin cambio funcional, `test_alta_solo_solicitante_007.py` (201, autoría, 422/404/409) |
| AC-22 | Matriz + `test_alta_solo_solicitante_007.py` (403 Admin, conteos) |
| AC-23 | Matriz + mismo archivo (403 Bodeguero, conteos) |
| AC-24 | Mismo archivo (payload JSON parseable inválido → 403; Solicitante → 422) |
| AC-25 | Mismo archivo (Superadmin 403) |
| AC-26 | `test_institucion_inactiva_007.py`/`test_institucion_inactiva_012.py` (401) |
| AC-27 | Mismo archivo (Admin/Bodeguero 403; Solicitante 401 de tenant) |
| AC-28 | `test_alta_solo_solicitante_007.py` (capacidad apagada/rehabilitada) |
| AC-29 | `permisos.py`, descripción de `tickets.py`, `test_permisos_endpoints.py`, `/openapi.json` |
| AC-30 | Suites de roles de tickets (lectura, aprobación, despacho, rechazo, PATCH, confirmación) |
| AC-31 | `test_alta_solo_solicitante_007.py` + fixtures ORM de AC-43 |
| AC-32 | `roles.ts`, `tickets.component.ts`, `roles.spec.ts`, `tickets.component.spec.ts` |
| AC-33 | Seis transcripciones, `test_correlacion_024.py`, suites del inventario, `conftest.py` |
| AC-34 | Comentarios/docstrings, `diseno-tecnico.md` 012, `roadmap.md`, `MEMORY.md`, grep |

### Riesgos y alcance no tocado

| Riesgo | Mitigación |
|---|---|
| El refactor de `conftest` rompe suites que dependen del override global | Mantener `cliente` como Administrador por defecto y la misma firma; ejecutar la suite completa tras la tarea del harness; restaurar overrides en vez de `clear()`. |
| Un test alterna roles y el contenedor conserva el último rol | El contenedor es function-scoped; cada test lo reinicia. `actuar_como` es explícito antes de cada petición. |
| `test_permisos_008.py` exige al Administrador en `OPERACIONES_AJUSTADAS` | Excepción documentada para el alta; el resto de operaciones ajustadas se conserva. |
| `test_correlacion_024.py` deja de ejercer un 422 | Su propósito es el log sin secretos; se actualiza el estado esperado a 403 y se conservan las aserciones de redacción. |
| `identidad_persistida` crea usuarios y altera conteos de administración | Solo se invoca cuando el test pide ese rol; las suites que cuentan usuarios/roles ajustan su expected o siembran su propio usuario. `datos_base` no cambia para el resto. |
| Un fixture histórico se convierte en alta de Solicitante y AC-43 deja de probar lo que dice | Sembrar por ORM con `usuario_id` Admin/Bodeguero; prohibido reasignar autores. |
| Añadir el 409 a `responses` por inercia | Revisar el decorador: solo `description`; el 409 no se declara. |
| Reordenar dependencias para “arreglar” la institución inactiva | No se toca el orden: Admin/Bodeguero 403 por matriz; Solicitante 401 de tenant. |
| Verificar 8080 sin reconstruir | `docker compose build frontend` + `up -d frontend` antes del humo; comprobar el hash del bundle. |

**No se toca:** DDL, `database/01_esquema.sql`, `database/02_datos_semilla.sql`, versión
`026.0`, tablas/entidades, autenticación Clerk, capacidades, modelo de datos, servicio de alta
en su comportamiento, `GET /tickets/catalogos`, listado/detalle/historial, tablero, aprobación,
despacho, rechazo, anulación, edición, `PATCH /estado`, confirmación de entrega, cobertura 021
ni Compras.
