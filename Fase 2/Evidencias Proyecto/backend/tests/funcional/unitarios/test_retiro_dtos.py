"""Feature 005 (T1) y enmienda 013: contrato del DTO de retiro e historial.

El seam observable es el propio modelo Pydantic: se valida aqui que el payload
exige un `usuario_id` entero y que el read model del historial expone todos
los campos de `spec.md` §5.

El DTO del historial se declara como read model de consulta (sin
`from_attributes`) porque lo arma `inventario_service` a partir de un mapping
que cruza cuatro tablas (plan §3.4); eso tambien se comprueba.
"""

from datetime import datetime

import pytest
from pydantic import ValidationError

from app.schemas.inventario_schema import MovimientoInventarioRespuesta
from app.schemas.ticket_schema import TicketRetiro

#: Campos exigidos por el contrato de `GET /inventario/movimientos` (§5).
CAMPOS_HISTORIAL = {
    "movimiento_id",
    "tipo_movimiento",
    "cantidad",
    "fecha_movimiento",
    "observacion",
    "stock_sede_id",
    "producto_id",
    "producto_nombre",
    "sede_id",
    "sede_nombre",
    # Feature 008 (AC-8): atribucion institucional del movimiento.
    "institucion_id",
}


def test_ticket_retiro_acepta_usuario_id_entero():
    payload = TicketRetiro.model_validate({"usuario_id": 6})
    assert payload.usuario_id == 6
    assert isinstance(payload.usuario_id, int)


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"usuario_id": None},
        {"usuario_id": "no-es-entero"},
    ],
)
def test_ticket_retiro_rechaza_usuario_id_ausente_o_no_entero(payload):
    with pytest.raises(ValidationError):
        TicketRetiro.model_validate(payload)


def test_movimiento_inventario_respuesta_expone_todos_los_campos_del_contrato():
    assert set(MovimientoInventarioRespuesta.model_fields) == CAMPOS_HISTORIAL


def test_movimiento_inventario_respuesta_es_read_model_de_consulta():
    # No es una entidad ORM: el service lo arma desde un mapping de columnas.
    assert MovimientoInventarioRespuesta.model_config.get("from_attributes") is not True


def test_movimiento_inventario_respuesta_instancia_todos_los_campos():
    movimiento = MovimientoInventarioRespuesta(
        movimiento_id=1,
        tipo_movimiento="SALIDA",
        cantidad=3,
        fecha_movimiento=datetime(2026, 1, 1, 12, 0, 0),
        observacion="Salida por retiro del ticket #1; detalle_id=2; producto_id=5",
        stock_sede_id=4,
        producto_id=5,
        producto_nombre="Resma de papel",
        sede_id=2,
        sede_nombre="Bodega",
    )
    assert movimiento.producto_nombre == "Resma de papel"
    assert movimiento.sede_nombre == "Bodega"
    assert movimiento.cantidad == 3
