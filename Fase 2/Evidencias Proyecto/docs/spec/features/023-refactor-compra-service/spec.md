# Feature 023: Mantenimiento técnico II — refactor incremental de `compra_service`

**Estado:** Cerrada (13/Nov/2026)
**Release:** 2.0 — Sprint 7 (mantenimiento transversal)
**Tipo:** Refactor estructural, sin valor de negocio directo
**Sucede a:** Feature 022 (mantenimiento técnico I, cerrada el 12/Nov/2026)

## 1. Problema

`backend/app/services/compra_service.py` concentra **1420 líneas** y once
responsabilidades distintas en un solo módulo:

| Bloque | Líneas aproximadas | Contenido |
|---|---:|---|
| Cabecera y helpers | 1–341 | errores HTTP, constantes, DTO de simulación, carga de OC, proyección de respuesta |
| Necesidades | 343–721 | `_simular_claves`, `institucion_de_compras`, consolidado por sede/producto |
| Preview de cobertura | 723–821 | simulación de una compra hipotética |
| Proveedores | 823–879 | catálogo global y réplica tenant |
| Órdenes de compra | 881–1156 | listado, alta, edición, emisión, factura y cancelación |
| Cobertura greedy | 1158–1231 | simulación todo-o-nada por pedido |
| Recepción | 1233–1420 | recepción ACID, stock, movimientos y desbloqueo de pedidos |

El módulo funciona y está cubierto por `test_compras.py`,
`test_cobertura_021.py`, `test_compras_endpoints_020.py` y los tests gated de
PostgreSQL 16. El costo es de mantenimiento:

1. **Lectura y revisión.** Un cambio en la recepción obliga a recorrer 1400
   líneas y a distinguir helpers de flujos.
2. **Riesgo de edición.** Las mismas opciones de carga de una OC
   (`joinedload`/`selectinload`) se repiten en `_cargar_orden` y en
   `listar_ordenes_compra`; la validación de sede, proveedor e ítems se repite
   en `crear_orden_compra` y `actualizar_orden_compra`.
3. **Frontera pública mezclada.** `compra_service` expone tanto la API que
   consumen los endpoints y `ticket_service` como helpers internos de simulación
   (`_simular_claves`), que hoy son una costura de test deliberada.

**Impacto:** ninguna regresión funcional conocida. El problema es de
mantenibilidad y de radio de cambio, no de correctitud.

## 2. Objetivo

Dividir `compra_service` en un **paquete interno con módulos cohesivos**,
conservando exactamente:

- la ruta de import `from app.services import compra_service`;
- los **14** símbolos públicos que consumen los endpoints, `ticket_service` y
  los tests;
- la costura `compra_service._simular_claves` y el DTO
  `SimulacionTicketProducto`;
- las firmas, los textos, los códigos HTTP, el orden de bloqueo, las
  transacciones y el contrato OpenAPI.

El refactor es **incremental y mecánico**: primero se mueve código sin
reescribirlo; después se eliminan dos duplicaciones internas con la suite en
verde.

## 3. Alcance

### 3.1 Dentro de alcance

| Tarea | Contenido |
|---|---|
| **T1** | Verificar la línea base, añadir el test de contrato estructural (rojo) y registrar la 023 en `roadmap.md`. |
| **T2** | Convertir `compra_service.py` en el paquete `compra_service/` con `_comun`, `necesidades`, `cobertura`, `proveedores`, `ordenes` y `recepcion`; `__init__.py` reexporta la API. Movimiento verbatim. |
| **T3** | Deduplicar las opciones de carga de OC (`_opciones_orden`) y la validación de alta/edición (`_validar_entrada_orden`), con la suite en verde. |
| **T4** | Cierre: suites, OpenAPI, diff protegido, recorrido 4200 / humo 8080, `stack.md`, evidencia, `MEMORY.md` y roadmap. |

### 3.2 Fuera de alcance

- Refactorizar `inventario_service`, `ticket_service`, `control_service`,
  `organizacion_service` o `dashboard_service`. Cada uno exige su propia spec.
- Cambiar cualquier regla de negocio, consulta, orden de bloqueo
  (`OC → producto → stock_sede`), transacción o `FOR UPDATE`.
- Cambiar rutas, métodos, `response_model`, matriz de permisos, textos visibles,
  códigos HTTP o DDL.
- Tocar `database/`, la versión `021.1`, las 27/24 tablas o la semilla.
- Cambiar el frontend, sus textos o sus tests.
- Añadir dependencias o usar SQL raw.
- Eliminar o renombrar `_simular_claves`, `SimulacionTicketProducto` o
  `orden_a_respuesta`.
- Reasignar 015/016 de sprint ni mover el Hito 2 (11/Dic/2026).

## 4. Decisiones de diseño

### D-1 — Paquete con fachada, no cambio de ruta de import

`backend/app/services/compra_service/` será un paquete y su `__init__.py` la
fachada. `from app.services import compra_service` sigue resolviendo al paquete,
y todos los nombres que hoy se usan fuera se reexportan. **Por qué:** evita
tocar endpoints, `ticket_service` y tests, y hace que el diff sea revisable como
un movimiento, no como una API nueva.

### D-2 — Mover primero, deduplicar después

T2 mueve bloques completos sin cambiar su cuerpo. T3 introduce
`_opciones_orden()` y `_validar_entrada_orden()` una vez que la suite ya
confirma que el movimiento fue neutro. **Por qué:** separa el riesgo de
transcripción del riesgo de refactor lógico y permite revertir una fase sin la
otra.

### D-3 — Módulos por caso de uso, no por entidad

| Módulo | Responsabilidad |
|---|---|
| `_comun.py` | errores, constantes, DTO de simulación, carga de OC, proyección y helpers compartidos |
| `necesidades.py` | `_simular_claves`, institución del actor y consolidado de necesidades |
| `cobertura.py` | preview de compra hipotética y cobertura greedy de pedidos |
| `proveedores.py` | catálogo global y réplica tenant |
| `ordenes.py` | listado, alta, edición, emisión, factura y cancelación |
| `recepcion.py` | recepción física ACID y desbloqueo de pedidos |

**Por qué:** cada módulo tiene una razón de cambio distinta y un conjunto
pequeño de dependencias. `calcular_cobertura_tickets` vive con el preview porque
ambos son simulaciones de cobertura; la recepción la consume.

### D-4 — `_comun` no importa módulos de flujo

El grafo queda sin ciclos:

```text
_comun  ←  necesidades  ←  cobertura  ←  recepcion
   ↑            ↑
   └── proveedores
   └── ordenes ─┘
```

`_comun` solo depende de modelos, schemas, `ambito_service` y
`auth_service`. Ningún módulo de flujo importa `compra_service` (la fachada),
sino sus hermanos concretos.

### D-5 — Sin cambios de comportamiento

Se conservan literalmente los textos de error, el orden de las consultas, los
`ORDER BY`, las condiciones de estado, los `commit`/`rollback`, los `flush` y
los valores de retorno. La suite existente es la caracterización de referencia;
el test nuevo solo fija la estructura y las firmas.

## 5. Criterios de aceptación

- [x] **AC-1 — Paquete y módulos cohesivos.** `backend/app/services/compra_service.py`
  ya no existe; existe `backend/app/services/compra_service/` con `__init__.py`,
  `_comun.py`, `necesidades.py`, `cobertura.py`, `proveedores.py`, `ordenes.py`
  y `recepcion.py`. `import app.services.compra_service` funciona y el paquete
  tiene `__path__`. **Evidencia:** `test_el_servicio_es_un_paquete_con_los_modulos_esperados`
  en verde y smoke de importación con `__file__` terminado en `__init__.py`.
- [x] **AC-2 — API pública intacta.** La fachada reexporta
  `institucion_de_compras`, `listar_necesidades_reabastecimiento`,
  `previsualizar_cobertura`, `listar_proveedores`, `crear_proveedor`,
  `listar_ordenes_compra`, `crear_orden_compra`, `actualizar_orden_compra`,
  `emitir_orden_compra`, `registrar_o_editar_factura`, `cancelar_orden_compra`,
  `calcular_cobertura_tickets`, `recepcionar_orden_compra`,
  `orden_a_respuesta`, `SimulacionTicketProducto` y `_simular_claves`.
  `ticket_service` y `test_cobertura_021.py` siguen usándolos sin cambios.
  **Evidencia:** `test_la_fachada_reexporta_la_api_publica` y `__all__` con 16 nombres;
  `test_cobertura_021.py` en verde.
- [x] **AC-3 — Firmas sin cambios.** Un test de contrato verifica los nombres de
  parámetros, los parámetros keyword-only (`estado`, `sede_id`) y los valores
  por defecto (`sede_id=None`, `producto_ids=None`, `cantidades_oc=None`,
  `bloquear=False`) de las 15 funciones. **Evidencia:**
  `test_las_firmas_publicas_y_el_dto_no_cambian`, con los 15 campos del DTO.
- [x] **AC-4 — Comportamiento sin regresiones.** `pytest` mantiene los **1499
  tests previos** en verde con **88 skipped** y añade los tests de contrato;
  `test_compras.py`, `test_cobertura_021.py` y
  `test_compras_endpoints_020.py` pasan completos. 0 fallos. **Evidencia:**
  **1502 passed/88 skipped/0 failed** y suites focalizadas **85 passed**.
- [x] **AC-5 — Duplicación interna eliminada.** `_opciones_orden()` es la única
  definición de las opciones de carga de una OC y la usan `_cargar_orden` y
  `listar_ordenes_compra`; `_validar_entrada_orden()` es la única validación de
  sede/proveedor/ítems y la usan `crear_orden_compra` y
  `actualizar_orden_compra`. **Evidencia:** grep sin copias locales de
  `joinedload(OrdenCompra.proveedor)` ni de la validación `sede → proveedor →
  ítems → réplica`.
- [x] **AC-6 — Contrato y áreas protegidas intactos.** Se conservan las **73**
  operaciones de negocio, las **75** de `/openapi.json`, la versión `021.1`, las
  27/24 tablas y la matriz de permisos. `database/`, `backend/app/models/`,
  `backend/app/core/permisos.py`, templates y `.env` no cambian. **Evidencia:**
  conteos verificados en vivo y `git status`/`git diff` vacíos en esas rutas.
- [x] **AC-7 — Documentación coherente.** `stack.md` documenta el patrón de
  paquete con fachada para servicios grandes; `roadmap.md` registra la 023;
  `MEMORY.md` recoge estado y decisiones; el `grep` de coherencia sobre
  `AGENTS.md`, `MEMORY.md` y `.agents/skills/` no deja referencias obsoletas.
  **Evidencia:** nota nueva en `stack.md`, roadmap en `[x]` el 13/Nov/2026 y
  `MEMORY.md` actualizado; `grep` de coherencia ejecutado.
- [x] **AC-8 — Cierre en los dos puertos.** `ng test` mantiene **549 SUCCESS** y
  `ng build` termina limpio; el recorrido funcional en **4200** (compras:
  necesidades, órdenes y recepción) y el humo en **8080** no muestran errores
  nuevos de consola. Al ser un cambio de backend, 8080 reutiliza el frontend ya
  construido y verifica la API nueva. **Evidencia:** `OC-2026-000002` con
  `F-023-0001` y `OC-2026-000003` con `F-023-0002` recepcionada por el Bodeguero;
  movimiento `ENTRADA` de 10 y stock 45 verificados en PostgreSQL; humo 8080 en
  `/compras` y `/compras/necesidades`.

## 6. Restricciones

- `AGENTS.md` §7: no se instalan paquetes nuevos.
- `AGENTS.md` §8: código solo después de `spec.md` y `plan.md` aprobados.
- `AGENTS.md` §8.5–§8.7: cierre es verificación, no marcado; 4200 y 8080.
- `constitucion.md`: consistencia transaccional y trazabilidad absoluta no se
  tocan.
- Los textos de error visibles son contrato de UI: se conservan literalmente.
- `backend/.dockerignore` excluye `tests/`; los tests se ejecutan desde el host.
- El refactor no cambia el comportamiento observable ni el DDL.

## 7. Riesgos y mitigación

| Riesgo | Probabilidad | Mitigación |
|---|---|---|
| Ciclo de imports al dividir | Media | Grafo acíclico D-4; smoke de importación y suite completa. |
| Deriva de comportamiento al mover código | Media | Movimiento verbatim en T2; suites focalizadas antes y después. |
| Confusión `compra_service.py` ↔ `compra_service/` | Baja | Borrar el archivo y su `__pycache__` en la misma tarea; verificar `__path__`. |
| Perder un símbolo público | Baja | Test de contrato con la lista completa y las firmas. |
| Cambiar sin querer un texto o un `ORDER BY` | Baja | `git diff` por bloques y tests existentes de textos/orden. |
| Introducir una regresión solo en PostgreSQL | Baja | Los tests gated siguen disponibles; no se toca SQL ni bloqueos. |

## 8. Evidencia de verificación

Completada en T4. La evidencia vive en
[`evidencia/README.md`](evidencia/README.md) y registra las suites, el contrato
OpenAPI, el diff protegido, el recorrido funcional en 4200 y el humo en 8080.
Resultado: `pytest` **1502 passed/88 skipped/0 failed**, `ng test` **549
SUCCESS**, `ng build` limpio, **73/75** operaciones, versión `021.1`, tablas
**27/24** y recorrido completo de compras con recepción real del Bodeguero.
