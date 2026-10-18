"""
app/core/model_registry.py
Central model registry for deterministic model loading.

This ensures all SQLAlchemy models are loaded before ORM initialization,
preventing "model not found" errors in relationships.
"""

import logging

# Registration failures are recorded rather than silently swallowed.  The
# application still starts (these domains are imported lazily to avoid circular
# imports), but the model-bootstrap schema path refuses to build a schema from
# an incomplete model set -- see app/core/model_bootstrap.py.  A silent failure
# here would otherwise produce a silently incomplete schema.
_REGISTRATION_FAILURES = {}


def _record_failure(domain, exc):
    """Record (and loudly log) a domain whose models failed to import."""
    _REGISTRATION_FAILURES[domain] = f"{type(exc).__name__}: {exc}"
    logging.getLogger("app").error(
        f"[model_registry] Failed to import {domain} models: {exc}"
    )


def registration_failures():
    """Return {domain: error} for every domain that failed to register."""
    return dict(_REGISTRATION_FAILURES)


def register_all_models():
    """
    Explicitly load all models before SQLAlchemy initializes.
    This must be called BEFORE db.init_app() in the app factory.
    """
    # Identity domain
    from app.identity.models.user import User
    from app.identity.models.organisation import Organisation
    from app.identity.models.organisation_catalogues import (
        OrganisationCategory,
        OrganisationTypeCatalogue,
    )
    from app.identity.models.organisation_provider_capability import OrganisationProviderCapability
    from app.identity.models.provider_participation import ProviderParticipation
    from app.identity.models.roles_permission import Role, Permission
    from app.identity.models.compliance_audit_log import ComplianceAuditLog
    from app.identity.models.org_payment_gateway import OrganisationPaymentGateway, PaymentGatewayProvider, PaymentGatewayEnvironment

    # Profile domain
    from app.profile.models import UserProfile

    # Wallet domain - NEW LEDGER ARCHITECTURE
    from app.wallet.models.ledger import AccountModel, LedgerEntryModel
    from app.wallet.models.agent_onboarding import AgentOnboarding, AgentOnboardingApproval
    from app.wallet.models.agent_float import AgentFloatAccount, AgentFloatLedger
    from app.wallet.models.transaction import TransactionModel
    from app.wallet.models.audit import AuditLogModel
    from app.wallet.models.fx import FXRateModel, FXTransactionModel
    from app.wallet.models.payment_identity import PaymentIdentityModel

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
            CancellationPolicy,
            CancellationPenalty,
            AccommodationPropertyTypeConfig,
            AccommodationListingTypeConfig,
            AccommodationPolicyTier,
            AccommodationBookingMode,
            AccommodationCurrency,
            PropertyTypeHostType,
            PropertyTypeListingType,
            AccommodationCancellationPolicyTypeConfig,
            AccommodationCancellationPhaseConfig,
            AccommodationNoShowChargeTypeConfig,
        )
    except ImportError as e:
        # Deliberately NOT silent: if this fails, test/CI schema setup will
        # be silently incomplete again.
        _record_failure("accommodation", e)

    # Events domain
    try:
        from app.events.models import Event, EventGroup, EventGroupMember
        from app.events.inventory import TicketHold
        from app.events.models import OrganizerProfile
    except ImportError as e:
        _record_failure("events", e)

    # Wallet payment config
    try:
        from app.wallet.models.payment_method import PaymentMethodConfig, EventPaymentPreference
    except ImportError as e:
        _record_failure("wallet_payment_method", e)

    # Organisation payment gateways
    try:
        from app.identity.models.org_payment_gateway import OrganisationPaymentGateway
    except ImportError as e:
        _record_failure("organisation_payment_gateway", e)

    # Transport domain
    try:
        from app.transport.models import (
            DriverProfile,
            OrganisationTransportProfile,
            Vehicle,
            DriverVehicleHistory,
            Booking,
            BookingPayment,
            Rating,
            ScheduledRoute,
            ContingencyPlan,
            TransportPassenger,
            # BOOKING-LIFECYCLE-PERSISTENCE (Stage 3B, Phase 1): pre-Booking
            # lifecycle persistence foundation (additive; no behavior change).
            RideRequest,
            SearchCycle,
            OfferAttempt,
        )
    except ImportError as e:
        _record_failure("transport", e)

    # Transport permissions (dynamic) - core model
    try:
        from app.core.transport_permissions import TransportPermission
    except ImportError as e:
        _record_failure("transport_permissions", e)

    # Admin domain - lazy import to avoid circular dependencies
    try:
        from app.admin.models.moderation import ContentFlag, ModerationLog
    except ImportError as e:
        ContentFlag = None
        ModerationLog = None
        _record_failure("admin_moderation", e)

    # Audit domain
    try:
        from app.audit.models import AuditLog
    except ImportError as e:
        _record_failure("audit", e)

    # Auth / KYC domain
    try:
        from app.kyc.models import KycRecord
    except ImportError as e:
        _record_failure("kyc", e)

    # Identity domain - IndividualVerification
    try:
        from app.identity.individuals.individual_verification import IndividualVerification
    except ImportError as e:
        _record_failure("individual_verification", e)

    # Compliance domain
    try:
        from app.admin.compliance.models import ComplianceCase, DataSubjectRequest, ComplianceReport
    except ImportError as e:
        _record_failure("compliance", e)

    # AML domain (screening / monitoring models — must be registered so their
    # tables resolve in db.metadata for both runtime and Alembic autogenerate)
    try:
        from app.compliance.aml_service import AMLScreeningResult, AMLTransactionMonitor
    except ImportError as e:
        _record_failure("aml", e)

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
        _record_failure("notifications", e)

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
        _record_failure("notifications_events", e)

    # Feed domain
    try:
        from app.feed.models import Post, Advertisement
    except ImportError as e:
        _record_failure("feed", e)

    # Fan domain
    try:
        from app.fan.models import FanProfile, UserDashboardContext
    except ImportError as e:
        _record_failure("fan", e)

    # Media domain
    try:
        from app.media.models import Media, MediaProcessingJob, MediaSettings
    except ImportError as e:
        _record_failure("media", e)

    # Payment provider config (for admin payment method configuration)
    try:
        from app.wallet.models.config import PaymentProviderConfig, WalletSystemConfig
    except ImportError as e:
        _record_failure("wallet_config", e)

    # GEO domain - durable location observation history (roadmap GEO-15).
    # Domain-neutral records; producing domains write via explicit contract.
    try:
        from app.geo.models import LocationObservation
    except ImportError as e:
        _record_failure("geo", e)