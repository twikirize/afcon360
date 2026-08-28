"""
Bank of Uganda compliant KYC tier system for Ugandan fintech platform.
Handles wallet payments, events, and organizational accounts with AML/CFT compliance.
"""

from functools import wraps
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timezone, date
from types import SimpleNamespace
from flask import session, current_app, request, abort
from flask_login import current_user

from app.extensions import db
from app.identity.individuals.individual_verification import IndividualVerification
from app.profile.models import UserProfile, get_profile_by_user, IMMUTABLE_AFTER_VERIFICATION
from app.identity.models.organisation import Organisation
from app.identity.models.organisation_member import OrganisationMember
from app.audit.comprehensive_audit import AuditService, SecurityEventLog

# Live, owner-configurable KYC settings. All tunables are described in
# app/kyc_config_schema and persisted in system_configs (category='kyc').
from app.kyc_config_schema import (
    DEFAULT_TIER_REQUIREMENTS,
    DEFAULT_ACTIVITY_TIER_REQUIREMENTS,
    get_tier_requirements,
    get_activity_tier_requirements,
    get_thresholds,
    is_requirement_enabled,
)
from collections.abc import Mapping


class _ConfigMapping(Mapping):
    """Read-only mapping backed by a live loader (refreshed from DB)."""

    def __init__(self, loader):
        self._loader = loader

    def __getitem__(self, key):
        return self._loader()[key]

    def __iter__(self):
        return iter(self._loader())

    def __len__(self):
        return len(self._loader())


# Proxies so existing call sites (including external modules and tests) keep
# working while always reflecting the current owner configuration.
TIER_REQUIREMENTS = _ConfigMapping(get_tier_requirements)
ACTIVITY_TIER_REQUIREMENTS = _ConfigMapping(get_activity_tier_requirements)
DAILY_LIMITS = _ConfigMapping(
    lambda: {t: get_tier_requirements()[t]["daily_limit"] for t in range(6)})
MONTHLY_LIMITS = _ConfigMapping(
    lambda: {t: get_tier_requirements()[t]["monthly_limit"] for t in range(6)})
TRANSACTION_LIMITS = _ConfigMapping(
    lambda: {t: get_tier_requirements()[t]["transaction_limit"] for t in range(6)})

# Maps a KYC requirement name to the scope flag produced by _aggregate_kyc_scope.
_KYC_SCOPE_MAP = {
    "phone_verified": "phone",
    "national_id": "national_id",
    "selfie": "biometric",
    "proof_of_address": "address",
    "tin": "tax",
    "income_source": "financial",
    "bank_reference": "financial",
    "organisation_registration": "kyb",
    "tin_certificate": "tax",
    "trading_license": "license",
    "directors_list": "ubo",
    "beneficial_owners": "ubo",
}

# ─────────────────────────────────────────────────────────────────
# IDENTITY RULE - internal vs external IDs
# ─────────────────────────────────────────────────────────────────
# user.id          → BigInteger PK  - use for ALL DB queries,
#                    ForeignKey joins, filter_by, wallet lookups,
#                    transaction queries, any SQLAlchemy operation
#
# user.public_id   → UUID string    - use for URLs, API responses,
#                    audit log descriptions, log messages,
#                    anything user-facing or externally visible
#
# NEVER pass public_id to a column defined as BigInteger or Integer.
# NEVER pass user.id to a URL parameter or API response.
# ─────────────────────────────────────────────────────────────────

# ============================================================================
# KYC Tier Constants (BoU Guidelines)
# ============================================================================

TIER_0_UNREGISTERED = 0  # Email only
TIER_1_BASIC = 1         # Phone + Name (UGX 400K daily limit)
TIER_2_STANDARD = 2      # + National ID + Selfie (UGX 2M daily limit)
TIER_3_ENHANCED = 3      # + Proof of Address (TIN configurable for individuals)
TIER_4_PREMIUM = 4       # + Income source + Bank ref (UGX 20M daily limit)
TIER_5_CORPORATE = 5     # + KYB + License (Custom limits)

# Individual TIN requirement is controlled by the kyc_require_tin toggle
# (see app/kyc_config_schema). It defaults to OFF (optional for individuals).

# Tier requirements are provided live via the TIER_REQUIREMENTS proxy (defined
# at the top of this file) which reads owner configuration from system_configs.
# The canonical defaults live in app/kyc_config_schema.

REQUIREMENT_LABELS = {
    "phone_verified": "Phone verification",
    "national_id": "National ID",
    "selfie": "Selfie / Biometric",
    "proof_of_address": "Proof of address",
    "tin": "TIN certificate",
    "income_source": "Income source",
    "bank_reference": "Bank reference",
    "organisation_registration": "Organisation registration",
    "tin_certificate": "TIN certificate",
    "trading_license": "Trading license",
    "directors_list": "Directors list",
    "beneficial_owners": "Beneficial owners",
}

# Activity -> minimum tier is provided live via the ACTIVITY_TIER_REQUIREMENTS
# proxy (defined at the top of this file).

# Transaction limits are provided live via the DAILY_LIMITS / MONTHLY_LIMITS /
# TRANSACTION_LIMITS proxies (defined at the top of this file).

# ============================================================================
# Core KYC Functions
# ============================================================================

def _label_requirements(reqs: List[str]) -> List[str]:
    return [REQUIREMENT_LABELS.get(r, r.replace("_", " ").title()) for r in reqs]


def _get_next_tier_info(current_tier: int) -> Dict[str, Any]:
    next_tier = current_tier + 1
    if next_tier > TIER_5_CORPORATE:
        return {
            "next_tier": None,
            "next_tier_name": None,
            "next_tier_requirements": [],
            "next_tier_requirements_labels": [],
        }
    reqs = TIER_REQUIREMENTS[next_tier]["required_documents"]
    return {
        "next_tier": next_tier,
        "next_tier_name": TIER_REQUIREMENTS[next_tier]["name"],
        "next_tier_requirements": reqs,
        "next_tier_requirements_labels": _label_requirements(reqs),
    }


def _build_tier_response(
    achieved_tier: int,
    missing_requirements: List[str],
    verification,
    profile,
    fulfillment_percentage: int,
) -> Dict[str, Any]:
    next_tier_info = _get_next_tier_info(achieved_tier)
    status = getattr(verification, "status", None) if verification else None
    status = (status or "pending").lower()
    is_verified = status in {"verified", "approved"}

    return {
        "tier": achieved_tier,
        "tier_name": TIER_REQUIREMENTS[achieved_tier]["name"],
        "tier_description": TIER_REQUIREMENTS[achieved_tier]["description"],
        "verification_status": status,
        "is_verified": is_verified,
        "fulfillment_percentage": fulfillment_percentage,
        "missing_requirements": missing_requirements,
        "missing_requirements_labels": _label_requirements(missing_requirements),
        **next_tier_info,
        "limits": get_limits_for_tier(achieved_tier),
        "verification_id": verification.id if verification else None,
        "immutable_fields": sorted(IMMUTABLE_AFTER_VERIFICATION),
        "activities_restricted": {
            activity: tier for activity, tier in ACTIVITY_TIER_REQUIREMENTS.items()
            if achieved_tier < tier
        },
    }


def calculate_kyc_tier(user_identifier) -> Dict[str, Any]:
    """
    Calculate user's KYC tier based on user identifier.
    Accepts either internal user ID (BIGINT) or public_id (UUID string).
    """
    from app.identity.models.user import User

    # Determine if identifier is integer (BIGINT id) or string (public_id)
    if isinstance(user_identifier, int):
        # It's an internal ID
        user = db.session.get(User, user_identifier)
    else:
        # Assume it's a public_id (UUID string)
        user = User.query.filter_by(public_id=user_identifier).first()

    if not user:
        raise ValueError(f"User with identifier {user_identifier} not found")

    # Get user profile using public_id (UUID string)
    profile = get_profile_by_user(user.public_id)

    # Get latest verification - this expects INTEGER user_id (BIGINT)
    verification = IndividualVerification.query.filter_by(
        user_id=user.id  # Use internal BIGINT id
    ).order_by(IndividualVerification.requested_at.desc()).first()

    # Manual KYC submissions are the source reviewed by compliance. Prefer a
    # newer manual decision over an older provider/profile verification row so
    # rejection or revocation is visible everywhere immediately.
    from app.kyc.models import KycRecord

    manual_record = KycRecord.query.filter_by(user_id=user.id).order_by(
        KycRecord.created_at.desc(), KycRecord.id.desc()
    ).first()

    def _verification_time(value):
        if value is None:
            return datetime.min.replace(tzinfo=timezone.utc)
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value

    if manual_record and (
        verification is None
        or _verification_time(manual_record.created_at)
        >= _verification_time(verification.requested_at)
    ):
        manual_status = (manual_record.status or "pending").lower()
        verification = SimpleNamespace(
            id=manual_record.id,
            status=manual_status,
            requested_at=manual_record.created_at,
            # Harmonised scope across all document types (see helper above).
            scope=_aggregate_kyc_scope(user.id),
        )

    # Check requirements for each tier starting from highest
    achieved_tier = TIER_0_UNREGISTERED
    missing_requirements = []

    # Check Tier 1: Phone verification. User flags are canonical because the
    # phone verification flow updates User, while legacy profile copies may lag.
    phone_verified = bool(
        getattr(user, "phone_verified", False)
        and (getattr(user, "phone_verified_at", None) or getattr(user, "phone", None))
    )
    if phone_verified:
        achieved_tier = TIER_1_BASIC
    else:
        missing_requirements.append("phone_verified")
        if verification and verification.status not in {"verified", "approved"}:
            missing_requirements.append("kyc_verification")
        return _build_tier_response(
            TIER_0_UNREGISTERED,
            missing_requirements,
            verification,
            profile,
            15 if getattr(user, "phone", None) else 0,
        )

    # Tiers 2-4 are evaluated against the live, owner-configurable requirement
    # definitions. National ID verified also auto-satisfies proof-of-residence
    # (handled in _aggregate_kyc_scope). Each requirement is skipped when the
    # Owner/Super Admin has relaxed it via its kyc_require_<req> toggle.
    if verification and verification.status in {"verified", "approved"}:
        scope = verification.scope or {}
        for tier in (TIER_2_STANDARD, TIER_3_ENHANCED, TIER_4_PREMIUM):
            tier_missing = []
            for req in TIER_REQUIREMENTS[tier]["required_documents"]:
                if not is_requirement_enabled(req):
                    continue
                if not scope.get(_KYC_SCOPE_MAP.get(req, req)):
                    tier_missing.append(req)
            if not tier_missing:
                achieved_tier = tier
            else:
                missing_requirements.extend(tier_missing)
                break

    # Tier 5 (Corporate) is reached via separate KYB verification.

    # Calculate fulfillment percentage
    # Tiers: 0=0%, 1=25%, 2=50%, 3=75%, 4=100%
    fulfillment_percentage = min(100, achieved_tier * 25)
    if achieved_tier == 0 and getattr(user, "phone", None):
        fulfillment_percentage = 15  # phone entered but not verified yet

    return _build_tier_response(
        achieved_tier,
        missing_requirements,
        verification,
        profile,
        fulfillment_percentage,
    )

def _kyc_requirement_enabled(requirement: str) -> bool:
    """
    Whether a given KYC document requirement is currently enforced.

    Delegates to the owner-configurable toggle ``kyc_require_<requirement>``
    (see app/kyc_config_schema). When no config row exists the requirement
    defaults to ENABLED (enforced), preserving the previous behaviour.
    """
    return is_requirement_enabled(requirement)


def _aggregate_kyc_scope(user_id: int) -> Dict[str, bool]:
    """
    Build a consolidated KYC scope across ALL of a user's KYC records.

    The upload flow accepts several document types (national_id, passport,
    proof_of_address, tin, income_source, bank_reference, ...). Previously the
    tier calculator only inspected the *latest* record and could only derive
    ``national_id`` + ``biometric``, so a verified proof-of-address never
    advanced the user to Tier 3.

    This helper harmonises the logic:
      * ``national_id`` — any verified National ID record (NIRA or uploaded).
      * ``biometric``    — any record carrying a selfie.
      * ``address``      — an explicit proof-of-address record, OR auto-satisfied
                          from a verified National ID, because the Uganda NIN
                          card carries the holder's registered address.
      * ``tax``/``financial`` stay False here — they require their own uploads
        (TIN / income source / bank reference) and are intentionally separate.
    """
    from app.kyc.models import KycRecord
    from datetime import datetime, timezone

    VERIFIED = {"verified", "approved"}
    scope = {
        "national_id": False,
        "biometric": False,
        "address": False,
        "tax": False,
        "financial": False,
    }

    now = datetime.now(timezone.utc)

    for record in KycRecord.query.filter_by(user_id=user_id).all():
        if (record.status or "pending").lower() not in VERIFIED:
            continue
        # Exclude expired documents
        if record.expiry_date:
            # Normalize to timezone-aware for comparison
            expiry = record.expiry_date
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
            if expiry < now:
                continue
        has_doc = bool(record.document_url)
        rt = (record.record_type or "").lower()
        it = (record.id_type or "").lower()

        is_national_id = it == "national_id" or rt.endswith("national_id")
        is_address_doc = (
            it in ("address_proof", "proof_of_address")
            or rt in ("address_verification", "proof_of_address_verification")
        )

        if is_national_id and has_doc:
            scope["national_id"] = True
        if bool(record.selfie_url):
            scope["biometric"] = True
        if is_address_doc and has_doc:
            scope["address"] = True
        # Tier 4 financial evidence: either an income-source or bank-reference
        # document (verified) satisfies the single "financial" scope flag.
        if it in ("income_source", "bank_reference") and has_doc:
            scope["financial"] = True

    # Uganda NIN carries the holder's registered address: a verified National ID
    # satisfies the Tier 3 proof-of-residence requirement.
    if scope["national_id"]:
        scope["address"] = True

    return scope


def get_limits_for_tier(tier: int) -> Dict[str, Optional[int]]:
    """Get limits for a specific tier."""
    return {
        "daily": DAILY_LIMITS.get(tier),
        "monthly": MONTHLY_LIMITS.get(tier),
        "transaction": TRANSACTION_LIMITS.get(tier),
        "tier_info": TIER_REQUIREMENTS.get(tier, {})
    }

def get_user_limits(user_identifier) -> Dict[str, Any]:
    """Get current user's limits based on their KYC tier."""
    from app.identity.models.user import User

    # Determine if identifier is integer (BIGINT id) or string (public_id)
    if isinstance(user_identifier, int):
        user = db.session.get(User, user_identifier)
    else:
        user = User.query.filter_by(public_id=user_identifier).first()

    if not user:
        raise ValueError(f"User with identifier {user_identifier} not found")

    kyc_info = calculate_kyc_tier(user.id)  # Pass internal BIGINT id
    limits = kyc_info["limits"]
    public_id = user.public_id

    # Initialize usage tracking with defaults
    daily_total = 0
    monthly_total = 0

    try:
        # Try to import Transaction model
        from app.wallet.models.transaction import TransactionModel
        from app.wallet.models.ledger import AccountModel, AccountOwnerType
        today = date.today()

        # Get user's account first (filter by owner_type for users)
        account = AccountModel.query.filter_by(
            user_id=user.id,
            owner_type=AccountOwnerType.USER
        ).first()
        if account:
            # Calculate daily usage via account.id
            daily_total = db.session.query(db.func.sum(TransactionModel.amount)).filter(
                TransactionModel.account_id == account.id,
                db.func.date(TransactionModel.created_at) == today,
                TransactionModel.status == "completed"
            ).scalar() or 0

            # Calculate monthly usage
            month_start = date(today.year, today.month, 1)
            monthly_total = db.session.query(db.func.sum(TransactionModel.amount)).filter(
                TransactionModel.account_id == account.id,
                TransactionModel.created_at >= month_start,
                TransactionModel.status == "completed"
            ).scalar() or 0
        else:
            daily_total = 0
            monthly_total = 0
    except AttributeError as e:
        # Log error but continue without usage tracking
        current_app.logger.warning(f"Could not calculate transaction usage for user {user_identifier}: {e}")
        daily_total = 0
        monthly_total = 0
    except Exception as e:
        current_app.logger.warning(f"Could not calculate transaction usage for user {user_identifier}: {e}")
        daily_total = 0
        monthly_total = 0

    limits["daily_used"] = daily_total
    limits["monthly_used"] = monthly_total
    limits["daily_remaining"] = limits["daily"] - daily_total if limits["daily"] else None
    limits["monthly_remaining"] = limits["monthly"] - monthly_total if limits["monthly"] else None

    return limits

def check_transaction_allowed(user_identifier, amount: float) -> Tuple[bool, str]:
    """
    Check if transaction is allowed based on KYC tier and limits.
    Returns (allowed, reason)
    """
    from app.identity.models.user import User

    # Determine if identifier is integer (BIGINT id) or string (public_id)
    if isinstance(user_identifier, int):
        user = db.session.get(User, user_identifier)
    else:
        user = User.query.filter_by(public_id=user_identifier).first()

    if not user:
        raise ValueError(f"User with identifier {user_identifier} not found")

    kyc_info = calculate_kyc_tier(user.id)  # Pass internal BIGINT id
    tier = kyc_info["tier"]
    limits = kyc_info["limits"]

    # Check transaction limit
    if limits["transaction"] and amount > limits["transaction"]:
        return False, f"Transaction exceeds tier {tier} limit of UGX {limits['transaction']:,}"

    # Check daily limit
    user_limits = get_user_limits(user_identifier)
    if user_limits["daily_remaining"] is not None and amount > user_limits["daily_remaining"]:
        return False, f"Transaction would exceed daily limit of UGX {limits['daily']:,}"

    # Check monthly limit
    if user_limits["monthly_remaining"] is not None and amount > user_limits["monthly_remaining"]:
        return False, f"Transaction would exceed monthly limit of UGX {limits['monthly']:,}"

    # AML/CFT checks for large transactions (thresholds are owner-configurable).
    thresholds = get_thresholds()
    if amount >= thresholds["aml_review"]:
        flag_for_aml_review(user.id, amount, "transaction")

    if amount >= thresholds["fia_report"]:
        report_to_fia(user.id, amount, "transaction")

    return True, "Transaction allowed"

# ============================================================================
# Decorators
# ============================================================================

def require_kyc_tier(min_tier: int):
    """Decorator to require minimum KYC tier for route access."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                abort(401)

            # RULE: calculate_kyc_tier expects either integer (user.id) or string (public_id)
            # Since user.id is BigInteger, we should pass it for database operations
            kyc_info = calculate_kyc_tier(current_user.id)
            if kyc_info["tier"] < min_tier:
                # Store attempted URL for redirect after KYC upgrade
                session['kyc_redirect_url'] = request.url
                session['required_tier'] = min_tier

                # Log the attempt - use public_id for audit descriptions, but user.id for user_id parameter
                AuditService.security(
                    event_type="kyc_tier_blocked",
                    severity="medium",
                    description=f"User {current_user.public_id} attempted to access {request.url} requiring tier {min_tier}",
                    user_id=current_user.id,  # RULE: Audit service expects BigInteger user_id
                    ip_address=request.remote_addr
                )

                # Redirect to KYC upgrade page
                from flask import redirect, url_for
                return redirect(url_for('kyc.upgrade'))

            return f(*args, **kwargs)
        return decorated_function
    return decorator

def require_kyc_tier_for_amount(amount_param: str = 'amount'):
    """
    Decorator to check if user's KYC tier allows transaction amount.
    Expects amount parameter in request args or form.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                abort(401)

            # Get amount from request
            amount = None
            if request.method == 'GET':
                amount = request.args.get(amount_param)
            else:
                amount = request.form.get(amount_param) or request.json.get(amount_param) if request.is_json else None

            if amount:
                try:
                    amount_float = float(amount)
                    # RULE: check_transaction_allowed expects either integer (user.id) or string (public_id)
                    # Since user.id is BigInteger, we should pass it for database operations
                    allowed, reason = check_transaction_allowed(current_user.id, amount_float)
                    if not allowed:
                        AuditService.security(
                            event_type="transaction_limit_exceeded",
                            severity="high",
                            description=f"User {current_user.public_id} attempted transaction of UGX {amount_float:,}: {reason}",
                            user_id=current_user.id,  # RULE: Audit service expects BigInteger user_id
                            ip_address=request.remote_addr
                        )
                        abort(403, description=reason)
                except ValueError:
                    abort(400, description="Invalid amount format")

            return f(*args, **kwargs)
        return decorated_function
    return decorator

def require_org_kyc_tier(min_tier: int, org_id_param: str = 'org_id'):
    """Decorator for organization-scoped operations requiring KYB level.
    
    Args:
        min_tier: Minimum KYB level required (1 = operational KYB, 2 = full KYB)
        org_id_param: Parameter name for organization ID
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                abort(401)

            # Get organization ID
            org_id = kwargs.get(org_id_param) or request.args.get(org_id_param) or \
                    request.form.get(org_id_param) or (request.json.get(org_id_param) if request.is_json else None)

            if not org_id:
                abort(400, description="Organization ID required")

            # Check organization KYB status
            org = db.session.get(Organisation, org_id)
            if not org:
                abort(404, description="Organization not found")

            # Check if user is member
            membership = OrganisationMember.query.filter_by(
                organisation_id=org_id,
                user_id=current_user.id,
                is_active=True
            ).first()

            if not membership:
                abort(403, description="Not a member of this organization")

            # Check organisation KYB status (authoritative source)
            from app.identity.services.organisation_kyb_service import OrganisationKYBService
            kyb_status = OrganisationKYBService.compute_status(org)
            
            # Map min_tier to KYB level requirements
            # min_tier 1 = operational KYB (L1), min_tier 2 = full KYB (L2)
            if min_tier <= 1:
                if not kyb_status["is_operational_kyb"]:
                    abort(403, description="Organisation requires operational KYB (business registration, identity, tax verification) to perform this operation")
            elif min_tier >= 2:
                if not kyb_status["is_full_kyb"]:
                    abort(403, description="Organisation requires full KYB (including UBO, sanctions screening, source of funds) to perform this operation")

            return f(*args, **kwargs)
        return decorated_function
    return decorator

# ============================================================================
# AML/CFT Compliance Functions
# ============================================================================

def flag_for_aml_review(user_id: int, amount: float, transaction_type: str):
    """Flag transaction for AML review."""
    from app.identity.models.user import User
    user = db.session.get(User, user_id)
    if not user:
        raise ValueError(f"User with id {user_id} not found")

    threshold = get_thresholds()["aml_review"]
    AuditService.security(
        event_type="aml_review_flagged",
        severity="medium",
        description=f"Transaction flagged for AML review: UGX {amount:,} by user {user.public_id}",
        user_id=user.id,  # RULE: Audit service expects BigInteger user_id
        ip_address=request.remote_addr if request else None,
        extra_data={
            "amount": amount,
            "transaction_type": transaction_type,
            "threshold": threshold
        }
    )

    # TODO: Add to AML review queue
    current_app.logger.warning(f"AML Review Flagged: User {user.public_id}, Amount UGX {amount:,}")

def report_to_fia(user_id: int, amount: float, transaction_type: str):
    """Report large transaction to Financial Intelligence Authority."""
    from app.identity.models.user import User
    user = db.session.get(User, user_id)
    if not user:
        raise ValueError(f"User with id {user_id} not found")

    threshold = get_thresholds()["fia_report"]
    AuditService.security(
        event_type="fia_report_generated",
        severity="high",
        description=f"FIA report generated for UGX {amount:,} transaction",
        user_id=user.id,  # RULE: Audit service expects BigInteger user_id
        ip_address=request.remote_addr if request else None,
        extra_data={
            "amount": amount,
            "transaction_type": transaction_type,
            "threshold": threshold,
            "report_time": datetime.now(timezone.utc).isoformat()
        }
    )

    # TODO: Generate FIA report and store for submission
    current_app.logger.warning(f"FIA Report Required: User {user.public_id}, Amount UGX {amount:,}")
def check_pep_status(user_id: int) -> str:
    """Check if user is a Politically Exposed Person.
    
    Returns:
        'NOT_SCREENED' - No screening performed (no provider configured)
        'CLEAR' - Screened and no match found
        'MATCH' - Potential PEP match found
        'MANUAL_REVIEW' - Requires manual review
        'ERROR' - Screening error
    
    NOTE: Currently no real PEP screening provider is integrated.
    This function returns 'NOT_SCREENED' to avoid false compliance representation.
    """
    from app.identity.models.user import User
    user = db.session.get(User, user_id)
    if not user:
        raise ValueError(f"User with id {user_id} not found")

    # No real PEP screening provider integrated
    # Name-based check is NOT a compliance control - it's a placeholder
    return "NOT_SCREENED"


def check_sanctions_list(user_id: int) -> str:
    """Check if user appears on sanctions lists.
    
    Returns:
        'NOT_SCREENED' - No screening performed (no provider configured)
        'CLEAR' - Screened and no match found
        'MATCH' - Potential sanctions match found
        'MANUAL_REVIEW' - Requires manual review
        'ERROR' - Screening error
    
    NOTE: Currently no real sanctions screening provider is integrated.
    This function returns 'NOT_SCREENED' to avoid false compliance representation.
    """
    from app.identity.models.user import User
    user = db.session.get(User, user_id)
    if not user:
        raise ValueError(f"User with id {user_id} not found")

    # No real sanctions screening provider integrated
    return "NOT_SCREENED"

# ============================================================================
# Utility Functions
# ============================================================================

def get_user_kyc_tier(user_identifier) -> int:
    """Get user's KYC tier (simplified version)."""
    from app.identity.models.user import User

    # Determine if identifier is integer (BIGINT id) or string (public_id)
    if isinstance(user_identifier, int):
        user = db.session.get(User, user_identifier)
    else:
        user = User.query.filter_by(public_id=user_identifier).first()

    if not user:
        raise ValueError(f"User with identifier {user_identifier} not found")

    kyc_info = calculate_kyc_tier(user.id)  # Pass internal BIGINT id
    return kyc_info["tier"]

def get_missing_requirements(user_identifier, target_tier: int) -> List[str]:
    """Get requirements missing for target tier."""
    from app.identity.models.user import User

    # Determine if identifier is integer (BIGINT id) or string (public_id)
    if isinstance(user_identifier, int):
        user = db.session.get(User, user_identifier)
    else:
        user = User.query.filter_by(public_id=user_identifier).first()

    if not user:
        raise ValueError(f"User with identifier {user_identifier} not found")

    current_info = calculate_kyc_tier(user.id)  # Pass internal BIGINT id
    target_reqs = TIER_REQUIREMENTS[target_tier]["required_documents"]

    # Use the consolidated scope so a verified National ID also satisfies
    # proof-of-residence, exactly as calculate_kyc_tier does.
    current_scope = _aggregate_kyc_scope(user.id)

    missing = []
    for req in target_reqs:
        # Skip requirements the Owner/Super Admin have disabled platform-wide.
        if not is_requirement_enabled(req):
            continue
        scope_key = _KYC_SCOPE_MAP.get(req, req)
        if not current_scope.get(scope_key):
            missing.append(req)

    return missing

def can_upgrade_to_tier(user_identifier, target_tier: int) -> Tuple[bool, List[str]]:
    """Check if user can upgrade to target tier and return missing requirements."""
    current_tier = get_user_kyc_tier(user_identifier)

    if target_tier <= current_tier:
        return True, []  # Already at or above target tier

    missing = get_missing_requirements(user_identifier, target_tier)
    return len(missing) == 0, missing

