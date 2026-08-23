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

    # Accommodation domain
    # NOTE: previously this domain had NO entry here at all (not even a
    # try/except stub like the others). Its only path onto db.metadata was
    # the accommodation_bp import in __init__.py, which is wrapped in a
    # broad `except Exception` that silently swallows any import failure.
    # That meant db.create_all() (used by scripts/setup_test_db_schema.py)
    # could run with zero accommodation tables registered, with no error
    # surfaced anywhere. This entry makes accommodation model registration
    # independent of blueprint registration succeeding, matching every
    # other domain in this file.
    try:
        from app.accommodation.models import (
            Property,
            AccommodationBooking,
            PropertyBookingPolicy,
            BookingPriceAdjustment,
            GuestRegistration,
            Review,
            RoomType,
            Room,
            BlockedDate,
            AccommodationComplaint,
            AccommodationBookingAmendment,
        )
    except ImportError as e:
        # Deliberately NOT silent: if this fails, test/CI schema setup will
        # be silently incomplete again. Log loudly instead of `pass`.
        import logging
        logging.getLogger("app").error(
            f"[model_registry] Failed to import accommodation models: {e}"
        )

    # Events domain
    try:
        from app.events.models import Event, EventGroup, EventGroupMember
        from app.events.inventory import TicketHold
        from app.events.models import OrganizerProfile
    except ImportError:
        pass

    # Wallet payment config
    try:
        from app.wallet.models.payment_method import PaymentMethodConfig, EventPaymentPreference
    except ImportError:
        pass

    # Transport domain
    try:
        from app.transport.models import Transport
    except ImportError:
        pass

    # Admin domain - lazy import to avoid circular dependencies
    try:
        from app.admin.models.moderation import ContentFlag, ModerationLog
    except ImportError:
        ContentFlag = None
        ModerationLog = None

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

    # AML domain (screening / monitoring models — must be registered so their
    # tables resolve in db.metadata for both runtime and Alembic autogenerate)
    try:
        from app.compliance.aml_service import AMLScreeningResult, AMLTransactionMonitor
    except ImportError:
        pass

    # Notification domain
    try:
        from app.notifications.models import (
            Notification,
            NotificationTemplate,
            UserNotificationPreference,
            NotificationLog,
            NotificationDelivery,
            CommunicationSettings,
            NotificationAggregator,
            Message,
        )
    except ImportError as e:
        import logging
        logging.getLogger("app").error(
            f"[model_registry] Failed to import notification models: {e}"
        )

    # Platform event backbone (transactional outbox, event ledger, webhooks).
    # Lives under app/notifications/events because app/events is the AFCON
    # events *business* domain (matches/tickets) and must not be shadowed.
    try:
        from app.notifications.events.models import (
            DomainEvent,
            OutboxEvent,
            ProcessedEvent,
            EventSubscription,
            WebhookDelivery,
        )
    except ImportError as e:
        import logging
        logging.getLogger("app").error(
            f"[model_registry] Failed to import event backbone models: {e}"
        )

    # KYC domain
    try:
        from app.kyc.models import KycRecord
    except ImportError:
        pass

    # Fan domain
    try:
        from app.fan.models import FanProfile, UserDashboardContext
    except ImportError:
        pass

    # Media domain
    try:
        from app.media.models import Media, MediaProcessingJob, MediaSettings
    except ImportError:
        pass

    # Payment provider config (for admin payment method configuration)
    try:
        from app.wallet.models.config import PaymentProviderConfig, WalletSystemConfig
    except ImportError:
        pass