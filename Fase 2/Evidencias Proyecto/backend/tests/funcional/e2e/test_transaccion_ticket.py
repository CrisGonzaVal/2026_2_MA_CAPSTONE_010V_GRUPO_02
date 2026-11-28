"""AC-8: `POST /api/v1/tickets/` es atomica.

Este archivo existe por una regresion concreta. La version previa del endpoint
hacia `db.commit()` apenas creaba el `Ticket` y recien despues agregaba los
`DetalleTicket`. Si un detalle fallaba (producto inexistente), el ticket ya
estaba commiteado y quedaba huerfano en `ticket` con cero detalles.

La extraccion a `ticket_service.py` lo corrige con `flush()` + un unico
`commit()`. Este test falla si alguien reintroduce el commit intermedio.

Las aserciones leen la API, no la base de datos: el rollback se comprueba
viendo que el ticket nunca aparecio en `GET /api/v1/tickets/`.
"""

import pytest
from sqlalchemy.orm import sessionmaker

from app.models import StockSede

from tests.funcional.integracion._soporte_sede_011 import (
    asegurar_sede_de_departamento,
    cliente as cliente_de_rol,
)


@pytest.fixture(autouse=True)
def sede_base(motor, datos_base):
    """Feature 011/026: el alta de ticket exige sede y el saldo vive por sede.

    Devuelve `{"sede_id", "stock_sede_ids"}` con 50 unidades del producto base.
    """
    return asegurar_sede_de_departamento(
        motor, datos_base, stocks={datos_base["producto_id"]: 50}
    )


def _stock_sede(motor, stock_sede_id: int) -> int:
    """Saldo de una fila de `stock_sede`, leido por ORM."""
    db = sessionmaker(bind=motor)()
    try:
        return db.get(StockSede, stock_sede_id).stock_actual
    finally:
        db.close()


def _cuerpo_ticket(datos_base, detalles, asunto="Ticket de prueba"):
    return {
        "usuario_id": datos_base["usuario_id"],
        "prioridad_id": datos_base["prioridad_id"],
        "estado_id": datos_base["estado_ingresado_id"],
        "asunto": asunto,
        "descripcion": "Descripcion de prueba.",
        "detalles": detalles,
    }


def test_detalle_invalido_no_deja_ticket_huerfano(
    cliente_sin_excepcion, actuar_como, datos_base
):
    """1 detalle valido + 1 con producto inexistente no debe persistir nada."""
    actuar_como("Solicitante")
    cuerpo = _cuerpo_ticket(
        datos_base,
        detalles=[
            {"producto_id": datos_base["producto_id"], "cantidad_solicitada": 5},
            {"producto_id": 999999, "cantidad_solicitada": 1},
        ],
    )

    respuesta = cliente_sin_excepcion.post("/api/v1/tickets/", json=cuerpo)
    # DEFECTO CONOCIDO: la API respondia 500 en vez de 4xx porque `crear_ticket`
    # no traducía el `IntegrityError`. Este test documentaba ese 500 como
    # comportamiento esperado (Feature 001, Fase C). La Feature 003 corrige ese
    # defecto preexistente: las referencias se comprueban antes de escribir, por
    # lo que la respuesta pasa a ser **404** y el mensaje nombra la referencia.
    assert respuesta.status_code == 404, respuesta.text

    # Lo que AC-8 protege de verdad: el ticket no debe existir. Esta asercion
    # falla si alguien reintroduce el `commit()` intermedio.
    assert cliente_sin_excepcion.get("/api/v1/tickets/").json() == []


def test_detalle_invalido_no_deja_ticket_por_mas_que_haya_tres_detalles(
    cliente_sin_excepcion, actuar_como, datos_base
):
    """El fallo en el ultimo de N detalles tambien revierte los anteriores."""
    actuar_como("Solicitante")
    detalles = [
        {"producto_id": datos_base["producto_id"], "cantidad_solicitada": n}
        for n in (1, 2, 3)
    ]
    detalles.append({"producto_id": 999999, "cantidad_solicitada": 4})

    respuesta = cliente_sin_excepcion.post(
        "/api/v1/tickets/", json=_cuerpo_ticket(datos_base, detalles)
    )
    assert respuesta.status_code == 404
    assert cliente_sin_excepcion.get("/api/v1/tickets/").json() == []


def test_ticket_valido_persiste_cabecera_y_detalles_juntos(
    cliente, actuar_como, datos_base
):
    """Contraprueba del anterior: el camino feliz sigue funcionando."""
    actuar_como("Solicitante")
    cuerpo = _cuerpo_ticket(
        datos_base,
        detalles=[
            {"producto_id": datos_base["producto_id"], "cantidad_solicitada": 5},
            {"producto_id": datos_base["producto_id"], "cantidad_solicitada": 7},
        ],
    )

    respuesta = cliente.post("/api/v1/tickets/", json=cuerpo)
    assert respuesta.status_code == 201, respuesta.text

    listados = cliente.get("/api/v1/tickets/").json()
    assert len(listados) == 1
    assert len(listados[0]["detalles"]) == 2
    assert sorted(d["cantidad_solicitada"] for d in listados[0]["detalles"]) == [5, 7]


def test_detalle_invalido_no_altera_el_stock(
    cliente_sin_excepcion, actuar_como, motor, datos_base, sede_base
):
    """Crear un ticket no debe mover inventario, ni siquiera al fallar.

    Marca el limite de la operacion: `crear_ticket` es atomica, pero todavia
    no descuenta stock. Ese descuento pertenece a la approbacion del ticket
    (Feature 004/005), no a la creacion.
    """
    actuar_como("Solicitante")
    stock_sede_id = sede_base["stock_sede_ids"][datos_base["producto_id"]]
    stock_antes = _stock_sede(motor, stock_sede_id)

    cuerpo = _cuerpo_ticket(
        datos_base,
        detalles=[
            {"producto_id": datos_base["producto_id"], "cantidad_solicitada": 5},
            {"producto_id": 999999, "cantidad_solicitada": 1},
        ],
    )
    # 404 desde la Feature 003 (antes 500 por el defecto de FK).
    assert cliente_sin_excepcion.post("/api/v1/tickets/", json=cuerpo).status_code == 404

    stock_despues = _stock_sede(motor, stock_sede_id)
    assert stock_despues == stock_antes


def test_saldo_insuficiente_no_registra_movimiento(
    motor, datos_base, sede_base
):
    """Trazabilidad absoluta (`constitucion.md` §2): un rechazo no deja rastro.

    Un movimiento rechazado no debe generar fila en `movimiento_inventario`, y el
    stock debe quedar intacto. Se verifica por la API: el stock no cambia y el
    siguiente movimiento valido debe partir del valor original, no de uno
    corrompido. Enmienda 26/Nov/2026 (D-31/AC-64): el registro manual lo ejerce
    el Bodeguero de la sede.
    """
    stock_sede_id = sede_base["stock_sede_ids"][datos_base["producto_id"]]
    with cliente_de_rol(
        motor,
        "Bodeguero",
        departamento_id=datos_base["departamento_id"],
        sede_id=sede_base["sede_id"],
    ) as cliente:
        saldo_insuficiente = cliente.post(
            "/api/v1/inventario/movimientos",
            json={
                "tipo_movimiento": "SALIDA",
                "cantidad": 9999,
                "observacion": "Debe rechazarse",
                "stock_sede_id": stock_sede_id,
            },
        )
        # Feature 011/026: sobre `stock_sede` el saldo insuficiente es un 409 de
        # conflicto con el estado del recurso (el 400 era del camino legado).
        assert saldo_insuficiente.status_code == 409, saldo_insuficiente.text

        stock = _stock_sede(motor, stock_sede_id)
        assert stock == 50

        # La siguiente operacion valida debe partir de 50, no del valor alterado.
        entrada = cliente.post(
            "/api/v1/inventario/movimientos",
            json={
                "tipo_movimiento": "ENTRADA",
                "cantidad": 10,
                "observacion": "Ingreso posterior",
                "stock_sede_id": stock_sede_id,
            },
        )
    assert entrada.status_code == 201, entrada.text
    assert entrada.json()["nuevo_stock"] == 60


def test_tipo_de_movimiento_invalido_no_registra_movimiento(
    motor, datos_base, sede_base
):
    stock_sede_id = sede_base["stock_sede_ids"][datos_base["producto_id"]]
    with cliente_de_rol(
        motor,
        "Bodeguero",
        departamento_id=datos_base["departamento_id"],
        sede_id=sede_base["sede_id"],
    ) as cliente:
        respuesta = cliente.post(
            "/api/v1/inventario/movimientos",
            json={
                "tipo_movimiento": "AJUSTE_MAGICO",
                "cantidad": 1,
                "observacion": "Tipo no permitido",
                "stock_sede_id": stock_sede_id,
            },
        )
    assert respuesta.status_code == 422, respuesta.text
    assert respuesta.json()["detail"][0]["loc"] == ["body", "tipo_movimiento"]
    assert _stock_sede(motor, stock_sede_id) == 50
