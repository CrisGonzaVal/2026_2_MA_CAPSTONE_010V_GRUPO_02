"""Enmienda 26/Nov/2026 de la Feature 013: catalogo, alta y flujo desde `EnRevision`.

**T33/T34 (26/27/Nov/2026):** este modulo queda verde: `_ESTADOS_TICKET_TENANT`
con las cuatro filas y el flujo de alta, aprobacion y edicion desde
`EnRevision`. La evidencia gated de la semilla vive en
`tests/funcional/sistema/test_catalogo_retiro_postgres_013.py`.
"""

from __future__ import annotations

import pytest

from app.models import EstadoTicket
from app.services import control_service, ticket_service

from tests.funcional.integracion._soporte_retiro_013 import (
    CATALOGO_RETIRO,
    anular,
    cambiar_estado,
    cliente_rol,
    rechazar,
    sembrar_mundo_retiro,
    sembrar_ticket_retiro,
)


# ---------------------------------------------------------------------------
# AC-50: catalogo de cuatro estados del aprovisionamiento
# ---------------------------------------------------------------------------


def _catalogo_tenant() -> tuple[tuple[str, str], ...]:
    catalogo = getattr(control_service, "_ESTADOS_TICKET_TENANT", None)
    assert catalogo is not None, (
        "capacidad ausente (T33): control_service._ESTADOS_TICKET_TENANT no "
        "existe; la enmienda lo publica con cuatro filas."
    )
    return catalogo


def test_el_catalogo_del_aprovisionamiento_tiene_las_cuatro_filas_ac_50():
    """D-36: 1 EnRevision, 2 EnCurso, 3 Cerrado, 4 Anulado; sin Pendiente."""
    nombres = [nombre for nombre, _ in _catalogo_tenant()]

    assert nombres == list(CATALOGO_RETIRO), (
        "el catalogo replicado por tenant debe ser exactamente "
        f"{list(CATALOGO_RETIRO)}; hoy es {nombres}"
    )
    assert len(set(nombres)) == len(nombres), "no puede haber dos filas homonimas"
    assert "Pendiente" not in nombres, "`Pendiente` deja de existir (D-27)"
    assert "Anulado" in nombres, (
        "un tenant nuevo debe nacer con el terminal negativo (AC-50/D-36)"
    )


def test_las_descripciones_del_catalogo_no_hablan_de_despacho_ac_50():
    """D-36: las descripciones describen revision y retiro, no el nombre historico."""
    for nombre, descripcion in _catalogo_tenant():
        texto = (descripcion or "").lower()
        assert "despacho" not in texto, (
            f"la descripcion de {nombre!r} conserva «despacho»: {descripcion!r}"
        )
        assert "pendiente" not in texto, (
            f"la descripcion de {nombre!r} conserva «pendiente»: {descripcion!r}"
        )


def test_pendiente_deja_de_ser_el_nombre_inicial_del_servicio_ac_50():
    """D-27: `NOMBRE_ESTADO_PENDIENTE` desaparece; `EnRevision` es el unico inicial."""
    assert not hasattr(ticket_service, "NOMBRE_ESTADO_PENDIENTE"), (
        "el servicio conserva NOMBRE_ESTADO_PENDIENTE; D-27 lo retira"
    )
    assert getattr(ticket_service, "NOMBRE_ESTADO_EN_REVISION") == "enrevision"


def test_el_estado_inicial_se_resuelve_por_nombre_y_no_por_posicion_ac_51():
    """AC-51: con `EnRevision` fuera de la primera fila, se resuelve igual."""
    resolver = getattr(ticket_service, "_resolver_estado_por_nombre")
    estados = [
        EstadoTicket(estado_id=40, nombre="Cerrado"),
        EstadoTicket(estado_id=7, nombre="EnRevision"),
    ]

    encontrado = resolver(estados, "enrevision")

    assert encontrado is not None
    assert encontrado.estado_id == 7


# ---------------------------------------------------------------------------
# AC-51: el alta nace en `EnRevision`
# ---------------------------------------------------------------------------


def _payload_alta(datos, estado_id: int) -> dict:
    return {
        "prioridad_id": datos["prioridad_id"],
        "estado_id": estado_id,
        "asunto": "Alta de la enmienda del catalogo",
        "descripcion": "Pedido creado por las pruebas rojas de T32.",
        "detalles": [
            {"producto_id": datos["producto_id"], "cantidad_solicitada": 1}
        ],
    }


def test_el_alta_nace_en_enrevision_aunque_no_sea_la_primera_fila_ac_51(
    motor, dos_instituciones
):
    """AC-51: 201 con `EnRevision` y `fecha_cierre` nula; sin historial inventado."""
    datos = sembrar_mundo_retiro(motor, dos_instituciones, con_stock=False)

    with cliente_rol(motor, datos, "Solicitante") as cliente:
        respuesta = cliente.post(
            "/api/v1/tickets/",
            json=_payload_alta(datos, datos["estados"]["EnRevision"]),
        )

    assert respuesta.status_code == 201, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["estado_id"] == datos["estados"]["EnRevision"], (
        "el alta debe nacer en EnRevision (D-27/AC-51)"
    )
    assert cuerpo["fecha_cierre"] is None


@pytest.mark.parametrize("estado", ["EnCurso", "Cerrado", "Anulado"])
def test_el_alta_rechaza_cualquier_otro_estado_con_409_ac_51(
    motor, dos_instituciones, estado
):
    """AC-51: solo `EnRevision` es estado inicial; el resto responde 409."""
    datos = sembrar_mundo_retiro(motor, dos_instituciones, con_stock=False)

    with cliente_rol(motor, datos, "Solicitante") as cliente:
        respuesta = cliente.post(
            "/api/v1/tickets/",
            json=_payload_alta(datos, datos["estados"][estado]),
        )
        listado = cliente.get("/api/v1/tickets/")

    assert respuesta.status_code == 409, respuesta.text
    assert "Pendiente" not in respuesta.json()["detail"], (
        "el 409 no puede nombrar el estado derogado (D-27)"
    )
    assert listado.status_code == 200, listado.text
    assert listado.json() == [], "un alta rechazada no puede dejar filas"


# ---------------------------------------------------------------------------
# AC-52/AC-53/AC-54: el flujo solo se mueve desde `EnRevision`
# ---------------------------------------------------------------------------


def test_aprobar_desde_enrevision_deja_en_curso_ac_52(motor, dos_instituciones):
    """AC-52: 200, `EnCurso`, `fecha_cierre` nula y una fila con el motivo."""
    datos = sembrar_mundo_retiro(motor, dos_instituciones)
    ticket_id = sembrar_ticket_retiro(motor, datos, estado="EnRevision")

    with cliente_rol(motor, datos, "Administrador") as cliente:
        respuesta = cliente.post(f"/api/v1/tickets/{ticket_id}/aprobacion")

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["estado_id"] == datos["estados"]["EnCurso"]
    assert cuerpo["fecha_cierre"] is None


def test_aprobar_fuera_de_enrevision_responde_409_sin_nombrar_pendiente_ac_52(
    motor, dos_instituciones
):
    """AC-52: `EnCurso`/`Cerrado`/`Anulado` no son origen; el 409 no cita `Pendiente`."""
    datos = sembrar_mundo_retiro(motor, dos_instituciones)
    ticket_id = sembrar_ticket_retiro(motor, datos, estado="EnCurso")

    with cliente_rol(motor, datos, "Administrador") as cliente:
        respuesta = cliente.post(f"/api/v1/tickets/{ticket_id}/aprobacion")

    assert respuesta.status_code == 409, respuesta.text
    assert "Pendiente" not in respuesta.json()["detail"], (
        "D-27 retira `Pendiente` tambien de los mensajes vigentes"
    )


def test_editar_en_enrevision_responde_200_ac_53(motor, dos_instituciones):
    """AC-53: el dueño edita en `EnRevision` y el estado no cambia."""
    datos = sembrar_mundo_retiro(motor, dos_instituciones)
    ticket_id = sembrar_ticket_retiro(motor, datos, estado="EnRevision")

    with cliente_rol(motor, datos, "Solicitante") as cliente:
        respuesta = cliente.put(
            f"/api/v1/tickets/{ticket_id}",
            json={
                "prioridad_id": datos["prioridad_id"],
                "asunto": "Asunto corregido en revision",
                "descripcion": "Edicion valida de la enmienda.",
                "detalles": [
                    {
                        "producto_id": datos["producto_id"],
                        "cantidad_solicitada": 2,
                    }
                ],
            },
        )

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["estado_id"] == datos["estados"]["EnRevision"]


def test_anular_y_rechazar_solo_desde_enrevision_ac_54(motor, dos_instituciones):
    """AC-54: desde `EnRevision` la anulacion y el rechazo cierran en `Anulado`."""
    datos = sembrar_mundo_retiro(motor, dos_instituciones)
    ticket_anulado = sembrar_ticket_retiro(motor, datos, estado="EnRevision")
    ticket_rechazado = sembrar_ticket_retiro(motor, datos, estado="EnRevision")

    with cliente_rol(motor, datos, "Administrador") as cliente:
        anulacion = anular(cliente, ticket_anulado, "Anulacion de una revision")
        rechazo = rechazar(cliente, ticket_rechazado, "Rechazo de una revision")

    assert anulacion.status_code == 200, anulacion.text
    assert rechazo.status_code == 200, rechazo.text
    assert anulacion.json()["estado_id"] == datos["estados"]["Anulado"]
    assert rechazo.json()["estado_id"] == datos["estados"]["Anulado"]


def test_anular_desde_en_curso_responde_409_ac_54(motor, dos_instituciones):
    """AC-54: desde `EnCurso` no hay anulacion ni rechazo."""
    datos = sembrar_mundo_retiro(motor, dos_instituciones)
    ticket_id = sembrar_ticket_retiro(motor, datos, estado="EnCurso")

    with cliente_rol(motor, datos, "Administrador") as cliente:
        anulacion = anular(cliente, ticket_id, "No aplica en curso")
        rechazo = rechazar(cliente, ticket_id, "No aplica en curso")

    assert anulacion.status_code == 409, anulacion.text
    assert rechazo.status_code == 409, rechazo.text


def test_el_patch_de_legado_sigue_siendo_solo_del_administrador_ac_60(
    motor, dos_instituciones
):
    """AC-60: el Bodeguero recibe 403; el Administrador mueve un paso."""
    datos = sembrar_mundo_retiro(motor, dos_instituciones)
    ticket_id = sembrar_ticket_retiro(motor, datos, estado="EnRevision")

    with cliente_rol(motor, datos, "Bodeguero") as cliente:
        negado = cambiar_estado(cliente, ticket_id, datos["estados"]["EnCurso"])

    with cliente_rol(motor, datos, "Administrador") as cliente:
        permitido = cambiar_estado(
            cliente, ticket_id, datos["estados"]["EnCurso"]
        )

    assert negado.status_code == 403, negado.text
    assert permitido.status_code == 200, permitido.text
    assert permitido.json()["estado_id"] == datos["estados"]["EnCurso"]
