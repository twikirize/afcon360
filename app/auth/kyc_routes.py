"""
KYC Routes for tier upgrades and compliance information.
"""
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user
from app.auth.decorators import require_role
from app.auth.kyc_compliance import (
    calculate_kyc_tier, get_user_limits, can_upgrade_to_tier,
    TIER_0_UNREGISTERED, TIER_1_BASIC, TIER_2_STANDARD,
    TIER_3_ENHANCED, TIER_4_PREMIUM, TIER_5_CORPORATE,
    TIER_REQUIREMENTS
)
from app.audit.forensic_audit import ForensicAuditService
from app.utils.id_guard import IDGuard

auth_kyc_bp = Blueprint('auth_kyc', __name__, url_prefix='/auth/kyc')

@auth_kyc_bp.route('/')
@login_required
def overview():
    """Display user's current KYC tier and limits."""
    # Use public_id for audit logging
    public_id = current_user.public_id

    # Calculate KYC info
    kyc_info = calculate_kyc_tier(current_user.id)
    limits = get_user_limits(current_user.id)

    # Log access
    ForensicAuditService.log_attempt(
        entity_type="kyc_info",
        entity_id=public_id,
        action="view",
        user_id=current_user.id,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string if request.user_agent else None
    )

    return render_template('kyc/overview.html',
                         kyc_info=kyc_info,
                         limits=limits,
                         tier_names=TIER_REQUIREMENTS)

@auth_kyc_bp.route('/upgrade')
@login_required
def upgrade():
    """Show KYC upgrade options based on current tier."""
    current_tier = calculate_kyc_tier(current_user.id)['tier']

    # Determine which tiers are available for upgrade
    available_upgrades = []
    for target_tier in range(current_tier + 1, 6):
        can_upgrade, missing = can_upgrade_to_tier(current_user.id, target_tier)
        available_upgrades.append({
            'tier': target_tier,
            'name': TIER_REQUIREMENTS[target_tier]['name'],
            'description': TIER_REQUIREMENTS[target_tier]['description'],
            'can_upgrade': can_upgrade,
            'missing_requirements': missing,
            'limits': TIER_REQUIREMENTS[target_tier].get('daily_limit'),
            'required_documents': TIER_REQUIREMENTS[target_tier]['required_documents']
        })

    # Log upgrade page access
    ForensicAuditService.log_attempt(
        entity_type="kyc_upgrade",
        entity_id=current_user.public_id,
        action="view_upgrade_options",
        user_id=current_user.id,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string if request.user_agent else None
    )

    return render_template('kyc/upgrade.html',
                         current_tier=current_tier,
                         current_tier_name=TIER_REQUIREMENTS[current_tier]['name'],
                         available_upgrades=available_upgrades)

@auth_kyc_bp.route('/upgrade/<int:target_tier>', methods=['POST'])
@login_required
def submit_upgrade(target_tier):
    """Submit documents for KYC tier upgrade."""
    # Validate target tier
    if target_tier < 1 or target_tier > 5:
        flash('Invalid KYC tier', 'danger')
        return redirect(url_for('auth_kyc.upgrade'))

    current_tier = calculate_kyc_tier(current_user.id)['tier']
    if target_tier <= current_tier:
        flash(f'You are already at tier {current_tier} or higher', 'info')
        return redirect(url_for('auth_kyc.overview'))

    # Check if upgrade is possible
    can_upgrade, missing = can_upgrade_to_tier(current_user.id, target_tier)
    if not can_upgrade:
        flash(f'Cannot upgrade to tier {target_tier}. Missing: {", ".join(missing)}', 'warning')
        return redirect(url_for('auth_kyc.upgrade'))

    # In a real implementation, this would start a verification process
    # For now, we'll just log the attempt
    ForensicAuditService.log_attempt(
        entity_type="kyc_upgrade",
        entity_id=current_user.public_id,
        action="submit_upgrade",
        user_id=current_user.id,
        ip_address=request.remote_addr,
        details={"target_tier": target_tier}
    )

    flash(f'Upgrade to tier {target_tier} submitted for verification. You will be notified when processed.', 'success')
    return redirect(url_for('auth_kyc.overview'))

@auth_kyc_bp.route('/limits')
@login_required
def limits():
    """Display current usage and limits."""
    limits_info = get_user_limits(current_user.id)

    ForensicAuditService.log_attempt(
        entity_type="kyc_limits",
        entity_id=current_user.public_id,
        action="view_limits",
        user_id=current_user.id,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string if request.user_agent else None
    )

    return render_template('kyc/limits.html', limits=limits_info)
