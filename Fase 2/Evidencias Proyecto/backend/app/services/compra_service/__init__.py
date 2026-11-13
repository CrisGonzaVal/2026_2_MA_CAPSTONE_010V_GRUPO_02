"""Servicio del reabastecimiento externo y compras (Feature 020).

Fachada del paquete (Feature 023): conserva la ruta de import
`from app.services import compra_service` y reexporta la API que consumen los
endpoints, `ticket_service` y los tests. La implementacion vive en modulos
cohesivos por caso de uso.
"""

from __future__ import annotations

from ._comun import SimulacionTicketProducto, orden_a_respuesta
from .cobertura import calcular_cobertura_tickets, previsualizar_cobertura
from .necesidades import (
    _simular_claves,
    institucion_de_compras,
    listar_necesidades_reabastecimiento,
)
from .ordenes import (
    actualizar_orden_compra,
    cancelar_orden_compra,
    crear_orden_compra,
    emitir_orden_compra,
    listar_ordenes_compra,
    registrar_o_editar_factura,
)
from .proveedores import crear_proveedor, listar_proveedores
from .recepcion import recepcionar_orden_compra

__all__ = [
    "SimulacionTicketProducto",
    "_simular_claves",
    "actualizar_orden_compra",
    "calcular_cobertura_tickets",
    "cancelar_orden_compra",
    "crear_orden_compra",
    "crear_proveedor",
    "emitir_orden_compra",
    "institucion_de_compras",
    "listar_necesidades_reabastecimiento",
    "listar_ordenes_compra",
    "listar_proveedores",
    "orden_a_respuesta",
    "previsualizar_cobertura",
    "recepcionar_orden_compra",
    "registrar_o_editar_factura",
]
