from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

#: Version de la aplicacion publicada en OpenAPI y en la metrica
#: `compustock_app_info`. Conserva el valor que `main.py` ya declaraba.
VERSION_APLICACION = "1.0.0"

#: Version objetivo del DDL de tenant (stack §5). Es la constante
#: de despliegue compartida por el codigo que resuelve el tenant y por la
#: instalacion limpia: el enrutamiento exige **igualdad exacta** contra
#: este token y se incrementa con cada cambio posterior de DDL. La
#: Feature 011 subio el objetivo de `010.1` a `011.1`; la Feature 012 agrego el
#: estado canonico `control.institucion.activo` y las capacidades por institucion
#: (`control.funcion_institucion`) y el estado logico de sede/departamento, asi
#: que el objetivo subio de `011.1` a `012.1`; la Feature 013 agrega el estado
#: `Anulado` al catalogo replicado y la tabla `historial_transicion_ticket` en
#: control y en cada tenant, de modo que el objetivo sube de `012.1` a `013.1`
#: (spec 013, AC-20/AC-21). La Feature 014 agrega el estado reversible
#: `producto.activo`/`categoria.activo` y los dos historiales de transicion del
#: catalogo (`historial_transicion_producto`/`historial_transicion_categoria`)
#: en control y en cada tenant, de modo que el objetivo sube de `013.1` a
#: `014.1` (spec 014, AC-13/AC-14). La Feature 020 agrega el catalogo global de
#: proveedores y las tablas de orden, detalle y factura de compra en control y en
#: cada tenant, ademas de la septima capacidad `compras`, de modo que el objetivo
#: sube de `014.1` a `020.1` (spec 020, AC-2/AC-14). La Feature 021 agrega la tabla
#: `orden_compra_ticket` y la columna `historial_transicion_ticket.orden_compra_id`
#: en control y en cada tenant, de modo que el objetivo sube de `020.1` a `021.1`
#: (spec 021, AC-6/AC-11).
VERSION_ESQUEMA_OBJETIVO = "021.1"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    DB_USER: str = "postgres"
    DB_PASSWORD: str = "postgres"
    DB_HOST: str = "localhost"
    DB_PORT: str = "5432"
    DB_NAME: str = "apt_erp"
    CLERK_PUBLISHABLE_KEY: str = ""
    CLERK_SECRET_KEY: str = ""
    CLERK_ISSUER: str = ""

    # Feature 024 (D-6): CORS por entorno con lista explicita y sin comodines.
    # Default solo para desarrollo local (4200 dev server, 8080 nginx).
    ALLOWED_ORIGINS: str = "http://localhost:4200,http://localhost:8080"
    # Feature 024 (R-2): nivel y formato del logging estructurado. Un valor
    # desconocido no rompe el arranque: `core/observabilidad.py` lo normaliza.
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"

    @field_validator("ALLOWED_ORIGINS")
    @classmethod
    def validar_origenes(cls, valor: str) -> str:
        """Recorta espacios y descarta entradas vacias; exige al menos un origen.

        Un `ALLOWED_ORIGINS=""` dejaria la SPA rota con un error de CORS en el
        navegador y un 200 del backend, el diagnostico mas caro de encontrar.
        Fallar al arrancar es mas barato que un fallback silencioso.
        """
        origenes = [origen.strip() for origen in valor.split(",") if origen.strip()]
        if not origenes:
            raise ValueError(
                "ALLOWED_ORIGINS no puede quedar vacio: declare al menos un "
                "origen explicito separado por comas."
            )
        return ",".join(origenes)

    @property
    def origenes_permitidos(self) -> list[str]:
        return [
            origen.strip()
            for origen in self.ALLOWED_ORIGINS.split(",")
            if origen.strip()
        ]

    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql+psycopg2://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"


settings = Settings()
