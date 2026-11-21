"""T2 (Feature 011): dashboard 009 sobre la nueva granularidad — pruebas rojas.

Seam bajo prueba: la **interfaz HTTP del `app` real** (`GET /api/v1/dashboard/`).

La Feature 011 no cambia el significado de los KPI de la Feature 009: cambia su
**fuente**. Las formulas se conservan (spec D-6) y se aplican al stock por sede; lo
que desaparece es la lectura de saldos departamentales legados. En concreto:

  * `unidades_en_stock` = suma de los saldos por sede del ambito;
  * `total_alertas` = filas de stock por sede con `stock_actual <= stock_minimo`
    (la criticidad se evalua **por sede**, spec AC-11);
  * la actividad sigue leyendo la auditoria y muestra los movimientos por
    `stock_sede_id`; la Feature 026 retiro el enlace legado `inventario_id`.

Trazabilidad AC (spec 011 §5):

  * **AC-11** criticidad y compatibilidad analitica.
  * **AC-2** ausencia de una segunda fuente operativa de saldo.

Estado actual: la suite esta en verde. Cada prueba arranca con la guarda de
capacidad correspondiente y siembra el stock por sede que necesita.
"""

from __future__ import annotations

from sqlalchemy.orm import sessionmaker

from app.models import MovimientoInventario, Producto, StockSede

from tests.funcional.integracion._soporte_sede_011 import (
    RUTA_DASHBOARD,
    cliente,
    crear_sede,
    crear_stock_sede,
    exigir_contrato_alerta_por_sede,
    sesion,
)


def _crear_producto(motor, *, datos_base, nombre: str, stock_minimo: int) -> int:
    db = sessionmaker(bind=motor)()
    try:
        producto = Producto(
            nombre=nombre,
            descripcion=f"Producto {nombre}",
            unidad_medida="UNIDAD",
            stock_minimo=stock_minimo,
            categoria_id=datos_base["categoria_id"],
            institucion_id=datos_base["institucion_id"],
        )
        db.add(producto)
        db.commit()
        db.refresh(producto)
        return producto.producto_id
    finally:
        db.close()


def _crear_movimiento(motor, *, stock_sede_id: int, cantidad: int) -> int:
    with sesion(motor) as db:
        movimiento = MovimientoInventario(
            tipo_movimiento="ENTRADA",
            cantidad=cantidad,
            observacion="movimiento historico",
            stock_sede_id=stock_sede_id,
        )
        db.add(movimiento)
        db.commit()
        db.refresh(movimiento)
        return movimiento.movimiento_id


def _dashboard(motor, rol: str, *, departamento_id: int, usuario_id: int = 9999) -> dict:
    with cliente(
        motor, rol, departamento_id=departamento_id, usuario_id=usuario_id
    ) as cliente_http:
        respuesta = cliente_http.get(RUTA_DASHBOARD)
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


# ---------------------------------------------------------------------------
# AC-2/AC-11: los KPI salen del stock por sede
# ---------------------------------------------------------------------------


def test_kpi_unidades_en_stock_suma_el_stock_por_sede(motor, datos_base):
    """AC-2: las unidades son la suma de las sedes, unica fuente de saldo.

    Con dos sedes de 30 y 12 el KPI debe sumar 42. La fixture base ya no siembra
    saldo: cada caso declara el suyo (Feature 026).
    """
    sede_norte = crear_sede(motor, institucion_id=datos_base["institucion_id"], nombre="Norte")
    sede_sur = crear_sede(motor, institucion_id=datos_base["institucion_id"], nombre="Sur")
    crear_stock_sede(
        motor, sede_id=sede_norte, producto_id=datos_base["producto_id"],
        stock_actual=30, institucion_id=datos_base["institucion_id"],
    )
    crear_stock_sede(
        motor, sede_id=sede_sur, producto_id=datos_base["producto_id"],
        stock_actual=12, institucion_id=datos_base["institucion_id"],
    )

    cuerpo = _dashboard(
        motor, "Administrador", departamento_id=datos_base["departamento_id"]
    )

    assert cuerpo["kpi"]["unidades_en_stock"] == 42


def test_kpi_sin_stock_por_sede_no_cuenta_el_legado(motor, datos_base):
    """AC-2: un saldo vigente cero produce KPI cero."""
    sede = crear_sede(
        motor, institucion_id=datos_base["institucion_id"], nombre="Sede Unica"
    )
    crear_stock_sede(
        motor, sede_id=sede, producto_id=datos_base["producto_id"],
        stock_actual=50, institucion_id=datos_base["institucion_id"],
    )
    with sesion(motor) as db:
        db.query(StockSede).filter(
            StockSede.producto_id == datos_base["producto_id"],
            StockSede.institucion_id == datos_base["institucion_id"],
        ).update({StockSede.stock_actual: 0})
        db.commit()
    cuerpo = _dashboard(
        motor, "Administrador", departamento_id=datos_base["departamento_id"]
    )

    assert cuerpo["kpi"]["unidades_en_stock"] == 0
    assert cuerpo["kpi"]["total_alertas"] == 1
    assert len(cuerpo["alertas"]) == 1


def test_alerta_por_sede_critica(motor, datos_base):
    """AC-11: la alerta corresponde a la sede critica y la atribuye.

    Producto con minimo 10: la sede A tiene 3 (critica) y la sede B 100 (holgada).
    El total agregado (103) no debe ocultar la alerta de A.
    """
    exigir_contrato_alerta_por_sede()
    producto_id = _crear_producto(
        motor, datos_base=datos_base, nombre="Producto alertable", stock_minimo=10
    )
    sede_a = crear_sede(motor, institucion_id=datos_base["institucion_id"], nombre="A")
    sede_b = crear_sede(motor, institucion_id=datos_base["institucion_id"], nombre="B")
    crear_stock_sede(
        motor, sede_id=sede_a, producto_id=producto_id, stock_actual=3,
        institucion_id=datos_base["institucion_id"],
    )
    crear_stock_sede(
        motor, sede_id=sede_b, producto_id=producto_id, stock_actual=100,
        institucion_id=datos_base["institucion_id"],
    )

    cuerpo = _dashboard(
        motor, "Administrador", departamento_id=datos_base["departamento_id"]
    )

    assert cuerpo["kpi"]["total_alertas"] == 1
    alerta = cuerpo["alertas"][0]
    assert alerta["producto_id"] == producto_id
    assert alerta["stock_actual"] == 3
    assert alerta["stock_minimo"] == 10
    assert alerta["sede_id"] == sede_a, "la alerta se atribuye a la sede critica"
    assert alerta["institucion_id"] == datos_base["institucion_id"]


def test_alerta_por_sede_en_el_borde_del_minimo(motor, datos_base):
    """AC-11: la regla por sede conserva el `<=` de la 009 (minimo exacto alerta)."""
    exigir_contrato_alerta_por_sede()
    producto_en_minimo = _crear_producto(
        motor, datos_base=datos_base, nombre="En el minimo", stock_minimo=10
    )
    producto_justo_arriba = _crear_producto(
        motor, datos_base=datos_base, nombre="Unidad arriba", stock_minimo=10
    )
    sede_id = crear_sede(motor, institucion_id=datos_base["institucion_id"])
    crear_stock_sede(
        motor, sede_id=sede_id, producto_id=producto_en_minimo, stock_actual=10,
        institucion_id=datos_base["institucion_id"],
    )
    crear_stock_sede(
        motor, sede_id=sede_id, producto_id=producto_justo_arriba, stock_actual=11,
        institucion_id=datos_base["institucion_id"],
    )

    cuerpo = _dashboard(
        motor, "Administrador", departamento_id=datos_base["departamento_id"]
    )

    productos_alertados = {fila["producto_id"] for fila in cuerpo["alertas"]}
    assert productos_alertados == {producto_en_minimo}


def test_actividad_reune_movimientos_por_sede(motor, datos_base):
    """AC-11/026: la actividad lee todos los movimientos por sede."""
    exigir_contrato_alerta_por_sede()
    sede_id = crear_sede(motor, institucion_id=datos_base["institucion_id"])
    fila_stock = crear_stock_sede(
        motor, sede_id=sede_id, producto_id=datos_base["producto_id"],
        stock_actual=10, institucion_id=datos_base["institucion_id"],
    )
    movimiento_anterior = _crear_movimiento(
        motor, stock_sede_id=fila_stock, cantidad=5
    )
    with sesion(motor) as db:
        nuevo = MovimientoInventario(
            tipo_movimiento="ENTRADA",
            cantidad=7,
            observacion="consolidacion por sede",
            stock_sede_id=fila_stock,
        )
        db.add(nuevo)
        db.commit()
        db.refresh(nuevo)
        movimiento_nuevo = nuevo.movimiento_id

    cuerpo = _dashboard(
        motor, "Administrador", departamento_id=datos_base["departamento_id"]
    )

    ids_actividad = {
        fila["movimiento_id"] for fila in cuerpo["actividad_movimientos"]
    }
    assert {movimiento_anterior, movimiento_nuevo} <= ids_actividad
