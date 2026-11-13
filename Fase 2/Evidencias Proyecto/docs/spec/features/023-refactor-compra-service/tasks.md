# Tareas — Feature 023: Refactor incremental de `compra_service`

**Feature:** `023-refactor-compra-service/`
**Spec:** [spec.md](spec.md) · **Plan:** [plan.md](plan.md)
**Regla:** T2 mueve verbatim; T3 deduplica con la suite en verde.

## T1 — Línea base, contrato y roadmap

- [x] Correr `pytest` completo y registrar la línea base (**1499 passed/88 skipped**).
- [x] Correr las suites focalizadas `test_compras.py`, `test_cobertura_021.py` y `test_compras_endpoints_020.py`.
- [x] Correr `ng test` y confirmar **549 SUCCESS**.
- [x] Crear `backend/tests/services/test_compra_service_estructura.py` con paquete, módulos, fachada y firmas.
- [x] Ejecutar el test nuevo y confirmar el **rojo esperado** (`compra_service` aún no tiene `__path__`).
- [x] Registrar la 023 en `docs/spec/roadmap.md` (índice y Sprint 7 con `[ ]`, sin mover 015/016 ni el Hito 2).

## T2 — Paquete con fachada (movimiento verbatim)

- [x] Crear `backend/app/services/compra_service/` con `__init__.py`, `_comun.py`, `necesidades.py`, `cobertura.py`, `proveedores.py`, `ordenes.py` y `recepcion.py`.
- [x] Mover constantes, DTO y helpers a `_comun.py`; proveedores a `proveedores.py`; órdenes a `ordenes.py`; simulación y necesidades a `necesidades.py`; preview y cobertura greedy a `cobertura.py`; recepción a `recepcion.py`.
- [x] Escribir la fachada `__init__.py` con los 14 símbolos públicos, `SimulacionTicketProducto`, `_simular_claves` y `__all__`.
- [x] Borrar `backend/app/services/compra_service.py` y `backend/app/services/__pycache__/compra_service*.pyc`.
- [x] Verificar que el grafo de imports es acíclico y que ningún módulo importa la fachada.
- [x] Correr el test de contrato y las suites focalizadas; luego `pytest` completo (**1502 passed/88 skipped**).

## T3 — Deduplicación interna

- [x] Añadir `_opciones_orden()` en `_comun.py` y usarla en `_cargar_orden` y `listar_ordenes_compra`.
- [x] Añadir `_validar_entrada_orden()` en `ordenes.py` y usarla en `crear_orden_compra` y `actualizar_orden_compra`.
- [x] Confirmar que el orden `sede → proveedor → ítems → réplica` y el `flush` se conservan.
- [x] Correr suites focalizadas y `pytest` completo (**1502 passed/88 skipped**).

## T4 — Cierre y evidencia

- [x] `pytest` completo en verde (**1502 passed/88 skipped/0 failed**).
- [x] `ng test` en **549 SUCCESS** y `ng build` limpio.
- [x] Verificar `/openapi.json`: **75** operaciones y **73** de negocio.
- [x] Verificar áreas protegidas con `git diff --stat`: `database/`, `backend/app/models/`, `backend/app/core/permisos.py`, `frontend/` y `.env` sin cambios.
- [x] Confirmar versión `021.1` y 27/24 tablas.
- [x] Recorrido funcional en **4200**: necesidades, alta/emisión de OC, factura y recepción sin errores de consola.
- [x] Humo en **8080** con el build congelado: módulo Compras y API de compras responden; sin errores nuevos.
- [x] Documentar el patrón «paquete con fachada» en `docs/spec/stack.md`.
- [x] Escribir `evidencia/README.md` con suites, OpenAPI, diff protegido y recorridos.
- [x] Actualizar `MEMORY.md` y `grep` de coherencia sobre `AGENTS.md`, `MEMORY.md` y `.agents/skills/`.
- [x] Marcar `spec.md` §5 con evidencia, `tasks.md` completo y `roadmap.md` en `[x]` con fecha de cierre.
