# Tareas — Feature 022: Mantenimiento técnico I

**Spec:** [spec.md](spec.md) · **Plan:** [plan.md](plan.md)
**Estado:** En implementación
**Regla:** cada casilla se marca solo cuando su criterio de cierre está verificado.

## T1 — Línea base y registro de la feature

- [x] Ejecutar `pytest -q` en `backend/` y registrar el resultado base (esperado: 1496 passed, 88 skipped, 0 failed).
- [x] Ejecutar `ng test --watch=false --browsers=ChromeHeadless` en `frontend/` y registrar el resultado base (esperado: 537 SUCCESS).
- [x] Ejecutar `ng build` y confirmar build limpio.
- [x] Contar operaciones: 73 de negocio en `MATRIZ_PERMISOS` y 75 en `/openapi.json` (incluye `/` y `/health`).
- [x] Confirmar que `docs/spec/features/022-mantenimiento-tecnico/` contiene `spec.md`, `plan.md` y `tasks.md`.
- [x] Registrar la Feature 022 en el índice y en el Sprint 7 de `docs/spec/roadmap.md`, sin mover 015/016 ni el Hito 2.

**Cierre T1:** línea base documentada y feature registrada; ninguna casilla de implementación tocada. **Verificado (12/Nov/2026):** backend 1496 passed/88 skipped/0 failed; frontend 537 SUCCESS; `ng build` limpio; 73 operaciones de negocio y 75 en OpenAPI.

## T2 — Borrar el servicio muerto

- [x] Confirmar que `UsuarioService` y `usuario.service` solo se referencian a sí mismos en `frontend/src`.
- [x] Eliminar `frontend/src/app/features/administracion/services/usuario.service.ts`.
- [x] Corregir en `docs/spec/stack.md` la referencia `usuario.service.ts` → `administracion.service.ts`.
- [x] Verificar `grep -r "UsuarioService\|usuario.service" frontend/src` → 0 resultados.
- [x] Ejecutar `ng build` y confirmar que compila sin errores.

**Cierre T2:** archivo eliminado, sin referencias y build limpio. **Verificado:** 0 referencias; `ng build` completo en 21 s.

## T3 — Coherencia documental

- [x] Actualizar `AGENTS.md` §4: `shared/` como `(components, config, interfaces, utils)` y `public/` en lugar de `src/assets/`.
- [x] Actualizar `docs/spec/stack.md`: árbol de frontend con `public/`, `shared/components/`, `shared/utils/` y las seis features de negocio.
- [x] Reescribir la Nota 1 de `stack.md` (seis features, no «cuarta feature»; `auth` y `acceso-denegado` como soporte sin `routes.ts` propio).
- [x] Reescribir la Nota 2 de `stack.md` (`shared/components/` existente con consumidores; `shared/pipes/` inexistente; `shared/utils/` para helpers).
- [x] Actualizar `README.md` raíz: 27 tablas de `control`, 24 por tenant y versión `021.1`.
- [x] Reemplazar `frontend/README.md` por contenido propio del proyecto (4200/8080, tests, estructura, `public/`).
- [x] Ejecutar `grep` de coherencia en las secciones de estructura/estado actual: sin `src/assets`, `usuario.service.ts` ni «cuarta feature». Las menciones históricas a `013.1`, `20` o `17` tablas dentro de la crónica de features se conservan porque documentan versiones pasadas.

**Cierre T3:** los cuatro documentos describen la estructura y la base reales; no quedan referencias obsoletas en las secciones vigentes. **Verificado:** `AGENTS.md` y `stack.md` sin `src/assets`, `usuario.service.ts` ni «cuarta feature»; README raíz con 27/24 y `021.1`.

## T4 — Dedup frontend de errores HTTP (test primero)

- [x] Crear `frontend/src/app/shared/utils/errores-http.spec.ts` con los casos de `detail` textual, `detail` no textual, 401/403/404/409/422/503/0/default y los textos literales de los seis helpers.
- [x] Confirmar que el spec falla antes de crear el helper (rojo).
- [x] Crear `frontend/src/app/shared/utils/errores-http.ts` con `mensajeDeErrorHttp` y `MensajesDeErrorHttp`.
- [x] Hacer que `mensajeDeErrorAdministracion` delegue conservando nombre, firma y textos.
- [x] Hacer que `mensajeDeErrorCompras` delegue conservando nombre, firma y textos.
- [x] Hacer que `mensajeDeErrorControl` delegue conservando nombre, firma y textos.
- [x] Hacer que `mensajeDeErrorCatalogo` delegue conservando nombre, firma y textos.
- [x] Hacer que `mensajeDeErrorProducto` delegue conservando nombre, firma y textos.
- [x] Hacer que `mensajeDeErrorTickets` delegue conservando nombre, firma y textos.
- [x] Ejecutar el spec nuevo y confirmar verde.
- [x] Ejecutar la suite completa de `ng test` y confirmar 537 previos + nuevos, 0 fallos.
- [x] Ejecutar `ng build` y confirmar build limpio.

**Cierre T4:** una sola implementación estructural, seis helpers con textos idénticos y suite/build verdes. **Verificado (12/Nov/2026):** rojo inicial por módulo ausente; tras el helper, **549 SUCCESS**; `ng build` completo en 21.5 s.

## T5 — Dedup backend de `_correo_actor` (test primero)

- [x] Crear `backend/tests/services/test_auth_service.py` con los casos identidad ausente, usuario ausente y correo con espacios/mayúsculas.
- [x] Confirmar que el test falla antes de crear `correo_del_actor` (rojo).
- [x] Añadir `correo_del_actor` a `backend/app/services/auth_service.py`.
- [x] Eliminar `_correo_actor` de `backend/app/services/organizacion_service.py` y reemplazar sus llamadas.
- [x] Eliminar `_correo_actor` de `backend/app/services/usuario_service.py` y reemplazar sus llamadas.
- [x] Ejecutar `pytest tests/services/test_auth_service.py -q` y confirmar verde.
- [x] Ejecutar `pytest -q` completo y confirmar 1496 previos + nuevos en verde, 88 skipped, 0 fallos.

**Cierre T5:** una sola implementación de la regla, sin duplicados y suite completa verde. **Verificado (12/Nov/2026):** rojo inicial por `ImportError`; test focalizado 3 passed; suite completa **1499 passed, 88 skipped, 0 failed**; 0 referencias a `_correo_actor`.

## T6 — Cierre

- [x] Ejecutar `pytest -q` completo y registrar el conteo final.
- [x] Ejecutar `ng test --watch=false --browsers=ChromeHeadless` completo y registrar el conteo final.
- [x] Ejecutar `ng build` y confirmar build limpio.
- [x] Verificar 73 operaciones de negocio en la matriz, 75 en `/openapi.json` y sin cambios de rutas/métodos/`response_model`.
- [x] Verificar con `git diff --stat` que no cambiaron `database/`, `backend/app/core/permisos.py`, `backend/app/models/`, la versión `021.1` ni los textos de UI.
- [x] Recorrido funcional en `http://localhost:4200` con sesión QA y sin errores de consola.
- [x] Reconstruir la imagen (`docker compose build frontend` + `up -d frontend`) y hacer humo en `http://localhost:8080`.
- [x] Crear `docs/spec/features/022-mantenimiento-tecnico/evidencia/README.md` con suites, build, OpenAPI, diff y recorrido.
- [x] Marcar los AC de `spec.md` con su evidencia.
- [x] Actualizar `MEMORY.md` con estado, decisiones y errores a evitar.
- [x] Marcar la Feature 022 como `[x]` en `docs/spec/roadmap.md`.
- [x] Ejecutar `grep` de coherencia sobre `AGENTS.md`, `MEMORY.md` y `.agents/skills/`.

**Cierre T6:** todos los AC verificados, evidencia publicada, memoria actualizada y 4200/8080 recorridos. **Verificado (12/Nov/2026):** backend 1499/88/0; frontend 549 SUCCESS; build limpio; 73/75 operaciones; diff sin áreas protegidas; 4200 y 8080 sin errores nuevos; grep de coherencia limpio.
