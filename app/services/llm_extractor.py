"""
Extracción de campos AFIP usando LLM (Ollama local o OpenAI como fallback).
Se invoca cuando el confidence de regex_afip < LLM_THRESHOLD.
"""
import json
import asyncio
from typing import Optional

import httpx

from app.core.config import settings

LLM_THRESHOLD = 0.5
_MAX_TEXTO = 4000  # tokens aproximados

_PROMPT = """\
Extraé los campos de la siguiente factura electrónica AFIP y respondé SOLO con JSON válido, sin texto adicional.

Campos requeridos (null si no se encuentra):
{
  "cae": "14 dígitos",
  "cae_vencimiento": "DD/MM/YYYY",
  "cuit_emisor": "XX-XXXXXXXX-X",
  "cuit_receptor": "XX-XXXXXXXX-X",
  "tipo_comprobante": "Factura A|B|C|M",
  "punto_venta": "XXXX",
  "numero": "XXXXXXXX",
  "fecha_emision": "DD/MM/YYYY",
  "importe_total": número,
  "importe_neto": número,
  "iva_21": número,
  "razon_social_emisor": "texto",
  "razon_social_receptor": "texto",
  "condicion_iva_emisor": "texto",
  "concepto": "texto"
}

Texto de la factura:
{texto}
"""


# ──────────────────────────────────────────────────────────
# Async  (FastAPI)
# ──────────────────────────────────────────────────────────

async def extraer_con_llm(texto: str) -> dict:
    """
    Intenta extracción con Ollama. Si falla o está deshabilitado,
    prueba OpenAI. Si ambos fallan, retorna dict vacío.
    """
    if settings.ollama_enabled:
        result = await _ollama(texto)
        if result:
            return result

    if settings.openai_api_key:
        result = await _openai(texto)
        if result:
            return result

    return {}


async def _ollama(texto: str) -> Optional[dict]:
    prompt = _PROMPT.format(texto=texto[:_MAX_TEXTO])
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{settings.ollama_url}/api/generate",
                json={"model": settings.ollama_model, "prompt": prompt, "stream": False, "format": "json"},
            )
            resp.raise_for_status()
            raw = resp.json().get("response", "{}")
            return json.loads(raw)
    except Exception:
        return None


async def _openai(texto: str) -> Optional[dict]:
    prompt = _PROMPT.format(texto=texto[:_MAX_TEXTO])
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                json={
                    "model": "gpt-4o-mini",
                    "messages": [{"role": "user", "content": prompt}],
                    "response_format": {"type": "json_object"},
                },
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            return json.loads(content)
    except Exception:
        return None


# ──────────────────────────────────────────────────────────
# Sync  (Celery — usa asyncio.run)
# ──────────────────────────────────────────────────────────

def extraer_con_llm_sync(texto: str) -> dict:
    try:
        return asyncio.run(extraer_con_llm(texto))
    except Exception:
        return {}
