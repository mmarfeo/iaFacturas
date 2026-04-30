"""
Rutas de autenticación: login, register, logout.
Usa formularios HTML + cookie HTTP-only con JWT.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.security import hash_password, verify_password, create_access_token
from app.core.auth import get_current_user
from app.models.usuario import Usuario
from app.models.plan import Plan

router = APIRouter(tags=["Auth"])
templates = Jinja2Templates(directory="app/templates")

_COOKIE = "access_token"
_COOKIE_OPTS = dict(httponly=True, samesite="lax", max_age=60 * 60 * 24 * 7)


# ── GET /auth/login ───────────────────────────────────────

@router.get("/auth/login", response_class=HTMLResponse)
async def login_page(
    request: Request,
    user=Depends(get_current_user),
):
    if user:
        return RedirectResponse("/app/inicio", status_code=302)
    return templates.TemplateResponse("auth/login.html", {
        "request": request, "user": None, "current_page": "login", "error": None,
    })


# ── POST /auth/login ──────────────────────────────────────

@router.post("/auth/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Usuario)
        .where(Usuario.email == email.lower().strip())
        .options(selectinload(Usuario.plan))
    )
    user = result.scalar_one_or_none()

    if not user or not verify_password(password, user.password_hash) or not user.is_active:
        return templates.TemplateResponse("auth/login.html", {
            "request": request, "user": None, "current_page": "login",
            "error": "Email o contraseña incorrectos.",
            "form_email": email,
        }, status_code=400)

    token = create_access_token(user.id)
    response = RedirectResponse("/app/inicio", status_code=302)
    response.set_cookie(_COOKIE, token, **_COOKIE_OPTS)
    return response


# ── GET /auth/register ────────────────────────────────────

@router.get("/auth/register", response_class=HTMLResponse)
async def register_page(
    request: Request,
    user=Depends(get_current_user),
):
    if user:
        return RedirectResponse("/app/inicio", status_code=302)
    return templates.TemplateResponse("auth/register.html", {
        "request": request, "user": None, "current_page": "register", "error": None,
    })


# ── POST /auth/register ───────────────────────────────────

@router.post("/auth/register", response_class=HTMLResponse)
async def register_submit(
    request: Request,
    nombre: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    plan: str = Form("free"),
    db: AsyncSession = Depends(get_db),
):
    email = email.lower().strip()

    # Email ya registrado
    existing = await db.execute(select(Usuario).where(Usuario.email == email))
    if existing.scalar_one_or_none():
        return templates.TemplateResponse("auth/register.html", {
            "request": request, "user": None, "current_page": "register",
            "error": "Ya existe una cuenta con ese email.",
            "form_email": email, "form_nombre": nombre,
        }, status_code=400)

    # Validar contraseña mínima
    if len(password) < 6:
        return templates.TemplateResponse("auth/register.html", {
            "request": request, "user": None, "current_page": "register",
            "error": "La contraseña debe tener al menos 6 caracteres.",
            "form_email": email, "form_nombre": nombre,
        }, status_code=400)

    # Obtener plan_id (1=Free, 2=Pro)
    plan_nombre = "Pro" if plan == "pro" else "Free"
    plan_result = await db.execute(select(Plan).where(Plan.nombre == plan_nombre))
    plan_obj = plan_result.scalar_one_or_none()
    plan_id = plan_obj.id if plan_obj else 1

    nuevo = Usuario(
        email=email,
        password_hash=hash_password(password),
        nombre=nombre.strip(),
        plan_id=plan_id,
        is_active=True,
        is_verified=False,
    )
    db.add(nuevo)
    await db.commit()
    await db.refresh(nuevo)

    token = create_access_token(nuevo.id)
    response = RedirectResponse("/app/inicio", status_code=302)
    response.set_cookie(_COOKIE, token, **_COOKIE_OPTS)
    return response


# ── GET /auth/logout ──────────────────────────────────────

@router.get("/auth/logout")
async def logout():
    response = RedirectResponse("/", status_code=302)
    response.delete_cookie(_COOKIE)
    return response
