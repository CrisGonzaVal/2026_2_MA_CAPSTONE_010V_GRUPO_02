"""Salud del esquema de la Feature 026 sobre PostgreSQL 16 real - gated.

SQLite acepta los indices de expresion portables, pero no reproduce el motor de
PostgreSQL ni el `CREATE UNIQUE INDEX ... ((true))` de U-07. Lo que la 026 exige
solo se acredita contra PostgreSQL 16:

  * arranque limpio (`01_esquema.sql` + `02_datos_semilla.sql`) con 25 tablas en
    `control` y 22 por tenant, sin `inventario` en ningun esquema;
  * los 15 indices P0 de la 026 (mas los 2 de `orden_compra_ticket` de la 021)
    replicados en `control` y en cada tenant;
  * las unicidades funcionales U-01..U-05 declaradas como indices unicos de
    expresion, y U-06 como indice parcial de una sola creacion por ticket;
  * U-07 (`version_esquema_unica_idx`) rechaza una segunda fila de version;
  * K-01/K-02 (correo y RUT canonicos), K-03 (tope entregado), K-04 (tipo de
    movimiento) y `stock_sede_id NOT NULL` rechazan los datos invalidos y siguen
    aceptando los validos;
  * la semilla deja 14 saldos, 3 movimientos y los cuadres 45/12 de INST-001.

COMO ACTIVARLA
    docker compose -f docker-compose.yml up -d db
    $env:POSTGRES_TEST_URL = "postgresql://postgres:postgres@localhost:5433/postgres"
    cd backend; python -m pytest tests/test_salud_esquema_postgres_026.py

    Sin `POSTGRES_TEST_URL` los tests se **saltan** con una razon clara y la
    suite ordinaria (SQLite) no cambia. La URL apunta a una base de
    mantenimiento donde el test **crea y destruye** una base temporal propia;
    nunca toca `apt_erp`.

NO se anade ninguna dependencia: `psycopg2` ya esta en `requirements.txt`.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import pytest

try:  # `psycopg2` es dependencia declarada; el guard evita un error de coleccion.
    import psycopg2

    _PSYCOPG2_DISPONIBLE = True
except ImportError:  # pragma: no cover - entorno sin la dependencia
    _PSYCOPG2_DISPONIBLE = False

from app.core.config import VERSION_ESQUEMA_OBJETIVO

_POSTGRES_TEST_URL = os.environ.get("POSTGRES_TEST_URL")

pytestmark = pytest.mark.skipif(
    not _POSTGRES_TEST_URL or not _PSYCOPG2_DISPONIBLE,
    reason=(
        "requiere POSTGRES_TEST_URL (PostgreSQL 16 real) y psycopg2; "
        "ver el docstring del modulo"
    ),
)

RAIZ = Path(__file__).resolve().parents[4]
ESQUEMA_SQL = RAIZ / "database" / "01_esquema.sql"
SEMILLA_SQL = RAIZ / "database" / "02_datos_semilla.sql"

VERSION_VIGENTE = "026.1"

#: Los 17 indices P0 que todo esquema (control y tenant) debe tener. Los 15 de
#: la 026 mas los 2 de `orden_compra_ticket` que introdujo la 021.
INDICES_P0 = {
    "orden_compra_ticket_ticket_idx": (
        "orden_compra_ticket",
        ("institucion_id", "ticket_id"),
    ),
    "orden_compra_ticket_producto_idx": (
        "orden_compra_ticket",
        ("institucion_id", "producto_id"),
    ),
    "stock_sede_producto_sede_idx": ("stock_sede", ("producto_id", "sede_id")),
    "movimiento_stock_sede_fecha_idx": (
        "movimiento_inventario",
        ("stock_sede_id", "fecha_movimiento", "movimiento_id"),
    ),
    "movimiento_fecha_idx": (
        "movimiento_inventario",
        ("fecha_movimiento", "movimiento_id"),
    ),
    "ticket_sede_estado_fecha_idx": (
        "ticket",
        ("sede_id", "estado_id", "fecha_creacion", "ticket_id"),
    ),
    "ticket_usuario_fecha_idx": (
        "ticket",
        ("usuario_id", "fecha_creacion", "ticket_id"),
    ),
    "detalle_ticket_ticket_idx": ("detalle_ticket", ("ticket_id", "detalle_ticket_id")),
    "detalle_ticket_producto_idx": ("detalle_ticket", ("producto_id", "ticket_id")),
    "historial_ticket_ticket_fecha_idx": (
        "historial_transicion_ticket",
        ("ticket_id", "fecha_transicion", "historial_transicion_id"),
    ),
    "historial_producto_producto_fecha_idx": (
        "historial_transicion_producto",
        ("producto_id", "fecha_transicion", "historial_producto_id"),
    ),
    "historial_categoria_categoria_fecha_idx": (
        "historial_transicion_categoria",
        ("categoria_id", "fecha_transicion", "historial_categoria_id"),
    ),
    "usuario_departamento_idx": ("usuario", ("departamento_id",)),
    "departamento_sede_idx": ("departamento", ("sede_id",)),
    "producto_categoria_idx": ("producto", ("categoria_id",)),
    "orden_compra_institucion_fecha_idx": (
        "orden_compra",
        ("institucion_id", "fecha_creacion", "orden_compra_id"),
    ),
    "orden_compra_sede_estado_fecha_idx": (
        "orden_compra",
        ("sede_id", "estado", "fecha_creacion", "orden_compra_id"),
    ),
}

#: Unicidades B2 de expresion: nombre del indice -> funcion que debe aparecer en
#: su definicion. U-06 y U-07 se comprueban aparte (indices parcial / constante).
UNICIDADES_B2 = {
    "usuario_correo_normalizado_uk": "lower",
    "proveedor_rut_normalizado_uk": "upper",
    "sede_nombre_institucion_uk": "lower",
    "departamento_nombre_institucion_uk": "lower",
    "categoria_nombre_institucion_uk": "lower",
}


# ---------------------------------------------------------------------------
# Conexion y utilidades
# ---------------------------------------------------------------------------


def _sin_driver(url: str) -> str:
    return url.replace("postgresql+psycopg2://", "postgresql://")


def _url_con_base(url: str, nombre: str) -> str:
    partes = urlsplit(url)
    return urlunsplit((partes.scheme, partes.netloc, "/" + nombre, "", ""))


@contextmanager
def _base_temporal():
    """Crea una base PostgreSQL efimera y la destruye al salir (nunca `apt_erp`)."""
    dsn = _sin_driver(_POSTGRES_TEST_URL or "")
    admin = psycopg2.connect(dsn)
    admin.autocommit = True
    nombre = f"compustock_026_{uuid4().hex[:12]}"
    with admin.cursor() as cur:
        cur.execute(f'CREATE DATABASE "{nombre}"')
    try:
        conexion = psycopg2.connect(_url_con_base(dsn, nombre))
        try:
            yield conexion
        finally:
            conexion.close()
    finally:
        with admin.cursor() as cur:
            cur.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (nombre,),
            )
            cur.execute(f'DROP DATABASE IF EXISTS "{nombre}"')
        admin.close()


def _filas(conexion, sql: str, params=None):
    with conexion.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall() if cur.description else []


def _escalar(conexion, sql: str, params=None):
    return _filas(conexion, sql, params)[0][0]


def _ejecutar(conexion, sql: str, params=None) -> None:
    with conexion.cursor() as cur:
        cur.execute(sql, params)
    conexion.commit()


def _ejecutar_script(conexion, ruta: Path) -> None:
    _ejecutar(conexion, ruta.read_text(encoding="utf-8"))


def _instalar(conexion) -> None:
    """Corre la instalacion limpia completa, en el orden del volumen."""
    _ejecutar_script(conexion, ESQUEMA_SQL)
    with conexion.cursor() as cur:
        cur.execute(SEMILLA_SQL.read_text(encoding="utf-8"))
    conexion.commit()


def _rechaza(conexion, sql: str, params=None) -> str:
    """Ejecuta un INSERT invalido dentro de un savepoint y devuelve el error.

    El savepoint mantiene viva la transaccion externa, de modo que los tests
    comparten la misma base instalada sin filtrar filas entre ellos.
    """
    with conexion.cursor() as cur:
        cur.execute("SAVEPOINT intento")
        try:
            cur.execute(sql, params)
        except psycopg2.Error as error:
            cur.execute("ROLLBACK TO SAVEPOINT intento")
            cur.execute("RELEASE SAVEPOINT intento")
            return str(error)
        cur.execute("ROLLBACK TO SAVEPOINT intento")
        cur.execute("RELEASE SAVEPOINT intento")
        raise AssertionError(f"se esperaba un rechazo del motor: {sql}")


def _acepta(conexion, sql: str, params=None) -> None:
    """Ejecuta un INSERT valido dentro de un savepoint y deshace sus efectos."""
    with conexion.cursor() as cur:
        cur.execute("SAVEPOINT intento")
        try:
            cur.execute(sql, params)
        except psycopg2.Error as error:
            cur.execute("ROLLBACK TO SAVEPOINT intento")
            cur.execute("RELEASE SAVEPOINT intento")
            raise AssertionError(f"se esperaba exito del motor: {error}") from error
        cur.execute("ROLLBACK TO SAVEPOINT intento")
        cur.execute("RELEASE SAVEPOINT intento")


def _colisiona(
    conexion,
    sql_valido: str,
    params_valido,
    sql_duplicado: str,
    params_duplicado,
) -> str:
    """Inserta una fila valida y luego una equivalente; la segunda debe chocar.

    Ambas filas viven en el mismo savepoint para que la unicidad se evalue de
    verdad, y el savepoint se deshace al terminar.
    """
    with conexion.cursor() as cur:
        cur.execute("SAVEPOINT colision")
        try:
            cur.execute(sql_valido, params_valido)
        except psycopg2.Error as error:
            cur.execute("ROLLBACK TO SAVEPOINT colision")
            cur.execute("RELEASE SAVEPOINT colision")
            raise AssertionError(f"la fila valida fallo: {error}") from error
        try:
            cur.execute(sql_duplicado, params_duplicado)
        except psycopg2.Error as error:
            cur.execute("ROLLBACK TO SAVEPOINT colision")
            cur.execute("RELEASE SAVEPOINT colision")
            return str(error)
        cur.execute("ROLLBACK TO SAVEPOINT colision")
        cur.execute("RELEASE SAVEPOINT colision")
        raise AssertionError("se esperaba una colision de unicidad")


def _tablas_del_esquema(conexion, esquema: str) -> set[str]:
    filas = _filas(
        conexion,
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = %s AND table_type = 'BASE TABLE'",
        (esquema,),
    )
    return {fila[0] for fila in filas}


def _esquema_de_institucion(institucion_id: str) -> str:
    from app.services.tenant_service import nombre_esquema_para_institucion

    return nombre_esquema_para_institucion(institucion_id)


def _esquemas_tenant(conexion) -> list[str]:
    """Esquemas `tenant_*` creados por la semilla (excluye `CTRL-SAAS`)."""
    return [
        fila[0]
        for fila in _filas(
            conexion,
            "SELECT schema_name FROM information_schema.schemata "
            "WHERE left(schema_name, 7) = 'tenant_' ORDER BY schema_name",
        )
    ]


def _esquemas(conexion) -> list[str]:
    """`control` mas un esquema por institucion sembrada."""
    return ["control"] + _esquemas_tenant(conexion)


def _columnas_del_indice(conexion, esquema: str) -> dict[str, tuple[str, tuple[str, ...]]]:
    """Indice -> (tabla, columnas) para los indices simples de un esquema."""
    filas = _filas(
        conexion,
        """
        SELECT i.relname, t.relname,
               array_agg(a.attname ORDER BY k.ord) AS columnas
        FROM pg_index x
        JOIN pg_class t ON t.oid = x.indrelid
        JOIN pg_class i ON i.oid = x.indexrelid
        JOIN pg_namespace n ON n.oid = t.relnamespace
        JOIN LATERAL unnest(
            string_to_array(x.indkey::text, ' ')::int[]
        ) WITH ORDINALITY AS k(attnum, ord) ON TRUE
        JOIN pg_attribute a
          ON a.attrelid = t.oid AND a.attnum = k.attnum
        WHERE n.nspname = %s
        GROUP BY i.relname, t.relname
        """,
        (esquema,),
    )
    return {fila[0]: (fila[1], tuple(fila[2])) for fila in filas}


def _definiciones_de_indices(conexion, esquema: str) -> dict[str, str]:
    return {
        fila[0]: fila[1]
        for fila in _filas(
            conexion,
            "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = %s",
            (esquema,),
        )
    }


def _columna(conexion, esquema: str, tabla: str, columna: str):
    filas = _filas(
        conexion,
        "SELECT is_nullable, data_type FROM information_schema.columns "
        "WHERE table_schema = %s AND table_name = %s AND column_name = %s",
        (esquema, tabla, columna),
    )
    return filas[0] if filas else None


def _un_registro(conexion, esquema: str, columnas: str, tabla: str, orden: str = ""):
    filas = _filas(
        conexion, f'SELECT {columnas} FROM "{esquema}"."{tabla}" {orden} LIMIT 1'
    )
    assert filas, f"{esquema}.{tabla} no tiene filas sembradas"
    return filas[0]


# ---------------------------------------------------------------------------
# Base instalada una sola vez por modulo
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def conexion():
    with _base_temporal() as base:
        _instalar(base)
        yield base


@pytest.fixture(autouse=True)
def _transaccion_limpia(conexion):
    """Deshace lo que deje cada prueba, incluso si una sentencia aborto la tx."""
    yield
    conexion.rollback()


@pytest.fixture
def tenant(conexion):
    """Esquema del tenant INST-001, el unico con saldos y movimientos."""
    return _esquema_de_institucion("INST-001")


# ---------------------------------------------------------------------------
# Arranque limpio: 25/22, sin inventario, version y semilla
# ---------------------------------------------------------------------------


def test_arranque_limpio_deja_25_tablas_en_control_y_22_por_tenant(conexion):
    assert len(_tablas_del_esquema(conexion, "control")) == 25
    esquemas = _esquemas_tenant(conexion)
    assert len(esquemas) == 4, esquemas
    for esquema in esquemas:
        tablas = _tablas_del_esquema(conexion, esquema)
        assert len(tablas) == 22, (esquema, len(tablas))
        assert "inventario" not in tablas, esquema
    assert "inventario" not in _tablas_del_esquema(conexion, "control")


def test_version_026_1_en_control_y_en_cada_tenant(conexion):
    assert VERSION_ESQUEMA_OBJETIVO == VERSION_VIGENTE
    assert _escalar(conexion, "SELECT version FROM control.version_esquema") == VERSION_VIGENTE
    for esquema in _esquemas(conexion)[1:]:
        assert _escalar(conexion, f'SELECT version FROM "{esquema}".version_esquema') == (
            VERSION_VIGENTE
        ), esquema


def test_semilla_conserva_14_saldos_3_movimientos_y_cuadres_45_12(conexion, tenant):
    total_saldos = sum(
        _escalar(conexion, f'SELECT count(*) FROM "{esquema}".stock_sede')
        for esquema in _esquemas(conexion)[1:]
    )
    assert total_saldos == 14, total_saldos
    assert _escalar(conexion, f'SELECT count(*) FROM "{tenant}".stock_sede') == 10
    assert _escalar(conexion, f'SELECT count(*) FROM "{tenant}".movimiento_inventario') == 3
    assert _escalar(
        conexion,
        f'SELECT count(*) FROM "{tenant}".movimiento_inventario WHERE stock_sede_id IS NULL',
    ) == 0
    saldos = dict(
        _filas(
            conexion,
            f'SELECT stock_sede_id, stock_actual FROM "{tenant}".stock_sede '
            "WHERE stock_sede_id IN (8, 9) ORDER BY stock_sede_id",
        )
    )
    assert saldos == {8: 45, 9: 12}, saldos


# ---------------------------------------------------------------------------
# Indices P0 y unicidades declaradas
# ---------------------------------------------------------------------------


def test_los_17_indices_p0_existen_en_control_y_en_cada_tenant(conexion):
    for esquema in _esquemas(conexion):
        encontrados = _columnas_del_indice(conexion, esquema)
        for nombre, (tabla, columnas) in INDICES_P0.items():
            assert nombre in encontrados, (esquema, nombre)
            assert encontrados[nombre] == (tabla, columnas), (esquema, nombre)


def test_unicidades_b2_son_indices_unicos_de_expresion(conexion):
    for esquema in _esquemas(conexion):
        definiciones = _definiciones_de_indices(conexion, esquema)
        for nombre, funcion in UNICIDADES_B2.items():
            assert nombre in definiciones, (esquema, nombre)
            definicion = definiciones[nombre]
            assert definicion.startswith("CREATE UNIQUE INDEX"), (esquema, nombre)
            assert funcion in definicion.lower(), (esquema, nombre, definicion)

        creacion = definiciones.get("historial_transicion_ticket_creacion_uk", "")
        assert creacion.startswith("CREATE UNIQUE INDEX"), esquema
        assert "estado_origen_id is null" in creacion.lower(), (esquema, creacion)

        version = definiciones.get("version_esquema_unica_idx", "")
        assert version.startswith("CREATE UNIQUE INDEX"), esquema
        assert "(true)" in version.lower(), (esquema, version)


# ---------------------------------------------------------------------------
# U-07: una sola version vigente por esquema
# ---------------------------------------------------------------------------


def test_u07_rechaza_una_segunda_fila_de_version(conexion):
    for esquema in _esquemas(conexion):
        error = _rechaza(
            conexion,
            f'INSERT INTO "{esquema}".version_esquema (version) VALUES (%s)',
            (VERSION_VIGENTE,),
        )
        assert "duplicate key" in error.lower() or "unique" in error.lower(), (
            esquema,
            error,
        )


# ---------------------------------------------------------------------------
# K-01 / K-02 / U-01 / U-02: correo y RUT canonicos
# ---------------------------------------------------------------------------


def test_k01_rechaza_correo_no_canonico_y_acepta_el_canonico(conexion, tenant):
    _, correo, departamento_id, rol_id = _un_registro(
        conexion,
        tenant,
        "usuario_id, correo, departamento_id, rol_id",
        "usuario",
        "ORDER BY usuario_id",
    )
    plantilla = (
        f'INSERT INTO "{tenant}".usuario '
        "(nombre, apellido, correo, departamento_id, rol_id) "
        "VALUES ('Prueba', 'K01', %s, %s, %s)"
    )
    error = _rechaza(conexion, plantilla, (f"  {correo.upper()}  ", departamento_id, rol_id))
    assert "usuario_correo_canonico_ck" in error, error

    _acepta(conexion, plantilla, (f"nuevo.{correo}", departamento_id, rol_id))

    # U-01: dos correos que normalizan igual chocan aunque el texto difiera en
    # los espacios exteriores (K-01 ya impide guardarlos, asi que se prueba con
    # el mismo correo canonico).
    error = _rechaza(conexion, plantilla, (correo, departamento_id, rol_id))
    assert "duplicate key" in error.lower() or "unique" in error.lower(), error


def test_k02_rechaza_rut_no_canonico_y_acepta_el_canonico(conexion, tenant):
    plantilla = (
        f'INSERT INTO "{tenant}".proveedor (proveedor_id, rut, razon_social) '
        "VALUES (9001, %s, 'Proveedor K02')"
    )
    error = _rechaza(conexion, plantilla, (" 11111111-1 ",))
    assert "proveedor_rut_canonico_ck" in error, error

    _acepta(conexion, plantilla, ("11111111-1",))


def test_u02_rechaza_el_mismo_rut_con_puntos_o_guiones_distintos(conexion, tenant):
    # U-02 normaliza el RUT quitando puntos, guiones y espacios: el mismo RUT
    # visible con otro formato debe chocar aunque el texto sea distinto.
    rut_visible = _un_registro(
        conexion,
        tenant,
        "rut",
        "proveedor",
        "WHERE length(rut) > 8 ORDER BY proveedor_id",
    )[0]
    sin_separadores = (
        rut_visible.replace(".", "").replace("-", "").replace(" ", "")
    )
    assert sin_separadores != rut_visible, rut_visible
    error = _rechaza(
        conexion,
        f'INSERT INTO "{tenant}".proveedor (proveedor_id, rut, razon_social) '
        "VALUES (9003, %s, 'Proveedor U02 duplicado')",
        (sin_separadores,),
    )
    assert "duplicate key" in error.lower() or "unique" in error.lower(), error


# ---------------------------------------------------------------------------
# U-03 / U-04 / U-05: nombres unicos por institucion sin mayusculas/espacios
# ---------------------------------------------------------------------------


def test_u03_u04_u05_rechazan_nombres_equivalentes_por_institucion(conexion, tenant):
    sede_id, sede_nombre, institucion_id = _un_registro(
        conexion, tenant, "sede_id, nombre, institucion_id", "sede", "ORDER BY sede_id"
    )
    error = _rechaza(
        conexion,
        f'INSERT INTO "{tenant}".sede (nombre, institucion_id) VALUES (%s, %s)',
        (f"  {sede_nombre.upper()}  ", institucion_id),
    )
    assert "duplicate key" in error.lower() or "unique" in error.lower(), error

    departamento_nombre = _un_registro(
        conexion, tenant, "nombre_dep", "departamento", "ORDER BY departamento_id"
    )[0]
    error = _rechaza(
        conexion,
        f'INSERT INTO "{tenant}".departamento (nombre_dep, institucion_id) '
        "VALUES (%s, %s)",
        (f"  {departamento_nombre.upper()}  ", institucion_id),
    )
    assert "duplicate key" in error.lower() or "unique" in error.lower(), error

    categoria_nombre = _un_registro(
        conexion, tenant, "nombre_cat", "categoria", "ORDER BY categoria_id"
    )[0]
    error = _rechaza(
        conexion,
        f'INSERT INTO "{tenant}".categoria (nombre_cat, institucion_id) '
        "VALUES (%s, %s)",
        (f"  {categoria_nombre.upper()}  ", institucion_id),
    )
    assert "duplicate key" in error.lower() or "unique" in error.lower(), error


# ---------------------------------------------------------------------------
# K-03 / K-04: topes y tipos de movimiento
# ---------------------------------------------------------------------------


def test_k03_rechaza_entregar_mas_de_lo_solicitado(conexion, tenant):
    ticket_id, institucion_id = _un_registro(
        conexion, tenant, "ticket_id, institucion_id", "ticket", "ORDER BY ticket_id"
    )
    producto_id = _un_registro(
        conexion, tenant, "producto_id", "producto", "ORDER BY producto_id"
    )[0]
    plantilla = (
        f'INSERT INTO "{tenant}".detalle_ticket '
        "(ticket_id, producto_id, cantidad_solicitada, cantidad_entregada, "
        "institucion_id) VALUES (%s, %s, %s, %s, %s)"
    )
    error = _rechaza(
        conexion, plantilla, (ticket_id, producto_id, 5, 6, institucion_id)
    )
    assert "detalle_cantidad_entregada_tope_ck" in error, error

    _acepta(conexion, plantilla, (ticket_id, producto_id, 5, 5, institucion_id))


def test_k04_rechaza_un_tipo_de_movimiento_fuera_del_dominio(conexion, tenant):
    stock_sede_id = _un_registro(
        conexion, tenant, "stock_sede_id", "stock_sede", "ORDER BY stock_sede_id"
    )[0]
    plantilla = (
        f'INSERT INTO "{tenant}".movimiento_inventario '
        "(tipo_movimiento, cantidad, stock_sede_id) VALUES (%s, %s, %s)"
    )
    error = _rechaza(conexion, plantilla, ("AJUSTE", 1, stock_sede_id))
    assert "movimiento_tipo_ck" in error, error

    _acepta(conexion, plantilla, ("ENTRADA", 1, stock_sede_id))


# ---------------------------------------------------------------------------
# U-06: una sola fila de creacion por ticket
# ---------------------------------------------------------------------------


def test_u06_una_creacion_por_ticket_y_transiciones_libres(conexion, tenant):
    ticket_id = _un_registro(conexion, tenant, "ticket_id", "ticket", "ORDER BY ticket_id")[0]
    usuario_id = _un_registro(
        conexion, tenant, "usuario_id", "usuario", "ORDER BY usuario_id"
    )[0]
    estado_id = _un_registro(
        conexion, tenant, "estado_id", "estado_ticket", "ORDER BY estado_id"
    )[0]
    creacion = (
        f'INSERT INTO "{tenant}".historial_transicion_ticket '
        "(ticket_id, estado_origen_id, estado_destino_id, usuario_id, motivo) "
        "VALUES (%s, NULL, %s, %s, 'creacion')"
    )
    error = _colisiona(
        conexion,
        creacion,
        (ticket_id, estado_id, usuario_id),
        creacion,
        (ticket_id, estado_id, usuario_id),
    )
    assert "duplicate key" in error.lower() or "unique" in error.lower(), error

    transicion = (
        f'INSERT INTO "{tenant}".historial_transicion_ticket '
        "(ticket_id, estado_origen_id, estado_destino_id, usuario_id) "
        "VALUES (%s, %s, %s, %s)"
    )
    _acepta(conexion, transicion, (ticket_id, estado_id, estado_id, usuario_id))
    _acepta(conexion, transicion, (ticket_id, estado_id, estado_id, usuario_id))


# ---------------------------------------------------------------------------
# N-01: stock_sede_id obligatorio y sin inventario_id
# ---------------------------------------------------------------------------


def test_n01_stock_sede_id_es_not_null_y_no_hay_inventario_id(conexion, tenant):
    for esquema in ("control", tenant):
        columna = _columna(conexion, esquema, "movimiento_inventario", "stock_sede_id")
        assert columna is not None, esquema
        assert columna[0] == "NO", (esquema, columna)
        assert _columna(conexion, esquema, "movimiento_inventario", "inventario_id") is None

    # El motor rechaza un movimiento sin saldo, no solo el servicio.
    error = _rechaza(
        conexion,
        f'INSERT INTO "{tenant}".movimiento_inventario '
        "(tipo_movimiento, cantidad, stock_sede_id) VALUES ('ENTRADA', 1, NULL)",
    )
    assert "not-null" in error.lower() or "null" in error.lower(), error
