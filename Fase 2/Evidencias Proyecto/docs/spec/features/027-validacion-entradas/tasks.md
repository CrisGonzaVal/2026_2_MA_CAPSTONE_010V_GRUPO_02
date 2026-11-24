# Tareas — Feature 027: Validación de entradas y errores de contrato

**Feature:** `027-validacion-entradas/`
**Spec:** [spec.md](spec.md) · **Plan:** [plan.md](plan.md)
**Regla:** cada tarea deja la suite en verde; no se relaja ninguna validación para que pase un fixture. Los RUT de prueba se corrigen conservando el cuerpo y recalculando el DV.

## T1 — Helper de RUT (backend)

**ACs:** AC-5 (parcial), AC-12 (soporte).

- [x] Crear `backend/app/core/rut.py` con `normalizar_rut`, `calcular_dv`, `validar_rut` y `formatear_rut`.
- [x] Reexportar `normalizar_rut` desde `backend/app/services/compra_service/proveedores.py` y eliminar la implementación local.
- [x] Confirmar que `_clave_rut_sql()` y el pre-check de unicidad no cambian.
- [x] Crear `backend/tests/funcional/unitarios/test_rut_027.py` con tabla de válidos, inválidos, DV, formato y normalización.
- [x] Correr `pytest tests/funcional/unitarios/test_rut_027.py` y dejar en verde.
- [x] **Cierre:** el helper no importa HTTP, Pydantic ni SQLAlchemy; los tests cubren `K` minúscula, 1–8 dígitos, cuerpo cero y 9 dígitos.

## T2 — Contrato de tickets y movimientos

**ACs:** AC-1, AC-3, AC-7 (parcial).

- [x] `ticket_schema.py`: `DetalleTicketCrear` con `producto_id ge=1`, `cantidad_solicitada gt=0` y `extra="forbid"`.
- [x] `ticket_schema.py`: `TicketCrear` con `prioridad_id`/`estado_id ge=1`, `asunto` con `strip` y 3/150, `descripcion max_length=500`, `detalles min_length=1` y `extra="forbid"`.
- [x] `ticket_schema.py`: `TicketEditar` con `asunto` con `strip` y 3/150, `descripcion max_length=500`, `prioridad_id ge=1` y `extra="forbid"`.
- [x] `ticket_schema.py`: `TicketActualizarEstado.estado_id ge=1` y `TicketDespacho.usuario_id ge=1`, ambos con `extra="forbid"`.
- [x] `inventario_schema.py`: `MovimientoCrear` con `Literal["ENTRADA","SALIDA"]` normalizado, `cantidad gt=0`, `observacion max_length=250`, `stock_sede_id ge=1` y `extra="forbid"`.
- [x] Verificar que `TicketMotivo.motivo` no cambia (sigue validándose en el servicio).
- [x] Agregar casos a `backend/tests/funcional/unitarios/test_esquemas_027.py`.
- [x] Actualizar `test_transaccion_ticket.py`: `AJUSTE_MAGICO` pasa de 400 a 422.
- [x] Correr `pytest tests/funcional/unitarios/test_esquemas_027.py tests/funcional/e2e/test_transaccion_ticket.py`.
- [x] **Cierre:** 500/501 de descripción, cantidad 0/-1, observación 251, tipo inválido, ids 0 y campos extra responden 422; `entrada`/`ENTRADA` son válidos.

## T3 — Contrato de catálogo y usuarios

**ACs:** AC-2, AC-4, AC-7 (parcial).

- [x] `producto_schema.py`: `ProductoBase` con `nombre` strip 1/150, `descripcion max_length=250`, `unidad_medida max_length=30`, `stock_minimo ge=0`, `categoria_id ge=1`.
- [x] `producto_schema.py`: `ProductoCrear` con `extra="forbid"`; **no** en `ProductoBase`.
- [x] `usuario_schema.py`: `UsuarioBase` con `nombre`/`apellido` strip 1/100, `departamento_id`/`rol_id ge=1`.
- [x] `usuario_schema.py`: `UsuarioCrear` con `extra="forbid"`; **no** en `UsuarioBase`; `UsuarioEdicion` no cambia.
- [x] Agregar casos a `test_esquemas_027.py`: límites 150/151, 250/251, 30/31, `stock_minimo=-1`, `categoria_id=0`, 100/101, ids 0, solo espacios y `extra_forbidden`.
- [x] Verificar que `ProductoRespuesta` y `UsuarioRespuesta` se construyen igual que antes.
- [x] Correr `pytest tests/funcional/unitarios/test_esquemas_027.py`.
- [x] **Cierre:** los DTO de respuesta no heredan `extra="forbid"` y los límites coinciden con el DDL.

## T4 — Contrato de compras, control y organización

**ACs:** AC-5, AC-6, AC-7, AC-8.

- [x] `compra_schema.py`: `ProveedorCrear.rut` con `StringConstraints(strip, max_length=20)` + `AfterValidator(validar_rut)`; `razon_social` strip 1/150; `extra="forbid"`.
- [x] `compra_schema.py`: `OrdenCompraCrear`, `OrdenCompraActualizar`, `FacturaCompraRegistrar`, `CancelacionOrdenCompra` y `CoberturaPreviewSolicitud` con `extra="forbid"`.
- [x] `compra_schema.py`: `numero_factura` strip 1/50, `observaciones max_length=500`, `motivo_cancelacion` strip 1/500.
- [x] `control_schema.py`: `InstitucionAltaControlCrear.rut` opcional con DV, `correo_administrador: EmailStr`, nombres con strip y `extra="forbid"` conservado.
- [x] `control_schema.py`: `InstitucionEdicion.rut` opcional con DV, `nombre` con strip y `extra="forbid"` conservado.
- [x] Normalizar `""`/solo espacios de `rut` a `None` en alta y edición de institución.
- [x] `organizacion_schema.py`: `SedeCrear/Edicion.nombre` y `DepartamentoCrear/Edicion.nombre_dep` con strip 1/100.
- [x] Agregar casos a `test_esquemas_027.py`: RUT válido en cuatro formas, DV inválido, cuerpo no numérico, cuerpo cero, 9 dígitos, 21 caracteres, RUT opcional vacío, correo inválido, nombres de solo espacios y `extra_forbidden`.
- [x] Actualizar los fixtures RUT que T4 rompe en `test_compras.py`, `test_compras_endpoints_020.py`, `test_compras_postgres_020.py`, `test_cobertura_021.py` y `test_aprovisionamiento_postgres_010.py` según el plan §8.2, incluidas las aserciones. El barrido completo se cierra en T6.
- [x] Correr `pytest tests/funcional/unitarios/test_esquemas_027.py tests/funcional/integracion/test_compras.py tests/funcional/integracion/test_compras_endpoints_020.py`.
- [x] **Cierre:** un RUT válido se guarda en su forma visible; el duplicado en otra forma sigue dando 409; el RUT de institución omitido es válido y el inválido da 422.

## T5 — Manejador de errores de BD

**ACs:** AC-9.

- [x] Crear `backend/app/core/errores_bd.py` con `clasificar_error_bd` y `manejador_error_bd`.
- [x] Mapear `23505`/`UNIQUE constraint failed` → 409; `23503`, `23514`, `23502`, `22001`, `22003` y sus señales SQLite → 422.
- [x] Leer `X-Request-ID` de `request.scope["state"]` y registrar `error_bd` sin exponer el mensaje crudo.
- [x] Relanzar los errores desconocidos al manejador de 500; no convertirlos en 409/422.
- [x] Registrar los handlers de `IntegrityError` y `DataError` en `crear_app()`.
- [x] Crear `backend/tests/funcional/sistema/test_errores_bd_027.py` con unitarios, ruta de prueba y caso de error desconocido.
- [x] Correr `pytest tests/funcional/sistema/test_errores_bd_027.py`.
- [x] **Cierre:** los errores conocidos devuelven `detail` en español y `X-Request-ID`; el 500 existente sigue intacto.

## T6 — Semilla, fixtures y mocks

**ACs:** AC-12.

- [x] Corregir los cuatro RUT de `control.institucion` en `database/01_esquema.sql` (`-0`, `-3`, `-2`, `-1`).
- [x] Corregir los tres RUT de proveedor en `database/02_datos_semilla.sql` (`-3`, `-7`, `-0`).
- [x] Aplicar el barrido de fixtures backend del plan §8.2, incluidas las aserciones que comparan el RUT.
- [x] Aplicar el barrido de mocks frontend del plan §8.3.
- [x] Crear `backend/tests/funcional/sistema/test_semilla_rut_027.py` que lea ambos SQL, valide los siete RUT y confirme que los antiguos no están.
- [x] Ejecutar `grep` de los siete RUT antiguos en `backend/`, `frontend/src/` y `database/` y confirmar que no quedan en datos vivos.
- [x] Correr `pytest tests/funcional/sistema/test_semilla_rut_027.py`.
- [x] **Cierre:** no queda ningún RUT inválido en la semilla ni en fixtures que pasen por el contrato.

## T7 — Helper de RUT (frontend)

**ACs:** AC-11 (parcial).

- [x] Crear `frontend/src/app/shared/utils/rut.ts` con `normalizarRut`, `calcularDv`, `validarRut`, `formatearRut` y `rutValido`.
- [x] `rutValido` devuelve `null` para vacío/solo espacios y `{ rutInvalido: true }` para un valor no vacío inválido.
- [x] Crear `frontend/src/app/shared/utils/rut.spec.ts` con la misma tabla de T1.
- [x] Correr `npx ng test --watch=false --browsers=ChromeHeadless --include='**/rut.spec.ts'`.
- [x] **Cierre:** el espejo acepta y rechaza exactamente los mismos casos que el backend.

## T8 — Parser de 422 compartido

**ACs:** AC-10 (parcial).

- [x] Crear `frontend/src/app/shared/utils/validacion-http.ts` con `DetalleError422`, `detallesDeValidacion`, `mensajeDeCampo`, `mensajeDeDetalle`, `traducirMensajeValidacion` y `mensajeDeValidacion`.
- [x] Implementar `campoLegible` con los nombres de campo del dominio y fallback `snake_case`.
- [x] Integrar `mensajeDeValidacion` en `errores-http.ts` para 422 con lista; conservar el texto del dominio para 422 sin lista.
- [x] Crear `validacion-http.spec.ts` con lista simple, `loc` anidado, `extra_forbidden`, `value_error` de email y límites.
- [x] Actualizar `errores-http.spec.ts`: el 422 con lista ahora espera el mensaje traducido.
- [x] Correr `npx ng test --watch=false --browsers=ChromeHeadless --include='**/validacion-http.spec.ts' --include='**/errores-http.spec.ts'`.
- [x] **Cierre:** todos los dominios que usan `mensajeDeErrorHttp` muestran el campo culpable sin cambios en sus firmas.

## T9 — Formularios de tickets

**ACs:** AC-1, AC-10.

- [x] `tickets.component.ts`: `descripcion` con `Validators.maxLength(500)`.
- [x] `tickets.component.ts`: eliminar `DetalleError422` y `traducirMensaje` locales; usar `detallesDeValidacion`, `mensajeDeCampo` y `mensajeDeDetalle`.
- [x] `tickets.component.html`: `maxlength="500"` en el textarea de descripción del alta.
- [x] `ticket-detalle.component.ts`: `formularioEdicion.descripcion` con `Validators.maxLength(500)`.
- [x] `ticket-detalle.component.html`: `maxlength="500"` en el textarea de descripción de la edición.
- [x] Agregar a `tickets.component.spec.ts` un 422 de descripción que muestre «Descripción» y no un 500.
- [x] Agregar a `ticket-detalle.component.spec.ts` un 422 de edición con mensaje de campo.
- [x] Correr los specs de tickets.
- [x] **Cierre:** alta y edición bloquean 501 en cliente y muestran el mensaje del backend si se salta la UI.

## T10 — Formularios de compras, control y administración

**ACs:** AC-10, AC-11.

- [x] `nueva-orden.component.ts`: agregar `rutValido` al control `rut`.
- [x] `alta-institucion.component.ts`: agregar `rutValido` al control `rut` y usar `mensajeDeValidacion` para 422.
- [x] `instituciones.component.ts`: agregar `rutValido` al control `rut` de edición.
- [x] Actualizar los tres templates con el mensaje «El RUT no es válido: revisa el dígito verificador.».
- [x] Agregar tests puros de 422 por campo para `mensajeDeErrorCompras`, `mensajeDeErrorAdministracion` y `mensajeDeErrorControl`.
- [x] Agregar al menos un caso 422 en los specs de `usuarios`, `sedes`, `departamentos`, `lista-ordenes` y `recepcion-bodega`.
- [x] Agregar a los specs de RUT: DV inválido bloquea, válido envía, opcional vacío envía `null`.
- [x] Correr los specs de compras, control y administración.
- [x] **Cierre:** los tres formularios con RUT bloquean un DV inválido y todos los formularios validados muestran el campo culpable.

## T11 — Integración backend y gated PostgreSQL

**ACs:** AC-5, AC-6, AC-9, AC-15 (parcial).

- [x] Crear `backend/tests/funcional/integracion/test_validacion_entradas_027.py` con los casos de tickets, productos, movimientos, usuarios, proveedores e instituciones del plan §13.1.
- [x] Verificar que `TicketCrear.usuario_id` sigue aceptado e ignorado.
- [x] Verificar que el tipo de movimiento inválido ya no responde 400.
- [x] Crear `backend/tests/funcional/sistema/test_validacion_entradas_postgres_027.py` con truncamiento real, checks, unicidad de red de seguridad, `DataError` y error desconocido.
- [x] Confirmar en el gated que la instalación limpia conserva `026.0`, 26/23 tablas y 21 entidades.
- [x] Correr `pytest tests/funcional/integracion/test_validacion_entradas_027.py`.
- [x] Correr el gated con `POSTGRES_TEST_URL`.
- [x] **Cierre:** 201/200/422/409 coherentes en SQLite y PostgreSQL; ningún 500 por entrada inválida.

## T12 — Verificación de cierre, evidencia y documentación

**ACs:** AC-13…AC-19.

- [x] Correr `pytest -q` en `backend/` y registrar el conteo.
- [x] Correr gated PostgreSQL y gated Redis; registrar conteos.
- [x] Correr `ng test` y `ng build`; registrar resultados.
- [x] Verificar `/openapi.json`: 75/73 operaciones, sin rutas nuevas, enum de `tipo_movimiento` y 422 documentados.
- [x] Verificar `026.0`, 26/23 tablas y 21 entidades con `grep` y gated de instalación limpia.
- [x] Ejecutar `down -v` + `up -d` y confirmar la guardia fail-closed y los siete RUT válidos.
- [x] Recorrido 4200 con los siete casos de AC-17 y consola sin errores.
- [x] Reconstruir la imagen del frontend y hacer humo en 8080.
- [x] Actualizar `docs/spec/stack.md` Nota 5.
- [x] Actualizar `deuda-tecnica.md`, `roadmap.md` y `MEMORY.md`.
- [x] Crear `docs/spec/features/027-validacion-entradas/evidencia/README.md` con línea base, suites, contrato, semilla, 4200 y 8080.
- [x] Marcar en `spec.md` §6 cada AC con su evidencia.
- [x] Ejecutar `grep` de coherencia de rutas y conteos en `AGENTS.md`, `MEMORY.md` y `.agents/skills/`.
- [x] **Cierre:** todas las casillas de T1–T12 marcadas; `tasks.md` sin pendientes; feature lista para el roadmap.
