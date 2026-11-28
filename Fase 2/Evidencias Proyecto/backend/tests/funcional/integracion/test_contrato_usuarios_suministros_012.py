"""E12-A3 (enmienda 012): contrato y OpenAPI del alta/edicion por rol.

Seam bajo prueba: la **interfaz publica** del contrato.

* Pydantic v2: `departamento_id` es opcional **solo** en la entrada
  (`UsuarioCrear`/`UsuarioEdicion`) y obligatorio en `UsuarioRespuesta`
  (D-12/AC-23); cuando viene, `ge=1` (0/negativo -> 422 para todos).
* `/openapi.json`: la entrada publica el campo como `integer(min 1)` o `null`,
  conserva `extra="forbid"`, documenta el **422 por rol** y por «Suministros»,
  y mantiene los conteos vigentes del Bloque B: **75** operaciones totales =
  **73 v1 + `GET /` + `/health`**, con la matriz central en **73** (AC-35).
* Regresion del Bloque A: `PUT /organizacion/usuarios/{usuario_id}/sede`
  conserva el **409** a no-Bodeguero y `gestion_organizacional` sigue gateando
  sedes, departamentos y usuarios (AC-30).

La concurrencia de «Suministros» no se acredita aqui: SQLite no la reproduce y
vive en el gated `tests/funcional/sistema/test_suministros_postgres_012.py`.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.core import capacidades, permisos
from app.core.config import VERSION_ESQUEMA_OBJETIVO
from app.models import (
    CAPACIDADES,
    FuncionInstitucion,
    MapaUsuarioEsquema,
    Usuario,
    VersionEsquema,
)
from app.schemas.usuario_schema import (
    UsuarioCrear,
    UsuarioEdicion,
    UsuarioEdicionConMotivo,
    UsuarioRespuesta,
)
from tests.funcional.integracion._soporte_sede_011 import crear_sede

METODOS = {"get", "post", "put", "patch", "delete", "options", "head", "trace"}

RUTA_USUARIOS = "/api/v1/usuarios/"
RUTA_USUARIO = "/api/v1/usuarios/{usuario_id}"
RUTA_SEDE_USUARIO = "/api/v1/organizacion/usuarios/{usuario_id}/sede"
RUTA_SEDES = "/api/v1/organizacion/sedes"
RUTA_DEPARTAMENTOS = "/api/v1/organizacion/departamentos"

#: Operaciones organizacionales que conservan `gestion_organizacional` (D-17).
OPERACIONES_GESTION = (
    ("GET", RUTA_SEDES),
    ("POST", RUTA_SEDES),
    ("PUT", "/api/v1/organizacion/sedes/{sede_id}"),
    ("PATCH", "/api/v1/organizacion/sedes/{sede_id}/estado"),
    ("GET", RUTA_DEPARTAMENTOS),
    ("POST", RUTA_DEPARTAMENTOS),
    ("PUT", "/api/v1/organizacion/departamentos/{departamento_id}"),
    ("PATCH", "/api/v1/organizacion/departamentos/{departamento_id}/estado"),
    ("PUT", "/api/v1/organizacion/departamentos/{departamento_id}/sede"),
    ("GET", RUTA_USUARIOS),
    ("POST", RUTA_USUARIOS),
    ("PUT", RUTA_USUARIO),
    ("PATCH", "/api/v1/usuarios/{usuario_id}/estado"),
    ("PUT", RUTA_SEDE_USUARIO),
)


# ---------------------------------------------------------------------------
# Contrato Pydantic v2
# ---------------------------------------------------------------------------


def test_usuario_crear_hace_opcional_el_departamento_y_la_respuesta_lo_exige():
    """AC-23/D-12: opcional solo en la entrada; `UsuarioRespuesta` lo exige."""
    assert UsuarioCrear.model_fields["departamento_id"].is_required() is False
    assert UsuarioEdicion.model_fields["departamento_id"].is_required() is False
    assert UsuarioEdicionConMotivo.model_fields["departamento_id"].is_required() is False
    assert UsuarioRespuesta.model_fields["departamento_id"].is_required() is True

    # Feature 027: `extra="forbid"` se conserva en las entradas.
    assert UsuarioCrear.model_config.get("extra") == "forbid"
    assert UsuarioEdicion.model_config.get("extra") == "forbid"
    assert UsuarioEdicionConMotivo.model_config.get("extra") == "forbid"


def test_esquema_de_entrada_admite_entero_minimo_1_o_nulo():
    """AC-23/D-12: `integer(min 1)` o `null`; 0/negativo se rechaza."""
    for modelo in (UsuarioCrear, UsuarioEdicion):
        esquema = modelo.model_json_schema()
        departamento = esquema["properties"]["departamento_id"]
        variantes = departamento.get("anyOf", [departamento])
        tipos = {variante.get("type") for variante in variantes}
        assert tipos == {"integer", "null"}, (modelo.__name__, variantes)
        entero = next(
            variante for variante in variantes if variante.get("type") == "integer"
        )
        assert entero.get("minimum") == 1, (modelo.__name__, entero)
        assert esquema.get("additionalProperties") is False, modelo.__name__

    valido = UsuarioCrear(
        nombre="Ada",
        apellido="Entrada",
        correo="ada.entrada@compustock.cl",
        departamento_id=None,
        rol_id=1,
    )
    assert valido.departamento_id is None

    for invalido in (0, -1):
        with pytest.raises(ValidationError):
            UsuarioCrear(
                nombre="Ada",
                apellido="Entrada",
                correo="ada.entrada@compustock.cl",
                departamento_id=invalido,
                rol_id=1,
            )


# ---------------------------------------------------------------------------
# OpenAPI: 75 = 73 v1 + dos rutas tecnicas; matriz 73; sin encargados
# ---------------------------------------------------------------------------


def _operaciones(esquema: dict):
    for ruta, metodos in esquema["paths"].items():
        for metodo, operacion in metodos.items():
            if metodo.lower() in METODOS:
                yield ruta, metodo.lower(), operacion


def test_openapi_publica_75_operaciones_73_v1_y_matriz_73(cliente):
    """AC-35: 75 totales = 73 v1 + `GET /` + `/health`; matriz 73."""
    esquema = cliente.get("/openapi.json").json()

    operaciones = list(_operaciones(esquema))
    assert len(operaciones) == 75, len(operaciones)
    v1 = [ruta for ruta, _, _ in operaciones if ruta.startswith("/api/v1")]
    assert len(v1) == 73, len(v1)
    assert sorted(ruta for ruta, _, _ in operaciones if not ruta.startswith("/api/v1")) == [
        "/",
        "/health",
    ]
    assert len(permisos.MATRIZ_PERMISOS) == 73


def test_openapi_y_matriz_no_publican_las_rutas_de_encargados(cliente):
    """AC-35/D-17: las 3 rutas retiradas no existen en el contrato ni en la matriz."""
    esquema = cliente.get("/openapi.json").json()

    assert not any("encargados" in ruta for ruta in esquema["paths"])
    assert not any(
        "encargados" in ruta for _, ruta in permisos.MATRIZ_PERMISOS
    )


def test_openapi_publica_el_departamento_opcional_en_las_entradas(cliente):
    """AC-23: el contrato de entrada coincide con el DTO (no lo endurece)."""
    esquema = cliente.get("/openapi.json").json()
    componentes = esquema["components"]["schemas"]

    for nombre in ("UsuarioCrear", "UsuarioEdicionConMotivo"):
        componente = componentes[nombre]
        assert "departamento_id" not in componente.get("required", []), nombre
        variantes = componente["properties"]["departamento_id"].get("anyOf", [])
        assert {variante.get("type") for variante in variantes} == {
            "integer",
            "null",
        }, (nombre, variantes)
        assert componente.get("additionalProperties") is False, nombre

    assert "departamento_id" in componentes["UsuarioRespuesta"].get("required", [])


def test_openapi_documenta_el_422_por_rol_y_por_suministros(cliente):
    """AC-23/D-12: el 422 por rol ausente y por «Suministros» es contractual."""
    esquema = cliente.get("/openapi.json").json()

    for ruta, metodo in ((RUTA_USUARIOS, "post"), (RUTA_USUARIO, "put")):
        respuestas = esquema["paths"][ruta][metodo]["responses"]
        assert "422" in respuestas, (metodo, ruta)
        descripcion = respuestas["422"]["description"]
        assert "departamento" in descripcion.lower(), (metodo, ruta, descripcion)
        assert "Suministros" in descripcion, (metodo, ruta, descripcion)
        assert "Bodeguero" in descripcion, (metodo, ruta, descripcion)


# ---------------------------------------------------------------------------
# Regresion: 409 de `PUT .../sede` y gating `gestion_organizacional`
# ---------------------------------------------------------------------------


def test_put_sede_conserva_el_409_para_no_bodeguero(
    motor, dos_instituciones, cliente, actuar_como
):
    """AC-30: la sede solo se asigna a un Bodeguero; otro rol -> 409 sin mutar."""
    sede_id = crear_sede(
        motor, institucion_id=dos_instituciones["inst_propia"], nombre="Sede 409"
    )
    solicitante_id = dos_instituciones["usuarios_inst01"]["Solicitante"]

    actuar_como("Administrador")
    respuesta = cliente.put(
        RUTA_SEDE_USUARIO.format(usuario_id=solicitante_id),
        json={"sede_id": sede_id},
    )

    assert respuesta.status_code == 409, respuesta.text
    with sessionmaker(bind=motor)() as db:
        assert db.get(Usuario, solicitante_id).sede_id is None

    assert permisos.roles_de_operacion("PUT", RUTA_SEDE_USUARIO) == frozenset(
        {"Administrador"}
    )


def _sembrar_capacidad_apagada(motor, datos, correo: str) -> None:
    """Control coherente con `gestion_organizacional` apagada para INST01."""
    institucion_id = datos["inst_propia"]
    with sessionmaker(bind=motor)() as db:
        if db.get(MapaUsuarioEsquema, correo) is None:
            db.add(
                MapaUsuarioEsquema(
                    correo=correo,
                    institucion_id=institucion_id,
                    nombre_esquema="tenant_inst01",
                    activo=True,
                )
            )
            db.flush()
        if db.execute(select(VersionEsquema)).scalars().first() is None:
            db.add(VersionEsquema(version=VERSION_ESQUEMA_OBJETIVO))
        for funcion in CAPACIDADES:
            fila = db.get(FuncionInstitucion, (institucion_id, funcion))
            habilitada = funcion != "gestion_organizacional"
            if fila is None:
                db.add(
                    FuncionInstitucion(
                        institucion_id=institucion_id,
                        funcion=funcion,
                        habilitada=habilitada,
                    )
                )
            else:
                fila.habilitada = habilitada
        db.commit()


def test_gestion_organizacional_sigue_gateando_las_tres_superficies(
    motor, dos_instituciones, cliente, actuar_como
):
    """AC-30/D-17: la capacidad se conserva y bloquea sedes/departamentos/usuarios."""
    for metodo, ruta in OPERACIONES_GESTION:
        assert capacidades.capacidad_de_operacion(metodo, ruta) == (
            "gestion_organizacional"
        ), (metodo, ruta)
        assert (metodo, ruta) in permisos.MATRIZ_PERMISOS, (metodo, ruta)

    _sembrar_capacidad_apagada(
        motor, dos_instituciones, dos_instituciones["correo_usado"]
    )
    actuar_como("Administrador")

    assert cliente.get(RUTA_SEDES).status_code == 403
    assert cliente.get(RUTA_DEPARTAMENTOS).status_code == 403
    assert cliente.get(RUTA_USUARIOS).status_code == 403
