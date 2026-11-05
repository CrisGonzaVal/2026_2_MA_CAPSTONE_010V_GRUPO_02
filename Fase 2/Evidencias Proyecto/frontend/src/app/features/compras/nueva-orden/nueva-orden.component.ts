import { DecimalPipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  OnInit,
  computed,
  inject,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import {
  FormArray,
  FormControl,
  FormGroup,
  NonNullableFormBuilder,
  ReactiveFormsModule,
  Validators,
} from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { forkJoin } from 'rxjs';

import {
  OrdenCompra,
  OrdenCompraCrear,
  Producto,
  Proveedor,
  ProveedorCrear,
  Sede,
} from '../../../shared/interfaces';
import { AdministracionService } from '../../administracion/services/administracion.service';
import { InventarioService } from '../../inventario/services/inventario.service';
import { mensajeDeErrorCompras } from '../compras-errores';
import { ComprasService } from '../services/compras.service';

/** Grupo tipado de una línea de la OC (producto, cantidad y costo pactado). */
interface LineaOrdenForm {
  producto_id: FormControl<number>;
  cantidad_solicitada: FormControl<number>;
  precio_unitario: FormControl<number>;
}

/**
 * Alta y edición de una orden de compra en borrador (Feature 020, T8).
 *
 * El mismo formulario sirve para `POST /compras/ordenes` y
 * `PUT /compras/ordenes/{id}`; en modo edición se carga la OC desde el listado
 * institucional (no existe lectura por ID en el contrato) y se exige que siga en
 * `Borrador`: emitida o posterior, la vista bloquea y ofrece volver.
 *
 * El selector de proveedor convive con un alta inline que escribe en el catálogo
 * global (`POST /compras/proveedores`) y selecciona el proveedor recién creado.
 * Los ítems son un `FormArray` con al menos una línea; el total se recalcula con
 * cada cambio y es solo informativo: el servidor lo vuelve a calcular.
 */
@Component({
  selector: 'app-compras-nueva-orden',
  standalone: true,
  imports: [DecimalPipe, ReactiveFormsModule, RouterLink],
  templateUrl: './nueva-orden.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class NuevaOrdenComponent implements OnInit {
  private readonly compras = inject(ComprasService);
  private readonly administracion = inject(AdministracionService);
  private readonly inventario = inject(InventarioService);
  private readonly constructorFormulario = inject(NonNullableFormBuilder);
  private readonly ruta = inject(ActivatedRoute);
  private readonly router = inject(Router);

  /** `id` de la ruta `:id/editar`; `null` en el alta. */
  readonly ordenId = signal<number | null>(this.leerIdDeRuta());
  readonly modoEdicion = computed(() => this.ordenId() !== null);

  readonly cargando = signal(true);
  readonly sedes = signal<Sede[]>([]);
  readonly proveedores = signal<Proveedor[]>([]);
  readonly productos = signal<Producto[]>([]);
  readonly orden = signal<OrdenCompra | null>(null);

  readonly errorCarga = signal<string | null>(null);
  readonly errorAccion = signal<string | null>(null);
  readonly mensajeExito = signal<string | null>(null);
  readonly guardando = signal(false);
  readonly guardandoProveedor = signal(false);
  readonly mostrarAltaProveedor = signal(false);
  readonly totalEstimado = signal(0);

  readonly formulario = this.constructorFormulario.group({
    sede_id: [0, [Validators.required, Validators.min(1)]],
    proveedor_id: [0, [Validators.required, Validators.min(1)]],
    items: this.constructorFormulario.array([this.crearLinea()]),
  });

  readonly formularioProveedor = this.constructorFormulario.group({
    rut: ['', [Validators.required, Validators.maxLength(20)]],
    razon_social: ['', [Validators.required, Validators.maxLength(150)]],
    giro: ['', [Validators.maxLength(100)]],
    correo: ['', [Validators.email, Validators.maxLength(100)]],
    telefono: ['', [Validators.maxLength(20)]],
  });

  constructor() {
    this.formulario.valueChanges
      .pipe(takeUntilDestroyed())
      .subscribe(() => this.calcularTotal());
  }

  get lineas(): FormArray<FormGroup<LineaOrdenForm>> {
    return this.formulario.controls.items;
  }

  ngOnInit(): void {
    this.cargar();
  }

  // --- lineas --------------------------------------------------------------

  agregarLinea(): void {
    this.lineas.push(this.crearLinea());
    this.calcularTotal();
  }

  quitarLinea(indice: number): void {
    if (this.lineas.length <= 1) {
      return;
    }
    this.lineas.removeAt(indice);
    this.calcularTotal();
  }

  subtotal(linea: FormGroup<LineaOrdenForm>): number {
    const cantidad = Number(linea.controls.cantidad_solicitada.value) || 0;
    const precio = Number(linea.controls.precio_unitario.value) || 0;
    return cantidad * precio;
  }

  // --- alta inline de proveedor (AC-2) -------------------------------------

  alternarAltaProveedor(): void {
    this.mostrarAltaProveedor.update((visible) => !visible);
    this.errorAccion.set(null);
    this.mensajeExito.set(null);
  }

  guardarProveedor(): void {
    if (this.formularioProveedor.invalid) {
      this.formularioProveedor.markAllAsTouched();
      return;
    }
    const valores = this.formularioProveedor.getRawValue();
    const datos: ProveedorCrear = {
      rut: valores.rut.trim(),
      razon_social: valores.razon_social.trim(),
      giro: valores.giro.trim() || null,
      correo: valores.correo.trim() || null,
      telefono: valores.telefono.trim() || null,
    };

    this.guardandoProveedor.set(true);
    this.errorAccion.set(null);
    this.compras.crearProveedor(datos).subscribe({
      next: (proveedor) => {
        this.guardandoProveedor.set(false);
        this.proveedores.update((lista) => [...lista, proveedor]);
        this.formulario.controls.proveedor_id.setValue(proveedor.proveedor_id);
        this.formularioProveedor.reset({
          rut: '',
          razon_social: '',
          giro: '',
          correo: '',
          telefono: '',
        });
        this.mostrarAltaProveedor.set(false);
        this.mensajeExito.set(
          `Proveedor «${proveedor.razon_social}» registrado en el catálogo global.`,
        );
      },
      error: (error: HttpErrorResponse) => {
        this.guardandoProveedor.set(false);
        this.errorAccion.set(mensajeDeErrorCompras(error));
      },
    });
  }

  // --- guardado ------------------------------------------------------------

  guardar(): void {
    if (this.formulario.invalid || this.lineas.length === 0) {
      this.formulario.markAllAsTouched();
      if (this.lineas.length === 0) {
        this.errorAccion.set('Agrega al menos un ítem a la orden.');
      }
      return;
    }
    const valores = this.formulario.getRawValue();
    const datos: OrdenCompraCrear = {
      sede_id: valores.sede_id,
      proveedor_id: valores.proveedor_id,
      items: valores.items.map((item) => ({
        producto_id: item.producto_id,
        cantidad_solicitada: item.cantidad_solicitada,
        precio_unitario: item.precio_unitario,
      })),
    };
    const id = this.ordenId();

    this.guardando.set(true);
    this.errorAccion.set(null);
    this.mensajeExito.set(null);
    const peticion =
      id === null
        ? this.compras.crearOrden(datos)
        : this.compras.actualizarOrden(id, datos);

    peticion.subscribe({
      next: () => {
        this.guardando.set(false);
        void this.router.navigate(['/compras'], {
          queryParams: { exito: id === null ? 'creada' : 'actualizada' },
        });
      },
      error: (error: HttpErrorResponse) => {
        this.guardando.set(false);
        this.errorAccion.set(mensajeDeErrorCompras(error));
      },
    });
  }

  reintentar(): void {
    this.cargar();
  }

  // --- carga ---------------------------------------------------------------

  private cargar(): void {
    this.cargando.set(true);
    this.errorCarga.set(null);

    forkJoin({
      sedes: this.administracion.listarSedes(),
      proveedores: this.compras.listarProveedores(),
      productos: this.inventario.obtenerProductos(),
    }).subscribe({
      next: ({ sedes, proveedores, productos }) => {
        this.sedes.set(sedes);
        this.proveedores.set(proveedores);
        this.productos.set(productos);
        const id = this.ordenId();
        if (id === null) {
          this.prefillDesdeQuery();
          this.cargando.set(false);
        } else {
          this.cargarOrden(id);
        }
      },
      error: (error: HttpErrorResponse) => {
        this.cargando.set(false);
        this.errorCarga.set(mensajeDeErrorCompras(error));
      },
    });
  }

  /**
   * Carga la OC a editar desde el listado institucional.
   *
   * El contrato no publica `GET /compras/ordenes/{id}`: el listado ya devuelve
   * la proyección completa (proveedor, sede, ítems y factura), así que la vista
   * encuentra la suya por id y respeta el ámbito del servidor.
   */
  private cargarOrden(id: number): void {
    this.compras.listarOrdenes().subscribe({
      next: (ordenes) => {
        this.cargando.set(false);
        const orden = ordenes.find((fila) => fila.orden_compra_id === id) ?? null;
        if (orden === null) {
          this.errorCarga.set(
            'La orden no existe o no está en tu alcance. Vuelve al listado e inténtalo de nuevo.',
          );
          return;
        }
        if (orden.estado !== 'Borrador') {
          this.errorCarga.set(
            `Solo se puede editar una orden en estado Borrador; esta está ${orden.estado}.`,
          );
          return;
        }
        this.orden.set(orden);
        this.patchOrden(orden);
      },
      error: (error: HttpErrorResponse) => {
        this.cargando.set(false);
        this.errorCarga.set(mensajeDeErrorCompras(error));
      },
    });
  }

  private patchOrden(orden: OrdenCompra): void {
    this.formulario.controls.sede_id.setValue(orden.sede_id);
    this.formulario.controls.proveedor_id.setValue(orden.proveedor_id);
    this.lineas.clear();
    for (const detalle of orden.detalles) {
      this.lineas.push(
        this.crearLinea(
          detalle.producto_id,
          detalle.cantidad_solicitada,
          Number(detalle.precio_unitario),
        ),
      );
    }
    if (this.lineas.length === 0) {
      this.lineas.push(this.crearLinea());
    }
    this.calcularTotal();
  }

  /** Precarga desde «Crear OC» de necesidades: sede, producto y cantidad. */
  private prefillDesdeQuery(): void {
    const parametros = this.ruta.snapshot.queryParamMap;
    const sedeId = Number(parametros.get('sede_id'));
    const productoId = Number(parametros.get('producto_id'));
    const cantidad = Number(parametros.get('cantidad'));

    if (sedeId > 0) {
      this.formulario.controls.sede_id.setValue(sedeId);
    }
    if (productoId > 0) {
      const linea = this.lineas.at(0);
      linea.controls.producto_id.setValue(productoId);
      if (cantidad > 0) {
        linea.controls.cantidad_solicitada.setValue(cantidad);
      }
    }
    this.calcularTotal();
  }

  private crearLinea(
    productoId = 0,
    cantidad = 1,
    precio = 0,
  ): FormGroup<LineaOrdenForm> {
    return this.constructorFormulario.group({
      producto_id: productoId,
      cantidad_solicitada: [cantidad, [Validators.required, Validators.min(1)]],
      precio_unitario: [precio, [Validators.required, Validators.min(0)]],
    });
  }

  private calcularTotal(): void {
    const total = this.lineas.controls.reduce(
      (suma, linea) => suma + this.subtotal(linea),
      0,
    );
    this.totalEstimado.set(total);
  }

  private leerIdDeRuta(): number | null {
    const id = Number(this.ruta.snapshot.paramMap.get('id'));
    return Number.isInteger(id) && id > 0 ? id : null;
  }
}
