"""T2 (Feature 012): institucion inactiva deniega (401) antes de tenant/version.

Seam bajo prueba: `app.services.tenant_service` y la dependencia
`app.api.dependencies.get_contexto_solicitud`. Una institucion inactiva
(`InstitucionControl.activo = False`) no resuelve identidad: la operacion tenant
deniega como identidad local no resoluble, **401**, incluso con la version del
tenant en el objetivo (D-2, diseno-tecnico.md §4).

Fase ROJA de TDD: `InstitucionControl.activo` y la consulta previa a la version
aun no existen (T3/T5); cada prueba falla por esa capacidad ausente o por la
ausencia del comportamiento esperado, nunca por importacion ni sintaxis.

Enmienda de la Feature 007 (26/Nov/2026, E26N-3, AC-26/AC-27): al final se fija
la precedencia del alta de tickets sobre la app real —401 sin sesion valida y,
con institucion inactiva, 403 de matriz para Administrador/Bodeguero y 401 del
contexto de tenant para el Solicitante— sin reordenar dependencias ni cambiar la
autenticacion.
"""

from __future__ import annotations

import importlib
import json
import time
from contextlib import contextmanager
from uuid import uuid4

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm
from sqlalchemy.orm import sessionmaker

from app.api import dependencies
from app.core.config import VERSION_ESQUEMA_OBJETIVO, settings
from app.main import app
from app.models import DetalleTicket, HistorialTransicionTicket, Ticket
from app.models.control import MapaUsuarioEsquema, VersionEsquema
from app.models.usuario import Usuario
from app.services import tenant_service
from app.services.auth_service import IdentidadAutenticada

from tests.funcional.integracion._soporte_sede_011 import contar_en

_VACIO = "capacidad ausente (T3/T5): {}".format


def _control_canonico():
    try:
        return importlib.import_module("app.models.control_canonico")
    except ImportError:
        pytest.fail(
            "capacidad ausente (T3): falta app.models.control_canonico "
            "(InstitucionControl.activo)."
        )


def _preparar(motor, *, activo: bool, con_version: bool = True) -> None:
    modulo = _control_canonico()
    base_control = getattr(modulo, "BaseControl", None)
    institucion_control = getattr(modulo, "InstitucionControl", None)
    if base_control is None or institucion_control is None:
        pytest.fail(_VACIO("BaseControl/InstitucionControl"))
    base_control.metadata.create_all(motor, checkfirst=True)

    db = sessionmaker(bind=motor)()
    try:
        db.add(
            institucion_control(
                institucion_id="INST01", nombre="Instituto Uno", activo=activo
            )
        )
        # El canonico de control y el mapa viven en `MetaData` distintos, asi que
        # el orden de INSERT no se infiere de la FK en el contexto logico unico de
        # SQLite: se fuerza con un `flush` para no disparar la FK del mapa.
        db.flush()
        db.add(
            MapaUsuarioEsquema(
                correo="u.inst01@compustock.cl",
                institucion_id="INST01",
                nombre_esquema="tenant_inst01",
                activo=True,
            )
        )
        if con_version:
            db.add(VersionEsquema(version=VERSION_ESQUEMA_OBJETIVO))
        db.commit()
    finally:
        db.close()


def _identidad(correo: str, rol: str = "Administrador") -> IdentidadAutenticada:
    from app.models.rol import Rol

    usuario = Usuario(
        usuario_id=1,
        nombre="Sonda",
        apellido="Inactiva",
        correo=correo,
        departamento_id=1,
        rol_id=1,
    )
    usuario.rol = Rol(nombre_rol=rol)
    return IdentidadAutenticada(usuario=usuario, sub="sub-012")


# ---------------------------------------------------------------------------
# Servicio: institucion inactiva no resuelve tenant
# ---------------------------------------------------------------------------


def test_institucion_inactiva_no_resuelve_tenant(motor):
    """AC-2: con version objetivo pero institucion inactiva, no hay resolucion."""
    _preparar(motor, activo=False)
    db = sessionmaker(bind=motor)()
    try:
        with pytest.raises(tenant_service.ErrorTenant):
            tenant_service.resolver_tenant_por_correo(db, "u.inst01@compustock.cl")
    finally:
        db.close()


def test_contexto_solicitud_deniega_institucion_inactiva(motor):
    _preparar(motor, activo=False)
    db = sessionmaker(bind=motor)()
    try:
        with pytest.raises(tenant_service.ErrorTenant):
            tenant_service.resolver_contexto_solicitud(db, "u.inst01@compustock.cl")
    finally:
        db.close()


def test_institucion_activa_resuelve_tenant(motor):
    """Control: una institucion activa y versionada si resuelve."""
    _preparar(motor, activo=True)
    db = sessionmaker(bind=motor)()
    try:
        resolucion = tenant_service.resolver_tenant_por_correo(
            db, "u.inst01@compustock.cl"
        )
        assert resolucion.nombre_esquema == "tenant_inst01"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# HTTP: 401 (identidad local no resoluble), no 403
# ---------------------------------------------------------------------------


def _cliente_probe(motor, correo: str, rol: str = "Administrador") -> TestClient:
    app_probe = FastAPI()

    @app_probe.get("/sonda")
    def sonda(_contexto: object = Depends(dependencies.get_contexto_solicitud)):
        return {"ok": True}

    def _db():
        sesion = sessionmaker(bind=motor)()
        try:
            yield sesion
        finally:
            sesion.close()

    app_probe.dependency_overrides[dependencies.get_db] = _db
    app_probe.dependency_overrides[dependencies.get_current_user] = (
        lambda: _identidad(correo, rol)
    )
    return TestClient(app_probe, raise_server_exceptions=False)


def test_http_institucion_inactiva_responde_401(motor):
    """AC-2/D-7: institucion inactiva -> 401 (no 403 ni 200)."""
    _preparar(motor, activo=False)
    cliente = _cliente_probe(motor, "u.inst01@compustock.cl")
    respuesta = cliente.get("/sonda")
    assert respuesta.status_code == 401, respuesta.text


def test_http_institucion_activa_responde_200(motor):
    _preparar(motor, activo=True)
    cliente = _cliente_probe(motor, "u.inst01@compustock.cl")
    respuesta = cliente.get("/sonda")
    assert respuesta.status_code == 200, respuesta.text


# ---------------------------------------------------------------------------
# Enmienda 007 (26/Nov/2026, AC-26/AC-27): sesion e institucion inactiva en el alta
# ---------------------------------------------------------------------------

#: Operacion de la enmienda: el alta de tickets reservada al Solicitante (D-11).
RUTA_ALTA = "/api/v1/tickets/"
#: Correo mapeado a `INST01` por `_preparar` (el unico mapa de control sembrado).
CORREO_MAPEADO = "u.inst01@compustock.cl"
#: Mensajes literales de la capa de dependencias (`dependencies.py`).
DETALLE_NO_AUTENTICADO = "No autenticado"
DETALLE_PERMISO_INSUFICIENTE = "Permiso insuficiente para la operacion"
DETALLE_IDENTIDAD_NO_RESUELVE = "La identidad no resuelve a una institucion activa"

#: Cuerpo **JSON parseable** con la forma del contrato del alta. No se valida:
#: AC-26/AC-27 se resuelven antes del payload, igual que el 403 de matriz de la
#: enmienda (D-13).
CUERPO_ALTA = {
    "prioridad_id": 1,
    "estado_id": 1,
    "asunto": "Requerimiento de sesion e institucion inactiva",
    "descripcion": "Cuerpo parseable de la enmienda del 26/Nov/2026 (AC-26/AC-27).",
    "detalles": [{"producto_id": 1, "cantidad_solicitada": 1}],
}

_SIN_OVERRIDE_PREVIO = object()


@contextmanager
def _cliente_app(motor, *, identidad=None, overrides=None, **opciones):
    """`TestClient` del `app` real con `get_db` en el motor de prueba.

    No usa el fixture `cliente` de `conftest`: ese inyecta una identidad de
    sesion y el 401 de AC-26 exige la frontera de autenticacion real. Los
    overrides instalados se guardan y se restauran (nunca
    `dependency_overrides.clear()`), de modo que un cliente anidado o previo
    conserva su estado.
    """

    Fabrica = sessionmaker(autocommit=False, autoflush=False, bind=motor)

    def _db_de_prueba():
        db = Fabrica()
        try:
            yield db
        finally:
            db.close()

    instalados = {dependencies.get_db: _db_de_prueba}
    if identidad is not None:
        identidad_fija = identidad
        instalados[dependencies.get_current_user] = lambda: identidad_fija
    if overrides:
        instalados.update(overrides)

    previos: dict = {}
    try:
        for clave, valor in instalados.items():
            previos[clave] = app.dependency_overrides.get(
                clave, _SIN_OVERRIDE_PREVIO
            )
            app.dependency_overrides[clave] = valor
        with TestClient(app, **opciones) as cliente_http:
            yield cliente_http
    finally:
        for clave, previo in previos.items():
            if previo is _SIN_OVERRIDE_PREVIO:
                app.dependency_overrides.pop(clave, None)
            else:
                app.dependency_overrides[clave] = previo


def _conteos_alta(motor) -> tuple[int, int, int]:
    """Filas de ticket, detalle e historial que una denegacion no puede tocar."""
    return (
        contar_en(motor, Ticket),
        contar_en(motor, DetalleTicket),
        contar_en(motor, HistorialTransicionTicket),
    )


def _par_de_claves(kid: str = "kid-inactiva-012"):
    """Par RSA efimero y su JWKS para validar un Bearer expirado sin red."""
    privada = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(RSAAlgorithm.to_jwk(privada.public_key()))
    jwk.update({"kid": kid, "use": "sig", "alg": "RS256"})
    return privada, {"keys": [jwk]}


def _token_expirado(privada, *, kid: str, emisor: str) -> str:
    """Token RS256 firmado con `exp`/`nbf` vencidos fuera del margen de reloj."""
    ahora = int(time.time())
    return jwt.encode(
        {
            "sub": "sub-012",
            "iss": emisor,
            "iat": ahora - 7200,
            "nbf": ahora - 7200,
            "exp": ahora - 3600,
            "azp": "http://localhost:4200",
        },
        privada,
        algorithm="RS256",
        headers={"kid": kid},
    )


def _transporte_prohibido(_peticion: httpx.Request) -> httpx.Response:
    """AC-26: la autenticacion no debe llegar al Backend API de Clerk."""
    raise AssertionError(
        "AC-26: un Bearer invalido o expirado no debe consultar Clerk"
    )


def _forzar_dialecto_postgresql(motor, monkeypatch) -> None:
    """Ejercita la rama de `get_db_negocio` que resuelve el contexto tenant.

    En SQLite la dependencia devuelve la misma sesion (contexto logico unico,
    AC-16 de la 010) y **no** lee el mapa de control; el 401 del contexto de
    tenant de AC-27 solo se observa con el dialecto PostgreSQL. El motor es de
    este test y `monkeypatch` restaura el nombre al terminar.
    """
    monkeypatch.setattr(motor.dialect, "name", "postgresql")


@pytest.mark.parametrize("variante", ["sin_authorization", "invalido", "expirado"])
def test_alta_con_sesion_ausente_o_invalida_responde_401_sin_escritura_ac_26(
    motor, monkeypatch, variante
):
    """AC-26: sin Bearer o con Bearer invalido/expirado, el alta responde 401."""
    privada, jwks = _par_de_claves()
    # Emisor unico por test: aisla la cache JWKS del resto de la suite (patron
    # de `test_auth.py`) sin limpiar estado global.
    emisor = f"https://clerk.test/{uuid4().hex}"
    monkeypatch.setattr(settings, "CLERK_ISSUER", emisor)
    encabezados = {
        "sin_authorization": {},
        "invalido": {"Authorization": "Bearer token-ilegible"},
        "expirado": {
            "Authorization": (
                "Bearer "
                + _token_expirado(
                    privada, kid="kid-inactiva-012", emisor=emisor
                )
            )
        },
    }[variante]
    antes = _conteos_alta(motor)

    with _cliente_app(
        motor,
        overrides={
            dependencies.obtener_fuente_jwks: lambda: (lambda _emisor: jwks),
            dependencies.obtener_transporte_clerk: lambda: httpx.MockTransport(
                _transporte_prohibido
            ),
        },
        raise_server_exceptions=False,
    ) as cliente_http:
        respuesta = cliente_http.post(
            RUTA_ALTA, json=CUERPO_ALTA, headers=encabezados
        )

    assert respuesta.status_code == 401, respuesta.text
    assert respuesta.json() == {"detail": DETALLE_NO_AUTENTICADO}
    assert respuesta.headers["www-authenticate"] == "Bearer"
    assert _conteos_alta(motor) == antes


def test_alta_con_institucion_inactiva_conserva_403_de_matriz_y_401_del_tenant_ac_27(
    motor, monkeypatch
):
    """AC-27: Admin/Bodeguero 403 por matriz; Solicitante 401 del contexto tenant.

    `requiere_operacion` se resuelve antes de `get_db_negocio`: por eso el
    Administrador y el Bodeguero, que ya no estan en la fila del alta, reciben
    el 403 de la matriz sin llegar al contexto de tenant. El Solicitante pasa la
    matriz y alcanza el 401 de `resolver_contexto_solicitud` porque `INST01`
    esta inactiva. No se reordena ninguna dependencia ni se cambia la
    autenticacion.
    """
    _preparar(motor, activo=False)
    _forzar_dialecto_postgresql(motor, monkeypatch)
    antes = _conteos_alta(motor)

    for rol in ("Administrador", "Bodeguero"):
        with _cliente_app(
            motor,
            identidad=_identidad(CORREO_MAPEADO, rol),
            raise_server_exceptions=False,
        ) as cliente_http:
            respuesta = cliente_http.post(RUTA_ALTA, json=CUERPO_ALTA)
        assert respuesta.status_code == 403, respuesta.text
        assert respuesta.json() == {"detail": DETALLE_PERMISO_INSUFICIENTE}
        assert _conteos_alta(motor) == antes

    with _cliente_app(
        motor,
        identidad=_identidad(CORREO_MAPEADO, "Solicitante"),
        raise_server_exceptions=False,
    ) as cliente_http:
        respuesta = cliente_http.post(RUTA_ALTA, json=CUERPO_ALTA)

    assert respuesta.status_code == 401, respuesta.text
    assert respuesta.json() == {"detail": DETALLE_IDENTIDAD_NO_RESUELVE}
    assert respuesta.headers["www-authenticate"] == "Bearer"
    assert _conteos_alta(motor) == antes
