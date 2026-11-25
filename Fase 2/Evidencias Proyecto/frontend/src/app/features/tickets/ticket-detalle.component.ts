import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  computed,
  effect,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { forkJoin, of } from 'rxjs';

import {
  puedeAnularTicket,
  puedeAprobarTicket,
  puedeConfirmarEntrega,
  puedeDespacharTicket,
  puedeEditarTicket,
  puedeRechazarTicket,
} from '../../core/auth/roles';
import { AutenticacionService } from '../../core/services/auth.service';
import {
  CatalogosTicket,
  DetalleTicket,
  DetalleTicketCrear,
  EstadoTicket,
  GestorProceso,
  HistorialTransicion,
  ProductoCatalogo,
  TicketDetalle,
  TicketEditar,
} from '../../shared/interfaces';
// Feature 021 (V-3): presentacion de estados, con las palabras separadas.
import { etiquetaEstado as etiquetaVisible } from '../../shared/utils/etiqueta-estado';
import {
  MensajesDeErrorHttp,
  mensajeDeErrorHttp,
} from '../../shared/utils/errores-http';
import { TicketService } from './services/ticket.service';

/** Fila resuelta del historial para el template (sin ids que el template no conozca). */
interface FilaHistorial {
  historial_transicion_id: number;
  origen: string;
  destino: string;
  actor: string;
  fecha: string;
  motivo: string | null;
  /** Feature 021 (AC-6): OC que desbloqueo el pedido, si aplica. */
  numeroOc: string | null;
}

/**
 * Acciones semánticas que la barra ofrece según estado y rol (ampliación
 * 25/Nov/2026, AC-32). No hay «Avanzar» ni «Retroceder»: cada botón expresa
 * una decisión del negocio y el `PATCH /estado` de legado no se invoca.
 */
interface AccionesDetalle {
  aprobar: boolean;
  despachar: boolean;
  confirmarEntrega: boolean;
  editar: boolean;
  anular: boolean;
  rechazar: boolean;
}

/** Tipo de confirmación abierta en el `<dialog>` nativo. */
type TipoConfirmacion = 'anular' | 'rechazo' | 'despacho' | 'entrega';

/**
 * Opción de un selector de producto de la edición (Feature 014, AC-9).
 *
 * `inactivo` distingue el producto que ya figura en los detalles actuales del
 * ticket y ya no está disponible: se ofrece **solo en su propia fila** para
 * conservarlo, nunca en una línea nueva.
 */
interface OpcionProductoEdicion {
  producto_id: number;
  etiqueta: string;
  inactivo: boolean;
}

/** Badge de prioridad por su nombre real; sin correspondencia, clase neutra. */
const CLASES_PRIORIDAD: Record<string, string> = {
  ALTA: 'text-rose-600 bg-rose-50',
  MEDIA: 'text-blue-600 bg-blue-50',
  BAJA: 'text-amber-600 bg-amber-50',
};

const MENSAJES_TICKETS: MensajesDeErrorHttp = {
  401: 'Tu sesión no es válida. Vuelve a iniciar sesión.',
  403: 'Tu rol no tiene permiso para esta operación sobre el pedido.',
  404: 'El pedido indicado no existe o no está en tu alcance.',
  409: 'La operación entra en conflicto con el estado actual del pedido.',
  422: 'Los datos enviados no son válidos: revisa el motivo y los campos del pedido.',
  predeterminado: (estado) => `No se pudo completar la operación (HTTP ${estado}).`,
};

/**
 * Mensaje legible de un fallo del ciclo de vida (Feature 013).
 *
 * Delega la estructura común —`detail` textual, status 0 y fallback— en
 * `mensajeDeErrorHttp`; aquí solo viven los textos de este dominio.
 */
export function mensajeDeErrorTickets(error: HttpErrorResponse): string {
  return mensajeDeErrorHttp(error, MENSAJES_TICKETS);
}

/**
 * Vista de detalle del ticket (Feature 013, D-13; ampliación 25/Nov/2026).
 *
 * Muestra cabecera (asunto, prioridad, estado canónico con la etiqueta de
 * proceso junto a él, solicitante con departamento, sede, fechas y los dos
 * responsables del historial), ítems con cantidades solicitadas y entregadas,
 * la cobertura de compras y el historial completo. **Toda mutación del ciclo
 * de vida se opera aquí** (D-14) con acciones semánticas: aprobar (un clic),
 * despachar y confirmar entrega (diálogo sin motivo), además de editar, anular
 * y rechazar (con motivo obligatorio). No hay «Avanzar»/«Retroceder» y la
 * vista no invoca `PATCH /estado` (AC-48).
 *
 * Tras cada mutación aceptada —y también tras un rechazo del servidor— se
 * reconsultan detalle e historial para reflejar la verdad del backend. Un
 * `enOperacion` común bloquea todos los controles mientras hay una petición en
 * vuelo (anti doble envío).
 */
@Component({
  selector: 'app-ticket-detalle',
  standalone: true,
  imports: [ReactiveFormsModule, DatePipe, RouterLink],
  templateUrl: './ticket-detalle.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class TicketDetalleComponent {
  private readonly servicioTickets = inject(TicketService);
  private readonly autenticacion = inject(AutenticacionService);
  private readonly route = inject(ActivatedRoute);
  private readonly fb = inject(NonNullableFormBuilder);

  // --- Estado de la carga ---

  readonly ticketId = signal<number | null>(null);
  readonly ticket = signal<TicketDetalle | null>(null);
  readonly historial = signal<HistorialTransicion[]>([]);
  readonly catalogos = signal<CatalogosTicket | null>(null);
  readonly cargando = signal(true);
  readonly errorCarga = signal<string | null>(null);

  // --- Estado de las operaciones ---

  readonly errorAccion = signal<string | null>(null);
  readonly mensajeExito = signal<string | null>(null);
  /** `true` mientras una mutación está en vuelo: bloquea todos los controles. */
  readonly enOperacion = signal(false);
  /** `null` sin confirmación abierta; el tipo abierto mientras el modal vive. */
  readonly confirmando = signal<TipoConfirmacion | null>(null);
  readonly editando = signal(false);

  // --- Identidad (presentación; la autorización la decide la API, D-2) ---

  readonly rolActual = computed(() => this.autenticacion.identidad()?.rol ?? null);

  /** `true` si el ticket abierto pertenece al usuario de la sesión. */
  readonly esDueno = computed(() => {
    const identidad = this.autenticacion.identidad();
    const ticket = this.ticket();
    return identidad !== null && ticket !== null && identidad.usuario_id === ticket.usuario_id;
  });

  // --- Catálogos resolutivos ---

  readonly estados = computed<EstadoTicket[]>(() => this.catalogos()?.estados ?? []);
  readonly prioridades = computed(() => this.catalogos()?.prioridades ?? []);
  /**
   * Productos disponibles del catálogo. El servidor ya excluye inactivos y los
   * de categoría inactiva; el filtro es la salvaguarda de UI (AC-4/AC-9).
   */
  readonly productos = computed<ProductoCatalogo[]>(() =>
    (this.catalogos()?.productos ?? []).filter((producto) => producto.activo !== false)
  );
  readonly solicitantes = computed(() => this.catalogos()?.solicitantes ?? []);

  // --- Derivación del estado actual ---

  /** Nombre del estado del ticket: catálogo por id, luego el campo del detalle. */
  readonly nombreEstado = computed<string | null>(() => {
    const ticket = this.ticket();
    if (ticket === null) {
      return null;
    }
    return (
      this.estados().find((estado) => estado.estado_id === ticket.estado_id)?.nombre ??
      ticket.estado_nombre ??
      null
    );
  });

  private readonly estadoNormalizado = computed(() =>
    this.nombreEstado() === null ? null : normalizar(this.nombreEstado()!),
  );

  /** `Pendiente` y el `EnRevision` heredado admiten aprobar, anular y rechazar (D-3). */
  private readonly admiteDecision = computed(() => {
    const estado = this.estadoNormalizado();
    return estado === 'pendiente' || estado === 'enrevision';
  });

  /**
   * Acciones semánticas ofrecidas por estado y rol (AC-32, ampliación
   * 25/Nov/2026).
   *
   * Aprobar: solo Administrador, desde `Pendiente` o `EnRevision` (heredado).
   * Despachar: Administrador/Bodeguero, solo `EnCurso` y con `stock_disponible`.
   * Confirmar entrega: Solicitante **dueño**, solo `Cerrado` sin confirmar.
   * Editar: solo `Pendiente`, Administrador o dueño. Anular: `Pendiente`/
   * `EnRevision`, Administrador o dueño. Rechazar: `Pendiente`/`EnRevision`,
   * Bodeguero/Administrador. `Anulado` no ofrece ninguna.
   */
  readonly acciones = computed<AccionesDetalle>(() => {
    const rol = this.rolActual();
    const estado = this.estadoNormalizado();
    const ticket = this.ticket();
    const esAdministrador = rol === 'Administrador';
    const esDueno = this.esDueno();
    return {
      aprobar: this.admiteDecision() && puedeAprobarTicket(rol),
      despachar:
        estado === 'encurso' &&
        puedeDespacharTicket(rol) &&
        ticket?.stock_disponible === true,
      confirmarEntrega:
        estado === 'cerrado' &&
        puedeConfirmarEntrega(rol) &&
        esDueno &&
        ticket?.entrega_confirmada !== true,
      editar:
        estado === 'pendiente' &&
        puedeEditarTicket(rol) &&
        (esAdministrador || esDueno),
      anular:
        this.admiteDecision() &&
        puedeAnularTicket(rol) &&
        (esAdministrador || esDueno),
      rechazar: this.admiteDecision() && puedeRechazarTicket(rol),
    };
  });

  /** `true` si al menos una acción está disponible. */
  readonly hayAcciones = computed(() => Object.values(this.acciones()).some(Boolean));

  /**
   * Nota visible cuando no hay ninguna acción: distingue los terminales
   * (`Cerrado` despachado pendiente de confirmación, `Cerrado` entregado,
   * `Anulado`), el `EnCurso` sin stock y el rol sin permiso, para que el vacío
   * sea informativo (AC-23/AC-32).
   */
  readonly notaAcciones = computed<string | null>(() => {
    if (this.hayAcciones() || this.ticket() === null) {
      return null;
    }
    const estado = this.estadoNormalizado();
    if (estado === 'anulado') {
      return 'Este pedido está Anulado: el rechazo o la anulación quedaron registrados y no admite más acciones.';
    }
    if (estado === 'cerrado') {
      if (this.ticket()?.entrega_confirmada === true) {
        return 'Este pedido está Cerrado y su entrega ya fue confirmada por el Solicitante: no admite más acciones.';
      }
      return 'Este pedido está Cerrado y pendiente de confirmación de entrega por el Solicitante dueño: las demás acciones del ciclo de vida no aplican.';
    }
    if (estado === 'encurso' && this.ticket()?.stock_disponible !== true) {
      return 'El pedido está En curso, pero el stock local aún no está disponible: el despacho se habilitará cuando la sede lo cubra.';
    }
    return 'Tu rol no puede operar el ciclo de vida de este pedido en su estado actual: solo puedes consultarlo.';
  });

  // --- Read model de proceso (ampliación 25/Nov/2026, AC-37/AC-39/AC-40) ---

  /**
   * Etiqueta derivada por el servidor. NO pasa por el helper de etiquetas de
   * estado: ya viaja con sus espacios («En confirmación de stock local»).
   */
  readonly etiquetaProceso = computed<string | null>(
    () => this.ticket()?.etiqueta_proceso ?? null,
  );

  readonly explicacionProceso = computed<string | null>(
    () => this.ticket()?.explicacion_proceso ?? null,
  );

  /** Último Bodeguero del historial; «Sin gestión registrada» si no hay fila. */
  readonly gestorBodeguero = computed<string>(() =>
    this.nombreGestor(this.ticket()?.gestionado_por_bodeguero ?? null),
  );

  /** Último Administrador del historial; «Sin gestión registrada» si no hay fila. */
  readonly gestorAdministrador = computed<string>(() =>
    this.nombreGestor(this.ticket()?.gestionado_por_administrador ?? null),
  );

  /** Actor de la confirmación de entrega, con la misma forma que el resto. */
  readonly entregaConfirmadaPor = computed<string | null>(() => {
    const ticket = this.ticket();
    if (ticket === null) {
      return null;
    }
    const nombre = this.nombrePersona(
      ticket.entrega_confirmada_por_nombre,
      ticket.entrega_confirmada_por_apellido,
    );
    return nombre === '' ? null : nombre;
  });

  // --- Etiquetas de presentación ---

  readonly etiquetaPrioridad = computed<string>(() => {
    const ticket = this.ticket();
    if (ticket === null) {
      return '';
    }
    const prioridad = this.prioridades().find(
      (p) => p.prioridad_id === ticket.prioridad_id,
    );
    return prioridad?.nombre ?? ticket.prioridad_nombre ?? `Prioridad #${ticket.prioridad_id}`;
  });

  /** Clase Tailwind del badge de prioridad, tolerante a mayúsculas (mismo criterio que el tablero). */
  readonly clasePrioridad = computed(() => {
    const nombre = this.etiquetaPrioridad().toUpperCase();
    return CLASES_PRIORIDAD[nombre] ?? 'text-slate-600 bg-slate-100';
  });

  readonly etiquetaEstado = computed<string>(() => {
    const ticket = this.ticket();
    if (ticket === null) {
      return '';
    }
    return etiquetaVisible(this.nombreEstado() ?? `Estado #${ticket.estado_id}`);
  });

  /** Badge de estado: `Anulado` y `Cerrado` se distinguen de un vistazo (AC-23). */
  readonly claseEstado = computed(() => {
    const estado = this.estadoNormalizado();
    if (estado === 'anulado') {
      return 'text-rose-700 bg-rose-50';
    }
    if (estado === 'cerrado') {
      return 'text-emerald-700 bg-emerald-50';
    }
    if (estado === 'encurso') {
      return 'text-indigo-700 bg-indigo-50';
    }
    if (estado === 'enrevision') {
      return 'text-amber-700 bg-amber-50';
    }
    return 'text-slate-700 bg-slate-100';
  });

  readonly etiquetaSolicitante = computed<string>(() => {
    const ticket = this.ticket();
    if (ticket === null) {
      return '';
    }
    const solicitante = this.solicitantes().find(
      (s) => s.usuario_id === ticket.usuario_id,
    );
    if (solicitante) {
      return `${solicitante.apellido}, ${solicitante.nombre}`;
    }
    const nombre = [ticket.solicitante_apellido, ticket.solicitante_nombre]
      .filter((parte): parte is string => typeof parte === 'string' && parte !== '')
      .join(', ');
    return nombre !== '' ? nombre : `Usuario #${ticket.usuario_id}`;
  });

  readonly correoSolicitante = computed<string | null>(() => {
    const ticket = this.ticket();
    if (ticket === null) {
      return null;
    }
    return (
      this.solicitantes().find((s) => s.usuario_id === ticket.usuario_id)?.correo ??
      ticket.solicitante_correo ??
      null
    );
  });

  readonly etiquetaDepartamento = computed<string | null>(() => {
    const ticket = this.ticket();
    if (ticket === null) {
      return null;
    }
    return (
      this.solicitantes().find((s) => s.usuario_id === ticket.usuario_id)
        ?.departamento_nombre ??
      ticket.departamento_nombre ??
      null
    );
  });

  readonly etiquetaSede = computed<string>(() => {
    const ticket = this.ticket();
    if (ticket === null) {
      return '';
    }
    if (ticket.sede_nombre) {
      return ticket.sede_nombre;
    }
    return ticket.sede_id !== null ? `Sede #${ticket.sede_id}` : 'Sin sede registrada';
  });

  // --- Historial resuelto ---

  /** Historial listo para el template: nombres resueltos, sin ids sueltos. */
  readonly filasHistorial = computed<FilaHistorial[]>(() =>
    this.historial().map((fila) => ({
      historial_transicion_id: fila.historial_transicion_id,
      origen:
        fila.estado_origen_id === null
          ? 'Creación'
          : etiquetaVisible(
              fila.estado_origen_nombre ??
                this.nombreDeEstado(fila.estado_origen_id) ??
                `Estado #${fila.estado_origen_id}`,
            ),
      destino: etiquetaVisible(
        fila.estado_destino_nombre ??
          this.nombreDeEstado(fila.estado_destino_id) ??
          `Estado #${fila.estado_destino_id}`,
      ),
      actor: this.actorDeFila(fila),
      fecha: fila.fecha_transicion,
      motivo: fila.motivo,
      numeroOc: fila.numero_oc ?? null,
    })),
  );

  // --- Formularios ---

  /**
   * Motivo obligatorio de la confirmación de anulación/rechazo (D-6). Las
   * confirmaciones de despacho y entrega no lo piden: el mismo diálogo lo
   * muestra solo cuando `exigeMotivo()` es `true`.
   */
  readonly motivoForm = this.fb.group({
    motivo: ['', [Validators.required, Validators.maxLength(500)]],
  });

  /** Edición en `Pendiente`: asunto, descripción, prioridad e ítems completos (D-9). */
  readonly formularioEdicion = this.fb.group({
    asunto: ['', [Validators.required, Validators.minLength(3), Validators.maxLength(150)]],
    descripcion: ['', Validators.maxLength(500)],
    prioridad_id: [null as number | null, Validators.required],
    detalles: this.fb.array([this.crearFilaEdicion()]),
  });

  readonly detallesEdicion = this.formularioEdicion.controls.detalles;

  crearFilaEdicion() {
    return this.fb.group({
      producto_id: [null as number | null, Validators.required],
      cantidad_solicitada: [1, [Validators.required, Validators.min(1)]],
    });
  }

  agregarDetalleEdicion() {
    this.detallesEdicion.push(this.crearFilaEdicion());
  }

  /** Con una sola fila no se quita: el backend exige al menos un ítem (422). */
  puedeQuitarDetalleEdicion(): boolean {
    return this.detallesEdicion.length > 1;
  }

  quitarDetalleEdicion(indice: number) {
    if (this.puedeQuitarDetalleEdicion()) {
      this.detallesEdicion.removeAt(indice);
    }
  }

  /** Ítems repetidos por producto se fusionan antes de enviar (mismo criterio que el alta). */
  combinarDetallesEdicion(): DetalleTicketCrear[] {
    const cantidades = new Map<number, number>();
    for (const fila of this.detallesEdicion.controls) {
      const productoId = fila.controls.producto_id.value;
      if (productoId === null) {
        continue;
      }
      cantidades.set(
        productoId,
        (cantidades.get(productoId) ?? 0) + fila.controls.cantidad_solicitada.value,
      );
    }
    return [...cantidades].map(([producto_id, cantidad_solicitada]) => ({
      producto_id,
      cantidad_solicitada,
    }));
  }

  /**
   * Opciones del selector de producto de una fila de edición (Feature 014, AC-9).
   *
   * Ofrece los productos **activos** del catálogo y, además, el producto de esa
   * misma fila cuando ya figura en los detalles actuales del ticket y dejó de
   * estar disponible. Así un ítem cuyo producto se retiró se puede conservar y
   * su cantidad modificar, pero no se puede elegir ese producto en una línea
   * nueva: una fila nueva arranca sin producto y solo recibe opciones activas.
   *
   * El servidor aplica la misma delimitación por `producto_id` (D-7): un
   * inactivo que no figure en los detalles actuales responde 409.
   */
  opcionesProductoEdicion(indice: number): OpcionProductoEdicion[] {
    const activos = this.productos().map((producto) => ({
      producto_id: producto.producto_id,
      etiqueta: `${producto.nombre} · ${producto.categoria_nombre}`,
      inactivo: false,
    }));

    const productoId = this.detallesEdicion.at(indice)?.controls.producto_id.value ?? null;
    if (productoId === null || activos.some((opcion) => opcion.producto_id === productoId)) {
      return activos;
    }

    const detalle = this.detalleActual(productoId);
    return [
      ...activos,
      {
        producto_id: productoId,
        etiqueta:
          detalle === null
            ? `Producto #${productoId} — no disponible (solo se conserva)`
            : this.etiquetaProductoConservado(detalle),
        inactivo: true,
      },
    ];
  }

  /** `true` si la fila conserva un producto que ya no está disponible. */
  esProductoInactivoEdicion(indice: number): boolean {
    const productoId = this.detallesEdicion.at(indice)?.controls.producto_id.value ?? null;
    return this.opcionesProductoEdicion(indice).some(
      (opcion) => opcion.inactivo && opcion.producto_id === productoId,
    );
  }

  /** Fila de los detalles **actuales** del ticket para un producto, si existe. */
  private detalleActual(productoId: number): DetalleTicket | null {
    return this.ticket()?.detalles.find((detalle) => detalle.producto_id === productoId) ?? null;
  }

  /**
   * Etiqueta de un producto conservado: nombre y categoría resueltos para que
   * la fila sea legible aunque el producto ya no viaje en el catálogo.
   */
  private etiquetaProductoConservado(detalle: DetalleTicket): string {
    const nombre = detalle.producto?.nombre ?? `Producto #${detalle.producto_id}`;
    const categoria = detalle.producto?.categoria?.nombre_cat;
    const base = categoria ? `${nombre} · ${categoria}` : nombre;
    return `${base} — inactivo (solo se conserva)`;
  }

  // --- Diálogos ---

  readonly dialogoConfirmacion =
    viewChild.required<ElementRef<HTMLDialogElement>>('dialogoConfirmacion');
  readonly dialogoEdicion = viewChild.required<ElementRef<HTMLDialogElement>>('dialogoEdicion');

  /** `true` solo para anulación y rechazo: despacho y entrega no piden motivo. */
  readonly exigeMotivo = computed(() => {
    const tipo = this.confirmando();
    return tipo === 'anular' || tipo === 'rechazo';
  });

  /** Título del `<dialog>` de confirmación según el tipo abierto. */
  readonly tituloConfirmacion = computed<string>(() => {
    switch (this.confirmando()) {
      case 'rechazo':
        return 'Rechazar pedido';
      case 'despacho':
        return 'Despachar pedido';
      case 'entrega':
        return 'Confirmar entrega';
      default:
        return 'Anular pedido';
    }
  });

  /** Cuerpo del `<dialog>`: qué consecuencia tiene confirmar cada acción. */
  readonly textoConfirmacion = computed<string>(() => {
    switch (this.confirmando()) {
      case 'despacho':
        return 'Se descontará el stock de la sede y el pedido quedará «Cerrado». Esta operación no se puede deshacer.';
      case 'entrega':
        return 'El pedido quedará «Entregado» para el Solicitante. Su estado canónico sigue siendo «Cerrado».';
      default:
        return 'El pedido pasará al estado «Anulado», que es terminal. El motivo queda registrado en el historial para trazabilidad.';
    }
  });

  /** Texto del botón de envío del diálogo, también deshabilitado en vuelo. */
  readonly textoBotonConfirmar = computed<string>(() => {
    if (this.enOperacion()) {
      return 'Procesando…';
    }
    switch (this.confirmando()) {
      case 'rechazo':
        return 'Confirmar rechazo';
      case 'despacho':
        return 'Confirmar despacho';
      case 'entrega':
        return 'Confirmar entrega';
      default:
        return 'Confirmar anulación';
    }
  });

  constructor() {
    // El `<dialog>` nativo da foco atrapado, `Esc` y fondo atenuado sin código de
    // foco propio (mismo patrón que el modal del tablero). Los diálogos viven
    // siempre en el DOM; estas señales solo abren/cierran.
    effect(() => {
      const tipo = this.confirmando();
      const nativo = this.dialogoConfirmacion().nativeElement;
      if (tipo !== null && !nativo.open) {
        nativo.showModal();
      }
      if (tipo === null && nativo.open) {
        nativo.close();
      }
    });
    effect(() => {
      const abierto = this.editando();
      const nativo = this.dialogoEdicion().nativeElement;
      if (abierto && !nativo.open) {
        nativo.showModal();
      }
      if (!abierto && nativo.open) {
        nativo.close();
      }
    });

    // La ruta `tickets/:ticketId` fija el id; cada cambio de parámetro recarga.
    this.route.paramMap.subscribe((parametros) => {
      const crudo = parametros.get('ticketId');
      const numero = crudo === null ? Number.NaN : Number(crudo);
      this.ticketId.set(Number.isNaN(numero) ? null : numero);
      this.cargar();
    });
  }

  // --- Carga ---

  /** Carga inicial y visible: detalle + historial + catálogos (los catálogos solo si faltan). */
  private cargar(): void {
    if (this.ticketId() === null) {
      this.cargando.set(false);
      this.errorCarga.set('El identificador del pedido no es válido.');
      return;
    }
    this.cargando.set(true);
    this.errorCarga.set(null);
    this.errorAccion.set(null);
    this.mensajeExito.set(null);

    forkJoin({
      detalle: this.servicioTickets.obtenerDetalleTicket(this.ticketId()!),
      historial: this.servicioTickets.obtenerHistorial(this.ticketId()!),
      catalogos:
        this.catalogos() === null
          ? this.servicioTickets.obtenerCatalogos()
          : of(this.catalogos()!),
    }).subscribe({
      next: ({ detalle, historial, catalogos }) => {
        this.catalogos.set(catalogos);
        this.ticket.set(detalle);
        this.historial.set(historial);
        this.cargando.set(false);
      },
      error: (error: HttpErrorResponse) => {
        this.ticket.set(null);
        this.historial.set([]);
        this.cargando.set(false);
        this.errorCarga.set(mensajeDeErrorTickets(error));
      },
    });
  }

  /** Reintenta la carga visible tras un error (404 incluido: cambia el id o vuelve). */
  reintentar(): void {
    this.cargar();
  }

  /**
   * Reconsulta silenciosa de detalle e historial: la verdad del servidor tras
   * una mutación aceptada o rechazada (AC-24), sin esconder la vista tras un
   * spinner global. Si la reconsulta falla, el aviso de la operación ya visible
   * manda y aquí no se duplica el error.
   */
  private reconsultar(): void {
    const id = this.ticketId();
    if (id === null) {
      return;
    }
    forkJoin({
      detalle: this.servicioTickets.obtenerDetalleTicket(id),
      historial: this.servicioTickets.obtenerHistorial(id),
    }).subscribe({
      next: ({ detalle, historial }) => {
        this.ticket.set(detalle);
        this.historial.set(historial);
      },
      error: () => {
        /* silencioso: el error de la operación ya está publicado */
      },
    });
  }

  // --- Aprobación (AC-32: un clic, sin motivo ni diálogo) ---

  /**
   * Aprueba el pedido: `POST /tickets/{id}/aprobacion`. No pide motivo ni abre
   * diálogo y el destino es siempre `EnCurso` (D-15). Al 200 se reconsulta y el
   * estado y la etiqueta se actualizan; un 409/403/404 se anuncia y reconsulta.
   */
  aprobar(): void {
    if (this.enOperacion() || this.ticketId() === null || !this.acciones().aprobar) {
      return;
    }
    this.limpiarAvisos();
    this.enOperacion.set(true);
    this.servicioTickets.aprobarTicket(this.ticketId()!).subscribe({
      next: () => this.terminarOperacion('Pedido aprobado.'),
      error: (error: HttpErrorResponse) => this.fallarOperacion(error),
    });
  }

  // --- Despacho y confirmación de entrega (diálogo sin motivo) ---

  solicitarDespacho(): void {
    if (this.enOperacion() || !this.acciones().despachar) {
      return;
    }
    this.limpiarAvisos();
    this.confirmando.set('despacho');
  }

  solicitarConfirmacionEntrega(): void {
    if (this.enOperacion() || !this.acciones().confirmarEntrega) {
      return;
    }
    this.limpiarAvisos();
    this.confirmando.set('entrega');
  }

  // --- Anulación y rechazo (confirmación con motivo obligatorio) ---

  solicitarAnulacion(): void {
    if (this.enOperacion() || !this.acciones().anular) {
      return;
    }
    this.limpiarAvisos();
    this.motivoForm.reset({ motivo: '' });
    this.confirmando.set('anular');
  }

  solicitarRechazo(): void {
    if (this.enOperacion() || !this.acciones().rechazar) {
      return;
    }
    this.limpiarAvisos();
    this.motivoForm.reset({ motivo: '' });
    this.confirmando.set('rechazo');
  }

  cancelarConfirmacion(): void {
    if (this.enOperacion()) {
      return;
    }
    this.confirmando.set(null);
  }

  /**
   * Envía la confirmación abierta. El motivo solo se exige —y solo se envía—
   * para anulación y rechazo; el despacho lleva el `usuario_id` de la sesión y
   * la entrega no lleva cuerpo (D-19/D-25).
   */
  confirmar(): void {
    const tipo = this.confirmando();
    if (tipo === null || this.enOperacion() || this.ticketId() === null) {
      return;
    }
    const ticketId = this.ticketId()!;

    if (tipo === 'anular' || tipo === 'rechazo') {
      const motivo = this.motivoForm.controls.motivo.value.trim();
      if (motivo === '') {
        this.motivoForm.controls.motivo.markAsTouched();
        return;
      }
      this.limpiarAvisos();
      this.enOperacion.set(true);
      const peticion =
        tipo === 'anular'
          ? this.servicioTickets.anularTicket(ticketId, motivo)
          : this.servicioTickets.rechazarTicket(ticketId, motivo);
      peticion.subscribe({
        next: () => {
          this.confirmando.set(null);
          this.terminarOperacion(tipo === 'anular' ? 'Pedido anulado.' : 'Pedido rechazado.');
        },
        error: (error: HttpErrorResponse) => this.fallarOperacion(error),
      });
      return;
    }

    if (tipo === 'despacho') {
      const identidad = this.autenticacion.identidad();
      if (identidad === null) {
        this.confirmando.set(null);
        this.errorAccion.set('Tu sesión no está disponible. Vuelve a iniciar sesión.');
        return;
      }
      this.limpiarAvisos();
      this.enOperacion.set(true);
      this.servicioTickets.despacharTicket(ticketId, identidad.usuario_id).subscribe({
        next: () => {
          this.confirmando.set(null);
          this.terminarOperacion('Pedido despachado.');
        },
        error: (error: HttpErrorResponse) => {
          // Sin motivo que corregir: el aviso queda en la página y el refresco
          // retira la acción si ya no aplica (AC-34).
          this.confirmando.set(null);
          this.fallarOperacion(error);
        },
      });
      return;
    }

    this.limpiarAvisos();
    this.enOperacion.set(true);
    this.servicioTickets.confirmarEntrega(ticketId).subscribe({
      next: () => {
        this.confirmando.set(null);
        this.terminarOperacion('Entrega confirmada.');
      },
      error: (error: HttpErrorResponse) => {
        this.confirmando.set(null);
        this.fallarOperacion(error);
      },
    });
  }

  // --- Edición en Pendiente (PUT) ---

  /** Abre el formulario de edición precargado con el ticket actual (D-9). */
  iniciarEdicion(): void {
    const ticket = this.ticket();
    if (ticket === null || this.enOperacion() || !this.acciones().editar) {
      return;
    }
    this.limpiarAvisos();
    this.formularioEdicion.reset({
      asunto: ticket.asunto,
      descripcion: ticket.descripcion ?? '',
      prioridad_id: ticket.prioridad_id,
    });
    this.detallesEdicion.clear();
    for (const detalle of ticket.detalles) {
      this.detallesEdicion.push(
        this.fb.group({
          producto_id: [detalle.producto_id as number | null, Validators.required],
          cantidad_solicitada: [
            detalle.cantidad_solicitada,
            [Validators.required, Validators.min(1)],
          ],
        }),
      );
    }
    if (this.detallesEdicion.length === 0) {
      // Un ticket sin ítems no puede editarse en el backend (422: al menos un
      // detalle); se ofrece una fila vacía para agregar el primero.
      this.detallesEdicion.push(this.crearFilaEdicion());
    }
    this.editando.set(true);
  }

  cancelarEdicion(): void {
    if (this.enOperacion()) {
      return;
    }
    this.editando.set(false);
  }

  /** Envía la edición completa (`PUT`): cabecera + reemplazo del conjunto de ítems. */
  guardarEdicion(): void {
    if (this.enOperacion() || this.ticketId() === null) {
      return;
    }
    if (this.formularioEdicion.invalid) {
      this.formularioEdicion.markAllAsTouched();
      return;
    }
    const valores = this.formularioEdicion.getRawValue();
    const cuerpo: TicketEditar = {
      asunto: valores.asunto.trim(),
      descripcion: valores.descripcion.trim() === '' ? null : valores.descripcion.trim(),
      prioridad_id: valores.prioridad_id!,
      detalles: this.combinarDetallesEdicion(),
    };
    this.limpiarAvisos();
    this.enOperacion.set(true);
    this.servicioTickets.editarTicket(this.ticketId()!, cuerpo).subscribe({
      next: () => {
        this.editando.set(false);
        this.terminarOperacion('Pedido editado.');
      },
      error: (error: HttpErrorResponse) => this.fallarOperacion(error),
    });
  }

  // --- Ciclo común de las mutaciones ---

  /** Éxito: cierra modales, publica el aviso y reconsulta detalle + historial. */
  private terminarOperacion(mensaje: string): void {
    this.mensajeExito.set(mensaje);
    this.reconsultar();
    this.enOperacion.set(false);
  }

  /** Rechazo del servidor (404/409/422/…): mensaje accesible y reconsulta. */
  private fallarOperacion(error: HttpErrorResponse): void {
    this.errorAccion.set(mensajeDeErrorTickets(error));
    this.reconsultar();
    this.enOperacion.set(false);
  }

  private limpiarAvisos(): void {
    this.errorAccion.set(null);
    this.mensajeExito.set(null);
  }

  // --- Auxiliares de presentación ---

  private nombreDeEstado(estadoId: number): string | null {
    return this.estados().find((estado) => estado.estado_id === estadoId)?.nombre ?? null;
  }

  /** Actor de la fila: nombre y apellido resueltos, con degradación a `#id`. */
  private actorDeFila(fila: HistorialTransicion): string {
    const nombre = this.nombrePersona(fila.usuario_nombre, fila.usuario_apellido);
    return nombre !== '' ? nombre : `Usuario #${fila.usuario_id}`;
  }

  /** Gestor del read model: «Apellido, Nombre» o el texto de ausencia. */
  private nombreGestor(gestor: GestorProceso | null): string {
    if (gestor === null) {
      return 'Sin gestión registrada';
    }
    const nombre = this.nombrePersona(gestor.nombre, gestor.apellido);
    return nombre !== '' ? nombre : 'Sin gestión registrada';
  }

  /** «Apellido, Nombre» con las partes presentes; cadena vacía si no hay ninguna. */
  private nombrePersona(nombre: string | null | undefined, apellido: string | null | undefined): string {
    return [apellido, nombre]
      .filter((parte): parte is string => typeof parte === 'string' && parte !== '')
      .join(', ');
  }
}

/** Normaliza para comparar nombres de estado: sin acentos, minúsculas, sin sobrantes. */
function normalizar(texto: string): string {
  return texto
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .trim();
}
