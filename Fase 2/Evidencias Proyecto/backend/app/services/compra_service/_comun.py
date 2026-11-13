"""Helpers internos compartidos del servicio de compras (Feature 023).

Reune los errores HTTP, las constantes, el DTO de simulacion, la carga de una OC
y su proyeccion a respuesta. No importa modulos de flujo del paquete.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core import permisos
from app.models import (
    Categoria,
    DetalleOrdenCompra,
    OrdenCompra,
    Producto,
    Sede,
)
from app.schemas.compra_schema import (
    DetalleOrdenCompraCrear,
    OrdenCompraRespuesta,
    PlanOrdenCompraRespuesta,
)
from app.services import ambito_service
from app.services.auth_service import IdentidadAutenticada


_ADMINISTRADOR = permisos.RolConocido.ADMINISTRADOR.value
_ESTADO_EN_CURSO = "EnCurso"
_BORRADOR = "Borrador"
_EMITIDA = "Emitida"
_FACTURADA = "Facturada"
_RECIBIDA = "Recibida"
_CANCELADA = "Cancelada"


@dataclass
class SimulacionTicketProducto:
    """Resultado de la necesidad neta parcial para un `(pedido, producto)`.

    Es una lectura: no se persiste ni reserva. La usan las necesidades, el
    preview, la emision y la cadena del pedido (Feature 021, DT-2). `faltante`
    es el hueco **despues** de repartir la compra simulada; en la necesidad
    (sin compra nueva) coincide con `necesidad`.
    """

    ticket_id: int
    asunto: str
    solicitante_nombre: str | None
    solicitante_apellido: str | None
    solicitante_correo: str | None
    prioridad_nombre: str | None
    fecha_creacion: datetime
    solicitado: int
    plan_previo: int
    cubierto_stock: int
    entregado: int
    necesidad: int
    asignada: int
    faltante: int
    cobertura: str


def _conflicto(detalle: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detalle)


def _no_encontrado(detalle: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detalle)


def _no_procesable(detalle: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detalle
    )


def _institucion_del_actor(
    db: Session, identidad: IdentidadAutenticada | None
) -> str:
    """Institucion obligatoria del actor de compras (Administrador)."""
    institucion_id = ambito_service.alcance_institucional(db, identidad)
    if institucion_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="La operacion de compras requiere un tenant de negocio",
        )
    return institucion_id


def _es_postgres(db: Session) -> bool:
    return db.get_bind().dialect.name == "postgresql"


def _confirmar(db: Session, detalle: str) -> None:
    """Commit con traduccion de una violacion de unicidad a 409."""
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise _conflicto(detalle) from exc


def _sede_valida(db: Session, sede_id: int, institucion_id: str) -> Sede:
    sede = db.get(Sede, sede_id)
    if sede is None or sede.institucion_id != institucion_id:
        raise _no_encontrado("Sede no encontrada")
    return sede


def _producto_activo(
    db: Session, producto_id: int, institucion_id: str
) -> Producto:
    """Producto de la institucion y operativo (producto y categoria activos)."""
    producto = db.execute(
        select(Producto)
        .options(joinedload(Producto.categoria))
        .where(Producto.producto_id == producto_id)
    ).scalar_one_or_none()
    if producto is None or producto.institucion_id != institucion_id:
        raise _no_encontrado("Producto no encontrado")
    categoria = producto.categoria or db.get(Categoria, producto.categoria_id)
    if not producto.activo or categoria is None or not categoria.activo:
        raise _conflicto(
            f"El producto {producto_id} esta inactivo y no admite compras"
        )
    return producto


def _items_validados(
    db: Session,
    items: Sequence[DetalleOrdenCompraCrear],
    institucion_id: str,
) -> list[DetalleOrdenCompraCrear]:
    if not items:
        raise _no_procesable("La orden debe contener al menos un item")
    vistos: set[int] = set()
    for item in items:
        if item.producto_id in vistos:
            raise _conflicto(
                f"El producto {item.producto_id} esta repetido en la orden"
            )
        vistos.add(item.producto_id)
        _producto_activo(db, item.producto_id, institucion_id)
    return list(items)


def _opciones_orden() -> tuple:
    """Opciones de carga de una OC con proveedor, sede, factura, detalles y plan."""
    return (
        joinedload(OrdenCompra.proveedor),
        joinedload(OrdenCompra.sede),
        joinedload(OrdenCompra.factura),
        selectinload(OrdenCompra.detalles).joinedload(
            DetalleOrdenCompra.producto
        ),
        selectinload(OrdenCompra.plan),
    )


def _cargar_orden(
    db: Session, orden_id: int, institucion_id: str | None
) -> OrdenCompra:
    orden = db.execute(
        select(OrdenCompra)
        .options(*_opciones_orden())
        .where(OrdenCompra.orden_compra_id == orden_id)
    ).unique().scalar_one_or_none()
    if orden is None or (
        institucion_id is not None
        and orden.institucion_id != institucion_id
    ):
        raise _no_encontrado("Orden de compra no encontrada")
    return orden


def orden_a_respuesta(orden: OrdenCompra) -> OrdenCompraRespuesta:
    """Proyeccion de una OC con su plan resuelto (Feature 021, DT-8).

    `OrdenCompraRespuesta.model_validate` proyecta columnas y relaciones, pero
    el resumen del pedido y el nombre del producto no son columnas de
    `orden_compra_ticket`; se resuelven aqui para no duplicar la logica en cada
    endpoint. El llamador debe mantener la sesion abierta (carga perezosa).
    """
    respuesta = OrdenCompraRespuesta.model_validate(orden)
    respuesta.plan = [
        PlanOrdenCompraRespuesta(
            orden_compra_ticket_id=fila.orden_compra_ticket_id,
            orden_compra_id=fila.orden_compra_id,
            ticket_id=fila.ticket_id,
            producto_id=fila.producto_id,
            cantidad_asignada=fila.cantidad_asignada,
            cantidad_faltante=fila.cantidad_faltante,
            fecha_asignacion=fila.fecha_asignacion,
            asunto=fila.ticket.asunto if fila.ticket else None,
            estado_nombre=(
                fila.ticket.estado.nombre
                if fila.ticket and fila.ticket.estado
                else None
            ),
            prioridad_nombre=(
                fila.ticket.prioridad.nombre
                if fila.ticket and fila.ticket.prioridad
                else None
            ),
            solicitante_nombre=(
                fila.ticket.usuario.nombre
                if fila.ticket and fila.ticket.usuario
                else None
            ),
            solicitante_apellido=(
                fila.ticket.usuario.apellido
                if fila.ticket and fila.ticket.usuario
                else None
            ),
            fecha_creacion=(
                fila.ticket.fecha_creacion if fila.ticket else None
            ),
            producto_nombre=fila.producto.nombre if fila.producto else None,
        )
        for fila in orden.plan
    ]
    return respuesta
