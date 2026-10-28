"""Durable request-first dispatch for AFCON360 on-demand rides.

A RideRequest owns the public reference until a driver wins. Offers and
matching history are persisted in SearchCycle / OfferAttempt. A Booking
is created only inside the successful acceptance transaction.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.extensions import db
from app.transport.models import (
    Booking, BookingStatus, ComplianceStatus, Currency, DriverProfile,
    OfferAttempt, PaymentStatus, ProviderType, RideRequest, SearchCycle,
    ServiceType, Vehicle,
)
from app.utils.exceptions import ValidationError

OFFER_RESPONSE_SECONDS = 15


class RideRequestDispatchError(Exception):
    """A stable, user-safe request dispatch/acceptance failure."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _location_text(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("display_name", "address", "name", "label", "formatted"):
            text = value.get(key)
            if isinstance(text, str) and text.strip():
                return text.strip()
    if isinstance(value, str):
        return value.strip()
    return "Location not available"


def _coordinates(value: Any) -> Dict[str, Optional[float]]:
    if not isinstance(value, dict):
        return {"latitude": None, "longitude": None}
    try:
        lat = float(value.get("latitude"))
        lng = float(value.get("longitude"))
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            raise ValueError("out of range")
        return {"latitude": lat, "longitude": lng}
    except (TypeError, ValueError):
        return {"latitude": None, "longitude": None}


class RideRequestDispatchService:
    """Create durable sequential offers and convert only after acceptance."""

    RESPONSE_SECONDS = OFFER_RESPONSE_SECONDS

    @staticmethod
    def _cycle_for_request(request: RideRequest, *, lock: bool = False) -> Optional[SearchCycle]:
        query = SearchCycle.query.filter_by(
            ride_request_id=request.id,
            is_deleted=False,
        ).order_by(SearchCycle.cycle_number.desc())
        if lock:
            query = query.with_for_update()
        return query.first()

    @staticmethod
    def _proxy(request: RideRequest):
        # MatchingService's existing ranker consumes only these request facts.
        return SimpleNamespace(
            id=request.id,
            booking_reference=request.public_id,
            pickup_location=request.pickup_location,
            dropoff_location=request.dropoff_location,
            service_type=request.service_type,
            passenger_count=request.passenger_count,
            booking_metadata={"vehicle_class": request.vehicle_class},
        )

    @staticmethod
    def _candidate_snapshot(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        safe = []
        for candidate in candidates:
            driver_id = candidate.get("driver_id")
            vehicle_id = candidate.get("vehicle_id")
            if not driver_id or not vehicle_id:
                continue
            safe.append({
                "driver_id": int(driver_id),
                "vehicle_id": int(vehicle_id),
                "match_score": int(candidate.get("match_score") or 0),
                "estimated_arrival_time": int(
                    candidate.get("estimated_arrival_time") or 15
                ),
            })
        return safe

    @staticmethod
    def _notify_driver(request: RideRequest, attempt: OfferAttempt) -> None:
        try:
            from app.transport.services.notification_service import NotificationService
            NotificationService.send_driver_notification(
                attempt.driver_id,
                "new_booking",
                {
                    "booking_reference": request.public_id,
                    "pickup_location": _location_text(request.pickup_location),
                    "dropoff_location": _location_text(request.dropoff_location),
                },
            )
        except Exception:
            # The durable attempt is authoritative; notification delivery is
            # best-effort and the driver poll endpoint can still discover it.
            import logging
            logging.getLogger(__name__).warning(
                "Ride-request offer notification failed for request %s / driver %s",
                request.public_id, attempt.driver_id, exc_info=True,
            )

    @classmethod
    def _insert_offer(cls, request: RideRequest, cycle: SearchCycle,
                      candidate: Dict[str, Any], attempt_number: int) -> OfferAttempt:
        now = _now()
        attempt = OfferAttempt(
            cycle_id=cycle.id,
            driver_id=int(candidate["driver_id"]),
            vehicle_id=int(candidate["vehicle_id"]),
            attempt_number=attempt_number,
            candidate_rank=int(candidate.get("rank") or attempt_number),
            status="offered",
            offered_at=now,
            response_deadline=now + timedelta(seconds=cls.RESPONSE_SECONDS),
            outcome_detail={
                "request_reference": request.public_id,
                "estimated_arrival_time": int(
                    candidate.get("estimated_arrival_time") or 15
                ),
            },
        )
        db.session.add(attempt)
        return attempt

    @classmethod
    def start_search(cls, request_public_id: str) -> Dict[str, Any]:
        """Create the first durable single-driver offer, idempotently."""
        from app.transport.services.matching_service import MatchingService

        request = RideRequest.query.filter_by(
            public_id=request_public_id, is_deleted=False
        ).with_for_update().first()
        if request is None:
            raise RideRequestDispatchError("request_not_found", "Ride request not found")
        if request.status == "converted":
            return {"status": "converted", "request_reference": request.public_id}
        if request.status != "searching":
            return {"status": request.status, "request_reference": request.public_id}

        cycle = cls._cycle_for_request(request, lock=True)
        if cycle is None or cycle.status != "searching":
            return {"status": "no_active_search", "request_reference": request.public_id}

        active = OfferAttempt.query.filter(
            OfferAttempt.cycle_id == cycle.id,
            OfferAttempt.status.in_(("offered", "accepting")),
        ).first()
        if active is not None:
            if active.status == "offered" and active.response_deadline and active.response_deadline > _now():
                return {"status": "offered", "request_reference": request.public_id}
            if active.status == "accepting":
                return {"status": "accepting", "request_reference": request.public_id}
            cls._advance_locked(request, cycle, active, "timed_out")
            db.session.commit()
            return {"status": cycle.status, "request_reference": request.public_id}

        # First call snapshots the ranked candidate pool. Later retries and
        # recoveries advance this immutable snapshot rather than re-ranking.
        cycle_meta = dict(cycle.cycle_metadata or {})
        pool = cycle_meta.get("ranked_pool")
        if not isinstance(pool, list):
            proxy = cls._proxy(request)
            _, ranked = MatchingService._ranked_candidates(proxy)
            pool = cls._candidate_snapshot(ranked)
            for rank, candidate in enumerate(pool, start=1):
                candidate["rank"] = rank
            cycle_meta["ranked_pool"] = pool
            cycle_meta["pool_snapshotted_at"] = _now().isoformat()
            cycle.cycle_metadata = cycle_meta

        if not pool:
            cycle.status = "expired"
            cycle.terminal_reason = "no_supply"
            cycle.completed_at = _now()
            db.session.commit()
            return {"status": "no_supply", "request_reference": request.public_id}

        attempt = cls._insert_offer(request, cycle, pool[0], 1)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            # The partial unique index is authoritative under duplicate calls.
            current = cls._cycle_for_request(request)
            active = OfferAttempt.query.filter(
                OfferAttempt.cycle_id == current.id,
                OfferAttempt.status.in_(("offered", "accepting")),
            ).first() if current else None
            if active:
                return {"status": active.status, "request_reference": request_public_id}
            raise
        cls._notify_driver(request, attempt)
        return {
            "status": "offered",
            "request_reference": request.public_id,
            "deadline": attempt.response_deadline.isoformat(),
        }

    @staticmethod
    def list_driver_offers(driver_id: int) -> List[Dict[str, Any]]:
        """Driver-safe offer payload; no internal database identifiers."""
        now = _now()
        attempts = (
            OfferAttempt.query.join(SearchCycle, OfferAttempt.cycle_id == SearchCycle.id)
            .join(RideRequest, SearchCycle.ride_request_id == RideRequest.id)
            .filter(
                OfferAttempt.driver_id == driver_id,
                OfferAttempt.status == "offered",
                OfferAttempt.response_deadline > now,
                SearchCycle.status == "searching",
                RideRequest.status == "searching",
                RideRequest.is_deleted.is_(False),
            )
            .order_by(OfferAttempt.offered_at.asc())
            .all()
        )
        offers = []
        for attempt in attempts:
            cycle = attempt.cycle
            request = cycle.ride_request if cycle else None
            if request is None:
                continue
            vehicle = attempt.vehicle
            pickup = request.pickup_location
            dropoff = request.dropoff_location
            estimate_meta = (request.request_metadata or {}).get("fare_estimate") or {}
            deadline = attempt.response_deadline
            offers.append({
                "booking_reference": request.public_id,
                "status": "offered",
                "expires_at": int(deadline.timestamp()) if deadline else 0,
                "ttl_remaining": max(0, int((deadline - now).total_seconds())) if deadline else 0,
                "pickup": {"text": _location_text(pickup), **_coordinates(pickup)},
                "destination": {"text": _location_text(dropoff), **_coordinates(dropoff)},
                "fare_estimate": {
                    "amount": float(request.fare_estimate_amount or 0),
                    "currency": request.currency_code or estimate_meta.get("currency"),
                },
                "ride_class": request.vehicle_class,
                "service_type": str(getattr(request.service_type, "value", request.service_type)),
                "passenger_count": int(request.passenger_count or 1),
                "vehicle": ({
                    "license_plate": vehicle.license_plate,
                    "make": vehicle.make,
                    "model": vehicle.model,
                    "vehicle_class": str(getattr(vehicle.vehicle_class, "value", vehicle.vehicle_class)),
                } if vehicle else None),
                "distance_km": (request.request_metadata or {}).get("distance_km"),
                "distance_basis": (request.request_metadata or {}).get("distance_basis"),
            })
        return offers

    @classmethod
    def _advance_locked(cls, request: RideRequest, cycle: SearchCycle,
                        attempt: OfferAttempt, outcome: str) -> Optional[OfferAttempt]:
        now = _now()
        attempt.status = outcome
        attempt.responded_at = now
        detail = dict(attempt.outcome_detail or {})
        detail["terminal_at"] = now.isoformat()
        attempt.outcome_detail = detail

        meta = dict(cycle.cycle_metadata or {})
        pool = meta.get("ranked_pool") if isinstance(meta.get("ranked_pool"), list) else []
        previous = OfferAttempt.query.filter_by(cycle_id=cycle.id).all()
        used = {int(row.driver_id) for row in previous}
        candidate = next(
            (item for item in pool
             if isinstance(item, dict)
             and item.get("driver_id") is not None
             and int(item["driver_id"]) not in used
             and item.get("vehicle_id") is not None),
            None,
        )
        if candidate is None:
            cycle.status = "expired"
            cycle.terminal_reason = "all_rejected" if previous else "no_supply"
            cycle.completed_at = now
            return None

        next_number = max((int(row.attempt_number or 0) for row in previous), default=0) + 1
        return cls._insert_offer(request, cycle, candidate, next_number)

    @classmethod
    def decline_offer(cls, request_public_id: str, driver_id: int) -> bool:
        request = RideRequest.query.filter_by(
            public_id=request_public_id, is_deleted=False
        ).with_for_update().first()
        if request is None or request.status != "searching":
            return False
        cycle = cls._cycle_for_request(request, lock=True)
        if cycle is None or cycle.status != "searching":
            return False
        attempt = OfferAttempt.query.filter_by(
            cycle_id=cycle.id, driver_id=driver_id, status="offered"
        ).with_for_update().first()
        if attempt is None:
            return False
        next_attempt = cls._advance_locked(request, cycle, attempt, "declined")
        db.session.commit()
        if next_attempt:
            cls._notify_driver(request, next_attempt)
        return True

    @classmethod
    def recover_expired(cls, batch: int = 100) -> Dict[str, int]:
        """Advance expired attempts, called by the normal transport recovery beat."""
        now = _now()
        rows = (
            OfferAttempt.query.filter(
                OfferAttempt.status == "offered",
                OfferAttempt.response_deadline.is_not(None),
                OfferAttempt.response_deadline <= now,
            )
            .order_by(OfferAttempt.response_deadline.asc())
            .limit(batch)
            .all()
        )
        expired = advanced = closed = 0
        for row in rows:
            try:
                request = row.cycle.ride_request if row.cycle else None
                if request is None:
                    continue
                locked_request = RideRequest.query.filter_by(
                    id=request.id, is_deleted=False
                ).with_for_update().first()
                if locked_request is None or locked_request.status != "searching":
                    continue
                cycle = cls._cycle_for_request(locked_request, lock=True)
                attempt = OfferAttempt.query.filter_by(
                    id=row.id, status="offered"
                ).with_for_update().first()
                if cycle is None or cycle.status != "searching" or attempt is None:
                    db.session.rollback()
                    continue
                if attempt.response_deadline and attempt.response_deadline > _now():
                    db.session.rollback()
                    continue
                next_attempt = cls._advance_locked(locked_request, cycle, attempt, "timed_out")
                db.session.commit()
                expired += 1
                if next_attempt:
                    cls._notify_driver(locked_request, next_attempt)
                    advanced += 1
                else:
                    closed += 1
            except Exception:
                db.session.rollback()
                import logging
                logging.getLogger(__name__).exception(
                    "Ride-request offer expiry recovery failed for attempt %s", row.id
                )
        return {"expired": expired, "advanced": advanced, "closed": closed}

    @classmethod
    def accept_offer(cls, request_public_id: str, driver_id: int,
                     vehicle_id: int, *, actor=None) -> Dict[str, Any]:
        """Atomically convert a request to a Booking only after acceptance.

        The request, cycle, winning offer, Booking, driver and vehicle all
        commit together. If any eligibility/availability guard fails, the
        Booking insert and lifecycle conversion roll back together.
        """
        from app.transport.services.assignment_service import (
            AssignmentService, DispatchClaimError,
        )

        now = _now()
        request = RideRequest.query.filter_by(
            public_id=request_public_id, is_deleted=False
        ).with_for_update().first()
        if request is None:
            raise RideRequestDispatchError("request_not_found", "Ride request not found")
        if request.status == "converted":
            raise RideRequestDispatchError("already_accepted", "Another driver already accepted this ride")
        if request.status != "searching":
            raise RideRequestDispatchError("request_not_searchable", "This ride request is no longer available")

        cycle = cls._cycle_for_request(request, lock=True)
        if cycle is None or cycle.status != "searching":
            raise RideRequestDispatchError("offer_unavailable", "This ride offer is no longer active")
        attempt = OfferAttempt.query.filter_by(
            cycle_id=cycle.id, driver_id=driver_id, status="offered"
        ).with_for_update().first()
        if attempt is None or attempt.vehicle_id != vehicle_id:
            raise RideRequestDispatchError("offer_unavailable", "This driver has no active offer for the ride")
        if attempt.response_deadline is None or attempt.response_deadline <= now:
            next_attempt = cls._advance_locked(request, cycle, attempt, "timed_out")
            db.session.commit()
            if next_attempt:
                cls._notify_driver(request, next_attempt)
            raise RideRequestDispatchError("offer_expired", "This ride offer has expired")

        # Mark in-flight under the request/cycle row locks; the state is
        # committed only together with the booking conversion below.
        request.status = "converting"
        cycle.status = "converting"
        attempt.status = "accepting"
        attempt.responded_at = now

        amount = Decimal(str(request.fare_estimate_amount or "0")).quantize(Decimal("0.01"))
        currency_code = str(request.currency_code or "USD").upper()
        try:
            currency = Currency(currency_code)
        except ValueError as exc:
            db.session.rollback()
            raise RideRequestDispatchError("invalid_currency", "The quoted fare currency is not supported") from exc

        metadata = request.request_metadata or {}
        booking_mode = str(metadata.get("booking_mode") or "instant").lower()
        pickup_time = request.requested_pickup_time or now
        booking = Booking(
            booking_reference=request.public_id,
            user_id=request.user_id,
            provider_type=ProviderType.INDIVIDUAL_DRIVER,
            service_type=request.service_type,
            pickup_location=request.pickup_location,
            dropoff_location=request.dropoff_location,
            pickup_address=_location_text(request.pickup_location),
            dropoff_address=_location_text(request.dropoff_location),
            pickup_time=pickup_time,
            pickup_mode=booking_mode if booking_mode in ("instant", "scheduled") else "instant",
            request_received_at=request.created_at or now,
            passenger_count=int(request.passenger_count or 1),
            luggage_count=0,
            base_price=amount,
            subtotal=amount,
            total_amount=amount,
            final_price=amount,
            currency=currency,
            payment_method=request.payment_method,
            payment_status=PaymentStatus.PENDING,
            status=BookingStatus.CONFIRMED,
            confirmed_at=now,
            service_subtype=request.vehicle_class,
            ride_request_id=request.id,
            search_cycle_id=cycle.id,
            booking_metadata={
                "vehicle_class": request.vehicle_class,
                "booking_mode": booking_mode,
                "fare_version": metadata.get("fare_version"),
                "fare_effective_from": metadata.get("fare_effective_from"),
                "distance_km": metadata.get("distance_km"),
                "distance_basis": metadata.get("distance_basis"),
                "trip_fingerprint": metadata.get("trip_hash"),
                "payment_timing": "pay_on_completion",
                "ride_request_public_id": request.public_id,
            },
        )
        db.session.add(booking)
        try:
            db.session.flush()
            result = AssignmentService.claim(
                request.public_id, driver_id, vehicle_id,
                actor=actor, commit=False,
            )
            attempt.status = "won"
            attempt.outcome_detail = {
                **(attempt.outcome_detail or {}),
                "accepted_at": now.isoformat(),
                "booking_created": True,
            }
            for other in OfferAttempt.query.filter(
                OfferAttempt.cycle_id == cycle.id,
                OfferAttempt.id != attempt.id,
                OfferAttempt.status.in_(("offered", "accepting")),
            ).all():
                other.status = "skipped"
                other.responded_at = now
                other.outcome_detail = {
                    **(other.outcome_detail or {}),
                    "reason": "another_driver_won",
                    "at": now.isoformat(),
                }
            cycle.status = "completed"
            cycle.completed_at = now
            cycle.terminal_reason = None
            request.status = "converted"
            request.converted_at = now
            db.session.commit()
        except (DispatchClaimError, IntegrityError, SQLAlchemyError) as exc:
            db.session.rollback()
            import logging
            logging.getLogger(__name__).warning(
                "Ride-request conversion failed for %s: %s", request_public_id, exc
            )
            # Keep the request trackable and allow the next eligible driver;
            # the failed Booking insert was rolled back with the claim.
            locked_request = RideRequest.query.filter_by(
                public_id=request_public_id, is_deleted=False
            ).with_for_update().first()
            if locked_request is not None and locked_request.status == "searching":
                locked_cycle = cls._cycle_for_request(locked_request, lock=True)
                if locked_cycle and locked_cycle.status == "searching":
                    locked_attempt = OfferAttempt.query.filter_by(
                        cycle_id=locked_cycle.id, driver_id=driver_id,
                        status="offered",
                    ).with_for_update().first()
                    if locked_attempt:
                        next_attempt = cls._advance_locked(
                            locked_request, locked_cycle, locked_attempt, "claim_failed"
                        )
                        db.session.commit()
                        if next_attempt:
                            cls._notify_driver(locked_request, next_attempt)
                    else:
                        db.session.rollback()
            if isinstance(exc, DispatchClaimError):
                raise RideRequestDispatchError(exc.kind, exc.message) from exc
            raise RideRequestDispatchError(
                "assignment_conflict", "The driver or vehicle is no longer available. We are checking another driver."
            ) from exc

        # The caller sees success only after the entire conversion transaction
        # commits. Notifications/cache invalidation are best-effort side effects.
        try:
            AssignmentService._invalidate_booking_read_cache(result["booking_id"])
            AssignmentService._notify_assigned(request.user_id, result["booking_id"], request.public_id)
        except Exception:
            import logging
            logging.getLogger(__name__).warning(
                "Post-conversion rider notification failed for %s", request_public_id,
                exc_info=True,
            )
        return result
