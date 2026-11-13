# Plan de implementación — Feature 022: Mantenimiento técnico I

**Feature:** `022-mantenimiento-tecnico/`
**Spec:** [spec.md](spec.md)
**Enfoque:** seis tareas secuenciales, cada una mergeable y con verificación propia.
**Regla:** no se abre la Feature 023 hasta que 022 esté cerrada y verde.

## 1. Orden de ejecución

```text
T1 línea base + roadmap
  → T2 borrar servicio muerto
  → T3 coherencia documental
  → T4 dedup frontend (test primero)
  → T5 dedup backend (test primero)
  → T6 cierre y evidencia
```

T2 y T3 no cambian comportamiento y pueden ir en commits separados. T4 y T5
siguen rojo → verde: primero el test que fija el contrato actual, luego la
implementación.

## 2. Línea base (T1)

### 2.1 Backend

```powershell
cd backend
.venv/Scripts/python.exe -m pytest -q
```

Esperado: `1496 passed, 88 skipped, 0 failed` (los tests gated de PostgreSQL se
omiten sin `POSTGRES_TEST_URL`).

### 2.2 Frontend

```powershell
cd frontend
$env:CHROME_BIN = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
npx ng test --watch=false --browsers=ChromeHeadless
```

Esperado: **537 SUCCESS**, 0 fallos. No usar `npm test` (modo watch).

### 2.3 Build y contrato

```powershell
cd frontend
npx ng build
```

```powershell
cd backend
.venv/Scripts/python.exe -c "from app.core.permisos import MATRIZ_PERMISOS; print(len(MATRIZ_PERMISOS))"
.venv/Scripts/python.exe -c "from app.main import app; print(len([(r, m) for r, ops in app.openapi()['paths'].items() for m in ops if m in {'get','post','put','patch','delete'}]))"
```

Esperado: **73** operaciones de negocio en la matriz y **75** en `/openapi.json`
(las 73 de `/api/v1` más `GET /` y `GET /health`, que no pasan por la matriz).
Alternativa con el backend levantado:

```powershell
(Invoke-RestMethod http://localhost:8000/openapi.json).paths.PSObject.Properties.Value.PSObject.Properties.Name | Where-Object { $_ -in @('get','post','put','patch','delete') } | Measure-Object
```

### 2.4 Registro en roadmap

Añadir la fila de 022 al índice de `docs/spec/roadmap.md` con estado `[ ]` y la
entrada correspondiente en la lista del Sprint 7. **No** mover 015/016 ni tocar
el Hito 2. La fila se actualiza a `[x]` solo en T6.

## 3. T2 — Borrar el servicio muerto

### Archivos

- Eliminar: `frontend/src/app/features/administracion/services/usuario.service.ts`
- Editar: `docs/spec/stack.md` (árbol de `features/administracion/`, línea ~709)

### Pasos

1. Confirmar cero imports:

   ```powershell
   Get-ChildItem frontend/src -Recurse -File -Include *.ts,*.html |
     Select-String -Pattern 'UsuarioService|usuario\.service'
   ```

   Solo debe aparecer la declaración del propio archivo.

2. Borrar el archivo.
3. En `stack.md`, cambiar `services/ # usuario.service.ts` por
   `services/ # administracion.service.ts`.
4. Verificar de nuevo el `grep` (0 resultados) y ejecutar `ng build`.

### Criterio de cierre

- El archivo no existe.
- `grep` global sin referencias.
- `ng build` limpio.

## 4. T3 — Coherencia documental

### 4.1 `AGENTS.md` §4

Línea 37, dejar la descripción alineada con el código:

- `src/app/shared/` → `(components, config, interfaces, utils)`
- `src/assets/` → `public/`
- features: mantener las seis de negocio y aclarar que `auth` y
  `acceso-denegado` no tienen `routes.ts` propio.
- Si se conserva la mención a `routes.ts`, precisar que el archivo real es
  `<feature>.routes.ts` (p. ej. `administracion.routes.ts`).

### 4.2 `docs/spec/stack.md` §3

1. Árbol de frontend:
   - `assets/` → `public/`
   - `shared/` añade `components/` y `utils/`
   - `features/` lista `dashboard`, `inventario`, `tickets`, `administracion`,
     `compras` y `control`
   - `administracion/services/` cita `administracion.service.ts`
2. **Nota 1:** sustituir «existe además una cuarta feature» por la estructura
   real: seis features de negocio; `auth` y `acceso-denegado` son features de
   soporte sin `routes.ts` propio.
3. **Nota 2:** dejar de afirmar que `shared/components/` está vacío. Debe decir
   que `shared/components/` ya existe y tiene consumidores reales
   (`enlace-invitacion`, `motivo-selector`), que `shared/pipes/` no existe y que
   `shared/utils/` aloja helpers transversales.
4. Revisar que no queden referencias a `src/assets/` ni a `usuario.service.ts`.

### 4.3 `README.md` raíz

- `01_esquema.sql`: **27** tablas de `control` y **24** por tenant.
- Versión de la base: **`021.1`**.
- Añadir «Compras y control SaaS» a los módulos principales si la lista queda
  incompleta.
- No tocar los comandos de arranque ni las variables de entorno.

### 4.4 `frontend/README.md`

Reemplazar el boilerplate por contenido propio y breve:

- requisitos y arranque (`npm start`, puerto 4200);
- build (`npm run build`);
- tests con el workaround de `CHROME_BIN` y `--watch=false`;
- diferencia entre 4200 (dev server) y 8080 (imagen nginx con build congelado);
- estructura `src/app/{core,shared,features}` y assets en `public/`;
- ninguna credencial ni valor de `.env`.

### Criterio de cierre

- `grep` de coherencia sin `src/assets`, `usuario.service.ts`, «cuarta feature»,
  «20 tablas», «17 tablas» ni `013.1`.
- Revisión manual de los cuatro documentos.

## 5. T4 — Dedup frontend de errores HTTP

### 5.1 Test primero (rojo)

Crear `frontend/src/app/shared/utils/errores-http.spec.ts` antes del helper.
Debe fijar:

- `detail` textual devuelve el texto tal cual;
- `detail` no textual (lista de Pydantic), vacío o con solo espacios usa el
  mapeo por estado;
- `status === 0` devuelve el mensaje de servidor inalcanzable;
- cada helper de dominio conserva **literalmente** sus textos para
  `401/403/404/409/422/503/0/default`;
- el fallback de `producto` es «No se pudo cargar el detalle del producto
  (HTTP N).» y el del resto es «No se pudo completar la operación (HTTP N).».

Ejecutar el spec y confirmar que falla porque
`shared/utils/errores-http.ts` aún no existe.

### 5.2 Implementación

Crear `frontend/src/app/shared/utils/errores-http.ts`:

```ts
export interface MensajesDeErrorHttp {
  readonly 401: string;
  readonly 403: string;
  readonly 404: string;
  readonly 409: string;
  readonly 422: string;
  readonly 503?: string;
  readonly predeterminado: (estado: number) => string;
}

export function mensajeDeErrorHttp(
  error: HttpErrorResponse,
  mensajes: MensajesDeErrorHttp,
): string
```

Comportamiento:

1. Si `error.error.detail` es string no vacío, devolverlo sin transformar.
2. `401/403/404/409/422` devuelven el texto del dominio.
3. `503` devuelve su texto si existe; si no, `predeterminado(503)`.
4. `0` devuelve el texto común de servidor inalcanzable.
5. Cualquier otro estado devuelve `predeterminado(error.status)`.

### 5.3 Delegación de los seis helpers

Mantener nombre y firma en:

- `features/administracion/administracion-errores.ts`
- `features/compras/compras-errores.ts`
- `features/control/control-errores.ts`
- `features/inventario/inventario.component.ts` (`mensajeDeErrorCatalogo`)
- `features/inventario/producto-detalle.component.ts` (`mensajeDeErrorProducto`)
- `features/tickets/ticket-detalle.component.ts` (`mensajeDeErrorTickets`)

Cada uno pasa su tabla de textos al helper. **No** se mueven de archivo ni se
renombran: eso evita tocar imports y conserva la API interna.

### 5.4 Verificación

```powershell
cd frontend
$env:CHROME_BIN = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
npx ng test --watch=false --browsers=ChromeHeadless
npx ng build
```

Esperado: 537 tests previos + los nuevos, 0 fallos; build limpio.

## 6. T5 — Dedup backend de `_correo_actor`

### 6.1 Test primero (rojo)

Crear `backend/tests/services/test_auth_service.py` con tres casos:

1. `identidad=None` → `"sistema"`.
2. `IdentidadAutenticada(usuario=None, sub="...")` → `"sistema"`.
3. Usuario con correo `"  Admin@Example.COM  "` → `"admin@example.com"`.

El test falla porque `auth_service.correo_del_actor` aún no existe.

### 6.2 Implementación

En `backend/app/services/auth_service.py`, añadir:

```python
def correo_del_actor(identidad: IdentidadAutenticada | None) -> str:
    """Correo normalizado del actor; ``sistema`` si no hay identidad."""
    if identidad is None or identidad.usuario is None:
        return "sistema"
    return security.normalizar_correo(str(identidad.usuario.correo))
```

En `organizacion_service.py` y `usuario_service.py`:

- eliminar la definición local `_correo_actor`;
- importar `correo_del_actor` desde `app.services.auth_service`;
- reemplazar las llamadas `_correo_actor(...)` por `correo_del_actor(...)`.

No cambiar la firma ni el valor de retorno: el contrato de auditoría
(`actor_correo`) se conserva.

### 6.3 Verificación

```powershell
cd backend
.venv/Scripts/python.exe -m pytest tests/services/test_auth_service.py -q
.venv/Scripts/python.exe -m pytest -q
```

Esperado: test nuevo en verde; suite completa con los 1496 tests previos en verde,
88 skipped y los nuevos tests añadidos, 0 fallos.

## 7. T6 — Cierre

### 7.1 Suites y contrato

- `pytest -q` completo.
- `ng test --watch=false --browsers=ChromeHeadless` completo.
- `ng build`.
- Conteo de operaciones: 73 de negocio en la matriz y 75 en OpenAPI (incluye `/` y `/health`).
- `git diff --stat` sin cambios en `database/`, `backend/app/core/permisos.py`,
  `backend/app/models/` ni `frontend/src/app/features/**/*.html` (salvo que un
  cambio documental justificado lo requiera; no se espera).

### 7.2 Recorrido 4200

Con el stack levantado:

1. Abrir `http://localhost:4200`.
2. Iniciar sesión con un usuario QA.
3. Recorrer dashboard, inventario, pedidos y compras lo suficiente para
   confirmar que no hay errores de consola ni pantallas rotas.
4. Confirmar que los textos de error no cambiaron (provocar un 404/409 si es
   posible sin mutar datos).

### 7.3 Humo 8080

```powershell
docker compose -f docker-compose.yml build frontend
docker compose -f docker-compose.yml up -d frontend
```

Abrir `http://localhost:8080`, verificar que la vista nueva/corregida está y que
el flujo básico responde. Recordar: 8080 sirve un build congelado en la imagen;
sin rebuild da falsos negativos.

### 7.4 Evidencia y memoria

- Crear `docs/spec/features/022-mantenimiento-tecnico/evidencia/README.md` con
  tablas de suites, build, OpenAPI, diff y recorrido.
- Actualizar `MEMORY.md` (estado, decisiones y errores a evitar).
- Marcar ACs de `spec.md`, tareas de `tasks.md` y la fila de 022 en
  `roadmap.md`.
- `grep` de coherencia sobre `AGENTS.md`, `MEMORY.md` y `.agents/skills/`.

## 8. Archivos previstos

| Archivo | Tarea | Acción |
|---|---|---|
| `docs/spec/features/022-mantenimiento-tecnico/spec.md` | T1 | Crear |
| `docs/spec/features/022-mantenimiento-tecnico/plan.md` | T1 | Crear |
| `docs/spec/features/022-mantenimiento-tecnico/tasks.md` | T1 | Crear |
| `docs/spec/roadmap.md` | T1/T6 | Registrar y cerrar 022 |
| `frontend/src/app/features/administracion/services/usuario.service.ts` | T2 | Eliminar |
| `docs/spec/stack.md` | T2/T3 | Corregir árbol y notas |
| `AGENTS.md` | T3 | Corregir §4 |
| `README.md` | T3 | Actualizar base y módulos |
| `frontend/README.md` | T3 | Reemplazar boilerplate |
| `frontend/src/app/shared/utils/errores-http.ts` | T4 | Crear |
| `frontend/src/app/shared/utils/errores-http.spec.ts` | T4 | Crear |
| `frontend/src/app/features/administracion/administracion-errores.ts` | T4 | Delegar |
| `frontend/src/app/features/compras/compras-errores.ts` | T4 | Delegar |
| `frontend/src/app/features/control/control-errores.ts` | T4 | Delegar |
| `frontend/src/app/features/inventario/inventario.component.ts` | T4 | Delegar |
| `frontend/src/app/features/inventario/producto-detalle.component.ts` | T4 | Delegar |
| `frontend/src/app/features/tickets/ticket-detalle.component.ts` | T4 | Delegar |
| `backend/app/services/auth_service.py` | T5 | Añadir `correo_del_actor` |
| `backend/app/services/organizacion_service.py` | T5 | Usar helper |
| `backend/app/services/usuario_service.py` | T5 | Usar helper |
| `backend/tests/services/test_auth_service.py` | T5 | Crear |
| `docs/spec/features/022-mantenimiento-tecnico/evidencia/README.md` | T6 | Crear |
| `MEMORY.md` | T6 | Actualizar |

## 9. Rollback

Cada tarea es independiente en git. Si una falla:

- T2/T3: revertir el archivo o la edición documental; no afectan runtime.
- T4: restaurar los seis helpers y borrar el helper compartido/spec.
- T5: restaurar `_correo_actor` local y borrar `correo_del_actor`.
- T6: no marcar `[x]`; la feature queda `[!]` o `[ ]` según corresponda.

No se reescribe historia ni se hace `reset --hard` sobre trabajo ajeno.
