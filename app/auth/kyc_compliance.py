"""
Bank of Uganda compliant KYC tier system for Ugandan fintech platform.
Handles wallet payments, events, and organizational accounts with AML/CFT compliance.
"""

from functools import wraps
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, date
from flask import session, current_app, request, abort
from flask_login import current_user

from app.extensions import db
from app.identity.individuals.individual_verification import IndividualVerification
from app.profile.models import UserProfile, get_profile_by_user
from app.identity.models.organisation import Organisation
from app.identity.models.organisation_member import OrganisationMember
from app.audit.comprehensive_audit import AuditService, SecurityEventLog

# ─────────────────────────────────────────────────────────────────
# IDENTITY RULE — internal vs external IDs
# ─────────────────────────────────────────────────────────────────
# user.id          → BigInteger PK  — use for ALL DB queries,
#                    ForeignKey joins, filter_by, wallet lookups,
#                    transaction queries, any SQLAlchemy operation
#
# user.public_id   → UUID string    — use for URLs, API responses,
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
TIER_3_ENHANCED = 3      # + Proof of Address + TIN (UGX 7M daily limit)
TIER_4_PREMIUM = 4       # + Income source + Bank ref (UGX 20M daily limit)
TIER_5_CORPORATE = 5     # + KYB + License (Custom limits)

# ============================================================================
# Tier Requirements
# ============================================================================

TIER_REQUIREMENTS = {
    TIER_0_UNREGISTERED: {
        "name": "Unregistered",
        "description": "Email verification only",
        "required_documents": [],
        "required_scope": {},
        "aml_required": False,
    },
    TIER_1_BASIC: {
        "name": "Basic",
        "description": "Phone number and full name verification",
        "required_documents": ["phone_verified"],
        "required_scope": {"identity": True},
        "aml_required": False,
        "daily_limit": 400000,
        "monthly_limit": 2000000,
        "transaction_limit": 100000,
    },
    TIER_2_STANDARD: {
        "name": "Standard",
        "description": "National ID and selfie verification",
        "required_documents": ["phone_verified", "national_id", "selfie"],
        "required_scope": {"identity": True, "national_id": True, "biometric": True},
        "aml_required": True,
        "daily_limit": 2000000,
        "monthly_limit": 10000000,
        "transaction_limit": 500000,
    },
    TIER_3_ENHANCED: {
        "name": "Enhanced",
        "description": "Proof of address and TIN verification",
        "required_documents": ["phone_verified", "national_id", "selfie", "proof_of_address", "tin"],
        "required_scope": {"identity": True, "national_id": True, "biometric": True, "address": True, "tax": True},
        "aml_required": True,
        "pep_screening": True,
        "daily_limit": 7000000,
        "monthly_limit": 35000000,
        "transaction_limit": 2000000,
    },
    TIER_4_PREMIUM: {
        "name": "Premium",
        "description": "Income source and bank reference",
        "required_documents": ["phone_verified", "national_id", "selfie", "proof_of_address", "tin", "income_source", "bank_reference"],
        "required_scope": {"identity": True, "national_id": True, "biometric": True, "address": True, "tax": True, "financial": True},
        "aml_required": True,
        "pep_screening": True,
        "sanctions_check": True,
        "daily_limit": 20000000,
        "monthly_limit": 100000000,
        "transaction_limit": 5000000,
    },
    TIER_5_CORPORATE: {
        "name": "Corporate",
        "description": "KYB and business license verification",
        "required_documents": ["organisation_registration", "tin_certificate", "trading_license", "directors_list", "beneficial_owners"],
        "required_scope": {"kyb": True, "business_registration": True, "tax": True, "license": True},
        "aml_required": True,
        "pep_screening": True,
        "sanctions_check": True,
        "ubo_screening": True,
        "daily_limit": None,  # Custom limits
        "monthly_limit": None,
        "transaction_limit": None,
    }
}

# ============================================================================
# Limit Configuration (BoU Compliant)
# ============================================================================

DAILY_LIMITS = {
    TIER_0_UNREGISTERED: 0,
    TIER_1_BASIC: 400000,
    TIER_2_STANDARD: 2000000,
    TIER_3_ENHANCED: 7000000,
    TIER_4_PREMIUM: 20000000,
    TIER_5_CORPORATE: None  # Custom limits
}

MONTHLY_LIMITS = {
    TIER_0_UNREGISTERED: 0,
    TIER_1_BASIC: 2000000,
    TIER_2_STANDARD: 10000000,
    TIER_3_ENHANCED: 35000000,
    TIER_4_PREMIUM: 100000000,
    TIER_5_CORPORATE: None  # Custom limits
}

TRANSACTION_LIMITS = {
    TIER_0_UNREGISTERED: 0,
    TIER_1_BASIC: 100000,
    TIER_2_STANDARD: 500000,
    TIER_3_ENHANCED: 2000000,
    TIER_4_PREMIUM: 5000000,
    TIER_5_CORPORATE: None  # Custom limits
}

# ============================================================================
# Core KYC Functions
# ============================================================================

def calculate_kyc_tier(user_identifier) -> Dict[str, Any]:
    """
    Calculate user's KYC tier based on user identifier.
    Accepts either internal user ID (BIGINT) or public_id (UUID string).
    """
    from app.identity.models.user import User

    # Determine if identifier is integer (BIGINT id) or string (public_id)
    if isinstance(user_identifier, int):
        # It's an internal ID
        user = User.query.get(user_identifier)
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

    # Check requirements for each tier starting from highest
    achieved_tier = TIER_0_UNREGISTERED
    missing_requirements = []

    # Check Tier 1: Phone verification
    if profile and profile.phone_number and profile.phone_verified:
        achieved_tier = TIER_1_BASIC
    else:
        missing_requirements.append("phone_verified")
        return {
            "tier": TIER_0_UNREGISTERED,
            "tier_name": TIER_REQUIREMENTS[TIER_0_UNREGISTERED]["name"],
            "missing_requirements": missing_requirements,
            "limits": get_limits_for_tier(TIER_0_UNREGISTERED)
        }

    # Check Tier 2: National ID and selfie
    if verification and verification.status == "verified":
        scope = verification.scope or {}
        if scope.get("national_id") and scope.get("biometric"):
            achieved_tier = TIER_2_STANDARD
        else:
            if not scope.get("national_id"):
                missing_requirements.append("national_id")
            if not scope.get("biometric"):
                missing_requirements.append("selfie")

    # Check Tier 3: Address and TIN
    if achieved_tier >= TIER_2_STANDARD and verification:
        scope = verification.scope or {}
        if scope.get("address") and scope.get("tax"):
            achieved_tier = TIER_3_ENHANCED
        else:
            if not scope.get("address"):
                missing_requirements.append("proof_of_address")
            if not scope.get("tax"):
                missing_requirements.append("tin")

    # Check Tier 4: Financial information
    if achieved_tier >= TIER_3_ENHANCED and verification:
        scope = verification.scope or {}
        if scope.get("financial"):
            achieved_tier = TIER_4_PREMIUM
        else:
            missing_requirements.append("income_source")
            missing_requirements.append("bank_reference")

    # Check Tier 5: Corporate KYB (organization-based)
    # This requires separate organization verification

    return {
        "tier": achieved_tier,
        "tier_name": TIER_REQUIREMENTS[achieved_tier]["name"],
        "missing_requirements": missing_requirements,
        "limits": get_limits_for_tier(achieved_tier),
        "verification_id": verification.id if verification else None,
        "verification_status": verification.status if verification else None
    }

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
        user = User.query.get(user_identifier)
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
        from app.wallet.models import Transaction
        today = date.today()

        # Check if Transaction has user_id field
        if hasattr(Transaction, 'user_id'):
            # Calculate daily usage
            # RULE: Transaction.user_id is BigInteger FK — use user.id NOT public_id
            daily_total = db.session.query(db.func.sum(Transaction.amount)).filter(
                Transaction.user_id == user.id,
                db.func.date(Transaction.created_at) == today,
                Transaction.status == "completed"
            ).scalar() or 0

            # Calculate monthly usage
            # RULE: Transaction.user_id is BigInteger FK — use user.id NOT public_id
            month_start = date(today.year, today.month, 1)
            monthly_total = db.session.query(db.func.sum(Transaction.amount)).filter(
                Transaction.user_id == user.id,
                Transaction.created_at >= month_start,
                Transaction.status == "completed"
            ).scalar() or 0
        else:
            # Try to get wallet first, then transactions
            from app.wallet.models import Wallet
            wallet = Wallet.query.filter_by(user_id=user.id).first()
            if wallet:
                # Calculate daily usage via wallet
                daily_total = db.session.query(db.func.sum(Transaction.amount)).filter(
                    Transaction.wallet_id == wallet.id,
                    db.func.date(Transaction.created_at) == today,
                    Transaction.status == "completed"
                ).scalar() or 0

                # Calculate monthly usage
                month_start = date(today.year, today.month, 1)
                monthly_total = db.session.query(db.func.sum(Transaction.amount)).filter(
                    Transaction.wallet_id == wallet.id,
                    Transaction.created_at >= month_start,
                    Transaction.status == "completed"
                ).scalar() or 0
    except Exception as e:
        # Log error but continue without usage tracking
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
        user = User.query.get(user_identifier)
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

    # AML/CFT checks for large transactions
    if amount >= 5000000:  # UGX 5M threshold
        flag_for_aml_review(user.id, amount, "transaction")

    if amount >= 20000000:  # UGX 20M threshold (FIA reporting)
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
    """Decorator for organization-scoped operations requiring KYC tier."""
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

            # Check organization KYC status (simplified - implement full KYB later)
            org = Organisation.query.get(org_id)
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

            # TODO: Implement organization KYB tier checking
            # For now, check user's personal tier
            kyc_info = calculate_kyc_tier(current_user.id)  # Use internal BIGINT id
            if kyc_info["tier"] < min_tier:
                abort(403, description=f"Requires KYC tier {min_tier} for organization operations")

            return f(*args, **kwargs)
        return decorated_function
    return decorator

# ============================================================================
# AML/CFT Compliance Functions
# ============================================================================

def flag_for_aml_review(user_id: int, amount: float, transaction_type: str):
    """Flag transaction for AML review."""
    from app.identity.models.user import User
    user = User.query.get(user_id)
    if not user:
        raise ValueError(f"User with id {user_id} not found")

    AuditService.security(
        event_type="aml_review_flagged",
        severity="medium",
        description=f"Transaction flagged for AML review: UGX {amount:,} by user {user.public_id}",
        user_id=user.id,  # RULE: Audit service expects BigInteger user_id
        ip_address=request.remote_addr if request else None,
        extra_data={
            "amount": amount,
            "transaction_type": transaction_type,
            "threshold": 5000000
        }
    )

    # TODO: Add to AML review queue
    current_app.logger.warning(f"AML Review Flagged: User {user.public_id}, Amount UGX {amount:,}")

def report_to_fia(user_id: int, amount: float, transaction_type: str):
    """Report large transaction to Financial Intelligence Authority."""
    from app.identity.models.user import User
    user = User.query.get(user_id)
    if not user:
        raise ValueError(f"User with id {user_id} not found")

    AuditService.security(
        event_type="fia_report_generated",
        severity="high",
        description=f"FIA report generated for UGX {amount:,} transaction",
        user_id=user.id,  # RULE: Audit service expects BigInteger user_id
        ip_address=request.remote_addr if request else None,
        extra_data={
            "amount": amount,
            "transaction_type": transaction_type,
            "threshold": 20000000,
            "report_time": datetime.utcnow().isoformat()
        }
    )

    # TODO: Generate FIA report and store for submission
    current_app.logger.warning(f"FIA Report Required: User {user.public_id}, Amount UGX {amount:,}")

def check_pep_status(user_id: int) -> bool:
    """Check if user is a Politically Exposed Person."""
    from app.identity.models.user import User
    user = User.query.get(user_id)
    if not user:
        raise ValueError(f"User with id {user_id} not found")

    # TODO: Integrate with PEP database
    # For now, check against known indicators
    profile = get_profile_by_user(user.public_id)
    if profile and profile.full_name:
        # Simple check for titles indicating political position
        pep_titles = ["minister", "mp", "mps", "honorable", "honourable", "ambassador", "mayor"]
        full_name_lower = profile.full_name.lower()
        for title in pep_titles:
            if title in full_name_lower:
                return True
    return False

def check_sanctions_list(user_id: int) -> bool:
    """Check if user appears on sanctions lists."""
    from app.identity.models.user import User
    user = User.query.get(user_id)
    if not user:
        raise ValueError(f"User with id {user_id} not found")

    # TODO: Integrate with sanctions databases
    # For now, return False (not on sanctions list)
    return False

# ============================================================================
# Utility Functions
# ============================================================================

def get_user_kyc_tier(user_identifier) -> int:
    """Get user's KYC tier (simplified version)."""
    from app.identity.models.user import User

    # Determine if identifier is integer (BIGINT id) or string (public_id)
    if isinstance(user_identifier, int):
        user = User.query.get(user_identifier)
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
        user = User.query.get(user_identifier)
    else:
        user = User.query.filter_by(public_id=user_identifier).first()

    if not user:
        raise ValueError(f"User with identifier {user_identifier} not found")

    current_info = calculate_kyc_tier(user.id)  # Pass internal BIGINT id
    target_reqs = TIER_REQUIREMENTS[target_tier]["required_documents"]

    # Get current verification scope
    verification = IndividualVerification.query.filter_by(
        user_id=user.id  # Use internal BIGINT id
    ).order_by(IndividualVerification.requested_at.desc()).first()

    current_scope = verification.scope if verification and verification.scope else {}

    missing = []
    for req in target_reqs:
        # Map requirement to scope key
        scope_key = {
            "phone_verified": "phone",
            "national_id": "national_id",
            "selfie": "biometric",
            "proof_of_address": "address",
            "tin": "tax",
            "income_source": "financial",
            "bank_reference": "financial"
        }.get(req, req)

        if scope_key not in current_scope or not current_scope[scope_key]:
            missing.append(req)

    return missing

def can_upgrade_to_tier(user_identifier, target_tier: int) -> Tuple[bool, List[str]]:
    """Check if user can upgrade to target tier and return missing requirements."""
    current_tier = get_user_kyc_tier(user_identifier)

    if target_tier <= current_tier:
        return True, []  # Already at or above target tier

    missing = get_missing_requirements(user_identifier, target_tier)
    return len(missing) == 0, missing
