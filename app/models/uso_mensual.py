from sqlalchemy import Integer, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class UsoMensual(Base):
    __tablename__ = "uso_mensual"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    usuario_id: Mapped[int] = mapped_column(Integer, ForeignKey("usuarios.id"), nullable=False, index=True)
    mes: Mapped[int] = mapped_column(Integer, nullable=False)   # 1-12
    anio: Mapped[int] = mapped_column(Integer, nullable=False)
    cantidad_facturas: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("usuario_id", "mes", "anio", name="uq_uso_mensual_usuario_mes"),
    )

    usuario: Mapped["Usuario"] = relationship("Usuario", back_populates="uso_mensual")
