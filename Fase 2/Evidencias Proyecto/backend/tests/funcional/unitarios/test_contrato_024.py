"""AC-15/AC-23/AC-44/AC-45/AC-49: contrato y matriz de la consolidacion final.

Ampliacion 25/Nov/2026: la aprobacion del Administrador (T21) y la confirmacion
de entrega del Solicitante (T22) suman **dos** operaciones v1 (73 -> 75; 75 -> 77
entradas con `GET /` y `/health`), y el `PATCH /estado` de legado pasa a ser
**solo** del Administrador. Esta tarea (T24) fija el recuento final y los roles
del contrato: la matriz tiene 75 operaciones, `/openapi.json` publica 75 v1 y 77
entradas, y las operaciones propias del Bodeguero (despacho y rechazo) conservan
sus roles.
"""

from app.core import capacidades, permisos

METODOS = {"get", "post", "put", "patch", "delete", "options", "head", "trace"}

RUTA_APROBACION = "/api/v1/tickets/{ticket_id}/aprobacion"
RUTA_CONFIRMACION = "/api/v1/tickets/{ticket_id}/confirmacion-entrega"
RUTA_ESTADO = "/api/v1/tickets/{ticket_id}/estado"
RUTA_DESPACHO = "/api/v1/tickets/{ticket_id}/despacho"
RUTA_RECHAZO = "/api/v1/tickets/{ticket_id}/rechazo"

CIERRE_RESERVADO = (
    "El cierre requiere despacho; use POST "
    "/api/v1/tickets/{ticket_id}/despacho"
)


def _operaciones(esquema: dict):
    for ruta, metodos in esquema["paths"].items():
        for metodo, operacion in metodos.items():
            if metodo.lower() in METODOS:
                yield ruta, metodo.lower(), operacion


def test_openapi_publica_77_operaciones(cliente):
    esquema = cliente.get("/openapi.json").json()

    rutas = list(_operaciones(esquema))
    assert len(rutas) == 77
    negocio = [ruta for ruta, _, _ in rutas if ruta.startswith("/api/v1")]
    assert len(negocio) == 75
    assert sorted(ruta for ruta, _, _ in rutas if not ruta.startswith("/api/v1")) == [
        "/",
        "/health",
    ]


def test_rutas_operativas_no_aparecen_en_openapi(cliente):
    esquema = cliente.get("/openapi.json").json()

    assert "/metrics" not in esquema["paths"]
    assert "/ready" not in esquema["paths"]


def test_health_sigue_documentado_sin_security(cliente):
    esquema = cliente.get("/openapi.json").json()

    operacion = esquema["paths"]["/health"]["get"]
    assert "security" not in operacion
    assert "responses" in operacion


def test_matriz_conserva_75_operaciones_y_ninguna_ruta_operativa():
    assert len(permisos.MATRIZ_PERMISOS) == 75
    assert not any(
        ruta in ("/metrics", "/ready")
        for _, ruta in permisos.MATRIZ_PERMISOS
    )


def test_matriz_fija_los_roles_de_la_ampliacion_ac_44_ac_49():
    """AC-44/AC-45/AC-49: dos operaciones nuevas y el PATCH solo Administrador."""
    assert permisos.roles_de_operacion("POST", RUTA_APROBACION) == frozenset(
        {"Administrador"}
    )
    assert permisos.roles_de_operacion("POST", RUTA_CONFIRMACION) == frozenset(
        {"Solicitante"}
    )
    assert permisos.roles_de_operacion("PATCH", RUTA_ESTADO) == frozenset(
        {"Administrador"}
    )
    # AC-49: el Bodeguero conserva despacho y rechazo, que no son el PATCH.
    assert permisos.roles_de_operacion("POST", RUTA_DESPACHO) == frozenset(
        {"Administrador", "Bodeguero"}
    )
    assert permisos.roles_de_operacion("POST", RUTA_RECHAZO) == frozenset(
        {"Administrador", "Bodeguero"}
    )


def test_capacidades_de_la_ampliacion_ac_44():
    """AC-44: la aprobacion se gatea con `kanban` y la confirmacion con `tickets`."""
    assert capacidades.capacidad_de_operacion("POST", RUTA_APROBACION) == "kanban"
    assert capacidades.capacidad_de_operacion("POST", RUTA_CONFIRMACION) == "tickets"


def test_openapi_publica_la_ampliacion_sin_cuerpo_y_con_sus_codigos_ac_44(cliente):
    """AC-44/AC-45/AC-46: las dos operaciones nuevas no tienen `requestBody`.

    Las respuestas 401/403/404/409 son contractuales; el 422 es el que FastAPI
    agrega por el `ticket_id` del path, no por un cuerpo obligatorio.
    """
    esquema = cliente.get("/openapi.json").json()
    for ruta, rol in (
        (RUTA_APROBACION, "Administrador"),
        (RUTA_CONFIRMACION, "Solicitante"),
    ):
        operacion = esquema["paths"][ruta]["post"]
        assert "requestBody" not in operacion, ruta
        assert {"200", "401", "403", "404", "409"} <= set(
            operacion["responses"]
        ), ruta
        assert "422" in operacion["responses"], ruta
        assert rol in operacion["description"], ruta


def test_openapi_del_patch_de_legado_es_solo_administrador_ac_49(cliente):
    """AC-49: un paso y cierre reservado, sin roles ni destinos previos."""
    esquema = cliente.get("/openapi.json").json()
    descripcion = esquema["paths"][RUTA_ESTADO]["patch"]["description"]

    assert "Administrador" in descripcion
    assert "Bodeguero" not in descripcion
    assert "auto-avance" not in descripcion.lower()
    assert "destino efectivo" not in descripcion.lower()
    assert "un paso" in descripcion
    assert CIERRE_RESERVADO in descripcion


def test_openapi_conserva_despacho_y_rechazo_ac_49(cliente):
    """AC-49: despacho y rechazo siguen publicados y con sus roles intactos."""
    esquema = cliente.get("/openapi.json").json()
    for ruta in (RUTA_DESPACHO, RUTA_RECHAZO):
        assert "post" in esquema["paths"].get(ruta, {}), ruta
        assert permisos.roles_de_operacion("POST", ruta) == frozenset(
            {"Administrador", "Bodeguero"}
        ), ruta
