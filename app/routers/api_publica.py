"""
API Pública v1 — Procesamiento de documentos vía API key.

Permite a sistemas externos enviar PDFs/imágenes y obtener
los datos extraídos sin necesidad de sesión web (cookie JWT).

Autenticación: header  X-API-Key: <tu_clave>
               o param  ?api_key=<tu_clave>

Endpoints:
  POST /api/v1/documentos          — sube documento, retorna job_id
  GET  /api/v1/documentos/{job_id} — consulta estado y resultado
  GET  /app/perfil/api-key         — página HTML para gestionar API key
  POST /app/perfil/api-key/generar — genera/regenera API key (requiere cookie auth)

Flujo típico:
  1. POST /api/v1/documentos  → { "job_id": 42 }
  2. Polling GET /api/v1/documentos/42 hasta estado="completado"
  3. Leer campo "resultado" con todos los datos extraídos
"""
import secrets
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Header, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.factura import Factura
from app.models.plan import Plan
from app.models.usuario import Usuario

router     = APIRouter(tags=["API Pública"])
templates  = Jinja2Templates(directory="app/templates")
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


# ═══════════════════════════════════════════════════════════
# DEPENDENCY — autenticación por API key
# ═══════════════════════════════════════════════════════════

async def get_user_by_api_key(
    x_api_key: str = Header(default=None, alias="X-API-Key"),
    api_key:   str = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> Usuario:
    """
    Autentica por X-API-Key header o ?api_key= query param.
    Lanza 401 si la clave es inválida o el usuario está inactivo.
    """
    clave = x_api_key or api_key
    if not clave:
        raise _unauth("Se requiere X-API-Key header o ?api_key= param")

    res = await db.execute(
        select(Usuario).where(Usuario.api_key == clave)
    )
    user = res.scalar_one_or_none()

    if not user or not user.is_active:
        raise _unauth("API key inválida o cuenta inactiva")

    return user


def _unauth(detail: str):
    from fastapi import HTTPException
    return HTTPException(status_code=401, detail=detail)


# ═══════════════════════════════════════════════════════════
# HELPER — verificar límite de plan
# ═══════════════════════════════════════════════════════════

async def _check_plan_limit(user: Usuario, db: AsyncSession) -> tuple[bool, str]:
    """Retorna (permitido, mensaje_error)."""
    from datetime import date
    plan_res = await db.execute(select(Plan).where(Plan.id == user.plan_id))
    plan = plan_res.scalar_one_or_none()
    if not plan or not plan.limite_mensual:
        return True, ""
    hoy = date.today()
    uso_res = await db.execute(
        select(func.count(Factura.id))
        .where(Factura.usuario_id == user.id)
        .where(func.extract("month", Factura.created_at) == hoy.month)
        .where(func.extract("year",  Factura.created_at) == hoy.year)
    )
    uso = uso_res.scalar() or 0
    if uso >= plan.limite_mensual:
        return False, f"Límite mensual de {plan.limite_mensual} documentos alcanzado"
    return True, ""


# ═══════════════════════════════════════════════════════════
# POST /api/v1/documentos — subir documento
# ═══════════════════════════════════════════════════════════

@router.post("/api/v1/documentos")
async def api_subir_documento(
    file: UploadFile = File(...),
    user: Usuario = Depends(get_user_by_api_key),
    db:   AsyncSession = Depends(get_db),
):
    """
    Sube un documento (PDF o imagen) para procesamiento asíncrono.

    **Headers requeridos:**
    - `X-API-Key`: clave de API del usuario

    **Body (multipart/form-data):**
    - `file`: archivo PDF, JPG, PNG, etc.

    **Respuesta:**
    ```json
    {
      "ok": true,
      "job_id": 42,
      "mensaje": "Documento recibido y en cola de procesamiento"
    }
    ```
    Usar `GET /api/v1/documentos/{job_id}` para consultar el resultado.
    """
    # Verificar límite de plan
    permitido, msg = await _check_plan_limit(user, db)
    if not permitido:
        return JSONResponse({"ok": False, "error": msg}, status_code=429)

    # Validar tipo de archivo
    ext = Path(file.filename or "doc").suffix.lower()
    if ext not in {".pdf", ".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp"}:
        return JSONResponse(
            {"ok": False, "error": f"Tipo de archivo no soportado: {ext}"},
            status_code=400,
        )

    # Guardar archivo
    filename = f"{user.id}_{uuid.uuid4().hex}{ext}"
    filepath = UPLOAD_DIR / filename
    content  = await file.read()
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
    except Exception as e:
        print(f"[CELERY WARNING] No se pudo encolar: {e}")

    return JSONResponse({
        "ok":      True,
        "job_id":  factura.id,
        "mensaje": "Documento recibido y en cola de procesamiento",
    })


# ═══════════════════════════════════════════════════════════
# GET /api/v1/documentos/{job_id} — consultar resultado
# ═══════════════════════════════════════════════════════════

@router.get("/api/v1/documentos/{job_id}")
async def api_resultado_documento(
    job_id: int,
    user:   Usuario = Depends(get_user_by_api_key),
    db:     AsyncSession = Depends(get_db),
):
    """
    Consulta el estado y resultado del procesamiento de un documento.

    **Estados posibles:** `pendiente` | `procesando` | `completado` | `error`

    **Respuesta cuando completado:**
    ```json
    {
      "ok": true,
      "job_id": 42,
      "estado": "completado",
      "tipo_documento": "factura_a",
      "metodo_extraccion": "pdfplumber",
      "resultado": {
        "cae": "12345678901234",
        "cuit_emisor": "30-99999999-9",
        "importe_total": 15000.00,
        "fecha_emision": "2026-04-25",
        ...
      },
      "cae_valido": true,
      "cae_vencimiento": "2026-05-31"
    }
    ```
    """
    res = await db.execute(
        select(Factura).where(
            Factura.id == job_id,
            Factura.usuario_id == user.id,
        )
    )
    factura = res.scalar_one_or_none()

    if not factura:
        return JSONResponse(
            {"ok": False, "error": "Documento no encontrado"},
            status_code=404,
        )

    respuesta: dict = {
        "ok":     True,
        "job_id": factura.id,
        "estado": factura.estado,
    }

    if factura.estado == "completado":
        respuesta.update({
            "tipo_documento":    factura.tipo_documento,
            "metodo_extraccion": factura.metodo_extraccion,
            "resultado":         factura.datos_extraidos or {},
            "cae_valido":        factura.cae_valido,
            "cae_vencimiento":   factura.cae_vencimiento.isoformat() if factura.cae_vencimiento else None,
            "cuit_emisor":       factura.cuit_emisor,
            "importe":           float(factura.importe) if factura.importe else None,
            "fecha_factura":     factura.fecha_factura.isoformat() if factura.fecha_factura else None,
        })
    elif factura.estado == "error":
        respuesta["error"] = (
            factura.datos_extraidos.get("error") if factura.datos_extraidos else "Error desconocido"
        )

    return JSONResponse(respuesta)


# ═══════════════════════════════════════════════════════════
# GESTIÓN DE API KEY — páginas HTML (requieren cookie auth)
# ═══════════════════════════════════════════════════════════

@router.get("/app/perfil/api-key", response_class=HTMLResponse)
async def api_key_page(
    request: Request,
    user: Usuario = Depends(get_current_user),
    db:   AsyncSession = Depends(get_db),
):
    """Página para ver y gestionar la API key del usuario."""
    if not user:
        return RedirectResponse("/auth/login", status_code=302)
    return templates.TemplateResponse("app/api_key.html", {
        "request":  request,
        "user":     user,
        "api_key":  user.api_key,
        "current_page": "api_key",
    })


@router.post("/app/perfil/api-key/generar")
async def generar_api_key(
    user: Usuario = Depends(get_current_user),
    db:   AsyncSession = Depends(get_db),
):
    """Genera o regenera la API key del usuario."""
    if not user:
        return JSONResponse({"error": "No autorizado"}, status_code=401)

    nueva_clave = secrets.token_hex(32)  # 64 caracteres hex

    res = await db.execute(select(Usuario).where(Usuario.id == user.id))
    usuario_db = res.scalar_one()
    usuario_db.api_key = nueva_clave
    await db.commit()

    return JSONResponse({"ok": True, "api_key": nueva_clave})


@router.delete("/app/perfil/api-key")
async def revocar_api_key(
    user: Usuario = Depends(get_current_user),
    db:   AsyncSession = Depends(get_db),
):
    """Revoca la API key del usuario (la deja en null)."""
    if not user:
        return JSONResponse({"error": "No autorizado"}, status_code=401)

    res = await db.execute(select(Usuario).where(Usuario.id == user.id))
    usuario_db = res.scalar_one()
    usuario_db.api_key = None
    await db.commit()

    return JSONResponse({"ok": True, "mensaje": "API key revocada"})
