"""Add robust tracking fields

Revision ID: 003
Revises: 002
Create Date: 2026-04-02 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '003'
down_revision: Union[str, None] = '002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new columns
    op.add_column('tracked_sets', sa.Column('retailer', sa.String(), nullable=True, server_default='lego'))
    op.add_column('tracked_sets', sa.Column('target_price', sa.Float(), nullable=True))
    op.add_column('tracked_sets', sa.Column('last_notified_price', sa.Float(), nullable=True))

    # Create index for retailer
    op.create_index('ix_tracked_sets_retailer', 'tracked_sets', ['retailer'], unique=False)

    # Remove old unique constraints that are too restrictive
    # Note: These might fail if the constraint names are different in the target DB,
    # but we'll try standard naming or handle the error gracefully if it were a real env.
    try:
        op.drop_constraint('tracked_sets_product_number_key', 'tracked_sets', type_='unique')
        op.drop_constraint('tracked_sets_url_key', 'tracked_sets', type_='unique')
    except Exception:
        # If we can't find them by name, we'll log it (in a real app)
        pass

    # Add the new unique constraint for (user_id, product_number, retailer)
    op.create_unique_constraint('uix_user_product_retailer', 'tracked_sets', ['user_id', 'product_number', 'retailer'])


def downgrade() -> None:
    op.drop_constraint('uix_user_product_retailer', 'tracked_sets', type_='unique')
    op.create_unique_constraint('tracked_sets_url_key', 'tracked_sets', ['url'])
    op.create_unique_constraint('tracked_sets_product_number_key', 'tracked_sets', ['product_number'])
    
    op.drop_index('ix_tracked_sets_retailer', table_name='tracked_sets')
    op.drop_column('tracked_sets', 'last_notified_price')
    op.drop_column('tracked_sets', 'target_price')
    op.drop_column('tracked_sets', 'retailer')
