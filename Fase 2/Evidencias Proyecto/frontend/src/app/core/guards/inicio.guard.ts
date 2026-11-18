import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';

import { AutenticacionService } from '../services/auth.service';

/**
 * Resuelve la pantalla inicial según el rol local ya vinculado a Clerk.
 *
 * El dashboard operativo no es una superficie del Superadmin: su entrada es el
 * dashboard global del portal `/control`. Los roles institucionales conservan
 * `/dashboard` como destino inicial.
 */
export const InicioGuard: CanActivateFn = async () => {
  const autenticacion = inject(AutenticacionService);
  const router = inject(Router);
  const identidad = await autenticacion.esperarIdentidad();

  if (identidad === null) {
    return router.createUrlTree(['/login'], { queryParams: { retorno: '/' } });
  }

  return router.createUrlTree([
    identidad.rol === 'Superadmin' ? '/control/dashboard' : '/dashboard',
  ]);
};
