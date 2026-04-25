"""fase5: api_key en usuarios, tipo_documento y metodo_extraccion en facturas

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-25
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "f5685366e080"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # usuarios: api_key
    cols_usuarios = {r[0] for r in conn.execute(sa.text(
        "SELECT column_name FROM information_schema.columns WHERE table_name='usuarios'"
    ))}
    if "api_key" not in cols_usuarios:
        op.add_column("usuarios", sa.Column("api_key", sa.String(64), nullable=True))
        op.create_unique_constraint("uq_usuarios_api_key", "usuarios", ["api_key"])
        op.create_index("ix_usuarios_api_key", "usuarios", ["api_key"])

    # facturas: tipo_documento y metodo_extraccion
    cols_facturas = {r[0] for r in conn.execute(sa.text(
        "SELECT column_name FROM information_schema.columns WHERE table_name='facturas'"
    ))}
    if "tipo_documento" not in cols_facturas:
        op.add_column("facturas", sa.Column("tipo_documento", sa.String(40), nullable=True))
    if "metodo_extraccion" not in cols_facturas:
        op.add_column("facturas", sa.Column("metodo_extraccion", sa.String(30), nullable=True))


def downgrade() -> None:
    op.drop_index("ix_usuarios_api_key", table_name="usuarios")
    op.drop_constraint("uq_usuarios_api_key", "usuarios", type_="unique")
    op.drop_column("usuarios", "api_key")
    op.drop_column("facturas", "tipo_documento")
    op.drop_column("facturas", "metodo_extraccion")
