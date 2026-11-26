# Feature 007: Control de acceso por roles y retiro de credenciales locales

**Estado:** Cerrada y verificada; con enmienda posterior cerrada (26/Nov/2026)  
**Release:** 2.0 — Sprint 3  
**Tipo:** Autorización y saneamiento de credenciales

> **Enmienda posterior al cierre (22/Oct/2026):** la Feature 007 permanece cerrada y
> verificada. Esta enmienda posterior solo ajusta presentación/contrato de alta de ticket;
> no cambia la matriz de roles, DDL, dependencias ni permisos por operación.

> **Enmienda posterior al cierre (26/Nov/2026):** la Feature 007 sigue cerrada y verificada
> en su alcance original. Esta segunda enmienda restringe la fila de `POST /tickets/` de la
> matriz al **Solicitante** y supera el alcance de roles de AC-6, AC-18 y AC-20; no cambia nada
> más de la matriz, el DDL, las dependencias, la autenticación ni las capacidades. Ver
> «Enmienda posterior al cierre: alta de tickets reservada al Solicitante — 26/Nov/2026», al
> final de §7.

## 1. Problema

La Feature 006 incorporó Clerk como autoridad de autenticación y expone el rol local
resuelto en la identidad autenticada. Sin embargo, dicho rol todavía es informativo:
las rutas de negocio permiten acceso a cualquier usuario con sesión y los permisos
no se verifican al invocar directamente la API. Esto deja expuestas operaciones
administrativas, de bodega y de solicitud a identidades que no deberían utilizarlas.

Además, el campo `usuario.password` conserva credenciales de texto plano que no se
usan desde la integración con Clerk. Mantenerlas en el esquema, semilla y contratos
de usuario crea una copia innecesaria y riesgosa.

## 2. Objetivo

Autorizar las operaciones y vistas de Compustock ERP según el rol local de la identidad
autenticada, tanto en la navegación como en las solicitudes directas a la API; denegar
el acceso no permitido con una respuesta comprensible. Retirar el campo de contraseña
local del modelo funcional y de las bases, preservando los demás datos existentes.

## 3. Alcance

### Dentro

- Roles presentes en la semilla: `Superadmin`, `Administrador`, `Bodeguero` y
  `Solicitante`. Se mantienen como roles distintos; `Admin` es solo una abreviatura
  documental de `Administrador`, no un alias ni una normalización runtime.
- Aplicar la política de roles a las rutas de Angular y a las operaciones de negocio
  de backend. La política no confía en que la interfaz o el guard oculten operaciones.
- Acceso global del Superadmin. Administrador y Bodeguero quedan limitados a su propia
  institución para tickets, inventario y movimientos; Solicitante consulta el inventario
  de su institución derivada de su departamento.
- Acceso del Administrador a usuarios y departamentos de su institución; sus lecturas de
  instituciones se limitan a la propia.
- Acceso de Bodeguero a dashboard, inventario y gestión operativa de tickets, incluido
  Kanban, cambios de estado y despacho, limitado a su institución.
- Acceso de Solicitante a dashboard, consulta de inventario/catálogo y creación y
  consulta únicamente de sus propios tickets. No administra usuarios, cambia estados
  ni despacha.
- El catálogo de productos/categorías y `stock_total` en `GET /tickets/catalogos` son
  globales en 007; el particionamiento institucional se implementa en 008.
- Restricción de `POST /usuarios/`: Administrador solo puede asignar `Bodeguero` o
  `Solicitante`; Superadmin puede asignar cualquiera de los cuatro roles.
- Denegación de navegación o solicitud de negocio a identidades con rol distinto al
  requerido, sin alterar el flujo de autenticación Clerk existente.
- Retiro de `usuario.password` de la definición de esquema, datos semilla, modelo
  funcional, contrato de creación de usuario y fixtures/pruebas que lo envían o
  requieren.
- Migración SQL reproducible para eliminar la columna de bases existentes sin perder
  las demás filas ni datos. Las nuevas instalaciones se crean desde el esquema y la
  semilla ya sin ese campo.

### Fuera

- Particionamiento lógico completo del SaaS, incluido el particionamiento del catálogo
  y stock, y aprovisionamiento/gestión del ciclo de vida de instituciones. Los límites
  operativos institucionales expresamente definidos en 007 sí están dentro.
- Gestión completa del ciclo de vida de usuarios (edición, borrado y aprovisionamiento)
  y cambios a la autoridad Clerk. La autorización de la creación existente y la
  restricción del rol asignable por Administrador sí son alcance de 007.
- Permisos granulares configurables por institución o usuario; esta entrega usa roles
  de catálogo.
- Cambios de interfaz ajenos a navegación/denegación por rol, como rediseños o nuevas
  capacidades operativas.
- Borrado de usuarios, migración de contraseñas a hashes o autenticación local como
  alternativa a Clerk.

## 4. Actores

- **Superadmin**: administrador global; accede a las áreas permitidas a los roles
  administrativos y puede consultar/modificar datos de cualquier institución.
- **Administrador Institucional (`Administrador`)**: gestiona usuarios y catálogos, y
  accede a las áreas concedidas, limitado a su institución en los datos operativos.
- **Bodeguero**: opera inventario y flujo de tickets, incluyendo preparación y despacho,
  únicamente en su institución.
- **Solicitante**: consulta catálogo/inventario de su institución y gestiona la creación
  y consulta de sus propios tickets.

## 5. Decisiones

### D-1 — Los cuatro nombres de rol son identidades distintas

`Superadmin` y `Administrador` no se colapsan en un alias. `Admin` en el roadmap es una
abreviatura documental del rol local `Administrador`; no existe alias ni normalización
runtime. Se conservan los cuatro roles de la semilla.

### D-2 — La autorización se exige en cliente y servidor

Los guards mejoran la navegación, pero no constituyen una frontera de seguridad: un
usuario puede llamar la API sin usar Angular. Por ello, una operación no autorizada
queda denegada también por backend, manteniendo Clerk como requisito previo.

### D-3 — La matriz de permisos es explícita por operación

La fila de `POST /tickets/` conserva la matriz aprobada, con la semántica de
autoatribución establecida por la enmienda posterior de 22/Oct/2026; los roles permitidos
no cambian.

**Transcripción histórica:** la fila de `POST /tickets/` refleja la regla posterior de
autoatribución de la enmienda de 22/Oct/2026; no hubo cambio de roles permitidos.

La política de permisos y el límite institucional se describen operación por operación
en la matriz siguiente. Superadmin tiene alcance global. Administrador y Bodeguero solo
operan tickets, inventario y movimientos de su institución; Administrador también queda
limitado en usuarios/departamentos y consulta de instituciones. Solicitante consulta
existencias de su institución. El catálogo maestro de productos/categorías y
`stock_total` de `GET /tickets/catalogos` permanecen globales en 007 porque el modelo no
asigna institución a producto/categoría y el agregado suma inventario de todas las sedes.
Ese `stock_total` no representa stock institucional. El particionamiento de catálogo y
stock pertenece a Feature 008. La autorización se aplica en backend incluso si la ruta
o el control de interfaz resulta accesible.

| Operación | Superadmin | Administrador | Bodeguero | Solicitante |
|---|---|---|---|---|
| `GET /auth/me` | ✅ | ✅ | ✅ | ✅ |
| `GET/POST /usuarios/` y catálogos de apoyo (`/roles`, `/departamentos`, `/instituciones`) | ✅; asigna cualquier rol | ✅; usuarios/departamentos acotados, roles compartidos, instituciones solo propia; solo asigna Bodeguero/Solicitante | ❌ 403 | ❌ 403 |
| `GET /inventario/categorias`, `/productos`, `/existencias`, `/stock` | ✅ | ✅; catálogo maestro compartido, existencias/stock propios | ✅; catálogo maestro compartido, existencias/stock propios | ✅ solo lectura; catálogo maestro compartido, existencias/stock propios |
| `POST /inventario/productos` | ✅ | ✅, catálogo compartido | ❌ 403 | ❌ 403 |
| `GET /inventario/movimientos` y `POST /inventario/movimientos` | ✅ | ✅, solo inventario propio | ✅, solo inventario propio | ❌ 403 |
| `GET /tickets/catalogos` | ✅; productos y stock globales; solicitantes globales | ✅; productos y `stock_total` globales, solicitantes de institución propia | ✅; productos y `stock_total` globales, solicitantes de institución propia | ✅; productos y `stock_total` globales; solicitantes solo su identidad |
| `GET /tickets/` | ✅ | ✅, tickets de institución propia | ✅, tickets de institución propia | ✅, solo propios |
| `POST /tickets/` | ❌ 403 desde Feature 008/017 | ✅; autoatribución de sesión, `usuario_id` opcional e ignorado si se envía | ✅; autoatribución de sesión, `usuario_id` opcional e ignorado si se envía | ✅; siempre a su nombre, `usuario_id` opcional e ignorado si se envía |

> **Nota de enmienda:** esta fila mantiene los permisos preexistentes, pero su semántica
> de atribución sustituye la decisión histórica de elegir solicitante en D-3.
| `POST /tickets/{id}/despacho` y `PATCH /tickets/{id}/estado` | ✅ | ✅, tickets e inventario propios | ✅, tickets e inventario propios | ❌ 403 |

Las solicitudes con parámetros `departamento_id` de otra institución para
`/inventario/existencias` o `/stock` responden 403 para los roles limitados; no se
silencia ni se aplica un filtro alternativo. Los catálogos de prioridad/estado y roles
son compartidos.

> **Superación de la fila `POST /tickets/` (26/Nov/2026).** La fila de `POST /tickets/` de
> esta tabla es **histórica**: la enmienda del 26/Nov/2026 la restringe a **solo
> `Solicitante`**. La tabla, la nota de autoatribución y la evidencia de AC-18/AC-20 se
> conservan como registro; la regla vigente está en «Enmienda posterior al cierre: alta de
> tickets reservada al Solicitante — 26/Nov/2026», al final de §7.

### D-4 — Límites institucionales desde 007

La institución de Administrador, Bodeguero y Solicitante se determina mediante
`usuario.departamento_id` → `departamento.institucion_id`. Administrador y Bodeguero
solo leen/operan inventario, movimientos y tickets de esa institución. El Administrador
además limita usuarios/departamentos a la misma institución e instituciones consultadas
a la propia. Solicitante solo consulta inventario de su institución y sus propios
tickets. En lecturas de `/inventario/existencias` y `/stock`, `departamento_id` ajeno
responde 403, no se filtra silenciosamente.

El catálogo maestro de producto/categoría no tiene pertenencia institucional en el
esquema y permanece compartido. `stock_total` en el catálogo de tickets también es un
agregado global de todas las sedes, no un valor institucional. Feature 008 definirá el
particionamiento lógico integral y el alcance institucional definitivo del catálogo y
stock.

Si Administrador, Bodeguero o Solicitante carecen de departamento o no se puede resolver
su institución, las operaciones que requieren ese ámbito responden HTTP 403. Nunca se
concede alcance global ni se omite el filtro. Superadmin es el único rol global.

### D-5 — Denegación de permiso y ocultación de ticket ajeno

Una sesión ausente o no válida mantiene el comportamiento de autenticación existente
(401). Una identidad autenticada sin permiso general para la operación recibe 403. Si
una operación de ticket permitida para el rol busca un ticket inexistente o un ticket
ajeno al Solicitante, responde 404 en ambos casos para no revelar su existencia. En
Angular, una ruta no permitida muestra estado dedicado de acceso denegado y no redirige
a login ni ejecuta la operación.

### D-6 — La asignación de rol respeta la autoridad del creador

En `POST /usuarios/`, Superadmin puede asignar cualquiera de los cuatro roles.
Administrador solo puede asignar `Bodeguero` o `Solicitante`; si intenta asignar
`Superadmin` o `Administrador`, la API responde 403 y no crea el usuario. La regla no
cambia el contrato de `TicketCrear`; la gestión completa de usuarios queda fuera.

### D-7 — La contraseña local se elimina, no se sustituye

Clerk es la única autoridad de autenticación; no se conserva ni se crea un hash local.
La columna deja de formar parte de los registros de usuario y se retira mediante una
migración reproducible, ya que alterar solamente el DDL no actualizaría bases
previamente inicializadas.

### Enmienda D-8 — Todo ticket queda atribuido a la identidad autenticada

Para cada rol autorizado a ejecutar `POST /tickets/` según la matriz vigente, el servidor
establece `usuario_id` con la identidad autenticada, sin aceptar selección de solicitante.
El campo de payload `usuario_id` pasa a opcional y cualquier valor recibido se ignora
silenciosamente: omitirlo no es 422, enviar otro valor no es 403, y un valor inexistente o
ajeno no produce 404 por usuario. La regla de pertenencia institucional ahora se aplica a
la identidad del actor/autor, no a un usuario seleccionado; la matriz de permisos no se
abre a roles nuevos ni a operaciones antes denegadas.

**Por qué:** la autoría debe corresponder a la sesión que realiza la acción. El selector
contradice esa regla para Administrador/Bodeguero y era redundante para Solicitante, a
quien el servidor ya autoatribuía.

### Enmienda D-9 — El formulario identifica al autor sin permitir elegirlo

La UI de creación no presenta selector ni control editable `usuario_id`; muestra como
información no editable el nombre, apellido y correo de `AutenticacionService.identidad()`
(respuesta `/auth/me`). Esa identidad no contiene departamento, por lo que no se añade una
consulta adicional ni se afirma que el campo muestre el nombre departamental. El catálogo
`solicitantes` se conserva para listados y detalle, aunque deje de poblar selector de alta.

**Por qué:** interfaz y contrato deben expresar la misma autoría inmutable y evitar una
opción visual que el servidor no debe honrar.

### Enmienda D-10 — El ámbito organizacional del alta sigue a la identidad

El ticket se ancla a institución y departamento de la identidad de sesión; su instantánea
de sede sale del `departamento.sede_id` de esa identidad. Si el departamento no tiene sede,
el alta responde 409 sin fallback, también para Administrador o Bodeguero; si tiene sede,
se crea usando esa sede. La semilla vigente tiene departamentos con sede para todos sus
Administradores y Bodegueros de roles 2 y 3 (usuarios 1, 3, 4, 10 y 6, 7, 12); los
Bodegueros 6, 7 y 12 tienen además asignación de usuario a sede, pero esa asignación no
sustituye la regla de sede del departamento del alta. Superadmin conserva el 403 de la
matriz actual de Feature 008/017.

**Por qué:** el contexto efectivo se deriva del usuario local y no puede seleccionarse en
el cuerpo. `_sede_vigente_de_solicitante` sigue tomando la sede del departamento del
usuario autor.

## 6. Reglas del flujo

1. La identidad debe autenticarse con Clerk y vincularse al usuario local conforme a
   Feature 006.
2. La autorización obtiene el rol local; valores desconocidos, ausentes o no resolubles
   no conceden permisos.
3. En Angular, una navegación de negocio requiere sesión. Si el rol no está permitido,
   la ruta no se activa y se presenta el estado de acceso denegado.
4. En backend, cada operación compara rol y acción antes de ejecutar lecturas o
   mutaciones. La denegación no cambia datos.
5. Para Administrador, Bodeguero y Solicitante, las operaciones con datos
   institucionales requieren resolver su institución desde el departamento; si falla,
   responden 403. Solo Superadmin tiene alcance global.
6. Administrador y Bodeguero acceden a tickets, inventario y movimientos solo de su
   institución. Administrador también limita usuarios/departamentos a esa institución.
   Solicitante consulta inventario de su institución y solo sus tickets. Los parámetros
   de departamento ajeno en `/inventario/existencias` o `/stock` responden 403.
7. El catálogo de productos/categorías y `stock_total` en `/tickets/catalogos` son
   globales en 007; el total agrega todas las sedes y no se presenta como stock
   institucional. El particionamiento corresponde a 008.
8. Solicitante solo consulta tickets propios. Al crear, todo rol autorizado queda
   atribuido a su identidad autenticada: `usuario_id` es opcional y, si se envía, se
   ignora sin error. La institución y sede del ticket se derivan de esa identidad; una
   sede departamental ausente conserva el 409 de Feature 011. Superadmin continúa sin
   permiso para el alta. En `GET /tickets/catalogos`, `solicitantes` se conserva según el
   alcance vigente del rol; la lista no constituye autoridad de autoría.
9. Un Solicitante sin permiso general para PATCH estado o despacho recibe 403. En
   operaciones de ticket permitidas, un ticket ajeno e inexistente responden ambos 404.
10. En `POST /usuarios/`, Administrador solo asigna Bodeguero o Solicitante; Superadmin
    puede asignar cualquiera de los roles. La restricción no implica especificar alta o
    edición completa de usuarios.
11. La migración de contraseña elimina únicamente la columna obsoleta y deja inalterados
    usuarios, relaciones, roles y demás atributos.

## 7. Criterios de aceptación

### Roles y navegación

- **AC-1** DADO QUE la identidad tiene uno de los cuatro roles (`Superadmin`,
  `Administrador`, `Bodeguero`, `Solicitante`), ENTONCES se reconoce de forma
  diferenciada. `Admin` es solo abreviatura documental de `Administrador`, sin alias ni
  normalización runtime. Un rol ausente/desconocido no concede acceso.
- **AC-2** DADO QUE una persona autenticada navega a una sección permitida por su
  matriz, ENTONCES la ruta se activa; si no está permitida, no se activa y aparece el
  estado dedicado de acceso denegado, sin cerrar sesión ni redirigir a login.
- **AC-3** `Superadmin` y `Administrador` pueden acceder a dashboard, inventario,
  tickets y administración, conforme al límite institucional de AC-8. `Bodeguero` puede
  acceder a dashboard, inventario y operaciones de tickets, sin administración y solo
  sobre su institución. `Solicitante` puede acceder a dashboard, consulta de inventario,
  catálogo y creación/consulta de sus tickets, pero no a administración, Kanban, cambio
  de estado ni despacho.
- **AC-4** DADO QUE no existe sesión Clerk válida, CUANDO se intenta entrar a una ruta
  de negocio, ENTONCES se conserva la redirección existente a `/login` con retorno; la
  política de roles no suplanta ni debilita la autenticación.
- **AC-5** La tabla de rutas de interfaz es: `dashboard` (Superadmin, Administrador,
  Bodeguero, Solicitante), `inventario` (los cuatro, con alcance institucional según
  AC-8), `tickets` (los cuatro, con capacidades según AC-3/AC-6/AC-7) y
  `administracion` (Superadmin y Administrador). `/` conserva su redirección a
  `dashboard`, `/login` queda fuera del guard y `/health` sigue público sin cambio.

### Autorización de API y propiedad

- **AC-6** DADO QUE el rol es `Solicitante`, CUANDO ejecuta `GET /tickets/`, ENTONCES
  recibe solo tickets propios. CUANDO un rol autorizado ejecuta `POST /tickets/`,
  ENTONCES el ticket se atribuye a la identidad autenticada, con payload `usuario_id`
  opcional e ignorado si se envía, sin 422/403 ni 404 por ese campo incluso si su valor
  es inexistente o ajeno. Administrador y Bodeguero crean bajo su propia identidad y el
  ámbito institucional/sede se deriva de ella; Superadmin conserva 403 conforme a la
  matriz. No se permite elegir otro autor. Si el departamento de sesión carece de sede,
  el alta conserva 409; con sede, usa esa sede. Si Solicitante invoca `PATCH /tickets/{id}/estado` o
  `POST /tickets/{id}/despacho`, recibe 403 por falta de permiso general. Si una
  operación de ticket permitida intenta acceder a un ticket existente de otro usuario,
  recibe 404 igual que para un id inexistente y no modifica datos. Esta formulación de
  autoatribución reemplaza la decisión histórica de conservar `TicketCrear` obligatorio
  para otros roles y permitirles elegir solicitante.
- **AC-7** DADO QUE el rol es `Bodeguero`, ENTONCES puede listar, actualizar estado y
  despachar tickets, y leer/operar inventario y movimientos, solo dentro de su
  institución. Si intenta administrar usuarios o crear productos, backend responde 403.
- **AC-8** DADO QUE el rol es `Superadmin`, ENTONCES tiene alcance global para las
  operaciones permitidas. DADO QUE el rol es `Administrador` o `Bodeguero`, sus
  operaciones institucionales de tickets, inventario y movimientos se limitan a su
  institución; Administrador limita también usuarios/departamentos y solo consulta su
  institución en `/instituciones`. Solicitante consulta existencias de su institución y
  tickets propios. Un `departamento_id` ajeno en `/inventario/existencias` o `/stock`
  responde 403. Si la institución de Administrador, Bodeguero o Solicitante no se puede
  resolver para una operación institucional, responde 403. Solo Superadmin es global.
- **AC-9** La matriz de D-3 es el contrato backend por operación. Sesión ausente/no
  válida responde 401; rol sin permiso general responde 403. Para una operación de
  ticket permitida, ticket ajeno a Solicitante e id inexistente responden 404. En
  `/tickets/catalogos`, productos/categorías y `stock_total` son globales para todos los
  roles autorizados; `stock_total` suma todas las sedes y no se presenta como dato
  institucional. `solicitantes` para Solicitante contiene únicamente su identidad; para
  otros roles se conserva la lista de lectura dentro del alcance aplicable. La lista no
  alimenta la autoría del alta (enmienda D-9); Superadmin sigue sin permiso a la operación.
- **AC-10** En `POST /usuarios/`, Administrador puede crear usuarios con rol
  `Bodeguero` o `Solicitante`; si intenta asignar `Superadmin` o `Administrador`, recibe
  HTTP 403 y no se crea usuario. Superadmin puede asignar cualquiera de los cuatro
  roles. La autorización no cambia el contrato de creación para Superadmin en otros
  aspectos y no amplía el alcance a edición/gestión completa de usuarios.

### Retiro de contraseña local y coherencia

- **AC-11** En una instalación nueva, el esquema no declara `usuario.password` y la
  semilla inserta usuarios sin columna ni valores de contraseña. Los comentarios de la
  semilla no afirman que la autenticación sea decorativa ni que la contraseña se migre
  posteriormente. El docstring de `TicketDespacho` no califica la autenticación como
  decorativa y el de `role.guard.ts` no lo describe como inerte ni pospone su política
  de roles a una implementación futura.
- **AC-12** El modelo funcional y el contrato de creación de usuario no declaran ni
  requieren contraseña; las pruebas/fixtures crean usuarios sin contraseña y no
  transmiten credenciales locales. Ninguna ruta de autenticación consulta esa columna.
- **AC-13** DADA una base existente con usuarios y columna `usuario.password`, CUANDO se
  ejecuta la migración SQL versionada, ENTONCES la columna se elimina, preservando
  usuarios, claves/relaciones y demás tablas; repetirla o ejecutarla sobre una base ya
  actualizada no causa pérdida adicional ni falla por ausencia previa de la columna.
- **AC-14** Después de la migración, Clerk, `/auth/me`, autorización y operaciones de
  usuario funcionan sin consultar ni depender de `usuario.password`.

### Verificación y cierre

- **AC-15** Las pruebas backend comprueban permisos permitidos/denegados por rol y
  operación, 401/403/404, ausencia de mutación ante denegación, propiedad y atribución de
  tickets, compatibilidad aditiva de `TicketCrear` (`usuario_id` opcional e ignorado para
  todos los roles autorizados), alcance
  institucional de Administrador/Bodeguero/Solicitante, restricción de roles asignables,
  filtro de solicitantes, stock de catálogo global y 403 si no se resuelve institución.
  Las pruebas frontend cubren guards, espera de identidad/rol y acceso denegado; las
  pruebas de contrato describen las denegaciones pertinentes.
- **AC-16** La verificación de migración demuestra que conserva usuarios y relaciones,
  elimina `usuario.password` y se puede aplicar nuevamente con seguridad. `pytest` y
  `ng test` permanecen verdes.
- **AC-17** El cierre registra evidencia verificable por AC, revisa el contrato de API
  y realiza recorridos en 4200 y 8080, reconstruyendo frontend antes de comprobarlo.
  Conforme a AGENTS.md §8.7, revisa `AGENTS.md`, `MEMORY.md` y `.agents/skills/` para
  actualizar referencias obsoletas; AC-11 cubre los comentarios/docstrings identificados.

### Evidencia de verificación al cierre

Suites finales (T13): backend `pytest` → **377 passed, 2 warnings**; frontend
`ng test --watch=false --browsers=ChromeHeadless` (Edge 155) → **140 SUCCESS**; build de
producción frontend OK (T11, 320.55 kB) y reconstruido en la imagen `sha256:3862981…` que
sirve el 8080.

| AC | Evidencia |
|---|---|
| AC-1 | Backend: `test_permisos.py::test_cuatro_roles_exactos_sin_alias_admin`, `::test_rol_desconocido_responde_403`, `::test_rol_ausente_responde_403`; literales sin alias en `backend/app/core/permisos.py` (`RolConocido`) y `frontend/src/app/core/auth/roles.ts`. Frontend: `role.guard.spec.ts::compara el rol exacto: \`Admin\` no es un alias de \`Administrador\``, `::deniega un rol ausente/desconocido`. |
| AC-2 | Frontend: `role.guard.spec.ts` (espera identidad, activa permitido, no activa rol distinto, `::ante denegación no redirige a login ni cierra la sesión`); `acceso-denegado.component.spec.ts` (estado dedicado, vuelve al dashboard sin enlazar a `/login`); `app.routes.spec.ts::expone el estado de acceso denegado sin exigir rol`. `RolGuard` en `frontend/src/app/core/guards/role.guard.ts` devuelve `RUTA_ACCESO_DENEGADO` sin activar la ruta. |
| AC-3 | `app.routes.spec.ts::permite dashboard, inventario y tickets a los cuatro roles (AC-5)`, `::restringe administración a Superadmin y Administrador (AC-3, AC-5)`; `tickets.component.spec.ts::oculta las operaciones de Kanban al Solicitante`, `::ofrece las operaciones de Kanban a Bodeguero, Administrador y Superadmin`. |
| AC-4 | `app.routes.spec.ts::protege las rutas de negocio con el guard de autenticación`, `::expone /login sin guard`; `AutenticacionGuard` conservado redirige a `/login` con retorno (regresión intacta desde 006). |
| AC-5 | `app.routes.spec.ts::conserva la redirección de la raíz a dashboard (AC-5)`, `::no expone ninguna ruta de registro`; `test_permisos_endpoints.py::test_rutas_publicas_no_exigen_sesion` (`/health`, `/docs`, `/openapi.json`). |
| AC-6 | Evidencia vigente tras la enmienda (Actualización 22/Oct/2026: reescritura ejecutada): `test_tickets_alcance.py::test_solicitante_lista_solo_sus_tickets`, `::test_solicitante_crea_y_se_atribuye_su_identidad`, `::test_roles_autorizados_atienden_la_identidad_de_sesion` (payload con `usuario_id` omitido, propio, ajeno e inexistente → 201 y autoría de sesión), `::test_administrador_ignora_solicitante_de_otra_institucion_y_atribuye_a_sesion`, `::test_administrador_crea_para_solicitante_propio_201`; más PATCH/despacho ajenos (`::test_administrador_patch_ticket_ajeno_404_sin_mutar`, `::test_bodeguero_despacho_ticket_ajeno_404_sin_mutar`) y permisos. |
| AC-7 | `test_permisos_endpoints.py::test_rol_sin_permiso_recibe_403` (Bodeguero en usuarios/productos → 403); `test_ambito_institucional.py::test_bodeguero_ajeno_existencias_solo_su_institucion`, `::test_movimientos_bodeguero_solo_su_institucion`, `::test_registrar_movimiento_en_inventario_ajeno_responde_403_sin_mutar`; `test_tickets_alcance.py::test_bodeguero_lista_solo_su_institucion`, `::test_bodeguero_despacho_propio_200_sigue_transaccional`. |
| AC-8 | `test_ambito_institucional.py::test_administrador_existencias_acota_a_su_institucion`, `::test_superadmin_existencias_es_global`, `::test_existencias_departamento_ajeno_responde_403`, `::test_rol_limitado_sin_institucion_resoluble_responde_403`, `::test_instituciones_administrador_solo_la_propia`, `::test_usuarios_administrador_solo_su_institucion`; `test_tickets_alcance.py::test_administrador_lista_solo_su_institucion`; `ambito_service.py` deriva `usuario → departamento → institución` y 403 si no resuelve. |
| AC-9 | `test_permisos.py::test_matriz_cubre_exactamente_las_operaciones_de_d3`, `::test_sin_sesion_responde_401`, `::test_denegacion_autenticada_es_403_y_no_401`, `::test_dependencia_concede_o_deniega_segun_matriz` (parametrizado por operación/rol); `test_permisos_endpoints.py::test_inventario_de_rutas_igual_a_la_matriz_d3`, `::test_denegacion_no_muta_datos`; `test_tickets_alcance.py::test_catalogo_solicitante_solo_su_identidad`, `::test_catalogo_productos_y_stock_siguen_globales`. La semántica de `solicitantes` del catálogo es consulta, no selección para alta (enmienda). |
| AC-10 | `test_rol_asignable_usuarios.py::test_administrador_crea_usuario_con_rol_permitido`, `::test_administrador_no_puede_asignar_rol_prohibido` (403 sin creación), `::test_superadmin_puede_asignar_cualquiera_de_los_cuatro_roles`; regla en `usuario_service.py`, no en el router. |
| AC-11 | `database/01_esquema.sql` y `database/02_datos_semilla.sql` sin columna/valores `password` (10 usuarios de semilla intactos); comentario de autenticación "decorativa" de la semilla y docstring de `TicketDespacho` corregidos; verificado contra PostgreSQL 16 real (T7). |
| AC-12 | `test_retiro_password.py` (3 tests): `Usuario` sin columna, `UsuarioCrear` sin campo, `UsuarioRespuesta` sin publicar `password`; grep de runtime sin dependencia de `usuario.password`. |
| AC-13 | `database/99_migracion_retiro_password.sql` (`ALTER TABLE usuario DROP COLUMN IF EXISTS password`). Verificado en vivo (T13) sobre `compustock_db`/`apt_erp`: la tabla `usuario` queda con `usuario_id, nombre, apellido, correo, departamento_id, rol_id` (sin `password`); **12 usuarios y 10 tickets intactos**; segunda ejecución con `ON_ERROR_STOP=1` → `NOTICE: column "password" ... does not exist, skipping`, exit 0 (idempotente); instalación limpia verificada en T8. |
| AC-14 | `/auth/me` en vivo (Bearer real) → 200 con `IdentidadAutenticadaRespuesta`; autorización y operaciones de usuario corren sin consultar `password`; recorrido funcional 4200 (T12) con sesiones Clerk reales por rol. |
| AC-15 | Backend `pytest` **1405 passed / 77 skipped / 0 failed** (gated PG16 **1482 / 0 skipped / 0 failed**); frontend `ng test` **470 SUCCESS / 0 FAILED** (guards, espera de identidad/rol, acceso denegado y capacidades); OpenAPI en vivo publica `HTTPBearer` y 401/403 por operación (`test_permisos_endpoints.py::test_openapi_*`). Cobertura vigente de autoatribución del alta: `test_tickets_alcance.py::test_roles_autorizados_atienden_la_identidad_de_sesion`, `::test_solicitante_crea_y_se_atribuye_su_identidad`, `::test_administrador_ignora_solicitante_de_otra_institucion_y_atribuye_a_sesion`, `::test_administrador_crea_para_solicitante_propio_201`, y los de propiedad/403 (PATCH/despacho ajenos); UI en `tickets.component.spec.ts`. Actualización 22/Oct/2026: reescritura ejecutada; ver AC-18–AC-20. |
| AC-16 | Migración PostgreSQL verificada en vivo con conservación de conteos/IDs y repetición segura (AC-13); `pytest` 377 y `ng test` 140 verdes. |
| AC-17 | Este cierre: evidencia por AC, contrato `/openapi.json` (HTTPBearer + 401/403) comprobado en vivo, recorridos 4200 (funcional, escrituras reales) y 8080 (humo sobre imagen reconstruida `sha256:3862981…`, ruta directa `/acceso-denegado` → 200), y grep §8.7 sobre `AGENTS.md`/`MEMORY.md`/`.agents/skills/` con correcciones aplicadas. |

### Enmienda posterior al cierre: autoría de alta de tickets — 22/Oct/2026

#### Problema

El selector de solicitante permitía emitir tickets a nombre de otra persona, incongruente
con la identidad que inicia sesión. Para Solicitante ya era ineficaz porque el backend
sobreescribía el valor con su propia identidad; para Administrador y Bodeguero habilitaba
una autoría ajena.

#### Qué cambia

El backend autoatribuye incondicionalmente a la identidad autenticada en todos los roles
que ya están autorizados a crear tickets. `usuario_id` pasa a opcional: se acepta payload
sin ese campo y se ignora cualquier valor enviado, sin 422/403 ni 404 por referencia de
usuario. La UI sustituye el selector por un campo informativo no editable con nombre,
apellido y correo de la identidad de sesión; en esa fecha `/auth/me` no incluía
departamento, por lo que no se muestra ni se consulta de forma adicional. (Desde la
enmienda AC-22 de la Feature 008, 20/Nov/2026, el contrato sí lo publica; el modal
conserva el mismo bloque informativo.)

#### Qué no cambia

No cambia la matriz de permisos ni se concede `POST /tickets/` a Superadmin, que conserva
403 según Feature 008/017. El catálogo `solicitantes` sigue en `GET /tickets/catalogos`
para listados/detalle; solo deja de poblar selector de creación. No cambia el resto de
`crear_ticket`: productos, prioridad, estado, transacción, detalles, historial y validación
de sede. La institución y sede se derivan de la identidad de sesión; sin sede en su
departamento el alta responde 409, con sede procede si las demás reglas se cumplen.

#### Por qué una enmienda

Es un ajuste posterior de contrato de autoría y presentación de un flujo ya cerrado; no
amplía ni redistribuye permisos y no requiere DDL ni dependencias. Se conserva la evidencia
de cierre original, marcando para reescritura únicamente las afirmaciones que el nuevo
contrato invalida.

#### Criterios de aceptación de la enmienda (AC-18–AC-20)

- **AC-18 — Atribución incondicional.** DADO Administrador o Bodeguero con permiso vigente, CUANDO crea un ticket sin `usuario_id` o incluye un valor propio, ajeno o inexistente, ENTONCES una solicitud válida responde **201** y `ticket.usuario_id` es el de la identidad de sesión; el valor enviado se ignora sin 422/403 ni 404 por ese campo. Institución y sede se derivan del usuario de sesión. Superadmin conserva 403 y la matriz no cambia.
  - *Evidencia (observada 22/Oct/2026):* `test_tickets_alcance.py::test_roles_autorizados_atienden_la_identidad_de_sesion` (Administrador/Bodeguero/Solicitante con `usuario_id` omitido, propio, ajeno e inexistente → 201 y autoría de sesión), `::test_administrador_ignora_solicitante_de_otra_institucion_y_atribuye_a_sesion`, `::test_administrador_crea_para_solicitante_propio_201`, `::test_solicitante_crea_y_se_atribuye_su_identidad`; `test_tickets_institucional.py::test_solicitante_ignora_usuario_ajeno_y_conserva_autoatribucion` y `::test_crear_ticket_con_producto_ajeno_404_sin_parcial` (404 de producto conservado); `test_modal_ticket.py::test_ticket_con_usuario_inexistente_se_ignora_y_atiende_a_la_sesion`. Suites: SQLite **1405 passed / 77 skipped / 0 failed**, gated PostgreSQL 16 **1482 passed / 0 skipped / 0 failed**. Contrato: `TicketCrear.required` sin `usuario_id`, campo documentado como ignorado y `POST /tickets/` sin 404 por usuario; matriz **62** operaciones y Superadmin 403. Recorrido 4200: tickets 11 (usuario 13) y 12 (usuario 11) con body sin `usuario_id` → 201. Evidencia: [`evidencia/README.md`](evidencia/README.md).
- **AC-19 — Presentación del autor y catálogo.** DADO el modal de creación con identidad disponible, CUANDO presenta el autor, ENTONCES muestra en solo lectura nombre, apellido y correo de sesión; no hay selector ni control editable `usuario_id`, y el POST no requiere/envía ese campo. `GET /tickets/catalogos` conserva `solicitantes` para listados/detalle, pero no se usa como selector de autoría.
  - *Evidencia (observada 22/Oct/2026):* `tickets.component.spec.ts` cubre identidad visible en solo lectura, ausencia del selector y del control `usuario_id`, y body sin ese campo; `ng test` **470 SUCCESS / 0 FAILED** (Edge 155) y `ng build` limpio (`main-QNRFXFUT.js`). El catálogo `GET /tickets/catalogos` conserva `solicitantes` (`test_modal_ticket.py::test_catalogos_responde_200_con_las_cuatro_listas`, `::test_solicitantes_traen_departamento_y_orden_por_apellido`) y alimenta listados/detalle, no el alta. Recorrido 4200: campo «Solicitante (sesión)» con nombre y correo de la identidad, sin selector; POST sin `usuario_id`. Humo 8080 tras rebuild con el mismo campo. Evidencia: [`evidencia/README.md`](evidencia/README.md).
- **AC-20 — Herencia del ámbito y sede.** DADO Administrador o Bodeguero cuya identidad está vinculada a un departamento con sede, CUANDO crea un ticket válido, ENTONCES el ticket y su instantánea de sede corresponden al departamento autenticado. Si no hay sede asignada, responde 409 sin ticket ni detalle parcial. No se usa `usuario.sede_id` como sustituto de `departamento.sede_id`.
  - *Evidencia (observada 22/Oct/2026):* `test_tickets_alcance.py::test_departamento_sin_sede_responde_409_sin_ticket_detalle_ni_historial` y `test_ticket_sede_011.py::test_crear_ticket_sin_sede_de_departamento_afecta_a_todos_los_roles_creadores` (409 sin ticket ni detalle), frente a `test_ticket_sede_011.py::test_crear_ticket_almacena_la_sede_del_departamento` (201 con la sede del departamento). En 4200 y en BD: Administrador (usuario 13, Dirección) → ticket 11 con `sede_id 1`; Solicitante (usuario 11, Biblioteca) → ticket 12 con `sede_id 2`; sin usar `usuario.sede_id`. Evidencia: [`evidencia/README.md`](evidencia/README.md).

> **Nota de superación de AC-18 y AC-20 (26/Nov/2026).** Ambos criterios y su evidencia se
> conservan como **registro histórico** de lo observado el 22/Oct/2026. Desde la enmienda del
> 26/Nov/2026, Administrador y Bodeguero reciben **403** en `POST /tickets/`: los 201 de esos
> roles quedan como registro y los tests vivos dejan de reproducirlos. En su alcance de roles,
> la misma superación alcanza la frase de AC-6 que describe el alta de Administrador y
> Bodeguero. La regla de autoatribución del alta (D-8) sigue vigente para el único rol
> autorizado, el Solicitante.

#### Evidencia anterior afectada

En AC-6, AC-15 y su tabla de evidencia queda obsoleto el test histórico del `usuario_id`
obligatorio (hoy eliminado); también cambia la expectativa de
`test_administrador_crea_para_solicitante_propio_201`. La evidencia de AC-9 que describe
`solicitantes` seleccionables se debe limitar al alcance del catálogo y no a la autoría del
POST. Los tests de permisos denegados, propiedad del listado y matriz permanecen válidos.
Toda evidencia nueva quedó reescrita tras la enmienda en la fase de implementación.

**Actualización 22/Oct/2026:** reescritura ejecutada; la evidencia observada de AC-18…AC-20
está en los propios AC y en [`evidencia/README.md`](evidencia/README.md).

### Enmienda posterior al cierre: alta de tickets reservada al Solicitante — 26/Nov/2026

> **Qué enmienda.** No reescribe el cierre ni la evidencia de AC-1…AC-20. Restringe **una
> fila existente** de la matriz de D-3: `POST /api/v1/tickets/` pasa de
> `{Administrador, Bodeguero, Solicitante}` a `{Solicitante}`. No agrega ni retira
> operaciones, no toca DDL, semilla, versión de esquema, autenticación, capacidades, modelo
> de datos ni servicios. Convierte en regla de servidor lo que el 25/Nov/2026 solo se hizo en
> la interfaz.

#### Problema

El 25/Nov/2026 se ocultó «+ Crear pedido» a Administrador y Bodeguero **solo en la UI**
(`ROLES_CREACION_TICKETS = ['Solicitante']`), mientras la API siguió admitiendo a los tres
roles. Esa demo dejó dos verdades: la vista dice una cosa y la matriz otra. Cualquier cliente
fuera de Angular puede crear un ticket con un rol que la vista ya no ofrece; la enmienda de
22/Oct/2026 (AC-18) verificó y documentó ese 201 para Administrador y Bodeguero, así que no
es una sospecha.

El hueco no es cosmético. Un ticket creado por Administrador o Bodeguero queda atribuido a
esa identidad y hereda la sede e institución del departamento de esa identidad, que no es el
de un funcionario solicitante que demanda para el suyo. Eso produce demanda falsa en el
tablero y en Compras (020/021), y un pedido sin dueño Solicitante que pueda confirmar la
entrega (013 AC-43). Además, ocultar un botón no autoriza: la frontera es la API.

#### Qué cambia

- La fila `POST /api/v1/tickets/` de `MATRIZ_PERMISOS` queda en **solo `Solicitante`**. La
  matriz conserva **75** operaciones: cambian los roles de una entrada existente, no su
  número.
- Administrador y Bodeguero pasan de 201 a **403** por matriz; Superadmin sigue en 403.
- El 403 se resuelve antes de validar el cuerpo, con JSON parseable, y no deja filas nuevas.
- La descripción de la operación en `/openapi.json` declara que solo el Solicitante crea.
- La UI deja de describirse como demo: el botón ya estaba oculto y solo se actualizan los
  comentarios y los títulos de pruebas. **No** se añade una guarda de apertura del modal.
- Se actualizan el docstring de `crear_ticket` (que aún enumera los tres roles), las notas de
  la 003 y la transcripción de la 012, y al implementar `MEMORY.md` y el roadmap.

#### Qué no cambia

- El servicio de alta: autoatribución de sesión, `usuario_id` opcional e ignorado, institución
  y sede derivadas de la identidad, `Pendiente` por nombre canónico, validaciones,
  transacción e historial de creación.
- `GET /tickets/catalogos` y su lista `solicitantes`; el listado, el detalle, el historial, el
  tablero y sus filtros.
- Aprobación, despacho, rechazo, anulación, edición, `PATCH /estado` y confirmación de
  entrega, con sus roles actuales.
- La capacidad `tickets`, que sigue gateando el alta como condición adicional.
- El contrato declarado: `POST /api/v1/tickets/` publica `201, 401, 403, 404 y 422`; el 409
  sigue apareciendo **solo en la descripción** y esta enmienda no añade ni retira respuestas.
- DDL, datos semilla, versión `026.0`, tablas, entidades, autenticación Clerk y el conjunto
  cerrado de capacidades.
- Los tickets existentes y su autoría: no se reasignan, no se anulan y no se borran.

#### Por qué una enmienda

La matriz por operación es el artefacto de la 007 (D-3) y esta decisión no crea operaciones,
flujo, DDL ni capacidades: ajusta los roles de una fila y su contrato. Tramitarlo como feature
independiente (se descartó la carpeta 028) duplicaría la fuente de verdad y sugeriría un
alcance nuevo que no existe. La enmienda conserva el cierre original, anota la superación de
AC-6/AC-18/AC-20 y deja una única regla vigente.

#### Decisiones de la enmienda

##### D-11 — Solo el Solicitante emite pedidos de insumo

El único rol autorizado a `POST /api/v1/tickets/` es `Solicitante`. La denegación es por rol:
no depende del payload, la institución, el departamento ni el ticket.

**Por qué:** la constitución asigna al Solicitante la emisión de requerimientos para su
departamento; el Bodeguero abastece y el Administrador administra. Un ticket de esos roles no
representa la demanda de un Solicitante, ensucia la cobertura de Compras y nace sin dueño que
pueda confirmar la entrega (013 AC-43). La regla también elimina la duplicidad «la vista dice
una cosa, la API otra», que es exactamente lo que una matriz central existe para evitar.

##### D-12 — La matriz es la frontera; el servicio de alta no repite el rol

La restricción vive en la fila de la matriz y en la dependencia de autorización del endpoint.
El servicio que persiste el ticket sigue siendo agnóstico del rol: autoatribuye la identidad
recibida y no vuelve a preguntar si es Solicitante.

**Por qué:** la 007 fija que la política es central y explícita por operación (D-3) y que los
servicios reciben la identidad ya resuelta, no flags de confianza. Duplicar la regla en el
servicio crearía dos fuentes que pueden divergir y rompería dos casos legítimos: las pruebas
que ejercen el servicio directamente y la creación interna de tickets sin sesión (el ticket
automático de la 016), que no tiene un rol de sesión que consultar.

**Alternativa descartada:** añadir un `if rol != Solicitante` dentro de `crear_ticket`. Se
descarta por duplicación, por acoplar la persistencia a un rol y por bloquear la creación
interna futura.

##### D-13 — El 403 de matriz es anterior al payload con JSON parseable

Con un cuerpo **JSON parseable**, el 403 de matriz se resuelve antes de la validación del
contrato: Administrador y Bodeguero reciben 403 aunque el payload tenga asunto corto,
`detalles` vacío, cantidad no positiva, campo extra o `estado_id` ausente. No se abre
transacción y no hay filas nuevas. Un cuerpo que **no** es JSON parseable puede producir 422
antes de que se resuelvan las dependencias; queda fuera de esta garantía y no se reordena
nada para cambiarlo.

**Por qué:** fail closed sin filtrar la forma del contrato ni dejar escritura parcial. La
ausencia de escritura no se promete por un `rollback`, sino porque la petición no llega al
servicio.

##### D-14 — La capacidad `tickets` sigue siendo un gating adicional

Con `tickets` habilitada, el Solicitante crea y Administrador/Bodeguero siguen en 403 por
matriz. Con `tickets` apagada, el Solicitante también recibe 403. La capacidad describe la
disponibilidad funcional de la institución (012 D-6); el rol describe quién puede ejecutar la
operación.

**Por qué:** son ejes ortogonales. Convertir la capacidad en la regla de rol obligaría a que
una institución «apagara» el alta para impedir que su Administrador cree tickets, que es un
error de modelado y una regresión del gating existente.

##### D-15 — La UI es espejo; el cambio se limita a lo ya oculto y a sus comentarios

«+ Crear pedido» se muestra solo al Solicitante; el botón ya está oculto desde el
25/Nov/2026. Administrador y Bodeguero conservan el acceso a `/tickets`, el tablero y el
detalle, y no tienen ningún otro control visible que abra el modal. El Solicitante conserva
el botón, el modal y el envío sin `usuario_id`. **No** se añade una guarda de apertura dentro
del componente.

**Por qué:** retirar `/tickets` a Administrador y Bodeguero les quitaría la aprobación, el
despacho, el rechazo y la consulta, que sí les corresponden. Una guarda de apertura
duplicaría en la vista una defensa que no es la frontera y añadiría superficie sin valor de
seguridad; la regla se prueba en la API.

##### D-16 — Los tickets históricos no se tocan

Los tickets creados antes por Administrador o Bodeguero conservan su autor, institución, sede,
detalles e historial y se operan según su estado con las reglas vigentes. Ninguno de esos
pedidos admite confirmación de entrega si su dueño no es Solicitante, como ya documenta la 013
AC-43.

**Por qué:** la autoría es un hecho histórico y la trazabilidad es un principio inmutable del
sistema (`constitucion.md` §4, principio 2). Reasignar autores para «arreglar» el pasado
falsificaría la auditoría. Esta enmienda cambia quién puede crear, no quién creó.

##### D-17 — Superación histórica de 003 AC-33 y 007 AC-6/AC-18/AC-20, sin reescribir la evidencia

La regla de autoatribución sigue vigente y ahora se aplica al único rol autorizado: el
Solicitante. Lo que queda **superado** es el alcance de roles: la 003 AC-33 y su evidencia de
201 para Administrador/Bodeguero; la 007 AC-18 y AC-20; y la frase de AC-6 que describe el
alta de Administrador y Bodeguero. La transcripción histórica de D-3 y toda la evidencia
observada el 22/Oct/2026 se conservan como registro, con su nota de superación; no se
reescriben ni se borran.

**Por qué:** el SDD mantiene la trazabilidad de las decisiones. Cambiar el pasado ocultaría
que el sistema admitió esos 201 y por qué se retiraron. La nota de superación permite leer la
historia sin confundirla con la regla vigente.

##### D-18 — Alta del Bodeguero por sede y ticket automático 016: fuera de alcance

El Bodeguero no gana aquí ninguna capacidad de alta, ni siquiera acotada a su sede. Cuando se
implemente, será una operación y un flujo propios (reposición por sede), con su spec, y no una
reapertura silenciosa de `POST /tickets/` para ese rol. El ticket automático por stock mínimo
pertenece a la 016 y se apoya en el servicio de alta, que D-12 mantiene independiente del rol.

**Por qué:** mezclar ambas cosas reintroduciría la ambigüedad que esta enmienda cierra y
obligaría a decidir hoy reglas de reposición (sede destino, cantidades, aprobación) que no
están definidas. La fila única del alta queda limpia: Solicitante, y nada más.

#### Reglas del flujo de la enmienda

| Rol | `POST /api/v1/tickets/` | Efecto |
|---|---|---|
| **Solicitante** | **201** con payload válido y capacidad `tickets` habilitada; 422/404/409 según las reglas vigentes del alta | Ticket y detalles en una sola transacción, con autoría, institución y sede de la identidad de sesión, estado `Pendiente` y su fila de historial de creación |
| **Administrador** | **403** por matriz | Ninguna fila nueva en ticket, detalle ni historial |
| **Bodeguero** | **403** por matriz | Ninguna fila nueva en ticket, detalle ni historial |
| **Superadmin** | **403** por matriz (sin cambio desde 008/017) | Ninguna fila nueva en ticket, detalle ni historial |

**Precedencia de las respuestas que esta enmienda fija.** 1) **401** sin `Authorization` o con
Bearer inválido o expirado. 2) **403** por capacidad `tickets` apagada o por rol fuera de la
matriz; con JSON parseable, el cuerpo no se valida. 3) **422** de forma del payload, solo para
el Solicitante con la capacidad habilitada. 4) **404** de referencia inexistente o producto
ajeno. 5) **409** de precondición del alta. 6) **201** persistido. Un JSON **malformado** puede
responder 422 antes del paso 2; no se promete 403 en ese caso. La institución inactiva se
documenta aparte porque no sigue este orden.

**Institución inactiva.** `get_current_user` resuelve la identidad; la inactividad se detecta
después, en `get_db_negocio` → `resolver_contexto_solicitud`. En `POST /tickets/`,
`requiere_operacion` se resuelve antes que `get_db_negocio`: un Administrador o Bodeguero de
institución inactiva recibe **403 por matriz**; un Solicitante, que sí pasa la matriz, alcanza
el **401** del contexto de tenant. No se reordena ninguna dependencia ni se cambia la
autenticación.

#### Criterios de aceptación de la enmienda (AC-21–AC-34)

- **AC-21 — Alta del Solicitante.** DADO un Solicitante autenticado, con la capacidad
  `tickets` habilitada, un departamento con sede y un payload válido (prioridad existente,
  `estado_id` de `Pendiente`, asunto, descripción y al menos un detalle de un producto de su
  institución), CUANDO invoca `POST /api/v1/tickets/`, ENTONCES responde **201** con el read
  model; el ticket queda con `usuario_id` de la sesión, la institución y la sede del
  departamento, estado `Pendiente` y una fila de historial de creación con origen nulo y el
  actor de sesión. Si el payload trae `usuario_id` (propio, ajeno o inexistente), se ignora
  sin 422/403/404 por ese campo. SI el payload es inválido para el contrato, ENTONCES 422; SI
  una referencia no existe o el producto es de otra institución, 404; SI el estado no es
  `Pendiente`, el producto no está disponible o falta la sede, 409; en los tres casos sin
  escritura.
- **AC-22 — Administrador denegado sin efectos.** DADO un Administrador autenticado con la
  capacidad `tickets` habilitada, CUANDO invoca `POST /api/v1/tickets/` con un payload JSON
  parseable y válido para el contrato, ENTONCES responde **403** con el mensaje estándar de
  permiso insuficiente, sin datos del payload, y las cuentas de ticket, detalle e historial de
  creación son idénticas antes y después. Aplica también al Administrador autor de tickets
  históricos.
- **AC-23 — Bodeguero denegado sin efectos.** DADO un Bodeguero autenticado con la capacidad
  `tickets` habilitada, CUANDO invoca `POST /api/v1/tickets/` con un payload JSON parseable y
  válido para el contrato, ENTONCES **403** con el mensaje estándar y cero filas nuevas en
  ticket, detalle e historial.
- **AC-24 — El 403 precede al payload con JSON parseable.** DADO un Administrador o un
  Bodeguero autenticado, CUANDO envía un cuerpo **JSON parseable** pero inválido para el
  contrato (asunto de menos de 3 caracteres, `detalles` vacío, cantidad no positiva, campo
  extra o `estado_id` ausente), ENTONCES responde **403**, no 422/404/409, y no escribe nada.
  La misma petición con un Solicitante y la capacidad habilitada responde el 422/404/409 que
  corresponda. Un cuerpo que **no** es JSON parseable puede responder 422 antes de las
  dependencias; esta garantía no lo cubre y no se reordena nada para conseguirlo.
- **AC-25 — Superadmin sin cambio.** DADO un Superadmin autenticado, CUANDO invoca
  `POST /api/v1/tickets/` con un cuerpo JSON parseable, válido o inválido para el contrato,
  ENTONCES **403** por matriz y cero filas nuevas. La enmienda no le concede nada ni le quita
  nada respecto de 008/017.
- **AC-26 — Sesión ausente o inválida.** DADO una petición sin `Authorization` o con un Bearer
  inválido o expirado, CUANDO invoca `POST /api/v1/tickets/`, ENTONCES **401** y sin
  escritura. La enmienda no promete 401 para otros escenarios: la institución inactiva se rige
  por AC-27. No se cambia la autenticación ni el orden de las dependencias.
- **AC-27 — Institución inactiva tal como es.** DADO una identidad cuya institución está
  inactiva, CUANDO invoca `POST /api/v1/tickets/`, ENTONCES: el Administrador y el Bodeguero
  reciben **403 por matriz**, porque `requiere_operacion` se resuelve antes de `get_db_negocio`;
  el Solicitante, que sí pasa la matriz, alcanza el **401** del contexto de tenant al no
  resolverse su institución activa. En ambos casos no hay escritura. Este es el comportamiento
  vigente; la enmienda no lo altera ni reordena dependencias.
- **AC-28 — Capacidad `tickets` deshabilitada.** DADO un Solicitante autenticado y la
  capacidad `tickets` deshabilitada, CUANDO invoca `POST /api/v1/tickets/` con un payload
  válido, ENTONCES **403** por capacidad y sin escritura; al rehabilitarla, el mismo caso con
  el resto de las condiciones de AC-21 responde **201**. DADO un Administrador o Bodeguero con
  la capacidad deshabilitada, ENTONCES **403** igualmente. La capacidad no concede la
  operación a ningún rol: con `tickets` habilitada, Administrador y Bodeguero siguen en 403.
- **AC-29 — Matriz y contrato publicados.** DADO la matriz central y `/openapi.json`, CUANDO
  se consultan, ENTONCES `POST /api/v1/tickets/` declara exactamente `{Solicitante}`; la
  matriz sigue con **75** operaciones (cambian los roles de una entrada, no el número); OpenAPI
  publica **77 operaciones** (75 v1 + `GET /` + `/health`). `POST /api/v1/tickets/` declara
  `201, 401, 403, 404 y 422`; el 409 sigue **solo en la descripción** y no se añade ni se
  retira ninguna respuesta en esta enmienda. La descripción afirma que solo el Solicitante
  crea y no insinúa tres roles. Sin operaciones, capacidades, versiones, tablas ni columnas
  nuevas; `response_model` y códigos de éxito no cambian.
- **AC-30 — El resto de operaciones de tickets no cambia.** DADO Administrador y Bodeguero,
  CUANDO ejercen sus operaciones de tickets, ENTONCES conservan la lectura de tickets,
  catálogos, detalle e historial de su institución; el Administrador conserva aprobación,
  despacho, rechazo, anulación y edición según su rol y `PATCH /estado`; el Bodeguero conserva
  despacho y rechazo y sigue recibiendo 403 en el `PATCH`; ambos siguen recibiendo 403 en el
  alta. El Solicitante conserva la lectura de lo propio, la edición/anulación de lo suyo y la
  confirmación de entrega. Ninguna otra fila de la matriz cambia de roles.
- **AC-31 — Tickets históricos intactos.** DADO un ticket existente creado por un
  Administrador o un Bodeguero, CUANDO se consulta o se opera según su estado, ENTONCES
  conserva autor, institución, sede, detalles e historial, y su ciclo de vida funciona como
  hoy (aprobación, despacho, rechazo o anulación por quien corresponda; sin confirmación de
  entrega si su dueño no es Solicitante, como fija 013 AC-43). La enmienda no reasigna autores
  ni modifica, anula o borra tickets existentes.
- **AC-32 — La interfaz como espejo.** DADO la vista `/tickets` renderizada para cada rol,
  CUANDO se inspeccionan sus controles visibles, ENTONCES «+ Crear pedido» aparece solo al
  Solicitante; Administrador y Bodeguero no ven el botón ni ningún otro control visible que
  abra el modal. Administrador y Bodeguero siguen entrando a `/tickets`, ven el tablero y
  abren el detalle con sus acciones. El Solicitante conserva el botón, el modal y el envío sin
  `usuario_id`. No se añade una guarda de apertura en el componente: la frontera es la API y
  el cambio de UI se limita a lo ya oculto y a sus comentarios.
- **AC-33 — Pruebas actualizadas sin pérdida de cobertura.** DADO la suite completa, CUANDO se
  ejecuta `pytest` y `ng test`, ENTONCES las **seis** transcripciones independientes de la
  matriz reflejan `POST /api/v1/tickets/ → {Solicitante}`: los cinco
  `backend/tests/no_funcional/seguridad/test_permisos*.py` (`test_permisos.py`,
  `test_permisos_008.py`, `test_permisos_010.py`, `test_permisos_012.py`,
  `test_permisos_endpoints.py`) y `test_ciclo_vida_autorizacion_013.py`, que también
  transcribe la fila con tres roles. `test_permisos_008.py` conserva su regla de que el
  Administrador mantiene las operaciones de `OPERACIONES_AJUSTADAS` **salvo esta excepción
  documentada**. `test_correlacion_024.py`, que hoy espera 400/401/422 con el cliente legacy,
  pasa a esperar **403**. Las altas vivas de las suites usan una identidad/cliente
  **Solicitante**; los fixtures históricos de tickets con autoría de Administrador o Bodeguero
  que prueban AC-43 se siembran por ORM (patrón de
  `test_ciclo_vida_confirmacion_013.py`), no se convierten en altas de Solicitante. Las suites
  que siembran por ORM o no hacen POST de tickets —cobertura 021, Compras— no se ven
  afectadas. No se borra cobertura: la autoatribución sigue probada con el Solicitante y se
  añaden los 403 de Administrador y Bodeguero con payload válido e inválido y la comprobación
  de cero filas. Ambas suites quedan en verde.
- **AC-34 — Coherencia documental.** DADO un grep de cierre sobre `docs/`, `backend/` y
  `frontend/`, CUANDO se buscan las afirmaciones de que el alta admite tres roles o de que la
  restricción es solo presentación, ENTONCES ninguna queda vigente: se actualizan los
  comentarios de `frontend/src/app/core/auth/roles.ts` y
  `frontend/src/app/features/tickets/tickets.component.ts`, el docstring de `crear_ticket` en
  `backend/app/services/ticket_service.py` (que aún enumera Administrador/Bodeguero/
  Solicitante), la nota de la 003 y la transcripción de
  `docs/spec/features/012-gestion-administrativa/diseno-tecnico.md` que lista los tres roles
  para `POST /tickets/` (o se declara que los diseños históricos no son normativos y quedan
  fuera del grep). `docs/spec/roadmap.md` registra la enmienda en la fila de la 007 y no anuncia
  una feature 028; `MEMORY.md` sustituye la nota de demo del 25/Nov/2026 y la mención «028–029»
  de los próximos pasos. La enmienda no se cierra como 028: pertenece a la 007.

#### Impacto en pruebas de la enmienda

- **Altas por HTTP con el cliente legacy (Administrador) o con cliente parametrizado por
  rol:** `test_smoke.py`, `test_transaccion_ticket.py`, `test_modal_ticket.py`,
  `test_tablero_kanban.py`, `test_despacho_transaccional.py`,
  `test_ciclo_vida_alta_inicial_013.py`, `test_ciclo_vida_historial_013.py`,
  `test_flujo_aprobacion_entrega_013.py`, `test_ticket_proceso_013.py`,
  `test_ticket_sede_011.py`, `test_historial_movimientos.py`,
  `test_validacion_entradas_027.py`, `test_tickets_alcance.py`,
  `test_tickets_institucional.py` y `test_correlacion_024.py`. Requieren revisión y, donde
  corresponda, una identidad/cliente Solicitante; `test_correlacion_024.py` pasa además a
  esperar 403.
- **Fixtures históricos:** los tickets con autoría de Administrador o Bodeguero que sostienen
  AC-43 se siembran por ORM (patrón de `test_ciclo_vida_confirmacion_013.py`), no se recrean
  con el alta del Solicitante.
- **Sin impacto:** `test_cobertura_021.py` y las suites de Compras siembran por ORM o no hacen
  POST de tickets; no crean tickets con la identidad legacy.
- **Mejora opcional, no AC:** centralizar `RESTRINGIDAS_013`, hoy repetido en varias
  transcripciones, evitaría una copia más al añadir restricciones futuras. No es requisito de
  esta enmienda.

#### Evidencia de la enmienda

Evidencia observada al cierre del **26/Nov/2026**; no se inventa ninguna observación. Los
recorridos de 4200 y 8080 usaron sesiones Clerk reales de la instancia dev (sin secretos).

| AC | Estado | Evidencia |
|---|---|---|
| AC-21 | Verificado | `backend/tests/funcional/integracion/test_alta_solo_solicitante_007.py` (**41 casos / 17 funciones**): 201 con read model y autoría de sesión (`usuario_id` omitido, propio, ajeno o inexistente), estado `Pendiente`, institución, sede del departamento e historial de creación; 422/404/409 sin escritura. **4200 (26/Nov/2026):** el Solicitante (Paula Rojas, `usuario_id=11`) creó el pedido **#11** desde el modal; en BD `usuario_id=11`, `estado_id=1`, `sede_id=2`, `institucion_id=INST-001`, 1 detalle y 1 fila de historial. **8080:** `POST /api/v1/tickets/` con sesión de Solicitante → **201**, ticket **#10** con la misma autoría, estado y sede. |
| AC-22 | Verificado | `test_alta_solo_solicitante_007.py::test_administrador_y_bodeguero_reciben_403_sin_escribir_ac_22_ac_23`. En vivo con sesión Clerk real: **8080** Administrador (Cristian González) → **403** `{"detail":"Permiso insuficiente para la operacion"}` y conteos SQL ticket/detalle/historial **9/9/8** idénticos antes y después; **4200** Administrador (cuenta QA `admin020.test`) → **403** con el mismo mensaje y tablero de 4 columnas accesible. |
| AC-23 | Verificado | Mismo test de `test_alta_solo_solicitante_007.py`. En vivo: **8080** y **4200** Bodeguero (Roberto Díaz) → **403** estándar; conteos **10/10/9** sin cambios; `/tickets` conserva el tablero y el detalle #2 con «Rechazar». |
| AC-24 | Verificado | `test_alta_solo_solicitante_007.py::test_el_403_precede_al_payload_invalido_parseable_ac_24` (Administrador/Bodeguero × 5 cuerpos JSON parseables inválidos) y `::test_solicitante_con_payload_invalido_recibe_422_sin_escribir_ac_21_ac_24`. En vivo, Admin y Bodeguero con cuerpo `{}` (parseable, inválido) recibieron **403**, no 422, y sin filas. |
| AC-25 | Verificado | `test_alta_solo_solicitante_007.py::test_superadmin_recibe_403_con_json_parseable_ac_25` (cuerpo válido + 5 inválidos): **403** por matriz y cero filas. |
| AC-26 | Verificado | `backend/tests/no_funcional/seguridad/test_institucion_inactiva_012.py` (**9 casos / 7 funciones**; 3 variantes nuevas): sin `Authorization`, Bearer ilegible y Bearer expirado → **401** con `WWW-Authenticate: Bearer` y conteos de alta sin cambios. |
| AC-27 | Verificado | `test_institucion_inactiva_012.py::test_alta_con_institucion_inactiva_conserva_403_de_matriz_y_401_del_tenant_ac_27`: con institución inactiva, Administrador y Bodeguero → **403** por matriz; Solicitante → **401** del contexto de tenant; sin escritura y sin reordenar dependencias. |
| AC-28 | Verificado | `test_alta_solo_solicitante_007.py::test_capacidad_tickets_apagada_deniega_y_al_rehabilitarla_crea_ac_28`: capacidad apagada → 403 para Solicitante, Administrador y Bodeguero sin filas; rehabilitada → **201** del Solicitante. |
| AC-29 | Verificado | `test_alta_solo_solicitante_007.py::test_la_matriz_reserva_el_alta_al_solicitante_ac_29` (`MATRIZ_PERMISOS[...] == {Solicitante}`, **75** operaciones) y `::test_openapi_del_alta_conserva_el_contrato_y_declara_el_rol_ac_29`. **`/openapi.json` en vivo (8000):** **75** operaciones `/api/v1` + `GET /` + `GET /health` = **77**; `POST /api/v1/tickets/` declara **201, 401, 403, 404 y 422**; el **409 solo aparece en la descripción**; la descripción afirma que «solo el Solicitante» crea y que Administrador, Bodeguero y Superadmin reciben 403. |
| AC-30 | Verificado | **137 casos** en las suites de ciclo de vida/despacho/confirmación (`test_tickets_alcance.py`, `test_tablero_kanban.py`, `test_despacho_transaccional.py`, `test_ciclo_vida_historial_013.py`, `test_ticket_proceso_013.py`, `test_ciclo_vida_confirmacion_013.py`, `test_flujo_aprobacion_entrega_013.py`) verdes. En 4200/8080, Administrador y Bodeguero conservan tablero, detalle y acciones; el Bodeguero mantiene «Rechazar» y `PATCH /estado` sigue reservado al Administrador. |
| AC-31 | Verificado | `test_alta_solo_solicitante_007.py::test_ticket_historico_de_autor_administrador_conserva_su_autoria_ac_31` y `::test_ticket_historico_de_autor_bodeguero_conserva_su_autoria_ac_31` (sembrados por ORM; autor, institución, sede, detalles e historial intactos); `test_ciclo_vida_confirmacion_013.py::test_un_pedido_creado_por_un_administrador_no_admite_confirmacion_ac_43` y `test_flujo_aprobacion_entrega_013.py::test_tickets_historicos_sin_rol_solicitante_quedan_despachados_sin_confirmacion`. |
| AC-32 | Verificado | `ng test` **639 SUCCESS** (Edge 158; nunca `npm test`) y `roles.spec.ts`/`tickets.component.spec.ts` conservan botón visible/oculto por rol. **4200 y 8080:** «+ Crear pedido» visible solo al Solicitante, oculto a Administrador y Bodeguero, que siguen entrando a `/tickets` con tablero y detalle; el modal muestra «Solicitante (sesión)» sin control `usuario_id` y el alta no envía ese campo. **Corrección post-validación (26/Nov/2026):** rebuild real **sin caché** de 8080 (`build --no-cache frontend` + `up -d --force-recreate frontend`), imagen **2026-11-26T17:43:22Z = 14:43 -03** posterior a los archivos del 26/Nov 03:57, contenedor `healthy` y bundle **`main-GULMVWMA.js`** (mismo hash: el delta de UI eran solo comentarios). Humo repetido con los tres roles: Administrador y Bodeguero sin «+ Crear pedido», con tablero y detalle operativos y `POST` real **403**; Solicitante con botón, modal «Solicitante (sesión)» sin `usuario_id` y alta **201** (#12). |
| AC-33 | Verificado | Seis transcripciones con `POST /api/v1/tickets/ → {Solicitante}`: `test_permisos.py`, `test_permisos_008.py`, `test_permisos_010.py`, `test_permisos_012.py`, `test_permisos_endpoints.py` y `test_ciclo_vida_autorizacion_013.py`; `test_ciclo_vida_autorizacion_014.py` y `test_filtros_inventario_018.py` reutilizan la restricción; `test_correlacion_024.py` espera **403**. Altas vivas con cliente Solicitante e históricos por ORM. `pytest` **2024 passed / 112 skipped**; `ng test` **639 SUCCESS**. **Corrección post-validación (26/Nov/2026):** focal `test_alta_solo_solicitante_007.py` **41 passed**, grupo `tests/no_funcional/seguridad` **463 passed** y `ng test` **639 SUCCESS** reejecutados sobre el árbol corregido. |
| AC-34 | Verificado | Grep de cierre `sigue admitiendo\|tres roles\|solo presentación\|demo 25/Nov\|028` sin afirmaciones vigentes sobre el alta (las menciones restantes son históricas o notas de superación). Comentarios actualizados en `roles.ts`, `tickets.component.ts`, `roles.spec.ts` y `tickets.component.spec.ts`; docstring de `crear_ticket`; notas de 003 y 012; `MEMORY.md` con la regla y sin feature 028; `roadmap.md` registra la enmienda y su cierre sin abrir feature nueva. `docs/informes/_generar_informe.py` y el `Informe_Flujos_Actores.docx` regenerado ya no atribuyen «Crear pedido» a Administrador/Bodeguero. **Corrección post-validación (26/Nov/2026):** el comentario de `permisos.py` sobre el alta se alineó con D-13/AC-24 (403 de matriz con JSON parseable; un JSON malformado puede responder 422 antes de las dependencias) y la evidencia de rebuild/humo de 8080 se corrigió con la imagen real y los tres roles. |

## 8. Riesgos y mitigaciones

- **Confundir nombres de rol o asumir tres roles:** mantener explícitos los cuatro
  valores; `Admin` es abreviatura documental, no un alias runtime.
- **Permitir acceso vía llamada directa:** aplicar denegación de rol en backend,
  independientemente del guard.
- **Solicitante accede a ticket ajeno:** comprobar propiedad en operaciones permitidas y
  responder 404 igual que para ticket inexistente; operaciones no permitidas responden
  403.
- **Filtrado institucional incompleto:** aplicar límites derivados del usuario a
  inventario, movimientos y tickets para los roles limitados. No presentar el
  `stock_total` global de catálogo como institucional; catálogo/stock se particionan en
  008.
- **Exposición de datos del catálogo o escalada de rol:** limitar el catálogo de lectura
  conforme al rol y restringir roles asignables por Administrador;
  verificar denegación 403.
- **Migración destructiva o no idempotente:** retirar solo la columna y probar
  preservación de datos y repetición segura antes de cerrar.
- **Matriz incompleta:** AC-9 exige matriz completa de operación/rol; no deducir permisos
  solo del nombre de una pantalla.

## 9. Restricciones y aclaraciones abiertas

- Clerk permanece como única autoridad de autenticación; la autorización usa el rol
  local ya resuelto en Feature 006.
- 007 implementa límites institucionales para Administrador, Bodeguero y Solicitante en
  datos operativos. El catálogo de productos/categorías y `stock_total` de
  `/tickets/catalogos` son globales; Feature 008 implementa el particionamiento integral
  del catálogo y stock.
- La institución se deriva del departamento obligatorio del usuario local. Si el
  vínculo no se resuelve para Administrador, Bodeguero o Solicitante en una operación
  institucional, se deniega con 403; no se eleva el alcance.
- La migración SQL versionada debe preservar los datos; su mecanismo y ubicación se
  resolverán en el plan técnico. No se permite descartar o reinicializar la base como
  sustituto de la migración.
- No se guardan secretos ni contraseñas reales en esta especificación.
