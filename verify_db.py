import os
import re
from pathlib import Path


def fix_datetime_utcnow(file_path):
    """Replace datetime.utcnow() with datetime.now(timezone.utc)"""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Check if file uses datetime.utcnow
    if 'datetime.utcnow()' not in content:
        return False

    # Add timezone import if needed
    if 'from datetime import datetime' in content:
        if 'from datetime import timezone' not in content and 'datetime.timezone' not in content:
            content = content.replace(
                'from datetime import datetime',
                'from datetime import datetime, timezone'
            )
    elif 'import datetime' in content:
        if 'datetime.timezone' not in content:
            content = content.replace(
                'import datetime',
                'import datetime\nfrom datetime import timezone'
            )
    else:
        # Add timezone import
        content = 'from datetime import timezone\n' + content

    # Replace datetime.utcnow()
    content = re.sub(
        r'datetime\.utcnow\(\)',
        'datetime.now(timezone.utc)',
        content
    )

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)

    return True


# Fix all Python files
fixed_count = 0
for py_file in Path('app').rglob('*.py'):
    if fix_datetime_utcnow(py_file):
        print(f"Fixed: {py_file}")
        fixed_count += 1

print(f"\n✅ Fixed {fixed_count} files")