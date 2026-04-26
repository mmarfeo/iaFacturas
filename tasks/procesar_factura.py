"""
Tarea Celery para procesamiento asíncrono de facturas/documentos en background.

Pipeline completo:
  Step 0 — OCR / pdfplumber      → texto crudo + método
  Step 1 — Clasificación          → tipo de documento + confianza
  Step 2 — Regex AFIP/Transferencia → campos estructurados + confidence
  Step 3 — LLM fallback           → Ollama/OpenAI si confidence < LLM_THRESHOLD
  Step 4 — Validación CAE AFIP    → estado VIGENTE/VENCIDO + caché Redis
  Step 5 — Guardar en DB          → datos_extraidos (JSONB) + campos indexados
"""
import asyncio
from decimal import Decimal
from pathlib import Path

import redis

from tasks.celery_app import celery_app
from app.services.llm_extractor import LLM_THRESHOLD

_REDIS_TTL = 3600  # 1 hora


def _r():
    import os
    url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
    return redis.from_url(url, decode_responses=True)


def _set_step(r, factura_id: int, step: int, estado: str = "procesando", error: str = ""):
    key = f"factura:{factura_id}"
    r.setex(f"{key}:step",   _REDIS_TTL, step)
    r.setex(f"{key}:estado", _REDIS_TTL, estado)
    if error:
        r.setex(f"{key}:error", _REDIS_TTL, error)


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
        # ── Step 0: OCR / pdfplumber ─────────────────────────────────────────
        _set_step(r, factura_id, 0)
        from app.services.ocr import extraer_texto_pdf_sync
        texto, metodo_ocr = extraer_texto_pdf_sync(archivo_path)

        if not texto.strip():
            _set_step(r, factura_id, 0, "error", "No se pudo extraer texto del documento")
            asyncio.run(_guardar_error(factura_id, "No se pudo extraer texto del documento"))
            return

        # ── Step 1: Clasificar tipo de documento ────────────────────────────
        _set_step(r, factura_id, 1)
        from app.services.document_classifier import clasificar_documento
        tipo_doc, confianza_tipo = clasificar_documento(texto)

        # ── Step 2: Regex según tipo ─────────────────────────────────────────
        _set_step(r, factura_id, 2)
        from app.services.regex_afip import extraer_campos
        campos = extraer_campos(texto, tipo=tipo_doc)
        confidence = campos.get("_confidence", 0)

        # ── Step 3: LLM fallback si confidence baja ──────────────────────────
        _set_step(r, factura_id, 3)
        metodo_final = metodo_ocr
        if confidence < LLM_THRESHOLD:
            try:
                from app.services.llm_extractor import extraer_con_llm_sync

                # Calcular campos faltantes para el prompt dinámico
                campos_clave = _campos_clave_para_tipo(tipo_doc)
                campos_faltantes = [
                    c for c in campos_clave
                    if not campos.get(c)
                ]

                llm = extraer_con_llm_sync(texto, tipo=tipo_doc, campos_faltantes=campos_faltantes)
                for k, v in llm.items():
                    if not k.startswith("_") and (k not in campos or campos[k] is None):
                        campos[k] = v

                metodo_final = f"{metodo_ocr}+llm" if metodo_ocr else "llm"
            except Exception as e:
                print(f"[LLM ERROR] factura_id={factura_id}: {e}")

        # ── Step 4: Validación CAE con AFIP ──────────────────────────────────
        _set_step(r, factura_id, 4)
        cae_valido = None
        if campos.get("cae") and campos.get("cuit_emisor"):
            try:
                from app.services.afip import validar_cae_sync
                cae_info = validar_cae_sync(campos["cae"], campos["cuit_emisor"])
                campos["cae_valido"]      = cae_info.get("valido", False)
                campos["cae_estado"]      = cae_info.get("estado", "NO_ENCONTRADO")
                campos["cae_vencimiento"] = cae_info.get("vencimiento")
                cae_valido = cae_info.get("valido", False)
            except Exception as e:
                print(f"[AFIP ERROR] factura_id={factura_id}: {e}")
                campos["cae_valido"] = bool(campos.get("cae"))  # fallback provisional
                cae_valido = campos["cae_valido"]
        else:
            campos["cae_valido"] = bool(campos.get("cae"))
            cae_valido = campos["cae_valido"]

        # ── Step 5: Guardar en DB ─────────────────────────────────────────────
        _set_step(r, factura_id, 5)
        lote_id = asyncio.run(_guardar(factura_id, campos, tipo_doc, metodo_final))
        if lote_id:
            asyncio.run(_actualizar_lote(lote_id))

        _set_step(r, factura_id, 5, "done")
        return {
            "factura_id": factura_id,
            "estado":     "done",
            "tipo":       tipo_doc,
            "metodo":     metodo_final,
            "confidence": confidence,
            "cae_valido": cae_valido,
        }

    except Exception as exc:
        _set_step(r, factura_id, 0, "error", str(exc))
        # Intentar actualizar stats del lote aunque haya error
        try:
            lote_id = asyncio.run(_get_lote_id(factura_id))
            if lote_id:
                asyncio.run(_actualizar_lote(lote_id))
        except Exception:
            pass
        raise self.retry(exc=exc, countdown=30)


def _campos_clave_para_tipo(tipo: str) -> list[str]:
    """Retorna los campos más importantes según el tipo de documento."""
    from app.services.document_classifier import es_transferencia
    if es_transferencia(tipo):
        return ["importe", "fecha_ejecucion", "cbu_receptor", "nombre_receptor",
                "nombre_emisor", "numero_comprobante", "concepto"]
    return ["cae", "cae_vencimiento", "cuit_emisor", "cuit_receptor",
            "tipo_comprobante", "punto_venta", "numero", "fecha_emision",
            "importe_total", "importe_neto", "razon_social_emisor",
            "razon_social_receptor", "condicion_venta", "concepto"]


async def _get_lote_id(factura_id: int):
    from app.core.database import AsyncSessionLocal
    from app.models.factura import Factura
    from sqlalchemy import select
    async with AsyncSessionLocal() as db:
        res = await db.execute(select(Factura.lote_id).where(Factura.id == factura_id))
        row = res.scalar_one_or_none()
        return row


async def _actualizar_lote(lote_id: int):
    """Recalcula y persiste los stats del lote."""
    from app.core.database import AsyncSessionLocal
    from app.models.factura import Factura
    from app.models.lote import Lote
    from sqlalchemy import select, func

    async with AsyncSessionLocal() as db:
        stats = (await db.execute(
            select(
                func.count(Factura.id).label("total"),
                func.count(Factura.id).filter(Factura.estado == "completado").label("procesados"),
                func.count(Factura.id).filter(Factura.estado == "error").label("errores"),
            ).where(Factura.lote_id == lote_id)
        )).one()

        procesados = stats.procesados or 0
        errores    = stats.errores or 0
        total      = stats.total or 0

        res = await db.execute(select(Lote).where(Lote.id == lote_id))
        lote = res.scalar_one_or_none()
        if not lote:
            return

        lote.total      = total
        lote.procesados = procesados
        lote.errores    = errores
        if procesados + errores >= total and total > 0:
            lote.estado = "con_errores" if errores > 0 else "completado"
        else:
            lote.estado = "procesando"
        await db.commit()


async def _guardar(factura_id: int, campos: dict, tipo_doc: str, metodo: str):
    """Persiste el resultado en PostgreSQL. Retorna lote_id si tiene."""
    from app.core.database import AsyncSessionLocal
    from app.models.factura import Factura
    from sqlalchemy import select
    from datetime import date

    async with AsyncSessionLocal() as db:
        res = await db.execute(select(Factura).where(Factura.id == factura_id))
        factura = res.scalar_one_or_none()
        if not factura:
            return None

        # Serializar todo a tipos JSON-compatibles para JSONB
        factura.datos_extraidos = {
            k: _serializable(v)
            for k, v in campos.items()
            if not k.startswith("_") and v is not None
        }

        # Campos indexados para búsquedas rápidas
        factura.cae             = campos.get("cae")
        factura.cae_valido      = campos.get("cae_valido")

        # Fecha de vencimiento del CAE (puede venir como str o date)
        vto_raw = campos.get("cae_vencimiento")
        if isinstance(vto_raw, str):
            try:
                from datetime import datetime
                factura.cae_vencimiento = datetime.strptime(vto_raw, "%Y-%m-%d").date()
            except Exception:
                factura.cae_vencimiento = None
        else:
            factura.cae_vencimiento = vto_raw

        factura.cuit_emisor     = campos.get("cuit_emisor")
        factura.cuit_receptor   = campos.get("cuit_receptor")
        factura.importe         = campos.get("importe_total") or campos.get("importe")
        factura.fecha_factura   = campos.get("fecha_emision") or campos.get("fecha_ejecucion")
        factura.tipo_documento  = tipo_doc
        factura.metodo_extraccion = metodo
        factura.estado          = "completado"

        lote_id = factura.lote_id
        await db.commit()
        return lote_id


async def _guardar_error(factura_id: int, mensaje: str):
    """Marca la factura como error en DB."""
    from app.core.database import AsyncSessionLocal
    from app.models.factura import Factura
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        res = await db.execute(select(Factura).where(Factura.id == factura_id))
        factura = res.scalar_one_or_none()
        if not factura:
            return
        factura.estado          = "error"
        factura.datos_extraidos = {"error": mensaje}
        lote_id = factura.lote_id
        await db.commit()
        if lote_id:
            await _actualizar_lote(lote_id)
