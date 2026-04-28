"""
Servicio de consulta de facturas apócrifas — base APOC de ARCA/AFIP.

Descarga el listado público (sin CAPTCHA ni certificado) desde:
  https://servicioscf.afip.gob.ar/Facturacion/facturasApocrifas/DownloadFile.aspx

El archivo es un ZIP que contiene FacturasApocrifas.txt con los CUITs
declarados apócrifos. Se cachea en memoria y se refresca cada 24 horas.
"""
import io
import re
import time
import zipfile
from typing import Optional

import httpx

_DOWNLOAD_URL = (
    "https://servicioscf.afip.gob.ar/Facturacion/facturasApocrifas/DownloadFile.aspx"
)
_CACHE_TTL = 86400  # 24 horas

_cache: dict = {
    "records": {},       # cuit_clean -> {"fecha_condicion": str, "fecha_publicacion": str}
    "last_updated": None,
    "error": None,
}


def _clean_cuit(cuit: str) -> str:
    return re.sub(r"\D", "", cuit)


def _parse_txt(content: str) -> dict:
    """
    Parsea el TXT de facturas apócrifas de AFIP.
    Intenta detectar el separador (|, ;, tab, coma) y extrae CUIT + fechas.
    Retorna dict {cuit_clean: {"fecha_condicion": ..., "fecha_publicacion": ...}}
    """
    records: dict = {}
    lines = content.splitlines()
    if not lines:
        return records

    # Detectar separador en la primera línea no vacía
    sep = "|"
    for line in lines[:5]:
        if line.strip():
            for candidate in ("|", ";", "\t", ","):
                if candidate in line:
                    sep = candidate
                    break
            break

    for line in lines:
        line = line.strip()
        if not line:
            continue

        parts = [p.strip() for p in line.split(sep)]
        if not parts:
            continue

        # El CUIT suele ser la primera columna
        raw_cuit = parts[0]
        clean = _clean_cuit(raw_cuit)

        # Saltar cabecera o líneas que no parecen CUIT (11 dígitos)
        if not clean.isdigit() or len(clean) != 11:
            continue

        fecha_condicion = parts[1].strip() if len(parts) > 1 else ""
        fecha_publicacion = parts[2].strip() if len(parts) > 2 else ""

        records[clean] = {
            "fecha_condicion": fecha_condicion,
            "fecha_publicacion": fecha_publicacion,
        }

    return records


async def _refresh_cache() -> None:
    """Descarga y parsea la base APOC; actualiza el cache global."""
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(
                _DOWNLOAD_URL,
                headers={"User-Agent": "Mozilla/5.0 (compatible; IAFacturas/1.0)"},
            )
        resp.raise_for_status()

        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            # Buscar el primer archivo .txt dentro del ZIP
            txt_name = next(
                (n for n in zf.namelist() if n.lower().endswith(".txt")),
                zf.namelist()[0] if zf.namelist() else None,
            )
            if txt_name is None:
                raise ValueError("ZIP vacío o sin archivo TXT")

            raw_bytes = zf.read(txt_name)

        # Intentar decodificar con encodings típicos de AFIP
        for enc in ("utf-8", "latin-1", "cp1252"):
            try:
                content = raw_bytes.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            content = raw_bytes.decode("latin-1", errors="replace")

        records = _parse_txt(content)
        _cache["records"] = records
        _cache["last_updated"] = time.time()
        _cache["error"] = None

    except Exception as e:
        _cache["error"] = str(e)
        # No borrar records anteriores si los hay


async def _ensure_cache() -> None:
    """Refresca el cache si está vencido o vacío."""
    last = _cache["last_updated"]
    if last is None or (time.time() - last) > _CACHE_TTL:
        await _refresh_cache()


async def check_cuit_apoc(cuit: str) -> dict:
    """
    Verifica si un CUIT está en la base de facturas apócrifas de AFIP/ARCA.

    Retorna:
        {
            "is_apoc": bool,
            "fecha_condicion": str | None,
            "fecha_publicacion": str | None,
            "cache_age_hours": float,
            "error": str | None,
        }
    """
    await _ensure_cache()

    clean = _clean_cuit(cuit)
    record = _cache["records"].get(clean)
    age = (
        round((time.time() - _cache["last_updated"]) / 3600, 1)
        if _cache["last_updated"]
        else None
    )

    return {
        "is_apoc": record is not None,
        "fecha_condicion": record["fecha_condicion"] if record else None,
        "fecha_publicacion": record["fecha_publicacion"] if record else None,
        "cache_age_hours": age,
        "error": _cache["error"],
    }


async def get_cache_stats() -> dict:
    """Info sobre el estado del cache (para diagnóstico)."""
    await _ensure_cache()
    return {
        "total_cuits": len(_cache["records"]),
        "last_updated": _cache["last_updated"],
        "cache_age_hours": (
            round((time.time() - _cache["last_updated"]) / 3600, 1)
            if _cache["last_updated"]
            else None
        ),
        "error": _cache["error"],
    }
