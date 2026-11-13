import { HttpErrorResponse } from '@angular/common/http';

import {
  MensajesDeErrorHttp,
  mensajeDeErrorHttp,
} from '../../shared/utils/errores-http';

const MENSAJES_CONTROL: MensajesDeErrorHttp = {
  401: 'Tu sesión no es válida para el portal de control. Vuelve a iniciar sesión.',
  403: 'Tu rol no tiene permiso para esta operación de control.',
  404: 'La institución o el Administrador indicado no existe.',
  409: 'La operación entra en conflicto con el estado actual: por ejemplo, la baja del último Administrador activo o una invitación ya aceptada.',
  422: 'Los datos o el motivo enviados no son válidos: revisa el catálogo, el texto de «Otro» y el límite de 500 caracteres.',
  503: 'El servicio de identidad o una confirmación local no está disponible. Reintenta la operación; el motivo se completa sin repetir el cambio.',
  predeterminado: (estado) => `No se pudo completar la operación (HTTP ${estado}).`,
};

/**
 * Mensaje legible de un fallo del portal de control (Feature 012, T9; ampliado en
 * Feature 017 con las mutaciones motivadas y la gestión de Administradores).
 *
 * Delega la estructura común —`detail` textual, status 0 y fallback— en
 * `mensajeDeErrorHttp`; aquí solo viven los textos de este dominio. Vive fuera de
 * los componentes para que las vistas de control compartan el mismo criterio.
 */
export function mensajeDeErrorControl(error: HttpErrorResponse): string {
  return mensajeDeErrorHttp(error, MENSAJES_CONTROL);
}
