#!/usr/bin/env python
"""
Seed all roles, permissions, and role-permission links.

Delegates to the canonical seed in app.auth.seed_roles (the same source
powering ``flask seed-all``), so every defined permission — including
``geo.view`` / ``geo.manage`` — and its role links are provisioned here.
Idempotent: safe to run repeatedly.

Run: python scripts/seed_roles.py
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from app.auth.seed_roles import seed_all


def main() -> None:
    app = create_app()
    with app.app_context():
        seed_all(verbose=True)


if __name__ == "__main__":
    main()