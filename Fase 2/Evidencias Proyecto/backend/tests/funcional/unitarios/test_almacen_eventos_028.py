"""Pruebas unitarias del almacen Redis de eventos (Feature 028, T3).

Fijan el contrato del publicador sincrono y del suscriptor asincrono **sin
abrir Redis**: serializacion y canal, fail-open con aviso acotado a 10 s, cota
del cliente sync (`socket_timeout` 0,5 s y `socket_connect_timeout` 0,3 s),
suscripcion que deserializa y `cerrar` idempotente. El unico escenario de red
usa la direccion reservada RFC 5737 `192.0.2.1`, igual que la suite de la 025:
el cliente corta por timeout y no depende de que haya un Redis levantado.

Sin `pytest-asyncio`: cada escenario asincrono se envuelve en `asyncio.run`.
"""

import asyncio
import json
import time

import pytest
import redis
import redis.asyncio
from redis.asyncio.retry import Retry as RetryAsincrono
from redis.backoff import NoBackoff
from redis.retry import Retry

from app.core import eventos
from app.core.eventos import (
    AlmacenRedisEventos,
    ErrorBusEventos,
    SobreEvento,
    canal_de_institucion,
    serializar_sobre,
)
from tests.funcional.integracion.soporte_observabilidad_024 import capturar_logs

URL = "redis://127.0.0.1:6380/0"

#: Canal de la institucion de prueba; el aislamiento es estructural.
CANAL = canal_de_institucion("INST-001")


def _sobre(**cambios) -> SobreEvento:
    datos = {
        "institucion_id": "INST-001",
        "dominios": frozenset({"pedidos"}),
        "motivo": "alta",
        "usuario_ids": frozenset({7}),
    }
    datos.update(cambios)
    return SobreEvento(**datos)


class _RelojFalso:
    """Reloj monotono inyectable: mueve el tiempo sin dormir la suite."""

    def __init__(self, ahora: float = 100.0) -> None:
        self.ahora = ahora

    def __call__(self) -> float:
        return self.ahora

    def avanzar(self, segundos: float) -> None:
        self.ahora += segundos


class _ClienteSyncFalso:
    """Doble del cliente `redis.Redis`; registra publicaciones y cierre."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.publicados: list[tuple[str, str]] = []
        self.cerrado = False

    def publish(self, canal: str, mensaje: str) -> int:
        if self.error is not None:
            raise self.error
        self.publicados.append((canal, mensaje))
        return 1

    def close(self) -> None:
        self.cerrado = True


class _PubSubFalso:
    """Doble del `PubSub` asincrono: mensajes en cola, timeout o error."""

    def __init__(
        self,
        mensajes: list[dict] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.mensajes = list(mensajes or [])
        self.error = error
        self.canales: list[str] = []
        self.llamadas: list[dict] = []
        self.cerrado = False

    async def subscribe(self, canal: str) -> None:
        self.canales.append(canal)

    async def get_message(
        self, ignore_subscribe_messages: bool = False, timeout: float | None = 0.0
    ) -> dict | None:
        self.llamadas.append(
            {
                "ignore_subscribe_messages": ignore_subscribe_messages,
                "timeout": timeout,
            }
        )
        if self.error is not None:
            raise self.error
        return self.mensajes.pop(0) if self.mensajes else None

    async def aclose(self) -> None:
        self.cerrado = True


class _PubSubQueFallaAlSuscribir(_PubSubFalso):
    async def subscribe(self, canal: str) -> None:
        self.canales.append(canal)
        raise ConnectionError("no se pudo suscribir")


class _ClienteAsyncFalso:
    """Doble del cliente `redis.asyncio.Redis`; entrega su `PubSub`."""

    def __init__(self, pubsub: _PubSubFalso) -> None:
        self.pubsub_creado = pubsub
        self.cerrado = False

    def pubsub(self) -> _PubSubFalso:
        return self.pubsub_creado

    async def aclose(self) -> None:
        self.cerrado = True


# ---------------------------------------------------------------------------
# Publicacion: serializacion, canal y fail-open
# ---------------------------------------------------------------------------


def test_publicar_serializa_el_sobre_en_el_canal_de_su_institucion():
    cliente = _ClienteSyncFalso()
    almacen = AlmacenRedisEventos(URL, cliente_sync=cliente)
    sobre = _sobre(dominios=frozenset({"pedidos", "inventario"}), usuario_ids={3, 7})

    almacen.publicar(sobre)

    assert cliente.publicados == [(CANAL, serializar_sobre(sobre))]
    documento = json.loads(cliente.publicados[0][1])
    assert documento["institucion_id"] == "INST-001"
    assert documento["dominios"] == ["inventario", "pedidos"]
    assert documento["usuario_ids"] == [3, 7]


def test_publicar_no_propaga_el_fallo_y_avisa_como_maximo_cada_diez_segundos():
    reloj = _RelojFalso()
    cliente = _ClienteSyncFalso(error=ConnectionError("redis no responde"))
    almacen = AlmacenRedisEventos(
        URL, cliente_sync=cliente, reloj=reloj, intervalo_aviso=10.0
    )

    with capturar_logs() as lineas:
        almacen.publicar(_sobre())
        almacen.publicar(_sobre())
        reloj.avanzar(9.9)
        almacen.publicar(_sobre())
        reloj.avanzar(0.2)
        almacen.publicar(_sobre())

    avisos = [
        json.loads(linea)
        for linea in lineas
        if "bus_eventos_degradado" in linea
    ]
    assert len(avisos) == 2
    assert avisos[0]["error_type"] == "ConnectionError"
    assert "redis no responde" not in "".join(lineas)
    assert "Traceback" not in "".join(lineas)


def test_publicar_traga_el_timeout_del_socket_y_solo_intenta_una_vez():
    cliente = _ClienteSyncFalso(error=redis.exceptions.TimeoutError("agotado"))
    almacen = AlmacenRedisEventos(URL, cliente_sync=cliente)

    with capturar_logs():
        almacen.publicar(_sobre())

    assert cliente.publicados == []


def test_la_cota_de_publicacion_es_inyectable_sin_dormir_en_la_suite(monkeypatch):
    capturado: dict = {}
    cliente = _ClienteSyncFalso()

    def from_url(url: str, **kwargs):
        capturado["url"] = url
        capturado.update(kwargs)
        return cliente

    monkeypatch.setattr(redis.Redis, "from_url", from_url)
    almacen = AlmacenRedisEventos(URL, tiempo_maximo_publicacion=0.05)

    almacen.publicar(_sobre())

    assert capturado["url"] == URL
    assert capturado["socket_timeout"] == 0.05


def test_un_redis_que_no_responde_no_bloquea_mas_alla_de_la_cota():
    # 192.0.2.1 es la red de documentacion RFC 5737: no hay servidor que
    # conteste. El cliente corta en 0,3 s de conexion; nunca espera de mas.
    almacen = AlmacenRedisEventos("redis://192.0.2.1:6399/0")
    inicio = time.monotonic()

    with capturar_logs():
        almacen.publicar(_sobre())

    duracion = time.monotonic() - inicio
    asyncio.run(almacen.cerrar())
    assert duracion < 1.0


# ---------------------------------------------------------------------------
# Cliente sync: tiempos, reintento y creacion perezosa
# ---------------------------------------------------------------------------


def test_el_cliente_sync_usa_los_tiempos_y_el_reintento_del_plan(monkeypatch):
    capturado: dict = {}
    cliente = _ClienteSyncFalso()

    def from_url(url: str, **kwargs):
        capturado["url"] = url
        capturado.update(kwargs)
        return cliente

    monkeypatch.setattr(redis.Redis, "from_url", from_url)

    AlmacenRedisEventos(URL).publicar(_sobre())

    assert capturado["socket_connect_timeout"] == 0.3
    assert capturado["socket_timeout"] == 0.5
    assert capturado["max_connections"] == 10
    assert capturado["decode_responses"] is True
    reintento = capturado["retry"]
    assert isinstance(reintento, Retry)
    assert reintento._retries == 0
    assert isinstance(reintento._backoff, NoBackoff)


def test_construir_el_almacen_no_crea_ningun_cliente(monkeypatch):
    def crear_prohibido(*_args, **_kwargs):
        raise AssertionError("El almacen no debe crear clientes al construirse")

    monkeypatch.setattr(redis.Redis, "from_url", crear_prohibido)
    monkeypatch.setattr(redis.asyncio.Redis, "from_url", crear_prohibido)

    almacen = AlmacenRedisEventos(URL)
    asyncio.run(almacen.cerrar())
    asyncio.run(almacen.cerrar())


def test_el_cliente_async_se_crea_perezoso_al_suscribir(monkeypatch):
    capturado: dict = {}
    pubsub = _PubSubFalso()
    cliente = _ClienteAsyncFalso(pubsub)

    def from_url(url: str, **kwargs):
        capturado["url"] = url
        capturado.update(kwargs)
        return cliente

    monkeypatch.setattr(redis.asyncio.Redis, "from_url", from_url)
    almacen = AlmacenRedisEventos(URL)

    async def escenario():
        suscripcion = await almacen.suscribir(CANAL)
        await suscripcion.cerrar()
        await almacen.cerrar()

    asyncio.run(escenario())

    assert capturado["url"] == URL
    assert capturado["socket_connect_timeout"] == 0.3
    assert capturado["decode_responses"] is True
    retry = capturado["retry"]
    assert isinstance(retry, RetryAsincrono)
    assert retry._retries == 0
    assert isinstance(retry._backoff, NoBackoff)


def test_obtener_almacen_crea_el_redis_perezoso_sin_abrir_clientes(monkeypatch):
    monkeypatch.setattr(eventos, "_ALMACEN", None)

    def crear_prohibido(*_args, **_kwargs):
        raise AssertionError("obtener_almacen no debe abrir clientes")

    monkeypatch.setattr(redis.Redis, "from_url", crear_prohibido)
    monkeypatch.setattr(redis.asyncio.Redis, "from_url", crear_prohibido)

    almacen = eventos.obtener_almacen()

    assert isinstance(almacen, AlmacenRedisEventos)
    assert eventos.obtener_almacen() is almacen


# ---------------------------------------------------------------------------
# Suscripcion: deserializacion, timeout y error del cliente
# ---------------------------------------------------------------------------


def test_suscribir_entrega_el_sobre_deserializado_y_none_al_vencer():
    sobre = _sobre()
    pubsub = _PubSubFalso(
        mensajes=[
            {
                "type": "message",
                "channel": CANAL,
                "data": serializar_sobre(sobre),
            }
        ]
    )
    almacen = AlmacenRedisEventos(
        URL, cliente_async=_ClienteAsyncFalso(pubsub)
    )

    async def escenario():
        suscripcion = await almacen.suscribir(CANAL)
        try:
            recibido = await suscripcion.recibir(timeout=0.01)
            vencido = await suscripcion.recibir(timeout=0.01)
            return recibido, vencido
        finally:
            await suscripcion.cerrar()
            await almacen.cerrar()

    recibido, vencido = asyncio.run(escenario())

    assert recibido == sobre
    assert vencido is None
    assert pubsub.canales == [CANAL]
    assert pubsub.llamadas[0] == {
        "ignore_subscribe_messages": True,
        "timeout": 0.01,
    }


def test_recibir_envuelve_el_error_del_cliente_en_error_bus_eventos():
    pubsub = _PubSubFalso(error=ConnectionError("caido"))
    almacen = AlmacenRedisEventos(
        URL, cliente_async=_ClienteAsyncFalso(pubsub)
    )

    async def escenario():
        suscripcion = await almacen.suscribir(CANAL)
        try:
            await suscripcion.recibir(timeout=0.01)
        finally:
            await suscripcion.cerrar()
            await almacen.cerrar()

    with pytest.raises(ErrorBusEventos):
        asyncio.run(escenario())


def test_suscribir_envuelve_el_error_del_cliente_y_cierra_el_pubsub():
    pubsub = _PubSubQueFallaAlSuscribir()
    almacen = AlmacenRedisEventos(
        URL, cliente_async=_ClienteAsyncFalso(pubsub)
    )

    with pytest.raises(ErrorBusEventos):
        asyncio.run(almacen.suscribir(CANAL))

    assert pubsub.cerrado is True
    asyncio.run(almacen.cerrar())


def test_un_mensaje_que_no_es_un_sobre_levanta_error_bus_eventos():
    pubsub = _PubSubFalso(
        mensajes=[{"type": "message", "channel": CANAL, "data": "no-json"}]
    )
    almacen = AlmacenRedisEventos(
        URL, cliente_async=_ClienteAsyncFalso(pubsub)
    )

    async def escenario():
        suscripcion = await almacen.suscribir(CANAL)
        try:
            await suscripcion.recibir(timeout=0.01)
        finally:
            await suscripcion.cerrar()
            await almacen.cerrar()

    with pytest.raises(ErrorBusEventos):
        asyncio.run(escenario())


# ---------------------------------------------------------------------------
# Cierre
# ---------------------------------------------------------------------------


def test_cerrar_es_idempotente_y_cierra_pubsub_y_clientes():
    pubsub = _PubSubFalso()
    cliente_async = _ClienteAsyncFalso(pubsub)
    cliente_sync = _ClienteSyncFalso()
    almacen = AlmacenRedisEventos(
        URL, cliente_sync=cliente_sync, cliente_async=cliente_async
    )

    async def escenario():
        await almacen.suscribir(CANAL)
        await almacen.cerrar()
        await almacen.cerrar()

    asyncio.run(escenario())

    assert pubsub.cerrado is True
    assert cliente_async.cerrado is True
    assert cliente_sync.cerrado is True


def test_cerrar_sin_clientes_creados_no_lanza_ni_los_crea(monkeypatch):
    def crear_prohibido(*_args, **_kwargs):
        raise AssertionError("cerrar no debe crear clientes")

    monkeypatch.setattr(redis.Redis, "from_url", crear_prohibido)
    monkeypatch.setattr(redis.asyncio.Redis, "from_url", crear_prohibido)
    almacen = AlmacenRedisEventos(URL)

    asyncio.run(almacen.cerrar())
    asyncio.run(almacen.cerrar())
