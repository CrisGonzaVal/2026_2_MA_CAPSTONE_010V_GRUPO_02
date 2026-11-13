import { HttpErrorResponse } from '@angular/common/http';

import {
  MensajesDeErrorHttp,
  mensajeDeErrorHttp,
} from '../../shared/utils/errores-http';

const MENSAJES_ADMINISTRACION: MensajesDeErrorHttp = {
  401: 'Tu sesión no es válida. Vuelve a iniciar sesión.',
  403: 'Tu rol no tiene permiso para esta operación administrativa.',
  404: 'El recurso indicado no existe o no pertenece a tu institución.',
  409: 'La operación entra en conflicto con el estado actual (por ejemplo, un correo ya vinculado o una invitación ya aceptada).',
  422: 'Los datos o el motivo enviados no son válidos: revisa el catálogo, el texto de «Otro» y el límite de 500 caracteres.',
  503: 'El servicio de identidad o una confirmación local no está disponible. Si el alta quedó incompleta, reintenta con el mismo correo para completarla.',
  predeterminado: (estado) => `No se pudo completar la operación (HTTP ${estado}).`,
};

/**
 * Mensaje legible de un fallo de la administración institucional (Feature 012, T10;
 * ampliado en Feature 017 con 409/422/503 de invitaciones y motivos).
 *
 * Delega la estructura común —`detail` textual, status 0 y fallback— en
 * `mensajeDeErrorHttp`; aquí solo viven los textos de este dominio. Vive fuera de
 * los componentes para compartir el mismo criterio entre vistas.
 */
export function mensajeDeErrorAdministracion(error: HttpErrorResponse): string {
  return mensajeDeErrorHttp(error, MENSAJES_ADMINISTRACION);
}
