import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import {
  CatalogosTicket,
  HistorialTransicion,
  Ticket,
  TicketCrear,
  TicketDetalle,
  TicketEditar,
} from '../../../shared/interfaces';
import { URL_API } from '../../../shared/config/url-api';

/** HTTP del flujo de tickets. */
@Injectable({ providedIn: 'root' })
export class TicketService {
  private readonly http = inject(HttpClient);

  obtenerCatalogos(): Observable<CatalogosTicket> {
    return this.http.get<CatalogosTicket>(`${URL_API}/tickets/catalogos`);
  }

  obtenerTickets(estadoId?: number): Observable<Ticket[]> {
    let params = new HttpParams();
    if (estadoId !== undefined) {
      params = params.set('estado_id', estadoId);
    }
    return this.http.get<Ticket[]>(`${URL_API}/tickets/`, { params });
  }

  crearTicket(datos: TicketCrear): Observable<Ticket> {
    return this.http.post<Ticket>(`${URL_API}/tickets/`, datos);
  }

  /**
   * Aprobación del Administrador (Feature 013, ampliación 25/Nov/2026, D-15):
   * `POST /tickets/{id}/aprobacion` sin cuerpo. El destino es siempre
   * `EnCurso`; el stock solo decide la etiqueta de proceso.
   */
  aprobarTicket(ticketId: number): Observable<Ticket> {
    return this.http.post<Ticket>(
      `${URL_API}/tickets/${ticketId}/aprobacion`,
      null,
    );
  }

  /**
   * Despacho de un pedido `EnCurso` (Feature 005, reutilizado en el detalle por
   * D-19): `POST /tickets/{id}/despacho` con el `usuario_id` de la sesión.
   */
  despacharTicket(ticketId: number, usuarioId: number): Observable<Ticket> {
    return this.http.post<Ticket>(`${URL_API}/tickets/${ticketId}/despacho`, {
      usuario_id: usuarioId,
    });
  }

  /**
   * Confirmación de entrega del Solicitante dueño (ampliación 25/Nov/2026,
   * D-25): `POST /tickets/{id}/confirmacion-entrega` sin cuerpo. No cambia el
   * estado canónico `Cerrado`; solo registra el evento.
   */
  confirmarEntrega(ticketId: number): Observable<Ticket> {
    return this.http.post<Ticket>(
      `${URL_API}/tickets/${ticketId}/confirmacion-entrega`,
      null,
    );
  }

  /** Detalle completo del ticket (Feature 013, spec §6, AC-23). */
  obtenerDetalleTicket(ticketId: number): Observable<TicketDetalle> {
    return this.http.get<TicketDetalle>(`${URL_API}/tickets/${ticketId}`);
  }

  /** Historial de transiciones, más reciente primero (spec §6, AC-10). */
  obtenerHistorial(ticketId: number): Observable<HistorialTransicion[]> {
    return this.http.get<HistorialTransicion[]>(
      `${URL_API}/tickets/${ticketId}/historial`,
    );
  }

  /** Anulación con motivo obligatorio (spec §6; el 422 lo resuelve el backend). */
  anularTicket(ticketId: number, motivo: string): Observable<TicketDetalle> {
    return this.http.post<TicketDetalle>(`${URL_API}/tickets/${ticketId}/anulacion`, {
      motivo,
    });
  }

  /** Rechazo con motivo obligatorio (spec §6; actores: Bodeguero/Administrador). */
  rechazarTicket(ticketId: number, motivo: string): Observable<TicketDetalle> {
    return this.http.post<TicketDetalle>(`${URL_API}/tickets/${ticketId}/rechazo`, {
      motivo,
    });
  }

  /** Edición en `Pendiente` con reemplazo atómico del conjunto de ítems (D-9). */
  editarTicket(ticketId: number, datos: TicketEditar): Observable<TicketDetalle> {
    return this.http.put<TicketDetalle>(`${URL_API}/tickets/${ticketId}`, datos);
  }
}