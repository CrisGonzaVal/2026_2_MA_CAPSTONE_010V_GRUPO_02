"""Nucleo del limite de tasa distribuido de la Feature 025.

La ventana es fija por IP y se ancla al primer acierto. El script Lua hace
atomico el incremento y la expiracion, de modo que varios procesos comparten el
mismo contador sin carreras. La IP solo vive en la clave de Redis: no se
registra, no se etiqueta y no viaja en la respuesta.
"""

import asyncio
import ipaddress
import logging
import math
import time
from contextlib import suppress
from dataclasses import dataclass
from typing import Protocol

import redis.asyncio
from redis.asyncio.retry import Retry
from redis.backoff import NoBackoff

from app.core.metricas import registrar_limite
from app.core.observabilidad import LOGGER_LIMITE, identificador_actual

#: Prefijo de las claves del limitador. Incluye el nombre de la aplicacion para
#: no colisionar con otras claves del mismo Redis.
LIMITE_PREFIJO_CLAVE = "compustock:limite:"

#: Mismo texto que el 429 del borde nginx (Feature 024), para que el cliente
#: reciba una respuesta uniforme venga de donde venga el rechazo.
TEXTO_LIMITE = "Demasiadas peticiones. Intente nuevamente en unos segundos."

#: IP usada cuando el `scope` no trae par TCP. Agrupa a los clientes sin
#: direccion en un unico presupuesto en vez de fallar.
IP_RESERVADA = "ip-desconocida"

MILISEGUNDOS_POR_SEGUNDO = 1000

#: Cota dura de una evaluacion, independiente de los timeouts del cliente. Con
#: Redis en un agujero negro el fail-open sigue siendo una cota.
TIEMPO_MAXIMO_EVALUACION = 0.5

SCRIPT_LUA = """
local actual = redis.call('INCR', KEYS[1])
local ttl = redis.call('PTTL', KEYS[1])
if actual == 1 or ttl < 0 then
    redis.call('PEXPIRE', KEYS[1], ARGV[1])
    ttl = tonumber(ARGV[1])
end
return {actual, ttl}
"""


def resolver_ip(scope: dict, confiar_proxy: bool) -> str:
    """IP del cliente; `X-Real-IP` solo si se confia en el proxy.

    `X-Forwarded-For` no se lee nunca: es una lista que el cliente puede
    falsificar y nginx ya deja la direccion real en `X-Real-IP`.
    """
    if confiar_proxy:
        for nombre, valor in scope.get("headers", []):
            if nombre.lower() != b"x-real-ip":
                continue
            try:
                direccion = ipaddress.ip_address(
                    valor.decode("latin-1").strip()
                )
            except ValueError:
                continue
            return str(direccion)

    par = scope.get("client")
    if not par or not par[0]:
        return IP_RESERVADA
    return str(par[0])


def es_ruta_limitada(camino: str) -> bool:
    """`/api/v1` o cualquier subruta, siempre por segmento."""
    return camino == "/api/v1" or camino.startswith("/api/v1/")


def es_preflight(scope: dict) -> bool:
    """`OPTIONS` con `Origin` y `Access-Control-Request-Method`."""
    if scope.get("method") != "OPTIONS":
        return False
    nombres = {nombre.lower() for nombre, _ in scope.get("headers", [])}
    return (
        b"origin" in nombres
        and b"access-control-request-method" in nombres
    )


class AlmacenLimite(Protocol):
    """Contrato minimo que consumen el limitador y sus dobles de prueba."""

    async def registrar(self, clave: str, ventana_ms: int) -> tuple[int, int]:
        """Incrementa y devuelve `(contador, ttl_restante_ms)`."""

    async def cerrar(self) -> None:
        """Libera las conexiones del almacen."""


class AlmacenRedis:
    """Almacen real sobre Redis, con cliente creado en la primera evaluacion."""

    def __init__(self, url: str) -> None:
        self._url = url
        self._cliente: redis.asyncio.Redis | None = None

    def _obtener_cliente(self) -> redis.asyncio.Redis:
        if self._cliente is None:
            # `from_url` no acepta `timeout` en redis-py 8.1.0: ese nombre se
            # reenvia al constructor de la conexion y lanza TypeError. La cota
            # del *pool* la impone `asyncio.wait_for` en `LimitadorTasa.evaluar`.
            self._cliente = redis.asyncio.Redis.from_url(
                self._url,
                socket_connect_timeout=0.2,
                socket_timeout=0.2,
                max_connections=20,
                retry=Retry(NoBackoff(), 0),
            )
        return self._cliente

    async def registrar(self, clave: str, ventana_ms: int) -> tuple[int, int]:
        respuesta = await self._obtener_cliente().eval(
            SCRIPT_LUA, 1, clave, ventana_ms
        )
        if not isinstance(respuesta, (list, tuple)) or len(respuesta) != 2:
            raise ValueError("respuesta inesperada del script de limite")
        actual, ttl_ms = int(respuesta[0]), int(respuesta[1])
        if actual < 1 or ttl_ms < 0:
            raise ValueError("valores fuera de rango del script de limite")
        return actual, ttl_ms

    async def cerrar(self) -> None:
        if self._cliente is not None:
            await self._cliente.aclose()


@dataclass(frozen=True)
class ResultadoLimite:
    """Decision del limitador para una peticion concreta."""

    permitida: bool
    restantes: int
    reinicio_segundos: int


class LimitadorTasa:
    """Ventana fija por IP sobre un `AlmacenLimite`."""

    def __init__(
        self,
        almacen: AlmacenLimite,
        maximo: int,
        ventana_segundos: int,
        confiar_proxy: bool,
        intervalo_aviso: float = 10.0,
    ) -> None:
        self._almacen = almacen
        self.maximo = maximo
        self._ventana_segundos = ventana_segundos
        self._confiar_proxy = confiar_proxy
        self._intervalo_aviso = intervalo_aviso
        self._ultimo_aviso = float("-inf")

    async def evaluar(self, scope: dict) -> ResultadoLimite:
        clave = (
            f"{LIMITE_PREFIJO_CLAVE}"
            f"{resolver_ip(scope, self._confiar_proxy)}"
        )
        ventana_ms = self._ventana_segundos * MILISEGUNDOS_POR_SEGUNDO
        try:
            actual, ttl_ms = await asyncio.wait_for(
                self._almacen.registrar(clave, ventana_ms),
                timeout=TIEMPO_MAXIMO_EVALUACION,
            )
            if actual < 1 or ttl_ms < 0:
                raise ValueError("valores fuera de rango del script de limite")
        except Exception as error:
            # Fail-open: sin Redis la aplicacion sigue operando; el limite se
            # degrada, no se rompe. No se registra IP, host, mensaje ni traza.
            self._registrar("error")
            self._avisar(error)
            return ResultadoLimite(
                permitida=True,
                restantes=self.maximo,
                reinicio_segundos=self._ventana_segundos,
            )

        permitida = actual <= self.maximo
        restantes = max(0, self.maximo - actual)
        reinicio = max(
            1,
            min(
                self._ventana_segundos,
                math.ceil(ttl_ms / MILISEGUNDOS_POR_SEGUNDO),
            ),
        )
        self._registrar("permitida" if permitida else "limitada")
        return ResultadoLimite(
            permitida=permitida,
            restantes=restantes,
            reinicio_segundos=reinicio,
        )

    @staticmethod
    def _registrar(resultado: str) -> None:
        """Instrumentacion best-effort: nunca convierte una decision en 5xx."""
        with suppress(Exception):
            registrar_limite(resultado)

    def _avisar(self, error: Exception) -> None:
        """Avisa del limite degradado como maximo una vez por intervalo."""
        ahora = time.monotonic()
        if ahora - self._ultimo_aviso < self._intervalo_aviso:
            return
        self._ultimo_aviso = ahora
        logging.getLogger(LOGGER_LIMITE).warning(
            "limite_tasa_degradado",
            extra={
                "request_id": identificador_actual(),
                "error_type": type(error).__name__,
            },
        )
