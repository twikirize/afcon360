# app/identity/services/organization_registration.py
"""
Organization Registration Service
Handles comprehensive organization registration with type-specific requirements
"""

from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from flask import current_app
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.identity.models.organisation import Organisation
from app.identity.models.organisation_member import OrganisationMember
from app.identity.models.organization_types import OrganizationType, get_available_roles, get_organization_capabilities
from app.identity.models.user import User
from app.wallet.models.ledger import AccountModel, AccountOwnerType
from app.wallet.services.wallet_service import WalletService


class OrganizationRegistrationService:
    """Service for registering new organizations"""
    
    @staticmethod
    def validate_registration_data(data: Dict[str, Any], org_settings: Dict[str, Any] = None) -> tuple[bool, List[str]]:
        """Validate organization registration data"""
        errors = []
        
        # Check if simplified registration mode is enabled
        is_testing_mode = org_settings and org_settings.get('registration_mode') == 'testing'
        kyc_enabled = org_settings and org_settings.get('kyc_enabled', False)
        
        if is_testing_mode or not kyc_enabled:
            # Simplified requirements for testing mode
            required_fields = ['legal_name', 'org_type', 'contact_email']
        else:
            # Full requirements for standard mode
            required_fields = ['legal_name', 'org_type', 'country', 'contact_email']
        
        for field in required_fields:
            if not data.get(field):
                errors.append(f"{field.replace('_', ' ').title()} is required")
        
        # Email validation
        if data.get('contact_email') and '@' not in data['contact_email']:
            errors.append("Invalid email format")
        
        # Organization type validation
        try:
            org_type = OrganizationType(data['org_type'])
        except ValueError:
            errors.append("Invalid organization type")
        
        # Phone validation (if provided)
        phone = data.get('contact_phone')
        if phone and not phone.replace('+', '').replace('-', '').replace(' ', '').isdigit():
            errors.append("Invalid phone number format")
        
        # Website validation (if provided)
        website = data.get('website')
        if website and not (website.startswith('http://') or website.startswith('https://')):
            errors.append("Website must start with http:// or https://")
        
        return len(errors) == 0, errors
    
    @staticmethod
    def check_type_requirements(org_type: OrganizationType) -> Dict[str, Any]:
        """Check requirements for specific organization type"""
        capabilities = get_organization_capabilities(org_type)
        
        requirements = {
            'requires_license': capabilities.requires_license,
            'requires_insurance': capabilities.requires_insurance,
            'requires_certification': capabilities.requires_certification,
            'required_documents': [],
            'setup_steps': []
        }
        
        # Add type-specific requirements
        if org_type == OrganizationType.SPORTS_TEAM:
            requirements['required_documents'].extend([
                'sports_federation_registration',
                'team_roster',
                'insurance_certificate'
            ])
            requirements['setup_steps'].extend([
                'register_with_sports_federation',
                'setup_team_management',
                'configure_event_participation'
            ])
        
        elif org_type == OrganizationType.HOTEL:
            requirements['required_documents'].extend([
                'hospitality_license',
                'health_safety_certificate',
                'fire_safety_certificate'
            ])
            requirements['setup_steps'].extend([
                'configure_room_types',
                'setup_booking_system',
                'initialize_pricing'
            ])
        
        elif org_type == OrganizationType.TRANSPORT_COMPANY:
            requirements['required_documents'].extend([
                'transport_license',
                'vehicle_registration',
                'insurance_certificate',
                'driver_certifications'
            ])
            requirements['setup_steps'].extend([
                'register_fleet',
                'setup_scheduling_system',
                'configure_pricing'
            ])
        
        elif org_type == OrganizationType.EVENT_MANAGEMENT:
            requirements['required_documents'].extend([
                'event_management_license',
                'insurance_certificate',
                'venue_contracts'
            ])
            requirements['setup_steps'].extend([
                'setup_event_templates',
                'configure_ticketing',
                'initialize_payment_system'
            ])
        
        return requirements
    
    @staticmethod
    def create_organization(data: Dict[str, Any], creator_user: User, org_settings: Dict[str, Any] = None) -> tuple[Optional[Organisation], List[str]]:
        """Create a new organization"""
        # Validate data
        is_valid, errors = OrganizationRegistrationService.validate_registration_data(data, org_settings)
        if not is_valid:
            return None, errors
        
        try:
            # Create organization
            org = Organisation(
                org_id=OrganizationRegistrationService.generate_org_id(),
                legal_name=data['legal_name'],
                org_type=data.get('org_type', 'merchant'),
                business_category=OrganizationType(data['org_type']),
                country=data['country'],
                region=data.get('region', ''),
                contact_email=data['contact_email'],
                contact_phone=data.get('contact_phone'),
                headquarters_address=data.get('headquarters_address', ''),
                website=data.get('website', ''),
                registration_no=data.get('registration_no', ''),
                tax_id=data.get('tax_id', ''),
                vat_number=data.get('vat_number', ''),
                verification_status='pending',
                lifecycle_state='registered',
                is_active=True,
                is_operational=False
            )
            
            # Set organization-specific settings
            org.set_setting('registration_date', datetime.now(timezone.utc).isoformat())
            org.set_setting('creator_user_id', creator_user.id)
            org.set_setting('setup_completed', False)
            
            # Set KYC settings (use provided settings or defaults)
            if org_settings:
                org.set_setting('kyc_enabled', org_settings.get('kyc_enabled', False))
                org.set_setting('kyc_strict', org_settings.get('kyc_strict', False))
                org.set_setting('kyc_auto_approve', org_settings.get('kyc_auto_approve', True))
                org.set_setting('default_kyc_level', org_settings.get('default_kyc_level', 0))
                org.set_setting('max_kyc_level', org_settings.get('max_kyc_level', 3))
                org.set_setting('registration_mode', org_settings.get('registration_mode', 'testing'))
                org.set_setting('kyc_require_identity', org_settings.get('kyc_require_identity', True))
                org.set_setting('kyc_require_address', org_settings.get('kyc_require_address', False))
                org.set_setting('kyc_require_business', org_settings.get('kyc_require_business', False))
                org.set_setting('kyc_require_financial', org_settings.get('kyc_require_financial', False))
            else:
                # Default settings for testing mode
                org.set_setting('kyc_enabled', False)
                org.set_setting('kyc_strict', False)
                org.set_setting('kyc_auto_approve', True)
                org.set_setting('default_kyc_level', 0)
                org.set_setting('max_kyc_level', 3)
                org.set_setting('registration_mode', 'testing')
                org.set_setting('kyc_require_identity', False)
                org.set_setting('kyc_require_address', False)
                org.set_setting('kyc_require_business', False)
                org.set_setting('kyc_require_financial', False)
            
            db.session.add(org)
            db.session.flush()  # Get org ID without committing
            
            # Add creator as organization owner
            OrganizationRegistrationService.add_org_member(
                org, creator_user, 'org_owner'
            )
            
            # Create wallet account for organization
            OrganizationRegistrationService.create_org_wallet(org)
            
            # Send for verification if required
            if org.requires_license():
                OrganizationRegistrationService.initiate_verification(org)
            
            db.session.commit()
            
            return org, []
            
        except IntegrityError as e:
            db.session.rollback()
            current_app.logger.error(f"Organization creation failed: {e}")
            return None, ["Organization with this details already exists"]
        
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Organization creation error: {e}")
            return None, ["An error occurred during organization creation"]
    
    @staticmethod
    def generate_org_id() -> str:
        """Generate unique organization ID"""
        import uuid
        return f"ORG-{uuid.uuid4().hex[:12].upper()}"
    
    @staticmethod
    def add_org_member(org: Organisation, user: User, role_name: str) -> OrganisationMember:
        """Add a member to organization with specified role"""
        from app.identity.models.organisation_member import OrganisationMember
        from app.identity.models.organisation import OrgRole
        
        # Get role
        role = OrgRole.query.filter_by(name=role_name).first()
        if not role:
            raise ValueError(f"Role '{role_name}' not found")
        
        # Create membership
        member = OrganisationMember(
            organisation_id=org.id,
            user_id=user.id,
            org_role_id=role.id,
            is_active=True,
            is_deleted=False
        )
        
        db.session.add(member)
        return member
    
    @staticmethod
    def create_org_wallet(org: Organisation) -> AccountModel:
        """Create wallet account for organization"""
        from app.wallet.models.ledger import AccountModel, AccountOwnerType
        
        account = AccountModel(
            user_id=org.id,
            owner_type=AccountOwnerType.ORGANISATION,
            account_name=f"{org.legal_name} Wallet",
            currency='UGX',  # Default to Ugandan Shillings
            is_active=True
        )
        
        db.session.add(account)
        return account
    
    @staticmethod
    def initiate_verification(org: Organisation) -> None:
        """Initiate organization verification process"""
        from app.identity.models.organisation import OrganisationVerification
        
        verification = OrganisationVerification(
            organisation_id=org.id,
            verification_type='business_registration',
            status='pending',
            requested_at=datetime.now(timezone.utc)
        )
        
        db.session.add(verification)
    
    @staticmethod
    def get_registration_form_config(org_type: Optional[str] = None) -> Dict[str, Any]:
        """Get registration form configuration"""
        config = {
            'organization_types': [
                {
                    'value': org_type.value,
                    'label': org_type.value.replace('_', ' ').title(),
                    'description': OrganizationRegistrationService.get_type_description(org_type),
                    'category': OrganizationRegistrationService.get_type_category(org_type)
                }
                for org_type in OrganizationType
            ],
            'countries': [
                {'value': 'UG', 'label': 'Uganda'},
                {'value': 'KE', 'label': 'Kenya'},
                {'value': 'TZ', 'label': 'Tanzania'},
                {'value': 'RW', 'label': 'Rwanda'},
                {'value': 'BI', 'label': 'Burundi'},
                {'value': 'SS', 'label': 'South Sudan'},
            ],
            'form_fields': [
                {
                    'name': 'legal_name',
                    'label': 'Legal Name',
                    'type': 'text',
                    'required': True,
                    'placeholder': 'Enter official organization name'
                },
                {
                    'name': 'org_type',
                    'label': 'Organization Type',
                    'type': 'select',
                    'required': True,
                    'options': 'organization_types'
                },
                {
                    'name': 'country',
                    'label': 'Country',
                    'type': 'select',
                    'required': True,
                    'options': 'countries'
                },
                {
                    'name': 'region',
                    'label': 'Region/State',
                    'type': 'text',
                    'required': False,
                    'placeholder': 'Enter region or state'
                },
                {
                    'name': 'contact_email',
                    'label': 'Contact Email',
                    'type': 'email',
                    'required': True,
                    'placeholder': 'organization@example.com'
                },
                {
                    'name': 'contact_phone',
                    'label': 'Contact Phone',
                    'type': 'tel',
                    'required': False,
                    'placeholder': '+256 123 456 789'
                },
                {
                    'name': 'headquarters_address',
                    'label': 'Headquarters Address',
                    'type': 'textarea',
                    'required': False,
                    'placeholder': 'Enter full address'
                },
                {
                    'name': 'website',
                    'label': 'Website',
                    'type': 'url',
                    'required': False,
                    'placeholder': 'https://www.example.com'
                },
                {
                    'name': 'registration_no',
                    'label': 'Registration Number',
                    'type': 'text',
                    'required': False,
                    'placeholder': 'Business registration number'
                },
                {
                    'name': 'tax_id',
                    'label': 'Tax ID',
                    'type': 'text',
                    'required': False,
                    'placeholder': 'Tax identification number'
                },
                {
                    'name': 'vat_number',
                    'label': 'VAT Number',
                    'type': 'text',
                    'required': False,
                    'placeholder': 'VAT registration number'
                }
            ]
        }
        
        if org_type:
            try:
                org_type_enum = OrganizationType(org_type)
                config['requirements'] = OrganizationRegistrationService.check_type_requirements(org_type_enum)
                config['available_roles'] = [
                    {
                        'value': role.value,
                        'label': role.value.replace('_', ' ').title()
                    }
                    for role in get_available_roles(org_type_enum)
                ]
            except ValueError:
                pass
        
        return config
    
    @staticmethod
    def get_type_description(org_type: OrganizationType) -> str:
        """Get description for organization type"""
        descriptions = {
            OrganizationType.HOTEL: "Hotel and accommodation provider",
            OrganizationType.RESTAURANT: "Restaurant and food service provider",
            OrganizationType.TOUR_OPERATOR: "Tour operator and travel packages",
            OrganizationType.TRAVEL_AGENCY: "Travel agency and booking services",
            OrganizationType.EVENT_MANAGEMENT: "Event management and planning services",
            OrganizationType.CONFERENCE_CENTER: "Conference center and venue provider",
            OrganizationType.SPORTS_TEAM: "Sports team and athletic organization",
            OrganizationType.SPORTS_FEDERATION: "Sports federation and governing body",
            OrganizationType.TRANSPORT_COMPANY: "Transportation and logistics company",
            OrganizationType.BUS_OPERATOR: "Bus and coach operator",
            OrganizationType.AIRLINE: "Airline and aviation services",
            OrganizationType.CORPORATE: "Corporate business entity",
            OrganizationType.GOVERNMENT: "Government organization",
            OrganizationType.NGO: "Non-governmental organization",
            OrganizationType.EDUCATIONAL_INSTITUTION: "School, college, or university",
            OrganizationType.MEDIA_COMPANY: "Media and entertainment company",
        }
        return descriptions.get(org_type, "Business organization")
    
    @staticmethod
    def get_type_category(org_type: OrganizationType) -> str:
        """Get category for organization type"""
        categories = {
            # Hospitality
            OrganizationType.HOTEL: "Hospitality",
            OrganizationType.RESTAURANT: "Hospitality",
            OrganizationType.ACCOMMODATION_PROVIDER: "Hospitality",
            OrganizationType.HOSTEL: "Hospitality",
            OrganizationType.VACATION_RENTAL: "Hospitality",
            
            # Tourism
            OrganizationType.TOUR_OPERATOR: "Tourism",
            OrganizationType.TRAVEL_AGENCY: "Tourism",
            OrganizationType.TOURISM_BOARD: "Tourism",
            
            # Events
            OrganizationType.EVENT_MANAGEMENT: "Events",
            OrganizationType.CONFERENCE_CENTER: "Events",
            OrganizationType.VENUE_OPERATOR: "Events",
            OrganizationType.EXHIBITION_ORG: "Events",
            
            # Sports
            OrganizationType.SPORTS_TEAM: "Sports",
            OrganizationType.SPORTS_FEDERATION: "Sports",
            OrganizationType.FITNESS_CENTER: "Sports",
            OrganizationType.RECREATION_FACILITY: "Sports",
            
            # Transportation
            OrganizationType.TRANSPORT_COMPANY: "Transportation",
            OrganizationType.AIRLINE: "Transportation",
            OrganizationType.BUS_OPERATOR: "Transportation",
            OrganizationType.TAXI_SERVICE: "Transportation",
            OrganizationType.CAR_RENTAL: "Transportation",
            
            # Business
            OrganizationType.CORPORATE: "Business",
            OrganizationType.CONSULTING_FIRM: "Business",
            OrganizationType.MARKETING_AGENCY: "Business",
            OrganizationType.IT_SERVICES: "Business",
            
            # Institutions
            OrganizationType.GOVERNMENT: "Institutions",
            OrganizationType.NGO: "Institutions",
            OrganizationType.EDUCATIONAL_INSTITUTION: "Institutions",
            OrganizationType.HEALTHCARE_PROVIDER: "Institutions",
            
            # Financial
            OrganizationType.BANK: "Financial",
            OrganizationType.INSURANCE_COMPANY: "Financial",
            OrganizationType.INVESTMENT_FIRM: "Financial",
            OrganizationType.FINTECH: "Financial",
            
            # Media
            OrganizationType.MEDIA_COMPANY: "Media",
            OrganizationType.BROADCASTING: "Media",
            OrganizationType.ENTERTAINMENT: "Media",
            OrganizationType.PUBLISHING: "Media",
        }
        return categories.get(org_type, "Other")
