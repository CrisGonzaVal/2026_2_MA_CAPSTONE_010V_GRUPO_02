"""Soporte compartido por las pruebas de observabilidad de la Feature 024.

No es un archivo de tests: concentra la captura de lineas del logger
`compustock` y, mas adelante, el parser de la exposicion Prometheus y el fake
de motor caido para la suite de readiness.
"""

import logging
from contextlib import contextmanager

from prometheus_client.parser import text_string_to_metric_families

from app.core.observabilidad import LOGGER_RAIZ, FormateadorJSON


class _Captura(logging.Handler):
    """Handler de memoria que formatea cada registro como JSON."""

    def __init__(self):
        super().__init__()
        self.lineas: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lineas.append(self.format(record))


@contextmanager
def capturar_logs(nivel: int = logging.DEBUG):
    """Captura las lineas del logger `compustock` sin tocar su handler de stdout.

    Devuelve la lista de lineas; cada una se formatea como JSON para que las
    pruebas puedan parsearla y comprobar los campos estructurados.
    """
    logger = logging.getLogger(LOGGER_RAIZ)
    anterior = logger.level
    handler = _Captura()
    handler.setLevel(nivel)
    handler.setFormatter(FormateadorJSON())
    logger.setLevel(nivel)
    logger.addHandler(handler)
    try:
        yield handler.lineas
    finally:
        logger.removeHandler(handler)
        logger.setLevel(anterior)


def leer_familias(texto: str) -> dict:
    """Familias Prometheus por nombre base (`compustock_...`)."""
    return {
        familia.name: familia
        for familia in text_string_to_metric_families(texto)
    }


def leer_muestras(texto: str, nombre: str) -> list:
    """Muestras de una serie concreta, incluidos sufijos `_bucket/_sum/_count`."""
    return [
        muestra
        for familia in text_string_to_metric_families(texto)
        for muestra in familia.samples
        if muestra.name == nombre
    ]


def valor_de_serie(texto: str, nombre: str, **etiquetas) -> float | None:
    """Valor de la primera muestra que contiene todas las etiquetas dadas."""
    for muestra in leer_muestras(texto, nombre):
        if all(muestra.labels.get(clave) == valor for clave, valor in etiquetas.items()):
            return muestra.value
    return None
