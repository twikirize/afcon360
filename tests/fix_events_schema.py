# fix_events_schema.py
"""Deprecated schema repair probe.

Schema changes belong in reviewed Alembic migrations and must not be applied
from a test or diagnostic script.
"""

def fix_schema():
    raise RuntimeError(
        'Do not repair event schema from a test script. Create and review an '
        'Alembic migration, then apply it through the operator workflow.'
    )

if __name__ == "__main__":
    fix_schema()
