# Feature 013 — Evidencia del recorrido funcional (T13)

Recorrido funcional contra el backend en contenedor (`uvicorn --reload`, volumen
`./backend/app`) y PostgreSQL **real** (`compustock_db` / `apt_erp`, puerto local
5433, usuario `postgres`), verificando **cada efecto con SQL por `docker exec
psql`**. El frontend se verificó en el dev server **4200** (`npm start`); el
recorrido de humo en **8080** (rebuild de la imagen) quedó documentado en §8.

> **Sin capturas de pantalla:** el recorrido se operó contra la API con tokens
> Clerk reales (no a través de la UI), y cada resultado quedó acreditado con la
> respuesta HTTP literal y con las consultas SQL transcritas en esta evidencia.
> La verificación de la UI en 4200 se limitó al arranque del dev server, al
> serve del shell SPA y a los chunks lazy (T14/T15 hacen el resto).

## 1. Estado inicial de la base

Verificado antes de la primera escritura del recorrido (19/Oct/2026, ~04:55):

| Hecho | Valor observado (SQL/HTTP) |
|---|---|
| Respaldo previo | `respaldos/apt_erp_pre_013.dump` (275.966 bytes, 19/Oct 00:21) |
| Versión de control | `control.version_esquema = '013.1'` (fila única, 19/Oct 03:22) |
| `Anulado` en catálogo de control | `control.estado_ticket = (1, 'Anulado')` — solo esa fila, como es post-004 |
| Catálogo del tenant INST-001 | `tenant_inst_001_038aa2a9.estado_ticket` = Pendiente(1), EnRevision(2), EnCurso(3), Cerrado(4), **Anulado(5)** |
| Historial al iniciar | `control.historial_transicion_ticket` = **0 filas**; `tenant_inst_001_…historial_transicion_ticket` = **0 filas** |
| Backend sirve el código 013 | `GET /openapi.json` = **49 operaciones** bajo `/api/v1/` con las 5 nuevas (ver §6) |
| Frontend 4200 | `npm start` compiló (initial 150,81 kB; lazy `ticket-detalle-component` 61,69 kB y `tickets-component` 48,11 kB); `GET /` y `GET /tickets` = **200** con el shell SPA (`app-root`). Detenido al cerrar (`Get-Process node | Stop-Process`; 4200 deja de responder) |

## 2. Cuentas usadas

Sesiones Clerk **reales** de la instancia dev `relevant-termite-8089` (emitidas
por HTTP durante el recorrido; ningún secreto en esta evidencia). Todas las
cuentas locales de la semilla **sí tienen usuario en Clerk con correo primario
verificado** (verificado vía Backend API `GET /v1/users`), por lo que **no se
usaron contrapartes `+clerk_test` salvo para Superadmin**:

| Cuenta Clerk | Rol efectivo (BD real) | Uso en el recorrido |
|---|---|---|
| `diego.munoz@losalpes.cl` | **Solicitante** (usuario_id 2, depto Secretaria → sede 2) | alta, anulación propia, edición, lecturas |
| `andres.vargas@losalpes.cl` | **Bodeguero** (usuario_id 6, sede 2) | rechazo, PATCH `/estado`, despacho |
| `valentina.reyes@losalpes.cl` | **Administrador** (usuario_id 3) | 409s de estado sobre tickets ajenos de la institución |
| `superadmin.test+clerk_test@example.com` | Superadmin (identidad de control) | 403 en escrituras; lectura global de detalle/historial |

> **Hallazgo de entorno (no es defecto):** el enunciado de la tarea describía
> `valentina.reyes` como Solicitante y `diego.munoz` como Administrador; en la
> BD real es al revés (tabla `rol`: 2=Administrador, 3=Bodeguero, 4=Solicitante;
> Valentina rol_id 2, Diego rol_id 4). El recorrido usó los roles reales.

### Cuentas QA en la semilla (posterior al cierre, para el equipo)

Para que cualquier clon pruebe el circuito completo de la 013 sin crear
usuarios a mano, la semilla `database/02_datos_semilla.sql` siembra dos
usuarios locales adicionales de INST-001, en el departamento 6 (Biblioteca →
Sede 2, la misma que opera el Bodeguero, de modo que el ticket emitido se
despacha desde su sede):

| id | Cuenta Clerk (`+clerk_test`, código `424242`) | Rol | Para probar |
|---|---|---|---|
| 11 | `solicitante.test+clerk_test@example.com` (Paula Rojas) | Solicitante | emitir, anular el propio, 404 en ajenos |
| 12 | `bodeguero.test+clerk_test@example.com` (Roberto Díaz, sede 2) | Bodeguero | rechazar con motivo, despachar |

Verificado con la cadena real de initdb (`01 → 02 → 03`) en una base
desechable: los 12 usuarios llegan al tenant, `mapa_usuario_esquema` resuelve
ambos correos, `departamento_encargado` asocia el departamento 6 a Paula y el
catálogo de estados trae `Anulado` con historial vacío (AC-12). Las cuentas
`@losalpes.cl` de la tabla anterior también siguen valiendo (rol por
departamento) y son útiles para el Administrador (`valentina.reyes`).

### Cómo se obtuvieron los tokens (para reproducibilidad)

El flujo pedido (`signIn.create → prepareFirstFactor → attemptFirstFactor` con
código `424242`) **ya no es ejecutable sin navegador**: el Frontend API con
`Authorization: Basic <pk:>` es *stateless* por request (cada llamada crea un
client nuevo y el sign-in queda huérfano: `signed_out`), y con el código fijo
responde `form_code_incorrect`. Se usó el flujo equivalente documentado de
testing de Clerk, **sin secretos hardcodeados** (todo leído de `.env`):

1. `POST /v1/dev_browser` (FAPI, con `Origin: http://localhost:4200`) → dev
   browser token, usado como query param `__dev_session` (el FAPI de instancias
   dev lo exige; con cookies o sin él responde `dev_browser_unauthenticated`).
2. `POST /v1/sign_in_tokens` (Backend API, secret key) → *sign-in ticket* para
   el `user_id` de la cuenta.
3. `POST /v1/client/sign_ins` + `attempt_first_factor` con
   `strategy=ticket&ticket=…` (FAPI, `Origin: localhost:4200`) → sesión completa.
4. `client.sessions[0].last_active_token.jwt` → token de sesión.

El `Origin: http://localhost:4200` es imprescindible: el backend exige
`azp ∈ {http://localhost:4200, http://localhost:8080}` (`security.py`
`AZP_PERMITIDOS`); un token minteado sin ese origen (p. ej.
`POST /v1/sessions/{id}/tokens` de la Backend API, que no lleva `azp`) recibe
**401**. Cada token de sesión vive ~60 s, así que se emitió uno nuevo por
petición. Ningún usuario fue creado ni modificado en Clerk.

## 3. Recorrido (acción → resultado HTTP + valores SQL reales)

Todos contra `http://localhost:8000/api/v1` con `Authorization: Bearer <token>`
y SQL posterior por psql sobre `tenant_inst_001_038aa2a9` salvo indicación.

### 3.1 Ciclo feliz (Solicitante + Bodeguero)

| # | Acción | Resultado HTTP (real) | Verificación SQL (real) | AC |
|---|---|---|---|---|
| 1 | `POST /tickets/` como Diego (Solicitante), estado inicial 1, producto 4 (Folder Manila) ×5 | **201** `ticket_id=13`, `estado_id=1`, `sede_id=2` (snapshot del depto Secretaria), `usuario_id=2` (atribuido al dueño aunque el payload trajera otro) | fila creada con sus detalles; historial: **1 fila** `(id=1, origen=NULL, destino=1 Pendiente, usuario_id=2, motivo=NULL, 04:57:41)` | AC-9 |
| 2 | `POST /tickets/13/anulacion` como Diego con motivo `"Se anula por duplicado con la solicitud S-0042"` | **200**, `estado_id=5` | `ticket 13 = Anulado, fecha_cierre = NULL`; historial fila `(id=2, 1→5, usuario 2, motivo literal completo)`; `stock_sede (2,4) = 200` **intacto**; `movimiento_inventario` sigue en **21** (0 salidas nuevas) | AC-1, AC-6 |
| 3 | `GET /tickets/13` como Diego | **200** con campos poblados: `estado_nombre:"Anulado"`, `prioridad_nombre:"Alta"`, `solicitante_id:2`, `solicitante_nombre:"Diego"`, `solicitante_apellido:"Munoz"`, `solicitante_correo`, `departamento_nombre:"Secretaria"`, `sede_nombre:"Sede 2"`, detalle con `producto.categoria` | — | AC-10, AC-19 |
| 4 | `GET /tickets/13/historial` como Diego | **200**, 2 filas en orden `fecha_transicion DESC, id DESC`: primero la anulación (con `estado_origen_nombre:"Pendiente"`, `estado_destino_nombre:"Anulado"`, `usuario_nombre:"Diego"`, `usuario_apellido:"Munoz"`, motivo literal), después la creación (origen nulo) | coincide 1:1 con las 2 filas SQL | AC-9, AC-10, AC-19 |
| 5 | `POST /tickets/` como Diego → `ticket_id=14` (2 ítems: producto 1 ×10, producto 8 ×3) | **201** | — | AC-13 (prep.) |
| 6 | `PUT /tickets/14` como Diego con payload nuevo: asunto/descripción distintos, `prioridad_id=3`, ítems **completamente distintos** (producto 2 ×7, producto 5 ×2) | **200** con `prioridad_id=3` y los 2 detalles nuevos | cabecera: asunto/descripción/prioridad actualizados; `usuario_id=2`, `estado_id=1`, `sede_id=2` **intactos**; `detalle_ticket` del ticket = solo ids 16 y 17 (los previos 14–15 **borrados**); historial del ticket sigue en **1** fila (editar no muta estado) | AC-13 |
| 7 | `POST /tickets/14/rechazo` como **Andrés (Bodeguero)** con motivo `"Sin stock disponible en la sede para la fecha solicitada"` | **200**, `estado_id=5` | `ticket 14 = Anulado, fecha_cierre = NULL`; historial añade `(id=4, 1→5, usuario_id=6 Andres, motivo literal)` | AC-3, AC-6 |

### 3.2 Regresión de la Feature 005 (despacho transaccional)

| # | Acción | Resultado HTTP (real) | Verificación SQL (real) | AC |
|---|---|---|---|---|
| 8 | `POST /tickets/` como Diego → `ticket_id=15` (producto 6 Clip Métrico ×3, sede 2) | **201** | historial: creación origen nulo | AC-9 |
| 9 | `PATCH /tickets/15/estado` 1→2 y 2→3 como Andrés (Bodeguero) | **200**, **200** (`estado_id=3` EnCurso) | historial suma exactamente 1 fila por mutación (ids 6 y 7) | AC-9 |
| 10 | `PATCH /tickets/15/estado` hacia `Cerrado` (4) | **409** literal `El cierre requiere despacho; use POST /api/v1/tickets/15/despacho` | sin cambios (ticket sigue EnCurso, sin filas nuevas) | AC-5, AC-26 |
| 11 | `POST /tickets/15/despacho` como Andrés con `usuario_id=6` | **200**, `estado_id=4`, **`fecha_cierre=2026-10-19T05:04:14`**, `cantidad_entregada=3` | `stock_sede (2,6): 35 → 32` (rebajo exacto de 3); movimiento **id=22** `SALIDA, cantidad=3, stock_sede_id=5, observacion='Despacho ticket_id=15; detalle_id=18; producto_id=6'`; historial añade `(id=8, 3→4 EnCurso→Cerrado, usuario 6)` | AC-5, AC-6, AC-9 |

### 3.3 Rechazos y guardingas (todos verificados sin efectos colaterales)

| # | Acción | Resultado HTTP (real) | AC |
|---|---|---|---|
| 12 | `POST /tickets/5/anulacion` (ticket de Isabel, **EnCurso**) como Valentina (Admin) | **409** `El estado actual no admite anulacion ni rechazo: solo se admiten 'Pendiente' o 'EnRevision'` | AC-2 |
| 13 | `POST /tickets/6/anulacion` (ticket **Cerrado**) como Admin | **409** ídem | AC-2 |
| 14 | `POST /tickets/13/anulacion` (ticket **ya Anulado**) como dueño | **409** `El ticket ya esta en 'Anulado'` | AC-2 |
| 15 | `POST /tickets/5/rechazo` (EnCurso) como Bodeguero | **409** (mismo literal de estado) | AC-3 |
| 16 | `PATCH /tickets/1/estado` **hacia** `Anulado` (id 5) | **409** `El estado 'Anulado' solo se alcanza por anulacion o rechazo; use POST /api/v1/tickets/1/anulacion o POST /api/v1/tickets/1/rechazo` | AC-4 |
| 17 | `PATCH /tickets/13/estado` **desde** `Anulado` | **409** `El ticket esta en 'Anulado', estado terminal del que ninguna operacion lo saca; …` | AC-4 |
| 18 | `POST /tickets/99999/anulacion` (inexistente) y `POST /tickets/2/anulacion` (ajeno: de Isabel) como Diego | ambos **404** con detalle **idéntico** `Ticket no encontrado` (sin revelar existencia) | AC-7, AC-18 |
| 19 | `POST /tickets/1/anulacion` con `motivo="   "` (solo espacios) | **422** `El motivo es obligatorio y no puede exceder 500 caracteres`; ticket 1 **sigue Pendiente** e historial sin filas nuevas (verificado por SQL) | AC-8 |
| 20 | `POST /tickets/` con `estado_id=5` (Anulado) | **409** `El estado 'Anulado' no es elegible para alta: un ticket nuevo no puede nacer anulado` | AC-4 (D-11) |
| 21 | `PUT /tickets/13` (edición sobre ticket **Anulado**) | **409** `La edicion solo se aplica a tickets en estado 'Pendiente'` | AC-14 |
| 22 | `POST /tickets/1/anulacion`, `POST /tickets/1/rechazo`, `PUT /tickets/1` como **Superadmin** | los tres **403** `Permiso insuficiente para la operacion` (matriz evaluada antes del recurso) | AC-17, AC-18 |
| 23 | `POST /tickets/1/rechazo` como **Diego (Solicitante)**: rol sin la operación | **403** `Permiso insuficiente para la operacion` (sin mirar el ticket, que es suyo) | AC-17, AC-18 |
| 24 | `GET /tickets/14` y `GET /tickets/14/historial` como **Superadmin** (ticket de INST-001) | **200** y **200** con presentación resuelta y alcance global (lector `leer_global_unico`), sin `DetachedInstanceError` | AC-19 |
| 25 | `GET /dashboard/` como Diego | **200** `kpi.tickets_activos = 3` — sus tickets anulados (13, 14) **no cuentan**: SQL por estado = Pendiente 3, EnRevision 2, EnCurso 1, **Anulado 2**, Cerrado 7; para Diego (alcance propio) sus activos son los tickets 1, 4 y 12 = 3 | AC-22 |

### 3.4 Integridad final (SQL de cierre, 19/Oct ~05:06)

```
tickets 13 y 14  = Anulado con fecha_cierre NULL
ticket 15        = Cerrado con fecha_cierre 2026-10-19 05:04:14
tickets 1, 2, 5, 6 (usados solo en rechazos 409/404/422) = INTACTOS (mismo estado que al inicio)
historial        = 8 filas (solo creaciones y transiciones reales del recorrido; ninguna inventada)
movimiento_inventario = 22 (solo +1: el despacho del ticket 15)
stock (2,4)=200 intacto (anulaciones no tocan stock); (2,6) 35→32 (solo el despacho)
```

## 4. Contrato OpenAPI (verificado contra el backend vivo)

`GET /openapi.json` en el contenedor: **49 operaciones** bajo `/api/v1/`. Las 5
de la 013 con sus códigos documentados:

| Operación | Códigos |
|---|---|
| `POST /tickets/{id}/anulacion` | 200, 401, 403, 404, 409, 422 |
| `POST /tickets/{id}/rechazo` | 200, 401, 403, 404, 409, 422 |
| `PUT /tickets/{id}` | 200, 401, 403, 404, 409, 422 |
| `GET /tickets/{id}` | 200, 401, 403, 404 |
| `GET /tickets/{id}/historial` | 200, 401, 403, 404 |

## 5. Mapeo AC-1…AC-26 → evidencia

Tests de la suite (T12: SQLite **952 passed / 68 skipped / 0 failed**; gated PG
**1020 passed / 0 failed**; `ng test` **323 SUCCESS**; ambos citados en T12 de
`tasks.md`) + recorrido real de esta evidencia (§3):

| AC | Evidencia |
|---|---|
| AC-1 anulación con motivo → 200, Anulado, fecha_cierre nula, stock/movs intactos, historial | test `test_ciclo_vida_flujo_013.py::test_anulacion_desde_pendiente…ac_1` (+`…desde_en_revision…ac_1`); recorrido §3.1 #2 (SQL: estado, fecha NULL, stock 200, movs 21, fila con motivo literal) |
| AC-2 409 desde EnCurso/Cerrado/Anulado sin efectos | test `…flujo_013.py::test_anulacion_desde_estado_inadmisible_responde_409_sin_efectos_ac_2`; recorrido §3.3 #12–#14 |
| AC-3 rechazo Bodeguero/Admin 200; 409 sin efectos | tests `…flujo_013.py::test_rechazo_por_bodeguero…ac_3`, `…por_administrador…ac_3`, `…desde_en_curso…409…ac_3`; recorrido §3.1 #7 y §3.3 #15 |
| AC-4 terminales por nombre: 409 hacia/desde Anulado | tests `…flujo_013.py::test_patch_estado_no_lleva_a_anulado…ac_4`, `…no_sale_de_anulado_ac_4`, `…alta_en_anulado…d11` + AC-26 (catálogos degenerados); recorrido §3.3 #16, #17, #20 |
| AC-5 `EnCurso→Cerrado` reservado al despacho; historial del despacho; Anulado no despachable | tests `…flujo_013.py::test_en_curso_a_cerrado_sigue_reservado_al_despacho_ac_5`, `…despacho_registra_su_transicion…ac_5`, `…despacho_de_un_anulado…409…ac_5`; recorrido §3.2 #10 (409 literal) y #11 |
| AC-6 `Cerrado` sella fecha; `Anulado` la deja nula y no escribe movimientos | tests `…flujo_013.py::test_alta_en_cerrado_sella_fecha_cierre_ac_6`, `…despacho_sella_fecha_cierre_ac_6`; recorrido §3.1 #2 (fecha NULL, movs intactos) y §3.2 #11 (fecha sellada) |
| AC-7 orden 404→409→422 | tests `…flujo_013.py::test_orden_404_ante_422…ac_7`, `…409_ante_422…ac_7`, `…422_de_motivo_invalido_no_modifica_nada_ac_7`, `…409_de_estado_inadmisible_con_motivo_valido_ac_7`; recorrido §3.3 #18 (404 idéntico), #12 (409), #19 (422 sin efectos) |
| AC-8 motivo obligatorio, no vacío, ≤500, literal | tests `…motivo_013.py` (4 tests AC-8: faltante/vacio/exceso/límite con literal persistido); recorrido §3.1 #2 y #7 (motivos literales en SQL), §3.3 #19 (422) |
| AC-9 una fila por mutación (creación origen nulo, cambio, despacho, anulación/rechazo) | tests `…historial_013.py::…creacion_con_origen_nulo_ac_9`, `…cambio_de_estado_suma_exactamente_una_fila_ac_9`, `…anulacion_y_rechazo_suman_exactamente_una_fila_ac_9`; recorrido §3.1 #1 (fila creación), #4, §3.2 #9 (1 fila/PATCH), #11 (fila despacho) |
| AC-10 historial solo lectura + orden determinista | tests `…historial_013.py::test_orden_mas_reciente_primero_con_desempate_por_id_ac_10`, `…no_expone_operaciones_de_escritura_ac_10`; recorrido §3.1 #4 (orden DESC con desempate por id) |
| AC-11 atomicidad estado+historial | tests `…historial_013.py::…persiste_estado_y_fila_juntos_ac_11`, `…si_la_fila_no_puede_registrarse_el_estado_no_cambia_ac_11` (inserción forzada a fallar) |
| AC-12 sin trazabilidad fabricada (legados con historial vacío) | tests `…historial_013.py::…legado_sin_transiciones_muestra_historial_vacio_ac_12`, `…anulacion_de_legado_no_inventa_fila_de_creacion_ac_12`; recorrido: los tickets 6–12 pre-013 siguen sin filas inventadas (el total de 8 filas corresponde solo al recorrido) |
| AC-13 edición en Pendiente: 200 con conjunto reemplazado, campos intactos | tests `…edicion_013.py::…reemplaza_cabecera_y_detalles_ac_13`, `…conserva_estado_solicitante_sede_e_institucion_ac_13`; recorrido §3.1 #6 (SQL: ids viejos borrados, cabecera nueva, estado/sede/solicitante intactos) |
| AC-14 409 fuera de Pendiente sin efectos | test `…edicion_013.py::test_edicion_fuera_de_pendiente_responde_409_sin_efectos_ac_14`; recorrido §3.3 #21 |
| AC-15 validación total antes de escribir (404/422 sin escritura parcial) | 5 tests `…edicion_013.py::…ac_15` (prioridad/producto inexistente, producto ajeno, cantidad no positiva, detalles vacíos) |
| AC-16 Bodeguero/Superadmin no editan (403); Solicitante solo los suyos; ajeno = 404 idéntico | tests `…edicion_013.py::test_bodeguero_y_superadmin_no_pueden_editar_ac_16`, `…solicitante_no_edita_ticket_ajeno…identico_ac_16`, `…administrador_de_otra_institucion…404_ocultado…ac_16`, `…administrador_edita_tickets_de_su_institucion_ac_16` |
| AC-17 matriz exacta (5 filas aditivas), Superadmin sin escritura, 49 operaciones | tests `…autorizacion_013.py` (matriz/OpenAPI/gating: 12 tests ac_17 incl. capacidades apagadas); contrato vivo §4 |
| AC-18 403 por matriz antes del recurso; 404 idéntico sin revelar existencia | tests `…autorizacion_013.py::…operar_ticket_ajeno_responde_404_identico_ac_18`, `…leer_ajeno_responde_404_identico_ac_18`; recorrido §3.3 #18 (detalle idéntico), #22, #23 (403 sin mirar el recurso) |
| AC-19 los 4 roles leen con su alcance; Superadmin global sin escritura | tests `…autorizacion_013.py::…superadmin_lee_detalle_e_historial_ac_19`, `…solicitante_lee_su_detalle_y_no_el_ajeno_ac_19`, `…administrador_y_bodeguero_leen…ac_19`; recorrido §3.1 #3–#4 (Solicitante), §3.3 #24 (Superadmin global 200) |
| AC-20 instalación nueva con `Anulado`; migración idempotente a 013.1 | gated `test_ciclo_vida_ticket_postgres_013.py` (7/7: cadena 01→02→03+mig 004, idempotencia, preflight); estado real de la base §1 (versión 013.1, catálogo completo, respaldo previo) |
| AC-21 solo enrutan tenants en 013.1 con `Anulado` | gated `test_ciclo_vida_ticket_postgres_013.py` (tenant en 012.1 deniega cerrado; en 013.1 enruta); §1 (el recorrido entero operó sobre tenant enrutado en 013.1) |
| AC-22 KPI excluye `Cerrado`/`Anulado` por nombre | tests `…dashboard_013.py` (3 tests ac_22); recorrido §3.3 #25 (tickets_activos=3 para Diego; sus 2 anulados fuera del conteo, contrastado con SQL por estado) |
| AC-23 vista de detalle: cabecera, ítems, historial, estados vacíos y errores visibles | `frontend/.../ticket-detalle.component.spec.ts` (27 specs, `ng test` 323 SUCCESS en T12); dev server 4200 sirvió el chunk lazy `ticket-detalle-component` (§1) |
| AC-24 toda mutación desde el detalle; tablero solo lectura con «Gestionar» y columna Anulado; errores accesibles sin doble envío | `ticket-detalle.component.spec.ts` + `tickets.component.spec.ts` (T11: sin controles de mutación, «Gestionar», columna Anulado, alta sin `Anulado`); 4200 sirvió `tickets-component` (§1) |
| AC-25 suites en verde y recorrido en 4200 con escritura real | T12 (`tasks.md`: SQLite 952/68/0, gated PG 1020/0, ng 323 SUCCESS, build limpio); 4200 §1; escritura real §3 (tickets 13–15 persistidos) |
| AC-26 terminalidad por nombre en cualquier catálogo | tests `…flujo_013.py::test_catalogo_degenerado_sin_salida_desde_cerrado_ac_26`, `…desde_anulado_ac_26`, `…reentrada_en_cerrado…ac_26`, `…ticket_despachado_no_vuelve…ac_26`; recorrido §3.3 #10, #16, #17 (catálogo canónico) |

## 6. Datos de prueba residuales (QA real, sin borrado)

Creados por el recorrido en `apt_erp` (esquema `tenant_inst_001_038aa2a9`):

- **Tickets nuevos: 13** (`T13 recorrido: anulable`, Anulado, dueño Diego),
  **14** (`T13 recorrido: editado con exito`, editado y rechazado → Anulado,
  dueño Diego), **15** (`T13 regresion 005: despacho`, Cerrado con despacho
  auditado, dueño Diego).
- **Historial:** 8 filas (ids 1–8) repartidas en esos 3 tickets.
- **Movimiento de inventario:** id 22 (SALIDA ×3, producto 6, sede 2) por el
  despacho del ticket 15.
- **Stock:** `stock_sede (sede 2, producto 6)` quedó en 32 (rebajo legítimo del
  despacho); el resto intacto.
- Residuos de una sesión previa interrumpida (no tocados): tickets **11**
  (`T13 recorrido 4200`, Cerrado) y **12** (`T13 ticket futuro`, Pendiente).
- Los tickets de la semilla usados en rechazos (1, 2, 5, 6) quedaron
  **intactos** (los 409/404/422 no escriben).
- En Clerk **no se creó ni modificó ningún usuario**; las sesiones emitidas
  expiraron solas (~60 s).

## 7. Hallazgos para T14/T15

1. **El flujo HTTP de sign-in de Clerk ya no funciona sin navegador.** El
   Frontend API con Basic auth es stateless por request y el código fijo `424242`
   fue rechazado (`form_code_incorrect`); el flujo de *sign-in ticket* + dev
   browser (§2) es el sustituto válido para futuros recorridos por API. Para el
   humo de 8080/T14, la UI usa `clerk-js` en el navegador y no depende de esto.
2. **`security.py` exige `azp` de localhost:4200/8080.** Cualquier token no
   emitido con ese origen (p. ej. Backend API `POST /v1/sessions/{id}/tokens`)
   recibe 401; útil al documentar cualquier prueba automatizada futura.
3. **Roles de la semilla ≠ enunciado de la tarea:** en la BD real
   `rol(2=Administrador, 3=Bodeguero, 4=Solicitante)`; Valentina Reyes es
   Administrador y Diego Munoz Solicitante. Las cuentas `+clerk_test` de la 012
   siguen vigentes para Superadmin e INST-002, pero para INST-001 las cuentas
   locales existen en Clerk con sus correos planos.
4. **Windows + PowerShell:** `curl.exe` dentro de PS conserva backslashes de
   escape (JSON malformado si se escapa con `\"`); usar archivos de body. Y
   `ForEach-Object` sobre salidas de curl disparó un falso positivo del
   antivirus de Windows que bloqueó el script (usar acceso por índice).

## 8. 8080 — humo (T14, 19/Oct/2026 ~05:23–05:46 UTC)

Rebuild de la imagen (AGENTS §5/§8.6: sin esto el 8080 sirve un build congelado
y la evidencia sería falsa):

| Paso | Resultado |
|---|---|
| `docker compose -f docker-compose.yml build frontend` | **sin errores**; `ng build` dentro del builder: **55,55 s**; capa del builder `DONE 63,1 s`; export de la imagen 1,1 s. Re-ejecución de control (todo en caché): **exit 0**, mismo digest de manifiesto `sha256:1acf53e1d8b7b55df46c9886dd23459c242f2d87d666f463ef88ba17ef6aa123` |
| `docker compose -f docker-compose.yml up -d frontend` | contenedor `compustock_frontend` **recreado** y **healthy** (`Up … (healthy)`, 0.0.0.0:8080->80/tcp); imagen en uso `sha256:1b8351b1468c…` = `evidenciasproyecto-frontend:latest` |

### 8.1 Bundle nuevo y humo del shell

| Verificación (HTTP contra `http://localhost:8080`) | Resultado real |
|---|---|
| `GET /` | **200**, shell SPA (`<app-root>`, 2.554 B) que referencia **`main-R6LIXDWJ.js`** (9.234 B) y `styles-2W3BHTMI.css`, con modulepreload de `chunk-PEC22F4L/YI56XUUK/EPU4OVNG/CWKE7X32/BCOWUETH/GMZLEGE6/WYQAXJ3U` |
| `GET /tickets` y `GET /tickets/13` (`try_files` de nginx) | **200** con el **mismo shell** (deep-link Angular resuelto por `try_files $uri $uri/ /index.html`) |
| Bundle anterior | `GET /main-6C2R7UG2.js` → **404** (el HTML previo al rebuild apuntaba a `main-6C2R7UG2.js` + `styles-4S7CHXBN.css`: **tanto el CSS como todos los chunks cambiaron de hash**) |
| Cacheo con hash | `HEAD /main-R6LIXDWJ.js` → `Cache-Control: max-age=31536000,public, immutable`, `Last-Modified: 19/Oct 05:23:56 GMT`, `nginx/1.31.7` |

### 8.2 Chunks de la 013 presentes y referenciados

- `GET /chunk-URBQGDLO.js` (el mapa de rutas perezosas que consume el bundle)
  sirve, **por HTTP**, el cableado de la feature:

  ```js
  var e=[{path:"",loadComponent:()=>import("./chunk-GGSHOG7T.js").then(t=>t.TicketsComponent),title:"Tickets y Kanban | CompuStock"},
         {path:":ticketId",loadComponent:()=>import("./chunk-FYJSV5V5.js").then(t=>t.TicketDetalleComponent),title:"Detalle del ticket | CompuStock"}];
  ```

- Búsqueda de marcadores en los `.js` **servidos** (`docker exec … grep -r`,
  BusyBox sin `--include`):

  | Marcador (literal del template) | Chunk servido | Tamaño |
  |---|---|---|
  | `Gestionar` (acción única de la tarjeta del tablero, T11) | `chunk-GGSHOG7T.js` = `TicketsComponent` | 20.523 B |
  | `Historial de transiciones` y `Avanzar un paso en el flujo` (vista de detalle, T10) | `chunk-FYJSV5V5.js` = `TicketDetalleComponent` | 28.509 B |

  Los tamaños coinciden con los chunks que reportó `ng build` en T12
  (`tickets-component` 20,52 kB y `ticket-detalle-component` 28,51 kB).

> **Nota sobre la imagen previa:** la evidencia de la 012 cita el bundle
> `main-GAEBNACE.js`, pero la imagen pre-T14 servía `main-6C2R7UG2.js` (hubo un
> rebuild intermedio no documentado). La imagen previa ya no existe (no quedan
> imágenes colgantes tras el `up -d`), por lo que no pudo inspeccionarse; el
> cambio de hash del **CSS** y de **todos** los chunks indica que compilaba
> fuentes distintas a las actuales (los templates de la 013 alteran las clases
> Tailwind, de donde sale el hash del CSS).

### 8.3 API a través del proxy de nginx (`/api/` → `backend:8000`)

| Verificación | Resultado real |
|---|---|
| `GET :8080/api/v1/openapi.json` | **404** — hallazgo: `frontend/nginx.conf` solo proxya `/api/` y FastAPI publica el OpenAPI en la **raíz** (`/openapi.json`, `main.py` sin `root_path`), así que el documento **no es accesible desde 8080** (en `:8080/openapi.json` y `:8080/health` nginx cae al shell SPA por `try_files`) |
| Contrato en el mismo backend vivo que proxya 8080 (`GET :8000/openapi.json`) | **49 operaciones** bajo `/api/v1/` (51 totales con `GET /` y `GET /health`); las 5 nuevas: `POST /tickets/{id}/anulacion`, `POST /tickets/{id}/rechazo`, `PUT /tickets/{id}` → 200,401,403,404,409,422; `GET /tickets/{id}` y `GET /tickets/{id}/historial` → 200,401,403,404,422 |
| `GET :8080/api/v1/tickets/13` **sin token** | **401** (autorización intacta tras el proxy) |
| `GET :8080/api/v1/auth/me` con token Clerk real | **200**, `usuario_id=2` Diego Munoz (Solicitante) |
| `GET :8080/api/v1/tickets/13` con token | **200** con presentación poblada: `estado_nombre:"Anulado"`, `prioridad_nombre:"Alta"`, `solicitante_id:2`, `solicitante_nombre:"Diego"`, `solicitante_apellido:"Munoz"`, `solicitante_correo:"diego.munoz@losalpes.cl"`, `departamento_nombre:"Secretaria"`, `sede_nombre:"Sede 2"`, **`fecha_cierre:null`**, detalle con `producto.categoria` **eager** (`nombre_cat:"Organizacion"`), `cantidad_solicitada=5`, `cantidad_entregada=0` |
| `GET :8080/api/v1/tickets/13/historial` con token | **200**, 2 filas en orden `fecha_transicion DESC, id DESC`: (2) `Pendiente→Anulado` por Diego Munoz con el motivo literal `Se anula por duplicado con la solicitud S-0042`; (1) creación con **origen nulo** |
| `GET :8080/api/v1/tickets/` con token | **200**, 7 tickets (estados 4×2, 5×2, 1×2, 2×1) |

Tokens emitidos por HTTP con el flujo de §2 (caducan a los ~60 s; uno nuevo por
petición). **Aprendizaje nuevo del flujo** (para futuros recorridos): el campo
de la Backend API se llama **`token`** (no `ticket`), y los endpoints FAPI de
client (`/v1/client/sign_ins` y `/v1/client/sign_ins/{id}/attempt_first_factor`)
exigen parámetros **form-encoded**: con `application/json` responden
`form_param_missing` / dejan el intento en `needs_identifier`. Flujo que
funcionó: `dev_browser` → `sign_in_tokens` (BAPI) → `sign_ins` con
`identifier` → `attempt_first_factor` con `strategy=ticket&ticket=<token>` →
`client.sessions[0].last_active_token.jwt`.

### 8.4 Limitación de esta sesión y hallazgos para T15

- **Sin herramienta de navegador** en esta sesión: el humo se verificó por
  **HTTP + inspección del bundle servido** (shell, `try_files`, mapa de rutas,
  chunks de tablero y detalle, API por el proxy). **No se capturaron
  pantallazos** de la columna `Anulado` renderizada ni del clic en «Gestionar»;
  la evidencia visual funcional de la 013 vive en el recorrido 4200 (§3) y en
  los specs (`ng test` 323 SUCCESS, T12). El humo visual en 8080 queda pendiente
  de captura para T15/cierre.
- Hallazgos: (1) el OpenAPI no es accesible desde 8080 (solo `/api/` está
  proxyado); (2) la imagen pre-T14 no coincidía con el bundle citado en la
  evidencia 012 (rebuild intermedio no documentado; ya no inspeccionable);
  (3) el flujo HTTP de Clerk descrito en §2 necesita las correcciones de forma
  anotadas arriba; (4) en Windows, `docker exec … sh -c '…'` con `$()` y comillas
  anidadas se rompe (PowerShell) y BusyBox `grep` no admite `--include`: usar
  `grep -r` sobre el directorio.

## 9. Enmienda post-cierre (05/Nov/2026): alta fija en `Pendiente` y prioridad `Media`

**Regla:** todo ticket nuevo nace en `Pendiente`, resuelto por **nombre canónico**
(casefold, menor `estado_id` ante duplicados) y no por la posición del catálogo. `POST
/tickets/` conserva `estado_id` obligatorio y responde **409** si no es `Pendiente` o si
el catálogo no lo contiene, antes de escribir; ya no se admite nacer en `Cerrado` ni se
sella `fecha_cierre` en el alta (004 AC-17 derogado en esa cláusula). La prioridad
arranca en `Media` (también por nombre) y sigue editable. No se toca DDL, semilla,
migración, matriz ni permisos.

### 9.1 Backend y contrato

| Verificación | Resultado real |
|---|---|
| `tests/funcional/integracion/test_ciclo_vida_alta_inicial_013.py` | **9 passed** — 409 en `EnRevision`/`EnCurso`/`Cerrado`/`Anulado` sin dejar tickets; 404 con id inexistente (la referencia precede a la regla); 422 sin `estado_id`; 409 con catálogo sin `Pendiente`; 201 con `Pendiente` y `fecha_cierre: null`; el `PATCH /estado` posterior sigue en 200; `Pendiente` fuera de la primera posición también resuelve |
| `pytest` (SQLite, suite completa) | **1459 passed / 83 skipped / 0 failed** en 4:06 min |
| `pytest` gated PostgreSQL 16 (`POSTGRES_TEST_URL`, base desechable) | **1542 passed / 0 skipped / 0 failed** en 9:17 min; `apt_erp` intacta |
| Ajustes de regresión | `conftest.datos_base` renombra `INGRESADO`/`CERRADO` a `Pendiente`/`Cerrado`; `test_tablero_kanban.py` siembra por ORM los escenarios no-`Pendiente` y los dos casos de alta en `Cerrado` pasan a exigir **409**; `test_ciclo_vida_flujo_013.py` ídem; `test_ticket_sede_011.py` crea en `Pendiente` y transiciona con `PATCH`; `test_modal_ticket.py` afirma `Pendiente` como primer estado |
| `/openapi.json` (`:8000`, 61 operaciones) | La descripción de `POST /api/v1/tickets/` documenta el estado inicial fijo y el **409**; `TicketCrear.estado_id` describe la obligatoriedad de `Pendiente` y el 409 |
| OpenAPI del alta | `estado_id` sigue en el `requestBody` (contrato aditivo; no se retiró el campo) |

### 9.2 Frontend

| Verificación | Resultado real |
|---|---|
| `tickets.component.spec.ts` | **69/69** — estado de solo lectura (sin `dialog select[formcontrolname="estado_id"]`, sin «Editable»), `Pendiente`/«Fijo»/«no se puede cambiar», resolución por nombre en catálogo hostil, bloqueo y aviso sin `Pendiente`, `Media` seleccionada y habilitada, cambio a `Alta` reflejado en el POST y vuelta a los valores por defecto tras crear |
| `ng test` (Edge headless) | **524 SUCCESS / 0 failed** |
| `ng build` | limpio; bundle `main-BX5UQPQ3.js` |

### 9.3 Recorrido funcional en 4200 (escritura real)

- Modal de alta: `Prioridad` con **Media** seleccionada y habilitada; `Estado inicial`
  muestra **Pendiente** + etiqueta **FIJO** y la ayuda «Todo ticket nuevo nace en este
  estado; no se puede cambiar»; **no existe** `<select>` de estado.
- Alta real como `Admin QA020` (Solicitante de sesión), 1 ítem × 2: `POST
  /api/v1/tickets/` → **201**; la tarjeta **#11** aparece en la columna **Pendiente** y el
  modal se cierra y resetea a `Media` + `Pendiente` con el asunto vacío.
- Sin errores de consola ni peticiones fallidas en el flujo.

### 9.4 Humo en 8080 (imagen reconstruida)

- `docker compose build frontend` + `up -d frontend`; contenedor **healthy** y bundle
  servido **`main-BX5UQPQ3.js`** (el mismo del `ng build`).
- `/tickets` carga con la sesión de QA y 11 tarjetas; el modal muestra el estado fijo
  (`Pendiente`/`FIJO`, sin selector) y `Media` preseleccionada y habilitada; «Cancelar»
  cierra sin errores de consola.

## 10. Ampliación 25/Nov/2026 — cierre (T30): suites, contrato, recorrido 4200 con los dos caminos y humo 8080

Cierre de la §9 de la spec (AC-28…AC-49). Recorrido **real de UI** en `4200` con
sesiones Clerk de la semilla, capturas en esta carpeta y verificación SQL por
`docker exec psql` tras cada camino. Sin escritura en `apt_erp` fuera del
recorrido; los tests gated usan bases desechables.

### 10.1 Suites, gated y build

| Verificación | Comando | Resultado real |
|---|---|---|
| Backend SQLite (suite completa) | `cd backend; .venv\Scripts\python.exe -m pytest -q` | **1973 passed / 112 skipped / 0 failed** en 438,65 s (17 warnings de deprecación preexistentes) |
| Gated PostgreSQL 16 (módulo T23) | `$env:POSTGRES_TEST_URL="postgresql://postgres:postgres@localhost:5433/postgres"; pytest tests/funcional/sistema/test_ciclo_vida_aprobacion_confirmacion_postgres_013.py -q` | **3 passed** en 27,76 s — concurrencia de aprobación y confirmación con una sola fila; `apt_erp` intacta |
| Gated PostgreSQL 16 (suite completa) | misma variable; `pytest -q` | **2082 passed / 3 skipped / 0 failed** en 1080,12 s (18:00 min), sobre bases temporales desechables; los 3 `skipped` son los módulos gated de Redis, que exigen `REDIS_TEST_URL`; `apt_erp` intacta |
| Frontend | `$env:CHROME_BIN="C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"; npx ng test --watch=false --browsers=ChromeHeadless` | **TOTAL: 634 SUCCESS / 0 failed** (repetido tras el ajuste de JSDoc de `roles.ts`) |
| Build de producción | `cd frontend; npx ng build` | limpio en 44,39 s; **`main-JE7KG3Z2.js`**, `Initial total 339.74 kB` (94.03 kB transferidos); lazy `ticket-detalle-component` 39,09 kB y `tickets-component` 23,22 kB |

### 10.2 Contrato OpenAPI (backend vivo en `:8000`)

`GET /openapi.json`: **77 operaciones** (75 bajo `/api/v1/` + `GET /` + `GET /health`).

| Operación | Roles documentados | Códigos |
|---|---|---|
| `POST /api/v1/tickets/{ticket_id}/aprobacion` | solo Administrador (capacidad `kanban`) | 200, 401, 403, 404, 409, 422 |
| `POST /api/v1/tickets/{ticket_id}/confirmacion-entrega` | solo Solicitante dueño (capacidad `tickets`) | 200, 401, 403, 404, 409, 422 |
| `PATCH /api/v1/tickets/{ticket_id}/estado` | **solo Administrador** («contrato de legado»; la UI ya no lo invoca) | sin cambio de forma |
| `POST /api/v1/tickets/{ticket_id}/despacho` | Administrador/Bodeguero (sin cambios de la 005) | sin cambio |
| `POST /api/v1/tickets/{ticket_id}/rechazo` | Administrador/Bodeguero (sin cambios) | sin cambio |

La descripción del `PATCH` deja de anunciar un destino efectivo distinto del
solicitado y documenta el 409 del cierre reservado al despacho.

### 10.3 Recorrido funcional en 4200 (escritura real)

Backend en contenedor (`uvicorn --reload`, volumen `./backend/app`) + `npm start`
(4200). Sesiones Clerk reales por el flujo documentado en §2 (`dev_browser` +
*sign-in ticket* + `sign_ins` con `strategy=ticket`, `Origin: localhost:4200`),
esta vez completado **sobre el mismo dev browser del navegador** para que Clerk JS
adopte la sesión; tokens de API refrescados por petición y ningún secreto impreso.

Cuentas (semilla INST-001): `ri.nilo@duocuc.cl` (Solicitante, Biblioteca → Sede
Maipú), `crise.gonzalez@duocuc.cl` (Administrador, Dirección),
`lu.illanes@duocuc.cl` (Bodeguero, Biblioteca → Sede Maipú).

#### Camino A — con stock («Papel Premium A4», producto 10: stock 64, mínimo 10)

| # | Actor | Acción en la UI | Observado | Captura |
|---|---|---|---|---|
| 1 | Solicitante | «+ Crear pedido»: 3 × Papel Premium A4, prioridad Media, estado **FIJO Pendiente** | 201 y tarjeta **#11** en la columna **Pendiente**; etiqueta «En aprobación» y «Sin gestión registrada» en ambos responsables | [01](30-4200-01-tablero-pendiente-etiqueta.png) |
| 2 | Solicitante | Detalle `/tickets/11` | Estado canónico **Pendiente** + etiqueta **En aprobación** con su frase; acciones Editar/Anular; historial: creación (origen nulo) | [02](30-4200-02-detalle-pendiente-en-aprobacion.png) |
| 3 | Administrador | «Aprobar» | **En Curso** + etiqueta **En confirmación de stock local**, badge «Stock disponible — Listo para despacho», «Pedido aprobado.», Último Administrador = Gonzalez, Cristian; historial `Pendiente → En Curso` con motivo `Aprobación del pedido`; `fecha_cierre` nula (no se muestra «Cerrado») | [03](30-4200-03-aprobacion-en-confirmacion-stock.png) |
| 4 | Bodeguero | «Confirmar stock local y despachar» → diálogo sin motivo → «Confirmar despacho» | **Cerrado** + etiqueta **Despachado**, `fecha_cierre` 25/11 20:24, entregado 3/3, Último Bodeguero = Illanes, Luciano; historial `En Curso → Cerrado`; badge desaparece y la barra pasa a la nota terminal | [04](30-4200-04-despacho-cerrado-despachado.png) |
| 5 | Solicitante | «Confirmar entrega» → diálogo → «Confirmar entrega» | Etiqueta **Entregado**, «Entregado el Nov 25, 2026, 8:24:49 PM **por Nilo, Ricardo**», «Entrega confirmada.», el botón desaparece y el estado sigue **Cerrado**; historial `Cerrado → Cerrado` con motivo `Entrega confirmada por el solicitante` | [05](30-4200-05-entrega-confirmada-entregado.png) |
| 6 | Solicitante | Tablero | 4 columnas: **Pendiente**, **En Revisión** (heredado), **En Curso**, **Terminados**; #11 en «Terminados» con etiqueta **Entregado** y los dos responsables; sin columna `Anulado` ni botones Avanzar/Retroceder | [06](30-4200-06-tablero-terminados-entregado.png) |

#### Camino B — sin stock («Resma Carta 75g A4», producto 1: stock 0 en Sede Maipú, mínimo 20)

| # | Actor | Acción en la UI | Observado | Captura |
|---|---|---|---|---|
| 7 | Administrador | Compras (`/compras/necesidades`) **antes** de crear/aprobar el pedido | 4 filas; **no** aparece «Resma Carta 75g A4» de Sede Maipú (sin saldo ni demanda) y **tampoco** «Papel Premium A4» (caso #10: 61 > 10 y demanda 3 ≤ 61) | [07](30-4200-07-compras-sin-caso10-ni-resma.png) |
| 8 | Solicitante | Alta de **#12**: 3 × Resma Carta 75g A4 | Nace **Pendiente** (etiqueta «En aprobación» en el detalle) | — |
| 9 | Administrador | «Aprobar» #12 | **En Curso** + etiqueta **Por comprar** («no hay stock suficiente ni compra vigente»), sin acción de despacho (nota: el despacho se habilitará cuando la sede lo cubra) | [08](30-4200-08-aprobacion-por-comprar.png) |
| 10 | Administrador | Compras | Aparece la fila **Sede Maipú / Resma Carta 75g A4**: stock 0, mínimo 20, demanda 3, sugerido **23**, y el pedido **#12** dentro de «Pedidos que componen la demanda» | [09](30-4200-09-compras-necesidad-ticket12.png) |
| 11 | Administrador | «Crear OC» (precargada sede 2 / producto 1 / 23) → proveedor Papelera del Pacífico, precio 4.990 → creada → **Emitir** → **Facturar** `F-T30-0002` | **OC-2026-000002** Borrador → **Emitida** (1 asignación) → **Facturada** (factura F-T30-0002 · 25/11/2026) | [10](30-4200-10-oc-emitida-facturada.png) |
| 12 | Administrador | Detalle #12 tras facturar | Etiqueta **Facturado** («la compra está facturada y pendiente de recepción»), cobertura comprado 3/recibido 0 y la OC Facturada en «Órdenes de compra que cubren el pedido» | [11](30-4200-11-ticket12-facturado.png) |
| 13 | Bodeguero | Recepción de Compras → «Recepcionar» → «Confirmar recepción» | «Orden de compra recepcionada exitosamente.» y «Se desbloquearon 1 pedido(s): T30 sin stock: resma carta»; ya no quedan OC facturadas en la sede | [12](30-4200-12-recepcion-oc.png) |
| 14 | Bodeguero | Detalle #12 | Etiqueta **En confirmación de stock local**, badge de stock, acción de despacho; historial añade `En Curso → En Curso` con motivo `Desbloqueo por reabastecimiento: OC OC-2026-000002 / Factura F-T30-0002` y la nota «OC … desbloqueó el pedido» | [13](30-4200-13-ticket12-en-confirmacion-tras-recepcion.png) |
| 15 | Bodeguero | «Confirmar stock local y despachar» → confirmar | **Cerrado** + **Despachado**, `fecha_cierre` 25/11 20:28, entregado 3/3, historial `En Curso → Cerrado` | [14](30-4200-14-ticket12-despachado.png) |
| 16 | Solicitante | «Confirmar entrega» | **Entregado** + «Entregado el … por Nilo, Ricardo», estado canónico **Cerrado**, historial `Cerrado → Cerrado` | [15](30-4200-15-ticket12-entregado.png) |
| 17 | Solicitante | Tablero final | «Terminados» **2** (#11 y #12, ambas «Entregado»), #10 sigue en «En Curso» | [16](30-4200-16-tablero-final-terminados-2.png) |
| 18 | Administrador | Tablero con el heredado | Columna **En Revisión** con **3** pedidos heredados (#3, #4, #9); #9 «En revisión» con su frase; en el detalle ofrece Aprobar/Rechazar/Anular y no Editar | [17](30-4200-17-tablero-en-revision-heredado.png) |

Sin errores de consola en todo el recorrido (`list_console_messages` vacío).

### 10.4 Verificación SQL (PostgreSQL real, `apt_erp` → `tenant_inst_001_038aa2a9`)

Estados y cierre:

| ticket | estado | `fecha_cierre` | sede | solicitante |
|---|---|---|---|---|
| 10 | EnCurso | NULL | 2 | 16 (Nilo) |
| 11 | **Cerrado** | 2026-11-25 20:24:20.459839 | 2 | 16 (Nilo) |
| 12 | **Cerrado** | 2026-11-25 20:28:21.992588 | 2 | 16 (Nilo) |

Stock (`stock_sede`): producto 10 / Sede Maipú **64 → 61**; producto 1 / Sede
Maipú **0 → 23** (recepción) **→ 20** (despacho). El saldo de producto 1 en Sede
Providencia (51) no se tocó, y el stock de la 020/021 sigue intacto.

Movimientos (`movimiento_inventario`, solo los del cierre):

| id | tipo | cantidad | producto | sede | observación |
|---|---|---|---|---|---|
| 5 | ENTRADA | 19 | 10 | 2 | Recepción OC-2026-000001 / Factura 123123987398 (previo, 24/11) |
| 6 | **SALIDA** | 3 | 10 | 2 | `Despacho ticket_id=11; detalle_id=12; producto_id=10` |
| 7 | **ENTRADA** | 23 | 1 | 2 | `Recepción OC OC-2026-000002 / Factura F-T30-0002 — Bodeguero: lu.illanes@duocuc.cl` |
| 8 | **SALIDA** | 3 | 1 | 2 | `Despacho ticket_id=12; detalle_id=13; producto_id=1` |

Historial (`historial_transicion_ticket`), orden real por `fecha_transicion`:

| id | ticket | origen → destino | actor | motivo | OC |
|---|---|---|---|---|---|
| 7 | 11 | (nulo) → Pendiente | 16 Ricardo | — | — |
| 8 | 11 | Pendiente → EnCurso | 14 Cristian | `Aprobación del pedido` | — |
| 9 | 11 | EnCurso → Cerrado | 15 Luciano | — | — |
| 10 | 11 | **Cerrado → Cerrado** | 16 Ricardo | `Entrega confirmada por el solicitante` | — |
| 11 | 12 | (nulo) → Pendiente | 16 Ricardo | — | — |
| 12 | 12 | Pendiente → EnCurso | 14 Cristian | `Aprobación del pedido` | — |
| 13 | 12 | EnCurso → EnCurso | 15 Luciano | `Desbloqueo por reabastecimiento: OC OC-2026-000002 / Factura F-T30-0002` | **2** |
| 14 | 12 | EnCurso → Cerrado | 15 Luciano | — | — |
| 15 | 12 | **Cerrado → Cerrado** | 16 Ricardo | `Entrega confirmada por el solicitante` | — |
| 16 | 9 | Pendiente → **EnRevision** | 14 Cristian | — (nulo) | — |

OC: `orden_compra 2` = `OC-2026-000002`, **Recibida**, proveedor 1, sede 2,
factura `F-T30-0002`, monto 114770.00; `orden_compra_ticket` 1 fila
`(OC 2, ticket 12, producto 1, cantidad_asignada 3)`.

### 10.5 Comprobaciones de contrato por HTTP real

| Caso | Resultado |
|---|---|
| `PATCH /tickets/10/estado {2}` como **Bodeguero** | **403** (matriz; sin cambio) |
| `PATCH /tickets/10/estado {4}` como Administrador | **409** (cierre reservado al despacho) |
| `PATCH /tickets/9/estado {2}` como Administrador | **200**, queda en `EnRevision` con fila motivo nulo (id 16) |
| `POST /tickets/11/aprobacion` como Bodeguero | **403** |
| `POST /tickets/11/aprobacion` como Administrador (ya `EnCurso`) | **409** |
| `POST /tickets/11/confirmacion-entrega` como Administrador | **403** |
| `POST /tickets/11/confirmacion-entrega` como Solicitante (ya confirmada) | **409** |

### 10.6 Humo en 8080 (imagen reconstruida)

`docker compose -f docker-compose.yml build frontend` + `up -d frontend`;
contenedor **healthy** y bundle servido **`main-JE7KG3Z2.js`**. Detalle:

- Imagen `evidenciasproyecto-frontend:latest` (manifest list `sha256:d983fdd217274da6106304e8da93b9d836c9bb41aab2777eadf0fc415744bba1`); `up -d frontend` recreó el contenedor y quedó **healthy**.
- El `index.html` servido referencia **`main-JE7KG3Z2.js`** y `styles-E7WDQOQI.css` (el mismo `main` del `ng build` del host). Los chunks lazy del tablero (`chunk-4C5P26XT.js`) contienen «Terminados» y el del detalle (`chunk-QF6ALCPA.js`) «Confirmar stock local y despachar» y «Confirmar la entrega».
- `GET /` y `GET /tickets/11` (try_files de nginx) responden **200** con el shell SPA; `GET /api/v1/tickets/11` sin token responde **401** (la autorización sobrevive al proxy).
- En el navegador (sesión Clerk compartida en `localhost`), 8080 sirve la vista nueva: tablero de **4 columnas**, «Terminados» con **4** pedidos (#11 y #12 «Entregado», con «Último Bodeguero» y «Último Administrador»), y detalle de #11 con estado canónico `Cerrado`, etiqueta «Entregado», «Entregado el … por Nilo, Ricardo», historial de 4 filas y **sin acciones**. Sin errores de consola.
- API por el proxy con token real: `GET :8080/api/v1/tickets/11` → **200**, `estado_nombre=Cerrado`, `etiqueta_proceso=Entregado`, `entrega_confirmada=true`, `fecha_cierre=2026-11-25T20:24:20`.
- Caché: el navegador solo solicitó `main-JE7KG3Z2.js` (200) y ningún bundle viejo; no hizo falta recargar con `ignoreCache`.
- Captura: [30-8080-01-detalle-entregado.png](30-8080-01-detalle-entregado.png).

### 10.7 Mapeo AC-28…AC-49 → evidencia

| AC | Evidencia |
|---|---|
| AC-28 | Tests `test_ciclo_vida_aprobacion_013.py::test_patch_estado_conserva_su_contrato_de_legado_para_el_administrador_ac_49` y `test_flujo_aprobacion_entrega_013.py::test_patch_de_legado_solo_administrador_y_cierre_reservado`; vivo: PATCH de #9 a `EnRevision` **200** con motivo nulo (SQL id 16) y PATCH a `Cerrado` **409**. §10.4-10.5 |
| AC-29 | Tests `test_aprobacion_desde_origen_elegible_deja_el_pedido_en_curso_ac_29`, `test_aprobacion_siempre_lleva_a_en_curso_y_el_stock_solo_cambia_la_etiqueta_ac_29`, `test_aprobacion_no_toca_stock_ni_movimientos_ac_29`; 4200: #11 (con stock) y #12 (sin stock) quedan **En Curso** con etiquetas distintas. Capturas 03 y 08 |
| AC-30 | Test `test_aprobacion_escribe_una_sola_fila_con_actor_y_motivo_ac_30` y `test_si_la_fila_de_historial_falla_el_estado_no_cambia_ac_30`; SQL filas 8 y 12 (una por pedido, actor Administrador, motivo literal, `orden_compra_id` nulo) |
| AC-31 | E2E `test_flujo_aprobacion_entrega_013.py::test_aprobacion_sin_stock_aparece_en_compras_y_la_oc_mueve_la_etiqueta`; 4200: necesidad ausente antes (07) y presente tras aprobar (09), OC Facturada (11), recepción desbloquea (13) y el cierre sigue siendo el despacho |
| AC-32 | Specs `ticket-detalle.component.spec.ts`; 4200: #11 Pendiente (Solicitante: Editar/Anular; Administrador: Aprobar/Editar/Rechazar/Anular), EnCurso (Bodeguero: despachar), Cerrado (Solicitante: confirmar), sin Avanzar/Retroceder. Capturas 02-05, 08, 13 |
| AC-33 | Specs del detalle y servicio; 4200: despacho de #11 y #12 con diálogo sin motivo, 200, `Cerrado` con `fecha_cierre`, entregado 3/3 y fila de despacho; SQL: dos `SALIDA` (ids 6 y 8). Capturas 04 y 14 |
| AC-34 | Specs de 409 en `role="alert"` y suite 005 de despacho; 4200: la acción no se ofrece al Solicitante (capturas 02 y 05), el tablero no ofrece despacho ni transiciones (06/16) y un despacho repetido está cubierto por los tests de la 005 |
| AC-35 | Caso #10 fuera de Compras en la UI (captura 07: sin fila «Papel Premium A4»); tests `test_flujo_aprobacion_entrega_013.py::test_caso_10_equivalente_omitido_en_compras_y_cierra_normal`, suite 021; sin DDL: token `026.0`, 26/23 tablas, 21 entidades (suite de control y gated) |
| AC-36 | Vivo: PATCH `Pendiente → EnRevision` deja `EnRevision` (no salta a `EnCurso`) y PATCH a `Cerrado` responde 409; tests de flujo y `test_patch…ac_49`; única vía a `EnCurso` es la aprobación (capturas 03/08) |
| AC-37 | Tests unitarios e integración `test_ticket_proceso_013.py` (etiquetas/frases de los cinco estados, `Cerrado` con y sin confirmación, degradación de estado desconocido); 4200: «En aprobación» (02), «En revisión» (17), «Por comprar» (08), «Facturado» (11), «En confirmación de stock local» (03/13), «Despachado» (04/14), «Entregado» (05/15) |
| AC-38 | Tests `test_ac_38_*` (precedencia Recibida > Facturada > Emitida, cancelada no cuenta, stock y «Por comprar»); 4200: «Por comprar» → «Facturado» → «En confirmación de stock local» con la misma OC (08, 11, 13) |
| AC-39 | Tests `test_ac_37_*`, `test_ac_39_*` (listado y detalle exponen los campos y coinciden, detalle conserva listas); 4200: detalle muestra estado canónico + etiqueta + frase (02), listado y tablero coinciden; contrato OpenAPI con los campos |
| AC-40 | Tests `test_ac_40_ultimo_gestor_por_fecha_y_desempate_por_id` y `test_ac_40_sin_historial_o_sin_rol_gestor_queda_en_none`; 4200: «Sin gestión registrada» antes (02) y «Illanes, Luciano» / «Gonzalez, Cristian» después (03, 04, 16) |
| AC-41 | Specs de `tickets.component.spec.ts`; 4200: columnas Pendiente / En Revisión / En Curso / **Terminados** con contador sumado (2), sin columna `Anulado`, etiqueta visible, frase accesible y dos responsables (06, 16, 17) |
| AC-42 | Tests `test_confirmacion_del_dueno_responde_200_con_una_fila_cerrado_cerrado_ac_42`, `test_la_confirmacion_no_reabre_ni_mueve_el_pedido_ac_42`, `test_listado_y_detalle_reflejan_la_entrega_confirmada_ac_42`; 4200 y SQL filas 10 y 15: una `Cerrado → Cerrado`, motivo literal, actor dueño, estado y `fecha_cierre` intactos, sin movimiento nuevo. Capturas 05/15 |
| AC-43 | Tests `test_confirmacion_ajena_e_inexistente_responden_404_identico_ac_43`, `test_confirmacion_no_se_concede_a_otros_roles_ac_43`, `…sin_sesion…401`, `…capacidad_tickets_apagada…403`, `…no_cerrado…409`, `…repetida…409 sin una segunda fila`, `test_un_pedido_creado_por_un_administrador_no_admite_confirmacion_ac_43`; vivo: 403 Administrador, 409 repetida (§10.5); gated: `(200, 409)` con una sola fila |
| AC-44 | `test_permisos_endpoints.py` (inventario rutas↔matriz 75) y `test_cobertura_021.py::test_openapi_publica_el_preview_y_75_operaciones`; `GET /openapi.json` **77** operaciones (75 v1), sin capacidades/estados/DDL nuevos (§10.2) |
| AC-45 | Tests `test_aprobacion_no_se_concede_a_otros_roles_ac_45`, `test_aprobacion_con_kanban_apagada_responde_403_sin_mutar_ac_45`, `test_matriz_declara_la_aprobacion_y_el_patch_solo_para_administrador_ac_44`; vivo: 403 Bodeguero y 409 ya `EnCurso` (§10.5); 4200: Aprobar visible solo con Administrador (02/03) |
| AC-46 | Tests `test_aprobacion_de_un_estado_ya_avanzado_o_terminal_responde_409_ac_46`, `…estado_no_elegible…409`, `…sin_en_curso…409`, `…404_identico`, `…401`; vivo 403/409; sin payload obligatorio |
| AC-47 | 4200: ningún alta produce `EnRevision` (estado fijo Pendiente), el tablero conserva la columna con 3 heredados (#3, #4, #9) y #9 ofrece Aprobar/Rechazar/Anular; solo el PATCH de legado produce `EnRevision` (vivo, §10.5). Captura 17 |
| AC-48 | Specs de detalle/tablero (sin Avanzar/Retroceder, sin `PATCH`); 4200: barras semánticas (02-05, 08, 13); vivo: `PATCH` 403 para Bodeguero, 200/409 para Administrador (§10.5) |
| AC-49 | Vivo: `PATCH` Bodeguero **403** y Administrador **200/409**; `POST /despacho` y `/rechazo` conservan Administrador/Bodeguero (tests `test_el_bodeguero_conserva_despacho_y_rechazo_ac_49`); matriz 75 (misma cuenta de operaciones) |

### 10.8 Hallazgos y datos residuales

- **Hallazgo menor — RESUELTO en T31 (25/Nov/2026):** tras un alta, la tarjeta
  del pedido nuevo mostraba como etiqueta el nombre canónico («Pendiente») en
  lugar de «En aprobación», porque el tablero inserta el `201` de `POST
  /tickets/` (que devolvía el ORM, con `etiqueta_proceso` vacía por defecto) sin
  reconsultar. **Corrección:** `crear_ticket` devuelve `TicketRespuesta`
  construido con `_respuesta_ticket_con_proceso` (el mismo read model del
  listado y el detalle), sin cambiar el alta (sigue naciendo en `Pendiente`,
  AC-27) ni el contrato de la operación. Evidencia: backend
  `test_ticket_proceso_013.py::test_ac_39_el_201_*` (Administrador y
  Solicitante como creadores)
  y frontend `tickets.component.spec.ts` «la tarjeta del pedido recién creado
  muestra «En aprobación» (T31)». El hallazgo original se conserva descrito
  arriba como contexto; ya no es deuda abierta.
- **Datos QA residuales:** pedidos #11 y #12 en `Cerrado`/«Entregado»; OC
  `OC-2026-000002` en `Recibida`; el pedido #9 pasó de `Pendiente` a
  `EnRevision` por la comprobación del `PATCH` de legado (fila 16, motivo nulo);
  producto 10 / Sede Maipú con stock 61 y producto 1 / Sede Maipú con 20.
  **Estos datos ya no existen:** la base QA se reseteó tras el cierre (§10.9).
- No se agregaron usuarios, proveedores ni productos. Las credenciales no se
  registraron en esta evidencia.

### 10.9 Reset de la base QA post-cierre (25/Nov/2026)

- Se ejecutó `docker compose -f docker-compose.yml down -v` y `up -d` después de
  cerrar T31: el volumen se recreó desde `01_esquema.sql` + `02_datos_semilla.sql`
  y desaparecieron los datos del recorrido (§10.8): pedidos #11/#12, OC
  `OC-2026-000002`, el #9 movido a `EnRevision` y los saldos 61/20.
- Verificación: `docker compose ps` con `db`, `redis`, `backend` y `frontend`
  arriba; token `026.0`; **26** tablas en `control` y **23** por tenant; cuentas
  demo de la semilla presentes (`crise.gonzalez`, `lu.illanes`, `ri.nilo`);
  tickets y stock de la semilla intactos; `/health` y `/ready` en **200**.
- Las capturas y consultas del recorrido (§10.1–§10.7) siguen siendo evidencia
  histórica válida del comportamiento verificado; no describen el estado actual
  de la base, que es el de la semilla.

## 11. Enmienda 26/Nov/2026 — cierre (T44): catálogo de cuatro estados, retiro y anulación con devolución

Cierre de la §10 de la spec (AC-50…AC-68). Recorrido **real de UI** en `4200` con
sesiones Clerk de la semilla vigente de la 012, capturas en esta carpeta y
verificación SQL por `docker exec psql` tras cada camino. Los tests gated usan
bases desechables y nunca tocan `apt_erp`.

### 11.1 Suites, gated y build

| Verificación | Comando | Resultado real |
|---|---|---|
| Backend SQLite (suite completa) | `cd backend; .venv\Scripts\python.exe -m pytest -q` | **2163 passed / 127 skipped / 0 failed** en 9:10 |
| Gated PostgreSQL 16 (suite completa) | `$env:POSTGRES_TEST_URL="postgresql://postgres:postgres@localhost:5433/postgres"; pytest -q` | **2287 passed / 3 skipped / 0 failed** en 1745,06 s (29:05); los 3 `skipped` son los módulos gated de Redis (sin `REDIS_TEST_URL`); `apt_erp` intacta |
| Frontend | `$env:CHROME_BIN="C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"; npx ng test --watch=false --browsers=ChromeHeadless` | **671 SUCCESS / 0 FAILED** |
| Build de producción | `cd frontend; npx ng build` | limpio; **`main-IRJLFDU6.js`**, `Initial total 339.98 kB` |

### 11.2 Contrato OpenAPI (backend vivo en `:8000`)

`GET /openapi.json`: **74 entradas** = **72** operaciones v1 + `GET /` + `GET
/health`; `MATRIZ_PERMISOS`: **72**. `POST /tickets/{id}/retiro` →
`{Bodeguero}` (capacidad `kanban`); `POST /inventario/movimientos` →
`{Bodeguero}`; `POST /tickets/{id}/anulacion` → `{Administrador, Solicitante}`;
`PATCH /tickets/{id}/estado` → `{Administrador}`; `/despacho` ausente.

**Delta externo (012, 27/Nov/2026):** la línea base de la 013 era **75 v1 / 77
entradas**; la enmienda de la 012 retiró las 3 operaciones de
`departamento_encargado` y dejó la base en **72/74**. La 013 no cambia la
cardinalidad: renombra una clave (`/despacho` → `/retiro`) y no retira ninguna
otra.

### 11.3 Reset de la base QA y verificación del catálogo (27/Nov/2026 ~15:29)

`docker compose -f docker-compose.yml down -v` + `up -d`: volumen recreado desde
`01_esquema.sql` + `02_datos_semilla.sql`; `db`, `redis`, `backend` y `frontend`
healthy; `/health` y `/ready` **200**.

| Verificación | Resultado |
|---|---|
| Token (`control.version_esquema`) | **`026.1`** |
| Tablas | **25** en `control`, **22** por tenant |
| Catálogo `estado_ticket` (tenant) | **4** filas: `EnRevision,EnCurso,Cerrado,Anulado` |
| Tickets INST-001 | #1–#4 `EnRevision`, #5–#6 `EnCurso`, #7–#8 `Cerrado` |
| Tickets INST-002 | #9 `EnRevision`, #10 `Cerrado` (5/5) |
| `Anulado` en la semilla | **ninguno** |
| `Cerrado` | `fecha_cierre` y `cantidad_entregada = cantidad_solicitada` |

**Delta externo (012):** la 013 esperaba **26/23** y `026.0`; la enmienda de la
012 del 27/Nov dejó **25/22** y `026.1`. La 013 no añadió DDL, migración ni
token: el catálogo y el retiro usan las tablas existentes.

### 11.4 Recorrido funcional en 4200 (escritura real)

Backend en contenedor (`uvicorn --reload`) + `npm start` (4200). Sesiones Clerk
reales con el código `424242` de las cuentas `+clerk_test`. Las cuentas de §2
son históricas del cierre del 25/Nov; el recorrido de §11 usó las de la semilla
vigente de la 012: `solicitante.test+clerk_test@example.com` (Paula Rojas,
Solicitante, Biblioteca → Sede Maipú), `admin020.test+clerk_test@example.com`
(Admin QA, Administrador) y `bodeguero.test+clerk_test@example.com` (Roberto
Diaz, Bodeguero, Sede Maipú).

| # | Actor | Acción en la UI | Observado | Captura |
|---|---|---|---|---|
| 1 | Solicitante | Tablero de 3 columnas | «En Revisión», «En Curso» y «Terminados»; contadores = tarjetas | [40-01](40-01-tablero-3-columnas-solicitante.png) |
| 2 | Solicitante | «+ Crear pedido» #9: 3 × Papel Premium A4, estado **FIJO En Revisión** | 201, tarjeta #9 en «En Revisión»; sin selector de estado | [40-02](40-02-tablero-3-columnas-con-pedidos.png) |
| 3 | Administrador | «Aprobar» #9 | **En Curso**; historial `En Revisión → En Curso` con motivo `Aprobación del pedido` | [40-03](40-03-detalle-enrevision-admin.png) / [40-04](40-04-tablero-3-columnas-admin-encurso.png) |
| 4 | Bodeguero | «Registrar retiro» #9 → «Confirmar retiro» | **Cerrado** + etiqueta **Retirado**; `fecha_cierre` 18:37:21; entregado 3/3 | [40-05](40-05-detalle-encurso-bodeguero-registrar-retiro.png) / [40-06](40-06-dialogo-confirmar-retiro.png) |
| 5 | Administrador | «Anular el retiro» #9 con motivo | **Anulado** + etiqueta **Rechazado**; stock devuelto y `cantidad_entregada` 0 | [40-07](40-07-detalle-retirado-admin-anular-retiro.png) / [40-08](40-08-dialogo-anular-retiro-motivo.png) / [40-09](40-09-detalle-anulado-rechazado-admin.png) |
| 6 | Bodeguero | «Registrar retiro» #10 → confirmar | **Cerrado** + **Retirado** | [40-10](40-10-detalle-encurso-bodeguero-ticket10.png) / [40-11](40-11-detalle-retirado-ticket10.png) |
| 7 | Solicitante | «Confirmar entrega» #10 → diálogo → confirmar | **Entregado**; «no admite más acciones»; estado canónico `Cerrado` | [40-12](40-12-detalle-retirado-solicitante-confirmar-entrega.png) / [40-13](40-13-dialogo-confirmar-entrega.png) / [40-14](40-14-detalle-entregado-solicitante.png) |
| 8 | Administrador | Intento de anular #10 ya confirmado | **409** `La entrega de este pedido ya fue confirmada por el solicitante: el retiro no puede anularse`; la acción no se ofrece | [40-15](40-15-detalle-entregado-admin-sin-acciones.png) |
| 9 | Administrador | Tablero / Dashboard | **En Revisión 4 / En Curso 3 / Terminados 4**; «Pedidos Activos» **7** | [40-16](40-16-tablero-3-columnas-cuatro-estados.png) / [40-17](40-17-dashboard-pedidos-activos-7.png) |

El #11 («Cierre T44 confirmacion previa») se creó y aprobó en el mismo recorrido
y quedó **EnCurso** para que el tablero tuviera datos de los cuatro estados.

#### Verificación SQL (PostgreSQL real, `apt_erp` → `tenant_inst_001_038aa2a9`)

| ticket | estado | `fecha_cierre` | `cantidad_entregada` |
|---|---|---|---|
| 9 | **Anulado** | NULL | 0 |
| 10 | Cerrado | 2026-11-27 18:40:25.243352 | 3 |
| 11 | EnCurso | NULL | 0 |

Stock `stock_sede` (producto 10 / Sede Maipú): **45 → 42** (retiro #9) **→ 45**
(devolución) **→ 42** (retiro #10).

`movimiento_inventario`:

| id | tipo | cantidad | observación |
|---|---|---|---|
| 4 | **SALIDA** | 3 | `Salida por retiro del ticket #9; detalle_id=9; producto_id=10` |
| 5 | **ENTRADA** | 3 | `Devolución por anulación del retiro del ticket #9; detalle_id=9; producto_id=10` |
| 6 | **SALIDA** | 3 | `Salida por retiro del ticket #10; detalle_id=10; producto_id=10` |

`historial_transicion_ticket` (ids 1–10): #9 `(nulo) → EnRevision` →
`EnRevision → EnCurso` → `EnCurso → Cerrado` → `Cerrado → Anulado`; #10
`(nulo) → EnRevision` → `EnRevision → EnCurso` → `EnCurso → Cerrado` →
`Cerrado → Cerrado` (`Entrega confirmada por el solicitante`); #11
`(nulo) → EnRevision` → `EnRevision → EnCurso`.

### 11.5 409 de anulación posterior a la confirmación

Con la sesión del Administrador y el pedido #10 ya confirmado, el servicio del
detalle (`POST /tickets/10/anulacion`) respondió **409** con
`{"detail":"La entrega de este pedido ya fue confirmada por el solicitante: el retiro no puede anularse"}`.
SQL posterior: #10 sigue `Cerrado`, `fecha_cierre` 18:40:25 y
`cantidad_entregada` 3 intactas, historial con 4 filas (la de confirmación no se
borró) y ningún movimiento nuevo.

### 11.6 Humo en 8080 (imagen reconstruida)

`docker compose -f docker-compose.yml build frontend` + `up -d frontend`; el
contenedor seguía con la imagen anterior (ID `7d925c…`, ya sin tag), así que se
recreó con `up -d --force-recreate frontend`. Imagen vigente
`evidenciasproyecto-frontend:latest` (`sha256:8c7ca2…`), contenedor **healthy**;
`index.html` sirve **`main-IRJLFDU6.js`** (el mismo del `ng build` del host).
`GET /` y `GET /tickets/10` responden **200** (try_files de nginx).

- Tablero: **En Revisión 4 / En Curso 3 / Terminados 4**; detalle #10
  **Entregado** (canónico `Cerrado`, «no admite más acciones») y detalle #9
  **Anulado/Rechazado**. Capturas [40-18](40-18-8080-tablero-3-columnas.png),
  [40-19](40-19-8080-detalle-entregado.png) y
  [40-20](40-20-8080-detalle-anulado.png).
- Red: `main-IRJLFDU6.js` **[200]**; sin errores de consola (solo el aviso de
  claves de desarrollo de Clerk y un aviso de accesibilidad de 5 campos sin
  `id`/`name`, ajeno a esta enmienda).
- La sesión Clerk de `localhost` se comparte entre 4200 y 8080; no hizo falta un
  login nuevo.
- **Recaptura 8080:** `40-18` se volvió a capturar en `http://localhost:8080/tickets`
  (196.983 bytes, hash distinto de `40-16`). `40-19` se volvió a capturar en
  `http://localhost:8080/tickets/10`; su archivo es idéntico a `40-15` porque la UI y
  los datos son los mismos, así que el humo 8080 se sostiene además en el hash
  `main-IRJLFDU6.js` y en `40-20`.

### 11.7 Mapeo AC-50…AC-68 → evidencia

| AC | Evidencia |
|---|---|
| AC-50 | `test_catalogo_estados_013.py::test_el_catalogo_del_aprovisionamiento_tiene_las_cuatro_filas_ac_50`; gated `test_catalogo_retiro_postgres_013.py` (5 passed) y `test_instalacion_limpia_postgres.py` (8 passed); SQL de §11.3: 4 filas, distribución de la semilla, ningún `Anulado`, `Cerrado` con fecha y cantidad. Delta 25/22/`026.1` por la 012 |
| AC-51 | `test_ciclo_vida_alta_inicial_013.py` (6 pruebas) y `tickets.component.spec.ts`; 4200: #9–#11 nacen `EnRevision` con estado fijo (40-01/40-02) |
| AC-52 | `test_ciclo_vida_aprobacion_013.py` y `test_catalogo_estados_013.py::test_aprobar_desde_enrevision_deja_en_curso_ac_52`; 4200: #9–#11 a `EnCurso` con actor `QA, Admin` (40-03/40-04) |
| AC-53 | `test_ciclo_vida_edicion_013.py` (12 pruebas) y `ticket-detalle.component.spec.ts`; edición sin cambiar estado/solicitante/sede/institución |
| AC-54 | `test_anulacion_retiro_013.py::test_la_anulacion_desde_enrevision_conserva_su_contrato_sin_stock_ac_54` y `test_catalogo_estados_013.py::test_anular_y_rechazar_solo_desde_enrevision_ac_54`; 4200: #9 `Anulado` «Rechazado» (40-09) |
| AC-55 | `test_retiro_transaccional_013.py` y `test_permisos_retiro_013.py`; contrato vivo 72 v1/74 y `/despacho` ausente; 4200: #9/#10 retirados por el Bodeguero (40-05/40-06/40-10/40-11). Delta 75/77 → 72/74 por la 012 |
| AC-56 | `test_retiro_sede_013.py` (4 pruebas: sede propia 200; otra sede 404 idéntico; sin sede 409; ticket sin sede 409); 4200: retiro de Sede Maipú |
| AC-57 | `test_retiro_transaccional_013.py` (17 pruebas) y gated `test_retiro_anulacion_postgres_013.py`; SQL de §11.4: `SALIDA` literal, stock 45→42, cantidad 3, fecha e historial |
| AC-58 | `test_anulacion_retiro_013.py` (14 pruebas) y gated de anulación; SQL de §11.4: #9 `Anulado`, fecha NULL, cantidad 0, stock 42→45, `ENTRADA` literal e historial `Cerrado → Anulado`; 4200: 40-07/40-08/40-09 |
| AC-59 | `test_retiro_anulacion_postgres_013.py` (anulación concurrente `(200, 409)`, una sola `ENTRADA`, creación de `stock_sede`, cruce con confirmación) y pruebas de atomicidad de `test_anulacion_retiro_013.py`; gated completo 2287/3 |
| AC-60 | `test_patch_estado_retiro_013.py` (8 pruebas) y `test_ciclo_vida_aprobacion_013.py::test_patch_estado_conserva_su_contrato_de_legado_para_el_administrador_ac_49` |
| AC-61 | `test_confirmacion_anulacion_013.py` (6 pruebas) y e2e `test_flujo_retiro_013.py`; SQL de §11.4: #10 `Cerrado`, fecha y cantidad intactas, historial `Cerrado → Cerrado`; 4200: 40-12/40-13/40-14; 409 de §11.5 |
| AC-62 | `tickets.component.spec.ts` (3 columnas, sin `Pendiente` ni `Anulado` separada, contadores); 4200: 4/3/4 (40-16); 8080: 4/3/4 (40-18) |
| AC-63 | `ticket-detalle.component.spec.ts` y `roles.spec.ts`; 4200 con Administrador/Bodeguero/Solicitante: retiro (Bodeguero), anulación (Administrador solo en `Cerrado` sin confirmar) y confirmación (Solicitante); el Superadmin queda fuera de `/tickets` (`ROLES_TICKETS` y `roles.spec.ts`); «Entregado»/«Rechazado» (40-05…40-15) |
| AC-64 | `test_permisos_retiro_013.py` (11 pruebas: matriz 72, `/retiro` solo Bodeguero, movimientos solo Bodeguero, `/anulacion` y `PATCH` intactos, OpenAPI 72/74, `/despacho` ausente) y `roles.spec.ts` (espejo). Delta 75/77 → 72/74 por la 012 |
| AC-65 | `test_ciclo_vida_dashboard_013.py` (excluye `Anulado` por nombre; ámbito del Solicitante; resto intacto); 4200: «Pedidos Activos» 7 (40-17) |
| AC-66 | e2e `test_flujo_retiro_013.py::test_compras_021_no_cambia_por_la_devolucion_ac_35` y suite 020/021; 4200: `/compras/necesidades` 4 filas / 33 sugeridas y devolución reflejada en `stock_sede` |
| AC-67 | `stack.md` §2 (enmienda y superación) con los cuatro estados, el retiro y la anulación con devolución; grep ampliado a `docs/diagramas/` y `docs/informes/`: 0 afirmaciones vigentes de `Pendiente`, `/despacho`, `Despachado`, «cinco estados», «cuatro columnas», `75/77` ni `026.0`; 06/07/10/11 actualizados con PNG regenerados, 4+1 03/01 con banner histórico, informe Word regenerado y solo notas históricas/slugs de archivo (§11.9) |
| AC-68 | §11.1 (suites y build), §11.2 (contrato), §11.4–§11.5 (4200 con escritura real) y §11.6 (8080 reconstruido) |

### 11.8 Hallazgos y datos residuales

- **Datos QA residuales:** #9 `Anulado`, #10 `Cerrado`/«Entregado» y #11
  `EnCurso`; producto 10 / Sede Maipú con stock **42**; movimientos 4–6 e
  historial 1–10 del recorrido. No se crearon usuarios, productos, proveedores
  ni OC. Las credenciales no se registraron.
- **Deltas externos asumidos:** la base vigente es **72 v1 / 74 entradas**,
  **25/22** tablas y **`026.1`** por la enmienda de la 012 del 27/Nov; la 013 no
  cambia la cardinalidad de operaciones ni el DDL. `roadmap.md:92` conserva la
  fila histórica de la 013 con `Pendiente`, matriz 49 y `013.1` (no se toca;
  pendiente para el coordinador). Las menciones históricas de `/despacho` en
  `008-particionamiento-institucional/spec.md` se conservan con la nota de superación; los
  diagramas corrientes se actualizaron y los 4+1 históricos llevan banner (§11.9).
- **8080 y la imagen:** `up -d frontend` no recreó el contenedor aunque la
  imagen acababa de reconstruirse; seguía sirviendo la imagen anterior. Hay que
  verificar el ID de imagen del contenedor o usar `up -d --force-recreate
  frontend` para que el humo sea válido.
- **Observación menor — RESUELTA en la corrección post-validación (27/Nov/2026):**
  `ticket_proceso.py` ya dice «…lo confirme y retire» y «Rechazado: el pedido no se
  retirará»; las fixtures de `test_ticket_proceso_013` (unitario e integración) se
  actualizaron y la suite SQLite completa volvió a quedar en **2163 passed / 127 skipped /
  0 failed** (13:04).

### 11.9 Corrección post-validación (27/Nov/2026): coherencia de diagramas e informes

La validación del reviewer detectó que AC-67/T43 aún dejaba menciones vigentes a
`/despacho` y `Pendiente` en diagramas e informes. Se corrigió sin tocar el contrato
funcional, `database/`, `plan.md`, `stack.md` ni los archivos del refactor externo de
la 012.

| Archivo | Tratamiento |
|---|---|
| `docs/diagramas/flujos-actores/README.md` | El límite conocido pasa a `POST /api/v1/tickets/{id}/retiro`; el flujo 07 se describe como retiro y se anota el slug histórico. |
| `06-administrador-pedidos.html` / `.png` | **Actualizado:** «Aprobar o rechazar», edición en En revisión y nota de cierre reservado al retiro + anulación administrativa. PNG regenerado (2400×1120). |
| `07-bodeguero-pedidos-despacho.html` / `.png` | **Actualizado:** «Pedidos y preparación del retiro», «Rechazar si no procede», «Preparar el retiro», «Registrar el retiro» y nota con «Registrar retiro» en el detalle. PNG regenerado. |
| `10-solicitante-crear-pedido`, `11-solicitante-seguimiento`, `04`, `08` y `09` | **Actualizados** de `Pendiente`/«despacho» a `En revisión`/«retiro»; PNG regenerados. |
| `4+1-kruchten/01-vista-logica/03-secuencia-despacho.html` | **Marcado histórico:** banner visible «La ruta vigente es `/retiro` y `registrar_retiro_ticket`; ver 013 §10». Se conserva el artefacto original. |
| `4+1-kruchten/02-vista-procesos/01-actividad-ciclo-ticket.html` | **Marcado histórico:** banner visible con el catálogo de cuatro estados y «Registrar retiro». |
| `4+1-kruchten/01-vista-logica/02-clases-inventario-tickets.html` | Colofón actualizado a `registrar_retiro_ticket`. |
| `docs/informes/_generar_informe.py` + `Informe_Flujos_Actores.docx` | Cadenas actualizadas al contrato vigente (retiro, En revisión, solo Bodeguero para retiro y movimientos) y DOCX regenerado con los 12 PNG. |
| `docs/informes/_generar_planilla_pruebas.py` | Etiquetas de taxonomía «transacción/retiro» y «transacciones/retiro». |

El índice `4+1-kruchten/00-indice.html` marca los enlaces a la secuencia y a la actividad
como «histórico».

**Grep de cierre ampliado** a `docs/diagramas/` y `docs/informes/`: no quedan
`/despacho`, `Pendiente`, `Despachado` ni `despachar_ticket` **vigentes**. Las únicas
coincidencias son históricas y están cubiertas por los banners de esta §11.9 o por
slugs de archivo (`07-bodeguero-pedidos-despacho`), que no son rutas ni estados.

**PNG:** se regeneraron `04`, `06`, `07`, `08`, `09`, `10` y `11` (2400×1120); el
`03-administrador-administracion.png` es el actualizado externamente el 27/Nov a las
15:05 y **no se tocó**; los de `00`, `01`, `02` y `05` no cambiaron porque sus flujos no
se tocaron. Los PNG de los 4+1 `03-secuencia` y `01-actividad` no se regeneraron: son
recortes del SVG (2880×1920 y 2880×2520) y el banner histórico vive en el HTML; se
conservan como artefactos. El PNG de `02-clases` no cambia porque el colofón está fuera
del SVG.

**Copy y capturas:** las capturas `40-05` y `40-09` se tomaron antes del ajuste de copy
de `ticket_proceso.py`; conservan «despache»/«no se despachará» como registro histórico
del recorrido. El copy vigente es «retire»/«no se retirará» y está cubierto por los
tests actualizados.

**Corrección visual del tablero (27/Nov/2026):** `tickets.component.html` pasó de
`md:grid-cols-4` a `md:grid-cols-3` (contenedor `data-testid="tablero-pedidos"`), con el
comentario ajustado a dos operativas + «Terminados». Regresión en
`tickets.component.spec.ts`; `ng test` **684 SUCCESS / 0 FAILED**, `ng build` limpio
(`main-6T35N3WS.js`) y 4200 con tres columnas de ~385 px sobre 1202 px (viewport 1536).

**Corrección del shell (27/Nov/2026):** `app.component.html` añade `overflow-hidden` y
`[contain:paint]` al contenedor `flex h-screen`, y `min-h-0 overflow-y-auto` al `nav`; el
`<main>` conserva su `overflow-y-auto`. Regresión en `app.component.spec.ts` (shell, nav y
main). `ng test` **685 SUCCESS / 0 FAILED**; `ng build` limpio (`main-SHBQMIGH.js`).
4200: documento **674 = ventana 674**, `window.scrollTo(9999)` no mueve, nav forzado
**272 > 160** con `scrollTop` 112 y main **1329/610** con scroll interno.

**8080 (27/Nov/2026, tras la corrección del shell):** imagen
`evidenciasproyecto-frontend:latest` reconstruida (`sha256:317fbdf…`) y contenedor recreado
con `--force-recreate`; `index.html` sirve **`main-SHBQMIGH.js`**; `main-6T35N3WS.js`,
`main-IRJLFDU6.js` y `main-72C5Q3DY.js` responden **404**; mismas métricas de shell y
capturas [40-21](40-21-8080-tablero-3-columnas-fix.png) y
[40-22](40-22-8080-shell-sin-scroll.png).

**Capturas 8080:** `40-18` se recapturó en `http://localhost:8080/tickets` (196.983
bytes, hash distinto de `40-16`); `40-19` se recapturó en
`http://localhost:8080/tickets/10` y su archivo coincide con `40-15` porque la UI y
los datos son los mismos. El humo original se sostuvo en `main-IRJLFDU6.js`; la
verificación final usa `main-SHBQMIGH.js` y `40-22` (§11.9).
