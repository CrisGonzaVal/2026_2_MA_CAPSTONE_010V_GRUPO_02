"""Regresiones SQLite de la Feature 026 (salud del esquema)."""

from sqlalchemy import CheckConstraint, Index

from app.db.database import Base
from app.models import BaseControl, MovimientoInventario
from app.schemas.dashboard_schema import MovimientoDashboardRespuesta
from app.schemas.inventario_schema import (
    MovimientoCrear,
    MovimientoInventarioRespuesta,
)


def test_orm_retiro_inventario_y_movimiento_por_sede():
    assert "inventario" not in Base.metadata.tables
    assert MovimientoInventario.stock_sede_id.property.columns[0].nullable is False


def test_indices_y_checks_de_la_feature_026_estan_declarados():
    nombres = {
        indice.name
        for metadata in (Base.metadata, BaseControl.metadata)
        for tabla in metadata.tables.values()
        for indice in tabla.indexes
    }
    esperados = {
        "stock_sede_producto_sede_idx",
        "movimiento_stock_sede_fecha_idx",
        "movimiento_fecha_idx",
        "ticket_sede_estado_fecha_idx",
        "ticket_usuario_fecha_idx",
        "detalle_ticket_ticket_idx",
        "detalle_ticket_producto_idx",
        "historial_ticket_ticket_fecha_idx",
        "historial_producto_producto_fecha_idx",
        "historial_categoria_categoria_fecha_idx",
        "usuario_departamento_idx",
        "departamento_sede_idx",
        "producto_categoria_idx",
        "orden_compra_institucion_fecha_idx",
        "orden_compra_sede_estado_fecha_idx",
        "usuario_correo_normalizado_uk",
        "proveedor_rut_normalizado_uk",
        "sede_nombre_institucion_uk",
        "departamento_nombre_institucion_uk",
        "categoria_nombre_institucion_uk",
        "historial_transicion_ticket_creacion_uk",
    }
    assert esperados <= nombres

    checks = {
        restriccion.name
        for metadata in (Base.metadata, BaseControl.metadata)
        for tabla in metadata.tables.values()
        for restriccion in tabla.constraints
        if isinstance(restriccion, CheckConstraint)
    }
    assert {
        "movimiento_tipo_ck",
        "detalle_cantidad_entregada_tope_ck",
        "usuario_correo_canonico_ck",
        "proveedor_rut_canonico_ck",
    } <= checks


def test_dtos_no_exponen_campos_legados():
    assert "inventario_id" not in MovimientoCrear.model_fields
    assert "inventario_id" not in MovimientoInventarioRespuesta.model_fields
    assert "inventario_id" not in MovimientoDashboardRespuesta.model_fields
    assert "departamento_nombre" not in MovimientoDashboardRespuesta.model_fields
    assert "ubicacion" not in MovimientoDashboardRespuesta.model_fields
