"""Modelos del reabastecimiento externo y compras (Features 020 y 021).

La Feature 020 agrega cuatro entidades de dominio: `Proveedor`, `OrdenCompra`,
`DetalleOrdenCompra` y `FacturaCompra`. La Feature 021 agrega una quinta,
`OrdenCompraTicket`, que congela que pedidos cubre cada OC al emitir. La
justificacion aprobada vive en `docs/spec/stack.md`, secciones
"Reabastecimiento externo y compras (Feature 020)" y "Cobertura automatica de
pedidos por ordenes de compra (Feature 021)", y el diseno en los `plan.md`
respectivos (020: DT-1, DT-3, DT-10 y DT-12; 021: DT-1, DT-2 y DT-5).

`Proveedor` es un caso especial: el catalogo **global** vive en
`control.proveedor` y lo mapea `ProveedorControl` (`app/models/control_canonico.py`).
La clase de este modulo es la **replica tenant** y conserva exactamente el mismo
`proveedor_id` entero, por eso su PK **no** tiene identidad propia y no hay FK
cross-schema. Las otras tres tablas son de negocio por esquema tenant; el DDL de
instalacion nueva las crea tambien en `control` por paridad estructural, pero
solo los tenants conservan datos.

El saldo operativo sigue siendo `stock_sede` (Feature 011): la recepcion de una
orden incrementa esa tabla y escribe `movimiento_inventario` en la misma
transaccion; este modulo no agrega columnas de stock.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

#: Estados del ciclo de vida de una orden de compra (AC-3/AC-12). El `CHECK` del
#: DDL y el servicio comparten este conjunto cerrado; la transicion valida la
#: hace el servicio, no la base.
ESTADOS_ORDEN_COMPRA: tuple[str, ...] = (
    "Borrador",
    "Emitida",
    "Facturada",
    "Recibida",
    "Cancelada",
)


class Proveedor(Base):
    """Replica tenant del catalogo global de proveedores (DT-1).

    Su PK **no** es identity: replica el `proveedor_id` de `control.proveedor`
    para que la correspondencia sea determinista y la orden de compra pueda usar
    una FK local ordinaria. El `UNIQUE (rut)` impide duplicados dentro del tenant;
    la unicidad global la garantiza `control.proveedor`.
    """

    __tablename__ = "proveedor"
    __table_args__ = (UniqueConstraint("rut", name="proveedor_rut_uk"),)

    proveedor_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=False
    )
    rut: Mapped[str] = mapped_column(String(20), nullable=False)
    razon_social: Mapped[str] = mapped_column(String(150), nullable=False)
    nombre_fantasia: Mapped[str | None] = mapped_column(String(100), nullable=True)
    giro: Mapped[str | None] = mapped_column(String(100), nullable=True)
    correo: Mapped[str | None] = mapped_column(String(100), nullable=True)
    telefono: Mapped[str | None] = mapped_column(String(20), nullable=True)
    #: Sin operacion de baja/reactivacion en la 020: nace activo.
    activo: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )

    ordenes = relationship(
        "OrdenCompra",
        back_populates="proveedor",
        primaryjoin="Proveedor.proveedor_id == OrdenCompra.proveedor_id",
        foreign_keys="OrdenCompra.proveedor_id",
    )
    facturas = relationship(
        "FacturaCompra",
        back_populates="proveedor",
        primaryjoin="Proveedor.proveedor_id == FacturaCompra.proveedor_id",
        foreign_keys="FacturaCompra.proveedor_id",
    )


class OrdenCompra(Base):
    """Orden de compra de una sede a un proveedor (AC-3).

    Nace en `Borrador` con `numero_oc` nulo. Al emitir se asigna
    `OC-{ANIO}-{orden_compra_id:06d}` y `fecha_emision` (DT-7); la recepcion sella
    `fecha_recepcion` y la cancelacion persiste motivo, fecha y actor (DT-12).
    El `total` lo calcula el servicio a partir de las lineas.
    """

    __tablename__ = "orden_compra"
    __table_args__ = (
        # Sede e institucion de la misma fila: una OC no puede comprar para una
        # sede ajena (mismo patron que stock_sede).
        ForeignKeyConstraint(
            ["institucion_id", "sede_id"],
            ["sede.institucion_id", "sede.sede_id"],
            name="orden_compra_sede_institucion_fk",
        ),
        UniqueConstraint("numero_oc", name="orden_compra_numero_uk"),
        # Destino de la FK compuesta de detalle_orden_compra.
        UniqueConstraint(
            "institucion_id", "orden_compra_id", name="orden_compra_institucion_uk"
        ),
        # Destino de la FK compuesta de factura_compra (DT-10).
        UniqueConstraint(
            "orden_compra_id", "proveedor_id", name="orden_compra_proveedor_uk"
        ),
        CheckConstraint(
            "estado IN ('Borrador', 'Emitida', 'Facturada', 'Recibida', 'Cancelada')",
            name="orden_compra_estado_ck",
        ),
        CheckConstraint("total >= 0", name="orden_compra_total_ck"),
    )

    orden_compra_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, index=True, autoincrement=True
    )
    #: Nulo mientras la orden esta en `Borrador`; se asigna al emitir.
    numero_oc: Mapped[str | None] = mapped_column(String(30), nullable=True)
    institucion_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("institucion.institucion_id"), nullable=False
    )
    sede_id: Mapped[int] = mapped_column(Integer, nullable=False)
    proveedor_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("proveedor.proveedor_id"), nullable=False
    )
    estado: Mapped[str] = mapped_column(
        String(20), nullable=False, default="Borrador"
    )
    total: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=0
    )
    #: Cancelacion (AC-12): el servicio exige motivo no vacio y persiste actor y
    #: fecha; la base solo los almacena.
    motivo_cancelacion: Mapped[str | None] = mapped_column(String(500), nullable=True)
    cancelado_por_usuario_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("usuario.usuario_id"), nullable=True
    )
    fecha_creacion: Mapped[datetime] = mapped_column(
        TIMESTAMP, nullable=False, server_default=func.current_timestamp()
    )
    fecha_emision: Mapped[datetime | None] = mapped_column(TIMESTAMP, nullable=True)
    fecha_recepcion: Mapped[datetime | None] = mapped_column(TIMESTAMP, nullable=True)
    fecha_cancelacion: Mapped[datetime | None] = mapped_column(TIMESTAMP, nullable=True)

    institucion = relationship(
        "Institucion",
        primaryjoin="OrdenCompra.institucion_id == Institucion.institucion_id",
        foreign_keys="OrdenCompra.institucion_id",
    )
    sede = relationship(
        "Sede",
        primaryjoin="OrdenCompra.sede_id == Sede.sede_id",
        foreign_keys="OrdenCompra.sede_id",
    )
    proveedor = relationship(
        "Proveedor",
        back_populates="ordenes",
        primaryjoin="OrdenCompra.proveedor_id == Proveedor.proveedor_id",
        foreign_keys="OrdenCompra.proveedor_id",
    )
    cancelado_por = relationship(
        "Usuario",
        primaryjoin="OrdenCompra.cancelado_por_usuario_id == Usuario.usuario_id",
        foreign_keys="OrdenCompra.cancelado_por_usuario_id",
    )
    detalles = relationship(
        "DetalleOrdenCompra",
        back_populates="orden",
        cascade="all, delete-orphan",
        order_by="DetalleOrdenCompra.detalle_orden_compra_id",
        primaryjoin="OrdenCompra.orden_compra_id == DetalleOrdenCompra.orden_compra_id",
        foreign_keys="DetalleOrdenCompra.orden_compra_id",
    )
    factura = relationship(
        "FacturaCompra",
        back_populates="orden",
        uselist=False,
        primaryjoin="OrdenCompra.orden_compra_id == FacturaCompra.orden_compra_id",
        foreign_keys="FacturaCompra.orden_compra_id",
    )
    #: Feature 021: plan congelado de cobertura. Se escribe solo al emitir y no
    #: se recalcula despues; el pedido no se borra en cascada.
    plan = relationship(
        "OrdenCompraTicket",
        back_populates="orden",
        cascade="all, delete-orphan",
        order_by="OrdenCompraTicket.orden_compra_ticket_id",
        primaryjoin=(
            "OrdenCompra.orden_compra_id == OrdenCompraTicket.orden_compra_id"
        ),
        foreign_keys="OrdenCompraTicket.orden_compra_id",
    )


class DetalleOrdenCompra(Base):
    """Linea de una orden de compra: producto y cantidad solicitada (AC-3).

    Las FK compuestas anclan la linea a la institucion de la orden y obligan a
    que el producto sea de esa misma institucion; `UNIQUE (orden_compra_id,
    producto_id)` impide repetir producto en la misma OC.
    """

    __tablename__ = "detalle_orden_compra"
    __table_args__ = (
        ForeignKeyConstraint(
            ["institucion_id", "orden_compra_id"],
            ["orden_compra.institucion_id", "orden_compra.orden_compra_id"],
            name="detalle_orden_compra_orden_fk",
        ),
        ForeignKeyConstraint(
            ["institucion_id", "producto_id"],
            ["producto.institucion_id", "producto.producto_id"],
            name="detalle_orden_compra_producto_fk",
        ),
        UniqueConstraint(
            "orden_compra_id",
            "producto_id",
            name="detalle_orden_compra_producto_uk",
        ),
        CheckConstraint(
            "cantidad_solicitada > 0", name="detalle_orden_compra_cantidad_ck"
        ),
        CheckConstraint(
            "precio_unitario >= 0", name="detalle_orden_compra_precio_ck"
        ),
    )

    detalle_orden_compra_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, index=True, autoincrement=True
    )
    orden_compra_id: Mapped[int] = mapped_column(Integer, nullable=False)
    institucion_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("institucion.institucion_id"), nullable=False
    )
    producto_id: Mapped[int] = mapped_column(Integer, nullable=False)
    cantidad_solicitada: Mapped[int] = mapped_column(Integer, nullable=False)
    precio_unitario: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=0
    )

    orden = relationship(
        "OrdenCompra",
        back_populates="detalles",
        primaryjoin=(
            "DetalleOrdenCompra.orden_compra_id == OrdenCompra.orden_compra_id"
        ),
        foreign_keys="DetalleOrdenCompra.orden_compra_id",
    )
    producto = relationship(
        "Producto",
        primaryjoin="DetalleOrdenCompra.producto_id == Producto.producto_id",
        foreign_keys="DetalleOrdenCompra.producto_id",
    )


class FacturaCompra(Base):
    """Factura del proveedor asociada a una orden (AC-5, DT-10).

    `proveedor_id` se porta explicitamente para declarar
    `UNIQUE (proveedor_id, numero_factura)` y para que la FK compuesta
    `(orden_compra_id, proveedor_id)` impida facturar una orden de otro proveedor.
    Una orden admite **una** factura: `UNIQUE (orden_compra_id)`.
    """

    __tablename__ = "factura_compra"
    __table_args__ = (
        ForeignKeyConstraint(
            ["orden_compra_id", "proveedor_id"],
            ["orden_compra.orden_compra_id", "orden_compra.proveedor_id"],
            name="factura_compra_orden_proveedor_fk",
        ),
        UniqueConstraint("orden_compra_id", name="factura_compra_orden_uk"),
        UniqueConstraint(
            "proveedor_id",
            "numero_factura",
            name="factura_compra_numero_proveedor_uk",
        ),
        CheckConstraint("monto_total > 0", name="factura_compra_monto_ck"),
    )

    factura_compra_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, index=True, autoincrement=True
    )
    orden_compra_id: Mapped[int] = mapped_column(Integer, nullable=False)
    proveedor_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("proveedor.proveedor_id"), nullable=False
    )
    numero_factura: Mapped[str] = mapped_column(String(50), nullable=False)
    fecha_factura: Mapped[date] = mapped_column(Date, nullable=False)
    monto_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    observaciones: Mapped[str | None] = mapped_column(String(500), nullable=True)
    fecha_registro: Mapped[datetime] = mapped_column(
        TIMESTAMP, nullable=False, server_default=func.current_timestamp()
    )

    orden = relationship(
        "OrdenCompra",
        back_populates="factura",
        primaryjoin="FacturaCompra.orden_compra_id == OrdenCompra.orden_compra_id",
        foreign_keys="FacturaCompra.orden_compra_id",
    )
    proveedor = relationship(
        "Proveedor",
        back_populates="facturas",
        primaryjoin="FacturaCompra.proveedor_id == Proveedor.proveedor_id",
        foreign_keys="FacturaCompra.proveedor_id",
    )


class OrdenCompraTicket(Base):
    """Plan congelado de cobertura de una OC sobre un pedido (Feature 021).

    Una fila por `(OC, pedido, producto)` con las unidades que la OC asigna a ese
    pedido al emitir y el faltante que deja. La clave unica impide duplicar el
    tramo; la FK a `detalle_orden_compra` impide asignar un producto que no esta
    en la OC y las FK compuestas con `institucion_id` impiden cruzar pedidos o
    productos de otra institucion. Varias OC pueden cubrir el mismo
    pedido/producto: el saldo vivo se calcula sumando las asignaciones activas.

    Es una tabla de negocio por esquema tenant; `control` la crea por paridad
    estructural y permanece vacia. No se recalcula al facturar, recepcionar o
    cancelar: es una foto del instante de la emision.
    """

    __tablename__ = "orden_compra_ticket"
    __table_args__ = (
        ForeignKeyConstraint(
            ["institucion_id", "orden_compra_id"],
            ["orden_compra.institucion_id", "orden_compra.orden_compra_id"],
            name="orden_compra_ticket_orden_institucion_fk",
        ),
        ForeignKeyConstraint(
            ["orden_compra_id", "producto_id"],
            [
                "detalle_orden_compra.orden_compra_id",
                "detalle_orden_compra.producto_id",
            ],
            name="orden_compra_ticket_orden_producto_fk",
        ),
        ForeignKeyConstraint(
            ["institucion_id", "ticket_id"],
            ["ticket.institucion_id", "ticket.ticket_id"],
            name="orden_compra_ticket_ticket_institucion_fk",
        ),
        ForeignKeyConstraint(
            ["institucion_id", "producto_id"],
            ["producto.institucion_id", "producto.producto_id"],
            name="orden_compra_ticket_producto_institucion_fk",
        ),
        UniqueConstraint(
            "orden_compra_id",
            "ticket_id",
            "producto_id",
            name="orden_compra_ticket_clave_uk",
        ),
        CheckConstraint(
            "cantidad_asignada > 0", name="orden_compra_ticket_asignada_ck"
        ),
        CheckConstraint(
            "cantidad_faltante >= 0", name="orden_compra_ticket_faltante_ck"
        ),
        Index(
            "orden_compra_ticket_ticket_idx", "institucion_id", "ticket_id"
        ),
        Index(
            "orden_compra_ticket_producto_idx", "institucion_id", "producto_id"
        ),
    )

    orden_compra_ticket_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, index=True, autoincrement=True
    )
    institucion_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("institucion.institucion_id"), nullable=False
    )
    orden_compra_id: Mapped[int] = mapped_column(Integer, nullable=False)
    ticket_id: Mapped[int] = mapped_column(Integer, nullable=False)
    producto_id: Mapped[int] = mapped_column(Integer, nullable=False)
    #: Unidades de la OC asignadas a este pedido; siempre > 0.
    cantidad_asignada: Mapped[int] = mapped_column(Integer, nullable=False)
    #: Foto del hueco que dejo esta OC, no un saldo vivo; siempre >= 0.
    cantidad_faltante: Mapped[int] = mapped_column(Integer, nullable=False)
    fecha_asignacion: Mapped[datetime] = mapped_column(
        TIMESTAMP, nullable=False, server_default=func.current_timestamp()
    )

    orden = relationship(
        "OrdenCompra",
        back_populates="plan",
        primaryjoin=(
            "OrdenCompraTicket.orden_compra_id == OrdenCompra.orden_compra_id"
        ),
        foreign_keys="OrdenCompraTicket.orden_compra_id",
    )
    ticket = relationship(
        "Ticket",
        primaryjoin="OrdenCompraTicket.ticket_id == Ticket.ticket_id",
        foreign_keys="OrdenCompraTicket.ticket_id",
    )
    producto = relationship(
        "Producto",
        primaryjoin="OrdenCompraTicket.producto_id == Producto.producto_id",
        foreign_keys="OrdenCompraTicket.producto_id",
    )
