# app/identity/__init__.py
from .models import (
    User, UserRole, MFASecret, Session, APIKey,
    Organisation, OrganisationMember, OrgRole, OrgUserRole, OrganisationController,
    OrganisationLicense, OrganisationDocument, OrganisationAuditLog,
    Role, Permission, RolePermission,
    ComplianceSettings, ComplianceAuditLog,
    OrganisationVerification, OrganisationKYBCheck, OrganisationUBO, OrganisationKYBDocument,
)
from .individuals import IndividualKYCDocument, IndividualVerification  # ← this already registers the class
from .utils.compliance_checker import ComplianceChecker
from .utils import compliance_utils

__all__ = [
    "User", "UserRole", "MFASecret", "Session", "APIKey",
    "Organisation", "OrganisationMember", "OrgRole", "OrgUserRole", "OrganisationController",
    "OrganisationLicense", "OrganisationDocument", "OrganisationAuditLog",
    "Role", "Permission", "RolePermission",
    "ComplianceSettings", "ComplianceAuditLog",
    "OrganisationVerification", "OrganisationKYBCheck", "OrganisationUBO", "OrganisationKYBDocument",
    "IndividualKYCDocument", "IndividualVerification",
    "ComplianceChecker", "compliance_utils",
]
