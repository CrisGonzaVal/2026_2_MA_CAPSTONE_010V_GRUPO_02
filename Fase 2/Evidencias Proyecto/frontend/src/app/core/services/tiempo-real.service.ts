import { DOCUMENT } from '@angular/common';
import {
  Injectable,
  InjectionToken,
  effect,
  inject,
  signal,
  untracked,
} from '@angular/core';

import { URL_API } from '../../shared/config/url-api';
import { AutenticacionService, EstadoIdentidad } from './auth.service';

/** Dominios que un frame puede invalidar (la marca `dashboard` es sintética). */
export const DOMINIOS_TIEMPO_REAL = [
  'pedidos',
  'inventario',
  'compras',
  'dashboard',
] as const;

export type DominioTiempoReal = (typeof DOMINIOS_TIEMPO_REAL)[number];

/** Motivos de diagnóstico del contrato de la Feature 028 (conjunto cerrado). */
export const MOTIVOS_TIEMPO_REAL = [
  'alta',
  'edicion',
  'aprobacion',
  'retiro',
  'confirmacion_entrega',
  'anulacion',
  'rechazo',
  'cambio_estado',
  'movimiento',
  'recepcion',
  'emision_oc',
  'facturacion_oc',
  'cancelacion_oc',
  'cambio',
] as const;

export type MotivoTiempoReal = (typeof MOTIVOS_TIEMPO_REAL)[number];

/** Estados observables del hub; no hay sondeo ni WebSocket. */
export type EstadoTiempoReal =
  | 'inactivo'
  | 'conectando'
  | 'conectado'
  | 'degradado'
  | 'reconectando';

export type EstadoFlujo = 'degradado' | 'recuperado';

/** Frame de invalidación ya validado contra el contrato. */
export interface CambioTiempoReal {
  readonly dominios: readonly DominioTiempoReal[];
  readonly motivo: MotivoTiempoReal;
}

export type FrameTiempoReal =
  | { readonly tipo: 'listo'; readonly dominios: readonly DominioTiempoReal[] }
  | ({ readonly tipo: 'cambio' } & CambioTiempoReal)
  | { readonly tipo: 'estado'; readonly estado: EstadoFlujo };

/** Costura inyectable del parser para que el hub y los tests compartan el lector. */
export interface ParserSse {
  alimentar(texto: string): void;
  reiniciar(): void;
}

/**
 * Reloj del hub. Se inyecta para que los tests controlen el retroceso y el
 * mínimo entre aperturas sin esperas reales; en producción usa `setTimeout`.
 */
export interface RelojTiempoReal {
  ahora(): number;
  programar(accion: () => void, retrasoMs: number): number;
  cancelar(identificador: number): void;
}

export const RELOJ_TIEMPO_REAL = new InjectionToken<RelojTiempoReal>(
  'RELOJ_TIEMPO_REAL',
  {
    providedIn: 'root',
    factory: (): RelojTiempoReal => ({
      ahora: () => Date.now(),
      programar: (accion, retrasoMs) =>
        setTimeout(accion, retrasoMs) as unknown as number,
      cancelar: (identificador) => clearTimeout(identificador),
    }),
  },
);

/**
 * Costura de `fetch`. El servicio no usa `EventSource` (no admite la cabecera
 * `Authorization` ni `AbortController`) ni `HttpClient` (puede bufferizar el
 * cuerpo). En producción es el `fetch` nativo.
 */
export const FETCH_TIEMPO_REAL = new InjectionToken<typeof fetch>(
  'FETCH_TIEMPO_REAL',
  {
    providedIn: 'root',
    factory: () => (entrada, opciones) => fetch(entrada, opciones),
  },
);

export const RETROCESO_MAXIMO_MS = 30_000;
export const MINIMO_ENTRE_APERTURAS_MS = 30_000;

/**
 * Retroceso exponencial 1/2/4/8/16/30 s con jitter de ±20 % y tope de 30 s.
 *
 * `aleatorio` se inyecta en los tests para fijar el factor; el hub usa
 * `Math.random`.
 */
export function calcularRetrocesoMs(
  intento: number,
  aleatorio: () => number = Math.random,
): number {
  const numero = Math.max(1, Math.floor(intento));
  const base = Math.min(
    RETROCESO_MAXIMO_MS,
    1000 * 2 ** (numero - 1),
  );
  const factor = 0.8 + aleatorio() * 0.4;
  return Math.min(RETROCESO_MAXIMO_MS, Math.round(base * factor));
}

/**
 * Traduce `Retry-After` (segundos o fecha HTTP) a milisegundos. Sin cabecera o
 * con un valor inválido devuelve `null` para que el hub use el retroceso.
 */
export function leerRetryAfterMs(valor: string | null): number | null {
  if (!valor) {
    return null;
  }
  const texto = valor.trim();
  const segundos = Number(texto);
  if (texto !== '' && Number.isFinite(segundos) && segundos >= 0) {
    return Math.round(segundos * 1000);
  }
  const fecha = Date.parse(texto);
  if (!Number.isNaN(fecha)) {
    return Math.max(0, fecha - Date.now());
  }
  return null;
}

function esDominio(valor: string): valor is DominioTiempoReal {
  return (DOMINIOS_TIEMPO_REAL as readonly string[]).includes(valor);
}

function esMotivo(valor: string): valor is MotivoTiempoReal {
  return (MOTIVOS_TIEMPO_REAL as readonly string[]).includes(valor);
}

function normalizarDominios(valor: unknown): DominioTiempoReal[] | null {
  if (!Array.isArray(valor)) {
    return null;
  }
  const dominios: DominioTiempoReal[] = [];
  for (const elemento of valor) {
    if (
      typeof elemento === 'string' &&
      esDominio(elemento) &&
      !dominios.includes(elemento)
    ) {
      dominios.push(elemento);
    }
  }
  return dominios.length > 0 ? dominios : null;
}

function interpretarFrame(
  tipo: string,
  carga: unknown,
): FrameTiempoReal | null {
  if (!carga || typeof carga !== 'object' || Array.isArray(carga)) {
    return null;
  }
  const registro = carga as Record<string, unknown>;

  if (tipo === 'listo') {
    const dominios = normalizarDominios(registro['dominios']);
    return dominios ? { tipo: 'listo', dominios } : null;
  }

  if (tipo === 'cambio') {
    const dominios = normalizarDominios(registro['dominios']);
    const motivo = registro['motivo'];
    if (!dominios || typeof motivo !== 'string' || !esMotivo(motivo)) {
      return null;
    }
    return { tipo: 'cambio', dominios, motivo };
  }

  if (tipo === 'estado') {
    const estado = registro['estado'];
    if (estado === 'degradado' || estado === 'recuperado') {
      return { tipo: 'estado', estado };
    }
  }

  return null;
}

/**
 * Parser incremental de SSE.
 *
 * Acumula texto y solo despacha en la línea vacía: los frames pueden llegar
 * partidos entre chunks, con `\r\n` o con comentarios `: latido`. Un tipo
 * desconocido, un JSON inválido o un `data` fuera del contrato se descartan sin
 * cerrar la conexión.
 */
export function crearParserSse(
  recibir: (frame: FrameTiempoReal) => void,
): ParserSse {
  let buffer = '';
  let tipoEvento = '';
  let lineasDatos: string[] = [];

  const despachar = (): void => {
    const tipo = tipoEvento || 'message';
    const datos = lineasDatos.join('\n');
    tipoEvento = '';
    lineasDatos = [];

    if (!datos) {
      return;
    }

    let carga: unknown;
    try {
      carga = JSON.parse(datos);
    } catch {
      return;
    }

    const frame = interpretarFrame(tipo, carga);
    if (frame) {
      recibir(frame);
    }
  };

  const procesarLinea = (linea: string): void => {
    if (linea === '') {
      despachar();
      return;
    }
    if (linea.startsWith(':')) {
      return;
    }

    const separador = linea.indexOf(':');
    const campo = separador >= 0 ? linea.slice(0, separador) : linea;
    let valor = separador >= 0 ? linea.slice(separador + 1) : '';
    if (valor.startsWith(' ')) {
      valor = valor.slice(1);
    }

    if (campo === 'event') {
      tipoEvento = valor;
    } else if (campo === 'data') {
      lineasDatos.push(valor);
    }
    // `id:`, `retry:` y campos desconocidos se ignoran (el servidor no los emite).
  };

  return {
    alimentar(texto: string): void {
      buffer += texto;
      // CRLF y CR solos se normalizan; un `\r` al final del chunk se conserva
      // porque puede ser la primera mitad de un `\r\n` en el siguiente.
      buffer = buffer.replace(/\r\n/g, '\n').replace(/\r(?!$)/g, '\n');
      const lineas = buffer.split('\n');
      buffer = lineas.pop() ?? '';
      for (const linea of lineas) {
        procesarLinea(linea);
      }
    },
    reiniciar(): void {
      buffer = '';
      tipoEvento = '';
      lineasDatos = [];
    },
  };
}

interface SuscripcionCambio {
  readonly dominios: ReadonlySet<DominioTiempoReal>;
  readonly callback: (cambio: CambioTiempoReal) => void;
}

/**
 * Hub raíz de actualización en tiempo real (Feature 028, T15).
 *
 * Una sola conexión por pestaña con `fetch` + `ReadableStream`; el Bearer sale
 * de `AutenticacionService` y viaja únicamente en la cabecera. El servicio no
 * interpreta datos de negocio: solo emite callbacks de invalidación y
 * resincronización para que cada vista relea por sus GET actuales.
 */
@Injectable({ providedIn: 'root' })
export class TiempoRealService {
  private readonly autenticacion = inject(AutenticacionService);
  private readonly documento = inject(DOCUMENT);
  private readonly fetchTiempoReal = inject(FETCH_TIEMPO_REAL);
  private readonly reloj = inject(RELOJ_TIEMPO_REAL);

  private readonly _estado = signal<EstadoTiempoReal>('inactivo');
  private readonly _ultimaConexion = signal<Date | null>(null);

  readonly estado = this._estado.asReadonly();
  readonly ultimaConexion = this._ultimaConexion.asReadonly();

  private readonly _activo = signal(false);

  /** Generación de la conexión: invalida lecturas y cierres de sesiones previas. */
  private generacion = 0;
  private conexionEnCurso = false;
  private abortador: AbortController | null = null;
  private temporizadorReintento: number | null = null;
  private intento = 0;
  private ultimaApertura = 0;
  private bloqueado = false;
  private estabaOculto = false;

  private readonly callbacksCambio = new Set<SuscripcionCambio>();
  private readonly callbacksResincronizar = new Set<() => void>();
  private readonly callbacksEstado = new Set<(estado: EstadoTiempoReal) => void>();

  private readonly alCambiarVisibilidad = (): void => {
    if (!this._activo()) {
      return;
    }
    const ocultoAhora = this.documento.hidden;
    if (this.estabaOculto && !ocultoAhora) {
      this.emitirResincronizacion();
    }
    this.estabaOculto = ocultoAhora;
  };

  constructor() {
    // Reacciona a la sesión sin repetir `/auth/me`: `AutenticacionService` ya
    // posee la identidad y el token.
    effect(
      () => {
        const activo = this._activo();
        const autenticado = this.autenticacion.estaAutenticado();
        const identidad = this.autenticacion.estadoIdentidad();
        untracked(() => this.aplicarSesion(activo, autenticado, identidad));
      },
      { allowSignalWrites: true },
    );
  }

  /**
   * Arranca el hub. Idempotente: varias llamadas comparten la misma conexión.
   * Solo abre con sesión y identidad local `disponible`.
   */
  iniciar(): void {
    if (this._activo()) {
      return;
    }
    this._activo.set(true);
    this.generacion += 1;
    this.intento = 0;
    this.bloqueado = false;
    this.estabaOculto = this.documento.hidden;
    this.documento.addEventListener('visibilitychange', this.alCambiarVisibilidad);
    this.aplicarSesion(
      true,
      this.autenticacion.estaAutenticado(),
      this.autenticacion.estadoIdentidad(),
    );
  }

  /**
   * Detiene el hub: aborta la conexión, cancela reintentos, deja el estado
   * inactivo y limpia los callbacks para que ninguna vista reciba frames de una
   * sesión cerrada.
   */
  detener(): void {
    this._activo.set(false);
    this.generacion += 1;
    this.cancelarReintento();
    this.abortarConexion();
    this.documento.removeEventListener(
      'visibilitychange',
      this.alCambiarVisibilidad,
    );
    this.conexionEnCurso = false;
    this.intento = 0;
    this.bloqueado = false;
    this.cambiarEstado('inactivo');
    this.limpiarCallbacks();
  }

  /** Registra un callback para los frames que toquen alguno de los dominios. */
  alCambio(
    dominios: readonly DominioTiempoReal[],
    callback: (cambio: CambioTiempoReal) => void,
  ): () => void {
    const suscripcion: SuscripcionCambio = {
      dominios: new Set(dominios),
      callback,
    };
    this.callbacksCambio.add(suscripcion);
    return () => {
      this.callbacksCambio.delete(suscripcion);
    };
  }

  /** Registra una resincronización (`listo`, `recuperado` o vuelta a foco). */
  alResincronizar(callback: () => void): () => void {
    this.callbacksResincronizar.add(callback);
    return () => {
      this.callbacksResincronizar.delete(callback);
    };
  }

  /** Observa las transiciones de estado y recibe el estado actual al suscribirse. */
  alEstado(callback: (estado: EstadoTiempoReal) => void): () => void {
    this.callbacksEstado.add(callback);
    try {
      callback(this._estado());
    } catch {
      // Un consumidor roto no debe impedir la conexión.
    }
    return () => {
      this.callbacksEstado.delete(callback);
    };
  }

  private aplicarSesion(
    activo: boolean,
    autenticado: boolean,
    identidad: EstadoIdentidad,
  ): void {
    if (!activo) {
      return;
    }
    if (!autenticado) {
      this.cerrarPorSesion(true);
      return;
    }
    if (identidad !== 'disponible') {
      this.cerrarPorSesion(false);
      return;
    }
    if (
      this.bloqueado ||
      this.conexionEnCurso ||
      this.temporizadorReintento !== null
    ) {
      return;
    }
    void this.abrirConexion(this.generacion);
  }

  private cerrarPorSesion(limpiarCallbacks: boolean): void {
    this.generacion += 1;
    this.cancelarReintento();
    this.abortarConexion();
    this.conexionEnCurso = false;
    this.intento = 0;
    this.bloqueado = false;
    this.cambiarEstado('inactivo');
    if (limpiarCallbacks) {
      this.limpiarCallbacks();
    }
  }

  private async abrirConexion(generacion: number): Promise<void> {
    if (!this._activo() || this.bloqueado || generacion !== this.generacion) {
      return;
    }
    if (this.conexionEnCurso || this.temporizadorReintento !== null) {
      return;
    }

    this.conexionEnCurso = true;
    this.cambiarEstado('conectando');

    let abortador: AbortController | null = null;

    try {
      const token = await this.autenticacion.obtenerToken();
      if (generacion !== this.generacion || !this._activo()) {
        return;
      }
      if (!token) {
        this.cambiarEstado('inactivo');
        return;
      }

      abortador = new AbortController();
      this.abortador = abortador;
      this.ultimaApertura = this.reloj.ahora();

      let respuesta: Response;
      try {
        respuesta = await this.fetchTiempoReal(`${URL_API}/eventos/`, {
          method: 'GET',
          headers: {
            Authorization: `Bearer ${token}`,
            Accept: 'text/event-stream',
          },
          cache: 'no-store',
          signal: abortador.signal,
        });
      } catch {
        if (abortador.signal.aborted || generacion !== this.generacion) {
          return;
        }
        this.programarError();
        return;
      }

      if (generacion !== this.generacion || abortador.signal.aborted) {
        this.descartarCuerpo(respuesta);
        return;
      }

      if (respuesta.status === 401 || respuesta.status === 403) {
        this.bloqueado = true;
        this.descartarCuerpo(respuesta);
        this.cambiarEstado('inactivo');
        return;
      }

      if (respuesta.status === 429) {
        this.descartarCuerpo(respuesta);
        const retraso = leerRetryAfterMs(respuesta.headers.get('Retry-After'));
        if (retraso !== null) {
          this.programarReconexion(retraso);
        } else {
          this.programarError();
        }
        return;
      }

      if (!respuesta.ok || !respuesta.body) {
        this.descartarCuerpo(respuesta);
        this.programarError();
        return;
      }

      await this.consumirFlujo(respuesta.body, abortador);

      if (
        generacion === this.generacion &&
        this._activo() &&
        !abortador.signal.aborted
      ) {
        this.programarRenovacion();
      }
    } catch {
      if (
        abortador?.signal.aborted ||
        generacion !== this.generacion ||
        !this._activo()
      ) {
        return;
      }
      this.programarError();
    } finally {
      if (generacion === this.generacion) {
        this.conexionEnCurso = false;
        if (this.abortador === abortador) {
          this.abortador = null;
        }
      }
    }
  }

  private async consumirFlujo(
    cuerpo: ReadableStream<Uint8Array>,
    abortador: AbortController,
  ): Promise<void> {
    const lector = cuerpo.getReader();
    const decodificador = new TextDecoder();
    const parser = crearParserSse((frame) => this.procesarFrame(frame));
    const alAbortar = (): void => {
      void lector.cancel().catch(() => undefined);
    };

    abortador.signal.addEventListener('abort', alAbortar);

    try {
      while (!abortador.signal.aborted) {
        const { done, value } = await lector.read();
        if (done) {
          break;
        }
        if (value) {
          parser.alimentar(decodificador.decode(value, { stream: true }));
        }
      }
      if (!abortador.signal.aborted) {
        const restante = decodificador.decode();
        if (restante) {
          parser.alimentar(restante);
        }
      }
    } finally {
      abortador.signal.removeEventListener('abort', alAbortar);
      lector.releaseLock();
    }
  }

  private procesarFrame(frame: FrameTiempoReal): void {
    switch (frame.tipo) {
      case 'listo':
        this.intento = 0;
        this._ultimaConexion.set(new Date());
        this.cambiarEstado('conectado');
        this.emitirResincronizacion();
        break;
      case 'cambio':
        this.emitirCambio({
          dominios: frame.dominios,
          motivo: frame.motivo,
        });
        break;
      case 'estado':
        if (frame.estado === 'degradado') {
          this.cambiarEstado('degradado');
        } else {
          this.intento = 0;
          this.cambiarEstado('conectado');
          this.emitirResincronizacion();
        }
        break;
    }
  }

  private emitirCambio(cambio: CambioTiempoReal): void {
    if (this.documento.hidden) {
      return;
    }
    for (const suscripcion of [...this.callbacksCambio]) {
      if (cambio.dominios.some((dominio) => suscripcion.dominios.has(dominio))) {
        try {
          suscripcion.callback(cambio);
        } catch {
          // Un callback roto no corta el flujo ni a los demás suscriptores.
        }
      }
    }
  }

  private emitirResincronizacion(): void {
    if (this.documento.hidden) {
      return;
    }
    for (const callback of [...this.callbacksResincronizar]) {
      try {
        callback();
      } catch {
        // Un callback roto no corta el flujo ni a los demás suscriptores.
      }
    }
  }

  private cambiarEstado(nuevo: EstadoTiempoReal): void {
    if (this._estado() === nuevo) {
      return;
    }
    this._estado.set(nuevo);
    for (const callback of [...this.callbacksEstado]) {
      try {
        callback(nuevo);
      } catch {
        // Un consumidor roto no debe impedir la conexión.
      }
    }
  }

  private programarError(): void {
    this.intento += 1;
    this.programarReconexion(calcularRetrocesoMs(this.intento));
  }

  private programarRenovacion(): void {
    const transcurrido = this.reloj.ahora() - this.ultimaApertura;
    this.programarReconexion(
      Math.max(0, MINIMO_ENTRE_APERTURAS_MS - transcurrido),
    );
  }

  private programarReconexion(retrasoMs: number): void {
    if (!this._activo() || this.bloqueado) {
      return;
    }
    this.cancelarReintento();
    this.cambiarEstado('reconectando');
    const generacion = this.generacion;
    this.temporizadorReintento = this.reloj.programar(() => {
      this.temporizadorReintento = null;
      if (!this._activo() || generacion !== this.generacion) {
        return;
      }
      void this.abrirConexion(generacion);
    }, Math.max(0, Math.round(retrasoMs)));
  }

  private cancelarReintento(): void {
    if (this.temporizadorReintento !== null) {
      this.reloj.cancelar(this.temporizadorReintento);
      this.temporizadorReintento = null;
    }
  }

  private abortarConexion(): void {
    if (this.abortador) {
      this.abortador.abort();
      this.abortador = null;
    }
  }

  private descartarCuerpo(respuesta: Response): void {
    if (respuesta.body) {
      void respuesta.body.cancel().catch(() => undefined);
    }
  }

  private limpiarCallbacks(): void {
    this.callbacksCambio.clear();
    this.callbacksResincronizar.clear();
    this.callbacksEstado.clear();
  }
}
