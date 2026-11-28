"""Pruebas unitarias del servicio de publicacion de eventos (Feature 028, T4).

Fijan el sobre que produce cada mutacion (dominios, motivo y audiencia), la
resolucion de dueÃ±os en **una** consulta filtrada por institucion y sin
duplicados, y el fail-open total: un fallo del almacen o de la consulta de
dueÃ±os no propaga, deja un aviso acotado (sin PII) y nunca publica un sobre a
medias. El interruptor apagado corta antes de consultar o tocar el bus.

El bus falso vive en `tests/funcional/integracion/_soporte_eventos_028.py`
porque T5/T8 lo reutilizan. El conftest deja `TIEMPO_REAL_HABILITADO` apagado
y el almacen nulo; estas pruebas encienden el canal solo durante el escenario.
"""

import json

import pytest
from sqlalchemy.orm import sessionmaker

from app.core.eventos import SobreEvento
from app.models import Ticket, Usuario
from app.services import evento_service
from tests.funcional.integracion._soporte_eventos_028 import BusFalso, instalar_bus
from tests.funcional.integracion.soporte_observabilidad_024 import capturar_logs

#: Institucion de los `datos_base` de la suite.
INSTITUCION = "INST01"


class _SesionQueFalla:
    """Sesion cuyo `execute` revienta: simula una consulta de dueÃ±os rota."""

    def execute(self, *_args, **_kwargs):
        raise RuntimeError("consulta rota")


class _SesionProhibida:
    """Sesion que falla si alguien consulta: el interruptor apagado no debe."""

    def execute(self, *_args, **_kwargs):
        raise AssertionError("No debe consultarse la audiencia con el canal apagado")


@pytest.fixture
def bus():
    """Bus falso instalado con el canal encendido para el test."""
    with instalar_bus() as bus_falso:
        yield bus_falso


def _crear_usuario(motor, datos_base, correo: str) -> int:
    """Usuario adicional en el departamento de INST01 (dueÃ±o de un pedido)."""
    with sessionmaker(bind=motor)() as db:
        usuario = Usuario(
            nombre="Otro",
            apellido="Solicitante",
            correo=correo,
            departamento_id=datos_base["departamento_id"],
            rol_id=datos_base["rol_bodeguero_id"],
        )
        db.add(usuario)
        db.commit()
        db.refresh(usuario)
        return usuario.usuario_id


def _crear_ticket(
    motor,
    datos_base,
    *,
    usuario_id: int,
    institucion_id: str = INSTITUCION,
    asunto: str = "Pedido de prueba",
) -> int:
    """Ticket minimo para resolver la audiencia de dueÃ±os."""
    with sessionmaker(bind=motor)() as db:
        ticket = Ticket(
            usuario_id=usuario_id,
            prioridad_id=datos_base["prioridad_id"],
            estado_id=datos_base["estado_ingresado_id"],
            asunto=asunto,
            institucion_id=institucion_id,
        )
        db.add(ticket)
        db.commit()
        db.refresh(ticket)
        return ticket.ticket_id


def _avisos(lineas: list[str]) -> list[dict]:
    """Lineas JSON del aviso de publicacion degradada."""
    return [
        json.loads(linea)
        for linea in lineas
        if "publicacion_evento_degradada" in linea
    ]


# ---------------------------------------------------------------------------
# Sobre por mutacion: dominios, motivo y audiencia
# ---------------------------------------------------------------------------


def test_publicar_pedidos_produce_el_sobre_de_pedidos_con_su_dueno(bus):
    evento_service.publicar_pedidos("INST-001", "alta", {7})

    assert bus.publicados == [
        SobreEvento(
            institucion_id="INST-001",
            dominios=frozenset({"pedidos"}),
            motivo="alta",
            usuario_ids=frozenset({7}),
        )
    ]


def test_publicar_inventario_produce_inventario_sin_audiencia(bus):
    evento_service.publicar_inventario("INST-001", "movimiento")

    assert len(bus.publicados) == 1
    sobre = bus.publicados[0]
    assert sobre.dominios == {"inventario"}
    assert sobre.motivo == "movimiento"
    assert sobre.usuario_ids == frozenset()


def test_publicar_pedidos_e_inventario_conserva_los_duenos(bus):
    evento_service.publicar_pedidos_e_inventario("INST-001", "retiro", {7, 9})

    assert len(bus.publicados) == 1
    sobre = bus.publicados[0]
    assert sobre.dominios == {"pedidos", "inventario"}
    assert sobre.usuario_ids == {7, 9}


def test_publicar_compras_con_tickets_resuelve_duenos_y_anuncia_pedidos(
    motor, datos_base, bus
):
    usuario_a = datos_base["usuario_id"]
    usuario_b = _crear_usuario(motor, datos_base, "otro.solicitante@compustock.cl")
    ticket_a = _crear_ticket(motor, datos_base, usuario_id=usuario_a)
    ticket_b = _crear_ticket(motor, datos_base, usuario_id=usuario_b)

    with sessionmaker(bind=motor)() as db:
        evento_service.publicar_compras(
            INSTITUCION,
            "emision_oc",
            db=db,
            ticket_ids={ticket_a, ticket_b},
        )

    assert len(bus.publicados) == 1
    sobre = bus.publicados[0]
    assert sobre.dominios == {"compras", "pedidos"}
    assert sobre.motivo == "emision_oc"
    assert sobre.usuario_ids == {usuario_a, usuario_b}


def test_publicar_compras_sin_tickets_solo_anuncia_compras(bus):
    evento_service.publicar_compras("INST-001", "cancelacion_oc")

    assert len(bus.publicados) == 1
    assert bus.publicados[0].dominios == {"compras"}
    assert bus.publicados[0].usuario_ids == frozenset()


def test_publicar_compras_con_inventario_anade_el_dominio(bus):
    evento_service.publicar_compras("INST-001", "recepcion", con_inventario=True)

    assert len(bus.publicados) == 1
    assert bus.publicados[0].dominios == {"compras", "inventario"}
    assert bus.publicados[0].usuario_ids == frozenset()


def test_publicar_compras_filtra_por_institucion_y_no_duplica_duenos(
    motor, dos_instituciones, bus
):
    datos = dos_instituciones
    usuario_propio = datos["usuarios_inst01"]["Solicitante"]
    usuario_ajeno = datos["usuarios_inst02"]["Solicitante"]
    ticket_1 = _crear_ticket(motor, datos, usuario_id=usuario_propio)
    ticket_2 = _crear_ticket(motor, datos, usuario_id=usuario_propio)
    ticket_ajeno = _crear_ticket(
        motor,
        datos,
        usuario_id=usuario_ajeno,
        institucion_id=datos["inst_ajena"],
    )

    with sessionmaker(bind=motor)() as db:
        evento_service.publicar_compras(
            datos["inst_propia"],
            "recepcion",
            db=db,
            ticket_ids={ticket_1, ticket_2, ticket_ajeno},
        )

    sobre = bus.publicados[0]
    assert sobre.dominios == {"compras", "pedidos"}
    assert sobre.usuario_ids == {usuario_propio}


def test_publicar_compras_sin_duenos_resolubles_no_anuncia_pedidos(
    motor, dos_instituciones, bus
):
    datos = dos_instituciones
    usuario_ajeno = datos["usuarios_inst02"]["Solicitante"]
    ticket_ajeno = _crear_ticket(
        motor,
        datos,
        usuario_id=usuario_ajeno,
        institucion_id=datos["inst_ajena"],
    )

    with sessionmaker(bind=motor)() as db:
        evento_service.publicar_compras(
            datos["inst_propia"],
            "recepcion",
            db=db,
            ticket_ids={ticket_ajeno},
        )

    sobre = bus.publicados[0]
    assert sobre.dominios == {"compras"}
    assert sobre.usuario_ids == frozenset()


# ---------------------------------------------------------------------------
# Audiencia de tickets: una consulta, institucion y sin duplicados
# ---------------------------------------------------------------------------


def test_audiencia_de_tickets_sin_ids_no_consulta_la_base():
    assert (
        evento_service._audiencia_de_tickets(_SesionProhibida(), "INST-001", ())
        == set()
    )


def test_audiencia_de_tickets_sin_sesion_falla_cerrado():
    with pytest.raises(ValueError):
        evento_service._audiencia_de_tickets(None, "INST-001", {1})


def test_audiencia_de_tickets_devuelve_duenos_unicos(motor, datos_base):
    usuario_id = datos_base["usuario_id"]
    ticket_1 = _crear_ticket(motor, datos_base, usuario_id=usuario_id)
    ticket_2 = _crear_ticket(motor, datos_base, usuario_id=usuario_id)

    with sessionmaker(bind=motor)() as db:
        audiencia = evento_service._audiencia_de_tickets(
            db, INSTITUCION, {ticket_1, ticket_2}
        )

    assert audiencia == {usuario_id}


# ---------------------------------------------------------------------------
# Fail-open: el almacen o la consulta fallan, la mutacion no se entera
# ---------------------------------------------------------------------------


def test_un_fallo_de_la_consulta_de_duenos_no_publica_ni_propaga():
    with instalar_bus() as bus:
        with capturar_logs() as lineas:
            evento_service.publicar_compras(
                INSTITUCION,
                "recepcion",
                db=_SesionQueFalla(),
                ticket_ids={1, 2},
            )

    assert bus.publicados == []
    avisos = _avisos(lineas)
    assert len(avisos) == 1
    assert avisos[0]["error_type"] == "RuntimeError"
    assert "consulta rota" not in "".join(lineas)
    assert "Traceback" not in "".join(lineas)


def test_un_fallo_del_almacen_no_publica_a_medias_ni_propaga():
    with instalar_bus(
        error_al_publicar=ConnectionError("redis caido")
    ) as bus:
        with capturar_logs() as lineas:
            evento_service.publicar_pedidos("INST-001", "alta", {7})

    assert bus.publicados == []
    avisos = _avisos(lineas)
    assert len(avisos) == 1
    assert avisos[0]["error_type"] == "ConnectionError"
    assert "redis caido" not in "".join(lineas)


def test_el_aviso_de_publicacion_se_acota_a_uno_cada_diez_segundos():
    with instalar_bus() as bus:
        bus.error_al_publicar = ConnectionError("redis caido")
        with capturar_logs() as lineas:
            evento_service.publicar_pedidos("INST-001", "alta", {7})
            evento_service.publicar_pedidos("INST-001", "edicion", {7})

    assert bus.publicados == []
    assert len(_avisos(lineas)) == 1


def test_un_motivo_desconocido_no_propaga_y_avisa(bus):
    with capturar_logs() as lineas:
        evento_service.publicar_pedidos("INST-001", "motivo-invalido", {7})

    assert bus.publicados == []
    avisos = _avisos(lineas)
    assert len(avisos) == 1
    assert avisos[0]["error_type"] == "ValueError"


def test_el_interruptor_apagado_no_consulta_ni_publica():
    with instalar_bus(habilitado=False) as bus:
        with capturar_logs() as lineas:
            evento_service.publicar_compras(
                INSTITUCION,
                "recepcion",
                db=_SesionProhibida(),
                ticket_ids={1},
            )
            evento_service.publicar_pedidos("INST-001", "alta", {7})

    assert bus.publicados == []
    assert _avisos(lineas) == []
