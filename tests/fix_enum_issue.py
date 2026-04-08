# fix_enum_issue.py
import os
import re

print("Fixing enum case issues in migration file...")

migration_file = 'migrations/versions/056c90f475de_add_transport_module_tables.py'

with open(migration_file, 'r', encoding='utf-8') as f:
    content = f.read()

# Fix 1: Change lowercase enum values to uppercase in WHERE clauses
# Pattern: WHERE verification_tier IN ('platform_verified', 'event_certified')
lowercase_pattern = r"WHERE verification_tier IN \('platform_verified', 'event_certified'\)"
uppercase_replacement = "WHERE verification_tier IN ('PLATFORM_VERIFIED', 'EVENT_CERTIFIED')"

if lowercase_pattern in content:
    content = content.replace(lowercase_pattern, uppercase_replacement)
    print("✅ Fixed verification_tier enum values (lowercase → uppercase)")

# Fix 2: Also fix any other enum references
# The enum was created with uppercase values in Python:
# PENDING, BASIC_VERIFIED, PLATFORM_VERIFIED, EVENT_CERTIFIED

# Check for other lowercase enum references
enum_fixes = [
    ("'pending'", "'PENDING'"),
    ("'basic_verified'", "'BASIC_VERIFIED'"),
    ("'platform_verified'", "'PLATFORM_VERIFIED'"),
    ("'event_certified'", "'EVENT_CERTIFIED'"),
]

for lowercase, uppercase in enum_fixes:
    # Only replace in SQL context (not in Python comments/strings)
    # Look for patterns like: WHERE column IN ('value1', 'value2')
    pattern = rf"IN \([^)]*{lowercase}[^)]*\)"
    if re.search(pattern, content):
        # Replace all occurrences
        content = re.sub(lowercase, uppercase, content)
        print(f"✅ Fixed {lowercase} → {uppercase}")

# Fix 3: Also check other enums in the migration
# Like compliancestatus, bookingstatus, etc.
other_enums = [
    ("'pending_review'", "'PENDING_REVIEW'"),
    ("'under_review'", "'UNDER_REVIEW'"),
    ("'approved'", "'APPROVED'"),
    ("'suspended'", "'SUSPENDED'"),
    ("'revoked'", "'REVOKED'"),
    ("'blacklisted'", "'BLACKLISTED'"),
]

for lowercase, uppercase in other_enums:
    if lowercase in content:
        # Be careful - only replace in SQL context
        lines = content.split('\n')
        for i, line in enumerate(lines):
            if lowercase in line and ("WHERE" in line or "IN (" in line or "CHECK" in line):
                lines[i] = lines[i].replace(lowercase, uppercase)
                print(f"✅ Fixed {lowercase} → {uppercase} in line {i+1}")
        content = '\n'.join(lines)

# Write back
with open(migration_file, 'w', encoding='utf-8') as f:
    f.write(content)

print("\n✅ Enum case issues fixed")
print("\nNow run: flask db upgrade")
