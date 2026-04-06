# app/events/routes.py
"""
Event routes - Unified entry points for all user roles
"""
from flask import render_template, request, jsonify, redirect, url_for, flash, session
from flask_login import login_required, current_user
from app.events import events_bp
from app.events.services import EventService, SoldOutException
from app.events.models import Event, EventRegistration, TicketType
from app.accommodation.services.search_service import search_properties
from app.accommodation.models.booking import BookingContextType
from app.extensions import db
from app.events.tasks import process_event_registration
from sqlalchemy import func
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def is_system_admin(user):
    """Check if user is a system admin (super admin)"""
    if not user or not user.is_authenticated:
        return False
    return user.is_super_admin() if hasattr(user, 'is_super_admin') else False


# ============================================================
# PUBLIC ROUTES
# ============================================================

@events_bp.route("/", endpoint="list")
def event_list():
    """List all events"""
    events = EventService.get_all_events(status='active')
    return render_template('events/public/list.html', events=events)


@events_bp.route("/<event_slug>", endpoint="landing")
def event_landing(event_slug):
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


@events_bp.route("/api/<event_slug>/properties", endpoint="api_properties")
def api_event_properties(event_slug):
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

@events_bp.route("/hub", endpoint="events_hub")
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


@events_bp.route("/my-registrations", endpoint="my_registrations")
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

    return render_template('events/attendee/my_registrations.html', 
                           registrations=data['upcoming_registrations'] + data['past_registrations'],
                           wallet_balance=wallet_balance)


@events_bp.route("/organizer/dashboard/<event_slug>", endpoint="organizer_dashboard")
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


@events_bp.route("/service-provider/dashboard", endpoint="service_provider_dashboard")
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

@events_bp.route("/my-events", endpoint="my_events")
@login_required
def my_events():
    """Organizer List - User's managed events page"""
    events = EventService.get_events_by_organizer(current_user.id)
    return render_template('events/organizer/my_events.html', events=events)


@events_bp.route("/create", methods=['GET', 'POST'], endpoint="create_event")
@login_required
def create_event():
    """Create event page"""
    if request.method == 'GET':
        return render_template('events/organizer/create.html')

    try:
        data = request.get_json()
        event, error = EventService.create_event(data, current_user.id)
        if error:
            return jsonify({'success': False, 'error': error}), 400

        return jsonify({
            'success': True,
            'redirect': url_for('events.my_events'),
            'message': 'Event created successfully!'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@events_bp.route("/<event_slug>/edit", methods=['GET', 'POST'], endpoint="edit_event")
@login_required
def edit_event(event_slug):
    """Edit event page"""
    event = EventService.get_event(event_slug)
    if not event or event.get('organizer_id') != current_user.id:
        flash('Unauthorized', 'danger')
        return redirect(url_for('events.my_events'))

    if request.method == 'GET':
        return render_template('events/organizer/edit.html', event=event)

    try:
        data = request.get_json()
        success, error = EventService.update_event(event_slug, data, current_user.id)
        if not success:
            return jsonify({'success': False, 'error': error}), 400

        return jsonify({'success': True, 'redirect': url_for('events.my_events')})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@events_bp.route("/<event_slug>/delete", methods=['POST'], endpoint="delete_event")
@login_required
def delete_event(event_slug):
    """Delete event"""
    success, error = EventService.delete_event(event_slug, current_user.id)

    if success:
        flash('Event deleted successfully', 'success')
    else:
        flash(error or 'Unable to delete event', 'danger')

    return redirect(url_for('events.my_events'))


@events_bp.route("/<event_slug>/scanner", endpoint="scanner")
@login_required
def event_scanner(event_slug):
    """Scanner interface for event staff"""
    event = EventService.get_event(event_slug)
    if not event:
        return render_template('events/public/not_found.html', event_slug=event_slug), 404

    from app.events.permissions import can_check_in_attendees
    if not can_check_in_attendees(current_user, event):
        flash('Unauthorized', 'danger')
        return redirect(url_for('events.landing', event_slug=event_slug))

    return render_template('events/organizer/scanner.html', event=event)


@events_bp.route("/<event_slug>/analytics", endpoint="event_analytics")
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
    demographics = {'Uganda': 45, 'Kenya': 12, 'Tanzania': 8, 'Other': 15} # Mock data

    return render_template('events/organizer/analytics.html', 
                           event=event, 
                           stats=stats,
                           daily_trend=daily_trend,
                           checkin_trend=checkin_trend,
                           revenue_by_ticket=revenue_by_ticket,
                           demographics=demographics)


@events_bp.route("/<event_slug>/export", endpoint="export_attendees")
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

@events_bp.route("/<event_slug>/register", methods=['GET', 'POST'], endpoint="register")
@login_required
def register_for_event(event_slug):
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

    except SoldOutException as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Registration route error: {e}")
        return jsonify({'success': False, 'error': "An unexpected error occurred."}), 500


@events_bp.route("/registration-confirmation/<reg_ref>", endpoint="registration_confirmation")
@login_required
def registration_confirmation(reg_ref):
    """Show registration confirmation with QR code"""
    # Get from session or database
    reg_data = session.get('last_registration')

    if not reg_data or reg_data['registration']['registration_ref'] != reg_ref:
        # Fetch from database
        from app.events.models import EventRegistration
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


@events_bp.route("/event/<event_slug>/attendees", endpoint="event_attendees")
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


@events_bp.route("/api/checkin", methods=['POST'], endpoint="api_checkin")
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

@events_bp.route("/admin/dashboard", endpoint="admin_dashboard")
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


@events_bp.route("/admin/<event_slug>/approve", methods=['POST'], endpoint="admin_approve")
@login_required
def admin_approve(event_slug):
    """Admin approve event"""
    if not is_system_admin(current_user):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403

    success, error = EventService.approve_event(event_slug, current_user.id)
    if success:
        flash('Event approved', 'success')
    return redirect(url_for('events.admin_dashboard'))


@events_bp.route("/admin/<event_slug>/reject", methods=['POST'], endpoint="admin_reject")
@login_required
def admin_reject(event_slug):
    """Admin reject event"""
    if not is_system_admin(current_user):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403

    reason = request.get_json().get('reason', 'No reason provided')
    success, error = EventService.reject_event(event_slug, current_user.id, reason)
    return jsonify({'success': success})

@events_bp.route("/admin/events", endpoint="admin_events")
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


@events_bp.route("/<event_slug>/staff", endpoint="event_staff")
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
