from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import Integer, String, Boolean, DateTime, Date, Numeric, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB
from app.core.database import Base


class Factura(Base):
    __tablename__ = "facturas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    usuario_id: Mapped[int] = mapped_column(Integer, ForeignKey("usuarios.id"), nullable=False, index=True)
    lote_id: Mapped[int] = mapped_column(Integer, ForeignKey("lotes.id"), nullable=True, index=True)

    # Archivo
    archivo_path: Mapped[str] = mapped_column(String(500), nullable=False)

    # Datos extraídos (resultado completo como JSONB)
    datos_extraidos: Mapped[dict] = mapped_column(JSONB, nullable=True)

    # Campos indexados para búsqueda rápida
    cae: Mapped[str] = mapped_column(String(20), nullable=True, index=True)
    cae_valido: Mapped[bool] = mapped_column(Boolean, nullable=True)
    cae_vencimiento: Mapped[date] = mapped_column(Date, nullable=True)
    cuit_emisor: Mapped[str] = mapped_column(String(13), nullable=True, index=True)
    cuit_receptor: Mapped[str] = mapped_column(String(13), nullable=True)
    importe: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=True)
    fecha_factura: Mapped[date] = mapped_column(Date, nullable=True)

    # Tipo de documento y método de extracción (poblados por el pipeline)
    tipo_documento: Mapped[str] = mapped_column(String(40), nullable=True)
    # factura_a | factura_b | factura_c | nota_credito | transferencia_* | desconocido
    metodo_extraccion: Mapped[str] = mapped_column(String(30), nullable=True)
    # pdfplumber | ocr | ocr_photo | pdfplumber+llm | ocr+llm

    # Estado del procesamiento
    estado: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pendiente"
    )  # pendiente | procesando | completado | error

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    usuario: Mapped["Usuario"] = relationship("Usuario", back_populates="facturas")
    lote: Mapped["Lote"] = relationship("Lote", back_populates="facturas")
