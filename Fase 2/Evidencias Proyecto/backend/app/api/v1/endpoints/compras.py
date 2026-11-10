"""Endpoints del reabastecimiento externo y compras (Features 020 y 021).

Diez operaciones aditivas de la matriz central (62 -> 72) de la Feature 020 y
una mas de la 021 (`POST /compras/cobertura/preview`, 72 -> 73), todas gateadas
por la septima capacidad institucional `compras` (plan §4):

* Administrador Institucional: necesidades, alta de OC, edicion, emision,
  factura, cancelacion y listado institucional.
* Bodeguero: panel de recepciones (solo OC `Facturada` de su sede) y
  confirmacion de la recepcion fisica.
* Superadmin: lectura y alta del catalogo global de proveedores en `control`.

Las dos sesiones (`db_control` y `db_negocio`) son dependencias distintas: el
catalogo de proveedores vive en `control` y las ordenes/facturas en el tenant.
En SQLite ambas resuelven al mismo contexto logico; en PostgreSQL cada una abre
su propio esquema. La precedencia de errores es 401 -> 403 matriz -> 403
capacidad -> 409 (Bodeguero sin sede) -> 404 (recurso ajeno/inexistente).
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api import dependencies
from app.schemas.compra_schema import (
    CancelacionOrdenCompra,
    CoberturaPreviewRespuesta,
    CoberturaPreviewSolicitud,
    FacturaCompraRegistrar,
    FacturaCompraRespuesta,
    NecesidadReabastecimiento,
    OrdenCompraActualizar,
    OrdenCompraCrear,
    OrdenCompraRespuesta,
    ProveedorCrear,
    ProveedorRespuesta,
    RecepcionRespuesta,
)
from app.services import compra_service
from app.services.auth_service import IdentidadAutenticada

router = APIRouter(prefix="/compras", tags=["Compras y Reabastecimiento"])


# ---------------------------------------------------------------------------
# AC-1: necesidades de abastecimiento
# ---------------------------------------------------------------------------


@router.get(
    "/necesidades",
    response_model=List[NecesidadReabastecimiento],
    status_code=status.HTTP_200_OK,
    summary="Consultar las necesidades de reabastecimiento",
    description=(
        "Consolida por `(sede, producto)` los productos activos en nivel critico "
        "o cuya demanda `EnCurso` supera el stock de la sede. `sugerido` se "
        "calcula como `max(0, stock_minimo + demanda_en_curso - stock_actual)`.\n\n"
        "`sede_id` es un filtro de lista: una sede inexistente o ajena devuelve "
        "`200` con `[]`, nunca 404. Solo el Administrador Institucional de la "
        "institucion consulta este consolidado.\n\n"
        "**Feature 020 (AC-1).**"
    ),
    responses=dependencies.respuestas_de_autorizacion(),
    dependencies=[
        Depends(
            dependencies.requiere_capacidad("GET", "/api/v1/compras/necesidades")
        )
    ],
)
def listar_necesidades_reabastecimiento(
    sede_id: Optional[int] = Query(
        default=None, ge=1, description="Filtro opcional por sede de la institucion."
    ),
    identidad: IdentidadAutenticada = Depends(
        dependencies.requiere_operacion("GET", "/api/v1/compras/necesidades")
    ),
    db: Session = Depends(dependencies.get_db_negocio),
) -> List[NecesidadReabastecimiento]:
    institucion_id = compra_service.institucion_de_compras(db, identidad)
    return compra_service.listar_necesidades_reabastecimiento(
        db, institucion_id, sede_id
    )


# ---------------------------------------------------------------------------
# AC-2: preview de cobertura automatica
# ---------------------------------------------------------------------------


@router.post(
    "/cobertura/preview",
    response_model=CoberturaPreviewRespuesta,
    status_code=status.HTTP_200_OK,
    summary="Simular la cobertura automatica de una compra",
    description=(
        "Simula el plan de cobertura de una compra hipotetica para una sede: "
        "reparte la cantidad por producto entre los pedidos `EnCurso` por "
        "prioridad y FIFO, despues del stock parcial y de los planes pendientes "
        "(`Emitida` + `Facturada`). No persiste filas, no reserva stock y no "
        "cambia el estado de ningun pedido; con el mismo estado devuelve el "
        "mismo resultado.\n\n"
        "La sede es concreta: inexistente o ajena responde `404`. Un producto "
        "ajeno o inexistente responde `404`; inactivo o repetido, `409`. Solo "
        "el Administrador Institucional puede simular.\n\n"
        "**Feature 021 (AC-2).**"
    ),
    responses={
        **dependencies.respuestas_de_autorizacion(),
        **dependencies.respuesta_recurso_oculto(),
        **dependencies.respuesta_conflicto(),
    },
    dependencies=[
        Depends(
            dependencies.requiere_operacion(
                "POST", "/api/v1/compras/cobertura/preview"
            )
        ),
        Depends(
            dependencies.requiere_capacidad(
                "POST", "/api/v1/compras/cobertura/preview"
            )
        ),
    ],
)
def previsualizar_cobertura(
    datos: CoberturaPreviewSolicitud,
    identidad: IdentidadAutenticada = Depends(
        dependencies.requiere_operacion("POST", "/api/v1/compras/cobertura/preview")
    ),
    db: Session = Depends(dependencies.get_db_negocio),
) -> CoberturaPreviewRespuesta:
    return compra_service.previsualizar_cobertura(db, datos, identidad)


# ---------------------------------------------------------------------------
# AC-2: catalogo global de proveedores
# ---------------------------------------------------------------------------


@router.get(
    "/proveedores",
    response_model=List[ProveedorRespuesta],
    status_code=status.HTTP_200_OK,
    summary="Listar el catalogo global de proveedores activos",
    description=(
        "Devuelve los proveedores activos de `control.proveedor`, ordenados por "
        "razon social. El catalogo es global (compartido por las instituciones); "
        "solo se listan los activos y el Administrador o el Superadmin pueden "
        "consultarlo.\n\n"
        "**Feature 020 (AC-2).**"
    ),
    responses=dependencies.respuestas_de_autorizacion(),
    dependencies=[
        Depends(
            dependencies.requiere_operacion("GET", "/api/v1/compras/proveedores")
        ),
        Depends(
            dependencies.requiere_capacidad("GET", "/api/v1/compras/proveedores")
        ),
    ],
)
def listar_proveedores(
    db_control: Session = Depends(dependencies.get_db),
) -> List[ProveedorRespuesta]:
    return [
        ProveedorRespuesta.model_validate(proveedor)
        for proveedor in compra_service.listar_proveedores(db_control)
    ]


@router.post(
    "/proveedores",
    response_model=ProveedorRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar un proveedor en el catalogo global",
    description=(
        "Da de alta un proveedor activo con RUT unico global. El Administrador "
        "Institucional escribe en `control.proveedor` y replica el registro en su "
        "tenant con el **mismo `proveedor_id`**; el Superadmin solo escribe en "
        "control y no replica (no tiene tenant operativo).\n\n"
        "Un RUT ya registrado responde `409`, incluso si otra institucion lo dio "
        "de alta. La baja/reactivacion de proveedores queda fuera de alcance.\n\n"
        "**Feature 020 (AC-2, DT-1).**"
    ),
    responses={
        **dependencies.respuestas_de_autorizacion(),
        **dependencies.respuesta_conflicto(),
    },
    dependencies=[
        Depends(
            dependencies.requiere_capacidad("POST", "/api/v1/compras/proveedores")
        )
    ],
)
def crear_proveedor(
    datos: ProveedorCrear,
    identidad: IdentidadAutenticada = Depends(
        dependencies.requiere_operacion("POST", "/api/v1/compras/proveedores")
    ),
    db_control: Session = Depends(dependencies.get_db),
    db_negocio: Session = Depends(dependencies.get_db_negocio),
) -> ProveedorRespuesta:
    return ProveedorRespuesta.model_validate(
        compra_service.crear_proveedor(
            db_control, db_negocio, datos, identidad
        )
    )


# ---------------------------------------------------------------------------
# AC-3: creacion, edicion y listado de ordenes
# ---------------------------------------------------------------------------


@router.post(
    "/ordenes",
    response_model=OrdenCompraRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Crear una orden de compra en borrador",
    description=(
        "Crea la OC y sus lineas en una sola transaccion. La institucion y el "
        "estado `Borrador` los fija el servidor; el total se calcula como la suma "
        "de `cantidad_solicitada * precio_unitario`.\n\n"
        "La sede debe pertenecer a la institucion del actor y todos los productos "
        "deben estar activos (producto y categoria). Un producto repetido o "
        "inactivo responde `409`; una sede o un proveedor inexistente responde "
        "`404`. Al crear no se toca el stock.\n\n"
        "**Feature 020 (AC-3).**"
    ),
    responses={
        **dependencies.respuestas_de_autorizacion(),
        **dependencies.respuesta_recurso_oculto(),
        **dependencies.respuesta_conflicto(),
    },
    dependencies=[
        Depends(
            dependencies.requiere_capacidad("POST", "/api/v1/compras/ordenes")
        )
    ],
)
def crear_orden_compra(
    datos: OrdenCompraCrear,
    identidad: IdentidadAutenticada = Depends(
        dependencies.requiere_operacion("POST", "/api/v1/compras/ordenes")
    ),
    db_control: Session = Depends(dependencies.get_db),
    db_negocio: Session = Depends(dependencies.get_db_negocio),
) -> OrdenCompraRespuesta:
    return compra_service.orden_a_respuesta(
        compra_service.crear_orden_compra(
            db_negocio, db_control, datos, identidad
        )
    )


@router.get(
    "/ordenes",
    response_model=List[OrdenCompraRespuesta],
    status_code=status.HTTP_200_OK,
    summary="Listar ordenes de compra segun el ambito del rol",
    description=(
        "El Administrador Institucional ve todas las OC de su institucion y puede "
        "filtrar por `estado` y `sede_id`; un filtro de sede inexistente o ajeno "
        "devuelve `[]`.\n\n"
        "El Bodeguero queda **forzado** a las OC `Facturada` de su propia sede: "
        "los query params se ignoran. Sin sede asignada responde `409`; una OC de "
        "otra sede o institucion nunca aparece en su panel.\n\n"
        "**Feature 020 (AC-3, AC-6).**"
    ),
    responses={
        **dependencies.respuestas_de_autorizacion(),
        **dependencies.respuesta_conflicto(),
    },
    dependencies=[
        Depends(
            dependencies.requiere_capacidad("GET", "/api/v1/compras/ordenes")
        )
    ],
)
def listar_ordenes_compra(
    estado: Optional[str] = Query(
        default=None,
        max_length=20,
        description=(
            "Filtro por estado (solo Administrador): Borrador, Emitida, "
            "Facturada, Recibida o Cancelada."
        ),
    ),
    sede_id: Optional[int] = Query(
        default=None,
        ge=1,
        description="Filtro por sede de la institucion (solo Administrador).",
    ),
    identidad: IdentidadAutenticada = Depends(
        dependencies.requiere_operacion("GET", "/api/v1/compras/ordenes")
    ),
    db: Session = Depends(dependencies.get_db_negocio),
) -> List[OrdenCompraRespuesta]:
    ordenes = compra_service.listar_ordenes_compra(
        db, identidad, estado=estado, sede_id=sede_id
    )
    return [compra_service.orden_a_respuesta(orden) for orden in ordenes]


@router.put(
    "/ordenes/{orden_id}",
    response_model=OrdenCompraRespuesta,
    status_code=status.HTTP_200_OK,
    summary="Editar una orden de compra en borrador",
    description=(
        "Reemplaza sede, proveedor e items **solo** si la OC esta en `Borrador`; "
        "recalcula el total y no toca stock. Las mismas validaciones de sede, "
        "proveedor y productos activos que el alta aplican aqui.\n\n"
        "Una OC `Emitida`, `Facturada`, `Recibida` o `Cancelada` responde `409`. "
        "Una OC de otra institucion se oculta como inexistente (`404`).\n\n"
        "**Feature 020 (AC-3, DT-14).**"
    ),
    responses={
        **dependencies.respuestas_de_autorizacion(),
        **dependencies.respuesta_recurso_oculto(),
        **dependencies.respuesta_conflicto(),
    },
    dependencies=[
        Depends(
            dependencies.requiere_capacidad(
                "PUT", "/api/v1/compras/ordenes/{orden_id}"
            )
        )
    ],
)
def actualizar_orden_compra(
    orden_id: int,
    datos: OrdenCompraActualizar,
    identidad: IdentidadAutenticada = Depends(
        dependencies.requiere_operacion(
            "PUT", "/api/v1/compras/ordenes/{orden_id}"
        )
    ),
    db_control: Session = Depends(dependencies.get_db),
    db_negocio: Session = Depends(dependencies.get_db_negocio),
) -> OrdenCompraRespuesta:
    return compra_service.orden_a_respuesta(
        compra_service.actualizar_orden_compra(
            db_negocio, db_control, orden_id, datos, identidad
        )
    )


# ---------------------------------------------------------------------------
# AC-4: emision formal
# ---------------------------------------------------------------------------


@router.post(
    "/ordenes/{orden_id}/emitir",
    response_model=OrdenCompraRespuesta,
    status_code=status.HTTP_200_OK,
    summary="Emitir formalmente una orden de compra",
    description=(
        "Pasa la OC de `Borrador` a `Emitida`, asigna "
        "`numero_oc = OC-{ANIO}-{orden_compra_id:06d}` y sella `fecha_emision`. "
        "No se usa `MAX + 1`, de modo que dos emisiones concurrentes no colisionan.\n\n"
        "En la misma transaccion congela el **plan de cobertura**: reparte las "
        "cantidades de la OC entre los pedidos `EnCurso` de su sede por prioridad y "
        "FIFO, despues del stock parcial y de los planes pendientes. Solo persiste "
        "filas con `cantidad_asignada > 0`; sin pedidos o sin necesidad neta el "
        "plan queda vacio.\n\n"
        "Solo se emite un borrador con items y con todos sus productos activos. "
        "Una segunda emision responde `409`; una OC ajena, `404`.\n\n"
        "**Feature 020 (AC-4, DT-7) / Feature 021 (AC-3, DT-5).**"
    ),
    responses={
        **dependencies.respuestas_de_autorizacion(),
        **dependencies.respuesta_recurso_oculto(),
        **dependencies.respuesta_conflicto(),
    },
    dependencies=[
        Depends(
            dependencies.requiere_capacidad(
                "POST", "/api/v1/compras/ordenes/{orden_id}/emitir"
            )
        )
    ],
)
def emitir_orden_compra(
    orden_id: int,
    identidad: IdentidadAutenticada = Depends(
        dependencies.requiere_operacion(
            "POST", "/api/v1/compras/ordenes/{orden_id}/emitir"
        )
    ),
    db: Session = Depends(dependencies.get_db_negocio),
) -> OrdenCompraRespuesta:
    return compra_service.orden_a_respuesta(
        compra_service.emitir_orden_compra(db, orden_id, identidad)
    )


# ---------------------------------------------------------------------------
# AC-5: factura del proveedor
# ---------------------------------------------------------------------------


@router.put(
    "/ordenes/{orden_id}/factura",
    response_model=FacturaCompraRespuesta,
    status_code=status.HTTP_200_OK,
    summary="Registrar o corregir la factura de una orden emitida",
    description=(
        "Crea la factura y pasa la OC a `Facturada` cuando esta en `Emitida`; en "
        "`Facturada` corrige los metadatos de la misma factura. El numero es unico "
        "por proveedor (`UNIQUE(proveedor_id, numero_factura)`).\n\n"
        "Una OC en `Borrador`, `Recibida` o `Cancelada` responde `409`; un numero "
        "duplicado del mismo proveedor, `409`; una fecha futura, `422`. Una OC "
        "ajena se oculta con `404`.\n\n"
        "**Feature 020 (AC-5, DT-10).**"
    ),
    responses={
        **dependencies.respuestas_de_autorizacion(),
        **dependencies.respuesta_recurso_oculto(),
        **dependencies.respuesta_conflicto(),
    },
    dependencies=[
        Depends(
            dependencies.requiere_capacidad(
                "PUT", "/api/v1/compras/ordenes/{orden_id}/factura"
            )
        )
    ],
)
def registrar_o_editar_factura(
    orden_id: int,
    datos: FacturaCompraRegistrar,
    identidad: IdentidadAutenticada = Depends(
        dependencies.requiere_operacion(
            "PUT", "/api/v1/compras/ordenes/{orden_id}/factura"
        )
    ),
    db: Session = Depends(dependencies.get_db_negocio),
) -> FacturaCompraRespuesta:
    return FacturaCompraRespuesta.model_validate(
        compra_service.registrar_o_editar_factura(
            db, orden_id, datos, identidad
        )
    )


# ---------------------------------------------------------------------------
# AC-7…AC-11: recepcion fisica
# ---------------------------------------------------------------------------


@router.post(
    "/ordenes/{orden_id}/recepcion",
    response_model=RecepcionRespuesta,
    status_code=status.HTTP_200_OK,
    summary="Confirmar la recepcion fisica de una orden facturada",
    description=(
        "Confirma la llegada total de la mercaderia **sin cantidades en el "
        "cuerpo**: usa `detalle_orden_compra.cantidad_solicitada`. En una sola "
        "transaccion incrementa `stock_sede` (crea la fila si falta), escribe un "
        "`movimiento_inventario` `ENTRADA` por detalle con la referencia OC / "
        "factura / Bodeguero, sella `fecha_recepcion` y pasa la OC a `Recibida`.\n\n"
        "Calcula la cobertura de tickets `EnCurso` antes y despues: los tickets "
        "que pasan a cubiertos se devuelven en `tickets_desbloqueados` y dejan una "
        "fila de historial con `estado_origen = estado_destino = EnCurso`; el "
        "estado del ticket no cambia.\n\n"
        "Solo el Bodeguero de la sede destino recepciona. Una OC no `Facturada` o "
        "ya recepcionada responde `409`; una OC de otra sede o institucion, `404`; "
        "un Bodeguero sin sede, `409`. Un producto desactivado **despues** de la "
        "emision se recepciona y queda auditado.\n\n"
        "**Feature 020 (AC-7…AC-11, DT-11).**"
    ),
    responses={
        **dependencies.respuestas_de_autorizacion(),
        **dependencies.respuesta_recurso_oculto(),
        **dependencies.respuesta_conflicto(),
    },
    dependencies=[
        Depends(
            dependencies.requiere_capacidad(
                "POST", "/api/v1/compras/ordenes/{orden_id}/recepcion"
            )
        )
    ],
)
def recepcionar_orden_compra(
    orden_id: int,
    identidad: IdentidadAutenticada = Depends(
        dependencies.requiere_operacion(
            "POST", "/api/v1/compras/ordenes/{orden_id}/recepcion"
        )
    ),
    db: Session = Depends(dependencies.get_db_negocio),
) -> RecepcionRespuesta:
    return compra_service.recepcionar_orden_compra(db, orden_id, identidad)


# ---------------------------------------------------------------------------
# AC-12: cancelacion
# ---------------------------------------------------------------------------


@router.post(
    "/ordenes/{orden_id}/cancelar",
    response_model=OrdenCompraRespuesta,
    status_code=status.HTTP_200_OK,
    summary="Cancelar una orden de compra en borrador o emitida",
    description=(
        "Cancela una OC en `Borrador` o `Emitida` con un motivo obligatorio y "
        "persiste `motivo_cancelacion`, `fecha_cancelacion` y el usuario actor. No "
        "modifica stock ni facturas.\n\n"
        "El **plan de cobertura** de una OC `Emitida` se conserva como auditoria, "
        "pero deja de sumar en la cobertura activa: el pedido vuelve a ser "
        "asignable por otra OC.\n\n"
        "Una OC `Facturada`, `Recibida` o `Cancelada` responde `409`; un motivo "
        "vacio, `422`; una OC ajena, `404`.\n\n"
        "**Feature 020 (AC-12, DT-12) / Feature 021 (AC-7).**"
    ),
    responses={
        **dependencies.respuestas_de_autorizacion(),
        **dependencies.respuesta_recurso_oculto(),
        **dependencies.respuesta_conflicto(),
    },
    dependencies=[
        Depends(
            dependencies.requiere_capacidad(
                "POST", "/api/v1/compras/ordenes/{orden_id}/cancelar"
            )
        )
    ],
)
def cancelar_orden_compra(
    orden_id: int,
    datos: CancelacionOrdenCompra,
    identidad: IdentidadAutenticada = Depends(
        dependencies.requiere_operacion(
            "POST", "/api/v1/compras/ordenes/{orden_id}/cancelar"
        )
    ),
    db: Session = Depends(dependencies.get_db_negocio),
) -> OrdenCompraRespuesta:
    return compra_service.orden_a_respuesta(
        compra_service.cancelar_orden_compra(db, orden_id, datos, identidad)
    )
