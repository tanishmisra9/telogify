"""add digest_design to race_weekend

Tracks which of the 3 digest email designs (production/neubrutalist/conversational) was sent
for a weekend, set once on first send. Also doubles as the rotation history a future send reads
back to pick the next design.

Revision ID: p1q2r3s4t5u6
Revises: n5o6p7q8r9s0
Create Date: 2026-07-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = "p1q2r3s4t5u6"
down_revision: Union[str, Sequence[str], None] = "n5o6p7q8r9s0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "race_weekend",
        sa.Column("digest_design", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("race_weekend", "digest_design")
