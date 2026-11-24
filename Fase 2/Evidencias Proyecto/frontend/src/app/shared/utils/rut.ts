import { AbstractControl, ValidationErrors, ValidatorFn } from '@angular/forms';

const MENSAJE_CUERPO = 'El cuerpo del RUT debe tener entre 1 y 8 dígitos.';

/** Clave de comparación: mayúsculas, sin puntos, guion ni espacios. */
export function normalizarRut(rut: string): string {
  return rut.replaceAll('.', '').replaceAll('-', '').replaceAll(' ', '').trim().toUpperCase();
}

/** Dígito verificador módulo 11; 11 → 0 y 10 → K. */
export function calcularDv(cuerpo: string): string {
  if (!/^\d{1,8}$/.test(cuerpo)) {
    throw new Error(MENSAJE_CUERPO);
  }

  let suma = 0;
  let multiplicador = 2;
  for (const digito of [...cuerpo].reverse()) {
    suma += Number(digito) * multiplicador;
    multiplicador = multiplicador === 7 ? 2 : multiplicador + 1;
  }

  const resto = 11 - (suma % 11);
  if (resto === 11) {
    return '0';
  }
  if (resto === 10) {
    return 'K';
  }
  return String(resto);
}

/** Acepta 1–8 dígitos, cuerpo distinto de cero y DV `0-9`/`K`. */
export function validarRut(rut: string): boolean {
  const limpio = normalizarRut(rut);
  if (limpio.length < 2) {
    return false;
  }

  const cuerpo = limpio.slice(0, -1);
  const dv = limpio.slice(-1);
  if (
    !/^\d{1,8}$/.test(cuerpo) ||
    /^0+$/.test(cuerpo) ||
    !/^[0-9K]$/.test(dv)
  ) {
    return false;
  }

  return dv === calcularDv(cuerpo);
}

/** Formato visible para presentación; no comprueba el DV. */
export function formatearRut(rut: string): string {
  const limpio = normalizarRut(rut);
  if (limpio.length < 2) {
    throw new Error(MENSAJE_CUERPO);
  }

  const cuerpo = limpio.slice(0, -1);
  const dv = limpio.slice(-1);
  if (!/^\d{1,8}$/.test(cuerpo)) {
    throw new Error(MENSAJE_CUERPO);
  }

  const grupos: string[] = [];
  let resto = cuerpo;
  while (resto.length > 0) {
    grupos.unshift(resto.slice(-3));
    resto = resto.slice(0, -3);
  }

  return `${grupos.join('.')}-${dv}`;
}

/** El vacío lo decide `required`; un valor no vacío debe tener DV válido. */
export const rutValido: ValidatorFn = (
  control: AbstractControl,
): ValidationErrors | null => {
  const valor: unknown = control.value;
  if (valor === null || valor === undefined) {
    return null;
  }
  if (typeof valor === 'string' && valor.trim() === '') {
    return null;
  }
  return typeof valor === 'string' && validarRut(valor)
    ? null
    : { rutInvalido: true };
};
