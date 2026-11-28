import { HttpErrorResponse } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  OnInit,
  computed,
  inject,
  signal,
} from '@angular/core';
import { takeUntilDestroyed, toSignal } from '@angular/core/rxjs-interop';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { forkJoin } from 'rxjs';

import { puedeAsignarRol } from '../../core/auth/roles';
import { AutenticacionService } from '../../core/services/auth.service';
import { EnlaceInvitacionComponent } from '../../shared/components/enlace-invitacion.component';
import { MotivoSelectorComponent } from '../../shared/components/motivo-selector.component';
import {
  esMotivoCompleto,
  construirMotivo,
  etiquetaEstadoInvitacion,
} from '../../shared/config/motivos-mutacion';
import {
  DepartamentoGestion,
  Rol,
  Sede,
  Usuario,
  UsuarioCrear,
  UsuarioEdicionConMotivo,
  UsuarioInvitacionRespuesta,
} from '../../shared/interfaces';
import { nuevaClaveIdempotencia } from '../../shared/utils/idempotencia';
import { mensajeDeErrorAdministracion } from './administracion-errores';
import { AdministracionService } from './services/administracion.service';

const _BODEGUERO = 'Bodeguero';
const _SOLICITANTE = 'Solicitante';
const _SUMINISTROS = 'suministros';

/**
 * Aviso del borde «no-Bodeguero con Suministros» (D-12/AC-24/AC-29): el combo
 * excluye la fila automática, pero un valor heredado o programático no debe
 * enviarse; la API respondería 422 y el formulario lo indica antes de guardar.
 */
const _MENSAJE_SUMINISTROS_NO_BODEGUERO =
  'El departamento «Suministros» solo se asigna automáticamente a los Bodegueros. Elige otro departamento.';

/**
 * Roles cuyo reenvío de invitación autoriza el Administrador institucional
 * (Feature 017, D-10/AC-9). Espejo de `_ROLES_ASIGNABLES_ADMINISTRADOR` del
 * backend: la frontera real la aplica la API (403 para cualquier otro rol).
 */
const _ROLES_REENVIABLES = ['Bodeguero', 'Solicitante'];

/**
 * Vista de usuarios locales de la institución (Feature 012, AC-8/AC-9/AC-11;
 * ampliada por Feature 017 con invitaciones y motivos).
 *
 * Lista los usuarios del tenant con su rol, departamento y sede aplicable
 * (Bodeguero). Desde la Feature 017 muestra **dos conceptos separados**: el
 * vínculo local activo/inactivo y el estado persistido de invitación
 * (`pendiente`/`aceptada`/`revocada`/`expirada`/`no disponible`). El alta puede
 * devolver una invitación nueva; su URL se muestra solo en la respuesta
 * inmediata (en memoria del componente) y nunca en el listado. Editar y
 * cambiar estado exigen motivo del catálogo D-7 cuando hay cambio efectivo.
 *
 * Desde T12 ofrece el **reenvío ordinario** (`POST /usuarios/{id}/invitacion/
 * reenvio`) a Bodegueros/Solicitantes de la institución, solo con vínculo local
 * activo y sin invitación aceptada, y copia el enlace nuevo sin persistirlo.
 * Reactivar sigue siendo una operación distinta (`PATCH .../estado` con motivo):
 * esta vista no reenvía al reactivar, solo deja disponible el reenvío después
 * (D-4, §5 regla 7).
 */

@Component({
  selector: 'app-administracion-usuarios',
  standalone: true,
  imports: [ReactiveFormsModule, MotivoSelectorComponent, EnlaceInvitacionComponent],
  templateUrl: './usuarios.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class UsuariosComponent implements OnInit {
  private readonly administracion = inject(AdministracionService);
  private readonly autenticacion = inject(AutenticacionService);
  private readonly constructorFormulario = inject(NonNullableFormBuilder);

  readonly cargando = signal(true);
  readonly usuarios = signal<Usuario[]>([]);
  readonly roles = signal<Rol[]>([]);
  readonly departamentos = signal<DepartamentoGestion[]>([]);
  readonly sedes = signal<Sede[]>([]);

  readonly mensajeError = signal<string | null>(null);
  readonly mensajeExito = signal<string | null>(null);
  readonly errorAccion = signal<string | null>(null);

  readonly editando = signal<Usuario | null>(null);
  readonly confirmando = signal<Usuario | null>(null);
  readonly asignandoSede = signal<Usuario | null>(null);
  readonly sedeSeleccion = signal<number | null>(null);
  readonly guardando = signal(false);

  /** `true` mientras el formulario de alta de usuario está abierto (AC-8). */
  readonly creando = signal(false);

  /**
   * Enlace de invitación recibido en la respuesta inmediata del alta
   * (Feature 017, D-4). Vive solo en memoria: al navegar o recargar desaparece.
   */
  readonly enlaceInvitacion = signal<{ url: string; nombre: string } | null>(null);

  /** `true` mientras hay un reenvío de invitación en vuelo (anti doble envío). */
  readonly reenviando = signal(false);

  /**
   * Usuario recién reactivado (Feature 017, §5 regla 7). Sirve para recordar en
   * la tarjeta que la reactivación **no** reenvía la invitación y que el envío
   * de un enlace nuevo es una acción separada.
   */
  readonly sugerenciaReenvio = signal<number | null>(null);

  /** Rol del usuario resuelto por `rol_id` contra el catálogo de roles. */
  readonly rolesPorId = computed(
    () => new Map(this.roles().map((rol) => [rol.rol_id, rol.nombre_rol])),
  );

  /**
   * Rol de la identidad activa (`/auth/me`). Reactivo a la sesión: si cambia el
   * usuario autenticado, el formulario de alta recalcula sus opciones.
   */
  readonly rolActual = computed(() => this.autenticacion.identidad()?.rol ?? null);

  /**
   * Roles que la identidad activa puede asignar en el **alta** (D-6/AC-10): el
   * Administrador solo `Bodeguero`/`Solicitante`; el Superadmin, los cuatro.
   */
  readonly rolesAsignables = computed(() =>
    this.roles().filter((rol) => puedeAsignarRol(this.rolActual(), rol.nombre_rol)),
  );

  /**
   * Roles del combo de **edición** (Feature 007, D-6/AC-10; Feature 017, AC-9).
   *
   * Ofrece los mismos roles asignables que el alta —un Administrador nunca ve
   * `Superadmin` ni puede promover a `Administrador`— y conserva el rol actual
   * del usuario editado aunque no sea asignable, para que el combo muestre el
   * valor persistido al editar a otro Administrador. `Superadmin` se excluye
   * siempre: es una identidad de control, no un rol de tenant, y esta vista solo
   * gestiona usuarios institucionales (Feature 017, AC-9/D-10).
   */
  readonly rolesEdicion = computed(() => {
    const usuario = this.editando();
    return this.roles().filter(
      (rol) =>
        rol.nombre_rol !== 'Superadmin' &&
        (puedeAsignarRol(this.rolActual(), rol.nombre_rol) ||
          rol.rol_id === Number(usuario?.rol_id)),
    );
  });

  readonly formularioEdicion = this.constructorFormulario.group({
    nombre: ['', [Validators.required, Validators.maxLength(100)]],
    apellido: ['', [Validators.required, Validators.maxLength(100)]],
    rol_id: [0, [Validators.required, Validators.min(1)]],
    departamento_id: [0, [Validators.required, Validators.min(1)]],
    sede_id: [null as number | null],
  });

  /** Motivo de la edición (Feature 017, D-5/D-7). */
  readonly motivoEdicion = this.constructorFormulario.group({
    codigo: [''],
    texto: [''],
  });

  /** Motivo de la baja/reactivación (Feature 017, D-5/D-7). */
  readonly motivoEstado = this.constructorFormulario.group({
    codigo: [''],
    texto: [''],
  });

  /** Valores reactivos de los formularios con motivo (signals, no getters). */
  private readonly valorEdicion = toSignal(this.formularioEdicion.valueChanges, {
    initialValue: this.formularioEdicion.getRawValue(),
  });
  private readonly valorMotivoEdicion = toSignal(this.motivoEdicion.valueChanges, {
    initialValue: { codigo: '', texto: '' },
  });
  private readonly valorMotivoEstado = toSignal(this.motivoEstado.valueChanges, {
    initialValue: { codigo: '', texto: '' },
  });

  /** Rol elegido en la edición; reactivo a los cambios del control (D-13). */
  private readonly rolEdicion = toSignal(
    this.formularioEdicion.controls.rol_id.valueChanges,
    { initialValue: 0 },
  );

  /** Sede elegida en la edición (sede del Bodeguero o filtro del Solicitante). */
  private readonly valorSedeEdicion = toSignal(
    this.formularioEdicion.controls.sede_id.valueChanges,
    { initialValue: null as number | null },
  );

  /**
   * `true` si el formulario de edición cambió algún atributo efectivo.
   *
   * Un Bodeguero cuyo departamento persistido **no** es «Suministros» (legacy,
   * p. ej. «Biblioteca») cambia de forma efectiva al guardar, porque el servidor
   * resuelve «Suministros»: exige motivo aunque solo cambie el nombre o no se
   * toque ningún otro campo (D-13/D-15). Un Bodeguero ya en «Suministros» sin
   * más cambios no lo exige.
   */
  readonly hayCambiosEdicion = computed(() => {
    const usuario = this.editando();
    if (!usuario) {
      return false;
    }
    const valores = this.valorEdicion();
    if (
      (valores.nombre ?? '').trim() !== usuario.nombre ||
      (valores.apellido ?? '').trim() !== usuario.apellido ||
      Number(valores.rol_id) !== Number(usuario.rol_id)
    ) {
      return true;
    }
    if (this.nombreRol(Number(valores.rol_id)) === _BODEGUERO) {
      return !this.esSuministrosPersistido(usuario);
    }
    return Number(valores.departamento_id) !== Number(usuario.departamento_id);
  });

  /** `true` si el motivo de la edición puede enviarse tal como está. */
  readonly motivoEdicionCompleto = computed(() => {
    const motivo = this.valorMotivoEdicion();
    return esMotivoCompleto(motivo.codigo ?? '', motivo.texto ?? '');
  });

  /** `true` si el motivo del cambio de estado puede enviarse tal como está. */
  readonly motivoEstadoCompleto = computed(() => {
    const motivo = this.valorMotivoEstado();
    return esMotivoCompleto(motivo.codigo ?? '', motivo.texto ?? '');
  });

  /**
   * Alta de usuario local (AC-8): nombre, apellido y correo, rol y departamento
   * del tenant. Desde la Feature 017 el backend invita (o reutiliza una
   * invitación/identidad) y su resultado se muestra al usuario.
   */
  readonly formularioCreacion = this.constructorFormulario.group({
    nombre: ['', [Validators.required, Validators.maxLength(100)]],
    apellido: ['', [Validators.required, Validators.maxLength(100)]],
    correo: ['', [Validators.required, Validators.email, Validators.maxLength(150)]],
    rol_id: [0, [Validators.required, Validators.min(1)]],
    departamento_id: [0, [Validators.required, Validators.min(1)]],
    sede_id: [null as number | null],
  });

  /** Rol elegido en el formulario de alta; reactivo a los cambios del control. */
  private readonly rolCreacion = toSignal(
    this.formularioCreacion.controls.rol_id.valueChanges,
    { initialValue: 0 },
  );

  /** Sede elegida en el alta (filtro del Solicitante o sede del Bodeguero). */
  private readonly valorSedeCreacion = toSignal(
    this.formularioCreacion.controls.sede_id.valueChanges,
    { initialValue: null as number | null },
  );

  /** Departamento elegido en el alta (vacío mientras no se elija uno válido). */
  private readonly valorDepartamentoCreacion = toSignal(
    this.formularioCreacion.controls.departamento_id.valueChanges,
    { initialValue: 0 },
  );

  /** `true` si el rol elegido para el alta es Bodeguero (sede obligatoria). */
  readonly creacionEsBodeguero = computed(
    () => this.nombreRol(this.rolCreacion()) === _BODEGUERO,
  );

  /** `true` si el rol elegido para el alta es Solicitante (sede como filtro). */
  readonly creacionEsSolicitante = computed(
    () => this.nombreRol(this.rolCreacion()) === _SOLICITANTE,
  );

  /** `true` si el alta muestra la Sede (Bodeguero y Solicitante; D-14). */
  readonly creacionMuestraSede = computed(
    () => this.creacionEsBodeguero() || this.creacionEsSolicitante(),
  );

  /**
   * Departamentos elegibles en el alta para un rol distinto de Bodeguero.
   *
   * «Suministros» se excluye porque el backend lo rechaza (422) para cualquier
   * rol que no sea Bodeguero (D-12); «Suministros» del Bodeguero lo resuelve el
   * servidor y no se elige. No se filtra por `activo`: el criterio vigente del
   * combo se conserva.
   */
  private readonly departamentosDisponibles = computed(() =>
    this.departamentos().filter(
      (departamento) => !this.esDepartamentoSuministros(departamento),
    ),
  );

  /**
   * Departamentos que ofrece el alta: todos los elegibles y, para el
   * Solicitante, los de la sede elegida como filtro (D-11). Sin filtro se
   * listan todos.
   */
  readonly departamentosCreacion = computed(() => {
    const disponibles = this.departamentosDisponibles();
    if (!this.creacionEsSolicitante()) {
      return disponibles;
    }
    const sedeId = this.valorSedeCreacion();
    if (sedeId === null) {
      return disponibles;
    }
    return disponibles.filter(
      (departamento) => departamento.sede_id === Number(sedeId),
    );
  });

  /** Departamento seleccionado dentro de la lista vigente del alta. */
  private readonly departamentoSeleccionadoCreacion = computed(
    () =>
      this.departamentosCreacion().find(
        (departamento) =>
          departamento.departamento_id ===
          Number(this.valorDepartamentoCreacion()),
      ) ?? null,
  );

  /** `true` si el tenant no tiene sedes y el alta pide una (Bodeguero). */
  readonly creacionBodegueroSinSedes = computed(
    () => this.creacionEsBodeguero() && this.sedes().length === 0,
  );

  /**
   * Texto único del borde «Suministros» para un rol distinto de Bodeguero
   * (D-12/AC-24/AC-29); se muestra junto al control y al intentar guardar.
   */
  readonly mensajeSuministros = _MENSAJE_SUMINISTROS_NO_BODEGUERO;

  /**
   * `true` si el alta tiene seleccionado «Suministros» para un rol distinto de
   * Bodeguero. El combo lo excluye; este predicado cubre un valor heredado o
   * programático y bloquea el envío con un aviso (D-12/AC-24).
   */
  readonly creacionSeleccionaSuministros = computed(
    () =>
      !this.creacionEsBodeguero() &&
      this.esDepartamentoSuministrosId(this.valorDepartamentoCreacion()),
  );

  /** `true` si el rol destino de la edición es Bodeguero (D-13). */
  readonly edicionEsBodeguero = computed(
    () => this.nombreRol(this.rolEdicion()) === _BODEGUERO,
  );

  /** `true` si el rol destino de la edición es Solicitante (Sede como filtro). */
  readonly edicionEsSolicitante = computed(
    () => this.nombreRol(this.rolEdicion()) === _SOLICITANTE,
  );

  /** `true` si la edición muestra la Sede (Bodeguero y Solicitante; D-14). */
  readonly edicionMuestraSede = computed(
    () => this.edicionEsBodeguero() || this.edicionEsSolicitante(),
  );

  /**
   * Departamentos elegibles en la edición: todos los que no son «Suministros»
   * y, para el Solicitante, los de la sede elegida como filtro (D-11/D-13).
   */
  readonly departamentosEdicion = computed(() => {
    const disponibles = this.departamentosDisponibles();
    if (!this.edicionEsSolicitante()) {
      return disponibles;
    }
    const sedeId = this.valorSedeEdicion();
    if (sedeId === null) {
      return disponibles;
    }
    return disponibles.filter(
      (departamento) => departamento.sede_id === Number(sedeId),
    );
  });

  /** `true` si el tenant no tiene sedes y la edición pide una (Bodeguero). */
  readonly edicionBodegueroSinSedes = computed(
    () => this.edicionEsBodeguero() && this.sedes().length === 0,
  );

  /**
   * `true` si la edición tiene seleccionado «Suministros» para un rol distinto
   * de Bodeguero. Cubre la selección heredada o programática que el combo ya no
   * ofrece y bloquea el guardado con un aviso (D-12/AC-29).
   */
  readonly edicionSeleccionaSuministros = computed(
    () =>
      !this.edicionEsBodeguero() &&
      this.esDepartamentoSuministrosId(this.valorEdicion().departamento_id),
  );

  /** Clave de idempotencia de la mutación en curso (se reutiliza en reintentos). */
  private idempotenciaEdicion: string | null = null;
  private idempotenciaEstado: string | null = null;

  /**
   * `true` mientras `abrirCreacion` reinicia el formulario: los valores
   * programáticos no deben disparar la sincronización sede↔departamento.
   */
  private inicializandoCreacion = false;

  /**
   * `true` mientras `iniciarEdicion` reinicia el formulario: los valores
   * programáticos no deben disparar la matriz de rol ni la sincronización.
   */
  private inicializandoEdicion = false;

  constructor() {
    this.formularioCreacion.controls.rol_id.valueChanges
      .pipe(takeUntilDestroyed())
      .subscribe(() => {
        if (!this.inicializandoCreacion) {
          this.aplicarRolCreacion();
        }
      });
    this.formularioCreacion.controls.sede_id.valueChanges
      .pipe(takeUntilDestroyed())
      .subscribe(() => {
        if (!this.inicializandoCreacion && this.creacionEsSolicitante()) {
          this.limpiarDepartamentoIncompatible();
        }
      });
    this.formularioCreacion.controls.departamento_id.valueChanges
      .pipe(takeUntilDestroyed())
      .subscribe(() => {
        if (!this.inicializandoCreacion) {
          this.sincronizarSedeConDepartamento();
        }
      });
    this.formularioEdicion.controls.rol_id.valueChanges
      .pipe(takeUntilDestroyed())
      .subscribe(() => {
        if (!this.inicializandoEdicion) {
          this.aplicarRolEdicion();
        }
      });
    this.formularioEdicion.controls.sede_id.valueChanges
      .pipe(takeUntilDestroyed())
      .subscribe(() => {
        if (!this.inicializandoEdicion && this.edicionEsSolicitante()) {
          this.limpiarDepartamentoIncompatibleEdicion();
        }
      });
    this.formularioEdicion.controls.departamento_id.valueChanges
      .pipe(takeUntilDestroyed())
      .subscribe(() => {
        if (!this.inicializandoEdicion) {
          this.sincronizarSedeConDepartamentoEdicion();
        }
      });
  }

  ngOnInit(): void {
    this.cargar();
  }

  reintentar(): void {
    this.cargar();
  }

  nombreRol(rolId: number): string | null {
    // El valor puede llegar como string desde un `<select>` con `[value]`
    // (residual) mientras el mapa usa claves numéricas. Normalizar aquí evita
    // que la matriz de rol y el motivo de edición se desalineen.
    return this.rolesPorId().get(Number(rolId)) ?? null;
  }

  nombreDepartamento(departamentoId: number): string | null {
    const id = Number(departamentoId);
    return (
      this.departamentos().find((d) => d.departamento_id === id)
        ?.nombre_dep ?? null
    );
  }

  /** `true` si el departamento es el «Suministros» de asignación automática. */
  private esDepartamentoSuministros(departamento: DepartamentoGestion): boolean {
    return departamento.nombre_dep.trim().toLowerCase() === _SUMINISTROS;
  }

  /**
   * `true` si el id corresponde a un departamento «Suministros» del catálogo.
   * Se usa para el borde de un rol distinto de Bodeguero (D-12/AC-24/AC-29).
   */
  private esDepartamentoSuministrosId(
    departamentoId: number | null | undefined,
  ): boolean {
    if (departamentoId === null || departamentoId === undefined) {
      return false;
    }
    const id = Number(departamentoId);
    if (!Number.isFinite(id) || id < 1) {
      return false;
    }
    const departamento = this.departamentos().find(
      (item) => item.departamento_id === id,
    );
    return (
      departamento !== undefined && this.esDepartamentoSuministros(departamento)
    );
  }

  /**
   * `true` si el departamento **persistido** del usuario es «Suministros».
   * Compara el nombre normalizado del catálogo (D-8/D-15); un legado en
   * «Biblioteca» no lo es y su edición será efectiva al resolverse «Suministros».
   */
  private esSuministrosPersistido(usuario: Usuario): boolean {
    return this.esDepartamentoSuministrosId(usuario.departamento_id);
  }

  nombreSede(sedeId: number | null | undefined): string | null {
    if (sedeId === null || sedeId === undefined) {
      return null;
    }
    const id = Number(sedeId);
    return this.sedes().find((sede) => sede.sede_id === id)?.nombre ?? null;
  }

  esBodeguero(usuario: Usuario): boolean {
    return this.nombreRol(usuario.rol_id) === _BODEGUERO;
  }

  /** Etiqueta legible del estado persistido de invitación (AC-5). */
  estadoInvitacion(usuario: Usuario): string {
    return etiquetaEstadoInvitacion(usuario.estado_invitacion);
  }

  /** `true` si el estado persistido es `aceptada` (no se reenvía). */
  invitacionAceptada(usuario: Usuario): boolean {
    return usuario.estado_invitacion === 'aceptada';
  }

  /** `true` si el rol del usuario admite reenvío por el Administrador (AC-9). */
  esReenviable(usuario: Usuario): boolean {
    const rol = this.nombreRol(usuario.rol_id);
    return rol !== null && _ROLES_REENVIABLES.includes(rol);
  }

  /**
   * `true` si se ofrece «Reenviar invitación» (Feature 017, D-4/D-10/AC-6).
   *
   * Exige vínculo local activo (el reenvío nunca reactiva), rol
   * Bodeguero/Solicitante y una invitación no aceptada. Una invitación
   * aceptada no se reenvía; `revocada`/`expirada`/`pendiente`/`no disponible`
   * sí admiten una nueva.
   */
  puedeReenviar(usuario: Usuario): boolean {
    return (
      usuario.activo === true &&
      this.esReenviable(usuario) &&
      !this.invitacionAceptada(usuario)
    );
  }

  /**
   * `true` si el reenvío está bloqueado solo por el vínculo inactivo: la vista
   * indica que primero hay que reactivar con motivo (operaciones separadas).
   */
  requiereReactivarParaReenviar(usuario: Usuario): boolean {
    return (
      usuario.activo !== true &&
      this.esReenviable(usuario) &&
      !this.invitacionAceptada(usuario)
    );
  }

  iniciarEdicion(usuario: Usuario): void {
    this.errorAccion.set(null);
    this.mensajeExito.set(null);
    this.enlaceInvitacion.set(null);
    this.sugerenciaReenvio.set(null);
    this.confirmando.set(null);
    this.asignandoSede.set(null);
    const nombreRol = this.nombreRol(usuario.rol_id);
    const esBodeguero = nombreRol === _BODEGUERO;
    const esSolicitante = nombreRol === _SOLICITANTE;
    const departamentoActual =
      this.departamentos().find(
        (departamento) =>
          departamento.departamento_id === Number(usuario.departamento_id),
      ) ?? null;
    this.inicializandoEdicion = true;
    try {
      this.formularioEdicion.reset({
        nombre: usuario.nombre,
        apellido: usuario.apellido,
        rol_id: Number(usuario.rol_id),
        // El Bodeguero no elige departamento: el control queda deshabilitado y
        // el servidor resuelve «Suministros» (D-8/D-13).
        departamento_id: esBodeguero ? 0 : Number(usuario.departamento_id),
        // La Sede del Bodeguero es la asignada; la del Solicitante es el filtro
        // inicializado con la sede de su departamento (D-10/D-11).
        sede_id: esBodeguero
          ? usuario.sede_id !== null && usuario.sede_id !== undefined
            ? Number(usuario.sede_id)
            : null
          : esSolicitante
            ? departamentoActual?.sede_id ?? null
            : null,
      });
    } finally {
      this.inicializandoEdicion = false;
    }
    this.motivoEdicion.reset({ codigo: '', texto: '' });
    this.idempotenciaEdicion = nuevaClaveIdempotencia();
    this.editando.set(usuario);
    this.aplicarRolEdicion();
  }

  cancelarEdicion(): void {
    this.editando.set(null);
    this.idempotenciaEdicion = null;
  }

  /** Abre el formulario de alta con valores por defecto del tenant (AC-8). */
  abrirCreacion(): void {
    this.errorAccion.set(null);
    this.mensajeExito.set(null);
    this.enlaceInvitacion.set(null);
    this.sugerenciaReenvio.set(null);
    this.editando.set(null);
    this.confirmando.set(null);
    this.asignandoSede.set(null);
    const rolInicial = this.rolesAsignables()[0]?.rol_id ?? 0;
    const rolInicialEsBodeguero = this.nombreRol(rolInicial) === _BODEGUERO;
    this.inicializandoCreacion = true;
    try {
      this.formularioCreacion.reset({
        nombre: '',
        apellido: '',
        correo: '',
        rol_id: rolInicial,
        departamento_id: rolInicialEsBodeguero
          ? 0
          : (this.departamentosDisponibles()[0]?.departamento_id ?? 0),
        sede_id: null,
      });
    } finally {
      this.inicializandoCreacion = false;
    }
    this.aplicarRolCreacion();
    this.creando.set(true);
  }

  cancelarCreacion(): void {
    this.creando.set(false);
    this.enlaceInvitacion.set(null);
  }

  /** Envía el alta; al volver muestra el estado de invitación y su enlace si vino. */
  guardarCreacion(): void {
    if (this.guardando()) {
      return;
    }
    const esBodeguero = this.creacionEsBodeguero();
    if (this.creacionBodegueroSinSedes()) {
      this.errorAccion.set(
        'La institución no tiene sedes registradas: no se puede crear un Bodeguero sin sede.',
      );
      return;
    }
    if (
      !this.creacionEsBodeguero() &&
      this.esDepartamentoSuministrosId(
        this.formularioCreacion.controls.departamento_id.value,
      )
    ) {
      // El combo excluye «Suministros» para roles distintos de Bodeguero; un
      // valor heredado o programático se bloquea aquí (D-12/AC-24).
      this.errorAccion.set(this.mensajeSuministros);
      return;
    }
    if (this.formularioCreacion.invalid) {
      this.formularioCreacion.markAllAsTouched();
      return;
    }
    const valores = this.formularioCreacion.getRawValue();
    const sedeElegida =
      esBodeguero && valores.sede_id !== null
        ? Number(valores.sede_id)
        : null;
    const datos: UsuarioCrear = {
      nombre: valores.nombre.trim(),
      apellido: valores.apellido.trim(),
      correo: valores.correo.trim(),
      rol_id: Number(valores.rol_id),
      // El Bodeguero no elige departamento: el servidor resuelve «Suministros»
      // (D-8/D-12). La sede nunca viaja en el alta (D-10): se persiste con el
      // PUT de sede después del 201.
      ...(esBodeguero
        ? {}
        : { departamento_id: Number(valores.departamento_id) }),
    };
    this.guardando.set(true);
    this.errorAccion.set(null);
    this.enlaceInvitacion.set(null);

    this.administracion
      .crearUsuario(datos)
      .subscribe({
        next: (creado) => {
          this.creando.set(false);
          if (creado.url_invitacion) {
            this.enlaceInvitacion.set({
              url: creado.url_invitacion,
              nombre: `${creado.nombre} ${creado.apellido}`,
            });
          }
          if (esBodeguero && sedeElegida !== null) {
            this.asignarSedeTrasAlta(creado, sedeElegida);
            return;
          }
          this.guardando.set(false);
          this.mensajeExito.set(this.mensajeDeAlta(creado));
          this.cargar();
        },
        error: (error: HttpErrorResponse) => {
          this.guardando.set(false);
          this.errorAccion.set(mensajeDeErrorAdministracion(error));
        },
      });
  }

  /**
   * Aplica la matriz de campos del rol elegido (D-14/AC-24): el Bodeguero deja
   * el Departamento deshabilitado (lo resuelve el servidor) y exige Sede; el
   * Solicitante habilita ambos (Sede como filtro); Administrador/Superadmin
   * mantienen Departamento obligatorio y no muestran Sede. Las selecciones que
   * el nuevo rol no admite se limpian.
   */
  private aplicarRolCreacion(): void {
    const esBodeguero = this.creacionEsBodeguero();
    const departamento = this.formularioCreacion.controls.departamento_id;
    const sede = this.formularioCreacion.controls.sede_id;

    if (esBodeguero) {
      departamento.disable({ emitEvent: false });
      departamento.setValidators(null);
      departamento.setValue(0, { emitEvent: false });
    } else {
      departamento.enable({ emitEvent: false });
      departamento.setValidators([Validators.required, Validators.min(1)]);
    }
    departamento.updateValueAndValidity({ emitEvent: false });

    sede.setValidators(esBodeguero ? Validators.required : null);
    if (this.creacionMuestraSede()) {
      sede.enable({ emitEvent: false });
    } else {
      sede.setValue(null, { emitEvent: false });
      sede.disable({ emitEvent: false });
    }
    sede.updateValueAndValidity({ emitEvent: false });

    this.limpiarDepartamentoIncompatible();
  }

  /**
   * Sincroniza la Sede con la del departamento elegido por el Solicitante; si
   * el departamento no tiene sede, el filtro queda en «Todas las sedes» (D-11).
   */
  private sincronizarSedeConDepartamento(): void {
    if (!this.creacionEsSolicitante()) {
      return;
    }
    const departamento = this.departamentoSeleccionadoCreacion();
    if (!departamento) {
      return;
    }
    this.formularioCreacion.controls.sede_id.setValue(departamento.sede_id ?? null);
  }

  /**
   * Limpia la selección de departamento que la sede filtrada ya no admite: el
   * formulario no se envía hasta elegir uno válido (D-11/AC-24).
   */
  private limpiarDepartamentoIncompatible(): void {
    const departamento = this.formularioCreacion.controls.departamento_id;
    if (departamento.disabled) {
      return;
    }
    const opciones = this.departamentosCreacion();
    if (
      !opciones.some(
        (opcion) => opcion.departamento_id === Number(departamento.value),
      )
    ) {
      departamento.setValue(0, { emitEvent: false });
    }
  }

  /**
   * Aplica la matriz de campos del rol destino de la edición (D-13/D-14): el
   * Bodeguero deja el Departamento deshabilitado (lo resuelve el servidor) y
   * exige Sede; el Solicitante habilita ambos con la Sede como filtro;
   * Administrador/Superadmin mantienen Departamento obligatorio y sin Sede.
   */
  private aplicarRolEdicion(): void {
    const esBodeguero = this.edicionEsBodeguero();
    const departamento = this.formularioEdicion.controls.departamento_id;
    const sede = this.formularioEdicion.controls.sede_id;

    if (esBodeguero) {
      departamento.disable({ emitEvent: false });
      departamento.setValidators(null);
      departamento.setValue(0, { emitEvent: false });
    } else {
      departamento.enable({ emitEvent: false });
      departamento.setValidators([Validators.required, Validators.min(1)]);
    }
    departamento.updateValueAndValidity({ emitEvent: false });

    sede.setValidators(esBodeguero ? Validators.required : null);
    if (this.edicionMuestraSede()) {
      sede.enable({ emitEvent: false });
    } else {
      sede.setValue(null, { emitEvent: false });
      sede.disable({ emitEvent: false });
    }
    // Al cambiar de rol el Departamento queda sin selección: el filtro del
    // Solicitante vuelve a «Todas las sedes» hasta que elija uno válido (D-11).
    if (!esBodeguero && Number(departamento.value) === 0) {
      sede.setValue(null);
    }
    sede.updateValueAndValidity({ emitEvent: false });

    this.limpiarDepartamentoIncompatibleEdicion();
    this.formularioEdicion.updateValueAndValidity({ emitEvent: true });
  }

  /**
   * Sincroniza la Sede (filtro) con la del departamento elegido en la edición;
   * si no tiene sede, el filtro queda en «Todas las sedes» (D-11).
   */
  private sincronizarSedeConDepartamentoEdicion(): void {
    if (!this.edicionEsSolicitante()) {
      return;
    }
    const departamento =
      this.departamentosEdicion().find(
        (opcion) =>
          opcion.departamento_id ===
          Number(this.formularioEdicion.controls.departamento_id.value),
      ) ?? null;
    if (!departamento) {
      return;
    }
    this.formularioEdicion.controls.sede_id.setValue(
      departamento.sede_id ?? null,
    );
  }

  /**
   * Limpia la selección de departamento que la sede filtrada ya no admite: el
   * formulario no se envía hasta elegir uno válido (D-11/D-13).
   */
  private limpiarDepartamentoIncompatibleEdicion(): void {
    const departamento = this.formularioEdicion.controls.departamento_id;
    if (departamento.disabled) {
      return;
    }
    const opciones = this.departamentosEdicion();
    if (
      !opciones.some(
        (opcion) => opcion.departamento_id === Number(departamento.value),
      )
    ) {
      departamento.setValue(0);
    }
  }

  /** Asigna la sede elegida en el alta; el error no revierte la creación. */
  private asignarSedeTrasAlta(
    creado: UsuarioInvitacionRespuesta,
    sedeId: number,
  ): void {
    this.administracion.asignarSedeUsuario(creado.usuario_id, sedeId).subscribe({
      next: () => {
        this.guardando.set(false);
        this.mensajeExito.set(
          `${this.mensajeDeAlta(creado)} Sede asignada.`,
        );
        this.cargar();
      },
      error: (error: HttpErrorResponse) => {
        this.guardando.set(false);
        this.errorAccion.set(
          `El usuario se creó, pero no se pudo asignar su sede. ${mensajeDeErrorAdministracion(error)}`,
        );
        this.cargar();
      },
    });
  }

  /** Mensaje del alta según el estado persistido y si trajo enlace inmediato. */
  private mensajeDeAlta(creado: UsuarioInvitacionRespuesta): string {
    const nombre = `«${creado.nombre} ${creado.apellido}»`;
    if (creado.url_invitacion) {
      return `Usuario ${nombre} creado con invitación pendiente. Copia el enlace ahora: no volverá a mostrarse.`;
    }
    if (creado.estado_invitacion === 'aceptada') {
      return `Usuario ${nombre} creado y vinculado a una identidad existente (invitación aceptada).`;
    }
    return `Usuario ${nombre} creado. Estado de invitación: ${etiquetaEstadoInvitacion(creado.estado_invitacion)}.`;
  }

  guardarEdicion(): void {
    const usuario = this.editando();
    if (!usuario || this.guardando()) {
      return;
    }
    if (this.edicionBodegueroSinSedes()) {
      this.errorAccion.set(
        'La institución no tiene sedes registradas: no se puede guardar un Bodeguero sin sede.',
      );
      return;
    }
    if (
      !this.edicionEsBodeguero() &&
      this.esDepartamentoSuministrosId(
        this.formularioEdicion.controls.departamento_id.value,
      )
    ) {
      // El combo excluye «Suministros» para roles distintos de Bodeguero; un
      // valor heredado o programático se bloquea aquí (D-12/AC-29).
      this.errorAccion.set(this.mensajeSuministros);
      return;
    }
    if (this.formularioEdicion.invalid) {
      this.formularioEdicion.markAllAsTouched();
      return;
    }
    const valores = this.formularioEdicion.getRawValue();
    const rolId = Number(valores.rol_id);
    const esBodegueroDestino = this.nombreRol(rolId) === _BODEGUERO;
    const cambia = this.hayCambiosEdicion();
    if (cambia && !this.motivoEdicionCompleto()) {
      this.motivoEdicion.markAllAsTouched();
      return;
    }
    const motivo = this.motivoEdicion.getRawValue();
    const datos: UsuarioEdicionConMotivo = {
      nombre: valores.nombre.trim(),
      apellido: valores.apellido.trim(),
      rol_id: rolId,
      // El Bodeguero no elige departamento: lo resuelve el servidor (D-8/D-13).
      // La Sede nunca viaja aquí: se persiste con el PUT .../sede posterior.
      ...(esBodegueroDestino
        ? {}
        : { departamento_id: Number(valores.departamento_id) }),
      ...(cambia
        ? {
            motivo: construirMotivo(motivo.codigo, motivo.texto),
            idempotencia: this.idempotenciaEdicion,
          }
        : {}),
    };
    this.guardando.set(true);
    this.errorAccion.set(null);

    this.administracion
      .editarUsuario(usuario.usuario_id, datos)
      .subscribe({
        next: (actualizado) => {
          const fusionado = this.fusionarUsuarioEditado(usuario, actualizado);
          this.editando.set(null);
          this.idempotenciaEdicion = null;
          this.reemplazar(fusionado);
          if (esBodegueroDestino && valores.sede_id !== null) {
            // Orden D-13: primero el usuario y después la sede. Si esta falla,
            // los cambios del usuario ya están guardados (éxito parcial).
            this.asignarSedeTrasEdicion(fusionado, Number(valores.sede_id));
            return;
          }
          this.guardando.set(false);
          this.mensajeExito.set(
            `Usuario «${actualizado.nombre} ${actualizado.apellido}» actualizado.`,
          );
          this.cargar();
        },
        error: (error: HttpErrorResponse) => {
          this.guardando.set(false);
          this.errorAccion.set(mensajeDeErrorAdministracion(error));
        },
      });
  }

  /** Conserva los datos que la edición no consulta (vínculo e invitación). */
  private fusionarUsuarioEditado(
    usuario: Usuario,
    actualizado: Usuario,
  ): Usuario {
    return {
      ...usuario,
      ...actualizado,
      sede_id:
        actualizado.sede_id !== undefined
          ? actualizado.sede_id
          : usuario.sede_id,
      activo: usuario.activo,
      estado_invitacion: usuario.estado_invitacion,
    };
  }

  /**
   * Persiste la sede elegida tras editar un Bodeguero (D-10/D-13). Es
   * idempotente si la sede no cambió; un fallo no revierte la edición y se
   * informa como éxito parcial.
   */
  private asignarSedeTrasEdicion(usuario: Usuario, sedeId: number): void {
    this.administracion.asignarSedeUsuario(usuario.usuario_id, sedeId).subscribe({
      next: (resultado) => {
        this.guardando.set(false);
        this.reemplazar({ ...usuario, sede_id: resultado.sede_id });
        this.mensajeExito.set(
          `Usuario «${usuario.nombre} ${usuario.apellido}» actualizado y sede asignada.`,
        );
        this.cargar();
      },
      error: (error: HttpErrorResponse) => {
        this.guardando.set(false);
        this.errorAccion.set(
          `Los cambios de «${usuario.nombre} ${usuario.apellido}» se guardaron, pero la sede no se actualizó. ${mensajeDeErrorAdministracion(error)}`,
        );
        this.cargar();
      },
    });
  }

  iniciarAsignacionSede(usuario: Usuario): void {
    this.errorAccion.set(null);
    this.mensajeExito.set(null);
    this.enlaceInvitacion.set(null);
    this.sugerenciaReenvio.set(null);
    this.editando.set(null);
    this.confirmando.set(null);
    this.sedeSeleccion.set(usuario.sede_id ?? null);
    this.asignandoSede.set(usuario);
  }

  cancelarAsignacionSede(): void {
    this.asignandoSede.set(null);
    this.sedeSeleccion.set(null);
  }

  cambiarSeleccionSede(evento: Event): void {
    const valor = (evento.target as HTMLSelectElement).value;
    this.sedeSeleccion.set(valor === '' ? null : Number(valor));
  }

  guardarSede(): void {
    const usuario = this.asignandoSede();
    const sedeId = this.sedeSeleccion();
    if (!usuario || sedeId === null || this.guardando()) {
      return;
    }
    this.guardando.set(true);
    this.errorAccion.set(null);

    this.administracion.asignarSedeUsuario(usuario.usuario_id, sedeId).subscribe({
      next: (resultado) => {
        this.guardando.set(false);
        this.asignandoSede.set(null);
        this.sedeSeleccion.set(null);
        this.reemplazar({ ...usuario, sede_id: resultado.sede_id });
        this.mensajeExito.set(
          `Sede «${this.nombreSede(resultado.sede_id) ?? resultado.sede_id}» asignada a «${usuario.nombre} ${usuario.apellido}».`,
        );
      },
      error: (error: HttpErrorResponse) => {
        this.guardando.set(false);
        this.errorAccion.set(mensajeDeErrorAdministracion(error));
      },
    });
  }

  solicitarCambioEstado(usuario: Usuario): void {
    this.errorAccion.set(null);
    this.mensajeExito.set(null);
    this.enlaceInvitacion.set(null);
    this.sugerenciaReenvio.set(null);
    this.editando.set(null);
    this.asignandoSede.set(null);
    this.motivoEstado.reset({ codigo: '', texto: '' });
    this.idempotenciaEstado = nuevaClaveIdempotencia();
    this.confirmando.set(usuario);
  }

  cancelarCambioEstado(): void {
    this.confirmando.set(null);
    this.idempotenciaEstado = null;
  }

  confirmarCambioEstado(): void {
    const usuario = this.confirmando();
    if (!usuario || this.guardando()) {
      return;
    }
    if (!this.motivoEstadoCompleto()) {
      this.motivoEstado.markAllAsTouched();
      return;
    }
    const motivo = this.motivoEstado.getRawValue();
    const nuevoEstado = !(usuario.activo ?? true);
    this.guardando.set(true);
    this.errorAccion.set(null);

    this.administracion
      .cambiarEstadoUsuario(usuario.usuario_id, {
        activo: nuevoEstado,
        motivo: construirMotivo(motivo.codigo, motivo.texto),
        idempotencia: this.idempotenciaEstado,
      })
      .subscribe({
        next: (resultado) => {
          this.guardando.set(false);
          this.confirmando.set(null);
          this.idempotenciaEstado = null;
          this.motivoEstado.reset({ codigo: '', texto: '' });
          this.usuarios.update((lista) =>
            lista.map((item) =>
              item.usuario_id === resultado.usuario_id
                ? { ...item, activo: resultado.activo }
                : item,
            ),
          );
          if (resultado.activo) {
            // Reactivar no reenvía la invitación: son operaciones separadas
            // (Feature 017, D-4; §5 regla 7). Se deja el reenvío disponible.
            this.sugerenciaReenvio.set(resultado.usuario_id);
            this.mensajeExito.set(
              `Usuario «${usuario.nombre} ${usuario.apellido}» reactivado. La reactivación no reenvía la invitación: usa «Reenviar invitación» si necesitas un enlace nuevo.`,
            );
            return;
          }
          this.sugerenciaReenvio.set(null);
          this.mensajeExito.set(
            `Usuario «${usuario.nombre} ${usuario.apellido}» desactivado.`,
          );
        },
        error: (error: HttpErrorResponse) => {
          this.guardando.set(false);
          this.errorAccion.set(mensajeDeErrorAdministracion(error));
        },
      });
  }

  /**
   * Reenvía la invitación de un Bodeguero/Solicitante (Feature 017, T12).
   *
   * La URL nueva solo vive en esta respuesta: se monta en `enlaceInvitacion`
   * (en memoria) y desaparece al cambiar de acción o navegar. Un 409 (aceptada,
   * vínculo inactivo, conflicto de Clerk) o un 503 de la frontera se muestran
   * con el mensaje de la administración; no se inventa enlace.
   */
  reenviarInvitacion(usuario: Usuario): void {
    if (this.reenviando()) {
      return;
    }
    this.reenviando.set(true);
    this.errorAccion.set(null);
    this.mensajeExito.set(null);
    this.enlaceInvitacion.set(null);
    this.sugerenciaReenvio.set(null);

    this.administracion.reenviarInvitacionUsuario(usuario.usuario_id).subscribe({
      next: (respuesta) => {
        this.reenviando.set(false);
        if (respuesta.url_invitacion) {
          this.enlaceInvitacion.set({
            url: respuesta.url_invitacion,
            nombre: `${respuesta.nombre} ${respuesta.apellido}`,
          });
        }
        this.reemplazar({
          ...usuario,
          activo: respuesta.activo ?? usuario.activo,
          estado_invitacion: respuesta.estado_invitacion ?? 'pendiente',
        });
        this.mensajeExito.set(
          `Invitación de «${usuario.nombre} ${usuario.apellido}» reenviada. Copia el enlace ahora: no volverá a mostrarse.`,
        );
      },
      error: (error: HttpErrorResponse) => {
        this.reenviando.set(false);
        this.errorAccion.set(mensajeDeErrorAdministracion(error));
      },
    });
  }

  private cargar(): void {
    this.cargando.set(true);
    this.mensajeError.set(null);

    forkJoin({
      usuarios: this.administracion.listarUsuarios(),
      roles: this.administracion.listarRoles(),
      departamentos: this.administracion.listarDepartamentos(),
      sedes: this.administracion.listarSedes(),
    }).subscribe({
      next: ({ usuarios, roles, departamentos, sedes }) => {
        this.usuarios.set(usuarios);
        this.roles.set(roles);
        this.departamentos.set(departamentos);
        this.sedes.set(sedes);
        this.cargando.set(false);
      },
      error: (error: HttpErrorResponse) => {
        this.usuarios.set([]);
        this.cargando.set(false);
        this.mensajeError.set(mensajeDeErrorAdministracion(error));
      },
    });
  }

  private reemplazar(actualizado: Usuario): void {
    this.usuarios.update((lista) =>
      lista.map((item) =>
        item.usuario_id === actualizado.usuario_id ? actualizado : item,
      ),
    );
  }
}
