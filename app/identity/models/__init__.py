#app/identity/models/__init__.py
from .user import User, UserRole, MFASecret, Session, APIKey
from .organisation import Organisation
from .organisation_member import OrganisationMember, OrgUserRole, OrgRole
from .organisation_controller import OrganisationController
from .licence_document import OrganisationLicense, OrganisationDocument, OrganisationAuditLog
from .roles_permission import Role, Permission, RolePermission
from .kyb import OrganisationVerification, OrganisationKYBCheck, OrganisationUBO, OrganisationKYBDocument
from .compliance_audit_log import ComplianceAuditLog
from .compliance_settings import ComplianceSettings
# Import UserProfile to resolve SQLAlchemy Mapper error
from app.profile.models import UserProfile
# Import IndividualVerification to resolve SQLAlchemy Mapper error
from app.identity.individuals.individual_verification import IndividualVerification

__all__ = [
    "User", "UserRole", "MFASecret", "Session", "APIKey",
    "Organisation", "OrganisationMember", "OrgUserRole", "OrgRole", "OrganisationController",
    "OrganisationLicense", "OrganisationDocument", "OrganisationAuditLog",
    "Role", "Permission", "RolePermission",
    "OrganisationVerification", "OrganisationKYBCheck", "OrganisationUBO", "OrganisationKYBDocument",
    "ComplianceAuditLog", "ComplianceSettings",
    "UserProfile", "IndividualVerification",
]
