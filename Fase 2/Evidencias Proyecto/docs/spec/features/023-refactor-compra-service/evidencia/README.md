# Evidencia — Feature 023: Mantenimiento técnico II

**Fecha de cierre:** 13/Nov/2026
**Alcance:** refactor incremental de `backend/app/services/compra_service.py` a
un paquete con fachada, sin cambio de comportamiento ni de contrato HTTP.
**Cuentas QA usadas:** `admin020.test+clerk_test@example.com` (Administrador) y
`bodeguero.test+clerk_test@example.com` (Roberto Díaz, Bodeguero de Sede Maipú),
con el código de prueba de Clerk `424242`. No se transcriben tokens ni secretos.

## 1. Línea base (T1)

| Suite | Resultado base |
|---|---|
| `pytest -q` | **1499 passed, 88 skipped, 0 failed** |
| `ng test --watch=false --browsers=ChromeHeadless` | **549 SUCCESS** |
| `ng build` | Limpio |
| Operaciones | 73 de negocio, 75 en `/openapi.json` |

El test de contrato `backend/tests/services/test_compra_service_estructura.py`
se creó antes del movimiento y falló como estaba previsto: 2 de sus 3 pruebas
(no existía `__path__` ni `__all__`). Ese rojo caracterizó el estado inicial.

## 2. Paquete con fachada (T2)

Se eliminó `backend/app/services/compra_service.py` (y su `.pyc`) y se creó el
paquete con siete archivos:

| Módulo | Líneas | Responsabilidad |
|---|---:|---|
| `__init__.py` | 42 | fachada: reexporta 14 símbolos públicos, `SimulacionTicketProducto` y `_simular_claves`; declara `__all__` |
| `_comun.py` | 194 | constantes, DTO, errores, carga de OC y proyección |
| `necesidades.py` | 381 | `_simular_claves`, institución del actor y consolidado |
| `cobertura.py` | 173 | preview y cobertura greedy de pedidos |
| `proveedores.py` | 101 | catálogo global y réplica tenant |
| `ordenes.py` | 291 | ciclo de la OC |
| `recepcion.py` | 207 | recepción ACID y desbloqueo |

Los cuerpos se movieron verbatim. El módulo plano tenía **1420 líneas**; el
paquete suma **1389** repartidas en los siete archivos. El grafo quedó acíclico
(`_comun ← necesidades ← cobertura ← recepcion`; `proveedores` y `ordenes`
dependen de `_comun`; `ordenes` también de `necesidades` y `proveedores`).
Ningún módulo importa la fachada.

**Smoke de importación:** `compra_service.__file__` termina en
`compra_service/__init__.py`; `_simular_claves.__module__` es
`app.services.compra_service.necesidades`; `__all__` tiene 16 nombres.

**Incidencia corregida dentro de T2:** `recepcion.py` no importaba `_FACTURADA`.
Las suites focalizadas lo detectaron (5 fallos) y se corrigió el import antes de
cerrar la tarea. Un chequeo AST de nombres globales no resueltos quedó limpio en
los siete módulos.

## 3. Deduplicación (T3)

| Helper | Única definición | Consumidores |
|---|---|---|
| `_opciones_orden()` | `_comun.py` | `_cargar_orden` y `listar_ordenes_compra` |
| `_validar_entrada_orden()` | `ordenes.py` | `crear_orden_compra` y `actualizar_orden_compra` |

Se conserva el orden `sede → proveedor → ítems → réplica`, que define la
precedencia de los 409/404 y el `flush` del tenant. Las suites focalizadas
quedaron en **85 passed**.

## 4. Suites finales

| Suite | Resultado |
|---|---|
| `pytest -q` | **1502 passed, 88 skipped, 0 failed** (1499 previos + 3 de contrato) |
| `pytest tests/api/test_compras.py tests/api/test_cobertura_021.py tests/api/test_compras_endpoints_020.py -q` | **85 passed** |
| `pytest tests/services/test_compra_service_estructura.py -q` | **3 passed** |
| `ng test --watch=false --browsers=ChromeHeadless` | **549 SUCCESS** |
| `ng build` | Limpio, sin avisos de presupuesto |

`frontend/` no cambió en la 023; sus suites y el build se ejecutaron como
regresión de cierre y se mantuvieron idénticos a la línea base.

## 5. Contrato y áreas protegidas

| Verificación | Resultado |
|---|---|
| `MATRIZ_PERMISOS` | **73** operaciones de negocio |
| `GET /openapi.json` en vivo | **75** operaciones (73 de `/api/v1` + `GET /` + `GET /health`) |
| `database/`, `backend/app/models/`, `backend/app/core/permisos.py`, `.env` | **Sin cambios** (`git status`/`git diff` vacíos) |
| Versión y tablas | `021.1`, **27** de control / **24** por tenant |
| Rutas y textos | Sin cambios; el test de contrato fija firmas, keyword-only y defaults |

El diff de `frontend/` que aparece en el árbol pertenece a la Feature 022
(cerrada el 12/Nov/2026). La 023 no tocó `frontend/`.

## 6. Recorrido funcional — 4200

Sesión de Administrador para el ciclo de compras y sesión de Bodeguero para la
recepción.

| Paso | Comprobación |
|---|---|
| `/compras/necesidades` | Consolidado por sede y producto; enlace «Crear OC» precargado. |
| `/compras/nueva` (Sede Providencia) | OC #2: Papelera del Pacífico, Clip Métrico 33 mm × 19 a $150 = **$2.850**. |
| Emisión | **`OC-2026-000002`** con 1 asignación de pedido. |
| Factura | **`F-023-0001`**; la OC queda `Facturada`. |
| `/compras/nueva` (Sede Maipú) | OC #3: Clip Métrico 33 mm × 10 a $150 = **$1.500**. |
| Emisión y factura | **`OC-2026-000003`** emitida y facturada con **`F-023-0002`**. |
| `/compras/recepcion` (Bodeguero) | Solo la OC facturada de su sede; confirmación → «Orden de compra recepcionada exitosamente» y lista vacía. |

Verificación en PostgreSQL del tenant `tenant_inst_001_038aa2a9`:

| Dato | Valor |
|---|---|
| `orden_compra` 3 | `OC-2026-000003`, estado `Recibida`, total `1500.00`, `fecha_recepcion 2026-11-13 00:26:24` |
| `factura_compra` | `F-023-0002`, `1500.00`, `2026-11-13` |
| `movimiento_inventario` 13 | `ENTRADA` de **10**, glosa con OC, factura y Bodeguero |
| `stock_sede` (producto 5, sede 2) | **45** (subió 10) |

**Consola:** solo el aviso preexistente de Clerk en claves de desarrollo. Sin
errores nuevos.

## 7. Humo — 8080

El frontend de 8080 no se reconstruyó porque la 023 no toca `frontend/`; el
humo usó el build congelado y el backend con recarga automática.

| Vista | Comprobación |
|---|---|
| `/compras` | Listado de OC con `OC-2026-000001` (Recibida) y la API de compras respondiendo. |
| `/compras/necesidades` | Consolidado cargado con las filas de la institución. |

**Consola:** solo el aviso preexistente de Clerk. Sin errores nuevos.

## 8. Diff

- **Eliminado:** `backend/app/services/compra_service.py` y su bytecode.
- **Nuevo:** `backend/app/services/compra_service/` con los siete módulos.
- **Nuevo:** `backend/tests/services/test_compra_service_estructura.py`.
- **Nuevos:** `docs/spec/features/023-refactor-compra-service/` (`spec.md`,
  `plan.md`, `tasks.md` y esta evidencia).
- **Modificados:** `docs/spec/roadmap.md`, `docs/spec/stack.md`, `MEMORY.md`.

## 9. Criterios de aceptación

| AC | Evidencia |
|---|---|
| AC-1 | Paquete con `__path__`, `__init__.py` y los seis módulos; el `.py` plano no existe. Test de contrato en verde. |
| AC-2 | `__all__` con los 16 nombres; `ticket_service` y `test_cobertura_021.py` sin cambios y en verde. |
| AC-3 | `test_las_firmas_publicas_y_el_dto_no_cambian`: 15 firmas, keyword-only y defaults. |
| AC-4 | **1502 passed, 88 skipped, 0 failed**; focalizadas de compras **85 passed**. |
| AC-5 | `_opciones_orden()` y `_validar_entrada_orden()` con sus consumidores únicos. |
| AC-6 | **73/75** operaciones, `021.1`, **27/24** tablas; `database/`, `models/`, `permisos.py` y `.env` sin cambios. |
| AC-7 | Nota del patrón en `stack.md`; roadmap, `MEMORY.md` y `grep` de coherencia. |
| AC-8 | `ng test` **549 SUCCESS**, `ng build` limpio, recorrido 4200 y humo 8080 sin errores nuevos. |
