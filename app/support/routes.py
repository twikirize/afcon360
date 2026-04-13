"""
Support/Admin Panel - KYC document verification and user management
"""
from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from app.auth.decorators import require_role
from app.auth.kyc_compliance import calculate_kyc_tier, get_missing_requirements
from app.identity.models.user import User
from app.profile.models import get_profile_by_user
from app.identity.individuals.individual_verification import IndividualVerification
from app.extensions import db

support_bp = Blueprint('support', __name__, url_prefix='/support')

@support_bp.route('/dashboard')
@login_required
@require_role('support', 'admin')
def dashboard():
    """Support main dashboard"""
    return render_template('support/dashboard.html')

@support_bp.route('/kyc-pending')
@login_required
@require_role('support', 'admin')
def kyc_pending():
    """List users with pending KYC verification"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)

    # Query pending verifications
    pending_verifications = IndividualVerification.query.filter_by(
        status='pending'
    ).order_by(IndividualVerification.requested_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return render_template('support/kyc_pending.html',
                          verifications=pending_verifications)

@support_bp.route('/kyc-review/<int:verification_id>')
@login_required
@require_role('support', 'admin')
def kyc_review(verification_id):
    """Review a specific KYC verification"""
    verification = IndividualVerification.query.get_or_404(verification_id)
    user = User.query.get(verification.user_id)
    profile = get_profile_by_user(user.public_id) if user else None

    kyc_info = calculate_kyc_tier(user.id) if user else None

    return render_template('support/kyc_review.html',
                          verification=verification,
                          user=user,
                          profile=profile,
                          kyc_info=kyc_info)

@support_bp.route('/kyc-approve/<int:verification_id>', methods=['POST'])
@login_required
@require_role('support', 'admin')
def kyc_approve(verification_id):
    """Approve a KYC verification"""
    verification = IndividualVerification.query.get_or_404(verification_id)

    # Update verification status
    verification.status = 'verified'
    verification.verified_at = db.func.now()
    verification.verified_by = current_user.id

    db.session.commit()

    flash('KYC verification approved successfully', 'success')
    return redirect(url_for('support.kyc_pending'))

@support_bp.route('/kyc-reject/<int:verification_id>', methods=['POST'])
@login_required
@require_role('support', 'admin')
def kyc_reject(verification_id):
    """Reject a KYC verification"""
    verification = IndividualVerification.query.get_or_404(verification_id)

    reason = request.form.get('reason', '')

    # Update verification status
    verification.status = 'rejected'
    verification.rejection_reason = reason
    verification.verified_at = db.func.now()
    verification.verified_by = current_user.id

    db.session.commit()

    flash('KYC verification rejected', 'warning')
    return redirect(url_for('support.kyc_pending'))

@support_bp.route('/user-search')
@login_required
@require_role('support', 'admin')
def user_search():
    """Search for users"""
    query = request.args.get('q', '')
    page = request.args.get('page', 1, type=int)

    if query:
        users = User.query.filter(
            (User.email.ilike(f'%{query}%')) |
            (User.public_id.ilike(f'%{query}%'))
        ).paginate(page=page, per_page=20, error_out=False)
    else:
        users = User.query.paginate(page=page, per_page=20, error_out=False)

    return render_template('support/user_search.html', users=users, query=query)
