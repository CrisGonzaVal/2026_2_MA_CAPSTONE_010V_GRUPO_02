"""Infraestructura de observabilidad de la Feature 024.

Concentra lo que comparten el middleware de correlacion y los endpoints
operativos: el identificador de peticion en un `ContextVar`, la validacion del
UUID canonico, los resolutores de formato y nivel, y los formateadores JSON y
texto del logger `compustock`.

El logging usa solo la biblioteca estandar. Nunca se registran cabeceras,
cuerpos, query string, correos, tokens, usuarios, instituciones ni tenants: la
lista blanca `CAMPOS_ADICIONALES` es la unica puerta de entrada de datos
estructurados al JSON.
"""

import json
import logging
import re
import sys
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings

LOGGER_RAIZ = "compustock"
LOGGER_ACCESO = "compustock.acceso"
LOGGER_SALUD = "compustock.salud"
LOGGER_LIMITE = "compustock.limite"

#: UUID canonico con guiones (8-4-4-4-12). Se valida con regex y no con
#: `uuid.UUID` porque el constructor acepta formas sin guiones que la spec
#: excluye; el identificador valido se devuelve **identico**, mayusculas
#: incluidas.
UUID_CANONICO = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

#: Identificador de la peticion en curso. El middleware lo fija al entrar y lo
#: resetea en `finally`, de modo que no se filtre entre peticiones.
IDENTIFICADOR_PETICION: ContextVar[str | None] = ContextVar(
    "identificador_peticion", default=None
)

#: Campos estructurados admitidos en el JSON. Cualquier `extra` fuera de esta
#: lista se descarta: es la garantia de que no se cuela PII por accidente.
CAMPOS_ADICIONALES = (
    "request_id",
    "method",
    "path",
    "status",
    "duration_ms",
    "evento",
    "error_type",
)

_NIVELES = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}

_MARCA_HANDLER = "_compustock_handler"


def resolver_identificador(cabecera: str | None) -> str:
    """Devuelve la cabecera si es un UUID canonico; si no, un UUID4 nuevo."""
    if cabecera and UUID_CANONICO.fullmatch(cabecera):
        return cabecera
    return str(uuid.uuid4())


def identificador_actual() -> str | None:
    """Identificador de la peticion en curso, o `None` fuera de una peticion."""
    return IDENTIFICADOR_PETICION.get()


def resolver_formato(valor: str | None) -> str:
    """`text` (sin distinguir mayusculas) o `json` por defecto."""
    if valor and valor.strip().lower() == "text":
        return "text"
    return "json"


def resolver_nivel(valor: str | None) -> int:
    """Nivel de logging por nombre; un valor desconocido cae a `INFO`."""
    if not valor:
        return logging.INFO
    return _NIVELES.get(valor.strip().upper(), logging.INFO)


def nivel_de_estado(status: int) -> int:
    """ERROR para 5xx, WARNING para 4xx, INFO para el resto."""
    if status >= 500:
        return logging.ERROR
    if status >= 400:
        return logging.WARNING
    return logging.INFO


def _marca_de_tiempo(registro: logging.LogRecord) -> str:
    return datetime.fromtimestamp(registro.created, tz=timezone.utc).isoformat()


def _campos_estructurados(registro: logging.LogRecord) -> dict[str, Any]:
    """Solo los campos de la lista blanca presentes en el registro."""
    return {
        campo: getattr(registro, campo)
        for campo in CAMPOS_ADICIONALES
        if hasattr(registro, campo)
    }


class FormateadorJSON(logging.Formatter):
    """Una linea JSON por evento, con los campos fijos y los de la lista blanca."""

    def format(self, registro: logging.LogRecord) -> str:
        salida: dict[str, Any] = {
            "timestamp": _marca_de_tiempo(registro),
            "level": registro.levelname,
            "logger": registro.name,
            "message": registro.getMessage(),
        }
        salida.update(_campos_estructurados(registro))
        return json.dumps(salida, ensure_ascii=False, default=str)


class FormateadorTexto(logging.Formatter):
    """Linea legible para desarrollo local; deliberadamente no es JSON valido."""

    def format(self, registro: logging.LogRecord) -> str:
        partes = [
            _marca_de_tiempo(registro),
            registro.levelname,
            registro.name,
            registro.getMessage(),
        ]
        for campo, valor in _campos_estructurados(registro).items():
            partes.append(f"{campo}={valor}")
        return " ".join(partes)


def configurar_registro(
    nivel: str | None = None,
    formato: str | None = None,
    nombre_logger: str = LOGGER_RAIZ,
) -> logging.Logger:
    """Configura el logger `compustock` de forma idempotente.

    No toca los loggers de uvicorn ni el logger raiz. El handler propio se
    reemplaza en cada llamada para que los tests y los reinicios no dupliquen
    lineas, y se escribe en `stdout` tanto en desarrollo como en el contenedor.
    """
    logger = logging.getLogger(nombre_logger)
    nivel_efectivo = resolver_nivel(
        nivel if nivel is not None else settings.LOG_LEVEL
    )
    logger.setLevel(nivel_efectivo)
    logger.propagate = False

    for existente in list(logger.handlers):
        if getattr(existente, _MARCA_HANDLER, False):
            logger.removeHandler(existente)

    manejador = logging.StreamHandler(sys.stdout)
    setattr(manejador, _MARCA_HANDLER, True)
    manejador.setLevel(nivel_efectivo)
    if resolver_formato(
        formato if formato is not None else settings.LOG_FORMAT
    ) == "text":
        manejador.setFormatter(FormateadorTexto())
    else:
        manejador.setFormatter(FormateadorJSON())
    logger.addHandler(manejador)

    return logger
