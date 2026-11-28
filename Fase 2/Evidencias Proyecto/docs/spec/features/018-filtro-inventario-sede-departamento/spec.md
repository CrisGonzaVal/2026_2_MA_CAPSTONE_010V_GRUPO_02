# Feature 018: Filtros de existencias por sede y departamento

**Estado:** Cerrada (21/Oct/2026). **Enmienda post-cierre del 27/Nov/2026 — checkbox «Solo con stock» (§11): cerrada el 27/Nov/2026 (T14/T15).**  
**Release:** 2.0 — backlog posterior al Sprint 6  
**Tipo:** Mejora de consulta de inventario

## 1. Problema

La pestaña «Existencias» de `/inventario` muestra el catálogo y el stock agregado del ámbito permitido, pero no permite filtrar por sede. El Administrador Institucional necesita acotar la lectura a una sede; el Bodeguero necesita seleccionar un departamento de su sede para confirmar/acotar la vista a esa ubicación física.

El stock operativo tiene granularidad por sede, nunca por departamento. El filtro departamental existente resuelve la sede asignada, pero además hace que desaparezcan de la respuesta los productos sin fila de stock para esa sede. Para el Bodeguero, elegir un departamento de su sede no particiona ni atribuye el saldo: solo confirma/acota la consulta a su sede y oculta productos sin saldo allí. El backend actual no acepta todavía `sede_id`, y el Bodeguero no puede consultar las lecturas organizacionales existentes para obtener opciones de selector. La franja actual de indicadores resume el catálogo cargado, por lo que deberá corresponder al resultado de la sede cuando se filtre por sede.

## 2. Objetivo

Permitir al Administrador filtrar existencias por sede y departamento, y al Bodeguero seleccionar un departamento de su sede con una explicación visible de que el stock sigue siendo compartido por la sede. Añadir las opciones mínimas de ámbito necesarias para los selectores y el filtro `sede_id`, manteniendo el stock por sede, los límites server-side y resultados, criticidad e indicadores coherentes con el ámbito seleccionado.

## 3. Actores

- **Administrador Institucional:** puede consultar la lectura de ámbito y recibe sedes/departamentos activos de su institución; puede filtrar existencias por `sede_id` o `departamento_id` dentro de la institución.
- **Bodeguero / Encargado de Suministros:** puede consultar la lectura de ámbito y recibe únicamente su sede asignada y sus departamentos activos; no puede seleccionar otra sede. Puede seleccionar un departamento de su sede, con la nota visible de D-3; la API sigue limitando las existencias a su sede.
- **Solicitante (Funcionario):** conserva la lectura de existencias actualmente permitida, pero no recibe la nueva lectura de ámbito ni ve los nuevos selectores.
- **Superadmin:** no puede consultar existencias ni la nueva lectura de ámbito; ambas solicitudes responden 403.

## 4. Alcance

### Dentro

- Selectores de sede y departamento en la pestaña «Existencias» para Administrador; para Bodeguero se muestra solo selector de departamento, limitado a su sede.
- Parámetro aditivo `sede_id` en `GET /inventario/existencias`, combinable con el parámetro existente `departamento_id`.
- Operación nueva de lectura mínima de ámbito para Administrador y Bodeguero, con semántica definida en D-6 y §7.
- Opciones de selector con asociaciones departamento→sede para filtrar departamentos al elegir sede.
- Comportamiento explícito para departamentos sin sede, sedes/departamentos inactivos y Bodeguero sin sede.
- Combinación de filtros organizacionales con búsqueda por texto, categoría, criticidad y «Limpiar filtros».
- Pruebas `pytest` SQLite y gated PostgreSQL 16, pruebas de Angular, contrato OpenAPI y recorridos 4200/8080 reconstruido.

### Fuera

- Crear, modificar o exponer saldo por departamento; `stock_sede` sigue siendo la fuente única del saldo operativo.
- Agrupar productos en secciones por sede o departamento, o presentar el saldo como perteneciente en exclusiva a un departamento.
- Cambiar tickets, consumo, movimientos, despacho o autenticación Clerk.
- Cambiar el permiso/roles de cualquier operación existente o retirar una operación de la matriz. La lectura de ámbito nueva y el parámetro `sede_id` de existencias son aditivos.
- Cambiar el modelo de datos o añadir paquetes.

## 5. Decisiones

### D-1 — Selectores, no agrupación

La lista permanece en su presentación actual y se acota mediante desplegables. No se crean secciones ni subtotales de agrupación.

**Por qué:** la necesidad es filtrar la consulta; la agrupación visual podría sugerir saldos independientes que el modelo no posee.

### D-2 — Departamento significa sede asignada

`departamento_id` identifica una sede a consultar, no una partición de stock departamental. Varios departamentos de una sede resuelven el mismo stock físico. Debido al contrato actual del filtro departamental, solo aparecen productos con fila de stock en esa sede; productos sin saldo en ella desaparecen de la respuesta.

**Por qué:** desde la Feature 011 la granularidad del stock es `(sede, producto)`. El filtro departamental sirve para seleccionar la ubicación física asociada y no representa consumo o posesión departamental.

### D-3 — Nota obligatoria para el selector de Bodeguero

El Bodeguero conserva el selector de departamento, limitado a departamentos de su sede, y no se renderiza para él un selector de sede. Junto al selector se presenta literalmente la nota: **«El stock es compartido por la sede. Elegir un departamento no divide ni cambia el saldo; solo muestra productos con stock en esta sede.»**

La selección departamental no particiona el saldo ni modifica su valor: limita el resultado a productos con existencia registrada en la sede del departamento, ocultando productos que no tengan fila de stock en esa sede. Los departamentos de una sede común dan el mismo resultado de stock.

**Por qué:** la selección responde a la necesidad de explorar por departamento sin afirmar una granularidad inexistente; la nota previene una interpretación financiera/operativa falsa del saldo compartido.

### D-4 — Interacción entre sede y departamento

En la vista del Administrador, elegir sede acota las opciones de departamento a los departamentos activos asociados con esa sede. Si cambia la sede, una selección departamental incompatible se limpia y no se envía. La interfaz no permite una combinación de `sede_id` y `departamento_id` que se asocien a sedes distintas. Si ambos filtros son coherentes, se envían juntos; el backend aplica ambos. El Bodeguero no tiene selector de sede y sus opciones departamentales ya están restringidas a la sede asignada.

**Por qué:** evita consultas incoherentes y garantiza que la UI no dependa de una respuesta accidentalmente vacía para corregir sus selecciones.

### D-5 — Opciones vigentes y departamentos sin sede

La lectura de ámbito y los selectores ofrecen únicamente sedes activas y departamentos activos con sede asignada. Los departamentos activos sin sede no aparecen como opciones; la vista no ofrece un filtro que no pueda resolverse a una ubicación física. Una sede inactiva puede seguir siendo indicada manualmente al endpoint por un cliente autorizado y el servidor aplica `sede_id` a sus existencias; que la UI la omita no altera el contrato del backend.

**Por qué:** las opciones son para filtrar inventario operativo vigente. La nulabilidad de `departamento.sede_id` permite estados organizacionales incompletos, no una sede implícita. El filtrado API sigue siendo independiente de la disponibilidad del selector.

### D-6 — Lectura mínima de ámbito y permiso aditivo

Se añade una sola operación GET de solo lectura para `Administrador` y `Bodeguero`, gateada por la capacidad institucional `inventario`. Su respuesta contiene únicamente opciones para filtrar: sedes con `sede_id` y nombre, y departamentos con `departamento_id`, nombre y el `sede_id` asociado (para que la UI pueda acotar departamentos sin consultar `/organizacion/departamentos`). Solo incluye filas activas y departamentos con sede asignada.

Para Administrador, la operación devuelve las sedes y departamentos elegibles de su institución. Para Bodeguero con sede asignada, devuelve exclusivamente su sede y departamentos de esa sede. Para Bodeguero sin sede asignada, responde **409 Conflict** con error claro; no ofrece un ámbito alternativo ni una sede por defecto. No incluye usuarios, tickets, existencias, stock, saldos agregados ni registros de otra institución/sede. La ruta exacta y el nombre concreto del DTO se deciden en `plan.md`.

La nueva operación solo abastece filtros y no sustituye autorización de `GET /inventario/existencias`. La entrada de permisos de lectura de ámbito es aditiva: `GET` de la nueva ruta, roles Administrador+Bodeguero; ninguna operación existente cambia sus roles o se retira. El gating de `inventario` se evalúa además de la matriz.

**Por qué:** Bodeguero no tiene acceso a lecturas administrativas y su sesión no incluye `sede_id`. Un contrato mínimo específico aporta opciones seguras sin abrir otras lecturas ni datos de negocio. El gating conserva la disponibilidad funcional por institución vigente para el inventario.

### D-7 — Contrato de existencias aditivo y agregados coherentes

Se añade `sede_id` como parámetro opcional a `GET /inventario/existencias`; no cambia el modelo de respuesta. Sin `sede_id` **ni** `departamento_id`, `stock_total`, `es_critico` y los indicadores representan el ámbito completo permitido por rol (todas las sedes de la institución para Administrador; la sede asignada para Bodeguero y Solicitante). Con `sede_id` válido, la respuesta contiene solo esa sede y los productos de ella; `stock_total` equivale al saldo de la sede, `es_critico` se calcula sobre ese saldo y la franja de indicadores se recalcula desde esos resultados. El indicador de productos sin stock/stock crítico se interpreta, respectivamente, dentro del resultado cargado, no como total institucional oculto por el filtro. Un filtro `departamento_id` sin `sede_id` acota también a la sede del departamento.

Para `departamento_id`, se conserva la semántica existente: valida institución; otro departamento de la misma institución pero de otra sede, un departamento inexistente o uno sin sede producen **200 con lista vacía**; un departamento de otra institución produce **403**. El `outerjoin` se restringe a la sede y el endpoint omite productos sin fila de stock cuando se especifica departamento. Si se combina con `sede_id`, el departamento debe pertenecer a esa sede; un par incoherente responde **200 con lista vacía** en servidor, aunque la interfaz evita enviarlo.

Un `sede_id` existente en el ámbito institucional del actor filtra por esa sede. Un `sede_id` que no existe en el esquema/ámbito del actor responde **200 con lista vacía**: entre esquemas tenant separados el servidor no distingue el identificador ajeno de uno inexistente. Esto no supera el 404 del AC-3 de Feature 011: allí se consulta un recurso (`GET /inventario/stock?sede_id=…`) y aquí se aplica un parámetro de filtro a una lista. Para Bodeguero, un `sede_id` distinto de su sede asignada responde **200 con lista vacía** por la intersección con su alcance de stock. Para Solicitante, su propia sede filtra normalmente; una sede distinta de la sede de su departamento responde **200 con lista vacía** por la misma intersección de ámbito. Sin filtro `sede_id` ni `departamento_id`, los productos de catálogo sin saldo permanecen visibles con `sedes: []`, `stock_total: 0` y criticidad calculada conforme a la regla vigente. La capacidad `inventario` apagada deniega la consulta con **403**.

**Por qué:** el stock y la criticidad son propios de la sede consultada; los totales y las tarjetas resumen deben describir la misma lista filtrada. El contrato explícito de códigos evita ocultar con semánticas inconsistentes los identificadores inválidos o fuera de ámbito.

### D-8 — Visibilidad por capacidad de rol

La interfaz decide visibilidad mediante un helper `puede*` de rol en `frontend/src/app/core/auth/roles.ts`, con pruebas propias. Administrador y Bodeguero ven filtros apropiados; Solicitante y Superadmin no los ven. Este helper es solo presentación: la API mantiene autorización y gating.

**Por qué:** mantiene una fuente central de reglas de visibilidad de UI y el patrón probado por las capacidades existentes, sin duplicar condiciones de rol en plantillas.

## 6. Reglas del flujo

1. Clerk autentica y el servidor resuelve el tenant. El cliente no selecciona institución ni esquema.
2. La lectura de ámbito ofrece al Administrador opciones activas de su institución y al Bodeguero solo su sede activa y departamentos activos de ella. Sin sede asignada para Bodeguero, responde 409 y la UI informa que no tiene sede asignada y deja los filtros organizacionales/listado de existencias en estado no disponible; no inventa una sede.
3. Administrador puede filtrar por sede, departamento o ambos coherentes. Cambiar sede acota departamentos y limpia uno incompatible. Bodeguero no ve selector de sede, ve selector departamental y la nota literal de D-3.
4. `sede_id` filtra la respuesta al saldo de esa sede; totales, criticidad y franja de indicadores corresponden a esa misma respuesta. Sin `sede_id` ni `departamento_id`, se mantiene el agregado permitido por rol.
5. `departamento_id` selecciona la sede del departamento, pero no separa stock departamental. Productos sin fila de stock en la sede se omiten. Departamentos distintos de una sede común generan el mismo saldo.
6. Texto, categoría y críticos se combinan con los filtros organizacionales. «Limpiar filtros» restablece todos los filtros visibles y recupera el agregado permitido por rol.
7. Sin filtros organizacionales, productos sin saldo aparecen en cero con `sedes: []`. Con `sede_id` o `departamento_id`, los productos sin fila de saldo en la sede filtrada desaparecen; si no quedan filas, la vista indica «Ningún insumo coincide con los filtros aplicados», no «El catálogo no tiene insumos cargados».
8. Sede/departamento de otra institución no se incluyen en opciones. La API aplica los códigos y ámbitos de D-7 incluso si el cliente manipula la petición.
9. Capacidad `inventario` apagada da 403 en la lectura de ámbito y en las existencias, independientemente de los roles permitidos por matriz.

## 7. Contrato semántico de operaciones nuevas/alteradas

### Lectura nueva de ámbito de inventario

- **Método y ruta:** GET; ruta exacta se decide en `plan.md`.
- **Roles:** Administrador y Bodeguero; Solicitante y Superadmin reciben 403.
- **Gating:** capacidad institucional `inventario`; apagada devuelve 403.
- **Administrador:** 200 con sedes activas y departamentos activos con sede asignada, todos de su institución.
- **Bodeguero con sede:** 200 con únicamente su sede y departamentos activos de esa sede.
- **Bodeguero sin sede:** 409, sin fallback ni opciones ajenas.
- **Campos mínimos:** ID/nombre de sede e ID/nombre/sede_id de departamento. Sin usuarios, tickets, stock ni otras instituciones/sedes.
- **Autenticación:** falta de sesión 401.

### `GET /inventario/existencias` (contrato ampliado aditivamente)

- Se conserva el permiso existente para los roles institucionales ya autorizados; Superadmin conserva 403. El gating existente de `inventario` aplica.
- Se añade el parámetro opcional `sede_id` y se conserva `departamento_id`.
- Sesión ausente: 401. Rol no autorizado o capacidad `inventario` apagada: 403.
- Administrador: `sede_id` existente en su institución filtra (200); identificador de sede fuera de su ámbito, incluido un id de otra institución en otro esquema, responde 200 con `[]` porque no existe en el ámbito consultado. Esto no cambia el 404 establecido por AC-3 de Feature 011 para `GET /inventario/stock?sede_id=…`, que consulta un recurso y no filtra una lista.
- Bodeguero: `sede_id` de su propia sede filtra; cualquier otra sede responde 200 con `[]` por la intersección con su alcance. Sin sede asignada, la lectura sigue respondiendo 409 conforme al comportamiento vigente.
- Solicitante: `sede_id` de la sede de su departamento filtra; una sede distinta responde 200 con `[]` por la intersección con su alcance. No se le habilitan selectores ni cambia su permiso.
- `departamento_id` inexistente, sin sede o de otra sede dentro de la misma institución: 200 con `[]`; departamento de otra institución: 403.
- Si ambos filtros se envían coherentemente, ambos se aplican. Departamento asociado a sede distinta del `sede_id`: 200 con `[]`; la UI no envía este caso.
- Sin filtro por `sede_id` ni `departamento_id`, producto sin existencias permanece en cero con `sedes: []`. Al filtrar por sede/departamento desaparecen productos sin fila de stock en esa sede.
- Con filtro por sede, `stock_total`, `es_critico` y franja de indicadores describen exclusivamente el saldo/resultado de esa sede.

## 8. Criterios de aceptación

- **AC-1 — Filtro de sede y coherencia de resultados para Administrador.** DADO un Administrador con existencias en más de una sede, CUANDO selecciona una sede válida de su institución, ENTONCES la lista contiene solo saldos de esa sede; cada `stock_total` es el saldo de esa sede, `es_critico` se calcula sobre ese saldo y la franja de indicadores (total de catálogo cargado, con existencias y críticos) se recalcula sobre la lista filtrada. DADO que no hay `sede_id` ni `departamento_id` seleccionados, ENTONCES esos valores describen el agregado de todas las sedes de su institución. Un `sede_id` que no existe en el ámbito consultado devuelve 200 con `[]` y no revela si existe en otro esquema tenant.
  - **Evidencia:** `backend/tests/funcional/integracion/test_filtros_inventario_018.py` cubre filtro de sede, totales/críticos y sede ajena; `frontend/src/app/features/inventario/inventario.component.spec.ts` verifica indicadores con y sin sede; recorrido 4200. Detalle por test en §10.

- **AC-2 — Filtro por departamento y semántica de sede compartida.** DADO dos departamentos activos asociados a la misma sede, CUANDO Administrador o Bodeguero selecciona cualquiera, ENTONCES se consulta con su `departamento_id` y se muestran los mismos saldos físicos de esa sede, sin atribuirlos exclusivamente al departamento. Solo aparecen productos con fila de stock en esa sede. En la UI del Bodeguero se muestra literalmente: «El stock es compartido por la sede. Elegir un departamento no divide ni cambia el saldo; solo muestra productos con stock en esta sede.»; la nota no se muestra al Administrador.
  - **Evidencia:** `backend/tests/funcional/integracion/test_filtros_inventario_018.py` cubre el filtro departamental, respuesta vacía y agregación; `frontend/src/app/features/inventario/inventario.component.spec.ts` verifica query y nota literal exclusiva del Bodeguero; recorrido 4200. Detalle por test en §10.

- **AC-3 — Filtro `sede_id` y códigos de ámbito.** DADO un Administrador, CUANDO solicita `GET /inventario/existencias?sede_id=…`, ENTONCES sede existente de su institución devuelve 200 acotado a esa sede; un identificador que no existe en el esquema del actor —incluido uno de otra institución— devuelve 200 con lista vacía, sin inferir si existe fuera de ese tenant. Esto no supera el 404 del AC-3 de Feature 011 para `GET /inventario/stock?sede_id=…`: el endpoint 011 consulta un recurso, mientras aquí `sede_id` filtra una lista. DADO Bodeguero, su propia sede filtra y cualquier otra sede devuelve 200 con lista vacía. DADO Solicitante, su sede departamental filtra y una distinta devuelve 200 con lista vacía. Parámetros válidos se combinan con departamento; pareja incoherente devuelve 200 con lista vacía.
  - **Evidencia:** `backend/tests/funcional/integracion/test_filtros_inventario_018.py` prueba códigos/ámbitos con TestClient; `backend/tests/funcional/sistema/test_filtros_inventario_postgres_018.py` (gated PostgreSQL 16) valida aislamiento tenant; `backend/tests/funcional/unitarios/test_dto_ambito_018.py` cubre el DTO de ámbito. OpenAPI publica `sede_id`; recorrido 4200. Detalle por test en §10.

- **AC-4 — Ámbito organizacional del Bodeguero y departamentos no autorizados.** DADO un Bodeguero con sede, CUANDO consulta la nueva lectura, ENTONCES recibe solo su sede y departamentos activos de ella; la UI no renderiza selector de sede. Para `GET /inventario/existencias`, `departamento_id` inexistente, sin sede o de otra sede de su institución responde 200 con lista vacía; departamento de otra institución responde 403. DADO un Bodeguero sin sede, ENTONCES la nueva lectura de ámbito y las existencias responden 409; la UI muestra el mensaje de sede no asignada y no presenta una selección sustituta.
  - **Evidencia:** `backend/tests/funcional/integracion/test_filtros_inventario_018.py` prueba respuesta de ámbito, sede ausente y los cuatro casos departamentales; `frontend/src/app/features/inventario/inventario.component.spec.ts` verifica ausencia del selector de sede, opciones y estado 409; recorrido 4200.

- **AC-5 — Selectores coherentes por sede y helper de rol.** DADO que Administrador elige sede A, CUANDO abre o actualiza el selector departamental, ENTONCES solo se ofrecen departamentos de sede A. Cambiar a sede B limpia selección incompatible; la UI nunca envía una pareja departamento/sede incoherente. El helper `puede*` de `roles.ts` permite selectores solo a Administrador/Bodeguero y las pruebas del helper verifican esos roles y la exclusión de Solicitante/Superadmin. El Bodeguero no ve selector de sede.
  - **Evidencia:** `frontend/src/app/core/auth/roles.spec.ts` para el helper y `frontend/src/app/features/inventario/inventario.component.spec.ts` para acotación, limpieza y query; recorrido 4200.

- **AC-6 — Estados vacíos según filtro organizacional.** DADO que un producto no tiene ninguna fila de stock, CUANDO no hay filtro de sede/departamento, ENTONCES aparece con `stock_total: 0`, `sedes: []` y criticidad vigente. DADO que ese producto no tiene fila de stock en la sede seleccionada o en la sede del departamento, ENTONCES desaparece. Si la consulta filtrada devuelve cero productos, la vista muestra «Ningún insumo coincide con los filtros aplicados»; si la consulta sin filtros devuelve un catálogo vacío, muestra «El catálogo no tiene insumos cargados». Carga y error conservan sus estados diferenciados.
  - **Evidencia:** `backend/tests/funcional/integracion/test_filtros_inventario_018.py` verifica resultado sin filtro vs. filtros sede/departamento; `inventario.component.spec.ts` comprueba los dos mensajes, carga y error; recorrido 4200.

- **AC-7 — Combinación y limpieza de filtros.** DADO filtros de sede/departamento, CUANDO se combinan con texto, categoría y «Solo stock crítico», ENTONCES se aplican simultáneamente. «Limpiar filtros» restablece filtros organizacionales y existentes; los indicadores regresan al agregado permitido por rol.
  - **Evidencia:** `frontend/src/app/features/inventario/inventario.component.spec.ts` cubre combinaciones, limpieza y métricas; recorrido 4200.

- **AC-8 — Roles, matriz, capacidad y OpenAPI.** DADO la nueva lectura, CUANDO se verifica autorización, ENTONCES aparece exactamente una nueva entrada en la matriz con Administrador+Bodeguero y la cardinalidad sube de 60 a **61**; todas las 60 operaciones previas mantienen exactamente sus roles y ninguna se retira. Solicitante/Superadmin reciben 403 en lectura de ámbito. Con capacidad `inventario` apagada, ambos roles autorizados reciben 403 en esa lectura y existencias. Superadmin conserva 403 en existencias. El contrato OpenAPI declara respuestas 200, 401, 403 y 409 aplicables para ámbito y el parámetro `sede_id` en existencias.
  - **Evidencia:** ampliar `backend/tests/funcional/integracion/test_ciclo_vida_autorizacion_014.py` (matriz 61 y 60 previas intactas), `backend/tests/funcional/integracion/test_permisos_*.py` (incluido el seam de referencia transcrita independientemente) y `backend/tests/no_funcional/seguridad/test_capacidades_gating_012.py` (asociación a `inventario` y 403 apagado); nuevo `test_filtros_inventario_018.py` para roles/endpoints; OpenAPI. `roles.spec.ts` verifica helper y `inventario.component.spec.ts` la presentación.

- **AC-9 — Verificación funcional y de aislamiento.** DADO el cambio backend y frontend, CUANDO se cierra la feature, ENTONCES `pytest` SQLite verifica contrato/matriz/gating; pruebas gated PostgreSQL 16 verifican aislamiento por tenant y límites de ámbito, incluyendo que un id de sede de otro esquema resulte 200/`[]` en este filtro de lista; `ng test` verifica helper, selectores, métricas, nota y vacíos; `/openapi.json` refleja el contrato; recorridos funcionales en 4200 y de humo en 8080 reconstruido pasan. El resultado 200/`[]` de esta lista no contradice el 404 de Feature 011 AC-3, que prueba la consulta de un recurso por `/inventario/stock`.
  - **Evidencia:** `cd backend && pytest`; suite gated con `POSTGRES_TEST_URL` y tests de `test_filtros_inventario_018.py`; `npx ng test --watch=false --browsers=ChromeHeadless`; `/openapi.json`; recorrido 4200 y 8080 con frontend reconstruido.

## 9. Restricciones y cambios documentales de cierre

- `stock_sede` sigue como fuente única de stock; no hay saldo por departamento ni cambios de modelo de datos.
- La matriz solo recibe una operación nueva y aditiva para lectura de ámbito (Administrador+Bodeguero); ninguna operación existente cambia de roles ni se retira. La matriz pasa de 60 a 61 operaciones. La Feature 014 se amplía explícitamente, no se reescribe en silencio: sus aserciones absolutas de cardinalidad y OpenAPI, `test_matriz_tiene_exactamente_60_operaciones_tras_014` y `test_openapi_tiene_60_operaciones_tras_014` en `backend/tests/funcional/integracion/test_ciclo_vida_autorizacion_014.py`, se actualizan de 60 a 61 o se trasladan a una instantánea histórica; el plan fija la opción concreta antes de implementar.
- Se añade únicamente `sede_id` a `GET /inventario/existencias`; `departamento_id` conserva la semántica de esta spec. No se cambia el modelo de respuesta.
- La nueva lectura está gateada por capacidad `inventario`; esto no amplía capacidades ni cambia su catálogo cerrado.
- La operación nueva no concede al Bodeguero lecturas de sedes ajenas, departamentos de otra sede, usuarios, tickets ni stock/saldos de otras sedes. La autorización y el aislamiento efectivos permanecen en backend.
- Clerk permanece como autoridad de autenticación. No se agregan paquetes.
- Identificadores de dominio en español; Angular standalone, signals/computed y Tailwind; helper `puede*` central con pruebas.
- No se depende de `AdministracionService` ni de endpoints administrativos para obtener las opciones de inventario.
- Al cierre se actualiza `docs/spec/stack.md` con la operación y parámetro aditivos, la matriz/gating y el contrato, siguiendo el precedente de las Features 011/014; también se actualiza la fila de Feature 018 en `docs/spec/roadmap.md` y se mantiene coherencia documental.

## 10. Estado y evidencia de verificación

Todos los AC quedaron **verificados** al cierre (21/Oct/2026). Los nombres de test son reales
y viven en `backend/tests/funcional/integracion/test_filtros_inventario_018.py` (35 pruebas),
`backend/tests/funcional/unitarios/test_dto_ambito_018.py` (13),
`backend/tests/funcional/sistema/test_filtros_inventario_postgres_018.py` (6 gated),
`frontend/src/app/core/auth/roles.spec.ts`,
`frontend/src/app/features/inventario/inventario.component.spec.ts` y
`frontend/src/app/features/inventario/services/inventario.service.spec.ts`. No se creó
`backend/tests/funcional/integracion/test_filtros_inventario_018.py`: el filtrado de lista, sus agregados y
la regla de `condicion_stock` se ejercen sobre el harness con `TestClient` (que atraviesa
ruta→servicio) y no por llamada directa al servicio.

| Criterio | Estado | Evidencia de verificación |
|---|---|---|
| AC-1 | Verificado | `test_filtros_inventario_018.py::test_existencias_con_sede_acotan_saldo_sedes_y_criticidad`, `::test_existencias_sin_filtro_mantienen_agregado_y_productos_sin_saldo`, `::test_existencias_sede_inexistente_responde_200_vacio` (saldo, `sedes` y `es_critico` por sede; agregado sin filtro; 200/`[]`). UI: `inventario.component.spec.ts` → *«al elegir una sede acota la consulta y recalcula la franja de indicadores»*. **Recorrido 4200** (no test): capturas `02-admin-sede-providencia.png` (franja 3/2/1) y `8080-02-admin-sede-filtrada.png`. |
| AC-2 | Verificado | Backend: `test_filtros_inventario_018.py::test_departamentos_de_la_misma_sede_devuelven_el_mismo_saldo` (dos departamentos de sede común → mismo saldo; productos sin fila desaparecen). UI: `inventario.component.spec.ts` → *«el Bodeguero no ve selector de sede, ve sus departamentos y la nota literal»* y *«la nota de stock compartido no se muestra al Administrador»*. **Recorrido 4200** (no test): capturas `03-admin-departamento-docencia.png` y `09-bodeguero-departamento-biblioteca.png`. |
| AC-3 | Verificado | Backend API: `test_filtros_inventario_018.py::test_existencias_sede_de_otra_institucion_responde_200_vacio`, `::test_existencias_bodeguero_filtra_su_sede_y_otra_sede_da_vacio`, `::test_existencias_solicitante_su_sede_filtra_y_otra_sede_da_vacio`, `::test_existencias_sede_y_departamento_incoherentes_responde_200_vacio`. **Gated PostgreSQL 16**: `test_filtros_inventario_postgres_018.py::test_sede_de_otro_tenant_devuelve_200_vacio_y_el_recurso_conserva_404` (filtro de lista → 200/`[]`; el recurso `/inventario/stock` conserva su 404 de 011) y `::test_filtro_propio_acota_saldo_y_sede_ajena_en_rol_operativo_da_vacio`. OpenAPI: `::test_openapi_publica_ambito_y_el_parametro_sede_id`. |
| AC-4 | Verificado | Backend API: `test_filtros_inventario_018.py::test_ambito_bodeguero_recibe_solo_su_sede_y_sus_departamentos`, `::test_ambito_bodeguero_sin_sede_responde_409`, `::test_existencias_departamento_no_resoluble_responde_200_vacio`, `::test_existencias_departamento_de_otra_institucion_responde_403` (harness SQLite), `::test_existencias_bodeguero_sin_sede_responde_409`. UI: `inventario.component.spec.ts` → *«el Administrador consulta el ámbito y ve sede y departamento con sus opciones»* y *«un 409 de ámbito sin sede deja la vista con aviso y sin filtros sustitutos»*. **Recorrido 4200/8080** (no test): capturas `08-bodeguero-nota-y-departamento.png` y `8080-03-bodeguero-departamento.png`; el 409 se contrastó por API con sesión real (`evidencia/README.md` §6.1). |
| AC-5 | Verificado | `roles.spec.ts` → *«puedeVerFiltrosInventario concede solo a Administrador y Bodeguero (AC-5/AC-8)»*, *«puedeVerFiltrosInventario no concede a alias, desconocido ni ausente (AC-5)»*, *«el Solicitante conserva la vista de inventario pero no sus filtros (AC-7)»*, *«el Superadmin sigue denegado en inventario y en sus filtros (AC-8)»*. UI: `inventario.component.spec.ts` → *«cambiar de sede limpia el departamento incompatible y acota sus opciones»*. **Recorrido 4200** (no test): captura `04-admin-cambio-sede-limpia-departamento.png`. |
| AC-6 | Verificado | Backend: `test_filtros_inventario_018.py::test_existencias_con_filtro_organizacional_oculta_productos_sin_saldo`. UI: `inventario.component.spec.ts` → *«con filtros organizacionales sin resultados muestra el vacío filtrado»*, *«debe distinguir el estado vacio del estado con filtros»*, *«debe mostrar un error si el backend no responde»*. **Recorrido 4200** (no test): captura `06-admin-vacio-filtrado.png`. |
| AC-7 | Verificado | UI: `inventario.component.spec.ts` → *«combina sede y departamento con texto, categoría y «Solo stock crítico»»* y *««Limpiar filtros» restablece los filtros organizacionales y los existentes»*. **Recorrido 4200** (no test): capturas `05-admin-combinacion-filtros.png` y `07-admin-limpiar-filtros.png`; `10-solicitante-sin-selectores.png`. |
| AC-8 | Verificado | Matriz 60→61: `backend/tests/funcional/integracion/test_ciclo_vida_autorizacion_014.py` (las dos aserciones absolutas `test_matriz_tiene_exactamente_60_operaciones_tras_014` y `test_openapi_tiene_60_operaciones_tras_014` quedaron en 61, con comentario de ampliación explícita por la 018). `test_filtros_inventario_018.py::test_matriz_declara_la_operacion_de_ambito_para_administrador_y_bodeguero`, `::test_matriz_conserva_las_operaciones_previas_intactas`, `::test_matriz_tiene_exactamente_61_operaciones_tras_018`, `::test_capacidad_inventario_asociada_a_la_operacion_de_ambito`, `::test_ambito_de_rol_no_autorizado_responde_403`, `::test_ambito_con_capacidad_inventario_apagada_responde_403`, `::test_openapi_publica_61_operaciones_tras_018`, `::test_openapi_documenta_respuestas_de_ambito_y_existencias`. Baseline histórico de 55 preservado en `backend/tests/no_funcional/seguridad/test_permisos.py` con referencia aditiva; gating en `backend/tests/no_funcional/seguridad/test_capacidades_gating_012.py`. **Matiz de evidencia:** el 403 por capacidad apagada en `/inventario/existencias` se acredita de forma indirecta —el mapa `inventario` de la 012 (línea `("GET", "/api/v1/inventario/existencias"): "inventario"`), el `requiere_capacidad` que encadena la ruta y la prueba directa de ámbito— y no por una aserción HTTP dedicada a existencias con la capacidad apagada; es comportamiento **previo a la 018** (ver `tasks.md` T9) y no una regresión de esta feature. UI: `roles.spec.ts` (helper) e `inventario.component.spec.ts` (presentación). |
| AC-9 | Verificado | **Suites:** `cd backend && python -m pytest -q` → **1339 passed / 76 skipped / 0 failed** (SQLite). Gated `POSTGRES_TEST_URL` → **1415 passed / 0 skipped / 0 failed** (`apt_erp` intacta: 5 instituciones, 4 esquemas `tenant_%`, `version_esquema 014.1` con la misma marca). `npx ng test --watch=false --browsers=ChromeHeadless` → **419 SUCCESS / 0 FAILED**; `npx ng build` limpio (`main-7QF7T5XQ.js`). **OpenAPI:** 61 operaciones v1, claves idénticas a `MATRIZ_PERMISOS`. **Recorrido funcional 4200** con escritura real (capturas `01`…`10`) y **humo 8080** tras `docker compose build frontend` (bundle `main-7QF7T5XQ.js`, capturas `8080-01`…`8080-04`), ambos en `docs/spec/features/018-filtro-inventario-sede-departamento/evidencia/README.md`. El 200/`[]` de la lista no contradice el 404 de 011 AC-3 (recurso `/inventario/stock`), verificado en el gated. |

La ruta/DTO exactos de la operación de ámbito se fijan en `plan.md`; no pueden alterar este contrato semántico ni la lista de campos mínimos. La operación publicada es `GET /api/v1/inventario/ambito` con `AmbitoInventarioRespuesta`.

> **Nota de dependencia (26/Nov/2026, Feature 013 §10).** El checkbox **«Solo con stock»** del
> inventario queda como **enmienda separada a esta feature**, fuera del alcance de la 013 y
> pendiente de planificación después del cierre de T44. No se implementa aquí ni agrega ACs
> ejecutables en la 013: se registrará con su propia spec/plan cuando se aborde. La 013 solo deja
> constancia de la dependencia en `../013-ciclo-vida-ticket/spec.md` §10.8/§10.12.

## 11. Enmienda post-cierre (27/Nov/2026): checkbox «Solo con stock»

> **Qué enmienda.** No crea una feature nueva ni reescribe la historia ni el cierre de la 018:
> añade la pieza «Solo con stock» sobre lo ya cerrado, con decisiones D-9…D-14 y criterios
> AC-10…AC-13. **No cambia la API, el DDL, el modelo de datos, la matriz de autorización, las
> capacidades ni los permisos**: `GET /inventario/existencias` sigue devolviendo los productos con
> saldo cero y no gana parámetros. Satisface la nota de dependencia al pie de §10 (26/Nov/2026,
> Feature 013), cuyo texto no se edita por ser registro histórico. Las tareas de esta enmienda
> quedaron en **T14** y **T15** de `tasks.md` y el detalle técnico, en `plan.md` §7 (§11.8).

### 11.1 Problema

La 018 acotó las existencias por rol y por sede/departamento, pero el catálogo sigue mostrando
**todos** los productos del ámbito, incluidos los que no tienen saldo: sin filtro organizacional
aparecen en cero con `sedes: []` (D-7), y con sede/departamento desaparecen solo los que no tienen
fila de stock en esa sede, no los que la tienen con saldo cero. Para el Administrador que revisa la
institución, el Bodeguero que prepara su bodega o el Solicitante que consulta disponibilidad antes
de pedir, esas filas en cero son ruido: alargan la tabla y obligan a leer el número de cada fila
para distinguir «hay» de «no hay». La lectura de disponibilidad real existe —`stock_total`— pero no
se puede pedir a la vista que la use como criterio.

### 11.2 Objetivo

Añadir en la pestaña «Existencias» un checkbox **«Solo con stock»**, marcado por defecto en falso,
que oculte de la tabla los productos sin saldo en el ámbito vigente del rol y de los filtros, sin
tocar el contrato del backend ni los indicadores del catálogo, y que se combine con el resto de
filtros y con «Limpiar filtros».

### 11.3 Alcance de la enmienda

#### Dentro

- Checkbox «Solo con stock» en la barra de filtros de la pestaña «Existencias», visible para
  **Administrador, Bodeguero y Solicitante**.
- Predicado `stock_total > 0` aplicado en cliente sobre la última respuesta de
  `GET /inventario/existencias` (ya acotada por rol y por `sede_id`/`departamento_id`).
- Combinación con búsqueda por texto, categoría, «Solo stock crítico» y filtros organizacionales;
  actualización de los conteos del panel de categorías, de «Limpiar filtros» y de la detección de
  filtros activos.
- Estado vacío propio, sin confundir «sin resultados» con «sin stock».
- Accesibilidad del control y presentación con Tailwind, sin CSS quemado.
- Pruebas de componente, `ng build`, recorrido funcional en 4200 y humo en 8080 reconstruido.

#### Fuera

- Endpoint, parámetro de consulta, DTO, response model, permiso, capacidad o entrada de matriz
  nuevos; el filtro **no viaja al servidor**.
- Cambios de DDL, modelo, semilla, token de esquema o migraciones.
- Persistencia del estado en URL, `localStorage`, preferencias de usuario o entre pestañas.
- Recalcular la franja de indicadores al marcar o desmarcar, o cambiar el comportamiento de
  «Solo stock crítico».
- Filtrar por stock en otras vistas o lecturas: detalle de producto de la 019, «Gestión del
  catálogo» de la 014, dashboard, tickets, compras o el propio backend.
- Ocultar productos de la respuesta, alterar `stock_total`, `sedes` o `es_critico`, o reordenar
  las filas.

### 11.4 Decisiones

#### D-9 — Filtro de presentación sobre el `stock_total` ya acotado por el servidor

El checkbox no envía ningún parámetro ni consulta un endpoint nuevo: oculta, en la tabla de la
pestaña «Existencias», los productos cuyo `stock_total` en la respuesta vigente **no sea
estrictamente mayor que 0**. El conjunto de partida es el que ya devolvió
`GET /inventario/existencias` con el alcance del rol (Administrador: toda la institución; Bodeguero
y Solicitante: su sede) y, si están elegidos, los filtros `sede_id`/`departamento_id`. El backend
sigue devolviendo los productos con saldo cero —incluidos los de `sedes: []`— y conserva su
contrato (D-7). Con filtro organizacional, el servidor ya omite los productos **sin fila** de stock
en esa sede (D-2); el checkbox oculta además los que tienen fila **con saldo 0**.

**Por qué:** `stock_total` es el campo que la tabla muestra y ya está calculado sobre el ámbito
correcto; recalcularlo en el cliente o añadir un parámetro al servidor duplicaría una decisión de
presentación, exigiría contrato/matriz/OpenAPI nuevos y no cambiaría ningún dato. Como el saldo es
por sede y no por departamento (D-2), «tiene stock» solo puede significar `stock_total > 0` en el
ámbito vigente. El `> 0` estricto —y no `>= 0`— es justamente lo que distingue «tiene existencias»
de «aparece en el catálogo», y coincide con la definición que ya usa el indicador «Con
existencias».

#### D-10 — La franja de indicadores no se recalcula al marcar

Los tres indicadores («Insumos», «Con existencias» y «Stock crítico») siguen describiendo el
catálogo **cargado** del ámbito del rol y de los filtros organizacionales, igual que hoy con
«Solo stock crítico»: marcar o desmarcar «Solo con stock» no los altera. Solo cambian la tabla, el
panel de categorías y el estado vacío.

**Por qué:** §6.4 y AC-1 atan la franja a la respuesta que devuelve el servidor para el ámbito
seleccionado, no a los filtros de cliente, y la vista ya la rotula «Catálogo cargado». Recalcular
los tres desde las filas visibles haría que, con el checkbox marcado, «Con existencias» fuera
siempre igual a «Insumos» (todas las filas tendrían saldo): el indicador perdería su función, que
es decir cuántos productos del catálogo tienen stock **antes** de decidir el filtro, y además
obligaría a reescribir las aserciones de la franja de AC-1 y la prueba de la transición
sede↔global. Alternativa descartada: recalcular desde las filas visibles, que además haría
depender el KPI de la categoría seleccionada, algo que el panel de categorías hoy evita a
propósito.

#### D-11 — Visible para los tres roles que leen existencias

El checkbox se muestra en la barra de filtros de la pestaña «Existencias» a **Administrador,
Bodeguero y Solicitante**. No depende de `puedeVerFiltrosInventario` —que gobierna los selectores
organizacionales y solo concede a Administrador y Bodeguero— ni consulta la lectura de ámbito. El
Superadmin no accede a la vista, que sigue denegada por matriz y capacidad.

**Por qué:** el control no amplía el alcance ni revela datos: solo oculta filas que la API ya
devolvió para el actor. El Solicitante —que consulta disponibilidad antes de emitir su ticket— es
el principal interesado en no leer ceros, y negárselo obligaría a mantener dos barras de filtros
distintas sin ninguna ganancia de seguridad. La autorización y el acotamiento por sede siguen
siendo del servidor (D-8): esto es visibilidad, no permiso.

#### D-12 — Estado vacío propio, con precedencia explícita

Cuando el checkbox está marcado y no queda ninguna fila visible, la vista muestra **«Ningún insumo
con stock coincide con los filtros aplicados.»** y no el vacío genérico. La precedencia es:
(1) si la respuesta cargada no trae ningún producto, se conserva «El catálogo no tiene insumos
cargados.» aunque el checkbox esté marcado; (2) si hay catálogo pero el checkbox marcado deja la
tabla vacía, se muestra el mensaje propio de stock; (3) en los demás casos con filtros y sin filas,
se conserva «Ningún insumo coincide con los filtros aplicados.».

**Por qué:** AC-6 ya distingue «no hay catálogo» de «los filtros no encuentran nada»; el checkbox
introduce un tercer caso —hay catálogo y puede haber coincidencias, pero ninguna con saldo— que no
debe leerse como filtros mal puestos ni como catálogo inexistente. El texto paralelo al de AC-6
mantiene intacto el contrato literal de los dos mensajes existentes y añade la causa real. Que el
catálogo vacío prevalezca evita atribuir a la falta de stock una ausencia de datos anterior al
filtro.

#### D-13 — Sin persistencia entre cargas

El estado vive solo en memoria de la vista: arranca **desmarcado** en cada carga y en cada recarga
de la página, y no se guarda en la URL, en `localStorage` ni en preferencias de usuario. Tampoco se
sincroniza entre pestañas ni se restaura desde el detalle de producto.

**Por qué:** es una ayuda de exploración, no una configuración. Persistirlo ocultaría productos del
catálogo sin señal visible —un usuario posterior creería que no existen— y convertiría la ausencia
de una fila en una decisión heredada de otra sesión. «Solo stock crítico», el filtro vecino, tampoco
persiste: mantener el mismo comportamiento evita dos filtros de la misma barra con reglas distintas.

#### D-14 — Control nativo accesible y estilos Tailwind

Se usa un `<input type="checkbox">` nativo con `id="solo-con-stock"`, `name="solo-con-stock"` y un
`<label>` visible asociado por `for`/`id` con el texto **«Solo con stock»**. Conserva el patrón del
checkbox existente: anillo `focus-visible` y clases Tailwind, sin CSS quemado ni `styles` en el
componente. El clic en la etiqueta conmuta el control y el lector de pantalla anuncia nombre y
estado. No se renombra ni se mueve «Solo stock crítico».

**Por qué:** el patrón ya está probado en la misma barra y cumple AGENTS.md §6 (solo Tailwind, sin
CSS embebido). Un `div` clicable o un control sin etiqueta rompería teclado y lectores de pantalla;
un `id` estable permite, además, la prueba DOM del contrato.

### 11.5 Reglas del flujo

1. La pestaña «Existencias» se carga como hoy: el servidor acota por rol y, si corresponde, por
   sede/departamento. El checkbox arranca desmarcado en cada carga.
2. Desmarcado, la tabla muestra el catálogo del ámbito —incluidos los productos con
   `stock_total: 0` y `sedes: []`—, exactamente como antes de esta enmienda.
3. Marcado, la tabla muestra solo los productos con `stock_total > 0` del conjunto cargado. No se
   emite una petición nueva ni se agrega un parámetro: el conjunto no se altera, solo se oculta.
4. El filtro se combina en intersección con el texto, la categoría, «Solo stock crítico» y los
   filtros organizacionales; no los reemplaza ni los limpia. Cambiar sede o departamento conserva
   el estado del checkbox y le reaplica el predicado a la nueva respuesta.
5. Con «Solo stock crítico» marcado a la vez, quedan los productos críticos **con** stock; los
   críticos en cero desaparecen (la regla vigente marca crítico también con saldo 0 y mínimo ≥ 0).
6. El panel de categorías cuenta sobre el mismo conjunto que el buscador y los dos checkboxes: al
   marcar «Solo con stock», el número de cada categoría y el de «Todas» excluyen los productos sin
   saldo, de modo que el conteo anunciado coincide con lo que la tabla mostrará al pulsar esa
   categoría.
7. El botón «Limpiar filtros» se muestra cuando hay algún filtro activo, incluido «Solo con
   stock»; al pulsarlo desmarca el checkbox y restablece el resto. Si el único filtro activo era de
   cliente, no se emite una lectura nueva de existencias.
8. La franja de indicadores no cambia al marcar o desmarcar (D-10): sigue representando el catálogo
   cargado del ámbito.
9. El estado vacío sigue la precedencia de D-12; carga y error conservan sus mensajes y su orden
   actuales, y un fallo del backend no se presenta como «sin stock».
10. Sin persistencia (D-13): una recarga de la vista vuelve a mostrar todos los productos.

### 11.6 Contrato de la interfaz

| Elemento | Contrato |
|---|---|
| Control | Checkbox nativo, `id="solo-con-stock"`, `name="solo-con-stock"`, etiqueta visible «Solo con stock» asociada por `for`, estado inicial `false`, foco visible con anillo y clases Tailwind. |
| Ubicación | Barra de filtros de la pestaña «Existencias», junto al buscador y a «Solo stock crítico». Visible para Administrador, Bodeguero y Solicitante. |
| Predicado | `stock_total > 0` sobre cada producto de la última respuesta de `GET /inventario/existencias`, ya acotada por rol y por sede/departamento. |
| Orden de aplicación | Servidor (rol y filtros organizacionales) → cliente (texto, críticos y «Solo con stock») → categoría. El predicado se aplica antes de la categoría para que el panel cuente lo que la tabla mostrará. |
| Indicadores | Sin cambios al marcar o desmarcar: siguen midiendo el catálogo cargado (D-10). |
| Estado vacío | «Ningún insumo con stock coincide con los filtros aplicados.» cuando el checkbox marcado deja la tabla vacía habiendo catálogo; precedencia de D-12. |
| Contrato del backend | Sin cambios: `GET /inventario/existencias` no gana parámetros ni campos; `stock_total`, `sedes` y `es_critico` conservan su semántica (D-7) y los productos sin saldo siguen en la respuesta. |
| Autorización | Sin entradas nuevas en la matriz, sin cambios de roles, capacidades ni gating; el control es solo presentación (D-11). |
| Persistencia | Ninguna (D-13). |

### 11.7 Criterios de aceptación (AC-10…AC-13)

- **AC-10 — Visibilidad, estado inicial y accesibilidad.** DADO un usuario con rol Administrador,
  Bodeguero o Solicitante, CUANDO abre `/inventario` en la pestaña «Existencias», ENTONCES ve el
  checkbox «Solo con stock» desmarcado; el control tiene `id="solo-con-stock"`, `name` y `<label>`
  visible asociada, se conmuta con clic en la etiqueta y con teclado, y muestra anillo
  `focus-visible`; no hay CSS embebido ni `styles` (solo Tailwind). DADO que la vista se vuelve a
  cargar o se monta de nuevo, ENTONCES el checkbox vuelve a estar desmarcado: no se persiste en
  URL, almacenamiento ni preferencias. El Superadmin no accede a la vista.
  - **Evidencia verificada (T15, 27/Nov/2026):** `frontend/src/app/features/inventario/inventario.component.spec.ts:1615-1631`
    — bucle `for (const rol of ['Administrador', 'Bodeguero', 'Solicitante'])` que genera el test
    *««Solo con stock» está visible para {rol} y arranca desmarcado»* (**3 casos**) y
    *«el checkbox «Solo con stock» declara id, name y label, y no persiste al remontar la vista»*,
    más `ng build` sin CSS embebido (`main-72C5Q3DY.js`, 339,98 kB
    iniciales). **4200:** `#solo-con-stock` con `id`/`name`/`<label for>` «Solo con stock»,
    desmarcado, y conmutación real **Tab + Espacio** con anillo `focus-visible` observado
    (`box-shadow` azul); recarga sin persistencia. **8080:** el mismo control en la imagen
    reconstruida. Detalle y capturas en `evidencia/README.md` §12.

- **AC-11 — Filtrado por saldo, sin contrato nuevo y con la franja intacta.** DADO el catálogo
  cargado del ámbito (por ejemplo, tres productos: dos con `stock_total > 0` y uno en cero con
  `sedes: []`), CUANDO se marca «Solo con stock», ENTONCES la tabla muestra solo los dos con saldo y
  desaparece el de cero; el producto sigue en la respuesta —no se refetchea ni se envía un
  parámetro— y los tres indicadores de la franja («Insumos», «Con existencias» y «Stock crítico»)
  conservan los valores que tenían antes de marcar. CUANDO se desmarca, ENTONCES vuelven a verse los
  tres. El contrato de `GET /inventario/existencias` no cambia y no se emite ninguna petición HTTP
  adicional.
  - **Evidencia verificada (T15, 27/Nov/2026):** `inventario.component.spec.ts` — *«marcar «Solo con stock»
    oculta los productos con stock_total 0 sin alterar la franja ni pedir existencias»* y
    *«desmarcar «Solo con stock» recupera los productos sin saldo»*, con `httpMock` sin peticiones
    pendientes. **4200 (Solicitante):** 10 filas con 5 ceros → **10 a 5 filas / 0 ceros** al marcar,
    franja **10 / 5 / 6** idéntica antes y después, y una sola `GET /inventario/existencias` (la de
    la carga); al recargar, el checkbox vuelve desmarcado y reaparecen las 10 filas. **8080:** mismo
    10→5 con la imagen reconstruida. El contrato de `GET /inventario/existencias` no cambió.
    Capturas `t15-03`, `t15-04` y `t15-06`.

- **AC-12 — Combinación con los demás filtros y limpieza.** DADO texto, categoría, «Solo stock
  crítico» y/o filtros organizacionales activos, CUANDO se marca «Solo con stock», ENTONCES se
  aplican simultáneamente y quedan solo las filas que cumplen todo, con `stock_total > 0`; con
  «Solo stock crítico» marcado a la vez quedan los críticos **con** saldo y desaparecen los
  críticos en cero. Los conteos del panel de categorías excluyen los productos sin saldo. El botón
  «Limpiar filtros» aparece con el checkbox marcado y, al pulsarlo, lo desmarca, restablece los
  demás filtros y —solo si había un filtro organizacional activo— vuelve a pedir el agregado del
  rol; si el único filtro activo era de cliente, no hay lectura nueva.
  - **Evidencia verificada (T15, 27/Nov/2026):** `inventario.component.spec.ts` — *««Solo con stock» se
    combina con texto, categoría, críticos y filtros organizacionales»*, *«el panel de categorías
    excluye los productos sin saldo al marcar «Solo con stock»»*, *««Limpiar filtros» desmarca «Solo
    con stock» y no pide existencias si el único filtro era de cliente»* y la rama con filtro
    organizacional activo. **4200 (Administrador):** texto `toner` + categoría «Toner y Cartuchos»
    + «Solo stock crítico» + «Solo con stock» deja **1 fila** y el panel anuncia «Toner y Cartuchos
    1 insumos», sin petición nueva; «Limpiar filtros» restablece el estado con 10 filas y sin
    lectura nueva. Captura `t15-02`; detalle en `evidencia/README.md` §12.

- **AC-13 — Estado vacío diferenciado y sin interferencia con carga/error.** DADO el checkbox
  marcado y ninguna fila con `stock_total > 0` en el ámbito y filtros vigentes, ENTONCES se muestra
  «Ningún insumo con stock coincide con los filtros aplicados.» y no el mensaje genérico de filtros
  ni el de catálogo vacío. DADO que la respuesta cargada no trae ningún producto, ENTONCES se
  conserva «El catálogo no tiene insumos cargados.» aunque el checkbox esté marcado. Los estados de
  carga y de error del backend conservan sus mensajes actuales; un error no se presenta como «sin
  stock».
  - **Evidencia verificada (T15, 27/Nov/2026):** `inventario.component.spec.ts` — *«sin productos con stock
    muestra un vacío que distingue la falta de stock»*, *«el vacío de catálogo prevalece sobre el
    vacío de «Solo con stock»»* y la prueba de error de AC-6 sin cambios. **4200:** con el checkbox
    marcado y filtros de cliente sin coincidencias (Administrador) o categoría «Limpieza» en el
    ámbito del Solicitante, la vista muestra **«Ningún insumo con stock coincide con los filtros
    aplicados.»** con la franja intacta; capturas `t15-01` y `t15-05`. El caso catálogo vacío +
    checkbox se acredita en el spec (provocarlo en vivo exigiría vaciar el tenant).

### 11.8 Superación, evidencia y cierre

- **La 018 no reescribe su cierre.** El estado histórico `Cerrada (21/Oct/2026)` y la §10 con la
  evidencia de AC-1…AC-9 quedan intactos: no se reabre su tabla, no se alteran sus conteos
  (matriz 60→61, suites 1339 SQLite / 1415 gated / 419 `ng test`, capturas del 21/Oct/2026) ni se
  reescribe el contrato de la 018. Esta §11 es **aditiva** y registra su propia superación: la
  pieza nueva y su evidencia viven aquí.
- **AC-1…AC-9 siguen vigentes sin cambios.** El checkbox no modifica la semántica de sede,
  departamento, criticidad, indicadores ni estados vacíos existentes; cuando está desmarcado, el
  comportamiento es idéntico al cerrado.
- **La nota de dependencia al pie de §10 queda satisfecha** por esta enmienda: el checkbox llegó
  como enmienda de la 018, fuera de la 013 y sin crear una feature nueva. El texto de la nota no se
  edita porque es registro histórico.
- **Tareas:** **T14** —pruebas rojas y control «Solo con stock» con su semántica, combinación,
  conteos, limpieza y estado vacío en la pestaña «Existencias»— y **T15** —verificación y evidencia:
  `npx ng test --watch=false --browsers=ChromeHeadless`, `npx ng build`, recorrido funcional en
  4200 y humo en 8080 reconstruido, más la anotación de la enmienda—. Ambas quedaron cerradas el
  27/Nov/2026; `tasks.md`, `plan.md` §7 y `evidencia/README.md` §12 son los registros vigentes.
- **Sin cambios de contrato ni de esquema**, por lo que `stack.md` no requiere actualización de
  contrato (no hay API, parámetro, matriz ni DDL nuevos). Al cerrar la enmienda se anotará en la
  fila 018 de `roadmap.md` y en `MEMORY.md`, con el grep de coherencia de AGENTS.md §8.5–§8.7.
- **Cierre de la enmienda** exige, por ser un cambio de frontend, reconstruir la imagen
  (`docker compose -f docker-compose.yml build frontend` + `up -d frontend`) y verificar los dos
  puertos, además de la suite y el build en verde.
