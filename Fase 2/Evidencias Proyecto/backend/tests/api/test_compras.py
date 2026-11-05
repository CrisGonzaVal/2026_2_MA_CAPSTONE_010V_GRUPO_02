"""Tests de la Feature 020: reabastecimiento externo y compras.

Seccion T4 (servicio, parte 1): necesidades de reabastecimiento, catalogo de
proveedores, CRUD de la Orden de Compra, factura y cancelacion. La suite se
ejecuta sobre SQLite en memoria, igual que el resto de la suite funcional; las
pruebas de esquemas, concurrencia y replicacion real de proveedores viven en los
tests gated de PostgreSQL 16.

Seam bajo prueba: las funciones publicas de `app.services.compra_service`, que
son las que los endpoints de T6 cablean. Las aserciones leen lo persistido con
una sesion nueva, no el estado del objeto devuelto, para no confundir "el
servicio muto el ORM" con "la transaccion quedo confirmada".
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.models import (
    DetalleOrdenCompra,
    DetalleTicket,
    FacturaCompra,
    HistorialTransicionTicket,
    MovimientoInventario,
    OrdenCompra,
    Prioridad,
    Producto,
    Proveedor,
    ProveedorControl,
    StockSede,
    Ticket,
)
from app.schemas.compra_schema import (
    CancelacionOrdenCompra,
    DetalleOrdenCompraCrear,
    FacturaCompraRegistrar,
    OrdenCompraActualizar,
    OrdenCompraCrear,
    ProveedorCrear,
)
from app.schemas.inventario_schema import MovimientoCrear
from app.services import compra_service, inventario_service, ticket_service

from tests.api._soporte_ciclo_vida_013 import sembrar_ticket
from tests.api._soporte_ciclo_vida_catalogo_014 import (
    crear_categoria,
    crear_producto,
    fijar_stock_sede,
    marcar_producto,
    sembrar_mundo_014,
)
from tests.api._soporte_sede_011 import (
    asignar_sede_a_usuario,
    crear_sede,
    identidad,
    sesion,
)

# ---------------------------------------------------------------------------
# Mundo de prueba
# ---------------------------------------------------------------------------


@pytest.fixture
def mundo(motor, dos_instituciones):
    """Sede del departamento, stock base y catalogo de estados de la 013."""
    return sembrar_mundo_014(motor, dos_instituciones)


def _admin(datos):
    return identidad(
        "Administrador", datos["departamento_id"], datos["usuario_id"]
    )


def _superadmin(datos):
    return identidad(
        "Superadmin",
        datos["departamento_ajeno_id"],
        datos["usuarios_inst02"]["Superadmin"],
    )


def _bodeguero(datos):
    return identidad(
        "Bodeguero",
        datos["departamento_id"],
        datos["usuarios_inst01"]["Bodeguero"],
        sede_id=datos["sede_id"],
    )


@contextmanager
def _sesiones(motor):
    """Dos sesiones sobre el mismo motor (control y tenant en SQLite)."""
    Fabrica = sessionmaker(autocommit=False, autoflush=False, bind=motor)
    db_control = Fabrica()
    db_tenant = Fabrica()
    try:
        yield db_control, db_tenant
    finally:
        db_control.close()
        db_tenant.close()


def _crear_proveedor_control(
    motor, *, rut: str, razon_social: str, activo: bool = True
) -> int:
    """Inserta un proveedor directamente en el catalogo global de prueba."""
    with sesion(motor) as db:
        fila = ProveedorControl(
            rut=rut, razon_social=razon_social, activo=activo
        )
        db.add(fila)
        db.commit()
        db.refresh(fila)
        return fila.proveedor_id


def _crear_orden(motor, mundo, *, proveedor_id: int, cantidad: int = 3):
    """Crea una OC en Borrador por el servicio y devuelve su id."""
    with _sesiones(motor) as (db_control, db_tenant):
        orden = compra_service.crear_orden_compra(
            db_tenant,
            db_control,
            OrdenCompraCrear(
                sede_id=mundo["sede_id"],
                proveedor_id=proveedor_id,
                items=[
                    DetalleOrdenCompraCrear(
                        producto_id=mundo["producto_id"],
                        cantidad_solicitada=cantidad,
                        precio_unitario=Decimal("2.50"),
                    )
                ],
            ),
            _admin(mundo),
        )
        return orden.orden_compra_id


def _emitir(motor, mundo, orden_id: int):
    with _sesiones(motor) as (db_control, db_tenant):
        return compra_service.emitir_orden_compra(
            db_tenant, orden_id, _admin(mundo)
        )


def _facturar(motor, mundo, orden_id: int, numero: str, **cambios):
    datos = {
        "numero_factura": numero,
        "fecha_factura": date.today(),
        "monto_total": Decimal("100.00"),
    }
    datos.update(cambios)
    payload = FacturaCompraRegistrar(**datos)
    with _sesiones(motor) as (db_control, db_tenant):
        return compra_service.registrar_o_editar_factura(
            db_tenant, orden_id, payload, _admin(mundo)
        )


def _leer_orden(motor, orden_id: int) -> OrdenCompra:
    with sesion(motor) as db:
        orden = db.get(OrdenCompra, orden_id)
        assert orden is not None
        # Fuerza la carga de las relaciones antes de cerrar la sesion.
        _ = orden.detalles, orden.factura, orden.proveedor, orden.sede
        return orden


def _necesidad(cuerpo, sede_id: int, producto_id: int):
    for fila in cuerpo:
        if fila.sede_id == sede_id and fila.producto_id == producto_id:
            return fila
    return None


# ---------------------------------------------------------------------------
# AC-1: necesidades de reabastecimiento por sede
# ---------------------------------------------------------------------------


def test_necesidades_consolida_formula_y_solo_tickets_en_curso(motor, mundo):
    """AC-1: agrupa por (sede, producto) y aplica max(0, min + demanda - stock)."""
    fijar_stock_sede(motor, mundo, mundo["producto_id"], 2)
    critico = crear_producto(
        motor,
        mundo,
        nombre="Critico sin demanda",
        stock_minimo=10,
        stock_sede=4,
    )
    inactivo = crear_producto(
        motor,
        mundo,
        nombre="Inactivo fuera de necesidades",
        stock_minimo=10,
        stock_sede=0,
    )
    marcar_producto(motor, inactivo, False)

    sembrar_ticket(
        motor,
        mundo,
        estado_id=mundo["estados"]["EnCurso"],
        producto_id=mundo["producto_id"],
        cantidad=5,
    )
    # Un ticket no aprobado no consume demanda de reabastecimiento.
    sembrar_ticket(
        motor,
        mundo,
        estado_id=mundo["estados"]["Pendiente"],
        producto_id=mundo["producto_id"],
        cantidad=100,
    )

    with sesion(motor) as db:
        cuerpo = compra_service.listar_necesidades_reabastecimiento(
            db, mundo["institucion_id"]
        )

    base = _necesidad(cuerpo, mundo["sede_id"], mundo["producto_id"])
    assert base is not None
    assert base.stock_actual == 2
    assert base.stock_minimo == 10
    assert base.demanda_tickets == 5
    assert base.sugerido == 13

    fila_critica = _necesidad(cuerpo, mundo["sede_id"], critico)
    assert fila_critica is not None
    assert fila_critica.stock_actual == 4
    assert fila_critica.demanda_tickets == 0
    assert fila_critica.sugerido == 6

    assert _necesidad(cuerpo, mundo["sede_id"], inactivo) is None


def test_necesidades_de_sede_inexistente_o_ajena_devuelve_lista_vacia(motor, mundo):
    """AC-1/§9.7: el filtro de sede no revela recursos y responde 200/[]."""
    from tests.api._soporte_sede_011 import crear_sede

    sede_ajena = crear_sede(
        motor, institucion_id="INST02", nombre="Sede de la institucion ajena"
    )
    with sesion(motor) as db:
        assert (
            compra_service.listar_necesidades_reabastecimiento(
                db, mundo["institucion_id"], sede_id=sede_ajena
            )
            == []
        )
        assert (
            compra_service.listar_necesidades_reabastecimiento(
                db, mundo["institucion_id"], sede_id=999999
            )
            == []
        )


# ---------------------------------------------------------------------------
# AC-2: catalogo global de proveedores
# ---------------------------------------------------------------------------


def test_listar_proveedores_solo_activos_y_ordenados_por_razon_social(motor, mundo):
    """AC-2: el selector ofrece solo activos, en orden alfabetico."""
    _crear_proveedor_control(motor, rut="77.777.777-7", razon_social="Zeta")
    _crear_proveedor_control(motor, rut="11.111.111-1", razon_social="Alfa")
    _crear_proveedor_control(
        motor, rut="22.222.222-2", razon_social="Beta inactiva", activo=False
    )

    with sesion(motor) as db:
        proveedores = compra_service.listar_proveedores(db)

    assert [p.razon_social for p in proveedores] == ["Alfa", "Zeta"]


def test_crear_proveedor_como_administrador_y_superadmin(motor, mundo):
    """AC-2: ambos roles crean en control; el RUT duplicado responde 409."""
    datos = ProveedorCrear(
        rut="12.345.678-9",
        razon_social="Suministros del Sur SpA",
        giro="Papeleria",
        correo="ventas@suministros.cl",
        telefono="+56911112222",
    )
    with _sesiones(motor) as (db_control, db_tenant):
        creado = compra_service.crear_proveedor(
            db_control, db_tenant, datos, _admin(mundo)
        )
        proveedor_id = creado.proveedor_id

    with sesion(motor) as db:
        control = db.get(ProveedorControl, proveedor_id)
        replica = db.get(Proveedor, proveedor_id)
        assert control is not None and control.activo is True
        assert replica is not None and replica.rut == "12.345.678-9"

    datos_superadmin = ProveedorCrear(
        rut="98.765.432-1", razon_social="Insumos Globales Ltda"
    )
    with _sesiones(motor) as (db_control, db_tenant):
        desde_saas = compra_service.crear_proveedor(
            db_control, db_tenant, datos_superadmin, _superadmin(mundo)
        )
    assert desde_saas.proveedor_id != proveedor_id

    with _sesiones(motor) as (db_control, db_tenant):
        with pytest.raises(HTTPException) as error:
            compra_service.crear_proveedor(
                db_control, db_tenant, datos, _superadmin(mundo)
            )
    assert error.value.status_code == 409


# ---------------------------------------------------------------------------
# AC-3: creacion y edicion de la OC en Borrador
# ---------------------------------------------------------------------------


def test_crear_orden_compra_calcula_total_y_deja_borrador(motor, mundo):
    """AC-3: la OC nace en Borrador, sin numero y con total calculado."""
    proveedor_id = _crear_proveedor_control(
        motor, rut="13.131.313-1", razon_social="Proveedor OC"
    )
    segundo = crear_producto(
        motor, mundo, nombre="Producto secundario", stock_minimo=0
    )

    with _sesiones(motor) as (db_control, db_tenant):
        orden = compra_service.crear_orden_compra(
            db_tenant,
            db_control,
            OrdenCompraCrear(
                sede_id=mundo["sede_id"],
                proveedor_id=proveedor_id,
                items=[
                    DetalleOrdenCompraCrear(
                        producto_id=mundo["producto_id"],
                        cantidad_solicitada=3,
                        precio_unitario=Decimal("2.50"),
                    ),
                    DetalleOrdenCompraCrear(
                        producto_id=segundo,
                        cantidad_solicitada=2,
                        precio_unitario=Decimal("10.00"),
                    ),
                ],
            ),
            _admin(mundo),
        )
        orden_id = orden.orden_compra_id

    persistida = _leer_orden(motor, orden_id)
    assert persistida.estado == "Borrador"
    assert persistida.numero_oc is None
    assert persistida.institucion_id == mundo["institucion_id"]
    assert persistida.sede_id == mundo["sede_id"]
    assert persistida.proveedor_id == proveedor_id
    assert persistida.total == Decimal("27.50")
    assert len(persistida.detalles) == 2
    assert persistida.proveedor.rut == "13.131.313-1"


def test_crear_orden_compra_rechaza_referencias_invalidas(motor, mundo):
    """AC-3: sede ajena, proveedor inactivo, producto inactivo/ajeno o repetido."""
    from tests.api._soporte_sede_011 import crear_sede

    activo = _crear_proveedor_control(
        motor, rut="14.141.414-1", razon_social="Proveedor valido"
    )
    inactivo = _crear_proveedor_control(
        motor, rut="15.151.515-1", razon_social="Proveedor inactivo", activo=False
    )
    sede_ajena = crear_sede(motor, institucion_id="INST02", nombre="Sede ajena")
    producto_inactivo = crear_producto(
        motor, mundo, nombre="Producto inactivo OC", stock_minimo=0
    )
    marcar_producto(motor, producto_inactivo, False)
    categoria_ajena = crear_categoria(
        motor, mundo, nombre="Categoria ajena OC", institucion_id="INST02"
    )
    producto_ajeno = crear_producto(
        motor,
        mundo,
        nombre="Producto ajeno OC",
        categoria_id=categoria_ajena,
        institucion_id="INST02",
    )

    def _intentar(sede_id, proveedor_id, items):
        with _sesiones(motor) as (db_control, db_tenant):
            return compra_service.crear_orden_compra(
                db_tenant,
                db_control,
                OrdenCompraCrear(
                    sede_id=sede_id, proveedor_id=proveedor_id, items=items
                ),
                _admin(mundo),
            )

    item_valido = DetalleOrdenCompraCrear(
        producto_id=mundo["producto_id"], cantidad_solicitada=1
    )

    casos = [
        (sede_ajena, activo, [item_valido], 404),
        (mundo["sede_id"], inactivo, [item_valido], 409),
        (
            mundo["sede_id"],
            activo,
            [
                DetalleOrdenCompraCrear(
                    producto_id=producto_inactivo, cantidad_solicitada=1
                )
            ],
            409,
        ),
        (
            mundo["sede_id"],
            activo,
            [
                DetalleOrdenCompraCrear(
                    producto_id=producto_ajeno, cantidad_solicitada=1
                )
            ],
            404,
        ),
        (mundo["sede_id"], activo, [item_valido, item_valido], 409),
    ]
    for sede_id, proveedor_id, items, esperado in casos:
        with pytest.raises(HTTPException) as error:
            _intentar(sede_id, proveedor_id, items)
        assert error.value.status_code == esperado


def test_actualizar_orden_compra_reemplaza_solo_en_borrador(motor, mundo):
    """AC-3/DT-14: el PUT reemplaza sede, proveedor e items solo en Borrador."""
    proveedor = _crear_proveedor_control(
        motor, rut="16.161.616-1", razon_social="Proveedor edicion"
    )
    orden_id = _crear_orden(motor, mundo, proveedor_id=proveedor)

    with _sesiones(motor) as (db_control, db_tenant):
        actualizada = compra_service.actualizar_orden_compra(
            db_tenant,
            db_control,
            orden_id,
            OrdenCompraActualizar(
                sede_id=mundo["sede_id"],
                proveedor_id=proveedor,
                items=[
                    DetalleOrdenCompraCrear(
                        producto_id=mundo["producto_id"],
                        cantidad_solicitada=7,
                        precio_unitario=Decimal("1.25"),
                    )
                ],
            ),
            _admin(mundo),
        )
        assert actualizada.total == Decimal("8.75")

    persistida = _leer_orden(motor, orden_id)
    assert persistida.estado == "Borrador"
    assert len(persistida.detalles) == 1
    assert persistida.detalles[0].cantidad_solicitada == 7
    assert persistida.total == Decimal("8.75")

    _emitir(motor, mundo, orden_id)
    with _sesiones(motor) as (db_control, db_tenant):
        with pytest.raises(HTTPException) as error:
            compra_service.actualizar_orden_compra(
                db_tenant,
                db_control,
                orden_id,
                OrdenCompraActualizar(
                    sede_id=mundo["sede_id"],
                    proveedor_id=proveedor,
                    items=[
                        DetalleOrdenCompraCrear(
                            producto_id=mundo["producto_id"],
                            cantidad_solicitada=1,
                        )
                    ],
                ),
                _admin(mundo),
            )
    assert error.value.status_code == 409


# ---------------------------------------------------------------------------
# AC-4: emision formal
# ---------------------------------------------------------------------------


def test_emitir_ordena_numero_formato_y_bloquea_segunda_emision(motor, mundo):
    """AC-4: numero OC-{ANIO}-{id:06d}, fecha de emision y 409 al repetir."""
    proveedor = _crear_proveedor_control(
        motor, rut="17.171.717-1", razon_social="Proveedor emision"
    )
    orden_id = _crear_orden(motor, mundo, proveedor_id=proveedor)

    emitida = _emitir(motor, mundo, orden_id)
    assert emitida.estado == "Emitida"
    assert emitida.numero_oc == f"OC-{date.today().year:04d}-{orden_id:06d}"
    assert emitida.fecha_emision is not None

    with _sesiones(motor) as (db_control, db_tenant):
        with pytest.raises(HTTPException) as error:
            compra_service.emitir_orden_compra(
                db_tenant, orden_id, _admin(mundo)
            )
    assert error.value.status_code == 409


def test_emitir_rechaza_producto_desactivado_antes_de_emitir(motor, mundo):
    """AC-4/§9.10: la emision exige productos activos y no muta la orden."""
    proveedor = _crear_proveedor_control(
        motor, rut="18.181.818-1", razon_social="Proveedor emision inactivo"
    )
    orden_id = _crear_orden(motor, mundo, proveedor_id=proveedor)
    marcar_producto(motor, mundo["producto_id"], False)

    with _sesiones(motor) as (db_control, db_tenant):
        with pytest.raises(HTTPException) as error:
            compra_service.emitir_orden_compra(
                db_tenant, orden_id, _admin(mundo)
            )
    assert error.value.status_code == 409
    assert _leer_orden(motor, orden_id).estado == "Borrador"


# ---------------------------------------------------------------------------
# AC-5: factura como llave de activacion
# ---------------------------------------------------------------------------


def test_factura_crea_pasa_a_facturada_y_se_puede_reeditar(motor, mundo):
    """AC-5: Emitida -> Facturada; en Facturada se corrigen los metadatos."""
    proveedor = _crear_proveedor_control(
        motor, rut="19.191.919-1", razon_social="Proveedor factura"
    )
    orden_id = _crear_orden(motor, mundo, proveedor_id=proveedor)
    _emitir(motor, mundo, orden_id)

    factura = _facturar(motor, mundo, orden_id, "FAC-001")
    assert factura.orden_compra_id == orden_id
    assert factura.proveedor_id == proveedor
    assert factura.monto_total == Decimal("100.00")
    orden = _leer_orden(motor, orden_id)
    assert orden.estado == "Facturada"
    assert orden.factura.numero_factura == "FAC-001"

    corregida = _facturar(
        motor,
        mundo,
        orden_id,
        "FAC-001-R",
        monto_total=Decimal("120.50"),
        observaciones="Correccion de monto",
    )
    assert corregida.factura_compra_id == factura.factura_compra_id
    orden = _leer_orden(motor, orden_id)
    assert orden.estado == "Facturada"
    assert orden.factura.numero_factura == "FAC-001-R"
    assert orden.factura.monto_total == Decimal("120.50")
    assert orden.factura.observaciones == "Correccion de monto"


def test_factura_rechaza_estado_duplicado_y_fecha_futura(motor, mundo):
    """AC-5: 409 fuera de Emitida/Facturada, 409 duplicado y 422 fecha futura."""
    proveedor = _crear_proveedor_control(
        motor, rut="20.202.020-1", razon_social="Proveedor factura errores"
    )
    orden_id = _crear_orden(motor, mundo, proveedor_id=proveedor)

    # Borrador: la factura aun no esta habilitada.
    with _sesiones(motor) as (db_control, db_tenant):
        with pytest.raises(HTTPException) as error:
            compra_service.registrar_o_editar_factura(
                db_tenant,
                orden_id,
                FacturaCompraRegistrar(
                    numero_factura="FAC-BORRADOR",
                    fecha_factura=date.today(),
                    monto_total=Decimal("10.00"),
                ),
                _admin(mundo),
            )
    assert error.value.status_code == 409

    _emitir(motor, mundo, orden_id)

    # Fecha futura: 422 antes de crear la factura.
    with _sesiones(motor) as (db_control, db_tenant):
        with pytest.raises(HTTPException) as error:
            compra_service.registrar_o_editar_factura(
                db_tenant,
                orden_id,
                FacturaCompraRegistrar(
                    numero_factura="FAC-FUTURA",
                    fecha_factura=date.today() + timedelta(days=1),
                    monto_total=Decimal("10.00"),
                ),
                _admin(mundo),
            )
    assert error.value.status_code == 422

    _facturar(motor, mundo, orden_id, "FAC-UNICA")

    # Segunda OC del mismo proveedor: el numero ya esta usado.
    otra = _crear_orden(motor, mundo, proveedor_id=proveedor)
    _emitir(motor, mundo, otra)
    with _sesiones(motor) as (db_control, db_tenant):
        with pytest.raises(HTTPException) as error:
            compra_service.registrar_o_editar_factura(
                db_tenant,
                otra,
                FacturaCompraRegistrar(
                    numero_factura="FAC-UNICA",
                    fecha_factura=date.today(),
                    monto_total=Decimal("10.00"),
                ),
                _admin(mundo),
            )
    assert error.value.status_code == 409

    # Una orden ya recibida no admite correccion de factura.
    with sesion(motor) as db:
        orden = db.get(OrdenCompra, orden_id)
        orden.estado = "Recibida"
        db.commit()
    with _sesiones(motor) as (db_control, db_tenant):
        with pytest.raises(HTTPException) as error:
            compra_service.registrar_o_editar_factura(
                db_tenant,
                orden_id,
                FacturaCompraRegistrar(
                    numero_factura="FAC-UNICA",
                    fecha_factura=date.today(),
                    monto_total=Decimal("99.00"),
                ),
                _admin(mundo),
            )
    assert error.value.status_code == 409


# ---------------------------------------------------------------------------
# AC-12: cancelacion con actor, fecha y motivo
# ---------------------------------------------------------------------------


def test_cancelar_borrador_y_emitida_persiste_actor_motivo_y_fecha(motor, mundo):
    """AC-12: Borrador y Emitida cancelan; se guardan motivo, fecha y actor."""
    proveedor = _crear_proveedor_control(
        motor, rut="21.212.121-1", razon_social="Proveedor cancelacion"
    )
    desde_borrador = _crear_orden(motor, mundo, proveedor_id=proveedor)
    desde_emitida = _crear_orden(motor, mundo, proveedor_id=proveedor)
    _emitir(motor, mundo, desde_emitida)

    for orden_id in (desde_borrador, desde_emitida):
        with _sesiones(motor) as (db_control, db_tenant):
            cancelada = compra_service.cancelar_orden_compra(
                db_tenant,
                orden_id,
                CancelacionOrdenCompra(motivo_cancelacion="Proveedor sin stock"),
                _admin(mundo),
            )
            assert cancelada.estado == "Cancelada"

        persistida = _leer_orden(motor, orden_id)
        assert persistida.estado == "Cancelada"
        assert persistida.motivo_cancelacion == "Proveedor sin stock"
        assert persistida.fecha_cancelacion is not None
        assert persistida.cancelado_por_usuario_id == mundo["usuario_id"]


def test_cancelar_rechaza_estados_terminales_y_motivo_vacio(motor, mundo):
    """AC-12: Facturada/Recibida/Cancelada responden 409; motivo vacio 422."""
    proveedor = _crear_proveedor_control(
        motor, rut="22.222.222-2", razon_social="Proveedor cancelacion errores"
    )
    orden_id = _crear_orden(motor, mundo, proveedor_id=proveedor)
    _emitir(motor, mundo, orden_id)

    with _sesiones(motor) as (db_control, db_tenant):
        with pytest.raises(HTTPException) as error:
            compra_service.cancelar_orden_compra(
                db_tenant,
                orden_id,
                CancelacionOrdenCompra(motivo_cancelacion="   "),
                _admin(mundo),
            )
    assert error.value.status_code == 422

    _facturar(motor, mundo, orden_id, "FAC-CANCELAR")
    with _sesiones(motor) as (db_control, db_tenant):
        with pytest.raises(HTTPException) as error:
            compra_service.cancelar_orden_compra(
                db_tenant,
                orden_id,
                CancelacionOrdenCompra(motivo_cancelacion="Ya no aplica"),
                _admin(mundo),
            )
    assert error.value.status_code == 409
    assert _leer_orden(motor, orden_id).estado == "Facturada"


# ---------------------------------------------------------------------------
# T5: cobertura greedy y recepcion ACID
# ---------------------------------------------------------------------------


def _prioridad(motor, nombre: str) -> int:
    with sesion(motor) as db:
        existente = db.execute(
            select(Prioridad).where(Prioridad.nombre == nombre)
        ).scalar_one_or_none()
        if existente is not None:
            return existente.prioridad_id
        fila = Prioridad(nombre=nombre, descripcion=f"Prioridad {nombre}")
        db.add(fila)
        db.commit()
        db.refresh(fila)
        return fila.prioridad_id


def _ticket_con_detalles(
    motor,
    mundo,
    *,
    detalles: list[tuple[int, int]],
    prioridad_id: int,
    estado: str = "EnCurso",
    fecha_creacion: datetime | None = None,
    usuario_id: int | None = None,
    sede_id: int | None = None,
) -> int:
    """Crea un ticket con varios detalles y control total del orden FIFO."""
    with sesion(motor) as db:
        ticket = Ticket(
            usuario_id=(
                usuario_id
                if usuario_id is not None
                else mundo["usuarios_inst01"]["Solicitante"]
            ),
            prioridad_id=prioridad_id,
            estado_id=mundo["estados"][estado],
            asunto="Ticket de cobertura 020",
            descripcion="Sembrado para la simulacion greedy.",
            institucion_id=mundo["institucion_id"],
            sede_id=sede_id if sede_id is not None else mundo["sede_id"],
        )
        if fecha_creacion is not None:
            ticket.fecha_creacion = fecha_creacion
        db.add(ticket)
        db.flush()
        for producto_id, cantidad in detalles:
            db.add(
                DetalleTicket(
                    ticket_id=ticket.ticket_id,
                    producto_id=producto_id,
                    cantidad_solicitada=cantidad,
                    cantidad_entregada=0,
                    institucion_id=mundo["institucion_id"],
                )
            )
        db.commit()
        return ticket.ticket_id


def _stock_de(motor, sede_id: int, producto_id: int) -> int | None:
    with sesion(motor) as db:
        fila = db.execute(
            select(StockSede).where(
                StockSede.sede_id == sede_id,
                StockSede.producto_id == producto_id,
            )
        ).scalar_one_or_none()
        return None if fila is None else fila.stock_actual


def _crear_orden_con_items(motor, mundo, *, proveedor_id: int, items):
    with _sesiones(motor) as (db_control, db_tenant):
        orden = compra_service.crear_orden_compra(
            db_tenant,
            db_control,
            OrdenCompraCrear(
                sede_id=mundo["sede_id"],
                proveedor_id=proveedor_id,
                items=items,
            ),
            _admin(mundo),
        )
        return orden.orden_compra_id


def _orden_facturada(motor, mundo, *, items, numero_factura: str):
    proveedor = _crear_proveedor_control(
        motor, rut=f"30.{len(numero_factura):06d}-1", razon_social="Proveedor recepcion"
    )
    orden_id = _crear_orden_con_items(
        motor, mundo, proveedor_id=proveedor, items=items
    )
    _emitir(motor, mundo, orden_id)
    _facturar(motor, mundo, orden_id, numero_factura)
    return orden_id


def _bodeguero_con_sede(motor, mundo, *, sede_id: int | None = None):
    sede = mundo["sede_id"] if sede_id is None else sede_id
    asignar_sede_a_usuario(
        motor, mundo["usuarios_inst01"]["Bodeguero"], sede
    )
    return identidad(
        "Bodeguero",
        mundo["departamento_id"],
        mundo["usuarios_inst01"]["Bodeguero"],
        sede_id=sede,
    )


def test_cobertura_greedy_prioridad_fifo_y_todo_o_nada(motor, mundo):
    """§9.4: prioridad ASC, FIFO y un ticket que no cabe no consume stock."""
    alta = mundo["prioridad_id"]
    media = _prioridad(motor, "MEDIA")
    baja = _prioridad(motor, "BAJA")
    producto_b = crear_producto(
        motor, mundo, nombre="Producto B cobertura", stock_minimo=0, stock_sede=1
    )
    fijar_stock_sede(motor, mundo, mundo["producto_id"], 3)

    t1 = _ticket_con_detalles(
        motor,
        mundo,
        detalles=[(mundo["producto_id"], 2), (producto_b, 1)],
        prioridad_id=alta,
        fecha_creacion=datetime(2026, 1, 1, 9, 0, 0),
    )
    # Misma prioridad que T1, pero no cabe completo: no consume stock.
    t2 = _ticket_con_detalles(
        motor,
        mundo,
        detalles=[(mundo["producto_id"], 2)],
        prioridad_id=alta,
        fecha_creacion=datetime(2026, 1, 1, 10, 0, 0),
    )
    # Prioridad baja con fecha anterior: la prioridad manda sobre la fecha.
    t3 = _ticket_con_detalles(
        motor,
        mundo,
        detalles=[(mundo["producto_id"], 1)],
        prioridad_id=baja,
        fecha_creacion=datetime(2026, 1, 1, 8, 0, 0),
    )
    # Misma prioridad que T1 y T2, FIFO posterior: alcanza el remanente.
    t4 = _ticket_con_detalles(
        motor,
        mundo,
        detalles=[(mundo["producto_id"], 1)],
        prioridad_id=alta,
        fecha_creacion=datetime(2026, 1, 1, 11, 0, 0),
    )

    with sesion(motor) as db:
        cobertura = compra_service.calcular_cobertura_tickets(
            db, mundo["sede_id"]
        )

    assert cobertura == {t1: True, t2: False, t3: False, t4: True}


def test_recepcion_incrementa_stock_audita_y_desbloquea_ticket(motor, mundo):
    """AC-7…AC-10: recepcion total, movimiento ENTRADA y desbloqueo del ticket."""
    producto_b = crear_producto(
        motor, mundo, nombre="Producto recepcion B", stock_minimo=0, stock_sede=0
    )
    fijar_stock_sede(motor, mundo, mundo["producto_id"], 0)
    alta = mundo["prioridad_id"]
    t1 = _ticket_con_detalles(
        motor,
        mundo,
        detalles=[(mundo["producto_id"], 2), (producto_b, 1)],
        prioridad_id=alta,
        fecha_creacion=datetime(2026, 1, 1, 9, 0, 0),
    )
    t2 = _ticket_con_detalles(
        motor,
        mundo,
        detalles=[(mundo["producto_id"], 1)],
        prioridad_id=_prioridad(motor, "BAJA"),
        fecha_creacion=datetime(2026, 1, 1, 10, 0, 0),
    )

    orden_id = _orden_facturada(
        motor,
        mundo,
        items=[
            DetalleOrdenCompraCrear(
                producto_id=mundo["producto_id"],
                cantidad_solicitada=2,
                precio_unitario=Decimal("2.50"),
            ),
            DetalleOrdenCompraCrear(
                producto_id=producto_b,
                cantidad_solicitada=1,
                precio_unitario=Decimal("4.00"),
            ),
        ],
        numero_factura="FAC-REC-001",
    )
    bodeguero = _bodeguero_con_sede(motor, mundo)

    with _sesiones(motor) as (_db_control, db_tenant):
        resultado = compra_service.recepcionar_orden_compra(
            db_tenant, orden_id, bodeguero
        )

    assert resultado.estado == "Recibida"
    assert resultado.orden.estado == "Recibida"
    assert resultado.fecha_recepcion is not None
    assert _stock_de(motor, mundo["sede_id"], mundo["producto_id"]) == 2
    assert _stock_de(motor, mundo["sede_id"], producto_b) == 1

    with sesion(motor) as db:
        movimientos = list(
            db.execute(
                select(MovimientoInventario).order_by(
                    MovimientoInventario.movimiento_id
                )
            )
            .scalars()
            .all()
        )
        historial = list(
            db.execute(select(HistorialTransicionTicket)).scalars().all()
        )
        ticket_1 = db.get(Ticket, t1)
        ticket_2 = db.get(Ticket, t2)
        estado_en_curso = mundo["estados"]["EnCurso"]

    assert len(movimientos) == 2
    assert {m.tipo_movimiento for m in movimientos} == {"ENTRADA"}
    assert {m.cantidad for m in movimientos} == {1, 2}
    assert all(m.inventario_id is None for m in movimientos)
    assert all("FAC-REC-001" in (m.observacion or "") for m in movimientos)
    assert all("Bodeguero:" in (m.observacion or "") for m in movimientos)

    assert resultado.tickets_desbloqueados == [
        resultado.tickets_desbloqueados[0]
    ], "solo T1 queda cubierto"
    assert resultado.tickets_desbloqueados[0].ticket_id == t1
    assert len(historial) == 1
    fila = historial[0]
    assert fila.ticket_id == t1
    assert fila.estado_origen_id == estado_en_curso
    assert fila.estado_destino_id == estado_en_curso
    assert fila.usuario_id == mundo["usuarios_inst01"]["Bodeguero"]
    assert "Desbloqueo por reabastecimiento" in (fila.motivo or "")
    assert ticket_1.estado_id == estado_en_curso
    assert ticket_2.estado_id == estado_en_curso


def test_recepcion_crea_fila_de_stock_ausente_y_respeta_estado(motor, mundo):
    """AC-8: si no existe la fila de stock en la sede, se crea con la cantidad."""
    producto_sin_stock = crear_producto(
        motor,
        mundo,
        nombre="Producto sin fila de stock",
        stock_minimo=0,
        stock_sede=None,
    )
    orden_id = _orden_facturada(
        motor,
        mundo,
        items=[
            DetalleOrdenCompraCrear(
                producto_id=producto_sin_stock,
                cantidad_solicitada=6,
                precio_unitario=Decimal("1.00"),
            )
        ],
        numero_factura="FAC-REC-002",
    )
    bodeguero = _bodeguero_con_sede(motor, mundo)

    with _sesiones(motor) as (_db_control, db_tenant):
        resultado = compra_service.recepcionar_orden_compra(
            db_tenant, orden_id, bodeguero
        )
    assert resultado.estado == "Recibida"
    assert _stock_de(motor, mundo["sede_id"], producto_sin_stock) == 6

    with _sesiones(motor) as (_db_control, db_tenant):
        with pytest.raises(HTTPException) as error:
            compra_service.recepcionar_orden_compra(
                db_tenant, orden_id, bodeguero
            )
    assert error.value.status_code == 409


def test_recepcion_rechaza_orden_no_facturada_y_ambitos_ajenos(motor, mundo):
    """AC-6/AC-7: 409 sin factura, 404 por sede/institucion y 409 sin sede."""
    proveedor = _crear_proveedor_control(
        motor, rut="31.313.131-1", razon_social="Proveedor ambito"
    )
    orden_id = _crear_orden(motor, mundo, proveedor_id=proveedor)

    with _sesiones(motor) as (_db_control, db_tenant):
        with pytest.raises(HTTPException) as error:
            compra_service.recepcionar_orden_compra(
                db_tenant, orden_id, _bodeguero_con_sede(motor, mundo)
            )
    assert error.value.status_code == 409

    _emitir(motor, mundo, orden_id)
    _facturar(motor, mundo, orden_id, "FAC-REC-003")

    # Bodeguero sin sede: 409 antes de resolver la orden.
    sin_sede = identidad(
        "Bodeguero",
        mundo["departamento_id"],
        mundo["usuarios_inst01"]["Bodeguero"],
    )
    with _sesiones(motor) as (_db_control, db_tenant):
        with pytest.raises(HTTPException) as error:
            compra_service.recepcionar_orden_compra(
                db_tenant, orden_id, sin_sede
            )
    assert error.value.status_code == 409

    # Otra sede de la misma institucion: 404.
    otra_sede = crear_sede(
        motor, institucion_id=mundo["institucion_id"], nombre="Otra sede"
    )
    with _sesiones(motor) as (_db_control, db_tenant):
        with pytest.raises(HTTPException) as error:
            compra_service.recepcionar_orden_compra(
                db_tenant, orden_id, _bodeguero_con_sede(motor, mundo, sede_id=otra_sede)
            )
    assert error.value.status_code == 404

    # Bodeguero de otra institucion con sede propia: 404.
    sede_ajena = crear_sede(
        motor, institucion_id="INST02", nombre="Sede institucion ajena"
    )
    asignar_sede_a_usuario(
        motor, mundo["usuarios_inst02"]["Bodeguero"], sede_ajena
    )
    ajeno = identidad(
        "Bodeguero",
        mundo["departamento_ajeno_id"],
        mundo["usuarios_inst02"]["Bodeguero"],
        sede_id=sede_ajena,
    )
    with _sesiones(motor) as (_db_control, db_tenant):
        with pytest.raises(HTTPException) as error:
            compra_service.recepcionar_orden_compra(db_tenant, orden_id, ajeno)
    assert error.value.status_code == 404


def test_recepcion_permite_producto_desactivado_pero_movimiento_generico_no(motor, mundo):
    """AC-11/§9.10: la recepcion excepcional no habilita el endpoint generico."""
    producto = crear_producto(
        motor, mundo, nombre="Producto desactivado tras emitir", stock_minimo=0
    )
    orden_id = _orden_facturada(
        motor,
        mundo,
        items=[
            DetalleOrdenCompraCrear(
                producto_id=producto,
                cantidad_solicitada=3,
                precio_unitario=Decimal("1.00"),
            )
        ],
        numero_factura="FAC-REC-004",
    )
    marcar_producto(motor, producto, False)
    bodeguero = _bodeguero_con_sede(motor, mundo)

    with _sesiones(motor) as (_db_control, db_tenant):
        resultado = compra_service.recepcionar_orden_compra(
            db_tenant, orden_id, bodeguero
        )
    assert resultado.estado == "Recibida"
    assert _stock_de(motor, mundo["sede_id"], producto) == 3

    with sesion(motor) as db:
        stock = db.execute(
            select(StockSede).where(
                StockSede.sede_id == mundo["sede_id"],
                StockSede.producto_id == producto,
            )
        ).scalar_one()

    with sesion(motor) as db:
        with pytest.raises(HTTPException) as error:
            inventario_service.registrar_movimiento(
                db,
                MovimientoCrear(
                    stock_sede_id=stock.stock_sede_id,
                    tipo_movimiento="ENTRADA",
                    cantidad=1,
                    observacion="Movimiento generico sobre producto inactivo",
                ),
                bodeguero,
            )
    assert error.value.status_code == 409


def test_detalle_de_ticket_expone_stock_disponible_sin_cambiar_estado(motor, mundo):
    """AC-10/AC-11: el DTO calcula `stock_disponible` con la misma simulacion."""
    producto_b = crear_producto(
        motor, mundo, nombre="Producto badge B", stock_minimo=0, stock_sede=0
    )
    fijar_stock_sede(motor, mundo, mundo["producto_id"], 0)
    t1 = _ticket_con_detalles(
        motor,
        mundo,
        detalles=[(mundo["producto_id"], 2)],
        prioridad_id=mundo["prioridad_id"],
        fecha_creacion=datetime(2026, 1, 1, 9, 0, 0),
    )
    t2 = _ticket_con_detalles(
        motor,
        mundo,
        detalles=[(producto_b, 1)],
        prioridad_id=_prioridad(motor, "BAJA"),
        fecha_creacion=datetime(2026, 1, 1, 10, 0, 0),
    )

    orden_id = _orden_facturada(
        motor,
        mundo,
        items=[
            DetalleOrdenCompraCrear(
                producto_id=mundo["producto_id"],
                cantidad_solicitada=2,
                precio_unitario=Decimal("1.00"),
            )
        ],
        numero_factura="FAC-REC-005",
    )
    with _sesiones(motor) as (_db_control, db_tenant):
        compra_service.recepcionar_orden_compra(
            db_tenant, orden_id, _bodeguero_con_sede(motor, mundo)
        )

    with sesion(motor) as db:
        detalle_1 = ticket_service.obtener_ticket_detalle(db, t1, _admin(mundo))
        detalle_2 = ticket_service.obtener_ticket_detalle(db, t2, _admin(mundo))
        ticket_1 = db.get(Ticket, t1)
        estado_1 = ticket_1.estado_id

    assert detalle_1.stock_disponible is True
    assert detalle_2.stock_disponible is False
    assert estado_1 == mundo["estados"]["EnCurso"]
