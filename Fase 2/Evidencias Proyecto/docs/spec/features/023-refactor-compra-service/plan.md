# Plan de implementación — Feature 023: Refactor incremental de `compra_service`

**Feature:** `023-refactor-compra-service/`
**Spec:** [spec.md](spec.md)
**Enfoque:** cuatro tareas secuenciales; T2 mueve código verbatim y T3 deduplica con la suite en verde.
**Regla:** no se reabre la limpieza de la Feature 022. Este plan toca únicamente `backend/app/services/compra_service*`, su test de contrato y la documentación de cierre.

## 1. Orden de ejecución

```text
T1 línea base + test de contrato (rojo) + roadmap
  → T2 paquete con fachada (movimiento verbatim)
  → T3 dedup de opciones de OC y validación de entrada
  → T4 cierre: suites, OpenAPI, diff protegido, 4200/8080, evidencia
```

T1 fija el contrato antes de mover nada. T2 y T3 son fases separadas: si T3
introduce una regresión, se revierte sin perder el movimiento. Cada tarea deja
la suite completa en verde (salvo el rojo deliberado del test de contrato en T1).

## 2. Línea base y contrato (T1)

### 2.1 Backend

```powershell
cd backend
.venv/Scripts/python.exe -m pytest -q
```

Esperado: `1499 passed, 88 skipped, 0 failed`. Los tests gated de PostgreSQL se
omiten sin `POSTGRES_TEST_URL`.

Suites focalizadas de referencia:

```powershell
.venv/Scripts/python.exe -m pytest -q tests/api/test_compras.py tests/api/test_cobertura_021.py tests/api/test_compras_endpoints_020.py
```

### 2.2 Frontend

```powershell
cd frontend
$env:CHROME_BIN = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
npx ng test --watch=false --browsers=ChromeHeadless
```

Esperado: `549 SUCCESS`. El refactor no toca `frontend/`; esta línea base solo
confirma que el cierre parte del mismo estado que dejó la 022.

### 2.3 Test de contrato estructural

Archivo nuevo: `backend/tests/services/test_compra_service_estructura.py`.

Fija tres cosas sin probar comportamiento de negocio:

1. **Paquete.** `compra_service` tiene `__path__`, su `__file__` termina en
   `__init__.py`, viven los siete archivos esperados y ya no existe
   `backend/app/services/compra_service.py`.
2. **Fachada.** Reexporta los 14 símbolos públicos más `SimulacionTicketProducto`
   y `_simular_claves`.
3. **Firmas.** Nombre, tipo de parámetro y valor por defecto de las 15 funciones:
   `estado` y `sede_id` keyword-only; `sede_id=None`, `producto_ids=None`,
   `cantidades_oc=None`, `bloquear=False`.

En T1 el test **debe fallar** en la primera aserción (`compra_service` todavía es
un módulo, no un paquete). Ese rojo es la caracterización del estado actual, no
una regresión.

### 2.4 Registro en el roadmap

- Fila nueva `023` en el índice de especificaciones con estado `[ ]`.
- Viñeta nueva en el Sprint 7 con `[ ]`.
- Nota en la línea de «Siguiente feature»: la 023 está en curso y no altera el
  orden 015/016 ni el Hito 2 (11/Dic/2026).

## 3. Paquete con fachada (T2)

### 3.1 Archivos

```text
backend/app/services/compra_service/
├── __init__.py        # fachada: reexporta la API pública y __all__
├── _comun.py          # constantes, DTO, errores, helpers, carga y proyección de OC
├── necesidades.py     # _simular_claves, institución del actor, consolidado
├── cobertura.py       # preview de compra y cobertura greedy de pedidos
├── proveedores.py     # catálogo global y réplica tenant
├── ordenes.py         # listado, alta, edición, emisión, factura y cancelación
└── recepcion.py       # recepción ACID y desbloqueo de pedidos
```

Se elimina `backend/app/services/compra_service.py` y su bytecode
`backend/app/services/__pycache__/compra_service*.pyc` en la misma tarea.

### 3.2 Reparto verbatim

| Origen (líneas actuales) | Destino |
|---|---|
| 72–106 (constantes y `SimulacionTicketProducto`) | `_comun.py` |
| 113–341 (errores y helpers) | `_comun.py`, salvo `_proveedor_activo_control`, `_replicar_proveedor`, `_total_orden` y `_agregar_detalles` |
| 348–721 (`_simular_claves`, institución, necesidades) | `necesidades.py` |
| 728–821 (`previsualizar_cobertura`) | `cobertura.py` |
| 828–879 (proveedores) | `proveedores.py` |
| 886–1155 (órdenes) | `ordenes.py` |
| 1163–1231 (`calcular_cobertura_tickets`) | `cobertura.py` |
| 1238–1420 (recepción) | `recepcion.py` |
| `_proveedor_activo_control`, `_replicar_proveedor` | `proveedores.py` |
| `_total_orden`, `_agregar_detalles` | `ordenes.py` |

Los cuerpos de función se mueven sin reescribir: mismos textos, mismas
consultas, mismos `ORDER BY`, mismos `commit`/`flush`, mismos valores de retorno.
Solo cambian los imports de cada módulo y la cabecera documental.

### 3.3 Grafo de imports

```text
_comun  ←  necesidades  ←  cobertura  ←  recepcion
   ↑            ↑
   └── proveedores
   └── ordenes ─┘
```

- `_comun` no importa módulos de flujo.
- `proveedores` importa `_comun`.
- `necesidades` importa `_comun`.
- `cobertura` importa `_comun` y `necesidades`.
- `ordenes` importa `_comun`, `necesidades` y `proveedores`.
- `recepcion` importa `_comun` y `cobertura`.
- Ningún módulo importa la fachada `compra_service`; la fachada importa a todos.

### 3.4 Verificación de T2

```powershell
cd backend
.venv/Scripts/python.exe -m pytest -q tests/services/test_compra_service_estructura.py
.venv/Scripts/python.exe -m pytest -q tests/api/test_compras.py tests/api/test_cobertura_021.py tests/api/test_compras_endpoints_020.py
.venv/Scripts/python.exe -m pytest -q
```

Esperado: contrato en verde, suites focalizadas en verde y **1502 passed/88
skipped** (los 1499 previos + 3 tests nuevos). Smoke adicional:

```powershell
.venv/Scripts/python.exe -c "from app.services import compra_service; print(compra_service.__file__); print(compra_service._simular_claves.__module__)"
```

### 3.5 Riesgo de módulo/paquete

Si quedan `compra_service.py` y `compra_service/` a la vez, Python resuelve el
paquete y el archivo viejo queda como código muerto. Por eso el borrado del
`.py` y de su `.pyc` ocurre en la misma tarea, antes de correr la suite.

## 4. Deduplicación (T3)

### 4.1 `_opciones_orden()` — `_comun.py`

Única definición de las opciones de carga de una OC:

```python
def _opciones_orden() -> tuple:
    return (
        joinedload(OrdenCompra.proveedor),
        joinedload(OrdenCompra.sede),
        joinedload(OrdenCompra.factura),
        selectinload(OrdenCompra.detalles).joinedload(
            DetalleOrdenCompra.producto
        ),
        selectinload(OrdenCompra.plan),
    )
```

La usan `_cargar_orden` y `listar_ordenes_compra` con `.options(*_opciones_orden())`.
El orden de las opciones se conserva para no alterar el SQL.

### 4.2 `_validar_entrada_orden()` — `ordenes.py`

Extrae el bloque idéntico de alta y edición:

```python
def _validar_entrada_orden(
    db_tenant: Session,
    db_control: Session,
    datos: OrdenCompraCrear | OrdenCompraActualizar,
    institucion_id: str,
) -> list[DetalleOrdenCompraCrear]:
    _sede_valida(db_tenant, datos.sede_id, institucion_id)
    proveedor = _proveedor_activo_control(db_control, datos.proveedor_id)
    items = _items_validados(db_tenant, datos.items, institucion_id)
    _replicar_proveedor(db_tenant, proveedor)
    return items
```

`crear_orden_compra` y `actualizar_orden_compra` la llaman después de resolver
la institución (y, en edición, después de comprobar `Borrador`). Se conserva el
orden `sede → proveedor → ítems → réplica`, que define la precedencia de los
409/404 y el `flush` del tenant.

### 4.3 Verificación de T3

Misma secuencia que T2. La suite existente es la caracterización: no se añaden
tests de comportamiento nuevos porque no cambia el comportamiento.

## 5. Cierre (T4)

### 5.1 Suites y contrato

```powershell
cd backend
.venv/Scripts/python.exe -m pytest -q
```

Esperado: **1502 passed/88 skipped/0 failed**.

```powershell
cd frontend
$env:CHROME_BIN = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
npx ng test --watch=false --browsers=ChromeHeadless
npx ng build
```

Esperado: `549 SUCCESS` y build limpio. No se reconstruye la imagen 8080 porque
`frontend/` no cambia; el humo usa el build ya congelado y valida la API nueva
(backend con recarga automática).

### 5.2 Contrato HTTP y áreas protegidas

- `/openapi.json`: **75** operaciones; endpoints de negocio: **73**.
- `git diff --stat` demuestra que no cambian `database/`,
  `backend/app/models/`, `backend/app/core/permisos.py`, `frontend/` ni `.env`.
- La versión sigue en `021.1` y las tablas en 27/24.
- `grep` de coherencia sobre `AGENTS.md`, `MEMORY.md` y `.agents/skills/`.

### 5.3 Recorrido funcional

- **4200** (dev server): login QA, módulo Compras → Necesidades → crear/emitir
  una OC → registrar factura → recepción; sin errores de consola.
- **8080** (build congelado): el mismo módulo carga y la API de compras responde;
  sin errores nuevos de consola.

### 5.4 Documentación y evidencia

- Nota en `docs/spec/stack.md` sobre el patrón «paquete con fachada» para
  servicios grandes y la excepción de `_simular_claves`.
- `docs/spec/features/023-refactor-compra-service/evidencia/README.md` con
  suites, OpenAPI, diff protegido y recorridos.
- `MEMORY.md`: estado, decisiones y siguiente trabajo.
- `roadmap.md`: fila y viñeta de la 023 en `[x]`, con fecha de cierre.

## 6. Rollback

- T2 se revierte restaurando `compra_service.py` y borrando el paquete.
- T3 se revierte volviendo a las dos copias locales de opciones/validación.
- No hay cambios de esquema ni de datos, así que no hace falta `down -v`.

## 7. Fuera de alcance operativo

- No se ejecutan los tests gated de PostgreSQL por defecto; el refactor no toca
  SQL, bloqueos ni transacciones. Si se dispone de `POSTGRES_TEST_URL`, correrlos
  es un extra, no un requisito de cierre.
- No se commitea: la 022 y la 023 quedan apiladas en el árbol de trabajo.
