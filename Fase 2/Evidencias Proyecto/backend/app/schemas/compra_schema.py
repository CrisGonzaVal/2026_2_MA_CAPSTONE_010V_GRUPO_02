"""Contratos Pydantic v2 del reabastecimiento externo y compras (Features 020 y 021).

La Feature 020 define proveedores, orden de compra, factura, recepcion y
necesidades. La Feature 021 (cobertura automatica de pedidos) agrega los DTO de
lectura de necesidades enriquecidas, preview de cobertura, plan de la OC y
asignaciones del pedido. Diseno en
`docs/spec/features/020-reabastecimiento-compras/plan.md` (DT-1, DT-2, DT-10,
DT-12 y DT-13) y `docs/spec/features/021-cobertura-automatica-tickets-compras/plan.md`
(DT-2…DT-8), con criterios en las `spec.md` respectivas.

Convenciones del proyecto:

* Solo sintaxis Pydantic v2 (`ConfigDict`, `model_validate`); nunca `class Config`.
* `from_attributes=True` **solo** en los DTO que proyectan una entidad ORM. Los
  read models que cruzan tablas o agregan (`NecesidadReabastecimiento`,
  `CoberturaPreviewRespuesta`, `PlanOrdenCompraRespuesta`,
  `RecepcionRespuesta` y sus partes) se arman a mano en `compra_service`.
* La validacion de forma vive aqui; la de referencias, estado y pertenencia vive
  en el servicio para conservar la precedencia 401 → 403 → 409 → 404 → 422.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.schemas.organizacion_schema import SedeRespuesta
from app.schemas.producto_schema import ProductoRespuesta

# ---------------------------------------------------------------------------
# Proveedores (AC-2, DT-1)
# ---------------------------------------------------------------------------


class ProveedorCrear(BaseModel):
    """Alta de un proveedor en el catalogo global `control.proveedor`.

    El RUT es unico **global**: el servicio responde 409 si ya existe, incluso
    si la institucion del actor no lo habia usado. El proveedor nace activo; la
    baja/reactivacion queda fuera de alcance (spec §9.1).
    """

    rut: str = Field(
        min_length=1,
        max_length=20,
        description="RUT del proveedor. Unico en el catalogo global.",
    )
    razon_social: str = Field(
        min_length=1,
        max_length=150,
        description="Razon social no vacia.",
    )
    nombre_fantasia: Optional[str] = Field(default=None, max_length=100)
    giro: Optional[str] = Field(default=None, max_length=100)
    correo: Optional[EmailStr] = Field(default=None, max_length=100)
    telefono: Optional[str] = Field(default=None, max_length=20)


class ProveedorRespuesta(BaseModel):
    """Proyeccion de `control.proveedor` o de su replica tenant."""

    model_config = ConfigDict(from_attributes=True)

    proveedor_id: int
    rut: str
    razon_social: str
    nombre_fantasia: Optional[str] = None
    giro: Optional[str] = None
    correo: Optional[str] = None
    telefono: Optional[str] = None
    activo: bool = True


# ---------------------------------------------------------------------------
# Necesidades de reabastecimiento (AC-1)
# ---------------------------------------------------------------------------


class NecesidadTicketRespuesta(BaseModel):
    """Pedido `EnCurso` que compone la demanda de una necesidad (Feature 021).

    Read model de DT-3: lo arma
    `compra_service.listar_necesidades_reabastecimiento` con la simulacion de
    necesidad neta parcial. `cantidad_cubierta = cantidad_solicitada -
    cantidad_faltante`; el faltante es la necesidad neta **antes** de una nueva
    OC, ya descontados los planes pendientes y el stock parcial.
    """

    ticket_id: int
    asunto: str
    solicitante_nombre: Optional[str] = None
    solicitante_apellido: Optional[str] = None
    solicitante_correo: Optional[str] = None
    prioridad_nombre: Optional[str] = None
    fecha_creacion: datetime
    cantidad_solicitada: int
    cantidad_cubierta: int
    cantidad_faltante: int


class NecesidadReabastecimiento(BaseModel):
    """Fila consolidada por `(sede, producto)` de `GET /compras/necesidades`.

    Read model: lo arma `compra_service.listar_necesidades_reabastecimiento`.
    `demanda_tickets` es la suma de `detalle_ticket.cantidad_solicitada` de los
    pedidos `EnCurso` de la sede. La Feature 021 agrega el comprometido por OC
    (`Emitida` + `Facturada`), el borrador (informativo, no descuenta) y los
    pedidos que componen la demanda; el sugerido pasa a
    `max(0, stock_minimo + demanda_tickets - stock_actual - stock_comprometido)`.
    """

    sede_id: int
    sede_nombre: str
    producto_id: int
    nombre: str
    stock_actual: int
    stock_minimo: int
    demanda_tickets: int
    sugerido: int
    stock_comprometido: int = 0
    stock_borrador: int = 0
    tickets: List[NecesidadTicketRespuesta] = []


# ---------------------------------------------------------------------------
# Preview de cobertura automatica (AC-2, DT-4)
# ---------------------------------------------------------------------------


class CoberturaPreviewItem(BaseModel):
    """Linea simulada del preview: producto y cantidad de la compra hipotetica."""

    producto_id: int = Field(ge=1, description="Producto activo de la institucion.")
    cantidad_solicitada: int = Field(
        gt=0, description="Unidades simuladas para ese producto; mayor que cero."
    )


class CoberturaPreviewSolicitud(BaseModel):
    """Payload de `POST /compras/cobertura/preview` (AC-2).

    No incluye proveedor: la cobertura depende de la sede, los pedidos y el
    stock, no de a quien se compra. La sede se valida en el servicio (404 si no
    existe o es ajena); la forma del cuerpo se valida aqui (422).
    """

    sede_id: int = Field(ge=1, description="Sede de la institucion del actor.")
    items: List[CoberturaPreviewItem] = Field(
        min_length=1,
        description="Al menos una linea; el servicio rechaza productos repetidos.",
    )


class CoberturaPreviewTicket(BaseModel):
    """Resultado simulado por pedido dentro de un producto del preview."""

    ticket_id: int
    asunto: str
    solicitante_nombre: Optional[str] = None
    solicitante_apellido: Optional[str] = None
    prioridad_nombre: Optional[str] = None
    fecha_creacion: datetime
    solicitado: int
    cubierto_plan: int
    cubierto_stock: int
    necesidad: int
    asignada: int
    faltante: int
    cobertura: str = Field(
        description="`total`, `parcial` o `sin_cobertura` (AC-9)."
    )


class CoberturaPreviewProducto(BaseModel):
    """Resultado simulado por producto del preview (AC-2)."""

    producto_id: int
    producto_nombre: str
    cantidad_simulada: int
    demanda_total: int
    cubierto_previo: int
    asignado: int
    faltante: int
    sin_asignar: int
    tickets: List[CoberturaPreviewTicket] = []


class CoberturaPreviewRespuesta(BaseModel):
    """Respuesta de `POST /compras/cobertura/preview`: no persiste ni reserva."""

    sede_id: int
    sede_nombre: str
    productos: List[CoberturaPreviewProducto] = []


# ---------------------------------------------------------------------------
# Orden de compra (AC-3/AC-4)
# ---------------------------------------------------------------------------


class DetalleOrdenCompraCrear(BaseModel):
    """Linea de una OC. La cantidad es una peticion, no una recepcion."""

    producto_id: int = Field(ge=1, description="Producto activo de la institucion.")
    cantidad_solicitada: int = Field(
        gt=0, description="Unidades pedidas. Debe ser mayor que cero."
    )
    precio_unitario: Decimal = Field(
        default=Decimal("0"),
        ge=0,
        max_digits=10,
        decimal_places=2,
        description="Costo estimado por unidad; no negativo.",
    )


class OrdenCompraCrear(BaseModel):
    """Payload de `POST /compras/ordenes` (AC-3).

    La institucion y el estado `Borrador` los fija el servidor; el cliente solo
    elige sede, proveedor e items.
    """

    sede_id: int = Field(ge=1, description="Sede de destino de la institucion.")
    proveedor_id: int = Field(ge=1, description="Proveedor activo del catalogo global.")
    items: List[DetalleOrdenCompraCrear] = Field(
        min_length=1,
        description="Al menos una linea; sin productos repetidos.",
    )


class OrdenCompraActualizar(BaseModel):
    """Payload de `PUT /compras/ordenes/{id}`: reemplazo completo del borrador.

    Solo se acepta en estado `Borrador`; el servicio recalcula el total y no
    toca inventario (AC-3, DT-14).
    """

    sede_id: int = Field(ge=1)
    proveedor_id: int = Field(ge=1)
    items: List[DetalleOrdenCompraCrear] = Field(min_length=1)


class DetalleOrdenCompraRespuesta(BaseModel):
    """Proyeccion de `detalle_orden_compra` con su producto resuelto."""

    model_config = ConfigDict(from_attributes=True)

    detalle_orden_compra_id: int
    orden_compra_id: int
    producto_id: int
    cantidad_solicitada: int
    precio_unitario: Decimal
    producto: Optional[ProductoRespuesta] = None


class PlanOrdenCompraRespuesta(BaseModel):
    """Fila del plan congelado de cobertura de una OC (Feature 021, AC-4).

    Read model construido por `compra_service.orden_a_respuesta`: resuelve el
    resumen del pedido y el nombre del producto en el servicio, porque no son
    columnas de `orden_compra_ticket`. `cantidad_faltante` es la foto del hueco
    que esta OC dejo al emitirse; no se recalcula.
    """

    model_config = ConfigDict(from_attributes=True)

    orden_compra_ticket_id: int
    orden_compra_id: int
    ticket_id: int
    producto_id: int
    cantidad_asignada: int
    cantidad_faltante: int
    fecha_asignacion: datetime
    asunto: Optional[str] = None
    estado_nombre: Optional[str] = None
    prioridad_nombre: Optional[str] = None
    solicitante_nombre: Optional[str] = None
    solicitante_apellido: Optional[str] = None
    fecha_creacion: Optional[datetime] = None
    producto_nombre: Optional[str] = None


class OrdenCompraRespuesta(BaseModel):
    """Proyeccion completa de una OC con proveedor, sede, detalles y factura."""

    model_config = ConfigDict(from_attributes=True)

    orden_compra_id: int
    numero_oc: Optional[str] = None
    institucion_id: str
    sede_id: int
    proveedor_id: int
    estado: str
    total: Decimal
    motivo_cancelacion: Optional[str] = None
    cancelado_por_usuario_id: Optional[int] = None
    fecha_creacion: datetime
    fecha_emision: Optional[datetime] = None
    fecha_recepcion: Optional[datetime] = None
    fecha_cancelacion: Optional[datetime] = None
    proveedor: Optional[ProveedorRespuesta] = None
    sede: Optional[SedeRespuesta] = None
    detalles: List[DetalleOrdenCompraRespuesta] = []
    factura: Optional["FacturaCompraRespuesta"] = None
    #: Feature 021: plan congelado al emitir. Vacio en `Borrador`.
    plan: List[PlanOrdenCompraRespuesta] = []


# ---------------------------------------------------------------------------
# Factura del proveedor (AC-5, DT-10)
# ---------------------------------------------------------------------------


class FacturaCompraRegistrar(BaseModel):
    """Payload de `PUT /compras/ordenes/{id}/factura`.

    El proveedor y la orden salen de la OC; `numero_factura` es unico por
    proveedor. La fecha no futura se valida en el servicio para responder 422
    sin adelantarse al 404/409 de la orden.
    """

    numero_factura: str = Field(min_length=1, max_length=50)
    fecha_factura: date = Field(description="Fecha de emision de la factura.")
    monto_total: Decimal = Field(
        gt=0, max_digits=12, decimal_places=2, description="Monto total; mayor que cero."
    )
    observaciones: Optional[str] = Field(default=None, max_length=500)


class FacturaCompraRespuesta(BaseModel):
    """Proyeccion de `factura_compra`."""

    model_config = ConfigDict(from_attributes=True)

    factura_compra_id: int
    orden_compra_id: int
    proveedor_id: int
    numero_factura: str
    fecha_factura: date
    monto_total: Decimal
    observaciones: Optional[str] = None
    fecha_registro: datetime


# ---------------------------------------------------------------------------
# Cancelacion de la orden (AC-12)
# ---------------------------------------------------------------------------


class CancelacionOrdenCompra(BaseModel):
    """Payload de `POST /compras/ordenes/{id}/cancelar`.

    El motivo es obligatorio (texto no vacio, hasta 500 caracteres); el actor y
    la fecha los fija el servidor a partir de la sesion (AC-12).
    """

    motivo_cancelacion: str = Field(
        min_length=1,
        max_length=500,
        description="Motivo obligatorio de la cancelacion.",
    )


OrdenCompraRespuesta.model_rebuild()


# ---------------------------------------------------------------------------
# Recepcion fisica (AC-7…AC-11)
# ---------------------------------------------------------------------------


class MovimientoRecepcionRespuesta(BaseModel):
    """Movimiento `ENTRADA` generado por la recepcion de una OC.

    Read model compacto para la confirmacion de bodega: no repite la proyeccion
    historica de `GET /inventario/movimientos`, pero conserva las referencias de
    auditoria (`movimiento_id`, `stock_sede_id`) y el saldo resultante.
    """

    movimiento_id: int
    producto_id: int
    producto_nombre: str
    cantidad: int
    stock_sede_id: int
    stock_actual: int
    observacion: str


class TicketDesbloqueadoRespuesta(BaseModel):
    """Ticket que paso de no cubierto a cubierto con la recepcion (AC-10)."""

    ticket_id: int
    asunto: str


class RecepcionRespuesta(BaseModel):
    """Resultado de `POST /compras/ordenes/{id}/recepcion` (sin cantidades en el body).

    `movimientos` son las entradas de auditoria creadas y `tickets_desbloqueados`
    los tickets que quedaron con `stock_disponible = true` despues del incremento
    (AC-9/AC-10). El estado del ticket no cambia.
    """

    orden: OrdenCompraRespuesta
    estado: str
    fecha_recepcion: datetime
    movimientos: List[MovimientoRecepcionRespuesta] = []
    tickets_desbloqueados: List[TicketDesbloqueadoRespuesta] = []
