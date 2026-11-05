import { provideHttpClient } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router, convertToParamMap } from '@angular/router';

import { URL_API } from '../../../shared/config/url-api';
import { OrdenCompra, Producto, Proveedor, Sede } from '../../../shared/interfaces';
import { NuevaOrdenComponent } from './nueva-orden.component';

const SEDES: Sede[] = [
  { sede_id: 3, nombre: 'Sede Norte', direccion: null, institucion_id: 'INST01', activo: true },
];

const PROVEEDORES: Proveedor[] = [
  {
    proveedor_id: 1,
    rut: '76.543.210-K',
    razon_social: 'Papelera Nacional SpA',
    nombre_fantasia: null,
    giro: null,
    correo: null,
    telefono: null,
    activo: true,
  },
];

const PRODUCTOS: Producto[] = [
  {
    producto_id: 7,
    nombre: 'Cuaderno linedado',
    descripcion: null,
    unidad_medida: 'UNIDAD',
    stock_minimo: 10,
    categoria_id: 1,
    activo: true,
    categoria: null,
  },
];

function ordenBorrador(sobrescribir: Partial<OrdenCompra> = {}): OrdenCompra {
  return {
    orden_compra_id: 21,
    numero_oc: null,
    institucion_id: 'INST01',
    sede_id: 3,
    proveedor_id: 1,
    estado: 'Borrador',
    total: '50.00',
    motivo_cancelacion: null,
    cancelado_por_usuario_id: null,
    fecha_creacion: '2026-11-03T10:00:00',
    fecha_emision: null,
    fecha_recepcion: null,
    fecha_cancelacion: null,
    proveedor: PROVEEDORES[0],
    sede: SEDES[0],
    detalles: [
      {
        detalle_orden_compra_id: 1,
        orden_compra_id: 21,
        producto_id: 7,
        cantidad_solicitada: 5,
        precio_unitario: '10.00',
        producto: PRODUCTOS[0],
      },
    ],
    factura: null,
    ...sobrescribir,
  };
}

/** Parámetros de la ruta que el doble entrega a cada `ngOnInit`. */
let rutaActual: { id: string | null; query: Record<string, string> } = {
  id: null,
  query: {},
};

function rutaDoble(): unknown {
  return {
    get snapshot() {
      return {
        paramMap: convertToParamMap(rutaActual.id ? { id: rutaActual.id } : {}),
        queryParamMap: convertToParamMap(rutaActual.query),
      };
    },
  };
}

/**
 * Feature 020 (T8, AC-2/AC-3): alta y edición de la OC en borrador.
 *
 * Seam: el componente con `HttpTestingController` y el router espiado. Se cubre
 * la carga de catálogos, la validación reactiva, el cuerpo del POST/PUT, el alta
 * inline de proveedor, la precarga desde necesidades y los bloqueos de edición.
 */
describe('NuevaOrdenComponent', () => {
  const RUTA_SEDES = `${URL_API}/organizacion/sedes`;
  const RUTA_PROVEEDORES = `${URL_API}/compras/proveedores`;
  const RUTA_PRODUCTOS = `${URL_API}/inventario/productos`;
  const RUTA_ORDENES = `${URL_API}/compras/ordenes`;

  let fixture: ComponentFixture<NuevaOrdenComponent>;
  let httpMock: HttpTestingController;
  let router: Router;

  beforeEach(async () => {
    rutaActual = { id: null, query: {} };
    await TestBed.configureTestingModule({
      imports: [NuevaOrdenComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: ActivatedRoute, useValue: rutaDoble() },
      ],
    }).compileComponents();

    httpMock = TestBed.inject(HttpTestingController);
    router = TestBed.inject(Router);
    spyOn(router, 'navigate');
  });

  afterEach(() => {
    httpMock.verify({ ignoreCancelled: true });
  });

  function crear(): NuevaOrdenComponent {
    fixture = TestBed.createComponent(NuevaOrdenComponent);
    return fixture.componentInstance;
  }

  /** Carga los tres catálogos y, en edición, el listado para hallar la OC. */
  function cargarCatalogos(): void {
    fixture.detectChanges();
    httpMock.expectOne(RUTA_SEDES).flush(SEDES);
    httpMock.expectOne(RUTA_PROVEEDORES).flush(PROVEEDORES);
    httpMock.expectOne(RUTA_PRODUCTOS).flush(PRODUCTOS);
    if (rutaActual.id !== null) {
      httpMock.expectOne(RUTA_ORDENES).flush([ordenBorrador()]);
    }
    fixture.detectChanges();
  }

  it('AC-3: carga sedes, proveedores y productos al inicializar', () => {
    const componente = crear();
    fixture.detectChanges();

    const peticionSedes = httpMock.expectOne(RUTA_SEDES);
    expect(peticionSedes.request.method).toBe('GET');
    peticionSedes.flush(SEDES);
    httpMock.expectOne(RUTA_PROVEEDORES).flush(PROVEEDORES);
    httpMock.expectOne(RUTA_PRODUCTOS).flush(PRODUCTOS);
    fixture.detectChanges();

    expect(componente.sedes().length).toBe(1);
    expect(componente.proveedores().length).toBe(1);
    expect(componente.productos().length).toBe(1);
    expect(componente.modoEdicion()).toBeFalse();
    expect(componente.lineas.length).toBe(1);
  });

  it('AC-3: un formulario vacío no envía ninguna orden', () => {
    const componente = crear();
    cargarCatalogos();

    componente.guardar();
    fixture.detectChanges();

    httpMock.expectNone(RUTA_ORDENES);
    expect(componente.formulario.controls.sede_id.touched).toBeTrue();
  });

  it('AC-3: crea la OC con el cuerpo completo y navega al listado', () => {
    const componente = crear();
    cargarCatalogos();

    componente.formulario.patchValue({ sede_id: 3, proveedor_id: 1 });
    componente.lineas.at(0).patchValue({
      producto_id: 7,
      cantidad_solicitada: 5,
      precio_unitario: 10,
    });
    fixture.detectChanges();

    componente.guardar();
    fixture.detectChanges();

    const peticion = httpMock.expectOne(RUTA_ORDENES);
    expect(peticion.request.method).toBe('POST');
    expect(peticion.request.body).toEqual({
      sede_id: 3,
      proveedor_id: 1,
      items: [{ producto_id: 7, cantidad_solicitada: 5, precio_unitario: 10 }],
    });
    peticion.flush(ordenBorrador());
    fixture.detectChanges();

    expect(router.navigate).toHaveBeenCalledWith(['/compras'], {
      queryParams: { exito: 'creada' },
    });
  });

  it('AC-2: el alta inline registra el proveedor y lo selecciona', () => {
    const componente = crear();
    cargarCatalogos();

    componente.alternarAltaProveedor();
    componente.formularioProveedor.patchValue({
      rut: '11.111.111-1',
      razon_social: 'Insumos Nuevos Ltda',
    });
    componente.guardarProveedor();
    fixture.detectChanges();

    const peticion = httpMock.expectOne(RUTA_PROVEEDORES);
    expect(peticion.request.method).toBe('POST');
    expect(peticion.request.body).toEqual({
      rut: '11.111.111-1',
      razon_social: 'Insumos Nuevos Ltda',
      giro: null,
      correo: null,
      telefono: null,
    });
    peticion.flush({
      proveedor_id: 42,
      rut: '11.111.111-1',
      razon_social: 'Insumos Nuevos Ltda',
      nombre_fantasia: null,
      giro: null,
      correo: null,
      telefono: null,
      activo: true,
    });
    fixture.detectChanges();

    expect(componente.proveedores().length).toBe(2);
    expect(componente.formulario.controls.proveedor_id.value).toBe(42);
    expect(componente.mostrarAltaProveedor()).toBeFalse();
  });

  it('AC-3: recalcula el total estimado al agregar líneas', () => {
    const componente = crear();
    cargarCatalogos();

    componente.lineas.at(0).patchValue({
      cantidad_solicitada: 2,
      precio_unitario: 15.5,
    });
    componente.agregarLinea();
    componente.lineas.at(1).patchValue({
      cantidad_solicitada: 1,
      precio_unitario: 10,
    });
    fixture.detectChanges();

    expect(componente.totalEstimado()).toBe(41);
  });

  it('necesidades: precarga sede, producto y cantidad desde el query', () => {
    rutaActual = { id: null, query: { sede_id: '3', producto_id: '7', cantidad: '14' } };
    const componente = crear();
    cargarCatalogos();

    expect(componente.formulario.controls.sede_id.value).toBe(3);
    const linea = componente.lineas.at(0).controls;
    expect(linea.producto_id.value).toBe(7);
    expect(linea.cantidad_solicitada.value).toBe(14);
  });

  it('AC-3: en edición precarga la OC y actualiza con PUT', () => {
    rutaActual = { id: '21', query: {} };
    const componente = crear();
    cargarCatalogos();

    expect(componente.modoEdicion()).toBeTrue();
    expect(componente.formulario.controls.sede_id.value).toBe(3);
    expect(componente.formulario.controls.proveedor_id.value).toBe(1);
    expect(componente.lineas.length).toBe(1);
    expect(componente.lineas.at(0).controls.cantidad_solicitada.value).toBe(5);

    componente.guardar();
    fixture.detectChanges();

    const peticion = httpMock.expectOne(`${RUTA_ORDENES}/21`);
    expect(peticion.request.method).toBe('PUT');
    expect(peticion.request.body.items).toEqual([
      { producto_id: 7, cantidad_solicitada: 5, precio_unitario: 10 },
    ]);
    peticion.flush(ordenBorrador());
    fixture.detectChanges();

    expect(router.navigate).toHaveBeenCalledWith(['/compras'], {
      queryParams: { exito: 'actualizada' },
    });
  });

  it('AC-3: no se edita una orden que ya no está en borrador', () => {
    rutaActual = { id: '21', query: {} };
    const componente = crear();
    fixture.detectChanges();
    httpMock.expectOne(RUTA_SEDES).flush(SEDES);
    httpMock.expectOne(RUTA_PROVEEDORES).flush(PROVEEDORES);
    httpMock.expectOne(RUTA_PRODUCTOS).flush(PRODUCTOS);
    httpMock.expectOne(RUTA_ORDENES).flush([ordenBorrador({ estado: 'Emitida' })]);
    fixture.detectChanges();

    expect(componente.errorCarga()).toContain('Borrador');
  });

  it('AC-3: una orden fuera de alcance se informa sin abrir el formulario', () => {
    rutaActual = { id: '99', query: {} };
    const componente = crear();
    fixture.detectChanges();
    httpMock.expectOne(RUTA_SEDES).flush(SEDES);
    httpMock.expectOne(RUTA_PROVEEDORES).flush(PROVEEDORES);
    httpMock.expectOne(RUTA_PRODUCTOS).flush(PRODUCTOS);
    httpMock.expectOne(RUTA_ORDENES).flush([ordenBorrador({ orden_compra_id: 21 })]);
    fixture.detectChanges();

    expect(componente.errorCarga()).toContain('no existe o no está en tu alcance');
  });
});
