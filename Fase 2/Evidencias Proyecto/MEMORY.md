# MEMORY.md — Diario del Proyecto
Memoria entre sesiones. Máximo ~50 líneas: resume lo útil y elimina lo que ya no aporte.

## Estado actual
- Features 000…**023 cerradas**; la **023** el **13/Nov/2026**, la **022** el **12/Nov/2026**, la **021** el **08/Nov/2026**, la **020** el **04/Nov/2026**, la **019** el **22/Oct/2026**, la **018** el **21/Oct/2026**, la **014** y la **017** el **20/Oct/2026**, la **013** el **19/Oct/2026**.
- **023 (mantenimiento técnico II) CERRADA:** `compra_service` pasó de módulo plano a paquete con fachada (`__init__.py`, `_comun`, `necesidades`, `cobertura`, `proveedores`, `ordenes`, `recepcion`). Se conservan la ruta `from app.services import compra_service`, los 16 símbolos, `_simular_claves`, las firmas y el contrato. Dedup de `_opciones_orden` y `_validar_entrada_orden`. Backend **1502 passed/88 skipped**, frontend **549 SUCCESS**, build limpio, 73/75 OpenAPI, `021.1` y 27/24 tablas; 4200 con `OC-2026-000002/3` y recepción real del Bodeguero, humo 8080 sin rebuild. Evidencia en `023-refactor-compra-service/evidencia/README.md`.
- **022 (mantenimiento técnico I) CERRADA:** eliminado el servicio HTTP muerto de administración, corregidos `AGENTS.md`/`stack.md`/README raíz/`frontend/README.md`, deduplicados los seis `mensajeDeError*` en `shared/utils/errores-http.ts` y `_correo_actor` en `auth_service.correo_del_actor`. Backend **1499 passed/88 skipped**, frontend **549 SUCCESS**. Evidencia en `022-mantenimiento-tecnico/evidencia/README.md`.
- **021 (cobertura automática por OC) CERRADA:** `orden_compra_ticket` (22.ª entidad), plan congelado al emitir, necesidad neta parcial con `stock_comprometido`/`stock_borrador`, preview de cobertura (matriz 72→73) y cadena por producto. Versión `021.1`, 27/24 tablas. Evidencia en `021-cobertura-automatica-tickets-compras/evidencia/README.md`.
- **020 (reabastecimiento externo y compras):** 21 entidades, séptima capacidad `compras`, matriz 62→72, catálogo global de proveedores replicado por `proveedor_id`, `numero_oc` derivado del identity y `stock_disponible` calculado. Evidencia en `020-reabastecimiento-compras/evidencia/README.md`.
- **019/018/014/017/013:** detalle de producto por alcance (matriz 62), filtro `sede_id` (61), ciclo de vida del catálogo (55→60, historiales 16.ª/17.ª), invitaciones Clerk y gobierno de Administradores (55), y ciclo de vida del pedido con `Anulado` e historial inmutable (15.ª entidad, 49). Enmiendas post-cierre: T-17 (pestañas ARIA de `/administracion`) y AC-27 de la 013 (alta fija en `Pendiente`, prioridad `Media`).
- **Base consolidada (08/Nov/2026):** `database/` tiene solo `01_esquema.sql` (control **27** tablas + **24** por tenant) y `02_datos_semilla.sql` (`021.1`, 28 capacidades, 3 proveedores, guardia fail-closed). Sin migraciones: reset = `down -v` + `up -d`.
- **Flujos por actor (11/Nov/2026):** 12 diagramas HTML+PNG en `docs/diagramas/flujos-actores/` e informe `docs/informes/Informe_Flujos_Actores.docx` (A4 horizontal, 38 páginas; 12/12 self_check; PNG 2400×1120). Publicado en `origin/main` y `origin/ricardo` el 12/Nov/2026.

## Feature 023 — decisiones clave
- **Paquete con fachada:** `compra_service/` reexporta la API y declara `__all__`; los consumidores no cambian. Grafo acíclico: `_comun ← necesidades ← cobertura ← recepcion`; `proveedores` y `ordenes` cuelgan de `_comun`; ningún módulo importa la fachada.
- **Movimiento verbatim y dedup posterior:** T2 movió bloques sin reescribirlos; T3 añadió `_opciones_orden()` (carga de OC) y `_validar_entrada_orden()` (alta/edición) conservando el orden `sede → proveedor → ítems → réplica`.
- **Costura privada:** `_simular_claves` se conserva y reexporta desde `necesidades.py` porque `ticket_service` y `test_cobertura_021.py` la usan. No se exportan privados nuevos.

## Feature 021 — decisiones clave
- **`orden_compra_ticket` es la intención:** una fila por `(OC, pedido, producto)`; varias OC pueden cubrir el mismo pedido. `base = max(0, solicitado - plan_previo - entregado)`; `plan_previo` = OC `Emitida` + `Facturada`; `Recibida` ya está en stock; `Cancelada` no cubre. Prioridad/FIFO, sin reserva.
- **`stock_comprometido`** suma `detalle_orden_compra` de OC `Emitida` + `Facturada`; `stock_borrador` es aparte; `sugerido = max(0, mínimo + demanda - actual - comprometido)`. **`Cerrado` sigue siendo el despacho:** la recepción deja el pedido en `EnCurso` con badge y fila de historial `EnCurso → EnCurso`.

## Decisiones vigentes (020/019/018/014/012/011)
- **020:** `control.proveedor` es catálogo global y la réplica tenant usa el mismo `proveedor_id`; el Superadmin no replica. **Listado de OC:** el Bodeguero queda forzado a `Facturada` + su sede.
- **019:** ámbito completo sin heredar filtros (Admin todas, Bodeguero su sede, Solicitante la de su departamento); sedes inactivas incluidas; 409 de sede antes de 404 de producto.
- **018:** `sede_id` es filtro dentro de `condicion_stock` (200/`[]` para id ajeno). **014:** nunca producto activo bajo categoría inactiva; baja exige saldo cero. **012/011:** `control.institucion.activo` gobierna el routing; 7 capacidades; `stock_sede` es la única fuente de saldo.
- **013:** `Anulado` no sella `fecha_cierre` ni toca stock; el alta nace en `Pendiente` por nombre canónico.

## Aprendizajes y errores a evitar
- **Filtro de lista ≠ recurso:** `sede_id` en `/inventario/existencias` responde 200/`[]`; no añadir lookup previo. El detalle nuevo usa `inventario` y `/productos/{id}` sigue en `catalogo`.
- Cierre = verificación (AGENTS §8.5–§8.7): los dos puertos; 8080 exige `docker compose build frontend` si cambió el frontend; el backend recarga solo; grep de coherencia sobre AGENTS/MEMORY/skills.
- **Mover un módulo a paquete:** borrar el `.py` y su `.pyc` en la misma tarea; un import faltante en un módulo movido lo detectan las suites focalizadas, no la suite completa.
- **Árbol revertido por un proceso externo:** revisar `git stash list` y `git reflog` antes de rehacer trabajo.
- **Contratos externos:** la API real de Clerk `GET /v1/invitations` devuelve lista desnuda, no `{"data":[…]}`. **La semilla limpia no crea al Superadmin:** `control.usuario` queda vacía.
- Tests PostgreSQL **gated** (`POSTGRES_TEST_URL`); SQLite no valida esquemas/namespaces ni FK compuestas. El gated debe cablear `abrir_sesion_tenant=crear_sesion_esquema`. Toda mutación exige actor persistido.
- Edge: `CHROME_BIN` + `--watch=false --browsers=ChromeHeadless` (nunca `npm test`). Clerk por HTTP: dev browser + sign-in ticket BAPI + `Origin: localhost:4200`; tokens ~60 s.
- **Detalle del pedido con scroll interno:** `take_screenshot(fullPage)` no incluye la cobertura; hacer `scrollIntoView` antes de capturar. **Specs Angular:** con `provideRouter([])` el click de un `routerLink` no actualiza `router.url` (probar el `href`). Pestañas ARIA sobre Router: derivar de `Router.url` y activar con `RouterLink`.
- **Autoría del ticket = identidad de sesión:** no validar `usuario_id` del alta; la sede sale de `departamento.sede_id`. **Carreras gated:** `Barrier` no fija el orden del lock; la poseedora confirma con `threading.Event`.

## Próximos pasos
- **Sprint 7 (03/Nov/2026 – 11/Dic/2026):** 020, 021, 022 y 023 cerradas; siguen **015** informes PDF/Excel y **016** notificaciones in-app. **Hito 2** al cierre del Sprint 7, el **11/Dic/2026**.
- **Siguiente trabajo:** abrir 015 o 016 según prioridad; no reabrir la limpieza de 022 ni el refactor de 023 sin una spec propia.
- **Diagramas:** 5 HTML + 5 PNG de casos de uso en `docs/diagramas/`, 8 diagramas 4+1 en `docs/diagramas/4+1-kruchten/` y 12 flujos por actor en `docs/diagramas/flujos-actores/`.
- Hallazgo abierto: la semilla no trae Administrador `+clerk_test`; aviso de accesibilidad en el buscador operativo de inventario.
