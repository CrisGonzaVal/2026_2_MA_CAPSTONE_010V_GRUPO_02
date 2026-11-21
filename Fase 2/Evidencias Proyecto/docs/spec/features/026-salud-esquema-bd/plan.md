# Plan de implementación — Feature 026: Salud del esquema de base de datos

**Feature:** `026-salud-esquema-bd/`
**Spec:** [spec.md](spec.md)
**Enfoque:** catorce tareas secuenciales; cada una deja la suite en verde. El esquema se reconstruye, no se migra.
**Regla:** no se reabre ninguna feature anterior. No se tocan permisos, rutas, capabilities ni la matriz de operaciones. Los únicos cambios de contrato son la desaparición de campos legados y los nuevos **409** documentados.

## 1. Orden de ejecución

```text
T1  línea base + inventario de referencias
  → T2  DDL: retiro de inventario + 15 índices + B1/B2
  → T3  semilla: 14 saldos, 3 movimientos, 026.0
  → T4  paridad ORM + helper PG de versión única
  → T5  retiro de caminos legados (servicios, schemas, models)
  → T6  B2: normalización y 409 en servicios
  → T7  limpieza del frontend
  → T8  tests SQLite / unit / API
  → T9  tests gated PostgreSQL 16
  → T10 frontend tests + build
  → T11 documentación viva
  → T12 suites completas + contrato OpenAPI
  → T13 down -v + up -d + recorrido 4200
  → T14 build 8080 + humo + evidencia + cierre
```

## 2. Archivos y frontera

### 2.1 Archivos nuevos

| Archivo | Propósito |
|---|---|
| `docs/spec/features/026-salud-esquema-bd/spec.md` | Esta spec |
| `docs/spec/features/026-salud-esquema-bd/plan.md` | Este plan |
| `docs/spec/features/026-salud-esquema-bd/tasks.md` | Checklist de ejecución |
| `docs/spec/features/026-salud-esquema-bd/evidencia/README.md` | Evidencia de cierre |
| `backend/tests/funcional/sistema/test_salud_esquema_026.py` | Paridad ORM, constraints y B2 en SQLite |
| `backend/tests/funcional/sistema/test_salud_esquema_postgres_026.py` | Gated: instalación limpia, índices, constraints y versión única |

> No se crean archivos de migración. No se crean endpoints ni componentes nuevos.

### 2.2 Archivos modificados

| Área | Archivos |
|---|---|
| DDL / semilla | `database/01_esquema.sql`, `database/02_datos_semilla.sql`, `database/README.md` |
| Modelos | `backend/app/models/inventario.py`, `institucion.py`, `producto.py`, `sede.py`, `usuario.py`, `ticket.py`, `compra.py`, `control_canonico.py`, `control.py`, `organizacion.py`, `__init__.py` |
| Servicios | `backend/app/services/inventario_service.py`, `dashboard_service.py`, `organizacion_service.py`, `compra_service/proveedores.py`, `usuario_service.py`, `control_service.py` |
| Schemas / config | `backend/app/schemas/inventario_schema.py`, `dashboard_schema.py`, `backend/app/core/config.py` |
| Tests backend | `backend/tests/conftest.py` + los archivos listados en T8/T9 |
| Frontend | `frontend/src/app/shared/interfaces/index.ts`, `frontend/src/app/features/dashboard/dashboard.component.html`, `frontend/src/app/features/dashboard/services/dashboard.service.spec.ts` (+ specs que mockean la actividad) |
| Documentación | `docs/spec/stack.md`, `docs/spec/roadmap.md`, `AGENTS.md`, `MEMORY.md` |

### 2.3 Lo que no se toca

- `backend/app/core/permisos.py`, `backend/app/api/**`, `backend/app/main.py`, middleware, métricas y limitador de tasa.
- `backend/app/models/control_canonico.py` **salvo** `ProveedorControl`; `CAPACIDADES` y `_TABLAS_SOLO_CONTROL` no cambian.
- `docker-compose.yml`, `frontend/nginx.conf`, `backend/requirements.txt`.
- Features 015 y 016.

## 3. T1 — Línea base e inventario de referencias

**ACs:** AC-16 (línea base), AC-14 (inventario de referencias).

### 3.1 Línea base

Desde el host y con el venv activo:

```powershell
cd backend
pytest -q
$env:POSTGRES_TEST_URL = "postgresql://postgres:postgres@localhost:5433/postgres"
pytest -q -m postgres
$env:REDIS_TEST_URL = "redis://127.0.0.1:6380/15"
pytest -q -m redis
```

Registrar en `evidencia/README.md` los conteos exactos. Línea base esperada (025): **1660 passed / 88 skipped**, gated PostgreSQL **73 passed**, gated Redis **3 passed**.

Frontend:

```powershell
cd frontend
$env:CHROME_BIN = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
npx ng test --watch=false --browsers=ChromeHeadless
```

Línea base esperada: **549 SUCCESS**.

### 3.2 Inventario de referencias

Ejecutar y guardar la salida:

```powershell
rg -n "\binventario\b|Inventario|inventario_id" backend frontend database docs/spec
```

Clasificar cada coincidencia en:

1. **Se retira** (tabla, columna, relación, servicio, DTO, campos de dashboard).
2. **Se conserva** (`CAPACIDADES` con `"inventario"` en `control_canonico.py`, textos de negocio como «inventario físico», nombres de tests históricos).
3. **Se actualiza** (comentarios, conteos, documentación).

El resultado se adjunta a la evidencia. Es la lista de control para T5 y T13.

## 4. T2 — DDL: retiro de `inventario`, índices y restricciones

**ACs:** AC-1, AC-3, AC-4, AC-5, AC-8, AC-9, AC-10, AC-11, AC-12, AC-13, AC-14.

### 4.1 Encabezado de `01_esquema.sql`

- Línea 9: `control` (27 tablas) → **26**.
- Línea 10: 24 tablas → **23**.
- Línea 27: la lista de entidades se corrige —se quita `inventario` y se agrega `orden_compra_ticket`—; el conteo sigue siendo **21 entidades**.
- Línea 39: `020.1` → **`026.0`**.

### 4.2 Retiro de `inventario` (control)

- Eliminar el bloque `CREATE TABLE control.inventario` (sección 7, líneas ~293–326).
- Renombrar el comentario `7b. STOCK_SEDE` a `7. STOCK_SEDE` (sin reenumerar el resto).
- En `control.movimiento_inventario`:
  - Eliminar `inventario_id INTEGER` y `CONSTRAINT movimiento_inventario_fk`.
  - Cambiar `stock_sede_id INTEGER` → `INTEGER NOT NULL`.
  - Agregar `CONSTRAINT movimiento_tipo_ck CHECK (tipo_movimiento IN ('ENTRADA', 'SALIDA'))`.
- En `control.detalle_ticket`: agregar `CONSTRAINT detalle_cantidad_entregada_tope_ck CHECK (cantidad_entregada <= cantidad_solicitada)`.
- En `control.usuario`: agregar `CONSTRAINT usuario_correo_canonico_ck CHECK (correo = lower(trim(correo)) AND length(correo) > 0)`.
- En `control.proveedor`: agregar `CONSTRAINT proveedor_rut_canonico_ck CHECK (rut = upper(trim(rut)) AND length(rut) > 0)`.
- Después de `control.version_esquema`, agregar:
  ```sql
  CREATE UNIQUE INDEX version_esquema_unica_idx
      ON control.version_esquema ((true));
  ```

### 4.3 Índices P0 de `control`

Insertar una sección `ÍNDICES P0 (Feature 026)` inmediatamente después del `ALTER TABLE control.historial_transicion_ticket ... orden_compra_fk` (línea ~906), antes de la topología. Debe contener, en este orden:

```sql
CREATE INDEX stock_sede_producto_sede_idx
    ON control.stock_sede (producto_id, sede_id);

CREATE INDEX movimiento_stock_sede_fecha_idx
    ON control.movimiento_inventario (stock_sede_id, fecha_movimiento DESC, movimiento_id DESC);

CREATE INDEX movimiento_fecha_idx
    ON control.movimiento_inventario (fecha_movimiento DESC, movimiento_id DESC);

CREATE INDEX ticket_sede_estado_fecha_idx
    ON control.ticket (sede_id, estado_id, fecha_creacion DESC, ticket_id DESC);

CREATE INDEX ticket_usuario_fecha_idx
    ON control.ticket (usuario_id, fecha_creacion DESC, ticket_id DESC);

CREATE INDEX detalle_ticket_ticket_idx
    ON control.detalle_ticket (ticket_id, detalle_ticket_id);

CREATE INDEX detalle_ticket_producto_idx
    ON control.detalle_ticket (producto_id, ticket_id);

CREATE INDEX historial_ticket_ticket_fecha_idx
    ON control.historial_transicion_ticket (ticket_id, fecha_transicion DESC, historial_transicion_id DESC);

CREATE INDEX historial_producto_producto_fecha_idx
    ON control.historial_transicion_producto (producto_id, fecha_transicion DESC, historial_producto_id DESC);

CREATE INDEX historial_categoria_categoria_fecha_idx
    ON control.historial_transicion_categoria (categoria_id, fecha_transicion DESC, historial_categoria_id DESC);

CREATE INDEX usuario_departamento_idx
    ON control.usuario (departamento_id);

CREATE INDEX departamento_sede_idx
    ON control.departamento (sede_id);

CREATE INDEX producto_categoria_idx
    ON control.producto (categoria_id);

CREATE INDEX orden_compra_institucion_fecha_idx
    ON control.orden_compra (institucion_id, fecha_creacion, orden_compra_id);

CREATE INDEX orden_compra_sede_estado_fecha_idx
    ON control.orden_compra (sede_id, estado, fecha_creacion, orden_compra_id);
```

### 4.4 Unicidades B2 y parcial de `control`

En la misma sección:

```sql
CREATE UNIQUE INDEX usuario_correo_normalizado_uk
    ON control.usuario (lower(trim(correo)));

CREATE UNIQUE INDEX proveedor_rut_normalizado_uk
    ON control.proveedor (
        upper(replace(replace(replace(trim(rut), '.', ''), '-', ''), ' ', ''))
    );

CREATE UNIQUE INDEX sede_nombre_institucion_uk
    ON control.sede (institucion_id, lower(trim(nombre)));

CREATE UNIQUE INDEX departamento_nombre_institucion_uk
    ON control.departamento (institucion_id, lower(trim(nombre_dep)));

CREATE UNIQUE INDEX categoria_nombre_institucion_uk
    ON control.categoria (institucion_id, lower(trim(nombre_cat)));

CREATE UNIQUE INDEX historial_transicion_ticket_creacion_uk
    ON control.historial_transicion_ticket (ticket_id)
    WHERE estado_origen_id IS NULL;
```

> Verificar antes que los datos de `control` no violan ninguna unicidad. La auditoría previa dio 0 violaciones; si aparece una, es un hallazgo, no un motivo para relajar el índice.

### 4.5 Plantilla tenant

- Eliminar el bloque `CREATE TABLE %1$I.inventario (...)`.
- En `movimiento_inventario`: quitar `inventario_id`, quitar la FK, `stock_sede_id INTEGER NOT NULL`, agregar `movimiento_tipo_ck`.
- En `detalle_ticket`: agregar el check de tope.
- En `usuario`: agregar `usuario_correo_canonico_ck`.
- En `proveedor`: agregar `proveedor_rut_canonico_ck`.
- Al final del arreglo `v_plantillas`, después del `ALTER TABLE ... historial_transicion_ticket_orden_compra_fk`:
  - los 15 `CREATE INDEX %1$I.<nombre> ON %1$I.<tabla> (...)` de §4.3;
  - las 5 unicidades B2 de §4.4;
  - `historial_transicion_ticket_creacion_uk` con el mismo `WHERE`;
  - `CREATE UNIQUE INDEX %1$I.version_esquema_unica_idx ON %1$I.version_esquema ((true));`.
- Cambiar el guard:
  ```sql
  IF v_conteo <> 23 THEN
      RAISE EXCEPTION
          '01: el tenant % tiene % tabla(s) (esperadas 23).',
          v_esquema, v_conteo;
  END IF;
  RAISE NOTICE '01: tenant % creado con 23 tablas.', v_esquema;
  ```

### 4.6 Orden de creación

- En `control`, los índices van después de todas las tablas y del `ALTER TABLE` de la FK de historial, porque referencian `orden_compra`.
- En el tenant, los índices van al final del arreglo, cuando todas las tablas existen.
- `version_esquema_unica_idx` se puede crear justo después de su tabla; no depende de otras.

## 5. T3 — Semilla: 14 saldos, 3 movimientos, `026.0`

**ACs:** AC-2, AC-3, AC-11, AC-12, AC-13.

### 5.1 Encabezado y versión

- Líneas 51–52: eliminar la frase «`inventario` queda como registro legado».
- Línea 66: `021.1` → **`026.0`**.
- Constante del bloque `DECLARE`: `v_version_objetivo constant text := '026.0';`.

### 5.2 Retiro de `inventario`

- Eliminar el bloque `7. INVENTARIO` con sus 14 inserts.
- Eliminar `'inventario'` de los dos arreglos de guardia (líneas ~127 y ~147).
- Eliminar el `setval` de `inventario` (línea ~541).
- Eliminar `'inventario:inventario_id'` del arreglo `pares` de `pg_temp.resetear_identidades` (línea ~574). La guarda `to_regclass` lo toleraría, pero dejaría una tabla inexistente en el contrato de la función.
- Eliminar `DELETE FROM control.inventario;` (línea ~826).
- En el copy loop de catálogo/stock, quitar `'inventario'`:
  ```sql
  FOREACH v_plantilla IN ARRAY ARRAY['categoria', 'producto', 'stock_sede'] LOOP
  ```

### 5.3 Stock resultante

Mantener 14 filas. Cambiar solo:

```sql
(8,  45, 2, 5,  'INST-001'),   -- antes 35; +10 por ENTRADA
(9,  12, 2, 9,  'INST-001'),   -- antes 6;  +6 por ENTRADA 21 - SALIDA 15
```

Actualizar el comentario de consolidación para explicar que los saldos 35/6 ya no son el legado, sino la base antes de los 3 movimientos.

### 5.4 Movimientos

Reemplazar las 14 filas por:

```sql
INSERT INTO movimiento_inventario (
    movimiento_id, tipo_movimiento, cantidad, fecha_movimiento, observacion, stock_sede_id
) OVERRIDING SYSTEM VALUE VALUES
(1, 'ENTRADA', 10, CURRENT_TIMESTAMP - INTERVAL '12 days', 'Compra de resmas para bodega', 8),
(2, 'ENTRADA', 21, CURRENT_TIMESTAMP - INTERVAL '9 days',  'Compra de toner para bodega', 9),
(3, 'SALIDA',  15, CURRENT_TIMESTAMP - INTERVAL '7 days',  'Entrega parcial de toner',    9);
```

Verificar que la suma neta coincide: saldo 8 (producto 5) = 35 + 10 = **45**; saldo 9 (producto 9) = 6 + 21 − 15 = **12**.

### 5.5 Reparto a tenants

Reescribir el paso (1.5):

```sql
EXECUTE format(
    'INSERT INTO %I.movimiento_inventario OVERRIDING SYSTEM VALUE '
    'SELECT m.* FROM control.movimiento_inventario m '
    'JOIN control.stock_sede s ON s.stock_sede_id = m.stock_sede_id '
    'WHERE s.institucion_id = $1', v_esquema
) USING v_institucion_id;
```

Los 3 movimientos pertenecen a INST-001; INST-002 queda con 0 movimientos y 4 saldos sin historial. Es el resultado esperado de descartar los 14 legados.

### 5.6 Guardas fail-closed

Hay **dos niveles**, porque el bucle recorre instituciones: cada tenant solo recibe las filas de la suya. La guarda absoluta de 14 saldos dentro del bucle fallaría en INST-002 (4 filas) y en INST-003/004 (0). El reparto esperado es **10 saldos y 3 movimientos en INST-001**, **4 saldos y 0 movimientos en INST-002**, **0 en INST-003/004**.

**Dentro del bucle (1.8.5), contra `control` filtrado por institución**, al estilo de las guardas 1.8.3 ya existentes:

1. `count(%I.stock_sede)` == `count(control.stock_sede WHERE institucion_id = $1)`.
2. `count(%I.movimiento_inventario)` == movimientos de control cuyo `stock_sede_id` pertenece a un saldo de esa institución.
3. `count(%I.movimiento_inventario WHERE stock_sede_id IS NULL)` = **0**.
4. `to_regclass(format('%I.inventario', v_esquema)) IS NULL`.

**Global, en un bloque nuevo justo después del `END LOOP` y antes de la Fase 3** (cuando `control` todavía conserva todos los datos):

5. `count(control.stock_sede)` = **14**, con 10 en INST-001 y 4 en INST-002.
6. `count(control.movimiento_inventario)` = **3**, todos con `stock_sede_id` no nulo.
7. Saldo 8 (producto 5, sede 2): `stock_actual` = **45**; saldo 9 (producto 9, sede 2): `stock_actual` = **12**.
8. Coherencia saldo-movimientos: `stock_actual - neto(movimientos)` = **35** en el saldo 8 y **6** en el saldo 9, que son las aperturas que la semilla documenta.

Cada fallo debe lanzar `RAISE EXCEPTION` con el esquema (o la tabla de control) y el valor obtenido, en el mismo estilo de las guardas actuales.

## 6. T4 — Paridad ORM y helper dialectal

**ACs:** AC-4, AC-5, AC-6, AC-7, AC-8, AC-9, AC-10, AC-11, AC-12, AC-13.

### 6.1 `backend/app/models/inventario.py`

- Eliminar la clase `Inventario` y todos sus imports (`ForeignKeyConstraint`, `UniqueConstraint`, `relationship` si queda sin uso).
- En `MovimientoInventario`:
  - `stock_sede_id` → `nullable=False`.
  - Eliminar `inventario_id` y la relación `inventario`.
  - Agregar `CheckConstraint("tipo_movimiento IN ('ENTRADA', 'SALIDA')", name="movimiento_tipo_ck")`.
- Después de la clase, declarar:
  ```python
  Index(
      "movimiento_stock_sede_fecha_idx",
      MovimientoInventario.stock_sede_id,
      MovimientoInventario.fecha_movimiento.desc(),
      MovimientoInventario.movimiento_id.desc(),
  )
  Index(
      "movimiento_fecha_idx",
      MovimientoInventario.fecha_movimiento.desc(),
      MovimientoInventario.movimiento_id.desc(),
  )
  ```

### 6.2 Relaciones y exports

- `models/institucion.py`: eliminar `Departamento.inventarios`.
- `models/producto.py`: eliminar `Producto.inventarios`.
- `models/__init__.py`: eliminar el import y el export de `Inventario`; conservar `MovimientoInventario`.
- `models/sede.py`: actualizar el docstring que menciona el legado como «registros históricos inmutables» para reflejar que ya no existe.
- `models/organizacion.py`: revisar que no haya relaciones a `Inventario` (no las hay, pero el `grep` de T1 lo confirma).

### 6.3 Índices simples y de expresión

Declarar después de cada clase o en `__table_args__` según corresponda:

| Archivo | Índices |
|---|---|
| `models/sede.py` | `stock_sede_producto_sede_idx`; U-03 `sede_nombre_institucion_uk` |
| `models/ticket.py` | I-04, I-05, I-06, I-07, I-08; U-06 parcial |
| `models/producto.py` | I-09, I-10, I-13; U-05 `categoria_nombre_institucion_uk` |
| `models/usuario.py` | I-11; U-01 `usuario_correo_normalizado_uk`; K-01 |
| `models/institucion.py` | I-12; U-04 `departamento_nombre_institucion_uk` |
| `models/compra.py` | I-14, I-15; U-02 `proveedor_rut_normalizado_uk`; K-02 |
| `models/control_canonico.py` | U-02 y K-02 en `ProveedorControl` |

Patrón de índice de expresión (definido después de la clase):

```python
Index(
    "usuario_correo_normalizado_uk",
    func.lower(func.trim(Usuario.correo)),
    unique=True,
)
```

Patrón de unicidad parcial:

```python
Index(
    "historial_transicion_ticket_creacion_uk",
    HistorialTransicionTicket.ticket_id,
    unique=True,
    postgresql_where=text("estado_origen_id IS NULL"),
    sqlite_where=text("estado_origen_id IS NULL"),
)
```

No usar `btrim`, `regexp_replace` ni `((true))` en el ORM.

### 6.4 `control_service.py`: helper de versión única

Agregar:

```python
def _crear_indice_version_unica(motor, esquema: str) -> None:
    """U-07: una sola fila de version por esquema, solo en PostgreSQL.

    SQLite no soporta el indice sobre una expresion constante y la suite
    necesita insertar varias filas para probar el enrutamiento. Por eso no
    vive en el ORM.
    """
    if motor.dialect.name != "postgresql":
        return
    with motor.begin() as conexion:
        conexion.execute(
            text(
                'CREATE UNIQUE INDEX IF NOT EXISTS version_esquema_unica_idx '
                f'ON "{esquema}".version_esquema ((true))'
            )
        )
```

- Llamarlo en `_provisionar_tenant_postgres` después de `Base.metadata.create_all(...)` y antes de la sesión tenant.
- Si el bootstrap de control crea tablas con `create_all` en PostgreSQL, llamarlo también con `esquema="control"` después de crear la tabla. Si el control solo se crea por SQL, no se llama.
- El nombre de esquema es interno (`tenant_...` o `control`); no proviene del usuario.

### 6.5 `config.py`

`VERSION_ESQUEMA_OBJETIVO = "021.1"` → **`"026.0"`**.

## 7. T5 — Retiro de caminos legados

**ACs:** AC-4, AC-7, AC-14, AC-15.

### 7.1 `backend/app/services/inventario_service.py`

- Eliminar los imports de `Inventario` y de `union_all` si queda sin uso.
- Eliminar `_historial_legados()`.
- Renombrar `_historial_nuevos()` a `_historial_movimientos()` y dejar solo la proyección por `stock_sede`.
- En `listar_historial_movimientos`, eliminar el `union_all`.
- En la creación de movimientos:
  - El DTO exige `stock_sede_id`; eliminar la rama `if movimiento.inventario_id is None`.
  - Resolver siempre `StockSede` y validar la sede del Bodeguero.
  - Eliminar el mensaje «Debe indicar 'stock_sede_id' o 'inventario_id'».
- En el despacho y la recepción, los `MovimientoInventario(...)` ya usan `stock_sede_id`; no cambiar su lógica.
- Actualizar los docstrings que describen «dos poblaciones».

### 7.2 `backend/app/services/dashboard_service.py`

- Eliminar `_actividad_legada()` (o el select equivalente) y el `union_all`.
- Dejar una sola consulta sobre `MovimientoInventario` unida a `StockSede`, `Sede`, `Producto` e `Institucion`.
- Eliminar los campos `departamento_id`, `departamento_nombre` y `ubicacion` de la proyección.
- Actualizar el docstring de cabecera.

### 7.3 Schemas

`backend/app/schemas/inventario_schema.py`:

- `MovimientoInventarioRespuesta`: eliminar `inventario_id`, `departamento_id`, `departamento_nombre`, `ubicacion`; `stock_sede_id` y `sede_id` pasan a no opcionales.
- `MovimientoCrear`: eliminar `inventario_id`; `stock_sede_id` obligatorio.
- Actualizar docstrings.

`backend/app/schemas/dashboard_schema.py`:

- `MovimientoDashboardRespuesta`: eliminar los tres campos legados; conservar `sede_id`, `sede_nombre`, `institucion_id`, `institucion_nombre`.

### 7.4 Endpoints

- Revisar `backend/app/api/v1/endpoints/inventario.py` y `dashboard.py` para eliminar menciones a `inventario_id` en docstrings y descripciones OpenAPI.
- No cambiar rutas, permisos ni códigos de estado.

## 8. T6 — B2: normalización y 409

**ACs:** AC-11, AC-12, AC-13.

### 8.1 `organizacion_service.py`

Agregar helpers privados:

```python
def _nombre_normalizado(nombre: str) -> str:
    return nombre.strip()

def _sede_duplicada(db, institucion_id, nombre, excluir_id=None) -> bool:
    consulta = db.query(Sede).filter(
        Sede.institucion_id == institucion_id,
        func.lower(func.trim(Sede.nombre)) == nombre.strip().lower(),
    )
    if excluir_id is not None:
        consulta = consulta.filter(Sede.sede_id != excluir_id)
    return consulta.first() is not None
```

Análogo para departamento con `nombre_dep`.

- `crear_sede`: guardar `nombre=datos.nombre.strip()`; usar `_sede_duplicada`; envolver `db.commit()` en `try/except IntegrityError` y lanzar `_conflicto("Ya existe una sede con ese nombre en la institucion")`.
- `editar_sede`: validar duplicado excluyendo `sede_id`; guardar `strip()`; mismo `try/except`.
- `crear_departamento`: agregar la validación que hoy no tiene; guardar `nombre_dep.strip()`; 409 y `try/except`.
- `editar_departamento`: validar duplicado excluyendo `departamento_id`; guardar `strip()`; 409 y `try/except`.
- No cambiar los mensajes existentes de sede; usar el mismo estilo para departamento («Ya existe un departamento con ese nombre en la institucion»).

### 8.2 `compra_service/proveedores.py`

Agregar:

```python
def normalizar_rut(rut: str) -> str:
    """Clave de comparacion: mayusculas, sin puntos, guion ni espacios."""
    return (
        rut.replace(".", "")
        .replace("-", "")
        .replace(" ", "")
        .strip()
        .upper()
    )
```

En `crear_proveedor`:

- Guardar `rut = datos.rut.strip().upper()` (conserva puntos y guion visibles).
- Comparar con la expresión SQL normalizada, no con `rut ==`:
  ```python
  clave = normalizar_rut(rut)
  existente = db_control.execute(
      select(ProveedorControl).where(
          func.upper(
              func.replace(
                  func.replace(
                      func.replace(func.trim(ProveedorControl.rut), ".", ""),
                      "-", "",
                  ),
                  " ", "",
              )
          )
          == clave
      )
  ).scalar_one_or_none()
  ```
- Mantener el 409 actual con el mismo mensaje.
- `_confirmar` ya traduce `IntegrityError` a 409; confirmar que el mensaje sea «El RUT del proveedor ya esta registrado».
- La réplica tenant conserva el mismo `rut` visible.

### 8.3 `usuario_service.py`

- Confirmar que `crear_usuario` ya normaliza (`security.normalizar_correo`) y que el `except IntegrityError` devuelve 409. No se requiere cambio funcional; solo un test que ejercite la colisión `Admin@X.CL` vs `admin@x.cl`.
- Revisar que ningún otro camino inserte usuarios sin normalizar (`control_service._crear_administrador` ya lo hace).

### 8.4 `control_service.py`

- `_crear_sede_inicial` no necesita pre-check (tenant nuevo), pero debe usar `nombre.strip()`.
- `_crear_administrador` ya normaliza el correo.

## 9. T7 — Limpieza del frontend

**ACs:** AC-9 (RUT visible), AC-15, AC-17.

### 9.1 `frontend/src/app/shared/interfaces/index.ts`

- `MovimientoCrear`: eliminar `inventario_id`; agregar `stock_sede_id: number`.
- `MovimientoDashboard`: eliminar `departamento_id`, `departamento_nombre`, `ubicacion`; conservar `sede_id`, `sede_nombre`, `institucion_id`, `institucion_nombre`.
- Actualizar el comentario de las líneas 555–563: ya no hay «dos poblaciones»; todos los movimientos son por sede.
- `RespuestaMovimiento` no cambia.

### 9.2 `dashboard.component.html`

Línea 163:

```html
{{ movimiento.sede_nombre ?? 'Sin sede' }} ·
```

### 9.3 Specs

- `dashboard.service.spec.ts`: eliminar los campos legados de los mocks; dejar `sede_nombre`/`sede_id` con valores reales.
- `dashboard.component.spec.ts`: ajustar el mock de `actividad_movimientos` y cualquier aserción sobre «departamento».
- `rg -n "inventario_id|departamento_nombre|ubicacion" frontend/src/app` debe devolver solo los usos legítimos de otras entidades (tickets, compras) y ninguno de movimientos.

## 10. T8 — Tests SQLite, unit y API

**ACs:** AC-4, AC-6, AC-7, AC-8, AC-9, AC-10, AC-11, AC-12, AC-13, AC-14, AC-15.

### 10.1 `backend/tests/conftest.py`

- Reemplazar las fixtures que crean `Inventario` por `StockSede`.
- Todos los `MovimientoInventario` deben llevar `stock_sede_id`.
- Eliminar los imports de `Inventario`.

### 10.2 Tests existentes a actualizar

| Archivo | Cambio |
|---|---|
| `tests/funcional/integracion/test_dashboard_service.py` | Eliminar la población legada; ajustar la actividad a solo sede |
| `tests/funcional/integracion/test_dashboard_analitico.py` | Ajustar conteos y campos de la actividad |
| `tests/funcional/integracion/test_dashboard_sede_011.py` | Quitar `inventario_id` de los movimientos |
| `tests/funcional/integracion/test_historial_movimientos.py` | Quitar la prueba de la unión legada; conservar la de movimientos por sede |
| `tests/funcional/unitarios/test_modelo_sede_011.py` | Reemplazar `Inventario` por `StockSede`; `stock_sede_id` obligatorio |
| `tests/funcional/unitarios/test_modelo_particionamiento.py` | Ajustar conteos 27/24 → 26/23 y tablas |
| `tests/funcional/sistema/test_esquema_postgres.py` | Ajustar conteos y lista de tablas |
| `tests/funcional/integracion/test_ciclo_vida_catalogo_014.py` | Ajustar referencias a `inventario` |
| `tests/funcional/integracion/test_ambito_institucional_008.py` | Reemplazar `Inventario` por `StockSede` |
| `tests/funcional/integracion/test_ambito_institucional.py` | Reemplazar `Inventario` por `StockSede` |
| `tests/funcional/integracion/test_detalle_producto_019.py` | Ajustar movimientos a `stock_sede_id` |
| `tests/funcional/integracion/test_lectura_global_tickets_011.py` | Ajustar movimientos |
| `tests/funcional/integracion/test_tickets_alcance.py` / `test_tickets_institucional.py` | Si crean `Inventario`, migrar a `StockSede` |
| `tests/funcional/sistema/test_integracion_multitenant_010.py` | Ajustar `VersionEsquema` y tablas; agregar `stock_sede_id` |
| `tests/funcional/unitarios/test_dependencias_024.py` | No cambia (no hay dependencia nueva) |

### 10.3 Nuevo `tests/funcional/sistema/test_salud_esquema_026.py`

Cubrir:

1. **Metadatos:** `Base.metadata.tables` no contiene `inventario`; `MovimientoInventario.stock_sede_id.nullable is False`; los 15 índices existen con sus columnas; U-06 existe; U-01…U-05 existen; K-01/K-02/K-03/K-04 existen; U-07 **no** existe en SQLite.
2. **Constraints:** insertar un detalle con `cantidad_entregada > cantidad_solicitada` y esperar `IntegrityError`; insertar un movimiento con `tipo_movimiento='AJUSTE'` y esperar `IntegrityError`; insertar dos filas de creación para el mismo ticket y esperar `IntegrityError`; insertar una segunda fila de creación con `estado_origen_id` no nulo y confirmar que pasa.
3. **B2:** dos usuarios con `Admin@X.CL` y `admin@x.cl` → `IntegrityError`; dos proveedores con `76.543.210-8` y `76543210-8` → `IntegrityError`; dos sedes «Sede Central» y « sede central » en la misma institución → `IntegrityError`; las mismas sedes en instituciones distintas → OK; dos departamentos homónimos en la misma institución → `IntegrityError`; dos categorías homónimas → `IntegrityError`.
4. **Servicios:** alta de sede duplicada con distinto case/espacios → 409; edición de sede al nombre de otra → 409; alta/edición de departamento duplicado → 409; alta de proveedor con RUT en otro formato → 409; alta de usuario con correo en mayúsculas → 409.
5. **DTOs:** `MovimientoCrear` sin `stock_sede_id` → 422; `MovimientoInventarioRespuesta` no tiene campos legados; `MovimientoDashboardRespuesta` tampoco.

### 10.4 Regla de oro

Ningún test debe relajar una constraint para pasar. Si un fixture choca con una unicidad, se cambia el dato del fixture (nombre/RUT/correo único), no se elimina la restricción.

## 11. T9 — Tests gated PostgreSQL 16

**ACs:** AC-1, AC-2, AC-3, AC-5, AC-7, AC-8, AC-9, AC-10, AC-11, AC-12, AC-13, AC-16.

### 11.1 Tests existentes a actualizar

| Archivo | Cambio |
|---|---|
| `tests/funcional/sistema/test_instalacion_limpia_postgres.py` | 26/23 tablas, `026.0`, 0 `inventario`, 14 saldos, 3 movimientos, 45/12 |
| `tests/funcional/sistema/test_cobertura_postgres_021.py` | Ajustar la cobertura de tablas e índices; agregar los 15 P0 |
| `tests/funcional/integracion/test_control_instituciones_010.py` | Los tenants aprovisionados en caliente deben tener 23 tablas y los 15 índices |
| `tests/funcional/sistema/test_ciclo_vida_catalogo_postgres_014.py` | Ajustar conteos y cualquier `Inventario` |
| `tests/funcional/sistema/test_compras_postgres_020.py` | Ajustar RUTs duplicados si usa formatos equivalentes |
| `tests/funcional/sistema/test_bootstrap_control_postgres_010.py` | Ajustar conteos/versión |
| `tests/funcional/sistema/test_esquema_postgres.py` | Ajustar 26/23 |

### 11.2 Nuevo `tests/funcional/sistema/test_salud_esquema_postgres_026.py`

Con `POSTGRES_TEST_URL` y base temporal desechable (nunca `apt_erp`):

1. Ejecutar `01_esquema.sql` + `02_datos_semilla.sql` sobre una base temporal y confirmar el arranque limpio.
2. Contar 26 tablas en `control` y 23 en cada `tenant_*`; confirmar que `inventario` no existe en `information_schema.tables`.
3. Confirmar `version_esquema` = `026.0` en control y en los 4 tenants; insertar una segunda fila en un esquema y esperar `UniqueViolation`.
4. Consultar `pg_indexes` y comparar los 15 nombres + columnas en control y en cada tenant.
5. Insertar datos válidos e inválidos para K-03, K-04, U-06, K-01, K-02 y U-01…U-05; los inválidos deben fallar y los válidos pasar.
6. Verificar que `movimiento_inventario.stock_sede_id` es `NOT NULL` y que no existe `inventario_id`.
7. Verificar 14 `stock_sede`, 3 movimientos, 45/12 y 0 movimientos huérfanos.
8. Confirmar que un `INSERT` de dos filas de creación para el mismo ticket falla, pero muchas transiciones con origen no nulo pasan.

### 11.3 Aislamiento

- Usar el patrón existente de `crear_base_temporal` y borrar la base al terminar.
- No tocar `apt_erp`.
- Si el test necesita `Base.metadata.create_all`, aplicar el helper `_crear_indice_version_unica` para que el esquema de prueba tenga U-07.

## 12. T10 — Frontend tests y build

**ACs:** AC-17.

```powershell
cd frontend
$env:CHROME_BIN = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
npx ng test --watch=false --browsers=ChromeHeadless
npx ng build
```

- Confirmar 549 SUCCESS (o el conteo actualizado si T7 agrega/elimina casos).
- `ng build` sin errores ni warnings nuevos.
- Buscar en el bundle que no aparezcan los campos legados.

## 13. T11 — Documentación viva

**ACs:** AC-19.

### 13.1 `docs/spec/stack.md`

- Nota de vigencia (líneas 95–105): 27/24 → **26/23**, `021.1` → **`026.0`**, y mención a la sección 026.
- Agregar una sección `#### Salud del esquema de base de datos (Feature 026)` al final de las secciones de modelo del backend (después de la 021, antes de `### 3. Estructura del Frontend`).
  - Explicar los tres ejes, los 15 índices P0, B1/B2, 5C-lite, 21/26/23 y `026.0`.
  - Justificar el retiro de `inventario` y por qué no hay migración.
  - Aclarar que `CAPACIDADES` conserva `"inventario"` como capacidad funcional.
- No reescribir las secciones históricas 008–021; son registro de su época.

### 13.2 `database/README.md`

- 27/24 → **26/23**.
- `021.1` → **`026.0`**.
- Describir la semilla: 14 `stock_sede`, 3 movimientos, 45/12, sin `inventario`.
- Agregar una línea sobre los 15 índices P0 y las unicidades B2.

### 13.3 `AGENTS.md`

- §4, línea de `database/`: 27 → **26**, 24 → **23**, `021.1` → **`026.0`**.
- §7, línea 114: 22 entidades → **21 entidades**.
- §5: los comandos no cambian.
- §9: no hay skills nuevas ni cambios de agente.

### 13.4 `docs/spec/roadmap.md`

- Agregar la fila 026 en la tabla, inicialmente `[ ]` «En ejecución».
- Al cerrar, marcarla `[x]` con el resumen de ACs, suites, conteos, versión, recorrido 4200 y humo 8080.

### 13.5 `MEMORY.md`

- Estado: features 000…025 cerradas; 026 en ejecución/cerrada.
- Decisión: 5C-lite, 15 índices P0, B1/B2, `026.0`, 21/26/23.
- Errores a evitar: no declarar U-07 en el ORM; no usar `btrim`/`regexp_replace`; no relajar unicidades para que pasen fixtures.
- Mantener ≤ 50 líneas.

### 13.6 `grep` de coherencia

```powershell
rg -n "27 tablas|24 tablas|27/24|021\.1|22 entidades de dominio" AGENTS.md MEMORY.md docs/spec .agents
```

Toda coincidencia debe ser histórica (dentro de una sección de una feature anterior) o estar corregida. Las coincidencias en notas de vigencia, `AGENTS.md` §4/§7 y `MEMORY.md` deben desaparecer.

## 14. T12 — Suites completas y contrato

**ACs:** AC-15, AC-16.

```powershell
cd backend
pytest -q
$env:POSTGRES_TEST_URL = "postgresql://postgres:postgres@localhost:5433/postgres"
pytest -q -m postgres
$env:REDIS_TEST_URL = "redis://127.0.0.1:6380/15"
pytest -q -m redis
```

- Registrar los conteos finales.
- Levantar el backend (`uvicorn` o contenedor) y consultar `GET /openapi.json`:
  - 75 operaciones OpenAPI / 73 de negocio.
  - `POST /api/v1/inventario/movimientos` documenta `stock_sede_id` obligatorio y no `inventario_id`.
  - Los DTOs de dashboard no exponen campos legados.
  - Los 409 nuevos están documentados en las operaciones de sede, departamento y proveedor.
- Ejecutar el test de contrato/permisos existente y confirmar que no cambió la matriz.

## 15. T13 — Reconstrucción del volumen y recorrido 4200

**ACs:** AC-1, AC-2, AC-3, AC-5, AC-18.

### 15.1 Reconstrucción

```powershell
docker compose -f docker-compose.yml down -v
docker compose -f docker-compose.yml up -d
docker compose -f docker-compose.yml logs db --tail 100
```

- Los logs deben mostrar `01:` con 4 tenants de **23 tablas** y `02:` sin excepciones.
- `docker compose ps` con `db`, `redis`, `backend` y `frontend` arriba.

### 15.2 Verificación SQL

Con `psql` o el MCP de PostgreSQL:

```sql
SELECT count(*) FROM information_schema.tables
WHERE table_schema = 'control' AND table_type = 'BASE TABLE';

SELECT table_schema, count(*) FROM information_schema.tables
WHERE table_schema LIKE 'tenant_%' AND table_type = 'BASE TABLE'
GROUP BY table_schema;

SELECT version FROM control.version_esquema;
SELECT version FROM tenant_inst_001_038aa2a9.version_esquema;

-- INST-001 (tenant_inst_001_038aa2a9): 10 saldos, 3 movimientos, 45 y 12.
SELECT count(*) FROM tenant_inst_001_038aa2a9.stock_sede;
SELECT count(*) FROM tenant_inst_001_038aa2a9.movimiento_inventario;
SELECT stock_actual FROM tenant_inst_001_038aa2a9.stock_sede
WHERE sede_id = 2 AND producto_id IN (5, 9) ORDER BY producto_id;

-- INST-002 (tenant_inst_002_5efdced3): 4 saldos, 0 movimientos.
SELECT count(*) FROM tenant_inst_002_5efdced3.stock_sede;
SELECT count(*) FROM tenant_inst_002_5efdced3.movimiento_inventario;

-- Total distribuido: 10 + 4 = 14 saldos y 3 + 0 = 3 movimientos.
SELECT (SELECT count(*) FROM tenant_inst_001_038aa2a9.stock_sede)
     + (SELECT count(*) FROM tenant_inst_002_5efdced3.stock_sede)
     + (SELECT count(*) FROM tenant_inst_003_37b7d724.stock_sede)
     + (SELECT count(*) FROM tenant_inst_004_c24e4e4c.stock_sede) AS saldos,
       (SELECT count(*) FROM tenant_inst_001_038aa2a9.movimiento_inventario)
     + (SELECT count(*) FROM tenant_inst_002_5efdced3.movimiento_inventario)
     + (SELECT count(*) FROM tenant_inst_003_37b7d724.movimiento_inventario)
     + (SELECT count(*) FROM tenant_inst_004_c24e4e4c.movimiento_inventario) AS movimientos;

SELECT count(*) FROM information_schema.tables
WHERE table_name = 'inventario' AND table_schema NOT IN ('pg_catalog', 'information_schema');
```

Esperado: 26; cuatro tenants con 23; `026.0` en control y en los tenants; INST-001 con 10 saldos, 3 movimientos, 45 y 12; INST-002 con 4 saldos y 0 movimientos; total 14 saldos y 3 movimientos; 0 tablas `inventario`. `control.stock_sede` y `control.movimiento_inventario` quedan vacías por la Fase 3: el total se mide sumando los tenants, no en `control`. Los nombres de esquema salen de `pg_temp.nombre_esquema_tenant` (sha256); si cambia la topología, se obtienen con `SELECT nombre_esquema FROM control.mapa_usuario_esquema WHERE institucion_id = 'INST-001'`.

### 15.3 Recorrido funcional en 4200

Con los cuatro roles:

1. **Administrador:** abrir Administración; crear una sede; intentar crearla de nuevo con distinto case/espacios → **409** visible; editar otra sede al mismo nombre → **409**; crear un departamento duplicado → **409**.
2. **Administrador:** crear un proveedor con `76.543.210-8`; intentar `76543210-8` → **409**.
3. **Bodeguero:** abrir inventario; registrar un movimiento de entrada/salida por `stock_sede_id`; confirmar que el saldo cambia y que el historial muestra la sede.
4. **Solicitante:** abrir dashboard; confirmar que la actividad reciente muestra la sede y no un bloque de departamento vacío.
5. **Solicitante:** crear un ticket y abrir su detalle; confirmar que la lectura de detalle e historial funciona.
6. Confirmar 0 errores de consola y que las rutas de dashboard, inventario, tickets y compras responden.

Guardar capturas y la lista de peticiones con su código HTTP.

## 16. T14 — Humo 8080, evidencia y cierre

**ACs:** AC-17, AC-18, AC-19, AC-20.

### 16.1 Build de producción

```powershell
docker compose -f docker-compose.yml build frontend
docker compose -f docker-compose.yml up -d frontend
```

- Abrir `http://localhost:8080`.
- Confirmar que la vista nueva está (dashboard sin campos legados, administración con 409 visible).
- Confirmar que `try_files` sirve las rutas Angular directas (`/dashboard`, `/administracion`, `/inventario`).
- Consola sin errores; no se exige la escritura completa, solo el humo.

### 16.2 Evidencia

Crear `evidencia/README.md` con:

- Línea base y resultados finales de las cuatro suites.
- Salida de la reconstrucción del volumen y de las consultas SQL.
- Conteo de índices por esquema.
- Pruebas negativas de constraints.
- Capturas de 4200 y 8080.
- Enlaces a `spec.md`, `plan.md` y `tasks.md`.

### 16.3 Cierre

- Marcar todas las casillas de `tasks.md`, incluidos los checks de Cierre.
- Marcar cada AC de `spec.md` §6 con su evidencia.
- Actualizar `roadmap.md` y `MEMORY.md`.
- `grep` de coherencia final.
- `git status` y `git diff --stat` limitados a este proyecto; no incluir fases hermanas.

## 17. Estrategia de pruebas

### 17.1 Archivos y cobertura

| Archivo | Tipo | Qué cubre |
|---|---|---|
| `tests/funcional/sistema/test_salud_esquema_026.py` | SQLite | ORM, índices, checks, B2, DTOs |
| `tests/funcional/sistema/test_salud_esquema_postgres_026.py` | Gated PG | Instalación limpia, índices reales, constraints, versión única |
| `tests/funcional/sistema/test_instalacion_limpia_postgres.py` | Gated PG | Conteos y semilla |
| `tests/funcional/sistema/test_cobertura_postgres_021.py` | Gated PG | Cobertura de tablas/índices |
| `tests/funcional/integracion/test_control_instituciones_010.py` | Gated PG | Tenants aprovisionados en caliente |
| `tests/funcional/integracion/test_dashboard_service.py` | SQLite | Actividad sin legado |
| `tests/funcional/integracion/test_dashboard_analitico.py` | SQLite | Contrato de dashboard |
| `tests/funcional/integracion/test_historial_movimientos.py` | SQLite | Historial por sede |
| `tests/funcional/unitarios/test_modelo_sede_011.py` | SQLite | `stock_sede_id` obligatorio |
| `frontend/.../dashboard.service.spec.ts` | Karma | Mock sin campos legados |

### 17.2 Aislamiento

- SQLite en memoria por test; sin dependencia de PostgreSQL.
- Gated PG con base temporal desechable; nunca `apt_erp`.
- Gated Redis con base 15; no se toca la 0.
- Frontend con `ChromeHeadless` apuntando a Edge.

### 17.3 Pruebas manuales obligatorias

- Alta duplicada de sede con distinto case/espacios → 409.
- Edición de sede al nombre de otra → 409.
- Alta/edición duplicada de departamento → 409.
- Alta de proveedor con RUT equivalente → 409.
- Alta de usuario con correo en mayúsculas → 409.
- Movimiento sin `stock_sede_id` → 422.
- Dashboard sin campos departamentales.
- Instalación limpia con 26/23 y `026.0`.

## 18. Matriz tarea → AC

| Tarea | ACs |
|---|---|
| T1 | AC-16 (línea base), AC-14 (inventario) |
| T2 | AC-1, AC-3, AC-4, AC-5, AC-8, AC-9, AC-10, AC-11, AC-12, AC-13, AC-14 |
| T3 | AC-2, AC-3, AC-11, AC-12, AC-13 |
| T4 | AC-4, AC-5, AC-6, AC-7, AC-8, AC-9, AC-10, AC-11, AC-12, AC-13 |
| T5 | AC-4, AC-7, AC-14, AC-15 |
| T6 | AC-11, AC-12, AC-13 |
| T7 | AC-15, AC-17 |
| T8 | AC-4, AC-6, AC-7, AC-8, AC-9, AC-10, AC-11, AC-12, AC-13, AC-14, AC-15 |
| T9 | AC-1, AC-2, AC-3, AC-5, AC-7, AC-8, AC-9, AC-10, AC-11, AC-12, AC-13, AC-16 |
| T10 | AC-17 |
| T11 | AC-19 |
| T12 | AC-15, AC-16 |
| T13 | AC-1, AC-2, AC-3, AC-5, AC-18 |
| T14 | AC-17, AC-18, AC-19, AC-20 |

## 19. Verificación de cierre

### 19.1 Backend

```powershell
cd backend
pytest -q
$env:POSTGRES_TEST_URL = "postgresql://postgres:postgres@localhost:5433/postgres"
pytest -q -m postgres
$env:REDIS_TEST_URL = "redis://127.0.0.1:6380/15"
pytest -q -m redis
```

Criterio: 0 failed; conteos registrados; gated PG con los 15 índices y las constraints nuevas.

### 19.2 Contrato y áreas protegidas

- `/openapi.json` con 75/73.
- `permisos.py` sin diff.
- `CAPACIDADES` contiene `"inventario"`.
- `docker-compose.yml`, `nginx.conf`, `requirements.txt` sin diff.

### 19.3 Frontend

```powershell
cd frontend
$env:CHROME_BIN = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
npx ng test --watch=false --browsers=ChromeHeadless
npx ng build
```

Criterio: 0 failed; build limpio.

### 19.4 Puertos

- 4200: recorrido funcional completo con escritura real.
- 8080: build reconstruido y humo de las vistas tocadas.

### 19.5 Documentación y evidencia

- `grep` de coherencia sin coincidencias obsoletas.
- `evidencia/README.md` completo.
- `roadmap.md` y `MEMORY.md` actualizados.

## 20. Rollback y guardas de alcance

- **Rollback de datos:** `docker compose down -v` + `up -d` vuelve a la semilla anterior solo si el código y el DDL anteriores están en el árbol. Como la feature cambia ambos, el rollback real es `git checkout` del commit previo y reconstruir el volumen.
- **No hay migración inversa:** no se crean scripts `down`.
- **Guarda de alcance:** si durante la implementación aparece la tentación de agregar un índice P1, una tabla nueva, un trigger o un cambio de permisos, se detiene y se abre una feature nueva. La 026 no crece.
- **Guarda de datos:** ninguna constraint se relaja para que pase un fixture; se ajusta el fixture.
- **Guarda de contrato:** si un test existente exige los campos legados, se actualiza el test, no se conserva el campo. La spec manda.
