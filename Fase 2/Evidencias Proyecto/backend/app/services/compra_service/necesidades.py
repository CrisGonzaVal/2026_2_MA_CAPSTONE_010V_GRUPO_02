"""Necesidades de reabastecimiento y simulacion de cobertura (Features 020/021)."""

from __future__ import annotations

from typing import Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models import (
    Categoria,
    DetalleOrdenCompra,
    DetalleTicket,
    EstadoTicket,
    OrdenCompra,
    OrdenCompraTicket,
    Producto,
    Sede,
    StockSede,
    Ticket,
)
from app.schemas.compra_schema import (
    NecesidadReabastecimiento,
    NecesidadTicketRespuesta,
)
from app.services.auth_service import IdentidadAutenticada

from ._comun import (
    SimulacionTicketProducto,
    _BORRADOR,
    _EMITIDA,
    _ESTADO_EN_CURSO,
    _FACTURADA,
    _es_postgres,
    _institucion_del_actor,
)


def _simular_claves(
    db: Session,
    institucion_id: str,
    claves: Iterable[tuple[int, int]],
    cantidades_oc: dict[tuple[int, int], int] | None = None,
    bloquear: bool = False,
) -> dict[tuple[int, int], list[SimulacionTicketProducto]]:
    """Simula la necesidad neta parcial por `(sede, producto)` (DT-2).

    Para cada pedido `EnCurso` de la sede, en orden `prioridad_id ASC`,
    `fecha_creacion ASC`, `ticket_id ASC`:

    ```
    base           = max(0, solicitado - plan_previo - entregado)
    cubierto_stock = min(base, stock_restante)
    necesidad      = base - cubierto_stock
    asignada       = min(necesidad, cantidad_oc_restante)
    faltante       = necesidad - asignada
    ```

    `plan_previo` suma solo OC `Emitida` + `Facturada`; las `Recibida` ya estan
    en `stock_actual` y las `Cancelada` no cubren. El stock se reparte de forma
    **parcial** entre pedidos (a diferencia de `calcular_cobertura_tickets`, que
    es todo-o-nada y no se modifica). No reserva stock y es determinista.

    Devuelve **todas** las filas de pedidos que demandan la clave, incluidas las
    que reciben `asignada = 0`. Con `bloquear=True` toma `FOR UPDATE` sobre los
    pedidos participantes (solo PostgreSQL); SQLite lo ignora.
    """
    claves_normalizadas = {(int(sede), int(producto)) for sede, producto in claves}
    resultado: dict[tuple[int, int], list[SimulacionTicketProducto]] = {
        clave: [] for clave in claves_normalizadas
    }
    if not claves_normalizadas:
        return resultado

    sedes = {sede for sede, _producto in claves_normalizadas}
    productos = {producto for _sede, producto in claves_normalizadas}
    cantidades = cantidades_oc or {}

    estado_en_curso = db.execute(
        select(EstadoTicket).where(EstadoTicket.nombre == _ESTADO_EN_CURSO)
    ).scalar_one_or_none()
    if estado_en_curso is None:
        return resultado

    consulta_ids = (
        select(Ticket.ticket_id)
        .join(DetalleTicket, DetalleTicket.ticket_id == Ticket.ticket_id)
        .where(Ticket.institucion_id == institucion_id)
        .where(Ticket.estado_id == estado_en_curso.estado_id)
        .where(Ticket.sede_id.in_(sedes))
        .where(DetalleTicket.producto_id.in_(productos))
        .distinct()
    )
    if bloquear and _es_postgres(db):
        db.execute(
            select(Ticket.ticket_id)
            .where(Ticket.ticket_id.in_(consulta_ids))
            .with_for_update()
        )

    tickets = (
        db.execute(
            select(Ticket)
            .options(
                joinedload(Ticket.prioridad),
                joinedload(Ticket.usuario),
                selectinload(Ticket.detalles),
            )
            .where(Ticket.ticket_id.in_(consulta_ids))
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
    if not tickets:
        return resultado

    ids_tickets = [ticket.ticket_id for ticket in tickets]
    plan_previo: dict[tuple[int, int], int] = {
        (ticket_id, producto_id): int(cantidad or 0)
        for ticket_id, producto_id, cantidad in db.execute(
            select(
                OrdenCompraTicket.ticket_id,
                OrdenCompraTicket.producto_id,
                func.sum(OrdenCompraTicket.cantidad_asignada),
            )
            .join(
                OrdenCompra,
                OrdenCompra.orden_compra_id
                == OrdenCompraTicket.orden_compra_id,
            )
            .where(OrdenCompraTicket.institucion_id == institucion_id)
            .where(OrdenCompra.estado.in_({_EMITIDA, _FACTURADA}))
            .where(OrdenCompraTicket.ticket_id.in_(ids_tickets))
            .where(OrdenCompraTicket.producto_id.in_(productos))
            .group_by(
                OrdenCompraTicket.ticket_id, OrdenCompraTicket.producto_id
            )
        ).all()
    }
    stock: dict[tuple[int, int], int] = {
        (sede, producto): int(cantidad)
        for sede, producto, cantidad in db.execute(
            select(
                StockSede.sede_id,
                StockSede.producto_id,
                StockSede.stock_actual,
            )
            .where(StockSede.institucion_id == institucion_id)
            .where(StockSede.sede_id.in_(sedes))
            .where(StockSede.producto_id.in_(productos))
        ).all()
    }

    for clave in claves_normalizadas:
        sede_id, producto_id = clave
        stock_restante = max(0, stock.get(clave, 0))
        oc_restante = max(0, int(cantidades.get(clave, 0)))
        filas: list[SimulacionTicketProducto] = []

        for ticket in tickets:
            if ticket.sede_id != sede_id:
                continue
            solicitado = sum(
                detalle.cantidad_solicitada
                for detalle in ticket.detalles
                if detalle.producto_id == producto_id
            )
            if solicitado <= 0:
                continue
            entregado = sum(
                detalle.cantidad_entregada or 0
                for detalle in ticket.detalles
                if detalle.producto_id == producto_id
            )
            plan = plan_previo.get((ticket.ticket_id, producto_id), 0)
            base = max(0, solicitado - plan - entregado)
            cubierto_stock = min(base, stock_restante)
            stock_restante -= cubierto_stock
            necesidad = base - cubierto_stock
            asignada = min(necesidad, oc_restante)
            oc_restante -= asignada
            faltante = necesidad - asignada
            cubierto_previo = plan + cubierto_stock + entregado
            if faltante == 0:
                cobertura = "total"
            elif cubierto_previo + asignada == 0:
                cobertura = "sin_cobertura"
            else:
                cobertura = "parcial"

            usuario = ticket.usuario
            prioridad = ticket.prioridad
            filas.append(
                SimulacionTicketProducto(
                    ticket_id=ticket.ticket_id,
                    asunto=ticket.asunto,
                    solicitante_nombre=usuario.nombre if usuario else None,
                    solicitante_apellido=usuario.apellido if usuario else None,
                    solicitante_correo=usuario.correo if usuario else None,
                    prioridad_nombre=prioridad.nombre if prioridad else None,
                    fecha_creacion=ticket.fecha_creacion,
                    solicitado=solicitado,
                    plan_previo=plan,
                    cubierto_stock=cubierto_stock,
                    entregado=entregado,
                    necesidad=necesidad,
                    asignada=asignada,
                    faltante=faltante,
                    cobertura=cobertura,
                )
            )
        resultado[clave] = filas
    return resultado


def institucion_de_compras(
    db: Session, identidad: IdentidadAutenticada | None
) -> str:
    """Institucion del actor de compras; 403 si no tiene tenant de negocio.

    Costura publica para los endpoints que resuelven el tenant antes de llamar a
    una lectura por `institucion_id` (necesidades). La regla vive aqui, no en la
    capa HTTP (AGENTS §6).
    """
    return _institucion_del_actor(db, identidad)


def listar_necesidades_reabastecimiento(
    db: Session, institucion_id: str, sede_id: int | None = None
) -> list[NecesidadReabastecimiento]:
    """Consolidado por `(sede, producto)` de la institucion (AC-1).

    Participan productos y categorias activos. Un `sede_id` inexistente o ajeno
    se comporta como filtro de lista y devuelve `[]` (no 404). La demanda suma
    solo pedidos `EnCurso` de la sede; los estados no aprobados y los terminales
    quedan fuera (spec §9.4/§9.9).

    Feature 021: agrega `stock_comprometido` (OC `Emitida` + `Facturada`),
    `stock_borrador` (informativo, no descuenta), los pedidos que componen la
    demanda y el sugerido neto
    `max(0, stock_minimo + demanda_tickets - stock_actual - stock_comprometido)`.
    """
    if sede_id is not None:
        sede = db.get(Sede, sede_id)
        if sede is None or sede.institucion_id != institucion_id:
            return []

    consulta_stock = (
        select(
            StockSede.sede_id,
            StockSede.producto_id,
            StockSede.stock_actual,
        )
        .join(Producto, Producto.producto_id == StockSede.producto_id)
        .join(Categoria, Categoria.categoria_id == Producto.categoria_id)
        .where(StockSede.institucion_id == institucion_id)
        .where(Producto.institucion_id == institucion_id)
        .where(Producto.activo.is_(True))
        .where(Categoria.activo.is_(True))
    )
    consulta_demanda = (
        select(
            Ticket.sede_id,
            DetalleTicket.producto_id,
            func.sum(DetalleTicket.cantidad_solicitada).label("demanda"),
        )
        .join(DetalleTicket, DetalleTicket.ticket_id == Ticket.ticket_id)
        .join(EstadoTicket, EstadoTicket.estado_id == Ticket.estado_id)
        .join(Producto, Producto.producto_id == DetalleTicket.producto_id)
        .join(Categoria, Categoria.categoria_id == Producto.categoria_id)
        .where(Ticket.institucion_id == institucion_id)
        .where(Ticket.sede_id.is_not(None))
        .where(EstadoTicket.nombre == _ESTADO_EN_CURSO)
        .where(Producto.institucion_id == institucion_id)
        .where(Producto.activo.is_(True))
        .where(Categoria.activo.is_(True))
        .group_by(Ticket.sede_id, DetalleTicket.producto_id)
    )
    consulta_comprometida = (
        select(
            OrdenCompra.sede_id,
            DetalleOrdenCompra.producto_id,
            OrdenCompra.estado,
            func.sum(DetalleOrdenCompra.cantidad_solicitada).label("cantidad"),
        )
        .join(
            OrdenCompra,
            OrdenCompra.orden_compra_id
            == DetalleOrdenCompra.orden_compra_id,
        )
        .where(DetalleOrdenCompra.institucion_id == institucion_id)
        .where(
            OrdenCompra.estado.in_({_EMITIDA, _FACTURADA, _BORRADOR})
        )
        .group_by(
            OrdenCompra.sede_id,
            DetalleOrdenCompra.producto_id,
            OrdenCompra.estado,
        )
    )
    if sede_id is not None:
        consulta_stock = consulta_stock.where(StockSede.sede_id == sede_id)
        consulta_demanda = consulta_demanda.where(Ticket.sede_id == sede_id)
        consulta_comprometida = consulta_comprometida.where(
            OrdenCompra.sede_id == sede_id
        )

    stock: dict[tuple[int, int], int] = {
        (fila.sede_id, fila.producto_id): fila.stock_actual
        for fila in db.execute(consulta_stock).all()
    }
    demanda: dict[tuple[int, int], int] = {
        (fila.sede_id, fila.producto_id): int(fila.demanda or 0)
        for fila in db.execute(consulta_demanda).all()
    }
    comprometido: dict[tuple[int, int], int] = {}
    borrador: dict[tuple[int, int], int] = {}
    for fila in db.execute(consulta_comprometida).all():
        clave = (fila.sede_id, fila.producto_id)
        if fila.estado == _BORRADOR:
            borrador[clave] = borrador.get(clave, 0) + int(fila.cantidad or 0)
        else:
            comprometido[clave] = comprometido.get(clave, 0) + int(
                fila.cantidad or 0
            )

    productos = {
        producto.producto_id: producto
        for producto in db.execute(
            select(Producto)
            .join(Categoria, Categoria.categoria_id == Producto.categoria_id)
            .where(Producto.institucion_id == institucion_id)
            .where(Producto.activo.is_(True))
            .where(Categoria.activo.is_(True))
        )
        .scalars()
        .all()
    }
    sedes = {
        sede.sede_id: sede
        for sede in db.execute(
            select(Sede).where(Sede.institucion_id == institucion_id)
        )
        .scalars()
        .all()
    }

    claves = set(stock) | set(demanda)
    simulaciones = _simular_claves(db, institucion_id, claves)
    necesidades: list[NecesidadReabastecimiento] = []
    for clave in claves:
        sede_id_fila, producto_id = clave
        producto = productos.get(producto_id)
        sede = sedes.get(sede_id_fila)
        if producto is None or sede is None:
            continue
        stock_actual = stock.get(clave, 0)
        demanda_tickets = demanda.get(clave, 0)
        if (
            stock_actual > producto.stock_minimo
            and demanda_tickets <= stock_actual
        ):
            continue
        stock_comprometido = comprometido.get(clave, 0)
        sugerido = max(
            0,
            producto.stock_minimo
            + demanda_tickets
            - stock_actual
            - stock_comprometido,
        )
        tickets = [
            NecesidadTicketRespuesta(
                ticket_id=simulacion.ticket_id,
                asunto=simulacion.asunto,
                solicitante_nombre=simulacion.solicitante_nombre,
                solicitante_apellido=simulacion.solicitante_apellido,
                solicitante_correo=simulacion.solicitante_correo,
                prioridad_nombre=simulacion.prioridad_nombre,
                fecha_creacion=simulacion.fecha_creacion,
                cantidad_solicitada=simulacion.solicitado,
                cantidad_cubierta=max(
                    0, simulacion.solicitado - simulacion.faltante
                ),
                cantidad_faltante=simulacion.faltante,
            )
            for simulacion in simulaciones.get(clave, [])
        ]
        necesidades.append(
            NecesidadReabastecimiento(
                sede_id=sede.sede_id,
                sede_nombre=sede.nombre,
                producto_id=producto.producto_id,
                nombre=producto.nombre,
                stock_actual=stock_actual,
                stock_minimo=producto.stock_minimo,
                demanda_tickets=demanda_tickets,
                sugerido=sugerido,
                stock_comprometido=stock_comprometido,
                stock_borrador=borrador.get(clave, 0),
                tickets=tickets,
            )
        )
    necesidades.sort(key=lambda fila: (fila.sede_id, fila.producto_id))
    return necesidades
