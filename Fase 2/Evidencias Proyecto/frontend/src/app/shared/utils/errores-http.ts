import { HttpErrorResponse } from '@angular/common/http';

/** Texto único para una caída de red o un servidor inalcanzable (`status === 0`). */
const SIN_CONEXION =
  'No se pudo contactar al servidor. Verifica la conexión e inténtalo de nuevo.';

/**
 * Tabla de textos de un dominio para `mensajeDeErrorHttp`.
 *
 * Cada feature aporta solo sus mensajes visibles; la estructura común —preferir
 * el `detail` textual del backend, tratar el status 0 y caer al mensaje por
 * defecto— vive en el helper compartido.
 */
export interface MensajesDeErrorHttp {
  readonly 401: string;
  readonly 403: string;
  readonly 404: string;
  readonly 409: string;
  readonly 422: string;
  readonly 503?: string;
  readonly predeterminado: (estado: number) => string;
}

/**
 * Mensaje legible de un fallo HTTP, con los textos propios de cada dominio.
 *
 * Prefiere el `detail` textual del backend y lo devuelve sin transformarlo. Si
 * no es texto (p. ej. la lista de validación de Pydantic) o está vacío, mapea el
 * código de estado con la tabla recibida; el status 0 se explica siempre como
 * servidor inalcanzable.
 */
export function mensajeDeErrorHttp(
  error: HttpErrorResponse,
  mensajes: MensajesDeErrorHttp,
): string {
  const detalle = (error.error as { detail?: unknown } | null)?.detail;
  if (typeof detalle === 'string' && detalle.trim() !== '') {
    return detalle;
  }
  switch (error.status) {
    case 401:
      return mensajes[401];
    case 403:
      return mensajes[403];
    case 404:
      return mensajes[404];
    case 409:
      return mensajes[409];
    case 422:
      return mensajes[422];
    case 503:
      return mensajes[503] ?? mensajes.predeterminado(503);
    case 0:
      return SIN_CONEXION;
    default:
      return mensajes.predeterminado(error.status);
  }
}
