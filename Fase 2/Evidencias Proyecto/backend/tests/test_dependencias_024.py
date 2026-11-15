"""AC-22: reproducibilidad del nivel directo de dependencias del backend.

El test lee `backend/requirements.txt` y fija el contrato de la Feature 024:
diez dependencias directas, todas con `==`, sin duplicados y con las versiones
que el proyecto ejecuta y verifica. No consulta el entorno instalado ni la red;
`pip check` cubre la resolucion real en la tarea de cierre.
"""

import re
from pathlib import Path

REQUISITOS = Path(__file__).resolve().parents[1] / "requirements.txt"

#: D-8 de la spec 024 mas la unica dependencia nueva (D-9).
VERSIONES_ESPERADAS = {
    "fastapi": "0.142.2",
    "uvicorn": "0.54.0",
    "sqlalchemy": "2.1.1",
    "psycopg2-binary": "2.9.13",
    "pydantic": "2.13.5",
    "pydantic-settings": "2.15.0",
    "python-dotenv": "1.2.3",
    "pyjwt": "2.15.1",
    "httpx": "0.28.1",
    "prometheus-client": "0.26.0",
}

_PATRON_DEPENDENCIA = re.compile(
    r"^(?P<nombre>[A-Za-z0-9_.-]+)(?:\[[A-Za-z0-9_,.-]+\])?==(?P<version>[^\s]+)$"
)


def _lineas_de_dependencias() -> list[str]:
    contenido = REQUISITOS.read_text(encoding="utf-8")
    return [
        linea.strip()
        for linea in contenido.splitlines()
        if linea.strip() and not linea.strip().startswith("#")
    ]


def _nombre_normalizado(nombre: str) -> str:
    return nombre.split("[", 1)[0].lower().replace("_", "-")


def test_requirements_declara_exactamente_diez_dependencias_directas():
    lineas = _lineas_de_dependencias()
    assert len(lineas) == 10, (
        "AC-22 exige diez dependencias directas (nueve existentes + "
        f"prometheus-client); requirements.txt declara {len(lineas)}"
    )
    assert len(set(lineas)) == len(lineas), "requirements.txt no debe repetir lineas"


def test_todas_las_dependencias_estan_pineadas_con_igualdad_exacta():
    for linea in _lineas_de_dependencias():
        assert _PATRON_DEPENDENCIA.fullmatch(linea), (
            f"la dependencia directa no esta pineada con ==: {linea!r}"
        )


def test_versiones_y_nombres_coinciden_con_d8_y_d9():
    obtenidas: dict[str, str] = {}
    for linea in _lineas_de_dependencias():
        coincidencia = _PATRON_DEPENDENCIA.fullmatch(linea)
        assert coincidencia is not None, linea
        nombre = _nombre_normalizado(coincidencia.group("nombre"))
        assert nombre not in obtenidas, f"dependencia duplicada: {nombre}"
        obtenidas[nombre] = coincidencia.group("version")

    assert obtenidas == VERSIONES_ESPERADAS, (
        "las versiones directas deben ser las de D-8 mas prometheus-client==0.26.0; "
        f"se obtuvo {obtenidas}"
    )


def test_prometheus_client_es_la_unica_dependencia_nueva():
    nombres = {
        _nombre_normalizado(_PATRON_DEPENDENCIA.fullmatch(linea).group("nombre"))
        for linea in _lineas_de_dependencias()
    }
    assert "prometheus-client" in nombres
    assert len(nombres) == 10
    assert nombres == set(VERSIONES_ESPERADAS)
