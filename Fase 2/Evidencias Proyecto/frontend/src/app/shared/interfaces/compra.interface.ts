/**
 * Tipos del reabastecimiento externo y compras (Feature 020).
 *
 * Reflejan 1:1 los schemas de `backend/app/schemas/compra_schema.py`, igual que
 * el resto de `shared/interfaces`: `snake_case` y sin normalizacion en el
 * cliente. Los importes viajan como **string** porque Pydantic serializa
 * `Decimal` en modo JSON con esa representacion (`"10.50"`); las peticiones, en
 * cambio, aceptan `number` y es el backend quien valida la escala.
 *
 * Se reexporta desde `shared/interfaces/index.ts` para conservar el punto de
 * importacion unico del repo (`from '../../../shared/interfaces'`).
 */

// Importacion **solo de tipos**: `index.ts` reexporta este archivo, y el
// modificador `type` evita un ciclo en tiempo de ejecucion.
import type { Producto, Sede } from './index';

// --- Proveedores (AC-2, DT-1) ----------------------------------------------

export interface Proveedor {
  proveedor_id: number;
  rut: string;
  razon_social: string;
  nombre_fantasia: string | null;
  giro: string | null;
  correo: string | null;
  telefono: string | null;
  /** El catalogo solo lista activos; el alta nace activa (spec §9.1). */
  activo: boolean;
}

/** Entrada de `POST /compras/proveedores`; el RUT es unico global. */
export interface ProveedorCrear {
  rut: string;
  razon_social: string;
  nombre_fantasia?: string | null;
  giro?: string | null;
  correo?: string | null;
  telefono?: string | null;
}

// --- Necesidades de reabastecimiento (AC-1) --------------------------------

/**
 * Pedido `EnCurso` que compone la demanda de una necesidad (Feature 021).
 *
 * `cantidad_cubierta = cantidad_solicitada - cantidad_faltante`; el faltante
 * es la necesidad neta **antes** de una nueva OC, ya descontados los planes
 * pendientes y el stock parcial (DT-3).
 */
export interface NecesidadTicket {
  ticket_id: number;
  asunto: string;
  solicitante_nombre: string | null;
  solicitante_apellido: string | null;
  solicitante_correo: string | null;
  prioridad_nombre: string | null;
  fecha_creacion: string;
  cantidad_solicitada: number;
  cantidad_cubierta: number;
  cantidad_faltante: number;
}

/**
 * Fila consolidada por `(sede, producto)` de `GET /compras/necesidades`.
 *
 * Desde la Feature 021 el sugerido es neto:
 * `sugerido = max(0, stock_minimo + demanda_tickets - stock_actual -
 * stock_comprometido)`. `stock_borrador` es informativo y no descuenta.
 */
export interface NecesidadReabastecimiento {
  sede_id: number;
  sede_nombre: string;
  producto_id: number;
  nombre: string;
  stock_actual: number;
  stock_minimo: number;
  demanda_tickets: number;
  sugerido: number;
  /** Unidades en OC `Emitida` + `Facturada` (comprometidas, aun no recibidas). */
  stock_comprometido?: number;
  /** Unidades en OC `Borrador`; se muestran aparte y no descuentan el sugerido. */
  stock_borrador?: number;
  /** Pedidos `EnCurso` que componen la demanda de esta fila. */
  tickets?: NecesidadTicket[];
}

// --- Preview de cobertura automatica (AC-2, DT-4) --------------------------

/** Linea simulada del preview: producto y cantidad de la compra hipotetica. */
export interface CoberturaPreviewItem {
  producto_id: number;
  cantidad_solicitada: number;
}

/** Payload de `POST /compras/cobertura/preview` (AC-2). */
export interface CoberturaPreviewSolicitud {
  sede_id: number;
  items: CoberturaPreviewItem[];
}

/** Resultado simulado por pedido dentro de un producto del preview. */
export interface CoberturaPreviewTicket {
  ticket_id: number;
  asunto: string;
  solicitante_nombre: string | null;
  solicitante_apellido: string | null;
  prioridad_nombre: string | null;
  fecha_creacion: string;
  solicitado: number;
  cubierto_plan: number;
  cubierto_stock: number;
  necesidad: number;
  asignada: number;
  faltante: number;
  /** `total`, `parcial` o `sin_cobertura` (AC-9). */
  cobertura: 'total' | 'parcial' | 'sin_cobertura' | string;
}

/** Resultado simulado por producto del preview (AC-2). */
export interface CoberturaPreviewProducto {
  producto_id: number;
  producto_nombre: string;
  cantidad_simulada: number;
  demanda_total: number;
  cubierto_previo: number;
  asignado: number;
  faltante: number;
  sin_asignar: number;
  tickets: CoberturaPreviewTicket[];
}

/** Respuesta de `POST /compras/cobertura/preview`: no persiste ni reserva. */
export interface CoberturaPreviewRespuesta {
  sede_id: number;
  sede_nombre: string;
  productos: CoberturaPreviewProducto[];
}

// --- Orden de compra (AC-3, AC-4) ------------------------------------------

/** Estados formales del ciclo de vida de la OC (spec §4.1). */
export type EstadoOrdenCompra =
  | 'Borrador'
  | 'Emitida'
  | 'Facturada'
  | 'Recibida'
  | 'Cancelada';

/** Linea de una OC: la cantidad es una peticion, no una recepcion. */
export interface DetalleOrdenCompraCrear {
  producto_id: number;
  cantidad_solicitada: number;
  /** Costo estimado por unidad; el backend lo valida no negativo. */
  precio_unitario?: number;
}

/** Entrada de `POST /compras/ordenes` (la institucion la fija el servidor). */
export interface OrdenCompraCrear {
  sede_id: number;
  proveedor_id: number;
  items: DetalleOrdenCompraCrear[];
}

/** Entrada de `PUT /compras/ordenes/{id}`: reemplazo completo del borrador. */
export interface OrdenCompraActualizar {
  sede_id: number;
  proveedor_id: number;
  items: DetalleOrdenCompraCrear[];
}

export interface DetalleOrdenCompra {
  detalle_orden_compra_id: number;
  orden_compra_id: number;
  producto_id: number;
  cantidad_solicitada: number;
  /** `Decimal` serializado como string por el backend. */
  precio_unitario: string;
  producto: Producto | null;
}

/** Proyeccion completa de una OC con proveedor, sede, detalles y factura. */
export interface OrdenCompra {
  orden_compra_id: number;
  /** `OC-{ANIO}-{orden_compra_id:06d}`; `null` mientras esta en `Borrador`. */
  numero_oc: string | null;
  institucion_id: string;
  sede_id: number;
  proveedor_id: number;
  estado: EstadoOrdenCompra;
  /** `Decimal` serializado como string por el backend. */
  total: string;
  motivo_cancelacion: string | null;
  cancelado_por_usuario_id: number | null;
  fecha_creacion: string;
  fecha_emision: string | null;
  fecha_recepcion: string | null;
  fecha_cancelacion: string | null;
  proveedor: Proveedor | null;
  sede: Sede | null;
  detalles: DetalleOrdenCompra[];
  factura: FacturaCompra | null;
  /** Feature 021: plan congelado al emitir; vacio en `Borrador`. */
  plan?: PlanOrdenCompra[];
}

/**
 * Fila del plan congelado de cobertura de una OC (Feature 021, AC-4).
 *
 * Es una foto de la intencion al emitir: no se recalcula al facturar,
 * recepcionar o cancelar. `cantidad_faltante` es el hueco que esta OC dejo.
 */
export interface PlanOrdenCompra {
  orden_compra_ticket_id: number;
  orden_compra_id: number;
  ticket_id: number;
  producto_id: number;
  cantidad_asignada: number;
  cantidad_faltante: number;
  fecha_asignacion: string;
  asunto: string | null;
  estado_nombre: string | null;
  prioridad_nombre: string | null;
  solicitante_nombre: string | null;
  solicitante_apellido: string | null;
  fecha_creacion: string | null;
  producto_nombre: string | null;
}

/** Filtros de lista de `GET /compras/ordenes` (solo Administrador). */
export interface FiltrosOrdenesCompra {
  estado?: EstadoOrdenCompra | null;
  sede_id?: number | null;
}

// --- Factura del proveedor (AC-5, DT-10) -----------------------------------

/** Entrada de `PUT /compras/ordenes/{id}/factura`. */
export interface FacturaCompraRegistrar {
  numero_factura: string;
  /** Fecha ISO (`YYYY-MM-DD`); no puede ser futura. */
  fecha_factura: string;
  monto_total: number;
  observaciones?: string | null;
}

export interface FacturaCompra {
  factura_compra_id: number;
  orden_compra_id: number;
  proveedor_id: number;
  numero_factura: string;
  fecha_factura: string;
  /** `Decimal` serializado como string por el backend. */
  monto_total: string;
  observaciones: string | null;
  fecha_registro: string;
}

// --- Recepcion fisica (AC-7…AC-11) -----------------------------------------

/** Movimiento `ENTRADA` generado por la recepcion de una OC. */
export interface MovimientoRecepcion {
  movimiento_id: number;
  producto_id: number;
  producto_nombre: string;
  cantidad: number;
  stock_sede_id: number;
  stock_actual: number;
  observacion: string;
}

/** Ticket que paso a estar cubierto con la recepcion (AC-10). */
export interface TicketDesbloqueado {
  ticket_id: number;
  asunto: string;
}

/** Respuesta de `POST /compras/ordenes/{id}/recepcion`, sin body de entrada. */
export interface RecepcionRespuesta {
  orden: OrdenCompra;
  estado: EstadoOrdenCompra;
  fecha_recepcion: string;
  movimientos: MovimientoRecepcion[];
  tickets_desbloqueados: TicketDesbloqueado[];
}
