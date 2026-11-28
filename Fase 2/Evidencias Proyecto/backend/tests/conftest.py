"""Fixtures compartidas para la suite de la Feature 001.

El seam bajo prueba es la **interfaz HTTP** (`TestClient`), nunca la capa de
servicios ni la sesion de SQLAlchemy. `tests/funcional/` verifica unicamente
comportamiento observable desde la API.

La suite esta organizada por tipo de prueba en `tests/funcional/` (unitarios,
integracion, sistema, e2e, aceptacion, humo) y `tests/no_funcional/`
(rendimiento, seguridad y los pendientes). Ver `tests/README.md`.

La base es SQLite en memoria para que la suite corra sin depender del
contenedor de PostgreSQL. Las aserciones no consultan la base directamente:
todo se comprueba leyendo la API, igual que lo haria un cliente real.

Enmienda 007 (26/Nov/2026, E26N-1): `identidad_actual` es un contenedor
mutable que permite alternar roles con `actuar_como` sobre un mismo
`TestClient`; `identidad_persistida` crea a demanda usuarios reales de
Bodeguero/Solicitante sin ampliar el catalogo base de `datos_base`.
"""

import os
from contextlib import contextmanager

# `app.db.database` resuelve la URL al importarse y `config.py` ya no trae
# valores por defecto. La suite redirige cada sesion a su SQLite en memoria, asi
# que el motor module-level solo necesita una URL valida. Se fija antes de
# importar `app` y sobrescribe cualquier `DB_URL` real del shell para que ningun
# test toque una base de verdad.
os.environ["DB_URL"] = "sqlite+pysqlite:///:memory:"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import dependencies
from app.core import eventos as bus_eventos
from app.core.config import settings as configuracion

# Feature 025: la suite heredada no debe abrir conexiones a Redis ni pagar
# timeouts. El apagado se hace sobre el singleton y no con una variable de
# entorno, para que `Settings()` siga exponiendo los defaults reales.
configuracion.LIMITE_TASA_HABILITADO = False

# Feature 028 (plan §9.1): la suite heredada publica a un no-op y no abre
# Redis. `TIEMPO_REAL_HABILITADO=False` corta la publicacion antes de consultar
# la audiencia o tocar el almacen; `AlmacenNulo` queda como almacen vigente para
# que cualquier publicacion directa de un test sea inocua. Los tests del canal
# encienden el interruptor y sustituyen el almacen por el bus falso.
configuracion.TIEMPO_REAL_HABILITADO = False
bus_eventos.configurar_almacen(bus_eventos.AlmacenNulo())

from app.db.database import Base
from app.main import app
from app.models import (
    BaseControl,
    Categoria,
    Departamento,
    EstadoTicket,
    Institucion,
    Prioridad,
    Producto,
    Rol,
    Sede,
    StockSede,
    Usuario,
)
from app.services.auth_service import IdentidadAutenticada

#: Motor en memoria. `StaticPool` mantiene una sola conexion para que la base
#: sobreviva entre el hilo de `TestClient` y el hilo principal.
SQLITE_MEMORIA = "sqlite+pysqlite:///:memory:"


@pytest.fixture
def motor():
    """Motor efimero con las 12 tablas creadas, con FKs activadas."""
    motor = create_engine(
        SQLITE_MEMORIA,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(motor, "connect")
    def activar_llaves_foraneas(conexion, _registro):
        # SQLite ignora las FKs salvo que se activen explicitamente. Sin esto,
        # el test de atomicidad (AC-8) no podria provocar la violacion que
        # dispara el rollback.
        conexion.execute("PRAGMA foreign_keys=ON")

    # Feature 012: el canonico de control (`InstitucionControl` + `funcion_institucion`)
    # se crea **primero**, de modo que la tabla compartida `institucion` de SQLite
    # sea el superset (espejo tenant de dos columnas + `rut`/`direccion`/`activo`).
    # Luego `Base.metadata` crea el resto y **se salta** `institucion` por
    # `checkfirst`: en el contexto logico unico control y tenant comparten tabla.
    BaseControl.metadata.create_all(motor)
    Base.metadata.create_all(motor)
    yield motor
    # `funcion_institucion` (control-only) referencia `institucion`; se elimina
    # antes del `drop_all` del tenant, que no conoce la tabla auxiliar y de otro
    # modo chocaria con la FK activada.
    BaseControl.metadata.tables["funcion_institucion"].drop(motor, checkfirst=True)
    Base.metadata.drop_all(motor)
    motor.dispose()


def identidad_de_prueba() -> IdentidadAutenticada:
    """Identidad autenticada inyectable para la suite funcional legacy.

    Tras la Feature 006 el router agregado de v1 exige Bearer. Las pruebas de
    negocio, que no comprueban autenticacion, necesitan una identidad resuelta
    para seguir ejerciendo su comportamiento funcional. Se construye un usuario
    local valido (no persistido: los endpoints de negocio no consumen la
    identidad) con un `sub` de Clerk ficticio. Nunca se usa una clave real.

    Feature 007 (T2): la autorizacion por rol ya esta cableada a cada operacion;
    la identidad legacy se elegia **Superadmin** porque su alcance global cubria
    las 18 operaciones y la suite funcional no se convertia, sin querer, en una
    prueba de denegacion.

    Feature 008 (T5, D-3): el ajuste de la matriz retira a Superadmin la
    escritura de catalogo, stock/movimientos y tickets (ahora 403). El unico rol
    que conserva las tres familias de escritura es **Administrador**, y la
    identidad legacy pasa a ese rol. Su alcance institucional se resuelve por
    `departamento_id=1`, que en estas pruebas pertenece a INST01 (la unica
    institucion que siembra la suite funcional). Las pruebas de autorizacion
    construyen su propia identidad por rol (ver
    `tests/no_funcional/seguridad/test_permisos_endpoints.py`).
    """
    usuario = Usuario(
        usuario_id=1,
        nombre="Identidad",
        apellido="De Prueba",
        correo="identidad.legacy@compustock.cl",
        departamento_id=1,
        rol_id=1,
    )
    usuario.rol = Rol(nombre_rol="Administrador")
    return IdentidadAutenticada(usuario=usuario, sub="sub-legacy-pruebas")


def _identidad_autenticada(
    *,
    usuario_id: int,
    departamento_id: int,
    rol_id: int,
    nombre_rol: str,
    correo: str,
    nombre: str = "Identidad",
    apellido: str = "De Prueba",
) -> IdentidadAutenticada:
    """Usuario suelto con ids reales y el rol legible pedido (patron de 011).

    No se persiste: la autorizacion solo lee `usuario.rol.nombre_rol` y los
    endpoints que releen el usuario lo hacen por `usuario_id` en la base.
    """
    usuario = Usuario(
        usuario_id=usuario_id,
        nombre=nombre,
        apellido=apellido,
        correo=correo,
        departamento_id=departamento_id,
        rol_id=rol_id,
    )
    usuario.rol = Rol(nombre_rol=nombre_rol)
    return IdentidadAutenticada(
        usuario=usuario, sub=f"sub-prueba-{nombre_rol.lower()}"
    )


def _rol_solicitante(datos_base, motor) -> int:
    """Devuelve el rol Solicitante, reutilizando el de `dos_instituciones`.

    Enmienda 007 (E26N-1, DT-5): el rol se busca por nombre para no duplicarlo
    cuando la suite ya sembro el padron multiinstitucion; solo se crea si falta.
    """
    if "rol_solicitante_id" in datos_base:
        return datos_base["rol_solicitante_id"]

    with sessionmaker(bind=motor)() as db:
        rol = db.execute(
            select(Rol).where(Rol.nombre_rol == "Solicitante")
        ).scalars().first()
        if rol is None:
            rol = Rol(
                nombre_rol="Solicitante",
                descripcion="Rol limitado de prueba (E26N-1)",
            )
            db.add(rol)
            db.commit()
            db.refresh(rol)
        rol_id = rol.rol_id

    datos_base["rol_solicitante_id"] = rol_id
    return rol_id


def _buscar_o_crear_usuario(
    motor,
    *,
    rol_id: int,
    departamento_id: int,
    correo: str,
    nombre_rol: str,
) -> tuple[int, str]:
    """Primer usuario con ese rol en el departamento, o uno nuevo persistido.

    Devuelve `(usuario_id, correo)` y es idempotente: una segunda llamada con el
    mismo rol y departamento reutiliza la fila creada por la primera.
    """
    with sessionmaker(bind=motor)() as db:
        usuario = db.execute(
            select(Usuario)
            .where(
                Usuario.rol_id == rol_id,
                Usuario.departamento_id == departamento_id,
            )
            .order_by(Usuario.usuario_id)
        ).scalars().first()
        if usuario is None:
            usuario = Usuario(
                nombre=nombre_rol,
                apellido="Prueba",
                correo=correo,
                departamento_id=departamento_id,
                rol_id=rol_id,
            )
            db.add(usuario)
            db.commit()
            db.refresh(usuario)
        return usuario.usuario_id, usuario.correo


def identidad_persistida(datos_base, rol: str, motor=None) -> IdentidadAutenticada:
    """Identidad autenticada con ids reales; persiste solo cuando hace falta.

    Enmienda 007 (E26N-1, DT-5): Administrador reutiliza a Ana
    (`datos_base["usuario_id"]`) y Superadmin es una identidad suelta porque su
    403 de matriz ocurre antes de la base. Bodeguero y Solicitante se buscan o
    crean de forma idempotente en el departamento de `datos_base`, y los ids
    resultantes quedan expuestos ahi (`usuario_bodeguero_id`,
    `rol_solicitante_id` y `usuario_solicitante_id`). La sede **no** se asigna:
    cada suite la resuelve con `asegurar_sede_de_departamento` o su helper.
    """
    nombre_rol = (rol or "").strip()
    departamento_id = datos_base["departamento_id"]

    if nombre_rol == "Administrador":
        return _identidad_autenticada(
            usuario_id=datos_base["usuario_id"],
            departamento_id=departamento_id,
            rol_id=datos_base["rol_id"],
            nombre_rol="Administrador",
            correo=datos_base["correo_usado"],
            nombre="Ana",
            apellido="Perez",
        )
    if nombre_rol == "Superadmin":
        return _identidad_autenticada(
            usuario_id=datos_base["usuario_id"],
            departamento_id=departamento_id,
            rol_id=datos_base["rol_id"],
            nombre_rol="Superadmin",
            correo=datos_base["correo_usado"],
        )
    if nombre_rol not in {"Bodeguero", "Solicitante"}:
        raise ValueError(f"rol no soportado por el harness de pruebas: {rol!r}")
    if motor is None:
        raise ValueError(
            "identidad_persistida necesita `motor` para persistir "
            f"el rol {nombre_rol}"
        )

    if nombre_rol == "Bodeguero":
        rol_id = datos_base["rol_bodeguero_id"]
        clave_usuario = "usuario_bodeguero_id"
        correo = "bodeguero.harness007@compustock.cl"
    else:
        rol_id = _rol_solicitante(datos_base, motor)
        clave_usuario = "usuario_solicitante_id"
        correo = "solicitante.harness007@compustock.cl"

    usuario_id, correo_persistido = _buscar_o_crear_usuario(
        motor,
        rol_id=rol_id,
        departamento_id=departamento_id,
        correo=correo,
        nombre_rol=nombre_rol,
    )
    datos_base[clave_usuario] = usuario_id
    return _identidad_autenticada(
        usuario_id=usuario_id,
        departamento_id=departamento_id,
        rol_id=rol_id,
        nombre_rol=nombre_rol,
        correo=correo_persistido,
        nombre=nombre_rol,
        apellido="Prueba",
    )


#: Centinela para distinguir un override ausente de uno instalado con `None`.
_SIN_OVERRIDE = object()


def _registrar_override(previos: dict, clave: object, valor: object) -> None:
    """Instala un override y recuerda su valor previo (o su ausencia)."""
    previos[clave] = app.dependency_overrides.get(clave, _SIN_OVERRIDE)
    app.dependency_overrides[clave] = valor


def _restaurar_overrides(previos: dict) -> None:
    """Devuelve las claves tocadas a su estado previo, sin `clear()` global.

    Enmienda 007 (E26N-1, DT-4): un cliente anidado o un helper que ya overridea
    `get_current_user` conserva su estado al salir del contexto.
    """
    for clave, valor in previos.items():
        if valor is _SIN_OVERRIDE:
            app.dependency_overrides.pop(clave, None)
        else:
            app.dependency_overrides[clave] = valor


@contextmanager
def _cliente_de_prueba(motor, identidad_actual=None, **opciones):
    """Enlaza `get_db` al motor en memoria durante el contexto.

    Ademas overridea `get_current_user` con la identidad del contenedor mutable
    `identidad_actual` para que la suite funcional legacy vuelva a ejercer su
    comportamiento de negocio bajo el router protegido y para que `actuar_como`
    cambie de rol sin recrear el `TestClient` (E26N-1, DT-4). Este override vive
    **solo** en el harness de tests y no se aplica a `test_auth.py`, cuyas
    pruebas de seguridad construyen su propio cliente sin el override.

    Los overrides que instala se guardan y se restauran al salir; nunca se borra
    el diccionario completo, de modo que un cliente anidado no pisa el estado
    del cliente externo.
    """
    FabricaSesion = sessionmaker(autocommit=False, autoflush=False, bind=motor)

    def obtener_db_de_prueba():
        db = FabricaSesion()
        try:
            yield db
        finally:
            db.close()

    contenedor = (
        identidad_actual
        if identidad_actual is not None
        else {"actual": identidad_de_prueba()}
    )

    previos: dict = {}
    try:
        _registrar_override(previos, dependencies.get_db, obtener_db_de_prueba)
        # El rol se lee en **cada peticion** del contenedor mutable.
        _registrar_override(
            previos,
            dependencies.get_current_user,
            lambda: contenedor["actual"],
        )
        # Feature 024 (T6): `/ready` usa SQLite en la suite, no el motor dedicado
        # a PostgreSQL que se crea en `app.db.database`.
        _registrar_override(
            previos, dependencies.obtener_motor_readiness, lambda: motor
        )
        # Feature 012 (D-3/AC-8): el alta local verifica el correo contra Clerk.
        # La costura se overridea para no invocar la red (el alta no crea cuentas).
        _registrar_override(
            previos,
            dependencies.obtener_verificador_correo_clerk,
            lambda: (lambda _correo: True),
        )
        from tests.funcional.integracion.soporte_frontera_017 import (
            instalar_frontera_clerk,
        )

        # La frontera Clerk instala tres costuras mas: se registran antes para
        # devolverlas a su estado previo y no contaminar la suite.
        for clave in (
            dependencies.obtener_consultor_identidad_clerk,
            dependencies.obtener_creador_invitacion_clerk,
            dependencies.obtener_revocador_invitacion_clerk,
        ):
            previos[clave] = app.dependency_overrides.get(clave, _SIN_OVERRIDE)
        instalar_frontera_clerk(identidad_existente=True)

        with TestClient(app, **opciones) as cliente_http:
            yield cliente_http
    finally:
        _restaurar_overrides(previos)


@pytest.fixture
def identidad_actual():
    """Contenedor mutable de la identidad de la sesion de prueba (E26N-1).

    `cliente` y `cliente_sin_excepcion` leen `identidad_actual["actual"]` en cada
    peticion; `actuar_como` lo sustituye sin recrear el `TestClient`.
    """
    return {"actual": identidad_de_prueba()}


@pytest.fixture
def cliente(motor, identidad_actual):
    """`TestClient` con `get_db` redirigido al motor en memoria."""
    with _cliente_de_prueba(motor, identidad_actual) as cliente_http:
        yield cliente_http


@pytest.fixture
def cliente_sin_excepcion(motor, identidad_actual):
    """Igual que `cliente`, pero las excepciones no manejadas se vuelven 500.

    `TestClient` por defecto relanza la excepcion en vez de responder, lo que
    impide observar que la API devuelve 500 ante un error de base de datos.
    Comparte el contenedor de identidad con `cliente` (misma sesion mutable).
    """
    with _cliente_de_prueba(
        motor, identidad_actual, raise_server_exceptions=False
    ) as cliente_http:
        yield cliente_http


@pytest.fixture
def datos_base(motor):
    """Catalogo minimo para poder crear tickets, usuarios y movimientos.

    Devuelve un dict con los ids generados por SQLite, porque en PostgreSQL las
    secuencias de identidad arrancan donde deje la ultima prueba y no es
    assumible un id fijo: los tests no codifican ids de catalogo.
    """
    db = sessionmaker(bind=motor)()
    try:
        rol = Rol(nombre_rol="Administrador", descripcion="Rol de prueba")
        db.add(rol)
        db.flush()

        # Rol asignable por el rol legacy (Feature 008: la identidad de la suite
        # funcional es Administrador, que solo puede asignar Bodeguero/Solicitante,
        # D-6/AC-10). El catalogo minimo lo necesita para el alta de usuarios.
        rol_bodeguero = Rol(nombre_rol="Bodeguero", descripcion="Rol asignable de prueba")
        db.add(rol_bodeguero)
        db.flush()

        institucion = Institucion(
            institucion_id="INST01",
            nombre="Instituto de Prueba",
        )
        db.add(institucion)
        db.flush()

        departamento = Departamento(
            nombre_dep="Operaciones",
            descripcion="Departamento de prueba",
            institucion_id=institucion.institucion_id,
        )
        db.add(departamento)
        db.flush()

        usuario = Usuario(
            nombre="Ana",
            apellido="Perez",
            correo="ana.prueba@compustock.cl",
            departamento_id=departamento.departamento_id,
            rol_id=rol.rol_id,
        )
        db.add(usuario)
        db.flush()

        prioridad = Prioridad(nombre="ALTA", descripcion="Prioridad alta")
        db.add(prioridad)
        db.flush()

        # Enmienda 26/Nov/2026 (D-27): el alta nace en `EnRevision`, y
        # `Cerrado` se reserva al retiro. Los nombres canonicos importan: el
        # servicio los resuelve por nombre (case-insensitive), no por id.
        estado_ingresado = EstadoTicket(
            nombre="EnRevision", descripcion="Ticket recien creado"
        )
        db.add(estado_ingresado)
        db.flush()

        estado_cerrado = EstadoTicket(nombre="Cerrado", descripcion="Ticket cerrado")
        db.add(estado_cerrado)
        db.flush()

        # Feature 008 (D-1): el catalogo es institucional. La institucion de
        # `datos_base` es INST01, y la pertenencia se ancla en las columnas
        # `institucion_id` que T6 puebla (el DDL de instalacion nueva las declara
        # NOT NULL; aqui sostienen las FK compuestas).
        categoria = Categoria(
            nombre_cat="Papeleria",
            descripcion_cat="Insumos de papeleria",
            institucion_id=institucion.institucion_id,
        )
        # Feature 014 (AC-13): el fixture declara explicitamente la vigencia del
        # catalogo para no depender de que la columna falte. Antes de T4 `activo`
        # aun no es columna mapeada y la asignacion es un atributo suelto.
        categoria.activo = True
        db.add(categoria)
        db.flush()

        producto = Producto(
            nombre="Cuaderno linedado",
            descripcion="Cuaderno de 100 hojas",
            unidad_medida="UNIDAD",
            stock_minimo=10,
            categoria_id=categoria.categoria_id,
            institucion_id=institucion.institucion_id,
        )
        producto.activo = True  # Feature 014: nace activo (AC-13).
        db.add(producto)
        db.flush()

        # Feature 026: `inventario` desaparecio y el saldo vivo es `stock_sede`.
        # La fixture base no siembra sedes ni saldo operativo: cada caso declara
        # el suyo con `asegurar_sede_de_departamento` (o su propio sembrado), de
        # modo que los totales no arrastren stock ajeno al escenario.
        db.commit()

        return {
            "rol_id": rol.rol_id,
            "rol_nombre": rol.nombre_rol,
            "rol_bodeguero_id": rol_bodeguero.rol_id,
            "departamento_id": departamento.departamento_id,
            "institucion_id": institucion.institucion_id,
            "usuario_id": usuario.usuario_id,
            "prioridad_id": prioridad.prioridad_id,
            "estado_ingresado_id": estado_ingresado.estado_id,
            "estado_cerrado_id": estado_cerrado.estado_id,
            "categoria_id": categoria.categoria_id,
            "producto_id": producto.producto_id,
            "correo_usado": usuario.correo,
        }
    finally:
        db.close()


@pytest.fixture
def actuar_como(motor, datos_base, identidad_actual):
    """Cambia el rol de la sesion de prueba sin recrear el `TestClient`.

    Enmienda 007 (E26N-1, DT-4): debe poder invocarse despues de crear
    `cliente` y antes de cada peticion. Devuelve la identidad resultante y deja
    en `datos_base` los ids de los usuarios o roles persistidos que el rol
    necesite (ver `identidad_persistida`).
    """

    def _cambiar(rol: str) -> IdentidadAutenticada:
        identidad_actual["actual"] = identidad_persistida(datos_base, rol, motor)
        return identidad_actual["actual"]

    return _cambiar


@pytest.fixture
def cliente_solicitante(cliente, actuar_como):
    """Deja el contenedor en Solicitante y devuelve el mismo `cliente`."""
    actuar_como("Solicitante")
    return cliente


@pytest.fixture
def dos_instituciones(motor, datos_base):
    """Padron multiinstitucion compartido (Feature 008, T9).

    Sobre `datos_base` (INST01: institucion, departamento "Operaciones", catalogo
    "Papeleria"/"Cuaderno linedado" con existencia 50, usuario Administrador Ana y
    los roles Administrador/Bodeguero) agrega:

    * el catalogo global de los cuatro roles (Superadmin y Solicitante);
    * INST02 ("Instituto Ajeno") con su departamento y un usuario persistido por
      cada uno de los cuatro roles;
    * una categoria y un producto **homonimos** de los de INST01 ("Papeleria" /
      "Cuaderno linedado"), con su propia existencia (stock 5), para comprobar el
      aislamiento de catalogo y stock (AC-1, AC-5, AC-6).

    No construye las identidades de prueba: cada suite decide el rol y el
    departamento del actor. Aporta un mundo coherente de dos instituciones y
    cuatro roles que las suites no tienen que resembrar, y con las columnas
    institucionales pobladas (el esquema las exige NOT NULL desde T9).
    """
    db = sessionmaker(bind=motor)()
    try:
        rol_superadmin = Rol(nombre_rol="Superadmin", descripcion="Rol global")
        rol_solicitante = Rol(nombre_rol="Solicitante", descripcion="Rol limitado")
        db.add_all([rol_superadmin, rol_solicitante])
        db.flush()

        institucion_ajena = Institucion(
            institucion_id="INST02",
            nombre="Instituto Ajeno",
        )
        db.add(institucion_ajena)
        db.flush()

        departamento_ajeno = Departamento(
            nombre_dep="Bodega Sur",
            descripcion="Deposito de la institucion ajena",
            institucion_id="INST02",
        )
        db.add(departamento_ajeno)
        db.flush()

        roles = {
            "Administrador": datos_base["rol_id"],
            "Bodeguero": datos_base["rol_bodeguero_id"],
            "Solicitante": rol_solicitante.rol_id,
            "Superadmin": rol_superadmin.rol_id,
        }

        # INST01: Ana (datos_base) ya es Administrador; se agregan los otros tres.
        usuarios_inst01 = {"Administrador": datos_base["usuario_id"]}
        for nombre_rol, rol_id in roles.items():
            if nombre_rol == "Administrador":
                continue
            usuario = Usuario(
                nombre=nombre_rol,
                apellido="Inst01",
                correo=f"{nombre_rol.lower()}.inst01@compustock.cl",
                departamento_id=datos_base["departamento_id"],
                rol_id=rol_id,
            )
            db.add(usuario)
            db.flush()
            usuarios_inst01[nombre_rol] = usuario.usuario_id

        # INST02: un usuario por rol.
        usuarios_inst02: dict[str, int] = {}
        for nombre_rol, rol_id in roles.items():
            usuario = Usuario(
                nombre=nombre_rol,
                apellido="Inst02",
                correo=f"{nombre_rol.lower()}.inst02@compustock.cl",
                departamento_id=departamento_ajeno.departamento_id,
                rol_id=rol_id,
            )
            db.add(usuario)
            db.flush()
            usuarios_inst02[nombre_rol] = usuario.usuario_id

        # Homonimos institucionales con existencia independiente (AC-1, AC-6).
        categoria_homonima = Categoria(
            nombre_cat="Papeleria",
            descripcion_cat="Homonimo de INST02",
            institucion_id="INST02",
        )
        categoria_homonima.activo = True  # Feature 014: homonimo vigente (AC-13).
        db.add(categoria_homonima)
        db.flush()

        producto_homonimo = Producto(
            nombre="Cuaderno linedado",
            descripcion="Homonimo de INST02",
            unidad_medida="UNIDAD",
            stock_minimo=10,
            categoria_id=categoria_homonima.categoria_id,
            institucion_id="INST02",
        )
        producto_homonimo.activo = True  # Feature 014: homonimo vigente (AC-13).
        db.add(producto_homonimo)
        db.flush()

        sede_ajena = Sede(
            nombre="Sede Ajeno",
            direccion="Bodega Sur - H1",
            institucion_id="INST02",
        )
        db.add(sede_ajena)
        db.flush()

        stock_homonimo = StockSede(
            stock_actual=5,
            sede_id=sede_ajena.sede_id,
            producto_id=producto_homonimo.producto_id,
            institucion_id="INST02",
        )
        db.add(stock_homonimo)
        db.commit()

        return {
            **datos_base,
            "inst_propia": "INST01",
            "inst_ajena": "INST02",
            "departamento_ajeno_id": departamento_ajeno.departamento_id,
            "categoria_homonima_ajena_id": categoria_homonima.categoria_id,
            "producto_homonimo_ajeno_id": producto_homonimo.producto_id,
            "sede_ajena_id": sede_ajena.sede_id,
            "stock_homonimo_ajeno_id": stock_homonimo.stock_sede_id,
            "stock_homonimo_ajeno": 5,
            "usuarios_inst01": usuarios_inst01,
            "usuarios_inst02": usuarios_inst02,
        }
    finally:
        db.close()
