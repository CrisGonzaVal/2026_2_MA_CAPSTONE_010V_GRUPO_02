# Pruebas de aceptación — índice

Esta carpeta agrupa la **evidencia de aceptación** del proyecto: la prueba de que
cada feature cerrada cumple sus criterios de aceptación (AC) con verificación
registrada.

## Dónde vive cada evidencia

La evidencia es **documentación de feature**, no código de test, así que **no se
duplica ni se mueve**: cada una sigue en la carpeta de su feature, en
`docs/spec/features/NNN-nombre-feature/evidencia/README.md`. Esta carpeta es el
**índice único** que las reúne por tipo de aceptación.

| Feature | Tipo de aceptación predominante | Evidencia |
|---|---|---|
| 003 — Modal de ticket | E2E de UI + persistencia transaccional | [README.md](../../../../docs/spec/features/003-modal-ticket/evidencia/README.md) |
| 007 — Control de acceso por roles | Aceptación de matriz de permisos | [README.md](../../../../docs/spec/features/007-control-acceso-roles/evidencia/README.md) |
| 008 — Particionamiento institucional | Aceptación de aislamiento por institución | [README.md](../../../../docs/spec/features/008-particionamiento-institucional/evidencia/README.md) |
| 012 — Gestión administrativa | Aceptación de CRUD institucional | [README.md](../../../../docs/spec/features/012-gestion-administrativa/evidencia/README.md) |
| 013 — Ciclo de vida del ticket | Aceptación de transiciones e historial | [README.md](../../../../docs/spec/features/013-ciclo-vida-ticket/evidencia/README.md) |
| 014 — Ciclo de vida del catálogo | Aceptación de bajas lógicas e historiales | [README.md](../../../../docs/spec/features/014-ciclo-vida-catalogo/evidencia/README.md) |
| 017 — Provisionamiento y gobierno | Aceptación de invitaciones y roles SaaS | [README.md](../../../../docs/spec/features/017-provisionamiento-y-gobierno-de-identidades/evidencia/README.md) |
| 018 — Filtros de inventario | Aceptación de filtros server-side | [README.md](../../../../docs/spec/features/018-filtro-inventario-sede-departamento/evidencia/README.md) |
| 019 — Detalle de producto | Aceptación de lectura por alcance | [README.md](../../../../docs/spec/features/019-detalle-producto-por-alcance/evidencia/README.md) |
| 020 — Reabastecimiento y compras | Aceptación del flujo procure-to-stock | [README.md](../../../../docs/spec/features/020-reabastecimiento-compras/evidencia/README.md) |
| 021 — Cobertura automática | Aceptación de cobertura por OC | [README.md](../../../../docs/spec/features/021-cobertura-automatica-tickets-compras/evidencia/README.md) |
| 022 — Mantenimiento técnico I | Aceptación de limpieza sin cambio de conducta | [README.md](../../../../docs/spec/features/022-mantenimiento-tecnico/evidencia/README.md) |
| 023 — Refactor de `compra_service` | Aceptación de equivalencia contractual | [README.md](../../../../docs/spec/features/023-refactor-compra-service/evidencia/README.md) |
| 024 — Hardening operativo I | Aceptación de observabilidad, CORS y borde | [README.md](../../../../docs/spec/features/024-hardening-operativo/evidencia/README.md) |
| 025 — Límite de tasa distribuido | Aceptación del límite distribuido con Redis | [README.md](../../../../docs/spec/features/025-limite-tasa-distribuido/evidencia/README.md) |
| 026 — Salud del esquema BD | Aceptación de índices, unicidades y normalización | [README.md](../../../../docs/spec/features/026-salud-esquema-bd/evidencia/README.md) |

## Qué prueba cada evidencia

Por `AGENTS.md` §8.5, una feature está cerrada solo si:

1. `tasks.md` tiene todas sus casillas marcadas, incluidas las de "Cierre".
2. `spec.md` §6 tiene **cada AC marcado con su evidencia de verificación**.
3. Los tests están en verde.
4. La feature se recorrió en **los dos puertos** (4200 funcional, 8080 humo).

Cada `evidencia/README.md` registra los conteos de suites, los recorridos con
resultados observables y los casos de error verificados.

## Relación con los tests de código

La evidencia de aceptación **consume** los tests automáticos de esta misma
jerarquía (`../unitarios/`, `../integracion/`, `../sistema/`, `../humo/`); no los
reemplaza. Un AC puede cerrarse con evidencia manual (recorrido visual) o
automatizada (test verde), y la evidencia registra cuál de las dos se usó.
