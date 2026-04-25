"""
Extracción de campos usando LLM (Ollama local → OpenAI como fallback).

Mejoras sobre la versión anterior:
  - Prompt dinámico: solo pide al LLM los campos que regex NO encontró
  - Contexto del tipo de documento (FACTURA A, TRANSFERENCIA, etc.)
  - _reparar_json(): parsing tolerante con 3 estrategias
  - Semáforo asyncio para serializar llamadas a Ollama (evita saturación)
"""
import asyncio
import json
import re
from typing import Optional

import httpx

from app.core.config import settings

LLM_THRESHOLD = 0.5   # Confidence mínimo de regex para no llamar al LLM
_MAX_TEXTO    = 3500  # Caracteres máximos del documento enviados al LLM

# Semáforo: solo 1 llamada a Ollama a la vez
_OLLAMA_SEM = asyncio.Semaphore(1)

# Etiquetas legibles por tipo de documento
_TIPO_LABELS: dict[str, str] = {
    "factura_a":    "FACTURA ELECTRÓNICA TIPO A (AFIP/ARCA)",
    "factura_b":    "FACTURA ELECTRÓNICA TIPO B (AFIP/ARCA)",
    "factura_c":    "FACTURA ELECTRÓNICA TIPO C (AFIP/ARCA)",
    "nota_credito": "NOTA DE CRÉDITO (AFIP/ARCA)",
    "nota_debito":  "NOTA DE DÉBITO (AFIP/ARCA)",
    "remito":       "REMITO",
    "recibo":       "RECIBO",
}

# Hints específicos por familia de documento
_HINT_FACTURA = (
    "Para FACTURAS AFIP: cuit_emisor=CUIT del proveedor/emisor (parte superior); "
    "cuit_receptor=CUIT del cliente (debajo de 'Señores:' o 'Datos del Receptor'). "
    "Son SIEMPRE distintos. numero=8 dígitos, punto_venta=4 dígitos (ej: 0001 / 00000282). "
    "razon_social NO debe incluir fechas ni CUIT. cae=14 dígitos exactos. "
    "tipo_comprobante=Factura A, Factura B o Factura C."
)
_HINT_TRANSFERENCIA = (
    "Para TRANSFERENCIAS: banco_emisor=banco de origen; "
    "cbu_receptor=22 dígitos exactos (el último CBU/CVU en el doc); "
    "importe=monto transferido; nombre_receptor=destinatario/beneficiario; "
    "nombre_emisor=ordenante/remitente; fecha_ejecucion=fecha de la operación; "
    "numero_comprobante=ID o número de transacción."
)


def _tipo_label(tipo: str) -> str:
    if tipo.startswith("transferencia"):
        banco = tipo.replace("transferencia_", "").replace("_", " ").title()
        return f"COMPROBANTE DE TRANSFERENCIA BANCARIA ({banco})"
    return _TIPO_LABELS.get(tipo, tipo.upper())


def _reparar_json(texto: str) -> Optional[dict]:
    """
    Parsea JSON del LLM con tolerancia a errores comunes:
      1. JSON válido directo
      2. Limpiar trailing commas + comentarios
      3. Extraer pares clave:valor con regex (fallback)
    """
    # Extraer el bloque JSON más externo
    m = re.search(r'\{.*\}', texto, re.S)
    if not m:
        return None
    raw = m.group(0)

    # Intento 1: JSON directo
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Intento 2: limpiar problemas comunes
    limpio = raw
    limpio = re.sub(r'//[^\n]*', '', limpio)                          # quitar comentarios
    limpio = re.sub(r',\s*([}\]])', r'\1', limpio)                    # trailing commas
    limpio = re.sub(r'("(?:[^"\\]|\\.)*"|null|true|false|\d+)\s*\n\s*(")', r'\1,\n\2', limpio)  # comas faltantes
    try:
        return json.loads(limpio)
    except json.JSONDecodeError:
        pass

    # Intento 3: extracción campo por campo con regex (muy tolerante)
    resultado: dict = {}
    for kv in re.finditer(r'"([\w_]+)"\s*:\s*("(?:[^"\\]|\\.)*"|null|true|false|-?\d+(?:\.\d+)?)', limpio):
        k, v = kv.group(1), kv.group(2)
        try:
            resultado[k] = json.loads(v)
        except Exception:
            resultado[k] = v.strip('"')
    return resultado if resultado else None


def _construir_prompt(
    texto: str,
    tipo: str,
    campos_faltantes: list[str],
) -> str:
    """Construye prompt dinámico según tipo de documento y campos faltantes."""
    from app.services.document_classifier import es_transferencia

    label    = _tipo_label(tipo)
    hint     = _HINT_TRANSFERENCIA if es_transferencia(tipo) else _HINT_FACTURA
    pide_items = "items" in campos_faltantes

    items_instruccion = ""
    if pide_items:
        items_instruccion = (
            '\n\nIMPORTANTE para "items": devolvé un ARRAY JSON de strings, '
            'uno por línea de producto/servicio. Ej: '
            '"items": ["2 Unid. Producto A $1.000,00"]. Si no hay ítems, devolvé null.'
        )

    campos_json = "{" + ", ".join(
        f'"{c}": null' for c in campos_faltantes
    ) + "}"

    return (
        f"Estás analizando: {label}.\n{hint}{items_instruccion}\n\n"
        f"Texto del documento:\n---\n{texto[:_MAX_TEXTO]}\n---\n\n"
        f"Devolvé SOLO este JSON con los valores encontrados (null si no aparece):\n"
        f"{campos_json}"
    )


# ═══════════════════════════════════════════════════════════
# ASYNC (FastAPI)
# ═══════════════════════════════════════════════════════════

async def extraer_con_llm(
    texto: str,
    tipo: str = "factura_a",
    campos_faltantes: Optional[list[str]] = None,
) -> dict:
    """
    Extrae campos con LLM. Intenta Ollama primero, OpenAI como fallback.
    Si campos_faltantes es None, usa un set completo de campos de factura.
    """
    if campos_faltantes is None:
        campos_faltantes = [
            "cae", "cae_vencimiento", "cuit_emisor", "cuit_receptor",
            "tipo_comprobante", "punto_venta", "numero", "fecha_emision",
            "importe_total", "importe_neto", "razon_social_emisor",
            "razon_social_receptor", "condicion_venta", "concepto",
        ]

    if not campos_faltantes:
        return {}

    if settings.ollama_enabled:
        result = await _ollama(texto, tipo, campos_faltantes)
        if result:
            return result

    if settings.openai_api_key:
        result = await _openai(texto, tipo, campos_faltantes)
        if result:
            return result

    return {}


async def _ollama(texto: str, tipo: str, campos_faltantes: list[str]) -> Optional[dict]:
    prompt      = _construir_prompt(texto, tipo, campos_faltantes)
    num_predict = 512 if "items" in campos_faltantes else 256
    try:
        async with _OLLAMA_SEM:
            async with httpx.AsyncClient(timeout=90.0) as client:
                resp = await client.post(
                    f"{settings.ollama_url}/api/generate",
                    json={
                        "model":   settings.ollama_model,
                        "prompt":  prompt,
                        "stream":  False,
                        "options": {"temperature": 0.05, "num_predict": num_predict},
                    },
                )
                resp.raise_for_status()
                raw = resp.json().get("response", "{}")
        return _reparar_json(raw) or None
    except Exception as e:
        print(f"[OLLAMA ERROR] {e}")
        return None


async def _openai(texto: str, tipo: str, campos_faltantes: list[str]) -> Optional[dict]:
    prompt = _construir_prompt(texto, tipo, campos_faltantes)
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
        return _reparar_json(content) or None
    except Exception as e:
        print(f"[OPENAI ERROR] {e}")
        return None


# ═══════════════════════════════════════════════════════════
# SYNC (Celery — usa asyncio.run en thread separado)
# ═══════════════════════════════════════════════════════════

def extraer_con_llm_sync(
    texto: str,
    tipo: str = "factura_a",
    campos_faltantes: Optional[list[str]] = None,
) -> dict:
    """Versión sincrónica para Celery workers."""
    try:
        # Celery corre en un thread sin event loop propio
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(
                extraer_con_llm(texto, tipo, campos_faltantes)
            )
        finally:
            loop.close()
    except Exception:
        return {}
