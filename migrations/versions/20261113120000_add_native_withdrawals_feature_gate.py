"""Add an independent default-off gate for native customer withdrawals.

Revision ID: 20261113120000
Revises: d85ed80bacdf
Create Date: 2026-11-13 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "20261113120000"
down_revision = "d85ed80bacdf"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "wallet_system_configs",
        sa.Column(
            "native_withdrawals_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("wallet_system_configs", "native_withdrawals_enabled")
