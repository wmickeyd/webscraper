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
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_columns = [c['name'] for c in inspector.get_columns('tracked_sets')]
    existing_indexes = [i['name'] for i in inspector.get_indexes('tracked_sets')]

    # Add new columns
    if 'retailer' not in existing_columns:
        op.add_column('tracked_sets', sa.Column('retailer', sa.String(), nullable=True, server_default='lego'))
    if 'target_price' not in existing_columns:
        op.add_column('tracked_sets', sa.Column('target_price', sa.Float(), nullable=True))
    if 'last_notified_price' not in existing_columns:
        op.add_column('tracked_sets', sa.Column('last_notified_price', sa.Float(), nullable=True))

    # Create index for retailer
    if 'ix_tracked_sets_retailer' not in existing_indexes:
        op.create_index('ix_tracked_sets_retailer', 'tracked_sets', ['retailer'], unique=False)

    # Remove old unique constraints using IF EXISTS to avoid aborting the transaction
    op.execute('ALTER TABLE tracked_sets DROP CONSTRAINT IF EXISTS tracked_sets_product_number_key')
    op.execute('ALTER TABLE tracked_sets DROP CONSTRAINT IF EXISTS tracked_sets_url_key')

    # Add the new unique constraint for (user_id, product_number, retailer)
    op.execute('ALTER TABLE tracked_sets DROP CONSTRAINT IF EXISTS uix_user_product_retailer')
    op.create_unique_constraint('uix_user_product_retailer', 'tracked_sets', ['user_id', 'product_number', 'retailer'])


def downgrade() -> None:
    op.drop_constraint('uix_user_product_retailer', 'tracked_sets', type_='unique')
    op.create_unique_constraint('tracked_sets_url_key', 'tracked_sets', ['url'])
    op.create_unique_constraint('tracked_sets_product_number_key', 'tracked_sets', ['product_number'])
    
    op.drop_index('ix_tracked_sets_retailer', table_name='tracked_sets')
    op.drop_column('tracked_sets', 'last_notified_price')
    op.drop_column('tracked_sets', 'target_price')
    op.drop_column('tracked_sets', 'retailer')
