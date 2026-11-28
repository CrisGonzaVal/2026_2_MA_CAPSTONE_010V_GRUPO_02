# Pruebas funcionales del frontend — índice

Clasificación de los specs de Angular por **tipo de prueba**.

Son **44 archivos** de spec bajo `src/app/` que ejecutan **671 casos** en la
última corrida verificada (27/Nov/2026). El índice los cubre todos; al final hay
un comando para detectar si alguno queda fuera.

## Por qué hay un índice y no una mudanza

Angular sigue la convención de **spec junto al sujeto** (`x.component.spec.ts`
al lado de `x.component.ts`): el spec importa su componente por ruta relativa y
`TestBed` lo monta en el mismo contexto de compilación. Separar los specs por
tipo rompe esa convención, vuelve frágil cada import relativo y no aporta
nada al runner (Karma ya descubre `src/**/*.spec.ts`).

Por eso en el frontend la clasificación **se materializa como índice navegable**
mientras los specs siguen en su carpeta de origen. En el backend sí hubo
reclasificación física, porque pytest no exige co-localización y ahí la
separación sí aporta (aislar los *gated* de PostgreSQL y Redis de los tests
rápidos).

## Índice por tipo

### Unitarios — lógica pura, sin plantillas

| Spec | Qué prueba |
|---|---|
| [`app/core/auth/roles.spec.ts`](../../app/core/auth/roles.spec.ts) | Resolución de roles y capacidades |
| [`app/shared/utils/etiqueta-estado.spec.ts`](../../app/shared/utils/etiqueta-estado.spec.ts) | Etiquetado de estados |
| [`app/shared/utils/errores-http.spec.ts`](../../app/shared/utils/errores-http.spec.ts) | Mapeo de errores HTTP |
| [`app/shared/utils/rut.spec.ts`](../../app/shared/utils/rut.spec.ts) | RUT: módulo 11 y forma visible |
| [`app/shared/utils/validacion-http.spec.ts`](../../app/shared/utils/validacion-http.spec.ts) | Parser de `loc`/`type` del 422 |

### Integración — servicios, guards, interceptores y rutas

| Spec | Qué prueba |
|---|---|
| [`app/core/services/auth.service.spec.ts`](../../app/core/services/auth.service.spec.ts) | Sesión Clerk, token y sesión Angular |
| [`app/core/interceptors/token.interceptor.spec.ts`](../../app/core/interceptors/token.interceptor.spec.ts) | Inyección del Bearer y `X-Request-ID` |
| [`app/core/guards/auth.guard.spec.ts`](../../app/core/guards/auth.guard.spec.ts) | Guard de autenticación |
| [`app/core/guards/role.guard.spec.ts`](../../app/core/guards/role.guard.spec.ts) | Guard de rol |
| [`app/core/guards/control-superadmin.guard.spec.ts`](../../app/core/guards/control-superadmin.guard.spec.ts) | Guard del panel SaaS |
| [`app/core/guards/tickets-acceso.spec.ts`](../../app/core/guards/tickets-acceso.spec.ts) | Acceso a tickets por rol |
| [`app/core/guards/superficies-retiradas.spec.ts`](../../app/core/guards/superficies-retiradas.spec.ts) | Superficies retiradas |
| [`app/features/administracion/administracion.routes.spec.ts`](../../app/features/administracion/administracion.routes.spec.ts) | Rutas de administración |
| [`app/features/compras/compras.routes.spec.ts`](../../app/features/compras/compras.routes.spec.ts) | Rutas de compras |
| [`app/features/control/control.routes.spec.ts`](../../app/features/control/control.routes.spec.ts) | Rutas del panel SaaS |
| [`app/features/dashboard/services/dashboard.service.spec.ts`](../../app/features/dashboard/services/dashboard.service.spec.ts) | Servicio de métricas |
| [`app/features/inventario/services/inventario.service.spec.ts`](../../app/features/inventario/services/inventario.service.spec.ts) | Servicio de inventario |
| [`app/features/administracion/services/administracion.service.spec.ts`](../../app/features/administracion/services/administracion.service.spec.ts) | Servicio de administración |
| [`app/features/tickets/services/ticket.service.spec.ts`](../../app/features/tickets/services/ticket.service.spec.ts) | Servicio de tickets |
| [`app/features/compras/services/compras.service.spec.ts`](../../app/features/compras/services/compras.service.spec.ts) | Servicio de compras |
| [`app/features/control/services/control.service.spec.ts`](../../app/features/control/services/control.service.spec.ts) | Servicio del panel SaaS |
| [`app/app.routes.spec.ts`](../../app/app.routes.spec.ts) | Rutas raíz, guards y carga diferida |
| [`app/features/administracion/administracion-nav.component.spec.ts`](../../app/features/administracion/administracion-nav.component.spec.ts) | Pestañas ARIA de administración (enmienda T-17) |

### Sistema / E2E — recorridos de usuario sobre la app integrada

| Spec | Qué prueba |
|---|---|
| [`app/app.component.spec.ts`](../../app/app.component.spec.ts) | Shell: cabecera, menú lateral, contexto institucional y badges por rol |
| [`app/features/dashboard/dashboard.component.spec.ts`](../../app/features/dashboard/dashboard.component.spec.ts) | Métricas y alertas del dashboard |
| [`app/features/inventario/inventario.component.spec.ts`](../../app/features/inventario/inventario.component.spec.ts) | Existencias y acciones del inventario |
| [`app/features/inventario/producto-detalle.component.spec.ts`](../../app/features/inventario/producto-detalle.component.spec.ts) | Detalle de producto por alcance |
| [`app/features/tickets/tickets.component.spec.ts`](../../app/features/tickets/tickets.component.spec.ts) | Listado y alta de tickets |
| [`app/features/tickets/ticket-detalle.component.spec.ts`](../../app/features/tickets/ticket-detalle.component.spec.ts) | Detalle, historial y transiciones del ticket |
| [`app/features/administracion/usuarios.component.spec.ts`](../../app/features/administracion/usuarios.component.spec.ts) | Usuarios, roles y asignación |
| [`app/features/administracion/sedes.component.spec.ts`](../../app/features/administracion/sedes.component.spec.ts) | CRUD de sedes y 409 por duplicado |
| [`app/features/administracion/departamentos.component.spec.ts`](../../app/features/administracion/departamentos.component.spec.ts) | CRUD de departamentos y sede asignada |
| [`app/features/compras/lista-ordenes/lista-ordenes.component.spec.ts`](../../app/features/compras/lista-ordenes/lista-ordenes.component.spec.ts) | Órdenes de compra: filtros, emisión y cancelación |
| [`app/features/compras/necesidades/necesidades.component.spec.ts`](../../app/features/compras/necesidades/necesidades.component.spec.ts) | Necesidades de compra por sede |
| [`app/features/compras/nueva-orden/nueva-orden.component.spec.ts`](../../app/features/compras/nueva-orden/nueva-orden.component.spec.ts) | Alta de orden de compra y de proveedor |
| [`app/features/compras/recepcion-bodega/recepcion-bodega.component.spec.ts`](../../app/features/compras/recepcion-bodega/recepcion-bodega.component.spec.ts) | Recepción de órdenes facturadas |
| [`app/features/control/control-login.component.spec.ts`](../../app/features/control/control-login.component.spec.ts) | Acceso al panel SaaS |
| [`app/features/control/administradores-control.component.spec.ts`](../../app/features/control/administradores-control.component.spec.ts) | Administradores institucionales e invitaciones |
| [`app/features/control/alta-institucion.component.spec.ts`](../../app/features/control/alta-institucion.component.spec.ts) | Alta de institución desde el panel SaaS |
| [`app/features/control/capacidades.component.spec.ts`](../../app/features/control/capacidades.component.spec.ts) | Capacidades por institución |
| [`app/features/control/dashboard-saas.component.spec.ts`](../../app/features/control/dashboard-saas.component.spec.ts) | Dashboard SaaS agregado |
| [`app/features/control/instituciones.component.spec.ts`](../../app/features/control/instituciones.component.spec.ts) | Listado y edición de instituciones |
| [`app/features/auth/login.component.spec.ts`](../../app/features/auth/login.component.spec.ts) | Login con Clerk |
| [`app/features/acceso-denegado/acceso-denegado.component.spec.ts`](../../app/features/acceso-denegado/acceso-denegado.component.spec.ts) | Pantalla de acceso denegado |

### Aceptación — evidencia por feature

Las evidencias de aceptación (AC verificados, conteos de suites y recorridos en
4200 y 8080) se indexan en [`evidencias/README.md`](evidencias/README.md).

### Humo — verificación rápida tras despliegue

El humo real del frontend es el **build de producción + recorrido corto en 8080**
(`docker compose -f docker-compose.yml build frontend` y luego `up -d frontend`),
según `AGENTS.md` §8.6. No es un spec de Karma: es un paso de cierre de feature.

## Cómo correr

```powershell
$env:CHROME_BIN = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
npx ng test --watch=false --browsers=ChromeHeadless
```

Nunca `npm test` a secas: Karma arranca en modo watch y el comando se queda
esperando.

## Comprobar que el índice está completo

Debe imprimir `0`. Lista los specs que existen en `src/app/` y no están
enlazados arriba (los nombres de archivo no se repiten, por eso basta comparar
por nombre).

```powershell
$doc = "src/testing/funcional/README.md"
(Get-ChildItem "src/app" -Recurse -Filter *.spec.ts | Where-Object {
  -not (Select-String -Path $doc -Pattern ([regex]::Escape($_.Name)) -Quiet)
}).Count
```
