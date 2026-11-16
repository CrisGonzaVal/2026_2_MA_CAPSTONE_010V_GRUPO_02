"""Soporte de pruebas del limite de tasa (Feature 025).

`AlmacenFalso` reproduce la semantica del script Lua —incremento, expiracion
anclada al primer acierto y TTL restante— con un reloj controlable. No abre
sockets y permite probar el limitador sin Redis.
"""

from dataclasses import dataclass, field


class AlmacenFalso:
    """Doble en memoria con la misma interfaz que `AlmacenRedis`."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.llamadas: list[tuple[str, int]] = []
        self._contadores: dict[str, int] = {}
        self._expira_en: dict[str, float] = {}
        self._ahora = 0.0
        self.cerrado = False

    def avanzar(self, segundos: float) -> None:
        """Mueve el reloj del doble; nunca duerme."""
        self._ahora += segundos

    def _depurar(self, clave: str) -> None:
        expira_en = self._expira_en.get(clave)
        if expira_en is not None and expira_en <= self._ahora:
            del self._expira_en[clave]
            del self._contadores[clave]

    async def registrar(self, clave: str, ventana_ms: int) -> tuple[int, int]:
        self.llamadas.append((clave, ventana_ms))
        if self.error is not None:
            raise self.error

        self._depurar(clave)
        actual = self._contadores.get(clave, 0) + 1
        self._contadores[clave] = actual
        if clave not in self._expira_en:
            self._expira_en[clave] = self._ahora + (ventana_ms / 1000)

        restante_ms = round((self._expira_en[clave] - self._ahora) * 1000)
        return actual, max(0, restante_ms)

    async def cerrar(self) -> None:
        self.cerrado = True


@dataclass(frozen=True)
class Escenario:
    """Datos minimos de un `scope` HTTP para las pruebas unitarias."""

    camino: str = "/api/v1/auth/me"
    metodo: str = "GET"
    ip: str | None = "203.0.113.7"
    cabeceras: dict[str, str] = field(default_factory=dict)

    def como_scope(self) -> dict:
        scope = {
            "type": "http",
            "method": self.metodo,
            "path": self.camino,
            "headers": [
                (nombre.encode("latin-1"), valor.encode("latin-1"))
                for nombre, valor in self.cabeceras.items()
            ],
        }
        if self.ip is not None:
            scope["client"] = (self.ip, 50000)
        return scope


def crear_scope(
    camino: str = "/api/v1/auth/me",
    metodo: str = "GET",
    ip: str | None = "203.0.113.7",
    cabeceras: dict[str, str] | None = None,
) -> dict:
    return Escenario(
        camino=camino,
        metodo=metodo,
        ip=ip,
        cabeceras=cabeceras or {},
    ).como_scope()


def crear_app_con_limite(
    monkeypatch,
    falso: AlmacenFalso,
    maximo: int = 3,
    ventana_segundos: int = 60,
    confiar_proxy: bool = False,
    habilitado: bool = True,
):
    """Construye una app aislada con el limitador cableado al almacen falso.

    Muta el singleton con `monkeypatch` (que lo restaura al terminar la prueba)
    y pasa el falso como costura; nunca usa el singleton `app`.
    """
    from app.core.config import settings as configuracion
    from app.main import crear_app

    monkeypatch.setattr(
        configuracion, "LIMITE_TASA_HABILITADO", habilitado
    )
    monkeypatch.setattr(
        configuracion, "LIMITE_TASA_MAX_PETICIONES", maximo
    )
    monkeypatch.setattr(
        configuracion, "LIMITE_TASA_VENTANA_SEGUNDOS", ventana_segundos
    )
    monkeypatch.setattr(
        configuracion, "LIMITE_TASA_CONFIAR_PROXY", confiar_proxy
    )
    return crear_app(cliente_limite=falso)
