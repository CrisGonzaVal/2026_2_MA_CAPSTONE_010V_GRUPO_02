import { HttpErrorResponse } from '@angular/common/http';

import {
  MensajesDeErrorHttp,
  mensajeDeErrorHttp,
} from '../../shared/utils/errores-http';

const MENSAJES_COMPRAS: MensajesDeErrorHttp = {
  401: 'Tu sesión no es válida. Vuelve a iniciar sesión.',
  403: 'Tu rol no tiene permiso para operar compras.',
  404: 'La orden, sede o proveedor no existe o no pertenece a tu institución.',
  409: 'La operación entra en conflicto con el estado actual de la orden.',
  422: 'Los datos enviados no son válidos: revisa cantidades, precios, fechas y el motivo.',
  predeterminado: (estado) => `No se pudo completar la operación (HTTP ${estado}).`,
};

/**
 * Mensaje legible de un fallo del reabastecimiento y compras (Feature 020, T8).
 *
 * Delega la estructura común —`detail` textual, status 0 y fallback— en
 * `mensajeDeErrorHttp`; aquí solo viven los textos de este dominio. Vive fuera de
 * los componentes para que las tres vistas de Administrador y la de Bodega
 * compartan el mismo criterio.
 */
export function mensajeDeErrorCompras(error: HttpErrorResponse): string {
  return mensajeDeErrorHttp(error, MENSAJES_COMPRAS);
}
