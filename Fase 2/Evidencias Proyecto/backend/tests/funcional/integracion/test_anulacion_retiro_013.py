"""Enmienda 26/Nov/2026 de la 013: anulacion administrativa del retiro (AC-58).

Fase ROJA de TDD (T32). El contrato nuevo permite al **Administrador** anular un
pedido `Cerrado` **sin confirmar**: devuelve el stock con una `ENTRADA` por
detalle entregado, crea la fila `stock_sede` si falta, resetea
`cantidad_entregada`, deja `fecha_cierre` nula, pasa a `Anulado` y escribe la
fila `Cerrado -> Anulado` con actor y motivo, todo en una transaccion (D-32).

La ruta `/anulacion` ya existe, asi que estas pruebas no necesitan guarda de
capacidad: fallan por comportamiento (hoy todo `Cerrado` responde 409).
"""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tests.funcional.integracion._soporte_retiro_013 import (
    FECHA_CIERRE,
    MOTIVO_CONFIRMACION,
    anular,
    cliente_rol,
    eliminar_fila_de_stock,
    entradas_devolucion,
    entregas_de_ticket,
    estado_de_ticket,
    fecha_cierre_de_ticket,
    historial_persistido,
    marcar_confirmado,
    rechazar,
    sembrar_mundo_retiro,
    sembrar_ticket_retiro,
    stock_de,
)

MOTIVO_ANULACION = "Retiro registrado por error en la bodega"


def _sembrar_cerrado(motor, datos, *, entregada: int = 3, sede_id="auto"):
    """Pedido `Cerrado` con la cantidad entregada y la fecha que dejo el retiro."""
    kwargs = {} if sede_id == "auto" else {"sede_id": sede_id}
    return sembrar_ticket_retiro(
        motor,
        datos,
        estado="Cerrado",
        detalles=[(datos["producto_id"], entregada, entregada)],
        fecha_cierre=FECHA_CIERRE,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# AC-58: devolucion de stock, reset y cierre administrativo
# ---------------------------------------------------------------------------


def test_el_administrador_anula_el_retiro_y_devuelve_el_stock_ac_58(
    motor, dos_instituciones
):
    """AC-58/D-32: 200, `Anulado`, `ENTRADA` por detalle, reset y fecha nula."""
    datos = sembrar_mundo_retiro(motor, dos_instituciones)
    ticket_id = _sembrar_cerrado(motor, datos, entregada=3)
    stock_antes = stock_de(motor, datos["sede_id"], datos["producto_id"])

    with cliente_rol(motor, datos, "Administrador") as cliente:
        respuesta = anular(cliente, ticket_id, MOTIVO_ANULACION)

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["estado_id"] == datos["estados"]["Anulado"]
    assert cuerpo["fecha_cierre"] is None, (
        "D-32: un `Anulado` no conserva `fecha_cierre`; la fecha del retiro "
        "vive en la fila `EnCurso -> Cerrado` del historial"
    )
    assert [d["cantidad_entregada"] for d in cuerpo["detalles"]] == [0]

    assert stock_de(motor, datos["sede_id"], datos["producto_id"]) == stock_antes + 3
    assert entregas_de_ticket(motor, ticket_id) == {
        cuerpo["detalles"][0]["detalle_ticket_id"]: 0
    }

    entradas = entradas_devolucion(motor, ticket_id)
    assert len(entradas) == 1, f"se esperaba una sola ENTRADA: {entradas}"
    assert entradas[0]["tipo_movimiento"] == "ENTRADA"
    assert entradas[0]["cantidad"] == 3
    assert entradas[0]["sede_id"] == datos["sede_id"]
    assert entradas[0]["stock_sede_id"] is not None
    esperada = (
        f"Devolución por anulación del retiro del ticket #{ticket_id}; "
        f"detalle_id={cuerpo['detalles'][0]['detalle_ticket_id']}; "
        f"producto_id={datos['producto_id']}"
    )
    assert entradas[0]["observacion"] == esperada

    filas = historial_persistido(motor, ticket_id)
    cierre = [
        fila
        for fila in filas
        if fila["estado_origen_id"] == datos["estados"]["Cerrado"]
        and fila["estado_destino_id"] == datos["estados"]["Anulado"]
    ]
    assert len(cierre) == 1, f"se esperaba una fila Cerrado -> Anulado: {filas}"
    assert cierre[0]["usuario_id"] == datos["usuario_id"]
    assert cierre[0]["motivo"] == MOTIVO_ANULACION


def test_solo_los_detalles_con_cantidad_entregada_generan_entrada_ac_58(
    motor, dos_instituciones
):
    """AC-58: un detalle con `cantidad_entregada = 0` no genera `ENTRADA`."""
    datos = sembrar_mundo_retiro(motor, dos_instituciones)
    ticket_id = sembrar_ticket_retiro(
        motor,
        datos,
        estado="Cerrado",
        detalles=[
            (datos["producto_id"], 3, 2),
            (datos["producto_id"], 5, 0),
        ],
        fecha_cierre=FECHA_CIERRE,
    )

    with cliente_rol(motor, datos, "Administrador") as cliente:
        respuesta = anular(cliente, ticket_id, MOTIVO_ANULACION)

    assert respuesta.status_code == 200, respuesta.text
    assert [d["cantidad_entregada"] for d in respuesta.json()["detalles"]] == [0, 0]
    entradas = entradas_devolucion(motor, ticket_id)
    assert len(entradas) == 1, "solo el detalle con entrega devuelve stock"
    assert entradas[0]["cantidad"] == 2


def test_la_anulacion_crea_la_fila_de_stock_si_falta_ac_58(motor, dos_instituciones):
    """D-32: si `stock_sede` no existe, se crea con el stock devuelto."""
    datos = sembrar_mundo_retiro(motor, dos_instituciones)
    ticket_id = _sembrar_cerrado(motor, datos, entregada=2)
    eliminar_fila_de_stock(
        motor, sede_id=datos["sede_id"], producto_id=datos["producto_id"]
    )
    assert stock_de(motor, datos["sede_id"], datos["producto_id"]) is None

    with cliente_rol(motor, datos, "Administrador") as cliente:
        respuesta = anular(cliente, ticket_id, MOTIVO_ANULACION)

    assert respuesta.status_code == 200, respuesta.text
    assert stock_de(motor, datos["sede_id"], datos["producto_id"]) == 2
    assert len(entradas_devolucion(motor, ticket_id)) == 1


# ---------------------------------------------------------------------------
# AC-58: actores y precondiciones
# ---------------------------------------------------------------------------


def test_el_solicitante_no_anula_un_retiro_ac_58(motor, dos_instituciones):
    """AC-58/D-33: el dueño recibe 409 y el detalle declara la via administrativa."""
    datos = sembrar_mundo_retiro(motor, dos_instituciones)
    ticket_id = _sembrar_cerrado(motor, datos, entregada=3)

    with cliente_rol(motor, datos, "Solicitante") as cliente:
        respuesta = anular(cliente, ticket_id, MOTIVO_ANULACION)

    assert respuesta.status_code == 409, respuesta.text
    assert "administrativ" in respuesta.json()["detail"].lower(), (
        "el 409 del dueño debe explicar que la anulacion del retiro es "
        "administrativa (D-33)"
    )
    assert estado_de_ticket(motor, ticket_id) == datos["estados"]["Cerrado"]
    assert fecha_cierre_de_ticket(motor, ticket_id) == FECHA_CIERRE
    assert list(entregas_de_ticket(motor, ticket_id).values()) == [3]
    assert stock_de(motor, datos["sede_id"], datos["producto_id"]) == 50
    assert entradas_devolucion(motor, ticket_id) == []


def test_un_retiro_confirmado_no_se_anula_ac_58_61(motor, dos_instituciones):
    """AC-58/AC-61: con la confirmacion canonica, 409 sin borrar su fila."""
    datos = sembrar_mundo_retiro(motor, dos_instituciones)
    ticket_id = _sembrar_cerrado(motor, datos, entregada=3)
    marcar_confirmado(motor, datos, ticket_id)
    filas_antes = historial_persistido(motor, ticket_id)

    with cliente_rol(motor, datos, "Administrador") as cliente:
        respuesta = anular(cliente, ticket_id, MOTIVO_ANULACION)

    assert respuesta.status_code == 409, respuesta.text
    assert estado_de_ticket(motor, ticket_id) == datos["estados"]["Cerrado"]
    assert fecha_cierre_de_ticket(motor, ticket_id) is not None
    assert stock_de(motor, datos["sede_id"], datos["producto_id"]) == 50
    assert entradas_devolucion(motor, ticket_id) == []
    filas_despues = historial_persistido(motor, ticket_id)
    assert filas_despues == filas_antes, (
        "la confirmacion es inmutable: el 409 no borra ni reescribe su fila"
    )
    assert any(
        fila["estado_origen_id"] == datos["estados"]["Cerrado"]
        and fila["estado_destino_id"] == datos["estados"]["Cerrado"]
        and fila["motivo"] == MOTIVO_CONFIRMACION
        for fila in filas_despues
    )


def test_el_rechazo_sobre_un_cerrado_no_devuelve_stock_ac_58(dos_instituciones, motor):
    """D-40.1: `/rechazo` sobre `Cerrado` es 409 y nunca crea una `ENTRADA`."""
    datos = sembrar_mundo_retiro(motor, dos_instituciones)
    ticket_id = _sembrar_cerrado(motor, datos, entregada=3)

    with cliente_rol(motor, datos, "Bodeguero") as cliente:
        respuesta = rechazar(cliente, ticket_id, "Rechazo posterior al retiro")

    assert respuesta.status_code == 409, respuesta.text
    assert estado_de_ticket(motor, ticket_id) == datos["estados"]["Cerrado"]
    assert stock_de(motor, datos["sede_id"], datos["producto_id"]) == 50
    assert entradas_devolucion(motor, ticket_id) == []


def test_un_cerrado_sin_sede_no_se_anula_con_devolucion_ac_58(
    motor, dos_instituciones
):
    """D-40.2: sin sede no hay destino del stock; 409 sin escribir."""
    datos = sembrar_mundo_retiro(motor, dos_instituciones)
    ticket_id = _sembrar_cerrado(motor, datos, entregada=3, sede_id=None)

    with cliente_rol(motor, datos, "Administrador") as cliente:
        respuesta = anular(cliente, ticket_id, MOTIVO_ANULACION)

    assert respuesta.status_code == 409, respuesta.text
    assert estado_de_ticket(motor, ticket_id) == datos["estados"]["Cerrado"]
    assert stock_de(motor, datos["sede_id"], datos["producto_id"]) == 50
    assert entradas_devolucion(motor, ticket_id) == []


@pytest.mark.parametrize("motivo", ["", "   ", "x" * 501])
def test_un_motivo_invalido_responde_422_ac_58(motor, dos_instituciones, motivo):
    """AC-58: desde un `Cerrado` valido, el motivo se valida despues del estado."""
    datos = sembrar_mundo_retiro(motor, dos_instituciones)
    ticket_id = _sembrar_cerrado(motor, datos, entregada=3)

    with cliente_rol(motor, datos, "Administrador") as cliente:
        respuesta = anular(cliente, ticket_id, motivo)

    assert respuesta.status_code == 422, respuesta.text
    assert estado_de_ticket(motor, ticket_id) == datos["estados"]["Cerrado"]
    assert entradas_devolucion(motor, ticket_id) == []


@pytest.mark.parametrize("estado", ["EnCurso", "Anulado"])
def test_un_estado_no_anulable_responde_409_ac_58(
    motor, dos_instituciones, estado
):
    """AC-58: `EnCurso` y `Anulado` no admiten la anulacion."""
    datos = sembrar_mundo_retiro(motor, dos_instituciones)
    ticket_id = sembrar_ticket_retiro(motor, datos, estado=estado)

    with cliente_rol(motor, datos, "Administrador") as cliente:
        respuesta = anular(cliente, ticket_id, MOTIVO_ANULACION)

    assert respuesta.status_code == 409, respuesta.text
    assert entradas_devolucion(motor, ticket_id) == []


def test_el_choque_de_unicidad_al_crear_stock_sede_se_traduce_a_409_ac_59(
    monkeypatch, motor, dos_instituciones
):
    """D-40.3: una carrera de creacion no puede terminar en 500 ni dejar stock."""
    datos = sembrar_mundo_retiro(motor, dos_instituciones)
    ticket_id = _sembrar_cerrado(motor, datos, entregada=2)
    eliminar_fila_de_stock(
        motor, sede_id=datos["sede_id"], producto_id=datos["producto_id"]
    )

    def commit_con_choque_de_unicidad(self):
        raise IntegrityError(
            "INSERT INTO stock_sede",
            {},
            Exception("duplicate key value violates stock_sede_sede_producto_uk"),
        )

    monkeypatch.setattr(Session, "commit", commit_con_choque_de_unicidad)

    with cliente_rol(motor, datos, "Administrador") as cliente:
        respuesta = anular(cliente, ticket_id, MOTIVO_ANULACION)

    assert respuesta.status_code == 409, respuesta.text
    assert "X-Request-ID" in respuesta.headers
    monkeypatch.undo()
    assert estado_de_ticket(motor, ticket_id) == datos["estados"]["Cerrado"]
    assert stock_de(motor, datos["sede_id"], datos["producto_id"]) is None
    assert entradas_devolucion(motor, ticket_id) == []


def test_la_anulacion_crea_una_sola_fila_de_stock_para_varios_detalles_ac_58(
    motor, dos_instituciones
):
    """D-32: dos detalles del mismo producto comparten el saldo creado."""
    datos = sembrar_mundo_retiro(motor, dos_instituciones)
    ticket_id = sembrar_ticket_retiro(
        motor,
        datos,
        estado="Cerrado",
        detalles=[
            (datos["producto_id"], 2, 2),
            (datos["producto_id"], 3, 3),
        ],
        fecha_cierre=FECHA_CIERRE,
    )
    eliminar_fila_de_stock(
        motor, sede_id=datos["sede_id"], producto_id=datos["producto_id"]
    )

    with cliente_rol(motor, datos, "Administrador") as cliente:
        respuesta = anular(cliente, ticket_id, MOTIVO_ANULACION)

    assert respuesta.status_code == 200, respuesta.text
    assert stock_de(motor, datos["sede_id"], datos["producto_id"]) == 5
    entradas = entradas_devolucion(motor, ticket_id)
    assert [entrada["cantidad"] for entrada in entradas] == [2, 3], (
        "una ENTRADA por detalle, con su cantidad entregada"
    )
    assert len({entrada["stock_sede_id"] for entrada in entradas}) == 1, (
        "el saldo creado se reutiliza para los dos detalles del mismo producto"
    )


def test_la_anulacion_es_atomica_si_falla_la_auditoria_ac_59(
    monkeypatch, motor, dos_instituciones
):
    """AC-59: un fallo tras mutar revierte stock, cantidades, fecha, estado y filas."""
    from app.services import ticket_service

    datos = sembrar_mundo_retiro(motor, dos_instituciones)
    ticket_id = _sembrar_cerrado(motor, datos, entregada=3)
    entregas_antes = entregas_de_ticket(motor, ticket_id)
    filas_antes = historial_persistido(motor, ticket_id)

    def transicion_que_falla(*args, **kwargs):
        raise RuntimeError("fallo inyectado al registrar la transicion")

    monkeypatch.setattr(
        ticket_service, "_registrar_transicion", transicion_que_falla
    )

    with cliente_rol(motor, datos, "Administrador") as cliente:
        respuesta = anular(cliente, ticket_id, MOTIVO_ANULACION)

    assert respuesta.status_code == 500, respuesta.text
    monkeypatch.undo()
    assert estado_de_ticket(motor, ticket_id) == datos["estados"]["Cerrado"]
    assert fecha_cierre_de_ticket(motor, ticket_id) == FECHA_CIERRE
    assert entregas_de_ticket(motor, ticket_id) == entregas_antes, (
        "la devolucion no puede dejar las cantidades reseteadas"
    )
    assert stock_de(motor, datos["sede_id"], datos["producto_id"]) == 50, (
        "la devolucion no puede quedar aplicada"
    )
    assert entradas_devolucion(motor, ticket_id) == []
    assert historial_persistido(motor, ticket_id) == filas_antes


def test_la_anulacion_desde_enrevision_conserva_su_contrato_sin_stock_ac_54(
    motor, dos_instituciones
):
    """AC-54/AC-58: la rama `EnRevision` no toca stock ni `fecha_cierre`."""
    datos = sembrar_mundo_retiro(motor, dos_instituciones)
    ticket_id = sembrar_ticket_retiro(motor, datos, estado="EnRevision")

    with cliente_rol(motor, datos, "Administrador") as cliente:
        respuesta = anular(cliente, ticket_id, MOTIVO_ANULACION)

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["estado_id"] == datos["estados"]["Anulado"]
    assert respuesta.json()["fecha_cierre"] is None
    assert stock_de(motor, datos["sede_id"], datos["producto_id"]) == 50
    assert entradas_devolucion(motor, ticket_id) == []


def test_el_catalogo_sin_anulado_responde_409(motor, dos_instituciones):
    """AC-58: sin el nombre `Anulado` la operacion no puede resolver su destino."""
    datos = sembrar_mundo_retiro(
        motor,
        dos_instituciones,
        nombres_estados=("EnRevision", "EnCurso", "Cerrado"),
    )
    ticket_id = sembrar_ticket_retiro(motor, datos, estado="Cerrado")

    with cliente_rol(motor, datos, "Administrador") as cliente:
        respuesta = anular(cliente, ticket_id, MOTIVO_ANULACION)

    assert respuesta.status_code == 409, respuesta.text
    assert entradas_devolucion(motor, ticket_id) == []
