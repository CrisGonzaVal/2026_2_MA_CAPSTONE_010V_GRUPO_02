"""Tests HTTP de la Feature 020: compras (T6).

Seam bajo prueba: la **interfaz HTTP** (`TestClient`) con los 10 endpoints de
`/api/v1/compras/*`. Las expectativas de autorizacion (matriz 62 -> 72) y de
capacidad (`compras`) se transcriben de la spec/plan, nunca se leen de
`MATRIZ_PERMISOS` ni de `MAPA_OPERACION_CAPACIDAD`.

Los escenarios de servicio (creacion de OC, emision y factura) se preparan
llamando al servicio ya probado en T4/T5; lo que se verifica aqui es el
cableado, el gating, el ambito y el contrato OpenAPI.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.api import dependencies
from app.core import capacidades, permisos
from app.main import app
from app.models import ProveedorControl, Rol, StockSede, Usuario
from app.schemas.compra_schema import (
    DetalleOrdenCompraCrear,
    FacturaCompraRegistrar,
    OrdenCompraCrear,
)
from app.services import compra_service

from tests.api._soporte_ciclo_vida_catalogo_014 import (
    CORREO_GATING,
    cliente_de_rol,
    crear_producto,
    fijar_stock_sede,
    sembrar_contexto_capacidades,
    sembrar_mundo_014,
)
from tests.api._soporte_sede_011 import cliente as cliente_de_sede
from tests.api._soporte_sede_011 import identidad, sesion

#: Las 10 operaciones nuevas de la 020 y sus roles, transcritos de la spec §7 y
#: del plan §4. No se leen de `MATRIZ_PERMISOS`.
OPERACIONES_020: dict[tuple[str, str], set[str]] = {
    ("GET", "/api/v1/compras/necesidades"): {"Administrador"},
    ("GET", "/api/v1/compras/proveedores"): {"Administrador", "Superadmin"},
    ("POST", "/api/v1/compras/proveedores"): {"Administrador", "Superadmin"},
    ("POST", "/api/v1/compras/ordenes"): {"Administrador"},
    ("GET", "/api/v1/compras/ordenes"): {"Administrador", "Bodeguero"},
    ("PUT", "/api/v1/compras/ordenes/{orden_id}"): {"Administrador"},
    ("POST", "/api/v1/compras/ordenes/{orden_id}/emitir"): {"Administrador"},
    ("PUT", "/api/v1/compras/ordenes/{orden_id}/factura"): {"Administrador"},
    ("POST", "/api/v1/compras/ordenes/{orden_id}/recepcion"): {"Bodeguero"},
    ("POST", "/api/v1/compras/ordenes/{orden_id}/cancelar"): {"Administrador"},
}

CAPACIDADES_020 = {clave: "compras" for clave in OPERACIONES_020}

TOTAL_OPERACIONES_020 = 72

_RESPUESTAS_COMUNES = {"200", "401", "403", "404", "409", "422"}


@pytest.fixture
def mundo(motor, dos_instituciones):
    """Mundo de la 014 (sede, estados y stock base) sobre las dos instituciones."""
    return sembrar_mundo_014(motor, dos_instituciones)


def _proveedor(motor, *, rut: str = "51.000.000-1", razon_social: str = "Proveedor HTTP 020") -> int:
    with sesion(motor) as db:
        fila = ProveedorControl(rut=rut, razon_social=razon_social, activo=True)
        db.add(fila)
        db.commit()
        db.refresh(fila)
        return fila.proveedor_id


def _admin(mundo):
    return identidad(
        "Administrador", mundo["departamento_id"], mundo["usuario_id"]
    )


def _payload_orden(mundo, proveedor_id: int, *, sede_id: int | None = None, cantidad: int = 2):
    return {
        "sede_id": sede_id if sede_id is not None else mundo["sede_id"],
        "proveedor_id": proveedor_id,
        "items": [
            {
                "producto_id": mundo["producto_id"],
                "cantidad_solicitada": cantidad,
                "precio_unitario": "2.50",
            }
        ],
    }


@contextmanager
def _sesiones(motor):
    from sqlalchemy.orm import sessionmaker

    Fabrica = sessionmaker(autocommit=False, autoflush=False, bind=motor)
    db_control = Fabrica()
    db_tenant = Fabrica()
    try:
        yield db_control, db_tenant
    finally:
        db_control.close()
        db_tenant.close()


def _crear_orden_servicio(
    motor, mundo, *, proveedor_id: int, sede_id: int | None = None, cantidad: int = 2
) -> int:
    with _sesiones(motor) as (db_control, db_tenant):
        orden = compra_service.crear_orden_compra(
            db_tenant,
            db_control,
            OrdenCompraCrear(
                sede_id=sede_id if sede_id is not None else mundo["sede_id"],
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


def _emitir_y_facturar(motor, mundo, orden_id: int, numero: str):
    with _sesiones(motor) as (_db_control, db_tenant):
        compra_service.emitir_orden_compra(db_tenant, orden_id, _admin(mundo))
        compra_service.registrar_o_editar_factura(
            db_tenant,
            orden_id,
            FacturaCompraRegistrar(
                numero_factura=numero,
                fecha_factura=date.today(),
                monto_total=Decimal("5.00"),
            ),
            _admin(mundo),
        )


def _stock(motor, sede_id: int, producto_id: int) -> int | None:
    from sqlalchemy import select

    with sesion(motor) as db:
        return db.execute(
            select(StockSede.stock_actual).where(
                StockSede.sede_id == sede_id,
                StockSede.producto_id == producto_id,
            )
        ).scalar_one_or_none()


# ---------------------------------------------------------------------------
# Matriz, capacidad y contrato
# ---------------------------------------------------------------------------


def test_matriz_declara_las_diez_operaciones_con_sus_roles():
    """AC-13/plan §4: las 10 operaciones y sus roles exactos en la matriz."""
    for clave, roles in OPERACIONES_020.items():
        if clave not in permisos.MATRIZ_PERMISOS:
            pytest.fail(
                "capacidad ausente (T6): MATRIZ_PERMISOS no declara "
                f"{clave}; la Feature 020 la cablea en T6."
            )
        assert set(permisos.MATRIZ_PERMISOS[clave]) == roles, (
            clave,
            permisos.MATRIZ_PERMISOS[clave],
        )


def test_matriz_tiene_exactamente_72_operaciones_tras_020():
    """Plan §4/DT-13: la 020 agrega 10 filas y la matriz pasa de 62 a 72."""
    total = len(permisos.MATRIZ_PERMISOS)
    assert total == TOTAL_OPERACIONES_020, (
        f"la matriz debe tener {TOTAL_OPERACIONES_020} operaciones tras la 020; "
        f"tiene {total}"
    )


def test_capacidad_compras_asociada_a_las_diez_operaciones():
    """DT-6: las 10 operaciones se gatean solo por la capacidad `compras`."""
    for clave, esperada in CAPACIDADES_020.items():
        obtenida = capacidades.capacidad_de_operacion(*clave)
        assert obtenida == esperada, (clave, obtenida, esperada)


def test_openapi_publica_las_diez_rutas_y_72_operaciones(cliente):
    """Plan §4: las 10 rutas existen con response_model y respuestas documentadas."""
    contrato = cliente.get("/openapi.json").json()
    for metodo, ruta in OPERACIONES_020:
        operacion = contrato["paths"].get(ruta, {}).get(metodo.lower())
        if operacion is None:
            pytest.fail(
                f"capacidad ausente (T6): {metodo} {ruta} no esta publicada en "
                "/openapi.json; la Feature 020 la cablea en T6."
            )
        assert "200" in operacion["responses"] or "201" in operacion["responses"], (
            metodo,
            ruta,
        )
        assert {"401", "403"} <= set(operacion["responses"]), (metodo, ruta)

    total = sum(
        1
        for ruta, operaciones in contrato["paths"].items()
        if ruta.startswith("/api/v1/")
        for metodo in operaciones
        if metodo.lower() in {"get", "post", "put", "patch", "delete"}
    )
    assert total == TOTAL_OPERACIONES_020, (
        f"/openapi.json debe publicar {TOTAL_OPERACIONES_020} operaciones v1; "
        f"publica {total}"
    )


# ---------------------------------------------------------------------------
# AC-13: segregacion de roles y gating
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "rol,metodo,ruta,datos",
    [
        ("Bodeguero", "POST", "/api/v1/compras/ordenes", {}),
        ("Solicitante", "POST", "/api/v1/compras/ordenes", {}),
        ("Superadmin", "POST", "/api/v1/compras/ordenes", {}),
        ("Bodeguero", "POST", "/api/v1/compras/ordenes/1/emitir", None),
        ("Solicitante", "PUT", "/api/v1/compras/ordenes/1/factura", {}),
        ("Bodeguero", "GET", "/api/v1/compras/necesidades", None),
        ("Superadmin", "GET", "/api/v1/compras/necesidades", None),
        ("Solicitante", "GET", "/api/v1/compras/ordenes", None),
        ("Bodeguero", "GET", "/api/v1/compras/proveedores", None),
        ("Bodeguero", "POST", "/api/v1/compras/proveedores", {}),
    ],
)
def test_roles_no_autorizados_reciben_403(motor, mundo, rol, metodo, ruta, datos):
    """AC-13: la matriz deniega antes de validar cuerpo o resolver recursos."""
    with cliente_de_rol(motor, mundo, rol) as cliente_http:
        respuesta = cliente_http.request(metodo, ruta, json=datos)
    assert respuesta.status_code == 403, respuesta.text


def test_superadmin_no_recepciona_ni_factura(motor, mundo):
    """AC-13: el Superadmin solo lista y crea proveedores en control."""
    proveedor_id = _proveedor(motor)
    orden_id = _crear_orden_servicio(motor, mundo, proveedor_id=proveedor_id)
    _emitir_y_facturar(motor, mundo, orden_id, "FAC-SAAS-403")

    with cliente_de_rol(motor, mundo, "Superadmin") as cliente_http:
        recepcion = cliente_http.post(
            f"/api/v1/compras/ordenes/{orden_id}/recepcion"
        )
        factura = cliente_http.put(
            f"/api/v1/compras/ordenes/{orden_id}/factura",
            json={
                "numero_factura": "FAC-SAAS-403",
                "fecha_factura": date.today().isoformat(),
                "monto_total": "5.00",
            },
        )
    assert recepcion.status_code == 403, recepcion.text
    assert factura.status_code == 403, factura.text


def test_capacidad_compras_apagada_deniega_403(motor, mundo):
    """DT-6: el gating por capacidad es adicional a la matriz."""
    sembrar_contexto_capacidades(
        motor, mundo, frozenset({"compras"}), correo=CORREO_GATING
    )
    with cliente_de_rol(
        motor, mundo, "Administrador", correo=CORREO_GATING
    ) as cliente_http:
        necesidades = cliente_http.get("/api/v1/compras/necesidades")
        ordenes = cliente_http.get("/api/v1/compras/ordenes")
    assert necesidades.status_code == 403, necesidades.text
    assert ordenes.status_code == 403, ordenes.text


# ---------------------------------------------------------------------------
# AC-1/AC-2: necesidades y proveedores
# ---------------------------------------------------------------------------


def test_administrador_consulta_necesidades_y_proveedores(motor, mundo):
    """AC-1/AC-2: el Administrador lee su consolidado y el catalogo global."""
    _proveedor(motor, rut="52.000.000-2", razon_social="Proveedor visible")
    with cliente_de_rol(motor, mundo, "Administrador") as cliente_http:
        necesidades = cliente_http.get("/api/v1/compras/necesidades")
        proveedores = cliente_http.get("/api/v1/compras/proveedores")
    assert necesidades.status_code == 200, necesidades.text
    assert isinstance(necesidades.json(), list)
    assert proveedores.status_code == 200, proveedores.text
    ruts = {fila["rut"] for fila in proveedores.json()}
    assert "52.000.000-2" in ruts


def test_superadmin_lista_y_crea_proveedores_sin_replica(motor, mundo):
    """AC-2/DT-1: el Superadmin opera control y no crea replica tenant."""
    with cliente_de_rol(motor, mundo, "Superadmin") as cliente_http:
        listado = cliente_http.get("/api/v1/compras/proveedores")
        alta = cliente_http.post(
            "/api/v1/compras/proveedores",
            json={"rut": "53.000.000-3", "razon_social": "Proveedor SaaS 020"},
        )
    assert listado.status_code == 200, listado.text
    assert alta.status_code == 201, alta.text
    assert alta.json()["rut"] == "53.000.000-3"

    # En SQLite control y tenant comparten la tabla fisica `proveedor`, asi que
    # la ausencia de replica del Superadmin solo se acredita en el gated de
    # PostgreSQL 16. Aqui se verifica que el alta quedo en el catalogo global.
    with sesion(motor) as db:
        assert db.get(ProveedorControl, alta.json()["proveedor_id"]) is not None


def test_administrador_crea_proveedor_y_rut_duplicado_responde_409(motor, mundo):
    """AC-2: alta 201 y duplicado global 409."""
    with cliente_de_rol(motor, mundo, "Administrador") as cliente_http:
        primera = cliente_http.post(
            "/api/v1/compras/proveedores",
            json={"rut": "54.000.000-4", "razon_social": "Proveedor Admin 020"},
        )
        segunda = cliente_http.post(
            "/api/v1/compras/proveedores",
            json={"rut": "54.000.000-4", "razon_social": "Proveedor duplicado"},
        )
    assert primera.status_code == 201, primera.text
    assert segunda.status_code == 409, segunda.text


# ---------------------------------------------------------------------------
# AC-3…AC-5/AC-12: flujo del Administrador
# ---------------------------------------------------------------------------


def test_flujo_administrador_crear_editar_emitir_facturar_y_cancelar(motor, mundo):
    """AC-3/AC-4/AC-5/AC-12: las cinco mutaciones del Administrador por HTTP."""
    proveedor_id = _proveedor(motor, rut="55.000.000-5", razon_social="Proveedor flujo")
    segundo = crear_producto(
        motor, mundo, nombre="Producto secundario HTTP", stock_minimo=0
    )

    with cliente_de_rol(motor, mundo, "Administrador") as cliente_http:
        creada = cliente_http.post(
            "/api/v1/compras/ordenes", json=_payload_orden(mundo, proveedor_id)
        )
        assert creada.status_code == 201, creada.text
        orden_id = creada.json()["orden_compra_id"]
        assert creada.json()["estado"] == "Borrador"
        assert creada.json()["numero_oc"] is None

        editada = cliente_http.put(
            f"/api/v1/compras/ordenes/{orden_id}",
            json={
                "sede_id": mundo["sede_id"],
                "proveedor_id": proveedor_id,
                "items": [
                    {
                        "producto_id": mundo["producto_id"],
                        "cantidad_solicitada": 3,
                        "precio_unitario": "2.00",
                    },
                    {
                        "producto_id": segundo,
                        "cantidad_solicitada": 1,
                        "precio_unitario": "4.00",
                    },
                ],
            },
        )
        assert editada.status_code == 200, editada.text
        assert editada.json()["total"] == "10.00"

        emitida = cliente_http.post(
            f"/api/v1/compras/ordenes/{orden_id}/emitir"
        )
        assert emitida.status_code == 200, emitida.text
        assert emitida.json()["estado"] == "Emitida"
        assert emitida.json()["numero_oc"] == f"OC-{date.today().year:04d}-{orden_id:06d}"

        facturada = cliente_http.put(
            f"/api/v1/compras/ordenes/{orden_id}/factura",
            json={
                "numero_factura": "FAC-HTTP-020",
                "fecha_factura": date.today().isoformat(),
                "monto_total": "10.00",
                "observaciones": "Factura del flujo HTTP",
            },
        )
        assert facturada.status_code == 200, facturada.text
        assert facturada.json()["numero_factura"] == "FAC-HTTP-020"

        listado = cliente_http.get("/api/v1/compras/ordenes?estado=Facturada")
        assert listado.status_code == 200, listado.text
        assert [fila["orden_compra_id"] for fila in listado.json()] == [orden_id]

        # Una segunda OC, aun en Borrador, se cancela con motivo.
        otra = cliente_http.post(
            "/api/v1/compras/ordenes", json=_payload_orden(mundo, proveedor_id)
        )
        otra_id = otra.json()["orden_compra_id"]
        cancelada = cliente_http.post(
            f"/api/v1/compras/ordenes/{otra_id}/cancelar",
            json={"motivo_cancelacion": "Proveedor sin stock"},
        )
        assert cancelada.status_code == 200, cancelada.text
        assert cancelada.json()["estado"] == "Cancelada"
        assert cancelada.json()["motivo_cancelacion"] == "Proveedor sin stock"


def test_orden_ajena_responde_404_y_no_aparece_en_el_listado(motor, mundo):
    """AC-14: una OC de otra institucion se oculta con 404 y no se lista."""
    from tests.api._soporte_sede_011 import crear_sede

    proveedor_id = _proveedor(motor, rut="56.000.000-6", razon_social="Proveedor ajeno")
    sede_ajena = crear_sede(
        motor, institucion_id=mundo["inst_ajena"], nombre="Sede ajena 020"
    )
    admin_ajeno = identidad(
        "Administrador",
        mundo["departamento_ajeno_id"],
        mundo["usuarios_inst02"]["Administrador"],
    )
    with _sesiones(motor) as (db_control, db_tenant):
        ajena = compra_service.crear_orden_compra(
            db_tenant,
            db_control,
            OrdenCompraCrear(
                sede_id=sede_ajena,
                proveedor_id=proveedor_id,
                items=[
                    DetalleOrdenCompraCrear(
                        producto_id=mundo["producto_homonimo_ajeno_id"],
                        cantidad_solicitada=1,
                        precio_unitario=Decimal("1.00"),
                    )
                ],
            ),
            admin_ajeno,
        )
        ajena_id = ajena.orden_compra_id

    with cliente_de_rol(motor, mundo, "Administrador") as cliente_http:
        listado = cliente_http.get("/api/v1/compras/ordenes")
        cancelar = cliente_http.post(
            f"/api/v1/compras/ordenes/{ajena_id}/cancelar",
            json={"motivo_cancelacion": "No corresponde"},
        )
    assert listado.status_code == 200, listado.text
    assert ajena_id not in [fila["orden_compra_id"] for fila in listado.json()]
    assert cancelar.status_code == 404, cancelar.text


# ---------------------------------------------------------------------------
# AC-6: panel de recepciones del Bodeguero
# ---------------------------------------------------------------------------


def test_bodeguero_solo_ve_facturadas_de_su_sede(motor, mundo):
    """AC-6: el listado del Bodeguero se fuerza a Facturada + su sede."""
    from tests.api._soporte_sede_011 import crear_sede

    proveedor_id = _proveedor(motor, rut="57.000.000-7", razon_social="Proveedor sede")
    propia = _crear_orden_servicio(motor, mundo, proveedor_id=proveedor_id)
    _emitir_y_facturar(motor, mundo, propia, "FAC-BODEGA-PROPIA")

    borrador_propio = _crear_orden_servicio(
        motor, mundo, proveedor_id=proveedor_id
    )
    otra_sede = crear_sede(
        motor, institucion_id=mundo["institucion_id"], nombre="Sede secundaria 020"
    )
    facturada_ajena = _crear_orden_servicio(
        motor, mundo, proveedor_id=proveedor_id, sede_id=otra_sede
    )
    _emitir_y_facturar(motor, mundo, facturada_ajena, "FAC-BODEGA-AJENA")

    with cliente_de_rol(motor, mundo, "Bodeguero") as cliente_http:
        listado = cliente_http.get(
            "/api/v1/compras/ordenes?estado=Borrador&sede_id=999999"
        )
    assert listado.status_code == 200, listado.text
    ids = [fila["orden_compra_id"] for fila in listado.json()]
    assert ids == [propia], ids
    assert borrador_propio not in ids

    # El Bodeguero de la sede secundaria ve solo la suya.
    with cliente_de_sede(
        motor,
        "Bodeguero",
        departamento_id=mundo["departamento_id"],
        usuario_id=mundo["usuarios_inst01"]["Bodeguero"],
        sede_id=otra_sede,
    ) as cliente_http:
        listado_ajeno = cliente_http.get("/api/v1/compras/ordenes")
    assert [fila["orden_compra_id"] for fila in listado_ajeno.json()] == [
        facturada_ajena
    ]


def test_bodeguero_sin_sede_recibe_409_en_el_listado(motor, mundo):
    """AC-6/§9.7: el Bodeguero sin sede no tiene panel y recibe 409."""
    with cliente_de_sede(
        motor,
        "Bodeguero",
        departamento_id=mundo["departamento_id"],
        usuario_id=mundo["usuarios_inst01"]["Bodeguero"],
        sede_id=None,
    ) as cliente_http:
        respuesta = cliente_http.get("/api/v1/compras/ordenes")
    assert respuesta.status_code == 409, respuesta.text


def test_bodeguero_recepciona_la_facturada_de_su_sede(motor, mundo):
    """AC-7…AC-11: el endpoint de recepcion confirma e incrementa el stock."""
    proveedor_id = _proveedor(motor, rut="58.000.000-8", razon_social="Proveedor recepcion")
    fijar_stock_sede(motor, mundo, mundo["producto_id"], 10)
    orden_id = _crear_orden_servicio(
        motor, mundo, proveedor_id=proveedor_id, cantidad=2
    )
    _emitir_y_facturar(motor, mundo, orden_id, "FAC-HTTP-REC")

    with cliente_de_rol(motor, mundo, "Bodeguero") as cliente_http:
        respuesta = cliente_http.post(
            f"/api/v1/compras/ordenes/{orden_id}/recepcion"
        )
    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["estado"] == "Recibida"
    assert cuerpo["orden"]["orden_compra_id"] == orden_id
    assert len(cuerpo["movimientos"]) == 1
    assert _stock(motor, mundo["sede_id"], mundo["producto_id"]) == 12


def test_bodeguero_sin_ordenes_en_su_sede_recibe_lista_vacia(motor, mundo):
    """AC-6: un Bodeguero sin OC `Facturada` en su sede recibe `200` y `[]`."""
    from tests.api._soporte_sede_011 import crear_sede

    sede_vacia = crear_sede(
        motor, institucion_id=mundo["institucion_id"], nombre="Sede sin compras 020"
    )
    with cliente_de_sede(
        motor,
        "Bodeguero",
        departamento_id=mundo["departamento_id"],
        usuario_id=mundo["usuarios_inst01"]["Bodeguero"],
        sede_id=sede_vacia,
    ) as cliente_http:
        respuesta = cliente_http.get("/api/v1/compras/ordenes")
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json() == []


def test_bodeguero_no_recepciona_orden_de_otra_sede(motor, mundo):
    """AC-6: una OC de otra sede responde 404 aunque este Facturada."""
    from tests.api._soporte_sede_011 import crear_sede

    proveedor_id = _proveedor(motor, rut="59.000.000-9", razon_social="Proveedor otra sede")
    otra_sede = crear_sede(
        motor, institucion_id=mundo["institucion_id"], nombre="Sede recepcion 020"
    )
    orden_id = _crear_orden_servicio(
        motor, mundo, proveedor_id=proveedor_id, sede_id=otra_sede
    )
    _emitir_y_facturar(motor, mundo, orden_id, "FAC-HTTP-OTRA")

    with cliente_de_rol(motor, mundo, "Bodeguero") as cliente_http:
        respuesta = cliente_http.post(
            f"/api/v1/compras/ordenes/{orden_id}/recepcion"
        )
    assert respuesta.status_code == 404, respuesta.text
