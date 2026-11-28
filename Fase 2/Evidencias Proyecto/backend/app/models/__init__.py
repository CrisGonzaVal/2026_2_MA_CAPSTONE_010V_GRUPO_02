"""Modelos SQLAlchemy del dominio, agrupados por modulo funcional.

Re-exporta los modelos para que `from app.models import Ticket` siga siendo
valido, igual que cuando vivian todos en `models.py`. El re-export tambien
garantiza que SQLAlchemy los registre todos antes de configurar los mappers, y que
`Base.metadata` (DDL por esquema, `schema_translate_map`) vea las entidades de la
Feature 011 (`Sede`, `StockSede`). La tabla puente auxiliar se retiro con la
enmienda 27/Nov/2026 de la 012.
"""

from app.db.database import Base
from app.models.compra import (
    DetalleOrdenCompra,
    FacturaCompra,
    OrdenCompra,
    OrdenCompraTicket,
    Proveedor,
)
from app.models.control import (
    ESTADOS_INVITACION,
    TIPOS_REGISTRO_MOTIVO,
    MapaUsuarioEsquema,
    RegistroMotivoConstancia,
    VersionEsquema,
)
from app.models.control_canonico import (
    CAPACIDADES,
    BaseControl,
    FuncionInstitucion,
    InstitucionControl,
    ProveedorControl,
)
from app.models.institucion import Departamento, Institucion
from app.models.inventario import MovimientoInventario
from app.models.producto import (
    Categoria,
    HistorialTransicionCategoria,
    HistorialTransicionProducto,
    Producto,
)
from app.models.rol import Rol
from app.models.sede import Sede, StockSede
from app.models.ticket import (
    DetalleTicket,
    EstadoTicket,
    HistorialTransicionTicket,
    Prioridad,
    Ticket,
)
from app.models.usuario import Usuario

__all__ = [
    "CAPACIDADES",
    "Base",
    "BaseControl",
    "Categoria",
    "Departamento",
    "DetalleOrdenCompra",
    "DetalleTicket",
    "ESTADOS_INVITACION",
    "EstadoTicket",
    "FacturaCompra",
    "FuncionInstitucion",
    "HistorialTransicionCategoria",
    "HistorialTransicionProducto",
    "HistorialTransicionTicket",
    "Institucion",
    "InstitucionControl",
    "MapaUsuarioEsquema",
    "MovimientoInventario",
    "OrdenCompra",
    "OrdenCompraTicket",
    "Prioridad",
    "Producto",
    "Proveedor",
    "ProveedorControl",
    "RegistroMotivoConstancia",
    "Rol",
    "Sede",
    "StockSede",
    "TIPOS_REGISTRO_MOTIVO",
    "Ticket",
    "Usuario",
    "VersionEsquema",
]
