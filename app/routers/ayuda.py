"""
Página de Ayuda y documentación.

GET /ayuda   — página HTML
"""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.core.auth import get_current_user

router = APIRouter(prefix="/ayuda", tags=["Ayuda"])
templates_jinja = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def ayuda_page(request: Request, user=Depends(get_current_user)):
    if not user:
        return RedirectResponse("/auth/login")
    return templates_jinja.TemplateResponse("app/ayuda.html", {
        "request": request,
        "user": user,
        "current_page": "ayuda",
    })
