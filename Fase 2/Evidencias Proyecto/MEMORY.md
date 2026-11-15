# MEMORY.md — Diario del Proyecto
Memoria entre sesiones. Máximo ~50 líneas: resume lo útil y elimina lo que ya no aporte.

## Estado actual
- Features 000…**024 cerradas**; la **024** el **15/Nov/2026**, la **023** el **13/Nov/2026**, la **022** el **12/Nov/2026**, la **021** el **08/Nov/2026**, la **020** el **04/Nov/2026**, la **019** el **22/Oct/2026**, la **018** el **21/Oct/2026**, la **014** y la **017** el **20/Oct/2026**, la **013** el **19/Oct/2026**.
- **024 (hardening operativo I) CERRADA:** `X-Request-ID` + log JSON, `/ready`, `/metrics`, CORS por entorno, límites nginx con 429 JSON, `URL_API=/api/v1` + `proxy.conf.json`. Backend **1596 passed/88 skipped**, gated **73 passed**, frontend **549 SUCCESS**, build limpio, 73/75 OpenAPI, `021.1` y 27/24 tablas; diff protegido solo `url-api.ts`. Evidencia en `024-hardening-operativo/evidencia/README.md`.
- **023 (mantenimiento técnico II) CERRADA:** `compra_service` es paquete con fachada (`__init__`, `_comun`, `necesidades`, `cobertura`, `proveedores`, `ordenes`, `recepcion`); se conservan ruta, 16 símbolos, `_simular_claves`, firmas y contrato. Dedup de `_opciones_orden` y `_validar_entrada_orden`.
- **022 (mantenimiento técnico I) CERRADA:** eliminado el servicio HTTP muerto de administración, corregidos `AGENTS.md`/`stack.md`/README raíz/`frontend/README.md`, deduplicados los seis `mensajeDeError*` y `_correo_actor`.
- **021 (cobertura automática por OC) CERRADA:** `orden_compra_ticket` (22.ª entidad), plan congelado al emitir, necesidad neta parcial con `stock_comprometido`/`stock_borrador`, preview de cobertura (matriz 72→73) y cadena por producto. Versión `021.1`, 27/24 tablas.
- **020 (reabastecimiento externo y compras):** 21 entidades, séptima capacidad `compras`, matriz 62→72, catálogo global de proveedores replicado por `proveedor_id`, `numero_oc` derivado del identity y `stock_disponible` calculado.
- **019/018/014/017/013:** detalle de producto por alcance (matriz 62), filtro `sede_id` (61), ciclo de vida del catálogo (55→60, historiales 16.ª/17.ª), invitaciones Clerk y gobierno de Administradores (55), y ciclo de vida del pedido con `Anulado` e historial inmutable (15.ª entidad, 49). Enmiendas post-cierre: T-17 (pestañas ARIA de `/administracion`) y AC-27 de la 013.
- **Base consolidada (08/Nov/2026):** `database/` tiene solo `01_esquema.sql` (control **27** tablas + **24** por tenant) y `02_datos_semilla.sql` (`021.1`, 28 capacidades, 3 proveedores, guardia fail-closed). Sin migraciones: reset = `down -v` + `up -d`.
- **Flujos por actor (11/Nov/2026):** 12 diagramas HTML+PNG en `docs/diagramas/flujos-actores/` e informe `docs/informes/Informe_Flujos_Actores.docx` (38 páginas). Publicado en `origin/main` y `origin/ricardo`.

## Feature 024 — decisiones clave
- **Observabilidad:** middleware ASGI puro; CORS dentro y observabilidad fuera; `X-Request-ID` validado; plantilla de ruta reconstruida tras el anidado de routers de FastAPI 0.142; log JSON con stdlib y `--no-access-log` para no duplicar.
- **Salud:** `/health` es liveness sin BD; `/ready` es readiness con motor `NullPool`, `connect_timeout=1` y `statement_timeout=1500 ms`, fuera de OpenAPI y de la matriz.
- **Métricas:** `prometheus-client` con `CollectorRegistry` propio, cinco familias, `route` como plantilla, sin PII y sin autoinstrumentación; `/metrics` se protege **por red** (nginx 404), no por rol.
- **Borde y SPA:** `/api/` con 10 r/s, `burst=20 nodelay` y `limit_conn 20`; 429 JSON con `detail` y ACAO solo en esa respuesta; la SPA llama `/api/v1` por proxy en 4200 y por nginx en 8080.

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
- Tests PostgreSQL **gated** (`POSTGRES_TEST_URL`); SQLite no valida esquemas/namespaces ni FK compuestas. El gated debe cablear `abrir_sesion_tenant=crear_sesion_esquema`. Toda mutación exige actor persistido. **Al subir el esquema, actualizar los snapshots gated** (27/24, `021.1`): quedaron rojos desde la 021 y se corrigieron en la 024.
- Edge: `CHROME_BIN` + `--watch=false --browsers=ChromeHeadless` (nunca `npm test`). Clerk por HTTP: dev browser + sign-in ticket BAPI + `Origin: localhost:4200`; tokens ~60 s.
- **Detalle del pedido con scroll interno:** `take_screenshot(fullPage)` no incluye la cobertura; hacer `scrollIntoView` antes de capturar. **Specs Angular:** con `provideRouter([])` el click de un `routerLink` no actualiza `router.url` (probar el `href`). Pestañas ARIA sobre Router: derivar de `Router.url` y activar con `RouterLink`.
- **Autoría del ticket = identidad de sesión:** no validar `usuario_id` del alta; la sede sale de `departamento.sede_id`. **Carreras gated:** `Barrier` no fija el orden del lock; la poseedora confirma con `threading.Event`.

## Próximos pasos
- **Sprint 7 (03/Nov/2026 – 11/Dic/2026):** 020, 021, 022, 023 y 024 cerradas; siguen **015** informes PDF/Excel y **016** notificaciones in-app. Orden acordado: **025** (hardening operativo II) antes de 015/016; 026–029 después. **Hito 2** el **11/Dic/2026**.
- **Siguiente trabajo:** abrir la 025 con su spec; no reabrir la limpieza de 022 ni el refactor de 023 sin una spec propia.
- **Diagramas:** 5 HTML + 5 PNG de casos de uso en `docs/diagramas/`, 8 diagramas 4+1 en `docs/diagramas/4+1-kruchten/` y 12 flujos por actor en `docs/diagramas/flujos-actores/`.
- Hallazgo abierto: la semilla no trae Administrador `+clerk_test`; aviso de accesibilidad en el buscador operativo de inventario. `/ready` con `db` detenido tarda 3–7 s por DNS de Docker Desktop (no es la cota de AC-10).
