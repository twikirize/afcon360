"""merge_20260717_rooms

Revision ID: d95160fba1fd
Revises: 20260701_add_room_types, db911bfe67b9
Create Date: 2026-07-17 19:45:53.055271

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd95160fba1fd'
down_revision = ('20260701_add_room_types', 'db911bfe67b9')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
