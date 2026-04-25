"""Seed inicial: crea planes y usuario admin si no existen."""
import asyncio
from sqlalchemy import select, text
from app.core.database import AsyncSessionLocal
from app.models.plan import Plan
from app.models.usuario import Usuario
import bcrypt as _bcrypt

def hash_password(plain: str) -> str:
    return _bcrypt.hashpw(plain.encode(), _bcrypt.gensalt()).decode()


async def main():
    async with AsyncSessionLocal() as db:
        # ── Planes ──────────────────────────────────────────
        planes_existentes = (await db.execute(select(Plan))).scalars().all()
        if not planes_existentes:
            db.add_all([
                Plan(id=1, nombre="Free",  limite_mensual=10,  precio=0,     descripcion="Plan gratuito"),
                Plan(id=2, nombre="Pro",   limite_mensual=100, precio=9.99,  descripcion="Plan profesional"),
                Plan(id=3, nombre="Elite", limite_mensual=500, precio=29.99, descripcion="Plan elite"),
            ])
            await db.commit()
            print("OK Planes creados: Free / Pro / Elite")
        else:
            print("OK Planes ya existen:", [p.nombre for p in planes_existentes])

        # ── Usuario admin ────────────────────────────────────
        admin = (await db.execute(
            select(Usuario).where(Usuario.email == "admin@iafacturas.com")
        )).scalar_one_or_none()
        if not admin:
            db.add(Usuario(
                email="admin@iafacturas.com",
                password_hash=hash_password("Admin1234!"),
                nombre="Admin",
                plan_id=2,
                is_active=True,
                is_verified=True,
            ))
            await db.commit()
            print("OK Usuario admin creado: admin@iafacturas.com / Admin1234!")
        else:
            print("OK Admin ya existe:", admin.email)


asyncio.run(main())
