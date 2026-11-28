"""Publicacion del movimiento manual de stock (Feature 028, T10).

Seam bajo prueba: la **interfaz HTTP** del `app` real (`TestClient`) con el
`BusFalso` de T4 instalado por `instalar_bus`, que enciende
`TIEMPO_REAL_HABILITADO` y guarda cada sobre publicado. Asi se comprueba el
efecto observable de la mutacion (status, cuerpo y sobre) sin tocar la capa de
servicios mas alla de la observacion del orden commit -> publicacion.

Tabla cubierta (spec §5.2 y Anexo A, fila 10):

| Mutacion | Motivo | Dominios | Dueno |
|---|---|---|---|
| `POST /inventario/movimientos` | `movimiento` | `inventario` | — |

Reglas verificadas ademas de la tabla: publicacion **posterior al commit**,
`usuario_ids` vacio (el stock no se enruta por dueno), silencio en los 404
(stock por sede inexistente o ajeno) y en los 409 (salida sin stock suficiente
o movimiento sobre un producto inactivo), y entrega del dominio al tablero y a
la marca sintetica del dashboard por el filtro de T6.

El movimiento manual lo escribe solo el Bodeguero (enmienda 26/Nov/2026 de la
013, D-31/AC-64); el resto de roles recibe 403 antes del servicio y no se
repite aqui. La recepcion de compras es de T12.
"""

from __future__ import annotations

import pytest
from sqlalchemy import event, select
from sqlalchemy.orm import Session, sessionmaker

from app.api.dependencies import ContextoTiempoReal
from app.api.v1.endpoints.eventos import _dominios_visibles_del_sobre
from app.models import Producto, StockSede

from tests.funcional.integracion._soporte_eventos_028 import instalar_bus
from tests.funcional.integracion._soporte_retiro_013 import (
    cliente_rol,
    sembrar_mundo_retiro,
)

RUTA_MOVIMIENTOS = "/api/v1/inventario/movimientos"

#: Institucion de la semilla (`datos_base`/`dos_instituciones`).
INSTITUCION = "INST01"

#: Motivo literal del movimiento manual de stock (spec §5.2).
MOTIVO_MOVIMIENTO = "movimiento"


# ---------------------------------------------------------------------------
# Mundo y peticion
# ---------------------------------------------------------------------------


@pytest.fixture
def mundo(motor, dos_instituciones):
    """Mundo del retiro (013) con la referencia de escritura y un inactivo.

    `sembrar_mundo_retiro` deja al Bodeguero de INST01 con la sede del pedido y
    50 unidades del producto base en esa sede. Se amplia con el `stock_sede_id`
    de esa fila -el destino unico de `MovimientoCrear`- y con un segundo
    producto **retirado** que conserva saldo en la misma sede, para el **409**
    de producto inactivo sin tocar el catalogo base de otras pruebas.
    """
    datos = sembrar_mundo_retiro(motor, dos_instituciones)
    db = sessionmaker(bind=motor)()
    try:
        fila = db.execute(
            select(StockSede).where(
                StockSede.sede_id == datos["sede_id"],
                StockSede.producto_id == datos["producto_id"],
            )
        ).scalar_one()
        stock_sede_id = fila.stock_sede_id

        inactivo = Producto(
            nombre="Cuaderno retirado para la 028",
            descripcion="Producto inactivo con saldo, para el 409 de T10",
            unidad_medida="UNIDAD",
            stock_minimo=0,
            categoria_id=datos["categoria_id"],
            institucion_id=datos["institucion_id"],
        )
        inactivo.activo = False
        db.add(inactivo)
        db.flush()
        stock_inactivo = StockSede(
            sede_id=datos["sede_id"],
            producto_id=inactivo.producto_id,
            stock_actual=10,
            institucion_id=datos["institucion_id"],
        )
        db.add(stock_inactivo)
        db.flush()
        stock_inactivo_id = stock_inactivo.stock_sede_id
        producto_inactivo_id = inactivo.producto_id
        db.commit()

        return {
            **datos,
            "stock_sede_id": stock_sede_id,
            "stock_inactivo_id": stock_inactivo_id,
            "producto_inactivo_id": producto_inactivo_id,
        }
    finally:
        db.close()


def _movimiento(
    cliente,
    *,
    stock_sede_id: int,
    tipo: str = "ENTRADA",
    cantidad: int = 25,
    observacion: str = "Movimiento manual de la prueba 028",
):
    """`POST /inventario/movimientos` con un cuerpo valido de la 027."""
    return cliente.post(
        RUTA_MOVIMIENTOS,
        json={
            "tipo_movimiento": tipo,
            "cantidad": cantidad,
            "observacion": observacion,
            "stock_sede_id": stock_sede_id,
        },
    )


# ---------------------------------------------------------------------------
# Observacion de la publicacion
# ---------------------------------------------------------------------------


def _sobre_unico(bus):
    """Un unico sobre publicado; falla con el conteo real si hubo cero o varios."""
    assert len(bus.publicados) == 1, (
        "se esperaba exactamente un sobre publicado por la mutacion; "
        f"hubo {len(bus.publicados)}: {bus.publicados!r}"
    )
    return bus.publicados[0]


def _afirmar_sobre_de_inventario(sobre) -> None:
    """Contrato del sobre de T10: un dominio, el motivo y sin duenos."""
    assert sobre.dominios == frozenset({"inventario"}), (
        "el movimiento manual solo anuncia `inventario`; "
        f"llego {sorted(sobre.dominios)}"
    )
    assert sobre.motivo == MOTIVO_MOVIMIENTO
    assert sobre.institucion_id == INSTITUCION
    assert sobre.usuario_ids == frozenset(), (
        "`inventario` no se enruta por dueno: la audiencia son los roles con "
        f"la capacidad, no un `usuario_id`; llego {sobre.usuario_ids!r}"
    )


def _contexto(
    *, usuario_id: int, rol: str, dominios_visibles: frozenset[str]
) -> ContextoTiempoReal:
    """Copia de contexto de una conexion SSE (misma forma que T2/T6)."""
    return ContextoTiempoReal(
        usuario_id=usuario_id,
        rol=rol,
        institucion_id=INSTITUCION,
        expira_en=None,
        dominios_visibles=dominios_visibles,
        request_id=None,
    )


# ---------------------------------------------------------------------------
# Tabla de mutaciones: el movimiento confirmado publica
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tipo, cantidad, nuevo_stock",
    [
        ("ENTRADA", 25, 75),
        ("SALIDA", 5, 45),
    ],
)
def test_movimiento_confirmado_publica_inventario_con_motivo_movimiento(
    motor, mundo, tipo, cantidad, nuevo_stock
):
    """Anexo A fila 10 / AC-6: la entrada y la salida confirmadas anuncian stock."""
    with instalar_bus() as bus:
        with cliente_rol(motor, mundo, "Bodeguero") as cliente:
            respuesta = _movimiento(
                cliente,
                stock_sede_id=mundo["stock_sede_id"],
                tipo=tipo,
                cantidad=cantidad,
            )

    assert respuesta.status_code == 201, respuesta.text
    assert respuesta.json()["nuevo_stock"] == nuevo_stock
    _afirmar_sobre_de_inventario(_sobre_unico(bus))


# ---------------------------------------------------------------------------
# Despues del commit, nunca antes (D-8, AC-7)
# ---------------------------------------------------------------------------


def test_la_publicacion_del_movimiento_ocurre_despues_del_commit(motor, mundo):
    """AC-7/D-8: al publicar, el saldo del movimiento ya esta persistido."""
    commits: list[int] = []
    observado: dict[str, int] = {}

    def registrar_commit(_sesion: Session) -> None:
        commits.append(1)

    with instalar_bus() as bus:
        publicar_original = bus.publicar

        def publicar_observando(sobre) -> None:
            observado["commits_previos"] = len(commits)
            publicar_original(sobre)

        bus.publicar = publicar_observando
        event.listen(Session, "after_commit", registrar_commit)
        try:
            with cliente_rol(motor, mundo, "Bodeguero") as cliente:
                respuesta = _movimiento(
                    cliente, stock_sede_id=mundo["stock_sede_id"], cantidad=25
                )
        finally:
            event.remove(Session, "after_commit", registrar_commit)

    assert respuesta.status_code == 201, respuesta.text
    assert len(bus.publicados) == 1
    assert observado["commits_previos"] >= 1, (
        "el sobre se publico antes de que la transaccion del movimiento "
        "confirmara (D-8)"
    )
    with sessionmaker(bind=motor)() as db:
        assert db.get(StockSede, mundo["stock_sede_id"]).stock_actual == 75, (
            "el bus ve el sobre cuando el saldo nuevo ya esta persistido"
        )


# ---------------------------------------------------------------------------
# Rechazos: 404 y 409 no publican (AC-7)
# ---------------------------------------------------------------------------


def test_un_stock_sede_inexistente_responde_404_y_no_publica(motor, mundo):
    """AC-7/AC-3: una sede/producto sin fila de saldo responde 404 y calla."""
    with instalar_bus() as bus:
        with cliente_rol(motor, mundo, "Bodeguero") as cliente:
            respuesta = _movimiento(cliente, stock_sede_id=999_999)

    assert respuesta.status_code == 404, respuesta.text
    assert bus.publicados == []


def test_un_stock_sede_ajeno_responde_404_y_no_publica(motor, mundo):
    """AC-7: el saldo de otra institucion se oculta con 404 y no se anuncia."""
    with instalar_bus() as bus:
        with cliente_rol(motor, mundo, "Bodeguero") as cliente:
            respuesta = _movimiento(
                cliente, stock_sede_id=mundo["stock_homonimo_ajeno_id"]
            )

    assert respuesta.status_code == 404, respuesta.text
    assert bus.publicados == []


def test_una_salida_sin_stock_suficiente_responde_409_y_no_publica(motor, mundo):
    """AC-7: la salida por encima del saldo responde 409 y no anuncia nada."""
    with instalar_bus() as bus:
        with cliente_rol(motor, mundo, "Bodeguero") as cliente:
            respuesta = _movimiento(
                cliente,
                stock_sede_id=mundo["stock_sede_id"],
                tipo="SALIDA",
                cantidad=500,
            )

    assert respuesta.status_code == 409, respuesta.text
    assert bus.publicados == []


def test_un_movimiento_sobre_producto_inactivo_responde_409_y_no_publica(
    motor, mundo
):
    """AC-7/014 AC-9: un producto retirado no admite movimientos ni avisos."""
    with instalar_bus() as bus:
        with cliente_rol(motor, mundo, "Bodeguero") as cliente:
            respuesta = _movimiento(
                cliente,
                stock_sede_id=mundo["stock_inactivo_id"],
                tipo="ENTRADA",
                cantidad=5,
            )

    assert respuesta.status_code == 409, respuesta.text
    assert bus.publicados == []


# ---------------------------------------------------------------------------
# Tablero y dashboard: el filtro de T6 entrega `inventario` a los tres roles
# ---------------------------------------------------------------------------


def test_el_sobre_de_inventario_llega_al_tablero_y_al_dashboard(motor, mundo):
    """AC-6/AC-28: `inventario` a los roles con capacidad; `dashboard` sin ella.

    La prueba de frames de punta a punta -conexion SSE, agrupacion y refresco-
    se completa en T6/T15; aqui basta comprobar que el sobre y el filtro de la
    conexion entregan el dominio al tablero y la marca sintetica al dashboard.
    """
    with instalar_bus() as bus:
        with cliente_rol(motor, mundo, "Bodeguero") as cliente:
            respuesta = _movimiento(
                cliente, stock_sede_id=mundo["stock_sede_id"], cantidad=25
            )

    assert respuesta.status_code == 201, respuesta.text
    sobre = _sobre_unico(bus)
    _afirmar_sobre_de_inventario(sobre)

    # Tablero y detalle del Bodeguero (y de Administrador/Solicitante): la
    # capacidad `inventario` esta habilitada, asi que reciben el dominio.
    tablero = _contexto(
        usuario_id=mundo["usuarios_inst01"]["Bodeguero"],
        rol="Bodeguero",
        dominios_visibles=frozenset(
            {"pedidos", "inventario", "compras", "dashboard"}
        ),
    )
    assert _dominios_visibles_del_sobre(tablero, sobre) == (
        ["inventario"],
        MOTIVO_MOVIMIENTO,
    )

    solicitante = _contexto(
        usuario_id=mundo["usuarios_inst01"]["Solicitante"],
        rol="Solicitante",
        dominios_visibles=frozenset({"pedidos", "inventario", "dashboard"}),
    )
    assert _dominios_visibles_del_sobre(solicitante, sobre) == (
        ["inventario"],
        MOTIVO_MOVIMIENTO,
    )

    # Conexion con `inventario` apagado pero `dashboard` encendido: recibe la
    # marca sintetica, nunca el dominio oculto ni el motivo real (AC-28/T6).
    solo_dashboard = _contexto(
        usuario_id=mundo["usuarios_inst01"]["Solicitante"],
        rol="Solicitante",
        dominios_visibles=frozenset({"pedidos", "dashboard"}),
    )
    assert _dominios_visibles_del_sobre(solo_dashboard, sobre) == (
        ["dashboard"],
        "cambio",
    )
