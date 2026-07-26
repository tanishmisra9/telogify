"""drop orphaned raw_lap_times_json from stint

raw_lap_times_json was never part of main's schema -- it was added by a migration on the
abandoned mirco-vis branch (fdataanalysis alternate pace-spread view, deleted rather than
merged: the mean-ranked/un-fuel-corrected view was rejected in favor of the existing
median-anchored methodology). That branch's migration ran against local Postgres at some
point and was never downgraded before switching back to main, leaving the column stranded
in local dev only. Uses IF EXISTS so this is a safe no-op anywhere that never had the
column (Railway, a fresh clone, CI).

Revision ID: 900f8e20604d
Revises: q2r3s4t5u6v7
Create Date: 2026-07-25 21:49:16.370542

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '900f8e20604d'
down_revision: Union[str, Sequence[str], None] = 'q2r3s4t5u6v7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('ALTER TABLE stint DROP COLUMN IF EXISTS raw_lap_times_json')


def downgrade() -> None:
    pass
