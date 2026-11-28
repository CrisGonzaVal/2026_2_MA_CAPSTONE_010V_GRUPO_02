"""Publicacion de la recepcion y el desbloqueo (Feature 028, T12).

Seam bajo prueba: la interfaz HTTP de
`POST /api/v1/compras/ordenes/{id}/recepcion` del `app` real, con el
`BusFalso` de T4 instalado por `instalar_bus` (canal encendido y sobres
guardados). El detalle se lee por el servicio
(`ticket_service.obtener_ticket_detalle`) porque `stock_disponible` es una
propiedad derivada de la simulacion de cobertura, no un campo de la vista.

Tabla cubierta (spec §5.2 y Anexo A, fila 14):

| Recepcion | Motivo | Dominios | Duenos |
|---|---|---|---|
| con plan y desbloqueo | `recepcion` | `inventario`, `compras`, `pedidos` | plan ∪ desbloqueados |
| sin plan, con desbloqueo | `recepcion` | `inventario`, `compras`, `pedidos` | desbloqueados |
| sin plan ni desbloqueo | `recepcion` | `inventario`, `compras` | — |
| OC ya `Recibida` (409) | — | no publica | — |

Reglas verificadas ademas de la tabla: un unico sobre por recepcion (la union
de duenos se publica una sola vez y sin duplicados) y el detalle del Bodeguero
refleja `stock_disponible = true` despues de la recepcion (AC-13).
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.models import ProveedorControl, Rol, Usuario
from app.schemas.compra_schema import (
    DetalleOrdenCompraCrear,
    FacturaCompraRegistrar,
    OrdenCompraCrear,
)
from app.services import compra_service, ticket_service

from tests.funcional.integracion._soporte_ciclo_vida_013 import sembrar_ticket
from tests.funcional.integracion._soporte_ciclo_vida_catalogo_014 import (
    cliente_de_rol,
    fijar_stock_sede,
    sembrar_mundo_014,
)
from tests.funcional.integracion._soporte_eventos_028 import instalar_bus
from tests.funcional.integracion._soporte_sede_011 import identidad, sesion

RUTA_RECEPCION = "/api/v1/compras/ordenes/{orden_id}/recepcion"

#: Institucion de la semilla (`datos_base`/`dos_instituciones`).
INSTITUCION = "INST01"

#: Motivo literal de la publicacion de recepcion (spec §5.2).
MOTIVO_RECEPCION = "recepcion"


# ---------------------------------------------------------------------------
# Mundo, clientes y preparacion
# ---------------------------------------------------------------------------


@pytest.fixture
def mundo(motor, dos_instituciones):
    """Sede del departamento, catalogo de estados y stock base (013/014)."""
    return sembrar_mundo_014(motor, dos_instituciones)


def _admin(mundo):
    return identidad(
        "Administrador", mundo["departamento_id"], mundo["usuario_id"]
    )


def _bodeguero(mundo):
    return identidad(
        "Bodeguero",
        mundo["departamento_id"],
        mundo["usuarios_inst01"]["Bodeguero"],
        sede_id=mundo["sede_id"],
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


def _proveedor(
    motor,
    *,
    rut: str,
    razon_social: str = "Proveedor de la recepcion 028",
) -> int:
    """Inserta un proveedor en el catalogo global de prueba."""
    with sesion(motor) as db:
        fila = ProveedorControl(rut=rut, razon_social=razon_social, activo=True)
        db.add(fila)
        db.commit()
        db.refresh(fila)
        return fila.proveedor_id


def _crear_orden(
    motor,
    mundo,
    *,
    proveedor_id: int,
    cantidad: int,
) -> int:
    """Crea una OC en `Borrador` por el servicio y devuelve su id."""
    with _sesiones(motor) as (db_control, db_tenant):
        orden = compra_service.crear_orden_compra(
            db_tenant,
            db_control,
            OrdenCompraCrear(
                sede_id=mundo["sede_id"],
                proveedor_id=proveedor_id,
                items=[
                    DetalleOrdenCompraCrear(
                        producto_id=mundo["producto_id"],
                        cantidad_solicitada=cantidad,
                        precio_unitario=Decimal("2.50"),
                    )
                ],
            ),
            _admin(mundo),
        )
        return orden.orden_compra_id


def _emitir(motor, mundo, orden_id: int):
    """Prepara una OC `Emitida` fuera del contexto del bus."""
    with _sesiones(motor) as (_db_control, db_tenant):
        return compra_service.emitir_orden_compra(
            db_tenant, orden_id, _admin(mundo)
        )


def _facturar(motor, mundo, orden_id: int, numero: str):
    """Prepara una OC `Facturada` fuera del contexto del bus."""
    with _sesiones(motor) as (_db_control, db_tenant):
        return compra_service.registrar_o_editar_factura(
            db_tenant,
            orden_id,
            FacturaCompraRegistrar(
                numero_factura=numero,
                fecha_factura=date.today(),
                monto_total=Decimal("5.00"),
            ),
            _admin(mundo),
        )


def _recepcionar(motor, mundo, orden_id: int):
    """Prepara una OC `Recibida` fuera del contexto del bus."""
    with _sesiones(motor) as (_db_control, db_tenant):
        return compra_service.recepcionar_orden_compra(
            db_tenant, orden_id, _bodeguero(mundo)
        )


def _segundo_solicitante(motor, mundo) -> int:
    """Segundo Solicitante de INST01 para un plan con dos duenos distintos."""
    with sesion(motor) as db:
        rol = db.execute(
            select(Rol).where(Rol.nombre_rol == "Solicitante")
        ).scalar_one()
        usuario = Usuario(
            nombre="Solicitante",
            apellido="Recepcion",
            correo="solicitante.recepcion.028@compustock.cl",
            departamento_id=mundo["departamento_id"],
            rol_id=rol.rol_id,
        )
        db.add(usuario)
        db.commit()
        db.refresh(usuario)
        return usuario.usuario_id


def _pedido_en_curso(motor, mundo, *, cantidad: int, usuario_id: int) -> int:
    """Pedido `EnCurso` con demanda del producto base."""
    return sembrar_ticket(
        motor,
        mundo,
        estado_id=mundo["estados"]["EnCurso"],
        usuario_id=usuario_id,
        cantidad=cantidad,
    )


def _detalle(motor, mundo, ticket_id: int):
    """Detalle del pedido leido por el servicio, con la identidad del Bodeguero."""
    with sesion(motor) as db:
        return ticket_service.obtener_ticket_detalle(
            db, ticket_id, _bodeguero(mundo)
        )


# ---------------------------------------------------------------------------
# Observacion de la publicacion
# ---------------------------------------------------------------------------


def _sobre_unico(bus):
    """Un unico sobre publicado; falla con el conteo real si hubo cero o varios."""
    assert len(bus.publicados) == 1, (
        "se esperaba exactamente un sobre publicado por la recepcion; "
        f"hubo {len(bus.publicados)}: {bus.publicados!r}"
    )
    return bus.publicados[0]


def _afirmar_sobre(
    sobre,
    *,
    dominios: set[str],
    usuario_ids: set[int],
) -> None:
    """Contrato de T12: dominios, motivo, institucion y duenos."""
    assert sobre.dominios == frozenset(dominios), (
        f"dominios esperados {sorted(dominios)}; llego {sorted(sobre.dominios)}"
    )
    assert sobre.motivo == MOTIVO_RECEPCION
    assert sobre.institucion_id == INSTITUCION
    assert sobre.usuario_ids == frozenset(usuario_ids), (
        "los duenos del sobre son la union del plan y los desbloqueados; "
        f"llego {sobre.usuario_ids!r}"
    )


# ---------------------------------------------------------------------------
# Recepcion con plan y desbloqueo
# ---------------------------------------------------------------------------


def test_recepcion_con_plan_y_desbloqueo_publica_un_sobre_con_la_union(
    motor, mundo
):
    """Anexo A fila 14 / AC-30: plan ∪ desbloqueados, en un solo sobre."""
    fijar_stock_sede(motor, mundo, mundo["producto_id"], 0)
    primer_dueno = mundo["usuarios_inst01"]["Solicitante"]
    segundo_dueno = _segundo_solicitante(motor, mundo)
    primer_pedido = _pedido_en_curso(
        motor, mundo, cantidad=3, usuario_id=primer_dueno
    )
    segundo_pedido = _pedido_en_curso(
        motor, mundo, cantidad=3, usuario_id=segundo_dueno
    )
    proveedor_id = _proveedor(motor, rut="57.000.000-1")
    # La OC reparte 3 al primer pedido y 1 al segundo: el plan tiene dos
    # duenos, pero solo el primero queda cubierto por el stock recibido.
    orden_id = _crear_orden(
        motor, mundo, proveedor_id=proveedor_id, cantidad=4
    )
    _emitir(motor, mundo, orden_id)
    _facturar(motor, mundo, orden_id, numero="FAC-028-REC-UNION")

    assert _detalle(motor, mundo, primer_pedido).stock_disponible is False
    assert _detalle(motor, mundo, segundo_pedido).stock_disponible is False

    with instalar_bus() as bus:
        with cliente_de_rol(motor, mundo, "Bodeguero") as cliente:
            respuesta = cliente.post(
                RUTA_RECEPCION.format(orden_id=orden_id)
            )

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["estado"] == "Recibida"
    assert [
        fila["ticket_id"]
        for fila in respuesta.json()["tickets_desbloqueados"]
    ] == [primer_pedido]

    sobre = _sobre_unico(bus)
    _afirmar_sobre(
        sobre,
        dominios={"inventario", "compras", "pedidos"},
        usuario_ids={primer_dueno, segundo_dueno},
    )
    # El primer pedido esta en el plan y ademas se desbloquea: su dueno
    # aparece una sola vez en el conjunto.
    assert len(sobre.usuario_ids) == 2

    assert _detalle(motor, mundo, primer_pedido).stock_disponible is True
    assert _detalle(motor, mundo, segundo_pedido).stock_disponible is False


def test_recepcion_sin_plan_pero_con_desbloqueo_publica_pedidos(motor, mundo):
    """Anexo A fila 14 / AC-30: el desbloqueo basta para anunciar `pedidos`."""
    fijar_stock_sede(motor, mundo, mundo["producto_id"], 0)
    proveedor_id = _proveedor(motor, rut="57.000.000-2")
    orden_id = _crear_orden(
        motor, mundo, proveedor_id=proveedor_id, cantidad=5
    )
    _emitir(motor, mundo, orden_id)  # plan vacio: aun no hay pedidos
    _facturar(motor, mundo, orden_id, numero="FAC-028-REC-DESBLOQUEO")
    dueno = mundo["usuarios_inst01"]["Solicitante"]
    pedido = _pedido_en_curso(motor, mundo, cantidad=3, usuario_id=dueno)
    assert _detalle(motor, mundo, pedido).stock_disponible is False

    with instalar_bus() as bus:
        with cliente_de_rol(motor, mundo, "Bodeguero") as cliente:
            respuesta = cliente.post(
                RUTA_RECEPCION.format(orden_id=orden_id)
            )

    assert respuesta.status_code == 200, respuesta.text
    assert [
        fila["ticket_id"]
        for fila in respuesta.json()["tickets_desbloqueados"]
    ] == [pedido]
    _afirmar_sobre(
        _sobre_unico(bus),
        dominios={"inventario", "compras", "pedidos"},
        usuario_ids={dueno},
    )
    assert _detalle(motor, mundo, pedido).stock_disponible is True


def test_recepcion_sin_plan_ni_desbloqueo_publica_solo_stock_y_compras(
    motor, mundo
):
    """Anexo A fila 14 / AC-30: sin pedidos afectados no se anuncia `pedidos`."""
    proveedor_id = _proveedor(motor, rut="57.000.000-3")
    orden_id = _crear_orden(
        motor, mundo, proveedor_id=proveedor_id, cantidad=3
    )
    _emitir(motor, mundo, orden_id)
    _facturar(motor, mundo, orden_id, numero="FAC-028-REC-SIN-PLAN")

    with instalar_bus() as bus:
        with cliente_de_rol(motor, mundo, "Bodeguero") as cliente:
            respuesta = cliente.post(
                RUTA_RECEPCION.format(orden_id=orden_id)
            )

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["tickets_desbloqueados"] == []
    _afirmar_sobre(
        _sobre_unico(bus),
        dominios={"inventario", "compras"},
        usuario_ids=set(),
    )


# ---------------------------------------------------------------------------
# Rechazos: una OC ya recibida no publica (AC-7)
# ---------------------------------------------------------------------------


def test_recepcion_de_una_orden_ya_recibida_responde_409_y_no_publica(
    motor, mundo
):
    """AC-7: una OC ya `Recibida` no vuelve a recepcionarse ni a anunciarse."""
    proveedor_id = _proveedor(motor, rut="57.000.000-4")
    orden_id = _crear_orden(
        motor, mundo, proveedor_id=proveedor_id, cantidad=2
    )
    _emitir(motor, mundo, orden_id)
    _facturar(motor, mundo, orden_id, numero="FAC-028-REC-409")
    _recepcionar(motor, mundo, orden_id)

    with instalar_bus() as bus:
        with cliente_de_rol(motor, mundo, "Bodeguero") as cliente:
            respuesta = cliente.post(
                RUTA_RECEPCION.format(orden_id=orden_id)
            )

    assert respuesta.status_code == 409, respuesta.text
    assert bus.publicados == []


# ---------------------------------------------------------------------------
# El detalle del Bodeguero refleja el desbloqueo (AC-13, servicio)
# ---------------------------------------------------------------------------


def test_detalle_del_bodeguero_refleja_stock_disponible_tras_la_recepcion(
    motor, mundo
):
    """AC-13: el detalle derivado pasa a `stock_disponible = true` (servicio)."""
    fijar_stock_sede(motor, mundo, mundo["producto_id"], 0)
    dueno = mundo["usuarios_inst01"]["Solicitante"]
    pedido = _pedido_en_curso(motor, mundo, cantidad=3, usuario_id=dueno)
    proveedor_id = _proveedor(motor, rut="57.000.000-5")
    orden_id = _crear_orden(
        motor, mundo, proveedor_id=proveedor_id, cantidad=5
    )
    _emitir(motor, mundo, orden_id)
    _facturar(motor, mundo, orden_id, numero="FAC-028-REC-DETALLE")
    assert _detalle(motor, mundo, pedido).stock_disponible is False

    with instalar_bus():
        with cliente_de_rol(motor, mundo, "Bodeguero") as cliente:
            respuesta = cliente.post(
                RUTA_RECEPCION.format(orden_id=orden_id)
            )

    assert respuesta.status_code == 200, respuesta.text
    detalle = _detalle(motor, mundo, pedido)
    assert detalle.stock_disponible is True
    assert detalle.estado_nombre == "EnCurso"
