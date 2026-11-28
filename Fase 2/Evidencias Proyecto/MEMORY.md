# MEMORY.md — Diario del Proyecto
Memoria entre sesiones. Máximo ~50 líneas: resume lo útil y elimina lo que ya no aporte.

## Estado actual
- Features **000…014 y 017…028 cerradas**; **015** (informes) y **016** (notificaciones) siguen pendientes en el Sprint 7. La **enmienda funcional de la 012** se **cerró el 27/Nov/2026**: AC-20…AC-41 evidenciados en `012-gestion-administrativa/evidencia/README.md`.
- **028 (tiempo real) cerrada el 28/Nov/2026 con `@reviewer` APROBADO:** SSE `GET /api/v1/eventos/` + bus Redis efímero; tablero, detalle y dashboard se refrescan sin recargar. **4200:** AC-9 (alta visible), AC-11 (Media→Alta), AC-10 (aprobación→retiro→confirmación→«Entregado»), AC-12 (dashboard ≤5 s), AC-14 (filtros/diálogo intactos) y AC-13 (OC + recepción → `stock_disponible=true` y «Registrar retiro»). **8080:** imagen `3974188a383e`, actualización en vivo por nginx. Excepciones aceptadas: T0/DT-17, manual de dos workers, `curl -N` autenticado, AC-4 60 s/consola y sin capturas.
- **Enmienda 018 «Solo con stock» cerrada el 27/Nov/2026:** checkbox de presentación visible para Administrador, Bodeguero y Solicitante (D-11); filtra en cliente `stock_total > 0` dentro de `insumosCoincidentes` (arrastra el panel de categorías), no mueve la franja, se limpia con «Limpiar filtros» y tiene vacío propio con precedencia. Sin cambios de API, contrato, matriz ni DDL (`stack.md` intacto). Evidencia en `018-filtro-inventario-sede-departamento/evidencia/README.md` §12.
- **Enmienda 012 — decisión:** `control` **25** tablas / tenant **22**, token **`026.1`**, **21** entidades de dominio **sin** `departamento_encargado`. Matriz **73** / OpenAPI **75** (73 v1 + `GET /` + `/health`); frontend con **3 pestañas**: Sedes, Departamentos, Usuarios.
- **Enmienda 012 — reglas:** el rol Bodeguero resuelve en el servidor el departamento **«Suministros»** (crear/reutilizar/reactivar, `sede_id NULL`) y la **Sede es obligatoria** en la interfaz, persistida con `PUT .../sede`; el Solicitante usa la Sede como **filtro** y solo envía `departamento_id`; `departamento_id` es opcional en `UsuarioCrear`/`UsuarioEdicion` y el servicio responde **422** por rol. `gestion_organizacional` se conserva para sedes, departamentos y usuarios.
- **Suites vigentes (28/Nov/2026, cierre 028):** backend SQLite **2323 passed / 135 skipped / 0 failed**; gated PostgreSQL **4 passed** (T13), gated Redis **4 passed** (T14) y seguridad 028 **4 passed**; `ng test` **758 SUCCESS / 0 failed**; `ng build` limpio, bundle **`main-UJT3LSFR.js`**, Initial **348,36 kB**; `/openapi.json` **75/73** y matriz **73**.
- **Base consolidada:** `database/` solo `01_esquema.sql` (25 en control + 22 por tenant) y `02_datos_semilla.sql` (token `026.1`, guardia fail-closed). Sin migraciones: reset = `down -v` + `up -d`.
- **Compatibilidad conservada:** `/auth/me` y `/usuarios/` resolvieron con sesión de tenant (`get_db_negocio`) + control (`get_db`); el 409 del último Administrador activo sigue, y el 409 de baja por encargado ya no existe.
- **Enmienda 013 (26/Nov) cerrada el 27/Nov/2026:** catálogo de cuatro estados (`EnRevision`, `EnCurso`, `Cerrado`, `Anulado`), alta en `EnRevision`, retiro solo del Bodeguero de la sede (`POST /tickets/{id}/retiro`) y anulación `Cerrado → Anulado` solo del Administrador con `ENTRADA` de devolución, bloqueada por la confirmación del Solicitante.
- **Enmienda 004 (27/Nov) cerrada el 28/Nov/2026:** filtro de periodo calendario y orden por columna en el tablero (AC-28…AC-30); **104** tests del tablero; 4200 con Administrador/Solicitante y alta #12, 8080 reconstruido; evidencia en `004-tablero-kanban/evidencia/README.md`.

## Decisiones vigentes (026/025/024/021/020/028)
- **Saldo vigente = `stock_sede`**; `movimiento_inventario.stock_sede_id` es `NOT NULL` y la tabla `inventario` se retiró en la 026.
- **Normalización = `lower(trim(...))`**; el RUT compara forma canónica y conserva el formato visible. **B2 responde 409**, no 500.
- **025:** ventana fija 60 s / 120 IP, fail-open, Redis efímero en `127.0.0.1:6380`. **024:** `/health` liveness, `/ready` con `NullPool`, `/metrics` por red.
- **021:** `orden_compra_ticket` = intención por `(OC, pedido, producto)`; `base = max(0, solicitado - plan_previo - entregado)`. **020:** `proveedor` global con réplica del mismo id; el Bodeguero queda en `Facturada` + su sede.
- **028:** SSE de invalidación, no de datos; sobre interno con institución/dueños que nunca se serializa; frame solo con `dominios`/`motivo`/`estado`; publicación tras commit, best-effort y fail-open (cota 0,5 s); marca `dashboard` sintética; `tenant_service` resuelve la institución en PostgreSQL (T13; SQLite conserva `ambito_service`); una conexión por pestaña y refresco agrupado (250 ms/1 s). **Deuda abierta:** DT-17 (TestClient bufferiza), DT-18 (versión de tenant en el camino sin sesión tenant), DT-19 (lectura post-commit en `ticket_service`) y R-05 (SSE sin métricas).

## Aprendizajes y errores a evitar
- **`TestClient` 1.7 bufferiza SSE:** los tests usan flujos acotados y leen el cuerpo completo; solo el gated PostgreSQL usa `uvicorn` real + `httpx.Client.stream`. **nginx:** `location = /api/v1/eventos/` con `proxy_buffering off` (T21); el dev server de Angular no necesita ajuste.
- **`<select>` con ids numéricos:** `[value]` entrega string; usar `[ngValue]` y normalizar antes de comparar. Los tests con `setValue` numérico no lo detectan: hace falta un caso DOM con `change`.
- **Cierre = verificación** (AGENTS §8.5–§8.7): los dos puertos, `docker compose build frontend` si cambió el frontend, grep de coherencia. **8080 puede reutilizar `index.html` cacheado**: verificar el hash real del bundle; y el contenedor puede seguir con la **imagen anterior** aunque la etiqueta se haya reconstruido: comparar el ID o usar `up -d --force-recreate frontend`.
- **Sesión equivocada en PostgreSQL:** un endpoint de tenant con la sesión de `control` devuelve 401/403 aunque SQLite lo oculte.
- Tests **gated** (`POSTGRES_TEST_URL` / `REDIS_TEST_URL`): SQLite no valida esquemas ni carreras; las unicidades y la concurrencia de «Suministros» solo las acredita PostgreSQL.
- Edge: `CHROME_BIN` + `--watch=false --browsers=ChromeHeadless`; nunca `npm test`. En Windows, `127.0.0.1:6380`, no `localhost` (`::1`).
- **Specs Angular:** con `provideRouter([])` el click de un `routerLink` no actualiza `router.url`; las pestañas ARIA se derivan de `Router.url`.
- **Rejillas del Kanban:** si cambia el número de columnas, ajustar `md:grid-cols-N`; hay regresión DOM por `data-testid="tablero-pedidos"` (3 columnas reales, sin celda vacía).
- **Shell:** el scroll interno de una vista puede contribuir al documento; el shell necesita `overflow-hidden` + `[contain:paint]` y el `nav` `min-h-0 overflow-y-auto`; regresión en `app.component.spec.ts`.
- **MCP locales en Windows:** `npx -y` tarda ~20 s en responder el `initialize`; con el timeout por defecto (30 s) `postgres` y `chrome-devtools` fallan como «Request timed out». `opencode.json` fija `mcp.timeout.startup = 120000`.

## Próximos pasos
- **028 cerrada** el 28/Nov/2026: 32 AC acreditados, `roadmap.md` en `[x]`, evidencia sincronizada y DT-19 registrada. No se relanza validación de `@reviewer`.
- **Sprint 7:** siguen **015** y **016**; **Hito 2** el **11/Dic/2026**. Diagramas en `docs/diagramas/` y deuda técnica en `docs/spec/deuda-tecnica.md`.
