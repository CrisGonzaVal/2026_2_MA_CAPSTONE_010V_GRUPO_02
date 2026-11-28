"""Servicio de asignaciones organizacionales (Feature 011, T7).

Superficie minima para que el modelo organizacional sea operable sin CRUD de
sedes (eso es la Feature 012): consulta de sedes del tenant y asignacion de sede a
departamento y a un Bodeguero. La enmienda 27/Nov/2026 de la 012 retira la tabla
puente auxiliar y sus operaciones; las asignaciones de sede siguen vigentes.

Reglas de dominio (AGENTS §6: la logica vive aqui, no en el router):

  * La institucion del actor se resuelve con `ambito_service.alcance_institucional`
    a partir de la identidad ya autenticada; nunca de la peticion. Un recurso
    inexistente **o ajeno** se oculta con **404** (patron Feature 008, spec §4.12);
    un recurso de otra institucion no se toca.
  * Una precondicion organizacional o una asignacion incompatible responde
    **409** sin mutacion: asignar sede a un usuario que no es Bodeguero.
"""

from __future__ import annotations

from uuid import uuid4

from typing import List

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import permisos, security
from app.models import (
    Departamento,
    MapaUsuarioEsquema,
    Rol,
    Sede,
    Usuario,
)
from app.schemas.organizacion_schema import (
    DepartamentoCrear,
    DepartamentoEdicion,
    SedeCrear,
    SedeEdicion,
)
from app.schemas.usuario_schema import UsuarioEdicion
from app.services import ambito_service, motivo_service
from app.services.auth_service import IdentidadAutenticada, correo_del_actor
from app.services.departamento_suministros import (
    es_departamento_suministros,
    resolver_departamento_suministros,
)

_ADMINISTRADOR = permisos.RolConocido.ADMINISTRADOR.value

_BODEGUERO = permisos.RolConocido.BODEGUERO.value

_SOLICITANTE = permisos.RolConocido.SOLICITANTE.value

_DETALLE_DEPARTAMENTO = "Departamento inexistente o fuera del ambito del usuario"
_DETALLE_USUARIO = "Usuario inexistente o fuera del ambito del usuario"
_DETALLE_SEDE = "Sede inexistente o fuera del ambito del usuario"


# ---------------------------------------------------------------------------
# Helpers de resolucion y pertenencia (404 indistinguible, spec §4.12)
# ---------------------------------------------------------------------------


def _departamento_en_alcance(
    db: Session, departamento_id: int, institucion_id: str | None
) -> Departamento:
    """Departamento visible para el ambito, o 404 si no existe o es ajeno."""
    departamento = db.get(Departamento, departamento_id)
    if departamento is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=_DETALLE_DEPARTAMENTO
        )
    ambito_service.exigir_pertenencia(
        departamento.institucion_id, institucion_id, detalle=_DETALLE_DEPARTAMENTO
    )
    return departamento


def _sede_en_alcance(
    db: Session, sede_id: int, institucion_id: str | None
) -> Sede:
    """Sede visible para el ambito, o 404 si no existe o es ajena (AC-3)."""
    sede = db.get(Sede, sede_id)
    if sede is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=_DETALLE_SEDE
        )
    ambito_service.exigir_pertenencia(
        sede.institucion_id, institucion_id, detalle=_DETALLE_SEDE
    )
    return sede


def _usuario_en_alcance(
    db: Session, usuario_id: int, institucion_id: str | None
) -> Usuario:
    """Usuario visible para el ambito, o 404 si no existe o es ajeno."""
    usuario = db.get(Usuario, usuario_id)
    if usuario is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=_DETALLE_USUARIO
        )
    institucion_usuario = ambito_service.institucion_de_usuario(db, usuario)
    ambito_service.exigir_pertenencia(
        institucion_usuario, institucion_id, detalle=_DETALLE_USUARIO
    )
    return usuario


def _nombre_rol(db: Session, usuario: Usuario) -> str | None:
    """Nombre del rol del usuario, o `None` si su rol no es resoluble."""
    rol = db.get(Rol, usuario.rol_id)
    return None if rol is None else rol.nombre_rol


def _conflicto(detalle: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detalle)


def _nombre_normalizado(nombre: str) -> str:
    """Nombre visible sin espacios exteriores; el resto se conserva."""
    return nombre.strip()


def _sede_duplicada(
    db: Session,
    institucion_id: str,
    nombre: str,
    excluir_id: int | None = None,
) -> bool:
    """Feature 026 (U-03): homonimo funcional dentro de la institucion."""
    consulta = db.query(Sede).filter(
        Sede.institucion_id == institucion_id,
        func.lower(func.trim(Sede.nombre)) == nombre.strip().lower(),
    )
    if excluir_id is not None:
        consulta = consulta.filter(Sede.sede_id != excluir_id)
    return consulta.first() is not None


def _departamento_duplicado(
    db: Session,
    institucion_id: str,
    nombre_dep: str,
    excluir_id: int | None = None,
) -> bool:
    """Feature 026 (U-04): homonimo funcional dentro de la institucion."""
    consulta = db.query(Departamento).filter(
        Departamento.institucion_id == institucion_id,
        func.lower(func.trim(Departamento.nombre_dep)) == nombre_dep.strip().lower(),
    )
    if excluir_id is not None:
        consulta = consulta.filter(Departamento.departamento_id != excluir_id)
    return consulta.first() is not None


# ---------------------------------------------------------------------------
# Sedes
# ---------------------------------------------------------------------------


def listar_sedes(
    db: Session, identidad: IdentidadAutenticada | None = None
) -> List[Sede]:
    """Sedes de la institucion del actor, sin nombrar ninguna de otro tenant."""
    institucion_id = ambito_service.alcance_institucional(db, identidad)
    consulta = db.query(Sede)
    if institucion_id is not None:
        consulta = consulta.filter(Sede.institucion_id == institucion_id)
    return consulta.order_by(Sede.sede_id).all()


def asignar_sede_a_departamento(
    db: Session,
    departamento_id: int,
    sede_id: int,
    identidad: IdentidadAutenticada | None = None,
) -> Departamento:
    """Fija la sede de un departamento del tenant (spec D-5, AC-5/AC-6)."""
    institucion_id = ambito_service.alcance_institucional(db, identidad)
    departamento = _departamento_en_alcance(db, departamento_id, institucion_id)
    _sede_en_alcance(db, sede_id, institucion_id)
    departamento.sede_id = sede_id
    db.commit()
    db.refresh(departamento)
    return departamento


def asignar_sede_a_usuario(
    db: Session,
    usuario_id: int,
    sede_id: int,
    identidad: IdentidadAutenticada | None = None,
) -> Usuario:
    """Fija la sede de un Bodeguero del tenant (spec D-5/D-7, AC-5/AC-7).

    Un usuario que no es Bodeguero es una precondicion organizacional invalida y
    responde **409** sin mutar nada: la sede solo tiene sentido para quien opera
    existencias.
    """
    institucion_id = ambito_service.alcance_institucional(db, identidad)
    usuario = _usuario_en_alcance(db, usuario_id, institucion_id)
    _sede_en_alcance(db, sede_id, institucion_id)
    if _nombre_rol(db, usuario) != _BODEGUERO:
        raise _conflicto(
            "Solo un usuario Bodeguero puede tener una sede asignada"
        )
    usuario.sede_id = sede_id
    db.commit()
    db.refresh(usuario)
    return usuario


# ---------------------------------------------------------------------------
# CRUD organizacional de sedes (Feature 012, T7, AC-6/AC-11/AC-13)
# ---------------------------------------------------------------------------


def _institucion_requerida(db: Session, identidad: IdentidadAutenticada | None) -> str:
    """Institucion del actor para crear recursos organizacionales.

    El alcance global (Superadmin) no crea recursos de tenant: la matriz ya
    reserva estas operaciones al Administrador institucional, pero se deniega de
    forma defensiva para no crear filas sin institucion.
    """
    institucion_id = ambito_service.alcance_institucional(db, identidad)
    if institucion_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="La operacion requiere una institucion concreta",
        )
    return institucion_id


def crear_sede(
    db: Session,
    datos: SedeCrear,
    identidad: IdentidadAutenticada | None = None,
) -> Sede:
    """Crea una sede en la institucion del Administrador (AC-6/AC-13).

    El nombre es unico dentro de la institucion: una sede homonima responde
    **409** sin crear fila, de modo que "Sede Central" no se duplica al abrir la
    UI (AC-6). La institucion la resuelve el servidor desde la sesion.
    """
    institucion_id = _institucion_requerida(db, identidad)
    nombre = _nombre_normalizado(datos.nombre)
    if _sede_duplicada(db, institucion_id, nombre):
        raise _conflicto("Ya existe una sede con ese nombre en la institucion")
    sede = Sede(
        nombre=nombre, direccion=datos.direccion, institucion_id=institucion_id
    )
    db.add(sede)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise _conflicto(
            "Ya existe una sede con ese nombre en la institucion"
        ) from exc
    db.refresh(sede)
    return sede


def editar_sede(
    db: Session,
    sede_id: int,
    datos: SedeEdicion,
    identidad: IdentidadAutenticada | None = None,
) -> Sede:
    """Modifica el nombre y la direccion de una sede del tenant (AC-6).

    Una sede inexistente o **ajena** responde **404** sin mutacion (patron de
    ocultacion de la 011).
    """
    institucion_id = ambito_service.alcance_institucional(db, identidad)
    sede = _sede_en_alcance(db, sede_id, institucion_id)
    nombre = _nombre_normalizado(datos.nombre)
    if _sede_duplicada(
        db, sede.institucion_id, nombre, excluir_id=sede.sede_id
    ):
        raise _conflicto("Ya existe una sede con ese nombre en la institucion")
    sede.nombre = nombre
    sede.direccion = datos.direccion
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise _conflicto(
            "Ya existe una sede con ese nombre en la institucion"
        ) from exc
    db.refresh(sede)
    return sede


def cambiar_estado_sede(
    db: Session,
    sede_id: int,
    activo: bool,
    identidad: IdentidadAutenticada | None = None,
) -> Sede:
    """Activa o desactiva logicamente una sede (idempotente, AC-11).

    Sin borrado fisico ni perdida de historial. Reactivar es la misma operacion
    con `activo=True`. Una desactivacion es **idempotente** si la sede ya esta en
    ese estado; si la desactivacion dejaria dependencias activas incompatibles
    (departamentos activos o Bodegueros asignados a la sede) responde **409** con
    el motivo concreto y no cambia el estado.
    """
    institucion_id = ambito_service.alcance_institucional(db, identidad)
    sede = _sede_en_alcance(db, sede_id, institucion_id)
    if sede.activo == activo:
        return sede
    if not activo:
        motivo = _dependencias_sede(db, sede_id)
        if motivo is not None:
            raise _conflicto(motivo)
    sede.activo = activo
    db.commit()
    db.refresh(sede)
    return sede


def _dependencias_sede(db: Session, sede_id: int) -> str | None:
    """Motivo por el que desactivar la sede es insegura, o `None` si es seguro."""
    departamento = (
        db.query(Departamento)
        .filter(Departamento.sede_id == sede_id, Departamento.activo.is_(True))
        .first()
    )
    if departamento is not None:
        return (
            "No se puede desactivar la sede: hay departamentos activos asignados a "
            "ella; reasigne su sede antes"
        )
    bodeguero = (
        db.query(Usuario)
        .join(Rol, Rol.rol_id == Usuario.rol_id)
        .filter(Usuario.sede_id == sede_id, Rol.nombre_rol == _BODEGUERO)
        .first()
    )
    if bodeguero is not None:
        return (
            "No se puede desactivar la sede: hay Bodegueros asignados a ella; "
            "reasigne su sede antes"
        )
    return None


# ---------------------------------------------------------------------------
# CRUD organizacional de departamentos (Feature 012, T7, AC-7/AC-11/AC-13)
# ---------------------------------------------------------------------------


def listar_departamentos(
    db: Session, identidad: IdentidadAutenticada | None = None
) -> List[Departamento]:
    """Departamentos de la institucion del actor, con su sede y estado (AC-7)."""
    institucion_id = ambito_service.alcance_institucional(db, identidad)
    consulta = db.query(Departamento)
    if institucion_id is not None:
        consulta = consulta.filter(Departamento.institucion_id == institucion_id)
    return consulta.order_by(Departamento.departamento_id).all()


def crear_departamento(
    db: Session,
    datos: DepartamentoCrear,
    identidad: IdentidadAutenticada | None = None,
) -> Departamento:
    """Crea un departamento en la institucion del Administrador (AC-7/AC-13).

    La sede **no** es obligatoria en el alta (la precondicion de sede es
    operativa, regla 011); se asigna despues con `PUT .../sede`.
    """
    institucion_id = _institucion_requerida(db, identidad)
    nombre_dep = _nombre_normalizado(datos.nombre_dep)
    if _departamento_duplicado(db, institucion_id, nombre_dep):
        raise _conflicto(
            "Ya existe un departamento con ese nombre en la institucion"
        )
    departamento = Departamento(
        nombre_dep=nombre_dep,
        descripcion=datos.descripcion,
        institucion_id=institucion_id,
    )
    db.add(departamento)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise _conflicto(
            "Ya existe un departamento con ese nombre en la institucion"
        ) from exc
    db.refresh(departamento)
    return departamento


def editar_departamento(
    db: Session,
    departamento_id: int,
    datos: DepartamentoEdicion,
    identidad: IdentidadAutenticada | None = None,
) -> Departamento:
    """Modifica nombre y descripcion de un departamento del tenant (AC-7)."""
    institucion_id = ambito_service.alcance_institucional(db, identidad)
    departamento = _departamento_en_alcance(db, departamento_id, institucion_id)
    nombre_dep = _nombre_normalizado(datos.nombre_dep)
    if _departamento_duplicado(
        db,
        departamento.institucion_id,
        nombre_dep,
        excluir_id=departamento.departamento_id,
    ):
        raise _conflicto(
            "Ya existe un departamento con ese nombre en la institucion"
        )
    departamento.nombre_dep = nombre_dep
    departamento.descripcion = datos.descripcion
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise _conflicto(
            "Ya existe un departamento con ese nombre en la institucion"
        ) from exc
    db.refresh(departamento)
    return departamento


def cambiar_estado_departamento(
    db: Session,
    departamento_id: int,
    activo: bool,
    identidad: IdentidadAutenticada | None = None,
) -> Departamento:
    """Activa o desactiva logicamente un departamento (idempotente, AC-11).

    Sin borrado fisico. Idempotente si el departamento ya esta en ese estado; si
    la desactivacion dejaria usuarios activos vinculados (operaciones dependientes
    inconsistentes) responde **409** con el motivo concreto sin cambiar el estado.
    """
    institucion_id = ambito_service.alcance_institucional(db, identidad)
    departamento = _departamento_en_alcance(db, departamento_id, institucion_id)
    if departamento.activo == activo:
        return departamento
    if not activo:
        motivo = _dependencias_departamento(db, departamento_id)
        if motivo is not None:
            raise _conflicto(motivo)
    departamento.activo = activo
    db.commit()
    db.refresh(departamento)
    return departamento


def _dependencias_departamento(db: Session, departamento_id: int) -> str | None:
    """Motivo por el que desactivar el departamento es inseguro, o `None`."""
    usuario = (
        db.query(Usuario).filter(Usuario.departamento_id == departamento_id).first()
    )
    if usuario is not None:
        return (
            "No se puede desactivar el departamento: tiene usuarios vinculados; "
            "reasigne o desactive esos usuarios antes"
        )
    return None


# ---------------------------------------------------------------------------
# Edicion y estado logico de usuarios locales con motivo (Features 012/017)
# ---------------------------------------------------------------------------


def _motivo_de(datos) -> object | None:
    """Motivo opcional del DTO (subclases de la Feature 017)."""
    return getattr(datos, "motivo", None)


def _idempotencia_de(datos) -> str | None:
    return getattr(datos, "idempotencia", None)


def _institucion_de_mutacion(
    db: Session,
    usuario: Usuario,
    identidad: IdentidadAutenticada | None,
    institucion_id: str | None,
) -> str:
    """Institucion de la mutacion: explicita (control) o la del usuario."""
    if institucion_id is not None:
        institucion_usuario = ambito_service.institucion_de_usuario(db, usuario)
        if institucion_usuario != institucion_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=_DETALLE_USUARIO
            )
        return institucion_id
    institucion_usuario = ambito_service.institucion_de_usuario(db, usuario)
    if institucion_usuario is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No se pudo resolver la institucion del usuario",
        )
    return institucion_usuario


def _mapa_por_correo(
    db_control: Session, correo: str
) -> MapaUsuarioEsquema | None:
    return (
        db_control.query(MapaUsuarioEsquema)
        .filter(
            MapaUsuarioEsquema.correo
            == security.normalizar_correo(str(correo))
        )
        .first()
    )


def _persistir_motivo(
    db_control: Session,
    *,
    motivo,
    clave: str,
    actor_correo: str,
    accion: str,
    institucion_id: str,
    usuario: Usuario,
) -> None:
    """Segunda confirmacion local: justificacion en control (D-5).

    Si falla, el cambio tenant ya esta confirmado: se deja una constancia
    recuperable y se responde **503**. El reintento con la misma clave completa
    el motivo sin repetir la mutacion.
    """
    try:
        motivo_service.registrar_justificacion(
            db_control,
            actor_correo=actor_correo,
            accion=accion,
            institucion_id=institucion_id,
            clave_idempotente=clave,
            codigo_motivo=motivo.codigo,
            texto_motivo=motivo.texto,
            usuario_objetivo_id=usuario.usuario_id,
            correo_objetivo=security.normalizar_correo(str(usuario.correo)),
        )
    except Exception as exc:  # noqa: BLE001 - el cambio ya se aplico
        try:
            db_control.rollback()
            motivo_service.registrar_constancia_motivo(
                db_control,
                actor_correo=actor_correo,
                accion=accion,
                institucion_id=institucion_id,
                clave_idempotente=clave,
                usuario_objetivo_id=usuario.usuario_id,
                correo_objetivo=security.normalizar_correo(str(usuario.correo)),
            )
        except Exception:  # noqa: BLE001
            db_control.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "El cambio se aplico pero no se pudo registrar el motivo; "
                "reintente con el mismo identificador idempotente"
            ),
        ) from exc


def _completar_motivo_si_pendiente(
    db_control: Session,
    *,
    motivo,
    clave: str | None,
    actor_correo: str,
    accion: str,
    institucion_id: str,
    usuario: Usuario,
) -> None:
    """Reintento idempotente: completa una constancia pendiente, sin crear motivo."""
    if motivo is None or not clave:
        return
    try:
        motivo_service.completar_motivo_pendiente(
            db_control,
            clave_idempotente=clave,
            actor_correo=actor_correo,
            accion=accion,
            institucion_id=institucion_id,
            codigo_motivo=motivo.codigo,
            texto_motivo=motivo.texto,
            usuario_objetivo_id=usuario.usuario_id,
            correo_objetivo=security.normalizar_correo(str(usuario.correo)),
        )
    except Exception:  # noqa: BLE001 - un fallo de evidencia no repite el cambio
        db_control.rollback()


def editar_usuario(
    db: Session,
    usuario_id: int,
    datos: UsuarioEdicion,
    identidad: IdentidadAutenticada | None = None,
    db_control: Session | None = None,
    *,
    institucion_id: str | None = None,
) -> Usuario:
    """Modifica los atributos locales de un usuario del tenant (AC-8/AC-10).

    No cambia el correo (clave de identidad local) ni toca Clerk. Una edicion
    **efectiva** exige un motivo del catalogo D-5 antes de mutar; una edicion sin
    cambios es idempotente y no exige ni genera justificacion. Respeta el rol
    asignable del creador (D-6/AC-10), el ambito institucional (404 para un
    usuario o departamento ajeno) y el contrato (422 en payload invalido).

    Enmienda 012 (D-12/D-13): el rol destino se resuelve una vez contra `rol`.
    Un Bodeguero no elige departamento: cualquier id positivo del cliente se
    ignora y se resuelve «Suministros» en la institucion del usuario/actor, de
    modo que el departamento resuelto participa del cambio efectivo (un legacy
    en «Biblioteca» exige motivo al pasar a «Suministros»). Un rol distinto de
    Bodeguero exige `departamento_id` (422 si falta), conserva el 403/404 de un
    departamento ajeno y rechaza «Suministros» con 422. Desde Bodeguero solo se
    permite pasar a Solicitante. La edicion nunca toca `usuario.sede_id` y no
    consulta encargados; el 409 del ultimo Administrador activo se conserva.
    """
    from app.services.usuario_service import _validar_rol_asignable

    _validar_rol_asignable(db, datos.rol_id, identidad)
    institucion_actor = ambito_service.alcance_institucional(db, identidad)
    usuario = _usuario_en_alcance(db, usuario_id, institucion_actor)

    # El nombre del rol destino se resuelve una sola vez, antes de validar el
    # departamento, porque la presencia y la validez de este dependen del rol
    # (D-12/D-13).
    rol_destino = db.get(Rol, datos.rol_id)
    nombre_rol_destino = None if rol_destino is None else rol_destino.nombre_rol
    nombre_rol_actual = _nombre_rol(db, usuario)

    # D-13: desde Bodeguero solo se permite pasar a Solicitante. El
    # Administrador ya no puede asignar roles administrativos
    # (`_validar_rol_asignable`); esta guarda cierra el camino del alcance
    # global de control sin reabrir la matriz.
    if (
        nombre_rol_actual == _BODEGUERO
        and usuario.rol_id != datos.rol_id
        and nombre_rol_destino != _SOLICITANTE
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Un Bodeguero solo puede cambiar al rol Solicitante",
        )

    sesion_control = db_control if db_control is not None else db

    if nombre_rol_destino == _BODEGUERO:
        # D-8/D-13: el Bodeguero no elige departamento. Cualquier id positivo
        # del cliente (propio, ajeno o inexistente) se ignora; la institucion
        # sale del usuario/actor y «Suministros» se resuelve en ella.
        institucion = _institucion_de_mutacion(
            db, usuario, identidad, institucion_id
        )
        departamento_destino_id = resolver_departamento_suministros(
            db, institucion
        ).departamento_id
    else:
        if datos.departamento_id is None:
            # D-12: la presencia la valida el servicio, porque el nombre del rol
            # solo se conoce aqui; el 422 llega antes de toda mutacion.
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="El departamento es obligatorio para el rol indicado",
            )
        # Se conservan las validaciones vigentes de existencia y ambito
        # (404 para un departamento inexistente o ajeno) antes de mirar el
        # nombre, de modo que un id ajeno no revele como se llama (D-12).
        departamento_destino = _departamento_en_alcance(
            db, datos.departamento_id, institucion_actor
        )
        institucion = _institucion_de_mutacion(
            db, usuario, identidad, institucion_id
        )
        if (
            institucion_id is not None
            and departamento_destino.institucion_id != institucion_id
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="El departamento indicado esta fuera de la institucion",
            )
        if es_departamento_suministros(departamento_destino):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=(
                    "El departamento Suministros se asigna automaticamente a los "
                    "Bodegueros y no puede elegirse para otro rol"
                ),
            )
        departamento_destino_id = departamento_destino.departamento_id

    cambio_efectivo = (
        usuario.nombre != datos.nombre
        or usuario.apellido != datos.apellido
        or usuario.departamento_id != departamento_destino_id
        or usuario.rol_id != datos.rol_id
    )
    # Continuidad administrativa (D-7/AC-12): degradar al unico Administrador
    # activo a un rol no administrativo responde 409 antes de mutar usuario,
    # mapa o motivo. No bloquea ediciones que preservan el rol ni degradaciones
    # cuando queda otro Administrador activo.
    if usuario.rol_id != datos.rol_id and nombre_rol_actual == _ADMINISTRADOR:
        if (
            rol_destino is None or rol_destino.nombre_rol != _ADMINISTRADOR
        ) and _es_ultimo_administrador_activo(db, sesion_control, usuario):
            raise _conflicto(
                "No se puede degradar al ultimo Administrador activo de la "
                "institucion"
            )
    motivo = _motivo_de(datos)
    clave = _idempotencia_de(datos)
    actor = correo_del_actor(identidad)
    accion = "edicion_usuario"

    if not cambio_efectivo:
        _completar_motivo_si_pendiente(
            sesion_control,
            motivo=motivo,
            clave=clave,
            actor_correo=actor,
            accion=accion,
            institucion_id=institucion,
            usuario=usuario,
        )
        return usuario

    if motivo is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="La edicion efectiva de un usuario exige un motivo del catalogo",
        )
    if not clave:
        clave = f"edicion-usuario-{usuario.usuario_id}-{uuid4().hex}"

    usuario.nombre = datos.nombre
    usuario.apellido = datos.apellido
    usuario.departamento_id = departamento_destino_id
    usuario.rol_id = datos.rol_id
    db.commit()
    db.refresh(usuario)

    _persistir_motivo(
        sesion_control,
        motivo=motivo,
        clave=clave,
        actor_correo=actor,
        accion=accion,
        institucion_id=institucion,
        usuario=usuario,
    )
    return usuario


def _es_ultimo_administrador_activo(
    db: Session, db_control: Session, usuario: Usuario
) -> bool:
    """True si dar de baja a `usuario` dejaria cero Administradores activos.

    Cuenta Administradores del tenant (asociacion local activa o ausente, que el
    listado publica como activa) excluyendo al objetivo. El bloqueo se evalua
    antes de cualquier mutacion; en PostgreSQL la consulta toma bloqueo de fila
    para serializar carreras (D-7/AC-12).
    """
    if _nombre_rol(db, usuario) != _ADMINISTRADOR:
        return False
    ids = (
        db.execute(
            select(Usuario.usuario_id)
            .join(Rol, Rol.rol_id == Usuario.rol_id)
            .where(Rol.nombre_rol == _ADMINISTRADOR)
            .with_for_update()
        )
        .scalars()
        .all()
    )
    otros_activos = 0
    for identificador in ids:
        if identificador == usuario.usuario_id:
            continue
        otro = db.get(Usuario, identificador)
        if otro is None:
            continue
        mapa = _mapa_por_correo(db_control, otro.correo)
        if mapa is None or mapa.activo:
            otros_activos += 1
    return otros_activos == 0


def cambiar_estado_usuario(
    db: Session,
    db_control: Session,
    usuario_id: int,
    activo: bool,
    identidad: IdentidadAutenticada | None = None,
    *,
    motivo=None,
    idempotencia: str | None = None,
    institucion_id: str | None = None,
) -> MapaUsuarioEsquema:
    """Activa o desactiva la vinculacion local de un usuario (D-3/D-5/AC-12).

    El estado vive en `mapa_usuario_esquema.activo`. Una baja/reactivacion
    efectiva exige motivo D-5; repetir el mismo estado no exige ni genera motivo.
    Una baja que dejaria cero Administradores activos, incluida la auto-baja,
    responde **409** sin cambiar usuario, mapa ni motivo. Un usuario inexistente o
    ajeno responde **404**.
    """
    institucion_actor = ambito_service.alcance_institucional(db, identidad)
    usuario = _usuario_en_alcance(db, usuario_id, institucion_actor)
    institucion = _institucion_de_mutacion(db, usuario, identidad, institucion_id)

    mapa = _mapa_por_correo(db_control, usuario.correo)
    actor = correo_del_actor(identidad)
    accion = "reactivacion_usuario" if activo else "baja_usuario"
    clave = idempotencia

    if mapa is not None and mapa.activo == activo:
        # Idempotente: ya esta en el estado pedido; no exige ni genera motivo.
        _completar_motivo_si_pendiente(
            db_control,
            motivo=motivo,
            clave=clave,
            actor_correo=actor,
            accion=accion,
            institucion_id=institucion,
            usuario=usuario,
        )
        return mapa

    if mapa is None and activo:
        # Sin mapa la asociacion se publica activa: no hay cambio de estado.
        mapa = MapaUsuarioEsquema(
            correo=security.normalizar_correo(str(usuario.correo)),
            institucion_id=institucion,
            nombre_esquema=_nombre_esquema_institucion(institucion),
            activo=True,
        )
        db_control.add(mapa)
        db_control.commit()
        return mapa

    if not activo:
        if _es_ultimo_administrador_activo(db, db_control, usuario):
            raise _conflicto(
                "No se puede dar de baja al ultimo Administrador activo de la "
                "institucion"
            )

    if motivo is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="El cambio de estado de un usuario exige un motivo del catalogo",
        )
    if not clave:
        clave = f"{accion}-{usuario.usuario_id}-{uuid4().hex}"

    if mapa is None:
        mapa = MapaUsuarioEsquema(
            correo=security.normalizar_correo(str(usuario.correo)),
            institucion_id=institucion,
            nombre_esquema=_nombre_esquema_institucion(institucion),
            activo=activo,
        )
        db_control.add(mapa)
    else:
        mapa.activo = activo
    db_control.commit()

    _persistir_motivo(
        db_control,
        motivo=motivo,
        clave=clave,
        actor_correo=actor,
        accion=accion,
        institucion_id=institucion,
        usuario=usuario,
    )
    return mapa


def _nombre_esquema_institucion(institucion_id: str) -> str:
    from app.services.tenant_service import nombre_esquema_para_institucion

    return nombre_esquema_para_institucion(institucion_id)
