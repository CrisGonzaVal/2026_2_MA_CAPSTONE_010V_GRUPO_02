# Feature 021 — Evidencia del recorrido funcional en 4200 y humo en 8080

Cierre de la Feature 021 (cobertura automática de pedidos por órdenes de compra).
El recorrido se hizo contra PostgreSQL real (`apt_erp`, **27** tablas de
`control`, **24** por tenant, versión **`021.1`**) con sesiones Clerk reales y
escritura persistida. No se transcriben tokens ni claves.

Fecha: **08/Nov/2026** (hora local). Entorno: `docker compose` con
`compustock_db`, `compustock_backend` y `compustock_frontend`; dev server de
Angular en 4200 y build de producción en 8080 tras reconstruir la imagen.

## 1. Suites y contrato

| Verificación | Resultado |
|---|---|
| `pytest` SQLite (suite completa) | **1496 passed**, 88 skipped, 0 failed |
| Gated PostgreSQL 16 (`test_cobertura_postgres_021.py`) | **5/5** |
| Endpoints 021 (`test_cobertura_021.py`) | **37/37** |
| `ng test --watch=false --browsers=ChromeHeadless` | **537/537 SUCCESS** |
| `ng build` | limpio (337.32 kB iniciales, 93.63 kB transferidos) |
| `/openapi.json` | **73** operaciones v1 y 75 HTTP totales (incluye `GET /` y `GET /health`); preview presente |
| `MATRIZ_PERMISOS` | **73** operaciones; una sola alta (`POST /compras/cobertura/preview`) |

## 2. Cuentas del recorrido

| Rol | Cuenta | Ámbito |
|---|---|---|
| Administrador | `admin020.test+clerk_test@example.com` (usuario 13, INST-001) | todas las sedes de la institución |
| Bodeguero | `bodeguero.test+clerk_test@example.com` (Roberto Díaz, usuario 12) | Sede Maipú |
| Solicitante | `solicitante.test+clerk_test@example.com` (Paula Rojas, usuario 11) | Departamento Biblioteca → Sede Maipú |

La cuenta de Administrador se reutilizó del recorrido de la 020 porque la semilla
no incluye un Administrador `+clerk_test` (hallazgo ya registrado en
`MEMORY.md`); su fila vive en el tenant y en `control.mapa_usuario_esquema`.

## 3. Recorrido funcional en 4200

### 3.1 Pedido y necesidad con pedidos (AC-1, V-1)

El Solicitante creó el **pedido #9** («Reposicion de rotuladores para inventario
fisico», producto 9 × 15). El Administrador lo pasó por `EnRevision` y lo dejó
`EnCurso` desde el detalle. `/compras/necesidades?sede_id=2` mostró la fila del
producto 9 con **stock 6, mínimo 12, demanda 15, comprometido 0, borrador 0,
sugerido 21** y el pedido #9 anidado con **cubierta 6 / faltante 9**.

El menú ya lee «Pedidos», el tablero se titula «Estados de pedidos», el botón es
«+ Crear pedido» y las columnas muestran «En Revisión» y «En Curso».

### 3.2 Preview parcial y total (AC-2, AC-9, AC-12)

`POST /compras/cobertura/preview` con una OC simulada de **5** devolvió
`asignada 5 / faltante 4 / cobertura parcial`; con **21**, `asignada 9 /
faltante 0 / sin asignar 12 / cobertura total`. Ninguna llamada persistió filas
ni reservó stock; repetirla devolvió el mismo resultado.

### 3.3 Emisión con plan congelado (AC-3, AC-4)

Se creó la OC **1** por 21 unidades × $250 = **$5.250** y se emitió como
**`OC-2026-000001`**. El detalle de la orden mostró el panel «Pedidos cubiertos
por esta OC» con el pedido #9, el producto, **asignado 9** y **faltante 0**. El
plan quedó persistido en `orden_compra_ticket` en la misma transacción de la
emisión.

### 3.4 Factura y recepción (AC-6)

El Administrador registró la factura **`F-021-0001`** (08/11/2026, $5.250) y la
OC pasó a `Facturada`. El Bodeguero confirmó la recepción: movimiento
**`ENTRADA` 21** y stock de la sede 2/producto 9 de **6 → 27**. El historial del
pedido sumó una fila `EnCurso → EnCurso` con `orden_compra_id = 1` y
`numero_oc = OC-2026-000001`; el pedido siguió en `EnCurso`, con
`stock_disponible = true`, la asignación en estado `Recibida` y la cadena
**15 / 9 / 9 / 0 / 0**.

### 3.5 Despacho y cierre (AC-5, AC-9)

El Bodeguero despachó el pedido: movimiento **`SALIDA` 15**, stock **27 → 12**,
pedido **`Cerrado`** y cadena final **15 / 9 / 9 / 15 / 0**. La OC conservó su
plan y el pedido cerrado ya no aparece como demanda viva.

## 4. Verificación SQL

| Consulta | Resultado |
|---|---|
| `orden_compra_ticket` | 1 fila: OC 1, pedido 9, producto 9, asignada 9, faltante 0 |
| `historial_transicion_ticket` con `orden_compra_id` | 1 fila: `EnCurso → EnCurso`, usuario 12, motivo «Desbloqueo por reabastecimiento: OC OC-2026-000001 / Factura F-021-0001» |
| `stock_sede` (sede 2, producto 9) | `stock_actual = 12` |
| `movimiento_inventario` | 11 `ENTRADA` 21 y 12 `SALIDA` 15 |
| `version_esquema` | `021.1` en `control` y en el tenant |
| Tablas | 27 en `control`, 24 en `tenant_inst_001_038aa2a9` |

## 5. Humo en 8080

Se reconstruyó la imagen (`docker compose -f docker-compose.yml build frontend`
+ `up -d frontend`) y el contenedor quedó `healthy`. El recorrido de humo
confirmó «Pedidos», «Estados de pedidos», «+ Crear pedido», «En Revisión»,
«Compras», las columnas Comprometido/Borrador, las subfilas de pedidos, el plan
de la OC y las tablas de cobertura del detalle. **0 errores de consola.**

## 6. Capturas

| Archivo | Contenido |
|---|---|
| `4200-01-estados-pedidos.png` | Tablero «Estados de pedidos» con columnas «En Revisión» y «En Curso» en 4200 |
| `4200-02-necesidades-pedidos.png` | Vista «Compras» con Comprometido/Borrador y pedidos anidados en 4200 |
| `4200-03-orden-plan.png` | OC `OC-2026-000001` con «Pedidos cubiertos por esta OC» en 4200 |
| `4200-04-detalle-cobertura.png` | Detalle del pedido #9 con cadena 15/9/9/15/0 y asignación de la OC en 4200 |
| `8080-01-estados-pedidos.png` | Mismo tablero servido por el build de producción en 8080 |
| `8080-02-necesidades.png` | Vista «Compras» en 8080 |
| `8080-03-orden-plan.png` | Plan de la OC en 8080 |
| `8080-04-detalle.png` | Cobertura del pedido en 8080 |

## 7. Hallazgos

- El DTO de alta de pedido (`TicketRespuesta`) devuelve `estado_id`, no
  `estado_nombre`; el nombre del estado se lee del detalle. El recorrido se
  ajustó a ese contrato sin cambiarlo.
- La respuesta de recepción publica `tickets_desbloqueados` (no `desbloqueados`)
  y no repite `orden_compra_id`; el enlace con la OC se verificó en el historial
  y en la tabla puente.
- El detalle del pedido usa scroll interno: `take_screenshot(fullPage)` no
  incluye las tablas de cobertura. Las capturas `04` se tomaron tras
  `scrollIntoView` al bloque «Cobertura por producto».
- Los mensajes canónicos del backend siguen usando «ticket»; el renombrado a
  «pedido» es solo de la copia visible de la SPA (AC V-1).
