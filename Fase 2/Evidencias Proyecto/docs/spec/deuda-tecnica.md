# DOCUMENTO UNICO: Deuda Técnica Abierta

> **Fuente:** Este es el registro único de toda deuda técnica abierta. Ningún otro archivo (`AGENTS.md`, `roadmap.md`, `MEMORY.md`) repite hallazgo, severidad ni recomendación. Si un ítem tiene feature asignada, se traslada a su `spec.md` y aquí queda marcado como absorbido.

## §1 Deuda de seguridad y despliegue

Severidad en entorno **dev** (local, 127.0.0.1) vs **producción** (servidor público). La columna "Dev" refleja el impacto actual; "Prod" refleja qué pasaría si el sistema quedara expuesto.

| ID | Hallazgo | Dev | Prod | Cierre propuesto |
|----|----------|-----|------|------------------|
| **DT-01** | `8000` publicado + `LIMITE_TASA_CONFIAR_PROXY=true` en `docker-compose.yml`. Quien alcance el puerto saltándose nginx puede falsificar `X-Real-IP` y evadir el límite distribuido de la 025 (además de acceder a `/docs`/`/openapi.json`). | Media | **Alta** | No publicar 8000 (red interna solo) **o** `LIMITE_TASA_CONFIAR_PROXY=false` si no hay proxy delante. Ideal: `false` por defecto y `true` solo en la red del proxy. |
| **DT-02** | `AZP_PERMITIDOS` hardcodeado a `localhost:4200/8080` en `backend/app/core/security.py`. Con un dominio real, **todos** los logins fallarán con 401 (falla cerrado, no es vuln, pero mina el despliegue). | Media | **Alta** | Derivar de `ALLOWED_ORIGINS` o hacerlo configurable por entorno. No tocar `security.py` a mano; es variable de entorno. |
| **DT-03** | PostgreSQL publicado en `5433:5432` con credenciales por defecto `postgres/postgres`. | Media | **Crítica** | No publicar el puerto en producción; fijar `DB_PASSWORD` fuerte. En local es irrelevante pero hay que documentarlo. |
| **DT-04** | Cabeceras de seguridad de nginx: por herencia `add_header`, los `location` con sus propias directivas **pierden** `nosniff`/`X-Frame-Options`; no hay CSP, `Referrer-Policy`, `Permissions-Policy`, `server_tokens off`. | Baja | Baja | Añadir `add_header` en cada `location` que lo requiera, `server_tokens off`, CSP/Referrer-Policy/Permissions-Policy completas. |
| **DT-05** | El 429 de nginx (`@limite_api`) refleja **cualquier** `Origin` (sin `Allow-Credentials`), mientras el 429 de la app sí valida origen. Inconsistente entre capas. | Baja | Baja | Reusar la lista permitida (`ALLOWED_ORIGINS`) también en la configuración del 429 de nginx. |
| **DT-06** | Sin TLS/HSTS en ningún punto. Todo HTTP local. | Baja | **Alta** | Terminación TLS en el borde (nginx o balanceador). HSTS `preload` una vez en producción. |
| **DT-07** | Sin CI automatizada, ni `pip-audit`/`npm audit`, ni Dependabot. `pip check` es manual; `npm audit` no se corre. | Baja | Media | Añadir workflow mínimo (tests + auditoría de dependencias) al cerrar el Hito 2. |
| **DT-08** | `/docs`, `/redoc`, `/openapi.json` abiertos en el backend (default FastAPI). No salen por nginx, pero sí por el 8000 publicado (DT-01). | Info | Media | Deshabilitarlos o protegerlos (`python -m uvicorn ... --limit-max-requests ...` o middleware) en producción. |
| **DT-09** | `environment.ts` compila la `pk_test` (clave pública por diseño) y usa la instancia **dev** de Clerk. | Info | Media | Instancia de producción + inyección por entorno (`environment.prod.ts`). La clave `pk_test` por sí misma no es una fuga; es el patrón esperado. |

**Nota sobre DT-09:** `pk_test` es el patrón estándar de Clerk; lo que se cierra es cambiar a instancia de producción y claves `pk_live`, no la clave en sí.

## §2 Otras deudas abiertas (sin feature asignada)

| ID | Hallazgo | Origen | Seguimiento |
|----|----------|--------|-------------|
| **DT-10** | Caché de lecturas sin feature propia. Quedó fuera de alcance en la 025 (solo límite de tasa distribuido). | Decision de la 025 | Quedará sin feature asignada hasta que haya un spec/plan propio; se indica en roadmap.md y MEMORY.md como "sin feature". |
| **DT-11** | `admin017.test+clerk_test@example.com` existe en Clerk pero no está mapeado en la BD actual (el Admin mapeado es `admin020`, usuario 13 de INST-001). | Seed inicial + mapeo de usuario | Pendiente de validar contra el flujo real; no bloquea funcionalidad actual. |
| **DT-12** | Aviso de accesibilidad en el buscador operativo de inventario. | UI/UX | Pendiente de diseño; no es bloqueador de la API. |

## §3 Riesgos aceptados (no deuda, decisión deliberada)

| ID | Hallazgo | Justificación | Condición que lo invalidaría |
|----|----------|---------------|------------------------------|
| **R-01** | Fail-open del límite distribuido (025): si Redis cae, pasa todo el tráfico. | Prioriza disponibilidad sobre pureza del límite. En local evita que el API caiga por un problema del limitador. | Tener proxy delante con salud check de Redis antes del backend. |
| **R-02** | Presupuesto compartido por NAT: varios usuarios tras la misma IP pública comparten límite de 120/min. | El límite es por IP, no por identidad de usuario; aceptado por diseño en la 025. | Migrar a límite por identidad (jwt `sub` o clerk `sub`) — fuera de alcance actual. |
| **R-03** | `/metrics` protegido por red (nginx 404), no por rol. | Aceptado para local; en producción el puerto no se publica o hay VLAN privada. | Publicar el puerto sin restricción adicional. |
| **R-04** | `X-Request-ID` del cliente aceptado si es UUID canónico. | El cliente puede proveer su propia cabecera de correlación; validado con regex estricta. | Permitir cualquier string sin validación (ya no cumplo el requisito de seguridad). |

## §4 Evidencia de la auditoría

- **Fecha:** 16/Nov/2026
- **Alcance:** 10 hallazgos (F1–F10 de la auditoría de seguridad de solo lectura)
- **Resultado:** 0 críticas, 0 altas, 2 medias, 5 bajas, 3 informativas
- **Archivos revisados:** `docker-compose.yml`, `frontend/nginx.conf`, `backend/app/core/security.py`, `backend/app/main.py`, `backend/app/core/observabilidad.py`, `frontend/src/environments/environment.ts`, `.gitignore`, `env.example`, grep de SQL crudo
- **Herramientas:** `grep`, lectura directa, inspección de contenedores Docker vivos

## §5 Regla de mantenimiento

Un ítem vive en este registro mientras **no tenga feature propia**. Cuando la tenga:

1. Se crea `docs/spec/features/NNN-nombre/` con `spec.md`, `plan.md`, `tasks.md`.
2. El ítem se **traslada** a su `spec.md` (dentro de los AC o como nota al pie) y aquí queda marcado como **absorbido**.
3. Si la feature se cierra y la deuda queda abierta, se **revive** en este registro con nuevo ID o se mantiene la referencia.

El registro no se convierte en un cementerio: cada línea tiene dueño, severidad y fecha de última revisión.

---
*Última revisión: 16/Nov/2026 — auditoría de seguridad de solo lectura completa.*