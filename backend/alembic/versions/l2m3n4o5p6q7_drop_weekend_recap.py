"""drop weekend_recap and wikipedia_title

The Wikipedia recap feature is fully removed: across 9 rounds of real 2026 data it never
once produced a candidate insight (0/99 recap_outcome candidates mined) or contributed to a
published insight (0/27), while a network hang fetching it stalled ingest for 20+ minutes in
a sandboxed environment. Reverses g7h8i9j0k1l2 exactly.

Revision ID: l2m3n4o5p6q7
Revises: k1l2m3n4o5p6
Create Date: 2026-07-12 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'l2m3n4o5p6q7'
down_revision: Union[str, Sequence[str], None] = 'k1l2m3n4o5p6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index('ix_weekend_recap_weekend_id', table_name='weekend_recap')
    op.drop_table('weekend_recap')
    op.drop_column('race_weekend', 'wikipedia_title')


def downgrade() -> None:
    op.add_column('race_weekend', sa.Column('wikipedia_title', sa.String(), nullable=True))
    op.create_table(
        'weekend_recap',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('weekend_id', sa.Integer(), nullable=False),
        sa.Column('page_title', sa.String(), nullable=True),
        sa.Column('page_id', sa.Integer(), nullable=True),
        sa.Column('fetched_at', sa.DateTime(), nullable=False),
        sa.Column('sessions_json', sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(['weekend_id'], ['race_weekend.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('weekend_id'),
    )
    op.create_index('ix_weekend_recap_weekend_id', 'weekend_recap', ['weekend_id'])
