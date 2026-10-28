from flask import Blueprint, render_template, redirect, url_for, flash, current_app, request, abort, jsonify, session
from flask_login import current_user, login_required, logout_user
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
        # Stale session (user row gone). Log out inline and go to login —
        # do NOT redirect to POST-only /logout (GET would 405).
        logout_user()
        flash("Your session is no longer valid. Please sign in again.", "warning")
        return redirect(url_for('auth.login'))

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

        # Canonical date_of_birth write path (single identity entry).
        # Parsed to a real date so the immutable firewall compares like values
        # and the model validator receives a date, not a raw form string.
        # An empty/absent field is left untouched (no clearing, no false block).
        dob_raw = (request.form.get('date_of_birth') or '').strip()
        if dob_raw:
            try:
                editable_data['date_of_birth'] = datetime.strptime(dob_raw, '%Y-%m-%d').date()
            except ValueError:
                flash('Date of birth must use the format YYYY-MM-DD.', 'danger')
                return redirect(url_for('profile.edit_profile'))

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


@profile_bp.route("/account/security")
@login_required
def account_security():
    """User-facing security dashboard (Google-style My Security page)."""
    from datetime import datetime, timezone, timedelta
    from app.identity.models.user import User, Session as DeviceSession
    from app.profile.models import get_profile_by_user
    from app.extensions import db
    from sqlalchemy import desc
    
    user = User.query.filter_by(public_id=str(current_user.public_id)).first()
    if not user:
        logout_user()
        flash("Your session is no longer valid. Please sign in again.", "warning")
        return redirect(url_for('auth.login'))
    
    profile = get_profile_by_user(current_user.public_id)
    
    # 1. Where you're signed in (device sessions)
    now = datetime.now(timezone.utc)
    device_sessions = DeviceSession.query.filter_by(user_id=user.id).filter(
        DeviceSession.expires_at > now,
        DeviceSession.revoked_at == None
    ).order_by(desc(DeviceSession.updated_at)).all()
    
    # 2. Recent security activity (from security event logs)
    from app.audit.comprehensive_audit import SecurityEventLog
    security_events = SecurityEventLog.query.filter_by(user_id=user.id).filter(
        SecurityEventLog.event_type.in_([
            'login', 'logout', 'password_change', 'email_change',
            'phone_change', 'mfa_enabled', 'mfa_disabled',
            'device_session_created', 'new_signin',
            'device_session_revoked', 'all_device_sessions_revoked',
            'account_locked', 'account_unlocked',
            'security_answer_verified', 'recovery_code_used'
        ])
    ).order_by(desc(SecurityEventLog.created_at)).limit(50).all()
    
    # 3. Account protection status
    mfa_active = bool(getattr(user, 'mfa_enabled', False))
    mfa_types = [m.mfa_type for m in getattr(user, 'mfa_secrets', []) or [] if getattr(m, 'is_active', False)]
    email_verified = bool(getattr(user, 'email_verified', False))
    phone_verified = bool(getattr(user, 'phone_verified', False))
    has_pin = bool(getattr(user, 'transaction_pin_hash', None))
    is_locked = bool(user.locked_until and user.locked_until > now)
    lock_countdown = None
    if is_locked:
        remaining = int((user.locked_until - now).total_seconds() / 60)
        lock_countdown = max(0, remaining)
    
    # Recovery options
    has_security_question = bool(getattr(user, 'security_question', None))
    has_recovery_code = bool(getattr(user, 'recovery_code', None))
    failed_logins = getattr(user, 'failed_logins', 0) or 0
    last_login = getattr(user, 'last_login', None)
    
    # 4. Sign out everywhere endpoint data
    can_revoke_all = len(device_sessions) > 1
    
    # Check if _pane for dashboard embedding
    if request.args.get('_pane') == '1':
        return render_template("profile/security_pane.html",
            user=user,
            profile=profile,
            device_sessions=device_sessions,
            security_events=security_events,
            mfa_active=mfa_active,
            mfa_types=mfa_types,
            email_verified=email_verified,
            phone_verified=phone_verified,
            has_pin=has_pin,
            is_locked=is_locked,
            lock_countdown=lock_countdown,
            has_security_question=has_security_question,
            has_recovery_code=has_recovery_code,
            can_revoke_all=can_revoke_all,
            failed_logins=failed_logins,
            last_login=last_login,
        )
    
    return render_template("profile/security.html",
        user=user,
        profile=profile,
        device_sessions=device_sessions,
        security_events=security_events,
        mfa_active=mfa_active,
        mfa_types=mfa_types,
        email_verified=email_verified,
        phone_verified=phone_verified,
        has_pin=has_pin,
        is_locked=is_locked,
        lock_countdown=lock_countdown,
        has_security_question=has_security_question,
        has_recovery_code=has_recovery_code,
        can_revoke_all=can_revoke_all,
        failed_logins=failed_logins,
        last_login=last_login,
    )


@profile_bp.route("/account/security/revoke-all", methods=["POST"])
@login_required
def revoke_all_device_sessions():
    """Sign out of all devices (current session excluded - handled by logout)."""
    from app.auth.sessions import revoke_all_device_sessions_for_user
    from flask import jsonify
    
    try:
        count = revoke_all_device_sessions_for_user(current_user.id, reason="user_revoked_all")
        # Keep current session alive - user will be redirected to logout if they want full sign-out
        return jsonify({'success': True, 'revoked': count, 'message': f'Signed out of {count} other device(s).'})
    except Exception as e:
        current_app.logger.error(f"Revoke all sessions failed: {e}")
        return jsonify({'success': False, 'error': 'Failed to revoke sessions'}), 500


@profile_bp.route("/account/security/revoke/<session_id>", methods=["POST"])
@login_required
def revoke_device_session_endpoint(session_id):
    """Revoke a specific device session."""
    from app.auth.sessions import revoke_device_session
    from flask import jsonify
    
    try:
        success = revoke_device_session(session_id, user_id=current_user.id, reason="user_revoked")
        if success:
            return jsonify({'success': True, 'message': 'Session revoked'})
        else:
            return jsonify({'success': False, 'error': 'Session not found'}), 404
    except Exception as e:
        current_app.logger.error(f"Revoke session failed: {e}")
        return jsonify({'success': False, 'error': 'Failed to revoke session'}), 500


@profile_bp.route("/account/settings", methods=["GET", "POST"])
@login_required
def account_settings():
    """Account settings page - profile info, email, phone, notifications."""
    from app.profile.models import get_profile_by_user
    from app.identity.models.user import User
    from app.utils.immutable_fields import filter_immutable_changes
    from app.audit.forensic_audit import ForensicAuditService
    from app.auth.email_validation import validate_email_address
    from datetime import datetime
    
    user = User.query.filter_by(public_id=str(current_user.public_id)).first()
    if not user:
        logout_user()
        flash("Your session is no longer valid. Please sign in again.", "warning")
        return redirect(url_for('auth.login'))
    
    profile = get_profile_by_user(current_user.public_id)
    
    if request.method == "POST":
        action = request.form.get('action')
        
        if action == 'update_profile':
            if not profile:
                flash('Profile not found.', 'danger')
                return redirect(url_for('profile.account_settings'))
            
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
                'phone_number': request.form.get('phone_number'),
            }
            
            # Canonical date_of_birth write path
            dob_raw = (request.form.get('date_of_birth') or '').strip()
            if dob_raw:
                try:
                    editable_data['date_of_birth'] = datetime.strptime(dob_raw, '%Y-%m-%d').date()
                except ValueError:
                    flash('Date of birth must use the format YYYY-MM-DD.', 'danger')
                    return redirect(url_for('profile.account_settings'))
            
            # Email change handling on User model
            new_email = request.form.get('email', '').strip() or None
            if new_email and new_email != current_user.email:
                if getattr(current_user, 'email_verified_at', None) is not None:
                    flash('Verified email cannot be changed.', 'danger')
                    return redirect(url_for('profile.account_settings'))
                else:
                    val = validate_email_address(new_email)
                    if not val.is_valid:
                        flash(val.message, 'danger')
                        return redirect(url_for('profile.account_settings'))
                    current_user.email = val.normalized
                    current_user.email_verified = False
                    current_user.email_verified_at = None
            
            if not is_verified:
                editable_data['full_name'] = request.form.get('full_name')
            
            allowed_changes, blocked_fields = filter_immutable_changes(
                profile, editable_data, is_verified,
            )
            
            for field, value in allowed_changes.items():
                if value is not None:
                    setattr(profile, field, value)
            
            if blocked_fields:
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
                return redirect(url_for('profile.account_settings'))
            
            try:
                db.session.commit()
                flash('Profile updated successfully.', 'success')
                return redirect(url_for('profile.account_settings'))
            except ValueError as e:
                db.session.rollback()
                flash(str(e), 'danger')
            except Exception as e:
                db.session.rollback()
                current_app.logger.error(f"Profile update error: {e}")
                flash('An error occurred. Please try again.', 'danger')
        
        elif action == 'update_email':
            new_email = request.form.get('email', '').strip()
            if not new_email:
                flash('Email is required.', 'danger')
                return redirect(url_for('profile.account_settings'))
            
            val = validate_email_address(new_email)
            if not val.is_valid:
                flash(val.message, 'danger')
                return redirect(url_for('profile.account_settings'))
            
            if current_user.email_verified_at:
                flash('Verified email cannot be changed.', 'danger')
                return redirect(url_for('profile.account_settings'))
            
            current_user.email = val.normalized
            current_user.email_verified = False
            current_user.email_verified_at = None
            
            try:
                db.session.commit()
                flash('Email updated. Please verify your new email address.', 'success')
            except Exception as e:
                db.session.rollback()
                current_app.logger.error(f"Email update error: {e}")
                flash('An error occurred. Please try again.', 'danger')
            
            return redirect(url_for('profile.account_settings'))
        
        elif action == 'update_security_question':
            import hashlib

            question = (request.form.get('security_question') or '').strip()
            answer = (request.form.get('security_answer') or '').strip()

            if not question or not answer:
                flash('Both a security question and answer are required.', 'danger')
                return redirect(url_for('profile.account_settings'))

            if len(answer) < 3:
                flash('Security answer is too short.', 'danger')
                return redirect(url_for('profile.account_settings'))

            user.security_question = question
            user.security_answer_hash = hashlib.sha256(answer.lower().encode()).hexdigest()

            try:
                db.session.commit()
                flash('Security question updated.', 'success')
            except Exception as e:
                db.session.rollback()
                current_app.logger.error(f"Security question update error: {e}")
                flash('An error occurred. Please try again.', 'danger')

            return redirect(url_for('profile.account_settings'))

        elif action == 'remove_security_question':
            user.security_question = None
            user.security_answer_hash = None

            try:
                db.session.commit()
                flash('Security question removed.', 'success')
            except Exception as e:
                db.session.rollback()
                current_app.logger.error(f"Security question removal error: {e}")
                flash('An error occurred. Please try again.', 'danger')

            return redirect(url_for('profile.account_settings'))

        elif action == 'generate_recovery_code':
            import secrets

            user.recovery_code = secrets.token_hex(16).upper()

            try:
                db.session.commit()
                flash('Recovery code generated. Store it somewhere safe.', 'success')
            except Exception as e:
                db.session.rollback()
                current_app.logger.error(f"Recovery code generation error: {e}")
                flash('An error occurred. Please try again.', 'danger')

            return redirect(url_for('profile.account_settings'))

        elif action == 'remove_recovery_code':
            user.recovery_code = None

            try:
                db.session.commit()
                flash('Recovery code removed.', 'success')
            except Exception as e:
                db.session.rollback()
                current_app.logger.error(f"Recovery code removal error: {e}")
                flash('An error occurred. Please try again.', 'danger')

            return redirect(url_for('profile.account_settings'))

        elif action == 'change_password':
            current_password = request.form.get('current_password')
            new_password = request.form.get('new_password')
            confirm_password = request.form.get('confirm_password')
            
            if not current_password or not new_password or not confirm_password:
                flash('All password fields are required.', 'danger')
                return redirect(url_for('profile.account_settings'))
            
            if new_password != confirm_password:
                flash('New passwords do not match.', 'danger')
                return redirect(url_for('profile.account_settings'))
            
            if len(new_password) < 8:
                flash('Password must be at least 8 characters.', 'danger')
                return redirect(url_for('profile.account_settings'))
            
            if not current_user.verify_password(current_password):
                flash('Current password is incorrect.', 'danger')
                return redirect(url_for('profile.account_settings'))
            
            current_user.set_password(new_password, changed_by_user_id=current_user.id)
            
            try:
                db.session.commit()
                flash('Password changed successfully.', 'success')
            except Exception as e:
                db.session.rollback()
                current_app.logger.error(f"Password change error: {e}")
                flash('An error occurred. Please try again.', 'danger')
            
            return redirect(url_for('profile.account_settings'))
    
    # GET request - prepare context
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
        'user': user,
        'has_security_question': bool(user.security_question and user.security_answer_hash),
        'has_recovery_code': bool(user.recovery_code),
        'failed_logins': getattr(user, 'failed_logins', 0) or 0,
        'last_login': getattr(user, 'last_login', None),
    }
    
    if request.args.get('_pane') == '1':
        return render_template('profile/settings_pane.html', **context)
    
    return render_template('profile/settings.html', **context)


@profile_bp.route("/account/danger")
@login_required
def account_danger():
    """Danger zone page - deactivate, download data, delete account."""
    from app.profile.models import get_profile_by_user
    from app.identity.models.user import User
    
    user = User.query.filter_by(public_id=str(current_user.public_id)).first()
    if not user:
        logout_user()
        flash("Your session is no longer valid. Please sign in again.", "warning")
        return redirect(url_for('auth.login'))
    
    profile = get_profile_by_user(current_user.public_id)
    
    # Get data stats for download preview
    from app.extensions import db
    from sqlalchemy import func
    
    context = {
        'user': user,
        'profile': profile,
        'current_user': current_user,
    }
    
    return render_template('profile/danger.html', **context)


@profile_bp.route("/account/danger/deactivate", methods=["POST"])
@login_required
def deactivate_account():
    """Deactivate account (soft disable)."""
    from app.identity.models.user import User
    from app.audit.comprehensive_audit import AuditService, AuditSeverity
    from flask import current_app
    
    confirm = request.form.get('confirm_deactivate')
    if confirm != 'deactivate':
        flash('Please type "deactivate" to confirm.', 'danger')
        return redirect(url_for('profile.account_danger'))
    
    user = User.query.filter_by(public_id=str(current_user.public_id)).first()
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('auth.login'))
    
    # Prevent owner from deactivating themselves
    if user.is_app_owner():
        flash('Owner account cannot be deactivated.', 'danger')
        return redirect(url_for('profile.account_danger'))
    
    user.is_active = False
    user.activated_at = None
    db.session.commit()
    
    AuditService.security(
        event_type='account_deactivated',
        severity=AuditSeverity.WARNING,
        description=f'User {user.public_id} deactivated their account',
        user_id=user.id,
        ip_address=request.remote_addr,
    )
    
    logout_user()
    flash('Your account has been deactivated. You can reactivate by logging in again.', 'info')
    return redirect(url_for('auth.login'))


@profile_bp.route("/account/danger/download-data", methods=["POST"])
@login_required
def download_data():
    """Download all user data (GDPR)."""
    from app.identity.models.user import User
    from app.audit.comprehensive_audit import AuditService, AuditSeverity
    import json
    from flask import make_response
    
    user = User.query.filter_by(public_id=str(current_user.public_id)).first()
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('profile.account_danger'))
    
    # Collect user data
    data = {
        'user': {
            'public_id': user.public_id,
            'username': user.username,
            'email': user.email,
            'phone': user.phone,
            'created_at': user.created_at.isoformat() if user.created_at else None,
            'last_login': user.last_login.isoformat() if user.last_login else None,
            'is_verified': user.is_verified,
            'email_verified': user.email_verified,
            'phone_verified': user.phone_verified,
            'kyc_level': user.kyc_level,
            'failed_logins': user.failed_logins,
            'locked_until': user.locked_until.isoformat() if user.locked_until else None,
            'mfa_enabled': user.mfa_enabled,
        },
    }
    
    # Add profile data if exists
    from app.profile.models import get_profile_by_user
    profile = get_profile_by_user(current_user.public_id)
    if profile:
        data['profile'] = {
            'display_name': profile.display_name,
            'full_name': profile.full_name,
            'bio': profile.bio,
            'fan_team': profile.fan_team,
            'avatar_url': profile.avatar_url,
            'nationality': profile.nationality,
            'address': profile.address,
            'city': profile.city,
            'country': profile.country,
            'date_of_birth': profile.date_of_birth.isoformat() if profile.date_of_birth else None,
            'verification_status': profile.verification_status,
            'profile_completed': profile.profile_completed,
        }
    
    # Audit log
    AuditService.security(
        event_type='data_downloaded',
        severity=AuditSeverity.INFO,
        description=f'User {user.public_id} downloaded their data',
        user_id=user.id,
        ip_address=request.remote_addr,
    )
    
    response = make_response(json.dumps(data, indent=2, default=str))
    response.headers['Content-Type'] = 'application/json'
    response.headers['Content-Disposition'] = f'attachment; filename=afcon360_data_{user.public_id}.json'
    return response


@profile_bp.route("/account/danger/delete", methods=["POST"])
@login_required
def delete_account():
    """Permanently delete account (requires owner approval for verified users)."""
    from app.identity.models.user import User
    from app.audit.comprehensive_audit import AuditService, AuditSeverity
    from app.extensions import db
    
    confirm = request.form.get('confirm_delete')
    if confirm != 'DELETE MY ACCOUNT':
        flash('Please type "DELETE MY ACCOUNT" exactly to confirm.', 'danger')
        return redirect(url_for('profile.account_danger'))
    
    user = User.query.filter_by(public_id=str(current_user.public_id)).first()
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('profile.account_danger'))
    
    # Prevent owner from deleting themselves
    if user.is_app_owner():
        flash('Owner account cannot be deleted.', 'danger')
        return redirect(url_for('profile.account_danger'))
    
    # For verified users, mark for deletion instead of immediate delete
    if user.is_verified or user.kyc_level > 0:
        user.is_deleted = True
        user.deleted_at = datetime.now(timezone.utc)
        user.email = f'deleted_{user.public_id}@deleted.local'
        user.username = f'deleted_{user.public_id}'
        user.phone = None
        db.session.commit()
        
        AuditService.security(
            event_type='account_deletion_requested',
            severity=AuditSeverity.WARNING,
            description=f'Verified user {user.public_id} requested account deletion (soft delete)',
            user_id=user.id,
            ip_address=request.remote_addr,
        )
        
        logout_user()
        flash('Account deletion requested. Your data has been anonymized and scheduled for permanent removal.', 'info')
    else:
        # Unverified users can be hard deleted
        user_id = user.id
        public_id = user.public_id
        db.session.delete(user)
        db.session.commit()
        
        AuditService.security(
            event_type='account_deleted',
            severity=AuditSeverity.WARNING,
            description=f'Unverified user {public_id} deleted their account',
            user_id=user_id,
            ip_address=request.remote_addr,
        )
        
        logout_user()
        flash('Your account has been permanently deleted.', 'info')
    
    return redirect(url_for('auth.login'))
