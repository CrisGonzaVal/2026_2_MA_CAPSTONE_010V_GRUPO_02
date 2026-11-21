# `backend/tests/` — organización por tipo de prueba

Los tests se clasifican por **tipo de prueba**, no por módulo ni por feature.
Cada subcarpeta corresponde a una categoría de la taxonomía estándar:

- **Funcionales**: verifican que el sistema hace lo que debe (unitarias,
  integración, sistema, E2E, aceptación, humo).
- **No funcionales**: verifican atributos de calidad (rendimiento, seguridad,
  carga/estrés, escalabilidad, usabilidad, compatibilidad).

> **`no_funcional` va con guion bajo, no con guion.** Python no permite importar
> paquetes cuyo nombre lleve guion, y la suite usa imports absolutos entre
> carpetas (`from tests.no_funcional.seguridad... import ...`). El guion bajo es
> obligatorio para que pytest resuelva los paquetes; el término visible sigue
> siendo «no funcional».

## Árbol

```
backend/tests/
├── conftest.py                    # fixtures compartidas (BD, sesión, Clerk)
├── funcional/
│   ├── unitarios/                 # lógica pura, DTOs, estructura, modelos
│   ├── integracion/               # endpoints + servicios + BD en SQLite
│   ├── sistema/                   # flujos completos contra PostgreSQL real
│   ├── e2e/                       # recorridos completos de usuario
│   ├── aceptacion/                # índice de evidencia de aceptación (README)
│   └── humo/                      # chequeo rápido health/ready
└── no_funcional/
    ├── rendimiento/               # límite de tasa, métricas, observabilidad
    ├── seguridad/                 # auth, permisos, CORS, aislamiento tenant
    ├── carga_estres/              # (pendiente: locust/k6)
    ├── escalabilidad/             # (pendiente: réplicas, particionado)
    ├── usabilidad/                # (pendiente: accesibilidad, contraste)
    └── compatibilidad/            # (pendiente: navegadores, dispositivos)
```

## Cómo correr cada grupo

| Comando | Alcance |
|---|---|
| `pytest` | Todo (SQLite en memoria por defecto) |
| `pytest tests/funcional/unitarios` | Solo unitarios (rápido, sin red) |
| `pytest tests/funcional/integracion` | Solo integración |
| `pytest tests/funcional/sistema` | Solo los *gated* de PostgreSQL |
| `pytest tests/funcional/e2e` | Solo recorridos completos |
| `pytest tests/funcional/humo` | Solo el chequeo rápido |
| `pytest tests/no_funcional/rendimiento` | Solo rendimiento y métricas |
| `pytest tests/no_funcional/seguridad` | Solo controles de seguridad |

## Suites *gated* (dependen del entorno)

Los tests de `funcional/sistema/` y `no_funcional/rendimiento/` que dependen de
infraestructura real se activan con variables de entorno:

```powershell
$env:POSTGRES_TEST_URL = "postgresql://postgres:postgres@localhost:5433/postgres"
$env:REDIS_TEST_URL    = "redis://127.0.0.1:6380/15"
```

Sin esas variables, los tests correspondientes se **omiten** (skipped) y la suite
restante corre sobre SQLite en memoria. Los *gated* de PostgreSQL crean bases
temporarias desechables y nunca tocan `apt_erp`; los de Redis vacían la base 15
al empezar y al terminar y nunca tocan la base 0.

## Convenciones

- Los módulos de apoyo compartidos (`_soporte_*.py`, `soporte_*.py`) viven en
  `funcional/integracion/` y se importan **por ruta absoluta**
  (`from tests.funcional.integracion._soporte_sede_011 import ...`), de modo que
  el destino de un test no rompe a sus consumidores. La única excepción es
  `no_funcional/rendimiento/soporte_limite_tasa_025.py`, que solo consumen los
  tests de límite de tasa y por eso se queda junto a ellos.
- Los tests se nombran `test_<que_se_prueba>_<NNN>.py`, donde `NNN` es la
  feature que los originó.
- Un archivo de test solo entra en una carpeta. Si un test sirve a dos tipos, se
  clasifica por su **propósito predominante** y se documenta el cruce en la
  evidencia de la feature.

## Reorganización del 20/Nov/2026

Antes de esta fecha la suite estaba organizada por **módulo de código**
(`tests/api/`, `tests/models/`, `tests/schemas/`, `tests/services/` y la raíz de
`tests/`), no por tipo de prueba. La reclasificación no cambió ninguna prueba:
solo su ubicación, sus imports (que pasaron de relativos a absolutos) y los
anclajes de ruta (`Path(__file__).resolve().parents[N]`).

Mapa de la organización anterior a la actual:

| Antes | Ahora |
|---|---|
| `tests/api/test_*.py` (mayoría) | `tests/funcional/integracion/` |
| `tests/api/test_smoke.py`, `test_salud_024.py` | `tests/funcional/humo/` |
| `tests/api/test_ciclo_vida_flujo_013.py`, `test_despacho_transaccional.py`, `test_transaccion_ticket.py` | `tests/funcional/e2e/` |
| `tests/api/test_permisos*.py`, `test_auth*.py`, `test_cors_024.py`, `test_correlacion_024.py`, `test_aislamiento_tenant_010.py`, `test_institucion_inactiva_012.py`, `test_capacidades_gating_012.py`, `test_gating_capacidades_endpoints_012.py` | `tests/no_funcional/seguridad/` |
| `tests/api/test_limite_tasa*.py`, `test_metricas*.py` | `tests/no_funcional/rendimiento/` |
| `tests/models/`, `tests/schemas/` | `tests/funcional/unitarios/` |
| `tests/services/` | `tests/funcional/integracion/` (salvo `test_compra_service_estructura.py`, que va a `unitarios/`) |
| `tests/test_*.py` con `postgres` | `tests/funcional/sistema/` |
| `tests/test_*.py` restantes | `tests/funcional/unitarios/` o `tests/funcional/integracion/` |

Los conteos no cambiaron: **1667 passed / 105 skipped** sin variables gated y
**1772 passed** con PostgreSQL y Redis activos.

