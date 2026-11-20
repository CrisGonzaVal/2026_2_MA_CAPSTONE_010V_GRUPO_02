from sqlalchemy import (
    CheckConstraint,
    Column,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class Usuario(Base):
    __tablename__ = "usuario"
    __table_args__ = (
        # Feature 026 (K-01): el correo se guarda canonico; `security.normalizar_correo`
        # lo hace en el servicio y este check cierra las escrituras directas.
        CheckConstraint(
            "correo = lower(trim(correo)) AND length(correo) > 0",
            name="usuario_correo_canonico_ck",
        ),
    )

    usuario_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    nombre = Column(String(100), nullable=False)
    apellido = Column(String(100), nullable=False)
    correo = Column(String(150), nullable=False, unique=True, index=True)
    departamento_id = Column(Integer, ForeignKey("departamento.departamento_id"), nullable=False)
    rol_id = Column(Integer, ForeignKey("rol.rol_id"), nullable=False)
    #: Sede asignada al Bodeguero (Feature 011, spec D-5/D-7). Nullable: la
    #: obligatoriedad es operativa, y un usuario que no es Bodeguero no necesita
    #: sede. La gestiona el Administrador institucional por API (Feature 011) y la
    #: administracion completa de usuarios sigue en la Feature 012.
    sede_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("sede.sede_id"), nullable=True
    )

    departamento = relationship("Departamento", back_populates="usuarios")
    rol = relationship("Rol", back_populates="usuarios")
    tickets = relationship("Ticket", back_populates="usuario")
    sede = relationship(
        "Sede",
        primaryjoin="Usuario.sede_id == Sede.sede_id",
        foreign_keys="Usuario.sede_id",
    )


# Feature 026: indice P0 de usuarios por departamento y unicidad funcional del
# correo (minusculas y sin espacios exteriores).
Index(
    "usuario_departamento_idx",
    Usuario.departamento_id,
)
Index(
    "usuario_correo_normalizado_uk",
    func.lower(func.trim(Usuario.correo)),
    unique=True,
)
