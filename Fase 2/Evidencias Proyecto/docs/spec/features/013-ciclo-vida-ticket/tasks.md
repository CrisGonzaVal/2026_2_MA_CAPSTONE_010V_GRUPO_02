# Feature 013 — Tareas

Spec: [`spec.md`](spec.md) · Plan: [`plan.md`](plan.md)

> Ejecutar en orden, una tarea por llamada, con pruebas primero. Leyenda: **`[!]` = bloqueado** (no iniciar hasta levantarlo). **El bloqueo del plan §7 ya está levantado:** el apartado de modelo de `docs/spec/stack.md` («Ciclo de vida del ticket: estado `Anulado` e historial de transiciones (Feature 013)») fue aprobado por el usuario, por lo que ninguna tarea aparece `[!]` y T4–T5 pueden tocar modelos/schemas/DDL/semilla/constructor/migración/`VERSION_ESQUEMA_OBJETIVO` (T1 deja constancia). Tareas **[PostgreSQL gated]** requieren `POSTGRES_TEST_URL`; las **[SQLite]** corren en la suite ordinaria; las **[ng test]** exigen `$env:CHROME_BIN` apuntando a Edge (AGENTS §5, nunca `npm test`). Ante discrepancia con spec/plan, detenerse y elevarla al coordinador; no ampliar la spec ni corregir el código de forma implícita (plan §7).

## Preparación y pruebas

- [x] **T1 — Constatar el prerrequisito aprobado y habilitar las tareas de modelo (bloqueante levantado).**
  - Archivos: `docs/spec/stack.md` (solo lectura), este `tasks.md`.
  - El apartado de modelo de la 013 en `stack.md` §2 fue aprobado por el usuario: `Anulado` como quinta fila del catálogo replicado, `historial_transicion_ticket` como 15.ª entidad de dominio, razón de `fecha_cierre` nula y del token `013.1`. Con eso, el bloqueo del plan §7 queda levantado y T4–T5 quedan **habilitadas**. No editar `stack.md`, `spec.md`, `plan.md` ni `roadmap.md` salvo los apartados de cierre previstos en el plan §4.
  - **AC:** AC-20, AC-21 (prerrequisito).
  - **Hecho cuando:** esta tarea consta `[x]` con la referencia a la sección aprobada de `stack.md` y ninguna tarea de modelo/DDL/migración figura marcada `[!]`.

- [x] **T2 — Pruebas rojas TDD de contrato, flujo e historial.**
  - Archivos: nuevos módulos de `backend/tests/funcional/integracion/` (013) y gated `backend/tests/funcional/sistema/test_ciclo_vida_ticket_postgres_013.py`.
  - Redactar primero los tests rojos del plan §5: anulación/rechazo y guards (AC-1…AC-7), motivo (AC-8), historial —exactamente una fila por mutación, origen nulo solo en creación, orden `fecha_transicion DESC, historial_transicion_id DESC`, atomicidad, ticket legado sin filas— (AC-9…AC-12), edición (AC-13…AC-16), autorización/matriz/OpenAPI (AC-17…AC-19), KPI (AC-22); en el gated, los esqueletos de migración `012.1 → 013.1`, constructor y token de versión para T5.
  - **AC:** AC-1…AC-22.
  - **Hecho cuando:** pytest identifica cada AC con sus casos, las pruebas nuevas fallan solo por las ausencias previstas y ninguna prueba previa queda roja. **[SQLite; PostgreSQL gated para migración]**

- [x] **T3 — Desacoplar el literal `012.1` de los tests que fijan la versión vigente (temprana, previa al bump).**
  - Archivos: `backend/tests/funcional/integracion/test_control_modelo_010.py`, `backend/tests/funcional/integracion/test_control_instituciones_010.py`, `backend/tests/funcional/integracion/_soporte_sede_011.py`, `backend/tests/no_funcional/seguridad/test_capacidades_gating_012.py`, `backend/tests/funcional/sistema/test_aprovisionamiento_postgres_010.py`, `backend/tests/funcional/sistema/test_gestion_administrativa_postgres_012.py`.
  - Importar `VERSION_ESQUEMA_OBJETIVO` de `app.core.config` en vez de repetir el literal (plan §5); el gated de la migración 012 conserva su propio `012.1` como fase de la cadena. Hacerlo antes del bump de T5 para que el cambio de objetivo no rompa las suites gated previas; revisar que ninguna aserción exija enrutar a `012.1` con el nuevo objetivo.
  - **AC:** AC-20, AC-21.
  - **Hecho cuando:** un grep en `backend/tests/` confirma que el literal de la versión objetivo solo vive en `config.py` (más la fase `012.1` de la cadena de migraciones) y ambas suites siguen verdes con el objetivo vigente. **[SQLite + PostgreSQL gated]**

## Base de datos: modelo, DDL, semilla, constructor y migración

- [x] **T4 — Modelo ORM, DDL y semilla: estado `Anulado` e historial de transiciones.**
  - Archivos: `backend/app/models/ticket.py`, `backend/app/models/__init__.py`, `database/01_esquema.sql`, `database/02_datos_semilla.sql`.
  - Crear `HistorialTransicionTicket` con mapeo exacto de `stack.md` (PK `historial_transicion_id`, FKs locales a `ticket`, `estado_ticket` ×2 y `usuario`, `motivo VARCHAR(500)` nullable) y exportarlo en el paquete; añadir `control.historial_transicion_ticket` en el DDL tras `detalle_ticket` (el de `estado_ticket` no cambia); quinta fila `(5, 'Anulado', …)` al final del `INSERT` de `estado_ticket` (preserva el orden lineal de la 003); ampliar la guardia fail-closed de la semilla a las 16 canónicas; **sin** filas de historial sembradas (AC-12: sin trazabilidad fabricada).
  - **AC:** AC-9, AC-12, AC-20 (estructura y semilla de instalación nueva).
  - **Hecho cuando:** la metadata SQLite crea la tabla por el export del modelo, una base temporal limpia la crea en control y siembra `Anulado`, y tras el initdb no existe ninguna fila de historial. **[SQLite + PostgreSQL gated]**
    - *Hecho (18/Oct/2026):* la metadata SQLite crea la tabla (columnas/FKs verificadas con el venv); contra PostgreSQL 16 real, `01 + 02` sobre una base temporal crean `control.historial_transicion_ticket` (7 columnas, 4 FK locales), siembran `(5, 'Anulado')` al final del catálogo y dejan el historial con 0 filas; la guardia fail-closed aborta la semilla sobre una base poblada. La guardia y el TRUNCATE de la semilla cubren **17** tablas canónicas (las 16 previas + la nueva; la semilla contaba ya 16 en su SELECT pese al comentario obsoleto "quince", actualizado). El gated de instalación nueva seguirá en rojo hasta T5 (constructor/migración/token) y los SQLite hasta T7–T9 (rutas/servicio), como prevé el plan.

- [x] **T5 — Constructor de tenants, migración operacional `004_…013.sql` y token `013.1`.**
  - Archivos: `database/03_construir_tenants_011.sql` (constructor vigente), `database/migraciones/004_migracion_ciclo_vida_ticket_013.sql` (nuevo), `backend/app/core/config.py`.
  - Plantilla de `historial_transicion_ticket` en `v_plantillas` y `v_version_objetivo` → `013.1` en el constructor (los tenants reciben `Anulado` por el `INSERT … SELECT` del catálogo de control); migración explícita `012.1 → 013.1` como bloque único `DO` (patrón 002/003): preflight (control y tenants en `012.1`, sin estructura 013 parcial), `INSERT` idempotente de `Anulado` por nombre (`WHERE NOT EXISTS`) en control y cada tenant, `CREATE TABLE IF NOT EXISTS` en control y cada tenant, versión al final y verificación global fail-closed; sin semilla destructiva, sin DELETE y sin reconstrucción de historial; `VERSION_ESQUEMA_OBJETIVO = "013.1"` con comentario actualizado.
  - **AC:** AC-20, AC-21.
  - **Hecho cuando:** el gated verifica la cadena `01 → 02 → 03` + migraciones `001`–`003` hasta `012.1` → migración 004 con `Anulado` y tabla en control y cada tenant, datos/mapas/historial previo intactos, segunda ejecución sin cambios y fallo de preflight sin versión parcial; el constructor limpio nace en `013.1` con ambas novedades replicadas; un tenant en `012.1` deniega cerrado con el objetivo nuevo. **[PostgreSQL gated obligatorio]**
    - *Hecho (18/Oct/2026):* gated `test_ciclo_vida_ticket_postgres_013.py` **7/7 en verde** contra PG 16 real sobre base desechable `apt_test_013` (creada y dropeada; `apt_erp` intacta): token `013.1`, instalación nueva `01→02→03` con `Anulado` (quinta fila del catálogo replicado) y tabla en control + 4 tenants (0 filas de historial), migración 004 (id por `max+1` del catálogo receptor) con transición `012.1→013.1` preservando datos/mapas, idempotencia (segunda ejecución sin cambios) y preflight que aborta ante estructura 013 parcial sin marcar versión; tenant en `012.1` deniega en cerrado y en `013.1` enruta. Suite completa con gated: **917 passed / 78 failed** — las 78 son las mismas rojas de ausencias previstas de T6–T9 (rutas/matriz/capacidades/servicio 013), idénticas con y sin `POSTGRES_TEST_URL` (verificado con stash de `config.py`: 78/78). El bump obligó a ajustar el gated de la 012 (plan §6): los tests de cadena 003 ahora materializan la forma 012.1 con `_degradar_a_012_1` y asientan `VERSION_MIGRACION_012`; el gated 013 corrigió el helper `_motor_sqlalchemy` (psycopg2 2.9+ no expone `password`) y el cableado del token (`abrir_sesion_tenant`, espejo de `dependencies.py`).

## Backend: matriz, servicios, endpoints y pruebas

- [x] **T6 — Matriz de permisos (44 → 49) y gating de capacidades de la 012.**
  - Archivos: `backend/app/core/permisos.py`, `backend/app/core/capacidades.py`.
  - Cinco filas **aditivas** en la sección «Feature 013» con los roles exactos del AC-17 (anulación: Solicitante+Administrador; rechazo: Bodeguero+Administrador; edición: Solicitante+Administrador; detalle e historial: los cuatro roles), sin modificar ninguna fila previa; en `MAPA_OPERACION_CAPACIDAD`, anulación y rechazo → `kanban`, edición/detalle/historial → `tickets` (sin capacidad nueva; conjunto cerrado de la 012 intacto).
  - **AC:** AC-16, AC-17.
  - **Hecho cuando:** las suites de transcripción de la matriz pasan con 49 operaciones y las 44 previas intactas (`git diff` de `permisos.py` solo añade), y el gating apagado devuelve 403 sin mutación en las cinco rutas nuevas. **[SQLite]**
    - *Hecho (18/Oct/2026):* `permisos.py` añade las 5 filas de la sección «Feature 013» (44 → 49, diff solo aditivo; roles exactos del AC-17 verificados por la transcripción no tautológica de `_soporte_ciclo_vida_013.OPERACIONES_013`) y `capacidades.py` asocia anulación/rechazo → `kanban`, edición/detalle/historial → `tickets`. Reconciliación de las suites de transcripción previas (patrón 011/012): `test_permisos.py`, `test_permisos_008.py` y `test_permisos_010.py` crecen a 49; `test_permisos_012.py` pasa de igualdad exacta a «conserva las 44 filas de la 012 idénticas» porque `MATRIZ_012` queda congelada en 44 como línea base de la 013 (la igualdad exacta a 49 la asume el módulo 013). **Pendiente hasta T9 (esperado):** `test_permisos_endpoints.py::test_inventario_de_rutas_igual_a_la_matriz_d3` sigue rojo porque el `app` aún publica 44 rutas frente a las 49 de la matriz — en T9 se publican las rutas y se reconcilia `MATRIZ_D3` a 49 (allí quedan verificables también el 403 de gating apagado en las cinco rutas reales, hoy 404 por ausencia de router). Suite tras T6: **849 passed / 78 failed / 68 skipped** (las 77 rojas 013 son las ausencias de T7–T9 más esta 1 previa acoplada a rutas; ninguna otra prueba previa quedó roja).

- [x] **T7 — Núcleo del ciclo de vida en `ticket_service`: terminales por nombre, historial de escritura, anulación y rechazo.**
  - Archivos: `backend/app/services/ticket_service.py` (sobre los tests rojos de T2).
  - `NOMBRE_ESTADO_ANULADO` y resolución de `Cerrado`/`Anulado` por nombre (`_resolver_estado_por_nombre`, casefold, menor id ante duplicados; sin terminalidad ordinal); `_registrar_transicion(...)` escrita en la misma transacción que todo cambio; fila de creación en `crear_ticket` (origen nulo, destino = estado inicial, actor = identidad) y de despacho en `despachar_ticket`; `crear_ticket` rechaza `estado_id` `Anulado` (409); `actualizar_estado_ticket` responde 409 con detalle que dirige a `/anulacion` o `/rechazo` si destino u origen es `Anulado`, conservando el orden 404→404→409 y la guarda de cierre reservado al despacho de la 005; `anular_ticket`/`rechazar_ticket` sobre el helper único `_cambiar_a_anulado` con orden 404 → 409 → 422 (motivo no vacío ≤ 500 validado en servicio) y escritura atómica ticket + historial; `fecha_cierre` nula y stock/movimientos intactos.
  - **AC:** AC-1, AC-2, AC-3, AC-4, AC-5, AC-6, AC-7, AC-9, AC-11.
  - **Hecho cuando:** pytest verifica 200 con fila de historial exacta y motivo literal; 409 sin efectos (ni en el ticket ni en el historial) desde `EnCurso`/`Cerrado`/`Anulado`; 409 literal de `PATCH /estado` hacia y desde `Anulado`; despacho de un `Anulado` → 409 de la 005 intacto; alta en `Anulado` → 409; y el orden 404→409→422 ante problemas simultáneos. **[SQLite]**
    - *Servicio completo, verificación HTTP parcial (18/Oct/2026), T7 sin cerrar:* implementado en `ticket_service.py` — `NOMBRE_ESTADO_ANULADO`; guards de `PATCH /estado` hacia/desde `Anulado` (409 que dirigen a `/anulacion` o `/rechazo`, tras los 404 y antes del 409 de flujo; la terminalidad ordinal de la 004 se conserva intacta, spec §8); `_registrar_transicion` en la MISMA transacción de creación (origen nulo), cambio de estado, despacho y anulación/rechazo (AC-11 verificado: fila caída ⇒ estado no cambia); `crear_ticket` rechaza alta en `Anulado` (409, D-11 — test nuevo `test_alta_en_anulado_responde_409_sin_ticket_d11`, único test que T2 no cubría); `anular_ticket`/`rechazar_ticket` sobre `_cambiar_a_anulado` (orden 404 → 409 —incl. catálogo sin `Anulado`— → 422 de motivo vacío/`>500` validado en servicio, motivo literal persistido; `fecha_cierre` nula, stock/movimientos intactos). **Verde con T7:** `test_patch_estado_no_lleva_a_anulado_y_dirige_a_la_operacion_ac_4` y el nuevo D-11; regresiones 004/005 (incl. `test_reentrar_en_cerrado_conserva_la_fecha_original` y `test_retroceso_desde_el_terminal_se_rechaza_con_409`) intactas. **Suite tras T7: 851 passed / 77 failed / 68 skipped** — las 76 rojas 013 restantes observan por HTTP lo que T7 ya escribe: 23 de `/anulacion` y `/rechazo` sin ruta (T9), 10 de historial sin `GET /historial` (T9), 7 de motivo (rutas T9 + `TicketMotivo` de T8), 17 de edición sin `PUT /tickets/{id}` ni `TicketEditar` (T8/T9), 23 de autorización/OpenAPI sin las 5 rutas (T9), 2 de KPI sin `dashboard_service` (T9), más la previa `test_inventario_de_rutas_igual_a_la_matriz_d3` (T9); el contrato de servicio correspondiente (200 con fila+motivo literal, 409 sin efectos, orden 404→409→422, catálogo sin `Anulado`, actor autenticado, atomicidad) fue verificado invocando el servicio directamente con 11 aserciones, todas en verde. **Reconciliación forzada (patrón T6):** la atribución de actor exige un `usuario` persistido (FK del historial), por lo que tres suites previas pasaron a autenticar con un usuario real en lugar de la sonda sintética `9999` (`test_ticket_sede_011.py`, `test_tickets_alcance.py`, `test_tickets_institucional.py`; solo fixtures, sin cambiar aserciones). **Hallazgo elevado al coordinador (plan §7):** la literal de spec D-4 («`Cerrado` y `Anulado` terminales por nombre») aplicada a `Cerrado` en cualquier catálogo regresaría la 004 (`test_reentrar_en_cerrado_conserva_la_fecha_original` exige `Cerrado → Archivado` = 200 en catálogo degenerado); se implementó el guard por nombre de `Anulado` (que elimina el único peligro real, `Cerrado → Anulado`) y se conservó la regla ordinal de la 004 como declara spec §8. **No se marca `[x]`:** el «Hecho cuando» exige verificación por pytest de la anulación/rechazo por HTTP, que queda en rojo hasta T8/T9.
    - *T7b (18/Oct/2026, enmienda de spec: D-4 literal + AC-26; resuelve el hallazgo elevado arriba):* la terminalidad pasa a resolverse **por nombre canónico en cualquier catálogo**. `actualizar_estado_ticket` añade el guard de **salida desde `Cerrado`** (409 cuyo detalle declara el cierre definitivo y que el despacho transaccional es el único camino a él) y **amplía** el guard de cierre reservado de la 005 a toda petición cuyo destino sea `Cerrado` (mismo literal `El cierre requiere despacho; use POST .../despacho`: imposibilita la reentrada en `Cerrado` y, con ella, el doble despacho); se **deroga** la cláusula ordinal "el último del catálogo no se sale" y se elimina el sellado de `fecha_cierre` en el cambio de estado (código muerto: sellan solo el alta y el despacho). Pruebas: derogado el test degenerado de la 004 `test_reentrar_en_cerrado_conserva_la_fecha_original`, sustituido por `test_salir_de_cerrado_responde_409_y_conserva_la_fecha_sellada` (misma cobertura viva: la fecha sellada no se borra ni se sobrescribe ante el 409); ajustado `test_el_sellado_no_distingue_mayusculas` al camino vigente (alta directa en `CERRADO`, casefold intacto) porque el `PATCH` ya no puede entrar en `Cerrado`; ajustado el smoke a `test_actualizar_estado_ticket_hacia_cerrado_responde_409` (antes `INGRESADO → CERRADO` = 200, hoy 409 con el literal de la 005 y sin mover el ticket — ambas correcciones documentadas en sus docstrings); y añadidos 4 tests **AC-26** en `test_ciclo_vida_flujo_013.py`, en verde: salida 409 desde `Cerrado` y desde `Anulado` en catálogos degenerados (con `Cerrado`/`Anulado` en medio), reentrada en `Cerrado` imposible desde estados contiguos y ticket despachado sin camino a un estado despachable (sin doble rebaja de stock). La ordinalidad de "avanzar/retroceder un paso entre contiguos" se conserva para los estados operativos. Suite tras T7b+T8: **855 passed / 77 failed / 68 skipped** (las 77 rojas son las mismas ausencias de T9; ninguna prueba previa nueva en rojo).
    - *Cerrado (18/Oct/2026) con T9:* la verificación HTTP que el "Hecho cuando" exigía quedó completa al publicar T9 las rutas del ciclo de vida: `test_ciclo_vida_flujo_013.py` y `test_ciclo_vida_motivo_013.py` verifican por interfaz HTTP el 200 con fila de historial exacta y motivo literal, el 409 sin efectos desde `EnCurso`/`Cerrado`/`Anulado`, los 409 literales de `PATCH /estado` hacia/desde `Anulado`, el despacho de un `Anulado` con el 409 de la 005 intacto, el alta en `Anulado` → 409 (D-11) y el orden 404 → 409 → 422 ante problemas simultáneos (AC-1…AC-7, AC-26); ninguna prueba previa quedó roja.

- [x] **T8 — Motivo, schemas y edición del ticket en `Pendiente` con reemplazo atómico.**
  - Archivos: `backend/app/schemas/ticket_schema.py`, `backend/app/services/ticket_service.py`.
  - `TicketMotivo` con `motivo: str` sin validación Pydantic de vacío/longitud (decisión 3 del plan: el servicio responde 422 y así el 422 no se adelanta al 404/409 del AC-7) y `TicketEditar` (asunto, descripción, prioridad_id, detalles; sin `usuario_id`); `editar_ticket` con orden 404 alcance → 409 fuera de `Pendiente` → validación total del payload (referencias 404, forma 422) → borra los detalles previos, inserta los nuevos y actualiza la cabecera en **una sola transacción**; estado, solicitante, sede e institución intactos.
  - **AC:** AC-8, AC-13, AC-14, AC-15, AC-16.
  - **Hecho cuando:** pytest cubre 200 con el conjunto de ítems reemplazado por completo; 409 sin modificar cabecera ni detalles fuera de `Pendiente`; payload con prioridad/producto inexistente, producto ajeno, cantidad no positiva o detalles vacíos → 404/422 sin escritura parcial; y 403/404 por rol. **[SQLite]**
    - *Hecho (18/Oct/2026):* `ticket_schema.py` añade `TicketMotivo` (`motivo: str` **sin** validación Pydantic de vacío/longitud —decisión 3—: el servicio responde 422 y el 422 no se adelanta al 404/409 del AC-7) y `TicketEditar` (asunto, descripción, `prioridad_id`, `detalles` con la misma forma que el alta —`min_length=1`, `gt=0`—; **sin** `usuario_id`, `estado_id`, sede ni institución; `model_config`/Pydantic v2, documentación OpenAPI). `ticket_service.editar_ticket` implementa el orden estricto **404** (ticket inexistente o fuera de alcance, idénticos) → **409** (fuera de `Pendiente`, resuelto por nombre canónico; fail-closed si el catálogo no contiene `Pendiente`) → **validación total del payload** (`_verificar_referencia` para la prioridad nombrando la referencia; `_verificar_productos` sobre la institución del ticket, 404 idéntico inexistente/ajeno) → **escritura atómica** (cabecera actualizada + borrado de los detalles previos + inserción de los nuevos en una sola transacción, `cantidad_entregada=0`). Estado, solicitante, sede e institución intactos; sin fila de historial (editar no muta estado). Verificado por invocación directa del servicio (9 tests, todas verdes: reemplazo íntegro con estado/solicitante/sede/institución intactos; 409 sin efectos en EnRevision/EnCurso/Cerrado/Anulado; 404 nombrando prioridad/producto sin escritura parcial; producto ajeno con detalle idéntico al inexistente; alcance 404 idéntico inexistente/ajeno con el dueño editando; contrato de ambos schemas). Los tests HTTP del módulo de edición siguen rojos **solo** por la ausencia de `PUT /tickets/{id}` (T9), igual que el resto de rojas 013.

- [x] **T9 — Endpoints del ciclo de vida, detalle, historial de lectura y KPI del dashboard.**
  - Archivos: `backend/app/api/v1/endpoints/tickets.py`, `backend/app/services/ticket_service.py`, `backend/app/schemas/ticket_schema.py`, `backend/app/services/dashboard_service.py`.
  - Cinco rutas nuevas (`POST /tickets/{id}/anulacion`, `POST /tickets/{id}/rechazo`, `PUT /tickets/{id}`, `GET /tickets/{id}`, `GET /tickets/{id}/historial`) con `response_model`, `status_code`, OpenAPI, `respuestas_de_autorizacion()` + `respuesta_recurso_oculto()` (+ `respuesta_conflicto()` donde aplique), `requiere_operacion` y `requiere_capacidad`; `HistorialTransicionRespuesta` y `TicketDetalleRespuesta` si `TicketRespuesta` no basta; alcance por rol con `leer_global_unico` (REPEATABLE READ) para el Superadmin; historial en orden determinista y sin variantes de escritura; descripción de `PATCH /estado` actualizada con los 409 de `Anulado`; `_contar_tickets_activos` pasa a excluir `nombre NOT IN ('Cerrado', 'Anulado')` por nombre exacto (AC-22).
  - **AC:** AC-10, AC-16, AC-17, AC-18, AC-19, AC-22.
  - **Hecho cuando:** pytest verifica los cuatro roles con su alcance vigente, 404 idéntico inexistente/ajeno sin filtrar existencia, Superadmin 403 en toda escritura y lectura global de detalle/historial, historial vacío y ordenado `fecha_transicion DESC, historial_transicion_id DESC`, anulados fuera del KPI con el resto intacto, y `/openapi.json` publica las cinco operaciones con 401/403/404/409/422 documentados. **[SQLite + PostgreSQL gated para el alcance global]**
    - *Hecho (18/Oct/2026):* rutas nuevas en `tickets.py` (`POST .../anulacion`, `POST .../rechazo`, `PUT /tickets/{id}`, `GET /tickets/{id}`, `GET /tickets/{id}/historial`) con `response_model`, `status_code`, OpenAPI, `requiere_operacion` + `requiere_capacidad` (kanban ×2, tickets ×3), `respuestas_de_autorizacion()` + ocultamiento + conflicto, y descripción de `PATCH /estado` reescrita con los 409 de terminales por nombre (conservando el literal del cierre reservado y la mención de `fecha_cierre` que exige la 004). Servicio: `obtener_ticket_detalle` (alcance por rol idéntico; Superadmin vía `global_service.leer_global_unico` REPEATABLE READ; DTO eager `detalles→producto→categoria` + cabecera contra `DetachedInstanceError`) y `obtener_historial_ticket` (orden `fecha_transicion DESC, historial_transicion_id DESC`, estados y actor resueltos). Schemas nuevos `TicketDetalleRespuesta` (extiende `TicketRespuesta` + `estado_nombre`, `prioridad_nombre`, `solicitante_id/nombre/apellido/correo`, `departamento_nombre`, `sede_nombre`) e `HistorialTransicionRespuesta` (7 campos tabulares + `estado_origen_nombre`/`estado_destino_nombre`/`usuario_nombre`/`usuario_apellido`): **contrato exacto** con los tipos TS `TicketDetalle`/`HistorialTransicion` de T10, que quedan poblados sin tocar el frontend (los opcionales de T10 ya no degradan). KPI: `_contar_tickets_activos` excluye `nombre NOT IN ('Cerrado', 'Anulado')` por nombre exacto (AC-22, semántica de la 009 conservada). Reconciliación del test previo (patrón T6): `MATRIZ_D3` de `test_permisos_endpoints.py` 44 → 49 con las cinco filas del AC-17, `datos_autorizacion` con `Anulado` en el catálogo y `ticket_ciclo_id` en `Pendiente`, `_ruta_concreta`/`_cuerpo` con los payloads del ciclo de vida y `REFERENCIAS_ESPERADAS` con los cinco DTOs. **Hallazgo reconciliado en el soporte de tests (contradicción interna de T2, spec AC-17 vs AC-18):** `test_operar_ticket_ajeno_responde_404_identico_ac_18[rechazo]` exigía un 404 de ocultamiento para el Solicitante, rol al que la matriz AC-17 (cerrada en T6) niega el rechazo con 403 —lo fija el propio módulo en `test_rol_sin_permiso_de_escritura_recibe_403_ac_17`—; el caso `rechazo` pasó a ejercerse con el Administrador de la otra institución (autorizado pero fuera de alcance), conservando el AC-18 íntegro (ajeno ≡ inexistente) sin tocar la matriz. Suite completa SQLite tras T9: **952 passed / 68 skipped / 0 failed** (gated PostgreSQL sin ejecutar aquí; T12 hará la ronda completa).

## Frontend

- [x] **T10 — Frontend: interfaces, servicio y vista de detalle del ticket.**
  - Archivos: `frontend/src/app/shared/interfaces/index.ts`, `frontend/src/app/features/tickets/services/ticket.service.ts`, `frontend/src/app/features/tickets/ticket-detalle.component.ts` (+ `.html`, `.spec.ts`), `frontend/src/app/features/tickets/tickets.routes.ts`, `frontend/src/app/core/auth/roles.ts`.
  - Tipos 1:1 con los schemas (`HistorialTransicion`, `TicketEditar`, `TicketDetalle`); en `TicketService`: `obtenerDetalleTicket`, `obtenerHistorial`, `anularTicket`, `rechazarTicket`, `editarTicket`; vista standalone nueva (skill `frontend-design`): cabecera (asunto, prioridad, solicitante y departamento, sede, fechas), ítems con cantidades solicitadas/entregadas y historial completo; barra de acciones por estado y rol (avanzar/retroceder vía `PATCH /estado`, editar solo en `Pendiente`, anular/rechazar con confirmación previa que exige motivo); errores 404/409/422 accesibles (`role="alert"`), anti doble envío y reconsulta tras cada mutación; ruta hija `tickets/:ticketId` con `loadComponent` perezoso; helpers de presentación `puedeAnularTicket`/`puedeRechazarTicket`/`puedeEditarTicket` (`ROLES_TICKETS` intacto: el Superadmin no navega `/tickets`, su lectura global es solo API). Signals + `computed()`, `inject()`, solo Tailwind, sin paquetes nuevos.
  - **AC:** AC-23, AC-24 (vista de detalle).
  - **Hecho cuando:** `ng test` con `CHROME_BIN` (Edge) verifica render por estado/rol, estados vacíos visibles y diferenciables, mensajes accesibles en 404/409/422, confirmación con motivo obligatorio y ausencia de doble envío; `ng build` queda limpio. **[ng test]**
    - *Hecho (18/Oct/2026):* `ng test` **330 SUCCESS / 0 failed** (27 specs nuevos de `ticket-detalle.component.spec.ts` + 4 de los helpers en `roles.spec.ts`; ningún spec previo quedó rojo, incluido el tablero `tickets.component.spec.ts`, que no se tocó) y `ng build` limpio con `ticket-detalle-component` como chunk lazy propio. Ruta hija `tickets/:ticketId` añadida con `loadComponent`; la ruta raíz del tablero queda intacta. **Nota de integración para T9:** los campos de presentación del contrato (`estado_nombre`, `prioridad_nombre`, `solicitante_*`, `departamento_nombre`, `sede_nombre` en `TicketDetalleRespuesta`; `estado_origen_nombre`/`estado_destino_nombre`/`usuario_nombre`/`usuario_apellido` en `HistorialTransicionRespuesta`) se declararon **opcionales** en los tipos porque los schemas se definen en T9; la vista degrada a catálogo y etiquetas `#id` si faltan, pero AC-23 exige el historial legible (actor y de→a), así que T9 debe poblarlos.

- [x] **T11 — Frontend: tablero Kanban a solo lectura con acción «Gestionar».**
  - Archivos: `frontend/src/app/features/tickets/tickets.component.ts` (+ `.html`, `.spec.ts`).
  - Eliminar los botones avanzar/retroceder y su lógica obsoleta (`puedeAvanzar`/`puedeRetroceder`/`estadoAnteriorId`/`estadoSiguienteId`, `errorMovimiento`); cada tarjeta ofrece **«Gestionar»** → navega al detalle; la columna `Anulado` surge del catálogo; conservar filtros y el modal de alta, filtrando `Anulado` de la elección de estado inicial (espejo de D-11; el backend ya responde 409); ajustar la aserción no-N+1 del tablero si el número de peticiones cambia. Deróganse los AC de UI de la 004 listados en la spec (D-14); el backend de `PATCH /estado` no se toca.
  - **AC:** AC-24.
  - **Hecho cuando:** `ng test` confirma el tablero sin controles de mutación, la acción «Gestionar» que abre el detalle, la columna `Anulado` con sus tarjetas y la alta sin `Anulado` como estado inicial; `ng build` limpio. **[ng test]**
    - *Hecho (18/Oct/2026):* el tablero pasa a solo lectura (D-14): se eliminaron los botones avanzar/retroceder y **toda** su lógica (`mover`/`moverSiguiente`/`moverAnterior`/`reconsultarTickets`/`liberar`, señales `enProceso` y `errorMovimiento`, `idEstadoEnCurso`, campos de mutación de `TarjetaKanban`, y `rolActual`/`puedeGestionarKanban` con su banner de «solo consulta» —ya no hay UI condicionada al rol en el tablero—); cada tarjeta ofrece un enlace **«Gestionar»** (`routerLink` `/tickets/{id}`, aria-label con el id) presente en **todas** las columnas, incluidas las terminales; la columna `Anulado` surge sola del catálogo (grid `md:grid-cols-5`) y el modal de alta itera `estadosAlta()` —nuevo `computed` que excluye `Anulado` por nombre canónico normalizado (D-11, espejo del backend que responde 409)—, con `estadoInicial()` sobre esa lista filtrada (catálogo degenerado con `anulado` primero y en minúsculas queda cubierto). Specs: fuera los de transiciones/rechazos/AC-16 del tablero (derogados por D-14) y los de capacidades por rol; dentro los de «Gestionar» (href + `navigateByUrl` al detalle, sin peticiones al navegar), ausencia de controles y de lógica residual en clase y tarjeta, columna `Anulado` con sus tarjetas, alta sin `Anulado` (lista, desplegable y exclusión por nombre) y aserción no-N+1 ajustada (2 peticiones al arranque; render, filtros y navegación añaden 0). **`ng test` 323 SUCCESS / 0 failed** (incluye los 27 specs del detalle de T10; 323 `it(` en `src` = 323 ejecutados, ninguno excluido) y **`ng build` limpio** con `tickets-component` (20.52 kB) y `ticket-detalle-component` como chunks lazy. El backend de `PATCH /estado` quedó intacto (`actualizarEstado` sigue en `TicketService`, usado por el detalle).

## Integración y cierre

- [x] **T12 — Integración: suites completas y contrato OpenAPI (49 operaciones).**
  - Archivos: `backend/tests/`, specs Angular; correcciones solo si aparecen defectos conforme a tareas previas.
  - Ejecutar `pytest` SQLite completo; suite gated con `POSTGRES_TEST_URL` (sin cerrarla por resultado SQLite); `npx ng test --watch=false --browsers=ChromeHeadless` con `$env:CHROME_BIN` apuntando a Edge; `ng build` de producción; inspeccionar `/openapi.json`: **49 operaciones** con las 44 previas intactas y las 5 nuevas aditivas.
  - **AC:** AC-17, AC-21, AC-25 (suites y contrato).
  - **Hecho cuando:** las suites quedan verdes —SQLite sin regresiones, gated sin skips en ejecución PostgreSQL, `ng test`/`ng build` limpios— y la matriz/OpenAPI muestran exactamente cinco operaciones nuevas sin modificación de las previas. **[SQLite + PostgreSQL gated + ng test]**
    - *Hecho (18/Oct/2026), sin defectos que corregir:* **SQLite** `pytest` **952 passed / 68 skipped / 0 failed** (baseline intacto). **Gated PostgreSQL 16** sobre base desechable `apt_test_013_full` (creada y dropeada; `apt_erp` intacta): **1020 passed / 0 skipped / 0 failed** —los 68 módulos gated corrieron, ninguno saltado por accidente— en 4:28 min. **`ng test`** (CHROME_BIN=Edge): **323 SUCCESS / 0 failed**; **`ng build`** limpio (19.66 s, initial 326.31 kB, lazy `ticket-detalle-component` 28.51 kB y `tickets-component` 20.52 kB). **`/openapi.json`** (TestClient): **exactamente 49 operaciones bajo `/api/v1/`** (51 totales con `GET /` y `GET /health`, hallazgo de T2) — las 5 nuevas (`POST .../anulacion`, `POST .../rechazo`, `PUT /tickets/{id}`, `GET /tickets/{id}`, `GET .../historial`) documentan 401/403/404 y las 3 escrituras además 409/422; las 44 previas intactas (las suites de transcripción de la matriz las fijan en verde y `git diff` de `permisos.py` es solo aditivo: +19 líneas). **Confirmación del lector global contra BD real (riesgo `DetachedInstanceError` de T7, previsto por T9):** verificación desechable por HTTP con TestClient e identidad Superadmin sobre base multi-tenant temporal — `GET /tickets/{id}` y `GET .../historial` responden **200** con los campos de presentación resueltos (`estado_nombre=Anulado`, solicitante, departamento, `categoria` eager; historial de 2 filas con origen/destino/actor/motivo) —**sin** 500 ni sesión desasociada: la construcción del DTO dentro de la sesión de cada tenant (T9) cierra el riesgo; no hubo ningún defecto que corregir en esta tarea.

- [x] **T13 — Recorrido funcional en 4200 con escritura real.**
  - Levantar backend y frontend dev contra PostgreSQL real (respaldo previo de `apt_erp`; migración a `013.1`); recorrer: alta → anulación con motivo → detalle con historial → edición en `Pendiente` → rechazo con motivo, más regresión del despacho transaccional de la 005 y los 404/409/422 esperados; documentar la evidencia (capturas/consultas en `evidencia/`).
  - **AC:** AC-25.
  - **Hecho cuando:** el recorrido confirma escritura real persistida en PostgreSQL (ticket anulado con `fecha_cierre` nula y su fila de historial, edición reflejada, despacho intacto) y cada AC-1…AC-24 queda asociado a evidencia concreta (test, consulta, OpenAPI o captura).
    - *Hecho (19/Oct/2026):* `evidencia/README.md` documenta el recorrido completo contra `apt_erp` real (respaldo `respaldos/apt_erp_pre_013.dump` previo; versión `013.1` y `Anulado` presentes al iniciar). **Escritura real verificada por SQL tras cada paso:** tickets **13** (alta 201 + anulación con motivo literal → `Anulado`, `fecha_cierre` NULL, stock/movimientos intactos), **14** (edición `PUT` con conjunto de ítems reemplazado íntegro —los previos borrados, cabecera nueva, estado/solicitante/sede intactos— y rechazo por Bodeguero → `Anulado`) y **15** (regresión 005: `PATCH` a `EnCurso`, cierre manual → **409** con el literal de la 005, despacho → `Cerrado` con `fecha_cierre` sellada, stock 35→32 y salida auditada id 22). Historial: **8 filas** exactas (creación con origen nulo, 1 por mutación, orden `DESC` comprobado por HTTP), sin filas inventadas en tickets legado. Rechazos verificados sin efectos: 409 desde `EnCurso`/`Cerrado`/`Anulado` y hacia/desde `Anulado` por nombre, 404 idéntico inexistente/ajeno, 422 motivo vacío, 409 alta en `Anulado`, 409 edición fuera de `Pendiente`, 403 Superadmin en toda escritura y 403 Solicitante en rechazo; Superadmin lee detalle/historial global 200; KPI excluye anulados (3 activos para el Solicitante contrastado con SQL). OpenAPI vivo: **49 operaciones** con las 5 nuevas (200/401/403/404 + 409/422 en escrituras). Frontend **4200**: `npm start` compiló (chunks lazy `ticket-detalle-component`/`tickets-component`) y sirvió el shell SPA en `/` y `/tickets` (200); dev server detenido al cerrar. Tokens Clerk reales por HTTP (cuentas documentadas en la evidencia; sin crear usuarios en Clerk). Mapeo **AC-1…AC-26 → evidencia** (tests + recorrido + OpenAPI) en la sección 5 de la evidencia.

- [x] **T14 — Rebuild y recorrido de humo en 8080.**
  - Ejecutar `docker compose -f docker-compose.yml build frontend` y luego `docker compose -f docker-compose.yml up -d frontend`; humo: tablero con columna `Anulado` y sin controles de transición, «Gestionar» que abre el detalle, historial y flujo básico respondiendo sin errores de consola/red.
  - **AC:** AC-25.
  - **Hecho cuando:** 8080 sirve el bundle reconstruido y el humo confirma detalle/tablero; no se atribuye evidencia a la imagen anterior (AGENTS §5/§8.6).
    - *Hecho (19/Oct/2026):* `evidencia/README.md` §8 documenta el humo. Build **sin errores** (`ng build` 55,55 s en el builder; re-ejecución de control exit 0 100 % en caché, mismo digest `sha256:1acf53e1…`) y `up -d frontend` con el contenedor **healthy**. 8080 sirve el bundle nuevo **`main-R6LIXDWJ.js`** (el anterior `main-6C2R7UG2.js` ahora **404**; CSS y todos los chunks con hash nuevo). Verificado por HTTP: shell SPA en `/` (200), `try_files` en `/tickets` y `/tickets/13` (200 con el mismo shell), mapa de rutas perezosas servido (`chunk-URBQGDLO.js` → `TicketsComponent` en `chunk-GGSHOG7T.js` y `TicketDetalleComponent` en `chunk-FYJSV5V5.js`), «Gestionar» presente en el chunk del tablero y «Historial de transiciones» en el del detalle, y API por el proxy de nginx: `GET /api/v1/tickets/13` 401 sin token y **200** con presentación poblada y `fecha_cierre: null` con token Clerk (flujo T13), `/historial` 200 con 2 filas ordenadas y `/tickets/` 200. OpenAPI: las **49 operaciones** con las 5 nuevas se verificaron en el mismo backend vivo que proxya 8080 (`:8000/openapi.json`), porque el documento **no es accesible desde 8080** (nginx solo proxya `/api/`; hallazgo, no defecto de la 013). Limitación declarada: sin navegador en la sesión, el humo fue por HTTP + inspección del bundle (sin capturas del render).

- [x] **T15 — Evidencia por AC, memoria, roadmap y grep de coherencia (§8.7) con «15 entidades».**
  - Archivos: `spec.md` (solo evidencia bajo cada AC-1…AC-25 de §7), `MEMORY.md`, `roadmap.md` (solo si procede tras verificación); `AGENTS.md` y `.agents/skills/` mediante grep de comprobación (la edición de `AGENTS.md` §7 la hace el coordinador/implementer, no el planner — plan §4).
  - Registrar en `spec.md` la evidencia observada de cada AC (archivos/métodos de test reales, contrato OpenAPI, recorrido 4200/8080 con su captura); actualizar `MEMORY.md` (estado, decisiones clave 013 y errores evitables, breve); ejecutar el grep de coherencia de AGENTS §8.7 sobre `AGENTS.md`, `MEMORY.md` y `.agents/skills/` **incluida la actualización del conteo de `AGENTS.md` §7 a «15 entidades de dominio»** (plan §4); marcar `roadmap.md` `[x]` solo tras cumplir AGENTS §8.5–§8.7.
  - **AC:** AC-25.
  - **Hecho cuando:** cada AC tiene evidencia verificada, `MEMORY.md` queda breve y actualizado, el grep no deja rutas ni afirmaciones obsoletas sin reportar (con el conteo «15 entidades» corregido en `AGENTS.md` §7), y el roadmap se marca `[x]` únicamente con todas las casillas de este `tasks.md` —incluidas las de cierre— en `[x]`.
    - *Hecho (19/Oct/2026):* `spec.md` registra evidencia real bajo cada AC-1…AC-26 (tests verificados por grep en `backend/tests/funcional/integracion/test_ciclo_vida_*_013.py` y `test_ciclo_vida_ticket_postgres_013.py`, specs de `frontend/src/app/features/tickets/*.spec.ts`, OpenAPI y secciones del recorrido de `evidencia/README.md`), con los 26 AC marcados y la nota de cierre; Estado → «aprobada y cerrada (19/Oct/2026)» con las dos enmiendas. `AGENTS.md` §7 y las skills `sdd-workflow`/`fastapi-pydantic-v2` actualizadas a **«15 de dominio + `departamento_encargado`»** (justificación en `stack.md` §2, sección 013); grep de coherencia §8.7 sin rutas ni afirmaciones obsoletas pendientes. `MEMORY.md` reescrito (013 cerrada, ~50 líneas) y `roadmap.md` con la fila 013 en `[x]`.

## Enmienda post-cierre (05/Nov/2026): alta fija en `Pendiente` y prioridad `Media`

- [x] **T16 — Backend: el alta exige `Pendiente` (409 en cualquier otro estado).**
  - `crear_ticket` resuelve `Pendiente` por nombre canónico (`NOMBRE_ESTADO_PENDIENTE`) y exige
    ese id; 409 si el `estado_id` no es `Pendiente` o si el catálogo no lo contiene, antes de
    escribir. Retirar el sellado de `Cerrado` y la rama específica de `Anulado`. Actualizar la
    descripción OpenAPI de `POST /tickets`.
  - Tests: nuevo `test_ciclo_vida_alta_inicial_013.py` (409 en EnRevision/EnCurso/Cerrado/Anulado
    y en id ajeno, 201 con Pendiente y `fecha_cierre` nula, 409 con catálogo sin Pendiente, 422
    sin `estado_id`); ajustar `conftest.datos_base` a `Pendiente`/`Cerrado`,
    `test_modal_ticket.py` (orden), `test_tablero_kanban.py`, `test_ciclo_vida_flujo_013.py` y
    `test_ticket_sede_011.py` (sembrar por ORM o transicionar).
  - **Hecho cuando:** `pytest` completo en verde y `/openapi.json` documenta el 409.
  - **AC:** AC-27.
    - *Hecho (05/Nov/2026):* `ticket_service.crear_ticket` resuelve `Pendiente` por nombre canónico y responde **409** si el `estado_id` no es ese (o si el catálogo no lo contiene), antes del primer `add()`; retirado el sellado de `fecha_cierre` y la rama de `Anulado`. `test_ciclo_vida_alta_inicial_013.py` **9/9**; suite completa SQLite **1459 passed / 83 skipped / 0 failed** y gated PostgreSQL 16 **1542 passed / 0 skipped / 0 failed**. `/openapi.json` (61 operaciones) documenta el 409 en la descripción del `POST /tickets/` y en `TicketCrear.estado_id`.
- [x] **T17 — Frontend: estado inicial fijo en `Pendiente` y prioridad `Media` predeterminada.**
  - Modal: campo de solo lectura para el estado (sin `<select>`, sin texto «Editable»); prioridad
    editable con `Media` preseleccionada; `aplicarValoresPorDefecto()` tras catálogos y tras
    alta; specs actualizadas y nuevas.
  - **Hecho cuando:** `ng test` y `ng build` limpios.
  - **AC:** AC-27.
    - *Hecho (05/Nov/2026):* modal con estado de solo lectura (`Pendiente` + etiqueta «Fijo», sin `<select>` ni el texto «Editable»), prioridad `Media` preseleccionada y cambiable, y `aplicarValoresPorDefecto()` al cargar catálogos y tras cada alta; `estadoInicial()`/`prioridadInicial()` por nombre canónico con bloqueo fail-closed si falta `Pendiente`. `tickets.component.spec.ts` **69/69**, `ng test` **524 SUCCESS**, `ng build` limpio.
- [x] **T18 — Verificación y cierre de la enmienda.**
  - `pytest`, `ng test` (Edge headless), `ng build`, recorrido 4200 (modal con Pendiente fijo y
    Media, alta real si aplica) y humo 8080 reconstruido; evidencia bajo AC-27 y `MEMORY.md`.
  - **AC:** AC-25, AC-27.
    - *Hecho (05/Nov/2026):* `evidencia/README.md` §9 registra las cuatro verificaciones: suites **1459/83/0** (SQLite) y **1542/0/0** (gated PG16), `ng test` **524** y `ng build` limpio (`main-BX5UQPQ3.js`); recorrido 4200 con alta real **#11** en la columna `Pendiente` y reset del modal a `Media`/`Pendiente`; humo 8080 con la imagen reconstruida sirviendo el mismo bundle, estado fijo sin selector y `Media` habilitada. `MEMORY.md`, `stack.md` y `roadmap.md` actualizados; grep de coherencia sin afirmaciones obsoletas sobre `estados[0]`.

## Ampliación 25/Nov/2026 — flujo de aprobación, etiqueta de proceso y confirmación de entrega

> Tareas de la §9 aprobada (AC-28…AC-49). Ejecutar en orden, una por llamada de @implementer, con
> pruebas primero. Sin DDL, sin `stack.md`, sin tocar `roadmap.md`; `MEMORY.md` lo actualiza el
> coordinador al cierre. Marcas: **[SQLite]**, **[PostgreSQL gated]**, **[ng test]**, **[build]**.

- [x] **T19 — Backend: DTOs del read model y derivación pura de la etiqueta.**
  - Archivos: `backend/app/schemas/ticket_schema.py`, `backend/app/services/ticket_proceso.py`
    (nuevo), `backend/tests/funcional/unitarios/test_ticket_proceso_013.py` (nuevo).
  - Prueba primero: etiquetas de los cinco estados, `Cerrado` con/sin confirmación, `EnCurso` con
    OC `Recibida`/`Facturada`/`Emitida`, `stock_disponible`, «Por comprar», estado desconocido;
    frases cortas; rango de OC; campos de `TicketRespuesta`/`TicketDetalleRespuesta`/
    `GestorProcesoRespuesta`.
  - Implementación: `GestorProcesoRespuesta` y campos aditivos; `ticket_proceso.py` con constantes,
    `rango_estado_orden` y `derivar_etiqueta`; sin tocar `compra_service`.
  - **AC:** AC-37, AC-38, AC-39 (esquema).
  - **Depende de:** —
  - **Hecho cuando:** los unitarios pasan y el contrato de los DTO declara exactamente los campos
    de §9.8 sin DDL. **[SQLite]**

- [x] **T20 — Backend: read model por lote en listado y detalle.**
  - Archivos: `backend/app/services/ticket_service.py`,
    `backend/tests/funcional/integracion/test_ticket_proceso_013.py` (nuevo),
    `backend/tests/funcional/integracion/test_tablero_kanban.py` (conteo de consultas).
  - Prueba primero: listado y detalle con etiqueta/frase, `estado_orden_cobertura`,
    `stock_disponible`, `entrega_confirmada`, gestores; etiqueta coherente entre listado y detalle;
    conteo de consultas fijo con 1 vs N tickets (patrón `before_cursor_execute`).
  - Implementación: `_cargar_proceso_tickets` con una simulación por sede, una consulta de OC, una
    de confirmaciones y una de gestores; `listar_tickets` devuelve `List[TicketRespuesta]`;
    `obtener_ticket_detalle` completa la base y la fecha/actor de la confirmación.
  - **AC:** AC-37, AC-38, AC-39, AC-40, AC-41 (datos).
  - **Depende de:** T19.
  - **Hecho cuando:** los tests de campos y el no-N+1 pasan; el detalle conserva
    `asignaciones`/`cadena_productos`. **[SQLite]**
    - *Hecho (25/Nov/2026):* `ticket_service` gana `_ProcesoTicket` (read model inmutable),
      `_cargar_proceso_tickets` (una simulación de la 020 por `sede_id` distinta, una consulta de
      `orden_compra_ticket ⋈ orden_compra` con `cantidad_asignada > 0` y rango `Recibida > Facturada
      > Emitida`, una de confirmaciones `Cerrado → Cerrado` con el motivo canónico —`Cerrado`
      resuelto por nombre, menor id— y una de gestores `historial ⋈ usuario ⋈ rol`, último por
      `fecha_transicion DESC, historial_transicion_id DESC` con el rol vigente), `_aplicar_proceso` y
      `_respuesta_ticket_con_proceso` (listo para el 200 de T21/T22). `listar_tickets` devuelve
      `List[TicketRespuesta]` (estado eager para la etiqueta; alcance y filtro intactos) y
      `obtener_ticket_detalle` deriva `estado_orden_cobertura` de sus `asignaciones` ya cargadas
      (sin consulta extra), completa la confirmación y conserva `stock_disponible`/`asignaciones`/
      `cadena_productos`. Nuevo `test_ticket_proceso_013.py`: **22/22** (AC-37…AC-40, stock por
      sede, sin sede, coherencia listado↔detalle y no-N+1 con **15** consultas constantes con 1 y 3
      pedidos `EnCurso`). `test_tablero_kanban.py` sube el tope del no-N+1 de **7 a 12** (cinco
      consultas fijas del read model; la igualdad 1 vs 3 se conserva). Reconciliación mínima fuera
      del listado previsto: `test_ciclo_vida_historial_013.py::test_si_la_fila_no_puede_registrarse_
      el_estado_no_cambia_ac_11` dropea `historial_transicion_ticket` a propósito y ya no puede usar
      `GET /tickets/` como canal de observación (el read model consulta esa tabla); pasa a leer el
      `estado_id` por ORM, conservando la intención AC-11. `test_ciclo_vida_operativas_servicio_014`
      **no** requirió cambios: `TicketRespuesta.detalles[].producto.categoria` conserva el acceso que
      usaba. Suite completa SQLite **1908 passed / 109 skipped** (baseline T19 1886 + 22 nuevos).
      Sin cambios de endpoint (`response_model` ya era `List[TicketRespuesta]`), permisos, capacidades,
      DDL ni frontend; `ng test` no se ejecuta.

- [x] **T21 — Backend: aprobación Admin-only, historial y rol del PATCH.**
  - Archivos: `backend/app/services/ticket_service.py`, `backend/app/core/permisos.py`,
    `backend/app/core/capacidades.py`, `backend/app/api/v1/endpoints/tickets.py`,
    `backend/tests/funcional/integracion/test_ciclo_vida_aprobacion_013.py` (nuevo).
  - Prueba primero: 200 desde `Pendiente`/`EnRevision` siempre a `EnCurso`; una fila
    `origen → EnCurso` con `motivo` `Aprobación del pedido`, actor y `orden_compra_id` nulo;
    atomicidad; 409 ya/terminal/catálogo; 404; 403 rol/capacidad; `PATCH` con Bodeguero 403 y con
    Administrador 200/409 de legado.
  - Implementación: `aprobar_ticket` con `FOR UPDATE`; matriz `POST /aprobacion` `{Administrador}`
    y `PATCH /estado` `{Administrador}`; capacidad `kanban`; endpoint y descripciones OpenAPI;
    `_respuesta_ticket_con_proceso` para el 200.
  - **AC:** AC-28, AC-29, AC-30, AC-31, AC-32 (Aprobar), AC-36, AC-45, AC-46, AC-49.
  - **Depende de:** T19, T20.
  - **Hecho cuando:** la aprobación y el `PATCH` se verifican por HTTP con sus roles, códigos y una
    sola fila; la matriz queda en 74 (75 al cerrar T22). **[SQLite]**

- [x] **T22 — Backend: confirmación de entrega.**
  - Archivos: `backend/app/services/ticket_service.py`, `backend/app/core/permisos.py`,
    `backend/app/core/capacidades.py`, `backend/app/api/v1/endpoints/tickets.py`,
    `backend/tests/funcional/integracion/test_ciclo_vida_confirmacion_013.py` (nuevo).
  - Prueba primero: 200 dueño; fila `Cerrado → Cerrado` con motivo, actor y `orden_compra_id`
    nulo; `entrega_confirmada`/etiqueta `Entregado`; sin estado/stock/`fecha_cierre`; 404 ajeno;
    403 Administrador/Bodeguero/Superadmin; 409 no `Cerrado` y ya confirmado; alta administrativa
    sin confirmación (403 del dueño sin rol Solicitante); capacidad `tickets`.
  - Implementación: `confirmar_entrega` con `FOR UPDATE` y detección por motivo; matriz
    `POST /confirmacion-entrega` `{Solicitante}`; capacidad `tickets`; endpoint y OpenAPI;
    `_respuesta_ticket_con_proceso` con `entrega_confirmada = true`.
  - **AC:** AC-42, AC-43, AC-44 (segunda operación).
  - **Depende de:** T21.
  - **Hecho cuando:** la confirmación se verifica por HTTP, la matriz queda en 75 y la fila
    persiste sin DDL. **[SQLite]**

- [x] **T23 — Backend gated PostgreSQL: concurrencia y filas de historial.**
  - Archivos:
    `backend/tests/funcional/sistema/test_ciclo_vida_aprobacion_confirmacion_postgres_013.py`
    (nuevo).
  - Prueba primero (gated, `skip` sin `POSTGRES_TEST_URL`): dos sesiones sobre la misma fila →
    aprobación `(200, 409)` con una fila; confirmación `(200, 409)` con una fila; lectura
    persistida del actor, fecha, motivo y `orden_compra_id NULL`; `fecha_cierre`/stock intactos;
    sin DDL.
  - Implementación: solo si la concurrencia revela un defecto en T21/T22; no se añaden bloqueos
    fuera del patrón de la 005.
  - **AC:** AC-30, AC-42, AC-43 (concurrencia).
  - **Depende de:** T21, T22.
  - **Hecho cuando:** el módulo gated pasa contra PostgreSQL 16 sobre base desechable y no toca
    `apt_erp`. **[PostgreSQL gated]**

- [x] **T24 — Backend: contrato/OpenAPI y recuentos 75/77.**
  - Archivos: `backend/tests/funcional/integracion/test_permisos_endpoints.py`,
    `test_cobertura_021.py`, `test_ciclo_vida_autorizacion_013.py`,
    `test_ciclo_vida_flujo_013.py`, `test_despacho_transaccional.py`, los tests de
    matriz/capacidades de la 012 (grep) y `backend/app/api/v1/endpoints/tickets.py`
    (descripciones), según el grep.
  - Prueba primero: matriz 75; `/openapi.json` 75 v1/77 entradas; `PATCH` solo Administrador;
    aprobación/confirmación con 401/403/404/409; las 73 previas con roles salvo el `PATCH`; los
    actores Bodeguero del `PATCH` pasan a Administrador o 403.
  - Implementación: reconciliación de aserciones absolutas y descripciones; sin cambios de
    comportamiento fuera de T21/T22.
  - **AC:** AC-44, AC-45, AC-49.
  - **Depende de:** T21, T22.
  - **Hecho cuando:** el inventario rutas↔matriz y el OpenAPI pasan con 75/77 y el `PATCH` con
    `{Administrador}`. **[SQLite]**

- [x] **T25 — Frontend: interfaces, servicio y helpers de roles.**
  - Archivos: `frontend/src/app/shared/interfaces/index.ts`,
    `frontend/src/app/features/tickets/services/ticket.service.ts`,
    `frontend/src/app/features/tickets/ticket.service.spec.ts` (nuevo),
    `frontend/src/app/core/auth/roles.ts`, `frontend/src/app/core/auth/roles.spec.ts`.
  - Prueba primero: URL/verbo/payload de `aprobarTicket` (POST sin cuerpo), `registrarRetiro`
    (POST `{usuario_id}`, entonces con Administrador/Bodeguero) y `confirmarEntrega` (POST sin
    cuerpo); ausencia de `actualizarEstado`;
    helpers `puedeAprobarTicket` (Administrador), `puedeRegistrarRetiro`
    (Administrador/Bodeguero) y `puedeConfirmarEntrega` (Solicitante).
  - Implementación: tipos `GestorProceso` y campos aditivos opcionales en `Ticket`/`TicketDetalle`;
    métodos del servicio; helpers; retirar `puedeOperarTickets` si queda sin consumidor.
  - **AC:** AC-32, AC-39, AC-42, AC-43, AC-45, AC-49.
  - **Depende de:** T19, T21, T22.
  - **Hecho cuando:** `ticket.service.spec.ts` y `roles.spec.ts` pasan; el proyecto compila.
    **[ng test]**

- [x] **T26 — Frontend: detalle con acciones semánticas y read model.**
  - Archivos: `frontend/src/app/features/tickets/ticket-detalle.component.ts` (+ `.html`,
    `.spec.ts`).
  - Prueba primero: acciones por estado/rol (Aprobar solo Administrador; Rechazar/Anular/Editar
    según estado y dueño; Despachar solo `EnCurso` con `stock_disponible`; Confirmar entrega solo
    dueño y `Cerrado` sin confirmar); no Avanzar/Retroceder; no `PATCH`; diálogo discriminado con
    motivo solo para anular/rechazo; 409 en `role="alert"`; sin doble envío; reconsulta;
    etiqueta/frase/responsables/línea de entrega.
  - Implementación: `acciones` y métodos `aprobar`/`solicitarRetiro`/`confirmarEntrega`; unión
    de `confirmando`; retirar `idEstadoSiguiente`/`idEstadoAnterior`/`transicion`; mostrar
    `etiqueta_proceso`, `explicacion_proceso`, `gestionado_por_*` y
    `entrega_confirmada_en`/`_por_*`; conservar el badge de stock y los diálogos de anular/rechazo.
  - **AC:** AC-32, AC-33, AC-34, AC-37…AC-40, AC-42, AC-43, AC-48.
  - **Depende de:** T25.
  - **Hecho cuando:** los specs del detalle pasan y `ng build` compila el componente. **[ng test]**

- [x] **T27 — Frontend: tablero con «Terminados», etiqueta y responsables.**
  - Archivos: `frontend/src/app/features/tickets/tickets.component.ts` (+ `.html`, `.spec.ts`).
  - Prueba primero: 4 columnas (`Pendiente`, `EnRevision` heredado, `EnCurso`, «Terminados»);
    `Cerrado`+`Anulado` en «Terminados» con contador sumado; sin columna `Anulado`; tarjeta con
    etiqueta, frase accesible y dos responsables (o «—»/«Sin gestión registrada»); tarjeta-enlace;
    `aria-label` con estado canónico; sin controles; no-N+1 (2 peticiones).
  - Implementación: `columnas` agrupa por `estado_ids`; `TarjetaKanban` con
    `etiquetaProceso`/`explicacionProceso`/`gestores`/`estadoCanonico`; grid de 4;
    `resolverTarjeta` resuelve el estado canónico del catálogo; `estadosAlta` sigue excluyendo
    `Anulado`.
  - **AC:** AC-37, AC-38, AC-40, AC-41, AC-47.
  - **Depende de:** T25.
  - **Hecho cuando:** los specs del tablero pasan y `ng build` compila. **[ng test]**

- [x] **T28 — Backend: e2e del flujo y regresión de suites.**
  - Archivos: `backend/tests/funcional/e2e/test_flujo_aprobacion_entrega_013.py` (nuevo) y los
    módulos reconciliados de T24/T21.
  - Prueba primero: alta → aprobar (etiqueta) → Compras/021 si hay necesidad → despachar →
    confirmar; 403/404/409; `PATCH` de legado 403 para Bodeguero y 200/409 para Administrador;
    ticket de Admin/Bodeguero sin confirmación; caso #10.
  - Implementación: solo correcciones si el e2e revela un defecto conforme a T19–T24; no se amplía
    la spec.
  - **AC:** AC-28…AC-49 (integración).
  - **Depende de:** T21, T22, T24.
  - **Hecho cuando:** el e2e y la suite SQLite completa pasan sin regresiones. **[SQLite]**

- [x] **T29 — Frontend: suite completa y build.**
  - Archivos: specs de `tickets`, `ticket-detalle`, `roles` y `ticket.service`; correcciones solo
    si el recorrido revela un defecto conforme a T25–T27.
  - `npx ng test --watch=false --browsers=ChromeHeadless` con `$env:CHROME_BIN` a Edge; `ng build`
    de producción.
  - **AC:** AC-32…AC-43, AC-48.
  - **Depende de:** T26, T27.
  - **Hecho cuando:** `ng test` y `ng build` quedan limpios y ningún spec previo queda rojo.
    **[ng test + build]**

- [x] **T30 — Cierre: suites, contrato, 4200/8080, evidencia y grep.**
  - Archivos: `spec.md` (evidencia bajo AC-28…AC-49), `evidencia/` (capturas/consultas);
    `MEMORY.md` lo actualiza el coordinador; `AGENTS.md`/skills solo si el grep de coherencia lo
    exige (coordinador). `roadmap.md` no se toca.
  - Ejecutar `pytest` SQLite completo, gated PG (`POSTGRES_TEST_URL`), `ng test`, `ng build`,
    inspeccionar `/openapi.json` (75 v1/77), recorrer 4200 con escritura real (aprobar, despachar,
    confirmar, tablero, detalle, caso #10) y 8080 tras `docker compose build frontend` +
    `up -d frontend`; grep de coherencia sobre `AGENTS.md`, `MEMORY.md` y `.agents/skills/`
    (PATCH/roles/etiquetas/columnas/recuentos).
  - **AC:** AC-28…AC-49 y «Cierre de la enmienda».
  - **Depende de:** T23, T28, T29.
  - **Hecho cuando:** todas las suites y el build están en verde, 4200/8080 verificados, cada AC
    - *Hecho (25/Nov/2026):* cierre verificado. **Suites:** SQLite **1973 passed / 112 skipped / 0 failed** (438,65 s); gated PostgreSQL 16 **2082 passed / 3 skipped / 0 failed** (1080,12 s) con el módulo de concurrencia de T23 **3/3**; `ng test` **634 SUCCESS**; `ng build` limpio (`main-JE7KG3Z2.js`, initial 339,74 kB). **OpenAPI:** **77** operaciones (75 v1 + `/` y `/health`) con aprobación `Administrador`/`kanban`, confirmación `Solicitante`/`tickets`, `PATCH` solo `Administrador` y despacho/rechazo `Administrador, Bodeguero`. **4200 con escritura real y los dos caminos:** #11 con stock (Solicitante crea → Administrador aprueba «En confirmación de stock local» → Bodeguero despacha → Solicitante confirma) y #12 sin stock (aprueba «Por comprar» → aparece en Compras con necesidad → OC-2026-000002 emitida y facturada → recepción del Bodeguero → «En confirmación de stock local» → despacho → confirmación del Solicitante); tablero de 4 columnas con «Terminados», caso #10 fuera de Compras, `PATCH` 403 Bodeguero y 200/409 Administrador, 17 capturas. **SQL:** stock 64→61 y 0→23→20, `SALIDA` ids 6 y 8, `ENTRADA` id 7, historial exacto `Pendiente → EnCurso → Cerrado → Cerrado` con motivos canónicos (ids 7-15). **8080:** imagen reconstruida, `main-JE7KG3Z2.js` servido, tablero y detalle nuevos, API por proxy 200/401; captura. **Grep §8.7:** sin referencias a PATCH/Avanzar/Retroceder/Anulado/«En espera de despacho»/«En ordenar compra» ni recuentos 75/77 obsoletos en `AGENTS.md`, `MEMORY.md` ni `.agents/skills/`; corregido el JSDoc de `ROLES_OPERATIVOS_TICKETS` que hablaba de avanzar/retroceder. Evidencia en `evidencia/README.md` §10 y AC-28…AC-49 con su evidencia en `spec.md`. **Hallazgo menor para el coordinador (resuelto en T31):** la tarjeta del pedido recién creado muestra el nombre canónico como etiqueta hasta la siguiente recarga (el tablero inserta el `201`, que no trae el read model).
    con evidencia y el grep sin afirmaciones obsoletas; `MEMORY.md` actualizado por el coordinador.
    **[SQLite + PostgreSQL gated + ng test + build + puertos]**

- [x] **T31 — Corrección post-cierre: read model en el `201` del alta.**
  - Archivos: `backend/app/services/ticket_service.py` (`crear_ticket`),
    `backend/app/api/v1/endpoints/tickets.py` (solo descripción OpenAPI),
    `backend/tests/funcional/integracion/test_ticket_proceso_013.py`,
    `frontend/src/app/features/tickets/tickets.component.spec.ts`; `spec.md`,
    `evidencia/README.md`, `MEMORY.md` y `roadmap.md` (cierre).
  - Prueba primero: `POST /tickets/` → 201 con `etiqueta_proceso` «En aprobación»,
    explicación no vacía, `stock_disponible=false`, `entrega_confirmada=false`,
    `estado_orden_cobertura=None`, gestores coherentes con la fila de creación y
    el estado persistido en `Pendiente`; spec del tablero que, tras el alta,
    muestra «En aprobación» y no el nombre canónico con el `201` corregido.
  - Implementación: `crear_ticket` devuelve `TicketRespuesta` construido con
    `_respuesta_ticket_con_proceso` (sin duplicar la derivación de la etiqueta).
    Sin DDL, sin permisos, sin cambios en el alta (`Pendiente`, AC-27), en el
    modal ni en las mutaciones.
  - **AC:** AC-39, AC-41.
  - **Hecho cuando:** el test de integración y el spec pasan, las suites siguen
    verdes, `ng build` queda limpio y `/openapi.json` conserva 75 v1/77.
    **[SQLite + ng test + build]**
    - *Hecho (25/Nov/2026):* `crear_ticket` devuelve `TicketRespuesta` con el
      read model ya poblado (`etiqueta_proceso`, `explicacion_proceso`,
      `estado_orden_cobertura`, `stock_disponible`, `entrega_confirmada` y los
      dos gestores), calculado con `_respuesta_ticket_con_proceso`; el alta
      sigue naciendo en `Pendiente` (AC-27) y no cambian el modal ni las
      mutaciones. `test_ac_39_el_201_del_alta_publica_el_read_model` y
      `test_ac_39_el_201_del_alta_de_un_solicitante_no_registra_gestores`
      (nuevos, **24/24** en el módulo) verifican el 201 completo, la fila de
      creación única, el estado persistido, los gestores según el rol del creador
      y la coincidencia con el listado; el spec del
      tablero `la tarjeta del pedido recién creado muestra «En aprobación»
      (T31)` cubre el 201 con read model. **Frontend de producción sin
      cambios:** `resolverTarjeta` ya usa `etiqueta_proceso` y solo cae al
      nombre canónico si viene vacía. Suites: SQLite **1975 passed / 112
      skipped / 0 failed**; `ng test` **639 SUCCESS** (el spec nuevo suma 1; el
      árbol ya contaba 638, por specs posteriores al recuento 634 de T30);
      `ng build` limpio (`main-GULMVWMA.js`); `/openapi.json` vivo **75 v1/77**
      con la descripción del `POST` mencionando el read model. Base QA
      reseteada después del cierre (`down -v` + `up -d`), verificada en §10.9
      de la evidencia.

## Enmienda 26/Nov/2026 — catálogo de tres estados y retiro

> Tareas de la §10 aprobada (AC-50…AC-68). Ejecutar en orden, una por llamada de @implementer, con
> pruebas primero. Sin DDL ni migración: token `026.0`, 26/23 tablas y 21 entidades. `stack.md` se
> actualiza en T43 con el texto de la §10.7; las notas de 005/007/004/018 se redactan en T43.
> `roadmap.md` no se toca (no hay feature nueva). `MEMORY.md`/`AGENTS.md` los sincroniza el
> coordinador al cerrar. Marcas: **[SQLite]**, **[PostgreSQL gated]**, **[ng test]**, **[build]**,
> **[docs]**.

- [x] **T32 — Pruebas rojas TDD de catálogo, flujo, retiro, anulación y confirmación.**
  - Archivos: `backend/tests/funcional/integracion/test_catalogo_estados_013.py` (nuevo),
    `test_retiro_transaccional_013.py` (nuevo/renombrado), `test_retiro_sede_013.py` (nuevo),
    `test_anulacion_retiro_013.py` (nuevo), `test_confirmacion_anulacion_013.py` (nuevo),
    `test_patch_estado_retiro_013.py` (nuevo),
    `backend/tests/no_funcional/seguridad/test_permisos_retiro_013.py` (nuevo), los fixtures de
    tickets y los módulos que hoy usan
    `Pendiente`; `frontend/src/app/features/tickets/tickets.component.spec.ts`,
    `ticket-detalle.component.spec.ts`, `roles.spec.ts` y `ticket.service.spec.ts`.
  - Prueba primero: dejar **rojo** el contrato completo — el contrato de `_ESTADOS_TICKET_TENANT`
    (4 filas con `Anulado`) y el esqueleto gated de la semilla (se completa en T33); alta,
    aprobación, edición y anulación/rechazo solo desde `EnRevision`; retiro con ruta `/retiro`,
    solo Bodeguero, 404/409 de sede, observación literal y ACID; anulación del retiro con
    `ENTRADA`, reset, `fecha_cierre` nula y 409 si confirmado; confirmación 200 y su fila
    canónica; matriz 75 con `/retiro`; tablero de 3 columnas y copy «Registrar retiro»/«Retirado».
    Ninguna implementación de producción en esta tarea; solo pruebas, fixtures y las marcas de
    reconciliación.
  - Implementación: ninguna; si un fixture necesita el catálogo nuevo, se prepara en el test, no
    en `backend/app` ni en `database/`.
  - **AC:** AC-50…AC-68 (cobertura roja; cada AC se completa en su tarea).
  - **Depende de:** —
  - **Hecho cuando:** la suite nueva existe, compila y falla por contrato (no por imports ni
    fixtures rotos), y las pruebas que hoy pasan con `Pendiente` quedan identificadas para su
    tarea. **[SQLite + ng test]**
  - **Nota de fase (T32 ejecutada el 26/Nov/2026).** Fase **roja**: no se tocó producción
    (`backend/app/`, `database/`, `frontend/src/app/**` salvo `.spec.ts`). La suite nueva
    compila y toda roja es por contrato (ruta/símbolo/comportamiento ausente), nunca por
    imports, fixtures o sintaxis. Las pruebas existentes que no se tocan siguen verdes.
    - **Archivos nuevos:** `backend/tests/funcional/integracion/test_catalogo_estados_013.py`,
      `test_retiro_transaccional_013.py`, `test_retiro_sede_013.py`,
      `test_anulacion_retiro_013.py`, `test_confirmacion_anulacion_013.py`,
      `test_patch_estado_retiro_013.py`, `backend/tests/no_funcional/seguridad/test_permisos_retiro_013.py`
      y el soporte de pruebas `backend/tests/funcional/integracion/_soporte_retiro_013.py`.
      **Editados:** `frontend/src/app/core/auth/roles.spec.ts`,
      `frontend/src/app/features/tickets/services/ticket.service.spec.ts`,
      `frontend/src/app/features/tickets/ticket-detalle.component.spec.ts` y
      `frontend/src/app/features/tickets/tickets.component.spec.ts`.
    - **Comandos y conteos.** Backend: `cd backend` + `.venv\Scripts\python.exe -m pytest`
      → **55 failed, 2051 passed, 112 skipped** (línea base previa: 2024/112; los 55 fallos
      son exclusivamente de los siete módulos nuevos; los 27 tests nuevos que ya pasan son
      los que fijan comportamientos conservados). Los siete módulos nuevos, ejecutados solos,
      dan **55 failed / 27 passed** (82 tests). Frontend:
      `$env:CHROME_BIN = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"; npx ng test --watch=false --browsers=ChromeHeadless`
      → **13 FAILED, 643 SUCCESS** (656 tests; línea base previa: 639).
    - **Rojos por AC y por qué.**
      **AC-50:** `_ESTADOS_TICKET_TENANT` sigue con `Pendiente`, cuatro filas sin `Anulado` y
      descripciones que dicen «despacho»; `NOMBRE_ESTADO_PENDIENTE` sigue existiendo.
      **AC-51:** el alta exige `Pendiente` (409 en `EnRevision`); en el tablero
      `estadoInicial()` es nulo con el catálogo nuevo y `estadoEnRevision` no existe.
      **AC-52/AC-53/AC-54/AC-60:** aprobar/editar aún nombran `Pendiente`; la edición solo
      acepta `Pendiente`; el `PATCH` conserva los literales `/despacho` y `Pendiente` y el
      retroceso/avance contiguo ya es correcto. **AC-55/AC-56/AC-57:** `/retiro` no está en
      OpenAPI ni en la matriz, `/despacho` sigue publicado y todas las variantes del retiro
      fallan por `exigir_retiro_publicado()` (T35); los casos `403/404/409/422` no pasan por
      el 404 del router. **AC-58/AC-59:** todo `Cerrado` responde 409 (no hay rama
      administrativa, ni `ENTRADA`, ni reset, ni `fecha_cierre` nula, ni creación de
      `stock_sede`); el 409 del Solicitante no dice «administrativa» y el 422 del motivo no se
      alcanza. **AC-61:** no se puede anular un `Cerrado` sin confirmar (la confirmación
      posterior nunca llega a probarse) y `entrega_confirmada` se presenta `true` en un
      `Anulado` con fila previa. **AC-62/AC-63:** el espejo no expone
      `ROLES_RETIRO_TICKETS`/`puedeRegistrarRetiro`, el servicio no tiene `registrarRetiro`
      (sigue `despacharTicket`/`/despacho`), el detalle no conoce la acción `registrarRetiro`,
      el tipo `'retiro'`, ni los títulos/copias «Registrar retiro»/«Confirmar retiro»/
      «Retirado», y el Administrador no ve «Anular el retiro». **AC-64:** la matriz conserva
      75 y `/anulacion`/`PATCH` sus roles, pero `/retiro` no figura, `/despacho` sí,
      `POST /inventario/movimientos` aún incluye al Administrador y `capacidad_de_operacion`
      no asocia `/retiro` a `kanban`; el conteo OpenAPI ya es 75/77 pero la ruta publicada es
      la histórica. **AC-65/AC-66:** sin rojos nuevos (la fórmula y la demanda no cambian).
    - **Módulos con `Pendiente` identificados y NO migrados** (T33–T42 los reconcilian):
      `backend/tests/conftest.py`, `_soporte_ciclo_vida_013.py`, los e2e
      `test_despacho_transaccional.py`, `test_ciclo_vida_flujo_013.py` y
      `test_flujo_aprobacion_entrega_013.py`, los `test_ciclo_vida_*_013.py`, `test_tablero_kanban.py`,
      `test_modal_ticket.py`, `test_ticket_sede_011.py`, dashboard/compras/cobertura
      (`test_ciclo_vida_dashboard_013.py`, `test_compras*`, `test_cobertura_021.py`),
      permisos/gating (`test_permisos_*`, `test_capacidades_gating_012.py`) y los gated
      `*postgres_013.py`. Grep de referencia: **56 archivos / 402 coincidencias** en
      `backend/tests`; en `frontend/src` quedan **28 archivos / 247 coincidencias** del
      vocabulario histórico (`Pendiente`, `Despachado`, `despachar`, `/despacho`) que T39–T41
      migran. `test_despacho_transaccional.py` se mantiene **verde** hasta T35/T42, como pide
      la tarea (T35 lo renombró a `test_retiro_005_regresion.py` al retirar `/despacho`; ver su
      Nota de fase).

- [x] **T33 — Semilla y catálogo de aprovisionamiento de cuatro estados.**
  - Archivos: `database/02_datos_semilla.sql`, `backend/app/services/control_service.py`,
    `backend/tests/funcional/sistema/test_catalogo_retiro_postgres_013.py` (nuevo) y
    `backend/tests/funcional/integracion/test_catalogo_estados_013.py`.
  - Prueba primero (gated para la semilla; integración para el catálogo del aprovisionamiento):
    `estado_ticket` con 4 filas (1 `EnRevision`, 2 `EnCurso`, 3 `Cerrado`, 4 `Anulado`), sin
    `Pendiente` ni homónimas; tickets 1–4/9 a 1, 5–6 a 2, 7–8/10 a 3, ninguno en 4; los `Cerrado`
    conservan `fecha_cierre` y `cantidad_entregada`; `_ESTADOS_TICKET_TENANT` con las 4 filas,
    `Anulado` incluido y descripciones sin «despacho»; 26/23 y `026.0`.
  - Implementación: cuatro filas y descripciones en la semilla; reenumerar los tickets; actualizar
    `_ESTADOS_TICKET_TENANT`; conservar la limpieza de `control.estado_ticket` (solo `Anulado`) y
    la copia previa a tenants. Sin tocar `01_esquema.sql`.
  - **AC:** AC-50.
  - **Depende de:** T32.
  - **Hecho cuando:** el gated de catálogo pasa contra PostgreSQL 16 sobre base desechable, el
    reset `down -v` + `up -d` arranca limpio y el SQL confirma las 4 filas y los tickets
    reenumerados. **[SQLite + PostgreSQL gated + reset]**
  - **Nota de fase (T33 ejecutada el 27/Nov/2026).** Se aplicó **solo** el catálogo y la
    semilla: no se tocó DDL, servicios de tickets, endpoints, frontend, matriz, `plan.md`,
    `spec.md` ni `stack.md`.
    - **Archivos editados:** `database/02_datos_semilla.sql` (4 filas con las descripciones de
      §10.3, sin `Pendiente` ni «despacho»; tickets 1–4/9 a 1, 5–6 a 2, 7–8/10 a 3, ninguno en 4;
      comentarios actualizados; guarda nueva por tenant que exige 4 filas, `Anulado` y ninguna
      `Pendiente`; se conservan la copia previa a tenants y la limpieza final de
      `control.estado_ticket` con solo `Anulado`),
      `backend/app/services/control_service.py` (`_ESTADOS_TICKET_TENANT` con las 4 filas),
      `backend/tests/funcional/integracion/test_catalogo_estados_013.py` (AC-50 en verde; los
      casos que dependen de `ticket_service` quedan `skip` con reason T34) y
      `backend/tests/funcional/sistema/test_catalogo_retiro_postgres_013.py` (nuevo gated, 5
      tests). No se tocó `01_esquema.sql`.
    - **Comandos y conteos.** Integración:
      `.venv\Scripts\python.exe -m pytest tests/funcional/integracion/test_catalogo_estados_013.py`
      → **7 passed, 7 skipped**. Gated con
      `$env:POSTGRES_TEST_URL = "postgresql://postgres:postgres@localhost:5433/postgres"` →
      **5 passed** (26,63 s): instala `01_`+`02_` en bases desechables `compustock_t33_*` y las
      destruye; **nunca toca `apt_erp`**. Cubre 4 filas por tenant, `control` solo `Anulado`,
      tickets reenumerados con `fecha_cierre`/entregas, 26/23 tablas, token `026.0` y el catálogo
      de un tenant recién aprovisionado por `control_service`.
    - **Suite SQLite completa:** **46 failed, 2053 passed, 124 skipped** (T32: 55/2051/112).
      Los 2 tests de AC-50 que curó T33 pasaron a verdes; 7 casos dependientes de T34 quedaron
      `skip`; los 5 gated nuevos se saltan sin `POSTGRES_TEST_URL`. Los **46 rojos restantes
      son exactamente los de T32** de retiro (19), anulación (7), confirmación (2), `PATCH` (6),
      sede (4) y seguridad/OpenAPI (8); **ningún test que ya estaba verde se rompió**.
    - **Reset:** **no se ejecutó** `down -v` + `up -d` para no destruir la base QA en esta
      tarea; la validación equivalente (y más fuerte) la hizo el gated instalando `01_`+`02_`
      desde cero en una base desechable. El reset de la QA queda para T44, como permite la
      tarea. Consecuencia esperada para T38: los snapshots gated que aún esperan 5 estados
      (`test_instalacion_limpia_postgres.py`) o siembran tickets en `Pendiente`
      (`test_ciclo_vida_aprobacion_confirmacion_postgres_013.py`) deben reconciliarse en T38
      (plan §10.11).

- [x] **T34 — Backend: estados, alta, aprobación, edición, anulación/rechazo y etiquetas.**
  - Archivos: `backend/app/services/ticket_service.py`,
    `backend/app/services/ticket_proceso.py`,
    `backend/tests/funcional/integracion/test_ciclo_vida_alta_inicial_013.py`,
    `test_ciclo_vida_aprobacion_013.py`,
    `test_ciclo_vida_edicion_013.py`, `test_ciclo_vida_flujo_013.py`,
    `backend/tests/funcional/unitarios/test_ticket_proceso_013.py` y
    `backend/tests/funcional/integracion/test_ticket_proceso_013.py`.
  - Prueba primero: alta `201` en `EnRevision` y `409` en cualquier otro estado o catálogo sin
    `EnRevision`; aprobación solo desde `EnRevision`; edición solo en `EnRevision`; anulación y
    rechazo solo desde `EnRevision` con sus actores; `PATCH` de legado `EnRevision → EnCurso` /
    `EnCurso → EnRevision` y `EnCurso → Cerrado` 409 con el detalle de retiro; etiquetas
    «Retirado»/«Entregado»/«Rechazado»/«En revisión» y `Pendiente` fuera.
  - Implementación: quitar `NOMBRE_ESTADO_PENDIENTE`; `crear_ticket`, `aprobar_ticket`,
    `editar_ticket` y `_cambiar_a_anulado` resuelven `EnRevision`; `actualizar_estado_ticket`
    actualiza el literal 409; `ticket_proceso.py` elimina la rama `pendiente` y renombra
    `ETIQUETA_DESPACHADO` → `ETIQUETA_RETIRADO`. Sin tocar todavía el retiro ni la anulación del
    retiro.
  - **AC:** AC-51, AC-52, AC-53, AC-54, AC-60 (rama de estados), AC-63 (etiqueta del servidor).
  - **Depende de:** T33.
  - **Hecho cuando:** las suites de alta, aprobación, edición, flujo y etiquetas pasan en SQLite sin
    referencias a `Pendiente` y el `PATCH` conserva la regla de un paso y la terminalidad.
    **[SQLite]**
  - **Nota de fase (T34 ejecutada el 27/Nov/2026).** Se implementó solo el flujo de estados:
    **no** se tocó el retiro, la anulación del retiro, la matriz, el frontend de producción ni
    `database/` (T33 cerrado).
    - **Producción editada:** `backend/app/services/ticket_service.py` (fuera
      `NOMBRE_ESTADO_PENDIENTE`; alta en `EnRevision`; aprobación, edición y
      anulación/rechazo solo desde `EnRevision`; `PATCH` con el literal
      `El cierre requiere retiro; use POST /api/v1/tickets/{ticket_id}/retiro`),
      `backend/app/services/ticket_proceso.py` (fuera la rama `pendiente`;
      `ETIQUETA_DESPACHADO` → `ETIQUETA_RETIRADO` «Retirado»; «En revisión» conserva su
      etiqueta y explicación de estado inicial) y **solo descripciones de contrato** en
      `backend/app/api/v1/endpoints/tickets.py` y `backend/app/schemas/ticket_schema.py`
      (alta/aprobación/anulación/rechazo/edición/PATCH). No se movió ninguna ruta ni fila de
      matriz.
    - **Fixtures y pruebas:** `conftest.py` y `_soporte_ciclo_vida_013.py` pasan a `EnRevision`
      (`estado_ingresado_id` y catálogo por defecto de 4 estados); se reescribieron
      `test_ciclo_vida_alta_inicial_013.py`, `test_ciclo_vida_aprobacion_013.py`,
      `test_ciclo_vida_edicion_013.py`, `test_ciclo_vida_flujo_013.py`,
      `test_ticket_proceso_013.py` (unitario e integración),
      `test_flujo_aprobacion_entrega_013.py` y `test_catalogo_estados_013.py` (se retiraron los
      7 `skip` de T33). `test_despacho_transaccional.py` sigue verde cambiando solo sus
      referencias de estado/clave a `EnRevision`/`estado_inicial_id` (su rename es T35/T42).
      Se reconciliaron además los verdes que dependían del catálogo viejo:
      `test_smoke.py`, `test_alta_solo_solicitante_007.py`, `test_ciclo_vida_autorizacion_013.py`,
      `test_ciclo_vida_historial_013.py`, `test_ciclo_vida_motivo_013.py`,
      `test_ciclo_vida_operativas_014.py`, `test_ciclo_vida_operativas_servicio_014.py`,
      `test_cobertura_021.py`, `test_compras.py`, `test_historial_movimientos.py`,
      `test_modal_ticket.py`, `test_tablero_kanban.py`, `test_ticket_sede_011.py`,
      `test_tickets_alcance.py`, `test_tickets_institucional.py`,
      `test_permisos_endpoints.py` y `test_contrato_024.py` (literal del `PATCH`).
    - **Comandos y conteos.** Módulos objetivo (alta, aprobación, edición, flujo e2e,
      `ticket_proceso` unitario+integración, e2e de aprobación/entrega, despacho y catálogo):
      **168 passed**. Suite SQLite completa: **39 failed, 2061 passed, 117 skipped** (T33:
      46/2053/124). Se curaron **7 rojos de T32**: los 6 de `test_patch_estado_retiro_013.py`
      y el OpenAPI del `PATCH` en seguridad/retiro; se eliminaron los 7 `skip` de T33 y **no
      queda ningún `skip` nuevo**. Los **39 rojos restantes son exactamente los de T32** de
      retiro (19), anulación (7), confirmación (2), sede (4) y seguridad/OpenAPI (7), que
      pertenecen a T35–T37. Ningún verde previo se rompió.
    - **Sin `Pendiente` vigente en los tests de T34:** solo quedan aserciones negativas que
      verifican su ausencia en catálogo/mensajes y la prueba unitaria de degradación del nombre
      derogado.

- [x] **T35 — Backend: retiro (DTO, ruta, servicio, matriz, ámbito y observación).**
  - Archivos: `backend/app/schemas/ticket_schema.py`,
    `backend/app/services/ticket_service.py`, `backend/app/services/inventario_service.py` (solo
    importación/reutilización), `backend/app/api/v1/endpoints/tickets.py`,
    `backend/app/core/permisos.py`, `backend/app/core/capacidades.py`,
    `backend/tests/funcional/integracion/test_retiro_transaccional_013.py`,
    `test_retiro_sede_013.py` y `backend/tests/no_funcional/seguridad/test_permisos_retiro_013.py`.
  - Prueba primero: `TicketDespacho` → `TicketRetiro`; `/despacho` ausente y `/retiro` presente;
    solo Bodeguero (Administrador/Solicitante/Superadmin 403); sede del Bodeguero (sin sede 409) y
    comparación con `ticket.sede_id` (otra sede 404 idéntico); ACID con `SALIDA` por detalle,
    observación
    `Salida por retiro del ticket #…; detalle_id=…; producto_id=…`, `cantidad_entregada`, sello de
    `fecha_cierre` e historial `EnCurso → Cerrado`; concurrencia SQLite y `PATCH` con el detalle de
    retiro.
  - Implementación: renombrar el DTO y el servicio (`registrar_retiro_ticket`), conservar el cuerpo
    ACID de la 005, cambiar la ruta y las claves de matriz/capacidad, reutilizar
    `sede_del_alcance_por_rol` antes de resolver el ticket y comparar `ticket.sede_id`; actualizar
    el literal 409 del `PATCH` y las descripciones OpenAPI. Matriz 75 (clave renombrada).
  - **AC:** AC-55, AC-56, AC-57, AC-60 (detalle de retiro), AC-64 (parte de retiro).
  - **Depende de:** T34.
  - **Hecho cuando:** el retiro se verifica por HTTP con sus roles, códigos, observación y una sola
    transacción; `/despacho` ya no existe en el contrato. **[SQLite]**
  - **Nota de fase (T35 ejecutada el 27/Nov/2026).** Se implementó **solo el retiro**; no se tocó
    la anulación del retiro con `ENTRADA` ni la confirmación bloqueante (T36), los roles de
    `/inventario/movimientos` (T37), el frontend de producción, `database/` ni `plan/spec/stack`.
    - **Producción editada:** `backend/app/schemas/ticket_schema.py` (`TicketDespacho` →
      `TicketRetiro`), `backend/app/services/ticket_service.py` (`despachar_ticket` →
      `registrar_retiro_ticket`, cuerpo ACID de la 005, observación
      `Salida por retiro del ticket #{ticket_id}; detalle_id={detalle_ticket_id}; producto_id={producto_id}`,
      `sede_del_alcance_por_rol` para el 409 sin sede y comparación `ticket.sede_id` para el 404 de
      otra sede), `backend/app/api/v1/endpoints/tickets.py` (ruta `/retiro` y descripción OpenAPI),
      `backend/app/core/permisos.py` (`_RETIRO_TICKETS = {Bodeguero}`; `_ESCRITURA_STOCK` intacto
      para T37) y `backend/app/core/capacidades.py` (`/retiro` → `kanban`). `inventario_service.py`
      solo se reutiliza su helper; no se modificó.
    - **Reconciliación del test 005:** `test_despacho_transaccional.py` se **renombró** a
      `test_retiro_005_regresion.py` (no se mergeó, para conservar su cobertura y evitar colisión
      con `test_retiro_transaccional_013.py`); se actualizaron ruta, observación, DTO y actor
      (Bodeguero de la sede) y se borraron el `.py` y el `.pyc` viejos. `test_despacho_dtos.py` se
      renombró a `test_retiro_dtos.py`. No queda ningún test llamando a `/despacho`; solo quedan
      aserciones negativas que verifican su ausencia.
    - **Tests ajustados:** los módulos objetivo de T32 más
      `test_permisos_endpoints.py`, `test_permisos.py`, `test_permisos_008/010/012.py`,
      `test_capacidades_gating_012.py`, `test_auth_me_institucion.py`, `test_organizacion_011.py`,
      `test_contrato_024.py`, `test_esquemas_027.py` y los e2e/integración que ejercían el cierre
      con el actor Administrador (`test_ciclo_vida_flujo_013.py`,
      `test_flujo_aprobacion_entrega_013.py`, `test_alta_solo_solicitante_007.py`,
      `test_ticket_proceso_013.py`, `test_ticket_sede_011.py`, `test_tickets_alcance.py`,
      `test_tickets_institucional.py`, `test_historial_movimientos.py`,
      `test_ciclo_vida_operativas_014.py`, `test_ciclo_vida_aprobacion_013.py`,
      `test_ciclo_vida_confirmacion_013.py`, `test_ciclo_vida_autorizacion_013.py` y
      `test_filtros_inventario_018.py`). El gated de T38 solo recibió el rename de símbolos para
      no romper la colección; su semántica sigue pendiente de T38.
    - **Comandos y conteos.** Módulos objetivo (`test_retiro_transaccional_013`,
      `test_retiro_sede_013`, `test_permisos_retiro_013`, `test_retiro_005_regresion`,
      `test_retiro_dtos`, `test_permisos_endpoints`, `test_capacidades_gating_012`) →
      **316 passed, 1 failed**: el rojo restante es
      `test_los_movimientos_manuales_son_solo_del_bodeguero_ac_64`, que pertenece a T37 y se
      conserva a propósito. Suite SQLite completa: **10 failed, 2091 passed, 117 skipped**
      (T34: 39/2061/117). Se curaron **29 rojos**: 19 del retiro, 4 de sede y 6 de
      seguridad/OpenAPI del retiro. Los **10 restantes** son 7 de anulación, 2 de confirmación
      (T36) y 1 de movimientos manuales (T37); ningún verde previo se rompió y no se añadió
      ningún `skip`.
    - **Contrato vivo:** matriz **75**; `/openapi.json` **75 v1 / 77 entradas**; `/retiro`
      publicada y `/despacho` ausente; `PATCH` conserva el 409 que dirige a `/retiro`.

- [x] **T36 — Backend: anulación del retiro y confirmación bloqueante.**
  - Archivos: `backend/app/services/ticket_service.py`,
    `backend/tests/funcional/integracion/test_anulacion_retiro_013.py` y
    `test_confirmacion_anulacion_013.py`, `test_ciclo_vida_confirmacion_013.py` y
    `test_ciclo_vida_flujo_013.py`.
  - Prueba primero: desde `Cerrado` **sin confirmar**, solo Administrador → 200 con `ENTRADA` por
    detalle con `cantidad_entregada > 0`, incremento/creación de `stock_sede`, reset a 0,
    `fecha_cierre` nula, historial `Cerrado → Anulado` y una sola transacción; Solicitante dueño
    409; **pedido confirmado 409 sin escribir ni borrar la fila de confirmación**; `/rechazo`
    sobre `Cerrado` 409 sin devolver stock; `Cerrado` sin `sede_id` 409 sin escribir; choque de
    unicidad al crear `stock_sede` → 409, nunca 500; `EnCurso`/`Anulado` 409; motivo inválido 422
    (orden 404 → 409 estado → 409 rol → 409 confirmación → 409 sin sede → 422); desde `EnRevision`
    se conserva la anulación sin stock; confirmación posterior a una anulación 409.
  - Implementación: `select(Ticket).with_for_update()` en `_cambiar_a_anulado`; resolver la rama
    `Cerrado` **solo para `anulacion`**; comprobar rol, confirmación y `ticket.sede_id` antes del
    motivo; bloquear `stock_sede` por `producto_id`, crear la fila si falta con el patrón de la
    recepción y traducir el choque de unicidad a 409 (patrón 026); devolver el stock; `commit`
    único y `rollback` ante excepción. La confirmación no cambia de contrato; solo se verifica el
    cruce.
  - **AC:** AC-58, AC-59, AC-61, AC-60 (sin cambios).
  - **Depende de:** T35.
  - **Hecho cuando:** la anulación y la confirmación se verifican por HTTP con sus códigos, stock,
    cantidades, fecha e historial, y el caso confirmado responde 409 sin efectos. **[SQLite]**
  - **Nota de fase (T36 ejecutada el 27/Nov/2026).** Se implementó la anulación administrativa
    del retiro y el cruce con la confirmación; **no** se tocó `/inventario/movimientos` (T37), el
    gated de PostgreSQL (T38), el frontend de producción (T39–T41), `database/`, `plan.md`,
    `spec.md` ni `stack.md`.
    - **Producción editada:** solo `backend/app/services/ticket_service.py`.
      `_cambiar_a_anulado` recibe `tipo_operacion` (`"anulacion"`/`"rechazo"`) y bloquea el
      ticket con `with_for_update()` desde el inicio; la rama `Cerrado` (solo para `anulacion`)
      vive en `_anular_retiro_administrativo` con el orden 404 → 409 estado → 409 rol →
      409 confirmación → 409 sin sede → 422 motivo. `_devolver_stock_de_anulacion` bloquea o
      crea la fila `stock_sede` por `producto_id` (patrón de la recepción 020) y escribe una
      `ENTRADA` por detalle con la observación literal, sin exigir `producto.activo` ni
      `sede.activo`; `_es_choque_de_unicidad_de_stock` traduce la carrera de creación a **409** y
      cualquier otro fallo hace `rollback`. `_cargar_confirmaciones_por_ticket` filtra por estado
      vigente `Cerrado`, de modo que un `Anulado` que conserva la fila de confirmación previa ya
      no se presenta «Entregado». El contrato de la confirmación no cambió.
    - **Pruebas:** `test_anulacion_retiro_013.py` ganó la atomicidad con `_registrar_transicion`
      inyectada (500 con stock, cantidades, fecha, estado e historial intactos) y el caso de dos
      detalles del mismo producto cuando falta la fila de stock; `test_ciclo_vida_flujo_013.py`
      ganó el ciclo completo `EnCurso → Cerrado → Anulado` y movió el 409→422 de AC-7 a
      `EnCurso`, porque `Cerrado` dejó de ser inadmisible para el Administrador (AC-58).
      `test_confirmacion_anulacion_013.py` y `test_ciclo_vida_confirmacion_013.py` ya cubrían los
      dos órdenes del cruce y no necesitaron cambios. No se añadió ningún `skip`.
    - **Comandos y conteos.** Módulos objetivo (`test_anulacion_retiro_013`,
      `test_confirmacion_anulacion_013`, `test_ciclo_vida_confirmacion_013`,
      `test_ciclo_vida_flujo_013`) → **71 passed**. Suite SQLite completa: **1 failed,
      2103 passed, 117 skipped** (T35: 10/2091/117). Se curaron los **9 rojos** de
      anulación/confirmación; el único rojo restante es
      `test_los_movimientos_manuales_son_solo_del_bodeguero_ac_64`, que pertenece a T37. Ningún
      verde previo se rompió.
    - **Cruce verificado:** confirmación previa → anulación 409 **sin borrar ni reescribir** la
      fila canónica; anulación previa → confirmación 409 con el pedido en `Anulado` y las
      cantidades reseteadas. La concurrencia real con dos sesiones queda para el gated de T38.

- [x] **T37 — Backend: contrato, matriz 75 y OpenAPI 75/77; movimientos solo Bodeguero.**
  - Archivos: `backend/app/core/permisos.py`, `backend/app/api/v1/endpoints/inventario.py` (solo
    descripción, si aplica), `backend/tests/no_funcional/seguridad/test_permisos_endpoints.py`,
    `backend/tests/funcional/integracion/test_cobertura_021.py`,
    `test_ciclo_vida_autorizacion_013.py`, `test_permisos_008.py`, `test_permisos_010.py`,
    `test_permisos_012.py` y `test_capacidades_gating_012.py`.
  - Prueba primero: `POST /inventario/movimientos` solo `Bodeguero` (Administrador 403);
    `/anulacion` conserva `{Administrador, Solicitante}`; `/retiro` solo `Bodeguero`; matriz **75**;
    `/openapi.json` **75 v1/77**, `/despacho` ausente y `/retiro` publicada; la anulación documenta
    el 409 de confirmación y el `PATCH` el 409 de retiro.
  - Implementación: ajustar `_ESCRITURA_STOCK`/constantes de la matriz sin cambiar la cardinalidad;
    actualizar descripciones OpenAPI y las aserciones absolutas de recuento.
  - **AC:** AC-64, AC-55 (contrato), AC-67 (parte de contrato).
  - **Depende de:** T35, T36.
  - **Hecho cuando:** matriz y OpenAPI pasan con 75/77, las rutas publicadas coinciden y el
    Administrador recibe 403 en movimientos. **[SQLite]**
  - **Nota de fase (T37 ejecutada el 27/Nov/2026).** Se ajustó el contrato de la enmienda:
    `POST /inventario/movimientos` queda **solo** para el Bodeguero, con la matriz en **75** y
    OpenAPI **75 v1 / 77**. **No** se tocó T38, el frontend de producción (T39–T41), `database/`,
    `plan.md`, `spec.md` ni `stack.md`.
    - **Producción editada:** `backend/app/core/permisos.py` (`_ESCRITURA_STOCK` pasa a
      `{Bodeguero}` con el comentario de operación de bodega; la fila de movimientos lo consume y
      `_RETIRO_TICKETS` sigue dedicado), `backend/app/api/v1/endpoints/inventario.py` (solo la
      descripción OpenAPI del `POST /movimientos`: Bodeguero, 403 del Administrador/Solicitante/
      Superadmin y 404/409/422 sin escritura) y `backend/app/api/v1/endpoints/tickets.py` (solo la
      descripción del `/anulacion`: devolución de stock, 409 de confirmación previa y 409 de sede
      ausente). Ningún `response_model` ni código de éxito cambió.
    - **Matriz y contrato:** 75 operaciones (ajuste de roles, sin fila nueva); `POST /retiro`
      `{Bodeguero}` y `POST /anulacion` `{Administrador, Solicitante}` intactos; `/despacho`
      ausente; `/openapi.json` con 75 v1 + `GET /` y `/health` = 77, y las rutas publicadas iguales
      a la matriz.
    - **Transcripciones históricas:** `test_permisos_008/010/012.py` y
      `test_ciclo_vida_autorizacion_013.py` conservan sus filas y documentan la restricción de la
      013 en `RESTRINGIDAS_013` (la 018 la consume por importación); `test_permisos_008.py` gana
      `EXCEPCION_MOVIMIENTOS_026N`; `test_permisos_endpoints.py` (seam vivo) usa
      `_MOVIMIENTOS_MANUALES = {Bodeguero}`; `test_permisos.py` aplica la restricción sobre su
      matriz histórica. `test_permisos_retiro_013.py` amplía su rojo de AC-64 con la verificación
      HTTP (403 sin mutación para Administrador, Solicitante y Superadmin; 201 del Bodeguero) y las
      descripciones vigentes de movimientos y anulación en su prueba de recuentos.
    - **Clientes migrados a Bodeguero con sede** (el Administrador ya no escribe movimientos):
      `test_smoke.py`, `test_transaccion_ticket.py`, `test_historial_movimientos.py`,
      `test_ciclo_vida_operativas_014.py`, `test_inventario_sede_011.py`,
      `test_validacion_entradas_027.py`, `test_ciclo_vida_catalogo_estado_014.py`,
      `test_dashboard_analitico.py` (`_cliente`/`_identidad` con `sede_id`) y
      `test_integracion_multitenant_010.py` (identidad Bodeguero para el 422 de `extra`).
    - **Comandos y conteos.** Módulos objetivo (`test_permisos_retiro_013`, `test_permisos_endpoints`,
      `test_permisos`, `test_permisos_008/010/012`, `test_capacidades_gating_012`,
      `test_cobertura_021`, `test_ciclo_vida_autorizacion_013`, `test_contrato_024`) →
      **418 passed**. Suite SQLite completa: **2104 passed, 117 skipped, 0 failed**
      (T36: 1/2103/117). Se curó el único rojo
      (`test_los_movimientos_manuales_son_solo_del_bodeguero_ac_64`); ningún verde previo se rompió
      y no se añadió ningún `skip`. `ng test` no corresponde a esta tarea: las rojas de frontend
      siguen pendientes de T39–T41.

- [x] **T38 — PostgreSQL gated: catálogo, concurrencia del retiro, anulación y confirmación.**
  - Archivos: `backend/tests/funcional/sistema/test_catalogo_retiro_postgres_013.py`,
    `test_retiro_anulacion_postgres_013.py` (nuevo).
  - Prueba primero (gated, `skip` sin `POSTGRES_TEST_URL`): 4 filas en control y tenant, token
    `026.0`, 26/23; retiro concurrente `(200, 409)` con un solo juego de `SALIDA`; anulación
    concurrente `(200, 409)` con una sola `ENTRADA`; confirmación vs anulación en ambos órdenes
    `(200, 409)`; creación de `stock_sede` y lectura persistida de stock, cantidades, `fecha_cierre`
    e historial; nunca toca `apt_erp`.
  - Implementación: solo correcciones si la concurrencia revela un defecto en T35/T36; no se añaden
    bloqueos fuera del patrón ticket → `stock_sede`.
  - **AC:** AC-50, AC-57, AC-58, AC-59, AC-61.
  - **Depende de:** T36.
  - **Hecho cuando:** los módulos gated pasan contra PostgreSQL 16 sobre bases desechables y no
    tocan `apt_erp`. **[PostgreSQL gated]**
  - **Nota de fase (T38 ejecutada el 27/Nov/2026).** Se acreditó la concurrencia del retiro, la
    anulación y el cruce con la confirmación contra PostgreSQL 16 real, y se reconciliaron los
    gated que todavía esperaban cinco estados o `Pendiente`. **No** se tocó producción (la
    concurrencia no reveló defectos en T35/T36), ni el contrato, la matriz, la semilla, el
    frontend, `plan.md`, `spec.md` ni `stack.md`.
    - **Módulo nuevo:** `backend/tests/funcional/sistema/test_retiro_anulacion_postgres_013.py`
      (6 pruebas, gated): retiro concurrente `(200, 409)` con un solo juego de `SALIDA` y una sola
      rebaja; anulación concurrente `(200, 409)` con una sola `ENTRADA`, `cantidad_entregada = 0`,
      `fecha_cierre` nula e historial `Cerrado → Anulado`; creación de la fila `stock_sede` cuando
      falta; confirmación previa bloquea la anulación (409 sin borrar la fila) y anulación previa
      bloquea la confirmación (409); cruce en paralelo con un único efecto, nunca las dos. Bases
      `compustock_t38_*` creadas y destruidas por prueba.
    - **Reconciliados:** `test_instalacion_limpia_postgres.py` (catálogo del tenant **5 → 4**
      filas); `test_ciclo_vida_aprobacion_confirmacion_postgres_013.py` (`Pendiente` →
      `EnRevision`, helper `_crear_ticket_en_revision`, transición esperada
      `EnRevision → EnCurso`, retiro por Bodeguero con su sede y vocabulario de retiro).
      `test_catalogo_retiro_postgres_013.py` ya estaba al día (T33) y se reejecutó.
    - **Comandos y conteos gated** (`$env:POSTGRES_TEST_URL="postgresql://postgres:postgres@localhost:5433/postgres"`):
      `test_catalogo_retiro_postgres_013.py` **5 passed**; `test_retiro_anulacion_postgres_013.py`
      **6 passed**; `test_ciclo_vida_aprobacion_confirmacion_postgres_013.py` **3 passed**;
      `test_instalacion_limpia_postgres.py` **8 passed**; de contraste,
      `test_ciclo_vida_ticket_postgres_013.py` **4 passed**,
      `test_ciclo_vida_catalogo_postgres_014.py` **9 passed** y
      `test_salud_esquema_postgres_026.py` **14 passed** → **49 passed, 0 failed** en conjunto.
    - **Higiene:** ninguna base `compustock_*` quedó creada tras las corridas; el módulo solo usa
      la base de mantenimiento `postgres` para crear y destruir sus bases desechables y **nunca**
      se conecta a `apt_erp`.
    - **Suite SQLite (sin `POSTGRES_TEST_URL`):** **2104 passed, 123 skipped, 0 failed** (el +6 de
      skipped son las pruebas nuevas, que se saltan sin la variable).

- [x] **T39 — Frontend: roles, interfaces y servicio de tickets.**
  - Archivos: `frontend/src/app/core/auth/roles.ts`, `roles.spec.ts`,
    `frontend/src/app/shared/interfaces/index.ts`,
    `frontend/src/app/features/tickets/services/ticket.service.ts`,
    `frontend/src/app/features/tickets/ticket.service.spec.ts`.
  - Prueba primero: `registrarRetiro` llama a `/retiro` con `{usuario_id}` y no a `/despacho`;
    `puedeRegistrarRetiro`/`ROLES_RETIRO_TICKETS` solo Bodeguero; `puedeAnularTicket` conserva
    Administrador/Solicitante; ninguna interfaz nombra `Pendiente`; comentarios con el término
    vigente.
  - Implementación: renombrar el método del servicio, la constante y el helper a
    `registrarRetiro`, `ROLES_RETIRO_TICKETS` y `puedeRegistrarRetiro`; cambiar la URL y los roles;
    actualizar comentarios y tipos. Sin tocar el detalle ni el tablero.
  - **AC:** AC-55, AC-63, AC-64 (espejo).
  - **Depende de:** T35.
  - **Hecho cuando:** `ticket.service.spec.ts` y `roles.spec.ts` pasan con los nombres nuevos, el
    proyecto compila y ningún archivo activo del frontend conserva los identificadores históricos
    del mapping de D-29. **[ng test]**
  - **Nota de fase (T39 ejecutada el 27/Nov/2026).** Se renombró el contrato del frontend al
    **retiro**: `ROLES_RETIRO_TICKETS` (`{Bodeguero}`), `puedeRegistrarRetiro` y
    `registrarRetiro` (`POST /tickets/{id}/retiro` con `{usuario_id}`). No se tocó la copia
    visible, las acciones, la lógica del detalle ni el tablero (T40/T41), ni el backend,
    `database/`, `plan.md`, `spec.md` o `stack.md`.
    - **Archivos:** `frontend/src/app/core/auth/roles.ts` (constante y helper renombrados, solo
      Bodeguero; comentarios de `ROLES_OPERATIVOS_TICKETS` al término vigente; `puedeAnularTicket`
      intacto), `roles.spec.ts` (imports estáticos y aserciones del contrato nuevo),
      `frontend/src/app/features/tickets/services/ticket.service.ts` (`despacharTicket` →
      `registrarRetiro`, URL `/retiro`; comentario de edición en `EnRevision`),
      `ticket.service.spec.ts` (llamada estática al método nuevo), 
      `frontend/src/app/shared/interfaces/index.ts` (`Ticket.sede_id?: number | null` para el
      guard de sede de T40, alineado con `TicketRespuesta`; comentario de `TicketEditar` sin
      `Pendiente`) y `ticket-detalle.component.ts` (**solo** el import del helper y las dos
      llamadas: guard y `servicioTickets.registrarRetiro`).
    - **Sin rastros activos:** no queda `despacharTicket`, `puedeDespacharTicket`,
      `ROLES_DESPACHO_TICKETS` ni `/despacho` fuera de las aserciones negativas de los specs.
    - **Comandos y conteos.** `$env:CHROME_BIN=…\msedge.exe` +
      `npx ng test --watch=false --browsers=ChromeHeadless --include=…roles.spec.ts
      --include=…ticket.service.spec.ts` → **35 SUCCESS**. Suite completa → **642 SUCCESS,
      14 FAILED**: se curaron las **5** rojas de roles/servicio y quedan (a) las **6** rojas nuevas
      del detalle de T32, (b) **6** pruebas antiguas del detalle que codificaban el despacho por
      Administrador y la URL `/despacho` (expectativas obsoletas que T40 reescribe al contrato de
      retiro) y (c) las **2** rojas del tablero (T41). Ningún módulo ajeno al detalle/tablero se
      rompió. `npx ng build` → **Application bundle generation complete** (30.8 s).

- [x] **T40 — Frontend: detalle con retiro, anulación condicionada y copia nueva.**
  - Archivos: `frontend/src/app/features/tickets/ticket-detalle.component.ts` (+ `.html`,
    `.spec.ts`).
  - Prueba primero: la acción `registrarRetiro`, el tipo `'retiro'` y los títulos «Registrar
    retiro»/«Confirmar retiro»; solo Bodeguero, pedido `EnCurso`, de su sede y con
    `stock_disponible`; resultado «Retirado»; «Anular el retiro» solo Administrador, `Cerrado` y
    `entrega_confirmada = false`; tras la confirmación la acción desaparece y el pedido se
    presenta «Entregado»; 409/422 en `role="alert"`, sin doble envío y con reconsulta; etiqueta
    «Retirado»/«Entregado»/«Rechazado»/«En revisión»; ninguna rama conserva el tipo o el título
    histórico.
  - Implementación: ajustar `acciones` con la clave `registrarRetiro`, la unión de `confirmando`
    con `'retiro'`, el método `solicitarRetiro` y la copia; no ofrecer el retiro al Administrador
    ni a un Bodeguero sin sede/otra sede; mostrar el motivo solo en anulación/rechazo. Sin
    `PATCH`.
  - **AC:** AC-55…AC-58, AC-61, AC-63.
  - **Depende de:** T39, T36.
  - **Hecho cuando:** los specs del detalle pasan, `ng build` compila el componente y no queda
    ninguna rama con el tipo o el título histórico (mapping de D-29). **[ng test]**
  - **Nota de fase (T40 ejecutada el 27/Nov/2026).** El detalle pasó al contrato de **retiro**:
    `AccionesDetalle.registrarRetiro` (sustituye a `despachar`), `TipoConfirmacion 'retiro'`,
    `solicitarRetiro`, títulos «Registrar retiro»/«Confirmar retiro» y resultado «Retirado». No se
    tocó el tablero (`tickets.component.*`, T41), el backend, `database/`, `plan.md`, `spec.md`,
    `stack.md` ni otras features.
    - **Archivos:** `frontend/src/app/features/tickets/ticket-detalle.component.ts`
      (`registrarRetiro` con `EnCurso` + `puedeRegistrarRetiro` + `stock_disponible` + **sede del
      pedido igual a `/auth/me.sede.sede_id`**; `solicitarRetiro`; `'retiro'` en los diálogos y en
      `confirmar`; `esAnulacionDeRetiro` y «Anular el retiro» solo Administrador, `Cerrado` y
      `entrega_confirmada !== true`, reutilizando el diálogo con motivo; `notaAcciones` y copia de
      retiro), `ticket-detalle.component.html` (botón «Registrar retiro», «Anular el retiro»
      condicionado, alerta de stock «Listo para el retiro», copia de edición en «En revisión») y
      `ticket-detalle.component.spec.ts` (bloque `despacho` reescrito como `retiro`, expectativas
      de acciones y aprobación al contrato nuevo, fixtures «Despachado» → «Retirado», sin
      `RUTA_DESPACHO`).
    - **Copia y etiquetas:** «En revisión», «Retirado», «Entregado», «Rechazado»; sin
      «Despachado» ni «En aprobación» en el componente. El `Pendiente` heredado se conserva solo
      como tolerancia de las ramas de aprobación/edición, igual que en el resto de la suite hasta
      T41.
    - **Comandos y conteos.** `$env:CHROME_BIN=…\msedge.exe` +
      `npx ng test --watch=false --browsers=ChromeHeadless --include=…ticket-detalle.component.spec.ts`
      → **73 SUCCESS**. Suite completa → **656 SUCCESS, 2 FAILED**: quedan únicamente las **2**
      rojas del tablero de T32/T41 (`TicketsComponent enmienda 26/Nov/2026: tres columnas y alta en
      EnRevision`), sin rojas ajenas. `npx ng build` → **Application bundle generation complete**
      (28.9 s).

- [x] **T41 — Frontend: tablero de tres columnas, alta en `EnRevision` y etiquetas.**
  - Archivos: `frontend/src/app/features/tickets/tickets.component.ts` (+ `.html`, `.spec.ts`),
    `frontend/src/app/shared/utils/etiqueta-estado.ts` (comentario) y el modal de alta si procede.
  - Prueba primero: exactamente 3 columnas (`EnRevision` «En Revisión», `EnCurso` «En Curso»,
    «Terminados» con `Cerrado`+`Anulado`); sin columna `Pendiente` ni `Anulado` separada; alta fija
    en `EnRevision` resuelta por nombre y prioridad `Media`; tarjeta con «Retirado»/«Entregado»/
    «Rechazado», responsables y enlace; contadores.
  - Implementación: `columnas` agrupa `EnRevision` y `EnCurso` más «Terminados»; `estadoPendiente`
    → `estadoEnRevision`; fixtures sin `Pendiente`; `etiqueta-estado.ts` sin la mención a
    `Pendiente` en el comentario.
  - **AC:** AC-51, AC-62, AC-63.
  - **Depende de:** T39.
  - **Hecho cuando:** los specs del tablero y del alta pasan, `ng build` compila y el tablero no
    referencia los identificadores históricos de D-29. **[ng test]**
  - **Nota de fase (T41 ejecutada el 27/Nov/2026).** El tablero quedó en **tres columnas**
    (`EnRevision` «En Revisión», `EnCurso` «En Curso» y «Terminados» con `Cerrado` + `Anulado`),
    sin columna `Pendiente` ni `Anulado` separada, y el alta nace en `EnRevision` resuelto por
    nombre. No se tocó el detalle (T40), el backend, `database/`, `plan.md`, `spec.md`, `stack.md`
    ni otras features.
    - **Archivos:** `frontend/src/app/features/tickets/tickets.component.ts`
      (`NOMBRE_ESTADO_PENDIENTE` → `NOMBRE_ESTADO_EN_REVISION`; `estadoPendiente` →
      `estadoEnRevision`; `nombreEstadoInicial`/`estadoInicial` y valores por defecto sobre
      `EnRevision`; se retiró `estadosAlta`, que ya no usaba el modal; comentarios del tablero al
      catálogo de cuatro estados), `tickets.component.html` (campo «Fijo» con `estadoEnRevision` y
      el aviso «no contiene el estado EnRevision»), `tickets.component.spec.ts` (fixtures del
      catálogo de cuatro estados, columnas, alta, tarjetas y etiquetas; sin `Pendiente` como
      estado del flujo) y `frontend/src/app/shared/utils/etiqueta-estado.ts` (comentario sin
      `Pendiente`; el mapa sigue con `EnCurso` y `EnRevision`).
    - **Copia y etiquetas:** «En revisión», «Retirado», «Entregado», «Rechazado»; sin
      «Despachado» ni «En aprobación» en el tablero/alta. Contadores = tarjetas de cada columna,
      tablero de solo lectura y tarjeta-enlace intactos.
    - **Comandos y conteos.** `$env:CHROME_BIN=…\msedge.exe` +
      `npx ng test --watch=false --browsers=ChromeHeadless --include=…tickets.component.spec.ts`
      → **87 SUCCESS**. Suite completa → **658 SUCCESS, 0 FAILED**. `npx ng build` →
      **Application bundle generation complete** (33.7 s).
    - **Restos de `Pendiente` reportados para el grep de cierre:** en el detalle se conserva la
      **tolerancia** a `Pendiente` en `admiteDecision` y en `editar`
      (`ticket-detalle.component.ts`), junto con los fixtures históricos de
      `ticket-detalle.component.spec.ts`; `etiqueta-estado.spec.ts` comprueba el passthrough de
      `etiquetaEstado('Pendiente')`. En el tablero solo quedan **aserciones negativas** que
      verifican que `Pendiente`/`estadoPendiente` ya no existen. No se tocó el detalle.
  - **Corrección post-cierre (27/Nov/2026).** El tablero mostraba tres columnas sobre
    `md:grid-cols-4`, dejando una celda vacía a la derecha. Se cambió a **`md:grid-cols-3`**
    en `tickets.component.html`, contenedor `data-testid="tablero-pedidos"`, y el comentario
    pasó a «dos operativas + una terminal agrupada». Regresión en
    `tickets.component.spec.ts`: el contenedor debe tener `grid-cols-1` y `md:grid-cols-3`, y
    **no** `md:grid-cols-4`. `ng test` **684 SUCCESS / 0 FAILED**; `ng build` limpio
    (`main-6T35N3WS.js`); 4200 verificado con tres columnas de ~385 px sobre 1202 px de ancho.
    **8080:** imagen reconstruida y contenedor recreado con `--force-recreate` (ID
    `sha256:7d3dbf…`); sirve **`main-6T35N3WS.js`**; `main-IRJLFDU6.js` y
    `main-72C5Q3DY.js` responden **404**; tablero verificado con tres columnas de ~385 px
    (captura `40-21`). Sin cambios en la lógica de agrupación, tarjetas, copia ni número de
    columnas.
  - **Corrección del shell (27/Nov/2026).** El shell usaba `flex h-screen` sin
    `overflow-hidden` y el `nav` sin scroll propio; la página desbordaba y aparecía blanco
    bajo el sidebar. Se añadió **`overflow-hidden` + `[contain:paint]`** al contenedor raíz y
    **`min-h-0 overflow-y-auto`** al `nav`; el `<main>` conserva su `overflow-y-auto`. El
    `contain:paint` fue necesario porque el scroll interno de la vista también contribuía al
    scroll del documento. Regresión en `app.component.spec.ts` (shell, nav y main). `ng test`
    **685 SUCCESS / 0 FAILED**; `ng build` limpio (`main-SHBQMIGH.js`). **4200:** documento
    **674 = ventana 674**, `window.scrollTo(9999)` no mueve, nav forzado **272 > 160** y
    `scrollTop` 112, main **1329/610** con scroll interno. **8080:** imagen
    `sha256:317fbdf…` recreada con `--force-recreate`; sirve **`main-SHBQMIGH.js`**;
    `main-6T35N3WS.js`, `main-IRJLFDU6.js` y `main-72C5Q3DY.js` responden **404**; mismas
    métricas; captura `40-22`. Sin cambios en `<main>`, navegación, enlaces ni lógica de
    vistas.

- [x] **T42 — Backend: e2e del flujo y regresión de suites SQLite.**
  - Archivos: `backend/tests/funcional/e2e/test_flujo_retiro_013.py` (nuevo) y los módulos
    reconciliados de T34–T37.
  - Prueba primero: alta → aprobar → retirar → confirmar; anular antes de confirmar (devolución de
    stock) y 409 después de confirmar; `PATCH` de legado 403 para Bodeguero y 200/409 para
    Administrador; Compras/021 sin cambio; caso #10; tablero de 3 columnas y detalle con las
    acciones nuevas.
  - Implementación: solo correcciones si el e2e revela un defecto conforme a T34–T37; no se amplía
    la spec.
  - **AC:** AC-50…AC-68 (integración).
  - **Depende de:** T36, T37.
  - **Hecho cuando:** el e2e y la suite SQLite completa pasan sin regresiones ni referencias
    vigentes a `Pendiente`/`/despacho`. **[SQLite]**
  - **Nota de fase (T42 ejecutada el 27/Nov/2026).**
    - **Paso 0 (línea base):** `pytest -q` antes de escribir → **2158 passed, 127 skipped,
      0 failed**. El refactor externo del backend añadió 54 pruebas y 4 skips sobre los
      ~2104/123 esperados; como no hubo ningún fallo (ni en `organizacion*`, `config` ni
      `models`), se continuó.
    - **E2E nuevo:** `backend/tests/funcional/e2e/test_flujo_retiro_013.py` (5 pruebas HTTP):
      alta → aprobar → retirar → confirmar con `SALIDA`, `cantidad_entregada`, `fecha_cierre` e
      historial; anulación del retiro **antes** de confirmar (`Anulado`, `ENTRADA`, stock
      restituido, reset, `fecha_cierre` nula, historial `Cerrado → Anulado`) y confirmación
      posterior 409; **confirmación previa** bloquea la anulación (409 sin tocar fila, stock,
      fecha ni estado); `PATCH /estado` de legado (Bodeguero 403; Administrador 200 en
      `EnRevision → EnCurso` y 409 al intentar `EnCurso → Cerrado`); Compras/021 (caso #10
      equivalente omitido antes y después de la devolución, sin filas de desbloqueo ni de plan
      de compra).
    - **Limpieza de `Pendiente`:** `ticket-detalle.component.ts` (`admiteDecision` solo
      `EnRevision`; la edición se habilita en `EnRevision`, no en `Pendiente`; comentarios),
      `ticket-detalle.component.spec.ts` (fixtures y expectativas al catálogo de cuatro estados;
      `explicacion_proceso` «En aprobación» → «En revisión») y
      `shared/utils/etiqueta-estado.spec.ts` (passthrough con `Archivado`). El grep de cierre
      reveló tres cadenas obsoletas más en archivos de la 013 y se corrigieron **sin cambio de
      comportamiento**: `tickets.py` («despachado»/«Despachado» → «retirado»/«Retirado» en el
      contrato de la confirmación), `ticket_schema.py` (ejemplo «En aprobación» → «En revisión»)
      y `ticket_service.py` (comentario `Pendiente` → `EnRevision`). Se conservan las menciones
      **históricas/negativas** de las specs 005/013, del glosario y de los tests
      (`ticket_proceso.py` «`Pendiente` ya no existe», aserciones de ausencia de
      `/despacho`/`Pendiente`).
    - **Conteos.** Backend: **2163 passed, 127 skipped, 0 failed** (2158 + 5 del e2e; los 6
      gated de T38 siguen saltándose sin `POSTGRES_TEST_URL`). Frontend: `ng test` →
      **671 SUCCESS, 0 FAILED** (el refactor externo del frontend añadió pruebas; todas verdes).
      `ng build` → **Application bundle generation complete**.
    - **Alcance:** no se tocaron los archivos del refactor externo (`app/core/config.py`,
      `app/models/*`, `app/schemas/organizacion_schema.py`,
      `app/services/organizacion_service.py`), ni `database/`, `plan.md`, `spec.md`, `stack.md`,
      T43 ni T44.

- [x] **T43 — Documentación derivada: `stack.md` y notas de 005/007/004/018.**
  - Archivos: `docs/spec/stack.md` (sección del ciclo de vida de la 013, con el texto de la §10.7
    de la spec), `docs/spec/features/005-despacho-transaccional/spec.md` (nota: rename de ruta/DTO/
    servicio/observación y 409 del `PATCH`), `docs/spec/features/007-control-acceso-roles/spec.md`
    (nota: matriz 75 con `/retiro` y movimientos solo Bodeguero; espejo frontend),
    `docs/spec/features/004-tablero-kanban/spec.md` (nota: tres columnas y anulación del retiro),
    `docs/spec/features/018-filtro-inventario-sede-departamento/spec.md` (nota: el checkbox «Solo
    con stock» queda como enmienda separada, fuera de la 013).
  - Prueba/verificación: grep de coherencia sobre `docs/`, `AGENTS.md`, `MEMORY.md` y
    `.agents/skills/` sin afirmaciones vigentes sobre `Pendiente`, cinco filas, `Cerrado` terminal
    sin salida, `/despacho` ni los identificadores históricos del frontend (mapping de D-29),
    salvo notas históricas/de superación.
  - Implementación: aplicar el texto propuesto de `stack.md`; redactar las cuatro notas breves de
    enmienda enlazando a la §10 de la 013; la nota de la 007 deja constancia del espejo del
    frontend con `ROLES_RETIRO_TICKETS`/`puedeRegistrarRetiro`. No se toca `roadmap.md` ni se crea
    feature nueva.
  - **AC:** AC-67.
  - **Depende de:** T42.
  - **Hecho cuando:** `stack.md` describe el catálogo de cuatro estados, el retiro y la anulación
    con bloqueo por confirmación; las notas existen y el grep no deja contradicciones vigentes.
    **[docs]**
  - **Nota de fase (T43 ejecutada el 27/Nov/2026).** Se actualizó la documentación derivada de la
    enmienda sin tocar código, `database/`, `plan.md`, `spec.md` de la 013, `roadmap.md` ni los
    archivos del refactor externo (los cambios externos de `stack.md` de las 03:33 se conservaron;
    la enmienda de la 012 en borrador que propone 25/22/`026.1` queda anotada como posterior y no
    se revirtió).
    - **`docs/spec/stack.md`:** la sección de la 013 gana los párrafos **«Enmienda 26/Nov/2026
      (catálogo de cuatro estados y retiro)»** y **«Superación (26/Nov/2026)»** con el texto de la
      §10.7: cuatro filas (`EnRevision`, `EnCurso`, `Cerrado`, `Anulado`) y alta en `EnRevision`;
      retiro solo Bodeguero de la sede con `SALIDA`, `cantidad_entregada`, `fecha_cierre` e
      historial; `Cerrado → Anulado` solo Administrador, con `ENTRADA` por detalle, reset y fecha
      nula, **bloqueada por la confirmación**; confirmación `Cerrado → Cerrado` final; `Anulado`
      terminal y `Cerrado` con esa única salida; movimientos manuales solo Bodeguero; sin DDL
      (26/23, 21 entidades, `026.0`, con la 012 en borrador como cambio posterior) y la 021 sin
      estado «recibido». Se corrigieron además cuatro menciones **vigentes** fuera de esa sección:
      el nombre del estado inicial en la regla de orden del catálogo, y «despacho» → «retiro» en
      las secciones de sede, compras/021 y auditoría de recepción. Las menciones históricas de la
      sección (05/Nov, «quinta fila», terminalidad de `Cerrado`, `/despacho`, «Despachado») se
      conservan con la nota de superación.
    - **Notas de enmienda (breves, enlazadas a `../013-ciclo-vida-ticket/spec.md` §10):**
      - **005/spec.md:** rename a `/retiro`, `TicketRetiro`, `registrar_retiro_ticket`,
        observación «Salida por retiro…», actor Bodeguero de la sede y `Cerrado` con salida
        administrativa; filas/AC y detalle 409 históricos marcados como superados; «despacho
        transaccional» se conserva como nombre histórico.
      - **007/spec.md:** matriz **75** con `/retiro` `{Bodeguero}` y movimientos `{Bodeguero}`;
        `/anulacion` conserva `{Administrador, Solicitante}`; espejo `ROLES_RETIRO_TICKETS`/
        `puedeRegistrarRetiro`; filas históricas de despacho/movimientos superadas.
      - **004/spec.md:** tres columnas (`EnRevision`, `EnCurso`, «Terminados» con `Cerrado` +
        `Anulado`), sin `Pendiente` ni `Anulado` separada; `Cerrado` por retiro y salida
        administrativa bloqueada por la confirmación; columnas/AC históricos superados por AC-62.
      - **018/spec.md:** el checkbox «Solo con stock» queda como **enmienda separada**, fuera de la
        013 y pendiente después de T44; sin ACs ejecutables nuevos.
    - **Grep de coherencia:** sin contradicciones vigentes en los archivos de T43. Pendientes para
      el coordinador/T44 (no editados aquí): `MEMORY.md:30` («`Cerrado` sigue siendo el despacho»)
      y `MEMORY.md:12/47` (013 cerrada el 25/Nov sin la enmienda del 26/Nov); `roadmap.md:92`
      (fila de la 013 con `Pendiente`, matriz 49 y `013.1`; roadmap no se toca) y menciones
      históricas de `/despacho` en `docs/diagramas/flujos-actores/README.md:18,71` y
      `008-particionamiento-institucional/spec.md` (AC-9/AC-16 y evidencia). `AGENTS.md` y
      `.agents/skills/` no contienen los patrones del grep.

- [x] **T44 — Cierre: suites, build, 4200/8080, evidencia y grep.**
  - Archivos: `spec.md` (evidencia bajo AC-50…AC-68), `evidencia/README.md` (§11),
    `MEMORY.md`/`AGENTS.md` y skills si el grep lo exige (coordinador); `roadmap.md` no se toca.
  - Ejecutar `pytest` SQLite completo, gated PG (`POSTGRES_TEST_URL`), `ng test`, `ng build`,
    inspeccionar `/openapi.json` (75 v1/77) y `MATRIZ_PERMISOS` (75, `/retiro` solo Bodeguero,
    movimientos solo Bodeguero); recorrer 4200 con escritura real (alta en `EnRevision`, aprobar,
    retirar, confirmar; anular antes de confirmar con devolución y 409 después; tablero de 3
    columnas y detalle) y 8080 tras `docker compose -f docker-compose.yml build frontend` +
    `up -d frontend`; grep de coherencia (`Pendiente`, `/despacho`, `Despachado`, cinco estados,
    4 columnas, 26/23, 75/77, identificadores históricos del frontend de D-29).
  - **AC:** AC-50…AC-68 y «Cierre» de la §10.
  - **Depende de:** T38, T40, T41, T43.
  - **Hecho cuando:** todas las suites y el build están en verde, 4200/8080 verificados, cada AC
    con su evidencia y el grep sin afirmaciones obsoletas; `MEMORY.md` actualizado por el
    coordinador. **[SQLite + PostgreSQL gated + ng test + build + puertos]**
  - **Nota de fase (T44 ejecutada el 27/Nov/2026).** Cierre verificado. **Suites:** SQLite
    **2163 passed / 127 skipped / 0 failed** (9:10); gated PostgreSQL 16 **2287 passed / 3
    skipped / 0 failed** (29:05, bases desechables, `apt_erp` intacta); `ng test` **671 SUCCESS /
    0 FAILED**; `ng build` limpio (`main-IRJLFDU6.js`, Initial 339.98 kB). **Contrato vivo:**
    `/openapi.json` **72 v1 / 74 entradas** y `MATRIZ_PERMISOS` **72**; `/retiro` solo
    `{Bodeguero}` (capacidad `kanban`), movimientos solo `{Bodeguero}`, `/anulacion`
    `{Administrador, Solicitante}`, `PATCH` `{Administrador}` y `/despacho` ausente. **Delta
    externo de la 012 (27/Nov):** 72/74, 25/22 y `026.1`; la línea base de la 013 era 75/77,
    26/23 y `026.0`, y esta enmienda no cambia la cardinalidad ni el DDL (una clave renombrada).
    **Reset QA:** `down -v` + `up -d`; token `026.1`; 25/22 tablas; catálogo de 4 estados;
    INST-001 #1–#4 `EnRevision`, #5–#6 `EnCurso`, #7–#8 `Cerrado`; INST-002 #9 `EnRevision`, #10
    `Cerrado`; ningún `Anulado`; `Cerrado` con fecha y cantidad. **4200:** alta #9–#11 en
    `EnRevision`, aprobación, retiro de #9/#10, anulación del retiro de #9 con `ENTRADA` y stock
    42→45, confirmación de #10 y **409** posterior, tablero 4/3/4 y «Pedidos Activos» 7; SQL con
    `SALIDA`/`ENTRADA` literales e historial; capturas `40-01`…`40-17`. **8080:** imagen
    reconstruida (`sha256:8c7ca2…`), `up -d` no recreó el contenedor y hizo falta
    `--force-recreate`; sirve `main-IRJLFDU6.js`; tablero 4/3/4 y detalles «Entregado»/«Rechazado»;
    capturas `40-18`…`40-20`. **Evidencia:** `spec.md` §10.10 con AC-50…AC-68 marcados y evidencia
    por AC; `evidencia/README.md` §11; `MEMORY.md` actualizado (013, suites 2287, `--force-recreate`
    y siguiente 018). **Grep:** 0 afirmaciones vigentes de `Pendiente`, `/despacho`, `Despachado`,
    «cinco estados», «cuatro columnas», `75/77` o `026.0` en `AGENTS.md`, `MEMORY.md`, `stack.md`
    y skills (solo notas históricas/de superación); el código activo no conserva los
    identificadores de D-29 (solo comentarios/negativas históricas). **Pendiente externo (no
    editado):** `roadmap.md:92` (fila histórica con `Pendiente`, matriz 49 y `013.1`), menciones
    históricas de `/despacho` en `docs/diagramas/flujos-actores/README.md:18,71` y
    `008.../spec.md`, y el copy «despache/despachará» de `ticket_proceso.py` (observación menor,
    fuera de AC). **Datos QA residuales:** #9 `Anulado`, #10 `Cerrado`/«Entregado», #11 `EnCurso`,
    stock 42; la base se deja con el recorrido (reset disponible con `down -v` + `up -d`).
  - **Nota de corrección post-validación (27/Nov/2026).** El reviewer detectó menciones
    vigentes a `/despacho` y `Pendiente` en diagramas e informes. Se corrigió: `06` y `07`
    actualizados (texto y PNG), `10`/`11` y textos genéricos de `04`/`08`/`09` regenerados;
    `README` de flujos actualizado; `03-secuencia` y `01-actividad` (4+1) marcados con banner
    histórico y el índice 4+1 con «histórico»; `02-clases` actualizó el colofón;
    `_generar_informe.py` e `Informe_Flujos_Actores.docx` regenerados;
    `_generar_planilla_pruebas.py` con etiquetas de retiro. Se añadió la línea de línea base
    (75/77, 26/23 y `026.0`) vs vigente (72/74, 25/22 y `026.1`) en AC-50/55/64/68; notas
    en 007 y 008. Grep ampliado a `docs/diagramas/` y `docs/informes/`: solo coincidencias
    históricas con banner (03/01) y slugs de archivo. `pytest` SQLite: **2163 passed / 127
    skipped / 0 failed** (13:04).
