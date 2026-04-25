"""
Pipeline OCR para extracción de texto de PDFs e imágenes.

Capas:
  1. pdfplumber  — PDFs digitales/nativos (texto embebido, < 1 s)
  2. Preprocessing + Tesseract — PDFs escaneados o imágenes (< 15 s)

Preprocessing pipeline:
  - detect_document()        : corrección de perspectiva (4 puntos) via OpenCV
  - preprocess_pipeline()    : para escaneos (deskew + denoise + adaptive threshold)
  - preprocess_pipeline_photo(): para fotos de celular (deskew suave + CLAHE)

La detección de foto vs escaneo se hace por heurística:
  - Si el archivo es imagen (jpg/png) → pipeline_photo
  - Si el PDF no tiene texto embebido pero la resolución original es baja → pipeline
  - Si es imagen de alta resolución capturada → pipeline_photo
"""
import asyncio
import os
from pathlib import Path
from typing import Optional, Tuple

# ─────────────────────────────────────────────────────────
# Importaciones opcionales: degradan elegantemente si faltan
# ─────────────────────────────────────────────────────────
try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

try:
    import pytesseract
    from PIL import Image as PILImage
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False

try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False

from app.core.config import settings

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp"}


# ═══════════════════════════════════════════════════════════
# DOCUMENT DETECTION — corrección de perspectiva
# ═══════════════════════════════════════════════════════════

def _order_points(pts):
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]
    rect[3] = pts[np.argmax(diff)]
    return rect


def _four_point_transform(image, pts):
    rect = _order_points(pts)
    (tl, tr, br, bl) = rect
    maxWidth  = max(int(np.linalg.norm(br - bl)), int(np.linalg.norm(tr - tl)))
    maxHeight = max(int(np.linalg.norm(tr - br)), int(np.linalg.norm(tl - bl)))
    dst = np.array([[0, 0], [maxWidth - 1, 0],
                    [maxWidth - 1, maxHeight - 1], [0, maxHeight - 1]], dtype="float32")
    M = cv2.getPerspectiveTransform(rect, dst)
    return cv2.warpPerspective(image, M, (maxWidth, maxHeight))


def detect_document(image):
    """
    Detecta y recorta el documento del fondo via contornos.
    Si no se detecta un cuadrilátero claro, devuelve la imagen original.
    """
    if not CV2_AVAILABLE:
        return image
    original = image.copy()
    gray    = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edged   = cv2.Canny(blurred, 75, 200)
    contours, _ = cv2.findContours(edged.copy(), cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    contours = sorted(contours, key=cv2.contourArea, reverse=True)[:5]
    for c in contours:
        peri  = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.02 * peri, True)
        if len(approx) == 4:
            warped = _four_point_transform(image, approx.reshape(4, 2))
            # Descartar si el resultado es demasiado pequeño (falso positivo)
            orig_area  = original.shape[0] * original.shape[1]
            warp_area  = warped.shape[0] * warped.shape[1]
            if warp_area >= orig_area * 0.25:
                return warped
    return original


# ═══════════════════════════════════════════════════════════
# PREPROCESSING PIPELINES
# ═══════════════════════════════════════════════════════════

def _deskew(image, max_angle: float = 45.0):
    gray   = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
    coords = np.column_stack(np.where(gray > 0))
    if len(coords) == 0:
        return image
    angle = cv2.minAreaRect(coords)[-1]
    angle = -(90 + angle) if angle < -45 else -angle
    (h, w) = image.shape[:2]
    M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
    return cv2.warpAffine(image, M, (w, h), flags=cv2.INTER_CUBIC,
                          borderMode=cv2.BORDER_REPLICATE)


def _deskew_soft(image, max_angle: float = 3.0):
    """Deskew conservador: solo corrige ángulos pequeños (fotos de celular)."""
    gray   = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
    coords = np.column_stack(np.where(gray > 0))
    if len(coords) == 0:
        return image
    angle = cv2.minAreaRect(coords)[-1]
    angle = -(90 + angle) if angle < -45 else -angle
    if abs(angle) > max_angle:
        return image
    (h, w) = image.shape[:2]
    M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
    return cv2.warpAffine(image, M, (w, h), flags=cv2.INTER_CUBIC,
                          borderMode=cv2.BORDER_REPLICATE)


def _adaptive_threshold(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
    return cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 2
    )


def _clahe_enhance(image):
    """Normalización de contraste/brillo para fotos irregulares."""
    gray  = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    return clahe.apply(gray)


def preprocess_pipeline(image):
    """Para escaneos: deskew completo + denoise + binarización adaptiva."""
    image = _deskew(image)
    image = cv2.GaussianBlur(image, (5, 5), 0)
    image = _adaptive_threshold(image)
    return image


def preprocess_pipeline_photo(image):
    """
    Para fotos de celular: deskew suave + denoise ligero + CLAHE.
    No binariza: Tesseract rinde mejor en escala de grises con fotos.
    """
    image = _deskew_soft(image, max_angle=3.0)
    image = cv2.GaussianBlur(image, (3, 3), 0)
    image = _clahe_enhance(image)
    return image


# ═══════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════

def _is_image_path(path: str) -> bool:
    return Path(path).suffix.lower() in _IMAGE_EXTS


def _pdf_has_embedded_text(path: str) -> bool:
    """Devuelve True si el PDF tiene texto embebido útil (no solo imagen)."""
    if not PDFPLUMBER_AVAILABLE:
        return False
    try:
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                txt = page.extract_text() or ""
                if len(txt.strip()) > 50:
                    return True
    except Exception:
        pass
    return False


def _pil_to_cv2_bgr(pil_img) -> "np.ndarray":
    img = np.array(pil_img)
    if img.ndim == 2:
        return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    if img.shape[2] == 4:
        return cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
    return cv2.cvtColor(img, cv2.COLOR_RGB2BGR)


# ═══════════════════════════════════════════════════════════
# EXTRACCIÓN PDFPLUMBER (capa 1)
# ═══════════════════════════════════════════════════════════

def _extraer_pdfplumber(path: str) -> str:
    if not PDFPLUMBER_AVAILABLE:
        return ""
    try:
        with pdfplumber.open(path) as pdf:
            partes = []
            for page in pdf.pages:
                txt = page.extract_text() or ""
                if txt.strip():
                    partes.append(txt)
            return "\n".join(partes)
    except Exception:
        return ""


# ═══════════════════════════════════════════════════════════
# EXTRACCIÓN OCR CON PREPROCESSING (capa 2)
# ═══════════════════════════════════════════════════════════

def _extraer_ocr(path: str, is_photo: bool = False) -> str:
    """
    Aplica preprocessing + Tesseract.
    is_photo=True → pipeline_photo (para imágenes de celular)
    is_photo=False → pipeline estándar (para escaneos/PDFs imagen)
    """
    if not TESSERACT_AVAILABLE or not CV2_AVAILABLE:
        return ""

    dpi = settings.ocr_dpi_photo if is_photo else settings.ocr_dpi

    try:
        if _is_image_path(path):
            pil_img = PILImage.open(path).convert("RGB")
            image   = _pil_to_cv2_bgr(pil_img)
        elif PDFPLUMBER_AVAILABLE:
            with pdfplumber.open(path) as pdf:
                if not pdf.pages:
                    return ""
                page    = pdf.pages[0]
                img     = page.to_image(resolution=dpi)
                image   = _pil_to_cv2_bgr(img.original)
        else:
            return ""

        original = image.copy()
        image    = detect_document(image)

        # Si detect_document devolvió algo raro, usar original
        orig_area = original.shape[0] * original.shape[1]
        curr_area = image.shape[0] * image.shape[1]
        if curr_area < orig_area * 0.3:
            image = original

        image = preprocess_pipeline_photo(image) if is_photo else preprocess_pipeline(image)

        config = "--oem 3 --psm 6"
        texto  = pytesseract.image_to_string(image, lang="spa+eng", config=config)
        return texto.strip()

    except Exception as e:
        print(f"[OCR ERROR] {e}")
        return ""


# ═══════════════════════════════════════════════════════════
# FUNCIÓN PRINCIPAL SYNC (Celery)
# ═══════════════════════════════════════════════════════════

def extraer_texto_pdf_sync(archivo_path: str) -> Tuple[str, str]:
    """
    Pipeline de extracción de texto.

    Retorna: (texto, metodo)
      metodo = "pdfplumber" | "ocr" | "ocr_photo" | ""

    Estrategia:
      1. pdfplumber (PDFs digitales — rápido, sin OCR)
      2. OCR estándar (PDFs escaneados)
      3. OCR foto si el archivo es imagen
    """
    path = str(archivo_path)
    is_image = _is_image_path(path)

    if not is_image:
        texto = _extraer_pdfplumber(path)
        if len(texto.strip()) > 100:
            return texto, "pdfplumber"

    # OCR
    is_photo = is_image  # imágenes directo = foto; PDFs sin texto = escaneo
    texto_ocr = _extraer_ocr(path, is_photo=is_photo)
    if texto_ocr.strip():
        metodo = "ocr_photo" if is_photo else "ocr"
        return texto_ocr, metodo

    return "", ""


# ═══════════════════════════════════════════════════════════
# WRAPPER ASYNC (FastAPI)
# ═══════════════════════════════════════════════════════════

async def extraer_texto_pdf(archivo_path: str) -> Tuple[str, str]:
    """Wrapper async de extraer_texto_pdf_sync (corre en threadpool)."""
    return await asyncio.to_thread(extraer_texto_pdf_sync, archivo_path)
