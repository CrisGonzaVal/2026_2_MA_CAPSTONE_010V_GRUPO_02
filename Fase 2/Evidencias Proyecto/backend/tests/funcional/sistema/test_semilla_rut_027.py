"""Feature 027, T6: la semilla QA solo contiene RUT con DV valido."""

from pathlib import Path

import pytest

from app.core.rut import validar_rut

RAIZ_REPOSITORIO = Path(__file__).resolve().parents[4]

CAMBIOS_SEMILLA = [
    ("01_esquema.sql", "65.432.100-9", "65.432.100-0"),
    ("01_esquema.sql", "65.887.230-1", "65.887.230-3"),
    ("01_esquema.sql", "77.120.540-3", "77.120.540-2"),
    ("01_esquema.sql", "65.998.720-K", "65.998.720-1"),
    ("02_datos_semilla.sql", "76.543.210-8", "76.543.210-3"),
    ("02_datos_semilla.sql", "77.654.321-K", "77.654.321-7"),
    ("02_datos_semilla.sql", "78.765.432-1", "78.765.432-0"),
]


@pytest.mark.parametrize(("archivo", "anterior", "vigente"), CAMBIOS_SEMILLA)
def test_rut_de_semilla_fue_corregido_y_es_valido(archivo, anterior, vigente):
    texto = (RAIZ_REPOSITORIO / "database" / archivo).read_text(encoding="utf-8")

    assert anterior not in texto
    assert vigente in texto
    assert validar_rut(vigente) == vigente
