"""Pruebas unitarias del contexto de tiempo real (Feature 028, T2).

Fijan la copia inmutable de identidad, institucion, rol, expiracion y dominios
visibles que `contexto_tiempo_real` entrega al flujo SSE, la denegacion **403**
cuando la institucion no se resuelve (sin degradar a global) y el cierre
temprano de la sesion de `get_db` antes de abrir el flujo.

La sesion se comprueba con un doble que **cuenta cierres**: en SQLAlchemy 2.1
`Session.is_active` sigue siendo `True` despues de `close()`, asi que ese
indicador no distingue una sesion cerrada.
"""

from dataclasses import FrozenInstanceError
from uuid import uuid4

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker
from starlette.requests import Request

from app.api import dependencies
from app.api.dependencies import ContextoTiempoReal, contexto_tiempo_real
from app.middleware.observabilidad import MiddlewareObservabilidad
from app.models import Rol, Usuario
from app.models.control_canonico import FuncionInstitucion
from app.services.auth_service import IdentidadAutenticada

#: UUID canonico que el middleware de la 024 acepta y propaga.
REQUEST_ID = str(uuid4())

#: Expiracion ficticia de la identidad de prueba (epoch en segundos).
EXPIRA_EN = 1_900_000_000


class _SesionEspia(Session):
    """Sesion real que cuenta cuantas veces se cerro (doble de `get_db`)."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.cierres = 0

    def close(self) -> None:
        self.cierres += 1
        super().close()


def _identidad(
    datos_base,
    *,
    rol: str = "Administrador",
    departamento_id: int | None = None,
    expira_en: int | None = EXPIRA_EN,
) -> IdentidadAutenticada:
    """Identidad suelta con ids reales y el rol legible pedido (patron 011)."""
    usuario = Usuario(
        usuario_id=datos_base["usuario_id"],
        nombre="Ana",
        apellido="Perez",
        correo=datos_base["correo_usado"],
        departamento_id=(
            datos_base["departamento_id"]
            if departamento_id is None
            else departamento_id
        ),
        rol_id=datos_base["rol_id"],
    )
    usuario.rol = Rol(nombre_rol=rol)
    return IdentidadAutenticada(
        usuario=usuario, sub="sub-tiempo-real-028", expira_en=expira_en
    )


def _peticion(request_id: str | None = REQUEST_ID) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/eventos/",
        "headers": [],
        "query_string": b"",
    }
    if request_id is not None:
        scope["state"] = {"request_id": request_id}
    return Request(scope)


def _contexto(
    motor,
    identidad: IdentidadAutenticada,
    *,
    request_id: str | None = REQUEST_ID,
) -> ContextoTiempoReal:
    """Invoca la dependencia como funcion, con sesion real del motor de prueba."""
    with sessionmaker(bind=motor)() as db:
        return contexto_tiempo_real(
            _peticion(request_id), identidad=identidad, db=db
        )


def _apagar_capacidad(motor, institucion_id: str, funcion: str) -> None:
    with sessionmaker(bind=motor)() as db:
        db.add(
            FuncionInstitucion(
                institucion_id=institucion_id,
                funcion=funcion,
                habilitada=False,
            )
        )
        db.commit()


# ---------------------------------------------------------------------------
# Identidad y expiracion
# ---------------------------------------------------------------------------


def test_identidad_construida_sin_expira_en_conserva_el_default():
    """Compatibilidad: los fixtures que no pasan `expira_en` siguen valiendo."""
    usuario = Usuario(
        usuario_id=1,
        nombre="Ana",
        apellido="Perez",
        correo="ana@compustock.cl",
        departamento_id=1,
        rol_id=1,
    )
    identidad = IdentidadAutenticada(usuario=usuario, sub="sub-sin-exp")

    assert identidad.expira_en is None


# ---------------------------------------------------------------------------
# Contexto del flujo
# ---------------------------------------------------------------------------


def test_contexto_copia_identidad_y_los_cuatro_dominios_del_administrador(
    motor, datos_base
):
    contexto = _contexto(motor, _identidad(datos_base))

    assert isinstance(contexto, ContextoTiempoReal)
    assert contexto.usuario_id == datos_base["usuario_id"]
    assert contexto.rol == "Administrador"
    assert contexto.institucion_id == datos_base["institucion_id"]
    assert contexto.expira_en == EXPIRA_EN
    assert contexto.dominios_visibles == {
        "pedidos",
        "inventario",
        "compras",
        "dashboard",
    }
    assert contexto.request_id == REQUEST_ID


def test_contexto_es_inmutable(motor, datos_base):
    contexto = _contexto(motor, _identidad(datos_base))

    with pytest.raises(FrozenInstanceError):
        contexto.rol = "Bodeguero"


def test_contexto_sin_request_id_en_el_scope_no_inventa_uno(motor, datos_base):
    contexto = _contexto(motor, _identidad(datos_base), request_id=None)

    assert contexto.request_id is None


@pytest.mark.parametrize(
    ("capacidad", "dominio_oculto"),
    [
        ("tickets", "pedidos"),
        ("inventario", "inventario"),
        ("dashboard", "dashboard"),
    ],
)
def test_capacidad_apagada_oculta_su_dominio(
    motor, datos_base, capacidad, dominio_oculto
):
    _apagar_capacidad(motor, datos_base["institucion_id"], capacidad)

    contexto = _contexto(motor, _identidad(datos_base))

    assert dominio_oculto not in contexto.dominios_visibles
    assert contexto.dominios_visibles == {
        "pedidos",
        "inventario",
        "compras",
        "dashboard",
    } - {dominio_oculto}


def test_solicitante_no_ve_compras_aunque_la_capacidad_este_encendida(
    motor, datos_base
):
    """Los dominios visibles combinan capacidad y claves de la matriz central."""
    contexto = _contexto(motor, _identidad(datos_base, rol="Solicitante"))

    assert contexto.rol == "Solicitante"
    assert contexto.dominios_visibles == {"pedidos", "inventario", "dashboard"}


def test_identidad_sin_institucion_responde_403_sin_degradar_a_global(
    motor, datos_base
):
    identidad = _identidad(datos_base, departamento_id=999_999)

    with pytest.raises(HTTPException) as error:
        _contexto(motor, identidad)

    assert error.value.status_code == 403


def test_superadmin_no_obtiene_contexto_de_tiempo_real(motor, datos_base):
    """El alcance global no se degrada a una suscripcion institucional."""
    with pytest.raises(HTTPException) as error:
        _contexto(motor, _identidad(datos_base, rol="Superadmin"))

    assert error.value.status_code == 403


# ---------------------------------------------------------------------------
# Sesion: cierre temprano, sesion compartida e idempotencia
# ---------------------------------------------------------------------------


def test_contexto_cierra_la_sesion_antes_de_retornar(motor, datos_base):
    sesion = _SesionEspia(bind=motor)
    try:
        contexto = contexto_tiempo_real(
            _peticion(), identidad=_identidad(datos_base), db=sesion
        )

        assert sesion.cierres == 1
        assert contexto.dominios_visibles
    finally:
        sesion.close()


def test_get_db_y_contexto_comparten_la_sesion_y_cierran_dos_veces(
    motor, datos_base
):
    """La sesion cacheada de `get_db` es una sola y su cierre es idempotente.

    El endpoint observa un cierre al ejecutarse (lo hizo `contexto_tiempo_real`
    antes de devolver) y, al salir el contexto del cliente, el `finally` de
    `get_db` vuelve a cerrar la misma sesion sin error.
    """
    fabrica = sessionmaker(bind=motor, class_=_SesionEspia)
    sesiones: list[_SesionEspia] = []
    identidades_recibidas: list[Session] = []
    cierres_antes_del_endpoint: dict[str, int] = {}

    def obtener_db():
        db = fabrica()
        sesiones.append(db)
        try:
            yield db
        finally:
            db.close()

    identidad = _identidad(datos_base)

    def identidad_con_db(db: Session = Depends(dependencies.get_db)):
        identidades_recibidas.append(db)
        return identidad

    aplicacion = FastAPI()
    aplicacion.add_middleware(MiddlewareObservabilidad)

    @aplicacion.get("/contexto")
    def leer_contexto(
        contexto: ContextoTiempoReal = Depends(contexto_tiempo_real),
    ):
        cierres_antes_del_endpoint["valor"] = sesiones[0].cierres
        return {
            "institucion_id": contexto.institucion_id,
            "request_id": contexto.request_id,
        }

    aplicacion.dependency_overrides[dependencies.get_db] = obtener_db
    aplicacion.dependency_overrides[dependencies.get_current_user] = identidad_con_db

    with TestClient(aplicacion) as cliente_http:
        respuesta = cliente_http.get(
            "/contexto", headers={"X-Request-ID": REQUEST_ID}
        )

        assert respuesta.status_code == 200, respuesta.text
        assert respuesta.json() == {
            "institucion_id": datos_base["institucion_id"],
            "request_id": REQUEST_ID,
        }

    assert len(sesiones) == 1
    # `get_current_user` y `contexto_tiempo_real` recibieron la misma sesion.
    assert identidades_recibidas == sesiones
    # Cerrada antes de que el endpoint se ejecutara.
    assert cierres_antes_del_endpoint["valor"] == 1
    # Y otra vez en el `finally` de `get_db`, sin romper ni propagar error.
    assert sesiones[0].cierres == 2
