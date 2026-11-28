# `_datos/` — snapshots de entrada de los generadores de informe

Estos archivos son **entradas generadas**, no fuentes normativas. Se producen desde el
árbol del repositorio y alimentan a `_generar_planilla_pruebas.py`.

| Archivo | Origen | Estado |
|---|---|---|
| `backend-coleccion-027.txt` | `cd backend && pytest --collect-only -q` | **Línea base del cierre 027** (24/Nov/2026) |
| `frontend-specs.json` | `node docs/informes/_datos/extraer_specs.js` | **Línea base del cierre 027** (24/Nov/2026) |

> **Histórico.** Ambos snapshots y el `Planilla_Pruebas_Compustock.xlsx` versionado
> pertenecen al cierre de la Feature 027 y todavía incluyen la vista y los casos de
> **encargados**, retirados por la enmienda de la Feature 012 el 27/Nov/2026. No se
> regeneraron en ese cierre: el binario y sus datos deben re-baselinarse juntos (ver el
> docstring de `_generar_planilla_pruebas.py`), porque `Planilla` fija conteos y fechas de
> la corrida.
