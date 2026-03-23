"""add TEMPORARY_HOLD uppercase to accommodationblockedreason

Revision ID: 171e85b93e68
Revises: da0346b38553
Create Date: 2026-03-21 23:46:17.759155

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '171e85b93e68'
down_revision = 'da0346b38553'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TYPE accommodationblockedreason ADD VALUE IF NOT EXISTS 'TEMPORARY_HOLD'")

def downgrade():
    pass