"""
AfipQrDecoder — Python port of the PHP AfipQrDecoder class (Dewoc CRM).

Decodes AFIP QR codes from:
  1. AFIP QR URLs: https://www.afip.gob.ar/fe/qr/?p=BASE64
  2. Raw JSON: {"ver":1,"cuit":...,"codAut":...}
  3. Raw base64 payload

Also provides read_qr_from_file() to extract QR payloads from PDF/image files
using OpenCV (already in requirements) and pdf2image.
"""
import base64
import json
import re
from typing import Optional
from urllib.parse import unquote


# ─── Lookup tables ────────────────────────────────────────────────────────────

_TIPO_COMPROBANTE: dict[int, str] = {
    1: "Factura A",
    2: "Nota de Débito A",
    3: "Nota de Crédito A",
    4: "Recibo A",
    5: "Nota de Venta al Contado A",
    6: "Factura B",
    7: "Nota de Débito B",
    8: "Nota de Crédito B",
    9: "Recibo B",
    10: "Nota de Venta al Contado B",
    11: "Factura C",
    12: "Nota de Débito C",
    13: "Nota de Crédito C",
    15: "Recibo C",
    19: "Factura E",
    20: "Nota de Débito E",
    21: "Nota de Crédito E",
    51: "Factura M",
    52: "Nota de Débito M",
    53: "Nota de Crédito M",
    201: "Factura de Crédito Electrónica MiPyME A",
    202: "Nota de Débito Electrónica MiPyME A",
    203: "Nota de Crédito Electrónica MiPyME A",
    206: "Factura de Crédito Electrónica MiPyME B",
    207: "Nota de Débito Electrónica MiPyME B",
    208: "Nota de Crédito Electrónica MiPyME B",
    211: "Factura de Crédito Electrónica MiPyME C",
    212: "Nota de Débito Electrónica MiPyME C",
    213: "Nota de Crédito Electrónica MiPyME C",
}

_MONEDA_NOMBRES: dict[str, str] = {
    "PES": "Pesos Argentinos (ARS)",
    "DOL": "Dólares Estadounidenses (USD)",
    "EUR": "Euros (EUR)",
    "BRL": "Reales Brasileños (BRL)",
}

_TIPO_DOC: dict[int, str] = {
    80: "CUIT", 86: "CUIL", 87: "CDI", 89: "LE", 90: "LC",
    91: "CI Extranjera", 92: "en trámite", 93: "Acta Nacim.",
    94: "CI Buenos Aires", 95: "CI Ciudad", 96: "DNI", 99: "Sin especificar",
}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _format_cuit(cuit: str) -> str:
    clean = re.sub(r"\D", "", cuit)
    if len(clean) == 11:
        return f"{clean[:2]}-{clean[2:10]}-{clean[10]}"
    return cuit


def _fmt_ars(v: float) -> str:
    """Format as Argentine peso: 1234567.89 → '$1.234.567,89'"""
    int_part = int(v)
    dec_part = round((v - int_part) * 100)
    # Format integer part with dots as thousand separator
    int_str = f"{int_part:,}".replace(",", ".")
    return f"${int_str},{dec_part:02d}"


def _normalize(data: dict, source_url: str) -> dict:
    tipo_cmp = int(data.get("tipoCmp", 0))
    moneda = str(data.get("moneda", "PES"))
    cuit = str(data.get("cuit", ""))
    nro_doc_rec = str(data.get("nroDocRec", ""))
    tipo_doc_rec = int(data.get("tipoDocRec", 80))
    pto_vta = int(data.get("ptoVta", 0))
    nro_cmp = int(data.get("nroCmp", 0))
    cod_aut = str(data.get("codAut", ""))
    importe = float(data.get("importe", 0.0))
    fecha = str(data.get("fecha", ""))

    # YYYY-MM-DD → DD/MM/YYYY
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", fecha)
    fecha_display = f"{m.group(3)}/{m.group(2)}/{m.group(1)}" if m else fecha

    return {
        "cuit_emisor": _format_cuit(cuit),
        "tipo_comprobante": _TIPO_COMPROBANTE.get(tipo_cmp, f"Tipo {tipo_cmp}"),
        "cod_comprobante": tipo_cmp,
        "punto_venta": f"{pto_vta:05d}",
        "numero_comprobante": f"{nro_cmp:08d}",
        "numero_completo": f"{pto_vta:05d}-{nro_cmp:08d}",
        "fecha": fecha_display,
        "fecha_iso": fecha,
        "importe": _fmt_ars(importe),
        "importe_raw": importe,
        "moneda": moneda,
        "moneda_nombre": _MONEDA_NOMBRES.get(moneda, moneda),
        "cotizacion": float(data.get("ctz", 1)),
        "tipo_doc_receptor": _TIPO_DOC.get(tipo_doc_rec, f"Doc {tipo_doc_rec}"),
        "nro_doc_receptor": _format_cuit(nro_doc_rec) if nro_doc_rec else "—",
        "tipo_cod_aut": str(data.get("tipoCodAut", "E")),
        "cae": cod_aut if cod_aut else "—",
        "afip_url": source_url,
        "version_qr": int(data.get("ver", 1)),
    }


def _decode_base64_payload(b64: str, source_url: str) -> Optional[dict]:
    """Decode a base64 string and parse as AFIP JSON. Returns None if invalid."""
    try:
        # Add padding if needed
        padding = 4 - len(b64) % 4
        if padding != 4:
            b64 += "=" * padding
        json_str = base64.b64decode(b64).decode("utf-8")
        data = json.loads(json_str)
        if not isinstance(data, dict) or "cuit" not in data or "codAut" not in data:
            return None
        return _normalize(data, source_url)
    except Exception:
        return None


# ─── Public API ───────────────────────────────────────────────────────────────

def decode_afip_url(url: str) -> Optional[dict]:
    """
    Decode an AFIP QR URL of the form:
      https://www.afip.gob.ar/fe/qr/?p=BASE64
    Also handles arca.gob.ar and any URL with a valid ?p= AFIP payload.
    Returns None if not a valid AFIP QR URL.
    """
    # Official AFIP/ARCA domain
    m = re.search(
        r"(?:afip\.gob\.ar|afip\.gov\.ar|arca\.gob\.ar)[^?]*\?.*\bp=([A-Za-z0-9+/%=_-]+)",
        url, re.IGNORECASE,
    )
    if m:
        return _decode_base64_payload(unquote(m.group(1)), url)

    # Fallback: any URL with ?p= that decodes to AFIP JSON
    if re.match(r"^https?://", url, re.IGNORECASE):
        m2 = re.search(r"\bp=([A-Za-z0-9+/%=_-]+)", url, re.IGNORECASE)
        if m2:
            return _decode_base64_payload(unquote(m2.group(1)), url)

    return None


def try_decode_raw_payload(payload: str) -> Optional[dict]:
    """
    Try to decode a QR payload that may be:
      - An AFIP QR URL
      - Raw JSON {"ver":1,"cuit":...,"codAut":...}
      - Raw base64 string
    """
    payload = payload.strip()

    if re.match(r"^https?://", payload, re.IGNORECASE):
        return decode_afip_url(payload)

    if payload.startswith("{"):
        try:
            data = json.loads(payload)
            if isinstance(data, dict) and "cuit" in data and "codAut" in data:
                return _normalize(data, "")
        except Exception:
            pass

    if re.match(r"^[A-Za-z0-9+/=]{20,}$", payload):
        return _decode_base64_payload(payload, "")

    return None


def decode_multiple(input_text: str) -> list[dict]:
    """
    Decode multiple AFIP QR URLs from a multi-line text (or CSV/TXT).
    Each line may have extra columns — the URL is extracted automatically.
    Returns a list of decoded dicts, or error entries for invalid lines.
    """
    results: list[dict] = []
    lines = re.split(r"[\r\n]+", input_text.strip())

    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        url_m = re.search(r"https?://[^\s,;\"']+", line, re.IGNORECASE)
        if url_m:
            decoded = decode_afip_url(url_m.group(0))
            if decoded:
                results.append(decoded)
                continue

        results.append({
            "error": "No se encontró una URL QR de AFIP válida en esta línea.",
            "input": line[:200] + "…" if len(line) > 200 else line,
        })

    return results


# ─── QR reading from files ────────────────────────────────────────────────────

_GS_DPIS = [300, 400, 600]
_MAX_PDF_PAGES = 5
# PDFs with large embedded images (scanned) already have enough resolution at 300 DPI;
# skip 600 DPI if the first raster exceeds this size to avoid timeout.
_GS_SKIP_HIGH_DPI_KB = 400


def _decode_bgr_image(img_bgr, detector) -> Optional[str]:
    """
    Try pyzbar (primary, ZXing-based) then OpenCV on multiple image variants.
    Mirrors the ZXing + upscale strategy used in QrDocumentDecoder.php.
    """
    import cv2
    import numpy as np

    h, w = img_bgr.shape[:2]
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    _, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # Build candidate images: original + upscales (x2, x3)
    base_variants = [img_bgr, gray, otsu]
    all_variants = list(base_variants)
    for factor in (2, 3):
        nw, nh = w * factor, h * factor
        all_variants.append(cv2.resize(img_bgr, (nw, nh), interpolation=cv2.INTER_CUBIC))
        all_variants.append(cv2.resize(gray, (nw, nh), interpolation=cv2.INTER_CUBIC))
        all_variants.append(cv2.resize(otsu, (nw, nh), interpolation=cv2.INTER_NEAREST))

    # pyzbar / ZXing — primary decoder
    try:
        from pyzbar.pyzbar import decode as pyzbar_decode
        for variant in all_variants:
            try:
                results = pyzbar_decode(variant)
            except Exception:
                continue
            for r in results:
                if r.type == "QRCODE" and r.data:
                    return r.data.decode("utf-8", errors="replace")
    except ImportError:
        pass

    # OpenCV fallback
    for variant in all_variants:
        try:
            data, _, _ = detector.detectAndDecode(variant)
            if data:
                return data
        except Exception:
            continue

    return None


def _rasterize_pdf_page_gs(pdf_bytes: bytes, page: int, dpi: int) -> Optional[bytes]:
    """
    Rasterize one PDF page to PNG bytes using the Ghostscript CLI.
    Returns PNG bytes or None on failure.
    """
    import subprocess
    import tempfile
    import os
    import shutil

    gs = shutil.which("gs") or shutil.which("gswin64c") or shutil.which("gswin32c")
    if gs is None:
        return None

    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = os.path.join(tmpdir, "input.pdf")
        out_path = os.path.join(tmpdir, "page.png")
        with open(pdf_path, "wb") as f:
            f.write(pdf_bytes)

        cmd = [
            gs,
            "-dQUIET", "-dSAFER", "-dBATCH", "-dNOPAUSE",
            "-sDEVICE=png16m",
            f"-r{dpi}",
            f"-dFirstPage={page}",
            f"-dLastPage={page}",
            f"-sOutputFile={out_path}",
            pdf_path,
        ]
        try:
            result = subprocess.run(cmd, timeout=90, capture_output=True)
        except Exception:
            return None

        if result.returncode != 0 or not os.path.isfile(out_path):
            return None

        file_size = os.path.getsize(out_path)
        if file_size < 64:
            return None

        with open(out_path, "rb") as f:
            return f.read()


def read_qr_from_image_bytes(image_bytes: bytes, mime_type: str) -> dict:
    """
    Read a QR code from image/PDF bytes.
    For PDFs: uses Ghostscript at 300/400/600 DPI (mirrors QrDocumentDecoder.php).
    For images: uses pyzbar (ZXing) + OpenCV with multiple upscale variants.

    Returns: {"payload": str|None, "error": str|None, "source": str}
    """
    import cv2
    import numpy as np

    detector = cv2.QRCodeDetector()

    if mime_type == "application/pdf":
        # Strategy 1: Ghostscript CLI (same as PHP — multiple DPIs per page)
        first_raster_kb: Optional[int] = None
        gs_available = True

        for page in range(1, _MAX_PDF_PAGES + 1):
            for dpi in _GS_DPIS:
                # Skip 600 DPI if first raster was large (already high-res PDF)
                if dpi == 600 and first_raster_kb is not None and first_raster_kb > _GS_SKIP_HIGH_DPI_KB:
                    continue

                png_bytes = _rasterize_pdf_page_gs(image_bytes, page, dpi)

                if png_bytes is None:
                    gs_available = False
                    break  # Ghostscript not available, fall through to pdf2image

                kb = len(png_bytes) // 1024
                if first_raster_kb is None:
                    first_raster_kb = kb

                arr = np.frombuffer(png_bytes, np.uint8)
                img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                if img is None:
                    continue

                payload = _decode_bgr_image(img, detector)
                if payload:
                    return {"payload": payload, "error": None, "source": f"pdf:p{page}:gs:{dpi}"}

            if not gs_available:
                break

        if gs_available:
            return {"payload": None, "error": "No se encontró código QR en el archivo", "source": "pdf:gs"}

        # Strategy 2: pdf2image fallback (when Ghostscript is not available)
        try:
            from pdf2image import convert_from_bytes
            pil_images = convert_from_bytes(
                image_bytes, dpi=300, first_page=1, last_page=_MAX_PDF_PAGES,
            )
        except Exception as e:
            return {"payload": None, "error": f"Error al convertir PDF: {e}", "source": "pdf2image"}

        for i, pil_img in enumerate(pil_images, start=1):
            rgb = np.array(pil_img.convert("RGB"))
            img = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
            payload = _decode_bgr_image(img, detector)
            if payload:
                return {"payload": payload, "error": None, "source": f"pdf:p{i}:pdf2image"}

        return {"payload": None, "error": "No se encontró código QR en el archivo", "source": "pdf2image"}

    else:
        arr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            return {"payload": None, "error": "No se pudo decodificar la imagen", "source": "cv2"}

        payload = _decode_bgr_image(img, detector)
        if payload:
            return {"payload": payload, "error": None, "source": "image"}

        return {"payload": None, "error": "No se encontró código QR en el archivo", "source": "image"}
