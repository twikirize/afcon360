# app/identity/catalog_data.py
"""
Canonical organisation classification catalogue definitions.

These constants are the seed data and fallback when the database lookup
tables (organisation_categories, organisation_types) have not been seeded
yet, such as before catalogue seeding or in a test environment built via
db.create_all().

Once the tables are seeded, organisation_classification_service reads the
database catalogue. These constants remain the controlled bootstrap source.

FROZEN CONTRACT:
  * 39 organisation types — MUST match the OrganizationType enum values
    1:1. Never add, remove, or rename a code without an approved
    specification change.
  * 8 categories — the existing onboarding optgroups. Category is derived
    server-side from the type; the client submits only the type code.
  * Type = what the organisation IS. ProviderParticipation defines the
    provider participation lifecycle. Consumer access and provider
    activation are controlled by their respective application services,
    never automatically granted by classification alone.

Integrity is enforced at import time by ``_assert_catalog_integrity``.
The function is also callable so tests can invoke it after mutating the
dictionaries to prove the checks fire.
"""

from app.identity.models.organization_types import OrganizationType


# ---------------------------------------------------------------------------
# Frozen category contract
# ---------------------------------------------------------------------------

# Category display order. The onboarding UI renders categories in the order
# they appear in ORGANISATION_CATEGORIES below. Reordering is a contract
# change and requires an approved specification change.
_EXPECTED_CATEGORY_ORDER: tuple[str, ...] = (
    "hospitality_tourism",
    "events_venues",
    "sports_recreation",
    "transportation",
    "business_services",
    "government_institutions",
    "financial_services",
    "media_entertainment",
)

# Derive the expected category set from the single ordered definition.
# This preserves both exact membership and display-order checks without
# maintaining the same eight codes independently.
_EXPECTED_CATEGORY_CODES: frozenset[str] = frozenset(
    _EXPECTED_CATEGORY_ORDER
)

# Freeze the enum's size independently of catalogue-to-enum parity.
# Simultaneous additions to both the enum and catalogue must not silently
# change the approved number of types.
_EXPECTED_TYPE_COUNT: int = 39

# Exact keys permitted on each type metadata entry.
_EXPECTED_TYPE_METADATA_KEYS: frozenset[str] = frozenset({
    "label",
    "category_code",
})


# ---------------------------------------------------------------------------
# Category catalogue
# ---------------------------------------------------------------------------

# Category code -> label.
# Dictionary insertion order defines the category order surfaced in onboarding.
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


# ---------------------------------------------------------------------------
# Organisation type catalogue
# ---------------------------------------------------------------------------

# Type code -> {label, category_code}.
# Codes MUST mirror OrganizationType member values.
# Keep these keys literal so accidental changes cannot be concealed by
# dynamically generating the catalogue from the enum.
ORGANISATION_TYPE_CATALOG: dict[str, dict[str, str]] = {
    # ---- Hospitality & Tourism ----
    "hotel": {
        "label": "Hotel",
        "category_code": "hospitality_tourism",
    },
    "restaurant": {
        "label": "Restaurant",
        "category_code": "hospitality_tourism",
    },
    "tour_operator": {
        "label": "Tour Operator",
        "category_code": "hospitality_tourism",
    },
    "travel_agency": {
        "label": "Travel Agency",
        "category_code": "hospitality_tourism",
    },
    "tourism_board": {
        "label": "Tourism Board",
        "category_code": "hospitality_tourism",
    },
    "accommodation_provider": {
        "label": "Accommodation Provider",
        "category_code": "hospitality_tourism",
    },
    "hostel": {
        "label": "Hostel",
        "category_code": "hospitality_tourism",
    },
    "vacation_rental": {
        "label": "Vacation Rental",
        "category_code": "hospitality_tourism",
    },
    "camping_site": {
        "label": "Camping Site",
        "category_code": "hospitality_tourism",
    },

    # ---- Events & Venues ----
    "event_management": {
        "label": "Event Management",
        "category_code": "events_venues",
    },
    "conference_center": {
        "label": "Conference Center",
        "category_code": "events_venues",
    },
    "venue_operator": {
        "label": "Venue Operator",
        "category_code": "events_venues",
    },
    "exhibition_org": {
        "label": "Exhibition Organisation",
        "category_code": "events_venues",
    },

    # ---- Sports & Recreation ----
    "sports_team": {
        "label": "Sports Team",
        "category_code": "sports_recreation",
    },
    "football_team": {
        "label": "Football Team",
        "category_code": "sports_recreation",
    },
    "sports_federation": {
        "label": "Sports Federation",
        "category_code": "sports_recreation",
    },
    "fitness_center": {
        "label": "Fitness Center",
        "category_code": "sports_recreation",
    },
    "recreation_facility": {
        "label": "Recreation Facility",
        "category_code": "sports_recreation",
    },

    # ---- Transportation ----
    "transport_company": {
        "label": "Transport Company",
        "category_code": "transportation",
    },
    "airline": {
        "label": "Airline",
        "category_code": "transportation",
    },
    "bus_operator": {
        "label": "Bus Operator",
        "category_code": "transportation",
    },
    "taxi_service": {
        "label": "Taxi Service",
        "category_code": "transportation",
    },
    "car_rental": {
        "label": "Car Rental",
        "category_code": "transportation",
    },

    # ---- Business Services ----
    "corporate": {
        "label": "Corporate",
        "category_code": "business_services",
    },
    "consulting_firm": {
        "label": "Consulting Firm",
        "category_code": "business_services",
    },
    "marketing_agency": {
        "label": "Marketing Agency",
        "category_code": "business_services",
    },
    "it_services": {
        "label": "IT Services",
        "category_code": "business_services",
    },

    # ---- Government & Institutions ----
    "government": {
        "label": "Government",
        "category_code": "government_institutions",
    },
    "ngo": {
        "label": "NGO",
        "category_code": "government_institutions",
    },
    "educational_institution": {
        "label": "Educational Institution",
        "category_code": "government_institutions",
    },
    "healthcare_provider": {
        "label": "Healthcare Provider",
        "category_code": "government_institutions",
    },

    # ---- Financial Services ----
    "bank": {
        "label": "Bank",
        "category_code": "financial_services",
    },
    "insurance_company": {
        "label": "Insurance Company",
        "category_code": "financial_services",
    },
    "investment_firm": {
        "label": "Investment Firm",
        "category_code": "financial_services",
    },
    "fintech": {
        "label": "Fintech",
        "category_code": "financial_services",
    },

    # ---- Media & Entertainment ----
    "media_company": {
        "label": "Media Company",
        "category_code": "media_entertainment",
    },
    "broadcasting": {
        "label": "Broadcasting",
        "category_code": "media_entertainment",
    },
    "entertainment": {
        "label": "Entertainment",
        "category_code": "media_entertainment",
    },
    "publishing": {
        "label": "Publishing",
        "category_code": "media_entertainment",
    },
}


# ---------------------------------------------------------------------------
# Integrity validation
# ---------------------------------------------------------------------------

def _validate_label(label: object, code: str, kind: str) -> str:
    """Validate a category or type label and return it."""
    if not isinstance(label, str):
        raise AssertionError(
            f"Organisation {kind} {code!r} must have a string label; "
            f"got {type(label).__name__}."
        )

    if not label.strip():
        raise AssertionError(
            f"Organisation {kind} {code!r} must have a non-empty label."
        )

    if label != label.strip():
        raise AssertionError(
            f"Organisation {kind} {code!r} label {label!r} must not have "
            "leading or trailing whitespace."
        )

    if label == code:
        raise AssertionError(
            f"Organisation {kind} {code!r} label must not equal its code."
        )

    return label


def _assert_catalog_integrity() -> None:
    """
    Validate the frozen catalogue contract.

    Checks:
      1. Category codes exactly match the frozen category set.
      2. Category display order matches the frozen order.
      3. Category labels are valid and unique.
      4. OrganizationType has exactly 39 members.
      5. Catalogue type codes exactly match OrganizationType values.
      6. Type metadata is a dictionary with exactly the expected keys.
      7. Type labels are valid and unique.
      8. Every type references a known category.
      9. Every category contains at least one type.

    The function does not cache its result. Every explicit invocation
    revalidates the current dictionaries, including mutations made in tests.
    """

    # ---- 1. Category code set -------------------------------------------
    actual_category_codes = set(ORGANISATION_CATEGORIES)

    if actual_category_codes != _EXPECTED_CATEGORY_CODES:
        missing = sorted(_EXPECTED_CATEGORY_CODES - actual_category_codes)
        unexpected = sorted(actual_category_codes - _EXPECTED_CATEGORY_CODES)

        raise AssertionError(
            "Organisation category code set drifted. "
            f"Missing: {missing!r}. "
            f"Unexpected: {unexpected!r}."
        )

    # ---- 2. Category display order --------------------------------------
    actual_category_order = tuple(ORGANISATION_CATEGORIES.keys())

    if actual_category_order != _EXPECTED_CATEGORY_ORDER:
        raise AssertionError(
            "Organisation category display order drifted. "
            f"Expected: {_EXPECTED_CATEGORY_ORDER!r}. "
            f"Actual:   {actual_category_order!r}. "
            "Reordering categories changes the onboarding presentation "
            "and requires an approved specification change."
        )

    # ---- 3. Category labels ---------------------------------------------
    seen_category_labels: dict[str, str] = {}

    for code, label in ORGANISATION_CATEGORIES.items():
        validated = _validate_label(label, code, kind="category")

        if validated in seen_category_labels:
            raise AssertionError(
                f"Duplicate category label {validated!r} on codes "
                f"{seen_category_labels[validated]!r} and {code!r}."
            )

        seen_category_labels[validated] = code

    # ---- 4. Enum member count -------------------------------------------
    expected_type_codes = {member.value for member in OrganizationType}

    if len(expected_type_codes) != _EXPECTED_TYPE_COUNT:
        raise AssertionError(
            f"OrganizationType enum has {len(expected_type_codes)} distinct type codes; "
            f"frozen contract requires exactly {_EXPECTED_TYPE_COUNT}. "
            "Adding or removing a type requires an approved specification "
            "change."
        )

    # ---- 5. Catalogue-to-enum parity -----------------------------------
    actual_type_codes = set(ORGANISATION_TYPE_CATALOG)

    if actual_type_codes != expected_type_codes:
        missing = sorted(expected_type_codes - actual_type_codes)
        unexpected = sorted(actual_type_codes - expected_type_codes)

        raise AssertionError(
            "Organisation type catalogue drifted from OrganizationType. "
            f"Missing: {missing!r}. "
            f"Unexpected: {unexpected!r}."
        )

    # ---- 6-8. Type metadata, labels, and category references ------------
    seen_type_labels: dict[str, str] = {}
    categories_in_use: dict[str, int] = {
        code: 0 for code in _EXPECTED_CATEGORY_CODES
    }

    for code, metadata in ORGANISATION_TYPE_CATALOG.items():
        # ---- 6. Metadata structure --------------------------------------
        if type(metadata) is not dict:
            raise AssertionError(
                f"Organisation type {code!r} metadata must be a dictionary; "
                f"got {type(metadata).__name__}."
            )

        actual_keys = set(metadata)

        if actual_keys != _EXPECTED_TYPE_METADATA_KEYS:
            missing = sorted(_EXPECTED_TYPE_METADATA_KEYS - actual_keys)
            unexpected = sorted(actual_keys - _EXPECTED_TYPE_METADATA_KEYS)

            raise AssertionError(
                f"Organisation type {code!r} metadata keys drifted. "
                f"Missing: {missing!r}. "
                f"Unexpected: {unexpected!r}."
            )

        # ---- 7. Type label ----------------------------------------------
        label = _validate_label(metadata["label"], code, kind="type")

        if label in seen_type_labels:
            raise AssertionError(
                f"Duplicate organisation type label {label!r} on codes "
                f"{seen_type_labels[label]!r} and {code!r}."
            )

        seen_type_labels[label] = code

        # ---- 8. Category reference --------------------------------------
        category_code = metadata["category_code"]

        if category_code not in _EXPECTED_CATEGORY_CODES:
            raise AssertionError(
                f"Organisation type {code!r} references unknown category "
                f"{category_code!r}. Known categories: "
                f"{sorted(_EXPECTED_CATEGORY_CODES)!r}."
            )

        categories_in_use[category_code] += 1

    # ---- 9. No empty categories -----------------------------------------
    empty_categories = sorted(
        code for code, count in categories_in_use.items() if count == 0
    )

    if empty_categories:
        raise AssertionError(
            "Organisation categories present in the frozen contract but "
            f"unused by any type: {empty_categories!r}. Either assign "
            "at least one type or remove the category in an approved "
            "specification change."
        )


# Fail early if the frozen catalogue contract is invalid.
_assert_catalog_integrity()
