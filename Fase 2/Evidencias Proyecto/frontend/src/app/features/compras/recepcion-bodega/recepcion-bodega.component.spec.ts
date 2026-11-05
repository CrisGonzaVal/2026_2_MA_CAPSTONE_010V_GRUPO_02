import { provideHttpClient } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';

import { URL_API } from '../../../shared/config/url-api';
import { OrdenCompra, RecepcionRespuesta, Sede } from '../../../shared/interfaces';
import { RecepcionBodegaComponent } from './recepcion-bodega.component';

const SEDE: Sede = {
  sede_id: 3,
  nombre: 'Sede Norte',
  direccion: null,
  institucion_id: 'INST01',
  activo: true,
};

function ordenFacturada(sobrescribir: Partial<OrdenCompra> = {}): OrdenCompra {
  return {
    orden_compra_id: 21,
    numero_oc: 'OC-2026-000021',
    institucion_id: 'INST01',
    sede_id: 3,
    proveedor_id: 1,
    estado: 'Facturada',
    total: '150.00',
    motivo_cancelacion: null,
    cancelado_por_usuario_id: null,
    fecha_creacion: '2026-11-03T10:00:00',
    fecha_emision: '2026-11-03T11:00:00',
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
    sede: SEDE,
    detalles: [
      {
        detalle_orden_compra_id: 1,
        orden_compra_id: 21,
        producto_id: 7,
        cantidad_solicitada: 10,
        precio_unitario: '15.00',
        producto: {
          producto_id: 7,
          nombre: 'Cuaderno linedado',
          descripcion: null,
          unidad_medida: 'UNIDAD',
          stock_minimo: 10,
          categoria_id: 1,
          activo: true,
          categoria: null,
        },
      },
    ],
    factura: {
      factura_compra_id: 5,
      orden_compra_id: 21,
      proveedor_id: 1,
      numero_factura: 'F-2026-001',
      fecha_factura: '2026-11-02',
      monto_total: '150.00',
      observaciones: null,
      fecha_registro: '2026-11-03T10:10:00',
    },
    ...sobrescribir,
  };
}

const RECEPCION: RecepcionRespuesta = {
  orden: { ...ordenFacturada(), estado: 'Recibida', fecha_recepcion: '2026-11-04T09:00:00' },
  estado: 'Recibida',
  fecha_recepcion: '2026-11-04T09:00:00',
  movimientos: [
    {
      movimiento_id: 90,
      producto_id: 7,
      producto_nombre: 'Cuaderno linedado',
      cantidad: 10,
      stock_sede_id: 4,
      stock_actual: 14,
      observacion: 'Recepcion OC-2026-000021',
    },
  ],
  tickets_desbloqueados: [{ ticket_id: 33, asunto: 'Reposición de cuadernos' }],
};

/**
 * Feature 020 (T9, AC-6…AC-11): panel de recepción del Bodeguero.
 *
 * Seam: el componente con `HttpTestingController`. Se verifica el listado (sin
 * filtros, porque el servidor fuerza sede + `Facturada`), la confirmación con
 * `POST` sin cuerpo, el mensaje de éxito exacto, la baja de la OC recepcionada y
 * el aviso de tickets desbloqueados.
 */
describe('RecepcionBodegaComponent', () => {
  const RUTA_ORDENES = `${URL_API}/compras/ordenes`;

  let fixture: ComponentFixture<RecepcionBodegaComponent>;
  let httpMock: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [RecepcionBodegaComponent],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();

    httpMock = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(RecepcionBodegaComponent);
  });

  afterEach(() => {
    httpMock.verify({ ignoreCancelled: true });
  });

  function texto(): string {
    return (fixture.nativeElement as HTMLElement).textContent ?? '';
  }

  function botonPorAria(prefijo: string): HTMLButtonElement | undefined {
    return Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll('button'),
    ).find((b) => (b.getAttribute('aria-label') ?? '').startsWith(prefijo));
  }

  function botonTexto(etiqueta: string): HTMLButtonElement | undefined {
    return Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll('button'),
    ).find((b) => (b.textContent ?? '').includes(etiqueta));
  }

  function montar(ordenes: OrdenCompra[] = [ordenFacturada()]): void {
    fixture.detectChanges();
    const peticion = httpMock.expectOne((p) => p.url === RUTA_ORDENES);
    expect(peticion.request.method).toBe('GET');
    expect(peticion.request.params.keys()).toEqual([]);
    peticion.flush(ordenes);
    fixture.detectChanges();
  }

  it('AC-6: lista las OC facturadas de la sede sin filtros', () => {
    montar();
    const visible = texto();
    expect(visible).toContain('OC-2026-000021');
    expect(visible).toContain('Papelera Nacional SpA');
    expect(visible).toContain('F-2026-001');
    expect(visible).toContain('Cuaderno linedado');
  });

  it('AC-6: sin órdenes facturadas muestra el estado vacío', () => {
    montar([]);
    expect(texto()).toContain('No tienes órdenes facturadas pendientes');
  });

  it('AC-8…AC-10: confirmar la recepción hace POST sin cuerpo y avisa el desbloqueo', () => {
    montar();
    botonPorAria('Recepcionar orden')?.click();
    fixture.detectChanges();

    expect(
      (fixture.nativeElement as HTMLElement).querySelector('[role="dialog"]'),
    ).toBeTruthy();

    botonTexto('Confirmar recepción')?.click();
    fixture.detectChanges();

    const peticion = httpMock.expectOne(`${RUTA_ORDENES}/21/recepcion`);
    expect(peticion.request.method).toBe('POST');
    expect(peticion.request.body).toBeNull();
    peticion.flush(RECEPCION);
    fixture.detectChanges();

    expect(texto()).toContain('Orden de compra recepcionada exitosamente.');
    expect(texto()).toContain('Reposición de cuadernos');
    // La OC recepcionada sale del panel (ya no está `Facturada`).
    expect(texto()).not.toContain('OC-2026-000021');
    expect(
      (fixture.nativeElement as HTMLElement).querySelector('[role="dialog"]'),
    ).toBeNull();
  });

  it('AC-7: un 409 del servidor se muestra con su motivo y conserva la orden', () => {
    montar();
    botonPorAria('Recepcionar orden')?.click();
    fixture.detectChanges();

    botonTexto('Confirmar recepción')?.click();
    fixture.detectChanges();

    httpMock
      .expectOne(`${RUTA_ORDENES}/21/recepcion`)
      .flush(
        { detail: 'El Bodeguero no tiene una sede asignada' },
        { status: 409, statusText: 'Conflict' },
      );
    fixture.detectChanges();

    const alerta = (fixture.nativeElement as HTMLElement).querySelector('[role="alert"]');
    expect(alerta?.textContent).toContain('El Bodeguero no tiene una sede asignada');
    expect(texto()).toContain('OC-2026-000021');
  });
});
