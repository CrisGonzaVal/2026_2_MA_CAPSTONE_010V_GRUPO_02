/**
 * Feature 021 (V-3): etiqueta visible de un estado del pedido.
 *
 * Los estados se persisten y se comparan por su nombre canónico (`EnCurso`,
 * `EnRevision`, `Pendiente`, `Cerrado`, `Anulado`): guards, roles y lógica de
 * negocio nunca leen esta etiqueta. Aquí solo se separan las palabras de los
 * estados compuestos para la copia visible de la SPA.
 */
const ETIQUETAS: Readonly<Record<string, string>> = {
  EnCurso: 'En Curso',
  EnRevision: 'En Revisión',
};

export function etiquetaEstado(nombre: string | null | undefined): string {
  const canonico = (nombre ?? '').trim();
  if (canonico === '') {
    return '';
  }
  return ETIQUETAS[canonico] ?? canonico;
}
