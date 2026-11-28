"""Enmienda 26/Nov/2026 de la 013: retiro transaccional (AC-55 y AC-57).

Fase ROJA de TDD (T32). El contrato nuevo publica `POST /tickets/{id}/retiro`
(DTO `TicketRetiro`, servicio `registrar_retiro_ticket`) en lugar de
`/despacho`; esta suite habla HTTP con JSON crudo y **no importa** los simbolos
que aun no existen. Cada caso que esperaria `200`/`403`/`409`/`422` ejecuta
antes `exigir_retiro_publicado()`: mientras la ruta no exista, la prueba falla
por la capacidad ausente (T35) y no por el `404` del router.

Seam: interfaz HTTP del `app` real. La auditoria (`movimiento_inventario`) y el
historial se leen por ORM porque no todos los casos tienen una lectura HTTP
equivalente; el resto se observa releyendo el ticket y el stock.
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from tests.funcional.integracion._soporte_retiro_013 import (
    RUTA_DESPACHO,
    RUTA_RETIRO,
    cliente_rol,
    crear_producto_con_stock,
    exigir_retiro_publicado,
    historial_persistido,
    retirar,
    salidas_retiro,
    sembrar_mundo_retiro,
    sembrar_ticket_retiro,
    stock_de,
    verificar_sin_efectos_retiro,
)


# ---------------------------------------------------------------------------
# AC-55: contrato publicado, ruta renombrada y roles
# ---------------------------------------------------------------------------


def test_el_contrato_publica_retiro_y_retira_despacho_ac_55(cliente):
    """AC-55: `/retiro` publicada con `TicketRetiro`; `/despacho` ya no existe."""
    exigir_retiro_publicado()
    contrato = cliente.get("/openapi.json").json()

    operacion = contrato["paths"][RUTA_RETIRO]["post"]
    peticion = operacion["requestBody"]["content"]["application/json"]["schema"][
        "$ref"
    ]
    assert peticion.endswith("TicketRetiro"), peticion
    respuesta = operacion["responses"]["200"]["content"]["application/json"][
        "schema"
    ]["$ref"]
    assert respuesta.endswith("TicketRespuesta"), respuesta
    for codigo in ("404", "409", "422"):
        assert codigo in operacion["description"], f"falta documentar el {codigo}"
    assert RUTA_DESPACHO not in contrato["paths"], (
        "D-29: la ruta historica /despacho deja de publicarse"
    )


def test_el_bodeguero_retira_y_cierra_el_pedido_ac_55_57(motor, dos_instituciones):
    """AC-55/AC-57: 200, `Cerrado`, fecha, entrega completa e historial."""
    datos = sembrar_mundo_retiro(motor, dos_instituciones)
    ticket_id = sembrar_ticket_retiro(motor, datos, estado="EnCurso")
    stock_antes = stock_de(motor, datos["sede_id"], datos["producto_id"])

    exigir_retiro_publicado()
    with cliente_rol(motor, datos, "Bodeguero") as cliente:
        respuesta = retirar(
            cliente,
            ticket_id,
            {"usuario_id": datos["usuarios_inst01"]["Bodeguero"]},
        )

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["ticket_id"] == ticket_id
    assert cuerpo["estado_id"] == datos["estados"]["Cerrado"]
    assert cuerpo["fecha_cierre"] is not None
    assert [d["cantidad_entregada"] for d in cuerpo["detalles"]] == [3]
    assert [d["cantidad_solicitada"] for d in cuerpo["detalles"]] == [3]
    assert stock_de(motor, datos["sede_id"], datos["producto_id"]) == stock_antes - 3

    filas = historial_persistido(motor, ticket_id)
    assert len(filas) == 1, f"se esperaba una sola transicion: {filas}"
    assert filas[0]["estado_origen_id"] == datos["estados"]["EnCurso"]
    assert filas[0]["estado_destino_id"] == datos["estados"]["Cerrado"]
    assert filas[0]["usuario_id"] == datos["usuarios_inst01"]["Bodeguero"]
    assert filas[0]["motivo"] is None, "el retiro no exige motivo (D-29)"


def test_el_retiro_registra_una_salida_con_la_observacion_literal_ac_57(
    motor, dos_instituciones
):
    """AC-57/D-29: una `SALIDA` por detalle con la observacion exacta."""
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
    detalle = respuesta.json()["detalles"][0]
    esperada = (
        f"Salida por retiro del ticket #{ticket_id}; "
        f"detalle_id={detalle['detalle_ticket_id']}; "
        f"producto_id={datos['producto_id']}"
    )

    salidas = salidas_retiro(motor, ticket_id)
    assert len(salidas) == 1, f"se esperaba una sola SALIDA: {salidas}"
    assert salidas[0]["tipo_movimiento"] == "SALIDA"
    assert salidas[0]["cantidad"] == 3
    assert salidas[0]["sede_id"] == datos["sede_id"]
    assert salidas[0]["stock_sede_id"] is not None
    assert salidas[0]["observacion"] == esperada


def test_dos_lineas_del_mismo_producto_dejan_una_salida_por_linea_ac_57(
    motor, dos_instituciones
):
    """AC-57: líneas repetidas se auditan por separado y el stock baja por la suma."""
    datos = sembrar_mundo_retiro(motor, dos_instituciones)
    ticket_id = sembrar_ticket_retiro(
        motor,
        datos,
        estado="EnCurso",
        detalles=[
            (datos["producto_id"], 3, 0),
            (datos["producto_id"], 4, 0),
        ],
    )
    stock_antes = stock_de(motor, datos["sede_id"], datos["producto_id"])

    exigir_retiro_publicado()
    with cliente_rol(motor, datos, "Bodeguero") as cliente:
        respuesta = retirar(
            cliente,
            ticket_id,
            {"usuario_id": datos["usuarios_inst01"]["Bodeguero"]},
        )

    assert respuesta.status_code == 200, respuesta.text
    detalles = sorted(
        respuesta.json()["detalles"], key=lambda d: d["detalle_ticket_id"]
    )
    assert [d["cantidad_entregada"] for d in detalles] == [3, 4]
    assert stock_de(motor, datos["sede_id"], datos["producto_id"]) == stock_antes - 7

    salidas = salidas_retiro(motor, ticket_id)
    assert len(salidas) == 2, "cada linea conserva su propio movimiento (D-7)"
    assert sorted(salida["cantidad"] for salida in salidas) == [3, 4]


@pytest.mark.parametrize("rol", ["Administrador", "Solicitante", "Superadmin"])
def test_el_retiro_es_solo_del_bodeguero_ac_55(motor, dos_instituciones, rol):
    """AC-55/D-30: cualquier otro rol recibe 403 por matriz."""
    datos = sembrar_mundo_retiro(motor, dos_instituciones)
    ticket_id = sembrar_ticket_retiro(motor, datos, estado="EnCurso")

    exigir_retiro_publicado()
    with cliente_rol(motor, datos, rol) as cliente:
        respuesta = retirar(
            cliente,
            ticket_id,
            {"usuario_id": datos["usuarios_inst01"][rol]},
        )

    assert respuesta.status_code == 403, respuesta.text
    assert stock_de(motor, datos["sede_id"], datos["producto_id"]) == 50


def test_el_retiro_sin_payload_responde_422_ac_55(motor, dos_instituciones):
    """AC-55: `usuario_id` es obligatorio."""
    datos = sembrar_mundo_retiro(motor, dos_instituciones)
    ticket_id = sembrar_ticket_retiro(motor, datos, estado="EnCurso")

    exigir_retiro_publicado()
    with cliente_rol(motor, datos, "Bodeguero") as cliente:
        respuesta = retirar(cliente, ticket_id)

    assert respuesta.status_code == 422, respuesta.text


def test_el_retiro_con_usuario_id_no_entero_responde_422_ac_55(
    motor, dos_instituciones
):
    """AC-55: un id no entero es error de forma, no de referencia."""
    datos = sembrar_mundo_retiro(motor, dos_instituciones)
    ticket_id = sembrar_ticket_retiro(motor, datos, estado="EnCurso")

    exigir_retiro_publicado()
    with cliente_rol(motor, datos, "Bodeguero") as cliente:
        respuesta = retirar(cliente, ticket_id, {"usuario_id": "no-es-entero"})

    assert respuesta.status_code == 422, respuesta.text


def test_el_retiro_con_usuario_inexistente_responde_404_sin_efectos_ac_55(
    motor, dos_instituciones
):
    """AC-55: el actor del payload debe existir; 404 sin tocar el ticket."""
    datos = sembrar_mundo_retiro(motor, dos_instituciones)
    ticket_id = sembrar_ticket_retiro(motor, datos, estado="EnCurso")

    exigir_retiro_publicado()
    with cliente_rol(motor, datos, "Bodeguero") as cliente:
        respuesta = retirar(cliente, ticket_id, {"usuario_id": 999999})

    assert respuesta.status_code == 404, respuesta.text
    assert "usuario" in respuesta.json()["detail"].lower()
    verificar_sin_efectos_retiro(
        motor,
        datos,
        ticket_id,
        estado="EnCurso",
        stocks={(datos["sede_id"], datos["producto_id"]): 50},
    )


def test_el_retiro_de_un_ticket_inexistente_responde_404_ac_55(
    motor, dos_instituciones
):
    """AC-55: ticket inexistente, 404 identico al oculto."""
    datos = sembrar_mundo_retiro(motor, dos_instituciones)

    exigir_retiro_publicado()
    with cliente_rol(motor, datos, "Bodeguero") as cliente:
        respuesta = retirar(
            cliente, 999999, {"usuario_id": datos["usuarios_inst01"]["Bodeguero"]}
        )

    assert respuesta.status_code == 404, respuesta.text
    assert "ticket" in respuesta.json()["detail"].lower()


# ---------------------------------------------------------------------------
# AC-57: precondiciones y atomicidad
# ---------------------------------------------------------------------------


def test_el_retiro_rechaza_un_pedido_que_no_esta_en_curso_sin_efectos_ac_57(
    motor, dos_instituciones
):
    """AC-57: solo `EnCurso` se retira; `EnRevision` responde 409 sin escribir."""
    datos = sembrar_mundo_retiro(motor, dos_instituciones)
    ticket_id = sembrar_ticket_retiro(motor, datos, estado="EnRevision")

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
        estado="EnRevision",
        stocks={(datos["sede_id"], datos["producto_id"]): 50},
    )


def test_el_retiro_sin_stock_responde_409_sin_efectos_ac_57(
    motor, dos_instituciones
):
    """AC-57: sin fila `stock_sede` no hay retiro; 409 y ninguna escritura."""
    datos = sembrar_mundo_retiro(motor, dos_instituciones, con_stock=False)
    ticket_id = sembrar_ticket_retiro(motor, datos, estado="EnCurso")

    exigir_retiro_publicado()
    with cliente_rol(motor, datos, "Bodeguero") as cliente:
        respuesta = retirar(
            cliente,
            ticket_id,
            {"usuario_id": datos["usuarios_inst01"]["Bodeguero"]},
        )

    assert respuesta.status_code == 409, respuesta.text
    assert stock_de(motor, datos["sede_id"], datos["producto_id"]) is None
    assert salidas_retiro(motor, ticket_id) == []


def test_el_retiro_rechaza_el_agregado_insuficiente_sin_efectos_ac_57(
    motor, dos_instituciones
):
    """AC-57: dos lineas del mismo producto suman 6 > stock 4; 409 sin rebajar."""
    datos = sembrar_mundo_retiro(motor, dos_instituciones)
    escaso = crear_producto_con_stock(
        motor, datos, nombre="Cinta escasa del retiro", stock_actual=4
    )
    ticket_id = sembrar_ticket_retiro(
        motor,
        datos,
        estado="EnCurso",
        detalles=[
            (escaso["producto_id"], 3, 0),
            (escaso["producto_id"], 3, 0),
        ],
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
        stocks={
            (datos["sede_id"], datos["producto_id"]): 50,
            (datos["sede_id"], escaso["producto_id"]): 4,
        },
    )


def test_el_retiro_de_un_ticket_sin_detalles_responde_409_ac_57(
    motor, dos_instituciones
):
    """AC-57: un pedido sin lineas no se retira."""
    datos = sembrar_mundo_retiro(motor, dos_instituciones)
    ticket_id = sembrar_ticket_retiro(motor, datos, estado="EnCurso", detalles=[])

    exigir_retiro_publicado()
    with cliente_rol(motor, datos, "Bodeguero") as cliente:
        respuesta = retirar(
            cliente,
            ticket_id,
            {"usuario_id": datos["usuarios_inst01"]["Bodeguero"]},
        )

    assert respuesta.status_code == 409, respuesta.text


@pytest.mark.parametrize("nombres", [("EnRevision", "Cerrado", "Anulado")])
def test_el_retiro_sin_en_curso_en_el_catalogo_responde_409(
    motor, dos_instituciones, nombres
):
    """AC-57: sin el nombre `EnCurso` el retiro no puede resolver su origen."""
    datos = sembrar_mundo_retiro(
        motor, dos_instituciones, nombres_estados=nombres
    )
    ticket_id = sembrar_ticket_retiro(motor, datos, estado="EnRevision")

    exigir_retiro_publicado()
    with cliente_rol(motor, datos, "Bodeguero") as cliente:
        respuesta = retirar(
            cliente,
            ticket_id,
            {"usuario_id": datos["usuarios_inst01"]["Bodeguero"]},
        )

    assert respuesta.status_code == 409, respuesta.text


@pytest.mark.parametrize("nombres", [("EnRevision", "EnCurso", "Anulado")])
def test_el_retiro_sin_cerrado_en_el_catalogo_responde_409(
    motor, dos_instituciones, nombres
):
    """AC-57: sin el nombre `Cerrado` no hay destino de cierre."""
    datos = sembrar_mundo_retiro(
        motor, dos_instituciones, nombres_estados=nombres
    )
    ticket_id = sembrar_ticket_retiro(motor, datos, estado="EnCurso")

    exigir_retiro_publicado()
    with cliente_rol(motor, datos, "Bodeguero") as cliente:
        respuesta = retirar(
            cliente,
            ticket_id,
            {"usuario_id": datos["usuarios_inst01"]["Bodeguero"]},
        )

    assert respuesta.status_code == 409, respuesta.text


def test_un_segundo_retiro_responde_409_sin_duplicar_salidas_ac_57(
    motor, dos_instituciones
):
    """AC-57: el primer retiro gana; el segundo relee `Cerrado` y no escribe."""
    datos = sembrar_mundo_retiro(motor, dos_instituciones)
    ticket_id = sembrar_ticket_retiro(motor, datos, estado="EnCurso")

    exigir_retiro_publicado()
    with cliente_rol(motor, datos, "Bodeguero") as cliente:
        primera = retirar(
            cliente,
            ticket_id,
            {"usuario_id": datos["usuarios_inst01"]["Bodeguero"]},
        )
        assert primera.status_code == 200, primera.text
        stock_tras_primera = stock_de(
            motor, datos["sede_id"], datos["producto_id"]
        )
        salidas_tras_primera = salidas_retiro(motor, ticket_id)
        assert len(salidas_tras_primera) == 1

        segunda = retirar(
            cliente,
            ticket_id,
            {"usuario_id": datos["usuarios_inst01"]["Bodeguero"]},
        )

    assert segunda.status_code == 409, segunda.text
    assert stock_de(motor, datos["sede_id"], datos["producto_id"]) == stock_tras_primera
    assert salidas_retiro(motor, ticket_id) == salidas_tras_primera, (
        "un segundo retiro no puede duplicar la auditoria"
    )


def test_el_retiro_revierte_todo_si_el_commit_falla_ac_57(
    monkeypatch, motor, dos_instituciones
):
    """AC-57: un fallo del `commit` revierte stock, entregas, estado y fecha."""
    datos = sembrar_mundo_retiro(motor, dos_instituciones)
    ticket_id = sembrar_ticket_retiro(motor, datos, estado="EnCurso")

    exigir_retiro_publicado()

    def commit_que_falla(self):
        raise RuntimeError("fallo de commit inyectado para probar el rollback")

    monkeypatch.setattr(Session, "commit", commit_que_falla)

    with cliente_rol(motor, datos, "Bodeguero") as cliente:
        respuesta = retirar(
            cliente,
            ticket_id,
            {"usuario_id": datos["usuarios_inst01"]["Bodeguero"]},
        )

    assert respuesta.status_code == 500, respuesta.text

    monkeypatch.undo()
    verificar_sin_efectos_retiro(
        motor,
        datos,
        ticket_id,
        estado="EnCurso",
        stocks={(datos["sede_id"], datos["producto_id"]): 50},
    )
