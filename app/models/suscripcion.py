from datetime import datetime
from sqlalchemy import Integer, Boolean, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class Suscripcion(Base):
    __tablename__ = "suscripciones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    usuario_id: Mapped[int] = mapped_column(Integer, ForeignKey("usuarios.id"), nullable=False, index=True)
    plan_id: Mapped[int] = mapped_column(Integer, ForeignKey("planes.id"), nullable=False)
    fecha_inicio: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    fecha_vencimiento: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    activa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    usuario: Mapped["Usuario"] = relationship("Usuario", back_populates="suscripciones")
    plan: Mapped["Plan"] = relationship("Plan", back_populates="suscripciones")
