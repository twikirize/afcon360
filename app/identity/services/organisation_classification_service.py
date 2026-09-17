# app/identity/services/organisation_classification_service.py
"""
Organisation classification service — database-backed organisation
categories / types with constant fallback.

The onboarding chooser (and any further consumer of the organisation
classification vocabulary) reads categories and their type options from these
lookup tables. When the tables have not been created (pre-migration) or are
empty (pre-seed / test bootstrap), the functions fall back to the canonical
frozen constants in ``app.identity.catalog_data`` so the UI never renders with
zero options and the server-side category derivation always works.

Contract:
  * the client submits ONLY the organisation type code;
  * the category is derived server-side via ``category_for``;
  * validation of a submitted type code happens against the frozen enum /
    catalogue (``validate_type``); and
  * ``assert_parity`` proves the catalogue 1:1 matches the ``OrganizationType``
    enum (39/39) — see the frozen contract in ``catalog_data``.
"""

from __future__ import annotations

import logging
from typing import List

from sqlalchemy.exc import IntegrityError, ProgrammingError

from app.extensions import db
from app.identity.catalog_data import (
    ORGANISATION_CATEGORIES,
    ORGANISATION_TYPE_CATALOG,
)
from app.identity.models.organisation_catalogues import (
    OrganisationCategory,
    OrganisationTypeCatalogue,
)

logger = logging.getLogger(__name__)


def _safe_query(query):
    """Execute a query, catching ProgrammingError (missing table) → returns []."""
    try:
        return query.all()
    except ProgrammingError:
        # Table doesn't exist yet (pre-migration) — rollback the aborted
        # transaction and fall back to constants.
        db.session.rollback()
        return []


def _ordered_active(model):
    return _safe_query(
        db.session.query(model)
        .filter(model.is_active.is_(True))
        .order_by(model.sort_order, model.code)
    )


def _fallback_groups() -> List[dict]:
    """Category groups built from the frozen constants (safe-fail bootstrap)."""
    return [
        {
            "code": cat_code,
            "label": cat_label,
            "types": [
                {"code": type_code, "label": meta["label"]}
                for type_code, meta in ORGANISATION_TYPE_CATALOG.items()
                if meta["category_code"] == cat_code
            ],
        }
        for cat_code, cat_label in ORGANISATION_CATEGORIES.items()
    ]


def category_groups() -> List[dict]:
    """Return the ordered category groups for the onboarding chooser.

    Each group: ``{"code", "label", "types": [{"code", "label"}, ...]}``.
    DB-first; falls back to the frozen constants when the tables are missing
    (pre-migration) or empty (unseeded).
    """
    categories = _ordered_active(OrganisationCategory)
    types = _ordered_active(OrganisationTypeCatalogue)
    if not categories or not types:
        return _fallback_groups()

    groups = []
    for cat in categories:
        groups.append(
            {
                "code": cat.code,
                "label": cat.label,
                "types": [
                    {"code": t.code, "label": t.label}
                    for t in types
                    if t.category_code == cat.code
                ],
            }
        )
    return groups


def type_options() -> List[dict]:
    """Return every active type option as ``{"code", "label", "category_code"}``.

    DB-first; falls back to the frozen catalogue when unseeded.
    """
    types = _ordered_active(OrganisationTypeCatalogue)
    if not types:
        return [
            {
                "code": code,
                "label": meta["label"],
                "category_code": meta["category_code"],
            }
            for code, meta in ORGANISATION_TYPE_CATALOG.items()
        ]
    return [
        {"code": t.code, "label": t.label, "category_code": t.category_code}
        for t in types
    ]


def category_for(org_type_code: str) -> str:
    """Derive the category code for a canonical organisation type code.

    Server-side derivation: users never submit a category; it is always
    resolved from the (frozen) type → category mapping.
    """
    meta = ORGANISATION_TYPE_CATALOG.get(str(org_type_code or "").strip())
    if meta is None:
        raise ValueError(f"Unknown organisation type code: {org_type_code!r}")
    return meta["category_code"]


def validate_type(org_type_code: str) -> str:
    """Return the canonical type code if valid, else raise ValueError."""
    code = str(org_type_code or "").strip()
    if code not in ORGANISATION_TYPE_CATALOG:
        raise ValueError("Please select a valid organisation type.")
    return code


def label_for(org_type_code) -> str:
    """Human label for a canonical type code ('' when the code is unknown).

    DB-first for the label text; falls back to the frozen catalogue.
    Used for read-only display (never for writes).
    """
    code = str(org_type_code or "").strip()
    if not code:
        return ""
    types = _ordered_active(OrganisationTypeCatalogue)
    if types:
        for t in types:
            if t.code == code:
                return t.label
    meta = ORGANISATION_TYPE_CATALOG.get(code)
    return meta["label"] if meta else ""


def assert_parity() -> None:
    """Assert the catalogue matches the frozen enum 1:1 (39/39).

    Raises AssertionError on any drift (missing / extra / renamed code).
    """
    from app.identity.models.organization_types import OrganizationType

    enum_values = {m.value for m in OrganizationType}
    catalogue_values = set(ORGANISATION_TYPE_CATALOG)
    if enum_values != catalogue_values:
        raise AssertionError(
            "Organisation classification catalogue != OrganizationType enum: "
            f"enum-only={sorted(enum_values - catalogue_values)} "
            f"catalogue-only={sorted(catalogue_values - enum_values)}"
        )


def seed_organisation_catalogues(*, force: bool = False, verbose: bool = False) -> bool:
    """Idempotently materialise the frozen classification vocabulary into the
    DB lookup tables (``organisation_categories`` + ``organisation_types``).

    * ``force=False`` (startup auto-seed): fast path — when
      ``organisation_types`` already contains any rows the catalogue is
      considered seeded and nothing is written (one cheap COUNT query). If
      the tables have not been created yet (pre-migration) it skips silently
      instead of breaking boot.
    * ``force=True`` (operator re-sync, ``scripts/seed_organisation_catalogues.py``):
      upsert every category/type, updating labels/sort_order/flags to match
      the frozen catalogue.

    Returns True when rows were written this call. Never raises for
    pre-migration, partial, or concurrent-seed conditions.
    """

    try:
        already_seeded = db.session.query(OrganisationTypeCatalogue).count() > 0
    except ProgrammingError:
        # Tables not created yet (pre-migration) — nothing to seed.
        db.session.rollback()
        return False

    if already_seeded and not force:
        return False

    def _upsert(model, code_col, code, **fields):
        row = db.session.query(model).filter(code_col == code).first()
        if row is None:
            db.session.add(model(code=code, **fields))
            return
        changed = False
        for key, value in fields.items():
            if getattr(row, key) != value:
                setattr(row, key, value)
                changed = True
        if changed:
            db.session.add(row)

    for sort_order, (code, label) in enumerate(ORGANISATION_CATEGORIES.items()):
        _upsert(
            OrganisationCategory,
            OrganisationCategory.code,
            code,
            label=label,
            sort_order=sort_order,
            is_active=True,
        )
    for sort_order, (code, meta) in enumerate(ORGANISATION_TYPE_CATALOG.items()):
        _upsert(
            OrganisationTypeCatalogue,
            OrganisationTypeCatalogue.code,
            code,
            label=meta["label"],
            category_code=meta["category_code"],
            sort_order=sort_order,
            is_active=True,
        )

    try:
        db.session.commit()
    except IntegrityError:
        # A concurrent boot seeded first — treat as success.
        db.session.rollback()
        return False

    if verbose:
        logger.info("Organisation classification catalogues seeded.")
    return True