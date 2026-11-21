# MEMORY.md — Diario del Proyecto
Memoria entre sesiones. Máximo ~50 líneas: resume lo útil y elimina lo que ya no aporte.

## Estado actual
- Features 000…**026 cerradas**. La **026** (salud del esquema BD) se cerró el **18/Nov/2026**; evidencia en `026-salud-esquema-bd/evidencia/README.md`.
- **026:** token `026.0`; control **26** tablas y tenants **23**; **21 entidades**. Se retiró `inventario` y los 14 movimientos legados: quedan 14 saldos `stock_sede` y 3 movimientos (producto 5 = 45, producto 9 = 12). 15 índices P0 + 2 heredados, 6 unicidades B2, U-07 PG-only y K-01…K-04. Al cierre: backend **1659 passed/105 skipped**, gated PG **1761/3**, gated Redis **1662/102**, frontend **549 SUCCESS**, OpenAPI **75** operaciones.
- **Enmienda 008 (20/Nov/2026):** `/auth/me` publica `sede` y `departamento` derivados por rol (D-9); la cabecera muestra `Sede` a Bodeguero/Solicitante y `Departamento` al Solicitante, con `—` si la asignación falta (D-10); Admin/Superadmin sin badges nuevos. Sin DDL. Backend **1667 passed/105 skipped**, frontend **556 SUCCESS**, 4200 con los cuatro roles y 8080 reconstruido. Evidencia en `008-particionamiento-institucional/evidencia/enmienda-contexto-organizacional.md`.
- **Base consolidada:** `database/` solo `01_esquema.sql` (26 en control + 23 por tenant) y `02_datos_semilla.sql` (`026.0`, guardia fail-closed). Sin migraciones: reset = `down -v` + `up -d`.
- **Cierre 026:** 4200 con 409 por duplicado (sede, departamento, RUT, correo), movimiento por `stock_sede_id` (201) y legado (422), dashboard sin campos legados; 8080 con imagen reconstruida y 8 rutas directas OK.
- **024/023/022/021 cerradas:** hardening (`X-Request-ID`, `/ready`, `/metrics`, 429 nginx, `URL_API=/api/v1`), `compra_service` como paquete con fachada y `orden_compra_ticket` como intención de cobertura. Detalle en la evidencia de cada feature.
- **Flujos por actor (11/Nov/2026):** 12 diagramas HTML+PNG en `docs/diagramas/flujos-actores/`.

## Feature 026 — decisiones clave
- **El saldo vigente es `stock_sede`:** `movimiento_inventario.stock_sede_id` es `NOT NULL`; la única FK retirada murió con `inventario`.
- **Normalización = `lower(trim(...))`:** solo recorta espacios exteriores; los internos distinguen (`"sede   providencia"` ≠ `"sede providencia"`). El RUT compara forma canónica sin puntos/guion/espacios pero **conserva el formato visible**.
- **U-07 (`UNIQUE ((true))` sobre `version_esquema`) es PG-only:** no está en el ORM; lo aplica `control_service._crear_indice_version_unica`.
- **Expresiones portables:** solo `lower`, `trim`, `upper`, `replace`; nunca `btrim` ni `regexp_replace`.
- **B2 responde 409, no 500:** pre-check normalizado **y** captura de `IntegrityError`.

## Decisiones vigentes (025/024/021/020)
- **025:** ventana fija 60 s / 120 IP, fail-open, Redis efímero en `127.0.0.1:6380`; middleware observabilidad → CORS → limitador; métricas por proceso (un worker).
- **024:** `/health` liveness sin BD; `/ready` readiness con `NullPool`; `/metrics` protegido por red; log JSON sin `--access-log`.
- **021:** `orden_compra_ticket` = intención por `(OC, pedido, producto)`; `base = max(0, solicitado - plan_previo - entregado)`; `Recibida` ya está en stock y `Cancelada` no cubre. `Cerrado` sigue siendo el despacho.
- **020:** `control.proveedor` global con réplica del mismo `proveedor_id`; el Bodeguero queda forzado a `Facturada` + su sede.

## Aprendizajes y errores a evitar
- **Filtro de lista ≠ recurso:** `sede_id` en `/inventario/existencias` responde 200/`[]`; el detalle usa `stock_sede`.
- Cierre = verificación (AGENTS §8.5–§8.7): los dos puertos, `docker compose build frontend` si cambió el frontend, grep de coherencia.
- **Mover un módulo a paquete:** borrar `.py` y `.pyc` en la misma tarea.
- **8080 tras rebuild:** el navegador puede reutilizar `index.html` cacheado y cargar el `main-*.js` viejo; verificar el hash real y recargar con `ignoreCache` antes de concluir que la imagen no se actualizó.
- **Árbol revertido por un proceso externo:** revisar `git stash list` y `git reflog` antes de rehacer.
- **Contratos externos:** `GET /v1/invitations` de Clerk devuelve lista desnuda; la semilla limpia no crea Superadmin.
- Tests **gated** (`POSTGRES_TEST_URL` / `REDIS_TEST_URL`): SQLite no valida esquemas ni FK compuestas; al subir el esquema, actualizar los snapshots gated.
- Edge: `CHROME_BIN` + `--watch=false --browsers=ChromeHeadless`; nunca `npm test`. Clerk HTTP: dev browser + sign-in ticket + `Origin: localhost:4200`; tokens ~60 s.
- **redis-py 8.1.0:** `from_url(timeout=...)` no existe; con Redis en `127.0.0.1`, no usar `localhost` (`::1` se cuelga). En Windows el handshake concurrente tarda ~200 ms: el tope de lectura no puede ser 0.2 s.
- **Specs Angular:** con `provideRouter([])` el click de un `routerLink` no actualiza `router.url`; pestañas ARIA se derivan de `Router.url`.
- **Autoría del ticket = identidad de sesión;** la sede sale de `departamento.sede_id`. **Carreras gated:** `Barrier` no fija el orden del lock.

## Próximos pasos
- **Sprint 7 (03/Nov – 11/Dic/2026):** quedan **015** (informes PDF/Excel) y **016** (notificaciones in-app); **027–029** después. **Hito 2** el **11/Dic/2026**.
- **Diagramas:** 5+5 casos de uso, 8 del modelo 4+1 y 12 flujos por actor en `docs/diagramas/`.
- Hallazgo abierto: `admin017.test+clerk_test@example.com` existe en Clerk pero no está mapeado en la BD; aviso de accesibilidad en el buscador operativo de inventario; `/ready` tarda 3–7 s con `db` detenido por DNS de Docker Desktop.
