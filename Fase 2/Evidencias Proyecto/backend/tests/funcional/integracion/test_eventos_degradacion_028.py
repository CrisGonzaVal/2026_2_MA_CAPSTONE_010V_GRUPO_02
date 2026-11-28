"""Degradacion, recuperacion y cota del canal SSE (Feature 028, T7).

Seam bajo prueba: el endpoint real `GET /api/v1/eventos/` con `TestClient` y un
bus guionizado que falla al suscribir o al recibir. Por la nota de T0
(`TestClient` bufferiza el cuerpo y espera el cierre), cada flujo se acota con
`VIDA_MAXIMA_CONEXION_SEGUNDOS` y `TIEMPO_REAL_LATIDO_SEGUNDOS` cortos.

Casos:

* el bus que lanza al suscribir deja el HTTP abierto, emite `estado: degradado`
  y sigue con latidos;
* el bus que lanza al recibir degrada la conexion y, al recuperarse, emite
  `estado: recuperado` sin volver a mandar `listo`;
* el retroceso interno es 1/2/4/8/10 s con tope y no abre otra peticion HTTP;
* la publicacion de una mutacion con el bus colgado respeta la cota de 0,5 s y
  no produce 5xx;
* la linea `compustock.tiempo_real` registra `request_id`, `route`,
  `resultado` y `motivo`, sin token, correo, query, IP ni ids;
* `/ready` sigue midiendo solo la base (200) con el bus caido.
"""

import asyncio
import json
import socket
import time

import pytest

from app.api.v1.endpoints import eventos
from app.core import eventos as bus_eventos
from app.core.config import settings
from app.core.eventos import (
    AlmacenNulo,
    AlmacenRedisEventos,
    ErrorBusEventos,
    SobreEvento,
)
from app.main import app
from app.models import Rol, Usuario
from app.services import evento_service
from app.services.auth_service import IdentidadAutenticada

from tests.funcional.integracion.soporte_observabilidad_024 import capturar_logs

RUTA = "/api/v1/eventos/"
RUTA_MUTACION = "/_prueba-mutacion-tiempo-real-028"
CANAL_INST01 = "compustock:eventos:INST01"

#: Mensaje estable de la linea semantica del canal.
MENSAJE_LOG = "conexion_tiempo_real"


# ---------------------------------------------------------------------------
# Dobles del bus
# ---------------------------------------------------------------------------


class _SuscripcionGuionizada:
    """Suscripcion con un guion de acciones: sobre, `None` o error."""

    def __init__(self, acciones: list) -> None:
        self._acciones = acciones
        self.cerrada = False

    async def recibir(self, timeout: float | None = None) -> SobreEvento | None:
        if self.cerrada:
            return None
        accion = self._acciones.pop(0) if self._acciones else None
        if isinstance(accion, BaseException):
            raise accion
        if accion is None:
            await asyncio.sleep(min(0.01, timeout if timeout else 0.01))
            return None
        return accion

    async def cerrar(self) -> None:
        self.cerrada = True


class _BusGuionizado:
    """Bus que falla N suscripciones y luego entrega el guion de recepciones."""

    def __init__(
        self,
        *,
        fallos_suscripcion: int = 0,
        acciones: list | None = None,
    ) -> None:
        self.fallos_suscripcion = fallos_suscripcion
        self.intentos_suscripcion = 0
        self.canales: list[str] = []
        self.cerrado = False
        self._acciones = list(acciones or [])

    def publicar(self, sobre: SobreEvento) -> None:
        """La degradacion se prueba en la lectura, no en la publicacion."""

    async def suscribir(self, canal: str):
        self.canales.append(canal)
        self.intentos_suscripcion += 1
        if self.intentos_suscripcion <= self.fallos_suscripcion:
            raise ErrorBusEventos("el bus no responde")
        return _SuscripcionGuionizada(self._acciones)

    async def cerrar(self) -> None:
        self.cerrado = True


# ---------------------------------------------------------------------------
# Utilidades de escenario
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def flujo_acotado(monkeypatch):
    """Todo flujo del modulo dura ~1 s: `TestClient` espera el cuerpo completo."""
    monkeypatch.setattr(settings, "VIDA_MAXIMA_CONEXION_SEGUNDOS", 1)
    monkeypatch.setattr(settings, "TIEMPO_REAL_LATIDO_SEGUNDOS", 1)


@pytest.fixture
def identidad_vigente(datos_base, identidad_actual):
    """Administrador de INST01 con `exp` lejano (el cierre sera por vida maxima)."""
    usuario = Usuario(
        usuario_id=datos_base["usuario_id"],
        nombre="Ana",
        apellido="Perez",
        correo=datos_base["correo_usado"],
        departamento_id=datos_base["departamento_id"],
        rol_id=datos_base["rol_id"],
    )
    usuario.rol = Rol(nombre_rol="Administrador")
    identidad_actual["actual"] = IdentidadAutenticada(
        usuario=usuario,
        sub="sub-degradacion-028",
        expira_en=int(time.time()) + 300,
    )
    return identidad_actual["actual"]


@pytest.fixture
def instalar_bus_guionizado(monkeypatch):
    """Instala el bus guionizado y enciende el canal solo durante el test."""

    def _instalar(bus: _BusGuionizado) -> _BusGuionizado:
        monkeypatch.setattr(bus_eventos, "_ALMACEN", bus)
        monkeypatch.setattr(settings, "TIEMPO_REAL_HABILITADO", True)
        return bus

    return _instalar


@pytest.fixture
def dormir_registrado(monkeypatch):
    """Sustituye la espera del retroceso y registra sus tramos."""
    esperas: list[float] = []

    async def _dormir(segundos: float) -> None:
        esperas.append(segundos)
        await asyncio.sleep(0.01)

    monkeypatch.setattr(eventos, "_dormir", _dormir)
    return esperas


def _abrir_flujo(cliente, ruta: str = RUTA, **opciones):
    """Abre el flujo y devuelve `(respuesta, cuerpo)` ya completos."""
    with cliente.stream("GET", ruta, **opciones) as respuesta:
        cuerpo = respuesta.read().decode("utf-8")
    return respuesta, cuerpo


def _eventos(cuerpo: str) -> list[tuple[str, dict]]:
    """Frames `(evento, data)` del cuerpo SSE; los comentarios no son frames."""
    encontrados: list[tuple[str, dict]] = []
    evento: str | None = None
    datos: dict | None = None
    for linea in cuerpo.splitlines():
        if linea.startswith("event: "):
            evento = linea[len("event: ") :]
        elif linea.startswith("data: "):
            datos = json.loads(linea[len("data: ") :])
        elif linea == "" and evento is not None:
            encontrados.append((evento, datos or {}))
            evento, datos = None, None
    return encontrados


def _estados(cuerpo: str) -> list[str]:
    return [
        datos.get("estado", "")
        for evento, datos in _eventos(cuerpo)
        if evento == "estado"
    ]


def _sobre_pedidos() -> SobreEvento:
    return SobreEvento(
        institucion_id="INST01",
        dominios=frozenset({"pedidos"}),
        motivo="alta",
        usuario_ids=frozenset({1}),
    )


def _escenario_recuperacion() -> _BusGuionizado:
    """Falla una suscripcion, entrega `listo`, falla una recepcion y se recupera."""
    return _BusGuionizado(
        fallos_suscripcion=1,
        acciones=[
            ErrorBusEventos("el bus cae al recibir"),
            _sobre_pedidos(),
        ],
    )


def _lineas_semanticas(lineas: list[str]) -> list[dict]:
    registros = []
    for linea in lineas:
        try:
            registro = json.loads(linea)
        except json.JSONDecodeError:
            continue
        if registro.get("message") == MENSAJE_LOG:
            registros.append(registro)
    return registros


# ---------------------------------------------------------------------------
# Degradacion y recuperacion
# ---------------------------------------------------------------------------


def test_el_bus_que_falla_al_suscribir_mantiene_el_http_y_emite_degradado(
    cliente, identidad_vigente, instalar_bus_guionizado, dormir_registrado
):
    """AC-8: sin suscripcion no hay `listo`, pero el flujo sigue abierto."""
    bus = instalar_bus_guionizado(
        _BusGuionizado(fallos_suscripcion=10**9)
    )

    respuesta, cuerpo = _abrir_flujo(cliente)

    assert respuesta.status_code == 200
    assert respuesta.headers["content-type"].startswith("text/event-stream")
    assert "event: listo" not in cuerpo, "listo solo se emite con suscripcion activa"
    assert _estados(cuerpo) == ["degradado"], "una sola transicion, no una por intento"
    assert ": latido" in cuerpo, "el latido sigue durante la degradacion"
    assert bus.intentos_suscripcion > 1, "el suscriptor reintenta sin cerrar el HTTP"


def test_el_bus_que_falla_al_recibir_degrada_y_al_recuperarse_emite_recuperado(
    cliente, identidad_vigente, instalar_bus_guionizado, dormir_registrado
):
    """AC-8: `degradado` al caer la recepcion y `recuperado` al reabrir el bus."""
    bus = instalar_bus_guionizado(_escenario_recuperacion())

    respuesta, cuerpo = _abrir_flujo(cliente)

    assert respuesta.status_code == 200
    assert _estados(cuerpo) == [
        "degradado",
        "recuperado",
        "degradado",
        "recuperado",
    ]
    assert cuerpo.count("event: listo") == 1, "la recuperacion no reemite `listo`"
    assert ("cambio", {"dominios": ["pedidos"], "motivo": "alta"}) in _eventos(cuerpo)
    assert bus.intentos_suscripcion == 3, "una peticion HTTP con tres intentos de bus"
    assert set(bus.canales) == {CANAL_INST01}, "el canal sale solo de la identidad"


def test_el_retroceso_interno_es_1_2_4_8_10_con_tope_en_el_ultimo_valor():
    """Plan §5.4: la reconexion usa 1/2/4/8/10 s y despues mantiene 10 s."""
    assert eventos.RETROCESO_SEGUNDOS == (1.0, 2.0, 4.0, 8.0, 10.0)
    assert [
        eventos.retroceso_de_intento(intento) for intento in range(7)
    ] == [1.0, 2.0, 4.0, 8.0, 10.0, 10.0, 10.0]


def test_la_reconexion_reintenta_por_dentro_sin_abrir_otra_peticion_http(
    cliente, identidad_vigente, instalar_bus_guionizado, dormir_registrado, monkeypatch
):
    """El reintento es interno: una sola respuesta para tres intentos de bus.

    El primer tramo del retroceso es 1 s (la escala exacta 1/2/4/8/10 se fija
    en `test_el_retroceso_interno_es_1_2_4_8_10_con_tope_en_el_ultimo_valor`);
    la vida del flujo acota el segundo tramo, por eso aqui solo se comprueba
    que la espera ocurre y que el cliente no abre otra peticion.
    """
    monkeypatch.setattr(settings, "TIEMPO_REAL_LATIDO_SEGUNDOS", 30)
    bus = instalar_bus_guionizado(_BusGuionizado(fallos_suscripcion=2))

    respuesta, cuerpo = _abrir_flujo(cliente)

    assert respuesta.status_code == 200
    assert dormir_registrado[0] == pytest.approx(1.0, abs=0.05)
    assert len(dormir_registrado) >= 2, "el segundo intento tambien espera"
    assert bus.intentos_suscripcion == 3
    assert "event: listo" in cuerpo


# ---------------------------------------------------------------------------
# Cota de publicacion con el bus colgado
# ---------------------------------------------------------------------------


def _mutacion_de_prueba() -> dict[str, str]:
    """Simula el punto que T8 inserta tras el commit de una mutacion."""
    evento_service.publicar_pedidos("INST01", "alta", {1})
    return {"status": "ok"}


@pytest.fixture
def redis_colgado():
    """Servidor TCP que acepta y nunca responde: el socket vence a los 0,5 s."""
    servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    servidor.bind(("127.0.0.1", 0))
    servidor.listen(8)
    almacen = AlmacenRedisEventos(
        f"redis://127.0.0.1:{servidor.getsockname()[1]}/0"
    )
    try:
        yield almacen
    finally:
        asyncio.run(almacen.cerrar())
        servidor.close()


def test_una_mutacion_con_el_bus_colgado_respeta_la_cota_y_no_da_5xx(
    cliente, monkeypatch, redis_colgado
):
    """AC-8: la mutacion conserva status y cuerpo; agrega como maximo 0,5 s."""
    monkeypatch.setattr(settings, "TIEMPO_REAL_HABILITADO", True)
    monkeypatch.setattr(bus_eventos, "_ALMACEN", AlmacenNulo())
    app.add_api_route(
        RUTA_MUTACION,
        _mutacion_de_prueba,
        methods=["POST"],
        include_in_schema=False,
    )
    try:
        inicio = time.monotonic()
        base = cliente.post(RUTA_MUTACION)
        latencia_base = time.monotonic() - inicio

        monkeypatch.setattr(bus_eventos, "_ALMACEN", redis_colgado)
        inicio = time.monotonic()
        colgada = cliente.post(RUTA_MUTACION)
        latencia_colgada = time.monotonic() - inicio
    finally:
        app.router.routes = [
            ruta
            for ruta in app.router.routes
            if getattr(ruta, "path", None) != RUTA_MUTACION
        ]

    assert base.status_code == 200
    assert colgada.status_code == 200, "el bus caido no puede convertirse en 5xx"
    assert colgada.json() == {"status": "ok"}
    assert latencia_colgada - latencia_base < 0.75, (
        "el intento de publicacion debe respetar la cota de 0,5 s; "
        f"delta medido {latencia_colgada - latencia_base:.3f} s"
    )
    assert latencia_colgada < 1.0


# ---------------------------------------------------------------------------
# Observabilidad del canal
# ---------------------------------------------------------------------------


def test_la_linea_tiempo_real_registra_campos_permitidos_sin_pii(
    cliente, identidad_vigente, instalar_bus_guionizado, dormir_registrado, datos_base
):
    """AC-8/§8: apertura, degradacion, recuperacion y cierre sin PII."""
    instalar_bus_guionizado(_escenario_recuperacion())
    token = "token-secreto-de-prueba-028"
    correo = datos_base["correo_usado"]

    with capturar_logs() as lineas:
        respuesta, _ = _abrir_flujo(
            cliente,
            f"{RUTA}?institucion_id=INST01&correo={correo}",
            headers={"Authorization": f"Bearer {token}"},
        )

    registros = _lineas_semanticas(lineas)
    assert registros, "debe existir al menos una linea de compustock.tiempo_real"
    resultados = [registro["resultado"] for registro in registros]
    assert set(resultados) == {"abierta", "degradada", "recuperada", "cerrada"}
    assert resultados.count("degradada") == 2

    for registro in registros:
        assert registro["logger"] == "compustock.tiempo_real"
        assert set(registro) == {
            "timestamp",
            "level",
            "logger",
            "message",
            "request_id",
            "route",
            "resultado",
            "motivo",
        }, "la linea solo lleva los campos fijos y los cuatro semanticos"
        assert registro["route"] == "/api/v1/eventos/"
        assert registro["resultado"] in {
            "abierta",
            "cerrada",
            "degradada",
            "recuperada",
        }
        assert registro["motivo"] in {
            "token_expirado",
            "vida_maxima",
            "sesion",
            "bus",
            "cliente",
            "error",
        }
        assert registro["request_id"] == respuesta.headers["x-request-id"]

    texto = "\n".join(lineas)
    for prohibido in (
        token,
        "Bearer",
        correo,
        "INST01",
        "institucion_id",
        "usuario_id",
        "usuario_ids",
        "correo=",
        "?",
        "127.0.0.1",
        "Traceback",
    ):
        assert prohibido not in texto, f"la linea de log no debe contener {prohibido!r}"


def test_ready_sigue_en_200_con_el_bus_degradado(cliente, instalar_bus_guionizado):
    """§5.5: `/ready` mide solo la base; no se acopla al bus de eventos."""
    instalar_bus_guionizado(_BusGuionizado(fallos_suscripcion=10**9))

    respuesta = cliente.get("/ready")

    assert respuesta.status_code == 200
    assert respuesta.json() == {"status": "ready"}
