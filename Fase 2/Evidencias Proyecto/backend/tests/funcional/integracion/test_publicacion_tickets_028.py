"""Publicacion de pedidos desde las mutaciones de ticket (Feature 028, T8).

Seam bajo prueba: la **interfaz HTTP** del `app` real (`TestClient`) con el
`BusFalso` de T4 instalado por `instalar_bus`, que enciende
`TIEMPO_REAL_HABILITADO` y guarda cada sobre publicado. Asi se comprueba el
efecto observable de la mutacion (status, cuerpo y sobre) sin tocar la capa de
servicios mas alla de la costura de rollback forzado.

Tabla cubierta (spec §5.2 y Anexo A, filas 1-3 y 5-9):

| Mutacion | Motivo | Dominios | Dueno |
|---|---|---|---|
| `POST /tickets/` | `alta` | `pedidos` | `ticket.usuario_id` |
| `PUT /tickets/{id}` | `edicion` | `pedidos` | `ticket.usuario_id` |
| `POST .../aprobacion` | `aprobacion` | `pedidos` | `ticket.usuario_id` |
| `POST .../confirmacion-entrega` | `confirmacion_entrega` | `pedidos` | `ticket.usuario_id` |
| `PATCH .../estado` | `cambio_estado` | `pedidos` | `ticket.usuario_id` |
| `POST .../anulacion` desde `EnRevision` | `anulacion` | `pedidos` | `ticket.usuario_id` |
| `POST .../rechazo` | `rechazo` | `pedidos` | `ticket.usuario_id` |

Reglas verificadas ademas de la tabla: publicacion **posterior al commit**,
**un solo sobre** por mutacion confirmada, silencio en 404/409/422, silencio
tras un rollback forzado y respuesta intacta con el bus caido (fail-open).
El retiro y la anulacion administrativa desde `Cerrado` son de T9 y no se
prueban aqui.
"""

from __future__ import annotations

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session, sessionmaker

from app.models import Ticket
from app.services import ticket_service

from tests.funcional.integracion._soporte_ciclo_vida_013 import (
    cliente_con_rol,
    payload_alta,
    sembrar_mundo_013,
    sembrar_ticket,
)
from tests.funcional.integracion._soporte_eventos_028 import instalar_bus

RUTA_ALTA = "/api/v1/tickets/"
RUTA_EDICION = "/api/v1/tickets/{ticket_id}"
RUTA_APROBACION = "/api/v1/tickets/{ticket_id}/aprobacion"
RUTA_CONFIRMACION = "/api/v1/tickets/{ticket_id}/confirmacion-entrega"
RUTA_ESTADO = "/api/v1/tickets/{ticket_id}/estado"
RUTA_ANULACION = "/api/v1/tickets/{ticket_id}/anulacion"
RUTA_RECHAZO = "/api/v1/tickets/{ticket_id}/rechazo"

#: Institucion de la semilla (`datos_base`/`dos_instituciones`).
INSTITUCION = "INST01"


# ---------------------------------------------------------------------------
# Mundo y clientes
# ---------------------------------------------------------------------------


@pytest.fixture
def mundo(motor, dos_instituciones):
    """Catalogo de estados del ciclo de vida, sede del departamento y stock."""
    return sembrar_mundo_013(motor, dos_instituciones)


def _cliente(motor, datos, rol: str):
    """`TestClient` con la identidad del rol institucional pedido."""
    if rol == "Administrador":
        return cliente_con_rol(
            motor,
            "Administrador",
            departamento_id=datos["departamento_id"],
            usuario_id=datos["usuario_id"],
        )
    if rol == "Bodeguero":
        return cliente_con_rol(
            motor,
            "Bodeguero",
            departamento_id=datos["departamento_id"],
            usuario_id=datos["usuarios_inst01"]["Bodeguero"],
            sede_id=datos["sede_id"],
        )
    if rol == "Solicitante":
        return cliente_con_rol(
            motor,
            "Solicitante",
            departamento_id=datos["departamento_id"],
            usuario_id=datos["usuarios_inst01"]["Solicitante"],
        )
    raise ValueError(f"rol no soportado por el escenario: {rol!r}")


def _dueno(datos) -> int:
    return datos["usuarios_inst01"]["Solicitante"]


# ---------------------------------------------------------------------------
# Observacion de la publicacion
# ---------------------------------------------------------------------------


def _sobre_unico(bus):
    """Un unico sobre publicado; falla con el conteo real si hubo cero o varios."""
    assert len(bus.publicados) == 1, (
        "se esperaba exactamente un sobre publicado por la mutacion; "
        f"hubo {len(bus.publicados)}: {bus.publicados!r}"
    )
    return bus.publicados[0]


def _afirmar_sobre_de_pedidos(sobre, *, motivo: str, usuario_id: int) -> None:
    """Contrato del sobre de T8: un dominio `pedidos`, el motivo y el dueno."""
    assert sobre.dominios == frozenset({"pedidos"}), (
        f"T8 solo anuncia `pedidos`; llego {sorted(sobre.dominios)}"
    )
    assert sobre.motivo == motivo
    assert sobre.institucion_id == INSTITUCION
    assert sobre.usuario_ids == frozenset({usuario_id}), (
        "el dueno del sobre es siempre `ticket.usuario_id`"
    )


def _estado_persistido(motor, ticket_id: int) -> int:
    """Estado del ticket leido en una sesion nueva, fuera de la del request."""
    with sessionmaker(bind=motor)() as db:
        return db.get(Ticket, ticket_id).estado_id


def _cuerpo_comparable(cuerpo: dict) -> dict:
    """Cuerpo sin los valores que dependen de la fila concreta.

    `ticket_id`, `fecha_creacion` y los ids de linea cambian entre dos siembras
    identicas; el resto del DTO debe ser igual con el bus sano y con el bus
    caido.
    """
    copia = dict(cuerpo)
    copia.pop("ticket_id", None)
    copia.pop("fecha_creacion", None)
    copia["detalles"] = [
        {clave: valor for clave, valor in detalle.items() if clave != "detalle_ticket_id"}
        for detalle in copia.get("detalles", [])
    ]
    return copia


# ---------------------------------------------------------------------------
# Tabla de mutaciones: una sola publicacion por mutacion confirmada
# ---------------------------------------------------------------------------


def test_alta_confirmada_publica_pedidos_con_motivo_alta(motor, mundo):
    """Anexo A fila 1 / AC-5: el alta confirmada anuncia `pedidos`."""
    datos = mundo

    with instalar_bus() as bus:
        with _cliente(motor, datos, "Solicitante") as cliente:
            respuesta = cliente.post(
                RUTA_ALTA,
                json=payload_alta(datos, datos["estados"]["EnRevision"]),
            )

    assert respuesta.status_code == 201, respuesta.text
    cuerpo = respuesta.json()
    _afirmar_sobre_de_pedidos(
        _sobre_unico(bus), motivo="alta", usuario_id=cuerpo["usuario_id"]
    )
    assert cuerpo["usuario_id"] == _dueno(datos)


def test_edicion_confirmada_publica_pedidos_con_motivo_edicion(motor, mundo):
    """Anexo A fila 2 / AC-5: la edicion anuncia `pedidos`."""
    datos = mundo
    ticket_id = sembrar_ticket(
        motor, datos, estado_id=datos["estados"]["EnRevision"]
    )
    payload = {
        "asunto": "Asunto editado para la 028",
        "descripcion": "Descripcion editada para la prueba de publicacion.",
        "prioridad_id": datos["prioridad_id"],
        "detalles": [
            {"producto_id": datos["producto_id"], "cantidad_solicitada": 2}
        ],
    }

    with instalar_bus() as bus:
        with _cliente(motor, datos, "Administrador") as cliente:
            respuesta = cliente.put(
                RUTA_EDICION.format(ticket_id=ticket_id), json=payload
            )

    assert respuesta.status_code == 200, respuesta.text
    _afirmar_sobre_de_pedidos(
        _sobre_unico(bus), motivo="edicion", usuario_id=_dueno(datos)
    )


def test_aprobacion_confirmada_publica_pedidos_con_motivo_aprobacion(motor, mundo):
    """Anexo A fila 3 / AC-5: la aprobacion anuncia `pedidos`."""
    datos = mundo
    ticket_id = sembrar_ticket(
        motor, datos, estado_id=datos["estados"]["EnRevision"]
    )

    with instalar_bus() as bus:
        with _cliente(motor, datos, "Administrador") as cliente:
            respuesta = cliente.post(RUTA_APROBACION.format(ticket_id=ticket_id))

    assert respuesta.status_code == 200, respuesta.text
    _afirmar_sobre_de_pedidos(
        _sobre_unico(bus), motivo="aprobacion", usuario_id=_dueno(datos)
    )


def test_confirmacion_de_entrega_publica_pedidos_con_su_motivo(motor, mundo):
    """Anexo A fila 5 / AC-5: la confirmacion de entrega anuncia `pedidos`."""
    datos = mundo
    ticket_id = sembrar_ticket(
        motor,
        datos,
        estado_id=datos["estados"]["Cerrado"],
        usuario_id=_dueno(datos),
    )

    with instalar_bus() as bus:
        with _cliente(motor, datos, "Solicitante") as cliente:
            respuesta = cliente.post(
                RUTA_CONFIRMACION.format(ticket_id=ticket_id)
            )

    assert respuesta.status_code == 200, respuesta.text
    _afirmar_sobre_de_pedidos(
        _sobre_unico(bus), motivo="confirmacion_entrega", usuario_id=_dueno(datos)
    )


def test_patch_estado_publica_pedidos_con_motivo_cambio_estado(motor, mundo):
    """Anexo A fila 9 / AC-5: el cambio de estado de legado anuncia `pedidos`."""
    datos = mundo
    ticket_id = sembrar_ticket(
        motor, datos, estado_id=datos["estados"]["EnRevision"]
    )

    with instalar_bus() as bus:
        with _cliente(motor, datos, "Administrador") as cliente:
            respuesta = cliente.patch(
                RUTA_ESTADO.format(ticket_id=ticket_id),
                json={"estado_id": datos["estados"]["EnCurso"]},
            )

    assert respuesta.status_code == 200, respuesta.text
    _afirmar_sobre_de_pedidos(
        _sobre_unico(bus), motivo="cambio_estado", usuario_id=_dueno(datos)
    )


def test_anulacion_desde_en_revision_publica_pedidos_con_motivo_anulacion(
    motor, mundo
):
    """Anexo A fila 6 / AC-5: la anulacion desde `EnRevision` anuncia `pedidos`."""
    datos = mundo
    ticket_id = sembrar_ticket(
        motor, datos, estado_id=datos["estados"]["EnRevision"]
    )

    with instalar_bus() as bus:
        with _cliente(motor, datos, "Administrador") as cliente:
            respuesta = cliente.post(
                RUTA_ANULACION.format(ticket_id=ticket_id),
                json={"motivo": "Anulacion de prueba de la 028"},
            )

    assert respuesta.status_code == 200, respuesta.text
    _afirmar_sobre_de_pedidos(
        _sobre_unico(bus), motivo="anulacion", usuario_id=_dueno(datos)
    )


def test_rechazo_publica_pedidos_con_motivo_rechazo(motor, mundo):
    """Anexo A fila 8 / AC-5: el rechazo anuncia `pedidos` y no duplica el sobre."""
    datos = mundo
    ticket_id = sembrar_ticket(
        motor, datos, estado_id=datos["estados"]["EnRevision"]
    )

    with instalar_bus() as bus:
        with _cliente(motor, datos, "Bodeguero") as cliente:
            respuesta = cliente.post(
                RUTA_RECHAZO.format(ticket_id=ticket_id),
                json={"motivo": "Rechazo de prueba de la 028"},
            )

    assert respuesta.status_code == 200, respuesta.text
    _afirmar_sobre_de_pedidos(
        _sobre_unico(bus), motivo="rechazo", usuario_id=_dueno(datos)
    )


# ---------------------------------------------------------------------------
# Despues del commit, nunca antes (D-8, AC-7)
# ---------------------------------------------------------------------------


def test_la_publicacion_ocurre_despues_del_commit(motor, mundo):
    """AC-7/D-8: al publicar, la transaccion de la mutacion ya confirmo."""
    datos = mundo
    ticket_id = sembrar_ticket(
        motor, datos, estado_id=datos["estados"]["EnRevision"]
    )
    commits: list[int] = []
    observado: dict[str, int] = {}

    def registrar_commit(_sesion: Session) -> None:
        commits.append(1)

    with instalar_bus() as bus:
        publicar_original = bus.publicar

        def publicar_observando(sobre) -> None:
            observado["commits_previos"] = len(commits)
            publicar_original(sobre)

        bus.publicar = publicar_observando
        event.listen(Session, "after_commit", registrar_commit)
        try:
            with _cliente(motor, datos, "Administrador") as cliente:
                respuesta = cliente.post(
                    RUTA_APROBACION.format(ticket_id=ticket_id)
                )
        finally:
            event.remove(Session, "after_commit", registrar_commit)

    assert respuesta.status_code == 200, respuesta.text
    assert len(bus.publicados) == 1
    assert observado["commits_previos"] >= 1, (
        "el sobre se publico antes de que la transaccion confirmara (D-8)"
    )
    assert _estado_persistido(motor, ticket_id) == datos["estados"]["EnCurso"], (
        "el bus ve el sobre cuando el ticket ya esta persistido en su estado nuevo"
    )


# ---------------------------------------------------------------------------
# Rechazos: ni 404, ni 409, ni 422, ni rollback publican (AC-7)
# ---------------------------------------------------------------------------


def test_un_404_no_publica(motor, mundo):
    """AC-7: un ticket inexistente responde 404 y no anuncia nada."""
    datos = mundo

    with instalar_bus() as bus:
        with _cliente(motor, datos, "Administrador") as cliente:
            respuesta = cliente.post(
                RUTA_ANULACION.format(ticket_id=999999),
                json={"motivo": "Anulacion de un ticket inexistente"},
            )

    assert respuesta.status_code == 404, respuesta.text
    assert bus.publicados == []


def test_un_409_de_patch_sin_cambio_no_publica(motor, mundo):
    """AC-7: `PATCH /estado` al mismo estado responde 409 y no publica."""
    datos = mundo
    ticket_id = sembrar_ticket(
        motor, datos, estado_id=datos["estados"]["EnRevision"]
    )

    with instalar_bus() as bus:
        with _cliente(motor, datos, "Administrador") as cliente:
            respuesta = cliente.patch(
                RUTA_ESTADO.format(ticket_id=ticket_id),
                json={"estado_id": datos["estados"]["EnRevision"]},
            )

    assert respuesta.status_code == 409, respuesta.text
    assert bus.publicados == []


def test_un_409_de_rechazo_desde_en_curso_no_publica(motor, mundo):
    """AC-7: el rechazo de un pedido ya aprobado responde 409 y no publica."""
    datos = mundo
    ticket_id = sembrar_ticket(
        motor, datos, estado_id=datos["estados"]["EnCurso"]
    )

    with instalar_bus() as bus:
        with _cliente(motor, datos, "Bodeguero") as cliente:
            respuesta = cliente.post(
                RUTA_RECHAZO.format(ticket_id=ticket_id),
                json={"motivo": "Rechazo de un pedido en curso"},
            )

    assert respuesta.status_code == 409, respuesta.text
    assert bus.publicados == []


def test_un_422_de_motivo_vacio_no_publica(motor, mundo):
    """AC-7: el motivo invalido responde 422 (tras 404/409) y no publica."""
    datos = mundo
    ticket_id = sembrar_ticket(
        motor, datos, estado_id=datos["estados"]["EnRevision"]
    )

    with instalar_bus() as bus:
        with _cliente(motor, datos, "Administrador") as cliente:
            respuesta = cliente.post(
                RUTA_ANULACION.format(ticket_id=ticket_id),
                json={"motivo": "   "},
            )

    assert respuesta.status_code == 422, respuesta.text
    assert bus.publicados == []


def test_un_rollback_forzado_no_publica(motor, mundo, monkeypatch):
    """AC-7: si la transaccion revierte, la mutacion no anuncia nada."""
    datos = mundo
    ticket_id = sembrar_ticket(
        motor, datos, estado_id=datos["estados"]["EnRevision"]
    )

    def fallar_antes_del_commit(*_args, **_kwargs):
        raise RuntimeError("fallo de base forzado por la prueba de rollback")

    # La fila del historial se escribe dentro de la transaccion de la mutacion;
    # hacerla fallar fuerza el `rollback()` del servicio, que ya mutó el estado.
    monkeypatch.setattr(ticket_service, "_registrar_transicion", fallar_antes_del_commit)

    with instalar_bus() as bus:
        with _cliente(motor, datos, "Administrador") as cliente:
            respuesta = cliente.post(RUTA_APROBACION.format(ticket_id=ticket_id))

    assert respuesta.status_code == 500, respuesta.text
    assert bus.publicados == []
    assert _estado_persistido(motor, ticket_id) == datos["estados"]["EnRevision"], (
        "el rollback debe devolver el ticket a su estado previo"
    )


# ---------------------------------------------------------------------------
# Fail-open: el bus caido no altera la respuesta (AC-8)
# ---------------------------------------------------------------------------


def test_el_bus_caido_no_cambia_el_status_ni_el_cuerpo(motor, mundo):
    """AC-8: la mutacion responde igual con el bus sano y con el bus caido."""
    datos = mundo
    ticket_sano = sembrar_ticket(
        motor, datos, estado_id=datos["estados"]["EnRevision"]
    )
    ticket_caido = sembrar_ticket(
        motor, datos, estado_id=datos["estados"]["EnRevision"]
    )

    with instalar_bus() as bus_sano:
        with _cliente(motor, datos, "Administrador") as cliente:
            respuesta_sana = cliente.post(
                RUTA_APROBACION.format(ticket_id=ticket_sano)
            )
    assert respuesta_sana.status_code == 200, respuesta_sana.text
    assert len(bus_sano.publicados) == 1

    with instalar_bus(
        error_al_publicar=RuntimeError("bus caido en la prueba de fail-open")
    ) as bus_caido:
        with _cliente(motor, datos, "Administrador") as cliente:
            respuesta_caida = cliente.post(
                RUTA_APROBACION.format(ticket_id=ticket_caido)
            )

    assert respuesta_caida.status_code == respuesta_sana.status_code
    assert _cuerpo_comparable(respuesta_caida.json()) == _cuerpo_comparable(
        respuesta_sana.json()
    ), "el cuerpo de la mutacion no depende del bus (fail-open)"
    assert bus_caido.publicados == []
    assert _estado_persistido(motor, ticket_caido) == datos["estados"]["EnCurso"]
