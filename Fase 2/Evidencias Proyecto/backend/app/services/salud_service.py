"""Servicio de disponibilidad (Feature 024, AC-9/AC-10).

La sonda no lee ninguna tabla de dominio: ejecuta `SELECT 1` con SQLAlchemy
Core tipado contra el motor de readiness. Solo se conserva el **nombre** del
error para el log; nunca la cadena de conexion ni el mensaje del driver.
"""

from sqlalchemy import literal, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError


def comprobar_conectividad(motor: Engine) -> tuple[bool, str | None]:
    """Devuelve `(disponible, nombre_del_error)` sin propagar la excepcion."""
    try:
        with motor.connect() as conexion:
            conexion.execute(select(literal(1)))
        return True, None
    except SQLAlchemyError as error:
        return False, type(error).__name__
