from flask import Blueprint, render_template, redirect, url_for, flash, current_app, request, abort, jsonify, session
from flask_login import current_user, login_required
from datetime import datetime, timezone
from app.identity.models.user import User, Session as UserSession
from app.profile.models import get_profile_by_user
from app.extensions import db
from app.utils.immutable_fields import filter_immutable_changes, enforce_immutability
from app.auth.kyc_compliance import calculate_kyc_tier, get_user_limits
from app.kyc.services import KycService

profile_bp = Blueprint("profile", __name__)


@profile_bp.route("/profile/kyc")
@login_required
def profile_kyc():
    """Compatibility entry point for legacy profile KYC links."""
    return redirect(url_for("kyc.index"))

@profile_bp.route("/profile/<public_id>", endpoint="public_profile")
def public_profile(public_id):
    user_lookup = getattr(User, 'get_by_public_id', None)
    if callable(user_lookup):
        user = User.get_by_public_id(public_id)
    else:
        user = User.query.filter_by(public_id=public_id).first()

    if not user or getattr(user, 'is_deleted', False):
        abort(404)

    profile = get_profile_by_user(user.public_id)
    is_own_profile = current_user.is_authenticated and getattr(current_user, 'public_id', None) == user.public_id

    public_info = {
        'display_name': getattr(profile, 'display_name', None) if profile else None,
        'full_name': getattr(profile, 'full_name', None) if profile else getattr(user, 'username', None),
        'avatar_url': getattr(profile, 'avatar_url', None) if profile else None,
        'bio': getattr(profile, 'bio', None) if profile else None,
        'fan_team': getattr(profile, 'fan_team', None) if profile else None,
        'city': getattr(profile, 'city', None) if profile else None,
        'country': getattr(profile, 'country', None) if profile else None,
    }

    user_roles = getattr(user, 'role_names', []) or []
    stats = {'stays_count': 0, 'trips_count': 0, 'reviews_count': 0}
    tournament_mode = True

    context = {
        'user': user,
        'profile': profile,
        'public_info': public_info,
        'is_own_profile': is_own_profile,
        'user_roles': user_roles,
        'stats': stats,
        'tournament_mode': tournament_mode,
    }

    if request.args.get('_pane') == '1':
        return render_template("profile/public_pane.html", **context)

    return render_template("profile/public.html", **context)

@profile_bp.route("/account")
@login_required
def account_overview():
    user = User.query.filter_by(public_id=str(current_user.public_id)).first()
    if not user:
        return redirect(url_for('auth.logout'))

    profile = get_profile_by_user(current_user.public_id)

    kyc_info = {}
    verification_state = {}
    try:
        kyc_info = calculate_kyc_tier(user.id)
    except Exception:
        pass

    try:
        verification_state = KycService.get_user_verification_status(user.id)
    except Exception:
        pass

    limits = {}
    try:
        limits = get_user_limits(user.id)
    except Exception:
        pass

    verification_status = (
        verification_state.get('status')
        or kyc_info.get('verification_status')
        or (profile.verification_status if profile else 'pending')
    )
    if verification_status == 'approved':
        verification_status = 'verified'
    latest_record = verification_state.get('latest_record')
    rejection_reason = (
        getattr(latest_record, 'rejection_reason', None)
        or (profile.rejected_reason if profile else None)
    )
    tier_name = kyc_info.get('tier_name', 'Basic')
    progress_percentage = kyc_info.get('fulfillment_percentage', kyc_info.get('progress_percentage', 0))

    active_sessions = []
    try:
        now = datetime.now(timezone.utc)
        sessions = UserSession.query.filter_by(user_id=user.id).filter(
            UserSession.expires_at > now,
            UserSession.revoked_at == None
        ).order_by(UserSession.created_at.desc()).limit(5).all()
        active_sessions = sessions
    except Exception:
        try:
            now = datetime.now()
            sessions = UserSession.query.filter_by(user_id=user.id).filter(
                UserSession.expires_at > now,
                UserSession.revoked_at == None
            ).order_by(UserSession.created_at.desc()).limit(5).all()
            active_sessions = sessions
        except Exception:
            pass

    user_roles = getattr(user, 'role_names', []) or []
    org_memberships = []
    try:
        for membership in getattr(user, 'organisations', []) or []:
            org = getattr(membership, 'organisation', None)
            if org and not getattr(org, 'is_deleted', False):
                org_roles = [our.role.name for our in getattr(membership, 'roles', []) or [] if getattr(our, 'role', None)]
                org_memberships.append({
                    'org_name': getattr(org, 'legal_name', None),
                    'org_id': getattr(org, 'id', None),
                    'roles': org_roles,
                })
    except Exception:
        pass

    def _now_matching(dt):
        return datetime.now(timezone.utc) if getattr(dt, 'tzinfo', None) else datetime.now()

    password_expires_at = getattr(user, 'password_expires_at', None)
    password_expired = False
    if password_expires_at:
        password_expired = _now_matching(password_expires_at) > password_expires_at

    mfa_active = bool(getattr(user, 'mfa_enabled', False))
    active_mfa_types = [m.mfa_type for m in getattr(user, 'mfa_secrets', []) or [] if getattr(m, 'is_active', False)]

    has_pin = bool(getattr(user, 'transaction_pin_hash', None))
    pin_locked = bool(
        getattr(user, 'transaction_pin_locked_until', None) and
        _now_matching(getattr(user, 'transaction_pin_locked_until', None)) < getattr(user, 'transaction_pin_locked_until', None)
    )

    role_stats = {}

    context = {
        'user': user,
        'profile': profile,
        'kyc_info': kyc_info,
        'limits': limits,
        'verification_status': verification_status,
        'verification_rejection_reason': rejection_reason,
        'tier_name': tier_name,
        'progress_percentage': progress_percentage,
        'profile_completion': None,
        'active_sessions': active_sessions,
        'user_roles': user_roles,
        'org_memberships': org_memberships,
        'password_expires_at': password_expires_at,
        'password_expired': password_expired,
        'mfa_active': mfa_active,
        'active_mfa_types': active_mfa_types,
        'has_pin': has_pin,
        'pin_locked': pin_locked,
        'role_stats': role_stats,
    }

    if request.args.get('_pane') == '1':
        # Loaded inside the unified user dashboard pane — render fragment only
        return render_template("profile/account_pane.html", **context)

    return render_template("profile/account.html", **context)

@profile_bp.route("/profile/account")
@login_required
def profile_account_redirect():
    return redirect(url_for('profile.account_overview'))

@profile_bp.route("/profile/sessions/<int:session_db_id>/revoke", methods=["POST"])
@login_required
def revoke_session(session_db_id):
    user = User.query.filter_by(public_id=str(current_user.public_id)).first()
    if not user:
        return jsonify({'success': False, 'error': 'Session not found'}), 404

    session_obj = UserSession.query.filter_by(id=session_db_id, user_id=user.id).first()
    if not session_obj:
        return jsonify({'success': False, 'error': 'Session not found'}), 404

    session_obj.revoked_at = datetime.now(timezone.utc)
    session_obj.revoked_reason = 'user_revoked'
    db.session.commit()
    return jsonify({'success': True})

@profile_bp.route("/profile/me")
@login_required
def my_public_profile():
    """Redirect to the current user's public profile page, or render pane fragment."""
    if request.args.get('_pane') == '1':
        return public_profile(current_user.public_id)
    return redirect(url_for('profile.public_profile', public_id=current_user.public_id))

@profile_bp.route("/profile/overview")
@login_required
def profile_overview():
    """Alias for account overview"""
    return redirect(url_for('profile.account_overview'))

@profile_bp.route("/profile/edit", methods=["GET", "POST"])
@login_required
def edit_profile():
    profile = get_profile_by_user(current_user.public_id)

    if request.method == "POST":
        if not profile:
            flash('Profile not found.', 'danger')
            return redirect(url_for('profile.edit_profile'))

        is_verified = profile.verification_status == 'verified'

        editable_data = {
            'display_name': request.form.get('display_name'),
            'bio': request.form.get('bio'),
            'fan_team': request.form.get('fan_team'),
            'avatar_url': request.form.get('avatar_url'),
            'nationality': request.form.get('nationality'),
            'address': request.form.get('address'),
            'city': request.form.get('city'),
            'country': request.form.get('country'),
            'email': (request.form.get('email') or '').strip() or None,
        }

        # Email-lock guard & change handling on User model
        new_email = editable_data.get('email')
        if new_email and new_email != current_user.email:
            if getattr(current_user, 'email_verified_at', None) is not None:
                flash('Verified email cannot be changed.', 'danger')
                return redirect(url_for('profile.edit_profile'))
            else:
                from app.auth.email_validation import validate_email_address
                val = validate_email_address(new_email)
                if not val.is_valid:
                    flash(val.message, 'danger')
                    return redirect(url_for('profile.edit_profile'))
                current_user.email = val.normalized
                current_user.email_verified = False
                current_user.email_verified_at = None
        # Remove email from editable_data so filter_immutable_changes doesn't touch UserProfile.email unexpectedly if not mapped there
        editable_data.pop('email', None)

        if not is_verified:
            editable_data['full_name'] = request.form.get('full_name')

        allowed_changes, blocked_fields = filter_immutable_changes(
            profile, editable_data, is_verified,
        )

        for field, value in allowed_changes.items():
            if value is not None:
                setattr(profile, field, value)

        if blocked_fields:
            from app.audit.forensic_audit import ForensicAuditService
            field_labels = {
                "full_name": "Full name",
                "date_of_birth": "Date of birth",
                "gender": "Gender",
                "nationality": "Nationality",
                "id_type": "ID type",
                "id_number": "ID number",
                "id_document_url": "ID document",
                "id_document_mime": "ID document type",
                "id_document_size": "ID document size",
            }
            blocked_labels = [field_labels.get(f, f.replace("_", " ").title()) for f in blocked_fields]
            for field in blocked_fields:
                old_value = getattr(profile, field, None)
                attempted_value = editable_data.get(field)
                ForensicAuditService.log_blocked(
                    entity_type="user_profile",
                    entity_id=str(profile.id),
                    action=f"update_{field}",
                    user_id=current_user.id,
                    reason=f"{field} cannot be changed after verification",
                    attempted_value=str(attempted_value) if attempted_value else None,
                    old_value=str(old_value) if old_value else None,
                    ip_address=request.remote_addr,
                )
            flash(
                f"Some fields cannot be changed after verification: {', '.join(blocked_labels)}. "
                "Contact support if you need to update them.",
                "danger"
            )
            return redirect(url_for('profile.edit_profile'))

        try:
            db.session.commit()
            flash('Profile updated successfully.', 'success')
            return redirect(url_for('profile.edit_profile'))
        except ValueError as e:
            db.session.rollback()
            flash(str(e), 'danger')
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Profile update error: {e}")
            flash('An error occurred. Please try again.', 'danger')

    completion = profile.get_completion_percentage() if profile else 0
    completion_breakdown = profile.get_completion_breakdown() if profile else {}
    is_verified = profile and profile.verification_status == 'verified'

    kyc_info = {}
    try:
        kyc_info = calculate_kyc_tier(current_user.id)
    except Exception:
        pass

    context = {
        'profile': profile,
        'completion': completion,
        'completion_breakdown': completion_breakdown,
        'is_verified': is_verified,
        'kyc_info': kyc_info,
        'current_user': current_user,
    }

    if request.args.get('_pane') == '1':
        return render_template('profile/edit_pane.html', **context)

    return render_template('profile/edit.html', **context)

@profile_bp.route("/profile")
def old_profile_redirect():
    """Redirect old /profile URL to appropriate location"""
    if current_user.is_authenticated:
        return redirect(url_for('profile.my_public_profile'))
    else:
        flash("Please log in to view your profile.", "warning")
        return redirect(url_for("auth.login"))


@profile_bp.route("/settings-pane")
@login_required
def settings_pane():
    """Return settings pane for dashboard (loads in right panel)"""
    from app.profile.models import get_profile_by_user

    profile = get_profile_by_user(current_user.public_id)

    return render_template(
        'user/settings_pane.html',
        profile=profile,
        current_theme=session.get('theme', 'light'),
        current_language=session.get('language', 'en'),
        allow_notifications=session.get('allow_notifications', True),
        mute_notifications=session.get('mute_notifications', False)
    )


@profile_bp.route("/update-settings", methods=['POST'])
@login_required
def update_settings():
    """Update user settings via AJAX"""
    from app.profile.models import get_profile_by_user
    from app.identity.models.user import User
    from app.utils.immutable_fields import filter_immutable_changes
    from app.audit.forensic_audit import ForensicAuditService

    profile = get_profile_by_user(current_user.public_id)
    user = User.query.filter_by(public_id=str(current_user.public_id)).first()

    if not profile:
        return jsonify({'success': False, 'error': 'Profile not found'}), 404

    is_verified = profile.verification_status == 'verified'

    editable_data = {
        'full_name': request.form.get('full_name'),
        'phone_number': request.form.get('phone_number'),
        'address': request.form.get('address'),
        'city': request.form.get('city'),
        'country': request.form.get('country'),
    }

    allowed_changes, blocked_fields = filter_immutable_changes(
        profile, editable_data, is_verified,
    )

    for field, value in allowed_changes.items():
        if value is not None:
            if field == 'full_name':
                profile.full_name = value
            elif field == 'phone_number':
                profile.phone_number = value
            elif field == 'address':
                profile.address = value
            elif field == 'city':
                profile.city = value
            elif field == 'country':
                profile.country = value

    if blocked_fields:
        for field in blocked_fields:
            old_value = getattr(profile, field, None)
            attempted_value = editable_data.get(field)
            ForensicAuditService.log_blocked(
                entity_type="user_profile",
                entity_id=str(profile.id),
                action=f"update_{field}",
                user_id=current_user.id,
                reason=f"{field} cannot be changed after verification",
                attempted_value=str(attempted_value) if attempted_value else None,
                old_value=str(old_value) if old_value else None,
                ip_address=request.remote_addr,
            )
        return jsonify({
            'success': False,
            'error': 'Some fields cannot be changed after verification.',
            'blocked_fields': list(blocked_fields),
        }), 403

    db.session.commit()
    return jsonify({'success': True, 'message': 'Profile updated successfully'})


@profile_bp.route("/update-theme", methods=['POST'])
@login_required
def update_theme():
    """Update user's theme preference"""
    data = request.get_json()
    session['theme'] = data.get('theme', 'light')
    return jsonify({'success': True})


@profile_bp.route("/update-language", methods=['POST'])
@login_required
def update_language():
    """Update user's language preference"""
    data = request.get_json()
    session['language'] = data.get('language', 'en')
    return jsonify({'success': True})


@profile_bp.route("/update-notification-settings", methods=['POST'])
@login_required
def update_notification_settings():
    """Update notification preferences"""
    data = request.get_json()
    if 'allow_notifications' in data:
        session['allow_notifications'] = data['allow_notifications']
    if 'mute_notifications' in data:
        session['mute_notifications'] = data['mute_notifications']
    return jsonify({'success': True})
