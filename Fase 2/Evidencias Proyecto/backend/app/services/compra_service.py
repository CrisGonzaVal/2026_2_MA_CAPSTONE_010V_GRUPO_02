"""Servicio del reabastecimiento externo y compras (Feature 020).

Cubre el ciclo del Administrador Institucional: deteccion de necesidades,
catalogo global de proveedores, creacion/edicion/emision de la Orden de Compra,
registro/correccion de la factura y cancelacion. La recepcion fisica y la
cobertura de tickets viven en la parte 2 del mismo servicio (T5).

Decisiones de diseno (plan.md): DT-1 (proveedor global + replica tenant con el
mismo ID), DT-3/DT-4 (saldo en `stock_sede`, sin autor en el movimiento), DT-7
(`numero_oc` derivado del identity), DT-10 (factura con `proveedor_id` y FK
compuesta), DT-11 (producto inactivo) y DT-12 (cancelacion con actor y fecha).

La sesion de control y la sesion tenant son independientes en PostgreSQL. En
SQLite la suite ordinaria usa un contexto logico unico: `control.proveedor` y la
replica tenant son la misma tabla fisica, por lo que la replicacion se omite y
la prueba de aislamiento real se ejerce en los tests gated de PostgreSQL 16.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Iterable, Sequence

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core import permisos
from app.models import (
    Categoria,
    DetalleOrdenCompra,
    DetalleTicket,
    EstadoTicket,
    FacturaCompra,
    HistorialTransicionTicket,
    MovimientoInventario,
    OrdenCompra,
    Prioridad,
    Producto,
    Proveedor,
    ProveedorControl,
    Sede,
    StockSede,
    Ticket,
)
from app.schemas.compra_schema import (
    CancelacionOrdenCompra,
    DetalleOrdenCompraCrear,
    FacturaCompraRegistrar,
    MovimientoRecepcionRespuesta,
    NecesidadReabastecimiento,
    OrdenCompraActualizar,
    OrdenCompraCrear,
    OrdenCompraRespuesta,
    ProveedorCrear,
    RecepcionRespuesta,
    TicketDesbloqueadoRespuesta,
)
from app.services import ambito_service, inventario_service
from app.services.auth_service import IdentidadAutenticada

_ADMINISTRADOR = permisos.RolConocido.ADMINISTRADOR.value
_ESTADO_EN_CURSO = "EnCurso"
_BORRADOR = "Borrador"
_EMITIDA = "Emitida"
_FACTURADA = "Facturada"
_RECIBIDA = "Recibida"
_CANCELADA = "Cancelada"


# ---------------------------------------------------------------------------
# Errores y helpers internos
# ---------------------------------------------------------------------------


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


def _proveedor_activo_control(
    db_control: Session, proveedor_id: int
) -> ProveedorControl:
    proveedor = db_control.get(ProveedorControl, proveedor_id)
    if proveedor is None:
        raise _no_encontrado("Proveedor no encontrado")
    if not proveedor.activo:
        raise _conflicto("El proveedor esta inactivo")
    return proveedor


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


def _total_orden(items: Iterable[DetalleOrdenCompraCrear]) -> Decimal:
    total = sum(
        (
            Decimal(item.precio_unitario) * item.cantidad_solicitada
            for item in items
        ),
        Decimal("0.00"),
    )
    return total.quantize(Decimal("0.01"))


def _replicar_proveedor(
    db_tenant: Session, proveedor: ProveedorControl
) -> None:
    """Upsert de la replica tenant con el mismo `proveedor_id` (DT-1).

    Solo aplica en PostgreSQL. En SQLite control y tenant comparten la tabla
    fisica `proveedor`, de modo que insertar de nuevo violaria la PK.
    """
    if not _es_postgres(db_tenant):
        return
    replica = db_tenant.get(Proveedor, proveedor.proveedor_id)
    if replica is None:
        replica = Proveedor(
            proveedor_id=proveedor.proveedor_id,
            rut=proveedor.rut,
            razon_social=proveedor.razon_social,
            nombre_fantasia=proveedor.nombre_fantasia,
            giro=proveedor.giro,
            correo=proveedor.correo,
            telefono=proveedor.telefono,
            activo=proveedor.activo,
        )
        db_tenant.add(replica)
    else:
        replica.rut = proveedor.rut
        replica.razon_social = proveedor.razon_social
        replica.nombre_fantasia = proveedor.nombre_fantasia
        replica.giro = proveedor.giro
        replica.correo = proveedor.correo
        replica.telefono = proveedor.telefono
        replica.activo = proveedor.activo
    db_tenant.flush()


def _cargar_orden(
    db: Session, orden_id: int, institucion_id: str | None
) -> OrdenCompra:
    orden = db.execute(
        select(OrdenCompra)
        .options(
            joinedload(OrdenCompra.proveedor),
            joinedload(OrdenCompra.sede),
            joinedload(OrdenCompra.factura),
            selectinload(OrdenCompra.detalles).joinedload(
                DetalleOrdenCompra.producto
            ),
        )
        .where(OrdenCompra.orden_compra_id == orden_id)
    ).unique().scalar_one_or_none()
    if orden is None or (
        institucion_id is not None
        and orden.institucion_id != institucion_id
    ):
        raise _no_encontrado("Orden de compra no encontrada")
    return orden


def _agregar_detalles(
    db: Session,
    orden: OrdenCompra,
    items: Sequence[DetalleOrdenCompraCrear],
) -> None:
    for item in items:
        db.add(
            DetalleOrdenCompra(
                orden_compra_id=orden.orden_compra_id,
                institucion_id=orden.institucion_id,
                producto_id=item.producto_id,
                cantidad_solicitada=item.cantidad_solicitada,
                precio_unitario=Decimal(item.precio_unitario),
            )
        )


# ---------------------------------------------------------------------------
# AC-1: necesidades de reabastecimiento
# ---------------------------------------------------------------------------


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
    solo tickets `EnCurso` de la sede; los estados no aprobados y los terminales
    quedan fuera (spec §9.4/§9.9).
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
    if sede_id is not None:
        consulta_stock = consulta_stock.where(StockSede.sede_id == sede_id)
        consulta_demanda = consulta_demanda.where(Ticket.sede_id == sede_id)

    stock: dict[tuple[int, int], int] = {
        (fila.sede_id, fila.producto_id): fila.stock_actual
        for fila in db.execute(consulta_stock).all()
    }
    demanda: dict[tuple[int, int], int] = {
        (fila.sede_id, fila.producto_id): int(fila.demanda or 0)
        for fila in db.execute(consulta_demanda).all()
    }

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
        sugerido = max(
            0,
            producto.stock_minimo + demanda_tickets - stock_actual,
        )
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
            )
        )
    necesidades.sort(key=lambda fila: (fila.sede_id, fila.producto_id))
    return necesidades


# ---------------------------------------------------------------------------
# AC-2: catalogo global de proveedores
# ---------------------------------------------------------------------------


def listar_proveedores(db_control: Session) -> list[ProveedorControl]:
    """Proveedores activos del catalogo global, en orden alfabetico."""
    return list(
        db_control.execute(
            select(ProveedorControl)
            .where(ProveedorControl.activo.is_(True))
            .order_by(ProveedorControl.razon_social, ProveedorControl.proveedor_id)
        )
        .scalars()
        .all()
    )


def crear_proveedor(
    db_control: Session,
    db_tenant: Session,
    datos: ProveedorCrear,
    identidad: IdentidadAutenticada | None,
) -> ProveedorControl:
    """Alta en `control.proveedor` y replica tenant si el actor es Administrador.

    El Superadmin opera solo sobre control (AC-2). En SQLite la replica es la
    misma tabla fisica y no se reinserta.
    """
    rut = datos.rut.strip()
    existente = db_control.execute(
        select(ProveedorControl).where(ProveedorControl.rut == rut)
    ).scalar_one_or_none()
    if existente is not None:
        raise _conflicto("El RUT del proveedor ya esta registrado")

    proveedor = ProveedorControl(
        rut=rut,
        razon_social=datos.razon_social.strip(),
        nombre_fantasia=datos.nombre_fantasia,
        giro=datos.giro,
        correo=str(datos.correo) if datos.correo is not None else None,
        telefono=datos.telefono,
        activo=True,
    )
    db_control.add(proveedor)
    _confirmar(db_control, "El RUT del proveedor ya esta registrado")
    db_control.refresh(proveedor)

    if permisos.nombre_rol_de(identidad) == _ADMINISTRADOR:
        _replicar_proveedor(db_tenant, proveedor)
        _confirmar(
            db_tenant,
            "La replica local del proveedor ya existe con otro identificador",
        )
    return proveedor


# ---------------------------------------------------------------------------
# AC-3/AC-6: listado de ordenes segun el rol
# ---------------------------------------------------------------------------


def listar_ordenes_compra(
    db: Session,
    identidad: IdentidadAutenticada | None,
    *,
    estado: str | None = None,
    sede_id: int | None = None,
) -> list[OrdenCompra]:
    """Ordenes visibles para el actor, con filtros de lista (AC-3/AC-6).

    El Administrador ve todas las OC de su institucion y puede filtrar por
    `estado` y `sede_id`; un filtro de sede inexistente o ajeno devuelve `[]`
    (es un filtro de lista, no una lectura por ID). El Bodeguero queda **forzado**
    a las OC `Facturada` de su propia sede: los query params se ignoran y sin
    sede asignada responde 409, igual que el resto de su ambito operativo
    (spec §6.7). Una OC de otra institucion nunca aparece.
    """
    institucion_id = _institucion_del_actor(db, identidad)
    consulta = (
        select(OrdenCompra)
        .options(
            joinedload(OrdenCompra.proveedor),
            joinedload(OrdenCompra.sede),
            joinedload(OrdenCompra.factura),
            selectinload(OrdenCompra.detalles).joinedload(
                DetalleOrdenCompra.producto
            ),
        )
        .where(OrdenCompra.institucion_id == institucion_id)
        .order_by(
            OrdenCompra.fecha_creacion.asc(),
            OrdenCompra.orden_compra_id.asc(),
        )
    )

    if permisos.nombre_rol_de(identidad) == permisos.RolConocido.BODEGUERO.value:
        sede_actor = inventario_service.sede_del_alcance_por_rol(db, identidad)
        consulta = consulta.where(
            OrdenCompra.sede_id == sede_actor,
            OrdenCompra.estado == _FACTURADA,
        )
    else:
        if estado is not None:
            consulta = consulta.where(OrdenCompra.estado == estado)
        if sede_id is not None:
            consulta = consulta.where(OrdenCompra.sede_id == sede_id)

    return list(db.execute(consulta).unique().scalars().all())


# ---------------------------------------------------------------------------
# AC-3: creacion y edicion de la Orden de Compra
# ---------------------------------------------------------------------------


def crear_orden_compra(
    db_tenant: Session,
    db_control: Session,
    datos: OrdenCompraCrear,
    identidad: IdentidadAutenticada | None,
) -> OrdenCompra:
    """Crea una OC en `Borrador` con total calculado (AC-3)."""
    institucion_id = _institucion_del_actor(db_tenant, identidad)
    _sede_valida(db_tenant, datos.sede_id, institucion_id)
    proveedor = _proveedor_activo_control(db_control, datos.proveedor_id)
    items = _items_validados(db_tenant, datos.items, institucion_id)
    _replicar_proveedor(db_tenant, proveedor)

    orden = OrdenCompra(
        institucion_id=institucion_id,
        sede_id=datos.sede_id,
        proveedor_id=datos.proveedor_id,
        estado=_BORRADOR,
        total=_total_orden(items),
    )
    db_tenant.add(orden)
    db_tenant.flush()
    _agregar_detalles(db_tenant, orden, items)
    _confirmar(db_tenant, "No se pudo crear la orden de compra")
    return _cargar_orden(db_tenant, orden.orden_compra_id, institucion_id)


def actualizar_orden_compra(
    db_tenant: Session,
    db_control: Session,
    orden_id: int,
    datos: OrdenCompraActualizar,
    identidad: IdentidadAutenticada | None,
) -> OrdenCompra:
    """Reemplaza sede, proveedor e items de un borrador (AC-3/DT-14)."""
    institucion_id = _institucion_del_actor(db_tenant, identidad)
    orden = _cargar_orden(db_tenant, orden_id, institucion_id)
    if orden.estado != _BORRADOR:
        raise _conflicto("Solo se puede editar una orden en estado Borrador")

    _sede_valida(db_tenant, datos.sede_id, institucion_id)
    proveedor = _proveedor_activo_control(db_control, datos.proveedor_id)
    items = _items_validados(db_tenant, datos.items, institucion_id)
    _replicar_proveedor(db_tenant, proveedor)

    orden.sede_id = datos.sede_id
    orden.proveedor_id = datos.proveedor_id
    orden.total = _total_orden(items)
    for detalle in list(orden.detalles):
        db_tenant.delete(detalle)
    db_tenant.flush()
    _agregar_detalles(db_tenant, orden, items)
    _confirmar(db_tenant, "No se pudo actualizar la orden de compra")
    return _cargar_orden(db_tenant, orden_id, institucion_id)


# ---------------------------------------------------------------------------
# AC-4: emision formal
# ---------------------------------------------------------------------------


def emitir_orden_compra(
    db_tenant: Session, orden_id: int, identidad: IdentidadAutenticada | None
) -> OrdenCompra:
    """Emite el borrador con `numero_oc` derivado del identity (AC-4/DT-7)."""
    institucion_id = _institucion_del_actor(db_tenant, identidad)
    orden = _cargar_orden(db_tenant, orden_id, institucion_id)
    if orden.estado != _BORRADOR:
        raise _conflicto("Solo se puede emitir una orden en estado Borrador")
    if not orden.detalles:
        raise _conflicto("La orden no tiene items para emitir")
    for detalle in orden.detalles:
        _producto_activo(db_tenant, detalle.producto_id, institucion_id)

    orden.estado = _EMITIDA
    orden.numero_oc = (
        f"OC-{datetime.utcnow().year:04d}-{orden.orden_compra_id:06d}"
    )
    orden.fecha_emision = datetime.utcnow()
    _confirmar(db_tenant, "No se pudo emitir la orden de compra")
    return _cargar_orden(db_tenant, orden_id, institucion_id)


# ---------------------------------------------------------------------------
# AC-5: factura del proveedor
# ---------------------------------------------------------------------------


def registrar_o_editar_factura(
    db_tenant: Session,
    orden_id: int,
    datos: FacturaCompraRegistrar,
    identidad: IdentidadAutenticada | None,
) -> FacturaCompra:
    """Crea la factura en `Emitida` o corrige metadatos en `Facturada` (AC-5)."""
    institucion_id = _institucion_del_actor(db_tenant, identidad)
    orden = _cargar_orden(db_tenant, orden_id, institucion_id)
    if orden.estado in {_RECIBIDA, _CANCELADA}:
        raise _conflicto("La orden ya no admite cambios de factura")
    if orden.estado not in {_EMITIDA, _FACTURADA}:
        raise _conflicto("La orden debe estar emitida para registrar la factura")
    if datos.fecha_factura > date.today():
        raise _no_procesable("La fecha de la factura no puede ser futura")

    duplicada = db_tenant.execute(
        select(FacturaCompra).where(
            FacturaCompra.proveedor_id == orden.proveedor_id,
            FacturaCompra.numero_factura == datos.numero_factura,
            FacturaCompra.orden_compra_id != orden_id,
        )
    ).scalar_one_or_none()
    if duplicada is not None:
        raise _conflicto(
            "El numero de factura ya fue registrado para este proveedor"
        )

    factura = orden.factura
    if factura is None:
        factura = FacturaCompra(
            orden_compra_id=orden.orden_compra_id,
            proveedor_id=orden.proveedor_id,
            numero_factura=datos.numero_factura,
            fecha_factura=datos.fecha_factura,
            monto_total=datos.monto_total,
            observaciones=datos.observaciones,
        )
        db_tenant.add(factura)
    else:
        factura.numero_factura = datos.numero_factura
        factura.fecha_factura = datos.fecha_factura
        factura.monto_total = datos.monto_total
        factura.observaciones = datos.observaciones

    orden.estado = _FACTURADA
    _confirmar(db_tenant, "El numero de factura ya fue registrado")
    db_tenant.refresh(factura)
    return factura


# ---------------------------------------------------------------------------
# AC-12: cancelacion
# ---------------------------------------------------------------------------


def cancelar_orden_compra(
    db_tenant: Session,
    orden_id: int,
    datos: CancelacionOrdenCompra,
    identidad: IdentidadAutenticada | None,
) -> OrdenCompra:
    """Cancela desde Borrador o Emitida y persiste actor, fecha y motivo."""
    institucion_id = _institucion_del_actor(db_tenant, identidad)
    orden = _cargar_orden(db_tenant, orden_id, institucion_id)
    if orden.estado not in {_BORRADOR, _EMITIDA}:
        raise _conflicto(
            "Solo se puede cancelar una orden en estado Borrador o Emitida"
        )
    motivo = datos.motivo_cancelacion.strip()
    if not motivo:
        raise _no_procesable("El motivo de cancelacion es obligatorio")

    orden.estado = _CANCELADA
    orden.motivo_cancelacion = motivo
    orden.fecha_cancelacion = datetime.utcnow()
    orden.cancelado_por_usuario_id = (
        identidad.usuario.usuario_id
        if identidad is not None and identidad.usuario is not None
        else None
    )
    _confirmar(db_tenant, "No se pudo cancelar la orden de compra")
    return _cargar_orden(db_tenant, orden_id, institucion_id)


# ---------------------------------------------------------------------------
# AC-10/AC-11: cobertura greedy de tickets
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# AC-7…AC-11: recepcion fisica total y atomica
# ---------------------------------------------------------------------------


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
        orden=OrdenCompraRespuesta.model_validate(orden),
        estado=orden.estado,
        fecha_recepcion=orden.fecha_recepcion,
        movimientos=movimientos,
        tickets_desbloqueados=desbloqueados,
    )
