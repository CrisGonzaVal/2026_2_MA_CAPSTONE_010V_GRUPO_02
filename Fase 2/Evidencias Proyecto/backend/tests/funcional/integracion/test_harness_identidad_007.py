"""Harness de identidad mutable de la enmienda 007 (26/Nov/2026, E26N-1).

Estas pruebas no adelantan la regla de alta exclusiva del Solicitante (E26N-2):
solo fijan que un mismo `TestClient` puede alternar roles con `actuar_como`,
que las identidades persistidas de Bodeguero y Solicitante se crean una sola
vez y que los overrides del cliente se restauran sin un `clear()` global.

El seam sigue siendo la interfaz HTTP: la alternancia se observa en
`/auth/me`, que relee el usuario real por `usuario_id`, y en una operacion de
negocio vigente (`GET /tickets/`) que hoy admite a los tres roles.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.api import dependencies
from app.main import app
from app.models import Rol, Usuario
from tests.conftest import _cliente_de_prueba


def _contar_usuarios(motor, *, rol_id: int, departamento_id: int) -> int:
    """Cuenta usuarios persistidos con un rol en un departamento."""
    with sessionmaker(bind=motor)() as db:
        return db.execute(
            select(func.count())
            .select_from(Usuario)
            .where(
                Usuario.rol_id == rol_id,
                Usuario.departamento_id == departamento_id,
            )
        ).scalar_one()


def test_actuar_como_alterna_solicitante_y_administrador_en_el_mismo_cliente(
    cliente, actuar_como, datos_base
):
    """El mismo `TestClient` responde como Solicitante y luego como Administrador."""
    identidad_solicitante = actuar_como("Solicitante")
    respuesta = cliente.get("/api/v1/auth/me")

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["rol"] == "Solicitante"
    assert cuerpo["usuario_id"] == datos_base["usuario_solicitante_id"]
    assert (
        identidad_solicitante.usuario.usuario_id
        == datos_base["usuario_solicitante_id"]
    )

    # Operacion de negocio vigente: la lectura de tickets admite al Solicitante.
    listado = cliente.get("/api/v1/tickets/")
    assert listado.status_code == 200, listado.text

    identidad_administrador = actuar_como("Administrador")
    respuesta_admin = cliente.get("/api/v1/auth/me")

    assert respuesta_admin.status_code == 200, respuesta_admin.text
    cuerpo_admin = respuesta_admin.json()
    assert cuerpo_admin["rol"] == "Administrador"
    assert cuerpo_admin["usuario_id"] == datos_base["usuario_id"]
    assert (
        identidad_administrador.usuario.usuario_id == datos_base["usuario_id"]
    )


def test_identidad_persistida_es_idempotente_y_expone_los_ids(
    motor, datos_base, actuar_como
):
    """Dos cambios al mismo rol reutilizan usuario y rol; no duplican filas."""
    primera_solicitante = actuar_como("Solicitante")
    segunda_solicitante = actuar_como("Solicitante")

    assert (
        primera_solicitante.usuario.usuario_id
        == segunda_solicitante.usuario.usuario_id
        == datos_base["usuario_solicitante_id"]
    )
    assert _contar_usuarios(
        motor,
        rol_id=datos_base["rol_solicitante_id"],
        departamento_id=datos_base["departamento_id"],
    ) == 1
    with sessionmaker(bind=motor)() as db:
        rol = db.get(Rol, datos_base["rol_solicitante_id"])
        assert rol is not None and rol.nombre_rol == "Solicitante"

    primera_bodeguero = actuar_como("Bodeguero")
    segunda_bodeguero = actuar_como("Bodeguero")

    assert (
        primera_bodeguero.usuario.usuario_id
        == segunda_bodeguero.usuario.usuario_id
        == datos_base["usuario_bodeguero_id"]
    )
    assert _contar_usuarios(
        motor,
        rol_id=datos_base["rol_bodeguero_id"],
        departamento_id=datos_base["departamento_id"],
    ) == 1


def test_cliente_solicitante_comparte_el_cliente_y_deja_el_contenedor_en_solicitante(
    cliente, cliente_solicitante, datos_base
):
    """La conveniencia devuelve el mismo cliente y la identidad ya cambiada."""
    assert cliente_solicitante is cliente

    respuesta = cliente_solicitante.get("/api/v1/auth/me")
    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["rol"] == "Solicitante"
    assert cuerpo["usuario_id"] == datos_base["usuario_solicitante_id"]


def test_el_cliente_restaura_los_overrides_que_instala(motor):
    """Un cliente anidado no borra los overrides previos (DT-4, sin `clear()`)."""

    def identidad_externa() -> None:
        return None

    def base_externa() -> None:
        return None

    app.dependency_overrides[dependencies.get_current_user] = identidad_externa
    app.dependency_overrides[dependencies.get_db] = base_externa
    try:
        with _cliente_de_prueba(motor):
            assert (
                app.dependency_overrides[dependencies.get_current_user]
                is not identidad_externa
            )
            assert app.dependency_overrides[dependencies.get_db] is not base_externa

        assert (
            app.dependency_overrides[dependencies.get_current_user]
            is identidad_externa
        )
        assert app.dependency_overrides[dependencies.get_db] is base_externa
        assert (
            dependencies.obtener_verificador_correo_clerk
            not in app.dependency_overrides
        )
    finally:
        app.dependency_overrides.pop(dependencies.get_current_user, None)
        app.dependency_overrides.pop(dependencies.get_db, None)
