from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    app_env: str = "production"
    app_url: str = "https://iafacturas.dewoc.com"
    secret_key: str

    # Base de datos
    database_url: str  # postgresql+asyncpg://...

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # Ollama (LLM en host del VPS)
    ollama_url: str = "http://host.docker.internal:11434"
    ollama_model: str = "qwen2.5:7b"
    ollama_enabled: bool = True

    # OpenAI (fallback)
    openai_api_key: Optional[str] = None

    # Email
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "noreply@iafacturas.dewoc.com"

    # MercadoPago
    mercadopago_access_token: Optional[str] = None
    mercadopago_webhook_secret: Optional[str] = None

    # VPS document-ai (extracción con plantillas)
    vps_extract_url: str = "http://localhost:8001"
    vps_api_key: str = "demo_key_123"

    # OCR
    ocr_dpi: int = 200            # DPI para escaneos
    ocr_dpi_photo: int = 300      # DPI para fotos de celular
    ocr_conf_threshold: int = 30  # Confianza mínima Tesseract (0-100)

    # AFIP
    afip_cache_ttl: int = 3600    # TTL caché Redis respuestas AFIP (segundos)

    @property
    def is_dev(self) -> bool:
        return self.app_env == "development"


settings = Settings()
