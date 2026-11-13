"""Recepcion fisica de una OC y desbloqueo de pedidos (Features 020/021)."""

from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import permisos
from app.models import (
    EstadoTicket,
    FacturaCompra,
    HistorialTransicionTicket,
    MovimientoInventario,
    OrdenCompra,
    Producto,
    StockSede,
    Ticket,
)
from app.schemas.compra_schema import (
    MovimientoRecepcionRespuesta,
    RecepcionRespuesta,
    TicketDesbloqueadoRespuesta,
)
from app.services import inventario_service
from app.services.auth_service import IdentidadAutenticada

from ._comun import (
    _ESTADO_EN_CURSO,
    _FACTURADA,
    _RECIBIDA,
    _cargar_orden,
    _confirmar,
    _conflicto,
    _es_postgres,
    _institucion_del_actor,
    _no_encontrado,
    orden_a_respuesta,
)
from .cobertura import calcular_cobertura_tickets


def _observacion_recepcion(
    orden: OrdenCompra,
    factura: FacturaCompra,
    identidad: IdentidadAutenticada | None,
) -> str:
    correo = (
        identidad.usuario.correo
        if identidad is not None and identidad.usuario is not None
        else "sin correo"
    )
    return (
        f"Recepción OC {orden.numero_oc} / Factura {factura.numero_factura}"
        f" — Bodeguero: {correo}"
    )[:250]


def recepcionar_orden_compra(
    db_tenant: Session, orden_id: int, identidad: IdentidadAutenticada | None
) -> RecepcionRespuesta:
    """Confirma la recepcion total de una OC `Facturada` (AC-7…AC-11).

    Una unica transaccion: incrementa `stock_sede` (creando la fila si falta),
    escribe un `movimiento_inventario` `ENTRADA` por detalle, sella la OC como
    `Recibida` y registra el desbloqueo de los tickets que pasan a cubiertos.
    No recibe cantidades: usa `detalle_orden_compra.cantidad_solicitada`.

    El producto **no** se exige activo: si se desactivo despues de la emision,
    la mercaderia ya fue despachada y debe auditarse (DT-11). La excepcion no se
    extiende al endpoint generico de movimientos, que conserva su 409.
    """
    if permisos.nombre_rol_de(identidad) != permisos.RolConocido.BODEGUERO.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo el Bodeguero de la sede puede recepcionar la orden",
        )
    institucion_id = _institucion_del_actor(db_tenant, identidad)
    sede_id = inventario_service.sede_del_alcance_por_rol(db_tenant, identidad)

    # Bloqueo de la OC (orden OC -> producto -> stock_sede, spec §6.4).
    consulta = select(OrdenCompra).where(
        OrdenCompra.orden_compra_id == orden_id
    )
    if _es_postgres(db_tenant):
        consulta = consulta.with_for_update()
    orden = db_tenant.execute(consulta).scalar_one_or_none()
    if (
        orden is None
        or orden.institucion_id != institucion_id
        or orden.sede_id != sede_id
    ):
        raise _no_encontrado("Orden de compra no encontrada")
    if orden.estado == _RECIBIDA:
        raise _conflicto("Orden ya recepcionada")
    if orden.estado != _FACTURADA:
        raise _conflicto(
            "La orden debe estar facturada para confirmar la recepcion"
        )

    orden = _cargar_orden(db_tenant, orden_id, institucion_id)
    factura = orden.factura
    if factura is None:
        raise _conflicto("La orden no tiene factura registrada")

    cobertura_antes = calcular_cobertura_tickets(db_tenant, sede_id)
    observacion = _observacion_recepcion(orden, factura, identidad)
    movimientos: list[MovimientoRecepcionRespuesta] = []

    for detalle in sorted(orden.detalles, key=lambda fila: fila.producto_id):
        producto = db_tenant.execute(
            select(Producto)
            .where(Producto.producto_id == detalle.producto_id)
            .with_for_update()
        ).scalar_one_or_none()
        if producto is None:
            raise _no_encontrado("Producto no encontrado")

        fila = db_tenant.execute(
            select(StockSede)
            .where(
                StockSede.sede_id == sede_id,
                StockSede.producto_id == detalle.producto_id,
            )
            .with_for_update()
        ).scalar_one_or_none()
        if fila is None:
            fila = StockSede(
                sede_id=sede_id,
                producto_id=detalle.producto_id,
                institucion_id=institucion_id,
                stock_actual=detalle.cantidad_solicitada,
            )
            db_tenant.add(fila)
            db_tenant.flush()
        else:
            fila.stock_actual += detalle.cantidad_solicitada

        movimiento = MovimientoInventario(
            tipo_movimiento=inventario_service.TIPO_ENTRADA,
            cantidad=detalle.cantidad_solicitada,
            observacion=observacion,
            stock_sede_id=fila.stock_sede_id,
        )
        db_tenant.add(movimiento)
        db_tenant.flush()
        movimientos.append(
            MovimientoRecepcionRespuesta(
                movimiento_id=movimiento.movimiento_id,
                producto_id=producto.producto_id,
                producto_nombre=producto.nombre,
                cantidad=detalle.cantidad_solicitada,
                stock_sede_id=fila.stock_sede_id,
                stock_actual=fila.stock_actual,
                observacion=observacion,
            )
        )

    orden.estado = _RECIBIDA
    orden.fecha_recepcion = datetime.utcnow()
    db_tenant.flush()

    cobertura_despues = calcular_cobertura_tickets(db_tenant, sede_id)
    desbloqueados_ids = [
        ticket_id
        for ticket_id, cubierto in cobertura_despues.items()
        if cubierto and not cobertura_antes.get(ticket_id, False)
    ]
    desbloqueados: list[TicketDesbloqueadoRespuesta] = []
    motivo = (
        f"Desbloqueo por reabastecimiento: OC {orden.numero_oc} / "
        f"Factura {factura.numero_factura}"
    )
    if desbloqueados_ids:
        estado_en_curso = db_tenant.execute(
            select(EstadoTicket).where(EstadoTicket.nombre == _ESTADO_EN_CURSO)
        ).scalar_one_or_none()
        tickets = {
            ticket.ticket_id: ticket
            for ticket in db_tenant.execute(
                select(Ticket).where(
                    Ticket.ticket_id.in_(desbloqueados_ids)
                )
            )
            .scalars()
            .all()
        }
        actor_id = (
            identidad.usuario.usuario_id
            if identidad is not None and identidad.usuario is not None
            else None
        )
        for ticket_id in desbloqueados_ids:
            ticket = tickets.get(ticket_id)
            if ticket is None:
                continue
            if estado_en_curso is not None and actor_id is not None:
                db_tenant.add(
                    HistorialTransicionTicket(
                        ticket_id=ticket_id,
                        estado_origen_id=estado_en_curso.estado_id,
                        estado_destino_id=estado_en_curso.estado_id,
                        usuario_id=actor_id,
                        motivo=motivo,
                        # Feature 021 (AC-6): enlace de auditoria de la OC que
                        # desbloqueo el pedido. Solo esta fila lo lleva.
                        orden_compra_id=orden.orden_compra_id,
                    )
                )
            desbloqueados.append(
                TicketDesbloqueadoRespuesta(
                    ticket_id=ticket_id, asunto=ticket.asunto
                )
            )
        db_tenant.flush()

    _confirmar(db_tenant, "No se pudo confirmar la recepcion de la orden")
    orden = _cargar_orden(db_tenant, orden_id, institucion_id)
    return RecepcionRespuesta(
        orden=orden_a_respuesta(orden),
        estado=orden.estado,
        fecha_recepcion=orden.fecha_recepcion,
        movimientos=movimientos,
        tickets_desbloqueados=desbloqueados,
    )
