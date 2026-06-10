from flask import Blueprint, render_template, redirect, url_for, flash, current_app, request, abort, jsonify
from flask_login import current_user, login_required
from datetime import datetime, timezone
from app.identity.models.user import User, Session as UserSession
from app.profile.models import get_profile_by_user
from app.extensions import db
from app.auth.kyc_compliance import calculate_kyc_tier, get_user_limits, TIER_REQUIREMENTS, TIER_0_UNREGISTERED, TIER_1_BASIC, TIER_2_STANDARD, TIER_3_ENHANCED, TIER_4_PREMIUM, TIER_5_CORPORATE

profile_bp = Blueprint("profile", __name__)

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

    return render_template(
        "profile/public.html",
        user=user,
        profile=profile,
        public_info=public_info,
        is_own_profile=is_own_profile,
        user_roles=user_roles,
        stats=stats,
        tournament_mode=tournament_mode,
    )

@profile_bp.route("/account")
@login_required
def account_overview():
    user = User.query.filter_by(public_id=str(current_user.public_id)).first()
    if not user:
        return redirect(url_for('auth.logout'))

    profile = get_profile_by_user(current_user.public_id)

    kyc_info = {}
    try:
        kyc_info = calculate_kyc_tier(current_user.id)
    except Exception:
        pass

    limits = {}
    try:
        limits = get_user_limits(current_user.id)
    except Exception:
        pass

    verification_status = profile.verification_status if profile else 'pending'
    tier_name = kyc_info.get('tier_name', 'Basic')
    progress_percentage = kyc_info.get('progress_percentage', 0)

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
        'tier_name': tier_name,
        'progress_percentage': progress_percentage,
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
    """Redirect to the current user's public profile page"""
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

        profile.display_name = request.form.get('display_name') or profile.display_name
        profile.bio = request.form.get('bio') or profile.bio
        profile.fan_team = request.form.get('fan_team') or profile.fan_team
        profile.avatar_url = request.form.get('avatar_url') or profile.avatar_url
        profile.nationality = request.form.get('nationality') or profile.nationality
        profile.address = request.form.get('address') or profile.address
        profile.city = request.form.get('city') or profile.city
        profile.country = request.form.get('country') or profile.country

        if not is_verified:
            full_name = request.form.get('full_name')
            if full_name:
                profile.full_name = full_name

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

    return render_template(
        'profile/edit.html',
        profile=profile,
        completion=completion,
        completion_breakdown=completion_breakdown,
        is_verified=is_verified,
    )

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

    profile = get_profile_by_user(current_user.public_id)
    user = User.query.filter_by(public_id=str(current_user.public_id)).first()

    if request.form.get('full_name') and profile:
        profile.full_name = request.form.get('full_name')
    if request.form.get('email') and user:
        user.email = request.form.get('email')
    if request.form.get('phone_number') and profile:
        profile.phone_number = request.form.get('phone_number')
    if request.form.get('location') and profile:
        parts = request.form.get('location').split(',')
        profile.city = parts[0].strip() if parts else None
        profile.country = parts[1].strip() if len(parts) > 1 else None

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
