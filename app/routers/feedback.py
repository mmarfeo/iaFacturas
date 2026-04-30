"""
Router de Feedback de usuarios.

Endpoints:
  POST /feedback/send   — guardar comentario (JSON)
  GET  /feedback/admin  — página HTML con listado (solo admins en el futuro, por ahora autenticados)
"""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.feedback import UserFeedback

router = APIRouter(prefix="/feedback", tags=["Feedback"])
templates_jinja = Jinja2Templates(directory="app/templates")

TIPOS_VALIDOS = {"mejora", "error", "consulta", "otro"}


class FeedbackIn(BaseModel):
    tipo: str
    mensaje: str
    pagina: str = ""


@router.post("/send")
async def feedback_send(
    body: FeedbackIn,
    request: Request,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.tipo not in TIPOS_VALIDOS:
        return JSONResponse({"success": False, "message": "Tipo inválido"}, status_code=400)
    if not body.mensaje.strip():
        return JSONResponse({"success": False, "message": "El mensaje no puede estar vacío"}, status_code=400)

    fb = UserFeedback(
        usuario_id=user.id if user else None,
        tipo=body.tipo,
        mensaje=body.mensaje.strip()[:2000],
        pagina=body.pagina[:255] if body.pagina else None,
    )
    db.add(fb)
    await db.commit()
    return JSONResponse({"success": True})


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
