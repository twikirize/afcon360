# app/events/routes.py

"""
Event routes - Unified entry points for all user roles
"""
from flask import render_template, request, jsonify, redirect, url_for, flash, session, make_response, current_app
from flask_login import login_required, current_user
from app.events import events_bp
from app.events.services import EventService
# SoldOutException is inside EventService class
from app.events.models import Event, EventRegistration, TicketType, Waitlist
from app.events.permissions import is_system_admin
from app.events.constants import EventStatus
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
from app.extensions import db, redis_client
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

def rate_limit(key, limit=10, window=60):
    """Redis-backed rate limiter safe for multi-worker deployments."""
    if not redis_client:
        # Fail open if Redis is unavailable — log and allow
        logger.warning(f"Rate limiter Redis unavailable, allowing request for key: {key}")
        return True
    try:
        pipe = redis_client.pipeline()
        cache_key = f"rate_limit:{key}"
        pipe.incr(cache_key)
        pipe.expire(cache_key, window)
        results = pipe.execute()
        current_count = results[0]
        return current_count <= limit
    except Exception as e:
        logger.warning(f"Rate limiter error: {e}, allowing request")
        return True

logger = logging.getLogger(__name__)


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def resolve_event(identifier):
    '''Resolve event by public_id (UUID) or slug'''
    from app.events.models import Event
    # Try as public_id first (exact UUID match)
    event = Event.query.filter_by(public_id=identifier).first()
    if event:
        return event
    # Fall back to slug
    return Event.query.filter_by(slug=identifier).first()



# ============================================================
# PUBLIC ROUTES
# ============================================================

@events_bp.route("/")
def list():
    """List all events"""
    events = EventService.get_all_events(status=EventStatus.PUBLISHED)
    return render_template('events/public/list.html', events=events)


@events_bp.route("/<identifier>")
def landing(identifier=None):
    """Landing page for an event"""
    lookup = identifier
    if not lookup:
        return render_template('events/public/not_found.html'), 404

    event_model = resolve_event(lookup)
    if not event_model:
        return render_template('events/public/not_found.html', event_slug=lookup), 404

    # Convert to dict using EventService
    event = EventService._event_to_dict(event_model)
    if not event:
        return render_template('events/public/not_found.html', event_slug=lookup), 404

    # Check if current user is registered for this event
    user_registered = False
    if current_user.is_authenticated:
        from app.events.models import EventRegistration
        registration = EventRegistration.query.filter_by(
            event_id=event_model.id,
            user_id=current_user.id,
            status='confirmed'
        ).first()
        user_registered = registration is not None

    # Calculate remaining capacity for each ticket type
    if event.get('ticket_types'):
        for tt in event['ticket_types']:
            tt['remaining'] = tt['capacity'] - tt['registration_count'] if tt.get('capacity') else None

    # Get total registrations count for social proof
    from app.events.models import EventRegistration
    total_registrations = EventRegistration.query.filter_by(event_id=event_model.id).count()

    # Get start time from event metadata if available
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
        is_admin=is_system_admin(current_user) if hasattr(current_user, 'is_authenticated') and current_user.is_authenticated else False,
        user_registered=user_registered,
        now=datetime.utcnow,
        total_registrations=total_registrations,
        event_start_time=start_time
    )


@events_bp.route("/api/event/<public_id>")
def api_get_event_by_public_id(public_id):
    """Get event by public_id (UUID)"""
    event_model = resolve_event(public_id)
    if not event_model:
        return jsonify({'error': 'Event not found'}), 404
    return jsonify(EventService._event_to_dict(event_model))

@events_bp.route("/api/<identifier>/properties")
def api_properties(identifier=None):
    """JSON API for event properties"""
    lookup = identifier
    if not lookup:
        return jsonify({'error': 'Event not found'}), 404

    event_model = resolve_event(lookup)
    if not event_model:
        return jsonify({'error': 'Event not found'}), 404
    event = EventService._event_to_dict(event_model)
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
    
    # Enrich registrations with assignment data
    all_registrations = data['upcoming_registrations'] + data['past_registrations']
    for reg in all_registrations:
        # Get assignment for this registration
        try:
            from app.events.models import EventAssignment, Event
            # Safely access event slug – event dict is always present now
            event_slug = reg.get('event', {}).get('slug')
            if event_slug:
                event = Event.query.filter_by(slug=event_slug).first()
                if event:
                    assignment = EventAssignment.query.filter_by(
                        event_id=event.id,
                        attendee_id=current_user.id
                    ).first()
                    if assignment:
                        reg['assignment'] = EventService._assignment_to_dict(assignment)
        except Exception as e:
            logger.warning(f"Could not load assignment for registration {reg.get('id')}: {e}")

    return render_template('events/attendee/my_registrations.html',
                           registrations=all_registrations,
                           wallet_balance=wallet_balance,
                           current_date=current_date)


@events_bp.route("/organizer/dashboard/<identifier>")
@login_required
def organizer_dashboard(identifier):
    """Specific Event Organizer Dashboard"""
    event = EventService.get_event(identifier)
    if not event or event.get('organizer_id') != current_user.id:
        flash('Unauthorized access', 'danger')
        return redirect(url_for('events.my_events'))

    stats = EventService.get_event_stats(identifier)
    registrations = EventService.get_registrations_by_event(identifier)

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
        return render_template('events/organizer/create.html')

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


@events_bp.route("/<identifier>/edit", methods=['GET', 'POST'])
@login_required
def edit_event(identifier):
    """Edit event page"""
    event = EventService.get_event(identifier)
    if not event or (event.get('organizer_id') != current_user.id and not is_system_admin(current_user)):
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




@events_bp.route("/<identifier>/scanner")
@login_required
def scanner(identifier):
    """Scanner interface for event staff"""
    event = EventService.get_event(identifier)
    if not event:
        return render_template('events/public/not_found.html', event_slug=identifier), 404

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
        # Get the actual event model to get the database ID
        event_model = EventService.get_event_model(identifier)
        if not event_model:
            return False

        staff_role = EventRole.query.filter_by(
            event_id=event_model.id,
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
        return redirect(url_for('events.landing', identifier=identifier))

    return render_template('events/organizer/scanner.html', event=event)


@events_bp.route("/<identifier>/analytics")
@login_required
def event_analytics(identifier):
    """Detailed event analytics for organizers"""
    event = EventService.get_event(identifier)
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

    stats = EventService.get_event_stats(identifier)
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


@events_bp.route("/<identifier>/export")
@login_required
def export_attendees(identifier):
    """Export attendee list as CSV"""
    event = EventService.get_event(identifier)
    if not event or event.get('organizer_id') != current_user.id:
        flash('Unauthorized', 'danger')
        return redirect(url_for('events.my_events'))

    registrations = EventService.get_registrations_by_event(identifier)

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
        headers={"Content-disposition": f"attachment; filename=attendees_{identifier}.csv"}
    )


# ============================================================
# REGISTRATION & CHECK-IN
# ============================================================

@events_bp.route("/<identifier>/register", methods=['GET', 'POST'])
@login_required
def register(identifier):
    """Register for an event with async processing and payment integration"""
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
        # Handle both JSON and form data
        if request.is_json:
            data = request.get_json()
        else:
            # Handle form data
            data = request.form.to_dict()
            # Convert numeric fields
            if 'ticket_type_id' in data:
                data['ticket_type_id'] = int(data['ticket_type_id'])

        # 1. Perform database transaction (Atomic Registration)
        registration, _, error = EventService.register_for_event(
            identifier, current_user.id, data
        )

        if error:
            return jsonify({'success': False, 'error': error}), 400

        # Store registration data in session for the confirmation page
        # We need to get the actual registration object to generate QR code
        from app.events.models import EventRegistration
        reg_obj = EventRegistration.query.filter_by(registration_ref=registration['registration_ref']).first()
        if reg_obj:
            # Generate QR code
            qr_code = EventService._generate_qr_code(reg_obj.qr_token, reg_obj.registration_ref)
            session['last_registration'] = {
                'registration': EventService._registration_to_dict(reg_obj),
                'qr_code': qr_code,
                'event': event
            }
        else:
            # Fallback to using the registration dict
            session['last_registration'] = {
                'registration': registration,
                'qr_code': None,
                'event': event
            }

        # 2. Trigger Background Task (Async Processing)
        # process_event_registration.delay(registration['id'], identifier)

        # Flash email reminder if not configured
        mail_configured = False
        try:
            mail_server = current_app.config.get('MAIL_SERVER')
            if mail_server:
                mail_configured = True
        except Exception:
            pass
        if not mail_configured and not session.get('email_reminder_shown', False):
            flash('⚠️ Email notifications are not configured. Please set up MAIL_SERVER in .env file to enable email confirmations. This reminder will appear until email is configured.', 'warning')
            session['email_reminder_shown'] = True

        # Determine if this is an AJAX request
        is_ajax = request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest'

        if is_ajax:
            # For AJAX/API requests, return enriched JSON with all registration details
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
                'redirect': url_for('events.registration_confirmation', reg_ref=registration['registration_ref']),
                'message': 'Registration received and is being processed!'
            }), 200
        else:
            # Regular form submission - perform actual HTTP redirect
            return redirect(url_for('events.registration_confirmation', reg_ref=registration['registration_ref']))

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
    try:
        # First, try to get from session
        reg_data = session.get('last_registration')

        # Check if the session data matches the requested registration reference
        if reg_data and reg_data.get('registration', {}).get('registration_ref') == reg_ref:
            # Clear the session data after using it to prevent reuse
            session.pop('last_registration', None)
            # Check if mail is configured
            mail_configured = False
            try:
                mail_server = current_app.config.get('MAIL_SERVER')
                if mail_server:
                    mail_configured = True
            except Exception:
                pass
            
            reg_data['mail_configured'] = mail_configured

            # Flash email reminder if not configured
            if not mail_configured and not session.get('email_reminder_shown', False):
                flash('⚠️ Email notifications are not configured. Please set up MAIL_SERVER in .env file to enable email confirmations. This reminder will appear until email is configured.', 'warning')
                session['email_reminder_shown'] = True

            return render_template('events/attendee/registration_confirmation.html', **reg_data)

        # If not in session, fetch from database
        from app.events.models import EventRegistration
        registration = EventRegistration.query.filter_by(registration_ref=reg_ref).first()
        if not registration or registration.user_id != current_user.id:
            flash('Registration not found', 'danger')
            return redirect(url_for('events.my_registrations'))

        # Generate QR code
        qr_code = EventService._generate_qr_code(registration.qr_token, registration.registration_ref)
        event = EventService.get_event(registration.event.slug)

        reg_data = {
            'registration': EventService._registration_to_dict(registration),
            'qr_code': qr_code,
            'event': event
        }

        # Check if mail is configured
        mail_configured = False
        try:
            mail_server = current_app.config.get('MAIL_SERVER')
            if mail_server:
                mail_configured = True
        except Exception:
            pass
        
        reg_data['mail_configured'] = mail_configured

        # Flash email reminder if not configured
        if not mail_configured and not session.get('email_reminder_shown', False):
            flash('⚠️ Email notifications are not configured. Please set up MAIL_SERVER in .env file to enable email confirmations. This reminder will appear until email is configured.', 'warning')
            session['email_reminder_shown'] = True

        return render_template('events/attendee/registration_confirmation.html', **reg_data)
    except Exception as e:
        logger.error(f"registration_confirmation error: {e}")
        flash('An error occurred while loading the confirmation page.', 'danger')
        return redirect(url_for('events.my_registrations'))


@events_bp.route("/event/<identifier>/attendees")
@login_required
def event_attendees(identifier):
    """Show attendees for an event (organizer only)"""
    event = EventService.get_event(identifier)
    if not event:
        return render_template('events/public/not_found.html', event_slug=identifier), 404

    # Check if user is organizer or system admin
    if event.get('organizer_id') != current_user.id and not is_system_admin(current_user):
        flash('You do not have permission to view attendees', 'danger')
        return redirect(url_for('events.landing', identifier=identifier))

    registrations = EventService.get_registrations_by_event(identifier)
    stats = {
        'total': len(registrations),
        'checked_in': len([r for r in registrations if r.get('status') == 'checked_in']),
        'confirmed': len([r for r in registrations if r.get('status') == 'confirmed']),
        'cancelled': len([r for r in registrations if r.get('status') == 'cancelled']),
    }

    return render_template('events/organizer/attendees.html', event=event, registrations=registrations, stats=stats)


@events_bp.route("/registration/<reg_ref>/cancel", methods=['POST'])
@login_required
def cancel_registration(reg_ref):
    """Cancel a registration"""
    success, error = EventService.cancel_registration(reg_ref, current_user.id)
    if success:
        return jsonify({'success': True, 'message': 'Registration cancelled successfully'})
    else:
        return jsonify({'success': False, 'error': error}), 400


@events_bp.route("/dismiss-email-reminder", methods=['POST'])
@login_required
def dismiss_email_reminder():
    """Dismiss the email configuration reminder"""
    session.pop('email_reminder_shown', None)
    return jsonify({'success': True})


@events_bp.route("/api/checkin", methods=['GET', 'POST'])
@login_required
def api_checkin():
    """JSON API for QR code check-in"""
    # Rate limiting: 60 requests per 60 seconds per user
    if not rate_limit(f"checkin:{current_user.id}", limit=60, window=60):
        return jsonify({'success': False, 'error': 'Too many requests. Please slow down.'}), 429

    # Extract token from POST JSON body or GET query param
    qr_token = None
    if request.method == 'POST':
        data = request.get_json()
        if data:
            qr_token = data.get('qr_token')
    else:
        qr_token = request.args.get('token')

    if not qr_token:
        return jsonify({'success': False, 'error': 'Missing qr_token parameter'}), 400

    success, message, attendee = EventService.check_in_attendee(qr_token, current_user.id)

    if success:
        return jsonify({'success': True, 'message': message, 'attendee': attendee})
    else:
        return jsonify({'success': False, 'error': message}), 400


@events_bp.route("/api/<event_slug>/checkin-stats")
@login_required
def api_checkin_stats(event_slug):
    """JSON API for real-time check-in stats (used by scanner dashboard)"""
    event = resolve_event(event_slug)
    if not event:
        return jsonify({'success': False, 'error': 'Event not found'}), 404

    # Permission check: only organizer or system admin
    if event.organizer_id != current_user.id and not is_system_admin(current_user):
        return jsonify({'success': False, 'error': 'Forbidden'}), 403

    from app.events.models import EventRegistration

    # Total registered = confirmed + checked_in
    total_registered = EventRegistration.query.filter(
        EventRegistration.event_id == event.id,
        EventRegistration.status.in_(['confirmed', 'checked_in'])
    ).count()

    # Total checked in
    total_checked_in = EventRegistration.query.filter(
        EventRegistration.event_id == event.id,
        EventRegistration.status == 'checked_in'
    ).count()

    # Last 10 check-ins
    recent_qs = EventRegistration.query.filter(
        EventRegistration.event_id == event.id,
        EventRegistration.status == 'checked_in'
    ).order_by(EventRegistration.checked_in_at.desc()).limit(10).all()

    recent_checkins = []
    for reg in recent_qs:
        recent_checkins.append({
            'full_name': reg.full_name,
            'ticket_type': reg.ticket_type,
            'checked_in_at': reg.checked_in_at.isoformat() if reg.checked_in_at else None,
            'registration_ref': reg.registration_ref,
        })

    return jsonify({
        'success': True,
        'total_registered': total_registered,
        'total_checked_in': total_checked_in,
        'recent_checkins': recent_checkins,
    })


# ============================================================
# EVENT MODERATION ROUTES (Protected backend-driven state transitions)
# ============================================================

@events_bp.route("/<identifier>/approve", methods=['POST'])
@login_required
def approve_event(identifier):
    """Approve a pending event"""
    from app.events.constants import EventStatus
    from app.events.permissions import require_event_permission
    
    event = EventService.get_event_model(identifier)
    if not event:
        return jsonify({'success': False, 'error': 'Event not found'}), 404
    
    # Check permission
    has_perm, error = require_event_permission(current_user, event, 'approve')
    if not has_perm:
        return jsonify({'success': False, 'error': error}), 403
    
    # Change status
    success, error = EventService.change_event_status(
        identifier, 
        EventStatus.APPROVED, 
        current_user.id,
        reason=request.json.get('reason') if request.is_json else None,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string if request.user_agent else None
    )
    
    if not success:
        return jsonify({'success': False, 'error': error}), 400
    
    return jsonify({'success': True, 'message': 'Event approved'})

@events_bp.route("/<identifier>/reject", methods=['POST'])
@login_required
def reject_event(identifier):
    """Reject a pending event"""
    from app.events.constants import EventStatus
    from app.events.permissions import require_event_permission
    
    event = EventService.get_event_model(identifier)
    if not event:
        return jsonify({'success': False, 'error': 'Event not found'}), 404
    
    # Check permission
    has_perm, error = require_event_permission(current_user, event, 'reject')
    if not has_perm:
        return jsonify({'success': False, 'error': error}), 403
    
    # Require reason for rejection
    if request.is_json and not request.json.get('reason'):
        return jsonify({'success': False, 'error': 'Reason is required for rejection'}), 400
    
    # Change status
    success, error = EventService.change_event_status(
        identifier, 
        EventStatus.REJECTED, 
        current_user.id,
        reason=request.json.get('reason') if request.is_json else None,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string if request.user_agent else None
    )
    
    if not success:
        return jsonify({'success': False, 'error': error}), 400
    
    return jsonify({'success': True, 'message': 'Event rejected'})

@events_bp.route("/<identifier>/suspend", methods=['POST'])
@login_required
def suspend_event(identifier):
    """Suspend a live event"""
    from app.events.constants import EventStatus
    from app.events.permissions import require_event_permission
    
    event = EventService.get_event_model(identifier)
    if not event:
        return jsonify({'success': False, 'error': 'Event not found'}), 404
    
    # Check permission
    has_perm, error = require_event_permission(current_user, event, 'suspend')
    if not has_perm:
        return jsonify({'success': False, 'error': error}), 403
    
    # Change status
    success, error = EventService.change_event_status(
        identifier, 
        EventStatus.SUSPENDED, 
        current_user.id,
        reason=request.json.get('reason') if request.is_json else None,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string if request.user_agent else None
    )
    
    if not success:
        return jsonify({'success': False, 'error': error}), 400
    
    return jsonify({'success': True, 'message': 'Event suspended'})

@events_bp.route("/<identifier>/reactivate", methods=['POST'])
@login_required
def reactivate_event(identifier):
    """Reactivate a suspended event"""
    from app.events.constants import EventStatus
    from app.events.permissions import require_event_permission
    
    event = EventService.get_event_model(identifier)
    if not event:
        return jsonify({'success': False, 'error': 'Event not found'}), 404
    
    # Check permission
    has_perm, error = require_event_permission(current_user, event, 'reactivate')
    if not has_perm:
        return jsonify({'success': False, 'error': error}), 403
    
    # Change status
    success, error = EventService.change_event_status(
        identifier, 
        EventStatus.PUBLISHED, 
        current_user.id,
        reason=request.json.get('reason') if request.is_json else None,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string if request.user_agent else None
    )
    
    if not success:
        return jsonify({'success': False, 'error': error}), 400
    
    return jsonify({'success': True, 'message': 'Event reactivated'})

@events_bp.route("/<identifier>/pause", methods=['POST'])
@login_required
def pause_event(identifier):
    """Pause a live event"""
    from app.events.constants import EventStatus
    from app.events.permissions import require_event_permission
    
    event = EventService.get_event_model(identifier)
    if not event:
        return jsonify({'success': False, 'error': 'Event not found'}), 404
    
    # Check permission
    has_perm, error = require_event_permission(current_user, event, 'pause')
    if not has_perm:
        return jsonify({'success': False, 'error': error}), 403
    
    # Change status
    success, error = EventService.change_event_status(
        identifier, 
        EventStatus.PAUSED, 
        current_user.id,
        reason=request.json.get('reason') if request.is_json else None,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string if request.user_agent else None
    )
    
    if not success:
        return jsonify({'success': False, 'error': error}), 400
    
    return jsonify({'success': True, 'message': 'Event paused'})

@events_bp.route("/<identifier>/resume", methods=['POST'])
@login_required
def resume_event(identifier):
    """Resume a paused event"""
    from app.events.constants import EventStatus
    from app.events.permissions import require_event_permission
    
    event = EventService.get_event_model(identifier)
    if not event:
        return jsonify({'success': False, 'error': 'Event not found'}), 404
    
    # Check permission
    has_perm, error = require_event_permission(current_user, event, 'resume')
    if not has_perm:
        return jsonify({'success': False, 'error': error}), 403
    
    # Change status
    success, error = EventService.change_event_status(
        identifier, 
        EventStatus.PUBLISHED, 
        current_user.id,
        reason=request.json.get('reason') if request.is_json else None,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string if request.user_agent else None
    )
    
    if not success:
        return jsonify({'success': False, 'error': error}), 400
    
    return jsonify({'success': True, 'message': 'Event resumed'})

@events_bp.route("/<identifier>/delete", methods=['POST'])
@login_required
def delete_event(identifier):
    """Delete an event (soft delete)"""
    from app.events.constants import EventStatus
    from app.events.permissions import require_event_permission
    
    event = EventService.get_event_model(identifier)
    if not event:
        return jsonify({'success': False, 'error': 'Event not found'}), 404
    
    # Check permission
    has_perm, error = require_event_permission(current_user, event, 'delete')
    if not has_perm:
        return jsonify({'success': False, 'error': error}), 403
    
    # Change status
    success, error = EventService.change_event_status(
        identifier, 
        EventStatus.DELETED, 
        current_user.id,
        reason=request.json.get('reason') if request.is_json else None,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string if request.user_agent else None
    )
    
    if not success:
        return jsonify({'success': False, 'error': error}), 400
    
    return jsonify({'success': True, 'message': 'Event deleted'})

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

    # Get dashboard data using the service
    dashboard_data = EventService.get_admin_dashboard_data()

    # Get pending events for approval
    pending_approval = Event.query.filter_by(status=EventStatus.PENDING_APPROVAL, is_deleted=False).order_by(Event.created_at.desc()).all()

    # Get recent events - order by status to show published and suspended first, then by creation date
    recent_events = Event.query.filter_by(is_deleted=False).order_by(Event.status.desc(), Event.created_at.desc()).limit(20).all()

    # Get category distribution
    categories = db.session.query(Event.category, func.count(Event.id)).filter_by(is_deleted=False).group_by(Event.category).all()

    return render_template('events/admin/dashboard.html',
                         total_events=dashboard_data.get('total_events', 0),
                         published_events=dashboard_data.get('published_events', 0),
                         pending_events=dashboard_data.get('pending_events', 0),
                         rejected_events=dashboard_data.get('rejected_events', 0),
                         total_registrations=dashboard_data.get('total_registrations', 0),
                         checked_in_registrations=dashboard_data.get('checked_in_registrations', 0),
                         pending_approval=pending_approval,
                         recent_events=recent_events,
                         categories=categories)


@events_bp.route("/admin/<identifier>/approve", methods=['POST'])
@login_required
def admin_approve(identifier):
    """Admin approve event - only for super_admin and owner"""
    if not is_system_admin(current_user):
        return jsonify({'success': False, 'error': 'Unauthorized - Super Admin access required'}), 403

    event = resolve_event(identifier)
    if not event:
        return jsonify({'success': False, 'error': 'Event not found'}), 404

    previous_status = event.status
    event.status = EventStatus.PUBLISHED
    event.approved_at = datetime.utcnow()
    event.approved_by_id = current_user.id
    # Clear any rejection fields if they exist
    event.rejected_at = None
    event.rejection_reason = None

    db.session.commit()

    # Audit logging
    logger.info(
        f"MODERATION | approve | event={event.slug} | admin={current_user.id} "
        f"| previous_status={previous_status}"
    )

    return jsonify({'success': True, 'message': f'Event {event.name} approved'})


@events_bp.route("/admin/<identifier>/reject", methods=['POST'])
@login_required
def admin_reject(identifier):
    """Admin reject event - only for super_admin and owner"""
    if not is_system_admin(current_user):
        return jsonify({'success': False, 'error': 'Unauthorized - Super Admin access required'}), 403

    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400

    reason = data.get('reason', 'No reason provided')

    event = resolve_event(identifier)
    if not event:
        return jsonify({'success': False, 'error': 'Event not found'}), 404

    previous_status = event.status
    event.status = EventStatus.REJECTED
    event.rejected_at = datetime.utcnow()
    event.rejection_reason = reason
    # Clear any approval fields if they exist
    event.approved_at = None
    event.approved_by_id = None

    db.session.commit()

    # Audit logging
    logger.info(
        f"MODERATION | reject | event={event.slug} | admin={current_user.id} "
        f"| previous_status={previous_status} | reason={reason[:80]}"
    )

    return jsonify({'success': True, 'message': f'Event {event.name} rejected'})

@events_bp.route("/admin/<identifier>/suspend", methods=['POST'])
@login_required
def admin_suspend(identifier):
    """
    Suspend an active event - only for super_admin and owner.
    Hides it from the public portal. Organiser can request reinstatement.
    """
    if not is_system_admin(current_user):
        return jsonify({'success': False, 'error': 'Unauthorized - Super Admin access required'}), 403

    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400

    reason   = data.get('reason', '').strip()
    duration = data.get('duration', '7d')

    if not reason:
        return jsonify({'success': False, 'error': 'Suspension reason is required'}), 400

    event = resolve_event(identifier)
    if not event or event.is_deleted:
        return jsonify({'success': False, 'error': 'Event not found'}), 404

    # Use sanitized status for comparison
    from app.events.services import EventService
    current_status = EventService.sanitize_status(event.status)
    if current_status != EventStatus.PUBLISHED.value:
        return jsonify({'success': False, 'error': f'Cannot suspend an event with status "{current_status}"'}), 400

    previous_status = event.status
    event.status             = EventStatus.SUSPENDED
    event.suspension_reason  = reason
    event.suspension_duration= duration
    event.suspended_at       = datetime.utcnow()
    event.suspended_by_id    = current_user.id

    try:
        db.session.commit()
        logger.info(
            f"MODERATION | suspend | event={event.slug} | admin={current_user.id} "
            f"| previous_status={previous_status} | duration={duration} | reason={reason[:80]}"
        )
        return jsonify({'success': True, 'message': f'Event "{event.name}" suspended ({duration})'})
    except Exception as e:
        db.session.rollback()
        logger.error(f"admin_suspend error: {e}")
        return jsonify({'success': False, 'error': 'Database error'}), 500

@events_bp.route("/admin/<identifier>/deactivate", methods=['POST'])
@login_required
def admin_deactivate(identifier):
    """
    Deactivate an event — disabled but NOT deleted - only for super_admin and owner.
    Organiser data preserved. Reactivation requires support contact.
    """
    if not is_system_admin(current_user):
        return jsonify({'success': False, 'error': 'Unauthorized - Super Admin access required'}), 403

    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400

    reason = data.get('reason', '').strip()
    if not reason:
        return jsonify({'success': False, 'error': 'Deactivation reason is required'}), 400

    event = resolve_event(identifier)
    if not event or event.is_deleted:
        return jsonify({'success': False, 'error': 'Event not found'}), 404

    if event.status in (EventStatus.ARCHIVED, 'deactivated'):
        return jsonify({'success': False, 'error': f'Event is already "{event.status}"'}), 400

    event.status              = 'deactivated'
    event.deactivation_reason = reason
    event.deactivated_at      = datetime.utcnow()
    event.deactivated_by_id   = current_user.id

    try:
        db.session.commit()
        logger.info(
            f"MODERATION | deactivate | event={event.slug} | admin={current_user.id} "
            f"| reason={reason[:80]}"
        )
        return jsonify({'success': True, 'message': f'Event "{event.name}" deactivated'})
    except Exception as e:
        db.session.rollback()
        logger.error(f"admin_deactivate error: {e}")
        return jsonify({'success': False, 'error': 'Database error'}), 500

@events_bp.route("/admin/<identifier>/takedown", methods=['POST'])
@login_required
def admin_takedown(identifier):
    """
    Policy takedown — severe enforcement action - only for super_admin and owner.
    Immediately removes event from public view.
    Logs the action with admin ID for compliance audit.
    Optionally notifies the organiser.
    """
    if not is_system_admin(current_user):
        return jsonify({'success': False, 'error': 'Unauthorized - Super Admin access required'}), 403

    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400

    category        = data.get('category', '').strip()
    reason          = data.get('reason', '').strip()
    notify_organiser= data.get('notify_organiser', True)

    if not category:
        return jsonify({'success': False, 'error': 'Violation category is required'}), 400
    if not reason:
        return jsonify({'success': False, 'error': 'Detailed reason is required'}), 400

    VALID_CATEGORIES = {
        'fraud', 'illegal_activity', 'hate_speech',
        'misinformation', 'spam', 'copyright', 'other'
    }
    if category not in VALID_CATEGORIES:
        return jsonify({'success': False, 'error': 'Invalid violation category'}), 400

    event = resolve_event(identifier)
    if not event or event.is_deleted:
        return jsonify({'success': False, 'error': 'Event not found'}), 404

    # Record takedown details before archiving
    event.takedown_reason    = reason
    event.takedown_category  = category
    event.taken_down_at      = datetime.utcnow()
    event.taken_down_by_id   = current_user.id
    event.status             = EventStatus.ARCHIVED   # removes from public listings
    event.rejection_reason   = f"[POLICY TAKEDOWN – {category.upper()}] {reason}"

    # Soft-delete so it's fully hidden
    event.is_deleted  = True
    event.deleted_at  = datetime.utcnow()
    event.deleted_by_id = current_user.id

    try:
        db.session.commit()

        # Compliance audit log (replace with your audit service if available)
        logger.warning(
            f"COMPLIANCE | takedown | event={event.slug} | admin={current_user.id} "
            f"| category={category} | notify={notify_organiser} | reason={reason[:120]}"
        )

        # TODO: if notify_organiser, send email via your notification service
        # e.g. send_moderation_email(event.organizer, 'takedown', reason, category)

        return jsonify({
            'success': True,
            'message': f'Event "{event.name}" taken down for policy violation ({category})'
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"admin_takedown error: {e}")
        return jsonify({'success': False, 'error': 'Database error'}), 500

@events_bp.route("/admin/<identifier>/restore", methods=['POST'])
@login_required
def admin_restore(identifier):
    """
    Restore a suspended event back to active - only for super_admin and owner.
    Clears suspension fields.
    """
    if not is_system_admin(current_user):
        return jsonify({'success': False, 'error': 'Unauthorized - Super Admin access required'}), 403

    event = resolve_event(identifier)
    if not event or event.is_deleted:
        return jsonify({'success': False, 'error': 'Event not found'}), 404

    if event.status != EventStatus.SUSPENDED:
        return jsonify({'success': False, 'error': f'Event is not suspended (current: {event.status})'}), 400

    event.status              = EventStatus.PUBLISHED
    event.suspension_reason   = None
    event.suspension_duration = None
    event.suspended_at        = None
    event.suspended_by_id     = None

    try:
        db.session.commit()
        logger.info(
            f"MODERATION | restore | event={event.slug} | admin={current_user.id}"
        )
        return jsonify({'success': True, 'message': f'Event "{event.name}" reinstated as active'})
    except Exception as e:
        db.session.rollback()
        logger.error(f"admin_restore error: {e}")
        return jsonify({'success': False, 'error': 'Database error'}), 500


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
        # Use the sanitizer from EventService to handle legacy status values
        from app.events.services import EventService
        sanitized_status = EventService.sanitize_status(status)
        # Filter by the sanitized status
        events = Event.query.filter_by(status=sanitized_status).all()

    return render_template('events/admin/events.html', events=events, current_filter=status)


@events_bp.route("/api/admin/stats")
@login_required
def api_admin_stats():
    """JSON API for admin dashboard stats — used by the super admin panel."""
    if not is_system_admin(current_user):
        return jsonify({"success": False, "error": "Unauthorized"}), 403

    try:
        data = EventService.get_admin_dashboard_data()
        logger.info(f"API admin stats: {data}")
        return jsonify({
            "success": True,
            "total_events": data.get('total_events', 0),
            "published_events": data.get('published_events', 0),
            "pending_events": data.get('pending_events', 0),
            "rejected_events": data.get('rejected_events', 0),
            "total_registrations": data.get('total_registrations', 0),
            "checked_in_registrations": data.get('checked_in_registrations', 0)
        })
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
        pending_events = Event.query.filter_by(status=EventStatus.PENDING_APPROVAL).order_by(Event.created_at.desc()).all()
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


@events_bp.route("/<identifier>/add-ticket-type", methods=['POST'])
@login_required
def add_ticket_type(identifier):
    """Add a new ticket type to an event"""
    event = EventService.get_event(identifier)
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
        ticket_type, error = EventService.add_ticket_type(identifier, data, current_user.id)

        if error:
            return jsonify({'success': False, 'error': error}), 400

        return jsonify({'success': True, 'ticket_type': ticket_type})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@events_bp.route("/<identifier>/assign-service", methods=['POST'])
@login_required
def assign_service_to_attendee_route(identifier):
    """Assign accommodation or transport to an attendee"""
    event = EventService.get_event(identifier)
    if not event:
        return jsonify({'success': False, 'error': 'Event not found'}), 404
    
    # Check if user is organizer or system admin
    if event.get('organizer_id') != current_user.id and not is_system_admin(current_user):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400
    
    attendee_id = data.get('attendee_id')
    booking_type = data.get('booking_type')  # 'accommodation' or 'transport'
    booking_id = data.get('booking_id')
    
    if not attendee_id or not booking_type or not booking_id:
        return jsonify({'success': False, 'error': 'Missing required fields'}), 400
    
    if booking_type not in ['accommodation', 'transport', 'meal']:
        return jsonify({'success': False, 'error': 'Invalid booking type'}), 400
    
    result, error = EventService.assign_service_to_attendee(
        attendee_id=attendee_id,
        identifier=identifier,
        booking_type=booking_type,
        booking_id=booking_id,
        managed_by=current_user.id
    )
    
    if error:
        return jsonify({'success': False, 'error': error}), 400
    
    return jsonify({'success': True, 'assignment': result, 'message': f'{booking_type.title()} assigned successfully'})

@events_bp.route("/<identifier>/assignments")
@login_required
def get_event_assignments(identifier):
    """Get all assignments for an event"""
    event = EventService.get_event(identifier)
    if not event:
        return jsonify({'success': False, 'error': 'Event not found'}), 404
    
    # Check if user is organizer or system admin
    if event.get('organizer_id') != current_user.id and not is_system_admin(current_user):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    assignments = EventService.get_event_assignments(identifier)
    return jsonify({'success': True, 'assignments': assignments})

@events_bp.route("/<identifier>/available-bookings/<booking_type>")
@login_required
def get_available_bookings(identifier, booking_type):
    """Get available bookings (accommodation/transport) for an event's city"""
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
            
            # Get properties in the event city
            properties = Property.query.filter_by(city=city, is_active=True).all()
            property_ids = [p.id for p in properties]
            
            if property_ids:
                # Get available bookings for these properties
                acc_bookings = AccommodationBooking.query.filter(
                    AccommodationBooking.property_id.in_(property_ids),
                    AccommodationBooking.status.in_(['confirmed', 'pending'])
                ).all()
                
                for booking in acc_bookings:
                    bookings.append({
                        'id': booking.id,
                        'type': 'accommodation',
                        'name': f"{booking.property.name} - {booking.room_type or 'Room'}",
                        'guest_name': booking.guest_name or f"Guest #{booking.user_id}",
                        'check_in': booking.check_in.isoformat() if booking.check_in else None,
                        'check_out': booking.check_out.isoformat() if booking.check_out else None,
                    })
        except ImportError:
            logger.warning("Accommodation module not available")
        except Exception as e:
            logger.error(f"Error fetching accommodation bookings: {e}")
    
    elif booking_type == 'transport':
        try:
            from app.transport.models import Booking as TransportBooking
            
            # Get transport bookings (simplified - you may want to filter by route/location)
            transport_bookings = TransportBooking.query.filter(
                TransportBooking.status.in_(['confirmed', 'pending'])
            ).all()
            
            for booking in transport_bookings:
                bookings.append({
                    'id': booking.id,
                    'type': 'transport',
                    'name': f"{booking.vehicle_type or 'Vehicle'} - {booking.pickup_location} to {booking.dropoff_location}",
                    'guest_name': f"User #{booking.user_id}",
                    'pickup_time': booking.pickup_time.isoformat() if booking.pickup_time else None,
                })
        except ImportError:
            logger.warning("Transport module not available")
        except Exception as e:
            logger.error(f"Error fetching transport bookings: {e}")
    
    return jsonify({'success': True, 'bookings': bookings})

@events_bp.route("/<identifier>/staff")
@login_required
def event_staff(identifier):
    """Manage event staff"""
    event = EventService.get_event(identifier)
    if not event:
        return render_template('events/public/not_found.html', event_slug=identifier), 404

    # Check permission
    if event.get('organizer_id') != current_user.id and not is_system_admin(current_user):
        flash('Only event organizers can manage staff', 'danger')
        return redirect(url_for('events.landing', identifier=identifier))

    from app.events.models import EventRole
    event_model = EventService.get_event_model(identifier)
    staff = EventRole.query.filter_by(
        event_id=event_model.id, is_active=True
    ).all() if event_model else []

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

@events_bp.route("/admin/debug/events")
@login_required
def admin_debug_events():
    """Debug endpoint to list all events with their statuses"""
    import os
    if os.getenv('FLASK_ENV', 'production') == 'production' and \
       not os.getenv('ENABLE_DEBUG_ENDPOINTS', '').lower() == 'true':
        return jsonify({"success": False, "error": "Not available"}), 404

    if not is_system_admin(current_user):
        return jsonify({"success": False, "error": "Unauthorized"}), 403

    try:
        events = Event.query.all()
        events_data = []
        for event in events:
            events_data.append({
                'id': event.id,
                'slug': event.slug,
                'name': event.name,
                'status': event.status,
                'is_deleted': event.is_deleted,
                'created_at': event.created_at.isoformat() if event.created_at else None,
                'organizer_id': event.organizer_id
            })

        # Count by status
        status_counts = {}
        for event in events:
            status = event.status
            status_counts[status] = status_counts.get(status, 0) + 1

        return jsonify({
            "success": True,
            "events": events_data,
            "counts": status_counts,
            "total": len(events)
        })
    except Exception as e:
        logger.error(f"admin_debug_events error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@events_bp.route("/admin/debug/counts")
@login_required
def admin_debug_counts():
    """Quick debug endpoint for event counts"""
    import os
    if os.getenv('FLASK_ENV', 'production') == 'production' and \
       not os.getenv('ENABLE_DEBUG_ENDPOINTS', '').lower() == 'true':
        return jsonify({"success": False, "error": "Not available"}), 404

    if not is_system_admin(current_user):
        return jsonify({"success": False, "error": "Unauthorized"}), 403

    try:
        from sqlalchemy import func
        counts = {
            'total': Event.query.filter_by(is_deleted=False).count(),
            'published': Event.query.filter_by(status=EventStatus.PUBLISHED, is_deleted=False).count(),
            'pending': Event.query.filter_by(status=EventStatus.PENDING_APPROVAL, is_deleted=False).count(),
            'rejected': Event.query.filter_by(status=EventStatus.REJECTED, is_deleted=False).count(),
            'suspended': Event.query.filter_by(status=EventStatus.SUSPENDED, is_deleted=False).count(),
            # Handle legacy 'deactivated' status separately
            'deactivated': Event.query.filter(
                Event.status == 'deactivated',
                Event.is_deleted == False
            ).count(),
            'archived': Event.query.filter_by(status=EventStatus.ARCHIVED, is_deleted=False).count(),
        }

        # Registration counts
        from app.events.models import EventRegistration
        reg_counts = {
            'total': EventRegistration.query.count(),
            'checked_in': EventRegistration.query.filter_by(status='checked_in').count(),
        }

        return jsonify({
            "success": True,
            "event_counts": counts,
            "registration_counts": reg_counts
        })
    except Exception as e:
        logger.error(f"admin_debug_counts error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
