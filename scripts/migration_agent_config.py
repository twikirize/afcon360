# scripts/migration_agent_config.py
"""
Configuration for the AFCON360 automated migration agent.

These values are consumed by `scripts/create_migration.py` to keep the
Alembic migration tree linear (single head) and PostgreSQL-compatible.

The goal is to prevent the "multiple heads" problem that fragments the
migration history and forces manual `flask db merge` recovery later.
"""
# Keep revision IDs under 32 chars. PostgreSQL has a 63-byte identifier
# limit, but short timestamp-based IDs stay readable in logs and avoid
# edge cases when referenced in indexes/constraints.
MAX_REVISION_LENGTH = 32

# When multiple heads are detected, automatically merge them into one
# linear history instead of creating a new divergent branch.
AUTO_MERGE_HEADS = True

# Prefix used when generating auto-merge migration messages.
MERGE_MESSAGE_PREFIX = "auto_merge"

# After merging heads, automatically apply the merge with `flask db upgrade`.
# The merge only linearizes history (no schema change), so it is safe to
# apply. Set to False if you prefer to review/apply merges manually.
AUTO_UPGRADE_AFTER_MERGE = True
