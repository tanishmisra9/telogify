"""add session_type to quali_insight

Sprint Qualifying now gets its own 2-insight batch alongside main Qualifying's, both stored in
quali_insight -- this discriminator keeps them from colliding on weekend_id+slot and lets each
batch's regen/delete stay scoped to its own session. Existing rows are all main-Qualifying
insights, so they default to "Q".

Revision ID: t5u6v7w8x9y0
Revises: s4t5u6v7w8x9
Create Date: 2026-09-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = "t5u6v7w8x9y0"
down_revision: Union[str, Sequence[str], None] = "s4t5u6v7w8x9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "quali_insight",
        sa.Column(
            "session_type",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
            server_default="Q",
        ),
    )


def downgrade() -> None:
    op.drop_column("quali_insight", "session_type")
