from pathlib import Path
from urllib.parse import quote

from pydantic import field_validator, model_validator
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
#: (spec 021, AC-6/AC-11). La Feature 026 retira la tabla `inventario` (el saldo
#: vigente es `stock_sede`), anade indices P0 y restricciones de dominio, de modo
#: que el objetivo sube a `026.0` (spec 026, AC-13/AC-14).
VERSION_ESQUEMA_OBJETIVO = "026.0"


#: Raiz de `backend/`. Localiza los `.env` sin depender del directorio desde el
#: que se lanza `uvicorn`; en la imagen Docker ninguno existe y toda la
#: configuracion llega por variables de entorno (docker compose, Render, Neon).
DIRECTORIO_BACKEND = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    # El `.env` del backend manda sobre el de la raiz: el de la raiz alimenta a
    # docker compose (interpolacion y Clerk) y el del backend fija la conexion
    # cuando se levanta uvicorn desde el host. Las variables del proceso
    # (contenedor, Render, CI) siempre ganan a ambos archivos.
    model_config = SettingsConfigDict(
        env_file=(DIRECTORIO_BACKEND.parent / ".env", DIRECTORIO_BACKEND / ".env"),
        env_file_encoding="utf-8",
    )

    # Conexion a PostgreSQL. `config.py` no guarda ningun valor: los pone el
    # `.env` de la raiz en local, docker compose en el contenedor y Render/Neon
    # en la nube. Si definen los cuatro componentes (la contrasena puede ir
    # vacia) se compone la URL; si falta alguno, `app.db.database` falla con un
    # mensaje accionable en vez de inventar una conexion.
    DB_USER: str = ""
    DB_PASSWORD: str = ""
    DB_HOST: str = ""
    DB_PORT: str = ""
    DB_NAME: str = ""

    #: Cadena completa de conexion (Neon, Render, VPS). Si esta definida tiene
    #: prioridad sobre los componentes `DB_*`: en Neon basta pegar la que entrega
    #: el panel, incluido `?sslmode=require`.
    #: Se llama `DB_URL` y no `DATABASE_URL` a proposito: esa ultima es una
    #: variable generica que otros proyectos de la maquina pueden tener definida
    #: (aqui apunta a otra base) y el proceso la heredaria en silencio.
    DB_URL: str = ""

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

    # Feature 025 (D-8): limite de tasa distribuido con Redis.
    REDIS_URL: str = "redis://127.0.0.1:6380/0"
    LIMITE_TASA_HABILITADO: bool = True
    LIMITE_TASA_MAX_PETICIONES: int = 120
    LIMITE_TASA_VENTANA_SEGUNDOS: int = 60
    LIMITE_TASA_CONFIAR_PROXY: bool = False

    @field_validator("LIMITE_TASA_MAX_PETICIONES", "LIMITE_TASA_VENTANA_SEGUNDOS")
    @classmethod
    def validar_limite_positivo(cls, valor: int) -> int:
        """Un maximo o una ventana no positivos romperian el limitador."""
        if valor < 1:
            raise ValueError(
                "LIMITE_TASA_MAX_PETICIONES y LIMITE_TASA_VENTANA_SEGUNDOS "
                "deben ser enteros mayores o iguales a 1."
            )
        return valor

    @model_validator(mode="after")
    def validar_url_redis(self):
        """Solo exige esquema Redis cuando el limitador va a conectarse."""
        if self.LIMITE_TASA_HABILITADO and not self.REDIS_URL.startswith(
            ("redis://", "rediss://")
        ):
            raise ValueError(
                "REDIS_URL debe empezar por redis:// o rediss:// cuando "
                "LIMITE_TASA_HABILITADO esta activo."
            )
        return self

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

    @field_validator("DB_URL")
    @classmethod
    def normalizar_cadena_base_datos(cls, valor: str) -> str:
        """Acepta el esquema `postgres://` que entregan algunos proveedores.

        SQLAlchemy 2 solo reconoce `postgresql`/`postgresql+psycopg2`; una URL
        copiada tal cual de Neon o Render con `postgres://` romperia al crear el
        motor con `NoSuchModuleError`.
        """
        valor = valor.strip()
        if valor.startswith("postgres://"):
            return "postgresql+psycopg2://" + valor.removeprefix("postgres://")
        return valor

    @model_validator(mode="after")
    def completar_cadena_base_datos(self):
        """Compone la URL desde `DB_*` cuando estan los cuatro componentes."""
        if self.DB_URL:
            return self
        if all((self.DB_USER, self.DB_HOST, self.DB_PORT, self.DB_NAME)):
            self.DB_URL = (
                "postgresql+psycopg2://"
                f"{quote(self.DB_USER, safe='')}:{quote(self.DB_PASSWORD, safe='')}"
                f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
            )
        return self


settings = Settings()
