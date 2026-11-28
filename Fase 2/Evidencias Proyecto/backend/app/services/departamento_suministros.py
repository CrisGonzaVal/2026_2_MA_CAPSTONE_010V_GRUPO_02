"""Resolucion del departamento «Suministros» (Feature 012, enmienda D-8/D-9).

Para un Bodeguero, el cliente no elige departamento: el servidor resuelve una
fila dedicada llamada exactamente `Suministros` en la institucion del usuario y
la usa como `usuario.departamento_id` (la columna sigue `NOT NULL`). La
opcionalidad del campo en la entrada la declara `UsuarioCrear`/`UsuarioEdicion`
(D-12); esta capa decide por el **nombre del rol** resuelto contra la tabla `rol`
y comparte el helper el alta (E12-A1) y la edicion (E12-A2).

Reglas (D-8/D-9):

* busqueda por nombre normalizado `lower(trim(nombre_dep)) == 'suministros'`
  dentro de la institucion (la unicidad vigente es
  `(institucion_id, lower(trim(nombre_dep)))`);
* si existe activo se reutiliza **sin tocar** nombre, descripcion ni sede;
* si existe inactivo se reactiva (`activo = True`) y se reutiliza;
* si no existe se crea con la descripcion de unidad automatica, `sede_id =
  NULL` y `activo = True`;
* el helper **no hace commit**: usa `flush()` dentro de la transaccion del
  llamador, de modo que un alta que no confirma el usuario tampoco confirma
  «Suministros»;
* concurrencia: en PostgreSQL el `INSERT` corre dentro de un savepoint
  (`begin_nested()`); si choca con la unicidad, el savepoint revierte y se
  relee la fila ganadora. Una relectura que no encuentra la fila vuelve a
  lanzar el `IntegrityError`, porque el conflicto no era el de «Suministros».
  En SQLite no se abre savepoint (pysqlite confirma en el `RELEASE` del
  savepoint exterior, lo que romperia la garantia transaccional); SQLite
  serializa las escrituras y no acredita la carrera. La verificacion real es
  PostgreSQL gated (E12-A3).
"""

from __future__ import annotations

from contextlib import nullcontext

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Departamento

#: Nombre exacto persistido la primera vez que nace la fila (D-8).
NOMBRE_SUMINISTROS = "Suministros"

#: Descripcion exacta de la fila creada por la resolucion automatica (D-8).
DESCRIPCION_SUMINISTROS = (
    "Unidad de suministros asignada automáticamente a los Bodegueros"
)


def es_nombre_suministros(nombre_dep: str | None) -> bool:
    """True si el nombre visible corresponde a `Suministros` (normalizado)."""
    return (nombre_dep or "").strip().lower() == NOMBRE_SUMINISTROS.lower()


def es_departamento_suministros(departamento: Departamento | None) -> bool:
    """True si la fila existe y su nombre normalizado es `Suministros`."""
    return departamento is not None and es_nombre_suministros(
        departamento.nombre_dep
    )


def _buscar_departamento_suministros(
    db: Session, institucion_id: str
) -> Departamento | None:
    """Fila de la institucion cuyo nombre normalizado es `Suministros`."""
    return (
        db.query(Departamento)
        .filter(
            Departamento.institucion_id == institucion_id,
            func.lower(func.trim(Departamento.nombre_dep))
            == NOMBRE_SUMINISTROS.lower(),
        )
        .first()
    )


def _reactivar_si_corresponde(db: Session, departamento: Departamento) -> Departamento:
    """Reactiva la fila inactiva y la deja visible para el llamador (D-8)."""
    if not departamento.activo:
        departamento.activo = True
        db.flush()
    return departamento


def _transaccion_de_creacion(db: Session):
    """Contexto de insercion de la fila nueva (D-9).

    En PostgreSQL el `INSERT` corre dentro de un savepoint: un conflicto de
    unicidad revierte solo ese intento y deja la transaccion del llamador
    utilizable para releer la fila ganadora.

    En SQLite no se usa savepoint: pysqlite emite el `SAVEPOINT` como control de
    transaccion exterior y su `RELEASE` confirma en el acto, lo que romperia la
    garantia de D-8 (la fila no puede confirmarse antes que el usuario). Ademas
    SQLite serializa las escrituras y no acredita la carrera; el pre-check
    normalizado basta y la fila sigue en la transaccion del llamador.
    """
    if db.get_bind().dialect.name == "postgresql":
        return db.begin_nested()
    return nullcontext()


def resolver_departamento_suministros(
    db: Session, institucion_id: str | None
) -> Departamento:
    """Devuelve el departamento `Suministros` de la institucion, creandolo si falta.

    Comparte la transaccion del llamador: nunca hace `commit()`. `institucion_id`
    debe estar resuelta; una institucion no resoluble es un error de contrato y
    responde **403** (mismo criterio que `ambito_service.alcance_institucional`).
    """
    if institucion_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No se pudo resolver la institucion del usuario",
        )

    existente = _buscar_departamento_suministros(db, institucion_id)
    if existente is not None:
        return _reactivar_si_corresponde(db, existente)

    try:
        with _transaccion_de_creacion(db):
            creado = Departamento(
                nombre_dep=NOMBRE_SUMINISTROS,
                descripcion=DESCRIPCION_SUMINISTROS,
                institucion_id=institucion_id,
                sede_id=None,
                activo=True,
            )
            db.add(creado)
            db.flush()
        return creado
    except IntegrityError:
        if db.get_bind().dialect.name != "postgresql":
            # Sin savepoint no hay transaccion recuperable: se propaga para que
            # el llamador aplique su propio rollback (D-8).
            raise
        # Otra transaccion gano la carrera de creacion: el savepoint revirtio y
        # la fila ya confirmada se reutiliza dentro de la misma peticion (D-9).
        ganadora = _buscar_departamento_suministros(db, institucion_id)
        if ganadora is None:
            raise
        return _reactivar_si_corresponde(db, ganadora)
