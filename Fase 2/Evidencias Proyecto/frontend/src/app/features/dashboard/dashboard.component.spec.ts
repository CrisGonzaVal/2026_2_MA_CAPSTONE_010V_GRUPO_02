import { provideHttpClient } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { WritableSignal, signal } from '@angular/core';
import { ComponentFixture, TestBed, fakeAsync, tick } from '@angular/core/testing';

import { AutenticacionService } from '../../core/services/auth.service';
import { TiempoRealService } from '../../core/services/tiempo-real.service';
import type {
  CambioTiempoReal,
  DominioTiempoReal,
  MotivoTiempoReal,
} from '../../core/services/tiempo-real.service';
import { URL_API } from '../../shared/config/url-api';
import {
  DashboardAnalitico,
  IdentidadAutenticada,
} from '../../shared/interfaces';
import { DashboardComponent } from './dashboard.component';

/**
 * Doble del hub de tiempo real (Feature 028, T15) para el dashboard. Registra
 * las suscripciones —cambio y resincronización— y permite emitir frames a mano
 * sin abrir `fetch` ni tocar la sesión de Clerk.
 */
class TiempoRealServiceFalso {
  readonly dominiosSuscritos: Array<readonly DominioTiempoReal[]> = [];
  /** Último frame de cambio entregado, para fijar que la marca es `dashboard`. */
  ultimoCambio: CambioTiempoReal | null = null;

  private readonly suscripcionesCambio: Array<{
    readonly dominios: readonly DominioTiempoReal[];
    readonly callback: (cambio: CambioTiempoReal) => void;
  }> = [];

  private readonly resincronizaciones = new Set<() => void>();

  alCambio(
    dominios: readonly DominioTiempoReal[],
    callback: (cambio: CambioTiempoReal) => void,
  ): () => void {
    const suscripcion = { dominios, callback };
    this.dominiosSuscritos.push(dominios);
    this.suscripcionesCambio.push(suscripcion);
    return () => {
      const indice = this.suscripcionesCambio.indexOf(suscripcion);
      if (indice >= 0) {
        this.suscripcionesCambio.splice(indice, 1);
      }
    };
  }

  alResincronizar(callback: () => void): () => void {
    this.resincronizaciones.add(callback);
    return () => {
      this.resincronizaciones.delete(callback);
    };
  }

  /** Suscripciones vivas: una de cambio y una de resincronización por vista. */
  get suscripcionesActivas(): number {
    return this.suscripcionesCambio.length + this.resincronizaciones.size;
  }

  emitirCambio(
    dominios: readonly DominioTiempoReal[],
    motivo: MotivoTiempoReal = 'cambio',
  ): void {
    this.ultimoCambio = { dominios, motivo };
    for (const suscripcion of [...this.suscripcionesCambio]) {
      if (dominios.some((dominio) => suscripcion.dominios.includes(dominio))) {
        suscripcion.callback({ dominios, motivo });
      }
    }
  }

  emitirResincronizacion(): void {
    for (const callback of [...this.resincronizaciones]) {
      callback();
    }
  }
}

/**
 * Feature 009 (T9): contrato de la vista del dashboard consolidado.
 *
 * Seam bajo prueba: la **interfaz publica del componente** — el DOM renderizado
 * y la(s) peticion(es) HTTP del `DashboardService` real bajo `HttpTestingController`.
 * Solo se asertan textos, encabezados, roles ARIA y numero de peticiones: nada de
 * clases Tailwind ni estructura interna fragil.
 *
 * Estado verde: el `DashboardComponent` carga la respuesta consolidada via
 * `DashboardService.obtenerDashboard()` al inicializar, con `signal()` para
 * carga/datos/error y `computed()` para las secciones, y ofrece reintento. Esta
 * spec fija el contrato de presentacion; el servicio/cliente HTTP tiene su propia
 * suite (`dashboard.service.spec.ts`).
 *
 * Contrato de template que fija esta spec:
 *   - cuatro KPI con las etiquetas exactas «Unidades en Stock», «Pedidos Activos»,
 *     «Departamentos» y «Alertas de Stock», con los valores del DTO;
 *   - sin el placeholder «Estado de Sedes Descentralizadas» ni cifras de ejemplo;
 *   - un listado de alertas con producto, sede, stock actual y minimo;
 *   - seccion «Actividad Reciente» solo si `actividad_disponible` es `true`; con
 *     `actividad_disponible=false` (Solicitante) no se pinta y **no** se consulta
 *     `/inventario/movimientos`;
 *   - durante la carga, un indicador con `role="status"`;
 *   - ante fallo, un `[role="alert"]` con un boton «Reintentar» que repite la
 *     lectura (sin restaurar cifras ficticias);
 *   - sin datos, KPI en cero y vacios explícitos («No hay alertas de stock.»,
 *     «Sin movimientos recientes.»).
 */
describe('DashboardComponent', () => {
  const RUTA_DASHBOARD = `${URL_API}/dashboard/`;
  const RUTA_MOVIMIENTOS = `${URL_API}/inventario/movimientos`;

  /** Respuesta global (Superadmin): dos instituciones atribuidas y actividad. */
  function crearDashboard(
    sobrescribir: Partial<DashboardAnalitico> = {},
  ): DashboardAnalitico {
    return {
      kpi: {
        unidades_en_stock: 4321,
        tickets_activos: 76,
        total_departamentos: 87,
        total_alertas: 9,
      },
      alertas: [
        {
          sede_id: 11,
          sede_nombre: 'Sede Central',
          producto_id: 101,
          producto_nombre: 'Papel Bond',
          stock_actual: 2,
          stock_minimo: 10,
          institucion_id: 'INSTA',
          institucion_nombre: 'Instituto Alfa',
        },
        {
          sede_id: 12,
          sede_nombre: 'Bodega Norte',
          producto_id: 202,
          producto_nombre: 'Toner HP',
          stock_actual: 1,
          stock_minimo: 5,
          institucion_id: 'INSTB',
          institucion_nombre: 'Instituto Beta',
        },
      ],
      actividad_disponible: true,
      actividad_movimientos: [
        {
          movimiento_id: 501,
          tipo_movimiento: 'ENTRADA',
          cantidad: 15,
          fecha_movimiento: '2026-04-01T08:00:00',
          producto_id: 101,
          producto_nombre: 'Papel Bond',
          sede_id: 11,
          sede_nombre: 'Sede Central',
          institucion_id: 'INSTA',
          institucion_nombre: 'Instituto Alfa',
        },
      ],
      ...sobrescribir,
    };
  }

  /** Respuesta sin datos: KPI en cero y listas vacias. */
  function crearDashboardVacio(): DashboardAnalitico {
    return {
      kpi: {
        unidades_en_stock: 0,
        tickets_activos: 0,
        total_departamentos: 0,
        total_alertas: 0,
      },
      alertas: [],
      actividad_disponible: true,
      actividad_movimientos: [],
    };
  }

  /** Respuesta del Solicitante: KPI/alertas de su ámbito, actividad no disponible. */
  function crearDashboardSolicitante(): DashboardAnalitico {
    return {
      kpi: {
        unidades_en_stock: 40,
        tickets_activos: 3,
        total_departamentos: 2,
        total_alertas: 1,
      },
      alertas: [
        {
          sede_id: 31,
          sede_nombre: 'Sede Sur',
          producto_id: 301,
          producto_nombre: 'Resma Carta',
          stock_actual: 1,
          stock_minimo: 8,
          institucion_id: 'INSTA',
          institucion_nombre: 'Instituto Alfa',
        },
      ],
      actividad_disponible: false,
      actividad_movimientos: [],
    };
  }

  /** Respuesta posterior a una mutación: KPI, alertas y actividad distintos. */
  function crearDashboardActualizado(): DashboardAnalitico {
    return {
      kpi: {
        unidades_en_stock: 9876,
        tickets_activos: 54,
        total_departamentos: 87,
        total_alertas: 8,
      },
      alertas: [
        {
          sede_id: 99,
          sede_nombre: 'Bodega Sur',
          producto_id: 909,
          producto_nombre: 'Grapas Grandes',
          stock_actual: 0,
          stock_minimo: 4,
          institucion_id: 'INSTA',
          institucion_nombre: 'Instituto Alfa',
        },
      ],
      actividad_disponible: true,
      actividad_movimientos: [
        {
          movimiento_id: 777,
          tipo_movimiento: 'SALIDA',
          cantidad: 3,
          fecha_movimiento: '2026-04-02T09:00:00',
          producto_id: 909,
          producto_nombre: 'Grapas Grandes',
          sede_id: 99,
          sede_nombre: 'Bodega Sur',
          institucion_id: 'INSTA',
          institucion_nombre: 'Instituto Alfa',
        },
      ],
    };
  }

  function crearIdentidad(rol: string): IdentidadAutenticada {
    return {
      usuario_id: 7,
      sub: 'user_dashboard',
      nombre: 'Dana',
      apellido: 'Rivas',
      correo: 'dana.rivas@losalpes.cl',
      rol,
      institucion: { institucion_id: 'INSTA', nombre: 'Instituto Alfa' },
      sede: null,
      departamento: null,
    };
  }

  let fixture: ComponentFixture<DashboardComponent>;
  let httpMock: HttpTestingController;
  let tiempoReal: TiempoRealServiceFalso;
  /** Identidad local (`/auth/me`) como señal: doble, sin arrancar Clerk. */
  let identidad: WritableSignal<IdentidadAutenticada | null>;

  beforeEach(async () => {
    identidad = signal<IdentidadAutenticada | null>(crearIdentidad('Superadmin'));
    tiempoReal = new TiempoRealServiceFalso();

    await TestBed.configureTestingModule({
      imports: [DashboardComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        // La vista no decide ámbito ni autorización (lo hace el servidor); aun
        // así se inyecta la identidad en el formato de la casa para cubrir el rol.
        { provide: AutenticacionService, useValue: { identidad } },
        // El hub real abriría `fetch` y dependería de Clerk; el doble permite
        // emitir frames de la Feature 028 sin conexión.
        { provide: TiempoRealService, useValue: tiempoReal },
      ],
    }).compileComponents();

    httpMock = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(DashboardComponent);
  });

  afterEach(() => {
    httpMock.verify({ ignoreCancelled: true });
  });

  /** Texto visible completo del dashboard. */
  function texto(): string {
    return (fixture.nativeElement as HTMLElement).textContent ?? '';
  }

  /** Dispara la carga inicial y resuelve la unica peticion con `dto`. */
  function montar(dto: DashboardAnalitico = crearDashboard()) {
    fixture.detectChanges();
    const peticion = httpMock.expectOne(RUTA_DASHBOARD);
    peticion.flush(dto);
    fixture.detectChanges();
    return peticion;
  }

  /** Boton de reintento del estado de error, por su texto accesible. */
  function botonReintentar(): HTMLButtonElement | undefined {
    const botones = Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll('button'),
    );
    return botones.find((boton) => /reintentar/i.test(boton.textContent ?? ''));
  }

  // -------------------------------------------------------------------------
  // Carga y contrato HTTP
  // -------------------------------------------------------------------------

  it('AC-15: pide el dashboard una sola vez al inicializar', () => {
    fixture.detectChanges();

    const peticion = httpMock.expectOne(RUTA_DASHBOARD);
    expect(peticion.request.method).toBe('GET');
    peticion.flush(crearDashboard());
    fixture.detectChanges();

    // Sin peticiones duplicadas.
    httpMock.expectNone(RUTA_DASHBOARD);
  });

  it('AC-8: no envía institución ni parámetros de ámbito', () => {
    fixture.detectChanges();

    const peticion = httpMock.expectOne(RUTA_DASHBOARD);
    expect(peticion.request.params.keys()).toEqual([]);
    expect(peticion.request.body).toBeNull();
    expect(peticion.request.headers.get('X-Institucion-Id')).toBeNull();

    peticion.flush(crearDashboard());
    fixture.detectChanges();
  });

  it('AC-15: no consulta el historial de movimientos para armar la actividad', () => {
    montar();

    httpMock.expectNone(RUTA_MOVIMIENTOS);
  });

  // -------------------------------------------------------------------------
  // AC-1/AC-15: KPI y retiro del placeholder
  // -------------------------------------------------------------------------

  it('AC-1: las cuatro tarjetas usan sus etiquetas exactas', () => {
    montar();

    const etiquetas = [
      'Unidades en Stock',
      'Pedidos Activos',
      'Departamentos',
      'Alertas de Stock',
    ];
    for (const etiqueta of etiquetas) {
      expect(texto()).withContext(etiqueta).toContain(etiqueta);
    }
  });

  it('AC-1: muestra los valores numéricos del DTO', () => {
    montar();

    for (const valor of ['4321', '76', '87', '9']) {
      expect(texto()).withContext(valor).toContain(valor);
    }
  });

  it('AC-15: retira el placeholder «Estado de Sedes Descentralizadas»', () => {
    montar();

    expect(texto()).not.toContain('Estado de Sedes Descentralizadas');
  });

  it('AC-15: no presenta cifras ni actividad de ejemplo', () => {
    montar();

    expect(texto()).not.toContain('1,240');
    expect(texto()).not.toContain('Se añadieron 200 lápices');
  });

  // -------------------------------------------------------------------------
  // AC-5: log de alertas
  // -------------------------------------------------------------------------

  it('AC-5: lista las alertas con producto, sede, stock actual y mínimo', () => {
    montar();

    const visible = texto();
    expect(visible).toContain('Papel Bond');
    expect(visible).toContain('Sede Central');
    expect(visible).toContain('Toner HP');
    expect(visible).toContain('Bodega Norte');
  });

  // -------------------------------------------------------------------------
  // AC-6/AC-7: actividad reciente y atribución
  // -------------------------------------------------------------------------

  it('AC-6/AC-7: muestra la Actividad Reciente con movimientos y su atribución', () => {
    montar();

    const visible = texto();
    expect(visible).toContain('Actividad Reciente');
    expect(visible).toContain('Papel Bond');
    expect(visible).toContain('Instituto Alfa');
  });

  it('AC-7: cada alerta global conserva su institución', () => {
    montar();

    const visible = texto();
    expect(visible).toContain('Instituto Alfa');
    expect(visible).toContain('Instituto Beta');
  });

  // -------------------------------------------------------------------------
  // AC-10: Solicitante sin actividad
  // -------------------------------------------------------------------------

  it('AC-10: el Solicitante no ve actividad y no consulta el historial', () => {
    identidad.set(crearIdentidad('Solicitante'));

    montar(crearDashboardSolicitante());

    expect(texto()).not.toContain('Actividad Reciente');
    httpMock.expectNone(RUTA_MOVIMIENTOS);
  });

  // -------------------------------------------------------------------------
  // AC-15: estados de carga, vacío y error recuperable
  // -------------------------------------------------------------------------

  it('AC-15: durante la carga identifica el estado pendiente', () => {
    fixture.detectChanges();

    const indicador = (fixture.nativeElement as HTMLElement).querySelector(
      '[role="status"]',
    );
    expect(indicador).withContext('indicador de carga').toBeTruthy();

    // Se resuelve la lectura para no dejar peticiones pendientes.
    httpMock.expectOne(RUTA_DASHBOARD).flush(crearDashboard());
    fixture.detectChanges();
  });

  it('AC-15: sin datos muestra ceros y vacíos explícitos', () => {
    montar(crearDashboardVacio());

    const visible = texto();
    expect(visible).toContain('0');
    expect(visible.toLowerCase()).toContain('no hay alertas');
    expect(visible.toLowerCase()).toContain('sin movimientos');
  });

  it('AC-15: ante fallo informa un error recuperable con acción de reintento', () => {
    fixture.detectChanges();

    httpMock
      .expectOne(RUTA_DASHBOARD)
      .flush({ detail: 'boom' }, { status: 500, statusText: 'Server Error' });
    fixture.detectChanges();

    const alerta = (fixture.nativeElement as HTMLElement).querySelector(
      '[role="alert"]',
    );
    expect(alerta).withContext('alerta de error').toBeTruthy();
    expect(botonReintentar()).withContext('botón de reintento').toBeTruthy();
  });

  it('AC-15: el reintento vuelve a pedir el dashboard y limpia el error', () => {
    fixture.detectChanges();

    httpMock
      .expectOne(RUTA_DASHBOARD)
      .flush({ detail: 'boom' }, { status: 500, statusText: 'Server Error' });
    fixture.detectChanges();

    botonReintentar()?.click();
    fixture.detectChanges();

    const reintento = httpMock.expectOne(RUTA_DASHBOARD);
    reintento.flush(crearDashboard());
    fixture.detectChanges();

    expect(
      (fixture.nativeElement as HTMLElement).querySelector('[role="alert"]'),
    ).toBeNull();
  });

  /**
   * Feature 028, T19: el dashboard se suscribe al hub y relee el DTO
   * consolidado de forma silenciosa ante `pedidos`, `inventario` y la marca
   * sintética `dashboard`. El refresco no enciende `cargando`, no muestra el
   * placeholder inicial, conserva los datos previos si falla y no añade
   * lecturas (spec §5.4, AC-12/AC-28).
   */
  describe('actualización en tiempo real (Feature 028, T19)', () => {
    /** Indicador del placeholder de carga inicial, por su rol ARIA. */
    function placeholder(): Element | null {
      return (fixture.nativeElement as HTMLElement).querySelector(
        '[role="status"]',
      );
    }

    it('se suscribe una sola vez a pedidos, inventario y la marca dashboard', () => {
      montar();

      expect(tiempoReal.dominiosSuscritos).toEqual([
        ['pedidos', 'inventario', 'dashboard'],
      ]);
      expect(tiempoReal.suscripcionesActivas).toBe(2);
    });

    it('un frame pedidos relee el dashboard una vez y actualiza KPI, alertas y actividad', fakeAsync(() => {
      montar();
      expect(texto()).toContain('4321');
      httpMock.expectNone(RUTA_DASHBOARD);

      tiempoReal.emitirCambio(['pedidos'], 'alta');

      // La agrupación espera la ventana de silencio de 250 ms.
      tick(249);
      httpMock.expectNone(RUTA_DASHBOARD);

      tick(1);
      const peticiones = httpMock.match(RUTA_DASHBOARD);
      expect(peticiones.length).toBe(1);

      // En vuelo: ni placeholder ni pérdida de los KPI ya visibles.
      fixture.detectChanges();
      expect(fixture.componentInstance.cargando()).toBe(false);
      expect(placeholder()).toBeNull();
      expect(texto()).toContain('4321');

      peticiones[0].flush(crearDashboardActualizado());
      tick();
      fixture.detectChanges();

      // El DTO nuevo reemplaza KPI, alertas y actividad en una sola lectura.
      expect(texto()).toContain('9876');
      expect(texto()).toContain('Grapas Grandes');
      expect(texto()).toContain('Bodega Sur');
      expect(texto()).not.toContain('Papel Bond');
      // El refresco no consulta el historial ni repite la lectura.
      httpMock.expectNone(RUTA_MOVIMIENTOS);
      httpMock.expectNone(RUTA_DASHBOARD);
      expect(placeholder()).toBeNull();
    }));

    it('un frame inventario también refresca el dashboard una vez', fakeAsync(() => {
      montar();

      tiempoReal.emitirCambio(['inventario'], 'movimiento');
      tick(250);

      const peticiones = httpMock.match(RUTA_DASHBOARD);
      expect(peticiones.length).toBe(1);

      peticiones[0].flush(crearDashboardActualizado());
      tick();
      fixture.detectChanges();

      expect(fixture.componentInstance.kpi()?.unidades_en_stock).toBe(9876);
      expect(texto()).toContain('9876');
      httpMock.expectNone(RUTA_MOVIMIENTOS);
    }));

    it('un frame dashboard sintético refresca sin exponer el dominio oculto', fakeAsync(() => {
      montar();

      // La conexión solo conoce la marca: `pedidos`/`inventario` pueden estar
      // ocultos por capacidad y el frame no los nombra (AC-28).
      tiempoReal.emitirCambio(['dashboard'], 'cambio');
      tick(250);

      const peticiones = httpMock.match(RUTA_DASHBOARD);
      expect(peticiones.length).toBe(1);
      expect(tiempoReal.ultimoCambio).toEqual({
        dominios: ['dashboard'],
        motivo: 'cambio',
      });

      peticiones[0].flush(crearDashboardActualizado());
      tick();
      fixture.detectChanges();

      expect(texto()).toContain('9876');
      expect(texto()).toContain('Grapas Grandes');
      // La marca solo invalida el dashboard: ninguna otra lectura (§5.4 regla 7).
      httpMock.expectNone(RUTA_MOVIMIENTOS);
      httpMock.expectNone(RUTA_DASHBOARD);
    }));

    it('una ráfaga de resincronización y cambio comparte el agrupador', fakeAsync(() => {
      montar();

      tiempoReal.emitirCambio(['pedidos'], 'aprobacion');
      tiempoReal.emitirResincronizacion();
      tick(250);

      const peticiones = httpMock.match(RUTA_DASHBOARD);
      expect(peticiones.length).toBe(1);

      peticiones[0].flush(crearDashboardActualizado());
      tick();
    }));

    it('no enciende cargando y un fallo conserva datos y KPI previos', fakeAsync(() => {
      montar();
      const previos = fixture.componentInstance.datos();

      tiempoReal.emitirCambio(['pedidos'], 'retiro');
      tick(250);

      const peticion = httpMock.expectOne(RUTA_DASHBOARD);
      // En vuelo: sin placeholder y con los KPI anteriores a la vista.
      fixture.detectChanges();
      expect(fixture.componentInstance.cargando()).toBe(false);
      expect(placeholder()).toBeNull();
      expect(texto()).toContain('4321');

      peticion.flush(
        { detail: 'boom' },
        { status: 500, statusText: 'Server Error' },
      );
      tick();
      fixture.detectChanges();

      // Un fallo del refresco no borra lo mostrado ni publica error global.
      expect(fixture.componentInstance.datos()).toBe(previos);
      expect(fixture.componentInstance.cargando()).toBe(false);
      expect(fixture.componentInstance.mensajeError()).toBeNull();
      expect(texto()).toContain('4321');
      expect(texto()).not.toContain('No se pudo cargar el dashboard');
      expect(
        (fixture.nativeElement as HTMLElement).querySelector('[role="alert"]'),
      ).toBeNull();

      // El agrupador quedó libre: una nueva invalidación vuelve a releer.
      tiempoReal.emitirCambio(['pedidos'], 'edicion');
      tick(250);
      httpMock.expectOne(RUTA_DASHBOARD).flush(crearDashboardActualizado());
      tick();
      fixture.detectChanges();
      expect(texto()).toContain('9876');
    }));

    it('el Solicitante sigue sin actividad y no consulta /inventario/movimientos', fakeAsync(() => {
      identidad.set(crearIdentidad('Solicitante'));
      montar(crearDashboardSolicitante());

      tiempoReal.emitirCambio(['inventario'], 'movimiento');
      tick(250);

      httpMock.expectOne(RUTA_DASHBOARD).flush(crearDashboardSolicitante());
      tick();
      fixture.detectChanges();

      expect(fixture.componentInstance.actividadDisponible()).toBe(false);
      expect(texto()).not.toContain('Actividad Reciente');
      httpMock.expectNone(RUTA_MOVIMIENTOS);
    }));

    it('ngOnDestroy cancela las suscripciones y el agrupador', fakeAsync(() => {
      montar();
      expect(tiempoReal.suscripcionesActivas).toBe(2);

      // Deja un refresco programado y destruye antes de que dispare.
      tiempoReal.emitirCambio(['pedidos'], 'alta');
      tick(100);
      fixture.destroy();

      expect(tiempoReal.suscripcionesActivas).toBe(0);

      tiempoReal.emitirCambio(['pedidos'], 'alta');
      tiempoReal.emitirResincronizacion();
      tick(1_000);
      httpMock.expectNone(RUTA_DASHBOARD);
    }));
  });
});
