"""add digest_sent_at to race_weekend

Marks the first (and only) time poll's auto-send fired the real digest for a weekend, so a
later cron tick that re-observes an already-complete weekend does not send it again.

Revision ID: s4t5u6v7w8x9
Revises: r3s4t5u6v7w8
Create Date: 2026-08-21 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "s4t5u6v7w8x9"
down_revision: Union[str, Sequence[str], None] = "r3s4t5u6v7w8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "race_weekend",
        sa.Column("digest_sent_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("race_weekend", "digest_sent_at")
