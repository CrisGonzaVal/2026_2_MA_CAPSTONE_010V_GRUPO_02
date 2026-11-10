import { etiquetaEstado } from './etiqueta-estado';

/**
 * Feature 021 (V-3): el helper centraliza la presentación de estados.
 *
 * Los estados canónicos (`EnCurso`, `EnRevision`, `Pendiente`, `Cerrado`,
 * `Anulado`) no cambian: la lógica por nombre canónico sigue intacta. El helper
 * es solo de presentación y se aplica al tablero, al detalle, al historial y a
 * las listas de la 021.
 */
describe('etiquetaEstado', () => {
  it('separa las palabras de EnCurso y EnRevision', () => {
    expect(etiquetaEstado('EnCurso')).toBe('En Curso');
    expect(etiquetaEstado('EnRevision')).toBe('En Revisión');
  });

  it('conserva igual cualquier otro estado canónico', () => {
    expect(etiquetaEstado('Pendiente')).toBe('Pendiente');
    expect(etiquetaEstado('Cerrado')).toBe('Cerrado');
    expect(etiquetaEstado('Anulado')).toBe('Anulado');
  });

  it('tolera nulos, vacíos y espacios', () => {
    expect(etiquetaEstado(null)).toBe('');
    expect(etiquetaEstado(undefined)).toBe('');
    expect(etiquetaEstado('')).toBe('');
    expect(etiquetaEstado('   ')).toBe('');
    expect(etiquetaEstado('  EnCurso  ')).toBe('En Curso');
  });

  it('no inventa estados desconocidos ni cambia mayúsculas ajenas', () => {
    expect(etiquetaEstado('encurso')).toBe('encurso');
    expect(etiquetaEstado('En curso')).toBe('En curso');
    expect(etiquetaEstado('En Camino')).toBe('En Camino');
  });
});
