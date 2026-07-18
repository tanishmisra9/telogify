"""add model_used and prompt_version to insight tables

Revision ID: 3df6990e5b55
Revises: 32958bed1585
Create Date: 2026-07-18 18:21:37.331423

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel

# revision identifiers, used by Alembic.
revision: str = '3df6990e5b55'
down_revision: Union[str, Sequence[str], None] = '32958bed1585'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('insight', sa.Column('model_used', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.add_column('insight', sa.Column('prompt_version', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.add_column('quali_insight', sa.Column('model_used', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.add_column('quali_insight', sa.Column('prompt_version', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.add_column('season_deployment_insight', sa.Column('model_used', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.add_column('season_deployment_insight', sa.Column('prompt_version', sqlmodel.sql.sqltypes.AutoString(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('season_deployment_insight', 'prompt_version')
    op.drop_column('season_deployment_insight', 'model_used')
    op.drop_column('quali_insight', 'prompt_version')
    op.drop_column('quali_insight', 'model_used')
    op.drop_column('insight', 'prompt_version')
    op.drop_column('insight', 'model_used')
