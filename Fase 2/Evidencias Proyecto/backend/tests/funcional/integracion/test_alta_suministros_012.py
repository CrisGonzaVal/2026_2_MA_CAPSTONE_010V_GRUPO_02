"""E12-A1 (Feature 012, Bloque A): alta con resolucion de «Suministros».

Seam bajo prueba: la **interfaz HTTP real** (`POST /api/v1/usuarios/`) con la
costura Clerk doblegada (Feature 017). Se observa el contrato 201/422/403, el
`departamento_id` real publicado y la fila de `departamento` persistida.

Cubre D-8/D-9/D-12 y AC-20/AC-21/AC-23/AC-24/AC-25/AC-26/AC-30/AC-31 en lo que
corresponde al alta. La carrera concurrente de dos altas es PostgreSQL gated
(E12-A3); aqui se fija el comportamiento secuencial y transaccional.
"""

from __future__ import annotations

from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.api import dependencies
from app.main import app
from app.models import Departamento, Rol, Sede, Usuario
from app.services import usuario_service
from app.services.departamento_suministros import DESCRIPCION_SUMINISTROS

from tests.funcional.integracion._soporte_sede_011 import identidad

RUTA_USUARIOS = "/api/v1/usuarios/"

#: Centinela para omitir el campo del cuerpo (distinto de enviar `null`).
_OMITIR = object()

_CORREO_ACTOR = "admin.suministros@compustock.cl"


# ---------------------------------------------------------------------------
# Cliente HTTP con la costura Clerk doblegada
# ---------------------------------------------------------------------------


@contextmanager
def _cliente(
    motor,
    rol: str = "Administrador",
    *,
    departamento_id: int,
    usuario_id: int = 9999,
    correo: str = _CORREO_ACTOR,
):
    Fabrica = sessionmaker(autocommit=False, autoflush=False, bind=motor)

    def _db_de_prueba():
        db = Fabrica()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[dependencies.get_db] = _db_de_prueba
    app.dependency_overrides[dependencies.obtener_verificador_correo_clerk] = (
        lambda: (lambda _correo: True)
    )
    from tests.funcional.integracion.soporte_frontera_017 import instalar_frontera_clerk

    instalar_frontera_clerk(identidad_existente=True)
    app.dependency_overrides[dependencies.get_current_user] = lambda: identidad(
        rol, departamento_id, usuario_id, None, correo
    )
    try:
        with TestClient(app, raise_server_exceptions=False) as cliente_http:
            yield cliente_http
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helpers de sembrado y observacion
# ---------------------------------------------------------------------------


def _payload(
    rol_id: int,
    *,
    correo: str,
    departamento_id=_OMITIR,
) -> dict:
    datos = {
        "nombre": "Nuevo",
        "apellido": "Suministros",
        "correo": correo,
        "rol_id": rol_id,
    }
    if departamento_id is not _OMITIR:
        datos["departamento_id"] = departamento_id
    return datos


def _rol_id(motor, nombre: str) -> int:
    with sessionmaker(bind=motor)() as db:
        rol = db.execute(select(Rol).where(Rol.nombre_rol == nombre)).scalars().first()
        assert rol is not None, f"la fixture no sembro el rol {nombre}"
        return rol.rol_id


def _crear_departamento(
    motor,
    *,
    institucion_id: str,
    nombre_dep: str,
    descripcion: str | None = None,
    sede_id: int | None = None,
    activo: bool = True,
) -> int:
    with sessionmaker(bind=motor)() as db:
        departamento = Departamento(
            nombre_dep=nombre_dep,
            descripcion=descripcion,
            institucion_id=institucion_id,
            sede_id=sede_id,
            activo=activo,
        )
        db.add(departamento)
        db.commit()
        db.refresh(departamento)
        return departamento.departamento_id


def _suministros(motor, institucion_id: str | None = None) -> list[dict]:
    with sessionmaker(bind=motor)() as db:
        consulta = db.query(Departamento).filter(
            func.lower(func.trim(Departamento.nombre_dep)) == "suministros"
        )
        if institucion_id is not None:
            consulta = consulta.filter(Departamento.institucion_id == institucion_id)
        return [
            {
                "departamento_id": fila.departamento_id,
                "institucion_id": fila.institucion_id,
                "descripcion": fila.descripcion,
                "sede_id": fila.sede_id,
                "activo": fila.activo,
                "nombre_dep": fila.nombre_dep,
            }
            for fila in consulta.all()
        ]


def _usuario(motor, correo: str) -> dict | None:
    with sessionmaker(bind=motor)() as db:
        usuario = db.execute(
            select(Usuario).where(Usuario.correo == correo)
        ).scalars().first()
        if usuario is None:
            return None
        return {
            "usuario_id": usuario.usuario_id,
            "departamento_id": usuario.departamento_id,
            "rol_id": usuario.rol_id,
            "sede_id": usuario.sede_id,
        }


def _unico_suministros(motor, institucion_id: str) -> dict:
    filas = _suministros(motor, institucion_id)
    assert len(filas) == 1, filas
    return filas[0]


# ---------------------------------------------------------------------------
# AC-20/D-8: Bodeguero sin departamento o con cualquier id positivo
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("departamento", [_OMITIR, None])
def test_alta_bodeguero_sin_departamento_resuelve_suministros(
    motor, dos_instituciones, departamento
):
    rol_bodeguero = dos_instituciones["rol_bodeguero_id"]
    correo = "bodeguero.sin.departamento@compustock.cl"
    with _cliente(
        motor, departamento_id=dos_instituciones["departamento_id"]
    ) as cliente_http:
        respuesta = cliente_http.post(
            RUTA_USUARIOS,
            json=_payload(rol_bodeguero, correo=correo, departamento_id=departamento),
        )

    assert respuesta.status_code == 201, respuesta.text
    suma = _unico_suministros(motor, "INST01")
    assert suma["nombre_dep"] == "Suministros"
    assert suma["descripcion"] == DESCRIPCION_SUMINISTROS
    assert suma["sede_id"] is None
    assert suma["activo"] is True

    cuerpo = respuesta.json()
    assert cuerpo["departamento_id"] == suma["departamento_id"]
    assert cuerpo["correo"] == correo
    usuario = _usuario(motor, correo)
    assert usuario is not None
    assert usuario["departamento_id"] == suma["departamento_id"]


@pytest.mark.parametrize("origen", ["propio", "ajeno", "inexistente"])
def test_alta_bodeguero_ignora_cualquier_departamento_positivo(
    motor, dos_instituciones, origen
):
    rol_bodeguero = dos_instituciones["rol_bodeguero_id"]
    enviado = {
        "propio": dos_instituciones["departamento_id"],
        "ajeno": dos_instituciones["departamento_ajeno_id"],
        "inexistente": 999999,
    }[origen]
    correo = f"bodeguero.ignora.{origen}@compustock.cl"

    with _cliente(
        motor, departamento_id=dos_instituciones["departamento_id"]
    ) as cliente_http:
        respuesta = cliente_http.post(
            RUTA_USUARIOS,
            json=_payload(rol_bodeguero, correo=correo, departamento_id=enviado),
        )

    assert respuesta.status_code == 201, (origen, respuesta.text)
    suma = _unico_suministros(motor, "INST01")
    assert respuesta.json()["departamento_id"] == suma["departamento_id"]
    assert respuesta.json()["departamento_id"] != enviado
    usuario = _usuario(motor, correo)
    assert usuario is not None
    assert usuario["departamento_id"] == suma["departamento_id"]


def test_alta_bodeguero_reutiliza_suministros_activo_sin_modificarlo(
    motor, dos_instituciones
):
    rol_bodeguero = dos_instituciones["rol_bodeguero_id"]
    with sessionmaker(bind=motor)() as db:
        sede = Sede(nombre="Sede Suministros", direccion="Bodega", institucion_id="INST01")
        db.add(sede)
        db.flush()
        sede_id = sede.sede_id
        db.commit()
    existente_id = _crear_departamento(
        motor,
        institucion_id="INST01",
        nombre_dep="Suministros",
        descripcion="Creado a mano",
        sede_id=sede_id,
    )

    with _cliente(
        motor, departamento_id=dos_instituciones["departamento_id"]
    ) as cliente_http:
        respuesta = cliente_http.post(
            RUTA_USUARIOS,
            json=_payload(rol_bodeguero, correo="bodeguero.reutiliza@compustock.cl"),
        )

    assert respuesta.status_code == 201, respuesta.text
    assert respuesta.json()["departamento_id"] == existente_id
    suma = _unico_suministros(motor, "INST01")
    assert suma["descripcion"] == "Creado a mano"
    assert suma["sede_id"] == sede_id


@pytest.mark.parametrize("nombre", [" SUMINISTROS ", "suministros"])
def test_alta_bodeguero_reutiliza_variantes_normalizadas(
    motor, dos_instituciones, nombre
):
    rol_bodeguero = dos_instituciones["rol_bodeguero_id"]
    existente_id = _crear_departamento(
        motor, institucion_id="INST01", nombre_dep=nombre
    )

    with _cliente(
        motor, departamento_id=dos_instituciones["departamento_id"]
    ) as cliente_http:
        respuesta = cliente_http.post(
            RUTA_USUARIOS,
            json=_payload(rol_bodeguero, correo=f"bodeguero.normalizado@compustock.cl"),
        )

    assert respuesta.status_code == 201, respuesta.text
    assert respuesta.json()["departamento_id"] == existente_id
    suma = _unico_suministros(motor, "INST01")
    assert suma["nombre_dep"] == nombre


def test_alta_bodeguero_reactiva_suministros_inactivo(motor, dos_instituciones):
    rol_bodeguero = dos_instituciones["rol_bodeguero_id"]
    existente_id = _crear_departamento(
        motor,
        institucion_id="INST01",
        nombre_dep="Suministros",
        descripcion="Preexistente inactivo",
        activo=False,
    )

    with _cliente(
        motor, departamento_id=dos_instituciones["departamento_id"]
    ) as cliente_http:
        respuesta = cliente_http.post(
            RUTA_USUARIOS,
            json=_payload(rol_bodeguero, correo="bodeguero.reactiva@compustock.cl"),
        )

    assert respuesta.status_code == 201, respuesta.text
    suma = _unico_suministros(motor, "INST01")
    assert suma["departamento_id"] == existente_id
    assert suma["activo"] is True
    assert suma["descripcion"] == "Preexistente inactivo"


def test_dos_altas_bodeguero_comparten_un_solo_suministros(motor, dos_instituciones):
    rol_bodeguero = dos_instituciones["rol_bodeguero_id"]
    with _cliente(
        motor, departamento_id=dos_instituciones["departamento_id"]
    ) as cliente_http:
        primera = cliente_http.post(
            RUTA_USUARIOS,
            json=_payload(rol_bodeguero, correo="bodeguero.uno@compustock.cl"),
        )
        segunda = cliente_http.post(
            RUTA_USUARIOS,
            json=_payload(rol_bodeguero, correo="bodeguero.dos@compustock.cl"),
        )

    assert primera.status_code == 201, primera.text
    assert segunda.status_code == 201, segunda.text
    suma = _unico_suministros(motor, "INST01")
    assert primera.json()["departamento_id"] == suma["departamento_id"]
    assert segunda.json()["departamento_id"] == suma["departamento_id"]


# ---------------------------------------------------------------------------
# AC-23/D-12: no-Bodeguero exige departamento y rechaza «Suministros»
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("departamento", [_OMITIR, None])
def test_alta_no_bodeguero_sin_departamento_responde_422_sin_mutar(
    motor, dos_instituciones, departamento
):
    rol_solicitante = _rol_id(motor, "Solicitante")
    correo = "solicitante.sin.departamento@compustock.cl"

    with _cliente(
        motor, departamento_id=dos_instituciones["departamento_id"]
    ) as cliente_http:
        respuesta = cliente_http.post(
            RUTA_USUARIOS,
            json=_payload(
                rol_solicitante, correo=correo, departamento_id=departamento
            ),
        )

    assert respuesta.status_code == 422, respuesta.text
    assert "departamento" in str(respuesta.json()["detail"]).lower()
    assert _usuario(motor, correo) is None
    assert _suministros(motor) == []


def test_alta_no_bodeguero_con_suministros_responde_422_sin_mutar(
    motor, dos_instituciones
):
    rol_solicitante = _rol_id(motor, "Solicitante")
    suma_id = _crear_departamento(
        motor,
        institucion_id="INST01",
        nombre_dep="Suministros",
        descripcion="Reservado a Bodegueros",
    )
    correo = "solicitante.con.suministros@compustock.cl"

    with _cliente(
        motor, departamento_id=dos_instituciones["departamento_id"]
    ) as cliente_http:
        respuesta = cliente_http.post(
            RUTA_USUARIOS,
            json=_payload(rol_solicitante, correo=correo, departamento_id=suma_id),
        )

    assert respuesta.status_code == 422, respuesta.text
    assert "suministros" in str(respuesta.json()["detail"]).lower()
    assert _usuario(motor, correo) is None
    suma = _unico_suministros(motor, "INST01")
    assert suma["activo"] is True
    assert suma["descripcion"] == "Reservado a Bodegueros"


def test_alta_no_bodeguero_con_departamento_ajeno_conserva_403_sin_mutar(
    motor, dos_instituciones
):
    rol_solicitante = _rol_id(motor, "Solicitante")
    correo = "solicitante.ajeno@compustock.cl"

    with _cliente(
        motor, departamento_id=dos_instituciones["departamento_id"]
    ) as cliente_http:
        respuesta = cliente_http.post(
            RUTA_USUARIOS,
            json=_payload(
                rol_solicitante,
                correo=correo,
                departamento_id=dos_instituciones["departamento_ajeno_id"],
            ),
        )

    assert respuesta.status_code == 403, respuesta.text
    assert _usuario(motor, correo) is None
    assert _suministros(motor) == []


@pytest.mark.parametrize("rol_nombre", ["Bodeguero", "Solicitante"])
@pytest.mark.parametrize("valor", [0, -1])
def test_departamento_id_no_positivo_responde_422_para_todos(
    motor, dos_instituciones, rol_nombre, valor
):
    rol_id = _rol_id(motor, rol_nombre)
    correo = f"invalido.{rol_nombre.lower()}.{abs(valor)}@compustock.cl"

    with _cliente(
        motor, departamento_id=dos_instituciones["departamento_id"]
    ) as cliente_http:
        respuesta = cliente_http.post(
            RUTA_USUARIOS,
            json=_payload(rol_id, correo=correo, departamento_id=valor),
        )

    assert respuesta.status_code == 422, respuesta.text
    assert respuesta.json()["detail"][0]["loc"][-1] == "departamento_id"
    assert _usuario(motor, correo) is None
    assert _suministros(motor) == []


# ---------------------------------------------------------------------------
# AC-26/AC-30: otros roles no crean «Suministros» y aislamiento por institucion
# ---------------------------------------------------------------------------


def test_alta_solicitante_valido_no_crea_suministros(motor, dos_instituciones):
    rol_solicitante = _rol_id(motor, "Solicitante")
    correo = "solicitante.valido@compustock.cl"

    with _cliente(
        motor, departamento_id=dos_instituciones["departamento_id"]
    ) as cliente_http:
        respuesta = cliente_http.post(
            RUTA_USUARIOS,
            json=_payload(
                rol_solicitante,
                correo=correo,
                departamento_id=dos_instituciones["departamento_id"],
            ),
        )

    assert respuesta.status_code == 201, respuesta.text
    assert (
        respuesta.json()["departamento_id"]
        == dos_instituciones["departamento_id"]
    )
    usuario = _usuario(motor, correo)
    assert usuario is not None
    assert usuario["departamento_id"] == dos_instituciones["departamento_id"]
    assert _suministros(motor) == []


def test_alta_de_administrador_denegada_no_crea_suministros(
    motor, dos_instituciones
):
    """La precedencia 403 del rol no asignable se conserva (D-6/AC-10)."""
    correo = "administrador.denegado@compustock.cl"

    with _cliente(
        motor, departamento_id=dos_instituciones["departamento_id"]
    ) as cliente_http:
        respuesta = cliente_http.post(
            RUTA_USUARIOS,
            json=_payload(
                dos_instituciones["rol_id"],
                correo=correo,
                departamento_id=dos_instituciones["departamento_id"],
            ),
        )

    assert respuesta.status_code == 403, respuesta.text
    assert _usuario(motor, correo) is None
    assert _suministros(motor) == []


def test_suministros_se_resuelve_en_la_institucion_del_actor(
    motor, dos_instituciones
):
    rol_bodeguero = dos_instituciones["rol_bodeguero_id"]
    ajeno_id = _crear_departamento(
        motor,
        institucion_id="INST02",
        nombre_dep="Suministros",
        descripcion="Ajeno",
    )

    with _cliente(
        motor, departamento_id=dos_instituciones["departamento_id"]
    ) as cliente_http:
        respuesta = cliente_http.post(
            RUTA_USUARIOS,
            json=_payload(rol_bodeguero, correo="bodeguero.aislado@compustock.cl"),
        )

    assert respuesta.status_code == 201, respuesta.text
    propio = _unico_suministros(motor, "INST01")
    assert propio["departamento_id"] != ajeno_id
    assert respuesta.json()["departamento_id"] == propio["departamento_id"]
    filas = _suministros(motor)
    assert len(filas) == 2
    assert {fila["institucion_id"] for fila in filas} == {"INST01", "INST02"}
    ajeno = _unico_suministros(motor, "INST02")
    assert ajeno["descripcion"] == "Ajeno"


def test_alta_fallida_antes_del_commit_no_confirma_suministros(
    motor, dos_instituciones, monkeypatch
):
    """D-8: si el alta no confirma el usuario, «Suministros» no queda confirmado.

    Se induce el fallo en la confirmacion del tenant (despues de resolver el
    departamento y antes del commit); el rollback del servicio debe descartar
    tanto el usuario como la fila recien creada.
    """
    rol_bodeguero = dos_instituciones["rol_bodeguero_id"]
    correo = "bodeguero.fallido@compustock.cl"

    def _fallar(*_args, **_kwargs):
        raise RuntimeError("fallo simulado antes de confirmar el usuario")

    monkeypatch.setattr(usuario_service, "_confirmar_usuario_tenant", _fallar)

    with _cliente(
        motor, departamento_id=dos_instituciones["departamento_id"]
    ) as cliente_http:
        respuesta = cliente_http.post(
            RUTA_USUARIOS,
            json=_payload(rol_bodeguero, correo=correo),
        )

    assert respuesta.status_code == 500, respuesta.text
    assert _usuario(motor, correo) is None
    assert _suministros(motor) == []
