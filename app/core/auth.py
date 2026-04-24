"""
Dependency de autenticación: lee el JWT desde la cookie HTTP-only
y devuelve el usuario activo, o None si no está autenticado.
"""
from typing import Optional

from fastapi import Cookie, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.security import decode_token
from app.models.usuario import Usuario


async def get_current_user(
    access_token: Optional[str] = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
) -> Optional[Usuario]:
    """Devuelve el usuario autenticado o None."""
    if not access_token:
        return None
    payload = decode_token(access_token)
    if not payload or not payload.get("sub"):
        return None
    result = await db.execute(
        select(Usuario)
        .where(Usuario.id == int(payload["sub"]))
        .options(selectinload(Usuario.plan))
    )
    user = result.scalar_one_or_none()
    return user if (user and user.is_active) else None
