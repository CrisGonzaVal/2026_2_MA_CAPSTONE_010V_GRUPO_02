"""Ciclo de la Orden de Compra (Feature 020)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import permisos
from app.models import (
    DetalleOrdenCompra,
    FacturaCompra,
    OrdenCompra,
    OrdenCompraTicket,
)
from app.schemas.compra_schema import (
    CancelacionOrdenCompra,
    DetalleOrdenCompraCrear,
    FacturaCompraRegistrar,
    OrdenCompraActualizar,
    OrdenCompraCrear,
)
from app.services import inventario_service
from app.services.auth_service import IdentidadAutenticada

from ._comun import (
    _BORRADOR,
    _CANCELADA,
    _EMITIDA,
    _FACTURADA,
    _RECIBIDA,
    _cargar_orden,
    _confirmar,
    _conflicto,
    _institucion_del_actor,
    _items_validados,
    _no_procesable,
    _opciones_orden,
    _producto_activo,
    _sede_valida,
)
from .necesidades import _simular_claves
from .proveedores import _proveedor_activo_control, _replicar_proveedor


def _total_orden(items: Iterable[DetalleOrdenCompraCrear]) -> Decimal:
    total = sum(
        (
            Decimal(item.precio_unitario) * item.cantidad_solicitada
            for item in items
        ),
        Decimal("0.00"),
    )
    return total.quantize(Decimal("0.01"))


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


def _validar_entrada_orden(
    db_tenant: Session,
    db_control: Session,
    datos: OrdenCompraCrear | OrdenCompraActualizar,
    institucion_id: str,
) -> list[DetalleOrdenCompraCrear]:
    """Valida sede, proveedor e items, y replica el proveedor en el tenant.

    El orden `sede -> proveedor -> items -> replica` conserva la precedencia de
    los 409/404 y el `flush` del tenant de la Feature 020.
    """
    _sede_valida(db_tenant, datos.sede_id, institucion_id)
    proveedor = _proveedor_activo_control(db_control, datos.proveedor_id)
    items = _items_validados(db_tenant, datos.items, institucion_id)
    _replicar_proveedor(db_tenant, proveedor)
    return items


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
        .options(*_opciones_orden())
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


def crear_orden_compra(
    db_tenant: Session,
    db_control: Session,
    datos: OrdenCompraCrear,
    identidad: IdentidadAutenticada | None,
) -> OrdenCompra:
    """Crea una OC en `Borrador` con total calculado (AC-3)."""
    institucion_id = _institucion_del_actor(db_tenant, identidad)
    items = _validar_entrada_orden(db_tenant, db_control, datos, institucion_id)

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

    items = _validar_entrada_orden(db_tenant, db_control, datos, institucion_id)

    orden.sede_id = datos.sede_id
    orden.proveedor_id = datos.proveedor_id
    orden.total = _total_orden(items)
    for detalle in list(orden.detalles):
        db_tenant.delete(detalle)
    db_tenant.flush()
    _agregar_detalles(db_tenant, orden, items)
    _confirmar(db_tenant, "No se pudo actualizar la orden de compra")
    return _cargar_orden(db_tenant, orden_id, institucion_id)


def emitir_orden_compra(
    db_tenant: Session, orden_id: int, identidad: IdentidadAutenticada | None
) -> OrdenCompra:
    """Emite el borrador y congela su plan de cobertura (AC-3/AC-4, DT-5).

    Conserva las validaciones de la 020 (`Borrador`, detalles y productos
    activos) y, en la misma transaccion del cambio a `Emitida`:

    1. Bloquea con `FOR UPDATE` los pedidos `EnCurso` de la sede que demandan
       los productos de la OC (solo PostgreSQL; SQLite lo ignora).
    2. Ejecuta `_simular_claves` con las cantidades de `detalle_orden_compra`,
       que resta el plan pendiente (`Emitida` + `Facturada`) y el stock parcial.
    3. Inserta una fila por pedido/producto con `asignada > 0`; el `faltante`
       es la foto del hueco que dejo esta OC.

    Sin pedidos o sin necesidad neta la emision es exitosa con plan vacio. Si
    algo falla no se persiste ninguna fila.
    """
    institucion_id = _institucion_del_actor(db_tenant, identidad)
    orden = _cargar_orden(db_tenant, orden_id, institucion_id)
    if orden.estado != _BORRADOR:
        raise _conflicto("Solo se puede emitir una orden en estado Borrador")
    if not orden.detalles:
        raise _conflicto("La orden no tiene items para emitir")
    for detalle in orden.detalles:
        _producto_activo(db_tenant, detalle.producto_id, institucion_id)

    cantidades_oc = {
        (orden.sede_id, detalle.producto_id): detalle.cantidad_solicitada
        for detalle in orden.detalles
    }
    simulaciones = _simular_claves(
        db_tenant,
        institucion_id,
        cantidades_oc.keys(),
        cantidades_oc=cantidades_oc,
        bloquear=True,
    )
    instante = datetime.utcnow()
    for clave, filas in simulaciones.items():
        producto_id = clave[1]
        for fila in filas:
            if fila.asignada <= 0:
                continue
            db_tenant.add(
                OrdenCompraTicket(
                    institucion_id=institucion_id,
                    orden_compra_id=orden.orden_compra_id,
                    ticket_id=fila.ticket_id,
                    producto_id=producto_id,
                    cantidad_asignada=fila.asignada,
                    cantidad_faltante=fila.faltante,
                    fecha_asignacion=instante,
                )
            )
    db_tenant.flush()

    orden.estado = _EMITIDA
    orden.numero_oc = (
        f"OC-{datetime.utcnow().year:04d}-{orden.orden_compra_id:06d}"
    )
    orden.fecha_emision = instante
    _confirmar(db_tenant, "No se pudo emitir la orden de compra")
    return _cargar_orden(db_tenant, orden_id, institucion_id)


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
