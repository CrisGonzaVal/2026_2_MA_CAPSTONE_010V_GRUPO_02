import { HttpErrorResponse } from '@angular/common/http';

import { mensajeDeErrorAdministracion } from '../../features/administracion/administracion-errores';
import { mensajeDeErrorCompras } from '../../features/compras/compras-errores';
import { mensajeDeErrorControl } from '../../features/control/control-errores';
import { mensajeDeErrorCatalogo } from '../../features/inventario/inventario.component';
import { mensajeDeErrorProducto } from '../../features/inventario/producto-detalle.component';
import { mensajeDeErrorTickets } from '../../features/tickets/ticket-detalle.component';
import { MensajesDeErrorHttp, mensajeDeErrorHttp } from './errores-http';

const SIN_CONEXION =
  'No se pudo contactar al servidor. Verifica la conexión e inténtalo de nuevo.';

function errorCon(estado: number, detalle?: unknown): HttpErrorResponse {
  return new HttpErrorResponse({
    status: estado,
    error: detalle === undefined ? null : { detail: detalle },
  });
}

const MENSAJES: MensajesDeErrorHttp = {
  401: 'no autorizado',
  403: 'prohibido',
  404: 'no encontrado',
  409: 'conflicto',
  422: 'no procesable',
  503: 'servicio no disponible',
  predeterminado: (estado) => `fallback ${estado}`,
};

describe('mensajeDeErrorHttp', () => {
  it('prefiere el detail textual del backend sin transformarlo', () => {
    expect(mensajeDeErrorHttp(errorCon(409, 'detalle del backend'), MENSAJES)).toBe(
      'detalle del backend',
    );
  });

  it('ignora un detail vacío o no textual y usa el estado', () => {
    expect(mensajeDeErrorHttp(errorCon(404, '   '), MENSAJES)).toBe('no encontrado');
    expect(mensajeDeErrorHttp(errorCon(422, [{ msg: 'inválido' }]), MENSAJES)).toBe(
      'no procesable',
    );
  });

  it('mapea los códigos con texto propio', () => {
    expect(mensajeDeErrorHttp(errorCon(401), MENSAJES)).toBe('no autorizado');
    expect(mensajeDeErrorHttp(errorCon(403), MENSAJES)).toBe('prohibido');
    expect(mensajeDeErrorHttp(errorCon(404), MENSAJES)).toBe('no encontrado');
    expect(mensajeDeErrorHttp(errorCon(409), MENSAJES)).toBe('conflicto');
    expect(mensajeDeErrorHttp(errorCon(422), MENSAJES)).toBe('no procesable');
    expect(mensajeDeErrorHttp(errorCon(503), MENSAJES)).toBe('servicio no disponible');
  });

  it('usa el fallback cuando 503 no tiene texto propio', () => {
    const sin503: MensajesDeErrorHttp = {
      401: 'no autorizado',
      403: 'prohibido',
      404: 'no encontrado',
      409: 'conflicto',
      422: 'no procesable',
      predeterminado: (estado) => `fallback ${estado}`,
    };
    expect(mensajeDeErrorHttp(errorCon(503), sin503)).toBe('fallback 503');
  });

  it('trata el estado 0 como servidor inalcanzable', () => {
    expect(mensajeDeErrorHttp(errorCon(0), MENSAJES)).toBe(SIN_CONEXION);
  });

  it('usa el fallback para un estado no mapeado', () => {
    expect(mensajeDeErrorHttp(errorCon(500), MENSAJES)).toBe('fallback 500');
  });
});

describe('helpers de error por dominio', () => {
  it('administracion conserva sus textos', () => {
    expect(mensajeDeErrorAdministracion(errorCon(401))).toBe(
      'Tu sesión no es válida. Vuelve a iniciar sesión.',
    );
    expect(mensajeDeErrorAdministracion(errorCon(403))).toBe(
      'Tu rol no tiene permiso para esta operación administrativa.',
    );
    expect(mensajeDeErrorAdministracion(errorCon(404))).toBe(
      'El recurso indicado no existe o no pertenece a tu institución.',
    );
    expect(mensajeDeErrorAdministracion(errorCon(409))).toBe(
      'La operación entra en conflicto con el estado actual (por ejemplo, un correo ya vinculado o una invitación ya aceptada).',
    );
    expect(mensajeDeErrorAdministracion(errorCon(422))).toBe(
      'Los datos o el motivo enviados no son válidos: revisa el catálogo, el texto de «Otro» y el límite de 500 caracteres.',
    );
    expect(mensajeDeErrorAdministracion(errorCon(503))).toBe(
      'El servicio de identidad o una confirmación local no está disponible. Si el alta quedó incompleta, reintenta con el mismo correo para completarla.',
    );
    expect(mensajeDeErrorAdministracion(errorCon(0))).toBe(SIN_CONEXION);
    expect(mensajeDeErrorAdministracion(errorCon(500))).toBe(
      'No se pudo completar la operación (HTTP 500).',
    );
  });

  it('compras conserva sus textos', () => {
    expect(mensajeDeErrorCompras(errorCon(401))).toBe(
      'Tu sesión no es válida. Vuelve a iniciar sesión.',
    );
    expect(mensajeDeErrorCompras(errorCon(403))).toBe(
      'Tu rol no tiene permiso para operar compras.',
    );
    expect(mensajeDeErrorCompras(errorCon(404))).toBe(
      'La orden, sede o proveedor no existe o no pertenece a tu institución.',
    );
    expect(mensajeDeErrorCompras(errorCon(409))).toBe(
      'La operación entra en conflicto con el estado actual de la orden.',
    );
    expect(mensajeDeErrorCompras(errorCon(422))).toBe(
      'Los datos enviados no son válidos: revisa cantidades, precios, fechas y el motivo.',
    );
    expect(mensajeDeErrorCompras(errorCon(503))).toBe(
      'No se pudo completar la operación (HTTP 503).',
    );
    expect(mensajeDeErrorCompras(errorCon(0))).toBe(SIN_CONEXION);
    expect(mensajeDeErrorCompras(errorCon(500))).toBe(
      'No se pudo completar la operación (HTTP 500).',
    );
  });

  it('control conserva sus textos', () => {
    expect(mensajeDeErrorControl(errorCon(401))).toBe(
      'Tu sesión no es válida para el portal de control. Vuelve a iniciar sesión.',
    );
    expect(mensajeDeErrorControl(errorCon(403))).toBe(
      'Tu rol no tiene permiso para esta operación de control.',
    );
    expect(mensajeDeErrorControl(errorCon(404))).toBe(
      'La institución o el Administrador indicado no existe.',
    );
    expect(mensajeDeErrorControl(errorCon(409))).toBe(
      'La operación entra en conflicto con el estado actual: por ejemplo, la baja del último Administrador activo o una invitación ya aceptada.',
    );
    expect(mensajeDeErrorControl(errorCon(422))).toBe(
      'Los datos o el motivo enviados no son válidos: revisa el catálogo, el texto de «Otro» y el límite de 500 caracteres.',
    );
    expect(mensajeDeErrorControl(errorCon(503))).toBe(
      'El servicio de identidad o una confirmación local no está disponible. Reintenta la operación; el motivo se completa sin repetir el cambio.',
    );
    expect(mensajeDeErrorControl(errorCon(0))).toBe(SIN_CONEXION);
    expect(mensajeDeErrorControl(errorCon(500))).toBe(
      'No se pudo completar la operación (HTTP 500).',
    );
  });

  it('catalogo conserva sus textos', () => {
    expect(mensajeDeErrorCatalogo(errorCon(401))).toBe(
      'Tu sesión no es válida. Vuelve a iniciar sesión.',
    );
    expect(mensajeDeErrorCatalogo(errorCon(403))).toBe(
      'Tu rol no tiene permiso para gestionar el catálogo.',
    );
    expect(mensajeDeErrorCatalogo(errorCon(404))).toBe(
      'El recurso indicado no existe o no está en tu alcance.',
    );
    expect(mensajeDeErrorCatalogo(errorCon(409))).toBe(
      'La operación entra en conflicto con el estado actual del catálogo.',
    );
    expect(mensajeDeErrorCatalogo(errorCon(422))).toBe(
      'Los datos enviados no son válidos: revisa el motivo.',
    );
    expect(mensajeDeErrorCatalogo(errorCon(503))).toBe(
      'No se pudo completar la operación (HTTP 503).',
    );
    expect(mensajeDeErrorCatalogo(errorCon(0))).toBe(SIN_CONEXION);
    expect(mensajeDeErrorCatalogo(errorCon(500))).toBe(
      'No se pudo completar la operación (HTTP 500).',
    );
  });

  it('producto conserva sus textos y su fallback propio', () => {
    expect(mensajeDeErrorProducto(errorCon(401))).toBe(
      'Tu sesión no es válida. Vuelve a iniciar sesión.',
    );
    expect(mensajeDeErrorProducto(errorCon(403))).toBe(
      'No tienes permiso para consultar este producto, o la capacidad inventario está deshabilitada para tu institución.',
    );
    expect(mensajeDeErrorProducto(errorCon(404))).toBe(
      'El producto indicado no existe o no está en tu alcance.',
    );
    expect(mensajeDeErrorProducto(errorCon(409))).toBe(
      'No se pudo resolver tu sede operativa: tu usuario no tiene una sede asignada.',
    );
    expect(mensajeDeErrorProducto(errorCon(422))).toBe(
      'El identificador del producto no es válido: debe ser un entero positivo.',
    );
    expect(mensajeDeErrorProducto(errorCon(503))).toBe(
      'No se pudo cargar el detalle del producto (HTTP 503).',
    );
    expect(mensajeDeErrorProducto(errorCon(0))).toBe(SIN_CONEXION);
    expect(mensajeDeErrorProducto(errorCon(500))).toBe(
      'No se pudo cargar el detalle del producto (HTTP 500).',
    );
  });

  it('tickets conserva sus textos', () => {
    expect(mensajeDeErrorTickets(errorCon(401))).toBe(
      'Tu sesión no es válida. Vuelve a iniciar sesión.',
    );
    expect(mensajeDeErrorTickets(errorCon(403))).toBe(
      'Tu rol no tiene permiso para esta operación sobre el pedido.',
    );
    expect(mensajeDeErrorTickets(errorCon(404))).toBe(
      'El pedido indicado no existe o no está en tu alcance.',
    );
    expect(mensajeDeErrorTickets(errorCon(409))).toBe(
      'La operación entra en conflicto con el estado actual del pedido.',
    );
    expect(mensajeDeErrorTickets(errorCon(422))).toBe(
      'Los datos enviados no son válidos: revisa el motivo y los campos del pedido.',
    );
    expect(mensajeDeErrorTickets(errorCon(503))).toBe(
      'No se pudo completar la operación (HTTP 503).',
    );
    expect(mensajeDeErrorTickets(errorCon(0))).toBe(SIN_CONEXION);
    expect(mensajeDeErrorTickets(errorCon(500))).toBe(
      'No se pudo completar la operación (HTTP 500).',
    );
  });
});
