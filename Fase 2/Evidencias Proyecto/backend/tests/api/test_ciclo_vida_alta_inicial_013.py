"""Enmienda post-cierre 05/Nov/2026 (AC-27): el alta nace siempre en `Pendiente`.

Seam bajo prueba: la **interfaz HTTP** (`TestClient`), como en toda la suite.
El catalogo es el canonico de la 013 (`Pendiente -> EnRevision -> EnCurso ->
Cerrado`, mas `Anulado`) y las altas se envian con la identidad de un
Solicitante de la institucion.

Reglas cubiertas:

* Todo `estado_id` distinto de `Pendiente` responde **409** antes de escribir
  (incluido `Anulado`, antes rechazado con un 409 propio, y `Cerrado`, que
  antes se admitia sellando `fecha_cierre`).
* Un catalogo sin `Pendiente` responde **409** (fail-closed).
* Un `estado_id` inexistente sigue respondiendo **404** (la validacion de
  referencia precede a la regla de estado inicial).
* `estado_id` sigue siendo obligatorio: omitirlo es **422**.
* El alta valida en `Pendiente` responde **201** con `fecha_cierre` nula y su
  fila de historial, y `PATCH /tickets/{id}/estado` conserva su flujo.
"""

from __future__ import annotations

import pytest

from app.models import Ticket

from ._soporte_ciclo_vida_013 import (
    abrir_ticket,
    cliente_con_rol,
    contar_en,
    leer_historial,
    payload_alta,
    sembrar_mundo_013,
)

RUTA_TICKETS = "/api/v1/tickets/"


@pytest.fixture
def datos_013(motor, dos_instituciones):
    """Padron de dos instituciones + catalogo 013 + sede con stock 50."""
    return sembrar_mundo_013(motor, dos_instituciones)


def _cliente_solicitante(motor, datos):
    return cliente_con_rol(
        motor,
        "Solicitante",
        departamento_id=datos["departamento_id"],
        usuario_id=datos["usuarios_inst01"]["Solicitante"],
    )


# ---------------------------------------------------------------------------
# AC-27: solo `Pendiente` es estado inicial
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("nombre", ["EnRevision", "EnCurso", "Cerrado", "Anulado"])
def test_alta_con_estado_distinto_de_pendiente_responde_409(
    motor, datos_013, nombre
):
    """AC-27: el estado inicial se rechaza antes de escribir, sin efectos."""
    tickets_antes = contar_en(motor, Ticket)

    with _cliente_solicitante(motor, datos_013) as cliente:
        respuesta = cliente.post(
            RUTA_TICKETS, json=payload_alta(datos_013, datos_013["estados"][nombre])
        )

        assert respuesta.status_code == 409, respuesta.text
        detalle = respuesta.json()["detail"]
        assert "Pendiente" in detalle, (
            f"el 409 debe nombrar el estado inicial valido: {detalle!r}"
        )

    assert contar_en(motor, Ticket) == tickets_antes, (
        "el 409 de estado inicial no puede dejar ticket ni detalle parciales"
    )


def test_alta_con_estado_inexistente_sigue_siendo_404(motor, datos_013):
    """El 404 de referencia precede a la regla de estado inicial (orden D-8)."""
    with _cliente_solicitante(motor, datos_013) as cliente:
        respuesta = cliente.post(RUTA_TICKETS, json=payload_alta(datos_013, 76543))

        assert respuesta.status_code == 404, respuesta.text


def test_alta_sin_estado_id_es_422(motor, datos_013):
    """`estado_id` sigue siendo obligatorio en el contrato (no se retiro)."""
    cuerpo = payload_alta(datos_013, datos_013["estados"]["Pendiente"])
    cuerpo.pop("estado_id")

    with _cliente_solicitante(motor, datos_013) as cliente:
        respuesta = cliente.post(RUTA_TICKETS, json=cuerpo)

        assert respuesta.status_code == 422, respuesta.text
        assert any(
            error["loc"][-1] == "estado_id" for error in respuesta.json()["detail"]
        ), "el 422 debe senalar el campo estado_id"


def test_catalogo_sin_pendiente_deniega_el_alta_con_409(motor, dos_instituciones):
    """AC-27 fail-closed: sin `Pendiente` no se resuelve estado inicial."""
    datos = sembrar_mundo_013(
        motor, dos_instituciones, nombres_estados=("EnRevision", "EnCurso")
    )

    with _cliente_solicitante(motor, datos) as cliente:
        respuesta = cliente.post(
            RUTA_TICKETS, json=payload_alta(datos, datos["estados"]["EnRevision"])
        )

        assert respuesta.status_code == 409, respuesta.text
        assert "Pendiente" in respuesta.json()["detail"]


def test_alta_en_pendiente_responde_201_sin_fecha_de_cierre(motor, datos_013):
    """AC-27: el camino valido crea en `Pendiente` y no sella `fecha_cierre`."""
    with _cliente_solicitante(motor, datos_013) as cliente:
        respuesta = cliente.post(
            RUTA_TICKETS,
            json=payload_alta(datos_013, datos_013["estados"]["Pendiente"]),
        )

        assert respuesta.status_code == 201, respuesta.text
        cuerpo = respuesta.json()
        assert cuerpo["estado_id"] == datos_013["estados"]["Pendiente"]
        assert cuerpo["fecha_cierre"] is None, (
            "AC-27: el alta jamas sella fecha_cierre (004 AC-17 derogado)"
        )

        # El flujo posterior sigue intacto: Pendiente -> EnRevision.
        ticket_id = cuerpo["ticket_id"]

    with cliente_con_rol(
        motor,
        "Administrador",
        departamento_id=datos_013["departamento_id"],
        usuario_id=datos_013["usuarios_inst01"]["Administrador"],
    ) as administrador:
        avance = administrador.patch(
            f"/api/v1/tickets/{ticket_id}/estado",
            json={"estado_id": datos_013["estados"]["EnRevision"]},
        )
        assert avance.status_code == 200, avance.text
        assert abrir_ticket(administrador, ticket_id)["estado_id"] == (
            datos_013["estados"]["EnRevision"]
        )

        historial = leer_historial(administrador, ticket_id)
        destinos = [fila["estado_destino_id"] for fila in reversed(historial)]
        assert destinos == [
            datos_013["estados"]["Pendiente"],
            datos_013["estados"]["EnRevision"],
        ], historial


def test_alta_resuelve_pendiente_por_nombre_y_no_por_posicion(motor, dos_instituciones):
    """AC-27: `Pendiente` puede no ser el primer id del catalogo."""
    datos = sembrar_mundo_013(
        motor,
        dos_instituciones,
        nombres_estados=("EnCurso", "Pendiente", "Cerrado"),
    )

    with _cliente_solicitante(motor, datos) as cliente:
        respuesta = cliente.post(
            RUTA_TICKETS, json=payload_alta(datos, datos["estados"]["Pendiente"])
        )

        assert respuesta.status_code == 201, respuesta.text
        assert respuesta.json()["estado_id"] == datos["estados"]["Pendiente"]
