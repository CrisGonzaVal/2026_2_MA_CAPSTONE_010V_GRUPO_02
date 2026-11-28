"""Ventana de capacidades e institucion del canal SSE (Feature 028, T14).

AC-31 (M9): una conexion abierta **no** entrega eventos de un dominio que ya no
puede ver mas alla de la ventana declarada, y la siguiente reapertura reevalua
la institucion y las capacidades antes de emitir `listo`.

La ventana se demuestra de forma determinista, sin esperas de 300 s:

  * `VIDA_MAXIMA_CONEXION_SEGUNDOS = 1` acota la conexion vieja. El generador
    emite `listo`, entrega los sobres de dominios que aun ve y cierra al vencer
    la ventana; un sobre publicado despues ya no se entrega por esa conexion.
  * Con `tickets` apagado, la reapertura no incluye `pedidos` en `listo`, el
    sobre de pedidos se sustituye por la marca sintetica `dashboard` (nunca se
    revela el dominio oculto) y `GET /api/v1/tickets/` responde **403**.
  * Con la institucion desactivada, la reapertura responde **401** antes de
    abrir el flujo (`ErrorInstitucionInactiva` del mapa de control).

El aislamiento entre instituciones es estructural (la suscripcion se abre en
el canal de la institucion del contexto) y se refuerza al recibir: un sobre de
otra institucion no produce frame. Los casos de rol/dueño/capacidad de frames
ya viven en `tests/funcional/integracion/test_eventos_filtro_028.py`; aqui se
prueba la **ventana** y la **reevaluacion en la reapertura**.
"""

from __future__ import annotations

import asyncio
import json
import time

import pytest
from sqlalchemy import update
from sqlalchemy.orm import sessionmaker

from app.api.dependencies import ContextoTiempoReal
from app.api.v1.endpoints.eventos import generar
from app.core.config import VERSION_ESQUEMA_OBJETIVO, settings
from app.core.eventos import SobreEvento, canal_de_institucion
from app.models import Rol, Usuario
from app.models.control import MapaUsuarioEsquema, VersionEsquema
from app.models.control_canonico import FuncionInstitucion, InstitucionControl
from app.services.auth_service import IdentidadAutenticada

from tests.funcional.integracion._soporte_eventos_028 import instalar_bus

RUTA_EVENTOS = "/api/v1/eventos/"
RUTA_TICKETS = "/api/v1/tickets/"

#: Institucion de la semilla de la suite (`datos_base`).
INSTITUCION = "INST01"

#: Dominios de un Administrador con las cuatro capacidades encendidas.
DOMINIOS_COMPLETOS = ["pedidos", "inventario", "compras", "dashboard"]

#: Dominios de la reapertura con `tickets` apagado (sin `pedidos`).
DOMINIOS_SIN_TICKETS = ["inventario", "compras", "dashboard"]


@pytest.fixture(autouse=True)
def ventana_corta(monkeypatch):
    """Acota la conexion a 1 s: la ventana se prueba sin esperas largas."""
    monkeypatch.setattr(settings, "VIDA_MAXIMA_CONEXION_SEGUNDOS", 1)
    monkeypatch.setattr(settings, "TIEMPO_REAL_LATIDO_SEGUNDOS", 1)


def _identidad(datos_base, *, expira_en: int | None = None) -> IdentidadAutenticada:
    """Identidad suelta del Administrador de INST01 con ids reales."""
    usuario = Usuario(
        usuario_id=datos_base["usuario_id"],
        nombre="Ana",
        apellido="Perez",
        correo=datos_base["correo_usado"],
        departamento_id=datos_base["departamento_id"],
        rol_id=datos_base["rol_id"],
    )
    usuario.rol = Rol(nombre_rol="Administrador")
    return IdentidadAutenticada(
        usuario=usuario,
        sub="sub-tiempo-real-t14",
        expira_en=expira_en,
    )


def _contexto(
    *,
    usuario_id: int,
    dominios_visibles: frozenset[str],
    institucion_id: str = INSTITUCION,
) -> ContextoTiempoReal:
    """Copia de contexto de una conexion SSE ya resuelta (sin base de datos)."""
    return ContextoTiempoReal(
        usuario_id=usuario_id,
        rol="Administrador",
        institucion_id=institucion_id,
        expira_en=None,
        dominios_visibles=dominios_visibles,
        request_id=None,
    )


def _sobre(
    dominios: set[str],
    *,
    motivo: str,
    institucion_id: str = INSTITUCION,
    usuario_ids=(),
) -> SobreEvento:
    return SobreEvento(
        institucion_id=institucion_id,
        dominios=frozenset(dominios),
        motivo=motivo,
        usuario_ids=frozenset(usuario_ids),
    )


def _abrir_flujo(cliente, ruta: str = RUTA_EVENTOS):
    """Abre un flujo acotado y devuelve `(respuesta, cuerpo)` completos."""
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


def _apagar_capacidad(motor, funcion: str) -> None:
    """Desactiva una capacidad funcional de INST01 con una fila explicita."""
    with sessionmaker(bind=motor)() as db:
        db.add(
            FuncionInstitucion(
                institucion_id=INSTITUCION,
                funcion=funcion,
                habilitada=False,
            )
        )
        db.commit()


def _sembrar_mapa_de_control(motor, correo: str) -> None:
    """Mapa `correo -> esquema` y version objetivo para la rama PostgreSQL."""
    with sessionmaker(bind=motor)() as db:
        db.add(
            MapaUsuarioEsquema(
                correo=correo,
                institucion_id=INSTITUCION,
                nombre_esquema="tenant_inst01",
                activo=True,
            )
        )
        db.add(VersionEsquema(version=VERSION_ESQUEMA_OBJETIVO))
        db.commit()


def _fijar_institucion_activa(motor, *, activo: bool) -> None:
    """Cambia el estado de ciclo de vida del registro canonico de control."""
    with sessionmaker(bind=motor)() as db:
        db.execute(
            update(InstitucionControl)
            .where(InstitucionControl.institucion_id == INSTITUCION)
            .values(activo=activo)
        )
        db.commit()


# ---------------------------------------------------------------------------
# AC-31: la conexion vieja muere con la ventana y no entrega mas dominio
# ---------------------------------------------------------------------------


def test_la_conexion_vieja_entrega_antes_de_la_ventana_y_cierra_al_vencer_ac_31():
    """Ventana de 1 s: un `cambio` a tiempo y ninguno despues del cierre.

    Se usa el generador real del endpoint con el bus falso: el sobre propio de
    `pedidos` llega como `cambio`, el de otra institucion se descarta
    (aislamiento) y, al vencer la vida maxima, la conexion cierra; un sobre
    publicado despues de la ventana ya no se entrega por la conexion vieja.
    """
    contexto = _contexto(
        usuario_id=7,
        dominios_visibles=frozenset(DOMINIOS_COMPLETOS),
    )
    propio = _sobre(
        {"pedidos"}, motivo="alta", usuario_ids={7}
    )
    ajeno = _sobre(
        {"pedidos"},
        motivo="alta",
        institucion_id="INST02",
        usuario_ids={7},
    )

    async def escenario():
        generador = generar(contexto)
        try:
            listo = await generador.__anext__()
            bus.publicar(propio)
            cambio = await generador.__anext__()
            bus.publicar(ajeno)

            inicio = time.monotonic()
            resto = [frame async for frame in generador]
            transcurrido = time.monotonic() - inicio

            # La ventana ya cerro: otro sobre del dominio no se entrega.
            bus.publicar(propio)
            cerrada = False
            try:
                await generador.__anext__()
            except StopAsyncIteration:
                cerrada = True
            return listo, cambio, resto, transcurrido, cerrada
        finally:
            await generador.aclose()

    with instalar_bus() as bus:
        listo, cambio, resto, transcurrido, cerrada = asyncio.run(escenario())
        canales = bus.canales

    assert canales == [canal_de_institucion(INSTITUCION)], (
        "la suscripcion sale solo de la institucion del contexto"
    )
    assert listo.startswith("event: listo"), listo
    assert '"dominios":["pedidos","inventario","compras","dashboard"]' in listo

    assert cambio.startswith("event: cambio"), cambio
    assert '"dominios":["pedidos"]' in cambio, cambio
    assert '"motivo":"alta"' in cambio, cambio
    for prohibido in ("institucion_id", "usuario_id", "usuario_ids", INSTITUCION):
        assert prohibido not in cambio, prohibido

    assert all("event: cambio" not in frame for frame in resto), (
        "el sobre de otra institucion no debe producir frame; se recibio: "
        f"{resto!r}"
    )
    assert transcurrido < 3, (
        "la conexion debe cerrar al vencer la ventana de 1 s, no al agotar la "
        f"vida maxima de produccion; tardo {transcurrido:.2f} s"
    )
    assert cerrada, "la conexion vieja debe estar cerrada al vencer la ventana"


# ---------------------------------------------------------------------------
# AC-31: la reapertura reevalua la capacidad apagada
# ---------------------------------------------------------------------------


def test_la_reapertura_no_incluye_el_dominio_apagado_y_la_lectura_responde_403_ac_31(
    cliente, motor, datos_base, identidad_actual
):
    """Con `tickets` apagado: `listo` sin `pedidos`, marca `dashboard` y 403."""
    identidad_actual["actual"] = _identidad(
        datos_base, expira_en=int(time.time()) + 120
    )
    # El gating de capacidad de la lectura resuelve el tenant por el mapa de
    # control (no por `ambito_service`); sin mapa, `get_contexto_capacidad`
    # devuelve `None` y omitiria el 403 por diseno.
    _sembrar_mapa_de_control(motor, datos_base["correo_usado"])
    sobre = _sobre(
        {"pedidos"}, motivo="alta", usuario_ids={datos_base["usuario_id"]}
    )

    with instalar_bus():
        _, cuerpo_viejo = _abrir_flujo(cliente)
    assert _eventos(cuerpo_viejo)[0] == ("listo", {"dominios": DOMINIOS_COMPLETOS})

    _apagar_capacidad(motor, "tickets")

    with instalar_bus(eventos_iniciales=[sobre]):
        respuesta, cuerpo_nuevo = _abrir_flujo(cliente)

    assert respuesta.status_code == 200, cuerpo_nuevo
    eventos = _eventos(cuerpo_nuevo)
    assert eventos[0] == ("listo", {"dominios": DOMINIOS_SIN_TICKETS}), eventos
    assert all(
        "pedidos" not in datos.get("dominios", [])
        for _, datos in eventos
    ), f"el dominio apagado no debe aparecer en ningun frame: {eventos!r}"
    assert (
        "cambio",
        {"dominios": ["dashboard"], "motivo": "cambio"},
    ) in eventos, (
        "un sobre de pedidos con la capacidad apagada solo puede marcar "
        f"`dashboard`; se recibio {eventos!r}"
    )

    lectura = cliente.get(RUTA_TICKETS)
    assert lectura.status_code == 403, lectura.text


# ---------------------------------------------------------------------------
# AC-31: la reapertura reevalua la institucion desactivada
# ---------------------------------------------------------------------------


def test_la_reapertura_con_la_institucion_inactiva_responde_401_ac_31(
    cliente, motor, datos_base, identidad_actual, monkeypatch
):
    """La institucion inactiva no resuelve identidad: 401 antes del flujo.

    En SQLite el contexto logico unico usa `ambito_service`; se fuerza el
    dialecto PostgreSQL para ejercitar la misma rama de `contexto_tiempo_real`
    que corre en produccion (`tenant_service.resolver_contexto_solicitud` sobre
    el mapa de control), como en `test_institucion_inactiva_012.py`.
    """
    identidad_actual["actual"] = _identidad(
        datos_base, expira_en=int(time.time()) + 120
    )
    _sembrar_mapa_de_control(motor, datos_base["correo_usado"])
    _fijar_institucion_activa(motor, activo=False)
    monkeypatch.setattr(motor.dialect, "name", "postgresql")
    try:
        respuesta = cliente.get(RUTA_EVENTOS)
    finally:
        _fijar_institucion_activa(motor, activo=True)

    assert respuesta.status_code == 401, respuesta.text
    assert respuesta.headers["content-type"].startswith("application/json")
    assert "streaming" not in respuesta.headers.get("content-type", "")


def test_un_correo_sin_mapa_de_control_no_abre_el_flujo_ac_15(
    cliente, motor, datos_base, identidad_actual, monkeypatch
):
    """El aislamiento no degrada a alcance global: correo sin mapa -> 403."""
    identidad_actual["actual"] = _identidad(
        datos_base, expira_en=int(time.time()) + 120
    )
    _sembrar_mapa_de_control(motor, "otro.correo.t14@example.com")
    monkeypatch.setattr(motor.dialect, "name", "postgresql")

    respuesta = cliente.get(RUTA_EVENTOS)

    assert respuesta.status_code == 403, respuesta.text
    assert respuesta.headers["content-type"].startswith("application/json")
