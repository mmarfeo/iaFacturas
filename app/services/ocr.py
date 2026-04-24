"""
Extracción de texto de PDFs.
Pipeline:
  1. pdfplumber  — PDFs digitales/nativos (texto embebido)
  2. pytesseract — fallback OCR para PDFs escaneados (imagen)
"""
import asyncio
from pathlib import Path


# ──────────────────────────────────────────────────────────
# Versión SYNC  (usada por Celery y por asyncio.to_thread)
# ──────────────────────────────────────────────────────────

def extraer_texto_pdf_sync(archivo_path: str) -> str:
    """
    Extrae texto de un PDF.
    Retorna el texto crudo (puede contener saltos de línea y espacios extra).
    """
    path = Path(archivo_path)
    texto = ""

    # Intento 1: pdfplumber (rápido, sin OCR)
    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                texto += page_text + "\n"
    except Exception:
        pass

    # Si obtuvimos texto suficiente (> 100 chars), ya está
    if len(texto.strip()) > 100:
        return texto

    # Intento 2: OCR con pytesseract + pdf2image
    try:
        from pdf2image import convert_from_path
        import pytesseract

        images = convert_from_path(str(path), dpi=300)
        ocr_text = ""
        for img in images:
            ocr_text += pytesseract.image_to_string(img, lang="spa") + "\n"
        if ocr_text.strip():
            texto = ocr_text
    except Exception:
        pass  # Si falla el OCR devolvemos lo que tenemos

    return texto


# ──────────────────────────────────────────────────────────
# Versión ASYNC  (usada por los endpoints FastAPI)
# ──────────────────────────────────────────────────────────

async def extraer_texto_pdf(archivo_path: str) -> str:
    """Wrapper async de extraer_texto_pdf_sync (corre en threadpool)."""
    return await asyncio.to_thread(extraer_texto_pdf_sync, archivo_path)
