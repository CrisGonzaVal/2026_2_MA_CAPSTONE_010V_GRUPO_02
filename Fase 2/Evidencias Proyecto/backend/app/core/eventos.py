"""Sobre interno y almacen de eventos de la Feature 028.

El sobre es el mensaje **interno** del bus: lleva la institucion, los dominios
de origen, el motivo y los duenos de pedidos para enrutar. Nunca se serializa
al frame del cliente: el suscriptor construye el frame por conexion con los
dominios visibles y sin identificadores.

La Feature 028 reutiliza el Redis efimero de la 025 como Pub/Sub. Este modulo
define el contrato del almacen (`AlmacenEventos`), el almacen nulo que instala
la suite heredada, el almacen Redis con clientes perezosos (publicador sync y
suscriptor async) y los seams de sustitucion. Nada se conecta al importar ni al
arrancar: el cliente de cada direccion se crea en el primer uso.
"""

import json
import logging
import time
from dataclasses import dataclass
from typing import Callable, Protocol

import redis
import redis.asyncio
from redis.asyncio.retry import Retry as RetryAsincrono
from redis.backoff import NoBackoff
from redis.retry import Retry

from app.core.config import settings
from app.core.observabilidad import identificador_actual

#: Prefijo del canal por institucion. La institucion sale solo de la identidad,
#: nunca de un parametro del cliente.
PREFIJO_CANAL = "compustock:eventos:"

#: Tope de la apertura de una conexion, igual que el publicador de la 025. Un
#: Redis inalcanzable debe caerse rapido: el fail-open no puede esperar.
TIEMPO_MAXIMO_CONEXION = 0.3

#: Cota de la publicacion (`socket_timeout`) y de las lecturas del suscriptor.
#: Es la cota dura del intento: no hay reintento de publicacion.
TIEMPO_MAXIMO_PUBLICACION = 0.5

#: Conexiones del publicador sync; el proceso comparte un unico cliente.
CONEXIONES_MAXIMAS_PUBLICADOR = 10

#: Un aviso de bus degradado como maximo cada 10 s, como el limite de la 025.
INTERVALO_AVISO_SEGUNDOS = 10.0

#: Logger del canal; T7 completa la linea semantica de apertura y cierre.
LOGGER_BUS = "compustock.tiempo_real"

#: Dominios de origen de la senal. `dashboard` no viaja en el sobre: es una
#: marca sintetica que el suscriptor anade por conexion.
DOMINIOS = frozenset({"pedidos", "inventario", "compras"})

#: Motivos de diagnostico del contrato. `cambio` es el unico que usa la marca
#: sintetica de dashboard; nunca revela el motivo real del dominio oculto.
MOTIVOS = frozenset(
    {
        "alta",
        "edicion",
        "aprobacion",
        "retiro",
        "confirmacion_entrega",
        "anulacion",
        "rechazo",
        "cambio_estado",
        "movimiento",
        "recepcion",
        "emision_oc",
        "facturacion_oc",
        "cancelacion_oc",
        "cambio",
    }
)


class ErrorBusEventos(RuntimeError):
    """El bus no esta disponible o entrego un mensaje que no es un sobre."""


@dataclass(frozen=True)
class SobreEvento:
    """Mensaje interno de invalidacion; nunca se serializa al cliente.

    Los conjuntos se copian a `frozenset` en la construccion para que el sobre
    sea realmente inmutable aunque el llamador pase un `set` o una lista.
    """

    institucion_id: str
    dominios: frozenset[str]
    motivo: str
    usuario_ids: frozenset[int] = frozenset()

    def __post_init__(self) -> None:
        if not isinstance(self.institucion_id, str) or not self.institucion_id.strip():
            raise ValueError("El sobre necesita un institucion_id no vacio.")
        object.__setattr__(self, "institucion_id", self.institucion_id.strip())
        object.__setattr__(self, "dominios", frozenset(self.dominios))
        object.__setattr__(self, "usuario_ids", frozenset(self.usuario_ids or ()))
        if not self.dominios <= DOMINIOS:
            raise ValueError(
                "Dominios desconocidos en el sobre: "
                f"{sorted(self.dominios - DOMINIOS)}"
            )
        if self.motivo not in MOTIVOS:
            raise ValueError(f"Motivo desconocido en el sobre: {self.motivo!r}")


def serializar_sobre(sobre: SobreEvento) -> str:
    """JSON interno con orden estable; los conjuntos viajan como listas."""
    return json.dumps(
        {
            "institucion_id": sobre.institucion_id,
            "dominios": sorted(sobre.dominios),
            "motivo": sobre.motivo,
            "usuario_ids": sorted(sobre.usuario_ids),
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def deserializar_sobre(mensaje: str | bytes) -> SobreEvento:
    """Reconstruye el sobre o levanta `ErrorBusEventos` si el payload no vale."""
    try:
        documento = json.loads(mensaje)
        if not isinstance(documento, dict):
            raise TypeError("El sobre debe ser un objeto JSON.")
        return SobreEvento(
            institucion_id=documento["institucion_id"],
            dominios=frozenset(documento["dominios"]),
            motivo=documento["motivo"],
            usuario_ids=frozenset(documento["usuario_ids"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ErrorBusEventos("El mensaje del bus no es un sobre valido.") from error


class SuscripcionEventos(Protocol):
    """Suscripcion viva a un canal; `recibir` devuelve `None` al vencer."""

    async def recibir(self, timeout: float | None = None) -> SobreEvento | None:
        """Siguiente sobre o `None` si no llego ninguno en `timeout`."""

    async def cerrar(self) -> None:
        """Libera el `PubSub` y sus conexiones."""


class AlmacenEventos(Protocol):
    """Contrato del bus: publicar es sync y best-effort; suscribir es async."""

    def publicar(self, sobre: SobreEvento) -> None:
        """Publica el sobre en el canal de su institucion."""

    async def suscribir(self, canal: str) -> SuscripcionEventos:
        """Abre una suscripcion al canal indicado."""

    async def cerrar(self) -> None:
        """Cierra los clientes del almacen."""


class _SuscripcionNula:
    """Suscripcion que nunca entrega nada y cuyo cierre es inocuo."""

    async def recibir(self, timeout: float | None = None) -> SobreEvento | None:
        return None

    async def cerrar(self) -> None:
        return None


class AlmacenNulo:
    """Almacen de la suite heredada: no publica, no conecta y no entrega.

    La suite lo instala como almacen vigente para que las mas de dos mil
    pruebas que mutan datos no abran conexiones ni paguen timeouts. La
    produccion usa `AlmacenRedisEventos`, creado de forma perezosa.
    """

    def publicar(self, sobre: SobreEvento) -> None:
        return None

    async def suscribir(self, canal: str) -> SuscripcionEventos:
        return _SuscripcionNula()

    async def cerrar(self) -> None:
        return None


class SuscripcionRedis:
    """Suscripcion viva sobre un `PubSub` asincrono de redis-py.

    `recibir` traduce el timeout del `PubSub` a `None` (no llego nada) y
    convierte cualquier fallo de Redis o un payload invalido en
    `ErrorBusEventos`, que el endpoint usa para anunciar la degradacion sin
    cerrar el HTTP.
    """

    def __init__(
        self,
        pubsub,
        *,
        al_cerrar: Callable[["SuscripcionRedis"], None] | None = None,
    ) -> None:
        self._pubsub = pubsub
        self._al_cerrar = al_cerrar
        self._cerrada = False

    async def recibir(self, timeout: float | None = None) -> SobreEvento | None:
        try:
            mensaje = await self._pubsub.get_message(
                ignore_subscribe_messages=True, timeout=timeout
            )
        except Exception as error:
            raise ErrorBusEventos(
                "El bus no entrego el mensaje."
            ) from error
        if mensaje is None:
            return None
        datos = mensaje.get("data") if isinstance(mensaje, dict) else None
        return deserializar_sobre(datos)

    async def cerrar(self) -> None:
        """Cierra el `PubSub` una sola vez; un fallo al cerrar no propaga."""
        if self._cerrada:
            return
        self._cerrada = True
        if self._al_cerrar is not None:
            self._al_cerrar(self)
        try:
            await self._pubsub.aclose()
        except Exception:
            pass


class AlmacenRedisEventos:
    """Bus real: publicador sync y suscriptor async sobre el mismo Redis.

    Los clientes se crean en el primer uso, nunca al construir el almacen ni al
    importar el modulo. El publicador comparte un unico cliente sync con
    `socket_timeout=0,5 s` (la cota del intento, sin reintento); el suscriptor
    abre un `PubSub` async por conexion SSE. Los fallos de publicacion se
    registran como maximo una vez cada 10 s y jamas se propagan a la mutacion.
    """

    def __init__(
        self,
        url: str,
        *,
        cliente_sync: redis.Redis | None = None,
        cliente_async: redis.asyncio.Redis | None = None,
        tiempo_maximo_publicacion: float = TIEMPO_MAXIMO_PUBLICACION,
        intervalo_aviso: float = INTERVALO_AVISO_SEGUNDOS,
        reloj: Callable[[], float] = time.monotonic,
    ) -> None:
        self._url = url
        self._cliente_sync = cliente_sync
        self._cliente_async = cliente_async
        self._tiempo_maximo_publicacion = tiempo_maximo_publicacion
        self._intervalo_aviso = intervalo_aviso
        self._reloj = reloj
        self._ultimo_aviso = float("-inf")
        self._suscripciones: set[SuscripcionRedis] = set()

    # -- Publicacion (sincrona, best-effort) --------------------------------

    def _crear_cliente_sync(self) -> redis.Redis:
        return redis.Redis.from_url(
            self._url,
            socket_connect_timeout=TIEMPO_MAXIMO_CONEXION,
            socket_timeout=self._tiempo_maximo_publicacion,
            max_connections=CONEXIONES_MAXIMAS_PUBLICADOR,
            retry=Retry(NoBackoff(), 0),
            decode_responses=True,
        )

    def _obtener_cliente_sync(self) -> redis.Redis:
        if self._cliente_sync is None:
            self._cliente_sync = self._crear_cliente_sync()
        return self._cliente_sync

    def publicar(self, sobre: SobreEvento) -> None:
        """Intenta publicar; un fallo o un timeout solo deja un aviso."""
        try:
            canal = canal_de_institucion(sobre.institucion_id)
            mensaje = serializar_sobre(sobre)
            self._obtener_cliente_sync().publish(canal, mensaje)
        except Exception as error:
            self._avisar(error)

    def _avisar(self, error: Exception) -> None:
        """Avisa del bus degradado como maximo una vez por intervalo."""
        ahora = self._reloj()
        if ahora - self._ultimo_aviso < self._intervalo_aviso:
            return
        self._ultimo_aviso = ahora
        logging.getLogger(LOGGER_BUS).warning(
            "bus_eventos_degradado",
            extra={
                "request_id": identificador_actual(),
                "error_type": type(error).__name__,
            },
        )

    # -- Suscripcion (asincrona) --------------------------------------------

    def _crear_cliente_async(self) -> redis.asyncio.Redis:
        return redis.asyncio.Redis.from_url(
            self._url,
            socket_connect_timeout=TIEMPO_MAXIMO_CONEXION,
            socket_timeout=TIEMPO_MAXIMO_PUBLICACION,
            retry=RetryAsincrono(NoBackoff(), 0),
            decode_responses=True,
        )

    def _obtener_cliente_async(self) -> redis.asyncio.Redis:
        if self._cliente_async is None:
            self._cliente_async = self._crear_cliente_async()
        return self._cliente_async

    async def suscribir(self, canal: str) -> SuscripcionEventos:
        pubsub = self._obtener_cliente_async().pubsub()
        try:
            await pubsub.subscribe(canal)
        except Exception as error:
            try:
                await pubsub.aclose()
            except Exception:
                pass
            raise ErrorBusEventos(
                "No se pudo abrir la suscripcion al bus."
            ) from error
        suscripcion = SuscripcionRedis(
            pubsub, al_cerrar=self._suscripciones.discard
        )
        self._suscripciones.add(suscripcion)
        return suscripcion

    # -- Cierre -------------------------------------------------------------

    async def cerrar(self) -> None:
        """Cierra suscripciones y clientes; idempotente y sin propagar."""
        for suscripcion in list(self._suscripciones):
            await suscripcion.cerrar()
        self._suscripciones.clear()

        cliente_async, self._cliente_async = self._cliente_async, None
        if cliente_async is not None:
            try:
                await cliente_async.aclose()
            except Exception:
                pass

        cliente_sync, self._cliente_sync = self._cliente_sync, None
        if cliente_sync is not None:
            try:
                cliente_sync.close()
            except Exception:
                pass


#: Almacen vigente del proceso. Los tests lo sustituyen con
#: `configurar_almacen`; la produccion crea el Redis en el primer acceso.
_ALMACEN: AlmacenEventos | None = None


def configurar_almacen(almacen: AlmacenEventos) -> None:
    """Sustituye el almacen global (suite, bus falso o Redis gated)."""
    global _ALMACEN
    _ALMACEN = almacen


def obtener_almacen() -> AlmacenEventos:
    """Almacen vigente; si nadie lo sustituyo, el Redis perezoso de produccion.

    Construir el almacen no abre sockets: el cliente sync se crea al publicar
    y el async al suscribir.
    """
    global _ALMACEN
    if _ALMACEN is None:
        _ALMACEN = AlmacenRedisEventos(settings.REDIS_URL)
    return _ALMACEN


async def cerrar_almacen() -> None:
    """Cierra el almacen vigente al apagar el proceso, si se llego a crear."""
    if _ALMACEN is not None:
        await _ALMACEN.cerrar()


def canal_de_institucion(institucion_id: str) -> str:
    """Canal unico por institucion; el aislamiento es estructural."""
    if not isinstance(institucion_id, str) or not institucion_id.strip():
        raise ValueError("El identificador de institucion no puede estar vacio.")
    return f"{PREFIJO_CANAL}{institucion_id.strip()}"
