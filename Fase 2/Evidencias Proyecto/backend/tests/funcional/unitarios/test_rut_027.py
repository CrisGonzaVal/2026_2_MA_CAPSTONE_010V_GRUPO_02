"""Pruebas unitarias del RUT chileno (Feature 027).

El seam es la API publica de `app.core.rut`: normalizacion, digito verificador
modulo 11, validacion del formato visible y formateo. Son funciones puras: no
tocan HTTP, Pydantic ni SQLAlchemy.
"""

import pytest

from app.core.rut import calcular_dv, formatear_rut, normalizar_rut, validar_rut


# ---------------------------------------------------------------------------
# normalizar_rut
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("entrada", "esperada"),
    [
        ("76.543.210-3", "765432103"),
        ("76543210-3", "765432103"),
        ("765432103", "765432103"),
        (" 76.543.210-3 ", "765432103"),
        ("76.543.210-k", "76543210K"),
        ("", ""),
    ],
)
def test_normalizar_rut_quita_separadores_y_pasa_a_mayusculas(entrada, esperada):
    """La clave de comparacion replica la de la Feature 026."""
    assert normalizar_rut(entrada) == esperada


# ---------------------------------------------------------------------------
# calcular_dv
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("cuerpo", "esperado"),
    [
        ("76543210", "3"),
        ("77654321", "7"),
        ("78765432", "0"),
        ("96021030", "1"),
        ("19191919", "K"),
        ("6", "K"),
        ("1", "9"),
        ("2", "7"),
        ("3", "5"),
        ("4", "3"),
        ("5", "1"),
        ("7", "8"),
        ("8", "6"),
        ("9", "4"),
        ("0", "0"),
    ],
)
def test_calcular_dv_aplica_modulo_11(cuerpo, esperado):
    """Multiplicadores 2..7 desde la derecha; 11 -> 0 y 10 -> K."""
    assert calcular_dv(cuerpo) == esperado


@pytest.mark.parametrize("cuerpo", ["", "12a", "123456789", " 123"])
def test_calcular_dv_rechaza_cuerpos_invalidos(cuerpo):
    """Solo acepta de 1 a 8 digitos, sin separadores."""
    with pytest.raises(ValueError, match="1 y 8"):
        calcular_dv(cuerpo)


# ---------------------------------------------------------------------------
# validar_rut
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("entrada", "visible"),
    [
        ("76.543.210-3", "76.543.210-3"),
        ("76543210-3", "76543210-3"),
        ("765432103", "765432103"),
        (" 76.543.210-3 ", "76.543.210-3"),
        ("1-9", "1-9"),
        ("6-k", "6-K"),
        ("19.191.919-k", "19.191.919-K"),
        ("77.654.321-7", "77.654.321-7"),
        ("78.765.432-0", "78.765.432-0"),
        ("96.021.030-1", "96.021.030-1"),
    ],
)
def test_validar_rut_acepta_formas_visibles_y_devuelve_la_recortada(entrada, visible):
    """Acepta con puntos, sin puntos o con guion; conserva el formato enviado."""
    assert validar_rut(entrada) == visible


@pytest.mark.parametrize(
    "entrada",
    [
        "76.543.210-8",
        "77.654.321-K",
        "78.765.432-1",
        "12.345.678-9",
        "99-9",
        "76.543.210-",
    ],
)
def test_validar_rut_rechaza_digito_verificador_incorrecto(entrada):
    """El DV calculado debe coincidir con el enviado."""
    with pytest.raises(ValueError, match="dígito verificador"):
        validar_rut(entrada)


@pytest.mark.parametrize(
    "entrada",
    [
        "",
        "   ",
        "0-0",
        "123456789-0",
        "76.543.210-33",
        "abc-1",
    ],
)
def test_validar_rut_rechaza_formato_invalido(entrada):
    """Cuerpo de 1..8 digitos, distinto de cero, y DV 0-9/K."""
    with pytest.raises(ValueError, match="1 y 8"):
        validar_rut(entrada)


# ---------------------------------------------------------------------------
# formatear_rut
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("765432103", "76.543.210-3"),
        ("76.543.210-3", "76.543.210-3"),
        ("1-9", "1-9"),
        ("123-4", "123-4"),
        ("1234-5", "1.234-5"),
        ("76543210k", "76.543.210-K"),
        (" 19.191.919-k ", "19.191.919-K"),
    ],
)
def test_formatear_rut_agrupa_el_cuerpo_con_puntos(entrada, esperado):
    """Solo presentacion: no valida el DV, pero si el cuerpo."""
    assert formatear_rut(entrada) == esperado


@pytest.mark.parametrize("entrada", ["", "abc-1", "123456789-0"])
def test_formatear_rut_rechaza_cuerpos_invalidos(entrada):
    """Un cuerpo no numerico o fuera de 1..8 digitos no se formatea."""
    with pytest.raises(ValueError, match="1 y 8"):
        formatear_rut(entrada)


# ---------------------------------------------------------------------------
# Compatibilidad con la Feature 026
# ---------------------------------------------------------------------------


def test_normalizar_rut_se_reexporta_desde_el_servicio_de_proveedores():
    """Los consumidores historicos siguen importando desde `proveedores`."""
    from app.services.compra_service.proveedores import (
        normalizar_rut as normalizar_desde_servicio,
    )

    assert normalizar_desde_servicio(" 76.543.210-k ") == "76543210K"

