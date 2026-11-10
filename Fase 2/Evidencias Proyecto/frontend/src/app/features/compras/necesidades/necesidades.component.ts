import { HttpErrorResponse } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  OnInit,
  computed,
  inject,
  signal,
} from '@angular/core';
import { RouterLink } from '@angular/router';

import { NecesidadReabastecimiento, NecesidadTicket, Sede } from '../../../shared/interfaces';
import { AdministracionService } from '../../administracion/services/administracion.service';
import { mensajeDeErrorCompras } from '../compras-errores';
import { ComprasService } from '../services/compras.service';

/** Fila con la demanda ya desglosada y sus subtotales (Feature 021). */
interface FilaNecesidad {
  fila: NecesidadReabastecimiento;
  tickets: NecesidadTicket[];
  subtotalSolicitado: number;
  subtotalCubierto: number;
  subtotalFaltante: number;
}

/**
 * Necesidades de reabastecimiento por sede y producto (Feature 020, AC-1; T8).
 *
 * Consolida lo que el backend calcula: productos activos en nivel critico o
 * cuya demanda `EnCurso` supera el stock de la sede, con el `sugerido` ya
 * resuelto (`max(0, stock_minimo + demanda - stock_actual)`). La vista no
 * reinterpreta la formula ni vuelve a filtrar: solo presenta y ofrece el paso
 * siguiente, crear una OC precargada con la fila elegida.
 *
 * El filtro por sede es un filtro de **lista**: se envia como query al servidor
 * y una sede sin filas (o ajena) responde `[]`, nunca 404.
 */
@Component({
  selector: 'app-compras-necesidades',
  standalone: true,
  imports: [RouterLink],
  templateUrl: './necesidades.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class NecesidadesComponent implements OnInit {
  private readonly compras = inject(ComprasService);
  private readonly administracion = inject(AdministracionService);

  readonly cargando = signal(true);
  readonly necesidades = signal<NecesidadReabastecimiento[]>([]);
  readonly sedes = signal<Sede[]>([]);
  readonly sedeSeleccionada = signal<number | null>(null);
  readonly mensajeError = signal<string | null>(null);

  /** Unidades sugeridas del filtro vigente, para el resumen de cabecera. */
  readonly totalSugerido = computed(() =>
    this.necesidades().reduce((total, fila) => total + fila.sugerido, 0),
  );

  /**
   * Feature 021 (AC-1): cada fila con los pedidos que componen su demanda y
   * sus subtotales. Toda la aritmetica se resuelve aqui; el template solo pinta.
   */
  readonly filas = computed<FilaNecesidad[]>(() =>
    this.necesidades().map((fila) => {
      const tickets = fila.tickets ?? [];
      return {
        fila,
        tickets,
        subtotalSolicitado: tickets.reduce(
          (total, pedido) => total + pedido.cantidad_solicitada,
          0,
        ),
        subtotalCubierto: tickets.reduce(
          (total, pedido) => total + pedido.cantidad_cubierta,
          0,
        ),
        subtotalFaltante: tickets.reduce(
          (total, pedido) => total + pedido.cantidad_faltante,
          0,
        ),
      };
    }),
  );

  ngOnInit(): void {
    this.cargarSedes();
    this.cargarNecesidades();
  }

  /** `''` es «todas las sedes»; cualquier otro valor viaja como `sede_id`. */
  filtrarPorSede(valor: string): void {
    this.sedeSeleccionada.set(valor === '' ? null : Number(valor));
    this.cargarNecesidades();
  }

  reintentar(): void {
    this.cargarSedes();
    this.cargarNecesidades();
  }

  private cargarSedes(): void {
    this.administracion.listarSedes().subscribe({
      next: (sedes) => this.sedes.set(sedes),
      // El selector es secundario: si falla, la tabla sigue siendo util sin el.
      error: () => this.sedes.set([]),
    });
  }

  private cargarNecesidades(): void {
    this.cargando.set(true);
    this.mensajeError.set(null);

    this.compras.listarNecesidades(this.sedeSeleccionada()).subscribe({
      next: (filas) => {
        this.necesidades.set(filas);
        this.cargando.set(false);
      },
      error: (error: HttpErrorResponse) => {
        this.necesidades.set([]);
        this.cargando.set(false);
        this.mensajeError.set(mensajeDeErrorCompras(error));
      },
    });
  }
}
