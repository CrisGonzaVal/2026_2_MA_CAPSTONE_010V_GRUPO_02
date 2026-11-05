import { Routes } from '@angular/router';

import { ROLES_COMPRAS_ADMIN, ROLES_COMPRAS_BODEGA } from '../../core/auth/roles';
import { RolGuard } from '../../core/guards/role.guard';

/**
 * Rutas del reabastecimiento externo y compras (Feature 020, T8/T9).
 *
 * El segmento `/compras` admite al Administrador y al Bodeguero en
 * `app.routes.ts`; aquí cada vista hija exige su rol con `RolGuard`, porque las
 * superficies son disjuntas: necesidades y OC son del Administrador y la
 * recepción es del Bodeguero de la sede destino.
 *
 * Cada vista se carga de forma perezosa y la edición reutiliza el formulario de
 * alta (`:id/editar`), porque solo cambia el modo de envío. Orden de
 * declaración: las rutas de un segmento fijo (`necesidades`, `nueva`,
 * `recepcion`) van antes que `:id/editar`, que exige dos segmentos.
 */
export const comprasRoutes: Routes = [
  {
    path: '',
    canActivate: [RolGuard(ROLES_COMPRAS_ADMIN)],
    data: { roles: ROLES_COMPRAS_ADMIN },
    loadComponent: () =>
      import('./lista-ordenes/lista-ordenes.component').then(
        (m) => m.ListaOrdenesComponent,
      ),
    title: 'Órdenes de compra | CompuStock',
  },
  {
    path: 'necesidades',
    canActivate: [RolGuard(ROLES_COMPRAS_ADMIN)],
    data: { roles: ROLES_COMPRAS_ADMIN },
    loadComponent: () =>
      import('./necesidades/necesidades.component').then(
        (m) => m.NecesidadesComponent,
      ),
    title: 'Necesidades de reabastecimiento | CompuStock',
  },
  {
    path: 'nueva',
    canActivate: [RolGuard(ROLES_COMPRAS_ADMIN)],
    data: { roles: ROLES_COMPRAS_ADMIN },
    loadComponent: () =>
      import('./nueva-orden/nueva-orden.component').then(
        (m) => m.NuevaOrdenComponent,
      ),
    title: 'Nueva orden de compra | CompuStock',
  },
  {
    path: ':id/editar',
    canActivate: [RolGuard(ROLES_COMPRAS_ADMIN)],
    data: { roles: ROLES_COMPRAS_ADMIN },
    loadComponent: () =>
      import('./nueva-orden/nueva-orden.component').then(
        (m) => m.NuevaOrdenComponent,
      ),
    title: 'Editar orden de compra | CompuStock',
  },
  {
    path: 'recepcion',
    canActivate: [RolGuard(ROLES_COMPRAS_BODEGA)],
    data: { roles: ROLES_COMPRAS_BODEGA },
    loadComponent: () =>
      import('./recepcion-bodega/recepcion-bodega.component').then(
        (m) => m.RecepcionBodegaComponent,
      ),
    title: 'Recepción de compras | CompuStock',
  },
];
