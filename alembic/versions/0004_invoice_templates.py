"""feat: tabla invoice_templates para plantillas de extracción

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-29
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    tablas = {r[0] for r in conn.execute(sa.text(
        "SELECT tablename FROM pg_tables WHERE schemaname='public'"
    ))}
    if "invoice_templates" not in tablas:
        op.create_table(
            "invoice_templates",
            sa.Column("id",            sa.Integer,      primary_key=True),
            sa.Column("usuario_id",    sa.Integer,      sa.ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False),
            sa.Column("name",          sa.String(255),  nullable=False),
            sa.Column("template_json", sa.Text,         nullable=False),
            sa.Column("created_at",    sa.DateTime,     nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at",    sa.DateTime,     nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_invoice_templates_usuario_id", "invoice_templates", ["usuario_id"])


def downgrade() -> None:
    op.drop_index("ix_invoice_templates_usuario_id", table_name="invoice_templates")
    op.drop_table("invoice_templates")
