"""
app/identity/
├── __init__.py
├── models/                # split models into logical files
├── services/              # business logic, e.g., authentication, verification
├── schemas/               # Pydantic/Marshmallow schemas for API serialization
├── repositories/          # optional DB access layer or helper queries
├── events/                # event handlers (e.g., pre-KYC duplicate check)
├── utils/                 # helpers: hashing, MFA, permission checks


app/identity/models/
├── __init__.py                # imports all models for SQLAlchemy binding
├── user.py                    # User, UserRole, MFASecret, Session, APIKey
├── organisation.py            # Organisation (core entity)
├── organisation_controller.py # OrganisationController (ownership/governance logic)
├── organisation_member.py     # OrganisationMember, OrgRole, OrgUserRole
├── roles_permission.py        # Role, Permission, RolePermission
├── licence_document.py        # OrganisationLicense, OrganisationDocument, OrganisationAuditLog
├── compliance_audit_log.py    # ComplianceAuditLog (tracks compliance events)
├── compliance_settings.py     # ComplianceSettings (admin toggles, regulator flags)
├── kyb.py                     # OrganisationVerification, OrganisationKYBCheck, OrganisationUBO, OrganisationKYBDocument
├── note.py                    # Note (annotations, comments, audit notes)

app/identity/individuals/
├── individual_document.py      # IndividualKYCDocument (personal KYC docs)
├── individual_verification.py  # IndividualVerification (personal identity checks)
├── __init__.py                 # binds individual models

app/identity/utils/
├── compliance_checker.py       # logic for compliance checks
├── compliance_utils.py         # helper functions for compliance workflows


"""