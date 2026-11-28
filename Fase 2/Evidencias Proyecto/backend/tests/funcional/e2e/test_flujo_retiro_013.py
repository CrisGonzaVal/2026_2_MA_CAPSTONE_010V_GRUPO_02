"""T42 (Feature 013; enmienda 26/Nov/2026): e2e del flujo de retiro - SQLite.

Seam bajo prueba: la **interfaz HTTP** del `app` real (`TestClient`), como en
toda la suite. Este modulo recorre de punta a punta la enmienda sobre el mundo de
fixtures de la 013:

    EnRevision --Aprobar (Administrador)--> EnCurso
    --Retirar (Bodeguero de la sede, con stock)--> Cerrado
    --Confirmar entrega (Solicitante dueño)--> Cerrado «Entregado»

y las dos salidas del cierre que abre el Administrador:

  * **Anular el retiro antes de confirmar**: `Cerrado -> Anulado` con una
    `ENTRADA` por detalle, stock restituido, `cantidad_entregada = 0`,
    `fecha_cierre` nula e historial `Cerrado -> Anulado`; la confirmacion
    posterior responde **409**.
  * **Confirmar primero**: la anulacion responde **409** sin tocar la fila de
    confirmacion, el stock, la fecha ni el estado.

Cubre ademas:

  * el `PATCH /estado` de legado: **403** para el Bodeguero; 200 del
    Administrador en `EnRevision -> EnCurso` y **409** al intentar
    `EnCurso -> Cerrado`, que sigue reservado al retiro (AC-49/AC-60);
  * Compras/021 sin cambio de logica: el «caso #10 equivalente» (stock 64,
    minimo 10, demanda 3) sigue omitido en `GET /compras/necesidades` antes y
    despues de la devolucion, y la anulacion **no** crea filas de desbloqueo ni
    de plan de compra (AC-35).

Las expectativas (roles, codigos, motivos y etiquetas) se transcriben a mano de
la spec; nunca se leen de `permisos.MATRIZ_PERMISOS` ni de
`ticket_proceso.ETIQUETAS`. Los unitarios de T34-T38 no se duplican: aqui solo
se verifica la integracion de la enmienda.
"""

from __future__ import annotations

import pytest

from tests.funcional.integracion._soporte_ciclo_vida_013 import payload_alta
from tests.funcional.integracion._soporte_retiro_013 import (
    MOTIVO_CONFIRMACION,
    anular,
    cambiar_estado,
    cliente_rol,
    confirmar,
    contar_en,
    entregas_de_ticket,
    entradas_devolucion,
    estado_de_ticket,
    fecha_cierre_de_ticket,
    fijar_stock,
    historial_persistido,
    retirar,
    salidas_retiro,
    sembrar_mundo_retiro,
    sembrar_ticket_retiro,
    stock_de,
)

#: Contrato de la enmienda (spec §10.5/§10.6).
RUTA_TICKETS = "/api/v1/tickets/"
RUTA_APROBACION = "/api/v1/tickets/{ticket_id}/aprobacion"
RUTA_RETIRO = "/api/v1/tickets/{ticket_id}/retiro"
RUTA_ANULACION = "/api/v1/tickets/{ticket_id}/anulacion"
RUTA_CONFIRMACION = "/api/v1/tickets/{ticket_id}/confirmacion-entrega"
RUTA_ESTADO = "/api/v1/tickets/{ticket_id}/estado"
RUTA_NECESIDADES = "/api/v1/compras/necesidades"

#: Motivos literales de la spec (D-16/D-32). Fuentes independientes.
MOTIVO_APROBACION = "Aprobación del pedido"
MOTIVO_ANULACION = "Retiro registrado por error en la bodega"

#: Etiquetas de proceso de la spec §9.8 (transcritas a mano).
ETIQUETA_EN_REVISION = "En revisión"
ETIQUETA_RETIRADO = "Retirado"
ETIQUETA_ENTREGADO = "Entregado"

#: Cantidad del detalle del alta (`payload_alta`).
CANTIDAD_PEDIDO = 3


@pytest.fixture
def datos_013(motor, dos_instituciones):
    """Estados 013, sede del departamento, Bodeguero de esa sede y stock 50."""
    return sembrar_mundo_retiro(motor, dos_instituciones)


# ---------------------------------------------------------------------------
# Observacion por la interfaz publica
# ---------------------------------------------------------------------------


def _detalle(cliente, ticket_id: int) -> dict:
    respuesta = cliente.get(f"/api/v1/tickets/{ticket_id}")
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


def _alta(cliente, datos: dict, *, asunto: str = "Pedido del e2e de retiro") -> int:
    respuesta = cliente.post(
        RUTA_TICKETS,
        json=payload_alta(datos, datos["estados"]["EnRevision"], asunto=asunto),
    )
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()["ticket_id"]


def _aprobar(cliente, ticket_id: int):
    return cliente.post(f"/api/v1/tickets/{ticket_id}/aprobacion")


def _retirar(cliente, ticket_id: int, usuario_id: int):
    return retirar(cliente, ticket_id, {"usuario_id": usuario_id})


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


# ---------------------------------------------------------------------------
# Flujo completo: alta -> aprobar -> retirar -> confirmar
# ---------------------------------------------------------------------------


def test_flujo_completo_de_retiro_y_confirmacion_ac_55_ac_57_ac_61(
    motor, datos_013
):
    """AC-55/AC-57/AC-61: el camino feliz del retiro, de punta a punta por HTTP."""
    datos = datos_013
    producto_id = datos["producto_id"]
    sede_id = datos["sede_id"]
    bodeguero_id = datos["usuarios_inst01"]["Bodeguero"]
    solicitante_id = datos["usuarios_inst01"]["Solicitante"]
    assert stock_de(motor, sede_id, producto_id) == 50, "precondicion del mundo"

    # 1. El Solicitante crea: nace EnRevision (AC-51) y la etiqueta es la vigente.
    with cliente_rol(motor, datos, "Solicitante") as solicitante:
        ticket_id = _alta(solicitante, datos)
        detalle = _detalle(solicitante, ticket_id)
        assert detalle["estado_id"] == datos["estados"]["EnRevision"]
        assert detalle["etiqueta_proceso"] == ETIQUETA_EN_REVISION
        assert detalle["usuario_id"] == solicitante_id

    # 2. El Administrador aprueba: EnCurso, sin stock movido ni fecha de cierre.
    with cliente_rol(motor, datos, "Administrador") as admin:
        aprobacion = _aprobar(admin, ticket_id)
        assert aprobacion.status_code == 200, aprobacion.text
        assert aprobacion.json()["estado_id"] == datos["estados"]["EnCurso"]
        assert aprobacion.json()["fecha_cierre"] is None
        filas = [
            fila
            for fila in historial_persistido(motor, ticket_id)
            if fila["motivo"] == MOTIVO_APROBACION
        ]
        assert len(filas) == 1, filas
        assert filas[0]["estado_origen_id"] == datos["estados"]["EnRevision"]
        assert filas[0]["estado_destino_id"] == datos["estados"]["EnCurso"]
        assert stock_de(motor, sede_id, producto_id) == 50

    # 3. El Bodeguero de la sede retira: Cerrado, SALIDA, entrega y cierre.
    with cliente_rol(motor, datos, "Bodeguero") as bodeguero:
        retiro = _retirar(bodeguero, ticket_id, bodeguero_id)
        assert retiro.status_code == 200, retiro.text
        cuerpo = retiro.json()
        assert cuerpo["estado_id"] == datos["estados"]["Cerrado"]
        assert cuerpo["fecha_cierre"] is not None

        assert stock_de(motor, sede_id, producto_id) == 50 - CANTIDAD_PEDIDO
        salidas = salidas_retiro(motor, ticket_id)
        assert len(salidas) == 1 and salidas[0]["cantidad"] == CANTIDAD_PEDIDO
        assert entregas_de_ticket(motor, ticket_id) == {
            cuerpo["detalles"][0]["detalle_ticket_id"]: CANTIDAD_PEDIDO
        }

        detalle = _detalle(bodeguero, ticket_id)
        assert detalle["etiqueta_proceso"] == ETIQUETA_RETIRADO
        assert detalle["entrega_confirmada"] is False
        fecha_cierre_retiro = detalle["fecha_cierre"]

        filas = [
            fila
            for fila in historial_persistido(motor, ticket_id)
            if fila["estado_origen_id"] == datos["estados"]["EnCurso"]
            and fila["estado_destino_id"] == datos["estados"]["Cerrado"]
        ]
        assert len(filas) == 1, filas
        assert filas[0]["usuario_id"] == bodeguero_id
        assert filas[0]["motivo"] is None

    # 4. El Solicitante dueño confirma: evento Cerrado -> Cerrado sin mover nada.
    with cliente_rol(motor, datos, "Solicitante") as solicitante:
        confirmacion = confirmar(solicitante, ticket_id)
        assert confirmacion.status_code == 200, confirmacion.text
        assert confirmacion.json()["estado_id"] == datos["estados"]["Cerrado"]
        assert confirmacion.json()["entrega_confirmada"] is True
        assert confirmacion.json()["etiqueta_proceso"] == ETIQUETA_ENTREGADO

        detalle = _detalle(solicitante, ticket_id)
        assert detalle["fecha_cierre"] == fecha_cierre_retiro, (
            "la confirmacion no sella ni borra fecha_cierre"
        )
        assert stock_de(motor, sede_id, producto_id) == 50 - CANTIDAD_PEDIDO
        assert len(salidas_retiro(motor, ticket_id)) == 1, (
            "la confirmacion no crea una segunda SALIDA"
        )
        filas = [
            fila
            for fila in historial_persistido(motor, ticket_id)
            if fila["motivo"] == MOTIVO_CONFIRMACION
        ]
        assert len(filas) == 1, filas
        assert filas[0]["estado_origen_id"] == datos["estados"]["Cerrado"]
        assert filas[0]["estado_destino_id"] == datos["estados"]["Cerrado"]


# ---------------------------------------------------------------------------
# Anulacion del retiro antes de confirmar: devolucion de stock
# ---------------------------------------------------------------------------


def test_anulacion_del_retiro_antes_de_confirmar_devuelve_el_stock_ac_58_ac_59(
    motor, datos_013
):
    """AC-58/AC-59: `Cerrado -> Anulado` con ENTRADA, reset y cierre nulo."""
    datos = datos_013
    producto_id = datos["producto_id"]
    sede_id = datos["sede_id"]
    bodeguero_id = datos["usuarios_inst01"]["Bodeguero"]
    administrador_id = datos["usuario_id"]

    with cliente_rol(motor, datos, "Solicitante") as solicitante:
        ticket_id = _alta(solicitante, datos, asunto="Retiro a anular (e2e)")
    with cliente_rol(motor, datos, "Administrador") as admin:
        assert _aprobar(admin, ticket_id).status_code == 200
    with cliente_rol(motor, datos, "Bodeguero") as bodeguero:
        retiro = _retirar(bodeguero, ticket_id, bodeguero_id)
        assert retiro.status_code == 200, retiro.text
        detalle_id = retiro.json()["detalles"][0]["detalle_ticket_id"]
    assert stock_de(motor, sede_id, producto_id) == 50 - CANTIDAD_PEDIDO

    with cliente_rol(motor, datos, "Administrador") as admin:
        anulacion = anular(admin, ticket_id, MOTIVO_ANULACION)
        assert anulacion.status_code == 200, anulacion.text
        cuerpo = anulacion.json()
        assert cuerpo["estado_id"] == datos["estados"]["Anulado"]
        assert cuerpo["fecha_cierre"] is None, (
            "un Anulado no conserva la fecha del retiro (D-32)"
        )
        assert [d["cantidad_entregada"] for d in cuerpo["detalles"]] == [0]

        assert stock_de(motor, sede_id, producto_id) == 50, (
            "la anulacion restituye exactamente lo entregado"
        )
        assert entregas_de_ticket(motor, ticket_id) == {detalle_id: 0}
        entradas = entradas_devolucion(motor, ticket_id)
        assert len(entradas) == 1, entradas
        assert entradas[0]["tipo_movimiento"] == "ENTRADA"
        assert entradas[0]["cantidad"] == CANTIDAD_PEDIDO
        assert entradas[0]["sede_id"] == sede_id
        assert len(salidas_retiro(motor, ticket_id)) == 1, (
            "la SALIDA original se conserva como evidencia inmutable"
        )

        filas = [
            fila
            for fila in historial_persistido(motor, ticket_id)
            if fila["estado_origen_id"] == datos["estados"]["Cerrado"]
            and fila["estado_destino_id"] == datos["estados"]["Anulado"]
        ]
        assert len(filas) == 1, filas
        assert filas[0]["usuario_id"] == administrador_id
        assert filas[0]["motivo"] == MOTIVO_ANULACION

    # La confirmacion posterior ve un pedido Anulado y responde 409.
    with cliente_rol(motor, datos, "Solicitante") as solicitante:
        confirmacion = confirmar(solicitante, ticket_id)
        assert confirmacion.status_code == 409, confirmacion.text

    assert estado_de_ticket(motor, ticket_id) == datos["estados"]["Anulado"]
    assert stock_de(motor, sede_id, producto_id) == 50
    assert fecha_cierre_de_ticket(motor, ticket_id) is None


# ---------------------------------------------------------------------------
# Confirmacion previa: la anulacion responde 409 sin efectos
# ---------------------------------------------------------------------------


def test_la_confirmacion_previa_bloquea_la_anulacion_ac_61(motor, datos_013):
    """AC-61/D-34: confirmado no se anula; su fila y el stock quedan intactos."""
    datos = datos_013
    producto_id = datos["producto_id"]
    sede_id = datos["sede_id"]
    bodeguero_id = datos["usuarios_inst01"]["Bodeguero"]

    with cliente_rol(motor, datos, "Solicitante") as solicitante:
        ticket_id = _alta(solicitante, datos, asunto="Retiro confirmado (e2e)")
    with cliente_rol(motor, datos, "Administrador") as admin:
        assert _aprobar(admin, ticket_id).status_code == 200
    with cliente_rol(motor, datos, "Bodeguero") as bodeguero:
        assert _retirar(bodeguero, ticket_id, bodeguero_id).status_code == 200
    with cliente_rol(motor, datos, "Solicitante") as solicitante:
        assert confirmar(solicitante, ticket_id).status_code == 200

    filas_antes = historial_persistido(motor, ticket_id)
    fecha_antes = fecha_cierre_de_ticket(motor, ticket_id)
    stock_antes = stock_de(motor, sede_id, producto_id)

    with cliente_rol(motor, datos, "Administrador") as admin:
        anulacion = anular(admin, ticket_id, MOTIVO_ANULACION)
        assert anulacion.status_code == 409, anulacion.text

    assert estado_de_ticket(motor, ticket_id) == datos["estados"]["Cerrado"]
    assert fecha_cierre_de_ticket(motor, ticket_id) == fecha_antes
    assert stock_de(motor, sede_id, producto_id) == stock_antes
    assert entradas_devolucion(motor, ticket_id) == []
    assert historial_persistido(motor, ticket_id) == filas_antes, (
        "el 409 no borra ni reescribe la confirmacion"
    )
    assert any(
        fila["motivo"] == MOTIVO_CONFIRMACION for fila in filas_antes
    ), "la confirmacion previa sigue registrada"


# ---------------------------------------------------------------------------
# PATCH /estado de legado
# ---------------------------------------------------------------------------


def test_patch_de_legado_bodeguero_403_y_administrador_200_y_409_ac_49(
    motor, datos_013
):
    """AC-49/AC-60: solo Administrador; el cierre sigue reservado al retiro."""
    datos = datos_013
    ticket_id = sembrar_ticket_retiro(motor, datos, estado="EnRevision")
    en_curso_id = sembrar_ticket_retiro(
        motor, datos, estado="EnCurso", asunto="Cierre reservado (e2e)"
    )

    with cliente_rol(motor, datos, "Bodeguero") as bodeguero:
        veto = cambiar_estado(bodeguero, ticket_id, datos["estados"]["EnCurso"])
        assert veto.status_code == 403, veto.text
        assert estado_de_ticket(motor, ticket_id) == datos["estados"]["EnRevision"]

    with cliente_rol(motor, datos, "Administrador") as admin:
        avance = cambiar_estado(admin, ticket_id, datos["estados"]["EnCurso"])
        assert avance.status_code == 200, avance.text
        assert avance.json()["estado_id"] == datos["estados"]["EnCurso"]

        cierre = cambiar_estado(admin, en_curso_id, datos["estados"]["Cerrado"])
        assert cierre.status_code == 409, cierre.text
        assert cierre.json()["detail"] == (
            "El cierre requiere retiro; use "
            f"POST /api/v1/tickets/{en_curso_id}/retiro"
        )
        assert estado_de_ticket(motor, en_curso_id) == datos["estados"]["EnCurso"]


# ---------------------------------------------------------------------------
# Compras/021: la devolucion no cambia la demanda ni crea desbloqueos
# ---------------------------------------------------------------------------


def test_compras_021_no_cambia_por_la_devolucion_ac_35(motor, datos_013):
    """AC-35: el caso #10 equivalente sigue omitido antes y despues de anular."""
    datos = datos_013
    producto_id = datos["producto_id"]
    sede_id = datos["sede_id"]
    bodeguero_id = datos["usuarios_inst01"]["Bodeguero"]

    # Stock 64 > minimo 10 y demanda 3 <= 64: la fila se omite (020/021).
    fijar_stock(motor, sede_id=sede_id, producto_id=producto_id, stock_actual=64)

    with cliente_rol(motor, datos, "Solicitante") as solicitante:
        ticket_id = _alta(solicitante, datos, asunto="Caso 10 equivalente (e2e)")

    with cliente_rol(motor, datos, "Administrador") as admin:
        assert _aprobar(admin, ticket_id).status_code == 200
        assert _necesidad_de(_necesidades(admin), sede_id, producto_id) is None, (
            "stock 64 > minimo 10 y demanda 3: la fila se omite, no es un fallo"
        )

    with cliente_rol(motor, datos, "Bodeguero") as bodeguero:
        retiro = _retirar(bodeguero, ticket_id, bodeguero_id)
        assert retiro.status_code == 200, retiro.text
    assert stock_de(motor, sede_id, producto_id) == 64 - CANTIDAD_PEDIDO

    with cliente_rol(motor, datos, "Administrador") as admin:
        assert _necesidad_de(_necesidades(admin), sede_id, producto_id) is None, (
            "un Cerrado no es demanda de Compras (020/021)"
        )
        anulacion = anular(admin, ticket_id, MOTIVO_ANULACION)
        assert anulacion.status_code == 200, anulacion.text

        assert _necesidad_de(_necesidades(admin), sede_id, producto_id) is None, (
            "un Anulado tampoco es demanda: la devolucion no crea necesidad"
        )
        assert contar_en(motor, "OrdenCompraTicket") == 0, (
            "la devolucion no crea filas de desbloqueo ni de plan de compra"
        )
        assert contar_en(motor, "OrdenCompra") == 0

    assert stock_de(motor, sede_id, producto_id) == 64
