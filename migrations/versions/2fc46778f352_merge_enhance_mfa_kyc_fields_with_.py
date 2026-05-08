"""Merge enhance_mfa_kyc_fields with existing head

Revision ID: 2fc46778f352
Revises: enhance_mfa_kyc_fields, f898e8aae452
Create Date: 2026-05-07 18:00:01.423862

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '2fc46778f352'
down_revision = ('enhance_mfa_kyc_fields', 'f898e8aae452')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
