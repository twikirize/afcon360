"""
Root-level pytest configuration.

This project contains tests only inside the tests/ directory.
We ignore everything else to prevent collection of .venv and other
non-test files.
"""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
os.environ["FLASK_ENV"] = "testing"


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers",
        "no_database: source/configuration contract check that does not access the database",
    )


def pytest_ignore_collect(collection_path, config):
    """
    Ignore any path that is not inside the 'tests/' directory.
    This prevents pytest from scanning .venv, root files, etc.
    """
    path = Path(collection_path)
    try:
        rel_path = path.resolve().relative_to(PROJECT_ROOT)
    except ValueError:
        # Path is outside the project root – ignore
        return True

    # Only allow collection from the 'tests/' directory
    if rel_path.parts[0] != "tests":
        return True

    # Also ignore non-Python files (just in case)
    if path.is_file() and path.suffix.lower() != ".py":
        return True

    return False