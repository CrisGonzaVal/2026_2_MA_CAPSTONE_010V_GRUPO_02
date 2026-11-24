"""Feature 027, T5: errores de BD traducidos a un contrato HTTP estable.

Seam de esta primera rebanada: el clasificador publico `clasificar_error_bd`.
Las siguientes rebanadas cubren el handler HTTP y la correlacion observabilidad.
"""

import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy.exc import DataError, IntegrityError

from app.core.errores_bd import clasificar_error_bd
from app.main import app

from tests.funcional.integracion.soporte_observabilidad_024 import capturar_logs


def test_unicidad_sqlite_se_clasifica_como_409():
    error = IntegrityError(
        "INSERT INTO prueba",
        {},
        Exception("UNIQUE constraint failed: prueba.rut"),
    )

    assert clasificar_error_bd(error) == (
        409,
        "El valor ya existe o entra en conflicto con un registro existente.",
    )


@pytest.mark.parametrize(
    ("tipo_error", "original", "esperado"),
    [
        (
            IntegrityError,
            SimpleNamespace(pgcode="23505"),
            (409, "El valor ya existe o entra en conflicto con un registro existente."),
        ),
        (
            IntegrityError,
            SimpleNamespace(diag=SimpleNamespace(sqlstate="23505")),
            (409, "El valor ya existe o entra en conflicto con un registro existente."),
        ),
        (
            IntegrityError,
            Exception("FOREIGN KEY constraint failed"),
            (422, "La referencia indicada no existe o no pertenece al ámbito de la operación."),
        ),
        (
            IntegrityError,
            SimpleNamespace(pgcode="23503"),
            (422, "La referencia indicada no existe o no pertenece al ámbito de la operación."),
        ),
        (
            IntegrityError,
            Exception("CHECK constraint failed"),
            (422, "Alguno de los valores enviados no cumple las reglas del recurso."),
        ),
        (
            IntegrityError,
            SimpleNamespace(pgcode="23514"),
            (422, "Alguno de los valores enviados no cumple las reglas del recurso."),
        ),
        (
            IntegrityError,
            Exception("NOT NULL constraint failed"),
            (422, "Falta un valor obligatorio."),
        ),
        (
            IntegrityError,
            SimpleNamespace(pgcode="23502"),
            (422, "Falta un valor obligatorio."),
        ),
        (
            DataError,
            Exception("String or BLOB exceeds size limit"),
            (422, "Uno de los textos supera la longitud permitida."),
        ),
        (
            DataError,
            SimpleNamespace(pgcode="22001"),
            (422, "Uno de los textos supera la longitud permitida."),
        ),
        (
            DataError,
            Exception("Numeric value out of range"),
            (422, "Uno de los valores numéricos está fuera de rango."),
        ),
        (
            DataError,
            SimpleNamespace(pgcode="22003"),
            (422, "Uno de los valores numéricos está fuera de rango."),
        ),
    ],
)
def test_senales_conocidas_se_clasifican(tipo_error, original, esperado):
    error = tipo_error("OPERACION DE PRUEBA", {}, original)

    assert clasificar_error_bd(error) == esperado


def test_error_desconocido_no_se_traduce():
    error = IntegrityError(
        "INSERT INTO prueba",
        {},
        Exception("fallo interno con datos sensibles"),
    )

    assert clasificar_error_bd(error) is None


def _respuesta_error_bd(cliente, error: Exception, identificador: str):
    """Ejecuta una ruta temporal que lanza el error recibido."""
    ruta = "/_prueba-error-bd-027"

    async def fallar():
        raise error

    app.add_api_route(ruta, fallar, include_in_schema=False)
    try:
        return cliente.get(ruta, headers={"X-Request-ID": identificador})
    finally:
        app.router.routes = [
            existente
            for existente in app.router.routes
            if getattr(existente, "path", None) != ruta
        ]


def test_handler_http_devuelve_409_y_conserva_request_id(cliente_sin_excepcion):
    identificador = str(uuid4())
    error = IntegrityError(
        "INSERT INTO prueba",
        {},
        Exception("UNIQUE constraint failed: prueba.rut"),
    )

    respuesta = _respuesta_error_bd(cliente_sin_excepcion, error, identificador)

    assert respuesta.status_code == 409
    assert respuesta.json() == {
        "detail": "El valor ya existe o entra en conflicto con un registro existente."
    }
    assert respuesta.headers["x-request-id"] == identificador


def test_data_error_http_devuelve_422_sin_filtrar_el_mensaje_crudo(
    cliente_sin_excepcion,
):
    identificador = str(uuid4())
    mensaje_crudo = "String or BLOB exceeds size limit: valor-sensible"
    error = DataError("UPDATE prueba", {}, Exception(mensaje_crudo))

    respuesta = _respuesta_error_bd(cliente_sin_excepcion, error, identificador)

    assert respuesta.status_code == 422
    assert respuesta.json() == {
        "detail": "Uno de los textos supera la longitud permitida."
    }
    assert mensaje_crudo not in respuesta.text
    assert respuesta.headers["x-request-id"] == identificador


def test_log_de_error_bd_no_contiene_el_mensaje_crudo(cliente_sin_excepcion):
    identificador = str(uuid4())
    mensaje_crudo = "UNIQUE constraint failed: prueba.correo-sensible"
    error = IntegrityError("INSERT INTO prueba", {}, Exception(mensaje_crudo))

    with capturar_logs() as lineas:
        respuesta = _respuesta_error_bd(cliente_sin_excepcion, error, identificador)

    assert respuesta.status_code == 409
    assert mensaje_crudo not in "\n".join(lineas)
    evento = [
        json.loads(linea)
        for linea in lineas
        if json.loads(linea).get("evento") == "error_bd"
    ]
    assert len(evento) == 1
    assert evento[0]["error_type"] == "IntegrityError"
    assert evento[0]["request_id"] == identificador


def test_error_bd_desconocido_sigue_dando_500(cliente_sin_excepcion):
    identificador = str(uuid4())
    mensaje_crudo = "fallo interno con datos sensibles"
    error = IntegrityError("INSERT INTO prueba", {}, Exception(mensaje_crudo))

    with capturar_logs() as lineas:
        respuesta = _respuesta_error_bd(cliente_sin_excepcion, error, identificador)

    assert respuesta.status_code == 500
    assert respuesta.text == "Internal Server Error"
    assert respuesta.headers["x-request-id"] == identificador
    assert mensaje_crudo not in respuesta.text
    assert mensaje_crudo not in "\n".join(lineas)
