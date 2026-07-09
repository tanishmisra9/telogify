"""add weekend_recap and wikipedia_title

Revision ID: g7h8i9j0k1l2
Revises: f6a7b8c9d0e1
Create Date: 2026-07-06 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "g7h8i9j0k1l2"
down_revision: Union[str, Sequence[str], None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("race_weekend", sa.Column("wikipedia_title", sa.String(), nullable=True))
    op.create_table(
        "weekend_recap",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("weekend_id", sa.Integer(), nullable=False),
        sa.Column("page_title", sa.String(), nullable=True),
        sa.Column("page_id", sa.Integer(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(), nullable=False),
        sa.Column("sessions_json", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["weekend_id"], ["race_weekend.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("weekend_id"),
    )
    op.create_index("ix_weekend_recap_weekend_id", "weekend_recap", ["weekend_id"])


def downgrade() -> None:
    op.drop_index("ix_weekend_recap_weekend_id", table_name="weekend_recap")
    op.drop_table("weekend_recap")
    op.drop_column("race_weekend", "wikipedia_title")
