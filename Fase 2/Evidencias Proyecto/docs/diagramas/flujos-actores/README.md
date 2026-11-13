# Flujos de uso por actor

Diagramas funcionales de CompuStock ERP. Cada figura muestra un recorrido paso a paso, con seis tarjetas numeradas, flechas de avance y un resultado global. Son diagramas de flujo, no capturas de pantalla: buscan que el recorrido se entienda sin depender de la resolución de una imagen.

El informe que los integra está en [`docs/informes/Informe_Flujos_Actores.docx`](../../informes/Informe_Flujos_Actores.docx).

## Índice

| # | Archivo | Actor | Flujo |
|---|---|---|---|
| 1 | `00-acceso-comun` | Todos | Login Clerk, identidad, rol y ruta inicial. |
| 2 | `01-superadmin-gobierno-saas` | Superadmin | Portal SaaS, instituciones, capacidades y administradores. |
| 3 | `02-superadmin-alta-institucion` | Superadmin | Alta de tenant, sede inicial, Administrador y módulos. |
| 4 | `03-administrador-administracion` | Administrador | Sedes, departamentos, usuarios y encargados. |
| 5 | `04-administrador-inventario-catalogo` | Administrador | Existencias, filtros, detalle y ciclo de vida del catálogo. |
| 6 | `05-administrador-compras` | Administrador | Necesidades, OC, emisión, factura y cobertura. |
| 7 | `06-administrador-pedidos` | Administrador | Kanban, estados, edición, rechazo y anulación. |
| 8 | `07-bodeguero-pedidos-despacho` | Bodeguero | Preparación del despacho y cierre del pedido. |
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
powershell -NoProfile -ExecutionPolicy Bypass -File .\_exportar.ps1
```

`_generar.py` define los 12 flujos en una sola estructura de datos y escribe los HTML. `_exportar.ps1` copia cada HTML a un directorio temporal, ejecuta Edge headless y espera a que el PNG termine de escribirse antes de copiarlo de vuelta.

Si Edge está en otra ruta, ajusta `$edge` al inicio de `_exportar.ps1`. El script usa `C:\Users\ricar\AppData\Local\Temp\opencode\flujos-export` como directorio de trabajo.

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

- El despacho de pedidos (`POST /api/v1/tickets/{id}/despacho`), el registro de movimientos (`POST /api/v1/inventario/movimientos`) y el catálogo global de proveedores del Superadmin existen en la API, pero no tienen una pantalla dedicada en el frontend.
- El informe los marca como `API` para no prometer una interfaz que no existe.
- Los diagramas reflejan el estado del código en la rama `ricardo`, publicada en GitHub; no se generaron capturas nuevas ni se modificó el producto.
