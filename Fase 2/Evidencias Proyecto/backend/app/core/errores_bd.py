"""Traduccion de errores de persistencia al contrato HTTP (Feature 027).

El cliente recibe un `detail` estable; el mensaje crudo del motor permanece solo
en el objeto de la excepcion y nunca se serializa ni se registra.
"""

import logging

from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.observabilidad import LOGGER_RAIZ

logger = logging.getLogger(LOGGER_RAIZ)


def _senal_error(error: Exception) -> str:
    """Devuelve el SQLSTATE de PostgreSQL o el texto normalizado de SQLite."""
    original = getattr(error, "orig", None)
    sqlstate = getattr(original, "pgcode", None)
    if not sqlstate:
        diagnostico = getattr(original, "diag", None)
        sqlstate = getattr(diagnostico, "sqlstate", None)
    if sqlstate:
        return str(sqlstate)
    return str(original).lower()


def clasificar_error_bd(error: Exception) -> tuple[int, str] | None:
    """Traduce una senal conocida de BD; lo desconocido sigue siendo un 500."""
    senal = _senal_error(error)
    respuestas_sqlstate = {
        "23505": (409, "El valor ya existe o entra en conflicto con un registro existente."),
        "23503": (422, "La referencia indicada no existe o no pertenece al ámbito de la operación."),
        "23514": (422, "Alguno de los valores enviados no cumple las reglas del recurso."),
        "23502": (422, "Falta un valor obligatorio."),
        "22001": (422, "Uno de los textos supera la longitud permitida."),
        "22003": (422, "Uno de los valores numéricos está fuera de rango."),
    }
    if senal in respuestas_sqlstate:
        return respuestas_sqlstate[senal]

    respuestas_sqlite = (
        ("unique constraint failed", (409, "El valor ya existe o entra en conflicto con un registro existente.")),
        ("foreign key constraint failed", (422, "La referencia indicada no existe o no pertenece al ámbito de la operación.")),
        ("check constraint failed", (422, "Alguno de los valores enviados no cumple las reglas del recurso.")),
        ("not null constraint failed", (422, "Falta un valor obligatorio.")),
        ("string or blob exceeds size limit", (422, "Uno de los textos supera la longitud permitida.")),
        ("numeric value out of range", (422, "Uno de los valores numéricos está fuera de rango.")),
    )
    for fragmento, respuesta in respuestas_sqlite:
        if fragmento in senal:
            return respuesta
    return None


def manejador_error_bd(request: Request, exc: Exception) -> JSONResponse:
    """Devuelve 409/422 sin filtrar el mensaje crudo del motor."""
    clasificacion = clasificar_error_bd(exc)
    if clasificacion is None:
        raise exc

    estado, detalle = clasificacion
    identificador = request.scope.get("state", {}).get("request_id")
    logger.error(
        "error de base de datos traducido",
        extra={
            "evento": "error_bd",
            "error_type": type(exc).__name__,
            "request_id": identificador,
        },
    )
    cabeceras = {"X-Request-ID": identificador} if identificador else None
    return JSONResponse(
        {"detail": detalle}, status_code=estado, headers=cabeceras
    )
