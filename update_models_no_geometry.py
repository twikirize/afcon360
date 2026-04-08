# update_models_no_geometry.py
import os
import re


def update_models_file():
    """Update models.py to remove Geometry columns"""

    models_file = 'app/transport/models.py'

    if not os.path.exists(models_file):
        print(f"❌ Models file not found: {models_file}")
        return False

    print(f"📝 Updating {models_file}...")

    with open(models_file, 'r', encoding='utf-8') as f:
        content = f.read()

    changes_made = []

    # 1. Remove geoalchemy2 import
    if 'from geoalchemy2 import Geometry' in content:
        content = content.replace('from geoalchemy2 import Geometry',
                                  '# from geoalchemy2 import Geometry  # Removed: PostGIS not installed')
        changes_made.append("Commented out geoalchemy2 import")

    # 2. Make sure JSONB is imported
    if 'from sqlalchemy.dialects.postgresql import JSONB' not in content:
        # Add it after SQLAlchemy imports
        import_section = """from sqlalchemy import (
    Index, UniqueConstraint, CheckConstraint, text, Enum as SQLEnum,
    ForeignKeyConstraint, event, DDL
)
from sqlalchemy.dialects.postgresql import JSONB, UUID"""

        if import_section in content:
            # Already has JSONB import
            pass
        else:
            # Find where postgresql imports are
            if 'from sqlalchemy.dialects.postgresql import' in content:
                # Add JSONB to existing import
                content = content.replace(
                    'from sqlalchemy.dialects.postgresql import UUID',
                    'from sqlalchemy.dialects.postgresql import JSONB, UUID'
                )
                changes_made.append("Added JSONB import")

    # 3. Replace Geometry columns with JSONB
    geometry_patterns = [
        # Vehicle.current_location
        (r"current_location = db\.Column\(Geometry\(geometry_type=\"POINT\", srid=4326\)\)",
         "current_location = db.Column(JSONB)"),

        # Booking.pickup_point
        (r"pickup_point = db\.Column\(Geometry\(geometry_type='POINT', srid=4326\)\)",
         "pickup_point = db.Column(JSONB)"),

        # Booking.dropoff_point
        (r"dropoff_point = db\.Column\(Geometry\('POINT', srid=4326\)\)",
         "dropoff_point = db.Column(JSONB)"),

        # ScheduledRoute.path_coordinates
        (r"path_coordinates = db\.Column\(Geometry\('LINESTRING', srid=4326\)\)",
         "path_coordinates = db.Column(JSONB)"),
    ]

    for pattern, replacement in geometry_patterns:
        if re.search(pattern, content):
            content = re.sub(pattern, replacement, content)
            changes_made.append(f"Replaced Geometry with JSONB: {pattern[:50]}...")

    # 4. Also fix any other Geometry references
    if 'Geometry(' in content:
        # Replace any remaining Geometry(...) with JSONB
        content = re.sub(
            r"Geometry\([^)]+\)",
            "JSONB",
            content
        )
        changes_made.append("Replaced remaining Geometry references")

    # Write back
    with open(models_file, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"✅ Made {len(changes_made)} changes:")
    for change in changes_made:
        print(f"  - {change}")

    return True


def create_migration_script():
    """Create a script to generate and run migration"""

    script = """#!/usr/bin/env python
# generate_migration.py
import subprocess
import sys

print("Generating migration for JSONB instead of Geometry...")

# Generate migration
result = subprocess.run(
    [sys.executable, "-m", "flask", "db", "migrate", "-m", "Replace geometry columns with JSONB (PostGIS not available)"],
    capture_output=True,
    text=True
)

if result.returncode == 0:
    print("✅ Migration generated")
    print(result.stdout)

    # Apply migration
    print("\\nApplying migration...")
    result2 = subprocess.run(
        [sys.executable, "-m", "flask", "db", "upgrade"],
        capture_output=True,
        text=True
    )

    if result2.returncode == 0:
        print("✅ Migration applied successfully!")
        print("\\nYour transport module is now ready without PostGIS.")
        print("Location data will be stored as JSONB instead of Geometry.")
    else:
        print("❌ Failed to apply migration:")
        print(result2.stderr)

else:
    print("❌ Failed to generate migration:")
    print(result.stderr)
"""

    with open('tests/generate_migration.py', 'w') as f:
        f.write(script)

    print("✅ Created migration script: generate_migration.py")
    return True


def main():
    print("=" * 60)
    print("REMOVING GEOMETRY COLUMNS (PostGIS not available)")
    print("=" * 60)

    print("\nStep 1: Updating models to use JSONB instead of Geometry...")
    if update_models_file():
        print("\nStep 2: Creating migration script...")
        create_migration_script()

        print("\n" + "=" * 60)
        print("NEXT STEPS:")
        print("=" * 60)
        print("1. Review the changes in app/transport/models.py")
        print("2. Run: python generate_migration.py")
        print("3. Your transport module will work with JSONB location storage")
        print("\\nNote: You can install PostGIS later and convert JSONB → Geometry")
    else:
        print("❌ Failed to update models")


if __name__ == "__main__":
    main()
