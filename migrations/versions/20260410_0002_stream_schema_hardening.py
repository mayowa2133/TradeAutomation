"""Expand order-book sequence capacity and stream error storage."""

from alembic import op
import sqlalchemy as sa


revision = "20260410_0002"
down_revision = "20260409_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("orderbook_snapshots") as batch_op:
        batch_op.alter_column(
            "sequence",
            existing_type=sa.Integer(),
            type_=sa.BigInteger(),
            existing_nullable=True,
        )
    with op.batch_alter_table("stream_status") as batch_op:
        batch_op.alter_column(
            "error_message",
            existing_type=sa.String(length=255),
            type_=sa.Text(),
            existing_nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("stream_status") as batch_op:
        batch_op.alter_column(
            "error_message",
            existing_type=sa.Text(),
            type_=sa.String(length=255),
            existing_nullable=True,
        )
    with op.batch_alter_table("orderbook_snapshots") as batch_op:
        batch_op.alter_column(
            "sequence",
            existing_type=sa.BigInteger(),
            type_=sa.Integer(),
            existing_nullable=True,
        )
