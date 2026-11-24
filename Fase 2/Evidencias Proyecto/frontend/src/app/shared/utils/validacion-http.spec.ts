import { HttpErrorResponse } from '@angular/common/http';

import {
  DetalleError422,
  detallesDeValidacion,
  mensajeDeCampo,
  mensajeDeDetalle,
  mensajeDeValidacion,
  traducirMensajeValidacion,
} from './validacion-http';

function errorCon(detalle: unknown, estado = 422): HttpErrorResponse {
  return new HttpErrorResponse({ status: estado, error: { detail: detalle } });
}

function detalle(
  loc: (string | number)[],
  type: string,
  msg: string,
): DetalleError422 {
  return { loc, type, msg };
}

describe('detallesDeValidacion', () => {
  it('devuelve los detalles bien formados de un 422', () => {
    const crudo = detalle(
      ['body', 'descripcion'],
      'string_too_long',
      'String should have at most 500 characters',
    );
    const error = errorCon([crudo, { msg: 'sin loc' }]);

    expect(detallesDeValidacion(error)).toEqual([crudo]);
  });

  it('devuelve [] para un detail textual, nulo o un estado distinto de 422', () => {
    expect(detallesDeValidacion(errorCon('detalle textual'))).toEqual([]);
    expect(detallesDeValidacion(errorCon(null))).toEqual([]);
    expect(
      detallesDeValidacion(
        errorCon([detalle(['body', 'nombre'], 'missing', 'Field required')], 409),
      ),
    ).toEqual([]);
  });
});

describe('traducirMensajeValidacion', () => {
  it('traduce límites, obligatoriedad y campos extra', () => {
    expect(
      traducirMensajeValidacion(
        detalle(
          ['body', 'asunto'],
          'string_too_short',
          'String should have at least 3 characters',
        ),
      ),
    ).toBe('Debe tener al menos 3 caracteres.');
    expect(
      traducirMensajeValidacion(
        detalle(
          ['body', 'descripcion'],
          'string_too_long',
          'String should have at most 500 characters',
        ),
      ),
    ).toBe('No puede superar los 500 caracteres.');
    expect(
      traducirMensajeValidacion(
        detalle(['body', 'nombre'], 'missing', 'Field required'),
      ),
    ).toBe('Este campo es obligatorio.');
    expect(
      traducirMensajeValidacion(
        detalle(['body', 'institucion_id'], 'extra_forbidden', 'Extra inputs are not permitted'),
      ),
    ).toBe('Este campo no está permitido.');
  });

  it('traduce rangos, literales y tipos de dato', () => {
    expect(
      traducirMensajeValidacion(
        detalle(
          ['body', 'detalles', 0, 'cantidad_solicitada'],
          'greater_than',
          'Input should be greater than 0',
        ),
      ),
    ).toBe('Debe ser mayor que 0.');
    expect(
      traducirMensajeValidacion(
        detalle(['body', 'stock_minimo'], 'greater_than_equal', 'Input should be greater than or equal to 0'),
      ),
    ).toBe('Debe ser mayor o igual que 0.');
    expect(
      traducirMensajeValidacion(
        detalle(['body', 'cantidad'], 'less_than', 'Input should be less than 10'),
      ),
    ).toBe('Debe ser menor que 10.');
    expect(
      traducirMensajeValidacion(
        detalle(['body', 'cantidad'], 'less_than_equal', 'Input should be less than or equal to 10'),
      ),
    ).toBe('Debe ser menor o igual que 10.');
    expect(
      traducirMensajeValidacion(
        detalle(['body', 'tipo_movimiento'], 'literal_error', "Input should be 'ENTRADA' or 'SALIDA'"),
      ),
    ).toBe('Debe ser uno de los valores permitidos.');
    expect(
      traducirMensajeValidacion(
        detalle(['body', 'producto_id'], 'int_parsing', 'Input should be a valid integer'),
      ),
    ).toBe('Debe ser un número entero.');
    expect(
      traducirMensajeValidacion(
        detalle(['body', 'monto_total'], 'decimal_parsing', 'Input should be a valid decimal'),
      ),
    ).toBe('Debe ser un número decimal válido.');
    expect(
      traducirMensajeValidacion(
        detalle(['body', 'fecha_factura'], 'date_parsing', 'Input should be a valid date'),
      ),
    ).toBe('Debe ser una fecha válida.');
    expect(
      traducirMensajeValidacion(
        detalle(['body', 'activo'], 'bool_parsing', 'Input should be a valid boolean'),
      ),
    ).toBe('Debe ser verdadero o falso.');
    expect(
      traducirMensajeValidacion(
        detalle(['body', 'observacion'], 'string_type', 'Input should be a valid string'),
      ),
    ).toBe('Debe ser texto.');
    expect(
      traducirMensajeValidacion(
        detalle(['body', 'items'], 'too_short', 'List should have at least 1 item after validation'),
      ),
    ).toBe('Agrega al menos un ítem.');
  });

  it('conserva el mensaje español del backend en value_error', () => {
    expect(
      traducirMensajeValidacion(
        detalle(
          ['body', 'rut'],
          'value_error',
          'Value error, El RUT no es válido: el dígito verificador no corresponde.',
        ),
      ),
    ).toBe('El RUT no es válido: el dígito verificador no corresponde.');
    expect(
      traducirMensajeValidacion(
        detalle(
          ['body', 'correo'],
          'value_error',
          'value is not a valid email address: The email address is not valid.',
        ),
      ),
    ).toBe('El correo no tiene un formato válido.');
  });

  it('usa un texto neutro para un tipo desconocido', () => {
    expect(
      traducirMensajeValidacion(
        detalle(['body', 'campo'], 'tipo_nuevo', 'mensaje crudo'),
      ),
    ).toBe('Revisa este valor.');
  });
});

describe('mensajeDeValidacion', () => {
  it('prefija el campo legible y el número de fila', () => {
    const simple = errorCon([
      detalle(
        ['body', 'descripcion'],
        'string_too_long',
        'String should have at most 500 characters',
      ),
    ]);
    const anidado = errorCon([
      detalle(
        ['body', 'detalles', 0, 'cantidad_solicitada'],
        'greater_than',
        'Input should be greater than 0',
      ),
    ]);

    expect(mensajeDeValidacion(simple)).toBe(
      'Descripción: No puede superar los 500 caracteres.',
    );
    expect(mensajeDeValidacion(anidado)).toBe(
      'Fila 1: Cantidad: Debe ser mayor que 0.',
    );
  });

  it('humaniza un campo snake_case desconocido y acepta un loc sin campo', () => {
    expect(
      mensajeDeValidacion(
        errorCon([
          detalle(['body', 'correo_administrador'], 'missing', 'Field required'),
        ]),
      ),
    ).toBe('Correo administrador: Este campo es obligatorio.');
    expect(
      mensajeDeValidacion(errorCon([detalle(['body'], 'missing', 'Field required')])),
    ).toBe('Este campo es obligatorio.');
  });

  it('devuelve null cuando no hay detalles traducibles', () => {
    expect(mensajeDeValidacion(errorCon('detalle textual'))).toBeNull();
    expect(mensajeDeValidacion(errorCon([]))).toBeNull();
  });
});

describe('mensajeDeCampo y mensajeDeDetalle', () => {
  const detalles = [
    detalle(
      ['body', 'detalles', 0, 'producto_id'],
      'greater_than_equal',
      'Input should be greater than or equal to 1',
    ),
    detalle(
      ['body', 'detalles', 1, 'cantidad_solicitada'],
      'greater_than',
      'Input should be greater than 0',
    ),
    detalle(['body', 'asunto'], 'string_too_long', 'String should have at most 150 characters'),
  ];

  it('encuentra el mensaje por el último elemento de loc', () => {
    expect(mensajeDeCampo(detalles, 'asunto')).toBe(
      'No puede superar los 150 caracteres.',
    );
    expect(mensajeDeCampo(detalles, 'inexistente')).toBeNull();
  });

  it('exige índice y campo para los errores de una fila', () => {
    expect(mensajeDeDetalle(detalles, 0, 'producto_id')).toBe(
      'Debe ser mayor o igual que 1.',
    );
    expect(mensajeDeDetalle(detalles, 1, 'cantidad_solicitada')).toBe(
      'Debe ser mayor que 0.',
    );
    expect(mensajeDeDetalle(detalles, 0, 'cantidad_solicitada')).toBeNull();
    expect(mensajeDeDetalle(detalles, 2, 'cantidad_solicitada')).toBeNull();
  });
});
