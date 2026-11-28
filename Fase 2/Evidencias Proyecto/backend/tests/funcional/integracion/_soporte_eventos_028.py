"""Bus falso de eventos de la Feature 028, compartido por T4/T5/T8.

Implementa el contrato completo de `AlmacenEventos` en memoria: `publicar`
guarda el sobre en `publicados` y lo reparte a las suscripciones vivas;
`suscribir` devuelve una suscripción con su propia cola `asyncio.Queue` que
entrega los sobres iniciales del escenario y vence con `None` en el timeout;
`cerrar` cierra las suscripciones y el almacén sin tocar la red.

No es un archivo de tests ni un mock parcial: el endpoint SSE de T5 puede
suscribirse a él y la publicación de T8 puede inspeccionar `publicados`.
"""

import asyncio
from contextlib import contextmanager

from app.core import eventos as bus_eventos
from app.core.config import settings
from app.core.eventos import SobreEvento
from app.services import evento_service


class SuscripcionBusFalso:
    """Suscripción en memoria con una cola de sobres y cierre idempotente."""

    def __init__(self, canal: str, eventos=()) -> None:
        self.canal = canal
        self.cola: asyncio.Queue[SobreEvento] = asyncio.Queue()
        self.cerrada = False
        for sobre in eventos:
            self.encolar(sobre)

    def encolar(self, sobre: SobreEvento) -> None:
        """Encola un sobre si la suscripción sigue viva."""
        if not self.cerrada:
            self.cola.put_nowait(sobre)

    async def recibir(self, timeout: float | None = None) -> SobreEvento | None:
        """Siguiente sobre de la cola o `None` si vence el timeout."""
        if self.cerrada:
            return None
        try:
            return await asyncio.wait_for(self.cola.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None

    async def cerrar(self) -> None:
        """Marca la suscripción como cerrada; no hay recurso que liberar."""
        self.cerrada = True


class BusFalso:
    """`AlmacenEventos` en memoria para las pruebas de publicación y del flujo.

    `error_al_publicar` simula un bus caído: `publicar` levanta la excepción
    antes de guardar el sobre, de modo que una prueba compruebe que el llamador
    la traga y no deja un sobre a medias.
    """

    def __init__(
        self,
        eventos=(),
        *,
        error_al_publicar: Exception | None = None,
    ) -> None:
        self.publicados: list[SobreEvento] = []
        self.suscripciones: list[SuscripcionBusFalso] = []
        self.error_al_publicar = error_al_publicar
        self.cerrado = False
        self._eventos_iniciales = list(eventos)

    def publicar(self, sobre: SobreEvento) -> None:
        """Guarda el sobre y lo reparte a las suscripciones vivas."""
        if self.error_al_publicar is not None:
            raise self.error_al_publicar
        self.publicados.append(sobre)
        for suscripcion in list(self.suscripciones):
            suscripcion.encolar(sobre)

    async def suscribir(self, canal: str) -> SuscripcionBusFalso:
        """Abre una suscripción al canal con los eventos iniciales del escenario."""
        suscripcion = SuscripcionBusFalso(canal, self._eventos_iniciales)
        self.suscripciones.append(suscripcion)
        return suscripcion

    async def cerrar(self) -> None:
        """Cierra las suscripciones abiertas y marca el almacén como cerrado."""
        self.cerrado = True
        for suscripcion in list(self.suscripciones):
            await suscripcion.cerrar()
        self.suscripciones.clear()

    @property
    def canales(self) -> list[str]:
        """Canales suscritos, en orden de apertura (aislamiento por institución)."""
        return [suscripcion.canal for suscripcion in self.suscripciones]


@contextmanager
def instalar_bus(
    *,
    eventos_iniciales=(),
    habilitado: bool = True,
    error_al_publicar: Exception | None = None,
):
    """Instala un `BusFalso` y enciende el canal durante el contexto.

    El conftest deja `TIEMPO_REAL_HABILITADO` apagado y el `AlmacenNulo`
    vigente; este contexto es el unico punto que enciende el canal en las
    pruebas del 028 y restaura el almacen, el interruptor y el reloj del aviso
    al salir, de modo que un escenario de fallo no contamine al siguiente.
    Devuelve el `BusFalso` instalado.
    """
    bus = BusFalso(eventos_iniciales, error_al_publicar=error_al_publicar)
    almacen_previo = bus_eventos.obtener_almacen()
    habilitado_previo = settings.TIEMPO_REAL_HABILITADO
    aviso_previo = evento_service._ultimo_aviso
    bus_eventos.configurar_almacen(bus)
    settings.TIEMPO_REAL_HABILITADO = habilitado
    evento_service._ultimo_aviso = float("-inf")
    try:
        yield bus
    finally:
        evento_service._ultimo_aviso = aviso_previo
        settings.TIEMPO_REAL_HABILITADO = habilitado_previo
        bus_eventos.configurar_almacen(almacen_previo)
