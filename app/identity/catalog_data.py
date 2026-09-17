# app/identity/catalog_data.py
"""
Canonical organisation classification catalogue definitions.

These constants are the *seed data* and the *fallback* when the DB lookup
tables (``organisation_categories``, ``organisation_types``) have not been
seeded yet (e.g. before the operator runs the catalogue seed, or in a test
environment built via ``db.create_all()``).

Once the tables are seeded, ``organisation_classification_service`` reads the
truth from the database and these constants are only used as a safe-fail
bootstrap.

FROZEN CONTRACT:
  * 39 organisation types — MUST match the ``OrganizationType`` enum values
    1:1 (see ``_assert_parity``). Never add/remove/rename a code here without
    an approved specification change.
  * 8 categories — the existing onboarding optgroups. Category is DERIVED
    server-side from the type; the client submits only the type code.
  * Type = what the organisation IS. ProviderParticipation (ProviderCapability
    lifecycle) = what it PROVIDES. Consumer access is universal; a provider
    capability requires an explicit intent → activation lifecycle, never
    auto-activation from the type alone.
"""

# category code -> label (dict order = optgroup order surfaced in onboarding)
ORGANISATION_CATEGORIES: dict[str, str] = {
    "hospitality_tourism": "Hospitality & Tourism",
    "events_venues": "Events & Venues",
    "sports_recreation": "Sports & Recreation",
    "transportation": "Transportation",
    "business_services": "Business Services",
    "government_institutions": "Government & Institutions",
    "financial_services": "Financial Services",
    "media_entertainment": "Media & Entertainment",
}

# type code -> {label, category_code}
# Codes MUST mirror app.identity.models.organization_types.OrganizationType.values.
ORGANISATION_TYPE_CATALOG: dict[str, dict] = {
    # ---- Hospitality & Tourism ----
    "hotel": {"label": "Hotel", "category_code": "hospitality_tourism"},
    "restaurant": {"label": "Restaurant", "category_code": "hospitality_tourism"},
    "tour_operator": {"label": "Tour Operator", "category_code": "hospitality_tourism"},
    "travel_agency": {"label": "Travel Agency", "category_code": "hospitality_tourism"},
    "tourism_board": {"label": "Tourism Board", "category_code": "hospitality_tourism"},
    "accommodation_provider": {"label": "Accommodation Provider", "category_code": "hospitality_tourism"},
    "hostel": {"label": "Hostel", "category_code": "hospitality_tourism"},
    "vacation_rental": {"label": "Vacation Rental", "category_code": "hospitality_tourism"},
    "camping_site": {"label": "Camping Site", "category_code": "hospitality_tourism"},
    # ---- Events & Venues ----
    "event_management": {"label": "Event Management", "category_code": "events_venues"},
    "conference_center": {"label": "Conference Center", "category_code": "events_venues"},
    "venue_operator": {"label": "Venue Operator", "category_code": "events_venues"},
    "exhibition_org": {"label": "Exhibition Organisation", "category_code": "events_venues"},
    # ---- Sports & Recreation ----
    "sports_team": {"label": "Sports Team", "category_code": "sports_recreation"},
    "football_team": {"label": "Football Team", "category_code": "sports_recreation"},
    "sports_federation": {"label": "Sports Federation", "category_code": "sports_recreation"},
    "fitness_center": {"label": "Fitness Center", "category_code": "sports_recreation"},
    "recreation_facility": {"label": "Recreation Facility", "category_code": "sports_recreation"},
    # ---- Transportation ----
    "transport_company": {"label": "Transport Company", "category_code": "transportation"},
    "airline": {"label": "Airline", "category_code": "transportation"},
    "bus_operator": {"label": "Bus Operator", "category_code": "transportation"},
    "taxi_service": {"label": "Taxi Service", "category_code": "transportation"},
    "car_rental": {"label": "Car Rental", "category_code": "transportation"},
    # ---- Business Services ----
    "corporate": {"label": "Corporate", "category_code": "business_services"},
    "consulting_firm": {"label": "Consulting Firm", "category_code": "business_services"},
    "marketing_agency": {"label": "Marketing Agency", "category_code": "business_services"},
    "it_services": {"label": "IT Services", "category_code": "business_services"},
    # ---- Government & Institutions ----
    "government": {"label": "Government", "category_code": "government_institutions"},
    "ngo": {"label": "NGO", "category_code": "government_institutions"},
    "educational_institution": {"label": "Educational Institution", "category_code": "government_institutions"},
    "healthcare_provider": {"label": "Healthcare Provider", "category_code": "government_institutions"},
    # ---- Financial Services ----
    "bank": {"label": "Bank", "category_code": "financial_services"},
    "insurance_company": {"label": "Insurance Company", "category_code": "financial_services"},
    "investment_firm": {"label": "Investment Firm", "category_code": "financial_services"},
    "fintech": {"label": "Fintech", "category_code": "financial_services"},
    # ---- Media & Entertainment ----
    "media_company": {"label": "Media Company", "category_code": "media_entertainment"},
    "broadcasting": {"label": "Broadcasting", "category_code": "media_entertainment"},
    "entertainment": {"label": "Entertainment", "category_code": "media_entertainment"},
    "publishing": {"label": "Publishing", "category_code": "media_entertainment"},
}

# Every type code must belong to a defined category.
_ASSERTED = False


def _assert_catalog_integrity() -> None:
    """Verify the frozen catalogue invariants (idempotent, module-load safe)."""
    global _ASSERTED
    if _ASSERTED:
        return
    known_categories = set(ORGANISATION_CATEGORIES)
    for code, meta in ORGANISATION_TYPE_CATALOG.items():
        if meta["category_code"] not in known_categories:
            raise AssertionError(
                f"Organisation type {code!r} references unknown category "
                f"{meta['category_code']!r}"
            )
    _ASSERTED = True


_assert_catalog_integrity()