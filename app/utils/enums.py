"""
============================================================================
APPLICATION-LEVEL ENUM CONSTANTS (NO POSTGRESQL ENUMS)
============================================================================

This file provides Python enum classes for APPLICATION-LEVEL VALIDATION ONLY.
These are used for:
  - Type hints and IDE support
  - Application-level validation in models (@validates)
  - Service-layer business logic
  - Templates and JavaScript constants

THESE DO NOT CREATE POSTGRESQL ENUM TYPES.

Database columns use String + CHECK constraints instead.
See DATABASE_SCALABILITY_ROADMAP.md for the migration strategy.

Rule: NEVER use sqlalchemy.Enum, SQLEnum, SAEnum, or PgEnum in models.
Use String columns with CHECK constraints for database-level validation.
============================================================================
"""
from enum import Enum
from typing import List, Set


# ============================================================================
# TRANSPORT MODULE
# ============================================================================

class ServiceType(str, Enum):
    AIRPORT_ARRIVAL = 'airport_arrival'
    AIRPORT_DEPARTURE = 'airport_departure'
    STADIUM_SHUTTLE = 'stadium_shuttle'
    HOTEL_TRANSFER = 'hotel_transfer'
    CITY_TOUR = 'city_tour'
    ON_DEMAND = 'on_demand'
    SCHEDULED_ROUTE = 'scheduled_route'
    CUSTOM_TOUR = 'custom_tour'

    @classmethod
    def values(cls) -> List[str]:
        return [e.value for e in cls]

    @classmethod
    def check_constraint(cls) -> str:
        vals = ", ".join(f"'{v}'" for v in cls.values())
        return f"service_type IN ({vals})"


class BookingStatus(str, Enum):
    DRAFT = 'draft'
    PENDING_PAYMENT = 'pending_payment'
    CONFIRMED = 'confirmed'
    ASSIGNED = 'assigned'
    DRIVER_EN_ROUTE = 'driver_en_route'
    PICKUP_ARRIVED = 'pickup_arrived'
    IN_PROGRESS = 'in_progress'
    COMPLETED = 'completed'
    CANCELLED = 'cancelled'
    NO_SHOW = 'no_show'
    DISPUTED = 'disputed'
    NO_MATCH = 'no_match'

    @classmethod
    def values(cls) -> List[str]:
        return [e.value for e in cls]

    @classmethod
    def check_constraint(cls) -> str:
        vals = ", ".join(f"'{v}'" for v in cls.values())
        return f"status IN ({vals})"


class ComplianceStatus(str, Enum):
    PENDING_REVIEW = 'pending_review'
    UNDER_REVIEW = 'under_review'
    APPROVED = 'approved'
    SUSPENDED = 'suspended'
    REVOKED = 'revoked'
    BLACKLISTED = 'blacklisted'

    @classmethod
    def values(cls) -> List[str]:
        return [e.value for e in cls]

    @classmethod
    def check_constraint(cls) -> str:
        vals = ", ".join(f"'{v}'" for v in cls.values())
        return f"compliance_status IN ({vals})"


class PaymentStatus(str, Enum):
    PENDING = 'pending'
    AUTHORIZED = 'authorized'
    CAPTURED = 'captured'
    PARTIALLY_CAPTURED = 'partially_captured'
    REFUNDED = 'refunded'
    PARTIALLY_REFUNDED = 'partially_refunded'
    FAILED = 'failed'
    CANCELLED = 'cancelled'

    @classmethod
    def values(cls) -> List[str]:
        return [e.value for e in cls]

    @classmethod
    def check_constraint(cls) -> str:
        vals = ", ".join(f"'{v}'" for v in cls.values())
        return f"payment_status IN ({vals})"


class VehicleClass(str, Enum):
    ECONOMY = 'economy'
    COMFORT = 'comfort'
    PREMIUM = 'premium'
    LUXURY = 'luxury'
    VAN = 'van'
    BUS = 'bus'

    @classmethod
    def values(cls) -> List[str]:
        return [e.value for e in cls]

    @classmethod
    def check_constraint(cls) -> str:
        vals = ", ".join(f"'{v}'" for v in cls.values())
        return f"vehicle_class IN ({vals})"


class IncidentSeverity(str, Enum):
    INFO = 'info'
    LOW = 'low'
    MEDIUM = 'medium'
    HIGH = 'high'
    CRITICAL = 'critical'

    @classmethod
    def values(cls) -> List[str]:
        return [e.value for e in cls]

    @classmethod
    def check_constraint(cls) -> str:
        vals = ", ".join(f"'{v}'" for v in cls.values())
        return f"severity IN ({vals})"


class Currency(str, Enum):
    USD = 'USD'
    EUR = 'EUR'
    GBP = 'GBP'
    XOF = 'XOF'
    XAF = 'XAF'
    NGN = 'NGN'
    KES = 'KES'
    GHS = 'GHS'
    ZAR = 'ZAR'
    UGX = 'UGX'

    @classmethod
    def values(cls) -> List[str]:
        return [e.value for e in cls]

    @classmethod
    def check_constraint(cls) -> str:
        vals = ", ".join(f"'{v}'" for v in cls.values())
        return f"currency IN ({vals})"


class ProviderType(str, Enum):
    INDIVIDUAL_DRIVER = 'individual_driver'
    HOTEL_FLEET = 'hotel_fleet'
    TOUR_OPERATOR = 'tour_operator'
    TRANSPORT_COMPANY = 'transport_company'
    EXTERNAL_PLATFORM = 'external_platform'

    @classmethod
    def values(cls) -> List[str]:
        return [e.value for e in cls]

    @classmethod
    def check_constraint(cls) -> str:
        vals = ", ".join(f"'{v}'" for v in cls.values())
        return f"provider_type IN ({vals})"


class VerificationTier(str, Enum):
    PENDING = 'pending'
    BASIC_VERIFIED = 'basic_verified'
    PLATFORM_VERIFIED = 'platform_verified'
    EVENT_CERTIFIED = 'event_certified'

    @classmethod
    def values(cls) -> List[str]:
        return [e.value for e in cls]

    @classmethod
    def check_constraint(cls) -> str:
        vals = ", ".join(f"'{v}'" for v in cls.values())
        return f"verification_tier IN ({vals})"


class CompensationModel(str, Enum):
    REVENUE_SPLIT = 'revenue_split'
    FIXED_RENTAL = 'fixed_rental'
    HYBRID = 'hybrid'
    FIXED_FEE = 'fixed_fee'
    PERCENTAGE = 'percentage'
    PER_KM = 'per_km'
    PER_HOUR = 'per_hour'
    DAILY_RATE = 'daily_rate'
    WEEKLY_RATE = 'weekly_rate'
    MONTHLY_RATE = 'monthly_rate'
    REVENUE_SHARE = 'revenue_share'

    @classmethod
    def values(cls) -> List[str]:
        return [e.value for e in cls]

    @classmethod
    def check_constraint(cls) -> str:
        vals = ", ".join(f"'{v}'" for v in cls.values())
        return f"compensation_model IN ({vals})"


class ContractStatus(str, Enum):
    DRAFT = 'draft'
    ACTIVE = 'active'
    SUSPENDED = 'suspended'
    TERMINATED = 'terminated'
    EXPIRED = 'expired'
    PENDING_SIGNATURE = 'pending_signature'

    @classmethod
    def values(cls) -> List[str]:
        return [e.value for e in cls]

    @classmethod
    def check_constraint(cls) -> str:
        vals = ", ".join(f"'{v}'" for v in cls.values())
        return f"contract_status IN ({vals})"


# ============================================================================
# ACCOMMODATION MODULE
# ============================================================================

class PropertyDocumentType(str, Enum):
    ID_DOCUMENT = 'id_document'
    BUSINESS_LICENSE = 'business_license'
    TAX_CERTIFICATE = 'tax_certificate'
    PROPERTY_DEED = 'property_deed'
    INSURANCE_CERTIFICATE = 'insurance_certificate'
    OTHER = 'other'

    @classmethod
    def values(cls) -> List[str]:
        return [e.value for e in cls]

    @classmethod
    def check_constraint(cls) -> str:
        vals = ", ".join(f"'{v}'" for v in cls.values())
        return f"document_type IN ({vals})"


class PropertyDocumentStatus(str, Enum):
    PENDING = 'pending'
    APPROVED = 'approved'
    REJECTED = 'rejected'
    EXPIRED = 'expired'

    @classmethod
    def values(cls) -> List[str]:
        return [e.value for e in cls]

    @classmethod
    def check_constraint(cls) -> str:
        vals = ", ".join(f"'{v}'" for v in cls.values())
        return f"status IN ({vals})"


# ============================================================================
# AUDIT MODULE
# ============================================================================

class AuditSeverity(str, Enum):
    INFO = 'info'
    WARNING = 'warning'
    CRITICAL = 'critical'
    SECURITY = 'security'

    @classmethod
    def values(cls) -> List[str]:
        return [e.value for e in cls]

    @classmethod
    def check_constraint(cls) -> str:
        vals = ", ".join(f"'{v}'" for v in cls.values())
        return f"severity IN ({vals})"


class AuditTransactionType(str, Enum):
    DEPOSIT = 'deposit'
    WITHDRAWAL = 'withdrawal'
    TRANSFER = 'transfer'
    REFUND = 'refund'
    FEE = 'fee'
    REVERSAL = 'reversal'
    CURRENCY_EXCHANGE = 'currency_exchange'
    COMMISSION = 'commission'
    PAYOUT = 'payout'
    EXCHANGE = 'exchange'

    @classmethod
    def values(cls) -> List[str]:
        return [e.value for e in cls]

    @classmethod
    def check_constraint(cls) -> str:
        vals = ", ".join(f"'{v}'" for v in cls.values())
        return f"transaction_type IN ({vals})"


class APICallStatus(str, Enum):
    SUCCESS = 'success'
    FAILURE = 'failure'
    TIMEOUT = 'timeout'
    RATE_LIMITED = 'rate_limited'

    @classmethod
    def values(cls) -> List[str]:
        return [e.value for e in cls]

    @classmethod
    def check_constraint(cls) -> str:
        vals = ", ".join(f"'{v}'" for v in cls.values())
        return f"status IN ({vals})"


class DataAccessType(str, Enum):
    READ = 'read'
    EXPORT = 'export'
    DELETE = 'delete'
    MODIFY = 'modify'

    @classmethod
    def values(cls) -> List[str]:
        return [e.value for e in cls]

    @classmethod
    def check_constraint(cls) -> str:
        vals = ", ".join(f"'{v}'" for v in cls.values())
        return f"access_type IN ({vals})"


# ============================================================================
# PROFILE MODULE
# ============================================================================

class Gender(str, Enum):
    MALE = 'male'
    FEMALE = 'female'
    OTHER = 'other'
    UNSPECIFIED = 'unspecified'

    @classmethod
    def values(cls) -> List[str]:
        return [e.value for e in cls]

    @classmethod
    def check_constraint(cls) -> str:
        vals = ", ".join(f"'{v}'" for v in cls.values())
        return f"gender IN ({vals})"


class IDType(str, Enum):
    PASSPORT = 'passport'
    NATIONAL_ID = 'national_id'
    DRIVER_LICENSE = 'driver_license'
    OTHER = 'other'

    @classmethod
    def values(cls) -> List[str]:
        return [e.value for e in cls]

    @classmethod
    def check_constraint(cls) -> str:
        vals = ", ".join(f"'{v}'" for v in cls.values())
        return f"id_type IN ({vals})"


class VerificationStatus(str, Enum):
    PENDING = 'pending'
    VERIFIED = 'verified'
    REJECTED = 'rejected'
    SUSPENDED = 'suspended'

    @classmethod
    def values(cls) -> List[str]:
        return [e.value for e in cls]

    @classmethod
    def check_constraint(cls) -> str:
        vals = ", ".join(f"'{v}'" for v in cls.values())
        return f"verification_status IN ({vals})"


class KYCLevel(str, Enum):
    BASIC = 'basic'
    ENHANCED = 'enhanced'
    GOVERNMENT = 'government'

    @classmethod
    def values(cls) -> List[str]:
        return [e.value for e in cls]

    @classmethod
    def check_constraint(cls) -> str:
        vals = ", ".join(f"'{v}'" for v in cls.values())
        return f"kyc_level IN ({vals})"


# ============================================================================
# IDENTITY MODULE
# ============================================================================

class OrgVerificationStatus(str, Enum):
    UNVERIFIED = 'unverified'
    PENDING = 'pending'
    VERIFIED = 'verified'
    REJECTED = 'rejected'
    SUSPENDED = 'suspended'
    EXPIRED = 'expired'

    @classmethod
    def values(cls) -> List[str]:
        return [e.value for e in cls]

    @classmethod
    def check_constraint(cls) -> str:
        vals = ", ".join(f"'{v}'" for v in cls.values())
        return f"verification_status IN ({vals})"


class OrgLifecycleState(str, Enum):
    DRAFT = 'draft'
    REGISTERED = 'registered'
    APPROVED = 'approved'
    SUSPENDED = 'suspended'
    CLOSED = 'closed'

    @classmethod
    def values(cls) -> List[str]:
        return [e.value for e in cls]

    @classmethod
    def check_constraint(cls) -> str:
        vals = ", ".join(f"'{v}'" for v in cls.values())
        return f"lifecycle_state IN ({vals})"


class OrgKybCheckType(str, Enum):
    IDENTITY = 'identity'
    TAX = 'tax'
    LICENSE = 'license'
    UBO = 'ubo'
    SANCTIONS = 'sanctions'

    @classmethod
    def values(cls) -> List[str]:
        return [e.value for e in cls]

    @classmethod
    def check_constraint(cls) -> str:
        vals = ", ".join(f"'{v}'" for v in cls.values())
        return f"check_type IN ({vals})"


class OrgKybCheckStatus(str, Enum):
    PENDING = 'pending'
    PASSED = 'passed'
    FAILED = 'failed'
    MANUAL_REVIEW = 'manual_review'

    @classmethod
    def values(cls) -> List[str]:
        return [e.value for e in cls]

    @classmethod
    def check_constraint(cls) -> str:
        vals = ", ".join(f"'{v}'" for v in cls.values())
        return f"status IN ({vals})"


class UboType(str, Enum):
    INDIVIDUAL = 'individual'
    CORPORATE = 'corporate'

    @classmethod
    def values(cls) -> List[str]:
        return [e.value for e in cls]

    @classmethod
    def check_constraint(cls) -> str:
        vals = ", ".join(f"'{v}'" for v in cls.values())
        return f"ubo_type IN ({vals})"


class KybDocStatus(str, Enum):
    PENDING = 'pending'
    VERIFIED = 'verified'
    REJECTED = 'rejected'

    @classmethod
    def values(cls) -> List[str]:
        return [e.value for e in cls]

    @classmethod
    def check_constraint(cls) -> str:
        vals = ", ".join(f"'{v}'" for v in cls.values())
        return f"verification_status IN ({vals})"


class IndVerificationStatus(str, Enum):
    PENDING = 'pending'
    VERIFIED = 'verified'
    REJECTED = 'rejected'
    EXPIRED = 'expired'
    SUSPENDED = 'suspended'

    @classmethod
    def values(cls) -> List[str]:
        return [e.value for e in cls]

    @classmethod
    def check_constraint(cls) -> str:
        vals = ", ".join(f"'{v}'" for v in cls.values())
        return f"status IN ({vals})"


class IndDocumentType(str, Enum):
    ID_CARD = 'id_card'
    PASSPORT = 'passport'
    DRIVER_LICENSE = 'driver_license'
    PROOF_OF_ADDRESS = 'proof_of_address'

    @classmethod
    def values(cls) -> List[str]:
        return [e.value for e in cls]

    @classmethod
    def check_constraint(cls) -> str:
        vals = ", ".join(f"'{v}'" for v in cls.values())
        return f"document_type IN ({vals})"


class DocVerificationStatus(str, Enum):
    PENDING = 'pending'
    VERIFIED = 'verified'
    REJECTED = 'rejected'

    @classmethod
    def values(cls) -> List[str]:
        return [e.value for e in cls]

    @classmethod
    def check_constraint(cls) -> str:
        vals = ", ".join(f"'{v}'" for v in cls.values())
        return f"verification_status IN ({vals})"


class OrgChangeType(str, Enum):
    CREATE = 'create'
    UPDATE = 'update'
    DELETE = 'delete'
    VERIFY = 'verify'
    SUSPEND = 'suspend'

    @classmethod
    def values(cls) -> List[str]:
        return [e.value for e in cls]

    @classmethod
    def check_constraint(cls) -> str:
        vals = ", ".join(f"'{v}'" for v in cls.values())
        return f"change_type IN ({vals})"


class OrgChangeSource(str, Enum):
    SYSTEM = 'system'
    USER = 'user'
    ADMIN = 'admin'

    @classmethod
    def values(cls) -> List[str]:
        return [e.value for e in cls]

    @classmethod
    def check_constraint(cls) -> str:
        # Column on OrganisationAuditLog is `source` (see
        # app/identity/models/licence_document.py), not `change_source`.
        vals = ", ".join(f"'{v}'" for v in cls.values())
        return f"source IN ({vals})"


class EntityType(str, Enum):
    ORGANISATION = 'organisation'
    INDIVIDUAL = 'individual'

    @classmethod
    def values(cls) -> List[str]:
        return [e.value for e in cls]

    @classmethod
    def check_constraint(cls) -> str:
        vals = ", ".join(f"'{v}'" for v in cls.values())
        return f"entity_type IN ({vals})"


class ComplianceDecision(str, Enum):
    ALLOWED = 'allowed'
    BLOCKED = 'blocked'
    CONDITIONAL = 'conditional'

    @classmethod
    def values(cls) -> List[str]:
        return [e.value for e in cls]

    @classmethod
    def check_constraint(cls) -> str:
        vals = ", ".join(f"'{v}'" for v in cls.values())
        return f"decision IN ({vals})"


class RiskTier(str, Enum):
    LOW = 'low'
    MEDIUM = 'medium'
    HIGH = 'high'

    @classmethod
    def values(cls) -> List[str]:
        return [e.value for e in cls]

    @classmethod
    def check_constraint(cls) -> str:
        vals = ", ".join(f"'{v}'" for v in cls.values())
        return f"risk_tier IN ({vals})"


class ComplianceEnforcementLevel(str, Enum):
    OPTIONAL = 'optional'
    CONDITIONAL = 'conditional'
    MANDATORY = 'mandatory'

    @classmethod
    def values(cls) -> List[str]:
        return [e.value for e in cls]

    @classmethod
    def check_constraint(cls) -> str:
        vals = ", ".join(f"'{v}'" for v in cls.values())
        return f"enforcement_level IN ({vals})"


class PaymentGatewayProvider(str, Enum):
    FLUTTERWAVE = 'flutterwave'
    PAYSTACK = 'paystack'
    MTN_MOMO = 'mtn_momo'
    AIRTEL_MONEY = 'airtel_money'
    VISA = 'visa'
    MASTERCARD = 'mastercard'
    PAYPAL = 'paypal'
    ALIPAY = 'alipay'
    WECHAT_PAY = 'wechat_pay'
    BANK_TRANSFER = 'bank_transfer'
    STRIPE = 'stripe'
    MPESA = 'mpesa'

    @classmethod
    def values(cls) -> List[str]:
        return [e.value for e in cls]

    @classmethod
    def check_constraint(cls) -> str:
        vals = ", ".join(f"'{v}'" for v in cls.values())
        return f"provider IN ({vals})"


class PaymentGatewayEnvironment(str, Enum):
    SANDBOX = 'sandbox'
    PRODUCTION = 'production'

    @classmethod
    def values(cls) -> List[str]:
        return [e.value for e in cls]

    @classmethod
    def check_constraint(cls) -> str:
        vals = ", ".join(f"'{v}'" for v in cls.values())
        return f"environment IN ({vals})"


# ============================================================================
# WALLET MODULE
# ============================================================================

class WindowMode(str, Enum):
    CALENDAR = 'calendar'
    ROLLING = 'rolling'

    @classmethod
    def values(cls) -> List[str]:
        return [e.value for e in cls]

    @classmethod
    def check_constraint(cls) -> str:
        vals = ", ".join(f"'{v}'" for v in cls.values())
        return f"window_mode IN ({vals})"


class RegulatoryVolumeStatus(str, Enum):
    PENDING = 'pending'
    APPROVED = 'approved'
    REJECTED = 'rejected'
    CANCELLED = 'cancelled'
    EXPIRED = 'expired'

    @classmethod
    def values(cls) -> List[str]:
        return [e.value for e in cls]

    @classmethod
    def check_constraint(cls) -> str:
        vals = ", ".join(f"'{v}'" for v in cls.values())
        return f"status IN ({vals})"


class WalletTransactionType(str, Enum):
    DEPOSIT = 'deposit'
    WITHDRAW = 'withdraw'
    TRANSFER = 'transfer'
    FEE = 'fee'
    REFUND = 'refund'
    ADJUSTMENT = 'adjustment'

    @classmethod
    def values(cls) -> List[str]:
        return [e.value for e in cls]

    @classmethod
    def check_constraint(cls) -> str:
        vals = ", ".join(f"'{v}'" for v in cls.values())
        return f"tx_type IN ({vals})"


class WalletTransactionStatus(str, Enum):
    PENDING = 'pending'
    COMPLETED = 'completed'
    FAILED = 'failed'
    CANCELLED = 'cancelled'

    @classmethod
    def values(cls) -> List[str]:
        return [e.value for e in cls]

    @classmethod
    def check_constraint(cls) -> str:
        vals = ", ".join(f"'{v}'" for v in cls.values())
        return f"status IN ({vals})"


# ============================================================================
# EVENTS MODULE
# ============================================================================

class EventStatus(str, Enum):
    DRAFT = 'draft'
    PENDING_APPROVAL = 'pending_approval'
    APPROVED = 'approved'
    REJECTED = 'rejected'
    PUBLISHED = 'published'
    SUSPENDED = 'suspended'
    PAUSED = 'paused'
    COMPLETED = 'completed'
    CANCELLED = 'cancelled'
    ARCHIVED = 'archived'
    DELETED = 'deleted'
    ACTIVE = 'active'  # legacy

    @classmethod
    def values(cls) -> List[str]:
        return [e.value for e in cls]

    @classmethod
    def check_constraint(cls) -> str:
        vals = ", ".join(f"'{v}'" for v in cls.values())
        return f"status IN ({vals})"


class RegistrationAvailability(str, Enum):
    NOT_OPEN = 'not_open'
    OPEN = 'open'
    CLOSED = 'closed'
    SOLD_OUT = 'sold_out'
    EXPIRED = 'expired'

    @classmethod
    def values(cls) -> List[str]:
        return [e.value for e in cls]

    @classmethod
    def check_constraint(cls) -> str:
        vals = ", ".join(f"'{v}'" for v in cls.values())
        return f"registration_availability IN ({vals})"


class BookingType(str, Enum):
    SELF = 'self'
    THIRD_PARTY = 'third_party'
    GROUP = 'group'

    @classmethod
    def values(cls) -> List[str]:
        return [e.value for e in cls]

    @classmethod
    def check_constraint(cls) -> str:
        vals = ", ".join(f"'{v}'" for v in cls.values())
        return f"booking_type IN ({vals})"


class CreatorType(str, Enum):
    INDIVIDUAL = 'individual'
    ORGANIZATION = 'organization'
    SYSTEM = 'system'

    @classmethod
    def values(cls) -> List[str]:
        return [e.value for e in cls]

    @classmethod
    def check_constraint(cls) -> str:
        vals = ", ".join(f"'{v}'" for v in cls.values())
        return f"created_by_type IN ({vals})"


class OwnerType(str, Enum):
    INDIVIDUAL = 'individual'
    ORGANIZATION = 'organization'
    SYSTEM = 'system'

    @classmethod
    def values(cls) -> List[str]:
        return [e.value for e in cls]

    @classmethod
    def check_constraint(cls) -> str:
        vals = ", ".join(f"'{v}'" for v in cls.values())
        return f"current_owner_type IN ({vals})"


class TransferStatus(str, Enum):
    PENDING = 'pending'
    APPROVED = 'approved'
    REJECTED = 'rejected'
    CANCELLED = 'cancelled'

    @classmethod
    def values(cls) -> List[str]:
        return [e.value for e in cls]

    @classmethod
    def check_constraint(cls) -> str:
        vals = ", ".join(f"'{v}'" for v in cls.values())
        return f"transfer_status IN ({vals})"


class DiscountType(str, Enum):
    PERCENTAGE = 'percentage'
    FIXED = 'fixed'

    @classmethod
    def values(cls) -> List[str]:
        return [e.value for e in cls]

    @classmethod
    def check_constraint(cls) -> str:
        vals = ", ".join(f"'{v}'" for v in cls.values())
        return f"discount_type IN ({vals})"


# ============================================================================
# ADMIN COMPLIANCE MODULE
# ============================================================================

class ComplianceCaseStatus(str, Enum):
    OPEN = 'open'
    IN_REVIEW = 'in_review'
    PENDING_INFO = 'pending_info'
    APPROVED = 'approved'
    REJECTED = 'rejected'
    ESCALATED = 'escalated'
    CLOSED = 'closed'

    @classmethod
    def values(cls) -> List[str]:
        return [e.value for e in cls]

    @classmethod
    def check_constraint(cls) -> str:
        vals = ", ".join(f"'{v}'" for v in cls.values())
        return f"status IN ({vals})"


class ComplianceCasePriority(str, Enum):
    CRITICAL = 'critical'
    HIGH = 'high'
    MEDIUM = 'medium'
    LOW = 'low'

    @classmethod
    def values(cls) -> List[str]:
        return [e.value for e in cls]

    @classmethod
    def check_constraint(cls) -> str:
        vals = ", ".join(f"'{v}'" for v in cls.values())
        return f"priority IN ({vals})"


class ComplianceCaseType(str, Enum):
    KYC_REVIEW = 'kyc_review'
    KYB_REVIEW = 'kyb_review'
    AML_ALERT = 'aml_alert'
    PAYOUT_REVIEW = 'payout_review'
    DATA_REQUEST = 'data_request'
    FLAG_ESCALATION = 'flag_escalation'
    LICENSE_REVIEW = 'license_review'
    OTHER = 'other'

    @classmethod
    def values(cls) -> List[str]:
        return [e.value for e in cls]

    @classmethod
    def check_constraint(cls) -> str:
        vals = ", ".join(f"'{v}'" for v in cls.values())
        return f"case_type IN ({vals})"


class DataSubjectRequestType(str, Enum):
    ACCESS = 'access'
    DELETION = 'deletion'
    RECTIFICATION = 'rectification'
    PORTABILITY = 'portability'
    OBJECTION = 'objection'

    @classmethod
    def values(cls) -> List[str]:
        return [e.value for e in cls]

    @classmethod
    def check_constraint(cls) -> str:
        vals = ", ".join(f"'{v}'" for v in cls.values())
        return f"request_type IN ({vals})"


class DataSubjectRequestStatus(str, Enum):
    PENDING = 'pending'
    VERIFIED = 'verified'
    PROCESSING = 'processing'
    COMPLETED = 'completed'
    REJECTED = 'rejected'
    EXPIRED = 'expired'

    @classmethod
    def values(cls) -> List[str]:
        return [e.value for e in cls]

    @classmethod
    def check_constraint(cls) -> str:
        vals = ", ".join(f"'{v}'" for v in cls.values())
        return f"status IN ({vals})"


class ComplianceReportType(str, Enum):
    KYC_SUMMARY = 'kyc_summary'
    AML_SUMMARY = 'aml_summary'
    PAYOUT_SUMMARY = 'payout_summary'
    CASE_HISTORY = 'case_history'
    AUDIT_TRAIL = 'audit_trail'
    RISK_ASSESSMENT = 'risk_assessment'
    REGULATORY_FILING = 'regulatory_filing'

    @classmethod
    def values(cls) -> List[str]:
        return [e.value for e in cls]

    @classmethod
    def check_constraint(cls) -> str:
        vals = ", ".join(f"'{v}'" for v in cls.values())
        return f"report_type IN ({vals})"


# ============================================================================
# ACCOMMODATION MODULE
# ============================================================================

class AccommodationPropertyType(str, Enum):
    HOTEL = 'hotel'
    APARTMENT = 'apartment'
    VILLA = 'villa'
    HOSTEL = 'hostel'
    GUESTHOUSE = 'guesthouse'

    @classmethod
    def values(cls) -> List[str]:
        return [e.value for e in cls]

    @classmethod
    def check_constraint(cls) -> str:
        vals = ", ".join(f"'{v}'" for v in cls.values())
        return f"property_type IN ({vals})"


class AccommodationListingType(str, Enum):
    ENTIRE_PLACE = 'entire_place'
    PRIVATE_ROOM = 'private_room'
    SHARED_ROOM = 'shared_room'

    @classmethod
    def values(cls) -> List[str]:
        return [e.value for e in cls]

    @classmethod
    def check_constraint(cls) -> str:
        vals = ", ".join(f"'{v}'" for v in cls.values())
        return f"listing_type IN ({vals})"


class AccommodationCancellationPolicy(str, Enum):
    FLEXIBLE = 'flexible'
    MODERATE = 'moderate'
    STRICT = 'strict'
    NON_REFUNDABLE = 'non_refundable'

    @classmethod
    def values(cls) -> List[str]:
        return [e.value for e in cls]

    @classmethod
    def check_constraint(cls) -> str:
        vals = ", ".join(f"'{v}'" for v in cls.values())
        return f"cancellation_policy IN ({vals})"


class AccommodationPropertyStatus(str, Enum):
    DRAFT = 'draft'
    PENDING = 'pending'
    APPROVED = 'approved'
    REJECTED = 'rejected'
    SUSPENDED = 'suspended'

    @classmethod
    def values(cls) -> List[str]:
        return [e.value for e in cls]

    @classmethod
    def check_constraint(cls) -> str:
        vals = ", ".join(f"'{v}'" for v in cls.values())
        return f"status IN ({vals})"


class AccommodationVerificationStatus(str, Enum):
    UNVERIFIED = 'unverified'
    PENDING = 'pending'
    VERIFIED = 'verified'
    REJECTED = 'rejected'

    @classmethod
    def values(cls) -> List[str]:
        return [e.value for e in cls]

    @classmethod
    def check_constraint(cls) -> str:
        vals = ", ".join(f"'{v}'" for v in cls.values())
        return f"verification_status IN ({vals})"


class AccommodationBookingStatus(str, Enum):
    DRAFT = 'draft'
    PENDING = 'pending'
    CONFIRMED = 'confirmed'
    CHECKED_IN = 'checked_in'
    CHECKED_OUT = 'checked_out'
    CANCELLED = 'cancelled'

    @classmethod
    def values(cls) -> List[str]:
        return [e.value for e in cls]

    @classmethod
    def check_constraint(cls) -> str:
        vals = ", ".join(f"'{v}'" for v in cls.values())
        return f"status IN ({vals})"


class AccommodationPaymentStatus(str, Enum):
    PENDING = 'pending'
    PROCESSING = 'processing'
    COMPLETED = 'completed'
    FAILED = 'failed'
    REFUNDED = 'refunded'

    @classmethod
    def values(cls) -> List[str]:
        return [e.value for e in cls]

    @classmethod
    def check_constraint(cls) -> str:
        vals = ", ".join(f"'{v}'" for v in cls.values())
        return f"payment_status IN ({vals})"


class AccommodationPaymentMethod(str, Enum):
    CARD = 'card'
    WALLET = 'wallet'
    BANK_TRANSFER = 'bank_transfer'
    CASH = 'cash'
    MOBILE_MONEY = 'mobile_money'

    @classmethod
    def values(cls) -> List[str]:
        return [e.value for e in cls]

    @classmethod
    def check_constraint(cls) -> str:
        vals = ", ".join(f"'{v}'" for v in cls.values())
        return f"payment_method IN ({vals})"


class AccommodationBlockedReason(str, Enum):
    MAINTENANCE = 'maintenance'
    BLOCKED = 'blocked'
    SEASONAL = 'seasonal'
    OWNER_USE = 'owner_use'

    @classmethod
    def values(cls) -> List[str]:
        return [e.value for e in cls]

    @classmethod
    def check_constraint(cls) -> str:
        vals = ", ".join(f"'{v}'" for v in cls.values())
        return f"reason IN ({vals})"


class AccommodationReviewStatus(str, Enum):
    PENDING = 'pending'
    APPROVED = 'approved'
    REJECTED = 'rejected'
    FLAGGED = 'flagged'

    @classmethod
    def values(cls) -> List[str]:
        return [e.value for e in cls]

    @classmethod
    def check_constraint(cls) -> str:
        vals = ", ".join(f"'{v}'" for v in cls.values())
        return f"status IN ({vals})"


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def get_all_enum_classes() -> List[type]:
    """Return all enum classes defined in this module."""
    import sys
    mod = sys.modules[__name__]
    enums = []
    for name in dir(mod):
        obj = getattr(mod, name)
        if isinstance(obj, type) and issubclass(obj, Enum) and obj is not Enum:
            enums.append(obj)
    return enums


def generate_all_check_constraints() -> dict:
    """Generate all CHECK constraint SQL for all enums."""
    constraints = {}
    for enum_cls in get_all_enum_classes():
        if hasattr(enum_cls, 'check_constraint'):
            # Use the enum class name as key, converted to snake_case
            key = enum_cls.__name__.lower()
            constraints[key] = enum_cls.check_constraint()
    return constraints


# ============================================================================
# MIGRATION HELPERS (for expand-contract pattern)
# ============================================================================

def get_enum_migration_info() -> List[dict]:
    """
    Returns migration info for each enum for the expand-contract pattern.
    Each dict contains: enum_class, column_name, table_name, constraint_name
    """
    # This is populated per-module during migration
    # Example:
    # {
    #     'enum_class': ServiceType,
    #     'column_name': 'service_type',
    #     'table_name': 'transport_ride_requests',
    #     'constraint_name': 'chk_service_type',
    #     'old_pg_type': 'servicetype',  # if migrating from existing PG enum
    # }
    return []