# app/accommodation/utils.py
"""
Shared accommodation helpers.

Centralises the Enum -> string conversion that the ENUM-to-String
migration made necessary. After that migration, DB-loaded columns
hold plain strings, while enum literals still expose `.value`.
Calling `.value` directly on a DB value crashes ('str' has no
attribute 'value'), so always route through `enum_value`.
"""

import enum

# ISO 3166-1 alpha-2 country codes for AFCON360 supported countries.
# Key: lowercase country name (for normalization)
# Value: ISO alpha-2 code
_COUNTRIES: dict[str, str] = {
    "uganda": "UG",
    "rwanda": "RW",
    "kenya": "KE",
    "tanzania": "TZ",
    "ghana": "GH",
    "ug": "UG",
    "rw": "RW",
    "ke": "KE",
    "tz": "TZ",
    "gh": "GH",
}


def enum_value(val):
    """
    Safely convert an Enum member to its string value.

    - If `val` is an enum member, return its `.value`.
    - If `val` is already a plain string/value, return it unchanged.

    Use this everywhere you would otherwise write `something.value`,
    especially on model attributes that were formerly Enum columns
    (property_type, status, payment_status, cancellation_policy, etc.).
    """
    return val.value if isinstance(val, enum.Enum) else val


def normalize_country(country_input: str | None) -> str:
    """
    Normalize a country value to its ISO 3166-1 alpha-2 code.

    Handles:
    - Full country names (case-insensitive, whitespace trimmed): "Uganda" → "UG"
    - ISO alpha-2 codes (pass-through, case-insensitive): "UG" → "UG", "ug" → "UG"
    - None/empty returns default 'UG'

    Raises ValueError if the country cannot be normalized to a valid ISO code.
    """
    if not country_input:
        return "UG"

    key = country_input.strip().lower()
    result = _COUNTRIES.get(key)
    if result is not None:
        return result.upper()

    # Also try reverse: if input is already a 2-char code, normalize case
    if len(key) == 2 and key.isalpha():
        return key.upper()

    # Not found - raise a descriptive error
    raise ValueError(
        f"Unknown country: '{country_input}'. "
        "Expected a supported country name or ISO alpha-2 code."
    )
