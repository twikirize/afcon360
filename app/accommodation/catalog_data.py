# app/accommodation/catalog_data.py
"""
Canonical accommodation catalog definitions.

These constants are the *seed data* and the *fallback* when the DB lookup
tables (``accommodation_property_types``, ``accommodation_listing_types``,
``accommodation_policy_tiers``, ``accommodation_booking_modes``,
``accommodation_currencies``, ``accommodation_cancellation_policy_types``,
``accommodation_cancellation_phases``, ``accommodation_no_show_charge_types``)
have not been seeded yet (e.g. before the operator runs the catalog seed, or
in a test environment built via ``db.create_all()``).

Once the tables are seeded, ``catalog_service`` reads the truth from the
database and these constants are only used as a safe-fail bootstrap.
"""

# property type -> (friendly label, host types allowed, valid listing types,
#                   whether it is a commercial/multi-room establishment)
PROPERTY_TYPE_CATALOG: dict[str, dict] = {
    "apartment": {
        "label": "Apartment",
        "host_types": ("individual", "organisation"),
        "listing_types": ("entire_place", "private_room", "shared_room"),
        "commercial": False,
    },
    "house": {
        "label": "House",
        "host_types": ("individual", "organisation"),
        "listing_types": ("entire_place", "private_room", "shared_room"),
        "commercial": False,
    },
    "villa": {
        "label": "Villa",
        "host_types": ("individual", "organisation"),
        "listing_types": ("entire_place", "private_room"),
        "commercial": False,
    },
    "lodge": {
        "label": "Lodge",
        "host_types": ("individual", "organisation"),
        "listing_types": ("entire_place", "private_room"),
        "commercial": True,
    },
    "guesthouse": {
        "label": "Guesthouse",
        "host_types": ("individual", "organisation"),
        "listing_types": ("entire_place", "private_room"),
        "commercial": True,
    },
    "hostel": {
        "label": "Hostel",
        "host_types": ("organisation",),
        "listing_types": ("private_room", "shared_room"),
        "commercial": True,
    },
    "hotel": {
        "label": "Hotel",
        "host_types": ("organisation",),
        "listing_types": ("private_room", "entire_place"),
        "commercial": True,
    },
    "boutique_hotel": {
        "label": "Boutique Hotel",
        "host_types": ("organisation",),
        "listing_types": ("private_room", "entire_place"),
        "commercial": True,
    },
    "resort": {
        "label": "Resort",
        "host_types": ("organisation",),
        "listing_types": ("private_room", "entire_place"),
        "commercial": True,
    },
}

# Human labels keyed by the canonical listing-type value.
LISTING_TYPE_LABELS: dict[str, str] = {
    "entire_place": "Entire Place",
    "private_room": "Private Room",
    "shared_room": "Shared Room",
}

# Cancellation policy tiers -> (label, description, icon). The description and
# icon drive the policy radio cards; the label drives the select option.
# These are the *simple* tiers used by PropertyBookingPolicy.cancellation_policy
# and the host create/edit form radio cards.
CANCELLATION_POLICY_TIERS: list[dict] = [
    {
        "code": "flexible",
        "label": "Flexible",
        "description": "Full refund up to 24h before check-in",
        "icon": "🔄",
    },
    {
        "code": "moderate",
        "label": "Moderate",
        "description": "Full refund 5+ days, 50% refund 1-4 days",
        "icon": "⚖️",
    },
    {
        "code": "strict",
        "label": "Strict",
        "description": "50% refund 7+ days only",
        "icon": "🔒",
    },
    {
        "code": "super_strict",
        "label": "Super Strict",
        "description": "Strictest tier — very limited refunds",
        "icon": "💎",
    },
    {
        "code": "non_refundable",
        "label": "Non-Refundable",
        "description": "No refunds under any circumstances",
        "icon": "🚫",
    },
]

# Advanced cancellation policy types (for CancellationPolicy model).
# These map to the phase-based policy engine.
CANCELLATION_POLICY_TYPES: list[dict] = [
    {
        "code": "FLEX",
        "label": "Flexible",
        "description": "Full refund if cancelled at least 1 day before check-in",
        "pre_checkin_days": 1,
        "pre_checkin_refund_pct": 100.00,
        "mid_stay_refund_pct": 100.00,
        "no_show_penalty": 0.00,
    },
    {
        "code": "MOD",
        "label": "Moderate",
        "description": "Full refund 5+ days before, 50% refund 1-4 days before",
        "pre_checkin_days": 5,
        "pre_checkin_refund_pct": 100.00,
        "mid_stay_refund_pct": 100.00,
        "no_show_penalty": 0.00,
    },
    {
        "code": "STRICT",
        "label": "Strict",
        "description": "50% refund 7+ days before, no refund within 7 days",
        "pre_checkin_days": 7,
        "pre_checkin_refund_pct": 50.00,
        "mid_stay_refund_pct": 50.00,
        "no_show_penalty": 0.00,
    },
    {
        "code": "SUPER",
        "label": "Super Strict",
        "description": "50% refund 30+ days, 25% refund 14-29 days, no refund within 14 days",
        "pre_checkin_days": 30,
        "pre_checkin_refund_pct": 50.00,
        "mid_stay_refund_pct": 25.00,
        "no_show_penalty": 0.00,
    },
    {
        "code": "NOSHOW",
        "label": "No-Show",
        "description": "Full first night charged for no-show",
        "pre_checkin_days": 0,
        "pre_checkin_refund_pct": 0.00,
        "mid_stay_refund_pct": 0.00,
        "no_show_penalty": 1.00,  # Interpreted as "full first night"
    },
]

# Cancellation phases
CANCELLATION_PHASES: list[dict] = [
    {"code": "pre_checkin", "label": "Pre Check-in", "description": "Cancellation before check-in date"},
    {"code": "mid_stay", "label": "Mid Stay", "description": "Cancellation after check-in but before check-out"},
    {"code": "no_show", "label": "No Show", "description": "Guest never arrives on check-in date"},
]

# No-show charge types (for PropertyBookingPolicy.no_show_charge_type)
NO_SHOW_CHARGE_TYPES: list[dict] = [
    {"code": "none", "label": "No Charge", "description": "No penalty for no-show"},
    {"code": "first_night", "label": "Charge First Night", "description": "Charge the first night's rate"},
    {"code": "full_booking", "label": "Charge Full Booking", "description": "Charge the entire booking amount"},
]

# Booking modes -> (label, is_default)
BOOKING_MODES: list[dict] = [
    {
        "code": "instant",
        "label": "Instant Book - Automatically confirm bookings",
        "is_default": True,
    },
    {
        "code": "host_approval",
        "label": "Host Approval Required - Manually approve each booking",
        "is_default": False,
    },
]

# Currencies -> (name, symbol)
CURRENCIES: list[dict] = [
    {"code": "USD", "name": "US Dollar", "symbol": "$"},
    {"code": "EUR", "name": "Euro", "symbol": "€"},
    {"code": "GBP", "name": "British Pound", "symbol": "£"},
    {"code": "UGX", "name": "Ugandan Shilling", "symbol": "USh"},
    {"code": "KES", "name": "Kenyan Shilling", "symbol": "KSh"},
    {"code": "NGN", "name": "Nigerian Naira", "symbol": "₦"},
]

# Booking modes -> (label, is_default)
BOOKING_MODES: list[dict] = [
    {
        "code": "instant",
        "label": "Instant Book - Automatically confirm bookings",
        "is_default": True,
    },
    {
        "code": "host_approval",
        "label": "Host Approval Required - Manually approve each booking",
        "is_default": False,
    },
]

# Currencies -> (name, symbol)
CURRENCIES: list[dict] = [
    {"code": "USD", "name": "US Dollar", "symbol": "$"},
    {"code": "EUR", "name": "Euro", "symbol": "€"},
    {"code": "GBP", "name": "British Pound", "symbol": "£"},
    {"code": "UGX", "name": "Ugandan Shilling", "symbol": "USh"},
    {"code": "KES", "name": "Kenyan Shilling", "symbol": "KSh"},
    {"code": "NGN", "name": "Nigerian Naira", "symbol": "₦"},
]