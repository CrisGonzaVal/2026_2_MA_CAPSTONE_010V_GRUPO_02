import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed, fakeAsync, tick } from '@angular/core/testing';
import { WritableSignal, signal } from '@angular/core';
import { ActivatedRoute, convertToParamMap } from '@angular/router';
import { of } from 'rxjs';

import { URL_API } from '../../shared/config/url-api';
import { AutenticacionService } from '../../core/services/auth.service';
import { TiempoRealService } from '../../core/services/tiempo-real.service';
import type {
  CambioTiempoReal,
  DominioTiempoReal,
  MotivoTiempoReal,
} from '../../core/services/tiempo-real.service';
import {
  CatalogosTicket,
  HistorialTransicion,
  IdentidadAutenticada,
  TicketDetalle,
} from '../../shared/interfaces';
import { TicketDetalleComponent } from './ticket-detalle.component';

const RUTA_DETALLE = `${URL_API}/tickets/7`;
const RUTA_HISTORIAL = `${URL_API}/tickets/7/historial`;
const RUTA_CATALOGOS = `${URL_API}/tickets/catalogos`;
const RUTA_APROBACION = `${URL_API}/tickets/7/aprobacion`;
const RUTA_RETIRO = `${URL_API}/tickets/7/retiro`;
const RUTA_CONFIRMACION_ENTREGA = `${URL_API}/tickets/7/confirmacion-entrega`;
const RUTA_ANULACION = `${URL_API}/tickets/7/anulacion`;
const RUTA_RECHAZO = `${URL_API}/tickets/7/rechazo`;

/**
 * Catálogo canónico de la enmienda 26/Nov/2026 (D-35): `EnRevision` es el único
 * estado inicial y los terminales `Cerrado` y `Anulado` cierran el flujo.
 */
const CATALOGOS_013: CatalogosTicket = {
  prioridades: [
    { prioridad_id: 1, nombre: 'Alta', descripcion: 'Corto plazo' },
    { prioridad_id: 2, nombre: 'Media', descripcion: 'Reposición' },
  ],
  estados: [
    { estado_id: 1, nombre: 'EnRevision', descripcion: 'En revisión' },
    { estado_id: 2, nombre: 'EnCurso', descripcion: 'En preparación' },
    { estado_id: 3, nombre: 'Cerrado', descripcion: 'Retirado' },
    { estado_id: 4, nombre: 'Anulado', descripcion: 'Anulado o rechazado' },
  ],
  productos: [
    {
      producto_id: 1,
      nombre: 'Cuaderno rayado',
      unidad_medida: 'UNIDAD',
      categoria_nombre: 'Papelería',
      stock_total: 50,
      es_critico: false,
    },
    {
      producto_id: 2,
      nombre: 'Toner HP 26A',
      unidad_medida: 'UNIDAD',
      categoria_nombre: 'Tóner',
      stock_total: 3,
      es_critico: true,
    },
  ],
  solicitantes: [
    {
      usuario_id: 5,
      nombre: 'Isabel',
      apellido: 'Contreras',
      correo: 'isabel.contreras@losalpes.cl',
      departamento_nombre: 'Docencia',
    },
    {
      usuario_id: 1,
      nombre: 'Camila',
      apellido: 'Fernandez',
      correo: 'camila.fernandez@losalpes.cl',
      departamento_nombre: 'Dirección',
    },
  ],
};

const PRODUCTO_DETALLE = {
  producto_id: 1,
  nombre: 'Cuaderno rayado',
  descripcion: null,
  unidad_medida: 'UNIDAD',
  stock_minimo: 5,
  categoria_id: 1,
  // Feature 014: el estado viaja en el recurso; el fixture solo lo declara.
  activo: true,
  categoria: null,
};

/**
 * Enmienda 26/Nov/2026 (D-35/AC-62): catálogo de cuatro estados con
 * `EnRevision` como único inicial. Los ids son solo los de la semilla; el
 * componente resuelve por nombre.
 */
const CATALOGOS_RETIRO: CatalogosTicket = {
  ...CATALOGOS_013,
  estados: [
    { estado_id: 1, nombre: 'EnRevision', descripcion: 'En revisión' },
    { estado_id: 2, nombre: 'EnCurso', descripcion: 'En preparación' },
    { estado_id: 3, nombre: 'Cerrado', descripcion: 'Retirado' },
    { estado_id: 4, nombre: 'Anulado', descripcion: 'Anulado o rechazado' },
  ],
};

/**
 * Producto retirado del catálogo (Feature 014): el backend ya no lo devuelve en
 * `GET /tickets/catalogos`, pero sigue resolviéndose en el detalle histórico del
 * ticket, que es justo lo que permite conservar el ítem (AC-9).
 */
const PRODUCTO_INACTIVO_DETALLE = { ...PRODUCTO_DETALLE, activo: false };

/** Catálogo operativo sin el producto 1: el servidor filtra al inactivo. */
const CATALOGOS_SIN_PRODUCTO_1: CatalogosTicket = {
  ...CATALOGOS_013,
  productos: CATALOGOS_013.productos.filter((producto) => producto.producto_id !== 1),
};

/** Detalle base: `EnRevision`, del Solicitante dueño (usuario 5), con un ítem. */
function crearDetalle(estado_id = 1, usuario_id = 5): TicketDetalle {
  return {
    ticket_id: 7,
    usuario_id,
    prioridad_id: 1,
    estado_id,
    asunto: 'Falta de papel para el trimestre',
    descripcion: 'Se solicita papel oficio para impresiones.',
    fecha_creacion: '2026-10-10T09:00:00',
    fecha_cierre: null,
    sede_id: 3,
    sede_nombre: 'Sede Central',
    detalles: [
      {
        detalle_ticket_id: 10,
        producto_id: 1,
        cantidad_solicitada: 3,
        cantidad_entregada: 1,
        producto: PRODUCTO_DETALLE,
      },
    ],
    estado_nombre: CATALOGOS_013.estados[estado_id - 1].nombre,
  };
}

/** Detalle con su único ítem apuntando a un producto ya retirado (AC-9). */
function crearDetalleConProductoInactivo(): TicketDetalle {
  const detalle = crearDetalle(1);
  detalle.detalles[0].producto = PRODUCTO_INACTIVO_DETALLE;
  return detalle;
}

/** Detalle del catálogo de la enmienda: `1 EnRevision`, `2 EnCurso`, `3 Cerrado`, `4 Anulado`. */
function crearDetalleRetiro(estado_id = 1, usuario_id = 5): TicketDetalle {
  const detalle = crearDetalle(1, usuario_id);
  detalle.estado_id = estado_id;
  detalle.estado_nombre = CATALOGOS_RETIRO.estados[estado_id - 1].nombre;
  return detalle;
}

/** Historial base: creación (origen nulo) + transición a `EnRevision` con motivo. */
function crearHistorial(): HistorialTransicion[] {
  return [
    {
      historial_transicion_id: 1,
      ticket_id: 7,
      estado_origen_id: null,
      estado_destino_id: 1,
      usuario_id: 5,
      fecha_transicion: '2026-10-10T09:00:00',
      motivo: null,
      estado_origen_nombre: null,
      estado_destino_nombre: 'EnRevision',
      usuario_nombre: 'Isabel',
      usuario_apellido: 'Contreras',
    },
    {
      historial_transicion_id: 2,
      ticket_id: 7,
      estado_origen_id: 1,
      estado_destino_id: 1,
      usuario_id: 9,
      fecha_transicion: '2026-10-11T10:00:00',
      motivo: 'Revisión inicial del requerimiento',
      estado_origen_nombre: 'EnRevision',
      estado_destino_nombre: 'EnRevision',
      usuario_nombre: 'Bruno',
      usuario_apellido: 'Soto',
    },
  ];
}

/**
 * Doble del hub de tiempo real (Feature 028, T15) para el detalle. Registra
 * las suscripciones —cambio y resincronización— y permite emitir frames a mano
 * sin abrir `fetch` ni tocar la sesión de Clerk.
 */
class TiempoRealServiceFalso {
  readonly dominiosSuscritos: Array<readonly DominioTiempoReal[]> = [];

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

describe('TicketDetalleComponent', () => {
  let fixture: ComponentFixture<TicketDetalleComponent>;
  let componente: TicketDetalleComponent;
  let httpMock: HttpTestingController;
  let raiz: HTMLElement;

  /** Identidad local (`/auth/me`) que el componente lee para condicionar la UI. */
  let identidad: WritableSignal<IdentidadAutenticada | null>;

  /** Hub de tiempo real falso (Feature 028, T18). */
  let tiempoReal: TiempoRealServiceFalso;

  function crearIdentidad(rol: string, usuario_id = 9): IdentidadAutenticada {
    return {
      usuario_id,
      sub: 'user_detalle',
      nombre: 'Bruno',
      apellido: 'Soto',
      correo: 'bruno.soto@losalpes.cl',
      rol,
      institucion: { institucion_id: 'inst-los-alpes', nombre: 'Los Alpes' },
      sede: null,
      departamento: null,
    };
  }

  /** Responde las tres peticiones del arranque de la vista. */
  function responderCarga(
    detalle: TicketDetalle | null = crearDetalle(),
    historial: HistorialTransicion[] = crearHistorial(),
    catalogos: CatalogosTicket = CATALOGOS_013,
  ) {
    if (detalle === null) {
      // `forkJoin` cancela las otras dos peticiones al fallar el detalle; se
      // descartan del controlador para que `verify` no las cuente como abiertas.
      httpMock
        .expectOne(RUTA_DETALLE)
        .flush({ detail: 'Ticket no encontrado' }, { status: 404, statusText: 'Not Found' });
      httpMock.match(RUTA_HISTORIAL);
      httpMock.match(RUTA_CATALOGOS);
      fixture.detectChanges();
      return;
    }
    httpMock.expectOne(RUTA_DETALLE).flush(detalle);
    httpMock.expectOne(RUTA_HISTORIAL).flush(historial);
    httpMock.expectOne(RUTA_CATALOGOS).flush(catalogos);
    fixture.detectChanges();
  }

  /** Responde la reconsulta silenciosa de detalle + historial tras una mutación. */
  function responderReconsulta(
    detalle: TicketDetalle = crearDetalle(1),
    historial: HistorialTransicion[] = crearHistorial(),
  ) {
    httpMock.expectOne(RUTA_DETALLE).flush(detalle);
    httpMock.expectOne(RUTA_HISTORIAL).flush(historial);
    fixture.detectChanges();
  }

  /** Botón cuyo texto visible coincide (más preciso que un índice de CSS). */
  function boton(texto: string): HTMLButtonElement | null {
    const botones = Array.from(raiz.querySelectorAll<HTMLButtonElement>('button'));
    return (
      botones.find((b) => (b.textContent ?? '').replace(/\s+/g, ' ').trim() === texto) ?? null
    );
  }

  /** Botones de acciones visibles en la página (excluye los de los diálogos). */
  function botonesAccion(): string[] {
    return Array.from(raiz.querySelectorAll('button'))
      .filter((b) => b.closest('dialog') === null)
      .map((b) => (b.textContent ?? '').replace(/\s+/g, ' ').trim());
  }

  function textoRaiz(): string {
    return (raiz.textContent ?? '').replace(/\s+/g, ' ');
  }

  /** Texto de la página sin el contenido (oculto) de los diálogos. */
  function textoPagina(): string {
    const clon = raiz.cloneNode(true) as HTMLElement;
    clon.querySelectorAll('dialog').forEach((dialogo) => dialogo.remove());
    return (clon.textContent ?? '').replace(/\s+/g, ' ');
  }

  function dialogos(): HTMLDialogElement[] {
    return Array.from(raiz.querySelectorAll<HTMLDialogElement>('dialog'));
  }

  function dialogoConfirmacion(): HTMLDialogElement {
    return dialogos()[0];
  }

  function dialogoEdicion(): HTMLDialogElement {
    return dialogos()[1];
  }

  function alertas(): string[] {
    return Array.from(raiz.querySelectorAll('[role="alert"]')).map((n) =>
      (n.textContent ?? '').replace(/\s+/g, ' ').trim(),
    );
  }

  function avisoExito(texto: string): boolean {
    return Array.from(raiz.querySelectorAll('[role="status"]')).some((n) =>
      (n.textContent ?? '').replace(/\s+/g, ' ').includes(texto),
    );
  }

  beforeEach(async () => {
    identidad = signal<IdentidadAutenticada | null>(crearIdentidad('Administrador'));
    tiempoReal = new TiempoRealServiceFalso();

    await TestBed.configureTestingModule({
      imports: [TicketDetalleComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: AutenticacionService, useValue: { identidad } },
        { provide: TiempoRealService, useValue: tiempoReal },
        {
          provide: ActivatedRoute,
          useValue: { paramMap: of(convertToParamMap({ ticketId: '7' })) },
        },
      ],
    }).compileComponents();

    httpMock = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(TicketDetalleComponent);
    componente = fixture.componentInstance;
    raiz = fixture.nativeElement as HTMLElement;
  });

  afterEach(() => {
    httpMock.verify({ ignoreCancelled: true });
  });

  // ---------------------------------------------------------------------------
  // Carga y render (AC-23)
  // ---------------------------------------------------------------------------

  describe('carga y cabecera', () => {
    it('carga detalle, historial y catálogos al abrir la vista', () => {
      responderCarga();

      expect(componente.ticket()).not.toBeNull();
      expect(componente.historial().length).toBe(2);
      expect(componente.catalogos()).not.toBeNull();
      expect(componente.cargando()).toBe(false);
      expect(componente.errorCarga()).toBeNull();
    });

    it('muestra cabecera con asunto, prioridad, estado, solicitante, departamento, sede y fechas', () => {
      responderCarga();

      const texto = textoRaiz();
      expect(texto).toContain('Falta de papel para el trimestre');
      expect(texto).toContain('Alta');
      expect(texto).toContain('En Revisión');
      expect(texto).toContain('Contreras, Isabel');
      expect(texto).toContain('isabel.contreras@losalpes.cl');
      expect(texto).toContain('Docencia');
      expect(texto).toContain('Sede Central');
      expect(texto).toContain('2026');
      // Sin `fecha_cierre` no aparece el bloque de cierre.
      expect(texto).not.toContain('Cerrado');
    });

    it('muestra la fecha de cierre solo cuando existe', () => {
      const conCierre = crearDetalle();
      conCierre.fecha_cierre = '2026-10-12T15:30:00';
      responderCarga(conCierre);

      expect(textoRaiz()).toContain('Cerrado');
    });

    it('muestra los ítems con cantidades solicitadas y entregadas', () => {
      responderCarga();

      const texto = textoRaiz();
      expect(texto).toContain('Cuaderno rayado');
      expect(texto).toContain('Solicitado');
      expect(texto).toContain('Entregado');
      expect(texto).toContain('3');
      expect(texto).toContain('1');
    });

    it('AC-11: muestra el aviso de stock disponible cuando el backend lo marca', () => {
      const conStock = crearDetalle();
      conStock.stock_disponible = true;
      responderCarga(conStock);

      expect(textoRaiz()).toContain('Stock disponible — Listo para el retiro');
    });

    it('AC-11: sin stock disponible no muestra el aviso', () => {
      responderCarga(crearDetalle());

      expect(textoRaiz()).not.toContain('Stock disponible');
    });

    it('muestra el historial completo con actor, de→a, instante y motivo', () => {
      responderCarga();

      const texto = textoRaiz();
      expect(texto).toContain('Creación → En Revisión');
      // Feature 021 (V-3): el historial separa las palabras del estado.
      expect(texto).toContain('En Revisión → En Revisión');
      expect(texto).toContain('Contreras, Isabel');
      expect(texto).toContain('Soto, Bruno');
      expect(texto).toContain('Revisión inicial del requerimiento');
    });

    it('diferencia el historial vacío de un error', () => {
      responderCarga(crearDetalle(), []);

      expect(textoRaiz()).toContain('Sin transiciones registradas');
      expect(alertas()).toEqual([]);
    });

    it('diferencia los ítems vacíos', () => {
      const sinItems = crearDetalle();
      sinItems.detalles = [];
      responderCarga(sinItems);

      expect(textoRaiz()).toContain('Este pedido no tiene ítems registrados.');
    });

    // --- Feature 021 (T11, AC-5/AC-6/AC-9): cobertura y OC ---------------

    it('AC-5: muestra la cobertura por producto y las OC que cubren el pedido', () => {
      const detalle = crearDetalle(2);
      detalle.asignaciones = [
        {
          orden_compra_ticket_id: 1,
          orden_compra_id: 21,
          numero_oc: 'OC-2026-000021',
          estado_orden: 'Recibida',
          producto_id: 1,
          producto_nombre: 'Papel oficio',
          cantidad_asignada: 2,
          cantidad_faltante: 0,
          fecha_asignacion: '2026-11-03T10:05:00',
        },
      ];
      detalle.cadena_productos = [
        {
          producto_id: 1,
          producto_nombre: 'Papel oficio',
          solicitado: 3,
          comprado: 2,
          recibido: 2,
          entregado: 1,
          faltante: 0,
        },
      ];
      responderCarga(detalle);

      const visible = textoRaiz();
      expect(visible).toContain('Cobertura por producto');
      expect(visible).toContain('Comprado');
      expect(visible).toContain('Recibido');
      expect(visible).toContain('Faltante');
      expect(visible).toContain('Órdenes de compra que cubren el pedido');
      expect(visible).toContain('OC-2026-000021');
      expect(visible).toContain('Recibida');
    });

    it('AC-9: una OC cancelada se marca y no se presenta como cobertura activa', () => {
      const detalle = crearDetalle(2);
      detalle.asignaciones = [
        {
          orden_compra_ticket_id: 2,
          orden_compra_id: 22,
          numero_oc: 'OC-2026-000022',
          estado_orden: 'Cancelada',
          producto_id: 1,
          producto_nombre: 'Papel oficio',
          cantidad_asignada: 2,
          cantidad_faltante: 1,
          fecha_asignacion: '2026-11-04T10:05:00',
        },
      ];
      detalle.cadena_productos = [];
      responderCarga(detalle);

      const visible = textoRaiz();
      expect(visible).toContain('Cancelada');
      expect(visible).toContain('no cuentan como cobertura');
    });

    it('AC-6: el historial muestra la OC que desbloqueó el pedido', () => {
      const historial = crearHistorial();
      historial[1] = {
        ...historial[1],
        estado_origen_nombre: 'EnCurso',
        estado_destino_nombre: 'EnCurso',
        orden_compra_id: 21,
        numero_oc: 'OC-2026-000021',
      };
      responderCarga(crearDetalle(2), historial);

      expect(textoRaiz()).toContain('En Curso → En Curso');
      expect(textoRaiz()).toContain('OC-2026-000021');
    });

    it('muestra un error accesible (role="alert") ante un 404 y permite reintentar', () => {
      responderCarga(null);

      expect(componente.ticket()).toBeNull();
      expect(alertas().length).toBeGreaterThan(0);
      expect(alertas()[0]).toContain('Ticket no encontrado');

      // Reintento: vuelve a pedir las tres cosas y se recupera.
      boton('Reintentar')!.click();
      httpMock.expectOne(RUTA_DETALLE).flush(crearDetalle());
      httpMock.expectOne(RUTA_HISTORIAL).flush(crearHistorial());
      httpMock.expectOne(RUTA_CATALOGOS).flush(CATALOGOS_013);
      fixture.detectChanges();

      expect(componente.ticket()).not.toBeNull();
      expect(componente.errorCarga()).toBeNull();
    });
  });

  // ---------------------------------------------------------------------------
  // Read model de la ampliación (AC-37…AC-40, AC-42)
  // ---------------------------------------------------------------------------

  describe('read model de proceso', () => {
    it('muestra el estado canónico y, junto a él, la etiqueta de proceso con su frase', () => {
      const detalle = crearDetalle(1);
      detalle.etiqueta_proceso = 'En revisión';
      detalle.explicacion_proceso =
        'En revisión: pendiente de revisión por Bodega o Administración.';
      responderCarga(detalle);

      const visible = textoPagina();
      // Estado canónico con su badge actual y la etiqueta derivada, juntos.
      expect(visible).toContain('En Revisión');
      expect(componente.nombreEstado()).toBe('EnRevision');
      expect(componente.etiquetaEstado()).toBe('En Revisión');
      expect(visible).toContain('En revisión');
      expect(visible).toContain(
        'En revisión: pendiente de revisión por Bodega o Administración.',
      );
    });

    it('respeta las palabras de la etiqueta de proceso sin aplicarles el helper de estados', () => {
      const detalle = crearDetalle(2);
      detalle.stock_disponible = true;
      detalle.etiqueta_proceso = 'En confirmación de stock local';
      detalle.explicacion_proceso =
        'En confirmación de stock local: el stock local está disponible; falta que el Bodeguero registre el retiro.';
      responderCarga(detalle);

      expect(componente.etiquetaEstado()).toBe('En Curso');
      expect(componente.etiquetaProceso()).toBe('En confirmación de stock local');
      expect(textoPagina()).toContain('En confirmación de stock local');
    });

    it('muestra el último Bodeguero y el último Administrador con nombre y apellido', () => {
      const detalle = crearDetalle(1);
      detalle.gestionado_por_bodeguero = {
        usuario_id: 9,
        nombre: 'Bruno',
        apellido: 'Soto',
      };
      detalle.gestionado_por_administrador = {
        usuario_id: 2,
        nombre: 'Camila',
        apellido: 'Fernandez',
      };
      responderCarga(detalle);

      const visible = textoPagina();
      expect(visible).toContain('Último Bodeguero');
      expect(visible).toContain('Soto, Bruno');
      expect(visible).toContain('Último Administrador');
      expect(visible).toContain('Fernandez, Camila');
      expect(visible).not.toContain('Sin gestión registrada');
    });

    it('sin gestores registrados muestra «Sin gestión registrada»', () => {
      responderCarga(crearDetalle(1));

      const visible = textoPagina();
      expect(componente.gestorBodeguero()).toBe('Sin gestión registrada');
      expect(componente.gestorAdministrador()).toBe('Sin gestión registrada');
      expect(visible).toContain('Último Bodeguero');
      expect(visible).toContain('Último Administrador');
      expect(visible).toContain('Sin gestión registrada');
    });

    it('muestra «Entregado el … por …» cuando el Solicitante confirmó la entrega', () => {
      const detalle = crearDetalle(3);
      detalle.entrega_confirmada = true;
      detalle.entrega_confirmada_en = '2026-11-25T12:00:00';
      detalle.entrega_confirmada_por_nombre = 'Isabel';
      detalle.entrega_confirmada_por_apellido = 'Contreras';
      responderCarga(detalle);

      const visible = textoPagina();
      expect(visible).toContain('Entregado el');
      expect(visible).toContain('Contreras, Isabel');
    });

    it('sin confirmación no muestra la línea de entrega', () => {
      responderCarga(crearDetalle(3));

      expect(textoPagina()).not.toContain('Entregado el');
    });
  });

  // ---------------------------------------------------------------------------
  // Acciones semánticas por estado y rol (AC-32)
  // ---------------------------------------------------------------------------

  describe('acciones por estado y rol', () => {
    it('EnRevision · Administrador: Aprobar, Editar, Rechazar y Anular', () => {
      responderCarga(crearDetalle(1));

      expect(botonesAccion()).toEqual(['Aprobar', 'Editar', 'Rechazar', 'Anular']);
    });

    it('EnRevision · Bodeguero: solo Rechazar (no aprueba, edita ni anula)', () => {
      identidad.set(crearIdentidad('Bodeguero'));
      responderCarga(crearDetalle(1));

      expect(botonesAccion()).toEqual(['Rechazar']);
    });

    it('EnRevision · Solicitante dueño: Editar y Anular', () => {
      identidad.set(crearIdentidad('Solicitante', 5));
      responderCarga(crearDetalle(1));

      expect(botonesAccion()).toEqual(['Editar', 'Anular']);
    });

    it('EnRevision · Solicitante no dueño: ninguna acción y la nota explica el rol', () => {
      identidad.set(crearIdentidad('Solicitante', 99));
      responderCarga(crearDetalle(1));

      expect(botonesAccion()).toEqual([]);
      expect(textoPagina()).toContain('Tu rol no puede operar el ciclo de vida');
    });

    it('EnCurso · Administrador con stock: no ofrece el retiro (solo Bodeguero)', () => {
      const detalle = crearDetalle(2);
      detalle.stock_disponible = true;
      responderCarga(detalle);

      expect(botonesAccion()).toEqual([]);
    });

    it('EnCurso · Bodeguero de la sede con stock: Registrar retiro', () => {
      identidad.set({
        ...crearIdentidad('Bodeguero'),
        sede: { sede_id: 3, nombre: 'Sede Central' },
      });
      const detalle = crearDetalle(2);
      detalle.stock_disponible = true;
      responderCarga(detalle);

      expect(botonesAccion()).toEqual(['Registrar retiro']);
    });

    it('EnCurso · Bodeguero sin sede: no ofrece el retiro', () => {
      identidad.set(crearIdentidad('Bodeguero'));
      const detalle = crearDetalle(2);
      detalle.stock_disponible = true;
      responderCarga(detalle);

      expect(botonesAccion()).toEqual([]);
    });

    it('EnCurso · sin stock_disponible: el retiro no se ofrece', () => {
      responderCarga(crearDetalle(2));

      expect(botonesAccion()).toEqual([]);
      expect(textoPagina()).toContain('stock local aún no está disponible');
    });

    it('EnCurso · Solicitante dueño: no puede registrar el retiro', () => {
      identidad.set(crearIdentidad('Solicitante', 5));
      const detalle = crearDetalle(2);
      detalle.stock_disponible = true;
      responderCarga(detalle);

      expect(botonesAccion()).toEqual([]);
    });

    it('Cerrado · Solicitante dueño sin confirmar: solo Confirmar entrega', () => {
      identidad.set(crearIdentidad('Solicitante', 5));
      const detalle = crearDetalle(3);
      detalle.entrega_confirmada = false;
      responderCarga(detalle);

      expect(botonesAccion()).toEqual(['Confirmar entrega']);
    });

    it('Cerrado · Solicitante no dueño: sin acciones y la nota pide la confirmación del dueño', () => {
      identidad.set(crearIdentidad('Solicitante', 99));
      responderCarga(crearDetalle(3));

      expect(botonesAccion()).toEqual([]);
      expect(textoPagina()).toContain('pendiente de confirmación de entrega');
    });

    it('Cerrado · Administrador sin confirmar: Anular el retiro', () => {
      responderCarga(crearDetalle(3));

      expect(botonesAccion()).toEqual(['Anular el retiro']);
    });

    it('Cerrado confirmado · Administrador: sin acciones; se presenta Entregado', () => {
      const detalle = crearDetalle(3);
      detalle.entrega_confirmada = true;
      detalle.etiqueta_proceso = 'Entregado';
      responderCarga(detalle);

      expect(botonesAccion()).toEqual([]);
      expect(textoPagina()).toContain('Entregado');
    });

    it('Cerrado entregado · Solicitante dueño: el botón desaparece y la nota lo explica', () => {
      identidad.set(crearIdentidad('Solicitante', 5));
      const detalle = crearDetalle(3);
      detalle.entrega_confirmada = true;
      detalle.entrega_confirmada_en = '2026-11-25T12:00:00';
      detalle.entrega_confirmada_por_nombre = 'Isabel';
      detalle.entrega_confirmada_por_apellido = 'Contreras';
      responderCarga(detalle);

      expect(botonesAccion()).toEqual([]);
      expect(textoPagina()).toContain('entrega ya fue confirmada');
    });

    it('Anulado · ningún rol ofrece acciones y la nota explica el terminal', () => {
      responderCarga(crearDetalle(4));

      expect(botonesAccion()).toEqual([]);
      expect(textoPagina()).toContain('está Anulado');
      expect(textoPagina()).toContain('no admite más acciones');
    });

    it('Superadmin: ninguna acción y la nota explica que solo puede consultar', () => {
      identidad.set(crearIdentidad('Superadmin'));
      responderCarga(crearDetalle(1));

      expect(botonesAccion()).toEqual([]);
      expect(textoPagina()).toContain('solo puedes consultarlo');
    });

    it('cada acción visible expone su propio aria-label', () => {
      responderCarga(crearDetalle(1));

      const botones = Array.from(raiz.querySelectorAll<HTMLButtonElement>('button')).filter(
        (b) => b.closest('dialog') === null,
      );
      expect(botones.length).toBeGreaterThan(0);
      for (const accion of botones) {
        expect((accion.getAttribute('aria-label') ?? '').length)
          .withContext((accion.textContent ?? '').trim())
          .toBeGreaterThan(0);
      }
    });
  });

  // ---------------------------------------------------------------------------
  // Aprobación del Administrador (AC-32, AC-48): un clic, sin motivo
  // ---------------------------------------------------------------------------

  describe('aprobación', () => {
    it('un clic aprueba sin diálogo ni motivo y reconsulta con EnCurso', () => {
      responderCarga(crearDetalle(1));

      boton('Aprobar')!.click();

      expect(componente.confirmando()).toBeNull();
      const peticion = httpMock.expectOne(RUTA_APROBACION);
      expect(peticion.request.method).toBe('POST');
      expect(peticion.request.body).toBeNull();
      peticion.flush(crearDetalle(2));

      const aprobado = crearDetalle(2);
      aprobado.stock_disponible = true;
      aprobado.etiqueta_proceso = 'En confirmación de stock local';
      aprobado.explicacion_proceso =
        'En confirmación de stock local: el stock local está disponible; falta que el Bodeguero registre el retiro.';
      responderReconsulta(aprobado);

      expect(avisoExito('Pedido aprobado.')).toBe(true);
      expect(alertas()).toEqual([]);
      expect(componente.enOperacion()).toBe(false);
      expect(componente.nombreEstado()).toBe('EnCurso');
      expect(textoPagina()).toContain('En Curso');
      expect(textoPagina()).toContain('En confirmación de stock local');
      // El retiro es exclusivo del Bodeguero de la sede: el Administrador no lo ve.
      expect(botonesAccion()).not.toContain('Registrar retiro');
    });

    it('un 409 se anuncia en role="alert" y reconsulta la verdad del backend', () => {
      responderCarga(crearDetalle(1));

      boton('Aprobar')!.click();
      httpMock
        .expectOne(RUTA_APROBACION)
        .flush(
          { detail: 'El pedido ya esta EnCurso' },
          { status: 409, statusText: 'Conflict' },
        );
      responderReconsulta(crearDetalle(1));

      expect(alertas().length).toBeGreaterThan(0);
      expect(alertas()[0]).toContain('El pedido ya esta EnCurso');
      expect(componente.enOperacion()).toBe(false);
      expect(componente.nombreEstado()).toBe('EnRevision');
    });

    it('un 403 se anuncia en role="alert" y reconsulta', () => {
      responderCarga(crearDetalle(1));

      boton('Aprobar')!.click();
      httpMock
        .expectOne(RUTA_APROBACION)
        .flush(
          { detail: 'Tu rol no tiene permiso para aprobar' },
          { status: 403, statusText: 'Forbidden' },
        );
      responderReconsulta(crearDetalle(1));

      expect(alertas()[0]).toContain('Tu rol no tiene permiso para aprobar');
    });

    it('no permite doble envío mientras la aprobación está en vuelo', () => {
      responderCarga(crearDetalle(1));

      boton('Aprobar')!.click();
      fixture.detectChanges();

      expect(boton('Aprobar')!.disabled).toBe(true);
      componente.aprobar();

      const peticion = httpMock.expectOne(RUTA_APROBACION);
      peticion.flush(crearDetalle(2));
      responderReconsulta(crearDetalle(2));
      httpMock.expectNone(RUTA_APROBACION);
    });
  });

  // ---------------------------------------------------------------------------
  // Retiro desde el detalle (D-29/AC-55/AC-63): diálogo sin motivo, solo Bodeguero
  // ---------------------------------------------------------------------------

  describe('retiro', () => {
    function detalleEnCurso(): TicketDetalle {
      const detalle = crearDetalleRetiro(2);
      detalle.stock_disponible = true;
      return detalle;
    }

    beforeEach(() => {
      identidad.set({
        ...crearIdentidad('Bodeguero'),
        sede: { sede_id: 3, nombre: 'Sede Central' },
      });
    });

    it('abre un diálogo sin motivo y envía el retiro con el usuario_id de la sesión', () => {
      responderCarga(detalleEnCurso(), crearHistorial(), CATALOGOS_RETIRO);

      boton('Registrar retiro')!.click();
      fixture.detectChanges();

      expect(componente.confirmando()).toBe('retiro');
      const dialogo = dialogoConfirmacion();
      expect(dialogo.open).toBe(true);
      expect(dialogo.querySelector('textarea')).toBeNull();
      expect((dialogo.textContent ?? '').replace(/\s+/g, ' ')).toContain('descontará');
      expect((dialogo.textContent ?? '').replace(/\s+/g, ' ')).toContain('Retirado');

      dialogo.querySelector<HTMLButtonElement>('button[type="submit"]')!.click();

      const peticion = httpMock.expectOne(RUTA_RETIRO);
      expect(peticion.request.method).toBe('POST');
      expect(peticion.request.body).toEqual({ usuario_id: 9 });
      peticion.flush(crearDetalleRetiro(3));

      const retirado = crearDetalleRetiro(3);
      retirado.fecha_cierre = '2026-11-25T10:00:00';
      retirado.etiqueta_proceso = 'Retirado';
      retirado.explicacion_proceso = 'Retirado: pendiente de confirmación de entrega.';
      responderReconsulta(retirado);

      expect(componente.confirmando()).toBeNull();
      expect(avisoExito('Pedido retirado.')).toBe(true);
      expect(alertas()).toEqual([]);
      expect(componente.nombreEstado()).toBe('Cerrado');
      expect(textoPagina()).toContain('Retirado');
      // El badge de stock y la acción desaparecen; queda la nota del terminal.
      expect(textoPagina()).not.toContain('Stock disponible');
      expect(botonesAccion()).toEqual([]);
    });

    it('un 409 del retiro se anuncia en role="alert" y retira la acción tras la reconsulta', () => {
      responderCarga(detalleEnCurso(), crearHistorial(), CATALOGOS_RETIRO);

      boton('Registrar retiro')!.click();
      fixture.detectChanges();
      dialogoConfirmacion().querySelector<HTMLButtonElement>('button[type="submit"]')!.click();

      httpMock
        .expectOne(RUTA_RETIRO)
        .flush(
          { detail: 'Stock insuficiente para el producto Cuaderno rayado' },
          { status: 409, statusText: 'Conflict' },
        );

      const sinStock = crearDetalleRetiro(2);
      sinStock.stock_disponible = false;
      sinStock.etiqueta_proceso = 'Por comprar';
      sinStock.explicacion_proceso = 'Por comprar: no hay stock suficiente ni compra vigente.';
      responderReconsulta(sinStock, crearHistorial());

      expect(alertas()[0]).toContain('Stock insuficiente para el producto Cuaderno rayado');
      expect(componente.confirmando()).toBeNull();
      expect(botonesAccion()).toEqual([]);
      expect(textoPagina()).toContain('Por comprar');
    });

    it('no permite doble envío mientras el retiro está en vuelo', () => {
      responderCarga(detalleEnCurso(), crearHistorial(), CATALOGOS_RETIRO);

      boton('Registrar retiro')!.click();
      fixture.detectChanges();
      const submit = dialogoConfirmacion().querySelector<HTMLButtonElement>(
        'button[type="submit"]',
      )!;
      submit.click();
      fixture.detectChanges();

      expect(submit.disabled).toBe(true);
      componente.confirmar();

      const peticion = httpMock.expectOne(RUTA_RETIRO);
      peticion.flush(crearDetalleRetiro(3));
      responderReconsulta(crearDetalleRetiro(3), crearHistorial());
      httpMock.expectNone(RUTA_RETIRO);
    });
  });

  // ---------------------------------------------------------------------------
  // Confirmación de entrega del Solicitante dueño (AC-42, AC-43)
  // ---------------------------------------------------------------------------

  describe('confirmación de entrega', () => {
    function detalleCerrado(): TicketDetalle {
      const detalle = crearDetalle(3);
      detalle.entrega_confirmada = false;
      return detalle;
    }

    it('abre un diálogo sin motivo, envía POST sin cuerpo y retira el botón al 200', () => {
      identidad.set(crearIdentidad('Solicitante', 5));
      responderCarga(detalleCerrado());

      boton('Confirmar entrega')!.click();
      fixture.detectChanges();

      expect(componente.confirmando()).toBe('entrega');
      const dialogo = dialogoConfirmacion();
      expect(dialogo.querySelector('textarea')).toBeNull();
      expect((dialogo.textContent ?? '').replace(/\s+/g, ' ')).toContain('Entregado');

      dialogo.querySelector<HTMLButtonElement>('button[type="submit"]')!.click();

      const peticion = httpMock.expectOne(RUTA_CONFIRMACION_ENTREGA);
      expect(peticion.request.method).toBe('POST');
      expect(peticion.request.body).toBeNull();
      peticion.flush(crearDetalle(3));

      const entregado = crearDetalle(3);
      entregado.entrega_confirmada = true;
      entregado.entrega_confirmada_en = '2026-11-25T12:00:00';
      entregado.entrega_confirmada_por_nombre = 'Isabel';
      entregado.entrega_confirmada_por_apellido = 'Contreras';
      entregado.etiqueta_proceso = 'Entregado';
      entregado.explicacion_proceso = 'Entregado: confirmado por el solicitante.';
      responderReconsulta(entregado);

      expect(componente.confirmando()).toBeNull();
      expect(avisoExito('Entrega confirmada.')).toBe(true);
      expect(componente.nombreEstado()).toBe('Cerrado');
      expect(textoPagina()).toContain('Entregado el');
      expect(textoPagina()).toContain('Contreras, Isabel');
      expect(botonesAccion()).toEqual([]);
    });

    it('un 409 (ya confirmado) se anuncia en role="alert" y reconsulta', () => {
      identidad.set(crearIdentidad('Solicitante', 5));
      responderCarga(detalleCerrado());

      boton('Confirmar entrega')!.click();
      fixture.detectChanges();
      dialogoConfirmacion().querySelector<HTMLButtonElement>('button[type="submit"]')!.click();

      httpMock
        .expectOne(RUTA_CONFIRMACION_ENTREGA)
        .flush(
          { detail: 'La entrega de este pedido ya fue confirmada' },
          { status: 409, statusText: 'Conflict' },
        );

      const confirmado = detalleCerrado();
      confirmado.entrega_confirmada = true;
      confirmado.entrega_confirmada_en = '2026-11-25T12:00:00';
      responderReconsulta(confirmado);

      expect(alertas()[0]).toContain('La entrega de este pedido ya fue confirmada');
      expect(componente.confirmando()).toBeNull();
      expect(botonesAccion()).toEqual([]);
    });

    it('no permite doble envío mientras la confirmación está en vuelo', () => {
      identidad.set(crearIdentidad('Solicitante', 5));
      responderCarga(detalleCerrado());

      boton('Confirmar entrega')!.click();
      fixture.detectChanges();
      const submit = dialogoConfirmacion().querySelector<HTMLButtonElement>(
        'button[type="submit"]',
      )!;
      submit.click();
      fixture.detectChanges();

      expect(submit.disabled).toBe(true);
      componente.confirmar();

      const peticion = httpMock.expectOne(RUTA_CONFIRMACION_ENTREGA);
      peticion.flush(crearDetalle(3));
      responderReconsulta(crearDetalle(3));
      httpMock.expectNone(RUTA_CONFIRMACION_ENTREGA);
    });
  });

  // ---------------------------------------------------------------------------
  // Anulación y rechazo con motivo obligatorio (D-6, AC-32)
  // ---------------------------------------------------------------------------

  describe('anulación y rechazo', () => {
    it('la confirmación exige motivo: vacío o en blanco no envía nada', () => {
      responderCarga(crearDetalle(1));

      boton('Anular')!.click();
      fixture.detectChanges();
      expect(componente.confirmando()).toBe('anular');

      const dialogo = dialogoConfirmacion();
      expect(dialogo.querySelector('textarea')).not.toBeNull();
      dialogo.querySelector<HTMLButtonElement>('button[type="submit"]')!.click();
      fixture.detectChanges();

      httpMock.expectNone(RUTA_ANULACION);
      expect(componente.confirmando()).toBe('anular');
      expect(textoRaiz()).toContain('El motivo es obligatorio');

      // Un motivo de solo espacios tampoco sale del cliente.
      componente.motivoForm.controls.motivo.setValue('   ');
      dialogo.querySelector<HTMLButtonElement>('button[type="submit"]')!.click();
      httpMock.expectNone(RUTA_ANULACION);
    });

    it('anula con el motivo literal y reconsulta tras el éxito', () => {
      responderCarga(crearDetalle(1));

      boton('Anular')!.click();
      fixture.detectChanges();
      componente.motivoForm.controls.motivo.setValue('Ya no hace falta');
      dialogoConfirmacion().querySelector<HTMLButtonElement>('button[type="submit"]')!.click();

      const peticion = httpMock.expectOne(RUTA_ANULACION);
      expect(peticion.request.method).toBe('POST');
      expect(peticion.request.body).toEqual({ motivo: 'Ya no hace falta' });
      peticion.flush(crearDetalle(4));
      responderReconsulta(crearDetalle(4));

      expect(componente.confirmando()).toBeNull();
      expect(textoRaiz()).toContain('Pedido anulado.');
    });

    it('un 422 del backend queda accesible en role="alert" y el modal sigue abierto', () => {
      responderCarga(crearDetalle(1));

      boton('Anular')!.click();
      fixture.detectChanges();
      componente.motivoForm.controls.motivo.setValue('Motivo');
      dialogoConfirmacion().querySelector<HTMLButtonElement>('button[type="submit"]')!.click();

      httpMock
        .expectOne(RUTA_ANULACION)
        .flush(
          { detail: 'El motivo excede la longitud maxima' },
          { status: 422, statusText: 'Unprocessable' },
        );
      responderReconsulta();

      expect(componente.confirmando()).toBe('anular');
      expect(alertas().length).toBeGreaterThan(0);
      expect(alertas()[0]).toContain('El motivo excede la longitud maxima');
    });

    it('el Bodeguero rechaza vía POST /rechazo con su motivo', () => {
      identidad.set(crearIdentidad('Bodeguero'));
      responderCarga(crearDetalle(1));

      boton('Rechazar')!.click();
      fixture.detectChanges();
      componente.motivoForm.controls.motivo.setValue('Sin stock en la sede');
      dialogoConfirmacion().querySelector<HTMLButtonElement>('button[type="submit"]')!.click();

      const peticion = httpMock.expectOne(RUTA_RECHAZO);
      expect(peticion.request.method).toBe('POST');
      expect(peticion.request.body).toEqual({ motivo: 'Sin stock en la sede' });
      peticion.flush(crearDetalle(4));
      responderReconsulta(crearDetalle(4));

      expect(textoRaiz()).toContain('Pedido rechazado.');
    });

    it('muestra el 409 del servidor al rechazar en un role="alert" y reconsulta', () => {
      identidad.set(crearIdentidad('Bodeguero'));
      responderCarga(crearDetalle(1));

      boton('Rechazar')!.click();
      fixture.detectChanges();
      componente.motivoForm.controls.motivo.setValue('Motivo válido');
      dialogoConfirmacion().querySelector<HTMLButtonElement>('button[type="submit"]')!.click();

      httpMock
        .expectOne(RUTA_RECHAZO)
        .flush(
          { detail: 'El estado actual no admite el rechazo' },
          { status: 409, statusText: 'Conflict' },
        );
      responderReconsulta();

      expect(alertas().length).toBeGreaterThan(0);
      expect(alertas()[0]).toContain('El estado actual no admite el rechazo');
      // El modal permanece abierto para que el usuario corrija o cancele.
      expect(componente.confirmando()).toBe('rechazo');
      expect(componente.enOperacion()).toBe(false);
    });
  });

  // ---------------------------------------------------------------------------
  // Edición en EnRevision (PUT, D-9)
  // ---------------------------------------------------------------------------

  describe('edición en EnRevision', () => {
    it('abre el formulario precargado y envía PUT con la cabecera y los ítems completos', () => {
      responderCarga(crearDetalle(1));

      boton('Editar')!.click();
      fixture.detectChanges();
      expect(componente.editando()).toBe(true);

      componente.formularioEdicion.controls.asunto.setValue('Falta de papel y cartulina');
      dialogoEdicion().querySelector<HTMLButtonElement>('button[type="submit"]')!.click();

      const peticion = httpMock.expectOne(RUTA_DETALLE);
      expect(peticion.request.method).toBe('PUT');
      expect(peticion.request.body).toEqual({
        asunto: 'Falta de papel y cartulina',
        descripcion: 'Se solicita papel oficio para impresiones.',
        prioridad_id: 1,
        detalles: [{ producto_id: 1, cantidad_solicitada: 3 }],
      });
      const editado = crearDetalle(1);
      editado.asunto = 'Falta de papel y cartulina';
      peticion.flush(editado);
      responderReconsulta(editado);

      expect(componente.editando()).toBe(false);
      expect(textoRaiz()).toContain('Pedido editado.');
    });

    it('un 409 del servidor (fuera de EnRevision) queda accesible en role="alert"', () => {
      responderCarga(crearDetalle(1));

      boton('Editar')!.click();
      fixture.detectChanges();
      dialogoEdicion().querySelector<HTMLButtonElement>('button[type="submit"]')!.click();

      httpMock
        .expectOne(RUTA_DETALLE)
        .flush(
          { detail: "La edicion solo se aplica a tickets en estado 'EnRevision'" },
          { status: 409, statusText: 'Conflict' },
        );
      responderReconsulta();

      expect(alertas().length).toBeGreaterThan(0);
      expect(alertas()[0]).toContain(
        "La edicion solo se aplica a tickets en estado 'EnRevision'",
      );
      expect(componente.editando()).toBe(true);
    });

    it('no envía la edición con el formulario inválido', () => {
      responderCarga(crearDetalle(1));

      boton('Editar')!.click();
      fixture.detectChanges();
      componente.formularioEdicion.controls.asunto.setValue('');
      componente.guardarEdicion();

      httpMock.expectNone(RUTA_DETALLE);
      expect(componente.editando()).toBe(true);
    });

    it('limita la descripción de la edición a 500 caracteres', () => {
      responderCarga(crearDetalle(1));

      boton('Editar')!.click();
      fixture.detectChanges();

      componente.formularioEdicion.controls.descripcion.setValue('x'.repeat(501));
      expect(
        componente.formularioEdicion.controls.descripcion.hasError('maxlength'),
      ).toBe(true);

      const textarea = dialogoEdicion().querySelector(
        'textarea[formcontrolname="descripcion"]',
      ) as HTMLTextAreaElement;
      expect(textarea.getAttribute('maxlength')).toBe('500');
    });

    it('muestra el campo culpable ante un 422 de descripción', () => {
      responderCarga(crearDetalle(1));

      boton('Editar')!.click();
      fixture.detectChanges();
      dialogoEdicion().querySelector<HTMLButtonElement>('button[type="submit"]')!.click();

      httpMock
        .expectOne(RUTA_DETALLE)
        .flush(
          {
            detail: [
              {
                loc: ['body', 'descripcion'],
                msg: 'String should have at most 500 characters',
                type: 'string_too_long',
              },
            ],
          },
          { status: 422, statusText: 'Unprocessable Entity' },
        );
      responderReconsulta();

      expect(alertas().length).toBeGreaterThan(0);
      expect(alertas()[0]).toContain('Descripción');
      expect(alertas()[0]).toContain('No puede superar los 500 caracteres.');
      expect(componente.editando()).toBe(true);
    });

    // -------------------------------------------------------------------------
    // Feature 014, AC-9: productos inactivos en la edición
    // -------------------------------------------------------------------------

    it('conserva un producto inactivo ya cargado y permite cambiar su cantidad', () => {
      responderCarga(
        crearDetalleConProductoInactivo(),
        crearHistorial(),
        CATALOGOS_SIN_PRODUCTO_1,
      );

      boton('Editar')!.click();
      fixture.detectChanges();

      // La opción no viene del catálogo (el servidor ya la excluye): se añade
      // desde los detalles actuales del propio ticket, marcada como inactiva.
      const opciones = componente.opcionesProductoEdicion(0);
      const conservada = opciones.find((opcion) => opcion.producto_id === 1);
      expect(conservada?.inactivo).toBe(true);
      expect(conservada?.etiqueta).toContain('inactivo');
      expect(componente.esProductoInactivoEdicion(0)).toBe(true);

      const select = dialogoEdicion().querySelectorAll('select')[1];
      const textos = Array.from(select.querySelectorAll('option')).map((opcion) =>
        (opcion.textContent ?? '').trim(),
      );
      expect(textos).toContain('Cuaderno rayado — inactivo (solo se conserva)');

      componente.detallesEdicion.at(0).controls.cantidad_solicitada.setValue(5);
      dialogoEdicion().querySelector<HTMLButtonElement>('button[type="submit"]')!.click();

      const peticion = httpMock.expectOne(RUTA_DETALLE);
      expect(peticion.request.method).toBe('PUT');
      expect(peticion.request.body.detalles).toEqual([
        { producto_id: 1, cantidad_solicitada: 5 },
      ]);

      const editado = crearDetalleConProductoInactivo();
      editado.detalles[0].cantidad_solicitada = 5;
      peticion.flush(editado);
      responderReconsulta(editado);

      expect(textoRaiz()).toContain('Pedido editado.');
    });

    it('no ofrece el producto inactivo para una línea nueva', () => {
      responderCarga(
        crearDetalleConProductoInactivo(),
        crearHistorial(),
        CATALOGOS_SIN_PRODUCTO_1,
      );

      boton('Editar')!.click();
      fixture.detectChanges();
      componente.agregarDetalleEdicion();
      fixture.detectChanges();

      // La fila nueva no tiene producto actual: solo ve el catálogo activo.
      const opcionesNuevas = componente.opcionesProductoEdicion(1);
      expect(opcionesNuevas.map((opcion) => opcion.producto_id)).toEqual([2]);
      expect(opcionesNuevas.some((opcion) => opcion.inactivo)).toBe(false);

      const segundoSelect = dialogoEdicion().querySelectorAll('select')[2];
      const textos = Array.from(segundoSelect.querySelectorAll('option')).map((opcion) =>
        (opcion.textContent ?? '').trim(),
      );
      expect(textos).not.toContain('Cuaderno rayado — inactivo (solo se conserva)');
      expect(textos.join(' ')).not.toContain('Cuaderno rayado');
    });

    it('muestra el 409 del servidor al intentar añadir un producto inactivo no presente', () => {
      responderCarga(crearDetalle(1));

      boton('Editar')!.click();
      fixture.detectChanges();
      componente.agregarDetalleEdicion();
      componente.detallesEdicion.at(1).controls.producto_id.setValue(2);
      fixture.detectChanges();

      dialogoEdicion().querySelector<HTMLButtonElement>('button[type="submit"]')!.click();

      httpMock
        .expectOne(RUTA_DETALLE)
        .flush(
          { detail: 'El producto 2 esta inactivo y no figura en el ticket' },
          { status: 409, statusText: 'Conflict' },
        );
      responderReconsulta();

      expect(alertas().length).toBeGreaterThan(0);
      expect(alertas()[0]).toContain('El producto 2 esta inactivo y no figura en el ticket');
      // El modal sigue abierto para corregir la línea o cancelar.
      expect(componente.editando()).toBe(true);
      expect(componente.enOperacion()).toBe(false);
    });
  });

  // ---------------------------------------------------------------------------
  // Sin transiciones genéricas ni PATCH /estado (AC-48)
  // ---------------------------------------------------------------------------

  describe('sin transiciones genéricas', () => {
    it('no ofrece «Avanzar» ni «Retroceder» y no conserva métodos de transición', () => {
      responderCarga(crearDetalle(1));

      const visible = textoPagina();
      expect(visible).not.toContain('Avanzar');
      expect(visible).not.toContain('Retroceder');

      const api = componente as unknown as Record<string, unknown>;
      expect(api['avanzar']).toBeUndefined();
      expect(api['retroceder']).toBeUndefined();
      expect(api['transicion']).toBeUndefined();
      expect(api['idEstadoSiguiente']).toBeUndefined();
      expect(api['idEstadoAnterior']).toBeUndefined();
    });

    it('las acciones del detalle no invocan PATCH /estado', () => {
      identidad.set({
        ...crearIdentidad('Bodeguero'),
        sede: { sede_id: 3, nombre: 'Sede Central' },
      });
      const detalle = crearDetalle(2);
      detalle.stock_disponible = true;
      responderCarga(detalle);

      // Cualquier mutación visible usa su propia ruta; `afterEach` falla si
      // apareciera una petición inesperada (el PATCH de legado no se usa).
      expect(botonesAccion()).toEqual(['Registrar retiro']);
    });
  });

  // ---------------------------------------------------------------------------
  // Enmienda 26/Nov/2026: retiro y anulación del retiro (AC-55…AC-63)
  // ---------------------------------------------------------------------------

  describe('enmienda 26/Nov/2026: retiro y anulación del retiro', () => {
    function identidadConSede(rol: string, sede_id: number, usuario_id = 9) {
      return {
        ...crearIdentidad(rol, usuario_id),
        sede: { sede_id, nombre: 'Sede Central' },
      };
    }

    it('expone la acción registrarRetiro y retira el vocabulario de despacho (D-29)', () => {
      identidad.set(identidadConSede('Bodeguero', 3));
      const detalle = crearDetalleRetiro(2);
      detalle.stock_disponible = true;
      responderCarga(detalle, crearHistorial(), CATALOGOS_RETIRO);

      const acciones = componente.acciones() as unknown as Record<
        string,
        boolean
      >;
      expect(acciones['despachar']).toBeUndefined();
      expect(acciones['registrarRetiro']).toBe(true);

      const api = componente as unknown as Record<string, unknown>;
      expect(api['solicitarDespacho']).toBeUndefined();
      expect(typeof api['solicitarRetiro']).toBe('function');
    });

    it('titula «Registrar retiro»/«Confirmar retiro» y no pide motivo (AC-63)', () => {
      responderCarga(crearDetalleRetiro(2), crearHistorial(), CATALOGOS_RETIRO);
      const confirmando = componente.confirmando as unknown as {
        set: (tipo: string | null) => void;
      };
      confirmando.set('retiro');
      fixture.detectChanges();

      expect(componente.tituloConfirmacion()).toBe('Registrar retiro');
      expect(componente.textoBotonConfirmar()).toBe('Confirmar retiro');
      expect(componente.exigeMotivo()).toBe(false);
    });

    it('ofrece «Registrar retiro» solo al Bodeguero de la sede con EnCurso y stock (AC-63)', () => {
      identidad.set(identidadConSede('Bodeguero', 3));
      const detalle = crearDetalleRetiro(2);
      detalle.stock_disponible = true;
      responderCarga(detalle, crearHistorial(), CATALOGOS_RETIRO);

      const botones = botonesAccion();
      expect(botones).toContain('Registrar retiro');
      expect(botones).not.toContain('Confirmar stock local y despachar');
    });

    it('no ofrece el retiro al Administrador (AC-63)', () => {
      identidad.set(crearIdentidad('Administrador'));
      const detalle = crearDetalleRetiro(2);
      detalle.stock_disponible = true;
      responderCarga(detalle, crearHistorial(), CATALOGOS_RETIRO);

      expect(botonesAccion()).not.toContain('Registrar retiro');
    });

    it('no ofrece el retiro al Bodeguero de otra sede (AC-63)', () => {
      identidad.set(identidadConSede('Bodeguero', 9));
      const detalle = crearDetalleRetiro(2);
      detalle.stock_disponible = true;
      responderCarga(detalle, crearHistorial(), CATALOGOS_RETIRO);

      expect(botonesAccion()).not.toContain('Registrar retiro');
    });

    it('muestra «Anular el retiro» solo al Administrador de un Cerrado sin confirmar (AC-63)', () => {
      responderCarga(crearDetalleRetiro(3), crearHistorial(), CATALOGOS_RETIRO);

      expect(botonesAccion()).toContain('Anular el retiro');
    });

    it('oculta toda acción tras la confirmación y presenta «Entregado» (AC-63)', () => {
      identidad.set(crearIdentidad('Solicitante', 5));
      const detalle = crearDetalleRetiro(3);
      detalle.entrega_confirmada = true;
      detalle.etiqueta_proceso = 'Entregado';
      responderCarga(detalle, crearHistorial(), CATALOGOS_RETIRO);

      expect(botonesAccion()).not.toContain('Confirmar entrega');
      expect(botonesAccion()).not.toContain('Anular el retiro');
      expect(textoPagina()).toContain('Entregado');
    });

    it('solicita el retiro, envía POST /retiro y anuncia «Retirado» (AC-55/AC-63)', () => {
      identidad.set(identidadConSede('Bodeguero', 3));
      const detalle = crearDetalleRetiro(2);
      detalle.stock_disponible = true;
      responderCarga(detalle, crearHistorial(), CATALOGOS_RETIRO);

      const api = componente as unknown as Record<string, unknown>;
      const solicitar = api['solicitarRetiro'];
      expect(typeof solicitar).toBe('function');
      if (typeof solicitar !== 'function') {
        return;
      }

      (solicitar as () => void).call(componente);
      fixture.detectChanges();
      expect(componente.confirmando() as string | null).toBe('retiro');

      componente.confirmar();

      const peticion = httpMock.expectOne(RUTA_RETIRO);
      expect(peticion.request.method).toBe('POST');
      expect(peticion.request.body).toEqual({ usuario_id: 9 });
      peticion.flush(crearDetalleRetiro(3));
      responderReconsulta(crearDetalleRetiro(3));
      fixture.detectChanges();

      const avisos = Array.from(
        raiz.querySelectorAll('[role="status"]'),
      ).map((nodo) => (nodo.textContent ?? '').toLowerCase());
      expect(avisos.some((texto) => texto.includes('retirado'))).toBe(true);
    });

    it('un 409 del retiro se anuncia en role="alert" y reconsulta (AC-63)', () => {
      identidad.set(identidadConSede('Bodeguero', 3));
      const detalle = crearDetalleRetiro(2);
      detalle.stock_disponible = true;
      responderCarga(detalle, crearHistorial(), CATALOGOS_RETIRO);

      const api = componente as unknown as Record<string, unknown>;
      const solicitar = api['solicitarRetiro'];
      expect(typeof solicitar).toBe('function');
      if (typeof solicitar !== 'function') {
        return;
      }

      (solicitar as () => void).call(componente);
      componente.confirmar();
      httpMock
        .expectOne(RUTA_RETIRO)
        .flush(
          { detail: 'El pedido ya no esta en EnCurso' },
          { status: 409, statusText: 'Conflict' },
        );
      responderReconsulta(crearDetalleRetiro(2));
      fixture.detectChanges();

      expect(alertas().some((texto) => texto.includes('EnCurso'))).toBe(true);
      expect(componente.enOperacion()).toBe(false);
    });
  });

  // ---------------------------------------------------------------------------
  // Actualización en tiempo real (Feature 028, T18)
  // ---------------------------------------------------------------------------

  describe('actualización en tiempo real (Feature 028, T18)', () => {
    it('se suscribe una sola vez a pedidos e inventario', () => {
      responderCarga();

      expect(tiempoReal.dominiosSuscritos).toEqual([['pedidos', 'inventario']]);
      expect(tiempoReal.suscripcionesActivas).toBe(2);
    });

    it('un frame pedidos recarga detalle e historial una vez sin cerrar el diálogo ni borrar el motivo', fakeAsync(() => {
      responderCarga(crearDetalle(1));

      boton('Anular')!.click();
      fixture.detectChanges();
      expect(componente.confirmando()).toBe('anular');
      componente.motivoForm.controls.motivo.setValue('Ya no se necesita el pedido');
      const dialogo = dialogoConfirmacion();
      expect(dialogo.open).toBe(true);

      tiempoReal.emitirCambio(['pedidos'], 'aprobacion');

      // La agrupación espera la ventana de silencio de 250 ms.
      tick(249);
      httpMock.expectNone(RUTA_DETALLE);
      tick(1);

      const detalles = httpMock.match(RUTA_DETALLE);
      const historiales = httpMock.match(RUTA_HISTORIAL);
      expect(detalles.length).toBe(1);
      expect(historiales.length).toBe(1);

      detalles[0].flush(crearDetalle(1));
      historiales[0].flush(crearHistorial());
      tick();
      fixture.detectChanges();

      expect(componente.confirmando()).toBe('anular');
      expect(dialogoConfirmacion().open).toBe(true);
      expect(componente.motivoForm.controls.motivo.value).toBe(
        'Ya no se necesita el pedido',
      );
      httpMock.expectNone(RUTA_DETALLE);
    }));

    it('las acciones se recalculan con el estado nuevo sin borrar el motivo', fakeAsync(() => {
      responderCarga(crearDetalle(1));
      expect(botonesAccion()).toEqual(['Aprobar', 'Editar', 'Rechazar', 'Anular']);

      boton('Anular')!.click();
      fixture.detectChanges();
      componente.motivoForm.controls.motivo.setValue('Motivo a medio escribir');

      tiempoReal.emitirCambio(['pedidos'], 'cambio_estado');
      tick(250);

      httpMock.expectOne(RUTA_DETALLE).flush(crearDetalle(4));
      httpMock.expectOne(RUTA_HISTORIAL).flush(crearHistorial());
      tick();
      fixture.detectChanges();

      expect(componente.nombreEstado()).toBe('Anulado');
      expect(componente.acciones()).toEqual({
        aprobar: false,
        registrarRetiro: false,
        confirmarEntrega: false,
        editar: false,
        anular: false,
        rechazar: false,
      });
      expect(botonesAccion()).toEqual([]);
      // El diálogo abierto sobrevive: no se fuerza su cierre.
      expect(componente.confirmando()).toBe('anular');
      expect(componente.motivoForm.controls.motivo.value).toBe(
        'Motivo a medio escribir',
      );
    }));

    it('un frame inventario actualiza stock_disponible y habilita el retiro', fakeAsync(() => {
      identidad.set({
        ...crearIdentidad('Bodeguero'),
        sede: { sede_id: 3, nombre: 'Sede Central' },
      });
      const sinStock = crearDetalleRetiro(2);
      sinStock.stock_disponible = false;
      sinStock.etiqueta_proceso = 'Por comprar';
      responderCarga(sinStock, crearHistorial(), CATALOGOS_RETIRO);

      expect(componente.ticket()?.stock_disponible).toBe(false);
      expect(botonesAccion()).toEqual([]);
      expect(textoPagina()).toContain('stock local aún no está disponible');

      tiempoReal.emitirCambio(['inventario'], 'recepcion');
      tick(250);

      const conStock = crearDetalleRetiro(2);
      conStock.stock_disponible = true;
      conStock.etiqueta_proceso = 'En confirmación de stock local';
      httpMock.expectOne(RUTA_DETALLE).flush(conStock);
      httpMock.expectOne(RUTA_HISTORIAL).flush(crearHistorial());
      tick();
      fixture.detectChanges();

      expect(componente.ticket()?.stock_disponible).toBe(true);
      expect(botonesAccion()).toEqual(['Registrar retiro']);
      expect(textoPagina()).toContain('Stock disponible — Listo para el retiro');
    }));

    it('el refresco silencioso no enciende cargando y un fallo conserva detalle e historial', fakeAsync(() => {
      responderCarga(crearDetalle(2));
      const detalleAntes = componente.ticket();
      const historialAntes = componente.historial();
      expect(componente.cargando()).toBe(false);

      tiempoReal.emitirCambio(['pedidos'], 'edicion');
      tick(250);

      const peticionDetalle = httpMock.expectOne(RUTA_DETALLE);
      expect(componente.cargando()).toBe(false);
      expect(fixture.nativeElement.textContent).not.toContain('Cargando pedido');

      peticionDetalle.flush('Falla', { status: 500, statusText: 'Server Error' });
      httpMock.match(RUTA_HISTORIAL);
      tick();
      fixture.detectChanges();

      expect(componente.ticket()).toBe(detalleAntes);
      expect(componente.historial()).toBe(historialAntes);
      expect(componente.errorCarga()).toBeNull();
      expect(componente.cargando()).toBe(false);

      // El agrupador quedó libre: una nueva invalidación vuelve a leer.
      tiempoReal.emitirCambio(['pedidos'], 'edicion');
      tick(250);
      httpMock.expectOne(RUTA_DETALLE).flush(crearDetalle(2));
      httpMock.expectOne(RUTA_HISTORIAL).flush(crearHistorial());
      tick();
    }));

    it('una resincronización y un frame de la misma ráfaga producen un solo refresco', fakeAsync(() => {
      responderCarga();

      tiempoReal.emitirResincronizacion();
      tiempoReal.emitirCambio(['pedidos'], 'alta');
      tick(250);

      const detalles = httpMock.match(RUTA_DETALLE);
      const historiales = httpMock.match(RUTA_HISTORIAL);
      expect(detalles.length).toBe(1);
      expect(historiales.length).toBe(1);

      detalles[0].flush(crearDetalle(1));
      historiales[0].flush(crearHistorial());
      tick();
      httpMock.expectNone(RUTA_DETALLE);
      httpMock.expectNone(RUTA_HISTORIAL);
    }));

    it('ngOnDestroy cancela las suscripciones y el agrupador', fakeAsync(() => {
      responderCarga();
      expect(tiempoReal.suscripcionesActivas).toBe(2);

      // Deja un refresco programado y destruye antes de que dispare.
      tiempoReal.emitirCambio(['pedidos'], 'alta');
      tick(100);
      fixture.destroy();

      expect(tiempoReal.suscripcionesActivas).toBe(0);

      tiempoReal.emitirCambio(['pedidos'], 'alta');
      tiempoReal.emitirResincronizacion();
      tick(1_000);
      httpMock.expectNone(RUTA_DETALLE);
      httpMock.expectNone(RUTA_HISTORIAL);
    }));
  });
});
