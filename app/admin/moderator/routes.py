"""
Moderator Dashboard - Content moderation and user management
"""
from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from app.auth.decorators import require_role
from app.extensions import db
from app.identity.models.user import User
from app.admin.models import ContentSubmission, ManageableItem
from datetime import datetime, timedelta

moderator_bp = Blueprint('moderator', __name__, url_prefix='/moderator')

@moderator_bp.route('/dashboard')
@login_required
@require_role('moderator', 'admin', 'super_admin', 'owner')
def dashboard():
    """Moderator main dashboard"""
    # Get pending content submissions
    pending_submissions = ContentSubmission.query.filter_by(
        status='pending'
    ).order_by(ContentSubmission.created_at.desc()).limit(10).all()

    # Get recent user registrations (last 7 days)
    week_ago = datetime.utcnow() - timedelta(days=7)
    recent_users = User.query.filter(
        User.created_at >= week_ago
    ).order_by(User.created_at.desc()).limit(10).all()

    # Get flagged items
    flagged_items = ManageableItem.query.filter_by(
        is_flagged=True
    ).order_by(ManageableItem.updated_at.desc()).limit(10).all()

    return render_template(
        'admin/moderator/dashboard.html',
        pending_submissions=pending_submissions,
        recent_users=recent_users,
        flagged_items=flagged_items,
        title="Moderator Dashboard"
    )

@moderator_bp.route('/content')
@login_required
@require_role('moderator', 'admin', 'super_admin', 'owner')
def content_moderation():
    """Content moderation panel"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    status = request.args.get('status', 'pending')

    query = ContentSubmission.query

    if status != 'all':
        query = query.filter_by(status=status)

    submissions = query.order_by(
        ContentSubmission.created_at.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)

    return render_template(
        'admin/moderator/content.html',
        submissions=submissions,
        status=status,
        title="Content Moderation"
    )

@moderator_bp.route('/content/<int:submission_id>')
@login_required
@require_role('moderator', 'admin', 'super_admin', 'owner')
def view_submission(submission_id):
    """View a specific content submission"""
    submission = ContentSubmission.query.get_or_404(submission_id)

    return render_template(
        'admin/moderator/view_submission.html',
        submission=submission,
        title=f"Submission #{submission_id}"
    )

@moderator_bp.route('/content/<int:submission_id>/approve', methods=['POST'])
@login_required
@require_role('moderator', 'admin', 'super_admin', 'owner')
def approve_submission(submission_id):
    """Approve a content submission"""
    submission = ContentSubmission.query.get_or_404(submission_id)

    submission.status = 'approved'
    submission.reviewed_by = current_user.id
    submission.reviewed_at = datetime.utcnow()
    submission.review_notes = request.form.get('notes', '')

    db.session.commit()

    flash('Submission approved successfully', 'success')
    # FIXED: Added 'admin.' prefix
    return redirect(url_for('admin.moderator.content_moderation'))

@moderator_bp.route('/content/<int:submission_id>/reject', methods=['POST'])
@login_required
@require_role('moderator', 'admin', 'super_admin', 'owner')
def reject_submission(submission_id):
    """Reject a content submission"""
    submission = ContentSubmission.query.get_or_404(submission_id)

    submission.status = 'rejected'
    submission.reviewed_by = current_user.id
    submission.reviewed_at = datetime.utcnow()
    submission.review_notes = request.form.get('notes', '')

    db.session.commit()

    flash('Submission rejected', 'warning')
    # FIXED: Added 'admin.' prefix
    return redirect(url_for('admin.moderator.content_moderation'))

@moderator_bp.route('/users')
@login_required
@require_role('moderator', 'admin', 'super_admin', 'owner')
def user_moderation():
    """User moderation panel"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    query_filter = request.args.get('filter', 'all')

    user_query = User.query

    if query_filter == 'recent':
        week_ago = datetime.utcnow() - timedelta(days=7)
        user_query = user_query.filter(User.created_at >= week_ago)
    elif query_filter == 'unverified':
        user_query = user_query.filter_by(is_verified=False)
    elif query_filter == 'inactive':
        user_query = user_query.filter_by(is_active=False)

    users = user_query.order_by(
        User.created_at.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)

    return render_template(
        'admin/moderator/users.html',
        users=users,
        current_filter=query_filter,
        title="User Moderation"
    )

@moderator_bp.route('/flagged')
@login_required
@require_role('moderator', 'admin', 'super_admin', 'owner')
def flagged_content():
    """View flagged content"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)

    flagged_items = ManageableItem.query.filter_by(
        is_flagged=True
    ).order_by(
        ManageableItem.updated_at.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)

    return render_template(
        'admin/moderator/flagged.html',
        flagged_items=flagged_items,
        title="Flagged Content"
    )
