import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Router, UrlTree, provideRouter } from '@angular/router';
import { WritableSignal, signal } from '@angular/core';

import { AutenticacionService } from '../../core/services/auth.service';
import { URL_API } from '../../shared/config/url-api';
import { CatalogosTicket, IdentidadAutenticada, Ticket } from '../../shared/interfaces';
import {
  inicioDePeriodo,
  TicketsComponent,
  type OrdenTablero,
  type PeriodoTablero,
} from './tickets.component';

const RUTA_CATALOGOS = `${URL_API}/tickets/catalogos`;
const RUTA_TICKETS = `${URL_API}/tickets/`;
const RUTA_ESTADO = (id: number) => `${URL_API}/tickets/${id}/estado`;

/**
 * `estados` en el orden del flujo, no alfabeticamente: "EnRevision" (1),
 * "EnCurso" (2), "Cerrado" (3) y "Anulado" (4). Desde la enmienda 26/Nov/2026
 * (D-35/AC-51) el componente resuelve el estado inicial por **nombre canonico**,
 * asi que este orden ya no decide el alta; se conserva porque es el que sirve el
 * backend y lo consumen los tests de presentacion.
 */
const CATALOGOS: CatalogosTicket = {
  prioridades: [
    { prioridad_id: 1, nombre: 'Alta', descripcion: 'Corto plazo' },
    { prioridad_id: 2, nombre: 'Media', descripcion: 'Reposicion' },
  ],
  estados: [
    { estado_id: 1, nombre: 'EnRevision', descripcion: 'En revision' },
    { estado_id: 2, nombre: 'EnCurso', descripcion: 'En preparacion para el retiro' },
    { estado_id: 3, nombre: 'Cerrado', descripcion: 'Retirado' },
    { estado_id: 4, nombre: 'Anulado', descripcion: 'Anulado o rechazado' },
  ],
  productos: [
    {
      producto_id: 1,
      nombre: 'Cuaderno linedado',
      unidad_medida: 'UNIDAD',
      categoria_nombre: 'Papeleria',
      stock_total: 50,
      es_critico: false,
    },
    {
      producto_id: 2,
      nombre: 'Toner HP 26A',
      unidad_medida: 'UNIDAD',
      categoria_nombre: 'Toner',
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
      departamento_nombre: 'Direccion',
    },
  ],
};

/**
 * Catalogo completo de la Feature 013 con la enmienda 26/Nov/2026 (D-35): los
 * cuatro estados vigentes, con `EnRevision` como unico inicial y los dos
 * terminales (`Cerrado` y `Anulado`) agrupados por el tablero en «Terminados».
 * La columna del tablero y la resolucion del alta se prueban contra este
 * catalogo, nunca contra ids fijos.
 */
const CATALOGOS_013: CatalogosTicket = {
  ...CATALOGOS,
};

/**
 * Enmienda 26/Nov/2026 (D-35/AC-62): catálogo de cuatro estados con
 * `EnRevision` como único inicial. El tablero agrupa `Cerrado` y `Anulado` en
 * «Terminados», así que las columnas quedan en tres.
 */
const CATALOGOS_RETIRO: CatalogosTicket = {
  ...CATALOGOS,
  estados: [
    { estado_id: 1, nombre: 'EnRevision', descripcion: 'En revision' },
    { estado_id: 2, nombre: 'EnCurso', descripcion: 'En preparacion para el retiro' },
    { estado_id: 3, nombre: 'Cerrado', descripcion: 'Retirado' },
    { estado_id: 4, nombre: 'Anulado', descripcion: 'Anulado o rechazado' },
  ],
};

// Fecha compartida por los tickets 3 y 4: ejercita el empate que se resuelve
// por `ticket_id` descendente. El ticket 4 ademas trae `fecha_cierre`.
const FECHA_EMPATE = '2026-10-02T10:00:00';
const FECHA_CIERRE = '2026-10-05T10:00:00';

/**
 * Fixture de tickets: cubre dos del mismo estado con fechas distintas (1 y 2),
 * dos del mismo estado con la **misma** fecha (3 y 4, empate), la columna
 * terminal sin tickets y uno con fecha de cierre no nula (el 4).
 */
const TICKETS: Ticket[] = [
  {
    ticket_id: 1,
    usuario_id: 5,
    prioridad_id: 1,
    estado_id: 1,
    asunto: 'Falta de papel',
    descripcion: 'Se solicita papel para el trimestre',
    fecha_creacion: '2026-10-01T10:00:00',
    fecha_cierre: null,
    detalles: [],
  },
  {
    ticket_id: 2,
    usuario_id: 1,
    prioridad_id: 2,
    estado_id: 1,
    asunto: 'Toner agotado',
    descripcion: null,
    fecha_creacion: '2026-10-03T10:00:00',
    fecha_cierre: null,
    detalles: [],
  },
  {
    ticket_id: 3,
    usuario_id: 5,
    prioridad_id: 1,
    estado_id: 2,
    asunto: 'Resma de papel',
    descripcion: null,
    fecha_creacion: FECHA_EMPATE,
    fecha_cierre: null,
    detalles: [],
  },
  {
    ticket_id: 4,
    usuario_id: 1,
    prioridad_id: 2,
    estado_id: 2,
    asunto: 'Grapas',
    descripcion: null,
    fecha_creacion: FECHA_EMPATE,
    fecha_cierre: FECHA_CIERRE,
    detalles: [],
  },
];

/**
 * Fixture de la ampliación 25/Nov/2026 (D-24/AC-41): la de T6 mas los tres
 * **terminales** del catálogo 013 —cerrado retirado (5), anulado/rechazado
 * (6) y cerrado entregado (7)—. Los tres caen en la columna «Terminados» y
 * cada uno lleva la etiqueta de proceso y los responsables que resuelve el
 * backend en el read model.
 */
const TICKETS_013: Ticket[] = [
  ...TICKETS,
  {
    ticket_id: 5,
    usuario_id: 5,
    prioridad_id: 1,
    estado_id: 3,
    asunto: 'Ticket cerrado por retiro',
    descripcion: null,
    fecha_creacion: '2026-10-04T10:00:00',
    fecha_cierre: FECHA_CIERRE,
    detalles: [],
    etiqueta_proceso: 'Retirado',
    explicacion_proceso: 'Retirado: pendiente de confirmación de entrega.',
    entrega_confirmada: false,
    gestionado_por_bodeguero: { usuario_id: 9, nombre: 'Luis', apellido: 'Illanes' },
    gestionado_por_administrador: {
      usuario_id: 8,
      nombre: 'Cristian',
      apellido: 'Gonzalez',
    },
  },
  {
    ticket_id: 6,
    usuario_id: 1,
    prioridad_id: 2,
    estado_id: 4,
    asunto: 'Ticket anulado con motivo',
    descripcion: null,
    fecha_creacion: '2026-10-05T10:00:00',
    fecha_cierre: null,
    detalles: [],
    etiqueta_proceso: 'Rechazado',
    explicacion_proceso: 'Rechazado: el pedido no se retirará.',
    gestionado_por_administrador: {
      usuario_id: 8,
      nombre: 'Cristian',
      apellido: 'Gonzalez',
    },
  },
  {
    ticket_id: 7,
    usuario_id: 1,
    prioridad_id: 1,
    estado_id: 3,
    asunto: 'Ticket entregado al solicitante',
    descripcion: null,
    fecha_creacion: '2026-10-06T10:00:00',
    fecha_cierre: FECHA_CIERRE,
    detalles: [],
    etiqueta_proceso: 'Entregado',
    explicacion_proceso: 'Entregado: confirmado por el solicitante.',
    entrega_confirmada: true,
    gestionado_por_bodeguero: { usuario_id: 9, nombre: 'Luis', apellido: 'Illanes' },
  },
];

/**
 * Fixture de T7 (filtros): no deforma la de T6. Cubre
 * - dos prioridades (1 y 2),
 * - asuntos con acentos (`Reposición de tóner`) y sin ellos (`Reposicion de
 *   sillas`) para probar la busqueda insensible a mayusculas y acentos,
 * - `%` (ticket 3) y `_` (ticket 4) literales para probar que no son comodines,
 * - estados con mas de un ticket (EnRevision: 1, 2 y 6; EnCurso: 3, 4 y 5)
 *   para ver el contador bajar al filtrar.
 */
const TICKETS_FILTROS: Ticket[] = [
  {
    ticket_id: 1,
    usuario_id: 5,
    prioridad_id: 1,
    estado_id: 1,
    asunto: 'Reposición de tóner',
    descripcion: null,
    fecha_creacion: '2026-10-01T10:00:00',
    fecha_cierre: null,
    detalles: [],
  },
  {
    ticket_id: 2,
    usuario_id: 1,
    prioridad_id: 2,
    estado_id: 1,
    asunto: 'Compra de resmas',
    descripcion: null,
    fecha_creacion: '2026-10-02T10:00:00',
    fecha_cierre: null,
    detalles: [],
  },
  {
    ticket_id: 3,
    usuario_id: 5,
    prioridad_id: 1,
    estado_id: 2,
    asunto: 'Descuento del 50% en papel',
    descripcion: null,
    fecha_creacion: '2026-10-03T10:00:00',
    fecha_cierre: null,
    detalles: [],
  },
  {
    ticket_id: 4,
    usuario_id: 1,
    prioridad_id: 2,
    estado_id: 2,
    asunto: 'Guantes_de látex',
    descripcion: null,
    fecha_creacion: '2026-10-04T10:00:00',
    fecha_cierre: null,
    detalles: [],
  },
  {
    ticket_id: 5,
    usuario_id: 5,
    prioridad_id: 1,
    estado_id: 2,
    asunto: 'Reposicion de sillas',
    descripcion: null,
    fecha_creacion: '2026-10-05T10:00:00',
    fecha_cierre: null,
    detalles: [],
  },
  {
    ticket_id: 6,
    usuario_id: 1,
    prioridad_id: 2,
    estado_id: 1,
    asunto: 'Solicitud de papel',
    descripcion: null,
    fecha_creacion: '2026-10-06T10:00:00',
    fecha_cierre: null,
    detalles: [],
  },
];

/**
 * Enmienda 27/Nov/2026 (AC-28…AC-30): reloj fijo y fixtures relativos al
 * calendario local. La semana del 28/Nov/2026 empieza el lunes 23/Nov, el mes
 * el 1/Nov y el año el 1/Ene. Los tickets de 0/3/10/40/400 días producen la
 * matriz Todo 5 / Hoy 1 / Semana 2 / Mes 3 / Año 4.
 */
const AHORA_TABLERO = new Date(2026, 10, 28, 15, 0, 0);

function fechaIsoLocal(fecha: Date): string {
  const dos = (valor: number) => String(valor).padStart(2, '0');
  const tres = (valor: number) => String(valor).padStart(3, '0');
  return `${fecha.getFullYear()}-${dos(fecha.getMonth() + 1)}-${dos(
    fecha.getDate()
  )}T${dos(fecha.getHours())}:${dos(fecha.getMinutes())}:${dos(
    fecha.getSeconds()
  )}.${tres(fecha.getMilliseconds())}`;
}

function fechaHaceDias(dias: number, hora = 12): string {
  const fecha = new Date(AHORA_TABLERO);
  fecha.setDate(fecha.getDate() - dias);
  fecha.setHours(hora, 0, 0, 0);
  return fechaIsoLocal(fecha);
}

function ticketPeriodo(
  ticket_id: number,
  estado_id: number,
  fecha_creacion: string,
  prioridad_id = 1,
  asunto = `Pedido ${ticket_id}`,
  fecha_cierre: string | null = null
): Ticket {
  return {
    ticket_id,
    usuario_id: 5,
    prioridad_id,
    estado_id,
    asunto,
    descripcion: null,
    fecha_creacion,
    fecha_cierre,
    detalles: [],
  };
}

const TICKETS_PERIODO: Ticket[] = [
  ticketPeriodo(101, 1, fechaHaceDias(0), 1, 'Pedido de hoy'),
  ticketPeriodo(102, 2, fechaHaceDias(3), 2, 'Pedido de la semana'),
  ticketPeriodo(103, 1, fechaHaceDias(10), 2, 'Pedido del mes'),
  ticketPeriodo(104, 3, fechaHaceDias(40), 1, 'Pedido del año', fechaHaceDias(0)),
  ticketPeriodo(105, 4, fechaHaceDias(400), 1, 'Pedido histórico'),
];

/** Dos parejas con la misma fecha para ejercitar el desempate por ticket_id. */
const FECHA_EMPATE_PERIODO = fechaHaceDias(8);
const TICKETS_ORDEN: Ticket[] = [
  ticketPeriodo(201, 1, FECHA_EMPATE_PERIODO, 1, 'Empate revisión A'),
  ticketPeriodo(202, 1, FECHA_EMPATE_PERIODO, 1, 'Empate revisión B'),
  ticketPeriodo(203, 3, FECHA_EMPATE_PERIODO, 1, 'Empate terminado A'),
  ticketPeriodo(204, 4, FECHA_EMPATE_PERIODO, 1, 'Empate terminado B'),
];

/**
 * Respuesta completa de `POST /tickets/` (T9): el componente consume el
 * `Ticket` entero, no un `{ ticket_id }` parcial, asi que los tests del modal
 * tienen que responder con esta forma.
 */
function ticketRespuesta(ticket_id: number, estado_id = 1): Ticket {
  return {
    ticket_id,
    usuario_id: 5,
    prioridad_id: 1,
    estado_id,
    asunto: 'Falta de papel',
    descripcion: null,
    fecha_creacion: '2026-10-07T10:00:00',
    fecha_cierre: null,
    detalles: [],
  };
}

/** Ticket del catalogo de la enmienda con su etiqueta de proceso visible. */
function ticketRetiro(
  ticket_id: number,
  estado_id: number,
  etiquetaProceso: string,
): Ticket {
  return {
    ...ticketRespuesta(ticket_id, estado_id),
    etiqueta_proceso: etiquetaProceso,
    explicacion_proceso: `${etiquetaProceso}: detalle del proceso.`,
  };
}

/**
 * `201` de `POST /tickets/` desde la corrección post-cierre T31: el backend
 * devuelve el read model de proceso completo, no el ORM desnudo. El tablero
 * inserta esta respuesta sin reconsultar, así que la tarjeta del pedido nuevo
 * debe mostrar «En revisión» y no el nombre canónico del estado.
 */
function ticketRespuestaConReadModel(ticket_id: number, estado_id = 1): Ticket {
  return {
    ...ticketRespuesta(ticket_id, estado_id),
    etiqueta_proceso: 'En revisión',
    explicacion_proceso:
      'En revisión: pendiente de revisión por Bodega o Administración.',
    estado_orden_cobertura: null,
    stock_disponible: false,
    entrega_confirmada: false,
    gestionado_por_bodeguero: null,
    gestionado_por_administrador: {
      usuario_id: 1,
      nombre: 'Ana',
      apellido: 'Perez',
    },
  };
}

describe('TicketsComponent', () => {
  let fixture: ComponentFixture<TicketsComponent>;
  let componente: TicketsComponent;
  let httpMock: HttpTestingController;

  /**
   * Identidad local (`/auth/me`) que el modal presenta como autor informativo.
   * El contrato ya incluye `departamento` (Feature 008, AC-22), pero el modal
   * solo muestra nombre, apellido y correo.
   */
  let identidad: WritableSignal<IdentidadAutenticada | null>;

  function crearIdentidad(usuario_id = 5): IdentidadAutenticada {
    return {
      usuario_id,
      sub: 'user_tickets',
      nombre: 'Isabel',
      apellido: 'Contreras',
      correo: 'isabel.contreras@losalpes.cl',
      rol: 'Solicitante',
      institucion: { institucion_id: '1', nombre: 'Los Alpes' },
      sede: null,
      departamento: null,
    };
  }

  /** Responde las dos peticiones del arranque del tablero. */
  function responderArranque(
    catalogos: CatalogosTicket = CATALOGOS,
    tickets: Ticket[] = TICKETS
  ) {
    httpMock.expectOne(RUTA_CATALOGOS).flush(catalogos);
    httpMock.expectOne(RUTA_TICKETS).flush(tickets);
    fixture.detectChanges();
  }

  /**
   * Abre el modal con los catalogos ya cargados por el arranque del tablero,
   * asi `abrirModal()` no vuelve a pedirlos.
   */
  function abrirConCatalogos(catalogos: CatalogosTicket = CATALOGOS) {
    responderArranque(catalogos);
    componente.abrirModal();
    fixture.detectChanges();
  }

  /** Deja el formulario valido con un solo detalle. */
  function completarFormulario() {
    const formulario = componente.formulario;
    formulario.controls.prioridad_id.setValue(1);
    formulario.controls.asunto.setValue('Falta de papel');
    componente.detalles.at(0).controls.producto_id.setValue(1);
    componente.detalles.at(0).controls.cantidad_solicitada.setValue(3);
  }

  beforeEach(async () => {
    // El tablero no condiciona su lectura al rol (D-14: sin controles de
    // mutación que ocultar), pero el alta de pedidos sí se oculta por rol
    // (enmienda 007, 26/Nov/2026) y el modal lee la identidad para presentar
    // el autor informativo (AC-34). Se inyecta un doble con una señal para
    // poder variarla.
    identidad = signal<IdentidadAutenticada | null>(crearIdentidad());

    await TestBed.configureTestingModule({
      imports: [TicketsComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: AutenticacionService, useValue: { identidad } },
        provideRouter([]),
      ],
    }).compileComponents();

    httpMock = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(TicketsComponent);
    componente = fixture.componentInstance;
    fixture.detectChanges();
  });

  afterEach(() => {
    httpMock.verify({ ignoreCancelled: true });
  });

  describe('carga de catalogos', () => {
    it('debe cargar catalogos y tickets al construir el componente', () => {
      httpMock.expectOne(RUTA_CATALOGOS).flush(CATALOGOS);
      httpMock.expectOne(RUTA_TICKETS).flush(TICKETS);
      fixture.detectChanges();

      expect(componente.catalogos()).not.toBeNull();
      expect(componente.tickets().length).toBe(TICKETS.length);
      expect(componente.cargandoTablero()).toBe(false);
      expect(componente.errorTablero()).toBeNull();
    });

    it('no debe volver a pedir los catalogos al abrir el modal si ya estan cargados', () => {
      responderArranque();

      componente.abrirModal();
      fixture.detectChanges();

      httpMock.expectNone(RUTA_CATALOGOS);
      expect(componente.catalogos()).not.toBeNull();
    });

    it('debe exponer los cuatro catalogos como senales', () => {
      abrirConCatalogos();

      expect(componente.prioridades().length).toBe(2);
      expect(componente.estados().length).toBe(4);
      expect(componente.productos().length).toBe(2);
      // AC-35: `solicitantes` se conserva como catálogo de **lectura** para
      // resolver el autor de las tarjetas; ya no alimenta ningún selector del alta.
      expect(componente.solicitantes().length).toBe(2);
    });

    it('debe arrancar el estado en EnRevision por nombre canonico, no por orden', () => {
      abrirConCatalogos();

      expect(componente.estadoEnRevision()?.nombre).toBe('EnRevision');
      expect(componente.estadoInicial()).toBe(1);
      expect(componente.formulario.controls.estado_id.value).toBe(1);
    });

    it('debe preseleccionar la prioridad Media y dejarla cambiable', () => {
      abrirConCatalogos();

      expect(componente.prioridadInicial()).toBe(2);
      expect(componente.formulario.controls.prioridad_id.value).toBe(2);
      expect(componente.formulario.controls.prioridad_id.valid).toBe(true);
    });

    it('debe exponer el error del tablero si falla el arranque', () => {
      httpMock
        .expectOne(RUTA_CATALOGOS)
        .flush('Falla', { status: 500, statusText: 'Server Error' });
      fixture.detectChanges();

      expect(componente.errorTablero()).toBeTruthy();
      expect(componente.errorGuardado()).toBeNull();
      expect(componente.cargandoTablero()).toBe(false);
    });

    it('debe exponer errorCatalogos al abrir el modal si el catalogo no se cargo', () => {
      httpMock
        .expectOne(RUTA_CATALOGOS)
        .flush('Falla', { status: 500, statusText: 'Server Error' });
      fixture.detectChanges();

      componente.abrirModal();
      httpMock
        .expectOne(RUTA_CATALOGOS)
        .flush('Falla', { status: 500, statusText: 'Server Error' });
      fixture.detectChanges();

      expect(componente.errorCatalogos()).toBeTruthy();
    });

    it('no debe pedir catalogos al reabrir el modal con catalogos cargados', () => {
      abrirConCatalogos();
      componente.cerrarModal();

      componente.abrirModal();
      fixture.detectChanges();

      httpMock.expectNone(RUTA_CATALOGOS);
      expect(componente.errorCatalogos()).toBeNull();
      expect(componente.cargandoCatalogos()).toBe(false);
    });
  });

  describe('detalles', () => {
    beforeEach(() => abrirConCatalogos());

    it('debe partir con una fila de detalle', () => {
      expect(componente.detalles.length).toBe(1);
    });

    it('debe agregar y quitar filas', () => {
      componente.agregarDetalle();
      expect(componente.detalles.length).toBe(2);

      componente.quitarDetalle(1);
      expect(componente.detalles.length).toBe(1);
    });

    it('no debe permitir quitar la ultima fila', () => {
      expect(componente.puedeQuitarDetalle()).toBe(false);
      componente.quitarDetalle(0);
      expect(componente.detalles.length).toBe(1);
    });

    it('debe sumar las cantidades de un producto repetido', () => {
      componente.agregarDetalle();
      componente.detalles.at(0).controls.producto_id.setValue(1);
      componente.detalles.at(0).controls.cantidad_solicitada.setValue(2);
      componente.detalles.at(1).controls.producto_id.setValue(1);
      componente.detalles.at(1).controls.cantidad_solicitada.setValue(5);

      expect(componente.combinarDetalles()).toEqual([
        { producto_id: 1, cantidad_solicitada: 7 },
      ]);
    });

    it('debe conservar productos distintos como lineas separadas', () => {
      componente.agregarDetalle();
      componente.detalles.at(0).controls.producto_id.setValue(1);
      componente.detalles.at(0).controls.cantidad_solicitada.setValue(2);
      componente.detalles.at(1).controls.producto_id.setValue(2);
      componente.detalles.at(1).controls.cantidad_solicitada.setValue(1);

      expect(componente.combinarDetalles()).toEqual([
        { producto_id: 1, cantidad_solicitada: 2 },
        { producto_id: 2, cantidad_solicitada: 1 },
      ]);
    });
  });

  describe('validacion del formulario', () => {
    beforeEach(() => abrirConCatalogos());

    it('no debe enviar si el formulario es invalido', () => {
      componente.enviar();

      const pendientes = httpMock.match(RUTA_TICKETS);
      expect(pendientes.length).toBe(0);
    });

    it('debe marcar los controles como tocados al intentar enviar', () => {
      componente.enviar();

      expect(componente.formulario.controls.asunto.touched).toBe(true);
    });

    it('debe rechazar un asunto de menos de 3 caracteres', () => {
      completarFormulario();
      componente.formulario.controls.asunto.setValue('ab');

      expect(componente.formulario.invalid).toBe(true);
    });

    it('debe rechazar un asunto de mas de 150 caracteres', () => {
      completarFormulario();
      componente.formulario.controls.asunto.setValue('x'.repeat(151));

      expect(componente.formulario.invalid).toBe(true);
    });

    it('debe aceptar un asunto de exactamente 150 caracteres', () => {
      completarFormulario();
      componente.formulario.controls.asunto.setValue('x'.repeat(150));

      expect(componente.formulario.valid).toBe(true);
    });

    it('debe rechazar una cantidad de 0', () => {
      completarFormulario();
      componente.detalles.at(0).controls.cantidad_solicitada.setValue(0);

      expect(componente.formulario.invalid).toBe(true);
    });

    it('debe aceptar una descripción de 500 y rechazar 501', () => {
      completarFormulario();
      componente.formulario.controls.descripcion.setValue('x'.repeat(500));
      expect(componente.formulario.valid).toBe(true);

      componente.formulario.controls.descripcion.setValue('x'.repeat(501));
      expect(componente.formulario.controls.descripcion.hasError('maxlength')).toBe(true);
    });

    it('debe limitar el textarea de descripción a 500 caracteres', () => {
      const textarea = fixture.nativeElement.querySelector(
        'dialog textarea[formcontrolname="descripcion"]',
      ) as HTMLTextAreaElement;

      expect(textarea.getAttribute('maxlength')).toBe('500');
    });
  });

  describe('envio', () => {
    beforeEach(() => abrirConCatalogos());

    it('debe enviar el ticket y avisar el id creado', () => {
      completarFormulario();
      componente.enviar();

      const peticion = httpMock.expectOne(RUTA_TICKETS);
      expect(peticion.request.method).toBe('POST');
      // AC-34: el cuerpo no incluye `usuario_id`; el servidor atribuye la
      // autoría a la identidad de sesión (E22-1).
      expect(peticion.request.body).toEqual({
        prioridad_id: 1,
        estado_id: 1,
        asunto: 'Falta de papel',
        descripcion: null,
        detalles: [{ producto_id: 1, cantidad_solicitada: 3 }],
      });
      expect('usuario_id' in peticion.request.body).toBe(false);

      peticion.flush(ticketRespuesta(42));
      fixture.detectChanges();

      expect(componente.ticketCreado()).toBe(42);
      expect(componente.modalAbierto()).toBe(false);
    });

    it('debe enviar las cantidades ya sumadas', () => {
      completarFormulario();
      componente.agregarDetalle();
      componente.detalles.at(1).controls.producto_id.setValue(1);
      componente.detalles.at(1).controls.cantidad_solicitada.setValue(4);
      componente.enviar();

      const cuerpo = httpMock.expectOne(RUTA_TICKETS).request.body;
      expect(cuerpo.detalles).toEqual([{ producto_id: 1, cantidad_solicitada: 7 }]);
    });

    it('debe limpiar el formulario tras un envio correcto', () => {
      completarFormulario();
      componente.enviar();
      httpMock.expectOne(RUTA_TICKETS).flush(ticketRespuesta(42));

      expect(componente.formulario.controls.asunto.value).toBe('');
      expect(componente.detalles.length).toBe(1);
    });

    it('no debe permitir el doble envio', () => {
      completarFormulario();
      componente.enviar();

      expect(componente.guardando()).toBe(true);

      componente.enviar();

      // `expectOne` lanza si hay **mas de una** peticion pendiente, asi que esta
      // linea es la que verifica que el segundo `enviar()` no salio. (Un `match`
      // no serviria: ademas de permitir duplicados, `expectOne` ya retiro la
      // primera peticion del backend de pruebas.)
      httpMock.expectOne(RUTA_TICKETS).flush(ticketRespuesta(42));
    });

    it('debe deshabilitar el envio mientras guarda', () => {
      completarFormulario();
      componente.enviar();
      const peticion = httpMock.expectOne(RUTA_TICKETS);

      expect(componente.guardando()).toBe(true);

      peticion.flush(ticketRespuesta(42));
      expect(componente.guardando()).toBe(false);
    });

    it('debe dejar el modal abierto y mostrar el error si el backend falla', () => {
      completarFormulario();
      componente.enviar();
      httpMock
        .expectOne(RUTA_TICKETS)
        .flush({ detail: 'No existe producto indicado: 99' }, { status: 404, statusText: 'Not Found' });
      fixture.detectChanges();

      expect(componente.modalAbierto()).toBe(true);
      expect(componente.errorGuardado()).toContain('No existe producto');
      expect(componente.ticketCreado()).toBeNull();
    });

    it('debe mapear un 422 por campo a su mensaje traducido', () => {
      // El formulario se envia **valido** a proposito: si estuviera invalido,
      // `enviar()` lo cortaria antes del POST y no habria nada que mapear. Lo
      // que se prueba aqui es la traduccion de un 422 que llega del servidor,
      // por ejemplo si las reglas del backend cambiasen antes que el espejo del
      // cliente.
      completarFormulario();
      componente.enviar();

      httpMock.expectOne(RUTA_TICKETS).flush(
        {
          detail: [
            {
              loc: ['body', 'asunto'],
              msg: 'String should have at most 150 characters',
              type: 'string_too_long',
            },
          ],
        },
        { status: 422, statusText: 'Unprocessable Entity' }
      );
      fixture.detectChanges();

      expect(componente.mensajeDe('asunto')).toBe('No puede superar los 150 caracteres.');
    });

    it('debe mostrar el campo culpable ante un 422 de descripción sin 500', () => {
      completarFormulario();
      componente.formulario.controls.descripcion.setValue('x'.repeat(501));
      // Se fuerza valido en el cliente para simular que el backend rechaza un
      // valor que el espejo local aun no limitaba.
      componente.formulario.controls.descripcion.clearValidators();
      componente.formulario.controls.descripcion.updateValueAndValidity();
      componente.enviar();

      httpMock.expectOne(RUTA_TICKETS).flush(
        {
          detail: [
            {
              loc: ['body', 'descripcion'],
              msg: 'String should have at most 500 characters',
              type: 'string_too_long',
            },
          ],
        },
        { status: 422, statusText: 'Unprocessable Entity' }
      );
      fixture.detectChanges();

      const texto = (fixture.nativeElement.querySelector('dialog')?.textContent ?? '')
        .replace(/\s+/g, ' ');
      expect(texto).toContain('Descripción');
      expect(texto).toContain('No puede superar los 500 caracteres.');
      expect(componente.errorGuardado()).toBe('Revisa los campos marcados.');
    });

    it('debe ubicar un 422 de detalle en su fila', () => {
      completarFormulario();
      // Ambas filas quedan validas en el cliente; el 422 simula que el servidor
      // rechazo la segunda fila. Se omite `agregarDetalle()` y se usa la fila
      // unica con indice 0 a proposito: al combinar, dos filas del **mismo**
      // producto se funden en una, asi que un `loc` con indice 1 solo es
      // reproducible si hay dos filas de productos distintos.
      componente.agregarDetalle();
      componente.detalles.at(1).controls.producto_id.setValue(2);
      componente.detalles.at(1).controls.cantidad_solicitada.setValue(2);
      componente.enviar();

      httpMock.expectOne(RUTA_TICKETS).flush(
        {
          detail: [
            {
              loc: ['body', 'detalles', 1, 'cantidad_solicitada'],
              msg: 'Input should be greater than 0',
              type: 'greater_than',
            },
          ],
        },
        { status: 422, statusText: 'Unprocessable Entity' }
      );
      fixture.detectChanges();

      expect(componente.mensajeDeDetalle(1)).toBe('Debe ser mayor que 0.');
      expect(componente.mensajeDeDetalle(0)).toBeNull();
    });
  });

  describe('cierre del modal', () => {
    beforeEach(() => abrirConCatalogos());

    it('debe cerrar el modal al cancelar', () => {
      componente.cerrarModal();

      expect(componente.modalAbierto()).toBe(false);
    });

    it('debe abrir el dialogo nativo en el DOM', () => {
      // `showModal()` no existe en el DOM de prueba si el `@if` no renderizo el
      // elemento; verificar `open` confirma que el `effect` llego a ejecutarlo.
      expect(componente.dialogo().nativeElement.open).toBe(true);
    });
  });

  describe('tablero Kanban', () => {
    it('debe mostrar las tres columnas del flujo, en orden (AC-62)', () => {
      responderArranque(CATALOGOS_013, TICKETS_013);

      const columnas = componente.columnas();
      expect(columnas.map((columna) => columna.clave)).toEqual([
        'EnRevision',
        'EnCurso',
        'Terminados',
      ]);
      expect(columnas.map((columna) => columna.estado)).toEqual([
        'EnRevision',
        'EnCurso',
        'Terminados',
      ]);
      expect(columnas.map((columna) => columna.etiqueta)).toEqual([
        'En Revisión',
        'En Curso',
        'Terminados',
      ]);
      // La columna agrupada declara los estados terminales del catálogo.
      expect(columnas[2].estado_ids).toEqual([3, 4]);

      // `EnCurso` agrupa sus dos tickets del fixture.
      const enCurso = columnas.find((columna) => columna.clave === 'EnCurso')!;
      expect(enCurso.estado_ids).toEqual([2]);
      expect(enCurso.tarjetas.length).toBe(2);
    });

    it('el contenedor del tablero usa una rejilla de tres columnas y no de cuatro (regresión visual)', () => {
      responderArranque();

      const tablero: HTMLElement | null = fixture.nativeElement.querySelector(
        '[data-testid="tablero-pedidos"]'
      );
      expect(tablero).not.toBeNull();
      expect(tablero!.classList.contains('grid-cols-1')).toBe(true);
      expect(tablero!.classList.contains('md:grid-cols-3')).toBe(true);
      expect(tablero!.classList.contains('md:grid-cols-4')).toBe(false);
    });

    it('debe agrupar cada ticket en la columna de su estado', () => {
      responderArranque();

      const columnas = componente.columnas();
      const enRevision = columnas.find((columna) => columna.clave === 'EnRevision')!;
      const enCurso = columnas.find((columna) => columna.clave === 'EnCurso')!;

      expect(enRevision.estado_ids).toEqual([1]);
      expect(enCurso.estado_ids).toEqual([2]);
      expect(enRevision.tarjetas.map((tarjeta) => tarjeta.ticket.ticket_id).sort()).toEqual([
        1, 2,
      ]);
      expect(enCurso.tarjetas.map((tarjeta) => tarjeta.ticket.ticket_id).sort()).toEqual([
        3, 4,
      ]);
    });

    it('debe ordenar por fecha de creacion DESC y, en empate, por ticket_id DESC', () => {
      responderArranque();

      const columnas = componente.columnas();

      // Estado 1: fechas distintas -> el 2 (03-10) va antes que el 1 (01-10).
      const enRevision = columnas.find((columna) => columna.clave === 'EnRevision')!;
      expect(enRevision.tarjetas.map((tarjeta) => tarjeta.ticket.ticket_id)).toEqual([2, 1]);

      // Estado 2: misma fecha -> desempata por ticket_id descendente -> 4 antes que 3.
      const enCurso = columnas.find((columna) => columna.clave === 'EnCurso')!;
      expect(enCurso.tarjetas.map((tarjeta) => tarjeta.ticket.ticket_id)).toEqual([4, 3]);
    });

    it('debe resolver asunto, prioridad, solicitante y fechas en la tarjeta', () => {
      responderArranque();

      const tarjetas = componente
        .columnas()
        .flatMap((columna) => columna.tarjetas);

      const conCierre = tarjetas.find((tarjeta) => tarjeta.ticket.ticket_id === 4)!;
      expect(conCierre.asunto).toBe('Grapas');
      expect(conCierre.prioridad).toBe('Media');
      expect(conCierre.clasePrioridad).toContain('bg-');
      expect(conCierre.solicitante).toBe('Fernandez, Camila · Direccion');
      expect(conCierre.fechaCreacion).toBe(FECHA_EMPATE);
      expect(conCierre.fechaCierre).toBe(FECHA_CIERRE);

      const sinCierre = tarjetas.find((tarjeta) => tarjeta.ticket.ticket_id === 1)!;
      expect(sinCierre.asunto).toBe('Falta de papel');
      expect(sinCierre.prioridad).toBe('Alta');
      expect(sinCierre.solicitante).toBe('Contreras, Isabel · Docencia');
      expect(sinCierre.fechaCreacion).toBe('2026-10-01T10:00:00');
      expect(sinCierre.fechaCierre).toBeNull();

      // Sin read model en el fixture, la etiqueta cae al nombre canónico del
      // estado y los responsables a «Sin gestión registrada» (fallbacks de
      // AC-37/AC-40).
      expect(sinCierre.estadoCanonico).toBe('EnRevision');
      expect(sinCierre.etiquetaProceso).toBe('En Revisión');
      expect(sinCierre.explicacionProceso).toBe('');
      expect(sinCierre.gestorBodeguero).toBe('Sin gestión registrada');
      expect(sinCierre.tieneGestorBodeguero).toBe(false);
      expect(sinCierre.gestorAdministrador).toBe('Sin gestión registrada');
      expect(sinCierre.tieneGestorAdministrador).toBe(false);
    });

    it('debe tratar un catalogo de estados vacio como error visible', () => {
      responderArranque({ ...CATALOGOS, estados: [] });

      expect(componente.cargandoTablero()).toBe(false);
      expect(componente.errorTablero()).toBeTruthy();
      expect(componente.columnas().length).toBe(0);
    });
  });

  /**
   * D-14 / AC-24 (013): el tablero es de solo lectura. Deroganse en la capa de
   * UI los AC-9, AC-10, AC-12, AC-19 y AC-20 de la 004 (transiciones por
   * botón en el tablero y su feedback): cada tarjeta completa es un enlace que
   * abre la vista de detalle, donde vive todo el ciclo de vida. Aqui se
   * verifica tanto el comportamiento nuevo como la **ausencia** de la logica
   * de transiciones que la 004 exibia.
   */
  describe('tablero de solo lectura (D-14, AC-24)', () => {
    /** Busca una tarjeta por el id de su ticket, aplanando las columnas. */
    function tarjetaDe(ticketId: number) {
      return componente
        .columnas()
        .flatMap((columna) => columna.tarjetas)
        .find((tarjeta) => tarjeta.ticket.ticket_id === ticketId);
    }

    /** Las tarjetas-enlace que el DOM pinta, una por tarjeta. */
    function tarjetasEnlazadas() {
      return fixture.nativeElement.querySelectorAll(
        'a[href^="/tickets/"]'
      ) as NodeListOf<HTMLAnchorElement>;
    }

    beforeEach(() => responderArranque(CATALOGOS_013, TICKETS_013));

    it('ofrece exactamente una tarjeta-enlace por ticket, sin controles de transición', () => {
      // Una por tarjeta, sin importar su estado.
      expect(tarjetasEnlazadas().length).toBe(TICKETS_013.length);

      // Ni botones de avanzar/retroceder ni su texto en el tablero.
      expect(
        fixture.nativeElement.querySelector('button[aria-label^="Avanzar ticket"]')
      ).toBeNull();
      expect(
        fixture.nativeElement.querySelector('button[aria-label^="Retroceder ticket"]')
      ).toBeNull();
      const texto = fixture.nativeElement.textContent ?? '';
      expect(texto).not.toContain('Avanzar');
      expect(texto).not.toContain('Retroceder');
      // El botón «Gestionar» desapareció: la tarjeta entera es el enlace.
      expect(texto).not.toContain('Gestionar');

      // Ningún `PATCH /estado` sale del tablero: la única red del arranque fue
      // catálogos + lista.
      httpMock.expectNone(RUTA_ESTADO(1));
      httpMock.expectNone(RUTA_ESTADO(6));
    });

    it('ofrece la tarjeta-enlace también en la columna terminal Terminados', () => {
      expect(tarjetaDe(5)).toBeTruthy(); // Cerrado → «Retirado»
      expect(tarjetaDe(6)).toBeTruthy(); // Anulado → «Rechazado»
      expect(tarjetaDe(7)).toBeTruthy(); // Cerrado → «Entregado»

      expect(
        fixture.nativeElement.querySelector('a[href="/tickets/5"]')
      ).not.toBeNull();
      expect(
        fixture.nativeElement.querySelector('a[href="/tickets/6"]')
      ).not.toBeNull();
      expect(
        fixture.nativeElement.querySelector('a[href="/tickets/7"]')
      ).not.toBeNull();
    });

    it('no conserva lógica de transición en el componente ni en la tarjeta (sin código muerto)', () => {
      // Nada de la UI de movimientos de la 004 sobrevive en la clase.
      for (const nombre of [
        'mover',
        'moverSiguiente',
        'moverAnterior',
        'errorMovimiento',
        'enProceso',
        'puedeGestionarKanban',
        'idEstadoEnCurso',
      ]) {
        expect(nombre in componente).withContext(nombre).toBe(false);
      }

      // Ni en la tarjeta, que ya no resuelve controles de mutación.
      const tarjeta = tarjetaDe(1)!;
      for (const nombre of [
        'puedeAvanzar',
        'puedeRetroceder',
        'estadoSiguienteId',
        'estadoAnteriorId',
        'enProceso',
      ]) {
        expect(nombre in tarjeta).withContext(nombre).toBe(false);
      }
    });

    it('la tarjeta navega a la ruta de detalle del ticket', () => {
      const router = TestBed.inject(Router);
      const navegacion = spyOn(router, 'navigateByUrl').and.returnValue(
        Promise.resolve(true)
      );

      const enlace = fixture.nativeElement.querySelector(
        'a[href="/tickets/1"]'
      ) as HTMLAnchorElement;
      expect(enlace).not.toBeNull();
      // La ruta hija `tickets/:ticketId` del T10.
      expect(enlace.getAttribute('href')).toBe('/tickets/1');

      enlace.click();

      // El click entra al Router (no a una navegación del navegador) y su
      // destino es la ruta de detalle del ticket.
      expect(navegacion).toHaveBeenCalledTimes(1);
      const destino = navegacion.calls.mostRecent().args[0] as UrlTree;
      expect(router.serializeUrl(destino)).toBe('/tickets/1');
      // La navegación no consulta nada: el detalle carga en su propio componente.
      expect(httpMock.match(() => true).length).toBe(0);
    });

    it('no pinta el banner de «solo consulta» de la 004 (derogado con D-14)', () => {
      // El tablero ya no muta para nadie: no hay controles de transición que
      // ocultar. La única pieza condicionada al rol es el alta de pedidos
      // (enmienda 007, 26/Nov/2026), no el Kanban.
      expect(fixture.nativeElement.textContent).not.toContain('Vista de solo consulta');
      expect(
        fixture.nativeElement.querySelector('button[aria-label^="Avanzar ticket"]')
      ).toBeNull();
      expect(
        fixture.nativeElement.querySelector('button[aria-label^="Retroceder ticket"]')
      ).toBeNull();
    });

    it('hace exactamente dos peticiones al arranque y ninguna por tarjeta (sin N+1)', () => {
      // `responderArranque` ya descargo catálogos y lista: el render de las
      // cuatro columnas con siete tarjetas no añade peticiones…
      expect(tarjetasEnlazadas().length).toBe(TICKETS_013.length);

      // …ni los filtros, que son de cliente sobre el conjunto cargado…
      componente.cambiarPrioridad('1');
      fixture.detectChanges();
      componente.actualizarBusqueda('papel');
      fixture.detectChanges();

      // …ni la navegación al detalle.
      (fixture.nativeElement.querySelector(
        'a[href="/tickets/3"]'
      ) as HTMLAnchorElement).click();
      fixture.detectChanges();

      expect(httpMock.match(() => true).length).toBe(0);
    });
  });

  /**
   * D-24 / AC-41 (ampliación 25/Nov/2026): el tablero conserva las columnas
   * operativas y agrupa `Cerrado` y `Anulado` en una única columna terminal
   * «Terminados», sin columna `Anulado` separada. La agrupación se resuelve por
   * nombre normalizado del catálogo, nunca por ids fijos.
   */
  describe('columna Terminados (D-24, AC-41)', () => {
    it('agrupa Cerrado y Anulado en una sola columna y suma el contador', () => {
      responderArranque(CATALOGOS_013, TICKETS_013);

      const columnas = componente.columnas();
      expect(columnas.map((columna) => columna.estado)).toEqual([
        'EnRevision',
        'EnCurso',
        'Terminados',
      ]);
      // Ninguna columna lleva el nombre del terminal negativo.
      expect(columnas.some((columna) => columna.estado === 'Anulado')).toBe(false);

      const terminados = columnas.find((columna) => columna.clave === 'Terminados')!;
      expect(terminados.estado_ids).toEqual([3, 4]);
      expect(
        terminados.tarjetas.map((tarjeta) => tarjeta.ticket.ticket_id).sort()
      ).toEqual([5, 6, 7]);
      // El contador de la columna suma ambos estados (Cerrado 5 y 7 + Anulado 6).
      expect(terminados.tarjetas.length).toBe(3);
    });

    it('cada tarjeta terminal muestra su etiqueta de proceso, no solo el color', () => {
      responderArranque(CATALOGOS_013, TICKETS_013);

      const terminados = componente
        .columnas()
        .find((columna) => columna.clave === 'Terminados')!;
      const etiquetas = new Map(
        terminados.tarjetas.map((tarjeta) => [
          tarjeta.ticket.ticket_id,
          tarjeta.etiquetaProceso,
        ])
      );
      expect(etiquetas.get(5)).toBe('Retirado');
      expect(etiquetas.get(7)).toBe('Entregado');
      expect(etiquetas.get(6)).toBe('Rechazado');

      const texto = fixture.nativeElement.textContent ?? '';
      expect(texto).toContain('Retirado');
      expect(texto).toContain('Entregado');
      expect(texto).toContain('Rechazado');
    });

    it('un ticket anulado queda solo en Terminados y conserva fecha_cierre nula', () => {
      responderArranque(CATALOGOS_013, TICKETS_013);

      const conElTicket = componente
        .columnas()
        .filter((columna) =>
          columna.tarjetas.some((tarjeta) => tarjeta.ticket.ticket_id === 6)
        );

      expect(conElTicket.length).toBe(1);
      expect(conElTicket[0].clave).toBe('Terminados');
      const anulado = conElTicket[0].tarjetas.find(
        (tarjeta) => tarjeta.ticket.ticket_id === 6
      )!;
      // `fecha_cierre` nula en el anulado (D-5): la tarjeta no pinta cierre.
      expect(anulado.fechaCierre).toBeNull();
      expect(anulado.estadoCanonico).toBe('Anulado');
    });

    it('no inventa Terminados si el catálogo no trae Cerrado ni Anulado', () => {
      const sinTerminales: CatalogosTicket = {
        ...CATALOGOS_013,
        estados: CATALOGOS_013.estados.filter(
          (estado) => estado.nombre !== 'Cerrado' && estado.nombre !== 'Anulado'
        ),
      };
      responderArranque(sinTerminales, []);

      expect(componente.columnas().map((columna) => columna.clave)).toEqual([
        'EnRevision',
        'EnCurso',
      ]);
    });

    it('agrupa por nombre normalizado aunque venga en otras mayúsculas', () => {
      // Catálogo hostil: `cerrado` y `ANULADO` con ids no canónicos.
      const hostil: CatalogosTicket = {
        ...CATALOGOS_013,
        estados: [
          { estado_id: 10, nombre: 'cerrado', descripcion: 'Minúsculas' },
          ...CATALOGOS_013.estados.filter(
            (estado) => estado.nombre !== 'Cerrado' && estado.nombre !== 'Anulado'
          ),
          { estado_id: 11, nombre: 'ANULADO', descripcion: 'Mayúsculas' },
        ],
      };
      responderArranque(hostil, []);

      const terminados = componente
        .columnas()
        .filter((columna) => columna.clave === 'Terminados');
      expect(terminados.length).toBe(1);
      expect([...terminados[0].estado_ids].sort()).toEqual([10, 11]);
    });
  });

  /**
   * §9.8 (AC-37/AC-40/AC-41): la tarjeta expone la etiqueta de proceso como
   * texto visible, la frase corta de forma accesible y los dos responsables del
   * historial, con «Sin gestión registrada» cuando falta alguno. Sigue siendo
   * un enlace al detalle sin controles de mutación.
   */
  describe('read model de la tarjeta (AC-37, AC-40, AC-41)', () => {
    /** Busca una tarjeta por el id de su ticket, aplanando las columnas. */
    function tarjetaDe(ticketId: number) {
      return componente
        .columnas()
        .flatMap((columna) => columna.tarjetas)
        .find((tarjeta) => tarjeta.ticket.ticket_id === ticketId)!;
    }

    beforeEach(() => responderArranque(CATALOGOS_013, TICKETS_013));

    it('resuelve etiqueta, frase y los dos responsables del read model', () => {
      const tarjeta = tarjetaDe(5);

      expect(tarjeta.estadoCanonico).toBe('Cerrado');
      expect(tarjeta.etiquetaProceso).toBe('Retirado');
      expect(tarjeta.explicacionProceso).toBe(
        'Retirado: pendiente de confirmación de entrega.'
      );
      expect(tarjeta.gestorBodeguero).toBe('Illanes, Luis');
      expect(tarjeta.tieneGestorBodeguero).toBe(true);
      expect(tarjeta.gestorAdministrador).toBe('Gonzalez, Cristian');
      expect(tarjeta.tieneGestorAdministrador).toBe(true);
    });

    it('muestra etiqueta, frase y responsables como texto visible (sin hover)', () => {
      const enlace = fixture.nativeElement.querySelector(
        'a[href="/tickets/5"]'
      ) as HTMLAnchorElement;
      const texto = (enlace.textContent ?? '').replace(/\s+/g, ' ');

      expect(texto).toContain('Retirado');
      expect(texto).toContain('Retirado: pendiente de confirmación de entrega.');
      expect(texto).toContain('Último Bodeguero:');
      expect(texto).toContain('Illanes, Luis');
      expect(texto).toContain('Último Administrador:');
      expect(texto).toContain('Gonzalez, Cristian');
    });

    it('sin responsable cae a «Sin gestión registrada» con — visible', () => {
      const tarjeta = tarjetaDe(7);
      expect(tarjeta.gestorBodeguero).toBe('Illanes, Luis');
      expect(tarjeta.gestorAdministrador).toBe('Sin gestión registrada');
      expect(tarjeta.tieneGestorAdministrador).toBe(false);

      const enlace = fixture.nativeElement.querySelector(
        'a[href="/tickets/7"]'
      ) as HTMLAnchorElement;
      const texto = (enlace.textContent ?? '').replace(/\s+/g, ' ');
      expect(texto).toContain('Último Administrador:');
      expect(texto).toContain('—');
      // El texto accesible acompaña al guion visual.
      expect(texto).toContain('Sin gestión registrada');
    });

    it('el aria-label incluye estado canónico, etiqueta y responsables', () => {
      const enlace = fixture.nativeElement.querySelector(
        'a[href="/tickets/5"]'
      ) as HTMLAnchorElement;
      const etiqueta = enlace.getAttribute('aria-label') ?? '';

      expect(etiqueta).toContain('Cerrado');
      expect(etiqueta).toContain('Retirado');
      expect(etiqueta).toContain('Illanes, Luis');
      expect(etiqueta).toContain('Gonzalez, Cristian');

      // La tarjeta sigue siendo un enlace, sin controles de mutación.
      expect(enlace.tagName).toBe('A');
      expect(enlace.querySelector('button, select, input, textarea')).toBeNull();
    });
  });

  /**
   * Enmienda 26/Nov/2026 (D-35/AC-51): el alta nace siempre en `EnRevision`,
   * resuelto por nombre canónico (no por la primera entrada del catálogo) y
   * mostrado como dato **fijo** (sin selector ni cambio por UI). El backend
   * responde 409 si llegara cualquier otro estado.
   */
  describe('alta con estado inicial fijo en EnRevision (AC-51)', () => {
    it('resuelve EnRevision por nombre y lo fija en el formulario', () => {
      abrirConCatalogos(CATALOGOS_013);

      expect(componente.estadoEnRevision()?.nombre).toBe('EnRevision');
      expect(componente.estadoInicial()).toBe(1);
      expect(componente.formulario.controls.estado_id.value).toBe(1);
    });

    it('muestra el estado como dato fijo y no ofrece selector de estado', () => {
      abrirConCatalogos(CATALOGOS_013);

      expect(
        fixture.nativeElement.querySelector('dialog select[formcontrolname="estado_id"]')
      ).toBeNull();

      const texto = (fixture.nativeElement.querySelector('dialog')?.textContent ?? '')
        .replace(/\s+/g, ' ');
      expect(texto).toContain('En Revisión');
      expect(texto).toContain('Fijo');
      expect(texto).toContain('no se puede cambiar');
      expect(texto).not.toContain('Editable para la demostración');
    });

    it('resuelve EnRevision por nombre aunque no sea el primer estado del catálogo', () => {
      // Catálogo hostil: `EnCurso` primero y `EnRevision` (id 7) en medio.
      const catalogoHostil: CatalogosTicket = {
        ...CATALOGOS_013,
        estados: [
          { estado_id: 8, nombre: 'EnCurso', descripcion: 'Primero' },
          { estado_id: 7, nombre: 'EnRevision', descripcion: 'No primero' },
          { estado_id: 9, nombre: 'anulado', descripcion: 'Terminal' },
        ],
      };
      abrirConCatalogos(catalogoHostil);

      expect(componente.nombreEstadoInicial()).toBe('En Revisión');
      expect(componente.estadoInicial()).toBe(7);
      expect(componente.formulario.controls.estado_id.value).toBe(7);
    });

    it('sin EnRevision en el catálogo bloquea el alta y lo avisa', () => {
      const catalogoSinRevision: CatalogosTicket = {
        ...CATALOGOS_013,
        estados: CATALOGOS_013.estados.filter(
          (estado) => estado.nombre !== 'EnRevision'
        ),
      };
      abrirConCatalogos(catalogoSinRevision);

      expect(componente.estadoInicial()).toBeNull();
      expect(componente.formulario.controls.estado_id.value).toBeNull();

      const texto = (fixture.nativeElement.querySelector('dialog')?.textContent ?? '')
        .replace(/\s+/g, ' ');
      expect(texto).toContain('no contiene el estado EnRevision');

      // El envío no sale: el control obligatorio quedó vacío (fail-closed).
      componente.formulario.controls.asunto.setValue('Sin estado inicial');
      componente.detalles.at(0).controls.producto_id.setValue(1);
      componente.enviar();
      expect(httpMock.match(RUTA_TICKETS).length).toBe(0);
    });

    it('resuelve EnRevision por nombre aunque Anulado venga primero', () => {
      // Catálogo degenerado: `anulado` en minúsculas y **primero** del arreglo.
      const catalogoAnuladoPrimero: CatalogosTicket = {
        ...CATALOGOS_013,
        estados: [
          { estado_id: 9, nombre: 'anulado', descripcion: 'Minuscula y primero' },
          ...CATALOGOS_013.estados.filter((estado) => estado.nombre !== 'Anulado'),
        ],
      };
      abrirConCatalogos(catalogoAnuladoPrimero);

      expect(componente.estadoInicial()).toBe(1);
    });
  });

  /**
   * Enmienda post-cierre 05/Nov/2026 (AC-27): la prioridad arranca en `Media`
   * (resuelta por nombre canónico) y sigue siendo cambiable; tras un alta
   * exitosa el formulario vuelve a los valores por defecto.
   */
  describe('prioridad Media predeterminada (AC-27)', () => {
    it('el selector del modal muestra Media seleccionada y habilitada', () => {
      abrirConCatalogos();

      const select = fixture.nativeElement.querySelector(
        'dialog select[formcontrolname="prioridad_id"]'
      ) as HTMLSelectElement;
      expect(select).not.toBeNull();
      expect(select.disabled).toBe(false);
      expect(select.selectedOptions[0]?.textContent?.trim()).toBe('Media');
    });

    it('cambiarla a Alta se refleja en el POST', () => {
      abrirConCatalogos();
      completarFormulario(); // fija prioridad 1 (Alta)
      componente.enviar();

      const peticion = httpMock.expectOne(RUTA_TICKETS);
      expect(peticion.request.body.prioridad_id).toBe(1);
      peticion.flush(ticketRespuesta(42));
    });

    it('vuelve a Media y a EnRevision después de crear', () => {
      abrirConCatalogos();
      completarFormulario();
      componente.enviar();
      httpMock.expectOne(RUTA_TICKETS).flush(ticketRespuesta(42));

      expect(componente.formulario.controls.prioridad_id.value).toBe(2);
      expect(componente.formulario.controls.estado_id.value).toBe(1);
      expect(componente.formulario.controls.prioridad_id.touched).toBe(false);
    });
  });

  /**
   * Feature 014, D-7/AC-4/AC-9: los selectores de alta no ofrecen productos
   * inactivos. `GET /tickets/catalogos` ya los excluye en servidor; el filtro
   * del componente es la salvaguarda de UI y aquí se hace explícita con un
   * catálogo degenerado que sí los incluyera.
   */
  describe('alta sin productos inactivos (AC-4, AC-9)', () => {
    const CATALOGOS_CON_INACTIVO: CatalogosTicket = {
      ...CATALOGOS_013,
      productos: [
        ...CATALOGOS_013.productos,
        {
          producto_id: 3,
          nombre: 'Guillotina retirada',
          unidad_medida: 'UNIDAD',
          categoria_nombre: 'Papelería',
          stock_total: 0,
          es_critico: false,
          activo: false,
        },
      ],
    };

    it('excluye los productos inactivos del catálogo que consume el alta', () => {
      abrirConCatalogos(CATALOGOS_CON_INACTIVO);

      expect(componente.productos().map((producto) => producto.producto_id)).toEqual([1, 2]);
    });

    it('el selector de producto del modal no ofrece el inactivo', () => {
      abrirConCatalogos(CATALOGOS_CON_INACTIVO);

      const opciones = Array.from(
        fixture.nativeElement.querySelectorAll(
          'dialog select[formcontrolname="producto_id"] option',
        ) as NodeListOf<HTMLOptionElement>,
      );
      // Marcador "Selecciona un producto" + los dos activos.
      expect(opciones.length).toBe(3);
      const textos = opciones.map((opcion) => (opcion.textContent ?? '').trim());
      expect(textos.some((texto) => texto.includes('Guillotina retirada'))).toBe(false);
    });

    it('conserva los productos activos cuando el catálogo no declara el estado', () => {
      // El contrato vigente no envía `activo`: ausente equivale a disponible.
      abrirConCatalogos(CATALOGOS_013);

      expect(componente.productos().length).toBe(CATALOGOS_013.productos.length);
    });
  });

  describe('filtros del tablero', () => {
    /** Todos los tickets que el tablero pinta, aplanando las columnas. */
    function tarjetasVisibles() {
      return componente.columnas().flatMap((columna) => columna.tarjetas);
    }

    beforeEach(() => responderArranque(CATALOGOS, TICKETS_FILTROS));

    it('debe arrancar en "todas" y filtrar por prioridad (AC-6)', () => {
      expect(componente.filtroPrioridad()).toBeNull();
      expect(tarjetasVisibles().length).toBe(TICKETS_FILTROS.length);

      componente.cambiarPrioridad('1');
      fixture.detectChanges();

      expect(componente.filtroPrioridad()).toBe(1);
      const visibles = tarjetasVisibles();
      expect(visibles.length).toBe(3);
      expect(visibles.every((tarjeta) => tarjeta.ticket.prioridad_id === 1)).toBe(true);

      componente.cambiarPrioridad('');
      fixture.detectChanges();

      expect(componente.filtroPrioridad()).toBeNull();
      expect(tarjetasVisibles().length).toBe(TICKETS_FILTROS.length);
    });

    it('debe contar las tarjetas despues de filtrar, no el total cargado (AC-3)', () => {
      componente.cambiarPrioridad('2');
      fixture.detectChanges();

      const columnaRevision = componente
        .columnas()
        .find((c) => c.clave === 'EnRevision')!;
      const columnaCurso = componente
        .columnas()
        .find((c) => c.clave === 'EnCurso')!;

      // Cargados: EnRevision 3 y EnCurso 3. Filtrados por prioridad 2: 2 y 1.
      expect(columnaRevision.tarjetas.length).toBe(2);
      expect(columnaCurso.tarjetas.length).toBe(1);

      const suma = componente
        .columnas()
        .reduce((total, columna) => total + columna.tarjetas.length, 0);
      expect(suma).toBe(3);
      expect(suma).toBeLessThan(TICKETS_FILTROS.length);
    });

    it('debe buscar sin distinguir mayusculas ni acentos (AC-7)', () => {
      componente.busqueda.set('reposicion');
      fixture.detectChanges();
      expect(
        tarjetasVisibles()
          .map((tarjeta) => tarjeta.ticket.ticket_id)
          .sort()
      ).toEqual([1, 5]);

      // Con el acento en la consulta tambien encuentra.
      componente.busqueda.set('REPOSICIÓN');
      fixture.detectChanges();
      expect(
        tarjetasVisibles()
          .map((tarjeta) => tarjeta.ticket.ticket_id)
          .sort()
      ).toEqual([1, 5]);

      componente.busqueda.set('TÓNER');
      fixture.detectChanges();
      expect(
        tarjetasVisibles().map((tarjeta) => tarjeta.ticket.ticket_id)
      ).toEqual([1]);
    });

    it('debe tratar "%" y "_" como texto literal, no comodines (AC-7)', () => {
      componente.busqueda.set('%');
      fixture.detectChanges();
      expect(
        tarjetasVisibles().map((tarjeta) => tarjeta.ticket.ticket_id)
      ).toEqual([3]);

      componente.busqueda.set('_');
      fixture.detectChanges();
      expect(
        tarjetasVisibles().map((tarjeta) => tarjeta.ticket.ticket_id)
      ).toEqual([4]);
    });

    it('debe ignorar una busqueda vacia o de solo espacios (AC-7)', () => {
      componente.busqueda.set('papel');
      fixture.detectChanges();
      expect(tarjetasVisibles().length).toBe(2);

      componente.actualizarBusqueda('   ');
      fixture.detectChanges();

      expect(componente.hayFiltros()).toBe(false);
      expect(tarjetasVisibles().length).toBe(TICKETS_FILTROS.length);
    });

    it('debe combinar prioridad y busqueda en interseccion (AC-7, D-6)', () => {
      componente.busqueda.set('papel');
      fixture.detectChanges();
      // Sin prioridad: el ticket 3 (prioridad 1) y el 6 (prioridad 2).
      expect(
        tarjetasVisibles()
          .map((tarjeta) => tarjeta.ticket.ticket_id)
          .sort()
      ).toEqual([3, 6]);

      componente.filtroPrioridad.set(1);
      fixture.detectChanges();
      expect(
        tarjetasVisibles().map((tarjeta) => tarjeta.ticket.ticket_id)
      ).toEqual([3]);
    });

    it('debe diferenciar el vacio por filtros del vacio normal (AC-5)', () => {
      // Sin filtros: la columna terminal Terminados esta vacia.
      expect(componente.hayFiltros()).toBe(false);
      expect(fixture.nativeElement.textContent).toContain('Sin pedidos en esta columna');

      componente.busqueda.set('zzzz');
      fixture.detectChanges();

      expect(componente.errorTablero()).toBeNull();
      expect(componente.hayFiltros()).toBe(true);
      expect(tarjetasVisibles().length).toBe(0);
      expect(fixture.nativeElement.textContent).toContain(
        'Ningún pedido coincide con los filtros'
      );
    });
  });

  describe('alta reflejada en el tablero', () => {
    /** Busca una tarjeta por el id de su ticket, aplanando las columnas. */
    function tarjetaDe(ticketId: number) {
      return componente
        .columnas()
        .flatMap((columna) => columna.tarjetas)
        .find((tarjeta) => tarjeta.ticket.ticket_id === ticketId);
    }

    /** La columna que agrupa un estado del catálogo. */
    function columna(estadoId: number) {
      return componente
        .columnas()
        .find((c) => c.estado_ids.includes(estadoId))!;
    }

    it('el ticket creado aparece en el tablero sin recargar', () => {
      abrirConCatalogos();

      completarFormulario();
      componente.enviar();

      httpMock.expectOne(RUTA_TICKETS).flush(ticketRespuesta(42));
      fixture.detectChanges();

      expect(componente.ticketCreado()).toBe(42);
      expect(componente.tickets().some((t) => t.ticket_id === 42)).toBe(true);
      expect(tarjetaDe(42)).toBeTruthy();
      expect(columna(1).tarjetas.some((t) => t.ticket.ticket_id === 42)).toBe(true);
      // Sin reconsulta: el alta se refleja con la respuesta del POST.
      httpMock.expectNone(RUTA_TICKETS);
    });

    it('la tarjeta del pedido recién creado muestra «En revisión» (T31)', () => {
      // El backend ya publica el read model en el `201` (corrección T31): la
      // tarjeta insertada no puede caer al nombre canónico hasta recargar.
      abrirConCatalogos();

      completarFormulario();
      componente.enviar();

      httpMock.expectOne(RUTA_TICKETS).flush(ticketRespuestaConReadModel(42));
      fixture.detectChanges();

      const tarjeta = tarjetaDe(42)!;
      expect(tarjeta.estadoCanonico).toBe('EnRevision');
      expect(tarjeta.etiquetaProceso).toBe('En revisión');
      expect(tarjeta.etiquetaProceso).not.toBe(tarjeta.estadoCanonico);
      expect(tarjeta.descripcionAccesible).toContain(
        'Etapa del proceso: En revisión'
      );
      expect(fixture.nativeElement.textContent).toContain('En revisión');
      // Sigue sin reconsultar el listado.
      httpMock.expectNone(RUTA_TICKETS);
    });

    it('el ticket creado no aparece si los filtros no lo admiten (D-6)', () => {
      abrirConCatalogos();

      componente.cambiarPrioridad('2');
      fixture.detectChanges();

      completarFormulario();
      componente.enviar();

      httpMock.expectOne(RUTA_TICKETS).flush(ticketRespuesta(42, 1));
      fixture.detectChanges();

      // Esta cargado en el conjunto...
      expect(componente.tickets().some((t) => t.ticket_id === 42)).toBe(true);
      // ...pero el filtro de prioridad 2 lo excluye de todas las columnas.
      expect(tarjetaDe(42)).toBeUndefined();
      expect(
        componente.columnas().some((columna) =>
          columna.tarjetas.some((t) => t.ticket.ticket_id === 42)
        )
      ).toBe(false);
    });
  });

  describe('periodo y orden del tablero (AC-28…AC-30)', () => {
    beforeEach(() => {
      jasmine.clock().install();
      jasmine.clock().mockDate(AHORA_TABLERO);
    });

    afterEach(() => {
      jasmine.clock().uninstall();
    });

    function tarjetasVisibles() {
      return componente.columnas().flatMap((columna) => columna.tarjetas);
    }

    function idsVisibles(): number[] {
      return tarjetasVisibles().map((tarjeta) => tarjeta.ticket.ticket_id);
    }

    function idsDe(clave: string): number[] {
      return (
        componente
          .columnas()
          .find((columna) => columna.clave === clave)
          ?.tarjetas.map((tarjeta) => tarjeta.ticket.ticket_id) ?? []
      );
    }

    function selectorPeriodo(): HTMLSelectElement {
      return fixture.nativeElement.querySelector(
        '[data-testid="filtro-periodo"]'
      ) as HTMLSelectElement;
    }

    function selectorOrden(): HTMLSelectElement {
      return fixture.nativeElement.querySelector(
        '[data-testid="filtro-orden"]'
      ) as HTMLSelectElement;
    }

    function cargarPeriodo() {
      responderArranque(CATALOGOS_RETIRO, TICKETS_PERIODO);
    }

    function cambiarPeriodo(periodo: PeriodoTablero) {
      componente.cambiarPeriodo(periodo);
      fixture.detectChanges();
    }

    function cambiarOrden(orden: OrdenTablero) {
      componente.cambiarOrden(orden);
      fixture.detectChanges();
    }

    it('inicioDePeriodo devuelve la medianoche local y el lunes de la semana', () => {
      cargarPeriodo();

      expect(inicioDePeriodo('todo', AHORA_TABLERO)).toBeNull();
      expect(inicioDePeriodo('hoy', AHORA_TABLERO)).toEqual(new Date(2026, 10, 28));
      expect(inicioDePeriodo('semana', AHORA_TABLERO)).toEqual(new Date(2026, 10, 23));
      expect(inicioDePeriodo('mes', AHORA_TABLERO)).toEqual(new Date(2026, 10, 1));
      expect(inicioDePeriodo('anio', AHORA_TABLERO)).toEqual(new Date(2026, 0, 1));
    });

    it('inicioDePeriodo lleva el domingo y el cruce de mes al lunes anterior', () => {
      cargarPeriodo();

      expect(inicioDePeriodo('semana', new Date(2026, 10, 29, 12, 0, 0))).toEqual(
        new Date(2026, 10, 23)
      );
      expect(inicioDePeriodo('semana', new Date(2026, 11, 1, 12, 0, 0))).toEqual(
        new Date(2026, 10, 30)
      );
    });

    it('debe arrancar en «Todo el tiempo» y no recortar el conjunto (AC-28)', () => {
      cargarPeriodo();

      expect(componente.filtroPeriodo()).toBe('todo');
      expect(idsVisibles().length).toBe(5);
      expect(selectorPeriodo().value).toBe('todo');
    });

    it('debe recortar por el inicio local de hoy, semana, mes y año (AC-28)', () => {
      cargarPeriodo();

      const casos: Array<[PeriodoTablero, number[]]> = [
        ['hoy', [101]],
        ['semana', [101, 102]],
        ['mes', [101, 102, 103]],
        ['anio', [101, 102, 103, 104]],
      ];

      for (const [periodo, esperados] of casos) {
        cambiarPeriodo(periodo);
        expect(idsVisibles().sort((a, b) => a - b))
          .withContext(periodo)
          .toEqual(esperados);
      }
    });

    it('debe incluir el borde exacto y excluir el milisegundo anterior (AC-28)', () => {
      const bordeHoy = new Date(2026, 10, 28);
      const bordeSemana = new Date(2026, 10, 23);
      const bordeMes = new Date(2026, 10, 1);
      const bordeAnio = new Date(2026, 0, 1);
      const tickets = [
        ticketPeriodo(301, 1, fechaIsoLocal(bordeHoy), 1, 'Hoy borde'),
        ticketPeriodo(
          302,
          1,
          fechaIsoLocal(new Date(bordeHoy.getTime() - 1)),
          1,
          'Hoy anterior'
        ),
        ticketPeriodo(303, 1, fechaIsoLocal(bordeSemana), 1, 'Semana borde'),
        ticketPeriodo(
          304,
          1,
          fechaIsoLocal(new Date(bordeSemana.getTime() - 1)),
          1,
          'Semana anterior'
        ),
        ticketPeriodo(305, 1, fechaIsoLocal(bordeMes), 1, 'Mes borde'),
        ticketPeriodo(
          306,
          1,
          fechaIsoLocal(new Date(bordeMes.getTime() - 1)),
          1,
          'Mes anterior'
        ),
        ticketPeriodo(307, 1, fechaIsoLocal(bordeAnio), 1, 'Año borde'),
        ticketPeriodo(
          308,
          1,
          fechaIsoLocal(new Date(bordeAnio.getTime() - 1)),
          1,
          'Año anterior'
        ),
      ];
      responderArranque(CATALOGOS_RETIRO, tickets);

      const pares: Array<[PeriodoTablero, number, number]> = [
        ['hoy', 301, 302],
        ['semana', 303, 304],
        ['mes', 305, 306],
        ['anio', 307, 308],
      ];

      for (const [periodo, exacto, anterior] of pares) {
        cambiarPeriodo(periodo);
        const ids = idsVisibles();
        expect(ids).withContext(`${periodo}: borde exacto`).toContain(exacto);
        expect(ids).withContext(`${periodo}: milisegundo anterior`).not.toContain(
          anterior
        );
      }
    });

    it('no debe aplicar cota superior al periodo (AC-28)', () => {
      const futuro = ticketPeriodo(
        401,
        1,
        fechaIsoLocal(new Date(2026, 11, 15, 12)),
        1,
        'Pedido futuro'
      );
      const hoy = ticketPeriodo(402, 1, fechaHaceDias(0), 1, 'Pedido de hoy');
      responderArranque(CATALOGOS_RETIRO, [futuro, hoy]);

      cambiarPeriodo('hoy');

      expect(idsVisibles().sort((a, b) => a - b)).toEqual([401, 402]);
    });

    it('no debe recortar por fecha_cierre (AC-28)', () => {
      cargarPeriodo();

      cambiarPeriodo('mes');

      expect(idsVisibles()).not.toContain(104);
      expect(
        componente.tickets().find((ticket) => ticket.ticket_id === 104)?.fecha_cierre
      ).not.toBeNull();
    });

    it('el selector de periodo declara label, valores estables y estilos Tailwind (AC-28)', () => {
      cargarPeriodo();
      const select = selectorPeriodo();
      const label = select.closest('label');

      expect(label?.textContent).toContain('Periodo');
      expect(select.value).toBe('todo');
      expect(Array.from(select.options).map((opcion) => opcion.value)).toEqual([
        'todo',
        'hoy',
        'semana',
        'mes',
        'anio',
      ]);
      expect(
        Array.from(select.options).map((opcion) => opcion.textContent?.trim())
      ).toEqual(['Todo el tiempo', 'Hoy', 'Esta semana', 'Este mes', 'Este año']);
      expect(select.className).toContain('border');
      expect(select.className).toContain('rounded-lg');
      expect(select.getAttribute('style')).toBeNull();
      expect(select.id).toBe('filtro-periodo');
      expect(select.name).toBe('periodo');
      expect(label?.getAttribute('for')).toBe('filtro-periodo');
    });

    it('debe ordenar «Más recientes» por defecto con desempate por ticket_id DESC (AC-29)', () => {
      cargarPeriodo();

      expect(componente.orden()).toBe('recientes');
      expect(selectorOrden().value).toBe('recientes');
      expect(idsDe('EnRevision')).toEqual([101, 103]);
      expect(idsDe('Terminados')).toEqual([104, 105]);
    });

    it('debe ordenar «Más antiguos» con desempate por ticket_id ASC dentro de cada columna (AC-29)', () => {
      responderArranque(CATALOGOS_RETIRO, TICKETS_ORDEN);

      expect(idsDe('EnRevision')).toEqual([202, 201]);
      expect(idsDe('Terminados')).toEqual([204, 203]);

      cambiarOrden('antiguos');

      expect(idsDe('EnRevision')).toEqual([201, 202]);
      expect(idsDe('Terminados')).toEqual([203, 204]);
    });

    it('el orden también aplica en Terminados y no altera contadores ni vacío (AC-29)', () => {
      cargarPeriodo();
      cambiarPeriodo('hoy');
      const conteos = componente.columnas().map((columna) => columna.tarjetas.length);

      expect(conteos).toEqual([1, 0, 0]);
      expect(componente.hayFiltros()).toBe(true);
      expect(fixture.nativeElement.textContent).toContain(
        'Ningún pedido coincide con los filtros'
      );

      cambiarOrden('antiguos');

      expect(componente.columnas().map((columna) => columna.tarjetas.length)).toEqual(
        conteos
      );
      expect(componente.hayFiltros()).toBe(true);
      expect(fixture.nativeElement.textContent).toContain(
        'Ningún pedido coincide con los filtros'
      );
      httpMock.expectNone(RUTA_TICKETS);
    });

    it('el selector de orden declara label, valores estables y estilos Tailwind (AC-29)', () => {
      cargarPeriodo();
      const select = selectorOrden();
      const label = select.closest('label');

      expect(label?.textContent).toContain('Orden');
      expect(select.value).toBe('recientes');
      expect(Array.from(select.options).map((opcion) => opcion.value)).toEqual([
        'recientes',
        'antiguos',
      ]);
      expect(
        Array.from(select.options).map((opcion) => opcion.textContent?.trim())
      ).toEqual(['Más recientes', 'Más antiguos']);
      expect(select.className).toContain('border');
      expect(select.getAttribute('style')).toBeNull();
      expect(select.id).toBe('filtro-orden');
      expect(select.name).toBe('orden');
      expect(label?.getAttribute('for')).toBe('filtro-orden');
    });

    it('debe combinar periodo, prioridad y búsqueda en intersección antes de agrupar (AC-30)', () => {
      cargarPeriodo();

      componente.filtroPeriodo.set('mes');
      componente.filtroPrioridad.set(2);
      componente.busqueda.set('semana');
      fixture.detectChanges();

      expect(idsVisibles()).toEqual([102]);
    });

    it('los contadores y el vacío reflejan el conjunto filtrado con periodo activo (AC-30)', () => {
      cargarPeriodo();
      cambiarPeriodo('hoy');

      expect(componente.columnas().map((columna) => columna.tarjetas.length)).toEqual([
        1, 0, 0,
      ]);
      expect(componente.hayFiltros()).toBe(true);
      expect(fixture.nativeElement.textContent).toContain(
        'Ningún pedido coincide con los filtros'
      );
      expect(fixture.nativeElement.textContent).not.toContain(
        'Sin pedidos en esta columna'
      );
    });

    it('el pedido recién creado cae en cualquier periodo vigente y respeta prioridad, búsqueda y orden (AC-30)', () => {
      responderArranque(CATALOGOS_RETIRO, TICKETS_PERIODO);
      componente.abrirModal();
      fixture.detectChanges();
      componente.filtroPeriodo.set('hoy');
      componente.filtroPrioridad.set(1);
      componente.busqueda.set('papel');
      componente.orden.set('antiguos');
      fixture.detectChanges();

      completarFormulario();
      componente.enviar();
      const nuevo: Ticket = {
        ...ticketRespuestaConReadModel(42),
        fecha_creacion: fechaIsoLocal(AHORA_TABLERO),
        asunto: 'Falta de papel',
      };
      httpMock.expectOne(RUTA_TICKETS).flush(nuevo);
      fixture.detectChanges();

      for (const periodo of ['hoy', 'semana', 'mes', 'anio', 'todo'] as PeriodoTablero[]) {
        componente.filtroPeriodo.set(periodo);
        fixture.detectChanges();
        expect(idsVisibles()).withContext(periodo).toContain(42);
      }

      componente.filtroPeriodo.set('hoy');
      componente.busqueda.set('');
      componente.orden.set('antiguos');
      fixture.detectChanges();
      expect(idsDe('EnRevision')).toEqual([101, 42]);

      componente.orden.set('recientes');
      fixture.detectChanges();
      expect(idsDe('EnRevision')).toEqual([42, 101]);

      componente.filtroPrioridad.set(2);
      fixture.detectChanges();
      expect(idsVisibles()).not.toContain(42);

      componente.filtroPrioridad.set(1);
      componente.busqueda.set('zzzz');
      fixture.detectChanges();
      expect(idsVisibles()).not.toContain(42);
      httpMock.expectNone(RUTA_TICKETS);
    });

    it('sin persistencia: al remontar vuelven «Todo el tiempo» y «Más recientes» (AC-30)', () => {
      responderArranque(CATALOGOS_RETIRO, TICKETS_PERIODO);
      componente.filtroPeriodo.set('hoy');
      componente.orden.set('antiguos');

      const otro = TestBed.createComponent(TicketsComponent);
      const otroComponente = otro.componentInstance;
      otro.detectChanges();
      httpMock.expectOne(RUTA_CATALOGOS).flush(CATALOGOS_RETIRO);
      httpMock.expectOne(RUTA_TICKETS).flush(TICKETS_PERIODO);
      otro.detectChanges();

      expect(otroComponente.filtroPeriodo()).toBe('todo');
      expect(otroComponente.orden()).toBe('recientes');
    });
  });

  /**
   * AC-34 (enmienda 22/Oct/2026): el autor del ticket es un dato informativo
   * de la identidad de sesión, no una elección. Sin selector, sin control
   * editable y sin llamada adicional: todo sale de `AutenticacionService`.
   */
  describe('autor informativo de la sesión (AC-34)', () => {
    beforeEach(() => abrirConCatalogos());

    function bloqueAutor(): HTMLElement | null {
      return fixture.nativeElement.querySelector('dialog dl');
    }

    it('muestra nombre, apellido y correo de la identidad, sin departamento', () => {
      const bloque = bloqueAutor();
      expect(bloque).not.toBeNull();

      const texto = bloque!.textContent ?? '';
      expect(texto).toContain('Isabel');
      expect(texto).toContain('Contreras');
      expect(texto).toContain('isabel.contreras@losalpes.cl');
      // El bloque autor no presenta el departamento ni lo consulta por separado;
      // el servidor lo deriva al crear el ticket (Feature 008, AC-22).
      expect(texto).not.toContain('Docencia');
      expect(texto).not.toContain('Departamento');
    });

    it('refleja la identidad vigente sin selector ni control editable', () => {
      identidad.set({
        ...crearIdentidad(7),
        nombre: 'Bruno',
        apellido: 'Soto',
        correo: 'bruno.soto@losalpes.cl',
      });
      fixture.detectChanges();

      const texto = bloqueAutor()!.textContent ?? '';
      expect(texto).toContain('Bruno');
      expect(texto).toContain('Soto');

      // Ni `<select>` ni ningún control de formulario llamado `usuario_id`.
      expect(
        fixture.nativeElement.querySelector('dialog select[formcontrolname="usuario_id"]')
      ).toBeNull();
      expect(
        fixture.nativeElement.querySelector('dialog [formcontrolname="usuario_id"]')
      ).toBeNull();
      expect('usuario_id' in componente.formulario.controls).toBe(false);
    });

    it('no hace ninguna llamada adicional para presentar la identidad', () => {
      // `abrirConCatalogos` ya consumió catálogos y lista del arranque: el
      // campo informativo no pide `/usuarios/` ni repite `/auth/me`.
      componente.abrirModal();
      fixture.detectChanges();

      expect(httpMock.match(() => true).length).toBe(0);
      expect(
        httpMock.match((peticion) => peticion.url.includes('/usuarios')).length
      ).toBe(0);
    });

    it('sin identidad disponible no inventa un autor ni un control', () => {
      identidad.set(null);
      fixture.detectChanges();

      const texto = bloqueAutor()!.textContent ?? '';
      expect(texto).toContain('No se pudo cargar tu identidad');
      expect(
        fixture.nativeElement.querySelector('dialog [formcontrolname="usuario_id"]')
      ).toBeNull();
    });
  });

  /**
   * AC-19: la vista de una institución presenta exactamente el catálogo, el
   * stock y los tickets que el servidor devolvió para su ámbito. El servidor ya
   * aísla (T7); el cliente no agrega ni recombina datos de otra institución, y
   * tampoco elige el ámbito: no lo envía.
   */
  describe('aislamiento institucional en la vista (AC-19)', () => {
    /** Catálogo de INST-A: homónimo con id y stock propios, sin nada de INST-B. */
    const CATALOGOS_A: CatalogosTicket = {
      ...CATALOGOS,
      productos: [
        {
          producto_id: 101,
          nombre: 'Resma Carta 75g',
          unidad_medida: 'RESMA',
          categoria_nombre: 'Papeleria',
          stock_total: 120,
          es_critico: false,
        },
      ],
    };

    /** Tickets de INST-A: solo su ámbito, sin tickets de INST-B. */
    const TICKETS_A: Ticket[] = [
      {
        ticket_id: 301,
        usuario_id: 5,
        prioridad_id: 1,
        estado_id: 1,
        asunto: 'Reposición de resma (INST-A)',
        descripcion: null,
        fecha_creacion: '2026-10-01T10:00:00',
        fecha_cierre: null,
        detalles: [],
      },
    ];

    function tarjetasVisibles() {
      return componente.columnas().flatMap((columna) => columna.tarjetas);
    }

    it('presenta solo el catálogo, el stock y los tickets del ámbito recibido', () => {
      responderArranque(CATALOGOS_A, TICKETS_A);

      expect(componente.tickets()).toEqual(TICKETS_A);
      expect(componente.productos()).toEqual(CATALOGOS_A.productos);
      // El stock mostrado es el de INST-A (120), no el de un homónimo de INST-B.
      expect(componente.productos()[0].stock_total).toBe(120);

      const texto = fixture.nativeElement.textContent ?? '';
      expect(texto).toContain('INST-A');
      // Ningún dato de INST-B aparece, ni tickets ni productos homónimos.
      expect(texto).not.toContain('INST-B');
      expect(tarjetasVisibles().map((tarjeta) => tarjeta.ticket.ticket_id)).toEqual([301]);
    });

    it('no pide institución ni parámetros de ámbito: el filtro es del servidor', () => {
      const peticiones = {
        catalogos: httpMock.expectOne(RUTA_CATALOGOS),
        tickets: httpMock.expectOne(RUTA_TICKETS),
      };
      peticiones.catalogos.flush(CATALOGOS_A);
      peticiones.tickets.flush(TICKETS_A);
      fixture.detectChanges();

      for (const peticion of [peticiones.catalogos, peticiones.tickets]) {
        expect(peticion.request.method).toBe('GET');
        expect(peticion.request.params.has('institucion_id')).toBe(false);
        expect(peticion.request.headers.get('X-Institucion-Id')).toBeNull();
      }
    });

    it('el alta de ticket no reenvía la institución como autorización', () => {
      abrirConCatalogos(CATALOGOS_A);

      completarFormulario();
      componente.enviar();

      const peticion = httpMock.expectOne(RUTA_TICKETS);
      expect(peticion.request.method).toBe('POST');
      const cuerpo = peticion.request.body as Record<string, unknown>;
      expect('institucion_id' in cuerpo).toBe(false);
      expect('usuario_id' in cuerpo).toBe(false);

      peticion.flush(ticketRespuesta(500));
    });
  });

  /**
   * Enmienda de la 007 (26/Nov/2026): solo el Solicitante crea tickets, así
   * que el botón de alta se oculta a Administrador, Bodeguero y Superadmin.
   * La API es la frontera y responde 403 a esos roles.
   */
  describe('alta de pedidos por rol (enmienda 007, 26/Nov/2026)', () => {
    function botonCrearPedido(): HTMLButtonElement | null {
      const botones = Array.from(
        fixture.nativeElement.querySelectorAll(
          'button'
        ) as NodeListOf<HTMLButtonElement>
      );
      return (
        botones.find(
          (boton) =>
            !boton.closest('dialog') &&
            (boton.textContent ?? '').includes('Crear pedido')
        ) ?? null
      );
    }

    it('el Solicitante ve el botón de alta y abre el modal', () => {
      responderArranque();

      const boton = botonCrearPedido();
      expect(boton).not.toBeNull();

      boton!.click();
      fixture.detectChanges();
      expect(componente.modalAbierto()).toBe(true);
    });

    it('el Administrador no ve el botón de alta', () => {
      identidad.set({ ...crearIdentidad(), rol: 'Administrador' });
      responderArranque();

      expect(botonCrearPedido()).toBeNull();
      expect(componente.modalAbierto()).toBe(false);
    });

    it('el Bodeguero no ve el botón de alta', () => {
      identidad.set({ ...crearIdentidad(), rol: 'Bodeguero' });
      responderArranque();

      expect(botonCrearPedido()).toBeNull();
      expect(componente.modalAbierto()).toBe(false);
    });
  });

  /**
   * Enmienda 26/Nov/2026 (D-35/AC-51/AC-62): con el catálogo de cuatro estados
   * el tablero queda en tres columnas —`EnRevision`, `EnCurso` y «Terminados»— y
   * el alta nace en `EnRevision` resuelto por nombre. La copia del read model
   * pasa de «Despachado» a «Retirado».
   */
  describe('enmienda 26/Nov/2026: tres columnas y alta en EnRevision', () => {
    const TICKETS_RETIRO: Ticket[] = [
      ticketRetiro(1, 1, 'En revisión'),
      ticketRetiro(2, 2, 'En preparación para el retiro'),
      ticketRetiro(3, 3, 'Retirado'),
      ticketRetiro(4, 4, 'Rechazado'),
    ];

    it('muestra exactamente las tres columnas del catálogo nuevo (AC-62)', () => {
      responderArranque(CATALOGOS_RETIRO, TICKETS_RETIRO);

      const columnas = componente.columnas();
      expect(columnas.map((columna) => columna.clave)).toEqual([
        'EnRevision',
        'EnCurso',
        'Terminados',
      ]);
      expect(columnas.map((columna) => columna.etiqueta)).toEqual([
        'En Revisión',
        'En Curso',
        'Terminados',
      ]);
      expect(
        columnas.some((columna) => columna.estado === 'Pendiente'),
      ).toBe(false);
      expect(
        columnas.some((columna) => columna.estado === 'Anulado'),
      ).toBe(false);

      const terminados = columnas[2];
      expect(terminados.estado_ids).toEqual([3, 4]);
      expect(
        terminados.tarjetas
          .map((tarjeta) => tarjeta.ticket.ticket_id)
          .sort(),
      ).toEqual([3, 4]);
      expect(columnas.map((columna) => columna.tarjetas.length)).toEqual([
        1, 1, 2,
      ]);
    });

    it('el alta nace en EnRevision y ya no depende de Pendiente (AC-51)', () => {
      responderArranque(CATALOGOS_RETIRO, []);
      componente.abrirModal();
      fixture.detectChanges();

      expect(componente.estadoInicial()).toBe(1);
      expect(componente.nombreEstadoInicial()).toBe('En Revisión');
      expect(componente.formulario.controls.estado_id.value).toBe(1);

      const api = componente as unknown as Record<string, unknown>;
      expect(api['estadoEnRevision']).toBeDefined();
      expect(api['estadoPendiente']).toBeUndefined();
    });

    it('envía siempre el EnRevision resuelto por nombre y sin selector (AC-51)', () => {
      responderArranque(CATALOGOS_RETIRO, []);
      componente.abrirModal();
      fixture.detectChanges();

      expect(
        fixture.nativeElement.querySelector(
          'dialog select[formcontrolname="estado_id"]',
        ),
      ).toBeNull();

      completarFormulario();
      componente.enviar();

      const peticion = httpMock.expectOne(RUTA_TICKETS);
      expect(peticion.request.method).toBe('POST');
      expect(peticion.request.body.estado_id).toBe(1);
      peticion.flush(ticketRespuesta(42, 1));
    });

    it('la tarjeta muestra Retirado y Rechazado desde el read model (AC-63)', () => {
      responderArranque(CATALOGOS_RETIRO, TICKETS_RETIRO);

      const texto = (fixture.nativeElement.textContent ?? '').replace(
        /\s+/g,
        ' ',
      );
      expect(texto).toContain('Retirado');
      expect(texto).toContain('Rechazado');
      expect(texto).not.toContain('Despachado');
    });
  });
});
