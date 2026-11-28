import { DatePipe } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  OnDestroy,
  OnInit,
  computed,
  inject,
  signal,
} from '@angular/core';
import { finalize } from 'rxjs';

import { TiempoRealService } from '../../core/services/tiempo-real.service';
import { DashboardAnalitico } from '../../shared/interfaces';
import { crearRefrescoAgrupado } from '../../shared/utils/refresco-agrupado';
import { DashboardService } from './services/dashboard.service';

/**
 * Dashboard analítico consolidado (Feature 009).
 *
 * Una sola lectura (`GET /dashboard/`) alimenta los cuatro KPI, el log de
 * alertas y la actividad reciente. La vista solo presenta: **no** decide ámbito
 * ni autorización. En particular, la sección de actividad se gobierna por el
 * booleano `actividad_disponible` que resuelve el servidor; con `false` (caso del
 * Solicitante) no se pinta y no se hace ninguna lectura del historial de
 * movimientos. Todo valor sale del DTO real, sin cifras de muestra.
 *
 * Desde la Feature 028 (T19) la vista se suscribe al hub de tiempo real y relee
 * el mismo DTO consolidado ante `pedidos`, `inventario` o la marca sintética
 * `dashboard`, en silencio: el refresco no enciende `cargando` ni muestra el
 * placeholder inicial y, si falla, conserva los datos previos (spec §5.4).
 */
@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [DatePipe],
  templateUrl: './dashboard.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class DashboardComponent implements OnInit, OnDestroy {
  private readonly dashboardService = inject(DashboardService);
  private readonly servicioTiempoReal = inject(TiempoRealService);

  readonly cargando = signal(true);
  readonly datos = signal<DashboardAnalitico | null>(null);
  readonly mensajeError = signal<string | null>(null);

  /** KPI del DTO, o `null` mientras no hay lectura. */
  readonly kpi = computed(() => this.datos()?.kpi ?? null);

  /** Log de alertas del DTO (lista vacía si no hay lectura). */
  readonly alertas = computed(() => this.datos()?.alertas ?? []);

  /** `true` cuando el servidor autoriza la sección de actividad al rol. */
  readonly actividadDisponible = computed(
    () => this.datos()?.actividad_disponible ?? false,
  );

  /** Movimientos recientes del DTO (vacíos para el Solicitante). */
  readonly actividad = computed(() => this.datos()?.actividad_movimientos ?? []);

  /**
   * Refresco del dashboard ante invalidaciones del hub (Feature 028, T19). Se
   * agrupa la ráfaga y solo relee el DTO consolidado, en silencio: no enciende
   * `cargando`, no muestra el placeholder y no toca el ámbito del rol.
   */
  private readonly refrescoDashboard = crearRefrescoAgrupado(() =>
    this.cargar({ silencioso: true }),
  );

  /**
   * Los tres frames que invalidan el dashboard: `pedidos`, `inventario` y la
   * marca sintética `dashboard` que el servidor entrega cuando el dominio de
   * origen está oculto por capacidad (AC-28).
   */
  private readonly cancelarSuscripcionCambios = this.servicioTiempoReal.alCambio(
    ['pedidos', 'inventario', 'dashboard'],
    () => this.refrescoDashboard.solicitar(),
  );

  /** `listo`, reapertura y vuelta a foco: resincroniza una vez por ventana. */
  private readonly cancelarSuscripcionResincronizacion =
    this.servicioTiempoReal.alResincronizar(() =>
      this.refrescoDashboard.solicitar(),
    );

  ngOnInit(): void {
    this.cargar();
  }

  ngOnDestroy(): void {
    this.cancelarSuscripcionCambios();
    this.cancelarSuscripcionResincronizacion();
    this.refrescoDashboard.cancelar();
  }

  /** Reintenta la lectura tras un error visible. */
  reintentar(): void {
    this.cargar();
  }

  /**
   * Una sola carga: el DTO consolidado es la unidad.
   *
   * La carga inicial y el reintento manual encienden `cargando` y, ante fallo,
   * descartan los datos previos (nada de cifras ficticias) y publican un
   * mensaje recuperable. El refresco silencioso (Feature 028, T19) no toca
   * `cargando` ni el error global, conserva `datos` si falla y devuelve una
   * promesa para que el agrupador sepa cuándo terminó (una en vuelo, una
   * pendiente).
   */
  private cargar({
    silencioso = false,
  }: { silencioso?: boolean } = {}): Promise<void> {
    if (!silencioso) {
      this.cargando.set(true);
      this.mensajeError.set(null);
    }

    return new Promise<void>((resolver) => {
      this.dashboardService
        .obtenerDashboard()
        .pipe(finalize(() => resolver()))
        .subscribe({
          next: (datos) => {
            this.datos.set(datos);
            // Un refresco exitoso deja obsoleto cualquier error previo.
            this.mensajeError.set(null);
            if (!silencioso) {
              this.cargando.set(false);
            }
          },
          error: () => {
            // El refresco silencioso conserva lo mostrado y no publica error
            // global: la siguiente invalidación o el reintento convergen.
            if (silencioso) {
              return;
            }
            this.datos.set(null);
            this.cargando.set(false);
            this.mensajeError.set(
              'No se pudo cargar el dashboard. Revisa la conexión e inténtalo de nuevo.',
            );
          },
        });
    });
  }
}
