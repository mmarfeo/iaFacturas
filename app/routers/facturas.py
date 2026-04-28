"""
Rutas de facturas: upload, estado, historial, resultado, export.
Incluye las páginas HTML del área de app (dashboard, upload, historial, resultado, planes).
"""
import json
import os
import uuid
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Optional

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.auth import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.models.factura import Factura
from app.models.plan import Plan
from app.models.uso_mensual import UsoMensual

router = APIRouter(tags=["Facturas"])
templates = Jinja2Templates(directory="app/templates")

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

_PAGE_SIZE = 15


def _redis():
    return aioredis.from_url(settings.redis_url, decode_responses=True)


# ──────────────────────────────────────────────────────────
# PÁGINAS HTML
# ──────────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
async def landing(request: Request, user=Depends(get_current_user)):
    return templates.TemplateResponse("landing.html", {
        "request": request, "user": user, "current_page": "landing",
    })


@router.get("/planes", response_class=HTMLResponse)
async def planes_page(
    request: Request,
    user=Depends(get_current_user),
    success: bool = False,
):
    return templates.TemplateResponse("app/planes.html", {
        "request": request, "user": user, "current_page": "planes", "success": success,
    })


@router.get("/app/inicio", response_class=HTMLResponse)
async def inicio(request: Request, user=Depends(get_current_user)):
    if not user:
        return RedirectResponse("/auth/login", status_code=302)
    return templates.TemplateResponse("app/inicio.html", {
        "request": request, "user": user, "current_page": "inicio",
    })


@router.get("/app/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not user:
        return RedirectResponse("/auth/login", status_code=302)

    # Últimas 5 facturas
    res = await db.execute(
        select(Factura)
        .where(Factura.usuario_id == user.id)
        .order_by(desc(Factura.created_at))
        .limit(5)
    )
    facturas_recientes = res.scalars().all()

    # Stats del mes
    from datetime import date
    hoy = date.today()
    res_mes = await db.execute(
        select(func.count(Factura.id))
        .where(Factura.usuario_id == user.id)
        .where(func.extract('month', Factura.created_at) == hoy.month)
        .where(func.extract('year',  Factura.created_at) == hoy.year)
    )
    total_mes = res_mes.scalar() or 0
    vigentes  = sum(1 for f in facturas_recientes if f.cae_valido is True)
    vencidos  = sum(1 for f in facturas_recientes if f.cae_valido is False)

    return templates.TemplateResponse("app/dashboard.html", {
        "request": request,
        "user": user,
        "current_page": "dashboard",
        "facturas_recientes": facturas_recientes,
        "stats": {"total": total_mes, "vigentes": vigentes, "vencidos": vencidos},
    })


@router.get("/app/upload", response_class=HTMLResponse)
async def upload_page(request: Request, user=Depends(get_current_user)):
    if not user:
        return RedirectResponse("/auth/login", status_code=302)
    return templates.TemplateResponse("app/upload.html", {
        "request": request, "user": user, "current_page": "upload",
    })


@router.get("/app/historial", response_class=HTMLResponse)
async def historial_page(
    request: Request,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    q: Optional[str] = None,
    cae: Optional[str] = None,
    page: int = 1,
):
    if not user:
        return RedirectResponse("/auth/login", status_code=302)

    query = select(Factura).where(Factura.usuario_id == user.id)

    if q:
        query = query.where(
            Factura.archivo_path.ilike(f"%{q}%") |
            Factura.cuit_emisor.ilike(f"%{q}%")
        )
    if cae == "VIGENTE":
        query = query.where(Factura.cae_valido == True)   # noqa: E712
    elif cae == "VENCIDO":
        query = query.where(Factura.cae_valido == False)  # noqa: E712

    # Total para paginación
    count_q = select(func.count()).select_from(query.subquery())
    total_res = await db.execute(count_q)
    total = total_res.scalar() or 0
    total_pages = max(1, (total + _PAGE_SIZE - 1) // _PAGE_SIZE)

    # Página actual
    query = query.order_by(desc(Factura.created_at))
    query = query.offset((page - 1) * _PAGE_SIZE).limit(_PAGE_SIZE)
    res = await db.execute(query)
    facturas = res.scalars().all()

    return templates.TemplateResponse("app/historial.html", {
        "request": request,
        "user": user,
        "current_page": "historial",
        "facturas": facturas,
        "total": total,
        "total_pages": total_pages,
        "current_page_num": page,
        "search": q or "",
        "filter_cae": cae or "todos",
    })


@router.get("/app/facturas/{factura_id}", response_class=HTMLResponse)
async def resultado_page(
    request: Request,
    factura_id: int,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not user:
        return RedirectResponse("/auth/login", status_code=302)

    res = await db.execute(
        select(Factura).where(Factura.id == factura_id, Factura.usuario_id == user.id)
    )
    factura = res.scalar_one_or_none()
    if not factura:
        return RedirectResponse("/app/historial", status_code=302)

    return templates.TemplateResponse("app/resultado.html", {
        "request": request,
        "user": user,
        "current_page": "resultado",
        "factura": factura,
    })


# ──────────────────────────────────────────────────────────
# API — UPLOAD + PROCESAMIENTO
# ──────────────────────────────────────────────────────────

@router.post("/app/upload")
async def upload_factura(
    request: Request,
    file: UploadFile = File(...),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not user:
        return JSONResponse({"error": "No autorizado"}, status_code=401)

    # Verificar límite de plan
    plan_res = await db.execute(select(Plan).where(Plan.id == user.plan_id))
    plan = plan_res.scalar_one_or_none()
    if plan and plan.limite_mensual and plan.limite_mensual > 0:
        from datetime import date
        hoy = date.today()
        uso_res = await db.execute(
            select(func.count(Factura.id))
            .where(Factura.usuario_id == user.id)
            .where(func.extract('month', Factura.created_at) == hoy.month)
            .where(func.extract('year',  Factura.created_at) == hoy.year)
        )
        uso = uso_res.scalar() or 0
        if uso >= plan.limite_mensual:
            return JSONResponse(
                {"error": f"Límite mensual de {plan.limite_mensual} facturas alcanzado."},
                status_code=429,
            )

    # Guardar archivo
    ext = Path(file.filename).suffix.lower() if file.filename else ".pdf"
    filename = f"{user.id}_{uuid.uuid4().hex}{ext}"
    filepath = UPLOAD_DIR / filename
    content = await file.read()
    with open(filepath, "wb") as f:
        f.write(content)

    # Crear registro en DB
    factura = Factura(
        usuario_id=user.id,
        archivo_path=str(filepath),
        estado="pendiente",
    )
    db.add(factura)
    await db.commit()
    await db.refresh(factura)

    # Encolar tarea Celery
    try:
        from tasks.procesar_factura import procesar_factura
        procesar_factura.delay(factura.id, str(filepath))
    except Exception:
        # Si Celery no está disponible (dev), procesar inline
        pass

    return JSONResponse({"job_id": factura.id})


@router.get("/app/upload/estado/{job_id}")
async def upload_estado(
    job_id: int,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Polling endpoint: devuelve step (0-4) y estado del procesamiento."""
    if not user:
        return JSONResponse({"error": "No autorizado"}, status_code=401)

    r = _redis()
    key = f"factura:{job_id}"

    try:
        estado = await r.get(f"{key}:estado") or "pendiente"
        step   = int(await r.get(f"{key}:step") or 0)
        error  = await r.get(f"{key}:error")
        await r.aclose()
    except Exception:
        # Redis no disponible → consultar DB
        res = await db.execute(select(Factura).where(Factura.id == job_id))
        f = res.scalar_one_or_none()
        if not f:
            return JSONResponse({"estado": "error", "error": "No encontrado"})
        estado_map = {"completado": "done", "error": "error"}
        return JSONResponse({
            "estado": estado_map.get(f.estado, "procesando"),
            "step": 4 if f.estado == "completado" else 0,
        })

    return JSONResponse({"estado": estado, "step": step, "error": error})


# ──────────────────────────────────────────────────────────
# EXPORTACIÓN
# ──────────────────────────────────────────────────────────

@router.get("/app/facturas/{factura_id}/export/excel")
async def export_factura_excel(
    factura_id: int,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not user:
        return RedirectResponse("/auth/login", status_code=302)

    res = await db.execute(
        select(Factura).where(Factura.id == factura_id, Factura.usuario_id == user.id)
    )
    factura = res.scalar_one_or_none()
    if not factura:
        return JSONResponse({"error": "No encontrado"}, status_code=404)

    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Factura"
    ws.append(["Campo", "Valor"])
    ws.column_dimensions["A"].width = 25
    ws.column_dimensions["B"].width = 40

    datos = factura.datos_extraidos or {}
    campos = [
        ("Archivo",           Path(factura.archivo_path).name),
        ("CAE",               factura.cae),
        ("CAE válido",        "Sí" if factura.cae_valido else "No"),
        ("Vencimiento CAE",   str(factura.cae_vencimiento) if factura.cae_vencimiento else ""),
        ("CUIT Emisor",       factura.cuit_emisor),
        ("CUIT Receptor",     factura.cuit_receptor),
        ("Importe Total",     float(factura.importe) if factura.importe else ""),
        ("Fecha Factura",     str(factura.fecha_factura) if factura.fecha_factura else ""),
        ("Tipo Comprobante",  datos.get("tipo_comprobante", "")),
        ("Razón Social Emisor", datos.get("razon_social_emisor", "")),
        ("Concepto",          datos.get("concepto", "")),
    ]
    for campo, valor in campos:
        ws.append([campo, valor])

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    nombre = Path(factura.archivo_path).stem + ".xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )


@router.get("/app/historial/export/excel")
async def export_historial_excel(
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    q: Optional[str] = None,
    cae: Optional[str] = None,
):
    if not user:
        return RedirectResponse("/auth/login", status_code=302)

    query = select(Factura).where(Factura.usuario_id == user.id)
    if q:
        query = query.where(Factura.archivo_path.ilike(f"%{q}%") | Factura.cuit_emisor.ilike(f"%{q}%"))
    if cae == "VIGENTE":
        query = query.where(Factura.cae_valido == True)   # noqa: E712
    elif cae == "VENCIDO":
        query = query.where(Factura.cae_valido == False)  # noqa: E712

    res = await db.execute(query.order_by(desc(Factura.created_at)))
    facturas = res.scalars().all()

    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Historial"
    headers = ["Archivo", "CUIT Emisor", "Importe", "Fecha", "CAE", "Estado CAE"]
    ws.append(headers)
    for col in ["A", "B", "C", "D", "E", "F"]:
        ws.column_dimensions[col].width = 22

    for f in facturas:
        ws.append([
            Path(f.archivo_path).name,
            f.cuit_emisor or "",
            float(f.importe) if f.importe else "",
            str(f.fecha_factura) if f.fecha_factura else "",
            f.cae or "",
            "VIGENTE" if f.cae_valido else "VENCIDO",
        ])

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="historial-facturas.xlsx"'},
    )
