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
from app.transport.services.assignment_service import (
    ACTIVE_ASSIGNMENT_STATUSES,
)
from app.transport.services.booking_service import _validate_booking_location_coordinates
from app.transport.services.booking_service import STATUS_TRANSITIONS
from app.transport.services.booking_service import allowed_transition_values
from app.transport.services.location_snapshot import build_canonical_location_snapshot
from app.transport.utils.helpers import paginate, filter_query, sort_query
from app.utils.exceptions import ValidationError
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from sqlalchemy import func, or_
import logging

logger = logging.getLogger(__name__)

BOOKING_SORT_FIELDS = [
    "created_at", "updated_at", "pickup_time",
    "status", "payment_status", "final_price", "passenger_count"
]

# Valid status transitions live in booking_service.STATUS_TRANSITIONS
# (single source of truth shared with moderation flows).


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
    result = (
        current_user.is_authenticated
        and hasattr(current_user, "has_global_role")
        and current_user.has_global_role("admin", "super_admin", "owner")
    )
    return result


def _canonical_admin_location(raw_location, field_name, explicit_address=None):
    """Canonicalize an admin-created endpoint before it becomes a row.

    Node 3 (D2): bare text and coordinate-less dicts are rejected with the
    project's standard validation error instead of being persisted as if
    they were resolved locations. Where the request itself carries source /
    resolution_method evidence it is passed through unchanged and validated
    by the canonical builder; when it does not, the builder infers the
    truthful direct-coordinate pair. No provenance is invented here.
    """
    payload = _validate_booking_location_coordinates(raw_location, field_name)
    if (not isinstance(payload, dict)
            or payload.get("latitude") is None
            or payload.get("longitude") is None):
        raise ValidationError(
            message=f"{field_name} must include both 'latitude' and 'longitude'",
            field=field_name,
        )

    try:
        return build_canonical_location_snapshot(
            location_payload=payload,
            explicit_address=explicit_address,
            source=payload.get("source"),
            resolution_method=payload.get("resolution_method"),
        )
    except ValueError as exc:
        # Unsatisfiable provenance claim (bad pairing, or a search/curated
        # claim with no provider evidence) is a client error, not a 500.
        raise ValidationError(message=f"{field_name}: {exc}",
                              field=field_name) from exc


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
            query = query.filter(
                func.coalesce(Booking.pickup_time, Booking.created_at) >= from_date
            )
        if to_date:
            query = query.filter(
                func.coalesce(Booking.pickup_time, Booking.created_at) <= to_date
            )

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

        raw_mode = data.get("pickup_mode")
        mode = str(raw_mode).strip().lower() if raw_mode not in (None, "") else None
        if mode is not None and mode not in ("instant", "scheduled"):
            return {
                "success": False,
                "error": "pickup_mode must be 'instant' or 'scheduled'",
            }, 400

        required = ["user_id", "service_type", "provider_type",
                    "pickup_location", "dropoff_location",
                    "passenger_count",
                    "base_price", "subtotal", "total_amount", "final_price"]
        if mode != "instant":
            required.append("pickup_time")

        missing = [f for f in required if f not in data]
        if missing:
            return {"success": False, "error": f"Missing fields: {missing}"}, 400

        try:
            validated = dict(data)
            if mode == "instant":
                now = datetime.now(timezone.utc)
                validated["pickup_time"] = now
                validated["request_received_at"] = now
            if mode is not None:
                validated["pickup_mode"] = mode

            # Node 3 (D2): the admin path must not persist an un-canonicalized
            # endpoint. Both endpoints are resolved through the canonical
            # snapshot builder before the row is constructed.
            validated["pickup_location"] = _canonical_admin_location(
                data.get("pickup_location"), "pickup_location",
                data.get("pickup_address"),
            )
            validated["dropoff_location"] = _canonical_admin_location(
                data.get("dropoff_location"), "dropoff_location",
                data.get("dropoff_address"),
            )
            fields = list(required)
            if mode == "instant":
                fields.extend(["pickup_time", "request_received_at"])
            if mode is not None:
                fields.append("pickup_mode")
            booking = Booking(**{k: validated[k] for k in fields})
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

def _rider_driver_display(booking):
    """Public-safe driver/vehicle card for the rider (F-NEW-D).

    Mirrors exactly what templates/transport/rides/show.html renders
    server-side (display name or driver code, phone or fallback, rating,
    vehicle make/model/plate/class). No internal ids, no licence data,
    no user internals — only fields already authorized for rider
    visibility. Returns None when no driver is assigned so the rider
    page renders no card.
    """
    driver = getattr(booking, "driver", None)
    if driver is None:
        return None
    user = getattr(driver, "user", None)
    name = (getattr(user, "display_name", None)
            or getattr(driver, "driver_code", None) or "Driver")
    vehicle = getattr(booking, "vehicle", None)
    vehicle_class = getattr(vehicle, "vehicle_class", None)
    return {
        "name": name,
        "phone": getattr(user, "phone", None),
        "rating": (float(driver.average_rating)
                   if getattr(driver, "average_rating", None) else None),
        "vehicle": None if vehicle is None else {
            "make": getattr(vehicle, "make", None),
            "model": getattr(vehicle, "model", None),
            "license_plate": getattr(vehicle, "license_plate", None),
            "vehicle_class": (vehicle_class.value
                              if hasattr(vehicle_class, "value")
                              else vehicle_class),
        },
    }


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

        data = booking.to_dict()
        if not _current_user_is_admin():
            # MATCH-01-owned: the durable offer ledger
            # (booking_metadata.offer_attempts, outcomes "offered"/"declined")
            # is admin-visible only. The rider surface must never carry
            # rejection internals (negative "reject"/"decline"/"refuse"
            # guarantee) — strip the key for non-admin readers. The raw
            # no_match_reason value ("all_rejected") contains the same
            # forbidden substring, so it is stripped too: riders learn the
            # branch from the server-rendered page (which reloads on
            # no_match), never from this payload. The audit_log trail
            # records the same internal reason strings, so it is withheld
            # from non-admin readers as well (riders have the timeline).
            # The rider template and rider_matching.js both consume this
            # endpoint.
            meta = data.get("booking_metadata")
            if isinstance(meta, dict) and "offer_attempts" in meta:
                meta = dict(meta)
                meta.pop("offer_attempts", None)
                data["booking_metadata"] = meta
            data.pop("no_match_reason", None)
            data.pop("audit_log", None)
            # Node 3: internal Booking identifiers must not cross the
            # rider boundary (dual-ID law; cf. wallet F-04). The rider
            # surface consumes status + driver_display only — nothing
            # here reads these FKs. Admin payload keeps them.
            for _k in (
                "user_id",
                "assigned_driver_id",
                "assigned_vehicle_id",
                "provider_id",
                "original_provider_id",
                "assigned_route_id",
                "event_id",
                "event_participation_id",
                "group_leader_id",
            ):
                data.pop(_k, None)
        return {
            "success": True,
            "data": {
                "booking": data,
                "driver": (
                    booking.driver.to_dict(exclude=["license_number_encrypted"])
                    if booking.driver else None
                ),
                "vehicle": booking.vehicle.to_dict() if booking.vehicle else None,
                "driver_display": _rider_driver_display(booking),
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

        if booking.status in ACTIVE_ASSIGNMENT_STATUSES:
            return {
                "success": False,
                "error": "cannot delete a booking with an active assignment; "
                         "cancel or complete it first",
                "code": "active_assignment",
            }, 409

        # D-11: a soft-deleted booking must not retain assignment
        # references that recovery queries (which filter on
        # is_deleted == False) can no longer see. The canonical release
        # path clears these on every terminal transition, so any row
        # still carrying them here is a data-integrity anomaly; clear
        # them rather than preserve invisible references.
        if (
            booking.assigned_driver_id is not None
            or booking.assigned_vehicle_id is not None
        ):
            booking.assigned_driver_id = None
            booking.assigned_vehicle_id = None

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

        from app.transport.services.assignment_service import DispatchClaimError
        from app.transport.services.booking_service import BookingService
        from app.utils.exceptions import ValidationError

        try:
            result = BookingService.transition_status(
                booking_id,
                new_status,
                reason=data.get("reason"),
                actor=current_user,
            )
        except ValidationError as e:
            db.session.rollback()
            return {
                "success": False,
                "error": e.message,
                "allowed_transitions": allowed_transition_values(booking.status),
            }, 422
        except DispatchClaimError as e:
            db.session.rollback()
            return {
                "success": False,
                "error": e.message,
                "code": e.kind,
                "allowed_transitions": allowed_transition_values(booking.status),
            }, 409

        refreshed = result["booking"]
        if result["release"] is not None:
            logger.info(
                f"Booking {booking_id} released via canonical dispatch -> {new_status.value}"
            )
            return {"success": True, "data": refreshed.to_dict(), "release": result["release"]}
        return {"success": True, "data": refreshed.to_dict()}


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
        """Create a missing pending payment record; never assert that money arrived.

        Captures must come from verified settlement paths: the internal Wallet
        ledger or the explicit post-trip driver cash receipt. This admin endpoint
        is for reconciliation/backfill only and cannot set a booking to paid.
        """
        booking = Booking.query.filter_by(
            id=booking_id,
            is_deleted=False,
        ).with_for_update().first_or_404()
        data = request.get_json(silent=True)
        if not data:
            return {"success": False, "error": "JSON body required"}, 400

        required = ["amount", "currency", "payment_method", "payment_status"]
        missing = [field for field in required if field not in data]
        if missing:
            return {"success": False, "error": f"Missing fields: {missing}"}, 400

        requested_status = str(data.get("payment_status") or "").strip().lower()
        if requested_status == PaymentStatus.CAPTURED.value:
            return {
                "success": False,
                "error": (
                    "Payment cannot be marked captured through admin record creation. "
                    "Use a verified Wallet settlement or the driver's post-trip cash receipt."
                ),
                "code": "verified_settlement_required",
            }, 409
        if requested_status != PaymentStatus.PENDING.value:
            return {
                "success": False,
                "error": "This endpoint only creates pending reconciliation records.",
                "code": "pending_record_only",
            }, 409
        if booking.payment_status != PaymentStatus.PENDING:
            return {
                "success": False,
                "error": "Only a booking that is currently pending payment may be reconciled here.",
                "code": "booking_payment_not_pending",
            }, 409

        stored_method = str(booking.payment_method or "").strip().lower()
        supplied_method = str(data.get("payment_method") or "").strip().lower()
        if not stored_method or supplied_method != stored_method:
            return {
                "success": False,
                "error": "Payment method must match the method selected for the trip.",
                "code": "payment_method_mismatch",
            }, 409

        stored_currency = str(getattr(booking.currency, "value", booking.currency) or "").upper()
        supplied_currency = str(data.get("currency") or "").strip().upper()
        if not stored_currency or supplied_currency != stored_currency:
            return {
                "success": False,
                "error": "Currency must match the stored fare currency.",
                "code": "payment_currency_mismatch",
            }, 409

        expected_amount = booking.final_price if booking.final_price is not None else booking.total_amount
        try:
            amount = Decimal(str(data.get("amount")))
            expected = Decimal(str(expected_amount))
            if amount <= 0 or amount != expected:
                raise ValueError("amount mismatch")
        except (InvalidOperation, TypeError, ValueError):
            return {
                "success": False,
                "error": "Amount must exactly match the stored trip amount.",
                "code": "payment_amount_mismatch",
            }, 409

        existing_payment = BookingPayment.query.filter_by(
            booking_id=booking_id,
            is_deleted=False,
        ).first()
        if existing_payment is not None:
            return {
                "success": False,
                "error": "A payment record already exists for this trip; use reconciliation rather than creating a duplicate.",
                "code": "payment_record_exists",
            }, 409

        try:
            payment = BookingPayment(
                booking_id=booking_id,
                payment_reference="",
                amount=amount,
                currency=booking.currency,
                payment_method=stored_method,
                payment_method_details={"source": "admin_pending_reconciliation"},
                payment_status=PaymentStatus.PENDING,
                initiated_at=datetime.now(timezone.utc),
            )
            payment.generate_payment_reference()
            db.session.add(payment)

            from app.utils.audit import audit_log
            audit_log(
                action="transport_pending_payment_record_created",
                resource_type="booking",
                resource_id=booking.id,
                user_id=current_user.id,
                details={
                    "booking_reference": booking.booking_reference,
                    "payment_reference": payment.payment_reference,
                    "amount": str(amount),
                    "currency": stored_currency,
                    "payment_method": stored_method,
                    "payment_status": PaymentStatus.PENDING.value,
                },
                db_session=db.session,
            )
            db.session.commit()
            logger.info(
                "Pending payment reconciliation record created for trip %s",
                booking.booking_reference,
            )
            return {"success": True, "data": payment.to_dict()}, 201

        except Exception:
            db.session.rollback()
            logger.exception(
                "Error creating pending payment record for booking %s",
                booking_id,
            )
            return {
                "success": False,
                "error": "Could not record the pending payment item.",
            }, 500


class RiderWalletSettlementResource(Resource):
    """POST /api/transport/rides/<booking_reference>/payment/settle-wallet.

    Owner-scoped retry for a completed trip whose chosen Wallet payment remains
    pending. Amount/currency/method are always derived from the stored Booking;
    the client submits no financial fields.
    """

    @login_required
    def post(self, booking_reference):
        booking = Booking.query.filter_by(
            booking_reference=booking_reference,
            is_deleted=False,
        ).first()
        if booking is None or booking.user_id != current_user.id:
            # 404 for both unknown and another rider's trip.
            return {"success": False, "error": "Ride not found"}, 404

        if booking.status != BookingStatus.COMPLETED:
            return {
                "success": False,
                "error": "Wallet payment is available only after trip completion",
                "code": "trip_not_completed",
            }, 409
        if str(booking.payment_method or "").strip().lower() != "wallet":
            return {
                "success": False,
                "error": "This trip did not select Wallet payment",
                "code": "payment_method_mismatch",
            }, 409
        if booking.payment_status == PaymentStatus.CAPTURED:
            return {
                "success": True,
                "data": {
                    "booking_reference": booking.booking_reference,
                    "payment_status": "captured",
                    "idempotent_replay": True,
                },
            }, 200
        if booking.payment_status != PaymentStatus.PENDING:
            return {
                "success": False,
                "error": "This payment is not awaiting settlement",
                "code": "payment_not_pending",
            }, 409

        amount = booking.final_price if booking.final_price is not None else booking.total_amount
        currency = str(getattr(booking.currency, "value", booking.currency))
        try:
            from app.transport.services.payment_service import PaymentService
            result = PaymentService.process_payment(
                booking.id,
                {
                    "amount": str(amount),
                    "currency": currency,
                    "payment_method": "wallet",
                },
                request_id="trip-complete:%s" % booking.booking_reference,
            )
        except ValidationError as exc:
            db.session.rollback()
            message = str(getattr(exc, "message", exc))
            if "insufficient" in message.lower():
                return {
                    "success": False,
                    "error": "Your wallet balance is too low. Add funds, then retry payment.",
                    "code": "insufficient_wallet_balance",
                }, 409
            return {
                "success": False,
                "error": "Wallet payment could not be completed. Please retry.",
                "code": "wallet_payment_rejected",
            }, 409
        except Exception:
            db.session.rollback()
            logger.exception(
                "Rider wallet settlement retry failed for trip %s",
                booking_reference,
            )
            return {
                "success": False,
                "error": "Wallet payment service is temporarily unavailable. Your trip remains completed and unpaid.",
                "code": "wallet_payment_unavailable",
            }, 503

        return {
            "success": True,
            "data": {
                "booking_reference": booking.booking_reference,
                "payment_status": result.get("data", {}).get("payment_status", "pending"),
                "payment_reference": result.get("data", {}).get("payment_reference"),
                "amount": result.get("data", {}).get("amount"),
                "currency": currency,
            },
        }, 200


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
