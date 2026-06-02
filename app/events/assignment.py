#app/events/routes/assignment.py
"""Event Assignment Routes - Accommodation & Transport Management
Integrates with EXISTING infrastructure:
- EventAssignment model (accommodation_booking_id, transport_booking_id)
- AccommodationBookingService.create_booking() & confirm_booking()
- ProviderService.get_available_drivers()
- AvailabilityService.is_range_available()
"""

from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, current_app
from flask_login import login_required, current_user
from sqlalchemy import and_, func
from datetime import datetime, timezone
from decimal import Decimal
import csv
from io import StringIO

from app.extensions import db
from app.auth.decorators import require_role
from app.events.models import Event, EventRegistration, EventAssignment
from app.accommodation.services.booking_service import BookingService
from app.accommodation.services.availability_service import AvailabilityService
from app.accommodation.models.property import Property, AccommodationPropertyStatus
from app.accommodation.models.booking import AccommodationBookingStatus
from app.transport.models import Booking, BookingStatus, ServiceType, ProviderType
from app.transport.services.provider_service import get_provider_service
from app.identity.models.user import User

assignment_bp = Blueprint('event_assignment', __name__, url_prefix='/events')


# ============================================================================
# DASHBOARD - Main Assignment Interface
# ============================================================================

@assignment_bp.route('/<int:event_id>/assignment', methods=['GET'])
@login_required
@require_role('event_manager', 'admin', 'super_admin', 'owner')
def assignment_dashboard(event_id):
    """Main dashboard for event assignment management"""
    event = Event.query.get_or_404(event_id)

    # Permission check
    if event.organizer_id != current_user.id and not current_user.has_global_role('admin'):
        flash("You don't have permission to manage this event.", "danger")
        return redirect(url_for('events.list'))

    # Get event statistics
    total_attendees = EventRegistration.query.filter_by(event_id=event_id).count()

    # Count assignments with bookings
    accommodation_assigned = db.session.query(func.count()).filter(
        and_(
            EventAssignment.event_id == event_id,
            EventAssignment.accommodation_booking_id != None
        )
    ).scalar() or 0

    transport_assigned = db.session.query(func.count()).filter(
        and_(
            EventAssignment.event_id == event_id,
            EventAssignment.transport_booking_id != None
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
        event_id=event_id
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

@assignment_bp.route('/<int:event_id>/attendees', methods=['GET'])
@login_required
@require_role('event_manager', 'admin', 'super_admin', 'owner')
def list_attendees(event_id):
    """List all registered attendees for an event"""
    event = Event.query.get_or_404(event_id)

    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    filter_type = request.args.get('filter', 'all')

    # Query attendees
    query = EventRegistration.query.filter_by(event_id=event_id)

    if search:
        query = query.filter(
            (EventRegistration.full_name.ilike(f'%{search}%')) |
            (EventRegistration.email.ilike(f'%{search}%'))
        )

    # Get assignments for filtering
    assignments = db.session.query(EventAssignment).filter_by(event_id=event_id).all()
    assignment_map = {a.registration_id: a for a in assignments if a.registration_id}

    attendees = query.paginate(page=page, per_page=20, error_out=False)

    return render_template(
        'events/admin/attendees_list.html',
        event=event,
        attendees=attendees,
        assignment_map=assignment_map,
        search=search,
        filter_type=filter_type
    )


# ============================================================================
# ACCOMMODATION - Assign accommodation using EXISTING BookingService
# ============================================================================

@assignment_bp.route('/<int:event_id>/accommodation/assign', methods=['POST'])
@login_required
@require_role('event_manager', 'admin', 'super_admin', 'owner')
def assign_accommodation(event_id):
    """Assign accommodation to an attendee
    Uses: AccommodationBookingService.create_booking() + confirm_booking()
    Stores: EventAssignment.accommodation_booking_id
    """
    event = Event.query.get_or_404(event_id)
    data = request.get_json()

    attendee_id = data.get('attendee_id')
    property_id = data.get('property_id')
    check_in = data.get('check_in')  # ISO format
    check_out = data.get('check_out')

    # Get registration
    registration = EventRegistration.query.filter_by(
        id=attendee_id, event_id=event_id
    ).first_or_404()

    try:
        # 1. CREATE booking using EXISTING service
        booking, error = BookingService.create_booking(
            guest_user_id=registration.user_id,
            property_id=property_id,
            check_in_date=datetime.fromisoformat(check_in).date(),
            check_out_date=datetime.fromisoformat(check_out).date(),
            context_type='EVENT',  # EXISTING feature
            context_id=str(event_id)
        )

        if error:
            return jsonify({'success': False, 'error': error}), 400

        # 2. AUTO-CONFIRM booking (event organizers pre-approve)
        success, confirm_error = BookingService.confirm_booking(booking.id)
        if not success:
            return jsonify({'success': False, 'error': confirm_error}), 400

        # 3. LINK to EventAssignment (EXISTING model)
        assignment = EventAssignment.query.filter_by(
            event_id=event_id,
            registration_id=registration.id
        ).first()

        if not assignment:
            assignment = EventAssignment(
                event_id=event_id,
                attendee_id=registration.user_id,
                registration_id=registration.id
            )
            db.session.add(assignment)

        assignment.accommodation_booking_id = booking.id
        assignment.assigned_by_id = current_user.id
        assignment.assigned_at = datetime.now(timezone.utc)

        db.session.commit()

        return jsonify({
            'success': True,
            'booking_reference': booking.booking_reference,
            'booking_id': booking.id,
            'message': 'Accommodation assigned and confirmed'
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Accommodation assignment error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# TRANSPORT - Assign transport using EXISTING Booking model
# ============================================================================

@assignment_bp.route('/<int:event_id>/transport/assign', methods=['POST'])
@login_required
@require_role('event_manager', 'admin', 'super_admin', 'owner')
def assign_transport(event_id):
    """Assign transport to an attendee
    Uses: ProviderService.get_available_drivers() + Booking model
    Stores: EventAssignment.transport_booking_id
    """
    event = Event.query.get_or_404(event_id)
    data = request.get_json()

    attendee_id = data.get('attendee_id')
    pickup_time_str = data.get('pickup_time')  # ISO format

    # Get registration
    registration = EventRegistration.query.filter_by(
        id=attendee_id, event_id=event_id
    ).first_or_404()

    try:
        # 1. CHECK available drivers using EXISTING service
        provider_service = get_provider_service()
        available_drivers = provider_service.get_available_drivers(
            zone=event.city,
            limit=50
        )

        if not available_drivers:
            return jsonify({
                'success': False,
                'error': f'No available drivers in {event.city}'
            }), 400

        # 2. CREATE transport booking using EXISTING Booking model
        booking = Booking(
            user_id=registration.user_id,
            service_type=ServiceType.STADIUM_SHUTTLE,
            provider_type=ProviderType.TRANSPORT_COMPANY,
            pickup_location={
                'address': event.venue or event.city,
                'latitude': getattr(event, 'venue_latitude', 0),
                'longitude': getattr(event, 'venue_longitude', 0)
            },
            pickup_address=event.venue or event.city,
            dropoff_address=event.venue or event.city,
            pickup_time=datetime.fromisoformat(pickup_time_str),
            passenger_count=1,
            base_price=Decimal('0.00'),  # FREE for event attendees
            subtotal=Decimal('0.00'),
            total_amount=Decimal('0.00'),
            final_price=Decimal('0.00'),
            status=BookingStatus.CONFIRMED,  # AUTO-CONFIRMED
            event_id=event_id,
            booking_metadata={
                'event_assignment': True,
                'assignment_context': 'event_organizer'
            }
        )

        booking.generate_booking_reference()
        db.session.add(booking)
        db.session.flush()

        # 3. LINK to EventAssignment (EXISTING model)
        assignment = EventAssignment.query.filter_by(
            event_id=event_id,
            registration_id=registration.id
        ).first()

        if not assignment:
            assignment = EventAssignment(
                event_id=event_id,
                attendee_id=registration.user_id,
                registration_id=registration.id
            )
            db.session.add(assignment)

        assignment.transport_booking_id = booking.id
        assignment.assigned_by_id = current_user.id
        assignment.assigned_at = datetime.now(timezone.utc)

        db.session.commit()

        return jsonify({
            'success': True,
            'booking_reference': booking.booking_reference,
            'booking_id': booking.id,
            'available_drivers': len(available_drivers),
            'message': 'Transport assigned and confirmed'
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Transport assignment error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# AVAILABILITY CHECKS - Query what's available
# ============================================================================

@assignment_bp.route('/<int:event_id>/available-properties', methods=['GET'])
@login_required
def check_available_properties(event_id):
    """Check available accommodation for event dates
    Uses: AvailabilityService.is_range_available()
    """
    event = Event.query.get_or_404(event_id)

    properties = Property.query.filter(
        Property.city == event.city,
        Property.status == AccommodationPropertyStatus.ACTIVE,
        Property.is_deleted == False
    ).limit(50).all()

    available = []
    check_in = event.start_date.date() if event.start_date else None
    check_out = event.end_date.date() if event.end_date else check_in

    for prop in properties:
        is_available, _, _ = AvailabilityService.is_range_available(
            property_id=prop.id,
            check_in=check_in,
            check_out=check_out
        )

        if is_available:
            available.append({
                'id': prop.id,
                'title': prop.title,
                'price_per_night': float(prop.base_price_per_night or 0),
                'bedrooms': prop.bedrooms,
                'max_guests': prop.max_guests,
                'rating': float(prop.average_rating or 0),
                'reviews': prop.total_reviews or 0
            })

    return jsonify({
        'success': True,
        'properties': available,
        'count': len(available)
    })


@assignment_bp.route('/<int:event_id>/available-drivers', methods=['GET'])
@login_required
def check_available_drivers(event_id):
    """Check available drivers for event
    Uses: ProviderService.get_available_drivers()
    """
    event = Event.query.get_or_404(event_id)

    provider_service = get_provider_service()
    drivers = provider_service.get_available_drivers(
        zone=event.city,
        limit=100
    )

    return jsonify({
        'success': True,
        'available_drivers': len(drivers),
        'drivers': [
            {
                'id': d.get('driver_id'),
                'code': d.get('driver_code'),
                'rating': d.get('average_rating', 0),
                'vehicle': d.get('vehicle_type', 'Unknown')
            }
            for d in drivers[:10]
        ]
    })


# ============================================================================
# EXPORT - Download assignments
# ============================================================================

@assignment_bp.route('/<int:event_id>/export/assignments', methods=['GET'])
@login_required
@require_role('event_manager', 'admin', 'super_admin', 'owner')
def export_assignments(event_id):
    """Export attendee assignments as CSV"""
    from flask import make_response

    event = Event.query.get_or_404(event_id)
    registrations = EventRegistration.query.filter_by(event_id=event_id).all()
    assignments_map = {
        a.registration_id: a for a in EventAssignment.query.filter_by(event_id=event_id).all()
    }

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
            accom = AccommodationBooking.query.get(accom_booking_id)
            accom_ref = accom.booking_reference if accom else ''

        transport_ref = ''
        if transport_booking_id:
            transport = Booking.query.get(transport_booking_id)
            transport_ref = transport.booking_reference if transport else ''

        writer.writerow([
            reg.id,
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
    response.headers['Content-Disposition'] = f'attachment; filename=event_{event_id}_assignments.csv'
    response.headers['Content-Type'] = 'text/csv'
    return response

