"""
Sistema de permisos por sección.

Cada usuario no-admin tiene un JSON en `permisos`:
    { "inicio": {"ver": true, "editar": false}, ... }

is_admin=True bypasea todas las verificaciones.
"""
import json
from typing import Optional

# ── Secciones de la aplicación ────────────────────────────────────────────────
PERMISSION_SECTIONS = [
    {"key": "inicio",        "label": "🚀 Inicio"},
    {"key": "dashboard",     "label": "📊 Dashboard"},
    {"key": "upload",        "label": "📤 Analizar facturas"},
    {"key": "historial",     "label": "📁 Historial"},
    {"key": "lotes",         "label": "📦 Lotes"},
    {"key": "pdf_toolkit",   "label": "📄 Herramientas PDF"},
    {"key": "templates",     "label": "🗂️ Plantillas de extracción"},
    {"key": "consultar_cae", "label": "🔍 Consultar CAE"},
    {"key": "planes",        "label": "💳 Planes"},
    {"key": "feedback_admin","label": "💬 Ver feedback de usuarios"},
    {"key": "admin_usuarios","label": "⚙️ Administración de usuarios"},
]

SECTION_KEYS = {s["key"] for s in PERMISSION_SECTIONS}


def parse_permisos(raw: Optional[str]) -> dict:
    """Parsea el JSON de permisos; devuelve {} si es inválido o None."""
    if not raw:
        return {}
    try:
        return json.loads(raw) or {}
    except (json.JSONDecodeError, TypeError):
        return {}


def has_perm(user, section: str, level: str = "ver") -> bool:
    """
    Verifica si el usuario tiene permiso sobre una sección.

    level: "ver" | "editar"
    - is_admin siempre devuelve True.
    - No autenticado siempre devuelve False.
    """
    if user is None:
        return False
    if getattr(user, "is_admin", False):
        return True
    perms = parse_permisos(getattr(user, "permisos", None))
    sec = perms.get(section, {})
    if isinstance(sec, dict):
        if level == "ver":
            return bool(sec.get("ver"))
        if level == "editar":
            return bool(sec.get("editar"))
    return False


def default_permisos_admin() -> str:
    """Devuelve JSON con acceso total a todas las secciones."""
    return json.dumps({
        s["key"]: {"ver": True, "editar": True}
        for s in PERMISSION_SECTIONS
    })


def default_permisos_vacio() -> str:
    """Devuelve JSON sin acceso a nada (base para nuevos usuarios)."""
    return json.dumps({
        s["key"]: {"ver": False, "editar": False}
        for s in PERMISSION_SECTIONS
    })
