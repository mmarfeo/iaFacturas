"""
Gestión de lotes: upload múltiple + seguimiento por nombre de proveedor/período/tipo.
"""
import uuid
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.factura import Factura
from app.models.lote import Lote

router = APIRouter(tags=["Lotes"])
templates = Jinja2Templates(directory="app/templates")
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

_EXTS = {".pdf", ".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp"}


# ═══════════════════════════════════════════════════════════
# GET /app/lotes — lista de lotes
# ═══════════════════════════════════════════════════════════

@router.get("/app/lotes", response_class=HTMLResponse)
async def lotes_page(
    request: Request,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not user:
        return RedirectResponse("/auth/login", status_code=302)

    res = await db.execute(
        select(Lote)
        .where(Lote.usuario_id == user.id)
        .order_by(desc(Lote.created_at))
    )
    lotes = res.scalars().all()

    return templates.TemplateResponse("app/lotes.html", {
        "request":      request,
        "user":         user,
        "current_page": "lotes",
        "lotes":        lotes,
    })


# ═══════════════════════════════════════════════════════════
# GET /app/lotes/nuevo — formulario
# ═══════════════════════════════════════════════════════════

@router.get("/app/lotes/nuevo", response_class=HTMLResponse)
async def nuevo_lote_page(
    request: Request,
    user=Depends(get_current_user),
):
    if not user:
        return RedirectResponse("/auth/login", status_code=302)
    return templates.TemplateResponse("app/nuevo_lote.html", {
        "request":      request,
        "user":         user,
        "current_page": "lotes",
    })


# ═══════════════════════════════════════════════════════════
# POST /app/lotes/nuevo — crear lote + subir archivos
# ═══════════════════════════════════════════════════════════

@router.post("/app/lotes/nuevo")
async def crear_lote(
    nombre: str = Form(...),
    files: List[UploadFile] = File(...),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not user:
        return JSONResponse({"error": "No autorizado"}, status_code=401)

    archivos = [f for f in files if Path(f.filename or "").suffix.lower() in _EXTS]
    if not archivos:
        return JSONResponse({"error": "No se enviaron archivos válidos (PDF, JPG, PNG…)"}, status_code=400)

    lote = Lote(
        nombre=nombre.strip(),
        usuario_id=user.id,
        estado="procesando",
        total=len(archivos),
        procesados=0,
        errores=0,
    )
    db.add(lote)
    await db.flush()  # obtener lote.id

    cola: list[tuple[int, str]] = []
    for file in archivos:
        ext      = Path(file.filename).suffix.lower()
        filename = f"{user.id}_{uuid.uuid4().hex}{ext}"
        filepath = UPLOAD_DIR / filename
        with open(filepath, "wb") as fh:
            fh.write(await file.read())

        factura = Factura(
            usuario_id=user.id,
            lote_id=lote.id,
            archivo_path=str(filepath),
            estado="pendiente",
        )
        db.add(factura)
        await db.flush()
        cola.append((factura.id, str(filepath)))

    await db.commit()

    try:
        from tasks.procesar_factura import procesar_factura
        for fid, fpath in cola:
            procesar_factura.delay(fid, fpath)
    except Exception as e:
        print(f"[CELERY WARNING] {e}")

    return RedirectResponse(f"/app/lotes/{lote.id}", status_code=302)


# ═══════════════════════════════════════════════════════════
# GET /app/lotes/{lote_id} — detalle del lote
# ═══════════════════════════════════════════════════════════

@router.get("/app/lotes/{lote_id}", response_class=HTMLResponse)
async def lote_detalle(
    request: Request,
    lote_id: int,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not user:
        return RedirectResponse("/auth/login", status_code=302)

    res = await db.execute(
        select(Lote).where(Lote.id == lote_id, Lote.usuario_id == user.id)
    )
    lote = res.scalar_one_or_none()
    if not lote:
        return RedirectResponse("/app/lotes", status_code=302)

    res_f = await db.execute(
        select(Factura).where(Factura.lote_id == lote_id).order_by(Factura.id)
    )
    facturas = res_f.scalars().all()

    return templates.TemplateResponse("app/lote_detalle.html", {
        "request":      request,
        "user":         user,
        "current_page": "lotes",
        "lote":         lote,
        "facturas":     facturas,
    })


# ═══════════════════════════════════════════════════════════
# GET /app/lotes/{lote_id}/estado — polling JSON
# ═══════════════════════════════════════════════════════════

@router.get("/app/lotes/{lote_id}/estado")
async def lote_estado(
    lote_id: int,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not user:
        return JSONResponse({"error": "No autorizado"}, status_code=401)

    res = await db.execute(
        select(Lote).where(Lote.id == lote_id, Lote.usuario_id == user.id)
    )
    lote = res.scalar_one_or_none()
    if not lote:
        return JSONResponse({"error": "No encontrado"}, status_code=404)

    # Recalcular stats desde facturas
    stats = (await db.execute(
        select(
            func.count(Factura.id).label("total"),
            func.count(Factura.id).filter(Factura.estado == "completado").label("procesados"),
            func.count(Factura.id).filter(Factura.estado == "error").label("errores"),
        ).where(Factura.lote_id == lote_id)
    )).one()

    procesados = stats.procesados or 0
    errores    = stats.errores or 0
    total      = stats.total or 0
    terminados = procesados + errores

    if terminados >= total and total > 0:
        nuevo_estado = "con_errores" if errores > 0 else "completado"
    else:
        nuevo_estado = "procesando"

    if lote.total != total or lote.procesados != procesados or lote.errores != errores or lote.estado != nuevo_estado:
        lote.total      = total
        lote.procesados = procesados
        lote.errores    = errores
        lote.estado     = nuevo_estado
        await db.commit()

    return JSONResponse({
        "estado":     nuevo_estado,
        "total":      total,
        "procesados": procesados,
        "errores":    errores,
    })


# ═══════════════════════════════════════════════════════════
# POST /app/lotes/{lote_id}/reprocesar
# ═══════════════════════════════════════════════════════════

@router.post("/app/lotes/{lote_id}/reprocesar")
async def reprocesar_lote(
    lote_id: int,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not user:
        return JSONResponse({"error": "No autorizado"}, status_code=401)

    res = await db.execute(
        select(Lote).where(Lote.id == lote_id, Lote.usuario_id == user.id)
    )
    lote = res.scalar_one_or_none()
    if not lote:
        return JSONResponse({"error": "Lote no encontrado"}, status_code=404)

    res_f = await db.execute(
        select(Factura).where(
            Factura.lote_id == lote_id,
            Factura.estado.in_(["pendiente", "error"]),
        )
    )
    facturas = res_f.scalars().all()

    try:
        from tasks.procesar_factura import procesar_factura
        for f in facturas:
            f.estado = "pendiente"
            procesar_factura.delay(f.id, f.archivo_path)
    except Exception as e:
        print(f"[CELERY WARNING] {e}")

    lote.estado = "procesando"
    await db.commit()

    return JSONResponse({"ok": True, "encoladas": len(facturas)})


# ═══════════════════════════════════════════════════════════
# DELETE /app/lotes/{lote_id}
# ═══════════════════════════════════════════════════════════

@router.delete("/app/lotes/{lote_id}")
async def eliminar_lote(
    lote_id: int,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not user:
        return JSONResponse({"error": "No autorizado"}, status_code=401)

    res = await db.execute(
        select(Lote).where(Lote.id == lote_id, Lote.usuario_id == user.id)
    )
    lote = res.scalar_one_or_none()
    if not lote:
        return JSONResponse({"error": "Lote no encontrado"}, status_code=404)

    res_f = await db.execute(select(Factura).where(Factura.lote_id == lote_id))
    for f in res_f.scalars().all():
        try:
            Path(f.archivo_path).unlink(missing_ok=True)
        except Exception:
            pass
        await db.delete(f)

    await db.delete(lote)
    await db.commit()
    return JSONResponse({"ok": True})
