# Evidencia — Feature 026: Salud del esquema de base de datos

**Feature:** `026-salud-esquema-bd/`
**Spec:** [../spec.md](../spec.md) · **Plan:** [../plan.md](../plan.md) · **Tareas:** [../tasks.md](../tasks.md)
**Estado:** cerrada el 18/Nov/2026.

## 1. Línea base (antes de tocar código)

| Suite | Resultado |
|---|---|
| Backend `pytest -q` (SQLite) | **1660 passed / 88 skipped / 0 failed** |
| Backend *gated* PostgreSQL 16 | **73 passed** (16 archivos `*postgres*.py`) |
| Backend *gated* Redis | **3 passed** |
| Frontend `ng test --watch=false --browsers=ChromeHeadless` | **549 SUCCESS** |
| Contrato OpenAPI | **75 operaciones** · `MATRIZ_PERMISOS` **73** |
| Esquema vivo | `021.1` · **27** tablas en `control` y **24** por tenant · **22** entidades de dominio |

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q
$env:POSTGRES_TEST_URL = "postgresql://postgres:postgres@localhost:5433/postgres"
.\.venv\Scripts\python.exe -m pytest tests -q
$env:REDIS_TEST_URL = "redis://127.0.0.1:6380/15"
.\.venv\Scripts\python.exe -m pytest tests -q

cd ..\frontend
$env:CHROME_BIN = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
npx ng test --watch=false --browsers=ChromeHeadless
```

### 1.1 Inventario de referencias a `inventario` (T1)

`rg -n "\binventario\b|Inventario|inventario_id" backend frontend database docs/spec` se
clasificó en tres destinos: **retirar** (tabla `inventario`, columna `inventario_id`, modelo
`Inventario`, relación `Producto.inventarios` / `Departamento.inventarios`, servicio
`_historial_legados`, `union_all` del dashboard, campos `departamento_id` /
`departamento_nombre` / `ubicacion` de los DTO de actividad), **conservar** (la capacidad
funcional `"inventario"` de `control_canonico.CAPACIDADES`, el nombre de la clase
`MovimientoInventario` y el de la tabla `movimiento_inventario`, los textos de negocio que
hablan de «inventario» como concepto) y **actualizar** (los docstrings de endpoints, schemas
y tests históricos que describían la tabla retirada).

## 2. DDL: retiro de `inventario`, índices y restricciones (T2/T4)

### 2.1 Conteo de tablas y versión

| Objeto | Antes | Después |
|---|---|---|
| Tablas en `control` | 27 | **26** |
| Tablas por tenant | 24 | **23** |
| Entidades de dominio | 22 | **21** |
| Token de versión | `021.1` | **`026.0`** |

`control.inventario` ya no existe; `movimiento_inventario` perdió `inventario_id` y su FK, y
`stock_sede_id` pasó a `NOT NULL` en DDL y en ORM.

### 2.2 Índices P0 (15 por esquema)

| # | Índice | Tabla | Columnas |
|---|---|---|---|
| I-01 | `stock_sede_producto_sede_idx` | `stock_sede` | `(producto_id, sede_id)` |
| I-02 | `movimiento_stock_sede_fecha_idx` | `movimiento_inventario` | `(stock_sede_id, fecha_movimiento DESC, movimiento_id DESC)` |
| I-03 | `movimiento_fecha_idx` | `movimiento_inventario` | `(fecha_movimiento DESC, movimiento_id DESC)` |
| I-04 | `ticket_sede_estado_fecha_idx` | `ticket` | `(sede_id, estado_id, fecha_creacion DESC, ticket_id DESC)` |
| I-05 | `ticket_usuario_fecha_idx` | `ticket` | `(usuario_id, fecha_creacion DESC, ticket_id DESC)` |
| I-06 | `detalle_ticket_ticket_idx` | `detalle_ticket` | `(ticket_id, detalle_ticket_id)` |
| I-07 | `detalle_ticket_producto_idx` | `detalle_ticket` | `(producto_id, ticket_id)` |
| I-08 | `historial_ticket_ticket_fecha_idx` | `historial_transicion_ticket` | `(ticket_id, fecha_transicion DESC, historial_transicion_id DESC)` |
| I-09 | `historial_producto_producto_fecha_idx` | `historial_transicion_producto` | `(producto_id, fecha_transicion DESC, historial_producto_id DESC)` |
| I-10 | `historial_categoria_categoria_fecha_idx` | `historial_transicion_categoria` | `(categoria_id, fecha_transicion DESC, historial_categoria_id DESC)` |
| I-11 | `usuario_departamento_idx` | `usuario` | `(departamento_id)` |
| I-12 | `departamento_sede_idx` | `departamento` | `(sede_id)` |
| I-13 | `producto_categoria_idx` | `producto` | `(categoria_id)` |
| I-14 | `orden_compra_institucion_fecha_idx` | `orden_compra` | `(institucion_id, fecha_creacion, orden_compra_id)` |
| I-15 | `orden_compra_sede_estado_fecha_idx` | `orden_compra` | `(sede_id, estado, fecha_creacion, orden_compra_id)` |

Verificación en la BD viva (`pg_indexes`): **67 índices en `control`** y **63 en cada uno de
los 4 tenants**; los 15 P0 aparecen con sus columnas y su orden exactos en los cinco
esquemas (más los 2 P0 heredados de la 021, `orden_compra_ticket_ticket_idx` y
`orden_compra_ticket_producto_idx`, y las 6 unicidades B2).

### 2.3 Unicidades B2, unicidad parcial y checks

| # | Nombre | Definición |
|---|---|---|
| U-01 | `usuario_correo_normalizado_uk` | `UNIQUE (lower(trim(correo)))` |
| U-02 | `proveedor_rut_normalizado_uk` | `UNIQUE (upper(replace(replace(replace(trim(rut),'.',''),'-',''),' ','')))` |
| U-03 | `sede_nombre_institucion_uk` | `UNIQUE (institucion_id, lower(trim(nombre)))` |
| U-04 | `departamento_nombre_institucion_uk` | `UNIQUE (institucion_id, lower(trim(nombre_dep)))` |
| U-05 | `categoria_nombre_institucion_uk` | `UNIQUE (institucion_id, lower(trim(nombre_cat)))` |
| U-06 | `historial_transicion_ticket_creacion_uk` | `UNIQUE (ticket_id) WHERE estado_origen_id IS NULL` |
| U-07 | `version_esquema_unica_idx` | `UNIQUE ((true))` sobre `version_esquema` — **solo PostgreSQL** |
| K-01 | `usuario_correo_canonico_ck` | el correo no puede quedar en blanco |
| K-02 | `proveedor_rut_canonico_ck` | el RUT no puede quedar en blanco |
| K-03 | `detalle_cantidad_entregada_tope_ck` | `cantidad_entregada <= cantidad_solicitada` |
| K-04 | `movimiento_tipo_ck` | `tipo_movimiento IN ('ENTRADA','SALIDA')` |

- **U-07 no está en el ORM.** Es un helper **dialectal de PostgreSQL**: `create_all` sobre
  SQLite no lo crea (para no romper la suite en memoria) y el aprovisionamiento en caliente
  lo aplica con `control_service._crear_indice_version_unica`
  (`CREATE UNIQUE INDEX IF NOT EXISTS ... ON ... ((true))`).
- Expresiones portables: solo `lower`, `trim`, `upper` y `replace`; nunca `btrim` ni
  `regexp_replace`.
- Auditoría previa de datos: **0 violaciones** de U-01…U-06 y K-01…K-04 en `control` y en los
  4 tenants antes de aplicar el DDL. Ninguna constraint se relajó para que pasara un fixture.

## 3. Semilla y arranque limpio (T3/T13)

`docker compose -f docker-compose.yml down -v` + `up -d` → `01_esquema.sql` y
`02_datos_semilla.sql` corren sin errores (guardia fail-closed con `ON_ERROR_STOP=1`).

| Comprobación | Resultado |
|---|---|
| Tablas en `control` | **26** |
| Tablas por tenant | **23** (4 tenants) |
| Tablas `inventario` en toda la base | **0** |
| Versión en `control` y en los 4 tenants | **`026.0`** |
| `stock_sede` sumados | **14** (INST-001: 10 · INST-002: 4 · INST-003/004: 0) |
| `movimiento_inventario` sumados | **3** (los 3 en INST-001) |
| Movimientos sin `stock_sede_id` | **0** |
| Saldo del producto 5 (INST-001) | **45** |
| Saldo del producto 9 (INST-001) | **12** |

Movimientos sembrados (los 3 coherentes con la 5C-lite): `ENTRADA 10` de Clip Metrico 33mm,
`ENTRADA 21` y `SALIDA 15` de Rotulador Marcador, todos en Sede Maipu. Los **14
movimientos legados** y las **14 filas de `inventario`** quedaron fuera: el saldo vigente es
`stock_sede` y la auditoría es `movimiento_inventario` con destino obligatorio.

Guion de verificación:

```sql
SELECT count(*) FROM information_schema.tables
 WHERE table_schema = 'control';                                   -- 26
SELECT count(*) FROM information_schema.tables
 WHERE table_schema LIKE 'tenant\_%';                               -- 23 por tenant
SELECT count(*) FROM information_schema.tables
 WHERE table_name = 'inventario';                                   -- 0
SELECT version FROM control.version_esquema;                       -- 026.0
SELECT count(*) FROM tenant_inst_001_038aa2a9.stock_sede;          -- 10
SELECT count(*) FROM tenant_inst_002_5efdced3.stock_sede;          -- 4
SELECT count(*) FROM tenant_inst_001_038aa2a9.movimiento_inventario
 WHERE stock_sede_id IS NULL;                                      -- 0
```

## 4. Retirada de caminos legados (T5/T7)

- `inventario_service.py`: fuera `_historial_legados`, el `union_all` y la rama de escritura
  por `inventario_id`; queda **una sola proyección por `stock_sede`**.
- `dashboard_service.py`: fuera la población legada y el `union_all`; la actividad es una
  **consulta única** sobre `movimiento_inventario`.
- `schemas/inventario_schema.py` / `schemas/dashboard_schema.py`: `MovimientoCrear.stock_sede_id`
  es obligatorio y ninguna respuesta expone `inventario_id`, `departamento_id`,
  `departamento_nombre` ni `ubicacion`.
- Frontend: `MovimientoCrear` usa `stock_sede_id`; `MovimientoDashboard` perdió los campos
  legados; `dashboard.component.html` resuelve `sede_nombre ?? 'Sin sede'`.
- Docstrings de endpoints (`dashboard.py`, `inventario.py`) y de los tests históricos
  (`test_dashboard_sede_011.py`, `test_inventario_sede_011.py`) actualizados: ya no describen
  la tabla retirada.
- `rg -n "Inventario|inventario_id" backend/app` solo deja usos legítimos: la capacidad
  `"inventario"`, la clase `MovimientoInventario`, la tabla `movimiento_inventario` y tres
  docstrings que **declaran la ausencia** del campo retirado (`inventario_schema.py` y
  `dashboard_service.py`). Los comentarios de `ticket_service.py` que aún decían «deja
  `inventario_id` nulo» se corrigieron en el cierre.

## 5. B2: normalización y 409 (T6)

| Alta duplicada | Normalización | Respuesta |
|---|---|---|
| `POST /organizacion/sedes` | `lower(trim(nombre))` por institución | **409** «Ya existe una sede con ese nombre en la institucion» |
| `POST /organizacion/departamentos` | `lower(trim(nombre_dep))` por institución | **409** «Ya existe un departamento con ese nombre en la institucion» |
| `POST /compras/proveedores` | RUT sin puntos, guiones ni espacios, en mayúsculas | **409** «El RUT del proveedor ya esta registrado» |
| `POST /usuarios/` | `lower(trim(correo))` | **409** «El correo ya esta registrado y vinculado a una institucion» |

Cada alta hace **pre-check normalizado** y además captura `IntegrityError` para convertir la
carrera real en **409** y no en un 500.

## 6. Suites completas y contrato (T8/T9/T10/T12)

| Comprobación | Resultado |
|---|---|
| `pytest -q` (SQLite) | **1659 passed / 105 skipped / 0 failed** (253,22 s) |
| `pytest -q` con `POSTGRES_TEST_URL` | **1761 passed / 3 skipped / 0 failed** (650,45 s) |
| `pytest -q` con `REDIS_TEST_URL` | **1662 passed / 102 skipped / 0 failed** (256,35 s) |
| `ng test --watch=false --browsers=ChromeHeadless` | **549 SUCCESS** |
| `ng build` | limpio (23,67 s) |
| `/openapi.json` | **75 operaciones** en 62 rutas; **37** declaran 409 |
| `MATRIZ_PERMISOS` | **73** — sin diff |
| `backend/tests/funcional/sistema/test_salud_esquema_026.py` (SQLite) | **3 passed** — metadatos, índices y constraints |
| `backend/tests/funcional/sistema/test_salud_esquema_postgres_026.py` (gated) | **14 passed** — 26/23, `026.0`, 14/3, 45/12, los 17 P0, U-01…U-07, K-01…K-04 y N-01 |

El archivo gated nuevo cubre: conteo 26/23 y ausencia de `inventario`; versión `026.0` en
`control` y en los 4 tenants; 14 saldos / 3 movimientos / 45-12; los **17 índices P0** (15
nuevos + 2 heredados de la 021) con tabla y columnas exactas en los cinco esquemas; U-01…U-05
como índices de expresión únicos; U-06 parcial y U-07 `((true))`; rechazo de una segunda fila
de `version_esquema`; K-01, K-02, K-03 y K-04; colisiones de RUT con y sin puntos; colisiones
de nombre normalizado en sede, departamento y categoría; y N-01 (`stock_sede_id NOT NULL`,
sin `inventario_id`).

Los tests gated de PostgreSQL se ejecutan contra **bases temporales desechables**:
`apt_erp` no se toca.

### 6.1 Defecto real corregido al cerrar: timeouts del cliente Redis (Feature 025)

Al ejecutar el *gated* de Redis para cerrar esta feature, el reparto concurrente de veinte
evaluaciones salió **12/8** en vez de **10/10**. La causa no era la atomicidad del script Lua
(`INCR` + `PTTL` + `PEXPIRE` dentro de un `EVAL`): era el **tope de lectura del socket**
(`socket_timeout=0.2`) aplicado al *handshake* de redis-py. Medido en esta máquina:

- 20 conexiones TCP crudas a `127.0.0.1:6380`: **28 ms** como máximo (el handshake TCP no
  es el cuello).
- 20 conexiones de redis-py con handshake completo: **174–203 ms** como máximo, justo sobre
  el tope de 200 ms → `TimeoutError` → *fail-open* → más permisos de los permitidos.

Corrección en `backend/app/core/limite_tasa.py`: el tope de **conexión** queda en
`TIEMPO_MAXIMO_CONEXION = 0.3 s` (rápido para que un Redis inalcanzable caiga) y el tope de
**lectura** sube a `TIEMPO_MAXIMO_LECTURA = 2.0 s` (holgado para el handshake). La cota dura
del camino de petición **no cambia**: sigue siendo `TIEMPO_MAXIMO_EVALUACION = 0.5 s`, que
envuelve toda la evaluación con `asyncio.wait_for`. El contrato de fail-open se mantiene: tres
evaluaciones seguidas contra `192.0.2.1:6379` (TEST-NET, inalcanzable) siguen cerrando dentro
del segundo.

Resultado tras la corrección: **68 passed** en tres corridas consecutivas de la selección
Redis (antes: fallo intermitente en 1 de cada 3).

## 7. Recorrido funcional en 4200 (T13)

Backend en `:8000` (contenedor, volumen `./backend/app`), frontend de desarrollo en
`http://localhost:4200/`. Sesión real de Clerk como **Administrador** de
`Instituto Profesional Los Alpes` (`admin020.test+clerk_test@example.com`).

| # | Recorrido | Resultado |
|---|---|---|
| 1 | Alta de sede duplicada (`Sede Providencia`) | **409** — «Ya existe una sede con ese nombre en la institucion» |
| 2 | Alta de departamento duplicado (`  direccion  ` contra `Direccion`) | **409** — «Ya existe un departamento con ese nombre en la institucion» |
| 3 | Alta de proveedor con RUT equivalente (` 76543210-8 ` contra `76.543.210-8`) | **409** — «El RUT del proveedor ya esta registrado» |
| 4 | Alta de usuario con correo en mayúsculas y espacios (`  CAMILA.FERNANDEZ@LOSALPES.CL  `) | **409** — «El correo ya esta registrado y vinculado a una institucion» |
| 5 | `POST /inventario/movimientos` con `stock_sede_id: 8` | **201** — `{"message":"Movimiento registrado exitosamente","nuevo_stock":52}` (45 → 52) |
| 6 | `POST /inventario/movimientos` con el campo legado `inventario_id` | **422** — `{"type":"missing","loc":["body","stock_sede_id"]}` |
| 7 | `GET /inventario/stock` | Serie plana: `stock_sede_id`, `sede_id`, `sede_nombre`, `producto_id`, `stock_actual`, `institucion_id`; **sin** `inventario_id` ni `ubicacion` |
| 8 | `GET /dashboard/` | Claves `kpi`, `alertas`, `actividad_disponible`, `actividad_movimientos`; cada movimiento trae `sede_id`/`sede_nombre`; **sin** `inventario_id`, `departamento_nombre` ni `ubicacion` |
| 9 | Tablero de pedidos y detalle `/tickets/8` | 8 pedidos en el Kanban; el detalle muestra ítems, historial y cobertura por producto |
| 10 | Consola del navegador | **Sin errores** (solo el aviso de claves de desarrollo de Clerk) |

Tras el recorrido se **reconstruyó el volumen** (`down -v` + `up -d`) para devolver la base QA
a la semilla prístina: producto 5 = 45, producto 9 = 12, 14 saldos y 3 movimientos.

## 8. Humo en 8080 (T14)

`docker compose -f docker-compose.yml build frontend` + `up -d frontend` (el 8080 sirve un
build de producción congelado en la imagen; sin reconstruir, el humo sería falso).

| Ruta directa de Angular | Título servido | Estado |
|---|---|---|
| `/` → `/dashboard` | Dashboard \| CompuStock | **200** |
| `/inventario` | Inventario \| CompuStock | **200** |
| `/inventario/5` | Detalle del producto \| CompuStock | **200** |
| `/administracion/sedes` | Sedes \| CompuStock | **200** |
| `/administracion/departamentos` | Departamentos \| CompuStock | **200** |
| `/tickets` | Pedidos \| CompuStock | **200** |
| `/tickets/8` | Detalle del pedido \| CompuStock | **200** |
| `/compras` | Órdenes de compra \| CompuStock | **200** |

El `try_files` de nginx sirve las rutas directas de Angular (prueba de la 024) y el bundle con
hash se sirve cacheado. Consola del navegador: **sin errores**. El dashboard en 8080 muestra
**572** unidades en stock (la suma de la semilla prístina), **6** pedidos activos, **7**
departamentos, **3** alertas y los **3** movimientos con su sede.

## 9. Documentación sincronizada y cierre (T11/T14)

| Documento | Estado |
|---|---|
| `AGENTS.md` §4 | 26 tablas en `control`, 23 por tenant, `026.0` |
| `AGENTS.md` §7 | **21 entidades de dominio** |
| `docs/spec/stack.md` | Enmienda de la Feature 026 (21 entidades, 26/23, `026.0`, 5C-lite) y lista de modelos sin `Inventario` |
| `docs/spec/roadmap.md` | Fila 026 cerrada en Sprint 7 |
| `database/README.md` | 26/23 y `026.0` |
| `MEMORY.md` | Estado, decisiones y errores a evitar |
| `README.md` | Conteo y versión al día |

`grep` de coherencia sobre `AGENTS.md`, `MEMORY.md`, `README.md`, `database/README.md`,
`docs/spec/stack.md`, `docs/spec/roadmap.md` y `docs/spec/constitucion.md`: **las notas de
vigencia** dicen 26/23, `026.0` y 21 entidades, sin rastros de `021.1` ni de 22 entidades. Las
únicas coincidencias de `27/24` y `021.1` son **registros históricos fechados**: las filas ya
cerradas de las features 020/021/024/025 en `roadmap.md` y sus propias secciones en
`stack.md`, que documentan el estado de su época y no el vigente. En esta pasada se corrigió
la enmienda de la 026 en `stack.md`, que por error decía «26 → 24» y «23 → 22» en vez de
**27 → 26** y **24 → 23**, y se recortó `MEMORY.md` a **40 líneas** (límite ~50).

**Sin cambios** en `backend/app/core/permisos.py`, en las rutas, en `CAPACIDADES` (la
capacidad funcional `"inventario"` se conserva: es una capacidad, no la tabla retirada), en
`package.json` ni en `requirements.txt`.
