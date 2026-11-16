"""Pruebas de API del limite de tasa distribuido (Feature 025).

Verifican el conteo por IP, el contrato del 429, la conservacion de CORS y
`X-Request-ID`, el alcance de `/api/v1`, el preflight sin presupuesto, la
confianza en `X-Real-IP`, el estado compartido entre apps y el apagado por
configuracion. Cada prueba construye su propia app con un almacen falso.
"""

import uuid

from fastapi.testclient import TestClient

from app.api import dependencies
from app.core.limite_tasa import TEXTO_LIMITE
from tests.soporte_limite_tasa_025 import AlmacenFalso, crear_app_con_limite

RUTA = "/api/v1/auth/me"
ORIGEN = "http://localhost:4200"
METODOS_CORS = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
CABECERAS_CORS = "Authorization, Content-Type, Accept"


def test_permite_tres_y_la_cuarta_responde_429(monkeypatch):
    falso = AlmacenFalso()
    aplicacion = crear_app_con_limite(monkeypatch, falso, maximo=3)

    with TestClient(aplicacion) as cliente:
        estados = [cliente.get(RUTA).status_code for _ in range(4)]

    assert estados == [401, 401, 401, 429]


def test_el_429_cumple_el_contrato_y_conserva_la_correlacion(monkeypatch):
    falso = AlmacenFalso()
    aplicacion = crear_app_con_limite(monkeypatch, falso, maximo=3)

    with TestClient(aplicacion) as cliente:
        for _ in range(3):
            cliente.get(RUTA)
        respuesta = cliente.get(RUTA, headers={"Origin": ORIGEN})

    assert respuesta.status_code == 429
    assert respuesta.headers["content-type"].startswith("application/json")
    assert respuesta.json() == {"detail": TEXTO_LIMITE}

    retry_after = int(respuesta.headers["retry-after"])
    reinicio = int(respuesta.headers["x-ratelimit-reset"])
    assert 1 <= retry_after <= 60
    assert reinicio == retry_after
    assert respuesta.headers["x-ratelimit-limit"] == "3"
    assert respuesta.headers["x-ratelimit-remaining"] == "0"

    identificador = respuesta.headers["x-request-id"]
    assert str(uuid.UUID(identificador)) == identificador
    assert respuesta.headers["access-control-allow-origin"] == ORIGEN


def test_el_429_de_un_origen_ajeno_no_lleva_acao(monkeypatch):
    falso = AlmacenFalso()
    aplicacion = crear_app_con_limite(monkeypatch, falso, maximo=1)

    with TestClient(aplicacion) as cliente:
        cliente.get(RUTA)
        respuesta = cliente.get(
            RUTA, headers={"Origin": "http://evil.example"}
        )

    assert respuesta.status_code == 429
    assert "access-control-allow-origin" not in respuesta.headers


def test_una_peticion_permitida_no_anade_cabeceras_del_limite(monkeypatch):
    falso = AlmacenFalso()
    aplicacion = crear_app_con_limite(monkeypatch, falso, maximo=3)

    with TestClient(aplicacion) as cliente:
        respuesta = cliente.get(RUTA)

    assert respuesta.status_code == 401
    assert not any(
        nombre.startswith("x-ratelimit") for nombre in respuesta.headers
    )


def test_con_confianza_cada_x_real_ip_tiene_su_propio_presupuesto(monkeypatch):
    falso = AlmacenFalso()
    aplicacion = crear_app_con_limite(
        monkeypatch, falso, maximo=2, confiar_proxy=True
    )

    with TestClient(aplicacion) as cliente:
        primera = cliente.get(RUTA, headers={"X-Real-IP": "198.51.100.1"})
        segunda = cliente.get(RUTA, headers={"X-Real-IP": "198.51.100.1"})
        tercera = cliente.get(RUTA, headers={"X-Real-IP": "198.51.100.1"})
        otra_ip = cliente.get(RUTA, headers={"X-Real-IP": "198.51.100.2"})

    assert [primera.status_code, segunda.status_code] == [401, 401]
    assert tercera.status_code == 429
    assert otra_ip.status_code == 401


def test_sin_confianza_dos_x_real_ip_comparten_el_par_tcp(monkeypatch):
    falso = AlmacenFalso()
    aplicacion = crear_app_con_limite(
        monkeypatch, falso, maximo=2, confiar_proxy=False
    )

    with TestClient(aplicacion) as cliente:
        estados = [
            cliente.get(RUTA, headers={"X-Real-IP": "198.51.100.1"}).status_code,
            cliente.get(RUTA, headers={"X-Real-IP": "198.51.100.2"}).status_code,
            cliente.get(RUTA, headers={"X-Real-IP": "198.51.100.3"}).status_code,
        ]

    assert estados == [401, 401, 429]


def test_el_preflight_no_consume_presupuesto(monkeypatch):
    falso = AlmacenFalso()
    aplicacion = crear_app_con_limite(monkeypatch, falso, maximo=120)

    with TestClient(aplicacion) as cliente:
        preflight = cliente.options(
            RUTA,
            headers={
                "Origin": ORIGEN,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )
        assert falso.llamadas == []

        estados = [cliente.get(RUTA).status_code for _ in range(120)]
        rechazada = cliente.get(RUTA)

    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == ORIGEN
    assert preflight.headers["access-control-allow-methods"] == METODOS_CORS
    assert preflight.headers["access-control-allow-headers"] == CABECERAS_CORS
    assert preflight.headers["access-control-allow-credentials"] == "true"
    assert estados == [401] * 120
    assert rechazada.status_code == 429


def test_las_rutas_fuera_de_api_v1_no_se_limitan(monkeypatch, motor):
    falso = AlmacenFalso()
    aplicacion = crear_app_con_limite(monkeypatch, falso, maximo=1)
    aplicacion.dependency_overrides[dependencies.obtener_motor_readiness] = (
        lambda: motor
    )

    with TestClient(aplicacion) as cliente:
        for ruta in ["/", "/health", "/ready", "/metrics", "/docs", "/redoc",
                     "/openapi.json"]:
            for _ in range(200):
                assert cliente.get(ruta).status_code == 200
        assert falso.llamadas == []
        inexistente = cliente.get("/api/v1/inexistente")

    assert inexistente.status_code == 404
    assert len(falso.llamadas) == 1


def test_un_post_consume_presupuesto_igual_que_un_get(monkeypatch):
    falso = AlmacenFalso()
    aplicacion = crear_app_con_limite(monkeypatch, falso, maximo=1)

    with TestClient(aplicacion) as cliente:
        post = cliente.post(RUTA)
        get = cliente.get(RUTA)

    assert [post.status_code, get.status_code] == [405, 429]


def test_dos_apps_comparten_el_estado_del_almacen(monkeypatch):
    falso = AlmacenFalso()
    primera_app = crear_app_con_limite(monkeypatch, falso, maximo=3)
    segunda_app = crear_app_con_limite(monkeypatch, falso, maximo=3)

    with TestClient(primera_app) as cliente_uno, TestClient(
        segunda_app
    ) as cliente_dos:
        estados = [
            cliente_uno.get(RUTA).status_code,
            cliente_uno.get(RUTA).status_code,
            cliente_dos.get(RUTA).status_code,
            cliente_dos.get(RUTA).status_code,
        ]

    assert estados == [401, 401, 401, 429]


def test_con_el_limitador_apagado_no_hay_middleware_ni_llamadas(monkeypatch):
    falso = AlmacenFalso()
    aplicacion = crear_app_con_limite(
        monkeypatch, falso, maximo=1, habilitado=False
    )

    with TestClient(aplicacion) as cliente:
        respuesta = cliente.get(RUTA)

    assert respuesta.status_code == 401
    assert falso.llamadas == []
