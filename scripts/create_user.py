"""
Crea un usuario directamente en la base de datos.

Uso (dentro del container):
    python scripts/create_user.py

O pasando argumentos:
    python scripts/create_user.py --email=hola@ejemplo.com --nombre="Juan" --password=secreto123 --plan=pro
"""
import argparse
import asyncio
import sys
import os

# Asegurar que el path del proyecto esté en sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models.plan import Plan
from app.models.usuario import Usuario


async def crear_usuario(email: str, nombre: str, password: str, plan_nombre: str):
    async with AsyncSessionLocal() as db:
        # Verificar duplicado
        existing = await db.execute(select(Usuario).where(Usuario.email == email.lower().strip()))
        if existing.scalar_one_or_none():
            print(f"ERROR: Ya existe un usuario con el email '{email}'.")
            return

        # Obtener plan
        plan_result = await db.execute(select(Plan).where(Plan.nombre == plan_nombre))
        plan_obj = plan_result.scalar_one_or_none()
        if not plan_obj:
            print(f"ERROR: Plan '{plan_nombre}' no encontrado. Planes disponibles: Free, Pro")
            return

        usuario = Usuario(
            email=email.lower().strip(),
            password_hash=hash_password(password),
            nombre=nombre.strip(),
            plan_id=plan_obj.id,
            is_active=True,
            is_verified=True,
        )
        db.add(usuario)
        await db.commit()
        await db.refresh(usuario)

        print(f"\n✓ Usuario creado exitosamente:")
        print(f"  ID     : {usuario.id}")
        print(f"  Email  : {usuario.email}")
        print(f"  Nombre : {usuario.nombre}")
        print(f"  Plan   : {plan_obj.nombre}")
        print(f"  Activo : {usuario.is_active}")
        print(f"  Verificado: {usuario.is_verified}\n")


def main():
    parser = argparse.ArgumentParser(description="Crear usuario en IAFacturas")
    parser.add_argument("--email",    default=None)
    parser.add_argument("--nombre",   default=None)
    parser.add_argument("--password", default=None)
    parser.add_argument("--plan",     default="pro", choices=["free", "pro"])
    args = parser.parse_args()

    email    = args.email    or input("Email: ").strip()
    nombre   = args.nombre   or input("Nombre: ").strip()
    password = args.password or input("Contraseña: ").strip()
    plan     = "Pro" if args.plan == "pro" else "Free"

    if not email or not nombre or not password:
        print("ERROR: Email, nombre y contraseña son obligatorios.")
        sys.exit(1)

    if len(password) < 6:
        print("ERROR: La contraseña debe tener al menos 6 caracteres.")
        sys.exit(1)

    asyncio.run(crear_usuario(email, nombre, password, plan))


if __name__ == "__main__":
    main()
