import { provideHttpClient } from '@angular/common/http';
import {
  HttpTestingController,
  TestRequest,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';

import { URL_API } from '../../../shared/config/url-api';
import {
  FacturaCompra,
  OrdenCompra,
  Sede,
} from '../../../shared/interfaces';
import { ListaOrdenesComponent } from './lista-ordenes.component';

const SEDES: Sede[] = [
  { sede_id: 3, nombre: 'Sede Norte', direccion: null, institucion_id: 'INST01', activo: true },
];

const FACTURA: FacturaCompra = {
  factura_compra_id: 5,
  orden_compra_id: 21,
  proveedor_id: 1,
  numero_factura: 'F-2026-001',
  fecha_factura: '2026-11-02',
  monto_total: '150.00',
  observaciones: null,
  fecha_registro: '2026-11-03T10:10:00',
};

function orden(sobrescribir: Partial<OrdenCompra> = {}): OrdenCompra {
  return {
    orden_compra_id: 21,
    numero_oc: null,
    institucion_id: 'INST01',
    sede_id: 3,
    proveedor_id: 1,
    estado: 'Borrador',
    total: '150.00',
    motivo_cancelacion: null,
    cancelado_por_usuario_id: null,
    fecha_creacion: '2026-11-03T10:00:00',
    fecha_emision: null,
    fecha_recepcion: null,
    fecha_cancelacion: null,
    proveedor: {
      proveedor_id: 1,
      rut: '76.543.210-K',
      razon_social: 'Papelera Nacional SpA',
      nombre_fantasia: null,
      giro: null,
      correo: null,
      telefono: null,
      activo: true,
    },
    sede: SEDES[0],
    detalles: [
      {
        detalle_orden_compra_id: 1,
        orden_compra_id: 21,
        producto_id: 7,
        cantidad_solicitada: 10,
        precio_unitario: '15.00',
        producto: null,
      },
    ],
    factura: null,
    ...sobrescribir,
  };
}

/**
 * Feature 020 (T8, AC-3/AC-4/AC-5/AC-12): lista y acciones de OC del Administrador.
 *
 * Seam: el componente con `HttpTestingController`. Se verifica el listado, los
 * filtros como query, las acciones habilitadas por estado, la emisión, la
 * factura (registro y corrección, mismo `PUT`) y la cancelación con motivo.
 */
describe('ListaOrdenesComponent', () => {
  const RUTA_SEDES = `${URL_API}/organizacion/sedes`;
  const RUTA_ORDENES = `${URL_API}/compras/ordenes`;

  let fixture: ComponentFixture<ListaOrdenesComponent>;
  let httpMock: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ListaOrdenesComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        {
          provide: ActivatedRoute,
          useValue: { snapshot: { queryParamMap: convertToParamMap({}) } },
        },
      ],
    }).compileComponents();

    httpMock = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(ListaOrdenesComponent);
  });

  afterEach(() => {
    httpMock.verify({ ignoreCancelled: true });
  });

  function texto(): string {
    return (fixture.nativeElement as HTMLElement).textContent ?? '';
  }

  function peticionOrdenes(): TestRequest {
    return httpMock.expectOne((peticion) => peticion.url === RUTA_ORDENES);
  }

  function montar(ordenes: OrdenCompra[] = [orden()]): void {
    fixture.detectChanges();
    httpMock.expectOne(RUTA_SEDES).flush(SEDES);
    peticionOrdenes().flush(ordenes);
    fixture.detectChanges();
  }

  function botonPorAria(prefijo: string): HTMLButtonElement | undefined {
    return Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll('button'),
    ).find((b) => (b.getAttribute('aria-label') ?? '').startsWith(prefijo));
  }

  it('AC-3: carga sedes y órdenes al inicializar, sin filtros', () => {
    fixture.detectChanges();
    httpMock.expectOne(RUTA_SEDES).flush(SEDES);
    const peticion = peticionOrdenes();
    expect(peticion.request.method).toBe('GET');
    expect(peticion.request.params.keys()).toEqual([]);
    peticion.flush([orden()]);
    fixture.detectChanges();

    expect(texto()).toContain('Papelera Nacional SpA');
    expect(texto()).toContain('Borrador');
  });

  it('AC-3: los filtros de estado y sede viajan como query', () => {
    montar();
    fixture.componentInstance.cambiarFiltroEstado('Facturada');
    const porEstado = peticionOrdenes();
    expect(porEstado.request.params.get('estado')).toBe('Facturada');
    porEstado.flush([]);
    fixture.detectChanges();

    fixture.componentInstance.cambiarFiltroSede('3');
    const porSede = peticionOrdenes();
    expect(porSede.request.params.get('estado')).toBe('Facturada');
    expect(porSede.request.params.get('sede_id')).toBe('3');
    porSede.flush([]);
    fixture.detectChanges();
  });

  it('AC-3/AC-12: el borrador ofrece editar, emitir y cancelar', () => {
    montar([orden({ estado: 'Borrador' })]);
    expect(botonPorAria('Emitir orden')).toBeTruthy();
    expect(botonPorAria('Cancelar orden')).toBeTruthy();
    const editar = Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll('a'),
    ).find((a) => (a.textContent ?? '').includes('Editar'));
    expect(editar?.getAttribute('href')).toBe('/compras/21/editar');
  });

  it('AC-4: emitir pasa la fila a Emitida con su número', () => {
    montar([orden({ estado: 'Borrador' })]);
    botonPorAria('Emitir orden')?.click();
    fixture.detectChanges();

    const peticion = httpMock.expectOne(`${RUTA_ORDENES}/21/emitir`);
    expect(peticion.request.method).toBe('POST');
    peticion.flush(
      orden({ estado: 'Emitida', numero_oc: 'OC-2026-000021', fecha_emision: '2026-11-03T11:00:00' }),
    );
    fixture.detectChanges();

    expect(texto()).toContain('OC-2026-000021');
    expect(texto()).toContain('Emitida');
    expect(texto().toLowerCase()).toContain('emitida');
  });

  it('AC-5: registrar factura abre el modal, hace PUT y pasa a Facturada', () => {
    montar([orden({ estado: 'Emitida', numero_oc: 'OC-2026-000021' })]);
    botonPorAria('Registrar factura')?.click();
    fixture.detectChanges();

    expect(
      (fixture.nativeElement as HTMLElement).querySelector('[role="dialog"]'),
    ).toBeTruthy();

    fixture.componentInstance.formularioFactura.patchValue({
      numero_factura: 'F-2026-001',
      fecha_factura: '2026-11-02',
      monto_total: 150,
      observaciones: 'Conforme',
    });
    fixture.detectChanges();
    const boton = Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll('button'),
    ).find((b) => (b.textContent ?? '').includes('Registrar factura'));
    boton?.click();
    fixture.detectChanges();

    const peticion = httpMock.expectOne(`${RUTA_ORDENES}/21/factura`);
    expect(peticion.request.method).toBe('PUT');
    expect(peticion.request.body).toEqual({
      numero_factura: 'F-2026-001',
      fecha_factura: '2026-11-02',
      monto_total: 150,
      observaciones: 'Conforme',
    });
    peticion.flush(FACTURA);
    fixture.detectChanges();

    expect(texto()).toContain('Facturada');
    expect(texto()).toContain('F-2026-001');
  });

  it('AC-5: en Facturada el botón corrige la misma factura con PUT', () => {
    montar([
      orden({ estado: 'Facturada', numero_oc: 'OC-2026-000021', factura: FACTURA }),
    ]);
    botonPorAria('Editar factura')?.click();
    fixture.detectChanges();

    fixture.componentInstance.formularioFactura.patchValue({ monto_total: 175 });
    fixture.detectChanges();
    const boton = Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll('button'),
    ).find((b) => (b.textContent ?? '').includes('Guardar factura'));
    boton?.click();
    fixture.detectChanges();

    const peticion = httpMock.expectOne(`${RUTA_ORDENES}/21/factura`);
    expect(peticion.request.method).toBe('PUT');
    expect(peticion.request.body.monto_total).toBe(175);
    peticion.flush({ ...FACTURA, monto_total: '175.00' });
    fixture.detectChanges();

    expect(texto()).toContain('Facturada');
  });

  it('AC-12: cancelar exige motivo y envía el POST con el texto', () => {
    montar([orden({ estado: 'Emitida', numero_oc: 'OC-2026-000021' })]);
    botonPorAria('Cancelar orden')?.click();
    fixture.detectChanges();

    // Sin motivo no se llama a la API.
    const confirmar = Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll('button'),
    ).find((b) => (b.textContent ?? '').includes('Confirmar cancelación'));
    confirmar?.click();
    fixture.detectChanges();
    expect(texto()).toContain('El motivo de cancelación es obligatorio.');

    fixture.componentInstance.formularioCancelacion.patchValue({
      motivo_cancelacion: 'Quiebre de stock del proveedor',
    });
    fixture.detectChanges();
    confirmar?.click();
    fixture.detectChanges();

    const peticion = httpMock.expectOne(`${RUTA_ORDENES}/21/cancelar`);
    expect(peticion.request.method).toBe('POST');
    expect(peticion.request.body).toEqual({
      motivo_cancelacion: 'Quiebre de stock del proveedor',
    });
    peticion.flush(
      orden({ estado: 'Cancelada', numero_oc: 'OC-2026-000021', motivo_cancelacion: 'Quiebre de stock del proveedor' }),
    );
    fixture.detectChanges();

    expect(texto()).toContain('Cancelada');
  });

  it('AC-3: una lista vacía muestra el estado vacío', () => {
    montar([]);
    expect(texto()).toContain('No hay órdenes con los filtros actuales');
  });
});
