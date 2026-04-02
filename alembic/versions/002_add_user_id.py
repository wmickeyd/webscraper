"""Add user_id to tracked_sets

Revision ID: 002
Revises: 001
Create Date: 2026-04-02 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('tracked_sets', sa.Column('user_id', sa.String(), nullable=True))
    op.create_index('ix_tracked_sets_user_id', 'tracked_sets', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_tracked_sets_user_id', table_name='tracked_sets')
    op.drop_column('tracked_sets', 'user_id')
