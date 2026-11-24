"""Catalogo global de proveedores y su replica tenant (Feature 020)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import permisos
from app.core.rut import normalizar_rut
from app.models import Proveedor, ProveedorControl
from app.schemas.compra_schema import ProveedorCrear
from app.services.auth_service import IdentidadAutenticada

from ._comun import (
    _ADMINISTRADOR,
    _confirmar,
    _conflicto,
    _es_postgres,
    _no_encontrado,
)

# `normalizar_rut` se reexporta desde `app.core.rut` (Feature 027). Se conserva
# el import para que los consumidores historicos sigan funcionando sin cambios.


def _clave_rut_sql():
    """Expresion SQL de la clave normalizada del RUT (misma que el indice)."""
    return func.upper(
        func.replace(
            func.replace(
                func.replace(func.trim(ProveedorControl.rut), ".", ""),
                "-",
                "",
            ),
            " ",
            "",
        )
    )


def _proveedor_activo_control(
    db_control: Session, proveedor_id: int
) -> ProveedorControl:
    proveedor = db_control.get(ProveedorControl, proveedor_id)
    if proveedor is None:
        raise _no_encontrado("Proveedor no encontrado")
    if not proveedor.activo:
        raise _conflicto("El proveedor esta inactivo")
    return proveedor


def _replicar_proveedor(
    db_tenant: Session, proveedor: ProveedorControl
) -> None:
    """Upsert de la replica tenant con el mismo `proveedor_id` (DT-1).

    Solo aplica en PostgreSQL. En SQLite control y tenant comparten la tabla
    fisica `proveedor`, de modo que insertar de nuevo violaria la PK.
    """
    if not _es_postgres(db_tenant):
        return
    replica = db_tenant.get(Proveedor, proveedor.proveedor_id)
    if replica is None:
        replica = Proveedor(
            proveedor_id=proveedor.proveedor_id,
            rut=proveedor.rut,
            razon_social=proveedor.razon_social,
            nombre_fantasia=proveedor.nombre_fantasia,
            giro=proveedor.giro,
            correo=proveedor.correo,
            telefono=proveedor.telefono,
            activo=proveedor.activo,
        )
        db_tenant.add(replica)
    else:
        replica.rut = proveedor.rut
        replica.razon_social = proveedor.razon_social
        replica.nombre_fantasia = proveedor.nombre_fantasia
        replica.giro = proveedor.giro
        replica.correo = proveedor.correo
        replica.telefono = proveedor.telefono
        replica.activo = proveedor.activo
    db_tenant.flush()


def listar_proveedores(db_control: Session) -> list[ProveedorControl]:
    """Proveedores activos del catalogo global, en orden alfabetico."""
    return list(
        db_control.execute(
            select(ProveedorControl)
            .where(ProveedorControl.activo.is_(True))
            .order_by(ProveedorControl.razon_social, ProveedorControl.proveedor_id)
        )
        .scalars()
        .all()
    )


def crear_proveedor(
    db_control: Session,
    db_tenant: Session,
    datos: ProveedorCrear,
    identidad: IdentidadAutenticada | None,
) -> ProveedorControl:
    """Alta en `control.proveedor` y replica tenant si el actor es Administrador.

    El Superadmin opera solo sobre control (AC-2). En SQLite la replica es la
    misma tabla fisica y no se reinserta.
    """
    rut = datos.rut.strip().upper()
    clave = normalizar_rut(rut)
    existente = db_control.execute(
        select(ProveedorControl).where(_clave_rut_sql() == clave)
    ).scalar_one_or_none()
    if existente is not None:
        raise _conflicto("El RUT del proveedor ya esta registrado")

    proveedor = ProveedorControl(
        rut=rut,
        razon_social=datos.razon_social.strip(),
        nombre_fantasia=datos.nombre_fantasia,
        giro=datos.giro,
        correo=str(datos.correo) if datos.correo is not None else None,
        telefono=datos.telefono,
        activo=True,
    )
    db_control.add(proveedor)
    _confirmar(db_control, "El RUT del proveedor ya esta registrado")
    db_control.refresh(proveedor)

    if permisos.nombre_rol_de(identidad) == _ADMINISTRADOR:
        _replicar_proveedor(db_tenant, proveedor)
        _confirmar(
            db_tenant,
            "La replica local del proveedor ya existe con otro identificador",
        )
    return proveedor
