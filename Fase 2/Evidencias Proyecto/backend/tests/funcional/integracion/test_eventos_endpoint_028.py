"""Contrato del canal SSE de la Feature 028 (T5).

Seam bajo prueba: la interfaz HTTP del `app` real con `TestClient`. La nota de
T0 es vinculante: `TestClient` de Starlette 1.7 ejecuta el generador hasta el
final y bufferiza el cuerpo, de modo que **todo** caso abre un flujo acotado
(vida maxima o `exp` cortos) y lee el cuerpo completo; nunca cierra un flujo
largo a la mitad.

Se fijan las cabeceras del contrato, el primer frame `listo` con los dominios
visibles, la ausencia de identificadores y de `id:`/`retry:`, el latido, el
cierre por `exp - MARGEN_RELOJ_SEGUNDOS` y el frame `cambio` de un sobre que el
bus falso entrega ya filtrado (el filtro por conexion es T6).
"""

import json
import time

import pytest

from app.core.config import settings
from app.core.eventos import SobreEvento
from app.models import Rol, Usuario
from app.services.auth_service import IdentidadAutenticada

from tests.funcional.integracion._soporte_eventos_028 import instalar_bus

RUTA = "/api/v1/eventos/"
CANAL_INST01 = "compustock:eventos:INST01"

#: Orden canonico del contrato para el frame `listo`.
DOMINIOS_ADMINISTRADOR = ["pedidos", "inventario", "compras", "dashboard"]
DOMINIOS_SOLICITANTE = ["pedidos", "inventario", "dashboard"]


@pytest.fixture(autouse=True)
def flujo_acotado(monkeypatch):
    """Acota todo flujo del modulo: `TestClient` espera el cuerpo completo."""
    monkeypatch.setattr(settings, "VIDA_MAXIMA_CONEXION_SEGUNDOS", 1)
    monkeypatch.setattr(settings, "TIEMPO_REAL_LATIDO_SEGUNDOS", 1)


def _identidad(
    datos_base,
    *,
    rol: str = "Administrador",
    expira_en: int | None = None,
) -> IdentidadAutenticada:
    """Identidad suelta con ids reales de INST01 (patron de la suite)."""
    usuario = Usuario(
        usuario_id=datos_base["usuario_id"],
        nombre="Ana",
        apellido="Perez",
        correo=datos_base["correo_usado"],
        departamento_id=datos_base["departamento_id"],
        rol_id=datos_base["rol_id"],
    )
    usuario.rol = Rol(nombre_rol=rol)
    return IdentidadAutenticada(
        usuario=usuario, sub="sub-eventos-028", expira_en=expira_en
    )


def _abrir_flujo(cliente, ruta: str = RUTA):
    """Abre el flujo y devuelve `(respuesta, cuerpo)` ya completos.

    `TestClient` bufferiza el `StreamingResponse`: la lectura termina cuando el
    generador cierra, por eso los flujos de este modulo duren ~1 s como maximo.
    """
    with cliente.stream("GET", ruta) as respuesta:
        cuerpo = respuesta.read().decode("utf-8")
    return respuesta, cuerpo


def _eventos(cuerpo: str) -> list[tuple[str, dict]]:
    """Frames `(evento, data)` del cuerpo SSE; los comentarios no son frames."""
    eventos: list[tuple[str, dict]] = []
    evento: str | None = None
    datos: dict | None = None
    for linea in cuerpo.splitlines():
        if linea.startswith("event: "):
            evento = linea[len("event: ") :]
        elif linea.startswith("data: "):
            datos = json.loads(linea[len("data: ") :])
        elif linea == "" and evento is not None:
            eventos.append((evento, datos or {}))
            evento, datos = None, None
    return eventos


def _lineas_de_campo(cuerpo: str, prefijo: str) -> list[str]:
    return [linea for linea in cuerpo.splitlines() if linea.startswith(prefijo)]


# ---------------------------------------------------------------------------
# Contrato de exito
# ---------------------------------------------------------------------------


def test_sesion_valida_abre_el_flujo_con_listo_y_sus_cabeceras(
    cliente, datos_base
):
    """AC-1: 200, `text/event-stream`, `no-store`, `X-Accel-Buffering` y `listo`."""
    with instalar_bus() as bus:
        respuesta, cuerpo = _abrir_flujo(cliente)

    assert respuesta.status_code == 200
    assert respuesta.headers["content-type"] == "text/event-stream; charset=utf-8"
    assert respuesta.headers["cache-control"] == "no-store"
    assert respuesta.headers["x-accel-buffering"] == "no"

    eventos = _eventos(cuerpo)
    assert eventos[0] == ("listo", {"dominios": DOMINIOS_ADMINISTRADOR})
    assert bus.canales == [CANAL_INST01], "el canal sale solo de la identidad"


def test_el_frame_listo_no_lleva_identificadores_ni_el_flujo_usa_id_o_retry(
    cliente, datos_base
):
    """AC-18/AC-24: `listo` solo publica `dominios`; sin `id:` ni `retry:`."""
    with instalar_bus():
        _, cuerpo = _abrir_flujo(cliente)

    listo = _eventos(cuerpo)[0]
    assert listo[0] == "listo"
    assert set(listo[1]) == {"dominios"}

    primero = cuerpo.split("\n\n", 1)[0]
    for prohibido in (
        "institucion_id",
        "usuario_id",
        "usuario_ids",
        "ticket_id",
        "INST01",
    ):
        assert prohibido not in primero, prohibido

    assert _lineas_de_campo(cuerpo, "id:") == []
    assert _lineas_de_campo(cuerpo, "retry:") == []


def test_emite_al_menos_un_latido_con_el_intervalo_corto(cliente, datos_base):
    """AC-4: con latido de 1 s y vida de 1 s se lee un comentario `: latido`."""
    with instalar_bus():
        respuesta, cuerpo = _abrir_flujo(cliente)

    assert respuesta.status_code == 200
    assert ": latido" in cuerpo


def test_el_flujo_se_cierra_en_exp_menos_el_margen(
    cliente, datos_base, identidad_actual, monkeypatch
):
    """AC-3: el limite es `exp - 10 s`, no la vida maxima (aqui 300 s)."""
    monkeypatch.setattr(settings, "VIDA_MAXIMA_CONEXION_SEGUNDOS", 300)
    identidad_actual["actual"] = _identidad(
        datos_base, expira_en=int(time.time()) + 11
    )

    with instalar_bus():
        inicio = time.monotonic()
        respuesta, cuerpo = _abrir_flujo(cliente)
        transcurrido = time.monotonic() - inicio

    assert respuesta.status_code == 200
    assert _eventos(cuerpo)[0][0] == "listo"
    assert transcurrido < 5, (
        "el flujo debe cerrarse por `exp - 10 s` (~1 s), no esperar la vida "
        f"maxima de 300 s; tardo {transcurrido:.2f} s"
    )


def test_un_sobre_ya_filtrado_del_bus_produce_un_frame_cambio_sin_ids(
    cliente, datos_base
):
    """T5: la suscripcion materializa `cambio`; el sobre interno no se filtra."""
    sobre = SobreEvento(
        institucion_id="INST01",
        dominios=frozenset({"pedidos"}),
        motivo="alta",
        usuario_ids=frozenset({7}),
    )
    with instalar_bus(eventos_iniciales=[sobre]):
        _, cuerpo = _abrir_flujo(cliente)

    eventos = _eventos(cuerpo)
    assert eventos[0] == ("listo", {"dominios": DOMINIOS_ADMINISTRADOR})
    assert ("cambio", {"dominios": ["pedidos"], "motivo": "alta"}) in eventos

    cambio = cuerpo.split("event: cambio", 1)[1].split("\n\n", 1)[0]
    for prohibido in ("usuario_ids", "institucion_id", '"7"', "INST01"):
        assert prohibido not in cambio, prohibido
