"""merge_migrations

Revision ID: 3b9698ba7dd0
Revises: 696448994561, fix_migration_state
Create Date: 2026-05-03 02:46:26.650425

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '3b9698ba7dd0'
down_revision = ('696448994561', 'fix_migration_state')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
