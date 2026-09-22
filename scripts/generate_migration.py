# scripts/generate_migration.py
"""
AFCON360 Migration Generator.

This is a thin wrapper around `flask db migrate` that ensures the
correct Alembic configuration is used. It does NOT modify env.py.

Usage:
    python scripts/generate_migration.py "description of change"

Workflow:
    1. Edit app/transport/models.py (or other model files)
    2. Run this script to generate the migration file
    3. Inspect the generated migration
    4. Run `flask db upgrade` to apply

For CHECK constraint changes only (not detected by flask db migrate):
    Use scripts/sync_check_constraints.py instead:
        python scripts/sync_check_constraints.py --accept-model-truth --message "desc"
    Then inspect the generated migration and run `flask db upgrade`.

Note: env.py uses compare_type=True which detects column/FK changes.
      CheckConstraint changes require sync_check_constraints.py
      because Alembic autogenerate cannot detect CHECK constraints.
"""
import argparse
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def generate_migration(message: str) -> None:
    """Generate a migration using flask db migrate."""
    cmd = ["flask", "db", "migrate", "-m", message]
    print(f"cmd: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT), text=True)
    if result.returncode != 0:
        print("Migration generation failed.")
        sys.exit(1)
    print("Migration generated. Review and run: flask db upgrade")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate Alembic migration"
    )
    parser.add_argument("message", nargs="?", default="auto-generated migration",
                        help="Migration message")
    args = parser.parse_args()
    generate_migration(args.message or "auto-generated migration")
