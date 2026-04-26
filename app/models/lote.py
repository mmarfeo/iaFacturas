from datetime import datetime
from sqlalchemy import Integer, String, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class Lote(Base):
    __tablename__ = "lotes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    usuario_id: Mapped[int] = mapped_column(Integer, ForeignKey("usuarios.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    # pendiente | procesando | completado | con_errores
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="pendiente")
    total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    procesados: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    errores: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    usuario: Mapped["Usuario"] = relationship("Usuario", back_populates="lotes")
    facturas: Mapped[list["Factura"]] = relationship("Factura", back_populates="lote")
