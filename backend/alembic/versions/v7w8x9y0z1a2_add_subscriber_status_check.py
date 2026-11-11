"""constrain subscriber.status to the states in subscriber_status.py

NOT VALID: the constraint is enforced for every new write but existing rows are not scanned,
so a stray legacy value in production cannot make `alembic upgrade head` (which runs inside
the Railway start command) fail and crash-loop the API.

Revision ID: v7w8x9y0z1a2
Revises: u6v7w8x9y0z1
Create Date: 2026-11-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "v7w8x9y0z1a2"
down_revision: Union[str, Sequence[str], None] = "u6v7w8x9y0z1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE subscriber ADD CONSTRAINT ck_subscriber_status CHECK "
        "(status IN ('pending','confirmed','unsubscribed','bounced','complained')) NOT VALID"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE subscriber DROP CONSTRAINT ck_subscriber_status")
