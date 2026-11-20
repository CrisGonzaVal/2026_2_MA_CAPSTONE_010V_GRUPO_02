from sqlalchemy import (
    TIMESTAMP,
    CheckConstraint,
    Column,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

# Feature 026 (D-5): la tabla `inventario` desaparecio. El unico saldo vigente es
# `stock_sede`, y todo movimiento apunta a el por `stock_sede_id` obligatorio.
# Los indices de bitacora se declaran al final del modulo para conservar la
# paridad con el DDL de `database/01_esquema.sql`.


class MovimientoInventario(Base):
    __tablename__ = "movimiento_inventario"
    __table_args__ = (
        CheckConstraint(
            "tipo_movimiento IN ('ENTRADA', 'SALIDA')",
            name="movimiento_tipo_ck",
        ),
    )

    movimiento_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    tipo_movimiento = Column(String(20), nullable=False)
    cantidad = Column(Integer, nullable=False)
    fecha_movimiento = Column(TIMESTAMP, nullable=False, server_default=func.current_timestamp())
    observacion = Column(String(250))
    #: Referencia de auditoria al saldo por sede (Feature 011, spec D-2). Desde la
    #: Feature 026 es obligatoria: no existe el destino legado por inventario.
    stock_sede_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("stock_sede.stock_sede_id"), nullable=False
    )

    stock_sede = relationship(
        "StockSede",
        back_populates="movimientos",
        primaryjoin="MovimientoInventario.stock_sede_id == StockSede.stock_sede_id",
        foreign_keys="MovimientoInventario.stock_sede_id",
    )


Index(
    "movimiento_stock_sede_fecha_idx",
    MovimientoInventario.stock_sede_id,
    MovimientoInventario.fecha_movimiento.desc(),
    MovimientoInventario.movimiento_id.desc(),
)
Index(
    "movimiento_fecha_idx",
    MovimientoInventario.fecha_movimiento.desc(),
    MovimientoInventario.movimiento_id.desc(),
)
