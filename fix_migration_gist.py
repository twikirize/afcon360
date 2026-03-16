# fix_migration_gist.py
import re

print("Fixing GiST indexes in migration file...")

migration_file = 'migrations/versions/056c90f475de_add_transport_module_tables.py'

with open(migration_file, 'r', encoding='utf-8') as f:
    content = f.read()

# Find and comment out ALL GiST indexes
gist_indexes = [
    # Look for any create_index with gist
    r"batch_op\.create_index\([^)]*postgresql_using='gist'[^)]*\)",
    # Also look for specific GiST indexes
    r"batch_op\.create_index\('idx_.*gist.*\)",
    r"batch_op\.create_index\('ix_.*gist.*\)",
]

for pattern in gist_indexes:
    matches = re.findall(pattern, content, re.IGNORECASE)
    for match in matches:
        # Comment it out if not already commented
        if not match.strip().startswith('#'):
            content = content.replace(match, f"# {match}")
            print(f"✅ Commented out: {match[:80]}...")

# Also check for specific problematic indexes mentioned in error
specific_indexes = [
    "idx_transport_scheduled_routes_path_coordinates",
    "idx_transport_bookings_pickup_point",
    "idx_transport_bookings_dropoff_point",
    "ix_booking_pickup",
    "ix_booking_dropoff",
    "idx_transport_vehicles_current_location",
    "ix_vehicle_location"
]

for index_name in specific_indexes:
    if index_name in content:
        # Find the line with this index
        lines = content.split('\n')
        for i, line in enumerate(lines):
            if index_name in line and 'batch_op.create_index' in line and not line.strip().startswith('#'):
                lines[i] = f"# {line}"
                print(f"✅ Commented out index: {index_name}")
        content = '\n'.join(lines)

# Write back
with open(migration_file, 'w', encoding='utf-8') as f:
    f.write(content)

print("\n✅ Migration file fixed. Now run: flask db upgrade")