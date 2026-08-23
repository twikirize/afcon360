# app/events/assignment.py
"""
Event Host coordination routes.

The coordination service links attendees to already-reserved owning-domain
resources; it does not create a parallel accommodation or transport system.

────────────────────────────────────────────────────────────────────────────
PURPOSE OF THIS FILE
────────────────────────────────────────────────────────────────────────────

This blueprint is the UI/API layer for an event organizer/coordinator.

The event organizer:
  1. Views the list of registered attendees for their event.
  2. Sees what accommodation/transport inventory they have already reserved
     or booked in the owning modules (accommodation, transport).
  3. Assigns a specific attendee to a specific reserved accommodation booking
     or transport booking.
  4. Tracks how many seats/rooms in each booking are still available after
     assignments.

IMPORTANT ARCHITECTURE RULE
────────────────────────────────────────────────────────────────────────────
The assignment module MUST NOT create new accommodation or transport records.
It only links an attendee registration to an EXISTING booking in another
module.

Example:
  Event organizer booked 30 rooms at Africana Hotel using the accommodation
  module.  This file allows assigning "Joan" to one of those 30 rooms.
  After assignment, there should be 29 remaining rooms available for other
  attendees.

Capacity enforcement must live in GuestCoordinationService or in the
assignment model/service, NOT here.  The route should just validate input
and delegate.

────────────────────────────────────────────────────────────────────────────
FUTURE IMPLEMENTATION NOTES
────────────────────────────────────────────────────────────────────────────

1. CAPACITY DEDUCTION
   - `EventAssignment` currently stores a link to one accommodation booking
     and one transport booking.
   - A future agent must implement a `capacity_used` or count assignments per
     booking to know how many rooms/seats are already assigned.
   - The accommodation/transport booking has its own capacity (e.g. 30 rooms,
     number of guests).  The assignment service must ensure that the number
     of assignments against a booking never exceeds that capacity.
   - When an assignment is cancelled, capacity must be released back.

2. WALLET TOP-UP INTEGRATION
   - If an attendee has a user account, it may be useful to top up their wallet
     before assigning paid services.
   - A future route or service method can:
       a. Find the attendee's user account from EventRegistration.user_id
          or attendee_user_id.
       b. Look up the wallet service.
       c. Top up the wallet if needed.
   - This should NOT be done automatically without explicit organizer action
     or consent; add an audit trail.

3. SERVICE/DEPENDENCY BOUNDARY
   - `GuestCoordinationService` is currently partially implemented.
   - The routes here expect it to expose:
       * dashboard(event, user, search, page)
       * assign_accommodation(event, user, registration_ref, booking_ref)
       * assign_transport(event, user, registration_ref, booking_ref)
       * bulk_assign(event, user, capability, assignments)
       * cancel(event, user, registration_ref, capability)
       * _assignment_ref(event, registration)opencode
       * _resolve_transport_booking(event, booking_ref)
   - A future agent must complete/formalize that service contract.

────────────────────────────────────────────────────────────────────────────
MODULE DEPENDENCIES
────────────────────────────────────────────────────────────────────────────
- `app.events.models`: Event, EventRegistration, EventAssignment
- `app.events.permissions.can_view_coordination`: shared authority gate
- `app.events.guest_coordination_service`: business logic
- `app.accommodation.models`: Property, AccommodationPropertyStatus,
  AccommodationBooking
- `app.transport.models`: Booking, BookingStatus, DriverProfile, Vehicle
"""
# ============================================================================
# FUTURE IMPLEMENTER NOTES — CROSS-MODULE ASSIGNMENT FUNCTIONALITY
# ============================================================================
#
# This file is part of a larger Event Host coordination feature that spans
# several modules:
#
#   - Events
#   - Accommodation
#   - Transport
#   - Wallet
#   - Identity / users
#   - Audit
#
# When completing the assignment functionality, the future agent must:
#
# 1. PERMISSIONS
#    Update `app/events/permissions.py` to define a clear distinction between:
#
#      - View coordination:        `can_view_coordination`
#      - Manage/assign resources:  NEW `can_manage_coordination`
#
#    The current routes use `can_view_coordination` for every operation,
#    including writes.  That is temporary.  Write operations such as
#    assign_accommodation, assign_transport, bulk_coordination, and cancel
#    must eventually require `can_manage_coordination`.
#
#    `can_manage_coordination` should return True for:
#      - event managers and above
#      - canonical event owner (individual or organization)
#      - org_owner / org_admin of the event's owning organization
#      - approved event-level staff with a new `coordinate` permission
#
#    Do NOT use `organizer_id` as ownership authority.
#    Always use canonical `current_owner_type` / `current_owner_id`.
#
# 2. ROUTES
#    Add the new permission check to every mutating route in this file:
#
#      - assignment_dashboard            -> can_view_coordination
#      - list_attendees                  -> can_view_coordination
#      - coordination_dashboard          -> can_view_coordination
#      - assign_accommodation            -> can_manage_coordination
#      - assign_transport                -> can_manage_coordination
#      - bulk_coordination               -> can_manage_coordination
#      - cancel_coordination             -> can_manage_coordination
#      - check_available_properties      -> can_view_coordination
#      - check_available_drivers         -> can_view_coordination
#      - export_assignments              -> can_view_coordination
#
# 3. MODELS
#    `EventAssignment` in `app/events/models.py` is currently a simple link
#    table.  For full functionality, consider adding:
#
#      - `status` enum that reflects assignment lifecycle:
#          pending, confirmed, cancelled, completed
#      - `capacity_used` or `seat_count` if a booking can host multiple
#        attendees
#      - `wallet_topup_required` and `wallet_topup_status` if wallet funding
#        will be part of assignment
#      - `assigned_by_id` and `assigned_at` are already present; ensure they
#        are populated on every assignment change
#      - `cancelled_by_id` and `cancelled_at` for audit
#
#    The owning modules must expose booking capacity and remaining counts.
#    Do NOT duplicate accommodation/transport inventory in the event module.
#
# 4. CAPACITY TRACKING
#    Capacity is owned by the accommodation and transport modules.
#    The assignment layer must:
#
#      - query remaining capacity from the owning module booking
#      - atomically reserve/decrement capacity on successful assignment
#      - release/increment capacity on cancellation
#      - prevent over-assignment
#
#    If the owning module does not yet expose capacity, the future agent must
#    add that capability to the owning module first, not invent parallel
#    capacity fields in `EventAssignment`.
#
# 5. WALLET TOP-UP
#    If the organizer can top up an attendee wallet, add a new service/route
#    that:
#
#      - resolves the attendee from `EventRegistration.user_id` or
#        `attendee_user_id`
#      - uses the existing WalletService
#      - logs the top-up in an audit table
#      - does not allow unauthorized top-ups or negative balances
#
# 6. ATTENDEE IDENTITY RESOLUTION
#    Assignment uses `registration_id` as the canonical guest/attendee link.
#    A guest does NOT need an AFCON360 account to be assigned accommodation or
#    transport; `EventAssignment.attendee_id` may be NULL.
#
#    Only resolve a canonical User record via
#    `app.events.attendee_accounts.find_or_create_attendee_user()` when an
#    account is genuinely required, e.g.:
#      - wallet top-up explicitly requested by the organizer
#      - account-linked services (notifications, profile) are explicitly used
#
#    Pass `create_guest_account=True` only in those explicit cases.  Never call
#    the helper to force account creation merely for assignment.  Prefer
#    resolution in the coordination service over calling it inside a route.
#
# 7. AUDIT
#    Every assignment, cancellation, bulk operation, and wallet top-up must
#    create an audit record.  Use the existing audit service or extend
#    `EventTransferLog`-style append-only logs if appropriate.
#
# 8. TESTS
#    Required test coverage:
#
#      - authorized organizer can assign accommodation/transport
#      - unauthorized user receives 403
#      - over-capacity assignment is rejected
#      - cancellation releases capacity
#      - bulk assignment returns per-item results with 207 on partial success
#      - CSV export contains correct assignment references
#      - wallet top-up success/failure paths if implemented
#
# 9. AUTHORITY INVARIANTS
#    Preserve the authority contract already established for events:
#
#      - `current_owner_type` / `current_owner_id` is canonical.
#      - `organizer_id` remains legacy public contact only.
#      - `created_by_type` / `created_by_entity_id` never change.
#      - No schema changes without a migration.
#      - No re-interpretation of legacy fields.
#
# ============================================================================

from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, abort
from flask_login import login_required, current_user
from sqlalchemy import and_, func, or_
import csv
from io import StringIO

from app.extensions import db
from app.events.models import Event, EventRegistration, EventAssignment
from app.events.permissions import (
    can_view_coordination,
    can_assign_accommodation,
    can_assign_transport,
    can_cancel_assignment,
    get_event_guest_permissions,
)
from app.events.guest_coordination_service import (
    CoordinationError,
    GuestCoordinationService,
)
from app.events.attendee_accounts import find_or_create_attendee_user  # noqa: F401  # future assignment/wallet integration
from app.accommodation.models.property import Property, AccommodationPropertyStatus
from app.transport.models import Booking, BookingStatus, DriverProfile, Vehicle

assignment_bp = Blueprint('event_assignment', __name__)


def _event_for_ref(event_ref):
    """
    Resolve an event from a public reference.

    Accepts:
      - public_id (UUID string)
      - slug
      - legacy numeric ID (only if the ref is digits)

    Returns Event or 404.
    """
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
    """
    Render the assignment dashboard for an event.

    The dashboard shows:
      - total registered attendees
      - assigned accommodation count
      - assigned transport count
      - available properties in the event city (legacy/stub)
      - recent assignments

    Future improvement:
      Replace or enhance the statistics with live remaining capacity from the
      actual accommodation/transport bookings, not just a count of assignments.
      Currently `available_properties` is a generic property count, not the
      number of available rooms in existing reservations.
    """
    event = _event_for_ref(event_ref)
    event_id = event.id

    # Shared coordination permission check. This should be the only authority
    # gate for assignment-related actions.
    allowed, _ = can_view_coordination(current_user, event)
    if not allowed:
        flash("You don't have permission to manage this event.", "danger")
        return redirect(url_for('events.list'))

    # Get event statistics
    total_attendees = EventRegistration.query.filter_by(
        event_id=event_id, is_deleted=False
    ).count()

    # Count assignments with bookings.
    # Important: this counts distinct assignments, not total rooms/seats used.
    # If one booking can hold multiple attendees, capacity handling must be
    # handled elsewhere.
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
    # TODO: Replace this with actual "remaining rooms in reserved bookings"
    #       rather than total active properties in the city.
    available_properties = Property.query.filter_by(
        city=event.city,
        status=AccommodationPropertyStatus.ACTIVE.value,
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
        recent_assignments=recent_assignments,
        perms=get_event_guest_permissions(current_user, event),
    )


# ============================================================================
# ATTENDEES - List all registered attendees
# ============================================================================

@assignment_bp.route('/<event_ref>/attendees', methods=['GET'])
@login_required
def list_attendees(event_ref):
    """
    List all registered attendees for an event.

    Supports:
      - pagination via `page`
      - search by `full_name` or `email`
      - filtering by assignment status:
          * all          -> show all attendees
          * accommodation -> show those without accommodation assignment
          * transport    -> show those without transport assignment
          * both         -> show those without either
          * assigned     -> show those with both accommodation and transport

    Returns JSON on forbidden, HTML template otherwise.

    Future improvement:
      Add remaining capacity for each booking in the response so the UI can
      disable assignment buttons when capacity is exhausted.
    """
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

    # Build a map of user/attendee identity to registration id.
    # Resolve attendee identity to a registration ID.
    # Assignment uses registration_id as the canonical guest/attendee link.
    # Do NOT create an AFCON360 account for assignment.
    # Use find_or_create_attendee_user(create_guest_account=True) only when
    # wallet top-up or account-linked services are explicitly requested.
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

    # Walk through assignments to associate them with registrations either by
    # direct registration_id or by attendee user identity.
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
        # Show attendees who do NOT yet have an accommodation assignment
        query = query.filter(~EventRegistration.id.in_(accommodation_ids)) if accommodation_ids else query
    elif filter_type == 'transport':
        # Show attendees who do NOT yet have a transport assignment
        query = query.filter(~EventRegistration.id.in_(transport_ids)) if transport_ids else query
    elif filter_type == 'both':
        # Show attendees missing either accommodation or transport
        if accommodation_ids:
            query = query.filter(~EventRegistration.id.in_(accommodation_ids))
        if transport_ids:
            query = query.filter(~EventRegistration.id.in_(transport_ids))
    elif filter_type == 'assigned':
        # Show attendees who have both accommodation and transport
        query = query.filter(EventRegistration.id.in_(accommodation_ids & transport_ids))

    attendees = query.paginate(page=page, per_page=20, error_out=False)

    return render_template(
        'events/admin/attendees_list.html',
        event=event,
        attendees=attendees,
        assignment_map=assignment_map,
        search=search,
        filter_type=filter_type,
        perms=get_event_guest_permissions(current_user, event),
    )


@assignment_bp.route('/<event_ref>/coordination', methods=['GET'])
@login_required
def coordination_dashboard(event_ref):
    """
    JSON endpoint for a coordination dashboard.

    Delegates entirely to GuestCoordinationService.dashboard().
    Future agents should make this the canonical data source for the UI,
    replacing the old HTML-only dashboard if needed.
    """
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
    """
    Assign a registered attendee to an existing accommodation booking.

    Expected JSON payload:
      {
        "registration_ref": "ER-...",
        "booking_ref": "HB-..."   // reference to existing AccommodationBooking
      }

    The route delegates validation and persistence to GuestCoordinationService.
    That service MUST:
      - verify the attendee is registered for this event and not already
        assigned a different accommodation booking for the same event.
      - verify the booking belongs to the event or matches the event context.
      - verify the booking still has capacity.
      - create/update EventAssignment with accommodation_booking_id.
      - decrement the booking's remaining capacity if capacity tracking is
        implemented in the accommodation module.
      - handle rollback on failure.

    Future improvement:
      Add support for assigning a specific room/unit within a booking if the
      accommodation model supports room-level assignments.
    """
    event = _event_for_ref(event_ref)
    event_id = event.id
    allowed, message = can_assign_accommodation(current_user, event)
    if not allowed:
        return jsonify({'success': False, 'code': 'EVENT_COORDINATION_FORBIDDEN', 'error': message}), 403
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
    """
    Assign a registered attendee to an existing transport booking.

    Expected JSON payload:
      {
        "registration_ref": "ER-...",
        "booking_ref": "TB-..."   // reference to existing transport Booking
      }

    Same coordination contract as accommodation:
      - validate attendee belongs to event
      - validate transport booking belongs to event / eligible
      - validate capacity (seats)
      - create/update EventAssignment.transport_booking_id
      - decrement remaining seats if capacity management exists
      - rollback on any failure

    Future improvement:
      Handle group transport where multiple attendees can be assigned to a
      single booking in one call.
    """
    event = _event_for_ref(event_ref)
    event_id = event.id
    allowed, message = can_assign_transport(current_user, event)
    if not allowed:
        return jsonify({'success': False, 'code': 'EVENT_COORDINATION_FORBIDDEN', 'error': message}), 403
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
    """
    Bulk assign multiple attendees to a capability.

    Expected JSON payload:
      {
        "assignments": [
            {"registration_ref": "...", "booking_ref": "..."},
            ...
        ]
      }

    `capability` should be "accommodation" or "transport".

    Returns 207 Multi-Status if some assignments fail, with per-item results.
    """
    event = _event_for_ref(event_ref)
    data = request.get_json(silent=True) or {}
    if capability == 'accommodation':
        allowed, message = can_assign_accommodation(current_user, event)
    elif capability == 'transport':
        allowed, message = can_assign_transport(current_user, event)
    else:
        allowed, message = False, 'Unknown coordination capability'
    if not allowed:
        return jsonify({'success': False, 'code': 'EVENT_COORDINATION_FORBIDDEN', 'error': message}), 403
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
    """
    Cancel a specific assignment capability for an attendee.

    Example:
        DELETE /<event_ref>/coordination/ER-ABC/accommodation
    would remove the accommodation assignment for that attendee but keep
    transport assignment unchanged.

    On cancellation, any capacity that was consumed by the assignment must be
    released back to the owning booking.
    """
    event = _event_for_ref(event_ref)
    allowed, message = can_cancel_assignment(current_user, event, capability)
    if not allowed:
        return jsonify({'success': False, 'code': 'EVENT_COORDINATION_FORBIDDEN', 'error': message}), 403
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
    """
    Return event-reserved accommodation bookings that still have remaining
    capacity.

    This is NOT a generic city property search. It only shows bookings that are
    linked to this event (via event_id or context_id) and have capacity left.

    Future improvement:
      - Use the booking's own capacity fields instead of `num_guests`.
      - Include exact room assignments if room-level assignment is added.
    """
    event = _event_for_ref(event_ref)
    allowed, message = can_view_coordination(current_user, event)
    if not allowed:
        return jsonify({'success': False, 'code': 'EVENT_COORDINATION_FORBIDDEN', 'error': message}), 403

    from app.accommodation.models.booking import AccommodationBooking

    # A booking is available for assignment when it is explicitly reserved for
    # this event (via event_id or context_id) OR when it was booked/owned by
    # the organizer performing the assignment.  Organizers frequently book
    # accommodation for their event without tagging it to the event context, and
    # they still need to assign their own attendees to those rooms.
    actor_id = getattr(current_user, 'id', None)
    owner_links = []
    if actor_id is not None:
        owner_links = [
            AccommodationBooking.booked_by_user_id == actor_id,
            AccommodationBooking.booking_owner_id == actor_id,
        ]

    booking_filter = or_(
        AccommodationBooking.event_id == event.id,
        AccommodationBooking.context_id.in_([str(event.public_id), str(event.slug)]),
        *owner_links,
    )

    bookings = AccommodationBooking.query.filter(
        booking_filter,
        AccommodationBooking.status.in_(['held', 'confirmed', 'pending', 'pending_approval']),
        AccommodationBooking.is_deleted.is_(False),
    ).limit(200).all()

    # Build assignment count per booking to compute remaining capacity.
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
        # Capacity heuristic: number of guests in the booking.
        # TODO: Replace with actual "rooms" or "beds" capacity from the
        # accommodation booking model.
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
    """
    Return event-reserved transport bookings that are eligible for assignment.

    A booking is eligible if:
      - it belongs to the event
      - it has status CONFIRMED or ASSIGNED
      - it has an assigned driver and vehicle
      - GuestCoordinationService._resolve_transport_booking() accepts it

    Future improvement:
      - Support transport bookings that do not yet have a driver assigned.
      - Include seat-level remaining capacity.
    """
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
    """
    Export attendee assignments as CSV.

    Columns:
      Registration ID, Name, Email, Phone,
      Accommodation Booked, Accommodation Ref,
      Transport Booked, Transport Ref,
      Registered At

    Future improvement:
      Add wallet status or top-up status if wallet integration is added.
    """
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
    # Assignment uses registration_id as the canonical guest/attendee link.
    # Do NOT create an AFCON360 account for assignment.
    # Use find_or_create_attendee_user(create_guest_account=True) only when
    # wallet top-up or account-linked services are explicitly requested.
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