# app/events/routes_accommodation.py
"""
Event Accommodation Management Routes
Organizer can assign attendees to accommodation (hotels or community hosts)
"""

from flask import request, jsonify, Response
from flask_login import login_required, current_user
from app.events import events_bp
from app.events.services import EventService
from app.events.models import Event, EventRegistration
from app.events.permissions import can_cancel_assignment, can_view_coordination
from app.events.services.guest_coordination_service import (
    CoordinationError,
    GuestCoordinationService,
)
from app.accommodation.models.booking import AccommodationBooking
from app.extensions import db
import csv
import io


@events_bp.route("/<slug>/accommodation")
@login_required
def accommodation_manage(slug):
    """Main accommodation management page for event organizers"""
    event = EventService.get_event_model(slug)
    if not event:
        flash('Event not found', 'danger')
        return redirect(url_for('events.my_events'))
    
    # Check permission: organizer or admin
    allowed, _ = can_view_coordination(current_user, event)
    if not allowed:
        flash('You do not have permission to manage this event', 'danger')
        return redirect(url_for('events.landing', identifier=slug))
    
    return render_template('events/organizer/accommodation_manage.html', event=event)


@events_bp.route("/api/<slug>/accommodation/attendees")
@login_required
def api_accommodation_attendees(slug):
    """Get attendees who need accommodation assignment"""
    event = EventService.get_event_model(slug)
    if not event:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    try:
        result = GuestCoordinationService.dashboard(
            event,
            current_user,
            page=request.args.get('page', 1, type=int),
            per_page=min(request.args.get('per_page', 100, type=int), 100),
            search=request.args.get('search'),
        )
        return jsonify({'success': True, 'attendees': result['items'], **result})
    except CoordinationError as error:
        return jsonify({'success': False, 'code': error.code, 'error': error.message}), 403


@events_bp.route("/api/<slug>/accommodation/inventory")
@login_required
def api_accommodation_inventory(slug):
    """Compatibility inventory view using public booking/property references."""
    event = EventService.get_event_model(slug)
    allowed, message = can_view_coordination(current_user, event) if event else (False, 'Event not found')
    if not allowed:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403

    hotel_bookings = AccommodationBooking.query.filter(
        AccommodationBooking.event_id == event.id,
        AccommodationBooking.status.in_(['held', 'confirmed', 'pending', 'pending_approval']),
        AccommodationBooking.is_deleted.is_(False),
    ).all()

    assigned = {
        assignment.accommodation_booking_id
        for assignment in EventAssignment.query.filter_by(
            event_id=event.id, is_deleted=False
        ).all()
        if assignment.accommodation_booking_id
    }
    hotels = [{
        'booking_ref': booking.booking_reference,
        'type': 'hotel',
        'property_ref': getattr(booking.accommodation_property, 'public_id', None),
        'property_name': booking.accommodation_property.title if booking.accommodation_property else 'Unknown Property',
        'check_in': booking.check_in.isoformat() if booking.check_in else None,
        'check_out': booking.check_out.isoformat() if booking.check_out else None,
        'remaining_capacity': booking.num_guests,
        'is_assigned': booking.id in assigned,
    } for booking in hotel_bookings]
    return jsonify({'success': True, 'inventory': {'hotels': hotels, 'community_hosts': []}})


@events_bp.route("/api/<slug>/accommodation/assign", methods=['POST'])
@login_required
def api_accommodation_assign(slug):
    """Compatibility wrapper for the canonical public-reference assignment."""
    event = EventService.get_event_model(slug)
    allowed, message = can_view_coordination(current_user, event) if event else (False, 'Event not found')
    if not allowed:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403

    data = request.get_json(silent=True) or {}
    registration_ref = data.get('registration_ref')
    booking_ref = data.get('booking_ref') or data.get('inventory_ref') or data.get('inventory_id')
    if not registration_ref or not booking_ref or data.get('inventory_type', 'hotel') != 'hotel':
        return jsonify({
            'success': False,
            'code': 'INVALID_EVENT_RESOURCE',
            'error': 'A confirmed registration_ref and hotel booking_ref are required',
        }), 400
    try:
        assignment = GuestCoordinationService.assign_accommodation(
            event, current_user, registration_ref, booking_ref
        )
        return jsonify({
            'success': True,
            'assignment_ref': GuestCoordinationService._assignment_ref(event, assignment.registration),
            'registration_ref': registration_ref,
            'status': assignment.status,
        })
    except CoordinationError as error:
        db.session.rollback()
        return jsonify({'success': False, 'code': error.code, 'error': error.message}), 400


@events_bp.route("/api/<slug>/accommodation/unassign", methods=['POST'])
@login_required
def api_accommodation_unassign(slug):
    """Compatibility wrapper for capability-scoped cancellation."""
    event = EventService.get_event_model(slug)
    allowed, message = can_cancel_assignment(current_user, event) if event else (False, 'Event not found')
    if not allowed:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403

    data = request.get_json(silent=True) or {}
    registration_ref = data.get('registration_ref')
    if not registration_ref and data.get('attendee_id'):
        legacy_id = str(data['attendee_id'])
        if legacy_id.isdigit():
            registration = EventRegistration.query.filter(
                EventRegistration.event_id == event.id,
                EventRegistration.is_deleted.is_(False),
                (EventRegistration.user_id == int(legacy_id)) |
                (EventRegistration.attendee_user_id == int(legacy_id)),
            ).first()
            registration_ref = registration.registration_ref if registration else None
    if not registration_ref:
        return jsonify({'success': False, 'code': 'INVALID_EVENT_REGISTRATION',
                        'error': 'registration_ref is required'}), 400
    try:
        assignment = GuestCoordinationService.cancel(
            event, current_user, registration_ref, 'accommodation'
        )
        return jsonify({'success': True, 'registration_ref': registration_ref, 'status': assignment.status})
    except CoordinationError as error:
        db.session.rollback()
        return jsonify({'success': False, 'code': error.code, 'error': error.message}), 400


@events_bp.route("/api/<slug>/accommodation/bulk-assign", methods=['POST'])
@login_required
def api_accommodation_bulk_assign(slug):
    """Compatibility CSV adapter for canonical bulk coordination."""
    event = EventService.get_event_model(slug)
    allowed, message = can_view_coordination(current_user, event) if event else (False, 'Event not found')
    if not allowed:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403

    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'}), 400
    file = request.files['file']
    if not file.filename.endswith('.csv'):
        return jsonify({'success': False, 'error': 'Please upload a CSV file'}), 400

    try:
        stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
        csv_input = csv.reader(stream)
        next(csv_input, None)
        requests = []
        for row_num, row in enumerate(csv_input, start=2):
            if len(row) < 2 or not row[0].strip() or not row[1].strip():
                continue
            if len(requests) >= 100:
                break
            registration = EventRegistration.query.filter_by(
                event_id=event.id, email=row[0].strip(), status='confirmed', is_deleted=False
            ).first()
            if not registration:
                continue
            if (len(row) > 2 and row[2].strip().lower() != 'hotel'):
                continue
            requests.append({'registration_ref': registration.registration_ref, 'booking_ref': row[1].strip()})

        result = GuestCoordinationService.bulk_assign(event, current_user, 'accommodation', requests)
        return jsonify(result), 200 if result['success'] else 207
    except CoordinationError as error:
        db.session.rollback()
        return jsonify({'success': False, 'code': error.code, 'error': error.message}), 400


@events_bp.route("/api/<slug>/accommodation/bulk-assign-template")
@login_required
def api_accommodation_bulk_assign_template(slug):
    """Download CSV template for bulk assign"""
    event = EventService.get_event_model(slug)
    if not event:
        return jsonify({'success': False, 'error': 'Event not found'}), 404
    allowed, message = can_view_coordination(current_user, event)
    if not allowed:
        return jsonify({'success': False, 'error': message}), 403
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['attendee_email', 'booking_ref', 'inventory_type'])
    writer.writerow(['guest@example.com', 'ACC-BOOKING-REF', 'hotel'])
    
    output.seek(0)
    
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename=bulk_assign_template_{slug}.csv"}
    )

