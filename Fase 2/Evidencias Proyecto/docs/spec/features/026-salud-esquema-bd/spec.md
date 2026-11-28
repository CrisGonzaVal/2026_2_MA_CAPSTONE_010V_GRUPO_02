# Feature 026: Salud del esquema de base de datos

**Estado:** Borrador para aprobación (17/Nov/2026)
**Release:** 2.0 — Sprint 7 (hardening de datos)
**Tipo:** Cambio de esquema y retiro de legado; el comportamiento funcional solo cambia en los duplicados funcionales (409) y en la desaparición del camino legado de `inventario`
**Sucede a:** Feature 025 (límite de tasa distribuido, cerrada el 15/Nov/2026)

## 1. Problema

La base de datos de Compustock funciona, pero arrastra cuatro deudas que se refuerzan entre sí. Ninguna es visible en la demo con pocos datos; todas se vuelven caras cuando el volumen crece o cuando alguien escribe sin pasar por el servicio.

### 1.1 El legado `inventario` duplica la fuente de verdad

La Feature 011 introdujo `stock_sede` como saldo operativo por `(sede, producto)` y dejó `inventario` como registro histórico departamental. Quince features después, el legado sigue vivo y contamina todo lo que toca:

1. `movimiento_inventario` conserva `inventario_id` nullable y una FK a `inventario`; `stock_sede_id` también es nullable. La regla «exactamente un destino» solo existe en el contrato del servicio, no en el DDL.
2. `inventario_service` mantiene `_historial_legados()`, un `union_all` con `_historial_nuevos()` y un camino de escritura que acepta `inventario_id`. `dashboard_service` repite la misma unión para la actividad reciente.
3. La semilla conserva **14 movimientos legados** (10 de INST-001 y 4 de INST-002) que, al no tener saldo inicial, implican aperturas negativas para los productos 5, 8, 11 y 13. Son datos QA que no cuadran con `stock_sede` y que obligan a mantener una reconciliación `(1.8.5)` solo para tapar la inconsistencia.
4. Cada nuevo desarrollador debe aprender dos modelos de stock y decidir cuál es el vigente. La respuesta —`stock_sede`— ya está tomada desde la 011, pero el esquema no la representa.

La auditoría de la base viva confirma que la consolidación es completa: `stock_sede = inventario + neto_movimientos` en las 14 filas, y los 3 movimientos coherentes (productos 5 y 9 de INST-001) ya viven en `stock_sede_id`. Retirar el legado no pierde información de negocio: pierde solo el registro departamental que la 011 sustituyó.

### 1.2 Faltan índices en los caminos de lectura reales

El DDL solo declara índices para claves primarias, claves únicas y las dos tablas auxiliares de `orden_compra_ticket`. PostgreSQL no indexa automáticamente las claves foráneas. Los caminos que la aplicación ejecuta en cada visita no tienen respaldo:

- El tablero Kanban filtra `ticket` por `(sede_id, estado_id)` y ordena por `fecha_creacion DESC`.
- «Mis pedidos» filtra `ticket` por `usuario_id` y ordena por fecha descendente.
- El detalle de ticket lee `detalle_ticket` por `ticket_id` y el historial por `ticket_id`/fecha.
- El detalle de producto lee `movimiento_inventario` por `stock_sede_id`/fecha y `stock_sede` por `producto_id`.
- El catálogo filtra `producto` por `categoria_id`; la organización filtra `usuario` por `departamento_id` y `departamento` por `sede_id`.
- Las listas de compras filtran `orden_compra` por institución o por `(sede_id, estado)` y ordenan por fecha.
- Los historiales de producto y categoría leen por su entidad y fecha descendente.

Con la semilla QA (14 productos, 14 saldos, 10 tickets) el planificador elige *seq scan* y nadie lo nota. Con miles de filas, cada una de esas lecturas se vuelve un recorrido completo.

### 1.3 El DDL no impide estados inválidos

Las restricciones actuales cubren bien cantidades positivas, precios no negativos y stock no negativo, pero dejan pasar estados que el servicio considera imposibles:

- `detalle_ticket.cantidad_entregada` puede superar `cantidad_solicitada`.
- `movimiento_inventario.tipo_movimiento` es texto libre: acepta `entrada`, `AJUSTE` o cualquier cadena.
- `historial_transicion_ticket` admite más de una fila de creación (`estado_origen_id IS NULL`) por ticket.
- `version_esquema` admite varias filas vigentes; la semilla y el arranque dependen de que exista «una sola».
- `usuario.correo` es único con comparación exacta: `Admin@X.CL` y `admin@x.cl` conviven.
- `proveedor.rut` es único con comparación exacta: `76.543.210-8`, `76543210-8` y ` 76.543.210-8 ` pueden convivir.
- `sede.nombre`, `departamento.nombre_dep` y `categoria.nombre_cat` no tienen unicidad por institución, aunque los servicios ya intentan evitar duplicados.

Los dos últimos grupos no son solo un problema de datos: obligan a que cada servicio recuerde normalizar y a que una carrera entre dos peticiones deje el duplicado igual.

### 1.4 Los metadatos del esquema están desalineados

El encabezado de `01_esquema.sql` declara 21 entidades y versión `020.1`; la realidad es 22 entidades y `021.1`. `database/README.md`, `AGENTS.md` y `docs/spec/stack.md` repiten conteos de distintas épocas. Un esquema sano también es un esquema que se puede leer: si el encabezado miente, la próxima feature parte de una foto falsa.

## 2. Objetivo

Cerrar las cuatro deudas en **una sola feature** (026), con tres ejes explícitos:

1. **Índices (punto 1 del encargo):** agregar 15 índices P0 por esquema, alineados con los caminos de lectura reales, sin tocar las FKs ni los joins del modelo vigente (la única FK que se retira es la del legado `inventario`, que desaparece con su tabla).
2. **Restricciones seguras (punto 2):** agregar checks y unicidades funcionales que el servicio ya asume, con normalización y respuesta **409** en los duplicados, sin bloquear los flujos válidos.
3. **Retiro del legado (punto 5):** eliminar `inventario`, su FK y su camino de lectura/escritura, y dejar `stock_sede` como única fuente de stock. La semilla conserva 14 saldos y **3 movimientos coherentes**; los 14 movimientos legados se descartan porque son datos QA y no cuadran.

Al cierre, el modelo canónico queda en **21 entidades de dominio** (22 − `inventario`), **26 tablas en `control`** y **23 tablas por tenant**, con token de esquema **`026.0`**. No hay migraciones: el volumen se recrea con `down -v` + `up -d`.

## 3. Alcance

### 3.1 Dentro de alcance

- `database/01_esquema.sql`: retiro de `inventario`, 15 índices P0, checks y unicidades B1/B2, conteos y versión.
- `database/02_datos_semilla.sql`: retiro de `inventario`, 3 movimientos coherentes, saldos 45/12, guardas y versión `026.0`.
- Paridad ORM obligatoria en `backend/app/models/**`: mismas tablas, índices, checks y unicidades, porque los tenants se aprovisionan con `Base.metadata.create_all`.
- Retiro del camino legado en `inventario_service`, `dashboard_service`, `schemas` y `models`.
- Normalización y 409 en `organizacion_service` (sede/departamento), `compra_service/proveedores.py` (RUT) y verificación de `usuario_service` (correo).
- Limpieza de interfaces y de la vista de dashboard en `frontend/`.
- Tests SQLite, tests gated de PostgreSQL 16, tests de frontend y evidencia de cierre.
- Actualización de `docs/spec/stack.md`, `docs/spec/roadmap.md`, `database/README.md`, `AGENTS.md` y `MEMORY.md`.

### 3.2 Fuera de alcance

- **Índices P1.** Se identificaron seis candidatos de soporte de FK (`usuario(rol_id)`, `usuario(sede_id)`, `departamento_encargado(usuario_id)`, `detalle_orden_compra(producto_id)`, `historial_transicion_ticket(usuario_id)`, `orden_compra(proveedor_id)`), pero no corresponden a un camino de lectura dominante hoy. Quedan documentados como deuda, no se crean.
- **Triggers, procedimientos almacenados y cursores.** Siguen pospuestos por decisión del proyecto; toda la lógica transaccional permanece en los servicios.
- **Caché de lecturas.** Sigue sin feature asignada; no se toca en la 026.
- **Nuevos endpoints.** Las rutas y la matriz de permisos no cambian. Los cambios de contrato se limitan a tres: desaparecen campos legados de los DTOs de movimientos y actividad, `POST /inventario/movimientos` exige `stock_sede_id` (422 sin él) y se documentan los nuevos **409** de duplicados funcionales.
- **Unicidad de nombre de producto.** Es una decisión de negocio pendiente (mismos nombres con distinta marca/presentación pueden ser válidos). No se impone en esta feature.
- **Migraciones.** No se crean scripts incrementales; el esquema se reconstruye.
- **Features 015 y 016** (informes y notificaciones), que siguen pendientes de especificación.

## 4. Decisiones de diseño

### D-1 — Una feature, tres ejes, un solo token de versión

Los puntos 1, 2 y 5 comparten el mismo artefacto —`01_esquema.sql` y su semilla— y el mismo momento de verificación —recrear el volumen—. Separarlos obligaría a tres `down -v`, tres actualizaciones de conteos y tres recorridos de cierre, con riesgo de dejar el esquema a medio camino. Se implementan juntos y se cierran juntos con el token **`026.0`**.

### D-2 — Solo índices P0, 15 por esquema, con desempate estable

Se crean exactamente los 15 índices que respaldan los caminos de lectura que la aplicación ejecuta hoy. Cada índice compuesto termina en la PK de la tabla para que el orden sea total y estable; los listados ordenados por fecha incluyen `DESC` explícito. No se agrega `prioridad_id` al índice del Kanban porque el backend no filtra por prioridad (el orden visual se resuelve en el cliente). Los P1 quedan fuera (ver §3.2).

| ID | Índice | Tabla | Columnas | Camino que sirve |
|---|---|---|---|---|
| I-01 | `stock_sede_producto_sede_idx` | `stock_sede` | `(producto_id, sede_id)` | Detalle de producto: saldo por sede |
| I-02 | `movimiento_stock_sede_fecha_idx` | `movimiento_inventario` | `(stock_sede_id, fecha_movimiento DESC, movimiento_id DESC)` | Historial de movimientos de un saldo |
| I-03 | `movimiento_fecha_idx` | `movimiento_inventario` | `(fecha_movimiento DESC, movimiento_id DESC)` | Actividad reciente global |
| I-04 | `ticket_sede_estado_fecha_idx` | `ticket` | `(sede_id, estado_id, fecha_creacion DESC, ticket_id DESC)` | Tablero Kanban por sede y estado |
| I-05 | `ticket_usuario_fecha_idx` | `ticket` | `(usuario_id, fecha_creacion DESC, ticket_id DESC)` | «Mis pedidos» del Solicitante |
| I-06 | `detalle_ticket_ticket_idx` | `detalle_ticket` | `(ticket_id, detalle_ticket_id)` | Detalle de un ticket |
| I-07 | `detalle_ticket_producto_idx` | `detalle_ticket` | `(producto_id, ticket_id)` | Demanda por producto |
| I-08 | `historial_ticket_ticket_fecha_idx` | `historial_transicion_ticket` | `(ticket_id, fecha_transicion DESC, historial_transicion_id DESC)` | Historial de un ticket |
| I-09 | `historial_producto_producto_fecha_idx` | `historial_transicion_producto` | `(producto_id, fecha_transicion DESC, historial_producto_id DESC)` | Historial de un producto |
| I-10 | `historial_categoria_categoria_fecha_idx` | `historial_transicion_categoria` | `(categoria_id, fecha_transicion DESC, historial_categoria_id DESC)` | Historial de una categoría |
| I-11 | `usuario_departamento_idx` | `usuario` | `(departamento_id)` | Usuarios por departamento |
| I-12 | `departamento_sede_idx` | `departamento` | `(sede_id)` | Departamentos por sede |
| I-13 | `producto_categoria_idx` | `producto` | `(categoria_id)` | Catálogo por categoría |
| I-14 | `orden_compra_institucion_fecha_idx` | `orden_compra` | `(institucion_id, fecha_creacion, orden_compra_id)` | Listado institucional de OC |
| I-15 | `orden_compra_sede_estado_fecha_idx` | `orden_compra` | `(sede_id, estado, fecha_creacion, orden_compra_id)` | OC por sede y estado |

Los 15 se replican en `control` y en cada esquema tenant. En `control` su utilidad es sobre todo de paridad estructural y del catálogo global; en los tenants son los que evitan los *seq scan*.

### D-3 — Restricciones B1: solo los deltas que el servicio ya asume

La auditoría encontró que muchas restricciones candidatas **ya existen** (`producto_stock_minimo_ck`, `stock_sede_stock_ck`, `movimiento_cantidad_ck`, `detalle_cantidad_solicitada_ck`, `detalle_cantidad_entregada_ck`, `detalle_orden_compra_*_ck`, `orden_compra_*_ck`, `factura_compra_monto_ck`, `orden_compra_ticket_*_ck`). No se re-declaran. Los deltas nuevos son:

| ID | Objeto | Definición | Motivo |
|---|---|---|---|
| K-03 | `detalle_cantidad_entregada_tope_ck` | `CHECK (cantidad_entregada <= cantidad_solicitada)` | El despacho nunca entrega más de lo pedido; hoy solo lo impide el servicio |
| K-04 | `movimiento_tipo_ck` | `CHECK (tipo_movimiento IN ('ENTRADA', 'SALIDA'))` | El dominio solo tiene dos tipos; el texto libre no aporta nada |
| U-06 | `historial_transicion_ticket_creacion_uk` | `UNIQUE (ticket_id) WHERE estado_origen_id IS NULL` | Un ticket tiene exactamente una fila de creación |
| U-07 | `version_esquema_unica_idx` | `UNIQUE ((true))` | Una sola versión vigente por esquema |
| N-01 | `movimiento_inventario.stock_sede_id` | `NOT NULL` tras retirar `inventario_id` | Todo movimiento nuevo apunta a un saldo por sede |

U-07 es **solo PostgreSQL**: SQLite no soporta el índice sobre una expresión constante booleana y la suite inserta varias filas de versión en pruebas de enrutamiento. Se crea con un helper dialectal después de `create_all`, nunca desde el ORM. La prueba gated verifica que un segundo `INSERT` falle en PostgreSQL.

### D-4 — Restricciones B2: unicidad funcional con normalización y 409

La unicidad se resuelve en dos capas, porque ninguna sola es suficiente:

1. **Servicio:** normaliza antes de comparar y de escribir, y devuelve **409** con un mensaje concreto. Esto da el error de negocio correcto y evita que la carrera llegue a la base en el caso normal.
2. **Base:** índice único sobre la expresión normalizada. Es la defensa contra carreras y contra escrituras que no pasan por el servicio.

| ID | Objeto | Expresión | Alcance |
|---|---|---|---|
| U-01 | `usuario_correo_normalizado_uk` | `lower(trim(correo))` | Por esquema |
| U-02 | `proveedor_rut_normalizado_uk` | `upper(replace(replace(replace(trim(rut), '.', ''), '-', ''), ' ', ''))` | Por esquema (global en `control`, réplica en tenant) |
| U-03 | `sede_nombre_institucion_uk` | `(institucion_id, lower(trim(nombre)))` | Por institución |
| U-04 | `departamento_nombre_institucion_uk` | `(institucion_id, lower(trim(nombre_dep)))` | Por institución |
| U-05 | `categoria_nombre_institucion_uk` | `(institucion_id, lower(trim(nombre_cat)))` | Por institución |
| K-01 | `usuario_correo_canonico_ck` | `correo = lower(trim(correo)) AND length(correo) > 0` | Por esquema |
| K-02 | `proveedor_rut_canonico_ck` | `rut = upper(trim(rut)) AND length(rut) > 0` | Por esquema |

Decisiones de detalle:

- **El correo se guarda normalizado** (minúsculas, sin espacios exteriores). `security.normalizar_correo` ya lo hace; el check solo cierra la puerta a escrituras directas.
- **El RUT conserva el formato visible** (puntos y guion) para no cambiar lo que ve el usuario; la unicidad compara la forma canónica sin puntos, guion ni espacios, y el check exige mayúsculas y sin espacios exteriores. Así `76.543.210-8`, `76543210-8` y ` 76.543.210-8 ` no pueden coexistir, pero el proveedor sigue mostrando `76.543.210-8`.
- **Los nombres se guardan con su capitalización** (no se fuerzan minúsculas para no destruir «Sede Central»); la unicidad compara `lower(trim(...))`. El servicio guarda `strip()` y compara normalizado.
- **`categoria` no tiene alta por API**, así que U-05 protege la semilla y futuras altas, sin un camino 409 que probar hoy.
- **`producto` queda fuera** por decisión de negocio (ver §3.2).
- **La unicidad de nombre es por institución**, no global: dos instituciones pueden tener «Sede Central» y «Papelería».

### D-5 — Retiro del legado con 5C-lite: `inventario` fuera y 3 movimientos coherentes

Se elimina `inventario` de `control` y de la plantilla tenant, junto con `movimiento_inventario.inventario_id` y su FK. `stock_sede_id` pasa a `NOT NULL`.

La semilla resultante:

- Conserva **14 filas de `stock_sede`** (las mismas sedes/productos).
- Ajusta los saldos de los dos productos con movimientos coherentes: producto 5 de la sede 2 pasa de **35 a 45** (ENTRADA 10) y producto 9 de la sede 2 pasa de **6 a 12** (ENTRADA 21 − SALIDA 15).
- Siembra **3 movimientos** enlazados por `stock_sede_id`:
  1. `ENTRADA 10` sobre el saldo 8 (producto 5).
  2. `ENTRADA 21` sobre el saldo 9 (producto 9).
  3. `SALIDA 15` sobre el saldo 9 (producto 9).
- Descarta los **14 movimientos legados** que implicaban aperturas negativas y la reconciliación `(1.8.5)`. No se pierde información de negocio: el saldo vigente ya estaba consolidado en `stock_sede` y los 3 movimientos coherentes son los únicos que describen entradas/salidas reales sobre ese saldo.

La decisión es «lite» porque no se inventan movimientos de apertura para los 12 saldos restantes ni se reconstruye la historia departamental. La semilla QA puede permitirse un historial parcial; lo que no puede permitirse es un historial que contradiga el saldo.

### D-6 — Conteos y versión: 21 entidades, 26/23 tablas, `026.0`

| Artefacto | Antes | Después |
|---|---|---|
| Entidades de dominio | 22 (incluye `inventario`) | **21** (sin `inventario`, con `orden_compra_ticket`) |
| Tablas en `control` | 27 | **26** |
| Tablas por tenant | 24 | **23** |
| Token de esquema | `021.1` | **`026.0`** |

`departamento_encargado` era la única tabla auxiliar y no se contaba como entidad (retirada por la enmienda 012 del 27/Nov/2026; ver la nota de vigencia al final). `funcion_institucion`, `mapa_usuario_esquema`, `registro_motivo_constancia` y `version_esquema` siguen siendo estructuras de control/versionado, no entidades de dominio.

### D-7 — Paridad ORM obligatoria y helper dialectal para PostgreSQL

Los tenants se aprovisionan en caliente con `Base.metadata.create_all` (`control_service._provisionar_tenant_postgres`). Si un índice o check vive solo en `01_esquema.sql`, un tenant creado por la aplicación nace sin él. Por eso **todo** lo que se agrega al DDL se agrega también al ORM, con estas excepciones controladas:

- U-07 (`version_esquema_unica_idx`) no se declara en el ORM porque SQLite no lo soporta y la suite lo necesita ausente. Se crea con un helper que solo actúa si `motor.dialect.name == "postgresql"`, después de `create_all`, tanto en el aprovisionamiento tenant como en el bootstrap de control cuando corresponda.
- U-06 (único parcial) se declara con `postgresql_where` y `sqlite_where`, de modo que ambas bases lo aplican.

Los índices de expresión (U-01…U-05) usan funciones portables (`lower`, `trim`, `upper`, `replace`), disponibles en PostgreSQL 16 y SQLite. No se usa `btrim` ni `regexp_replace` para no romper la suite.

### D-8 — Restricciones excluidas a propósito

| Candidata | Por qué no |
|---|---|
| `detalle_ticket UNIQUE (ticket_id, producto_id)` | Un test de la 003 crea 5 líneas repetidas y espera 201 con 5 detalles; el contrato permite repetir producto en un pedido |
| `estado_ticket UNIQUE (nombre)` | El servicio resuelve duplicados por `estado_id` menor y varias fixtures crean catálogos con nombres repetidos; imponerlo rompería la compatibilidad |
| `producto UNIQUE (institucion_id, nombre)` | Decisión de negocio pendiente; los homónimos entre instituciones son deliberados y la misma institución puede tener presentaciones distintas |
| `usuario UNIQUE (nombre, apellido)` | No es una clave de negocio y bloquearía homónimos legítimos |

### D-9 — Sin migraciones: reconstrucción del volumen

El proyecto no tiene cadena incremental. `database/` solo contiene `01_esquema.sql` y `02_datos_semilla.sql`; el cierre exige `docker compose down -v` + `up -d` y verificar el arranque limpio. No se crean scripts `03_`, `ALTER` sueltos ni carpetas de migración.

### D-10 — Estrategia de pruebas: SQLite, PostgreSQL real y frontend

- **SQLite (suite principal):** valida el ORM, la paridad de índices/checks, los 409 de servicio y la ausencia de referencias legadas. No valida esquemas, `schema_translate_map` ni el índice `((true))`.
- **PostgreSQL 16 gated (`POSTGRES_TEST_URL`):** valida la instalación limpia, los conteos 26/23, los 15 índices en `control` y en los 4 tenants, el rechazo real de los checks, la unicidad parcial, la versión única y la ausencia de `inventario`.
- **Redis gated (`REDIS_TEST_URL`):** se corre como no regresión; la 026 no toca el limitador.
- **Frontend (`ng test`):** valida que las interfaces y la vista de dashboard no referencian campos legados.
- **Dos puertos:** 4200 para el recorrido funcional con escritura real; 8080 para el humo tras reconstruir la imagen.

### D-11 — Documentación y evidencia como parte del cierre

El encabezado del DDL, `database/README.md`, `AGENTS.md` §4/§7, `docs/spec/stack.md` y `MEMORY.md` deben quedar sincronizados con 21/26/23 y `026.0`. El cierre incluye un `grep` de coherencia sobre `AGENTS.md`, `MEMORY.md` y `.agents/skills/` para que ninguna ruta ni conteo quede obsoleto. La evidencia vive en `docs/spec/features/026-salud-esquema-bd/evidencia/README.md`.

## 5. Requisitos funcionales

### R-1 — Esquema limpio sin `inventario`

`01_esquema.sql` no debe contener la tabla `control.inventario`, la plantilla tenant `inventario`, la columna `movimiento_inventario.inventario_id` ni la FK `movimiento_inventario_fk`. El guard tenant debe exigir **23** tablas y el encabezado debe declarar **21 entidades / 26 control / 23 tenant / `026.0`**.

### R-2 — Movimientos anclados a `stock_sede`

`movimiento_inventario.stock_sede_id` es `NOT NULL` y su FK a `stock_sede` se conserva. El ORM usa `nullable=False` y ya no declara la relación `inventario`. La API de creación de movimientos exige `stock_sede_id`; `inventario_id` desaparece del DTO.

### R-3 — Semilla coherente

`02_datos_semilla.sql` siembra 14 filas de `stock_sede` (10 en INST-001 y 4 en INST-002), 3 movimientos (todos en INST-001, los de INST-002 caen con el legado) y ningún `inventario`. Los saldos del producto 5 (sede 2) y del producto 9 (sede 2) son 45 y 12. Las guardas fail-closed son de dos niveles: por tenant, los conteos deben igualar a `control` filtrado por institución y ningún movimiento puede quedar sin `stock_sede_id`; globales, antes de vaciar `control`, deben cuadrar 14 saldos (10/4), 3 movimientos, 45/12 y las aperturas 35/6. La versión `026.0` se verifica en control y en cada tenant.

### R-4 — 15 índices P0 en control y en cada tenant

Los índices I-01…I-15 existen con el nombre, la tabla, las columnas y el orden `DESC` documentados en D-2, tanto en `control` como en cada esquema `tenant_*`. El ORM los declara para que un tenant aprovisionado en caliente nazca con ellos.

### R-5 — Checks y unicidades B1

K-03, K-04, U-06 y N-01 existen en el DDL y en el ORM. U-07 existe en PostgreSQL por helper dialectal; en SQLite no se crea y la suite puede insertar varias filas de versión.

### R-6 — Unicidades funcionales B2 y 409

U-01…U-05 y K-01/K-02 existen en el DDL y en el ORM. Los servicios de alta/edición de sede, departamento y proveedor normalizan antes de comparar, devuelven 409 ante un duplicado funcional y traducen la `IntegrityError` de una carrera al mismo 409. La creación de usuario conserva su 409 actual y se beneficia de U-01.

### R-7 — Sin caminos legados

`inventario_service` ya no contiene `_historial_legados`, la unión con `_historial_nuevos` ni la rama de escritura por `inventario_id`. `dashboard_service` ya no consulta `Inventario` ni proyecta los campos departamentales legados. `models/__init__.py` ya no exporta `Inventario`.

### R-8 — Contrato y permisos intactos

La matriz de permisos y el número de operaciones no cambian (75 OpenAPI / 73 de negocio). Los DTOs de movimientos y actividad pierden campos legados; la API de creación de movimientos documenta `stock_sede_id` obligatorio. Los nuevos 409 se documentan en OpenAPI.

### R-9 — Frontend sin campos legados

Las interfaces `MovimientoCrear` y `MovimientoDashboard` ya no exponen `inventario_id`, `departamento_id`, `departamento_nombre` ni `ubicacion`. La vista de dashboard muestra `sede_nombre ?? 'Sin sede'` y no depende del bloque legado. Los mocks de los specs se actualizan.

### R-10 — Documentación y evidencia sincronizadas

`docs/spec/stack.md`, `docs/spec/roadmap.md`, `database/README.md`, `AGENTS.md` y `MEMORY.md` reflejan 21/26/23 y `026.0`. La evidencia registra comandos, resultados y capturas de los dos puertos.

## 6. Criterios de aceptación

| AC | Criterio | Evidencia |
|---|---|---|
| AC-1 ✅ | `01_esquema.sql` crea **26** tablas en `control` y **23** por tenant; el guard falla si el conteo no es 23; no existe `inventario` ni en control ni en la plantilla. | `test_salud_esquema_postgres_026.py` (14 passed) + `test_instalacion_limpia_postgres.py`: 26 en `control`, 23 × 4 tenants, **0** `inventario` en `information_schema`. |
| AC-2 ✅ | `02_datos_semilla.sql` deja **14** `stock_sede` (10 en INST-001 + 4 en INST-002), **3** `movimiento_inventario` con `stock_sede_id` no nulo (todos en INST-001), **0** `inventario`; producto 5 = 45 y producto 9 = 12. Las guardas por tenant comparan contra `control` por institución; las globales verifican 14/3 y las aperturas 35/6. | Semilla `down -v` + `up -d` sin errores + gated 026: 10/4 saldos, 3/0 movimientos, 0 sin `stock_sede_id`, 45 y 12. Guardas fail-closed de `02_`. |
| AC-3 ✅ | La versión objetivo es **`026.0`** en `config.py`, encabezado del DDL, constante de la semilla y filas de `version_esquema` de control y los 4 tenants. | `grep` de `026.0` en `config.py`, ambos scripts + gated 026: `version_esquema` = `026.0` en `control` y en los 4 tenants. |
| AC-4 ✅ | `movimiento_inventario` no tiene `inventario_id` ni su FK; `stock_sede_id` es `NOT NULL` en DDL y ORM. | Gated 026 (N-01: columna ausente y `is_nullable = NO`) + `test_salud_esquema_026.py` sobre `Base.metadata`. |
| AC-5 ✅ | Los 15 índices I-01…I-15 existen con sus columnas y orden en `control` y en los 4 tenants. | Gated 026: los **17 P0** (15 nuevos + 2 heredados de la 021) con tabla y columnas exactas en los 5 esquemas; `pg_indexes`: 67 en `control` y 63 por tenant. |
| AC-6 ✅ | El ORM `create_all` crea los 15 índices y las restricciones B1/B2 en SQLite (salvo U-07), y los tests de metadatos lo verifican. | `test_salud_esquema_026.py` (**3 passed**): metadatos, índices, U-01…U-06 y K-01…K-04; U-07 ausente en SQLite. |
| AC-7 ✅ | En PostgreSQL, `version_esquema` rechaza una segunda fila; en SQLite la suite sigue pudiendo insertar varias. | Gated 026: segunda fila rechazada por `version_esquema_unica_idx`; la suite SQLite (1659) inserta varias sin error. |
| AC-8 ✅ | `detalle_cantidad_entregada_tope_ck` rechaza `cantidad_entregada > cantidad_solicitada`; los datos y flujos válidos siguen pasando. | Test negativo de constraint en gated 026 + suite completa de despacho/tickets en verde. |
| AC-9 ✅ | `movimiento_tipo_ck` acepta solo `ENTRADA` y `SALIDA`; un valor distinto falla. | Test negativo de constraint en gated 026 (`AJUSTE` rechazado) + movimientos válidos de la semilla. |
| AC-10 ✅ | `historial_transicion_ticket_creacion_uk` permite una sola fila de creación por ticket y muchas transiciones con origen no nulo. | Gated 026: segunda creación rechazada y varias transiciones aceptadas; `test_salud_esquema_026.py` en SQLite. |
| AC-11 ✅ | El correo se guarda normalizado; `Admin@X.CL` y `admin@x.cl` no coexisten y el alta duplicada responde **409**. | Tests de `usuario_service` + gated 026 (U-01) + recorrido 4200: `  CAMILA.FERNANDEZ@LOSALPES.CL  ` → **409**. |
| AC-12 ✅ | El RUT compara forma canónica; `76.543.210-8`, `76543210-8` y ` 76.543.210-8 ` no coexisten y el alta duplicada responde **409**. | Tests de proveedores + gated 026 (U-02/K-02) + recorrido 4200: ` 76543210-8 ` contra `76.543.210-8` → **409**. |
| AC-13 ✅ | Sede y departamento tienen nombre único por institución sin distinguir mayúsculas/espacios; alta o edición duplicada responde **409**. Categoría tiene el índice U-05. | Tests de organización + gated 026 (U-03/U-04/U-05) + 4200: alta duplicada y **edición** duplicada de sede y departamento → **409**. |
| AC-14 ✅ | No se eliminan FKs ni joins del modelo vigente: la única FK retirada es `movimiento_inventario_fk`, que muere con la tabla `inventario`. No se crean tablas ni columnas; el modelo queda en 21 entidades de dominio. | Diff de `01_esquema.sql` + `grep` de referencias: única FK retirada la de `inventario`; 21 entidades en `AGENTS.md` §7 y `stack.md`. |
| AC-15 ✅ | La matriz de permisos y el contrato conservan 75 OpenAPI / 73 operaciones; los nuevos 409 están documentados y los campos legados ya no aparecen. | `/openapi.json`: **62 rutas / 75 operaciones**, **37** con 409; `MATRIZ_PERMISOS` = 73 sin diff; `permisos.py` sin diff. |
| AC-16 ✅ | `pytest` SQLite, gated PostgreSQL y gated Redis quedan en verde con los conteos registrados. | SQLite **1659 passed / 105 skipped**; gated PG **1761 passed / 3 skipped**; gated Redis **1662 passed / 102 skipped**; 0 failed. |
| AC-17 ✅ | `ng test` queda en verde y `ng build` compila sin errores ni campos legados. | `ng test` **549 SUCCESS**; `ng build` limpio; bundle con **0** `inventario_id` y **0** `ubicacion` (los `departamento_nombre` restantes son de tickets, no de la actividad del dashboard). |
| AC-18 ✅ | Recorrido funcional en **4200** con escritura real (alta de proveedor, movimiento, edición de sede/departamento) y humo en **8080** tras reconstruir la imagen. | `evidencia/README.md` §7 y §8: 4 altas duplicadas → 409, edición duplicada → 409, movimiento por `stock_sede_id` → **201** (45→52), campo legado → **422**, 8 rutas directas en 8080 → 200. |
| AC-19 ✅ | `AGENTS.md`, `MEMORY.md`, `docs/spec/stack.md`, `docs/spec/roadmap.md` y `database/README.md` no contienen conteos ni tokens obsoletos (`27/24`, `021.1`, 22 entidades). | `grep` final: las únicas coincidencias son **registros históricos fechados** de las filas 020/021/024/025 de `roadmap.md` y de sus propias secciones en `stack.md`; las notas de vigencia dicen 26/23, `026.0` y 21 entidades. Se corrigió la enmienda 026 que decía 24/22. |
| AC-20 ✅ | `control_canonico.CAPACIDADES` conserva `"inventario"` como **capacidad funcional**; no se confunde con la tabla retirada. | `control_canonico.py` conserva `"inventario"` en `CAPACIDADES`; `permisos.py` y la matriz sin diff. |

## 7. Riesgos y mitigación

| Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|
| Un índice o check queda solo en el DDL y no en el ORM; el tenant aprovisionado en caliente nace incompleto | Media | Alto | Tarea T4 obligatoria + test de metadatos que compara DDL esperado contra `Base.metadata` |
| El retiro de `inventario` rompe un servicio, test o relación no inventariado | Media | Alto | `grep` exhaustivo en T1 + suite completa + gated PostgreSQL antes de cerrar |
| Las unicidades B2 chocan con datos QA existentes | Baja | Medio | Auditoría previa: 0 violaciones en control y 4 tenants; el volumen se reconstruye |
| U-07 rompe la suite SQLite | Alta si se declara en el ORM | Medio | Helper dialectal PG-only + test que confirma que SQLite no lo tiene |
| Los índices de expresión no son portables | Baja | Medio | Solo `lower`, `trim`, `upper`, `replace`; test de `create_all` en SQLite |
| `stock_sede_id NOT NULL` rompe fixtures que crean movimientos legados | Alta | Medio | T8 actualiza `conftest` y todos los fixtures; el gated valida la columna |
| Una carrera de alta devuelve 500 en vez de 409 | Media | Medio | Pre-check + `except IntegrityError` en sede, departamento y proveedor; tests de duplicado |
| El índice del Kanban no se usa por el orden exacto | Baja | Bajo | Columnas y `DESC` alineados con la consulta; se valida la definición, no el plan con datos QA |
| La documentación queda con conteos de la 021 | Media | Bajo | `grep` de cierre AC-19 y tarea T13 |
| La remoción cambia el contrato de `POST /inventario/movimientos` | Segura | Bajo | Es un camino legado sin uso en el frontend; se documenta en OpenAPI y se prueba el 422 sin `stock_sede_id` |

## 8. Plan de verificación de cierre

1. **Línea base registrada:** `pytest` SQLite (1660/88), gated PostgreSQL (73), gated Redis (3), `ng test` (549) y OpenAPI (75/73).
2. **Instalación limpia:** `docker compose down -v` + `up -d`; los scripts `01_` y `02_` terminan sin error con `ON_ERROR_STOP=1`.
3. **Conteos y versión:** 26 tablas en `control`, 23 en cada uno de los 4 tenants, 21 entidades, `026.0` en control y tenants, 0 `inventario`.
4. **Índices:** 15 nombres por esquema en `pg_indexes`, con columnas y orden correctos.
5. **Restricciones:** pruebas negativas de K-03, K-04, U-06, U-07, K-01, K-02 y U-01…U-05 contra PostgreSQL real; los datos válidos siguen pasando.
6. **Semilla:** 14 saldos, 3 movimientos, 45/12, 0 movimientos sin `stock_sede_id`.
7. **Suites:** SQLite, gated PostgreSQL, gated Redis y frontend en verde. OpenAPI en 75/73.
8. **4200:** recorrido funcional con los cuatro roles y escritura real; alta de proveedor con RUT en dos formatos (409 en el segundo), edición de sede/departamento duplicada (409), alta de movimiento por `stock_sede_id`, dashboard sin campos legados.
9. **8080:** `docker compose build frontend` + `up -d frontend`; humo de las vistas tocadas y consola sin errores.
10. **Documentación:** `grep` de coherencia y evidencia en `evidencia/README.md`.

## 9. Dependencias y supuestos

- **Depende de:** Feature 011 (`stock_sede` y la consolidación), Feature 021 (`orden_compra_ticket` y el esquema 27/24), Feature 025 (suite base y Redis gated).
- **Supone que:** los datos QA pueden descartarse; no hay datos de producción que migrar; el volumen se recrea.
- **Supone que:** los 3 movimientos coherentes son los únicos con saldo verificable; los 14 legados no aportan información que el negocio necesite conservar.
- **Supone que:** el frontend no consume `inventario_id` ni los campos departamentales de la actividad (verificado por `grep`); solo los specs de dashboard los usan como mocks.
- **No depende de:** Redis, Clerk ni servicios externos. Las pruebas gated de Redis son solo no regresión.
- **Aprobación requerida:** `docs/spec/stack.md` debe recibir la sección de la Feature 026 antes de tocar modelos, DDL o semilla (`AGENTS.md` §7).

## 10. Nota de vigencia (27/Nov/2026): retiro de `departamento_encargado`

La **enmienda funcional de la Feature 012** (`docs/spec/features/012-gestion-administrativa/spec.md`,
«Segundo bloque de la enmienda (27/Nov/2026): eliminación del concepto de encargado de
departamento») **implementada y cerrada el 27/Nov/2026** retiró `control.departamento_encargado`
y su copia tenant, sus 5 filas de semilla, su modelo/esquemas/servicios/rutas y su vista. El
estado vigente es **25 tablas en `control`**, **22 por tenant**, **21 entidades de dominio** y
token **`026.1`**; `departamento_encargado` ya no existe. Las menciones de esta spec a 26/23,
`026.0` y a `departamento_encargado` como única tabla auxiliar son **históricas de su cierre**
y quedan superadas por esta nota. La 026 no se reescribe.
