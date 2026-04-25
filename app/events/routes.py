# app/events/routes.py
"""
Event routes — Unified entry points for all user roles.
Synchronized with constants.py (state machine), models.py, services.py.
"""

from flask import (
    render_template, request, jsonify, redirect, url_for, flash,
    session, current_app, Response
)
from flask_login import login_required, current_user
from app.events import events_bp
from app.events.services import EventService, SoldOutException, CrossSellingService
from app.events.models import Event, EventRegistration, TicketType, Waitlist, EventAssignment, EventRole, DiscountCode
from app.events.permissions import is_system_admin, require_event_permission
from app.events.constants import (
    EventStatus,
    PUBLIC_VISIBLE_STATUSES,
    REGISTRATION_OPEN_STATUSES,
    TERMINAL_STATUSES,
)
from app.extensions import db, redis_client
from sqlalchemy import func
from datetime import datetime, timedelta, date
import logging
import html
import io
import csv
import os

logger = logging.getLogger(__name__)


# ============================================================================
# MODULE FALLBACKS — Graceful degradation
# ============================================================================

try:
    from app.accommodation.models.booking import BookingContextType
except ImportError:
    from enum import Enum
    class BookingContextType(Enum):
        EVENT = "event"
        TOURISM = "tourism"
        TRANSPORT = "transport"
        GENERAL = "general"


def search_properties(city=None, limit=10):
    """Fallback when accommodation module is unavailable."""
    return []


# ============================================================================
# UTILITIES
# ============================================================================

def sanitize_html(text, max_length=5000):
    """Sanitize HTML input to prevent XSS."""
    if not text:
        return text
    if len(text) > max_length:
        text = text[:max_length]
    text = html.escape(text)
    text = text.replace('\n', '<br>')
    return text


def rate_limit(key, limit=10, window=60):
    """Redis-backed rate limiter. Fails open if Redis is unavailable."""
    if not redis_client:
        return True
    try:
        pipe = redis_client.pipeline()
        cache_key = f"rate_limit:{key}"
        pipe.incr(cache_key)
        pipe.expire(cache_key, window)
        results = pipe.execute()
        return results[0] <= limit
    except Exception as e:
        logger.warning(f"Rate limiter error: {e}, allowing request")
        return True


def resolve_event(identifier):
    """Resolve event by public_id (UUID) or slug, excluding soft-deleted."""
    event = Event.query.filter_by(public_id=identifier, is_deleted=False).first()
    if event:
        return event
    return Event.query.filter_by(slug=identifier, is_deleted=False).first()


def resolve_event_admin(identifier):
    """Resolve event including soft-deleted (for admin)."""
    event = Event.query.filter_by(public_id=identifier).first()
    if event:
        return event
    return Event.query.filter_by(slug=identifier).first()


def check_event_access(event_dict, user):
    """Check if user can manage an event (organizer or system admin)."""
    if not user or not user.is_authenticated:
        return False
    if is_system_admin(user):
        return True
    if event_dict and event_dict.get('organizer_id') == user.id:
        return True
    return False


def check_can_check_in(user, event_dict, event_model):
    """Check if user can check in attendees."""
    if not user or not user.is_authenticated:
        return False
    if event_dict and event_dict.get('organizer_id') == user.id:
        return True
    if is_system_admin(user):
        return True
    if event_model:
        staff_role = EventRole.query.filter_by(
            event_id=event_model.id, user_id=user.id, is_active=True
        ).first()
        if staff_role and 'check_in_attendees' in (staff_role.permissions or []):
            return True
    return False


# ============================================================================
# PUBLIC ROUTES
# ============================================================================

@events_bp.route("/")
def list():
    """List all published events (public-facing)."""
    events = EventService.get_all_events()
    return render_template('events/public/list.html', events=events)


@events_bp.route("/<identifier>")
def landing(identifier=None):
    """Landing page for an event."""
    if not identifier:
        return render_template('events/public/not_found.html'), 404

    event_model = resolve_event(identifier)
    if not event_model:
        return render_template('events/public/not_found.html', event_slug=identifier), 404

    event = EventService._event_to_dict(event_model)
    if not event:
        return render_template('events/public/not_found.html', event_slug=identifier), 404

    # Registration status for current user
    user_registered = False
    if current_user.is_authenticated:
        registration = EventRegistration.query.filter_by(
            event_id=event_model.id, user_id=current_user.id, status='confirmed'
        ).first()
        user_registered = registration is not None

    # Remaining capacity per ticket type
    if event.get('ticket_types'):
        for tt in event['ticket_types']:
            tt['remaining'] = tt['capacity'] - tt['registration_count'] if tt.get('capacity') else None

    total_registrations = EventRegistration.query.filter_by(event_id=event_model.id).count()
    start_time = event_model.event_metadata.get('start_time', '00:00:00') if event_model.event_metadata else '00:00:00'
    properties = search_properties(city=event['city'])

    return render_template(
        'events/public/landing.html',
        event=event,
        properties=properties,
        context_type=BookingContextType.EVENT.value,
        context_id=event['slug'],
        context_metadata={
            'event_name': event['name'],
            'event_dates': f"{event['start_date']} to {event['end_date']}" if event.get('start_date') else '',
            'venue': event.get('venue', '')
        },
        is_admin=is_system_admin(current_user) if current_user.is_authenticated else False,
        user_registered=user_registered,
        now=datetime.utcnow,
        total_registrations=total_registrations,
        event_start_time=start_time
    )


# ============================================================================
# API ROUTES
# ============================================================================

@events_bp.route("/api/event/<public_id>")
def api_get_event_by_public_id(public_id):
    """Get event by public_id (UUID)."""
    event_model = resolve_event(public_id)
    if not event_model:
        return jsonify({'error': 'Event not found'}), 404
    return jsonify(EventService._event_to_dict(event_model))


@events_bp.route("/api/<identifier>/properties")
def api_properties(identifier=None):
    """JSON API for event properties."""
    if not identifier:
        return jsonify({'error': 'Event not found'}), 404
    event_model = resolve_event(identifier)
    if not event_model:
        return jsonify({'error': 'Event not found'}), 404
    event = EventService._event_to_dict(event_model)
    if not event:
        return jsonify({'error': 'Event not found'}), 404
    properties = search_properties(city=event['city'])
    return jsonify({'success': True, 'properties': properties, 'count': len(properties)})


@events_bp.route("/api/checkin", methods=['GET', 'POST'])
@login_required
def api_checkin():
    """JSON API for QR code check-in."""
    if not rate_limit(f"checkin:{current_user.id}", limit=60, window=60):
        return jsonify({'success': False, 'error': 'Too many requests. Please slow down.'}), 429

    qr_token = None
    if request.method == 'POST' and request.is_json:
        qr_token = request.get_json().get('qr_token')
    else:
        qr_token = request.args.get('token')

    if not qr_token:
        return jsonify({'success': False, 'error': 'Missing qr_token parameter'}), 400

    success, message, attendee = EventService.check_in_attendee(qr_token, current_user.id)
    if success:
        return jsonify({'success': True, 'message': message, 'attendee': attendee})
    return jsonify({'success': False, 'error': message}), 400


@events_bp.route("/api/<event_slug>/checkin-stats")
@login_required
def api_checkin_stats(event_slug):
    """Real-time check-in stats for scanner dashboard."""
    event = resolve_event(event_slug)
    if not event:
        return jsonify({'success': False, 'error': 'Event not found'}), 404

    if event.organizer_id != current_user.id and not is_system_admin(current_user):
        return jsonify({'success': False, 'error': 'Forbidden'}), 403

    total_registered = EventRegistration.query.filter(
        EventRegistration.event_id == event.id,
        EventRegistration.status.in_(['confirmed', 'checked_in'])
    ).count()

    total_checked_in = EventRegistration.query.filter(
        EventRegistration.event_id == event.id,
        EventRegistration.status == 'checked_in'
    ).count()

    recent = EventRegistration.query.filter(
        EventRegistration.event_id == event.id,
        EventRegistration.status == 'checked_in'
    ).order_by(EventRegistration.checked_in_at.desc()).limit(10).all()

    recent_checkins = [{
        'full_name': r.full_name, 'ticket_type': r.ticket_type,
        'checked_in_at': r.checked_in_at.isoformat() if r.checked_in_at else None,
        'registration_ref': r.registration_ref,
    } for r in recent]

    return jsonify({
        'success': True,
        'total_registered': total_registered,
        'total_checked_in': total_checked_in,
        'recent_checkins': recent_checkins,
    })


@events_bp.route("/api/admin/stats")
@login_required
def api_admin_stats():
    """JSON API for admin dashboard stats."""
    if not is_system_admin(current_user):
        return jsonify({"success": False, "error": "Unauthorized"}), 403

    try:
        data = EventService.get_admin_dashboard_data()
        return jsonify({"success": True, **data})
    except Exception as e:
        logger.error(f"api_admin_stats error: {e}")
        return jsonify({"success": False, "error": "Could not load stats"}), 500


@events_bp.route("/api/admin/pending-events")
@login_required
def api_pending_events():
    """JSON API for pending events list."""
    if not is_system_admin(current_user):
        return jsonify({"success": False, "error": "Unauthorized"}), 403

    try:
        pending = Event.query.filter_by(
            status=EventStatus.PENDING_APPROVAL, is_deleted=False
        ).order_by(Event.created_at.desc()).all()

        events_data = [{
            'name': e.name, 'slug': e.slug, 'city': e.city,
            'organizer_id': e.organizer_id,
            'organizer_name': e.organizer.username if e.organizer else f"User {e.organizer_id}"
        } for e in pending]

        return jsonify({"success": True, "events": events_data})
    except Exception as e:
        logger.error(f"api_pending_events error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ============================================================================
# DASHBOARDS
# ============================================================================

@events_bp.route("/hub")
@login_required
def events_hub():
    """Unified hub for all event-related activities."""
    attendee_data = EventService.get_attendee_dashboard_data(current_user.id)
    organizer_data = EventService.get_organizer_dashboard_data(current_user.id)
    provider_data = EventService.get_service_provider_dashboard_data(current_user.id)

    wallet_balance = 0
    try:
        from app.wallet.services.wallet_service import WalletService
        wallet = WalletService.get_wallet_by_user_id(current_user.id)
        if wallet:
            wallet_balance = wallet.balance
    except Exception:
        pass

    admin_stats = EventService.get_admin_dashboard_data() if is_system_admin(current_user) else None

    return render_template('events/events_hub.html',
                           registrations=attendee_data['upcoming_registrations'],
                           managed_events=organizer_data['active_events'],
                           relevant_events=provider_data['relevant_events'],
                           wallet_balance=wallet_balance,
                           admin_stats=admin_stats)


@events_bp.route("/my-registrations")
@login_required
def my_registrations():
    """Attendee's detailed registration dashboard."""
    data = EventService.get_attendee_dashboard_data(current_user.id)

    wallet_balance = 0
    try:
        from app.wallet.services.wallet_service import WalletService
        wallet = WalletService.get_wallet_by_user_id(current_user.id)
        if wallet:
            wallet_balance = wallet.balance
    except Exception:
        pass

    current_date = date.today().isoformat()
    all_registrations = data['upcoming_registrations'] + data['past_registrations']

    for reg in all_registrations:
        try:
            event_slug = reg.get('event', {}).get('slug')
            if event_slug:
                event = Event.query.filter_by(slug=event_slug).first()
                if event:
                    assignment = EventAssignment.query.filter_by(
                        event_id=event.id, attendee_id=current_user.id
                    ).first()
                    if assignment:
                        reg['assignment'] = EventService._assignment_to_dict(assignment)
        except Exception as e:
            logger.warning(f"Could not load assignment: {e}")

    return render_template('events/attendee/my_registrations.html',
                           registrations=all_registrations,
                           wallet_balance=wallet_balance,
                           current_date=current_date)


@events_bp.route("/organizer/dashboard/<identifier>")
@login_required
def organizer_dashboard(identifier):
    """Event-specific organizer dashboard."""
    event = EventService.get_event(identifier)
    if not check_event_access(event, current_user):
        flash('Unauthorized access', 'danger')
        return redirect(url_for('events.my_events'))

    stats = EventService.get_event_stats(identifier)
    registrations = EventService.get_registrations_by_event(identifier)
    assignments = EventService.get_event_assignments(identifier)

    return render_template('events/organizer/organizer_dashboard.html',
                           event=event, stats=stats,
                           registrations=registrations, assignments=assignments)


@events_bp.route("/service-provider/dashboard")
@login_required
def service_provider_dashboard():
    """Service provider dashboard."""
    data = EventService.get_service_provider_dashboard_data(current_user.id)

    wallet_balance = 0
    try:
        from app.wallet.services.wallet_service import WalletService
        wallet = WalletService.get_wallet_by_user_id(current_user.id)
        if wallet:
            wallet_balance = wallet.balance
    except Exception:
        pass

    return render_template('events/service_provider/service_provider_dashboard.html',
                           user_properties=data['user_properties'],
                           user_vehicles=data['user_vehicles'],
                           relevant_events=data['relevant_events'],
                           wallet_balance=wallet_balance,
                           event_bookings=data['event_assignments'])


# ============================================================================
# ORGANIZER ACTIONS
# ============================================================================

@events_bp.route("/my-events")
@login_required
def my_events():
    """User's managed events."""
    events = EventService.get_events_managed_by_user(current_user.id)
    return render_template('events/organizer/my_events.html', events=events)


@events_bp.route("/create", methods=['GET', 'POST'])
@login_required
def create_event():
    """Create a new event."""
    # Rate limit only POST requests
    if request.method == 'POST' and not rate_limit(f"create_event:{current_user.id}", limit=10, window=300):
        if request.is_json:
            return jsonify({'success': False, 'error': 'Too many requests. Please try again later.'}), 429
        flash('Too many requests. Please try again later.', 'danger')
        return redirect(url_for('events.my_events'))

    if request.method == 'GET':
        return render_template('events/organizer/create.html')

    # Parse request data
    if request.is_json:
        data = request.get_json()
    else:
        data = request.form.to_dict()
        data['registration_required'] = 'registration_required' in request.form
        tier_names = request.form.getlist('tier_name[]')
        tier_prices = request.form.getlist('tier_price[]')
        tier_capacities = request.form.getlist('tier_capacity[]')
        if tier_names and tier_names[0]:
            data['ticket_tiers'] = []
            for i in range(len(tier_names)):
                if tier_names[i]:
                    data['ticket_tiers'].append({
                        'name': tier_names[i],
                        'price': float(tier_prices[i]) if i < len(tier_prices) and tier_prices[i] else 0.0,
                        'capacity': int(tier_capacities[i]) if i < len(tier_capacities) and tier_capacities[i] else None
                    })

    # Force registration_required
    data['registration_required'] = True

    # Validate start date is not in the past
    if data.get('start_date'):
        from datetime import date
        start_date = datetime.strptime(data['start_date'], '%Y-%m-%d').date()
        if start_date < date.today():
            return jsonify({'success': False, 'error': 'Start date cannot be in the past.'}), 400

    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400

    for field in ['name', 'city', 'start_date']:
        if not data.get(field):
            return jsonify({'success': False, 'error': f'Missing required field: {field}'}), 400

    try:
        event, error = EventService.create_event(data, current_user.id)
        if error:
            return jsonify({'success': False, 'error': error}), 400
        return jsonify({
            'success': True,
            'redirect': url_for('events.my_events'),
            'message': 'Event created successfully!'
        })
    except Exception as e:
        logger.error(f"Create event error: {e}")
        return jsonify({'success': False, 'error': 'Internal server error'}), 500


@events_bp.route("/<identifier>/edit", methods=['GET', 'POST'])
@login_required
def edit_event(identifier):
    """Edit an event."""
    event = EventService.get_event(identifier)
    if not check_event_access(event, current_user):
        flash('Unauthorized', 'danger')
        return redirect(url_for('events.my_events'))

    if request.method == 'GET':
        return render_template('events/organizer/edit.html', event=event)

    try:
        data = request.get_json()
        success, error = EventService.update_event(identifier, data, current_user.id)
        if not success:
            return jsonify({'success': False, 'error': error}), 400
        return jsonify({'success': True, 'redirect': url_for('events.my_events')})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@events_bp.route("/<identifier>/add-ticket-type", methods=['POST'])
@login_required
def add_ticket_type(identifier):
    """Add a ticket type to an event."""
    event = EventService.get_event(identifier)
    if not check_event_access(event, current_user):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403

    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400

    ticket_type, error = EventService.add_ticket_type(identifier, data, current_user.id)
    if error:
        return jsonify({'success': False, 'error': error}), 400
    return jsonify({'success': True, 'ticket_type': ticket_type})


@events_bp.route("/<identifier>/scanner")
@login_required
def scanner(identifier):
    """Scanner interface for event staff."""
    event = EventService.get_event(identifier)
    if not event:
        return render_template('events/public/not_found.html', event_slug=identifier), 404

    event_model = EventService.get_event_model(identifier)
    if not check_can_check_in(current_user, event, event_model):
        flash('Unauthorized', 'danger')
        return redirect(url_for('events.landing', identifier=identifier))

    return render_template('events/organizer/scanner.html', event=event)


@events_bp.route("/<identifier>/analytics")
@login_required
def event_analytics(identifier):
    """Event analytics for organizers."""
    event = EventService.get_event(identifier)
    if not check_event_access(event, current_user):
        flash('Unauthorized access', 'danger')
        return redirect(url_for('events.my_events'))

    stats = EventService.get_event_stats(identifier)
    stats['checked_in'] = stats.get('checked_in_count', 0)
    stats['total'] = stats.get('total_registrations', 0)
    stats['checkin_rate'] = round((stats['checked_in'] / stats['total'] * 100), 1) if stats['total'] > 0 else 0

    daily_trend = [
        {'date': (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d'), 'count': 5 + i}
        for i in range(7, 0, -1)
    ]
    checkin_trend = [
        {'date': (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d'), 'count': 2 + i}
        for i in range(7, 0, -1)
    ]

    revenue_by_ticket = {tt['name']: tt['registration_count'] * tt['price'] for tt in event.get('ticket_types', [])}
    demographics = {'Uganda': 45, 'Kenya': 12, 'Tanzania': 8, 'Other': 15}

    return render_template('events/organizer/analytics.html',
                           event=event, stats=stats,
                           daily_trend=daily_trend, checkin_trend=checkin_trend,
                           revenue_by_ticket=revenue_by_ticket, demographics=demographics)


@events_bp.route("/<identifier>/export")
@login_required
def export_attendees(identifier):
    """Export attendee list as CSV."""
    event = EventService.get_event(identifier)
    if not check_event_access(event, current_user):
        flash('Unauthorized', 'danger')
        return redirect(url_for('events.my_events'))

    registrations = EventService.get_registrations_by_event(identifier)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Ref', 'Name', 'Email', 'Ticket Type', 'Status', 'Registered At'])
    for reg in registrations:
        writer.writerow([
            reg['registration_ref'], reg['full_name'], reg['email'],
            reg['ticket_type'], reg['status'], reg['created_at']
        ])
    output.seek(0)

    return Response(output, mimetype="text/csv",
                    headers={"Content-disposition": f"attachment; filename=attendees_{identifier}.csv"})


@events_bp.route("/<identifier>/staff")
@login_required
def event_staff(identifier):
    """Manage event staff."""
    event = EventService.get_event(identifier)
    if not check_event_access(event, current_user):
        flash('Only event organizers can manage staff', 'danger')
        return redirect(url_for('events.landing', identifier=identifier))

    event_model = EventService.get_event_model(identifier)
    staff = EventRole.query.filter_by(
        event_id=event_model.id, is_active=True
    ).all() if event_model else []

    return render_template('events/admin/staff.html', event=event, staff=staff)


@events_bp.route("/staff/<int:staff_id>/remove", methods=['POST'])
@login_required
def remove_staff(staff_id):
    """Remove staff member from event."""
    staff = EventRole.query.get_or_404(staff_id)
    event = EventService.get_event_model_by_id(staff.event_id)

    if not event or (event.organizer_id != current_user.id and not is_system_admin(current_user)):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403

    try:
        staff.is_active = False
        db.session.commit()
        return jsonify({'success': True, 'message': 'Staff member removed successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@events_bp.route("/<identifier>/attendees")
@login_required
def event_attendees(identifier):
    """Show attendees for an event."""
    event = EventService.get_event(identifier)
    if not check_event_access(event, current_user):
        flash('You do not have permission to view attendees', 'danger')
        return redirect(url_for('events.landing', identifier=identifier))

    registrations = EventService.get_registrations_by_event(identifier)
    stats = {
        'total': len(registrations),
        'checked_in': len([r for r in registrations if r.get('status') == 'checked_in']),
        'confirmed': len([r for r in registrations if r.get('status') == 'confirmed']),
        'cancelled': len([r for r in registrations if r.get('status') == 'cancelled']),
    }

    return render_template('events/organizer/attendees.html',
                           event=event, registrations=registrations, stats=stats)


# ============================================================================
# REGISTRATION & CHECK-IN
# ============================================================================

@events_bp.route("/<identifier>/register", methods=['GET', 'POST'])
@login_required
def register(identifier):
    """Register for an event."""
    event = EventService.get_event(identifier)
    if not event:
        return render_template('events/public/not_found.html', event_slug=identifier), 404

    if request.method == 'GET':
        user_data = {
            'full_name': getattr(current_user, 'username', current_user.email),
            'email': current_user.email,
            'phone': getattr(current_user, 'phone', ''),
            'nationality': getattr(current_user, 'nationality', ''),
        }
        return render_template('events/attendee/register.html', event=event, user_data=user_data)

    try:
        if request.is_json:
            data = request.get_json()
        else:
            data = request.form.to_dict()
            if 'ticket_type_id' in data:
                data['ticket_type_id'] = int(data['ticket_type_id'])

        registration, _, error = EventService.register_for_event(identifier, current_user.id, data)
        if error:
            return jsonify({'success': False, 'error': error}), 400

        reg_obj = EventRegistration.query.filter_by(registration_ref=registration['registration_ref']).first()
        qr_code = EventService._generate_qr_code(reg_obj.qr_token, reg_obj.registration_ref) if reg_obj else None

        session['last_registration'] = {
            'registration': EventService._registration_to_dict(reg_obj) if reg_obj else registration,
            'qr_code': qr_code,
            'event': event
        }

        mail_configured = bool(current_app.config.get('MAIL_SERVER'))
        if not mail_configured and not session.get('email_reminder_shown'):
            flash('⚠️ Email notifications are not configured. Set MAIL_SERVER in .env.', 'warning')
            session['email_reminder_shown'] = True

        is_ajax = request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest'

        if is_ajax:
            return jsonify({
                'success': True,
                'registration_ref': registration['registration_ref'],
                'ticket_number': registration.get('ticket_number'),
                'qr_code': qr_code,
                'status': registration['status'],
                'payment_status': registration['payment_status'],
                'registration_fee': registration['registration_fee'],
                'ticket_type': registration['ticket_type'],
                'event': registration.get('event'),
                'suggested_services': registration.get('suggested_services', {}),
                'redirect': url_for('events.registration_confirmation', reg_ref=registration['registration_ref']),
                'message': 'Registration successful!'
            })
        else:
            return redirect(url_for('events.registration_confirmation', reg_ref=registration['registration_ref']))

    except Exception as e:
        if "sold out" in str(e).lower():
            return jsonify({'success': False, 'error': str(e)}), 400
        logger.error(f"Registration error: {e}")
        return jsonify({'success': False, 'error': 'An unexpected error occurred'}), 500


@events_bp.route("/registration-confirmation/<reg_ref>")
@login_required
def registration_confirmation(reg_ref):
    """Show registration confirmation with QR code."""
    try:
        reg_data = session.get('last_registration')
        if reg_data and reg_data.get('registration', {}).get('registration_ref') == reg_ref:
            session.pop('last_registration', None)
        else:
            registration = EventRegistration.query.filter_by(registration_ref=reg_ref).first()
            if not registration or registration.user_id != current_user.id:
                flash('Registration not found', 'danger')
                return redirect(url_for('events.my_registrations'))

            qr_code = EventService._generate_qr_code(registration.qr_token, registration.registration_ref)
            event = EventService.get_event(registration.event.slug)
            reg_data = {
                'registration': EventService._registration_to_dict(registration),
                'qr_code': qr_code,
                'event': event
            }

        mail_configured = bool(current_app.config.get('MAIL_SERVER'))
        reg_data['mail_configured'] = mail_configured

        if not mail_configured and not session.get('email_reminder_shown'):
            flash('⚠️ Email notifications are not configured.', 'warning')
            session['email_reminder_shown'] = True

        return render_template('events/attendee/registration_confirmation.html', **reg_data)
    except Exception as e:
        logger.error(f"Confirmation error: {e}")
        flash('An error occurred', 'danger')
        return redirect(url_for('events.my_registrations'))


@events_bp.route("/registration/<reg_ref>/cancel", methods=['POST'])
@login_required
def cancel_registration(reg_ref):
    """Cancel a registration."""
    success, error = EventService.cancel_registration(reg_ref, current_user.id)
    if success:
        return jsonify({'success': True, 'message': 'Registration cancelled successfully'})
    return jsonify({'success': False, 'error': error}), 400


@events_bp.route("/dismiss-email-reminder", methods=['POST'])
@login_required
def dismiss_email_reminder():
    """Dismiss email configuration reminder."""
    session.pop('email_reminder_shown', None)
    return jsonify({'success': True})


# ============================================================================
# ORCHESTRATION — Service Assignment (Events ↔ Accommodation/Transport)
# ============================================================================

@events_bp.route("/<identifier>/assign-service", methods=['POST'])
@login_required
def assign_service_to_attendee_route(identifier):
    """Assign accommodation or transport to an attendee."""
    event = EventService.get_event(identifier)
    if not check_event_access(event, current_user):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403

    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400

    attendee_id = data.get('attendee_id')
    booking_type = data.get('booking_type')
    booking_id = data.get('booking_id')

    if not all([attendee_id, booking_type, booking_id]):
        return jsonify({'success': False, 'error': 'Missing required fields'}), 400
    if booking_type not in ['accommodation', 'transport', 'meal']:
        return jsonify({'success': False, 'error': 'Invalid booking type'}), 400

    result, error = EventService.assign_service_to_attendee(
        attendee_id=attendee_id, identifier=identifier,
        booking_type=booking_type, booking_id=booking_id,
        managed_by=current_user.id
    )

    if error:
        return jsonify({'success': False, 'error': error}), 400
    return jsonify({'success': True, 'assignment': result,
                    'message': f'{booking_type.title()} assigned successfully'})


@events_bp.route("/<identifier>/assignments")
@login_required
def get_event_assignments(identifier):
    """Get all assignments for an event."""
    event = EventService.get_event(identifier)
    if not check_event_access(event, current_user):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403

    assignments = EventService.get_event_assignments(identifier)
    return jsonify({'success': True, 'assignments': assignments})


@events_bp.route("/<identifier>/available-bookings/<booking_type>")
@login_required
def get_available_bookings(identifier, booking_type):
    """Get available bookings for an event's city."""
    event = EventService.get_event(identifier)
    if not event:
        return jsonify({'success': False, 'error': 'Event not found'}), 404

    city = event.get('city')
    if not city:
        return jsonify({'success': False, 'error': 'Event city not specified'}), 400

    bookings = []

    if booking_type == 'accommodation':
        try:
            from app.accommodation.models.booking import AccommodationBooking
            from app.accommodation.models.property import Property
            properties = Property.query.filter_by(city=city, is_active=True).all()
            property_ids = [p.id for p in properties]
            if property_ids:
                acc_bookings = AccommodationBooking.query.filter(
                    AccommodationBooking.property_id.in_(property_ids),
                    AccommodationBooking.status.in_(['confirmed', 'pending'])
                ).all()
                for b in acc_bookings:
                    bookings.append({
                        'id': b.id, 'type': 'accommodation',
                        'name': f"{b.accommodation_property.name} - Room",
                        'guest_name': b.guest_name or f"Guest #{b.guest_user_id}",
                        'check_in': b.check_in.isoformat() if b.check_in else None,
                        'check_out': b.check_out.isoformat() if b.check_out else None,
                    })
        except ImportError:
            logger.warning("Accommodation module not available")
        except Exception as e:
            logger.error(f"Error fetching accommodation: {e}")

    elif booking_type == 'transport':
        try:
            from app.transport.models import Booking as TransportBooking
            transport_bookings = TransportBooking.query.filter(
                TransportBooking.status.in_(['confirmed', 'pending'])
            ).all()
            for b in transport_bookings:
                bookings.append({
                    'id': b.id, 'type': 'transport',
                    'name': f"{b.vehicle_type or 'Vehicle'} - {b.pickup_location} to {b.dropoff_location}",
                    'guest_name': f"User #{b.user_id}",
                    'pickup_time': b.pickup_time.isoformat() if b.pickup_time else None,
                })
        except ImportError:
            logger.warning("Transport module not available")
        except Exception as e:
            logger.error(f"Error fetching transport: {e}")

    return jsonify({'success': True, 'bookings': bookings})


# ============================================================================
# MODERATION — State Machine Driven (Uses change_event_status via services.py)
# ============================================================================

@events_bp.route("/<identifier>/approve", methods=['POST'])
@login_required
def approve_event(identifier):
    """Approve a pending event → APPROVED."""
    event = EventService.get_event_model(identifier)
    if not event:
        return jsonify({'success': False, 'error': 'Event not found'}), 404

    has_perm, error = require_event_permission(current_user, event, 'approve')
    if not has_perm:
        return jsonify({'success': False, 'error': error}), 403

    success, error = EventService.change_event_status(
        identifier, EventStatus.APPROVED, current_user.id,
        is_admin=is_system_admin(current_user),
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string if request.user_agent else None
    )
    if not success:
        return jsonify({'success': False, 'error': error}), 400
    return jsonify({'success': True, 'message': 'Event approved'})


@events_bp.route("/<identifier>/reject", methods=['POST'])
@login_required
def reject_event(identifier):
    """Reject a pending event → REJECTED."""
    event = EventService.get_event_model(identifier)
    if not event:
        return jsonify({'success': False, 'error': 'Event not found'}), 404

    has_perm, error = require_event_permission(current_user, event, 'reject')
    if not has_perm:
        return jsonify({'success': False, 'error': error}), 403

    reason = request.json.get('reason') if request.is_json else None
    if not reason:
        return jsonify({'success': False, 'error': 'Reason is required for rejection'}), 400

    success, error = EventService.change_event_status(
        identifier, EventStatus.REJECTED, current_user.id,
        reason=reason,
        is_admin=is_system_admin(current_user),
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string if request.user_agent else None
    )
    if not success:
        return jsonify({'success': False, 'error': error}), 400
    return jsonify({'success': True, 'message': 'Event rejected'})

@events_bp.route("/<identifier>/publish", methods=['POST'])
@login_required
def publish_event(identifier):
    """Publish an approved event → PUBLISHED. Respects publish_permission."""
    event = EventService.get_event_model(identifier)
    if not event:
        return jsonify({'success': False, 'error': 'Event not found'}), 404

    is_admin = is_system_admin(current_user)
    is_owner = event.organizer_id == current_user.id
    publish_perm = getattr(event, 'publish_permission', 'either')

    # Enforce publish_permission
    if publish_perm == 'admin' and not is_admin:
        return jsonify({'success': False, 'error': 'Only admins can publish this event'}), 403
    if publish_perm == 'self' and not is_owner:
        return jsonify({'success': False, 'error': 'Only the organizer can publish this event'}), 403
    if publish_perm not in ('self', 'admin', 'either'):
        return jsonify({'success': False, 'error': f'Invalid publish permission: {publish_perm}'}), 400

    success, error = EventService.change_event_status(
        identifier, EventStatus.PUBLISHED, current_user.id,
        is_admin=is_admin,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string if request.user_agent else None
    )
    if not success:
        return jsonify({'success': False, 'error': error}), 400
    return jsonify({'success': True, 'message': 'Event published'})

@events_bp.route("/<identifier>/suspend", methods=['POST'])
@login_required
def suspend_event(identifier):
    """Suspend a published event → SUSPENDED."""
    event = EventService.get_event_model(identifier)
    if not event:
        return jsonify({'success': False, 'error': 'Event not found'}), 404

    has_perm, error = require_event_permission(current_user, event, 'suspend')
    if not has_perm:
        return jsonify({'success': False, 'error': error}), 403

    reason = request.json.get('reason') if request.is_json else 'Administrative suspension'
    duration = request.json.get('duration', '7d') if request.is_json else '7d'

    success, error = EventService.change_event_status(
        identifier, EventStatus.SUSPENDED, current_user.id,
        reason=f"{reason} (duration: {duration})",
        is_admin=is_system_admin(current_user),
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string if request.user_agent else None
    )
    if not success:
        return jsonify({'success': False, 'error': error}), 400
    return jsonify({'success': True, 'message': f'Event suspended ({duration})'})


@events_bp.route("/<identifier>/reactivate", methods=['POST'])
@login_required
def reactivate_event(identifier):
    """Reactivate a suspended/paused event → PUBLISHED."""
    event = EventService.get_event_model(identifier)
    if not event:
        return jsonify({'success': False, 'error': 'Event not found'}), 404

    has_perm, error = require_event_permission(current_user, event, 'reactivate')
    if not has_perm:
        return jsonify({'success': False, 'error': error}), 403

    success, error = EventService.change_event_status(
        identifier, EventStatus.PUBLISHED, current_user.id,
        is_admin=is_system_admin(current_user),
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string if request.user_agent else None
    )
    if not success:
        return jsonify({'success': False, 'error': error}), 400
    return jsonify({'success': True, 'message': 'Event reactivated'})


@events_bp.route("/<identifier>/pause", methods=['POST'])
@login_required
def pause_event(identifier):
    """Pause a published event → PAUSED."""
    event = EventService.get_event_model(identifier)
    if not event:
        return jsonify({'success': False, 'error': 'Event not found'}), 404

    has_perm, error = require_event_permission(current_user, event, 'pause')
    if not has_perm:
        return jsonify({'success': False, 'error': error}), 403

    is_admin = is_system_admin(current_user)
    success, error = EventService.change_event_status(
        identifier, EventStatus.PAUSED, current_user.id,
        is_admin=is_admin,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string if request.user_agent else None
    )
    if not success:
        return jsonify({'success': False, 'error': error}), 400
    return jsonify({'success': True, 'message': 'Event paused'})


@events_bp.route("/<identifier>/resume", methods=['POST'])
@login_required
def resume_event(identifier):
    """Resume a paused event → PUBLISHED."""
    event = EventService.get_event_model(identifier)
    if not event:
        return jsonify({'success': False, 'error': 'Event not found'}), 404

    has_perm, error = require_event_permission(current_user, event, 'resume')
    if not has_perm:
        return jsonify({'success': False, 'error': error}), 403

    is_admin = is_system_admin(current_user)
    success, error = EventService.change_event_status(
        identifier, EventStatus.PUBLISHED, current_user.id,
        is_admin=is_admin,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string if request.user_agent else None
    )
    if not success:
        return jsonify({'success': False, 'error': error}), 400
    return jsonify({'success': True, 'message': 'Event resumed'})


@events_bp.route("/<identifier>/cancel", methods=['POST'])
@login_required
def cancel_event(identifier):
    """Cancel an event → CANCELLED."""
    event = EventService.get_event_model(identifier)
    if not event:
        return jsonify({'success': False, 'error': 'Event not found'}), 404

    if event.organizer_id != current_user.id and not is_system_admin(current_user):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403

    reason = request.json.get('reason') if request.is_json else 'Cancelled by organizer'
    is_admin = is_system_admin(current_user)
    success, error = EventService.change_event_status(
        identifier, EventStatus.CANCELLED, current_user.id,
        reason=reason,
        is_admin=is_admin,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string if request.user_agent else None
    )
    if not success:
        return jsonify({'success': False, 'error': error}), 400
    return jsonify({'success': True, 'message': 'Event cancelled'})


@events_bp.route("/<identifier>/delete", methods=['POST'])
@login_required
def delete_event(identifier):
    """Soft-delete an event (ARCHIVED for organizers, DELETED for admins)."""
    event = EventService.get_event_model(identifier)
    if not event:
        if not request.is_json:
            flash('Event not found', 'danger')
            return redirect(url_for('events.my_events'))
        return jsonify({'success': False, 'error': 'Event not found'}), 404

    has_perm, error = require_event_permission(current_user, event, 'delete')
    if not has_perm:
        if not request.is_json:
            flash(error or 'Unauthorized', 'danger')
            return redirect(url_for('events.my_events'))
        return jsonify({'success': False, 'error': error}), 403

    is_admin = is_system_admin(current_user)
    target_status = EventStatus.DELETED if is_admin else EventStatus.ARCHIVED

    success, error = EventService.change_event_status(
        identifier, target_status, current_user.id,
        reason=request.json.get('reason') if request.is_json else None,
        is_admin=is_admin,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string if request.user_agent else None
    )
    if not success:
        if not request.is_json:
            flash(error or 'Delete failed', 'danger')
            return redirect(url_for('events.my_events'))
        return jsonify({'success': False, 'error': error}), 400

    if not request.is_json:
        flash('Event deleted successfully', 'success')
        return redirect(url_for('events.my_events'))
    return jsonify({'success': True, 'message': 'Event deleted'})


# ============================================================================
# ADMIN ROUTES — Full System Admin Control Panel
# ============================================================================

@events_bp.route("/admin/dashboard")
@login_required
def admin_dashboard():
    """Super admin dashboard with full event oversight."""
    if not is_system_admin(current_user):
        flash('Admin access required', 'danger')
        return redirect(url_for('events.list'))

    dashboard_data = EventService.get_admin_dashboard_data()

    pending_approval = Event.query.filter_by(
        status=EventStatus.PENDING_APPROVAL, is_deleted=False
    ).order_by(Event.created_at.desc()).all()

    recent_events = Event.query.filter_by(is_deleted=False).order_by(
        Event.status.desc(), Event.created_at.desc()
    ).limit(20).all()

    categories = db.session.query(Event.category, func.count(Event.id)).filter_by(
        is_deleted=False
    ).group_by(Event.category).all()

    return render_template('events/admin/dashboard.html',
                           total_events=dashboard_data.get('total_events', 0),
                           published_events=dashboard_data.get('published_events', 0),
                           pending_events=dashboard_data.get('pending_events', 0),
                           rejected_events=dashboard_data.get('rejected_events', 0),
                           completed_events=dashboard_data.get('completed_events', 0),
                           cancelled_events=dashboard_data.get('cancelled_events', 0),
                           suspended_events=dashboard_data.get('suspended_events', 0),
                           total_registrations=dashboard_data.get('total_registrations', 0),
                           checked_in_registrations=dashboard_data.get('checked_in_registrations', 0),
                           pending_approval=pending_approval,
                           recent_events=recent_events,
                           categories=categories)


@events_bp.route("/admin/events")
@login_required
def admin_events():
    """View all events as admin with status filtering."""
    if not is_system_admin(current_user):
        return redirect(url_for('events.list'))

    status_filter = request.args.get('status', 'all')
    if status_filter == 'all':
        events = Event.query.filter_by(is_deleted=False).order_by(Event.created_at.desc()).all()
    else:
        sanitized = EventService.sanitize_status(status_filter)
        events = Event.query.filter_by(status=sanitized, is_deleted=False).order_by(Event.created_at.desc()).all()

    return render_template('events/admin/events.html', events=events, current_filter=status_filter)


# Admin quick-actions that go through the state machine
@events_bp.route("/admin/<identifier>/approve", methods=['POST'])
@login_required
def admin_approve(identifier):
    """Admin approve AND publish — PENDING_APPROVAL → APPROVED → PUBLISHED."""
    if not is_system_admin(current_user):
        return jsonify({'success': False, 'error': 'Unauthorized - Super Admin access required'}), 403

    # First approve
    success, error = EventService.change_event_status(
        identifier, EventStatus.APPROVED, current_user.id,
        is_admin=True,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string if request.user_agent else None
    )
    if not success:
        return jsonify({'success': False, 'error': error}), 400

    # Then publish
    success, error = EventService.change_event_status(
        identifier, EventStatus.PUBLISHED, current_user.id,
        is_admin=True,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string if request.user_agent else None
    )
    if not success:
        return jsonify({'success': False, 'error': error}), 400

    logger.info(f"MODERATION | admin_approve+publish | event={identifier} | admin={current_user.id}")
    return jsonify({'success': True, 'message': 'Event approved and published'})


@events_bp.route("/admin/<identifier>/reject", methods=['POST'])
@login_required
def admin_reject(identifier):
    """Admin reject an event."""
    if not is_system_admin(current_user):
        return jsonify({'success': False, 'error': 'Unauthorized - Super Admin access required'}), 403

    data = request.get_json()
    reason = data.get('reason', 'No reason provided') if data else 'No reason provided'

    success, error = EventService.change_event_status(
        identifier, EventStatus.REJECTED, current_user.id,
        reason=reason, is_admin=True,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string if request.user_agent else None
    )
    if not success:
        return jsonify({'success': False, 'error': error}), 400

    logger.info(f"MODERATION | admin_reject | event={identifier} | admin={current_user.id} | reason={reason[:80]}")
    return jsonify({'success': True, 'message': 'Event rejected'})


@events_bp.route("/admin/<identifier>/suspend", methods=['POST'])
@login_required
def admin_suspend(identifier):
    """Admin suspend an event with reason and duration."""
    if not is_system_admin(current_user):
        return jsonify({'success': False, 'error': 'Unauthorized - Super Admin access required'}), 403

    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400

    reason = data.get('reason', '').strip()
    duration = data.get('duration', '7d')

    if not reason:
        return jsonify({'success': False, 'error': 'Suspension reason is required'}), 400

    success, error = EventService.change_event_status(
        identifier, EventStatus.SUSPENDED, current_user.id,
        reason=f"{reason} (duration: {duration})", is_admin=True,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string if request.user_agent else None
    )
    if not success:
        return jsonify({'success': False, 'error': error}), 400

    logger.info(f"MODERATION | admin_suspend | event={identifier} | admin={current_user.id} | duration={duration} | reason={reason[:80]}")
    return jsonify({'success': True, 'message': f'Event suspended ({duration})'})


@events_bp.route("/admin/<identifier>/restore", methods=['POST'])
@login_required
def admin_restore(identifier):
    """Admin restore a suspended event → PUBLISHED."""
    if not is_system_admin(current_user):
        return jsonify({'success': False, 'error': 'Unauthorized - Super Admin access required'}), 403

    success, error = EventService.change_event_status(
        identifier, EventStatus.PUBLISHED, current_user.id,
        is_admin=True,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string if request.user_agent else None
    )
    if not success:
        return jsonify({'success': False, 'error': error}), 400

    logger.info(f"MODERATION | admin_restore | event={identifier} | admin={current_user.id}")
    return jsonify({'success': True, 'message': 'Event reinstated'})


@events_bp.route("/admin/<identifier>/deactivate", methods=['POST'])
@login_required
def admin_deactivate(identifier):
    """Admin deactivate an event → ARCHIVED (preserves data, hides from public)."""
    if not is_system_admin(current_user):
        return jsonify({'success': False, 'error': 'Unauthorized - Super Admin access required'}), 403

    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400

    reason = data.get('reason', '').strip()
    if not reason:
        return jsonify({'success': False, 'error': 'Deactivation reason is required'}), 400

    success, error = EventService.change_event_status(
        identifier, EventStatus.ARCHIVED, current_user.id,
        reason=reason, is_admin=True,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string if request.user_agent else None
    )
    if not success:
        return jsonify({'success': False, 'error': error}), 400

    logger.info(f"MODERATION | admin_deactivate | event={identifier} | admin={current_user.id} | reason={reason[:80]}")
    return jsonify({'success': True, 'message': 'Event deactivated'})


@events_bp.route("/admin/<identifier>/takedown", methods=['POST'])
@login_required
def admin_takedown(identifier):
    """Policy takedown — severe enforcement. Archives + marks for compliance."""
    if not is_system_admin(current_user):
        return jsonify({'success': False, 'error': 'Unauthorized - Super Admin access required'}), 403

    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400

    category = data.get('category', '').strip()
    reason = data.get('reason', '').strip()
    notify_organiser = data.get('notify_organiser', True)

    if not category:
        return jsonify({'success': False, 'error': 'Violation category is required'}), 400
    if not reason:
        return jsonify({'success': False, 'error': 'Detailed reason is required'}), 400

    VALID_CATEGORIES = {'fraud', 'illegal_activity', 'hate_speech', 'misinformation', 'spam', 'copyright', 'other'}
    if category not in VALID_CATEGORIES:
        return jsonify({'success': False, 'error': 'Invalid violation category'}), 400

    event = resolve_event_admin(identifier)
    if not event or event.is_deleted:
        return jsonify({'success': False, 'error': 'Event not found'}), 404

    # Record takedown metadata
    event.takedown_reason = reason
    event.takedown_category = category
    event.taken_down_at = datetime.utcnow()
    event.taken_down_by_id = current_user.id
    event.rejection_reason = f"[POLICY TAKEDOWN – {category.upper()}] {reason}"

    success, error = EventService.change_event_status(
        identifier, EventStatus.DELETED, current_user.id,
        reason=f"TAKEDOWN [{category}]: {reason}", is_admin=True,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string if request.user_agent else None
    )

    if not success:
        db.session.rollback()
        return jsonify({'success': False, 'error': error}), 400

    logger.warning(
        f"COMPLIANCE | takedown | event={event.slug} | admin={current_user.id} "
        f"| category={category} | notify={notify_organiser} | reason={reason[:120]}"
    )

    return jsonify({'success': True, 'message': f'Event taken down ({category})'})


# ============================================================================
# DEBUG ROUTES
# ============================================================================

@events_bp.route("/admin/debug/events")
@login_required
def admin_debug_events():
    """Debug: list all events with statuses."""
    if os.getenv('FLASK_ENV', 'production') == 'production' and \
       not os.getenv('ENABLE_DEBUG_ENDPOINTS', '').lower() == 'true':
        return jsonify({"success": False, "error": "Not available"}), 404

    if not is_system_admin(current_user):
        return jsonify({"success": False, "error": "Unauthorized"}), 403

    events = Event.query.all()
    events_data = [{
        'id': e.id, 'slug': e.slug, 'name': e.name,
        'status': e.status.value if hasattr(e.status, 'value') else str(e.status),
        'is_deleted': e.is_deleted,
        'created_at': e.created_at.isoformat() if e.created_at else None,
        'organizer_id': e.organizer_id
    } for e in events]

    status_counts = {}
    for e in events:
        s = e.status.value if hasattr(e.status, 'value') else str(e.status)
        status_counts[s] = status_counts.get(s, 0) + 1

    return jsonify({"success": True, "events": events_data, "counts": status_counts, "total": len(events)})


@events_bp.route("/admin/debug/counts")
@login_required
def admin_debug_counts():
    """Debug: event counts by status."""
    if os.getenv('FLASK_ENV', 'production') == 'production' and \
       not os.getenv('ENABLE_DEBUG_ENDPOINTS', '').lower() == 'true':
        return jsonify({"success": False, "error": "Not available"}), 404

    if not is_system_admin(current_user):
        return jsonify({"success": False, "error": "Unauthorized"}), 403

    counts = {
        'total': Event.query.filter_by(is_deleted=False).count(),
        'published': Event.query.filter_by(status=EventStatus.PUBLISHED, is_deleted=False).count(),
        'pending': Event.query.filter_by(status=EventStatus.PENDING_APPROVAL, is_deleted=False).count(),
        'rejected': Event.query.filter_by(status=EventStatus.REJECTED, is_deleted=False).count(),
        'suspended': Event.query.filter_by(status=EventStatus.SUSPENDED, is_deleted=False).count(),
        'paused': Event.query.filter_by(status=EventStatus.PAUSED, is_deleted=False).count(),
        'completed': Event.query.filter_by(status=EventStatus.COMPLETED, is_deleted=False).count(),
        'cancelled': Event.query.filter_by(status=EventStatus.CANCELLED, is_deleted=False).count(),
        'archived': Event.query.filter_by(status=EventStatus.ARCHIVED, is_deleted=False).count(),
        'draft': Event.query.filter_by(status=EventStatus.DRAFT, is_deleted=False).count(),
    }

    reg_counts = {
        'total': EventRegistration.query.count(),
        'checked_in': EventRegistration.query.filter_by(status='checked_in').count(),
    }

    return jsonify({"success": True, "event_counts": counts, "registration_counts": reg_counts})
