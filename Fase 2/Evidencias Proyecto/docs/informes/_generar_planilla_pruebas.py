#!/usr/bin/env python3
"""Genera la planilla Excel de pruebas de Compustock ERP.

Uso:
    python docs/informes/_generar_planilla_pruebas.py

Fuente de estado: evidencia consolidada del cierre 027 (24/Nov/2026).
No ejecuta la suite: enumera los casos con `pytest --collect-only` y usa los
conteos documentados en `docs/spec/features/027-validacion-entradas/evidencia/README.md`.

> **Artefacto histórico.** El `Planilla_Pruebas_Compustock.xlsx` versionado y los
> snapshots `_datos/backend-coleccion-027.txt` y `_datos/frontend-specs.json` son la
> **línea base del cierre 027** y, por tanto, todavía incluyen la vista y los casos de
> `encargados`, retirados por la enmienda de la Feature 012 (27/Nov/2026). No se
> regeneraron en el cierre de esa enmienda: re-baselinar exige
> `pytest --collect-only -q` y `node docs/informes/_datos/extraer_specs.js` sobre el
> árbol actual, actualizar `TOTAL_BACKEND`/`TOTAL_FRONTEND`/`BACKEND_*_OK` y `FECHA`, y
> recortar `PESTANAS` a 3 entradas. Hasta entonces, la planilla **no** describe el
> estado vigente del frontend.

Salida:
    docs/informes/Planilla_Pruebas_Compustock.xlsx
"""
from __future__ import annotations

import ast
import io
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

RAIZ = Path(__file__).resolve().parents[2]
BACKEND = RAIZ / "backend"
FRONTEND = RAIZ / "frontend"
DATOS = RAIZ / "docs" / "informes" / "_datos"
COLECCION = DATOS / "backend-coleccion-027.txt"
SPECS_JSON = DATOS / "frontend-specs.json"
SALIDA = RAIZ / "docs" / "informes" / "Planilla_Pruebas_Compustock.xlsx"

FECHA = date(2026, 11, 24)
FECHA_TEXTO = "24/Nov/2026"

# Conteos del cierre 027 (evidencia de la feature 027).
TOTAL_BACKEND = 1972
BACKEND_SQLITE_OK = 1863
BACKEND_BD_OK = 106
BACKEND_REDIS_OK = 3
TOTAL_FRONTEND = 597

# ---------------------------------------------------------------------------
# Metadatos de features y módulos
# ---------------------------------------------------------------------------

FEATURES = {
    0: "Modelado 3NF y entorno",
    1: "Reestructuración modular",
    2: "Catálogo de insumos",
    3: "Modal de ticket",
    4: "Tablero Kanban",
    5: "Despacho transaccional",
    6: "Autenticación Clerk",
    7: "Control de acceso por roles",
    8: "Particionamiento institucional",
    9: "Dashboard analítico",
    10: "Multi-tenant por esquemas",
    11: "Modelo organizacional",
    12: "Gestión administrativa",
    13: "Ciclo de vida del ticket",
    14: "Ciclo de vida del catálogo",
    15: "Informes PDF/Excel",
    16: "Notificaciones in-app",
    17: "Gobierno de identidades",
    18: "Filtros de inventario",
    19: "Detalle de producto",
    20: "Reabastecimiento y compras",
    21: "Cobertura automática",
    22: "Mantenimiento técnico I",
    23: "Refactor de compras",
    24: "Hardening operativo I",
    25: "Límite de tasa distribuido",
    26: "Salud del esquema BD",
    27: "Validación de entradas",
}

DETALLES_BACKEND = {
    "auth": "Sesión y autenticación",
    "auth_me_institucion": "Identidad e institución en /auth/me",
    "auth_service": "Servicio de autenticación",
    "permisos": "Matriz de permisos",
    "permisos_endpoints": "Permisos por endpoint",
    "retiro_password": "Retiro de password local",
    "rol_asignable_usuarios": "Roles asignables",
    "tablero_kanban": "Tablero Kanban",
    "modal_ticket": "Modal de ticket",
    "transaccion_ticket": "Transacción de ticket",
    "despacho_transaccional": "Despacho transaccional",
    "despacho_dtos": "DTOs de despacho",
    "historial_movimientos": "Historial de movimientos",
    "tickets_alcance": "Alcance de tickets",
    "tickets_institucional": "Tickets institucionales",
    "dashboard_analitico": "Dashboard analítico",
    "dashboard_service": "Servicio de dashboard",
    "catalogo_consulta": "Consulta de catálogo",
    "compras": "Compras",
    "compra_service_estructura": "Estructura del servicio de compras",
    "control_instituciones": "Control de instituciones",
    "control_modelo": "Modelo de control",
    "aprovisionamiento": "Aprovisionamiento",
    "integracion_multitenant": "Integración multi-tenant",
    "contexto_tenant_sqlite": "Contexto de tenant en SQLite",
    "modelo_particionamiento": "Particionamiento",
    "ambito_institucional": "Ámbito institucional",
    "organizacion": "Organización",
    "espejo_institucion": "Espejo de institución",
    "contrato_organizacion": "Contrato de organización",
    "contrato_control": "Contrato de control",
    "gobierno_identidades": "Gobierno de identidades",
    "gobierno_administradores": "Gobierno de administradores",
    "gobierno_lecturas": "Gobierno de lecturas",
    "provisionamiento_identidades": "Provisionamiento de identidades",
    "frontera_clerk": "Frontera Clerk",
    "aceptacion_invitacion": "Aceptación de invitaciones",
    "esquema_postgres": "Esquema PostgreSQL",
    "instalacion_limpia_postgres": "Instalación limpia",
    "salud_esquema": "Salud del esquema",
    "salud_esquema_postgres": "Salud del esquema (PostgreSQL)",
    "esquemas_027": "Esquemas Pydantic",
    "rut_027": "RUT",
    "semilla_rut_027": "Semilla RUT",
    "errores_bd_027": "Errores de BD",
    "validacion_entradas_027": "Validación de entradas",
    "validacion_entradas_postgres_027": "Validación de entradas (PostgreSQL)",
    "configuracion_base_datos": "Configuración de BD",
    "limite_tasa_025": "Límite de tasa",
    "limite_tasa_failopen_025": "Límite de tasa fail-open",
    "limite_tasa_redis_025": "Límite de tasa (Redis)",
    "limite_tasa_unidad_025": "Límite de tasa (unidad)",
    "metricas_024": "Métricas Prometheus",
    "metricas_limite_tasa_025": "Métricas del límite de tasa",
    "configuracion_024": "Configuración",
    "configuracion_025": "Configuración del límite de tasa",
    "contrato_024": "Contrato OpenAPI",
    "dependencias_024": "Dependencias",
    "correlacion_024": "Correlación X-Request-ID",
    "cors_024": "CORS",
    "salud_024": "Salud y readiness",
    "smoke": "Humo de la API",
    "aislamiento_sede_011": "Aislamiento por sede",
    "aislamiento_tenant_010": "Aislamiento por tenant",
    "correcciones_postgres": "Correcciones PostgreSQL",
    "lectura_global_tickets": "Lectura global de tickets",
    "control_sede_011": "Control por sede",
    "modelo_sede_011": "Modelo de sede",
    "dashboard_sede_011": "Dashboard por sede",
    "inventario_sede_011": "Inventario por sede",
    "ticket_sede_011": "Ticket por sede",
    "organizacion_011": "Organización",
    "organizacion_crud_012": "CRUD de organización",
    "gestion_administrativa_http_postgres_012": "Gestión administrativa HTTP (PostgreSQL)",
    "gestion_administrativa_postgres_012": "Gestión administrativa (PostgreSQL)",
    "gobierno_correcciones_017": "Correcciones de gobierno",
    "cobertura_021": "Cobertura de pedidos",
    "cobertura_ac_008": "Cobertura de AC de la 008",
    "compras_endpoints_020": "Endpoints de compras",
    "compras_postgres_020": "Compras (PostgreSQL)",
    "ciclo_vida_catalogo_postgres_014": "Ciclo de vida del catálogo (PostgreSQL)",
    "ciclo_vida_ticket_postgres_013": "Ciclo de vida del ticket (PostgreSQL)",
    "ciclo_vida_flujo_013": "Ciclo de vida del ticket (flujo)",
    "cobertura_postgres_021": "Cobertura de pedidos (PostgreSQL)",
    "filtros_inventario_018": "Filtros de inventario",
    "filtros_inventario_postgres_018": "Filtros de inventario (PostgreSQL)",
    "detalle_producto_019": "Detalle de producto",
    "detalle_producto_postgres_019": "Detalle de producto (PostgreSQL)",
    "dto_ambito_018": "DTO de ámbito",
    "dashboard_tecnico_017": "Dashboard técnico",
    "dashboard_tecnico_postgres_017": "Dashboard técnico (PostgreSQL)",
    "capacidades_gating_012": "Gating de capacidades",
    "gating_capacidades_endpoints_012": "Gating de capacidades por endpoint",
    "institucion_inactiva_012": "Institución inactiva",
    "inventario_sede_011": "Inventario por sede",
    "bootstrap_control_postgres_010": "Bootstrap de control (PostgreSQL)",
    "control_postgres_010": "Control (PostgreSQL)",
    "aprovisionamiento_postgres_010": "Aprovisionamiento (PostgreSQL)",
    "aceptacion_invitacion_postgres_017": "Aceptación de invitaciones (PostgreSQL)",
    "salud_esquema_postgres_026": "Salud del esquema (PostgreSQL)",
}

DOMINIOS_BACKEND = [
    ("auth", "Autenticación"),
    ("permiso", "Autorización"),
    ("retiro_password", "Seguridad"),
    ("rol_asignable", "Administración"),
    ("tablero", "Tickets"),
    ("modal_ticket", "Tickets"),
    ("transaccion_ticket", "Tickets"),
    ("despacho", "Tickets"),
    ("historial_movimientos", "Tickets"),
    ("tickets", "Tickets"),
    ("ticket_sede", "Tickets"),
    ("ciclo_vida_ticket", "Tickets"),
    ("dashboard", "Dashboard"),
    ("catalogo", "Catálogo"),
    ("ciclo_vida_catalogo", "Catálogo"),
    ("inventario", "Inventario"),
    ("filtros_inventario", "Inventario"),
    ("detalle_producto", "Inventario"),
    ("dto_ambito", "Inventario"),
    ("compras", "Compras"),
    ("compra_service", "Compras"),
    ("cobertura", "Compras"),
    ("control", "Control SaaS"),
    ("aprovisionamiento", "Control SaaS"),
    ("integracion_multitenant", "Control SaaS"),
    ("contexto_tenant", "Control SaaS"),
    ("modelo_particionamiento", "Multi-tenant"),
    ("aislamiento", "Seguridad"),
    ("ambito_institucional", "Organización"),
    ("organizacion", "Organización"),
    ("espejo_institucion", "Organización"),
    ("contrato_organizacion", "Organización"),
    ("contrato_control", "Control SaaS"),
    ("gobierno", "Identidades"),
    ("provisionamiento_identidades", "Identidades"),
    ("frontera_clerk", "Identidades"),
    ("aceptacion_invitacion", "Identidades"),
    ("esquema", "Base de datos"),
    ("instalacion", "Base de datos"),
    ("salud_esquema", "Base de datos"),
    ("semilla", "Validación"),
    ("validacion", "Validación"),
    ("errores_bd", "Validación"),
    ("esquemas_027", "Validación"),
    ("rut", "Validación"),
    ("configuracion_base_datos", "Validación"),
    ("limite_tasa", "Hardening"),
    ("metricas", "Hardening"),
    ("configuracion", "Hardening"),
    ("contrato", "Hardening"),
    ("dependencias", "Hardening"),
    ("correlacion", "Hardening"),
    ("cors", "Hardening"),
    ("salud_024", "Hardening"),
    ("smoke", "Salud"),
]

DETALLES_FRONTEND = {
    "app.component": "Shell de la aplicación",
    "app.routes": "Rutas raíz",
    "roles": "Roles y capacidades",
    "auth.guard": "Guard de autenticación",
    "role.guard": "Guard de rol",
    "control-superadmin.guard": "Guard del panel SaaS",
    "superficies-retiradas": "Superficies retiradas",
    "tickets-acceso": "Acceso a tickets",
    "token.interceptor": "Interceptor de token",
    "auth.service": "Servicio de autenticación",
    "acceso-denegado.component": "Acceso denegado",
    "login.component": "Login Clerk",
    "administracion-nav.component": "Navegación ARIA",
    "departamentos.component": "Departamentos",
    # Histórico (línea base 027): el spec y la vista se retiraron en la enmienda de la 012.
    "encargados.component": "Encargados",
    "sedes.component": "Sedes",
    "usuarios.component": "Usuarios",
    "administracion.service": "Servicio de administración",
    "administracion.routes": "Rutas de administración",
    "lista-ordenes.component": "Órdenes de compra",
    "necesidades.component": "Necesidades",
    "nueva-orden.component": "Nueva orden",
    "recepcion-bodega.component": "Recepción en bodega",
    "compras.service": "Servicio de compras",
    "compras.routes": "Rutas de compras",
    "administradores-control.component": "Administradores",
    "alta-institucion.component": "Alta de institución",
    "capacidades.component": "Capacidades",
    "control-login.component": "Acceso al panel",
    "control.routes": "Rutas del panel",
    "dashboard-saas.component": "Dashboard SaaS",
    "instituciones.component": "Instituciones",
    "control.service": "Servicio de control",
    "dashboard.component": "Métricas y alertas",
    "dashboard.service": "Servicio de dashboard",
    "inventario.component": "Existencias",
    "producto-detalle.component": "Detalle de producto",
    "inventario.service": "Servicio de inventario",
    "ticket-detalle.component": "Detalle de ticket",
    "tickets.component": "Listado y alta",
    "errores-http": "Errores HTTP",
    "etiqueta-estado": "Etiquetas de estado",
    "rut": "RUT",
    "validacion-http": "Validación HTTP",
}

DOMINIOS_FRONTEND = {
    "dashboard": "Dashboard",
    "inventario": "Inventario",
    "tickets": "Tickets",
    "administracion": "Administración",
    "compras": "Compras",
    "control": "Control SaaS",
    "auth": "Autenticación",
    "acceso-denegado": "Autorización",
}

# Pestañas de administración usadas por los 4 casos dinámicos de ARIA.
# Histórico (línea base 027): la enmienda de la 012 retiró /administracion/encargados y
# dejó 3 pestañas; recortar esta lista al re-baselinar la planilla (ver docstring).
PESTANAS = [
    {"href": "/administracion/sedes", "etiqueta": "Sedes"},
    {"href": "/administracion/departamentos", "etiqueta": "Departamentos"},
    {"href": "/administracion/usuarios", "etiqueta": "Usuarios"},
    {"href": "/administracion/encargados", "etiqueta": "Encargados"},
]

EXPANSIONES_FRONTEND = {
    ("frontend/src/app/core/guards/superficies-retiradas.spec.ts", 52): [
        {"ruta": r} for r in ["/dashboard", "/inventario", "/tickets", "/administracion"]
    ],
    ("frontend/src/app/features/administracion/administracion-nav.component.spec.ts", 164): [
        {"esperada.href": p["href"]} for p in PESTANAS
    ],
    ("frontend/src/app/features/administracion/administracion-nav.component.spec.ts", 219): [
        {"esperada.href": p["href"]} for p in PESTANAS
    ],
    ("frontend/src/app/features/administracion/administracion-nav.component.spec.ts", 305): [
        {
            "origen.etiqueta": PESTANAS[i]["etiqueta"],
            "siguiente.etiqueta": PESTANAS[(i + 1) % len(PESTANAS)]["etiqueta"],
        }
        for i in range(len(PESTANAS))
    ],
    ("frontend/src/app/features/administracion/administracion-nav.component.spec.ts", 336): [
        {
            "origen.etiqueta": PESTANAS[i]["etiqueta"],
            "anterior.etiqueta": PESTANAS[(i - 1) % len(PESTANAS)]["etiqueta"],
        }
        for i in range(len(PESTANAS))
    ],
    ("frontend/src/app/features/inventario/inventario.component.spec.ts", 664): [
        {"rol": r} for r in ["Bodeguero", "Solicitante"]
    ],
    ("frontend/src/app/features/inventario/inventario.component.spec.ts", 1362): [
        {"rol": r} for r in ["Administrador", "Bodeguero", "Solicitante"]
    ],
    ("frontend/src/app/features/inventario/inventario.component.spec.ts", 1396): [
        {"rol": r} for r in ["Bodeguero", "Solicitante"]
    ],
    ("frontend/src/app/features/inventario/producto-detalle.component.spec.ts", 234): [
        {"invalido": v} for v in ["0", "-3", "1abc"]
    ],
}

# ---------------------------------------------------------------------------
# Utilidades de texto
# ---------------------------------------------------------------------------


def humanizar(texto: str) -> str:
    texto = texto.replace("_", " ")
    texto = re.sub(r"\bac (\d+)\b", r"(AC-\1)", texto, flags=re.IGNORECASE)
    texto = re.sub(r"\s+", " ", texto).strip()
    reemplazos = {
        "dto": "DTO",
        "dtos": "DTOs",
        "http": "HTTP",
        "api": "API",
        "openapi": "OpenAPI",
        "json": "JSON",
        "ddl": "DDL",
        "fk": "FK",
        "uuid": "UUID",
        "p0": "P0",
        "bd": "BD",
        "id": "ID",
        "rut": "RUT",
        "oc": "OC",
        "ui": "UI",
        "ac": "AC",
        "postgres": "PostgreSQL",
        "redis": "Redis",
    }
    palabras = [reemplazos.get(p.lower(), p) for p in texto.split(" ")]
    texto = " ".join(palabras)
    texto = re.sub(r"\b(\d{3}) (\d{1,2})\b", r"\1.\2", texto)
    return texto[:1].upper() + texto[1:] if texto else texto


def primer_parrafo(doc: str) -> str:
    if not doc:
        return ""
    parrafos = re.split(r"\n\s*\n", doc.strip())
    texto = parrafos[0].strip() if parrafos else ""
    texto = re.sub(r"\s+", " ", texto)
    return texto


def recortar(texto: str, maximo: int = 320) -> str:
    texto = re.sub(r"\s+", " ", texto).strip()
    if len(texto) <= maximo:
        return texto
    return texto[: maximo - 1].rstrip() + "…"


def miles(numero: int) -> str:
    return f"{numero:,}".replace(",", ".")


def plural(numero: int, singular: str, plural_: str) -> str:
    return f"{numero} {singular if numero == 1 else plural_}"


def resumir_assert(expr: str) -> str:
    expr = re.sub(r"\s+", " ", expr.strip())
    m = re.search(r"status_code\s*==\s*(\d{3})", expr)
    if m:
        return f"HTTP {m.group(1)}"
    m = re.search(r"status_code\s*in\s*\(([^)]+)\)", expr)
    if m:
        codigos = re.findall(r"\d{3}", m.group(1))
        return "HTTP " + " o ".join(codigos)
    if expr == "not errores":
        return "no se registran errores"
    m = re.search(r"sorted\(([^)]+)\)\s*==\s*\[([^\]]+)\]", expr)
    if m:
        return f"{m.group(1).strip()} ordenadas = [{m.group(2).strip()}]"
    m = re.search(r"len\(([^)]+)\)\s*==\s*(\d+)", expr)
    if m:
        return f"{m.group(1).strip()} tiene {m.group(2)} elementos"
    if expr.startswith("all("):
        return "todas las condiciones se cumplen"
    if expr.startswith("any("):
        return "alguna condición se cumple"
    if re.search(r"\bis None\b", expr):
        return "valor nulo"
    if "not in" in expr:
        return "no incluye el valor esperado"
    if " in " in expr:
        return "incluye el valor esperado"
    if "==" in expr:
        izq, der = expr.split("==", 1)
        return f"{izq.strip()[-80:]} = {der.strip()[:80]}"
    return expr[:120]


def resumen_asserts(asserts: list[str], maximo: int = 2) -> str:
    if not asserts:
        return ""
    partes = [resumir_assert(a) for a in asserts[:maximo]]
    return "; ".join(partes)


def extraer_ac(texto: str) -> list[str]:
    encontrados = re.findall(r"AC-\d+", texto or "")
    return sorted(set(encontrados), key=lambda x: int(x.split("-")[1]))


def extraer_features(texto: str) -> list[int]:
    return sorted({int(n) for n in re.findall(r"Feature\s+(\d{3})", texto or "")})


# ---------------------------------------------------------------------------
# Backend: colección, AST y clasificación
# ---------------------------------------------------------------------------


def leer_coleccion() -> list[str]:
    lineas = io.open(COLECCION, encoding="utf-8-sig").read().splitlines()
    return [l.strip() for l in lineas if l.strip().startswith("tests/") and "::" in l]


def archivos_gated_pg() -> set[str]:
    gated = set()
    for py in BACKEND.glob("tests/**/test_*.py"):
        texto = py.read_text(encoding="utf-8")
        if "pytestmark = pytest.mark.skipif(" in texto and "POSTGRES_TEST_URL" in texto:
            gated.add(py.relative_to(BACKEND).as_posix())
    return gated


def parsear_ast_backend() -> dict[str, dict]:
    meta = {}
    for py in BACKEND.glob("tests/**/test_*.py"):
        rel = py.relative_to(BACKEND).as_posix()
        arbol = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        funciones = {}
        for nodo in ast.walk(arbol):
            if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)) and nodo.name.startswith("test_"):
                funciones[nodo.name] = {
                    "linea": nodo.lineno,
                    "doc": ast.get_docstring(nodo) or "",
                    "asserts": [ast.unparse(n.test) for n in ast.walk(nodo) if isinstance(n, ast.Assert)],
                    "args": [a.arg for a in nodo.args.args],
                }
        meta[rel] = {"doc_modulo": ast.get_docstring(arbol) or "", "funciones": funciones}
    return meta


def tipo_prueba_backend(archivo: str) -> str:
    if "/unitarios/" in archivo:
        return "Unitario"
    if "/integracion/" in archivo:
        return "Integración"
    if "/sistema/" in archivo:
        return "Sistema"
    if "/e2e/" in archivo:
        return "E2E"
    if "/humo/" in archivo:
        return "Humo"
    if "/rendimiento/" in archivo:
        return "Rendimiento"
    if "/seguridad/" in archivo:
        return "Seguridad"
    if "/aceptacion/" in archivo:
        return "Aceptación"
    return "Integración"


def feature_backend(archivo: str, doc_modulo: str) -> int:
    stem = Path(archivo).stem
    m = re.search(r"_(\d{3})$", stem)
    if m:
        return int(m.group(1))
    reglas = [
        ("auth", 6),
        ("permiso", 7),
        ("retiro_password", 7),
        ("rol_asignable", 12),
        ("tablero_kanban", 4),
        ("modal_ticket", 3),
        ("transaccion_ticket", 3),
        ("despacho", 5),
        ("historial_movimientos", 5),
        ("tickets_alcance", 13),
        ("tickets_institucional", 8),
        ("dashboard", 9),
        ("catalogo_consulta", 2),
        ("compras", 20),
        ("compra_service", 23),
        ("control", 10),
        ("aprovisionamiento", 10),
        ("integracion_multitenant", 10),
        ("contexto_tenant", 10),
        ("modelo_particionamiento", 8),
        ("ambito_institucional", 8),
        ("organizacion", 12),
        ("espejo_institucion", 12),
        ("contrato_organizacion", 12),
        ("gobierno", 17),
        ("provisionamiento_identidades", 17),
        ("frontera_clerk", 17),
        ("aceptacion_invitacion", 17),
        ("esquema", 26),
        ("instalacion", 26),
        ("salud_esquema", 26),
        ("semilla", 27),
        ("validacion", 27),
        ("errores_bd", 27),
        ("esquemas_027", 27),
        ("rut", 27),
        ("configuracion_base_datos", 27),
        ("limite_tasa", 25),
        ("metricas", 24),
        ("configuracion", 24),
        ("contrato", 24),
        ("dependencias", 24),
        ("correlacion", 24),
        ("cors", 24),
        ("salud_024", 24),
        ("smoke", 1),
    ]
    for clave, feature in reglas:
        if clave in stem:
            return feature
    menciones = extraer_features(doc_modulo)
    if menciones:
        return menciones[0]
    return 1


def modulo_backend(archivo: str) -> str:
    stem = Path(archivo).stem[len("test_") :]
    stem_sin_sufijo = re.sub(r"_\d{3}$", "", stem)
    detalle = DETALLES_BACKEND.get(stem, DETALLES_BACKEND.get(stem_sin_sufijo))
    if not detalle:
        detalle = humanizar(stem_sin_sufijo)
    dominio = "Backend"
    for clave, valor in DOMINIOS_BACKEND:
        if clave in stem:
            dominio = valor
            break
    return f"{dominio} · {detalle}"


def contexto_backend(archivo: str, tipo: str, tipo_prueba: str, modulo: str) -> str:
    stem = Path(archivo).stem
    if tipo == "BD":
        return (
            "Dado PostgreSQL 16 con una base temporal creada desde "
            "`01_esquema.sql` y `02_datos_semilla.sql`."
        )
    if "limite_tasa" in stem:
        return (
            "Dado Redis 7.2 con la base 15 limpia y un presupuesto de "
            "120 solicitudes/60 s por IP real."
        )
    if "semilla" in stem:
        return "Dado los scripts `01_esquema.sql` y `02_datos_semilla.sql` con los RUT de la semilla."
    if "configuracion_base_datos" in stem:
        return "Dado el entorno de configuración de la base de datos y sus variables."
    if "salud_esquema" in stem or "esquema" in stem:
        return "Dado el metadata del ORM y las tablas del esquema."
    if "smoke" in stem or "salud_024" in stem:
        return "Dado el backend en ejecución y la base de datos disponible o detenida."
    if "auth" in stem:
        return "Dado un usuario con identidad Clerk válida y una sesión local resuelta."
    if tipo_prueba == "Seguridad":
        return "Dado un usuario autenticado y la matriz de permisos por rol."
    if "despacho" in stem:
        return "Dado un ticket en curso y stock suficiente o insuficiente en la sede."
    if "ticket" in stem:
        return "Dado un ticket existente y los catálogos de estados, prioridades y productos."
    if "dashboard" in stem:
        return "Dado el agregado de inventario y tickets de una institución."
    if "catalogo" in stem:
        return "Dado el catálogo maestro de categorías y productos de una institución."
    if "inventario" in stem or "detalle_producto" in stem:
        return "Dado el stock por sede y los filtros organizacionales del usuario."
    if "compras" in stem or "cobertura" in stem:
        return "Dado el flujo de necesidades, órdenes de compra y recepción en bodega."
    if "control" in stem or "aprovisionamiento" in stem or "multitenant" in stem:
        return "Dado el contexto global de control y una institución aprovisionada."
    if "organizacion" in stem or "sede" in stem or "departamento" in stem:
        return "Dado el modelo de sedes, departamentos y usuarios de una institución."
    if "gobierno" in stem or "identidades" in stem or "invitacion" in stem:
        return "Dado el mapa de identidades Clerk y las invitaciones persistidas."
    if "validacion" in stem or "errores_bd" in stem or "esquemas" in stem or "rut" in stem:
        return "Dado un contrato Pydantic estricto y datos de entrada válidos o inválidos."
    if tipo_prueba == "Unitario":
        return f"Dado el módulo {modulo} con datos de entrada controlados."
    return f"Dado el contexto del módulo {modulo} con las fixtures de prueba."


def evaluar_critica(
    tipo: str, tipo_prueba: str, archivo: str, nombre: str, doc: str, modulo: str
) -> tuple[str, str]:
    # La clasificación se apoya en la ruta del archivo, no en menciones
    # incidentales de roles o instituciones dentro del docstring o del módulo.
    base = archivo.lower()
    reglas = [
        (
            ["permiso", "guard", "role", "roles", "auth", "autentic", "acceso", "autoriz", "interceptor"],
            "autorización/autenticación",
        ),
        (["aislamiento", "tenant", "multitenant", "particionamiento"], "aislamiento multi-tenant"),
        (["despacho", "transacc"], "transacción/retiro"),
        (["limite_tasa", "rate_limit", "failopen"], "límite de tasa"),
        (
            ["validacion", "errores", "esquemas_027", "rut", "semilla", "configuracion_base_datos"],
            "validación de contrato",
        ),
        (["esquema", "salud", "instalacion"], "esquema/salud de BD"),
        (["gobierno", "provisionamiento", "frontera_clerk", "invitacion"], "gobierno de identidades"),
        (["cobertura"], "cobertura de pedidos"),
        (["recepcion"], "recepción en bodega"),
        (["anulacion", "rechazo"], "anulación/rechazo de ticket"),
        (["password", "retiro_password"], "credenciales"),
        (["cors", "correlacion"], "borde y observabilidad"),
    ]
    for claves, razon in reglas:
        if any(clave in base for clave in claves):
            return "Sí", razon

    if tipo == "BD":
        return "Sí", "validación sobre PostgreSQL 16"
    if tipo_prueba == "Seguridad":
        return "Sí", "control de seguridad"
    if tipo_prueba == "E2E":
        return "Sí", "flujo E2E de negocio"

    # Flujos de UI que materializan reglas de negocio críticas.
    if tipo == "Frontend":
        criticos_ui = [
            "ticket-detalle",
            "tickets.component",
            "lista-ordenes",
            "nueva-orden",
            "recepcion-bodega",
            "alta-institucion",
            "administradores-control",
            "capacidades",
            "usuarios.component",
            "login.component",
            "acceso-denegado",
        ]
        if any(clave in archivo for clave in criticos_ui):
            return "Sí", "flujo crítico de interfaz"
    return "No", ""


# ---------------------------------------------------------------------------
# Frontend: JSON + expansión de casos dinámicos
# ---------------------------------------------------------------------------


def cargar_frontend() -> list[dict]:
    casos = json.loads(SPECS_JSON.read_text(encoding="utf-8"))
    expandidos = []
    for caso in casos:
        clave = (caso["archivo"], caso["linea"])
        reglas = EXPANSIONES_FRONTEND.get(clave)
        if not reglas:
            caso = dict(caso)
            caso.setdefault("variante", "")
            expandidos.append(caso)
            continue
        for valores in reglas:
            nuevo = dict(caso)
            titulo = nuevo["titulo"]
            for clave_valor, valor in valores.items():
                titulo = titulo.replace("${" + clave_valor + "}", valor)
            nuevo["titulo"] = titulo
            nuevo["nombreCompleto"] = " › ".join(nuevo["suite"] + [titulo])
            nuevo["variante"] = ", ".join(f"{k}={v}" for k, v in valores.items())
            expandidos.append(nuevo)
    return expandidos


def tipo_prueba_frontend(archivo: str) -> str:
    if "/shared/utils/" in archivo or "/core/auth/roles" in archivo:
        return "Unitario"
    if (
        "/services/" in archivo
        or "/guards/" in archivo
        or "/interceptors/" in archivo
        or archivo.endswith("routes.spec.ts")
    ):
        return "Integración"
    return "Sistema"


def feature_frontend(archivo: str) -> int:
    if "features/control" in archivo:
        return 10
    if "features/administracion" in archivo:
        return 12
    if "features/compras" in archivo:
        return 20
    if "features/tickets" in archivo:
        return 13
    if "features/inventario/producto-detalle" in archivo:
        return 19
    if "features/inventario" in archivo:
        return 18
    if "features/dashboard" in archivo:
        return 9
    if "features/auth" in archivo:
        return 6
    if "features/acceso-denegado" in archivo:
        return 7
    if "core/guards" in archivo or "core/auth" in archivo:
        return 7
    if "core/services/auth" in archivo or "core/interceptors" in archivo:
        return 6
    if "shared/utils/etiqueta-estado" in archivo:
        return 13
    if "shared/utils" in archivo:
        return 27
    if "app.component" in archivo or "app.routes" in archivo:
        return 7
    return 1


def modulo_frontend(archivo: str) -> str:
    p = archivo.replace("frontend/src/app/", "").replace(".spec.ts", "")
    partes = p.split("/")
    nombre = partes[-1]
    detalle = DETALLES_FRONTEND.get(nombre, humanizar(nombre.replace(".component", "")))
    if p.startswith("features/"):
        dominio = DOMINIOS_FRONTEND.get(partes[1], humanizar(partes[1]))
        return f"{dominio} · {detalle}"
    if p.startswith("core/guards"):
        return f"Autorización · {detalle}"
    if p.startswith("core/auth"):
        return f"Autorización · {detalle}"
    if p.startswith("core/services"):
        return f"Autenticación · {detalle}"
    if p.startswith("core/interceptors"):
        return f"Autenticación · {detalle}"
    if p.startswith("shared/utils"):
        return f"Utilidades · {detalle}"
    if p == "app.component":
        return f"Shell · {detalle}"
    if p == "app.routes":
        return f"Rutas · {detalle}"
    return f"Frontend · {detalle}"


def contexto_frontend(archivo: str, tipo_prueba: str, modulo: str) -> str:
    if "shared/utils" in archivo or "/core/auth/roles" in archivo:
        return f"Dado el módulo {modulo} con valores de entrada controlados."
    if "/guards/" in archivo or "/interceptors/" in archivo or "/services/" in archivo:
        return f"Dado el servicio, guard o interceptor {modulo} con sus dependencias simuladas."
    if archivo.endswith("routes.spec.ts"):
        return "Dado el router de Angular con las rutas y guards configurados."
    return f"Dado el componente {modulo} montado en TestBed con mocks de HTTP y datos de prueba."


# ---------------------------------------------------------------------------
# Construcción de filas
# ---------------------------------------------------------------------------


@dataclass
class Caso:
    id: str = ""
    nombre: str = ""
    feature_num: int = 0
    feature: str = ""
    modulo: str = ""
    tipo: str = ""
    tipo_prueba: str = ""
    dado: str = ""
    cuando: str = ""
    entonces: str = ""
    esperado: str = ""
    real: str = ""
    estado: str = "APROBADA"
    metrica: str = ""
    fecha: date = FECHA
    observaciones: str = ""
    ubicacion: str = ""
    critica: str = "No"
    critica_razon: str = ""
    top100: bool = False
    score: int = 0
    evidencia: str = ""
    ac: list[str] = field(default_factory=list)
    archivo: str = ""
    linea: int = 0
    variante: str = ""


def construir_backend() -> list[Caso]:
    meta = parsear_ast_backend()
    gated = archivos_gated_pg()
    redis_file = "tests/no_funcional/rendimiento/test_limite_tasa_redis_025.py"
    casos: list[Caso] = []
    faltantes = 0

    for nodeid in leer_coleccion():
        archivo, resto = nodeid.split("::", 1)
        base, _, param = resto.partition("[")
        param = param.rstrip("]") if param else ""
        info = meta.get(archivo, {})
        funcion = info.get("funciones", {}).get(base)
        if not funcion:
            faltantes += 1
            funcion = {"linea": 0, "doc": "", "asserts": [], "args": []}
        doc_modulo = info.get("doc_modulo", "")
        doc_test = primer_parrafo(funcion["doc"])
        asserts = funcion["asserts"]
        nombre = humanizar(base[5:] if base.startswith("test_") else base)
        if param:
            nombre += f" [{param}]"
        feature = feature_backend(archivo, doc_modulo)
        tipo = "BD" if archivo in gated else "Backend"
        tipo_prueba = tipo_prueba_backend(archivo)
        modulo = modulo_backend(archivo)
        ac = extraer_ac(f"{base} {funcion['doc']} {doc_modulo}")
        features_extra = [f for f in extraer_features(funcion["doc"]) if f != feature]

        resumen = resumen_asserts(asserts)
        if doc_test:
            esperado = doc_test
        elif resumen and (
            (resumen.startswith("HTTP ") and len(resumen) <= 25)
            or resumen
            in {
                "no se registran errores",
                "colección vacía",
                "valor nulo",
                "todas las condiciones se cumplen",
                "alguna condición se cumple",
            }
        ):
            esperado = resumen
        elif asserts:
            esperado = nombre
        else:
            esperado = f"El caso cumple el contrato de {modulo}."
        entonces = esperado if esperado.endswith((".", "!", "?")) else esperado + "."
        cuando = f"Cuando se ejecuta el caso «{nombre}» sobre {modulo}."
        dado = contexto_backend(archivo, tipo, tipo_prueba, modulo)

        if tipo == "BD":
            evidencia = "PostgreSQL 16"
            real = f"Conforme (PostgreSQL 16: {BACKEND_BD_OK}/{BACKEND_BD_OK})."
            metrica = f"{plural(len(asserts) or 1, 'aserción', 'aserciones')} · BD {BACKEND_BD_OK}/{BACKEND_BD_OK}"
        elif archivo == redis_file:
            evidencia = "Redis 025"
            real = f"Conforme (Redis 025: {BACKEND_REDIS_OK}/{BACKEND_REDIS_OK})."
            metrica = f"{plural(len(asserts) or 1, 'aserción', 'aserciones')} · Redis {BACKEND_REDIS_OK}/{BACKEND_REDIS_OK}"
        else:
            evidencia = "SQLite 027"
            real = f"Conforme (SQLite 027: {BACKEND_SQLITE_OK}/{BACKEND_SQLITE_OK})."
            metrica = f"{plural(len(asserts) or 1, 'aserción', 'aserciones')} · SQLite {BACKEND_SQLITE_OK}/{BACKEND_SQLITE_OK}"

        critica, razon = evaluar_critica(tipo, tipo_prueba, archivo, nombre, doc_test, modulo)
        obs = []
        if not doc_test:
            obs.append("Gherkin derivado del nombre y las aserciones")
        if ac:
            obs.append(", ".join(ac))
        if features_extra:
            obs.append("Cubre: " + ", ".join(f"{n:03d}" for n in features_extra))
        if param:
            obs.append(f"Parametrizado: {param}")
        if tipo == "BD":
            obs.append("Gated PostgreSQL 16")
        elif archivo == redis_file:
            obs.append("Gated Redis 025")
        if critica == "Sí":
            obs.append(f"Crítica: {razon}")
        if not obs:
            obs.append("Sin observaciones adicionales")

        ubicacion = f"backend/{archivo}:{funcion['linea']}::{base}"
        if param:
            ubicacion += f"[{param}]"

        casos.append(
            Caso(
                nombre=nombre,
                feature_num=feature,
                feature=f"{feature:03d} · {FEATURES.get(feature, 'Transversal')}",
                modulo=modulo,
                tipo=tipo,
                tipo_prueba=tipo_prueba,
                dado=dado,
                cuando=cuando,
                entonces=entonces,
                esperado=recortar(esperado),
                real=real,
                metrica=metrica,
                observaciones=" · ".join(dict.fromkeys(obs)),
                ubicacion=ubicacion,
                critica=critica,
                critica_razon=razon,
                evidencia=evidencia,
                ac=ac,
                archivo=archivo,
                linea=funcion["linea"],
                variante=param,
            )
        )

    if faltantes:
        print(f"ADVERTENCIA: {faltantes} nodeids sin función AST (se usó fallback).")
    return casos


def construir_frontend() -> list[Caso]:
    casos: list[Caso] = []
    for item in cargar_frontend():
        archivo = item["archivo"]
        titulo = item["titulo"]
        suite = " › ".join(item["suite"])
        feature = feature_frontend(archivo)
        tipo_prueba = tipo_prueba_frontend(archivo)
        modulo = modulo_frontend(archivo)
        ac = item.get("ac", [])
        features_extra = extraer_features(f"{titulo} {suite} {item.get('comentario', '')}")
        features_extra = [f for f in features_extra if f != feature]
        expect = item.get("expect", 0)
        expect_none = item.get("expectNone", 0)

        dado = contexto_frontend(archivo, tipo_prueba, modulo)
        cuando = f"Cuando se ejecuta el caso «{titulo}» en {modulo}."
        titulo_cita = titulo.replace("«", "“").replace("»", "”")
        if tipo_prueba == "Sistema":
            entonces = (
                f"El resultado de la interfaz coincide con el AC esperado: «{titulo_cita}», "
                "y no muestra errores de consola."
            )
        elif tipo_prueba == "Integración":
            entonces = f"El resultado de la integración coincide con el AC esperado: «{titulo_cita}»."
        else:
            entonces = f"El resultado de la utilidad coincide con el AC esperado: «{titulo_cita}»."
        esperado = recortar(titulo + ("; sin errores de consola" if tipo_prueba == "Sistema" else ""))
        real = f"Conforme (Karma 027: {TOTAL_FRONTEND}/{TOTAL_FRONTEND} SUCCESS)."
        metrica = plural(expect or 1, "expectativa", "expectativas")
        if expect_none:
            metrica += f" + {expect_none} expectNone"
        metrica += f" · Karma {TOTAL_FRONTEND}/{TOTAL_FRONTEND}"

        critica, razon = evaluar_critica("Frontend", tipo_prueba, archivo, titulo, suite, modulo)
        obs = []
        if ac:
            obs.append(", ".join(ac))
        if features_extra:
            obs.append("Cubre: " + ", ".join(f"{n:03d}" for n in features_extra))
        if item.get("variante"):
            obs.append(f"Caso dinámico: {item['variante']}")
        if critica == "Sí":
            obs.append(f"Crítica: {razon}")
        if not obs:
            obs.append("Sin observaciones adicionales")

        ubicacion = f"{archivo}:{item['linea']}"
        if suite:
            ubicacion += f" › {suite} › {titulo}"

        casos.append(
            Caso(
                nombre=item.get("nombreCompleto") or titulo,
                feature_num=feature,
                feature=f"{feature:03d} · {FEATURES.get(feature, 'Transversal')}",
                modulo=modulo,
                tipo="Frontend",
                tipo_prueba=tipo_prueba,
                dado=dado,
                cuando=cuando,
                entonces=entonces,
                esperado=esperado,
                real=real,
                metrica=metrica,
                observaciones=" · ".join(dict.fromkeys(obs)),
                ubicacion=ubicacion,
                critica=critica,
                critica_razon=razon,
                evidencia="Karma 027",
                ac=ac,
                archivo=archivo,
                linea=item["linea"],
                variante=item.get("variante", ""),
            )
        )
    return casos


# ---------------------------------------------------------------------------
# IDs y Top 100
# ---------------------------------------------------------------------------


def asignar_ids(casos: list[Caso]) -> None:
    orden_tipo = {"Backend": 0, "BD": 1, "Frontend": 2}
    prefijos = {"Backend": "BE", "BD": "BD", "Frontend": "FE"}
    casos.sort(key=lambda c: (orden_tipo[c.tipo], c.feature_num, c.archivo, c.linea, c.nombre))
    contadores = defaultdict(int)
    for caso in casos:
        contadores[caso.tipo] += 1
        caso.id = f"{prefijos[caso.tipo]}-{contadores[caso.tipo]:04d}"


def calcular_score(caso: Caso) -> int:
    score = 0
    if caso.critica == "Sí":
        score += 100
    if caso.tipo_prueba == "E2E":
        score += 35
    if caso.tipo_prueba == "Seguridad":
        score += 35
    if caso.tipo == "BD":
        score += 40
    if caso.tipo_prueba == "Sistema":
        score += 20
    if caso.ac:
        score += 15
    texto = f"{caso.archivo} {caso.nombre} {caso.modulo}".lower()
    palabras = [
        "despacho",
        "transacc",
        "aislamiento",
        "tenant",
        "limite_tasa",
        "validacion",
        "esquema",
        "salud",
        "instalacion",
        "invitacion",
        "gobierno",
        "cobertura",
        "recepcion",
    ]
    score += min(24, 8 * sum(1 for p in palabras if p in texto))
    if caso.feature_num in {5, 13, 20, 21, 26, 27}:
        score += 10
    return score


def seleccionar_top100(casos: list[Caso]) -> list[Caso]:
    for caso in casos:
        caso.score = calcular_score(caso)
    seleccionados: list[Caso] = []
    ids = set()
    por_tipo = Counter()
    por_feature = Counter()

    def agregar(caso: Caso, cap_feature: int = 999) -> bool:
        if caso.id in ids or len(seleccionados) >= 100:
            return False
        if por_feature[caso.feature_num] >= cap_feature:
            return False
        ids.add(caso.id)
        caso.top100 = True
        seleccionados.append(caso)
        por_tipo[caso.tipo] += 1
        por_feature[caso.feature_num] += 1
        return True

    # 1) Al menos un caso por feature, eligiendo el de mayor score.
    agrupados: dict[int, list[Caso]] = defaultdict(list)
    for caso in casos:
        agrupados[caso.feature_num].append(caso)
    for feature in sorted(agrupados):
        candidato = max(agrupados[feature], key=lambda c: c.score)
        agregar(candidato)

    # 2) Completar con cuotas por tipo y un tope por feature para evitar que
    #    dos flujos dominen toda la selección.
    cuotas = {"Backend": 40, "Frontend": 35, "BD": 25}
    ordenados = sorted(casos, key=lambda c: (-c.score, c.tipo, c.feature_num, c.nombre))
    for cap_feature in (8, 12, 999):
        for caso in ordenados:
            if len(seleccionados) >= 100:
                break
            if por_tipo[caso.tipo] >= cuotas[caso.tipo]:
                continue
            agregar(caso, cap_feature)

    # 3) Si aún faltan, completar sin cuota de tipo.
    for cap_feature in (8, 12, 999):
        for caso in ordenados:
            if len(seleccionados) >= 100:
                break
            agregar(caso, cap_feature)

    seleccionados.sort(key=lambda c: (c.tipo, c.feature_num, c.nombre))
    return seleccionados


# ---------------------------------------------------------------------------
# Excel
# ---------------------------------------------------------------------------

INK = "1E293B"
ACCENT = "2563EB"
MUTED = "475569"
LIGHT = "F8FAFC"
BORDER = "CBD5E1"
GREEN_FILL = "DCFCE7"
GREEN_TEXT = "166534"
RED_FILL = "FEE2E2"
RED_TEXT = "991B1B"
AMBER_FILL = "FEF3C7"
AMBER_TEXT = "92400E"
BLUE_FILL = "EFF6FF"
WHITE = "FFFFFF"

HEADERS = [
    "ID de la prueba",
    "Nombre de la prueba",
    "Feature",
    "Caso/Módulo",
    "Tipo",
    "Tipo de prueba",
    "Dado",
    "Cuando",
    "Entonces",
    "Resultado esperado",
    "Resultado real",
    "Estado",
    "Métrica de verificación",
    "Fecha de ejecución",
    "Observaciones",
    "Identificador de ubicación",
    "¿Prueba crítica?",
]

ANCHOS = [12, 42, 30, 30, 11, 14, 46, 44, 44, 40, 34, 12, 30, 14, 42, 56, 11]

FONT_BASE = Font(name="Calibri", size=10, color=INK)
FONT_BOLD = Font(name="Calibri", size=10, bold=True, color=INK)
FONT_HEADER = Font(name="Calibri", size=10, bold=True, color=WHITE)
FONT_TITLE = Font(name="Calibri", size=18, bold=True, color=INK)
FONT_SUBTITLE = Font(name="Calibri", size=11, color=MUTED)
FONT_SECTION = Font(name="Calibri", size=12, bold=True, color=ACCENT)
FONT_MONO = Font(name="Consolas", size=9, color=INK)

FILL_HEADER = PatternFill("solid", fgColor=INK)
FILL_LIGHT = PatternFill("solid", fgColor=LIGHT)
FILL_BLUE = PatternFill("solid", fgColor=BLUE_FILL)
FILL_GREEN = PatternFill("solid", fgColor=GREEN_FILL)
FILL_RED = PatternFill("solid", fgColor=RED_FILL)
FILL_AMBER = PatternFill("solid", fgColor=AMBER_FILL)
FILL_WHITE = PatternFill("solid", fgColor=WHITE)
FILL_TOP100 = PatternFill("solid", fgColor="E0F2FE")

THIN = Side(style="thin", color=BORDER)
BORDE = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
BORDE_INFERIOR = Border(bottom=Side(style="thin", color=BORDER))

ALINEADO = Alignment(vertical="top", wrap_text=True)
ALINEADO_CENTRO = Alignment(horizontal="center", vertical="center", wrap_text=True)


def ajustar_anchos(ws, anchos=ANCHOS) -> None:
    for indice, ancho in enumerate(anchos, start=1):
        ws.column_dimensions[get_column_letter(indice)].width = ancho


def escribir_encabezado(ws, fila: int) -> None:
    for columna, titulo in enumerate(HEADERS, start=1):
        celda = ws.cell(row=fila, column=columna, value=titulo)
        celda.font = FONT_HEADER
        celda.fill = FILL_HEADER
        celda.alignment = ALINEADO_CENTRO
        celda.border = BORDE
    ws.row_dimensions[fila].height = 34


def escribir_titulo(ws, titulo: str, subtitulo: str, columnas: int = 17) -> int:
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=columnas)
    celda = ws.cell(row=1, column=1, value=titulo)
    celda.font = FONT_TITLE
    celda.alignment = Alignment(vertical="center")
    ws.row_dimensions[1].height = 28

    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=columnas)
    celda = ws.cell(row=2, column=1, value=subtitulo)
    celda.font = FONT_SUBTITLE
    celda.alignment = Alignment(vertical="center")
    ws.row_dimensions[2].height = 20
    return 4


def escribir_filas(ws, casos: list[Caso], fila_inicial: int, resaltar_top: bool = False) -> int:
    fila = fila_inicial
    for indice, caso in enumerate(casos):
        valores = [
            caso.id,
            caso.nombre,
            caso.feature,
            caso.modulo,
            caso.tipo,
            caso.tipo_prueba,
            caso.dado,
            caso.cuando,
            caso.entonces,
            caso.esperado,
            caso.real,
            caso.estado,
            caso.metrica,
            caso.fecha,
            caso.observaciones,
            caso.ubicacion,
            caso.critica,
        ]
        for columna, valor in enumerate(valores, start=1):
            celda = ws.cell(row=fila, column=columna, value=valor)
            celda.font = FONT_BASE
            celda.alignment = ALINEADO
            celda.border = BORDE_INFERIOR
            if resaltar_top and caso.top100:
                celda.fill = FILL_TOP100
            elif indice % 2 == 1:
                celda.fill = FILL_LIGHT
        ws.cell(row=fila, column=14).number_format = "yyyy-mm-dd"
        ws.cell(row=fila, column=14).alignment = Alignment(horizontal="center", vertical="top")
        ws.cell(row=fila, column=5).alignment = ALINEADO_CENTRO
        ws.cell(row=fila, column=6).alignment = ALINEADO_CENTRO
        ws.cell(row=fila, column=12).alignment = ALINEADO_CENTRO
        ws.cell(row=fila, column=17).alignment = ALINEADO_CENTRO
        ws.row_dimensions[fila].height = 60
        fila += 1
    return fila - 1


def aplicar_formato_tabla(ws, desde: int, hasta: int) -> None:
    ws.auto_filter.ref = f"A{desde}:Q{hasta}"
    ws.freeze_panes = f"C{desde + 1}"
    ws.sheet_view.showGridLines = False
    ws.print_title_rows = f"{desde}:{desde}"
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True

    ws.conditional_formatting.add(
        f"L{desde + 1}:L{hasta}",
        CellIsRule(operator="equal", formula=['"APROBADA"'], fill=FILL_GREEN, font=Font(color=GREEN_TEXT, bold=True)),
    )
    ws.conditional_formatting.add(
        f"L{desde + 1}:L{hasta}",
        CellIsRule(operator="equal", formula=['"FALLIDA"'], fill=FILL_RED, font=Font(color=RED_TEXT, bold=True)),
    )
    ws.conditional_formatting.add(
        f"L{desde + 1}:L{hasta}",
        CellIsRule(operator="equal", formula=['"OMITIDA"'], fill=FILL_AMBER, font=Font(color=AMBER_TEXT, bold=True)),
    )
    ws.conditional_formatting.add(
        f"Q{desde + 1}:Q{hasta}",
        CellIsRule(operator="equal", formula=['"Sí"'], fill=FILL_RED, font=Font(color=RED_TEXT, bold=True)),
    )

    dv_estado = DataValidation(type="list", formula1='"APROBADA,FALLIDA,OMITIDA"', allow_blank=False)
    ws.add_data_validation(dv_estado)
    dv_estado.add(f"L{desde + 1}:L{hasta}")
    dv_critica = DataValidation(type="list", formula1='"Sí,No"', allow_blank=False)
    ws.add_data_validation(dv_critica)
    dv_critica.add(f"Q{desde + 1}:Q{hasta}")


def hoja_resumen(wb: Workbook, casos: list[Caso]) -> None:
    ws = wb.active
    ws.title = "Resumen"
    ws.sheet_properties.tabColor = ACCENT
    ws.sheet_view.showGridLines = False
    ws.column_dimensions["A"].width = 30
    ws.column_dimensions["B"].width = 16
    ws.column_dimensions["C"].width = 22
    ws.column_dimensions["D"].width = 16
    ws.column_dimensions["E"].width = 16
    ws.column_dimensions["F"].width = 46

    ws.merge_cells("A1:F1")
    celda = ws["A1"]
    celda.value = "Planilla de pruebas — Compustock ERP"
    celda.font = FONT_TITLE
    celda.alignment = Alignment(vertical="center")
    ws.row_dimensions[1].height = 30

    ws.merge_cells("A2:F2")
    celda = ws["A2"]
    celda.value = (
        f"Evidencia consolidada del cierre 027 · {FECHA_TEXTO} · "
        f"{miles(len(casos))} casos · Frontend, Backend y BD"
    )
    celda.font = FONT_SUBTITLE
    ws.row_dimensions[2].height = 20

    total = len(casos)
    aprobadas = sum(1 for c in casos if c.estado == "APROBADA")
    fallidas = sum(1 for c in casos if c.estado == "FALLIDA")
    omitidas = sum(1 for c in casos if c.estado == "OMITIDA")
    criticas = sum(1 for c in casos if c.critica == "Sí")
    top = sum(1 for c in casos if c.top100)

    fila = 4
    ws.cell(row=fila, column=1, value="Indicadores").font = FONT_SECTION
    fila += 1
    encabezados = ["Indicador", "Valor", "Detalle"]
    for columna, titulo in enumerate(encabezados, start=1):
        celda = ws.cell(row=fila, column=columna, value=titulo)
        celda.font = FONT_HEADER
        celda.fill = FILL_HEADER
        celda.alignment = ALINEADO_CENTRO
        celda.border = BORDE
    ws.merge_cells(start_row=fila, start_column=3, end_row=fila, end_column=6)
    fila += 1

    indicadores = [
        ("Total de casos", total, "Backend + BD + Frontend"),
        ("Aprobadas", aprobadas, f"{aprobadas/total:.1%} del total"),
        ("Fallidas", fallidas, "Sin fallos en la evidencia 027"),
        ("Omitidas", omitidas, "Los skipped de una corrida se cubrieron en la otra"),
        ("Pruebas críticas", criticas, f"{criticas/total:.1%} del total"),
        ("Top 100", top, "Selección balanceada por tipo y feature"),
    ]
    for etiqueta, valor, detalle in indicadores:
        ws.cell(row=fila, column=1, value=etiqueta).font = FONT_BOLD
        ws.cell(row=fila, column=1).border = BORDE
        celda = ws.cell(row=fila, column=2, value=valor)
        celda.font = FONT_BOLD
        celda.alignment = ALINEADO_CENTRO
        celda.border = BORDE
        celda.fill = FILL_BLUE
        if isinstance(valor, int):
            celda.number_format = "#,##0"
        ws.merge_cells(start_row=fila, start_column=3, end_row=fila, end_column=6)
        celda = ws.cell(row=fila, column=3, value=detalle)
        celda.font = FONT_BASE
        celda.alignment = ALINEADO
        celda.border = BORDE
        fila += 1

    # Por tipo
    fila += 1
    ws.cell(row=fila, column=1, value="Cobertura por tipo").font = FONT_SECTION
    fila += 1
    for columna, titulo in enumerate(["Tipo", "Casos", "Aprobadas", "Críticas", "Cobertura"], start=1):
        celda = ws.cell(row=fila, column=columna, value=titulo)
        celda.font = FONT_HEADER
        celda.fill = FILL_HEADER
        celda.alignment = ALINEADO_CENTRO
        celda.border = BORDE
    ws.merge_cells(start_row=fila, start_column=5, end_row=fila, end_column=6)
    fila += 1
    for tipo in ["Backend", "BD", "Frontend"]:
        sub = [c for c in casos if c.tipo == tipo]
        valores = [
            tipo,
            len(sub),
            sum(1 for c in sub if c.estado == "APROBADA"),
            sum(1 for c in sub if c.critica == "Sí"),
            f"{len(sub)/total:.1%}",
        ]
        for columna, valor in enumerate(valores, start=1):
            celda = ws.cell(row=fila, column=columna, value=valor)
            celda.font = FONT_BASE
            celda.border = BORDE
            celda.alignment = ALINEADO_CENTRO if columna > 1 else ALINEADO
            if isinstance(valor, int):
                celda.number_format = "#,##0"
        fila += 1

    # Por tipo de prueba
    fila += 1
    ws.cell(row=fila, column=1, value="Cobertura por tipo de prueba").font = FONT_SECTION
    fila += 1
    for columna, titulo in enumerate(["Tipo de prueba", "Casos", "Aprobadas", "Críticas"], start=1):
        celda = ws.cell(row=fila, column=columna, value=titulo)
        celda.font = FONT_HEADER
        celda.fill = FILL_HEADER
        celda.alignment = ALINEADO_CENTRO
        celda.border = BORDE
    fila += 1
    for tipo in ["Unitario", "Integración", "Sistema", "E2E", "Humo", "Rendimiento", "Seguridad", "Aceptación"]:
        sub = [c for c in casos if c.tipo_prueba == tipo]
        if not sub:
            continue
        valores = [
            tipo,
            len(sub),
            sum(1 for c in sub if c.estado == "APROBADA"),
            sum(1 for c in sub if c.critica == "Sí"),
        ]
        for columna, valor in enumerate(valores, start=1):
            celda = ws.cell(row=fila, column=columna, value=valor)
            celda.font = FONT_BASE
            celda.border = BORDE
            celda.alignment = ALINEADO_CENTRO if columna > 1 else ALINEADO
            if isinstance(valor, int):
                celda.number_format = "#,##0"
        fila += 1

    # Por feature
    fila += 1
    ws.cell(row=fila, column=1, value="Cobertura por feature").font = FONT_SECTION
    fila += 1
    for columna, titulo in enumerate(
        ["Feature", "Backend", "BD", "Frontend", "Total", "Críticas"], start=1
    ):
        celda = ws.cell(row=fila, column=columna, value=titulo)
        celda.font = FONT_HEADER
        celda.fill = FILL_HEADER
        celda.alignment = ALINEADO_CENTRO
        celda.border = BORDE
    fila += 1
    por_feature: dict[int, list[Caso]] = defaultdict(list)
    for caso in casos:
        por_feature[caso.feature_num].append(caso)
    for feature in sorted(por_feature):
        sub = por_feature[feature]
        valores = [
            f"{feature:03d} · {FEATURES.get(feature, 'Transversal')}",
            sum(1 for c in sub if c.tipo == "Backend"),
            sum(1 for c in sub if c.tipo == "BD"),
            sum(1 for c in sub if c.tipo == "Frontend"),
            len(sub),
            sum(1 for c in sub if c.critica == "Sí"),
        ]
        for columna, valor in enumerate(valores, start=1):
            celda = ws.cell(row=fila, column=columna, value=valor)
            celda.font = FONT_BASE
            celda.border = BORDE
            celda.alignment = ALINEADO if columna == 1 else ALINEADO_CENTRO
            if isinstance(valor, int):
                celda.number_format = "#,##0"
        fila += 1

    # Conciliación
    fila += 1
    ws.cell(row=fila, column=1, value="Conciliación de conteos (cierre 027)").font = FONT_SECTION
    fila += 1
    conciliacion = [
        ("pytest SQLite", "1.863 passed / 109 skipped", "Los 109 skipped son 106 BD + 3 Redis."),
        ("pytest PostgreSQL 16", "1.969 passed / 3 skipped", "Los 3 skipped son los tests de Redis."),
        ("pytest Redis 025", "3 passed", "Los 3 tests de límite de tasa distribuido."),
        ("ng test (Karma)", "597 SUCCESS", "576 casos estáticos + 21 generados por bucles."),
        ("Consolidado", "2.569 APROBADA", "0 fallidas / 0 omitidas en la consolidación."),
    ]
    for suite, valor, detalle in conciliacion:
        ws.cell(row=fila, column=1, value=suite).font = FONT_BOLD
        ws.cell(row=fila, column=1).border = BORDE
        celda = ws.cell(row=fila, column=2, value=valor)
        celda.font = FONT_BASE
        celda.border = BORDE
        ws.merge_cells(start_row=fila, start_column=2, end_row=fila, end_column=3)
        ws.merge_cells(start_row=fila, start_column=4, end_row=fila, end_column=6)
        celda = ws.cell(row=fila, column=4, value=detalle)
        celda.font = FONT_BASE
        celda.alignment = ALINEADO
        celda.border = BORDE
        fila += 1

    # Entorno
    fila += 1
    ws.cell(row=fila, column=1, value="Entorno de la evidencia").font = FONT_SECTION
    fila += 1
    entorno = [
        ("Repositorio", "Commit 8b41014 · feat(027) · árbol limpio"),
        ("Fecha de cierre", FECHA_TEXTO),
        ("Backend", "Python 3.11.3 · pytest 9.1.1 · FastAPI · SQLAlchemy 2.0"),
        ("Frontend", "Angular 18.2 · Karma/Jasmine · Edge headless"),
        ("Base de datos", "PostgreSQL 16 · Redis 7.2 · Docker Compose"),
        ("Fuente", "docs/spec/features/027-validacion-entradas/evidencia/README.md"),
    ]
    for etiqueta, valor in entorno:
        ws.cell(row=fila, column=1, value=etiqueta).font = FONT_BOLD
        ws.cell(row=fila, column=1).border = BORDE
        ws.merge_cells(start_row=fila, start_column=2, end_row=fila, end_column=6)
        celda = ws.cell(row=fila, column=2, value=valor)
        celda.font = FONT_BASE
        celda.alignment = ALINEADO
        celda.border = BORDE
        fila += 1

    # Notas
    fila += 1
    ws.cell(row=fila, column=1, value="Notas").font = FONT_SECTION
    fila += 1
    notas = [
        "No se re-ejecutó la suite para esta planilla: el estado es el consolidado del cierre 027.",
        "El Gherkin se deriva de docstrings, nombres de test, títulos de spec y aserciones; no se inventan pasos.",
        "Los recorridos manuales 4200/8080 se documentan en las evidencias de cada feature y no se listan aquí.",
        "La columna «¿Prueba crítica?» es una lista Sí/No filtrable; openpyxl no crea checkboxes nativos.",
    ]
    for nota in notas:
        ws.merge_cells(start_row=fila, start_column=1, end_row=fila, end_column=6)
        celda = ws.cell(row=fila, column=1, value="• " + nota)
        celda.font = FONT_BASE
        celda.alignment = ALINEADO
        ws.row_dimensions[fila].height = 26
        fila += 1

    ws.page_setup.orientation = "portrait"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True


def hoja_casos(wb: Workbook, casos: list[Caso], titulo: str, subtitulo: str) -> None:
    ws = wb.create_sheet(titulo)
    ws.sheet_properties.tabColor = ACCENT if titulo == "Top 100" else MUTED
    ws.sheet_view.showGridLines = False
    ajustar_anchos(ws)
    desde = escribir_titulo(ws, titulo, subtitulo)
    escribir_encabezado(ws, desde)
    hasta = escribir_filas(ws, casos, desde + 1, resaltar_top=(titulo == "Matriz completa"))
    aplicar_formato_tabla(ws, desde, hasta)


def hoja_leyenda(wb: Workbook) -> None:
    ws = wb.create_sheet("Leyenda")
    ws.sheet_properties.tabColor = MUTED
    ws.sheet_view.showGridLines = False
    ws.column_dimensions["A"].width = 26
    ws.column_dimensions["B"].width = 110

    ws.merge_cells("A1:B1")
    celda = ws["A1"]
    celda.value = "Leyenda y criterios de la planilla"
    celda.font = FONT_TITLE
    ws.row_dimensions[1].height = 30

    fila = 3
    secciones = [
        (
            "1. Alcance",
            "Se listan los 2.569 casos automatizados del cierre 027: 1.972 casos de la "
            "suite backend (1.866 Backend + 106 BD) y 597 de frontend (Karma/Jasmine). No "
            "se incluyen los recorridos manuales 4200/8080, que viven en la evidencia de "
            "cada feature. El estado es el consolidado documentado, no una nueva ejecución.",
        ),
        (
            "2. Tipo",
            "Frontend: specs de Angular/Karma. Backend: tests pytest que corren sobre "
            "SQLite o validan la API. BD: tests gated que exigen PostgreSQL 16 real "
            "(esquema, instalación limpia, constraints y salud). Los 3 tests de Redis se "
            "clasifican como Backend/Rendimiento; las validaciones de la semilla RUT que "
            "no exigen PostgreSQL quedan como Backend/Sistema.",
        ),
        (
            "3. Tipo de prueba",
            "Se toma de la carpeta de la suite: unitarios, integración, sistema, E2E, "
            "humo, rendimiento y seguridad. En frontend: unitario para utilidades, "
            "integración para servicios/guards/rutas y sistema para componentes.",
        ),
        (
            "4. Feature",
            "Backend: sufijo _NNN del archivo y, si falta, palabras clave del módulo. "
            "Frontend: carpeta de la feature. Las features secundarias detectadas en "
            "docstrings o títulos se anotan en Observaciones. Las features 015 y 016 "
            "están pendientes y no tienen casos; la 022 fue mantenimiento sin tests "
            "nuevos y se cubre con la suite existente.",
        ),
        (
            "5. Gherkin",
            "Dado describe el contexto del módulo (API, BD, UI, guard o utilidad). Cuando "
            "ejecuta el caso concreto. Entonces usa el docstring del test o el título del "
            "spec, que ya expresan el resultado esperado. En UI se añade el criterio de "
            "aceptación «sin errores de consola»; no se inventan pasos no documentados.",
        ),
        (
            "6. Criticidad",
            "Sí cuando el caso cubre seguridad, autenticación, autorización, aislamiento "
            "multi-tenant, transacciones/retiro, esquema o salud de BD, límite de tasa, "
            "validación de contrato, gobierno de identidades o flujos E2E. No en cambios "
            "de presentación o utilidades sin impacto de seguridad/integridad.",
        ),
        (
            "7. Top 100",
            "Se elige al menos un caso por feature y se completa con cuotas de 40 backend, "
            "35 frontend y 25 BD, priorizando criticidad, E2E, seguridad, cobertura de AC "
            "y palabras clave de riesgo. La hoja conserva la misma ID de la matriz completa "
            "y sus 100 filas se resaltan en azul claro dentro de la matriz.",
        ),
        (
            "8. Conciliación",
            "SQLite: 1.863 passed + 109 skipped. PostgreSQL: 1.969 passed + 3 skipped. "
            "Redis: 3 passed. Los 109 skipped de SQLite son 106 pruebas de BD y 3 de Redis; "
            "al consolidar las corridas quedan 1.972/1.972 backend. Karma: 597/597 SUCCESS "
            "(576 estáticos + 21 generados por 9 bucles).",
        ),
        (
            "9. Fecha y resultado",
            "Fecha de ejecución = 24/Nov/2026 (cierre 027). Resultado real = «Conforme» "
            "con la suite que acredita el caso. No se re-ejecutó pytest ni Karma para esta "
            "planilla; si se requiere una corrida fresca, se regenera con JUnit XML y el "
            "reporter JSON de Karma.",
        ),
        (
            "10. Casilla crítica",
            "La columna «¿Prueba crítica?» usa Sí/No con validación de datos y resaltado. "
            "Es filtrable y ordenable; no es un control de formulario nativo de Excel.",
        ),
        (
            "11. Reproducibilidad",
            "El generador es docs/informes/_generar_planilla_pruebas.py. La enumeración "
            "de backend se guarda en docs/informes/_datos/backend-coleccion-027.txt "
            "(`pytest --collect-only -q`) y la de frontend en "
            "docs/informes/_datos/frontend-specs.json "
            "(`node docs/informes/_datos/extraer_specs.js`).",
        ),
    ]
    for titulo, texto in secciones:
        ws.cell(row=fila, column=1, value=titulo).font = FONT_SECTION
        ws.merge_cells(start_row=fila, start_column=1, end_row=fila, end_column=2)
        fila += 1
        ws.merge_cells(start_row=fila, start_column=1, end_row=fila, end_column=2)
        celda = ws.cell(row=fila, column=1, value=texto)
        celda.font = FONT_BASE
        celda.alignment = ALINEADO
        ws.row_dimensions[fila].height = 60
        fila += 2

    ws.cell(row=fila, column=1, value="12. Columnas").font = FONT_SECTION
    fila += 1
    descripciones = [
        ("ID de la prueba", "Identificador único: BE (backend), BD (base de datos), FE (frontend)."),
        ("Nombre de la prueba", "Nombre legible del caso; conserva el parámetro si es parametrizado."),
        ("Feature", "Número y nombre corto de la feature que originó el caso."),
        ("Caso/Módulo", "Dominio y módulo funcional bajo prueba."),
        ("Tipo", "Frontend, Backend o BD."),
        ("Tipo de prueba", "Unitario, Integración, Sistema, E2E, Humo, Rendimiento, Seguridad o Aceptación."),
        ("Dado", "Precondición o contexto del caso."),
        ("Cuando", "Acción o caso ejecutado."),
        ("Entonces", "Resultado esperado en formato Gherkin."),
        ("Resultado esperado", "Resultado concreto documentado por el test o su aserción principal."),
        ("Resultado real", "Conformidad consolidada e indicación de la suite que la acredita."),
        ("Estado", "APROBADA, FALLIDA u OMITIDA según la evidencia consolidada."),
        ("Métrica de verificación", "Número de aserciones/expectativas y ratio de la suite."),
        ("Fecha de ejecución", "24/Nov/2026, fecha del cierre 027."),
        ("Observaciones", "AC, features secundarias, parametrización, gating y motivo de criticidad."),
        ("Identificador de ubicación", "Ruta, línea y nodeid de pytest o cadena describe › it de Karma."),
        ("¿Prueba crítica?", "Sí/No según la heurística de la sección 6."),
    ]
    for columna, titulo in enumerate(["Columna", "Descripción"], start=1):
        celda = ws.cell(row=fila, column=columna, value=titulo)
        celda.font = FONT_HEADER
        celda.fill = FILL_HEADER
        celda.alignment = ALINEADO_CENTRO
        celda.border = BORDE
    fila += 1
    for nombre, descripcion in descripciones:
        ws.cell(row=fila, column=1, value=nombre).font = FONT_BOLD
        ws.cell(row=fila, column=1).border = BORDE
        celda = ws.cell(row=fila, column=2, value=descripcion)
        celda.font = FONT_BASE
        celda.alignment = ALINEADO
        celda.border = BORDE
        ws.row_dimensions[fila].height = 24
        fila += 1

    ws.page_setup.orientation = "portrait"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True


def generar_excel(casos: list[Caso], top100: list[Caso]) -> None:
    wb = Workbook()
    hoja_resumen(wb, casos)

    subtitulo_top = (
        f"{len(top100)} casos priorizados · evidencia cierre 027 · "
        "40 backend / 35 frontend / 25 BD"
    )
    hoja_casos(wb, top100, "Top 100", subtitulo_top)

    subtitulo_matriz = (
        f"{miles(len(casos))} casos · {FECHA_TEXTO} · "
        "Backend + BD + Frontend · una fila por caso"
    )
    hoja_casos(wb, casos, "Matriz completa", subtitulo_matriz)

    hoja_leyenda(wb)
    wb.save(SALIDA)


# ---------------------------------------------------------------------------
# Validación
# ---------------------------------------------------------------------------


def validar() -> None:
    wb = load_workbook(SALIDA, read_only=True)
    hojas = wb.sheetnames
    assert hojas == ["Resumen", "Top 100", "Matriz completa", "Leyenda"], hojas

    ws = wb["Matriz completa"]
    filas = list(ws.iter_rows(min_row=5, values_only=True))
    filas = [f for f in filas if f[0]]
    assert len(filas) == TOTAL_BACKEND + TOTAL_FRONTEND, len(filas)
    assert len({f[0] for f in filas}) == len(filas), "IDs duplicados"
    assert all(f[11] == "APROBADA" for f in filas), "Hay estados no aprobados"
    assert all(f[16] in ("Sí", "No") for f in filas), "Crítica inválida"
    for f in filas:
        assert all(v not in (None, "") for v in f[:17]), f"Fila incompleta: {f[0]}"

    ws_top = wb["Top 100"]
    filas_top = [f for f in ws_top.iter_rows(min_row=5, values_only=True) if f[0]]
    assert len(filas_top) == 100, len(filas_top)

    tipos = Counter(f[4] for f in filas)
    tipos_prueba = Counter(f[5] for f in filas)
    criticas = sum(1 for f in filas if f[16] == "Sí")
    print("Validación OK")
    print(f"  Total: {len(filas)}")
    print(f"  Tipos: {dict(tipos)}")
    print(f"  Tipos de prueba: {dict(tipos_prueba)}")
    print(f"  Críticas: {criticas} ({criticas/len(filas):.1%})")
    print(f"  Top 100: {len(filas_top)}")
    print(f"  Archivo: {SALIDA} ({SALIDA.stat().st_size/1024/1024:.2f} MB)")


def main() -> None:
    print("Generando planilla de pruebas…")
    casos = construir_backend() + construir_frontend()
    print(f"  Casos construidos: {len(casos)}")
    asignar_ids(casos)
    top100 = seleccionar_top100(casos)
    print(f"  Top 100: {len(top100)}")
    generar_excel(casos, top100)
    print(f"  Guardado: {SALIDA}")
    validar()


if __name__ == "__main__":
    main()
