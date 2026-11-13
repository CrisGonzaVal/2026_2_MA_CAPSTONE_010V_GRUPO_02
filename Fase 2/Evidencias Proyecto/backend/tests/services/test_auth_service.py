"""Feature 022, T5: contrato del helper `auth_service.correo_del_actor`.

El helper concentra la regla de auditoría que antes duplicaban
`organizacion_service` y `usuario_service`: si no hay identidad (o no tiene
usuario) el actor es ``sistema``; si la hay, su correo se normaliza con la
regla única de `security.normalizar_correo`.
"""

from app.models import Usuario
from app.services.auth_service import IdentidadAutenticada, correo_del_actor


def test_correo_del_actor_sin_identidad_es_sistema():
    assert correo_del_actor(None) == "sistema"


def test_correo_del_actor_sin_usuario_es_sistema():
    identidad = IdentidadAutenticada(usuario=None, sub="user_123")  # type: ignore[arg-type]

    assert correo_del_actor(identidad) == "sistema"


def test_correo_del_actor_normaliza_el_correo_del_usuario():
    usuario = Usuario(correo="  Admin@Example.COM  ")
    identidad = IdentidadAutenticada(usuario=usuario, sub="user_123")

    assert correo_del_actor(identidad) == "admin@example.com"
