import { HttpErrorResponse } from '@angular/common/http';

/** Un error de validación de FastAPI, con su ubicación y su tipo estable. */
export interface DetalleError422 {
  loc: (string | number)[];
  msg: string;
  type: string;
}

const CAMPOS_LEGIBLES: Record<string, string> = {
  activo: 'Activo',
  apellido: 'Apellido',
  apellido_administrador: 'Apellido del administrador',
  asunto: 'Asunto',
  cantidad: 'Cantidad',
  cantidad_solicitada: 'Cantidad',
  categoria_id: 'Categoría',
  correo: 'Correo',
  correo_administrador: 'Correo administrador',
  departamento_id: 'Departamento',
  departamento_nombre_administrativo: 'Departamento administrativo',
  descripcion: 'Descripción',
  detalles: 'Detalles',
  direccion: 'Dirección',
  estado_id: 'Estado',
  fecha_factura: 'Fecha de factura',
  giro: 'Giro',
  institucion_id: 'Institución',
  items: 'Ítems',
  monto_total: 'Monto total',
  motivo_cancelacion: 'Motivo de cancelación',
  nombre: 'Nombre',
  nombre_administrador: 'Nombre del administrador',
  nombre_dep: 'Nombre del departamento',
  nombre_fantasia: 'Nombre de fantasía',
  numero_factura: 'Número de factura',
  observacion: 'Observación',
  observaciones: 'Observaciones',
  prioridad_id: 'Prioridad',
  producto_id: 'Producto',
  proveedor_id: 'Proveedor',
  razon_social: 'Razón social',
  rol_id: 'Rol',
  rut: 'RUT',
  sede_id: 'Sede',
  stock_minimo: 'Stock mínimo',
  stock_sede_id: 'Stock de sede',
  telefono: 'Teléfono',
  tipo_movimiento: 'Tipo de movimiento',
  unidad_medida: 'Unidad de medida',
  usuario_id: 'Usuario',
};

function esDetalle(valor: unknown): valor is DetalleError422 {
  if (typeof valor !== 'object' || valor === null) {
    return false;
  }
  const candidato = valor as Record<string, unknown>;
  const loc = candidato['loc'];
  return (
    Array.isArray(loc) &&
    loc.every((parte) => typeof parte === 'string' || typeof parte === 'number') &&
    typeof candidato['msg'] === 'string' &&
    typeof candidato['type'] === 'string'
  );
}

/** Detalles estructurados de un 422; cualquier otra forma devuelve `[]`. */
export function detallesDeValidacion(error: HttpErrorResponse): DetalleError422[] {
  if (error.status !== 422) {
    return [];
  }
  const detalle = (error.error as { detail?: unknown } | null)?.detail;
  return Array.isArray(detalle) ? detalle.filter(esDetalle) : [];
}

function cantidadDe(msg: string, porDefecto: number): number {
  const encontrado = msg.match(/(-?\d+(?:\.\d+)?)/)?.[0];
  return encontrado === undefined ? porDefecto : Number(encontrado);
}

/** Traduce el mensaje de Pydantic manteniendo el contrato en español. */
export function traducirMensajeValidacion(detalle: DetalleError422): string {
  switch (detalle.type) {
    case 'string_too_short':
      return `Debe tener al menos ${cantidadDe(detalle.msg, 3)} caracteres.`;
    case 'string_too_long':
      return `No puede superar los ${cantidadDe(detalle.msg, 150)} caracteres.`;
    case 'missing':
      return 'Este campo es obligatorio.';
    case 'greater_than':
      return `Debe ser mayor que ${cantidadDe(detalle.msg, 0)}.`;
    case 'greater_than_equal':
      return `Debe ser mayor o igual que ${cantidadDe(detalle.msg, 1)}.`;
    case 'less_than':
      return `Debe ser menor que ${cantidadDe(detalle.msg, 0)}.`;
    case 'less_than_equal':
      return `Debe ser menor o igual que ${cantidadDe(detalle.msg, 0)}.`;
    case 'literal_error':
      return 'Debe ser uno de los valores permitidos.';
    case 'extra_forbidden':
      return 'Este campo no está permitido.';
    case 'int_parsing':
    case 'int_type':
      return 'Debe ser un número entero.';
    case 'decimal_parsing':
      return 'Debe ser un número decimal válido.';
    case 'date_parsing':
      return 'Debe ser una fecha válida.';
    case 'bool_parsing':
      return 'Debe ser verdadero o falso.';
    case 'string_type':
      return 'Debe ser texto.';
    case 'too_short':
      return 'Agrega al menos un ítem.';
    case 'value_error': {
      const texto = detalle.msg.replace(/^Value error,\s*/i, '').trim();
      if (/email/i.test(texto)) {
        return 'El correo no tiene un formato válido.';
      }
      return texto || 'Revisa este valor.';
    }
    default:
      return 'Revisa este valor.';
  }
}

function campoLegible(campo: string): string {
  if (campo === '' || campo === 'body' || campo === '__root__') {
    return '';
  }
  const conocido = CAMPOS_LEGIBLES[campo];
  if (conocido !== undefined) {
    return conocido;
  }
  const humano = campo.replaceAll('_', ' ').trim();
  return humano === '' ? '' : humano.charAt(0).toUpperCase() + humano.slice(1);
}

/** Mensaje por campo para un control concreto, sin prefijar su etiqueta. */
export function mensajeDeCampo(
  detalles: DetalleError422[],
  campo: string,
): string | null {
  const encontrado = detalles.find((detalle) => detalle.loc.at(-1) === campo);
  return encontrado === undefined
    ? null
    : traducirMensajeValidacion(encontrado);
}

/** Mensaje del campo dentro de una fila concreta de una lista anidada. */
export function mensajeDeDetalle(
  detalles: DetalleError422[],
  indice: number,
  campo: string,
): string | null {
  const encontrado = detalles.find(
    (detalle) =>
      detalle.loc.at(-2) === indice && detalle.loc.at(-1) === campo,
  );
  return encontrado === undefined
    ? null
    : traducirMensajeValidacion(encontrado);
}

/** Primer mensaje de validación con etiqueta del campo y número de fila. */
export function mensajeDeValidacion(error: HttpErrorResponse): string | null {
  const detalles = detallesDeValidacion(error);
  if (detalles.length === 0) {
    return null;
  }

  const primero = detalles[0];
  const mensaje = traducirMensajeValidacion(primero);
  const campo = primero.loc.at(-1);
  const fila = primero.loc.at(-2);
  const etiqueta = typeof campo === 'string' ? campoLegible(campo) : '';
  const prefijoFila = typeof fila === 'number' ? `Fila ${fila + 1}: ` : '';
  return etiqueta === ''
    ? `${prefijoFila}${mensaje}`
    : `${prefijoFila}${etiqueta}: ${mensaje}`;
}
