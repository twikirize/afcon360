# app/user/routes.py
from flask import Blueprint, render_template, redirect, url_for, request, flash, jsonify
from flask_login import login_required, current_user
from app.extensions import db
from app.events.services import EventService
from app.wallet.services.wallet_service import WalletService
from app.wallet.services.wallet_status_service import WalletStatusService
from datetime import date, datetime
import logging
from app.auth.kyc_compliance import calculate_kyc_tier
from app.fan.services.fan_profile_service import (
    get_dashboard_mode,
    activate_fan_profile,
    deactivate_fan_profile,
    update_fan_preferences,
    get_fan_profile,
)

logger = logging.getLogger(__name__)

user_bp = Blueprint('user', __name__, url_prefix='/user')


def _enrich_registrations(registrations):
    """
    Shared helper — enrich a list of registration dicts with:
    - ISO-stringified dates
    - EventAssignment data if available
    Returns the same list mutated in place.
    """
    for reg in registrations:
        # Normalise date fields to ISO strings so Jinja slice [:10] is safe
        event_data = reg.get('event', {})
        for field in ('start_date', 'end_date', 'created_at', 'updated_at'):
            val = event_data.get(field)
            if isinstance(val, (date, datetime)):
                event_data[field] = val.isoformat()

        # Try to attach assignment and ensure IDs/City for journey links
        try:
            from app.events.models import EventAssignment, Event
            slug = event_data.get('slug')
            if slug:
                event_obj = Event.query.filter_by(slug=slug).first()
                if event_obj:
                    # Ensure we have the database ID and city for cross-module links
                    if 'id' not in event_data or not event_data['id']:
                        event_data['id'] = event_obj.id
                    if 'city' not in event_data or not event_data['city']:
                        event_data['city'] = event_obj.city
                    
                    if 'event_id' not in reg:
                        reg['event_id'] = event_obj.id

                    assignment = EventAssignment.query.filter_by(
                        event_id=event_obj.id,
                        attendee_id=current_user.id
                    ).first()
                    if assignment:
                        reg['assignment'] = EventService._assignment_to_dict(assignment)
        except Exception as exc:
            logger.warning("Could not load assignment for reg %s: %s", reg.get('id'), exc)

    return registrations


def _get_wallet(context='individual', org_id=None):
    """Return wallet object or None — never raises."""
    try:
        if context == 'organization' and org_id:
            from app.identity.models.organisation import Organisation
            org = Organisation.query.filter_by(org_id=org_id).first()
            if org:
                wallet = WalletService.get_wallet_by_org_id(org.id)
                return wallet if hasattr(wallet, 'balance') else None
        wallet = WalletService.get_wallet_by_user_id(current_user.id)
        return wallet if hasattr(wallet, 'balance') else None
    except Exception:
        return None


def _get_modules():
    """Return module-enabled dict — never raises."""
    from app.utils.module_guard import module_enabled
    keys = ('wallet', 'transport', 'accommodation', 'tourism', 'tournament', 'events')
    return {k: {'enabled': module_enabled(k)} for k in keys}


def _get_driver_profile(user):
    """Return active driver profile for a user, if present."""
    if not user:
        return None
    try:
        from app.transport.models import DriverProfile, VerificationTier
        driver = DriverProfile.query.filter_by(user_id=user.id, is_deleted=False).first()
        if not driver:
            return None
        tier = getattr(driver.verification_tier, 'value', driver.verification_tier)
        if tier in (VerificationTier.PLATFORM_VERIFIED.value, VerificationTier.EVENT_CERTIFIED.value):
            return driver
    except Exception:
        pass
    return None


def _can_access_host_dashboard(user):
    """Return True when the user can open host tools."""
    if not user:
        return False
    try:
        from app.accommodation.services.identity_service import AccommodationIdentityService
        can_host, _ = AccommodationIdentityService.can_host(user)
        return bool(can_host)
    except Exception:
        return False


def _get_org_role_names(user):
    """Collect organisation role names from loaded memberships."""
    if not user:
        return set()
    roles = set()
    try:
        for membership in getattr(user, 'organisations', []) or []:
            for org_role in getattr(membership, 'roles', []) or []:
                role = getattr(org_role, 'role', None)
                if role and role.name:
                    roles.add(role.name)
    except Exception:
        pass
    return roles


def _get_role_dashboard_links(user=None, current_context='individual', current_org_id=None):
    """Return role/capability workspace links for the authenticated user.

    The universal user dashboard is not a replacement for role dashboards. It
    should expose the exact dashboard URL for every role or role-like capability
    the user currently has: event manager, transport admin, wallet admin,
    accommodation admin, tourism admin, driver, host, moderator, auditor,
    compliance, support, and org-scoped workspaces.
    """
    from app.utils.module_guard import safe_url

    role_names = set(getattr(user, 'role_names', []) or []) if user else set()
    org_role_names = _get_org_role_names(user)
    driver_profile = _get_driver_profile(user)
    can_host = _can_access_host_dashboard(user)

    role_targets = {
        'owner': ('Platform Owner', 'fa-crown', 'admin.owner.dashboard'),
        'super_admin': ('System Admin', 'fa-user-shield', 'admin.super_dashboard'),
        'admin': ('Admin', 'fa-shield-alt', 'admin.super_dashboard'),
        'moderator': ('Moderator', 'fa-gavel', 'admin.moderator.dashboard'),
        'support': ('Support', 'fa-headset', 'admin.support.dashboard'),
        'auditor': ('Auditor', 'fa-search', 'admin.auditor.dashboard'),
        'compliance_officer': ('Compliance Officer', 'fa-clipboard-check', 'admin.compliance.dashboard'),
        'event_manager': ('Event Manager', 'fa-calendar-star', 'admin.event_manager_dashboard'),
        'transport_admin': ('Transport Admin', 'fa-shuttle-van', 'admin.transport_admin_dashboard'),
        'wallet_admin': ('Wallet Admin', 'fa-vault', 'admin.wallet_admin_dashboard'),
        'accommodation_admin': ('Accommodation Admin', 'fa-hotel', 'admin.accommodation_admin_dashboard'),
        'tourism_admin': ('Tourism Admin', 'fa-map-marked-alt', 'admin.tourism_admin_dashboard'),
    }

    role_order = [
        'owner', 'super_admin', 'admin', 'auditor', 'compliance_officer',
        'moderator', 'support', 'event_manager', 'transport_admin',
        'wallet_admin', 'accommodation_admin', 'tourism_admin',
    ]

    links = []
    seen = set()

    def add_link(role_name, label=None, icon=None, endpoint=None, **kwargs):
        if role_name in seen or not role_name:
            return
        target = role_targets.get(role_name)
        if target:
            label = target[0]
            icon = target[1]
            endpoint = target[2]
        if not endpoint:
            return
        url = safe_url(endpoint, **kwargs) if kwargs else safe_url(endpoint)
        if not url or url == '#':
            return
        links.append({
            'role_name': role_name,
            'label': label or role_name.replace('_', ' ').title(),
            'icon': icon or 'fa-id-card',
            'url': url,
        })
        seen.add(role_name)

    for role_name in role_order:
        if role_name in role_names:
            add_link(role_name)

    org_internal_id = None
    if current_org_id:
        try:
            for membership in getattr(user, 'organisations', []) or []:
                org = getattr(membership, 'organisation', None)
                if getattr(org, 'org_id', None) == current_org_id or str(getattr(membership, 'organisation_id', None)) == str(current_org_id):
                    org_internal_id = getattr(membership, 'organisation_id', None)
                    break
        except Exception:
            org_internal_id = None

    org_endpoint = 'org.org_dashboard' if org_internal_id else 'org.dashboard'
    org_kwargs = {'org_id': org_internal_id} if org_internal_id else {}
    if 'org_owner' in org_role_names:
        add_link('org_owner', label='Organisation Owner', icon='fa-building', endpoint=org_endpoint, **org_kwargs)
    if 'org_admin' in org_role_names:
        add_link('org_admin', label='Organisation Admin', icon='fa-building', endpoint=org_endpoint, **org_kwargs)
    if 'finance_manager' in org_role_names:
        add_link('finance_manager', label='Finance Manager', icon='fa-coins', endpoint=org_endpoint, **org_kwargs)
    if org_role_names and not any(link['role_name'].startswith('org_') or link['role_name'] == 'finance_manager' for link in links):
        add_link('org_member', label='Organisation Member', icon='fa-users', endpoint=org_endpoint, **org_kwargs)

    if driver_profile:
        add_link('driver', label='Driver Dashboard', icon='fa-id-card-clip', endpoint='transport.driver_dashboard')

    if can_host:
        add_link('host', label='Host Dashboard', icon='fa-key', endpoint='accommodation.host_dashboard')

    return links


def _get_shell_context(user=None):
    """Return shared context variables for user dashboard shell templates."""
    from flask import session
    from app.identity.models.user import User
    from sqlalchemy.orm import joinedload
    from app.auth.context import (
        get_active_context,
        get_available_contexts,
        resolve_effective_permissions,
    )
    from app.auth.policy import can_in_context

    if user is None:
        user = User.query.options(joinedload(User.organisations)).get(current_user.id)

    role_names = getattr(user, 'role_names', []) if user else []
    active_context = get_active_context(user) if user else None
    available_contexts = get_available_contexts(user) if user else []
    try:
        effective_permissions = resolve_effective_permissions(user, active_context) if user else set()
    except Exception as exc:
        logger.warning("Could not resolve context permissions for shell: %s", exc)
        effective_permissions = set()

    def context_can(permission):
        return bool(user and active_context and can_in_context(user, permission, context=active_context))
    user_roles = {
        'event_manager': 'event_manager' in role_names or (user and user.is_super_admin()),
        'transport_admin': 'transport_admin' in role_names or (user and user.is_super_admin()),
        'wallet_admin': 'wallet_admin' in role_names or (user and user.is_super_admin()),
        'accommodation_admin': 'accommodation_admin' in role_names or (user and user.is_super_admin()),
        'host': 'accommodation_admin' in role_names or 'host' in role_names or (user and user.is_super_admin()),
        'tourism_admin': 'tourism_admin' in role_names or (user and user.is_super_admin()),
        'auditor': 'auditor' in role_names or (user and user.is_super_admin()),
        'compliance': 'compliance_officer' in role_names or (user and user.is_super_admin()),
        'driver': bool(_get_driver_profile(user)),
    }

    return {
        'active_context': active_context,
        'available_contexts': available_contexts,
        'effective_permissions': effective_permissions,
        'can': context_can,
        'current_context': session.get('current_context', 'individual'),
        'current_org_id': session.get('current_org_id'),
        'current_org_name': session.get('current_org_name'),
        'user_roles': user_roles,
        'role_dashboard_links': _get_role_dashboard_links(
            user,
            current_context=session.get('current_context', 'individual'),
            current_org_id=session.get('current_org_id'),
        ),
        'user_organisations': user.organisations if user else [],
    }


def _split_registrations(all_regs):
    """Split a flat list of reg dicts into upcoming / past by event.start_date."""
    today = date.today().isoformat()
    upcoming, past = [], []
    for reg in all_regs:
        sd = reg.get('event', {}).get('start_date', '')
        if isinstance(sd, str) and sd[:10] >= today:
            upcoming.append(reg)
        else:
            past.append(reg)
    return upcoming, past


# ─── UNIFIED DASHBOARD ────────────────────────────────────────────────────────

@user_bp.route('/dashboard', endpoint='dashboard')
@login_required
def dashboard():
    """
    The ONE dashboard for all users.
    Assembles widgets based on FanProfile presence and current mode.
    """
    try:
        from app.identity.models.user import User
        from app.identity.models.organisation import Organisation
        from sqlalchemy.orm import joinedload
        from app.auth.context import get_active_context

        user = User.query.options(joinedload(User.organisations)).get(current_user.id)
        if not user:
            return redirect(url_for('auth.logout'))

        # Fan/Tournament Mode Logic
        mode = get_dashboard_mode(user)
        fan_profile = get_fan_profile(user.id)

        # Context Info is resolved from live assignments; legacy session values
        # are read only inside the resolver's rollout compatibility path.
        active_context = get_active_context(user)
        current_context = (
            "organization"
            if active_context.type.value == "organisation"
            else "individual"
        )
        current_org_id = (
            active_context.public_id
            if active_context.type.value == "organisation"
            else None
        )
        current_org_name = active_context.label if current_org_id else None
        
        org_obj = None
        if current_context == 'organization' and current_org_id:
            org_obj = Organisation.query.filter_by(org_id=current_org_id).first()

        data = EventService.get_attendee_dashboard_data(current_user.id)
        all_regs = data['upcoming_registrations'] + data['past_registrations']
        _enrich_registrations(all_regs)
        upcoming_regs, past_regs = _split_registrations(all_regs)

        wallet = _get_wallet(current_context, current_org_id)
        wallet_balance = wallet.balance if wallet else 0.0

        upcoming_count = len(upcoming_regs)
        attended_count = sum(1 for r in past_regs if r.get('status') == 'checked_in')
        total_spent = sum((r.get('registration_fee') or 0) for r in all_regs if r.get('status') != 'cancelled')

        kyc_info = {}
        try:
            if current_context == 'organization' and org_obj:
                kyc_info = {
                    'tier': 5 if org_obj.verification_status == 'verified' else 0,
                    'tier_name': 'Corporate' if org_obj.verification_status == 'verified' else 'Unverified Organisation',
                    'status': org_obj.verification_status,
                    'is_org': True
                }
            else:
                kyc_info = calculate_kyc_tier(user.id)
        except Exception:
            pass

        shell_context = _get_shell_context(user)
        # The settings pane and dashboard must render the same authoritative
        # KYC result for the effective user, including after phone verification.
        shell_context['kyc_info'] = kyc_info

        tourism_listings = []
        try:
            from app.tourism.models import TourismListing
            tourism_listings = TourismListing.query.filter_by(status='published', is_deleted=False).order_by(TourismListing.created_at.desc()).limit(4).all()
        except Exception:
            pass

        wallet_banner = WalletStatusService.get_wallet_banner(org_obj if current_context == 'organization' else user)
        wallet_action_buttons = WalletStatusService.get_action_buttons(org_obj if current_context == 'organization' else user)

        priority_actions = []
        # NOTE: KYC verification prompt is rendered as a single consolidated banner
        # in user_dashboard.html (kyc_info.tier < 2). Do NOT add a duplicate KYC
        # card here — that caused three redundant "Verify" cards on the dashboard.

        return render_template(
            'user/user_dashboard.html',
            dashboard_mode=mode,
            fan_profile=fan_profile,
            registrations=all_regs,
            upcoming_registrations=upcoming_regs,
            past_registrations=past_regs,
            upcoming_count=upcoming_count,
            attended_count=attended_count,
            total_spent="%.2f" % total_spent,
            wallet=wallet,
            wallet_balance=wallet_balance,
            wallet_banner=wallet_banner,
            wallet_action_buttons=wallet_action_buttons,
            priority_actions=priority_actions,
            current_date=date.today().isoformat(),
            kyc_info=kyc_info,
            tourism_listings=tourism_listings,
            modules=_get_modules(),
            **shell_context,
        )

    except Exception as exc:
        logger.error("Error loading user dashboard: %s", exc)
        return render_template(
            'user/user_dashboard.html',
            dashboard_mode='standard',
            fan_profile=None,
            registrations=[], upcoming_registrations=[], past_registrations=[],
            upcoming_count=0, attended_count=0, total_spent="0.00",
            wallet=None, wallet_balance=0,
            current_date=date.today().isoformat(),
            kyc_info={}, tourism_listings=[],
            modules=_get_modules(),
            **_get_shell_context(None)
        )


# ─── FAN PROFILE SETTINGS ─────────────────────────────────────────────────────

@user_bp.route('/settings/interests', methods=['GET'], endpoint='interests_settings')
@login_required
def interests_settings():
    """Settings → Interests page. Where FanProfile is activated/managed."""
    fan_profile = get_fan_profile(current_user.id)
    return render_template(
        'user/settings/interests.html',
        fan_profile=fan_profile,
    )


@user_bp.route('/settings/interests/fan/activate', methods=['POST'], endpoint='fan_activate')
@login_required
def fan_activate():
    """Activate fan profile from Settings."""
    teams = request.form.getlist('favorite_teams') or []
    sports = request.form.getlist('favorite_sports') or ['football']

    activate_fan_profile(current_user.id, favorite_teams=teams, favorite_sports=sports)
    db.session.commit()
    flash('Fan profile activated. You now have access to sports and tournament features.', 'success')
    return redirect(url_for('user.interests_settings'))


@user_bp.route('/settings/interests/fan/deactivate', methods=['POST'], endpoint='fan_deactivate')
@login_required
def fan_deactivate():
    """Deactivate fan profile. Preferences are saved for reactivation."""
    deactivate_fan_profile(current_user.id)
    db.session.commit()
    flash('Fan profile deactivated. Sports content is now hidden.', 'info')
    return redirect(url_for('user.interests_settings'))


@user_bp.route('/settings/interests/fan/update', methods=['POST'], endpoint='fan_update')
@login_required
def fan_update():
    """Update fan preferences (teams, sports, notifications)."""
    data = {
        'favorite_teams': request.form.getlist('favorite_teams'),
        'favorite_sports': request.form.getlist('favorite_sports'),
        'tournament_notifications': 'tournament_notifications' in request.form,
        'match_reminders': 'match_reminders' in request.form,
        'team_news': 'team_news' in request.form,
        'social_features_enabled': 'social_features_enabled' in request.form,
    }
    update_fan_preferences(current_user.id, data)
    db.session.commit()
    flash('Fan preferences updated.', 'success')
    return redirect(url_for('user.interests_settings'))


# ─── EXISTING ROUTES ──────────────────────────────────────────────────────────

@user_bp.route('/registrations', endpoint='my_registrations')
@login_required
def my_registrations():
    """Standalone registrations page."""
    try:
        data = EventService.get_attendee_dashboard_data(current_user.id)
        all_regs = data['upcoming_registrations'] + data['past_registrations']
        _enrich_registrations(all_regs)
        upcoming_regs, past_regs = _split_registrations(all_regs)

        wallet = _get_wallet()
        shell_context = _get_shell_context()

        return render_template(
            'user/my_registrations.html',
            registrations=all_regs,
            upcoming_registrations=upcoming_regs,
            past_registrations=past_regs,
            upcoming_count=len(upcoming_regs),
            attended_count=sum(1 for r in past_regs if r.get('status') == 'checked_in'),
            total_spent="%.2f" % sum((r.get('registration_fee') or 0) for r in all_regs if r.get('status') != 'cancelled'),
            wallet=wallet,
            wallet_balance=wallet.balance if wallet else 0.0,
            current_date=date.today().isoformat(),
            kyc_info={},
            tourism_listings=[],
            modules=_get_modules(),
            **shell_context,
        )
    except Exception as exc:
        logger.error("Error loading my registrations: %s", exc)
        return render_template(
            'user/my_registrations.html',
            registrations=[], upcoming_registrations=[], past_registrations=[],
            upcoming_count=0, attended_count=0, total_spent="0.00",
            wallet=None, wallet_balance=0,
            current_date=date.today().isoformat(),
            kyc_info={},
            tourism_listings=[],
            modules=_get_modules(),
            **_get_shell_context(None),
        )


@user_bp.route("/preferences", endpoint='preferences')
@login_required
def preferences():
    return render_template('user/preferences.html')


@user_bp.route("/cancel-registration", methods=['POST'])
@login_required
def cancel_registration():
    try:
        payload = request.get_json()
        reg_ref = payload.get('reg_ref') if payload else None
        if not reg_ref:
            return jsonify({'success': False, 'error': 'Registration reference required'}), 400
        success, error = EventService.cancel_registration(reg_ref, current_user.id)
        if success:
            return jsonify({'success': True, 'message': 'Registration cancelled successfully'})
        return jsonify({'success': False, 'error': error or 'Failed to cancel registration'}), 400
    except Exception as exc:
        logger.error("Error cancelling registration: %s", exc)
        return jsonify({'success': False, 'error': 'An unexpected error occurred'}), 500


@user_bp.route("/contact-organizer", methods=['POST'])
@login_required
def contact_organizer():
    try:
        payload = request.get_json()
        event_id = payload.get('event_id') if payload else None
        message = payload.get('message') if payload else None
        if not event_id or not message:
            return jsonify({'success': False, 'error': 'Event ID and message required'}), 400
        return jsonify({'success': True, 'message': 'Message sent to organizer'})
    except Exception as exc:
        logger.error("Error contacting organizer: %s", exc)
        return jsonify({'success': False, 'error': 'An unexpected error occurred'}), 500
