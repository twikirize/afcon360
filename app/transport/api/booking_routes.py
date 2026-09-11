# app/transport/api/booking_routes.py
"""
AFCON360 Transport - Booking REST API
Handles the full booking lifecycle: create, view, status updates,
driver assignment, payments, and route association.
"""
from flask import request, abort
from flask_login import current_user, login_required
from flask_restful import Resource
from app.extensions import db
from app.transport.models import (
    Booking, BookingPayment, BookingStatus,
    PaymentStatus, DriverProfile, Vehicle, ScheduledRoute
)
from app.auth.decorators import admin_required
from app.transport.services.booking_service import _validate_booking_location_coordinates
from app.transport.utils.helpers import paginate, filter_query, sort_query
from datetime import datetime, timezone
from sqlalchemy import func, or_
import logging

logger = logging.getLogger(__name__)

BOOKING_SORT_FIELDS = [
    "created_at", "updated_at", "pickup_time",
    "status", "payment_status", "final_price", "passenger_count"
]

# Valid status transitions - enforced server-side
STATUS_TRANSITIONS = {
    BookingStatus.DRAFT:           [BookingStatus.PENDING_PAYMENT, BookingStatus.CANCELLED],
    BookingStatus.PENDING_PAYMENT: [BookingStatus.CONFIRMED, BookingStatus.CANCELLED],
    BookingStatus.CONFIRMED:       [BookingStatus.ASSIGNED, BookingStatus.CANCELLED],
    BookingStatus.ASSIGNED:        [BookingStatus.DRIVER_EN_ROUTE, BookingStatus.CANCELLED],
    BookingStatus.DRIVER_EN_ROUTE: [BookingStatus.PICKUP_ARRIVED, BookingStatus.CANCELLED],
    BookingStatus.PICKUP_ARRIVED:  [BookingStatus.IN_PROGRESS, BookingStatus.NO_SHOW],
    BookingStatus.IN_PROGRESS:     [BookingStatus.COMPLETED, BookingStatus.DISPUTED],
    BookingStatus.COMPLETED:       [],
    BookingStatus.CANCELLED:       [],
    BookingStatus.NO_SHOW:         [],
    BookingStatus.DISPUTED:        [BookingStatus.COMPLETED, BookingStatus.CANCELLED],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _booking_or_404(booking_id):
    return Booking.query.filter_by(id=booking_id, is_deleted=False).first_or_404()


def _booking_by_reference_or_404(booking_reference):
    return Booking.query.filter_by(
        booking_reference=booking_reference, is_deleted=False
    ).first_or_404()


def _current_user_is_admin():
    return (
        current_user.is_authenticated
        and hasattr(current_user, "has_global_role")
        and current_user.has_global_role("admin", "super_admin", "owner")
    )


def _can_transition(current: BookingStatus, target: BookingStatus) -> bool:
    return target in STATUS_TRANSITIONS.get(current, [])


# ===========================================================================
# Booking List
# ===========================================================================

class BookingListResource(Resource):
    """GET /api/transport/bookings  - list with filters/sort/pagination
       POST /api/transport/bookings - create a new booking
    """

    @admin_required
    def get(self):
        """List bookings with filtering, sorting, and pagination"""
        query = Booking.query.filter_by(is_deleted=False)

        # Filters
        filters = {
            "status":         request.args.get("status"),
            "payment_status": request.args.get("payment_status"),
            "service_type":   request.args.get("service_type"),
            "provider_type":  request.args.get("provider_type"),
            "user_type":      request.args.get("user_type"),
            "final_price__gte": request.args.get("min_price", type=float),
            "final_price__lte": request.args.get("max_price", type=float),
        }
        query = filter_query(query, Booking, filters)

        # Date range filter
        from_date = request.args.get("from_date")
        to_date = request.args.get("to_date")
        if from_date:
            query = query.filter(Booking.pickup_time >= from_date)
        if to_date:
            query = query.filter(Booking.pickup_time <= to_date)

        # Driver / vehicle filter
        driver_id = request.args.get("driver_id", type=int)
        vehicle_id = request.args.get("vehicle_id", type=int)
        if driver_id:
            query = query.filter(Booking.assigned_driver_id == driver_id)
        if vehicle_id:
            query = query.filter(Booking.assigned_vehicle_id == vehicle_id)

        # Search on reference
        search = request.args.get("search")
        if search:
            query = query.filter(
                or_(
                    Booking.booking_reference.ilike(f"%{search}%"),
                    Booking.external_reference.ilike(f"%{search}%"),
                )
            )

        query = sort_query(query, Booking, BOOKING_SORT_FIELDS)
        result = paginate(query)

        return {
            "success": True,
            "data": {
                "items": [b.to_dict() for b in result["items"]],
                "total":    result["total"],
                "page":     result["page"],
                "per_page": result["per_page"],
                "pages":    result["pages"],
                "has_next": result["has_next"],
                "has_prev": result["has_prev"],
            },
        }

    @admin_required
    def post(self):
        """Create a new booking (admin / system use)"""
        data = request.get_json()
        if not data:
            return {"success": False, "error": "JSON body required"}, 400

        required = ["user_id", "service_type", "provider_type",
                    "pickup_location", "dropoff_location",
                    "pickup_time", "passenger_count",
                    "base_price", "subtotal", "total_amount", "final_price"]

        missing = [f for f in required if f not in data]
        if missing:
            return {"success": False, "error": f"Missing fields: {missing}"}, 400

        try:
            from app.utils.exceptions import ValidationError
            validated = dict(data)
            validated["pickup_location"] = _validate_booking_location_coordinates(data.get("pickup_location"), "pickup_location")
            validated["dropoff_location"] = _validate_booking_location_coordinates(data.get("dropoff_location"), "dropoff_location")
            booking = Booking(**{k: validated[k] for k in required})
            booking.generate_booking_reference()
            db.session.add(booking)
            db.session.commit()
            logger.info(f"Booking created: ref={booking.booking_reference}")
            return {"success": True, "data": booking.to_dict()}, 201

        except ValidationError as e:
            db.session.rollback()
            return {"success": False, "error": str(e)}, 400
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating booking: {e}", exc_info=True)
            return {"success": False, "error": str(e)}, 500


# ===========================================================================
# Booking Detail
# ===========================================================================

class BookingDetailResource(Resource):
    """GET/PUT/DELETE /api/transport/bookings/<booking_reference>"""

    @login_required
    def get(self, booking_reference):
        """Get full booking detail with related data (owner or admin only)"""
        booking = _booking_by_reference_or_404(booking_reference)

        if not (_current_user_is_admin() or booking.user_id == current_user.id):
            logger.warning(
                f"Ownership check failed: user={current_user.id} tried to access "
                f"booking owned by {booking.user_id}"
            )
            abort(403)

        return {
            "success": True,
            "data": {
                "booking": booking.to_dict(),
                "driver": (
                    booking.driver.to_dict(exclude=["license_number_encrypted"])
                    if booking.driver else None
                ),
                "vehicle": booking.vehicle.to_dict() if booking.vehicle else None,
                "route": booking.assigned_route.to_dict() if booking.assigned_route else None,
                "payments": [p.to_dict() for p in booking.payments],
                "incidents": [i.to_dict() for i in booking.incidents],
                "rating": booking.rating.to_dict() if booking.rating else None,
            },
        }

    @admin_required
    def put(self, booking_reference):
        """Update booking fields (admin only)"""
        booking = _booking_by_reference_or_404(booking_reference)
        data = request.get_json()
        if not data:
            return {"success": False, "error": "JSON body required"}, 400

        updatable = [
            "pickup_instructions", "dropoff_instructions",
            "pickup_contact_name", "pickup_contact_phone",
            "dropoff_contact_name", "dropoff_contact_phone",
            "special_requirements", "accessibility_requirements",
            "passenger_count", "luggage_count",
            "booking_metadata",
        ]
        for field in updatable:
            if field in data:
                setattr(booking, field, data[field])

        try:
            db.session.commit()
            logger.info(f"Booking {booking_reference} updated")
            return {"success": True, "data": booking.to_dict()}
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating booking {booking_reference}: {e}", exc_info=True)
            return {"success": False, "error": str(e)}, 500

    @admin_required
    def delete(self, booking_reference):
        """Soft delete booking.

        Rejects bookings that currently hold an active assignment
        (TH-3-D2): a live booking must be cancelled/completed via the
        canonical release before it can be soft-deleted.
        """
        booking = _booking_by_reference_or_404(booking_reference)

        ACTIVE_ASSIGNMENT = (
            BookingStatus.ASSIGNED,
            BookingStatus.DRIVER_EN_ROUTE,
            BookingStatus.PICKUP_ARRIVED,
            BookingStatus.IN_PROGRESS,
        )
        if booking.status in ACTIVE_ASSIGNMENT:
            return {
                "success": False,
                "error": "cannot delete a booking with an active assignment; "
                         "cancel or complete it first",
                "code": "active_assignment",
            }, 409

        booking.is_deleted = True
        booking.deleted_at = datetime.now(timezone.utc)

        try:
            db.session.commit()
            logger.info(f"Booking {booking_reference} soft-deleted")
            return {"success": True, "message": "Booking deleted"}
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error deleting booking {booking_reference}: {e}", exc_info=True)
            return {"success": False, "error": str(e)}, 500


# ===========================================================================
# Booking Status
# ===========================================================================

class BookingStatusResource(Resource):
    """POST /api/transport/bookings/<booking_id>/status"""

    @admin_required
    def post(self, booking_id):
        """
        Transition booking to a new status.
        Enforces valid state machine transitions.
        """
        booking = _booking_or_404(booking_id)
        data = request.get_json()
        if not data:
            return {"success": False, "error": "JSON body required"}, 400

        try:
            new_status = BookingStatus(data.get("status"))
        except (ValueError, KeyError):
            return {"success": False, "error": f"Invalid status: {data.get('status')}"}, 400

        if not _can_transition(booking.status, new_status):
            return {
                "success": False,
                "error": f"Cannot transition from {booking.status.value} to {new_status.value}",
                "allowed_transitions": [s.value for s in STATUS_TRANSITIONS.get(booking.status, [])],
            }, 422

        old_status = booking.status
        now = datetime.now(timezone.utc)

        # TH-3-D2: terminal transitions on an assigned booking go through the
        # canonical release (status -> terminal, clear assignment FKs, free
        # resources with late-release protection) in one transaction.
        TERMINAL_TARGETS = (
            BookingStatus.COMPLETED,
            BookingStatus.CANCELLED,
            BookingStatus.NO_SHOW,
            BookingStatus.DISPUTED,
        )
        if new_status in TERMINAL_TARGETS and (
            booking.assigned_driver_id is not None or booking.assigned_vehicle_id is not None
        ):
            from app.transport.services.assignment_service import (
                AssignmentService,
                DispatchClaimError,
            )
            if new_status == BookingStatus.COMPLETED:
                booking.completed_at = now
            elif new_status == BookingStatus.CANCELLED:
                booking.cancelled_at = now
                booking.cancellation_reason = data.get("reason", "admin_action")
                booking.cancellation_initiated_by = "admin"
            try:
                release_result = AssignmentService.release(
                    booking_id,
                    new_status,
                    actor=current_user,
                    reason=data.get("reason"),
                    audit_extra={"from": old_status.value},
                )
            except DispatchClaimError as e:
                db.session.rollback()
                return {
                    "success": False,
                    "error": e.message,
                    "code": e.kind,
                    "allowed_transitions": [
                        s.value for s in STATUS_TRANSITIONS.get(booking.status, [])
                    ],
                }, 409
            refreshed = _booking_or_404(booking_id)
            logger.info(
                f"Booking {booking_id} released via canonical dispatch -> {new_status.value}"
            )
            return {"success": True, "data": refreshed.to_dict(), "release": release_result}

        booking.status = new_status

        # Set lifecycle timestamps automatically
        if new_status == BookingStatus.CONFIRMED:
            booking.confirmed_at = now
        elif new_status == BookingStatus.COMPLETED:
            booking.completed_at = now
        elif new_status == BookingStatus.CANCELLED:
            booking.cancelled_at = now
            booking.cancellation_reason = data.get("reason", "admin_action")
            booking.cancellation_initiated_by = "admin"

        # Append to audit log
        booking.audit_log = (booking.audit_log or []) + [{
            "action": "status_changed",
            "from": old_status.value,
            "to": new_status.value,
            "at": now.isoformat(),
            "reason": data.get("reason"),
        }]

        try:
            db.session.commit()
            logger.info(f"Booking {booking_id} status: {old_status.value} → {new_status.value}")
            return {"success": True, "data": booking.to_dict()}
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error transitioning booking {booking_id}: {e}", exc_info=True)
            return {"success": False, "error": str(e)}, 500


# ===========================================================================
# Booking Assignment
# ===========================================================================

class BookingAssignmentResource(Resource):
    """POST /api/transport/bookings/<booking_id>/assign"""

    @admin_required
    def post(self, booking_id):
        """
        Assign a driver (and vehicle) to a booking via the canonical
        dispatch claim (TH-3-D2). The vehicle is derived from the driver's
        current vehicle when not supplied. The assignment is atomic; a
        concurrent claim or cancellation wins and yields a typed 409.
        """
        from app.transport.services.assignment_service import (
            AssignmentService,
            DispatchClaimError,
        )

        booking = _booking_or_404(booking_id)
        data = request.get_json()
        if not data:
            return {"success": False, "error": "JSON body required"}, 400

        driver_id = data.get("driver_id")
        if not driver_id:
            return {"success": False, "error": "driver_id is required for assignment"}, 400

        driver = DriverProfile.query.filter_by(id=driver_id, is_deleted=False).first()
        if not driver:
            return {"success": False, "error": f"Driver {driver_id} not found"}, 404

        vehicle_id = data.get("vehicle_id")
        if not vehicle_id:
            vehicle_id = driver.current_vehicle.id if driver.current_vehicle else None
        if not vehicle_id:
            return {
                "success": False,
                "error": f"Driver {driver_id} has no vehicle to assign; supply vehicle_id",
            }, 400

        force = bool(data.get("force", False))

        try:
            result = AssignmentService.claim(
                booking.booking_reference,
                driver_id,
                vehicle_id,
                actor=current_user,
                force=force,
            )
        except DispatchClaimError as e:
            db.session.rollback()
            status_code = (
                403 if e.kind == "unauthorized" else 409
            )
            return {
                "success": False,
                "error": e.message,
                "code": e.kind,
            }, status_code

        logger.info(f"Booking {booking_id} claimed via canonical dispatch: driver={driver_id}")
        return {"success": True, "data": result}


# ===========================================================================
# Booking Payments
# ===========================================================================

class BookingPaymentResource(Resource):
    """GET/POST /api/transport/bookings/<booking_id>/payments"""

    @admin_required
    def get(self, booking_id):
        """List all payment records for a booking"""
        _booking_or_404(booking_id)
        payments = BookingPayment.query.filter_by(
            booking_id=booking_id, is_deleted=False
        ).order_by(BookingPayment.created_at.desc()).all()

        return {
            "success": True,
            "data": {
                "payments": [p.to_dict() for p in payments],
                "total_paid": float(
                    sum(
                        p.amount for p in payments
                        if p.payment_status == PaymentStatus.CAPTURED
                    )
                ),
            },
        }

    @admin_required
    def post(self, booking_id):
        """Record a new payment against a booking"""
        booking = _booking_or_404(booking_id)
        data = request.get_json()
        if not data:
            return {"success": False, "error": "JSON body required"}, 400

        required = ["amount", "currency", "payment_method", "payment_status"]
        missing = [f for f in required if f not in data]
        if missing:
            return {"success": False, "error": f"Missing fields: {missing}"}, 400

        try:
            payment = BookingPayment(
                booking_id=booking_id,
                amount=data["amount"],
                currency=data["currency"],
                payment_method=data["payment_method"],
                payment_status=data["payment_status"],
                payment_gateway=data.get("payment_gateway"),
                gateway_transaction_id=data.get("gateway_transaction_id"),
                initiated_at=datetime.now(timezone.utc),
            )
            payment.generate_payment_reference()

            # Sync booking payment status
            if data["payment_status"] == PaymentStatus.CAPTURED.value:
                booking.payment_status = PaymentStatus.CAPTURED
                booking.payment_captured_at = datetime.now(timezone.utc)
            elif data["payment_status"] == PaymentStatus.FAILED.value:
                booking.payment_status = PaymentStatus.FAILED

            db.session.add(payment)
            db.session.commit()
            logger.info(f"Payment recorded for booking {booking_id}: ref={payment.payment_reference}")
            return {"success": True, "data": payment.to_dict()}, 201

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error recording payment for booking {booking_id}: {e}", exc_info=True)
            return {"success": False, "error": str(e)}, 500


# ===========================================================================
# Booking Route Association
# ===========================================================================

class BookingRouteResource(Resource):
    """GET/POST /api/transport/bookings/<booking_id>/route"""

    @admin_required
    def get(self, booking_id):
        """Get the scheduled route assigned to this booking"""
        booking = _booking_or_404(booking_id)
        if not booking.assigned_route:
            return {"success": True, "data": None}

        return {"success": True, "data": booking.assigned_route.to_dict()}

    @admin_required
    def post(self, booking_id):
        """Assign a scheduled route to a booking"""
        booking = _booking_or_404(booking_id)
        data = request.get_json()
        if not data:
            return {"success": False, "error": "JSON body required"}, 400

        route_id = data.get("route_id")
        if not route_id:
            return {"success": False, "error": "route_id required"}, 400

        route = ScheduledRoute.query.filter_by(
            id=route_id, is_deleted=False, is_active=True
        ).first()
        if not route:
            return {"success": False, "error": f"Route {route_id} not found or inactive"}, 404

        # Check capacity
        if not route.can_accommodate(booking.passenger_count):
            return {
                "success": False,
                "error": "Route does not have enough available seats",
                "available_seats": route.available_seats,
                "requested": booking.passenger_count,
            }, 422

        booking.assigned_route_id = route_id
        route.update_availability()

        try:
            db.session.commit()
            logger.info(f"Booking {booking_id} assigned to route {route_id}")
            return {"success": True, "data": booking.to_dict()}
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error assigning route to booking {booking_id}: {e}", exc_info=True)
            return {"success": False, "error": str(e)}, 500
