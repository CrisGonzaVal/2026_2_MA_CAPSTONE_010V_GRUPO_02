"""Enmienda 26/Nov/2026 de la 013: `PATCH /estado` de legado (AC-60).

Fase ROJA de TDD (T32). La regla de **un paso entre contiguos** se conserva y
los terminales se resuelven por nombre en cualquier catalogo:

* `EnRevision -> EnCurso` y el retroceso `EnCurso -> EnRevision` son validos;
* `EnRevision -> Cerrado` es 409 por saltarse un paso;
* `EnCurso -> Cerrado` es 409 con el detalle que dirige al **retiro**;
* entrar o salir de `Cerrado` o `Anulado` es 409 en cualquier catalogo;
* el `PATCH` sigue siendo solo del Administrador y la UI no lo invoca.

El unico rojo esperado de la fase es el literal del cierre: hoy sigue diciendo
`/despacho`, y la enmienda lo sustituye por `/retiro` (D-29/AC-60).
"""

from __future__ import annotations

import pytest

from tests.funcional.integracion._soporte_retiro_013 import (
    cambiar_estado,
    cliente_rol,
    historial_persistido,
    sembrar_mundo_retiro,
    sembrar_ticket_retiro,
)


@pytest.mark.parametrize(
    ("origen", "destino"),
    [("EnRevision", "EnCurso"), ("EnCurso", "EnRevision")],
)
def test_el_administrador_mueve_un_paso_en_ambas_direcciones_ac_60(
    motor, dos_instituciones, origen, destino
):
    """AC-60: los dos movimientos contiguos son 200 y dejan su fila de historial."""
    datos = sembrar_mundo_retiro(motor, dos_instituciones)
    ticket_id = sembrar_ticket_retiro(motor, datos, estado=origen)

    with cliente_rol(motor, datos, "Administrador") as cliente:
        respuesta = cambiar_estado(cliente, ticket_id, datos["estados"][destino])

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["estado_id"] == datos["estados"][destino]
    filas = historial_persistido(motor, ticket_id)
    assert len(filas) == 1
    assert filas[0]["estado_origen_id"] == datos["estados"][origen]
    assert filas[0]["estado_destino_id"] == datos["estados"][destino]
    assert filas[0]["motivo"] is None


def test_saltarse_un_paso_responde_409_ac_60(motor, dos_instituciones):
    """AC-60: `EnRevision -> Cerrado` no es contiguo."""
    datos = sembrar_mundo_retiro(motor, dos_instituciones)
    ticket_id = sembrar_ticket_retiro(motor, datos, estado="EnRevision")

    with cliente_rol(motor, datos, "Administrador") as cliente:
        respuesta = cambiar_estado(cliente, ticket_id, datos["estados"]["Cerrado"])

    assert respuesta.status_code == 409, respuesta.text
    assert historial_persistido(motor, ticket_id) == []


def test_en_curso_a_cerrado_dirige_al_retiro_y_no_al_despacho_ac_60(
    motor, dos_instituciones
):
    """AC-60/D-29: el 409 del cierre reservado nombra `/retiro`, no `/despacho`."""
    datos = sembrar_mundo_retiro(motor, dos_instituciones)
    ticket_id = sembrar_ticket_retiro(motor, datos, estado="EnCurso")

    with cliente_rol(motor, datos, "Administrador") as cliente:
        respuesta = cambiar_estado(cliente, ticket_id, datos["estados"]["Cerrado"])

    assert respuesta.status_code == 409, respuesta.text
    detalle = respuesta.json()["detail"]
    assert f"/tickets/{ticket_id}/retiro" in detalle, (
        f"el 409 debe dirigir al retiro: {detalle!r}"
    )
    assert "/despacho" not in detalle, (
        f"el 409 no puede conservar la ruta historica: {detalle!r}"
    )
    assert "retiro" in detalle.lower()


@pytest.mark.parametrize("destino", ["EnRevision", "EnCurso"])
def test_no_se_sale_de_cerrado_por_patch_ac_60(
    motor, dos_instituciones, destino
):
    """AC-60: `Cerrado` solo sale por la anulacion administrativa del retiro."""
    datos = sembrar_mundo_retiro(motor, dos_instituciones)
    ticket_id = sembrar_ticket_retiro(motor, datos, estado="Cerrado")

    with cliente_rol(motor, datos, "Administrador") as cliente:
        respuesta = cambiar_estado(cliente, ticket_id, datos["estados"][destino])

    assert respuesta.status_code == 409, respuesta.text
    detalle = respuesta.json()["detail"]
    assert "/despacho" not in detalle, (
        f"la salida de `Cerrado` no puede anunciar `/despacho`: {detalle!r}"
    )


@pytest.mark.parametrize("destino", ["EnRevision", "EnCurso", "Cerrado"])
def test_no_se_sale_de_anulado_por_patch_ac_60(
    motor, dos_instituciones, destino
):
    """AC-60: `Anulado` es terminal y el 409 no cita `Pendiente`."""
    datos = sembrar_mundo_retiro(motor, dos_instituciones)
    ticket_id = sembrar_ticket_retiro(motor, datos, estado="Anulado")

    with cliente_rol(motor, datos, "Administrador") as cliente:
        respuesta = cambiar_estado(cliente, ticket_id, datos["estados"][destino])

    assert respuesta.status_code == 409, respuesta.text
    assert "Pendiente" not in respuesta.json()["detail"], (
        "D-27 retira `Pendiente` tambien de los mensajes vigentes"
    )


def test_el_patch_no_entra_en_cerrado_ni_en_anulado_ac_60(motor, dos_instituciones):
    """AC-60: ninguna peticion lleva a `Cerrado` ni a `Anulado` por el PATCH."""
    datos = sembrar_mundo_retiro(motor, dos_instituciones)
    ticket_id = sembrar_ticket_retiro(motor, datos, estado="EnRevision")

    with cliente_rol(motor, datos, "Administrador") as cliente:
        hacia_cerrado = cambiar_estado(
            cliente, ticket_id, datos["estados"]["Cerrado"]
        )
        hacia_anulado = cambiar_estado(
            cliente, ticket_id, datos["estados"]["Anulado"]
        )

    assert hacia_cerrado.status_code == 409, hacia_cerrado.text
    assert hacia_anulado.status_code == 409, hacia_anulado.text
    assert "anulacion" in hacia_anulado.json()["detail"].lower()


def test_el_patch_sigue_siendo_solo_del_administrador_ac_60(
    motor, dos_instituciones
):
    """AC-60: Bodeguero y Solicitante reciben 403."""
    datos = sembrar_mundo_retiro(motor, dos_instituciones)
    ticket_id = sembrar_ticket_retiro(motor, datos, estado="EnRevision")

    with cliente_rol(motor, datos, "Bodeguero") as cliente:
        bodeguero = cambiar_estado(cliente, ticket_id, datos["estados"]["EnCurso"])

    with cliente_rol(motor, datos, "Solicitante") as cliente:
        solicitante = cambiar_estado(
            cliente, ticket_id, datos["estados"]["EnCurso"]
        )

    assert bodeguero.status_code == 403, bodeguero.text
    assert solicitante.status_code == 403, solicitante.text


def test_la_terminalidad_de_cerrado_es_por_nombre_en_catalogo_degenerado_ac_60(
    motor, dos_instituciones
):
    """AC-60: aunque `Cerrado` sea contiguo a `EnCurso`, no se sale de el."""
    datos = sembrar_mundo_retiro(
        motor,
        dos_instituciones,
        nombres_estados=("EnRevision", "Cerrado", "EnCurso", "Anulado"),
    )
    ticket_id = sembrar_ticket_retiro(motor, datos, estado="Cerrado")

    with cliente_rol(motor, datos, "Administrador") as cliente:
        respuesta = cambiar_estado(cliente, ticket_id, datos["estados"]["EnCurso"])

    assert respuesta.status_code == 409, respuesta.text
    assert respuesta.json()["detail"], "el 409 debe explicar la terminalidad"
