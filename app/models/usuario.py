from datetime import datetime
from typing import Optional
from sqlalchemy import Integer, String, Boolean, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    plan_id: Mapped[int] = mapped_column(Integer, ForeignKey("planes.id"), nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    # API key para acceso externo (POST /api/v1/documentos)
    api_key: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, unique=True, index=True)

    plan: Mapped["Plan"] = relationship("Plan", back_populates="usuarios")
    lotes: Mapped[list["Lote"]] = relationship("Lote", back_populates="usuario")
    facturas: Mapped[list["Factura"]] = relationship("Factura", back_populates="usuario")
    suscripciones: Mapped[list["Suscripcion"]] = relationship("Suscripcion", back_populates="usuario")
    uso_mensual: Mapped[list["UsoMensual"]] = relationship("UsoMensual", back_populates="usuario")
