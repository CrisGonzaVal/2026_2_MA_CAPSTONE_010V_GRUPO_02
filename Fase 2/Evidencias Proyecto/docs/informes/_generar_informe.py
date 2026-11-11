#!/usr/bin/env python3
"""Genera el informe Word de flujos por actor de CompuStock ERP.

Requiere python-docx y Pillow. En esta máquina se instalaron en el directorio
temporal aprobado; ejecutar con PYTHONPATH apuntando a esa carpeta.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

BASE = Path(__file__).resolve().parent
DIAGRAMS = BASE.parent / "diagramas" / "flujos-actores"
OUTPUT = BASE / "Informe_Flujos_Actores.docx"

INK = RGBColor(0x1E, 0x29, 0x3B)
MUTED = RGBColor(0x47, 0x55, 0x69)
SOFT = RGBColor(0x64, 0x74, 0x8B)
ACCENT = RGBColor(0x25, 0x63, 0xEB)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
INK_HEX = "1E293B"
ACCENT_HEX = "2563EB"
MUTED_HEX = "475569"
RULE_HEX = "CBD5E1"
LIGHT_HEX = "F8FAFC"
TINT_HEX = "EFF6FF"
TINT2_HEX = "DBEAFE"

BODY_FONT = "Calibri"
DISPLAY_FONT = "Cambria"
MONO_FONT = "Consolas"


def load_flows():
    spec = importlib.util.spec_from_file_location(
        "flujos_generador", BASE.parent / "diagramas" / "flujos-actores" / "_generar.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module.FLOWS, module.NOTES


FLOWS, NOTES = load_flows()
FLOW_BY_SLUG = {flow["slug"]: flow for flow in FLOWS}

LEADS = {
    "00-acceso-comun": (
        "Este flujo es transversal: lo recorren los cuatro actores antes de entrar a su "
        "superficie. Clerk administra la identidad; CompuStock resuelve el rol, la institución "
        "y el alcance efectivo de la sesión."
    ),
    "01-superadmin-gobierno-saas": (
        "El Superadmin no opera el día a día de una institución: gobierna el SaaS. Desde "
        "`/control` revisa la cartera, habilita módulos y designa a los administradores "
        "institucionales."
    ),
    "02-superadmin-alta-institucion": (
        "El alta es el único flujo que crea un tenant. Combina los datos de la institución, su "
        "primera sede, el Administrador inicial y las capacidades contratadas."
    ),
    "03-administrador-administracion": (
        "El Administrador es el único rol que gestiona la estructura institucional. Sedes, "
        "departamentos, usuarios y encargados son la base sobre la que se apoyan inventario, "
        "pedidos y compras."
    ),
    "04-administrador-inventario-catalogo": (
        "Inventario es la vista de decisión del Administrador: existencias por sede, detalle por "
        "producto y ciclo de vida del catálogo. El stock no se edita a mano: se mueve por "
        "operaciones."
    ),
    "05-administrador-compras": (
        "Compras conecta la demanda de los pedidos con el abastecimiento. La necesidad neta se "
        "convierte en una orden de compra que, al emitirse, congela su plan y compromete stock."
    ),
    "06-administrador-pedidos": (
        "El Administrador puede operar el ciclo del pedido y también corregir o cerrar casos "
        "excepcionales. Cada decisión deja estado, motivo e historial."
    ),
    "07-bodeguero-pedidos-despacho": (
        "El Bodeguero opera el Kanban y prepara el despacho. Su alcance es la sede: no elige otra "
        "sede ni edita el pedido."
    ),
    "08-bodeguero-inventario": (
        "La consulta de inventario del Bodeguero es operativa: sirve para preparar despachos y "
        "detectar faltantes. El saldo es de la sede, no del departamento."
    ),
    "09-bodeguero-recepcion-compras": (
        "La recepción es el punto donde la compra se vuelve stock. Solo el Bodeguero de la sede "
        "destino recibe una OC facturada y desbloquea los pedidos cubiertos."
    ),
    "10-solicitante-crear-pedido": (
        "El Solicitante convierte una necesidad de su departamento en un pedido justificado. El "
        "alta no reserva ni descuenta stock: eso ocurre después, en la operación."
    ),
    "11-solicitante-seguimiento": (
        "El seguimiento es la contraparte del ciclo de vida: el Solicitante ve el estado y solo "
        "modifica lo que el estado permite."
    ),
}

ROUTES = {
    "00-acceso-comun": [
        "/", "/auth", "/dashboard", "/control", "/acceso-denegado",
    ],
    "01-superadmin-gobierno-saas": [
        "/control", "/control/dashboard", "/control/instituciones",
        "/control/instituciones/:id/capacidades",
        "/control/instituciones/:id/administradores",
    ],
    "02-superadmin-alta-institucion": ["/control/alta"],
    "03-administrador-administracion": [
        "/administracion/sedes", "/administracion/departamentos",
        "/administracion/usuarios", "/administracion/encargados",
    ],
    "04-administrador-inventario-catalogo": [
        "/inventario", "/inventario/:productoId", "API /inventario/movimientos",
    ],
    "05-administrador-compras": [
        "/compras", "/compras/necesidades", "/compras/nueva",
        "/compras/:id/editar", "API /compras/cobertura/preview",
    ],
    "06-administrador-pedidos": ["/tickets", "/tickets/:id"],
    "07-bodeguero-pedidos-despacho": [
        "/tickets", "/tickets/:id", "API POST /tickets/:id/despacho",
    ],
    "08-bodeguero-inventario": ["/dashboard", "/inventario", "/inventario/:productoId"],
    "09-bodeguero-recepcion-compras": [
        "/compras/recepcion", "API POST /compras/ordenes/:id/recepcion",
    ],
    "10-solicitante-crear-pedido": [
        "/dashboard", "/inventario", "/inventario/:productoId", "/tickets",
    ],
    "11-solicitante-seguimiento": ["/tickets", "/tickets/:id"],
}

SUMMARIES = {
    "00-acceso-comun": ("Credenciales Clerk", "Rol e institución", "Superficie permitida"),
    "01-superadmin-gobierno-saas": ("Portal /control", "Capacidades y administradores", "Institución gobernada"),
    "02-superadmin-alta-institucion": ("Datos de la institución", "Sede, Administrador y módulos", "Tenant operativo"),
    "03-administrador-administracion": ("Institución y sedes", "Estructura y roles", "Organización lista"),
    "04-administrador-inventario-catalogo": ("Catálogo y stock", "Filtros y ciclo de vida", "Stock confiable"),
    "05-administrador-compras": ("Necesidad neta", "Emitir la OC", "OC facturada"),
    "06-administrador-pedidos": ("Pedido en Kanban", "Aprobar, rechazar o editar", "Estado auditado"),
    "07-bodeguero-pedidos-despacho": ("Pedido en Kanban", "Preparar el despacho", "Pedido cerrado"),
    "08-bodeguero-inventario": ("Sede y productos", "Detectar el crítico", "Prioridad de compra"),
    "09-bodeguero-recepcion-compras": ("OC facturada", "Confirmar la recepción", "Stock y pedidos habilitados"),
    "10-solicitante-crear-pedido": ("Necesidad del departamento", "Crear el pedido", "Pedido en Pendiente"),
    "11-solicitante-seguimiento": ("Pedido propio", "Editar o anular", "Seguimiento con historial"),
}

CHECKS = {
    "00-acceso-comun": [
        "La ruta inicial coincide con el rol de la sesión.",
        "Una ruta prohibida redirige a /acceso-denegado.",
    ],
    "01-superadmin-gobierno-saas": [
        "La capacidad desactivada desaparece del menú y la API la rechaza.",
        "El Administrador asignado puede entrar a /administracion.",
    ],
    "02-superadmin-alta-institucion": [
        "El esquema tenant, la sede y el Administrador existen.",
        "La invitación llega al correo designado.",
    ],
    "03-administrador-administracion": [
        "Cada usuario tiene rol y sede coherentes.",
        "Cada departamento tiene su bodega de despacho.",
    ],
    "04-administrador-inventario-catalogo": [
        "El saldo por sede cuadra con productos y movimientos.",
        "Una baja no deja stock positivo.",
    ],
    "05-administrador-compras": [
        "La OC emitida cubre los pedidos y ya no se edita.",
        "La factura habilita la recepción del Bodeguero.",
    ],
    "06-administrador-pedidos": [
        "El estado y el historial reflejan la decisión.",
        "Un pedido anulado no se puede reactivar.",
    ],
    "07-bodeguero-pedidos-despacho": [
        "El pedido en En curso queda listo para despacho.",
        "El despacho rebaja stock y cierra el pedido.",
    ],
    "08-bodeguero-inventario": [
        "El Bodeguero no ve existencias de otras sedes.",
        "La alerta crítica coincide con el mínimo.",
    ],
    "09-bodeguero-recepcion-compras": [
        "La OC pasa a Recibida y el stock sube.",
        "Los pedidos cubiertos quedan listos para despacho.",
    ],
    "10-solicitante-crear-pedido": [
        "El pedido nace en Pendiente y no descuenta stock.",
        "El autor es la sesión, no un selector.",
    ],
    "11-solicitante-seguimiento": [
        "El Solicitante no ve acciones fuera del estado.",
        "El historial conserva cada transición.",
    ],
}

ACTOR_LIMITS = {
    "Superadmin": [
        "No opera dashboard, inventario ni pedidos de un tenant.",
        "No crea usuarios de una institución: designa administradores.",
        "El catálogo global de proveedores solo está disponible por API.",
    ],
    "Administrador institucional": [
        "No crea instituciones ni asigna administradores.",
        "No despacha ni recibe compras desde la interfaz.",
        "No ajusta stock desde un formulario; usa la API de movimientos.",
    ],
    "Bodeguero": [
        "No administra sedes, usuarios ni catálogo.",
        "No edita ni anula pedidos.",
        "No elige otra sede ni gestiona órdenes de compra.",
    ],
    "Solicitante": [
        "No opera inventario, compras ni el Kanban.",
        "No edita un pedido fuera de Pendiente.",
        "No anula fuera de Pendiente o En revisión.",
    ],
}

ACTORS = [
    {
        "num": 5,
        "name": "Superadmin",
        "eyebrow": "ACTOR 1 DE 4 · GOBIERNO GLOBAL",
        "lead": (
            "El Superadmin es el administrador global del SaaS. Su territorio es `/control`: "
            "gobierna instituciones, capacidades y administradores. No opera el dashboard, el "
            "inventario ni los pedidos de un tenant; esas rutas le responden 403 desde la 017."
        ),
        "bullets": [
            "Crea instituciones con su esquema tenant, sede inicial y primer Administrador.",
            "Activa o desactiva capacidades por institución y audita métricas globales.",
            "Asigna o revoca Administradores institucionales y gestiona sus invitaciones.",
        ],
        "funcs": [
            ("Dashboard SaaS", "/control/dashboard", "Instituciones, sedes, usuarios por rol y estado de versión."),
            ("Instituciones", "/control/instituciones", "Listado, búsqueda y detalle de la cartera."),
            ("Capacidades", "/control/instituciones/:id/capacidades", "Módulos habilitados; impactan rutas y API."),
            ("Administradores", "/control/instituciones/:id/administradores", "Asignar, revocar e invitar."),
            ("Alta de institución", "/control/alta", "Tenant, sede inicial, Administrador y módulos."),
            ("Proveedores globales", "API /compras/proveedores", "Catálogo global en `control`; sin pantalla."),
        ],
        "flows": ["01-superadmin-gobierno-saas", "02-superadmin-alta-institucion"],
    },
    {
        "num": 6,
        "name": "Administrador institucional",
        "eyebrow": "ACTOR 2 DE 4 · GESTIÓN DEL TENANT",
        "lead": (
            "El Administrador es el dueño funcional de la institución. Configura la organización, "
            "mantiene el catálogo, decide sobre los pedidos y gestiona las compras. Su alcance es "
            "el tenant completo, no una sola sede."
        ),
        "bullets": [
            "Único rol que administra sedes, departamentos, usuarios y encargados.",
            "Gestiona el ciclo de vida del catálogo y consulta el inventario con filtros.",
            "Crea, emite, factura y cancela órdenes de compra; opera el ciclo del pedido.",
        ],
        "funcs": [
            ("Administración", "/administracion/*", "Sedes, departamentos, usuarios y encargados."),
            ("Dashboard", "/dashboard", "Indicadores, alertas y actividad reciente."),
            ("Inventario", "/inventario", "Existencias, filtros, detalle y catálogo."),
            ("Pedidos", "/tickets", "Kanban, detalle, estados, edición, rechazo y anulación."),
            ("Compras", "/compras", "Necesidades, OC, emisión, factura y cancelación."),
            ("Proveedores", "API /compras/proveedores", "Alta desde la OC; se replica al tenant."),
        ],
        "flows": [
            "03-administrador-administracion",
            "04-administrador-inventario-catalogo",
            "05-administrador-compras",
            "06-administrador-pedidos",
        ],
    },
    {
        "num": 7,
        "name": "Bodeguero",
        "eyebrow": "ACTOR 3 DE 4 · OPERACIÓN DE SEDE",
        "lead": (
            "El Bodeguero es el operador de la sede. Prepara y despacha pedidos, consulta el stock "
            "físico y recibe las compras facturadas. No administra la organización, el catálogo ni "
            "las órdenes de compra."
        ),
        "bullets": [
            "Opera el Kanban de su sede: avanza, retrocede y rechaza pedidos con motivo.",
            "Consulta inventario y detecta productos críticos; la sede la fija el servidor.",
            "Recibe OC facturadas de su sede y desbloquea los pedidos cubiertos.",
        ],
        "funcs": [
            ("Dashboard", "/dashboard", "Stock, pedidos activos y alertas de la sede."),
            ("Inventario", "/inventario", "Existencias, filtros y detalle por producto."),
            ("Pedidos", "/tickets", "Kanban, detalle, avance, retroceso y rechazo."),
            ("Despacho", "API /tickets/:id/despacho", "Rebaja stock y cierra el pedido."),
            ("Recepción", "/compras/recepcion", "OC facturadas de la sede; confirmación irreversible."),
            ("Movimientos", "API /inventario/movimientos", "Ajustes de stock; sin formulario en la UI."),
        ],
        "flows": [
            "07-bodeguero-pedidos-despacho",
            "08-bodeguero-inventario",
            "09-bodeguero-recepcion-compras",
        ],
    },
    {
        "num": 8,
        "name": "Solicitante",
        "eyebrow": "ACTOR 4 DE 4 · DEMANDA",
        "lead": (
            "El Solicitante representa la necesidad del departamento. Consulta disponibilidad, crea "
            "pedidos justificados y sigue su estado. No opera inventario, compras ni transiciones "
            "del Kanban."
        ),
        "bullets": [
            "Consulta el catálogo y el stock sin filtros de sede.",
            "Crea pedidos con prioridad, asunto, descripción e ítems; el autor es la sesión.",
            "Edita o anula su pedido solo mientras el estado lo permite.",
        ],
        "funcs": [
            ("Dashboard", "/dashboard", "Resumen de stock, pedidos y alertas de su ámbito."),
            ("Inventario", "/inventario", "Catálogo y disponibilidad; sin filtros de sede."),
            ("Pedidos", "/tickets", "Kanban propio y alta con el modal “+ Crear pedido”."),
            ("Detalle", "/tickets/:id", "Estado, ítems, cobertura e historial."),
            ("Editar", "/tickets/:id", "Solo en Pendiente, y solo el pedido propio."),
            ("Anular", "/tickets/:id", "Pendiente o En revisión, con motivo."),
        ],
        "flows": ["10-solicitante-crear-pedido", "11-solicitante-seguimiento"],
    },
]

MATRIX = [
    ("Iniciar sesión y resolver el rol", "Sí", "Sí", "Sí", "Sí"),
    ("Dashboard global SaaS", "Sí", "—", "—", "—"),
    ("Dashboard operativo", "—", "Sí", "Sí", "Sí"),
    ("Gobierno de instituciones y capacidades", "Sí", "—", "—", "—"),
    ("Alta de institución", "Sí", "—", "—", "—"),
    ("Administrar sedes y departamentos", "—", "Sí", "—", "—"),
    ("Administrar usuarios y encargados", "—", "Sí", "—", "—"),
    ("Consultar inventario y productos", "—", "Sí", "Sí", "Sí"),
    ("Filtrar inventario por sede/departamento", "—", "Sí", "Sí (sede fija)", "—"),
    ("Gestionar catálogo y ciclo de vida", "—", "Sí", "—", "—"),
    ("Registrar movimientos de stock", "—", "API", "API", "—"),
    ("Crear pedido", "—", "Sí", "Sí", "Sí (principal)"),
    ("Avanzar o retroceder pedido", "—", "Sí", "Sí", "—"),
    ("Rechazar pedido con motivo", "—", "Sí", "Sí", "—"),
    ("Editar pedido", "—", "Sí", "—", "Propio (Pendiente)"),
    ("Anular pedido con motivo", "—", "Sí", "—", "Propio (Pendiente / En revisión)"),
    ("Despachar pedido", "—", "API", "API", "—"),
    ("Gestionar compras y órdenes de compra", "—", "Sí", "—", "—"),
    ("Recibir compras facturadas", "—", "—", "Sí", "—"),
    ("Catálogo global de proveedores", "API", "—", "—", "—"),
    ("Alta de proveedor desde una OC", "—", "Sí", "—", "—"),
    ("Consultar cobertura e historial", "—", "Sí", "Sí", "Propio"),
    ("Auditar métricas del SaaS", "Sí", "—", "—", "—"),
]

API_ONLY = [
    ("Movimiento de stock", "POST /api/v1/inventario/movimientos", "Administrador y Bodeguero",
     "No hay formulario de ajuste en Inventario; el saldo se mueve por despacho y recepción."),
    ("Despacho de pedido", "POST /api/v1/tickets/{ticket_id}/despacho", "Administrador y Bodeguero",
     "El detalle bloquea el avance desde En curso; el cierre y la rebaja los ejecuta el despacho."),
    ("Catálogo global de proveedores", "GET/POST /api/v1/compras/proveedores", "Superadmin",
     "El portal `/control` no tiene pantalla de proveedores; el Administrador da de alta los suyos desde la OC."),
    ("Operación de pedidos del Superadmin", "API de tickets", "Superadmin (sin UI)",
     "La 017 retiró las lecturas y escrituras de tenant del Superadmin; no navega `/tickets`."),
]

SOURCES = [
    ("frontend/src/app/app.routes.ts", "Rutas reales y guards por rol.", "Mapa de navegación y alcance."),
    ("frontend/src/app/core/auth/roles.ts", "Matriz de roles, permisos y redirecciones.", "Actores y acciones permitidas."),
    ("frontend/src/app/app.component.html", "Menú lateral y etiquetas visibles.", "Nombres de secciones y flujos."),
    ("backend/app/core/permisos.py", "Matriz operación → roles de la API.", "Verificación de límites y funciones API."),
    ("docs/spec/features/003-modal-ticket/", "Alta de pedido y modal.", "Flujo del Solicitante."),
    ("docs/spec/features/012-gestion-administrativa/", "Administración y portal SaaS.", "Flujos de Superadmin y Administrador."),
    ("docs/spec/features/013-ciclo-vida-ticket/", "Estados, edición, rechazo y anulación.", "Flujo de pedidos y seguimiento."),
    ("docs/spec/features/014-ciclo-vida-catalogo/", "Ciclo de vida del catálogo.", "Inventario del Administrador."),
    ("docs/spec/features/017-provisionamiento-y-gobierno-de-identidades/", "Invitaciones y gobierno de identidades.", "Alta y administradores."),
    ("docs/spec/features/018-filtro-inventario-sede-departamento/", "Filtros y alcance por sede.", "Inventario del Administrador y Bodeguero."),
    ("docs/spec/features/019-detalle-producto-por-alcance/", "Detalle de producto por alcance.", "Flujos de inventario."),
    ("docs/spec/features/020-reabastecimiento-compras/", "OC, factura y recepción.", "Compras y recepción."),
    ("docs/spec/features/021-cobertura-automatica-tickets-compras/", "Cobertura, plan congelado y desbloqueo.", "Compras y recepción."),
    ("docs/diagramas/flujos-actores/", "HTML y PNG de los 12 flujos.", "Figuras del informe."),
]

DELIVERABLES = [
    ("docs/informes/Informe_Flujos_Actores.docx", "Word (A4 horizontal)", "Informe completo con 12 diagramas y tablas de pasos."),
    ("docs/diagramas/flujos-actores/*.html", "HTML autocontenido", "Fuente vectorial de cada diagrama."),
    ("docs/diagramas/flujos-actores/*.png", "PNG 2400×1120", "Exportación 2x para el informe y reutilización."),
    ("docs/diagramas/flujos-actores/README.md", "Markdown", "Índice, convenciones y reproducción."),
    ("docs/diagramas/flujos-actores/_generar.py", "Python", "Genera los HTML desde una sola definición de datos."),
    ("docs/diagramas/flujos-actores/_exportar.ps1", "PowerShell", "Exporta los PNG con Edge headless."),
    ("docs/informes/_generar_informe.py", "Python", "Genera este DOCX a partir de los diagramas y sus datos."),
]


def rgb(hex_value: str) -> RGBColor:
    value = hex_value.lstrip("#")
    return RGBColor(int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))


def set_run_font(run, name: str, size: float, bold: bool = False, italic: bool = False,
                 color: RGBColor = INK):
    run.font.name = name
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = color
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    for attr in ("w:ascii", "w:hAnsi", "w:cs"):
        rfonts.set(qn(attr), name)
    rfonts.set(qn("w:eastAsia"), name)


def add_text(paragraph, text: str, size: float = 10, bold: bool = False,
             italic: bool = False, color: RGBColor = INK, font: str = BODY_FONT):
    # El contenido se escribe para Word: los backticks de Markdown no se muestran.
    text = text.replace("`", "")
    run = paragraph.add_run(text)
    set_run_font(run, font, size, bold, italic, color)
    return run


def para(container, text: str = "", size: float = 10, bold: bool = False,
         italic: bool = False, color: RGBColor = INK, font: str = BODY_FONT,
         align=WD_ALIGN_PARAGRAPH.LEFT, space_before: float = 0,
         space_after: float = 4, line_spacing: float = 1.12,
         keep_with_next: bool = False):
    p = container.add_paragraph()
    p.alignment = align
    pf = p.paragraph_format
    pf.space_before = Pt(space_before)
    pf.space_after = Pt(space_after)
    pf.line_spacing = line_spacing
    pf.keep_with_next = keep_with_next
    if text:
        add_text(p, text, size, bold, italic, color, font)
    return p


def add_bottom_border(paragraph, color: str = RULE_HEX, size: int = 6, space: int = 4):
    p_pr = paragraph._p.get_or_add_pPr()
    p_bdr = p_pr.find(qn("w:pBdr"))
    if p_bdr is None:
        p_bdr = OxmlElement("w:pBdr")
        p_pr.append(p_bdr)
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), str(size))
    bottom.set(qn("w:space"), str(space))
    bottom.set(qn("w:color"), color)
    p_bdr.append(bottom)


def shade_cell(cell, hex_color: str):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    tc_pr.append(shd)


def set_cell_margins(cell, top: int = 40, bottom: int = 40, left: int = 90, right: int = 90):
    tc_pr = cell._tc.get_or_add_tcPr()
    mar = OxmlElement("w:tcMar")
    for side, value in (("top", top), ("bottom", bottom), ("left", left), ("right", right)):
        el = OxmlElement(f"w:{side}")
        el.set(qn("w:w"), str(value))
        el.set(qn("w:type"), "dxa")
        mar.append(el)
    tc_pr.append(mar)


def set_table_borders(table, color: str = RULE_HEX, size: int = 4, none: bool = False):
    tbl_pr = table._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{edge}")
        if none:
            el.set(qn("w:val"), "nil")
        else:
            el.set(qn("w:val"), "single")
            el.set(qn("w:sz"), str(size))
            el.set(qn("w:space"), "0")
            el.set(qn("w:color"), color)
        borders.append(el)
    tbl_pr.append(borders)


def set_cell_border(cell, edges: dict[str, tuple[str, int]], color: str = RULE_HEX):
    tc_pr = cell._tc.get_or_add_tcPr()
    borders = OxmlElement("w:tcBorders")
    for edge, (val, size) in edges.items():
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), val)
        el.set(qn("w:sz"), str(size))
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), color)
        borders.append(el)
    tc_pr.append(borders)


def set_col_widths(table, widths_cm: list[float]):
    table.autofit = False
    tbl_pr = table._tbl.tblPr
    layout = OxmlElement("w:tblLayout")
    layout.set(qn("w:type"), "fixed")
    tbl_pr.append(layout)
    twips = sum(int(Cm(w).twips) for w in widths_cm)
    tbl_w = OxmlElement("w:tblW")
    tbl_w.set(qn("w:type"), "dxa")
    tbl_w.set(qn("w:w"), str(twips))
    tbl_pr.append(tbl_w)
    for row in table.rows:
        for idx, width in enumerate(widths_cm):
            row.cells[idx].width = Cm(width)
    for idx, width in enumerate(widths_cm):
        table.columns[idx].width = Cm(width)


def mark_header_row(row):
    tr_pr = row._tr.get_or_add_trPr()
    header = OxmlElement("w:tblHeader")
    header.set(qn("w:val"), "true")
    tr_pr.append(header)


def mark_no_split(row):
    tr_pr = row._tr.get_or_add_trPr()
    cant = OxmlElement("w:cantSplit")
    cant.set(qn("w:val"), "true")
    tr_pr.append(cant)


def style_table(table, header_bg: str = INK_HEX, header_fg: RGBColor = WHITE,
                font_size: float = 8.5):
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(table, RULE_HEX, 4)
    for row_idx, row in enumerate(table.rows):
        mark_no_split(row)
        for cell in row.cells:
            cell.vertical_alignment = WD_ALIGN_VERTICAL.TOP
            set_cell_margins(cell)
            if row_idx == 0:
                shade_cell(cell, header_bg)
                for p in cell.paragraphs:
                    for run in p.runs:
                        run.font.bold = True
                        run.font.color.rgb = header_fg
                        run.font.size = Pt(font_size)
            elif row_idx % 2 == 0:
                shade_cell(cell, LIGHT_HEX)
    mark_header_row(table.rows[0])


def write_cell(cell, text: str, size: float = 8.5, bold: bool = False,
               color: RGBColor = INK, font: str = BODY_FONT,
               align=WD_ALIGN_PARAGRAPH.LEFT):
    cell.text = ""
    p = cell.paragraphs[0]
    p.alignment = align
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.line_spacing = 1.05
    add_text(p, text, size, bold, False, color, font)


def add_field(paragraph, instruction: str, fallback: str = "1"):
    run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = instruction
    sep = OxmlElement("w:fldChar")
    sep.set(qn("w:fldCharType"), "separate")
    text = OxmlElement("w:t")
    text.text = fallback
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run._r.append(begin)
    run._r.append(instr)
    run._r.append(sep)
    run._r.append(text)
    run._r.append(end)


def configure_document() -> Document:
    doc = Document()
    section = doc.sections[0]
    section.orientation = WD_ORIENT.LANDSCAPE
    section.page_width = Cm(29.7)
    section.page_height = Cm(21.0)
    section.top_margin = Cm(1.7)
    section.bottom_margin = Cm(1.5)
    section.left_margin = Cm(1.8)
    section.right_margin = Cm(1.8)
    section.header_distance = Cm(0.7)
    section.footer_distance = Cm(0.6)
    section.different_first_page_header_footer = True

    styles = doc.styles
    normal = styles["Normal"]
    normal.font.name = BODY_FONT
    normal.font.size = Pt(10)
    normal.font.color.rgb = INK
    normal.paragraph_format.space_after = Pt(4)
    normal.paragraph_format.line_spacing = 1.12

    for style_name, font, size, color, before, after in (
        ("Heading 1", DISPLAY_FONT, 20, INK, 0, 6),
        ("Heading 2", DISPLAY_FONT, 15, ACCENT, 0, 4),
        ("Heading 3", BODY_FONT, 11, INK, 8, 3),
    ):
        style = styles[style_name]
        style.font.name = font
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = color
        style.paragraph_format.space_before = Pt(before)
        style.paragraph_format.space_after = Pt(after)
        style.paragraph_format.keep_with_next = True
        style.paragraph_format.line_spacing = 1.0

    # Encabezado y pie de las páginas interiores.
    header = section.header
    hp = header.paragraphs[0]
    hp.text = ""
    hp.paragraph_format.tab_stops.add_tab_stop(Cm(26.1), WD_TAB_ALIGNMENT.RIGHT)
    add_text(hp, "CompuStock ERP · Flujos por actor", 8, False, False, SOFT, MONO_FONT)
    add_text(hp, "\t", 8, False, False, SOFT, MONO_FONT)
    add_text(hp, "Rama ricardo · Noviembre 2026", 8, False, False, SOFT, MONO_FONT)
    add_bottom_border(hp, RULE_HEX, 4, 2)

    footer = section.footer
    fp = footer.paragraphs[0]
    fp.text = ""
    fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    add_text(fp, "Página ", 8, False, False, SOFT, MONO_FONT)
    add_field(fp, " PAGE ", "1")
    add_text(fp, " de ", 8, False, False, SOFT, MONO_FONT)
    add_field(fp, " NUMPAGES ", "1")

    # Portada sin encabezado ni pie.
    section.first_page_header.paragraphs[0].text = ""
    section.first_page_footer.paragraphs[0].text = ""

    core = doc.core_properties
    core.title = "CompuStock ERP — Flujos de uso por actor"
    core.subject = "Informe visual de funciones y flujos por actor"
    core.author = "Equipo CompuStock"
    core.keywords = "CompuStock, ERP, flujos, actores, Superadmin, Administrador, Bodeguero, Solicitante"
    core.comments = "Documento generado a partir de las rutas, roles y evidencias del repositorio."
    return doc


def add_cover(doc: Document):
    for _ in range(2):
        para(doc, "", size=10, space_after=0)

    p = para(doc, "COMPUSTOCK ERP  ·  DOCUMENTO DE FLUJOS", 9, True, False, ACCENT, MONO_FONT, space_after=8)
    p.paragraph_format.keep_with_next = True

    p = para(doc, "Flujos de uso por actor", 34, True, False, INK, DISPLAY_FONT, space_after=2)
    p.paragraph_format.keep_with_next = True

    para(doc, "Guía visual paso a paso de las funciones principales del sistema", 15, False, False, MUTED, BODY_FONT, space_after=10)

    line = para(doc, "", space_before=0, space_after=12)
    add_bottom_border(line, ACCENT_HEX, 18, 6)
    line.paragraph_format.right_indent = Cm(18)

    # Tres cifras de portada.
    stats = doc.add_table(rows=1, cols=3)
    stats.alignment = WD_TABLE_ALIGNMENT.LEFT
    set_table_borders(stats, "FFFFFF", 0, none=True)
    set_col_widths(stats, [5.2, 5.2, 5.2])
    for idx, (number, label) in enumerate((("12", "diagramas de flujo"), ("4", "actores del sistema"), ("72", "pasos documentados"))):
        cell = stats.rows[0].cells[idx]
        shade_cell(cell, TINT_HEX)
        set_cell_margins(cell, 120, 100, 160, 120)
        cell.text = ""
        p1 = cell.paragraphs[0]
        p1.alignment = WD_ALIGN_PARAGRAPH.LEFT
        p1.paragraph_format.space_after = Pt(0)
        add_text(p1, number, 24, True, False, ACCENT, DISPLAY_FONT)
        p2 = cell.add_paragraph()
        p2.paragraph_format.space_before = Pt(0)
        p2.paragraph_format.space_after = Pt(0)
        add_text(p2, label, 8.5, False, False, MUTED, MONO_FONT)

    para(doc, "", size=4, space_after=8)

    meta = doc.add_table(rows=7, cols=2)
    meta.style = "Table Grid"
    set_table_borders(meta, RULE_HEX, 4)
    set_col_widths(meta, [4.2, 15.8])
    rows = [
        ("Versión", "1.0"),
        ("Fecha", "11 de noviembre de 2026"),
        ("Rama", "`ricardo` (trabajo local; sin publicación)"),
        ("Entorno", "http://localhost:4200 (dev server con el código actual)"),
        ("Alcance", "Funciones principales de Superadmin, Administrador, Bodeguero y Solicitante"),
        ("Fuente", "Rutas, roles, componentes y evidencias del repositorio"),
        ("Estado", "Entregable de documentación; no modifica código de producto"),
    ]
    for idx, (label, value) in enumerate(rows):
        c0, c1 = meta.rows[idx].cells
        for cell in (c0, c1):
            set_cell_margins(cell, 50, 50, 100, 100)
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        shade_cell(c0, LIGHT_HEX)
        write_cell(c0, label, 8.5, True, MUTED, MONO_FONT)
        write_cell(c1, value, 9, False, INK, BODY_FONT)

    para(doc, "", size=4, space_after=16)
    para(doc, "Documento de apoyo para la revisión funcional del proyecto. Los diagramas se generaron con la misma identidad visual de los diagramas 4+1 y se exportaron a PNG de 2400 × 1120 px.", 8.5, False, True, SOFT, BODY_FONT, space_after=0)
    doc.add_page_break()


def add_document_map(doc: Document):
    add_h1(doc, "Control del documento")
    para(doc, "Este informe describe cómo usa CompuStock cada actor y qué resultado obtiene en cada paso. No es un manual de instalación ni una especificación técnica: es una lectura funcional, trazable al código y a las evidencias del repositorio.", 10, False, False, MUTED, space_after=8)

    table = doc.add_table(rows=1, cols=2)
    set_col_widths(table, [6.0, 19.8])
    headers = ["Campo", "Detalle"]
    for idx, header in enumerate(headers):
        write_cell(table.rows[0].cells[idx], header, 8.5, True, WHITE, MONO_FONT)
    style_table(table)
    rows = [
        ("Título", "CompuStock ERP — Flujos de uso por actor"),
        ("Versión", "1.0"),
        ("Fecha", "11/11/2026"),
        ("Rama", "`ricardo` (local)"),
        ("Base de código", "Rutas, roles y componentes del frontend; matriz de permisos del backend."),
        ("Cobertura", "12 flujos: 1 transversal, 2 de Superadmin, 4 de Administrador, 3 de Bodeguero y 2 de Solicitante."),
        ("Formato", "A4 horizontal, con diagramas a ancho completo y tablas de pasos."),
        ("Entregables", "Este DOCX, 12 HTML, 12 PNG y el README de la carpeta de diagramas."),
    ]
    for label, value in rows:
        row = table.add_row()
        write_cell(row.cells[0], label, 8.5, True, MUTED, MONO_FONT)
        write_cell(row.cells[1], value, 9, False, INK, BODY_FONT)
    for idx, row in enumerate(table.rows):
        if idx > 0:
            shade_cell(row.cells[0], LIGHT_HEX)

    para(doc, "", size=4, space_after=8)
    add_h2(doc, "Mapa del documento")
    mapa = doc.add_table(rows=1, cols=2)
    set_col_widths(mapa, [7.5, 18.3])
    for idx, header in enumerate(["Sección", "Qué encontrar"]):
        write_cell(mapa.rows[0].cells[idx], header, 8.5, True, WHITE, MONO_FONT)
    style_table(mapa)
    secciones = [
        ("1. Propósito y alcance", "Qué cubre el informe, qué deja fuera y por qué se usaron diagramas."),
        ("2. Actores y acceso", "Los cuatro roles, su superficie y la lógica de autorización."),
        ("3. Cómo leer los diagramas", "Convenciones visuales y significado de cada elemento."),
        ("4. Flujo común de acceso", "Login Clerk, resolución de identidad y ruta inicial."),
        ("5. Superadmin", "Gobierno SaaS y alta de institución."),
        ("6. Administrador", "Administración, inventario, compras y pedidos."),
        ("7. Bodeguero", "Pedidos y despacho, inventario y recepción de compras."),
        ("8. Solicitante", "Alta de pedido y seguimiento."),
        ("9. Matriz de funciones", "Qué puede hacer cada actor, incluidas las operaciones API."),
        ("10. Funciones sin pantalla", "Límites conocidos entre la UI y la API."),
        ("11. Trazabilidad", "Fuentes usadas para cada flujo."),
        ("12. Entregables y cierre", "Archivos, validación y observaciones."),
    ]
    for seccion, detalle in secciones:
        row = mapa.add_row()
        write_cell(row.cells[0], seccion, 8.5, True, INK, BODY_FONT)
        write_cell(row.cells[1], detalle, 8.5, False, MUTED, BODY_FONT)
    for idx, row in enumerate(mapa.rows):
        if idx > 0 and idx % 2 == 0:
            for cell in row.cells:
                shade_cell(cell, LIGHT_HEX)


def add_h1(doc: Document, text: str):
    p = doc.add_paragraph(style="Heading 1")
    add_text(p, text, 20, True, False, INK, DISPLAY_FONT)
    add_bottom_border(p, ACCENT_HEX, 10, 3)
    return p


def add_h2(doc: Document, text: str):
    p = doc.add_paragraph(style="Heading 2")
    add_text(p, text, 15, True, False, ACCENT, DISPLAY_FONT)
    return p


def add_h3(doc: Document, text: str):
    p = doc.add_paragraph(style="Heading 3")
    add_text(p, text, 11, True, False, INK, BODY_FONT)
    return p


def add_label(doc: Document, text: str, color: RGBColor = ACCENT):
    p = para(doc, text.upper(), 8.5, True, False, color, MONO_FONT, space_before=4, space_after=3, keep_with_next=True)
    return p


def add_bullets(doc: Document, items: list[str], size: float = 9.5):
    for item in items:
        p = doc.add_paragraph(style="List Bullet")
        p.paragraph_format.space_after = Pt(2)
        p.paragraph_format.line_spacing = 1.05
        add_text(p, item, size, False, False, INK, BODY_FONT)


def add_small_table(doc: Document, headers: list[str], rows: list[tuple[str, ...]],
                    widths: list[float], font_size: float = 8.5):
    table = doc.add_table(rows=1, cols=len(headers))
    set_col_widths(table, widths)
    for idx, header in enumerate(headers):
        write_cell(table.rows[0].cells[idx], header, font_size, True, WHITE, MONO_FONT)
    style_table(table, font_size=font_size)
    for values in rows:
        row = table.add_row()
        for idx, value in enumerate(values):
            write_cell(row.cells[idx], value, font_size, idx == 0, INK if idx != 0 else INK, BODY_FONT)
    return table


def add_route_line(doc: Document, slug: str):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(6)
    add_text(p, "Rutas implicadas: ", 8, True, False, MUTED, MONO_FONT)
    for idx, route in enumerate(ROUTES[slug]):
        if idx:
            add_text(p, "   ·   ", 8, False, False, SOFT, MONO_FONT)
        add_text(p, route, 8, False, False, ACCENT if route.startswith("API") else MUTED, MONO_FONT)


def add_image(doc: Document, image_path: Path, caption: str, alt: str):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(2)
    run = p.add_run()
    shape = run.add_picture(str(image_path), width=Cm(25.2))
    # Borde fino para separar el papel del diagrama del fondo de la página.
    inline = shape._inline
    try:
        sp_pr = inline.graphic.graphicData.pic.spPr
        ln = OxmlElement("a:ln")
        ln.set("w", "6350")
        solid = OxmlElement("a:solidFill")
        srgb = OxmlElement("a:srgbClr")
        srgb.set("val", "CBD5E1")
        solid.append(srgb)
        ln.append(solid)
        sp_pr.append(ln)
    except Exception:
        pass
    # Texto alternativo.
    try:
        doc_pr = inline.docPr
        doc_pr.set("descr", alt)
    except Exception:
        pass

    cp = doc.add_paragraph()
    cp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cp.paragraph_format.space_before = Pt(1)
    cp.paragraph_format.space_after = Pt(2)
    add_text(cp, caption, 8.5, False, True, SOFT, BODY_FONT)


def add_note(doc: Document, text: str, title: str = "Nota"):
    table = doc.add_table(rows=1, cols=1)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_col_widths(table, [25.2])
    cell = table.rows[0].cells[0]
    shade_cell(cell, TINT_HEX)
    set_cell_border(cell, {"left": ("single", 24), "top": ("nil", 0), "bottom": ("nil", 0), "right": ("nil", 0)}, ACCENT_HEX)
    set_cell_margins(cell, 100, 100, 160, 120)
    cell.text = ""
    p = cell.paragraphs[0]
    p.paragraph_format.space_after = Pt(2)
    add_text(p, title.upper(), 8, True, False, ACCENT, MONO_FONT)
    p2 = cell.add_paragraph()
    p2.paragraph_format.space_after = Pt(0)
    p2.paragraph_format.line_spacing = 1.08
    add_text(p2, text, 9, False, False, MUTED, BODY_FONT)


def add_actor_intro(doc: Document, actor: dict):
    doc.add_page_break()
    add_h1(doc, f"{actor['num']}. {actor['name']}")
    para(doc, actor["eyebrow"], 8.5, True, False, ACCENT, MONO_FONT, space_after=6)
    para(doc, actor["lead"], 10.5, False, False, MUTED, BODY_FONT, space_after=8)
    add_label(doc, "Alcance del actor")
    add_bullets(doc, actor["bullets"])
    para(doc, "", size=4, space_after=4)
    add_label(doc, "Funciones principales")
    add_small_table(doc, ["Función", "Ruta / medio", "Qué permite"], actor["funcs"], [5.2, 7.4, 12.6], 8.5)
    para(doc, "", size=4, space_after=6)
    add_label(doc, "Flujos documentados")
    for slug in actor["flows"]:
        flow = FLOW_BY_SLUG[slug]
        fig = next(idx for idx, f in enumerate(FLOWS, start=1) if f["slug"] == slug)
        p = doc.add_paragraph(style="List Bullet")
        p.paragraph_format.space_after = Pt(2)
        add_text(p, f"Figura {fig} — {flow['title']}", 9.5, True, False, INK, BODY_FONT)
        add_text(p, f"  ·  {flow['scope']}", 8.5, False, False, SOFT, MONO_FONT)

    para(doc, "", size=4, space_after=4)
    add_label(doc, "Límites del rol")
    add_bullets(doc, ACTOR_LIMITS[actor["name"]], 9.5)


def add_flow_section(doc: Document, slug: str, section_num: int, sub: int):
    flow = FLOW_BY_SLUG[slug]
    fig = next(idx for idx, f in enumerate(FLOWS, start=1) if f["slug"] == slug)
    doc.add_page_break()
    add_h2(doc, f"{section_num}.{sub} {flow['title']}")
    para(doc, LEADS[slug], 10, False, False, MUTED, BODY_FONT, space_after=4)
    add_route_line(doc, slug)
    add_image(
        doc,
        DIAGRAMS / f"{slug}.png",
        f"Figura {fig}. {flow['title']} — {flow['actor']}.",
        f"Diagrama de flujo de {flow['actor']}: {flow['title']}",
    )
    para(
        doc,
        "El diagrama resume el recorrido; la tabla de la página siguiente detalla qué ocurre en cada paso y qué resultado deja.",
        8.5, False, True, SOFT, BODY_FONT, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=0,
    )

    doc.add_page_break()
    add_h3(doc, "Paso a paso")
    para(doc, "La numeración coincide con las tarjetas del diagrama. El resultado es el estado que queda al terminar el paso.", 9, False, False, MUTED, space_after=5)
    table = doc.add_table(rows=1, cols=4)
    set_col_widths(table, [1.0, 4.6, 13.4, 6.2])
    headers = ["#", "Paso", "Qué ocurre", "Resultado"]
    for idx, header in enumerate(headers):
        write_cell(table.rows[0].cells[idx], header, 8.5, True, WHITE, MONO_FONT)
    style_table(table)
    for idx, (title, body, result) in enumerate(flow["steps"], start=1):
        row = table.add_row()
        write_cell(row.cells[0], str(idx), 9, True, ACCENT, MONO_FONT, WD_ALIGN_PARAGRAPH.CENTER)
        write_cell(row.cells[1], title, 8.8, True, INK, BODY_FONT)
        write_cell(row.cells[2], body, 8.5, False, MUTED, BODY_FONT)
        write_cell(row.cells[3], result, 8.5, True, INK, BODY_FONT)

    p = para(doc, "", space_before=6, space_after=4)
    add_text(p, "Resultado del flujo: ", 9.5, True, False, ACCENT, BODY_FONT)
    add_text(p, flow["result"], 9.5, False, False, INK, BODY_FONT)

    note = NOTES.get(slug)
    if note:
        add_note(doc, note)

    entrada, decision, salida = SUMMARIES[slug]
    add_h3(doc, "Resumen del flujo")
    summary = doc.add_table(rows=1, cols=3)
    set_col_widths(summary, [8.4, 8.4, 8.4])
    for idx, header in enumerate(["Entrada", "Decisión clave", "Salida"]):
        write_cell(summary.rows[0].cells[idx], header, 8.5, True, WHITE, MONO_FONT)
    style_table(summary, font_size=8.5)
    row = summary.add_row()
    for idx, value in enumerate((entrada, decision, salida)):
        write_cell(row.cells[idx], value, 9, idx == 1, INK, BODY_FONT)
    for cell in row.cells:
        shade_cell(cell, TINT_HEX)

    add_label(doc, "Puntos de control")
    add_bullets(doc, CHECKS[slug], 9)


def add_propósito(doc: Document):
    doc.add_page_break()
    add_h1(doc, "1. Propósito y alcance")
    para(doc, "Este documento explica, actor por actor, cómo se recorre CompuStock para cumplir las funciones principales del sistema. Cada flujo combina un diagrama de pasos con una tabla que describe qué ocurre y qué resultado deja el paso.", 10.5, False, False, MUTED, space_after=6)
    para(doc, "El objetivo es que una persona que revisa el proyecto pueda entender la operación sin abrir el código: quién entra, qué ve, qué decide, qué se guarda y qué límites tiene la interfaz.", 10.5, False, False, MUTED, space_after=8)

    add_h3(doc, "Qué incluye")
    add_bullets(doc, [
        "Los cuatro actores del sistema y su superficie real de navegación.",
        "12 flujos funcionales: acceso, gobierno SaaS, administración, inventario, compras, pedidos, despacho, recepción y seguimiento.",
        "Una matriz de funciones por actor y una lista explícita de operaciones que hoy viven solo en la API.",
        "La trazabilidad de cada flujo a rutas, roles, componentes y evidencias del repositorio.",
    ])

    add_h3(doc, "Qué deja fuera")
    add_bullets(doc, [
        "Instalación, despliegue y configuración de Clerk o PostgreSQL.",
        "Detalle de implementación interna (modelos, SQL, tests) salvo cuando explica un límite funcional.",
        "Capturas de pantalla: se optó por diagramas de flujo para que el paso a paso sea legible en Word y no dependa de la resolución de una captura.",
        "Funciones no implementadas o fuera del alcance de las features 000–021.",
    ])

    add_note(doc, "Los diagramas no son decorativos: cada tarjeta corresponde a un paso verificable en las rutas y componentes del frontend. Cuando una operación solo existe en la API, el informe lo dice de forma explícita.")

    add_h3(doc, "Criterio de lectura")
    para(doc, "Un flujo puede tener pasos que no son clics literales. Por ejemplo, “resolver identidad” ocurre en una llamada a `/auth/me` y “aplicar el rol” ocurre en un guard de navegación. Se documentan como hitos funcionales porque son los que explican el comportamiento del sistema.", 10, False, False, MUTED)


def add_actores(doc: Document):
    doc.add_page_break()
    add_h1(doc, "2. Actores y acceso")
    para(doc, "CompuStock tiene cuatro roles distintos. No son alias ni variantes: la matriz de permisos del backend los trata como identidades separadas y un rol ausente o desconocido nunca concede permiso.", 10.5, False, False, MUTED, space_after=6)

    rows = [
        ("Superadmin", "Global (SaaS)", "`/control`", "Instituciones, capacidades, administradores y métricas globales."),
        ("Administrador", "Una institución", "`/administracion`, `/inventario`, `/tickets`, `/compras`", "Organización, catálogo, pedidos y compras."),
        ("Bodeguero", "Una sede", "`/dashboard`, `/inventario`, `/tickets`, `/compras/recepcion`", "Stock físico, Kanban, despacho y recepción."),
        ("Solicitante", "Su departamento", "`/dashboard`, `/inventario`, `/tickets`", "Consulta, alta y seguimiento de pedidos."),
    ]
    add_small_table(doc, ["Actor", "Alcance", "Superficie", "Funciones clave"], rows, [4.2, 4.2, 9.0, 7.8], 8.5)

    add_h3(doc, "Cómo se resuelve el acceso")
    para(doc, "Clerk autentica y entrega el token. Angular lo adjunta como Bearer; la API valida el JWT y resuelve la identidad. El frontend usa el rol para decidir la ruta inicial y el menú, pero la frontera de seguridad real está en la API: una ruta oculta no es un permiso.", 10, False, False, MUTED, space_after=4)
    add_bullets(doc, [
        "Superadmin entra a `/control`; los roles de negocio entran a `/dashboard`.",
        "Las rutas de tenant están protegidas por guards de rol y por la matriz de permisos del backend.",
        "Una ruta prohibida no rompe la sesión: redirige a `/acceso-denegado`.",
    ])

    add_h3(doc, "Fronteras que conviene tener presentes")
    add_bullets(doc, [
        "El Superadmin no lee dashboard, inventario ni pedidos de un tenant desde la 017. Su gobierno de administradores vive en `/control`.",
        "El Administrador solo puede asignar roles Bodeguero o Solicitante; no crea otro Administrador ni un Superadmin.",
        "El Bodeguero no elige sede: el servidor fija la suya. El Solicitante no filtra por sede ni despacha.",
        "El despacho y el ajuste de stock existen en la API; la UI no expone un botón o formulario para todas esas operaciones.",
    ])


def add_como_leer(doc: Document):
    doc.add_page_break()
    add_h1(doc, "3. Cómo leer los diagramas")
    para(doc, "Los diagramas usan una secuencia horizontal de tarjetas numeradas. Cada tarjeta es un paso; las flechas indican el avance; la tarjeta azul marca el paso clave del flujo.", 10.5, False, False, MUTED, space_after=6)

    rows = [
        ("Círculo numerado", "Orden del paso dentro del flujo."),
        ("Tarjeta blanca", "Paso ordinario: una acción o una decisión."),
        ("Tarjeta azul con etiqueta CLAVE", "Paso que concentra el valor o el control del flujo."),
        ("Flecha", "Avance al siguiente paso; el flujo termina en el punto FIN."),
        ("Barra inferior", "Resultado global del flujo: el estado que queda al completarlo."),
        ("Encabezado superior derecho", "Actor y superficie o ruta principal del flujo."),
    ]
    add_small_table(doc, ["Elemento", "Significado"], rows, [7.0, 18.2], 9)

    add_h3(doc, "Convenciones del informe")
    add_bullets(doc, [
        "Los nombres de pantallas y rutas se tomaron del frontend real; no se inventaron etiquetas.",
        "La columna “Resultado” de cada tabla describe el estado que deja el paso, no una promesa abstracta.",
        "Las notas al pie de cada flujo explican límites, excepciones o dependencias de la API.",
        "Las operaciones marcadas “API” no tienen pantalla en el frontend; se incluyen porque forman parte del flujo funcional.",
    ])
    add_note(doc, "La lectura recomendada es: primero el diagrama para ubicar el recorrido; después la tabla para entender el detalle; al final, la nota para conocer el límite o la excepción.")


def add_flujo_comun(doc: Document):
    doc.add_page_break()
    add_h1(doc, "4. Flujo común de acceso")
    para(doc, "Antes de cualquier función, los cuatro actores pasan por el mismo embudo: login, token, identidad y rol. La diferencia está en la superficie a la que llegan.", 10.5, False, False, MUTED, space_after=4)

    add_h3(doc, "Qué ve cada actor al entrar")
    rows = [
        ("Superadmin", "/control/dashboard", "Cartera de instituciones, capacidades y métricas globales."),
        ("Administrador", "/dashboard", "Indicadores de la institución, alertas y actividad reciente."),
        ("Bodeguero", "/dashboard", "Stock de la sede, pedidos activos y alertas."),
        ("Solicitante", "/dashboard", "Disponibilidad, pedidos propios y alertas de su ámbito."),
    ]
    add_small_table(doc, ["Actor", "Ruta inicial", "Primer foco"], rows, [5.0, 6.4, 13.8], 9)
    add_note(doc, "El login es el mismo para todos; lo que cambia es la resolución del rol y la superficie que el guard habilita. El diagrama de la página siguiente muestra ese recorrido común.")
    add_flow_section(doc, "00-acceso-comun", 4, 1)


def add_matriz(doc: Document):
    doc.add_page_break()
    add_h1(doc, "9. Matriz de funciones por actor")
    para(doc, "La matriz resume qué puede hacer cada actor. “Sí” significa que la función está disponible en la interfaz; “API” significa que la operación existe en el backend pero no tiene pantalla; “Propio” significa que el actor solo opera sus propios pedidos y con restricciones de estado.", 9.5, False, False, MUTED, space_after=5)
    table = doc.add_table(rows=1, cols=5)
    set_col_widths(table, [8.2, 4.2, 4.2, 4.2, 4.2])
    for idx, header in enumerate(["Función", "Superadmin", "Administrador", "Bodeguero", "Solicitante"]):
        write_cell(table.rows[0].cells[idx], header, 8, True, WHITE, MONO_FONT)
    style_table(table, font_size=8)
    for idx, row_values in enumerate(MATRIX):
        row = table.add_row()
        for col, value in enumerate(row_values):
            write_cell(
                row.cells[col], value, 7.8,
                col == 0,
                ACCENT if value in ("Sí", "API") and col > 0 else (MUTED if value == "—" else INK),
                BODY_FONT,
                WD_ALIGN_PARAGRAPH.LEFT if col == 0 else WD_ALIGN_PARAGRAPH.CENTER,
            )
        if idx % 2 == 1:
            for cell in row.cells:
                shade_cell(cell, LIGHT_HEX)
    add_note(doc, "La matriz refleja la UI y la matriz de permisos de la API. No todos los “Sí” implican la misma amplitud: el Administrador ve toda la institución; el Bodeguero, su sede; el Solicitante, sus propios pedidos.")


def add_api_only(doc: Document):
    doc.add_page_break()
    add_h1(doc, "10. Funciones sin pantalla")
    para(doc, "Durante el recorrido aparecen operaciones que son parte del flujo funcional pero no tienen un botón o formulario en el frontend. Se documentan aquí para que el informe no prometa una interfaz que no existe.", 10.5, False, False, MUTED, space_after=6)
    add_small_table(doc, ["Operación", "Método / ruta", "Quién", "Por qué no está en la UI"], API_ONLY, [4.2, 7.8, 4.6, 8.6], 8.5)
    para(doc, "", size=4, space_after=6)
    add_note(doc, "Esto no es una omisión del informe: es un límite del producto en el estado documentado. La API sí ejecuta la operación y la matriz de permisos la protege.")


def add_trazabilidad(doc: Document):
    doc.add_page_break()
    add_h1(doc, "11. Trazabilidad de fuentes")
    para(doc, "Cada flujo se contrastó con las rutas, los roles y las evidencias del repositorio. Esta tabla permite volver de un diagrama a su fuente.", 10.5, False, False, MUTED, space_after=6)
    add_small_table(doc, ["Fuente", "Qué aporta", "Uso en este informe"], SOURCES, [8.2, 9.0, 8.0], 8.2)
    add_note(doc, "Las evidencias 012–021 se consultaron en su versión del repositorio; las capturas existentes no se reutilizaron porque el informe se apoya en diagramas de flujo.")


def add_cierre(doc: Document):
    doc.add_page_break()
    add_h1(doc, "12. Entregables y cierre")
    para(doc, "El entregable principal es este DOCX. Los diagramas viven en una carpeta separada para que puedan reutilizarse en presentaciones o en la revisión del proyecto.", 10.5, False, False, MUTED, space_after=6)
    add_small_table(doc, ["Archivo", "Formato", "Contenido"], DELIVERABLES, [10.0, 5.2, 10.0], 8.3)

    add_h3(doc, "Validación realizada")
    add_bullets(doc, [
        "12 HTML autocontenidos validados con `self_check.py`: 12/12 sin fallos.",
        "12 PNG exportados a 2400 × 1120 px (2x) con Edge headless.",
        "Informe generado en A4 horizontal y reabierto con python-docx para verificar estructura, tablas e imágenes.",
        "Rutas, roles y límites contrastados con `app.routes.ts`, `roles.ts` y `permisos.py`.",
    ])

    add_h3(doc, "Observaciones")
    para(doc, "El sistema cubre el ciclo completo de abastecimiento: el Solicitante pide, el Administrador decide y compra, el Bodeguero recibe y despacha, y el Superadmin gobierna el SaaS. La documentación separa lo que ya tiene interfaz de lo que hoy solo existe en la API, para que la revisión funcional sea honesta y accionable.", 10, False, False, MUTED, space_after=4)

    add_note(doc, "Trabajo realizado en la rama local `ricardo`. No se publicó en GitHub ni se modificó el código de producto; el cambio se limita a documentación y diagramas.")


def main():
    if not DIAGRAMS.exists():
        raise SystemExit(f"No existe la carpeta de diagramas: {DIAGRAMS}")
    for flow in FLOWS:
        png = DIAGRAMS / f"{flow['slug']}.png"
        if not png.exists():
            raise SystemExit(f"Falta el PNG: {png}")

    doc = configure_document()
    add_cover(doc)
    add_document_map(doc)
    add_propósito(doc)
    add_actores(doc)
    add_como_leer(doc)
    add_flujo_comun(doc)

    for actor in ACTORS:
        add_actor_intro(doc, actor)
        for sub, slug in enumerate(actor["flows"], start=1):
            add_flow_section(doc, slug, actor["num"], sub)

    add_matriz(doc)
    add_api_only(doc)
    add_trazabilidad(doc)
    add_cierre(doc)

    # Cierre limpio: sin párrafo vacío final gigante.
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc.save(OUTPUT)
    print(f"DOCX  {OUTPUT}")
    print(f"Tablas: {len(doc.tables)} · Imágenes: {len(doc.inline_shapes)} · Párrafos: {len(doc.paragraphs)}")


if __name__ == "__main__":
    main()
