"""E12-A3 (enmienda 012): concurrencia de «Suministros» en PostgreSQL 16 - gated.

SQLite serializa las escrituras y no acredita la carrera de D-9; aqui se ejerce
contra PostgreSQL 16 real, con una base temporal desechable (nunca `apt_erp`):

* **AC-22** - dos altas concurrentes de usuarios **Bodeguero distintos** en una
  institucion sin «Suministros»: ambas responden **201**, queda **una sola** fila
  «Suministros», ambos usuarios apuntan a ella y ninguna peticion responde 500.
  La barrera se coloca **despues del pre-check** de cada peticion para que ambas
  transacciones vean la institucion sin la fila antes de insertar: la perdedora
  choca con la unicidad, el savepoint revierte y relee la fila ganadora (D-9).
  `Barrier` no fija el orden del lock ni el ganador.
* **D-8/D-9** - reutilizacion concurrente de una fila activa sin duplicarla ni
  modificar nombre/descripcion/sede, y reactivacion concurrente idempotente de
  una fila inactiva.
* **D-8** - un fallo local posterior a la resolucion no confirma «Suministros»:
  el rollback del servicio descarta la fila junto con el usuario fallido.

COMO ACTIVARLA
    docker compose -f docker-compose.yml up -d db
    $env:POSTGRES_TEST_URL = "postgresql://postgres:postgres@localhost:5433/postgres"
    cd backend; python -m pytest tests/funcional/sistema/test_suministros_postgres_012.py

Sin `POSTGRES_TEST_URL` los tests se **saltan**. La URL apunta a una base de
mantenimiento donde el modulo crea y DESTRUYE bases temporales propias; nunca
toca `apt_erp`. No se anade ninguna dependencia: `psycopg2` ya esta declarado.
"""

from __future__ import annotations

import os
import threading
from contextlib import contextmanager
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import pytest

try:  # `psycopg2` es dependencia declarada; el guard evita un error de coleccion.
    import psycopg2  # noqa: F401

    _PSYCOPG2_DISPONIBLE = True
except ImportError:  # pragma: no cover - entorno sin la dependencia
    _PSYCOPG2_DISPONIBLE = False

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import CreateSchema

from app.api import dependencies
from app.core import security
from app.core.config import VERSION_ESQUEMA_OBJETIVO
from app.db.database import (
    Base,
    ESQUEMA_CONTROL,
    crear_sesion_control,
    crear_sesion_esquema,
)
from app.main import app
from app.models import (
    BaseControl,
    Departamento,
    Rol,
    Sede,
    Usuario,
    VersionEsquema,
)
from app.schemas.control_schema import InstitucionAltaControlCrear
from app.schemas.usuario_schema import UsuarioCrear
from app.services import control_service, usuario_service
from app.services.auth_service import IdentidadAutenticada
from app.services.departamento_suministros import (
    DESCRIPCION_SUMINISTROS,
    NOMBRE_SUMINISTROS,
    es_nombre_suministros,
)
from app.services.tenant_service import nombre_esquema_para_institucion

_POSTGRES_TEST_URL = os.environ.get("POSTGRES_TEST_URL")

pytestmark = pytest.mark.skipif(
    not _POSTGRES_TEST_URL or not _PSYCOPG2_DISPONIBLE,
    reason=(
        "Requiere PostgreSQL 16 real: exporta POSTGRES_TEST_URL="
        "postgresql://postgres:postgres@localhost:5433/postgres y levanta el "
        "contenedor `db` (docker compose up -d db)."
    ),
)

_INSTITUCION = "INST-012SUM"
_CORREO_ADMIN = "admin.suministros.012@compustock.cl"
_CORREO_UNO = "bodeguero.concurrente.uno@compustock.cl"
_CORREO_DOS = "bodeguero.concurrente.dos@compustock.cl"
_CORREO_FALLO = "bodeguero.fallo.local@compustock.cl"

RUTA_USUARIOS = "/api/v1/usuarios/"

#: Correos normalizados por `security.normalizar_correo`.
_CORREOS_CONCURRENTES = (_CORREO_UNO, _CORREO_DOS)


# ---------------------------------------------------------------------------
# Base temporal y utilidades
# ---------------------------------------------------------------------------


def _url_sqlalchemy(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg2://", 1)
    return url


@contextmanager
def _base_temporal():
    """Crea una base PostgreSQL efimera y la destruye al salir (nunca `apt_erp`)."""
    dsn = (_POSTGRES_TEST_URL or "").replace("postgresql+psycopg2://", "postgresql://")
    admin = psycopg2.connect(dsn)
    admin.autocommit = True
    nombre = f"compustock_012sum_{uuid4().hex[:12]}"
    with admin.cursor() as cur:
        cur.execute(f'CREATE DATABASE "{nombre}"')
    partes = urlsplit(dsn)
    url = urlunsplit((partes.scheme, partes.netloc, "/" + nombre, "", ""))
    try:
        yield url
    finally:
        with admin.cursor() as cur:
            cur.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (nombre,),
            )
            cur.execute(f'DROP DATABASE IF EXISTS "{nombre}"')
        admin.close()


@contextmanager
def _sesion_tenant(motor, esquema: str):
    sesion = crear_sesion_esquema(esquema, motor=motor)
    try:
        yield sesion
    finally:
        sesion.close()


@contextmanager
def _mundo_suministros():
    """Control + un tenant aprovisionado por el flujo real, sin «Suministros»."""
    with _base_temporal() as url:
        motor = create_engine(_url_sqlalchemy(url), future=True)
        try:
            with motor.begin() as conexion:
                conexion.execute(CreateSchema(ESQUEMA_CONTROL))
            motor_control = motor.execution_options(
                schema_translate_map={None: ESQUEMA_CONTROL}
            )
            # El canonico (con `activo`) y `funcion_institucion` viven solo en
            # control; se crean primero para que `institucion` sea superset.
            BaseControl.metadata.create_all(bind=motor_control)
            Base.metadata.create_all(bind=motor_control)

            datos = InstitucionAltaControlCrear(
                institucion_id=_INSTITUCION,
                nombre="Instituto Suministros 012",
                correo_administrador=_CORREO_ADMIN,
                nombre_administrador="Ada",
                apellido_administrador="Suministros",
                departamento_nombre_administrativo="Administracion",
            )
            sesion_control = crear_sesion_control(motor)
            try:
                # El control vigente porta su version objetivo (DDL 01 la siembra);
                # la resolucion de contexto la lee de aqui.
                sesion_control.add(VersionEsquema(version=VERSION_ESQUEMA_OBJETIVO))
                sesion_control.flush()
                control_service.aprovisionar_institucion(
                    sesion_control, datos, lambda _correo: True
                )
            finally:
                sesion_control.close()

            esquema = nombre_esquema_para_institucion(_INSTITUCION)
            yield {
                "engine": motor,
                "motor_control": motor_control,
                "esquema": esquema,
                "identidad": _identidad_de_tenant(motor, esquema),
            }
        finally:
            motor.dispose()


def _identidad_de_tenant(motor, esquema: str) -> IdentidadAutenticada:
    """Identidad del Administrador aprovisionado, sin depender de la sesion abierta."""
    sesion = crear_sesion_esquema(esquema, motor=motor)
    try:
        usuario = sesion.execute(
            select(Usuario).where(Usuario.correo == _CORREO_ADMIN)
        ).scalar_one()
        usuario_id = usuario.usuario_id
        departamento_id = usuario.departamento_id
        rol_nombre = usuario.rol.nombre_rol
    finally:
        sesion.close()
    fantasma = Usuario(
        usuario_id=usuario_id,
        nombre="Admin",
        apellido="Suministros",
        correo=_CORREO_ADMIN,
        departamento_id=departamento_id,
        rol_id=1,
    )
    fantasma.rol = Rol(nombre_rol=rol_nombre)
    return IdentidadAutenticada(usuario=fantasma, sub="sub-012-suministros")


@pytest.fixture
def mundo_suministros():
    with _mundo_suministros() as mundo:
        yield mundo


def _rol_id(motor, esquema: str, nombre_rol: str) -> int:
    with _sesion_tenant(motor, esquema) as db:
        return db.execute(
            select(Rol.rol_id).where(Rol.nombre_rol == nombre_rol)
        ).scalar_one()


def _sede_central_id(motor, esquema: str) -> int:
    with _sesion_tenant(motor, esquema) as db:
        return db.execute(
            select(Sede.sede_id).order_by(Sede.sede_id).limit(1)
        ).scalar_one()


def _crear_suministros(
    motor,
    esquema: str,
    *,
    activo: bool,
    nombre_dep: str = NOMBRE_SUMINISTROS,
    descripcion: str = "Fila preexistente de prueba",
    sede_id: int | None = None,
) -> int:
    with _sesion_tenant(motor, esquema) as db:
        fila = Departamento(
            nombre_dep=nombre_dep,
            descripcion=descripcion,
            institucion_id=_INSTITUCION,
            sede_id=sede_id,
            activo=activo,
        )
        db.add(fila)
        db.commit()
        db.refresh(fila)
        return fila.departamento_id


def _filas_suministros(motor, esquema: str) -> list[dict]:
    """Filas de la institucion cuyo nombre normalizado es «Suministros»."""
    with _sesion_tenant(motor, esquema) as db:
        filas = db.execute(
            select(Departamento).where(
                Departamento.institucion_id == _INSTITUCION,
                func.lower(func.trim(Departamento.nombre_dep))
                == NOMBRE_SUMINISTROS.lower(),
            )
        ).scalars().all()
        consultadas = [
            {
                "departamento_id": fila.departamento_id,
                "nombre_dep": fila.nombre_dep,
                "descripcion": fila.descripcion,
                "sede_id": fila.sede_id,
                "activo": fila.activo,
            }
            for fila in filas
        ]
    assert all(
        es_nombre_suministros(fila["nombre_dep"]) for fila in consultadas
    ), consultadas
    return consultadas


def _usuarios_por_correo(motor, esquema: str, correos) -> dict[str, int]:
    with _sesion_tenant(motor, esquema) as db:
        usuarios = db.execute(
            select(Usuario).where(Usuario.correo.in_(tuple(correos)))
        ).scalars().all()
        return {usuario.correo: usuario.departamento_id for usuario in usuarios}


def _usuarios_en_departamento(motor, esquema: str, departamento_id: int) -> int:
    with _sesion_tenant(motor, esquema) as db:
        return db.execute(
            select(func.count())
            .select_from(Usuario)
            .where(Usuario.departamento_id == departamento_id)
        ).scalar_one()


# ---------------------------------------------------------------------------
# Cliente HTTP concurrente
# ---------------------------------------------------------------------------


def _consultor_identidad_existente():
    """Seam Clerk: el correo ya es una identidad verificada (sin invitacion)."""

    def _consultar(_correo: str) -> security.EstadoIdentidadClerk:
        return security.EstadoIdentidadClerk(
            identidad_existente=True,
            invitacion_pendiente=False,
            invitacion_id=None,
        )

    return _consultar


def _verificador_existente():
    return lambda _correo: True


@contextmanager
def _dos_clientes(mundo):
    """Dos `TestClient` reales sobre el mismo app y la base temporal."""
    Fabrica = sessionmaker(bind=mundo["motor_control"])

    def _db_de_prueba():
        db = Fabrica()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[dependencies.get_db] = _db_de_prueba
    app.dependency_overrides[dependencies.get_current_user] = (
        lambda: mundo["identidad"]
    )
    app.dependency_overrides[dependencies.obtener_consultor_identidad_clerk] = (
        _consultor_identidad_existente
    )
    app.dependency_overrides[dependencies.obtener_verificador_correo_clerk] = (
        _verificador_existente
    )
    try:
        with TestClient(app, raise_server_exceptions=False) as primera, TestClient(
            app, raise_server_exceptions=False
        ) as segunda:
            yield primera, segunda
    finally:
        app.dependency_overrides.clear()


def _alta(correo: str, rol_id: int) -> dict:
    """Alta de Bodeguero sin `departamento_id` (D-12): lo resuelve el servidor."""
    return {
        "nombre": "Bodeguero",
        "apellido": "Concurrente",
        "correo": correo,
        "rol_id": rol_id,
    }


def _correr_en_paralelo(primera, segunda) -> dict[str, tuple[int | str, str]]:
    """Arranca dos peticiones a la vez con una barrera y devuelve sus resultados."""
    barrera = threading.Barrier(2)
    resultados: dict[str, tuple[int | str, str]] = {}
    candado = threading.Lock()

    def _ejecutar(nombre: str, tarea) -> None:
        try:
            barrera.wait(timeout=15)
            respuesta = tarea()
            resultado: tuple[int | str, str] = (
                respuesta.status_code,
                respuesta.text,
            )
        except Exception as exc:  # pragma: no cover - diagnostico de carrera
            resultado = (f"error:{type(exc).__name__}:{exc}", "")
        with candado:
            resultados[nombre] = resultado

    hilos = [
        threading.Thread(target=_ejecutar, args=("primera", primera)),
        threading.Thread(target=_ejecutar, args=("segunda", segunda)),
    ]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join(timeout=30)

    assert not any(hilo.is_alive() for hilo in hilos), (
        "una carrera quedo colgada: posible deadlock o bloqueo sin liberar"
    )
    assert set(resultados) == {"primera", "segunda"}, resultados
    return resultados


def _sincronizar_precheck(monkeypatch) -> None:
    """Fuerza que ambas peticiones vean el estado inicial antes de escribir.

    La barrera se coloca **despues** de la primera busqueda de cada peticion y
    antes de su `INSERT`/`UPDATE`: garantiza que las dos transacciones parten del
    mismo estado (sin fila, fila activa o fila inactiva) sin fijar cual gana el
    lock de unicidad (D-9). Sin esta sincronizacion, una peticion podria
    completar y confirmar antes de que la otra empiece, y la carrera no se
    ejerceria.
    """
    import app.services.departamento_suministros as modulo

    original = modulo._buscar_departamento_suministros
    barrera = threading.Barrier(2)
    estado = threading.local()

    def _buscar(db, institucion_id):
        fila = original(db, institucion_id)
        if not getattr(estado, "sincronizado", False):
            estado.sincronizado = True
            barrera.wait(timeout=15)
        return fila

    monkeypatch.setattr(modulo, "_buscar_departamento_suministros", _buscar)


# ---------------------------------------------------------------------------
# AC-22: dos altas concurrentes -> dos 201 y una sola fila
# ---------------------------------------------------------------------------


def test_dos_altas_concurrentes_responden_201_y_comparten_una_sola_fila(
    mundo_suministros, monkeypatch
):
    """AC-22/D-9: la perdedora relee y reutiliza; nadie responde 500 ni queda huerfano."""
    _sincronizar_precheck(monkeypatch)
    motor = mundo_suministros["engine"]
    esquema = mundo_suministros["esquema"]
    rol_id = _rol_id(motor, esquema, "Bodeguero")

    assert _filas_suministros(motor, esquema) == []

    with _dos_clientes(mundo_suministros) as (primera, segunda):
        resultados = _correr_en_paralelo(
            lambda: primera.post(
                RUTA_USUARIOS, json=_alta(_CORREO_UNO, rol_id)
            ),
            lambda: segunda.post(
                RUTA_USUARIOS, json=_alta(_CORREO_DOS, rol_id)
            ),
        )

    assert resultados["primera"][0] == 201, resultados
    assert resultados["segunda"][0] == 201, resultados

    filas = _filas_suministros(motor, esquema)
    assert len(filas) == 1, filas
    fila = filas[0]
    assert fila["nombre_dep"] == NOMBRE_SUMINISTROS
    assert fila["descripcion"] == DESCRIPCION_SUMINISTROS
    assert fila["sede_id"] is None
    assert fila["activo"] is True

    usuarios = _usuarios_por_correo(motor, esquema, _CORREOS_CONCURRENTES)
    assert set(usuarios) == set(_CORREOS_CONCURRENTES), usuarios
    assert all(
        departamento_id == fila["departamento_id"]
        for departamento_id in usuarios.values()
    ), usuarios
    assert _usuarios_en_departamento(
        motor, esquema, fila["departamento_id"]
    ) == 2


def test_reutilizacion_concurrente_no_duplica_ni_modifica_la_fila(
    mundo_suministros, monkeypatch
):
    """D-8/D-9: una fila activa se reutiliza tal cual, aunque el nombre varie en caja."""
    _sincronizar_precheck(monkeypatch)
    motor = mundo_suministros["engine"]
    esquema = mundo_suministros["esquema"]
    rol_id = _rol_id(motor, esquema, "Bodeguero")
    sede_id = _sede_central_id(motor, esquema)
    existente_id = _crear_suministros(
        motor,
        esquema,
        activo=True,
        nombre_dep=" SUMINISTROS ",
        descripcion="Fila preexistente sin tocar",
        sede_id=sede_id,
    )

    with _dos_clientes(mundo_suministros) as (primera, segunda):
        resultados = _correr_en_paralelo(
            lambda: primera.post(
                RUTA_USUARIOS, json=_alta(_CORREO_UNO, rol_id)
            ),
            lambda: segunda.post(
                RUTA_USUARIOS, json=_alta(_CORREO_DOS, rol_id)
            ),
        )

    assert resultados["primera"][0] == 201, resultados
    assert resultados["segunda"][0] == 201, resultados

    filas = _filas_suministros(motor, esquema)
    assert len(filas) == 1, filas
    fila = filas[0]
    assert fila["departamento_id"] == existente_id
    assert fila["nombre_dep"] == " SUMINISTROS "
    assert fila["descripcion"] == "Fila preexistente sin tocar"
    assert fila["sede_id"] == sede_id
    assert fila["activo"] is True

    usuarios = _usuarios_por_correo(motor, esquema, _CORREOS_CONCURRENTES)
    assert set(usuarios) == set(_CORREOS_CONCURRENTES), usuarios
    assert all(
        departamento_id == existente_id for departamento_id in usuarios.values()
    ), usuarios


def test_reactivacion_concurrente_es_idempotente(mundo_suministros, monkeypatch):
    """D-8/D-9: dos reactivaciones simultaneas dejan la fila activa una sola vez."""
    _sincronizar_precheck(monkeypatch)
    motor = mundo_suministros["engine"]
    esquema = mundo_suministros["esquema"]
    rol_id = _rol_id(motor, esquema, "Bodeguero")
    existente_id = _crear_suministros(
        motor,
        esquema,
        activo=False,
        descripcion="Suministros inactivo",
    )
    assert _filas_suministros(motor, esquema)[0]["activo"] is False

    with _dos_clientes(mundo_suministros) as (primera, segunda):
        resultados = _correr_en_paralelo(
            lambda: primera.post(
                RUTA_USUARIOS, json=_alta(_CORREO_UNO, rol_id)
            ),
            lambda: segunda.post(
                RUTA_USUARIOS, json=_alta(_CORREO_DOS, rol_id)
            ),
        )

    assert resultados["primera"][0] == 201, resultados
    assert resultados["segunda"][0] == 201, resultados

    filas = _filas_suministros(motor, esquema)
    assert len(filas) == 1, filas
    fila = filas[0]
    assert fila["departamento_id"] == existente_id
    assert fila["activo"] is True

    usuarios = _usuarios_por_correo(motor, esquema, _CORREOS_CONCURRENTES)
    assert set(usuarios) == set(_CORREOS_CONCURRENTES), usuarios
    assert all(
        departamento_id == existente_id for departamento_id in usuarios.values()
    ), usuarios


# ---------------------------------------------------------------------------
# D-8: un fallo local posterior a la resolucion no confirma «Suministros»
# ---------------------------------------------------------------------------


def test_fallo_local_no_confirma_suministros(mundo_suministros, monkeypatch):
    """D-8: el rollback descarta «Suministros» junto con el usuario que no confirma."""
    motor = mundo_suministros["engine"]
    esquema = mundo_suministros["esquema"]
    rol_id = _rol_id(motor, esquema, "Bodeguero")

    def _fallar(_db, _usuario):
        raise RuntimeError("fallo simulado antes de confirmar el usuario")

    monkeypatch.setattr(usuario_service, "_confirmar_usuario_tenant", _fallar)

    db_tenant = crear_sesion_esquema(esquema, motor=motor)
    db_control = crear_sesion_control(motor)
    try:
        with pytest.raises(RuntimeError):
            usuario_service.crear_usuario(
                db_tenant,
                UsuarioCrear(
                    nombre="Fallo",
                    apellido="Local",
                    correo=_CORREO_FALLO,
                    rol_id=rol_id,
                ),
                mundo_suministros["identidad"],
                db_control=db_control,
                consultar_identidad=_consultor_identidad_existente(),
            )
    finally:
        db_tenant.close()
        db_control.close()

    assert _filas_suministros(motor, esquema) == []
    assert _usuarios_por_correo(motor, esquema, (_CORREO_FALLO,)) == {}
