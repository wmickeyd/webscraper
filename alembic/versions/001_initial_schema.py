"""Initial schema

Revision ID: 001
Revises:
Create Date: 2026-01-01 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'tracked_sets',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=True),
        sa.Column('product_number', sa.String(), nullable=True),
        sa.Column('url', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('product_number'),
        sa.UniqueConstraint('url'),
    )
    op.create_index('ix_tracked_sets_id', 'tracked_sets', ['id'], unique=False)
    op.create_index('ix_tracked_sets_name', 'tracked_sets', ['name'], unique=False)
    op.create_index('ix_tracked_sets_product_number', 'tracked_sets', ['product_number'], unique=False)

    op.create_table(
        'price_history',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('set_id', sa.Integer(), nullable=True),
        sa.Column('price', sa.Float(), nullable=True),
        sa.Column('timestamp', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['set_id'], ['tracked_sets.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_price_history_id', 'price_history', ['id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_price_history_id', table_name='price_history')
    op.drop_table('price_history')
    op.drop_index('ix_tracked_sets_product_number', table_name='tracked_sets')
    op.drop_index('ix_tracked_sets_name', table_name='tracked_sets')
    op.drop_index('ix_tracked_sets_id', table_name='tracked_sets')
    op.drop_table('tracked_sets')
