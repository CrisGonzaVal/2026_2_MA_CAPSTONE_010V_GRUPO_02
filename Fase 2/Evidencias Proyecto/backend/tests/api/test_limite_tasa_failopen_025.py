"""AC-9, AC-10 y AC-11: fail-open del limite de tasa (Feature 025).

Un fallo de Redis nunca cambia el estado ni el cuerpo de la ruta: la peticion
pasa, se cuenta como `error` y el aviso se emite como maximo una vez por
ventana, sin IP, host, mensaje ni traza. `/ready` sigue midiendo solo la base.
"""

import asyncio
import json
import time
import uuid

from fastapi.testclient import TestClient

from app.api import dependencies
from app.core.limite_tasa import AlmacenRedis, LimitadorTasa
from app.core.metricas import generar_exposicion
from tests.soporte_limite_tasa_025 import (
    AlmacenFalso,
    crear_app_con_limite,
    crear_scope,
)
from tests.soporte_observabilidad_024 import capturar_logs, valor_de_serie

RUTA = "/api/v1/auth/me"
IP_PRUEBA = "203.0.113.9"
MENSAJE_ERROR = "conexion rechazada hacia el almacen"


def _serie_error() -> float:
    return (
        valor_de_serie(
            generar_exposicion(),
            "compustock_rate_limit_requests_total",
            resultado="error",
        )
        or 0.0
    )


def test_un_almacen_caido_deja_pasar_y_avisa_una_sola_vez(monkeypatch):
    falso = AlmacenFalso(error=ConnectionError(MENSAJE_ERROR))
    aplicacion = crear_app_con_limite(
        monkeypatch, falso, maximo=3, confiar_proxy=True
    )
    antes = _serie_error()

    with capturar_logs() as lineas:
        with TestClient(aplicacion) as cliente:
            estados = [
                cliente.get(RUTA, headers={"X-Real-IP": IP_PRUEBA}).status_code
                for _ in range(20)
            ]

    assert estados == [401] * 20
    assert _serie_error() - antes == 20

    avisos = [
        json.loads(linea)
        for linea in lineas
        if "limite_tasa_degradado" in linea
    ]
    assert len(avisos) == 1
    aviso = avisos[0]
    assert aviso["error_type"] == "ConnectionError"
    assert str(uuid.UUID(aviso["request_id"])) == aviso["request_id"]

    texto = "".join(lineas)
    assert IP_PRUEBA not in texto
    assert MENSAJE_ERROR not in texto
    assert "Traceback" not in texto
    assert "compustock:limite:" not in texto


def test_redis_inalcanzable_no_bloquea_mas_de_lo_previsto():
    async def escenario():
        almacen = AlmacenRedis("redis://192.0.2.1:6379/0")
        limitador = LimitadorTasa(
            almacen=almacen,
            maximo=120,
            ventana_segundos=60,
            confiar_proxy=False,
        )
        inicio = time.monotonic()
        resultados = [
            await limitador.evaluar(crear_scope()) for _ in range(3)
        ]
        duracion = time.monotonic() - inicio
        await almacen.cerrar()
        return duracion, resultados

    duracion, resultados = asyncio.run(escenario())

    assert all(resultado.permitida for resultado in resultados)
    assert duracion < 1.0


def test_ready_y_health_no_dependen_de_redis(monkeypatch, motor):
    falso = AlmacenFalso(error=ConnectionError(MENSAJE_ERROR))
    aplicacion = crear_app_con_limite(monkeypatch, falso, maximo=3)
    aplicacion.dependency_overrides[dependencies.obtener_motor_readiness] = (
        lambda: motor
    )

    with TestClient(aplicacion) as cliente:
        ready = cliente.get("/ready")
        health = cliente.get("/health")

    assert ready.status_code == 200
    assert ready.json() == {"status": "ready"}
    assert health.status_code == 200
    assert "redis" not in ready.text.lower()
    assert falso.llamadas == []
