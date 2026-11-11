#!/usr/bin/env python3
"""Genera los diagramas de flujo por actor de CompuStock ERP.

La salida es un HTML autocontenido por flujo. El PNG se obtiene después con
Edge headless a partir del mismo HTML (ver README.md de esta carpeta).
"""

from __future__ import annotations

import html
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent

INK = "#1e293b"
MUTED = "#475569"
SOFT = "#64748b"
RULE = "#cbd5e1"
PAPER = "#f8fafc"
ACCENT = "#2563eb"
ACCENT_TINT = "#eff6ff"
ACCENT_RULE = "#bfdbfe"

FLOWS = [
    {
        "slug": "00-acceso-comun",
        "actor": "Todos los actores",
        "scope": "Login Clerk · /auth/me",
        "eyebrow": "FLUJO TRANSVERSAL",
        "title": "Acceso y resolución de identidad",
        "subtitle": "Del login de Clerk a la superficie que corresponde a cada rol.",
        "focal": 4,
        "steps": [
            ("Abrir la aplicación", "La SPA de Angular carga en localhost:4200 y muestra el login.", "Login visible"),
            ("Iniciar sesión", "Correo y contraseña, o el código de prueba 424242 en Clerk.", "Sesión Clerk"),
            ("Adjuntar el token", "El interceptor agrega el token Bearer a cada llamada a la API.", "Peticiones autenticadas"),
            ("Resolver identidad", "GET /auth/me devuelve nombre, rol e institución efectiva.", "Identidad cargada"),
            ("Aplicar el rol", "Superadmin va a /control; los roles de negocio van a /dashboard.", "Ruta inicial"),
            ("Entrar a la superficie", "El menú muestra solo lo permitido; una ruta prohibida cae en /acceso-denegado.", "Sesión con alcance"),
        ],
        "result": "Cada actor entra a su superficie con identidad, rol e institución correctos.",
    },
    {
        "slug": "01-superadmin-gobierno-saas",
        "actor": "Superadmin",
        "scope": "Portal /control",
        "eyebrow": "SUPERADMIN · GOBIERNO SAAS",
        "title": "Instituciones y capacidades",
        "subtitle": "Administración global de instituciones, módulos y administradores.",
        "focal": 4,
        "steps": [
            ("Abrir el portal", "Entrar a /control; solo el rol Superadmin navega este portal.", "Portal de control"),
            ("Ver dashboard SaaS", "Instituciones activas, sedes, usuarios por rol y estado de versión.", "Panorama global"),
            ("Listar instituciones", "Buscar instituciones y revisar RUT, dirección y estado activo.", "Cartera visible"),
            ("Abrir una institución", "Acceder al detalle y a sus acciones de gobierno.", "Institución seleccionada"),
            ("Gestionar capacidades", "Activar o desactivar módulos; el cambio impacta rutas y API.", "Módulos vigentes"),
            ("Gestionar administradores", "Asignar o revocar Administradores; invitar o reenviar invitación.", "Administradores vigentes"),
        ],
        "result": "La institución queda gobernada con capacidades y administradores coherentes.",
    },
    {
        "slug": "02-superadmin-alta-institucion",
        "actor": "Superadmin",
        "scope": "Portal /control/alta",
        "eyebrow": "SUPERADMIN · APROVISIONAMIENTO",
        "title": "Alta de una institución",
        "subtitle": "Tenant, sede inicial y primer Administrador en un solo flujo.",
        "focal": 5,
        "steps": [
            ("Entrar a Alta", "Abrir /control/alta desde el portal de control.", "Formulario de alta"),
            ("Completar identidad", "Nombre, RUT, dirección y datos de contacto de la institución.", "Datos validados"),
            ("Definir sede inicial", "Nombre, dirección y código de la primera sede operativa.", "Sede inicial"),
            ("Designar Administrador", "Correo del primer Administrador; Clerk envía la invitación.", "Invitación preparada"),
            ("Elegir capacidades", "Marcar los módulos iniciales que tendrá el tenant.", "Módulos iniciales"),
            ("Confirmar el alta", "Se crea el esquema tenant y la topología; el Administrador queda invitado.", "Institución operativa"),
        ],
        "result": "La institución nace con su esquema, sede, Administrador y capacidades listas.",
    },
    {
        "slug": "03-administrador-administracion",
        "actor": "Administrador",
        "scope": "Tenant · /administracion",
        "eyebrow": "ADMINISTRADOR · ORGANIZACIÓN",
        "title": "Administración institucional",
        "subtitle": "Sedes, departamentos, usuarios y encargados de la institución.",
        "focal": 3,
        "steps": [
            ("Abrir Administración", "El menú aparece solo para el Administrador institucional.", "Panel administrativo"),
            ("Gestionar sedes", "Crear o editar sedes; una sede agrupa departamentos y stock.", "Sedes actualizadas"),
            ("Gestionar departamentos", "Asignar sede, definir bodega de despacho y estado activo.", "Departamentos ordenados"),
            ("Gestionar usuarios", "Altas, roles Bodeguero/Solicitante, sede y estado de la cuenta.", "Usuarios y accesos"),
            ("Asignar encargados", "Vincular uno o más encargados a cada departamento.", "Encargados asignados"),
            ("Verificar la estructura", "Revisar que sedes, departamentos y usuarios queden coherentes.", "Organización lista"),
        ],
        "result": "La estructura organizacional queda lista para operar inventario, pedidos y compras.",
    },
    {
        "slug": "04-administrador-inventario-catalogo",
        "actor": "Administrador",
        "scope": "Tenant · /inventario",
        "eyebrow": "ADMINISTRADOR · CATÁLOGO",
        "title": "Inventario y catálogo",
        "subtitle": "Existencias, detalle por producto y ciclo de vida del catálogo.",
        "focal": 3,
        "steps": [
            ("Abrir Inventario", "Ver existencias consolidadas y el desglose por sede.", "Stock visible"),
            ("Filtrar el alcance", "Sede, departamento, texto, categoría y solo stock crítico.", "Vista acotada"),
            ("Abrir el producto", "Saldo total, mínimo, estado, sedes y movimientos.", "Detalle completo"),
            ("Gestionar catálogo", "Crear o editar productos y categorías; aplicar baja o reactivación.", "Catálogo actualizado"),
            ("Registrar movimientos", "Entradas y salidas por sede; la API actualiza stock_sede.", "Saldo ajustado"),
            ("Revisar el historial", "Ver transiciones, actor, motivo y fecha de cada cambio.", "Trazabilidad"),
        ],
        "result": "El catálogo y el stock quedan confiables para decidir compras y despachos.",
    },
    {
        "slug": "05-administrador-compras",
        "actor": "Administrador",
        "scope": "Tenant · /compras",
        "eyebrow": "ADMINISTRADOR · COMPRAS",
        "title": "Compras y cobertura de pedidos",
        "subtitle": "De la necesidad neta a la orden de compra facturada.",
        "focal": 4,
        "steps": [
            ("Abrir Compras", "Listado de OC y estados: Borrador, Emitida, Facturada, Recibida y Cancelada.", "OC visibles"),
            ("Revisar necesidades", "Demanda por sede/producto, pedidos que la componen y sugerido neto.", "Necesidad calculada"),
            ("Crear la orden", "Sede destino, proveedor, ítems, cantidades y costo unitario.", "Borrador"),
            ("Emitir la OC", "El plan se congela, cubre pedidos y suma stock comprometido.", "OC emitida"),
            ("Registrar la factura", "Número, fecha, monto y observaciones; habilita la recepción.", "OC facturada"),
            ("Hacer seguimiento", "Ver pedidos cubiertos, faltantes, factura y recepción en bodega.", "Cobertura trazable"),
        ],
        "result": "La OC cubre la demanda, queda facturada y habilita la recepción del Bodeguero.",
    },
    {
        "slug": "06-administrador-pedidos",
        "actor": "Administrador",
        "scope": "Tenant · /tickets",
        "eyebrow": "ADMINISTRADOR · PEDIDOS",
        "title": "Pedidos y ciclo de vida",
        "subtitle": "Revisión, rechazo, anulación y edición de pedidos.",
        "focal": 4,
        "steps": [
            ("Abrir Pedidos", "Tablero Kanban por estado y filtros por prioridad o asunto.", "Tablero"),
            ("Abrir el detalle", "Ítems, justificación, solicitante, cobertura e historial.", "Contexto completo"),
            ("Revisar stock", "Comparar lo solicitado con stock disponible y OC asociadas.", "Viabilidad"),
            ("Avanzar o retroceder", "Mover el pedido entre Pendiente, En revisión y En curso.", "Estado actualizado"),
            ("Rechazar o anular", "Exigir motivo; el pedido pasa a Anulado y conserva historial.", "Cierre auditado"),
            ("Editar si está Pendiente", "Corregir asunto, prioridad o ítems antes de operar.", "Datos corregidos"),
        ],
        "result": "El pedido queda con un estado, un motivo y un historial que explican cada decisión.",
    },
    {
        "slug": "07-bodeguero-pedidos-despacho",
        "actor": "Bodeguero",
        "scope": "Tenant · /tickets",
        "eyebrow": "BODEGUERO · DESPACHO",
        "title": "Pedidos y preparación del despacho",
        "subtitle": "Operación del Kanban y llegada del pedido a bodega.",
        "focal": 4,
        "steps": [
            ("Abrir Pedidos", "Kanban de la institución; el Bodeguero ve su sede.", "Tablero operativo"),
            ("Filtrar y abrir", "Buscar por prioridad o asunto y abrir el detalle del pedido.", "Pedido seleccionado"),
            ("Revisar ítems y stock", "Cantidades solicitadas, entregadas, stock disponible y cobertura.", "Preparación"),
            ("Avanzar o retroceder", "Pendiente → En revisión → En curso; rechazar con motivo si no procede.", "Estado listo"),
            ("Preparar el despacho", "En En curso el pedido queda marcado como listo para despacho.", "Listo para despachar"),
            ("Ejecutar el despacho", "La operación de despacho rebaja stock y cierra el pedido.", "Pedido cerrado"),
        ],
        "result": "El pedido se despacha con stock rebajado y el solicitante ve el cierre.",
    },
    {
        "slug": "08-bodeguero-inventario",
        "actor": "Bodeguero",
        "scope": "Tenant · /inventario",
        "eyebrow": "BODEGUERO · INVENTARIO",
        "title": "Inventario operativo y alertas",
        "subtitle": "Consulta de existencias de la sede y productos críticos.",
        "focal": 5,
        "steps": [
            ("Abrir Dashboard", "Ver unidades en stock, pedidos activos y alertas de la sede.", "Alertas"),
            ("Ir a Inventario", "Listado de insumos con existencias y desglose por sede.", "Stock de la sede"),
            ("Filtrar por departamento", "El Bodeguero no elige sede; el servidor la fija a la suya.", "Vista acotada"),
            ("Abrir el producto", "Saldo, mínimo, estado y sedes con existencia.", "Detalle"),
            ("Detectar el crítico", "Activar “Solo stock crítico” o leer la alerta del dashboard.", "Prioridad de compra"),
            ("Actualizar el saldo", "El stock cambia por despachos y recepciones, no por edición manual.", "Saldo consistente"),
        ],
        "result": "El Bodeguero conoce qué hay, qué falta y qué debe preparar o comprar.",
    },
    {
        "slug": "09-bodeguero-recepcion-compras",
        "actor": "Bodeguero",
        "scope": "Tenant · /compras/recepcion",
        "eyebrow": "BODEGUERO · RECEPCIÓN",
        "title": "Recepción de compras",
        "subtitle": "Ingreso de una OC facturada y desbloqueo de pedidos cubiertos.",
        "focal": 4,
        "steps": [
            ("Abrir Recepción", "Menú exclusivo del Bodeguero: /compras/recepcion.", "Panel de recepción"),
            ("Ver OC facturadas", "Solo órdenes Facturada de su sede, con proveedor y factura.", "OC por recibir"),
            ("Verificar la factura", "Número, fecha, monto e ítems a recibir.", "Datos contrastados"),
            ("Confirmar recepción", "Modal irreversible: ingresa cantidades y pasa la OC a Recibida.", "OC recibida"),
            ("Incrementar stock", "Cada ítem suma a stock_sede de la sede destino.", "Stock actualizado"),
            ("Desbloquear pedidos", "Los pedidos cubiertos quedan listos para despacho.", "Pedidos habilitados"),
        ],
        "result": "La OC queda recibida, el stock sube y los pedidos cubiertos quedan operables.",
    },
    {
        "slug": "10-solicitante-crear-pedido",
        "actor": "Solicitante",
        "scope": "Tenant · /tickets",
        "eyebrow": "SOLICITANTE · ALTA",
        "title": "Crear un pedido de requerimiento",
        "subtitle": "Consulta de disponibilidad y alta del pedido para el departamento.",
        "focal": 5,
        "steps": [
            ("Abrir Dashboard", "Resumen de stock, pedidos activos y alertas de su ámbito.", "Contexto"),
            ("Consultar Inventario", "Ver productos y disponibilidad; sin filtros de sede.", "Catálogo visible"),
            ("Abrir el producto", "Saldo, mínimo, estado y sede con existencia.", "Decisión de pedido"),
            ("Crear el pedido", "Abrir “+ Crear pedido” en Pedidos.", "Modal abierto"),
            ("Completar el formulario", "Prioridad, asunto, descripción e ítems con producto y cantidad.", "Pedido armado"),
            ("Confirmar el alta", "Nace en Pendiente; no descuenta stock y queda a nombre de la sesión.", "Pedido creado"),
        ],
        "result": "El pedido queda justificado, en Pendiente y visible para el solicitante y la bodega.",
    },
    {
        "slug": "11-solicitante-seguimiento",
        "actor": "Solicitante",
        "scope": "Tenant · /tickets/:id",
        "eyebrow": "SOLICITANTE · SEGUIMIENTO",
        "title": "Seguimiento y modificación del pedido",
        "subtitle": "Qué puede hacer el solicitante según el estado de su pedido.",
        "focal": 3,
        "steps": [
            ("Abrir Pedidos", "Ver sus pedidos en el Kanban y filtrar por prioridad o asunto.", "Pedidos propios"),
            ("Abrir el detalle", "Estado, ítems, cantidades entregadas, cobertura e historial.", "Estado real"),
            ("Leer el estado", "Pendiente, En revisión, En curso, Cerrado o Anulado.", "Expectativa"),
            ("Editar si está Pendiente", "Corregir asunto, prioridad, ítems o cantidades.", "Pedido actualizado"),
            ("Anular si corresponde", "Solo en Pendiente o En revisión y con motivo; queda Anulado.", "Cierre con motivo"),
            ("Consultar el historial", "Ver cada transición, actor y fecha; no se borra.", "Trazabilidad"),
        ],
        "result": "El solicitante sigue su pedido y solo lo modifica mientras el estado lo permite.",
    },
]

NOTES = {
    "00-acceso-comun": "El guard decide la navegación; la autorización real la valida la API en cada petición.",
    "01-superadmin-gobierno-saas": "El catálogo global de proveedores del Superadmin se opera por API; no tiene pantalla en el frontend.",
    "02-superadmin-alta-institucion": "Si el correo ya existe en Clerk, el alta vincula la identidad sin generar una invitación nueva.",
    "03-administrador-administracion": "El Administrador solo puede asignar roles Bodeguero o Solicitante; las rutas y la API validan la matriz.",
    "04-administrador-inventario-catalogo": "Una baja exige saldo cero; no se puede dejar un producto activo bajo una categoría inactiva. Los movimientos se registran por API: POST /inventario/movimientos.",
    "05-administrador-compras": "Una OC pertenece a una sola sede. La cancelación exige motivo y no revierte stock ni facturas.",
    "06-administrador-pedidos": "El Administrador puede editar, rechazar, anular y operar estados. En En curso, el cierre está reservado al despacho.",
    "07-bodeguero-pedidos-despacho": "La pantalla de detalle no expone el botón de despacho: la operación En curso → Cerrado se ejecuta por API. El Bodeguero no edita ni anula pedidos.",
    "08-bodeguero-inventario": "La nota de la vista recuerda que el stock es compartido por la sede: elegir departamento filtra productos, no divide el saldo.",
    "09-bodeguero-recepcion-compras": "Si no hay OC facturadas en su sede, el panel muestra el vacío; no permite elegir otra sede.",
    "10-solicitante-crear-pedido": "El solicitante no elige autor ni estado inicial: ambos salen de la sesión y del flujo.",
    "11-solicitante-seguimiento": "El Solicitante no avanza estados ni despacha. En En curso o Cerrado ya no puede editar ni anular.",
}


def esc(value: str) -> str:
    return html.escape(value, quote=True)


def wrap_lines(value: str, width: int, max_lines: int) -> list[str]:
    lines = textwrap.wrap(value, width=width, break_long_words=False, break_on_hyphens=False)
    if len(lines) <= max_lines:
        return lines
    # Recorta con elipsis en la última línea permitida.
    lines = lines[:max_lines]
    last = lines[-1]
    if len(last) >= width - 1:
        last = last[: width - 2].rstrip()
    lines[-1] = last + "…"
    return lines


def svg_text(lines: list[str], x: float, y: float, line_height: float, **attrs) -> str:
    attrs_text = " ".join(f'{k}="{esc(str(v))}"' for k, v in attrs.items())
    spans = "".join(
        f'<tspan x="{x}" dy="{0 if i == 0 else line_height}">{esc(line)}</tspan>'
        for i, line in enumerate(lines)
    )
    return f'<text x="{x}" y="{y}" {attrs_text}>{spans}</text>'


def build_svg(flow: dict) -> str:
    slug = flow["slug"]
    steps = flow["steps"]
    n = len(steps)
    gap = 20
    flow_w = 1060
    card_w = (flow_w - (n - 1) * gap) / n
    x_start = (1200 - flow_w) / 2
    card_y = 160
    card_h = 270
    card_center = card_y + card_h / 2
    focal = flow["focal"]
    title_wrap = max(14, int(card_w / 10.3))
    body_wrap = max(18, int(card_w / 8.0))
    result_wrap = max(20, int(card_w / 7.2))

    parts: list[str] = []
    # Fondo
    parts.append(f'<rect x="0" y="0" width="1200" height="560" fill="{PAPER}"/>')
    parts.append(f'<rect x="0" y="0" width="1200" height="560" fill="url(#dots-{slug})" opacity="0.55"/>')
    parts.append(f'<line x1="70" y1="128" x2="1130" y2="128" stroke="#e2e8f0" stroke-width="1"/>')

    # Cabecera
    parts.append(
        f'<text x="70" y="36" font-family="Geist Mono, monospace" font-size="11" '
        f'font-weight="500" letter-spacing="1.3" fill="{ACCENT}">{esc(flow["eyebrow"])}</text>'
    )
    parts.append(
        f'<text x="70" y="78" font-family="Instrument Serif, serif" font-size="34" '
        f'fill="{INK}">{esc(flow["title"])}</text>'
    )
    parts.append(
        f'<text x="70" y="104" font-family="Geist, sans-serif" font-size="14" '
        f'fill="{MUTED}">{esc(flow["subtitle"])}</text>'
    )
    parts.append(
        f'<text x="1130" y="34" text-anchor="end" font-family="Geist Mono, monospace" '
        f'font-size="9" letter-spacing="1.2" fill="{SOFT}">ACTOR</text>'
    )
    parts.append(
        f'<text x="1130" y="57" text-anchor="end" font-family="Geist, sans-serif" '
        f'font-size="16" font-weight="600" fill="{INK}">{esc(flow["actor"])}</text>'
    )
    parts.append(
        f'<text x="1130" y="75" text-anchor="end" font-family="Geist Mono, monospace" '
        f'font-size="10" fill="{SOFT}">{esc(flow["scope"])}</text>'
    )

    # Conectores (antes de las cajas)
    for i in range(n - 1):
        x1 = x_start + (i + 1) * card_w + i * gap
        x2 = x1 + gap
        parts.append(
            f'<line x1="{x1 + 3:.1f}" y1="{card_center:.1f}" x2="{x2 - 3:.1f}" '
            f'y2="{card_center:.1f}" stroke="{MUTED}" stroke-width="1.4" marker-end="url(#arrow-{slug})"/>'
        )
    start_x = x_start - 24
    end_x = x_start + flow_w + 24
    parts.append(
        f'<line x1="{start_x + 7:.1f}" y1="{card_center:.1f}" x2="{x_start - 4:.1f}" '
        f'y2="{card_center:.1f}" stroke="{MUTED}" stroke-width="1.2" marker-end="url(#arrow-{slug})"/>'
    )
    parts.append(
        f'<line x1="{x_start + flow_w + 4:.1f}" y1="{card_center:.1f}" x2="{end_x - 6:.1f}" '
        f'y2="{card_center:.1f}" stroke="{MUTED}" stroke-width="1.2" marker-end="url(#arrow-{slug})"/>'
    )
    parts.append(f'<circle cx="{start_x}" cy="{card_center}" r="5" fill="{MUTED}"/>')
    parts.append(f'<circle cx="{end_x}" cy="{card_center}" r="5" fill="{MUTED}"/>')
    parts.append(
        f'<text x="{start_x}" y="{card_center + 24}" text-anchor="middle" '
        f'font-family="Geist Mono, monospace" font-size="8" letter-spacing="0.8" fill="{SOFT}">INICIO</text>'
    )
    parts.append(
        f'<text x="{end_x}" y="{card_center + 24}" text-anchor="middle" '
        f'font-family="Geist Mono, monospace" font-size="8" letter-spacing="0.8" fill="{SOFT}">FIN</text>'
    )

    # Tarjetas
    for i, (title, body, result) in enumerate(steps):
        x = x_start + i * (card_w + gap)
        is_focal = i == focal
        fill = ACCENT_TINT if is_focal else "#ffffff"
        stroke = ACCENT if is_focal else RULE
        stroke_w = 2 if is_focal else 1
        parts.append(
            f'<rect x="{x:.1f}" y="{card_y}" width="{card_w:.1f}" height="{card_h}" '
            f'rx="8" fill="{fill}" stroke="{stroke}" stroke-width="{stroke_w}"/>'
        )
        # Número
        parts.append(
            f'<circle cx="{x + 22:.1f}" cy="{card_y + 24}" r="12" '
            f'fill="{ACCENT if is_focal else INK}"/>'
        )
        parts.append(
            f'<text x="{x + 22:.1f}" y="{card_y + 29}" text-anchor="middle" '
            f'font-family="Geist, sans-serif" font-size="12" font-weight="600" fill="#ffffff">{i + 1}</text>'
        )
        if is_focal:
            parts.append(
                f'<rect x="{x + card_w - 56:.1f}" y="{card_y + 12}" width="44" height="16" '
                f'rx="2" fill="#dbeafe"/>'
            )
            parts.append(
                f'<text x="{x + card_w - 34:.1f}" y="{card_y + 23}" text-anchor="middle" '
                f'font-family="Geist Mono, monospace" font-size="8" font-weight="600" '
                f'letter-spacing="0.8" fill="{ACCENT}">CLAVE</text>'
            )

        tx = x + 15
        title_lines = wrap_lines(title, title_wrap, 2)
        parts.append(
            svg_text(
                title_lines,
                tx,
                card_y + 57,
                20,
                **{
                    "font-family": "Geist, sans-serif",
                    "font-size": "16.5",
                    "font-weight": "600",
                    "fill": INK,
                },
            )
        )
        body_lines = wrap_lines(body, body_wrap, 5)
        parts.append(
            svg_text(
                body_lines,
                tx,
                card_y + 106,
                17.5,
                **{
                    "font-family": "Geist, sans-serif",
                    "font-size": "13.5",
                    "fill": MUTED,
                },
            )
        )
        # Resultado
        parts.append(
            f'<line x1="{tx}" y1="{card_y + 210}" x2="{x + card_w - 15:.1f}" '
            f'y2="{card_y + 210}" stroke="#e2e8f0" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{tx}" y="{card_y + 226}" font-family="Geist Mono, monospace" '
            f'font-size="8.5" letter-spacing="1" fill="{SOFT}">RESULTADO</text>'
        )
        result_lines = wrap_lines(result, result_wrap, 2)
        parts.append(
            svg_text(
                result_lines,
                tx,
                card_y + 244,
                14,
                **{
                    "font-family": "Geist, sans-serif",
                    "font-size": "11.5",
                    "font-weight": "500",
                    "fill": ACCENT if is_focal else INK,
                },
            )
        )

    # Resultado global
    parts.append(
        f'<rect x="70" y="470" width="1060" height="56" rx="6" '
        f'fill="#eff6ff" stroke="{ACCENT_RULE}" stroke-width="1"/>'
    )
    parts.append(f'<rect x="70" y="470" width="4" height="56" rx="2" fill="{ACCENT}"/>')
    parts.append(
        f'<text x="88" y="491" font-family="Geist Mono, monospace" font-size="9" '
        f'font-weight="500" letter-spacing="1.2" fill="{ACCENT}">RESULTADO DEL FLUJO</text>'
    )
    parts.append(
        f'<text x="88" y="511" font-family="Geist, sans-serif" font-size="13" '
        f'fill="{INK}">{esc(flow["result"])}</text>'
    )
    parts.append(
        f'<text x="70" y="548" font-family="Geist Mono, monospace" font-size="8.5" '
        f'fill="#94a3b8">CompuStock ERP · flujos por actor · rama ricardo · noviembre 2026</text>'
    )
    parts.append(
        f'<text x="1130" y="548" text-anchor="end" font-family="Geist Mono, monospace" '
        f'font-size="8.5" fill="#94a3b8">→ avance del flujo · tarjeta azul = paso clave</text>'
    )

    return "".join(parts)


def build_html(flow: dict) -> str:
    slug = flow["slug"]
    title_id = f"flujo-{slug}-title"
    desc_id = f"flujo-{slug}-desc"
    note = NOTES.get(slug, "")
    note_html = (
        f'<p class="nota"><strong>Nota.</strong> {esc(note)}</p>' if note else ""
    )
    desc = (
        f"Diagrama de flujo del actor {flow['actor']}: {flow['title']}. "
        f"Pasos: " + "; ".join(step[0] for step in flow["steps"]) + "."
    )
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{esc(flow["title"])} · {esc(flow["actor"])} | CompuStock</title>
  <link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Geist:wght@400;500;600;700&family=Geist+Mono:wght@400;500;600&display=swap" rel="stylesheet">
  <style>
    *, *::before, *::after {{ box-sizing: border-box; }}
    html, body {{ margin: 0; padding: 0; background: {PAPER}; }}
    body {{ font-family: 'Geist', system-ui, sans-serif; color: {INK}; }}
    .viewport {{ width: 100%; overflow-x: auto; }}
    .canvas {{ width: 1200px; min-width: 1200px; background: {PAPER}; }}
    svg {{ display: block; width: 1200px; height: 560px; }}
    .nota {{
      width: 1200px; margin: 0; padding: 14px 70px 22px; color: {MUTED};
      font-size: 12px; line-height: 1.5; border-top: 1px solid #e2e8f0;
    }}
    .nota strong {{ color: {INK}; }}
    @media print {{ .nota {{ display: none; }} }}
  </style>
</head>
<body>
  <div class="viewport">
    <div class="canvas">
      <svg viewBox="0 0 1200 560" role="img" aria-labelledby="{title_id} {desc_id}">
        <title id="{title_id}">{esc(flow["title"])} · {esc(flow["actor"])}</title>
        <desc id="{desc_id}">{esc(desc)}</desc>
        <defs>
          <pattern id="dots-{slug}" width="22" height="22" patternUnits="userSpaceOnUse">
            <circle cx="11" cy="11" r="0.8" fill="{INK}" opacity="0.10"/>
          </pattern>
          <marker id="arrow-{slug}" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">
            <polygon points="0 0, 8 3, 0 6" fill="{MUTED}"/>
          </marker>
        </defs>
        {build_svg(flow)}
      </svg>
      {note_html}
    </div>
  </div>
</body>
</html>
"""


def main() -> None:
    for flow in FLOWS:
        path = ROOT / f"{flow['slug']}.html"
        path.write_text(build_html(flow), encoding="utf-8")
        print(f"HTML  {path.name}")
    print(f"\n{len(FLOWS)} diagramas generados en {ROOT}")


if __name__ == "__main__":
    main()
