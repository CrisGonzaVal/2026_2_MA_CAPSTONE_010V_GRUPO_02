"""Feature 007 — enmienda 26/Nov/2026: el alta de tickets es solo del Solicitante.

Seam bajo prueba: la **interfaz HTTP** del `app` real (`TestClient`) con el
harness de identidad mutable de `conftest` (E26N-1): un mismo cliente alterna
roles con `actuar_como` sin recrear el cliente ni pisar overrides. La
expectativa se transcribe de la spec (D-11…D-13, AC-21…AC-25, AC-28, AC-29 y
AC-31); la matriz solo se lee en la comprobacion viva que AC-29 pide
expresamente.

Fuera de este archivo: AC-26/AC-27 viven en
`tests/no_funcional/seguridad/test_institucion_inactiva_012.py` y las seis
transcripciones de la matriz en E26N-4. AC-31 se cubre aquí con tickets
historicos sembrados por ORM (E26N-6), nunca con el alta del Solicitante ni
reasignando autores.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core import permisos
from app.main import app
from app.models import (
    DetalleTicket,
    FuncionInstitucion,
    HistorialTransicionTicket,
    Producto,
    Ticket,
)

from tests.funcional.integracion._soporte_ciclo_vida_013 import (
    instalar_catalogo_ciclo_vida,
    sembrar_contexto_capacidades,
)
from tests.funcional.integracion._soporte_sede_011 import (
    asegurar_sede_de_departamento,
    contar_en,
    sesion,
)

RUTA_ALTA = "/api/v1/tickets/"
CLAVE_MATRIZ_ALTA = ("POST", "/api/v1/tickets/")

#: Rol unico autorizado por la enmienda (D-11).
ROL_AUTORIZADO = "Solicitante"
#: Roles que reciben 403 por matriz (Superadmin se prueba aparte).
ROLES_DENEGADOS = ("Administrador", "Bodeguero")

#: Mensajes literales de la capa de autorizacion (dependencies.py).
DETALLE_PERMISO = "Permiso insuficiente para la operacion"
DETALLE_CAPACIDAD = "La capacidad funcional de la institucion esta deshabilitada"

#: Motivo literal de la confirmacion de entrega (Feature 013, D-25).
MOTIVO_CONFIRMACION = "Entrega confirmada por el solicitante"

#: Correo propio del contexto de capacidades de esta suite (no reutiliza el
#: literal historico de la 013 para que ambas suites no se pisen).
CORREO_GATING_ALTA = "gating007.alta@compustock.cl"

#: Cuerpos **JSON parseable** que incumplen el contrato de `TicketCrear`.
VARIANTES_INVALIDAS = (
    "asunto_corto",
    "detalles_vacio",
    "cantidad_no_positiva",
    "campo_extra",
    "estado_id_ausente",
)

#: Centinela para distinguir `usuario_id` omitido de un valor enviado.
_OMITIDO = object()


# ---------------------------------------------------------------------------
# Payloads
# ---------------------------------------------------------------------------


def _payload(
    datos: dict,
    *,
    prioridad_id: int | None = None,
    estado_id: int | None = None,
    producto_id: int | None = None,
    cantidad: int = 3,
    asunto: str = "Requerimiento de insumos de prueba",
    usuario_id=_OMITIDO,
) -> dict:
    """Payload valido del alta con ids reales de `datos` (nunca inventados)."""
    cuerpo = {
        "prioridad_id": (
            datos["prioridad_id"] if prioridad_id is None else prioridad_id
        ),
        "estado_id": (
            datos["estado_ingresado_id"] if estado_id is None else estado_id
        ),
        "asunto": asunto,
        "descripcion": "Alta de prueba de la enmienda del 26/Nov/2026.",
        "detalles": [
            {
                "producto_id": (
                    datos["producto_id"] if producto_id is None else producto_id
                ),
                "cantidad_solicitada": cantidad,
            }
        ],
    }
    if usuario_id is not _OMITIDO:
        cuerpo["usuario_id"] = usuario_id
    return cuerpo


def _cuerpo_invalido(datos: dict, variante: str) -> dict:
    """Cuerpo JSON parseable que incumple el contrato, por la variante pedida."""
    cuerpo = _payload(datos)
    if variante == "asunto_corto":
        cuerpo["asunto"] = "ab"
    elif variante == "detalles_vacio":
        cuerpo["detalles"] = []
    elif variante == "cantidad_no_positiva":
        cuerpo["detalles"][0]["cantidad_solicitada"] = 0
    elif variante == "campo_extra":
        cuerpo["campo_no_declarado"] = "extra"
    elif variante == "estado_id_ausente":
        cuerpo.pop("estado_id")
    else:  # pragma: no cover - protege contra una variante sin cuerpo definido
        raise AssertionError(f"variante invalida desconocida: {variante}")
    return cuerpo


# ---------------------------------------------------------------------------
# Observacion de lo persistido (independiente del rol del cliente)
# ---------------------------------------------------------------------------


def _conteos_alta(motor) -> tuple[int, int, int]:
    """Filas de ticket, detalle e historial que una denegacion no puede tocar."""
    return (
        contar_en(motor, Ticket),
        contar_en(motor, DetalleTicket),
        contar_en(motor, HistorialTransicionTicket),
    )


def _ticket_persistido(motor, ticket_id: int) -> dict:
    with sesion(motor) as db:
        fila = db.get(Ticket, ticket_id)
        assert fila is not None, f"ticket {ticket_id} no persistido"
        return {
            "usuario_id": fila.usuario_id,
            "estado_id": fila.estado_id,
            "institucion_id": fila.institucion_id,
            "sede_id": fila.sede_id,
            "fecha_cierre": fila.fecha_cierre,
        }


def _detalles_persistidos(motor, ticket_id: int) -> list[dict]:
    with sesion(motor) as db:
        filas = db.execute(
            select(DetalleTicket)
            .where(DetalleTicket.ticket_id == ticket_id)
            .order_by(DetalleTicket.detalle_ticket_id)
        ).scalars().all()
        return [
            {
                "producto_id": fila.producto_id,
                "cantidad_solicitada": fila.cantidad_solicitada,
                "institucion_id": fila.institucion_id,
            }
            for fila in filas
        ]


def _historial_persistido(motor, ticket_id: int) -> list[dict]:
    with sesion(motor) as db:
        filas = db.execute(
            select(HistorialTransicionTicket)
            .where(HistorialTransicionTicket.ticket_id == ticket_id)
            .order_by(HistorialTransicionTicket.historial_transicion_id)
        ).scalars().all()
        return [
            {
                "estado_origen_id": fila.estado_origen_id,
                "estado_destino_id": fila.estado_destino_id,
                "usuario_id": fila.usuario_id,
                "motivo": fila.motivo,
            }
            for fila in filas
        ]


def _desactivar_producto(motor, producto_id: int) -> None:
    """Deja el producto existente pero no disponible (409, no 404)."""
    with sesion(motor) as db:
        producto = db.get(Producto, producto_id)
        producto.activo = False
        db.commit()


def _habilitar_capacidad(motor, institucion_id: str, funcion: str) -> None:
    """Rehabilita una capacidad ya sembrada por `sembrar_contexto_capacidades`."""
    with sesion(motor) as db:
        fila = db.get(FuncionInstitucion, (institucion_id, funcion))
        assert fila is not None, "la capacidad debe existir para rehabilitarla"
        fila.habilitada = True
        db.commit()


def _solicitante_con_correo_de_contexto(actuar_como, correo: str):
    """Solicitante persistido cuya identidad resuelve el gating de capacidad."""
    identidad = actuar_como("Solicitante")
    identidad.usuario.correo = correo
    return identidad


def _sembrar_ticket_historico(
    motor,
    datos: dict,
    *,
    autor_id: int,
    estado_id: int,
    sede_id: int,
    asunto: str,
) -> int:
    """Ticket histórico con autoría Administrador/Bodeguero, por ORM (AC-31).

    Patrón de `test_ciclo_vida_confirmacion_013.py::_sembrar_cerrado`: siembra
    `Ticket`, `DetalleTicket` y la fila de creación de
    `HistorialTransicionTicket` sin pasar por el alta (que ya solo ejerce el
    Solicitante). El autor se fija de una vez y no se reasigna después.
    """
    with sesion(motor) as db:
        ticket = Ticket(
            usuario_id=autor_id,
            prioridad_id=datos["prioridad_id"],
            estado_id=estado_id,
            asunto=asunto,
            descripcion="Ticket histórico de la enmienda del 26/Nov/2026.",
            institucion_id=datos["institucion_id"],
            sede_id=sede_id,
        )
        db.add(ticket)
        db.flush()
        db.add(
            DetalleTicket(
                ticket_id=ticket.ticket_id,
                producto_id=datos["producto_id"],
                cantidad_solicitada=3,
                cantidad_entregada=0,
                institucion_id=datos["institucion_id"],
            )
        )
        db.add(
            HistorialTransicionTicket(
                ticket_id=ticket.ticket_id,
                estado_origen_id=None,
                estado_destino_id=estado_id,
                usuario_id=autor_id,
            )
        )
        db.commit()
        return ticket.ticket_id


# ---------------------------------------------------------------------------
# AC-21 — alta del Solicitante
# ---------------------------------------------------------------------------


def test_solicitante_con_payload_valido_crea_201_con_read_model_ac_21(
    cliente_solicitante, motor, datos_base
):
    """AC-21: 201 con el read model de proceso ya poblado."""
    sede = asegurar_sede_de_departamento(motor, datos_base)

    respuesta = cliente_solicitante.post(RUTA_ALTA, json=_payload(datos_base))

    assert respuesta.status_code == 201, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["usuario_id"] == datos_base["usuario_solicitante_id"]
    assert cuerpo["estado_id"] == datos_base["estado_ingresado_id"]
    assert cuerpo["sede_id"] == sede["sede_id"]
    assert cuerpo["fecha_cierre"] is None
    assert cuerpo["etiqueta_proceso"], "el 201 devuelve el read model de proceso"
    assert {
        "explicacion_proceso",
        "stock_disponible",
        "entrega_confirmada",
        "gestionado_por_bodeguero",
        "gestionado_por_administrador",
    } <= set(cuerpo)
    assert cuerpo["detalles"][0]["producto_id"] == datos_base["producto_id"]


@pytest.mark.parametrize("variante", ["omitido", "propio", "ajeno", "inexistente"])
def test_el_alta_atribuye_siempre_a_la_identidad_de_sesion_ac_21(
    cliente_solicitante, motor, datos_base, variante
):
    """AC-21: `usuario_id` omitido, propio, ajeno o inexistente no cambia el autor."""
    asegurar_sede_de_departamento(motor, datos_base)
    enviados = {
        "omitido": _OMITIDO,
        "propio": datos_base["usuario_solicitante_id"],
        "ajeno": datos_base["usuario_id"],
        "inexistente": 987654,
    }

    respuesta = cliente_solicitante.post(
        RUTA_ALTA, json=_payload(datos_base, usuario_id=enviados[variante])
    )

    assert respuesta.status_code == 201, respuesta.text
    assert respuesta.json()["usuario_id"] == datos_base["usuario_solicitante_id"]


def test_el_alta_nace_en_pendiente_con_institucion_sede_e_historial_ac_21(
    cliente_solicitante, motor, datos_base
):
    """AC-21: autoría, institución, sede, `Pendiente` y fila de creación."""
    sede = asegurar_sede_de_departamento(motor, datos_base)

    respuesta = cliente_solicitante.post(RUTA_ALTA, json=_payload(datos_base))
    assert respuesta.status_code == 201, respuesta.text
    ticket_id = respuesta.json()["ticket_id"]

    ticket = _ticket_persistido(motor, ticket_id)
    assert ticket["usuario_id"] == datos_base["usuario_solicitante_id"]
    assert ticket["estado_id"] == datos_base["estado_ingresado_id"]
    assert ticket["institucion_id"] == datos_base["institucion_id"]
    assert ticket["sede_id"] == sede["sede_id"]
    assert ticket["fecha_cierre"] is None

    detalles = _detalles_persistidos(motor, ticket_id)
    assert len(detalles) == 1
    assert detalles[0]["producto_id"] == datos_base["producto_id"]
    assert detalles[0]["institucion_id"] == datos_base["institucion_id"]

    historial = _historial_persistido(motor, ticket_id)
    assert historial == [
        {
            "estado_origen_id": None,
            "estado_destino_id": datos_base["estado_ingresado_id"],
            "usuario_id": datos_base["usuario_solicitante_id"],
            "motivo": None,
        }
    ]


@pytest.mark.parametrize("referencia", ["prioridad", "estado", "producto"])
def test_referencia_inexistente_responde_404_sin_escritura_ac_21(
    cliente_solicitante, motor, datos_base, referencia
):
    """AC-21: una referencia inexistente es 404 y no deja filas."""
    asegurar_sede_de_departamento(motor, datos_base)
    cuerpos = {
        "prioridad": _payload(datos_base, prioridad_id=987654),
        "estado": _payload(datos_base, estado_id=987654),
        "producto": _payload(datos_base, producto_id=987654),
    }
    antes = _conteos_alta(motor)

    respuesta = cliente_solicitante.post(RUTA_ALTA, json=cuerpos[referencia])

    assert respuesta.status_code == 404, respuesta.text
    assert _conteos_alta(motor) == antes


def test_producto_de_otra_institucion_responde_404_sin_escritura_ac_21(
    cliente_solicitante, motor, dos_instituciones
):
    """AC-21: un producto ajeno se oculta con 404 y no deja ticket parcial."""
    asegurar_sede_de_departamento(motor, dos_instituciones)
    antes = _conteos_alta(motor)

    respuesta = cliente_solicitante.post(
        RUTA_ALTA,
        json=_payload(
            dos_instituciones,
            producto_id=dos_instituciones["producto_homonimo_ajeno_id"],
        ),
    )

    assert respuesta.status_code == 404, respuesta.text
    assert _conteos_alta(motor) == antes


def test_estado_distinto_de_pendiente_responde_409_sin_escritura_ac_21(
    cliente_solicitante, motor, datos_base
):
    """AC-21: un estado inicial distinto de `Pendiente` es 409 sin escribir."""
    asegurar_sede_de_departamento(motor, datos_base)
    antes = _conteos_alta(motor)

    respuesta = cliente_solicitante.post(
        RUTA_ALTA,
        json=_payload(datos_base, estado_id=datos_base["estado_cerrado_id"]),
    )

    assert respuesta.status_code == 409, respuesta.text
    assert _conteos_alta(motor) == antes


def test_departamento_sin_sede_responde_409_sin_escritura_ac_21(
    cliente_solicitante, motor, datos_base
):
    """AC-21: `datos_base` no asigna sede; el alta deniega cerrado con 409."""
    antes = _conteos_alta(motor)

    respuesta = cliente_solicitante.post(RUTA_ALTA, json=_payload(datos_base))

    assert respuesta.status_code == 409, respuesta.text
    assert _conteos_alta(motor) == antes


def test_producto_no_disponible_responde_409_sin_escritura_ac_21(
    cliente_solicitante, motor, datos_base
):
    """AC-21: un producto existente pero inactivo es 409 (no 404)."""
    asegurar_sede_de_departamento(motor, datos_base)
    _desactivar_producto(motor, datos_base["producto_id"])
    antes = _conteos_alta(motor)

    respuesta = cliente_solicitante.post(RUTA_ALTA, json=_payload(datos_base))

    assert respuesta.status_code == 409, respuesta.text
    assert _conteos_alta(motor) == antes


@pytest.mark.parametrize("variante", VARIANTES_INVALIDAS)
def test_solicitante_con_payload_invalido_recibe_422_sin_escribir_ac_21_ac_24(
    cliente_solicitante, motor, datos_base, variante
):
    """AC-21/AC-24: la forma inválida es 422 para el único rol autorizado."""
    asegurar_sede_de_departamento(motor, datos_base)
    antes = _conteos_alta(motor)

    respuesta = cliente_solicitante.post(
        RUTA_ALTA, json=_cuerpo_invalido(datos_base, variante)
    )

    assert respuesta.status_code == 422, respuesta.text
    assert _conteos_alta(motor) == antes


# ---------------------------------------------------------------------------
# AC-22/AC-23 — Administrador y Bodeguero denegados sin efectos
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rol", ROLES_DENEGADOS)
def test_administrador_y_bodeguero_reciben_403_sin_escribir_ac_22_ac_23(
    cliente, actuar_como, motor, datos_base, rol
):
    """AC-22/AC-23: payload válido y capacidad habilitada, pero 403 por matriz."""
    actuar_como(rol)
    asegurar_sede_de_departamento(motor, datos_base)
    antes = _conteos_alta(motor)

    respuesta = cliente.post(RUTA_ALTA, json=_payload(datos_base))

    assert respuesta.status_code == 403, respuesta.text
    assert respuesta.json() == {"detail": DETALLE_PERMISO}
    assert _conteos_alta(motor) == antes


# ---------------------------------------------------------------------------
# AC-24 — el 403 precede al payload con JSON parseable
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rol", ROLES_DENEGADOS)
@pytest.mark.parametrize("variante", VARIANTES_INVALIDAS)
def test_el_403_precede_al_payload_invalido_parseable_ac_24(
    cliente, actuar_como, motor, datos_base, rol, variante
):
    """AC-24: con JSON parseable, Administrador y Bodeguero reciben 403, no 422."""
    actuar_como(rol)
    asegurar_sede_de_departamento(motor, datos_base)
    antes = _conteos_alta(motor)

    respuesta = cliente.post(
        RUTA_ALTA, json=_cuerpo_invalido(datos_base, variante)
    )

    assert respuesta.status_code == 403, respuesta.text
    assert respuesta.json() == {"detail": DETALLE_PERMISO}
    assert _conteos_alta(motor) == antes


# ---------------------------------------------------------------------------
# AC-25 — Superadmin sin cambio
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("variante", ("valido",) + VARIANTES_INVALIDAS)
def test_superadmin_recibe_403_con_json_parseable_ac_25(
    cliente, actuar_como, motor, datos_base, variante
):
    """AC-25: válido o inválido, el Superadmin recibe 403 por matriz."""
    actuar_como("Superadmin")
    asegurar_sede_de_departamento(motor, datos_base)
    cuerpo = (
        _payload(datos_base)
        if variante == "valido"
        else _cuerpo_invalido(datos_base, variante)
    )
    antes = _conteos_alta(motor)

    respuesta = cliente.post(RUTA_ALTA, json=cuerpo)

    assert respuesta.status_code == 403, respuesta.text
    assert respuesta.json() == {"detail": DETALLE_PERMISO}
    assert _conteos_alta(motor) == antes


# ---------------------------------------------------------------------------
# AC-28 — la capacidad `tickets` sigue siendo un gating adicional
# ---------------------------------------------------------------------------


def test_capacidad_tickets_apagada_deniega_y_al_rehabilitarla_crea_ac_28(
    cliente, actuar_como, motor, dos_instituciones
):
    """AC-28: apagada bloquea a los tres roles; rehabilitada crea al Solicitante."""
    datos = dos_instituciones
    sembrar_contexto_capacidades(
        motor, datos, {"tickets"}, correo=CORREO_GATING_ALTA
    )
    sede = asegurar_sede_de_departamento(motor, datos)
    cuerpo = _payload(datos)
    antes = _conteos_alta(motor)

    _solicitante_con_correo_de_contexto(actuar_como, CORREO_GATING_ALTA)
    apagada = cliente.post(RUTA_ALTA, json=cuerpo)
    assert apagada.status_code == 403, apagada.text
    assert apagada.json() == {"detail": DETALLE_CAPACIDAD}
    assert _conteos_alta(motor) == antes

    for rol in ROLES_DENEGADOS:
        actuar_como(rol)
        denegado = cliente.post(RUTA_ALTA, json=cuerpo)
        assert denegado.status_code == 403, denegado.text
        assert _conteos_alta(motor) == antes

    _habilitar_capacidad(motor, datos["inst_propia"], "tickets")
    _solicitante_con_correo_de_contexto(actuar_como, CORREO_GATING_ALTA)

    creado = cliente.post(RUTA_ALTA, json=cuerpo)

    assert creado.status_code == 201, creado.text
    assert creado.json()["sede_id"] == sede["sede_id"]
    assert _conteos_alta(motor) == (antes[0] + 1, antes[1] + 1, antes[2] + 1)


# ---------------------------------------------------------------------------
# AC-29 (parcial) — matriz y contrato publicados
# ---------------------------------------------------------------------------


def test_la_matriz_reserva_el_alta_al_solicitante_ac_29():
    """AC-29: la fila viva es exactamente `{Solicitante}` y no cambia el total."""
    assert permisos.MATRIZ_PERMISOS[CLAVE_MATRIZ_ALTA] == frozenset({ROL_AUTORIZADO})
    assert len(permisos.MATRIZ_PERMISOS) == 75


def test_openapi_del_alta_conserva_el_contrato_y_declara_el_rol_ac_29():
    """AC-29: 201/401/403/404/422; el 409 sigue solo en la descripción."""
    operacion = app.openapi()["paths"][RUTA_ALTA]["post"]

    assert set(operacion["responses"]) == {"201", "401", "403", "404", "422"}, (
        "el 409 no se declara en `responses`; esta enmienda no agrega ni retira "
        "respuestas"
    )
    descripcion = operacion["description"]
    assert "solo el Solicitante" in descripcion
    assert "403" in descripcion
    assert "409" in descripcion


# ---------------------------------------------------------------------------
# AC-31 — los tickets históricos conservan su autoría y su ciclo de vida
# ---------------------------------------------------------------------------


def test_ticket_historico_de_autor_administrador_conserva_su_autoria_ac_31(
    cliente, actuar_como, motor, datos_base
):
    """AC-31/D-16: un ticket sembrado por ORM con autor Administrador conserva
    autor, institución, sede, detalles e historial, y se opera sin reasignarlo.

    El ciclo se ejerce por HTTP (aprobación y despacho del Administrador) y la
    confirmación de entrega se niega porque el dueño no es Solicitante (013
    AC-43).
    """
    sede = asegurar_sede_de_departamento(
        motor, datos_base, stocks={datos_base["producto_id"]: 50}
    )
    estados = instalar_catalogo_ciclo_vida(motor)
    autor = actuar_como("Administrador")
    autor_id = autor.usuario.usuario_id
    ticket_id = _sembrar_ticket_historico(
        motor,
        datos_base,
        autor_id=autor_id,
        estado_id=estados["Pendiente"],
        sede_id=sede["sede_id"],
        asunto="Ticket histórico del Administrador",
    )

    # 1. Se consulta: autor, institución, sede, detalles e historial intactos.
    listado = cliente.get(RUTA_ALTA)
    assert listado.status_code == 200, listado.text
    fila = next(
        (f for f in listado.json() if f["ticket_id"] == ticket_id), None
    )
    assert fila is not None, "el ticket histórico se lista para su institución"
    assert fila["usuario_id"] == autor_id

    respuesta = cliente.get(f"/api/v1/tickets/{ticket_id}")
    assert respuesta.status_code == 200, respuesta.text
    detalle = respuesta.json()
    assert detalle["usuario_id"] == autor_id
    assert detalle["sede_id"] == sede["sede_id"]
    assert detalle["estado_id"] == estados["Pendiente"]
    assert detalle["etiqueta_proceso"] == "En aprobación"
    assert [
        (linea["producto_id"], linea["cantidad_solicitada"])
        for linea in detalle["detalles"]
    ] == [(datos_base["producto_id"], 3)], "los detalles históricos se conservan"
    assert detalle["gestionado_por_administrador"] == {
        "usuario_id": autor_id,
        "nombre": "Ana",
        "apellido": "Perez",
    }, "la creación histórica cuenta como gestión del Administrador"
    assert detalle["gestionado_por_bodeguero"] is None

    persistido = _ticket_persistido(motor, ticket_id)
    assert persistido["usuario_id"] == autor_id
    assert persistido["institucion_id"] == datos_base["institucion_id"]

    historial = _historial_persistido(motor, ticket_id)
    assert historial == [
        {
            "estado_origen_id": None,
            "estado_destino_id": estados["Pendiente"],
            "usuario_id": autor_id,
            "motivo": None,
        }
    ], "el historial histórico conserva su fila de creación y su autor"

    # 2. Se opera según su estado: aprobación y despacho del Administrador.
    aprobacion = cliente.post(f"/api/v1/tickets/{ticket_id}/aprobacion")
    assert aprobacion.status_code == 200, aprobacion.text
    assert aprobacion.json()["estado_id"] == estados["EnCurso"]
    assert _ticket_persistido(motor, ticket_id)["usuario_id"] == autor_id, (
        "aprobar no reasigna el autor histórico"
    )

    despacho = cliente.post(
        f"/api/v1/tickets/{ticket_id}/despacho",
        json={"usuario_id": autor_id},
    )
    assert despacho.status_code == 200, despacho.text
    assert despacho.json()["estado_id"] == estados["Cerrado"]
    assert _ticket_persistido(motor, ticket_id)["usuario_id"] == autor_id, (
        "despachar no reasigna el autor histórico"
    )

    # 3. Sin confirmación de entrega: el dueño no es Solicitante (013 AC-43).
    sin_rol = cliente.post(f"/api/v1/tickets/{ticket_id}/confirmacion-entrega")
    assert sin_rol.status_code == 403, sin_rol.text

    actuar_como("Solicitante")
    ajena = cliente.post(f"/api/v1/tickets/{ticket_id}/confirmacion-entrega")
    assert ajena.status_code == 404, (
        "un Solicitante que no es el dueño no confirma: "
        f"{ajena.status_code} {ajena.text}"
    )

    actuar_como("Administrador")
    final = cliente.get(f"/api/v1/tickets/{ticket_id}")
    assert final.status_code == 200, final.text
    cuerpo = final.json()
    assert cuerpo["usuario_id"] == autor_id
    assert cuerpo["estado_id"] == estados["Cerrado"]
    assert cuerpo["entrega_confirmada"] is False
    assert cuerpo["etiqueta_proceso"] == "Despachado"

    filas = _historial_persistido(motor, ticket_id)
    assert [linea["estado_origen_id"] for linea in filas] == [
        None,
        estados["Pendiente"],
        estados["EnCurso"],
    ], "aprobación y despacho suman sus filas y ninguna confirma la entrega"
    assert all(linea["motivo"] != MOTIVO_CONFIRMACION for linea in filas)


def test_ticket_historico_de_autor_bodeguero_conserva_su_autoria_ac_31(
    cliente, actuar_como, motor, datos_base
):
    """AC-31/D-16: el ticket histórico del Bodeguero conserva autor, sede,
    detalles e historial, y aprobarlo no reasigna su autoría."""
    sede = asegurar_sede_de_departamento(motor, datos_base)
    estados = instalar_catalogo_ciclo_vida(motor)
    autor = actuar_como("Bodeguero")
    autor_id = autor.usuario.usuario_id
    ticket_id = _sembrar_ticket_historico(
        motor,
        datos_base,
        autor_id=autor_id,
        estado_id=estados["Pendiente"],
        sede_id=sede["sede_id"],
        asunto="Ticket histórico del Bodeguero",
    )

    respuesta = cliente.get(f"/api/v1/tickets/{ticket_id}")
    assert respuesta.status_code == 200, respuesta.text
    detalle = respuesta.json()
    assert detalle["usuario_id"] == autor_id
    assert detalle["sede_id"] == sede["sede_id"]
    assert detalle["gestionado_por_bodeguero"] == {
        "usuario_id": autor_id,
        "nombre": "Bodeguero",
        "apellido": "Prueba",
    }, "la creación histórica cuenta como gestión del Bodeguero"
    assert detalle["gestionado_por_administrador"] is None
    assert [
        (linea["producto_id"], linea["cantidad_solicitada"])
        for linea in detalle["detalles"]
    ] == [(datos_base["producto_id"], 3)]

    persistido = _ticket_persistido(motor, ticket_id)
    assert persistido["usuario_id"] == autor_id
    assert persistido["institucion_id"] == datos_base["institucion_id"]

    historial = _historial_persistido(motor, ticket_id)
    assert [linea["usuario_id"] for linea in historial] == [autor_id]
    assert [linea["estado_origen_id"] for linea in historial] == [None]

    actuar_como("Administrador")
    aprobacion = cliente.post(f"/api/v1/tickets/{ticket_id}/aprobacion")
    assert aprobacion.status_code == 200, aprobacion.text
    assert aprobacion.json()["estado_id"] == estados["EnCurso"]
    assert _ticket_persistido(motor, ticket_id)["usuario_id"] == autor_id, (
        "aprobar no reasigna el autor histórico"
    )
