"""Add explicit IANA timezones to accommodation properties and events.

Revision ID: 20261107130000
Revises: 20261107120000
Create Date: 2026-11-07
"""
from alembic import op
import sqlalchemy as sa


revision = "20261107130000"
down_revision = "20261107120000"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "accommodation_properties",
        sa.Column("timezone_name", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "events",
        sa.Column("timezone_name", sa.String(length=64), nullable=True),
    )

    # Populate precise property zones from stored coordinates where possible.
    # The fallback is intentionally limited to unambiguous country defaults.
    from app.utils.location_timezone import (
        timezone_for_coordinates,
        timezone_for_country,
        resolve_location_timezone,
    )
    connection = op.get_bind()
    properties = connection.execute(
        sa.text(
            "SELECT id, latitude, longitude, country "
            "FROM accommodation_properties"
        )
    ).mappings()
    for row in properties:
        try:
            zone = resolve_location_timezone(
                latitude=row["latitude"],
                longitude=row["longitude"],
                country=row["country"],
            )
        except ValueError:
            zone = None
        if zone:
            connection.execute(
                sa.text(
                    "UPDATE accommodation_properties "
                    "SET timezone_name = :zone WHERE id = :id"
                ),
                {"zone": zone, "id": row["id"]},
            )

    events = connection.execute(
        sa.text("SELECT id, country, event_metadata FROM events")
    ).mappings()
    for row in events:
        metadata = row["event_metadata"] or {}
        explicit = metadata.get("timezone_name") if isinstance(metadata, dict) else None
        zone = explicit or timezone_for_country(row["country"])
        if zone:
            # Validate before persistence. Invalid legacy metadata stays unset.
            try:
                from app.utils.time_policy import require_iana_timezone
                zone = require_iana_timezone(zone, field="event venue timezone").key
            except ValueError:
                zone = None
        if zone:
            connection.execute(
                sa.text(
                    "UPDATE events SET timezone_name = :zone WHERE id = :id"
                ),
                {"zone": zone, "id": row["id"]},
            )


def downgrade():
    op.drop_column("events", "timezone_name")
    op.drop_column("accommodation_properties", "timezone_name")
