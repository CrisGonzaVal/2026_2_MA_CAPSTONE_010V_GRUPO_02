import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';

import { URL_API } from '../../shared/config/url-api';
import { AutenticacionService, EstadoIdentidad } from './auth.service';
import {
  CambioTiempoReal,
  EstadoTiempoReal,
  FETCH_TIEMPO_REAL,
  FrameTiempoReal,
  MINIMO_ENTRE_APERTURAS_MS,
  RELOJ_TIEMPO_REAL,
  RelojTiempoReal,
  TiempoRealService,
  calcularRetrocesoMs,
  crearParserSse,
  leerRetryAfterMs,
} from './tiempo-real.service';

/**
 * El hub es la única conexión de la pestaña con `GET /api/v1/eventos/`.
 *
 * Estos specs fijan su contrato sin red real: un `fetch` falso devuelve
 * `Response` con `ReadableStream`, un reloj falso controla el retroceso y un
 * doble de `AutenticacionService` publica la sesión. La lectura del flujo se
 * prueba con specs `async` (T0: `fakeAsync` no resuelve la promesa del reader);
 * el parser puro y el calendario del retroceso se prueban sin temporizadores
 * reales.
 */
describe('TiempoRealService', () => {
  class AutenticacionFalsa {
    readonly autenticado = signal(true);
    readonly identidad = signal<EstadoIdentidad>('disponible');
    readonly estaAutenticado = this.autenticado.asReadonly();
    readonly estadoIdentidad = this.identidad.asReadonly();
    readonly obtenerToken = jasmine
      .createSpy('obtenerToken')
      .and.resolveTo('token-de-prueba');

    cerrarSesion(): void {
      this.autenticado.set(false);
    }
  }

  class RelojFalso implements RelojTiempoReal {
    private instante = 0;
    private siguienteId = 1;
    private readonly pendientes = new Map<
      number,
      { accion: () => void; retraso: number }
    >();

    get retrasos(): number[] {
      return [...this.pendientes.values()].map((temporizador) => temporizador.retraso);
    }

    ahora(): number {
      return this.instante;
    }

    programar(accion: () => void, retrasoMs: number): number {
      const identificador = this.siguienteId;
      this.siguienteId += 1;
      this.pendientes.set(identificador, { accion, retraso: retrasoMs });
      return identificador;
    }

    cancelar(identificador: number): void {
      this.pendientes.delete(identificador);
    }

    avanzar(ms: number): void {
      this.instante += ms;
    }

    dispararSiguiente(): void {
      const primera = this.pendientes.entries().next();
      if (primera.done) {
        throw new Error('No hay temporizador programado');
      }
      const [identificador, temporizador] = primera.value;
      this.pendientes.delete(identificador);
      this.instante += temporizador.retraso;
      temporizador.accion();
    }

    limpiar(): void {
      this.pendientes.clear();
    }
  }

  interface FlujoFalso {
    respuesta: Response;
    emitir(texto: string): void;
    cerrar(): void;
  }

  function crearFlujoFalso(): FlujoFalso {
    let controlador: ReadableStreamDefaultController<Uint8Array> | null = null;
    const flujo = new ReadableStream<Uint8Array>({
      start(control) {
        controlador = control;
      },
    });
    const codificador = new TextEncoder();

    return {
      respuesta: new Response(flujo, { status: 200 }),
      emitir(texto: string): void {
        controlador?.enqueue(codificador.encode(texto));
      },
      cerrar(): void {
        try {
          controlador?.close();
        } catch {
          // El lector ya canceló el flujo.
        }
      },
    };
  }

  const microtarea = (): Promise<void> =>
    new Promise<void>((resolver) => setTimeout(resolver));

  async function esperar(condicion: () => boolean): Promise<void> {
    for (let intento = 0; intento < 100 && !condicion(); intento += 1) {
      await microtarea();
    }
    if (!condicion()) {
      throw new Error('La condición del test no se cumplió');
    }
  }

  let autenticacion: AutenticacionFalsa;
  let reloj: RelojFalso;
  let flujo: FlujoFalso;
  let responder: (url: string, opciones: RequestInit) => Response | Promise<Response>;
  let fetchFalso: jasmine.Spy;
  let espiaOculto: jasmine.Spy;
  let servicio: TiempoRealService;

  async function iniciarYEsperar(): Promise<void> {
    servicio.iniciar();
    await esperar(() => fetchFalso.calls.count() > 0);
    await microtarea();
  }

  beforeEach(() => {
    autenticacion = new AutenticacionFalsa();
    reloj = new RelojFalso();
    flujo = crearFlujoFalso();
    responder = () => flujo.respuesta;
    fetchFalso = jasmine
      .createSpy('fetch')
      .and.callFake((url: string, opciones?: RequestInit) =>
        Promise.resolve(responder(url, opciones ?? {})),
      );

    TestBed.configureTestingModule({
      providers: [
        { provide: AutenticacionService, useValue: autenticacion },
        { provide: FETCH_TIEMPO_REAL, useValue: fetchFalso },
        { provide: RELOJ_TIEMPO_REAL, useValue: reloj },
      ],
    });

    // `DOCUMENT` es el documento real de Karma; se fija `hidden` para que el
    // resultado no dependa del estado de la pestaña headless.
    espiaOculto = spyOnProperty(document, 'hidden', 'get').and.returnValue(false);
    servicio = TestBed.inject(TiempoRealService);
  });

  afterEach(() => {
    servicio.detener();
    reloj.limpiar();
  });

  describe('parser SSE', () => {
    it('interpreta listo, cambio y estado, e ignora comentarios y líneas vacías', () => {
      const frames: FrameTiempoReal[] = [];
      const parser = crearParserSse((frame) => frames.push(frame));

      parser.alimentar(': latido\n\n');
      parser.alimentar('\n\n');
      parser.alimentar(
        'event: listo\ndata: {"dominios":["pedidos","inventario","dashboard"]}\n\n',
      );
      parser.alimentar(
        'event: cambio\ndata: {"dominios":["pedidos","inventario"],"motivo":"retiro"}\n\n',
      );
      parser.alimentar('event: estado\ndata: {"estado":"degradado"}\n\n');
      parser.alimentar('event: estado\ndata: {"estado":"recuperado"}\n\n');

      expect(frames).toEqual([
        { tipo: 'listo', dominios: ['pedidos', 'inventario', 'dashboard'] },
        {
          tipo: 'cambio',
          dominios: ['pedidos', 'inventario'],
          motivo: 'retiro',
        },
        { tipo: 'estado', estado: 'degradado' },
        { tipo: 'estado', estado: 'recuperado' },
      ]);
    });

    it('tolera frames partidos entre chunks y finales de línea CRLF', () => {
      const frames: FrameTiempoReal[] = [];
      const parser = crearParserSse((frame) => frames.push(frame));
      const texto =
        'event: cambio\r\ndata: {"dominios":["inventario"],"motivo":"movimiento"}\r\n\r\n';

      for (const caracter of texto) {
        parser.alimentar(caracter);
      }

      expect(frames).toEqual([
        {
          tipo: 'cambio',
          dominios: ['inventario'],
          motivo: 'movimiento',
        },
      ]);
    });

    it('ignora tipos desconocidos y data inválido sin romper el parser', () => {
      const frames: FrameTiempoReal[] = [];
      const parser = crearParserSse((frame) => frames.push(frame));

      parser.alimentar('event: futuro\ndata: {"dominios":["pedidos"]}\n\n');
      parser.alimentar('event: cambio\ndata: {no-json}\n\n');
      parser.alimentar('event: cambio\ndata: {"dominios":["otro"],"motivo":"retiro"}\n\n');
      parser.alimentar('event: cambio\ndata: {"dominios":["pedidos"],"motivo":"inventado"}\n\n');
      parser.alimentar('event: estado\ndata: {"estado":"roto"}\n\n');
      parser.alimentar('event: listo\ndata: {"dominios":"pedidos"}\n\n');
      parser.alimentar('data: {"dominios":["pedidos"],"motivo":"alta"}\n\n');

      expect(frames).toEqual([]);

      parser.alimentar('event: cambio\ndata: {"dominios":["compras"],"motivo":"cambio"}\n\n');

      expect(frames).toEqual([
        { tipo: 'cambio', dominios: ['compras'], motivo: 'cambio' },
      ]);
    });
  });

  describe('calendario de reconexión', () => {
    it('calcula el retroceso exponencial 1/2/4/8/16 con jitter y tope de 30 s', () => {
      const sinJitter = (): number => 0.5;

      expect([1, 2, 3, 4, 5].map((intento) => calcularRetrocesoMs(intento, sinJitter))).toEqual([
        1000, 2000, 4000, 8000, 16000,
      ]);
      expect(calcularRetrocesoMs(6, sinJitter)).toBe(30000);
      expect(calcularRetrocesoMs(1, () => 0)).toBe(800);
      expect(calcularRetrocesoMs(1, () => 1)).toBe(1200);
      expect(calcularRetrocesoMs(20, () => 1)).toBe(30000);
    });

    it('interpreta Retry-After en segundos y descarta valores inválidos', () => {
      expect(leerRetryAfterMs('7')).toBe(7000);
      expect(leerRetryAfterMs('0')).toBe(0);
      expect(leerRetryAfterMs(null)).toBeNull();
      expect(leerRetryAfterMs('mañana')).toBeNull();
    });
  });

  describe('conexión', () => {
    it('usa fetch con Bearer en cabecera, Accept SSE y cache no-store, sin EventSource', async () => {
      const espiaEventSource = spyOn(globalThis, 'EventSource');

      await iniciarYEsperar();

      expect(espiaEventSource).not.toHaveBeenCalled();
      expect(fetchFalso).toHaveBeenCalledTimes(1);
      expect(autenticacion.obtenerToken).toHaveBeenCalledTimes(1);

      const [url, opciones] = fetchFalso.calls.mostRecent().args as [
        string,
        RequestInit,
      ];
      expect(url).toBe(`${URL_API}/eventos/`);
      expect(opciones.method).toBe('GET');
      expect(opciones.cache).toBe('no-store');
      expect(opciones.headers).toEqual({
        Authorization: 'Bearer token-de-prueba',
        Accept: 'text/event-stream',
      });
      expect(opciones.signal).toBeInstanceOf(AbortSignal);
      // El token solo viaja en la cabecera: ni en la URL ni en almacenamiento.
      expect(url).not.toContain('token');
    });

    it('no abre dos conexiones simultáneas', async () => {
      await iniciarYEsperar();

      servicio.iniciar();
      TestBed.flushEffects();
      document.dispatchEvent(new Event('visibilitychange'));
      await microtarea();

      expect(fetchFalso).toHaveBeenCalledTimes(1);
    });

    it('al recibir listo queda conectado, registra la hora y resincroniza una vez', async () => {
      const resincronizaciones: number[] = [];
      servicio.alResincronizar(() => resincronizaciones.push(1));

      await iniciarYEsperar();
      expect(servicio.estado()).toBe('conectando');

      flujo.emitir('event: listo\ndata: {"dominios":["pedidos","inventario"]}\n\n');
      await esperar(() => servicio.estado() === 'conectado');

      expect(resincronizaciones.length).toBe(1);
      expect(servicio.ultimaConexion()).toBeInstanceOf(Date);
    });

    it('un cambio notifica solo a los dominios suscritos', async () => {
      const dePedidos: CambioTiempoReal[] = [];
      const deDashboard: CambioTiempoReal[] = [];
      servicio.alCambio(['pedidos'], (cambio) => dePedidos.push(cambio));
      servicio.alCambio(['dashboard'], (cambio) => deDashboard.push(cambio));

      await iniciarYEsperar();
      flujo.emitir('event: listo\ndata: {"dominios":["pedidos"]}\n\n');
      await esperar(() => servicio.estado() === 'conectado');

      flujo.emitir(
        'event: cambio\ndata: {"dominios":["pedidos","inventario"],"motivo":"retiro"}\n\n',
      );
      await esperar(() => dePedidos.length === 1);

      expect(dePedidos[0].dominios).toEqual(['pedidos', 'inventario']);
      expect(dePedidos[0].motivo).toBe('retiro');
      expect(deDashboard.length).toBe(0);
    });

    it('degradado no bloquea y recuperado resincroniza una vez', async () => {
      const resincronizaciones: number[] = [];
      const cambios: CambioTiempoReal[] = [];
      servicio.alResincronizar(() => resincronizaciones.push(1));
      servicio.alCambio(['pedidos'], (cambio) => cambios.push(cambio));

      await iniciarYEsperar();
      flujo.emitir('event: listo\ndata: {"dominios":["pedidos"]}\n\n');
      await esperar(() => servicio.estado() === 'conectado');
      expect(resincronizaciones.length).toBe(1);

      flujo.emitir('event: estado\ndata: {"estado":"degradado"}\n\n');
      await esperar(() => servicio.estado() === 'degradado');
      expect(resincronizaciones.length).toBe(1);

      // La app sigue operable: un cambio posterior se sigue entregando.
      flujo.emitir(
        'event: cambio\ndata: {"dominios":["pedidos"],"motivo":"aprobacion"}\n\n',
      );
      await esperar(() => cambios.length === 1);

      flujo.emitir('event: estado\ndata: {"estado":"recuperado"}\n\n');
      await esperar(() => servicio.estado() === 'conectado');
      expect(resincronizaciones.length).toBe(2);
    });

    it('una pestaña oculta no refresca y al volver a foco resincroniza una sola vez', async () => {
      const resincronizaciones: number[] = [];
      const cambios: CambioTiempoReal[] = [];
      servicio.alResincronizar(() => resincronizaciones.push(1));
      servicio.alCambio(['pedidos'], (cambio) => cambios.push(cambio));

      await iniciarYEsperar();
      flujo.emitir('event: listo\ndata: {"dominios":["pedidos"]}\n\n');
      await esperar(() => servicio.estado() === 'conectado');
      expect(resincronizaciones.length).toBe(1);

      espiaOculto.and.returnValue(true);
      document.dispatchEvent(new Event('visibilitychange'));

      flujo.emitir(
        'event: cambio\ndata: {"dominios":["pedidos"],"motivo":"alta"}\n\n',
      );
      await microtarea();
      expect(cambios.length).toBe(0);
      expect(resincronizaciones.length).toBe(1);

      espiaOculto.and.returnValue(false);
      document.dispatchEvent(new Event('visibilitychange'));
      document.dispatchEvent(new Event('visibilitychange'));
      await microtarea();

      expect(resincronizaciones.length).toBe(2);
      expect(fetchFalso).toHaveBeenCalledTimes(1);
    });

    it('ignora frames inválidos sin cerrar la conexión', async () => {
      const cambios: CambioTiempoReal[] = [];
      servicio.alCambio(['pedidos'], (cambio) => cambios.push(cambio));

      await iniciarYEsperar();
      flujo.emitir('event: listo\ndata: {"dominios":["pedidos"]}\n\n');
      await esperar(() => servicio.estado() === 'conectado');

      flujo.emitir('event: cambio\ndata: {roto}\n\n');
      flujo.emitir('event: futuro\ndata: {"dominios":["pedidos"]}\n\n');
      flujo.emitir(
        'event: cambio\ndata: {"dominios":["pedidos"],"motivo":"alta"}\n\n',
      );
      await esperar(() => cambios.length === 1);

      expect(cambios.length).toBe(1);
      expect(servicio.estado()).toBe('conectado');
    });

    it('publica las transiciones de estado por alEstado', async () => {
      const estados: EstadoTiempoReal[] = [];
      servicio.alEstado((estado) => estados.push(estado));
      expect(estados).toEqual(['inactivo']);

      await iniciarYEsperar();
      flujo.emitir('event: listo\ndata: {"dominios":["pedidos"]}\n\n');
      await esperar(() => servicio.estado() === 'conectado');

      expect(estados).toEqual(['inactivo', 'conectando', 'conectado']);
    });
  });

  describe('fallos y reconexión', () => {
    for (const estadoHttp of [401, 403]) {
      it(`ante ${estadoHttp} cierra y no reintenta`, async () => {
        responder = () => new Response(null, { status: estadoHttp });

        await iniciarYEsperar();
        await esperar(() => servicio.estado() === 'inactivo');
        await microtarea();

        expect(fetchFalso).toHaveBeenCalledTimes(1);
        expect(reloj.retrasos).toEqual([]);
      });
    }

    it('ante 429 espera Retry-After antes de reabrir', async () => {
      responder = () =>
        new Response(null, {
          status: 429,
          headers: { 'Retry-After': '7' },
        });

      await iniciarYEsperar();
      await esperar(() => reloj.retrasos.length === 1);

      expect(reloj.retrasos[0]).toBe(7000);
      expect(servicio.estado()).toBe('reconectando');

      responder = () => flujo.respuesta;
      reloj.dispararSiguiente();
      await esperar(() => fetchFalso.calls.count() === 2);
    });

    it('ante 5xx reintenta con retroceso 1/2/4/8/16/30 y tope de 30 s', async () => {
      responder = () => new Response(null, { status: 500 });

      await iniciarYEsperar();

      const rangos: Array<[number, number]> = [
        [800, 1200],
        [1600, 2400],
        [3200, 4800],
        [6400, 9600],
        [12800, 19200],
        [24000, 30000],
      ];

      for (let intento = 0; intento < rangos.length; intento += 1) {
        await esperar(() => reloj.retrasos.length === 1);
        const retraso = reloj.retrasos[0];
        expect(retraso).toBeGreaterThanOrEqual(rangos[intento][0]);
        expect(retraso).toBeLessThanOrEqual(rangos[intento][1]);
        reloj.dispararSiguiente();
        await esperar(() => fetchFalso.calls.count() === intento + 2);
      }
    });

    it('un cierre limpio reabre respetando el mínimo de 30 s entre aperturas', async () => {
      await iniciarYEsperar();
      flujo.emitir('event: listo\ndata: {"dominios":["pedidos"]}\n\n');
      await esperar(() => servicio.estado() === 'conectado');

      reloj.avanzar(5000);
      flujo.cerrar();
      await esperar(() => reloj.retrasos.length === 1);

      expect(reloj.retrasos[0]).toBe(MINIMO_ENTRE_APERTURAS_MS - 5000);
      expect(servicio.estado()).toBe('reconectando');

      responder = () => crearFlujoFalso().respuesta;
      reloj.dispararSiguiente();
      await esperar(() => fetchFalso.calls.count() === 2);
    });

    it('sin token no abre el canal ni programa reintentos', async () => {
      autenticacion.obtenerToken.and.resolveTo(null);

      servicio.iniciar();
      await esperar(() => servicio.estado() === 'inactivo');

      expect(fetchFalso).not.toHaveBeenCalled();
      expect(reloj.retrasos).toEqual([]);
    });
  });

  describe('cierre y sesión', () => {
    it('detener aborta la conexión, deja inactivo y limpia los callbacks', async () => {
      const cambios: CambioTiempoReal[] = [];
      servicio.alCambio(['pedidos'], (cambio) => cambios.push(cambio));

      await iniciarYEsperar();
      flujo.emitir('event: listo\ndata: {"dominios":["pedidos"]}\n\n');
      await esperar(() => servicio.estado() === 'conectado');

      const senal = (fetchFalso.calls.mostRecent().args[1] as RequestInit)
        .signal as AbortSignal;

      servicio.detener();

      expect(senal.aborted).toBe(true);
      expect(servicio.estado()).toBe('inactivo');
      expect(reloj.retrasos).toEqual([]);

      // Al reiniciar, el callback anterior ya no está registrado.
      flujo = crearFlujoFalso();
      responder = () => flujo.respuesta;
      servicio.iniciar();
      await esperar(() => fetchFalso.calls.count() === 2);
      await microtarea();
      flujo.emitir('event: listo\ndata: {"dominios":["pedidos"]}\n\n');
      await esperar(() => servicio.estado() === 'conectado');
      flujo.emitir(
        'event: cambio\ndata: {"dominios":["pedidos"],"motivo":"alta"}\n\n',
      );
      await microtarea();

      expect(cambios.length).toBe(0);
    });

    it('el logout aborta, no reintenta y deja el hub inactivo', async () => {
      await iniciarYEsperar();
      const senal = (fetchFalso.calls.mostRecent().args[1] as RequestInit)
        .signal as AbortSignal;

      autenticacion.cerrarSesion();
      TestBed.flushEffects();
      await esperar(() => servicio.estado() === 'inactivo');
      await microtarea();

      expect(senal.aborted).toBe(true);
      expect(reloj.retrasos).toEqual([]);
      expect(fetchFalso).toHaveBeenCalledTimes(1);
    });

    it('no guarda el token en localStorage, cookie ni URL', async () => {
      const guardar = spyOn(Storage.prototype, 'setItem');
      const cookieAntes = document.cookie;

      await iniciarYEsperar();
      flujo.emitir('event: listo\ndata: {"dominios":["pedidos"]}\n\n');
      await esperar(() => servicio.estado() === 'conectado');
      servicio.detener();

      expect(guardar).not.toHaveBeenCalled();
      expect(document.cookie).toBe(cookieAntes);
      expect(fetchFalso.calls.mostRecent().args[0]).toBe(`${URL_API}/eventos/`);
    });
  });
});
