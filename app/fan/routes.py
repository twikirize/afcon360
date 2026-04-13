# app/fan/routes.py
"""
Fan/User Portal - Accommodation, tourism, and personal dashboard
"""
import logging
from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from app.auth.decorators import require_role
from app.auth.kyc_compliance import calculate_kyc_tier, get_user_limits, check_transaction_allowed
from app.accommodation.services.search_service import get_property_by_identifier
from app.wallet.models import Wallet
from app.extensions import db

# Standardized blueprint name: fan
fan_bp = Blueprint("fan", __name__)

logger = logging.getLogger(__name__)

@fan_bp.route("/dashboard")
@login_required
@require_role('fan')
def dashboard():
    """Fan main dashboard"""
    # Get KYC information
    kyc_info = calculate_kyc_tier(current_user.id)
    user_limits = get_user_limits(current_user.id)

    # Get wallet balance
    wallet = Wallet.query.filter_by(user_id=current_user.public_id).first()

    return render_template(
        "fan/dashboard.html",
        kyc_info=kyc_info,
        user_limits=user_limits,
        wallet=wallet
    )

@fan_bp.route("/accommodation")
@login_required
@require_role('fan')
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
@require_role('fan')
def accommodation_detail(property_id):
    """View accommodation details"""
    property_data = get_property_by_identifier(property_id)
    if not property_data:
        return render_template('errors/404.html'), 404

    return render_template('fan/accommodation_detail.html', property=property_data)

@fan_bp.route("/my-bookings")
@login_required
@require_role('fan')
def my_bookings():
    """View user's bookings"""
    # This would query the booking model
    # For now, return empty
    bookings = []

    return render_template('fan/my_bookings.html', bookings=bookings)

@fan_bp.route("/kyc-status")
@login_required
@require_role('fan')
def kyc_status():
    """View and upgrade KYC status"""
    kyc_info = calculate_kyc_tier(current_user.id)
    limits = get_user_limits(current_user.id)

    return render_template('fan/kyc_status.html',
                          kyc_info=kyc_info,
                          limits=limits)

@fan_bp.route("/wallet")
@login_required
@require_role('fan')
def wallet():
    """View wallet and transaction history"""
    wallet = Wallet.query.filter_by(user_id=current_user.public_id).first()

    # Get transactions if wallet exists
    transactions = []
    if wallet:
        transactions = wallet.transactions.order_by(
            db.desc('created_at')
        ).limit(20).all()

    return render_template('fan/wallet.html',
                          wallet=wallet,
                          transactions=transactions)

@fan_bp.route("/check-transaction-limit", methods=["POST"])
@login_required
@require_role('fan')
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
@require_role('fan')
def view_fan_profile():
    """View fan profile"""
    from app.wallet import get_or_create_wallet
    from app.fan.services.registry import get_or_create_fan

    wallet = get_or_create_wallet(current_user.id)
    profile = get_or_create_fan(wallet.user_id)
    return render_template("fan_profile.html", profile=profile, wallet=wallet)

@fan_bp.route("/profile/update", methods=["POST"])
@login_required
@require_role('fan')
def update_fan_profile_route():
    """Update fan profile"""
    from app.wallet import get_or_create_wallet
    from app.fan.services.registry import update_fan_profile

    wallet = get_or_create_wallet(current_user.id)
    name = request.form.get("name")
    nationality = request.form.get("nationality")
    favorite_team = request.form.get("favorite_team")
    avatar_url = request.form.get("avatar_url")
    update_fan_profile(wallet.user_id, name, nationality, favorite_team, avatar_url)
    flash("Profile updated.", "success")
    return redirect(url_for("fan.view_fan_profile"))
