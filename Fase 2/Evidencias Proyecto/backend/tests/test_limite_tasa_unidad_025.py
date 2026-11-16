"""Pruebas unitarias del nucleo del limite de tasa (Feature 025).

Cubren la resolucion de IP (confianza, validacion y `X-Forwarded-For`), el
alcance de rutas, el preflight y la semantica del limitador con un almacen
falso: conteo, rechazo, TTL que no se renueva y clave por IP. Sin
`pytest-asyncio`: cada escenario asincrono se envuelve en `asyncio.run`.
"""

import asyncio

import pytest

from app.core.limite_tasa import (
    IP_RESERVADA,
    LIMITE_PREFIJO_CLAVE,
    LimitadorTasa,
    es_preflight,
    es_ruta_limitada,
    resolver_ip,
)
from tests.soporte_limite_tasa_025 import AlmacenFalso, crear_scope


# ---------------------------------------------------------------------------
# Resolucion de IP
# ---------------------------------------------------------------------------


def test_sin_confianza_ignora_x_real_ip_y_usa_el_par_tcp():
    scope = crear_scope(cabeceras={"X-Real-IP": "198.51.100.9"})

    assert resolver_ip(scope, confiar_proxy=False) == "203.0.113.7"


@pytest.mark.parametrize(
    ("cabecera", "esperada"),
    [
        ("198.51.100.9", "198.51.100.9"),
        ("2001:db8::1", "2001:db8::1"),
    ],
)
def test_con_confianza_usa_x_real_ip_valida(cabecera, esperada):
    scope = crear_scope(cabeceras={"X-Real-IP": cabecera})

    assert resolver_ip(scope, confiar_proxy=True) == esperada


@pytest.mark.parametrize(
    "cabecera",
    ["abc", "1.2.3.4:80", "1.1.1.1, 2.2.2.2", "", "  "],
)
def test_con_confianza_ignora_x_real_ip_invalida(cabecera):
    scope = crear_scope(cabeceras={"X-Real-IP": cabecera})

    assert resolver_ip(scope, confiar_proxy=True) == "203.0.113.7"


@pytest.mark.parametrize("confiar", [False, True])
def test_x_forwarded_for_nunca_cambia_la_ip(confiar):
    scope = crear_scope(cabeceras={"X-Forwarded-For": "198.51.100.9"})

    assert resolver_ip(scope, confiar_proxy=confiar) == "203.0.113.7"


def test_sin_par_tcp_devuelve_la_ip_reservada():
    scope = crear_scope(ip=None)

    assert resolver_ip(scope, confiar_proxy=False) == IP_RESERVADA


def test_con_host_vacio_devuelve_la_ip_reservada():
    scope = crear_scope(ip="")

    assert resolver_ip(scope, confiar_proxy=False) == IP_RESERVADA


# ---------------------------------------------------------------------------
# Alcance y preflight
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "camino",
    ["/api/v1", "/api/v1/", "/api/v1/auth/me", "/api/v1/tickets/7"],
)
def test_las_rutas_de_la_api_v1_estan_limitadas(camino):
    assert es_ruta_limitada(camino) is True


@pytest.mark.parametrize(
    "camino",
    ["/", "/api", "/api/v10", "/api/v1x", "/health", "/ready", "/metrics", "/docs", "/openapi.json"],
)
def test_las_rutas_fuera_de_la_api_v1_no_estan_limitadas(camino):
    assert es_ruta_limitada(camino) is False


def test_preflight_exige_metodo_y_las_dos_cabeceras():
    completo = crear_scope(
        metodo="OPTIONS",
        cabeceras={
            "Origin": "http://localhost:4200",
            "Access-Control-Request-Method": "GET",
        },
    )
    sin_metodo = crear_scope(
        metodo="POST",
        cabeceras={
            "Origin": "http://localhost:4200",
            "Access-Control-Request-Method": "GET",
        },
    )
    sin_origen = crear_scope(
        metodo="OPTIONS",
        cabeceras={"Access-Control-Request-Method": "GET"},
    )
    sin_pedido = crear_scope(
        metodo="OPTIONS",
        cabeceras={"Origin": "http://localhost:4200"},
    )

    assert es_preflight(completo) is True
    assert es_preflight(sin_metodo) is False
    assert es_preflight(sin_origen) is False
    assert es_preflight(sin_pedido) is False


# ---------------------------------------------------------------------------
# Limitador con almacen falso
# ---------------------------------------------------------------------------


def _limitador(falso: AlmacenFalso, maximo: int = 3, ventana: int = 60) -> LimitadorTasa:
    return LimitadorTasa(
        almacen=falso,
        maximo=maximo,
        ventana_segundos=ventana,
        confiar_proxy=False,
    )


def test_permite_tres_y_rechaza_la_cuarta():
    async def escenario():
        falso = AlmacenFalso()
        limitador = _limitador(falso)
        scope = crear_scope()
        return [await limitador.evaluar(scope) for _ in range(4)]

    resultados = asyncio.run(escenario())

    assert [resultado.permitida for resultado in resultados] == [
        True, True, True, False,
    ]
    assert [resultado.restantes for resultado in resultados] == [2, 1, 0, 0]
    assert resultados[-1].reinicio_segundos == 60


def test_el_ttl_no_se_renueva_al_rechazar_y_el_reinicio_decrece():
    async def escenario():
        falso = AlmacenFalso()
        limitador = _limitador(falso)
        scope = crear_scope()
        primera = await limitador.evaluar(scope)
        for _ in range(2):
            await limitador.evaluar(scope)
        falso.avanzar(10)
        rechazada = await limitador.evaluar(scope)
        falso.avanzar(5)
        otra_rechazada = await limitador.evaluar(scope)
        return falso, primera, rechazada, otra_rechazada

    falso, primera, rechazada, otra_rechazada = asyncio.run(escenario())

    assert primera.reinicio_segundos == 60
    assert rechazada.permitida is False
    assert rechazada.reinicio_segundos == 50
    assert otra_rechazada.reinicio_segundos == 45
    assert falso.llamadas[-1][1] == 60000


def test_la_ventana_se_renueva_al_expirar():
    async def escenario():
        falso = AlmacenFalso()
        limitador = _limitador(falso, maximo=1)
        scope = crear_scope()
        permitidas = [(await limitador.evaluar(scope)).permitida]
        permitidas.append((await limitador.evaluar(scope)).permitida)
        falso.avanzar(60.1)
        permitidas.append((await limitador.evaluar(scope)).permitida)
        return permitidas

    assert asyncio.run(escenario()) == [True, False, True]


def test_la_clave_lleva_el_prefijo_y_la_ip():
    async def escenario():
        falso = AlmacenFalso()
        limitador = _limitador(falso)
        await limitador.evaluar(crear_scope())
        return falso.llamadas

    assert asyncio.run(escenario()) == [
        (f"{LIMITE_PREFIJO_CLAVE}203.0.113.7", 60000),
    ]
