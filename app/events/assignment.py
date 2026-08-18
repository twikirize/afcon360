#app/events/routes/assignment.py
"""Event Host coordination routes.

The coordination service links attendees to already-reserved owning-domain
resources; it does not create a parallel accommodation or transport system.
"""

from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, abort
from flask_login import login_required, current_user
from sqlalchemy import and_, func, or_
import csv
from io import StringIO

from app.extensions import db
from app.events.models import Event, EventRegistration, EventAssignment
from app.events.permissions import can_view_coordination
from app.events.services.guest_coordination_service import (
    CoordinationError,
    GuestCoordinationService,
)
from app.accommodation.models.property import Property, AccommodationPropertyStatus
from app.transport.models import Booking, BookingStatus, DriverProfile, Vehicle

assignment_bp = Blueprint('event_assignment', __name__)


def _event_for_ref(event_ref):
    """Resolve public event references; numeric IDs remain legacy-only input."""
    query = Event.query.filter(Event.is_deleted.is_(False))
    event = query.filter(
        (Event.public_id == str(event_ref))
        | (Event.slug == str(event_ref))
    ).first()
    if event is None and str(event_ref).isdigit():
        event = query.filter_by(id=int(event_ref)).first()
    return event or abort(404)


# ============================================================================
# DASHBOARD - Main Assignment Interface
# ============================================================================

@assignment_bp.route('/<event_ref>/assignment', methods=['GET'])
@login_required
def assignment_dashboard(event_ref):
    """Main dashboard for event assignment management"""
    event = _event_for_ref(event_ref)
    event_id = event.id

    allowed, _ = can_view_coordination(current_user, event)
    if not allowed:
        flash("You don't have permission to manage this event.", "danger")
        return redirect(url_for('events.list'))

    # Get event statistics
    total_attendees = EventRegistration.query.filter_by(
        event_id=event_id, is_deleted=False
    ).count()

    # Count assignments with bookings
    accommodation_assigned = db.session.query(func.count()).filter(
        and_(
            EventAssignment.event_id == event_id,
            EventAssignment.accommodation_booking_id != None,
            EventAssignment.is_deleted.is_(False),
        )
    ).scalar() or 0

    transport_assigned = db.session.query(func.count()).filter(
        and_(
            EventAssignment.event_id == event_id,
            EventAssignment.transport_booking_id != None,
            EventAssignment.is_deleted.is_(False),
        )
    ).scalar() or 0

    # Get availability stats for event city
    available_properties = Property.query.filter_by(
        city=event.city,
        status=AccommodationPropertyStatus.ACTIVE,
        is_deleted=False
    ).count()

    stats = {
        'total_attendees': total_attendees,
        'assigned_accommodation': accommodation_assigned,
        'pending_accommodation': total_attendees - accommodation_assigned,
        'assigned_transport': transport_assigned,
        'pending_transport': total_attendees - transport_assigned,
        'available_properties': available_properties,
        'accommodation_coverage': round((accommodation_assigned / total_attendees * 100),
                                        1) if total_attendees > 0 else 0,
        'transport_coverage': round((transport_assigned / total_attendees * 100), 1) if total_attendees > 0 else 0,
    }

    # Get recent assignments
    recent_assignments = EventAssignment.query.filter_by(
        event_id=event_id, is_deleted=False
    ).order_by(
        EventAssignment.assigned_at.desc()
    ).limit(10).all()

    return render_template(
        'events/admin/assignment_dashboard.html',
        event=event,
        stats=stats,
        recent_assignments=recent_assignments
    )


# ============================================================================
# ATTENDEES - List all registered attendees
# ============================================================================

@assignment_bp.route('/<event_ref>/attendees', methods=['GET'])
@login_required
def list_attendees(event_ref):
    """List all registered attendees for an event"""
    event = _event_for_ref(event_ref)
    event_id = event.id
    allowed, message = can_view_coordination(current_user, event)
    if not allowed:
        return jsonify({'success': False, 'code': 'EVENT_COORDINATION_FORBIDDEN', 'error': message}), 403

    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    filter_type = request.args.get('filter', 'all')

    # Query attendees
    query = EventRegistration.query.filter_by(event_id=event_id, is_deleted=False)

    if search:
        query = query.filter(
            (EventRegistration.full_name.ilike(f'%{search}%')) |
            (EventRegistration.email.ilike(f'%{search}%'))
        )

    # Get assignments for filtering
    assignments = db.session.query(EventAssignment).filter_by(
        event_id=event_id, is_deleted=False
    ).all()
    user_registration_ids = {
        identity_id: registration_id
        for registration_id, user_id, attendee_user_id in EventRegistration.query.filter_by(
            event_id=event_id, is_deleted=False
        ).with_entities(
            EventRegistration.id,
            EventRegistration.user_id,
            EventRegistration.attendee_user_id,
        ).all()
        for identity_id in (user_id, attendee_user_id)
        if identity_id is not None
    }
    assignment_map = {a.registration_id: a for a in assignments if a.registration_id}
    accommodation_ids = set()
    transport_ids = set()
    for assignment in assignments:
        registration_id = user_registration_ids.get(assignment.attendee_id)
        if registration_id is not None:
            assignment_map.setdefault(registration_id, assignment)
        registration_id = assignment.registration_id or registration_id
        if registration_id and assignment.accommodation_booking_id:
            accommodation_ids.add(registration_id)
        if registration_id and assignment.transport_booking_id:
            transport_ids.add(registration_id)
    if filter_type == 'accommodation':
        query = query.filter(~EventRegistration.id.in_(accommodation_ids)) if accommodation_ids else query
    elif filter_type == 'transport':
        query = query.filter(~EventRegistration.id.in_(transport_ids)) if transport_ids else query
    elif filter_type == 'both':
        if accommodation_ids:
            query = query.filter(~EventRegistration.id.in_(accommodation_ids))
        if transport_ids:
            query = query.filter(~EventRegistration.id.in_(transport_ids))
    elif filter_type == 'assigned':
        query = query.filter(EventRegistration.id.in_(accommodation_ids & transport_ids))

    attendees = query.paginate(page=page, per_page=20, error_out=False)

    return render_template(
        'events/admin/attendees_list.html',
        event=event,
        attendees=attendees,
        assignment_map=assignment_map,
        search=search,
        filter_type=filter_type
    )


@assignment_bp.route('/<event_ref>/coordination', methods=['GET'])
@login_required
def coordination_dashboard(event_ref):
    event = _event_for_ref(event_ref)
    try:
        result = GuestCoordinationService.dashboard(
            event,
            current_user,
            search=request.args.get('search'),
            page=request.args.get('page', 1, type=int),
        )
    except CoordinationError as error:
        return jsonify({'success': False, 'code': error.code, 'error': error.message}), 403
    return jsonify({'success': True, **result})


# ============================================================================
# ACCOMMODATION - Assign accommodation using EXISTING BookingService
# ============================================================================

@assignment_bp.route('/<event_ref>/accommodation/assign', methods=['POST'])
@login_required
def assign_accommodation(event_ref):
    """Link a confirmed attendee to an existing event accommodation booking."""
    event = _event_for_ref(event_ref)
    event_id = event.id
    data = request.get_json(silent=True) or {}

    try:
        assignment = GuestCoordinationService.assign_accommodation(
            event,
            current_user,
            str(data.get('registration_ref') or data.get('attendee_ref') or ''),
            data.get('booking_ref') or data.get('booking_id'),
        )
        return jsonify({
            'success': True,
            'assignment_ref': GuestCoordinationService._assignment_ref(
                event, assignment.registration
            ),
            'registration_ref': assignment.registration.registration_ref,
            'status': assignment.status,
        })
    except CoordinationError as error:
        db.session.rollback()
        return jsonify({'success': False, 'code': error.code, 'error': error.message}), 400

# ============================================================================
# TRANSPORT - Assign transport using EXISTING Booking model
# ============================================================================

@assignment_bp.route('/<event_ref>/transport/assign', methods=['POST'])
@login_required
def assign_transport(event_ref):
    """Link a confirmed attendee to an existing eligible transport booking."""
    event = _event_for_ref(event_ref)
    event_id = event.id
    data = request.get_json(silent=True) or {}

    try:
        assignment = GuestCoordinationService.assign_transport(
            event,
            current_user,
            str(data.get('registration_ref') or data.get('attendee_ref') or ''),
            data.get('booking_ref') or data.get('booking_id'),
        )
        return jsonify({
            'success': True,
            'assignment_ref': GuestCoordinationService._assignment_ref(
                event, assignment.registration
            ),
            'registration_ref': assignment.registration.registration_ref,
            'status': assignment.status,
        })
    except CoordinationError as error:
        db.session.rollback()
        return jsonify({'success': False, 'code': error.code, 'error': error.message}), 400


@assignment_bp.route('/<event_ref>/coordination/bulk/<capability>', methods=['POST'])
@login_required
def bulk_coordination(event_ref, capability):
    """Validate each attendee independently and report every result."""
    event = _event_for_ref(event_ref)
    data = request.get_json(silent=True) or {}
    try:
        result = GuestCoordinationService.bulk_assign(
            event,
            current_user,
            capability,
            data.get('assignments', []),
        )
        return jsonify(result), 200 if result['success'] else 207
    except CoordinationError as error:
        db.session.rollback()
        return jsonify({'success': False, 'code': error.code, 'error': error.message}), 400


@assignment_bp.route('/<event_ref>/coordination/<registration_ref>/<capability>', methods=['DELETE'])
@login_required
def cancel_coordination(event_ref, registration_ref, capability):
    """Cancel one capability without deleting the attendee's other assignment."""
    event = _event_for_ref(event_ref)
    try:
        assignment = GuestCoordinationService.cancel(
            event, current_user, registration_ref, capability
        )
        return jsonify({
            'success': True,
            'registration_ref': registration_ref,
            'capability': capability,
            'status': assignment.status,
        })
    except CoordinationError as error:
        db.session.rollback()
        return jsonify({'success': False, 'code': error.code, 'error': error.message}), 400

# ============================================================================
# AVAILABILITY CHECKS - Query what's available
# ============================================================================

@assignment_bp.route('/<event_ref>/available-properties', methods=['GET'])
@login_required
def check_available_properties(event_ref):
    """List event-reserved accommodation bookings, not generic inventory."""
    event = _event_for_ref(event_ref)
    allowed, message = can_view_coordination(current_user, event)
    if not allowed:
        return jsonify({'success': False, 'code': 'EVENT_COORDINATION_FORBIDDEN', 'error': message}), 403

    from app.accommodation.models.booking import AccommodationBooking

    bookings = AccommodationBooking.query.filter(
        or_(
            AccommodationBooking.event_id == event.id,
            AccommodationBooking.context_id.in_([str(event.public_id), str(event.slug)]),
        ),
        AccommodationBooking.status.in_(['held', 'confirmed', 'pending', 'pending_approval']),
        AccommodationBooking.is_deleted.is_(False),
    ).limit(100).all()
    assigned_counts = dict(
        db.session.query(
            EventAssignment.accommodation_booking_id, func.count(EventAssignment.id)
        ).filter(
            EventAssignment.event_id == event.id,
            EventAssignment.accommodation_booking_id.is_not(None),
            EventAssignment.is_deleted.is_(False),
        ).group_by(EventAssignment.accommodation_booking_id).all()
    )
    available = []
    for booking in bookings:
        used = assigned_counts.get(booking.id, 0)
        capacity = max(1, int(booking.num_guests or 1))
        if used < capacity:
            available.append({
                'booking_ref': booking.booking_reference,
                'title': getattr(getattr(booking, 'accommodation_property', None), 'title', None) or 'Reserved accommodation',
                'room_type': getattr(getattr(booking, 'room_type', None), 'name', None),
                'check_in': booking.check_in.isoformat() if booking.check_in else None,
                'check_out': booking.check_out.isoformat() if booking.check_out else None,
                'remaining_capacity': capacity - used,
            })

    return jsonify({
        'success': True,
        'properties': available,
        'count': len(available)
    })


@assignment_bp.route('/<event_ref>/available-drivers', methods=['GET'])
@login_required
def check_available_drivers(event_ref):
    """List event-reserved transport bookings with their owning resources."""
    event = _event_for_ref(event_ref)
    allowed, message = can_view_coordination(current_user, event)
    if not allowed:
        return jsonify({'success': False, 'code': 'EVENT_COORDINATION_FORBIDDEN', 'error': message}), 403

    bookings = Booking.query.filter(
        Booking.event_id == event.id,
        Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.ASSIGNED, 'confirmed', 'assigned']),
        Booking.is_deleted.is_(False),
    ).limit(100).all()

    eligible = []
    for booking in bookings:
        try:
            GuestCoordinationService._resolve_transport_booking(
                event, booking.booking_reference
            )
        except CoordinationError:
            continue
        driver = db.session.get(DriverProfile, booking.assigned_driver_id)
        vehicle = db.session.get(Vehicle, booking.assigned_vehicle_id)
        eligible.append((booking, driver, vehicle))

    return jsonify({
        'success': True,
        'available_drivers': len(eligible),
        'drivers': [
            {
                'booking_ref': booking.booking_reference,
                'driver_ref': getattr(driver, 'public_id', None),
                'vehicle_ref': getattr(vehicle, 'public_id', None),
                'vehicle': getattr(vehicle, 'registration_number', 'Unknown'),
                'pickup_time': booking.pickup_time.isoformat() if booking.pickup_time else None,
            }
            for booking, driver, vehicle in eligible
        ]
    })


# ============================================================================
# EXPORT - Download assignments
# ============================================================================

@assignment_bp.route('/<event_ref>/export/assignments', methods=['GET'])
@login_required
def export_assignments(event_ref):
    """Export attendee assignments as CSV"""
    from flask import make_response

    event = _event_for_ref(event_ref)
    event_id = event.id
    allowed, message = can_view_coordination(current_user, event)
    if not allowed:
        return jsonify({'success': False, 'code': 'EVENT_COORDINATION_FORBIDDEN', 'error': message}), 403
    registrations = EventRegistration.query.filter_by(
        event_id=event_id, is_deleted=False
    ).all()
    assignments = EventAssignment.query.filter_by(
        event_id=event_id, is_deleted=False
    ).all()
    assignments_map = {a.registration_id: a for a in assignments if a.registration_id}
    user_registration_ids = {
        identity_id: registration.id
        for registration in registrations
        for identity_id in (registration.user_id, getattr(registration, 'attendee_user_id', None))
        if identity_id is not None
    }
    for assignment in assignments:
        registration_id = user_registration_ids.get(assignment.attendee_id)
        if registration_id is not None:
            assignments_map.setdefault(registration_id, assignment)

    # Create CSV
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'Registration ID', 'Name', 'Email', 'Phone',
        'Accommodation Booked', 'Accommodation Ref',
        'Transport Booked', 'Transport Ref',
        'Registered At'
    ])

    for reg in registrations:
        assignment = assignments_map.get(reg.id)

        accom_booking_id = assignment.accommodation_booking_id if assignment else None
        transport_booking_id = assignment.transport_booking_id if assignment else None

        # Get booking references if they exist
        accom_ref = ''
        if accom_booking_id:
            from app.accommodation.models.booking import AccommodationBooking
            accom = db.session.get(AccommodationBooking, accom_booking_id)
            accom_ref = accom.booking_reference if accom else ''

        transport_ref = ''
        if transport_booking_id:
            transport = db.session.get(Booking, transport_booking_id)
            transport_ref = transport.booking_reference if transport else ''

        writer.writerow([
            reg.registration_ref,
            reg.full_name,
            reg.email,
            reg.phone or '',
            'Yes' if accom_booking_id else 'No',
            accom_ref,
            'Yes' if transport_booking_id else 'No',
            transport_ref,
            reg.created_at.isoformat() if reg.created_at else ''
        ])

    response = make_response(output.getvalue())
    response.headers['Content-Disposition'] = f'attachment; filename=event_{event.public_id}_assignments.csv'
    response.headers['Content-Type'] = 'text/csv'
    return response


