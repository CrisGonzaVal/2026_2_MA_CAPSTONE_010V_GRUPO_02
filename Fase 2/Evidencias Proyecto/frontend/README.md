# CompuStock ERP — Frontend

Aplicación Angular 18 standalone del proyecto CompuStock ERP. Consume la API
FastAPI en `/api/v1` y usa Clerk para la sesión.

## Requisitos

- Node.js 20+ y npm.
- Backend levantado en `http://localhost:8000`.
- Variables de Clerk configuradas en el `.env` de la raíz (no se versionan).

## Arranque

```bash
npm install
npm start
```

Dev server: <http://localhost:4200>. Se recarga al cambiar el código.

## Build

```bash
npm run build
```

El resultado queda en `dist/frontend-app/`. La imagen de producción lo sirve con
nginx en <http://localhost:8080>. **No hay volumen montado**: para que 8080
refleje un cambio hay que reconstruir la imagen:

```bash
docker compose -f docker-compose.yml build frontend
docker compose -f docker-compose.yml up -d frontend
```

## Tests

```powershell
$env:CHROME_BIN = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
npx ng test --watch=false --browsers=ChromeHeadless
```

No usar `npm test` a secas: arranca Karma en modo watch y el comando no termina.

## Estructura

```text
public/                  # Assets estáticos (favicon, imágenes, íconos)
src/app/core/            # Guards, interceptors y servicios singleton
src/app/shared/          # Componentes, config, interfaces y utils reutilizables
src/app/features/        # dashboard, inventario, tickets, administracion,
                         # compras, control, auth y acceso-denegado
src/styles.scss          # Tailwind CSS global
```

Cada feature de negocio se carga con `loadChildren` desde `app.routes.ts` y
expone su `<feature>.routes.ts`. Los componentes usan `inject()`, `signal()` y
`computed()`; no hay `NgModule` ni CSS quemado fuera de Tailwind.
