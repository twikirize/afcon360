"""
Support Dashboard - User support and ticket management
"""
from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from app.auth.decorators import require_role
from app.extensions import db
from app.identity.models.user import User
from app.identity.individuals.individual_verification import IndividualVerification
from app.profile.models import get_profile_by_user
from datetime import datetime, timedelta

support_bp = Blueprint('support', __name__, url_prefix='/support')

@support_bp.route('/dashboard')
@login_required
@require_role('support', 'admin', 'super_admin', 'owner')
def dashboard():
    """Support main dashboard"""
    # Get pending KYC verifications
    pending_verifications = IndividualVerification.query.filter_by(
        status='pending'
    ).order_by(IndividualVerification.requested_at.desc()).limit(10).all()

    # Get recent user issues (users with failed logins)
    recent_issues = User.query.filter(
        User.failed_logins >= 3
    ).order_by(User.last_login.desc()).limit(10).all()

    # Get users needing assistance (unverified for more than 3 days)
    three_days_ago = datetime.utcnow() - timedelta(days=3)
    unverified_users = User.query.filter(
        User.is_verified == False,
        User.created_at <= three_days_ago
    ).order_by(User.created_at.desc()).limit(10).all()

    return render_template(
        'admin/support/dashboard.html',
        pending_verifications=pending_verifications,
        recent_issues=recent_issues,
        unverified_users=unverified_users,
        title="Support Dashboard"
    )

@support_bp.route('/kyc-pending')
@login_required
@require_role('support', 'admin', 'super_admin', 'owner')
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

    return render_template('admin/support/kyc_pending.html',
                          verifications=pending_verifications,
                          title="Pending KYC Verifications")

@support_bp.route('/kyc-review/<int:verification_id>')
@login_required
@require_role('support', 'admin', 'super_admin', 'owner')
def kyc_review(verification_id):
    """Review a specific KYC verification"""
    verification = IndividualVerification.query.get_or_404(verification_id)
    user = User.query.get(verification.user_id)
    profile = get_profile_by_user(user.public_id) if user else None

    return render_template('admin/support/kyc_review.html',
                          verification=verification,
                          user=user,
                          profile=profile,
                          title=f"KYC Review #{verification_id}")

@support_bp.route('/kyc-approve/<int:verification_id>', methods=['POST'])
@login_required
@require_role('support', 'admin', 'super_admin', 'owner')
def kyc_approve(verification_id):
    """Approve a KYC verification"""
    verification = IndividualVerification.query.get_or_404(verification_id)

    # Update verification status
    verification.status = 'verified'
    verification.verified_at = db.func.now()
    verification.verified_by = current_user.id

    # Also mark user as verified
    user = User.query.get(verification.user_id)
    if user:
        user.is_verified = True

    db.session.commit()

    flash('KYC verification approved successfully', 'success')
    return redirect(url_for('support.kyc_pending'))

@support_bp.route('/kyc-reject/<int:verification_id>', methods=['POST'])
@login_required
@require_role('support', 'admin', 'super_admin', 'owner')
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
@require_role('support', 'admin', 'super_admin', 'owner')
def user_search():
    """Search for users"""
    query = request.args.get('q', '')
    page = request.args.get('page', 1, type=int)

    if query:
        users = User.query.filter(
            (User.email.ilike(f'%{query}%')) |
            (User.public_id.ilike(f'%{query}%')) |
            (User.username.ilike(f'%{query}%'))
        ).paginate(page=page, per_page=20, error_out=False)
    else:
        users = User.query.paginate(page=page, per_page=20, error_out=False)

    return render_template('admin/support/user_search.html',
                          users=users,
                          query=query,
                          title="User Search")

@support_bp.route('/user/<string:user_id>')
@login_required
@require_role('support', 'admin', 'super_admin', 'owner')
def view_user(user_id):
    """View user details"""
    user = User.query.filter_by(public_id=user_id).first_or_404()
    profile = get_profile_by_user(user.public_id)

    # Get user's verifications
    verifications = IndividualVerification.query.filter_by(
        user_id=user.id
    ).order_by(IndividualVerification.requested_at.desc()).all()

    return render_template('admin/support/view_user.html',
                          user=user,
                          profile=profile,
                          verifications=verifications,
                          title=f"User: {user.username}")

@support_bp.route('/tickets')
@login_required
@require_role('support', 'admin', 'super_admin', 'owner')
def support_tickets():
    """Support tickets management"""
    # This would integrate with a ticket system
    # For now, return a placeholder
    return render_template('admin/support/tickets.html',
                          title="Support Tickets")
