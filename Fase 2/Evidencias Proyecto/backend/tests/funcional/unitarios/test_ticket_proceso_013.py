"""Pruebas unitarias de la etiqueta de proceso y del read model (Feature 013).

Ampliacion del 25/Nov/2026, spec §9.8. Cubren:

- **AC-37**: etiqueta y frase de `Pendiente`, `EnRevision`, `Anulado` y
  `Cerrado` (con y sin confirmacion de entrega), y degradacion de un estado
  fuera del conjunto canonico sin lanzar excepcion.
- **AC-38**: en `EnCurso`, la OC activa mas avanzada que cubre el pedido decide
  la etiqueta con la escala `Recibida` > `Facturada` > `Emitida`; una OC
  `Cancelada` (o `None`) no cuenta y el stock solo decide sin cobertura.
- **AC-39**: el contrato aditivo de `TicketRespuesta`/`TicketDetalleRespuesta`
  y `GestorProcesoRespuesta`.

Son pruebas puras: sin base de datos, sin sesion y sin fixtures. Las frases
esperadas son literales de la spec, no constantes del modulo bajo prueba.
"""

from datetime import datetime

import pytest

from app.schemas.ticket_schema import (
    GestorProcesoRespuesta,
    TicketDetalleRespuesta,
    TicketRespuesta,
)
from app.services.ticket_proceso import derivar_etiqueta, rango_estado_orden

#: Frases cortas literales de la spec §9.8 (fuente independiente del modulo).
FRASE_EN_APROBACION = (
    "En aprobación: pendiente de revisión por Bodega o Administración."
)
FRASE_EN_REVISION = (
    "En revisión: estado heredado; se aprueba con la acción Aprobar."
)
FRASE_EN_COMPRA = (
    "En compra: la orden está emitida y pendiente de facturación."
)
FRASE_FACTURADO = (
    "Facturado: la compra está facturada y pendiente de recepción."
)
FRASE_EN_CONFIRMACION_STOCK = (
    "En confirmación de stock local: el stock local está disponible; falta que "
    "el Bodeguero lo confirme y despache."
)
FRASE_POR_COMPRAR = "Por comprar: no hay stock suficiente ni compra vigente."
FRASE_DESPACHADO = "Despachado: pendiente de confirmación de entrega."
FRASE_ENTREGADO = "Entregado: confirmado por el solicitante."
FRASE_RECHAZADO = "Rechazado: el pedido no se despachará."
FRASE_DESCONOCIDO = "Estado no reconocido por la etiqueta de proceso"


def _derivar(
    estado_canonico,
    *,
    stock_disponible=False,
    estado_orden_cobertura=None,
    entrega_confirmada=False,
):
    """Invoca `derivar_etiqueta` con argumentos nombrados (orden explicito)."""
    return derivar_etiqueta(
        estado_canonico,
        stock_disponible=stock_disponible,
        estado_orden_cobertura=estado_orden_cobertura,
        entrega_confirmada=entrega_confirmada,
    )


# ---------------------------------------------------------------------------
# AC-37 — etiqueta y frase por estado canonico
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("estado", "entrega_confirmada", "etiqueta", "frase"),
    [
        ("Pendiente", False, "En aprobación", FRASE_EN_APROBACION),
        ("EnRevision", False, "En revisión", FRASE_EN_REVISION),
        ("Anulado", False, "Rechazado", FRASE_RECHAZADO),
        ("Cerrado", False, "Despachado", FRASE_DESPACHADO),
        ("Cerrado", True, "Entregado", FRASE_ENTREGADO),
    ],
)
def test_ac_37_etiqueta_y_frase_de_los_estados_fuera_de_encurso(
    estado, entrega_confirmada, etiqueta, frase
):
    assert _derivar(estado, entrega_confirmada=entrega_confirmada) == (
        etiqueta,
        frase,
    )


def test_ac_37_estado_desconocido_degrada_a_su_nombre_sin_lanzar():
    etiqueta, frase = _derivar(
        "Archivado",
        stock_disponible=True,
        estado_orden_cobertura="Recibida",
        entrega_confirmada=True,
    )

    assert (etiqueta, frase) == ("Archivado", FRASE_DESCONOCIDO)


# ---------------------------------------------------------------------------
# AC-38 — precedencia de la OC activa sobre el stock en EnCurso
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("estado_orden", "etiqueta", "frase"),
    [
        ("Recibida", "En confirmación de stock local", FRASE_EN_CONFIRMACION_STOCK),
        ("Facturada", "Facturado", FRASE_FACTURADO),
        ("Emitida", "En compra", FRASE_EN_COMPRA),
    ],
)
def test_ac_38_encurso_usa_la_etiqueta_de_la_oc_activa(
    estado_orden, etiqueta, frase
):
    assert _derivar("EnCurso", estado_orden_cobertura=estado_orden) == (
        etiqueta,
        frase,
    )


def test_ac_38_precedencia_recibida_sobre_facturada_y_emitida_simultaneas():
    estados = ["Emitida", "Cancelada", "Facturada", "Recibida"]

    mas_avanzada = max(estados, key=rango_estado_orden)

    assert mas_avanzada == "Recibida"
    assert _derivar("EnCurso", estado_orden_cobertura=mas_avanzada) == (
        "En confirmación de stock local",
        FRASE_EN_CONFIRMACION_STOCK,
    )


def test_ac_38_rango_estado_orden_escala_recibida_facturada_emitida():
    assert rango_estado_orden("Recibida") > rango_estado_orden("Facturada")
    assert rango_estado_orden("Facturada") > rango_estado_orden("Emitida")
    assert rango_estado_orden("Emitida") > rango_estado_orden("Cancelada")


def test_ac_38_cancelada_y_none_no_cuentan_como_cobertura():
    assert rango_estado_orden("Cancelada") == rango_estado_orden(None) == 0

    assert _derivar(
        "EnCurso",
        stock_disponible=True,
        estado_orden_cobertura="Cancelada",
    ) == ("En confirmación de stock local", FRASE_EN_CONFIRMACION_STOCK)


@pytest.mark.parametrize("estado_orden", ["Emitida", "Facturada", "Recibida"])
def test_ac_38_la_oc_activa_prevalece_sobre_el_stock(estado_orden):
    con_stock = _derivar(
        "EnCurso",
        stock_disponible=True,
        estado_orden_cobertura=estado_orden,
    )
    sin_stock = _derivar(
        "EnCurso",
        stock_disponible=False,
        estado_orden_cobertura=estado_orden,
    )

    assert con_stock == sin_stock


def test_ac_38_encurso_con_stock_y_sin_oc_espera_confirmacion_local():
    assert _derivar("EnCurso", stock_disponible=True) == (
        "En confirmación de stock local",
        FRASE_EN_CONFIRMACION_STOCK,
    )


def test_ac_38_encurso_sin_stock_ni_oc_queda_por_comprar():
    assert _derivar("EnCurso", stock_disponible=False) == (
        "Por comprar",
        FRASE_POR_COMPRAR,
    )


# ---------------------------------------------------------------------------
# AC-39 — contrato aditivo de los DTO del read model
# ---------------------------------------------------------------------------


def test_ac_39_gestor_proceso_respuesta_expone_id_nombre_y_apellido():
    gestor = GestorProcesoRespuesta(
        usuario_id=7, nombre="Ana", apellido="Pérez"
    )

    assert (gestor.usuario_id, gestor.nombre, gestor.apellido) == (
        7,
        "Ana",
        "Pérez",
    )
    assert set(GestorProcesoRespuesta.model_fields) == {
        "usuario_id",
        "nombre",
        "apellido",
    }


def test_ac_39_ticket_respuesta_conserva_defaults_sin_los_campos_nuevos():
    ticket = TicketRespuesta(
        ticket_id=1,
        usuario_id=2,
        prioridad_id=3,
        estado_id=4,
        asunto="Pedido de insumos",
        fecha_creacion=datetime(2026, 1, 1, 12, 0, 0),
    )

    assert ticket.etiqueta_proceso == ""
    assert ticket.explicacion_proceso == ""
    assert ticket.estado_orden_cobertura is None
    assert ticket.stock_disponible is False
    assert ticket.entrega_confirmada is False
    assert ticket.gestionado_por_bodeguero is None
    assert ticket.gestionado_por_administrador is None


def test_ac_39_ticket_respuesta_declara_los_campos_del_read_model():
    assert {
        "etiqueta_proceso",
        "explicacion_proceso",
        "estado_orden_cobertura",
        "stock_disponible",
        "entrega_confirmada",
        "gestionado_por_bodeguero",
        "gestionado_por_administrador",
    } <= set(TicketRespuesta.model_fields)


def test_ac_39_ticket_respuesta_acepta_los_valores_derivados():
    ticket = TicketRespuesta(
        ticket_id=1,
        usuario_id=2,
        prioridad_id=3,
        estado_id=4,
        asunto="Pedido de insumos",
        fecha_creacion=datetime(2026, 1, 1, 12, 0, 0),
        etiqueta_proceso="En confirmación de stock local",
        explicacion_proceso=FRASE_EN_CONFIRMACION_STOCK,
        estado_orden_cobertura="Recibida",
        stock_disponible=True,
        entrega_confirmada=False,
        gestionado_por_bodeguero=GestorProcesoRespuesta(
            usuario_id=5, nombre="Beto", apellido="Bodega"
        ),
        gestionado_por_administrador=None,
    )

    assert ticket.etiqueta_proceso == "En confirmación de stock local"
    assert ticket.estado_orden_cobertura == "Recibida"
    assert ticket.stock_disponible is True
    assert ticket.gestionado_por_bodeguero.nombre == "Beto"
    assert ticket.gestionado_por_administrador is None


def test_ac_39_ticket_detalle_hereda_stock_disponible_y_agrega_la_entrega():
    # `stock_disponible` vive en la base y el detalle lo hereda: no se declara
    # dos veces (la anotacion propia del detalle no lo repite).
    assert "stock_disponible" in TicketRespuesta.model_fields
    assert "stock_disponible" in TicketDetalleRespuesta.model_fields
    assert "stock_disponible" not in TicketDetalleRespuesta.__annotations__

    detalle = TicketDetalleRespuesta(
        ticket_id=1,
        usuario_id=2,
        prioridad_id=3,
        estado_id=4,
        asunto="Pedido de insumos",
        fecha_creacion=datetime(2026, 1, 1, 12, 0, 0),
        stock_disponible=True,
        entrega_confirmada_en=datetime(2026, 1, 2, 9, 30, 0),
        entrega_confirmada_por_nombre="Sofía",
        entrega_confirmada_por_apellido="Solicitante",
    )

    assert detalle.stock_disponible is True
    assert detalle.entrega_confirmada_en == datetime(2026, 1, 2, 9, 30, 0)
    assert detalle.entrega_confirmada_por_nombre == "Sofía"
    assert detalle.entrega_confirmada_por_apellido == "Solicitante"


def test_ac_39_ticket_detalle_deja_nulos_los_campos_de_entrega_por_defecto():
    detalle = TicketDetalleRespuesta(
        ticket_id=1,
        usuario_id=2,
        prioridad_id=3,
        estado_id=4,
        asunto="Pedido de insumos",
        fecha_creacion=datetime(2026, 1, 1, 12, 0, 0),
    )

    assert detalle.entrega_confirmada_en is None
    assert detalle.entrega_confirmada_por_nombre is None
    assert detalle.entrega_confirmada_por_apellido is None
