# app/forms/organization_forms.py
"""
Organization registration and management forms
"""

from flask_wtf import FlaskForm
from wtforms import (
    StringField, SelectField, TextAreaField, URLField, TelField,
    BooleanField, HiddenField, FieldList, FormField
)
from wtforms.validators import (
    DataRequired, Email, Optional, URL, Length, Regexp
)
from app.identity.models.organization_types import OrganizationType


class OrganizationRegistrationForm(FlaskForm):
    """Main organization registration form"""
    
    # Basic Information
    legal_name = StringField('Legal Name', validators=[
        DataRequired(message='Legal name is required'),
        Length(min=3, max=255, message='Legal name must be between 3 and 255 characters')
    ])
    
    org_type = SelectField('Organization Type', coerce=str, validators=[
        DataRequired(message='Organization type is required')
    ])
    
    country = SelectField('Country', coerce=str, validators=[
        DataRequired(message='Country is required')
    ])
    
    region = StringField('Region/State', validators=[
        Optional(),
        Length(max=128, message='Region must be less than 128 characters')
    ])
    
    # Contact Information
    contact_email = StringField('Contact Email', validators=[
        DataRequired(message='Contact email is required'),
        Email(message='Please enter a valid email address'),
        Length(max=255, message='Email must be less than 255 characters')
    ])
    
    contact_phone = TelField('Contact Phone', validators=[
        Optional(),
        Regexp(r'^\+?[\d\s\-\(\)]+$', message='Please enter a valid phone number'),
        Length(max=32, message='Phone number must be less than 32 characters')
    ])
    
    headquarters_address = TextAreaField('Headquarters Address', validators=[
        Optional(),
        Length(max=1000, message='Address must be less than 1000 characters')
    ])
    
    website = URLField('Website', validators=[
        Optional(),
        URL(message='Please enter a valid URL'),
        Length(max=255, message='Website must be less than 255 characters')
    ])
    
    # Business Information
    registration_no = StringField('Registration Number', validators=[
        Optional(),
        Length(max=128, message='Registration number must be less than 128 characters')
    ])
    
    tax_id = StringField('Tax ID', validators=[
        Optional(),
        Length(max=64, message='Tax ID must be less than 64 characters')
    ])
    
    vat_number = StringField('VAT Number', validators=[
        Optional(),
        Length(max=64, message='VAT number must be less than 64 characters')
    ])
    
    # Terms and Conditions
    agree_terms = BooleanField('I agree to the terms and conditions', validators=[
        DataRequired(message='You must agree to the terms and conditions')
    ])
    
    agree_privacy = BooleanField('I agree to the privacy policy', validators=[
        DataRequired(message='You must agree to the privacy policy')
    ])
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Populate organization type choices
        self.org_type.choices = [
            (org_type.value, org_type.value.replace('_', ' ').title())
            for org_type in OrganizationType
        ]
        
        # Populate country choices
        self.country.choices = [
            ('UG', 'Uganda'),
            ('KE', 'Kenya'),
            ('TZ', 'Tanzania'),
            ('RW', 'Rwanda'),
            ('BI', 'Burundi'),
            ('SS', 'South Sudan'),
        ]


class OrganizationSettingsForm(FlaskForm):
    """Organization settings form"""
    
    # Basic Settings
    legal_name = StringField('Legal Name', validators=[
        DataRequired(),
        Length(min=3, max=255)
    ])
    
    contact_email = StringField('Contact Email', validators=[
        DataRequired(),
        Email(),
        Length(max=255)
    ])
    
    contact_phone = TelField('Contact Phone', validators=[
        Optional(),
        Regexp(r'^\+?[\d\s\-\(\)]+$'),
        Length(max=32)
    ])
    
    headquarters_address = TextAreaField('Headquarters Address', validators=[
        Optional(),
        Length(max=1000)
    ])
    
    website = URLField('Website', validators=[
        Optional(),
        URL(),
        Length(max=255)
    ])
    
    # Business Settings
    business_description = TextAreaField('Business Description', validators=[
        Optional(),
        Length(max=2000)
    ])
    
    # Notification Settings
    email_notifications = BooleanField('Email Notifications')
    sms_notifications = BooleanField('SMS Notifications')
    
    # Privacy Settings
    public_profile = BooleanField('Make organization profile public')
    allow_member_invites = BooleanField('Allow members to invite others')


class OrganizationMemberForm(FlaskForm):
    """Form for adding organization members"""
    
    user_email = StringField('User Email', validators=[
        DataRequired(),
        Email()
    ])
    
    role = SelectField('Role', coerce=str, validators=[
        DataRequired()
    ])
    
    send_invite = BooleanField('Send invitation email', default=True)
    
    def __init__(self, organization_type=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set role choices based on organization type
        if organization_type:
            from app.identity.models.organization_types import get_available_roles
            available_roles = get_available_roles(organization_type)
            self.role.choices = [
                (role.value, role.value.replace('_', ' ').title())
                for role in available_roles
            ]
        else:
            # Default roles
            self.role.choices = [
                ('staff_member', 'Staff Member'),
                ('agent', 'Agent'),
                ('viewer', 'Viewer')
            ]


class OrganizationDocumentForm(FlaskForm):
    """Form for uploading organization documents"""
    
    document_type = SelectField('Document Type', coerce=str, validators=[
        DataRequired()
    ])
    
    document_number = StringField('Document Number', validators=[
        Optional(),
        Length(max=128)
    ])
    
    issuing_authority = StringField('Issuing Authority', validators=[
        Optional(),
        Length(max=255)
    ])
    
    issue_date = StringField('Issue Date', validators=[
        Optional()
    ])
    
    expiry_date = StringField('Expiry Date', validators=[
        Optional()
    ])
    
    def __init__(self, organization_type=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set document type choices based on organization type
        document_types = [
            ('business_registration', 'Business Registration'),
            ('tax_certificate', 'Tax Certificate'),
            ('vat_certificate', 'VAT Certificate'),
            ('insurance_certificate', 'Insurance Certificate'),
            ('license', 'License'),
            ('permit', 'Permit'),
            ('certificate', 'Certificate'),
            ('other', 'Other')
        ]
        
        # Add type-specific documents
        if organization_type:
            from app.identity.models.organization_types import OrganizationType
            
            if organization_type == OrganizationType.SPORTS_TEAM:
                document_types.extend([
                    ('sports_federation_registration', 'Sports Federation Registration'),
                    ('team_roster', 'Team Roster'),
                    ('player_contracts', 'Player Contracts')
                ])
            elif organization_type == OrganizationType.HOTEL:
                document_types.extend([
                    ('hospitality_license', 'Hospitality License'),
                    ('health_safety_certificate', 'Health & Safety Certificate'),
                    ('fire_safety_certificate', 'Fire Safety Certificate'),
                    ('food_handling_certificate', 'Food Handling Certificate')
                ])
            elif organization_type == OrganizationType.TRANSPORT_COMPANY:
                document_types.extend([
                    ('transport_license', 'Transport License'),
                    ('vehicle_registration', 'Vehicle Registration'),
                    ('driver_certifications', 'Driver Certifications'),
                    ('road_worthiness_certificate', 'Road Worthiness Certificate')
                ])
            elif organization_type == OrganizationType.EVENT_MANAGEMENT:
                document_types.extend([
                    ('event_management_license', 'Event Management License'),
                    ('venue_contracts', 'Venue Contracts'),
                    ('event_permits', 'Event Permits')
                ])
        
        self.document_type.choices = document_types


class OrganizationWalletForm(FlaskForm):
    """Form for organization wallet settings"""
    
    default_currency = SelectField('Default Currency', coerce=str, validators=[
        DataRequired()
    ])
    
    auto_settlement = BooleanField('Enable Automatic Settlement')
    
    settlement_frequency = SelectField('Settlement Frequency', coerce=str, validators=[
        Optional()
    ])
    
    require_approval_for_large_transactions = BooleanField('Require Approval for Large Transactions')
    
    large_transaction_threshold = StringField('Large Transaction Threshold', validators=[
        Optional()
    ])
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Currency choices
        self.default_currency.choices = [
            ('UGX', 'Ugandan Shillings (UGX)'),
            ('KES', 'Kenyan Shillings (KES)'),
            ('TZS', 'Tanzanian Shillings (TZS)'),
            ('RWF', 'Rwandan Francs (RWF)'),
            ('USD', 'US Dollars (USD)'),
            ('EUR', 'Euros (EUR)'),
        ]
        
        # Settlement frequency choices
        self.settlement_frequency.choices = [
            ('daily', 'Daily'),
            ('weekly', 'Weekly'),
            ('monthly', 'Monthly'),
            ('quarterly', 'Quarterly')
        ]


class OrganizationEventForm(FlaskForm):
    """Form for creating organization events"""
    
    name = StringField('Event Name', validators=[
        DataRequired(),
        Length(min=3, max=255)
    ])
    
    description = TextAreaField('Event Description', validators=[
        Optional(),
        Length(max=2000)
    ])
    
    event_type = SelectField('Event Type', coerce=str, validators=[
        DataRequired()
    ])
    
    start_date = StringField('Start Date', validators=[
        DataRequired()
    ])
    
    end_date = StringField('End Date', validators=[
        DataRequired()
    ])
    
    venue = StringField('Venue', validators=[
        Optional(),
        Length(max=255)
    ])
    
    max_attendees = StringField('Maximum Attendees', validators=[
        Optional()
    ])
    
    ticket_price = StringField('Ticket Price', validators=[
        Optional()
    ])
    
    is_public = BooleanField('Public Event', default=True)
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Event type choices
        self.event_type.choices = [
            ('conference', 'Conference'),
            ('meeting', 'Meeting'),
            ('workshop', 'Workshop'),
            ('seminar', 'Seminar'),
            ('training', 'Training'),
            ('competition', 'Competition'),
            ('tournament', 'Tournament'),
            ('exhibition', 'Exhibition'),
            ('concert', 'Concert'),
            ('festival', 'Festival'),
            ('celebration', 'Celebration'),
            ('other', 'Other')
        ]
