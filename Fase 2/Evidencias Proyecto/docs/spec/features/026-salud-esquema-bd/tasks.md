# Tareas — Feature 026: Salud del esquema de base de datos

**Feature:** `026-salud-esquema-bd/`
**Spec:** [spec.md](spec.md) · **Plan:** [plan.md](plan.md)
**Regla:** cada tarea deja la suite en verde; no se relaja ninguna constraint para que pase un fixture. El esquema se reconstruye, no se migra.

## T1 — Línea base e inventario de referencias

**ACs:** AC-16 (línea base), AC-14 (inventario de referencias).

- [x] Correr `pytest -q` en `backend/` y registrar la línea base SQLite.
- [x] Correr gated PostgreSQL con `POSTGRES_TEST_URL` y registrar el conteo.
- [x] Correr gated Redis con `REDIS_TEST_URL` y registrar el conteo.
- [x] Correr `ng test` con `CHROME_BIN` y registrar los SUCCESS.
- [x] Ejecutar `rg -n "\binventario\b|Inventario|inventario_id" backend frontend database docs/spec` y clasificar cada coincidencia (retirar / conservar / actualizar).
- [x] Guardar el inventario en `evidencia/README.md`.

## T2 — DDL: retiro de `inventario`, índices y restricciones

**ACs:** AC-1, AC-3, AC-4, AC-5, AC-8, AC-9, AC-10, AC-11, AC-12, AC-13, AC-14.

- [x] Actualizar el encabezado de `database/01_esquema.sql`: 26 control, 23 tenant, 21 entidades, `026.0`.
- [x] Eliminar `CREATE TABLE control.inventario` y la sección `7b` pasa a `7. STOCK_SEDE`.
- [x] En `control.movimiento_inventario`: quitar `inventario_id` y su FK; `stock_sede_id NOT NULL`; agregar `movimiento_tipo_ck`.
- [x] En `control.detalle_ticket`: agregar `detalle_cantidad_entregada_tope_ck`.
- [x] En `control.usuario`: agregar `usuario_correo_canonico_ck`.
- [x] En `control.proveedor`: agregar `proveedor_rut_canonico_ck`.
- [x] Crear `version_esquema_unica_idx` en `control.version_esquema`.
- [x] Agregar los 15 índices I-01…I-15 de `control` después del `ALTER TABLE` de historial.
- [x] Agregar U-01…U-05 y U-06 de `control`.
- [x] En la plantilla tenant: eliminar `inventario`; actualizar `movimiento_inventario`; agregar los checks de detalle, usuario y proveedor.
- [x] En la plantilla tenant: agregar los 15 índices, U-01…U-06 y U-07.
- [x] Cambiar el guard tenant de 24 a **23** y el `RAISE NOTICE`.
- [x] Revisar que el orden de creación de índices sea válido (`orden_compra` e historial existen antes).

## T3 — Semilla: 14 saldos, 3 movimientos, `026.0`

**ACs:** AC-2, AC-3, AC-11, AC-12, AC-13.

- [x] Actualizar el encabezado y `v_version_objetivo := '026.0'`.
- [x] Eliminar el bloque `7. INVENTARIO` con sus 14 inserts.
- [x] Eliminar `'inventario'` de los dos arreglos de guardia.
- [x] Eliminar el `setval` de `inventario`.
- [x] Eliminar `'inventario:inventario_id'` del mapa de reparto.
- [x] Eliminar `DELETE FROM control.inventario`.
- [x] Quitar `'inventario'` del copy loop de catálogo/stock.
- [x] Ajustar los saldos: producto 5 (sede 2) = **45**; producto 9 (sede 2) = **12**.
- [x] Reemplazar los 14 movimientos por los 3 movimientos coherentes (ENTRADA 10; ENTRADA 21; SALIDA 15).
- [x] Reescribir el reparto de movimientos con `JOIN control.stock_sede` por `stock_sede_id`.
- [x] Reemplazar la reconciliación `(1.8.5)` por guardas de dos niveles: por tenant (conteos contra `control` filtrado por institución, 0 movimientos sin `stock_sede_id`, ausencia de la tabla `inventario`) y globales tras el bucle (14 saldos con reparto 10/4, 3 movimientos, 45/12 y aperturas 35/6).
- [x] Verificar que la semilla sigue en `BEGIN/COMMIT` y con guardia fail-closed.

## T4 — Paridad ORM y helper dialectal

**ACs:** AC-4, AC-5, AC-6, AC-7, AC-8, AC-9, AC-10, AC-11, AC-12, AC-13.

- [x] `models/inventario.py`: eliminar `Inventario`; `MovimientoInventario.stock_sede_id` obligatorio; quitar `inventario_id` y su relación; agregar `movimiento_tipo_ck`.
- [x] Agregar los índices I-02 e I-03 al ORM.
- [x] `models/institucion.py`: eliminar `Departamento.inventarios`; agregar I-12 y U-04.
- [x] `models/producto.py`: eliminar `Producto.inventarios`; agregar I-09, I-10, I-13 y U-05.
- [x] `models/sede.py`: agregar I-01 y U-03; actualizar el docstring del legado.
- [x] `models/usuario.py`: agregar I-11, U-01 y K-01.
- [x] `models/ticket.py`: agregar I-04…I-08 y U-06 parcial.
- [x] `models/compra.py`: agregar I-14, I-15, U-02 y K-02.
- [x] `models/control_canonico.py`: agregar U-02 y K-02 a `ProveedorControl`.
- [x] `models/__init__.py`: eliminar el import/export de `Inventario`.
- [x] `control_service.py`: agregar `_crear_indice_version_unica` y llamarlo en el aprovisionamiento tenant (y en control si `create_all` aplica).
- [x] `config.py`: `VERSION_ESQUEMA_OBJETIVO = "026.0"`.
- [x] Confirmar que U-07 **no** está en el ORM.

## T5 — Retiro de caminos legados

**ACs:** AC-4, AC-7, AC-14, AC-15.

- [x] `inventario_service.py`: eliminar `_historial_legados`, el `union_all` y la rama de escritura por `inventario_id`.
- [x] `inventario_service.py`: dejar una sola proyección por `stock_sede`.
- [x] `dashboard_service.py`: eliminar la población legada y el `union_all`.
- [x] `dashboard_service.py`: eliminar los campos `departamento_id`, `departamento_nombre`, `ubicacion`.
- [x] `schemas/inventario_schema.py`: `MovimientoCrear.stock_sede_id` obligatorio; quitar campos legados de la respuesta.
- [x] `schemas/dashboard_schema.py`: quitar los campos legados de la actividad.
- [x] Revisar docstrings de endpoints de inventario y dashboard.
- [x] Ejecutar `rg -n "Inventario|inventario_id" backend/app` y confirmar que solo quedan usos legítimos (capability `"inventario"`, textos de negocio, nombres de tablas de stock).

## T6 — B2: normalización y 409

**ACs:** AC-11, AC-12, AC-13.

- [x] `organizacion_service.py`: agregar helpers de nombre normalizado y duplicado.
- [x] `crear_sede`: `strip()`, pre-check normalizado, `except IntegrityError` → 409.
- [x] `editar_sede`: pre-check excluyendo la propia sede, `strip()`, 409.
- [x] `crear_departamento`: pre-check normalizado, `strip()`, 409.
- [x] `editar_departamento`: pre-check excluyendo el propio departamento, `strip()`, 409.
- [x] `compra_service/proveedores.py`: agregar `normalizar_rut` y comparar con la expresión SQL normalizada.
- [x] `compra_service/proveedores.py`: guardar `rut.strip().upper()` y conservar el 409.
- [x] `usuario_service.py`: confirmar normalización y 409 existentes; no cambiar el contrato.
- [x] `control_service.py`: revisar `_crear_sede_inicial` y `_crear_administrador` para que respeten las nuevas unicidades.

## T7 — Limpieza del frontend

**ACs:** AC-15, AC-17.

- [x] `shared/interfaces/index.ts`: `MovimientoCrear` usa `stock_sede_id`; elimina `inventario_id`.
- [x] `shared/interfaces/index.ts`: `MovimientoDashboard` elimina `departamento_id`, `departamento_nombre`, `ubicacion`.
- [x] Actualizar los comentarios de la actividad reciente.
- [x] `dashboard.component.html`: `sede_nombre ?? 'Sin sede'`.
- [x] `dashboard.service.spec.ts`: limpiar los mocks legados.
- [x] `dashboard.component.spec.ts`: ajustar el mock de actividad y las aserciones.
- [x] `rg -n "inventario_id|departamento_nombre|ubicacion" frontend/src/app` y confirmar que no quedan usos en movimientos.

## T8 — Tests SQLite, unit y API

**ACs:** AC-4, AC-6, AC-7, AC-8, AC-9, AC-10, AC-11, AC-12, AC-13, AC-14, AC-15.

- [x] `conftest.py`: reemplazar `Inventario` por `StockSede`; todos los movimientos con `stock_sede_id`.
- [x] Actualizar `test_dashboard_service.py`, `test_dashboard_analitico.py`, `test_dashboard_sede_011.py`, `test_historial_movimientos.py`.
- [x] Actualizar `test_modelo_sede_011.py`, `test_modelo_particionamiento.py`, `test_esquema_postgres.py`.
- [x] Actualizar `test_ciclo_vida_catalogo_014.py`, `test_ambito_institucional_008.py`, `api/test_ambito_institucional.py`.
- [x] Actualizar `test_detalle_producto_019.py`, `test_lectura_global_tickets_011.py` y los fixtures de tickets que usen `Inventario`.
- [x] Actualizar `test_integracion_multitenant_010.py` y cualquier `VersionEsquema` que dependa de los conteos.
- [x] Crear `tests/funcional/sistema/test_salud_esquema_026.py` con los cinco bloques del plan (§10.3).
- [x] Verificar que los tests de metadatos cubren los 15 índices y las 6 constraints nuevas.
- [x] Confirmar que ningún test relaja una constraint para pasar.

## T9 — Tests gated PostgreSQL 16

**ACs:** AC-1, AC-2, AC-3, AC-5, AC-7, AC-8, AC-9, AC-10, AC-11, AC-12, AC-13, AC-16.

- [x] Actualizar `test_instalacion_limpia_postgres.py` (26/23, `026.0`, 14/3, 45/12).
- [x] Actualizar `test_cobertura_postgres_021.py` con los 15 índices.
- [x] Actualizar `test_control_instituciones_010.py` (tenants en caliente con 23 tablas e índices).
- [x] Actualizar `test_ciclo_vida_catalogo_postgres_014.py` y `test_compras_postgres_020.py`.
- [x] Actualizar `test_bootstrap_control_postgres_010.py` y `test_esquema_postgres.py`.
- [x] Crear `tests/funcional/sistema/test_salud_esquema_postgres_026.py` con los ocho bloques del plan (§11.2).
- [x] Confirmar que U-07 rechaza una segunda fila en PostgreSQL.
- [x] Confirmar que la base temporal se borra y `apt_erp` no se toca.

## T10 — Frontend tests y build

**ACs:** AC-17.

- [x] `ng test --watch=false --browsers=ChromeHeadless` en verde.
- [x] `ng build` limpio.
- [x] Confirmar que los campos legados no aparecen en el bundle.

## T11 — Documentación viva

**ACs:** AC-19.

- [x] `docs/spec/stack.md`: actualizar la nota de vigencia (26/23, `026.0`) y agregar la sección de la Feature 026.
- [x] `database/README.md`: 26/23 y `026.0`.
- [x] `AGENTS.md` §4: 26/23 y `026.0`.
- [x] `AGENTS.md` §7: 21 entidades de dominio.
- [x] `docs/spec/roadmap.md`: agregar la fila 026 en ejecución.
- [x] `MEMORY.md`: estado, decisiones y errores a evitar.
- [x] `grep` de coherencia sin coincidencias obsoletas en notas de vigencia.

## T12 — Suites completas y contrato

**ACs:** AC-15, AC-16.

- [x] `pytest -q` SQLite en verde.
- [x] Gated PostgreSQL en verde.
- [x] Gated Redis en verde.
- [x] `/openapi.json` en 75/73.
- [x] `POST /inventario/movimientos` documenta `stock_sede_id` y no `inventario_id`.
- [x] Los DTOs de dashboard no exponen campos legados.
- [x] Los 409 nuevos están documentados.
- [x] `permisos.py` y la matriz de operaciones sin diff.

## T13 — Reconstrucción del volumen y recorrido 4200

**ACs:** AC-1, AC-2, AC-3, AC-5, AC-18.

- [x] `docker compose down -v` + `up -d`; logs de `01_` y `02_` sin errores.
- [x] 26 tablas en `control` y 23 en los 4 tenants.
- [x] `026.0` en control y tenants.
- [x] 0 tablas `inventario` en toda la base.
- [x] 14 `stock_sede` y 3 movimientos **sumando los tenants** (INST-001: 10 y 3; INST-002: 4 y 0; INST-003/004: 0), 45/12 en INST-001 y 0 movimientos sin `stock_sede_id`.
- [x] 15 índices por esquema en `pg_indexes`.
- [x] Recorrido 4200: alta de sede duplicada → 409; edición duplicada → 409; departamento duplicado → 409.
- [x] Recorrido 4200: proveedor con RUT equivalente → 409; usuario con correo en mayúsculas → 409.
- [x] Recorrido 4200: movimiento por `stock_sede_id`; dashboard sin campos legados; ticket y detalle funcionando.
- [x] Consola sin errores.

## T14 — Humo 8080, evidencia y cierre

**ACs:** AC-17, AC-18, AC-19, AC-20.

- [x] `docker compose build frontend` + `up -d frontend`.
- [x] Humo en 8080: dashboard, administración, inventario y rutas directas de Angular.
- [x] Consola sin errores.
- [x] Crear `evidencia/README.md` con línea base, resultados, SQL, capturas y enlaces.
- [x] Verificar AC-20: `CAPACIDADES` conserva `"inventario"`.
- [x] Marcar cada AC de `spec.md` §6 con su evidencia.
- [x] Marcar `roadmap.md` con la 026 cerrada.
- [x] Actualizar `MEMORY.md` (≤ 50 líneas).
- [x] `grep` final de coherencia.
- [x] `git status` / `git diff --stat` limitados a este proyecto.

## Cierre

- [x] Todas las casillas de T1–T14 marcadas.
- [x] `spec.md` §6 con evidencia en cada AC.
- [x] Suites SQLite, PostgreSQL gated, Redis gated y frontend en verde.
- [x] 4200 recorrido funcional con escritura real.
- [x] 8080 reconstruido y humo verificado.
- [x] Documentación sincronizada: 21 entidades, 26/23 tablas, `026.0`.
- [x] Sin cambios en permisos, rutas, capabilities ni dependencias.
- [x] Evidencia publicada en `evidencia/README.md`.
