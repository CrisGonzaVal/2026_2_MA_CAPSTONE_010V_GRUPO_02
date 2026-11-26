"""Feature 027, T11: validacion de entradas en la superficie HTTP real."""

import pytest

from tests.funcional.integracion._soporte_sede_011 import (
    asegurar_sede_de_departamento,
)


@pytest.fixture(autouse=True)
def sede_base(motor, datos_base):
    return asegurar_sede_de_departamento(
        motor, datos_base, stocks={datos_base["producto_id"]: 50}
    )


def _ticket(datos_base, **cambios):
    datos = {
        "usuario_id": datos_base["usuario_id"],
        "prioridad_id": datos_base["prioridad_id"],
        "estado_id": datos_base["estado_ingresado_id"],
        "asunto": "Pedido de validacion",
        "descripcion": "Descripcion valida.",
        "detalles": [
            {
                "producto_id": datos_base["producto_id"],
                "cantidad_solicitada": 1,
            }
        ],
    }
    datos.update(cambios)
    return datos


def _producto(datos_base, **cambios):
    datos = {
        "nombre": "Producto de validacion",
        "descripcion": "Descripcion",
        "unidad_medida": "UNIDAD",
        "stock_minimo": 0,
        "categoria_id": datos_base["categoria_id"],
    }
    datos.update(cambios)
    return datos


def _usuario(datos_base, **cambios):
    datos = {
        "nombre": "Ana",
        "apellido": "Validacion",
        "correo": "ana.validacion@compustock.cl",
        "departamento_id": datos_base["departamento_id"],
        "rol_id": datos_base["rol_bodeguero_id"],
    }
    datos.update(cambios)
    return datos


def test_ticket_acepta_500_y_rechaza_501_sin_500(
    cliente_solicitante, datos_base
):
    aceptado = cliente_solicitante.post(
        "/api/v1/tickets/", json=_ticket(datos_base, descripcion="a" * 500)
    )
    assert aceptado.status_code == 201, aceptado.text

    rechazado = cliente_solicitante.post(
        "/api/v1/tickets/", json=_ticket(datos_base, descripcion="a" * 501)
    )
    assert rechazado.status_code == 422, rechazado.text
    detalle = rechazado.json()["detail"][0]
    assert detalle["loc"] == ["body", "descripcion"]
    assert detalle["type"] == "string_too_long"


def test_ticket_rechaza_campo_extra_y_asunto_de_solo_espacios(
    cliente_solicitante, datos_base
):
    extra = cliente_solicitante.post(
        "/api/v1/tickets/", json=_ticket(datos_base, campo_extra=1)
    )
    assert extra.status_code == 422
    assert extra.json()["detail"][0]["type"] == "extra_forbidden"

    espacios = cliente_solicitante.post(
        "/api/v1/tickets/", json=_ticket(datos_base, asunto="   ")
    )
    assert espacios.status_code == 422
    assert espacios.json()["detail"][0]["loc"] == ["body", "asunto"]


def test_producto_acepta_limites_y_rechaza_excesos_sin_500(cliente, datos_base):
    aceptado = cliente.post(
        "/api/v1/inventario/productos",
        json=_producto(
            datos_base,
            nombre="a" * 150,
            descripcion="b" * 250,
            unidad_medida="c" * 30,
            stock_minimo=0,
        ),
    )
    assert aceptado.status_code == 201, aceptado.text
    assert aceptado.json()["nombre"] == "a" * 150

    for cambios in (
        {"nombre": "a" * 151},
        {"descripcion": "b" * 251},
        {"unidad_medida": "c" * 31},
        {"stock_minimo": -1},
        {"categoria_id": 0},
    ):
        rechazado = cliente.post(
            "/api/v1/inventario/productos",
            json=_producto(datos_base, **cambios),
        )
        assert rechazado.status_code == 422, (cambios, rechazado.text)


def test_movimiento_acepta_entrada_en_minusculas_y_rechaza_invalidos(
    cliente, datos_base, sede_base
):
    stock_sede_id = sede_base["stock_sede_ids"][datos_base["producto_id"]]
    valido = cliente.post(
        "/api/v1/inventario/movimientos",
        json={
            "tipo_movimiento": "entrada",
            "cantidad": 1,
            "observacion": "o" * 250,
            "stock_sede_id": stock_sede_id,
        },
    )
    assert valido.status_code == 201, valido.text

    for cambios in (
        {"cantidad": 0},
        {"cantidad": -1},
        {"observacion": "o" * 251},
        {"tipo_movimiento": "AJUSTE"},
        {"stock_sede_id": 0},
        {"campo_extra": 1},
    ):
        datos = {
            "tipo_movimiento": "ENTRADA",
            "cantidad": 1,
            "observacion": "valida",
            "stock_sede_id": stock_sede_id,
            **cambios,
        }
        rechazado = cliente.post(
            "/api/v1/inventario/movimientos", json=datos
        )
        assert rechazado.status_code == 422, (cambios, rechazado.text)


def test_usuario_acepta_limites_y_rechaza_invalidos(cliente, datos_base):
    aceptado = cliente.post(
        "/api/v1/usuarios/",
        json=_usuario(datos_base, nombre="a" * 100, apellido="b" * 100),
    )
    assert aceptado.status_code == 201, aceptado.text

    for cambios in (
        {"correo": "dos@compustock.cl", "nombre": "a" * 101},
        {"correo": "tres@compustock.cl", "departamento_id": 0},
        {"correo": "cuatro@compustock.cl", "rol_id": 0},
        {"correo": "cinco@compustock.cl", "nombre": "   "},
        {"correo": "seis@compustock.cl", "campo_extra": 1},
    ):
        rechazado = cliente.post(
            "/api/v1/usuarios/", json=_usuario(datos_base, **cambios)
        )
        assert rechazado.status_code == 422, (cambios, rechazado.text)


@pytest.mark.parametrize(
    "rut",
    ["76.543.210-3", "76543210-3", "765432103", "19.191.919-k"],
)
def test_proveedor_acepta_rut_valido_en_cualquier_forma(cliente, rut):
    respuesta = cliente.post(
        "/api/v1/compras/proveedores",
        json={"rut": rut, "razon_social": f"Proveedor {rut}"},
    )
    assert respuesta.status_code == 201, respuesta.text
    assert respuesta.json()["rut"] == rut.strip().upper()


def test_proveedor_rechaza_dv_invalido_y_duplicado_normalizado_responde_409(
    cliente,
):
    invalido = cliente.post(
        "/api/v1/compras/proveedores",
        json={"rut": "76.543.210-8", "razon_social": "Proveedor invalido"},
    )
    assert invalido.status_code == 422
    assert invalido.json()["detail"][0]["loc"] == ["body", "rut"]

    primero = cliente.post(
        "/api/v1/compras/proveedores",
        json={"rut": "77.777.777-7", "razon_social": "Proveedor primero"},
    )
    assert primero.status_code == 201, primero.text

    duplicado = cliente.post(
        "/api/v1/compras/proveedores",
        json={"rut": "77777777-7", "razon_social": "Proveedor duplicado"},
    )
    assert duplicado.status_code == 409, duplicado.text
