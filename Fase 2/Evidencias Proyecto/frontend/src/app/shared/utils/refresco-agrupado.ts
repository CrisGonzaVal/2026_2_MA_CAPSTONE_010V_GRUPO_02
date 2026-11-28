/**
 * Temporizadores del agrupador. Se inyectan en los tests para controlar la
 * ventana de silencio y el tope con `fakeAsync`/`tick`, y en producción son
 * `setTimeout`/`clearTimeout`.
 */
export interface TemporizadoresRefresco {
  programar(accion: () => void, retrasoMs: number): number;
  cancelar(identificador: number): void;
}

/** Opciones del agrupador; los valores por defecto son los de la Feature 028. */
export interface OpcionesRefrescoAgrupado {
  /** Silencio tras la última solicitud antes de refrescar (250 ms por defecto). */
  quietudMs?: number;
  /** Tope desde la primera solicitud de la ráfaga (1 000 ms por defecto). */
  maxEsperaMs?: number;
  /** Implementación de temporizadores; en producción `setTimeout`. */
  temporizadores?: TemporizadoresRefresco;
}

/** Contrato público del agrupador que consumen las vistas. */
export interface RefrescoAgrupado {
  /** Registra una invalidación y agenda un único refresco por ráfaga. */
  solicitar(): void;
  /** Limpia temporizadores y la pendiente, sin lanzar ninguna ejecución. */
  cancelar(): void;
}

const QUIETUD_POR_DEFECTO_MS = 250;
const MAX_ESPERA_POR_DEFECTO_MS = 1_000;

const TEMPORIZADORES_POR_DEFECTO: TemporizadoresRefresco = {
  programar(accion, retrasoMs) {
    return setTimeout(accion, retrasoMs) as unknown as number;
  },
  cancelar(identificador) {
    clearTimeout(identificador);
  },
};

/**
 * Agrupador de refrescos de la Feature 028 (spec §5.4 regla 2, plan §6.2).
 *
 * Una ráfaga de invalidaciones produce como máximo una ejecución 250 ms después
 * de la última solicitud, y nunca más tarde de 1 s desde la primera. Si ya hay
 * una ejecución en vuelo, se guarda una sola pendiente que se lanza al terminar,
 * de modo que nunca hay dos refrescos solapados. Un error de `fn` se absorbe y
 * no impide solicitudes futuras.
 *
 * No depende de Angular ni usa `setInterval`: solo programa dos `setTimeout`
 * (la ventana de silencio y el tope de la ráfaga).
 */
export function crearRefrescoAgrupado(
  ejecutarRefresco: () => void | Promise<void>,
  opciones: OpcionesRefrescoAgrupado = {},
): RefrescoAgrupado {
  const quietudMs = opciones.quietudMs ?? QUIETUD_POR_DEFECTO_MS;
  const maxEsperaMs = opciones.maxEsperaMs ?? MAX_ESPERA_POR_DEFECTO_MS;
  const temporizadores = opciones.temporizadores ?? TEMPORIZADORES_POR_DEFECTO;

  let temporizadorQuietud: number | null = null;
  let temporizadorMaximo: number | null = null;
  let enVuelo = false;
  let pendiente = false;

  function limpiarTemporizadores(): void {
    if (temporizadorQuietud !== null) {
      temporizadores.cancelar(temporizadorQuietud);
      temporizadorQuietud = null;
    }
    if (temporizadorMaximo !== null) {
      temporizadores.cancelar(temporizadorMaximo);
      temporizadorMaximo = null;
    }
  }

  function terminar(): void {
    enVuelo = false;
    if (pendiente) {
      pendiente = false;
      ejecutar();
    }
  }

  function ejecutar(): void {
    if (enVuelo) {
      pendiente = true;
      return;
    }

    enVuelo = true;

    let resultado: unknown;
    try {
      resultado = ejecutarRefresco();
    } catch {
      terminar();
      return;
    }

    if (
      typeof resultado === 'object' &&
      resultado !== null &&
      typeof (resultado as PromiseLike<void>).then === 'function'
    ) {
      void Promise.resolve(resultado as PromiseLike<void>).then(
        terminar,
        terminar,
      );
    } else {
      terminar();
    }
  }

  function alDisparar(): void {
    limpiarTemporizadores();
    ejecutar();
  }

  function solicitar(): void {
    if (enVuelo) {
      pendiente = true;
      return;
    }

    if (temporizadorMaximo === null) {
      temporizadorMaximo = temporizadores.programar(alDisparar, maxEsperaMs);
    }
    if (temporizadorQuietud !== null) {
      temporizadores.cancelar(temporizadorQuietud);
    }
    temporizadorQuietud = temporizadores.programar(alDisparar, quietudMs);
  }

  function cancelar(): void {
    limpiarTemporizadores();
    pendiente = false;
  }

  return { solicitar, cancelar };
}
