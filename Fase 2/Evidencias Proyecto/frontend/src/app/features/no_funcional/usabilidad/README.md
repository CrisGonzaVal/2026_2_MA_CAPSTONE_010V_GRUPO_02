# Pruebas de usabilidad — pendiente

Carpeta reservada para las pruebas **no funcionales de usabilidad** del frontend:
accesibilidad, contraste, legibilidad y ergonomía de los flujos.

## Estado actual

**Sin tests automatizados.** El proyecto cubre usabilidad de forma indirecta:

- Los specs de componente verifican que los flujos críticos se pueden completar
  (render, formularios, navegación).
- La revisión de UI aplica la convención de Tailwind (sin CSS quemado,
  `styles: []` prohibido) y la skill `web-design-guidelines` cuando se audita.

## Pendiente conocido

| Ítem | Detalle | Dónde está registrado |
|---|---|---|
| Aviso de accesibilidad en el buscador operativo de inventario | Hallazgo de la auditoría de UI | `docs/spec/deuda-tecnica.md` (DT-12) |
| Enmienda T-17 (pestañas ARIA de `/administracion`) | Ya cerrada en su feature | `docs/spec/features/012-gestion-administrativa/evidencia/README.md` |

## Qué debería entrar aquí

1. Auditoría automática de accesibilidad ( Lighthouse o axe ) sobre las vistas
   principales, con umbral mínimo por WCAG AA.
2. Tests de teclado: navegación completa por tabulación y foco visible.
3. Pruebas de contraste sobre la paleta real de Tailwind.
4. Recorridos de usabilidad con los cuatro roles (Superadmin, Administrador,
   Bodeguero, Solicitante).

## Cómo se ejecutaría

```powershell
$env:CHROME_BIN = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
npx ng test --watch=false --browsers=ChromeHeadless
```

con los specs de usabilidad alojados junto a la vista que prueban (convención de
Angular) y referenciados desde este índice, igual que los specs funcionales.
