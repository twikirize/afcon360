"""Merge media migration

Revision ID: 721f6a09485d
Revises: 20260627_add_media, 5582ce532c6f
Create Date: 2026-06-29 15:49:48.882886

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '721f6a09485d'
down_revision = ('20260627_add_media_tables', '5582ce532c6f')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
