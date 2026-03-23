"""add temporary_hold to accommodationblockedreason

Revision ID: da0346b38553
Revises: fbebb1d6d968
Create Date: 2026-03-21 23:33:48.807849

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'da0346b38553'
down_revision = 'fbebb1d6d968'
branch_labels = None
depends_on = None

# Required for PostgreSQL enum changes - cannot run inside a transaction
transaction_per_migration = False

def upgrade():
    op.execute("ALTER TYPE accommodationblockedreason ADD VALUE IF NOT EXISTS 'temporary_hold'")

def downgrade():
    pass

