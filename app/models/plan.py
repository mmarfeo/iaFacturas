from sqlalchemy import Integer, String, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class Plan(Base):
    __tablename__ = "planes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    limite_mensual: Mapped[int] = mapped_column(Integer, nullable=False)  # -1 = ilimitado
    precio: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    descripcion: Mapped[str] = mapped_column(Text, nullable=True)

    usuarios: Mapped[list["Usuario"]] = relationship("Usuario", back_populates="plan")
    suscripciones: Mapped[list["Suscripcion"]] = relationship("Suscripcion", back_populates="plan")
