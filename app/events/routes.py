# app/events/routes.py
"""
Event routes - Unified entry points for all user roles
"""
from flask import render_template, request, jsonify, redirect, url_for, flash, session, make_response
from flask_login import login_required, current_user
from app.events import events_bp
from app.events.services import EventService
# SoldOutException is inside EventService class
from app.events.models import Event, EventRegistration, TicketType, Waitlist
# Remove tight coupling - define fallback functions
def search_properties(city=None, limit=10):
    """Fallback function when accommodation module is not available"""
    # Return empty list to avoid breaking the UI
    return []

# Define a fallback BookingContextType
try:
    from app.accommodation.models.booking import BookingContextType
except ImportError:
    from enum import Enum
    class BookingContextType(Enum):
        EVENT = "event"
        TOURISM = "tourism"
        TRANSPORT = "transport"
        GENERAL = "general"
from app.extensions import db
from app.events.tasks import process_event_registration
from sqlalchemy import func
from datetime import datetime, timedelta
import logging
import html

# Input sanitization
def sanitize_html(text, max_length=5000):
    """Sanitize HTML input to prevent XSS."""
    if not text:
        return text

    # Truncate to max length
    if len(text) > max_length:
        text = text[:max_length]

    # Escape HTML special characters
    text = html.escape(text)

    # Allow safe line breaks
    text = text.replace('\n', '<br>')

    return text
import secrets

# CSRF protection






# Rate limiting
import time
from collections import defaultdict

# Simple in-memory rate limiter (replace with Redis in production)
_rate_limit_data = defaultdict(list)

def rate_limit(key, limit=10, window=60):
    """Simple rate limiter."""
    now = time.time()
    window_start = now - window

    # Clean old entries
    requests = _rate_limit_data[key]
    requests[:] = [req_time for req_time in requests if req_time > window_start]

    if len(requests) >= limit:
        return False

    requests.append(now)
    return True

logger = logging.getLogger(__name__)


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def is_system_admin(user):
    """Check if user is a system admin (super admin)"""
    if not user or not user.is_authenticated:
        return False

    # Use proper permission checking
    from app.auth.policy import can
    try:
        return can(user, "admin.system")
    except:
        # Fallback to legacy method
        return user.is_super_admin() if hasattr(user, 'is_super_admin') else False


# ============================================================
# PUBLIC ROUTES
# ============================================================

@events_bp.route("/")
def list():
    """List all events"""
    events = EventService.get_all_events(status='active')
    return render_template('events/public/list.html', events=events)


@events_bp.route("/<event_slug>")
def landing(event_slug):
    """Landing page for an event"""
    event = EventService.get_event(event_slug)
    if not event:
        return render_template('events/public/not_found.html', event_slug=event_slug), 404

    properties = search_properties(city=event['city'])

    return render_template(
        'events/public/landing.html',
        event=event,
        properties=properties,
        context_type=BookingContextType.EVENT.value,
        context_id=event_slug,
        context_metadata={
            'event_name': event['name'],
            'event_dates': f"{event['start_date']} to {event['end_date']}" if event.get('start_date') else '',
            'venue': event.get('venue', '')
        }
    )


@events_bp.route("/api/<event_slug>/properties")
def api_properties(event_slug):
    """JSON API for event properties"""
    event = EventService.get_event(event_slug)
    if not event:
        return jsonify({'error': 'Event not found'}), 404

    properties = search_properties(city=event['city'])
    return jsonify({
        'success': True,
        'properties': properties,
        'count': len(properties)
    })


# ============================================================
# DASHBOARDS (THE HUB)
# ============================================================

@events_bp.route("/hub")
@login_required
def events_hub():
    """Unified landing page for all event-related activities"""
    from app.wallet.services.wallet_service import WalletService

    # Fetch unified data
    attendee_data = EventService.get_attendee_dashboard_data(current_user.id)
    organizer_data = EventService.get_organizer_dashboard_data(current_user.id)
    provider_data = EventService.get_service_provider_dashboard_data(current_user.id)

    wallet_balance = 0
    try:
        wallet = WalletService.get_wallet_by_user_id(current_user.id)
        if wallet:
            wallet_balance = wallet.balance
    except Exception:
        pass

    admin_stats = None
    if is_system_admin(current_user):
        admin_stats = EventService.get_admin_dashboard_data()

    return render_template('events/events_hub.html',
                           registrations=attendee_data['upcoming_registrations'],
                           managed_events=organizer_data['active_events'],
                           relevant_events=provider_data['relevant_events'],
                           wallet_balance=wallet_balance,
                           admin_stats=admin_stats)


@events_bp.route("/my-registrations")
@login_required
def my_registrations():
    """Attendee Dashboard - Detailed view of user's event registrations"""
    data = EventService.get_attendee_dashboard_data(current_user.id)

    # Get wallet balance
    from app.wallet.services.wallet_service import WalletService
    wallet_balance = 0
    try:
        wallet = WalletService.get_wallet_by_user_id(current_user.id)
        if wallet:
            wallet_balance = wallet.balance
    except Exception:
        pass

    # Get current date for filtering
    from datetime import date
    current_date = date.today().isoformat()

    return render_template('events/attendee/my_registrations.html',
                           registrations=data['upcoming_registrations'] + data['past_registrations'],
                           wallet_balance=wallet_balance,
                           current_date=current_date)


@events_bp.route("/organizer/dashboard/<event_slug>")
@login_required
def organizer_dashboard(event_slug):
    """Specific Event Organizer Dashboard"""
    event = EventService.get_event(event_slug)
    if not event or event.get('organizer_id') != current_user.id:
        flash('Unauthorized access', 'danger')
        return redirect(url_for('events.my_events'))

    stats = EventService.get_event_stats(event_slug)
    registrations = EventService.get_registrations_by_event(event_slug)

    return render_template('events/organizer/organizer_dashboard.html',
                           event=event,
                           stats=stats,
                           registrations=registrations)


@events_bp.route("/service-provider/dashboard")
@login_required
def service_provider_dashboard():
    """Service Provider Dashboard"""
    from app.wallet.services.wallet_service import WalletService

    data = EventService.get_service_provider_dashboard_data(current_user.id)

    wallet_balance = 0
    try:
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


# ============================================================
# ORGANIZER ACTIONS
# ============================================================

@events_bp.route("/my-events")
@login_required
def my_events():
    """Organizer List - User's managed events page"""
    events = EventService.get_events_by_organizer(current_user.id)
    return render_template('events/organizer/my_events.html', events=events)


@events_bp.route("/create", methods=['GET', 'POST'])
@login_required
def create_event():
    """Create event page"""
    # Rate limiting
    if not rate_limit(f"create_event:{current_user.id}", limit=5, window=300):
        return jsonify({'success': False, 'error': 'Too many requests. Please try again later.'}), 429

    if request.method == 'GET':
        return render_template('events/create.html')

    # Handle both JSON and form data

    # Get data based on content type
    if request.is_json:
        data = request.get_json()
    else:
        # Handle form data
        data = request.form.to_dict()
        # Handle registration_required checkbox
        data['registration_required'] = 'registration_required' in request.form
        # Handle ticket tiers for form data
        tier_names = request.form.getlist('tier_name[]')
        tier_prices = request.form.getlist('tier_price[]')
        tier_capacities = request.form.getlist('tier_capacity[]')

        if tier_names and tier_names[0]:  # At least one tier is provided
            data['ticket_tiers'] = []
            for i in range(len(tier_names)):
                if tier_names[i]:  # Only add if name is not empty
                    data['ticket_tiers'].append({
                        'name': tier_names[i],
                        'price': float(tier_prices[i]) if i < len(tier_prices) and tier_prices[i] else 0.0,
                        'capacity': int(tier_capacities[i]) if i < len(tier_capacities) and tier_capacities[i] else None
                    })

    print(f"🔥 Received data: {data}")

    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400

    # Validate required fields
    required_fields = ['name', 'city', 'start_date']
    for field in required_fields:
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
        logger.error(f"Error creating event: {e}")
        print(f"🔥 Exception in create_event: {e}")
        return jsonify({'success': False, 'error': 'Internal server error'}), 500


@events_bp.route("/<event_slug>/edit", methods=['GET', 'POST'])
@login_required
def edit_event(event_slug):
    """Edit event page"""
    event = EventService.get_event(event_slug)
    if not event or (event.get('organizer_id') != current_user.id and not is_system_admin(current_user)):
        flash('Unauthorized', 'danger')
        return redirect(url_for('events.my_events'))

    if request.method == 'GET':
        return render_template('events/edit.html', event=event)

    try:
        data = request.get_json()
        success, error = EventService.update_event(event_slug, data, current_user.id)
        if not success:
            return jsonify({'success': False, 'error': error}), 400

        return jsonify({'success': True, 'redirect': url_for('events.my_events')})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@events_bp.route("/<event_slug>/delete", methods=['POST'])
@login_required
def delete_event(event_slug):
    """Delete event"""
    # First, get the event to check permissions
    event = EventService.get_event(event_slug)
    if not event:
        flash('Event not found', 'danger')
        return redirect(url_for('events.my_events'))

    # Check if current user is organizer or system admin
    if event.get('organizer_id') != current_user.id and not is_system_admin(current_user):
        flash('Unauthorized', 'danger')
        return redirect(url_for('events.my_events'))

    success, error = EventService.delete_event(event_slug, current_user.id)

    if success:
        flash('Event deleted successfully', 'success')
    else:
        flash(error or 'Unable to delete event', 'danger')

    return redirect(url_for('events.my_events'))


@events_bp.route("/<event_slug>/scanner")
@login_required
def scanner(event_slug):
    """Scanner interface for event staff"""
    event = EventService.get_event(event_slug)
    if not event:
        return render_template('events/public/not_found.html', event_slug=event_slug), 404

    # Define can_check_in_attendees locally since app.events.permissions doesn't exist
    def can_check_in_attendees(user, event_data):
        """Check if user can check in attendees for an event"""
        if not user or not user.is_authenticated:
            return False

        # Event organizers can always check in
        if event_data.get('organizer_id') == user.id:
            return True

        # System admins can check in
        if is_system_admin(user):
            return True

        # Check if user has event staff role with check-in permission
        from app.events.models import EventRole
        staff_role = EventRole.query.filter_by(
            event_id=event_data.get('event_id'),
            user_id=user.id,
            is_active=True
        ).first()

        if staff_role:
            # Check if role has check-in permission
            permissions = staff_role.permissions or []
            if 'check_in_attendees' in permissions:
                return True

        return False

    if not can_check_in_attendees(current_user, event):
        flash('Unauthorized', 'danger')
        return redirect(url_for('events.landing', event_slug=event_slug))

    return render_template('events/organizer/scanner.html', event=event)


@events_bp.route("/<event_slug>/analytics")
@login_required
def event_analytics(event_slug):
    """Detailed event analytics for organizers"""
    event = EventService.get_event(event_slug)
    if not event or event.get('organizer_id') != current_user.id:
        flash('Unauthorized access', 'danger')
        return redirect(url_for('events.my_events'))

    # Mock data for charts
    daily_trend = [
        {'date': (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d'), 'count': 5 + i}
        for i in range(7, 0, -1)
    ]
    checkin_trend = [
        {'date': (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d'), 'count': 2 + i}
        for i in range(7, 0, -1)
    ]

    stats = EventService.get_event_stats(event_slug)
    # Add rate calculation
    stats['checked_in'] = stats.get('checked_in_count', 0)
    stats['total'] = stats.get('total_registrations', 0)
    stats['checkin_rate'] = round((stats['checked_in'] / stats['total'] * 100), 1) if stats['total'] > 0 else 0

    revenue_by_ticket = {tt['name']: tt['registration_count'] * tt['price'] for tt in event.get('ticket_types', [])}
    demographics = {'Uganda': 45, 'Kenya': 12, 'Tanzania': 8, 'Other': 15}  # Mock data

    return render_template('events/organizer/analytics.html',
                           event=event,
                           stats=stats,
                           daily_trend=daily_trend,
                           checkin_trend=checkin_trend,
                           revenue_by_ticket=revenue_by_ticket,
                           demographics=demographics)


@events_bp.route("/<event_slug>/export")
@login_required
def export_attendees(event_slug):
    """Export attendee list as CSV"""
    event = EventService.get_event(event_slug)
    if not event or event.get('organizer_id') != current_user.id:
        flash('Unauthorized', 'danger')
        return redirect(url_for('events.my_events'))

    registrations = EventService.get_registrations_by_event(event_slug)

    import io
    import csv
    from flask import Response

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Ref', 'Name', 'Email', 'Ticket Type', 'Status', 'Registered At'])

    for reg in registrations:
        writer.writerow([
            reg['registration_ref'],
            reg['full_name'],
            reg['email'],
            reg['ticket_type'],
            reg['status'],
            reg['created_at']
        ])

    output.seek(0)
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-disposition": f"attachment; filename=attendees_{event_slug}.csv"}
    )


# ============================================================
# REGISTRATION & CHECK-IN
# ============================================================

@events_bp.route("/<event_slug>/register", methods=['GET', 'POST'])
@login_required
def register(event_slug):
    """Register for an event with async processing and payment integration"""
    event = EventService.get_event(event_slug)
    if not event:
        return render_template('events/public/not_found.html', event_slug=event_slug), 404

    if request.method == 'GET':
        user_data = {
            'full_name': getattr(current_user, 'username', current_user.email),
            'email': current_user.email,
            'phone': getattr(current_user, 'phone', ''),
            'nationality': getattr(current_user, 'nationality', ''),
        }
        return render_template('events/attendee/register.html', event=event, user_data=user_data)

    try:
        data = request.get_json()

        # 1. Perform database transaction (Atomic Registration)
        registration, _, error = EventService.register_for_event(
            event_slug, current_user.id, data
        )

        if error:
            return jsonify({'success': False, 'error': error}), 400

        # 2. Trigger Background Task (Async Processing)
        process_event_registration.delay(registration['id'], event_slug)

        return jsonify({
            'success': True,
            'redirect': url_for('events.registration_confirmation', reg_ref=registration['registration_ref']),
            'message': 'Registration received and is being processed!'
        }), 202

    except Exception as e:
        # Check if it's a SoldOutException
        if "sold out" in str(e).lower():
            return jsonify({'success': False, 'error': str(e)}), 400
        logger.error(f"Registration route error: {e}")
        return jsonify({'success': False, 'error': "An unexpected error occurred."}), 500


@events_bp.route("/registration-confirmation/<reg_ref>")
@login_required
def registration_confirmation(reg_ref):
    """Show registration confirmation with QR code"""
    # Get from session or database
    reg_data = session.get('last_registration')

    if not reg_data or reg_data['registration']['registration_ref'] != reg_ref:
        # Fetch from database
        registration = EventRegistration.query.filter_by(registration_ref=reg_ref).first()
        if not registration or registration.user_id != current_user.id:
            flash('Registration not found', 'danger')
            return redirect(url_for('events.my_registrations'))

        # Generate QR code again
        qr_code = EventService._generate_qr_code(registration.qr_token, registration.registration_ref)
        event = EventService.get_event(registration.event.slug)

        reg_data = {
            'registration': EventService._registration_to_dict(registration),
            'qr_code': qr_code,
            'event': event
        }

    return render_template('events/attendee/registration_confirmation.html', **reg_data)


@events_bp.route("/event/<event_slug>/attendees")
@login_required
def event_attendees(event_slug):
    """Show attendees for an event (organizer only)"""
    event = EventService.get_event(event_slug)
    if not event:
        return render_template('events/public/not_found.html', event_slug=event_slug), 404

    # Check if user is organizer or system admin
    if event.get('organizer_id') != current_user.id and not is_system_admin(current_user):
        flash('You do not have permission to view attendees', 'danger')
        return redirect(url_for('events.landing', event_slug=event_slug))

    registrations = EventService.get_registrations_by_event(event_slug)
    stats = {
        'total': len(registrations),
        'checked_in': len([r for r in registrations if r.get('status') == 'checked_in']),
        'confirmed': len([r for r in registrations if r.get('status') == 'confirmed']),
        'cancelled': len([r for r in registrations if r.get('status') == 'cancelled']),
    }

    return render_template('events/organizer/attendees.html', event=event, registrations=registrations, stats=stats)


@events_bp.route("/api/checkin", methods=['POST'])
@login_required
def api_checkin():
    """JSON API for QR code check-in"""
    data = request.get_json()
    qr_token = data.get('qr_token')
    success, message, attendee = EventService.check_in_attendee(qr_token, current_user.id)

    if success:
        return jsonify({'success': True, 'message': message, 'attendee': attendee})
    else:
        return jsonify({'success': False, 'error': message}), 400


# ============================================================
# SYSTEM ADMIN ROUTES
# ============================================================

@events_bp.route("/admin/dashboard")
@login_required
def admin_dashboard():
    """Super admin dashboard"""
    if not is_system_admin(current_user):
        flash('Admin access required', 'danger')
        return redirect(url_for('events.list'))

    data = EventService.get_admin_dashboard_data()
    from app.events.models import Event
    recent_events = Event.query.order_by(Event.created_at.desc()).limit(10).all()
    pending_approval = Event.query.filter_by(status='pending').all()

    # Categories for chart
    categories = db.session.query(Event.category, func.count(Event.id)).group_by(Event.category).all()

    return render_template('events/admin/dashboard.html',
                           **data,
                           recent_events=recent_events,
                           pending_approval=pending_approval,
                           categories=categories)


@events_bp.route("/admin/<event_slug>/approve", methods=['POST'])
@login_required
def admin_approve(event_slug):
    """Admin approve event"""
    if not is_system_admin(current_user):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403

    success, error = EventService.approve_event(event_slug, current_user.id)
    if success:
        flash('Event approved', 'success')
    return redirect(url_for('events.admin_dashboard'))


@events_bp.route("/admin/<event_slug>/reject", methods=['POST'])
@login_required
def admin_reject(event_slug):
    """Admin reject event"""
    if not is_system_admin(current_user):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403

    reason = request.get_json().get('reason', 'No reason provided')
    success, error = EventService.reject_event(event_slug, current_user.id, reason)
    return jsonify({'success': success})


@events_bp.route("/admin/events")
@login_required
def admin_events():
    """View all events as admin"""
    if not is_system_admin(current_user):
        return redirect(url_for('events.list'))

    status = request.args.get('status', 'all')
    if status == 'all':
        events = Event.query.all()
    else:
        events = Event.query.filter_by(status=status).all()

    return render_template('events/admin/events.html', events=events, current_filter=status)


@events_bp.route("/api/admin/stats")
@login_required
def api_admin_stats():
    """JSON API for admin dashboard stats — used by the super admin panel."""
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
    """JSON API for pending events list — used by the owner dashboard."""
    if not is_system_admin(current_user):
        return jsonify({"success": False, "error": "Unauthorized"}), 403

    try:
        pending_events = Event.query.filter_by(status='pending').order_by(Event.created_at.desc()).all()
        events_data = []
        for event in pending_events:
            events_data.append({
                'name': event.name,
                'slug': event.slug,
                'city': event.city,
                'organizer_id': event.organizer_id,
                'organizer_name': event.organizer.username if event.organizer else f"User {event.organizer_id}"
            })
        return jsonify({"success": True, "events": events_data})
    except Exception as e:
        logger.error(f"api_pending_events error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@events_bp.route("/<event_slug>/add-ticket-type", methods=['POST'])
@login_required
def add_ticket_type(event_slug):
    """Add a new ticket type to an event"""
    event = EventService.get_event(event_slug)
    if not event:
        return jsonify({'success': False, 'error': 'Event not found'}), 404

    if event.get('organizer_id') != current_user.id:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403

    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400

        # Call service to add ticket type
        from app.events.services import EventService
        ticket_type, error = EventService.add_ticket_type(event_slug, data, current_user.id)

        if error:
            return jsonify({'success': False, 'error': error}), 400

        return jsonify({'success': True, 'ticket_type': ticket_type})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@events_bp.route("/<event_slug>/staff")
@login_required
def event_staff(event_slug):
    """Manage event staff"""
    event = EventService.get_event(event_slug)
    if not event:
        return render_template('events/public/not_found.html', event_slug=event_slug), 404

    # Check permission
    if event.get('organizer_id') != current_user.id and not is_system_admin(current_user):
        flash('Only event organizers can manage staff', 'danger')
        return redirect(url_for('events.landing', event_slug=event_slug))

    from app.events.models import EventRole
    staff = EventRole.query.filter_by(event_id=event.get('event_id'), is_active=True).all()

    return render_template('events/admin/staff.html', event=event, staff=staff)


@events_bp.route("/staff/<int:staff_id>/remove", methods=['POST'])
@login_required
def remove_staff(staff_id):
    """Remove staff member from event"""
    from app.events.models import EventRole

    staff = EventRole.query.get_or_404(staff_id)
    event = EventService.get_event_model_by_id(staff.event_id)

    if not event:
        return jsonify({'success': False, 'error': 'Event not found'}), 404

    # Check permission - use the is_system_admin function defined at the top of the file
    if event.organizer_id != current_user.id and not is_system_admin(current_user):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403

    try:
        staff.is_active = False
        db.session.commit()
        return jsonify({'success': True, 'message': 'Staff member removed successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
