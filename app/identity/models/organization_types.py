# app/identity/models/organization_types.py
"""
Organization Types with DUAL Capabilities:
1. PROVIDER: What services they OFFER to others
2. CONSUMER: What services they NEED from others
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Any


class OrganizationType(Enum):
    """Comprehensive organization types for AFCON360 ecosystem"""
    
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
    FOOTBALL_TEAM = "football_team"  # National Football Teams
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


@dataclass
class ProviderCapabilities:
    """What this organization SELLS/PROVIDES to others"""
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
        return {k: v for k, v in self.__dict__.items()}


@dataclass
class ConsumerCapabilities:
    """What this organization BUYS/NEEDS from others"""
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
        return {k: v for k, v in self.__dict__.items()}


@dataclass
class OrganizationCapabilities:
    """Complete organization capabilities - what they PROVIDE and what they CONSUME"""
    provider: ProviderCapabilities = field(default_factory=ProviderCapabilities)
    consumer: ConsumerCapabilities = field(default_factory=ConsumerCapabilities)
    
    # Common capabilities (both provider and consumer)
    can_manage_staff: bool = False
    can_manage_finance: bool = False
    can_view_analytics: bool = False
    requires_kyb: bool = False
    has_compliance_requirements: bool = False


# Legacy OrganizationCapability for backward compatibility
@dataclass
class OrganizationCapability:
    """Legacy OrganizationCapability for backward compatibility"""
    # Core capabilities
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
    
    # Regulatory requirements
    requires_license: bool = False
    requires_insurance: bool = False
    requires_certification: bool = False
    
    # System integration
    integrates_with_events: bool = False
    integrates_with_accommodation: bool = False
    integrates_with_transport: bool = False
    integrates_with_wallet: bool = True


# Dual capability mappings
DUAL_ORGANIZATION_CAPABILITIES: Dict[OrganizationType, OrganizationCapabilities] = {
    
    # ========== PROVIDERS (SELL services) ==========
    
    # EVENT_MANAGEMENT: They SELL event services
    OrganizationType.EVENT_MANAGEMENT: OrganizationCapabilities(
        provider=ProviderCapabilities(
            provides_event_management=True,
            provides_venue_rental=True,
            provides_ticketing=True,
            provides_catering=True,
            provides_payment_processing=True
        ),
        consumer=ConsumerCapabilities(
            needs_hotel_booking=True,      # They might book hotels FOR their events
            needs_transport_booking=True,  # They might book buses FOR their events
        ),
        can_manage_staff=True,
        can_manage_finance=True,
        can_view_analytics=True,
        requires_kyb=True,
        has_compliance_requirements=False
    ),
    
    # TRANSPORT_COMPANY: They SELL transport services
    OrganizationType.TRANSPORT_COMPANY: OrganizationCapabilities(
        provider=ProviderCapabilities(
            provides_transport=True,
            provides_charter_buses=True,
            provides_airport_transfer=True,
            provides_wallet_services=True
        ),
        consumer=ConsumerCapabilities(
            needs_transport_booking=False,  # They maintain their own fleet
        ),
        can_manage_staff=True,
        can_manage_finance=True,
        can_view_analytics=True,
        requires_kyb=True,
        has_compliance_requirements=True  # Transport licenses
    ),
    
    # HOTEL: They SELL rooms
    OrganizationType.HOTEL: OrganizationCapabilities(
        provider=ProviderCapabilities(
            provides_hotel_rooms=True,
            provides_conference_rooms=True,
            provides_catering=True,
            provides_event_management=True  # Many hotels host events
        ),
        consumer=ConsumerCapabilities(
            needs_transport_booking=True,   # Hotels book taxis for guests
        ),
        can_manage_staff=True,
        can_manage_finance=True,
        can_view_analytics=True,
        requires_kyb=True,
        has_compliance_requirements=True  # Tourism licenses
    ),
    
    # TOUR_OPERATOR: They SELL tours
    OrganizationType.TOUR_OPERATOR: OrganizationCapabilities(
        provider=ProviderCapabilities(
            provides_tour_guides=True,
            provides_transport=True,
            provides_event_management=True
        ),
        consumer=ConsumerCapabilities(
            needs_hotel_booking=True,       # Book hotels for tour groups
            needs_venue_booking=True,       # Book attractions
        ),
        can_manage_staff=True,
        can_manage_finance=True,
        can_view_analytics=True,
        requires_kyb=True,
        has_compliance_requirements=True
    ),
    
    # ========== CONSUMERS (BUY services) ==========
    
    # CORPORATE (like Windsurf.io): They BUY services for events
    OrganizationType.CORPORATE: OrganizationCapabilities(
        provider=ProviderCapabilities(),  # No provider capabilities
        consumer=ConsumerCapabilities(
            needs_event_creation=True,      # ← Create events in Uganda
            needs_venue_booking=True,       # ← Book venues for events
            needs_ticket_purchasing=True,   # ← Sell tickets to event
            needs_hotel_booking=True,       # ← Book hotels for staff/attendees
            needs_transport_booking=True,   # ← Book transport
            needs_payment_processing=True,  # ← Process payments
            needs_wallet_for_payments=True  # ← Use platform wallet
        ),
        can_manage_staff=True,
        can_manage_finance=True,
        can_view_analytics=True,
        requires_kyb=False,  # Consumer, less strict
        has_compliance_requirements=False
    ),
    
    # NATIONAL FOOTBALL TEAM: They NEED services for away games
    OrganizationType.FOOTBALL_TEAM: OrganizationCapabilities(
        provider=ProviderCapabilities(),  # They don't sell services
        consumer=ConsumerCapabilities(
            needs_event_creation=True,      # ← Create match events
            needs_venue_booking=True,       # ← Book stadium for home games
            needs_hotel_booking=True,       # ← Book hotels for team when away
            needs_transport_booking=True,   # ← Book team buses
            needs_ticket_purchasing=False,  # Usually federation handles this
            needs_payment_processing=True   # Pay for services
        ),
        can_manage_staff=True,   # Manage players, coaches
        can_manage_finance=True,
        can_view_analytics=True,
        requires_kyb=False,
        has_compliance_requirements=True  # FIFA regulations
    ),
    
    # SPORTS_TEAM: Can be hybrid
    OrganizationType.SPORTS_TEAM: OrganizationCapabilities(
        provider=ProviderCapabilities(
            provides_venue_rental=True,     # Rent out their stadium
            provides_event_management=True  # Host events
        ),
        consumer=ConsumerCapabilities(
            needs_transport_booking=True,   # For away games
            needs_hotel_booking=True,       # For away games
        ),
        can_manage_staff=True,
        can_manage_finance=True,
        can_view_analytics=True,
        requires_kyb=False,
        has_compliance_requirements=False
    ),
    
    # ========== HYBRID EXAMPLE ==========
    
    # TRAVEL_AGENCY: Sells tours (provider) + books hotels/transport (consumer)
    OrganizationType.TRAVEL_AGENCY: OrganizationCapabilities(
        provider=ProviderCapabilities(
            provides_tour_guides=True,
            provides_transport=True,
            provides_event_management=True
        ),
        consumer=ConsumerCapabilities(
            needs_hotel_booking=True,       # Book hotels for clients
            needs_transport_booking=True,   # Book transport for clients
            needs_venue_booking=True,       # Book venues for events
        ),
        can_manage_staff=True,
        can_manage_finance=True,
        can_view_analytics=True,
        requires_kyb=True,
        has_compliance_requirements=True
    ),
    
    # GOVERNMENT: Primarily consumer
    OrganizationType.GOVERNMENT: OrganizationCapabilities(
        provider=ProviderCapabilities(),  # Generally don't sell services
        consumer=ConsumerCapabilities(
            needs_event_creation=True,      # Government events
            needs_venue_booking=True,       # Book venues for events
            needs_transport_booking=True,   # Transport for officials
            needs_payment_processing=True,   # Process payments
        ),
        can_manage_staff=True,
        can_manage_finance=True,
        can_view_analytics=True,
        requires_kyb=True,
        has_compliance_requirements=True
    ),
    
    # NGO: Primarily consumer
    OrganizationType.NGO: OrganizationCapabilities(
        provider=ProviderCapabilities(),  # Generally don't sell services
        consumer=ConsumerCapabilities(
            needs_event_creation=True,      # Charity events
            needs_venue_booking=True,       # Book venues for events
            needs_transport_booking=True,   # Transport for volunteers
            needs_payment_processing=True,   # Process donations
        ),
        can_manage_staff=True,
        can_manage_finance=True,
        can_view_analytics=True,
        requires_kyb=False,
        has_compliance_requirements=False
    ),
}

# Legacy OrganizationCapability mappings for backward compatibility
ORGANIZATION_CAPABILITIES: Dict[OrganizationType, OrganizationCapability] = {
    
    # Hospitality & Tourism
    OrganizationType.HOTEL: OrganizationCapability(
        can_manage_accommodation=True,
        can_manage_staff=True,
        can_process_payments=True,
        can_manage_inventory=True,
        can_provide_services=True,
        requires_license=True,
        integrates_with_accommodation=True,
        integrates_with_wallet=True
    ),
    
    OrganizationType.RESTAURANT: OrganizationCapability(
        can_manage_staff=True,
        can_process_payments=True,
        can_manage_inventory=True,
        can_provide_services=True,
        requires_license=True,
        integrates_with_wallet=True
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
        integrates_with_wallet=True
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
        integrates_with_wallet=True
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
        integrates_with_wallet=True
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
        integrates_with_wallet=True
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
        integrates_with_wallet=True
    ),
    
    # Transportation
    OrganizationType.TRANSPORT_COMPANY: OrganizationCapability(
        can_manage_staff=True,
        can_manage_transport=True,
        can_process_payments=True,
        requires_license=True,
        requires_insurance=True,
        integrates_with_transport=True,
        integrates_with_wallet=True
    ),
    
    OrganizationType.BUS_OPERATOR: OrganizationCapability(
        can_manage_staff=True,
        can_manage_transport=True,
        can_sell_tickets=True,
        can_process_payments=True,
        requires_license=True,
        requires_insurance=True,
        integrates_with_transport=True,
        integrates_with_wallet=True
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
        integrates_with_wallet=True
    ),
    
    # Government & NGOs
    OrganizationType.GOVERNMENT: OrganizationCapability(
        can_manage_staff=True,
        can_create_events=True,
        requires_license=True,
        integrates_with_events=True,
        integrates_with_wallet=True
    ),
    
    OrganizationType.NGO: OrganizationCapability(
        can_manage_staff=True,
        can_create_events=True,
        can_process_payments=True,
        requires_license=True,
        integrates_with_events=True,
        integrates_with_wallet=True
    ),
}


class OrganizationRole(Enum):
    """Organization-specific roles"""
    
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


# Role permissions mapping
ROLE_PERMISSIONS: Dict[OrganizationRole, List[str]] = {
    
    OrganizationRole.ORG_OWNER: [
        "org.full_control", "org.manage_settings", "org.manage_staff",
        "org.manage_wallet", "org.create_events", "org.manage_accommodation",
        "org.manage_transport", "org.manage_tourism", "org.view_reports",
        "org.delete_org"
    ],
    
    OrganizationRole.ORG_ADMIN: [
        "org.manage_settings", "org.manage_staff", "org.manage_wallet",
        "org.create_events", "org.manage_accommodation", "org.manage_transport",
        "org.manage_tourism", "org.view_reports"
    ],
    
    OrganizationRole.ORG_MANAGER: [
        "org.manage_staff", "org.create_events", "org.manage_wallet",
        "org.view_reports"
    ],
    
    OrganizationRole.OPERATIONS_MANAGER: [
        "org.manage_operations", "org.manage_transport", "org.manage_accommodation",
        "org.view_reports"
    ],
    
    OrganizationRole.FINANCE_MANAGER: [
        "org.manage_wallet", "org.view_financial_reports", "org.process_payments"
    ],
    
    OrganizationRole.HR_MANAGER: [
        "org.manage_staff", "org.view_staff_reports"
    ],
    
    OrganizationRole.EVENT_MANAGER: [
        "org.create_events", "org.manage_events", "org.sell_tickets"
    ],
    
    OrganizationRole.TRANSPORT_MANAGER: [
        "org.manage_transport", "org.manage_fleet", "org.schedule_transport"
    ],
    
    OrganizationRole.ACCOMMODATION_MANAGER: [
        "org.manage_accommodation", "org.manage_bookings", "org.manage_rooms"
    ],
    
    OrganizationRole.TOURISM_MANAGER: [
        "org.manage_tourism", "org.create_tours", "org.manage_tourism_bookings"
    ],
    
    OrganizationRole.STAFF_MEMBER: [
        "org.view_basic_info", "org.perform_assigned_tasks"
    ],
    
    OrganizationRole.AGENT: [
        "org.sell_tickets", "org.manage_bookings", "org.process_payments"
    ],
    
    OrganizationRole.VIEWER: [
        "org.view_basic_info"
    ],
    
    OrganizationRole.GUEST: [
        "org.view_public_info"
    ]
}


def get_organization_capabilities(org_type: OrganizationType) -> OrganizationCapability:
    """Get legacy capabilities for an organization type (backward compatibility)"""
    return ORGANIZATION_CAPABILITIES.get(org_type, OrganizationCapability())


def get_dual_organization_capabilities(org_type: OrganizationType) -> OrganizationCapabilities:
    """Get dual capabilities for an organization type"""
    return DUAL_ORGANIZATION_CAPABILITIES.get(org_type, OrganizationCapabilities())


def can_provide_service(org_type: OrganizationType, service: str) -> bool:
    """Check if organization type can PROVIDE a specific service"""
    caps = get_dual_organization_capabilities(org_type)
    return getattr(caps.provider, f"provides_{service}", False)


def can_consume_service(org_type: OrganizationType, service: str) -> bool:
    """Check if organization type can CONSUME a specific service"""
    caps = get_dual_organization_capabilities(org_type)
    return getattr(caps.consumer, f"needs_{service}", False)


def get_role_permissions(role: OrganizationRole) -> List[str]:
    """Get permissions for an organization role"""
    return ROLE_PERMISSIONS.get(role, [])


def get_available_roles(org_type: OrganizationType) -> List[OrganizationRole]:
    """Get available roles for an organization type"""
    base_roles = [
        OrganizationRole.ORG_OWNER,
        OrganizationRole.ORG_ADMIN,
        OrganizationRole.STAFF_MEMBER,
        OrganizationRole.VIEWER
    ]
    
    # Add specialized roles based on organization type
    if org_type in [OrganizationType.SPORTS_TEAM, OrganizationType.EVENT_MANAGEMENT, OrganizationType.FOOTBALL_TEAM]:
        base_roles.extend([OrganizationRole.EVENT_MANAGER])
    
    if org_type in [OrganizationType.TRANSPORT_COMPANY, OrganizationType.BUS_OPERATOR]:
        base_roles.extend([OrganizationRole.TRANSPORT_MANAGER])
    
    if org_type in [OrganizationType.HOTEL, OrganizationType.ACCOMMODATION_PROVIDER]:
        base_roles.extend([OrganizationRole.ACCOMMODATION_MANAGER])
    
    if org_type in [OrganizationType.TOUR_OPERATOR, OrganizationType.TRAVEL_AGENCY]:
        base_roles.extend([OrganizationRole.TOURISM_MANAGER])
    
    return list(set(base_roles))  # Remove duplicates
