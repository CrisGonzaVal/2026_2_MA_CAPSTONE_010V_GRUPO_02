"""Enmienda 26/Nov/2026 de la 013: retiro acotado a la sede del Bodeguero (AC-56).

Fase ROJA de TDD (T32). Se fijan las tres variantes del ambito de D-30:

* pedido de la sede del Bodeguero: se retira con normalidad;
* pedido de **otra** sede: 404 **identico** al inexistente, sin revelar
  existencia ni tocar stock;
* Bodeguero **sin sede**: 409 de precondicion del actor, sin fallback.

Mientras `/retiro` no exista (T35), cada caso falla por `exigir_retiro_publicado`.
"""

from __future__ import annotations

from tests.funcional.integracion._soporte_retiro_013 import (
    DETALLE_TICKET_NO_ENCONTRADO,
    cliente_rol,
    crear_sede,
    exigir_retiro_publicado,
    historial_persistido,
    retirar,
    salidas_retiro,
    sembrar_mundo_retiro,
    sembrar_ticket_retiro,
    stock_de,
    verificar_sin_efectos_retiro,
)


def test_el_bodeguero_retira_un_pedido_de_su_sede_ac_56(motor, dos_instituciones):
    """AC-56: con sede propia y pedido de esa sede, el retiro es 200."""
    datos = sembrar_mundo_retiro(motor, dos_instituciones)
    ticket_id = sembrar_ticket_retiro(motor, datos, estado="EnCurso")

    exigir_retiro_publicado()
    with cliente_rol(motor, datos, "Bodeguero") as cliente:
        respuesta = retirar(
            cliente,
            ticket_id,
            {"usuario_id": datos["usuarios_inst01"]["Bodeguero"]},
        )

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["estado_id"] == datos["estados"]["Cerrado"]
    assert len(historial_persistido(motor, ticket_id)) == 1


def test_el_bodeguero_no_retira_un_pedido_de_otra_sede_ac_56(
    motor, dos_instituciones
):
    """AC-56: otra sede responde el mismo 404 que un ticket inexistente."""
    datos = sembrar_mundo_retiro(motor, dos_instituciones)
    sede_ajena = crear_sede(
        motor, institucion_id=datos["institucion_id"], nombre="Sede Ajena"
    )
    ticket_id = sembrar_ticket_retiro(
        motor, datos, estado="EnCurso", sede_id=sede_ajena
    )
    stock_antes = stock_de(motor, sede_ajena, datos["producto_id"])

    exigir_retiro_publicado()
    with cliente_rol(motor, datos, "Bodeguero") as cliente:
        ajeno = retirar(
            cliente,
            ticket_id,
            {"usuario_id": datos["usuarios_inst01"]["Bodeguero"]},
        )
        inexistente = retirar(
            cliente,
            999999,
            {"usuario_id": datos["usuarios_inst01"]["Bodeguero"]},
        )

    assert ajeno.status_code == 404, ajeno.text
    assert inexistente.status_code == 404, inexistente.text
    assert ajeno.json()["detail"] == inexistente.json()["detail"], (
        "el 404 de otra sede debe ser identico al del ticket inexistente"
    )
    assert ajeno.json()["detail"] == DETALLE_TICKET_NO_ENCONTRADO
    assert stock_de(motor, sede_ajena, datos["producto_id"]) == stock_antes, (
        "un pedido de otra sede no puede rebajar su stock"
    )
    assert salidas_retiro(motor, ticket_id) == []


def test_el_bodeguero_sin_sede_no_puede_retirar_ac_56(motor, dos_instituciones):
    """AC-56: sin sede asignada, 409 de precondicion del actor (sin fallback)."""
    datos = sembrar_mundo_retiro(motor, dos_instituciones)
    ticket_id = sembrar_ticket_retiro(motor, datos, estado="EnCurso")

    exigir_retiro_publicado()
    with cliente_rol(
        motor, datos, "Bodeguero", sede_id=None
    ) as cliente:
        respuesta = retirar(
            cliente,
            ticket_id,
            {"usuario_id": datos["usuarios_inst01"]["Bodeguero"]},
        )

    assert respuesta.status_code == 409, respuesta.text
    assert "sede" in respuesta.json()["detail"].lower()
    verificar_sin_efectos_retiro(
        motor,
        datos,
        ticket_id,
        estado="EnCurso",
        stocks={(datos["sede_id"], datos["producto_id"]): 50},
    )


def test_un_ticket_sin_sede_no_se_retira_ac_56(motor, dos_instituciones):
    """D-30/AC-56: el pedido sin instantanea de sede responde 409 sin escribir."""
    datos = sembrar_mundo_retiro(motor, dos_instituciones)
    ticket_id = sembrar_ticket_retiro(
        motor, datos, estado="EnCurso", sede_id=None
    )

    exigir_retiro_publicado()
    with cliente_rol(motor, datos, "Bodeguero") as cliente:
        respuesta = retirar(
            cliente,
            ticket_id,
            {"usuario_id": datos["usuarios_inst01"]["Bodeguero"]},
        )

    assert respuesta.status_code == 409, respuesta.text
    verificar_sin_efectos_retiro(
        motor,
        datos,
        ticket_id,
        estado="EnCurso",
        stocks={(datos["sede_id"], datos["producto_id"]): 50},
    )
