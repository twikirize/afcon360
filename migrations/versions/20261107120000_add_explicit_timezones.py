"""Add explicit IANA timezones to compliance jurisdictions and user profiles.

Revision ID: 20261107120000
Revises: 20261106181703
Create Date: 2026-11-07
"""
from alembic import op
import sqlalchemy as sa

revision = "20261107120000"
down_revision = "20261106181703"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "aml_jurisdiction_profiles",
        sa.Column("timezone_name", sa.String(length=64), nullable=True),
    )
    op.execute(
        """
        UPDATE aml_jurisdiction_profiles
        SET timezone_name = CASE country_code
            WHEN 'INT' THEN 'UTC'
            WHEN 'UG' THEN 'Africa/Kampala'
            WHEN 'KE' THEN 'Africa/Nairobi'
            WHEN 'TZ' THEN 'Africa/Dar_es_Salaam'
            WHEN 'ZM' THEN 'Africa/Lusaka'
            WHEN 'RW' THEN 'Africa/Kigali'
            WHEN 'NG' THEN 'Africa/Lagos'
            WHEN 'GH' THEN 'Africa/Accra'
            WHEN 'ZA' THEN 'Africa/Johannesburg'
            WHEN 'GB' THEN 'Europe/London'
            WHEN 'US' THEN 'America/New_York'
            WHEN 'EU' THEN 'Europe/Brussels'
            ELSE 'UTC'
        END
        WHERE timezone_name IS NULL
        """
    )
    op.alter_column(
        "aml_jurisdiction_profiles",
        "timezone_name",
        existing_type=sa.String(length=64),
        nullable=False,
    )
    op.add_column(
        "user_profiles",
        sa.Column("preferred_timezone", sa.String(length=64), nullable=True),
    )


def downgrade():
    op.drop_column("user_profiles", "preferred_timezone")
    op.drop_column("aml_jurisdiction_profiles", "timezone_name")
