import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';

import { administracionRoutes } from './administracion.routes';

/** Destino de reemplazo del wildcard: evita cargar el dashboard real. */
@Component({
  selector: 'app-dashboard-falso',
  standalone: true,
  template: '<p>Dashboard de reemplazo</p>',
})
class DashboardFalsoComponent {}

/**
 * Contrato de navegación del área administrativa institucional (Feature 012, T10).
 *
 * Un layout lazy con `AdministracionComponent` que monta la navegación y sus
 * vistas hijas (sedes, departamentos y usuarios), todas de carga perezosa. El
 * acceso lo protege `app.routes.ts` con el guard de roles
 * administrativos; este segmento no lo repite ni ofrece selector de institución.
 * La vista retirada por el Bloque B no se publica: una URL sin hija casada cae
 * en el wildcard vigente de `app.routes.ts` (`**` → `/dashboard`), sujeto a la
 * autenticación (AC-38).
 */
describe('administracionRoutes', () => {
  const layout = administracionRoutes[0];
  const hijas = (layout.children ?? []).filter((r) => r.path !== '');

  it('monta el layout con carga perezosa', () => {
    expect(typeof layout.loadComponent).toBe('function');
  });

  it('redirige la entrada vacía a sedes', () => {
    const raiz = (layout.children ?? []).find((r) => r.path === '');
    expect(raiz?.redirectTo).toBe('sedes');
  });

  it('publica las tres vistas de dominio con carga perezosa', () => {
    expect(hijas.map((r) => r.path).sort()).toEqual(
      ['departamentos', 'sedes', 'usuarios'].sort(),
    );
    for (const hija of hijas) {
      const contexto = hija.path ?? '';
      expect(typeof hija.loadComponent).withContext(contexto).toBe('function');
      expect(hija.loadChildren).withContext(contexto).toBeUndefined();
    }
  });

  it('AC-38: una ruta hija no publicada no monta vista y cae en el wildcard', async () => {
    TestBed.configureTestingModule({
      providers: [
        // Árbol real de administración con el wildcard vigente de app.routes.
        // El contrato de «tres vistas» de arriba garantiza que cualquier otra
        // URL hija —incluida la vista retirada por el Bloque B— no case; aquí
        // se fija el comportamiento del wildcard para esa URL no publicada.
        provideRouter([
          { path: 'administracion', children: administracionRoutes },
          { path: 'dashboard', component: DashboardFalsoComponent },
          { path: '**', redirectTo: 'dashboard' },
        ]),
      ],
    });
    const router = TestBed.inject(Router);
    const harness = await RouterTestingHarness.create();

    await harness.navigateByUrl('/administracion/ruta-no-publicada');

    expect(router.url).toBe('/dashboard');
    expect(harness.routeNativeElement?.textContent ?? '').toContain(
      'Dashboard de reemplazo',
    );
    expect(
      harness.routeNativeElement?.querySelector('app-administracion'),
    ).toBeNull();
  });
});
