"""feat: adjunto PDF en user_feedback

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-30
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    cols = {r[0] for r in conn.execute(sa.text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='user_feedback' AND table_schema='public'"
    ))}
    if "archivo_path" not in cols:
        op.add_column("user_feedback", sa.Column("archivo_path",   sa.String(500), nullable=True))
    if "archivo_nombre" not in cols:
        op.add_column("user_feedback", sa.Column("archivo_nombre", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("user_feedback", "archivo_nombre")
    op.drop_column("user_feedback", "archivo_path")
