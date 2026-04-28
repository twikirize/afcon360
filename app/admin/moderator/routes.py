# app/admin/moderator/routes.py
"""
Moderator Blueprint — Complete Route Set
=========================================
All routes the moderator role needs. Nothing deferred.

Sections:
  A.  Dashboard
  B.  Content Submissions  (list · view · approve · reject · request-changes · assign · flag · bulk)
  C.  Flag Management      (list · view · resolve · escalate · close · assign · bulk · create)
  D.  User Moderation      (list · view · suspend · unsuspend · warn · verify · deactivate · flag · note · bulk)
  E.  ManageableCategory   (list · view · toggle-active)
  F.  ManageableItem       (list · view · approve · reject · feature · delete · flag)
  G.  Event Moderation     (list · view · approve · reject · flag)
  H.  Organisation Queue   (list · view · approve · reject · flag)
  I.  KYC Queue            (list · view · flag · refer-to-compliance)
  J.  Audit Log            (list — read-only)
  K.  Moderation Stats     (dashboard)
  L.  JSON API helpers     (live counters, quick-resolve)
"""

import logging
from datetime import datetime, timedelta

from flask import (
    Blueprint, render_template, request, jsonify,
    flash, redirect, url_for, abort, Response
)
from flask_login import login_required, current_user
from sqlalchemy import func, or_

from app.auth.decorators import require_role, require_permission
from app.extensions import db
from app.identity.models.user import User
from app.admin.models import (
    ContentSubmission, ManageableItem,
    ManageableCategory, ContentFlag
)
from app.admin.services import create_flag, resolve_flag

# Phase 2: ModerationLog model
class ModerationLog(db.Model):
    __tablename__ = 'moderation_logs'
    id = db.Column(db.Integer, primary_key=True)
    moderator_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    submission_id = db.Column(db.Integer, db.ForeignKey('content_submission.id'))
    action = db.Column(db.String(20))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    processing_time = db.Column(db.Float)
    moderator = db.relationship('User')

# Phase 2: Ensure SLA columns exist
def _ensure_sla_columns():
    try:
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        sub_cols = [c['name'] for c in inspector.get_columns('content_submission')]
        if 'claimed_at' not in sub_cols:
            db.engine.execute('ALTER TABLE content_submission ADD COLUMN claimed_at TIMESTAMP')
        if 'resolved_at' not in sub_cols:
            db.engine.execute('ALTER TABLE content_submission ADD COLUMN resolved_at TIMESTAMP')
        if 'processing_time' not in sub_cols:
            db.engine.execute('ALTER TABLE content_submission ADD COLUMN processing_time FLOAT')
        flag_cols = [c['name'] for c in inspector.get_columns('content_flag')]
        if 'auto_priority' not in flag_cols:
            db.engine.execute('ALTER TABLE content_flag ADD COLUMN auto_priority BOOLEAN DEFAULT TRUE')
        if 'resolved_at' not in flag_cols:
            db.engine.execute('ALTER TABLE content_flag ADD COLUMN resolved_at TIMESTAMP')
        tables = inspector.get_table_names()
        if 'moderation_logs' not in tables:
            db.engine.execute('''
                CREATE TABLE moderation_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    moderator_id INTEGER REFERENCES user(id),
                    submission_id INTEGER REFERENCES content_submission(id),
                    action VARCHAR(20),
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    processing_time FLOAT
                )
            ''')
    except Exception as exc:
        logger.warning("SLA migration: %s", exc)

_ensure_sla_columns()

logger = logging.getLogger(__name__)

moderator_bp = Blueprint('moderator', __name__, url_prefix='/moderator')

# Roles allowed everywhere unless a route narrows it
_MOD = ('moderator', 'admin', 'super_admin', 'owner')


# ─────────────────────────────────────────────────────────────────────────────
# INTERNAL HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _audit(action: str, category: str, details: dict):
    """Silently write to OwnerAuditLog; never raises."""
    try:
        from app.admin.owner.models import OwnerAuditLog
        OwnerAuditLog.log_action(
            current_user, action=action, category=category,
            details={**details, '_ip': request.remote_addr}
        )
    except Exception as exc:
        logger.debug("Audit log unavailable: %s", exc)


def _review_url(entity_type: str, entity_id: int):
    try:
        from app.admin.moderator.registry import get_review_url
        return get_review_url(entity_type, entity_id)
    except Exception:
        return None


def _enrich_flags(flag_list):
    return [{"flag": f, "review_url": _review_url(f.entity_type, f.entity_id)}
            for f in flag_list]


def _moderators():
    """Return list of users who are moderators/admins — for assign dropdowns."""
    try:
        from app.identity.models.roles_permission import Role, UserRole
        role_ids = db.session.query(Role.id).filter(
            Role.name.in_(['moderator', 'admin', 'super_admin'])
        ).subquery()
        return (User.query
                .join(UserRole, UserRole.user_id == User.id)
                .filter(UserRole.role_id.in_(role_ids))
                .distinct().all())
    except Exception:
        return []


def _redirect_back(fallback):
    ref = request.referrer
    return redirect(ref if ref else url_for(fallback))


# ═════════════════════════════════════════════════════════════════════════════
# A.  DASHBOARD
# ═════════════════════════════════════════════════════════════════════════════

@moderator_bp.route('/dashboard')
@login_required
@require_role(*_MOD)
def dashboard():
    week_ago = datetime.utcnow() - timedelta(days=7)

    pending_submissions = (ContentSubmission.query
                           .filter_by(status='pending')
                           .order_by(ContentSubmission.created_at.desc())
                           .limit(10).all())

    recent_users = (User.query
                    .filter(User.created_at >= week_ago)
                    .order_by(User.created_at.desc())
                    .limit(10).all())

    open_flags = (ContentFlag.query
                  .filter_by(status='open')
                  .order_by(ContentFlag.created_at.desc())
                  .limit(10).all())

    flag_rows = _enrich_flags(open_flags)

    by_priority = dict(
        ContentFlag.query
        .with_entities(ContentFlag.priority, func.count())
        .filter_by(status='open')
        .group_by(ContentFlag.priority).all()
    )
    by_type = dict(
        ContentFlag.query
        .with_entities(ContentFlag.entity_type, func.count())
        .filter_by(status='open')
        .group_by(ContentFlag.entity_type).all()
    )
    total_open_flags = sum(by_priority.values())

    approved_7d = ContentSubmission.query.filter(
        ContentSubmission.status == 'approved',
        ContentSubmission.reviewed_at >= week_ago
    ).count()
    rejected_7d = ContentSubmission.query.filter(
        ContentSubmission.status == 'rejected',
        ContentSubmission.reviewed_at >= week_ago
    ).count()
    resolved_flags_7d = ContentFlag.query.filter(
        ContentFlag.status == 'resolved',
        ContentFlag.resolved_at >= week_ago
    ).count()
    pending_count = ContentSubmission.query.filter_by(status='pending').count()
    changes_requested_count = ContentSubmission.query.filter_by(status='changes_requested').count()

    return render_template(
        'admin/moderator/dashboard.html',
        pending_submissions=pending_submissions,
        recent_users=recent_users,
        flags=open_flags,
        flag_rows=flag_rows,
        flags_by_priority=by_priority,
        flags_by_type=by_type,
        total_open_flags=total_open_flags,
        approved_7d=approved_7d,
        rejected_7d=rejected_7d,
        resolved_flags_7d=resolved_flags_7d,
        pending_count=pending_count,
        changes_requested_count=changes_requested_count,
        title="Moderator Dashboard"
    )


# ═════════════════════════════════════════════════════════════════════════════
# B.  CONTENT SUBMISSIONS
# ═════════════════════════════════════════════════════════════════════════════

@moderator_bp.route('/content')
@login_required
@require_role(*_MOD)
def content_moderation():
    page       = request.args.get('page', 1, type=int)
    per_page   = request.args.get('per_page', 20, type=int)
    status     = request.args.get('status', 'pending')
    cat_id     = request.args.get('category_id', type=int)
    search     = request.args.get('q', '').strip()
    sort       = request.args.get('sort', 'newest')   # newest | oldest

    q = ContentSubmission.query
    if status != 'all':
        q = q.filter_by(status=status)
    if cat_id:
        q = q.filter_by(category_id=cat_id)
    if search:
        q = q.filter(ContentSubmission.name.ilike(f'%{search}%'))

    q = q.order_by(
        ContentSubmission.created_at.asc()
        if sort == 'oldest'
        else ContentSubmission.created_at.desc()
    )

    submissions = q.paginate(page=page, per_page=per_page, error_out=False)
    categories  = ManageableCategory.query.filter_by(is_active=True).order_by(ManageableCategory.name).all()

    # Status counts for tab badges
    status_counts = dict(
        ContentSubmission.query
        .with_entities(ContentSubmission.status, func.count())
        .group_by(ContentSubmission.status).all()
    )

    return render_template(
        'admin/moderator/content.html',
        submissions=submissions,
        status=status,
        categories=categories,
        selected_category=cat_id,
        search=search,
        sort=sort,
        status_counts=status_counts,
        title="Content Moderation"
    )


@moderator_bp.route('/content/<int:submission_id>')
@login_required
@require_role(*_MOD)
def view_submission(submission_id):
    submission    = ContentSubmission.query.get_or_404(submission_id)
    related_flags = (ContentFlag.query
                     .filter_by(entity_type='content_submission', entity_id=submission_id)
                     .order_by(ContentFlag.created_at.desc()).all())
    moderators    = _moderators()
    return render_template(
        'admin/moderator/view_submission.html',
        submission=submission,
        related_flags=related_flags,
        moderators=moderators,
        title=f"Submission #{submission_id}"
    )


@moderator_bp.route('/content/<int:submission_id>/approve', methods=['POST'])
@login_required
@require_role(*_MOD)
def approve_submission(submission_id):
    s = ContentSubmission.query.get_or_404(submission_id)
    now = datetime.utcnow()
    s.status      = 'approved'
    s.reviewed_by = current_user.id
    s.reviewed_at = now
    s.review_notes = request.form.get('notes', '')
    s.resolved_at = now
    if s.claimed_at:
        s.processing_time = (now - s.claimed_at).total_seconds()
    db.session.add(ModerationLog(
        moderator_id=current_user.id,
        submission_id=submission_id,
        action='approve',
        processing_time=s.processing_time
    ))
    db.session.commit()
    _audit('submission.approve', 'content', {'id': submission_id, 'name': s.name})
    flash('Submission approved.', 'success')
    return redirect(url_for('admin.moderator.content_moderation'))


@moderator_bp.route('/content/<int:submission_id>/reject', methods=['POST'])
@login_required
@require_role(*_MOD)
def reject_submission(submission_id):
    s = ContentSubmission.query.get_or_404(submission_id)
    notes = request.form.get('notes', '').strip()
    if not notes:
        flash('Rejection reason is required.', 'danger')
        return redirect(url_for('admin.moderator.view_submission', submission_id=submission_id))
    now = datetime.utcnow()
    s.status      = 'rejected'
    s.reviewed_by = current_user.id
    s.reviewed_at = now
    s.review_notes = notes
    s.resolved_at = now
    if s.claimed_at:
        s.processing_time = (now - s.claimed_at).total_seconds()
    db.session.add(ModerationLog(
        moderator_id=current_user.id,
        submission_id=submission_id,
        action='reject',
        processing_time=s.processing_time
    ))
    db.session.commit()
    _audit('submission.reject', 'content', {'id': submission_id, 'reason': notes})
    flash('Submission rejected.', 'warning')
    return redirect(url_for('admin.moderator.content_moderation'))


@moderator_bp.route('/content/<int:submission_id>/request-changes', methods=['POST'])
@login_required
@require_role(*_MOD)
def request_changes(submission_id):
    s = ContentSubmission.query.get_or_404(submission_id)
    notes = request.form.get('notes', '').strip()
    if not notes:
        flash('Change request details are required.', 'danger')
        return redirect(url_for('admin.moderator.view_submission', submission_id=submission_id))
    s.status      = 'changes_requested'
    s.reviewed_by = current_user.id
    s.reviewed_at = datetime.utcnow()
    s.review_notes = notes
    db.session.commit()
    _audit('submission.request_changes', 'content', {'id': submission_id, 'notes': notes})
    flash('Changes requested from submitter.', 'info')
    return redirect(url_for('admin.moderator.content_moderation'))


@moderator_bp.route('/content/<int:submission_id>/assign', methods=['POST'])
@login_required
@require_role(*_MOD)
def assign_submission(submission_id):
    s = ContentSubmission.query.get_or_404(submission_id)
    assignee_id = request.form.get('assignee_id', type=int)
    if not assignee_id:
        flash('Select a moderator to assign.', 'danger')
        return redirect(url_for('admin.moderator.view_submission', submission_id=submission_id))
    assignee = User.query.get_or_404(assignee_id)
    s.reviewed_by  = assignee.id
    s.review_notes = f"[ASSIGNED → {assignee.username}] {s.review_notes or ''}"
    db.session.commit()
    _audit('submission.assign', 'content', {'id': submission_id, 'assignee': assignee.username})
    flash(f'Assigned to {assignee.username}.', 'success')
    return redirect(url_for('admin.moderator.view_submission', submission_id=submission_id))


@moderator_bp.route('/content/<int:submission_id>/flag', methods=['POST'])
@login_required
@require_permission('content.flag')
def flag_submission(submission_id):
    ContentSubmission.query.get_or_404(submission_id)   # existence check
    reason   = request.form.get('reason') or (request.json or {}).get('reason', '')
    priority = request.form.get('priority', 'normal')
    ok, result = create_flag(current_user, 'content_submission', submission_id, reason, priority)
    if not ok:
        flash(f'Could not flag: {result}', 'danger')
        if request.is_json:
            return jsonify({"ok": False, "error": result}), 403
        return redirect(url_for('admin.moderator.view_submission', submission_id=submission_id))
    _audit('submission.flag', 'moderation', {'submission_id': submission_id, 'priority': priority})
    flash('Submission flagged for escalation.', 'warning')
    if request.is_json:
        return jsonify({"ok": True, "flag_id": int(result.id)})
    return redirect(url_for('admin.moderator.view_submission', submission_id=submission_id))


@moderator_bp.route('/content/bulk-action', methods=['POST'])
@login_required
@require_role(*_MOD)
def bulk_submission_action():
    """Approve or reject multiple submissions at once."""
    ids    = request.form.getlist('submission_ids', type=int)
    action = request.form.get('action')   # approve | reject | request_changes
    notes  = request.form.get('notes', 'Bulk action by moderator')

    if not ids:
        flash('No submissions selected.', 'warning')
        return redirect(url_for('admin.moderator.content_moderation'))

    valid_actions = {'approve': 'approved', 'reject': 'rejected', 'request_changes': 'changes_requested'}
    if action not in valid_actions:
        flash('Invalid action.', 'danger')
        return redirect(url_for('admin.moderator.content_moderation'))

    count = 0
    for sid in ids:
        s = ContentSubmission.query.get(sid)
        if s and s.status == 'pending':
            s.status      = valid_actions[action]
            s.reviewed_by = current_user.id
            s.reviewed_at = datetime.utcnow()
            s.review_notes = notes
            count += 1
    db.session.commit()
    _audit(f'submission.bulk_{action}', 'content', {'count': count, 'ids': ids})
    flash(f'{count} submission(s) {valid_actions[action]}.', 'success')
    return redirect(url_for('admin.moderator.content_moderation'))


# ═════════════════════════════════════════════════════════════════════════════
# C.  FLAG MANAGEMENT
# ═════════════════════════════════════════════════════════════════════════════

@moderator_bp.route('/flagged')
@login_required
@require_role(*_MOD)
def flagged_content():
    page            = request.args.get('page', 1, type=int)
    per_page        = request.args.get('per_page', 20, type=int)
    status_filter   = request.args.get('status', 'open')
    priority_filter = request.args.get('priority')
    type_filter     = request.args.get('entity_type')
    sort            = request.args.get('sort', 'newest')

    q = ContentFlag.query
    if status_filter != 'all':
        q = q.filter_by(status=status_filter)
    if priority_filter:
        q = q.filter_by(priority=priority_filter)
    if type_filter:
        q = q.filter_by(entity_type=type_filter)

    if sort == 'priority':
        priority_order = db.case(
            (ContentFlag.priority == 'critical', 1),
            (ContentFlag.priority == 'high',     2),
            (ContentFlag.priority == 'medium',   3),
            (ContentFlag.priority == 'normal',   4),
            (ContentFlag.priority == 'low',      5),
            else_=6
        )
        q = q.order_by(priority_order, ContentFlag.created_at.asc())
    else:
        q = q.order_by(ContentFlag.created_at.desc())

    flags      = q.paginate(page=page, per_page=per_page, error_out=False)
    flag_rows  = _enrich_flags(flags.items)
    moderators = _moderators()

    entity_types = [
        r[0] for r in db.session.query(ContentFlag.entity_type.distinct()).all() if r[0]
    ]

    status_counts = dict(
        ContentFlag.query
        .with_entities(ContentFlag.status, func.count())
        .group_by(ContentFlag.status).all()
    )

    return render_template(
        'admin/moderator/flagged.html',
        flags=flags,
        flag_rows=flag_rows,
        entity_types=entity_types,
        moderators=moderators,
        status_filter=status_filter,
        priority_filter=priority_filter,
        entity_type_filter=type_filter,
        sort=sort,
        status_counts=status_counts,
        title="Flagged Content"
    )


@moderator_bp.route('/flagged/<int:flag_id>')
@login_required
@require_role(*_MOD)
def view_flag(flag_id):
    flag        = ContentFlag.query.get_or_404(flag_id)
    review_url  = _review_url(flag.entity_type, flag.entity_id)
    moderators  = _moderators()

    # Other open flags on the same entity
    siblings = (ContentFlag.query
                .filter(
                    ContentFlag.entity_type == flag.entity_type,
                    ContentFlag.entity_id   == flag.entity_id,
                    ContentFlag.id          != flag.id,
                    ContentFlag.status      == 'open'
                )
                .order_by(ContentFlag.created_at.desc())
                .limit(5).all())

    # Flags raised by the same flagger (context)
    by_same_user = (ContentFlag.query
                    .filter_by(flagged_by=flag.flagged_by)
                    .order_by(ContentFlag.created_at.desc())
                    .limit(5).all())

    return render_template(
        'admin/moderator/view_flag.html',
        flag=flag,
        review_url=review_url,
        siblings=siblings,
        by_same_user=by_same_user,
        moderators=moderators,
        title=f"Flag #{flag_id}"
    )


@moderator_bp.route('/flagged/<int:flag_id>/resolve', methods=['POST'])
@login_required
@require_role(*_MOD)
def resolve_flag_route(flag_id):
    action = request.form.get('action', 'reviewed') or (request.json or {}).get('action', 'reviewed')
    notes  = request.form.get('notes', '')           or (request.json or {}).get('notes', '')
    ok, result = resolve_flag(current_user, flag_id, action, notes)
    if ok:
        _audit('flag.resolve', 'moderation', {'flag_id': flag_id, 'action': action})
        flash('Flag resolved.', 'success')
    else:
        flash(f'Error: {result}', 'danger')
    if request.is_json:
        return jsonify({"ok": ok, "error": None if ok else result})
    return _redirect_back('admin.moderator.flagged_content')


@moderator_bp.route('/flagged/<int:flag_id>/escalate', methods=['POST'])
@login_required
@require_role(*_MOD)
def escalate_flag(flag_id):
    flag        = ContentFlag.query.get_or_404(flag_id)
    role        = request.form.get('role', 'admin')
    assignee_id = request.form.get('assignee_id', type=int)
    notes       = request.form.get('notes', '').strip()

    flag.status           = 'in_review'
    flag.escalated_to_role = role
    if assignee_id:
        flag.assigned_to = assignee_id
    if notes:
        flag.resolution_notes = notes
    db.session.commit()
    _audit('flag.escalate', 'moderation', {
        'flag_id': flag_id, 'to_role': role, 'assignee': assignee_id
    })
    flash('Flag escalated.', 'warning')
    if request.is_json:
        return jsonify({"ok": True})
    return _redirect_back('admin.moderator.flagged_content')


@moderator_bp.route('/flagged/<int:flag_id>/close', methods=['POST'])
@login_required
@require_role(*_MOD)
def close_flag(flag_id):
    flag       = ContentFlag.query.get_or_404(flag_id)
    notes      = request.form.get('notes', 'Closed by moderator — not actionable')
    flag.status             = 'resolved'
    flag.resolved_by        = current_user.id
    flag.resolution_action  = 'closed'
    flag.resolution_notes   = notes
    flag.resolved_at        = datetime.utcnow()
    db.session.commit()
    _audit('flag.close', 'moderation', {'flag_id': flag_id, 'notes': notes})
    flash('Flag closed.', 'info')
    if request.is_json:
        return jsonify({"ok": True})
    return _redirect_back('admin.moderator.flagged_content')


@moderator_bp.route('/flagged/<int:flag_id>/assign', methods=['POST'])
@login_required
@require_role(*_MOD)
def assign_flag(flag_id):
    flag        = ContentFlag.query.get_or_404(flag_id)
    assignee_id = request.form.get('assignee_id', type=int)
    if not assignee_id:
        flash('Select a moderator.', 'danger')
        return _redirect_back('admin.moderator.flagged_content')
    assignee         = User.query.get_or_404(assignee_id)
    flag.assigned_to = assignee.id
    flag.status      = 'in_review'
    db.session.commit()
    _audit('flag.assign', 'moderation', {'flag_id': flag_id, 'assignee': assignee.username})
    flash(f'Flag assigned to {assignee.username}.', 'success')
    return _redirect_back('admin.moderator.flagged_content')


@moderator_bp.route('/flagged/<int:flag_id>/reprioritise', methods=['POST'])
@login_required
@require_role(*_MOD)
def reprioritise_flag(flag_id):
    flag          = ContentFlag.query.get_or_404(flag_id)
    new_priority  = request.form.get('priority', 'normal')
    VALID         = {'low', 'normal', 'medium', 'high', 'critical'}
    if new_priority not in VALID:
        flash('Invalid priority.', 'danger')
        return _redirect_back('admin.moderator.flagged_content')
    old           = flag.priority
    flag.priority = new_priority
    db.session.commit()
    _audit('flag.reprioritise', 'moderation', {
        'flag_id': flag_id, 'old': old, 'new': new_priority
    })
    flash(f'Priority changed: {old} → {new_priority}.', 'info')
    if request.is_json:
        return jsonify({"ok": True})
    return _redirect_back('admin.moderator.flagged_content')


@moderator_bp.route('/flagged/create', methods=['POST'])
@login_required
@require_permission('content.flag')
def create_flag_route():
    """Moderator manually raises a flag against any entity."""
    entity_type = request.form.get('entity_type', '').strip()
    entity_id   = request.form.get('entity_id', type=int)
    reason      = request.form.get('reason', '').strip()
    priority    = request.form.get('priority', 'normal')
    if not entity_type or not entity_id or not reason:
        flash('Entity type, entity ID, and reason are all required.', 'danger')
        return _redirect_back('admin.moderator.flagged_content')
    ok, result = create_flag(current_user, entity_type, entity_id, reason, priority)
    if ok:
        _audit('flag.create', 'moderation', {
            'entity_type': entity_type, 'entity_id': entity_id, 'priority': priority
        })
        flash(f'Flag #{result.id} created.', 'success')
    else:
        flash(f'Could not create flag: {result}', 'danger')
    if request.is_json:
        return jsonify({"ok": ok, "flag_id": int(result.id) if ok else None})
    return _redirect_back('admin.moderator.flagged_content')


@moderator_bp.route('/flagged/bulk-action', methods=['POST'])
@login_required
@require_role(*_MOD)
def bulk_flag_action():
    flag_ids = request.form.getlist('flag_ids', type=int)
    action   = request.form.get('action')   # resolve | close | escalate
    notes    = request.form.get('notes', 'Bulk action by moderator')
    role     = request.form.get('role', 'admin')

    if not flag_ids:
        flash('No flags selected.', 'warning')
        return redirect(url_for('admin.moderator.flagged_content'))

    count = 0
    for fid in flag_ids:
        flag = ContentFlag.query.get(fid)
        if not flag or flag.status not in ('open', 'in_review'):
            continue
        if action in ('resolve', 'close'):
            ok, _ = resolve_flag(current_user, fid, action, notes)
            if ok:
                count += 1
        elif action == 'escalate':
            flag.status            = 'in_review'
            flag.escalated_to_role = role
            db.session.commit()
            count += 1

    _audit(f'flag.bulk_{action}', 'moderation', {'count': count, 'ids': flag_ids})
    flash(f'{count} flag(s) actioned.', 'success')
    return redirect(url_for('admin.moderator.flagged_content'))


# ═════════════════════════════════════════════════════════════════════════════
# D.  USER MODERATION
# ═════════════════════════════════════════════════════════════════════════════

@moderator_bp.route('/users')
@login_required
@require_role(*_MOD)
def user_moderation():
    page         = request.args.get('page', 1, type=int)
    per_page     = request.args.get('per_page', 20, type=int)
    filter_      = request.args.get('filter', 'all')
    search       = request.args.get('q', '').strip()
    week_ago     = datetime.utcnow() - timedelta(days=7)

    q = User.query
    if filter_ == 'recent':
        q = q.filter(User.created_at >= week_ago)
    elif filter_ == 'unverified':
        q = q.filter_by(is_verified=False)
    elif filter_ == 'inactive':
        q = q.filter_by(is_active=False)
    elif filter_ == 'flagged':
        flagged_ids = db.session.query(ContentFlag.entity_id).filter_by(
            entity_type='user', status='open'
        ).subquery()
        q = q.filter(User.id.in_(flagged_ids))

    if search:
        q = q.filter(or_(
            User.username.ilike(f'%{search}%'),
            User.email.ilike(f'%{search}%')
        ))

    users = q.order_by(User.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    # Count flags per user (for badge display)
    open_flag_counts = dict(
        db.session.query(ContentFlag.entity_id, func.count())
        .filter_by(entity_type='user', status='open')
        .group_by(ContentFlag.entity_id).all()
    )

    return render_template(
        'admin/moderator/users.html',
        users=users,
        current_filter=filter_,
        search=search,
        open_flag_counts=open_flag_counts,
        title="User Moderation"
    )


@moderator_bp.route('/users/<int:user_id>')
@login_required
@require_role(*_MOD)
def view_user(user_id):
    user           = User.query.get_or_404(user_id)
    flags_raised   = (ContentFlag.query.filter_by(flagged_by=user_id)
                      .order_by(ContentFlag.created_at.desc()).limit(20).all())
    flags_against  = (ContentFlag.query.filter_by(entity_type='user', entity_id=user_id)
                      .order_by(ContentFlag.created_at.desc()).limit(20).all())
    submissions    = (ContentSubmission.query.filter_by(submitted_by=user_id)
                      .order_by(ContentSubmission.created_at.desc()).limit(20).all())
    return render_template(
        'admin/moderator/view_user.html',
        user=user,
        flags_raised=flags_raised,
        flags_against=flags_against,
        submissions=submissions,
        title=f"User: {user.username}"
    )


@moderator_bp.route('/users/<int:user_id>/suspend', methods=['POST'])
@login_required
@require_role(*_MOD)
def suspend_user(user_id):
    user   = User.query.get_or_404(user_id)
    reason = request.form.get('reason', '').strip()
    if user.id == current_user.id:
        flash('Cannot suspend yourself.', 'danger')
        return redirect(url_for('admin.moderator.view_user', user_id=user_id))
    if not reason:
        flash('Suspension reason is required.', 'danger')
        return redirect(url_for('admin.moderator.view_user', user_id=user_id))
    user.is_active = False
    db.session.commit()
    create_flag(current_user, 'user', user_id, f'[SUSPENDED] {reason}', priority='high')
    _audit('user.suspend', 'user_management', {
        'target': user.username, 'target_id': user_id, 'reason': reason
    })
    flash(f'{user.username} suspended.', 'warning')
    return redirect(url_for('admin.moderator.view_user', user_id=user_id))


@moderator_bp.route('/users/<int:user_id>/unsuspend', methods=['POST'])
@login_required
@require_role(*_MOD)
def unsuspend_user(user_id):
    user           = User.query.get_or_404(user_id)
    user.is_active = True
    # Resolve any open suspension flags
    ContentFlag.query.filter_by(
        entity_type='user', entity_id=user_id, status='open'
    ).update({
        'status': 'resolved', 'resolved_by': current_user.id,
        'resolution_action': 'unsuspended', 'resolved_at': datetime.utcnow()
    })
    db.session.commit()
    _audit('user.unsuspend', 'user_management', {
        'target': user.username, 'target_id': user_id
    })
    flash(f'{user.username} re-activated.', 'success')
    return redirect(url_for('admin.moderator.view_user', user_id=user_id))


@moderator_bp.route('/users/<int:user_id>/warn', methods=['POST'])
@login_required
@require_role(*_MOD)
def warn_user(user_id):
    user   = User.query.get_or_404(user_id)
    reason = request.form.get('reason', '').strip()
    if not reason:
        flash('Warning reason is required.', 'danger')
        return redirect(url_for('admin.moderator.view_user', user_id=user_id))
    create_flag(current_user, 'user', user_id, f'[WARNING] {reason}', priority='medium')
    _audit('user.warn', 'user_management', {
        'target': user.username, 'target_id': user_id, 'reason': reason
    })
    flash(f'Formal warning issued to {user.username}.', 'warning')
    return redirect(url_for('admin.moderator.view_user', user_id=user_id))


@moderator_bp.route('/users/<int:user_id>/verify', methods=['POST'])
@login_required
@require_role(*_MOD)
def verify_user(user_id):
    user             = User.query.get_or_404(user_id)
    user.is_verified = True
    db.session.commit()
    _audit('user.verify', 'user_management', {
        'target': user.username, 'target_id': user_id
    })
    flash(f'{user.username} marked as verified.', 'success')
    return redirect(url_for('admin.moderator.view_user', user_id=user_id))


@moderator_bp.route('/users/<int:user_id>/deactivate', methods=['POST'])
@login_required
@require_role(*_MOD)
def deactivate_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('Cannot deactivate yourself.', 'danger')
        return redirect(url_for('admin.moderator.view_user', user_id=user_id))
    user.is_active = False
    db.session.commit()
    _audit('user.deactivate', 'user_management', {'target': user.username})
    flash(f'{user.username} deactivated.', 'warning')
    return redirect(url_for('admin.moderator.view_user', user_id=user_id))


@moderator_bp.route('/users/<int:user_id>/activate', methods=['POST'])
@login_required
@require_role(*_MOD)
def activate_user(user_id):
    user           = User.query.get_or_404(user_id)
    user.is_active = True
    db.session.commit()
    _audit('user.activate', 'user_management', {'target': user.username})
    flash(f'{user.username} activated.', 'success')
    return redirect(url_for('admin.moderator.view_user', user_id=user_id))


@moderator_bp.route('/users/<int:user_id>/flag', methods=['POST'])
@login_required
@require_permission('content.flag')
def flag_user(user_id):
    user     = User.query.get_or_404(user_id)
    reason   = request.form.get('reason') or (request.json or {}).get('reason', '')
    priority = request.form.get('priority', 'normal')
    ok, result = create_flag(current_user, 'user', user_id, reason, priority)
    if ok:
        flash(f'{user.username} flagged.', 'warning')
    else:
        flash(f'Could not flag: {result}', 'danger')
    if request.is_json:
        return jsonify({"ok": ok, "flag_id": int(result.id) if ok else None})
    return redirect(url_for('admin.moderator.view_user', user_id=user_id))


@moderator_bp.route('/users/<int:user_id>/note', methods=['POST'])
@login_required
@require_role(*_MOD)
def add_user_note(user_id):
    User.query.get_or_404(user_id)
    note = request.form.get('note', '').strip()
    if not note:
        flash('Note cannot be empty.', 'danger')
        return redirect(url_for('admin.moderator.view_user', user_id=user_id))
    create_flag(current_user, 'user', user_id, f'[NOTE] {note}', priority='low')
    flash('Internal note saved.', 'success')
    return redirect(url_for('admin.moderator.view_user', user_id=user_id))


@moderator_bp.route('/users/bulk-action', methods=['POST'])
@login_required
@require_role(*_MOD)
def bulk_user_action():
    """suspend | activate | deactivate | verify multiple users."""
    user_ids = request.form.getlist('user_ids', type=int)
    action   = request.form.get('action')
    reason   = request.form.get('reason', 'Bulk action by moderator')

    if not user_ids:
        flash('No users selected.', 'warning')
        return redirect(url_for('admin.moderator.user_moderation'))

    count = 0
    for uid in user_ids:
        if uid == current_user.id:
            continue
        u = User.query.get(uid)
        if not u:
            continue
        if action == 'suspend':
            u.is_active = False
            create_flag(current_user, 'user', uid, f'[BULK SUSPEND] {reason}', priority='high')
            count += 1
        elif action == 'activate':
            u.is_active = True
            count += 1
        elif action == 'deactivate':
            u.is_active = False
            count += 1
        elif action == 'verify':
            u.is_verified = True
            count += 1

    db.session.commit()
    _audit(f'user.bulk_{action}', 'user_management', {'count': count, 'ids': user_ids})
    flash(f'{count} user(s) actioned.', 'success')
    return redirect(url_for('admin.moderator.user_moderation'))


# ═════════════════════════════════════════════════════════════════════════════
# E.  MANAGEABLE CATEGORIES
# ═════════════════════════════════════════════════════════════════════════════

@moderator_bp.route('/categories')
@login_required
@require_role(*_MOD)
def categories_list():
    cats = ManageableCategory.query.order_by(ManageableCategory.name).all()
    return render_template(
        'admin/moderator/categories.html',
        categories=cats,
        title="Manage Categories"
    )


@moderator_bp.route('/categories/<int:cat_id>')
@login_required
@require_role(*_MOD)
def view_category(cat_id):
    cat = ManageableCategory.query.get_or_404(cat_id)
    pending_items = ManageableItem.query.filter_by(
        category_id=cat_id, is_approved=False
    ).count()
    return render_template(
        'admin/moderator/view_category.html',
        category=cat,
        pending_items=pending_items,
        title=f"Category: {cat.name}"
    )


@moderator_bp.route('/categories/<int:cat_id>/toggle-active', methods=['POST'])
@login_required
@require_role(*_MOD)
def toggle_category_active(cat_id):
    cat           = ManageableCategory.query.get_or_404(cat_id)
    cat.is_active = not cat.is_active
    db.session.commit()
    state = 'activated' if cat.is_active else 'deactivated'
    _audit(f'category.{state}', 'content', {'category_id': cat_id, 'name': cat.name})
    flash(f'Category "{cat.name}" {state}.', 'info')
    return redirect(url_for('admin.moderator.categories_list'))


# ═════════════════════════════════════════════════════════════════════════════
# F.  MANAGEABLE ITEMS
# ═════════════════════════════════════════════════════════════════════════════

@moderator_bp.route('/items')
@login_required
@require_role(*_MOD)
def items_list():
    page     = request.args.get('page', 1, type=int)
    approved = request.args.get('approved', 'all')
    cat_id   = request.args.get('category_id', type=int)
    search   = request.args.get('q', '').strip()

    q = ManageableItem.query
    if approved == 'pending':
        q = q.filter_by(is_approved=False)
    elif approved == 'approved':
        q = q.filter_by(is_approved=True)
    if cat_id:
        q = q.filter_by(category_id=cat_id)
    if search:
        q = q.filter(ManageableItem.name.ilike(f'%{search}%'))

    items      = q.order_by(ManageableItem.created_at.desc()).paginate(page=page, per_page=25, error_out=False)
    categories = ManageableCategory.query.filter_by(is_active=True).all()

    return render_template(
        'admin/moderator/items.html',
        items=items,
        categories=categories,
        approved_filter=approved,
        selected_category=cat_id,
        search=search,
        title="Manage Items"
    )


@moderator_bp.route('/items/<int:item_id>')
@login_required
@require_role(*_MOD)
def view_item(item_id):
    item  = ManageableItem.query.get_or_404(item_id)
    flags = (ContentFlag.query
             .filter_by(entity_type='manageable_item', entity_id=item_id)
             .order_by(ContentFlag.created_at.desc()).all())
    return render_template(
        'admin/moderator/view_item.html',
        item=item,
        flags=flags,
        title=f"Item: {item.name}"
    )


@moderator_bp.route('/items/<int:item_id>/approve', methods=['POST'])
@login_required
@require_role(*_MOD)
def approve_item(item_id):
    item             = ManageableItem.query.get_or_404(item_id)
    item.is_approved = True
    item.is_active   = True
    db.session.commit()
    _audit('item.approve', 'content', {'item_id': item_id, 'name': item.name})
    flash(f'"{item.name}" approved.', 'success')
    return redirect(url_for('admin.moderator.items_list'))


@moderator_bp.route('/items/<int:item_id>/reject', methods=['POST'])
@login_required
@require_role(*_MOD)
def reject_item(item_id):
    item             = ManageableItem.query.get_or_404(item_id)
    notes            = request.form.get('notes', '').strip()
    item.is_approved = False
    item.is_active   = False
    db.session.commit()
    _audit('item.reject', 'content', {'item_id': item_id, 'name': item.name, 'reason': notes})
    flash(f'"{item.name}" rejected.', 'warning')
    return redirect(url_for('admin.moderator.items_list'))


@moderator_bp.route('/items/<int:item_id>/toggle-featured', methods=['POST'])
@login_required
@require_role(*_MOD)
def toggle_item_featured(item_id):
    item             = ManageableItem.query.get_or_404(item_id)
    item.is_featured = not item.is_featured
    db.session.commit()
    state = 'featured' if item.is_featured else 'unfeatured'
    flash(f'"{item.name}" {state}.', 'info')
    return redirect(url_for('admin.moderator.view_item', item_id=item_id))


@moderator_bp.route('/items/<int:item_id>/flag', methods=['POST'])
@login_required
@require_permission('content.flag')
def flag_item(item_id):
    ManageableItem.query.get_or_404(item_id)
    reason   = request.form.get('reason') or (request.json or {}).get('reason', '')
    priority = request.form.get('priority', 'normal')
    ok, result = create_flag(current_user, 'manageable_item', item_id, reason, priority)
    if ok:
        flash('Item flagged.', 'warning')
    else:
        flash(f'Could not flag: {result}', 'danger')
    if request.is_json:
        return jsonify({"ok": ok, "flag_id": int(result.id) if ok else None})
    return redirect(url_for('admin.moderator.view_item', item_id=item_id))


# ═════════════════════════════════════════════════════════════════════════════
# G.  EVENT MODERATION
# ═════════════════════════════════════════════════════════════════════════════

def _events_model():
    from app.events.models import Event
    return Event


@moderator_bp.route('/events')
@login_required
@require_role(*_MOD)
def events_list():
    page          = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', 'all')
    search        = request.args.get('q', '').strip()

    try:
        Event = _events_model()
        q     = Event.query.filter_by(is_deleted=False)
        if status_filter != 'all':
            q = q.filter_by(status=status_filter)
        if search:
            q = q.filter(Event.title.ilike(f'%{search}%'))
        events           = q.order_by(Event.created_at.desc()).paginate(page=page, per_page=25, error_out=False)
        events_available = True
    except Exception:
        events           = None
        events_available = False

    return render_template(
        'admin/moderator/events.html',
        events=events,
        events_available=events_available,
        status_filter=status_filter,
        search=search,
        title="Event Moderation"
    )


@moderator_bp.route('/events/<int:event_id>')
@login_required
@require_role(*_MOD)
def view_event(event_id):
    try:
        Event = _events_model()
        event = Event.query.get_or_404(event_id)
    except Exception:
        abort(404)

    flags = (ContentFlag.query
             .filter_by(entity_type='event', entity_id=event_id)
             .order_by(ContentFlag.created_at.desc()).all())
    return render_template(
        'admin/moderator/view_event.html',
        event=event,
        flags=flags,
        title=f"Event #{event_id}"
    )


@moderator_bp.route('/events/<int:event_id>/approve', methods=['POST'])
@login_required
@require_role(*_MOD)
def approve_event(event_id):
    try:
        Event        = _events_model()
        event        = Event.query.get_or_404(event_id)
        event.status = 'approved'
        db.session.commit()
        _audit('event.approve', 'content', {'event_id': event_id})
        flash('Event approved.', 'success')
    except Exception as exc:
        logger.error("approve_event: %s", exc)
        flash('Could not approve event.', 'danger')
    return redirect(url_for('admin.moderator.events_list'))


@moderator_bp.route('/events/<int:event_id>/reject', methods=['POST'])
@login_required
@require_role(*_MOD)
def reject_event(event_id):
    try:
        Event        = _events_model()
        event        = Event.query.get_or_404(event_id)
        reason       = request.form.get('notes', '').strip()
        event.status = 'rejected'
        db.session.commit()
        _audit('event.reject', 'content', {'event_id': event_id, 'reason': reason})
        flash('Event rejected.', 'warning')
    except Exception as exc:
        logger.error("reject_event: %s", exc)
        flash('Could not reject event.', 'danger')
    return redirect(url_for('admin.moderator.events_list'))


@moderator_bp.route('/events/<int:event_id>/flag', methods=['POST'])
@login_required
@require_permission('content.flag')
def flag_event(event_id):
    reason   = request.form.get('reason') or (request.json or {}).get('reason', '')
    priority = request.form.get('priority', 'normal')
    ok, result = create_flag(current_user, 'event', event_id, reason, priority)
    if not ok:
        flash(f'Could not flag: {result}', 'danger')
        if request.is_json:
            return jsonify({"ok": False, "error": result}), 403
        return redirect(url_for('admin.moderator.events_list'))
    flash('Event flagged.', 'warning')
    if request.is_json:
        return jsonify({"ok": True, "flag_id": int(result.id)})
    return _redirect_back('admin.moderator.events_list')


# ═════════════════════════════════════════════════════════════════════════════
# H.  ORGANISATION VERIFICATION QUEUE
# ═════════════════════════════════════════════════════════════════════════════

def _org_model():
    from app.identity.models.organisation import Organisation
    return Organisation


@moderator_bp.route('/orgs')
@login_required
@require_role(*_MOD)
def orgs_queue():
    page          = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', 'pending')

    try:
        Org  = _org_model()
        q    = Org.query
        if status_filter != 'all':
            q = q.filter_by(verification_status=status_filter)
        orgs           = q.order_by(Org.created_at.desc()).paginate(page=page, per_page=25, error_out=False)
        orgs_available = True
    except Exception:
        orgs           = None
        orgs_available = False

    return render_template(
        'admin/moderator/orgs.html',
        orgs=orgs,
        orgs_available=orgs_available,
        status_filter=status_filter,
        title="Organisation Verification"
    )


@moderator_bp.route('/orgs/<int:org_id>')
@login_required
@require_role(*_MOD)
def view_org(org_id):
    try:
        Org = _org_model()
        org = Org.query.get_or_404(org_id)
    except Exception:
        abort(404)

    flags = (ContentFlag.query
             .filter_by(entity_type='organisation', entity_id=org_id)
             .order_by(ContentFlag.created_at.desc()).all())
    return render_template(
        'admin/moderator/view_org.html',
        org=org,
        flags=flags,
        title=f"Org: {org.name}"
    )


@moderator_bp.route('/orgs/<int:org_id>/approve', methods=['POST'])
@login_required
@require_role(*_MOD)
def approve_org(org_id):
    try:
        Org                       = _org_model()
        org                       = Org.query.get_or_404(org_id)
        org.verification_status   = 'verified'
        org.is_active             = True
        db.session.commit()
        _audit('org.approve', 'compliance', {'org_id': org_id, 'name': org.name})
        flash(f'"{org.name}" approved.', 'success')
    except Exception as exc:
        logger.error("approve_org: %s", exc)
        flash('Could not approve.', 'danger')
    return redirect(url_for('admin.moderator.orgs_queue'))


@moderator_bp.route('/orgs/<int:org_id>/reject', methods=['POST'])
@login_required
@require_role(*_MOD)
def reject_org(org_id):
    try:
        Org                     = _org_model()
        org                     = Org.query.get_or_404(org_id)
        reason                  = request.form.get('notes', '').strip()
        org.verification_status = 'rejected'
        db.session.commit()
        _audit('org.reject', 'compliance', {'org_id': org_id, 'name': org.name, 'reason': reason})
        flash(f'"{org.name}" rejected.', 'warning')
    except Exception as exc:
        logger.error("reject_org: %s", exc)
        flash('Could not reject.', 'danger')
    return redirect(url_for('admin.moderator.orgs_queue'))


@moderator_bp.route('/orgs/<int:org_id>/flag', methods=['POST'])
@login_required
@require_permission('content.flag')
def flag_org(org_id):
    reason   = request.form.get('reason') or (request.json or {}).get('reason', '')
    priority = request.form.get('priority', 'normal')
    ok, result = create_flag(current_user, 'organisation', org_id, reason, priority)
    if ok:
        flash('Organisation flagged.', 'warning')
    else:
        flash(f'Could not flag: {result}', 'danger')
    if request.is_json:
        return jsonify({"ok": ok})
    return _redirect_back('admin.moderator.orgs_queue')


# ═════════════════════════════════════════════════════════════════════════════
# I.  KYC QUEUE
# ═════════════════════════════════════════════════════════════════════════════

def _kyc_model():
    from app.identity.individuals.individual_document import IndividualKYCDocument
    return IndividualKYCDocument


@moderator_bp.route('/kyc')
@login_required
@require_role(*_MOD)
def kyc_queue():
    page          = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', 'pending')

    try:
        KYC  = _kyc_model()
        q    = KYC.query
        if status_filter != 'all':
            q = q.filter_by(status=status_filter)
        records       = q.order_by(KYC.created_at.desc()).paginate(page=page, per_page=25, error_out=False)
        kyc_available = True
    except Exception:
        records       = None
        kyc_available = False

    return render_template(
        'admin/moderator/kyc.html',
        records=records,
        kyc_available=kyc_available,
        status_filter=status_filter,
        title="KYC Queue"
    )


@moderator_bp.route('/kyc/<int:doc_id>')
@login_required
@require_role(*_MOD)
def view_kyc(doc_id):
    try:
        KYC = _kyc_model()
        doc = KYC.query.get_or_404(doc_id)
    except Exception:
        abort(404)

    flags = (ContentFlag.query
             .filter_by(entity_type='kyc_document', entity_id=doc_id)
             .order_by(ContentFlag.created_at.desc()).all())
    return render_template(
        'admin/moderator/view_kyc.html',
        doc=doc,
        flags=flags,
        title=f"KYC Document #{doc_id}"
    )


@moderator_bp.route('/kyc/<int:doc_id>/flag', methods=['POST'])
@login_required
@require_permission('content.flag')
def flag_kyc(doc_id):
    reason   = request.form.get('reason') or (request.json or {}).get('reason', '')
    priority = request.form.get('priority', 'high')
    ok, result = create_flag(current_user, 'kyc_document', doc_id, reason, priority)
    if ok:
        flash('KYC record flagged — compliance team will review.', 'warning')
    else:
        flash(f'Could not flag: {result}', 'danger')
    if request.is_json:
        return jsonify({"ok": ok})
    return _redirect_back('admin.moderator.kyc_queue')


@moderator_bp.route('/kyc/<int:doc_id>/refer-compliance', methods=['POST'])
@login_required
@require_role(*_MOD)
def refer_kyc_compliance(doc_id):
    """Escalate a KYC document directly to the compliance team."""
    reason   = request.form.get('reason', 'Referred by moderator for compliance review').strip()
    ok, result = create_flag(current_user, 'kyc_document', doc_id, reason,
                             priority='critical')
    if ok:
        result.escalated_to_role = 'compliance_officer'
        result.status            = 'in_review'
        db.session.commit()
        _audit('kyc.refer_compliance', 'compliance', {'doc_id': doc_id, 'reason': reason})
        flash('KYC record referred to compliance team.', 'warning')
    else:
        flash(f'Could not refer: {result}', 'danger')
    return _redirect_back('admin.moderator.kyc_queue')


# ═════════════════════════════════════════════════════════════════════════════
# J.  AUDIT LOG (read-only)
# ═════════════════════════════════════════════════════════════════════════════

@moderator_bp.route('/audit-log')
@login_required
@require_role(*_MOD)
def audit_log():
    page            = request.args.get('page', 1, type=int)
    per_page        = 50
    action_filter   = request.args.get('action', '').strip()
    category_filter = request.args.get('category', '').strip()
    user_filter     = request.args.get('user_id', type=int)

    try:
        from app.admin.owner.models import OwnerAuditLog
        q = OwnerAuditLog.query
        if action_filter:
            q = q.filter(OwnerAuditLog.action.ilike(f'%{action_filter}%'))
        if category_filter:
            q = q.filter_by(category=category_filter)
        if user_filter:
            q = q.filter_by(actor_id=user_filter)
        logs           = q.order_by(OwnerAuditLog.created_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        categories     = [r[0] for r in db.session.query(
            OwnerAuditLog.category.distinct()).all() if r[0]]
        audit_available = True
    except Exception as exc:
        logger.debug("Audit log unavailable: %s", exc)
        logs            = None
        categories      = []
        audit_available = False

    return render_template(
        'admin/moderator/audit_log.html',
        logs=logs,
        categories=categories,
        action_filter=action_filter,
        category_filter=category_filter,
        audit_available=audit_available,
        title="Audit Log"
    )


# ═════════════════════════════════════════════════════════════════════════════
# K.  MODERATION STATS
# ═════════════════════════════════════════════════════════════════════════════

@moderator_bp.route('/stats')
@login_required
@require_role(*_MOD)
def stats():
    now     = datetime.utcnow()
    week_ago  = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    def _sub_stats(since):
        return {
            'approved': ContentSubmission.query.filter(
                ContentSubmission.status == 'approved',
                ContentSubmission.reviewed_at >= since
            ).count(),
            'rejected': ContentSubmission.query.filter(
                ContentSubmission.status == 'rejected',
                ContentSubmission.reviewed_at >= since
            ).count(),
            'changes': ContentSubmission.query.filter(
                ContentSubmission.status == 'changes_requested',
                ContentSubmission.reviewed_at >= since
            ).count(),
        }

    def _flag_stats(since):
        return {
            'opened':   ContentFlag.query.filter(ContentFlag.created_at >= since).count(),
            'resolved': ContentFlag.query.filter(
                ContentFlag.status == 'resolved',
                ContentFlag.resolved_at >= since
            ).count(),
            'open':     ContentFlag.query.filter_by(status='open').count(),
        }

    submission_stats = {'7d': _sub_stats(week_ago), '30d': _sub_stats(month_ago)}
    flag_stats       = {'7d': _flag_stats(week_ago), '30d': _flag_stats(month_ago)}

    priority_dist = dict(
        ContentFlag.query
        .with_entities(ContentFlag.priority, func.count())
        .filter_by(status='open')
        .group_by(ContentFlag.priority).all()
    )
    type_dist = dict(
        ContentFlag.query
        .with_entities(ContentFlag.entity_type, func.count())
        .filter_by(status='open')
        .group_by(ContentFlag.entity_type).all()
    )

    # 14-day daily opens for sparkline
    daily_opens = []
    for i in range(13, -1, -1):
        day = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        daily_opens.append({
            'date':  day.strftime('%b %d'),
            'count': ContentFlag.query.filter(
                ContentFlag.created_at >= day,
                ContentFlag.created_at < day + timedelta(days=1)
            ).count()
        })

    # Top flaggers (last 30 days) — useful to spot spam-flaggers
    top_flaggers_raw = (
        ContentFlag.query
        .with_entities(ContentFlag.flagged_by, func.count().label('n'))
        .filter(ContentFlag.created_at >= month_ago)
        .group_by(ContentFlag.flagged_by)
        .order_by(func.count().desc())
        .limit(5).all()
    )
    flagger_ids   = [r[0] for r in top_flaggers_raw]
    flagger_users = {u.id: u for u in User.query.filter(User.id.in_(flagger_ids)).all()}
    top_flaggers  = [
        {'user': flagger_users.get(r[0]), 'count': r[1]}
        for r in top_flaggers_raw
    ]

    return render_template(
        'admin/moderator/stats.html',
        submission_stats=submission_stats,
        flag_stats=flag_stats,
        priority_dist=priority_dist,
        type_dist=type_dist,
        daily_opens=daily_opens,
        top_flaggers=top_flaggers,
        title="Moderation Stats"
    )


# ═════════════════════════════════════════════════════════════════════════════
# L.  JSON API HELPERS
# ═════════════════════════════════════════════════════════════════════════════

@moderator_bp.route('/api/queue-health')
@login_required
@require_role(*_MOD)
def api_queue_health():
    """Live queue counters for header widgets / polling."""
    return jsonify({
        "open_flags":            ContentFlag.query.filter_by(status='open').count(),
        "critical_flags":        ContentFlag.query.filter_by(status='open', priority='critical').count(),
        "high_flags":            ContentFlag.query.filter_by(status='open', priority='high').count(),
        "pending_submissions":   ContentSubmission.query.filter_by(status='pending').count(),
        "changes_requested":     ContentSubmission.query.filter_by(status='changes_requested').count(),
        "in_review_flags":       ContentFlag.query.filter_by(status='in_review').count(),
    })


@moderator_bp.route('/api/flags/<int:flag_id>/resolve', methods=['POST'])
@login_required
@require_role(*_MOD)
def api_resolve_flag(flag_id):
    data   = request.get_json() or {}
    ok, result = resolve_flag(
        current_user, flag_id,
        data.get('action', 'reviewed'),
        data.get('notes', '')
    )
    if ok:
        _audit('flag.resolve', 'moderation', {'flag_id': flag_id})
    return jsonify({"ok": ok, "error": None if ok else result})


@moderator_bp.route('/api/flags/<int:flag_id>/close', methods=['POST'])
@login_required
@require_role(*_MOD)
def api_close_flag(flag_id):
    data  = request.get_json() or {}
    flag  = ContentFlag.query.get_or_404(flag_id)
    flag.status            = 'resolved'
    flag.resolved_by       = current_user.id
    flag.resolution_action = 'closed'
    flag.resolution_notes  = data.get('notes', 'Closed via API')
    flag.resolved_at       = datetime.utcnow()
    db.session.commit()
    return jsonify({"ok": True})


@moderator_bp.route('/api/submissions/<int:submission_id>/approve', methods=['POST'])
@login_required
@require_role(*_MOD)
def api_approve_submission(submission_id):
    s = ContentSubmission.query.get_or_404(submission_id)
    now = datetime.utcnow()
    s.status      = 'approved'
    s.reviewed_by = current_user.id
    s.reviewed_at = now
    s.review_notes = (request.get_json() or {}).get('notes', '')
    s.resolved_at = now
    if s.claimed_at:
        s.processing_time = (now - s.claimed_at).total_seconds()
    db.session.add(ModerationLog(
        moderator_id=current_user.id,
        submission_id=submission_id,
        action='approve',
        processing_time=s.processing_time
    ))
    db.session.commit()
    return jsonify({"ok": True})


@moderator_bp.route('/api/submissions/<int:submission_id>/reject', methods=['POST'])
@login_required
@require_role(*_MOD)
def api_reject_submission(submission_id):
    data  = request.get_json() or {}
    notes = data.get('notes', '').strip()
    if not notes:
        return jsonify({"ok": False, "error": "notes required"}), 400
    s = ContentSubmission.query.get_or_404(submission_id)
    now = datetime.utcnow()
    s.status      = 'rejected'
    s.reviewed_by = current_user.id
    s.reviewed_at = now
    s.review_notes = notes
    s.resolved_at = now
    if s.claimed_at:
        s.processing_time = (now - s.claimed_at).total_seconds()
    db.session.add(ModerationLog(
        moderator_id=current_user.id,
        submission_id=submission_id,
        action='reject',
        processing_time=s.processing_time
    ))
    db.session.commit()
    return jsonify({"ok": True})


@moderator_bp.route('/claim/<int:submission_id>', methods=['POST'])
@login_required
@require_role(*_MOD)
def claim_submission(submission_id):
    s = ContentSubmission.query.get_or_404(submission_id)
    if s.reviewed_by:
        return jsonify({"ok": False, "error": "Already claimed"}), 400
    s.reviewed_by = current_user.id
    s.claimed_at = datetime.utcnow()
    db.session.add(ModerationLog(
        moderator_id=current_user.id,
        submission_id=submission_id,
        action='claim'
    ))
    db.session.commit()
    return jsonify({"ok": True})


@moderator_bp.route('/performance')
@login_required
@require_role(*_MOD)
def performance():
    from sqlalchemy import func
    data = db.session.query(
        User.id, User.username,
        func.count(ContentSubmission.id).label('processed'),
        func.avg(ContentSubmission.processing_time).label('avg_time')
    ).join(ContentSubmission, ContentSubmission.reviewed_by == User.id)\
     .filter(ContentSubmission.status.in_(['approved','rejected']))\
     .group_by(User.id).all()
    return jsonify([{
        "user_id": r.id, "username": r.username,
        "processed": r.processed,
        "avg_processing_time": round(r.avg_time or 0, 2)
    } for r in data])


@moderator_bp.route('/queue_metrics')
@login_required
@require_role(*_MOD)
def queue_metrics():
    now = datetime.utcnow()
    pending = ContentSubmission.query.filter_by(status='pending')
    total = pending.count()
    unassigned = pending.filter(ContentSubmission.reviewed_by == None).count()
    oldest = pending.order_by(ContentSubmission.created_at.asc()).first()
    age = int((now - oldest.created_at).total_seconds()) if oldest else 0
    return jsonify({"total_pending": total, "unassigned_count": unassigned, "oldest_item_age_sec": age})


@moderator_bp.route('/audit_insights')
@login_required
@require_role(*_MOD)
def audit_insights():
    from sqlalchemy import func
    logs = db.session.query(
        ModerationLog.moderator_id,
        func.count(ModerationLog.id).label('actions')
    ).group_by(ModerationLog.moderator_id).all()
    return jsonify([{"moderator_id": l.moderator_id, "actions": l.actions} for l in logs])


@moderator_bp.route('/api/auto-priority', methods=['POST'])
@login_required
@require_role(*_MOD)
def api_auto_priority():
    now = datetime.utcnow()
    flags = ContentFlag.query.filter(
        ContentFlag.resolved_at == None,
        ContentFlag.auto_priority == True
    ).all()
    updated = 0
    for f in flags:
        age_hours = (now - f.created_at).total_seconds() / 3600
        if age_hours > 6 and f.priority != 'critical':
            f.priority = 'critical'
            updated += 1
        elif age_hours > 2 and f.priority != 'high':
            f.priority = 'high'
            updated += 1
    db.session.commit()
    return jsonify({"ok": True, "updated": updated})


@moderator_bp.route('/api/my-queue')
@login_required
@require_role(*_MOD)
def my_queue():
    """Return items assigned to the current moderator for the My Queue panel."""
    submissions = ContentSubmission.query.filter_by(
        reviewed_by=current_user.id,
        status='pending'
    ).limit(5).all()

    flags = ContentFlag.query.filter_by(
        assigned_to=current_user.id,
        status='in_review'
    ).limit(5).all()

    return jsonify({
        "submissions": [
            {
                "id": s.id,
                "name": s.name,
                "category_slug": s.category.slug if s.category else None,
                "created_at": s.created_at.isoformat()
            }
            for s in submissions
        ],
        "flags": [
            {
                "id": f.id,
                "entity_type": f.entity_type,
                "entity_id": f.entity_id,
                "priority": f.priority,
                "reason": f.reason,
                "created_at": f.created_at.isoformat()
            }
            for f in flags
        ]
    })
