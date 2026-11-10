"""Tests de la Feature 021: cobertura automatica de pedidos por OC.

La suite ordinaria corre sobre SQLite en memoria. Las pruebas de esquemas,
FKs compuestas y concurrencia de emision viven en
`tests/test_cobertura_postgres_021.py` (gated PostgreSQL 16).

Seam bajo prueba: las funciones publicas de `app.services.compra_service` y
`app.services.ticket_service`, que son las que los endpoints cablean. Las
aserciones leen lo persistido con una sesion nueva para no confundir "el
servicio muto el ORM" con "la transaccion quedo confirmada".
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.models import (
    DetalleOrdenCompra,
    DetalleTicket,
    HistorialTransicionTicket,
    OrdenCompra,
    OrdenCompraTicket,
    Prioridad,
    ProveedorControl,
    Sede,
    StockSede,
    Ticket,
)
from app.core import capacidades, permisos
from app.schemas.compra_schema import (
    CoberturaPreviewSolicitud,
    DetalleOrdenCompraCrear,
    FacturaCompraRegistrar,
    OrdenCompraCrear,
)
from app.services import compra_service, ticket_service

from tests.api._soporte_ciclo_vida_013 import sembrar_ticket
from tests.api._soporte_ciclo_vida_catalogo_014 import (
    CORREO_GATING,
    cliente_de_rol,
    fijar_stock_sede,
    marcar_producto,
    sembrar_contexto_capacidades,
    sembrar_mundo_014,
)
from tests.api._soporte_sede_011 import identidad, sesion

# ---------------------------------------------------------------------------
# Mundo de prueba
# ---------------------------------------------------------------------------


@pytest.fixture
def mundo(motor, dos_instituciones):
    """Sede, stock base y catalogo de estados de la 013 sobre dos instituciones."""
    return sembrar_mundo_014(motor, dos_instituciones)


def _admin(datos):
    return identidad(
        "Administrador", datos["departamento_id"], datos["usuario_id"]
    )


def _bodeguero(datos):
    return identidad(
        "Bodeguero",
        datos["departamento_id"],
        datos["usuarios_inst01"]["Bodeguero"],
        sede_id=datos["sede_id"],
    )


@contextmanager
def _sesiones(motor):
    """Dos sesiones sobre el mismo motor (control y tenant en SQLite)."""
    Fabrica = sessionmaker(autocommit=False, autoflush=False, bind=motor)
    db_control = Fabrica()
    db_tenant = Fabrica()
    try:
        yield db_control, db_tenant
    finally:
        db_control.close()
        db_tenant.close()


def _crear_proveedor_control(
    motor, *, rut: str = "96.000.000-1", razon_social: str = "Proveedor 021"
) -> int:
    """Inserta un proveedor directamente en el catalogo global de prueba."""
    with sesion(motor) as db:
        fila = ProveedorControl(
            rut=rut, razon_social=razon_social, activo=True
        )
        db.add(fila)
        db.commit()
        db.refresh(fila)
        return fila.proveedor_id


def _crear_orden(
    motor, mundo, *, proveedor_id: int, cantidad: int = 3, producto_id=None
) -> int:
    """Crea una OC en Borrador por el servicio y devuelve su id."""
    with _sesiones(motor) as (db_control, db_tenant):
        orden = compra_service.crear_orden_compra(
            db_tenant,
            db_control,
            OrdenCompraCrear(
                sede_id=mundo["sede_id"],
                proveedor_id=proveedor_id,
                items=[
                    DetalleOrdenCompraCrear(
                        producto_id=producto_id or mundo["producto_id"],
                        cantidad_solicitada=cantidad,
                        precio_unitario=Decimal("2.50"),
                    )
                ],
            ),
            _admin(mundo),
        )
        return orden.orden_compra_id


def _emitir(motor, mundo, orden_id: int):
    with _sesiones(motor) as (_db_control, db_tenant):
        return compra_service.emitir_orden_compra(
            db_tenant, orden_id, _admin(mundo)
        )


def _facturar(motor, mundo, orden_id: int, numero: str):
    with _sesiones(motor) as (_db_control, db_tenant):
        return compra_service.registrar_o_editar_factura(
            db_tenant,
            orden_id,
            FacturaCompraRegistrar(
                numero_factura=numero,
                fecha_factura=date.today(),
                monto_total=Decimal("100.00"),
            ),
            _admin(mundo),
        )


def _leer_orden(motor, orden_id: int) -> OrdenCompra:
    with sesion(motor) as db:
        orden = db.get(OrdenCompra, orden_id)
        assert orden is not None
        _ = orden.detalles, orden.proveedor, orden.sede, orden.plan
        return orden


def _plan(motor, orden_id: int) -> list[OrdenCompraTicket]:
    with sesion(motor) as db:
        return list(
            db.execute(
                select(OrdenCompraTicket)
                .where(OrdenCompraTicket.orden_compra_id == orden_id)
                .order_by(OrdenCompraTicket.orden_compra_ticket_id)
            )
            .scalars()
            .all()
        )


# ---------------------------------------------------------------------------
# T2: modelos
# ---------------------------------------------------------------------------


def test_modelo_orden_compra_ticket_expone_plan_y_historial_enlaza_oc(motor, mundo):
    """T2: el plan se lee desde la OC y el historial admite `orden_compra_id`."""
    proveedor_id = _crear_proveedor_control(motor)
    ticket_id = sembrar_ticket(
        motor,
        mundo,
        estado_id=mundo["estados"]["EnCurso"],
        cantidad=5,
    )
    orden_id = _crear_orden(motor, mundo, proveedor_id=proveedor_id, cantidad=3)

    with sesion(motor) as db:
        db.add(
            OrdenCompraTicket(
                institucion_id=mundo["institucion_id"],
                orden_compra_id=orden_id,
                ticket_id=ticket_id,
                producto_id=mundo["producto_id"],
                cantidad_asignada=3,
                cantidad_faltante=2,
            )
        )
        db.add(
            HistorialTransicionTicket(
                ticket_id=ticket_id,
                estado_origen_id=mundo["estados"]["EnCurso"],
                estado_destino_id=mundo["estados"]["EnCurso"],
                usuario_id=mundo["usuarios_inst01"]["Bodeguero"],
                motivo="Desbloqueo por recepcion de compra",
                orden_compra_id=orden_id,
            )
        )
        db.commit()

    leida = _leer_orden(motor, orden_id)
    assert len(leida.plan) == 1
    assert leida.plan[0].ticket_id == ticket_id
    assert leida.plan[0].cantidad_asignada == 3
    assert leida.plan[0].cantidad_faltante == 2

    with sesion(motor) as db:
        historial = db.execute(
            select(HistorialTransicionTicket).where(
                HistorialTransicionTicket.ticket_id == ticket_id
            )
        ).scalars().one()
        assert historial.orden_compra_id == orden_id
        assert historial.orden_compra.orden_compra_id == orden_id


# ---------------------------------------------------------------------------
# T3: schemas
# ---------------------------------------------------------------------------


def test_preview_solicitud_rechaza_items_vacios_y_cantidades_no_positivas():
    """T3/AC-2: la forma del preview se valida en Pydantic (422 en la ruta)."""
    from pydantic import ValidationError

    from app.schemas.compra_schema import CoberturaPreviewSolicitud

    with pytest.raises(ValidationError):
        CoberturaPreviewSolicitud(sede_id=1, items=[])
    with pytest.raises(ValidationError):
        CoberturaPreviewSolicitud(
            sede_id=1, items=[{"producto_id": 1, "cantidad_solicitada": 0}]
        )
    with pytest.raises(ValidationError):
        CoberturaPreviewSolicitud(
            sede_id=0, items=[{"producto_id": 1, "cantidad_solicitada": 1}]
        )

    valida = CoberturaPreviewSolicitud(
        sede_id=5, items=[{"producto_id": 2, "cantidad_solicitada": 3}]
    )
    assert valida.sede_id == 5
    assert valida.items[0].producto_id == 2
    assert valida.items[0].cantidad_solicitada == 3


def test_necesidad_agrega_comprometido_borrador_y_tickets_sin_romper_la_020():
    """T3/AC-1: los campos nuevos son aditivos y arrancan en cero."""
    from app.schemas.compra_schema import NecesidadReabastecimiento

    base = NecesidadReabastecimiento(
        sede_id=1,
        sede_nombre="Sede",
        producto_id=2,
        nombre="Lapiz",
        stock_actual=3,
        stock_minimo=5,
        demanda_tickets=4,
        sugerido=2,
    )
    assert base.stock_comprometido == 0
    assert base.stock_borrador == 0
    assert base.tickets == []


def test_orden_compra_respuesta_serializa_el_plan_y_conserva_sus_campos():
    """T3/AC-4: `plan` se agrega sin perder detalles, factura ni total."""
    from datetime import datetime
    from decimal import Decimal

    from app.schemas.compra_schema import (
        OrdenCompraRespuesta,
        PlanOrdenCompraRespuesta,
    )

    plan = PlanOrdenCompraRespuesta(
        orden_compra_ticket_id=1,
        orden_compra_id=2,
        ticket_id=3,
        producto_id=4,
        cantidad_asignada=5,
        cantidad_faltante=1,
        fecha_asignacion=datetime(2026, 11, 7, 10, 0, 0),
        asunto="Pedido de utiles",
        estado_nombre="EnCurso",
        prioridad_nombre="Alta",
        solicitante_nombre="Ana",
        solicitante_apellido="Perez",
        fecha_creacion=datetime(2026, 11, 7, 8, 30, 0),
        producto_nombre="Lapiz",
    )
    respuesta = OrdenCompraRespuesta(
        orden_compra_id=2,
        institucion_id="INST-001",
        sede_id=1,
        proveedor_id=9,
        estado="Emitida",
        total=Decimal("12.50"),
        fecha_creacion=datetime(2026, 11, 7, 9, 0, 0),
        plan=[plan],
    )
    datos = respuesta.model_dump()
    assert datos["plan"][0]["cantidad_asignada"] == 5
    assert datos["plan"][0]["cantidad_faltante"] == 1
    assert datos["plan"][0]["producto_nombre"] == "Lapiz"
    # Campos que ya consumia la 020 siguen presentes.
    assert datos["factura"] is None
    assert datos["detalles"] == []
    assert datos["numero_oc"] is None


def test_detalle_pedido_expone_asignaciones_cadena_e_historial_con_oc():
    """T3/AC-5/AC-6: el detalle y el historial suman campos resueltos."""
    from datetime import datetime

    from app.schemas.ticket_schema import (
        AsignacionTicketRespuesta,
        CadenaProductoTicketRespuesta,
        HistorialTransicionRespuesta,
        TicketDetalleRespuesta,
    )

    instante = datetime(2026, 11, 7, 10, 0, 0)
    detalle = TicketDetalleRespuesta(
        ticket_id=1,
        usuario_id=2,
        prioridad_id=1,
        estado_id=1,
        asunto="Pedido",
        fecha_creacion=instante,
        asignaciones=[
            AsignacionTicketRespuesta(
                orden_compra_ticket_id=1,
                orden_compra_id=2,
                numero_oc="OC-2026-000002",
                estado_orden="Cancelada",
                producto_id=3,
                producto_nombre="Lapiz",
                cantidad_asignada=2,
                cantidad_faltante=1,
                fecha_asignacion=instante,
            )
        ],
        cadena_productos=[
            CadenaProductoTicketRespuesta(
                producto_id=3,
                producto_nombre="Lapiz",
                solicitado=5,
                comprado=2,
                recibido=0,
                entregado=0,
                faltante=3,
            )
        ],
    )
    assert detalle.asignaciones[0].estado_orden == "Cancelada"
    assert detalle.cadena_productos[0].faltante == 3
    # Campos de la 013/020 intactos.
    assert detalle.stock_disponible is False
    assert detalle.detalles == []

    historial = HistorialTransicionRespuesta(
        historial_transicion_id=1,
        ticket_id=1,
        estado_destino_id=1,
        usuario_id=2,
        fecha_transicion=instante,
        orden_compra_id=2,
        numero_oc="OC-2026-000002",
    )
    assert historial.orden_compra_id == 2
    assert historial.numero_oc == "OC-2026-000002"
    assert historial.estado_origen_id is None


# ---------------------------------------------------------------------------
# T4: simulacion de cobertura y necesidades enriquecidas
# ---------------------------------------------------------------------------

_AUSENTE = object()


def _crear_prioridad_021(motor, nombre: str) -> int:
    with sesion(motor) as db:
        fila = Prioridad(nombre=nombre, descripcion="Prioridad de prueba 021")
        db.add(fila)
        db.commit()
        db.refresh(fila)
        return fila.prioridad_id


def _crear_ticket_021(
    motor,
    mundo,
    *,
    estado: str,
    cantidad: int,
    producto_id: int | None = None,
    prioridad_id: int | None = None,
    sede_id=_AUSENTE,
    asunto: str = "Pedido sembrado para la cobertura 021",
) -> int:
    """Inserta un pedido con un unico detalle, en cualquier estado y sede."""
    with sesion(motor) as db:
        ticket = Ticket(
            usuario_id=mundo["usuarios_inst01"]["Solicitante"],
            prioridad_id=prioridad_id or mundo["prioridad_id"],
            estado_id=mundo["estados"][estado],
            asunto=asunto,
            descripcion="Pedido de prueba de la cobertura automatica.",
            institucion_id=mundo["institucion_id"],
            sede_id=mundo["sede_id"] if sede_id is _AUSENTE else sede_id,
        )
        db.add(ticket)
        db.flush()
        db.add(
            DetalleTicket(
                ticket_id=ticket.ticket_id,
                producto_id=producto_id or mundo["producto_id"],
                cantidad_solicitada=cantidad,
                cantidad_entregada=0,
                institucion_id=mundo["institucion_id"],
            )
        )
        db.commit()
        db.refresh(ticket)
        return ticket.ticket_id


def _crear_orden_con_detalle(
    motor,
    mundo,
    *,
    proveedor_id: int,
    cantidad: int,
    estado: str = "Emitida",
    producto_id: int | None = None,
) -> int:
    """Crea una OC con una linea, sin pasar por el servicio, y devuelve su id."""
    producto = producto_id or mundo["producto_id"]
    with sesion(motor) as db:
        orden = OrdenCompra(
            institucion_id=mundo["institucion_id"],
            sede_id=mundo["sede_id"],
            proveedor_id=proveedor_id,
            estado=estado,
            total=Decimal("0.00"),
        )
        db.add(orden)
        db.flush()
        if estado != "Borrador":
            orden.numero_oc = f"OC-2026-{orden.orden_compra_id:06d}"
        db.add(
            DetalleOrdenCompra(
                orden_compra_id=orden.orden_compra_id,
                institucion_id=mundo["institucion_id"],
                producto_id=producto,
                cantidad_solicitada=cantidad,
                precio_unitario=Decimal("1.00"),
            )
        )
        db.commit()
        db.refresh(orden)
        return orden.orden_compra_id


def _agregar_plan_021(
    motor,
    mundo,
    orden_id: int,
    *,
    ticket_id: int,
    cantidad_asignada: int,
    cantidad_faltante: int,
    producto_id: int | None = None,
) -> None:
    with sesion(motor) as db:
        db.add(
            OrdenCompraTicket(
                institucion_id=mundo["institucion_id"],
                orden_compra_id=orden_id,
                ticket_id=ticket_id,
                producto_id=producto_id or mundo["producto_id"],
                cantidad_asignada=cantidad_asignada,
                cantidad_faltante=cantidad_faltante,
            )
        )
        db.commit()


def _simular(motor, mundo, cantidad_oc: int):
    clave = (mundo["sede_id"], mundo["producto_id"])
    with sesion(motor) as db:
        resultado = compra_service._simular_claves(
            db,
            mundo["institucion_id"],
            {clave},
            cantidades_oc={clave: cantidad_oc},
        )
    return resultado[clave]


def test_simulacion_asigna_por_prioridad_y_fifo_con_faltante_parcial(motor, mundo):
    """T4/AC-3/AC-9: prioridad manda sobre FIFO y la OC cubre en parte."""
    fijar_stock_sede(motor, mundo, mundo["producto_id"], 0)
    alta = _crear_prioridad_021(motor, "ALTA 021")
    baja = _crear_prioridad_021(motor, "BAJA 021")
    # El pedido de baja prioridad se crea primero: FIFO no gana a prioridad.
    pedido_baja = _crear_ticket_021(
        motor, mundo, estado="EnCurso", cantidad=4, prioridad_id=baja
    )
    pedido_alta = _crear_ticket_021(
        motor, mundo, estado="EnCurso", cantidad=5, prioridad_id=alta
    )

    filas = _simular(motor, mundo, 6)

    assert [fila.ticket_id for fila in filas] == [pedido_alta, pedido_baja]
    assert (filas[0].solicitado, filas[0].asignada, filas[0].faltante) == (5, 5, 0)
    assert filas[0].cobertura == "total"
    assert (filas[1].solicitado, filas[1].asignada, filas[1].faltante) == (4, 1, 3)
    assert filas[1].cobertura == "parcial"


def test_simulacion_reparte_stock_parcial_antes_de_la_compra(motor, mundo):
    """T4/D-4: el stock cubre parte de un pedido y la compra solo la necesidad neta."""
    fijar_stock_sede(motor, mundo, mundo["producto_id"], 3)
    primero = _crear_ticket_021(motor, mundo, estado="EnCurso", cantidad=5)
    segundo = _crear_ticket_021(motor, mundo, estado="EnCurso", cantidad=2)

    filas = _simular(motor, mundo, 10)

    assert [fila.ticket_id for fila in filas] == [primero, segundo]
    assert (filas[0].cubierto_stock, filas[0].necesidad, filas[0].asignada) == (3, 2, 2)
    assert filas[0].faltante == 0
    assert (filas[1].cubierto_stock, filas[1].necesidad, filas[1].asignada) == (0, 2, 2)
    assert filas[1].faltante == 0


def test_simulacion_resta_plan_previo_y_no_resta_oc_recibida(motor, mundo):
    """T4/D-4: `Emitida` resta el tramo; `Recibida` ya vive en el stock."""
    fijar_stock_sede(motor, mundo, mundo["producto_id"], 0)
    proveedor_id = _crear_proveedor_control(motor, rut="96.021.010-1")
    pedido = _crear_ticket_021(motor, mundo, estado="EnCurso", cantidad=5)

    emitida = _crear_orden_con_detalle(
        motor, mundo, proveedor_id=proveedor_id, cantidad=2, estado="Emitida"
    )
    _agregar_plan_021(
        motor,
        mundo,
        emitida,
        ticket_id=pedido,
        cantidad_asignada=2,
        cantidad_faltante=3,
    )
    filas = _simular(motor, mundo, 5)
    assert (filas[0].plan_previo, filas[0].necesidad, filas[0].asignada) == (2, 3, 3)
    assert filas[0].faltante == 0

    recibida = _crear_orden_con_detalle(
        motor, mundo, proveedor_id=proveedor_id, cantidad=4, estado="Recibida"
    )
    _agregar_plan_021(
        motor,
        mundo,
        recibida,
        ticket_id=pedido,
        cantidad_asignada=4,
        cantidad_faltante=0,
    )
    filas = _simular(motor, mundo, 5)
    # La recibida no se resta como plan previo: sigue siendo solo 2.
    assert (filas[0].plan_previo, filas[0].necesidad, filas[0].asignada) == (2, 3, 3)


def test_simulacion_excluye_otra_sede_sin_sede_y_estados_no_en_curso(motor, mundo):
    """T4/AC-8: solo pedidos `EnCurso` de la sede de la clave participan."""
    fijar_stock_sede(motor, mundo, mundo["producto_id"], 0)
    with sesion(motor) as db:
        otra_sede = Sede(
            nombre="Otra sede 021",
            institucion_id=mundo["institucion_id"],
        )
        db.add(otra_sede)
        db.commit()
        db.refresh(otra_sede)
        otra_sede_id = otra_sede.sede_id

    incluido = _crear_ticket_021(motor, mundo, estado="EnCurso", cantidad=2)
    _crear_ticket_021(motor, mundo, estado="EnRevision", cantidad=9)
    _crear_ticket_021(motor, mundo, estado="Pendiente", cantidad=9)
    _crear_ticket_021(
        motor, mundo, estado="EnCurso", cantidad=7, sede_id=otra_sede_id
    )
    _crear_ticket_021(motor, mundo, estado="EnCurso", cantidad=8, sede_id=None)

    filas = _simular(motor, mundo, 10)

    assert [fila.ticket_id for fila in filas] == [incluido]
    assert filas[0].solicitado == 2


def test_necesidades_enriquecidas_con_comprometido_borrador_y_pedidos(motor, mundo):
    """T4/AC-1: comprometido y borrador se separan y el sugerido es neto."""
    fijar_stock_sede(motor, mundo, mundo["producto_id"], 0)
    proveedor_id = _crear_proveedor_control(motor, rut="96.021.020-1")
    pedido = _crear_ticket_021(motor, mundo, estado="EnCurso", cantidad=4)
    _crear_ticket_021(motor, mundo, estado="Pendiente", cantidad=9)
    _crear_orden_con_detalle(
        motor, mundo, proveedor_id=proveedor_id, cantidad=3, estado="Emitida"
    )
    _crear_orden_con_detalle(
        motor, mundo, proveedor_id=proveedor_id, cantidad=2, estado="Borrador"
    )

    with sesion(motor) as db:
        necesidades = compra_service.listar_necesidades_reabastecimiento(
            db, mundo["institucion_id"], mundo["sede_id"]
        )

    fila = next(
        necesidad
        for necesidad in necesidades
        if necesidad.producto_id == mundo["producto_id"]
    )
    assert fila.stock_actual == 0
    assert fila.stock_minimo == 10
    assert fila.demanda_tickets == 4
    assert fila.stock_comprometido == 3
    assert fila.stock_borrador == 2
    assert fila.sugerido == 11  # 10 + 4 - 0 - 3; el borrador no descuenta
    assert [ticket.ticket_id for ticket in fila.tickets] == [pedido]
    assert fila.tickets[0].cantidad_solicitada == 4
    assert fila.tickets[0].cantidad_cubierta == 0
    assert fila.tickets[0].cantidad_faltante == 4


def test_necesidades_con_sede_ajena_devuelve_lista_vacia(motor, mundo):
    """T4/AC-1: la sede invalida es filtro de lista, no 404."""
    with sesion(motor) as db:
        assert (
            compra_service.listar_necesidades_reabastecimiento(
                db, mundo["institucion_id"], 999_999
            )
            == []
        )


def test_orden_a_respuesta_resuelve_el_resumen_del_plan(motor, mundo):
    """T4/DT-8: el DTO de la OC adjunta nombres que no son columnas."""
    fijar_stock_sede(motor, mundo, mundo["producto_id"], 0)
    proveedor_id = _crear_proveedor_control(motor, rut="96.021.030-1")
    pedido = _crear_ticket_021(
        motor, mundo, estado="EnCurso", cantidad=4, asunto="Pedido del plan"
    )
    orden_id = _crear_orden_con_detalle(
        motor, mundo, proveedor_id=proveedor_id, cantidad=2, estado="Emitida"
    )
    _agregar_plan_021(
        motor,
        mundo,
        orden_id,
        ticket_id=pedido,
        cantidad_asignada=2,
        cantidad_faltante=2,
    )

    with sesion(motor) as db:
        orden = db.get(OrdenCompra, orden_id)
        respuesta = compra_service.orden_a_respuesta(orden)

    assert respuesta.estado == "Emitida"
    assert len(respuesta.plan) == 1
    fila = respuesta.plan[0]
    assert fila.ticket_id == pedido
    assert fila.asunto == "Pedido del plan"
    assert fila.estado_nombre == "EnCurso"
    assert fila.solicitante_nombre == "Solicitante"
    assert fila.solicitante_apellido == "Inst01"
    assert fila.prioridad_nombre == "ALTA"
    assert fila.producto_nombre == "Cuaderno linedado"
    assert (fila.cantidad_asignada, fila.cantidad_faltante) == (2, 2)


# ---------------------------------------------------------------------------
# T5: preview de cobertura
# ---------------------------------------------------------------------------


def _previsualizar(motor, mundo, items, *, sede_id=None, identidad_actor=None):
    from app.schemas.compra_schema import CoberturaPreviewItem

    datos = CoberturaPreviewSolicitud(
        sede_id=sede_id if sede_id is not None else mundo["sede_id"],
        items=[
            CoberturaPreviewItem(producto_id=producto, cantidad_solicitada=cantidad)
            for producto, cantidad in items
        ],
    )
    with sesion(motor) as db:
        return compra_service.previsualizar_cobertura(
            db, datos, identidad_actor or _admin(mundo)
        )


def test_preview_reparte_la_compra_y_no_persiste_ni_reserva(motor, mundo):
    """T5/AC-2/AC-9: mismo algoritmo que la emision, sin escribir ni reservar."""
    fijar_stock_sede(motor, mundo, mundo["producto_id"], 0)
    alta = _crear_prioridad_021(motor, "ALTA PREVIEW")
    baja = _crear_prioridad_021(motor, "BAJA PREVIEW")
    pedido_baja = _crear_ticket_021(
        motor, mundo, estado="EnCurso", cantidad=4, prioridad_id=baja
    )
    pedido_alta = _crear_ticket_021(
        motor, mundo, estado="EnCurso", cantidad=5, prioridad_id=alta
    )

    respuesta = _previsualizar(motor, mundo, [(mundo["producto_id"], 6)])

    assert respuesta.sede_id == mundo["sede_id"]
    assert len(respuesta.productos) == 1
    producto = respuesta.productos[0]
    assert producto.cantidad_simulada == 6
    assert producto.demanda_total == 9
    assert producto.cubierto_previo == 0
    assert producto.asignado == 6
    assert producto.faltante == 3
    assert producto.sin_asignar == 0
    assert [ticket.ticket_id for ticket in producto.tickets] == [
        pedido_alta,
        pedido_baja,
    ]
    assert (
        producto.tickets[0].solicitado,
        producto.tickets[0].cubierto_plan,
        producto.tickets[0].cubierto_stock,
        producto.tickets[0].necesidad,
        producto.tickets[0].asignada,
        producto.tickets[0].faltante,
    ) == (5, 0, 0, 5, 5, 0)
    assert producto.tickets[0].cobertura == "total"
    assert (
        producto.tickets[1].solicitado,
        producto.tickets[1].asignada,
        producto.tickets[1].faltante,
    ) == (4, 1, 3)
    assert producto.tickets[1].cobertura == "parcial"

    # No persiste filas del plan ni reserva stock.
    with sesion(motor) as db:
        assert db.execute(select(OrdenCompraTicket)).scalars().all() == []
        assert (
            db.execute(
                select(StockSede.stock_actual).where(
                    StockSede.sede_id == mundo["sede_id"],
                    StockSede.producto_id == mundo["producto_id"],
                )
            ).scalar_one()
            == 0
        )


def test_preview_es_idempotente(motor, mundo):
    """T5/AC-2: dos llamadas con el mismo estado devuelven lo mismo."""
    fijar_stock_sede(motor, mundo, mundo["producto_id"], 1)
    _crear_ticket_021(motor, mundo, estado="EnCurso", cantidad=3)
    primera = _previsualizar(motor, mundo, [(mundo["producto_id"], 4)])
    segunda = _previsualizar(motor, mundo, [(mundo["producto_id"], 4)])
    assert primera.model_dump() == segunda.model_dump()


def test_preview_sin_demanda_deja_la_compra_sin_asignar(motor, mundo):
    """T5/AC-2: sin pedidos no hay asignacion y la compra queda sin asignar."""
    fijar_stock_sede(motor, mundo, mundo["producto_id"], 0)
    respuesta = _previsualizar(motor, mundo, [(mundo["producto_id"], 3)])
    producto = respuesta.productos[0]
    assert producto.demanda_total == 0
    assert producto.cubierto_previo == 0
    assert producto.asignado == 0
    assert producto.faltante == 0
    assert producto.sin_asignar == 3
    assert producto.tickets == []


def test_preview_rechaza_sede_inexistente_y_ajena_con_404(motor, mundo):
    """T5/AC-2: la sede concreta se valida, no es filtro de lista."""
    with sesion(motor) as db:
        with pytest.raises(HTTPException) as error:
            compra_service.previsualizar_cobertura(
                db,
                CoberturaPreviewSolicitud(
                    sede_id=999_999,
                    items=[
                        {
                            "producto_id": mundo["producto_id"],
                            "cantidad_solicitada": 1,
                        }
                    ],
                ),
                _admin(mundo),
            )
    assert error.value.status_code == 404

    with sesion(motor) as db:
        sede_ajena = Sede(
            nombre="Sede ajena preview 021", institucion_id=mundo["inst_ajena"]
        )
        db.add(sede_ajena)
        db.commit()
        db.refresh(sede_ajena)
        sede_ajena_id = sede_ajena.sede_id

    with sesion(motor) as db:
        with pytest.raises(HTTPException) as error:
            compra_service.previsualizar_cobertura(
                db,
                CoberturaPreviewSolicitud(
                    sede_id=sede_ajena_id,
                    items=[
                        {
                            "producto_id": mundo["producto_id"],
                            "cantidad_solicitada": 1,
                        }
                    ],
                ),
                _admin(mundo),
            )
    assert error.value.status_code == 404


def test_preview_rechaza_producto_ajeno_inexistente_inactivo_y_repetido(motor, mundo):
    """T5/AC-2: 404 para ajeno/inexistente; 409 para inactivo o repetido."""
    with sesion(motor) as db:
        with pytest.raises(HTTPException) as ajeno:
            compra_service.previsualizar_cobertura(
                db,
                CoberturaPreviewSolicitud(
                    sede_id=mundo["sede_id"],
                    items=[
                        {
                            "producto_id": mundo["producto_homonimo_ajeno_id"],
                            "cantidad_solicitada": 1,
                        }
                    ],
                ),
                _admin(mundo),
            )
        with pytest.raises(HTTPException) as inexistente:
            compra_service.previsualizar_cobertura(
                db,
                CoberturaPreviewSolicitud(
                    sede_id=mundo["sede_id"],
                    items=[{"producto_id": 999_999, "cantidad_solicitada": 1}],
                ),
                _admin(mundo),
            )
        with pytest.raises(HTTPException) as repetido:
            compra_service.previsualizar_cobertura(
                db,
                CoberturaPreviewSolicitud(
                    sede_id=mundo["sede_id"],
                    items=[
                        {
                            "producto_id": mundo["producto_id"],
                            "cantidad_solicitada": 1,
                        },
                        {
                            "producto_id": mundo["producto_id"],
                            "cantidad_solicitada": 2,
                        },
                    ],
                ),
                _admin(mundo),
            )
    assert ajeno.value.status_code == 404
    assert inexistente.value.status_code == 404
    assert repetido.value.status_code == 409

    marcar_producto(motor, mundo["producto_id"], False)
    with sesion(motor) as db:
        with pytest.raises(HTTPException) as inactivo:
            compra_service.previsualizar_cobertura(
                db,
                CoberturaPreviewSolicitud(
                    sede_id=mundo["sede_id"],
                    items=[
                        {
                            "producto_id": mundo["producto_id"],
                            "cantidad_solicitada": 1,
                        }
                    ],
                ),
                _admin(mundo),
            )
    assert inactivo.value.status_code == 409


def test_preview_http_responde_200_con_la_forma_documentada(motor, mundo):
    """T5/AC-2/AC-12: el endpoint publica la simulacion sin persistir."""
    fijar_stock_sede(motor, mundo, mundo["producto_id"], 0)
    pedido = _crear_ticket_021(motor, mundo, estado="EnCurso", cantidad=3)

    with cliente_de_rol(motor, mundo, "Administrador") as cliente_http:
        respuesta = cliente_http.post(
            "/api/v1/compras/cobertura/preview",
            json={
                "sede_id": mundo["sede_id"],
                "items": [
                    {
                        "producto_id": mundo["producto_id"],
                        "cantidad_solicitada": 2,
                    }
                ],
            },
        )
    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["sede_id"] == mundo["sede_id"]
    assert cuerpo["sede_nombre"] == "Sede Base"
    producto = cuerpo["productos"][0]
    assert producto["producto_id"] == mundo["producto_id"]
    assert producto["cantidad_simulada"] == 2
    assert producto["asignado"] == 2
    assert producto["faltante"] == 1
    assert producto["sin_asignar"] == 0
    assert producto["tickets"][0]["ticket_id"] == pedido
    assert producto["tickets"][0]["cobertura"] == "parcial"


@pytest.mark.parametrize("rol", ["Bodeguero", "Solicitante", "Superadmin"])
def test_preview_http_deniega_roles_no_administradores(motor, mundo, rol):
    """T5/AC-10: solo el Administrador Institucional simula la cobertura."""
    with cliente_de_rol(motor, mundo, rol) as cliente_http:
        respuesta = cliente_http.post(
            "/api/v1/compras/cobertura/preview",
            json={
                "sede_id": mundo["sede_id"],
                "items": [
                    {
                        "producto_id": mundo["producto_id"],
                        "cantidad_solicitada": 1,
                    }
                ],
            },
        )
    assert respuesta.status_code == 403, respuesta.text


def test_preview_http_rechaza_cuerpo_invalido_con_422(motor, mundo):
    """T5/AC-2: items vacios o cantidades no positivas son 422 de forma."""
    with cliente_de_rol(motor, mundo, "Administrador") as cliente_http:
        vacio = cliente_http.post(
            "/api/v1/compras/cobertura/preview",
            json={"sede_id": mundo["sede_id"], "items": []},
        )
        cero = cliente_http.post(
            "/api/v1/compras/cobertura/preview",
            json={
                "sede_id": mundo["sede_id"],
                "items": [
                    {
                        "producto_id": mundo["producto_id"],
                        "cantidad_solicitada": 0,
                    }
                ],
            },
        )
    assert vacio.status_code == 422, vacio.text
    assert cero.status_code == 422, cero.text


# ---------------------------------------------------------------------------
# T6: emision con plan congelado y cancelacion
# ---------------------------------------------------------------------------


def test_emision_persiste_el_plan_para_los_pedidos_con_asignacion(motor, mundo):
    """T6/AC-3/AC-4: una fila por pedido/producto con asignada > 0."""
    fijar_stock_sede(motor, mundo, mundo["producto_id"], 0)
    alta = _crear_prioridad_021(motor, "ALTA EMISION")
    baja = _crear_prioridad_021(motor, "BAJA EMISION")
    pedido_alta = _crear_ticket_021(
        motor, mundo, estado="EnCurso", cantidad=5, prioridad_id=alta
    )
    pedido_baja = _crear_ticket_021(
        motor, mundo, estado="EnCurso", cantidad=4, prioridad_id=baja
    )
    pedido_sin_cupo = _crear_ticket_021(
        motor, mundo, estado="EnCurso", cantidad=2, prioridad_id=baja
    )
    proveedor_id = _crear_proveedor_control(motor, rut="96.021.040-1")
    orden_id = _crear_orden(
        motor, mundo, proveedor_id=proveedor_id, cantidad=6
    )

    orden = _emitir(motor, mundo, orden_id)

    assert orden.estado == "Emitida"
    assert orden.numero_oc == f"OC-2026-{orden_id:06d}"
    assert orden.fecha_emision is not None
    filas = _plan(motor, orden_id)
    assert [
        (fila.ticket_id, fila.cantidad_asignada, fila.cantidad_faltante)
        for fila in filas
    ] == [
        (pedido_alta, 5, 0),
        (pedido_baja, 1, 3),
    ]
    assert pedido_sin_cupo not in {fila.ticket_id for fila in filas}
    assert all(fila.institucion_id == mundo["institucion_id"] for fila in filas)
    assert all(fila.producto_id == mundo["producto_id"] for fila in filas)
    assert all(fila.fecha_asignacion is not None for fila in filas)


def test_emision_sin_demanda_emite_con_plan_vacio(motor, mundo):
    """T6/AC-3: una OC sin pedidos se emite igual y no inventa plan."""
    fijar_stock_sede(motor, mundo, mundo["producto_id"], 0)
    proveedor_id = _crear_proveedor_control(motor, rut="96.021.041-1")
    orden_id = _crear_orden(
        motor, mundo, proveedor_id=proveedor_id, cantidad=3
    )

    orden = _emitir(motor, mundo, orden_id)

    assert orden.estado == "Emitida"
    assert _plan(motor, orden_id) == []


def test_emision_resta_el_plan_previo_y_rechaza_la_segunda_emision(motor, mundo):
    """T6/AC-3/AC-7: dos OC se reparten la necesidad; re-emitir es 409."""
    fijar_stock_sede(motor, mundo, mundo["producto_id"], 0)
    pedido = _crear_ticket_021(motor, mundo, estado="EnCurso", cantidad=5)
    proveedor_id = _crear_proveedor_control(motor, rut="96.021.042-1")

    primera_id = _crear_orden(
        motor, mundo, proveedor_id=proveedor_id, cantidad=2
    )
    _emitir(motor, mundo, primera_id)
    segunda_id = _crear_orden(
        motor, mundo, proveedor_id=proveedor_id, cantidad=3
    )
    _emitir(motor, mundo, segunda_id)

    assert [
        (fila.ticket_id, fila.cantidad_asignada, fila.cantidad_faltante)
        for fila in _plan(motor, primera_id)
    ] == [(pedido, 2, 3)]
    assert [
        (fila.ticket_id, fila.cantidad_asignada, fila.cantidad_faltante)
        for fila in _plan(motor, segunda_id)
    ] == [(pedido, 3, 0)]

    with pytest.raises(HTTPException) as error:
        _emitir(motor, mundo, primera_id)
    assert error.value.status_code == 409


def test_plan_congelado_no_cambia_al_facturar_ni_con_pedidos_nuevos(motor, mundo):
    """T6/AC-4/AC-5: el plan es una foto del estado al emitir."""
    fijar_stock_sede(motor, mundo, mundo["producto_id"], 0)
    pedido = _crear_ticket_021(motor, mundo, estado="EnCurso", cantidad=4)
    proveedor_id = _crear_proveedor_control(motor, rut="96.021.043-1")
    orden_id = _crear_orden(
        motor, mundo, proveedor_id=proveedor_id, cantidad=2
    )
    _emitir(motor, mundo, orden_id)
    antes = [
        (fila.ticket_id, fila.cantidad_asignada, fila.cantidad_faltante)
        for fila in _plan(motor, orden_id)
    ]

    _facturar(motor, mundo, orden_id, "FAC-021-CONGELADO")
    _crear_ticket_021(motor, mundo, estado="EnCurso", cantidad=9)

    despues = [
        (fila.ticket_id, fila.cantidad_asignada, fila.cantidad_faltante)
        for fila in _plan(motor, orden_id)
    ]
    assert antes == despues == [(pedido, 2, 2)]
    assert _leer_orden(motor, orden_id).estado == "Facturada"


def test_cancelacion_conserva_el_plan_y_libera_la_cobertura(motor, mundo):
    """T6/AC-7: la OC cancelada deja de cubrir, pero su plan queda auditado."""
    from app.schemas.compra_schema import CancelacionOrdenCompra

    fijar_stock_sede(motor, mundo, mundo["producto_id"], 0)
    pedido = _crear_ticket_021(motor, mundo, estado="EnCurso", cantidad=5)
    proveedor_id = _crear_proveedor_control(motor, rut="96.021.044-1")
    orden_id = _crear_orden(
        motor, mundo, proveedor_id=proveedor_id, cantidad=3
    )
    _emitir(motor, mundo, orden_id)

    with _sesiones(motor) as (_db_control, db_tenant):
        cancelada = compra_service.cancelar_orden_compra(
            db_tenant,
            orden_id,
            CancelacionOrdenCompra(motivo_cancelacion="Proveedor sin stock"),
            _admin(mundo),
        )
    assert cancelada.estado == "Cancelada"
    assert [(fila.ticket_id, fila.cantidad_asignada) for fila in _plan(motor, orden_id)] == [
        (pedido, 3)
    ]

    # La necesidad vuelve a estar viva: la cancelada no se resta como plan.
    filas = _simular(motor, mundo, 4)
    assert (filas[0].plan_previo, filas[0].necesidad, filas[0].asignada) == (
        0,
        5,
        4,
    )
    with sesion(motor) as db:
        necesidades = compra_service.listar_necesidades_reabastecimiento(
            db, mundo["institucion_id"], mundo["sede_id"]
        )
    fila = next(
        necesidad
        for necesidad in necesidades
        if necesidad.producto_id == mundo["producto_id"]
    )
    assert fila.stock_comprometido == 0


def test_emision_http_devuelve_el_plan_y_el_listado_lo_incluye(motor, mundo):
    """T6/DT-8: la respuesta de emision y `GET /compras/ordenes` exponen `plan`."""
    fijar_stock_sede(motor, mundo, mundo["producto_id"], 0)
    pedido = _crear_ticket_021(motor, mundo, estado="EnCurso", cantidad=4)
    proveedor_id = _crear_proveedor_control(motor, rut="96.021.045-1")
    orden_id = _crear_orden(
        motor, mundo, proveedor_id=proveedor_id, cantidad=2
    )

    with cliente_de_rol(motor, mundo, "Administrador") as cliente_http:
        emision = cliente_http.post(
            f"/api/v1/compras/ordenes/{orden_id}/emitir"
        )
        listado = cliente_http.get("/api/v1/compras/ordenes")

    assert emision.status_code == 200, emision.text
    plan = emision.json()["plan"]
    assert len(plan) == 1
    assert plan[0]["ticket_id"] == pedido
    assert plan[0]["cantidad_asignada"] == 2
    assert plan[0]["cantidad_faltante"] == 2
    assert plan[0]["asunto"] is not None
    assert plan[0]["producto_nombre"] == "Cuaderno linedado"

    assert listado.status_code == 200, listado.text
    orden_listada = next(
        orden
        for orden in listado.json()
        if orden["orden_compra_id"] == orden_id
    )
    assert orden_listada["plan"] == plan


# ---------------------------------------------------------------------------
# T7: recepcion - enlace de auditoria en el historial
# ---------------------------------------------------------------------------


def _sembrar_historial_sin_oc(motor, mundo, ticket_id: int) -> int:
    """Inserta la fila de creacion del pedido (sin OC) y devuelve su id."""
    with sesion(motor) as db:
        fila = HistorialTransicionTicket(
            ticket_id=ticket_id,
            estado_origen_id=None,
            estado_destino_id=mundo["estados"]["EnCurso"],
            usuario_id=mundo["usuarios_inst01"]["Solicitante"],
            motivo="Alta del pedido",
        )
        db.add(fila)
        db.commit()
        db.refresh(fila)
        return fila.historial_transicion_id


def test_recepcion_enlaza_la_oc_solo_en_la_fila_de_desbloqueo(motor, mundo):
    """T7/AC-6: la fila `EnCurso -> EnCurso` referencia la OC recepcionada."""
    fijar_stock_sede(motor, mundo, mundo["producto_id"], 0)
    pedido = _crear_ticket_021(motor, mundo, estado="EnCurso", cantidad=3)
    _sembrar_historial_sin_oc(motor, mundo, pedido)
    proveedor_id = _crear_proveedor_control(motor, rut="96.021.046-1")
    orden_id = _crear_orden(
        motor, mundo, proveedor_id=proveedor_id, cantidad=5
    )
    _emitir(motor, mundo, orden_id)
    _facturar(motor, mundo, orden_id, "FAC-021-RECEPCION")

    with _sesiones(motor) as (_db_control, db_tenant):
        respuesta = compra_service.recepcionar_orden_compra(
            db_tenant, orden_id, _bodeguero(mundo)
        )

    assert respuesta.estado == "Recibida"
    assert [ticket.ticket_id for ticket in respuesta.tickets_desbloqueados] == [
        pedido
    ]
    # La recepcion no altera el plan congelado.
    assert [
        (fila.ticket_id, fila.cantidad_asignada) for fila in _plan(motor, orden_id)
    ] == [(pedido, 3)]

    with sesion(motor) as db:
        historial = ticket_service.obtener_historial_ticket(
            db, pedido, _admin(mundo)
        )
    por_motivo = {fila.motivo: fila for fila in historial}
    creacion = por_motivo["Alta del pedido"]
    assert creacion.orden_compra_id is None
    assert creacion.numero_oc is None
    desbloqueo = next(
        fila for fila in historial if fila.orden_compra_id is not None
    )
    assert desbloqueo.orden_compra_id == orden_id
    assert desbloqueo.numero_oc == f"OC-2026-{orden_id:06d}"
    assert desbloqueo.estado_origen_nombre == "EnCurso"
    assert desbloqueo.estado_destino_nombre == "EnCurso"

    # El pedido sigue `EnCurso`: la recepcion no cierra nada.
    assert _leer_orden(motor, orden_id).estado == "Recibida"
    with sesion(motor) as db:
        assert db.get(Ticket, pedido).estado.nombre == "EnCurso"


def test_recepcion_http_historial_expone_numero_oc(motor, mundo):
    """T7/AC-6: el historial del pedido publica la OC que lo desbloqueo."""
    fijar_stock_sede(motor, mundo, mundo["producto_id"], 0)
    pedido = _crear_ticket_021(motor, mundo, estado="EnCurso", cantidad=3)
    proveedor_id = _crear_proveedor_control(motor, rut="96.021.047-1")
    orden_id = _crear_orden(
        motor, mundo, proveedor_id=proveedor_id, cantidad=5
    )
    _emitir(motor, mundo, orden_id)
    _facturar(motor, mundo, orden_id, "FAC-021-HISTORIAL")

    with cliente_de_rol(motor, mundo, "Bodeguero") as cliente_http:
        recepcion = cliente_http.post(
            f"/api/v1/compras/ordenes/{orden_id}/recepcion"
        )
    assert recepcion.status_code == 200, recepcion.text

    with cliente_de_rol(motor, mundo, "Solicitante") as cliente_http:
        historial = cliente_http.get(
            f"/api/v1/tickets/{pedido}/historial"
        )
    assert historial.status_code == 200, historial.text
    filas = historial.json()
    assert len(filas) == 1
    assert filas[0]["orden_compra_id"] == orden_id
    assert filas[0]["numero_oc"] == f"OC-2026-{orden_id:06d}"
    assert filas[0]["estado_destino_nombre"] == "EnCurso"


# ---------------------------------------------------------------------------
# T8: detalle del pedido - asignaciones y cadena por producto
# ---------------------------------------------------------------------------


def _detalle(motor, mundo, ticket_id: int):
    with sesion(motor) as db:
        return ticket_service.obtener_ticket_detalle(db, ticket_id, _admin(mundo))


def test_detalle_expone_asignaciones_y_cadena_por_producto(motor, mundo):
    """T8/AC-5/D-7: comprado incluye lo recibido y el faltante usa el stock."""
    fijar_stock_sede(motor, mundo, mundo["producto_id"], 0)
    pedido = _crear_ticket_021(motor, mundo, estado="EnCurso", cantidad=5)
    proveedor_id = _crear_proveedor_control(motor, rut="96.021.050-1")
    emitida = _crear_orden_con_detalle(
        motor, mundo, proveedor_id=proveedor_id, cantidad=2, estado="Emitida"
    )
    _agregar_plan_021(
        motor, mundo, emitida, ticket_id=pedido, cantidad_asignada=2, cantidad_faltante=3
    )
    recibida = _crear_orden_con_detalle(
        motor, mundo, proveedor_id=proveedor_id, cantidad=3, estado="Recibida"
    )
    _agregar_plan_021(
        motor, mundo, recibida, ticket_id=pedido, cantidad_asignada=3, cantidad_faltante=0
    )
    fijar_stock_sede(motor, mundo, mundo["producto_id"], 3)

    detalle = _detalle(motor, mundo, pedido)

    assert len(detalle.asignaciones) == 2
    por_orden = {fila.orden_compra_id: fila for fila in detalle.asignaciones}
    assert por_orden[emitida].estado_orden == "Emitida"
    assert por_orden[emitida].cantidad_asignada == 2
    assert por_orden[emitida].numero_oc == f"OC-2026-{emitida:06d}"
    assert por_orden[recibida].estado_orden == "Recibida"
    assert por_orden[recibida].producto_nombre == "Cuaderno linedado"

    assert len(detalle.cadena_productos) == 1
    cadena = detalle.cadena_productos[0]
    assert cadena.producto_id == mundo["producto_id"]
    assert cadena.solicitado == 5
    assert cadena.comprado == 5
    assert cadena.recibido == 3
    assert cadena.entregado == 0
    assert cadena.faltante == 0
    # `stock_disponible` de la 020 no se recalcula con el plan.
    assert detalle.stock_disponible is False


def test_detalle_marca_oc_cancelada_y_no_la_suma_a_la_cobertura(motor, mundo):
    """T8/AC-7/D-8: la cancelada se muestra pero no cuenta como comprado."""
    from app.schemas.compra_schema import CancelacionOrdenCompra

    fijar_stock_sede(motor, mundo, mundo["producto_id"], 0)
    pedido = _crear_ticket_021(motor, mundo, estado="EnCurso", cantidad=4)
    proveedor_id = _crear_proveedor_control(motor, rut="96.021.051-1")
    cancelada_id = _crear_orden_con_detalle(
        motor, mundo, proveedor_id=proveedor_id, cantidad=3, estado="Emitida"
    )
    _agregar_plan_021(
        motor,
        mundo,
        cancelada_id,
        ticket_id=pedido,
        cantidad_asignada=3,
        cantidad_faltante=1,
    )
    with _sesiones(motor) as (_db_control, db_tenant):
        compra_service.cancelar_orden_compra(
            db_tenant,
            cancelada_id,
            CancelacionOrdenCompra(motivo_cancelacion="Sin stock del proveedor"),
            _admin(mundo),
        )
    activa_id = _crear_orden_con_detalle(
        motor, mundo, proveedor_id=proveedor_id, cantidad=1, estado="Emitida"
    )
    _agregar_plan_021(
        motor,
        mundo,
        activa_id,
        ticket_id=pedido,
        cantidad_asignada=1,
        cantidad_faltante=3,
    )

    detalle = _detalle(motor, mundo, pedido)

    estados = {fila.orden_compra_id: fila.estado_orden for fila in detalle.asignaciones}
    assert estados == {cancelada_id: "Cancelada", activa_id: "Emitida"}
    cadena = detalle.cadena_productos[0]
    assert cadena.comprado == 1
    assert cadena.recibido == 0
    assert cadena.faltante == 3


def test_detalle_de_pedido_terminal_deja_el_faltante_en_cero(motor, mundo):
    """T8/D-7: un pedido `Cerrado` o `Anulado` no arrastra faltante."""
    fijar_stock_sede(motor, mundo, mundo["producto_id"], 0)
    proveedor_id = _crear_proveedor_control(motor, rut="96.021.052-1")
    for estado in ("Cerrado", "Anulado"):
        pedido = _crear_ticket_021(motor, mundo, estado=estado, cantidad=3)
        with sesion(motor) as db:
            db.execute(
                DetalleTicket.__table__.update()
                .where(DetalleTicket.ticket_id == pedido)
                .values(cantidad_entregada=1)
            )
            db.commit()
        orden_id = _crear_orden_con_detalle(
            motor, mundo, proveedor_id=proveedor_id, cantidad=2, estado="Emitida"
        )
        _agregar_plan_021(
            motor,
            mundo,
            orden_id,
            ticket_id=pedido,
            cantidad_asignada=2,
            cantidad_faltante=3,
        )

        detalle = _detalle(motor, mundo, pedido)

        cadena = detalle.cadena_productos[0]
        assert cadena.solicitado == 3
        assert cadena.entregado == 1
        assert cadena.faltante == 0
        assert detalle.stock_disponible is False


def test_detalle_http_incluye_asignaciones_y_cadena(motor, mundo):
    """T8/AC-5: el contrato de `GET /tickets/{id}` publica las listas nuevas."""
    fijar_stock_sede(motor, mundo, mundo["producto_id"], 0)
    pedido = _crear_ticket_021(motor, mundo, estado="EnCurso", cantidad=3)
    proveedor_id = _crear_proveedor_control(motor, rut="96.021.053-1")
    orden_id = _crear_orden_con_detalle(
        motor, mundo, proveedor_id=proveedor_id, cantidad=2, estado="Emitida"
    )
    _agregar_plan_021(
        motor, mundo, orden_id, ticket_id=pedido, cantidad_asignada=2, cantidad_faltante=1
    )

    with cliente_de_rol(motor, mundo, "Solicitante") as cliente_http:
        respuesta = cliente_http.get(f"/api/v1/tickets/{pedido}")

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["asignaciones"][0]["orden_compra_id"] == orden_id
    assert cuerpo["asignaciones"][0]["numero_oc"] == f"OC-2026-{orden_id:06d}"
    assert cuerpo["asignaciones"][0]["cantidad_asignada"] == 2
    assert cuerpo["cadena_productos"][0]["solicitado"] == 3
    assert cuerpo["cadena_productos"][0]["comprado"] == 2
    assert cuerpo["cadena_productos"][0]["faltante"] == 1


# ---------------------------------------------------------------------------
# T9: matriz 73, capacidad y contrato
# ---------------------------------------------------------------------------

_PREVIEW = ("POST", "/api/v1/compras/cobertura/preview")


def test_matriz_declara_el_preview_con_su_rol_y_la_matriz_llega_a_73():
    """T9/AC-10/AC-12: una sola operacion nueva, solo Administrador."""
    assert set(permisos.MATRIZ_PERMISOS[_PREVIEW]) == {"Administrador"}
    assert capacidades.capacidad_de_operacion(*_PREVIEW) == "compras"
    assert len(permisos.MATRIZ_PERMISOS) == 73


def test_openapi_publica_el_preview_y_73_operaciones(cliente):
    """T9/AC-12: la ruta nueva existe con su contrato y el total es 73."""
    contrato = cliente.get("/openapi.json").json()
    operacion = contrato["paths"]["/api/v1/compras/cobertura/preview"]["post"]
    assert "200" in operacion["responses"]
    assert {"401", "403", "404", "409", "422"} <= set(operacion["responses"])

    total = sum(
        1
        for ruta, metodos in contrato["paths"].items()
        if ruta.startswith("/api/v1/")
        for metodo in metodos
        if metodo.lower() in {"get", "post", "put", "patch", "delete"}
    )
    assert total == 73


def test_preview_con_capacidad_compras_apagada_responde_403(motor, mundo):
    """T9/AC-10: el gating por capacidad es adicional a la matriz."""
    sembrar_contexto_capacidades(
        motor, mundo, frozenset({"compras"}), correo=CORREO_GATING
    )
    with cliente_de_rol(
        motor, mundo, "Administrador", correo=CORREO_GATING
    ) as cliente_http:
        respuesta = cliente_http.post(
            "/api/v1/compras/cobertura/preview",
            json={
                "sede_id": mundo["sede_id"],
                "items": [
                    {
                        "producto_id": mundo["producto_id"],
                        "cantidad_solicitada": 1,
                    }
                ],
            },
        )
    assert respuesta.status_code == 403, respuesta.text
