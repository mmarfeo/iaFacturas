"""
Router de Feedback de usuarios.

Endpoints:
  POST /feedback/send              — guardar comentario + PDF opcional (multipart)
  GET  /feedback/admin             — página HTML con listado
  GET  /feedback/download/{id}     — descarga el PDF adjunto del comentario
"""
import os
import re
import unicodedata
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.feedback import UserFeedback

router = APIRouter(prefix="/feedback", tags=["Feedback"])
templates_jinja = Jinja2Templates(directory="app/templates")

TIPOS_VALIDOS = {"mejora", "error", "consulta", "otro"}
UPLOADS_BASE = Path("uploads/feedback")
MAX_PDF_MB = 10


def _safe_name(text: str) -> str:
    """Convierte texto a nombre de carpeta seguro (sin tildes ni espacios)."""
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_str = nfkd.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-zA-Z0-9_-]", "_", ascii_str)[:40]


def _feedback_dir(username: str) -> Path:
    """
    Devuelve la ruta donde guardar el adjunto:
      uploads/feedback/YYYY-MM-DD/{timestamp}_{username}/
    """
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    ts_str = now.strftime("%Y%m%d_%H%M%S")
    folder = UPLOADS_BASE / date_str / f"{ts_str}_{_safe_name(username)}"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


# ── Enviar feedback ────────────────────────────────────────────────────────────

@router.post("/send")
async def feedback_send(
    tipo: str = Form(...),
    mensaje: str = Form(...),
    pagina: str = Form(""),
    archivo: UploadFile = File(None),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if tipo not in TIPOS_VALIDOS:
        return JSONResponse({"success": False, "message": "Tipo inválido"}, status_code=400)
    if not mensaje.strip():
        return JSONResponse({"success": False, "message": "El mensaje no puede estar vacío"}, status_code=400)

    archivo_path = None
    archivo_nombre = None

    if archivo and archivo.filename:
        if not archivo.filename.lower().endswith(".pdf"):
            return JSONResponse({"success": False, "message": "Solo se permiten archivos PDF"}, status_code=400)

        pdf_bytes = await archivo.read()
        if len(pdf_bytes) > MAX_PDF_MB * 1024 * 1024:
            return JSONResponse(
                {"success": False, "message": f"El PDF no puede superar {MAX_PDF_MB} MB"},
                status_code=400,
            )

        username = user.nombre if user else "anonimo"
        dest_dir = _feedback_dir(username)
        safe_filename = re.sub(r"[^a-zA-Z0-9._-]", "_", archivo.filename)
        dest_path = dest_dir / safe_filename
        dest_path.write_bytes(pdf_bytes)

        # Guardamos la ruta relativa a uploads/
        archivo_path = str(dest_path)
        archivo_nombre = archivo.filename

    fb = UserFeedback(
        usuario_id=user.id if user else None,
        tipo=tipo,
        mensaje=mensaje.strip()[:2000],
        pagina=pagina[:255] if pagina else None,
        archivo_path=archivo_path,
        archivo_nombre=archivo_nombre,
    )
    db.add(fb)
    await db.commit()
    return JSONResponse({"success": True})


# ── Admin ──────────────────────────────────────────────────────────────────────

@router.get("/admin", response_class=HTMLResponse, include_in_schema=False)
async def feedback_admin(
    request: Request,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not user:
        from fastapi.responses import RedirectResponse
        return RedirectResponse("/auth/login")

    result = await db.execute(
        select(UserFeedback).order_by(UserFeedback.created_at.desc()).limit(500)
    )
    items = result.scalars().all()
    return templates_jinja.TemplateResponse("app/feedback_admin.html", {
        "request": request,
        "user": user,
        "current_page": "feedback_admin",
        "items": items,
    })


# ── Descarga de adjunto ────────────────────────────────────────────────────────

@router.get("/download/{feedback_id}")
async def feedback_download(
    feedback_id: int,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not user:
        return JSONResponse({"success": False, "message": "No autorizado"}, status_code=401)

    result = await db.execute(
        select(UserFeedback).where(UserFeedback.id == feedback_id)
    )
    fb = result.scalar_one_or_none()
    if not fb or not fb.archivo_path:
        return JSONResponse({"success": False, "message": "Archivo no encontrado"}, status_code=404)

    path = Path(fb.archivo_path)
    if not path.exists():
        return JSONResponse({"success": False, "message": "Archivo no existe en disco"}, status_code=404)

    return FileResponse(
        path=str(path),
        media_type="application/pdf",
        filename=fb.archivo_nombre or path.name,
    )
