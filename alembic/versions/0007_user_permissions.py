"""feat: is_admin y permisos en tabla usuarios

Revision ID: 0007
Revises: 0006
Create Date: 2026-04-30
"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    cols = {r[0] for r in conn.execute(sa.text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='usuarios' AND table_schema='public'"
    ))}
    if "is_admin" not in cols:
        op.add_column("usuarios", sa.Column("is_admin", sa.Boolean(), nullable=False, server_default="false"))
    if "permisos" not in cols:
        op.add_column("usuarios", sa.Column("permisos", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("usuarios", "permisos")
    op.drop_column("usuarios", "is_admin")
