"""
Router de Plantillas de Extracción (Invoice Templates).

Endpoints:
  GET  /templates/                — página HTML del editor
  GET  /templates/list            — lista de plantillas del usuario (JSON)
  POST /templates/save            — crear / actualizar plantilla (JSON)
  GET  /templates/get/{id}        — obtener plantilla por ID (JSON)
  DELETE /templates/{id}          — eliminar plantilla (JSON)
  POST /templates/extract         — extraer campos vía VPS FastAPI (JSON)
"""
import json
from io import BytesIO

import httpx
from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.models.invoice_template import InvoiceTemplate

router = APIRouter(prefix="/templates", tags=["Invoice Templates"])
templates_jinja = Jinja2Templates(directory="app/templates")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _convert_template_for_vps(template_data: dict) -> dict:
    """
    Convierte el formato UI (coordenadas de viewport) al formato esperado
    por el VPS FastAPI (/extract).

    Entrada (clave 'zonas'):
        { x0, y0, x1, y1 }  en píxeles del viewport (PDF a escala 2.5)

    Salida (clave 'zones'):
        { field, type, bbox: [x0_pts, y0_pts, x1_pts, y1_pts] }  en puntos PDF
    """
    ui = template_data.get("ui", {})
    vw = ui.get("viewport_width") or 1
    vh = ui.get("viewport_height") or 1
    pw = ui.get("page_width_pts") or 595
    ph = ui.get("page_height_pts") or 842

    converted_zones = []
    for zona in template_data.get("zonas", []):
        bbox = [
            round(zona["x0"] * pw / vw, 2),
            round(zona["y0"] * ph / vh, 2),
            round(zona["x1"] * pw / vw, 2),
            round(zona["y1"] * ph / vh, 2),
        ]
        converted_zones.append({
            "field": zona["name"],
            "type": zona.get("type", "rect"),
            "bbox": bbox,
            "page_range": zona.get("page_range", "all"),
            "drawn_on_page": zona.get("drawn_on_page", 0),
        })

    return {
        "page": 1,
        "expected_page_width": pw,
        "expected_page_height": ph,
        "zones": converted_zones,
    }


def _unauthorized():
    return JSONResponse({"success": False, "message": "No autorizado"}, status_code=401)


# ── Página HTML ────────────────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def templates_page(request: Request, user=Depends(get_current_user)):
    if not user:
        from fastapi.responses import RedirectResponse
        return RedirectResponse("/auth/login")
    return templates_jinja.TemplateResponse("app/invoice_templates.html", {
        "request": request,
        "user": user,
        "current_page": "templates",
    })


# ── CRUD ───────────────────────────────────────────────────────────────────────

@router.get("/list")
async def templates_list(
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not user:
        return _unauthorized()
    result = await db.execute(
        select(InvoiceTemplate)
        .where(InvoiceTemplate.usuario_id == user.id)
        .order_by(InvoiceTemplate.updated_at.desc())
    )
    rows = result.scalars().all()
    return JSONResponse({
        "success": True,
        "data": [
            {"id": t.id, "name": t.name, "created_at": t.created_at.isoformat(),
             "updated_at": t.updated_at.isoformat()}
            for t in rows
        ],
    })


@router.get("/get/{template_id}")
async def templates_get(
    template_id: int,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not user:
        return _unauthorized()
    result = await db.execute(
        select(InvoiceTemplate).where(
            InvoiceTemplate.id == template_id,
            InvoiceTemplate.usuario_id == user.id,
        )
    )
    tmpl = result.scalar_one_or_none()
    if not tmpl:
        return JSONResponse({"success": False, "message": "Plantilla no encontrada"}, status_code=404)
    return JSONResponse({
        "success": True,
        "data": {
            "id": tmpl.id,
            "name": tmpl.name,
            "template_json": json.loads(tmpl.template_json),
        },
    })


@router.post("/save")
async def templates_save(
    name: str = Form(...),
    template: str = Form(...),
    template_id: int = Form(None),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not user:
        return _unauthorized()

    try:
        template_data = json.loads(template)
    except json.JSONDecodeError:
        return JSONResponse({"success": False, "message": "JSON inválido"}, status_code=400)

    if template_id:
        result = await db.execute(
            select(InvoiceTemplate).where(
                InvoiceTemplate.id == template_id,
                InvoiceTemplate.usuario_id == user.id,
            )
        )
        tmpl = result.scalar_one_or_none()
        if not tmpl:
            return JSONResponse({"success": False, "message": "Plantilla no encontrada"}, status_code=404)
        tmpl.name = name.strip()
        tmpl.template_json = json.dumps(template_data, ensure_ascii=False)
    else:
        tmpl = InvoiceTemplate(
            usuario_id=user.id,
            name=name.strip(),
            template_json=json.dumps(template_data, ensure_ascii=False),
        )
        db.add(tmpl)

    await db.commit()
    await db.refresh(tmpl)
    return JSONResponse({"success": True, "id": tmpl.id, "name": tmpl.name})


@router.delete("/{template_id}")
async def templates_delete(
    template_id: int,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not user:
        return _unauthorized()
    result = await db.execute(
        select(InvoiceTemplate).where(
            InvoiceTemplate.id == template_id,
            InvoiceTemplate.usuario_id == user.id,
        )
    )
    tmpl = result.scalar_one_or_none()
    if not tmpl:
        return JSONResponse({"success": False, "message": "Plantilla no encontrada"}, status_code=404)
    await db.delete(tmpl)
    await db.commit()
    return JSONResponse({"success": True})


# ── Extracción via VPS ─────────────────────────────────────────────────────────

@router.post("/extract")
async def templates_extract(
    pdf: UploadFile = File(...),
    template: str = Form(...),
    user=Depends(get_current_user),
):
    """
    Recibe el PDF y el JSON de zonas (formato UI), convierte al formato del VPS
    y llama al endpoint /extract del microservicio document-ai.
    """
    if not user:
        return _unauthorized()

    try:
        template_data = json.loads(template)
    except json.JSONDecodeError:
        return JSONResponse({"success": False, "message": "Template JSON inválido"}, status_code=400)

    vps_template = _convert_template_for_vps(template_data)
    pdf_bytes = await pdf.read()

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{settings.vps_extract_url}/extract",
                files={"file": (pdf.filename or "documento.pdf", BytesIO(pdf_bytes), "application/pdf")},
                data={"template": json.dumps(vps_template)},
            )
        if response.status_code != 200:
            return JSONResponse(
                {"success": False, "message": f"Error del VPS: {response.status_code}"},
                status_code=502,
            )
        vps_result = response.json()
    except httpx.ConnectError:
        return JSONResponse(
            {"success": False, "message": "No se pudo conectar al servicio de extracción. Verificá la URL del VPS."},
            status_code=503,
        )
    except Exception as exc:
        return JSONResponse({"success": False, "message": str(exc)}, status_code=500)

    # Normalizar respuesta: el VPS devuelve { "fields": {...} }
    fields = vps_result.get("fields") or vps_result.get("results") or vps_result
    results = [{"name": k, "value": v} for k, v in fields.items()] if isinstance(fields, dict) else []

    return JSONResponse({"success": True, "results": results, "raw": vps_result})
