"""Add LOW, MEDIUM and HIGH labels to auditseverity.

Revision ID: 20261115100000
Revises: 20261113120000
Create Date: 2026-11-15
"""
from alembic import op


revision = "20261115100000"
down_revision = "20261113120000"
branch_labels = None
depends_on = None


def upgrade():
    # PostgreSQL 12+ supports adding enum labels transactionally.
    # These labels are not used until the migration transaction commits.
    op.execute("ALTER TYPE auditseverity ADD VALUE IF NOT EXISTS 'LOW'")
    op.execute("ALTER TYPE auditseverity ADD VALUE IF NOT EXISTS 'MEDIUM'")
    op.execute("ALTER TYPE auditseverity ADD VALUE IF NOT EXISTS 'HIGH'")


def downgrade():
    # PostgreSQL does not support directly removing individual enum labels.
    pass