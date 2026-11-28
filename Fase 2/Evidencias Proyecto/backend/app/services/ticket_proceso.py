"""Derivacion pura de la etiqueta de proceso del ticket (Feature 013, §9.8).

La etiqueta de proceso es de solo lectura: no es un estado canonico, no se
persiste y no altera la maquina de estados, Compras, la orden de compra ni el
stock (spec D-21/D-22). Este modulo no importa modelos ni SQLAlchemy: recibe
los datos ya resueltos por `ticket_service` y devuelve `(etiqueta, frase)`.

Precedencia en `EnCurso` (AC-38): OC `Recibida` > OC `Facturada` >
OC `Emitida` > `stock_disponible` > sin cobertura. Una OC `Cancelada` (o un
estado de OC desconocido) no cuenta como activa.
"""

from typing import Optional, Tuple

#: Motivos literales que el historial usa para distinguir los eventos de la
#: ampliacion (spec D-16/D-25). Los consumen la aprobacion y la confirmacion de
#: entrega en `ticket_service`.
MOTIVO_APROBACION = "Aprobación del pedido"
MOTIVO_CONFIRMACION_ENTREGA = "Entrega confirmada por el solicitante"

#: Etiquetas canonicas de proceso (spec D-22; enmienda 26/Nov/2026 D-37).
#: No son estados canonicos.
ETIQUETA_EN_REVISION = "En revisión"
ETIQUETA_RECHAZADO = "Rechazado"
ETIQUETA_RETIRADO = "Retirado"
ETIQUETA_ENTREGADO = "Entregado"
ETIQUETA_EN_CONFIRMACION_STOCK = "En confirmación de stock local"
ETIQUETA_FACTURADO = "Facturado"
ETIQUETA_EN_COMPRA = "En compra"
ETIQUETA_POR_COMPRAR = "Por comprar"

#: Frases cortas de `explicacion_proceso` (spec §9.8; enmienda 26/Nov/2026).
EXPLICACION_EN_REVISION = (
    "En revisión: estado inicial; se aprueba con la acción Aprobar."
)
EXPLICACION_EN_COMPRA = (
    "En compra: la orden está emitida y pendiente de facturación."
)
EXPLICACION_FACTURADO = (
    "Facturado: la compra está facturada y pendiente de recepción."
)
EXPLICACION_EN_CONFIRMACION_STOCK = (
    "En confirmación de stock local: el stock local está disponible; falta que "
    "el Bodeguero lo confirme y retire."
)
EXPLICACION_POR_COMPRAR = "Por comprar: no hay stock suficiente ni compra vigente."
EXPLICACION_RETIRADO = "Retirado: pendiente de confirmación de entrega."
EXPLICACION_ENTREGADO = "Entregado: confirmado por el solicitante."
EXPLICACION_RECHAZADO = "Rechazado: el pedido no se retirará."
EXPLICACION_ESTADO_DESCONOCIDO = "Estado no reconocido por la etiqueta de proceso"

#: Rango de avance de la OC activa que cubre el pedido (AC-38). La escala es
#: `Recibida` > `Facturada` > `Emitida`; `Cancelada` y `None` no cuentan.
_RANGO_POR_ESTADO_ORDEN = {
    "emitida": 1,
    "facturada": 2,
    "recibida": 3,
}

#: Rango de un pedido sin cobertura activa (sin OC, `Cancelada` o desconocida).
RANGO_SIN_COBERTURA = 0


def rango_estado_orden(estado: Optional[str]) -> int:
    """Rango de avance de una OC: 3 `Recibida`, 2 `Facturada`, 1 `Emitida`.

    `Cancelada`, `None` y cualquier estado desconocido devuelven 0: no cuentan
    como cobertura activa. La comparacion no distingue mayusculas ni espacios
    exteriores, para no depender del formato con que llegue el nombre.
    """
    if not estado:
        return RANGO_SIN_COBERTURA
    return _RANGO_POR_ESTADO_ORDEN.get(estado.strip().casefold(), RANGO_SIN_COBERTURA)


def derivar_etiqueta(
    estado_canonico: Optional[str],
    stock_disponible: bool,
    estado_orden_cobertura: Optional[str],
    entrega_confirmada: bool,
) -> Tuple[str, str]:
    """Deriva `(etiqueta_proceso, explicacion_proceso)` de un pedido.

    Implementa la precedencia exacta de la spec D-22 (AC-37/AC-38) con la
    enmienda 26/Nov/2026 (D-37):

    - `EnRevision` y `Anulado` tienen etiqueta propia; `Pendiente` ya no existe.
    - `Cerrado` distingue `Retirado` de `Entregado` por `entrega_confirmada`.
    - `EnCurso` se decide por la OC activa mas avanzada que cubre el pedido:
      `Recibida` > `Facturada` > `Emitida`; sin cobertura activa decide
      `stock_disponible` y, si no hay, `Por comprar`.
    - Un estado fuera del conjunto canonico no lanza: devuelve su nombre
      visible con la explicacion de degradacion.
    """
    nombre_visible = (estado_canonico or "").strip()
    clave = nombre_visible.casefold()

    if clave == "enrevision":
        return ETIQUETA_EN_REVISION, EXPLICACION_EN_REVISION
    if clave == "anulado":
        return ETIQUETA_RECHAZADO, EXPLICACION_RECHAZADO
    if clave == "cerrado":
        if entrega_confirmada:
            return ETIQUETA_ENTREGADO, EXPLICACION_ENTREGADO
        return ETIQUETA_RETIRADO, EXPLICACION_RETIRADO
    if clave == "encurso":
        rango = rango_estado_orden(estado_orden_cobertura)
        if rango >= 3:
            return ETIQUETA_EN_CONFIRMACION_STOCK, EXPLICACION_EN_CONFIRMACION_STOCK
        if rango == 2:
            return ETIQUETA_FACTURADO, EXPLICACION_FACTURADO
        if rango == 1:
            return ETIQUETA_EN_COMPRA, EXPLICACION_EN_COMPRA
        if stock_disponible:
            return ETIQUETA_EN_CONFIRMACION_STOCK, EXPLICACION_EN_CONFIRMACION_STOCK
        return ETIQUETA_POR_COMPRAR, EXPLICACION_POR_COMPRAR
    return nombre_visible, EXPLICACION_ESTADO_DESCONOCIDO
