# app/identity/services/organisation_slug.py
"""
Organisation slug generation.

The organisation slug is a browser-facing routing identifier only. It is never
an authorization credential and never replaces the internal ``id`` or the
stable public ``org_id``. See the approved "Organisation Browser Identity &
Slug Policy".

Slug rules (authorized):
- derived from the first two MEANINGFUL words of ``legal_name``;
- lowercase, joined with ``_``, punctuation removed;
- non-distinctive administrative words are excluded;
- globally unique (``-2``, ``-3``, ... colliders);
- deterministic fallback to the existing ``org_id`` when no meaningful words
  exist;
- immutable once assigned — a change of ``legal_name`` must NOT change the
  collected slug.
"""
from __future__ import annotations

import re

# Words excluded when selecting the two "meaningful" words of the name.
STOPWORDS = frozenset({
    "the",
    "of",
    "and",
    "for",
    "ltd",
    "limited",
    "company",
    "co",
    "corporation",
})

_TOKEN_RE = re.compile(r"[\w']+", re.UNICODE)


def slugify_org_name(legal_name) -> str:
    """Return the base slug candidate from ``legal_name`` (may be empty).

    The first two non-stopword word tokens are taken, lowercased and joined
    with ``_``. ``""`` is returned when no meaningful words remain so callers
    can fall back to the organisation's stable ``org_id``.
    """
    if not legal_name:
        return ""
    tokens = [token.lower() for token in _TOKEN_RE.findall(str(legal_name))]
    tokens = [token for token in tokens if token and token not in STOPWORDS]
    meaningful = tokens[:2]
    if not meaningful:
        return ""
    return "_".join(meaningful)


def _fallback_slug(org) -> str:
    """Deterministic, URL-safe last-resort slug derived from ``org_id``."""
    base = re.sub(r"[^a-z0-9]+", "_", (org.org_id or "").strip().lower()).strip("_")
    return base or "organisation"


def _taken_slugs(base: str) -> set[str]:
    """Existing slugs that would collide with ``base`` (base itself + base-N)."""
    from app.identity.models.organisation import Organisation

    rows = (
        Organisation.query.with_entities(Organisation.slug)
        .filter(
            (Organisation.slug == base) | (Organisation.slug.like(f"{base}-%"))
        )
        .all()
    )
    return {row[0] for row in rows}


def ensure_unique_slug(org) -> str:
    """Assign a globally unique slug to ``org`` (mutates ``org.slug``).

    The database unique constraint remains the final integrity boundary; this
    helper only performs the application-level collision resolution required
    to generate deterministic numeric suffis such as ``miracle_center-2``.
    """
    if getattr(org, "slug", None):
        return org.slug

    base = slugify_org_name(getattr(org, "legal_name", None)) or _fallback_slug(org)
    taken = _taken_slugs(base)

    candidate = base
    if candidate in taken:
        n = 2
        while f"{base}-{n}" in taken:
            n += 1
        candidate = f"{base}-{n}"

    org.slug = candidate
    return candidate