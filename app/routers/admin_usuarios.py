"""
Módulo de administración de usuarios.

Solo accesible para usuarios con is_admin=True.

Endpoints:
  GET  /admin/usuarios                  — página HTML
  GET  /admin/usuarios/list             — JSON lista de usuarios
  GET  /admin/usuarios/permissions-schema — JSON secciones de permisos
  POST /admin/usuarios/create           — crear usuario
  POST /admin/usuarios/update           — editar usuario + permisos
  POST /admin/usuarios/toggle-status    — activar/desactivar
  DELETE /admin/usuarios/{id}           — eliminar
"""
import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.database import get_db
from app.core.permissions import PERMISSION_SECTIONS, parse_permisos
from app.core.security import hash_password
from app.models.plan import Plan
from app.models.usuario import Usuario

router = APIRouter(prefix="/admin/usuarios", tags=["Admin Usuarios"])
templates_jinja = Jinja2Templates(directory="app/templates")


# ── Guard helper ──────────────────────────────────────────────────────────────

def _require_admin(user):
    if not user or not user.is_admin:
        return JSONResponse({"success": False, "message": "Acceso denegado"}, status_code=403)
    return None


# ── Página HTML ───────────────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def admin_usuarios_page(request: Request, user=Depends(get_current_user)):
    if not user:
        from fastapi.responses import RedirectResponse
        return RedirectResponse("/auth/login")
    if not user.is_admin:
        from fastapi.responses import RedirectResponse
        return RedirectResponse("/app/inicio")
    return templates_jinja.TemplateResponse("app/admin_usuarios.html", {
        "request": request,
        "user": user,
        "current_page": "admin_usuarios",
    })


# ── Schema de permisos (para JS) ──────────────────────────────────────────────

@router.get("/permissions-schema")
async def permissions_schema(user=Depends(get_current_user)):
    err = _require_admin(user)
    if err:
        return err
    return JSONResponse({"success": True, "sections": PERMISSION_SECTIONS})


# ── Listar usuarios ───────────────────────────────────────────────────────────

@router.get("/list")
async def admin_list(
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    err = _require_admin(user)
    if err:
        return err

    result = await db.execute(
        select(Usuario).order_by(Usuario.created_at.desc())
    )
    rows = result.scalars().all()
    data = [
        {
            "id": u.id,
            "nombre": u.nombre,
            "email": u.email,
            "is_active": u.is_active,
            "is_admin": u.is_admin,
            "is_verified": u.is_verified,
            "plan_id": u.plan_id,
            "permisos": u.permisos or "{}",
            "created_at": u.created_at.strftime("%d/%m/%Y"),
        }
        for u in rows
    ]
    return JSONResponse({"success": True, "data": data})


# ── Crear usuario ─────────────────────────────────────────────────────────────

class CreateUsuarioIn(BaseModel):
    nombre: str
    email: str
    password: str
    is_admin: bool = False
    plan: str = "free"


@router.post("/create")
async def admin_create(
    body: CreateUsuarioIn,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    err = _require_admin(user)
    if err:
        return err

    email = body.email.lower().strip()
    existing = await db.execute(select(Usuario).where(Usuario.email == email))
    if existing.scalar_one_or_none():
        return JSONResponse({"success": False, "message": "Ya existe un usuario con ese email"}, status_code=400)

    if len(body.password) < 6:
        return JSONResponse({"success": False, "message": "La contraseña debe tener al menos 6 caracteres"}, status_code=400)

    plan_nombre = "Pro" if body.plan == "pro" else "Free"
    plan_result = await db.execute(select(Plan).where(Plan.nombre == plan_nombre))
    plan_obj = plan_result.scalar_one_or_none()
    plan_id = plan_obj.id if plan_obj else 1

    nuevo = Usuario(
        email=email,
        password_hash=hash_password(body.password),
        nombre=body.nombre.strip(),
        plan_id=plan_id,
        is_active=True,
        is_verified=True,
        is_admin=body.is_admin,
        permisos=None,
    )
    db.add(nuevo)
    await db.commit()
    await db.refresh(nuevo)
    return JSONResponse({"success": True, "message": "Usuario creado correctamente", "id": nuevo.id})


# ── Actualizar usuario + permisos ─────────────────────────────────────────────

class UpdateUsuarioIn(BaseModel):
    id: int
    nombre: str
    email: str
    password: str = ""
    is_admin: bool = False
    is_active: bool = True
    plan: str = "free"
    permisos: dict = {}


@router.post("/update")
async def admin_update(
    body: UpdateUsuarioIn,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    err = _require_admin(user)
    if err:
        return err

    result = await db.execute(select(Usuario).where(Usuario.id == body.id))
    u = result.scalar_one_or_none()
    if not u:
        return JSONResponse({"success": False, "message": "Usuario no encontrado"}, status_code=404)

    email = body.email.lower().strip()
    dup = await db.execute(select(Usuario).where(Usuario.email == email, Usuario.id != body.id))
    if dup.scalar_one_or_none():
        return JSONResponse({"success": False, "message": "El email ya está en uso"}, status_code=400)

    u.nombre = body.nombre.strip()
    u.email = email
    u.is_admin = body.is_admin
    u.is_active = body.is_active

    if body.password:
        if len(body.password) < 6:
            return JSONResponse({"success": False, "message": "La contraseña debe tener al menos 6 caracteres"}, status_code=400)
        u.password_hash = hash_password(body.password)

    plan_nombre = "Pro" if body.plan == "pro" else "Free"
    plan_result = await db.execute(select(Plan).where(Plan.nombre == plan_nombre))
    plan_obj = plan_result.scalar_one_or_none()
    if plan_obj:
        u.plan_id = plan_obj.id

    # Guardar permisos como JSON
    u.permisos = json.dumps(body.permisos, ensure_ascii=False)

    await db.commit()
    return JSONResponse({"success": True, "message": "Usuario actualizado correctamente"})


# ── Toggle activo/inactivo ────────────────────────────────────────────────────

class ToggleStatusIn(BaseModel):
    id: int
    is_active: bool


@router.post("/toggle-status")
async def admin_toggle_status(
    body: ToggleStatusIn,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    err = _require_admin(user)
    if err:
        return err

    result = await db.execute(select(Usuario).where(Usuario.id == body.id))
    u = result.scalar_one_or_none()
    if not u:
        return JSONResponse({"success": False, "message": "Usuario no encontrado"}, status_code=404)

    if u.id == user.id and not body.is_active:
        return JSONResponse({"success": False, "message": "No podés desactivar tu propia cuenta"}, status_code=400)

    u.is_active = body.is_active
    await db.commit()
    return JSONResponse({"success": True})


# ── Eliminar ──────────────────────────────────────────────────────────────────

@router.delete("/{usuario_id}")
async def admin_delete(
    usuario_id: int,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    err = _require_admin(user)
    if err:
        return err

    if usuario_id == user.id:
        return JSONResponse({"success": False, "message": "No podés eliminar tu propia cuenta"}, status_code=400)

    result = await db.execute(select(Usuario).where(Usuario.id == usuario_id))
    u = result.scalar_one_or_none()
    if not u:
        return JSONResponse({"success": False, "message": "Usuario no encontrado"}, status_code=404)

    await db.delete(u)
    await db.commit()
    return JSONResponse({"success": True})
