"""merge_two_heads

Revision ID: 559ed1dc362b
Revises: 2fc46778f352, enhance_mfa_kyc_fields_fixed
Create Date: 2026-05-07 19:33:15.119469

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '559ed1dc362b'
down_revision = ('2fc46778f352', 'enhance_mfa_kyc_fields_fixed')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
