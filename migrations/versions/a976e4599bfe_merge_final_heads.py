"""merge_final_heads

Revision ID: a976e4599bfe
Revises: 20260629_add_media_enhancements, 721f6a09485d
Create Date: 2026-06-30 21:55:03.535844

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a976e4599bfe'
down_revision = ('20260629_add_media_enhancements', '721f6a09485d')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
