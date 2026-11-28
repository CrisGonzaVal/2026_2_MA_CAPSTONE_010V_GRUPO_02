# Flujos de uso por actor

Diagramas funcionales de CompuStock ERP. Cada figura muestra un recorrido paso a paso, con seis tarjetas numeradas, flechas de avance y un resultado global. Son diagramas de flujo, no capturas de pantalla: buscan que el recorrido se entienda sin depender de la resolución de una imagen.

El informe que los integra está en [`docs/informes/Informe_Flujos_Actores.docx`](../../informes/Informe_Flujos_Actores.docx).

## Índice

| # | Archivo | Actor | Flujo |
|---|---|---|---|
| 1 | `00-acceso-comun` | Todos | Login Clerk, identidad, rol y ruta inicial. |
| 2 | `01-superadmin-gobierno-saas` | Superadmin | Portal SaaS, instituciones, capacidades y administradores. |
| 3 | `02-superadmin-alta-institucion` | Superadmin | Alta de tenant, sede inicial, Administrador y módulos. |
| 4 | `03-administrador-administracion` | Administrador | Sedes, departamentos y usuarios. |
| 5 | `04-administrador-inventario-catalogo` | Administrador | Existencias, filtros, detalle y ciclo de vida del catálogo. |
| 6 | `05-administrador-compras` | Administrador | Necesidades, OC, emisión, factura y cobertura. |
| 7 | `06-administrador-pedidos` | Administrador | Kanban, estados, edición, rechazo y anulación. |
| 8 | `07-bodeguero-pedidos-despacho` | Bodeguero | Preparación del retiro y cierre del pedido. |
| 9 | `08-bodeguero-inventario` | Bodeguero | Stock de la sede, filtros y alertas. |
| 10 | `09-bodeguero-recepcion-compras` | Bodeguero | Recepción de OC facturadas y desbloqueo. |
| 11 | `10-solicitante-crear-pedido` | Solicitante | Consulta, creación y justificación del pedido. |
| 12 | `11-solicitante-seguimiento` | Solicitante | Detalle, estados, edición y anulación. |

Cada flujo tiene dos archivos:

- `*.html`: fuente autocontenida, sin dependencias externas.
- `*.png`: exportación a 2400 × 1120 px (2x), usada en el informe.

## Diseño

- Lienzo base: 1200 × 560 px; exportación 2x con `--force-device-scale-factor=2`.
- Fondo tipo papel (`#F7F4EE`) con tarjetas blancas, tinta (`#1E293B`), acento azul (`#2563EB`) y notas cálidas.
- Tipografías: Instrument Serif para títulos y Geist para texto; se cargan desde Google Fonts dentro del HTML.
- Tarjeta azul con etiqueta `CLAVE` para el paso que concentra el control del flujo.
- Barra inferior con el resultado global y encabezado con actor y ruta principal.
- La numeración de las tarjetas coincide con la tabla “Paso a paso” del informe.

## Reproducción

Desde esta carpeta:

```powershell
python _generar.py
# PNG 2x de cada flujo: captura la ventana de 1200 × 560 (el SVG ocupa la
# primera pantalla; la nota queda fuera del encuadre).
$edge = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
& $edge --headless --disable-gpu --hide-scrollbars --force-device-scale-factor=2 `
  --window-size=1200,560 --screenshot="$PWD\03-administrador-administracion.png" `
  "file:///$($PWD.Path.Replace('\','/'))/03-administrador-administracion.html"
```

`_generar.py` define los 12 flujos en una sola estructura de datos y escribe los HTML. La
exportación a PNG se hace con Edge headless (`--force-device-scale-factor=2`), que rasteriza
la ventana completa de 1200 × 560 px a 2400 × 1120 px. No hay script `_exportar.ps1` en el
repo: el comando de arriba es el procedimiento vigente.

## Validación

```powershell
Get-ChildItem *.html | ForEach-Object {
  python ..\..\..\.agents\skills\diagram-design\scripts\self_check.py $_.FullName
}
```

Resultado esperado: 12/12 sin fallos. Los PNG se verificaron a 2400 × 1120 px.

## Fuentes

- Rutas y guards: `frontend/src/app/app.routes.ts`.
- Roles y permisos: `frontend/src/app/core/auth/roles.ts`.
- Matriz de la API: `backend/app/core/permisos.py`.
- Navegación visible: `frontend/src/app/app.component.html`.
- Evidencias funcionales: `docs/spec/features/012`, `013`, `014`, `017`, `018`, `019`, `020` y `021`.

## Límites conocidos

- El retiro de pedidos (`POST /api/v1/tickets/{id}/retiro`) se ejecuta desde el detalle («Registrar retiro») y no tiene una pantalla dedicada; el registro de movimientos (`POST /api/v1/inventario/movimientos`) y el catálogo global de proveedores del Superadmin existen en la API, sin pantalla en el frontend.
- El informe marca los movimientos y el catálogo de proveedores como `API`; el retiro se documenta en el flujo 07 y en la matriz como acción del Bodeguero de la sede.
- Los diagramas se regeneraron el 27/Nov/2026 con el contrato vigente (catálogo de cuatro estados y retiro). El flujo 07 conserva el slug histórico `07-bodeguero-pedidos-despacho`; su título y contenido usan «retiro».
