"""
Backfill legacy accommodation_properties rows to the new structure/occupancy split.

Why this exists:
- ``flask db migrate`` (Alembic autogenerate) does NOT detect CHECK-constraint
  changes, so the old mixed ``ck_property_type_valid`` (occupancy + legacy values)
  would stay active and reject the structure values written by this script.
- This script is only needed for non-empty databases with legacy rows
  (occupancy values in ``property_type``). Fresh databases built from models
  already have ``listing_type`` and the server_defaults applied.

Order (part of the sanctioned three-step flow):
    1. flask db migrate -m "..."  -> adds listing_type column
    2. this script                -> drops legacy mixed constraint + backfills rows
    3. scripts/sync_check_constraints.py --accept-model-truth  -> adds the two
       new CHECK constraints (ADD-only, safe because rows now hold structure
       values)

This script NEVER edits a migration file.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import create_app
from app.extensions import db
from sqlalchemy import text


def main():
    app = create_app()
    with app.app_context():
        with db.engine.begin() as conn:
            print("=== BEFORE ===")
            rows = conn.execute(
                text(
                    "SELECT id, property_type, listing_type "
                    "FROM accommodation_properties ORDER BY id"
                )
            ).fetchall()
            for r in rows:
                print(r)

            conn.execute(
                text(
                    "ALTER TABLE accommodation_properties "
                    "DROP CONSTRAINT IF EXISTS ck_property_type_valid"
                )
            )

            updated = 0

            result = conn.execute(
                text(
                    "UPDATE accommodation_properties "
                    "SET listing_type = 'private_room', property_type = 'hotel' "
                    "WHERE property_type = 'hotel_room'"
                )
            )
            updated += result.rowcount

            result = conn.execute(
                text(
                    "UPDATE accommodation_properties "
                    "SET listing_type = 'entire_place', property_type = 'house' "
                    "WHERE property_type = 'community_host'"
                )
            )
            updated += result.rowcount

            result = conn.execute(
                text(
                    "UPDATE accommodation_properties "
                    "SET listing_type = property_type, property_type = 'house' "
                    "WHERE property_type IN "
                    "('entire_place', 'private_room', 'shared_room')"
                )
            )
            updated += result.rowcount

            print("=== UPDATED ROWS:", updated, "===")
            print("=== AFTER ===")
            rows = conn.execute(
                text(
                    "SELECT id, property_type, listing_type "
                    "FROM accommodation_properties ORDER BY id"
                )
            ).fetchall()
            for r in rows:
                print(r)


if __name__ == "__main__":
    main()