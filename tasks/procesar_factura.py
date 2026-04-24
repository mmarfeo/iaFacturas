"""
Tarea Celery para procesamiento async de facturas en background.

Pipeline:
  Step 0 — OCR / pdfplumber  → texto
  Step 1 — regex_afip        → campos AFIP
  Step 2 — Validación CAE    → AFIP (preparado, activar en Fase 5)
  Step 3 — LLM fallback      → Ollama / OpenAI si confidence < 0.5
  Step 4 — Guardar en DB     → datos_extraidos (JSONB) + campos indexados
"""
import asyncio
from decimal import Decimal
from pathlib import Path

import redis

from tasks.celery_app import celery_app

_REDIS_TTL = 3600  # 1 hora


def _r():
    import os
    url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
    return redis.from_url(url, decode_responses=True)


def _set_step(r, factura_id: int, step: int, estado: str = "procesando"):
    key = f"factura:{factura_id}"
    r.setex(f"{key}:step",   _REDIS_TTL, step)
    r.setex(f"{key}:estado", _REDIS_TTL, estado)


def _serializable(v):
    if isinstance(v, Decimal):
        return float(v)
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return v


@celery_app.task(bind=True, name="tasks.procesar_factura.procesar", max_retries=2)
def procesar_factura(self, factura_id: int, archivo_path: str):
    r = _r()
    try:
        # ── Step 0: OCR ──────────────────────────────────────
        _set_step(r, factura_id, 0)
        from app.services.ocr import extraer_texto_pdf_sync
        texto = extraer_texto_pdf_sync(archivo_path)

        # ── Step 1: Regex AFIP ───────────────────────────────
        _set_step(r, factura_id, 1)
        from app.services.regex_afip import extraer_campos
        campos = extraer_campos(texto)
        confidence = campos.get("_confidence", 0)

        # ── Step 2: Validación CAE (Fase 5) ──────────────────
        _set_step(r, factura_id, 2)
        # TODO Fase 5: activar validación online en AFIP
        # if campos.get("cae") and campos.get("cuit_emisor"):
        #     from app.services.afip import validar_cae_sync
        #     cae_info = validar_cae_sync(campos["cae"], campos["cuit_emisor"])
        #     campos["cae_valido"] = cae_info.get("valido", False)
        campos["cae_valido"] = bool(campos.get("cae"))  # provisional

        # ── Step 3: LLM fallback ─────────────────────────────
        _set_step(r, factura_id, 3)
        if confidence < 0.5:
            try:
                from app.services.llm_extractor import extraer_con_llm_sync
                llm = extraer_con_llm_sync(texto)
                for k, v in llm.items():
                    if k not in campos or campos[k] is None:
                        campos[k] = v
            except Exception:
                pass

        # ── Step 4: Guardar en DB ────────────────────────────
        _set_step(r, factura_id, 4)
        asyncio.run(_guardar(factura_id, campos))

        _set_step(r, factura_id, 4, "done")
        return {"factura_id": factura_id, "estado": "done", "confidence": confidence}

    except Exception as exc:
        key = f"factura:{factura_id}"
        r.setex(f"{key}:estado", _REDIS_TTL, "error")
        r.setex(f"{key}:error",  _REDIS_TTL, str(exc))
        raise self.retry(exc=exc, countdown=30)


async def _guardar(factura_id: int, campos: dict):
    """Persiste el resultado en PostgreSQL (async)."""
    from app.core.database import AsyncSessionLocal
    from app.models.factura import Factura
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        res = await db.execute(select(Factura).where(Factura.id == factura_id))
        factura = res.scalar_one_or_none()
        if not factura:
            return

        # JSONB: serializar Decimal y date
        factura.datos_extraidos = {
            k: _serializable(v)
            for k, v in campos.items()
            if not k.startswith("_") and v is not None
        }

        # Campos indexados para búsquedas rápidas
        factura.cae             = campos.get("cae")
        factura.cae_valido      = campos.get("cae_valido")
        factura.cae_vencimiento = campos.get("cae_vencimiento")
        factura.cuit_emisor     = campos.get("cuit_emisor")
        factura.cuit_receptor   = campos.get("cuit_receptor")
        factura.importe         = campos.get("importe_total")
        factura.fecha_factura   = campos.get("fecha_emision")
        factura.estado          = "completado"

        await db.commit()
