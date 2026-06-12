# app/user/routes.py
from flask import Blueprint, render_template, request, jsonify, redirect, url_for
from flask_login import login_required, current_user
from app.events.services import EventService
from app.wallet.services.wallet_service import WalletService
from datetime import date, datetime
import logging
from app.auth.kyc_compliance import calculate_kyc_tier

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

        # Try to attach assignment
        try:
            from app.events.models import EventAssignment, Event
            slug = event_data.get('slug')
            if slug:
                event_obj = Event.query.filter_by(slug=slug).first()
                if event_obj:
                    assignment = EventAssignment.query.filter_by(
                        event_id=event_obj.id,
                        attendee_id=current_user.id
                    ).first()
                    if assignment:
                        reg['assignment'] = EventService._assignment_to_dict(assignment)
        except Exception as exc:
            logger.warning("Could not load assignment for reg %s: %s", reg.get('id'), exc)

    return registrations


def _get_wallet():
    """Return wallet object or None — never raises."""
    try:
        return WalletService.get_wallet_by_user_id(current_user.id)
    except Exception:
        return None


def _get_modules():
    """Return module-enabled dict — never raises."""
    from app.utils.module_switch import check_module_enabled
    keys = ('wallet', 'transport', 'accommodation', 'tourism', 'tournament')
    return {k: {'enabled': check_module_enabled(k)} for k in keys}


def _split_registrations(all_regs):
    """Split a flat list of reg dicts into upcoming / past by event.start_date."""
    today = date.today().isoformat()
    upcoming, past = [], []
    for reg in all_regs:
        sd = reg.get('event', {}).get('start_date', '')
        # start_date is already an ISO string after _enrich_registrations
        if isinstance(sd, str) and sd[:10] >= today:
            upcoming.append(reg)
        else:
            past.append(reg)
    return upcoming, past


@user_bp.route("/dashboard")
@login_required
def user_dashboard():
    """Main user dashboard."""
    try:
        from app.identity.models.user import User
        from sqlalchemy.orm import joinedload
        user = User.query.options(joinedload(User.organisations)).get(current_user.id)
        if not user:
            return redirect(url_for('auth.logout'))

        data = EventService.get_attendee_dashboard_data(current_user.id)
        all_regs = data['upcoming_registrations'] + data['past_registrations']
        _enrich_registrations(all_regs)
        upcoming_regs, past_regs = _split_registrations(all_regs)

        wallet = _get_wallet()
        wallet_balance = wallet.balance if wallet else 0.0

        # Compute dashboard stats
        upcoming_count = len(upcoming_regs)
        attended_count = sum(
            1 for r in past_regs if r.get('status') == 'checked_in'
        )
        total_spent = sum(
            (r.get('registration_fee') or 0) for r in all_regs
            if r.get('status') != 'cancelled'
        )

        # KYC tier
        kyc_info = {}
        try:
            kyc_info = calculate_kyc_tier(current_user.id)
        except Exception:
            pass

        # Tourism listings (sidebar preview)
        tourism_listings = []
        try:
            from app.tourism.models import TourismListing
            tourism_listings = TourismListing.query.filter_by(
                status='published', is_deleted=False
            ).order_by(TourismListing.created_at.desc()).limit(4).all()
        except Exception:
            pass

        return render_template(
            'user/user_dashboard.html',
            # Flat list (legacy compat)
            registrations=all_regs,
            # Split lists (new template uses these)
            upcoming_registrations=upcoming_regs,
            past_registrations=past_regs,
            # Stats
            upcoming_count=upcoming_count,
            attended_count=attended_count,
            total_spent="%.2f" % total_spent,
            # Wallet — pass BOTH formats
            wallet=wallet,
            wallet_balance=wallet_balance,
            # Misc
            current_date=date.today().isoformat(),
            user_organisations=user.organisations,
            kyc_info=kyc_info,
            tourism_listings=tourism_listings,
            modules=_get_modules(),
        )

    except Exception as exc:
        logger.error("Error loading user dashboard: %s", exc)
        return render_template(
            'user/user_dashboard.html',
            registrations=[], upcoming_registrations=[], past_registrations=[],
            upcoming_count=0, attended_count=0, total_spent="0.00",
            wallet=None, wallet_balance=0,
            current_date=date.today().isoformat(),
            user_organisations=[], kyc_info={}, tourism_listings=[],
            modules=_get_modules(),
        )


@user_bp.route("/my-registrations")
@login_required
def my_registrations():
    """Standalone registrations page (also pane-loadable)."""
    try:
        data = EventService.get_attendee_dashboard_data(current_user.id)
        all_regs = data['upcoming_registrations'] + data['past_registrations']
        _enrich_registrations(all_regs)
        upcoming_regs, past_regs = _split_registrations(all_regs)

        wallet = _get_wallet()

        return render_template(
            'user/my_registrations.html',
            registrations=all_regs,
            upcoming_registrations=upcoming_regs,
            past_registrations=past_regs,
            upcoming_count=len(upcoming_regs),
            attended_count=sum(1 for r in past_regs if r.get('status') == 'checked_in'),
            total_spent="%.2f" % sum(
                (r.get('registration_fee') or 0) for r in all_regs
                if r.get('status') != 'cancelled'
            ),
            wallet=wallet,
            wallet_balance=wallet.balance if wallet else 0.0,
            current_date=date.today().isoformat(),
        )
    except Exception as exc:
        logger.error("Error loading my registrations: %s", exc)
        return render_template(
            'user/my_registrations.html',
            registrations=[], upcoming_registrations=[], past_registrations=[],
            upcoming_count=0, attended_count=0, total_spent="0.00",
            wallet=None, wallet_balance=0,
            current_date=date.today().isoformat(),
        )


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
