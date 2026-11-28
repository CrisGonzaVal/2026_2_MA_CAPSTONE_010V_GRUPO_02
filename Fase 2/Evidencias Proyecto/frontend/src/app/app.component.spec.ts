import { WritableSignal, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';

import { AppComponent } from './app.component';
import { routes } from './app.routes';
import { AutenticacionService, EstadoIdentidad } from './core/services/auth.service';
import { TiempoRealService } from './core/services/tiempo-real.service';
import {
  DepartamentoEfectivo,
  IdentidadAutenticada,
  InstitucionEfectiva,
  SedeEfectiva,
} from './shared/interfaces';

/**
 * Institución efectiva de la identidad limitada (Feature 008, AC-17). Procede de
 * `GET /auth/me` y la vista solo la presenta como contexto.
 */
const INSTITUCION: InstitucionEfectiva = {
  institucion_id: 'inst-los-alpes',
  nombre: 'Los Alpes',
};

/** Contexto organizacional del Bodeguero y del Solicitante (AC-22). */
const SEDE: SedeEfectiva = {
  sede_id: 2,
  nombre: 'Sede Maipú',
};

const DEPARTAMENTO: DepartamentoEfectivo = {
  departamento_id: 6,
  nombre: 'Biblioteca',
};

/**
 * Identidad local de prueba (`/auth/me`), equivalente a la usuaria real de la
 * semilla: debe presentarse como "Camila Fernandez",
 * "camila.fernandez@losalpes.cl" y rol legible "Administrador".
 */
const IDENTIDAD_RESUELTA: IdentidadAutenticada = {
  usuario_id: 1,
  sub: 'user_de_prueba',
  nombre: 'Camila',
  apellido: 'Fernandez',
  correo: 'camila.fernandez@losalpes.cl',
  rol: 'Administrador',
  institucion: INSTITUCION,
  sede: null,
  departamento: null,
};

/** Valores ficticios que el layout antiguo mostraba quemados (AC-16 / D-14). */
const DATOS_FICTICIOS = [
  'Super Administrator',
  'admin@compustock.cl',
  'Superadmin',
];

describe('AppComponent', () => {
  let autenticacionFalsa: {
    cerrarSesion: jasmine.Spy;
    estaAutenticado: WritableSignal<boolean>;
    identidad: WritableSignal<IdentidadAutenticada | null>;
    estadoIdentidad: WritableSignal<EstadoIdentidad>;
  };

  /** Doble del hub raíz: registra arranque y parada sin abrir `fetch`. */
  let tiempoRealFalso: {
    iniciar: jasmine.Spy;
    detener: jasmine.Spy;
  };

  beforeEach(async () => {
    autenticacionFalsa = {
      cerrarSesion: jasmine.createSpy('cerrarSesion').and.resolveTo(undefined),
      estaAutenticado: signal(true),
      identidad: signal<IdentidadAutenticada | null>(IDENTIDAD_RESUELTA),
      estadoIdentidad: signal<EstadoIdentidad>('disponible'),
    };

    tiempoRealFalso = {
      iniciar: jasmine.createSpy('iniciar'),
      detener: jasmine.createSpy('detener'),
    };

    await TestBed.configureTestingModule({
      imports: [AppComponent],
      // `AppComponent` usa `routerLink`/`router-outlet`, asi que sin el router
      //-provider los enlaces no se pueden resolver y el fixture falla al crear.
      providers: [
        provideRouter(routes),
        // La shell no guarda token local: consume la sesion/identidad de Clerk
        // como señales. En la prueba se sustituyen por señales dobles.
        { provide: AutenticacionService, useValue: autenticacionFalsa },
        // Feature 028: la shell arranca el hub raíz; el doble evita una
        // conexión real y permite contar los arranques.
        { provide: TiempoRealService, useValue: tiempoRealFalso },
      ],
    }).compileComponents();
  });

  function crearYRenderizar(): HTMLElement {
    const fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  it('should create the app', () => {
    const fixture = TestBed.createComponent(AppComponent);
    expect(fixture.componentInstance).toBeTruthy();
  });

  it('debe exponer el titulo del sistema', () => {
    const fixture = TestBed.createComponent(AppComponent);
    expect(fixture.componentInstance.titulo).toEqual('CompuStock');
  });

  it('debe renderizar el encabezado principal', () => {
    const compilado = crearYRenderizar();
    expect(compilado.querySelector('h1')?.textContent).toContain(
      'Sistema de Gestión de Insumos',
    );
  });

  it('el shell no scrollea la página y el sidebar scrollea internamente', () => {
    const compilado = crearYRenderizar();
    const shell = compilado.querySelector('.flex.h-screen') as HTMLElement | null;
    const navegacion = compilado.querySelector(
      'nav[aria-label="Navegacion principal"]'
    ) as HTMLElement | null;
    const principal = compilado.querySelector('main') as HTMLElement | null;

    expect(shell).not.toBeNull();
    expect(navegacion).not.toBeNull();
    expect(principal).not.toBeNull();
    expect(shell!.classList.contains('overflow-hidden')).toBe(true);
    // El scroll interno del main no debe contribuir al documento.
    expect(shell!.classList.contains('[contain:paint]')).toBe(true);
    expect(navegacion!.classList.contains('overflow-y-auto')).toBe(true);
    expect(navegacion!.classList.contains('min-h-0')).toBe(true);
    // El main conserva su scroll interno; no se toca en esta corrección.
    expect(principal!.classList.contains('overflow-y-auto')).toBe(true);
  });

  it('debe alternar el menu lateral', () => {
    const fixture = TestBed.createComponent(AppComponent);
    const app = fixture.componentInstance;

    expect(app.sidebarAbierto()).toBeTrue();
    app.alternarSidebar();
    expect(app.sidebarAbierto()).toBeFalse();
    app.alternarSidebar();
    expect(app.sidebarAbierto()).toBeTrue();
  });

  it('cerrar sesion vuelve al login', async () => {
    const router = TestBed.inject(Router);
    spyOn(router, 'navigate');
    const fixture = TestBed.createComponent(AppComponent);

    fixture.componentInstance.cerrarSesion();
    await fixture.whenStable();

    expect(autenticacionFalsa.cerrarSesion).toHaveBeenCalled();
    expect(router.navigate).toHaveBeenCalledWith(['/login']);
  });

  describe('identidad local en el layout (AC-16)', () => {
    it('presenta nombre completo, correo local y rol legible sin datos ficticios', () => {
      const compilado = crearYRenderizar();
      const texto = compilado.textContent ?? '';

      expect(texto).toContain('Camila Fernandez');
      expect(texto).toContain('camila.fernandez@losalpes.cl');
      expect(texto).toContain('Administrador');

      for (const ficticio of DATOS_FICTICIOS) {
        expect(texto).not.toContain(ficticio);
      }
    });

    it('deriva el nombre completo y el rol de la identidad resuelta', () => {
      const fixture = TestBed.createComponent(AppComponent);
      const app = fixture.componentInstance;

      expect(app.nombreCompleto()).toEqual('Camila Fernandez');
      expect(app.correoLocal()).toEqual('camila.fernandez@losalpes.cl');
      expect(app.rolLegible()).toEqual('Administrador');
    });

    it('muestra en el avatar la inicial del nombre normalizada a mayúscula', () => {
      const fixture = TestBed.createComponent(AppComponent);
      fixture.detectChanges();
      const app = fixture.componentInstance;

      expect(app.inicialNombre()).toEqual('C');

      // El avatar recibe la inicial, no una letra fija.
      const avatar = fixture.nativeElement.querySelector(
        '.w-10.h-10.rounded-full',
      ) as HTMLElement | null;
      expect(avatar?.textContent?.trim()).toEqual('C');
    });

    it('normaliza a mayúscula un nombre en minúscula', () => {
      autenticacionFalsa.identidad.set({
        ...IDENTIDAD_RESUELTA,
        nombre: 'camila',
      });
      const fixture = TestBed.createComponent(AppComponent);

      expect(fixture.componentInstance.inicialNombre()).toEqual('C');
    });

    it('mientras carga la identidad muestra un marcador neutro sin parecer usuario', () => {
      autenticacionFalsa.identidad.set(null);
      autenticacionFalsa.estadoIdentidad.set('cargando');
      const fixture = TestBed.createComponent(AppComponent);
      fixture.detectChanges();
      const texto = (fixture.nativeElement as HTMLElement).textContent ?? '';

      expect(texto).toContain('Cargando identidad');
      expect(fixture.componentInstance.inicialNombre()).toBeNull();
      expect(fixture.componentInstance.nombreCompleto()).toBeNull();
      expect(fixture.componentInstance.rolLegible()).toBeNull();

      for (const ficticio of DATOS_FICTICIOS) {
        expect(texto).not.toContain(ficticio);
      }
    });

    it('ante error o identidad no disponible muestra un marcador neutro', () => {
      autenticacionFalsa.identidad.set(null);
      autenticacionFalsa.estadoIdentidad.set('no_disponible');
      const fixture = TestBed.createComponent(AppComponent);
      fixture.detectChanges();
      const texto = (fixture.nativeElement as HTMLElement).textContent ?? '';

      expect(texto).toContain('Identidad no disponible');
      expect(fixture.componentInstance.inicialNombre()).toBeNull();
      expect(fixture.componentInstance.rolLegible()).toBeNull();

      for (const ficticio of DATOS_FICTICIOS) {
        expect(texto).not.toContain(ficticio);
      }
    });

    it('sin sesion no muestra el marco de la app ni identidad ficticia', () => {
      autenticacionFalsa.estaAutenticado.set(false);
      autenticacionFalsa.identidad.set(null);
      autenticacionFalsa.estadoIdentidad.set('no_disponible');
      const compilado = crearYRenderizar();

      expect(compilado.querySelector('aside')).toBeNull();

      for (const ficticio of DATOS_FICTICIOS) {
        expect(compilado.textContent ?? '').not.toContain(ficticio);
      }
    });
  });

  /**
   * AC-3: el Solicitante no recibe el acceso administrativo en la navegación.
   * Es comodidad de interfaz; la ruta sigue protegida por el guard de rol.
   */
  describe('navegación por rol (AC-3)', () => {
    function destinos(compilado: HTMLElement): string[] {
      return Array.from(compilado.querySelectorAll('a')).map(
        (enlace) => enlace.getAttribute('href') ?? '',
      );
    }

    it('oculta el enlace de administración al Solicitante', () => {
      autenticacionFalsa.identidad.set({ ...IDENTIDAD_RESUELTA, rol: 'Solicitante' });
      const compilado = crearYRenderizar();

      expect(destinos(compilado)).not.toContain('/administracion');
      // Las demás secciones permitidas siguen visibles.
      expect(destinos(compilado)).toContain('/dashboard');
      expect(destinos(compilado)).toContain('/inventario');
      expect(destinos(compilado)).toContain('/tickets');
    });

    it('mantiene el enlace de administración solo al Administrador', () => {
      autenticacionFalsa.identidad.set({
        ...IDENTIDAD_RESUELTA,
        rol: 'Administrador',
      });
      expect(destinos(crearYRenderizar())).toContain('/administracion');

      // Feature 017 (AC-15): la API tenant de administración niega al
      // Superadmin, así que su navegación no ofrece una pantalla muerta.
      autenticacionFalsa.identidad.set({
        ...IDENTIDAD_RESUELTA,
        rol: 'Superadmin',
        institucion: null,
      });
      expect(destinos(crearYRenderizar())).not.toContain('/administracion');
    });

    /**
     * Feature 012, AC-3 y Feature 017, AC-15: el Superadmin solo conserva
     * `/control` como superficie. Dashboard, inventario, tickets y
     * administración se retiran de la navegación; las rutas siguen protegidas
     * por el guard de rol.
     */
    it('deja al Superadmin únicamente el portal /control en la navegación', () => {
      autenticacionFalsa.identidad.set({
        ...IDENTIDAD_RESUELTA,
        rol: 'Superadmin',
        institucion: null,
      });
      const compilado = crearYRenderizar();

      for (const retirada of [
        '/dashboard',
        '/inventario',
        '/tickets',
        '/administracion',
        '/compras',
        '/compras/necesidades',
        '/compras/recepcion',
      ]) {
        expect(destinos(compilado)).withContext(retirada).not.toContain(retirada);
      }
      expect(destinos(compilado)).toContain('/control/dashboard');
      expect(destinos(compilado)).toContain('/control/instituciones');
    });

    /**
     * Feature 020, AC-13: la administración de compras es del Administrador. El
     * Bodeguero tiene su propia entrada de recepción (T9), no estas; el
     * Superadmin solo opera proveedores por API.
     */
    it('ofrece las entradas de compras solo al Administrador', () => {
      autenticacionFalsa.identidad.set({ ...IDENTIDAD_RESUELTA, rol: 'Administrador' });
      const admin = destinos(crearYRenderizar());
      expect(admin).toContain('/compras');
      expect(admin).toContain('/compras/necesidades');

      for (const rol of ['Bodeguero', 'Solicitante', 'Superadmin']) {
        autenticacionFalsa.identidad.set({ ...IDENTIDAD_RESUELTA, rol });
        const destinosRol = destinos(crearYRenderizar());
        expect(destinosRol).withContext(rol).not.toContain('/compras');
        expect(destinosRol).withContext(rol).not.toContain('/compras/necesidades');
      }
    });

    /**
     * Feature 020, AC-6 (T9): la recepción de compras es del Bodeguero. El
     * Administrador no la ve; el Solicitante tampoco.
     */
    it('ofrece la recepción de compras solo al Bodeguero', () => {
      autenticacionFalsa.identidad.set({ ...IDENTIDAD_RESUELTA, rol: 'Bodeguero' });
      const bodega = destinos(crearYRenderizar());
      expect(bodega).toContain('/compras/recepcion');
      expect(bodega).not.toContain('/compras');

      for (const rol of ['Administrador', 'Solicitante', 'Superadmin']) {
        autenticacionFalsa.identidad.set({ ...IDENTIDAD_RESUELTA, rol });
        expect(destinos(crearYRenderizar()))
          .withContext(rol)
          .not.toContain('/compras/recepcion');
      }
    });

    it('mantiene el enlace de tickets a los roles de negocio', () => {
      for (const rol of ['Administrador', 'Bodeguero', 'Solicitante']) {
        autenticacionFalsa.identidad.set({ ...IDENTIDAD_RESUELTA, rol });
        const compilado = crearYRenderizar();

        expect(destinos(compilado)).withContext(rol).toContain('/tickets');
      }
    });
  });

  /**
   * AC-17 / AC-19: el contexto institucional mostrado es el de `/auth/me`. Para
   * roles limitados es el nombre de su institución efectiva; para Superadmin,
   * cuyo `institucion` es `null`, es un contexto global explícito. La vista no
   * ofrece ningún selector ni trata el contexto como seguridad.
   */
  describe('contexto institucional (AC-17, AC-19)', () => {
    it('muestra el nombre de la institución efectiva del rol limitado', () => {
      const fixture = TestBed.createComponent(AppComponent);
      fixture.detectChanges();
      const texto = (fixture.nativeElement as HTMLElement).textContent ?? '';

      expect(fixture.componentInstance.contextoInstitucional()).toEqual('Los Alpes');
      expect(texto).toContain('Los Alpes');
    });

    it('para Superadmin muestra un contexto global explícito, no vacío', () => {
      autenticacionFalsa.identidad.set({
        ...IDENTIDAD_RESUELTA,
        rol: 'Superadmin',
        institucion: null,
      });
      const fixture = TestBed.createComponent(AppComponent);
      fixture.detectChanges();
      const texto = (fixture.nativeElement as HTMLElement).textContent ?? '';

      expect(fixture.componentInstance.contextoInstitucional()).toEqual(
        'Todas las instituciones',
      );
      expect(texto).toContain('Todas las instituciones');
      // El nombre de una institución concreta no se usa para Superadmin.
      expect(texto).not.toContain('Los Alpes');
    });

    it('un rol limitado sin institución resuelta no muestra un contexto global', () => {
      autenticacionFalsa.identidad.set({ ...IDENTIDAD_RESUELTA, institucion: null });
      const fixture = TestBed.createComponent(AppComponent);
      fixture.detectChanges();

      // Solo Superadmin declara el contexto global; una institución ausente en
      // un rol limitado es una ausencia, no un ámbito global (AC-17).
      expect(fixture.componentInstance.contextoInstitucional()).toBeNull();
      expect((fixture.nativeElement as HTMLElement).textContent ?? '').not.toContain(
        'Todas las instituciones',
      );
    });

    it('mientras la identidad carga no muestra contexto institucional', () => {
      autenticacionFalsa.identidad.set(null);
      autenticacionFalsa.estadoIdentidad.set('cargando');
      const fixture = TestBed.createComponent(AppComponent);
      fixture.detectChanges();

      expect(fixture.componentInstance.contextoInstitucional()).toBeNull();
      expect((fixture.nativeElement as HTMLElement).textContent ?? '').not.toContain(
        'Los Alpes',
      );
    });

    it('no expone un selector ni una entrada de ámbito institucional', () => {
      const compilado = crearYRenderizar();

      expect(compilado.querySelector('select')).toBeNull();
      expect(compilado.querySelector('input')).toBeNull();
    });
  });

  /**
   * AC-22/AC-23: la cabecera presenta el contexto organizacional informativo de
   * `/auth/me`. El Bodeguero ve su sede; el Solicitante, su departamento y la
   * sede de ese departamento. La asignación faltante se muestra como `—` y los
   * roles a los que no aplica no reciben badges nuevos.
   */
  describe('contexto organizacional (AC-22, AC-23)', () => {
    function textoDe(compilado: HTMLElement): string {
      return compilado.textContent ?? '';
    }

    it('el Administrador no muestra badges de sede ni departamento', () => {
      const compilado = crearYRenderizar();

      expect(textoDe(compilado)).not.toContain('Sede:');
      expect(textoDe(compilado)).not.toContain('Departamento:');
      expect(
        compilado.querySelector('[aria-label="Sede del usuario"]'),
      ).toBeNull();
      expect(
        compilado.querySelector('[aria-label="Departamento del usuario"]'),
      ).toBeNull();
    });

    it('el Bodeguero muestra su sede y omite el departamento', () => {
      autenticacionFalsa.identidad.set({
        ...IDENTIDAD_RESUELTA,
        rol: 'Bodeguero',
        sede: SEDE,
        departamento: null,
      });
      const fixture = TestBed.createComponent(AppComponent);
      fixture.detectChanges();
      const texto = textoDe(fixture.nativeElement as HTMLElement);

      expect(fixture.componentInstance.contextoSede()).toEqual('Sede Maipú');
      expect(fixture.componentInstance.contextoDepartamento()).toBeNull();
      expect(texto).toContain('Sede: Sede Maipú');
      expect(texto).not.toContain('Departamento:');
    });

    it('el Bodeguero sin sede muestra el badge con guion', () => {
      autenticacionFalsa.identidad.set({
        ...IDENTIDAD_RESUELTA,
        rol: 'Bodeguero',
        sede: null,
        departamento: null,
      });
      const fixture = TestBed.createComponent(AppComponent);
      fixture.detectChanges();
      const texto = textoDe(fixture.nativeElement as HTMLElement);

      expect(fixture.componentInstance.contextoSede()).toEqual('—');
      expect(texto).toContain('Sede: —');
      expect(texto).not.toContain('Departamento:');
    });

    it('el Solicitante muestra departamento y sede', () => {
      autenticacionFalsa.identidad.set({
        ...IDENTIDAD_RESUELTA,
        rol: 'Solicitante',
        sede: SEDE,
        departamento: DEPARTAMENTO,
      });
      const fixture = TestBed.createComponent(AppComponent);
      fixture.detectChanges();
      const texto = textoDe(fixture.nativeElement as HTMLElement);

      expect(fixture.componentInstance.contextoSede()).toEqual('Sede Maipú');
      expect(fixture.componentInstance.contextoDepartamento()).toEqual('Biblioteca');
      expect(texto).toContain('Sede: Sede Maipú');
      expect(texto).toContain('Departamento: Biblioteca');
    });

    it('el Solicitante sin asignaciones muestra ambos badges con guion', () => {
      autenticacionFalsa.identidad.set({
        ...IDENTIDAD_RESUELTA,
        rol: 'Solicitante',
        sede: null,
        departamento: null,
      });
      const fixture = TestBed.createComponent(AppComponent);
      fixture.detectChanges();
      const texto = textoDe(fixture.nativeElement as HTMLElement);

      expect(texto).toContain('Sede: —');
      expect(texto).toContain('Departamento: —');
    });

    it('el Superadmin no recibe badges organizacionales', () => {
      autenticacionFalsa.identidad.set({
        ...IDENTIDAD_RESUELTA,
        rol: 'Superadmin',
        institucion: null,
        sede: null,
        departamento: null,
      });
      const compilado = crearYRenderizar();

      expect(compilado.querySelector('[aria-label="Sede del usuario"]')).toBeNull();
      expect(
        compilado.querySelector('[aria-label="Departamento del usuario"]'),
      ).toBeNull();
    });

    it('no expone un selector ni una entrada de sede o departamento', () => {
      autenticacionFalsa.identidad.set({
        ...IDENTIDAD_RESUELTA,
        rol: 'Solicitante',
        sede: SEDE,
        departamento: DEPARTAMENTO,
      });
      const compilado = crearYRenderizar();

      expect(compilado.querySelector('select')).toBeNull();
      expect(compilado.querySelector('input')).toBeNull();
    });
  });

  /**
   * Feature 028, AC-19/AC-22: la shell es el único punto de arranque del hub.
   *
   * `TiempoRealService` es `providedIn: 'root'` e idempotente, así que una sola
   * llamada por shell mantiene una conexión por pestaña aunque se navegue entre
   * rutas. El cierre de sesión lo resuelve el propio hub (observa la sesión); la
   * shell solo lo detiene como red de seguridad al destruirse.
   */
  describe('arranque del hub en tiempo real (AC-19, AC-22)', () => {
    it('inicia el hub una sola vez al montar la shell', () => {
      const fixture = TestBed.createComponent(AppComponent);
      fixture.detectChanges();
      fixture.detectChanges();

      expect(tiempoRealFalso.iniciar).toHaveBeenCalledTimes(1);
      expect(tiempoRealFalso.detener).not.toHaveBeenCalled();
    });

    it('no duplica el hub ni cambia el layout al navegar entre rutas', async () => {
      const router = TestBed.inject(Router);
      const fixture = TestBed.createComponent(AppComponent);
      fixture.detectChanges();
      const compilado = fixture.nativeElement as HTMLElement;

      await router.navigateByUrl('/acceso-denegado');
      fixture.detectChanges();
      await router.navigateByUrl('/acceso-denegado?revision=2');
      fixture.detectChanges();

      expect(tiempoRealFalso.iniciar).toHaveBeenCalledTimes(1);

      const shell = compilado.querySelector('.flex.h-screen') as HTMLElement | null;
      const navegacion = compilado.querySelector(
        'nav[aria-label="Navegacion principal"]',
      ) as HTMLElement | null;
      expect(shell).not.toBeNull();
      expect(shell!.classList.contains('overflow-hidden')).toBe(true);
      expect(shell!.classList.contains('[contain:paint]')).toBe(true);
      expect(navegacion!.classList.contains('overflow-y-auto')).toBe(true);
    });

    it('al cerrar sesión no reinicia el hub y lo detiene al destruir la shell', async () => {
      const router = TestBed.inject(Router);
      spyOn(router, 'navigate');
      const fixture = TestBed.createComponent(AppComponent);
      fixture.detectChanges();

      autenticacionFalsa.estaAutenticado.set(false);
      fixture.componentInstance.cerrarSesion();
      await fixture.whenStable();
      fixture.detectChanges();

      // El hub observa la sesión y se cierra solo; la shell ni lo reabre ni lo
      // reinicia después del cierre.
      expect(tiempoRealFalso.iniciar).toHaveBeenCalledTimes(1);
      expect(tiempoRealFalso.detener).not.toHaveBeenCalled();

      // Red de seguridad: al desaparecer la shell no quedan timers ni reintentos.
      fixture.destroy();
      expect(tiempoRealFalso.detener).toHaveBeenCalledTimes(1);
    });
  });
});
