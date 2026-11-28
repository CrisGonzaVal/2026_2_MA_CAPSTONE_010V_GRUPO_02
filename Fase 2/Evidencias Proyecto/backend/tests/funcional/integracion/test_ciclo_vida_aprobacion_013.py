"""Feature 013 (ampliacion 25/Nov/2026): aprobacion Admin-only (AC-28…AC-32/36/45/46/49).

Seam bajo prueba: la **interfaz HTTP** del `app` real (`TestClient`), como en el
resto de la suite. La aprobacion es una operacion semantica propia
(`POST /api/v1/tickets/{ticket_id}/aprobacion`) que lleva el pedido desde
`EnRevision` **siempre** a `EnCurso`, con una sola fila de historial (origen
real -> `EnCurso`, actor = Administrador, motivo literal
`Aprobación del pedido`, `orden_compra_id` nulo) y sin evaluar stock, reservar
ni tocar `fecha_cierre` (spec §9.2 D-15/D-16/D-17, §9.3, AC-52).

El `PATCH /estado` conserva su contrato de legado (un paso, cierre reservado al
retiro, terminalidad por nombre) pero deja de concederse al Bodeguero
(§9.10, AC-49). El Bodeguero conserva despacho y rechazo hasta T35.

La matriz y el contrato se transcriben a mano desde la spec (nunca se leen de
`permisos.MATRIZ_PERMISOS` como fuente de la expectativa).
"""

from __future__ import annotations

import pytest
from sqlalchemy import select, text

from app.core import permisos
from app.core.config import VERSION_ESQUEMA_OBJETIVO
from app.models import (
    CAPACIDADES,
    FuncionInstitucion,
    InstitucionControl,
    MapaUsuarioEsquema,
    Ticket,
    VersionEsquema,
)

from tests.funcional.integracion._soporte_ciclo_vida_013 import (
    DETALLE_TICKET_NO_ENCONTRADO,
    SIN_AUTENTICAR,
    abrir_ticket,
    cliente_con_rol,
    contar_en,
    leer_historial,
    leer_stock_sede,
    sembrar_mundo_013,
    sembrar_ticket,
    sesion,
)

#: Contrato de la ampliacion (spec §9.4).
RUTA_APROBACION = "/api/v1/tickets/{ticket_id}/aprobacion"
RUTA_ESTADO = "/api/v1/tickets/{ticket_id}/estado"
RUTA_RETIRO = "/api/v1/tickets/{ticket_id}/retiro"
RUTA_RECHAZO = "/api/v1/tickets/{ticket_id}/rechazo"

#: Motivo literal del historial (spec D-16). Fuente independiente del codigo.
MOTIVO_APROBACION = "Aprobación del pedido"

#: Etiquetas de proceso de la spec §9.8 que decide el stock tras la aprobacion.
ETIQUETA_EN_CONFIRMACION_STOCK = "En confirmación de stock local"
ETIQUETA_POR_COMPRAR = "Por comprar"

#: Correo del contexto de capacidades del gating (distinto del resto de suites).
_CORREO_GATING = "gating013.aprobacion@compustock.cl"


# ---------------------------------------------------------------------------
# Mundos y clientes
# ---------------------------------------------------------------------------


@pytest.fixture
def mundo_con_stock(motor, dos_instituciones):
    """Estados 013, sede del departamento y 50 unidades del producto base."""
    return sembrar_mundo_013(motor, dos_instituciones)


@pytest.fixture
def mundo_sin_stock(motor, dos_instituciones):
    """Mismo mundo con sede asignada pero **sin** saldo del producto base."""
    return sembrar_mundo_013(motor, dos_instituciones, con_stock=False)


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
        sede_id=datos["sede_id"],
    )


def _cliente_solicitante(motor, datos):
    return cliente_con_rol(
        motor,
        "Solicitante",
        departamento_id=datos["departamento_id"],
        usuario_id=datos["usuarios_inst01"]["Solicitante"],
    )


def _cliente_superadmin(motor, datos):
    return cliente_con_rol(
        motor,
        "Superadmin",
        departamento_id=datos["departamento_id"],
        usuario_id=datos["usuarios_inst01"]["Superadmin"],
    )


def _cliente_admin_ajeno(motor, datos):
    return cliente_con_rol(
        motor,
        "Administrador",
        departamento_id=datos["departamento_ajeno_id"],
        usuario_id=datos["usuarios_inst02"]["Administrador"],
    )


# ---------------------------------------------------------------------------
# Observacion
# ---------------------------------------------------------------------------


def _aprobar(cliente, ticket_id: int):
    """`POST /aprobacion` sin payload, como lo invoca la vista de detalle."""
    return cliente.post(f"/api/v1/tickets/{ticket_id}/aprobacion")


def _estado_persistido(motor, ticket_id: int) -> int | None:
    """Estado por ORM, para escenarios donde el cliente no puede listar."""
    with sesion(motor) as db:
        return db.get(Ticket, ticket_id).estado_id


# ---------------------------------------------------------------------------
# AC-52: 200 desde EnRevision; destino siempre EnCurso
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("origen", ["EnRevision"])
def test_aprobacion_desde_origen_elegible_deja_el_pedido_en_curso_ac_52(
    motor, mundo_con_stock, origen
):
    """AC-52: solo `EnRevision` se aprueba a `EnCurso`."""
    datos = mundo_con_stock
    ticket_id = sembrar_ticket(
        motor, datos, estado_id=datos["estados"][origen]
    )

    with _cliente_administrador(motor, datos) as cliente:
        respuesta = _aprobar(cliente, ticket_id)

        assert respuesta.status_code == 200, respuesta.text
        cuerpo = respuesta.json()
        assert cuerpo["ticket_id"] == ticket_id
        assert cuerpo["estado_id"] == datos["estados"]["EnCurso"], (
            f"la aprobacion desde {origen} debe dejar el pedido en EnCurso"
        )
        assert cuerpo["fecha_cierre"] is None, (
            "aprobar no es un cierre por despacho: fecha_cierre sigue nula"
        )
        assert cuerpo["etiqueta_proceso"] == ETIQUETA_EN_CONFIRMACION_STOCK
        assert cuerpo["stock_disponible"] is True
        assert abrir_ticket(cliente, ticket_id)["estado_id"] == (
            datos["estados"]["EnCurso"]
        )


@pytest.mark.parametrize(
    "mundo,etiqueta,stock_disponible",
    [
        ("mundo_con_stock", ETIQUETA_EN_CONFIRMACION_STOCK, True),
        ("mundo_sin_stock", ETIQUETA_POR_COMPRAR, False),
    ],
    ids=["con_stock", "sin_stock"],
)
def test_aprobacion_siempre_lleva_a_en_curso_y_el_stock_solo_cambia_la_etiqueta_ac_29(
    motor, request, mundo, etiqueta, stock_disponible
):
    """AC-29/D-17: el stock decide la etiqueta, nunca el estado destino."""
    datos = request.getfixturevalue(mundo)
    ticket_id = sembrar_ticket(
        motor, datos, estado_id=datos["estados"]["EnRevision"]
    )

    with _cliente_administrador(motor, datos) as cliente:
        respuesta = _aprobar(cliente, ticket_id)

        assert respuesta.status_code == 200, respuesta.text
        cuerpo = respuesta.json()
        assert cuerpo["estado_id"] == datos["estados"]["EnCurso"], (
            "con stock o sin el, la aprobacion deja el pedido en EnCurso"
        )
        assert cuerpo["etiqueta_proceso"] == etiqueta
        assert cuerpo["stock_disponible"] is stock_disponible
        assert cuerpo["fecha_cierre"] is None


def test_aprobacion_no_toca_stock_ni_movimientos_ac_29(motor, mundo_con_stock):
    """AC-29/D-18: aprobar no reserva, no rebaja stock ni audita movimiento."""
    datos = mundo_con_stock
    ticket_id = sembrar_ticket(
        motor, datos, estado_id=datos["estados"]["EnRevision"]
    )
    stock_antes = leer_stock_sede(motor, datos["sede_id"], datos["producto_id"])
    movimientos_antes = contar_en(motor, "MovimientoInventario")

    with _cliente_administrador(motor, datos) as cliente:
        respuesta = _aprobar(cliente, ticket_id)
        assert respuesta.status_code == 200, respuesta.text

    assert leer_stock_sede(motor, datos["sede_id"], datos["producto_id"]) == (
        stock_antes
    ), "la aprobacion no evalua ni rebaja stock"
    assert contar_en(motor, "MovimientoInventario") == movimientos_antes, (
        "la aprobacion no escribe movimientos de inventario"
    )


# ---------------------------------------------------------------------------
# AC-30: exactamente una fila de historial, con actor y motivo literales
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("origen", ["EnRevision"])
def test_aprobacion_escribe_una_sola_fila_con_actor_y_motivo_ac_30(
    motor, mundo_con_stock, origen
):
    """AC-30/D-16: origen real -> `EnCurso`, actor de sesion, motivo literal."""
    datos = mundo_con_stock
    ticket_id = sembrar_ticket(motor, datos, estado_id=datos["estados"][origen])

    with _cliente_administrador(motor, datos) as cliente:
        respuesta = _aprobar(cliente, ticket_id)
        assert respuesta.status_code == 200, respuesta.text

        historial = leer_historial(cliente, ticket_id)
        assert len(historial) == 1, (
            "exactamente una fila por aprobacion (ticket sembrado por ORM, sin "
            f"fila de creacion): {historial}"
        )
        fila = historial[0]
        assert fila["estado_origen_id"] == datos["estados"][origen], (
            "el origen registrado es el estado real del pedido"
        )
        assert fila["estado_destino_id"] == datos["estados"]["EnCurso"]
        assert fila["usuario_id"] == datos["usuario_id"], (
            "el actor es el Administrador de la sesion, nunca un 'sistema'"
        )
        assert fila["usuario_id"] != datos["usuarios_inst01"]["Solicitante"]
        assert fila["motivo"] == MOTIVO_APROBACION
        assert fila["orden_compra_id"] is None, (
            "la aprobacion no esta ligada a ninguna orden de compra"
        )


def test_si_la_fila_de_historial_falla_el_estado_no_cambia_ac_30(
    motor, cliente_sin_excepcion, mundo_con_stock
):
    """AC-30/AC-11: si la fila no puede escribirse, el estado no cambia.

    Se retira la tabla del historial del motor de prueba (mismo patron que AC-11
    de la 013) y `cliente_sin_excepcion` convierte el fallo en un 500
    observable. El estado se lee por ORM porque el listado tambien depende de la
    tabla retirada.
    """
    datos = mundo_con_stock
    ticket_id = sembrar_ticket(
        motor, datos, estado_id=datos["estados"]["EnRevision"]
    )

    with motor.begin() as conexion:
        conexion.execute(text("DROP TABLE IF EXISTS historial_transicion_ticket"))

    respuesta = cliente_sin_excepcion.post(
        f"/api/v1/tickets/{ticket_id}/aprobacion"
    )

    assert respuesta.status_code == 500, (
        f"sin la tabla del historial la aprobacion debe fallar completa: {respuesta.text}"
    )
    assert _estado_persistido(motor, ticket_id) == datos["estados"]["EnRevision"], (
        "si la fila no pudo registrarse, el pedido conserva su estado"
    )


# ---------------------------------------------------------------------------
# AC-46: 409 sin escritura (ya/terminal/catalogo) y 404 identico
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("estado", ["EnCurso", "Cerrado", "Anulado"])
def test_aprobacion_de_un_estado_ya_avanzado_o_terminal_responde_409_ac_46(
    motor, mundo_con_stock, estado
):
    """AC-46: `EnCurso`, `Cerrado` y `Anulado` responden 409 sin escribir."""
    datos = mundo_con_stock
    ticket_id = sembrar_ticket(motor, datos, estado_id=datos["estados"][estado])

    with _cliente_administrador(motor, datos) as cliente:
        respuesta = _aprobar(cliente, ticket_id)

        assert respuesta.status_code == 409, respuesta.text
        assert abrir_ticket(cliente, ticket_id)["estado_id"] == (
            datos["estados"][estado]
        ), "un 409 no puede cambiar el estado"
        assert leer_historial(cliente, ticket_id) == [], (
            "un 409 no puede escribir historial"
        )


def test_aprobacion_de_un_estado_no_elegible_responde_409_sin_escribir_ac_46(
    motor, dos_instituciones
):
    """AC-46: un estado existente pero no elegible (`Archivado`) responde 409."""
    datos = sembrar_mundo_013(
        motor,
        dos_instituciones,
        nombres_estados=(
            "EnRevision",
            "EnCurso",
            "Cerrado",
            "Anulado",
            "Archivado",
        ),
    )
    ticket_id = sembrar_ticket(
        motor, datos, estado_id=datos["estados"]["Archivado"]
    )

    with _cliente_administrador(motor, datos) as cliente:
        respuesta = _aprobar(cliente, ticket_id)

        assert respuesta.status_code == 409, respuesta.text
        assert abrir_ticket(cliente, ticket_id)["estado_id"] == (
            datos["estados"]["Archivado"]
        )
        assert leer_historial(cliente, ticket_id) == []


def test_aprobacion_sin_en_curso_en_el_catalogo_responde_409_sin_escribir_ac_46(
    motor, dos_instituciones
):
    """AC-46: sin `EnCurso` en el catalogo la operacion deniega cerrado (409)."""
    datos = sembrar_mundo_013(
        motor,
        dos_instituciones,
        nombres_estados=("EnRevision", "Cerrado", "Anulado"),
    )
    ticket_id = sembrar_ticket(
        motor, datos, estado_id=datos["estados"]["EnRevision"]
    )

    with _cliente_administrador(motor, datos) as cliente:
        respuesta = _aprobar(cliente, ticket_id)

        assert respuesta.status_code == 409, respuesta.text
        assert abrir_ticket(cliente, ticket_id)["estado_id"] == (
            datos["estados"]["EnRevision"]
        ), "el fail-closed del catalogo no puede escribir"
        assert leer_historial(cliente, ticket_id) == []


def test_aprobacion_inexistente_y_ajena_responden_404_identico_ac_46(
    motor, mundo_con_stock
):
    """AC-46/D-8: inexistente y de otra institucion son 404 indistinguibles."""
    datos = mundo_con_stock
    propio = sembrar_ticket(
        motor, datos, estado_id=datos["estados"]["EnRevision"]
    )
    ajeno = sembrar_ticket(
        motor,
        datos,
        usuario_id=datos["usuarios_inst01"]["Solicitante"],
        estado_id=datos["estados"]["EnRevision"],
    )

    with _cliente_administrador(motor, datos) as cliente:
        inexistente = _aprobar(cliente, 999999)
        aprobado_propio = _aprobar(cliente, propio)
        assert aprobado_propio.status_code == 200, aprobado_propio.text

    with _cliente_admin_ajeno(motor, datos) as cliente_ajeno:
        respuesta_ajena = _aprobar(cliente_ajeno, ajeno)
        respuesta_inexistente = _aprobar(cliente_ajeno, 999999)

        assert respuesta_ajena.status_code == 404, respuesta_ajena.text
        assert respuesta_ajena.json()["detail"] == DETALLE_TICKET_NO_ENCONTRADO
        assert respuesta_inexistente.status_code == 404
        assert respuesta_inexistente.json()["detail"] == (
            respuesta_ajena.json()["detail"]
        ), "el 404 del ajeno debe ser indistinguible del inexistente"

    assert inexistente.status_code == 404, inexistente.text
    assert _estado_persistido(motor, ajeno) == datos["estados"]["EnRevision"], (
        "la aprobacion ajena no puede mutar el pedido"
    )


# ---------------------------------------------------------------------------
# AC-45: 403 por roles y por capacidad, 401 sin sesion
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "fabrica",
    [_cliente_bodeguero, _cliente_solicitante, _cliente_superadmin],
    ids=["bodeguero", "solicitante", "superadmin"],
)
def test_aprobacion_no_se_concede_a_otros_roles_ac_45(
    motor, mundo_con_stock, fabrica
):
    """AC-45: Bodeguero, Solicitante y Superadmin reciben 403 por matriz."""
    datos = mundo_con_stock
    ticket_id = sembrar_ticket(
        motor, datos, estado_id=datos["estados"]["EnRevision"]
    )

    with fabrica(motor, datos) as cliente:
        respuesta = _aprobar(cliente, ticket_id)

        assert respuesta.status_code == 403, respuesta.text

    assert _estado_persistido(motor, ticket_id) == datos["estados"]["EnRevision"], (
        "el 403 no puede mutar el pedido"
    )


def _sembrar_contexto_capacidades(motor, datos, capacidades_apagadas=frozenset()):
    """Control coherente para que el correo del gating resuelva a INST01.

    Mismo patron que `test_ciclo_vida_autorizacion_013.py`: institucion canonica
    activa, mapa `correo -> esquema`, version objetivo y las siete capacidades
    con las apagadas explicitas.
    """
    institucion_id = datos["inst_propia"]
    with sesion(motor) as db:
        if db.get(InstitucionControl, institucion_id) is None:
            db.add(
                InstitucionControl(
                    institucion_id=institucion_id,
                    nombre="Instituto de Prueba",
                    activo=True,
                )
            )
            db.flush()
        if db.get(MapaUsuarioEsquema, _CORREO_GATING) is None:
            db.add(
                MapaUsuarioEsquema(
                    correo=_CORREO_GATING,
                    institucion_id=institucion_id,
                    nombre_esquema="tenant_inst01",
                    activo=True,
                )
            )
            db.flush()
        if db.execute(select(VersionEsquema)).scalars().first() is None:
            db.add(VersionEsquema(version=VERSION_ESQUEMA_OBJETIVO))
        for funcion in CAPACIDADES:
            db.add(
                FuncionInstitucion(
                    institucion_id=institucion_id,
                    funcion=funcion,
                    habilitada=funcion not in capacidades_apagadas,
                )
            )
        db.commit()


def test_aprobacion_con_kanban_apagada_responde_403_sin_mutar_ac_45(
    motor, mundo_con_stock
):
    """AC-45: la capacidad `kanban` apagada bloquea la aprobacion del Admin."""
    datos = mundo_con_stock
    _sembrar_contexto_capacidades(motor, datos, {"kanban"})
    ticket_id = sembrar_ticket(
        motor, datos, estado_id=datos["estados"]["EnRevision"]
    )

    with _cliente_administrador(motor, datos, correo=_CORREO_GATING) as cliente:
        respuesta = _aprobar(cliente, ticket_id)

        assert respuesta.status_code == 403, respuesta.text

    assert _estado_persistido(motor, ticket_id) == datos["estados"]["EnRevision"]


def test_aprobacion_sin_sesion_responde_401_ac_46(motor, mundo_con_stock):
    """AC-46: sin sesion la precedencia empieza por el 401."""
    datos = mundo_con_stock
    ticket_id = sembrar_ticket(
        motor, datos, estado_id=datos["estados"]["EnRevision"]
    )

    with cliente_con_rol(motor, SIN_AUTENTICAR) as cliente:
        respuesta = _aprobar(cliente, ticket_id)

    assert respuesta.status_code == 401, respuesta.text


# ---------------------------------------------------------------------------
# AC-49: el PATCH /estado queda solo para el Administrador
# ---------------------------------------------------------------------------


def test_patch_estado_deniega_al_bodeguero_por_matriz_ac_49(motor, mundo_con_stock):
    """AC-49: el Bodeguero pierde el `PATCH /estado` (403, sin mutacion)."""
    datos = mundo_con_stock
    ticket_id = sembrar_ticket(
        motor, datos, estado_id=datos["estados"]["EnRevision"]
    )

    with _cliente_bodeguero(motor, datos) as cliente:
        respuesta = cliente.patch(
            f"/api/v1/tickets/{ticket_id}/estado",
            json={"estado_id": datos["estados"]["EnRevision"]},
        )

        assert respuesta.status_code == 403, respuesta.text

    assert _estado_persistido(motor, ticket_id) == datos["estados"]["EnRevision"]


def test_patch_estado_conserva_su_contrato_de_legado_para_el_administrador_ac_49(
    motor, mundo_con_stock
):
    """AC-49/AC-60: el Administrador conserva el paso y el cierre reservado."""
    datos = mundo_con_stock
    ticket_id = sembrar_ticket(
        motor, datos, estado_id=datos["estados"]["EnRevision"]
    )

    with _cliente_administrador(motor, datos) as cliente:
        en_curso = cliente.patch(
            f"/api/v1/tickets/{ticket_id}/estado",
            json={"estado_id": datos["estados"]["EnCurso"]},
        )
        assert en_curso.status_code == 200, en_curso.text
        assert en_curso.json()["estado_id"] == datos["estados"]["EnCurso"]

        retroceso = cliente.patch(
            f"/api/v1/tickets/{ticket_id}/estado",
            json={"estado_id": datos["estados"]["EnRevision"]},
        )
        assert retroceso.status_code == 200, retroceso.text

        avance = cliente.patch(
            f"/api/v1/tickets/{ticket_id}/estado",
            json={"estado_id": datos["estados"]["EnCurso"]},
        )
        assert avance.status_code == 200, avance.text

        cierre = cliente.patch(
            f"/api/v1/tickets/{ticket_id}/estado",
            json={"estado_id": datos["estados"]["Cerrado"]},
        )
        assert cierre.status_code == 409, cierre.text
        assert cierre.json()["detail"] == (
            "El cierre requiere retiro; use "
            f"POST /api/v1/tickets/{ticket_id}/retiro"
        )

        assert abrir_ticket(cliente, ticket_id)["estado_id"] == (
            datos["estados"]["EnCurso"]
        ), "el 409 del cierre reservado no puede mover el pedido"


def test_el_bodeguero_conserva_despacho_y_rechazo_ac_49(motor, mundo_con_stock):
    """AC-49: el Bodeguero mantiene sus operaciones propias (no el PATCH)."""
    datos = mundo_con_stock
    a_despachar = sembrar_ticket(
        motor, datos, estado_id=datos["estados"]["EnCurso"]
    )
    a_rechazar = sembrar_ticket(
        motor, datos, estado_id=datos["estados"]["EnRevision"]
    )

    with _cliente_bodeguero(motor, datos) as cliente:
        despacho = cliente.post(
            f"/api/v1/tickets/{a_despachar}/retiro",
            json={"usuario_id": datos["usuarios_inst01"]["Bodeguero"]},
        )
        assert despacho.status_code == 200, despacho.text
        assert despacho.json()["estado_id"] == datos["estados"]["Cerrado"]

        rechazo = cliente.post(
            f"/api/v1/tickets/{a_rechazar}/rechazo",
            json={"motivo": "Rechazo del Bodeguero dentro de su operacion"},
        )
        assert rechazo.status_code == 200, rechazo.text
        assert rechazo.json()["estado_id"] == datos["estados"]["Anulado"]


# ---------------------------------------------------------------------------
# AC-44: matriz y contrato de la ampliacion
# ---------------------------------------------------------------------------


def test_matriz_declara_la_aprobacion_y_el_patch_solo_para_administrador_ac_44():
    """AC-44/AC-49: una operacion nueva y el PATCH restringido; el resto igual."""
    aprobacion = permisos.MATRIZ_PERMISOS.get(("POST", RUTA_APROBACION))
    assert aprobacion is not None, (
        "MATRIZ_PERMISOS debe declarar la operacion de aprobacion"
    )
    assert set(aprobacion) == {"Administrador"}
    assert set(permisos.MATRIZ_PERMISOS[("PATCH", RUTA_ESTADO)]) == {
        "Administrador"
    }, "el PATCH de legado deja de concederse al Bodeguero"
    assert len(permisos.MATRIZ_PERMISOS) == 73, (
        "la matriz suma una operacion por tarea de la ampliacion (73 -> 74 en "
        "T21 y 74 -> 75 con la confirmacion de entrega en T22), la enmienda "
        "27/Nov/2026 de la 012 la deja en 72 y la Feature 028 (T5) suma el "
        "canal de tiempo real"
    )
    # Las operaciones propias del Bodeguero no cambian de roles.
    assert set(permisos.MATRIZ_PERMISOS[("POST", RUTA_RETIRO)]) == {
        "Bodeguero"
    }
    assert set(permisos.MATRIZ_PERMISOS[("POST", RUTA_RECHAZO)]) == {
        "Administrador",
        "Bodeguero",
    }
    assert set(permisos.MATRIZ_PERMISOS[("POST", "/api/v1/tickets/{ticket_id}/anulacion")]) == {
        "Administrador",
        "Solicitante",
    }


def test_capacidad_kanban_gatea_la_aprobacion_ac_44():
    """AC-44: la aprobacion pertenece a la capacidad `kanban`, sin una nueva."""
    from app.core import capacidades as mapa_capacidades

    assert mapa_capacidades.capacidad_de_operacion("POST", RUTA_APROBACION) == (
        "kanban"
    )
    assert mapa_capacidades.capacidad_de_operacion("PATCH", RUTA_ESTADO) == "kanban"


def test_openapi_publica_la_aprobacion_con_sus_codigos_ac_44(cliente):
    """AC-44: `/openapi.json` publica la operacion con 200/401/403/404/409."""
    contrato = cliente.get("/openapi.json").json()
    operacion = contrato["paths"].get(RUTA_APROBACION, {}).get("post")
    assert operacion is not None, "falta POST /tickets/{ticket_id}/aprobacion"

    respuestas = set(operacion.get("responses", {}))
    assert {"200", "401", "403", "404", "409"} <= respuestas, sorted(respuestas)
    assert "requestBody" not in operacion, (
        "la aprobacion no tiene payload obligatorio"
    )
    referencia = (
        operacion["responses"]["200"]["content"]["application/json"]["schema"][
            "$ref"
        ].rsplit("/", 1)[-1]
    )
    assert referencia == "TicketRespuesta", (
        "el 200 promete el DTO con la etiqueta de proceso"
    )
