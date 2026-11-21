"""AC-15 y AC-23: el contrato y la matriz no cambian con las rutas operativas."""

from app.core import permisos

METODOS = {"get", "post", "put", "patch", "delete", "options", "head", "trace"}


def _operaciones(esquema: dict):
    for ruta, metodos in esquema["paths"].items():
        for metodo, operacion in metodos.items():
            if metodo.lower() in METODOS:
                yield ruta, metodo.lower(), operacion


def test_openapi_publica_75_operaciones(cliente):
    esquema = cliente.get("/openapi.json").json()

    rutas = list(_operaciones(esquema))
    assert len(rutas) == 75
    negocio = [ruta for ruta, _, _ in rutas if ruta.startswith("/api/v1")]
    assert len(negocio) == 73
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


def test_matriz_conserva_73_operaciones_y_ninguna_ruta_operativa():
    assert len(permisos.MATRIZ_PERMISOS) == 73
    assert not any(
        ruta in ("/metrics", "/ready")
        for _, ruta in permisos.MATRIZ_PERMISOS
    )
