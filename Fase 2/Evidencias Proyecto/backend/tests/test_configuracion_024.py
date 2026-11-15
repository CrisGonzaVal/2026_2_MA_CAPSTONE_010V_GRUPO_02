"""AC-6 y AC-17: configuracion por entorno de la Feature 024.

Fija los defaults de CORS y logging, el recorte de `ALLOWED_ORIGINS`, el
fail-fast ante una lista vacia y la tolerancia a valores de log desconocidos.
"""

import json
import logging
from datetime import datetime

import pytest
from pydantic import ValidationError

from app.core.config import VERSION_APLICACION, Settings
from app.core.observabilidad import (
    FormateadorJSON,
    FormateadorTexto,
    configurar_registro,
    nivel_de_estado,
    resolver_formato,
    resolver_identificador,
    resolver_nivel,
)


def test_version_aplicacion_conserva_el_valor_publicado():
    assert VERSION_APLICACION == "1.0.0"


def test_default_de_origenes_permite_dev_y_nginx():
    configuracion = Settings()

    assert configuracion.origenes_permitidos == [
        "http://localhost:4200",
        "http://localhost:8080",
    ]


def test_origenes_recorta_espacios_y_descarta_entradas_vacias():
    configuracion = Settings(
        ALLOWED_ORIGINS=" http://a.example , , http://b.example "
    )

    assert configuracion.origenes_permitidos == [
        "http://a.example",
        "http://b.example",
    ]
    assert configuracion.ALLOWED_ORIGINS == "http://a.example,http://b.example"


@pytest.mark.parametrize("valor", ["", " , ", ",,,", "   "])
def test_origenes_vacios_impiden_construir_la_configuracion(valor):
    with pytest.raises(ValidationError) as error:
        Settings(ALLOWED_ORIGINS=valor)

    assert "ALLOWED_ORIGINS" in str(error.value)
    assert "origen" in str(error.value).lower()


def test_origenes_alternos_reemplazan_el_default():
    configuracion = Settings(ALLOWED_ORIGINS="http://otro.example")

    assert configuracion.origenes_permitidos == ["http://otro.example"]


def test_defaults_de_logging_son_json_e_info():
    configuracion = Settings()

    assert configuracion.LOG_FORMAT == "json"
    assert configuracion.LOG_LEVEL == "INFO"


@pytest.mark.parametrize("formato", ["xml", "", "JSONL", "TEXT"])
def test_formato_de_log_desconocido_no_rompe_el_arranque(formato):
    # La normalizacion (desconocido -> json) vive en `core/observabilidad.py`;
    # aqui solo se fija que `Settings` acepta el valor sin validarlo con Literal.
    configuracion = Settings(LOG_FORMAT=formato)

    assert configuracion.LOG_FORMAT == formato


@pytest.mark.parametrize("nivel", ["TRACE", "", "verbose", "warn"])
def test_nivel_de_log_desconocido_no_rompe_el_arranque(nivel):
    configuracion = Settings(LOG_LEVEL=nivel)

    assert configuracion.LOG_LEVEL == nivel


# ---------------------------------------------------------------------------
# T3: formateadores, niveles y configuracion del logger
# ---------------------------------------------------------------------------


def _registro_de_acceso(**adicionales) -> logging.LogRecord:
    registro = logging.LogRecord(
        name="compustock.acceso",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="peticion_completada",
        args=(),
        exc_info=None,
    )
    registro.request_id = "3f1c2a9e-8b7d-4c6e-9f01-2a3b4c5d6e7f"
    registro.method = "GET"
    registro.path = "/health"
    registro.status = 200
    registro.duration_ms = 1.234
    for campo, valor in adicionales.items():
        setattr(registro, campo, valor)
    return registro


def test_formateador_json_emite_los_nueve_campos_parseables():
    linea = FormateadorJSON().format(_registro_de_acceso())

    datos = json.loads(linea)
    assert set(datos) == {
        "timestamp",
        "level",
        "logger",
        "message",
        "request_id",
        "method",
        "path",
        "status",
        "duration_ms",
    }
    assert datos["level"] == "INFO"
    assert datos["logger"] == "compustock.acceso"
    assert datos["message"] == "peticion_completada"
    assert datos["request_id"] == "3f1c2a9e-8b7d-4c6e-9f01-2a3b4c5d6e7f"
    assert datos["path"] == "/health"
    assert datetime.fromisoformat(datos["timestamp"]).tzinfo is not None


def test_formateador_json_descarta_campos_fuera_de_la_lista_blanca():
    linea = FormateadorJSON().format(
        _registro_de_acceso(correo="foo@example.com", token="secreto")
    )

    assert "foo@example.com" not in linea
    assert "secreto" not in linea


def test_formateador_texto_es_legible_y_no_json():
    linea = FormateadorTexto().format(_registro_de_acceso())

    assert "peticion_completada" in linea
    assert "request_id=" in linea
    with pytest.raises(json.JSONDecodeError):
        json.loads(linea)


@pytest.mark.parametrize(
    ("status", "esperado"),
    [
        (200, logging.INFO),
        (204, logging.INFO),
        (404, logging.WARNING),
        (422, logging.WARNING),
        (500, logging.ERROR),
        (503, logging.ERROR),
    ],
)
def test_nivel_de_estado(status, esperado):
    assert nivel_de_estado(status) == esperado


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        (None, logging.INFO),
        ("info", logging.INFO),
        ("WARNING", logging.WARNING),
        ("error", logging.ERROR),
        ("trace", logging.INFO),
        ("", logging.INFO),
    ],
)
def test_resolver_nivel(valor, esperado):
    assert resolver_nivel(valor) == esperado


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [(None, "json"), ("", "json"), ("json", "json"), ("xml", "json"),
     ("text", "text"), ("TEXT", "text")],
)
def test_resolver_formato(valor, esperado):
    assert resolver_formato(valor) == esperado


def test_configurar_registro_warning_filtra_info_y_deja_handler_al_nivel(capsys):
    logger = configurar_registro(
        nivel="WARNING",
        formato="json",
        nombre_logger="compustock.prueba_024",
    )

    assert logger.level == logging.WARNING
    assert all(handler.level == logging.WARNING for handler in logger.handlers)
    assert logger.propagate is False

    logger.info("no debe salir")
    logger.warning("si debe salir")

    salida = capsys.readouterr().out
    assert "no debe salir" not in salida
    assert "si debe salir" in salida


def test_configurar_registro_es_idempotente(capsys):
    nombre = "compustock.prueba_idempotente_024"
    configurar_registro("INFO", "json", nombre_logger=nombre)
    configurar_registro("INFO", "json", nombre_logger=nombre)

    logger = logging.getLogger(nombre)
    propios = [
        handler
        for handler in logger.handlers
        if getattr(handler, "_compustock_handler", False)
    ]
    assert len(propios) == 1

    logger.info("una sola linea")
    salida = capsys.readouterr().out.strip().splitlines()
    assert len(salida) == 1
    assert json.loads(salida[0])["message"] == "una sola linea"


@pytest.mark.parametrize(
    ("cabecera", "identica"),
    [
        ("3f1c2a9e-8b7d-4c6e-9f01-2a3b4c5d6e7f", True),
        ("3F1C2A9E-8B7D-4C6E-9F01-2A3B4C5D6E7F", True),
        ("abc", False),
        ("", False),
        (None, False),
        ("3f1c2a9e8b7d4c6e9f012a3b4c5d6e7f", False),
        ("{3f1c2a9e-8b7d-4c6e-9f01-2a3b4c5d6e7f}", False),
    ],
)
def test_resolver_identificador_solo_acepta_uuid_canonico(cabecera, identica):
    resultado = resolver_identificador(cabecera)

    if identica:
        assert resultado == cabecera
    else:
        assert resultado != cabecera
        assert len(resultado) == 36
