"""Retired legacy cleanup/bootstrap script.

This file intentionally performs no database operations. Test-database
provisioning and row cleanup are owned by the migration workflow and managed
pytest isolation fixtures. Never run ad-hoc cleanup against shared or
production databases.
"""

if __name__ == "__main__":
    raise SystemExit(
        "This legacy script is retired. Use the approved test-database "
        "workflow and pytest isolation fixtures."
    )
