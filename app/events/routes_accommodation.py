# app/events/routes_accommodation.py
"""
Event Accommodation Management Routes
Organizer can assign attendees to accommodation (hotels or community hosts)
"""

from flask import render_template, request, jsonify, flash, redirect, url_for, Response
from flask_login import login_required, current_user
from app.events import events_bp
from app.events.services import EventService
from app.events.models import Event, EventRegistration, EventAssignment
from app.accommodation.models.booking import AccommodationBooking, BookingContextType
from app.accommodation.models.property import Property, AccommodationPropertyType
from app.extensions import db
import csv
import io
import logging

logger = logging.getLogger(__name__)


@events_bp.route("/<slug>/accommodation")
@login_required
def accommodation_manage(slug):
    """Main accommodation management page for event organizers"""
    event = EventService.get_event_model(slug)
    if not event:
        flash('Event not found', 'danger')
        return redirect(url_for('events.my_events'))
    
    # Check permission: organizer or admin
    if event.organizer_id != current_user.id and not current_user.has_global_role('admin'):
        flash('You do not have permission to manage this event', 'danger')
        return redirect(url_for('events.landing', identifier=slug))
    
    return render_template('events/organizer/accommodation_manage.html', event=event)


@events_bp.route("/api/<slug>/accommodation/attendees")
@login_required
def api_accommodation_attendees(slug):
    """Get attendees who need accommodation assignment"""
    event = EventService.get_event_model(slug)
    if not event or (event.organizer_id != current_user.id and not current_user.has_global_role('admin')):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    # Get all registrations for this event
    registrations = EventRegistration.query.filter_by(
        event_id=event.id,
        status='confirmed'
    ).all()
    
    # Get existing assignments
    assignments = {
        a.attendee_id: a for a in EventAssignment.query.filter_by(event_id=event.id).all()
    }
    
    attendees = []
    for reg in registrations:
        assignment = assignments.get(reg.user_id)
        
        # Determine if assigned to accommodation (hotel or community host)
        has_accommodation = False
        assigned_to = None
        
        if assignment:
            if assignment.accommodation_booking_id:
                has_accommodation = True
                booking = AccommodationBooking.query.get(assignment.accommodation_booking_id)
                if booking and booking.accommodation_property:
                    assigned_to = {
                        'type': 'hotel',
                        'name': booking.accommodation_property.title,
                        'check_in': booking.check_in.isoformat() if booking.check_in else None,
                        'check_out': booking.check_out.isoformat() if booking.check_out else None
                    }
            elif assignment.community_host_id:
                has_accommodation = True
                host = Property.query.get(assignment.community_host_id)
                if host:
                    assigned_to = {
                        'type': 'community_host',
                        'name': host.title,
                        'host_name': host.owner_display_name,
                        'address': host.address_line1
                    }
        
        attendees.append({
            'id': reg.user_id,
            'registration_id': reg.id,
            'name': reg.full_name,
            'email': reg.email,
            'phone': reg.phone,
            'ticket_type': reg.ticket_type,
            'has_accommodation': has_accommodation,
            'assigned_to': assigned_to
        })
    
    return jsonify({'success': True, 'attendees': attendees})


@events_bp.route("/api/<slug>/accommodation/inventory")
@login_required
def api_accommodation_inventory(slug):
    """Get available accommodation inventory for event"""
    event = EventService.get_event_model(slug)
    if not event or (event.organizer_id != current_user.id and not current_user.has_global_role('admin')):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    # 1. Hotel rooms booked FOR this event (via context)
    hotel_bookings = AccommodationBooking.query.filter(
        AccommodationBooking.event_id == event.id,
        AccommodationBooking.status.in_(['confirmed', 'pending'])
    ).all()
    
    # Also get bookings with context_type=EVENT and context_id=slug
    context_bookings = AccommodationBooking.query.filter(
        AccommodationBooking.context_type == 'event',
        AccommodationBooking.context_id == slug,
        AccommodationBooking.status.in_(['confirmed', 'pending'])
    ).all()
    
    # Combine and deduplicate
    all_hotel_bookings = {b.id: b for b in hotel_bookings}
    for b in context_bookings:
        if b.id not in all_hotel_bookings:
            all_hotel_bookings[b.id] = b
    
    # 2. Community hosts approved for this event
    # First, check if there's a property_event_association table or event_id on property
    # For now, query properties with property_type=COMMUNITY_HOST that have event_metadata indicating this event
    community_hosts = Property.query.filter(
        Property.property_type == AccommodationPropertyType.COMMUNITY_HOST,
        Property.is_active == True,
        Property.status == 'active'
    ).all()
    
    # Filter hosts that are associated with this event (via event_metadata JSON)
    event_hosts = []
    for host in community_hosts:
        if host.event_metadata and host.event_metadata.get('event_id') == event.id:
            event_hosts.append(host)
        # Also check if host has a relationship - for now, use metadata
    
    # Get existing assignments to know what's taken
    assignments = EventAssignment.query.filter_by(event_id=event.id).all()
    taken_booking_ids = {a.accommodation_booking_id for a in assignments if a.accommodation_booking_id}
    taken_host_ids = {a.community_host_id for a in assignments if a.community_host_id}
    
    # Get assigned attendee names
    def get_assigned_attendee_name(booking_id=None, host_id=None):
        for a in assignments:
            if booking_id and a.accommodation_booking_id == booking_id:
                reg = EventRegistration.query.filter_by(event_id=event.id, user_id=a.attendee_id).first()
                return reg.full_name if reg else None
            if host_id and a.community_host_id == host_id:
                reg = EventRegistration.query.filter_by(event_id=event.id, user_id=a.attendee_id).first()
                return reg.full_name if reg else None
        return None
    
    inventory = {
        'hotels': [
            {
                'id': b.id,
                'type': 'hotel',
                'property_id': b.property_id,
                'property_name': b.accommodation_property.title if b.accommodation_property else 'Unknown Property',
                'room_type': b.special_requests or 'Standard Room',
                'check_in': b.check_in.isoformat() if b.check_in else None,
                'check_out': b.check_out.isoformat() if b.check_out else None,
                'max_guests': b.num_guests,
                'nightly_rate': float(b.nightly_rate) if b.nightly_rate else 0,
                'is_assigned': b.id in taken_booking_ids,
                'assigned_to': get_assigned_attendee_name(booking_id=b.id)
            }
            for b in all_hotel_bookings.values()
        ],
        'community_hosts': [
            {
                'id': h.id,
                'type': 'community_host',
                'name': h.title,
                'host_name': h.owner_display_name,
                'address': h.address_line1,
                'city': h.city,
                'price_per_night': float(h.base_price_per_night) if h.base_price_per_night else 0,
                'is_free': h.base_price_per_night == 0,
                'max_guests': h.max_guests,
                'description': h.description[:100] if h.description else '',
                'is_assigned': h.id in taken_host_ids,
                'assigned_to': get_assigned_attendee_name(host_id=h.id)
            }
            for h in event_hosts
        ]
    }
    
    return jsonify({'success': True, 'inventory': inventory})


@events_bp.route("/api/<slug>/accommodation/assign", methods=['POST'])
@login_required
def api_accommodation_assign(slug):
    """Assign an attendee to accommodation"""
    event = EventService.get_event_model(slug)
    if not event or (event.organizer_id != current_user.id and not current_user.has_global_role('admin')):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    data = request.get_json()
    attendee_id = data.get('attendee_id')
    inventory_id = data.get('inventory_id')
    inventory_type = data.get('inventory_type')  # 'hotel' or 'community_host'
    
    if not attendee_id or not inventory_id or not inventory_type:
        return jsonify({'success': False, 'error': 'Missing required fields'}), 400
    
    try:
        # Verify attendee exists
        registration = EventRegistration.query.filter_by(
            event_id=event.id,
            user_id=attendee_id,
            status='confirmed'
        ).first()
        
        if not registration:
            return jsonify({'success': False, 'error': 'Attendee not found'}), 404
        
        # Verify inventory item exists and is available
        if inventory_type == 'hotel':
            booking = AccommodationBooking.query.get(inventory_id)
            if not booking:
                return jsonify({'success': False, 'error': 'Hotel booking not found'}), 404
            
            # Check if already assigned to someone else
            existing = EventAssignment.query.filter(
                EventAssignment.event_id == event.id,
                EventAssignment.accommodation_booking_id == inventory_id
            ).first()
            if existing and existing.attendee_id != attendee_id:
                return jsonify({'success': False, 'error': 'This room is already assigned to another attendee'}), 400
            
        elif inventory_type == 'community_host':
            host = Property.query.get(inventory_id)
            if not host or host.property_type != AccommodationPropertyType.COMMUNITY_HOST:
                return jsonify({'success': False, 'error': 'Community host not found'}), 404
            
            # Check if already assigned to someone else
            existing = EventAssignment.query.filter(
                EventAssignment.event_id == event.id,
                EventAssignment.community_host_id == inventory_id
            ).first()
            if existing and existing.attendee_id != attendee_id:
                return jsonify({'success': False, 'error': 'This host is already assigned to another attendee'}), 400
        
        # Get or create assignment
        assignment = EventAssignment.query.filter_by(
            event_id=event.id,
            attendee_id=attendee_id
        ).first()
        
        if not assignment:
            assignment = EventAssignment(
                event_id=event.id,
                attendee_id=attendee_id,
                managed_by=current_user.id,
                assigned_by_id=current_user.id,
                assigned_at=db.func.now()
            )
            db.session.add(assignment)
        
        # Update assignment
        if inventory_type == 'hotel':
            assignment.accommodation_booking_id = inventory_id
            # Clear community host if was assigned
            assignment.community_host_id = None
        else:  # community_host
            assignment.community_host_id = inventory_id
            # Clear hotel booking if was assigned
            assignment.accommodation_booking_id = None
        
        assignment.notes = f"Assigned by {current_user.username} on {db.func.now()}"
        
        db.session.commit()
        
        # TODO: Send notification email to attendee
        
        logger.info(f"Assigned attendee {attendee_id} to {inventory_type} {inventory_id} for event {slug}")
        
        return jsonify({'success': True, 'message': 'Assigned successfully'})
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Assignment error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@events_bp.route("/api/<slug>/accommodation/unassign", methods=['POST'])
@login_required
def api_accommodation_unassign(slug):
    """Remove accommodation assignment from an attendee"""
    event = EventService.get_event_model(slug)
    if not event or (event.organizer_id != current_user.id and not current_user.has_global_role('admin')):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    data = request.get_json()
    attendee_id = data.get('attendee_id')
    
    if not attendee_id:
        return jsonify({'success': False, 'error': 'Attendee ID required'}), 400
    
    assignment = EventAssignment.query.filter_by(
        event_id=event.id,
        attendee_id=attendee_id
    ).first()
    
    if assignment:
        assignment.accommodation_booking_id = None
        assignment.community_host_id = None
        assignment.notes = f"Unassigned by {current_user.username} on {db.func.now()}"
        db.session.commit()
        logger.info(f"Unassigned attendee {attendee_id} for event {slug}")
    
    return jsonify({'success': True, 'message': 'Unassigned successfully'})


@events_bp.route("/api/<slug>/accommodation/bulk-assign", methods=['POST'])
@login_required
def api_accommodation_bulk_assign(slug):
    """Bulk assign attendees from CSV upload"""
    event = EventService.get_event_model(slug)
    if not event or (event.organizer_id != current_user.id and not current_user.has_global_role('admin')):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'}), 400
    
    file = request.files['file']
    if not file.filename.endswith('.csv'):
        return jsonify({'success': False, 'error': 'Please upload a CSV file'}), 400
    
    try:
        stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
        csv_input = csv.reader(stream)
        headers = next(csv_input)  # Skip header row
        
        assignments_created = 0
        errors = []
        
        for row_num, row in enumerate(csv_input, start=2):
            if len(row) < 2:
                continue
            
            attendee_email = row[0].strip()
            inventory_id = row[1].strip()
            inventory_type = row[2].strip().lower() if len(row) > 2 else 'hotel'
            
            if not attendee_email or not inventory_id:
                errors.append(f"Row {row_num}: Missing email or inventory ID")
                continue
            
            # Find attendee by email
            registration = EventRegistration.query.filter_by(
                event_id=event.id,
                email=attendee_email,
                status='confirmed'
            ).first()
            
            if not registration:
                errors.append(f"Row {row_num}: Attendee not found - {attendee_email}")
                continue
            
            # Verify inventory item exists
            if inventory_type == 'hotel':
                try:
                    booking_id = int(inventory_id)
                except ValueError:
                    errors.append(f"Row {row_num}: Invalid hotel booking ID - {inventory_id}")
                    continue
                    
                booking = AccommodationBooking.query.filter_by(
                    id=booking_id,
                    event_id=event.id
                ).first()
                
                if not booking:
                    errors.append(f"Row {row_num}: Hotel booking not found - {inventory_id}")
                    continue
                
                # Check if already assigned
                existing = EventAssignment.query.filter_by(
                    event_id=event.id,
                    accommodation_booking_id=booking_id
                ).first()
                if existing and existing.attendee_id != registration.user_id:
                    errors.append(f"Row {row_num}: Hotel booking {inventory_id} already assigned")
                    continue
                
                # Get or create assignment
                assignment = EventAssignment.query.filter_by(
                    event_id=event.id,
                    attendee_id=registration.user_id
                ).first()
                if not assignment:
                    assignment = EventAssignment(
                        event_id=event.id,
                        attendee_id=registration.user_id,
                        managed_by=current_user.id,
                        assigned_by_id=current_user.id,
                        assigned_at=db.func.now()
                    )
                    db.session.add(assignment)
                
                assignment.accommodation_booking_id = booking_id
                assignment.community_host_id = None
                assignments_created += 1
                
            elif inventory_type == 'community_host':
                try:
                    host_id = int(inventory_id)
                except ValueError:
                    errors.append(f"Row {row_num}: Invalid host ID - {inventory_id}")
                    continue
                
                host = Property.query.filter_by(
                    id=host_id,
                    property_type=AccommodationPropertyType.COMMUNITY_HOST
                ).first()
                
                if not host:
                    errors.append(f"Row {row_num}: Community host not found - {inventory_id}")
                    continue
                
                # Check if already assigned
                existing = EventAssignment.query.filter_by(
                    event_id=event.id,
                    community_host_id=host_id
                ).first()
                if existing and existing.attendee_id != registration.user_id:
                    errors.append(f"Row {row_num}: Community host {inventory_id} already assigned")
                    continue
                
                # Get or create assignment
                assignment = EventAssignment.query.filter_by(
                    event_id=event.id,
                    attendee_id=registration.user_id
                ).first()
                if not assignment:
                    assignment = EventAssignment(
                        event_id=event.id,
                        attendee_id=registration.user_id,
                        managed_by=current_user.id,
                        assigned_by_id=current_user.id,
                        assigned_at=db.func.now()
                    )
                    db.session.add(assignment)
                
                assignment.community_host_id = host_id
                assignment.accommodation_booking_id = None
                assignments_created += 1
                
            else:
                errors.append(f"Row {row_num}: Invalid inventory type - {inventory_type}")
                continue
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'assignments_created': assignments_created,
            'errors': errors
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Bulk assign error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@events_bp.route("/api/<slug>/accommodation/bulk-assign-template")
@login_required
def api_accommodation_bulk_assign_template(slug):
    """Download CSV template for bulk assign"""
    event = EventService.get_event_model(slug)
    if not event:
        return jsonify({'success': False, 'error': 'Event not found'}), 404
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['attendee_email', 'inventory_id', 'inventory_type'])
    writer.writerow(['guest@example.com', '123', 'hotel'])
    writer.writerow(['guest2@example.com', '456', 'community_host'])
    
    output.seek(0)
    
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename=bulk_assign_template_{slug}.csv"}
    )
