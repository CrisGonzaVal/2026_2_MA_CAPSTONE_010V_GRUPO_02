"""AC-12 y AC-13: metrica del limitador y ruta reservada (Feature 025).

Comprueban que la sexta familia cuenta permitidas, limitadas y errores; que la
etiqueta es exactamente `{resultado}`; que el 429 se registra como
`route="rate_limited"` en la metrica y en la linea de acceso; y que ni la
exposicion, ni los logs, ni el cuerpo filtran la IP, la clave o el prefijo.
"""

import json

from fastapi.testclient import TestClient

from app.core.metricas import generar_exposicion
from tests.no_funcional.rendimiento.soporte_limite_tasa_025 import AlmacenFalso, crear_app_con_limite
from tests.funcional.integracion.soporte_observabilidad_024 import (
    capturar_logs,
    leer_familias,
    valor_de_serie,
)

RUTA = "/api/v1/auth/me"
IP_PRUEBA = "203.0.113.7"

#: El parser de Prometheus nombra las familias de contador sin el sufijo
#: `_total`; el nombre de la muestra sí lo conserva.
FAMILIA_NUEVA = "compustock_rate_limit_requests"
SERIE_NUEVA = "compustock_rate_limit_requests_total"

FAMILIAS_024 = {
    "compustock_http_requests",
    "compustock_http_request_duration_seconds",
    "compustock_http_requests_in_flight",
    "compustock_http_errors",
    "compustock_app_info",
}


def _valor(resultado: str) -> float:
    return (
        valor_de_serie(
            generar_exposicion(), SERIE_NUEVA, resultado=resultado
        )
        or 0.0
    )


def test_la_familia_nueva_cuenta_permitidas_y_limitadas(monkeypatch):
    falso = AlmacenFalso()
    aplicacion = crear_app_con_limite(
        monkeypatch, falso, maximo=1, confiar_proxy=True
    )
    permitidas_antes = _valor("permitida")
    limitadas_antes = _valor("limitada")

    with TestClient(aplicacion) as cliente:
        permitida = cliente.get(RUTA, headers={"X-Real-IP": IP_PRUEBA})
        limitada = cliente.get(RUTA, headers={"X-Real-IP": IP_PRUEBA})

    assert [permitida.status_code, limitada.status_code] == [401, 429]
    assert _valor("permitida") - permitidas_antes == 1
    assert _valor("limitada") - limitadas_antes == 1


def test_la_etiqueta_es_exactamente_el_resultado(monkeypatch):
    falso = AlmacenFalso()
    aplicacion = crear_app_con_limite(
        monkeypatch, falso, maximo=1, confiar_proxy=True
    )

    with TestClient(aplicacion) as cliente:
        cliente.get(RUTA, headers={"X-Real-IP": IP_PRUEBA})
        cliente.get(RUTA, headers={"X-Real-IP": IP_PRUEBA})

    familias = leer_familias(generar_exposicion())
    muestras = [
        muestra
        for muestra in familias[FAMILIA_NUEVA].samples
        if muestra.name == SERIE_NUEVA
    ]
    assert muestras
    assert all(set(muestra.labels) == {"resultado"} for muestra in muestras)
    assert {muestra.labels["resultado"] for muestra in muestras} >= {
        "permitida",
        "limitada",
    }


def test_las_cinco_familias_de_la_024_siguen_presentes(monkeypatch):
    falso = AlmacenFalso()
    aplicacion = crear_app_con_limite(monkeypatch, falso, maximo=3)

    with TestClient(aplicacion) as cliente:
        cliente.get(RUTA)

    familias = leer_familias(generar_exposicion())

    assert FAMILIAS_024 <= set(familias)
    assert FAMILIA_NUEVA in familias
    assert len(FAMILIAS_024 | {FAMILIA_NUEVA}) == 6


def test_el_429_se_registra_como_rate_limited(monkeypatch):
    falso = AlmacenFalso()
    aplicacion = crear_app_con_limite(monkeypatch, falso, maximo=1)
    antes = (
        valor_de_serie(
            generar_exposicion(),
            "compustock_http_requests_total",
            method="GET",
            route="rate_limited",
            status="429",
        )
        or 0.0
    )

    with capturar_logs() as lineas:
        with TestClient(aplicacion) as cliente:
            cliente.get(RUTA)
            respuesta = cliente.get(RUTA)

    despues = (
        valor_de_serie(
            generar_exposicion(),
            "compustock_http_requests_total",
            method="GET",
            route="rate_limited",
            status="429",
        )
        or 0.0
    )
    assert respuesta.status_code == 429
    assert despues - antes == 1

    accesos = [
        json.loads(linea)
        for linea in lineas
        if json.loads(linea).get("message") == "peticion_completada"
        and json.loads(linea).get("status") == 429
    ]
    assert len(accesos) == 1
    assert accesos[0]["path"] == "rate_limited"


def test_ninguna_superficie_filtra_la_ip_ni_la_clave(monkeypatch):
    falso = AlmacenFalso()
    aplicacion = crear_app_con_limite(
        monkeypatch, falso, maximo=1, confiar_proxy=True
    )

    with capturar_logs() as lineas:
        with TestClient(aplicacion) as cliente:
            cliente.get(RUTA, headers={"X-Real-IP": IP_PRUEBA})
            respuesta = cliente.get(RUTA, headers={"X-Real-IP": IP_PRUEBA})

    assert respuesta.status_code == 429
    superficies = respuesta.text + generar_exposicion() + "".join(lineas)
    assert IP_PRUEBA not in superficies
    assert "compustock:limite:" not in superficies
    assert 'route="rate_limited"' in generar_exposicion()


def test_con_el_limitador_apagado_la_familia_no_se_mueve(monkeypatch):
    falso = AlmacenFalso()
    aplicacion = crear_app_con_limite(
        monkeypatch, falso, maximo=1, habilitado=False
    )
    antes = _valor("permitida")

    with TestClient(aplicacion) as cliente:
        respuesta = cliente.get(RUTA)

    assert respuesta.status_code == 401
    assert _valor("permitida") - antes == 0
    assert falso.llamadas == []
    familias = leer_familias(generar_exposicion())
    assert FAMILIAS_024 <= set(familias)
