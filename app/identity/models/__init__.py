#app/identity/models/__init__.py
from .user import User, UserRole, MFASecret, Session, APIKey
from .organisation import Organisation
from .organisation_member import OrganisationMember, OrgUserRole, OrgRole
from .organisation_controller import OrganisationController
from .licence_document import OrganisationLicense, OrganisationDocument, OrganisationAuditLog
from .roles_permission import Role, Permission, RolePermission
from .compliance_settings import ComplianceSettings
from .compliance_audit_log import ComplianceAuditLog
from .kyb import OrganisationVerification, OrganisationKYBCheck, OrganisationUBO, OrganisationKYBDocument
# Import UserProfile to resolve SQLAlchemy Mapper error
from app.profile.models import UserProfile
# Import IndividualVerification to resolve SQLAlchemy Mapper error
from app.identity.individuals.individual_verification import IndividualVerification

__all__ = [
    "User", "UserRole", "MFASecret", "Session", "APIKey",
    "Organisation", "OrganisationMember", "OrgUserRole", "OrgRole", "OrganisationController",
    "OrganisationLicense", "OrganisationDocument", "OrganisationAuditLog",
    "Role", "Permission", "RolePermission",
    "ComplianceSettings", "ComplianceAuditLog",
    "OrganisationVerification", "OrganisationKYBCheck", "OrganisationUBO", "OrganisationKYBDocument",
    "UserProfile", "IndividualVerification",
]
