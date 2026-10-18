"""add_organisation_slug_column

Revision ID: bd9d3bb673aa
Revises: 71893e3a42a2
Create Date: 2026-09-15 23:24:45.840482

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'bd9d3bb673aa'
down_revision = '71893e3a42a2'
branch_labels = None
depends_on = None


def upgrade():
    # Neutralized: this migration duplicates 71893e3a42a2_add_organisation_slug.py,
    # which already adds organisations.slug (NOT NULL, matching the model),
    # ix_org_slug_unique and uq_org_slug. Re-adding here raised
    # DuplicateColumn on clean install. Proven duplicate -> minimal no-op.
    pass


def downgrade():
    # Kept symmetric with the neutralized upgrade; the column/index/constraint
    # are owned by 71893e3a42a2 and dropped by its downgrade.
    pass
