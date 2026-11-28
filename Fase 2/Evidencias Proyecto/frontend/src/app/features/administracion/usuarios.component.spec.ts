import { provideHttpClient } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { WritableSignal, signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';

import { AutenticacionService } from '../../core/services/auth.service';
import { URL_API } from '../../shared/config/url-api';
import {
  DepartamentoGestion,
  IdentidadAutenticada,
  Rol,
  Sede,
  Usuario,
  UsuarioInvitacionRespuesta,
} from '../../shared/interfaces';
import { UsuariosComponent } from './usuarios.component';

/**
 * Feature 012 (T10) y Feature 017 (T9): vista de usuarios locales.
 *
 * Seam bajo prueba: la interfaz pública del componente — DOM y peticiones reales
 * del `AdministracionService` bajo `HttpTestingController`. Se verifica el
 * listado con el estado de invitación persistido separado del vínculo local, el
 * alta con invitación y copia del enlace solo en la respuesta inmediata, los
 * motivos obligatorios de edición y estado, los errores 409/422/503 y —desde
 * T12— el reenvío ordinario (`POST /usuarios/{id}/invitacion/reenvio`) con su
 * restricción por rol/estado y la secuencia reactivar (con motivo) → reenviar.
 */
describe('UsuariosComponent', () => {
  const RUTA_USUARIOS = `${URL_API}/usuarios/`;
  const RUTA_ROLES = `${URL_API}/usuarios/roles`;
  const RUTA_DEPARTAMENTOS = `${URL_API}/organizacion/departamentos`;
  const RUTA_SEDES = `${URL_API}/organizacion/sedes`;

  const ROLES: Rol[] = [
    { rol_id: 1, nombre_rol: 'Administrador', descripcion: null },
    { rol_id: 3, nombre_rol: 'Bodeguero', descripcion: null },
    { rol_id: 4, nombre_rol: 'Solicitante', descripcion: null },
  ];

  const ROLES_CUATRO: Rol[] = [
    { rol_id: 1, nombre_rol: 'Superadmin', descripcion: null },
    { rol_id: 2, nombre_rol: 'Administrador', descripcion: null },
    { rol_id: 3, nombre_rol: 'Bodeguero', descripcion: null },
    { rol_id: 4, nombre_rol: 'Solicitante', descripcion: null },
  ];

  function identidad(rol: string): IdentidadAutenticada {
    return {
      usuario_id: 1,
      sub: 'user_prueba',
      nombre: 'Sonda',
      apellido: 'Rol',
      correo: 'sonda@example.com',
      rol,
      institucion: null,
      sede: null,
      departamento: null,
    };
  }

  const DEPARTAMENTOS: DepartamentoGestion[] = [
    {
      departamento_id: 10,
      nombre_dep: 'Logística',
      descripcion: null,
      institucion_id: 'INSTA',
      sede_id: null,
      activo: true,
    },
  ];

  const SEDES: Sede[] = [
    { sede_id: 1, nombre: 'Sede Central', direccion: null, institucion_id: 'INSTA', activo: true },
    { sede_id: 2, nombre: 'Bodega Norte', direccion: null, institucion_id: 'INSTA', activo: true },
  ];

  function usuario(sobrescribir: Partial<Usuario> = {}): Usuario {
    return {
      usuario_id: 1,
      nombre: 'Ana',
      apellido: 'Pérez',
      correo: 'ana@example.com',
      departamento_id: 10,
      rol_id: 3,
      sede_id: 1,
      activo: true,
      estado_invitacion: 'aceptada',
      ...sobrescribir,
    };
  }

  function invitacion(
    sobrescribir: Partial<UsuarioInvitacionRespuesta> = {},
  ): UsuarioInvitacionRespuesta {
    return {
      ...usuario(),
      url_invitacion: null,
      ...sobrescribir,
    };
  }

  let fixture: ComponentFixture<UsuariosComponent>;
  let httpMock: HttpTestingController;
  let identidadFalsa: WritableSignal<IdentidadAutenticada | null>;
  let portapapeles: string[];

  beforeEach(async () => {
    identidadFalsa = signal<IdentidadAutenticada | null>(identidad('Administrador'));
    portapapeles = [];
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: {
        writeText: (texto: string) => {
          portapapeles.push(texto);
          return Promise.resolve();
        },
      },
    });

    await TestBed.configureTestingModule({
      imports: [UsuariosComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: AutenticacionService, useValue: { identidad: identidadFalsa } },
      ],
    }).compileComponents();

    httpMock = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(UsuariosComponent);
  });

  afterEach(() => {
    httpMock.verify({ ignoreCancelled: true });
  });

  function texto(): string {
    return (fixture.nativeElement as HTMLElement).textContent ?? '';
  }

  function boton(etiqueta: string): HTMLButtonElement | undefined {
    return Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll('button'),
    ).find((b) => new RegExp(etiqueta, 'i').test(b.textContent ?? ''));
  }

  function montar(
    usuarios: Usuario[] = [usuario()],
    roles: Rol[] = ROLES,
    departamentos: DepartamentoGestion[] = DEPARTAMENTOS,
    sedes: Sede[] = SEDES,
  ): void {
    fixture.detectChanges();
    httpMock.expectOne(RUTA_USUARIOS).flush(usuarios);
    httpMock.expectOne(RUTA_ROLES).flush(roles);
    httpMock.expectOne(RUTA_DEPARTAMENTOS).flush(departamentos);
    httpMock.expectOne(RUTA_SEDES).flush(sedes);
    fixture.detectChanges();
  }

  function abrirAlta(): void {
    boton('nuevo usuario')?.click();
    fixture.detectChanges();
  }

  function selectAlta(id: string): HTMLSelectElement | null {
    return (fixture.nativeElement as HTMLElement).querySelector<HTMLSelectElement>(
      id,
    );
  }

  function opcionesSelectAlta(id: string): string[] {
    return Array.from(selectAlta(id)?.options ?? []).map(
      (opcion) => (opcion.textContent ?? '').trim(),
    );
  }

  function elegirRol(rolId: number): void {
    fixture.componentInstance.formularioCreacion.controls.rol_id.setValue(rolId);
    fixture.detectChanges();
  }

  function elegirSede(sedeId: number | null): void {
    fixture.componentInstance.formularioCreacion.controls.sede_id.setValue(sedeId);
    fixture.detectChanges();
  }

  function elegirDepartamento(departamentoId: number): void {
    fixture.componentInstance.formularioCreacion.controls.departamento_id.setValue(
      departamentoId,
    );
    fixture.detectChanges();
  }

  /** Departamentos de dos sedes, uno sin sede y un «Suministros» preexistente. */
  const DEPARTAMENTOS_POR_SEDE: DepartamentoGestion[] = [
    {
      departamento_id: 11,
      nombre_dep: 'Logística',
      descripcion: null,
      institucion_id: 'INSTA',
      sede_id: 1,
      activo: true,
    },
    {
      departamento_id: 12,
      nombre_dep: 'Compras',
      descripcion: null,
      institucion_id: 'INSTA',
      sede_id: 2,
      activo: true,
    },
    {
      departamento_id: 13,
      nombre_dep: 'Sin sede',
      descripcion: null,
      institucion_id: 'INSTA',
      sede_id: null,
      activo: true,
    },
    {
      departamento_id: 14,
      nombre_dep: '  SUMINISTROS  ',
      descripcion: null,
      institucion_id: 'INSTA',
      sede_id: null,
      activo: true,
    },
  ];

  /** Catálogo de edición: incluye un legado «Biblioteca» de la semilla. */
  const DEPARTAMENTOS_EDICION: DepartamentoGestion[] = [
    {
      departamento_id: 11,
      nombre_dep: 'Logística',
      descripcion: null,
      institucion_id: 'INSTA',
      sede_id: 1,
      activo: true,
    },
    {
      departamento_id: 12,
      nombre_dep: 'Compras',
      descripcion: null,
      institucion_id: 'INSTA',
      sede_id: 2,
      activo: true,
    },
    {
      departamento_id: 13,
      nombre_dep: 'Sin sede',
      descripcion: null,
      institucion_id: 'INSTA',
      sede_id: null,
      activo: true,
    },
    {
      departamento_id: 14,
      nombre_dep: 'Suministros',
      descripcion: null,
      institucion_id: 'INSTA',
      sede_id: null,
      activo: true,
    },
    {
      departamento_id: 15,
      nombre_dep: 'Biblioteca',
      descripcion: null,
      institucion_id: 'INSTA',
      sede_id: 1,
      activo: true,
    },
  ];

  /** El catálogo antes de que «Suministros» exista en el tenant (D-8/D-15). */
  const DEPARTAMENTOS_EDICION_SIN_SUMINISTROS: DepartamentoGestion[] =
    DEPARTAMENTOS_EDICION.filter(
      (departamento) => departamento.departamento_id !== 14,
    );

  /** Tenant que solo tiene el departamento automático «Suministros». */
  const DEPARTAMENTOS_SOLO_SUMINISTROS: DepartamentoGestion[] = [
    DEPARTAMENTOS_EDICION[3],
  ];

  function opcionesRolAlta(): string[] {
    return Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll(
        '#crear-usuario-rol option',
      ),
    ).map((o) => o.textContent?.trim() ?? '');
  }

  function opcionesRolEdicion(): string[] {
    return Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll(
        '#editar-usuario-rol option',
      ),
    ).map((o) => o.textContent?.trim() ?? '');
  }

  function rellenarAlta(sobrescribir: Record<string, unknown> = {}): void {
    fixture.componentInstance.formularioCreacion.patchValue({
      nombre: 'Nuevo',
      apellido: 'Solicitante',
      correo: 'nuevo@example.com',
      rol_id: 4,
      departamento_id: 10,
      ...sobrescribir,
    });
    fixture.detectChanges();
  }

  function rellenarDatosAlta(): void {
    fixture.componentInstance.formularioCreacion.patchValue({
      nombre: 'Nuevo',
      apellido: 'Solicitante',
      correo: 'nuevo@example.com',
    });
    fixture.detectChanges();
  }

  function abrirEdicion(): void {
    boton('editar')?.click();
    fixture.detectChanges();
  }

  function selectEdicion(id: string): HTMLSelectElement | null {
    return (fixture.nativeElement as HTMLElement).querySelector<HTMLSelectElement>(
      id,
    );
  }

  function opcionesSelectEdicion(id: string): string[] {
    return Array.from(selectEdicion(id)?.options ?? []).map(
      (opcion) => (opcion.textContent ?? '').trim(),
    );
  }

  function elegirRolEdicion(rolId: number): void {
    fixture.componentInstance.formularioEdicion.controls.rol_id.setValue(rolId);
    fixture.detectChanges();
  }

  function elegirSedeEdicion(sedeId: number | null): void {
    fixture.componentInstance.formularioEdicion.controls.sede_id.setValue(sedeId);
    fixture.detectChanges();
  }

  function elegirDepartamentoEdicion(departamentoId: number): void {
    fixture.componentInstance.formularioEdicion.controls.departamento_id.setValue(
      departamentoId,
    );
    fixture.detectChanges();
  }

  function completarMotivoEdicion(): void {
    fixture.componentInstance.motivoEdicion.patchValue({
      codigo: 'reasignacion_organizacional',
      texto: '',
    });
    fixture.detectChanges();
  }

  /** Consume la recarga (catálogo + listado) que sigue a una edición guardada. */
  function confirmarRecarga(
    usuarios: Usuario[] = [usuario()],
    departamentos: DepartamentoGestion[] = DEPARTAMENTOS_EDICION,
  ): void {
    httpMock.expectOne(RUTA_USUARIOS).flush(usuarios);
    httpMock.expectOne(RUTA_ROLES).flush(ROLES);
    httpMock.expectOne(RUTA_DEPARTAMENTOS).flush(departamentos);
    httpMock.expectOne(RUTA_SEDES).flush(SEDES);
    fixture.detectChanges();
  }

  /**
   * Selecciona una opción real de un `<select>` y dispara `change`, como el
   * navegador. Los casos con `setValue` no detectaban que `[value]` entregaba
   * el id como string y rompía los `computed` de rol (corrección post-recorrido).
   */
  function elegirOpcionDom(selector: string, etiqueta: string): void {
    const select = (fixture.nativeElement as HTMLElement).querySelector<HTMLSelectElement>(
      selector,
    );
    if (!select) {
      throw new Error(`No existe el select ${selector}`);
    }
    const indice = Array.from(select.options).findIndex(
      (opcion) => (opcion.textContent ?? '').trim() === etiqueta,
    );
    if (indice < 0) {
      throw new Error(`No existe la opción «${etiqueta}» en ${selector}`);
    }
    select.selectedIndex = indice;
    select.dispatchEvent(new Event('change'));
    fixture.detectChanges();
  }

  it('AC-8: renderiza rol, departamento, estado y sede del Bodeguero', () => {
    montar();
    const visible = texto();
    expect(visible).toContain('Ana Pérez');
    expect(visible).toContain('ana@example.com');
    expect(visible).toContain('Bodeguero');
    expect(visible).toContain('Logística');
    expect(visible).toContain('Activo');
    expect(visible).toContain('Sede Central');
  });

  it('AC-5: muestra el estado de invitación persistido separado del vínculo local', () => {
    montar([
      usuario({ usuario_id: 1, activo: false, estado_invitacion: 'pendiente' }),
      usuario({ usuario_id: 2, nombre: 'Beto', activo: true, estado_invitacion: 'aceptada' }),
    ]);
    const visible = texto();
    expect(visible).toContain('Inactivo');
    expect(visible).toContain('Activo');
    expect(visible).toContain('Invitación: Pendiente');
    expect(visible).toContain('Invitación: Aceptada');
  });

  it('AC-5: un estado de invitación desconocido se presenta como «No disponible»', () => {
    montar([usuario({ estado_invitacion: undefined })]);
    expect(texto()).toContain('Invitación: No disponible');
    expect(texto()).not.toContain('Invitación: Aceptada');
  });

  it('AC-5: el listado nunca muestra una URL de invitación', () => {
    montar([usuario({ estado_invitacion: 'pendiente' })]);
    expect(texto()).not.toContain('http');
    expect(texto().toLowerCase()).not.toContain('copiar enlace');
  });

  it('AC-8/AC-11: un usuario inactivo se muestra como tal y ofrece Reactivar', () => {
    montar([usuario({ activo: false })]);
    expect(texto()).toContain('Inactivo');
    expect(boton('reactivar')).toBeTruthy();
  });

  it('AC-8: el listado publica el estado real, sin "Estado no informado"', () => {
    montar([
      usuario({ activo: true }),
      usuario({ usuario_id: 2, nombre: 'Beto', activo: false }),
    ]);
    const visible = texto();
    expect(visible).toContain('Activo');
    expect(visible).toContain('Inactivo');
    expect(visible).not.toContain('Estado no informado');
  });

  it('AC-10: edita con PUT y motivo del catálogo, sin enviar el correo', () => {
    montar();
    boton('editar')?.click();
    fixture.detectChanges();

    fixture.componentInstance.formularioEdicion.patchValue({
      nombre: 'Ana María',
      apellido: 'Pérez',
      rol_id: 4,
      departamento_id: 10,
    });
    fixture.componentInstance.motivoEdicion.patchValue({
      codigo: 'cambio_funciones',
      texto: 'Nuevo rol',
    });
    fixture.detectChanges();

    boton('guardar cambios')?.click();
    fixture.detectChanges();

    const peticion = httpMock.expectOne(`${URL_API}/usuarios/1`);
    expect(peticion.request.method).toBe('PUT');
    const cuerpo = peticion.request.body as Record<string, unknown>;
    expect(cuerpo['nombre']).toBe('Ana María');
    expect(cuerpo['apellido']).toBe('Pérez');
    expect(cuerpo['rol_id']).toBe(4);
    expect(cuerpo['departamento_id']).toBe(10);
    expect(cuerpo['correo']).toBeUndefined();
    expect(cuerpo['motivo']).toEqual({ codigo: 'cambio_funciones', texto: 'Nuevo rol' });
    expect(typeof cuerpo['idempotencia']).toBe('string');

    peticion.flush(usuario({ nombre: 'Ana María', rol_id: 4 }));
    fixture.detectChanges();
    confirmarRecarga([usuario({ nombre: 'Ana María', rol_id: 4 })]);
    expect(texto()).toContain('Ana María');
    expect(texto()).toContain('actualizado');
  });

  it('AC-27: un Bodeguero ya en «Suministros» sin cambios no exige motivo', () => {
    montar(
      [usuario({ departamento_id: 14 })],
      ROLES,
      DEPARTAMENTOS_POR_SEDE,
      SEDES,
    );
    abrirEdicion();

    expect(selectEdicion('#editar-usuario-departamento')?.disabled).toBe(true);
    expect(fixture.componentInstance.hayCambiosEdicion()).toBe(false);
    expect(boton('guardar cambios')?.disabled).toBe(false);

    boton('guardar cambios')?.click();
    fixture.detectChanges();

    const peticion = httpMock.expectOne(`${URL_API}/usuarios/1`);
    const cuerpo = peticion.request.body as Record<string, unknown>;
    expect(cuerpo['motivo']).toBeUndefined();
    expect(cuerpo['idempotencia']).toBeUndefined();
    expect('departamento_id' in cuerpo).toBe(false);
    peticion.flush(usuario({ departamento_id: 14 }));
    fixture.detectChanges();

    // La sede se reafirma con el mismo PUT idempotente (D-10).
    const sede = httpMock.expectOne(`${URL_API}/organizacion/usuarios/1/sede`);
    expect(sede.request.method).toBe('PUT');
    expect(sede.request.body).toEqual({ sede_id: 1 });
    sede.flush({ usuario_id: 1, sede_id: 1 });
    fixture.detectChanges();

    confirmarRecarga(
      [usuario({ departamento_id: 14 })],
      DEPARTAMENTOS_POR_SEDE,
    );
    expect(texto()).toContain('actualizado');
  });

  it('AC-10: «otro» sin texto no envía la edición', () => {
    montar();
    boton('editar')?.click();
    fixture.detectChanges();
    fixture.componentInstance.formularioEdicion.patchValue({ nombre: 'Cambio' });
    fixture.componentInstance.motivoEdicion.patchValue({ codigo: 'otro', texto: '   ' });
    fixture.detectChanges();

    boton('guardar cambios')?.click();
    fixture.detectChanges();

    httpMock.expectNone(`${URL_API}/usuarios/1`);
    expect(texto()).toContain('exige un texto explicativo');
  });

  it('AC-10: un texto de motivo mayor a 500 caracteres no envía la edición', () => {
    montar();
    boton('editar')?.click();
    fixture.detectChanges();
    fixture.componentInstance.formularioEdicion.patchValue({ nombre: 'Cambio' });
    fixture.componentInstance.motivoEdicion.patchValue({
      codigo: 'otro',
      texto: 'a'.repeat(501),
    });
    fixture.detectChanges();

    boton('guardar cambios')?.click();
    fixture.detectChanges();

    httpMock.expectNone(`${URL_API}/usuarios/1`);
  });

  // --- Edición por rol y legacy (enmienda 012, E12-A5; D-13/D-15, AC-27/AC-28/AC-29) ---

  describe('edición por rol (enmienda 012, E12-A5)', () => {
    it('AC-27: un Bodeguero legacy en «Biblioteca» exige motivo y guarda la sede después del usuario', () => {
      montar(
        [usuario({ departamento_id: 15 })],
        ROLES,
        DEPARTAMENTOS_EDICION_SIN_SUMINISTROS,
        SEDES,
      );
      abrirEdicion();

      expect(selectEdicion('#editar-usuario-departamento')?.disabled).toBe(true);
      expect(opcionesSelectEdicion('#editar-usuario-departamento')).toEqual([
        'Suministros (asignación automática)',
      ]);
      expect(opcionesSelectEdicion('#editar-usuario-sede')).not.toContain(
        'Sin asignar',
      );
      expect(fixture.componentInstance.hayCambiosEdicion()).toBe(true);
      expect(boton('guardar cambios')?.disabled).toBe(true);

      fixture.componentInstance.guardarEdicion();
      fixture.detectChanges();
      httpMock.expectNone(`${URL_API}/usuarios/1`);

      completarMotivoEdicion();
      expect(boton('guardar cambios')?.disabled).toBe(false);
      boton('guardar cambios')?.click();
      fixture.detectChanges();

      const peticion = httpMock.expectOne(`${URL_API}/usuarios/1`);
      expect(peticion.request.method).toBe('PUT');
      const cuerpo = peticion.request.body as Record<string, unknown>;
      expect('departamento_id' in cuerpo).toBe(false);
      expect('sede_id' in cuerpo).toBe(false);
      expect(cuerpo['motivo']).toEqual({
        codigo: 'reasignacion_organizacional',
        texto: null,
      });
      expect(typeof cuerpo['idempotencia']).toBe('string');
      // Orden: primero /usuarios y después .../sede.
      httpMock.expectNone(`${URL_API}/organizacion/usuarios/1/sede`);

      peticion.flush(usuario({ departamento_id: 14 }));
      fixture.detectChanges();

      const sede = httpMock.expectOne(`${URL_API}/organizacion/usuarios/1/sede`);
      expect(sede.request.method).toBe('PUT');
      expect(sede.request.body).toEqual({ sede_id: 1 });
      sede.flush({ usuario_id: 1, sede_id: 1 });
      fixture.detectChanges();

      // El catálogo no tenía «Suministros»: la recarga lo trae y el listado lo muestra.
      confirmarRecarga([usuario({ departamento_id: 14 })]);
      expect(texto()).toContain('Suministros');
      expect(texto()).toContain('actualizado');
    });

    it('AC-27: cambiar solo el nombre de un Bodeguero exige motivo', () => {
      montar(
        [usuario({ departamento_id: 14 })],
        ROLES,
        DEPARTAMENTOS_POR_SEDE,
        SEDES,
      );
      abrirEdicion();
      fixture.componentInstance.formularioEdicion.controls.nombre.setValue(
        'Ana María',
      );
      fixture.detectChanges();

      expect(fixture.componentInstance.hayCambiosEdicion()).toBe(true);
      expect(boton('guardar cambios')?.disabled).toBe(true);

      completarMotivoEdicion();
      boton('guardar cambios')?.click();
      fixture.detectChanges();

      const peticion = httpMock.expectOne(`${URL_API}/usuarios/1`);
      const cuerpo = peticion.request.body as Record<string, unknown>;
      expect(cuerpo['nombre']).toBe('Ana María');
      expect(cuerpo['motivo']).toEqual({
        codigo: 'reasignacion_organizacional',
        texto: null,
      });
      expect('departamento_id' in cuerpo).toBe(false);
      peticion.flush(usuario({ nombre: 'Ana María', departamento_id: 14 }));
      fixture.detectChanges();

      const sede = httpMock.expectOne(`${URL_API}/organizacion/usuarios/1/sede`);
      expect(sede.request.body).toEqual({ sede_id: 1 });
      sede.flush({ usuario_id: 1, sede_id: 1 });
      fixture.detectChanges();
      confirmarRecarga(
        [usuario({ nombre: 'Ana María', departamento_id: 14 })],
        DEPARTAMENTOS_POR_SEDE,
      );
      expect(texto()).toContain('Ana María');
    });

    it('AC-29: en la edición del Solicitante la Sede filtra, sincroniza y solo viaja departamento_id', () => {
      montar(
        [usuario({ rol_id: 4, departamento_id: 11, sede_id: null })],
        ROLES,
        DEPARTAMENTOS_EDICION,
        SEDES,
      );
      abrirEdicion();

      // La sede arranca con la del departamento actual (Logística → Sede Central),
      // así que el combo llega filtrado a esa sede (D-11).
      expect(
        fixture.componentInstance.formularioEdicion.controls.sede_id.value,
      ).toBe(1);
      expect(opcionesSelectEdicion('#editar-usuario-sede')).toContain(
        'Todas las sedes',
      );
      expect(opcionesSelectEdicion('#editar-usuario-departamento')).toEqual([
        'Selecciona un departamento',
        'Logística',
        'Biblioteca',
      ]);

      elegirSedeEdicion(2);
      expect(opcionesSelectEdicion('#editar-usuario-departamento')).toEqual([
        'Selecciona un departamento',
        'Compras',
      ]);
      expect(
        fixture.componentInstance.formularioEdicion.controls.departamento_id.value,
      ).toBe(0);
      expect(fixture.componentInstance.formularioEdicion.invalid).toBe(true);

      elegirDepartamentoEdicion(12);
      expect(
        fixture.componentInstance.formularioEdicion.controls.sede_id.value,
      ).toBe(2);

      completarMotivoEdicion();
      boton('guardar cambios')?.click();
      fixture.detectChanges();

      const peticion = httpMock.expectOne(`${URL_API}/usuarios/1`);
      const cuerpo = peticion.request.body as Record<string, unknown>;
      expect(cuerpo['rol_id']).toBe(4);
      expect(cuerpo['departamento_id']).toBe(12);
      expect('sede_id' in cuerpo).toBe(false);
      expect(cuerpo['motivo']).toEqual({
        codigo: 'reasignacion_organizacional',
        texto: null,
      });
      peticion.flush(
        usuario({ rol_id: 4, departamento_id: 12, sede_id: null }),
      );
      fixture.detectChanges();

      httpMock.expectNone(`${URL_API}/organizacion/usuarios/1/sede`);
      confirmarRecarga([
        usuario({ rol_id: 4, departamento_id: 12, sede_id: null }),
      ]);
      expect(texto()).toContain('Compras');
    });

    it('AC-28: cambiar un Solicitante a Bodeguero deshabilita el Departamento y persiste la sede elegida', () => {
      montar(
        [usuario({ rol_id: 4, departamento_id: 11, sede_id: null })],
        ROLES,
        DEPARTAMENTOS_EDICION,
        SEDES,
      );
      abrirEdicion();
      elegirRolEdicion(3);

      expect(selectEdicion('#editar-usuario-departamento')?.disabled).toBe(true);
      expect(opcionesSelectEdicion('#editar-usuario-departamento')).toEqual([
        'Suministros (asignación automática)',
      ]);
      expect(
        fixture.componentInstance.formularioEdicion.controls.sede_id.hasError(
          'required',
        ),
      ).toBe(false);
      expect(fixture.componentInstance.hayCambiosEdicion()).toBe(true);
      expect(boton('guardar cambios')?.disabled).toBe(true);

      elegirSedeEdicion(2);
      completarMotivoEdicion();
      boton('guardar cambios')?.click();
      fixture.detectChanges();

      const peticion = httpMock.expectOne(`${URL_API}/usuarios/1`);
      const cuerpo = peticion.request.body as Record<string, unknown>;
      expect(cuerpo['rol_id']).toBe(3);
      expect('departamento_id' in cuerpo).toBe(false);
      expect(cuerpo['motivo']).toEqual({
        codigo: 'reasignacion_organizacional',
        texto: null,
      });
      peticion.flush(usuario({ rol_id: 3, departamento_id: 14 }));
      fixture.detectChanges();

      const sede = httpMock.expectOne(`${URL_API}/organizacion/usuarios/1/sede`);
      expect(sede.request.body).toEqual({ sede_id: 2 });
      sede.flush({ usuario_id: 1, sede_id: 2 });
      fixture.detectChanges();

      confirmarRecarga([
        usuario({ rol_id: 3, departamento_id: 14, sede_id: 2 }),
      ]);
      expect(texto()).toContain('Suministros');
      expect(texto()).toContain('Bodega Norte');
    });

    it('AC-29: cambiar un Bodeguero a Solicitante no ofrece «Suministros» y no toca la sede', () => {
      montar(
        [usuario({ rol_id: 3, departamento_id: 14, sede_id: 1 })],
        ROLES,
        DEPARTAMENTOS_EDICION,
        SEDES,
      );
      abrirEdicion();
      elegirRolEdicion(4);

      expect(selectEdicion('#editar-usuario-departamento')?.disabled).toBe(false);
      expect(opcionesSelectEdicion('#editar-usuario-departamento')).not.toContain(
        'Suministros',
      );
      expect(
        fixture.componentInstance.formularioEdicion.controls.departamento_id.value,
      ).toBe(0);
      expect(
        fixture.componentInstance.formularioEdicion.controls.sede_id.value,
      ).toBeNull();
      expect(fixture.componentInstance.formularioEdicion.invalid).toBe(true);
      expect(fixture.componentInstance.hayCambiosEdicion()).toBe(true);

      fixture.componentInstance.guardarEdicion();
      fixture.detectChanges();
      httpMock.expectNone(`${URL_API}/usuarios/1`);

      elegirDepartamentoEdicion(11);
      expect(
        fixture.componentInstance.formularioEdicion.controls.sede_id.value,
      ).toBe(1);
      // El cambio de rol desde Bodeguero es efectivo y exige motivo (D-13).
      expect(boton('guardar cambios')?.disabled).toBe(true);
      completarMotivoEdicion();
      boton('guardar cambios')?.click();
      fixture.detectChanges();

      const peticion = httpMock.expectOne(`${URL_API}/usuarios/1`);
      const cuerpo = peticion.request.body as Record<string, unknown>;
      expect(cuerpo['rol_id']).toBe(4);
      expect(cuerpo['departamento_id']).toBe(11);
      peticion.flush(usuario({ rol_id: 4, departamento_id: 11, sede_id: 1 }));
      fixture.detectChanges();

      httpMock.expectNone(`${URL_API}/organizacion/usuarios/1/sede`);
      confirmarRecarga([
        usuario({ rol_id: 4, departamento_id: 11, sede_id: 1 }),
      ]);
      // `usuario.sede_id` no se limpia al dejar de ser Bodeguero (D-13).
      expect(fixture.componentInstance.usuarios()[0].sede_id).toBe(1);
      expect(texto()).not.toContain('Sin sede asignada');
    });

    it('AC-29: si el tenant solo tiene «Suministros», el cambio a Solicitante no se puede guardar y lo indica', () => {
      montar(
        [usuario({ rol_id: 3, departamento_id: 14 })],
        ROLES,
        DEPARTAMENTOS_SOLO_SUMINISTROS,
        SEDES,
      );
      abrirEdicion();
      elegirRolEdicion(4);

      expect(opcionesSelectEdicion('#editar-usuario-departamento')).toEqual([
        'Selecciona un departamento',
      ]);
      expect(texto()).toContain('No hay departamentos disponibles');
      expect(fixture.componentInstance.formularioEdicion.invalid).toBe(true);

      fixture.componentInstance.guardarEdicion();
      fixture.detectChanges();
      httpMock.expectNone(`${URL_API}/usuarios/1`);
    });

    it('AC-27: sin sedes en el tenant la edición de un Bodeguero no se guarda y lo indica', () => {
      montar(
        [usuario({ departamento_id: 15, sede_id: null })],
        ROLES,
        DEPARTAMENTOS_EDICION_SIN_SUMINISTROS,
        [],
      );
      abrirEdicion();

      expect(opcionesSelectEdicion('#editar-usuario-sede')).toEqual([
        'Selecciona una sede',
      ]);
      expect(
        fixture.componentInstance.formularioEdicion.controls.sede_id.hasError(
          'required',
        ),
      ).toBe(true);
      expect(texto()).toContain('no tiene sedes');
      expect(boton('guardar cambios')?.disabled).toBe(true);

      fixture.componentInstance.guardarEdicion();
      fixture.detectChanges();
      httpMock.expectNone(`${URL_API}/usuarios/1`);
    });

    it('AC-27: si falla el PUT de sede, los cambios quedan guardados y el mensaje es de éxito parcial', () => {
      montar(
        [usuario({ departamento_id: 15 })],
        ROLES,
        DEPARTAMENTOS_EDICION_SIN_SUMINISTROS,
        SEDES,
      );
      abrirEdicion();
      fixture.componentInstance.formularioEdicion.controls.nombre.setValue(
        'Ana María',
      );
      completarMotivoEdicion();
      boton('guardar cambios')?.click();
      fixture.detectChanges();

      httpMock
        .expectOne(`${URL_API}/usuarios/1`)
        .flush(usuario({ nombre: 'Ana María', departamento_id: 14 }));
      fixture.detectChanges();

      httpMock
        .expectOne(`${URL_API}/organizacion/usuarios/1/sede`)
        .flush(
          { detail: 'No disponible' },
          { status: 500, statusText: 'Server Error' },
        );
      fixture.detectChanges();

      const alerta = (fixture.nativeElement as HTMLElement).querySelector(
        '[role="alert"]',
      );
      expect(alerta?.textContent).toContain('se guardaron');
      expect(alerta?.textContent).toContain('sede no se actualizó');

      confirmarRecarga([usuario({ nombre: 'Ana María', departamento_id: 14 })]);
      expect(texto()).toContain('Ana María');
      expect(texto()).toContain('Suministros');
      expect(boton('guardar cambios')).toBeFalsy();
    });

    it('AC-27: si el PUT del usuario falla, no se llama al PUT de sede', () => {
      montar(
        [usuario({ departamento_id: 15 })],
        ROLES,
        DEPARTAMENTOS_EDICION_SIN_SUMINISTROS,
        SEDES,
      );
      abrirEdicion();
      completarMotivoEdicion();
      boton('guardar cambios')?.click();
      fixture.detectChanges();

      httpMock
        .expectOne(`${URL_API}/usuarios/1`)
        .flush(
          { detail: 'La edicion efectiva exige un motivo del catalogo' },
          { status: 422, statusText: 'Unprocessable Entity' },
        );
      fixture.detectChanges();

      httpMock.expectNone(`${URL_API}/organizacion/usuarios/1/sede`);
      const alerta = (fixture.nativeElement as HTMLElement).querySelector(
        '[role="alert"]',
      );
      expect(alerta?.textContent).toContain('motivo');
      expect(selectEdicion('#editar-usuario-departamento')).toBeTruthy();
    });

    it('AC-26: la edición de un Administrador no muestra Sede y mantiene el Departamento obligatorio', () => {
      identidadFalsa.set(identidad('Superadmin'));
      montar(
        [usuario({ rol_id: 2, departamento_id: 11, sede_id: null })],
        ROLES_CUATRO,
        DEPARTAMENTOS_EDICION,
        SEDES,
      );
      abrirEdicion();

      expect(selectEdicion('#editar-usuario-sede')).toBeNull();
      expect(selectEdicion('#editar-usuario-departamento')?.disabled).toBe(false);
      expect(
        fixture.componentInstance.formularioEdicion.controls.departamento_id
          .hasError('required'),
      ).toBe(false);
      expect(fixture.componentInstance.hayCambiosEdicion()).toBe(false);

      boton('guardar cambios')?.click();
      fixture.detectChanges();

      const peticion = httpMock.expectOne(`${URL_API}/usuarios/1`);
      const cuerpo = peticion.request.body as Record<string, unknown>;
      expect(cuerpo['departamento_id']).toBe(11);
      expect(cuerpo['motivo']).toBeUndefined();
      peticion.flush(usuario({ rol_id: 2, departamento_id: 11, sede_id: null }));
      fixture.detectChanges();

      httpMock.expectNone(`${URL_API}/organizacion/usuarios/1/sede`);
      confirmarRecarga([
        usuario({ rol_id: 2, departamento_id: 11, sede_id: null }),
      ]);
    });
  });

  it('AC-11: un 409 al desactivar (último Administrador activo) muestra el motivo', () => {
    montar();
    boton('desactivar')?.click();
    fixture.detectChanges();
    fixture.componentInstance.motivoEstado.patchValue({
      codigo: 'termino_vinculo',
      texto: '',
    });
    fixture.detectChanges();
    expect(fixture.componentInstance.motivoEstadoCompleto()).withContext('motivo completo').toBe(true);
    expect(boton('confirmar')?.disabled).withContext('confirmar habilitado').toBe(false);
    boton('confirmar')?.click();
    fixture.detectChanges();

    const peticion = httpMock.expectOne(`${URL_API}/usuarios/1/estado`);
    const cuerpo = peticion.request.body as Record<string, unknown>;
    expect(cuerpo['activo']).toBe(false);
    expect(cuerpo['motivo']).toEqual({ codigo: 'termino_vinculo', texto: null });
    expect(typeof cuerpo['idempotencia']).toBe('string');
    peticion.flush(
      {
        detail:
          'No se puede dar de baja al ultimo Administrador activo de la institucion',
      },
      { status: 409, statusText: 'Conflict' },
    );
    fixture.detectChanges();

    const alerta = (fixture.nativeElement as HTMLElement).querySelector('[role="alert"]');
    expect(alerta?.textContent).toContain('Administrador activo');
    expect(texto()).toContain('Activo');
  });

  it('AC-10: sin motivo válido el cambio de estado no se envía', () => {
    montar();
    boton('desactivar')?.click();
    fixture.detectChanges();
    fixture.componentInstance.confirmarCambioEstado();
    fixture.detectChanges();

    httpMock.expectNone(`${URL_API}/usuarios/1/estado`);
    expect(texto()).toContain('Selecciona un motivo');
  });

  it('AC-9: asigna sede a un Bodeguero con opciones limitadas al tenant', () => {
    montar([usuario({ sede_id: null })]);
    boton('asignar sede')?.click();
    fixture.detectChanges();

    const opciones = Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll('select option'),
    ).map((o) => o.textContent?.trim());
    expect(opciones).toEqual(['Sin asignar', 'Sede Central', 'Bodega Norte']);

    fixture.componentInstance.cambiarSeleccionSede({
      target: { value: '2' },
    } as unknown as Event);
    fixture.detectChanges();

    boton('guardar sede')?.click();
    fixture.detectChanges();

    const peticion = httpMock.expectOne(`${URL_API}/organizacion/usuarios/1/sede`);
    expect(peticion.request.method).toBe('PUT');
    expect(peticion.request.body).toEqual({ sede_id: 2 });
    peticion.flush({ usuario_id: 1, sede_id: 2 });
    fixture.detectChanges();
    expect(texto()).toContain('Bodega Norte');
  });

  it('AC-9: un Solicitante no ofrece la acción de asignar sede', () => {
    montar([usuario({ rol_id: 4, sede_id: null })]);
    expect(boton('asignar sede')).toBeFalsy();
  });

  // --- Reenvío ordinario de invitación (Feature 017, T12) ---

  describe('reenvío ordinario de invitación (T12)', () => {
    function tarjetas(): HTMLElement[] {
      return Array.from(
        (fixture.nativeElement as HTMLElement).querySelectorAll('li'),
      );
    }

    function botonEn(indice: number, etiqueta: string): HTMLButtonElement | undefined {
      return Array.from(tarjetas()[indice].querySelectorAll('button')).find((b) =>
        new RegExp(etiqueta, 'i').test(b.textContent ?? ''),
      );
    }

    function textoDe(indice: number): string {
      return tarjetas()[indice].textContent ?? '';
    }

    it('AC-6/AC-9: solo se ofrece a Bodeguero/Solicitante activos con invitación no aceptada', () => {
      montar([
        usuario({ usuario_id: 1, estado_invitacion: 'pendiente' }),
        usuario({ usuario_id: 2, estado_invitacion: 'aceptada' }),
        usuario({ usuario_id: 3, estado_invitacion: 'expirada', activo: false }),
        usuario({ usuario_id: 4, rol_id: 1, estado_invitacion: 'pendiente' }),
        usuario({ usuario_id: 5, rol_id: 4, estado_invitacion: 'revocada' }),
      ]);

      expect(botonEn(0, 'reenviar')).toBeTruthy();
      expect(botonEn(1, 'reenviar')).toBeFalsy();
      expect(botonEn(2, 'reenviar')).toBeFalsy();
      expect(botonEn(3, 'reenviar')).toBeFalsy();
      expect(botonEn(4, 'reenviar')).toBeTruthy();
    });

    it('AC-6: un vínculo inactivo no ofrece reenvío y pide reactivarlo primero', () => {
      montar([usuario({ usuario_id: 3, estado_invitacion: 'expirada', activo: false })]);

      expect(botonEn(0, 'reenviar')).toBeFalsy();
      expect(textoDe(0)).toContain('Reactívalo primero');
    });

    it('AC-6: reenvía con POST sin cuerpo y muestra la URL solo en esa respuesta', async () => {
      montar([usuario({ usuario_id: 7, estado_invitacion: 'expirada' })]);

      botonEn(0, 'reenviar')?.click();
      fixture.detectChanges();

      const peticion = httpMock.expectOne(`${URL_API}/usuarios/7/invitacion/reenvio`);
      expect(peticion.request.method).toBe('POST');
      expect(peticion.request.body).toBeNull();
      peticion.flush(
        invitacion({
          usuario_id: 7,
          estado_invitacion: 'pendiente',
          url_invitacion: 'https://clerk.example/inv/nueva',
        }),
      );
      fixture.detectChanges();

      expect(textoDe(0)).toContain('Invitación: Pendiente');
      expect(texto()).toContain('https://clerk.example/inv/nueva');
      expect(texto()).toContain('reenviada');

      boton('copiar enlace')?.click();
      await fixture.whenStable();
      fixture.detectChanges();
      expect(portapapeles).toEqual(['https://clerk.example/inv/nueva']);
      expect(texto()).toContain('Enlace copiado');
    });

    it('AC-6: no envía el reenvío dos veces mientras está en vuelo', () => {
      montar([usuario({ usuario_id: 7, estado_invitacion: 'pendiente' })]);

      const objetivo = usuario({ usuario_id: 7, estado_invitacion: 'pendiente' });
      fixture.componentInstance.reenviarInvitacion(objetivo);
      fixture.componentInstance.reenviarInvitacion(objetivo);
      fixture.detectChanges();

      const peticiones = httpMock.match(
        `${URL_API}/usuarios/7/invitacion/reenvio`,
      );
      expect(peticiones.length).toBe(1);
      peticiones[0].flush(
        invitacion({ usuario_id: 7, estado_invitacion: 'pendiente', url_invitacion: null }),
      );
      fixture.detectChanges();
    });

    it('AC-6: un 409 (aceptada/conflicto) se muestra sin enlace', () => {
      montar([usuario({ usuario_id: 8, estado_invitacion: 'pendiente' })]);

      botonEn(0, 'reenviar')?.click();
      fixture.detectChanges();

      httpMock
        .expectOne(`${URL_API}/usuarios/8/invitacion/reenvio`)
        .flush(
          { detail: 'La invitacion ya fue aceptada; no se reenvia' },
          { status: 409, statusText: 'Conflict' },
        );
      fixture.detectChanges();

      expect(texto()).toContain('ya fue aceptada');
      expect(texto()).not.toContain('Copiar enlace');
      expect(botonEn(0, 'reenviar')).toBeTruthy();
    });

    it('AC-6: un 503 de la frontera Clerk se informa y es reintentable', () => {
      montar([usuario({ usuario_id: 8, estado_invitacion: 'pendiente' })]);

      botonEn(0, 'reenviar')?.click();
      fixture.detectChanges();

      httpMock
        .expectOne(`${URL_API}/usuarios/8/invitacion/reenvio`)
        .flush('', { status: 503, statusText: 'Service Unavailable' });
      fixture.detectChanges();

      expect(texto()).toContain('no está disponible');
      expect(botonEn(0, 'reenviar')).toBeTruthy();
    });

    it('AC-2: reactivar no reenvía; después el reenvío es una operación separada', () => {
      montar([usuario({ usuario_id: 9, estado_invitacion: 'pendiente', activo: false })]);

      expect(botonEn(0, 'reenviar')).toBeFalsy();

      botonEn(0, 'reactivar')?.click();
      fixture.detectChanges();
      fixture.componentInstance.motivoEstado.patchValue({
        codigo: 'reasignacion_organizacional',
        texto: '',
      });
      fixture.detectChanges();

      boton('confirmar')?.click();
      fixture.detectChanges();

      const cambio = httpMock.expectOne(`${URL_API}/usuarios/9/estado`);
      expect(cambio.request.method).toBe('PATCH');
      expect(cambio.request.body.activo).toBe(true);
      expect(cambio.request.body.motivo).toEqual({
        codigo: 'reasignacion_organizacional',
        texto: null,
      });
      cambio.flush({ usuario_id: 9, activo: true });
      fixture.detectChanges();

      // La reactivación no llama a Clerk ni crea invitaciones.
      httpMock.expectNone(`${URL_API}/usuarios/9/invitacion/reenvio`);
      expect(textoDe(0)).toContain('La reactivación no reenvía la invitación');

      expect(botonEn(0, 'reenviar')).toBeTruthy();
      botonEn(0, 'reenviar')?.click();
      fixture.detectChanges();

      const reenvio = httpMock.expectOne(`${URL_API}/usuarios/9/invitacion/reenvio`);
      expect(reenvio.request.method).toBe('POST');
      reenvio.flush(
        invitacion({
          usuario_id: 9,
          estado_invitacion: 'pendiente',
          url_invitacion: 'https://clerk.example/inv/reactivado',
        }),
      );
      fixture.detectChanges();

      expect(texto()).toContain('https://clerk.example/inv/reactivado');
    });
  });

  it('AC-8: estado vacío cuando no hay usuarios', () => {
    montar([]);
    expect(texto()).toContain('Aún no hay usuarios');
  });

  // --- Alta de usuario con invitación (Feature 017, T9) ---

  it('AC-8: el botón Nuevo usuario abre el formulario de alta', () => {
    montar();
    expect(boton('crear usuario')).toBeFalsy();
    boton('nuevo usuario')?.click();
    fixture.detectChanges();

    const visible = texto();
    expect(visible).toContain('Alta de usuario');
    expect(boton('crear usuario')).toBeTruthy();
    const campos = (
      fixture.nativeElement as HTMLElement
    ).querySelectorAll('#crear-usuario-nombre, #crear-usuario-correo, #crear-usuario-rol');
    expect(campos.length).toBe(3);
  });

  it('AC-1: el alta con invitación muestra el estado pendiente y el enlace copiable', async () => {
    montar([]);
    boton('nuevo usuario')?.click();
    fixture.detectChanges();
    rellenarAlta();

    boton('crear usuario')?.click();
    fixture.detectChanges();

    const peticion = httpMock.expectOne(`${URL_API}/usuarios/`);
    expect(peticion.request.method).toBe('POST');
    peticion.flush(
      invitacion({
        usuario_id: 5,
        nombre: 'Nuevo',
        apellido: 'Solicitante',
        correo: 'nuevo@example.com',
        rol_id: 4,
        sede_id: null,
        estado_invitacion: 'pendiente',
        url_invitacion: 'https://clerk.example/inv/abc',
      }),
    );
    fixture.detectChanges();

    expect(texto()).toContain('invitación pendiente');
    expect(texto()).toContain('https://clerk.example/inv/abc');
    expect(texto()).toContain('Copiar enlace');

    boton('copiar enlace')?.click();
    await fixture.whenStable();
    fixture.detectChanges();
    expect(portapapeles).toEqual(['https://clerk.example/inv/abc']);
    expect(texto()).toContain('Enlace copiado');

    httpMock.expectOne(RUTA_USUARIOS).flush([]);
    httpMock.expectOne(RUTA_ROLES).flush(ROLES);
    httpMock.expectOne(RUTA_DEPARTAMENTOS).flush(DEPARTAMENTOS);
    httpMock.expectOne(RUTA_SEDES).flush(SEDES);
    fixture.detectChanges();
  });

  it('AC-2: si Clerk ya tenía identidad, el alta informa «aceptada» y no trae enlace', () => {
    montar([]);
    boton('nuevo usuario')?.click();
    fixture.detectChanges();
    rellenarAlta();

    boton('crear usuario')?.click();
    fixture.detectChanges();

    httpMock.expectOne(`${URL_API}/usuarios/`).flush(
      invitacion({
        usuario_id: 5,
        nombre: 'Nuevo',
        apellido: 'Solicitante',
        estado_invitacion: 'aceptada',
        url_invitacion: null,
      }),
    );
    fixture.detectChanges();

    expect(texto()).toContain('invitación aceptada');
    expect(texto()).not.toContain('Copiar enlace');

    httpMock.expectOne(RUTA_USUARIOS).flush([]);
    httpMock.expectOne(RUTA_ROLES).flush(ROLES);
    httpMock.expectOne(RUTA_DEPARTAMENTOS).flush(DEPARTAMENTOS);
    httpMock.expectOne(RUTA_SEDES).flush(SEDES);
    fixture.detectChanges();
  });

  it('AC-10: un 422 de motivo/rol se muestra y no cierra el alta', () => {
    montar();
    boton('nuevo usuario')?.click();
    fixture.detectChanges();
    rellenarAlta({ correo: 'invalido@example.com' });

    boton('crear usuario')?.click();
    fixture.detectChanges();

    httpMock.expectOne(`${URL_API}/usuarios/`).flush(
      {
        detail: [
          {
            type: 'value_error',
            loc: ['body', 'motivo'],
            msg: 'Value error, el motivo `otro` exige texto',
          },
        ],
      },
      { status: 422, statusText: 'Unprocessable Entity' },
    );
    fixture.detectChanges();

    const alerta = (fixture.nativeElement as HTMLElement).querySelector(
      '[role="alert"]',
    );
    expect(alerta?.textContent).toContain('motivo');
    expect(boton('crear usuario')).toBeTruthy();
  });

  it('AC-1: un 409 de correo ya vinculado se muestra con el motivo', () => {
    montar();
    boton('nuevo usuario')?.click();
    fixture.detectChanges();
    rellenarAlta({ correo: 'ya.vinculado@example.com' });

    boton('crear usuario')?.click();
    fixture.detectChanges();

    httpMock.expectOne(`${URL_API}/usuarios/`).flush(
      { detail: 'El correo ya esta vinculado a una identidad local activa' },
      { status: 409, statusText: 'Conflict' },
    );
    fixture.detectChanges();

    const alerta = (fixture.nativeElement as HTMLElement).querySelector(
      '[role="alert"]',
    );
    expect(alerta?.textContent).toContain('ya esta vinculado');
  });

  it('AC-2: un 503 de la frontera Clerk es recuperable y no cierra el alta', () => {
    montar();
    boton('nuevo usuario')?.click();
    fixture.detectChanges();
    rellenarAlta();

    boton('crear usuario')?.click();
    fixture.detectChanges();

    httpMock.expectOne(`${URL_API}/usuarios/`).flush(
      { detail: 'La frontera Clerk no esta disponible' },
      { status: 503, statusText: 'Service Unavailable' },
    );
    fixture.detectChanges();

    const alerta = (fixture.nativeElement as HTMLElement).querySelector(
      '[role="alert"]',
    );
    expect(alerta?.textContent).toContain('no esta disponible');
    expect(boton('crear usuario')).toBeTruthy();
  });

  it('AC-1: el alta no se envía dos veces mientras está en vuelo', () => {
    montar([]);
    boton('nuevo usuario')?.click();
    fixture.detectChanges();
    rellenarAlta();

    expect(fixture.componentInstance.formularioCreacion.valid).withContext('formulario válido').toBe(true);
    fixture.componentInstance.guardarCreacion();
    fixture.componentInstance.guardarCreacion();
    fixture.detectChanges();

    const peticion = httpMock.expectOne(`${URL_API}/usuarios/`);
    httpMock.expectNone(`${URL_API}/usuarios/`);
    peticion.flush(
      invitacion({ usuario_id: 5, estado_invitacion: 'pendiente', url_invitacion: null }),
    );
    fixture.detectChanges();
    httpMock.expectOne(RUTA_USUARIOS).flush([]);
    httpMock.expectOne(RUTA_ROLES).flush(ROLES);
    httpMock.expectOne(RUTA_DEPARTAMENTOS).flush(DEPARTAMENTOS);
    httpMock.expectOne(RUTA_SEDES).flush(SEDES);
    fixture.detectChanges();
  });

  it('AC-9/AC-20: el alta de un Bodeguero con sede la asigna tras crear y omite departamento_id', () => {
    montar();
    abrirAlta();
    expect(selectAlta('#crear-usuario-departamento')?.disabled).toBe(true);
    rellenarAlta({
      nombre: 'Beto',
      apellido: 'Bodega',
      correo: 'beto@example.com',
      rol_id: 3,
      sede_id: 2,
    });

    boton('crear usuario')?.click();
    fixture.detectChanges();

    const peticion = httpMock.expectOne(`${URL_API}/usuarios/`);
    const cuerpo = peticion.request.body as Record<string, unknown>;
    expect(cuerpo['rol_id']).toBe(3);
    expect('departamento_id' in cuerpo).toBe(false);
    expect('sede_id' in cuerpo).toBe(false);
    peticion.flush(
      invitacion({
        usuario_id: 7,
        nombre: 'Beto',
        apellido: 'Bodega',
        correo: 'beto@example.com',
        rol_id: 3,
        sede_id: null,
        estado_invitacion: 'pendiente',
        url_invitacion: 'https://clerk.example/inv/beto',
      }),
    );
    fixture.detectChanges();

    const asignacion = httpMock.expectOne(
      `${URL_API}/organizacion/usuarios/7/sede`,
    );
    expect(asignacion.request.method).toBe('PUT');
    expect(asignacion.request.body).toEqual({ sede_id: 2 });
    asignacion.flush({ usuario_id: 7, sede_id: 2 });
    fixture.detectChanges();

    httpMock.expectOne(RUTA_USUARIOS).flush([]);
    httpMock.expectOne(RUTA_ROLES).flush(ROLES);
    httpMock.expectOne(RUTA_DEPARTAMENTOS).flush(DEPARTAMENTOS);
    httpMock.expectOne(RUTA_SEDES).flush(SEDES);
    fixture.detectChanges();

    expect(texto()).toContain('Sede asignada');
    expect(texto()).toContain('https://clerk.example/inv/beto');
  });

  // --- Alta por rol (enmienda 012, E12-A4; D-10/D-11/D-14, AC-24/AC-25/AC-26) ---

  it('AC-24: el alta de Bodeguero deshabilita el Departamento y exige Sede sin «Sin asignar»', () => {
    montar([], ROLES, DEPARTAMENTOS_POR_SEDE, SEDES);
    abrirAlta();

    const departamento = selectAlta('#crear-usuario-departamento');
    expect(departamento?.disabled).toBe(true);
    expect(opcionesSelectAlta('#crear-usuario-departamento')).toEqual([
      'Suministros (asignación automática)',
    ]);
    expect(
      fixture.componentInstance.formularioCreacion.controls.departamento_id.disabled,
    ).toBe(true);

    expect(opcionesSelectAlta('#crear-usuario-sede')).not.toContain('Sin asignar');
    expect(
      fixture.componentInstance.formularioCreacion.controls.sede_id.hasError(
        'required',
      ),
    ).toBe(true);

    rellenarAlta({ rol_id: 3 });
    expect(fixture.componentInstance.formularioCreacion.invalid).toBe(true);

    elegirSede(2);
    expect(fixture.componentInstance.formularioCreacion.valid).toBe(true);
  });

  it('AC-20: si falla la asignación de sede tras el alta de Bodeguero, informa éxito parcial y conserva el enlace', () => {
    montar([], ROLES, DEPARTAMENTOS_POR_SEDE, SEDES);
    abrirAlta();
    rellenarAlta({ rol_id: 3, sede_id: 1 });

    boton('crear usuario')?.click();
    fixture.detectChanges();

    httpMock.expectOne(`${URL_API}/usuarios/`).flush(
      invitacion({
        usuario_id: 8,
        nombre: 'Nuevo',
        apellido: 'Solicitante',
        rol_id: 3,
        sede_id: null,
        estado_invitacion: 'pendiente',
        url_invitacion: 'https://clerk.example/inv/parcial',
      }),
    );
    fixture.detectChanges();

    httpMock.expectOne(`${URL_API}/organizacion/usuarios/8/sede`).flush(
      { detail: 'No disponible' },
      { status: 500, statusText: 'Server Error' },
    );
    fixture.detectChanges();

    httpMock.expectOne(RUTA_USUARIOS).flush([]);
    httpMock.expectOne(RUTA_ROLES).flush(ROLES);
    httpMock.expectOne(RUTA_DEPARTAMENTOS).flush(DEPARTAMENTOS_POR_SEDE);
    httpMock.expectOne(RUTA_SEDES).flush(SEDES);
    fixture.detectChanges();

    const alerta = (fixture.nativeElement as HTMLElement).querySelector(
      '[role="alert"]',
    );
    expect(alerta?.textContent).toContain('se creó');
    expect(alerta?.textContent).toContain('no se pudo asignar');
    expect(texto()).toContain('https://clerk.example/inv/parcial');
    expect(boton('crear usuario')).toBeFalsy();
  });

  it('AC-20: sin sedes en el tenant, el alta de Bodeguero no se envía y lo indica', () => {
    montar([], ROLES, DEPARTAMENTOS_POR_SEDE, []);
    abrirAlta();
    rellenarAlta({ rol_id: 3 });

    expect(texto()).toContain('no tiene sedes');
    expect(boton('crear usuario')?.disabled).toBe(true);

    fixture.componentInstance.guardarCreacion();
    fixture.detectChanges();
    httpMock.expectNone(`${URL_API}/usuarios/`);
  });

  it('AC-25: en el alta de Solicitante la Sede filtra los departamentos y se sincroniza', () => {
    montar([], ROLES, DEPARTAMENTOS_POR_SEDE, SEDES);
    abrirAlta();
    elegirRol(4);

    expect(opcionesSelectAlta('#crear-usuario-departamento')).toEqual([
      'Selecciona un departamento',
      'Logística',
      'Compras',
      'Sin sede',
    ]);

    elegirSede(1);
    expect(opcionesSelectAlta('#crear-usuario-departamento')).toEqual([
      'Selecciona un departamento',
      'Logística',
    ]);

    elegirDepartamento(11);
    expect(fixture.componentInstance.formularioCreacion.controls.sede_id.value).toBe(
      1,
    );
    expect(opcionesSelectAlta('#crear-usuario-sede')).toContain('Todas las sedes');

    elegirSede(null);
    elegirDepartamento(12);
    expect(fixture.componentInstance.formularioCreacion.controls.sede_id.value).toBe(
      2,
    );

    elegirSede(null);
    elegirDepartamento(13);
    expect(
      fixture.componentInstance.formularioCreacion.controls.sede_id.value,
    ).toBeNull();
  });

  it('AC-25: cambiar la Sede limpia un departamento incompatible y no se envía sin departamento', () => {
    montar([], ROLES, DEPARTAMENTOS_POR_SEDE, SEDES);
    abrirAlta();
    rellenarDatosAlta();
    elegirRol(4);
    elegirSede(2);
    elegirDepartamento(12);

    elegirSede(1);
    expect(
      fixture.componentInstance.formularioCreacion.controls.departamento_id.value,
    ).toBe(0);
    expect(fixture.componentInstance.formularioCreacion.invalid).toBe(true);

    boton('crear usuario')?.click();
    fixture.detectChanges();
    httpMock.expectNone(`${URL_API}/usuarios/`);
  });

  it('AC-25: el alta de Solicitante envía solo departamento_id y no llama a la sede', () => {
    montar([], ROLES, DEPARTAMENTOS_POR_SEDE, SEDES);
    abrirAlta();
    rellenarDatosAlta();
    elegirRol(4);
    elegirSede(1);
    elegirDepartamento(11);

    boton('crear usuario')?.click();
    fixture.detectChanges();

    const peticion = httpMock.expectOne(`${URL_API}/usuarios/`);
    const cuerpo = peticion.request.body as Record<string, unknown>;
    expect(cuerpo['rol_id']).toBe(4);
    expect(cuerpo['departamento_id']).toBe(11);
    expect('sede_id' in cuerpo).toBe(false);
    peticion.flush(
      invitacion({
        usuario_id: 9,
        nombre: 'Nuevo',
        apellido: 'Solicitante',
        rol_id: 4,
        sede_id: null,
        estado_invitacion: 'aceptada',
        url_invitacion: null,
      }),
    );
    fixture.detectChanges();

    httpMock.expectNone(`${URL_API}/organizacion/usuarios/9/sede`);
    httpMock.expectOne(RUTA_USUARIOS).flush([]);
    httpMock.expectOne(RUTA_ROLES).flush(ROLES);
    httpMock.expectOne(RUTA_DEPARTAMENTOS).flush(DEPARTAMENTOS_POR_SEDE);
    httpMock.expectOne(RUTA_SEDES).flush(SEDES);
    fixture.detectChanges();

    expect(texto()).toContain('invitación aceptada');
  });

  it('AC-24: cambiar de rol recalcula los controles y no conserva una selección incompatible', () => {
    montar([], ROLES, DEPARTAMENTOS_POR_SEDE, SEDES);
    abrirAlta();
    rellenarDatosAlta();
    elegirRol(4);
    elegirSede(1);
    elegirDepartamento(11);

    elegirRol(3);
    expect(
      fixture.componentInstance.formularioCreacion.controls.departamento_id.disabled,
    ).toBe(true);
    expect(
      fixture.componentInstance.formularioCreacion.controls.departamento_id.value,
    ).toBe(0);
    expect(
      fixture.componentInstance.formularioCreacion.controls.sede_id.hasError(
        'required',
      ),
    ).toBe(false);

    elegirRol(4);
    expect(
      fixture.componentInstance.formularioCreacion.controls.departamento_id.disabled,
    ).toBe(false);
    expect(
      fixture.componentInstance.formularioCreacion.controls.departamento_id.value,
    ).toBe(0);
    expect(fixture.componentInstance.formularioCreacion.invalid).toBe(true);
  });

  it('AC-24/AC-26: el alta de Administrador no muestra Sede, exige Departamento y no ofrece «Suministros»', () => {
    identidadFalsa.set(identidad('Superadmin'));
    montar([], ROLES_CUATRO, DEPARTAMENTOS_POR_SEDE, SEDES);
    abrirAlta();
    elegirRol(2);

    expect(selectAlta('#crear-usuario-sede')).toBeNull();
    expect(selectAlta('#crear-usuario-departamento')?.disabled).toBe(false);
    expect(opcionesSelectAlta('#crear-usuario-departamento')).not.toContain(
      'SUMINISTROS',
    );
    expect(
      fixture.componentInstance.formularioCreacion.controls.departamento_id.hasError(
        'required',
      ),
    ).toBe(false);

    fixture.componentInstance.formularioCreacion.patchValue({
      nombre: 'Nuevo',
      apellido: 'Administrador',
      correo: 'admin.nuevo@example.com',
      departamento_id: 11,
    });
    fixture.detectChanges();

    boton('crear usuario')?.click();
    fixture.detectChanges();

    const peticion = httpMock.expectOne(`${URL_API}/usuarios/`);
    const cuerpo = peticion.request.body as Record<string, unknown>;
    expect(cuerpo['rol_id']).toBe(2);
    expect(cuerpo['departamento_id']).toBe(11);
    expect('sede_id' in cuerpo).toBe(false);
    peticion.flush(
      invitacion({
        usuario_id: 10,
        nombre: 'Nuevo',
        apellido: 'Administrador',
        rol_id: 2,
        sede_id: null,
        estado_invitacion: 'pendiente',
        url_invitacion: null,
      }),
    );
    fixture.detectChanges();

    httpMock.expectNone(`${URL_API}/organizacion/usuarios/10/sede`);
    httpMock.expectOne(RUTA_USUARIOS).flush([]);
    httpMock.expectOne(RUTA_ROLES).flush(ROLES_CUATRO);
    httpMock.expectOne(RUTA_DEPARTAMENTOS).flush(DEPARTAMENTOS_POR_SEDE);
    httpMock.expectOne(RUTA_SEDES).flush(SEDES);
    fixture.detectChanges();
  });

  it('AC-24: al pasar de Administrador a Bodeguero la Sede pasa a ser obligatoria', () => {
    identidadFalsa.set(identidad('Superadmin'));
    montar([], ROLES_CUATRO, DEPARTAMENTOS_POR_SEDE, SEDES);
    abrirAlta();
    elegirRol(2);
    expect(selectAlta('#crear-usuario-sede')).toBeNull();

    elegirRol(3);
    expect(selectAlta('#crear-usuario-sede')).toBeTruthy();
    expect(
      fixture.componentInstance.formularioCreacion.controls.sede_id.value,
    ).toBeNull();
    expect(
      fixture.componentInstance.formularioCreacion.controls.sede_id.hasError(
        'required',
      ),
    ).toBe(true);
    expect(
      fixture.componentInstance.formularioCreacion.controls.departamento_id.disabled,
    ).toBe(true);
  });

  // --- Roles asignables según la identidad (ajuste post-cierre, D-6/AC-10) ---

  it('AC-8/AC-10: con identidad Administrador el combo de rol del alta ofrece dos roles', () => {
    montar();
    boton('nuevo usuario')?.click();
    fixture.detectChanges();

    expect(opcionesRolAlta()).toEqual(['Bodeguero', 'Solicitante']);
  });

  it('AC-8/AC-10: con identidad Superadmin el combo de rol del alta ofrece los cuatro roles', () => {
    identidadFalsa.set(identidad('Superadmin'));
    montar([usuario()], ROLES_CUATRO);
    boton('nuevo usuario')?.click();
    fixture.detectChanges();

    expect(opcionesRolAlta()).toEqual([
      'Superadmin',
      'Administrador',
      'Bodeguero',
      'Solicitante',
    ]);
  });

  it('AC-8/AC-10: el rol por defecto del alta es asignable por la identidad activa', () => {
    montar();
    boton('nuevo usuario')?.click();
    fixture.detectChanges();

    expect(fixture.componentInstance.formularioCreacion.controls.rol_id.value).toBe(
      3,
    );
  });

  it('AC-8/AC-10: si cambia la identidad activa, el combo se recalcula', () => {
    montar();
    boton('nuevo usuario')?.click();
    fixture.detectChanges();
    expect(opcionesRolAlta().length).toBe(2);

    identidadFalsa.set(identidad('Superadmin'));
    fixture.detectChanges();
    expect(opcionesRolAlta().length).toBe(3);
  });

  it('AC-8/AC-10: el combo de rol de la edición no ofrece Superadmin a un Administrador', () => {
    montar([usuario()], ROLES_CUATRO);
    boton('editar')?.click();
    fixture.detectChanges();

    expect(opcionesRolEdicion()).toEqual(['Bodeguero', 'Solicitante']);
  });

  it('AC-8/AC-10: al editar un Administrador se conserva visible su rol actual, sin Superadmin', () => {
    montar([usuario({ rol_id: 2, nombre: 'Camila' })], ROLES_CUATRO);
    boton('editar')?.click();
    fixture.detectChanges();

    expect(opcionesRolEdicion()).toEqual([
      'Administrador',
      'Bodeguero',
      'Solicitante',
    ]);
    expect(
      fixture.componentInstance.formularioEdicion.controls.rol_id.value,
    ).toBe(2);
  });

  it('AC-8/AC-10: la edición institucional nunca ofrece Superadmin, ni con identidad Superadmin', () => {
    identidadFalsa.set(identidad('Superadmin'));
    montar([usuario()], ROLES_CUATRO);
    boton('editar')?.click();
    fixture.detectChanges();

    expect(opcionesRolEdicion()).toEqual([
      'Administrador',
      'Bodeguero',
      'Solicitante',
    ]);
  });

  // --- Regresión cruzada, accesibilidad y bordes (enmienda 012, E12-A6) ---

  describe('regresión cruzada, accesibilidad y bordes (E12-A6)', () => {
    /** Formulario real que contiene el control indicado (alta o edición). */
    function formularioDe(selectorControl: string): HTMLFormElement {
      const control = (fixture.nativeElement as HTMLElement).querySelector(
        selectorControl,
      );
      const formulario = control?.closest('form');
      expect(formulario)
        .withContext(`formulario de ${selectorControl}`)
        .toBeTruthy();
      return formulario as HTMLFormElement;
    }

    /**
     * Auditoría de accesibilidad de los controles del formulario: cada `label`
     * apunta a un control existente, cada control tiene nombre accesible, foco
     * visible, `tabindex` no negativo e ids únicos (AC-24/AC-27).
     */
    function verificarEtiquetasYFoco(formulario: HTMLFormElement): void {
      const etiquetas = Array.from(formulario.querySelectorAll('label[for]'));
      expect(etiquetas.length)
        .withContext('labels asociados del formulario')
        .toBeGreaterThan(0);
      for (const etiqueta of etiquetas) {
        const destino = etiqueta.getAttribute('for') ?? '';
        const control = formulario.querySelector(`#${destino}`);
        expect(control).withContext(`label ${destino}`).toBeTruthy();
        expect(['INPUT', 'SELECT', 'TEXTAREA']).toContain(
          control?.tagName ?? '',
        );
      }

      const controles = Array.from(
        formulario.querySelectorAll<HTMLElement>(
          'input, select, textarea',
        ),
      ).filter(
        (control) =>
          !(control instanceof HTMLInputElement && control.type === 'hidden'),
      );
      const ids = controles.map((control) => control.id).filter(Boolean);
      expect(new Set(ids).size)
        .withContext('ids únicos en el formulario')
        .toBe(ids.length);
      for (const control of controles) {
        const etiquetado =
          ((control as HTMLInputElement).labels?.length ?? 0) > 0 ||
          control.hasAttribute('aria-label') ||
          control.hasAttribute('aria-labelledby');
        expect(etiquetado)
          .withContext(`control ${control.id} con nombre accesible`)
          .toBe(true);
        expect(control.className)
          .withContext(`foco visible de ${control.id}`)
          .toContain('focus-visible:ring-2');
        const tabindex = control.getAttribute('tabindex');
        expect(tabindex === null || Number(tabindex) >= 0)
          .withContext(`tabindex de ${control.id}`)
          .toBe(true);
      }
    }

    /** Primer elemento con `role="alert"` cuyo texto cumple el patrón. */
    function avisoConTexto(patron: RegExp): HTMLElement | undefined {
      return Array.from(
        (fixture.nativeElement as HTMLElement).querySelectorAll<HTMLElement>(
          '[role="alert"]',
        ),
      ).find((elemento) => patron.test(elemento.textContent ?? ''));
    }

    it('AC-24: el alta asocia labels y describe el Departamento automático del Bodeguero', () => {
      montar([], ROLES, DEPARTAMENTOS_POR_SEDE, SEDES);
      abrirAlta();

      const formulario = formularioDe('#crear-usuario-nombre');
      verificarEtiquetasYFoco(formulario);

      const departamento = selectAlta('#crear-usuario-departamento');
      expect(departamento).toBeTruthy();
      expect(departamento?.disabled).toBe(true);
      const descrito = departamento?.getAttribute('aria-describedby');
      expect(descrito).toBe('crear-usuario-departamento-ayuda');
      const ayuda = formulario.querySelector<HTMLElement>(`#${descrito}`);
      expect(ayuda?.textContent).toContain('Suministros');
      expect((departamento?.options[0].textContent ?? '').trim()).toBe(
        'Suministros (asignación automática)',
      );
    });

    it('AC-24/AC-31: el aviso de tenant sin sedes se anuncia como alerta y describe la Sede', () => {
      montar([], ROLES, DEPARTAMENTOS_POR_SEDE, []);
      abrirAlta();

      const sede = selectAlta('#crear-usuario-sede');
      expect(sede?.getAttribute('aria-describedby')).toBe(
        'crear-usuario-sede-ayuda',
      );
      const ayuda = avisoConTexto(/no tiene sedes/i);
      expect(ayuda?.id).toBe('crear-usuario-sede-ayuda');
      expect(ayuda?.getAttribute('role')).toBe('alert');
    });

    it('AC-27: la edición del Bodeguero asocia labels, describe el Departamento automático y anuncia la falta de sedes', () => {
      montar(
        [usuario({ departamento_id: 15, sede_id: null })],
        ROLES,
        DEPARTAMENTOS_EDICION_SIN_SUMINISTROS,
        [],
      );
      abrirEdicion();

      const formulario = formularioDe('#editar-usuario-nombre');
      verificarEtiquetasYFoco(formulario);

      const departamento = selectEdicion('#editar-usuario-departamento');
      expect(departamento?.disabled).toBe(true);
      expect(departamento?.getAttribute('aria-describedby')).toBe(
        'editar-usuario-departamento-ayuda',
      );
      expect(
        formulario.querySelector('#editar-usuario-departamento-ayuda')
          ?.textContent,
      ).toContain('Suministros');

      const sede = selectEdicion('#editar-usuario-sede');
      expect(sede?.getAttribute('aria-describedby')).toBe(
        'editar-usuario-sede-ayuda',
      );
      expect(sede?.hasAttribute('disabled')).toBe(false);
      expect(avisoConTexto(/no tiene sedes/i)?.id).toBe(
        'editar-usuario-sede-ayuda',
      );
    });

    it('AC-24/AC-29: con solo «Suministros», el alta de un rol no Bodeguero se indica y no se envía', () => {
      montar([], ROLES, DEPARTAMENTOS_SOLO_SUMINISTROS, SEDES);
      abrirAlta();
      rellenarDatosAlta();
      elegirRol(4);

      expect(opcionesSelectAlta('#crear-usuario-departamento')).toEqual([
        'Selecciona un departamento',
      ]);
      const aviso = avisoConTexto(/no hay departamentos disponibles/i);
      expect(aviso).toBeTruthy();
      expect(aviso?.getAttribute('role')).toBe('alert');
      expect(fixture.componentInstance.formularioCreacion.invalid).toBe(true);

      boton('crear usuario')?.click();
      fixture.detectChanges();
      httpMock.expectNone(`${URL_API}/usuarios/`);
    });

    it('AC-24: el alta no Bodeguera bloquea el «Suministros» heredado y lo indica', () => {
      montar([], ROLES, DEPARTAMENTOS_POR_SEDE, SEDES);
      abrirAlta();
      rellenarDatosAlta();
      elegirRol(4);
      fixture.componentInstance.formularioCreacion.controls.departamento_id.setValue(
        14,
      );
      fixture.detectChanges();

      expect(fixture.componentInstance.creacionSeleccionaSuministros()).toBe(
        true,
      );
      expect(avisoConTexto(/solo se asigna automáticamente/i)).toBeTruthy();
      expect(boton('crear usuario')?.disabled).toBe(true);

      fixture.componentInstance.guardarCreacion();
      fixture.detectChanges();
      httpMock.expectNone(`${URL_API}/usuarios/`);
      expect(texto()).toContain('solo se asigna automáticamente');
    });

    it('AC-29: la edición no Bodeguera bloquea el «Suministros» heredado y lo indica', () => {
      montar(
        [usuario({ rol_id: 4, departamento_id: 11, sede_id: null })],
        ROLES,
        DEPARTAMENTOS_EDICION,
        SEDES,
      );
      abrirEdicion();
      elegirDepartamentoEdicion(14);
      completarMotivoEdicion();

      expect(fixture.componentInstance.edicionSeleccionaSuministros()).toBe(
        true,
      );
      expect(avisoConTexto(/solo se asigna automáticamente/i)).toBeTruthy();
      expect(boton('guardar cambios')?.disabled).toBe(true);

      fixture.componentInstance.guardarEdicion();
      fixture.detectChanges();
      httpMock.expectNone(`${URL_API}/usuarios/1`);
      expect(texto()).toContain('solo se asigna automáticamente');
    });

    it('AC-24/AC-27: un Administrador que pasa a Bodeguero exige sede y el 409 del último Administrador no llama a la sede', () => {
      identidadFalsa.set(identidad('Superadmin'));
      montar(
        [usuario({ rol_id: 2, departamento_id: 11, sede_id: null })],
        ROLES_CUATRO,
        DEPARTAMENTOS_EDICION,
        SEDES,
      );
      abrirEdicion();

      // Matriz de edición: Administrador sin Sede → Bodeguero con Sede y sin
      // Departamento (lo resuelve el servidor).
      expect(selectEdicion('#editar-usuario-sede')).toBeNull();
      elegirRolEdicion(3);
      expect(selectEdicion('#editar-usuario-sede')).toBeTruthy();
      expect(selectEdicion('#editar-usuario-departamento')?.disabled).toBe(
        true,
      );
      expect(
        fixture.componentInstance.formularioEdicion.controls.sede_id.hasError(
          'required',
        ),
      ).toBe(true);
      expect(fixture.componentInstance.hayCambiosEdicion()).toBe(true);
      expect(boton('guardar cambios')?.disabled).toBe(true);

      elegirSedeEdicion(1);
      completarMotivoEdicion();
      expect(boton('guardar cambios')?.disabled).toBe(false);
      boton('guardar cambios')?.click();
      fixture.detectChanges();

      const peticion = httpMock.expectOne(`${URL_API}/usuarios/1`);
      expect(peticion.request.method).toBe('PUT');
      const cuerpo = peticion.request.body as Record<string, unknown>;
      expect(cuerpo['rol_id']).toBe(3);
      expect('departamento_id' in cuerpo).toBe(false);
      expect('sede_id' in cuerpo).toBe(false);
      expect(cuerpo['motivo']).toEqual({
        codigo: 'reasignacion_organizacional',
        texto: null,
      });
      peticion.flush(
        {
          detail:
            'No se puede dar de baja al ultimo Administrador activo de la institucion',
        },
        { status: 409, statusText: 'Conflict' },
      );
      fixture.detectChanges();

      httpMock.expectNone(`${URL_API}/organizacion/usuarios/1/sede`);
      expect(avisoConTexto(/Administrador activo/i)).toBeTruthy();
      expect(selectEdicion('#editar-usuario-departamento')).toBeTruthy();
    });
  });

  // --- Regresión DOM de selects (corrección post-recorrido 27/Nov/2026) ---

  describe('regresión DOM de selects (corrección post-recorrido)', () => {
    it('AC-24/AC-25: elegir Solicitante desde el DOM muestra la Sede del alta, filtra y envía números', () => {
      montar([], ROLES, DEPARTAMENTOS_POR_SEDE, SEDES);
      abrirAlta();

      // El alta arranca en Bodeguero con Sede visible; al cambiar a Solicitante
      // el control debe seguir visible como filtro (no desaparecer).
      elegirOpcionDom('#crear-usuario-rol', 'Solicitante');
      expect(
        fixture.componentInstance.formularioCreacion.controls.rol_id.value,
      ).toBe(4);
      const sede = selectAlta('#crear-usuario-sede');
      expect(sede).toBeTruthy();
      expect(sede?.disabled).toBe(false);
      expect(
        fixture.componentInstance.formularioCreacion.controls.sede_id.hasError(
          'required',
        ),
      ).toBe(false);

      rellenarDatosAlta();
      elegirOpcionDom('#crear-usuario-sede', 'Sede Central');
      expect(opcionesSelectAlta('#crear-usuario-departamento')).toEqual([
        'Selecciona un departamento',
        'Logística',
      ]);
      elegirOpcionDom('#crear-usuario-departamento', 'Logística');

      boton('crear usuario')?.click();
      fixture.detectChanges();

      const peticion = httpMock.expectOne(`${URL_API}/usuarios/`);
      const cuerpo = peticion.request.body as Record<string, unknown>;
      expect(cuerpo['rol_id']).toBe(4);
      expect(typeof cuerpo['rol_id']).toBe('number');
      expect(cuerpo['departamento_id']).toBe(11);
      expect(typeof cuerpo['departamento_id']).toBe('number');
      expect('sede_id' in cuerpo).toBe(false);

      peticion.flush(
        invitacion({
          usuario_id: 20,
          nombre: 'Nuevo',
          apellido: 'Solicitante',
          rol_id: 4,
          departamento_id: 11,
          sede_id: null,
          estado_invitacion: 'aceptada',
          url_invitacion: null,
        }),
      );
      fixture.detectChanges();

      httpMock.expectNone(`${URL_API}/organizacion/usuarios/20/sede`);
      confirmarRecarga([], DEPARTAMENTOS_POR_SEDE);
      expect(texto()).toContain('invitación aceptada');
    });

    it('AC-29: elegir Solicitante desde el DOM mantiene la Sede de edición, filtra y envía números', () => {
      montar(
        [usuario({ rol_id: 3, departamento_id: 14, sede_id: 1 })],
        ROLES,
        DEPARTAMENTOS_EDICION,
        SEDES,
      );
      abrirEdicion();

      elegirOpcionDom('#editar-usuario-rol', 'Solicitante');
      expect(
        fixture.componentInstance.formularioEdicion.controls.rol_id.value,
      ).toBe(4);
      const sede = selectEdicion('#editar-usuario-sede');
      expect(sede).toBeTruthy();
      expect(sede?.disabled).toBe(false);
      expect(selectEdicion('#editar-usuario-departamento')?.disabled).toBe(false);
      expect(
        fixture.componentInstance.formularioEdicion.controls.sede_id.value,
      ).toBeNull();

      elegirOpcionDom('#editar-usuario-sede', 'Sede Central');
      expect(opcionesSelectEdicion('#editar-usuario-departamento')).toEqual([
        'Selecciona un departamento',
        'Logística',
        'Biblioteca',
      ]);
      elegirOpcionDom('#editar-usuario-departamento', 'Logística');
      expect(
        fixture.componentInstance.formularioEdicion.controls.sede_id.value,
      ).toBe(1);
      expect(fixture.componentInstance.hayCambiosEdicion()).toBe(true);

      completarMotivoEdicion();
      boton('guardar cambios')?.click();
      fixture.detectChanges();

      const peticion = httpMock.expectOne(`${URL_API}/usuarios/1`);
      const cuerpo = peticion.request.body as Record<string, unknown>;
      expect(cuerpo['rol_id']).toBe(4);
      expect(typeof cuerpo['rol_id']).toBe('number');
      expect(cuerpo['departamento_id']).toBe(11);
      expect(typeof cuerpo['departamento_id']).toBe('number');
      expect('sede_id' in cuerpo).toBe(false);
      peticion.flush(
        usuario({ rol_id: 4, departamento_id: 11, sede_id: 1 }),
      );
      fixture.detectChanges();

      httpMock.expectNone(`${URL_API}/organizacion/usuarios/1/sede`);
      confirmarRecarga([usuario({ rol_id: 4, departamento_id: 11, sede_id: 1 })]);
    });
  });
});
