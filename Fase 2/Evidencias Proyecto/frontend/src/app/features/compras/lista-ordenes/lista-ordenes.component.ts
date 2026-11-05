import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  OnInit,
  inject,
  signal,
} from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';

import {
  EstadoOrdenCompra,
  FacturaCompraRegistrar,
  OrdenCompra,
  Sede,
} from '../../../shared/interfaces';
import { AdministracionService } from '../../administracion/services/administracion.service';
import { mensajeDeErrorCompras } from '../compras-errores';
import { ComprasService } from '../services/compras.service';

/** Los cinco estados formales del ciclo de vida de la OC (spec §6.1). */
const ESTADOS_ORDEN: readonly EstadoOrdenCompra[] = [
  'Borrador',
  'Emitida',
  'Facturada',
  'Recibida',
  'Cancelada',
];

/**
 * Lista y acciones de las órdenes de compra del Administrador (Feature 020, T8).
 *
 * Presenta las OC de la institución con sus filtros de estado y sede y ofrece
 * **solo** las acciones que el estado permite: editar/emitir/cancelar en
 * `Borrador`, facturar en `Emitida` y corregir la factura en `Facturada`. La
 * vista no decide el flujo: si el servidor responde 409, se muestra su motivo y
 * la fila no cambia.
 *
 * La factura es un `PUT` idempotente; la vista elige `registrarFactura` cuando
 * la OC aun no tiene factura y `editarFactura` cuando ya la tiene, aunque ambas
 * llamen al mismo endpoint (AC-5).
 */
@Component({
  selector: 'app-compras-lista-ordenes',
  standalone: true,
  imports: [DatePipe, ReactiveFormsModule, RouterLink],
  templateUrl: './lista-ordenes.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ListaOrdenesComponent implements OnInit {
  private readonly compras = inject(ComprasService);
  private readonly administracion = inject(AdministracionService);
  private readonly constructorFormulario = inject(NonNullableFormBuilder);
  private readonly ruta = inject(ActivatedRoute);

  readonly estados = ESTADOS_ORDEN;

  readonly cargando = signal(true);
  readonly ordenes = signal<OrdenCompra[]>([]);
  readonly sedes = signal<Sede[]>([]);
  readonly filtroEstado = signal<EstadoOrdenCompra | null>(null);
  readonly filtroSede = signal<number | null>(null);
  readonly mensajeError = signal<string | null>(null);
  readonly mensajeExito = signal<string | null>(null);
  readonly errorAccion = signal<string | null>(null);

  readonly facturando = signal<OrdenCompra | null>(null);
  readonly cancelando = signal<OrdenCompra | null>(null);
  readonly guardandoFactura = signal(false);
  readonly guardandoCancelacion = signal(false);
  readonly procesando = signal<number | null>(null);

  readonly formularioFactura = this.constructorFormulario.group({
    numero_factura: ['', [Validators.required, Validators.maxLength(50)]],
    fecha_factura: ['', [Validators.required]],
    monto_total: [0, [Validators.required, Validators.min(0.01)]],
    observaciones: ['', [Validators.maxLength(500)]],
  });

  readonly formularioCancelacion = this.constructorFormulario.group({
    motivo_cancelacion: [
      '',
      [Validators.required, Validators.maxLength(500)],
    ],
  });

  ngOnInit(): void {
    this.cargarSedes();
    this.cargarOrdenes();
    this.leerMensajeDeRetorno();
  }

  // --- filtros -------------------------------------------------------------

  cambiarFiltroEstado(valor: string): void {
    this.filtroEstado.set(valor === '' ? null : (valor as EstadoOrdenCompra));
    this.cargarOrdenes();
  }

  cambiarFiltroSede(valor: string): void {
    this.filtroSede.set(valor === '' ? null : Number(valor));
    this.cargarOrdenes();
  }

  limpiarFiltros(): void {
    this.filtroEstado.set(null);
    this.filtroSede.set(null);
    this.cargarOrdenes();
  }

  reintentar(): void {
    this.cargarSedes();
    this.cargarOrdenes();
  }

  // --- acciones por estado -------------------------------------------------

  puedeEditar(orden: OrdenCompra): boolean {
    return orden.estado === 'Borrador';
  }

  puedeEmitir(orden: OrdenCompra): boolean {
    return orden.estado === 'Borrador';
  }

  puedeFacturar(orden: OrdenCompra): boolean {
    return orden.estado === 'Emitida' || orden.estado === 'Facturada';
  }

  puedeCancelar(orden: OrdenCompra): boolean {
    return orden.estado === 'Borrador' || orden.estado === 'Emitida';
  }

  /** Clases Tailwind completas del badge de estado (no se concatenan). */
  claseEstado(estado: EstadoOrdenCompra): string {
    const base =
      'inline-flex rounded-full px-2.5 py-1 text-xs font-semibold';
    switch (estado) {
      case 'Borrador':
        return `${base} bg-slate-100 text-slate-700`;
      case 'Emitida':
        return `${base} bg-blue-100 text-blue-800`;
      case 'Facturada':
        return `${base} bg-amber-100 text-amber-800`;
      case 'Recibida':
        return `${base} bg-emerald-100 text-emerald-800`;
      case 'Cancelada':
        return `${base} bg-rose-100 text-rose-800`;
    }
  }

  emitir(orden: OrdenCompra): void {
    this.limpiarMensajes();
    this.procesando.set(orden.orden_compra_id);

    this.compras.emitirOrden(orden.orden_compra_id).subscribe({
      next: (actualizada) => {
        this.procesando.set(null);
        this.reemplazar(actualizada);
        this.mensajeExito.set(
          `Orden ${actualizada.numero_oc ?? '#' + actualizada.orden_compra_id} emitida.`,
        );
      },
      error: (error: HttpErrorResponse) => {
        this.procesando.set(null);
        this.errorAccion.set(mensajeDeErrorCompras(error));
      },
    });
  }

  // --- factura (AC-5) ------------------------------------------------------

  abrirFactura(orden: OrdenCompra): void {
    this.limpiarMensajes();
    this.formularioFactura.reset({
      numero_factura: orden.factura?.numero_factura ?? '',
      fecha_factura:
        orden.factura?.fecha_factura ?? new Date().toISOString().slice(0, 10),
      monto_total: orden.factura
        ? Number(orden.factura.monto_total)
        : Number(orden.total),
      observaciones: orden.factura?.observaciones ?? '',
    });
    this.facturando.set(orden);
  }

  cerrarFactura(): void {
    this.facturando.set(null);
  }

  guardarFactura(): void {
    const orden = this.facturando();
    if (!orden) {
      return;
    }
    if (this.formularioFactura.invalid) {
      this.formularioFactura.markAllAsTouched();
      return;
    }
    const valores = this.formularioFactura.getRawValue();
    const datos: FacturaCompraRegistrar = {
      numero_factura: valores.numero_factura.trim(),
      fecha_factura: valores.fecha_factura,
      monto_total: valores.monto_total,
      observaciones: valores.observaciones.trim() || null,
    };
    const editando = orden.factura !== null;

    this.guardandoFactura.set(true);
    this.errorAccion.set(null);
    const peticion = editando
      ? this.compras.editarFactura(orden.orden_compra_id, datos)
      : this.compras.registrarFactura(orden.orden_compra_id, datos);

    peticion.subscribe({
      next: (factura) => {
        this.guardandoFactura.set(false);
        this.facturando.set(null);
        this.ordenes.update((lista) =>
          lista.map((item) =>
            item.orden_compra_id === orden.orden_compra_id
              ? { ...item, estado: 'Facturada', factura }
              : item,
          ),
        );
        this.mensajeExito.set(
          editando
            ? 'Factura actualizada. La orden sigue lista para recepción.'
            : 'Factura registrada. La orden quedó lista para recepción en bodega.',
        );
      },
      error: (error: HttpErrorResponse) => {
        this.guardandoFactura.set(false);
        this.errorAccion.set(mensajeDeErrorCompras(error));
      },
    });
  }

  // --- cancelacion (AC-12) -------------------------------------------------

  abrirCancelacion(orden: OrdenCompra): void {
    this.limpiarMensajes();
    this.formularioCancelacion.reset({ motivo_cancelacion: '' });
    this.cancelando.set(orden);
  }

  cerrarCancelacion(): void {
    this.cancelando.set(null);
  }

  confirmarCancelacion(): void {
    const orden = this.cancelando();
    if (!orden) {
      return;
    }
    const motivo = this.formularioCancelacion.controls.motivo_cancelacion.value.trim();
    if (motivo === '') {
      this.formularioCancelacion.markAllAsTouched();
      this.errorAccion.set('El motivo de cancelación es obligatorio.');
      return;
    }

    this.guardandoCancelacion.set(true);
    this.errorAccion.set(null);
    this.compras.cancelarOrden(orden.orden_compra_id, motivo).subscribe({
      next: (actualizada) => {
        this.guardandoCancelacion.set(false);
        this.cancelando.set(null);
        this.reemplazar(actualizada);
        this.mensajeExito.set(
          `Orden ${actualizada.numero_oc ?? '#' + actualizada.orden_compra_id} cancelada.`,
        );
      },
      error: (error: HttpErrorResponse) => {
        this.guardandoCancelacion.set(false);
        this.errorAccion.set(mensajeDeErrorCompras(error));
      },
    });
  }

  // --- carga ---------------------------------------------------------------

  private cargarSedes(): void {
    this.administracion.listarSedes().subscribe({
      next: (sedes) => this.sedes.set(sedes),
      error: () => this.sedes.set([]),
    });
  }

  private cargarOrdenes(): void {
    this.cargando.set(true);
    this.mensajeError.set(null);

    this.compras
      .listarOrdenes({
        estado: this.filtroEstado(),
        sede_id: this.filtroSede(),
      })
      .subscribe({
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

  /** Mensaje de una sola vez tras crear/editar desde el formulario. */
  private leerMensajeDeRetorno(): void {
    const exito = this.ruta.snapshot.queryParamMap.get('exito');
    if (exito === 'creada') {
      this.mensajeExito.set('Orden de compra creada en borrador.');
    } else if (exito === 'actualizada') {
      this.mensajeExito.set('Orden de compra actualizada.');
    }
  }

  private reemplazar(actualizada: OrdenCompra): void {
    this.ordenes.update((lista) =>
      lista.map((item) =>
        item.orden_compra_id === actualizada.orden_compra_id ? actualizada : item,
      ),
    );
  }

  private limpiarMensajes(): void {
    this.mensajeExito.set(null);
    this.errorAccion.set(null);
  }
}
