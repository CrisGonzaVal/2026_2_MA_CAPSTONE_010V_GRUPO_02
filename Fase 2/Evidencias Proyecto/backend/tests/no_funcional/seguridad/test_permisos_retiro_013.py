"""Enmienda 26/Nov/2026 de la 013: matriz, OpenAPI y roles del retiro (AC-64).

Fase ROJA de TDD (T32). Se transcribe la matriz desde la spec §10.5/§10.10, no
desde `permisos.MATRIZ_PERMISOS` como fuente de la expectativa:

* la matriz conserva **72** operaciones (75 menos las tres que retira la
  enmienda 27/Nov/2026 de la 012 con la tabla puente auxiliar);
* `POST /tickets/{id}/retiro` existe con **solo `Bodeguero`** (capacidad
  `kanban`) y `/despacho` ya no esta;
* `POST /inventario/movimientos` queda **solo** para el Bodeguero;
* `POST /anulacion` conserva `{Administrador, Solicitante}` y `PATCH /estado`
  conserva `{Administrador}`;
* `/openapi.json` publica 72 operaciones v1 (74 entradas) con `/retiro` y sin
  `/despacho`.
"""

from __future__ import annotations

from app.core import capacidades, permisos

from tests.funcional.integracion._soporte_retiro_013 import (
    cliente_rol,
    crear_producto_con_stock,
    sembrar_mundo_retiro,
    stock_de,
)

RUTA_RETIRO = "/api/v1/tickets/{ticket_id}/retiro"
RUTA_DESPACHO = "/api/v1/tickets/{ticket_id}/despacho"
RUTA_ANULACION = "/api/v1/tickets/{ticket_id}/anulacion"
RUTA_RECHAZO = "/api/v1/tickets/{ticket_id}/rechazo"
RUTA_ESTADO = "/api/v1/tickets/{ticket_id}/estado"
RUTA_MOVIMIENTOS = "/api/v1/inventario/movimientos"

_METODOS = {"get", "post", "put", "patch", "delete"}


def _operaciones(esquema: dict):
    for ruta, metodos in esquema["paths"].items():
        for metodo in metodos:
            if metodo.lower() in _METODOS:
                yield ruta, metodo.lower()


# ---------------------------------------------------------------------------
# Matriz central
# ---------------------------------------------------------------------------


def test_la_matriz_conserva_72_operaciones_ac_64():
    """AC-64: una clave renombrada y dos conjuntos ajustados, no una fila nueva.

    Enmienda 27/Nov/2026 de la 012: la matriz pasa de 75 a 72 al retirar las tres
    operaciones de la tabla puente auxiliar.
    """
    assert len(permisos.MATRIZ_PERMISOS) == 72, (
        "la enmienda de la 013 conserva sus filas y la de la 012 deja 72 "
        "operaciones (D-29/AC-64)"
    )


def test_la_matriz_declara_retiro_solo_para_el_bodeguero_ac_64():
    """AC-64/D-30: `/retiro` existe con `{Bodeguero}`."""
    clave = ("POST", RUTA_RETIRO)
    assert clave in permisos.MATRIZ_PERMISOS, (
        "MATRIZ_PERMISOS no declara POST /tickets/{ticket_id}/retiro; "
        "la enmienda la cablea en T35"
    )
    assert permisos.MATRIZ_PERMISOS[clave] == frozenset({"Bodeguero"})


def test_la_matriz_ya_no_declara_despacho_ac_64():
    """AC-55/AC-64: `/despacho` desaparece de la matriz."""
    assert ("POST", RUTA_DESPACHO) not in permisos.MATRIZ_PERMISOS


def test_los_movimientos_manuales_son_solo_del_bodeguero_ac_64(
    motor, dos_instituciones
):
    """AC-64/D-31: el Administrador deja de escribir movimientos manuales.

    Doble verificacion: la matriz declara `{Bodeguero}` y la interfaz HTTP
    responde 403 a Administrador, Solicitante y Superadmin **sin mutar** el
    saldo; el Bodeguero de la sede obtiene 201.
    """
    clave = ("POST", RUTA_MOVIMIENTOS)
    assert clave in permisos.MATRIZ_PERMISOS
    assert permisos.MATRIZ_PERMISOS[clave] == frozenset({"Bodeguero"}), (
        "POST /inventario/movimientos debe quedar solo para el Bodeguero"
    )

    datos = sembrar_mundo_retiro(motor, dos_instituciones)
    producto = crear_producto_con_stock(
        motor, datos, nombre="Movimiento manual 064", stock_actual=10
    )
    cuerpo = {
        "tipo_movimiento": "ENTRADA",
        "cantidad": 5,
        "observacion": "Reposicion de bodega",
        "stock_sede_id": producto["stock_sede_id"],
    }

    for rol in ("Administrador", "Solicitante", "Superadmin"):
        with cliente_rol(motor, datos, rol) as cliente:
            respuesta = cliente.post(RUTA_MOVIMIENTOS, json=cuerpo)
        assert respuesta.status_code == 403, (rol, respuesta.text)
        assert stock_de(motor, datos["sede_id"], producto["producto_id"]) == 10, (
            f"un 403 de {rol} no puede mutar el saldo"
        )

    with cliente_rol(motor, datos, "Bodeguero") as cliente:
        respuesta = cliente.post(RUTA_MOVIMIENTOS, json=cuerpo)

    assert respuesta.status_code == 201, respuesta.text
    assert stock_de(motor, datos["sede_id"], producto["producto_id"]) == 15


def test_anulacion_rechazo_y_patch_conservan_sus_roles_ac_64():
    """AC-64: las otras entradas de la matriz no cambian."""
    assert permisos.MATRIZ_PERMISOS[("POST", RUTA_ANULACION)] == frozenset(
        {"Administrador", "Solicitante"}
    )
    assert permisos.MATRIZ_PERMISOS[("POST", RUTA_RECHAZO)] == frozenset(
        {"Administrador", "Bodeguero"}
    )
    assert permisos.MATRIZ_PERMISOS[("PATCH", RUTA_ESTADO)] == frozenset(
        {"Administrador"}
    )


def test_la_capacidad_del_retiro_es_kanban_ac_64():
    """AC-64: el retiro se gatea con `kanban`, sin capacidad nueva."""
    assert capacidades.capacidad_de_operacion("POST", RUTA_RETIRO) == "kanban"
    assert capacidades.capacidad_de_operacion("POST", RUTA_DESPACHO) is None


# ---------------------------------------------------------------------------
# OpenAPI
# ---------------------------------------------------------------------------


def test_openapi_publica_72_operaciones_v1_y_74_entradas_ac_64(cliente):
    """AC-64: el contrato queda en 72 v1 + `GET /` y `/health` = 74.

    Ademas fija las descripciones vigentes de la enmienda: el registro manual de
    movimientos es una operacion de bodega (403 del Administrador) y la
    anulacion documenta la devolucion de stock y el 409 de una entrega ya
    confirmada (D-32/D-34).
    """
    esquema = cliente.get("/openapi.json").json()
    operaciones = list(_operaciones(esquema))

    assert len(operaciones) == 74
    v1 = [ruta for ruta, _ in operaciones if ruta.startswith("/api/v1")]
    assert len(v1) == 72
    assert sorted(
        ruta for ruta, _ in operaciones if not ruta.startswith("/api/v1")
    ) == ["/", "/health"]

    movimientos = esquema["paths"][RUTA_MOVIMIENTOS]["post"]
    descripcion = movimientos["description"]
    assert "Bodeguero" in descripcion, descripcion
    assert "Administrador" in descripcion, descripcion
    assert "403" in descripcion, descripcion
    assert "bodega" in descripcion.lower(), descripcion
    assert "201" in movimientos["responses"]
    assert "403" in movimientos["responses"]

    anulacion = esquema["paths"][RUTA_ANULACION]["post"]
    descripcion_anulacion = anulacion["description"]
    minusculas = descripcion_anulacion.lower()
    assert "administrador" in minusculas, descripcion_anulacion
    assert "confirm" in minusculas, (
        "la anulacion debe documentar el 409 de una entrega ya confirmada"
    )
    assert "devuelve" in minusculas or "devol" in minusculas, (
        "la anulacion debe documentar que devuelve el stock del retiro"
    )
    for codigo in ("403", "404", "409", "422"):
        assert codigo in descripcion_anulacion, f"falta documentar {codigo}"
    assert "409" in anulacion["responses"]


def test_openapi_publica_retiro_y_no_despacho_ac_55_64(cliente):
    """AC-55/AC-64: la ruta publicada cambia sin mover el recuento."""
    esquema = cliente.get("/openapi.json").json()

    assert RUTA_RETIRO in esquema["paths"], (
        "/openapi.json debe publicar POST /tickets/{ticket_id}/retiro"
    )
    assert "post" in esquema["paths"][RUTA_RETIRO]
    assert RUTA_DESPACHO not in esquema["paths"], (
        "/openapi.json no puede publicar la ruta historica /despacho"
    )


def test_openapi_del_retiro_declara_actores_y_codigos_ac_55(cliente):
    """AC-55: descripcion con el 403 del Administrador y los errores del retiro."""
    esquema = cliente.get("/openapi.json").json()
    operacion = esquema["paths"][RUTA_RETIRO]["post"]

    assert "Bodeguero" in operacion["description"]
    assert "Administrador" in operacion["description"]
    for codigo in ("403", "404", "409", "422"):
        assert codigo in operacion["description"], f"falta documentar {codigo}"
    assert "sede" in operacion["description"].lower()
    assert "stock" in operacion["description"].lower()

    peticion = operacion["requestBody"]["content"]["application/json"]["schema"][
        "$ref"
    ]
    assert peticion.endswith("TicketRetiro"), peticion
    respuesta = operacion["responses"]["200"]["content"]["application/json"][
        "schema"
    ]["$ref"]
    assert respuesta.endswith("TicketRespuesta"), respuesta


def test_openapi_del_patch_anuncia_el_retiro_y_no_el_despacho_ac_60(cliente):
    """AC-60/D-29: el cierre reservado dirige a `/retiro`."""
    esquema = cliente.get("/openapi.json").json()
    descripcion = esquema["paths"][RUTA_ESTADO]["patch"]["description"]

    assert "/retiro" in descripcion, (
        "la descripcion del PATCH debe dirigir al retiro"
    )
    assert "/despacho" not in descripcion, (
        "la descripcion del PATCH no puede conservar la ruta historica"
    )


def test_openapi_no_deja_el_dto_historico_ac_55(cliente):
    """AC-55/D-29: `TicketRetiro` sustituye a `TicketDespacho` en components."""
    esquema = cliente.get("/openapi.json").json()
    componentes = esquema["components"]["schemas"]

    assert "TicketRetiro" in componentes
    assert "TicketDespacho" not in componentes
