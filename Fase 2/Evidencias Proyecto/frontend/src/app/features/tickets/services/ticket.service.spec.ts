import { provideHttpClient } from '@angular/common/http';
import {
  HttpTestingController,
  TestRequest,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { URL_API } from '../../../shared/config/url-api';
import { Ticket } from '../../../shared/interfaces';
import { TicketService } from './ticket.service';

const TICKET_APROBADO: Ticket = {
  ticket_id: 10,
  usuario_id: 5,
  prioridad_id: 2,
  estado_id: 3,
  asunto: 'Falta de papel confort',
  descripcion: 'Tres unidades para la Sede Maipú.',
  fecha_creacion: '2026-11-25T09:00:00',
  fecha_cierre: null,
  detalles: [
    {
      detalle_ticket_id: 1,
      producto_id: 7,
      cantidad_solicitada: 3,
      cantidad_entregada: 0,
      producto: null,
    },
  ],
  etiqueta_proceso: 'En confirmación de stock local',
  explicacion_proceso:
    'En confirmación de stock local: el stock local está disponible; falta que el Bodeguero lo confirme y despache.',
  estado_orden_cobertura: null,
  stock_disponible: true,
  entrega_confirmada: false,
  gestionado_por_bodeguero: null,
  gestionado_por_administrador: {
    usuario_id: 2,
    nombre: 'Cristian',
    apellido: 'González',
  },
};

const TICKET_RETIRADO: Ticket = {
  ...TICKET_APROBADO,
  estado_id: 4,
  fecha_cierre: '2026-11-25T10:00:00',
  etiqueta_proceso: 'Retirado',
  explicacion_proceso: 'Retirado: pendiente de confirmación de entrega.',
  stock_disponible: false,
};

const TICKET_ENTREGADO: Ticket = {
  ...TICKET_RETIRADO,
  etiqueta_proceso: 'Entregado',
  explicacion_proceso: 'Entregado: confirmado por el solicitante.',
  entrega_confirmada: true,
};

/**
 * Contrato HTTP de la ampliación del 25/Nov/2026 (spec §9, T25).
 *
 * Cubre las tres mutaciones del flujo: aprobación, retiro y confirmación de
 * entrega. Las aserciones comparan ruta, verbo y cuerpo; no prueban la lógica
 * del servidor, solo que el cliente hable el contrato. La enmienda 26/Nov/2026
 * sustituye `despacharTicket`/`/despacho` por `registrarRetiro`/`/retiro`.
 */
describe('TicketService (ampliación 013, §9)', () => {
  let servicio: TicketService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    servicio = TestBed.inject(TicketService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  /** Selecciona por ruta sin query: `expectOne(string)` exige la URL exacta. */
  function peticionA(ruta: string): TestRequest {
    return httpMock.expectOne((peticion) => peticion.url === ruta);
  }

  it('aprobarTicket hace POST sin cuerpo a /tickets/{id}/aprobacion', () => {
    const recibidos: Ticket[] = [];
    servicio
      .aprobarTicket(10)
      .subscribe((ticket) => recibidos.push(ticket));

    const peticion = peticionA(`${URL_API}/tickets/10/aprobacion`);
    expect(peticion.request.method).toBe('POST');
    expect(peticion.request.body).toBeNull();
    peticion.flush(TICKET_APROBADO);

    expect(recibidos).toEqual([TICKET_APROBADO]);
  });

  /**
   * Enmienda 26/Nov/2026 (D-29/AC-55/AC-63): el método vigente es
   * `registrarRetiro` y llama a `/retiro`. La llamada es estática desde T39;
   * el nombre histórico solo se consulta por acceso dinámico para probar su
   * ausencia.
   */
  it('registrarRetiro hace POST con el usuario_id de la sesión a /tickets/{id}/retiro', () => {
    const recibidos: Ticket[] = [];
    servicio.registrarRetiro(10, 7).subscribe({
      next: (ticket) => recibidos.push(ticket),
    });

    const peticion = peticionA(`${URL_API}/tickets/10/retiro`);
    expect(peticion.request.method).toBe('POST');
    expect(peticion.request.body).toEqual({ usuario_id: 7 });
    peticion.flush(TICKET_RETIRADO);

    expect(recibidos).toEqual([TICKET_RETIRADO]);
  });

  it('ya no expone despacharTicket ni llama a /despacho (D-29)', () => {
    const api = servicio as unknown as Record<string, unknown>;

    expect(api['despacharTicket']).toBeUndefined();
    expect(api['registrarRetiro']).toBeDefined();
  });

  it('confirmarEntrega hace POST sin cuerpo a /tickets/{id}/confirmacion-entrega', () => {
    const recibidos: Ticket[] = [];
    servicio
      .confirmarEntrega(10)
      .subscribe((ticket) => recibidos.push(ticket));

    const peticion = peticionA(`${URL_API}/tickets/10/confirmacion-entrega`);
    expect(peticion.request.method).toBe('POST');
    expect(peticion.request.body).toBeNull();
    peticion.flush(TICKET_ENTREGADO);

    expect(recibidos).toEqual([TICKET_ENTREGADO]);
  });

  /**
   * AC-48: la vista no invoca el `PATCH /estado` de legado. El método se retiró
   * del servicio en la tarea T26; esta aserción impide reintroducirlo sin
   * contrato de interfaz.
   */
  it('ya no expone actualizarEstado: el detalle no usa PATCH /estado', () => {
    expect(
      (servicio as unknown as Record<string, unknown>)['actualizarEstado'],
    ).toBeUndefined();
  });
});
