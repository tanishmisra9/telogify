"""add quali insight

Revision ID: 4409de28fc1d
Revises: l2m3n4o5p6q7
Create Date: 2026-07-12 23:03:36.108954

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '4409de28fc1d'
down_revision: Union[str, Sequence[str], None] = 'l2m3n4o5p6q7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('quali_insight',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('weekend_id', sa.Integer(), nullable=False),
    sa.Column('slot', sa.Integer(), nullable=False),
    sa.Column('team', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('header', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('explanation_web', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('explanation_email', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('source_tool_calls_json', sa.JSON(), nullable=True),
    sa.ForeignKeyConstraint(['weekend_id'], ['race_weekend.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_quali_insight_weekend_id'), 'quali_insight', ['weekend_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_quali_insight_weekend_id'), table_name='quali_insight')
    op.drop_table('quali_insight')
