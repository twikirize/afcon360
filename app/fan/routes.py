# app/fan/routes.py
"""
Fan/User Portal - Accommodation, tourism, and personal dashboard
"""
import logging
from decimal import Decimal
from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from app.auth.decorators import require_role
from app.auth.kyc_compliance import calculate_kyc_tier, get_user_limits, check_transaction_allowed
from app.accommodation.services.search_service import get_property_by_identifier
from app.wallet.models.ledger import AccountModel
from app.wallet.services.wallet_service import WalletService
from app.extensions import db
from app.profile.models import get_profile_by_user  # 🆕 ADD THIS IMPORT

# Standardized blueprint name: fan
fan_bp = Blueprint("fan", __name__, url_prefix='/fan')

logger = logging.getLogger(__name__)

@fan_bp.route("/dashboard")
@login_required
def dashboard():
    """Fan main dashboard - Outlook 3-pane style"""
    # Get KYC information
    kyc_info = calculate_kyc_tier(current_user.id)
    user_limits = get_user_limits(current_user.id)

    # Get wallet balance using AccountModel
    # current_user.id is public_id (UUID), need internal id (BIGINT)
    from app.identity.models.user import User
    from app.wallet.models.ledger import AccountOwnerType
    user = User.query.filter_by(public_id=str(current_user.public_id)).first()
    internal_id = user.id if user else current_user.id
    
    account = AccountModel.query.filter_by(
        user_id=internal_id,
        owner_type=AccountOwnerType.USER
    ).first()
    if account:
        service = WalletService()
        wallet_balance = service.get_balance(internal_id)
    else:
        wallet_balance = Decimal('0')
    
    # For backward compatibility with templates
    wallet = account

    # 🆕 Get profile and completion percentage
    profile = get_profile_by_user(current_user.public_id)
    completion = profile.get_completion_percentage() if profile else 0

    # 🆕 User stats (placeholders - replace with actual queries later)
    stats = {
        'bookings_count': 0,
        'trips_count': 0,
        'stays_count': 0,
        'reviews_count': 0,
        'total_spent': 0
    }

    # 🆕 Upcoming events (placeholder - replace with actual EventService)
    upcoming_events = []
    try:
        from app.events.services import EventService
        if hasattr(EventService, 'get_upcoming_events'):
            upcoming_events = EventService.get_upcoming_events(limit=5)
    except ImportError:
        pass  # Events module not available yet

    # 🆕 Recent stays (placeholder - replace with actual accommodation service)
    recent_stays = []

    # 🆕 Recommended items (placeholder)
    recommended = []

    driver_status = None
    try:
        from app.transport.models import DriverProfile
        if user:
            driver_profile = DriverProfile.query.filter_by(user_id=user.id).first()
            if driver_profile:
                driver_status = getattr(driver_profile, "verification_status", None)
    except Exception:
        pass

    return render_template(
        "fan/dashboard.html",
        user=current_user,
        profile=profile,
        completion=completion,
        kyc_info=kyc_info,
        user_limits=user_limits,
        wallet=wallet,
        wallet_balance=wallet_balance,
        upcoming_events=upcoming_events,
        recent_stays=recent_stays,
        recommended=recommended,
        stats=stats,
        driver_status=driver_status,
    )

# ============================================================================
# KEEP ALL YOUR EXISTING ROUTES BELOW - DO NOT MODIFY
# ============================================================================

@fan_bp.route("/accommodation")
@login_required
def accommodation():
    """Browse accommodation"""
    # Get search parameters
    location = request.args.get('location', '')
    check_in = request.args.get('check_in', '')
    check_out = request.args.get('check_out', '')

    # In a real implementation, this would query the database
    # For now, we'll use a placeholder
    properties = []

    return render_template('fan/accommodation.html',
                          properties=properties,
                          location=location,
                          check_in=check_in,
                          check_out=check_out)

@fan_bp.route("/accommodation/<property_id>")
@login_required
def accommodation_detail(property_id):
    """View accommodation details"""
    property_data = get_property_by_identifier(property_id)
    if not property_data:
        return render_template('errors/404.html'), 404

    return render_template('fan/accommodation_detail.html', property=property_data)

@fan_bp.route("/my-bookings")
@login_required
def my_bookings():
    """View user's bookings"""
    # This would query the booking model
    # For now, return empty
    bookings = []

    return render_template('fan/my_bookings.html', bookings=bookings)

@fan_bp.route("/kyc-status")
@login_required
def kyc_status():
    """View and upgrade KYC status"""
    kyc_info = calculate_kyc_tier(current_user.id)
    limits = get_user_limits(current_user.id)

    return render_template('fan/kyc_status.html',
                          kyc_info=kyc_info,
                          limits=limits)

@fan_bp.route("/wallet")
@login_required
def wallet():
    """View wallet and transaction history"""
    from app.wallet.models.transaction import TransactionModel
    from app.identity.models.user import User
    from app.wallet.models.ledger import AccountOwnerType
    
    # Get account using new AccountModel
    # current_user.id is public_id (UUID), need internal id (BIGINT)
    user = User.query.filter_by(public_id=str(current_user.id)).first()
    internal_id = user.id if user else current_user.id
    
    account = AccountModel.query.filter_by(
        user_id=internal_id,
        owner_type=AccountOwnerType.USER
    ).first()
    
    # Get balance
    if account:
        service = WalletService()
        balance = service.get_balance(account.id)
    else:
        balance = Decimal('0')
    
    # Get transactions if account exists
    transactions = []
    if account:
        transactions = TransactionModel.query.filter_by(
            user_id=internal_id
        ).order_by(TransactionModel.created_at.desc()).limit(20).all()
    
    # For template compatibility
    wallet = account
    if wallet:
        wallet.balance_home = balance
        wallet.home_currency = account.currency if account else 'UGX'

    return render_template('fan/wallet.html',
                          wallet=wallet,
                          transactions=transactions)

@fan_bp.route("/check-transaction-limit", methods=["POST"])
@login_required
def check_transaction_limit():
    """Check if a transaction amount is allowed"""
    data = request.get_json()
    amount = data.get('amount', 0)

    try:
        amount_float = float(amount)
        allowed, reason = check_transaction_allowed(current_user.id, amount_float)

        return jsonify({
            'allowed': allowed,
            'reason': reason,
            'amount': amount_float
        })
    except ValueError:
        return jsonify({
            'allowed': False,
            'reason': 'Invalid amount format',
            'amount': amount
        }), 400

# Keep the original profile routes for backward compatibility
@fan_bp.route("/profile")
@login_required
def view_fan_profile():
    """View fan profile"""
    from app.fan.services.registry import get_or_create_fan
    from app.identity.models.user import User
    from app.wallet.models.ledger import AccountOwnerType
    
    # Get internal user ID
    user = User.query.filter_by(public_id=str(current_user.id)).first()
    internal_id = user.id if user else current_user.id
    
    account = AccountModel.query.filter_by(
        user_id=internal_id,
        owner_type=AccountOwnerType.USER,
    ).first()
    
    profile = get_or_create_fan(internal_id)
    
    # For template compatibility, use account as wallet
    return render_template("fan_profile.html", profile=profile, wallet=account)

@fan_bp.route("/profile/update", methods=["POST"])
@login_required
def update_fan_profile_route():
    """Update fan profile"""
    from app.fan.services.registry import update_fan_profile
    from app.identity.models.user import User
    
    # Get internal user ID
    user = User.query.filter_by(public_id=str(current_user.id)).first()
    internal_id = user.id if user else current_user.id
    
    name = request.form.get("name")
    nationality = request.form.get("nationality")
    favorite_team = request.form.get("favorite_team")
    avatar_url = request.form.get("avatar_url")
    update_fan_profile(internal_id, name, nationality, favorite_team, avatar_url)
    flash("Profile updated.", "success")
    return redirect(url_for("fan.view_fan_profile"))
