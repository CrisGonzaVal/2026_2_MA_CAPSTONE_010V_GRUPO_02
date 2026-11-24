# Plan de implementación — Feature 027: Validación de entradas y errores de contrato

**Feature:** `027-validacion-entradas/`
**Spec:** [spec.md](spec.md)
**Enfoque:** doce tareas secuenciales; backend primero (el contrato manda), frontend espejo; sin cambio de esquema.
**Regla:** cada tarea deja la suite en verde; no se relaja ninguna validación para que pase un fixture. Los RUT de prueba se corrigen conservando el cuerpo y recalculando el DV, no se exceptúan.

## 1. Orden de ejecución

```text
T1  helper de RUT (backend) + unitarios
  → T2  contrato de tickets y movimientos
  → T3  contrato de catálogo y usuarios
  → T4  contrato de compras, control y organización + fixtures RUT
  → T5  manejador de errores de BD
  → T6  semilla + barrido de fixtures y mocks
  → T7  helper de RUT (frontend) + unitarios
  → T8  parser de 422 compartido + integración en errores-http
  → T9  formularios de tickets
  → T10 formularios de compras, control y administración
  → T11 integración backend + gated PostgreSQL
  → T12 verificación de cierre, evidencia y documentación
```

Las tareas T2, T3 y T4 son independientes entre sí una vez cerrada T1; pueden ejecutarse en paralelo si se respeta el orden de imports. T5 no depende de T2–T4. T9 y T10 dependen de T7 y T8.

## 2. Archivos y frontera

### 2.1 Archivos nuevos

| Archivo | Propósito |
|---|---|
| `backend/app/core/rut.py` | Normalización, DV módulo 11, validación y formateo del RUT. |
| `backend/app/core/errores_bd.py` | Clasificación de `IntegrityError`/`DataError` y manejador HTTP. |
| `backend/tests/funcional/unitarios/test_rut_027.py` | Tabla de RUT válidos/inválidos y algoritmo. |
| `backend/tests/funcional/unitarios/test_esquemas_027.py` | Límites, rangos, `extra="forbid"` y RUT en DTOs. |
| `backend/tests/funcional/integracion/test_validacion_entradas_027.py` | Endpoints: 201/200/422/409 y campos extra. |
| `backend/tests/funcional/sistema/test_errores_bd_027.py` | Manejador de BD, SQLSTATE/señales SQLite, `X-Request-ID` y 500 desconocido. |
| `backend/tests/funcional/sistema/test_semilla_rut_027.py` | Los siete RUT de la semilla son válidos y los antiguos no están. |
| `backend/tests/funcional/sistema/test_validacion_entradas_postgres_027.py` | Gated PostgreSQL 16: `VARCHAR`, checks y red de seguridad. |
| `frontend/src/app/shared/utils/rut.ts` | Espejo del módulo 11 y `rutValido` como `ValidatorFn`. |
| `frontend/src/app/shared/utils/rut.spec.ts` | Tabla de RUT válidos/inválidos y `rutValido`. |
| `frontend/src/app/shared/utils/validacion-http.ts` | Parser de 422 por campo y traducción de `type`. |
| `frontend/src/app/shared/utils/validacion-http.spec.ts` | Parser, `loc` anidado, traducciones y campo legible. |
| `docs/spec/features/027-validacion-entradas/evidencia/README.md` | Evidencia de cierre. |

### 2.2 Archivos modificados

| Área | Archivos |
|---|---|
| Schemas | `backend/app/schemas/ticket_schema.py`, `producto_schema.py`, `inventario_schema.py`, `usuario_schema.py`, `compra_schema.py`, `control_schema.py`, `organizacion_schema.py` |
| Servicios / core | `backend/app/services/compra_service/proveedores.py` (reexportación), `backend/app/main.py` |
| Datos | `database/01_esquema.sql`, `database/02_datos_semilla.sql` |
| Tests backend | `test_compras.py`, `test_compras_endpoints_020.py`, `test_compras_postgres_020.py`, `test_cobertura_021.py`, `test_aprovisionamiento_postgres_010.py`, `test_transaccion_ticket.py` + los nuevos de §2.1 |
| Frontend shared | `frontend/src/app/shared/utils/errores-http.ts`, `errores-http.spec.ts` |
| Frontend tickets | `tickets.component.ts`, `tickets.component.html`, `tickets.component.spec.ts`, `ticket-detalle.component.ts`, `ticket-detalle.component.html`, `ticket-detalle.component.spec.ts` |
| Frontend compras | `nueva-orden.component.ts`, `nueva-orden.component.html`, `nueva-orden.component.spec.ts`, `lista-ordenes.component.spec.ts`, `recepcion-bodega.component.spec.ts`, `compras.service.spec.ts` |
| Frontend control | `alta-institucion.component.ts`, `alta-institucion.component.html`, `alta-institucion.component.spec.ts`, `instituciones.component.ts`, `instituciones.component.html`, `instituciones.component.spec.ts`, `control.service.spec.ts`, `capacidades.component.spec.ts` |
| Frontend administración | Specs de `usuarios`, `sedes` y `departamentos` (la adopción del parser es central; se agregan casos 422). |
| Documentación | `docs/spec/stack.md` (Nota 5), `docs/spec/roadmap.md`, `docs/spec/deuda-tecnica.md`, `MEMORY.md`, `evidencia/README.md` |

### 2.3 Lo que no se toca

- `database/01_esquema.sql` en su **DDL**, índices, checks, triggers o versión: solo cambian cuatro valores de RUT de la semilla de topología.
- `database/02_datos_semilla.sql` en su estructura, guardias o reparto: solo cambian tres valores de RUT.
- `backend/app/models/**`, `backend/app/core/permisos.py`, `backend/app/api/**`, la matriz de permisos y las rutas.
- `backend/requirements.txt`, `frontend/package.json`, `docker-compose.yml`, `frontend/nginx.conf`.
- `TicketMotivo.motivo` y `TransicionCatalogo.motivo`: siguen validándose en el servicio para preservar la precedencia 404 → 409 → 422 de las Features 013/014. `TransicionCatalogo` solo recibe `extra="forbid"`.
- Features 015 y 016.

## 3. T1 — Helper de RUT (backend)

**ACs:** AC-5 (parcial), AC-12 (soporte).

### 3.1 `backend/app/core/rut.py`

API pública:

```python
def normalizar_rut(rut: str) -> str:
    """Quita puntos, guion y espacios, y devuelve mayúsculas."""

def calcular_dv(cuerpo: str) -> str:
    """Módulo 11: multiplicadores 2..7 desde la derecha; 11→0, 10→K."""

def validar_rut(rut: str) -> str:
    """Valida formato y DV; devuelve la forma visible recortada y en mayúsculas."""

def formatear_rut(rut: str) -> str:
    """Devuelve la forma visible con puntos y guion (solo presentación/pruebas)."""
```

Reglas:

- `normalizar_rut` replica exactamente el comportamiento de la 026: `replace(".", "").replace("-", "").replace(" ", "").upper()`. No se usa una regex que elimine otros caracteres.
- `validar_rut` recibe el valor ya recortado por Pydantic, aplica `strip().upper()`, normaliza los separadores y exige:
  - último carácter `0-9` o `K` (el DV);
  - cuerpo de 1 a 8 dígitos;
  - cuerpo distinto de cero;
  - DV igual a `calcular_dv(cuerpo)`.
- Un DV incorrecto lanza `ValueError("El RUT no es válido: el dígito verificador no corresponde.")`.
- Un formato inválido lanza `ValueError("El RUT debe tener entre 1 y 8 dígitos y un dígito verificador (0-9 o K).")`.
- `formatear_rut` agrupa el cuerpo con puntos desde la derecha y agrega `-DV`; un cuerpo de 1 a 3 dígitos no lleva puntos.
- El helper no conoce HTTP ni Pydantic: es una función pura y testeable.

### 3.2 Reexportación

En `backend/app/services/compra_service/proveedores.py`, reemplazar la implementación local de `normalizar_rut` por:

```python
from app.core.rut import normalizar_rut  # noqa: F401  (reexportación compatible)
```

Se conserva `_clave_rut_sql()` y el pre-check de unicidad sin cambios. Los imports existentes (`from app.services.compra_service.proveedores import normalizar_rut`) siguen funcionando.

### 3.3 Tests

`test_rut_027.py` con tabla:

- Válidos: `76.543.210-3`, `76543210-3`, `765432103`, `77.654.321-7`, `78.765.432-0`, `96.021.030-1`, `1-9`, `k` minúscula.
- Inválidos: `76.543.210-8`, `77.654.321-K`, `78.765.432-1`, `12.345.678-9`, `99-9`, `0-0`, `123456789-0` (9 dígitos), `abc-1`, `12.345.678` (sin DV), `""`.
- `calcular_dv` con cuerpos conocidos y `formatear_rut` con 1, 3, 4 y 8 dígitos.
- `normalizar_rut` conserva la equivalencia de la 026.

## 4. T2 — Contrato de tickets y movimientos

**ACs:** AC-1, AC-3, AC-7 (parcial).

### 4.1 `ticket_schema.py`

- `DetalleTicketCrear`: `producto_id: int = Field(ge=1)`, `cantidad_solicitada: int = Field(gt=0)`, `model_config = ConfigDict(extra="forbid")`.
- `TicketCrear`: `prioridad_id` y `estado_id` con `ge=1`; `asunto` con `StringConstraints(strip_whitespace=True, min_length=3, max_length=150)`; `descripcion: Optional[str] = Field(default=None, max_length=500)`; `detalles` con `min_length=1`; `model_config = ConfigDict(extra="forbid")`. `usuario_id` se conserva declarado e ignorado.
- `TicketActualizarEstado`: `estado_id: int = Field(ge=1)`, `extra="forbid"`.
- `TicketDespacho`: `usuario_id: int = Field(ge=1)`, `extra="forbid"`.
- `TicketEditar`: `asunto` con `StringConstraints(strip_whitespace=True, min_length=3, max_length=150)`; `descripcion` con `max_length=500`; `prioridad_id` con `ge=1`; `detalles` con `min_length=1`; `extra="forbid"`.
- `TicketMotivo` no cambia.

### 4.2 `inventario_schema.py`

- `MovimientoCrear`:
  - `tipo_movimiento: Annotated[Literal["ENTRADA", "SALIDA"], BeforeValidator(_mayusculas)]`, donde `_mayusculas` devuelve `valor.upper()` solo si `isinstance(valor, str)` y, si no, devuelve el valor para que Pydantic emita 422.
  - `cantidad: int = Field(gt=0)`.
  - `observacion: Optional[str] = Field(default=None, max_length=250)`.
  - `stock_sede_id: int = Field(ge=1)`.
  - `model_config = ConfigDict(extra="forbid")`.
- El servicio conserva su rama defensiva de `tipo_movimiento`; deja de ser el camino normal.

### 4.3 Tests

- `test_esquemas_027.py`: 500/501 en `descripcion` de alta y edición; `asunto` de solo espacios; ids `<1`; `extra_forbidden`; `cantidad=0/-1`; `observacion=251`; `tipo="AJUSTE"`; `tipo="entrada"` válido; `stock_sede_id=0`.
- `test_transaccion_ticket.py`: el caso `AJUSTE_MAGICO` pasa de `400` a `422`.
- `test_tickets_*` existentes: verificar que no envían `descripcion` > 500 ni campos extra.

## 5. T3 — Contrato de catálogo y usuarios

**ACs:** AC-2, AC-4, AC-7 (parcial).

### 5.1 `producto_schema.py`

- `ProductoBase`:
  - `nombre` con `StringConstraints(strip_whitespace=True, min_length=1, max_length=150)`.
  - `descripcion: Optional[str] = Field(default=None, max_length=250)`.
  - `unidad_medida: Optional[str] = Field(default=None, max_length=30)`.
  - `stock_minimo: int = Field(default=0, ge=0)`.
  - `categoria_id: int = Field(ge=1)`.
- `ProductoCrear(ProductoBase)`: `model_config = ConfigDict(extra="forbid")`. **No** se pone en `ProductoBase` para no heredarlo a `ProductoRespuesta` (Pydantic v2 fusiona `model_config`).

### 5.2 `usuario_schema.py`

- `UsuarioBase`: `nombre`/`apellido` con `StringConstraints(strip_whitespace=True, min_length=1, max_length=100)`; `departamento_id`/`rol_id` con `ge=1`.
- `UsuarioCrear(UsuarioBase)`: `model_config = ConfigDict(extra="forbid")`. **No** se pone en `UsuarioBase` para no heredarlo a `UsuarioRespuesta`.
- `UsuarioEdicion` conserva sus restricciones actuales.

### 5.3 Tests

- `test_esquemas_027.py`: 150/151 de nombre, 250/251 de descripción, 30/31 de unidad, `stock_minimo=-1`, `categoria_id=0`, `extra_forbidden`, `nombre="   "` y `"  Nombre  "` normalizado.
- `test_esquemas_027.py`: usuario con 100/101, ids `<1`, `extra_forbidden`, nombres de solo espacios.
- Verificar que `ProductoRespuesta` y `UsuarioRespuesta` sigan aceptando su construcción normal (no se contaminó la respuesta).

## 6. T4 — Contrato de compras, control y organización

**ACs:** AC-5, AC-6, AC-7, AC-8.

### 6.1 `compra_schema.py`

- `ProveedorCrear`:
  - `rut: Rut` con `Annotated[str, StringConstraints(strip_whitespace=True, max_length=20), AfterValidator(validar_rut)]`.
  - `razon_social` con `StringConstraints(strip_whitespace=True, min_length=1, max_length=150)`.
  - `model_config = ConfigDict(extra="forbid")`.
  - `correo` sigue siendo `Optional[EmailStr]` con `max_length=100`.
- `OrdenCompraCrear`, `OrdenCompraActualizar`, `FacturaCompraRegistrar`, `CancelacionOrdenCompra`, `CoberturaPreviewSolicitud`: `extra="forbid"`.
- `FacturaCompraRegistrar.numero_factura` con `StringConstraints(strip_whitespace=True, min_length=1, max_length=50)`; `observaciones` con `max_length=500`.
- `CancelacionOrdenCompra.motivo_cancelacion` con `StringConstraints(strip_whitespace=True, min_length=1, max_length=500)`.
- `DetalleOrdenCompraCrear` conserva sus límites y recibe `extra="forbid"`.
- `CoberturaPreviewItem` recibe `extra="forbid"`.

### 6.2 `control_schema.py`

- `InstitucionAltaControlCrear`:
  - `rut: Rut | None = None`.
  - `correo_administrador: EmailStr = Field(max_length=150)`.
  - `nombre`, `nombre_administrador`, `apellido_administrador`, `departamento_nombre_administrativo` con `StringConstraints(strip_whitespace=True, min_length=1, max_length=...)`.
  - Conserva `extra="forbid"`.
- `InstitucionEdicion`:
  - `nombre` con `StringConstraints(strip_whitespace=True, min_length=1, max_length=150)`.
  - `rut: Rut | None = None`.
  - Conserva `extra="forbid"`.
- `None` y `""` se normalizan a `None`: un `BeforeValidator` o un `field_validator` que convierta la cadena vacía/espacios en `None` antes de la validación del RUT. El servicio sigue tratando `None` como RUT omitido.

### 6.3 `organizacion_schema.py`

- `SedeCrear`/`SedeEdicion`: `nombre` con `StringConstraints(strip_whitespace=True, min_length=1, max_length=100)`.
- `DepartamentoCrear`/`DepartamentoEdicion`: `nombre_dep` con `StringConstraints(strip_whitespace=True, min_length=1, max_length=100)`.
- `descripcion`/`direccion` conservan `max_length` y no se recortan por dentro.

### 6.4 Tests y fixtures

- `test_esquemas_027.py`: RUT válidos en todas sus formas; DV inválido, cuerpo no numérico, cuerpo cero, 9 dígitos y 21 caracteres → 422; RUT opcional `None`/`""`; correo inválido → 422; `extra_forbidden`; nombres de solo espacios.
- Actualizar los fixtures RUT de T6 antes de correr la suite, para que las pruebas existentes sigan en verde.

## 7. T5 — Manejador de errores de BD

**ACs:** AC-9.

### 7.1 `backend/app/core/errores_bd.py`

```python
def clasificar_error_bd(exc: Exception) -> tuple[int, str] | None:
    """Devuelve (status, detail) para un error conocido, o None."""

def manejador_error_bd(request: Request, exc: Exception) -> JSONResponse:
    """Traduce el error conocido; si no lo es, lo relanza al 500."""
```

Clasificación:

| Error | Señal PostgreSQL | Señal SQLite | Respuesta |
|---|---|---|---|
| Unicidad | `23505` | `UNIQUE constraint failed` | **409** «El valor ya existe o entra en conflicto con un registro existente.» |
| FK | `23503` | `FOREIGN KEY constraint failed` | **422** «La referencia indicada no existe o no pertenece al ámbito de la operación.» |
| Check | `23514` | `CHECK constraint failed` | **422** «Alguno de los valores enviados no cumple las reglas del recurso.» |
| Not null | `23502` | `NOT NULL constraint failed` | **422** «Falta un valor obligatorio.» |
| Texto largo | `22001` | `String or BLOB exceeds size limit` | **422** «Uno de los textos supera la longitud permitida.» |
| Número fuera de rango | `22003` | `Numeric value out of range` | **422** «Uno de los valores numéricos está fuera de rango.» |

- El SQLSTATE se obtiene de `exc.orig.pgcode` o `exc.orig.diag.sqlstate`; en SQLite se usa el texto de `exc.orig` en minúsculas.
- `X-Request-ID` se toma de `request.scope.get("state", {}).get("request_id")`, igual que el manejador de 500.
- Se registra `logger.error("error de base de datos traducido", extra={"evento": "error_bd", "error_type": type(exc).__name__, "request_id": rid})`; nunca se envía el mensaje de la BD al cliente.
- Un `IntegrityError`/`DataError` sin señal conocida se relanza (`raise exc`) para que `manejador_error_no_controlado` devuelva el 500 existente. **No se convierte un bug en 409/422.**
- No se hace `db.rollback()` en el manejador: el `finally` de `get_db` cierra la sesión y SQLAlchemy revierte la transacción.

### 7.2 `main.py`

Registrar los handlers después del handler genérico:

```python
aplicacion.add_exception_handler(IntegrityError, manejador_error_bd)
aplicacion.add_exception_handler(DataError, manejador_error_bd)
```

FastAPI resuelve el handler más específico por MRO; el 500 genérico sigue cubriendo el resto.

### 7.3 Tests

`test_errores_bd_027.py`:

- `clasificar_error_bd` con `IntegrityError`/`DataError` construidos con `pgcode` simulado y con mensajes SQLite.
- Un `IntegrityError` desconocido devuelve `None`.
- `manejador_error_bd` devuelve JSON con `detail`, status y `X-Request-ID`; el log no contiene el mensaje crudo.
- Ruta de prueba en una app creada con `crear_app()` que lanza cada excepción; verifica 409/422 y que un `RuntimeError` siga dando 500.
- No se usa una ruta de producción nueva.

## 8. T6 — Semilla, fixtures y mocks

**ACs:** AC-12.

### 8.1 Semilla

`database/01_esquema.sql` (topología):

| Registro | Antes | Después |
|---|---|---|
| INST-001 | `65.432.100-9` | `65.432.100-0` |
| INST-002 | `65.887.230-1` | `65.887.230-3` |
| INST-003 | `77.120.540-3` | `77.120.540-2` |
| INST-004 | `65.998.720-K` | `65.998.720-1` |

`database/02_datos_semilla.sql` (proveedores):

| Registro | Antes | Después |
|---|---|---|
| Papelera del Pacífico SpA | `76.543.210-8` | `76.543.210-3` |
| Suministros Corporativos Andinos Ltda. | `77.654.321-K` | `77.654.321-7` |
| Tecnología y Tóner Express S.A. | `78.765.432-1` | `78.765.432-0` |

No se toca ninguna otra línea de la semilla ni la versión `026.0`.

### 8.2 Barrido de fixtures backend

Se conserva el cuerpo y se recalcula el DV. Solo se corrigen los RUT que representan datos válidos; los que una prueba negativa usa a propósito se conservan y se comentan. Se actualizan también las aserciones que comparan el RUT (por ejemplo, `replica.rut == "91.000.000-1"`).

| Archivo | Antes | Después |
|---|---|---|
| `test_aprovisionamiento_postgres_010.py` | `99-9` | `99-K` |
| `test_compras.py` | `12.345.678-9` | `12.345.678-5` |
| `test_compras.py` | `98.765.432-1` | `98.765.432-5` |
| `test_compras.py` | `13.131.313-1` | `13.131.313-6` |
| `test_compras.py` | `14.141.414-1` | `14.141.414-3` |
| `test_compras.py` | `15.151.515-1` | `15.151.515-0` |
| `test_compras.py` | `16.161.616-1` | `16.161.616-8` |
| `test_compras.py` | `17.171.717-1` | `17.171.717-5` |
| `test_compras.py` | `18.181.818-1` | `18.181.818-2` |
| `test_compras.py` | `19.191.919-1` | `19.191.919-K` |
| `test_compras.py` | `20.202.020-1` | `20.202.020-8` |
| `test_compras.py` | `21.212.121-1` | `21.212.121-5` |
| `test_compras.py` | `31.313.131-1` | `31.313.131-9` |
| `test_compras_endpoints_020.py` | `52.000.000-2` | `52.000.000-3` |
| `test_compras_endpoints_020.py` | `53.000.000-3` | `53.000.000-1` |
| `test_compras_endpoints_020.py` | `54.000.000-4` | `54.000.000-K` |
| `test_compras_endpoints_020.py` | `55.000.000-5` | `55.000.000-8` |
| `test_compras_endpoints_020.py` | `57.000.000-7` | `57.000.000-4` |
| `test_compras_endpoints_020.py` | `58.000.000-8` | `58.000.000-2` |
| `test_compras_endpoints_020.py` | `59.000.000-9` | `59.000.000-0` |
| `test_compras_postgres_020.py` | `91.000.000-1` | `91.000.000-4` |
| `test_cobertura_021.py` | `96.021.010-1` | `96.021.010-7` |
| `test_cobertura_021.py` | `96.021.020-1` | `96.021.020-4` |
| `test_cobertura_021.py` | `96.021.040-1` | `96.021.040-9` |
| `test_cobertura_021.py` | `96.021.041-1` | `96.021.041-7` |
| `test_cobertura_021.py` | `96.021.042-1` | `96.021.042-5` |
| `test_cobertura_021.py` | `96.021.043-1` | `96.021.043-3` |
| `test_cobertura_021.py` | `96.021.045-1` | `96.021.045-K` |
| `test_cobertura_021.py` | `96.021.046-1` | `96.021.046-8` |
| `test_cobertura_021.py` | `96.021.047-1` | `96.021.047-6` |
| `test_cobertura_021.py` | `96.021.050-1` | `96.021.050-6` |
| `test_cobertura_021.py` | `96.021.051-1` | `96.021.051-4` |
| `test_cobertura_021.py` | `96.021.052-1` | `96.021.052-2` |
| `test_cobertura_021.py` | `96.021.053-1` | `96.021.053-0` |

Ya son válidos y no se tocan: `77.777.777-7`, `11.111.111-1`, `22.222.222-2`, `92.000.000-2`, `96.021.030-1`, `96.021.044-1`, `56.000.000-6`.

### 8.3 Mocks frontend

| Archivo | Antes | Después |
|---|---|---|
| `compras.service.spec.ts` | `76.543.210-K` | `76.543.210-3` |
| `lista-ordenes.component.spec.ts` | `76.543.210-K` | `76.543.210-3` |
| `recepcion-bodega.component.spec.ts` | `76.543.210-K` | `76.543.210-3` |
| `nueva-orden.component.spec.ts` | `76.543.210-K` | `76.543.210-3` |
| `alta-institucion.component.spec.ts` | `76.111.222-3` | `76.111.222-8` |
| `instituciones.component.spec.ts` | `76.111.222-3` | `76.111.222-8` |
| `control.service.spec.ts` | `76.111.222-3` | `76.111.222-8` |
| `capacidades.component.spec.ts` | `76.111.222-3` | `76.111.222-8` |

`11.111.111-1` ya es válido y no se toca.

### 8.4 Test de semilla

`test_semilla_rut_027.py`:

- Lee `database/01_esquema.sql` y `database/02_datos_semilla.sql` desde la ruta del repositorio.
- Verifica que los siete RUT corregidos están presentes y que los siete antiguos ya no.
- Valida cada uno con `validar_rut`.
- No depende del contenedor `db`; corre en la suite SQLite.

## 9. T7 — Helper de RUT (frontend)

**ACs:** AC-11 (parcial).

`frontend/src/app/shared/utils/rut.ts`:

```ts
export function normalizarRut(rut: string): string;
export function calcularDv(cuerpo: string): string;
export function validarRut(rut: string): boolean;
export function formatearRut(rut: string): string;
export function rutValido(control: AbstractControl): ValidationErrors | null;
```

- Misma tabla de multiplicadores y mismos límites que el backend (1–8 dígitos, cuerpo no cero, DV `0-9`/`K`, `k` → `K`).
- `rutValido` devuelve `null` para vacío o solo espacios (el `required` decide), y `{ rutInvalido: true }` para un valor no vacío inválido.
- No depende de servicios ni de `HttpClient`; es un `ValidatorFn` puro.
- `rut.spec.ts` replica la tabla de T1, incluyendo `formatearRut` y el caso vacío.

## 10. T8 — Parser de 422 compartido

**ACs:** AC-10 (parcial).

### 10.1 `frontend/src/app/shared/utils/validacion-http.ts`

```ts
export interface DetalleError422 {
  loc: (string | number)[];
  msg: string;
  type: string;
}

export function detallesDeValidacion(error: HttpErrorResponse): DetalleError422[];
export function mensajeDeCampo(detalles: DetalleError422[], campo: string): string | null;
export function mensajeDeDetalle(
  detalles: DetalleError422[],
  indice: number,
  campo: string,
): string | null;
export function traducirMensajeValidacion(detalle: DetalleError422): string;
export function mensajeDeValidacion(error: HttpErrorResponse): string | null;
```

- `detallesDeValidacion` devuelve `[]` si `detail` no es un array o el error no es 422.
- `mensajeDeCampo` busca el último elemento de `loc` igual a `campo`; `mensajeDeDetalle` exige `loc.at(-2) === indice` y `loc.at(-1) === campo`.
- `traducirMensajeValidacion` traduce: `string_too_short`, `string_too_long`, `missing`, `greater_than`, `greater_than_equal`, `less_than`, `less_than_equal`, `literal_error`, `extra_forbidden`, `int_parsing`, `decimal_parsing`, `date_parsing`, `bool_parsing`, `string_type`, `int_type`, y `value_error` (usa el `msg` en español del backend, quitando el prefijo `Value error, `; si menciona `email`, devuelve «El correo no tiene un formato válido.»).
- `mensajeDeValidacion` devuelve el primer detalle traducido, prefijado con un nombre legible del campo (`campoLegible`): `descripcion` → «Descripción», `rut` → «RUT», `razon_social` → «Razón social», `cantidad`/`cantidad_solicitada` → «Cantidad», `stock_minimo` → «Stock mínimo», etc. Si `loc.at(-2)` es un número, prefija «Fila N: ».
- `campoLegible` humaniza `snake_case` como fallback.

### 10.2 `errores-http.ts`

En el caso `422`, antes de devolver `mensajes[422]`:

```ts
const validacion = mensajeDeValidacion(error);
if (validacion) return validacion;
```

Así todos los dominios que ya usan `mensajeDeErrorHttp` (`compras-errores`, `administracion-errores`, `control-errores`, `mensajeDeErrorCatalogo`, `mensajeDeErrorTickets`, `mensajeDeErrorProducto`) muestran el campo culpable sin duplicar lógica. `mensajeDeErrorHttp` sigue prefiriendo el `detail` textual y cubriendo 401/403/404/409/500/red.

### 10.3 Tests

- `validacion-http.spec.ts`: lista simple, `loc` anidado con índice, `extra_forbidden`, `value_error` con email, `string_too_long` con límite, `mensajeDeCampo`/`mensajeDeDetalle`, y `detail` textual/`null`.
- `errores-http.spec.ts`: el caso 422 con lista ahora espera el mensaje traducido; se conserva el 422 sin lista con el texto del dominio.

## 11. T9 — Formularios de tickets

**ACs:** AC-1, AC-10.

- `tickets.component.ts`:
  - `descripcion` con `Validators.maxLength(500)`.
  - Eliminar `DetalleError422` y `traducirMensaje` locales; importar `detallesDeValidacion`, `mensajeDeCampo`, `mensajeDeDetalle`.
  - `mensajeDe(campo)` y `mensajeDeDetalle(indice)` delegan en el helper compartido.
  - En el error 422, `this.detalleErrores.set(detallesDeValidacion(fallo))` y el aviso «Revisa los campos marcados.» se conserva.
- `tickets.component.html`: `maxlength="500"` en el textarea de descripción del alta.
- `ticket-detalle.component.ts`:
  - `formularioEdicion.descripcion` con `Validators.maxLength(500)`.
  - `fallarOperacion` sigue usando `mensajeDeErrorTickets`; ahora muestra el campo culpable vía `errores-http`.
- `ticket-detalle.component.html`: `maxlength="500"` en el textarea de descripción de la edición.
- Specs:
  - Alta con `descripcion` de 501 simulada por 422: el mensaje menciona «Descripción» y no hay 500.
  - Edición con 422: el mensaje menciona el campo.
  - `maxlength` presente en ambos textareas.

## 12. T10 — Formularios de compras, control y administración

**ACs:** AC-10, AC-11.

### 12.1 RUT

- `nueva-orden.component.ts`: `rut: ['', [Validators.required, Validators.maxLength(20), rutValido]]`.
- `alta-institucion.component.ts`: `rut: ['', [Validators.maxLength(20), rutValido]]`.
- `instituciones.component.ts`: `rut: ['', [Validators.maxLength(20), rutValido]]`.
- Los tres templates muestran «El RUT no es válido: revisa el dígito verificador.» cuando el control está inválido y tocado, y bloquean el envío (`formulario.invalid` ya lo hace).
- `alta-institucion.component.ts` mantiene su `mensajeDeError` para 409/503, pero ante un 422 con lista usa `mensajeDeValidacion(error)` antes del switch.

### 12.2 Mensajes 422

- `compras-errores.ts`, `administracion-errores.ts` y `control-errores.ts` no cambian de firma; heredan el campo culpable de `mensajeDeErrorHttp`.
- Se agregan tests puros por dominio:
  - `mensajeDeErrorCompras` con 422 de `rut`/`cantidad_solicitada` → mensaje con el campo.
  - `mensajeDeErrorAdministracion` con 422 de `nombre`/`correo` → mensaje con el campo.
  - `mensajeDeErrorControl` con 422 de `rut`/`correo_administrador` → mensaje con el campo.
- `lista-ordenes.component.ts` (factura/cancelación), `recepcion-bodega.component.ts`, `usuarios.component.ts`, `sedes.component.ts` y `departamentos.component.ts` no requieren cambios de lógica: ya usan el helper del dominio. Se agrega al menos un caso 422 en sus specs.

### 12.3 Specs de RUT

- `nueva-orden.component.spec.ts`: un RUT con DV inválido marca el control y no dispara el POST; uno válido lo dispara.
- `alta-institucion.component.spec.ts`: RUT opcional vacío válido; RUT inválido bloquea; RUT válido envía.
- `instituciones.component.spec.ts`: edición con RUT inválido bloquea; vacío envía `null`.

## 13. T11 — Integración backend y gated PostgreSQL

**ACs:** AC-5, AC-6, AC-9, AC-15 (parcial).

### 13.1 Integración SQLite

`test_validacion_entradas_027.py`:

- Tickets: 500 → 201; 501 → 422 con `loc` en `descripcion`; campo extra → 422; `asunto` de solo espacios → 422.
- Productos: límites 150/250/30/0 → 201; 151/251/31/-1 → 422; `categoria_id=0` → 422 (no 404).
- Movimientos: `ENTRADA`/`entrada` y cantidad 1 → 201; cantidad 0, observación 251, `AJUSTE`, `stock_sede_id=0` → 422; ya no hay 400.
- Usuarios: 100 → 201; 101 → 422; ids `<1` → 422; solo espacios → 422.
- Proveedores: RUT válido en cuatro formas → 201; DV inválido → 422; duplicado válido en otra forma → 409.
- Instituciones: RUT válido/omitido → 201/200; RUT inválido → 422; correo inválido → 422.
- `extra="forbid"` en cada DTO listado; `TicketCrear.usuario_id` sigue aceptado e ignorado.

### 13.2 Gated PostgreSQL 16

`test_validacion_entradas_postgres_027.py`, con el patrón de base temporal de los tests gated existentes:

- Insertar un `VARCHAR` en el límite y en límite+1; el segundo responde 422 (no 500).
- `stock_minimo=-1` y `cantidad=0` fallan por check y responden 422.
- Un `IntegrityError` de unicidad que no pase por el pre-check responde 409 vía `manejador_error_bd`.
- Un `DataError` de truncamiento responde 422 vía `manejador_error_bd`.
- Un error desconocido sigue dando 500.
- La instalación limpia conserva `026.0`, 26/23 tablas y 21 entidades (AC-13).

## 14. T12 — Verificación de cierre, evidencia y documentación

**ACs:** AC-13…AC-19.

### 14.1 Suites

```powershell
cd backend
pytest -q
$env:POSTGRES_TEST_URL = "postgresql://postgres:postgres@localhost:5433/postgres"
pytest -q -m postgres
$env:REDIS_TEST_URL = "redis://127.0.0.1:6380/15"
pytest -q -m redis

cd ..\frontend
$env:CHROME_BIN = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
npx ng test --watch=false --browsers=ChromeHeadless
npx ng build
```

Registrar conteos exactos y confirmar que no hay regresiones.

### 14.2 Contrato y esquema

- `/openapi.json`: 75 operaciones / 73 de negocio, sin rutas nuevas; `tipo_movimiento` publica su enum; los 422 están documentados.
- `grep` de `VERSION_ESQUEMA_OBJETIVO`/`026.0` y de los conteos 26/23/21.
- `down -v` + `up -d`; la guardia fail-closed de `02_` pasa y los siete RUT de la semilla son válidos.

### 14.3 Recorrido 4200

Con escritura real:

1. Ticket con descripción de 501 → 422 con mensaje de campo; 500 → 201.
2. Proveedor con RUT inválido → 422; RUT válido → 201; duplicado → 409.
3. Institución con RUT inválido → 422; RUT válido/omitido → 201/200.
4. Movimiento inválido por API → 422; válido → 201.
5. Campo extra → 422.
6. Nombre de solo espacios → 422.
7. Consola sin errores.

### 14.4 Humo 8080

```powershell
docker compose -f docker-compose.yml build frontend
docker compose -f docker-compose.yml up -d frontend
```

Verificar que las vistas tocadas cargan, el flujo básico responde y la consola no muestra errores.

### 14.5 Documentación

- `docs/spec/stack.md` Nota 5: describir el parser compartido de 422 y el validador de RUT.
- `docs/spec/deuda-tecnica.md`: DT-13…DT-16 quedan absorbidos; al cierre se retiran o se marca su estado final.
- `docs/spec/roadmap.md`: 027 cerrada con conteos y evidencia.
- `MEMORY.md`: estado final y decisiones.
- `evidencia/README.md`: línea base, suites, contrato, semilla, 4200 y 8080.

## 15. Matriz AC → tarea → evidencia

| AC | Tarea(s) | Evidencia |
|---|---|---|
| AC-1 | T2, T9 | Tests de schema/endpoint + specs de tickets + 4200 |
| AC-2 | T3, T11 | Tests de schema/endpoint + gated PG |
| AC-3 | T2, T11 | Tests de schema/endpoint + gated PG |
| AC-4 | T3, T11 | Tests de schema/endpoint |
| AC-5 | T1, T4, T11 | `test_rut_027` + endpoints + gated PG |
| AC-6 | T4, T11 | Tests de control + endpoint |
| AC-7 | T2–T4 | Tests parametrizados por DTO |
| AC-8 | T3, T4 | Tests de schemas + endpoint |
| AC-9 | T5, T11 | `test_errores_bd_027` + gated PG |
| AC-10 | T8–T10 | Specs de `validacion-http` + dominios + formularios |
| AC-11 | T7, T10 | Specs de `rut` + tres formularios |
| AC-12 | T6 | `test_semilla_rut_027` + `grep` + reset |
| AC-13 | T11, T12 | Gated de instalación limpia + `grep` |
| AC-14 | T12 | `/openapi.json` + `MATRIZ_PERMISOS` sin diff |
| AC-15 | T12 | Salidas de las tres corridas |
| AC-16 | T12 | `ng test` + `ng build` |
| AC-17 | T12 | `evidencia/README.md` §4200 |
| AC-18 | T12 | `evidencia/README.md` §8080 |
| AC-19 | T12 | `grep` de coherencia y diff documental |

## 16. Riesgos y mitigaciones

| Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|
| `extra="forbid"` en `ProductoBase`/`UsuarioBase` se hereda a las respuestas y rompe su serialización | Media | Alto | Se declara en `ProductoCrear`/`UsuarioCrear`, no en la base; test explícito de respuesta. |
| El manejador de BD convierte un bug en 409/422 | Media | Alto | Solo se traducen SQLSTATE/señales conocidas; lo desconocido se relanza al 500 y se registra con traza. |
| `DataError` no es subclase de `IntegrityError` y el handler no lo captura | Baja | Medio | Se registran ambos tipos por separado; test con cada uno. |
| `X-Request-ID` no está disponible en el handler | Baja | Bajo | Se lee de `request.scope["state"]`, igual que el 500; test de correlación. |
| Los fixtures RUT inválidos son decenas y alguno se escapa | Alta | Alto | Barrido table-driven de T6 + suite completa; los tests fallan si queda uno. |
| SQLite no aplica `VARCHAR(n)` y el 500 por truncamiento no se reproduce | Alta | Medio | Tests de schema para el 422 + gated PostgreSQL con el valor límite y límite+1. |
| `BeforeValidator` de `tipo_movimiento` recibe un no-`str` y lanza `AttributeError` | Baja | Medio | El validador devuelve el valor sin tocar si no es `str`; test con entero/`None`. |
| El cambio de `errores-http` para 422 rompe specs que esperaban el texto genérico | Media | Bajo | Actualizar `errores-http.spec.ts` y los specs de dominio; el 422 sin lista conserva el texto. |
| El RUT opcional `""` se valida como inválido | Media | Medio | `BeforeValidator` convierte `""`/espacios en `None`; test de alta/edición de institución. |
| La semilla de instituciones se pasa por alto | Media | Medio | T6 incluye `01_esquema.sql`; test de semilla valida los siete RUT. |
| La adopción del parser deja un formulario sin mensaje por campo | Media | Medio | Adopción central en `errores-http` + tests por dominio + recorrido 4200. |
| El `maxlength` del textarea no cubre la edición | Media | Bajo | Se aplica en alta y edición; el backend valida ambos. |
| El test de correlación 500 (`/_prueba-500-024`) se ve afectado | Baja | Medio | El handler solo captura `IntegrityError`/`DataError`; el 500 genérico sigue en `ServerErrorMiddleware`. |

## 17. Definición de Done

- [x] T1–T12 marcadas en `tasks.md`.
- [x] `pytest` SQLite, gated PostgreSQL y gated Redis en verde, con conteos registrados.
- [x] `ng test` en verde y `ng build` limpio.
- [x] `/openapi.json` conserva 75/73 operaciones y publica el enum de `tipo_movimiento`.
- [x] Semilla con los siete RUT válidos y reset `down -v`/`up -d` sin errores.
- [x] Recorrido 4200 con los casos de AC-17.
- [x] Humo 8080 con imagen reconstruida.
- [x] `spec.md` §6 con cada AC marcado y su evidencia.
- [x] `deuda-tecnica.md`, `roadmap.md`, `MEMORY.md`, `stack.md` y `evidencia/README.md` sincronizados.
- [x] `grep` de coherencia de rutas y conteos sin referencias obsoletas.
