"""AC-8, AC-9 y AC-10: `/health` intacto y `/ready` con motor dedicado."""

import json

from sqlalchemy.exc import OperationalError
from sqlalchemy.pool import NullPool

from app.api import dependencies
from app.db.database import crear_motor_readiness, opciones_motor_readiness
from app.main import app

from tests.funcional.integracion.soporte_observabilidad_024 import capturar_logs


class _MotorCaido:
    """Motor falso cuya conexion falla como lo haria PostgreSQL inalcanzable."""

    def connect(self):
        raise OperationalError(
            "SELECT 1", {}, RuntimeError("conexion rechazada de prueba")
        )


def _instalar_motor_caido() -> _MotorCaido:
    motor_caido = _MotorCaido()
    app.dependency_overrides[dependencies.obtener_motor_readiness] = (
        lambda: motor_caido
    )
    return motor_caido


def test_ready_responde_200_con_sqlite(cliente):
    respuesta = cliente.get("/ready")

    assert respuesta.status_code == 200
    assert respuesta.json() == {"status": "ready"}
    assert respuesta.headers["x-request-id"]


def test_ready_responde_503_saneado_y_correlacionado(cliente):
    _instalar_motor_caido()

    with capturar_logs() as lineas:
        respuesta = cliente.get("/ready")

    assert respuesta.status_code == 503
    assert respuesta.json() == {"status": "not_ready"}
    cuerpo = respuesta.text.lower()
    for prohibido in ("psycopg2", "connection", "postgres", "apt_erp"):
        assert prohibido not in cuerpo

    registros = [
        json.loads(linea)
        for linea in lineas
        if json.loads(linea).get("message") == "readiness_fallida"
    ]
    assert len(registros) == 1
    registro = registros[0]
    assert registro["logger"] == "compustock.salud"
    assert registro["request_id"] == respuesta.headers["x-request-id"]
    assert registro["error_type"] == "OperationalError"
    assert "postgres" not in json.dumps(registro).lower()


def test_health_responde_200_aunque_la_base_este_caida(cliente):
    _instalar_motor_caido()

    respuesta = cliente.get("/health")

    assert respuesta.status_code == 200
    assert respuesta.json() == {"status": "healthy"}


def test_health_sigue_documentado_sin_security_y_ready_no_aparece(cliente):
    esquema = cliente.get("/openapi.json").json()

    assert "/health" in esquema["paths"]
    assert "security" not in esquema["paths"]["/health"]["get"]
    assert "/ready" not in esquema["paths"]
    assert "/metrics" not in esquema["paths"]


def test_opciones_de_readiness_postgresql_acotan_conexion_y_sentencia():
    # Ajuste de T12: con 2 s el driver consumia el presupuesto entero y el
    # overhead del handler superaba el limite de AC-10. El plan contempla la
    # bajada a 1 s / 1500 ms si la medicion de T12 superaba 2 s.
    opciones = opciones_motor_readiness(
        "postgresql+psycopg2://usuario:clave@db:5432/apt_erp"
    )

    assert opciones["poolclass"] is NullPool
    assert opciones["connect_args"]["connect_timeout"] == 1
    assert opciones["connect_args"]["options"] == "-c statement_timeout=1500"


def test_opciones_de_readiness_sqlite_solo_usa_nullpool():
    opciones = opciones_motor_readiness("sqlite+pysqlite:///:memory:")

    assert opciones == {"poolclass": NullPool}


def test_motor_de_readiness_es_efimero():
    motor = crear_motor_readiness("sqlite+pysqlite:///:memory:")

    try:
        assert isinstance(motor.pool, NullPool)
    finally:
        motor.dispose()
