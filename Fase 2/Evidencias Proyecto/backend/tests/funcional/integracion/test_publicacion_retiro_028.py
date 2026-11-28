"""Publicacion de retiro y anulacion administrativa (Feature 028, T9).

Seam bajo prueba: la **interfaz HTTP** del `app` real (`TestClient`) con el
`BusFalso` de T4 instalado por `instalar_bus`, que enciende
`TIEMPO_REAL_HABILITADO` y guarda cada sobre publicado. Asi se comprueba el
efecto observable de la mutacion (status, cuerpo y sobre) sin tocar la capa de
servicios.

Tabla cubierta (spec §5.2 y Anexo A, filas 4 y 7):

| Mutacion | Motivo | Dominios | Dueno |
|---|---|---|---|
| `POST /tickets/{id}/retiro` | `retiro` | `pedidos`, `inventario` | `ticket.usuario_id` |
| `POST /tickets/{id}/anulacion` desde `Cerrado` | `anulacion` | `pedidos`, `inventario` | `ticket.usuario_id` |

Reglas verificadas ademas de la tabla: publicacion **posterior al commit**,
**un solo sobre** por mutacion confirmada (no dos mensajes), silencio en los
409 (retiro sin stock y anulacion de un pedido ya confirmado) y ausencia de
identificadores en el frame que el suscriptor (T6) construye desde el sobre.

La rama `EnRevision` de la anulacion sigue publicando solo `pedidos` (T8) y no
se repite aqui; tampoco se repiten las mutaciones de alta, edicion, aprobacion,
confirmacion, rechazo ni `PATCH`.
"""

from __future__ import annotations

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session, sessionmaker

from app.api.dependencies import ContextoTiempoReal
from app.api.v1.endpoints.eventos import (
    _dominios_visibles_del_sobre,
    _frame,
)
from app.models import Ticket

from tests.funcional.integracion._soporte_eventos_028 import instalar_bus
from tests.funcional.integracion._soporte_retiro_013 import (
    FECHA_CIERRE,
    anular,
    cliente_rol,
    marcar_confirmado,
    retirar,
    sembrar_mundo_retiro,
    sembrar_ticket_retiro,
)

#: Institucion de la semilla (`datos_base`/`dos_instituciones`).
INSTITUCION = "INST01"

#: Motivo literal de la anulacion administrativa del retiro (013 D-32).
MOTIVO_ANULACION = "Retiro registrado por error en la bodega"


# ---------------------------------------------------------------------------
# Mundo y observacion de la publicacion
# ---------------------------------------------------------------------------


@pytest.fixture
def mundo(motor, dos_instituciones):
    """Catalogo de cuatro estados, sede del Bodeguero y 50 unidades de stock."""
    return sembrar_mundo_retiro(motor, dos_instituciones)


def _sobre_unico(bus):
    """Un unico sobre publicado; falla con el conteo real si hubo cero o varios."""
    assert len(bus.publicados) == 1, (
        "se esperaba exactamente un sobre publicado por la mutacion; "
        f"hubo {len(bus.publicados)}: {bus.publicados!r}"
    )
    return bus.publicados[0]


def _afirmar_sobre_de_pedidos_e_inventario(
    sobre, *, motivo: str, usuario_id: int
) -> None:
    """Contrato del sobre de T9: los dos dominios, el motivo y el dueno."""
    assert sobre.dominios == frozenset({"pedidos", "inventario"}), (
        "el retiro y la anulacion administrativa anuncian `pedidos` e "
        f"`inventario`; llego {sorted(sobre.dominios)}"
    )
    assert sobre.motivo == motivo
    assert sobre.institucion_id == INSTITUCION
    assert sobre.usuario_ids == frozenset({usuario_id}), (
        "el dueno del sobre es siempre `ticket.usuario_id`"
    )


def _retirar(cliente, ticket_id: int, datos: dict):
    """Retiro con el actor minimo que exige el DTO de la 013."""
    return retirar(
        cliente,
        ticket_id,
        {"usuario_id": datos["usuarios_inst01"]["Bodeguero"]},
    )


# ---------------------------------------------------------------------------
# Tabla de mutaciones: una sola publicacion con los dos dominios
# ---------------------------------------------------------------------------


def test_retiro_confirmado_publica_pedidos_e_inventario_con_motivo_retiro(
    motor, mundo
):
    """Anexo A fila 4 / AC-5: el retiro confirmado anuncia `pedidos`+`inventario`."""
    datos = mundo
    ticket_id = sembrar_ticket_retiro(motor, datos, estado="EnCurso")

    with instalar_bus() as bus:
        with cliente_rol(motor, datos, "Bodeguero") as cliente:
            respuesta = _retirar(cliente, ticket_id, datos)

    assert respuesta.status_code == 200, respuesta.text
    _afirmar_sobre_de_pedidos_e_inventario(
        _sobre_unico(bus),
        motivo="retiro",
        usuario_id=datos["usuarios_inst01"]["Solicitante"],
    )


def test_anulacion_desde_cerrado_publica_pedidos_e_inventario_con_motivo_anulacion(
    motor, mundo
):
    """Anexo A fila 7 / AC-5: la anulacion administrativa anuncia ambos dominios."""
    datos = mundo
    ticket_id = sembrar_ticket_retiro(
        motor,
        datos,
        estado="Cerrado",
        detalles=[(datos["producto_id"], 3, 3)],
        fecha_cierre=FECHA_CIERRE,
    )

    with instalar_bus() as bus:
        with cliente_rol(motor, datos, "Administrador") as cliente:
            respuesta = anular(cliente, ticket_id, MOTIVO_ANULACION)

    assert respuesta.status_code == 200, respuesta.text
    _afirmar_sobre_de_pedidos_e_inventario(
        _sobre_unico(bus),
        motivo="anulacion",
        usuario_id=datos["usuarios_inst01"]["Solicitante"],
    )


# ---------------------------------------------------------------------------
# Un solo sobre y ningun id en el frame futuro
# ---------------------------------------------------------------------------


def test_el_retiro_publica_un_solo_sobre_y_el_frame_no_lleva_ids(motor, mundo):
    """AC-7/AC-18: un mensaje (no dos) y el frame solo lleva dominios y motivo."""
    datos = mundo
    dueno = datos["usuarios_inst01"]["Solicitante"]
    ticket_id = sembrar_ticket_retiro(motor, datos, estado="EnCurso")

    with instalar_bus() as bus:
        with cliente_rol(motor, datos, "Bodeguero") as cliente:
            respuesta = _retirar(cliente, ticket_id, datos)

    assert respuesta.status_code == 200, respuesta.text
    sobre = _sobre_unico(bus)
    assert len(bus.publicados) == 1, (
        "el retiro no puede emitir dos mensajes: un unico sobre con el conjunto "
        f"de dominios; hubo {bus.publicados!r}"
    )

    # El suscriptor de T6 construye el frame desde la copia de contexto de la
    # conexion; nunca serializa el sobre ni sus ids de enrutamiento.
    contexto = ContextoTiempoReal(
        usuario_id=dueno,
        rol="Solicitante",
        institucion_id=INSTITUCION,
        expira_en=None,
        dominios_visibles=frozenset({"pedidos", "inventario", "dashboard"}),
        request_id=None,
    )
    filtrado = _dominios_visibles_del_sobre(contexto, sobre)
    assert filtrado == (["pedidos", "inventario"], "retiro")
    dominios, motivo = filtrado
    cuerpo = _frame("cambio", {"dominios": dominios, "motivo": motivo})

    for prohibido in (
        '"institucion_id"',
        '"usuario_id"',
        '"usuario_ids"',
        '"ticket_id"',
        INSTITUCION,
        f'"{dueno}"',
    ):
        assert prohibido not in cuerpo, prohibido


# ---------------------------------------------------------------------------
# Despues del commit, nunca antes (D-8, AC-7)
# ---------------------------------------------------------------------------


def test_la_publicacion_del_retiro_ocurre_despues_del_commit(motor, mundo):
    """AC-7/D-8: al publicar, la transaccion del retiro ya confirmo."""
    datos = mundo
    ticket_id = sembrar_ticket_retiro(motor, datos, estado="EnCurso")
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
            with cliente_rol(motor, datos, "Bodeguero") as cliente:
                respuesta = _retirar(cliente, ticket_id, datos)
        finally:
            event.remove(Session, "after_commit", registrar_commit)

    assert respuesta.status_code == 200, respuesta.text
    assert len(bus.publicados) == 1
    assert observado["commits_previos"] >= 1, (
        "el sobre se publico antes de que la transaccion del retiro confirmara "
        "(D-8)"
    )
    with sessionmaker(bind=motor)() as db:
        assert db.get(Ticket, ticket_id).estado_id == datos["estados"]["Cerrado"], (
            "el bus ve el sobre cuando el retiro ya esta persistido"
        )


# ---------------------------------------------------------------------------
# Rechazos: los 409 no publican (AC-7)
# ---------------------------------------------------------------------------


def test_un_retiro_sin_stock_suficiente_no_publica(motor, mundo):
    """AC-7: el retiro con stock insuficiente responde 409 y no anuncia nada."""
    datos = mundo
    ticket_id = sembrar_ticket_retiro(
        motor,
        datos,
        estado="EnCurso",
        detalles=[(datos["producto_id"], 500, 0)],
    )

    with instalar_bus() as bus:
        with cliente_rol(motor, datos, "Bodeguero") as cliente:
            respuesta = _retirar(cliente, ticket_id, datos)

    assert respuesta.status_code == 409, respuesta.text
    assert bus.publicados == []


def test_la_anulacion_de_un_confirmado_no_publica(motor, mundo):
    """AC-7: anular un retiro ya confirmado responde 409 y no anuncia nada."""
    datos = mundo
    ticket_id = sembrar_ticket_retiro(
        motor,
        datos,
        estado="Cerrado",
        detalles=[(datos["producto_id"], 3, 3)],
        fecha_cierre=FECHA_CIERRE,
    )
    marcar_confirmado(motor, datos, ticket_id)

    with instalar_bus() as bus:
        with cliente_rol(motor, datos, "Administrador") as cliente:
            respuesta = anular(cliente, ticket_id, MOTIVO_ANULACION)

    assert respuesta.status_code == 409, respuesta.text
    assert bus.publicados == []
