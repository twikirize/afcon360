# verify_fix.py
print("Checking migration file after fix...")

with open('migrations/versions/056c90f475de_add_transport_module_tables.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Check if Geometry still exists
if 'Geometry(' in content:
    print("❌ Geometry still found in migration file")
    # Show lines with Geometry
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if 'Geometry(' in line:
            print(f"  Line {i+1}: {line.strip()[:100]}...")
else:
    print("✅ No Geometry found - good!")

# Check for JSONB
if 'JSONB' in content:
    print("✅ JSONB found in migration file")
else:
    print("❌ JSONB not found")

print("\nTrying to apply migration...")
import subprocess
result = subprocess.run(['flask', 'db', 'upgrade'], capture_output=True, text=True)

if result.returncode == 0:
    print("✅ Migration successful!")
    print(result.stdout[:500])  # Show first 500 chars
else:
    print("❌ Migration failed!")
    print("Error:", result.stderr[:500])  # Show first 500 chars of error