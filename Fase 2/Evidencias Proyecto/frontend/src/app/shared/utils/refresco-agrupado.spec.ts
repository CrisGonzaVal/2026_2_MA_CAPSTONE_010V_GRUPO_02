import { fakeAsync, flushMicrotasks, tick } from '@angular/core/testing';

import {
  TemporizadoresRefresco,
  crearRefrescoAgrupado,
} from './refresco-agrupado';

/**
 * Agrupador de refrescos de la Feature 028 (D-10 y spec §5.4 regla 2).
 *
 * Es una utilidad pura: las pruebas usan `fakeAsync` para avanzar el reloj sin
 * esperas reales y confirman que una ráfaga produce una sola relectura, que la
 * espera máxima acota la ventana y que nunca hay dos ejecuciones solapadas.
 */
describe('crearRefrescoAgrupado', () => {
  it('agrupa 20 solicitudes en una sola ejecución tras 250 ms de silencio', fakeAsync(() => {
    const ejecuciones: number[] = [];
    const refresco = crearRefrescoAgrupado(() => {
      ejecuciones.push(1);
    });

    for (let solicitud = 0; solicitud < 20; solicitud += 1) {
      refresco.solicitar();
      tick(10);
    }

    // La última solicitud ocurrió a los 190 ms: aún no hay ejecución.
    expect(ejecuciones.length).toBe(0);

    tick(239);
    expect(ejecuciones.length).toBe(0);

    tick(1);
    expect(ejecuciones.length).toBe(1);

    tick(5_000);
    expect(ejecuciones.length).toBe(1);
  }));

  it('no espera más de 1 s desde la primera solicitud de una ráfaga continua', fakeAsync(() => {
    const ejecuciones: number[] = [];
    const refresco = crearRefrescoAgrupado(() => {
      ejecuciones.push(1);
    });

    for (let solicitud = 0; solicitud < 10; solicitud += 1) {
      refresco.solicitar();
      tick(100);
    }

    // El tope se cumple a los 1 000 ms aunque la ráfaga no se detenga.
    expect(ejecuciones.length).toBe(1);

    refresco.solicitar();
    tick(100);
    refresco.solicitar();
    tick(249);
    expect(ejecuciones.length).toBe(1);

    tick(1);
    expect(ejecuciones.length).toBe(2);
  }));

  it('respeta una ventana de silencio y un máximo configurables', fakeAsync(() => {
    const ejecuciones: number[] = [];
    const refresco = crearRefrescoAgrupado(
      () => {
        ejecuciones.push(1);
      },
      { quietudMs: 100, maxEsperaMs: 300 },
    );

    for (let solicitud = 0; solicitud < 5; solicitud += 1) {
      refresco.solicitar();
      tick(50);
    }

    // La última solicitud fue a los 200 ms y el tope vence a los 300 ms.
    expect(ejecuciones.length).toBe(0);
    tick(50);
    expect(ejecuciones.length).toBe(1);
  }));

  it('mantiene una ejecución en vuelo y como máximo una pendiente, sin solaparse', fakeAsync(() => {
    const resoluciones: Array<() => void> = [];
    let enVuelo = 0;
    let maximoEnVuelo = 0;
    let iniciadas = 0;

    const refresco = crearRefrescoAgrupado(() => {
      iniciadas += 1;
      enVuelo += 1;
      maximoEnVuelo = Math.max(maximoEnVuelo, enVuelo);
      return new Promise<void>((resolver) => {
        resoluciones.push(() => {
          enVuelo -= 1;
          resolver();
        });
      });
    });

    refresco.solicitar();
    tick(250);
    expect(iniciadas).toBe(1);
    expect(enVuelo).toBe(1);

    // Tres solicitudes durante el vuelo producen una sola pendiente.
    refresco.solicitar();
    refresco.solicitar();
    refresco.solicitar();
    tick(1_000);
    expect(iniciadas).toBe(1);
    expect(enVuelo).toBe(1);

    resoluciones.shift()?.();
    flushMicrotasks();
    expect(iniciadas).toBe(2);
    expect(enVuelo).toBe(1);

    resoluciones.shift()?.();
    flushMicrotasks();
    expect(enVuelo).toBe(0);
    expect(maximoEnVuelo).toBe(1);

    // No quedó una tercera ejecución encolada.
    tick(5_000);
    expect(iniciadas).toBe(2);
  }));

  it('cancelar() limpia temporizadores y no ejecuta; una nueva solicitud vuelve a funcionar', fakeAsync(() => {
    const ejecuciones: number[] = [];
    const refresco = crearRefrescoAgrupado(() => {
      ejecuciones.push(1);
    });

    refresco.solicitar();
    tick(100);
    refresco.cancelar();
    tick(5_000);
    expect(ejecuciones.length).toBe(0);

    refresco.solicitar();
    tick(249);
    expect(ejecuciones.length).toBe(0);
    tick(1);
    expect(ejecuciones.length).toBe(1);
  }));

  it('cancelar() durante un vuelo descarta la pendiente y no lanza otra ejecución', fakeAsync(() => {
    const resoluciones: Array<() => void> = [];
    let iniciadas = 0;

    const refresco = crearRefrescoAgrupado(() => {
      iniciadas += 1;
      return new Promise<void>((resolver) => {
        resoluciones.push(resolver);
      });
    });

    refresco.solicitar();
    tick(250);
    expect(iniciadas).toBe(1);

    refresco.solicitar();
    refresco.cancelar();
    resoluciones.shift()?.();
    flushMicrotasks();

    expect(iniciadas).toBe(1);
    tick(5_000);
    expect(iniciadas).toBe(1);
  }));

  it('tolera un error síncrono de la ejecución y sigue aceptando solicitudes', fakeAsync(() => {
    let intentos = 0;
    const refresco = crearRefrescoAgrupado(() => {
      intentos += 1;
      if (intentos === 1) {
        throw new Error('fallo de refresco');
      }
    });

    refresco.solicitar();
    expect(() => tick(250)).not.toThrow();
    expect(intentos).toBe(1);

    refresco.solicitar();
    tick(250);
    expect(intentos).toBe(2);
  }));

  it('tolera el rechazo de una ejecución asíncrona sin romper el agrupador', fakeAsync(() => {
    let intentos = 0;
    const refresco = crearRefrescoAgrupado(() => {
      intentos += 1;
      return Promise.reject(new Error('fallo asíncrono'));
    });

    refresco.solicitar();
    expect(() => {
      tick(250);
      flushMicrotasks();
    }).not.toThrow();
    expect(intentos).toBe(1);

    refresco.solicitar();
    tick(250);
    flushMicrotasks();
    expect(intentos).toBe(2);
  }));

  it('acepta temporizadores inyectables y no usa setInterval', fakeAsync(() => {
    const espiaIntervalo = spyOn(window, 'setInterval');
    const programar = jasmine
      .createSpy('programar')
      .and.callFake((accion: () => void, retrasoMs: number) =>
        setTimeout(accion, retrasoMs) as unknown as number,
      );
    const cancelar = jasmine
      .createSpy('cancelar')
      .and.callFake((identificador: number) => clearTimeout(identificador));
    const temporizadores: TemporizadoresRefresco = { programar, cancelar };
    const ejecuciones: number[] = [];

    const refresco = crearRefrescoAgrupado(
      () => {
        ejecuciones.push(1);
      },
      { temporizadores },
    );

    refresco.solicitar();
    const retrasos = programar.calls
      .allArgs()
      .map((argumentos) => argumentos[1] as number);
    expect(retrasos).toContain(250);
    expect(retrasos).toContain(1_000);

    // Una segunda solicitud reinicia solo la ventana de silencio.
    refresco.solicitar();
    expect(programar).toHaveBeenCalledTimes(3);
    expect(cancelar).toHaveBeenCalled();

    tick(250);
    expect(ejecuciones.length).toBe(1);
    expect(espiaIntervalo).not.toHaveBeenCalled();
  }));
});
