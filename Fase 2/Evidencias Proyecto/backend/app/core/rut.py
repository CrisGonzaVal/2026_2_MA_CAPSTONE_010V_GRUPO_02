"""RUT chileno: normalizacion, digito verificador y validacion (Feature 027).

Funciones puras, sin HTTP, Pydantic ni SQLAlchemy. La validacion del digito
verificador se comparte entre proveedores e instituciones para que ambos
contratos rechacen exactamente el mismo valor.

La normalizacion replica la clave de la Feature 026: mayusculas, sin puntos,
guion ni espacios. El valor visible que se guarda es el enviado, recortado y en
mayusculas; la unicidad sigue evaluandose sobre la clave normalizada.
"""

from __future__ import annotations

_MENSAJE_FORMATO = (
    "El RUT debe tener entre 1 y 8 dígitos y un dígito verificador (0-9 o K)."
)
_MENSAJE_DV = "El RUT no es válido: el dígito verificador no corresponde."
_MENSAJE_CUERPO = "El cuerpo del RUT debe tener entre 1 y 8 dígitos."

_DIGITOS_DV = frozenset("0123456789K")


def normalizar_rut(rut: str) -> str:
    """Clave de comparacion: mayusculas, sin puntos, guion ni espacios.

    Coincide con la expresion del indice funcional
    `proveedor_rut_normalizado_uk` del DDL y del ORM (Feature 026).
    """
    return rut.replace(".", "").replace("-", "").replace(" ", "").strip().upper()


def calcular_dv(cuerpo: str) -> str:
    """Digito verificador modulo 11 de un cuerpo de 1 a 8 digitos.

    Recorre el cuerpo desde la derecha con multiplicadores 2..7 ciclicos. Un
    resto de 11 se representa como `0` y uno de 10 como `K`.
    """
    if not cuerpo.isdigit() or not 1 <= len(cuerpo) <= 8:
        raise ValueError(_MENSAJE_CUERPO)

    suma = 0
    multiplicador = 2
    for digito in reversed(cuerpo):
        suma += int(digito) * multiplicador
        multiplicador = 2 if multiplicador == 7 else multiplicador + 1

    resto = 11 - (suma % 11)
    if resto == 11:
        return "0"
    if resto == 10:
        return "K"
    return str(resto)


def validar_rut(rut: str) -> str:
    """Valida formato y DV; devuelve la forma visible recortada y en mayusculas.

    Acepta el RUT con puntos, con guion o sin separadores. El cuerpo debe tener
    de 1 a 8 digitos y no puede ser cero. Lanza `ValueError` con un mensaje en
    espanol cuando el formato o el digito verificador no corresponden.
    """
    visible = rut.strip().upper()
    limpio = normalizar_rut(visible)

    if len(limpio) < 2:
        raise ValueError(_MENSAJE_FORMATO)

    cuerpo, dv = limpio[:-1], limpio[-1]
    if (
        not cuerpo.isdigit()
        or not 1 <= len(cuerpo) <= 8
        or int(cuerpo) == 0
        or dv not in _DIGITOS_DV
    ):
        raise ValueError(_MENSAJE_FORMATO)

    if dv != calcular_dv(cuerpo):
        raise ValueError(_MENSAJE_DV)

    return visible


def formatear_rut(rut: str) -> str:
    """Devuelve el RUT visible con puntos y guion (solo presentacion).

    No valida el digito verificador: agrupa el cuerpo de derecha a izquierda en
    bloques de tres y conserva el DV en mayusculas.
    """
    limpio = normalizar_rut(rut)
    if len(limpio) < 2:
        raise ValueError(_MENSAJE_FORMATO)

    cuerpo, dv = limpio[:-1], limpio[-1]
    if not cuerpo.isdigit() or not 1 <= len(cuerpo) <= 8:
        raise ValueError(_MENSAJE_FORMATO)

    grupos: list[str] = []
    resto = cuerpo
    while resto:
        grupos.insert(0, resto[-3:])
        resto = resto[:-3]

    return f"{'.'.join(grupos)}-{dv}"
