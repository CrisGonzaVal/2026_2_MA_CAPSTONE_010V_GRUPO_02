"""T13 (Feature 028): pool y cierre de sesion del canal SSE - gated.

AC-29 (sin retencion del pool) y AC-1/AC-2 (apertura del canal con una identidad
de tenant sobre PostgreSQL real). SQLite no acredita el corte entre `control` y
los esquemas tenant, asi que este modulo corre contra PostgreSQL 16 real:

  * **Cinco flujos ociosos** abiertos al endpoint con un motor de pool diminuto
    (`pool_size=2`, `max_overflow=0`, `pool_timeout=2`): cada `listo` deja
    `pool.checkedout() == 0` y la actividad de PostgreSQL acotada al pool. Con
    los cinco abiertos, `GET /api/v1/tickets/` responde **200** y no aparece
    `QueuePool limit`.
  * **Apertura con identidad de tenant**: `GET /api/v1/eventos/` responde
    **200**, entrega `listo` y no retiene la sesion de `get_db`. La institucion
    se resuelve por el mapa de control (`tenant_service`), no leyendo
    `control.departamento` (correccion T13 del 28/Nov/2026).
  * **Denegacion en cerrado**: institucion inactiva -> **401**; correo sin
    asignacion activa -> **403**.

El `TestClient` de Starlette 1.7 bufferiza el cuerpo hasta cerrar el generador y
no sirve para mantener flujos abiertos; `httpx.ASGITransport` tambien bufferiza.
El modulo levanta un `uvicorn.Server` real en un puerto efimero y lee los frames
con `httpx.Client.stream`.

COMO ACTIVARLO
    docker compose -f docker-compose.yml up -d db
    $env:POSTGRES_TEST_URL = "postgresql://postgres:postgres@localhost:5433/postgres"
    cd backend; python -m pytest tests/funcional/sistema/test_pool_tiempo_real_028.py

Sin `POSTGRES_TEST_URL` el modulo se **salta**. La URL apunta a una base de
mantenimiento donde el modulo crea y DESTRUYE una base temporal propia
(`compustock_t13_*`); nunca toca `apt_erp`. No se anade ninguna dependencia:
`psycopg2`, `uvicorn` y `httpx` ya estan declarados.
"""

from __future__ import annotations

import asyncio
import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import pytest

try:  # `psycopg2` es dependencia declarada; el guard evita un error de coleccion.
    import psycopg2

    _PSYCOPG2_DISPONIBLE = True
except ImportError:  # pragma: no cover - entorno sin la dependencia
    _PSYCOPG2_DISPONIBLE = False

import httpx
import uvicorn
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import joinedload

from app.api import dependencies
from app.core import eventos as bus_eventos
from app.core.config import settings
from app.db.database import crear_sesion_control, crear_sesion_esquema
from app.main import app
from app.models import Rol, Usuario
from app.models.control_canonico import InstitucionControl
from app.services import tenant_service
from app.services.auth_service import IdentidadAutenticada

_POSTGRES_TEST_URL = os.environ.get("POSTGRES_TEST_URL")

pytestmark = pytest.mark.skipif(
    not _POSTGRES_TEST_URL or not _PSYCOPG2_DISPONIBLE,
    reason=(
        "Requiere PostgreSQL 16 real: exporta POSTGRES_TEST_URL="
        "postgresql://postgres:postgres@localhost:5433/postgres y levanta el "
        "contenedor `db` (docker compose up -d db)."
    ),
)

RAIZ = Path(__file__).resolve().parents[4]
ESQUEMA_SQL = RAIZ / "database" / "01_esquema.sql"
SEMILLA_SQL = RAIZ / "database" / "02_datos_semilla.sql"

#: Institucion y Administrador sembrados por la QA de INST-001.
_INSTITUCION = "INST-001"
_CORREO_ADMINISTRADOR = "admin020.test+clerk_test@example.com"

#: `application_name` del motor temporal: acota `pg_stat_activity` a esta prueba.
_APP = "compustock_t13_pool"

#: Pool diminuto: dos conexiones bastan para una peticion de negocio
#: (control + tenant) y no dejan margen para una sesion SSE retenida.
_TAMANO_POOL = 2
_FLUJOS = 5

#: Centinela para distinguir un override ausente de uno instalado.
_SIN_OVERRIDE = object()


# ---------------------------------------------------------------------------
# Base temporal y utilidades
# ---------------------------------------------------------------------------


def _sin_driver(url: str) -> str:
    return url.replace("postgresql+psycopg2://", "postgresql://")


def _url_con_base(url: str, nombre: str) -> str:
    partes = urlsplit(url)
    return urlunsplit((partes.scheme, partes.netloc, "/" + nombre, "", ""))


@contextmanager
def _base_temporal():
    """Crea una base PostgreSQL efimera y la destruye al salir (nunca `apt_erp`)."""
    dsn = _sin_driver(_POSTGRES_TEST_URL or "")
    assert "/apt_erp" not in dsn, "POSTGRES_TEST_URL apunta a `apt_erp`"
    admin = psycopg2.connect(dsn)
    admin.autocommit = True
    nombre = f"compustock_t13_{uuid4().hex[:12]}"
    with admin.cursor() as cur:
        cur.execute(f'CREATE DATABASE "{nombre}"')
    try:
        conexion = psycopg2.connect(_url_con_base(dsn, nombre))
        try:
            yield conexion, nombre
        finally:
            conexion.close()
    finally:
        with admin.cursor() as cur:
            cur.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (nombre,),
            )
            cur.execute(f'DROP DATABASE IF EXISTS "{nombre}"')
        admin.close()


def _instalar(conexion) -> None:
    """Carga el DDL y la semilla QA en la base temporal."""
    for ruta in (ESQUEMA_SQL, SEMILLA_SQL):
        with conexion.cursor() as cur:
            cur.execute(ruta.read_text(encoding="utf-8"))
        conexion.commit()


def _motor_de(conexion):
    """Motor temporal con pool diminuto y nombre de aplicacion propio."""
    nombre = conexion.get_dsn_parameters()["dbname"]
    url = _url_con_base(_sin_driver(_POSTGRES_TEST_URL or ""), nombre)
    url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return create_engine(
        url,
        pool_size=_TAMANO_POOL,
        max_overflow=0,
        pool_timeout=2,
        future=True,
        connect_args={"application_name": _APP},
    )


def _identidad_de_administrador(motor) -> IdentidadAutenticada:
    """Identidad suelta del Administrador sembrado, con ids reales del tenant."""
    esquema = tenant_service.nombre_esquema_para_institucion(_INSTITUCION)
    sesion = crear_sesion_esquema(esquema, motor=motor)
    try:
        usuario = sesion.execute(
            select(Usuario)
            .options(joinedload(Usuario.rol))
            .where(Usuario.correo == _CORREO_ADMINISTRADOR)
        ).scalar_one()
        sesion.expunge(usuario)
        datos = (
            usuario.usuario_id,
            usuario.nombre,
            usuario.apellido,
            usuario.correo,
            usuario.departamento_id,
            usuario.rol_id,
            usuario.rol.nombre_rol,
        )
    finally:
        sesion.close()

    fantasma = Usuario(
        usuario_id=datos[0],
        nombre=datos[1],
        apellido=datos[2],
        correo=datos[3],
        departamento_id=datos[4],
        rol_id=datos[5],
    )
    fantasma.rol = Rol(nombre_rol=datos[6])
    return IdentidadAutenticada(
        usuario=fantasma,
        sub=f"t13-{_CORREO_ADMINISTRADOR}",
        expira_en=int(time.time()) + 120,
    )


def _identidad_no_mapeada(identidad: IdentidadAutenticada) -> IdentidadAutenticada:
    """Misma identidad con un correo sin fila activa en el mapa de control."""
    fantasma = Usuario(
        usuario_id=identidad.usuario.usuario_id,
        nombre="Sin",
        apellido="Mapa",
        correo="sin.mapa.t13@example.com",
        departamento_id=identidad.usuario.departamento_id,
        rol_id=identidad.usuario.rol_id,
    )
    fantasma.rol = Rol(nombre_rol=identidad.usuario.rol.nombre_rol)
    return IdentidadAutenticada(
        usuario=fantasma, sub="t13-sin-mapa", expira_en=identidad.expira_en
    )


def _cambiar_estado_institucion(motor, activo: bool) -> None:
    sesion = crear_sesion_control(motor)
    try:
        sesion.execute(
            update(InstitucionControl)
            .where(InstitucionControl.institucion_id == _INSTITUCION)
            .values(activo=activo)
        )
        sesion.commit()
    finally:
        sesion.close()


def _conexiones_de_la_app(conexion) -> int:
    """Conexiones del motor de la prueba visibles en `pg_stat_activity`."""
    with conexion.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM pg_stat_activity "
            "WHERE datname = current_database() AND application_name = %s",
            (_APP,),
        )
        return cur.fetchone()[0]


def _esperar_checkedout(motor, esperado: int, plazo: float = 3.0) -> bool:
    """Espera acotada a que el pool quede en el valor esperado."""
    limite = time.monotonic() + plazo
    while time.monotonic() < limite:
        if motor.pool.checkedout() == esperado:
            return True
        time.sleep(0.02)
    return motor.pool.checkedout() == esperado


# ---------------------------------------------------------------------------
# Bus lento falso y servidor real
# ---------------------------------------------------------------------------


class _SuscripcionLenta:
    """Suscripcion que no entrega sobres y cede el turno (evita un bucle activo)."""

    async def recibir(self, timeout: float | None = None):
        await asyncio.sleep(min(0.25, timeout or 0.25))
        return None

    async def cerrar(self) -> None:
        return None


class _BusLento:
    """Bus de la prueba: mantener los flujos abiertos y ociosos, sin Redis."""

    def publicar(self, sobre) -> None:
        return None

    async def suscribir(self, canal: str):
        return _SuscripcionLenta()

    async def cerrar(self) -> None:
        return None


@contextmanager
def _servidor():
    """`uvicorn.Server` real en un hilo, con puerto efimero y cierre acotado."""
    configuracion = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=0,
        log_level="warning",
        access_log=False,
        lifespan="on",
        timeout_graceful_shutdown=5,
    )
    servidor = uvicorn.Server(configuracion)
    hilo = threading.Thread(target=servidor.run, daemon=True)
    hilo.start()
    limite = time.time() + 20
    while not servidor.started and hilo.is_alive() and time.time() < limite:
        time.sleep(0.05)
    if not servidor.started:
        servidor.should_exit = True
        raise RuntimeError("uvicorn no arranco en el puerto efimero")
    try:
        puerto = servidor.servers[0].sockets[0].getsockname()[1]
        yield f"http://127.0.0.1:{puerto}"
    finally:
        servidor.should_exit = True
        hilo.join(timeout=15)
        if hilo.is_alive():
            servidor.force_exit = True
            hilo.join(timeout=5)


# ---------------------------------------------------------------------------
# Fixture: base + motor + overrides + servidor
# ---------------------------------------------------------------------------


@contextmanager
def _registrar_override(previos: dict, clave, valor) -> None:
    previos[clave] = app.dependency_overrides.get(clave, _SIN_OVERRIDE)
    app.dependency_overrides[clave] = valor


def _restaurar_overrides(previos: dict) -> None:
    for clave, valor in previos.items():
        if valor is _SIN_OVERRIDE:
            app.dependency_overrides.pop(clave, None)
        else:
            app.dependency_overrides[clave] = valor


@pytest.fixture
def entorno_t13():
    """Base temporal instalada, motor diminuto, bus lento y uvicorn real."""
    with _base_temporal() as (conexion, _nombre):
        _instalar(conexion)
        motor = _motor_de(conexion)
        contenedor = {"actual": _identidad_de_administrador(motor)}

        def obtener_db_de_prueba():
            db = crear_sesion_control(motor)
            try:
                yield db
            finally:
                db.close()

        previos: dict = {}
        _registrar_override(previos, dependencies.get_db, obtener_db_de_prueba)
        _registrar_override(
            previos,
            dependencies.get_current_user,
            lambda: contenedor["actual"],
        )

        habilitado_previo = settings.TIEMPO_REAL_HABILITADO
        latido_previo = settings.TIEMPO_REAL_LATIDO_SEGUNDOS
        vida_previo = settings.VIDA_MAXIMA_CONEXION_SEGUNDOS
        settings.TIEMPO_REAL_HABILITADO = True
        settings.TIEMPO_REAL_LATIDO_SEGUNDOS = 1
        settings.VIDA_MAXIMA_CONEXION_SEGUNDOS = 30
        bus_eventos.configurar_almacen(_BusLento())

        cliente_negocio = httpx.Client(
            timeout=httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0)
        )
        cliente_sse = httpx.Client(
            timeout=httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0)
        )
        flujos: list = []
        try:
            with _servidor() as base:
                cliente_negocio.base_url = base
                cliente_sse.base_url = base
                try:
                    yield {
                        "conexion": conexion,
                        "motor": motor,
                        "identidades": contenedor,
                        "cliente_negocio": cliente_negocio,
                        "cliente_sse": cliente_sse,
                        "flujos": flujos,
                    }
                finally:
                    # Los flujos se cierran antes de apagar uvicorn para que el
                    # apagado no espere conexiones abiertas.
                    for contexto in flujos:
                        try:
                            contexto.__exit__(None, None, None)
                        except Exception:  # noqa: BLE001 - limpieza best-effort
                            pass
                    flujos.clear()
        finally:
            cliente_sse.close()
            cliente_negocio.close()
            settings.TIEMPO_REAL_HABILITADO = habilitado_previo
            settings.TIEMPO_REAL_LATIDO_SEGUNDOS = latido_previo
            settings.VIDA_MAXIMA_CONEXION_SEGUNDOS = vida_previo
            bus_eventos.configurar_almacen(bus_eventos.AlmacenNulo())
            _restaurar_overrides(previos)
            motor.dispose()


# ---------------------------------------------------------------------------
# Apertura y cierre de flujos
# ---------------------------------------------------------------------------


def _abrir_flujo(entorno: dict) -> tuple[list[str], int, bytes]:
    """Abre un flujo SSE y lee el primer frame completo (`listo`)."""
    contexto = entorno["cliente_sse"].stream(
        "GET", "/api/v1/eventos/", headers={"Authorization": "Bearer t13"}
    )
    respuesta = contexto.__enter__()
    if respuesta.status_code != 200:
        cuerpo = respuesta.read()
        contexto.__exit__(None, None, None)
        return [], respuesta.status_code, cuerpo

    lineas: list[str] = []
    for linea in respuesta.iter_lines():
        lineas.append(linea)
        if linea == "" and any(parte.startswith("event:") for parte in lineas):
            break
    entorno["flujos"].append(contexto)
    return lineas, respuesta.status_code, b""


def _cerrar_flujos(entorno: dict) -> None:
    for contexto in entorno["flujos"]:
        contexto.__exit__(None, None, None)
    entorno["flujos"].clear()


# ---------------------------------------------------------------------------
# AC-29: pool y cierre de sesion
# ---------------------------------------------------------------------------


def test_cinco_flujos_ociosos_no_agotan_el_pool_ac_29(entorno_t13):
    motor = entorno_t13["motor"]

    for indice in range(_FLUJOS):
        lineas, estado, cuerpo = _abrir_flujo(entorno_t13)
        assert estado == 200, cuerpo
        assert lineas[0] == "event: listo", lineas
        assert lineas[1].startswith("data: "), lineas
        assert "pedidos" in lineas[1], lineas
        assert _esperar_checkedout(motor, 0), (
            f"tras abrir el flujo {indice + 1} el pool retiene "
            f"{motor.pool.checkedout()} conexion(es)"
        )

    assert len(entorno_t13["flujos"]) == _FLUJOS
    assert _conexiones_de_la_app(entorno_t13["conexion"]) <= _TAMANO_POOL, (
        "el pool abrio mas conexiones que su tamano con los flujos ociosos"
    )

    respuesta = entorno_t13["cliente_negocio"].get(
        "/api/v1/tickets/", headers={"Authorization": "Bearer t13"}
    )
    assert respuesta.status_code == 200, respuesta.text
    assert "QueuePool limit" not in respuesta.text
    assert isinstance(respuesta.json(), list)
    assert _esperar_checkedout(motor, 0), (
        "la peticion de negocio dejo una conexion retenida"
    )

    _cerrar_flujos(entorno_t13)
    assert _esperar_checkedout(motor, 0)
    assert _conexiones_de_la_app(entorno_t13["conexion"]) <= _TAMANO_POOL


# ---------------------------------------------------------------------------
# AC-1/AC-2: apertura y denegacion en cerrado sobre PostgreSQL real
# ---------------------------------------------------------------------------


def test_eventos_abre_para_identidad_de_tenant_postgres_ac_1(entorno_t13):
    """El canal debe abrir con la institucion resuelta desde el mapa de control."""
    lineas, estado, cuerpo = _abrir_flujo(entorno_t13)

    assert estado == 200, cuerpo
    assert lineas[0] == "event: listo", lineas
    assert "pedidos" in lineas[1], lineas
    assert _esperar_checkedout(entorno_t13["motor"], 0), (
        "el flujo retuvo la sesion de `get_db`"
    )

    _cerrar_flujos(entorno_t13)
    assert _esperar_checkedout(entorno_t13["motor"], 0)


def test_institucion_inactiva_deniega_401_ac_2(entorno_t13):
    _cambiar_estado_institucion(entorno_t13["motor"], False)
    try:
        respuesta = entorno_t13["cliente_negocio"].get(
            "/api/v1/eventos/", headers={"Authorization": "Bearer t13"}
        )
    finally:
        _cambiar_estado_institucion(entorno_t13["motor"], True)

    assert respuesta.status_code == 401, respuesta.text
    assert respuesta.headers["content-type"].startswith("application/json")


def test_correo_no_mapeado_deniega_403_ac_2(entorno_t13):
    original = entorno_t13["identidades"]["actual"]
    entorno_t13["identidades"]["actual"] = _identidad_no_mapeada(original)
    try:
        respuesta = entorno_t13["cliente_negocio"].get(
            "/api/v1/eventos/", headers={"Authorization": "Bearer t13"}
        )
    finally:
        entorno_t13["identidades"]["actual"] = original

    assert respuesta.status_code == 403, respuesta.text
    assert respuesta.headers["content-type"].startswith("application/json")
