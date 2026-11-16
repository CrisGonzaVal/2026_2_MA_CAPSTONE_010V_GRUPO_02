"""AC-4 y AC-16: semantica real del limite contra Redis (suite gated).

Requiere `REDIS_TEST_URL` apuntando a la base 15 del Redis de Compose
(`redis://127.0.0.1:6380/15`); sin ella las pruebas se omiten. Cada escenario
vacia su base al empezar y al terminar y nunca toca la base 0 de la aplicacion.
Sin `pytest-asyncio`: cada prueba envuelve su escenario en `asyncio.run`.
"""

import asyncio
import os

import pytest
import redis.asyncio

from app.core.limite_tasa import AlmacenRedis, LimitadorTasa
from tests.soporte_limite_tasa_025 import crear_scope

URL = os.environ.get("REDIS_TEST_URL")

CLAVE = "compustock:limite:203.0.113.7"

pytestmark = pytest.mark.skipif(
    not URL,
    reason="REDIS_TEST_URL no definida: prueba gated de Redis",
)


def _url_de_prueba() -> str:
    """La suite solo corre contra la base 15, nunca contra la 0."""
    if not URL.endswith("/15"):
        pytest.skip("REDIS_TEST_URL debe apuntar a la base 15 de pruebas")
    return URL


async def _abrir_explorador():
    cliente = redis.asyncio.Redis.from_url(
        _url_de_prueba(), socket_connect_timeout=1, socket_timeout=1
    )
    await cliente.flushdb()
    return cliente


def test_tres_permitidas_cuarta_rechazada_y_ttl():
    async def escenario():
        explorador = await _abrir_explorador()
        almacen = AlmacenRedis(_url_de_prueba())
        limitador = LimitadorTasa(almacen, 3, 1, False)
        scope = crear_scope(ip="203.0.113.7")
        try:
            resultados = [await limitador.evaluar(scope) for _ in range(4)]
            ttl = await explorador.pttl(CLAVE)
            existe = await explorador.exists(CLAVE)
        finally:
            await almacen.cerrar()
            await explorador.flushdb()
            await explorador.aclose()
        return resultados, ttl, existe

    resultados, ttl, existe = asyncio.run(escenario())

    assert [resultado.permitida for resultado in resultados] == [
        True, True, True, False,
    ]
    assert resultados[-1].restantes == 0
    assert 1 <= ttl <= 1000
    assert existe == 1


def test_reinicio_por_del_expiracion_y_ttl_que_no_se_renueva():
    async def escenario():
        explorador = await _abrir_explorador()
        almacen = AlmacenRedis(_url_de_prueba())
        limitador = LimitadorTasa(almacen, 1, 2, False)
        scope = crear_scope(ip="203.0.113.7")
        try:
            permitida = await limitador.evaluar(scope)
            rechazada = await limitador.evaluar(scope)
            ttl_antes = await explorador.pttl(CLAVE)
            await asyncio.sleep(1.1)
            otra_rechazada = await limitador.evaluar(scope)
            ttl_despues = await explorador.pttl(CLAVE)

            await explorador.delete(CLAVE)
            tras_del = await limitador.evaluar(scope)

            await asyncio.sleep(2.1)
            tras_expiracion = await limitador.evaluar(scope)
        finally:
            await almacen.cerrar()
            await explorador.flushdb()
            await explorador.aclose()
        return (
            permitida,
            rechazada,
            otra_rechazada,
            ttl_antes,
            ttl_despues,
            tras_del,
            tras_expiracion,
        )

    (
        permitida,
        rechazada,
        otra_rechazada,
        ttl_antes,
        ttl_despues,
        tras_del,
        tras_expiracion,
    ) = asyncio.run(escenario())

    assert permitida.permitida is True
    assert rechazada.permitida is False
    assert otra_rechazada.permitida is False
    assert rechazada.reinicio_segundos == 2
    assert otra_rechazada.reinicio_segundos == 1
    assert otra_rechazada.reinicio_segundos <= rechazada.reinicio_segundos
    assert ttl_despues <= ttl_antes
    assert tras_del.permitida is True
    assert tras_expiracion.permitida is True


def test_veinte_evaluaciones_concurrentes_reparten_diez_y_diez():
    async def escenario():
        explorador = await _abrir_explorador()
        almacen = AlmacenRedis(_url_de_prueba())
        limitador = LimitadorTasa(almacen, 10, 5, False)
        scope = crear_scope(ip="203.0.113.7")
        try:
            resultados = await asyncio.gather(
                *[limitador.evaluar(scope) for _ in range(20)]
            )
        finally:
            await almacen.cerrar()
            await explorador.flushdb()
            await explorador.aclose()
        return resultados

    resultados = asyncio.run(escenario())

    permitidas = [resultado for resultado in resultados if resultado.permitida]
    rechazadas = [resultado for resultado in resultados if not resultado.permitida]
    assert len(permitidas) == 10
    assert len(rechazadas) == 10
    assert all(resultado.restantes == 0 for resultado in rechazadas)
