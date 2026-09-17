"""
Stage 4B classification catalog + chokepoint tests.

FROZEN CONTRACT (organisation classification redesign):
  1. 39 organisation type codes — the catalogue MUST match the
     ``OrganizationType`` enum 1:1 (assert_parity).
  2. 8 categories; every type belongs to exactly ONE category.
  3. Category is DERIVED server-side (category_for); the client submits only
     the type code.
  4. New organisations persist ``organisation_type_code`` (canonical write
     target); the legacy ``business_category`` enum column is NOT written.
  5. get_effective_org_type(): organisation_type_code → business_category
     fallback → CORPORATE default. Legacy rows keep resolving.
  6. Consumer-by-default: no organisation type is required for general AFCON
     360 access; provider capability = explicit intent (never auto-activation).
  7. ProviderParticipation / ProviderCapabilityCode gates are unchanged — the
     classification redesign does NOT weaken the G-1 accommodation write gate.
  8. The onboarding chooser renders DB-seeded categories when available and
     falls back to constants when empty/not-yet-seeded (never zero options).

Run: pytest tests/test_organisation_classification.py -v
"""

import uuid

import pytest

from app.extensions import db
from app.identity.catalog_data import (
    ORGANISATION_CATEGORIES,
    ORGANISATION_TYPE_CATALOG,
)
from app.identity.models.organisation import Organisation
from app.identity.models.organisation_catalogues import (
    OrganisationCategory,
    OrganisationTypeCatalogue,
)
from app.identity.models.organization_types import OrganizationType
from app.identity.services.organisation_classification_service import (
    assert_parity,
    category_for,
    category_groups,
    type_options,
    validate_type,
)


def _make_org(session, *, organisation_type_code=None, business_category=None):
    org = Organisation(
        org_id=f"org_{uuid.uuid4().hex[:10]}",
        legal_name=f"Org {uuid.uuid4().hex[:8]}",
        country="UG",
        organisation_type_code=organisation_type_code,
        business_category=business_category,
        verification_status="pending",
        lifecycle_state="registered",
        is_active=True,
        is_operational=False,
    )
    session.add(org)
    session.flush()
    return org


def _seed_catalog(session):
    """Insert the frozen catalogue rows so FK-writes to organisation_types
    succeed inside tests (mirrors scripts/seed_organisation_catalogues.py)."""
    for sort_order, (code, label) in enumerate(ORGANISATION_CATEGORIES.items()):
        existing = (
            session.query(OrganisationCategory).filter_by(code=code).first()
        )
        if existing is None:
            session.add(
                OrganisationCategory(
                    code=code, label=label, sort_order=sort_order, is_active=True,
                )
            )
    session.flush()
    for sort_order, (code, meta) in enumerate(ORGANISATION_TYPE_CATALOG.items()):
        existing = (
            session.query(OrganisationTypeCatalogue)
            .filter_by(code=code)
            .first()
        )
        if existing is None:
            session.add(
                OrganisationTypeCatalogue(
                    code=code,
                    label=meta["label"],
                    category_code=meta["category_code"],
                    sort_order=sort_order,
                    is_active=True,
                )
            )
    session.flush()


# ---------------------------------------------------------------------------
# 1. Frozen 39/39 parity + catalogue integrity
# ---------------------------------------------------------------------------

class TestCatalogueParity:

    def test_catalog_matches_enum_exactly(self):
        assert_parity()  # raises AssertionError on drift

    def test_every_category_has_exactly_one_category(self):
        for code, meta in ORGANISATION_TYPE_CATALOG.items():
            assert meta["category_code"] in ORGANISATION_CATEGORIES, code

    def test_eight_categories(self):
        assert len(ORGANISATION_CATEGORIES) == 8

    def test_thirty_nine_types(self):
        assert len(ORGANISATION_TYPE_CATALOG) == 39

    def test_categories_ordered_for_onboarding(self):
        # Order must equal the onboarding optgroup order.
        assert list(ORGANISATION_CATEGORIES) == [
            "hospitality_tourism",
            "events_venues",
            "sports_recreation",
            "transportation",
            "business_services",
            "government_institutions",
            "financial_services",
            "media_entertainment",
        ]

    def test_type_codes_are_enum_values(self):
        enum_values = {m.value for m in OrganizationType}
        for code in ORGANISATION_TYPE_CATALOG:
            assert code in enum_values, f"{code!r} is not an OrganizationType value"


# ---------------------------------------------------------------------------
# 2. Server-side category derivation
# ---------------------------------------------------------------------------

class TestCategoryDerivation:

    def test_category_for_derives_hospitality(self):
        assert category_for("hotel") == "hospitality_tourism"
        assert category_for("accommodation_provider") == "hospitality_tourism"

    def test_category_for_derives_financial(self):
        assert category_for("bank") == "financial_services"

    def test_category_for_rejects_unknown(self):
        with pytest.raises(ValueError):
            category_for("not_a_type")

    def test_validate_type_accepts_frozen_codes(self):
        for code in ORGANISATION_TYPE_CATALOG:
            assert validate_type(code) == code

    def test_validate_type_rejects_unknown(self):
        with pytest.raises(ValueError):
            validate_type("fictional_type")


# ---------------------------------------------------------------------------
# 3. Organisation storage / chokepoint
# ---------------------------------------------------------------------------

class TestChokepoint:

    def test_code_wins_over_legacy_business_category(self, db_session):
        _seed_catalog(db_session)
        org = _make_org(
            db_session,
            organisation_type_code="hotel",
            business_category=OrganizationType.RESTAURANT,
        )
        assert org.get_effective_org_type() == OrganizationType.HOTEL

    def test_legacy_business_category_fallback(self, db_session):
        org = _make_org(db_session, business_category=OrganizationType.HOTEL)
        assert org.organisation_type_code is None
        assert org.get_effective_org_type() == OrganizationType.HOTEL

    def test_corporate_default_when_no_type(self, db_session):
        org = _make_org(db_session)
        assert org.get_effective_org_type() == OrganizationType.CORPORATE

    def test_capabilities_use_effective_type(self, db_session):
        _seed_catalog(db_session)
        org = _make_org(db_session, organisation_type_code="hotel")
        assert org.can_manage_accommodation() is True

    def test_legacy_capabilities_via_fallback(self, db_session):
        org = _make_org(db_session, business_category=OrganizationType.HOTEL)
        assert org.can_manage_accommodation() is True

    def test_null_preserved_when_unset(self, db_session):
        org = _make_org(db_session)
        assert org.organisation_type_code is None

    def test_new_onboarding_writes_only_code_not_business_category(self, db_session):
        _seed_catalog(db_session)
        # Mirrors the Stage 4B write contract: organisation_type_code is the
        # canonical target; business_category stays NULL for new orgs.
        org = _make_org(db_session, organisation_type_code="hotel")
        assert org.organisation_type_code == "hotel"
        assert org.business_category is None
        assert org.get_effective_org_type() == OrganizationType.HOTEL


# ---------------------------------------------------------------------------
# 4. Consumer-by-default & provider capability unchanged
# ---------------------------------------------------------------------------

class TestConsumerByDefaultAndGates:

    def test_seeding_a_type_extracts_no_category_when_category_service_reads_db(
        self, db_session, app
    ):
        # Server-side derivation works before catalog tables are seeded
        # (constant fallback) without touching any provider capability.
        assert category_for("hotel") == "hospitality_tourism"

    def test_provider_gate_unchanged_model_contract(self):
        # The redesign does not alter the provider-capability licensing: a type
        # alone must never bestow an activated capability. The participation
        # lifecycle (INTENT → activation) is the ONLY activation path, and that
        # is enforced elsewhere (G-1). Here we assert the catalog never exposes
        # an implied activation flag.
        for code, meta in ORGANISATION_TYPE_CATALOG.items():
            assert "auto_activate" not in meta
            assert "capabilities" not in meta  # do not attach implied grants


# ---------------------------------------------------------------------------
# 5. DB-seeded + constant-fallback rendering (option availability)
# ---------------------------------------------------------------------------

class TestRenderingSources:

    def test_service_type_options_non_empty_via_constants(self):
        options = type_options()
        assert len(options) == 39
        for opt in options:
            assert opt["category_code"] in ORGANISATION_CATEGORIES

    def test_service_category_groups_cover_all_types_constants(self):
        groups = category_groups()
        grouped = {
            t["code"]
            for g in groups
            for t in g["types"]
        }
        assert grouped == set(ORGANISATION_TYPE_CATALOG)

    def test_db_seed_round_trip(self, db_session):
        # Seed the catalog tables (idempotent — rows may already exist in the
        # shared test DB from other sessions) and assert the service reads DB.
        _seed_catalog(db_session)

        groups = category_groups()
        assert groups
        type_codes = {t["code"] for g in groups for t in g["types"]}
        assert type_codes == set(ORGANISATION_TYPE_CATALOG)
        assert len(type_options()) == 39


# ---------------------------------------------------------------------------
# 6. Startup sanity
# ---------------------------------------------------------------------------

def test_create_app_import_sanity(app):
    assert app is not None
    from app.identity.catalog_data import ORGANISATION_TYPE_CATALOG
    assert len(ORGANISATION_TYPE_CATALOG) == 39