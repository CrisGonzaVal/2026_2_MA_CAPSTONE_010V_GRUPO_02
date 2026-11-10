import { provideHttpClient } from '@angular/common/http';
import {
  HttpTestingController,
  TestRequest,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { URL_API } from '../../../shared/config/url-api';
import {
  CoberturaPreviewRespuesta,
  CoberturaPreviewSolicitud,
  FacturaCompra,
  FacturaCompraRegistrar,
  NecesidadReabastecimiento,
  OrdenCompra,
  OrdenCompraCrear,
  Proveedor,
  ProveedorCrear,
  RecepcionRespuesta,
} from '../../../shared/interfaces';
import { ComprasService } from './compras.service';

const PROVEEDOR: Proveedor = {
  proveedor_id: 1,
  rut: '76.543.210-K',
  razon_social: 'Papelera Nacional SpA',
  nombre_fantasia: 'Papelera Nacional',
  giro: 'Comercio de articulos de oficina',
  correo: 'ventas@papelera.cl',
  telefono: '+56223456789',
  activo: true,
};

const NECESIDAD: NecesidadReabastecimiento = {
  sede_id: 3,
  sede_nombre: 'Sede Norte',
  producto_id: 7,
  nombre: 'Cuaderno linedado',
  stock_actual: 4,
  stock_minimo: 10,
  demanda_tickets: 8,
  sugerido: 14,
};

const ORDEN: OrdenCompra = {
  orden_compra_id: 21,
  numero_oc: 'OC-2026-000021',
  institucion_id: 'inst-los-alpes',
  sede_id: 3,
  proveedor_id: 1,
  estado: 'Emitida',
  total: '150.00',
  motivo_cancelacion: null,
  cancelado_por_usuario_id: null,
  fecha_creacion: '2026-11-03T10:00:00',
  fecha_emision: '2026-11-03T10:05:00',
  fecha_recepcion: null,
  fecha_cancelacion: null,
  proveedor: PROVEEDOR,
  sede: {
    sede_id: 3,
    nombre: 'Sede Norte',
    direccion: 'Av. Norte 123',
    institucion_id: 'inst-los-alpes',
    activo: true,
  },
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
        descripcion: 'Cuaderno de 100 hojas',
        unidad_medida: 'UNIDAD',
        stock_minimo: 10,
        categoria_id: 1,
        activo: true,
        categoria: null,
      },
    },
  ],
  factura: null,
};

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

const RECEPCION: RecepcionRespuesta = {
  orden: { ...ORDEN, estado: 'Recibida', fecha_recepcion: '2026-11-03T12:00:00' },
  estado: 'Recibida',
  fecha_recepcion: '2026-11-03T12:00:00',
  movimientos: [
    {
      movimiento_id: 90,
      producto_id: 7,
      producto_nombre: 'Cuaderno linedado',
      cantidad: 10,
      stock_sede_id: 4,
      stock_actual: 14,
      observacion: 'Recepcion OC-2026-000021 / factura F-2026-001',
    },
  ],
  tickets_desbloqueados: [{ ticket_id: 33, asunto: 'Reposicion de cuadernos' }],
};

/**
 * Contrato HTTP de la Feature 020 (T7).
 *
 * Se cubren las diez rutas del plan §4 a traves de los once metodos publicados:
 * `registrarFactura` y `editarFactura` comparten el mismo `PUT` idempotente,
 * porque el backend crea la factura en `Emitida` y corrige sus metadatos en
 * `Facturada` (AC-5). Las aserciones comparan ruta, metodo, query y cuerpo; no
 * prueban la logica del servidor, solo que el cliente hable el contrato.
 */
describe('ComprasService (Feature 020)', () => {
  const RUTA_NECESIDADES = `${URL_API}/compras/necesidades`;
  const RUTA_PROVEEDORES = `${URL_API}/compras/proveedores`;
  const RUTA_ORDENES = `${URL_API}/compras/ordenes`;

  let servicio: ComprasService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    servicio = TestBed.inject(ComprasService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  /** Selecciona por ruta sin query: `expectOne(string)` exige la URL exacta. */
  function peticionA(ruta: string): TestRequest {
    return httpMock.expectOne((peticion) => peticion.url === ruta);
  }

  // --- AC-1: necesidades ---------------------------------------------------

  it('listarNecesidades pide GET sin query cuando no se informa sede', () => {
    const recibidas: NecesidadReabastecimiento[][] = [];
    servicio.listarNecesidades().subscribe((filas) => recibidas.push(filas));

    const peticion = peticionA(RUTA_NECESIDADES);
    expect(peticion.request.method).toBe('GET');
    expect(peticion.request.params.keys()).toEqual([]);
    expect(peticion.request.body).toBeNull();
    peticion.flush([NECESIDAD]);

    expect(recibidas).toEqual([[NECESIDAD]]);
  });

  it('listarNecesidades envia sede_id como query y omite null (AC-1)', () => {
    servicio.listarNecesidades(3).subscribe();
    const conSede = peticionA(RUTA_NECESIDADES);
    expect(conSede.request.params.get('sede_id')).toBe('3');
    conSede.flush([]);

    servicio.listarNecesidades(null).subscribe();
    const sinSede = peticionA(RUTA_NECESIDADES);
    expect(sinSede.request.params.keys()).toEqual([]);
    sinSede.flush([]);
  });

  // --- AC-2: catalogo global de proveedores --------------------------------

  it('listarProveedores hace GET /compras/proveedores sin parametros', () => {
    const recibidos: Proveedor[][] = [];
    servicio.listarProveedores().subscribe((filas) => recibidos.push(filas));

    const peticion = peticionA(RUTA_PROVEEDORES);
    expect(peticion.request.method).toBe('GET');
    expect(peticion.request.params.keys()).toEqual([]);
    peticion.flush([PROVEEDOR]);

    expect(recibidos).toEqual([[PROVEEDOR]]);
  });

  it('crearProveedor envia POST con el cuerpo de alta (AC-2)', () => {
    const datos: ProveedorCrear = {
      rut: '76.543.210-K',
      razon_social: 'Papelera Nacional SpA',
      correo: 'ventas@papelera.cl',
    };
    servicio.crearProveedor(datos).subscribe();

    const peticion = peticionA(RUTA_PROVEEDORES);
    expect(peticion.request.method).toBe('POST');
    expect(peticion.request.body).toEqual(datos);
    peticion.flush(PROVEEDOR, { status: 201, statusText: 'Created' });
  });

  // --- AC-3/AC-4: orden de compra ------------------------------------------

  it('crearOrden envia POST /compras/ordenes con sede, proveedor e items', () => {
    const datos: OrdenCompraCrear = {
      sede_id: 3,
      proveedor_id: 1,
      items: [
        { producto_id: 7, cantidad_solicitada: 10, precio_unitario: 15 },
      ],
    };
    servicio.crearOrden(datos).subscribe();

    const peticion = peticionA(RUTA_ORDENES);
    expect(peticion.request.method).toBe('POST');
    expect(peticion.request.body).toEqual(datos);
    peticion.flush(ORDEN, { status: 201, statusText: 'Created' });
  });

  it('actualizarOrden envia PUT a la ruta de la OC con el reemplazo completo', () => {
    const datos: OrdenCompraCrear = {
      sede_id: 3,
      proveedor_id: 1,
      items: [{ producto_id: 7, cantidad_solicitada: 5 }],
    };
    servicio.actualizarOrden(21, datos).subscribe();

    const peticion = peticionA(`${RUTA_ORDENES}/21`);
    expect(peticion.request.method).toBe('PUT');
    expect(peticion.request.body).toEqual(datos);
    peticion.flush(ORDEN);
  });

  it('emitirOrden envia POST sin cuerpo a /emitir (AC-4)', () => {
    servicio.emitirOrden(21).subscribe();

    const peticion = peticionA(`${RUTA_ORDENES}/21/emitir`);
    expect(peticion.request.method).toBe('POST');
    expect(peticion.request.body).toBeNull();
    peticion.flush(ORDEN);
  });

  it('listarOrdenes envia estado y sede_id como query cuando se informan (AC-3)', () => {
    servicio.listarOrdenes({ estado: 'Facturada', sede_id: 3 }).subscribe();

    const peticion = peticionA(RUTA_ORDENES);
    expect(peticion.request.method).toBe('GET');
    expect(peticion.request.params.get('estado')).toBe('Facturada');
    expect(peticion.request.params.get('sede_id')).toBe('3');
    peticion.flush([ORDEN]);
  });

  it('listarOrdenes no envia filtros vacios ni nulos (AC-3, AC-6)', () => {
    servicio.listarOrdenes().subscribe();
    const sinFiltros = peticionA(RUTA_ORDENES);
    expect(sinFiltros.request.params.keys()).toEqual([]);
    sinFiltros.flush([]);

    servicio.listarOrdenes({ estado: null, sede_id: null }).subscribe();
    const conNulos = peticionA(RUTA_ORDENES);
    expect(conNulos.request.params.keys()).toEqual([]);
    conNulos.flush([]);
  });

  // --- AC-5: factura del proveedor -----------------------------------------

  it('registrarFactura envia PUT con el cuerpo de la factura (AC-5)', () => {
    const datos: FacturaCompraRegistrar = {
      numero_factura: 'F-2026-001',
      fecha_factura: '2026-11-02',
      monto_total: 150,
      observaciones: null,
    };
    servicio.registrarFactura(21, datos).subscribe();

    const peticion = peticionA(`${RUTA_ORDENES}/21/factura`);
    expect(peticion.request.method).toBe('PUT');
    expect(peticion.request.body).toEqual(datos);
    peticion.flush(FACTURA);
  });

  it('editarFactura usa el mismo PUT idempotente que registrarFactura (AC-5)', () => {
    const datos: FacturaCompraRegistrar = {
      numero_factura: 'F-2026-001',
      fecha_factura: '2026-11-02',
      monto_total: 175.5,
    };
    servicio.editarFactura(21, datos).subscribe();

    const peticion = peticionA(`${RUTA_ORDENES}/21/factura`);
    expect(peticion.request.method).toBe('PUT');
    expect(peticion.request.body).toEqual(datos);
    peticion.flush({ ...FACTURA, monto_total: '175.50' });
  });

  // --- AC-7…AC-11: recepcion fisica ----------------------------------------

  it('recepcionar envia POST sin cuerpo y devuelve movimientos y tickets (AC-8…AC-10)', () => {
    const recibidas: RecepcionRespuesta[] = [];
    servicio.recepcionar(21).subscribe((respuesta) => recibidas.push(respuesta));

    const peticion = peticionA(`${RUTA_ORDENES}/21/recepcion`);
    expect(peticion.request.method).toBe('POST');
    expect(peticion.request.body).toBeNull();
    peticion.flush(RECEPCION);

    expect(recibidas).toEqual([RECEPCION]);
  });

  // --- AC-12: cancelacion ---------------------------------------------------

  it('cancelarOrden envia POST con el motivo obligatorio (AC-12)', () => {
    servicio.cancelarOrden(21, 'Quiebre de stock del proveedor').subscribe();

    const peticion = peticionA(`${RUTA_ORDENES}/21/cancelar`);
    expect(peticion.request.method).toBe('POST');
    expect(peticion.request.body).toEqual({
      motivo_cancelacion: 'Quiebre de stock del proveedor',
    });
    peticion.flush({ ...ORDEN, estado: 'Cancelada' });
  });

  // --- Feature 021 (AC-2): preview de cobertura -----------------------------

  it('previsualizarCobertura envia POST con sede e items y devuelve la simulacion', () => {
    const datos: CoberturaPreviewSolicitud = {
      sede_id: 4,
      items: [{ producto_id: 7, cantidad_solicitada: 10 }],
    };
    const respuesta: CoberturaPreviewRespuesta = {
      sede_id: 4,
      sede_nombre: 'Sede Central',
      productos: [
        {
          producto_id: 7,
          producto_nombre: 'Cuaderno linedado',
          cantidad_simulada: 10,
          demanda_total: 12,
          cubierto_previo: 0,
          asignado: 10,
          faltante: 2,
          sin_asignar: 0,
          tickets: [
            {
              ticket_id: 33,
              asunto: 'Reposicion de cuadernos',
              solicitante_nombre: 'Isabel',
              solicitante_apellido: 'Contreras',
              prioridad_nombre: 'ALTA',
              fecha_creacion: '2026-11-01T09:00:00',
              solicitado: 12,
              cubierto_plan: 0,
              cubierto_stock: 0,
              necesidad: 12,
              asignada: 10,
              faltante: 2,
              cobertura: 'parcial',
            },
          ],
        },
      ],
    };
    const recibidas: CoberturaPreviewRespuesta[] = [];
    servicio
      .previsualizarCobertura(datos)
      .subscribe((cuerpo) => recibidas.push(cuerpo));

    const peticion = peticionA(`${URL_API}/compras/cobertura/preview`);
    expect(peticion.request.method).toBe('POST');
    expect(peticion.request.body).toEqual(datos);
    peticion.flush(respuesta);

    expect(recibidas).toEqual([respuesta]);
  });
});
