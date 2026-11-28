"""Enmienda 26/Nov/2026 de la 013 (D-27/D-28/AC-51): el alta nace en `EnRevision`.

Seam bajo prueba: la **interfaz HTTP** (`TestClient`), como en toda la suite.
El catalogo es el canonico de la enmienda (`EnRevision -> EnCurso -> Cerrado`,
mas `Anulado` fuera del flujo) y las altas se envian con la identidad de un
Solicitante de la institucion.

Reglas cubiertas:

* Todo `estado_id` distinto de `EnRevision` responde **409** antes de escribir
  (incluidos `EnCurso`, `Cerrado` y `Anulado`).
* Un catalogo sin `EnRevision` responde **409** (fail-closed) y el detalle no
  nombra el estado derogado `Pendiente`.
* Un `estado_id` inexistente sigue respondiendo **404** (la validacion de
  referencia precede a la regla de estado inicial).
* `estado_id` sigue siendo obligatorio: omitirlo es **422**.
* El alta valida en `EnRevision` responde **201** con `fecha_cierre` nula, su
  fila de historial y el read model; `EnRevision` se resuelve por nombre aunque
  no sea la primera fila del catalogo.
"""

from __future__ import annotations

import pytest

from app.models import Ticket

from tests.funcional.integracion._soporte_ciclo_vida_013 import (
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
# AC-51: solo `EnRevision` es estado inicial
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("nombre", ["EnCurso", "Cerrado", "Anulado"])
def test_alta_con_estado_distinto_de_enrevision_responde_409(
    motor, datos_013, nombre
):
    """AC-51: el estado inicial se rechaza antes de escribir, sin efectos."""
    tickets_antes = contar_en(motor, Ticket)

    with _cliente_solicitante(motor, datos_013) as cliente:
        respuesta = cliente.post(
            RUTA_TICKETS, json=payload_alta(datos_013, datos_013["estados"][nombre])
        )

        assert respuesta.status_code == 409, respuesta.text
        detalle = respuesta.json()["detail"]
        assert "EnRevision" in detalle, (
            f"el 409 debe nombrar el estado inicial valido: {detalle!r}"
        )
        assert "Pendiente" not in detalle, (
            "el 409 no puede nombrar el estado derogado (D-27)"
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
    cuerpo = payload_alta(datos_013, datos_013["estados"]["EnRevision"])
    cuerpo.pop("estado_id")

    with _cliente_solicitante(motor, datos_013) as cliente:
        respuesta = cliente.post(RUTA_TICKETS, json=cuerpo)

        assert respuesta.status_code == 422, respuesta.text
        assert any(
            error["loc"][-1] == "estado_id" for error in respuesta.json()["detail"]
        ), "el 422 debe senalar el campo estado_id"


def test_catalogo_sin_enrevision_deniega_el_alta_con_409(motor, dos_instituciones):
    """AC-51 fail-closed: sin `EnRevision` no se resuelve estado inicial."""
    datos = sembrar_mundo_013(
        motor, dos_instituciones, nombres_estados=("EnCurso", "Cerrado")
    )

    with _cliente_solicitante(motor, datos) as cliente:
        respuesta = cliente.post(
            RUTA_TICKETS, json=payload_alta(datos, datos["estados"]["EnCurso"])
        )

        assert respuesta.status_code == 409, respuesta.text
        assert "EnRevision" in respuesta.json()["detail"]
        assert "Pendiente" not in respuesta.json()["detail"]


def test_alta_en_enrevision_responde_201_sin_fecha_de_cierre(motor, datos_013):
    """AC-51: el camino valido crea en `EnRevision` y no sella `fecha_cierre`."""
    with _cliente_solicitante(motor, datos_013) as cliente:
        respuesta = cliente.post(
            RUTA_TICKETS,
            json=payload_alta(datos_013, datos_013["estados"]["EnRevision"]),
        )

        assert respuesta.status_code == 201, respuesta.text
        cuerpo = respuesta.json()
        assert cuerpo["estado_id"] == datos_013["estados"]["EnRevision"]
        assert cuerpo["fecha_cierre"] is None, (
            "AC-51: el alta jamas sella fecha_cierre (004 AC-17 derogado)"
        )
        assert cuerpo["etiqueta_proceso"] == "En revisión"
        ticket_id = cuerpo["ticket_id"]

    with cliente_con_rol(
        motor,
        "Administrador",
        departamento_id=datos_013["departamento_id"],
        usuario_id=datos_013["usuarios_inst01"]["Administrador"],
    ) as administrador:
        avance = administrador.patch(
            f"/api/v1/tickets/{ticket_id}/estado",
            json={"estado_id": datos_013["estados"]["EnCurso"]},
        )
        assert avance.status_code == 200, avance.text
        assert abrir_ticket(administrador, ticket_id)["estado_id"] == (
            datos_013["estados"]["EnCurso"]
        )

        historial = leer_historial(administrador, ticket_id)
        destinos = [fila["estado_destino_id"] for fila in reversed(historial)]
        assert destinos == [
            datos_013["estados"]["EnRevision"],
            datos_013["estados"]["EnCurso"],
        ], historial


def test_alta_resuelve_enrevision_por_nombre_y_no_por_posicion(
    motor, dos_instituciones
):
    """AC-51: `EnRevision` puede no ser el primer id del catalogo."""
    datos = sembrar_mundo_013(
        motor,
        dos_instituciones,
        nombres_estados=("EnCurso", "EnRevision", "Cerrado"),
    )

    with _cliente_solicitante(motor, datos) as cliente:
        respuesta = cliente.post(
            RUTA_TICKETS, json=payload_alta(datos, datos["estados"]["EnRevision"])
        )

        assert respuesta.status_code == 201, respuesta.text
        assert respuesta.json()["estado_id"] == datos["estados"]["EnRevision"]
