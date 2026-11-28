"""Filtro por conexion del canal SSE (Feature 028, T6).

Seam bajo prueba: el endpoint real `GET /api/v1/eventos/` con `TestClient` y el
`BusFalso` de T4, que entrega los sobres internos del escenario. Cada flujo se
acota (vida maxima y latido de 1 s) porque `TestClient` bufferiza el cuerpo y
espera el cierre (nota de T0).

Casos: aislamiento por institucion (canal y comprobacion del sobre), fan-out al
Solicitante dueno y silencio para otro Solicitante de la misma institucion
(guardrail AC-16/D-5), visibilidad de `pedidos` para Administrador y Bodeguero,
marca sintetica `dashboard` con `tickets`/`inventario` apagados, ausencia de la
marca por `compras`, una sola marca por sobre, conjunto visible vacio sin frame
y ausencia de identificadores en el frame serializado.
"""

import json
import time

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.eventos import SobreEvento
from app.models import Rol, Usuario
from app.models.control_canonico import FuncionInstitucion
from app.services.auth_service import IdentidadAutenticada

from tests.funcional.integracion._soporte_eventos_028 import instalar_bus

RUTA = "/api/v1/eventos/"
CANAL_INST01 = "compustock:eventos:INST01"
CANAL_INST02 = "compustock:eventos:INST02"


@pytest.fixture(autouse=True)
def flujo_acotado(monkeypatch):
    """Acota todo flujo del modulo: `TestClient` espera el cuerpo completo."""
    monkeypatch.setattr(settings, "VIDA_MAXIMA_CONEXION_SEGUNDOS", 1)
    monkeypatch.setattr(settings, "TIEMPO_REAL_LATIDO_SEGUNDOS", 1)


def _identidad(
    *,
    usuario_id: int,
    rol: str,
    departamento_id: int,
    correo: str,
) -> IdentidadAutenticada:
    """Identidad suelta con ids reales; la institucion sale del departamento."""
    usuario = Usuario(
        usuario_id=usuario_id,
        nombre=rol,
        apellido="Prueba",
        correo=correo,
        departamento_id=departamento_id,
        rol_id=1,
    )
    usuario.rol = Rol(nombre_rol=rol)
    return IdentidadAutenticada(
        usuario=usuario,
        sub=f"sub-filtro-028-{rol.lower()}",
        expira_en=int(time.time()) + 300,
    )


def _administrador_inst01(datos) -> IdentidadAutenticada:
    return _identidad(
        usuario_id=datos["usuario_id"],
        rol="Administrador",
        departamento_id=datos["departamento_id"],
        correo=datos["correo_usado"],
    )


def _solicitante_inst01(datos, usuario_id: int) -> IdentidadAutenticada:
    return _identidad(
        usuario_id=usuario_id,
        rol="Solicitante",
        departamento_id=datos["departamento_id"],
        correo=f"solicitante.{usuario_id}.inst01@compustock.cl",
    )


def _crear_solicitante_inst01(motor, datos) -> int:
    """Segundo Solicitante persistido en INST01, distinto del dueño."""
    with sessionmaker(bind=motor)() as db:
        rol_id = db.execute(
            select(Rol.rol_id).where(Rol.nombre_rol == "Solicitante")
        ).scalar_one()
        usuario = Usuario(
            nombre="Otro",
            apellido="Solicitante",
            correo="otro.solicitante.inst01@compustock.cl",
            departamento_id=datos["departamento_id"],
            rol_id=rol_id,
        )
        db.add(usuario)
        db.commit()
        db.refresh(usuario)
        return usuario.usuario_id


def _apagar_capacidad(motor, institucion_id: str, funcion: str) -> None:
    """Desactiva una capacidad funcional de la institucion (fila explicita)."""
    with sessionmaker(bind=motor)() as db:
        db.add(
            FuncionInstitucion(
                institucion_id=institucion_id,
                funcion=funcion,
                habilitada=False,
            )
        )
        db.commit()


def _sobre(
    dominios: set[str],
    *,
    motivo: str,
    institucion_id: str,
    usuario_ids=(),
) -> SobreEvento:
    return SobreEvento(
        institucion_id=institucion_id,
        dominios=frozenset(dominios),
        motivo=motivo,
        usuario_ids=frozenset(usuario_ids),
    )


def _abrir_flujo(cliente, ruta: str = RUTA):
    """Abre el flujo y devuelve `(respuesta, cuerpo)` ya completos."""
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


def _cambios(cuerpo: str) -> list[dict]:
    return [datos for evento, datos in _eventos(cuerpo) if evento == "cambio"]


# ---------------------------------------------------------------------------
# Aislamiento por institucion (AC-15)
# ---------------------------------------------------------------------------


def test_la_institucion_ajena_no_recibe_el_sobre_de_otra_institucion(
    cliente, dos_instituciones, identidad_actual
):
    """AC-15/TD-2: canal por identidad y comprobacion del sobre al recibir."""
    datos = dos_instituciones
    identidad_actual["actual"] = _identidad(
        usuario_id=datos["usuarios_inst02"]["Administrador"],
        rol="Administrador",
        departamento_id=datos["departamento_ajeno_id"],
        correo="administrador.inst02@compustock.cl",
    )
    sobre = _sobre(
        {"pedidos"},
        motivo="alta",
        institucion_id=datos["inst_propia"],
        usuario_ids={datos["usuario_id"]},
    )

    with instalar_bus(eventos_iniciales=[sobre]) as bus:
        respuesta, cuerpo = _abrir_flujo(
            cliente, f"{RUTA}?institucion_id={datos['inst_propia']}"
        )

    assert respuesta.status_code == 200
    assert bus.canales == [CANAL_INST02], (
        "la suscripcion sale solo de la identidad, no de la query"
    )
    assert _eventos(cuerpo)[0] == (
        "listo",
        {"dominios": ["pedidos", "inventario", "compras", "dashboard"]},
    )
    assert _cambios(cuerpo) == []


# ---------------------------------------------------------------------------
# Audiencia de pedidos: dueno, Administrador y Bodeguero (AC-16/AC-27)
# ---------------------------------------------------------------------------


def test_solicitante_dueno_recibe_el_cambio_de_su_pedido(
    cliente, dos_instituciones, identidad_actual
):
    datos = dos_instituciones
    dueno = datos["usuarios_inst01"]["Solicitante"]
    identidad_actual["actual"] = _solicitante_inst01(datos, dueno)
    sobre = _sobre(
        {"pedidos"},
        motivo="alta",
        institucion_id=datos["inst_propia"],
        usuario_ids={dueno},
    )

    with instalar_bus(eventos_iniciales=[sobre]):
        _, cuerpo = _abrir_flujo(cliente)

    assert _cambios(cuerpo) == [{"dominios": ["pedidos"], "motivo": "alta"}]


def test_otro_solicitante_no_recibe_ni_la_marca_por_un_pedido_ajeno(
    cliente, motor, dos_instituciones, identidad_actual
):
    """Guardrail AC-16/D-5: la marca solo se sintetiza dentro de la audiencia.

    La conexion tiene `dashboard` encendido (esta en `listo`), pero el evento es
    un pedido de otro Solicitante: no recibe ni `pedidos` ni la marca, y su
    tablero no se refresca.
    """
    datos = dos_instituciones
    dueno = datos["usuarios_inst01"]["Solicitante"]
    ajeno = _crear_solicitante_inst01(motor, datos)
    identidad_actual["actual"] = _solicitante_inst01(datos, ajeno)
    sobre = _sobre(
        {"pedidos"},
        motivo="alta",
        institucion_id=datos["inst_propia"],
        usuario_ids={dueno},
    )

    with instalar_bus(eventos_iniciales=[sobre]):
        _, cuerpo = _abrir_flujo(cliente)

    listo, dominios_listos = _eventos(cuerpo)[0]
    assert listo == "listo"
    assert "dashboard" in dominios_listos["dominios"]
    assert "pedidos" in dominios_listos["dominios"]
    assert _cambios(cuerpo) == []
    assert "event: cambio" not in cuerpo


@pytest.mark.parametrize("rol", ["Administrador", "Bodeguero"])
def test_administrador_y_bodeguero_reciben_el_cambio_de_pedidos(
    cliente, dos_instituciones, identidad_actual, rol
):
    datos = dos_instituciones
    if rol == "Administrador":
        identidad = _administrador_inst01(datos)
    else:
        identidad = _identidad(
            usuario_id=datos["usuarios_inst01"]["Bodeguero"],
            rol=rol,
            departamento_id=datos["departamento_id"],
            correo="bodeguero.inst01@compustock.cl",
        )
    identidad_actual["actual"] = identidad
    sobre = _sobre(
        {"pedidos"},
        motivo="cambio_estado",
        institucion_id=datos["inst_propia"],
        usuario_ids={datos["usuarios_inst01"]["Solicitante"]},
    )

    with instalar_bus(eventos_iniciales=[sobre]):
        _, cuerpo = _abrir_flujo(cliente)

    assert _cambios(cuerpo) == [
        {"dominios": ["pedidos"], "motivo": "cambio_estado"}
    ]


# ---------------------------------------------------------------------------
# Visibilidad por rol/capacidad y marca `dashboard` (AC-17/AC-28)
# ---------------------------------------------------------------------------


def test_tickets_apagado_entrega_solo_la_marca_dashboard_sin_el_motivo_real(
    cliente, motor, dos_instituciones, identidad_actual
):
    """AC-28: el frame no nombra `pedidos` ni revela el motivo real."""
    datos = dos_instituciones
    _apagar_capacidad(motor, datos["inst_propia"], "tickets")
    identidad_actual["actual"] = _administrador_inst01(datos)
    sobre = _sobre(
        {"pedidos"},
        motivo="alta",
        institucion_id=datos["inst_propia"],
        usuario_ids={datos["usuario_id"]},
    )

    with instalar_bus(eventos_iniciales=[sobre]):
        _, cuerpo = _abrir_flujo(cliente)

    assert _cambios(cuerpo) == [{"dominios": ["dashboard"], "motivo": "cambio"}]
    frame = cuerpo.split("event: cambio", 1)[1].split("\n\n", 1)[0]
    assert "pedidos" not in frame
    assert "alta" not in frame


def test_inventario_apagado_entrega_la_marca_dashboard(
    cliente, motor, dos_instituciones, identidad_actual
):
    datos = dos_instituciones
    _apagar_capacidad(motor, datos["inst_propia"], "inventario")
    identidad_actual["actual"] = _administrador_inst01(datos)
    sobre = _sobre(
        {"inventario"},
        motivo="movimiento",
        institucion_id=datos["inst_propia"],
    )

    with instalar_bus(eventos_iniciales=[sobre]):
        _, cuerpo = _abrir_flujo(cliente)

    assert _cambios(cuerpo) == [{"dominios": ["dashboard"], "motivo": "cambio"}]


def test_compras_apagado_no_emite_compras_ni_la_marca_dashboard(
    cliente, motor, dos_instituciones, identidad_actual
):
    """D-13: `compras` no sustituye por `dashboard`; sin visibilidad, nada."""
    datos = dos_instituciones
    _apagar_capacidad(motor, datos["inst_propia"], "compras")
    identidad_actual["actual"] = _administrador_inst01(datos)
    sobre = _sobre(
        {"compras"},
        motivo="emision_oc",
        institucion_id=datos["inst_propia"],
    )

    with instalar_bus(eventos_iniciales=[sobre]):
        _, cuerpo = _abrir_flujo(cliente)

    assert _cambios(cuerpo) == []
    assert "event: cambio" not in cuerpo


def test_pedidos_e_inventario_apagados_producen_un_solo_frame_dashboard(
    cliente, motor, dos_instituciones, identidad_actual
):
    """AC-28: dos dominios ocultos comparten una unica marca."""
    datos = dos_instituciones
    _apagar_capacidad(motor, datos["inst_propia"], "tickets")
    _apagar_capacidad(motor, datos["inst_propia"], "inventario")
    identidad_actual["actual"] = _administrador_inst01(datos)
    sobre = _sobre(
        {"pedidos", "inventario"},
        motivo="retiro",
        institucion_id=datos["inst_propia"],
        usuario_ids={datos["usuario_id"]},
    )

    with instalar_bus(eventos_iniciales=[sobre]):
        _, cuerpo = _abrir_flujo(cliente)

    assert _cambios(cuerpo) == [{"dominios": ["dashboard"], "motivo": "cambio"}]
    assert cuerpo.count("event: cambio") == 1


def test_un_sobre_cuyo_conjunto_visible_queda_vacio_no_emite_frame(
    cliente, dos_instituciones, identidad_actual
):
    """AC-17: el Solicitante no ve `compras`; un evento de OC no le llega."""
    datos = dos_instituciones
    identidad_actual["actual"] = _solicitante_inst01(
        datos, datos["usuarios_inst01"]["Solicitante"]
    )
    sobre = _sobre(
        {"compras"},
        motivo="cancelacion_oc",
        institucion_id=datos["inst_propia"],
    )

    with instalar_bus(eventos_iniciales=[sobre]):
        _, cuerpo = _abrir_flujo(cliente)

    assert _cambios(cuerpo) == []
    assert "event: cambio" not in cuerpo


def test_el_frame_serializado_no_lleva_ids_ni_institucion_ni_usuario(
    cliente, motor, dos_instituciones, identidad_actual
):
    """AC-18/AC-27: el sobre no se serializa; solo dominios, motivo y estado."""
    datos = dos_instituciones
    _apagar_capacidad(motor, datos["inst_propia"], "tickets")
    dueno = datos["usuarios_inst01"]["Solicitante"]
    identidad_actual["actual"] = _administrador_inst01(datos)
    sobre = _sobre(
        {"pedidos"},
        motivo="alta",
        institucion_id=datos["inst_propia"],
        usuario_ids={dueno},
    )

    with instalar_bus(eventos_iniciales=[sobre]):
        _, cuerpo = _abrir_flujo(cliente)

    assert _cambios(cuerpo) == [{"dominios": ["dashboard"], "motivo": "cambio"}]
    for prohibido in (
        '"institucion_id"',
        '"usuario_id"',
        '"usuario_ids"',
        '"ticket_id"',
        datos["inst_propia"],
        f'"{dueno}"',
        "alta",
    ):
        assert prohibido not in cuerpo, prohibido
