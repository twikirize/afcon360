"""
app/core/model_registry.py
Central model registry for deterministic model loading.

This ensures all SQLAlchemy models are loaded before ORM initialization,
preventing "model not found" errors in relationships.
"""

def register_all_models():
    """
    Explicitly load all models before SQLAlchemy initializes.
    This must be called BEFORE db.init_app() in the app factory.
    """
    # Identity domain
    from app.identity.models.user import User
    from app.identity.models.organisation import Organisation
    from app.identity.models.roles_permission import Role, Permission
    from app.identity.models.compliance_audit_log import ComplianceAuditLog

    # Profile domain
    from app.profile.models import UserProfile

    # Wallet domain - NEW LEDGER ARCHITECTURE
    from app.wallet.models.ledger import AccountModel, LedgerEntryModel
    from app.wallet.models.transaction import TransactionModel
    from app.wallet.models.audit import AuditLogModel
    from app.wallet.models.fx import FXRateModel, FXTransactionModel

    # Events domain
    try:
        from app.events.models import Event
    except ImportError:
        pass

    # Transport domain
    try:
        from app.transport.models import Transport
    except ImportError:
        pass

    # Admin domain
    try:
        from app.admin.models.moderation import ContentFlag, ModerationLog
    except ImportError:
        pass

    # Audit domain
    try:
        from app.audit.models import AuditLog
    except ImportError:
        pass

    # Auth domain
    try:
        from app.auth.models import KYCRecord, IndividualVerification
    except ImportError:
        pass

    # Compliance domain
    try:
        from app.admin.compliance.models import ComplianceCase, DataSubjectRequest, ComplianceReport
    except ImportError:
        pass

    # KYC domain
    try:
        from app.kyc.models import KycRecord
    except ImportError:
        pass
