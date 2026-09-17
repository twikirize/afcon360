# scripts/seed_organisation_catalogues.py
"""
Seed / re-sync the organisation classification catalog lookup tables.

The tables are auto-seeded once at app startup when empty (see
``organisation_classification_service.seed_organisation_catalogues``).
This script is for operators who want a forced re-sync (e.g. after the
frozen catalogue or its labels change):

    python scripts/seed_organisation_catalogues.py

Idempotent: safe to re-run; upserts all categories/types so the DB matches
the frozen catalogue exactly.
"""

import sys, os
sys.path.insert(0, os.getcwd())

from app import create_app
from app.identity.services.organisation_classification_service import (
    seed_organisation_catalogues,
)


def main():
    app = create_app()
    with app.app_context():
        seed_organisation_catalogues(force=True, verbose=True)


if __name__ == "__main__":
    main()