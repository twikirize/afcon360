"""Still_wallet

Revision ID: bd22abbdba18
Revises: 3b9698ba7dd0
Create Date: 2026-05-03 16:35:54.484498

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = 'bd22abbdba18'
down_revision = '3b9698ba7dd0'
branch_labels = None
depends_on = None


def upgrade():
    # Add account_id column as UUID to match accounts.id
    with op.batch_alter_table('transactions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('account_id', UUID(as_uuid=True), nullable=True))
        batch_op.create_index('ix_transactions_account_id', ['account_id'], unique=False)
        batch_op.create_foreign_key(
            'fk_transactions_account_id',
            'accounts',
            ['account_id'],
            ['id'],
            ondelete='SET NULL'
        )


def downgrade():
    with op.batch_alter_table('transactions', schema=None) as batch_op:
        batch_op.drop_constraint('fk_transactions_account_id', type_='foreignkey')
        batch_op.drop_index('ix_transactions_account_id')
        batch_op.drop_column('account_id')