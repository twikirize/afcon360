"""AFCON360 Transport Module - Passenger Service

Domain-owned participant management for Transport.

Purpose:
    Support BOOKER != PASSENGER, accountless passengers, group / multi-vehicle
    assignments, capacity enforcement, and a secure claim/link flow.

Security model:
    * A passenger may exist WITHOUT a System User Account (accountless).
    * Management of a booking requires the BOOKER (authorized via Booking.user_id).
    * A passenger claim token is short-lived, unguessable, single-purpose,
      bound to the specific passenger, consumed on success, and audited. It
      NEVER grants management rights - it only links the passenger to a User.
    * One user cannot claim another passenger's record (token is bound to the
      passenger id and the intended identity attributes).
    * Capacity is a Transport-domain concern, never a Wallet concern.

Canonical identity:
    User        = AFCON360 SYSTEM USER ACCOUNT (app/identity/models/user.py)
    AccountModel= FINANCIAL ACCOUNT (app/wallet/models/ledger.py) - NOT touched here
"""
from datetime import datetime, timezone, timedelta
import hashlib
import secrets
import logging
from typing import Dict, List, Optional, Any

from app.extensions import db
from app.transport.models import (
    Booking,
    TransportPassenger,
    PassengerStatus,
    Vehicle,
)
from app.utils.exceptions import ValidationError, NotFoundError, PermissionError
from app.utils.audit import audit_log

logger = logging.getLogger(__name__)

CLAIM_TOKEN_TTL_MINUTES = 30
DEFAULT_CLAIM_TTL = timedelta(minutes=CLAIM_TOKEN_TTL_MINUTES)


class PassengerService:
    """Business logic for Transport passengers/participants."""

    # ------------------------------------------------------------------
    # Add passenger
    # ------------------------------------------------------------------

    def add_passenger(
        self,
        booking: Booking,
        *,
        name: Optional[str] = None,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        user_id: Optional[int] = None,
        seat_label: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **_,
    ) -> TransportPassenger:
        """Add one passenger to a booking.

        A passenger may be accountless (no user_id) or linked to a User.
        Never auto-creates a User for a passenger record.
        """
        if booking.is_deleted:
            raise NotFoundError("Booking not found", resource_type="booking", resource_id=booking.id)

        if not (name or email or phone or user_id):
            raise ValidationError(
                message="Passenger must have a name, email, phone, or linked user"
            )

        passenger = TransportPassenger(
            booking_id=booking.id,
            user_id=user_id,
            name=name,
            email=email,
            phone=phone,
            seat_label=seat_label,
            passenger_metadata=metadata or {},
        )
        if user_id is not None:
            passenger.status = PassengerStatus.LINKED
        db.session.add(passenger)
        db.session.flush()
        self._sync_booking_passenger_count(booking)

        audit_log(
            action="transport_passenger_added",
            resource_type="transport_passenger",
            resource_id=passenger.id,
            user_id=user_id,
            details={"booking_id": booking.id, "accountless": user_id is None},
        )
        return passenger

    def bulk_add_passengers(self, booking: Booking, passengers: List[Dict[str, Any]]) -> List[TransportPassenger]:
        """Add multiple passengers (group / coordinator flow)."""
        created = []
        for row in passengers:
            created.append(
                self.add_passenger(
                    booking,
                    name=row.get("name"),
                    email=row.get("email"),
                    phone=row.get("phone"),
                    user_id=row.get("user_id"),
                    seat_label=row.get("seat_label"),
                    metadata=row.get("metadata"),
                )
            )
        db.session.flush()
        return created

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_passenger(self, passenger_id: int) -> TransportPassenger:
        p = db.session.get(TransportPassenger, passenger_id)
        if not p or p.is_deleted:
            raise NotFoundError(
                "Passenger not found", resource_type="transport_passenger", resource_id=passenger_id
            )
        return p

    def passengers_for_booking(self, booking_id: int, include_cancelled: bool = False):
        query = TransportPassenger.query.filter(
            TransportPassenger.booking_id == booking_id,
            TransportPassenger.is_deleted == False,
        )
        if not include_cancelled:
            query = query.filter(TransportPassenger.status != PassengerStatus.CANCELLED)
        return query.order_by(TransportPassenger.created_at.asc()).all()

    def active_passenger_count(self, booking_id: int) -> int:
        return len(self.passengers_for_booking(booking_id))

    def serialize(self, passenger: TransportPassenger) -> Dict[str, Any]:
        """API-safe representation (public_id only - never exposes internal ids)."""
        return {
            "public_id": passenger.public_id,
            "status": str(passenger.status.value) if passenger.status else None,
            "name": passenger.name,
            "email": passenger.email,
            "phone": passenger.phone,
            "seat_label": passenger.seat_label,
            "is_accountless": passenger.user_id is None,
            "is_claimed": passenger.claimed_by_user_id is not None,
            "booking_public_id": (
                passenger.booking.booking_reference if passenger.booking else None
            ),
            "assigned_vehicle_public_id": (
                getattr(passenger.assigned_vehicle, "license_plate", None)
                if passenger.assigned_vehicle else None
            ),
            "created_at": passenger.created_at.isoformat() if passenger.created_at else None,
        }

    # ------------------------------------------------------------------
    # Assignment (multi-vehicle / group) with capacity enforcement
    # ------------------------------------------------------------------

    def assign_vehicle(
        self,
        passenger: TransportPassenger,
        vehicle: Vehicle,
        booking: Optional[Booking] = None,
    ):
        """Assign a passenger to a vehicle / booking, enforcing capacity."""
        if passenger.is_deleted:
            raise NotFoundError("Passenger not found", resource_type="transport_passenger",
                                resource_id=passenger.id)
        if vehicle.is_deleted:
            raise NotFoundError("Vehicle not found", resource_type="vehicle", resource_id=vehicle.id)

        self._check_capacity(vehicle, passenger=passenger, target_booking=booking or passenger.booking)

        passenger.assigned_vehicle_id = vehicle.id
        passenger.status = PassengerStatus.ASSIGNED
        if booking is not None:
            passenger.booking_id = booking.id
        db.session.flush()
        audit_log(
            action="transport_passenger_assigned_vehicle",
            resource_type="transport_passenger",
            resource_id=passenger.id,
            user_id=passenger.user_id,
            details={"vehicle_id": vehicle.id, "booking_id": passenger.booking_id},
        )
        return passenger

    def _check_capacity(
        self,
        vehicle: Vehicle,
        *,
        passenger: Optional[TransportPassenger] = None,
        target_booking: Optional[Booking] = None,
    ):
        """Reject over-capacity assignment. Capacity is a Transport concern."""
        capacity = vehicle.passenger_capacity or vehicle.max_passenger_capacity or 0
        if capacity <= 0:
            raise ValidationError(
                message="Vehicle has no defined passenger capacity"
            )

        currently = TransportPassenger.query.filter(
            TransportPassenger.assigned_vehicle_id == vehicle.id,
            TransportPassenger.is_deleted == False,
            TransportPassenger.status != PassengerStatus.CANCELLED,
        ).count()

        # If this passenger is already assigned to this vehicle, don't double count.
        dedup = 1 if (passenger is not None
                      and passenger.assigned_vehicle_id == vehicle.id
                      and passenger.status != PassengerStatus.CANCELLED) else 0
        required = currently - dedup + 1

        if required > capacity:
            raise ValidationError(
                message=f"Vehicle '{vehicle.license_plate}' is at capacity "
                        f"({capacity} passengers already assigned)"
            )

        if target_booking is not None:
            assigned_now = TransportPassenger.query.filter(
                TransportPassenger.booking_id == target_booking.id,
                TransportPassenger.is_deleted == False,
                TransportPassenger.status != PassengerStatus.CANCELLED,
                TransportPassenger.assigned_vehicle_id.isnot(None),
            ).count()
            dedup_self = 1 if (
                passenger is not None
                and passenger.booking_id == target_booking.id
                and passenger.assigned_vehicle_id is not None
            ) else 0
            after_assignment = assigned_now - dedup_self + 1
            if target_booking.passenger_count and after_assignment > target_booking.passenger_count:
                raise ValidationError(
                    message=f"Booking allows at most {target_booking.passenger_count} passengers"
                )

    def reassign_passenger(self, passenger_id: int, new_booking: Booking, vehicle: Optional[Vehicle] = None):
        """Move a passenger to another booking (multi-vehicle coordination)."""
        passenger = self.get_passenger(passenger_id)
        passenger.booking_id = new_booking.id
        if vehicle is not None:
            return self.assign_vehicle(passenger, vehicle, booking=new_booking)
        db.session.flush()
        return passenger

    # ------------------------------------------------------------------
    # Secure claim / link
    # ------------------------------------------------------------------

    def create_claim_token(self, passenger: TransportPassenger,
                           ttl: timedelta = DEFAULT_CLAIM_TTL) -> str:
        """Issue a short-lived, single-use, unguessable claim token.

        The token is bound to the specific passenger (never grants rights to
        any other passenger). It is stored only as a SHA-256 hash.
        """
        if passenger.is_deleted:
            raise NotFoundError("Passenger not found", resource_type="transport_passenger",
                                resource_id=passenger.id)
        if not (passenger.email or passenger.phone):
            raise ValidationError(
                message="Cannot issue a claim without an email or phone to bind to"
            )

        token = secrets.token_urlsafe(32)
        passenger.claim_token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        passenger.claim_token_expires_at = datetime.now(timezone.utc) + ttl
        passenger.claim_token_consumed_at = None
        db.session.flush()
        return token

    def validate_claim_token(self, passenger_public_id: str, token: str,
                             expected_email: Optional[str] = None,
                             expected_phone: Optional[str] = None) -> TransportPassenger:
        """Validate a claim token. Single-purpose security check.

        The passenger is resolved by public_id (the value embedded in the shared
        claim link) so the internal database id is never exposed outside the
        transport module's protected management endpoints.
        """
        passenger = TransportPassenger.query.filter_by(
            public_id=passenger_public_id, is_deleted=False
        ).first()
        if not passenger:
            raise NotFoundError("Passenger not found", resource_type="transport_passenger",
                                resource_id=passenger_public_id)

        if not passenger.claim_token_hash:
            raise PermissionError("No claim token issued for this passenger")

        supplied = hashlib.sha256(token.encode("utf-8")).hexdigest()
        if not secrets.compare_digest(supplied, passenger.claim_token_hash):
            raise PermissionError("Invalid claim token")

        if passenger.claim_token_consumed_at is not None:
            raise PermissionError("Claim token has already been used")

        expires_at = passenger.claim_token_expires_at
        if expires_at is None or expires_at < datetime.now(timezone.utc):
            raise ValidationError("Claim token has expired")

        if expected_email and passenger.email and passenger.email.lower() != expected_email.lower():
            raise PermissionError("Claim token is not valid for this recipient")
        if expected_phone and passenger.phone and passenger.phone != expected_phone:
            raise PermissionError("Claim token is not valid for this recipient")

        return passenger

    def claim_with_token(self, passenger_public_id: str, token: str, user) -> TransportPassenger:
        """Link an accountless passenger to the authenticated User using a valid token."""
        passenger = self.validate_claim_token(
            passenger_public_id, token,
            expected_email=getattr(user, "email", None),
            expected_phone=getattr(user, "phone", None),
        )

        if passenger.user_id is not None and passenger.user_id != user.id:
            # A passenger can only ever be linked to ONE user.
            raise PermissionError("This passenger is already linked to another account")

        passenger.link_to_user(user)
        passenger.claimed_by_user_id = user.id
        passenger.claimed_at = datetime.now(timezone.utc)
        passenger.claim_token_consumed_at = datetime.now(timezone.utc)
        passenger.claim_token_hash = None  # single-use -> invalidate
        passenger.claim_token_expires_at = None
        db.session.flush()

        audit_log(
            action="transport_passenger_claimed",
            resource_type="transport_passenger",
            resource_id=passenger.id,
            user_id=user.id,
            details={"booking_id": passenger.booking_id, "linked": True},
        )
        return passenger

    def link_passenger(self, passenger_id: int, user) -> TransportPassenger:
        """Link a passenger to the current authenticated user (idempotent).

        Used when the booker coordinates a passenger that corresponds to the
        authenticated user, or a direct (already-authorized) link.
        """
        passenger = self.get_passenger(passenger_id)
        if passenger.user_id is not None and passenger.user_id != user.id:
            raise PermissionError("Passenger already linked to another account")
        passenger.link_to_user(user)
        db.session.flush()
        return passenger

    # ------------------------------------------------------------------
    # Group helpers
    # ------------------------------------------------------------------

    def mark_group(self, booking: Booking, group_booking_id: str, leader_user_id: int):
        booking.is_group_booking = True
        booking.group_booking_id = group_booking_id
        booking.group_leader_id = leader_user_id
        booking.group_size = self.active_passenger_count(int(booking.id))
        db.session.flush()

    def _sync_booking_passenger_count(self, booking: Booking):
        # Preserve an explicit booking passenger target; only auto-set when the
        # booking did not define one (e.g. passengers added to a skeleton booking).
        if not booking.passenger_count:
            booking.passenger_count = self.active_passenger_count(int(booking.id))
            db.session.flush()


# ------------------------------------------------------------------
# Singleton getter
# ------------------------------------------------------------------
from threading import Lock  # noqa: E402

_passenger_service_instance = None
_passenger_service_lock = Lock()


def get_passenger_service() -> PassengerService:
    global _passenger_service_instance
    if _passenger_service_instance is None:
        with _passenger_service_lock:
            if _passenger_service_instance is None:
                _passenger_service_instance = PassengerService()
    return _passenger_service_instance
