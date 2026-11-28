"""E12-A1 (Feature 012): contrato y resolucion del departamento «Suministros».

Seam bajo prueba: el helper de servicio `resolver_departamento_suministros`
(unidad sobre una sesion real) y los DTOs de entrada/salida (contrato Pydantic).
La concurrencia real entre transacciones es PostgreSQL gated (E12-A3); aqui se
fija el comportamiento deterministico:

  * busqueda por `lower(trim(nombre_dep)) == 'suministros'` dentro de la
    institucion (D-8);
  * creacion con descripcion, `sede_id = NULL` y `activo = True`;
  * reutilizacion sin tocar nombre, descripcion ni sede; reactivacion del
    inactivo (D-8/D-9);
  * aislamiento por institucion y relectura tras el conflicto de unicidad;
  * la creacion no se confirma antes del commit del llamador (D-8).

Contrato (D-12): `departamento_id` es opcional solo en `UsuarioCrear` y
`UsuarioEdicion`; `UsuarioBase` y `UsuarioRespuesta` lo conservan obligatorio y
`ge=1` rechaza `0`/negativo en todos.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.models import Departamento, Institucion, Sede
from app.schemas.usuario_schema import (
    UsuarioBase,
    UsuarioCrear,
    UsuarioEdicion,
    UsuarioRespuesta,
)
from app.services import departamento_suministros
from app.services.departamento_suministros import (
    DESCRIPCION_SUMINISTROS,
    NOMBRE_SUMINISTROS,
    es_departamento_suministros,
    resolver_departamento_suministros,
)


# ---------------------------------------------------------------------------
# Helpers de sembrado
# ---------------------------------------------------------------------------


def _sembrar_institucion(motor, institucion_id: str) -> None:
    with sessionmaker(bind=motor)() as db:
        db.add(Institucion(institucion_id=institucion_id, nombre=f"Institucion {institucion_id}"))
        db.commit()


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


def _suministros(motor, institucion_id: str | None = None) -> list[Departamento]:
    with sessionmaker(bind=motor)() as db:
        consulta = db.query(Departamento).filter(
            func.lower(func.trim(Departamento.nombre_dep))
            == NOMBRE_SUMINISTROS.lower()
        )
        if institucion_id is not None:
            consulta = consulta.filter(Departamento.institucion_id == institucion_id)
        return consulta.all()


# ---------------------------------------------------------------------------
# D-8: creacion, reutilizacion, reactivacion y aislamiento
# ---------------------------------------------------------------------------


def test_crea_suministros_con_los_valores_de_la_spec(motor):
    _sembrar_institucion(motor, "INST01")
    with sessionmaker(bind=motor)() as db:
        departamento = resolver_departamento_suministros(db, "INST01")

        assert departamento.departamento_id is not None
        assert departamento.nombre_dep == NOMBRE_SUMINISTROS
        assert departamento.descripcion == DESCRIPCION_SUMINISTROS
        assert departamento.institucion_id == "INST01"
        assert departamento.sede_id is None
        assert departamento.activo is True


def test_reutiliza_suministros_activo_sin_tocar_descripcion_ni_sede(motor):
    _sembrar_institucion(motor, "INST01")
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

    with sessionmaker(bind=motor)() as db:
        resultado = resolver_departamento_suministros(db, "INST01")

        assert resultado.departamento_id == existente_id
        assert resultado.descripcion == "Creado a mano"
        assert resultado.sede_id == sede_id
        assert resultado.activo is True
    assert len(_suministros(motor, "INST01")) == 1


@pytest.mark.parametrize("nombre", [" SUMINISTROS ", "suministros", "SuMiNiStRoS"])
def test_encuentra_por_nombre_normalizado_y_conserva_el_nombre(motor, nombre):
    _sembrar_institucion(motor, "INST01")
    existente_id = _crear_departamento(
        motor, institucion_id="INST01", nombre_dep=nombre
    )

    with sessionmaker(bind=motor)() as db:
        resultado = resolver_departamento_suministros(db, "INST01")

        assert resultado.departamento_id == existente_id
        assert resultado.nombre_dep == nombre
    assert len(_suministros(motor, "INST01")) == 1


def test_reactiva_suministros_inactivo_sin_duplicar_ni_reescribir(motor):
    _sembrar_institucion(motor, "INST01")
    existente_id = _crear_departamento(
        motor,
        institucion_id="INST01",
        nombre_dep="Suministros",
        descripcion="Preexistente inactivo",
        activo=False,
    )

    with sessionmaker(bind=motor)() as db:
        resultado = resolver_departamento_suministros(db, "INST01")

        assert resultado.departamento_id == existente_id
        assert resultado.activo is True
        assert resultado.descripcion == "Preexistente inactivo"
        db.commit()  # el llamador confirma la transaccion compartida (D-8)
    filas = _suministros(motor, "INST01")
    assert len(filas) == 1
    assert filas[0].activo is True


def test_no_reutiliza_el_suministros_de_otra_institucion(motor):
    _sembrar_institucion(motor, "INST01")
    _sembrar_institucion(motor, "INST02")
    ajeno_id = _crear_departamento(
        motor,
        institucion_id="INST02",
        nombre_dep="Suministros",
        descripcion="Ajeno",
    )

    with sessionmaker(bind=motor)() as db:
        propio = resolver_departamento_suministros(db, "INST01")

        assert propio.departamento_id != ajeno_id
        assert propio.institucion_id == "INST01"
        db.commit()  # el llamador confirma la transaccion compartida (D-8)
    filas = _suministros(motor)
    assert {fila.institucion_id for fila in filas} == {"INST01", "INST02"}
    assert len(filas) == 2


def test_no_confirma_la_creacion_antes_del_commit_del_llamador(motor):
    """D-8: el helper no hace commit; un rollback del llamador la descarta."""
    _sembrar_institucion(motor, "INST01")
    with sessionmaker(bind=motor)() as db:
        creado = resolver_departamento_suministros(db, "INST01")
        creado_id = creado.departamento_id
        assert db.get(Departamento, creado_id) is not None
        db.rollback()

    with sessionmaker(bind=motor)() as db:
        assert db.get(Departamento, creado_id) is None
    assert _suministros(motor, "INST01") == []


def test_conflicto_de_unicidad_fuera_de_postgresql_se_propaga(motor, monkeypatch):
    """SQLite no abre savepoint: un conflicto real se propaga al llamador.

    La recuperacion por relectura (D-9) se acredita en PostgreSQL gated (E12-A3),
    que es el unico dialecto donde el savepoint no confirma al liberarse. Aqui se
    fija que, sin savepoint, el helper no intenta una relectura sobre una
    transaccion invalidada: el `IntegrityError` llega al llamador, que decide.
    """
    _sembrar_institucion(motor, "INST01")
    _crear_departamento(
        motor,
        institucion_id="INST01",
        nombre_dep="Suministros",
        descripcion="Ganadora",
    )

    original = departamento_suministros._buscar_departamento_suministros
    llamadas = {"total": 0}

    def _buscar_sin_ver_la_primera_vez(db, institucion_id: str):
        llamadas["total"] += 1
        if llamadas["total"] == 1:
            return None
        return original(db, institucion_id)

    monkeypatch.setattr(
        departamento_suministros,
        "_buscar_departamento_suministros",
        _buscar_sin_ver_la_primera_vez,
    )

    with sessionmaker(bind=motor)() as db:
        with pytest.raises(IntegrityError):
            resolver_departamento_suministros(db, "INST01")
        db.rollback()
    assert llamadas["total"] == 1
    assert len(_suministros(motor, "INST01")) == 1


@pytest.mark.parametrize(
    "nombre, esperado",
    [
        ("Suministros", True),
        (" SUMINISTROS ", True),
        ("suministros", True),
        ("Biblioteca", False),
        ("Suministros especiales", False),
        (None, False),
    ],
)
def test_predicado_de_nombre_suministros(nombre, esperado):
    assert (
        es_departamento_suministros(
            None if nombre is None else Departamento(nombre_dep=nombre)
        )
        is esperado
    )


# ---------------------------------------------------------------------------
# D-12: contrato de los DTOs
# ---------------------------------------------------------------------------


def _datos_usuario(**cambios):
    datos = {
        "nombre": "Ana",
        "apellido": "Perez",
        "correo": "ana.suministros@compustock.cl",
        "departamento_id": 1,
        "rol_id": 1,
    }
    datos.update(cambios)
    return datos


def test_departamento_id_opcional_solo_en_las_entradas():
    assert UsuarioBase.model_fields["departamento_id"].is_required()
    assert UsuarioRespuesta.model_fields["departamento_id"].is_required()
    assert not UsuarioCrear.model_fields["departamento_id"].is_required()
    assert UsuarioCrear.model_fields["departamento_id"].default is None
    assert not UsuarioEdicion.model_fields["departamento_id"].is_required()
    assert UsuarioEdicion.model_fields["departamento_id"].default is None


@pytest.mark.parametrize("esquema", [UsuarioCrear, UsuarioEdicion])
def test_departamento_id_omitido_o_nulo_es_aceptado_por_la_entrada(esquema):
    sin_campo = _datos_usuario()
    sin_campo.pop("departamento_id")
    if esquema is UsuarioEdicion:
        sin_campo.pop("correo")  # la edicion no cambia la clave de identidad
    assert esquema(**sin_campo).departamento_id is None

    con_nulo = _datos_usuario(departamento_id=None)
    if esquema is UsuarioEdicion:
        con_nulo.pop("correo")
    assert esquema(**con_nulo).departamento_id is None


@pytest.mark.parametrize("esquema", [UsuarioCrear, UsuarioEdicion])
@pytest.mark.parametrize("valor", [0, -1])
def test_departamento_id_menor_que_uno_responde_422(esquema, valor):
    datos = _datos_usuario(departamento_id=valor)
    if esquema is UsuarioEdicion:
        datos.pop("correo")
    with pytest.raises(ValidationError) as excinfo:
        esquema(**datos)
    assert any(
        error["loc"] == ("departamento_id",) for error in excinfo.value.errors()
    )


def test_la_respuesta_sigue_exigiendo_departamento():
    datos = _datos_usuario()
    datos.pop("departamento_id")
    with pytest.raises(ValidationError):
        UsuarioRespuesta(**datos, usuario_id=1)


def test_usuario_crear_conserva_extra_forbid():
    with pytest.raises(ValidationError):
        UsuarioCrear(**_datos_usuario(campo_extra=1))
