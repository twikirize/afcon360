"""BOOKING-LIFECYCLE-REQUEST-CREATE (Stage 3B, Phase 2A).

Rider request-creation endpoint. Authenticated + commitment-gated
(login, profile completion, KYC tier 2 — the same gates as the legacy
rider booking route). Creates zero Bookings by construction.
"""
import logging

from flask import request
from flask_login import current_user, login_required
from flask_restful import Resource

from app.extensions import db

from app.auth.decorators import require_profile_completion
from app.auth.kyc_compliance import require_kyc_tier
from app.transport.services.ride_request_service import (
    IdempotencyConflictError,
    RideRequestService,
    serialize_request,
)
from app.utils.exceptions import ValidationError

logger = logging.getLogger(__name__)


class RideRequestCreateResource(Resource):
    """POST /api/transport/ride-requests — create a pre-Booking ride request."""

    # Outermost runs first: anonymous callers get the KYC gate's 401
    # (same as login_required's JSON 401 for /api/ paths).
    method_decorators = [
        login_required,
        require_profile_completion,
        require_kyc_tier(2),
    ]

    def post(self):
        data = request.get_json(silent=True) or {}
        try:
            result = RideRequestService.create_request(current_user.id, data)
        except IdempotencyConflictError as e:
            logger.warning("Ride-request idempotency conflict for user %s: %s",
                           getattr(current_user, "id", None), e.message)
            return {"success": False, "error": e.message,
                    "code": "idempotency_conflict"}, 409
        except ValidationError as e:
            return {"success": False, "error": e.message}, 400

        ride_request = result["request"]
        cycle = result["cycle"]
        replayed = bool(result.get("replayed"))
        logger.info("Ride-request %s for user %s (replayed=%s)",
                    ride_request.public_id,
                    getattr(current_user, "id", None), replayed)
        return {
            "success": True,
            "data": serialize_request(ride_request, cycle),
            "replayed": replayed,
        }, (200 if replayed else 201)

class RideRequestDetailResource(Resource):
    """GET /api/transport/ride-requests/<request_public_id> — owner-scoped tracker."""

    @login_required
    def get(self, request_public_id):
        from app.transport.models import Booking, DriverProfile, RideRequest, SearchCycle, Vehicle

        ride_request = RideRequest.query.filter_by(
            public_id=request_public_id, is_deleted=False
        ).first()
        # 404 for both unknown and someone else's request avoids a reference
        # existence oracle.
        if ride_request is None or ride_request.user_id != current_user.id:
            return {"success": False, "error": "Ride request not found"}, 404

        cycle = SearchCycle.query.filter_by(
            ride_request_id=ride_request.id, is_deleted=False
        ).order_by(SearchCycle.cycle_number.desc()).first()
        if cycle is None:
            return {"success": False, "error": "Ride request has no search history"}, 500

        data = serialize_request(ride_request, cycle)
        data["booking_reference"] = ride_request.public_id
        data["converted"] = ride_request.status == "converted"
        data["cycle"]["terminal_reason"] = cycle.terminal_reason

        if ride_request.status == "converted":
            booking = Booking.query.filter_by(
                ride_request_id=ride_request.id, is_deleted=False
            ).first()
            if booking is None:
                # A converted request without its unique Booking violates the
                # atomic-conversion contract. Fail closed and log the anomaly.
                logger.error(
                    "RideRequest %s says converted but has no linked Booking",
                    ride_request.public_id,
                )
                return {"success": False, "error": "Ride assignment is being reconciled"}, 503

            data["booking_status"] = str(
                getattr(booking.status, "value", booking.status)
            )
            driver = (
                db.session.get(DriverProfile, booking.assigned_driver_id)
                if booking.assigned_driver_id else None
            )
            vehicle = (
                db.session.get(Vehicle, booking.assigned_vehicle_id)
                if booking.assigned_vehicle_id else None
            )
            driver_user = driver.user if driver is not None else None
            data["driver"] = ({
                "display_name": (
                    getattr(driver_user, "display_name", None)
                    or getattr(driver, "driver_code", None)
                    or "Your driver"
                ),
                "rating": float(driver.average_rating or 0) if driver else None,
            } if driver else None)
            data["vehicle"] = ({
                "make": vehicle.make,
                "model": vehicle.model,
                "license_plate": vehicle.license_plate,
                "vehicle_class": str(
                    getattr(vehicle.vehicle_class, "value", vehicle.vehicle_class)
                ) if vehicle.vehicle_class else None,
            } if vehicle else None)
            data["payment"] = {
                "method": booking.payment_method,
                "status": str(
                    getattr(booking.payment_status, "value", booking.payment_status)
                ),
                "amount": float(booking.final_price or booking.total_amount or 0),
                "currency": str(getattr(booking.currency, "value", booking.currency)),
            }
        return {"success": True, "data": data}
