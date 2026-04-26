"""Seed inicial: crea planes y usuario admin si no existen."""
import asyncio
from sqlalchemy import select, text
from app.core.database import AsyncSessionLocal
from app.models.lote import Lote  # noqa: F401 — necesario para resolver relaciones SQLAlchemy
from app.models.plan import Plan
from app.models.usuario import Usuario
import bcrypt as _bcrypt

def hash_password(plain: str) -> str:
    return _bcrypt.hashpw(plain.encode(), _bcrypt.gensalt()).decode()


async def main():
    async with AsyncSessionLocal() as db:
        # ── Planes — upsert por nombre ───────────────────────
        config_planes = [
            ("Free",  10,  0,     "Plan gratuito"),
            ("Pro",   500, 9.99,  "Plan profesional"),
            ("Elite", -1,  29.99, "Plan elite — ilimitado"),
        ]
        for nombre, limite, precio, desc in config_planes:
            p = (await db.execute(select(Plan).where(Plan.nombre == nombre))).scalar_one_or_none()
            if p:
                p.limite_mensual = limite
                p.precio         = precio
                p.descripcion    = desc
                print(f"OK Plan '{nombre}' actualizado: limite={limite}")
            else:
                db.add(Plan(nombre=nombre, limite_mensual=limite, precio=precio, descripcion=desc))
                print(f"OK Plan '{nombre}' creado")
        await db.commit()

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
            pro = (await db.execute(select(Plan).where(Plan.nombre == "Pro"))).scalar_one_or_none()
            if pro:
                admin.plan_id = pro.id
                await db.commit()
                print(f"OK Admin en plan Pro (plan_id={pro.id})")
            else:
                print("OK Admin ya existe:", admin.email, "| plan_id:", admin.plan_id)


asyncio.run(main())
