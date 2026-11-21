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
| [`core/auth/roles.spec.ts`](../../core/auth/roles.spec.ts) | Resolución de roles y capacidades |
| [`shared/utils/etiqueta-estado.spec.ts`](../../shared/utils/etiqueta-estado.spec.ts) | Etiquetado de estados |
| [`shared/utils/errores-http.spec.ts`](../../shared/utils/errores-http.spec.ts) | Mapeo de errores HTTP |

### Integración — servicios, guards, interceptores y rutas

| Spec | Qué prueba |
|---|---|
| [`core/services/auth.service.spec.ts`](../../core/services/auth.service.spec.ts) | Sesión Clerk, token y sesión Angular |
| [`core/interceptors/token.interceptor.spec.ts`](../../core/interceptors/token.interceptor.spec.ts) | Inyección del Bearer y `X-Request-ID` |
| [`core/guards/auth.guard.spec.ts`](../../core/guards/auth.guard.spec.ts) | Guard de autenticación |
| [`core/guards/role.guard.spec.ts`](../../core/guards/role.guard.spec.ts) | Guard de rol |
| [`core/guards/control-superadmin.guard.spec.ts`](../../core/guards/control-superadmin.guard.spec.ts) | Guard del panel SaaS |
| [`core/guards/tickets-acceso.spec.ts`](../../core/guards/tickets-acceso.spec.ts) | Acceso a tickets por rol |
| [`core/guards/superficies-retiradas.spec.ts`](../../core/guards/superficies-retiradas.spec.ts) | Superficies retiradas |
| [`features/administracion/administracion.routes.spec.ts`](../administracion/administracion.routes.spec.ts) | Rutas de administración |
| [`features/compras/compras.routes.spec.ts`](../compras/compras.routes.spec.ts) | Rutas de compras |
| [`features/control/control.routes.spec.ts`](../control/control.routes.spec.ts) | Rutas del panel SaaS |
| [`features/dashboard/services/dashboard.service.spec.ts`](../dashboard/services/dashboard.service.spec.ts) | Servicio de métricas |
| [`features/inventario/services/inventario.service.spec.ts`](../inventario/services/inventario.service.spec.ts) | Servicio de inventario |
| [`features/administracion/services/administracion.service.spec.ts`](../administracion/services/administracion.service.spec.ts) | Servicio de administración |
| [`features/compras/services/compras.service.spec.ts`](../compras/services/compras.service.spec.ts) | Servicio de compras |
| [`features/control/services/control.service.spec.ts`](../control/services/control.service.spec.ts) | Servicio del panel SaaS |

### Sistema / E2E — recorridos de usuario sobre la app integrada

Los specs de componente de cada feature recorren el flujo completo de la vista
con sus servicios reales: [`dashboard`](../dashboard/dashboard.component.spec.ts),
[`inventario`](../inventario/inventario.component.spec.ts),
[`producto-detalle`](../inventario/producto-detalle.component.spec.ts),
[`tickets`](../tickets/tickets.component.spec.ts),
[`ticket-detalle`](../tickets/ticket-detalle.component.spec.ts),
[`administracion`](../administracion/usuarios.component.spec.ts) (usuarios,
sedes, departamentos, encargados y navegación),
[`compras`](../compras/compras.routes.spec.ts) (órdenes, necesidades, nueva
orden y recepción),
[`control`](../control/control-login.component.spec.ts) (instituciones,
administradores, capacidades, dashboard SaaS),
[`auth`](../auth/login.component.spec.ts) y
[`acceso-denegado`](../acceso-denegado/acceso-denegado.component.spec.ts).

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
