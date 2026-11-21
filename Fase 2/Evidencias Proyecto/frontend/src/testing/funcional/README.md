# Pruebas funcionales del frontend — índice

Clasificación de los specs de Angular por **tipo de prueba**.

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
| [`app/features/compras/services/compras.service.spec.ts`](../../app/features/compras/services/compras.service.spec.ts) | Servicio de compras |
| [`app/features/control/services/control.service.spec.ts`](../../app/features/control/services/control.service.spec.ts) | Servicio del panel SaaS |

### Sistema / E2E — recorridos de usuario sobre la app integrada

Los specs de componente de cada feature recorren el flujo completo de la vista
con sus servicios reales: [`dashboard`](../../app/features/dashboard/dashboard.component.spec.ts),
[`inventario`](../../app/features/inventario/inventario.component.spec.ts),
[`producto-detalle`](../../app/features/inventario/producto-detalle.component.spec.ts),
[`tickets`](../../app/features/tickets/tickets.component.spec.ts),
[`ticket-detalle`](../../app/features/tickets/ticket-detalle.component.spec.ts),
[`administracion`](../../app/features/administracion/usuarios.component.spec.ts) (usuarios,
sedes, departamentos, encargados y navegación),
[`compras`](../../app/features/compras/compras.routes.spec.ts) (órdenes, necesidades, nueva
orden y recepción),
[`control`](../../app/features/control/control-login.component.spec.ts) (instituciones,
administradores, capacidades, dashboard SaaS),
[`auth`](../../app/features/auth/login.component.spec.ts) y
[`acceso-denegado`](../../app/features/acceso-denegado/acceso-denegado.component.spec.ts).

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
