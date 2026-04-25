"""
Router de validación CAE — Fase 5.

Endpoints:
  GET  /cae/validar?cae=X&cuit=Y   — valida un CAE online con AFIP
  GET  /cae/validar/local?cae=X    — validación local (sin red, por fecha embebida)

Ambos endpoints requieren autenticación (JWT cookie) para proteger
la consulta de abuso. Los resultados se cachean en Redis (TTL 1h).
"""
from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from app.core.auth import get_current_user
from app.services.afip import validar_cae, _validar_cae_local

router = APIRouter(prefix="/cae", tags=["CAE / AFIP"])


@router.get("/validar")
async def validar_cae_endpoint(
    cae:  str = Query(..., description="CAE de 14 dígitos", min_length=14, max_length=14),
    cuit: str = Query(..., description="CUIT del emisor (con o sin guiones)"),
    user=Depends(get_current_user),
):
    """
    Valida un CAE contra el webservice de AFIP.
    Resultado cacheado en Redis por 1 hora para evitar sobrecarga.

    Respuesta:
    ```json
    {
      "valido": true,
      "estado": "VIGENTE",
      "cae": "12345678901234",
      "vencimiento": "2026-06-30"
    }
    ```
    """
    if not user:
        return JSONResponse({"error": "No autorizado"}, status_code=401)

    resultado = await validar_cae(cae, cuit)

    # Limpiar campos internos antes de devolver al cliente
    return JSONResponse({
        "valido":      resultado["valido"],
        "estado":      resultado["estado"],
        "cae":         resultado["cae"],
        "vencimiento": resultado["vencimiento"],
    })


@router.get("/validar/local")
async def validar_cae_local_endpoint(
    cae: str = Query(..., description="CAE de 14 dígitos", min_length=14, max_length=14),
    user=Depends(get_current_user),
):
    """
    Validación local del CAE sin consultar AFIP.
    Extrae la fecha de vencimiento embebida en los últimos 8 dígitos del CAE.
    Más rápido pero menos preciso que la consulta online.
    """
    if not user:
        return JSONResponse({"error": "No autorizado"}, status_code=401)

    resultado = _validar_cae_local(cae)
    return JSONResponse({
        "valido":      resultado["valido"],
        "estado":      resultado["estado"],
        "cae":         resultado["cae"],
        "vencimiento": resultado["vencimiento"],
    })
