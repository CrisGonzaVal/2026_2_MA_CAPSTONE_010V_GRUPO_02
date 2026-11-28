"""Enmienda 26/Nov/2026 de la 013: confirmacion final y bloqueo de la anulacion.

Fase ROJA de TDD (T32). La confirmacion del Solicitante dueño conserva su
contrato (acuse `Cerrado -> Cerrado` con el motivo canonico) y gana una
precision: **una vez confirmada, el retiro no se anula** (D-34/AC-61). Si la
anulacion gana primero, la confirmacion posterior ve `Anulado` y responde 409.

Tambien fija la lectura `entrega_confirmada` fuera de `Cerrado` (spec §10.5):
un pedido `Anulado` con una fila de confirmacion previa responde 409 y no se
presenta como entregado.
"""

from __future__ import annotations

import pytest

from tests.funcional.integracion._soporte_retiro_013 import (
    FECHA_CIERRE,
    MOTIVO_CONFIRMACION,
    anular,
    cliente_rol,
    confirmar,
    entregas_de_ticket,
    estado_de_ticket,
    fecha_cierre_de_ticket,
    historial_persistido,
    marcar_confirmado,
    sembrar_mundo_retiro,
    sembrar_ticket_retiro,
    stock_de,
)

MOTIVO_ANULACION = "El retiro se registro sobre el pedido equivocado"


def _sembrar_cerrado(motor, datos, *, entregada: int = 3):
    return sembrar_ticket_retiro(
        motor,
        datos,
        estado="Cerrado",
        detalles=[(datos["producto_id"], entregada, entregada)],
        fecha_cierre=FECHA_CIERRE,
    )


def test_el_dueno_confirma_y_el_estado_sigue_cerrado_ac_61(motor, dos_instituciones):
    """AC-61: 200, `Cerrado`, fecha y cantidades intactas, fila canonica."""
    datos = sembrar_mundo_retiro(motor, dos_instituciones)
    ticket_id = _sembrar_cerrado(motor, datos, entregada=3)
    stock_antes = stock_de(motor, datos["sede_id"], datos["producto_id"])

    with cliente_rol(motor, datos, "Solicitante") as cliente:
        respuesta = confirmar(cliente, ticket_id)

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["estado_id"] == datos["estados"]["Cerrado"]
    assert cuerpo["fecha_cierre"] is not None
    assert [d["cantidad_entregada"] for d in cuerpo["detalles"]] == [3]
    assert cuerpo["entrega_confirmada"] is True
    assert stock_de(motor, datos["sede_id"], datos["producto_id"]) == stock_antes

    filas = historial_persistido(motor, ticket_id)
    assert len(filas) == 1, f"exactamente una fila por confirmacion: {filas}"
    assert filas[0]["estado_origen_id"] == datos["estados"]["Cerrado"]
    assert filas[0]["estado_destino_id"] == datos["estados"]["Cerrado"]
    assert filas[0]["motivo"] == MOTIVO_CONFIRMACION
    assert filas[0]["usuario_id"] == datos["usuarios_inst01"]["Solicitante"]


def test_una_anulacion_despues_de_la_confirmacion_responde_409_ac_61(
    motor, dos_instituciones
):
    """AC-61/D-34: confirmado no se anula; la fila canonica no se borra."""
    datos = sembrar_mundo_retiro(motor, dos_instituciones)
    ticket_id = _sembrar_cerrado(motor, datos, entregada=3)

    with cliente_rol(motor, datos, "Solicitante") as cliente:
        confirmacion = confirmar(cliente, ticket_id)
        assert confirmacion.status_code == 200, confirmacion.text

    filas_antes = historial_persistido(motor, ticket_id)

    with cliente_rol(motor, datos, "Administrador") as cliente:
        anulacion = anular(cliente, ticket_id, MOTIVO_ANULACION)

    assert anulacion.status_code == 409, anulacion.text
    assert estado_de_ticket(motor, ticket_id) == datos["estados"]["Cerrado"]
    assert fecha_cierre_de_ticket(motor, ticket_id) is not None
    assert stock_de(motor, datos["sede_id"], datos["producto_id"]) == 50
    assert historial_persistido(motor, ticket_id) == filas_antes, (
        "el 409 no puede borrar ni reescribir la confirmacion"
    )


def test_una_confirmacion_despues_de_la_anulacion_responde_409_ac_61(
    motor, dos_instituciones
):
    """AC-61: si la anulacion gana, el pedido esta `Anulado` y confirma 409."""
    datos = sembrar_mundo_retiro(motor, dos_instituciones)
    ticket_id = _sembrar_cerrado(motor, datos, entregada=3)

    with cliente_rol(motor, datos, "Administrador") as cliente:
        anulacion = anular(cliente, ticket_id, MOTIVO_ANULACION)

    assert anulacion.status_code == 200, anulacion.text
    assert anulacion.json()["estado_id"] == datos["estados"]["Anulado"]

    with cliente_rol(motor, datos, "Solicitante") as cliente:
        confirmacion = confirmar(cliente, ticket_id)

    assert confirmacion.status_code == 409, confirmacion.text
    assert estado_de_ticket(motor, ticket_id) == datos["estados"]["Anulado"]
    assert entregas_de_ticket(motor, ticket_id) == {
        anulacion.json()["detalles"][0]["detalle_ticket_id"]: 0
    }


def test_un_anulado_con_confirmacion_previa_no_se_presenta_entregado_ac_61(
    motor, dos_instituciones
):
    """Spec §10.5: `entrega_confirmada` no es `true` fuera de `Cerrado`."""
    datos = sembrar_mundo_retiro(motor, dos_instituciones)
    ticket_id = sembrar_ticket_retiro(motor, datos, estado="Anulado")
    marcar_confirmado(motor, datos, ticket_id)

    with cliente_rol(motor, datos, "Solicitante") as cliente:
        listado = cliente.get("/api/v1/tickets/")

    assert listado.status_code == 200, listado.text
    ticket = next(
        t for t in listado.json() if t["ticket_id"] == ticket_id
    )
    assert ticket["estado_id"] == datos["estados"]["Anulado"]
    assert ticket["entrega_confirmada"] is False, (
        "un Anulado no puede presentarse como entregado aunque conserve la "
        "fila de una confirmacion previa"
    )


def test_la_confirmacion_solo_la_hace_el_dueno_ac_61(motor, dos_instituciones):
    """AC-61: el Solicitante no dueño recibe 404 oculto; el Administrador, 403."""
    datos = sembrar_mundo_retiro(motor, dos_instituciones)
    ticket_id = _sembrar_cerrado(motor, datos, entregada=3)

    with cliente_rol(
        motor, datos, "Solicitante", usuario_id=datos["usuarios_inst02"]["Solicitante"]
    ) as cliente:
        ajeno = confirmar(cliente, ticket_id)

    with cliente_rol(motor, datos, "Administrador") as cliente:
        administrador = confirmar(cliente, ticket_id)

    assert ajeno.status_code == 404, ajeno.text
    assert administrador.status_code == 403, administrador.text
    assert historial_persistido(motor, ticket_id) == []


@pytest.mark.parametrize("estado", ["EnCurso", "Anulado"])
def test_la_confirmacion_fuera_de_cerrado_responde_409_ac_61(
    motor, dos_instituciones, estado
):
    """AC-61: solo un `Cerrado` se confirma."""
    datos = sembrar_mundo_retiro(motor, dos_instituciones)
    ticket_id = sembrar_ticket_retiro(motor, datos, estado=estado)

    with cliente_rol(motor, datos, "Solicitante") as cliente:
        respuesta = confirmar(cliente, ticket_id)

    assert respuesta.status_code == 409, respuesta.text
