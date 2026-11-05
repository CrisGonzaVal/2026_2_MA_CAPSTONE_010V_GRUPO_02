import { ROLES_COMPRAS_ADMIN, ROLES_COMPRAS_BODEGA } from '../../core/auth/roles';
import { comprasRoutes } from './compras.routes';

/**
 * Contrato de navegación del reabastecimiento y compras (Feature 020, T8/T9).
 *
 * Cinco entradas de carga perezosa: necesidades, listado, alta y edición (que
 * reutiliza el formulario) para el Administrador, y la recepción para el
 * Bodeguero. El segmento `/compras` admite a ambos roles en `app.routes.ts` y
 * aquí cada vista hija exige el suyo con `RolGuard`.
 */
describe('comprasRoutes', () => {
  it('publica las cinco rutas con carga perezosa', () => {
    expect(comprasRoutes.map((ruta) => ruta.path).sort()).toEqual(
      ['', 'necesidades', 'nueva', 'recepcion', ':id/editar'].sort(),
    );
    for (const ruta of comprasRoutes) {
      const contexto = ruta.path ?? '';
      expect(typeof ruta.loadComponent).withContext(contexto).toBe('function');
      expect(ruta.loadChildren).withContext(contexto).toBeUndefined();
    }
  });

  it('la entrada vacía es el listado de órdenes', () => {
    const raiz = comprasRoutes.find((ruta) => ruta.path === '');
    expect(raiz?.redirectTo).toBeUndefined();
    expect(raiz?.title).toContain('Órdenes de compra');
  });

  it('la edición reutiliza el formulario de alta', () => {
    const alta = comprasRoutes.find((ruta) => ruta.path === 'nueva');
    const edicion = comprasRoutes.find((ruta) => ruta.path === ':id/editar');
    expect(alta?.loadComponent).toBeDefined();
    expect(edicion?.loadComponent).toBeDefined();
  });

  it('las vistas de Administrador exigen su rol y la recepción el del Bodeguero', () => {
    for (const ruta of comprasRoutes) {
      const contexto = ruta.path ?? '';
      const esperado =
        ruta.path === 'recepcion' ? ROLES_COMPRAS_BODEGA : ROLES_COMPRAS_ADMIN;
      expect(ruta.data?.['roles']).withContext(contexto).toEqual(esperado);
      expect(ruta.canActivate?.length).withContext(contexto).toBe(1);
    }
  });
});
