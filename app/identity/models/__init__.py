#app/identity/models/__init__.py
from .user import User, UserRole, MFASecret, Session, APIKey
from .organisation import Organisation
from .organisation_provider_capability import OrganisationProviderCapability, ProviderCapabilityCode, ProviderCapabilityStatus
from .provider_participation import ProviderParticipation
from .organisation_member import OrganisationMember, OrgUserRole, OrgRole
from .organisation_controller import OrganisationController
from .licence_document import OrganisationLicense, OrganisationDocument, OrganisationAuditLog
from .roles_permission import Role, Permission, RolePermission
from .kyb import OrganisationVerification, OrganisationKYBCheck, OrganisationUBO, OrganisationKYBDocument
from .compliance_audit_log import ComplianceAuditLog
from .compliance_settings import ComplianceSettings
# Import UserProfile to resolve SQLAlchemy Mapper error
from app.profile.models import UserProfile
# Import Individual Verification to resolve SQLAlchemy Mapper error
from app.identity.individuals.individual_verification import IndividualVerification

# Fan profile extension (user-activated, not a role)
from app.fan.models import FanProfile, UserDashboardContext

__all__ = [

    "User", "UserRole", "MFASecret", "Session", "APIKey",
    "Organisation", "OrganisationMember", "OrgUserRole", "OrgRole", "OrganisationController",
    "OrganisationProviderCapability", "ProviderCapabilityCode", "ProviderCapabilityStatus",
    "ProviderParticipation",
    "OrganisationLicense", "OrganisationDocument", "OrganisationAuditLog",
    "Role", "Permission", "RolePermission",
    "OrganisationVerification", "OrganisationKYBCheck", "OrganisationUBO", "OrganisationKYBDocument",
    "ComplianceAuditLog", "ComplianceSettings",
    "UserProfile", "IndividualVerification",
]
