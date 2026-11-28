"""Publicacion de eventos de la Feature 028 desde los servicios de negocio.

Cada mutacion confirmada llama a una de las funciones de este modulo **despues
del commit**. El servicio construye el sobre interno (`institucion_id`,
`dominios`, `motivo` y dueños de pedidos) y lo entrega al almacen vigente. No
hay logica de negocio: los dominios y los dueños los decide la mutacion; la
unica consulta es la audiencia de los tickets de un plan de compras.

El contrato es **best-effort y fail-open** (AC-7/AC-8): `_publicar` envuelve
todo el camino (consulta de dueños, construccion del sobre y almacen) en un
`try/except` total. Un fallo deja un unico aviso `WARNING` acotado a uno cada
10 s, con `request_id` y `error_type`, y retorna sin cambiar la respuesta ni la
transaccion de la mutacion. La audiencia se resuelve antes de publicar, de modo
que un error de la consulta nunca deja un sobre a medias.

Con `TIEMPO_REAL_HABILITADO` apagado el canal no se usa: se retorna antes de
consultar la audiencia o tocar el almacen. La suite heredada lo deja apagado en
`conftest.py` y usa `AlmacenNulo` (plan §9.1).
"""

import logging
import time
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.eventos import LOGGER_BUS, SobreEvento, obtener_almacen
from app.core.observabilidad import identificador_actual
from app.models import Ticket

#: Un aviso de publicacion degradada como maximo cada 10 s, igual que el
#: patron de la 025 y del almacen Redis de T3.
INTERVALO_AVISO_SEGUNDOS = 10.0

#: Marca temporal monotona del ultimo aviso emitido. Se reinicia en las
#: pruebas para que un escenario de fallo no silencie el de la prueba siguiente.
_ultimo_aviso = float("-inf")


def publicar_pedidos(
    institucion_id: str,
    motivo: str,
    usuario_ids: Iterable[int],
) -> None:
    """Anuncia `pedidos` con los dueños que la mutacion ya conoce."""
    _publicar(
        institucion_id,
        motivo,
        {"pedidos"},
        usuario_ids=usuario_ids,
    )


def publicar_inventario(institucion_id: str, motivo: str) -> None:
    """Anuncia `inventario`; el stock no tiene un dueño por pedido."""
    _publicar(institucion_id, motivo, {"inventario"})


def publicar_pedidos_e_inventario(
    institucion_id: str,
    motivo: str,
    usuario_ids: Iterable[int],
) -> None:
    """Anuncia `pedidos` e `inventario` en **un** sobre (retiro y anulacion)."""
    _publicar(
        institucion_id,
        motivo,
        {"pedidos", "inventario"},
        usuario_ids=usuario_ids,
    )


def publicar_compras(
    institucion_id: str,
    motivo: str,
    *,
    db: Session | None = None,
    ticket_ids: Iterable[int] | None = None,
    con_inventario: bool = False,
) -> None:
    """Anuncia `compras` y, si toca pedidos o stock, sus dominios.

    Con `ticket_ids` se resuelven los dueños de esos pedidos en una sola
    consulta y, si hay alguno, se anade `pedidos`. `con_inventario` anade
    `inventario` (recepcion). Sin tickets y sin inventario, solo `compras`.
    """
    dominios = {"compras"}
    if con_inventario:
        dominios.add("inventario")
    _publicar(
        institucion_id,
        motivo,
        dominios,
        db=db,
        ticket_ids=ticket_ids,
    )


def _publicar(
    institucion_id: str,
    motivo: str,
    dominios: Iterable[str],
    *,
    usuario_ids: Iterable[int] = (),
    db: Session | None = None,
    ticket_ids: Iterable[int] | None = None,
) -> None:
    """Intenta publicar el sobre sin afectar nunca a la mutacion.

    El interruptor se consulta primero: con el canal apagado no se consulta la
    audiencia ni se toca el almacen. Dentro del `try` la audiencia se resuelve
    antes de construir y publicar el sobre, de modo que un fallo no deja un
    mensaje a medias. Cualquier excepcion (consulta, serializacion o almacen)
    se captura, se registra con el aviso acotado y no se propaga.
    """
    if not settings.TIEMPO_REAL_HABILITADO:
        return
    try:
        ids_tickets = tuple(ticket_ids or ())
        audiencia = set(usuario_ids or ())
        dominios_sobre = set(dominios)
        if ids_tickets:
            audiencia |= _audiencia_de_tickets(db, institucion_id, ids_tickets)
            if audiencia:
                dominios_sobre.add("pedidos")
        sobre = SobreEvento(
            institucion_id=institucion_id,
            dominios=frozenset(dominios_sobre),
            motivo=motivo,
            usuario_ids=frozenset(audiencia),
        )
        obtener_almacen().publicar(sobre)
    except Exception as error:  # noqa: BLE001 - fail-open por contrato
        _avisar(error)


def _audiencia_de_tickets(
    db: Session | None,
    institucion_id: str,
    ticket_ids: Iterable[int],
) -> set[int]:
    """Dueños de los tickets, en **una** consulta y sin duplicados.

    Filtra por `Ticket.institucion_id` (columna real del modelo, poblada por el
    alta desde la Feature 008) para que un id de otra institucion no amplie la
    audiencia. `DISTINCT` sobre `usuario_id` colapsa varios pedidos del mismo
    solicitante. Una sesion ausente con ids se rechaza con `ValueError`; el
    llamador (`_publicar`) la traga y avisa.
    """
    ids = {int(ticket_id) for ticket_id in ticket_ids}
    if not ids:
        return set()
    if db is None:
        raise ValueError("La audiencia de tickets necesita una sesion de base.")
    filas = db.execute(
        select(Ticket.usuario_id)
        .where(Ticket.ticket_id.in_(ids))
        .where(Ticket.institucion_id == institucion_id)
        .distinct()
    ).scalars()
    return set(filas)


def _avisar(error: Exception) -> None:
    """Avisa de la publicacion degradada como maximo una vez por intervalo.

    Sin IP, host, mensaje de la excepcion ni traza: solo `request_id` y el
    tipo de error, que son campos de la lista blanca de la 024.
    """
    global _ultimo_aviso
    ahora = time.monotonic()
    if ahora - _ultimo_aviso < INTERVALO_AVISO_SEGUNDOS:
        return
    _ultimo_aviso = ahora
    logging.getLogger(LOGGER_BUS).warning(
        "publicacion_evento_degradada",
        extra={
            "request_id": identificador_actual(),
            "error_type": type(error).__name__,
        },
    )
