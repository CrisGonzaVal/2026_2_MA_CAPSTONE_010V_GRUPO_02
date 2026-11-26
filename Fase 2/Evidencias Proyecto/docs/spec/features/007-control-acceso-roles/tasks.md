# Feature 007 — Tasks

**Spec:** [`spec.md`](spec.md) · **Plan:** [`plan.md`](plan.md)

Tareas en orden de dependencia; cada bloque debe mantener TDD para comportamiento observable. No marcar una tarea sin satisfacer `Hecho cuando:` y registrar evidencia concreta. Máximo 15 tareas. `[!]` significa bloqueada e indica el impedimento.

Verificación habitual:
- Backend: `cd backend && .venv\\Scripts\\python.exe -m pytest`
- Frontend: `$env:CHROME_BIN = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe"; cd frontend && npx ng test --watch=false --browsers=ChromeHeadless`
- Migración: PostgreSQL 16 real; los tests SQLite en memoria no acreditan ejecución/idempotencia del DDL PostgreSQL.

---

## Bloque A — backend-authz

### T1 — Fijar política central y dependencia de autorización (AC-1, AC-9, AC-15)

- [x] Antes de implementación, escribir pruebas de dependencia para cada rol conocido, rol desconocido/ausente, autenticación ausente/inválida, rol no autorizado y autorizado; definir literal exacto de los cuatro roles y matriz operacional central conforme a D-3. Añadir la dependencia de rol basada en `get_current_user`; preservar 401 y hacer 403 para denegación autenticada. No introducir alias `Admin`.

**Hecho cuando:** pruebas prueban 401 sin sesión, 403 con sesión sin permiso, permiso concedido solo al rol/método de la matriz y rechazo de rol ausente/desconocido; la identidad Clerk se resuelve una sola vez por solicitud y pytest pasa.

### T2 — Proteger las 18 operaciones y verificar contrato HTTP/OpenAPI (AC-7…AC-10, AC-15)

- [x] Aplicar permiso explícito a todas las operaciones de la matriz D-3 (18 endpoints, incluida `/auth/me` ya autenticada y las rutas/catálogos de apoyo); añadir tests parametrizados por operación/rol para permisos y denegaciones. Declarar códigos/documentación 401/403 pertinentes y verificar `/openapi.json`; mantener health/docs públicos.

**Hecho cuando:** el inventario de rutas contrastado con la matriz no deja operaciones sin prueba/autorización; pruebas HTTP validan allow/deny por rol y `/openapi.json` refleja autenticación y errores aplicables sin alterar los contratos de respuesta existentes.

### T3 — Imponer ámbito institucional en servicios de usuarios e inventario (AC-7…AC-9, AC-15)

- [x] Escribir pruebas cruzadas de dos instituciones para Administrador, Bodeguero, Solicitante y Superadmin; aplicar derivación `usuario → departamento → institución` en `usuario_service` e `inventario_service`. Cubrir listados, existencias/stock, movimientos, institución propia, parámetro `departamento_id` ajeno con 403, relación ausente/no resoluble con 403, catálogo categoría/producto compartido y catálogo de solicitantes según rol.

**Hecho cuando:** ningún rol limitado puede leer/modificar datos institucionales ajenos ni obtiene alcance global ante vínculo faltante; Superadmin conserva alcance global; tests demuestran catálogo maestro global y filtros correctos de solicitantes.

### T4 — Imponer propiedad, atribución y ámbito institucional en tickets (AC-6…AC-9, AC-15)

- [x] Escribir pruebas de listado propio, ticket ajeno e inexistente ambos 404 para operaciones permitidas, 403 general para acciones prohibidas, creación atribuida al Solicitante aunque envíe otro `usuario_id`, y contrato `TicketCrear` con `usuario_id` obligatorio para los otros roles. Aplicar filtros al listar, validar institución de solicitantes para Administrador/Bodeguero y comprobar ámbito antes de PATCH/despacho, sin romper la transacción de despacho.

**Hecho cuando:** tests cubren lectura y mutación por id sin fuga entre instituciones, id ajeno/no existente ocultos para Solicitante, denegación sin cambios de filas y atribución correcta; tests de despacho transaccional existentes y nuevos siguen verdes.

### T5 — Restringir rol asignable en alta de usuario (AC-8, AC-10, AC-15)

- [x] Probar `POST /usuarios/` para Administrador con Bodeguero/Solicitante y con Superadmin/Administrador; verificar 403 y cero creación para los dos roles prohibidos. Probar Superadmin con los cuatro roles y límite institucional del Administrador; implementar la regla en servicio, no en el router.

**Hecho cuando:** tests HTTP/servicio verifican altas permitidas, denegaciones 403 sin mutación y no regresión del contrato de creación salvo retiro de contraseña en T7.

## Bloque B — base de datos y retiro de password

### T6 — Añadir cobertura y eliminar contraseña de modelo/contrato/fixtures (AC-12, AC-14, AC-15)

- [x] Localizar todos los usos funcionales de `usuario.password`; actualizar primero fixtures y pruebas a usuarios sin credencial local, después retirar atributo de `Usuario` y campo requerido de `UsuarioCrear`. Mantener Clerk como única autoridad, y comprobar `/auth/me`/alta de usuario sin consultar contraseña.

**Hecho cuando:** suite backend no crea ni transmite contraseña local; schema/modelo no publican ese campo y grep de runtime/tests no deja dependencia de `usuario.password` (excepto asserts/documentación intencionales de su ausencia).

### T7 — Limpiar esquema inicial, semilla y comentarios obsoletos (AC-11, AC-12)

- [x] Retirar `password` de `database/01_esquema.sql` y de columnas/valores de usuarios en `database/02_datos_semilla.sql`; corregir comentarios obsoletos de autenticación de semilla y el docstring de `TicketDespacho`. Verificar cantidad/orden de columnas y conservación de los diez usuarios/relaciones de semilla.

**Hecho cuando:** grep de esquema/semilla/modelo/schema/tests no encuentra definición ni valor de contraseña; SQL inicial sigue siendo coherente (mismo número de valores por usuario) y los comentarios descritos por AC-11 están corregidos.

### T8 — Crear y verificar migración idempotente para volúmenes existentes (AC-13, AC-16)

- [x] Añadir script SQL versionado y posterior al orden de init, que retire solo `usuario.password` de forma idempotente. Documentar en el propio script el comando reproducible con `psql`/`docker exec` y `ON_ERROR_STOP=1` para base ya inicializada. Preparar PostgreSQL 16 con usuarios, tickets/relaciones y columna; ejecutar migración, comprobar columna ausente y todos los datos/relaciones preservados, repetir y comprobar éxito. Probar también una instalación limpia.

**Hecho cuando:** evidencia contra PostgreSQL 16 confirma conservación de conteos/IDs/relaciones, eliminación de columna, segunda ejecución sin error y aplicabilidad sin depender de `/docker-entrypoint-initdb.d` en volumen preexistente.

## Bloque C — frontend-guards

### T9 — Implementar RolGuard reactivo y denegación dedicada (AC-1, AC-2, AC-4, AC-15)

- [x] Escribir tests primero para identidad cargando, rol válido permitido, rol distinto, rol ausente/desconocido, sesión Clerk inexistente y denegación a vista dedicada sin login/logout. Implementar el guard sobre identidad local de `AutenticacionService`; esperar estado de identidad sin repetir `/auth/me`; crear/usar estado de acceso denegado accesible.

**Hecho cuando:** la suite frontend demuestra espera correcta, comparación exacta, no activación ante falta de permiso, permanencia de sesión y ausencia de redirección a login en 403 de navegación; guard auth sigue redirigiendo a `/login` con retorno sin sesión.

### T10 — Configurar rutas por rol y limitar capacidades UI (AC-2…AC-5, AC-15)

- [x] Probar y aplicar roles de ruta: dashboard e inventario para los cuatro; tickets para los cuatro con capacidades según rol; administración Superadmin/Administrador. Conservar `/`→dashboard, `/login` libre y `/health` público. Ocultar/desactivar para Solicitante operaciones Kanban/estado/despacho y acceso administrativo; no tratar controles UI como autorización API.

**Hecho cuando:** tests de rutas confirman sesión+rol en las cuatro áreas, capacidades por perfil sin alias, navegación a denegación dedicada, rutas públicas intactas y las acciones no autorizadas no se ofrecen al Solicitante.

## Bloque D — regresión y cierre

### T11 — Matriz integrada, OpenAPI y suites completas (AC-1…AC-16)

- [x] Ejecutar la matriz completa de pruebas de backend por operación/rol incluyendo 401/403/404, no mutación, ámbito, filtro de solicitantes, stock global y rol asignable; ejecutar suites completas `pytest` y `ng test` con Edge/ChromeHeadless, build de producción frontend y revisar `/openapi.json`. Ejecutar grep de credenciales local y confirmar que no se añadió dependencia.

**Hecho cuando:** ambas suites y build están verdes; OpenAPI y tests fijan denegaciones y contratos pertinentes; no hay credenciales/paquetes locales residuales ni regressions del flujo Clerk, tickets, inventario o despacho.

### T12 — Recorridos funcional y de humo con roles diferenciados (AC-2…AC-10, AC-14, AC-17)

- [x] En 4200, recorrer sesión Clerk con al menos un usuario de cada rol y comprobar navegación permitida/denegada, estado dedicado, intento directo API 403, límites institucionales, propiedad de tickets, creación por Solicitante y capacidades de Bodeguero/Administrador/Superadmin. Verificar escrituras reales y ausencia de cambios ante denegación. Reconstruir frontend (`docker compose -f docker-compose.yml build frontend`, luego `up -d frontend`) y repetir en 8080 un recorrido de humo con build nuevo; incluir ruta Angular directa y flujo básico.

**Hecho cuando:** evidencia separa 4200 funcional de 8080 humo, registra versión reconstruida, perfiles probados y respuestas/resultados observables sin incluir secretos.

### T13 — Registrar evidencia por AC y actualizar coherencia documental (AC-11…AC-17)

- [x] Solo tras completar verificaciones, registrar evidencia verificable para AC-1…AC-17 en `spec.md` sin alterar requisitos; actualizar `stack.md` si el patrón de autorización se convierte en norma, `MEMORY.md` y roadmap de acuerdo al estado real. Hacer grep de coherencia sobre `AGENTS.md`, `MEMORY.md` y `.agents/skills/` por rutas/afirmaciones obsoletas; corregir únicamente las referencias confirmadas. Incluir prueba de migración y OpenAPI en evidencia.

**Hecho cuando:** cada AC tiene evidencia concreta; `pytest`, `ng test`, `/openapi.json`, PostgreSQL migration test y recorridos 4200/8080 quedan documentados; documentación/grep son coherentes y roadmap solo pasa a cerrada cuando se cumplen AGENTS.md §8.5–§8.7.

---

## Cierre de feature (AC-17)

- [x] **C1 — Suites y build:** backend `pytest`, frontend `ng test --watch=false --browsers=ChromeHeadless` (Edge configurado) y build producción completan sin fallos.
  **Hecho cuando:** se adjuntan comandos y resultados finales. → `cd backend && .venv\Scripts\python.exe -m pytest` = **377 passed, 2 warnings**; `$env:CHROME_BIN=…msedge.exe; cd frontend && npx ng test --watch=false --browsers=ChromeHeadless` = **140 SUCCESS** (Edge 155); `ng build` OK (T11, 320.55 kB) reflejado en la imagen de producción reconstruida.
- [x] **C2 — Contrato API:** comprobar `/openapi.json`, seguridad bearer, rutas protegidas y respuestas 401/403 pertinentes.
  **Hecho cuando:** evidencia identifica las operaciones y esquemas revisados. → `/openapi.json` en vivo publica `HTTPBearer` (http/bearer) y cada operación de negocio exige bearer con 401 ("Credenciales ausentes o invalidas…") y 403 ("Identidad autenticada sin el rol requerido…"); `test_permisos_endpoints.py::test_openapi_*` fija el contrato.
- [x] **C3 — Migración PostgreSQL:** verificar instalación limpia y BD existente con segunda ejecución idempotente.
  **Hecho cuando:** usuarios/relaciones permanecen y columna está ausente en ambos escenarios. → En vivo sobre `compustock_db`/`apt_erp`: `usuario` sin `password` (`usuario_id, nombre, apellido, correo, departamento_id, rol_id`) con **12 usuarios/10 tickets** intactos; re-ejecución de `99_migracion_retiro_password.sql` con `ON_ERROR_STOP=1` → `NOTICE: column "password" … does not exist, skipping`, exit 0. Instalación limpia verificada en T8.
- [x] **C4 — Recorridos:** 4200 funcional con escrituras reales y 8080 tras build + `up -d` reconstruido.
  **Hecho cuando:** evidencia de ambos puertos y de perfiles/acciones queda registrada. → T12: 4200 funcional con 4 roles (Solicitante autoatribuido, 403/404, límite institucional del Admin, denegación sin escritura); 8080 humo sobre imagen `sha256:3862981…` (2026-10-14T16:02Z); T13 confirma ruta directa `/acceso-denegado` → 200.
- [x] **C5 — Coherencia y memoria:** grep §8.7; actualizar `MEMORY.md`, `stack.md` si procede y evidencia de spec; roadmap solo al cumplir todo lo anterior.
  **Hecho cuando:** no quedan referencias obsoletas y la documentación coincide con implementación verificada. → evidencia por AC en `spec.md`; `stack.md` §5 documenta el patrón de autorización; `MEMORY.md` actualizado a post-007; grep §8.7 corregido en `AGENTS.md` y `.agents/skills/`; `roadmap.md` 007 cerrada.

### Trazabilidad AC → tareas

| AC | Tareas |
|---|---|
| AC-1 | T1, T2, T9, T10, T11 |
| AC-2 | T9, T10, T12 |
| AC-3 | T10, T12 |
| AC-4 | T9, T10, T11 |
| AC-5 | T2, T10, T11 |
| AC-6 | T2, T4, T11, T12 |
| AC-7 | T2, T3, T4, T10, T11, T12 |
| AC-8 | T2, T3, T4, T5, T11, T12 |
| AC-9 | T1, T2, T3, T4, T11 |
| AC-10 | T2, T5, T11, T12 |
| AC-11 | T7, T13 |
| AC-12 | T6, T7, T11 |
| AC-13 | T8, T11, C3 |
| AC-14 | T6, T11, T12 |
| AC-15 | T1…T11 |
| AC-16 | T8, T11, C1, C3 |
| AC-17 | T12, T13, C1…C5 |

---

## Enmienda de autoatribución de tickets (22/Oct/2026)

> Cambio único transversal coordinado por `008/tasks.md` E22-1…E22-4, en este orden: backend → frontend → regresión conjunta → verificación/cierre. Las tareas aquí documentan AC-6 actualizado y AC-18…AC-20 de 007; no reejecutar ni solapar la secuencia común.

- [x] **E22-1 — Backend común: opcionalidad y autoría de sesión** (ejecución en `008/tasks.md` E22-1).
  - **Archivos:** schema/servicio/endpoint tickets y `test_tickets_alcance.py`, `test_tickets_institucional.py`, `test_modal_ticket.py`, `test_ticket_sede_011.py`, `test_transaccion_ticket.py` según el inventario por grep.
  - Rojo: reemplazar prueba de `usuario_id` obligatorio; actualizar creación para Administrador/Solicitante/Bodeguero y solicitante ajeno; campo ausente, propio, ajeno e inexistente no cambia autor. La identidad de sesión gobierna autor/institución. Sede departamental faltante → 409 sin datos; producto ajeno conserva 404 sin parcial. No tocar casos de despacho.
  - **AC:** AC-6, AC-18, AC-20.
  - **Hecho cuando:** HTTP y OpenAPI confirman opcionalidad/ignorado sin 422/403/404 por usuario; autoría e institución de sesión son observables; matriz y Superadmin 403 idénticos.
  - **Comando:** `backend\.venv\Scripts\python.exe -m pytest backend\tests\api\test_tickets_alcance.py backend\tests\api\test_tickets_institucional.py backend\tests\api\test_modal_ticket.py backend\tests\api\test_ticket_sede_011.py backend\tests\api\test_transaccion_ticket.py -q`.

- [x] **E22-2 — Frontend común: identidad visible sin selección** (ejecución en `008/tasks.md` E22-2).
  - **Archivos:** tickets componente/template/spec e interface compartida.
  - **AC:** AC-19.
  - **Hecho cuando:** no existe control `usuario_id` ni `<select>`; se ve nombre/apellido/correo de `AutenticacionService.identidad()` sin consulta nueva ni departamento; POST omite el campo; catálogo `solicitantes` permanece para listados/detalle.
  - **Comando:** `$env:CHROME_BIN = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"; cd frontend; npx ng test --watch=false --browsers=ChromeHeadless` (nunca `npm test`).

- [x] **E22-3 — Regresión de roles, catálogo y payloads** (ejecución en `008/tasks.md` E22-3).
  - **Archivos:** tests backend/frontend de tickets afectados.
  - Inventario del grep verificado; tests sustituidos: `test_roles_autorizados_atienden_la_identidad_de_sesion` (parametrizado por rol y por `usuario_id` omitido/propio/ajeno/inexistente), `test_administrador_crea_para_solicitante_propio_201`, `test_solicitante_crea_y_se_atribuye_su_identidad`, `test_administrador_ignora_solicitante_de_otra_institucion_y_atribuye_a_sesion`, `test_departamento_sin_sede_ignora_usuario_sede_id_y_responde_409` y `test_ticket_guarda_la_sede_del_departamento_no_la_del_usuario`; frontend: `formulario.controls.usuario_id.setValue(5)`, aserción de campo en body y pruebas de selector retiradas/reemplazadas. Conservar `test_crear_ticket_con_producto_ajeno_404_sin_parcial`, `test_crear_ticket_puebla_institucion_en_ticket_y_detalle`, pruebas del catálogo y payloads `TicketDespacho.usuario_id`.
  - **AC:** AC-6, AC-18…AC-20.
  - **Hecho cuando:** ninguna evidencia de rol atribuye alta a un usuario seleccionado y continúan verdes permisos/matriz, propiedad, catálogo de lectura, productos ajenos, sedes y despacho.
  - **Comandos:** `backend\.venv\Scripts\python.exe -m pytest`; `$env:CHROME_BIN = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"; cd frontend; npx ng test --watch=false --browsers=ChromeHeadless`.

- [x] **E22-4 — Verificación y evidencia coordinada** (ejecución en `008/tasks.md` E22-4).
  - **AC:** AC-6, AC-18…AC-20.
  - **Hecho cuando:** evidencia actualizada bajo AC de las tres specs, suites verdes, recorrido 4200 y humo 8080 tras rebuild frontend, `/openapi.json` revisado, `MEMORY.md` actualizado, grep de coherencia y roadmap solo si corresponde tras verificación; el estado histórico Cerrada de 007 no se altera automáticamente.
  - **Comandos:** `backend\.venv\Scripts\python.exe -m pytest`; `CHROME_BIN` a Edge + `npx ng test --watch=false --browsers=ChromeHeadless`; si se valida frontend, `docker compose -f docker-compose.yml build frontend` y `docker compose -f docker-compose.yml up -d frontend`.

### Cierre de enmienda

- [x] **E22-C1 — Suites, OpenAPI y dos puertos.** **AC:** AC-6, AC-18…AC-20. **Hecho cuando:** pytest SQLite/gated requerido y ng test pasan, OpenAPI refleja `usuario_id` opcional, 4200 prueba creación real y 8080 tras rebuild prueba humo de la UI; sin `npm test`.
- [x] **E22-C2 — Evidencia y coherencia.** **AC:** AC-18…AC-20. **Hecho cuando:** evidencia observada está en las tres specs; `MEMORY.md` concisa; grep `AGENTS.md`/`MEMORY.md`/`.agents/skills/` realizado y roadmap no se cambia sin completar gates.

### Matriz de trazabilidad de enmienda AC ↔ tareas

| AC | Tareas |
|---|---|
| AC-6 actualizado | E22-1, E22-3, E22-4, E22-C1 |
| AC-18 | E22-1, E22-3, E22-4, E22-C1, E22-C2 |
| AC-19 | E22-2, E22-3, E22-4, E22-C1, E22-C2 |
| AC-20 | E22-1, E22-3, E22-4, E22-C1, E22-C2 |

---

## Enmienda de alta reservada al Solicitante (26/Nov/2026)

> Tareas de la enmienda aprobada en `spec.md` (D-11…D-18, AC-21…AC-34). Nomenclatura
> `E26N` = enmienda del 26/Nov, para no confundirla con la Feature 026. Orden de dependencia:
> harness → matriz/contrato → sesión e institución → transcripciones → suites → frontend →
> documentación → cierre. No existe feature 028.

- [x] **E26N-1 — Harness de identidad mutable y cliente Solicitante.**
  - **Archivos:** `backend/tests/conftest.py`; ajustes mínimos en `_soporte_sede_011.py` solo si
    se reutiliza su patrón.
  - **Pruebas primero:** un test de humo del harness (primer caso de
    `test_alta_solo_solicitante_007.py` o un archivo hermano) que cree con
    `actuar_como("Solicitante")` y luego lea/apruebe con `actuar_como("Administrador")` usando
    el mismo `cliente`.
  - `_cliente_de_prueba` recibe `identidad_actual = {"actual": ...}` y overridea
    `get_current_user` con `lambda: identidad_actual["actual"]`; guarda y **restaura** los
    overrides que instala (no `clear()`). `cliente` conserva su firma y su valor por defecto
    Administrador; `cliente_sin_excepcion` comparte el contenedor. Fixture `actuar_como(rol)` y
    conveniencia `cliente_solicitante`.
  - `identidad_persistida(datos_base, rol)` garantiza de forma idempotente: Administrador = Ana;
    Bodeguero y Solicitante persistidos en `datos_base["departamento_id"]`; reutiliza el rol
    Solicitante si `dos_instituciones` ya lo creó. La sede **no** se autoasigna: la resuelve
    cada suite con `asegurar_sede_de_departamento`.
  - **AC:** habilita AC-21…AC-33 (sin AC propio).
  - **Hecho cuando:** un mismo test alterna Solicitante → Administrador/Bodeguero sin recrear
    el cliente ni pisar overrides; la suite existente sigue verde sin cambiar sus expectativas;
    no hay usuario/rol nuevo en `datos_base` para todas las suites.
  - **Comando:** `cd backend && .venv\Scripts\python.exe -m pytest -q`.

- [x] **E26N-2 — Matriz, contrato y docstring del alta (AC-21…AC-25, AC-28, AC-29).**
  - **Archivos:** `backend/app/core/permisos.py`, `backend/app/api/v1/endpoints/tickets.py`,
    `backend/app/services/ticket_service.py`, `backend/tests/funcional/integracion/test_alta_solo_solicitante_007.py` (nuevo).
  - **Rojo:** pruebas de AC-21 (201 Solicitante con autoría/institución/sede/`Pendiente`/
    historial; `usuario_id` ignorado; 422/404/409), AC-22/AC-23 (403 Admin/Bodeguero con
    payload válido y cero filas en ticket/detalle/historial), AC-24 (payload JSON parseable
    inválido → 403; Solicitante → 422), AC-25 (Superadmin 403), AC-28 (capacidad apagada y
    rehabilitada).
  - **Verde:** fila `("POST", "/api/v1/tickets/")` a `frozenset({_SOLICITANTE})`; retirar
    `_ESCRITURA_TICKETS`; actualizar la descripción del endpoint (solo descripción) y el
    docstring de `crear_ticket`. Sin comprobación de rol en el servicio, sin 409 en
    `responses`, sin cambio de `response_model`/201/dependencias. Para AC-28, reutilizar el
    patrón `_sembrar_contexto_capacidades` de `test_ciclo_vida_confirmacion_013.py` y usar su
    correo de contexto en la identidad del Solicitante; si se comparte, moverlo a
    `_soporte_ciclo_vida_013.py`.
  - **AC:** AC-21, AC-22, AC-23, AC-24, AC-25, AC-28, AC-29.
  - **Hecho cuando:** las pruebas nuevas pasan; la matriz sigue con 75 operaciones; el
    decorador conserva 201/401/403/404/422 y el 409 solo en la descripción; ningún otro rol
    crea tickets.
  - **Comando:** `cd backend && .venv\Scripts\python.exe -m pytest tests/funcional/integracion/test_alta_solo_solicitante_007.py -q`.

- [x] **E26N-3 — Sesión e institución inactiva (AC-26, AC-27).**
  - **Archivos:** `backend/tests/no_funcional/seguridad/test_institucion_inactiva_012.py` (dos
    casos nuevos al final).
  - **Pruebas primero:** 401 sin `Authorization` y con Bearer inválido/expirado; con institución
    inactiva (`_preparar(activo=False)`), Administrador y Bodeguero → 403 por matriz, Solicitante
    → 401 del contexto de tenant; sin filas. Usar `TestClient(app)` real con overrides de
    `get_db`/`get_current_user`; la identidad del Solicitante usa el correo mapeado en
    `_preparar` (`u.inst01@compustock.cl`). No usar el `cliente` que inyecta identidad para el
    401.
  - **AC:** AC-26, AC-27.
  - **Hecho cuando:** ambos códigos se observan con la app real y el endpoint de alta; no se
    reordena ninguna dependencia ni se cambia la autenticación.
  - **Comando:** `cd backend && .venv\Scripts\python.exe -m pytest tests/no_funcional/seguridad -q`.

- [x] **E26N-4 — Seis transcripciones de la matriz y correlación (AC-29, AC-33).**
  - **Archivos:** `test_permisos.py`, `test_permisos_008.py`, `test_permisos_010.py`,
    `test_permisos_012.py`, `test_permisos_endpoints.py`,
    `test_ciclo_vida_autorizacion_013.py`, `test_correlacion_024.py`.
  - Añadir la restricción documentada `("POST", "/api/v1/tickets/") -> {"Solicitante"}` con el
    patrón de `RESTRINGIDAS_013`; en `test_permisos_endpoints.py` actualizar `MATRIZ_D3` (los
    casos permitidos/denegados se regeneran) y en `test_permisos_008.py` documentar la excepción
    a `OPERACIONES_AJUSTADAS`, ajustar `CASOS_AJUSTADOS` (Admin/Bodeguero 403, Solicitante 200)
    y excluir el alta de `test_administrador_conserva_las_escrituras_institucionales`. En
    `test_correlacion_024.py`, esperar 403 y conservar las aserciones del log.
  - **AC:** AC-29, AC-33.
  - **Hecho cuando:** las seis transcripciones reflejan el alta solo para Solicitante sin
    borrar operaciones ni rebajar conteos; `test_permisos_008` conserva las demás operaciones
    ajustadas; la suite de permisos y correlación pasa.
  - **Comando:** `cd backend && .venv\Scripts\python.exe -m pytest tests/no_funcional/seguridad tests/funcional/integracion/test_ciclo_vida_autorizacion_013.py -q`.

- [x] **E26N-5 — Suites de altas vivas con cliente Solicitante (AC-21, AC-30, AC-33).**
  - **Archivos:** `humo/test_smoke.py`, `e2e/test_transaccion_ticket.py`,
    `integracion/test_modal_ticket.py`, `integracion/test_tablero_kanban.py`,
    `e2e/test_despacho_transaccional.py`, `integracion/test_ciclo_vida_alta_inicial_013.py`,
    `integracion/test_ciclo_vida_historial_013.py`,
    `e2e/test_flujo_aprobacion_entrega_013.py`, `integracion/test_ticket_proceso_013.py`,
    `integracion/test_ticket_sede_011.py`, `integracion/test_historial_movimientos.py`,
    `integracion/test_validacion_entradas_027.py`, `integracion/test_tickets_alcance.py`,
    `integracion/test_tickets_institucional.py`.
  - Cambiar solo las altas a `actuar_como("Solicitante")`/`cliente_solicitante`; conservar las
    operaciones con Administrador/Bodeguero (aprobación, despacho, rechazo, `PATCH`) y las
    aserciones de propiedad/ámbito. Añadir `asegurar_sede_de_departamento` donde falte.
  - **AC:** AC-21, AC-30, AC-33.
  - **Hecho cuando:** las 14 suites pasan sin que ninguna alta use Administrador/Bodeguero; la
    cobertura de autoatribución queda en el Solicitante; no se borran casos de 404/409/422 ni de
    propiedad.
  - **Comando:** `cd backend && .venv\Scripts\python.exe -m pytest tests/funcional -q`.

- [x] **E26N-6 — Fixtures históricos de autoría Admin/Bodeguero (AC-31, AC-33).**
  - **Archivos:** `test_ciclo_vida_confirmacion_013.py` (referencia), suites que necesiten un
    ticket histórico; `test_alta_solo_solicitante_007.py` para AC-31.
  - Sembrar por ORM (`Ticket`, `DetalleTicket`, `HistorialTransicionTicket`) los tickets con
    autor Administrador/Bodeguero que prueban AC-31/AC-43; no crearlos con el alta del
    Solicitante ni reasignar autores.
  - **AC:** AC-31, AC-33.
  - **Hecho cuando:** los escenarios históricos conservan su autor y ciclo de vida; ningún
    fixture se convirtió en alta de Solicitante; cobertura 021 y Compras no se tocaron.
  - **Comando:** `cd backend && .venv\Scripts\python.exe -m pytest tests/funcional/integracion/test_ciclo_vida_confirmacion_013.py tests/funcional/integracion/test_alta_solo_solicitante_007.py -q`.

- [x] **E26N-7 — Frontend: espejo y comentarios (AC-32, AC-34).**
  - **Archivos:** `frontend/src/app/core/auth/roles.ts`, `roles.spec.ts`,
    `frontend/src/app/features/tickets/tickets.component.ts`, `tickets.component.spec.ts`.
  - Solo comentarios y títulos: dejar de decir «demo/presentación» o «la API sigue admitiendo a
    los tres roles». **No** añadir guarda de apertura, no tocar template ni servicio.
  - **AC:** AC-32, AC-34.
  - **Hecho cuando:** el botón sigue visible solo al Solicitante, oculto a Admin/Bodeguero; el
    modal y el body sin `usuario_id` no cambian; `ng test` verde.
  - **Comando:** `$env:CHROME_BIN = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"; cd frontend; npx ng test --watch=false --browsers=ChromeHeadless`.

- [x] **E26N-8 — Documentación y coherencia (AC-34).**
  - **Archivos:** `docs/spec/features/012-gestion-administrativa/diseno-tecnico.md`,
    `docs/spec/roadmap.md`, `MEMORY.md`; nota de la 003 ya presente.
  - Anotar/superar la transcripción de la 012; registrar la enmienda en la fila/estado de la 007
    sin anunciar la 028; sustituir en `MEMORY.md` la nota de demo y la mención «028–029».
  - **AC:** AC-34.
  - **Hecho cuando:** grep en `docs/`, `backend/` y `frontend/` sin afirmaciones vigentes de que
    el alta admite tres roles o que la restricción es solo presentación; no hay feature 028.
  - **Comando:** `rg -n "sigue admitiendo|tres roles|solo presentación|demo 25/Nov|028" docs backend frontend`.

- [x] **E26N-9 — Cierre: suites, contrato y dos puertos (AC-21…AC-34).**
  - **Hecho cuando:** `pytest` y `ng test` verdes; `/openapi.json` publica 75 operaciones v1/77
    totales, la descripción del alta nombra al Solicitante y declara 201/401/403/404/422 (409
    solo en descripción); 4200 con Solicitante creando y Admin/Bodeguero recibiendo 403 sin
    perder tablero/detalle; 8080 reconstruido (`docker compose -f docker-compose.yml build frontend`
    + `up -d frontend`) con humo de la vista; evidencia AC-21…AC-34 registrada sin inventar
    observaciones; grep de coherencia ejecutado.
  - **AC:** AC-21…AC-34.
  - **Comando:** `cd backend && .venv\Scripts\python.exe -m pytest`; frontend con `CHROME_BIN` a
    Edge y `npx ng test --watch=false --browsers=ChromeHeadless`; nunca `npm test`.
  - **Corrección post-validación (26/Nov/2026, tras veredicto CAMBIOS NECESARIOS):**
    (a) comentario de `backend/app/core/permisos.py` alineado con D-13/AC-24 —403 de matriz con
    JSON **parseable** y posible 422 de JSON malformado antes de las dependencias—; la fila y el
    comportamiento no cambian. (b) La imagen anterior era del **25/Nov 18:02 -03**, previa a los
    archivos del 26/Nov 03:57: se reconstruyó **sin caché** (`build --no-cache frontend` +
    `up -d --force-recreate frontend`); imagen nueva **2026-11-26T17:43:22Z = 14:43 -03**,
    contenedor `healthy`, bundle **`main-GULMVWMA.js`** (mismo hash: el delta de UI eran solo
    comentarios) y humo 8080: Admin/Bodeguero sin «+ Crear pedido» y POST real **403** con tablero
    y detalle operativos; Solicitante con botón, modal «Solicitante (sesión)» sin `usuario_id` y
    POST **201** (#12: autor 11/Paula Rojas, `Pendiente`, sede 2, 1 detalle y 1 historial).
    (c) Suites de la corrección: focal `test_alta_solo_solicitante_007.py` **41 passed**,
    `tests/no_funcional/seguridad` **463 passed** y `ng test` **639 SUCCESS**.

### Trazabilidad de la enmienda AC ↔ tareas

| AC | Tareas |
|---|---|
| AC-21 | E26N-1, E26N-2, E26N-5, E26N-9 |
| AC-22 | E26N-1, E26N-2, E26N-9 |
| AC-23 | E26N-1, E26N-2, E26N-9 |
| AC-24 | E26N-2, E26N-9 |
| AC-25 | E26N-2, E26N-9 |
| AC-26 | E26N-3, E26N-9 |
| AC-27 | E26N-3, E26N-9 |
| AC-28 | E26N-2, E26N-9 |
| AC-29 | E26N-2, E26N-4, E26N-9 |
| AC-30 | E26N-5, E26N-9 |
| AC-31 | E26N-2, E26N-6, E26N-9 |
| AC-32 | E26N-7, E26N-9 |
| AC-33 | E26N-1, E26N-4, E26N-5, E26N-6, E26N-9 |
| AC-34 | E26N-7, E26N-8, E26N-9 |
