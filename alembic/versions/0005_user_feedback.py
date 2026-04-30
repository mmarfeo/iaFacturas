"""feat: tabla user_feedback para comentarios de usuarios

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-30
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    tablas = {r[0] for r in conn.execute(sa.text(
        "SELECT tablename FROM pg_tables WHERE schemaname='public'"
    ))}
    if "user_feedback" not in tablas:
        op.create_table(
            "user_feedback",
            sa.Column("id",          sa.Integer,     primary_key=True),
            sa.Column("usuario_id",  sa.Integer,     sa.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True),
            sa.Column("tipo",        sa.String(20),  nullable=False),
            sa.Column("mensaje",     sa.Text,        nullable=False),
            sa.Column("pagina",      sa.String(255), nullable=True),
            sa.Column("created_at",  sa.DateTime,    nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_user_feedback_usuario_id", "user_feedback", ["usuario_id"])


def downgrade() -> None:
    op.drop_index("ix_user_feedback_usuario_id", table_name="user_feedback")
    op.drop_table("user_feedback")
