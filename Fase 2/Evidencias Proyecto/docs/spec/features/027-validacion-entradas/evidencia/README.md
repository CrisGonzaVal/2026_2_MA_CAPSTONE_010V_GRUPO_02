# Evidencia — Feature 027: validación de entradas y errores de contrato

**Cierre:** 24/Nov/2026
**Alcance:** contrato Pydantic y errores de BD en backend; RUT, parser 422 y límites en frontend.
**Sin cambio de esquema:** `026.0`, 26 tablas en `control`, 23 por tenant y 21 entidades.

## 1. Línea base y resultado

| Suite | Antes (026 + enmienda 008) | Cierre 027 |
|---|---|---|
| `pytest` SQLite | 1675 passed / 105 skipped | **1863 passed / 109 skipped / 0 failed** |
| Gated PostgreSQL 16 | 1769 passed / 3 skipped | **1969 passed / 3 skipped / 0 failed** |
| Gated Redis 025 | 1662 passed / 102 skipped | **3 passed** (`test_limite_tasa_redis_025.py` con `REDIS_TEST_URL`) |
| `ng test` | 559 SUCCESS | **597 SUCCESS** |
| `ng build` | limpio | **limpio** (`main-NQGWSVMA.js`, 339.25 kB iniciales) |
| OpenAPI / matriz | 75 / 73 | **75 / 73**, sin rutas nuevas |

La suite gated se ejecutó completa con
`POSTGRES_TEST_URL=postgresql://postgres:postgres@localhost:5433/postgres`; crea y destruye
bases temporales y no toca `apt_erp`.

## 2. Qué cambió

- **RUT:** `backend/app/core/rut.py` (módulo 11) valida proveedor e institución; semilla y
  fixtures corregidos. Espejo `frontend/src/app/shared/utils/rut.ts` con `rutValido`.
- **DTO:** límites del DDL, ids `ge=1`, `Literal["ENTRADA","SALIDA"]`, `EmailStr`, nombres con
  `strip` y `extra="forbid"` en los DTO de entrada. Los DTO de respuesta no heredan `forbid`.
- **Errores de BD:** `backend/app/core/errores_bd.py` traduce `IntegrityError`/`DataError`
  conocidos a **409/422** con `detail` y `X-Request-ID`; lo desconocido sigue en 500.
- **Frontend:** parser 422 compartido (`validacion-http.ts`) integrado en `errores-http.ts`;
  tickets, compras, control y administración muestran el campo culpable. `maxlength=500` y
  `Validators.maxLength(500)` en alta y edición de ticket.

## 3. Contrato verificado

`GET /openapi.json`: **75 operaciones**, matriz **73**; `MovimientoCrear.tipo_movimiento`
publica `enum: ["ENTRADA","SALIDA"]`; `POST /tickets/` documenta 422. `ProveedorCrear.rut`
mantiene `maxLength: 20`.

## 4. Semilla y reset

`docker compose down -v` + `up -d` recreó el volumen. Consulta directa a PostgreSQL:

```text
INST|INST-001|65.432.100-0
INST|INST-002|65.887.230-3
INST|INST-003|77.120.540-2
INST|INST-004|65.998.720-1
PROV|1|76.543.210-3
PROV|2|77.654.321-7
PROV|3|78.765.432-0
VERSION|026.0
MAPA|17
```

La guardia fail-closed de `02_datos_semilla.sql` termina sin error en el arranque limpio.

## 5. Recorrido funcional en 4200

Sesión real de Administrador (`admin020.test+clerk_test@example.com`, INST-001) y escritura
real a través del proxy de desarrollo:

| Caso | Resultado |
|---|---|
| Ticket con `descripcion` de 501 | **422** `string_too_long`, `loc=["body","descripcion"]` |
| Ticket con `descripcion` de 500 | **201**, ticket #9 creado |
| Ticket con `campo_extra` | **422** `extra_forbidden` |
| Proveedor con RUT `76.543.210-8` | **422** `value_error`, DV inválido |
| Proveedor con RUT `77.777.777-7` | **201**, proveedor #4 |
| Mismo RUT como `77777777-7` | **409**, duplicado normalizado |
| Movimiento `AJUSTE` | **422** `literal_error` (ya no 400) |
| Movimiento con `institucion_id` | **422** `extra_forbidden` |
| Movimiento `entrada`, cantidad 1 | **201** |
| Producto con nombre `"   "` | **422** `string_too_short` |
| Textarea de descripción del alta | `maxlength="500"` verificado en el DOM |
| RUT inválido en el alta inline de proveedor | Mensaje «El RUT no es válido: revisa el dígito verificador.» y sin POST |

La consola no registró excepciones de la aplicación; los únicos errores de red fueron los
4xx deliberados del recorrido. Captura: [4200-ticket-descripcion-500.png](4200-ticket-descripcion-500.png).

## 6. Humo en 8080

Se reconstruyó la imagen (`docker compose build frontend`) y se levantó con `up -d frontend`.
El bundle servido fue `main-NQGWSVMA.js`. Verificado:

- `/tickets` carga y el modal de alta expone `maxlength="500"`.
- `/compras/nueva` carga; un RUT con DV inválido muestra el mensaje de campo y no agrega el
  proveedor.
- Consola sin errores (solo el aviso esperado de claves dev de Clerk).
- Captura: [8080-ticket-descripcion-500.jpeg](8080-ticket-descripcion-500.jpeg).

## 7. Batería específica 027

| Archivo | Casos |
|---|---|
| `backend/tests/funcional/unitarios/test_rut_027.py` | 58 |
| `backend/tests/funcional/unitarios/test_esquemas_027.py` | 93 |
| `backend/tests/funcional/sistema/test_errores_bd_027.py` | 18 |
| `backend/tests/funcional/sistema/test_semilla_rut_027.py` | 7 |
| `backend/tests/funcional/sistema/test_validacion_entradas_postgres_027.py` | 4 (gated) |
| `backend/tests/funcional/integracion/test_validacion_entradas_027.py` | 10 |
| `frontend/src/app/shared/utils/rut.spec.ts` | 10 |
| `frontend/src/app/shared/utils/validacion-http.spec.ts` | 11 |

## 8. Deuda absorbida

DT-13…DT-16 quedan **cerrados** en `docs/spec/deuda-tecnica.md`: DTO alineados al DDL, RUT con
DV, contrato de error único y errores de BD traducidos. La caché de lecturas sigue fuera de
alcance y sin feature asignada.
