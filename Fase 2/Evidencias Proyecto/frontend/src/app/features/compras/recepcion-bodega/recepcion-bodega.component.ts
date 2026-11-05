import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  OnInit,
  inject,
  signal,
} from '@angular/core';

import { OrdenCompra, TicketDesbloqueado } from '../../../shared/interfaces';
import { mensajeDeErrorCompras } from '../compras-errores';
import { ComprasService } from '../services/compras.service';

/**
 * Panel de recepción física del Bodeguero (Feature 020, AC-6…AC-11; T9).
 *
 * Muestra únicamente las OC `Facturada` de la sede del Bodeguero: el servidor
 * fuerza ese ámbito (ignora cualquier filtro) y responde 409 si el Bodeguero no
 * tiene sede. Confirmar la llegada es todo-o-nada y sin cantidades: el backend
 * usa `detalle_orden_compra`, incrementa `stock_sede`, audita el `ENTRADA` y
 * desbloquea los tickets cubiertos (AC-8/AC-9/AC-10). La vista no recalcula
 * nada: presenta el resultado y retira la OC ya recepcionada del panel.
 */
@Component({
  selector: 'app-compras-recepcion-bodega',
  standalone: true,
  imports: [DatePipe],
  templateUrl: './recepcion-bodega.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class RecepcionBodegaComponent implements OnInit {
  private readonly compras = inject(ComprasService);

  readonly cargando = signal(true);
  readonly ordenes = signal<OrdenCompra[]>([]);
  readonly mensajeError = signal<string | null>(null);
  readonly mensajeExito = signal<string | null>(null);
  readonly errorAccion = signal<string | null>(null);
  readonly confirmando = signal<OrdenCompra | null>(null);
  readonly procesando = signal(false);
  readonly ticketsDesbloqueados = signal<TicketDesbloqueado[]>([]);

  ngOnInit(): void {
    this.cargar();
  }

  reintentar(): void {
    this.cargar();
  }

  solicitarRecepcion(orden: OrdenCompra): void {
    this.mensajeExito.set(null);
    this.errorAccion.set(null);
    this.confirmando.set(orden);
  }

  cancelarRecepcion(): void {
    this.confirmando.set(null);
  }

  confirmarRecepcion(): void {
    const orden = this.confirmando();
    if (!orden) {
      return;
    }
    this.procesando.set(true);
    this.errorAccion.set(null);

    this.compras.recepcionar(orden.orden_compra_id).subscribe({
      next: (respuesta) => {
        this.procesando.set(false);
        this.confirmando.set(null);
        this.ordenes.update((lista) =>
          lista.filter((item) => item.orden_compra_id !== orden.orden_compra_id),
        );
        this.ticketsDesbloqueados.set(respuesta.tickets_desbloqueados);
        this.mensajeExito.set('Orden de compra recepcionada exitosamente.');
      },
      error: (error: HttpErrorResponse) => {
        this.procesando.set(false);
        this.errorAccion.set(mensajeDeErrorCompras(error));
      },
    });
  }

  private cargar(): void {
    this.cargando.set(true);
    this.mensajeError.set(null);

    this.compras.listarOrdenes().subscribe({
      next: (ordenes) => {
        this.ordenes.set(ordenes);
        this.cargando.set(false);
      },
      error: (error: HttpErrorResponse) => {
        this.ordenes.set([]);
        this.cargando.set(false);
        this.mensajeError.set(mensajeDeErrorCompras(error));
      },
    });
  }
}
