"""Pruebas unitarias del nucleo de eventos de la Feature 028 (T1).

Fijan la configuracion del canal, el sobre interno inmutable y su JSON sin
campos extra, el almacen nulo que usa la suite heredada y el canal por
institucion. Sin `pytest-asyncio`: cada escenario asincrono se envuelve en
`asyncio.run`.
"""

import asyncio
import json
import socket
from dataclasses import FrozenInstanceError

import pytest
from pydantic import ValidationError

from app.core import eventos
from app.core.config import Settings
from app.core.eventos import (
    DOMINIOS,
    MOTIVOS,
    AlmacenNulo,
    SobreEvento,
    canal_de_institucion,
    deserializar_sobre,
    serializar_sobre,
)

VARIABLES = (
    "TIEMPO_REAL_HABILITADO",
    "TIEMPO_REAL_LATIDO_SEGUNDOS",
    "MARGEN_RELOJ_SEGUNDOS",
    "VIDA_MAXIMA_CONEXION_SEGUNDOS",
)

#: Conjunto cerrado del contrato (§2.2 del plan): los trece motivos de origen
#: mas `cambio`, que solo usa la marca sintetica de dashboard.
MOTIVOS_ESPERADOS = {
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


@pytest.fixture
def entorno_limpio(monkeypatch):
    """Borra las variables del canal para que el shell no altere los defaults."""
    for variable in VARIABLES:
        monkeypatch.delenv(variable, raising=False)
    return monkeypatch


def _configuracion(**cambios) -> Settings:
    """`Settings` aislado del `.env`, igual que el resto de unitarios."""
    return Settings(_env_file=None, **cambios)


# ---------------------------------------------------------------------------
# Configuracion del canal
# ---------------------------------------------------------------------------


def test_defaults_del_tiempo_real(entorno_limpio):
    configuracion = _configuracion()

    assert configuracion.TIEMPO_REAL_HABILITADO is True
    assert configuracion.TIEMPO_REAL_LATIDO_SEGUNDOS == 25
    assert configuracion.MARGEN_RELOJ_SEGUNDOS == 10
    assert configuracion.VIDA_MAXIMA_CONEXION_SEGUNDOS == 300


@pytest.mark.parametrize(
    ("variable", "valor"),
    [
        ("TIEMPO_REAL_LATIDO_SEGUNDOS", "0"),
        ("TIEMPO_REAL_LATIDO_SEGUNDOS", "31"),
        ("MARGEN_RELOJ_SEGUNDOS", "0"),
        ("VIDA_MAXIMA_CONEXION_SEGUNDOS", "0"),
    ],
)
def test_valores_fuera_de_rango_impiden_construir(
    entorno_limpio, variable, valor
):
    with pytest.raises(ValidationError) as error:
        _configuracion(**{variable: valor})

    assert variable in str(error.value)


@pytest.mark.parametrize(
    ("variable", "valor"),
    [
        ("TIEMPO_REAL_LATIDO_SEGUNDOS", "1"),
        ("TIEMPO_REAL_LATIDO_SEGUNDOS", "30"),
        ("MARGEN_RELOJ_SEGUNDOS", "1"),
        ("VIDA_MAXIMA_CONEXION_SEGUNDOS", "1"),
    ],
)
def test_los_extremos_del_rango_son_validos(entorno_limpio, variable, valor):
    configuracion = _configuracion(**{variable: valor})

    assert getattr(configuracion, variable) == int(valor)


def test_interruptor_lee_valores_booleanos_de_texto(entorno_limpio):
    assert _configuracion(TIEMPO_REAL_HABILITADO="false").TIEMPO_REAL_HABILITADO is False
    assert _configuracion(TIEMPO_REAL_HABILITADO="true").TIEMPO_REAL_HABILITADO is True


# ---------------------------------------------------------------------------
# Constantes y sobre interno
# ---------------------------------------------------------------------------


def test_dominios_de_origen_son_los_tres_del_contrato():
    assert DOMINIOS == {"pedidos", "inventario", "compras"}


def test_motivos_son_los_del_contrato_e_incluyen_cambio():
    assert MOTIVOS == MOTIVOS_ESPERADOS


def _sobre(**cambios) -> SobreEvento:
    datos = {
        "institucion_id": "INST-001",
        "dominios": frozenset({"pedidos"}),
        "motivo": "alta",
        "usuario_ids": frozenset({7}),
    }
    datos.update(cambios)
    return SobreEvento(**datos)


def test_sobre_evento_es_inmutable():
    sobre = _sobre()

    with pytest.raises(FrozenInstanceError):
        sobre.motivo = "edicion"
    with pytest.raises(FrozenInstanceError):
        sobre.dominios = frozenset({"inventario"})


def test_sobre_evento_copia_los_conjuntos_como_inmutables():
    sobre = SobreEvento(
        institucion_id="INST-001",
        dominios={"pedidos"},
        motivo="alta",
        usuario_ids={7},
    )

    assert isinstance(sobre.dominios, frozenset)
    assert isinstance(sobre.usuario_ids, frozenset)


def test_json_del_sobre_conserva_los_cuatro_campos_y_ninguno_extra():
    sobre = _sobre(
        dominios=frozenset({"pedidos", "inventario"}),
        usuario_ids=frozenset({3, 7}),
    )

    documento = json.loads(serializar_sobre(sobre))

    assert set(documento) == {
        "institucion_id",
        "dominios",
        "motivo",
        "usuario_ids",
    }
    assert documento["institucion_id"] == "INST-001"
    assert documento["dominios"] == ["inventario", "pedidos"]
    assert documento["motivo"] == "alta"
    assert documento["usuario_ids"] == [3, 7]
    assert deserializar_sobre(serializar_sobre(sobre)) == sobre


# ---------------------------------------------------------------------------
# Almacen nulo y seams
# ---------------------------------------------------------------------------


class _AlmacenEspia:
    """Doble minimo para comprobar los seams sin abrir Redis."""

    def __init__(self):
        self.publicados = []
        self.cerrado = False

    def publicar(self, sobre):
        self.publicados.append(sobre)

    async def suscribir(self, canal):
        raise AssertionError("El espia no se suscribe en estas pruebas")

    async def cerrar(self):
        self.cerrado = True


def test_almacen_nulo_no_publica_no_abre_redis_ni_entrega_nada(monkeypatch):
    def conectar_prohibido(*_args, **_kwargs):
        raise AssertionError("AlmacenNulo no debe abrir conexiones")

    almacen = AlmacenNulo()

    async def escenario():
        # El parche va dentro del escenario: el ProactorEventLoop de Windows
        # crea su self-pipe con `socketpair()` y `connect()` al construirse.
        with monkeypatch.context() as parche:
            parche.setattr(socket.socket, "connect", conectar_prohibido)

            almacen.publicar(_sobre())
            suscripcion = await almacen.suscribir(
                canal_de_institucion("INST-001")
            )
            try:
                return await suscripcion.recibir(timeout=0.01)
            finally:
                await suscripcion.cerrar()
                await almacen.cerrar()

    assert asyncio.run(escenario()) is None


def test_configurar_y_obtener_almacen_devuelven_el_configurado():
    previo = eventos.obtener_almacen()
    espia = _AlmacenEspia()
    try:
        eventos.configurar_almacen(espia)

        assert eventos.obtener_almacen() is espia
    finally:
        eventos.configurar_almacen(previo)


def test_cerrar_almacen_cierra_el_configurado():
    previo = eventos.obtener_almacen()
    espia = _AlmacenEspia()
    try:
        eventos.configurar_almacen(espia)

        asyncio.run(eventos.cerrar_almacen())

        assert espia.cerrado is True
    finally:
        eventos.configurar_almacen(previo)


# ---------------------------------------------------------------------------
# Canal por institucion
# ---------------------------------------------------------------------------


def test_canal_de_institucion_compone_el_prefijo_del_bus():
    assert canal_de_institucion("INST-001") == "compustock:eventos:INST-001"


@pytest.mark.parametrize("institucion_id", ["", "   ", None])
def test_canal_de_institucion_rechaza_identificadores_vacios(institucion_id):
    with pytest.raises(ValueError):
        canal_de_institucion(institucion_id)
