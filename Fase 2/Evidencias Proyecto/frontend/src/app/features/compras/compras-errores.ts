import { HttpErrorResponse } from '@angular/common/http';

/**
 * Mensaje legible de un fallo del reabastecimiento y compras (Feature 020, T8).
 *
 * Prefiere el `detail` textual del backend (404 oculto, 409 de estado o
 * duplicado, 422 de fecha/motivo) y, si no es texto (p. ej. el arreglo de
 * errores de validación de Pydantic), recurre a un mensaje por código. Vive
 * fuera de los componentes para que las tres vistas de Administrador y la de
 * Bodega compartan el mismo criterio.
 */
export function mensajeDeErrorCompras(error: HttpErrorResponse): string {
  const detalle = (error.error as { detail?: unknown } | null)?.detail;
  if (typeof detalle === 'string' && detalle.trim() !== '') {
    return detalle;
  }
  switch (error.status) {
    case 401:
      return 'Tu sesión no es válida. Vuelve a iniciar sesión.';
    case 403:
      return 'Tu rol no tiene permiso para operar compras.';
    case 404:
      return 'La orden, sede o proveedor no existe o no pertenece a tu institución.';
    case 409:
      return 'La operación entra en conflicto con el estado actual de la orden.';
    case 422:
      return 'Los datos enviados no son válidos: revisa cantidades, precios, fechas y el motivo.';
    case 0:
      return 'No se pudo contactar al servidor. Verifica la conexión e inténtalo de nuevo.';
    default:
      return `No se pudo completar la operación (HTTP ${error.status}).`;
  }
}
