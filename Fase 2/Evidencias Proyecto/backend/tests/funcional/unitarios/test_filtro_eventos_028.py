"""Pruebas unitarias del filtro por conexion del canal SSE (Feature 028, T6).

Seam bajo prueba: `_dominios_visibles_del_sobre(contexto, sobre)`, la funcion
pura que traduce el sobre interno del bus al frame de **una** conexion. El orden
del filtro es el de la spec §5.3: institucion, audiencia de dueno de `pedidos`,
visibilidad por rol/capacidad y sustitucion por la marca `dashboard`.

Casos fijados: aislamiento institucional; fan-out al Solicitante dueno y silencio
para el no dueno **aunque tenga `dashboard`** (guardrail de AC-16/D-5);
`dashboard` sintetico solo si el dominio oculto es `pedidos` o `inventario` y la
capacidad `dashboard` esta encendida; una sola marca por sobre; motivo `cambio`
sin revelar el real; conjunto vacio sin frame; y orden canonico del contrato.
"""

import pytest

from app.api.dependencies import ContextoTiempoReal
from app.api.v1.endpoints.eventos import _dominios_visibles_del_sobre
from app.core.eventos import SobreEvento

#: Los cuatro dominios que puede ver una conexion con todas las capacidades.
TODOS = frozenset({"pedidos", "inventario", "compras", "dashboard"})


def _contexto(
    *,
    rol: str = "Administrador",
    usuario_id: int = 7,
    institucion_id: str = "INST01",
    dominios_visibles: frozenset[str] = TODOS,
) -> ContextoTiempoReal:
    """Copia inmutable del contexto de una conexion, sin base ni red."""
    return ContextoTiempoReal(
        usuario_id=usuario_id,
        rol=rol,
        institucion_id=institucion_id,
        expira_en=None,
        dominios_visibles=frozenset(dominios_visibles),
        request_id=None,
    )


def _sobre(
    dominios: set[str] | frozenset[str],
    *,
    motivo: str = "alta",
    institucion_id: str = "INST01",
    usuario_ids: set[int] | frozenset[int] = frozenset(),
) -> SobreEvento:
    """Sobre interno con dominios de origen y audiencia de duenos."""
    return SobreEvento(
        institucion_id=institucion_id,
        dominios=frozenset(dominios),
        motivo=motivo,
        usuario_ids=frozenset(usuario_ids),
    )


# ---------------------------------------------------------------------------
# Aislamiento institucional
# ---------------------------------------------------------------------------


def test_sobre_de_otra_institucion_se_descarta_aunque_el_dominio_sea_visible():
    """AC-15/TD-2: el canal no basta; el sobre se comprueba por institucion."""
    sobre = _sobre({"pedidos"}, institucion_id="INST02")

    assert _dominios_visibles_del_sobre(_contexto(), sobre) is None


# ---------------------------------------------------------------------------
# Audiencia de pedidos: dueno, Administrador y Bodeguero
# ---------------------------------------------------------------------------


def test_solicitante_dueno_recibe_sus_pedidos():
    """AC-16/AC-27: el dueno ve `pedidos` con el motivo real."""
    contexto = _contexto(rol="Solicitante", usuario_id=7)
    sobre = _sobre({"pedidos"}, motivo="edicion", usuario_ids={7})

    assert _dominios_visibles_del_sobre(contexto, sobre) == (["pedidos"], "edicion")


def test_solicitante_no_dueno_no_recibe_ni_la_marca_dashboard():
    """Guardrail AC-16/D-5: un pedido ajeno no produce frame ni marca.

    La conexion tiene `dashboard` encendido (esta en `dominios_visibles`), de
    modo que el unico motivo por el que no recibe nada es que la audiencia de
    dueno se resuelve **antes** de sintetizar la marca.
    """
    contexto = _contexto(rol="Solicitante", usuario_id=8)
    sobre = _sobre({"pedidos"}, motivo="alta", usuario_ids={7})

    assert "dashboard" in contexto.dominios_visibles
    assert _dominios_visibles_del_sobre(contexto, sobre) is None


def test_solicitante_no_dueno_no_recibe_ni_la_marca_sin_audiencia_en_el_sobre():
    """El silencio tambien aplica cuando el sobre no declara dueños."""
    contexto = _contexto(rol="Solicitante", usuario_id=8)

    assert _dominios_visibles_del_sobre(contexto, _sobre({"pedidos"})) is None


def test_solicitante_no_dueno_recibe_solo_el_inventario_del_retiro_ajeno():
    """Un retiro ajeno no revela `pedidos`, pero el stock si le incumbe."""
    contexto = _contexto(rol="Solicitante", usuario_id=8)
    sobre = _sobre({"pedidos", "inventario"}, motivo="retiro", usuario_ids={7})

    assert _dominios_visibles_del_sobre(contexto, sobre) == (
        ["inventario"],
        "retiro",
    )


@pytest.mark.parametrize("rol", ["Administrador", "Bodeguero"])
def test_administrador_y_bodeguero_reciben_los_pedidos_de_la_institucion(rol):
    """AC-16: los roles operativos no dependen de la audiencia de duenos."""
    contexto = _contexto(rol=rol, usuario_id=9)
    sobre = _sobre({"pedidos"}, motivo="aprobacion", usuario_ids={7})

    assert _dominios_visibles_del_sobre(contexto, sobre) == (
        ["pedidos"],
        "aprobacion",
    )


# ---------------------------------------------------------------------------
# Visibilidad por rol/capacidad y marca `dashboard`
# ---------------------------------------------------------------------------


def test_pedidos_oculto_por_capacidad_se_sustituye_por_una_marca_dashboard():
    """AC-28: `tickets` apagado + `dashboard` encendido -> solo la marca."""
    contexto = _contexto(dominios_visibles=TODOS - {"pedidos"})
    sobre = _sobre({"pedidos"}, motivo="alta", usuario_ids={7})

    resultado = _dominios_visibles_del_sobre(contexto, sobre)

    assert resultado == (["dashboard"], "cambio")
    assert "pedidos" not in resultado[0]
    assert resultado[1] != sobre.motivo


def test_inventario_oculto_por_capacidad_se_sustituye_por_una_marca_dashboard():
    """AC-28: un movimiento de stock oculto tambien invalida el dashboard."""
    contexto = _contexto(dominios_visibles=TODOS - {"inventario"})
    sobre = _sobre({"inventario"}, motivo="movimiento")

    assert _dominios_visibles_del_sobre(contexto, sobre) == (
        ["dashboard"],
        "cambio",
    )


def test_compras_oculto_no_sintetiza_la_marca_dashboard():
    """AC-17/D-13: `compras` no afecta al dashboard; sin visibilidad, nada."""
    contexto = _contexto(dominios_visibles=TODOS - {"compras"})
    sobre = _sobre({"compras"}, motivo="emision_oc")

    assert _dominios_visibles_del_sobre(contexto, sobre) is None


def test_sin_capacidad_dashboard_un_dominio_oculto_no_emite_frame():
    """AC-17: sin `dashboard`, un dominio oculto no deja ninguna marca."""
    contexto = _contexto(dominios_visibles=frozenset({"inventario"}))
    sobre = _sobre({"pedidos"}, motivo="alta", usuario_ids={7})

    assert _dominios_visibles_del_sobre(contexto, sobre) is None


def test_dos_dominios_ocultos_producen_una_sola_marca_dashboard():
    """AC-28: la marca se anade como maximo una vez por sobre."""
    contexto = _contexto(dominios_visibles=TODOS - {"pedidos", "inventario"})
    sobre = _sobre(
        {"pedidos", "inventario"}, motivo="retiro", usuario_ids={7}
    )

    assert _dominios_visibles_del_sobre(contexto, sobre) == (
        ["dashboard"],
        "cambio",
    )


def test_el_motivo_se_normaliza_a_cambio_si_hay_marca_aunque_haya_dominio_visible():
    """Plan §5.4: con marca sintetica el frame no revela el motivo real."""
    contexto = _contexto(dominios_visibles={"inventario", "dashboard"})
    sobre = _sobre(
        {"pedidos", "inventario"}, motivo="retiro", usuario_ids={7}
    )

    assert _dominios_visibles_del_sobre(contexto, sobre) == (
        ["inventario", "dashboard"],
        "cambio",
    )


# ---------------------------------------------------------------------------
# Conjunto vacio y orden canonico
# ---------------------------------------------------------------------------


def test_un_sobre_sin_dominios_visibles_no_emite_frame():
    """El Solicitante no tiene `compras`: un evento de compras no le llega."""
    contexto = _contexto(
        rol="Solicitante",
        usuario_id=7,
        dominios_visibles={"pedidos", "inventario", "dashboard"},
    )
    sobre = _sobre({"compras"}, motivo="facturacion_oc")

    assert _dominios_visibles_del_sobre(contexto, sobre) is None


def test_los_dominios_conservan_el_orden_canonico_y_el_motivo_real():
    """Contrato §6.1: `pedidos`, `inventario`, `compras`, `dashboard`."""
    contexto = _contexto()
    sobre = _sobre(
        {"compras", "inventario", "pedidos"}, motivo="recepcion", usuario_ids={7}
    )

    assert _dominios_visibles_del_sobre(contexto, sobre) == (
        ["pedidos", "inventario", "compras"],
        "recepcion",
    )
