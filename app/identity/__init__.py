# app/identity/__init__.py
from .models import (
    User, UserRole, MFASecret, Session, APIKey,
    Organisation, OrganisationMember, OrgRole, OrgUserRole, OrganisationController,
    OrganisationLicense, OrganisationDocument, OrganisationAuditLog,
    Role, Permission, RolePermission,
    OrganisationVerification, OrganisationKYBCheck, OrganisationUBO, OrganisationKYBDocument,
)
from .individuals import IndividualKYCDocument, IndividualVerification  # ← this already registers the class

# Compliance imports deferred to avoid circular imports
# Use app.admin.compliance directly when needed

__all__ = [
    "User", "UserRole", "MFASecret", "Session", "APIKey",
    "Organisation", "OrganisationMember", "OrgRole", "OrgUserRole", "OrganisationController",
    "OrganisationLicense", "OrganisationDocument", "OrganisationAuditLog",
    "Role", "Permission", "RolePermission",
    "OrganisationVerification", "OrganisationKYBCheck", "OrganisationUBO", "OrganisationKYBDocument",
    "IndividualKYCDocument", "IndividualVerification",
    "ComplianceAuditLog", "ComplianceSettings",
]
