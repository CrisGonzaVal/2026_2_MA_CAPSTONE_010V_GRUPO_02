"""Soporte de las pruebas rojas de la enmienda 26/Nov/2026 de la Feature 013.

La enmienda sustituye el catalogo de cinco nombres por cuatro
(`EnRevision`, `EnCurso`, `Cerrado`, `Anulado`), renombra el despacho a
**retiro** (`POST /tickets/{id}/retiro`, DTO `TicketRetiro`, servicio
`registrar_retiro_ticket`) y abre la anulacion administrativa del retiro
(`Cerrado -> Anulado` con devolucion de stock).

Como esta es la fase **roja** (T32), este modulo no importa nigun simbolo que
aun no exista (`TicketRetiro`, `registrar_retiro_ticket`): las pruebas hablan
HTTP con JSON crudo y consultan la matriz/OpenAPI como contrato. Las guardas
`exigir_ruta`/`exigir_operacion` fallan con `pytest.fail` cuando la ruta o la
fila de matriz todavia no estan cableadas (T35/T37), de modo que una prueba que
espera `403`/`404`/`409` no pase por el motivo equivocado (la ruta ausente).

El seam bajo prueba sigue siendo la interfaz HTTP (`TestClient`); la lectura
por ORM se limita a la auditoria (`movimiento_inventario`, historial, stock),
que no expone todavia un endpoint equivalente para todos los casos.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.core import permisos
from app.main import app
from app.models import (
    DetalleTicket,
    HistorialTransicionTicket,
    MovimientoInventario,
    Producto,
    StockSede,
    Ticket,
    Usuario,
)

from tests.funcional.integracion._soporte_ciclo_vida_013 import sembrar_mundo_013
from tests.funcional.integracion._soporte_sede_011 import (
    SIN_AUTENTICAR,
    asignar_sede_a_usuario,
    cliente as cliente_con_rol,
    contar_en,
    crear_sede,
    leer_stock_sede,
    sesion,
)

# ---------------------------------------------------------------------------
# Contrato de la enmienda (spec §10.5, plan §10.5-§10.6)
# ---------------------------------------------------------------------------

#: Catalogo canonico de la enmienda: cuatro nombres, sin `Pendiente` y sin
#: homonimos (D-27). Los ids son los de la semilla; el codigo resuelve por
#: nombre, nunca por posicion.
CATALOGO_RETIRO: tuple[str, ...] = ("EnRevision", "EnCurso", "Cerrado", "Anulado")

RUTA_RETIRO = "/api/v1/tickets/{ticket_id}/retiro"
RUTA_DESPACHO = "/api/v1/tickets/{ticket_id}/despacho"
RUTA_ANULACION = "/api/v1/tickets/{ticket_id}/anulacion"
RUTA_RECHAZO = "/api/v1/tickets/{ticket_id}/rechazo"
RUTA_CONFIRMACION = "/api/v1/tickets/{ticket_id}/confirmacion-entrega"
RUTA_ESTADO = "/api/v1/tickets/{ticket_id}/estado"
RUTA_MOVIMIENTOS = "/api/v1/inventario/movimientos"

#: Motivo canonico de la confirmacion de entrega (D-25/D-34).
MOTIVO_CONFIRMACION = "Entrega confirmada por el solicitante"

#: Observaciones literales de la enmienda (D-29/D-32).
PREFIJO_SALIDA = "Salida por retiro del ticket #{ticket_id};"
PREFIJO_ENTRADA = "Devolución por anulación del retiro del ticket #{ticket_id};"

#: `fecha_cierre` de un ticket `Cerrado` sembrado por ORM.
FECHA_CIERRE = datetime(2026, 11, 20, 9, 30)

#: Detalle unico del 404 de ticket (inexistente y ajeno, ocultamiento D-8).
DETALLE_TICKET_NO_ENCONTRADO = "Ticket no encontrado"

#: Sentinela para distinguir "sede automatica del rol" de "sin sede".
_SEDE_AUTOMATICA = object()


# ---------------------------------------------------------------------------
# Guardas de la fase roja (mismo patron que las features 011/013)
# ---------------------------------------------------------------------------


def exigir_ruta(ruta: str, metodo: str = "POST") -> None:
    """Falla si la operacion aun no esta publicada en `/openapi.json` (T35)."""
    operaciones = app.openapi().get("paths", {}).get(ruta, {})
    if metodo.lower() not in operaciones:
        pytest.fail(
            f"capacidad ausente (T35): {metodo.upper()} {ruta} no esta publicada "
            "en /openapi.json; la enmienda 26/Nov/2026 la cablea en T35."
        )


def exigir_operacion(metodo: str, ruta: str) -> None:
    """Falla si la operacion aun no esta declarada en la matriz central (T35/T37)."""
    if (metodo.upper(), ruta) not in permisos.MATRIZ_PERMISOS:
        pytest.fail(
            f"capacidad ausente (T35): MATRIZ_PERMISOS no declara "
            f"{(metodo.upper(), ruta)}; la enmienda 26/Nov/2026 la cablea en T35."
        )


def exigir_retiro_publicado() -> None:
    """Falla si `/retiro` no esta ni publicada ni en la matriz (fase roja T32)."""
    exigir_ruta(RUTA_RETIRO)
    exigir_operacion("POST", RUTA_RETIRO)


# ---------------------------------------------------------------------------
# Construccion del mundo
# ---------------------------------------------------------------------------


def sembrar_mundo_retiro(
    motor,
    datos: dict[str, Any],
    *,
    nombres_estados: tuple[str, ...] | None = None,
    con_stock: bool = True,
) -> dict[str, Any]:
    """Padron de la 013 con el catalogo de cuatro estados y sede del Bodeguero.

    Reutiliza `sembrar_mundo_013` (sede del departamento, catalogo por nombre y
    50 unidades del producto base en la sede) y asigna al Bodeguero de INST01
    la sede del pedido, que es la precondicion del retiro acotado (D-30).
    Devuelve `datos` ampliado, como el helper original.
    """
    mundo = sembrar_mundo_013(
        motor,
        datos,
        nombres_estados=nombres_estados or CATALOGO_RETIRO,
        con_stock=con_stock,
    )
    asignar_sede_a_usuario(
        motor, mundo["usuarios_inst01"]["Bodeguero"], mundo["sede_id"]
    )
    return mundo


def crear_producto_con_stock(
    motor,
    datos: dict[str, Any],
    *,
    nombre: str,
    stock_actual: int,
    sede_id: int | None = None,
) -> dict[str, int]:
    """Producto de la institucion con su fila `stock_sede` en la sede pedida."""
    sede = datos["sede_id"] if sede_id is None else sede_id
    db = sessionmaker(bind=motor)()
    try:
        producto = Producto(
            nombre=nombre,
            descripcion="Producto de las pruebas de la enmienda del retiro",
            unidad_medida="UNIDAD",
            stock_minimo=0,
            categoria_id=datos["categoria_id"],
            institucion_id=datos["institucion_id"],
        )
        producto.activo = True
        db.add(producto)
        db.flush()
        fila = StockSede(
            sede_id=sede,
            producto_id=producto.producto_id,
            stock_actual=stock_actual,
            institucion_id=datos["institucion_id"],
        )
        db.add(fila)
        db.commit()
        return {
            "producto_id": producto.producto_id,
            "stock_sede_id": fila.stock_sede_id,
        }
    finally:
        db.close()


def fijar_stock(
    motor, *, sede_id: int, producto_id: int, stock_actual: int
) -> None:
    """Fija el saldo de `(sede, producto)`, creando la fila si falta."""
    with sesion(motor) as db:
        fila = db.execute(
            select(StockSede).where(
                StockSede.sede_id == sede_id,
                StockSede.producto_id == producto_id,
            )
        ).scalar_one_or_none()
        if fila is None:
            fila = StockSede(
                sede_id=sede_id,
                producto_id=producto_id,
                stock_actual=stock_actual,
                institucion_id="INST01",
            )
            db.add(fila)
        else:
            fila.stock_actual = stock_actual
        db.commit()


def sembrar_ticket_retiro(
    motor,
    datos: dict[str, Any],
    *,
    estado: str = "EnCurso",
    detalles: list[tuple[int, int, int]] | None = None,
    sede_id: int | None | object = _SEDE_AUTOMATICA,
    usuario_id: int | None = None,
    fecha_cierre: datetime | None = None,
    asunto: str = "Pedido sembrado para la enmienda del retiro",
) -> int:
    """Ticket por ORM en el estado pedido, con detalles `(producto, pedida, entregada)`.

    Permite sembrar `EnCurso`, `Cerrado` (con `fecha_cierre` y cantidades ya
    entregadas, el estado del que parte la anulacion administrativa) y
    `Anulado`, sin pasar por el alta. `sede_id` admite `None` para el caso
    "ticket de otra sede/sin sede" y por defecto usa la sede del mundo.
    """
    if sede_id is _SEDE_AUTOMATICA:
        sede_id = datos["sede_id"]
    if usuario_id is None:
        usuario_id = datos["usuarios_inst01"]["Solicitante"]
    filas = (
        [(datos["producto_id"], 3, 0)] if detalles is None else detalles
    )

    db = sessionmaker(bind=motor)()
    try:
        ticket = Ticket(
            usuario_id=usuario_id,
            prioridad_id=datos["prioridad_id"],
            estado_id=datos["estados"][estado],
            asunto=asunto,
            descripcion="Sembrado para las pruebas rojas de la enmienda.",
            institucion_id=datos["institucion_id"],
            sede_id=sede_id,
            fecha_cierre=fecha_cierre,
        )
        db.add(ticket)
        db.flush()
        for producto_id, cantidad_solicitada, cantidad_entregada in filas:
            db.add(
                DetalleTicket(
                    ticket_id=ticket.ticket_id,
                    producto_id=producto_id,
                    cantidad_solicitada=cantidad_solicitada,
                    cantidad_entregada=cantidad_entregada,
                    institucion_id=datos["institucion_id"],
                )
            )
        db.commit()
        return ticket.ticket_id
    finally:
        db.close()


def marcar_confirmado(
    motor,
    datos: dict[str, Any],
    ticket_id: int,
    *,
    usuario_id: int | None = None,
) -> None:
    """Inserta la fila canonica `Cerrado -> Cerrado` de la confirmacion (D-25)."""
    if usuario_id is None:
        usuario_id = datos["usuarios_inst01"]["Solicitante"]
    with sesion(motor) as db:
        db.add(
            HistorialTransicionTicket(
                ticket_id=ticket_id,
                estado_origen_id=datos["estados"]["Cerrado"],
                estado_destino_id=datos["estados"]["Cerrado"],
                usuario_id=usuario_id,
                motivo=MOTIVO_CONFIRMACION,
            )
        )
        db.commit()


def eliminar_fila_de_stock(motor, *, sede_id: int, producto_id: int) -> None:
    """Borra la fila `stock_sede` para forzar el camino "crear si falta" (D-32)."""
    with sesion(motor) as db:
        fila = db.execute(
            select(StockSede).where(
                StockSede.sede_id == sede_id,
                StockSede.producto_id == producto_id,
            )
        ).scalar_one_or_none()
        if fila is not None:
            db.delete(fila)
            db.commit()


# ---------------------------------------------------------------------------
# Clientes por rol
# ---------------------------------------------------------------------------


def cliente_rol(
    motor,
    datos: dict[str, Any],
    rol: str,
    *,
    sede_id: int | None | object = _SEDE_AUTOMATICA,
    usuario_id: int | None = None,
    correo: str | None = None,
):
    """`TestClient` autenticado con el rol pedido sobre el padron de INST01.

    Por defecto el Bodeguero opera con la sede del pedido (la del mundo) y el
    resto de roles sin sede. `sede_id=None` permite el caso "Bodeguero sin
    sede" (409 del retiro) y un entero distinto el "Bodeguero de otra sede"
    (404 identico al inexistente, D-30).
    """
    if usuario_id is None:
        usuario_id = datos["usuarios_inst01"][rol]
    if sede_id is _SEDE_AUTOMATICA:
        sede_id = datos["sede_id"] if rol == "Bodeguero" else None
    opciones: dict[str, Any] = {
        "departamento_id": datos["departamento_id"],
        "usuario_id": usuario_id,
        "sede_id": sede_id,
    }
    if correo is not None:
        opciones["correo"] = correo
    return cliente_con_rol(motor, rol, **opciones)


# ---------------------------------------------------------------------------
# Peticiones del contrato (JSON crudo: no importa DTOs que aun no existen)
# ---------------------------------------------------------------------------


def retirar(cliente, ticket_id: int, payload: dict | None = None):
    """`POST /tickets/{id}/retiro` con el payload crudo de la 005."""
    if payload is None:
        return cliente.post(f"/api/v1/tickets/{ticket_id}/retiro")
    return cliente.post(f"/api/v1/tickets/{ticket_id}/retiro", json=payload)


def anular(cliente, ticket_id: int, motivo: str):
    return cliente.post(
        f"/api/v1/tickets/{ticket_id}/anulacion", json={"motivo": motivo}
    )


def rechazar(cliente, ticket_id: int, motivo: str):
    return cliente.post(
        f"/api/v1/tickets/{ticket_id}/rechazo", json={"motivo": motivo}
    )


def confirmar(cliente, ticket_id: int):
    return cliente.post(f"/api/v1/tickets/{ticket_id}/confirmacion-entrega")


def cambiar_estado(cliente, ticket_id: int, estado_id: int):
    return cliente.patch(
        f"/api/v1/tickets/{ticket_id}/estado", json={"estado_id": estado_id}
    )


# ---------------------------------------------------------------------------
# Observacion de lo persistido
# ---------------------------------------------------------------------------


def historial_persistido(motor, ticket_id: int) -> list[dict[str, Any]]:
    """Filas del historial del ticket, en orden de escritura."""
    with sesion(motor) as db:
        filas = (
            db.execute(
                select(HistorialTransicionTicket)
                .where(HistorialTransicionTicket.ticket_id == ticket_id)
                .order_by(HistorialTransicionTicket.historial_transicion_id)
            )
            .scalars()
            .all()
        )
        return [
            {
                "historial_transicion_id": fila.historial_transicion_id,
                "ticket_id": fila.ticket_id,
                "estado_origen_id": fila.estado_origen_id,
                "estado_destino_id": fila.estado_destino_id,
                "usuario_id": fila.usuario_id,
                "motivo": fila.motivo,
            }
            for fila in filas
        ]


def movimientos_persistidos(motor) -> list[dict[str, Any]]:
    """Filas de auditoria con su `stock_sede` resuelta (producto y sede)."""
    with sesion(motor) as db:
        filas = db.execute(
            select(MovimientoInventario, StockSede)
            .join(
                StockSede,
                StockSede.stock_sede_id == MovimientoInventario.stock_sede_id,
            )
            .order_by(MovimientoInventario.movimiento_id)
        ).all()
        return [
            {
                "movimiento_id": movimiento.movimiento_id,
                "tipo_movimiento": movimiento.tipo_movimiento,
                "cantidad": movimiento.cantidad,
                "observacion": movimiento.observacion,
                "stock_sede_id": movimiento.stock_sede_id,
                "producto_id": stock.producto_id,
                "sede_id": stock.sede_id,
            }
            for movimiento, stock in filas
        ]


def salidas_retiro(motor, ticket_id: int) -> list[dict[str, Any]]:
    """`SALIDA` del retiro del ticket, identificadas por su observacion D-29."""
    prefijo = PREFIJO_SALIDA.format(ticket_id=ticket_id)
    return [
        movimiento
        for movimiento in movimientos_persistidos(motor)
        if movimiento["tipo_movimiento"] == "SALIDA"
        and (movimiento["observacion"] or "").startswith(prefijo)
    ]


def entradas_devolucion(motor, ticket_id: int) -> list[dict[str, Any]]:
    """`ENTRADA` de la anulacion del retiro del ticket (D-32)."""
    prefijo = PREFIJO_ENTRADA.format(ticket_id=ticket_id)
    return [
        movimiento
        for movimiento in movimientos_persistidos(motor)
        if movimiento["tipo_movimiento"] == "ENTRADA"
        and (movimiento["observacion"] or "").startswith(prefijo)
    ]


def estado_de_ticket(motor, ticket_id: int) -> int | None:
    with sesion(motor) as db:
        ticket = db.get(Ticket, ticket_id)
        return None if ticket is None else ticket.estado_id


def fecha_cierre_de_ticket(motor, ticket_id: int):
    with sesion(motor) as db:
        ticket = db.get(Ticket, ticket_id)
        return None if ticket is None else ticket.fecha_cierre


def entregas_de_ticket(motor, ticket_id: int) -> dict[int, int]:
    """`{detalle_ticket_id: cantidad_entregada}` leido por ORM."""
    with sesion(motor) as db:
        filas = (
            db.execute(
                select(DetalleTicket)
                .where(DetalleTicket.ticket_id == ticket_id)
                .order_by(DetalleTicket.detalle_ticket_id)
            )
            .scalars()
            .all()
        )
        return {fila.detalle_ticket_id: fila.cantidad_entregada for fila in filas}


def stock_de(motor, sede_id: int, producto_id: int) -> int | None:
    return leer_stock_sede(motor, sede_id, producto_id)


def usuario_tiene_sede(motor, usuario_id: int) -> int | None:
    with sesion(motor) as db:
        usuario = db.get(Usuario, usuario_id)
        return None if usuario is None else usuario.sede_id


def verificar_sin_efectos_retiro(
    motor,
    datos: dict[str, Any],
    ticket_id: int,
    *,
    estado: str,
    stocks: dict[tuple[int, int], int],
) -> None:
    """Un rechazo del retiro no puede dejar rastro en ticket, detalles ni stock."""
    assert estado_de_ticket(motor, ticket_id) == datos["estados"][estado], (
        "un rechazo no puede cambiar el estado del ticket"
    )
    assert fecha_cierre_de_ticket(motor, ticket_id) is None, (
        "un rechazo no puede sellar el cierre"
    )
    assert all(
        cantidad == 0 for cantidad in entregas_de_ticket(motor, ticket_id).values()
    ), "un rechazo no puede dejar entregas, ni parciales"
    for (sede_id, producto_id), esperado in stocks.items():
        assert stock_de(motor, sede_id, producto_id) == esperado, (
            f"un rechazo no puede rebajar el stock de ({sede_id}, {producto_id})"
        )
    assert salidas_retiro(motor, ticket_id) == [], (
        "un rechazo no puede crear movimientos de auditoria"
    )


__all__ = [
    "CATALOGO_RETIRO",
    "DETALLE_TICKET_NO_ENCONTRADO",
    "FECHA_CIERRE",
    "MOTIVO_CONFIRMACION",
    "PREFIJO_ENTRADA",
    "PREFIJO_SALIDA",
    "RUTA_ANULACION",
    "RUTA_CONFIRMACION",
    "RUTA_DESPACHO",
    "RUTA_ESTADO",
    "RUTA_MOVIMIENTOS",
    "RUTA_RECHAZO",
    "RUTA_RETIRO",
    "SIN_AUTENTICAR",
    "anular",
    "cambiar_estado",
    "cliente_rol",
    "confirmar",
    "contar_en",
    "crear_producto_con_stock",
    "crear_sede",
    "eliminar_fila_de_stock",
    "entradas_devolucion",
    "entregas_de_ticket",
    "estado_de_ticket",
    "exigir_operacion",
    "exigir_retiro_publicado",
    "exigir_ruta",
    "fecha_cierre_de_ticket",
    "fijar_stock",
    "historial_persistido",
    "marcar_confirmado",
    "movimientos_persistidos",
    "rechazar",
    "retirar",
    "salidas_retiro",
    "sembrar_mundo_retiro",
    "sembrar_ticket_retiro",
    "sesion",
    "stock_de",
    "usuario_tiene_sede",
    "verificar_sin_efectos_retiro",
]
