"""Add risk decision source enum label for Postgres runtimes."""

from alembic import op


revision = "20260411_0003"
down_revision = "20260410_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE decisionsource ADD VALUE IF NOT EXISTS 'RISK'")


def downgrade() -> None:
    # PostgreSQL enum value removal is intentionally not attempted here.
    pass
