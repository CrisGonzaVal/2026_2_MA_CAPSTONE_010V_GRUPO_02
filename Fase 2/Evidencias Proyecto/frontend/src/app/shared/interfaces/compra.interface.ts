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
 * Fila consolidada por `(sede, producto)` de `GET /compras/necesidades`.
 *
 * `sugerido = max(0, stock_minimo + demanda_tickets - stock_actual)`; la formula
 * la calcula el servidor y la vista solo la muestra.
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
