"""fase6: tabla lotes y FK lote_id en facturas

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-26
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    tablas = {r[0] for r in conn.execute(sa.text(
        "SELECT tablename FROM pg_tables WHERE schemaname='public'"
    ))}

    # ── Crear tabla lotes ───────────────────────────────────────────────────────
    if "lotes" not in tablas:
        op.create_table(
            "lotes",
            sa.Column("id",          sa.Integer,     primary_key=True),
            sa.Column("nombre",      sa.String(200),  nullable=False),
            sa.Column("usuario_id",  sa.Integer,      sa.ForeignKey("usuarios.id"), nullable=False),
            sa.Column("created_at",  sa.DateTime,     nullable=False, server_default=sa.func.now()),
            sa.Column("estado",      sa.String(20),   nullable=False, server_default="pendiente"),
            sa.Column("total",       sa.Integer,      nullable=False, server_default="0"),
            sa.Column("procesados",  sa.Integer,      nullable=False, server_default="0"),
            sa.Column("errores",     sa.Integer,      nullable=False, server_default="0"),
        )
        op.create_index("ix_lotes_usuario_id", "lotes", ["usuario_id"])

    # ── Agregar lote_id a facturas ─────────────────────────────────────────────
    cols = {r[0] for r in conn.execute(sa.text(
        "SELECT column_name FROM information_schema.columns WHERE table_name='facturas'"
    ))}
    if "lote_id" not in cols:
        op.add_column("facturas", sa.Column(
            "lote_id", sa.Integer,
            sa.ForeignKey("lotes.id"),
            nullable=True,
        ))
        op.create_index("ix_facturas_lote_id", "facturas", ["lote_id"])


def downgrade() -> None:
    op.drop_index("ix_facturas_lote_id", table_name="facturas")
    op.drop_column("facturas", "lote_id")
    op.drop_index("ix_lotes_usuario_id", table_name="lotes")
    op.drop_table("lotes")
