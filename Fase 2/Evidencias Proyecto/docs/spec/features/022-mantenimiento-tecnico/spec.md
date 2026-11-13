# Feature 022: Mantenimiento técnico I — limpieza y deduplicación

**Estado:** Aprobada para implementación
**Release:** 2.0 — Sprint 7 (mantenimiento transversal)
**Tipo:** Saneamiento técnico, sin valor de negocio directo
**Antecede a:** Feature 023 (refactor incremental de `compra_service`, fuera de esta spec)

## 1. Problema

El proyecto arrastra deuda de mantenimiento que no rompe la funcionalidad, pero
degrada la lectura del repositorio y la confianza en `docs/spec/` como fuente
única de verdad:

1. **Código muerto confirmado.** `frontend/src/app/features/administracion/services/usuario.service.ts`
   (32 líneas, 4 métodos HTTP) quedó sustituido por `administracion.service.ts`
   en la Feature 012. Hoy tiene **cero imports**: solo se referencia a sí mismo.
2. **Documentación desalineada con el código.**
   - `docs/spec/stack.md` sigue citando `usuario.service.ts` y `src/assets/`,
     pero Angular usa `"input": "public"` en `angular.json`.
   - La Nota 1 de `stack.md` habla de una «cuarta feature» y omite `compras/` y
     `control/`; la Nota 2 afirma que `shared/components/` está vacío cuando ya
     existe y se usa, y menciona `shared/pipes/`, que no existe.
   - `AGENTS.md` §4 describe `src/app/shared/` como `(components, interfaces, pipes)`
     y cita `src/assets/`; la realidad es `(components, config, interfaces, utils)`
     y `public/`.
   - `README.md` raíz dice 20 tablas de `control`, 17 por tenant y versión
     `013.1`; la base consolidada es 27/24 y `021.1`.
   - `frontend/README.md` es el boilerplate de Angular CLI y no describe el
     proyecto ni la diferencia entre 4200 y 8080.
3. **Duplicación mecánica en el frontend.** Los seis helpers `mensajeDeError*`
   (`administracion`, `compras`, `control`, `catalogo`, `producto`, `tickets`)
   repiten exactamente la misma estructura: leer `detail`, devolverlo si es
   texto y, si no, mapear el código HTTP. Solo cambian los textos de cada dominio.
4. **Duplicación mecánica en el backend.** `_correo_actor` es idéntica en
   `organizacion_service.py` y `usuario_service.py` (6 líneas cada una).
5. **Ruido de mantenimiento.** El repo no tiene basura versionada, pero el
   inventario local incluye cachés regenerables (`frontend/.angular`, `dist`,
   `.pytest_cache`, `devserver.log`). No forman parte de esta feature porque no
   están en git.

**Impacto:** ninguna regresión funcional conocida. El costo es de mantenimiento:
un archivo muerto que parece vivo, documentos que contradicen el código y seis
copias de una misma regla de presentación de errores.

## 2. Objetivo

Dejar el repositorio coherente y sin duplicación mecánica, **sin cambiar el
comportamiento observable**:

- eliminar el único archivo TypeScript muerto confirmado;
- alinear `AGENTS.md`, `stack.md` y los README con la estructura y la base reales;
- centralizar la estructura de los seis helpers de error HTTP conservando
  nombres, firmas y textos literales;
- unificar `_correo_actor` en `auth_service.correo_del_actor`;
- cerrar con la misma línea base de tests, contrato OpenAPI, DDL y permisos.

## 3. Alcance

### 3.1 Dentro de alcance

| Tarea | Contenido |
|---|---|
| **T1** | Verificar la línea base y registrar la feature en `roadmap.md`. |
| **T2** | Borrar `usuario.service.ts` y corregir su referencia en `stack.md`. |
| **T3** | Coherencia documental: `AGENTS.md`, `stack.md`, `README.md` raíz y `frontend/README.md`. |
| **T4** | Crear `shared/utils/errores-http.ts` y hacer que los seis `mensajeDeError*` deleguen en él, con tests primero. |
| **T5** | Mover `_correo_actor` a `auth_service.correo_del_actor`, usarlo en `organizacion_service` y `usuario_service`, con test unitario primero. |
| **T6** | Cierre: evidencia, `MEMORY.md`, suites, OpenAPI, build y recorrido 4200/8080. |

### 3.2 Fuera de alcance

- Dividir `compra_service`, `inventario_service`, `ticket_service` o
  `control_service`. Ese trabajo pertenece a la Feature 023 y posteriores.
- Dividir componentes Angular grandes (`inventario`, `ticket-detalle`,
  `usuarios`, `tickets`) o `app.component`.
- Escribir tests de caracterización para el futuro refactor de servicios.
- Borrar las cuatro interfaces sin uso de `shared/interfaces/index.ts`
  (`CapacidadFuncional`, `CapacidadActualizar`, `AsignacionSedeCrear`,
  `EncargadoCrear`); se revisan en 015/016.
- Cambiar DDL, semilla, versión `021.1`, número de tablas, matriz de permisos,
  capacidades, rutas, contratos de API, `response_model` o textos visibles.
- Cambiar el orden de bloqueo `categoria → producto → stock_sede`, los
  `FOR UPDATE` o la transacción única de los flujos ACID.
- Reasignar 015/016 de sprint. El usuario indicó que «probablemente» pasan a otro
  sprint, pero no es una decisión confirmada; esta feature no altera su estado.
- Borrar evidencias PNG, helpers `_soporte_*.py`, `_historial_legados()` /
  `_historial_nuevos()` ni `backend/.env.example`.
- Limpiar cachés locales (`frontend/.angular`, `frontend/dist`, `.pytest_cache`):
  son artefactos ignorados y regenerables, no parte del cambio versionado.

## 4. Decisiones de diseño

### D-1 — Refactor incremental, no reescritura

La arquitectura por capas (`api`, `services`, `models`, `schemas`) es adecuada.
El problema de los cuatro servicios grandes es de **funciones largas**, no de
correctitud, y exige su propia spec. Mezclarlo con limpieza produciría un diff
irrevisable y un riesgo desproporcionado para el cierre del Hito 2.

### D-2 — Un helper genérico para los errores HTTP

`mensajeDeErrorHttp(error, mensajes)` concentra la lectura de `detail`, el caso
`status === 0` y el fallback. Cada helper de dominio aporta solo sus textos y su
mensaje predeterminado. La API pública de los seis helpers no cambia.

**Por qué:** los seis helpers tienen la misma estructura y los textos son
contractuales para la UI. Centralizar la estructura reduce seis copias a una sin
tocar el contrato visible.

### D-3 — `correo_del_actor` vive en `auth_service`

`auth_service` ya importa `security` y define `IdentidadAutenticada`; además es
la frontera natural de identidad. `organizacion_service` y `usuario_service` ya
importan de él, así que no se crea un ciclo nuevo.

### D-4 — La documentación se corrige contra el código, no al revés

`AGENTS.md` y `stack.md` son norma, pero describen estructura. Cuando la norma y
el código divergen en un hecho verificable (carpeta `public/`, features
existentes, tablas, versión), se corrige el documento. No se renombra código para
que coincida con un árbol obsoleto.

### D-5 — No se tocan las interfaces sin uso

Las cuatro interfaces podrían ser contrato de las Features 015/016. Borrarlas
ahora sería una decisión de producto, no de limpieza. Se dejan intactas.

## 5. Criterios de aceptación

- [x] **AC-1 — Código muerto eliminado.** `frontend/src/app/features/administracion/services/usuario.service.ts`
  ya no existe y `grep -r "UsuarioService\|usuario.service" frontend/src` devuelve
  0 resultados.
  **Evidencia (12/Nov/2026):** archivo eliminado; `Select-String` sobre `frontend/src`
  con 0 coincidencias; `ng build` limpio.
- [x] **AC-2 — `AGENTS.md` y `stack.md` describen la estructura real.**
  `AGENTS.md` cita `public/` y `shared/` como `(components, config, interfaces,
  utils)`; `stack.md` ya no cita `src/assets/` ni `usuario.service.ts`, lista las
  seis features de negocio (`dashboard`, `inventario`, `tickets`,
  `administracion`, `compras`, `control`) y sus notas describen
  `shared/components/` existente y `shared/pipes/` inexistente.
  **Evidencia:** árbol de `stack.md` con `public/`, `shared/{components,config,interfaces,utils}`
  y las seis features; `grep` sin `src/assets`, `usuario.service.ts` ni «cuarta feature»
  en las secciones vigentes.
- [x] **AC-3 — README raíz actualizado.** Refleja **27** tablas de `control`,
  **24** tablas por tenant y versión **`021.1`**; no quedan `20`, `17` ni
  `013.1` como descripción de la base.
  **Evidencia:** `README.md` líneas 36 y 41 con 27/24 y `021.1`; listado de módulos
  ampliado con «Compras y control SaaS».
- [x] **AC-4 — Dedup frontend sin cambio de textos.** Los seis helpers
  `mensajeDeError*` conservan nombre, firma y cada texto literal; solo delegan la
  estructura común en `shared/utils/errores-http.ts`. Un test cubre `detail`
  textual, `detail` no textual (lista de Pydantic), los códigos mapeados, el
  status `0` y el fallback.
  **Evidencia:** `errores-http.spec.ts` con **12** specs; rojo inicial por módulo
  ausente y después **549 SUCCESS** (537 previos + 12); `ng build` limpio.
- [x] **AC-5 — Dedup backend.** `_correo_actor` ya no existe duplicado;
  `auth_service.correo_del_actor` es la única implementación y se usa en
  `organizacion_service` y `usuario_service`. Un test unitario cubre identidad
  ausente, usuario ausente y normalización de correo.
  **Evidencia:** `test_auth_service.py` con **3 passed**; 0 referencias a
  `_correo_actor`; `correo_del_actor` usado en 2 llamadas de `organizacion_service`
  y 3 de `usuario_service`; suite completa **1499 passed/88 skipped**.
- [x] **AC-6 — Contrato y datos intactos.** Se conservan las **73 operaciones
  de negocio** de la matriz de permisos (`backend/app/core/permisos.py`);
  `/openapi.json` sigue exponiendo **75** operaciones al contar `/` y `/health`,
  que viven fuera de `/api/v1`. `database/`, la versión `021.1`, las 27/24 tablas
  y los textos de UI no cambian.
  **Evidencia:** `MATRIZ_PERMISOS` = 73 y `/openapi.json` en vivo = 75;
  `git diff --name-only` sin cambios en `database/`, `permisos.py`, `models/`,
  templates ni `.env`.
- [x] **AC-7 — Suites sin regresiones.** `pytest` mantiene los **1496 tests
  previos** en verde con **88 skipped** y añade los tests del helper; `ng test`
  mantiene los **537 tests previos** en verde y añade los del helper; 0 fallos en
  ambas suites.
  **Evidencia:** backend **1499 passed, 88 skipped, 0 failed** (1496 + 3);
  frontend **549 SUCCESS** (537 + 12).
- [x] **AC-8 — Build y recorrido.** `ng build` termina limpio; el recorrido
  funcional en **4200** y el humo en **8080** (tras reconstruir la imagen) no
  muestran errores de consola ni cambios visibles.
  **Evidencia:** build de producción limpio; recorrido 4200 como
  `admin020.test+clerk_test@example.com` por dashboard, inventario, detalle de
  producto, pedidos, detalle de pedido, necesidades y órdenes de compra; humo 8080
  con la imagen reconstruida por dashboard, inventario y necesidades. Consola sin
  errores nuevos: solo el aviso preexistente de Clerk en claves de desarrollo.
- [x] **AC-9 — Roadmap coherente.** La Feature 022 figura en el índice con su
  estado real; 015/016 conservan su sprint y el Hito 2 sigue en el 11/Dic/2026.
  **Evidencia:** fila de 022 en `[x]` y lista del Sprint 7 en `[x]` con fecha
  12/Nov/2026; 015/016 y «Hito 2 (11/Dic/2026)» sin cambios.

## 6. Restricciones

- `AGENTS.md` §7: no se instalan paquetes nuevos.
- `AGENTS.md` §8: código solo después de `spec.md` y `plan.md` aprobados.
- `AGENTS.md` §8.5–§8.7: cierre es verificación, no marcado; 4200 y 8080.
- `constitucion.md`: consistencia transaccional y trazabilidad absoluta no se
  tocan.
- Los textos de error visibles son contrato de UI: se copian literalmente.
- `backend/.dockerignore` excluye `tests/`; los tests se ejecutan desde el host.

## 7. Riesgos y mitigación

| Riesgo | Probabilidad | Mitigación |
|---|---|---|
| Cambiar sin querer un texto de error visible | Media | Test que compara los seis helpers contra los textos actuales. |
| Crear un ciclo de imports al mover `_correo_actor` | Baja | `auth_service` no importa `organizacion_service` ni `usuario_service`; verificar suite completa. |
| Romper un import por borrar `usuario.service.ts` | Muy baja | `grep` global antes y después; `ng build`. |
| Actualizar documentación con cifras equivocadas | Baja | Contrastar con `database/01_esquema.sql`, `AGENTS.md` §4 y `MEMORY.md`. |
| Confundir el estado de 015/016 | Media | No modificar sus filas ni el Hito 2; dejar 022 como mantenimiento. |

## 8. Evidencia de verificación

La evidencia completa está en
[`evidencia/README.md`](evidencia/README.md): suites, build, OpenAPI,
`git diff --stat`, recorrido 4200 y humo 8080. Resumen: backend **1499
passed/88 skipped**, frontend **549 SUCCESS**, build limpio, 73 operaciones de
negocio / 75 OpenAPI y consola sin errores nuevos en ambos puertos.
