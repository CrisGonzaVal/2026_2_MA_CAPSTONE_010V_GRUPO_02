# `src/testing/` — soporte y registro de pruebas del frontend

Esta carpeta **no forma parte de la aplicación**: `tsconfig.app.json` compila
solo `src/main.ts`, así que nada de aquí entra en el bundle de producción.

## Contenido

- [`clerk-falso.ts`](clerk-falso.ts) — doble del SDK `@clerk/clerk-js` que usan
  `core/services/auth.service.spec.ts`, `features/auth/login.component.spec.ts`
  y `features/control/control-login.component.spec.ts`.
- [`funcional/README.md`](funcional/README.md) — índice de los 42 specs por tipo
  (unitarios, integración y sistema/E2E).
- [`funcional/evidencias/README.md`](funcional/evidencias/README.md) — índice de
  las 16 evidencias de aceptación.
- [`no_funcional/usabilidad/README.md`](no_funcional/usabilidad/README.md) y
  [`no_funcional/compatibilidad/README.md`](no_funcional/compatibilidad/README.md)
  — alcance y brechas de las pruebas no funcionales pendientes.

## Qué no vive aquí

Los specs **no se mueven**: siguen junto a su sujeto (`x.component.spec.ts` al
lado de `x.component.ts`), por convención de Angular. Este directorio solo
guarda el soporte compartido y el registro por tipo; los tests ejecutables del
backend viven en `backend/tests/` y su guía es `backend/tests/README.md`.
