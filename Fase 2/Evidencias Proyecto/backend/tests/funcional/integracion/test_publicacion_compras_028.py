"""Publicacion de compras: emision, facturacion y cancelacion (Feature 028, T11).

Seam bajo prueba: la **interfaz HTTP** del `app` real (`TestClient`) con el
`BusFalso` de T4 instalado por `instalar_bus`, que enciende
`TIEMPO_REAL_HABILITADO` y guarda cada sobre publicado. Asi se comprueba el
efecto observable de la mutacion (status, cuerpo y sobre) sin tocar la capa de
servicios mas alla de la preparacion del escenario y de la lectura del detalle
del pedido.

Tabla cubierta (spec §5.2 y Anexo A, filas 11-13):

| Mutacion | Motivo | Dominios | Duenos |
|---|---|---|---|
| `POST /compras/ordenes/{id}/emitir` | `emision_oc` | `compras` (+ `pedidos` si hay plan) | duenos del plan |
| `PUT /compras/ordenes/{id}/factura` | `facturacion_oc` | `compras` (+ `pedidos` si `Emitida -> Facturada` con plan) | duenos del plan |
| `POST /compras/ordenes/{id}/cancelar` | `cancelacion_oc` | `compras` (+ `pedidos` si cancela una `Emitida` con plan) | duenos del plan |

Reglas verificadas ademas de la tabla: publicacion **posterior al commit**,
silencio en alta/edicion en `Borrador`, proveedores y preview (no cambian
`GET /tickets/{id}`), silencio en los 409 de estado no elegible, y la cadena del
pedido (`GET /tickets/{id}`) antes/despues de cada mutacion leida por el
servicio. La recepcion de compras es de T12 y no se prueba aqui.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import event, select
from sqlalchemy.orm import Session, sessionmaker

from app.models import OrdenCompra, ProveedorControl, Rol, Usuario
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

RUTA_ORDENES = "/api/v1/compras/ordenes"
RUTA_EMITIR = "/api/v1/compras/ordenes/{orden_id}/emitir"
RUTA_FACTURA = "/api/v1/compras/ordenes/{orden_id}/factura"
RUTA_CANCELAR = "/api/v1/compras/ordenes/{orden_id}/cancelar"
RUTA_PREVIEW = "/api/v1/compras/cobertura/preview"
RUTA_PROVEEDORES = "/api/v1/compras/proveedores"

#: Institucion de la semilla (`datos_base`/`dos_instituciones`).
INSTITUCION = "INST01"

#: Motivos literales de la tabla de publicacion (spec §5.2).
MOTIVO_EMISION = "emision_oc"
MOTIVO_FACTURACION = "facturacion_oc"
MOTIVO_CANCELACION = "cancelacion_oc"


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
    rut: str = "59.000.000-1",
    razon_social: str = "Proveedor de la 028",
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
    cantidad: int = 2,
    producto_id: int | None = None,
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
    """Prepara una OC `Emitida` fuera del contexto del bus."""
    with _sesiones(motor) as (_db_control, db_tenant):
        return compra_service.emitir_orden_compra(
            db_tenant, orden_id, _admin(mundo)
        )


def _facturar(
    motor, mundo, orden_id: int, numero: str = "FAC-PREPARADA-028"
):
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


def _cuerpo_factura(
    numero: str = "FAC-HTTP-028", monto_total: str = "5.00"
) -> dict:
    """Cuerpo valido del `PUT /compras/ordenes/{id}/factura`."""
    return {
        "numero_factura": numero,
        "fecha_factura": date.today().isoformat(),
        "monto_total": monto_total,
    }


def _payload_orden(
    mundo, proveedor_id: int, *, cantidad: int = 2
) -> dict:
    """Cuerpo valido del alta/edicion de una OC (Feature 020)."""
    return {
        "sede_id": mundo["sede_id"],
        "proveedor_id": proveedor_id,
        "items": [
            {
                "producto_id": mundo["producto_id"],
                "cantidad_solicitada": cantidad,
                "precio_unitario": "2.50",
            }
        ],
    }


def _segundo_solicitante(motor, mundo) -> int:
    """Segundo Solicitante de INST01 para un plan con dos duenos distintos."""
    with sesion(motor) as db:
        rol = db.execute(
            select(Rol).where(Rol.nombre_rol == "Solicitante")
        ).scalar_one()
        usuario = Usuario(
            nombre="Solicitante",
            apellido="Secundario",
            correo="solicitante.secundario.028@compustock.cl",
            departamento_id=mundo["departamento_id"],
            rol_id=rol.rol_id,
        )
        db.add(usuario)
        db.commit()
        db.refresh(usuario)
        return usuario.usuario_id


def _detalle(motor, mundo, ticket_id: int):
    """`GET /tickets/{id}` por el servicio: cadena y asignaciones del pedido."""
    with sesion(motor) as db:
        return ticket_service.obtener_ticket_detalle(
            db, ticket_id, _admin(mundo)
        )


def _pedido_en_curso(motor, mundo, *, cantidad: int, usuario_id: int) -> int:
    """Pedido `EnCurso` con demanda del producto base (participa del plan)."""
    return sembrar_ticket(
        motor,
        mundo,
        estado_id=mundo["estados"]["EnCurso"],
        usuario_id=usuario_id,
        cantidad=cantidad,
    )


def _plan_con_dos_duenos(motor, mundo, *, cantidad_oc: int = 6):
    """Dos pedidos de duenos distintos y una OC en `Borrador` que los cubre.

    El primer pedido (FIFO) recibe 5 unidades y el segundo 1, de modo que el
    plan congelado tiene dos duenos. Devuelve `(orden_id, primer_dueno,
    segundo_dueno, primer_pedido, segundo_pedido, proveedor_id)`.
    """
    fijar_stock_sede(motor, mundo, mundo["producto_id"], 0)
    primer_dueno = mundo["usuarios_inst01"]["Solicitante"]
    segundo_dueno = _segundo_solicitante(motor, mundo)
    primer_pedido = _pedido_en_curso(
        motor, mundo, cantidad=5, usuario_id=primer_dueno
    )
    segundo_pedido = _pedido_en_curso(
        motor, mundo, cantidad=4, usuario_id=segundo_dueno
    )
    proveedor_id = _proveedor(motor)
    orden_id = _crear_orden(
        motor, mundo, proveedor_id=proveedor_id, cantidad=cantidad_oc
    )
    return (
        orden_id,
        primer_dueno,
        segundo_dueno,
        primer_pedido,
        segundo_pedido,
        proveedor_id,
    )


# ---------------------------------------------------------------------------
# Observacion de la publicacion
# ---------------------------------------------------------------------------


def _sobre_unico(bus):
    """Un unico sobre publicado; falla con el conteo real si hubo cero o varios."""
    assert len(bus.publicados) == 1, (
        "se esperaba exactamente un sobre publicado por la mutacion; "
        f"hubo {len(bus.publicados)}: {bus.publicados!r}"
    )
    return bus.publicados[0]


def _afirmar_sobre(
    sobre,
    *,
    dominios: set[str],
    motivo: str,
    usuario_ids: set[int],
) -> None:
    """Contrato del sobre de T11: dominios, motivo, institucion y duenos."""
    assert sobre.dominios == frozenset(dominios), (
        f"dominios esperados {sorted(dominios)}; llego {sorted(sobre.dominios)}"
    )
    assert sobre.motivo == motivo
    assert sobre.institucion_id == INSTITUCION
    assert sobre.usuario_ids == frozenset(usuario_ids), (
        "los duenos del sobre son los pedidos del plan; "
        f"llego {sobre.usuario_ids!r}"
    )


# ---------------------------------------------------------------------------
# Tabla de mutaciones: emision con y sin plan
# ---------------------------------------------------------------------------


def test_emision_con_plan_publica_compras_y_pedidos_con_los_duenos(motor, mundo):
    """Anexo A fila 11 / AC-30: la emision con plan anuncia ambos dominios."""
    (
        orden_id,
        primer_dueno,
        segundo_dueno,
        primer_pedido,
        segundo_pedido,
        _proveedor_id,
    ) = _plan_con_dos_duenos(motor, mundo)

    antes = _detalle(motor, mundo, primer_pedido)
    assert antes.asignaciones == []
    assert antes.cadena_productos[0].comprado == 0
    assert antes.cadena_productos[0].faltante == 5

    with instalar_bus() as bus:
        with cliente_de_rol(motor, mundo, "Administrador") as cliente:
            respuesta = cliente.post(RUTA_EMITIR.format(orden_id=orden_id))

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["estado"] == "Emitida"
    _afirmar_sobre(
        _sobre_unico(bus),
        dominios={"compras", "pedidos"},
        motivo=MOTIVO_EMISION,
        usuario_ids={primer_dueno, segundo_dueno},
    )

    # La cadena del pedido refleja el plan recien congelado (AC-30).
    despues = _detalle(motor, mundo, primer_pedido)
    assert despues.cadena_productos[0].comprado == 5
    assert despues.cadena_productos[0].faltante == 0
    assert [
        (
            fila.orden_compra_id,
            fila.estado_orden,
            fila.cantidad_asignada,
        )
        for fila in despues.asignaciones
    ] == [(orden_id, "Emitida", 5)]
    segundo = _detalle(motor, mundo, segundo_pedido)
    assert segundo.cadena_productos[0].comprado == 1
    assert segundo.cadena_productos[0].faltante == 3


def test_emision_sin_plan_publica_solo_compras(motor, mundo):
    """Anexo A fila 11 / AC-30: sin pedidos asignados no se anuncia `pedidos`."""
    proveedor_id = _proveedor(motor, rut="59.000.000-2")
    orden_id = _crear_orden(motor, mundo, proveedor_id=proveedor_id, cantidad=3)

    with instalar_bus() as bus:
        with cliente_de_rol(motor, mundo, "Administrador") as cliente:
            respuesta = cliente.post(RUTA_EMITIR.format(orden_id=orden_id))

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["estado"] == "Emitida"
    _afirmar_sobre(
        _sobre_unico(bus),
        dominios={"compras"},
        motivo=MOTIVO_EMISION,
        usuario_ids=set(),
    )


# ---------------------------------------------------------------------------
# Tabla de mutaciones: facturacion con y sin transicion de la cadena
# ---------------------------------------------------------------------------


def test_facturacion_desde_emitida_con_plan_publica_compras_y_pedidos(
    motor, mundo
):
    """Anexo A fila 12 / AC-30: `Emitida -> Facturada` con plan anuncia ambos."""
    (
        orden_id,
        dueno,
        _segundo_dueno,
        primer_pedido,
        _segundo_pedido,
        _proveedor_id,
    ) = _plan_con_dos_duenos(motor, mundo)
    _emitir(motor, mundo, orden_id)

    antes = _detalle(motor, mundo, primer_pedido)
    assert antes.asignaciones[0].estado_orden == "Emitida"

    with instalar_bus() as bus:
        with cliente_de_rol(motor, mundo, "Administrador") as cliente:
            respuesta = cliente.put(
                RUTA_FACTURA.format(orden_id=orden_id),
                json=_cuerpo_factura("FAC-028-EMITIDA"),
            )

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["numero_factura"] == "FAC-028-EMITIDA"
    _afirmar_sobre(
        _sobre_unico(bus),
        dominios={"compras", "pedidos"},
        motivo=MOTIVO_FACTURACION,
        usuario_ids={dueno, _segundo_dueno},
    )

    despues = _detalle(motor, mundo, primer_pedido)
    assert despues.asignaciones[0].estado_orden == "Facturada"
    assert despues.cadena_productos[0].comprado == 5


def test_correccion_de_una_facturada_publica_solo_compras(motor, mundo):
    """Anexo A fila 12 / AC-30: corregir una `Facturada` no cambia el pedido."""
    (
        orden_id,
        _dueno,
        _segundo_dueno,
        primer_pedido,
        _segundo_pedido,
        _proveedor_id,
    ) = _plan_con_dos_duenos(motor, mundo)
    _emitir(motor, mundo, orden_id)
    _facturar(motor, mundo, orden_id, numero="FAC-028-CORREGIR")

    antes = _detalle(motor, mundo, primer_pedido)
    assert antes.asignaciones[0].estado_orden == "Facturada"
    assert antes.cadena_productos[0].comprado == 5

    with instalar_bus() as bus:
        with cliente_de_rol(motor, mundo, "Administrador") as cliente:
            respuesta = cliente.put(
                RUTA_FACTURA.format(orden_id=orden_id),
                json=_cuerpo_factura(
                    "FAC-028-CORREGIR", monto_total="7.00"
                ),
            )

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["monto_total"] == "7.00"
    _afirmar_sobre(
        _sobre_unico(bus),
        dominios={"compras"},
        motivo=MOTIVO_FACTURACION,
        usuario_ids=set(),
    )

    despues = _detalle(motor, mundo, primer_pedido)
    assert despues.asignaciones[0].estado_orden == "Facturada"
    assert despues.cadena_productos[0].comprado == 5


# ---------------------------------------------------------------------------
# Tabla de mutaciones: cancelacion con y sin plan
# ---------------------------------------------------------------------------


def test_cancelacion_desde_emitida_con_plan_publica_compras_y_pedidos(
    motor, mundo
):
    """Anexo A fila 13 / AC-30: cancelar una `Emitida` con plan anuncia ambos."""
    (
        orden_id,
        dueno,
        _segundo_dueno,
        primer_pedido,
        _segundo_pedido,
        _proveedor_id,
    ) = _plan_con_dos_duenos(motor, mundo)
    _emitir(motor, mundo, orden_id)

    antes = _detalle(motor, mundo, primer_pedido)
    assert antes.cadena_productos[0].comprado == 5
    assert antes.asignaciones[0].estado_orden == "Emitida"

    with instalar_bus() as bus:
        with cliente_de_rol(motor, mundo, "Administrador") as cliente:
            respuesta = cliente.post(
                RUTA_CANCELAR.format(orden_id=orden_id),
                json={"motivo_cancelacion": "Proveedor sin stock"},
            )

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["estado"] == "Cancelada"
    _afirmar_sobre(
        _sobre_unico(bus),
        dominios={"compras", "pedidos"},
        motivo=MOTIVO_CANCELACION,
        usuario_ids={dueno, _segundo_dueno},
    )

    despues = _detalle(motor, mundo, primer_pedido)
    assert despues.cadena_productos[0].comprado == 0
    assert despues.cadena_productos[0].faltante == 5
    assert despues.asignaciones[0].estado_orden == "Cancelada"


def test_cancelacion_desde_borrador_publica_solo_compras(motor, mundo):
    """Anexo A fila 13 / AC-30: un `Borrador` no tiene plan y solo anuncia compras."""
    proveedor_id = _proveedor(motor, rut="59.000.000-3")
    orden_id = _crear_orden(motor, mundo, proveedor_id=proveedor_id)

    with instalar_bus() as bus:
        with cliente_de_rol(motor, mundo, "Administrador") as cliente:
            respuesta = cliente.post(
                RUTA_CANCELAR.format(orden_id=orden_id),
                json={"motivo_cancelacion": "Compra cancelada antes de emitir"},
            )

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["estado"] == "Cancelada"
    _afirmar_sobre(
        _sobre_unico(bus),
        dominios={"compras"},
        motivo=MOTIVO_CANCELACION,
        usuario_ids=set(),
    )


# ---------------------------------------------------------------------------
# Despues del commit, nunca antes (D-8, AC-7)
# ---------------------------------------------------------------------------


def test_la_publicacion_de_compras_ocurre_despues_del_commit(motor, mundo):
    """AC-7/D-8: al publicar, la OC ya esta persistida en su estado nuevo."""
    proveedor_id = _proveedor(motor, rut="59.000.000-4")
    orden_id = _crear_orden(motor, mundo, proveedor_id=proveedor_id)
    commits: list[int] = []
    observado: dict[str, int] = {}

    def registrar_commit(_sesion: Session) -> None:
        commits.append(1)

    with instalar_bus() as bus:
        publicar_original = bus.publicar

        def publicar_observando(sobre) -> None:
            observado["commits_previos"] = len(commits)
            publicar_original(sobre)

        bus.publicar = publicar_observando
        event.listen(Session, "after_commit", registrar_commit)
        try:
            with cliente_de_rol(motor, mundo, "Administrador") as cliente:
                respuesta = cliente.post(
                    RUTA_EMITIR.format(orden_id=orden_id)
                )
        finally:
            event.remove(Session, "after_commit", registrar_commit)

    assert respuesta.status_code == 200, respuesta.text
    assert len(bus.publicados) == 1
    assert observado["commits_previos"] >= 1, (
        "el sobre se publico antes de que la transaccion de la emision "
        "confirmara (D-8)"
    )
    with sesion(motor) as db:
        assert db.get(OrdenCompra, orden_id).estado == "Emitida", (
            "el bus ve el sobre cuando la OC ya esta persistida en `Emitida`"
        )


# ---------------------------------------------------------------------------
# Rechazos: los 409 de estado no elegible no publican (AC-7)
# ---------------------------------------------------------------------------


def test_una_segunda_emision_responde_409_y_no_publica(motor, mundo):
    """AC-7: una OC ya `Emitida` no vuelve a emitirse ni a anunciarse."""
    proveedor_id = _proveedor(motor, rut="59.000.000-5")
    orden_id = _crear_orden(motor, mundo, proveedor_id=proveedor_id)
    _emitir(motor, mundo, orden_id)

    with instalar_bus() as bus:
        with cliente_de_rol(motor, mundo, "Administrador") as cliente:
            respuesta = cliente.post(RUTA_EMITIR.format(orden_id=orden_id))

    assert respuesta.status_code == 409, respuesta.text
    assert bus.publicados == []


def test_facturar_un_borrador_responde_409_y_no_publica(motor, mundo):
    """AC-7: la factura de una OC en `Borrador` no cambia nada ni publica."""
    proveedor_id = _proveedor(motor, rut="59.000.000-6")
    orden_id = _crear_orden(motor, mundo, proveedor_id=proveedor_id)

    with instalar_bus() as bus:
        with cliente_de_rol(motor, mundo, "Administrador") as cliente:
            respuesta = cliente.put(
                RUTA_FACTURA.format(orden_id=orden_id),
                json=_cuerpo_factura("FAC-028-BORRADOR"),
            )

    assert respuesta.status_code == 409, respuesta.text
    assert bus.publicados == []


def test_cancelar_una_facturada_responde_409_y_no_publica(motor, mundo):
    """AC-7: una OC `Facturada` no se cancela ni se anuncia."""
    proveedor_id = _proveedor(motor, rut="59.000.000-7")
    orden_id = _crear_orden(motor, mundo, proveedor_id=proveedor_id)
    _emitir(motor, mundo, orden_id)
    _facturar(motor, mundo, orden_id, numero="FAC-028-409")

    with instalar_bus() as bus:
        with cliente_de_rol(motor, mundo, "Administrador") as cliente:
            respuesta = cliente.post(
                RUTA_CANCELAR.format(orden_id=orden_id),
                json={"motivo_cancelacion": "No deberia cancelarse"},
            )

    assert respuesta.status_code == 409, respuesta.text
    assert bus.publicados == []


# ---------------------------------------------------------------------------
# Alta/edicion en Borrador, proveedores y preview no publican (AC-30)
# ---------------------------------------------------------------------------


def test_alta_edicion_proveedores_y_preview_no_publican(motor, mundo):
    """Anexo A nota 3 / AC-30: las rutas sin efecto en el pedido no anuncian."""
    with instalar_bus() as bus:
        with cliente_de_rol(motor, mundo, "Administrador") as cliente:
            proveedor = cliente.post(
                RUTA_PROVEEDORES,
                json={
                    "rut": "53.000.000-1",
                    "razon_social": "Proveedor sin aviso 028",
                },
            )
            proveedor_id = proveedor.json()["proveedor_id"]
            creada = cliente.post(
                RUTA_ORDENES,
                json=_payload_orden(mundo, proveedor_id, cantidad=2),
            )
            orden_id = creada.json()["orden_compra_id"]
            editada = cliente.put(
                f"{RUTA_ORDENES}/{orden_id}",
                json=_payload_orden(mundo, proveedor_id, cantidad=3),
            )
            preview = cliente.post(
                RUTA_PREVIEW,
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

    assert proveedor.status_code == 201, proveedor.text
    assert creada.status_code == 201, creada.text
    assert editada.status_code == 200, editada.text
    assert preview.status_code == 200, preview.text
    assert bus.publicados == [], (
        "el alta/edicion en Borrador, los proveedores y el preview no cambian "
        "GET /tickets/{id} y no deben publicar (AC-30)"
    )
