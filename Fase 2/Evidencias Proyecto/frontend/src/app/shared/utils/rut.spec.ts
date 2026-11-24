import { FormControl } from '@angular/forms';

import {
  calcularDv,
  formatearRut,
  normalizarRut,
  rutValido,
  validarRut,
} from './rut';

describe('normalizarRut', () => {
  it('quita puntos, guion y espacios y pasa a mayúsculas', () => {
    expect(normalizarRut('76.543.210-3')).toBe('765432103');
    expect(normalizarRut('76543210-3')).toBe('765432103');
    expect(normalizarRut('765432103')).toBe('765432103');
    expect(normalizarRut(' 76.543.210-3 ')).toBe('765432103');
    expect(normalizarRut('76.543.210-k')).toBe('76543210K');
    expect(normalizarRut('')).toBe('');
  });
});

describe('calcularDv', () => {
  it('aplica módulo 11 con multiplicadores 2..7', () => {
    expect(calcularDv('76543210')).toBe('3');
    expect(calcularDv('77654321')).toBe('7');
    expect(calcularDv('78765432')).toBe('0');
    expect(calcularDv('96021030')).toBe('1');
    expect(calcularDv('19191919')).toBe('K');
    expect(calcularDv('6')).toBe('K');
    expect(calcularDv('1')).toBe('9');
    expect(calcularDv('0')).toBe('0');
  });

  it('rechaza cuerpos vacíos, no numéricos o de más de 8 dígitos', () => {
    expect(() => calcularDv('')).toThrowError(/1 y 8/);
    expect(() => calcularDv('12a')).toThrowError(/1 y 8/);
    expect(() => calcularDv('123456789')).toThrowError(/1 y 8/);
    expect(() => calcularDv(' 123')).toThrowError(/1 y 8/);
  });
});

describe('validarRut', () => {
  it('acepta las mismas formas visibles que el backend', () => {
    expect(validarRut('76.543.210-3')).toBeTrue();
    expect(validarRut('76543210-3')).toBeTrue();
    expect(validarRut('765432103')).toBeTrue();
    expect(validarRut(' 76.543.210-3 ')).toBeTrue();
    expect(validarRut('1-9')).toBeTrue();
    expect(validarRut('6-k')).toBeTrue();
    expect(validarRut('19.191.919-k')).toBeTrue();
    expect(validarRut('77.654.321-7')).toBeTrue();
    expect(validarRut('78.765.432-0')).toBeTrue();
    expect(validarRut('96.021.030-1')).toBeTrue();
  });

  it('rechaza un DV incorrecto', () => {
    expect(validarRut('76.543.210-8')).toBeFalse();
    expect(validarRut('77.654.321-K')).toBeFalse();
    expect(validarRut('78.765.432-1')).toBeFalse();
    expect(validarRut('12.345.678-9')).toBeFalse();
    expect(validarRut('99-9')).toBeFalse();
    expect(validarRut('76.543.210-')).toBeFalse();
  });

  it('rechaza cuerpo cero, 9 dígitos y formatos inválidos', () => {
    expect(validarRut('')).toBeFalse();
    expect(validarRut('   ')).toBeFalse();
    expect(validarRut('0-0')).toBeFalse();
    expect(validarRut('123456789-0')).toBeFalse();
    expect(validarRut('76.543.210-33')).toBeFalse();
    expect(validarRut('abc-1')).toBeFalse();
  });
});

describe('formatearRut', () => {
  it('agrupa el cuerpo sin validar el DV', () => {
    expect(formatearRut('765432103')).toBe('76.543.210-3');
    expect(formatearRut('76.543.210-3')).toBe('76.543.210-3');
    expect(formatearRut('1-9')).toBe('1-9');
    expect(formatearRut('123-4')).toBe('123-4');
    expect(formatearRut('1234-5')).toBe('1.234-5');
    expect(formatearRut('76543210k')).toBe('76.543.210-K');
    expect(formatearRut(' 19.191.919-k ')).toBe('19.191.919-K');
  });

  it('rechaza cuerpos inválidos', () => {
    expect(() => formatearRut('')).toThrowError(/1 y 8/);
    expect(() => formatearRut('abc-1')).toThrowError(/1 y 8/);
    expect(() => formatearRut('123456789-0')).toThrowError(/1 y 8/);
  });
});

describe('rutValido', () => {
  it('deja el vacío a manos de required', () => {
    expect(rutValido(new FormControl(null))).toBeNull();
    expect(rutValido(new FormControl(''))).toBeNull();
    expect(rutValido(new FormControl('   '))).toBeNull();
  });

  it('marca un RUT no vacío inválido y acepta uno válido', () => {
    expect(rutValido(new FormControl('76.543.210-8'))).toEqual({
      rutInvalido: true,
    });
    expect(rutValido(new FormControl('76.543.210-3'))).toBeNull();
  });
});
