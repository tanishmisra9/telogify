"""add sector_best, quali_character, stint tyre_ages_json

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-30 21:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('stint', sa.Column('tyre_ages_json', sa.JSON(), nullable=True))

    op.create_table(
        'sector_best',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=False),
        sa.Column('driver', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('sector', sa.Integer(), nullable=False),
        sa.Column('best_time_s', sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['session.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_sector_best_session_id'), 'sector_best', ['session_id'], unique=False)
    op.create_index(op.f('ix_sector_best_driver'), 'sector_best', ['driver'], unique=False)

    op.create_table(
        'quali_character',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=False),
        sa.Column('driver', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('constructor', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('lap_time_s', sa.Float(), nullable=True),
        sa.Column('top_speed_kmh', sa.Float(), nullable=True),
        sa.Column('min_speed_kmh', sa.Float(), nullable=True),
        sa.Column('full_throttle_pct', sa.Float(), nullable=True),
        sa.Column('corner_speeds_json', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['session_id'], ['session.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_quali_character_session_id'), 'quali_character', ['session_id'], unique=False)
    op.create_index(op.f('ix_quali_character_driver'), 'quali_character', ['driver'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_quali_character_driver'), table_name='quali_character')
    op.drop_index(op.f('ix_quali_character_session_id'), table_name='quali_character')
    op.drop_table('quali_character')
    op.drop_index(op.f('ix_sector_best_driver'), table_name='sector_best')
    op.drop_index(op.f('ix_sector_best_session_id'), table_name='sector_best')
    op.drop_table('sector_best')
    op.drop_column('stint', 'tyre_ages_json')
