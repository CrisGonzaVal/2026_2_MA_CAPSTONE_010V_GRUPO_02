"""Feature 013 (ampliacion 25/Nov/2026): read model de proceso por lote.

Seam bajo prueba: la interfaz HTTP que consumen el tablero y el detalle
(`GET /api/v1/tickets/` y `GET /api/v1/tickets/{id}`), nunca la sesion. Cubre:

- **AC-37/AC-63**: `EnRevision`, `Anulado` y `Cerrado` (con y sin
  confirmacion de entrega) exponen `etiqueta_proceso` y `explicacion_proceso`
  en el listado y en el detalle. `Pendiente` ya no tiene etiqueta propia.
- **AC-38**: en `EnCurso`, la OC activa mas avanzada decide la etiqueta con la
  escala `Recibida` > `Facturada` > `Emitida`; `Cancelada` no cuenta y sin
  cobertura decide `stock_disponible`.
- **AC-39**: `stock_disponible` se simula **por sede** (no por institucion),
  los siete campos del read model coinciden entre listado y detalle y el
  detalle conserva `asignaciones`/`cadena_productos`.
- **AC-40**: `gestionado_por_bodeguero`/`gestionado_por_administrador` son el
  ultimo actor por `fecha_transicion DESC`, `historial_transicion_id DESC`
  con su rol **vigente**; la fila de creacion cuenta; sin filas, `None`.

Ademas, el listado no puede hacer N+1: el numero de consultas es el mismo con
1 y con N pedidos (patron `before_cursor_execute` de `test_tablero_kanban.py`).
"""

import itertools
from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy import event, select

from app.models import (
    DetalleOrdenCompra,
    DetalleTicket,
    HistorialTransicionTicket,
    OrdenCompra,
    OrdenCompraTicket,
    ProveedorControl,
    Rol,
    Ticket,
    Usuario,
)
from app.services.ticket_proceso import MOTIVO_CONFIRMACION_ENTREGA

from tests.funcional.integracion._soporte_ciclo_vida_013 import (
    abrir_ticket,
    cliente_con_rol,
    leer_historial,
    payload_alta,
    sembrar_ticket,
)
from tests.funcional.integracion._soporte_ciclo_vida_catalogo_014 import (
    cliente_de_rol,
    fijar_stock_sede,
    sembrar_mundo_014,
)
from tests.funcional.integracion._soporte_sede_011 import (
    crear_sede,
    crear_stock_sede,
    sesion,
)

#: Frases cortas literales de la spec §9.8 (fuente independiente del codigo).
FRASE_EN_REVISION = (
    "En revisión: estado inicial; se aprueba con la acción Aprobar."
)
FRASE_EN_COMPRA = "En compra: la orden está emitida y pendiente de facturación."
FRASE_FACTURADO = (
    "Facturado: la compra está facturada y pendiente de recepción."
)
FRASE_EN_CONFIRMACION_STOCK = (
    "En confirmación de stock local: el stock local está disponible; falta que "
    "el Bodeguero lo confirme y retire."
)
FRASE_POR_COMPRAR = "Por comprar: no hay stock suficiente ni compra vigente."
FRASE_RETIRADO = "Retirado: pendiente de confirmación de entrega."
FRASE_ENTREGADO = "Entregado: confirmado por el solicitante."
FRASE_RECHAZADO = "Rechazado: el pedido no se retirará."

#: Instantes fijos para que el desempate por fecha sea observable y estable.
FECHA_CONFIRMACION = datetime(2026, 5, 4, 12, 30, 0)
FECHA_ANTIGUA = datetime(2026, 5, 1, 9, 0, 0)
FECHA_RECIENTE = datetime(2026, 5, 2, 9, 0, 0)


@pytest.fixture
def mundo(motor, dos_instituciones):
    """Estados de la 013, sede de la institucion y stock base de 50 unidades."""
    return sembrar_mundo_014(motor, dos_instituciones)


# ---------------------------------------------------------------------------
# Helpers de escenario
# ---------------------------------------------------------------------------


def _detalle(cliente, ticket_id: int) -> dict:
    """`GET /api/v1/tickets/{id}` como lo consume la vista de detalle."""
    respuesta = cliente.get(f"/api/v1/tickets/{ticket_id}")
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


def _insertar_historial(
    motor,
    ticket_id: int,
    *,
    usuario_id: int,
    estado_origen_id: int | None,
    estado_destino_id: int,
    fecha: datetime = FECHA_ANTIGUA,
    motivo: str | None = None,
) -> int:
    """Inserta una fila de historial (preparacion del escenario, no la API)."""
    with sesion(motor) as db:
        fila = HistorialTransicionTicket(
            ticket_id=ticket_id,
            estado_origen_id=estado_origen_id,
            estado_destino_id=estado_destino_id,
            usuario_id=usuario_id,
            fecha_transicion=fecha,
            motivo=motivo,
        )
        db.add(fila)
        db.commit()
        db.refresh(fila)
        return fila.historial_transicion_id


def _confirmar_entrega(
    motor,
    mundo,
    ticket_id: int,
    *,
    fecha: datetime = FECHA_CONFIRMACION,
    usuario_id: int | None = None,
) -> int:
    """Fila `Cerrado -> Cerrado` con el motivo canonico (D-25)."""
    cerrado = mundo["estados"]["Cerrado"]
    return _insertar_historial(
        motor,
        ticket_id,
        usuario_id=usuario_id or mundo["usuarios_inst01"]["Solicitante"],
        estado_origen_id=cerrado,
        estado_destino_id=cerrado,
        fecha=fecha,
        motivo=MOTIVO_CONFIRMACION_ENTREGA,
    )


_SECUENCIA_PROVEEDOR = itertools.count(1)


def _crear_proveedor(motor, *, rut: str | None = None) -> int:
    numero = next(_SECUENCIA_PROVEEDOR)
    with sesion(motor) as db:
        fila = ProveedorControl(
            rut=rut or f"96.013.{numero:03d}-5",
            razon_social="Proveedor proceso 013",
            activo=True,
        )
        db.add(fila)
        db.commit()
        db.refresh(fila)
        return fila.proveedor_id


def _crear_oc(
    motor,
    mundo,
    *,
    estado: str,
    producto_id: int | None = None,
    cantidad: int = 3,
) -> int:
    """OC con una linea del producto base, sin pasar por el servicio de compras."""
    producto = producto_id or mundo["producto_id"]
    proveedor_id = _crear_proveedor(motor)
    with sesion(motor) as db:
        orden = OrdenCompra(
            institucion_id=mundo["institucion_id"],
            sede_id=mundo["sede_id"],
            proveedor_id=proveedor_id,
            estado=estado,
            total=Decimal("0.00"),
        )
        db.add(orden)
        db.flush()
        if estado != "Borrador":
            orden.numero_oc = f"OC-2026-{orden.orden_compra_id:06d}"
        db.add(
            DetalleOrdenCompra(
                orden_compra_id=orden.orden_compra_id,
                institucion_id=mundo["institucion_id"],
                producto_id=producto,
                cantidad_solicitada=cantidad,
                precio_unitario=Decimal("1.00"),
            )
        )
        db.commit()
        db.refresh(orden)
        return orden.orden_compra_id


def _asignar_oc(
    motor,
    mundo,
    orden_id: int,
    ticket_id: int,
    *,
    producto_id: int | None = None,
    cantidad_asignada: int = 2,
    cantidad_faltante: int = 1,
) -> None:
    """Fila de plan que hace que la OC «cubra» el pedido (AC-38)."""
    with sesion(motor) as db:
        db.add(
            OrdenCompraTicket(
                institucion_id=mundo["institucion_id"],
                orden_compra_id=orden_id,
                ticket_id=ticket_id,
                producto_id=producto_id or mundo["producto_id"],
                cantidad_asignada=cantidad_asignada,
                cantidad_faltante=cantidad_faltante,
            )
        )
        db.commit()


def _crear_usuario(
    motor,
    mundo,
    *,
    nombre: str,
    apellido: str,
    correo: str,
    rol_id: int,
) -> int:
    """Usuario adicional con un rol vigente concreto (actores del historial)."""
    with sesion(motor) as db:
        fila = Usuario(
            nombre=nombre,
            apellido=apellido,
            correo=correo,
            departamento_id=mundo["departamento_id"],
            rol_id=rol_id,
        )
        db.add(fila)
        db.commit()
        db.refresh(fila)
        return fila.usuario_id


def _sembrar_ticket_sin_sede(motor, mundo, estado_id: int) -> int:
    """Ticket legado sin instantanea de sede (no participa de la simulacion)."""
    with sesion(motor) as db:
        ticket = Ticket(
            usuario_id=mundo["usuarios_inst01"]["Solicitante"],
            prioridad_id=mundo["prioridad_id"],
            estado_id=estado_id,
            asunto="Ticket legado sin sede para el proceso",
            descripcion="Sembrado sin `sede_id`.",
            institucion_id=mundo["institucion_id"],
            sede_id=None,
        )
        db.add(ticket)
        db.flush()
        db.add(
            DetalleTicket(
                ticket_id=ticket.ticket_id,
                producto_id=mundo["producto_id"],
                cantidad_solicitada=3,
                cantidad_entregada=0,
                institucion_id=mundo["institucion_id"],
            )
        )
        db.commit()
        db.refresh(ticket)
        return ticket.ticket_id


# ---------------------------------------------------------------------------
# AC-37 — etiqueta y frase por estado canonico en listado y detalle
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("estado", "etiqueta", "frase"),
    [
        ("EnRevision", "En revisión", FRASE_EN_REVISION),
        ("Anulado", "Rechazado", FRASE_RECHAZADO),
        ("Cerrado", "Retirado", FRASE_RETIRADO),
    ],
)
def test_ac_37_listado_y_detalle_exponen_etiqueta_y_frase(
    motor, cliente, mundo, estado, etiqueta, frase
):
    """AC-37: cada estado canonico no `EnCurso` tiene etiqueta y frase propias."""
    ticket_id = sembrar_ticket(
        motor, mundo, estado_id=mundo["estados"][estado]
    )

    en_listado = abrir_ticket(cliente, ticket_id)
    assert en_listado is not None
    assert (en_listado["etiqueta_proceso"], en_listado["explicacion_proceso"]) == (
        etiqueta,
        frase,
    )

    en_detalle = _detalle(cliente, ticket_id)
    assert (en_detalle["etiqueta_proceso"], en_detalle["explicacion_proceso"]) == (
        etiqueta,
        frase,
    )


def test_ac_37_alta_en_enrevision_por_http_expone_en_revision(
    cliente_solicitante, motor, mundo
):
    """AC-37/AC-51: el alta nace en `EnRevision` y su etiqueta es «En revisión»."""
    respuesta = cliente_solicitante.post(
        "/api/v1/tickets/",
        json=payload_alta(mundo, mundo["estados"]["EnRevision"]),
    )
    assert respuesta.status_code == 201, respuesta.text
    ticket_id = respuesta.json()["ticket_id"]

    assert abrir_ticket(cliente_solicitante, ticket_id)["etiqueta_proceso"] == "En revisión"
    assert _detalle(cliente_solicitante, ticket_id)["etiqueta_proceso"] == "En revisión"


def test_ac_37_cerrado_con_confirmacion_es_entregado_y_expone_la_linea(
    motor, cliente, mundo
):
    """AC-37/AC-39: `Cerrado` + fila canonica => «Entregado» con fecha y actor."""
    ticket_id = sembrar_ticket(
        motor, mundo, estado_id=mundo["estados"]["Cerrado"]
    )
    _confirmar_entrega(motor, mundo, ticket_id)

    en_listado = abrir_ticket(cliente, ticket_id)
    assert en_listado["entrega_confirmada"] is True
    assert (en_listado["etiqueta_proceso"], en_listado["explicacion_proceso"]) == (
        "Entregado",
        FRASE_ENTREGADO,
    )

    en_detalle = _detalle(cliente, ticket_id)
    assert en_detalle["entrega_confirmada"] is True
    assert en_detalle["etiqueta_proceso"] == "Entregado"
    assert datetime.fromisoformat(en_detalle["entrega_confirmada_en"]) == (
        FECHA_CONFIRMACION
    )
    assert en_detalle["entrega_confirmada_por_nombre"] == "Solicitante"
    assert en_detalle["entrega_confirmada_por_apellido"] == "Inst01"


def test_ac_37_cerrado_con_otro_motivo_no_esta_confirmado(
    motor, cliente, mundo
):
    """AC-37/D-25: solo la fila con el motivo canonico confirma la entrega."""
    ticket_id = sembrar_ticket(
        motor, mundo, estado_id=mundo["estados"]["Cerrado"]
    )
    cerrado = mundo["estados"]["Cerrado"]
    _insertar_historial(
        motor,
        ticket_id,
        usuario_id=mundo["usuarios_inst01"]["Solicitante"],
        estado_origen_id=cerrado,
        estado_destino_id=cerrado,
        fecha=FECHA_CONFIRMACION,
        motivo="Otro motivo que no confirma la entrega",
    )

    en_detalle = _detalle(cliente, ticket_id)
    assert en_detalle["entrega_confirmada"] is False
    assert en_detalle["etiqueta_proceso"] == "Retirado"
    assert en_detalle["entrega_confirmada_en"] is None


# ---------------------------------------------------------------------------
# AC-38 — precedencia de la OC activa sobre el stock en EnCurso
# ---------------------------------------------------------------------------


def _ticket_en_curso(motor, mundo, *, cantidad: int = 3) -> int:
    return sembrar_ticket(
        motor,
        mundo,
        estado_id=mundo["estados"]["EnCurso"],
        cantidad=cantidad,
    )


def test_ac_38_encurso_con_stock_local_espera_confirmacion(motor, cliente, mundo):
    """AC-38: sin OC activa, `stock_disponible` decide la etiqueta."""
    ticket_id = _ticket_en_curso(motor, mundo)

    en_detalle = _detalle(cliente, ticket_id)
    assert en_detalle["stock_disponible"] is True
    assert en_detalle["estado_orden_cobertura"] is None
    assert (
        en_detalle["etiqueta_proceso"],
        en_detalle["explicacion_proceso"],
    ) == ("En confirmación de stock local", FRASE_EN_CONFIRMACION_STOCK)


def test_ac_38_encurso_sin_stock_ni_oc_queda_por_comprar(motor, cliente, mundo):
    """AC-38: sin cobertura activa ni saldo, el pedido esta «Por comprar»."""
    fijar_stock_sede(motor, mundo, mundo["producto_id"], 0)
    ticket_id = _ticket_en_curso(motor, mundo)

    en_detalle = _detalle(cliente, ticket_id)
    assert en_detalle["stock_disponible"] is False
    assert en_detalle["estado_orden_cobertura"] is None
    assert (
        en_detalle["etiqueta_proceso"],
        en_detalle["explicacion_proceso"],
    ) == ("Por comprar", FRASE_POR_COMPRAR)


@pytest.mark.parametrize(
    ("estado_orden", "etiqueta", "frase"),
    [
        ("Emitida", "En compra", FRASE_EN_COMPRA),
        ("Facturada", "Facturado", FRASE_FACTURADO),
        (
            "Recibida",
            "En confirmación de stock local",
            FRASE_EN_CONFIRMACION_STOCK,
        ),
    ],
)
def test_ac_38_la_oc_activa_decide_la_etiqueta(
    motor, cliente, mundo, estado_orden, etiqueta, frase
):
    """AC-38: la OC activa prevalece sobre el stock local."""
    fijar_stock_sede(motor, mundo, mundo["producto_id"], 0)
    ticket_id = _ticket_en_curso(motor, mundo)
    orden_id = _crear_oc(motor, mundo, estado=estado_orden)
    _asignar_oc(motor, mundo, orden_id, ticket_id)

    en_listado = abrir_ticket(cliente, ticket_id)
    assert en_listado["estado_orden_cobertura"] == estado_orden
    assert en_listado["stock_disponible"] is False
    assert (en_listado["etiqueta_proceso"], en_listado["explicacion_proceso"]) == (
        etiqueta,
        frase,
    )

    en_detalle = _detalle(cliente, ticket_id)
    assert en_detalle["estado_orden_cobertura"] == estado_orden
    assert en_detalle["etiqueta_proceso"] == etiqueta


def test_ac_38_precedencia_recibida_sobre_facturada_y_emitida(
    motor, cliente, mundo
):
    """AC-38: con varias OC activas gana la mas avanzada, no la ultima creada."""
    ticket_id = _ticket_en_curso(motor, mundo)
    emitida = _crear_oc(motor, mundo, estado="Emitida")
    facturada = _crear_oc(motor, mundo, estado="Facturada")
    recibida = _crear_oc(motor, mundo, estado="Recibida")
    _asignar_oc(motor, mundo, emitida, ticket_id)
    _asignar_oc(motor, mundo, facturada, ticket_id)
    _asignar_oc(motor, mundo, recibida, ticket_id)

    en_detalle = _detalle(cliente, ticket_id)
    assert en_detalle["estado_orden_cobertura"] == "Recibida"
    assert en_detalle["etiqueta_proceso"] == "En confirmación de stock local"


def test_ac_38_precedencia_facturada_sobre_emitida_no_depende_del_orden(
    motor, cliente, mundo
):
    """AC-38: Facturada > Emitida aunque la Emitida se cree despues."""
    ticket_id = _ticket_en_curso(motor, mundo)
    facturada = _crear_oc(motor, mundo, estado="Facturada")
    emitida = _crear_oc(motor, mundo, estado="Emitida")
    _asignar_oc(motor, mundo, emitida, ticket_id)
    _asignar_oc(motor, mundo, facturada, ticket_id)

    en_detalle = _detalle(cliente, ticket_id)
    assert en_detalle["estado_orden_cobertura"] == "Facturada"
    assert en_detalle["etiqueta_proceso"] == "Facturado"


def test_ac_38_oc_cancelada_no_cuenta_y_decide_el_stock(motor, cliente, mundo):
    """AC-38: una `Cancelada` no es cobertura activa; el saldo decide."""
    ticket_id = _ticket_en_curso(motor, mundo)
    cancelada = _crear_oc(motor, mundo, estado="Cancelada")
    _asignar_oc(motor, mundo, cancelada, ticket_id)

    en_detalle = _detalle(cliente, ticket_id)
    assert en_detalle["estado_orden_cobertura"] is None
    assert en_detalle["stock_disponible"] is True
    assert en_detalle["etiqueta_proceso"] == "En confirmación de stock local"


def test_ac_38_plan_sin_asignacion_no_cubre_el_pedido(motor, cliente, mundo):
    """AC-38: «cubre» exige al menos una fila de plan con asignacion > 0.

    El CHECK de la tabla impide persistir `cantidad_asignada = 0`, de modo que
    la ausencia de cobertura se representa con una OC sin fila de plan para el
    pedido; el saldo sigue decidiendo.
    """
    fijar_stock_sede(motor, mundo, mundo["producto_id"], 0)
    ticket_id = _ticket_en_curso(motor, mundo)
    _crear_oc(motor, mundo, estado="Recibida")  # sin fila de plan para el ticket

    en_detalle = _detalle(cliente, ticket_id)
    assert en_detalle["estado_orden_cobertura"] is None
    assert en_detalle["etiqueta_proceso"] == "Por comprar"


# ---------------------------------------------------------------------------
# AC-39 — stock por sede, coherencia y detalle intacto
# ---------------------------------------------------------------------------


def test_ac_39_stock_disponible_se_simula_por_sede_no_por_institucion(
    motor, cliente, mundo
):
    """AC-39: el saldo de otra sede no cubre el pedido de esta sede."""
    en_sede_base = _ticket_en_curso(motor, mundo)
    sede_sin_stock = crear_sede(
        motor,
        institucion_id=mundo["institucion_id"],
        nombre="Sede sin stock del proceso",
    )
    crear_stock_sede(
        motor,
        sede_id=sede_sin_stock,
        producto_id=mundo["producto_id"],
        stock_actual=0,
        institucion_id=mundo["institucion_id"],
    )
    en_sede_sin_stock = sembrar_ticket(
        motor,
        mundo,
        estado_id=mundo["estados"]["EnCurso"],
        sede_id=sede_sin_stock,
    )

    con_stock = abrir_ticket(cliente, en_sede_base)
    sin_stock = abrir_ticket(cliente, en_sede_sin_stock)

    assert con_stock["stock_disponible"] is True
    assert con_stock["etiqueta_proceso"] == "En confirmación de stock local"
    assert sin_stock["stock_disponible"] is False
    assert sin_stock["etiqueta_proceso"] == "Por comprar"
    assert _detalle(cliente, en_sede_sin_stock)["stock_disponible"] is False


def test_ac_39_ticket_sin_sede_no_participa_de_la_simulacion(
    motor, cliente, mundo
):
    """AC-39: un ticket sin instantanea de sede queda en `stock_disponible=False`."""
    ticket_id = _sembrar_ticket_sin_sede(
        motor, mundo, mundo["estados"]["EnCurso"]
    )

    en_detalle = _detalle(cliente, ticket_id)
    assert en_detalle["stock_disponible"] is False
    assert en_detalle["etiqueta_proceso"] == "Por comprar"


def test_ac_39_listado_y_detalle_coinciden_y_el_detalle_conserva_las_listas(
    motor, cliente, mundo
):
    """AC-39: misma etiqueta en listado y detalle; `asignaciones`/`cadena` intactas."""
    ticket_id = sembrar_ticket(
        motor, mundo, estado_id=mundo["estados"]["Cerrado"], cantidad=3
    )
    orden_id = _crear_oc(motor, mundo, estado="Recibida", cantidad=3)
    _asignar_oc(
        motor,
        mundo,
        orden_id,
        ticket_id,
        cantidad_asignada=3,
        cantidad_faltante=0,
    )
    _confirmar_entrega(motor, mundo, ticket_id)

    en_listado = abrir_ticket(cliente, ticket_id)
    en_detalle = _detalle(cliente, ticket_id)

    for campo in (
        "etiqueta_proceso",
        "explicacion_proceso",
        "estado_orden_cobertura",
        "stock_disponible",
        "entrega_confirmada",
        "gestionado_por_bodeguero",
        "gestionado_por_administrador",
    ):
        assert en_listado[campo] == en_detalle[campo], (
            f"listado y detalle no pueden divergir en `{campo}`"
        )

    assert (en_listado["etiqueta_proceso"], en_listado["entrega_confirmada"]) == (
        "Entregado",
        True,
    )
    assert en_listado["estado_orden_cobertura"] == "Recibida"
    assert en_listado["stock_disponible"] is False, (
        "un pedido terminal no participa de la simulacion de stock"
    )

    assert len(en_detalle["asignaciones"]) == 1
    asignacion = en_detalle["asignaciones"][0]
    assert asignacion["orden_compra_id"] == orden_id
    assert asignacion["estado_orden"] == "Recibida"
    assert asignacion["cantidad_asignada"] == 3

    assert len(en_detalle["cadena_productos"]) == 1
    cadena = en_detalle["cadena_productos"][0]
    assert cadena["producto_id"] == mundo["producto_id"]
    assert (cadena["solicitado"], cadena["recibido"], cadena["entregado"]) == (
        3,
        3,
        0,
    )
    assert cadena["faltante"] == 0, "un pedido terminal deja la cadena sin faltante"


# ---------------------------------------------------------------------------
# AC-40 — ultimo Bodeguero y ultimo Administrador del historial
# ---------------------------------------------------------------------------


def test_ac_39_el_201_del_alta_publica_el_read_model(
    motor, cliente, actuar_como, mundo
):
    """AC-39 (corrección T31): el `201` del alta trae el read model completo.

    El tablero inserta la respuesta del `POST /tickets/` sin reconsultar
    (AC-41), así que el alta debe devolver la misma etiqueta que el listado y
    no un `TicketRespuesta` derivado de un ORM desnudo (etiqueta vacía).

    Enmienda 26/Nov/2026 (E26N-5): el alta la ejerce el Solicitante; la etiqueta
    y el listado se leen con Administrador. La creación por Administrador que
    contaba como gestor (AC-40) se recupera en
    `test_ac_40_tickets_historicos_conservan_su_gestor_y_siguen_operativos`
    (E26N-6), sembrada por ORM y sin reasignar autores.
    """
    actuar_como("Solicitante")
    respuesta = cliente.post(
        "/api/v1/tickets/",
        json=payload_alta(mundo, mundo["estados"]["EnRevision"]),
    )
    assert respuesta.status_code == 201, respuesta.text
    cuerpo = respuesta.json()

    assert cuerpo["estado_id"] == mundo["estados"]["EnRevision"]
    assert (cuerpo["etiqueta_proceso"], cuerpo["explicacion_proceso"]) == (
        "En revisión",
        FRASE_EN_REVISION,
    )
    assert cuerpo["stock_disponible"] is False, (
        "un pedido en `EnRevision` no participa de la simulación de la 020"
    )
    assert cuerpo["entrega_confirmada"] is False
    assert cuerpo["estado_orden_cobertura"] is None

    # Lectura con Administrador: el listado y el detalle siguen siendo suyos.
    actuar_como("Administrador")
    historial = leer_historial(cliente, cuerpo["ticket_id"])
    assert len(historial) == 1, historial
    creacion = historial[0]
    assert creacion["estado_origen_id"] is None
    assert creacion["estado_destino_id"] == mundo["estados"]["EnRevision"]

    with sesion(motor) as db:
        estado_persistido = db.execute(
            select(Ticket.estado_id).where(Ticket.ticket_id == cuerpo["ticket_id"])
        ).scalar_one()
        rol_actor = db.execute(
            select(Rol.nombre_rol)
            .join(Usuario, Rol.rol_id == Usuario.rol_id)
            .where(Usuario.usuario_id == creacion["usuario_id"])
        ).scalar_one()

    assert estado_persistido == mundo["estados"]["EnRevision"], (
        "el alta nace en `EnRevision` (D-27/AC-51)"
    )

    # El actor de creación es el Solicitante (rol vigente): no es gestor.
    assert rol_actor == "Solicitante"
    assert cuerpo["gestionado_por_administrador"] is None
    assert cuerpo["gestionado_por_bodeguero"] is None

    # Y coincide con lo que publica el listado que consume el tablero.
    en_listado = abrir_ticket(cliente, cuerpo["ticket_id"])
    for campo in (
        "etiqueta_proceso",
        "explicacion_proceso",
        "estado_orden_cobertura",
        "stock_disponible",
        "entrega_confirmada",
        "gestionado_por_bodeguero",
        "gestionado_por_administrador",
    ):
        assert cuerpo[campo] == en_listado[campo], (
            f"el `201` del alta no puede divergir del listado en `{campo}`"
        )


def test_ac_39_el_201_del_alta_de_un_solicitante_no_registra_gestores(motor, mundo):
    """AC-39/AC-40: si el creador es Solicitante, los dos gestores quedan en `None`.

    La fila de creación existe, pero su actor no tiene rol gestor: el read model
    del `201` debe decirlo igual que el listado, sin inventar responsables.
    """
    with cliente_con_rol(
        motor,
        "Solicitante",
        departamento_id=mundo["departamento_id"],
        usuario_id=mundo["usuarios_inst01"]["Solicitante"],
    ) as solicitante:
        respuesta = solicitante.post(
            "/api/v1/tickets/",
            json=payload_alta(mundo, mundo["estados"]["EnRevision"]),
        )
        assert respuesta.status_code == 201, respuesta.text
        cuerpo = respuesta.json()

        assert cuerpo["etiqueta_proceso"] == "En revisión"
        assert cuerpo["gestionado_por_bodeguero"] is None
        assert cuerpo["gestionado_por_administrador"] is None

        historial = leer_historial(solicitante, cuerpo["ticket_id"])
        assert len(historial) == 1, historial
        assert historial[0]["estado_origen_id"] is None
        assert (
            historial[0]["usuario_id"] == mundo["usuarios_inst01"]["Solicitante"]
        )


def test_ac_40_ultimo_gestor_por_fecha_y_desempate_por_id(motor, cliente, mundo):
    """AC-40: `fecha_transicion DESC` y, en empate, `historial_transicion_id DESC`."""
    ticket_id = _ticket_en_curso(motor, mundo)
    bodeguero_viejo = _crear_usuario(
        motor,
        mundo,
        nombre="Bodeguero",
        apellido="Antiguo",
        correo="bodeguero.antiguo.013@compustock.cl",
        rol_id=mundo["rol_bodeguero_id"],
    )
    bodeguero_nuevo = _crear_usuario(
        motor,
        mundo,
        nombre="Bodeguero",
        apellido="Reciente",
        correo="bodeguero.reciente.013@compustock.cl",
        rol_id=mundo["rol_bodeguero_id"],
    )
    administrador_primero = _crear_usuario(
        motor,
        mundo,
        nombre="Administrador",
        apellido="Primero",
        correo="administrador.primero.013@compustock.cl",
        rol_id=mundo["rol_id"],
    )
    administrador_segundo = _crear_usuario(
        motor,
        mundo,
        nombre="Administrador",
        apellido="Segundo",
        correo="administrador.segundo.013@compustock.cl",
        rol_id=mundo["rol_id"],
    )
    solicitante = mundo["usuarios_inst01"]["Solicitante"]
    encurso = mundo["estados"]["EnCurso"]

    # Bodeguero: gana la fila con la fecha mas reciente (el usuario nuevo),
    # aunque sea la ultima creada o no. El Solicitante escribe despues y no
    # cuenta como gestor.
    _insertar_historial(
        motor,
        ticket_id,
        usuario_id=bodeguero_viejo,
        estado_origen_id=encurso,
        estado_destino_id=encurso,
        fecha=FECHA_ANTIGUA,
    )
    _insertar_historial(
        motor,
        ticket_id,
        usuario_id=bodeguero_nuevo,
        estado_origen_id=encurso,
        estado_destino_id=encurso,
        fecha=FECHA_RECIENTE,
    )
    _insertar_historial(
        motor,
        ticket_id,
        usuario_id=solicitante,
        estado_origen_id=encurso,
        estado_destino_id=encurso,
        fecha=datetime(2026, 5, 3, 9, 0, 0),
    )

    # Administrador: dos filas en el mismo instante; el desempate es el id.
    primera_admin = _insertar_historial(
        motor,
        ticket_id,
        usuario_id=administrador_primero,
        estado_origen_id=encurso,
        estado_destino_id=encurso,
        fecha=FECHA_ANTIGUA,
    )
    segunda_admin = _insertar_historial(
        motor,
        ticket_id,
        usuario_id=administrador_segundo,
        estado_origen_id=encurso,
        estado_destino_id=encurso,
        fecha=FECHA_ANTIGUA,
    )
    assert segunda_admin > primera_admin

    en_listado = abrir_ticket(cliente, ticket_id)
    en_detalle = _detalle(cliente, ticket_id)
    for respuesta in (en_listado, en_detalle):
        assert respuesta["gestionado_por_bodeguero"] == {
            "usuario_id": bodeguero_nuevo,
            "nombre": "Bodeguero",
            "apellido": "Reciente",
        }
        assert respuesta["gestionado_por_administrador"] == {
            "usuario_id": administrador_segundo,
            "nombre": "Administrador",
            "apellido": "Segundo",
        }


def test_ac_40_sin_historial_o_sin_rol_gestor_queda_en_none(motor, cliente, mundo):
    """AC-40: sin filas del rol, el campo es `None`; la creacion si cuenta."""
    sin_historial = _ticket_en_curso(motor, mundo)
    solo_solicitante = _ticket_en_curso(motor, mundo)
    con_creacion = _ticket_en_curso(motor, mundo)
    _insertar_historial(
        motor,
        solo_solicitante,
        usuario_id=mundo["usuarios_inst01"]["Solicitante"],
        estado_origen_id=mundo["estados"]["EnRevision"],
        estado_destino_id=mundo["estados"]["EnCurso"],
        fecha=FECHA_RECIENTE,
    )
    # Fila de creacion: origen nulo, actor con rol Bodeguero (AC-40/D-23).
    _insertar_historial(
        motor,
        con_creacion,
        usuario_id=mundo["usuarios_inst01"]["Bodeguero"],
        estado_origen_id=None,
        estado_destino_id=mundo["estados"]["EnCurso"],
        fecha=FECHA_ANTIGUA,
    )

    assert abrir_ticket(cliente, sin_historial)["gestionado_por_bodeguero"] is None
    assert (
        abrir_ticket(cliente, sin_historial)["gestionado_por_administrador"] is None
    )
    solo = abrir_ticket(cliente, solo_solicitante)
    assert solo["gestionado_por_bodeguero"] is None
    assert solo["gestionado_por_administrador"] is None

    creacion = abrir_ticket(cliente, con_creacion)
    assert creacion["gestionado_por_bodeguero"] == {
        "usuario_id": mundo["usuarios_inst01"]["Bodeguero"],
        "nombre": "Bodeguero",
        "apellido": "Inst01",
    }


def test_ac_40_tickets_historicos_conservan_su_gestor_y_siguen_operativos(
    motor, mundo
):
    """AC-31 (007 D-16)/AC-40: un ticket historico con autoria Administrador o
    Bodeguero conserva su autor y su gestor de creacion, y se opera con las
    reglas vigentes.

    Enmienda 007 del 26/Nov/2026 (E26N-6): el alta solo la ejerce el Solicitante;
    la cobertura del antiguo `201` administrativo se recupera sembrando el
    ticket por ORM, sin reasignar su autoria.
    """
    datos = mundo
    administrador_id = datos["usuario_id"]
    bodeguero_id = datos["usuarios_inst01"]["Bodeguero"]
    en_revision = datos["estados"]["EnRevision"]

    del_administrador = sembrar_ticket(
        motor,
        datos,
        usuario_id=administrador_id,
        estado_id=en_revision,
        asunto="Ticket historico del Administrador",
    )
    _insertar_historial(
        motor,
        del_administrador,
        usuario_id=administrador_id,
        estado_origen_id=None,
        estado_destino_id=en_revision,
    )
    del_bodeguero = sembrar_ticket(
        motor,
        datos,
        usuario_id=bodeguero_id,
        estado_id=en_revision,
        asunto="Ticket historico del Bodeguero",
    )
    _insertar_historial(
        motor,
        del_bodeguero,
        usuario_id=bodeguero_id,
        estado_origen_id=None,
        estado_destino_id=en_revision,
    )

    with cliente_de_rol(motor, datos, "Administrador") as admin:
        en_listado = abrir_ticket(admin, del_administrador)
        en_detalle = _detalle(admin, del_administrador)
        detalle_bodeguero = _detalle(admin, del_bodeguero)

        # El autor historico se conserva y el read model lo publica.
        assert en_listado["usuario_id"] == administrador_id
        assert en_detalle["usuario_id"] == administrador_id
        assert detalle_bodeguero["usuario_id"] == bodeguero_id
        assert en_detalle["etiqueta_proceso"] == "En revisión"
        assert [fila["producto_id"] for fila in en_detalle["detalles"]] == [
            datos["producto_id"]
        ], "los detalles del ticket historico se conservan"

        # La fila de creacion cuenta como gestion del rol vigente del autor.
        assert en_listado["gestionado_por_administrador"] == {
            "usuario_id": administrador_id,
            "nombre": "Ana",
            "apellido": "Perez",
        }
        assert en_listado["gestionado_por_bodeguero"] is None
        assert detalle_bodeguero["gestionado_por_bodeguero"] == {
            "usuario_id": bodeguero_id,
            "nombre": "Bodeguero",
            "apellido": "Inst01",
        }
        assert detalle_bodeguero["gestionado_por_administrador"] is None

        # Sigue operativo: el Administrador lo aprueba segun su estado.
        aprobacion = admin.post(
            f"/api/v1/tickets/{del_administrador}/aprobacion"
        )
        assert aprobacion.status_code == 200, aprobacion.text
        assert aprobacion.json()["estado_id"] == datos["estados"]["EnCurso"]
        assert aprobacion.json()["usuario_id"] == administrador_id, (
            "aprobar no reasigna el autor historico"
        )

    with cliente_de_rol(motor, datos, "Bodeguero") as bodeguero:
        retiro = bodeguero.post(
            f"/api/v1/tickets/{del_administrador}/retiro",
            json={"usuario_id": bodeguero_id},
        )
        assert retiro.status_code == 200, retiro.text
        assert retiro.json()["estado_id"] == datos["estados"]["Cerrado"]
        assert retiro.json()["usuario_id"] == administrador_id, (
            "despachar no reasigna el autor historico"
        )

    with cliente_de_rol(motor, datos, "Administrador") as admin:
        final = _detalle(admin, del_administrador)
        assert final["usuario_id"] == administrador_id
        assert final["etiqueta_proceso"] == "Retirado"
        assert final["entrega_confirmada"] is False
        assert final["gestionado_por_administrador"]["usuario_id"] == administrador_id
        assert final["gestionado_por_bodeguero"]["usuario_id"] == bodeguero_id

        historial = leer_historial(admin, del_administrador)
        creacion = next(
            fila for fila in historial if fila["estado_origen_id"] is None
        )
        assert creacion["usuario_id"] == administrador_id, (
            "la creacion del ticket historico conserva a su autor"
        )
        assert creacion["estado_destino_id"] == en_revision


# ---------------------------------------------------------------------------
# No-N+1: el read model se calcula por lote
# ---------------------------------------------------------------------------


def test_listado_no_hace_consultas_por_ticket(motor, cliente, mundo):
    """El numero de SELECT del listado no crece con los pedidos (AC-39).

    Se cuentan las ejecuciones con `before_cursor_execute` y se compara 1
    pedido contra 3, todos `EnCurso` de la misma sede para ejercitar tambien la
    simulacion de la 020, la cobertura de OC, las confirmaciones y los gestores.
    """
    contador = {"n": 0}

    def contar(*_args, **_kwargs):
        contador["n"] += 1

    _ticket_en_curso(motor, mundo)
    event.listen(motor, "before_cursor_execute", contar)
    try:
        contador["n"] = 0
        assert cliente.get("/api/v1/tickets/").status_code == 200
        with_uno = contador["n"]

        _ticket_en_curso(motor, mundo)
        _ticket_en_curso(motor, mundo)
        contador["n"] = 0
        assert cliente.get("/api/v1/tickets/").status_code == 200
        with_tres = contador["n"]
    finally:
        event.remove(motor, "before_cursor_execute", contar)

    assert with_tres == with_uno, (
        "el read model de proceso no puede emitir una consulta por ticket "
        f"(N+1): {with_uno} queries con 1 ticket y {with_tres} con 3"
    )
    # El numero es fijo, pero acotado: carga eager en cadena, una simulacion por
    # sede, una consulta de OC, una de confirmaciones (mas la resolucion del
    # `Cerrado` canonico) y una de gestores. Con estos tres pedidos `EnCurso` son
    # 15 ejecuciones tanto con 1 como con 3; lo que protege la prueba es que no
    # crezca con los pedidos y el tope detecta un bucle disfrazado.
    assert with_tres <= 15, (
        "el listado debe resolverse en un numero acotado de consultas fijas: "
        f"{with_tres} consultas con 3 tickets"
    )
