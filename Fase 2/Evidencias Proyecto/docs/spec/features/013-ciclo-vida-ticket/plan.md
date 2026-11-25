# Feature 013 — Plan técnico

Spec: [`spec.md`](spec.md). La spec está aprobada por el usuario; este plan concreta su implementación sin alterar alcance. No se añaden dependencias.

## 0. Nota de estado de la spec

La aprobación corresponde al usuario/coordinador; la cabecera de `spec.md` aún refleja `**Estado:** borrador` y su actualización pertenece al flujo de aprobación, no a este plan. Este plan no modifica la spec; toda duda de diseño resoluble a nivel técnico se decide aquí y se marca como decisión con su alternativa descartada.

## 1. Prerrequisito desbloqueante: justificación en `stack.md`

La sección «Ciclo de vida del ticket: estado `Anulado` e historial de transiciones (Feature 013)» fue incorporada al final de §2 de `docs/spec/stack.md` (patrón de las secciones 011/012). Fija:

- `Anulado` como quinta fila del catálogo `estado_ticket` replicado por tenant, de presencia obligatoria en toda instalación (semilla, constructor, migración con token `013.1`), sin CRUD.
- `historial_transicion_ticket` como **15.ª entidad de dominio** (no auxiliar): hecho de negocio inmutable, visible por API, con FK a `ticket`, `usuario` y `estado_ticket`; el modelo pasa de 14 a 15 entidades de dominio.
- Por qué `fecha_cierre` **no** se sella en la anulación y por qué no hay segunda columna de fecha.
- Por qué el token sube de `012.1` a `013.1` y por qué las transiciones previas no se reconstruyen.

**Bloqueo:** ninguna tarea puede tocar `backend/app/models/`, `backend/app/schemas/`, `database/` ni `VERSION_ESQUEMA_OBJETIVO` hasta que el usuario/coordinador apruebe ese apartado en `stack.md` (mismo mecanismo de bloqueo de la 012, §6).

## 2. Impacto en la matriz de permisos y en el gating de la 012

- **La matriz pasa de 44 a 49 operaciones** (aditivo; ninguna fila existente se modifica). Las 5 nuevas, con los roles exactos del AC-17:

  | Operación | Roles permitidos |
  |---|---|
  | `POST /api/v1/tickets/{ticket_id}/anulacion` | Solicitante, Administrador |
  | `POST /api/v1/tickets/{ticket_id}/rechazo` | Bodeguero, Administrador |
  | `PUT /api/v1/tickets/{ticket_id}` | Solicitante, Administrador |
  | `GET /api/v1/tickets/{ticket_id}` | los cuatro roles |
  | `GET /api/v1/tickets/{ticket_id}/historial` | los cuatro roles |

  Superadmin queda **fuera de toda escritura** (403) y conserva lectura global de detalle e historial (AC-17/AC-19). Un rol limitado ajeno al ticket recibe **404 idéntico** al inexistente (patrón de ocultamiento vigente).

- **Gating de capacidades de la 012** (`app/core/capacidades.py`, sin tocar la matriz): las 5 operaciones se asocian a capacidades existentes —conjunto cerrado de seis, sin capacidad nueva—. Decisión: anulación y rechazo → `kanban` (son mutaciones del ciclo de vida, la misma familia que `PATCH /estado` y `POST /despacho` que la 012 ya gateó bajo `kanban`); edición, detalle e historial → `tickets` (gestión y consulta del ticket, la familia de `GET /tickets/` y `POST /tickets/`). **Alternativa descartada:** crear una capacidad `ciclo_vida` (rompe el conjunto cerrado de la 012) y asociar todas a `tickets` (dejaría anular/rechazar disponibles con `kanban` deshabilitada, separando mutaciones equivalentes de la misma familia). El gating se aplica con `requiere_capacidad(...)` en cada ruta nueva; `/auth/me` y `/control/*` siguen sin gating.

## 3. Decisiones técnicas (con alternativa descartada)

1. **Tabla de historial vs. columnas en `ticket`.** Se crea la tabla `historial_transicion_ticket` (decisión D-10 de la spec). **Descartado:** añadir `estado_anterior`, `fecha_anulacion`, `motivo_anulacion`… al ticket: una sola fila por ticket no puede representar el ciclo completo (creación → revisión → curso → cierre/anulación con actores distintos) y multiplicaría columnas por cada transición posible.
2. **`GET /tickets/{id}/historial` propio vs. historial embebido en el detalle.** Se crea el endpoint separado (spec §6). **Descartado:** embeberlo en `GET /tickets/{id}`: el detalle se carga siempre y el historial crece de forma independiente; un endpoint aparte permite reconsultar solo el historial tras cada transición (AC-24) sin retraer la cabecera, y mantiene response_models simples.
3. **Motivo validado en el servicio, no en Pydantic.** `TicketMotivo` acepta `motivo: str` sin restricciones de vacío/longitud; el servicio valida no vacío y longitud ≤ 500 y responde **422**. Es imprescindible para el orden 404 → 409 → 422 del AC-7: si Pydantic rechazara el payload, el 422 se dispararía **antes** del handler y ganaría al 404 de un ticket inexistente. **Descartado:** validación en el schema (incumple AC-7 ante problemas simultáneos).
4. **Dos endpoints (`/anulacion`, `/rechazo`) vs. uno genérico con bandera.** Dos operaciones (D-7): conjuntos de roles distintos en la matriz y significado público distinto. **Descartado:** `POST /anulacion` con `tipo=rechazo` (la matriz no podría distinguir los roles sin una operación intermedia, y el contrato público perdería semántica).
5. **Terminales por nombre, no por ordinal.** `ticket_service` resuelve `cerrado` y `anulado` con `_resolver_estado_por_nombre` (casefold, menor `estado_id` ante duplicados) y la regla de flujo deja de usar `indice_actual == len(estados) - 1` como único terminal. El `PATCH /estado` responde **409** con detalle que dirige a `/anulacion` o `/rechazo` si el destino es `Anulado` o el origen es `Anulado` (AC-4), y conserva intactos el orden de validación 404→404→409 y la guarda de cierre reservado al despacho de la 005. **Descartado:** mantener la terminalidad ordinal (con `Anulado` al final del catálogo convertiría a `Cerrado` en no-terminal y habilitaría `Cerrado → Anulado`).
6. **Un solo helper de servicio para anulación y rechazo.** `_cambiar_a_anulado(db, ticket_id, motivo, identidad)` comparte el camino (404 alcance → 409 estado → 422 motivo → escritura atómica de ticket + fila de historial); la distinción de roles vive en la matriz, no en el servicio. **Descartado:** duplicar la lógica en dos funciones.
7. **Edición con `PUT` y reemplazo atómico del conjunto de detalles.** `editar_ticket` valida todo el payload (referencias 404, forma 422) antes de escribir; luego borra los detalles previos e inserta los nuevos y actualiza la cabecera en **una sola transacción** (AC-15). **Descartado:** patch parcial por campo (dejaría cabecera sin detalles ante un fallo a mitad) y `PATCH` con campos parciales (la spec fija payload equivalente al alta).
8. **Alta con `estado_id = Anulado` → 409.** D-11 exige rechazarlo; el 409 ("estado existente pero no elegible para alta") sigue el patrón de conflictos de precondición de la 004/005. **Descartados:** 422 (el estado es válido en forma, inválido en precondición) y 404 (mentiría: el estado existe en el catálogo).
9. **Filas de historial del alta y del despacho.** `crear_ticket` inserta la fila de creación (`estado_origen_id` nulo, destino = estado inicial, actor = identidad autenticada; en invocación directa al servicio sin identidad —no observable por HTTP— usa `ticket.usuario_id`) y `despachar_ticket` inserta su transición en la misma transacción ACID que ya maneja (AC-5/AC-9/AC-11).
10. **KPI del dashboard por nombre exacto.** `_contar_tickets_activos` pasa de excluir `nombre != 'Cerrado'` a `nombre NOT IN ('Cerrado', 'Anulado')`, conservando la semántica de coincidencia exacta documentada en la 009 (AC-22). **Descartado:** excluir también variantes de mayúsculas (rompería la decisión documentada de la 009 de contar `cerrado`/`CERRADO` como activos).
11. **Detalle e historial del Superadmin global vía `global_service.leer_global_unico`.** Mismo patrón que la lectura global de lista: recorre tenants en una transacción `REPEATABLE READ` y devuelve el primer ticket resoluble; un rol limitado usa su única sesión (AC-19).
12. **Sin filas de historial en la semilla.** `02_datos_semilla.sql` añade la fila `Anulado` pero **no** inventa filas de historial para sus tickets QA (AC-12: sin trazabilidad fabricada); el historial vacío de un ticket sembrado ejercita el estado vacío del detalle. **Descartado:** siembra de filas de creación (datos ficticios de trazabilidad, prohibidos por D-10).

## 4. Archivos previstos y responsabilidades

### Base de datos

| Archivo | Responsabilidad | AC |
|---|---|---|
| `database/01_esquema.sql` | `control.historial_transicion_ticket` (PK, FKs locales a `ticket`/`estado_ticket`×2/`usuario`, `motivo VARCHAR(500)`), tras `detalle_ticket`; `estado_ticket` sin cambio de DDL (fila nueva solo en semilla). | AC-9, AC-20 |
| `database/02_datos_semilla.sql` | Quinta fila `(5, 'Anulado', …)` al final del `INSERT` de `estado_ticket` (preserva el orden del flujo de la 003, D-4); la guardia fail-closed suma la tabla nueva a sus canónicas ("16 tablas"); sin filas de historial. | AC-20 |
| `database/03_construir_tenants_011.sql` (constructor vigente) | Plantilla de `historial_transicion_ticket` en `v_plantillas` (se replica a cada tenant); `v_version_objetivo` `012.1` → `013.1`; los tenants ya reciben `Anulado` por el `INSERT … SELECT * FROM control.estado_ticket`. | AC-20, AC-21 |
| `database/migraciones/004_migracion_ciclo_vida_ticket_013.sql` (nuevo) | Migración operacional explícita `012.1 → 013.1`, patrón del bloque único `DO` de la 002/003: preflight (control y tenants en `012.1`, sin estructura 013 parcial), `INSERT` idempotente de `Anulado` (`WHERE NOT EXISTS` por nombre) en control y cada tenant, `CREATE TABLE IF NOT EXISTS historial_transicion_ticket` en control y cada tenant, versión al final y verificación global fail-closed. Sin semilla destructiva, sin DELETE, sin reconstrucción de historial. | AC-20, AC-21 |

### Backend

| Archivo | Responsabilidad | AC |
|---|---|---|
| `backend/app/models/ticket.py` | Modelo `HistorialTransicionTicket` (mapeo exacto del DDL; relaciones a `Ticket`, `Usuario`, `EstadoTicket` origen/destino). | AC-9 |
| `backend/app/models/__init__.py` | Exportar el modelo nuevo en el paquete (SQLite/heredado lo crea `Base.metadata`). | AC-9 |
| `backend/app/schemas/ticket_schema.py` | `TicketMotivo` (entrada de anulación/rechazo, sin validación de vacío/longitud — decisión 3), `HistorialTransicionRespuesta`, `TicketEditar` (asunto, descripción, prioridad_id, detalles; sin `usuario_id`), `TicketDetalleRespuesta` si `TicketRespuesta` no basta para el contrato del detalle. | AC-8, AC-10, AC-13 |
| `backend/app/core/permisos.py` | 5 filas nuevas (sección «Feature 013», comentario explícito de aditividad); 44 → 49 operaciones; ninguna fila previa modificada. | AC-17 |
| `backend/app/core/capacidades.py` | 5 asociaciones nuevas (kanban ×2, tickets ×3) en `MAPA_OPERACION_CAPACIDAD`. | AC-1…AC-4, AC-17 |
| `backend/app/core/config.py` | `VERSION_ESQUEMA_OBJETIVO = "013.1"` (comentario actualizado). | AC-20, AC-21 |
| `backend/app/services/ticket_service.py` | `NOMBRE_ESTADO_ANULADO`; terminales por nombre; `_registrar_transicion(...)` (misma transacción que el cambio); filas de creación y de despacho; guards `Anulado` en `actualizar_estado_ticket` (409 dirigiendo a la operación); `anular_ticket`/`rechazar_ticket` sobre `_cambiar_a_anulado` (orden 404→409→422); `editar_ticket` (404→409 `Pendiente`→validación total→reemplazo atómico de detalles); `obtener_ticket_detalle` y `obtener_historial_ticket` con alcance por rol y `leer_global_unico` para Superadmin; rechazo del `estado_id` `Anulado` en `crear_ticket` (409). | AC-1…AC-19 |
| `backend/app/services/dashboard_service.py` | `_contar_tickets_activos` excluye `('Cerrado', 'Anulado')` por nombre exacto. | AC-22 |
| `backend/app/api/v1/endpoints/tickets.py` | 5 rutas nuevas con `response_model`, `status_code`, OpenAPI, `respuestas_de_autorizacion()` + `respuesta_recurso_oculto()` (+ `respuesta_conflicto()` donde aplica), `requiere_operacion` y `requiere_capacidad`; descripción de `PATCH /estado` actualizada con los 409 de `Anulado`. | AC-1…AC-19 |
| `backend/tests/` | Ver §6. | AC-1…AC-22, AC-25 |

### Frontend

| Archivo | Responsabilidad | AC |
|---|---|---|
| `frontend/src/app/shared/interfaces/index.ts` | Tipos nuevos 1:1 con los schemas: `HistorialTransicion`, `TicketEditar` (y `TicketDetalle` si aplica). | AC-23 |
| `frontend/src/app/features/tickets/services/ticket.service.ts` | `obtenerDetalleTicket`, `obtenerHistorial`, `anularTicket`, `rechazarTicket`, `editarTicket`. | AC-23, AC-24 |
| `frontend/src/app/features/tickets/ticket-detalle.component.ts` (+ `.html`, `.spec.ts`) | Vista de detalle standalone (nueva, `frontend-design`): cabecera, ítems con cantidades solicitadas/entregadas, fechas, historial completo; barra de acciones por estado y rol (avanzar/retroceder vía `PATCH /estado`, editar en `Pendiente`, anular/rechazar con modal de confirmación que exige motivo); errores 404/409/422 accesibles (`role="alert"`), anti doble envío y reconsulta tras cada mutación. Signals + `computed()`, Tailwind, `inject()`. | AC-23, AC-24 |
| `frontend/src/app/features/tickets/tickets.routes.ts` | Ruta hija `tickets/:ticketId` con `loadComponent` perezoso. | AC-24 |
| `frontend/src/app/features/tickets/tickets.component.ts` (+ `.html`, `.spec.ts`) | Tablero a solo lectura: se **eliminan** los botones avanzar/retroceder y su lógica (`puedeAvanzar`/`puedeRetroceder`/`estadoAnteriorId`/`estadoSiguienteId`, `errorMovimiento` de transición); cada tarjeta ofrece **Gestionar** → navega al detalle; la columna `Anulado` surge sola del catálogo; se conservan filtros y modal de alta. | AC-24 |
| `frontend/src/app/core/auth/roles.ts` | Helpers de presentación espejo de la matriz (`puedeAnularTicket`, `puedeRechazarTicket`, `puedeEditarTicket`); `ROLES_TICKETS` intacto (Superadmin no navega `/tickets` desde la 012; su lectura global de detalle es solo API). | AC-16, AC-24 |
| `frontend/src/app/features/dashboard/` | Sin cambios: el KPI se corrige en el backend y el componente ya muestra el valor del API. | AC-22 |

### Documentación

| Archivo | Responsabilidad | AC |
|---|---|---|
| `docs/spec/stack.md` | Sección de modelo aprobada (§1 de este plan). | AC-20, AC-21 |
| `docs/spec/features/013-ciclo-vida-ticket/spec.md`, `tasks.md`, `roadmap.md`, `MEMORY.md`, `AGENTS.md` (§7) | Al cierre: evidencia por AC, tareas, y el grep de coherencia (§8.7) que actualice el conteo «14 → 15 entidades de dominio» en `AGENTS.md` §7 y `MEMORY.md`. `AGENTS.md` lo edita el coordinador/implementer, no el planner. | AC-25 |

## 5. Estrategia de pruebas

### Backend SQLite (`pytest` ordinario)

- TDD sobre la interfaz HTTP (`TestClient`, patrón del `conftest.py` vigente): primero los tests de los endpoints nuevos y luego la implementación.
- Flujo y estados (AC-1…AC-7): anulación/rechazo desde `Pendiente`/`EnRevision` → 200 con ticket en `Anulado`, `fecha_cierre` nula, stock intacto y fila de historial; 409 desde `EnCurso`/`Cerrado`/`Anulado` sin efectos; guards de `PATCH /estado` hacia/desde `Anulado` (409 literal) y despacho de un `Anulado` (409 de la 005 intacto); alta con `Anulado` → 409.
- Orden de respuestas (AC-7): casos con problemas simultáneos para cada combinación 404/409/422 (motivo vacío y largo ≤ escala).
- Historial (AC-9…AC-12): exactamente una fila por mutación (creación, cambio de estado, despacho, anulación, rechazo), origen nulo solo en la creación, orden `fecha_transicion DESC, historial_transicion_id DESC`, atomicidad (fila y estado juntos), sin endpoints de escritura del historial, ticket legado con historial vacío.
- Edición (AC-13…AC-16): reemplazo completo de detalles, estado/solicitante/sede/institución intactos, 409 fuera de `Pendiente`, validación total sin escritura parcial, 404/403 por rol.
- Autorización (AC-17…AC-19): matriz por operación (los 5 roles exactos; Superadmin 403 en escritura), 404 idéntico inexistente/ajeno, `/openapi.json` con las 49 operaciones, 401/403/404/409/422 documentados y aserción de no-modificación de las 44 filas previas.
- KPI (AC-22): anulado no cuenta como activo para ningún rol; resto de KPI intacto.
- Gating (012): capacidad `kanban`/`tickets` apagada → 403 sin mutación en las 5 operaciones nuevas.

### PostgreSQL gated (`POSTGRES_TEST_URL`, obligatorio para cierre)

- Nuevo módulo `tests/funcional/sistema/test_ciclo_vida_ticket_postgres_013.py` con el patrón de los gated de 011/012 (`skip` sin la variable):
  - **Migración `012.1 → 013.1`** sobre una base construida con el mismo harness de la 012 (cadena `01 → 02 → 03` + migraciones `001`–`003` hasta `012.1`, aspecto real de una instalación existente): `Anulado` presente en control y cada tenant, tabla creada, datos/mapas/historial previo intactos, segunda ejecución sin cambios, fallo de preflight sin versión parcial.
  - **Constructor/initdb** (`01 → 02 → 03` recién levantado): tenants nacen en `013.1` con `Anulado` replicado y la tabla creada.
  - **Token de versión:** un tenant en `012.1` (sin los cambios 013) **deniega cerrado** en el routing con el objetivo `013.1`, y solo se enrutan tenants exactamente en `013.1` (AC-21).
- Actualizar los tests que fijan el literal `012.1` como objetivo vigente (`test_control_modelo_010.py`, `api/test_control_instituciones_010.py`, `_soporte_sede_011.py`, `api/test_capacidades_gating_012.py`, `test_aprovisionamiento_postgres_010.py`, `test_gestion_administrativa_postgres_012.py`): preferir importar `VERSION_ESQUEMA_OBJETIVO` en vez de repetir el literal. El test gated de la migración 012 conserva su propio objetivo `012.1` como fase de la cadena; revisar que ninguna aserción exija enrutar a `012.1` con el nuevo objetivo.

### Frontend

- `npx ng test --watch=false --browsers=ChromeHeadless` con `$env:CHROME_BIN` apuntando a Edge (AGENTS §5; nunca `npm test`).
- Actualizar `tickets.component.spec.ts` (tablero sin controles de transición, acción Gestionar, columna `Anulado`) y crear `ticket-detalle.component.spec.ts` (render por estado/rol, estados vacíos, mensajes `role="alert"` en 404/409/422, confirmación con motivo obligatorio, sin doble envío).
- `ng build` de producción limpio. Sin paquetes nuevos.

### Recorridos de cierre (AC-25)

`pytest` ordinario en verde; suite gated con `POSTGRES_TEST_URL` en verde; `ng test` y `ng build`; inspección de `/openapi.json`; recorrido funcional en 4200 con escritura real (alta → anulación con motivo → detalle con historial → edición → rechazo, más regresión de despacho); `docker compose -f docker-compose.yml build frontend` + `up -d frontend` y humo en 8080. Evidencia y cierre conforme a `AGENTS.md` §8.5–§8.7 (incluido el grep de coherencia que actualice `AGENTS.md` §7 y `MEMORY.md`).

## 6. Riesgos y cobertura spec → plan

| Riesgo | Mitación |
|---|---|
| La terminalidad ordinal vigente convierte `Cerrado` en no-terminal al añadir `Anulado` | Decisión 5: terminales por nombre en `actualizar_estado_ticket`; tests de 409 `Cerrado → Anulado` y de regresión del flujo 004. |
| El 422 de Pydantic se adelanta al 404/409 (AC-7) | Decisión 3: motivo validado en servicio; test con problema simultáneo. |
| Migración deja `Anulado` o la tabla a medias por tenant | Bloque único `DO` + verificación global + gated de reejecución y de fallo inyectado (patrón 002/003). |
| Bump de versión rompe tests gated previos que fijan `012.1` | Actualizar literales/import; revisar el test de la migración 012 dentro de la cadena. |
| El tablero hereda lógica muerta de transiciones al quitar botones | Eliminar señales y métodos obsoletos junto con los botones; spec del componente actualizada. |
| UI de 8080 desactualizada | Rebuild obligatorio antes del humo (AGENTS §5/§8.6). |

| AC | Partes |
|---|---|
| AC-1, AC-2, AC-3 | `ticket_service` (anulación/rechazo), endpoints, permisos/capacidades, tests de flujo. |
| AC-4, AC-5, AC-6, AC-7 | Guards de `PATCH /estado` y despacho, terminales por nombre, orden de respuestas, tests. |
| AC-8 | `TicketMotivo` + validación en servicio (decisión 3), tests 422. |
| AC-9…AC-12 | Modelo/tabla, `_registrar_transicion`, semilla/migración sin filas inventadas, tests de historial. |
| AC-13…AC-16 | `editar_ticket` + `TicketEditar`, alcance por rol, tests de edición. |
| AC-17…AC-19 | `permisos.py` (49 operaciones), `capacidades.py`, OpenAPI, ocultamiento 404, `leer_global_unico`. |
| AC-20, AC-21 | `01_esquema.sql`, `02_datos_semilla.sql`, constructor, migración `004_…013.sql`, `config.py`, gated. |
| AC-22 | `dashboard_service._contar_tickets_activos`, tests de KPI. |
| AC-23, AC-24 | Componente de detalle, tablero a solo lectura, rutas, `ticket.service.ts`, `roles.ts`, specs Angular. |
| AC-25 | Suites completas, build y recorridos en 4200/8080, evidencia y grep de coherencia. |

## 7. Condición de bloqueo

No iniciar ninguna tarea de modelos, schemas, DDL, semilla, constructor, migración ni `VERSION_ESQUEMA_OBJETIVO` hasta la aprobación del apartado de `stack.md` (§1). Si la implementación revela una contradicción real con la spec aprobada —p. ej. un contrato de códigos imposible de satisfacer con el orden 404→409→422, o un rol que la matriz no puede representar—, se detiene la tarea y se eleva el hallazgo al coordinador; no se amplía la spec ni se corrige el código de forma implícita. El `tasks.md` de la 013 se genera en la fase posterior, con tareas en orden de dependencia ancladas a este plan.

## 8. Enmienda post-cierre (05/Nov/2026): alta fija en `Pendiente` y prioridad `Media`

**Alcance:** solo `backend/app/services/ticket_service.py` (+ descripción OpenAPI de
`POST /tickets`) y `frontend/src/app/features/tickets/tickets.component.{ts,html,spec.ts}`. Sin
modelo, sin DDL, sin semilla, sin migración, sin permisos nuevos, sin cambios de matriz.

**Backend.** `crear_ticket` resuelve `Pendiente` por nombre canónico (nueva constante
`NOMBRE_ESTADO_PENDIENTE = "pendiente"` + `_resolver_estado_por_nombre`, mismo patrón que
`Anulado`/`Cerrado`), exige que `datos.estado_id` sea ese id y que el catálogo lo contenga;
ambos incumplimientos responden **409** antes del primer `add()`. Se retiran la rama de sellado
en `Cerrado` y la mención específica de `Anulado` (subsumida por la regla general; el 409 sigue
existiendo). La validación de referencia (`_verificar_referencia`) va antes, así que un id ajeno
sigue siendo **404** y no 409. Los tests que sembraban tickets en otro estado vía API pasan a
sembrarlos por ORM (patrón `sembrar_ticket` de `_soporte_ciclo_vida_013.py`) o a crear en
`Pendiente` y transicionar con `PATCH /estado`; el fixture `datos_base` renombra sus estados a
`Pendiente`/`Cerrado`, que es lo que el resto de la suite ya usa por id.

**Frontend.** El modal muestra el estado inicial como dato de solo lectura (nombre del catálogo,
etiqueta «Fijo», sin `<select>`); el `FormControl estado_id` se llena por código y se envía con
`getRawValue()`. `estadoInicial()` y `prioridadInicial()` resuelven por nombre canónico
(`mismo` patrón que `NOMBRE_ESTADO_ANULADO`), y un `aplicarValoresPorDefecto()` los fija al
cargar catálogos y tras cada alta exitosa. La prioridad conserva su `<select>` habilitado.

**Riesgo principal:** el renombrado de `datos_base` (`INGRESADO`→`Pendiente`). Se acota a un
fixture y a las aserciones de orden de `test_modal_ticket.py`; ninguna otra suite fija el nombre
del primer estado (grep `INGRESADO` en `backend/tests`).

## 9. Ampliación 25/Nov/2026 — flujo de aprobación, etiqueta de proceso y confirmación de entrega

**Alcance.** Implementa la §9 de la spec (AC-28…AC-49): aprobación Admin-only a `EnCurso`,
`PATCH /estado` solo para `Administrador` y como legado, etiqueta de proceso derivada con
responsables, tablero con «Terminados», detalle con acciones semánticas y confirmación de entrega.
**Sin DDL, sin migración, sin token nuevo, sin `docs/spec/stack.md`, sin cambios en Compras, la
021, el despacho de la 005 ni el modelo:** el token sigue en `026.0`, 26/23 tablas y 21 entidades.
La matriz pasa de **73 a 75** operaciones v1 y `/openapi.json` de **75 a 77** entradas; el `PATCH`
conserva su entrada y solo cambia de rol.

### 9.1 Decisiones técnicas (con alternativa descartada)

1. **Etiqueta derivada en el servidor, en un módulo puro.** `backend/app/services/ticket_proceso.py`
   (nuevo) concentra constantes (`MOTIVO_APROBACION = "Aprobación del pedido"`,
   `MOTIVO_CONFIRMACION_ENTREGA = "Entrega confirmada por el solicitante"`), el mapa de
   etiquetas/frases y `derivar_etiqueta(estado_nombre, estado_orden_cobertura, stock_disponible,
   entrega_confirmada) -> tuple[str, str]`, sin ORM ni sesión. `ticket_service` lo consume.
   **Descartado:** derivar en el frontend (tablero y detalle podrían divergir y cada vista
   replicaría la precedencia) y meter el mapeo en `ticket_service` (ya supera 1.600 líneas; el
   módulo puro se prueba sin BD).
2. **Un read model por lote, no por ticket.** `ticket_service._cargar_proceso_tickets(db, tickets)`
   hace **cuatro bloques** de consulta para toda la lista: (a) `stock_disponible` con
   `compra_service.calcular_cobertura_tickets` una vez por `sede_id` distinta; (b) cobertura de OC
   (`OrdenCompraTicket` ⋈ `OrdenCompra`, estados `Emitida`/`Facturada`/`Recibida`,
   `cantidad_asignada > 0`, reducida a una fila por ticket con el estado de mayor rango); (c)
   confirmaciones (`Cerrado → Cerrado` con el motivo exacto); (d) gestores
   (`HistorialTransicionTicket` ⋈ `Usuario` ⋈ `Rol`, roles `Bodeguero`/`Administrador`, orden
   `fecha_transicion DESC`, `historial_transicion_id DESC`). **Descartado:** resolver la etiqueta
   con `calcular_cobertura_tickets` por ticket (N+1 y simulaciones inconsistentes) y cargar el
   historial completo de cada ticket para los gestores (el detalle ya lo hace; el listado no lo
   necesita).
3. **`stock_disponible` en el listado con una simulación por sede.** La 020 ya devuelve
   `{ticket_id: bool}` para todos los `EnCurso` de una sede; el listado agrupa por `sede_id`, la
   invoca una vez por sede y usa `false` para el resto. **Descartado:** añadir una columna o un
   cálculo por ticket (DDL y N+1); se conserva el contrato de la 020 (solo `EnCurso`).
4. **Cobertura de OC en `ticket_service`, no en `compra_service`.** La consulta lee
   `orden_compra_ticket`/`orden_compra` y reduce el rango en Python; no toca el paquete de la 021.
   **Descartado:** exportar un helper nuevo de `compra_service` (la 021 no cambia y el paquete
   queda cerrado) y un `CASE` SQL complejo (la reducción en Python es determinista y portable).
5. **Confirmación como fila `Cerrado → Cerrado`, sin DDL.** `confirmar_entrega` inserta
   `HistorialTransicionTicket` con el `Cerrado` canónico, actor, fecha, motivo literal y
   `orden_compra_id = NULL`; la existencia se detecta por el motivo exacto. **Descartado:**
   columna/tabla nueva o un `200` idempotente (la spec exige 409 y el modelo no cambia).
6. **Aprobación con bloqueo de fila.** `select(Ticket).with_for_update()` al inicio, patrón de la
   005; la validación de estado y la fila de historial ocurren dentro de la transacción.
   **Descartado:** comprobación optimista (dos aprobaciones concurrentes escribirían dos filas y
   la segunda no daría 409).
7. **`TicketRespuesta` base + `TicketDetalleRespuesta` por herencia.** Los campos derivados viven
   en la base; el detalle añade `entrega_confirmada_en`/`_por_*` y conserva `asignaciones`. El
   listado y el detalle se construyen con `TicketRespuesta.model_validate(ticket)` +
   `model_copy(update=proceso)` (el detalle, con su construcción manual actual). **Descartado:**
   un DTO de listado separado (duplicaría campos y el detalle dejaría de heredar) y poblar los
   campos en el ORM (atributos transitorios fuera del modelo).
8. **`PATCH /estado` como legado y rol en la matriz.** La restricción a `Administrador` vive en
   `permisos.py`; la UI no lo invoca. **Descartado:** ocultarlo solo en la UI (la API seguiría
   concediendo al Bodeguero) y retirar la operación (rompe clientes y la regla de un paso de la
   004).
9. **La aprobación y la confirmación devuelven `TicketRespuesta` construido por el servicio** (la
   spec promete la etiqueta en el 200). El `PATCH` y el despacho siguen devolviendo el ORM: sus
   esquemas tienen los campos con su valor por defecto y la UI reconsulta. **Descartado:** cambiar
   todas las mutaciones a DTO (más superficie y riesgo) y devolver el ORM en la aprobación (la
   etiqueta prometida faltaría).
10. **Un solo diálogo discriminado en el detalle.** `confirmando` pasa a
    `'anular' | 'rechazo' | 'despacho' | 'entrega'`; el motivo solo se muestra para anular/rechazo.
    **Descartado:** dos `<dialog>` nuevos (duplica foco, `Esc` y estilos).
11. **El tablero agrupa en el componente.** `columnas` mapea `Pendiente`, `EnRevision` y `EnCurso`
    y una columna «Terminados» con los `estado_id` de `Cerrado` y `Anulado`. **Descartado:**
    agrupar en el backend (presentación pura) y eliminar la columna `EnRevision` (los heredados
    deben seguir visibles).
12. **Sin cambios en `compra_service`/021.** La etiqueta solo lee; la aprobación no evalúa stock.
    **Descartado:** recalcular `stock_disponible` con el candidato (la regla de auto-avance ya no
    existe).

### 9.2 Backend: DTOs y read model

- `TicketRespuesta` gana `etiqueta_proceso: str`, `explicacion_proceso: str`,
  `estado_orden_cobertura: str | None`, `stock_disponible: bool` (se mueve desde
  `TicketDetalleRespuesta`), `entrega_confirmada: bool`, `gestionado_por_bodeguero:
  GestorProcesoRespuesta | None` y `gestionado_por_administrador: GestorProcesoRespuesta | None`.
- `GestorProcesoRespuesta`: `usuario_id`, `nombre` y `apellido`.
- `TicketDetalleRespuesta` añade `entrega_confirmada_en`, `entrega_confirmada_por_nombre` y
  `entrega_confirmada_por_apellido`; conserva `asignaciones`/`cadena_productos`.
- `ticket_proceso.py`: constantes, `ETIQUETAS`/`EXPLICACIONES`, `rango_estado_orden` y
  `derivar_etiqueta`. `EnRevision` → «En revisión»; `EnCurso` con OC `Recibida` o
  `stock_disponible` → «En confirmación de stock local»; sin OC ni stock → «Por comprar».
- `ticket_service.listar_tickets` deja de devolver ORM y devuelve `List[TicketRespuesta]`
  construidos en la misma sesión (el wrapper `agregar_lista_global` concatena DTOs; no le importa
  el tipo). El orden, el filtro `estado_id` y el alcance por rol no cambian.
- `ticket_service.obtener_ticket_detalle` completa la base con el mismo helper y añade la
  fecha/actor de la confirmación. El detalle ya carga `asignaciones_db`; deriva
  `estado_orden_cobertura` de esas filas filtrando `Cancelada` y tomando el mayor rango (sin
  consulta extra).
- Los gestores se resuelven con el rol **vigente** (`Usuario.rol`), orden
  `fecha_transicion DESC, historial_transicion_id DESC`, primera fila por `(ticket, rol)`. Un
  actor sin usuario/rol resoluble no cuenta.
- La confirmación se detecta por `estado_origen_id = estado_destino_id = <Cerrado>` y
  `motivo = MOTIVO_CONFIRMACION_ENTREGA`; el `Cerrado` se resuelve por nombre (menor id ante
  duplicados) una vez por consulta.
- La etiqueta degrada para estados fuera del conjunto canónico: nombre visible + «Estado no
  reconocido por la etiqueta de proceso».
- La construcción del DTO ocurre dentro de la sesión del tenant (sin `DetachedInstanceError`; el
  listado global de Superadmin no aplica desde la 017, pero el wrapper sigue siendo seguro).

### 9.3 Backend: aprobación y `PATCH` de legado

- `ticket_service.aprobar_ticket(db, ticket_id, identidad)`:
  1. `select(Ticket).where(...).with_for_update()`; si no existe o está fuera de alcance, 404
     (mismo `_verificar_alcance_de_ticket`).
  2. Resuelve `Pendiente`, `EnRevision` y `EnCurso` por nombre (casefold, menor id). Sin
     `EnCurso`, **409** fail-closed.
  3. Si `ticket.estado_id` no es `Pendiente` ni `EnRevision`, **409** sin escribir (incluye
     `EnCurso`, `Cerrado`, `Anulado` y estados fuera del catálogo).
  4. `ticket.estado_id = EnCurso.id`; `_registrar_transicion(db, ticket, origen, EnCurso.id,
     identidad, MOTIVO_APROBACION)`; `commit`; `rollback` ante excepción.
  5. Devuelve `TicketRespuesta` con el proceso cargado (`_respuesta_ticket_con_proceso`), no el
     ORM.
- `permisos.py`: `POST /tickets/{id}/aprobacion` → `{Administrador}`; `PATCH /tickets/{id}/estado`
  → `{Administrador}` (deja de usar `_ESCRITURA_STOCK`); `POST /tickets/{id}/despacho` conserva
  `_ESCRITURA_STOCK`. Matriz 73 → 74 en esta sección; la segunda operación (74 → 75) llega en
  §9.4.
- `capacidades.py`: aprobación → `kanban`; el `PATCH` sigue `kanban`.
- `tickets.py`: endpoint `POST /{ticket_id}/aprobacion` sin payload, `response_model=TicketRespuesta`,
  `status_code=200`, `respuestas_de_autorizacion()`, `respuesta_recurso_oculto()`,
  `respuesta_conflicto()`, `requiere_operacion` + `requiere_capacidad("POST", ruta)`. Descripción
  con el 409 de estado/catálogo y el 403 del Bodeguero. El `PATCH` actualiza su descripción: solo
  Administrador, sin destino efectivo distinto del solicitado.
- La aprobación es una operación propia; el `PATCH` conserva la regla de un paso, el cierre
  reservado y la terminalidad. No se toca el servicio de despacho.

### 9.4 Backend: confirmación de entrega

- `ticket_service.confirmar_entrega(db, ticket_id, identidad)`:
  1. `select(Ticket).where(...).with_for_update()`; 404 si no existe o está fuera de alcance;
     404 si `ticket.usuario_id != identidad.usuario.usuario_id` (defensa; la matriz ya limita a
     `Solicitante`).
  2. Resuelve `Cerrado` por nombre; **409** si el pedido no está `Cerrado`.
  3. Si ya existe una fila `Cerrado → Cerrado` con `MOTIVO_CONFIRMACION_ENTREGA`, **409** sin
     escribir.
  4. Inserta `HistorialTransicionTicket` con origen/destino `Cerrado`, actor, fecha del servidor,
     motivo y `orden_compra_id = NULL`; `commit`; `rollback` ante excepción. No cambia
     `estado_id`, `fecha_cierre`, stock ni movimientos.
  5. Devuelve `TicketRespuesta` con `entrega_confirmada = true` y la etiqueta «Entregado».
- `permisos.py`: `POST /tickets/{id}/confirmacion-entrega` → `{Solicitante}`; matriz 74 → 75.
  `capacidades.py`: `tickets`.
- `tickets.py`: endpoint sin payload, `response_model=TicketRespuesta`, 200, 401/403/404/409,
  dependencias. Descripción con «solo el Solicitante dueño» y el 409 de ya confirmado.
- La confirmación es un evento, no una transición: `GET /historial` la devuelve como
  `Cerrado → Cerrado` con el motivo; AC-9 sigue siendo una fila por mutación de estado.

### 9.5 Backend: archivos y responsabilidades

| Archivo | Responsabilidad | AC |
|---|---|---|
| `backend/app/schemas/ticket_schema.py` | `GestorProcesoRespuesta`; campos base y de detalle; `stock_disponible` en la base. | AC-39 |
| `backend/app/services/ticket_proceso.py` (nuevo) | Constantes, etiquetas/frases, `rango_estado_orden`, `derivar_etiqueta`; funciones puras. | AC-37, AC-38, AC-40 (puro) |
| `backend/app/services/ticket_service.py` | `_cargar_proceso_tickets`, `_respuesta_ticket_con_proceso`, `listar_tickets` con DTO, detalle, `aprobar_ticket`, `confirmar_entrega`. | AC-29…AC-43 |
| `backend/app/core/permisos.py` | Aprobación `{Administrador}`; confirmación `{Solicitante}`; `PATCH` `{Administrador}`; 73 → 75. | AC-44, AC-45, AC-49 |
| `backend/app/core/capacidades.py` | Aprobación → `kanban`; confirmación → `tickets`. | AC-44 |
| `backend/app/api/v1/endpoints/tickets.py` | Dos rutas nuevas, OpenAPI, descripción del `PATCH`. | AC-29…AC-46 |
| `backend/tests/…` | §9.7. | AC-28…AC-49 |

### 9.6 Frontend: archivos y responsabilidades

| Archivo | Responsabilidad | AC |
|---|---|---|
| `frontend/src/app/shared/interfaces/index.ts` | `GestorProceso`; campos base en `Ticket` y de detalle en `TicketDetalle` (opcionales para no romper fixtures). | AC-39 |
| `frontend/src/app/features/tickets/services/ticket.service.ts` | Retira `actualizarEstado`; añade `aprobarTicket`, `despacharTicket(id, usuarioId)` y `confirmarEntrega`. | AC-32, AC-42, AC-43 |
| `frontend/src/app/core/auth/roles.ts` | `puedeAprobarTicket` (Administrador), `puedeDespacharTicket` (Administrador/Bodeguero) y `puedeConfirmarEntrega` (Solicitante); retira `puedeOperarTickets` si queda sin consumidor. | AC-32, AC-45, AC-49 |
| `frontend/src/app/features/tickets/ticket-detalle.component.{ts,html,spec.ts}` | Acciones semánticas, diálogo discriminado, despacho, confirmación, etiqueta/frase/responsables/línea de entrega; sin Avanzar/Retroceder ni `PATCH`. | AC-32…AC-43, AC-48 |
| `frontend/src/app/features/tickets/tickets.component.{ts,html,spec.ts}` | Columnas `Pendiente`/`EnRevision`/`EnCurso`/«Terminados»; tarjeta con etiqueta, frase accesible y responsables; enlace al detalle. | AC-37…AC-41, AC-47 |
| `frontend/src/app/features/tickets/ticket.service.spec.ts` (nuevo) | URL, verbo y payload de las tres operaciones nuevas. | AC-32, AC-42 |
| `frontend/src/app/core/auth/roles.spec.ts` | Helpers nuevos y retirados. | AC-32, AC-45 |

### 9.7 Estrategia de pruebas

**Backend SQLite (ordinario)**

- Unitarios: `test_ticket_proceso_013.py` (etiquetas, frases, precedencia, estados desconocidos,
  rango de OC) y contrato de los DTO (campos base/detalle, `GestorProcesoRespuesta`).
- Integración: `test_ticket_proceso_013.py` (listado y detalle con los campos, etiqueta coherente,
  responsables, confirmación, y **conteo de consultas** con `before_cursor_execute` para 1 vs N
  tickets; patrón de `test_tablero_kanban.py`).
- Aprobación: `test_ciclo_vida_aprobacion_013.py` (200 desde `Pendiente`/`EnRevision`, siempre
  `EnCurso`, fila de historial exacta, atomicidad, 409 ya/terminal/catálogo, 404, 403
  rol/capacidad, `PATCH` Bodeguero 403).
- Confirmación: `test_ciclo_vida_confirmacion_013.py` (200 dueño, fila exacta, etiqueta
  `Entregado`, sin estado/stock/`fecha_cierre`, 404 ajeno, 403 roles/capacidad, 409 no `Cerrado`,
  409 ya confirmado, alta administrativa sin confirmación).
- E2E: `test_flujo_aprobacion_entrega_013.py` (alta → aprobar → etiqueta → Compras/021 →
  despachar → confirmar; 409/403/404; `PATCH` de legado sin uso en la UI).
- Regresión: actualizar los recuentos y roles de matriz/OpenAPI, el no-N+1 del listado y los tests
  que usaban al Bodeguero para el `PATCH` (ver §9.8).

**PostgreSQL gated (`POSTGRES_TEST_URL`, obligatorio para cierre)**

- `test_ciclo_vida_aprobacion_confirmacion_postgres_013.py`: dos sesiones concurrentes sobre la
  misma fila → aprobación `(200, 409)` con **una** fila; confirmación `(200, 409)` con **una**
  fila `Cerrado → Cerrado`; lectura persistida del actor, fecha, motivo y `orden_compra_id NULL`;
  `fecha_cierre`/stock intactos; sin DDL. SQLite no acredita el bloqueo.

**Frontend**

- `ticket.service.spec.ts`: URL/verbo/payload de `aprobarTicket`, `despacharTicket` y
  `confirmarEntrega`; ausencia de `actualizarEstado`.
- `roles.spec.ts`: `puedeAprobarTicket`/`puedeDespacharTicket`/`puedeConfirmarEntrega`.
- `ticket-detalle.component.spec.ts`: acciones por estado/rol, sin Avanzar/Retroceder, Aprobar solo
  Administrador, Despachar solo `EnCurso` + `stock_disponible`, Confirmar entrega solo dueño +
  `Cerrado` sin confirmar, diálogos, 409 accesibles, sin doble envío, reconsulta, etiqueta/frase/
  responsables/línea de entrega.
- `tickets.component.spec.ts`: 4 columnas, «Terminados» con `Cerrado`+`Anulado`, sin columna
  `Anulado`, etiqueta/frase accesible/responsables, tarjeta-enlace, no-N+1 (2 peticiones).
- `npx ng test --watch=false --browsers=ChromeHeadless` con `$env:CHROME_BIN` a Edge; `ng build`
  limpio.

**Contrato**

- `/openapi.json`: **75** operaciones v1 (**77** entradas con `GET /` y `/health`), las 73 previas
  con sus roles salvo el `PATCH` (solo `Administrador`), la aprobación con `401/403/404/409` y la
  confirmación con `401/403/404/409`.

### 9.8 Pruebas existentes que quedan obsoletas o deben reconciliarse

**Backend**

- `test_permisos_endpoints.py` (inventario rutas↔matriz): `MATRIZ_D3` y el recuento a 75; las dos
  rutas nuevas publicadas.
- `test_cobertura_021.py` / tests de matriz de la 021: 73 → 75; `test_openapi_publica…73` → 75;
  la aserción de las 73 previas conserva roles salvo el `PATCH`.
- `test_ciclo_vida_autorizacion_013.py`: si la aserción de matriz es viva, 49 → 75; el `PATCH` con
  Bodeguero pasa a 403.
- `test_ciclo_vida_flujo_013.py`, `test_ciclo_vida_alta_inicial_013.py` y
  `test_despacho_transaccional.py`: los `PATCH` ejecutados con Bodeguero se cambian a Administrador
  (o se añade la aserción 403); el 409 de cierre reservado se conserva con Administrador.
- `test_tablero_kanban.py`: el conteo de consultas del listado sube por el read model; el número
  esperado se actualiza y se mantiene la aserción de no-N+1.
- `test_despacho_dtos.py`/tests de contrato de `TicketRespuesta` y `TicketDetalleRespuesta`: el
  conjunto exacto de campos se amplía; `stock_disponible` deja de estar duplicado en el detalle.
- `test_permisos_012.py`/`test_capacidades_gating_012.py`: si el `PATCH` se ejercita con
  Bodeguero, se cambia a Administrador; la aprobación se añade a `kanban` y la confirmación a
  `tickets`.

**Frontend**

- `tickets.component.spec.ts`: fuera la columna `Anulado` y el grid de 5; dentro «Terminados»,
  el contador sumado, la etiqueta/frase/responsables y el enlace.
- `ticket-detalle.component.spec.ts`: fuera los specs de Avanzar/Retroceder y del `PATCH`; dentro
  Aprobar/Despachar/Confirmar entrega, la etiqueta/responsables/línea de entrega y la ausencia de
  `PATCH`.
- `roles.spec.ts`: fuera `puedeOperarTickets` si se retira; dentro los tres helpers nuevos.

### 9.9 Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| El listado pasa a construir DTOs y añade consultas | Read model por lote: una simulación por sede, una consulta de OC, una de confirmaciones y una de gestores; test de conteo fijo con 1 vs N tickets. |
| Los recuentos absolutos de la matriz/OpenAPI (49 históricos, 73 vivos; 75 y 77 nuevos) rompen suites | Reconciliación explícita en §9.8 y en los tests de contrato; grep de `73`, `49`, `75`, `77` y `openapi` en `backend/tests`. |
| Pedidos heredados en `EnRevision` | La aprobación los acepta; el tablero conserva la columna; no se produce el estado en el flujo nuevo; tests de aprobación desde ambos orígenes. |
| Pedidos creados por Admin/Bodeguero sin confirmación posible | La acción no se ofrece; el dueño sin rol `Solicitante` recibe 403; el pedido queda «Despachado»; test explícito. |
| Carrera stock/despacho | La aprobación no evalúa stock; el despacho sigue validando y devuelve 409; la UI reconsulta y retira la acción. |
| Campos aditivos rompen contratos exactos o fixtures | Actualizar los tests de campos exactos; tipos TS opcionales; los DTO de mutación existentes conservan defaults y la UI reconsulta. |
| El `PATCH` restringido rompe clientes/tests con Bodeguero | Cambiar los actores a Administrador o asertar 403; actualizar la descripción OpenAPI; el `MATRIZ` y el inventario de rutas. |
| La confirmación se duplica por carrera | Bloqueo de fila + detección por motivo; gated PG con dos sesiones y una sola fila. |
| 8080 sirve la imagen vieja | `docker compose build frontend` + `up -d frontend` antes del humo (AGENTS §5/§8.6). |

### 9.10 Cobertura AC → partes

| AC | Partes |
|---|---|
| AC-28, AC-29, AC-30, AC-36 | `aprobar_ticket`, `PATCH` sin auto-avance, `ticket_proceso`, tests de flujo/historial. |
| AC-31 | Compras/021 sin cambios; aprobación a `EnCurso`; tests de necesidades. |
| AC-32, AC-33, AC-34 | Detalle: acciones, despacho, 409; frontend. |
| AC-35 | Invariantes: sin DDL, token `026.0`, 26/23, 21 entidades. |
| AC-37, AC-38, AC-39 | `ticket_proceso`, DTOs, read model de listado/detalle. |
| AC-40 | Consulta de gestores por lote; UI de responsables. |
| AC-41 | Tablero «Terminados», etiqueta/frase/responsables; frontend. |
| AC-42, AC-43 | `confirmar_entrega`, endpoint, matriz, UI, gated PG. |
| AC-44, AC-45, AC-46, AC-49 | Matriz 75, OpenAPI 77, aprobación Admin-only, PATCH 403, tests de contrato. |
| AC-47, AC-48 | `EnRevision` heredado, acciones semánticas y PATCH de legado sin uso en la UI. |
| Cierre de la enmienda | Suites, build, 4200/8080, evidencia y grep. |

### 9.11 Verificación de cierre

- `pytest` SQLite completo sin regresiones y con los tests nuevos en verde; gated PostgreSQL 16 con
  `POSTGRES_TEST_URL` (concurrencia y filas de historial), sin skips accidentales.
- `ng test` con Edge headless y `ng build` de producción limpios.
- `/openapi.json`: **75** operaciones v1 (**77** entradas), el `PATCH` solo Administrador, la
  aprobación y la confirmación con sus códigos.
- 4200 con escritura real: alta → aprobar (etiqueta «En confirmación de stock local» o «Por
  comprar») → despachar → confirmar entrega; tablero con «Terminados»; detalle sin
  Avanzar/Retroceder; caso #10 fuera de Compras; un pedido con necesidad aparece tras la
  aprobación; `PATCH` de legado 403 para Bodeguero y 200 para Administrador.
- 8080 tras `docker compose -f docker-compose.yml build frontend` + `up -d frontend`; humo de la
  vista y del flujo básico.
- Evidencia bajo cada AC-28…AC-49; `MEMORY.md` lo actualiza el coordinador al cierre; grep de
  coherencia sobre `AGENTS.md`, `MEMORY.md` y `.agents/skills/` (PATCH/roles/etiquetas/columnas).
- **Sin DDL, sin migración, sin `stack.md`, sin tocar `roadmap.md`**: la fila 013 ya está `[x]` y
  la enmienda se registra en `spec.md` y `evidencia/`.
