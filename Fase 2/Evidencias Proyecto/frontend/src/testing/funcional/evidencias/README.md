# Evidencias de aceptación del frontend — índice

La **evidencia de aceptación** del frontend es la que registra, por feature,
que los AC se cumplieron con verificación observable: specs en verde, build de
producción limpio y recorrido en los dos puertos (4200 funcional, 8080 humo).

Cada evidencia sigue en la carpeta de su feature, en
`docs/spec/features/NNN-nombre-feature/evidencia/README.md`: es documentación de
la feature y se referencia desde su `spec.md`, su `tasks.md` y el `roadmap.md`.
Esta carpeta es el **índice único** que las reúne.

| Feature | Qué valida la evidencia | Enlace |
|---|---|---|
| 003 — Modal de ticket | Formulario modal, persistencia transaccional, rutas | [README.md](../../../../../docs/spec/features/003-modal-ticket/evidencia/README.md) |
| 007 — Control de acceso por roles | Guards, matriz y redirigir por rol | [README.md](../../../../../docs/spec/features/007-control-acceso-roles/evidencia/README.md) |
| 008 — Particionamiento institucional | Ámbito institucional en la cabecera | [README.md](../../../../../docs/spec/features/008-particionamiento-institucional/evidencia/README.md) |
| 012 — Gestión administrativa | CRUD institucional y panel SaaS | [README.md](../../../../../docs/spec/features/012-gestion-administrativa/evidencia/README.md) |
| 013 — Ciclo de vida del ticket | Estados, historial y tablero | [README.md](../../../../../docs/spec/features/013-ciclo-vida-ticket/evidencia/README.md) |
| 014 — Ciclo de vida del catálogo | Gestión del catálogo e historiales | [README.md](../../../../../docs/spec/features/014-ciclo-vida-catalogo/evidencia/README.md) |
| 017 — Provisionamiento y gobierno | Invitaciones y gobierno de administradores | [README.md](../../../../../docs/spec/features/017-provisionamiento-y-gobierno-de-identidades/evidencia/README.md) |
| 018 — Filtros de inventario | Filtro por sede y departamento | [README.md](../../../../../docs/spec/features/018-filtro-inventario-sede-departamento/evidencia/README.md) |
| 019 — Detalle de producto | Detalle por alcance | [README.md](../../../../../docs/spec/features/019-detalle-producto-por-alcance/evidencia/README.md) |
| 020 — Reabastecimiento y compras | Flujo de compras y recepción | [README.md](../../../../../docs/spec/features/020-reabastecimiento-compras/evidencia/README.md) |
| 021 — Cobertura automática | Cobertura por orden de compra | [README.md](../../../../../docs/spec/features/021-cobertura-automatica-tickets-compras/evidencia/README.md) |
| 022 — Mantenimiento técnico I | Limpieza sin cambio de conducta | [README.md](../../../../../docs/spec/features/022-mantenimiento-tecnico/evidencia/README.md) |
| 023 — Refactor de `compra_service` | Equivalencia contractual | [README.md](../../../../../docs/spec/features/023-refactor-compra-service/evidencia/README.md) |
| 024 — Hardening operativo I | Observabilidad, CORS y borde nginx | [README.md](../../../../../docs/spec/features/024-hardening-operativo/evidencia/README.md) |
| 025 — Límite de tasa distribuido | Límite distribuido y fail-open | [README.md](../../../../../docs/spec/features/025-limite-tasa-distribuido/evidencia/README.md) |
| 026 — Salud del esquema BD | Normalización, índices y unicidades | [README.md](../../../../../docs/spec/features/026-salud-esquema-bd/evidencia/README.md) |

## Qué se registra en cada evidencia

- Conteo de specs en verde (`ng test`) y del build de producción (`ng build`).
- Recorrido funcional en **4200** con el resultado esperado de cada paso.
- Recorrido de humo en **8080** con la imagen reconstruida.
- Errores de consola y casos de error verificados.

Los AC de cada feature están marcados con su evidencia en el `spec.md` §6 de esa
feature, y el cierre exige además todos los checks de `tasks.md` (`AGENTS.md`
§8.5).
