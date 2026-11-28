"""E12-A2 (Feature 012, Bloque A): edicion por rol, motivo D-5 y legacy.

Seam bajo prueba: la **interfaz HTTP real** de edicion
(`PUT /api/v1/usuarios/{usuario_id}`), mas la ruta de control de Administradores
que reutiliza el mismo DTO (`PUT /api/v1/control/instituciones/{id}/usuarios/{id}`).
Se observa el contrato 200/403/404/409/422, el `departamento_id` real publicado y
la fila de `departamento` persistida.

Cubre D-8/D-12/D-13/D-15 y AC-27/AC-28/AC-29/AC-30/AC-31 en lo que corresponde a
la edicion:

  * Bodeguero legacy «Biblioteca» -> «Suministros» exige motivo D-5;
  * Bodeguero ya en «Suministros» sin cambios no exige motivo;
  * no-Bodeguero exige departamento (422), rechaza «Suministros» (422) y
    conserva 403/404 para un departamento ajeno;
  * cambio de rol a/desde Bodeguero con motivo;
  * `usuario.sede_id` no se toca en la edicion;
  * el 409 del ultimo Administrador activo se conserva y no hay 409 por encargado;
  * aislamiento institucional y respuesta con el id real.

La carrera concurrente de dos ediciones es PostgreSQL gated (E12-A3); aqui se
fija el comportamiento secuencial y transaccional.
"""

from __future__ import annotations

from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.api import dependencies
from app.main import app
from app.models import Departamento, RegistroMotivoConstancia, Rol, Sede, Usuario
from app.services.departamento_suministros import DESCRIPCION_SUMINISTROS

from tests.funcional.integracion._soporte_sede_011 import identidad

RUTA_USUARIO = "/api/v1/usuarios/{usuario_id}"
RUTA_CONTROL_USUARIO = (
    "/api/v1/control/instituciones/{institucion_id}/usuarios/{usuario_id}"
)

MOTIVO = {
    "codigo": "reasignacion_organizacional",
    "texto": "Ajuste organizacional de la edicion E12-A2",
}

#: Centinela para omitir el campo del cuerpo (distinto de enviar `null`).
_OMITIR = object()

_CORREO_ACTOR = "admin.edicion012@compustock.cl"


# ---------------------------------------------------------------------------
# Cliente HTTP con la costura Clerk doblegada
# ---------------------------------------------------------------------------


@contextmanager
def _cliente(
    motor,
    rol: str = "Administrador",
    *,
    departamento_id: int | None,
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
    activo: bool = True,
) -> int:
    with sessionmaker(bind=motor)() as db:
        departamento = Departamento(
            nombre_dep=nombre_dep,
            descripcion=descripcion,
            institucion_id=institucion_id,
            activo=activo,
        )
        db.add(departamento)
        db.commit()
        db.refresh(departamento)
        return departamento.departamento_id


def _crear_sede(motor, *, institucion_id: str, nombre: str = "Sede A2") -> int:
    with sessionmaker(bind=motor)() as db:
        sede = Sede(nombre=nombre, institucion_id=institucion_id)
        db.add(sede)
        db.commit()
        db.refresh(sede)
        return sede.sede_id


def _crear_usuario(
    motor,
    *,
    departamento_id: int,
    rol_nombre: str,
    correo: str,
    nombre: str = "Sonda",
    apellido: str = "A2",
    sede_id: int | None = None,
) -> int:
    with sessionmaker(bind=motor)() as db:
        rol = db.execute(select(Rol).where(Rol.nombre_rol == rol_nombre)).scalars().first()
        assert rol is not None, f"la fixture no sembro el rol {rol_nombre}"
        usuario = Usuario(
            nombre=nombre,
            apellido=apellido,
            correo=correo,
            departamento_id=departamento_id,
            rol_id=rol.rol_id,
            sede_id=sede_id,
        )
        db.add(usuario)
        db.commit()
        db.refresh(usuario)
        return usuario.usuario_id


def _usuario(motor, usuario_id: int) -> dict:
    with sessionmaker(bind=motor)() as db:
        usuario = db.get(Usuario, usuario_id)
        assert usuario is not None
        return {
            "nombre": usuario.nombre,
            "apellido": usuario.apellido,
            "departamento_id": usuario.departamento_id,
            "rol_id": usuario.rol_id,
            "sede_id": usuario.sede_id,
        }


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
                "nombre_dep": fila.nombre_dep,
                "descripcion": fila.descripcion,
                "sede_id": fila.sede_id,
                "activo": fila.activo,
            }
            for fila in consulta.all()
        ]


def _unico_suministros(motor, institucion_id: str) -> dict:
    filas = _suministros(motor, institucion_id)
    assert len(filas) == 1, filas
    return filas[0]


def _contar_motivos(motor) -> int:
    with sessionmaker(bind=motor)() as db:
        return db.query(RegistroMotivoConstancia).count()


def _cuerpo(
    usuario: dict,
    *,
    nombre: str | None = None,
    apellido: str | None = None,
    departamento=_OMITIR,
    rol_id: int | None = None,
    motivo: dict | None = None,
) -> dict:
    datos = {
        "nombre": usuario["nombre"] if nombre is None else nombre,
        "apellido": usuario["apellido"] if apellido is None else apellido,
        "rol_id": usuario["rol_id"] if rol_id is None else rol_id,
    }
    if departamento is not _OMITIR:
        datos["departamento_id"] = departamento
    if motivo is not None:
        datos["motivo"] = motivo
    return datos


# ---------------------------------------------------------------------------
# AC-27/D-15: Bodeguero legacy «Biblioteca» -> «Suministros»
# ---------------------------------------------------------------------------


def test_bodeguero_legacy_pasa_a_suministros_con_motivo(motor, dos_instituciones):
    biblioteca = _crear_departamento(
        motor, institucion_id="INST01", nombre_dep="Biblioteca"
    )
    sede = _crear_sede(motor, institucion_id="INST01")
    usuario_id = _crear_usuario(
        motor,
        departamento_id=biblioteca,
        rol_nombre="Bodeguero",
        correo="legacy.con.motivo@compustock.cl",
        nombre="Legacy",
        apellido="Bodega",
        sede_id=sede,
    )
    original = _usuario(motor, usuario_id)

    with _cliente(
        motor, departamento_id=dos_instituciones["departamento_id"]
    ) as cliente_http:
        respuesta = cliente_http.put(
            RUTA_USUARIO.format(usuario_id=usuario_id),
            json=_cuerpo(
                original,
                # Un id positivo del cliente se ignora para Bodeguero (D-8).
                departamento=999999,
                motivo=MOTIVO,
            ),
        )

    assert respuesta.status_code == 200, respuesta.text
    suma = _unico_suministros(motor, "INST01")
    assert suma["nombre_dep"] == "Suministros"
    assert suma["descripcion"] == DESCRIPCION_SUMINISTROS
    assert suma["sede_id"] is None
    assert suma["activo"] is True

    assert respuesta.json()["departamento_id"] == suma["departamento_id"]
    guardado = _usuario(motor, usuario_id)
    assert guardado["departamento_id"] == suma["departamento_id"]
    assert guardado["departamento_id"] != biblioteca
    # La sede del Bodeguero se persiste aparte (`PUT .../sede`): la edicion no
    # la toca (D-10/D-13).
    assert guardado["sede_id"] == sede
    assert _contar_motivos(motor) == 1


def test_bodeguero_legacy_sin_motivo_responde_422_sin_mutar(motor, dos_instituciones):
    biblioteca = _crear_departamento(
        motor, institucion_id="INST01", nombre_dep="Biblioteca"
    )
    usuario_id = _crear_usuario(
        motor,
        departamento_id=biblioteca,
        rol_nombre="Bodeguero",
        correo="legacy.sin.motivo@compustock.cl",
        nombre="Legacy",
        apellido="Bodega",
    )
    original = _usuario(motor, usuario_id)

    with _cliente(
        motor, departamento_id=dos_instituciones["departamento_id"]
    ) as cliente_http:
        respuesta = cliente_http.put(
            RUTA_USUARIO.format(usuario_id=usuario_id),
            json=_cuerpo(original),
        )

    assert respuesta.status_code == 422, respuesta.text
    assert "motivo" in str(respuesta.json()["detail"]).lower()
    assert _usuario(motor, usuario_id) == original
    # La fila resuelta comparte la transaccion y nunca se confirma si la
    # edicion no se aplica (D-8).
    assert _suministros(motor) == []
    assert _contar_motivos(motor) == 0


def test_bodeguero_ya_en_suministros_sin_cambios_no_exige_motivo(
    motor, dos_instituciones
):
    suma = _crear_departamento(
        motor, institucion_id="INST01", nombre_dep="Suministros"
    )
    usuario_id = _crear_usuario(
        motor,
        departamento_id=suma,
        rol_nombre="Bodeguero",
        correo="bodeguero.estable@compustock.cl",
        nombre="Estable",
        apellido="Suministros",
    )
    original = _usuario(motor, usuario_id)

    with _cliente(
        motor, departamento_id=dos_instituciones["departamento_id"]
    ) as cliente_http:
        respuesta = cliente_http.put(
            RUTA_USUARIO.format(usuario_id=usuario_id),
            json=_cuerpo(original),
        )

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["departamento_id"] == suma
    assert _usuario(motor, usuario_id) == original
    assert _contar_motivos(motor) == 0


def test_bodeguero_en_suministros_cambio_de_nombre_exige_motivo(
    motor, dos_instituciones
):
    suma = _crear_departamento(
        motor, institucion_id="INST01", nombre_dep="Suministros"
    )
    usuario_id = _crear_usuario(
        motor,
        departamento_id=suma,
        rol_nombre="Bodeguero",
        correo="bodeguero.renombrado@compustock.cl",
        nombre="Antes",
        apellido="Suministros",
    )
    original = _usuario(motor, usuario_id)

    with _cliente(
        motor, departamento_id=dos_instituciones["departamento_id"]
    ) as cliente_http:
        sin_motivo = cliente_http.put(
            RUTA_USUARIO.format(usuario_id=usuario_id),
            json=_cuerpo(original, nombre="Despues"),
        )
        assert sin_motivo.status_code == 422, sin_motivo.text
        assert _usuario(motor, usuario_id)["nombre"] == "Antes"
        assert _contar_motivos(motor) == 0

        con_motivo = cliente_http.put(
            RUTA_USUARIO.format(usuario_id=usuario_id),
            json=_cuerpo(original, nombre="Despues", motivo=MOTIVO),
        )

    assert con_motivo.status_code == 200, con_motivo.text
    assert _usuario(motor, usuario_id)["nombre"] == "Despues"
    assert _usuario(motor, usuario_id)["departamento_id"] == suma
    assert _contar_motivos(motor) == 1


# ---------------------------------------------------------------------------
# AC-23/D-12: no-Bodeguero exige departamento y rechaza «Suministros»
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("departamento", [_OMITIR, None])
def test_no_bodeguero_sin_departamento_responde_422_sin_mutar(
    motor, dos_instituciones, departamento
):
    usuario_id = dos_instituciones["usuarios_inst01"]["Solicitante"]
    original = _usuario(motor, usuario_id)

    with _cliente(
        motor, departamento_id=dos_instituciones["departamento_id"]
    ) as cliente_http:
        respuesta = cliente_http.put(
            RUTA_USUARIO.format(usuario_id=usuario_id),
            json=_cuerpo(
                original,
                nombre="Cambiado",
                departamento=departamento,
                motivo=MOTIVO,
            ),
        )

    assert respuesta.status_code == 422, respuesta.text
    assert "departamento" in str(respuesta.json()["detail"]).lower()
    assert _usuario(motor, usuario_id) == original
    assert _suministros(motor) == []
    assert _contar_motivos(motor) == 0


def test_no_bodeguero_con_suministros_responde_422_sin_mutar(
    motor, dos_instituciones
):
    suma = _crear_departamento(
        motor,
        institucion_id="INST01",
        nombre_dep="Suministros",
        descripcion="Reservado a Bodegueros",
    )
    usuario_id = dos_instituciones["usuarios_inst01"]["Solicitante"]
    original = _usuario(motor, usuario_id)

    with _cliente(
        motor, departamento_id=dos_instituciones["departamento_id"]
    ) as cliente_http:
        respuesta = cliente_http.put(
            RUTA_USUARIO.format(usuario_id=usuario_id),
            json=_cuerpo(
                original,
                nombre="Cambiado",
                departamento=suma,
                motivo=MOTIVO,
            ),
        )

    assert respuesta.status_code == 422, respuesta.text
    assert "suministros" in str(respuesta.json()["detail"]).lower()
    assert _usuario(motor, usuario_id) == original
    fila = _unico_suministros(motor, "INST01")
    assert fila["descripcion"] == "Reservado a Bodegueros"
    assert fila["activo"] is True
    assert _contar_motivos(motor) == 0


def test_no_bodeguero_con_departamento_ajeno_conserva_403_o_404(
    motor, dos_instituciones
):
    usuario_id = dos_instituciones["usuarios_inst01"]["Solicitante"]
    original = _usuario(motor, usuario_id)

    with _cliente(
        motor, departamento_id=dos_instituciones["departamento_id"]
    ) as cliente_http:
        respuesta = cliente_http.put(
            RUTA_USUARIO.format(usuario_id=usuario_id),
            json=_cuerpo(
                original,
                departamento=dos_instituciones["departamento_ajeno_id"],
                motivo=MOTIVO,
            ),
        )

    assert respuesta.status_code in (403, 404), respuesta.text
    assert _usuario(motor, usuario_id) == original
    assert _suministros(motor) == []
    assert _contar_motivos(motor) == 0


def test_no_bodeguero_con_departamento_valido_responde_200(motor, dos_instituciones):
    usuario_id = dos_instituciones["usuarios_inst01"]["Solicitante"]
    original = _usuario(motor, usuario_id)

    with _cliente(
        motor, departamento_id=dos_instituciones["departamento_id"]
    ) as cliente_http:
        respuesta = cliente_http.put(
            RUTA_USUARIO.format(usuario_id=usuario_id),
            json=_cuerpo(
                original,
                nombre="Cambiado",
                departamento=dos_instituciones["departamento_id"],
                motivo=MOTIVO,
            ),
        )

    assert respuesta.status_code == 200, respuesta.text
    guardado = _usuario(motor, usuario_id)
    assert guardado["nombre"] == "Cambiado"
    assert guardado["departamento_id"] == dos_instituciones["departamento_id"]
    assert _contar_motivos(motor) == 1


@pytest.mark.parametrize("rol_nombre", ["Bodeguero", "Solicitante"])
@pytest.mark.parametrize("valor", [0, -1])
def test_departamento_id_no_positivo_en_edicion_responde_422(
    motor, dos_instituciones, rol_nombre, valor
):
    usuario_id = dos_instituciones["usuarios_inst01"]["Solicitante"]
    original = _usuario(motor, usuario_id)

    with _cliente(
        motor, departamento_id=dos_instituciones["departamento_id"]
    ) as cliente_http:
        respuesta = cliente_http.put(
            RUTA_USUARIO.format(usuario_id=usuario_id),
            json=_cuerpo(
                original,
                departamento=valor,
                rol_id=_rol_id(motor, rol_nombre),
                motivo=MOTIVO,
            ),
        )

    assert respuesta.status_code == 422, respuesta.text
    assert respuesta.json()["detail"][0]["loc"][-1] == "departamento_id"
    assert _usuario(motor, usuario_id) == original
    assert _suministros(motor) == []
    assert _contar_motivos(motor) == 0


# ---------------------------------------------------------------------------
# AC-28/D-13: cambio de rol a Bodeguero
# ---------------------------------------------------------------------------


def test_solicitante_a_bodeguero_resuelve_suministros_con_motivo(
    motor, dos_instituciones
):
    sede = _crear_sede(motor, institucion_id="INST01")
    usuario_id = dos_instituciones["usuarios_inst01"]["Solicitante"]
    with sessionmaker(bind=motor)() as db:
        # Se fija una sede previa para probar que la edicion no la modifica.
        db.get(Usuario, usuario_id).sede_id = sede
        db.commit()
    original = _usuario(motor, usuario_id)

    with _cliente(
        motor, departamento_id=dos_instituciones["departamento_id"]
    ) as cliente_http:
        respuesta = cliente_http.put(
            RUTA_USUARIO.format(usuario_id=usuario_id),
            json=_cuerpo(
                original,
                departamento=_OMITIR,
                rol_id=dos_instituciones["rol_bodeguero_id"],
                motivo=MOTIVO,
            ),
        )

    assert respuesta.status_code == 200, respuesta.text
    suma = _unico_suministros(motor, "INST01")
    assert respuesta.json()["departamento_id"] == suma["departamento_id"]
    guardado = _usuario(motor, usuario_id)
    assert guardado["rol_id"] == dos_instituciones["rol_bodeguero_id"]
    assert guardado["departamento_id"] == suma["departamento_id"]
    assert guardado["sede_id"] == sede
    assert _contar_motivos(motor) == 1


def test_solicitante_a_bodeguero_sin_motivo_responde_422_sin_mutar(
    motor, dos_instituciones
):
    usuario_id = dos_instituciones["usuarios_inst01"]["Solicitante"]
    original = _usuario(motor, usuario_id)

    with _cliente(
        motor, departamento_id=dos_instituciones["departamento_id"]
    ) as cliente_http:
        respuesta = cliente_http.put(
            RUTA_USUARIO.format(usuario_id=usuario_id),
            json=_cuerpo(
                original,
                departamento=_OMITIR,
                rol_id=dos_instituciones["rol_bodeguero_id"],
            ),
        )

    assert respuesta.status_code == 422, respuesta.text
    assert "motivo" in str(respuesta.json()["detail"]).lower()
    assert _usuario(motor, usuario_id) == original
    assert _suministros(motor) == []
    assert _contar_motivos(motor) == 0


# ---------------------------------------------------------------------------
# AC-29/D-13: cambio desde Bodeguero a Solicitante
# ---------------------------------------------------------------------------


def test_bodeguero_a_solicitante_con_departamento_valido_responde_200(
    motor, dos_instituciones
):
    suma = _crear_departamento(
        motor, institucion_id="INST01", nombre_dep="Suministros"
    )
    sede = _crear_sede(motor, institucion_id="INST01")
    usuario_id = _crear_usuario(
        motor,
        departamento_id=suma,
        rol_nombre="Bodeguero",
        correo="bodeguero.a.solicitante@compustock.cl",
        nombre="Bodega",
        apellido="Cambio",
        sede_id=sede,
    )
    original = _usuario(motor, usuario_id)
    rol_solicitante = _rol_id(motor, "Solicitante")

    with _cliente(
        motor, departamento_id=dos_instituciones["departamento_id"]
    ) as cliente_http:
        sin_motivo = cliente_http.put(
            RUTA_USUARIO.format(usuario_id=usuario_id),
            json=_cuerpo(
                original,
                departamento=dos_instituciones["departamento_id"],
                rol_id=rol_solicitante,
            ),
        )
        assert sin_motivo.status_code == 422, sin_motivo.text
        assert _usuario(motor, usuario_id) == original
        assert _contar_motivos(motor) == 0

        con_motivo = cliente_http.put(
            RUTA_USUARIO.format(usuario_id=usuario_id),
            json=_cuerpo(
                original,
                departamento=dos_instituciones["departamento_id"],
                rol_id=rol_solicitante,
                motivo=MOTIVO,
            ),
        )

    assert con_motivo.status_code == 200, con_motivo.text
    guardado = _usuario(motor, usuario_id)
    assert guardado["rol_id"] == rol_solicitante
    assert guardado["departamento_id"] == dos_instituciones["departamento_id"]
    # La edicion no limpia la sede previa (fuera del alcance de la enmienda).
    assert guardado["sede_id"] == sede
    assert _contar_motivos(motor) == 1


def test_bodeguero_a_solicitante_con_suministros_responde_422_sin_mutar(
    motor, dos_instituciones
):
    suma = _crear_departamento(
        motor, institucion_id="INST01", nombre_dep="Suministros"
    )
    usuario_id = _crear_usuario(
        motor,
        departamento_id=suma,
        rol_nombre="Bodeguero",
        correo="bodeguero.suministros.a.solicitante@compustock.cl",
        nombre="Bodega",
        apellido="Cambio",
    )
    original = _usuario(motor, usuario_id)

    with _cliente(
        motor, departamento_id=dos_instituciones["departamento_id"]
    ) as cliente_http:
        respuesta = cliente_http.put(
            RUTA_USUARIO.format(usuario_id=usuario_id),
            json=_cuerpo(
                original,
                departamento=suma,
                rol_id=_rol_id(motor, "Solicitante"),
                motivo=MOTIVO,
            ),
        )

    assert respuesta.status_code == 422, respuesta.text
    assert "suministros" in str(respuesta.json()["detail"]).lower()
    assert _usuario(motor, usuario_id) == original
    assert _contar_motivos(motor) == 0


def test_bodeguero_a_administrador_por_administrador_responde_403_sin_mutar(
    motor, dos_instituciones
):
    biblioteca = _crear_departamento(
        motor, institucion_id="INST01", nombre_dep="Biblioteca"
    )
    usuario_id = _crear_usuario(
        motor,
        departamento_id=biblioteca,
        rol_nombre="Bodeguero",
        correo="bodeguero.a.administrador@compustock.cl",
    )
    original = _usuario(motor, usuario_id)

    with _cliente(
        motor, departamento_id=dos_instituciones["departamento_id"]
    ) as cliente_http:
        respuesta = cliente_http.put(
            RUTA_USUARIO.format(usuario_id=usuario_id),
            json=_cuerpo(
                original,
                departamento=dos_instituciones["departamento_id"],
                rol_id=dos_instituciones["rol_id"],
                motivo=MOTIVO,
            ),
        )

    assert respuesta.status_code == 403, respuesta.text
    assert _usuario(motor, usuario_id) == original
    assert _suministros(motor) == []
    assert _contar_motivos(motor) == 0


# ---------------------------------------------------------------------------
# AC-12: continuidad administrativa sin encargados
# ---------------------------------------------------------------------------


def test_editar_ultimo_administrador_a_bodeguero_conserva_409(
    motor, datos_base
):
    # `datos_base` siembra un unico Administrador; `dos_instituciones` agrega el
    # de INST02 y en SQLite ambos comparten el contexto logico unico, por lo que
    # no serviria para el caso del ultimo Administrador.
    usuario_id = datos_base["usuario_id"]
    original = _usuario(motor, usuario_id)

    with _cliente(
        motor, departamento_id=datos_base["departamento_id"]
    ) as cliente_http:
        respuesta = cliente_http.put(
            RUTA_USUARIO.format(usuario_id=usuario_id),
            json=_cuerpo(
                original,
                departamento=_OMITIR,
                rol_id=datos_base["rol_bodeguero_id"],
                motivo=MOTIVO,
            ),
        )

    assert respuesta.status_code == 409, respuesta.text
    assert "Administrador" in respuesta.json()["detail"]
    assert _usuario(motor, usuario_id) == original
    assert _suministros(motor) == []
    assert _contar_motivos(motor) == 0


def test_edicion_de_usuario_no_bloquea_por_encargado(motor, dos_instituciones):
    """B1 retiro la tabla puente: la edicion no consulta encargados.

    Un Solicitante (rol que antes podia ser encargado de su departamento) se
    edita solo por rol/departamento/motivo y responde 200.
    """
    usuario_id = dos_instituciones["usuarios_inst01"]["Solicitante"]
    original = _usuario(motor, usuario_id)

    with _cliente(
        motor, departamento_id=dos_instituciones["departamento_id"]
    ) as cliente_http:
        respuesta = cliente_http.put(
            RUTA_USUARIO.format(usuario_id=usuario_id),
            json=_cuerpo(
                original,
                nombre="Sin.Encargado",
                departamento=dos_instituciones["departamento_id"],
                motivo=MOTIVO,
            ),
        )

    assert respuesta.status_code == 200, respuesta.text
    assert _usuario(motor, usuario_id)["nombre"] == "Sin.Encargado"


# ---------------------------------------------------------------------------
# AC-30: aislamiento institucional y respuesta con el id real
# ---------------------------------------------------------------------------


def test_bodeguero_resuelve_suministros_de_su_institucion_y_publica_el_id_real(
    motor, dos_instituciones
):
    ajeno = _crear_departamento(
        motor,
        institucion_id="INST02",
        nombre_dep="Suministros",
        descripcion="Ajeno",
    )
    biblioteca = _crear_departamento(
        motor, institucion_id="INST01", nombre_dep="Biblioteca"
    )
    usuario_id = _crear_usuario(
        motor,
        departamento_id=biblioteca,
        rol_nombre="Bodeguero",
        correo="bodeguero.aislado.edicion@compustock.cl",
    )
    original = _usuario(motor, usuario_id)

    with _cliente(
        motor, departamento_id=dos_instituciones["departamento_id"]
    ) as cliente_http:
        respuesta = cliente_http.put(
            RUTA_USUARIO.format(usuario_id=usuario_id),
            json=_cuerpo(original, departamento=ajeno, motivo=MOTIVO),
        )

    assert respuesta.status_code == 200, respuesta.text
    propio = _unico_suministros(motor, "INST01")
    assert respuesta.json()["departamento_id"] == propio["departamento_id"]
    assert respuesta.json()["departamento_id"] != ajeno
    assert _usuario(motor, usuario_id)["departamento_id"] == propio["departamento_id"]
    ajeno_guardado = _unico_suministros(motor, "INST02")
    assert ajeno_guardado["departamento_id"] == ajeno
    assert ajeno_guardado["descripcion"] == "Ajeno"


def test_editar_usuario_ajeno_responde_404_sin_resolver_suministros(
    motor, dos_instituciones
):
    ajeno_id = dos_instituciones["usuarios_inst02"]["Bodeguero"]
    original = _usuario(motor, ajeno_id)

    with _cliente(
        motor, departamento_id=dos_instituciones["departamento_id"]
    ) as cliente_http:
        respuesta = cliente_http.put(
            RUTA_USUARIO.format(usuario_id=ajeno_id),
            json=_cuerpo(original, motivo=MOTIVO),
        )

    assert respuesta.status_code == 404, respuesta.text
    assert _usuario(motor, ajeno_id) == original
    assert _suministros(motor) == []
    assert _contar_motivos(motor) == 0


# ---------------------------------------------------------------------------
# AC-23/D-12: la ruta de control reutiliza el mismo DTO
# ---------------------------------------------------------------------------


def test_control_omite_departamento_responde_422_sin_mutar(
    motor, dos_instituciones
):
    usuario_id = dos_instituciones["usuarios_inst01"]["Administrador"]
    original = _usuario(motor, usuario_id)

    with _cliente(
        motor, "Superadmin", departamento_id=None
    ) as cliente_http:
        respuesta = cliente_http.put(
            RUTA_CONTROL_USUARIO.format(
                institucion_id="INST01", usuario_id=usuario_id
            ),
            json=_cuerpo(original, motivo=MOTIVO),
        )

    assert respuesta.status_code == 422, respuesta.text
    assert "departamento" in str(respuesta.json()["detail"]).lower()
    assert _usuario(motor, usuario_id) == original
    assert _contar_motivos(motor) == 0


def test_control_rechaza_suministros_para_administrador_422(
    motor, dos_instituciones
):
    suma = _crear_departamento(
        motor, institucion_id="INST01", nombre_dep="Suministros"
    )
    usuario_id = dos_instituciones["usuarios_inst01"]["Administrador"]
    original = _usuario(motor, usuario_id)

    with _cliente(
        motor, "Superadmin", departamento_id=None
    ) as cliente_http:
        respuesta = cliente_http.put(
            RUTA_CONTROL_USUARIO.format(
                institucion_id="INST01", usuario_id=usuario_id
            ),
            json=_cuerpo(
                original,
                departamento=suma,
                motivo=MOTIVO,
            ),
        )

    assert respuesta.status_code == 422, respuesta.text
    assert "suministros" in str(respuesta.json()["detail"]).lower()
    assert _usuario(motor, usuario_id) == original
    assert _contar_motivos(motor) == 0
