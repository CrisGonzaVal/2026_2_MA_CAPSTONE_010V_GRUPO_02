import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  OnDestroy,
  computed,
  effect,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { finalize, forkJoin } from 'rxjs';

import { puedeCrearTicket } from '../../core/auth/roles';
import { AutenticacionService } from '../../core/services/auth.service';
import { TiempoRealService } from '../../core/services/tiempo-real.service';
import {
  CatalogosTicket,
  DetalleTicketCrear,
  GestorProceso,
  Prioridad,
  ProductoCatalogo,
  Solicitante,
  Ticket,
  TicketCrear,
} from '../../shared/interfaces';
import { etiquetaEstado } from '../../shared/utils/etiqueta-estado';
import { crearRefrescoAgrupado } from '../../shared/utils/refresco-agrupado';
import type { DetalleError422 } from '../../shared/utils/validacion-http';
import {
  detallesDeValidacion,
  mensajeDeCampo,
  mensajeDeDetalle,
} from '../../shared/utils/validacion-http';
import { TicketService } from './services/ticket.service';

/**
 * Encabezado de una columna del tablero.
 *
 * Desde la ampliación 25/Nov/2026 (D-24/AC-41), una columna puede agrupar más
 * de un estado del catálogo: «Terminados» reúne `Cerrado` y `Anulado`. Por eso
 * ya no hay un único `estado_id`; `clave` identifica la columna para `track` y
 * `estado_ids` declara los estados que agrupa.
 */
interface ColumnaKanban {
  /** Clave estable para `track`: nombre canónico o «Terminados». */
  clave: string;
  /** Estados del catálogo que la columna agrupa, en el orden del catálogo. */
  estado_ids: number[];
  /** Nombre canónico de la columna; «Terminados» no es un estado canónico. */
  estado: string;
  /** Feature 021 (V-3): rotulo visible, con las palabras separadas. */
  etiqueta: string;
  tarjetas: TarjetaKanban[];
}

/**
 * Tarjeta con los ids ya resueltos a texto. El template no resuelve ids: todo
 * lo que necesita para pintar (nombre de prioridad, solicitante, clases) sale
 * del `computed` de columnas, que es el unico lugar que conoce los catalogos.
 *
 * Es **informativa** (Feature 013, D-14): no resuelve controles de mutacion.
 * La tarjeta entera es un enlace al detalle en el template; el gating por
 * estado y rol vive en esa vista, no aqui.
 *
 * Desde la ampliación 25/Nov/2026 (§9.8) también presenta el read model de
 * proceso: etiqueta derivada, frase corta y los dos responsables del historial.
 */
interface TarjetaKanban {
  ticket: Ticket;
  asunto: string;
  prioridad: string;
  clasePrioridad: string;
  solicitante: string;
  fechaCreacion: string;
  fechaCierre: string | null;
  /** Nombre canónico del estado resuelto desde el catálogo (AC-41). */
  estadoCanonico: string;
  /** Etiqueta de proceso del backend; si falta, el nombre canónico (AC-37). */
  etiquetaProceso: string;
  /** Frase corta derivada por el servidor; vacía si no vino (AC-37). */
  explicacionProceso: string;
  /** Último Bodeguero («Apellido, Nombre») o «Sin gestión registrada». */
  gestorBodeguero: string;
  /** `false` cuando no hay fila de ese rol: la tarjeta pinta `—` accesible. */
  tieneGestorBodeguero: boolean;
  /** Último Administrador («Apellido, Nombre») o «Sin gestión registrada». */
  gestorAdministrador: string;
  tieneGestorAdministrador: boolean;
  /** Nombre accesible del enlace: estado, etapa y responsables (AC-41). */
  descripcionAccesible: string;
}

const CLASES_PRIO: Record<string, string> = {
  ALTA: 'text-rose-600 bg-rose-50',
  MEDIA: 'text-blue-600 bg-blue-50',
  BAJA: 'text-amber-600 bg-amber-50',
};

const CLASE_PRIORIDAD_NEUTRA = 'text-slate-600 bg-slate-100';

/**
 * Nombre canonico del estado terminal que un ticket nuevo no puede elegir
 * (Feature 013, D-11). Se compara normalizado (sin acentos, minusculas), con
 * la misma regla del backend y del resto del tablero: sin ids fijos ni
 * posiciones, porque el catalogo es mutable y replicado por tenant.
 */
const NOMBRE_ESTADO_ANULADO = 'anulado';

/**
 * Nombre canonico del estado terminal positivo (ampliación 25/Nov/2026,
 * D-24): se agrupa con `Anulado` en la columna «Terminados», resuelto por
 * nombre normalizado y nunca por id.
 */
const NOMBRE_ESTADO_CERRADO = 'cerrado';

/** Título de la columna terminal agrupada (D-24); no es un estado canónico. */
const NOMBRE_COLUMNA_TERMINADOS = 'Terminados';

/** Enmienda 27/Nov/2026 (AC-28): lecturas de periodo del tablero. */
export type PeriodoTablero = 'todo' | 'hoy' | 'semana' | 'mes' | 'anio';

/** Enmienda 27/Nov/2026 (AC-29): orden de las tarjetas dentro de cada columna. */
export type OrdenTablero = 'recientes' | 'antiguos';

const PERIODOS_TABLERO: readonly PeriodoTablero[] = [
  'todo',
  'hoy',
  'semana',
  'mes',
  'anio',
];

const ORDENES_TABLERO: readonly OrdenTablero[] = ['recientes', 'antiguos'];

/**
 * Inicio local (00:00:00.000) del periodo calendario, construido por campos y
 * sin restar duraciones. `semana` usa lunes como primer día: retrocede
 * `(getDay() + 6) % 7` días desde la medianoche de hoy.
 */
export function inicioDePeriodo(
  periodo: PeriodoTablero,
  ahora: Date
): Date | null {
  if (periodo === 'todo') {
    return null;
  }

  const anio = ahora.getFullYear();
  const mes = ahora.getMonth();
  const dia = ahora.getDate();

  if (periodo === 'hoy') {
    return new Date(anio, mes, dia);
  }
  if (periodo === 'semana') {
    const diasDesdeLunes = (ahora.getDay() + 6) % 7;
    return new Date(anio, mes, dia - diasDesdeLunes);
  }
  if (periodo === 'mes') {
    return new Date(anio, mes, 1);
  }
  return new Date(anio, 0, 1);
}

/** Texto de ausencia del read model de responsables (D-23/AC-40). */
const SIN_GESTION_REGISTRADA = 'Sin gestión registrada';

/**
 * Nombre canonico del estado inicial del alta (enmienda 26/Nov/2026,
 * D-35/AC-51): todo ticket nuevo nace en `EnRevision`, resuelto por nombre
 * normalizado y no por la primera entrada del catalogo.
 */
const NOMBRE_ESTADO_EN_REVISION = 'enrevision';

/**
 * Nombre canonico de la prioridad predeterminada del alta (enmienda AC-27):
 * `Media` viene preseleccionada, pero el usuario puede cambiarla.
 */
const NOMBRE_PRIORIDAD_MEDIA = 'media';

/**
 * Tablero Kanban de **solo lectura**, mas el modal de alta (Feature 013,
 * D-14/AC-24): los botones avanzar/retroceder de la Feature 004 quedaron
 * derogados en su capa de UI y toda mutacion del ciclo de vida se opera en la
 * vista de detalle. Cada tarjeta completa es un enlace que navega a
 * `tickets/:ticketId`.
 *
 * **El tablero es real**: se arma con `GET /tickets/catalogos` (estados ya
 * ordenados por `estado_id`) y `GET /tickets/`, disparados al construir el
 * componente. Las columnas son las operativas del catálogo (`EnRevision`,
 * `EnCurso`) más una terminal agrupada, «Terminados», que reúne `Cerrado` y
 * `Anulado` (D-24/AC-41); las vacías se conservan
 * (AC-1). Dentro, el orden por `fecha_creacion` y `ticket_id` lo elige el
 * selector `orden` («Más recientes» por defecto, AC-2/AC-29); la prioridad, la
 * búsqueda y el periodo se filtran antes de agrupar. Ningun id de estado se
 * codifica a mano: el nombre sale del catalogo.
 *
 * El modal comparte el catalogo que el tablero ya cargo: `abrirModal` no vuelve
 * a pedirlo si esta disponible. Como el tablero no muta nada, tampoco se
 * reconsulta al cambiar el estado de un ticket: las dos peticiones del
 * arranque son toda la red de la vista (sin N+1). El alta inserta la respuesta
 * `201` de `POST /tickets/` en `tickets()` y el `computed` de columnas la
 * filtra y ordena en cliente, sin recargar el listado (AC-8).
 */
@Component({
  selector: 'app-tickets',
  standalone: true,
  imports: [ReactiveFormsModule, DatePipe, RouterLink],
  templateUrl: './tickets.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class TicketsComponent implements OnDestroy {
  // --- Estado del tablero ---

  /** Tickets reales, tal como los devuelve `GET /tickets/` (orden ya explicito). */
  readonly tickets = signal<Ticket[]>([]);

  readonly cargandoTablero = signal(false);
  readonly errorTablero = signal<string | null>(null);

  /** Filtro de prioridad del tablero. `null` = "todas" (valor por defecto, AC-6). */
  readonly filtroPrioridad = signal<number | null>(null);

  /** Texto de busqueda por asunto. Vacio o solo espacios = sin filtro (AC-7). */
  readonly busqueda = signal('');

  /** Periodo calendario sobre `fecha_creacion`; `todo` = sin recorte (AC-28). */
  readonly filtroPeriodo = signal<PeriodoTablero>('todo');

  /** Orden dentro de cada columna; `recientes` conserva AC-2 por defecto (AC-29). */
  readonly orden = signal<OrdenTablero>('recientes');

  /** Hay algun filtro activo: distingue el vacio "por filtros" del vacio real (AC-5). */
  readonly hayFiltros = computed(
    () =>
      this.filtroPeriodo() !== 'todo' ||
      this.filtroPrioridad() !== null ||
      this.busqueda().trim() !== ''
  );

  /**
   * Columnas del tablero: las operativas del catalogo en su orden (`EnRevision`,
   * `EnCurso`) y una unica terminal agrupada, «Terminados», que reune `Cerrado`
   * y `Anulado` (D-24/AC-41). La columna
   * terminal aparece en la posicion del primero de esos estados y no se
   * inventa si el catalogo no contiene ninguno. Las columnas vacias se
   * conservan (AC-1). Los filtros de prioridad, busqueda y periodo se aplican
   * antes de agrupar; despues, las tarjetas de cada `estado_ids` se ordenan con
   * `orden`: `recientes` = `fecha_creacion` DESC y `ticket_id` DESC (AC-2);
   * `antiguos` = ASC y `ticket_id` ASC. Es `computed` y no `signal`: todo sale
   * de `estados()`, `tickets()` y las señales de filtro, no hay estado propio
   * que mantener.
   *
   * Los filtros se aplican **antes de agrupar** (plan §3.5): es un filtrado de
   * cliente sobre el conjunto ya cargado, no una consulta nueva. Con eso los
   * contadores de cada columna (`tarjetas.length`) quedan ya "despues de
   * filtrar" (AC-3) sin una señal de contador aparte. Los tres predicados se
   * combinan en interseccion (AC-7, D-6).
   */
  readonly columnas = computed<ColumnaKanban[]>(() => {
    const prioridad = this.filtroPrioridad();
    const busqueda = this.normalizar(this.busqueda());
    const inicio = inicioDePeriodo(this.filtroPeriodo(), new Date());
    const orden = this.orden();

    const filtrados = this.tickets().filter(
      (ticket) =>
        (prioridad === null || ticket.prioridad_id === prioridad) &&
        (busqueda === '' || this.normalizar(ticket.asunto).includes(busqueda)) &&
        (inicio === null ||
          new Date(ticket.fecha_creacion).getTime() >= inicio.getTime())
    );

    const comparar =
      orden === 'recientes'
        ? (a: Ticket, b: Ticket) =>
            Date.parse(b.fecha_creacion) - Date.parse(a.fecha_creacion) ||
            b.ticket_id - a.ticket_id
        : (a: Ticket, b: Ticket) =>
            Date.parse(a.fecha_creacion) - Date.parse(b.fecha_creacion) ||
            a.ticket_id - b.ticket_id;

    const grupos: ColumnaKanban[] = [];
    let terminados: ColumnaKanban | null = null;

    for (const estado of this.estados()) {
      const nombre = this.normalizar(estado.nombre);
      const esTerminal =
        nombre === NOMBRE_ESTADO_CERRADO || nombre === NOMBRE_ESTADO_ANULADO;

      if (esTerminal) {
        if (terminados === null) {
          terminados = {
            clave: NOMBRE_COLUMNA_TERMINADOS,
            estado_ids: [],
            estado: NOMBRE_COLUMNA_TERMINADOS,
            etiqueta: NOMBRE_COLUMNA_TERMINADOS,
            tarjetas: [],
          };
          grupos.push(terminados);
        }
        terminados.estado_ids.push(estado.estado_id);
        continue;
      }

      grupos.push({
        clave: estado.nombre,
        estado_ids: [estado.estado_id],
        estado: estado.nombre,
        etiqueta: etiquetaEstado(estado.nombre),
        tarjetas: [],
      });
    }

    for (const grupo of grupos) {
      grupo.tarjetas = filtrados
        .filter((ticket) => grupo.estado_ids.includes(ticket.estado_id))
        .sort(comparar)
        .map((ticket) => this.resolverTarjeta(ticket));
    }

    return grupos;
  });

  /**
   * Resuelve ids contra los catalogos para que el template no conozca ninguno
   * ni calcule indices. Solo datos de presentación: la tarjeta no ofrece
   * controles de mutación (D-14).
   *
   * El read model de proceso (§9.8) llega ya derivado del backend; aquí solo se
   * resuelve el nombre del estado canónico para el `aria-label` y se aplican
   * los fallbacks de presentación: etiqueta vacía → nombre canónico; gestor
   * ausente → «Sin gestión registrada».
   */
  private resolverTarjeta(ticket: Ticket): TarjetaKanban {
    const prioridad = this.prioridades().find((p) => p.prioridad_id === ticket.prioridad_id);
    const solicitante = this.solicitantes().find((s) => s.usuario_id === ticket.usuario_id);
    const nombrePrioridad = prioridad?.nombre ?? `Prioridad #${ticket.prioridad_id}`;
    const estadoCanonico = this.nombreEstado(ticket.estado_id);
    const etiquetaProceso = ticket.etiqueta_proceso?.trim()
      ? ticket.etiqueta_proceso
      : etiquetaEstado(estadoCanonico);
    const bodeguero = this.resolverGestor(ticket.gestionado_por_bodeguero ?? null);
    const administrador = this.resolverGestor(
      ticket.gestionado_por_administrador ?? null
    );

    return {
      ticket,
      asunto: ticket.asunto,
      prioridad: nombrePrioridad,
      clasePrioridad: this.clasePrioridad(nombrePrioridad),
      solicitante: solicitante
        ? `${solicitante.apellido}, ${solicitante.nombre} · ${solicitante.departamento_nombre}`
        : `Usuario #${ticket.usuario_id}`,
      fechaCreacion: ticket.fecha_creacion,
      fechaCierre: ticket.fecha_cierre,
      estadoCanonico,
      etiquetaProceso,
      explicacionProceso: ticket.explicacion_proceso ?? '',
      gestorBodeguero: bodeguero.nombre,
      tieneGestorBodeguero: bodeguero.registrado,
      gestorAdministrador: administrador.nombre,
      tieneGestorAdministrador: administrador.registrado,
      descripcionAccesible: `Pedido #${ticket.ticket_id}: ${ticket.asunto}. Estado: ${estadoCanonico}. Etapa del proceso: ${etiquetaProceso}. Último Bodeguero: ${bodeguero.nombre}. Último Administrador: ${administrador.nombre}.`,
    };
  }

  /** Nombre canónico del estado por su id; degrada a `Estado #id` si no está. */
  private nombreEstado(estadoId: number): string {
    return (
      this.estados().find((estado) => estado.estado_id === estadoId)?.nombre ??
      `Estado #${estadoId}`
    );
  }

  /**
   * Resuelve un gestor del read model a «Apellido, Nombre», con el texto de
   * ausencia cuando no hay fila (D-23/AC-40). El flag `registrado` permite que
   * la tarjeta pinte `—` visible sin perder el texto accesible.
   */
  private resolverGestor(gestor: GestorProceso | null): {
    nombre: string;
    registrado: boolean;
  } {
    if (gestor === null) {
      return { nombre: SIN_GESTION_REGISTRADA, registrado: false };
    }
    const nombre = [gestor.apellido, gestor.nombre]
      .filter((parte) => parte !== '')
      .join(', ');
    return nombre === ''
      ? { nombre: SIN_GESTION_REGISTRADA, registrado: false }
      : { nombre, registrado: true };
  }

  /**
   * Clase Tailwind de la prioridad por su nombre real, tolerante a mayusculas;
   * si el catalogo trae un nombre inesperado cae en una clase neutra en vez de
   * pintar `undefined`.
   */
  private clasePrioridad(nombre: string): string {
    return CLASES_PRIO[nombre.toUpperCase()] ?? CLASE_PRIORIDAD_NEUTRA;
  }

  // --- Filtros ---

  /** Fija el filtro de prioridad desde el `<select>`: `''` es "todas". */
  cambiarPrioridad(valor: string) {
    this.filtroPrioridad.set(valor === '' ? null : Number(valor));
  }

  /** Fija el periodo desde el `<select>`; ignora valores fuera del contrato. */
  cambiarPeriodo(valor: string) {
    const periodo = PERIODOS_TABLERO.find((opcion) => opcion === valor);
    if (periodo !== undefined) {
      this.filtroPeriodo.set(periodo);
    }
  }

  /** Fija el orden desde el `<select>`; ignora valores fuera del contrato. */
  cambiarOrden(valor: string) {
    const orden = ORDENES_TABLERO.find((opcion) => opcion === valor);
    if (orden !== undefined) {
      this.orden.set(orden);
    }
  }

  /** Actualiza el texto de busqueda desde el `<input>`. */
  actualizarBusqueda(valor: string) {
    this.busqueda.set(valor);
  }

  /**
   * Normaliza para comparar: sin acentos, minusculas y sin espacios sobrantes.
   *
   * Se usa tanto para el asunto como para la consulta. Al no haber `LIKE` en
   * SQL, `%` y `_` son caracteres literales por construccion (D-6, AC-7). Sobre
   * la consulta, el `.trim()` es lo que implementa "vacio = sin filtro".
   */
  private normalizar(texto: string): string {
    return texto
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .toLowerCase()
      .trim();
  }

  private readonly servicioTickets = inject(TicketService);
  private readonly autenticacion = inject(AutenticacionService);
  private readonly fb = inject(NonNullableFormBuilder);
  private readonly servicioTiempoReal = inject(TiempoRealService);

  /**
   * Refresco del tablero ante invalidaciones del hub (Feature 028, T17). Se
   * agrupa la ráfaga y solo relee la lista, en silencio: no enciende
   * `cargandoTablero` ni toca filtros, orden ni búsqueda (spec §5.4).
   */
  private readonly refrescoTablero = crearRefrescoAgrupado(() =>
    this.cargarTablero({ silencioso: true }),
  );

  /** Los dos frames que invalidan el tablero: pedidos e inventario. */
  private readonly cancelarSuscripcionCambios = this.servicioTiempoReal.alCambio(
    ['pedidos', 'inventario'],
    () => this.refrescoTablero.solicitar(),
  );

  /** `listo`, reapertura y vuelta a foco: resincroniza una vez por ventana. */
  private readonly cancelarSuscripcionResincronizacion =
    this.servicioTiempoReal.alResincronizar(() =>
      this.refrescoTablero.solicitar(),
    );

  // --- Estado del modal ---

  /**
   * Identidad de sesión (Feature 003, AC-34): el alta no elige autor. El
   * servidor atribuye el ticket a esta misma identidad; aquí solo se presenta
   * como dato informativo de solo lectura. El departamento sí está disponible
   * en `/auth/me` desde la enmienda AC-22 de la Feature 008 (20/Nov/2026), pero
   * este bloque informativo conserva nombre, apellido y correo: el servidor
   * deriva el departamento del ticket y el modal no lo edita ni lo consulta por
   * separado.
   */
  readonly identidad = this.autenticacion.identidad;

  /**
   * Espejo de la matriz tras la enmienda de la 007 (26/Nov/2026): solo el
   * Solicitante ve el botón de alta. La API es la frontera de seguridad y
   * responde 403 a Administrador, Bodeguero y Superadmin.
   */
  readonly puedeCrearPedido = computed(() =>
    puedeCrearTicket(this.identidad()?.rol ?? null),
  );

  readonly modalAbierto = signal(false);
  readonly catalogos = signal<CatalogosTicket | null>(null);
  readonly cargandoCatalogos = signal(false);
  readonly guardando = signal(false);
  readonly ticketCreado = signal<number | null>(null);
  readonly errorCatalogos = signal<string | null>(null);
  readonly errorGuardado = signal<string | null>(null);
  readonly detalleErrores = signal<DetalleError422[]>([]);

  /**
   * El `<dialog>` nativo, no un overlay de Tailwind.
   *
   * `showModal()` da el foco atrapado, `Esc` para cerrar y el fondo atenuado
   * sin escribir una sola linea de codigo de foco. Se accede por `viewChild`
   * y no por `@ViewChild` porque el componente es standalone y no usa decoradores
   * de clase.
   */
  readonly dialogo = viewChild.required<ElementRef<HTMLDialogElement>>('dialogo');

  constructor() {
    // El `effect` corre **después** del render, que es justo lo que necesita:
    // con `@if (modalAbierto())` el `<dialog>` no existe en el DOM hasta que
    // Angular lo crea, asi que llamar a `showModal()` desde el `(click)` del
    // boton encontraria `undefined`. La guarda `!nativo.open` evita el
    // `InvalidStateError` de abrir un dialogo que ya esta abierto.
    effect(() => {
      const abierto = this.modalAbierto();
      const nativo = this.dialogo().nativeElement;
      if (abierto && !nativo.open) {
        nativo.showModal();
      }
      if (!abierto && nativo.open) {
        nativo.close();
      }
    });

    // El tablero se carga al construir: catalogos de estados + tickets.
    void this.cargarTablero();
  }

  /**
   * Cancela las suscripciones al hub y el agrupador al destruir la vista. Sin
   * esto, un frame tardío podría disparar una relectura sobre un componente
   * ya destruido.
   */
  ngOnDestroy(): void {
    this.cancelarSuscripcionCambios();
    this.cancelarSuscripcionResincronizacion();
    this.refrescoTablero.cancelar();
  }

  // --- Formulario ---

  /**
   * `NonNullableFormBuilder` para que los controles nazcan con valor y no con
   * `null`: la cantidad arranca en 1, que es valida, en vez de en 0, que por
   * `gt=0` seria un 422 garantizado en el primer envio.
   *
   * Los validadores del cliente son espejo de `TicketCrear` en el backend. El
   * servidor sigue siendo la fuente de verdad: esto solo evita el viaje de ida
   * y vuelta para descubrir un error que ya se conocia.
   *
   * No hay control de autor: la identidad de sesion atribuye el alta (AC-34).
   */
  readonly formulario = this.fb.group({
    prioridad_id: [null as number | null, Validators.required],
    estado_id: [null as number | null, Validators.required],
    asunto: ['', [Validators.required, Validators.minLength(3), Validators.maxLength(150)]],
    descripcion: ['', Validators.maxLength(500)],
    detalles: this.fb.array([this.crearFilaDetalle()]),
  });

  readonly detalles = this.formulario.controls.detalles;

  crearFilaDetalle() {
    return this.fb.group({
      producto_id: [null as number | null, Validators.required],
      cantidad_solicitada: [1, [Validators.required, Validators.min(1)]],
    });
  }

  // --- Catálogos ---

  readonly prioridades = computed<Prioridad[]>(() => this.catalogos()?.prioridades ?? []);
  readonly estados = computed(() => this.catalogos()?.estados ?? []);
  /**
   * Productos que el alta puede ofrecer en sus selectores.
   *
   * `GET /tickets/catalogos` ya excluye inactivos y productos de categoría
   * inactiva (Feature 014, D-7/AC-4), así que normalmente esto es el catálogo
   * tal cual. El filtro por `activo` es la salvaguarda de UI: si una regresión
   * llegara a incluirlos, no se ofrecen para una línea nueva (AC-9).
   */
  readonly productos = computed<ProductoCatalogo[]>(() =>
    (this.catalogos()?.productos ?? []).filter((producto) => producto.activo !== false)
  );
  /**
   * Catálogo de solicitantes conservado como dato de **lectura**: resuelve el
   * autor de cada tarjeta del tablero (AC-35). El alta ya no lo usa como
   * selector; la autoría sale de la identidad de sesión.
   */
  readonly solicitantes = computed<Solicitante[]>(() => this.catalogos()?.solicitantes ?? []);

  /** Etiqueta de un producto en el desplegable: nombre, unidad y categoria. */
  etiquetaProducto(producto: ProductoCatalogo): string {
    const unidad = producto.unidad_medida ? ` (${producto.unidad_medida})` : '';
    return `${producto.nombre}${unidad} · ${producto.categoria_nombre}`;
  }

  /**
   * Estado inicial del alta: `EnRevision` resuelto por **nombre canonico**
   * (enmienda 26/Nov/2026, D-35/AC-51), no la primera entrada del catalogo. Un
   * catalogo degenerado no puede cambiar el estado de nacimiento; sin
   * `EnRevision` el formulario queda invalido (fail-closed, espejo del 409 del
   * backend).
   */
  readonly estadoEnRevision = computed(
    () =>
      this.estados().find(
        (estado) => this.normalizar(estado.nombre) === NOMBRE_ESTADO_EN_REVISION
      ) ?? null
  );

  /** Nombre visible del estado inicial en el campo fijo del modal (V-3). */
  readonly nombreEstadoInicial = computed(() =>
    etiquetaEstado(this.estadoEnRevision()?.nombre ?? 'EnRevision')
  );

  estadoInicial(): number | null {
    return this.estadoEnRevision()?.estado_id ?? null;
  }

  /**
   * Prioridad predeterminada del alta: `Media` por nombre canonico (enmienda
   * AC-27). Sigue siendo editable; sin `Media` en el catalogo el desplegable
   * conserva su marcador y la validacion obliga a elegir.
   */
  readonly prioridadMedia = computed(
    () =>
      this.prioridades().find(
        (prioridad) => this.normalizar(prioridad.nombre) === NOMBRE_PRIORIDAD_MEDIA
      ) ?? null
  );

  prioridadInicial(): number | null {
    return this.prioridadMedia()?.prioridad_id ?? null;
  }

  /**
   * Fija los valores por defecto del alta (`EnRevision` y `Media`). Se aplica
   * al cargar los catalogos y despues de cada alta exitosa, para que el
   * formulario no arrastre el ticket anterior.
   */
  private aplicarValoresPorDefecto(): void {
    const estado = this.estadoInicial();
    if (estado !== null) {
      this.formulario.controls.estado_id.setValue(estado);
    }
    const prioridad = this.prioridadInicial();
    if (prioridad !== null) {
      this.formulario.controls.prioridad_id.setValue(prioridad);
    }
  }

  // --- Carga del tablero ---

  /**
   * Carga del tablero. La carga inicial y el reintento manual piden catalogo y
   * tickets, encienden `cargandoTablero` y publican el error visible si algo
   * falla. El refresco silencioso (Feature 028, T17) solo relee la lista
   * —spec §5.4: el tablero repite «Lista de pedidos»—, no toca el estado de
   * carga ni el error global, conserva las tarjetas previas si falla y devuelve
   * una promesa para que el agrupador sepa cuándo terminó.
   */
  private cargarTablero({
    silencioso = false,
  }: { silencioso?: boolean } = {}): Promise<void> {
    if (!silencioso) {
      this.cargandoTablero.set(true);
      this.errorTablero.set(null);
    }

    if (silencioso) {
      return new Promise<void>((resolver) => {
        this.servicioTickets
          .obtenerTickets()
          .pipe(finalize(() => resolver()))
          .subscribe({
            next: (tickets) => {
              // Reemplazo íntegro: si el `201` insertó una tarjeta de forma
              // optimista, el listado del servidor la contiene una sola vez.
              this.tickets.set(tickets);
            },
            // Un fallo del refresco no borra lo ya mostrado, no cierra la vista
            // y no muestra el error global: la siguiente invalidación o la
            // recarga manual convergen (AC-14, §5.4 regla 4).
            error: () => undefined,
          });
      });
    }

    return new Promise<void>((resolver) => {
      forkJoin({
        catalogos: this.servicioTickets.obtenerCatalogos(),
        tickets: this.servicioTickets.obtenerTickets(),
      })
        .pipe(finalize(() => resolver()))
        .subscribe({
          next: ({ catalogos, tickets }) => {
            if (catalogos.estados.length === 0) {
              this.cargandoTablero.set(false);
              this.errorTablero.set(
                'El catálogo de estados está vacío. El tablero no se puede mostrar.'
              );
              return;
            }
            this.catalogos.set(catalogos);
            this.tickets.set(tickets);
            this.aplicarValoresPorDefecto();
            this.cargandoTablero.set(false);
          },
          error: () => {
            this.cargandoTablero.set(false);
            this.errorTablero.set(
              'No se pudo cargar el tablero. Revisa la conexión e inténtalo de nuevo.'
            );
          },
        });
    });
  }

  /** Reintenta la carga del tablero tras un error visible. */
  reintentarTablero() {
    void this.cargarTablero();
  }

  // --- Acciones del modal ---

  abrirModal() {
    this.errorGuardado.set(null);
    this.errorCatalogos.set(null);
    this.detalleErrores.set([]);
    this.ticketCreado.set(null);
    this.modalAbierto.set(true);

    // El tablero ya cargo el catalogo al construir el componente: si esta
    // disponible, abrir el modal no vuelve a pedirlo. Solo se pide cuando el
    // arranque fallo o aun no se completo, para no dejar el formulario vacio.
    if (this.catalogos() !== null) {
      return;
    }

    this.cargandoCatalogos.set(true);
    this.servicioTickets.obtenerCatalogos().subscribe({
      next: (catalogos) => {
        this.catalogos.set(catalogos);
        this.cargandoCatalogos.set(false);
        this.aplicarValoresPorDefecto();
      },
      error: () => {
        this.cargandoCatalogos.set(false);
        this.errorCatalogos.set(
          'No se pudieron cargar las prioridades, estados ni productos. Revisa la conexión e inténtalo de nuevo.'
        );
      },
    });
  }

  /** Cierra el modal. El `effect` se encarga de llamar a `close()`. */
  cerrarModal() {
    this.modalAbierto.set(false);
  }

  agregarDetalle() {
    this.detalles.push(this.crearFilaDetalle());
  }

  /** Con una sola fila no se puede quitar: un ticket sin items es un 422. */
  puedeQuitarDetalle(): boolean {
    return this.detalles.length > 1;
  }

  quitarDetalle(indice: number) {
    if (this.puedeQuitarDetalle()) {
      this.detalles.removeAt(indice);
    }
  }

  /**
   * Suma las cantidades de los productos repetidos antes de enviar.
   *
   * `detalle_ticket` no declara `UNIQUE(ticket_id, producto_id)`, asi que el
   * servidor aceptaria las dos filas. Fusionarlas aqui es corregir un error de
   * uso del formulario, no imponer una regla de negocio: quien use la API
   * directamente puede seguir mandando dos lineas, y el backend las respeta.
   */
  combinarDetalles(): DetalleTicketCrear[] {
    const cantidades = new Map<number, number>();
    for (const detalle of this.detalles.controls) {
      const productoId = detalle.controls.producto_id.value;
      if (productoId === null) {
        continue;
      }
      cantidades.set(productoId, (cantidades.get(productoId) ?? 0) + detalle.controls.cantidad_solicitada.value);
    }
    return [...cantidades].map(([producto_id, cantidad_solicitada]) => ({
      producto_id,
      cantidad_solicitada,
    }));
  }

  // --- Errores ---

  /**
   * Traduce el `detail` de FastAPI a un mensaje por control.
   *
   * `loc` termina en el nombre del campo; para un error de detalle termina en
   * `[..., 'detalles', indice, 'cantidad_solicitada']`, y ese indice se muestra
   * como numero de fila empezando en 1.
   */
  mensajeDe(campo: string): string | null {
    return mensajeDeCampo(this.detalleErrores(), campo);
  }

  mensajeDeDetalle(indice: number): string | null {
    const detalles = this.detalleErrores();
    return (
      mensajeDeDetalle(detalles, indice, 'cantidad_solicitada') ??
      mensajeDeDetalle(detalles, indice, 'producto_id')
    );
  }

  // --- Envío ---

  enviar() {
    this.errorGuardado.set(null);
    this.detalleErrores.set([]);

    if (this.formulario.invalid) {
      this.formulario.markAllAsTouched();
      return;
    }
    if (this.guardando()) {
      return;
    }

    const valor = this.formulario.getRawValue();
    // AC-34: el cuerpo no lleva `usuario_id`. El backend atribuye el alta a la
    // identidad de sesión y resuelve institución, productos y sede con ella.
    const cuerpo: TicketCrear = {
      prioridad_id: valor.prioridad_id!,
      estado_id: valor.estado_id!,
      asunto: valor.asunto,
      descripcion: valor.descripcion === '' ? null : valor.descripcion,
      detalles: this.combinarDetalles(),
    };

    this.guardando.set(true);
    this.servicioTickets.crearTicket(cuerpo).subscribe({
      next: (ticket: Ticket) => {
        this.guardando.set(false);
        this.ticketCreado.set(ticket.ticket_id);
        // AC-8: el ticket creado se refleja en el tablero sin recargar. Nada de
        // filtrar a mano: el `computed` de columnas aplica los filtros activos,
        // asi que un ticket que no los cumpla queda fuera por construccion.
        this.tickets.update((lista) => [ticket, ...lista]);
        this.cerrarModal();
        this.formulario.reset({ asunto: '', descripcion: '' });
        this.aplicarValoresPorDefecto();
        this.detalles.clear();
        this.detalles.push(this.crearFilaDetalle());
      },
      error: (fallo: HttpErrorResponse) => {
        this.guardando.set(false);
        const detalle = (fallo.error as { detail?: unknown } | null)?.detail;

        if (Array.isArray(detalle)) {
          this.detalleErrores.set(detallesDeValidacion(fallo));
          this.errorGuardado.set('Revisa los campos marcados.');
        } else if (typeof detalle === 'string') {
          // Un 404 de referencia (producto borrado entre la carga del catalogo y
          // el envio, por ejemplo). No se mapea a un control: no sabemos cual, y
          // adivinar seria peor que mostrar el mensaje del backend.
          this.errorGuardado.set(detalle);
        } else {
          this.errorGuardado.set('No se pudo crear el pedido. Inténtalo de nuevo.');
        }
      },
    });
  }
}
