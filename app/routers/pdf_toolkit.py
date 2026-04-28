"""
Router de Herramientas PDF.

Endpoints:
  GET  /pdf-toolkit/herramientas   — página HTML
  POST /pdf-toolkit/info           — devuelve cantidad de páginas de un PDF
  POST /pdf-toolkit/split          — divide PDF(s) y retorna ZIP
"""
import asyncio
from io import BytesIO

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from app.core.auth import get_current_user
from app.services import pdf_toolkit as svc

router = APIRouter(prefix="/pdf-toolkit", tags=["PDF Toolkit"])
templates = Jinja2Templates(directory="app/templates")

_ALLOWED_MIME = {"application/pdf"}


def _es_pdf(upload: UploadFile) -> bool:
    mime_ok = (upload.content_type or "") in _ALLOWED_MIME
    ext_ok = (upload.filename or "").lower().endswith(".pdf")
    return mime_ok or ext_ok


# ── Página ─────────────────────────────────────────────────────────────────────

@router.get("/herramientas", response_class=HTMLResponse, include_in_schema=False)
async def pdf_toolkit_page(request: Request, user=Depends(get_current_user)):
    if not user:
        from fastapi.responses import RedirectResponse
        return RedirectResponse("/auth/login")
    return templates.TemplateResponse("app/pdf_toolkit.html", {
        "request": request, "user": user, "current_page": "pdf_toolkit",
    })


# ── Info (páginas) ─────────────────────────────────────────────────────────────

@router.post("/info")
async def pdf_info(
    request: Request,
    user=Depends(get_current_user),
    documento: UploadFile = File(...),
):
    """Devuelve la cantidad de páginas del primer PDF subido."""
    if not user:
        return JSONResponse({"error": "No autorizado"}, status_code=401)
    if not _es_pdf(documento):
        return JSONResponse({"error": "Solo se aceptan archivos PDF"}, status_code=400)

    pdf_bytes = await documento.read()
    try:
        paginas = await asyncio.to_thread(svc.contar_paginas, pdf_bytes)
    except Exception as exc:
        return JSONResponse({"error": f"No se pudo leer el PDF: {exc}"}, status_code=422)

    return JSONResponse({"paginas": paginas, "nombre": documento.filename})


# ── Split ──────────────────────────────────────────────────────────────────────

@router.post("/split")
async def split_pdfs(
    request: Request,
    user=Depends(get_current_user),
    documents: list[UploadFile] = File(...),
    mode: str = Form("all"),
    page_start: int = Form(1),
    page_end: int = Form(1),
):
    """
    Recibe uno o varios PDFs y devuelve un ZIP con las páginas separadas.
    mode: "all" (todas) | "range" (rango page_start–page_end, 1-based)
    """
    if not user:
        return JSONResponse({"error": "No autorizado"}, status_code=401)
    if mode not in ("all", "range"):
        return JSONResponse({"error": "Modo inválido"}, status_code=400)

    archivos: list[tuple[str, bytes]] = []
    for upload in documents:
        if not _es_pdf(upload):
            return JSONResponse(
                {"error": f"Solo se aceptan archivos PDF ({upload.filename})"},
                status_code=400,
            )
        pdf_bytes = await upload.read()
        archivos.append((upload.filename or "documento.pdf", pdf_bytes))

    if not archivos:
        return JSONResponse({"error": "No se recibieron archivos"}, status_code=400)

    try:
        zip_bytes, total = await asyncio.to_thread(
            svc.separar_pdfs_en_zip, archivos, mode, page_start, page_end
        )
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)
    except Exception as exc:
        return JSONResponse({"error": f"Error procesando PDF: {exc}"}, status_code=500)

    nombre_zip = "hoja_separada.pdf" if total == 1 else "hojas_separadas.zip"

    return StreamingResponse(
        BytesIO(zip_bytes),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={nombre_zip}"},
    )
