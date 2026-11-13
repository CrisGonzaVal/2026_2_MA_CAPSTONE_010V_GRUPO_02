"""Preview de cobertura y cobertura greedy de pedidos (Feature 021)."""

from __future__ import annotations

from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models import EstadoTicket, Producto, StockSede, Ticket
from app.schemas.compra_schema import (
    CoberturaPreviewProducto,
    CoberturaPreviewRespuesta,
    CoberturaPreviewSolicitud,
    CoberturaPreviewTicket,
)
from app.services.auth_service import IdentidadAutenticada

from ._comun import (
    _ESTADO_EN_CURSO,
    _conflicto,
    _institucion_del_actor,
    _no_encontrado,
    _sede_valida,
)
from .necesidades import _simular_claves


def previsualizar_cobertura(
    db: Session,
    datos: CoberturaPreviewSolicitud,
    identidad: IdentidadAutenticada | None,
) -> CoberturaPreviewRespuesta:
    """Simula la cobertura de una compra hipotetica (AC-2, DT-4).

    Ejecuta exactamente `_simular_claves` sin persistir ni reservar. La sede es
    concreta: inexistente o ajena responde **404** (no es un filtro de lista).
    El producto ajeno o inexistente responde **404**; el inactivo o repetido,
    **409**. La precedencia sigue el plan §3: primero 409 (regla) y despues 404.
    """
    institucion_id = _institucion_del_actor(db, identidad)
    sede = _sede_valida(db, datos.sede_id, institucion_id)

    ids = [item.producto_id for item in datos.items]
    if len(set(ids)) != len(ids):
        raise _conflicto(
            "No se puede repetir un producto en la simulacion de cobertura"
        )

    productos = {
        producto.producto_id: producto
        for producto in db.execute(
            select(Producto)
            .where(Producto.institucion_id == institucion_id)
            .where(Producto.producto_id.in_(ids))
        )
        .scalars()
        .all()
    }
    for item in datos.items:
        producto = productos.get(item.producto_id)
        if producto is not None and not producto.activo:
            raise _conflicto("El producto esta inactivo")
    for item in datos.items:
        if item.producto_id not in productos:
            raise _no_encontrado("Producto no encontrado")

    cantidades_oc = {
        (sede.sede_id, item.producto_id): item.cantidad_solicitada
        for item in datos.items
    }
    simulaciones = _simular_claves(
        db,
        institucion_id,
        cantidades_oc.keys(),
        cantidades_oc=cantidades_oc,
    )

    respuesta_productos: list[CoberturaPreviewProducto] = []
    for item in datos.items:
        filas = simulaciones.get((sede.sede_id, item.producto_id), [])
        producto = productos[item.producto_id]
        asignado = sum(fila.asignada for fila in filas)
        respuesta_productos.append(
            CoberturaPreviewProducto(
                producto_id=producto.producto_id,
                producto_nombre=producto.nombre,
                cantidad_simulada=item.cantidad_solicitada,
                demanda_total=sum(fila.solicitado for fila in filas),
                cubierto_previo=sum(
                    fila.plan_previo + fila.cubierto_stock + fila.entregado
                    for fila in filas
                ),
                asignado=asignado,
                faltante=sum(fila.faltante for fila in filas),
                sin_asignar=max(0, item.cantidad_solicitada - asignado),
                tickets=[
                    CoberturaPreviewTicket(
                        ticket_id=fila.ticket_id,
                        asunto=fila.asunto,
                        solicitante_nombre=fila.solicitante_nombre,
                        solicitante_apellido=fila.solicitante_apellido,
                        prioridad_nombre=fila.prioridad_nombre,
                        fecha_creacion=fila.fecha_creacion,
                        solicitado=fila.solicitado,
                        cubierto_plan=fila.plan_previo,
                        cubierto_stock=fila.cubierto_stock,
                        necesidad=fila.necesidad,
                        asignada=fila.asignada,
                        faltante=fila.faltante,
                        cobertura=fila.cobertura,
                    )
                    for fila in filas
                ],
            )
        )
    return CoberturaPreviewRespuesta(
        sede_id=sede.sede_id,
        sede_nombre=sede.nombre,
        productos=respuesta_productos,
    )


def calcular_cobertura_tickets(
    db: Session, sede_id: int, producto_ids: Sequence[int] | None = None
) -> dict[int, bool]:
    """Simula la cobertura de los tickets `EnCurso` de una sede (§9.4).

    Reglas exactas de la spec:

    * solo participan tickets `EnCurso` de la sede;
    * orden por `prioridad_id ASC`, `fecha_creacion ASC`, `ticket_id ASC`;
    * la asignacion es por producto y **todo o nada por ticket**: un ticket que
      no cabe completo no consume saldo y se evalua el siguiente;
    * el saldo no se reserva: la simulacion es de lectura.

    Devuelve `{ticket_id: cubierto}`. `producto_ids` solo filtra **el resultado**
    (util para acotar la respuesta a los productos recepcionados); la simulacion
    siempre considera todos los detalles del ticket para que el resultado sea el
    mismo que ve `GET /tickets/{id}`.
    """
    stock: dict[int, int] = {
        producto_id: stock_actual
        for producto_id, stock_actual in db.execute(
            select(StockSede.producto_id, StockSede.stock_actual).where(
                StockSede.sede_id == sede_id
            )
        ).all()
    }
    tickets = (
        db.execute(
            select(Ticket)
            .join(EstadoTicket, EstadoTicket.estado_id == Ticket.estado_id)
            .options(
                joinedload(Ticket.prioridad),
                selectinload(Ticket.detalles),
            )
            .where(Ticket.sede_id == sede_id)
            .where(EstadoTicket.nombre == _ESTADO_EN_CURSO)
            .order_by(
                Ticket.prioridad_id.asc(),
                Ticket.fecha_creacion.asc(),
                Ticket.ticket_id.asc(),
            )
        )
        .unique()
        .scalars()
        .all()
    )

    filtro = set(producto_ids) if producto_ids is not None else None
    cobertura: dict[int, bool] = {}
    for ticket in tickets:
        consumos: dict[int, int] = {}
        for detalle in ticket.detalles:
            consumos[detalle.producto_id] = (
                consumos.get(detalle.producto_id, 0)
                + detalle.cantidad_solicitada
            )
        cubierto = all(
            stock.get(producto_id, 0) >= cantidad
            for producto_id, cantidad in consumos.items()
        )
        if cubierto:
            for producto_id, cantidad in consumos.items():
                stock[producto_id] = stock.get(producto_id, 0) - cantidad
        if filtro is None or any(
            producto_id in filtro for producto_id in consumos
        ):
            cobertura[ticket.ticket_id] = cubierto
    return cobertura
