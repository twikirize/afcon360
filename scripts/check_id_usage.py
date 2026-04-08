#!/usr/bin/env python
"""
Pre-commit hook to prevent ID mixing mistakes
Run this before every commit to catch errors early
"""

import re
import sys
from pathlib import Path

FORBIDDEN_PATTERNS = [
    # Direct session user_id access
    (r"session\['user_id'\]", "Use get_current_internal_id() or get_current_public_id() instead"),
    (r"session\.get\('user_id'\)", "Use get_current_internal_id() or get_current_public_id() instead"),

    # Using UUID for foreign key assignment
    (r"\.owner_id\s*=\s*.*\.user_id", "Foreign keys must use .id (BIGINT), not .user_id (UUID)"),
    (r"\.user_id\s*=\s*.*\.user_id", "Foreign keys must use .id (BIGINT), not .user_id (UUID)"),

    # Direct UUID to FK assignment
    (r"\.owner_id\s*=\s*.*\.uuid", "Foreign keys must use .id (BIGINT)"),
    (r"\.user_id\s*=\s*.*\.uuid", "Foreign keys must use .id (BIGINT)"),

    # Using internal ID in URLs
    (r"url_for\(.*,\s*.*_id\s*=\s*.*\.id\)", "URLs must use .user_id (UUID), not .id"),

    # Wrong FK type hints
    (r"db\.ForeignKey\(['\"]users\.user_id['\"]\)", "Foreign keys must reference users.id, not users.user_id"),
]

def check_file(filepath):
    """Check a single file for forbidden patterns"""
    errors = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            lines = content.split('\n')

            for pattern, message in FORBIDDEN_PATTERNS:
                for i, line in enumerate(lines, 1):
                    if re.search(pattern, line):
                        errors.append(f"  {filepath}:{i}: {message}")
                        errors.append(f"    Line: {line.strip()}")
    except Exception as e:
        # Skip binary files or files that can't be read
        pass

    return errors

def main():
    """Main entry point"""
    # Look for files to check in command line args, otherwise default to app/ and tools/
    files_to_check = []
    if len(sys.argv) > 1:
        for arg in sys.argv[1:]:
            p = Path(arg)
            if p.is_file():
                files_to_check.append(p)
            elif p.is_dir():
                files_to_check.extend(list(p.rglob('*.py')))

    if not files_to_check:
        # Default scan if no paths provided
        project_root = Path(__file__).parent.parent
        app_dir = project_root / 'app'
        if app_dir.exists():
            files_to_check.extend(list(app_dir.rglob('*.py')))

        tools_dir = project_root / 'tools'
        if tools_dir.exists():
            files_to_check.extend(list(tools_dir.rglob('*.py')))

        # Also check app/tools if it exists
        app_tools_dir = app_dir / 'tools'
        if app_tools_dir.exists() and app_tools_dir not in files_to_check:
            files_to_check.extend(list(app_tools_dir.rglob('*.py')))

    all_errors = []
    for filepath in files_to_check:
        # Convert to string for checking path exclusions
        path_str = str(filepath)
        if filepath.suffix == '.py' and 'migrations' not in path_str and '.venv' not in path_str:
            errors = check_file(filepath)
            all_errors.extend(errors)

    if all_errors:
        print("\n" + "="*70)
        print("❌ ID SYSTEM VIOLATIONS DETECTED")
        print("="*70)
        for error in all_errors:
            print(error)
        print("\n🔧 Fix these before committing:")
        print("  - Use .id (BIGINT) for database foreign keys")
        print("  - Use .user_id (UUID) for URLs and public APIs")
        print("  - Use get_current_internal_id() instead of session['user_id']")
        sys.exit(1)

    print("✅ No ID system violations found")
    sys.exit(0)

if __name__ == '__main__':
    main()
