# scripts/create_migration.py
"""
Safe migration creation script for the AFCON360 migration agent.

Prevents the "multiple heads" problem by:
  1. Checking for multiple Alembic heads before creating a new revision.
  2. Auto-merging heads when detected (configurable via migration_agent_config).
  3. Creating revisions with short, timestamp-based IDs (< 32 chars) to stay
     within PostgreSQL identifier limits.

Usage:
    python scripts/create_migration.py "add system_configs table"
"""
import os
import subprocess
import sys
from datetime import datetime

# Ensure the script's own directory is importable so the config can be
# loaded regardless of the current working directory.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from migration_agent_config import (  # noqa: E402
    MAX_REVISION_LENGTH,
    AUTO_MERGE_HEADS,
    MERGE_MESSAGE_PREFIX,
    AUTO_UPGRADE_AFTER_MERGE,
)


def _run(cmd, check=True):
    """Run a flask/alembic command, streaming output, returning CompletedProcess."""
    print(f"▶ {' '.join(cmd)}")
    return subprocess.run(cmd, check=check, text=True)


def _get_heads():
    """Return a list of current Alembic head revision IDs (excluding blanks)."""
    result = subprocess.run(
        ["flask", "db", "heads"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print("❌ Failed to read alembic heads:")
        print(result.stderr)
        sys.exit(1)
    # Output may contain header lines / blank lines — keep only non-empty tokens.
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def create_migration(message):
    """Create a migration with a short revision ID, merging heads if needed."""

    heads = _get_heads()
    # print(f"ℹ️ Current heads: {heads}")

    if len(heads) > 1:
        if not AUTO_MERGE_HEADS:
            print(
                "⚠️ Multiple heads detected but AUTO_MERGE_HEADS is False. "
                "Aborting to avoid creating a new divergent branch."
            )
            sys.exit(1)

        print(f"⚠️ Multiple heads ({len(heads)}) detected. Merging first...")
        merge_msg = f"{MERGE_MESSAGE_PREFIX}_{datetime.now().strftime('%Y%m%d')}"
        _run(["flask", "db", "merge", "heads", "-m", merge_msg])

        if AUTO_UPGRADE_AFTER_MERGE:
            _run(["flask", "db", "upgrade"])
        else:
            print("ℹ️ AUTO_UPGRADE_AFTER_MERGE is False — run `flask db upgrade` manually.")

    # Create the migration with a short, timestamp-based revision ID.
    short_id = datetime.now().strftime("%Y%m%d_%H%M")
    if len(short_id) > MAX_REVISION_LENGTH:
        short_id = short_id[-MAX_REVISION_LENGTH:]

    _run(["flask", "db", "revision", "-m", message, "--rev-id", short_id])
    print(f"✅ Migration created: {short_id}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('Usage: python scripts/create_migration.py "migration message"')
        sys.exit(1)
    create_migration(sys.argv[1])
