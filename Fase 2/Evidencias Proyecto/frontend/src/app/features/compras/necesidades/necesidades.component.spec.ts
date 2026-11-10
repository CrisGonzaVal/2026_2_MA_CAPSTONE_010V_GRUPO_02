import { provideHttpClient } from '@angular/common/http';
import {
  HttpTestingController,
  TestRequest,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { URL_API } from '../../../shared/config/url-api';
import { NecesidadReabastecimiento, Sede } from '../../../shared/interfaces';
import { NecesidadesComponent } from './necesidades.component';

const SEDES: Sede[] = [
  { sede_id: 1, nombre: 'Sede Central', direccion: null, institucion_id: 'INST01', activo: true },
  { sede_id: 3, nombre: 'Sede Norte', direccion: null, institucion_id: 'INST01', activo: true },
];

function necesidad(
  sobrescribir: Partial<NecesidadReabastecimiento> = {},
): NecesidadReabastecimiento {
  return {
    sede_id: 1,
    sede_nombre: 'Sede Central',
    producto_id: 7,
    nombre: 'Cuaderno linedado',
    stock_actual: 4,
    stock_minimo: 10,
    demanda_tickets: 8,
    sugerido: 14,
    ...sobrescribir,
  };
}

/**
 * Feature 020 (T8, AC-1): consolidado de necesidades del Administrador.
 *
 * Seam: la interfaz pública del componente con peticiones reales bajo
 * `HttpTestingController`. Se verifica el render de la tabla, el filtro por sede
 * como query (nunca 404), los estados vacío/error y el enlace de creación.
 */
describe('NecesidadesComponent', () => {
  const RUTA_SEDES = `${URL_API}/organizacion/sedes`;
  const RUTA_NECESIDADES = `${URL_API}/compras/necesidades`;

  let fixture: ComponentFixture<NecesidadesComponent>;
  let httpMock: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [NecesidadesComponent],
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
    }).compileComponents();

    httpMock = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(NecesidadesComponent);
  });

  afterEach(() => {
    httpMock.verify({ ignoreCancelled: true });
  });

  function texto(): string {
    return (fixture.nativeElement as HTMLElement).textContent ?? '';
  }

  function peticionNecesidades(): TestRequest {
    return httpMock.expectOne((peticion) => peticion.url === RUTA_NECESIDADES);
  }

  function montar(filas: NecesidadReabastecimiento[] = [necesidad()]): void {
    fixture.detectChanges();
    httpMock.expectOne(RUTA_SEDES).flush(SEDES);
    peticionNecesidades().flush(filas);
    fixture.detectChanges();
  }

  it('AC-1: carga sedes y necesidades al inicializar, sin query por defecto', () => {
    fixture.detectChanges();
    httpMock.expectOne(RUTA_SEDES).flush(SEDES);
    const peticion = peticionNecesidades();
    expect(peticion.request.method).toBe('GET');
    expect(peticion.request.params.keys()).toEqual([]);
    peticion.flush([necesidad()]);
    fixture.detectChanges();

    expect(texto()).toContain('Cuaderno linedado');
    expect(texto()).toContain('Sede Central');
  });

  it('AC-1: renderiza stock, mínimo, demanda y sugerido de cada fila', () => {
    montar([
      necesidad({ stock_actual: 4, stock_minimo: 10, demanda_tickets: 8, sugerido: 14 }),
    ]);
    const visible = texto();
    expect(visible).toContain('Stock mínimo');
    expect(visible).toContain('Demanda en curso');
    expect(visible).toContain('Sugerido');
    expect(visible).toContain('14');
  });

  it('AC-1: el filtro por sede viaja como query y admite «todas»', () => {
    montar();
    fixture.componentInstance.filtrarPorSede('3');
    const conSede = peticionNecesidades();
    expect(conSede.request.params.get('sede_id')).toBe('3');
    conSede.flush([necesidad({ sede_id: 3, sede_nombre: 'Sede Norte' })]);
    fixture.detectChanges();
    expect(texto()).toContain('Sede Norte');

    fixture.componentInstance.filtrarPorSede('');
    const todas = peticionNecesidades();
    expect(todas.request.params.has('sede_id')).toBe(false);
    todas.flush([]);
    fixture.detectChanges();
  });

  it('AC-1: una lista vacía no es un error y muestra el estado vacío', () => {
    montar([]);
    expect(texto()).toContain('No hay necesidades con el filtro actual');
  });

  it('AC-1: un fallo se muestra con su motivo y ofrece reintentar', () => {
    fixture.detectChanges();
    httpMock.expectOne(RUTA_SEDES).flush(SEDES);
    peticionNecesidades().flush(
      { detail: 'Sin permiso de compras' },
      { status: 403, statusText: 'Forbidden' },
    );
    fixture.detectChanges();

    const alerta = (fixture.nativeElement as HTMLElement).querySelector('[role="alert"]');
    expect(alerta?.textContent).toContain('Sin permiso de compras');

    fixture.componentInstance.reintentar();
    httpMock.expectOne(RUTA_SEDES).flush(SEDES);
    peticionNecesidades().flush([necesidad()]);
    fixture.detectChanges();
    expect(texto()).toContain('Cuaderno linedado');
  });

  it('AC-1: la fila con sugerido positivo enlaza a crear una OC precargada', () => {
    montar([necesidad({ sede_id: 3, producto_id: 9, sugerido: 14 })]);
    const enlace = Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll('a'),
    ).find((a) => (a.textContent ?? '').includes('Crear OC'));

    expect(enlace?.getAttribute('href')).toContain('/compras/nueva');
    expect(enlace?.getAttribute('href')).toContain('sede_id=3');
    expect(enlace?.getAttribute('href')).toContain('producto_id=9');
    expect(enlace?.getAttribute('href')).toContain('cantidad=14');
  });

  // --- Feature 021 (T11, AC-1): comprometido, borrador y pedidos -----------

  it('AC-1: muestra el comprometido y el borrador como columnas separadas', () => {
    montar([necesidad({ stock_comprometido: 4, stock_borrador: 2 })]);

    const visible = texto();
    expect(visible).toContain('Comprometido');
    expect(visible).toContain('Borrador');
    expect(visible).toContain('Comprometido = OC emitidas/facturadas');
    expect(visible).toContain('Borrador no descuenta el sugerido');
  });

  it('AC-1: cada pedido que compone la demanda aparece en una subfila', () => {
    montar([
      necesidad({
        stock_comprometido: 3,
        tickets: [
          {
            ticket_id: 33,
            asunto: 'Reposición de cuadernos',
            solicitante_nombre: 'Isabel',
            solicitante_apellido: 'Contreras',
            solicitante_correo: null,
            prioridad_nombre: 'ALTA',
            fecha_creacion: '2026-11-01T09:00:00',
            cantidad_solicitada: 8,
            cantidad_cubierta: 3,
            cantidad_faltante: 5,
          },
        ],
      }),
    ]);

    const visible = texto();
    expect(visible).toContain('Pedido');
    expect(visible).toContain('#33');
    expect(visible).toContain('Reposición de cuadernos');
    expect(visible).toContain('Contreras, Isabel');
    expect(visible).toContain('ALTA');
    expect(visible).toContain('Subtotal solicitado');
    expect(visible).toContain('Subtotal cubierto');
    expect(visible).toContain('Subtotal faltante');
  });

  it('AC-1: un sugerido 0 se presenta como cubierto y no enlaza a crear OC', () => {
    montar([necesidad({ sugerido: 0, stock_comprometido: 14 })]);
    const visible = texto();
    expect(visible).toContain('Cubierto');

    const enlaceCrear = Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll('a'),
    ).find((a) => (a.textContent ?? '').includes('Crear OC'));
    expect(enlaceCrear).toBeUndefined();
  });
});
