"""
Router de validación CAE — Fase 5.

Endpoints existentes:
  GET  /cae/validar?cae=X&cuit=Y   — valida un CAE online con AFIP
  GET  /cae/validar/local?cae=X    — validación local (sin red, por fecha embebida)

Nuevos endpoints (página Consultar CAE):
  GET  /app/consultar-cae          — página completa de consulta
  POST /cae/lookup-urls            — decodifica URLs QR de AFIP (textarea/CSV)
  POST /cae/upload-docs            — sube archivos y lee QR con OpenCV
  POST /cae/validate-url           — valida una URL AFIP en línea (estado + importe)
"""
import asyncio
import re

import httpx
from fastapi import APIRouter, Depends, Query, Request, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from app.core.auth import get_current_user
from app.services.afip import validar_cae, _validar_cae_local
from app.services import afip_qr_decoder as qr

router = APIRouter(prefix="/cae", tags=["CAE / AFIP"])
templates = Jinja2Templates(directory="app/templates")

_ALLOWED_MIME = {"application/pdf", "image/jpeg", "image/png", "image/webp"}


# ── Página completa ────────────────────────────────────────────────────────────

@router.get("/consultar", response_class=HTMLResponse, include_in_schema=False)
async def consultar_cae_page(request: Request, user=Depends(get_current_user)):
    if not user:
        from fastapi.responses import RedirectResponse
        return RedirectResponse("/auth/login")
    return templates.TemplateResponse("app/consultar_cae.html", {
        "request": request, "user": user, "current_page": "consultar_cae",
    })


# ── Endpoints AJAX ─────────────────────────────────────────────────────────────

@router.post("/lookup-urls")
async def lookup_urls(request: Request, user=Depends(get_current_user)):
    """
    Decodifica múltiples URLs QR de AFIP pegadas en el textarea o en un CSV/TXT subido.
    Body form: qr_urls (texto), csv_file (opcional)
    Respuesta: {"results": [...]}
    """
    if not user:
        return JSONResponse({"error": "No autorizado"}, status_code=401)

    form = await request.form()
    raw_text = str(form.get("qr_urls", "")).strip()

    # Si se subió un archivo CSV/TXT, agregar su contenido
    csv_file = form.get("csv_file")
    if csv_file and hasattr(csv_file, "read"):
        try:
            csv_bytes = await csv_file.read()
            raw_text += "\n" + csv_bytes.decode("utf-8", errors="replace")
        except Exception:
            pass

    if not raw_text.strip():
        return JSONResponse({"results": [], "error": "No se recibió texto."})

    results = qr.decode_multiple(raw_text)
    return JSONResponse({"results": results})


@router.post("/upload-docs")
async def upload_docs(
    request: Request,
    user=Depends(get_current_user),
    documents: list[UploadFile] = File(...),
):
    """
    Sube archivos (PDF/JPG/PNG/WebP), lee el QR de cada uno con OpenCV
    y decodifica los datos AFIP del payload.
    Respuesta: {"results": [...]}
    """
    if not user:
        return JSONResponse({"error": "No autorizado"}, status_code=401)

    results: list[dict] = []

    for upload in documents:
        filename = upload.filename or "archivo"
        content_type = upload.content_type or ""

        if content_type not in _ALLOWED_MIME:
            results.append({
                "error": f"Tipo de archivo no permitido ({content_type}).",
                "archivo": filename,
            })
            continue

        try:
            file_bytes = await upload.read()
        except Exception:
            results.append({"error": "No se pudo leer el archivo.", "archivo": filename})
            continue

        # Ejecutar el procesamiento (bloqueante) en un thread
        decoded_qr = await asyncio.to_thread(
            qr.read_qr_from_image_bytes, file_bytes, content_type
        )

        if decoded_qr["payload"] is None:
            results.append({
                "error": decoded_qr["error"] or "No se encontró código QR.",
                "archivo": filename,
            })
            continue

        afip_data = qr.try_decode_raw_payload(decoded_qr["payload"])
        if afip_data is None:
            results.append({
                "error": "QR leído pero no contiene datos AFIP válidos.",
                "archivo": filename,
                "qr_raw": decoded_qr["payload"][:200],
            })
            continue

        afip_data["archivo"] = filename
        results.append(afip_data)

    return JSONResponse({"results": results})


@router.post("/validate-url")
async def validate_afip_url(request: Request, user=Depends(get_current_user)):
    """
    Valida una URL QR de AFIP consultando la página oficial de AFIP/ARCA.
    Extrae también el importe del payload base64 de la propia URL.
    Body form: afip_url
    Respuesta: {"status": "valid"|"invalid"|"unknown"|"error", "message": str,
                "importe_afip": float|null, "observacion": str|null, "diferencia": float|null}
    """
    if not user:
        return JSONResponse({"error": "No autorizado"}, status_code=401)

    form = await request.form()
    afip_url = str(form.get("afip_url", "")).strip()

    if not afip_url or not re.match(r"^https?://", afip_url, re.IGNORECASE):
        return JSONResponse({"status": "error", "message": "URL inválida"})

    # Solo permitir dominios oficiales AFIP / ARCA
    from urllib.parse import urlparse
    host = (urlparse(afip_url).hostname or "").lower()
    if not re.search(r"(?:^|\.)(afip|arca)\.gob\.ar$", host):
        return JSONResponse({"status": "error", "message": "URL no pertenece a AFIP/ARCA"})

    # Extraer importe del payload base64 de la URL (sin llamar a AFIP)
    qr_data = qr.decode_afip_url(afip_url)
    importe_afip: float | None = qr_data.get("importe_raw") if qr_data else None

    try:
        async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
            resp = await client.get(
                afip_url,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; IAFacturas/1.0)",
                    "Accept": "text/html,application/xhtml+xml",
                },
            )
    except Exception as e:
        return JSONResponse({"status": "error", "message": f"Sin respuesta de AFIP ({e})"})

    if resp.status_code != 200:
        return JSONResponse({
            "status": "error",
            "message": f"AFIP respondió HTTP {resp.status_code}",
        })

    body_lower = resp.text.lower()

    # Indicadores negativos
    negative = [
        "no encontrado", "no existe", "inválido", "invalido",
        "no válido", "no valido", "código de autorización no",
    ]
    if any(kw in body_lower for kw in negative):
        return JSONResponse({"status": "invalid", "message": "CAE no encontrado en AFIP"})

    # Indicadores positivos
    positive = "cae" in body_lower and any(
        kw in body_lower for kw in ["comprobante", "importe", "fecha"]
    )

    if positive:
        observacion = None
        diferencia = None
        if importe_afip is not None and importe_afip >= 100_000_000 and (importe_afip % 100) < 0.01:
            probable = importe_afip / 100.0
            diferencia = importe_afip - probable
            from app.services.afip_qr_decoder import _fmt_ars
            observacion = (
                f"Posible error de unidad en el QR: importe codificado en centavos "
                f"en vez de pesos. Valor probable en pesos: {_fmt_ars(probable)}"
            )
        return JSONResponse({
            "status": "valid",
            "message": "Verificado en AFIP",
            "importe_afip": importe_afip,
            "observacion": observacion,
            "diferencia": diferencia,
        })

    return JSONResponse({
        "status": "unknown",
        "message": "AFIP respondió pero no se pudo determinar el estado",
    })


# ── Endpoints originales ───────────────────────────────────────────────────────

@router.get("/validar")
async def validar_cae_endpoint(
    cae:  str = Query(..., description="CAE de 14 dígitos", min_length=14, max_length=14),
    cuit: str = Query(..., description="CUIT del emisor (con o sin guiones)"),
    user=Depends(get_current_user),
):
    """
    Valida un CAE contra el webservice de AFIP.
    Resultado cacheado en Redis por 1 hora para evitar sobrecarga.
    """
    if not user:
        return JSONResponse({"error": "No autorizado"}, status_code=401)
    resultado = await validar_cae(cae, cuit)
    return JSONResponse({
        "valido":      resultado["valido"],
        "estado":      resultado["estado"],
        "cae":         resultado["cae"],
        "vencimiento": resultado["vencimiento"],
    })


@router.get("/validar/local")
async def validar_cae_local_endpoint(
    cae: str = Query(..., description="CAE de 14 dígitos", min_length=14, max_length=14),
    user=Depends(get_current_user),
):
    """Validación local del CAE sin consultar AFIP."""
    if not user:
        return JSONResponse({"error": "No autorizado"}, status_code=401)
    resultado = _validar_cae_local(cae)
    return JSONResponse({
        "valido":      resultado["valido"],
        "estado":      resultado["estado"],
        "cae":         resultado["cae"],
        "vencimiento": resultado["vencimiento"],
    })
