"""add accel_sample

Revision ID: j0k1l2m3n4o5
Revises: i9j0k1l2m3n4
Create Date: 2026-07-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "j0k1l2m3n4o5"
down_revision: Union[str, Sequence[str], None] = "i9j0k1l2m3n4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "accel_sample",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("driver", sa.String(), nullable=False),
        sa.Column("constructor", sa.String(), nullable=True),
        sa.Column("speed_kmh_json", sa.JSON(), nullable=False),
        sa.Column("longitudinal_accel_ms2_json", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["session.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_accel_sample_session_id", "accel_sample", ["session_id"])
    op.create_index("ix_accel_sample_driver", "accel_sample", ["driver"])


def downgrade() -> None:
    op.drop_index("ix_accel_sample_driver", table_name="accel_sample")
    op.drop_index("ix_accel_sample_session_id", table_name="accel_sample")
    op.drop_table("accel_sample")
