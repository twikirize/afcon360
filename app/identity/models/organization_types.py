# app/identity/models/organization_types.py
"""
Organization type vocabulary and capability metadata for AFCON360.

Compatibility contracts:
- OrganizationType retains the 39 canonical organization-type codes.
- DUAL_ORGANIZATION_CAPABILITIES describes provider and consumer metadata.
- ORGANIZATION_CAPABILITIES preserves legacy capability mappings.
- OrganizationRole and ROLE_PERMISSIONS preserve legacy role metadata.

Security:
- Capability metadata is not an authorization decision.
- Unknown or unmapped legacy organization types receive deny-all capabilities.
- Lookup helpers return defensive copies of mutable capability records.
- Canonical RBAC, provider activation, payment access, and compliance policy
  remain the responsibility of their owning services.

Compliance flags are descriptive metadata, not authoritative legal decisions.
"""

from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Union


OrganizationTypeInput = Union["OrganizationType", str]


__all__ = [
    "OrganizationType",
    "ProviderCapabilities",
    "ConsumerCapabilities",
    "OrganizationCapabilities",
    "OrganizationCapability",
    "DUAL_ORGANIZATION_CAPABILITIES",
    "ORGANIZATION_CAPABILITIES",
    "OrganizationRole",
    "ROLE_PERMISSIONS",
    "get_organization_capabilities",
    "get_dual_organization_capabilities",
    "can_provide_service",
    "can_consume_service",
    "get_role_permissions",
    "get_available_roles",
]


# ---------------------------------------------------------------------------
# Canonical organization type catalogue.
# These values must remain synchronized with the organization type catalogue.
# ---------------------------------------------------------------------------

class OrganizationType(Enum):
    """Canonical organization type codes."""

    # Hospitality & Tourism
    HOTEL = "hotel"
    RESTAURANT = "restaurant"
    TOUR_OPERATOR = "tour_operator"
    TRAVEL_AGENCY = "travel_agency"
    TOURISM_BOARD = "tourism_board"

    # Event Management
    EVENT_MANAGEMENT = "event_management"
    CONFERENCE_CENTER = "conference_center"
    VENUE_OPERATOR = "venue_operator"
    EXHIBITION_ORG = "exhibition_org"

    # Sports & Recreation
    SPORTS_TEAM = "sports_team"
    FOOTBALL_TEAM = "football_team"
    SPORTS_FEDERATION = "sports_federation"
    FITNESS_CENTER = "fitness_center"
    RECREATION_FACILITY = "recreation_facility"

    # Transportation
    TRANSPORT_COMPANY = "transport_company"
    AIRLINE = "airline"
    BUS_OPERATOR = "bus_operator"
    TAXI_SERVICE = "taxi_service"
    CAR_RENTAL = "car_rental"

    # Accommodation
    ACCOMMODATION_PROVIDER = "accommodation_provider"
    HOSTEL = "hostel"
    VACATION_RENTAL = "vacation_rental"
    CAMPING_SITE = "camping_site"

    # Business Services
    CORPORATE = "corporate"
    CONSULTING_FIRM = "consulting_firm"
    MARKETING_AGENCY = "marketing_agency"
    IT_SERVICES = "it_services"

    # Government & NGOs
    GOVERNMENT = "government"
    NGO = "ngo"
    EDUCATIONAL_INSTITUTION = "educational_institution"
    HEALTHCARE_PROVIDER = "healthcare_provider"

    # Financial Services
    BANK = "bank"
    INSURANCE_COMPANY = "insurance_company"
    INVESTMENT_FIRM = "investment_firm"
    FINTECH = "fintech"

    # Media & Entertainment
    MEDIA_COMPANY = "media_company"
    BROADCASTING = "broadcasting"
    ENTERTAINMENT = "entertainment"
    PUBLISHING = "publishing"


# ---------------------------------------------------------------------------
# Dual capability metadata
# ---------------------------------------------------------------------------

@dataclass
class ProviderCapabilities:
    """Services an organization type may provide in principle."""

    # Event services
    provides_event_management: bool = False
    provides_venue_rental: bool = False
    provides_ticketing: bool = False

    # Transport services
    provides_transport: bool = False
    provides_charter_buses: bool = False
    provides_airport_transfer: bool = False

    # Accommodation services
    provides_hotel_rooms: bool = False
    provides_conference_rooms: bool = False
    provides_catering: bool = False

    # Payment services
    provides_payment_processing: bool = False
    provides_wallet_services: bool = False

    # Other services
    provides_tour_guides: bool = False
    provides_equipment_rental: bool = False

    def to_dict(self) -> Dict[str, bool]:
        return dict(self.__dict__)


@dataclass
class ConsumerCapabilities:
    """Services an organization type may need to consume."""

    # Event needs
    needs_event_creation: bool = False
    needs_venue_booking: bool = False
    needs_ticket_purchasing: bool = False

    # Transport needs
    needs_transport_booking: bool = False
    needs_shuttle_service: bool = False

    # Accommodation needs
    needs_hotel_booking: bool = False
    needs_conference_booking: bool = False

    # Payment needs
    needs_payment_processing: bool = False
    needs_wallet_for_payments: bool = False

    # Other needs
    needs_tour_booking: bool = False
    needs_equipment_rental: bool = False

    def to_dict(self) -> Dict[str, bool]:
        return dict(self.__dict__)


@dataclass
class OrganizationCapabilities:
    """Dual provider/consumer metadata for an organization type."""

    provider: ProviderCapabilities = field(
        default_factory=ProviderCapabilities
    )
    consumer: ConsumerCapabilities = field(
        default_factory=ConsumerCapabilities
    )

    # Cross-cutting descriptive metadata
    can_manage_staff: bool = False
    can_manage_finance: bool = False
    can_view_analytics: bool = False
    requires_kyb: bool = False
    has_compliance_requirements: bool = False


@dataclass
class OrganizationCapability:
    """Legacy flat capability record retained for compatibility.

    Historical defaults are intentionally preserved. Do not instantiate this
    class as an authorization fallback; use get_organization_capabilities().

    The requires_* fields are descriptive metadata, not authoritative
    determinations of legal or regulatory obligations.
    """

    # Core capabilities: historical defaults retained
    can_manage_staff: bool = True
    can_manage_wallet: bool = True
    can_create_events: bool = False
    can_manage_accommodation: bool = False
    can_manage_transport: bool = False
    can_manage_tourism: bool = False

    # Advanced capabilities
    can_sell_tickets: bool = False
    can_process_payments: bool = False
    can_manage_inventory: bool = False
    can_provide_services: bool = False

    # Regulatory metadata
    requires_license: bool = False
    requires_insurance: bool = False
    requires_certification: bool = False

    # Legacy integration metadata
    integrates_with_events: bool = False
    integrates_with_accommodation: bool = False
    integrates_with_transport: bool = False
    integrates_with_wallet: bool = True

    def to_dict(self) -> Dict[str, bool]:
        return dict(self.__dict__)


def _deny_all_legacy_capability() -> OrganizationCapability:
    """Return an explicit deny-all legacy capability record."""

    return OrganizationCapability(
        can_manage_staff=False,
        can_manage_wallet=False,
        can_create_events=False,
        can_manage_accommodation=False,
        can_manage_transport=False,
        can_manage_tourism=False,
        can_sell_tickets=False,
        can_process_payments=False,
        can_manage_inventory=False,
        can_provide_services=False,
        requires_license=False,
        requires_insurance=False,
        requires_certification=False,
        integrates_with_events=False,
        integrates_with_accommodation=False,
        integrates_with_transport=False,
        integrates_with_wallet=False,
    )


def _coerce_organization_type(
    value: object,
) -> Optional[OrganizationType]:
    """Resolve an enum member or canonical string code."""

    if isinstance(value, OrganizationType):
        return value

    if isinstance(value, str):
        normalized = value.strip().lower()
        if not normalized:
            return None

        try:
            return OrganizationType(normalized)
        except ValueError:
            return None

    return None


# ---------------------------------------------------------------------------
# Dual provider/consumer capability mappings.
#
# Types not explicitly listed receive default all-false metadata.
# Do not infer provider eligibility or approval from these mappings.
# ---------------------------------------------------------------------------

DUAL_ORGANIZATION_CAPABILITIES: Dict[
    OrganizationType, OrganizationCapabilities
] = {
    OrganizationType.EVENT_MANAGEMENT: OrganizationCapabilities(
        provider=ProviderCapabilities(
            provides_event_management=True,
            provides_venue_rental=True,
            provides_ticketing=True,
            provides_catering=True,
            provides_payment_processing=True,
        ),
        consumer=ConsumerCapabilities(
            needs_hotel_booking=True,
            needs_transport_booking=True,
        ),
        can_manage_staff=True,
        can_manage_finance=True,
        can_view_analytics=True,
        requires_kyb=True,
        has_compliance_requirements=False,
    ),

    OrganizationType.TRANSPORT_COMPANY: OrganizationCapabilities(
        provider=ProviderCapabilities(
            provides_transport=True,
            provides_charter_buses=True,
            provides_airport_transfer=True,
            provides_wallet_services=True,
        ),
        consumer=ConsumerCapabilities(
            needs_transport_booking=False,
        ),
        can_manage_staff=True,
        can_manage_finance=True,
        can_view_analytics=True,
        requires_kyb=True,
        has_compliance_requirements=True,
    ),

    OrganizationType.HOTEL: OrganizationCapabilities(
        provider=ProviderCapabilities(
            provides_hotel_rooms=True,
            provides_conference_rooms=True,
            provides_catering=True,
            provides_event_management=True,
        ),
        consumer=ConsumerCapabilities(
            needs_transport_booking=True,
        ),
        can_manage_staff=True,
        can_manage_finance=True,
        can_view_analytics=True,
        requires_kyb=True,
        has_compliance_requirements=True,
    ),

    OrganizationType.TOUR_OPERATOR: OrganizationCapabilities(
        provider=ProviderCapabilities(
            provides_tour_guides=True,
            provides_transport=True,
            provides_event_management=True,
        ),
        consumer=ConsumerCapabilities(
            needs_hotel_booking=True,
            needs_venue_booking=True,
        ),
        can_manage_staff=True,
        can_manage_finance=True,
        can_view_analytics=True,
        requires_kyb=True,
        has_compliance_requirements=True,
    ),

    OrganizationType.CORPORATE: OrganizationCapabilities(
        provider=ProviderCapabilities(),
        consumer=ConsumerCapabilities(
            needs_event_creation=True,
            needs_venue_booking=True,
            needs_ticket_purchasing=True,
            needs_hotel_booking=True,
            needs_transport_booking=True,
            needs_payment_processing=True,
            needs_wallet_for_payments=True,
        ),
        can_manage_staff=True,
        can_manage_finance=True,
        can_view_analytics=True,
        requires_kyb=False,
        has_compliance_requirements=False,
    ),

    OrganizationType.FOOTBALL_TEAM: OrganizationCapabilities(
        provider=ProviderCapabilities(),
        consumer=ConsumerCapabilities(
            needs_event_creation=True,
            needs_venue_booking=True,
            needs_hotel_booking=True,
            needs_transport_booking=True,
            needs_ticket_purchasing=False,
            needs_payment_processing=True,
        ),
        can_manage_staff=True,
        can_manage_finance=True,
        can_view_analytics=True,
        requires_kyb=False,
        has_compliance_requirements=True,
    ),

    OrganizationType.SPORTS_TEAM: OrganizationCapabilities(
        provider=ProviderCapabilities(
            provides_venue_rental=True,
            provides_event_management=True,
        ),
        consumer=ConsumerCapabilities(
            needs_transport_booking=True,
            needs_hotel_booking=True,
        ),
        can_manage_staff=True,
        can_manage_finance=True,
        can_view_analytics=True,
        requires_kyb=False,
        has_compliance_requirements=False,
    ),

    OrganizationType.TRAVEL_AGENCY: OrganizationCapabilities(
        provider=ProviderCapabilities(
            provides_tour_guides=True,
            provides_transport=True,
            provides_event_management=True,
        ),
        consumer=ConsumerCapabilities(
            needs_hotel_booking=True,
            needs_transport_booking=True,
            needs_venue_booking=True,
        ),
        can_manage_staff=True,
        can_manage_finance=True,
        can_view_analytics=True,
        requires_kyb=True,
        has_compliance_requirements=True,
    ),

    OrganizationType.GOVERNMENT: OrganizationCapabilities(
        provider=ProviderCapabilities(),
        consumer=ConsumerCapabilities(
            needs_event_creation=True,
            needs_venue_booking=True,
            needs_transport_booking=True,
            needs_payment_processing=True,
        ),
        can_manage_staff=True,
        can_manage_finance=True,
        can_view_analytics=True,
        requires_kyb=True,
        has_compliance_requirements=True,
    ),

    OrganizationType.NGO: OrganizationCapabilities(
        provider=ProviderCapabilities(),
        consumer=ConsumerCapabilities(
            needs_event_creation=True,
            needs_venue_booking=True,
            needs_transport_booking=True,
            needs_payment_processing=True,
        ),
        can_manage_staff=True,
        can_manage_finance=True,
        can_view_analytics=True,
        requires_kyb=False,
        has_compliance_requirements=False,
    ),
}


# ---------------------------------------------------------------------------
# Legacy flat capability mappings.
#
# Preserve explicit mappings and historical defaults for omitted fields.
# The public helper returns deny-all metadata for unmapped types.
# ---------------------------------------------------------------------------

ORGANIZATION_CAPABILITIES: Dict[
    OrganizationType, OrganizationCapability
] = {
    # Hospitality & Tourism
    OrganizationType.HOTEL: OrganizationCapability(
        can_manage_accommodation=True,
        can_manage_staff=True,
        can_process_payments=True,
        can_manage_inventory=True,
        can_provide_services=True,
        requires_license=True,
        integrates_with_accommodation=True,
        integrates_with_wallet=True,
    ),

    OrganizationType.RESTAURANT: OrganizationCapability(
        can_manage_staff=True,
        can_process_payments=True,
        can_manage_inventory=True,
        can_provide_services=True,
        requires_license=True,
        integrates_with_wallet=True,
    ),

    OrganizationType.TOUR_OPERATOR: OrganizationCapability(
        can_manage_staff=True,
        can_create_events=True,
        can_manage_transport=True,
        can_manage_accommodation=True,
        can_sell_tickets=True,
        can_process_payments=True,
        requires_license=True,
        requires_insurance=True,
        integrates_with_events=True,
        integrates_with_transport=True,
        integrates_with_accommodation=True,
        integrates_with_wallet=True,
    ),

    OrganizationType.TRAVEL_AGENCY: OrganizationCapability(
        can_manage_staff=True,
        can_manage_transport=True,
        can_manage_accommodation=True,
        can_sell_tickets=True,
        can_process_payments=True,
        requires_license=True,
        integrates_with_transport=True,
        integrates_with_accommodation=True,
        integrates_with_wallet=True,
    ),

    # Event Management
    OrganizationType.EVENT_MANAGEMENT: OrganizationCapability(
        can_manage_staff=True,
        can_create_events=True,
        can_manage_accommodation=True,
        can_sell_tickets=True,
        can_process_payments=True,
        requires_license=True,
        requires_insurance=True,
        integrates_with_events=True,
        integrates_with_wallet=True,
    ),

    # Sports & Recreation
    OrganizationType.SPORTS_TEAM: OrganizationCapability(
        can_manage_staff=True,
        can_create_events=True,
        can_manage_transport=True,
        can_manage_accommodation=True,
        can_sell_tickets=True,
        can_process_payments=True,
        requires_license=True,
        requires_insurance=True,
        integrates_with_events=True,
        integrates_with_transport=True,
        integrates_with_accommodation=True,
        integrates_with_wallet=True,
    ),

    OrganizationType.SPORTS_FEDERATION: OrganizationCapability(
        can_manage_staff=True,
        can_create_events=True,
        can_manage_transport=True,
        can_sell_tickets=True,
        can_process_payments=True,
        requires_license=True,
        integrates_with_events=True,
        integrates_with_transport=True,
        integrates_with_wallet=True,
    ),

    # Transportation
    OrganizationType.TRANSPORT_COMPANY: OrganizationCapability(
        can_manage_staff=True,
        can_manage_transport=True,
        can_process_payments=True,
        requires_license=True,
        requires_insurance=True,
        integrates_with_transport=True,
        integrates_with_wallet=True,
    ),

    OrganizationType.BUS_OPERATOR: OrganizationCapability(
        can_manage_staff=True,
        can_manage_transport=True,
        can_sell_tickets=True,
        can_process_payments=True,
        requires_license=True,
        requires_insurance=True,
        integrates_with_transport=True,
        integrates_with_wallet=True,
    ),

    # Business Services
    OrganizationType.CORPORATE: OrganizationCapability(
        can_manage_staff=True,
        can_create_events=True,
        can_manage_accommodation=True,
        can_manage_transport=True,
        can_process_payments=True,
        integrates_with_events=True,
        integrates_with_accommodation=True,
        integrates_with_transport=True,
        integrates_with_wallet=True,
    ),

    # Government & NGOs
    OrganizationType.GOVERNMENT: OrganizationCapability(
        can_manage_staff=True,
        can_create_events=True,
        requires_license=True,
        integrates_with_events=True,
        integrates_with_wallet=True,
    ),

    OrganizationType.NGO: OrganizationCapability(
        can_manage_staff=True,
        can_create_events=True,
        can_process_payments=True,
        requires_license=True,
        integrates_with_events=True,
        integrates_with_wallet=True,
    ),
}


# ---------------------------------------------------------------------------
# Organization roles and legacy permission metadata.
# Canonical RBAC remains authoritative.
# ---------------------------------------------------------------------------

class OrganizationRole(Enum):
    """Legacy organization role identifiers."""

    # Executive roles
    ORG_OWNER = "org_owner"
    ORG_ADMIN = "org_admin"
    ORG_MANAGER = "org_manager"

    # Department heads
    OPERATIONS_MANAGER = "operations_manager"
    FINANCE_MANAGER = "finance_manager"
    HR_MANAGER = "hr_manager"
    MARKETING_MANAGER = "marketing_manager"

    # Staff roles
    STAFF_MEMBER = "staff_member"
    AGENT = "agent"
    REPRESENTATIVE = "representative"

    # Specialized roles
    EVENT_MANAGER = "event_manager"
    TRANSPORT_MANAGER = "transport_manager"
    ACCOMMODATION_MANAGER = "accommodation_manager"
    TOURISM_MANAGER = "tourism_manager"

    # Support roles
    VIEWER = "viewer"
    GUEST = "guest"


ROLE_PERMISSIONS: Dict[OrganizationRole, List[str]] = {
    OrganizationRole.ORG_OWNER: [
        "org.full_control",
        "org.manage_settings",
        "org.manage_staff",
        "org.manage_wallet",
        "org.create_events",
        "org.manage_accommodation",
        "org.manage_transport",
        "org.manage_tourism",
        "org.view_reports",
        "org.delete_org",
    ],

    OrganizationRole.ORG_ADMIN: [
        "org.manage_settings",
        "org.manage_staff",
        "org.manage_wallet",
        "org.create_events",
        "org.manage_accommodation",
        "org.manage_transport",
        "org.manage_tourism",
        "org.view_reports",
    ],

    OrganizationRole.ORG_MANAGER: [
        "org.manage_staff",
        "org.create_events",
        "org.manage_wallet",
        "org.view_reports",
    ],

    OrganizationRole.OPERATIONS_MANAGER: [
        "org.manage_operations",
        "org.manage_transport",
        "org.manage_accommodation",
        "org.view_reports",
    ],

    OrganizationRole.FINANCE_MANAGER: [
        "org.manage_wallet",
        "org.view_financial_reports",
        "org.process_payments",
    ],

    OrganizationRole.HR_MANAGER: [
        "org.manage_staff",
        "org.view_staff_reports",
    ],

    OrganizationRole.MARKETING_MANAGER: [],

    OrganizationRole.EVENT_MANAGER: [
        "org.create_events",
        "org.manage_events",
        "org.sell_tickets",
    ],

    OrganizationRole.TRANSPORT_MANAGER: [
        "org.manage_transport",
        "org.manage_fleet",
        "org.schedule_transport",
    ],

    OrganizationRole.ACCOMMODATION_MANAGER: [
        "org.manage_accommodation",
        "org.manage_bookings",
        "org.manage_rooms",
    ],

    OrganizationRole.TOURISM_MANAGER: [
        "org.manage_tourism",
        "org.create_tours",
        "org.manage_tourism_bookings",
    ],

    OrganizationRole.STAFF_MEMBER: [
        "org.view_basic_info",
        "org.perform_assigned_tasks",
    ],

    OrganizationRole.AGENT: [
        "org.sell_tickets",
        "org.manage_bookings",
        "org.process_payments",
    ],

    OrganizationRole.REPRESENTATIVE: [],

    OrganizationRole.VIEWER: [
        "org.view_basic_info",
    ],

    OrganizationRole.GUEST: [
        "org.view_public_info",
    ],
}


# ---------------------------------------------------------------------------
# Public lookup helpers
# ---------------------------------------------------------------------------

def get_organization_capabilities(
    org_type: OrganizationTypeInput,
) -> OrganizationCapability:
    """Return legacy capability metadata for a recognized organization type.

    Explicitly mapped types retain their historical values. Unknown,
    invalid, and unmapped types receive deny-all capability metadata.

    Returns a defensive copy so callers cannot mutate the global mapping
    through the returned object.

    Compliance flags do not determine whether regulatory review is required.
    """

    normalized_type = _coerce_organization_type(org_type)

    if normalized_type is None:
        return _deny_all_legacy_capability()

    capabilities = ORGANIZATION_CAPABILITIES.get(normalized_type)

    if capabilities is None:
        return _deny_all_legacy_capability()

    return deepcopy(capabilities)


def get_dual_organization_capabilities(
    org_type: OrganizationTypeInput,
) -> OrganizationCapabilities:
    """Return defensive provider/consumer metadata for an organization type.

    Unknown, invalid, and unmapped types receive all-false metadata.

    This does not establish provider approval, operational access, booking
    eligibility, or authorization to transact.
    """

    normalized_type = _coerce_organization_type(org_type)

    if normalized_type is None:
        return OrganizationCapabilities()

    capabilities = DUAL_ORGANIZATION_CAPABILITIES.get(normalized_type)

    if capabilities is None:
        return OrganizationCapabilities()

    return deepcopy(capabilities)


def can_provide_service(
    org_type: OrganizationTypeInput,
    service: str,
) -> bool:
    """Check whether type metadata lists a provided service.

    Example: can_provide_service(OrganizationType.HOTEL, "hotel_rooms")

    The service argument is the suffix after "provides_". Unknown types,
    invalid inputs, and unknown service names return False.

    This is descriptive metadata, not provider activation or authorization.
    """

    if not isinstance(service, str):
        return False

    service = service.strip()

    if not service:
        return False

    capabilities = get_dual_organization_capabilities(org_type)
    attribute = f"provides_{service}"

    if not hasattr(capabilities.provider, attribute):
        return False

    return getattr(capabilities.provider, attribute) is True


def can_consume_service(
    org_type: OrganizationTypeInput,
    service: str,
) -> bool:
    """Check whether type metadata lists a consumer need.

    Example: can_consume_service(OrganizationType.HOTEL, "transport_booking")

    The service argument is the suffix after "needs_". Unknown types,
    invalid inputs, and unknown service names return False.

    This is descriptive metadata, not permission to book or transact.
    """

    if not isinstance(service, str):
        return False

    service = service.strip()

    if not service:
        return False

    capabilities = get_dual_organization_capabilities(org_type)
    attribute = f"needs_{service}"

    if not hasattr(capabilities.consumer, attribute):
        return False

    return getattr(capabilities.consumer, attribute) is True


def get_role_permissions(role: OrganizationRole) -> List[str]:
    """Return a defensive copy of legacy permission metadata.

    Unknown roles return an empty list. Mutating the returned list cannot
    modify ROLE_PERMISSIONS.

    Permission enforcement belongs to the canonical RBAC service.
    """

    if not isinstance(role, OrganizationRole):
        return []

    return list(ROLE_PERMISSIONS.get(role, []))


def get_available_roles(
    org_type: OrganizationTypeInput,
) -> List[OrganizationRole]:
    """Return deterministic UI-projection roles for an organization type.

    The result describes roles that may be offered in a UI. It does not
    provision roles, assign memberships, or grant permissions.

    Generic roles remain available for compatibility. Specialized roles
    are added only for the recognized organization types listed below.
    """

    normalized_type = _coerce_organization_type(org_type)

    base_roles = [
        OrganizationRole.ORG_OWNER,
        OrganizationRole.ORG_ADMIN,
        OrganizationRole.STAFF_MEMBER,
        OrganizationRole.VIEWER,
    ]

    if normalized_type in (
        OrganizationType.SPORTS_TEAM,
        OrganizationType.EVENT_MANAGEMENT,
        OrganizationType.FOOTBALL_TEAM,
    ):
        base_roles.append(OrganizationRole.EVENT_MANAGER)

    if normalized_type in (
        OrganizationType.TRANSPORT_COMPANY,
        OrganizationType.BUS_OPERATOR,
    ):
        base_roles.append(OrganizationRole.TRANSPORT_MANAGER)

    if normalized_type in (
        OrganizationType.HOTEL,
        OrganizationType.ACCOMMODATION_PROVIDER,
    ):
        base_roles.append(OrganizationRole.ACCOMMODATION_MANAGER)

    if normalized_type in (
        OrganizationType.TOUR_OPERATOR,
        OrganizationType.TRAVEL_AGENCY,
    ):
        base_roles.append(OrganizationRole.TOURISM_MANAGER)

    return sorted(set(base_roles), key=lambda role: role.value)