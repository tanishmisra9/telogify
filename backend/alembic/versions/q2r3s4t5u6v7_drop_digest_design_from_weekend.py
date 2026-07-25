"""drop digest_design from race_weekend

Neubrutalist is now the only digest design; the rotation history this column tracked
(production/neubrutalist/conversational) no longer applies.

Revision ID: q2r3s4t5u6v7
Revises: p1q2r3s4t5u6
Create Date: 2026-07-25 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = "q2r3s4t5u6v7"
down_revision: Union[str, Sequence[str], None] = "p1q2r3s4t5u6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("race_weekend", "digest_design")


def downgrade() -> None:
    op.add_column(
        "race_weekend",
        sa.Column("digest_design", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    )
