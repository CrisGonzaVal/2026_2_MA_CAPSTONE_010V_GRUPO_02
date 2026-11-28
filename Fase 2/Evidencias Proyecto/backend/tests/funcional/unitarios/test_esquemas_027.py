"""Pruebas unitarias del contrato de entrada (Feature 027).

Verifican los DTO de alta y edicion de tickets y movimientos: limites de
longitud, rangos de identificadores, normalizacion del tipo de movimiento y
rechazo de campos extra. Son pruebas de schema, sin HTTP ni base de datos.
"""

import pytest
from pydantic import ValidationError

from app.schemas.compra_schema import (
    CancelacionOrdenCompra,
    CoberturaPreviewSolicitud,
    FacturaCompraRegistrar,
    OrdenCompraActualizar,
    OrdenCompraCrear,
    ProveedorCrear,
)
from app.schemas.control_schema import InstitucionAltaControlCrear, InstitucionEdicion
from app.schemas.inventario_schema import MovimientoCrear
from app.schemas.organizacion_schema import (
    DepartamentoCrear,
    DepartamentoEdicion,
    SedeCrear,
    SedeEdicion,
)
from app.schemas.producto_schema import (
    ProductoCrear,
    ProductoRespuesta,
    TransicionCatalogo,
)
from app.schemas.ticket_schema import (
    DetalleTicketCrear,
    TicketActualizarEstado,
    TicketCrear,
    TicketRetiro,
    TicketEditar,
    TicketMotivo,
)
from app.schemas.usuario_schema import UsuarioCrear, UsuarioRespuesta


def _campos(error: ValidationError) -> set[str]:
    """Nombres de campo reportados por Pydantic (ultimo elemento de `loc`)."""
    return {str(detalle["loc"][-1]) for detalle in error.errors()}


def _detalle(**cambios) -> dict:
    datos = {"producto_id": 1, "cantidad_solicitada": 2}
    datos.update(cambios)
    return datos


def _ticket(**cambios) -> dict:
    datos = {
        "prioridad_id": 1,
        "estado_id": 1,
        "asunto": "Solicitud de insumos",
        "descripcion": "Justificacion del pedido",
        "detalles": [_detalle()],
    }
    datos.update(cambios)
    return datos


def _ticket_editar(**cambios) -> dict:
    datos = {
        "prioridad_id": 1,
        "asunto": "Solicitud de insumos",
        "descripcion": "Justificacion del pedido",
        "detalles": [_detalle()],
    }
    datos.update(cambios)
    return datos


def _movimiento(**cambios) -> dict:
    datos = {"tipo_movimiento": "ENTRADA", "cantidad": 1, "stock_sede_id": 1}
    datos.update(cambios)
    return datos


# ---------------------------------------------------------------------------
# TicketCrear: descripcion, asunto, ids y detalles
# ---------------------------------------------------------------------------


def test_ticket_crear_acepta_descripcion_de_500_caracteres():
    ticket = TicketCrear(**_ticket(descripcion="a" * 500))

    assert len(ticket.descripcion) == 500


def test_ticket_crear_rechaza_descripcion_de_501_caracteres():
    with pytest.raises(ValidationError) as error:
        TicketCrear(**_ticket(descripcion="a" * 501))

    assert _campos(error.value) == {"descripcion"}


def test_ticket_crear_recorta_el_asunto_y_rechaza_solo_espacios():
    ticket = TicketCrear(**_ticket(asunto="  Compra de papel  "))

    assert ticket.asunto == "Compra de papel"

    with pytest.raises(ValidationError) as error:
        TicketCrear(**_ticket(asunto="   "))

    assert _campos(error.value) == {"asunto"}


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("prioridad_id", 0),
        ("estado_id", 0),
    ],
)
def test_ticket_crear_rechaza_identificadores_no_positivos(campo, valor):
    with pytest.raises(ValidationError) as error:
        TicketCrear(**_ticket(**{campo: valor}))

    assert _campos(error.value) == {campo}


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("producto_id", 0),
        ("cantidad_solicitada", 0),
        ("cantidad_solicitada", -1),
    ],
)
def test_detalle_ticket_rechaza_identificadores_y_cantidades_invalidas(campo, valor):
    with pytest.raises(ValidationError) as error:
        DetalleTicketCrear(**_detalle(**{campo: valor}))

    assert _campos(error.value) == {campo}


def test_ticket_crear_rechaza_lista_de_detalles_vacia():
    with pytest.raises(ValidationError) as error:
        TicketCrear(**_ticket(detalles=[]))

    assert _campos(error.value) == {"detalles"}


def test_ticket_crear_rechaza_campos_extra():
    with pytest.raises(ValidationError) as error:
        TicketCrear(**_ticket(campo_extra=1))

    assert _campos(error.value) == {"campo_extra"}
    assert error.value.errors()[0]["type"] == "extra_forbidden"


def test_detalle_ticket_rechaza_campos_extra():
    with pytest.raises(ValidationError) as error:
        TicketCrear(**_ticket(detalles=[_detalle(campo_extra=1)]))

    assert _campos(error.value) == {"campo_extra"}
    assert error.value.errors()[0]["type"] == "extra_forbidden"


def test_ticket_crear_sigue_aceptando_e_ignorando_usuario_id():
    """Compatibilidad 003/008: el autor lo fija el servidor."""
    ticket = TicketCrear(**_ticket(usuario_id=999))

    assert ticket.usuario_id == 999


# ---------------------------------------------------------------------------
# TicketEditar, TicketActualizarEstado y TicketRetiro
# ---------------------------------------------------------------------------


def test_ticket_editar_acepta_descripcion_de_500_y_rechaza_501():
    assert TicketEditar(**_ticket_editar(descripcion="a" * 500))

    with pytest.raises(ValidationError) as error:
        TicketEditar(**_ticket_editar(descripcion="a" * 501))

    assert _campos(error.value) == {"descripcion"}


def test_ticket_editar_rechaza_campos_extra_y_detalles_vacios():
    with pytest.raises(ValidationError) as error:
        TicketEditar(**_ticket_editar(campo_extra=1))

    assert _campos(error.value) == {"campo_extra"}

    with pytest.raises(ValidationError) as error:
        TicketEditar(**_ticket_editar(detalles=[]))

    assert _campos(error.value) == {"detalles"}


def test_ticket_editar_rechaza_prioridad_no_positiva():
    with pytest.raises(ValidationError) as error:
        TicketEditar(**_ticket_editar(prioridad_id=0))

    assert _campos(error.value) == {"prioridad_id"}


def test_actualizar_estado_rechaza_id_no_positivo_y_campos_extra():
    with pytest.raises(ValidationError) as error:
        TicketActualizarEstado(estado_id=0)

    assert _campos(error.value) == {"estado_id"}

    with pytest.raises(ValidationError) as error:
        TicketActualizarEstado(estado_id=1, campo_extra=1)

    assert _campos(error.value) == {"campo_extra"}


def test_retiro_rechaza_usuario_no_positivo_y_campos_extra():
    with pytest.raises(ValidationError) as error:
        TicketRetiro(usuario_id=0)

    assert _campos(error.value) == {"usuario_id"}

    with pytest.raises(ValidationError) as error:
        TicketRetiro(usuario_id=1, campo_extra=1)

    assert _campos(error.value) == {"campo_extra"}


def test_ticket_motivo_conserva_la_validacion_del_servicio():
    """La precedencia 404 -> 409 -> 422 exige que el schema no rechace."""
    assert TicketMotivo(motivo="").motivo == ""
    assert len(TicketMotivo(motivo="a" * 501).motivo) == 501


# ---------------------------------------------------------------------------
# MovimientoCrear
# ---------------------------------------------------------------------------


def test_movimiento_normaliza_el_tipo_a_mayusculas():
    assert MovimientoCrear(**_movimiento(tipo_movimiento="entrada")).tipo_movimiento == (
        "ENTRADA"
    )
    assert MovimientoCrear(**_movimiento(tipo_movimiento="Salida")).tipo_movimiento == (
        "SALIDA"
    )


@pytest.mark.parametrize("tipo", ["AJUSTE", "", None, 123])
def test_movimiento_rechaza_tipo_invalido(tipo):
    with pytest.raises(ValidationError) as error:
        MovimientoCrear(**_movimiento(tipo_movimiento=tipo))

    assert _campos(error.value) == {"tipo_movimiento"}


@pytest.mark.parametrize("cantidad", [0, -1])
def test_movimiento_rechaza_cantidad_no_positiva(cantidad):
    with pytest.raises(ValidationError) as error:
        MovimientoCrear(**_movimiento(cantidad=cantidad))

    assert _campos(error.value) == {"cantidad"}


def test_movimiento_acepta_observacion_de_250_y_rechaza_251():
    assert MovimientoCrear(**_movimiento(observacion="a" * 250))

    with pytest.raises(ValidationError) as error:
        MovimientoCrear(**_movimiento(observacion="a" * 251))

    assert _campos(error.value) == {"observacion"}


def test_movimiento_rechaza_stock_sede_no_positivo_y_campos_extra():
    with pytest.raises(ValidationError) as error:
        MovimientoCrear(**_movimiento(stock_sede_id=0))

    assert _campos(error.value) == {"stock_sede_id"}

    with pytest.raises(ValidationError) as error:
        MovimientoCrear(**_movimiento(campo_extra=1))

    assert _campos(error.value) == {"campo_extra"}


# ---------------------------------------------------------------------------
# ProductoCrear y ProductoRespuesta
# ---------------------------------------------------------------------------


def _producto(**cambios) -> dict:
    datos = {"nombre": "Papel bond", "categoria_id": 1}
    datos.update(cambios)
    return datos


def test_producto_crear_recorta_el_nombre_y_rechaza_solo_espacios():
    producto = ProductoCrear(**_producto(nombre="  Papel bond  "))

    assert producto.nombre == "Papel bond"

    with pytest.raises(ValidationError) as error:
        ProductoCrear(**_producto(nombre="   "))

    assert _campos(error.value) == {"nombre"}


def test_producto_crear_acepta_nombre_de_150_y_rechaza_151():
    assert ProductoCrear(**_producto(nombre="a" * 150))

    with pytest.raises(ValidationError) as error:
        ProductoCrear(**_producto(nombre="a" * 151))

    assert _campos(error.value) == {"nombre"}


def test_producto_crear_acepta_descripcion_de_250_y_rechaza_251():
    assert ProductoCrear(**_producto(descripcion="a" * 250))

    with pytest.raises(ValidationError) as error:
        ProductoCrear(**_producto(descripcion="a" * 251))

    assert _campos(error.value) == {"descripcion"}


def test_producto_crear_acepta_unidad_de_30_y_rechaza_31():
    assert ProductoCrear(**_producto(unidad_medida="a" * 30))

    with pytest.raises(ValidationError) as error:
        ProductoCrear(**_producto(unidad_medida="a" * 31))

    assert _campos(error.value) == {"unidad_medida"}


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("stock_minimo", -1),
        ("categoria_id", 0),
    ],
)
def test_producto_crear_rechaza_rangos_invalidos(campo, valor):
    with pytest.raises(ValidationError) as error:
        ProductoCrear(**_producto(**{campo: valor}))

    assert _campos(error.value) == {campo}


def test_producto_crear_rechaza_campos_extra():
    with pytest.raises(ValidationError) as error:
        ProductoCrear(**_producto(campo_extra=1))

    assert _campos(error.value) == {"campo_extra"}
    assert error.value.errors()[0]["type"] == "extra_forbidden"


def test_producto_respuesta_no_hereda_extra_forbid():
    """La configuracion de alta no debe filtrarse a la serializacion."""
    respuesta = ProductoRespuesta.model_validate(
        {
            "producto_id": 1,
            "nombre": "Papel bond",
            "categoria_id": 1,
            "campo_extra": "ignorado",
        }
    )

    assert respuesta.producto_id == 1


# ---------------------------------------------------------------------------
# UsuarioCrear y UsuarioRespuesta
# ---------------------------------------------------------------------------


def _usuario(**cambios) -> dict:
    datos = {
        "nombre": "Ana",
        "apellido": "Perez",
        "correo": "ana.perez@ejemplo.cl",
        "departamento_id": 1,
        "rol_id": 1,
    }
    datos.update(cambios)
    return datos


def test_usuario_crear_recorta_nombres_y_rechaza_solo_espacios():
    usuario = UsuarioCrear(**_usuario(nombre="  Ana  ", apellido="  Perez  "))

    assert (usuario.nombre, usuario.apellido) == ("Ana", "Perez")

    with pytest.raises(ValidationError) as error:
        UsuarioCrear(**_usuario(nombre="   "))

    assert _campos(error.value) == {"nombre"}

    with pytest.raises(ValidationError) as error:
        UsuarioCrear(**_usuario(apellido="   "))

    assert _campos(error.value) == {"apellido"}


def test_usuario_crear_acepta_nombres_de_100_y_rechaza_101():
    assert UsuarioCrear(**_usuario(nombre="a" * 100, apellido="b" * 100))

    with pytest.raises(ValidationError) as error:
        UsuarioCrear(**_usuario(nombre="a" * 101))

    assert _campos(error.value) == {"nombre"}

    with pytest.raises(ValidationError) as error:
        UsuarioCrear(**_usuario(apellido="b" * 101))

    assert _campos(error.value) == {"apellido"}


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("departamento_id", 0),
        ("rol_id", 0),
    ],
)
def test_usuario_crear_rechaza_identificadores_no_positivos(campo, valor):
    with pytest.raises(ValidationError) as error:
        UsuarioCrear(**_usuario(**{campo: valor}))

    assert _campos(error.value) == {campo}


def test_usuario_crear_rechaza_correo_invalido():
    with pytest.raises(ValidationError) as error:
        UsuarioCrear(**_usuario(correo="ana-sin-arroba"))

    assert _campos(error.value) == {"correo"}


def test_usuario_crear_rechaza_campos_extra():
    with pytest.raises(ValidationError) as error:
        UsuarioCrear(**_usuario(campo_extra=1))

    assert _campos(error.value) == {"campo_extra"}
    assert error.value.errors()[0]["type"] == "extra_forbidden"


def test_usuario_respuesta_no_hereda_extra_forbid():
    """La configuracion de alta no debe filtrarse a la serializacion."""
    respuesta = UsuarioRespuesta.model_validate(
        {
            "usuario_id": 1,
            **_usuario(),
            "campo_extra": "ignorado",
        }
    )

    assert respuesta.usuario_id == 1


# ---------------------------------------------------------------------------
# ProveedorCrear: RUT con DV y razon social
# ---------------------------------------------------------------------------


def _proveedor(**cambios) -> dict:
    datos = {"rut": "76.543.210-3", "razon_social": "Papelera del Pacifico"}
    datos.update(cambios)
    return datos


@pytest.mark.parametrize(
    ("rut", "visible"),
    [
        ("76.543.210-3", "76.543.210-3"),
        ("76543210-3", "76543210-3"),
        ("765432103", "765432103"),
        (" 76.543.210-3 ", "76.543.210-3"),
        ("19.191.919-k", "19.191.919-K"),
    ],
)
def test_proveedor_acepta_rut_valido_en_sus_formas(rut, visible):
    proveedor = ProveedorCrear(**_proveedor(rut=rut))

    assert proveedor.rut == visible


@pytest.mark.parametrize(
    "rut",
    [
        "76.543.210-8",
        "77.654.321-K",
        "99-9",
        "0-0",
        "123456789-0",
        "abc-1",
        "a" * 21,
    ],
)
def test_proveedor_rechaza_rut_invalido(rut):
    with pytest.raises(ValidationError) as error:
        ProveedorCrear(**_proveedor(rut=rut))

    assert _campos(error.value) == {"rut"}


def test_proveedor_recorta_la_razon_social_y_rechaza_solo_espacios():
    proveedor = ProveedorCrear(**_proveedor(razon_social="  Papelera  "))

    assert proveedor.razon_social == "Papelera"

    with pytest.raises(ValidationError) as error:
        ProveedorCrear(**_proveedor(razon_social="   "))

    assert _campos(error.value) == {"razon_social"}


def test_proveedor_acepta_razon_social_de_150_y_rechaza_151():
    assert ProveedorCrear(**_proveedor(razon_social="a" * 150))

    with pytest.raises(ValidationError) as error:
        ProveedorCrear(**_proveedor(razon_social="a" * 151))

    assert _campos(error.value) == {"razon_social"}


def test_proveedor_rechaza_correo_invalido_y_campos_extra():
    with pytest.raises(ValidationError) as error:
        ProveedorCrear(**_proveedor(correo="no-es-correo"))

    assert _campos(error.value) == {"correo"}

    with pytest.raises(ValidationError) as error:
        ProveedorCrear(**_proveedor(campo_extra=1))

    assert _campos(error.value) == {"campo_extra"}


# ---------------------------------------------------------------------------
# InstitucionAltaControlCrear e InstitucionEdicion
# ---------------------------------------------------------------------------


def _institucion(**cambios) -> dict:
    datos = {
        "institucion_id": "INST-T027",
        "nombre": "Institucion de prueba",
        "rut": "76.543.210-3",
        "correo_administrador": "admin@ejemplo.cl",
        "nombre_administrador": "Ada",
        "apellido_administrador": "Administradora",
        "departamento_nombre_administrativo": "Administracion",
    }
    datos.update(cambios)
    return datos


@pytest.mark.parametrize(
    ("rut", "esperado"),
    [
        ("76.543.210-3", "76.543.210-3"),
        ("765432103", "765432103"),
        (None, None),
        ("", None),
        ("   ", None),
    ],
)
def test_institucion_alta_acepta_rut_valido_u_omitido(rut, esperado):
    institucion = InstitucionAltaControlCrear(**_institucion(rut=rut))

    assert institucion.rut == esperado


@pytest.mark.parametrize("rut", ["76.543.210-8", "99-9", "0-0", "abc-1", "a" * 21])
def test_institucion_alta_rechaza_rut_invalido(rut):
    with pytest.raises(ValidationError) as error:
        InstitucionAltaControlCrear(**_institucion(rut=rut))

    assert _campos(error.value) == {"rut"}


def test_institucion_alta_rechaza_correo_invalido():
    with pytest.raises(ValidationError) as error:
        InstitucionAltaControlCrear(**_institucion(correo_administrador="sin-arroba"))

    assert _campos(error.value) == {"correo_administrador"}


def test_institucion_alta_recorta_nombres_y_rechaza_solo_espacios():
    institucion = InstitucionAltaControlCrear(
        **_institucion(
            nombre="  Institucion  ",
            nombre_administrador="  Ada  ",
            apellido_administrador="  Lovelace  ",
            departamento_nombre_administrativo="  Administracion  ",
        )
    )

    assert institucion.nombre == "Institucion"
    assert institucion.nombre_administrador == "Ada"
    assert institucion.apellido_administrador == "Lovelace"
    assert institucion.departamento_nombre_administrativo == "Administracion"

    with pytest.raises(ValidationError) as error:
        InstitucionAltaControlCrear(**_institucion(nombre="   "))

    assert _campos(error.value) == {"nombre"}


def test_institucion_alta_rechaza_campos_extra():
    with pytest.raises(ValidationError) as error:
        InstitucionAltaControlCrear(**_institucion(campo_extra=1))

    assert _campos(error.value) == {"campo_extra"}


@pytest.mark.parametrize(
    ("rut", "esperado"),
    [
        ("76.543.210-3", "76.543.210-3"),
        (None, None),
        ("", None),
        ("   ", None),
    ],
)
def test_institucion_edicion_acepta_rut_valido_u_omitido(rut, esperado):
    institucion = InstitucionEdicion(nombre="Institucion", rut=rut)

    assert institucion.rut == esperado


def test_institucion_edicion_rechaza_rut_invalido_y_campos_extra():
    with pytest.raises(ValidationError) as error:
        InstitucionEdicion(nombre="Institucion", rut="76.543.210-8")

    assert _campos(error.value) == {"rut"}

    with pytest.raises(ValidationError) as error:
        InstitucionEdicion(nombre="Institucion", campo_extra=1)

    assert _campos(error.value) == {"campo_extra"}


def test_institucion_edicion_recorta_el_nombre_y_rechaza_solo_espacios():
    assert InstitucionEdicion(nombre="  Institucion  ").nombre == "Institucion"

    with pytest.raises(ValidationError) as error:
        InstitucionEdicion(nombre="   ")

    assert _campos(error.value) == {"nombre"}


# ---------------------------------------------------------------------------
# Orden de compra, factura, cancelacion y cobertura
# ---------------------------------------------------------------------------


def test_orden_compra_rechaza_campos_extra_en_el_padre_y_en_el_detalle():
    with pytest.raises(ValidationError) as error:
        OrdenCompraCrear(
            sede_id=1,
            proveedor_id=1,
            items=[{"producto_id": 1, "cantidad_solicitada": 1}],
            campo_extra=1,
        )

    assert _campos(error.value) == {"campo_extra"}

    with pytest.raises(ValidationError) as error:
        OrdenCompraCrear(
            sede_id=1,
            proveedor_id=1,
            items=[
                {"producto_id": 1, "cantidad_solicitada": 1, "campo_extra": 1}
            ],
        )

    assert _campos(error.value) == {"campo_extra"}


def test_orden_compra_actualizar_rechaza_campos_extra():
    with pytest.raises(ValidationError) as error:
        OrdenCompraActualizar(
            sede_id=1,
            proveedor_id=1,
            items=[{"producto_id": 1, "cantidad_solicitada": 1}],
            campo_extra=1,
        )

    assert _campos(error.value) == {"campo_extra"}


def test_factura_recorta_numero_y_rechaza_solo_espacios_o_51():
    factura = FacturaCompraRegistrar(
        numero_factura="  F-2026-001  ",
        fecha_factura="2026-01-01",
        monto_total="10.00",
    )

    assert factura.numero_factura == "F-2026-001"

    with pytest.raises(ValidationError) as error:
        FacturaCompraRegistrar(
            numero_factura="   ",
            fecha_factura="2026-01-01",
            monto_total="10.00",
        )

    assert _campos(error.value) == {"numero_factura"}

    with pytest.raises(ValidationError) as error:
        FacturaCompraRegistrar(
            numero_factura="a" * 51,
            fecha_factura="2026-01-01",
            monto_total="10.00",
        )

    assert _campos(error.value) == {"numero_factura"}


def test_factura_acepta_observaciones_de_500_y_rechaza_501():
    datos = {
        "numero_factura": "F-1",
        "fecha_factura": "2026-01-01",
        "monto_total": "10.00",
    }

    assert FacturaCompraRegistrar(**datos, observaciones="a" * 500)

    with pytest.raises(ValidationError) as error:
        FacturaCompraRegistrar(**datos, observaciones="a" * 501)

    assert _campos(error.value) == {"observaciones"}


def test_factura_rechaza_campos_extra():
    with pytest.raises(ValidationError) as error:
        FacturaCompraRegistrar(
            numero_factura="F-1",
            fecha_factura="2026-01-01",
            monto_total="10.00",
            campo_extra=1,
        )

    assert _campos(error.value) == {"campo_extra"}


def test_cancelacion_recorta_motivo_y_rechaza_solo_espacios_o_501():
    assert CancelacionOrdenCompra(motivo_cancelacion="  ya no se necesita  ").motivo_cancelacion == (
        "ya no se necesita"
    )

    with pytest.raises(ValidationError) as error:
        CancelacionOrdenCompra(motivo_cancelacion="   ")

    assert _campos(error.value) == {"motivo_cancelacion"}

    with pytest.raises(ValidationError) as error:
        CancelacionOrdenCompra(motivo_cancelacion="a" * 501)

    assert _campos(error.value) == {"motivo_cancelacion"}


def test_cancelacion_rechaza_campos_extra():
    with pytest.raises(ValidationError) as error:
        CancelacionOrdenCompra(motivo_cancelacion="motivo", campo_extra=1)

    assert _campos(error.value) == {"campo_extra"}


def test_cobertura_rechaza_campos_extra_en_solicitud_e_item():
    with pytest.raises(ValidationError) as error:
        CoberturaPreviewSolicitud(
            sede_id=1,
            items=[{"producto_id": 1, "cantidad_solicitada": 1}],
            campo_extra=1,
        )

    assert _campos(error.value) == {"campo_extra"}

    with pytest.raises(ValidationError) as error:
        CoberturaPreviewSolicitud(
            sede_id=1,
            items=[
                {"producto_id": 1, "cantidad_solicitada": 1, "campo_extra": 1}
            ],
        )

    assert _campos(error.value) == {"campo_extra"}


# ---------------------------------------------------------------------------
# Organizacion: sede y departamento
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("modelo", [SedeCrear, SedeEdicion])
def test_sede_recorta_nombre_y_rechaza_solo_espacios(modelo):
    assert modelo(nombre="  Sede Centro  ").nombre == "Sede Centro"

    with pytest.raises(ValidationError) as error:
        modelo(nombre="   ")

    assert _campos(error.value) == {"nombre"}


@pytest.mark.parametrize("modelo", [SedeCrear, SedeEdicion])
def test_sede_acepta_nombre_de_100_y_rechaza_101(modelo):
    assert modelo(nombre="a" * 100)

    with pytest.raises(ValidationError) as error:
        modelo(nombre="a" * 101)

    assert _campos(error.value) == {"nombre"}


@pytest.mark.parametrize("modelo", [DepartamentoCrear, DepartamentoEdicion])
def test_departamento_recorta_nombre_y_rechaza_solo_espacios(modelo):
    assert modelo(nombre_dep="  Compras  ").nombre_dep == "Compras"

    with pytest.raises(ValidationError) as error:
        modelo(nombre_dep="   ")

    assert _campos(error.value) == {"nombre_dep"}


@pytest.mark.parametrize("modelo", [DepartamentoCrear, DepartamentoEdicion])
def test_departamento_acepta_nombre_de_100_y_rechaza_101(modelo):
    assert modelo(nombre_dep="a" * 100)

    with pytest.raises(ValidationError) as error:
        modelo(nombre_dep="a" * 101)

    assert _campos(error.value) == {"nombre_dep"}


# ---------------------------------------------------------------------------
# TransicionCatalogo
# ---------------------------------------------------------------------------


def test_transicion_catalogo_prohibe_campos_extra_sin_limitar_el_motivo():
    with pytest.raises(ValidationError) as error:
        TransicionCatalogo(activo=False, campo_extra=1)

    assert _campos(error.value) == {"campo_extra"}

    assert TransicionCatalogo(activo=False, motivo="").motivo == ""
    assert len(TransicionCatalogo(activo=False, motivo="a" * 501).motivo) == 501

