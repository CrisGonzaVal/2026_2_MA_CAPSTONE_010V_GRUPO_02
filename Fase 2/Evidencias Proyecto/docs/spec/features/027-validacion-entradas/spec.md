# Feature 027: Validación de entradas y errores de contrato

**Estado:** Cerrada y verificada (24/Nov/2026)
**Release:** 2.0 — Sprint 7 (antes de 015/016)
**Tipo:** Endurecimiento de contrato (Pydantic v2 + UX), sin cambio de esquema
**Sucede a:** Feature 026 (salud del esquema BD, cerrada el 18/Nov/2026)

## 1. Problema

La auditoría de entradas del 23/Nov/2026 encontró cuatro familias de huecos que
hoy no rompen la demo con datos QA, pero que sí producen errores 500, datos
inválidos o mensajes que no dicen qué corregir. Ninguna requiere cambiar el
modelo de datos; todas se cierran en el contrato y en la interfaz.

### 1.1 El contrato acepta valores que la base rechaza

Varios DTO de entrada no declaran las longitudes, rangos ni tipos que el DDL ya
impone. En SQLite la suite no lo nota porque no aplica `VARCHAR(n)`; en
PostgreSQL el `INSERT` falla con `DataError` o `IntegrityError` y el usuario
recibe un 500 sin detalle.

| DTO | Campo | Límite real (DDL) | Hoy | Consecuencia |
|---|---|---|---|---|
| `TicketCrear` / `TicketEditar` | `descripcion` | `VARCHAR(500)` | sin `max_length` | 500 por truncamiento; es el gap más visible porque el textarea no tiene `maxlength` |
| `ProductoBase` | `nombre` | `VARCHAR(150)` | sin `max_length` | 500 por truncamiento |
| `ProductoBase` | `descripcion` | `VARCHAR(250)` | sin `max_length` | 500 por truncamiento |
| `ProductoBase` | `unidad_medida` | `VARCHAR(30)` | sin `max_length` | 500 por truncamiento |
| `ProductoBase` | `stock_minimo` | `CHECK (stock_minimo >= 0)` | sin `ge=0` | 500 por check |
| `ProductoBase` | `categoria_id` | FK a `categoria` | sin `ge=1` | 404 del servicio para un id inexistente; el contrato no expresa que 0 no es un id válido |
| `MovimientoCrear` | `cantidad` | `CHECK (cantidad > 0)` | sin `gt=0` | 500 por check |
| `MovimientoCrear` | `observacion` | `VARCHAR(250)` | sin `max_length` | 500 por truncamiento |
| `MovimientoCrear` | `tipo_movimiento` | `CHECK IN ('ENTRADA','SALIDA')` | `str` libre | 400 del servicio, no 422; inconsistente con el resto |
| `MovimientoCrear` | `stock_sede_id` | FK a `stock_sede` | sin `ge=1` | 404 del servicio para un id inexistente |
| `UsuarioBase` | `nombre` / `apellido` | `VARCHAR(100)` | sin `max_length` | 500 por truncamiento |
| `UsuarioBase` | `departamento_id` / `rol_id` | FK | sin `ge=1` | 404 del servicio; el contrato no expresa el rango |
| `InstitucionAltaControlCrear` | `correo_administrador` | `VARCHAR(150)` | `str`, no `EmailStr` | un correo mal formado llega a Clerk o a la BD; el error no es un 422 de validación |
| `ProveedorCrear` / `InstitucionAltaControlCrear` / `InstitucionEdicion` | `rut` | `VARCHAR(20)` | solo longitud | ver §1.2 |
| `SedeCrear/Edicion`, `DepartamentoCrear/Edicion`, `ProductoBase`, `UsuarioBase`, `ProveedorCrear`, `InstitucionAltaControlCrear` | nombres y razones sociales | `NOT NULL` + `VARCHAR` | `min_length=1` (o ausencia de límite) deja pasar `"   "` | el servicio hace `strip()` y puede guardar una cadena vacía |
| Varios DTO de alta/edición | campos desconocidos | — | se ignoran silenciosamente | el cliente cree que guardó un campo que el servidor descartó |

Los DTO sin `extra="forbid"` son: `TicketCrear`, `TicketEditar`,
`DetalleTicketCrear`, `TicketActualizarEstado`, `TicketDespacho`, `ProductoBase`,
`MovimientoCrear`, `UsuarioBase`, `ProveedorCrear`, `DetalleOrdenCompraCrear`,
`OrdenCompraCrear`, `OrdenCompraActualizar`, `FacturaCompraRegistrar`,
`CancelacionOrdenCompra`, `CoberturaPreviewItem`, `CoberturaPreviewSolicitud` y
`TransicionCatalogo`.

### 1.2 El RUT no valida el dígito verificador

`normalizar_rut()` en `backend/app/services/compra_service/proveedores.py` quita
puntos, guion y espacios, y el índice funcional `proveedor_rut_normalizado_uk`
garantiza unicidad. Pero **nadie comprueba el dígito verificador**: el sistema
acepta `76.543.210-8`, `77.654.321-K` y `78.765.432-1`, que son inválidos.

El mismo hueco existe en el RUT de institución (`control_schema`), que ni
siquiera tiene unicidad funcional. En el frontend, los tres formularios que
piden RUT solo aplican `Validators.maxLength(20)`.

La semilla de la 026 sembró esos tres RUT inválidos en `control.proveedor` y sus
réplicas tenant. Además, la topología de `01_esquema.sql` sembró cuatro RUT
institucionales con DV inválido: `65.432.100-9` (debe ser `-0`), `65.887.230-1`
(debe ser `-3`), `77.120.540-3` (debe ser `-2`) y `65.998.720-K` (debe ser `-1`).
Los mocks de frontend usan `76.543.210-K` y `76.111.222-3`, también inválidos, y
varios fixtures de tests usan cuerpos con DV incorrecto. La spec y la evidencia
de la 026 usan `76.543.210-8` como ejemplo histórico de unicidad; esos documentos
**no se reescriben**: la 027 corrige los datos vivos y deja constancia de que el
ejemplo de la 026 no era un RUT válido.

### 1.3 Los errores no dicen qué corregir

- Un 422 de Pydantic devuelve `detail` como lista de `{loc, msg, type}`. Solo
  `tickets.component.ts` la parsea y traduce por campo. El resto de formularios
  usa `mensajeDeErrorHttp`, que para una lista cae al texto genérico del 422.
- `ticket-detalle.component.ts` tampoco parsea la lista: una edición con
  `descripcion` de 501 caracteres mostraría un mensaje genérico.
- `tipo_movimiento` inválido responde 400 con un texto claro, mientras el resto
  de validaciones de forma responde 422. Dos contratos para el mismo tipo de
  error.
- `IntegrityError` y `DataError` no tienen manejador: suben como 500 en texto
  plano (`"Internal Server Error"`), sin `detail` accionable. El
  `X-Request-ID` se conserva, pero el usuario no sabe qué campo corregir.
- Un campo extra se ignora sin avisar; el cliente no descubre que su dato no se
  guardó.

### 1.4 La semilla contradice la regla que se quiere imponer

Si la 027 valida el DV y la semilla conserva RUT inválidos, el catálogo muestra
proveedores e instituciones que la propia API rechazaría al recrearlos. La
incoherencia es de datos, no de esquema: se corrige el DV de las siete filas
(tres proveedores y cuatro instituciones) y se alinean los mocks y fixtures que
pasan por el contrato.

## 2. Objetivo

Cerrar las cuatro familias en **una sola feature** (027), con dos capas
explícitas:

1. **Backend — contrato:** alinear cada DTO con el DDL, validar el RUT con
   módulo 11, rechazar campos extra y traducir los errores de BD a 409/422 con
   `detail` claro.
2. **Frontend — UX:** espejo del validador de RUT, `maxlength` en la descripción
   del ticket y un parser compartido de 422 por campo adoptado por todos los
   formularios validados.

Al cierre: **0 respuestas 500 por entradas inválidas** en los endpoints
cubiertos, **100 % de los RUT de la semilla válidos** y **todos los formularios
validados muestran el campo culpable** cuando el backend responde 422.

No hay cambio de esquema, de versión (`026.0`), de número de tablas (26/23), de
entidades (21), de rutas ni de matriz de permisos. No se agrega ninguna
dependencia: `pydantic[email]` ya está instalado y `EmailStr` ya se usa en
`usuario_schema` y `compra_schema`.

## 3. Alcance

### 3.1 Dentro de alcance

- `backend/app/schemas/ticket_schema.py`: `descripcion` con `max_length=500`,
  ids con `ge=1`, `extra="forbid"` y `asunto` sin espacios exteriores.
- `backend/app/schemas/producto_schema.py`: longitudes del DDL, `stock_minimo`
  con `ge=0`, `categoria_id` con `ge=1`, `extra="forbid"` en `ProductoCrear`
  (no en `ProductoBase`, para no heredarlo a `ProductoRespuesta`) y nombres sin
  espacios exteriores.
- `backend/app/schemas/inventario_schema.py`: `tipo_movimiento` como
  `Literal["ENTRADA","SALIDA"]` normalizado a mayúsculas, `cantidad` con
  `gt=0`, `observacion` con `max_length=250`, `stock_sede_id` con `ge=1` y
  `extra="forbid"`.
- `backend/app/schemas/usuario_schema.py`: longitudes de `nombre`/`apellido`,
  `ge=1` en ids, `extra="forbid"` en `UsuarioCrear` (no en `UsuarioBase`, para
  no heredarlo a `UsuarioRespuesta`) y nombres sin espacios exteriores.
- `backend/app/schemas/compra_schema.py`: RUT con DV en `ProveedorCrear`,
  `extra="forbid"` en los DTO de alta/edición, `razon_social` sin espacios
  exteriores y `motivo_cancelacion` sin espacios exteriores.
- `backend/app/schemas/control_schema.py`: RUT con DV en alta y edición de
  institución, `correo_administrador: EmailStr`, nombres sin espacios exteriores
  y `extra="forbid"` donde falte.
- `backend/app/schemas/organizacion_schema.py`: nombres de sede y departamento
  sin espacios exteriores (los `max_length` y `extra="forbid"` ya existen).
- `backend/app/core/rut.py` (nuevo): `normalizar_rut`, `calcular_dv`,
  `validar_rut` y `formatear_rut`; `proveedores.normalizar_rut` se conserva como
  reexportación para no romper imports ni tests.
- `backend/app/core/errores_bd.py` (nuevo) y `backend/app/main.py`: traducción
  de `IntegrityError`/`DataError` a 409/422 con `detail` claro, `X-Request-ID` y
  registro del error original sin filtrarlo al cliente.
- `database/01_esquema.sql`: DV corregido en los cuatro RUT de
  `control.institucion` (`65.432.100-0`, `65.887.230-3`, `77.120.540-2`,
  `65.998.720-1`).
- `database/02_datos_semilla.sql`: DV corregido en los tres proveedores
  (`76.543.210-3`, `77.654.321-7`, `78.765.432-0`).
- `frontend/src/app/shared/utils/rut.ts` (nuevo): espejo del validador y del
  formateo; `rutValido` como `ValidatorFn` de Angular.
- `frontend/src/app/shared/utils/validacion-http.ts` (nuevo): parser compartido
  de 422 por campo y traducción de los `type` de Pydantic.
- `frontend/src/app/features/tickets/tickets.component.{ts,html}` y
  `ticket-detalle.component.{ts,html}`: `maxlength="500"` y
  `Validators.maxLength(500)` en `descripcion`; adopción del parser compartido.
- `frontend/src/app/features/compras/**`, `control/**`,
  `administracion/**`: adopción del parser compartido en los formularios
  validados y del validador de RUT en los tres campos que lo piden.
- Tests de backend (unitarios, integración, sistema y gated PostgreSQL), tests
  de frontend y evidencia de cierre.
- Documentación: `docs/spec/deuda-tecnica.md`, `docs/spec/roadmap.md`,
  `docs/spec/stack.md` (Nota 5), `MEMORY.md` y
  `docs/spec/features/027-validacion-entradas/evidencia/README.md`.

### 3.2 Fuera de alcance

- **Cambios de DDL, índices, checks, triggers o versión de esquema.** El DV no
  se puede expresar razonablemente en un `CHECK`; se valida en el contrato. La
  base se reconstruye con `down -v` + `up -d`, pero no cambia.
- **Nuevos endpoints o cambios en la matriz de permisos.** Las rutas y los roles
  se conservan; solo cambia la validación de los cuerpos.
- **Migraciones de datos.** La semilla se corrige y el volumen se recrea; no se
  escribe un script incremental.
- **RUT de datos históricos o inserciones directas.** Sin trigger ni función de
  BD, una escritura directa puede seguir guardando un DV inválido. La API es la
  frontera validada.
- **Formularios de producto y movimiento.** Hoy no existen en la UI (solo el
  servicio HTTP); su validación se cierra en el backend y se prueba por API.
- **Rediseño de la experiencia de error.** No se cambia el layout ni el sistema
  visual; solo se agregan mensajes por campo y el texto de fallback del 500.
- **Unicidad de nombre de producto, de sede o de categoría.** Sigue siendo una
  decisión de negocio pendiente (026 §3.2).
- **Features 015 y 016** (informes y notificaciones), que quedan después de la
  027 en el Sprint 7.

## 4. Decisiones de diseño

### D-1 — Una feature, dos capas, un solo criterio

El contrato del backend y la UX del frontend son la misma regla vista desde dos
lados. Separarlos obligaría a mantener dos specs para el mismo `max_length`, el
mismo DV y el mismo 422. Se implementan juntos: el backend fija la verdad y el
frontend la anticipa, pero el servidor sigue siendo la autoridad.

### D-2 — RUT con módulo 11 en un helper compartido

Se crea `backend/app/core/rut.py` con la regla chilena:

1. `normalizar_rut(rut)` quita puntos, guion y espacios, y aplica `upper`.
2. `calcular_dv(cuerpo)` multiplica los dígitos desde la derecha por
   `2,3,4,5,6,7` cíclicamente, suma, calcula `11 - (suma % 11)` y devuelve
   `0`, `1…9` o `K` (11 → 0, 10 → K).
3. `validar_rut(rut)` exige cuerpo numérico de 1 a 8 dígitos, DV `0-9`/`K`,
   cuerpo distinto de cero y DV correcto.
4. `formatear_rut(rut)` devuelve la forma visible `12.345.678-5` (útil para
   presentación y pruebas; la API no la impone).

El RUT se **guarda en el formato visible que envía el usuario** (puntos y guion
incluidos, en mayúsculas y sin espacios exteriores), tal como decidió la 026
(D-4). La comparación de unicidad sigue usando `normalizar_rut`, de modo que
`76.543.210-3`, `76543210-3` y `765432103` siguen siendo el mismo proveedor.
`proveedores.normalizar_rut` se conserva como reexportación del helper para no
romper imports existentes.

La validación vive en el schema (`Annotated[str, AfterValidator(...)]`) y no en
el servicio: es forma pura, no referencia ni estado, y así el 422 se dispara
antes de tocar la BD. El servicio sigue normalizando para el pre-check de
unicidad.

### D-3 — Longitudes y rangos espejo del DDL

Cada `max_length` del contrato se copia del `VARCHAR(n)` real y cada `ge`/`gt`
del `CHECK` o de la FK. La tabla de referencia está en el Anexo A. La regla es:
**si el DDL lo rechaza, el DTO lo rechaza antes con 422**. No se agregan límites
que el DDL no tenga (por ejemplo, no se limita `TicketMotivo.motivo` en el
schema porque la 013 decidió validarlo en el servicio para preservar la
precedencia 404 → 409 → 422).

### D-4 — Nombres sin espacios exteriores, descripciones intactas

Los campos de nombre y razón social usan
`StringConstraints(strip_whitespace=True, min_length=1, max_length=n)`: `"   "`
se convierte en `""` y falla con 422; `"  Sede Central  "` se guarda como
`"Sede Central"`. Es lo mismo que ya hacen los servicios con `strip()`, pero
ahora ocurre antes y con un error de contrato.

Las descripciones, observaciones y motivos **no** se recortan por dentro ni se
les quita el espacio exterior de forma destructiva: solo se limita su longitud.
Un texto de solo espacios en una descripción opcional sigue siendo válido; en un
motivo obligatorio, el servicio ya lo rechaza.

### D-5 — `extra="forbid"` en las entradas, no en las salidas

Se agrega `model_config = ConfigDict(extra="forbid")` a los DTO de alta y
edición listados en §1.1. Un campo desconocido responde 422 con
`type="extra_forbidden"` y `loc` con el nombre del campo. `TicketCrear` conserva
`usuario_id` declarado e ignorado por compatibilidad (003/008); no se vuelve un
campo prohibido. Los DTO de respuesta no cambian.

**Clarificación (24/Nov/2026):** cuando el DTO de entrada es una clase base que
también hereda un DTO de respuesta (`ProductoBase` → `ProductoRespuesta`,
`UsuarioBase` → `UsuarioRespuesta`), el `extra="forbid"` se declara en la
subclase de alta (`ProductoCrear`, `UsuarioCrear`), no en la base. Pydantic v2
fusiona `model_config` en la herencia y no queremos que la prohibición de campos
extra se filtre a la serialización de respuestas.

### D-6 — `EmailStr` para el correo del administrador institucional

`InstitucionAltaControlCrear.correo_administrador` pasa de `str` a `EmailStr`.
No hay dependencia nueva: `pydantic[email]` ya está en `requirements.txt` y
`EmailStr` ya se usa en `usuario_schema` y `compra_schema`. El correo se sigue
normalizando con `security.normalizar_correo` en el servicio.

### D-7 — `tipo_movimiento` como `Literal` normalizado, 422 en vez de 400

El campo se declara como
`Annotated[Literal["ENTRADA","SALIDA"], BeforeValidator(_mayusculas)]`, de modo
que `"entrada"` y `"ENTRADA"` son válidos, `"AJUSTE"` es 422 y OpenAPI publica
el enum. El servicio conserva su rama defensiva, pero deja de ser el camino
normal para un valor inválido. Los tests que hoy esperan 400 se actualizan a
422.

### D-8 — Traducción de errores de BD como red de seguridad

Los servicios ya traducen los conflictos que conocen (409 de duplicados,
404 de referencias). La 027 agrega una red de seguridad para lo que se escape:

| Error | SQLSTATE PostgreSQL | Señal SQLite | Respuesta |
|---|---|---|---|
| Unicidad | `23505` | `UNIQUE constraint failed` | **409** «El valor ya existe o entra en conflicto con un registro existente.» |
| Clave foránea | `23503` | `FOREIGN KEY constraint failed` | **422** «La referencia indicada no existe o no pertenece al ámbito de la operación.» |
| Check | `23514` | `CHECK constraint failed` | **422** «Alguno de los valores enviados no cumple las reglas del recurso.» |
| Not null | `23502` | `NOT NULL constraint failed` | **422** «Falta un valor obligatorio.» |
| Texto demasiado largo | `22001` | `String or BLOB exceeds size limit` | **422** «Uno de los textos supera la longitud permitida.» |
| Número fuera de rango | `22003` | — | **422** «Uno de los valores numéricos está fuera de rango.» |

El manejador se registra en `main.py` para `IntegrityError` y `DataError`, añade
`X-Request-ID` y registra el error original en el log sin exponerlo. Un error
desconocido se re-lanza al manejador de 500 existente: **no se convierte un bug
en un 422**. Los mensajes concretos de los servicios (por ejemplo «El RUT del
proveedor ya está registrado») tienen prioridad porque se lanzan antes.

### D-9 — Un parser de 422 compartido, no ocho copias

Se crea `frontend/src/app/shared/utils/validacion-http.ts` con:

- `detallesDeValidacion(error): DetalleError422[]` — extrae la lista de
  `detail` si es un array; si no, devuelve `[]`.
- `mensajeDeCampo(detalles, campo): string | null` — busca el último elemento de
  `loc` igual al campo.
- `mensajeDeDetalle(detalles, indice, campo): string | null` — para
  `FormArray`, usa `loc.at(-2)` como índice y `loc.at(-1)` como campo.
- `traducirMensajeValidacion(error): string` — traduce `string_too_short`,
  `string_too_long`, `missing`, `greater_than`, `greater_than_equal`,
  `less_than`, `less_than_equal`, `literal_error`, `extra_forbidden`,
  `value_error` (usa el texto en español del backend) y los `type` de parseo
  (`int_parsing`, `decimal_parsing`, `date_parsing`) a mensajes en español.

`mensajeDeErrorHttp` se conserva para los errores que no son listas de
validación. Los componentes dejan de duplicar `DetalleError422` y
`traducirMensaje`.

### D-10 — Espejo del RUT en el frontend

`frontend/src/app/shared/utils/rut.ts` replica `normalizarRut`, `calcularDv` y
`validarRut` con la misma tabla de multiplicadores. `rutValido` es un
`ValidatorFn`: devuelve `null` para vacío (el `required` decide si es
obligatorio) y `{ rutInvalido: true }` para un valor no vacío con DV incorrecto.
Se aplica a:

- `features/control/alta-institucion.component.ts` (RUT opcional).
- `features/control/instituciones.component.ts` (RUT opcional en edición).
- `features/compras/nueva-orden/nueva-orden.component.ts` (RUT obligatorio del
  proveedor).

Los tres templates muestran «El RUT no es válido: revisa el dígito
verificador.» y el formulario no se envía si el control es inválido. El backend
sigue siendo la autoridad: un cliente que se salte la UI recibe 422.

### D-11 — La semilla se corrige, no se maquilla

Los siete RUT de la semilla cambian solo el DV:

| Registro | Antes | Después |
|---|---|---|
| Proveedor Papelera del Pacífico SpA | `76.543.210-8` | `76.543.210-3` |
| Proveedor Suministros Corporativos Andinos Ltda. | `77.654.321-K` | `77.654.321-7` |
| Proveedor Tecnología y Tóner Express S.A. | `78.765.432-1` | `78.765.432-0` |
| Institución INST-001 | `65.432.100-9` | `65.432.100-0` |
| Institución INST-002 | `65.887.230-1` | `65.887.230-3` |
| Institución INST-003 | `77.120.540-3` | `77.120.540-2` |
| Institución INST-004 | `65.998.720-K` | `65.998.720-1` |

Se conserva el cuerpo y el formato visible; solo se corrige el dígito. Los
mocks de frontend que muestran RUT (`compras.service.spec.ts`,
`lista-ordenes.component.spec.ts`, `recepcion-bodega.component.spec.ts`,
`nueva-orden.component.spec.ts`, `alta-institucion.component.spec.ts`,
`instituciones.component.spec.ts`, `control.service.spec.ts` y
`capacidades.component.spec.ts`) se alinean a un RUT válido. Los fixtures de
tests que construyen `ProveedorCrear`, `InstitucionAltaControlCrear` o pasan por
un endpoint se barren con el mismo criterio: se conserva el cuerpo y se corrige
el DV. Los documentos cerrados de la 026 no se reescriben: su ejemplo
`76.543.210-8` queda como registro histórico y la 027 documenta que no era un DV
válido.

### D-12 — Sin cambio de esquema ni de versión

La feature no toca `01_esquema.sql`, el ORM ni la semilla en su estructura. El
token sigue en **`026.0`**, con **26** tablas en `control`, **23** por tenant y
**21** entidades de dominio. No se agregan índices, checks ni columnas. El
`down -v` + `up -d` se usa para verificar la semilla corregida, no porque haya
un cambio de DDL.

## 5. Requisitos funcionales

### R-1 — Ticket con descripción acotada

`TicketCrear.descripcion` y `TicketEditar.descripcion` aceptan `null` o hasta
**500** caracteres. 501 responde **422** con `loc` terminando en `descripcion` y
`type="string_too_long"`. `asunto` se guarda sin espacios exteriores y conserva
`min_length=3`/`max_length=150`. Los ids de prioridad, estado, producto y
cantidad tienen `ge=1`/`gt=0` donde corresponde.

### R-2 — Producto alineado al DDL

`ProductoCrear` acepta `nombre` de hasta 150, `descripcion` de hasta 250,
`unidad_medida` de hasta 30 y `stock_minimo >= 0`; `categoria_id` es `>= 1`.
Un valor fuera de límite responde **422** antes de tocar la BD. El nombre se
guarda sin espacios exteriores. El DTO prohíbe campos extra.

### R-3 — Movimiento con tipo cerrado y cantidad positiva

`MovimientoCrear` acepta `tipo_movimiento` `ENTRADA`/`SALIDA` (sin distinguir
mayúsculas), `cantidad > 0`, `observacion` de hasta 250 y `stock_sede_id >= 1`.
Un tipo distinto, una cantidad no positiva o un texto demasiado largo responden
**422**. El 400 anterior por tipo inválido desaparece. El DTO prohíbe campos
extra.

### R-4 — Usuario con longitudes y referencias válidas

`UsuarioBase`/`UsuarioCrear` aceptan `nombre` y `apellido` de hasta 100,
`departamento_id >= 1` y `rol_id >= 1`; `correo` sigue siendo `EmailStr`. Los
nombres se guardan sin espacios exteriores. El DTO prohíbe campos extra.
`UsuarioEdicion` conserva sus restricciones actuales.

### R-5 — RUT de proveedor con dígito verificador

`ProveedorCrear.rut` acepta cualquier combinación de puntos, guion y espacios
alrededor de un cuerpo numérico de 1 a 8 dígitos y un DV correcto (`0-9`/`K`).
La forma visible se guarda en mayúsculas y sin espacios exteriores; la unicidad
sigue comparando la forma normalizada. Un DV inválido responde **422** con un
mensaje que menciona el dígito verificador. Un RUT válido duplicado sigue
respondiendo **409**. El DTO prohíbe campos extra y `razon_social` se guarda sin
espacios exteriores.

### R-6 — RUT de institución y correo del administrador

`InstitucionAltaControlCrear.rut` e `InstitucionEdicion.rut` aplican la misma
regla. `None` y `""` se normalizan a `None` (RUT opcional); un valor no vacío
debe ser válido. `correo_administrador` es `EmailStr`. Los nombres de la
institución y del administrador se guardan sin espacios exteriores. El alta
mantiene `extra="forbid"` y la edición lo conserva.

### R-7 — Nombres de sede, departamento y catálogo sin espacios vacíos

`SedeCrear/Edicion.nombre`, `DepartamentoCrear/Edicion.nombre_dep`,
`ProductoCrear.nombre` y `UsuarioBase.nombre/apellido` rechazan una cadena de
solo espacios con **422** y recortan los espacios exteriores de un valor válido.
Las descripciones opcionales no se recortan por dentro.

### R-8 — Campos extra rechazados

Los DTO listados en §1.1 responden **422** con `type="extra_forbidden"` cuando
reciben un campo no declarado. `TicketCrear.usuario_id` sigue declarado e
ignorado. Las respuestas y los DTO de lectura no cambian.

### R-9 — Errores de BD traducidos

`IntegrityError` y `DataError` no controlados responden **409** (unicidad) o
**422** (FK, check, not null, truncamiento, rango numérico) con `detail` en
español y `X-Request-ID`. Un error desconocido conserva el 500 existente. El log
registra el error original sin exponer detalles de la BD al cliente.

### R-10 — Parser de 422 compartido y adoptado

`validacion-http.ts` implementa las funciones de D-9 y tiene tests unitarios.
Los formularios de tickets (alta y edición), proveedor/orden de compra,
institución (alta y edición), usuarios, sedes, departamentos y factura/cancelación
usan el parser para mostrar el mensaje del campo cuando el backend responde 422.
`mensajeDeErrorHttp` sigue cubriendo 401/403/404/409/500/red.

### R-11 — RUT validado en el frontend

`rut.ts` implementa el espejo del módulo 11 y `rutValido` como `ValidatorFn`.
Los tres formularios con RUT marcan el campo y bloquean el envío ante un DV
inválido; un RUT vacío en un campo opcional es válido y se envía como `null`.
Un RUT válido no se bloquea. El backend sigue validando aunque la UI se salte.

### R-12 — Semilla y mocks coherentes

`01_esquema.sql` siembra `65.432.100-0`, `65.887.230-3`, `77.120.540-2` y
`65.998.720-1`; `02_datos_semilla.sql` siembra `76.543.210-3`, `77.654.321-7` y
`78.765.432-0`. Los mocks de frontend que muestran RUT usan un valor válido. No
queda ningún RUT inválido en la semilla ni en los fixtures que construyen
`ProveedorCrear`/`InstitucionAltaControlCrear` o hacen `POST` a los endpoints.

## 6. Criterios de aceptación

| AC | Criterio | Evidencia |
|---|---|---|
| AC-1 | `POST /tickets/` y `PUT /tickets/{id}` aceptan `descripcion` de 500 caracteres y rechazan 501 con **422** (`loc` en `descripcion`, `type="string_too_long"`), sin 500. Los dos textareas tienen `maxlength="500"` y el control `Validators.maxLength(500)`. | Cumplido: tests de schema/endpoint, specs de `tickets.component` y `ticket-detalle.component`; 4200 con ticket #9 de 500 y 422 de 501; 8080 con `maxlength="500"`. |
| AC-2 | `POST /inventario/productos` acepta los límites del DDL (150/250/30/0) y rechaza un valor por encima o `stock_minimo=-1` con **422**, sin 500. `categoria_id=0` responde 422, no 404. | Cumplido: `test_esquemas_027.py`, `test_validacion_entradas_027.py` y gated PostgreSQL 4/4. |
| AC-3 | `POST /inventario/movimientos` acepta `ENTRADA`/`entrada`, `cantidad=1`, `observacion=250`; rechaza `cantidad<=0`, `observacion=251`, `tipo="AJUSTE"` y `stock_sede_id=0` con **422**. Ya no existe el 400 por tipo inválido. | Cumplido: esquemas, integración y 4200 (movimiento `AJUSTE` 422, `entrada` 201). |
| AC-4 | `POST/PUT /usuarios/` acepta nombres de 100 y rechaza 101, ids `<1` y nombres de solo espacios con **422**. `UsuarioEdicion` conserva sus reglas. | Cumplido: `test_esquemas_027.py` y `test_validacion_entradas_027.py` (201/422 por campo). |
| AC-5 | `ProveedorCrear` acepta RUT válidos en formato con puntos, con guion, sin separadores o con `K`; rechaza DV inválido, cuerpo no numérico, cuerpo cero y longitud fuera de rango con **422**. Un duplicado válido en otra forma responde **409**. | Cumplido: 58 casos de `test_rut_027.py`, integración y 4200 (201, 422 y 409). |
| AC-6 | El alta y la edición de institución aceptan RUT válido u omitido (`None`/`""`) y rechazan RUT inválido con **422**; `correo_administrador` inválido responde **422**. | Cumplido: `test_esquemas_027.py` y `test_aprovisionamiento_010.py` (alta válida, RUT omitido y 422). |
| AC-7 | Los DTO listados en §1.1 rechazan un campo desconocido con **422** (`type="extra_forbidden"`); `TicketCrear.usuario_id` sigue aceptado e ignorado. | Cumplido: tests parametrizados por DTO; 4200 con ticket y movimiento `extra_forbidden`. |
| AC-8 | Sede, departamento, producto, usuario, proveedor e institución rechazan nombres de solo espacios con **422** y guardan `"  Nombre  "` como `"Nombre"`. | Cumplido: esquemas, integración y 4200 (producto `"   "` → 422). |
| AC-9 | `IntegrityError`/`DataError` no controlados responden **409/422** con `detail` y `X-Request-ID`; un error desconocido conserva el 500. No se filtra el mensaje de la BD. | Cumplido: 18 casos de `test_errores_bd_027.py` y gated PostgreSQL (truncamiento real y unicidad). |
| AC-10 | `validacion-http.ts` tiene tests unitarios y los formularios de tickets, compras, administración y control muestran el mensaje del campo ante un 422. | Cumplido: 11 casos del parser, `errores-http.spec.ts` y specs de las cuatro familias de formularios. |
| AC-11 | `rut.ts` tiene tests table-driven; los tres formularios con RUT bloquean un DV inválido y aceptan uno válido; el RUT opcional vacío se envía como `null`. | Cumplido: 10 casos de `rut.spec.ts`; specs y 8080 con el alta inline bloqueada por DV inválido. |
| AC-12 | `01_esquema.sql` siembra `65.432.100-0`, `65.887.230-3`, `77.120.540-2` y `65.998.720-1`; `02_datos_semilla.sql` siembra `76.543.210-3`, `77.654.321-7` y `78.765.432-0`; ningún fixture que pase por el contrato usa un DV inválido. | Cumplido: 7 casos de `test_semilla_rut_027.py`, reset y consulta directa a PostgreSQL. |
| AC-13 | No cambia el esquema: `026.0`, 26 tablas en `control`, 23 por tenant, 21 entidades, sin índices/checks/columnas nuevas. | Cumplido: gated de instalación limpia (26/23 y `026.0`) y `grep` sin cambios de DDL. |
| AC-14 | El contrato conserva **75** operaciones OpenAPI / **73** de negocio, sin rutas nuevas; los 422 se documentan y `tipo_movimiento` publica su enum. La matriz de permisos no cambia. | Cumplido: `/openapi.json` 75/73, enum `ENTRADA`/`SALIDA`, 422 documentado y matriz 73. |
| AC-15 | `pytest` SQLite, gated PostgreSQL y gated Redis quedan en verde, con los conteos registrados. | Cumplido: **1863/109**, **1969/3** y **3/3**; evidencia §1. |
| AC-16 | `ng test` queda en verde y `ng build` compila sin errores. | Cumplido: **597 SUCCESS** y build limpio (`main-NQGWSVMA.js`). |
| AC-17 | Recorrido funcional en **4200** con escritura real: ticket de 501 → 422 con mensaje de campo; ticket de 500 → 201; RUT inválido → 422; RUT válido → 201; duplicado → 409; movimiento inválido → 422; movimiento válido → 201; campo extra → 422; nombre de solo espacios → 422. | Cumplido: tabla completa en `evidencia/README.md` §5. |
| AC-18 | Humo en **8080** tras reconstruir la imagen: las vistas tocadas cargan, el flujo básico responde y la consola no muestra errores. | Cumplido: imagen reconstruida, `main-NQGWSVMA.js`, tickets y compras verificados; consola sin errores. |
| AC-19 | `deuda-tecnica.md` registra DT-13…DT-16 como absorbidos por la 027; `roadmap.md` ubica la 027 en el Sprint 7 antes de 015/016; `MEMORY.md`, `stack.md` (Nota 5) y la evidencia quedan sincronizados. | Cumplido: DT-13…DT-16 cerrados, Nota 5 ampliada, roadmap y `MEMORY.md` sincronizados; `grep` de coherencia sin rutas obsoletas. |

## 7. Riesgos y mitigación

| Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|
| Los tests y fixtures usan RUT inválidos de forma extendida (`12.345.678-9`, `98.765.432-1`, `53.000.000-3`, `54.000.000-4`, `91.000.000-1`, `96.021.010-1`…`96.021.053-1`, `13.131.313-1`…`31.313.131-1`, `52.000.000-2`…`59.000.000-9`, `76.111.222-3`, `76.543.210-K`, `99-9`) y fallan al activar el validador | **Alta** | Alto | Inventario en T1 + barrido mecánico que conserva el cuerpo y corrige el DV; los inserts directos que no pasan por el contrato se revisan uno a uno |
| `extra="forbid"` rompe un cliente o test que envía un campo hoy ignorado | Media | Medio | Lista cerrada de DTO; tests de `extra_forbidden`; `usuario_id` se conserva declarado |
| El cambio de 400 a 422 rompe tests que esperan el status anterior | Media | Medio | `grep` de `status_code == 400` en tests de movimientos + actualización explícita |
| El manejador global de BD convierte un bug en 409/422 y oculta la causa | Media | Alto | Solo se traducen SQLSTATE/señales conocidas; lo desconocido se re-lanza al 500 y se registra con traza |
| La semilla corregida rompe aserciones de la 026 o de la demo | Media | Medio | `grep` de los tres RUT; la 026 histórica no se edita; se actualizan solo datos vivos y tests |
| El validador de RUT rechaza un RUT legítimo (cuerpo de 7 u 8 dígitos, `K` minúscula, puntos) | Baja | Alto | Tabla de casos válidos/inválidos + pruebas con RUT reales; se acepta `k` y se normaliza a `K` |
| SQLite no aplica `VARCHAR(n)` y la suite no detecta el truncamiento | Alta | Medio | Tests de schema para el 422 + gated PostgreSQL que inserta el valor límite y el límite+1 |
| La adopción del parser de 422 en ocho formularios deja alguno sin mensaje por campo | Media | Medio | Util compartido + un spec por familia + recorrido 4200 de los formularios tocados |
| El `maxlength` del textarea no cubre el `PUT` de edición | Media | Bajo | Se aplica en alta y edición, y el backend valida ambos |
| El test de correlación 500 (`/_prueba-500-024`) se ve afectado por el nuevo manejador | Baja | Medio | El manejador solo captura `IntegrityError`/`DataError`; el 500 genérico sigue en `ServerErrorMiddleware` |

## 8. Plan de verificación de cierre

1. **Línea base registrada:** `pytest` SQLite, gated PostgreSQL, gated Redis,
   `ng test`, `ng build` y `/openapi.json` (75/73).
2. **Unitarios de contrato:** cada schema con valores límite, un valor por
   encima y un campo extra; `core.rut` con tabla de RUT válidos e inválidos;
   `errores_bd` con SQLSTATE de PostgreSQL y mensajes de SQLite.
3. **Integración:** endpoints de tickets, productos, movimientos, usuarios,
   proveedores, instituciones, sedes y departamentos con 201/200 y 422; los
   duplicados de RUT siguen en 409; el tipo de movimiento inválido ya no es 400.
4. **Gated PostgreSQL 16:** truncamiento real (`VARCHAR`), checks de cantidad y
   stock mínimo, y una violación de unicidad que no pase por el pre-check para
   verificar el 409 de la red de seguridad.
5. **Frontend:** `validacion-http`, `rut` y los specs de los formularios
   tocados; `ng build` limpio.
6. **Semilla:** `down -v` + `up -d`; los tres RUT de proveedor válidos y la
   guardia fail-closed de `02_` sin errores.
7. **4200:** recorrido funcional con escritura real y los casos de AC-17.
8. **8080:** `docker compose build frontend` + `up -d frontend`; humo de las
   vistas tocadas y consola sin errores.
9. **Documentación:** `deuda-tecnica.md`, `roadmap.md`, `MEMORY.md`,
   `stack.md` y `evidencia/README.md`; `grep` de coherencia de rutas y conteos.

## 9. Dependencias y supuestos

- **Depende de:** Feature 003 (tickets), 010/012 (control y administración),
  013 (edición de ticket), 014 (catálogo), 017 (usuarios e invitaciones), 020
  (proveedores y compras) y 026 (normalización y unicidad del RUT).
- **Supone que:** el RUT es chileno y se valida con módulo 11; no hay RUT
  extranjeros en el alcance.
- **Supone que:** `pydantic[email]` sigue instalado y `EmailStr` es aceptable
  para el correo del administrador; no se agrega dependencia.
- **Supone que:** los datos QA se pueden corregir y el volumen se recrea; no hay
  datos de producción que migrar.
- **Supone que:** la UI no tiene formularios de producto ni de movimiento; su
  validación se prueba por API.
- **No depende de:** Redis, Clerk ni servicios externos para la validación; las
  pruebas gated de Redis son solo no regresión.
- **Aprobación requerida:** esta `spec.md` y su `plan.md` antes de tocar
  `backend/` o `frontend/` (`AGENTS.md` §7).

## 10. Deuda absorbida

Los siguientes hallazgos se registran en `docs/spec/deuda-tecnica.md` y quedan
absorbidos por esta feature:

| ID | Hallazgo | Severidad dev | Severidad prod |
|---|---|---|---|
| **DT-13** | DTOs sin longitudes/rangos del DDL: `descripcion` de ticket, `ProductoCrear`, `MovimientoCrear`, `UsuarioBase` y nombres de solo espacios. Producen 500 por truncamiento/check en PostgreSQL. | Media | **Alta** |
| **DT-14** | RUT de proveedor e institución sin dígito verificador; la semilla y los mocks usan DV inválidos. | Media | Media |
| **DT-15** | Contrato de error inconsistente: `tipo_movimiento` inválido responde 400; el 422 por campo solo se parsea en tickets; el 500 no tiene `detail` accionable; los campos extra se ignoran. | Media | Media |
| **DT-16** | `IntegrityError`/`DataError` no traducidos: 500 en texto plano, sin mensaje que indique el campo o la regla. | Media | **Alta** |

## Anexo A — Límites objetivo por DTO

| DTO | Campo | Regla objetivo |
|---|---|---|
| `DetalleTicketCrear` | `producto_id` | `ge=1` |
| `DetalleTicketCrear` | `cantidad_solicitada` | `gt=0` |
| `TicketCrear` | `prioridad_id`, `estado_id` | `ge=1` |
| `TicketCrear` | `asunto` | `strip`, `min_length=3`, `max_length=150` |
| `TicketCrear` | `descripcion` | `max_length=500` |
| `TicketEditar` | `asunto` | `strip`, `min_length=3`, `max_length=150` |
| `TicketEditar` | `descripcion` | `max_length=500` |
| `TicketEditar` | `prioridad_id` | `ge=1` |
| `TicketActualizarEstado` | `estado_id` | `ge=1` |
| `TicketDespacho` | `usuario_id` | `ge=1` |
| `ProductoBase` | `nombre` | `strip`, `min_length=1`, `max_length=150` |
| `ProductoBase` | `descripcion` | `max_length=250` |
| `ProductoBase` | `unidad_medida` | `max_length=30` |
| `ProductoBase` | `stock_minimo` | `ge=0` |
| `ProductoBase` | `categoria_id` | `ge=1` |
| `ProductoCrear` | — | `extra="forbid"` |
| `MovimientoCrear` | `tipo_movimiento` | `Literal["ENTRADA","SALIDA"]`, normalizado a mayúsculas |
| `MovimientoCrear` | `cantidad` | `gt=0` |
| `MovimientoCrear` | `observacion` | `max_length=250` |
| `MovimientoCrear` | `stock_sede_id` | `ge=1` |
| `UsuarioBase` | `nombre`, `apellido` | `strip`, `min_length=1`, `max_length=100` |
| `UsuarioBase` | `departamento_id`, `rol_id` | `ge=1` |
| `UsuarioCrear` | — | `extra="forbid"` |
| `ProveedorCrear` | `rut` | RUT con DV, `max_length=20` |
| `ProveedorCrear` | `razon_social` | `strip`, `min_length=1`, `max_length=150` |
| `ProveedorCrear` | `nombre_fantasia`, `giro` | `max_length=100` |
| `ProveedorCrear` | `correo` | `EmailStr`, `max_length=100` |
| `ProveedorCrear` | `telefono` | `max_length=20` |
| `InstitucionAltaControlCrear` | `institucion_id` | `min_length=1`, `max_length=20` |
| `InstitucionAltaControlCrear` | `nombre` | `strip`, `min_length=1`, `max_length=150` |
| `InstitucionAltaControlCrear` | `rut` | RUT con DV opcional, `max_length=20` |
| `InstitucionAltaControlCrear` | `direccion` | `max_length=200` |
| `InstitucionAltaControlCrear` | `correo_administrador` | `EmailStr`, `max_length=150` |
| `InstitucionAltaControlCrear` | `nombre_administrador`, `apellido_administrador` | `strip`, `min_length=1`, `max_length=100` |
| `InstitucionAltaControlCrear` | `departamento_nombre_administrativo` | `strip`, `min_length=1`, `max_length=100` |
| `InstitucionEdicion` | `nombre` | `strip`, `min_length=1`, `max_length=150` |
| `InstitucionEdicion` | `rut` | RUT con DV opcional, `max_length=20` |
| `InstitucionEdicion` | `direccion` | `max_length=200` |
| `SedeCrear/Edicion` | `nombre` | `strip`, `min_length=1`, `max_length=100` |
| `SedeCrear/Edicion` | `direccion` | `max_length=200` |
| `DepartamentoCrear/Edicion` | `nombre_dep` | `strip`, `min_length=1`, `max_length=100` |
| `DepartamentoCrear/Edicion` | `descripcion` | `max_length=200` |
| `CancelacionOrdenCompra` | `motivo_cancelacion` | `strip`, `min_length=1`, `max_length=500` |
| `FacturaCompraRegistrar` | `numero_factura` | `strip`, `min_length=1`, `max_length=50` |
| `FacturaCompraRegistrar` | `observaciones` | `max_length=500` |
