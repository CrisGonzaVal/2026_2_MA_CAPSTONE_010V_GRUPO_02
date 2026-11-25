"""T28 (Feature 013, ampliacion 25/Nov/2026): e2e del flujo y regresion de roles.

Seam bajo prueba: la **interfaz HTTP** del `app` real (`TestClient`), como en
toda la suite. Este modulo recorre de punta a punta el flujo de la §9 aprobada
(AC-28…AC-49) sobre el mundo de fixtures de la 013:

``Pendiente`` --Aprobar (Administrador)--> ``EnCurso`` --Despachar
(Bodeguero/Administrador, con stock)--> ``Cerrado`` --Confirmar entrega
(Solicitante dueño)--> ``Cerrado`` con etiqueta «Entregado».

Cubre ademas:

* la etiqueta de proceso y los dos responsables leidos por `GET /tickets/` y
  `GET /tickets/{id}` (AC-37…AC-40);
* el camino sin stock y Compras/021: la aprobacion hace aparecer la necesidad,
  la OC emitida/facturada cambia la etiqueta —«En compra»/«Facturado»— y la
  recepcion la lleva a «En confirmación de stock local» **sin** cambiar el
  estado (AC-31/AC-38);
* el caso #10 equivalente construido con fixtures (stock 64, minimo 10,
  demanda 3): la fila `(sede, producto)` sigue omitida en
  `GET /compras/necesidades` y el pedido cierra normal (AC-35);
* el `PATCH /estado` de legado: **403** para el Bodeguero, 200 y 409 para el
  Administrador (AC-28/AC-36/AC-49);
* el alta administrativa sin confirmacion posible: el pedido queda
  «Despachado» para siempre (AC-43/D-26);
* la matriz de errores 401/403/404/409 de aprobacion y confirmacion
  (AC-43/AC-45/AC-46).

La etiqueta de la **aprobacion** y de la **confirmacion** viene en el cuerpo del
200 (es lo que promete la spec §9.4/§9.9). El alta, el despacho y el `PATCH`
devuelven el ORM con los campos derivados en su valor por defecto (plan §9.1,
decision 9), de modo que sus etiquetas se observan por el read model
(`GET /tickets/` / `GET /tickets/{id}`), nunca por el cuerpo de la mutacion.

Las expectativas (roles, codigos, motivos y etiquetas) se transcriben a mano de
la spec; nunca se leen de `permisos.MATRIZ_PERMISOS` ni de
`ticket_proceso.ETIQUETAS`.
"""

from __future__ import annotations

from datetime import date

import pytest

from tests.funcional.integracion._soporte_ciclo_vida_013 import (
    DETALLE_TICKET_NO_ENCONTRADO,
    contar_en,
    leer_historial,
    leer_stock_sede,
    payload_alta,
    sembrar_mundo_013,
    sembrar_ticket,
)
from tests.funcional.integracion._soporte_ciclo_vida_catalogo_014 import (
    cliente_de_rol,
    fijar_stock_sede,
)

#: Contrato de la ampliacion (spec §9.3/§9.4/§9.9).
RUTA_TICKETS = "/api/v1/tickets/"
RUTA_APROBACION = "/api/v1/tickets/{ticket_id}/aprobacion"
RUTA_CONFIRMACION = "/api/v1/tickets/{ticket_id}/confirmacion-entrega"
RUTA_DESPACHO = "/api/v1/tickets/{ticket_id}/despacho"
RUTA_ESTADO = "/api/v1/tickets/{ticket_id}/estado"
RUTA_NECESIDADES = "/api/v1/compras/necesidades"
RUTA_ORDENES = "/api/v1/compras/ordenes"

#: Motivos literales del historial (spec D-16/D-25). Fuentes independientes.
MOTIVO_APROBACION = "Aprobación del pedido"
MOTIVO_CONFIRMACION = "Entrega confirmada por el solicitante"

#: Etiquetas de proceso de la spec §9.8, transcritas a mano.
ETIQUETA_EN_APROBACION = "En aprobación"
ETIQUETA_EN_CONFIRMACION_STOCK = "En confirmación de stock local"
ETIQUETA_POR_COMPRAR = "Por comprar"
ETIQUETA_EN_COMPRA = "En compra"
ETIQUETA_FACTURADO = "Facturado"
ETIQUETA_DESPACHADO = "Despachado"
ETIQUETA_ENTREGADO = "Entregado"

#: Cantidad de los pedidos de fixture (el detalle del alta usa 3).
CANTIDAD_PEDIDO = 3


@pytest.fixture
def datos_013(motor, dos_instituciones):
    """Estados 013, sede del departamento y 50 unidades del producto base."""
    return sembrar_mundo_013(motor, dos_instituciones)


# ---------------------------------------------------------------------------
# Observacion por la interfaz publica
# ---------------------------------------------------------------------------


def _detalle(cliente, ticket_id: int) -> dict:
    respuesta = cliente.get(f"/api/v1/tickets/{ticket_id}")
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


def _ticket_en_listado(cliente, ticket_id: int) -> dict:
    respuesta = cliente.get(RUTA_TICKETS)
    assert respuesta.status_code == 200, respuesta.text
    encontrado = next(
        (fila for fila in respuesta.json() if fila["ticket_id"] == ticket_id),
        None,
    )
    assert encontrado is not None, (
        f"el ticket {ticket_id} no aparece en GET /tickets/: {respuesta.text}"
    )
    return encontrado


def _alta(cliente, datos: dict, *, asunto: str = "Pedido del e2e 013") -> int:
    respuesta = cliente.post(
        RUTA_TICKETS,
        json=payload_alta(datos, datos["estados"]["Pendiente"], asunto=asunto),
    )
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()["ticket_id"]


def _aprobar(cliente, ticket_id: int):
    return cliente.post(f"/api/v1/tickets/{ticket_id}/aprobacion")


def _despachar(cliente, ticket_id: int, usuario_id: int):
    return cliente.post(
        f"/api/v1/tickets/{ticket_id}/despacho",
        json={"usuario_id": usuario_id},
    )


def _confirmar(cliente, ticket_id: int):
    return cliente.post(f"/api/v1/tickets/{ticket_id}/confirmacion-entrega")


def _necesidades(cliente) -> list[dict]:
    respuesta = cliente.get(RUTA_NECESIDADES)
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


def _necesidad_de(necesidades: list[dict], sede_id: int, producto_id: int):
    return next(
        (
            fila
            for fila in necesidades
            if fila["sede_id"] == sede_id and fila["producto_id"] == producto_id
        ),
        None,
    )


def _filas_por_motivo(historial: list[dict], motivo: str) -> list[dict]:
    return [fila for fila in historial if fila["motivo"] == motivo]


# ---------------------------------------------------------------------------
# Camino completo con stock: alta -> aprobar -> despachar -> confirmar
# ---------------------------------------------------------------------------


def test_flujo_completo_con_stock_aprobacion_despacho_y_confirmacion(motor, datos_013):
    """AC-29/30/33/37/39/40/42/45/46: el camino feliz de punta a punta."""
    datos = datos_013
    producto_id = datos["producto_id"]
    sede_id = datos["sede_id"]
    bodeguero_id = datos["usuarios_inst01"]["Bodeguero"]
    solicitante_id = datos["usuarios_inst01"]["Solicitante"]
    administrador_id = datos["usuario_id"]
    stock_inicial = leer_stock_sede(motor, sede_id, producto_id)
    assert stock_inicial == 50, "precondicion del mundo 013"

    # 1. Alta por el Solicitante: nace Pendiente y la etiqueta «En aprobación»
    #    se lee por el read model (el 201 devuelve el ORM, plan §9.1 decision 9).
    with cliente_de_rol(motor, datos, "Solicitante") as solicitante:
        alta = solicitante.post(
            RUTA_TICKETS,
            json=payload_alta(datos, datos["estados"]["Pendiente"]),
        )
        assert alta.status_code == 201, alta.text
        ticket_id = alta.json()["ticket_id"]
        assert alta.json()["estado_id"] == datos["estados"]["Pendiente"]
        assert alta.json()["fecha_cierre"] is None

        detalle = _detalle(solicitante, ticket_id)
        assert detalle["usuario_id"] == solicitante_id, (
            "la autoria es la identidad de la sesion"
        )
        assert detalle["etiqueta_proceso"] == ETIQUETA_EN_APROBACION
        assert detalle["explicacion_proceso"]
        assert detalle["fecha_cierre"] is None
        assert _ticket_en_listado(solicitante, ticket_id)["etiqueta_proceso"] == (
            ETIQUETA_EN_APROBACION
        ), "la etiqueta coincide entre listado y detalle (AC-39)"

    # 2. El Bodeguero no aprueba: 403 por matriz, sin mutar el pedido.
    with cliente_de_rol(motor, datos, "Bodeguero") as bodeguero:
        veto = _aprobar(bodeguero, ticket_id)
        assert veto.status_code == 403, veto.text
        assert _detalle(bodeguero, ticket_id)["estado_id"] == (
            datos["estados"]["Pendiente"]
        ), "un 403 no puede aprobar el pedido"

    # 3. El Administrador aprueba: 200, EnCurso, etiqueta con stock, una fila
    #    de historial con motivo literal y fecha_cierre nula.
    with cliente_de_rol(motor, datos, "Administrador") as admin:
        aprobacion = _aprobar(admin, ticket_id)
        assert aprobacion.status_code == 200, aprobacion.text
        cuerpo = aprobacion.json()
        assert cuerpo["estado_id"] == datos["estados"]["EnCurso"]
        assert cuerpo["etiqueta_proceso"] == ETIQUETA_EN_CONFIRMACION_STOCK, (
            "con stock, la aprobacion deja el pedido «En confirmación de stock "
            "local» (AC-29/AC-38)"
        )
        assert cuerpo["stock_disponible"] is True
        assert cuerpo["fecha_cierre"] is None, (
            "aprobar no es un cierre: fecha_cierre sigue nula"
        )

        historial = leer_historial(admin, ticket_id)
        filas = _filas_por_motivo(historial, MOTIVO_APROBACION)
        assert len(filas) == 1, (
            "exactamente una fila de aprobacion (la creacion no lleva motivo): "
            f"{historial}"
        )
        fila = filas[0]
        assert fila["ticket_id"] == ticket_id
        assert fila["estado_origen_id"] == datos["estados"]["Pendiente"]
        assert fila["estado_destino_id"] == datos["estados"]["EnCurso"]
        assert fila["usuario_id"] == administrador_id, (
            "el actor es el Administrador de la sesion"
        )
        assert fila["orden_compra_id"] is None, (
            "la aprobacion no se vincula a ninguna OC"
        )
        assert fila["fecha_transicion"] is not None
        assert _detalle(admin, ticket_id)["fecha_cierre"] is None

    # 4. El Bodeguero despacha con su usuario_id: 200 Cerrado, fecha_cierre,
    #    stock rebajado y una SALIDA auditada.
    with cliente_de_rol(motor, datos, "Bodeguero") as bodeguero:
        despacho = _despachar(bodeguero, ticket_id, bodeguero_id)
        assert despacho.status_code == 200, despacho.text
        cuerpo = despacho.json()
        assert cuerpo["estado_id"] == datos["estados"]["Cerrado"]
        assert cuerpo["fecha_cierre"] is not None

        assert leer_stock_sede(motor, sede_id, producto_id) == (
            stock_inicial - CANTIDAD_PEDIDO
        ), "el despacho rebaja el stock de la sede"
        assert contar_en(
            motor, "MovimientoInventario", tipo_movimiento="SALIDA"
        ) == 1, "una SALIDA por detalle (un detalle)"

        detalle = _detalle(bodeguero, ticket_id)
        assert detalle["etiqueta_proceso"] == ETIQUETA_DESPACHADO, (
            "Cerrado sin confirmacion es «Despachado»"
        )
        assert detalle["entrega_confirmada"] is False
        assert detalle["gestionado_por_bodeguero"]["usuario_id"] == bodeguero_id
        assert detalle["gestionado_por_administrador"]["usuario_id"] == (
            administrador_id
        )
        fecha_cierre_despacho = detalle["fecha_cierre"]

    # 5. Administrador y Bodeguero no confirman (403); el Solicitante dueño si.
    with cliente_de_rol(motor, datos, "Administrador") as admin:
        assert _confirmar(admin, ticket_id).status_code == 403
    with cliente_de_rol(motor, datos, "Bodeguero") as bodeguero:
        assert _confirmar(bodeguero, ticket_id).status_code == 403

    with cliente_de_rol(motor, datos, "Solicitante") as solicitante:
        confirmacion = _confirmar(solicitante, ticket_id)
        assert confirmacion.status_code == 200, confirmacion.text
        cuerpo = confirmacion.json()
        assert cuerpo["estado_id"] == datos["estados"]["Cerrado"], (
            "la confirmacion no cambia el estado canonico"
        )
        assert cuerpo["entrega_confirmada"] is True
        assert cuerpo["etiqueta_proceso"] == ETIQUETA_ENTREGADO

        historial = leer_historial(solicitante, ticket_id)
        filas = _filas_por_motivo(historial, MOTIVO_CONFIRMACION)
        assert len(filas) == 1, (
            f"exactamente una fila de confirmacion: {historial}"
        )
        fila = filas[0]
        assert fila["estado_origen_id"] == datos["estados"]["Cerrado"]
        assert fila["estado_destino_id"] == datos["estados"]["Cerrado"], (
            "la confirmacion es un evento Cerrado -> Cerrado"
        )
        assert fila["usuario_id"] == solicitante_id
        assert fila["fecha_transicion"] is not None
        assert fila["orden_compra_id"] is None

        # La segunda confirmacion responde 409 sin una segunda fila.
        segunda = _confirmar(solicitante, ticket_id)
        assert segunda.status_code == 409, segunda.text
        assert len(
            _filas_por_motivo(leer_historial(solicitante, ticket_id), MOTIVO_CONFIRMACION)
        ) == 1, "el 409 no puede duplicar la fila de confirmacion"

        # Sin efectos colaterales: stock, movimientos y fecha_cierre intactos.
        assert leer_stock_sede(motor, sede_id, producto_id) == (
            stock_inicial - CANTIDAD_PEDIDO
        )
        assert contar_en(
            motor, "MovimientoInventario", tipo_movimiento="SALIDA"
        ) == 1

        detalle = _detalle(solicitante, ticket_id)
        assert detalle["estado_id"] == datos["estados"]["Cerrado"]
        assert detalle["fecha_cierre"] == fecha_cierre_despacho, (
            "la confirmacion no sella ni borra fecha_cierre"
        )
        assert detalle["etiqueta_proceso"] == ETIQUETA_ENTREGADO
        assert detalle["entrega_confirmada_en"] is not None
        assert detalle["entrega_confirmada_por_nombre"] is not None
        assert detalle["entrega_confirmada_por_apellido"] is not None
        assert detalle["gestionado_por_bodeguero"]["usuario_id"] == bodeguero_id
        assert detalle["gestionado_por_administrador"]["usuario_id"] == (
            administrador_id
        )

        # La etiqueta y los responsables coinciden en el listado (AC-39/AC-40).
        tarjeta = _ticket_en_listado(solicitante, ticket_id)
        assert tarjeta["estado_id"] == datos["estados"]["Cerrado"]
        assert tarjeta["etiqueta_proceso"] == ETIQUETA_ENTREGADO
        assert tarjeta["entrega_confirmada"] is True
        assert tarjeta["gestionado_por_bodeguero"]["usuario_id"] == bodeguero_id
        assert tarjeta["gestionado_por_administrador"]["usuario_id"] == (
            administrador_id
        ), "tablero y detalle no pueden divergir en la etiqueta ni en los gestores"


# ---------------------------------------------------------------------------
# Camino sin stock: aprobacion, necesidad en Compras y cadena de la OC
# ---------------------------------------------------------------------------


def test_aprobacion_sin_stock_aparece_en_compras_y_la_oc_mueve_la_etiqueta(
    motor, dos_instituciones
):
    """AC-31/AC-38: «Por comprar» -> necesidad -> «En compra» -> «Facturado» ->
    «En confirmación de stock local», sin cambiar el estado canonico."""
    datos = sembrar_mundo_013(motor, dos_instituciones, con_stock=False)
    producto_id = datos["producto_id"]
    sede_id = datos["sede_id"]
    bodeguero_id = datos["usuarios_inst01"]["Bodeguero"]

    with cliente_de_rol(motor, datos, "Solicitante") as solicitante:
        ticket_id = _alta(solicitante, datos, asunto="Pedido sin stock del e2e")

    # Antes de aprobar, el pedido Pendiente no es demanda de Compras.
    with cliente_de_rol(motor, datos, "Administrador") as admin:
        necesidades = _necesidades(admin)
        assert _necesidad_de(necesidades, sede_id, producto_id) is None, (
            "un pedido Pendiente no suma demanda ni aparece en Compras"
        )

    # Aprobar siempre deja EnCurso; sin stock, la etiqueta es «Por comprar».
    with cliente_de_rol(motor, datos, "Administrador") as admin:
        aprobacion = _aprobar(admin, ticket_id)
        assert aprobacion.status_code == 200, aprobacion.text
        cuerpo = aprobacion.json()
        assert cuerpo["estado_id"] == datos["estados"]["EnCurso"]
        assert cuerpo["stock_disponible"] is False
        assert cuerpo["etiqueta_proceso"] == ETIQUETA_POR_COMPRAR

        # Ya EnCurso, aparece como necesidad neta (minimo 10 + demanda 3).
        necesidades = _necesidades(admin)
        fila = _necesidad_de(necesidades, sede_id, producto_id)
        assert fila is not None, (
            "el pedido aprobado sin stock debe aparecer en Compras: "
            f"{necesidades}"
        )
        assert fila["stock_actual"] == 0
        assert fila["stock_minimo"] == 10
        assert fila["demanda_tickets"] == CANTIDAD_PEDIDO
        assert fila["sugerido"] == 13, "minimo 10 + demanda 3 - stock 0"
        assert [t["ticket_id"] for t in fila["tickets"]] == [ticket_id]

        # La OC: crear -> emitir -> facturar por HTTP.
        proveedor = admin.post(
            "/api/v1/compras/proveedores",
            json={"rut": "51.000.000-5", "razon_social": "Proveedor e2e 013"},
        )
        assert proveedor.status_code == 201, proveedor.text
        proveedor_id = proveedor.json()["proveedor_id"]

        creada = admin.post(
            RUTA_ORDENES,
            json={
                "sede_id": sede_id,
                "proveedor_id": proveedor_id,
                "items": [
                    {
                        "producto_id": producto_id,
                        "cantidad_solicitada": 10,
                        "precio_unitario": "2.50",
                    }
                ],
            },
        )
        assert creada.status_code == 201, creada.text
        orden_id = creada.json()["orden_compra_id"]

        emitida = admin.post(f"{RUTA_ORDENES}/{orden_id}/emitir")
        assert emitida.status_code == 200, emitida.text
        assert emitida.json()["estado"] == "Emitida"

        detalle = _detalle(admin, ticket_id)
        assert detalle["estado_id"] == datos["estados"]["EnCurso"], (
            "emitir la OC no cambia el estado del pedido"
        )
        assert detalle["estado_orden_cobertura"] == "Emitida"
        assert detalle["etiqueta_proceso"] == ETIQUETA_EN_COMPRA

        facturada = admin.put(
            f"{RUTA_ORDENES}/{orden_id}/factura",
            json={
                "numero_factura": "FAC-E2E-013",
                "fecha_factura": date.today().isoformat(),
                "monto_total": "25.00",
            },
        )
        assert facturada.status_code == 200, facturada.text

        detalle = _detalle(admin, ticket_id)
        assert detalle["estado_id"] == datos["estados"]["EnCurso"]
        assert detalle["estado_orden_cobertura"] == "Facturada"
        assert detalle["etiqueta_proceso"] == ETIQUETA_FACTURADO

    # La recepcion del Bodeguero de la sede incrementa stock y deja la etiqueta
    # en «En confirmación de stock local», sin mover el estado.
    with cliente_de_rol(motor, datos, "Bodeguero") as bodeguero:
        recepcion = bodeguero.post(f"{RUTA_ORDENES}/{orden_id}/recepcion")
        assert recepcion.status_code == 200, recepcion.text
        assert recepcion.json()["estado"] == "Recibida"

        assert leer_stock_sede(motor, sede_id, producto_id) == 10

        detalle = _detalle(bodeguero, ticket_id)
        assert detalle["estado_id"] == datos["estados"]["EnCurso"], (
            "la recepcion no cambia el estado del pedido"
        )
        assert detalle["estado_orden_cobertura"] == "Recibida"
        assert detalle["etiqueta_proceso"] == ETIQUETA_EN_CONFIRMACION_STOCK

    # El flujo cierra por el despacho, con el usuario del Bodeguero de la sede.
    with cliente_de_rol(motor, datos, "Bodeguero") as bodeguero:
        despacho = _despachar(bodeguero, ticket_id, bodeguero_id)
        assert despacho.status_code == 200, despacho.text
        assert despacho.json()["estado_id"] == datos["estados"]["Cerrado"]

        detalle = _detalle(bodeguero, ticket_id)
        assert detalle["etiqueta_proceso"] == ETIQUETA_DESPACHADO


# ---------------------------------------------------------------------------
# Caso #10 equivalente: pedido cubierto por stock no aparece en Compras
# ---------------------------------------------------------------------------


def test_caso_10_equivalente_omitido_en_compras_y_cierra_normal(
    motor, dos_instituciones
):
    """AC-35: stock 64, minimo 10 y demanda 3 -> la fila se omite; el flujo cierra."""
    datos = sembrar_mundo_013(motor, dos_instituciones, con_stock=False)
    producto_id = datos["producto_id"]
    sede_id = datos["sede_id"]
    bodeguero_id = datos["usuarios_inst01"]["Bodeguero"]

    # La sede arranca con 64 unidades, como el caso reportado de la Sede Maipu.
    fijar_stock_sede(motor, datos, producto_id, 64)

    with cliente_de_rol(motor, datos, "Solicitante") as solicitante:
        ticket_id = _alta(solicitante, datos, asunto="Caso 10 papel confort")

    with cliente_de_rol(motor, datos, "Administrador") as admin:
        aprobacion = _aprobar(admin, ticket_id)
        assert aprobacion.status_code == 200, aprobacion.text
        assert aprobacion.json()["etiqueta_proceso"] == (
            ETIQUETA_EN_CONFIRMACION_STOCK
        )

        necesidades = _necesidades(admin)
        assert _necesidad_de(necesidades, sede_id, producto_id) is None, (
            "stock 64 > minimo 10 y demanda 3 <= 64: la fila se omite (020/021), "
            f"no es un fallo: {necesidades}"
        )

    # El pedido cubierto por stock cierra normal: despacho y confirmacion.
    with cliente_de_rol(motor, datos, "Bodeguero") as bodeguero:
        despacho = _despachar(bodeguero, ticket_id, bodeguero_id)
        assert despacho.status_code == 200, despacho.text
        assert despacho.json()["estado_id"] == datos["estados"]["Cerrado"]
        assert leer_stock_sede(motor, sede_id, producto_id) == 64 - CANTIDAD_PEDIDO

    with cliente_de_rol(motor, datos, "Solicitante") as solicitante:
        confirmacion = _confirmar(solicitante, ticket_id)
        assert confirmacion.status_code == 200, confirmacion.text
        assert confirmacion.json()["etiqueta_proceso"] == ETIQUETA_ENTREGADO


# ---------------------------------------------------------------------------
# PATCH /estado de legado: solo Administrador y cierre reservado
# ---------------------------------------------------------------------------


def test_patch_de_legado_solo_administrador_y_cierre_reservado(motor, datos_013):
    """AC-28/AC-36/AC-49: Bodeguero 403; Administrador 200 en un paso y 409 al
    intentar el cierre reservado al despacho."""
    datos = datos_013
    ticket_id = sembrar_ticket(
        motor, datos, estado_id=datos["estados"]["Pendiente"]
    )

    with cliente_de_rol(motor, datos, "Bodeguero") as bodeguero:
        veto = bodeguero.patch(
            f"/api/v1/tickets/{ticket_id}/estado",
            json={"estado_id": datos["estados"]["EnRevision"]},
        )
        assert veto.status_code == 403, veto.text
        assert _detalle(bodeguero, ticket_id)["estado_id"] == (
            datos["estados"]["Pendiente"]
        ), "el 403 del Bodeguero no puede mover el pedido"

    with cliente_de_rol(motor, datos, "Administrador") as admin:
        avance = admin.patch(
            f"/api/v1/tickets/{ticket_id}/estado",
            json={"estado_id": datos["estados"]["EnRevision"]},
        )
        assert avance.status_code == 200, avance.text
        assert avance.json()["estado_id"] == datos["estados"]["EnRevision"], (
            "el PATCH conserva su regla de un paso y no auto-avanza a EnCurso"
        )

    # El cierre EnCurso -> Cerrado sigue reservado al despacho (005 intacta).
    en_curso = sembrar_ticket(
        motor, datos, estado_id=datos["estados"]["EnCurso"], asunto="Cierre reservado"
    )
    with cliente_de_rol(motor, datos, "Administrador") as admin:
        cierre = admin.patch(
            f"/api/v1/tickets/{en_curso}/estado",
            json={"estado_id": datos["estados"]["Cerrado"]},
        )
        assert cierre.status_code == 409, cierre.text
        assert cierre.json()["detail"] == (
            "El cierre requiere despacho; use "
            f"POST /api/v1/tickets/{en_curso}/despacho"
        )
        assert _detalle(admin, en_curso)["estado_id"] == (
            datos["estados"]["EnCurso"]
        )


# ---------------------------------------------------------------------------
# Alta administrativa: el dueño sin rol Solicitante no confirma
# ---------------------------------------------------------------------------


def test_altas_sin_rol_solicitante_quedan_despachadas_sin_confirmacion(
    motor, datos_013
):
    """AC-43/D-26: un pedido creado por Administrador o Bodeguero (dueño sin rol
    Solicitante) no tiene confirmacion posible; tras el despacho permanece
    «Despachado»."""
    datos = datos_013
    administrador_id = datos["usuario_id"]
    bodeguero_id = datos["usuarios_inst01"]["Bodeguero"]

    with cliente_de_rol(motor, datos, "Administrador") as admin:
        ticket_id = _alta(admin, datos, asunto="Alta administrativa del e2e")

        detalle = _detalle(admin, ticket_id)
        assert detalle["usuario_id"] == administrador_id, (
            "la autoria es la identidad de la sesion (Administrador)"
        )
        assert detalle["etiqueta_proceso"] == ETIQUETA_EN_APROBACION

        aprobacion = _aprobar(admin, ticket_id)
        assert aprobacion.status_code == 200, aprobacion.text

        despacho = _despachar(admin, ticket_id, administrador_id)
        assert despacho.status_code == 200, despacho.text
        assert despacho.json()["estado_id"] == datos["estados"]["Cerrado"]

        # El Administrador no tiene la operacion de confirmacion (403 por
        # matriz); el pedido se queda «Despachado» para siempre.
        confirmacion = _confirmar(admin, ticket_id)
        assert confirmacion.status_code == 403, confirmacion.text

        detalle = _detalle(admin, ticket_id)
        assert detalle["estado_id"] == datos["estados"]["Cerrado"]
        assert detalle["entrega_confirmada"] is False
        assert detalle["etiqueta_proceso"] == ETIQUETA_DESPACHADO
        assert _filas_por_motivo(
            leer_historial(admin, ticket_id), MOTIVO_CONFIRMACION
        ) == [], "no se inventa una confirmacion por otro rol"

    # El mismo caso con un pedido creado por el Bodeguero: tampoco confirma.
    with cliente_de_rol(motor, datos, "Bodeguero") as bodeguero:
        ticket_bodeguero = _alta(bodeguero, datos, asunto="Alta del Bodeguero")
        assert _detalle(bodeguero, ticket_bodeguero)["usuario_id"] == bodeguero_id

    with cliente_de_rol(motor, datos, "Administrador") as admin:
        aprobacion = _aprobar(admin, ticket_bodeguero)
        assert aprobacion.status_code == 200, aprobacion.text

    with cliente_de_rol(motor, datos, "Bodeguero") as bodeguero:
        despacho = _despachar(bodeguero, ticket_bodeguero, bodeguero_id)
        assert despacho.status_code == 200, despacho.text
        assert _confirmar(bodeguero, ticket_bodeguero).status_code == 403
        detalle = _detalle(bodeguero, ticket_bodeguero)
        assert detalle["entrega_confirmada"] is False
        assert detalle["etiqueta_proceso"] == ETIQUETA_DESPACHADO


# ---------------------------------------------------------------------------
# Errores de aprobacion y confirmacion (401/403/404/409)
# ---------------------------------------------------------------------------


def test_aprobacion_y_confirmacion_de_pedido_ajeno_responden_404(motor, datos_013):
    """AC-43/AC-46: el 404 de ocultamiento es identico para el pedido ajeno."""
    datos = datos_013
    ajeno = sembrar_ticket(
        motor,
        datos,
        usuario_id=datos["usuarios_inst02"]["Solicitante"],
        institucion_id=datos["inst_ajena"],
        sede_id=datos["sede_ajena_id"],
        producto_id=datos["producto_homonimo_ajeno_id"],
        estado_id=datos["estados"]["Pendiente"],
        asunto="Pedido ajeno de INST02",
    )
    ajeno_cerrado = sembrar_ticket(
        motor,
        datos,
        usuario_id=datos["usuarios_inst02"]["Solicitante"],
        institucion_id=datos["inst_ajena"],
        sede_id=datos["sede_ajena_id"],
        producto_id=datos["producto_homonimo_ajeno_id"],
        estado_id=datos["estados"]["Cerrado"],
        asunto="Pedido ajeno cerrado de INST02",
    )

    # El Administrador de INST01 no aprueba un pedido de INST02: 404 identico.
    with cliente_de_rol(motor, datos, "Administrador") as admin:
        respuesta = _aprobar(admin, ajeno)
        assert respuesta.status_code == 404, respuesta.text
        assert respuesta.json()["detail"] == DETALLE_TICKET_NO_ENCONTRADO

    # El Solicitante de INST01 no confirma un pedido de otro Solicitante: 404
    # identico, aunque el pedido este Cerrado.
    with cliente_de_rol(motor, datos, "Solicitante") as solicitante:
        respuesta = _confirmar(solicitante, ajeno_cerrado)
        assert respuesta.status_code == 404, respuesta.text
        assert respuesta.json()["detail"] == DETALLE_TICKET_NO_ENCONTRADO


def test_confirmacion_exige_cerrado_y_no_duplica_la_fila(motor, datos_013):
    """AC-43: no `Cerrado` -> 409 sin escribir; ya confirmado -> 409 sin fila."""
    datos = datos_013
    solicitante_id = datos["usuarios_inst01"]["Solicitante"]

    # Un pedido Pendiente del propio Solicitante no se puede confirmar.
    pendiente = sembrar_ticket(
        motor, datos, estado_id=datos["estados"]["Pendiente"]
    )
    with cliente_de_rol(motor, datos, "Solicitante") as solicitante:
        respuesta = _confirmar(solicitante, pendiente)
        assert respuesta.status_code == 409, respuesta.text
        assert leer_historial(solicitante, pendiente) == [], (
            "el 409 de no Cerrado no puede escribir historial"
        )

    # Un pedido Cerrado del propio Solicitante confirma una sola vez.
    cerrado = sembrar_ticket(
        motor, datos, estado_id=datos["estados"]["Cerrado"], asunto="Ya confirmado"
    )
    with cliente_de_rol(motor, datos, "Solicitante") as solicitante:
        primera = _confirmar(solicitante, cerrado)
        assert primera.status_code == 200, primera.text
        fila = _filas_por_motivo(
            leer_historial(solicitante, cerrado), MOTIVO_CONFIRMACION
        )
        assert len(fila) == 1
        assert fila[0]["usuario_id"] == solicitante_id

        segunda = _confirmar(solicitante, cerrado)
        assert segunda.status_code == 409, segunda.text
        assert len(
            _filas_por_motivo(
                leer_historial(solicitante, cerrado), MOTIVO_CONFIRMACION
            )
        ) == 1, "la segunda confirmacion no escribe una segunda fila"
