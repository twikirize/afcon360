"""Slug generation utilities for the accommodation module."""

import re
from sqlalchemy import inspect

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    """Generate a lowercase slug safe for URLs."""
    base = _SLUG_RE.sub("-", text.lower()).strip("-")
    return base or "listing"


def ensure_unique_slug(base_slug: str, session, model_class) -> str:
    """Ensure slug uniqueness by appending numeric suffixes when needed.

    Args:
        base_slug: The initial slug value.
        session: SQLAlchemy session to query for conflicts.
        model_class: SQLAlchemy model class with a `slug` column.

    Returns:
        A unique slug string.
    """
    slug = base_slug
    suffix = 2
    while session.query(model_class).filter_by(slug=slug).first() is not None:
        slug = f"{base_slug}-{suffix}"
        suffix += 1
    return slug
