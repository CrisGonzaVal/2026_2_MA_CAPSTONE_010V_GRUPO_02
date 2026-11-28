"""Feature 013 (ampliacion 25/Nov/2026): confirmacion de entrega (AC-42/43/44).

Seam bajo prueba: la **interfaz HTTP** del `app` real (`TestClient`), como en el
resto de la suite. La confirmacion es el evento posterior al despacho
(`POST /api/v1/tickets/{ticket_id}/confirmacion-entrega`): solo el Solicitante
**dueño** del pedido la ejecuta, se persiste como una fila
`Cerrado -> Cerrado` de `historial_transicion_ticket` con el motivo literal
`Entrega confirmada por el solicitante`, el actor y la fecha del servidor, y
**no** cambia el estado canonico, `fecha_cierre`, el stock ni los movimientos
(spec §9.9, D-25/D-26).

La matriz y el contrato se transcriben a mano desde la spec (nunca se leen de
`permisos.MATRIZ_PERMISOS` como fuente de la expectativa).
"""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import select

from app.core import permisos
from app.models import HistorialTransicionTicket, Ticket

from tests.funcional.integracion._soporte_ciclo_vida_013 import (
    CORREO_GATING_013 as _CORREO_GATING,
    DETALLE_TICKET_NO_ENCONTRADO,
    SIN_AUTENTICAR,
    abrir_ticket,
    cliente_con_rol,
    contar_en,
    leer_historial,
    leer_stock_sede,
    sembrar_contexto_capacidades as _sembrar_contexto_capacidades,
    sembrar_mundo_013,
    sembrar_ticket,
    sesion,
)

#: Contrato de la ampliacion (spec §9.4/§9.9).
RUTA_CONFIRMACION = "/api/v1/tickets/{ticket_id}/confirmacion-entrega"
RUTA_ESTADO = "/api/v1/tickets/{ticket_id}/estado"
RUTA_RETIRO = "/api/v1/tickets/{ticket_id}/retiro"
RUTA_RECHAZO = "/api/v1/tickets/{ticket_id}/rechazo"
RUTA_APROBACION = "/api/v1/tickets/{ticket_id}/aprobacion"

#: Motivo literal del historial (spec D-25). Fuente independiente del codigo.
MOTIVO_CONFIRMACION = "Entrega confirmada por el solicitante"

#: Etiquetas de proceso de la spec §9.8 que distingue la confirmacion.
ETIQUETA_RETIRADO = "Retirado"
ETIQUETA_ENTREGADO = "Entregado"

#: `fecha_cierre` que sella el despacho; la confirmacion no puede tocarla.
FECHA_CIERRE = datetime(2026, 11, 20, 9, 30)

#: Correo del contexto de capacidades del gating (distinto del resto de suites).
_CORREO_GATING = "gating013.confirmacion@compustock.cl"


# ---------------------------------------------------------------------------
# Mundos y clientes
# ---------------------------------------------------------------------------


@pytest.fixture
def mundo(motor, dos_instituciones):
    """Estados 013, sede del departamento y 50 unidades del producto base."""
    return sembrar_mundo_013(motor, dos_instituciones)


def _cliente_solicitante(motor, datos, correo=None):
    """Solicitante **dueño** del pedido sembrado (INST01)."""
    return cliente_con_rol(
        motor,
        "Solicitante",
        departamento_id=datos["departamento_id"],
        usuario_id=datos["usuarios_inst01"]["Solicitante"],
        **({"correo": correo} if correo else {}),
    )


def _cliente_solicitante_ajeno(motor, datos):
    """Solicitante de otra institucion: ajeno a todo pedido de INST01."""
    return cliente_con_rol(
        motor,
        "Solicitante",
        departamento_id=datos["departamento_ajeno_id"],
        usuario_id=datos["usuarios_inst02"]["Solicitante"],
    )


def _cliente_administrador(motor, datos, correo=None):
    return cliente_con_rol(
        motor,
        "Administrador",
        departamento_id=datos["departamento_id"],
        usuario_id=datos["usuario_id"],
        **({"correo": correo} if correo else {}),
    )


def _cliente_bodeguero(motor, datos):
    return cliente_con_rol(
        motor,
        "Bodeguero",
        departamento_id=datos["departamento_id"],
        usuario_id=datos["usuarios_inst01"]["Bodeguero"],
    )


def _cliente_superadmin(motor, datos):
    return cliente_con_rol(
        motor,
        "Superadmin",
        departamento_id=datos["departamento_id"],
        usuario_id=datos["usuarios_inst01"]["Superadmin"],
    )


# ---------------------------------------------------------------------------
# Siembra y observacion
# ---------------------------------------------------------------------------


def _sembrar_cerrado(motor, datos, *, usuario_id=None, fecha_cierre=FECHA_CIERRE):
    """Ticket `Cerrado` (retirado) con su `fecha_cierre` sellada por ORM."""
    ticket_id = sembrar_ticket(
        motor,
        datos,
        usuario_id=(
            usuario_id
            if usuario_id is not None
            else datos["usuarios_inst01"]["Solicitante"]
        ),
        estado_id=datos["estados"]["Cerrado"],
    )
    with sesion(motor) as db:
        db.get(Ticket, ticket_id).fecha_cierre = fecha_cierre
        db.commit()
    return ticket_id


def _confirmar(cliente, ticket_id: int):
    """`POST /confirmacion-entrega` sin payload, como lo invoca el detalle."""
    return cliente.post(f"/api/v1/tickets/{ticket_id}/confirmacion-entrega")


def _estado_persistido(motor, ticket_id: int) -> int | None:
    """Estado por ORM, para escenarios donde el rol del cliente no lista."""
    with sesion(motor) as db:
        return db.get(Ticket, ticket_id).estado_id


def _fecha_cierre_persistida(motor, ticket_id: int):
    with sesion(motor) as db:
        return db.get(Ticket, ticket_id).fecha_cierre


def _historial_persistido(motor, ticket_id: int) -> list[HistorialTransicionTicket]:
    """Filas del historial por ORM (observacion independiente del rol)."""
    with sesion(motor) as db:
        return list(
            db.execute(
                select(HistorialTransicionTicket)
                .where(HistorialTransicionTicket.ticket_id == ticket_id)
                .order_by(HistorialTransicionTicket.historial_transicion_id)
            )
            .scalars()
            .all()
        )


# ---------------------------------------------------------------------------
# AC-42: 200 del dueño, fila `Cerrado -> Cerrado`, sin efectos colaterales
# ---------------------------------------------------------------------------


def test_confirmacion_del_dueno_responde_200_con_una_fila_cerrado_cerrado_ac_42(
    motor, mundo
):
    """AC-42/D-25: 200, etiqueta «Entregado» y una sola fila del historial."""
    datos = mundo
    ticket_id = _sembrar_cerrado(motor, datos)
    stock_antes = leer_stock_sede(motor, datos["sede_id"], datos["producto_id"])
    movimientos_antes = contar_en(motor, "MovimientoInventario")

    with _cliente_solicitante(motor, datos) as cliente:
        antes = abrir_ticket(cliente, ticket_id)
        assert antes["etiqueta_proceso"] == ETIQUETA_RETIRADO, (
            "precondicion: un Cerrado sin confirmacion esta «Retirado»"
        )

        respuesta = _confirmar(cliente, ticket_id)

        assert respuesta.status_code == 200, respuesta.text
        cuerpo = respuesta.json()
        assert cuerpo["ticket_id"] == ticket_id
        assert cuerpo["estado_id"] == datos["estados"]["Cerrado"], (
            "la confirmacion no cambia el estado canonico: Cerrado sigue siendo "
            "terminal"
        )
        assert cuerpo["entrega_confirmada"] is True
        assert cuerpo["etiqueta_proceso"] == ETIQUETA_ENTREGADO
        assert cuerpo["explicacion_proceso"], (
            "el 200 promete la frase corta de la etiqueta"
        )

        historial = leer_historial(cliente, ticket_id)
        assert len(historial) == 1, (
            "exactamente una fila por confirmacion (ticket sembrado por ORM, sin "
            f"fila de creacion): {historial}"
        )
        fila = historial[0]
        assert fila["estado_origen_id"] == datos["estados"]["Cerrado"]
        assert fila["estado_destino_id"] == datos["estados"]["Cerrado"]
        assert fila["usuario_id"] == datos["usuarios_inst01"]["Solicitante"], (
            "el actor es el Solicitante dueño de la sesion"
        )
        assert fila["motivo"] == MOTIVO_CONFIRMACION
        assert fila["orden_compra_id"] is None, (
            "la confirmacion no esta ligada a ninguna orden de compra"
        )
        assert fila["fecha_transicion"], "la fecha la pone el servidor"

    assert _fecha_cierre_persistida(motor, ticket_id) == FECHA_CIERRE, (
        "la confirmacion no sella ni borra fecha_cierre"
    )
    assert leer_stock_sede(motor, datos["sede_id"], datos["producto_id"]) == (
        stock_antes
    ), "la confirmacion no mueve stock"
    assert contar_en(motor, "MovimientoInventario") == movimientos_antes, (
        "la confirmacion no escribe movimientos de inventario"
    )


def test_la_confirmacion_no_reabre_ni_mueve_el_pedido_ac_42(motor, mundo):
    """AC-42: el pedido sigue `Cerrado` y con su `fecha_cierre` intacta."""
    datos = mundo
    ticket_id = _sembrar_cerrado(motor, datos)

    with _cliente_solicitante(motor, datos) as cliente:
        assert _confirmar(cliente, ticket_id).status_code == 200

        despues = abrir_ticket(cliente, ticket_id)
        assert despues["estado_id"] == datos["estados"]["Cerrado"]
        assert despues["fecha_cierre"] is not None
        assert despues["entrega_confirmada"] is True

        retiro = cliente.post(
            f"/api/v1/tickets/{ticket_id}/retiro",
            json={"usuario_id": datos["usuarios_inst01"]["Solicitante"]},
        )
        assert retiro.status_code in (403, 409), (
            "un pedido confirmado no admite un segundo retiro: "
            f"{retiro.status_code} {retiro.text}"
        )

    assert _estado_persistido(motor, ticket_id) == datos["estados"]["Cerrado"]


# ---------------------------------------------------------------------------
# AC-43: 404 identico (ajeno/inexistente), 403 de otros roles y 401
# ---------------------------------------------------------------------------


def test_confirmacion_ajena_e_inexistente_responden_404_identico_ac_43(
    motor, mundo
):
    """AC-43/D-26: el pedido de otro Solicitante es indistinguible del ausente."""
    datos = mundo
    ajeno = _sembrar_cerrado(motor, datos)

    with _cliente_solicitante_ajeno(motor, datos) as cliente:
        respuesta_ajena = _confirmar(cliente, ajeno)
        respuesta_inexistente = _confirmar(cliente, 999999)

    assert respuesta_ajena.status_code == 404, respuesta_ajena.text
    assert respuesta_ajena.json()["detail"] == DETALLE_TICKET_NO_ENCONTRADO
    assert respuesta_inexistente.status_code == 404, respuesta_inexistente.text
    assert respuesta_inexistente.json()["detail"] == (
        respuesta_ajena.json()["detail"]
    ), "el 404 del ajeno debe ser indistinguible del inexistente"
    assert _historial_persistido(motor, ajeno) == [], (
        "una confirmacion ajena no puede escribir historial"
    )
    assert _estado_persistido(motor, ajeno) == datos["estados"]["Cerrado"]


@pytest.mark.parametrize(
    "fabrica",
    [_cliente_administrador, _cliente_bodeguero, _cliente_superadmin],
    ids=["administrador", "bodeguero", "superadmin"],
)
def test_confirmacion_no_se_concede_a_otros_roles_ac_43(motor, mundo, fabrica):
    """AC-43/D-26: Administrador, Bodeguero y Superadmin reciben 403 por matriz."""
    datos = mundo
    ticket_id = _sembrar_cerrado(motor, datos)

    with fabrica(motor, datos) as cliente:
        respuesta = _confirmar(cliente, ticket_id)

    assert respuesta.status_code == 403, respuesta.text
    assert _historial_persistido(motor, ticket_id) == []
    assert _estado_persistido(motor, ticket_id) == datos["estados"]["Cerrado"]


def test_confirmacion_sin_sesion_responde_401_ac_43(motor, mundo):
    """AC-43: sin sesion la precedencia empieza por el 401."""
    datos = mundo
    ticket_id = _sembrar_cerrado(motor, datos)

    with cliente_con_rol(motor, SIN_AUTENTICAR) as cliente:
        respuesta = _confirmar(cliente, ticket_id)

    assert respuesta.status_code == 401, respuesta.text


def test_confirmacion_con_la_capacidad_tickets_apagada_responde_403_ac_43(
    motor, mundo
):
    """AC-43: la capacidad `tickets` apagada bloquea al Solicitante dueño."""
    datos = mundo
    _sembrar_contexto_capacidades(motor, datos, {"tickets"})
    ticket_id = _sembrar_cerrado(motor, datos)

    with _cliente_solicitante(motor, datos, correo=_CORREO_GATING) as cliente:
        respuesta = _confirmar(cliente, ticket_id)

    assert respuesta.status_code == 403, respuesta.text
    assert _historial_persistido(motor, ticket_id) == []


# ---------------------------------------------------------------------------
# AC-43: 409 sin escritura (no Cerrado y ya confirmado)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("estado", ["EnRevision", "EnCurso", "Anulado"])
def test_confirmacion_de_un_pedido_no_cerrado_responde_409_sin_escribir_ac_43(
    motor, mundo, estado
):
    """AC-43: solo un `Cerrado` admite la confirmacion; el resto es 409."""
    datos = mundo
    ticket_id = sembrar_ticket(
        motor, datos, estado_id=datos["estados"][estado]
    )

    with _cliente_solicitante(motor, datos) as cliente:
        respuesta = _confirmar(cliente, ticket_id)
        assert respuesta.status_code == 409, respuesta.text
        assert leer_historial(cliente, ticket_id) == [], (
            "un 409 no puede escribir historial"
        )

    assert _estado_persistido(motor, ticket_id) == datos["estados"][estado]


def test_confirmacion_repetida_responde_409_sin_una_segunda_fila_ac_43(
    motor, mundo
):
    """AC-43/D-25: la segunda confirmacion es 409 y no duplica la fila."""
    datos = mundo
    ticket_id = _sembrar_cerrado(motor, datos)

    with _cliente_solicitante(motor, datos) as cliente:
        primera = _confirmar(cliente, ticket_id)
        segunda = _confirmar(cliente, ticket_id)

        assert primera.status_code == 200, primera.text
        assert segunda.status_code == 409, segunda.text
        assert leer_historial(cliente, ticket_id) and len(
            leer_historial(cliente, ticket_id)
        ) == 1, "solo puede existir una fila de confirmacion"

    assert len(_historial_persistido(motor, ticket_id)) == 1


# ---------------------------------------------------------------------------
# AC-43: el alta administrativa no ofrece confirmacion
# ---------------------------------------------------------------------------


def test_un_pedido_creado_por_un_administrador_no_admite_confirmacion_ac_43(
    motor, mundo
):
    """AC-43/D-26: el dueño sin rol Solicitante no confirma; queda «Retirado»."""
    datos = mundo
    ticket_id = _sembrar_cerrado(motor, datos, usuario_id=datos["usuario_id"])

    with _cliente_administrador(motor, datos) as cliente:
        respuesta = _confirmar(cliente, ticket_id)
        assert respuesta.status_code == 403, respuesta.text

        tarjeta = abrir_ticket(cliente, ticket_id)
        assert tarjeta["etiqueta_proceso"] == ETIQUETA_RETIRADO, (
            "el pedido de alta administrativa permanece «Retirado»"
        )
        assert tarjeta["entrega_confirmada"] is False

    with _cliente_solicitante(motor, datos) as cliente:
        respuesta = _confirmar(cliente, ticket_id)
        assert respuesta.status_code == 404, (
            "un Solicitante que no es el dueño no puede confirmar: "
            f"{respuesta.status_code} {respuesta.text}"
        )

    assert _historial_persistido(motor, ticket_id) == []


# ---------------------------------------------------------------------------
# AC-42/AC-39: listado y detalle coinciden tras la confirmacion
# ---------------------------------------------------------------------------


def test_listado_y_detalle_reflejan_la_entrega_confirmada_ac_42(motor, mundo):
    """AC-42/AC-39: `entrega_confirmada` y la linea «Entregado el … por …»."""
    datos = mundo
    ticket_id = _sembrar_cerrado(motor, datos)

    with _cliente_solicitante(motor, datos) as cliente:
        assert _confirmar(cliente, ticket_id).status_code == 200

        listado = abrir_ticket(cliente, ticket_id)
        detalle = cliente.get(f"/api/v1/tickets/{ticket_id}")
        assert detalle.status_code == 200, detalle.text
        cuerpo = detalle.json()

        assert listado["entrega_confirmada"] is True
        assert cuerpo["entrega_confirmada"] is True
        assert listado["etiqueta_proceso"] == ETIQUETA_ENTREGADO
        assert cuerpo["etiqueta_proceso"] == listado["etiqueta_proceso"], (
            "listado y detalle no pueden divergir en la etiqueta"
        )
        assert cuerpo["estado_nombre"] == "Cerrado", (
            "la etiqueta no reemplaza al estado canonico"
        )
        assert cuerpo["entrega_confirmada_en"] is not None
        assert cuerpo["entrega_confirmada_por_nombre"] == "Solicitante"
        assert cuerpo["entrega_confirmada_por_apellido"] == "Inst01"


# ---------------------------------------------------------------------------
# AC-44: matriz, capacidad y contrato
# ---------------------------------------------------------------------------


def test_matriz_declara_la_confirmacion_solo_para_el_solicitante_ac_44():
    """AC-44/D-26: una operacion nueva y aditiva, solo `Solicitante`."""
    confirmacion = permisos.MATRIZ_PERMISOS.get(("POST", RUTA_CONFIRMACION))
    assert confirmacion is not None, (
        "MATRIZ_PERMISOS debe declarar la operacion de confirmacion de entrega"
    )
    assert set(confirmacion) == {"Solicitante"}
    assert len(permisos.MATRIZ_PERMISOS) == 72, (
        "la matriz suma una operacion en esta tarea (74 -> 75) y la enmienda "
        "27/Nov/2026 de la 012 la deja en 72"
    )
    # El resto de operaciones del flujo conserva sus roles (T21 intacta).
    assert set(permisos.MATRIZ_PERMISOS[("POST", RUTA_APROBACION)]) == {
        "Administrador"
    }
    assert set(permisos.MATRIZ_PERMISOS[("PATCH", RUTA_ESTADO)]) == {
        "Administrador"
    }
    assert set(permisos.MATRIZ_PERMISOS[("POST", RUTA_RETIRO)]) == {
        "Bodeguero"
    }
    assert set(permisos.MATRIZ_PERMISOS[("POST", RUTA_RECHAZO)]) == {
        "Administrador",
        "Bodeguero",
    }


def test_capacidad_tickets_gatea_la_confirmacion_ac_44():
    """AC-44: la confirmacion pertenece a la capacidad `tickets`, sin una nueva."""
    from app.core import capacidades as mapa_capacidades

    assert mapa_capacidades.capacidad_de_operacion("POST", RUTA_CONFIRMACION) == (
        "tickets"
    )
    assert mapa_capacidades.capacidad_de_operacion("POST", RUTA_APROBACION) == (
        "kanban"
    )


def test_openapi_publica_la_confirmacion_con_sus_codigos_ac_44(cliente):
    """AC-44: `/openapi.json` publica la operacion con 200/401/403/404/409."""
    contrato = cliente.get("/openapi.json").json()
    operacion = contrato["paths"].get(RUTA_CONFIRMACION, {}).get("post")
    assert operacion is not None, (
        "falta POST /tickets/{ticket_id}/confirmacion-entrega"
    )

    respuestas = set(operacion.get("responses", {}))
    assert {"200", "401", "403", "404", "409"} <= respuestas, sorted(respuestas)
    assert "requestBody" not in operacion, (
        "la confirmacion no tiene payload obligatorio"
    )
    referencia = (
        operacion["responses"]["200"]["content"]["application/json"]["schema"][
            "$ref"
        ].rsplit("/", 1)[-1]
    )
    assert referencia == "TicketRespuesta", (
        "el 200 promete el DTO con la etiqueta de proceso"
    )


# ---------------------------------------------------------------------------
# AC-42/AC-43: concurrencia secuencial (la real se verifica en PostgreSQL, T23)
# ---------------------------------------------------------------------------


def test_dos_confirmaciones_secuenciales_dan_200_y_409_con_una_sola_fila(motor, mundo):
    """AC-42/AC-43: el doble envio no pasa inadvertido y no duplica la fila."""
    datos = mundo
    ticket_id = _sembrar_cerrado(motor, datos)

    with _cliente_solicitante(motor, datos) as cliente:
        primera = _confirmar(cliente, ticket_id)
        segunda = _confirmar(cliente, ticket_id)

    assert (primera.status_code, segunda.status_code) == (200, 409), (
        primera.text,
        segunda.text,
    )
    filas = _historial_persistido(motor, ticket_id)
    assert len(filas) == 1
    assert filas[0].motivo == MOTIVO_CONFIRMACION
    assert filas[0].orden_compra_id is None
