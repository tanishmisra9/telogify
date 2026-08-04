"""add subscriber double opt-in columns, audit log, RLS and audit triggers

Turns the single-step `subscriber` row into a double opt-in record (status + hashed, expiring
verification token) and adds the append-only `subscriber_audit` log with the row-change trigger,
immutability trigger and row level security policies that back it.

The raw SQL lives in telogify/security_sql.py rather than inline here because tests build their
schema with SQLModel.metadata.create_all(), not Alembic, and would otherwise never see it.

Backfill: pre-existing rows opted in under the old single-step flow, so they are marked
'confirmed' with confirmed_at = created_at. Marking them 'pending' would silently drop real
subscribers off the digest the moment the confirmed-only filter lands.

Revision ID: r3s4t5u6v7w8
Revises: 900f8e20604d
Create Date: 2026-08-04 01:40:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op

from telogify.security_sql import SUBSCRIBER_SECURITY_DDL, SUBSCRIBER_SECURITY_DOWN_DDL

# revision identifiers, used by Alembic.
revision: str = 'r3s4t5u6v7w8'
down_revision: Union[str, Sequence[str], None] = '900f8e20604d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('subscriber', sa.Column('status', sqlmodel.sql.sqltypes.AutoString(),
                                          nullable=False, server_default='pending'))
    op.add_column('subscriber', sa.Column('confirmed_at', sa.DateTime(), nullable=True))
    op.add_column('subscriber', sa.Column('verify_token_hash',
                                          sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.add_column('subscriber', sa.Column('verify_expires_at', sa.DateTime(), nullable=True))
    op.create_index(op.f('ix_subscriber_status'), 'subscriber', ['status'], unique=False)
    op.create_index(op.f('ix_subscriber_verify_token_hash'), 'subscriber',
                    ['verify_token_hash'], unique=True)

    # Anyone already in the table opted in before double opt-in existed. Grandfather them.
    op.execute("UPDATE subscriber SET status = 'confirmed', confirmed_at = created_at")

    op.create_table(
        'subscriber_audit',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('subscriber_id', sa.Integer(), nullable=True),
        sa.Column('email', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('action', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('old_data', sa.JSON(), nullable=True),
        sa.Column('new_data', sa.JSON(), nullable=True),
        sa.Column('actor_key', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('actor_ip_hash', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('actor_user_agent', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_subscriber_audit_subscriber_id'), 'subscriber_audit',
                    ['subscriber_id'], unique=False)
    op.create_index(op.f('ix_subscriber_audit_email'), 'subscriber_audit', ['email'],
                    unique=False)
    op.create_index(op.f('ix_subscriber_audit_action'), 'subscriber_audit', ['action'],
                    unique=False)
    op.create_index(op.f('ix_subscriber_audit_actor_ip_hash'), 'subscriber_audit',
                    ['actor_ip_hash'], unique=False)
    op.create_index(op.f('ix_subscriber_audit_created_at'), 'subscriber_audit', ['created_at'],
                    unique=False)
    # The rate limiter counts recent attempts per IP and per email; these are the two shapes
    # it queries, and it runs on every signup, so neither is optional.
    op.create_index('ix_subscriber_audit_ip_time', 'subscriber_audit',
                    ['actor_ip_hash', 'created_at'], unique=False)
    op.create_index('ix_subscriber_audit_email_time', 'subscriber_audit',
                    ['email', 'created_at'], unique=False)

    for stmt in SUBSCRIBER_SECURITY_DDL:
        op.execute(stmt)

    # Drop the server_default now that every row has a value; the model supplies it going
    # forward, matching how every other column in this schema behaves.
    op.alter_column('subscriber', 'status', server_default=None)


def downgrade() -> None:
    for stmt in SUBSCRIBER_SECURITY_DOWN_DDL:
        op.execute(stmt)

    op.drop_table('subscriber_audit')
    op.drop_index(op.f('ix_subscriber_verify_token_hash'), table_name='subscriber')
    op.drop_index(op.f('ix_subscriber_status'), table_name='subscriber')
    op.drop_column('subscriber', 'verify_expires_at')
    op.drop_column('subscriber', 'verify_token_hash')
    op.drop_column('subscriber', 'confirmed_at')
    op.drop_column('subscriber', 'status')
