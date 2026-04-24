"""
Pipeline principal de extracción de facturas.

Flujo:
  1. OCR / pdfplumber  → texto crudo
  2. regex_afip        → campos estructurados + confidence
  3. LLM (Ollama/OAI)  → fallback si confidence < LLM_THRESHOLD
"""
import asyncio
from decimal import Decimal
from typing import Any

from app.services.ocr import extraer_texto_pdf_sync
from app.services.regex_afip import extraer_campos
from app.services.llm_extractor import LLM_THRESHOLD


# ──────────────────────────────────────────────────────────
# Helpers de serialización
# ──────────────────────────────────────────────────────────

def _serializable(v: Any) -> Any:
    """Convierte tipos no serializables a str para guardar en JSONB."""
    if isinstance(v, Decimal):
        return float(v)
    if hasattr(v, 'isoformat'):   # date / datetime
        return v.isoformat()
    return v


def _limpiar(campos: dict) -> dict:
    """Elimina claves internas (_confidence, _texto_len) y serializa."""
    return {
        k: _serializable(v)
        for k, v in campos.items()
        if not k.startswith('_') and v is not None
    }


# ──────────────────────────────────────────────────────────
# Sync  (Celery)
# ──────────────────────────────────────────────────────────

def extraer_factura_sync(archivo_path: str) -> dict:
    """
    Pipeline completo (sincrónico).
    Retorna dict limpio listo para guardar en datos_extraidos (JSONB).
    """
    texto = extraer_texto_pdf_sync(archivo_path)
    campos = extraer_campos(texto)
    confidence = campos.get('_confidence', 0)

    if confidence < LLM_THRESHOLD:
        try:
            from app.services.llm_extractor import extraer_con_llm_sync
            llm = extraer_con_llm_sync(texto)
            for k, v in llm.items():
                if k not in campos or campos[k] is None:
                    campos[k] = v
        except Exception:
            pass

    return {
        'campos': _limpiar(campos),
        'confidence': confidence,
        'texto_len': campos.get('_texto_len', 0),
    }


# ──────────────────────────────────────────────────────────
# Async  (FastAPI — en caso de uso directo sin Celery)
# ──────────────────────────────────────────────────────────

async def extraer_factura(archivo_path: str) -> dict:
    """Wrapper async del pipeline (corre sync en threadpool)."""
    return await asyncio.to_thread(extraer_factura_sync, archivo_path)
