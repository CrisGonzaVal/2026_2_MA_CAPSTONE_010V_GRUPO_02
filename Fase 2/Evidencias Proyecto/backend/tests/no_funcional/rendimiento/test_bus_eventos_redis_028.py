"""Suite gated del bus de eventos sobre Redis real (Feature 028, T3/T14).

AC-8 (fail-open), AC-23 (dos instancias comparten el bus) y AC-25 (sin
dependencias nuevas). Con `REDIS_TEST_URL` apuntando a la base 15 del Redis de
Compose (`redis://127.0.0.1:6380/15`) el modulo comprueba:

  * la publicacion y la recepcion reales de un sobre en el canal de su
    institucion;
  * que dos **hubs aislados** (dos `AlmacenRedisEventos` con clientes propios,
    como los de dos procesos) comparten el bus: el sobre publicado por la
    instancia A llega a la conexion SSE viva de la instancia B por Redis y no
    por memoria local (la evidencia de dos procesos reales es el recorrido
    manual con `uvicorn --workers 2`, registrado en T22);
  * que con Redis caido (URL a un puerto cerrado, sin apagar el Redis
    compartido) la mutacion conserva su respuesta y su latencia y `/ready`
    sigue en 200: la publicacion es best-effort y nunca bloquea la API.

La base se vacia al empezar y al terminar cada prueba y **nunca** se toca la
base 0: la URL debe terminar en `/15` y el fixture lo verifica antes de conectar.
Sin `REDIS_TEST_URL` todo el modulo se omite. Sin `pytest-asyncio`: cada
escenario se envuelve en `asyncio.run`.

COMO ACTIVARLO
    docker compose -f docker-compose.yml up -d redis
    $env:REDIS_TEST_URL = "redis://127.0.0.1:6380/15"
    cd backend; python -m pytest tests/no_funcional/rendimiento/test_bus_eventos_redis_028.py

RECORRIDO MANUAL DE DOS PROCESOS (el resultado se registra en la evidencia de T22)
    cd backend; uvicorn app.main:app --port 8000 --workers 2
    # con el tablero abierto en dos sesiones (4200), la mutacion de una debe
    # refrescar el tablero de la otra: los dos workers comparten este Pub/Sub.
"""

from __future__ import annotations

import asyncio
import os
import socket
import time
from contextlib import contextmanager
from urllib.parse import urlsplit

import pytest
import redis.asyncio
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.api.dependencies import ContextoTiempoReal
from app.api.v1.endpoints.eventos import generar
from app.core import eventos as bus_eventos
from app.core.config import settings
from app.core.eventos import (
    AlmacenRedisEventos,
    SobreEvento,
    canal_de_institucion,
)
from app.models import StockSede

from tests.funcional.integracion._soporte_retiro_013 import sembrar_mundo_retiro

URL = os.environ.get("REDIS_TEST_URL")

pytestmark = pytest.mark.skipif(
    not URL,
    reason="REDIS_TEST_URL no definida: prueba gated de Redis",
)

#: Institucion de la semilla de la suite (`datos_base`/`dos_instituciones`).
INSTITUCION = "INST-001"

#: Ruta del movimiento manual de stock (unica mutacion del escenario fail-open).
RUTA_MOVIMIENTOS = "/api/v1/inventario/movimientos"


def _url_de_prueba() -> str:
    """La suite solo corre contra la base 15, nunca contra la 0."""
    if not URL or not URL.endswith("/15"):
        pytest.skip("REDIS_TEST_URL debe apuntar a la base 15 de pruebas")
    return URL


async def _vaciar_base() -> None:
    """Vacia la base 15 en su propio bucle de eventos."""
    cliente = redis.asyncio.Redis.from_url(
        _url_de_prueba(), socket_connect_timeout=1, socket_timeout=1
    )
    try:
        await cliente.flushdb()
    finally:
        await cliente.aclose()


@pytest.fixture(autouse=True)
def base_redis_limpia():
    """Garantiza la base 15 vacia al empezar y al terminar (tambien en fallo)."""
    asyncio.run(_vaciar_base())
    yield
    asyncio.run(_vaciar_base())


async def _abrir_explorador() -> redis.asyncio.Redis:
    cliente = redis.asyncio.Redis.from_url(
        _url_de_prueba(),
        socket_connect_timeout=1,
        socket_timeout=1,
        decode_responses=True,
    )
    await cliente.flushdb()
    return cliente


@contextmanager
def _almacen_vigente(almacen):
    """Instala un almacen y enciende el canal durante el contexto.

    El conftest deja `TIEMPO_REAL_HABILITADO` apagado y el `AlmacenNulo`
    vigente; este contexto restaura ambos al salir, de modo que un escenario
    fail-open no contamine al siguiente.
    """
    previo = bus_eventos.obtener_almacen()
    habilitado_previo = settings.TIEMPO_REAL_HABILITADO
    bus_eventos.configurar_almacen(almacen)
    settings.TIEMPO_REAL_HABILITADO = True
    try:
        yield
    finally:
        settings.TIEMPO_REAL_HABILITADO = habilitado_previo
        bus_eventos.configurar_almacen(previo)


def _url_de_puerto_cerrado() -> str:
    """URL de la base 15 en un puerto local que nadie escucha.

    Se toma un puerto efimero y se cierra el socket antes de devolverlo: el
    `publish` recibira un rechazo de conexion inmediato y la prueba no depende
    de apagar el Redis compartido ni de esperar el `socket_timeout`.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sonda:
        sonda.bind(("127.0.0.1", 0))
        puerto = sonda.getsockname()[1]
    return f"redis://127.0.0.1:{puerto}/15"


def _sobre(dominios: set[str], *, motivo: str, usuario_ids=()) -> SobreEvento:
    return SobreEvento(
        institucion_id=INSTITUCION,
        dominios=frozenset(dominios),
        motivo=motivo,
        usuario_ids=frozenset(usuario_ids),
    )


# ---------------------------------------------------------------------------
# T3/AC-8: publicacion y suscripcion reales
# ---------------------------------------------------------------------------


def test_publicar_y_recibir_un_sobre_por_redis_real():
    canal = canal_de_institucion(INSTITUCION)
    sobre = _sobre({"pedidos", "inventario"}, motivo="retiro", usuario_ids={7})

    async def escenario():
        explorador = await _abrir_explorador()
        almacen = AlmacenRedisEventos(_url_de_prueba())
        try:
            suscripcion = await almacen.suscribir(canal)
            try:
                almacen.publicar(sobre)
                for _ in range(50):
                    recibido = await suscripcion.recibir(timeout=0.1)
                    if recibido is not None:
                        return recibido
                return None
            finally:
                await suscripcion.cerrar()
        finally:
            await almacen.cerrar()
            await explorador.aclose()

    assert asyncio.run(escenario()) == sobre


# ---------------------------------------------------------------------------
# T14/AC-23: dos hubs aislados comparten el bus
# ---------------------------------------------------------------------------


def test_dos_instancias_aisladas_comparten_el_bus_y_el_cambio_cruza_redis(
    monkeypatch,
):
    """El sobre de la instancia A llega a la conexion SSE de la instancia B.

    Cada `AlmacenRedisEventos` representa el hub de un proceso: clientes
    propios, sin colas ni objetos compartidos. La suscripcion vive en B y la
    publicacion sale del cliente sync de A; el unico camino posible entre
    ambos es el canal de Redis, asi que el frame `cambio` de la conexion de B
    acredita el fan-out entre instancias (el recorrido manual con
    `uvicorn --workers 2` queda como evidencia de dos procesos reales, T22).
    """
    monkeypatch.setattr(settings, "VIDA_MAXIMA_CONEXION_SEGUNDOS", 2)
    monkeypatch.setattr(settings, "TIEMPO_REAL_LATIDO_SEGUNDOS", 1)

    contexto = ContextoTiempoReal(
        usuario_id=7,
        rol="Administrador",
        institucion_id=INSTITUCION,
        expira_en=int(time.time()) + 120,
        dominios_visibles=frozenset(
            {"pedidos", "inventario", "compras", "dashboard"}
        ),
        request_id=None,
    )
    sobre = _sobre({"pedidos"}, motivo="alta", usuario_ids={7})

    async def escenario():
        explorador = await _abrir_explorador()
        instancia_a = AlmacenRedisEventos(_url_de_prueba())
        instancia_b = AlmacenRedisEventos(_url_de_prueba())
        with _almacen_vigente(instancia_b):
            try:
                generador = generar(contexto)
                listo = await generador.__anext__()
                suscriptores = await explorador.pubsub_numsub(
                    canal_de_institucion(INSTITUCION)
                )

                async def publicar_desde_a() -> None:
                    await asyncio.sleep(0.1)
                    instancia_a.publicar(sobre)

                tarea = asyncio.create_task(publicar_desde_a())
                marcos: list[str] = []
                try:
                    # El primer `get_message` puede consumir la confirmacion de
                    # `subscribe` y devolver `None` (latido); se leen marcos
                    # hasta el `cambio` o el tope acotado.
                    for _ in range(6):
                        marco = await asyncio.wait_for(
                            generador.__anext__(), timeout=3
                        )
                        marcos.append(marco)
                        if marco.startswith("event: cambio"):
                            break
                finally:
                    await tarea
                await generador.aclose()
                return listo, marcos, suscriptores, instancia_a, instancia_b
            finally:
                await instancia_a.cerrar()
                await instancia_b.cerrar()
                await explorador.aclose()

    listo, marcos, suscriptores, instancia_a, instancia_b = asyncio.run(
        escenario()
    )

    assert instancia_a is not instancia_b, (
        "las dos instancias deben ser hubs distintos, no el mismo almacen"
    )
    assert dict(suscriptores).get(canal_de_institucion(INSTITUCION), 0) >= 1, (
        "la conexion de la instancia B debe tener una suscripcion viva en Redis"
    )
    assert listo.startswith("event: listo"), listo
    assert '"pedidos"' in listo and '"dashboard"' in listo, listo

    cambios = [marco for marco in marcos if marco.startswith("event: cambio")]
    assert cambios, (
        "la conexion de B debe recibir por Redis el sobre publicado por A; "
        f"marcos recibidos: {marcos!r}"
    )
    cambio = cambios[0]
    assert '"dominios":["pedidos"]' in cambio, cambio
    assert '"motivo":"alta"' in cambio, cambio
    for prohibido in ("institucion_id", "usuario_id", "usuario_ids", INSTITUCION):
        assert prohibido not in cambio, prohibido


# ---------------------------------------------------------------------------
# T14/AC-8: Redis caido y fail-open
# ---------------------------------------------------------------------------


def _stock_sede_id(motor, sede_id: int, producto_id: int) -> int:
    with sessionmaker(bind=motor)() as db:
        fila = db.execute(
            select(StockSede).where(
                StockSede.sede_id == sede_id,
                StockSede.producto_id == producto_id,
            )
        ).scalar_one()
        return fila.stock_sede_id


def _movimiento(cliente, *, stock_sede_id: int, cantidad: int):
    return cliente.post(
        RUTA_MOVIMIENTOS,
        json={
            "tipo_movimiento": "ENTRADA",
            "cantidad": cantidad,
            "observacion": "Fail-open de Redis de la 028 (T14)",
            "stock_sede_id": stock_sede_id,
        },
    )


def test_redis_detenido_conserva_la_respuesta_y_ready_200(
    cliente, motor, dos_instituciones, actuar_como
):
    """AC-8: con Redis caido la mutacion responde igual y `/ready` sigue en 200.

    No se apaga el Redis compartido: el almacen apunta a un puerto cerrado. La
    primera mutacion (con `AlmacenNulo`) es la linea base de latencia; la
    segunda (con el Redis inalcanzable) debe conservar status y cuerpo y no
    superar la base en mas de 0,5 s. `/ready` solo mide la base, asi que sigue
    en 200.
    """
    mundo = sembrar_mundo_retiro(motor, dos_instituciones)
    stock_sede_id = _stock_sede_id(
        motor, mundo["sede_id"], mundo["producto_id"]
    )
    identidad = actuar_como("Bodeguero")
    identidad.usuario.sede_id = mundo["sede_id"]

    with _almacen_vigente(bus_eventos.AlmacenNulo()):
        inicio = time.monotonic()
        base = _movimiento(
            cliente, stock_sede_id=stock_sede_id, cantidad=1
        )
        duracion_base = time.monotonic() - inicio

    almacen = AlmacenRedisEventos(_url_de_puerto_cerrado())
    try:
        with _almacen_vigente(almacen):
            inicio = time.monotonic()
            respuesta = _movimiento(
                cliente, stock_sede_id=stock_sede_id, cantidad=2
            )
            duracion = time.monotonic() - inicio
            ready = cliente.get("/ready")
    finally:
        asyncio.run(almacen.cerrar())

    assert base.status_code == 201, base.text
    assert base.json()["nuevo_stock"] == 51, base.text

    assert respuesta.status_code == 201, respuesta.text
    assert respuesta.json()["nuevo_stock"] == 53, respuesta.text
    assert duracion <= duracion_base + 0.5, (
        "la publicacion al Redis caido no debe anadir mas de 0,5 s a la "
        f"mutacion: base {duracion_base:.3f} s, con Redis caido {duracion:.3f} s"
    )

    assert ready.status_code == 200, ready.text
    assert ready.json() == {"status": "ready"}


# ---------------------------------------------------------------------------
# T14/AC-25: la suite nunca usa la base 0
# ---------------------------------------------------------------------------


def test_la_suite_solo_se_ejecuta_contra_la_base_15():
    """La guarda de la URL impide tocar la base 0 de la aplicacion."""
    assert urlsplit(_url_de_prueba()).path == "/15"
