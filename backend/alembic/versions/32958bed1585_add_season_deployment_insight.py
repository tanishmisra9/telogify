"""add season deployment insight

Revision ID: 32958bed1585
Revises: 4409de28fc1d
Create Date: 2026-07-16 23:03:44.891966

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel

# revision identifiers, used by Alembic.
revision: str = '32958bed1585'
down_revision: Union[str, Sequence[str], None] = '4409de28fc1d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('season_deployment_insight',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('year', sa.Integer(), nullable=False),
    sa.Column('rank', sa.Integer(), nullable=False),
    sa.Column('pu_name', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('works_team', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('teams_json', sa.JSON(), nullable=True),
    sa.Column('header', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('explanation_web', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('source_metrics_json', sa.JSON(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_season_deployment_insight_year'), 'season_deployment_insight', ['year'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_season_deployment_insight_year'), table_name='season_deployment_insight')
    op.drop_table('season_deployment_insight')
