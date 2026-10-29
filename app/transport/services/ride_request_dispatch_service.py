"""Durable request-first dispatch for AFCON360 on-demand rides.

A RideRequest owns the public reference until a driver wins. Offers and
matching history are persisted in SearchCycle / OfferAttempt. A Booking
is created only inside the successful acceptance transaction.
"""
from datetime import datetime, timedelta, timezone
import uuid
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.extensions import db
from app.transport.models import (
    Booking, BookingPayment, BookingStatus, ComplianceStatus, Currency,
    DriverProfile, DriverVehicleHistory, OfferAttempt, PaymentStatus,
    ProviderType, RideRequest, SearchCycle, ServiceType, Vehicle,
)
from app.utils.exceptions import ValidationError

OFFER_RESPONSE_SECONDS = 25


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
    def _close_cycle_at_deadline(
        cls, request: RideRequest, cycle: SearchCycle, now: Optional[datetime] = None,
    ) -> bool:
        """Close an elapsed matching window and withdraw its actionable offer.

        The request row must already be locked by the caller. This makes
        expiry mutually exclusive with acceptance and rider cancellation.
        Returns False when the window has not elapsed.
        """
        now = now or _now()
        if cycle.deadline is None or cycle.deadline > now:
            return False

        attempts = OfferAttempt.query.filter_by(cycle_id=cycle.id).with_for_update().all()
        had_attempts = bool(attempts)
        for attempt in attempts:
            if attempt.status in ("offered", "accepting"):
                attempt.status = "timed_out"
                attempt.responded_at = now
                attempt.outcome_detail = {
                    **(attempt.outcome_detail or {}),
                    "reason": "matching_window_expired",
                    "at": now.isoformat(),
                }
        cycle.status = "expired"
        cycle.terminal_reason = "all_rejected" if had_attempts else "no_supply"
        cycle.completed_at = now
        meta = dict(cycle.cycle_metadata or {})
        meta["window_expired_at"] = now.isoformat()
        cycle.cycle_metadata = meta
        return True

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
        if cls._close_cycle_at_deadline(request, cycle):
            db.session.commit()
            return {"status": "expired", "request_reference": request.public_id}

        active = OfferAttempt.query.filter(
            OfferAttempt.cycle_id == cycle.id,
            OfferAttempt.status.in_(("offered", "accepting")),
        ).first()
        if active is not None:
            if active.status == "offered" and active.response_deadline and active.response_deadline > _now():
                return {"status": "offered", "request_reference": request.public_id}
            if active.status == "accepting":
                return {"status": "accepting", "request_reference": request.public_id}
            next_attempt = cls._advance_locked(request, cycle, active, "timed_out")
            db.session.commit()
            if next_attempt:
                cls._notify_driver(request, next_attempt)
            return {"status": cycle.status, "request_reference": request.public_id}

        # First call snapshots the ranked candidate pool. Later retries and
        # recoveries advance this immutable snapshot rather than re-ranking.
        cycle_meta = dict(cycle.cycle_metadata or {})
        pool = cycle_meta.get("ranked_pool")
        if not isinstance(pool, list):
            proxy = cls._proxy(request)
            _, ranked = MatchingService._ranked_candidates(proxy)
            # Keep request-first matching aligned with the canonical MATCH-01
            # budget: five ranked drivers per cycle, not the ranker's wider
            # discovery pool. Retries create a new cycle and a fresh snapshot.
            pool = cls._candidate_snapshot(
                ranked[:MatchingService.MATCHING_POOL_SIZE]
            )
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
        if cls._close_cycle_at_deadline(request, cycle, now):
            return None
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
    def retry_search(cls, request_public_id: str, owner_user_id: int) -> Dict[str, Any]:
        """Open a new durable search cycle after a previous cycle exhausted."""
        from app.transport.services.matching_service import MatchingService

        request = RideRequest.query.filter_by(
            public_id=request_public_id, is_deleted=False
        ).with_for_update().first()
        if request is None or request.user_id != owner_user_id:
            raise RideRequestDispatchError("request_not_found", "Ride request not found")
        if request.status != "searching":
            raise RideRequestDispatchError(
                "request_not_retryable", "This ride request can no longer be retried"
            )

        current_cycle = cls._cycle_for_request(request, lock=True)
        if current_cycle is not None and current_cycle.status == "searching":
            if cls._close_cycle_at_deadline(request, current_cycle):
                db.session.commit()
                return {
                    "status": "expired",
                    "request_reference": request.public_id,
                }
            active = OfferAttempt.query.filter(
                OfferAttempt.cycle_id == current_cycle.id,
                OfferAttempt.status.in_(("offered", "accepting")),
            ).first()
            if active is not None:
                if active.status == "accepting":
                    raise RideRequestDispatchError(
                        "accept_in_progress", "A driver is currently accepting this ride"
                    )
                if active.response_deadline and active.response_deadline > _now():
                    return {"status": "offered", "request_reference": request.public_id}
                next_attempt = cls._advance_locked(
                    request, current_cycle, active, "timed_out"
                )
                db.session.commit()
                if next_attempt:
                    cls._notify_driver(request, next_attempt)
                return {
                    "status": current_cycle.status,
                    "request_reference": request.public_id,
                }

            # Search cycle exists but its first offer has not yet been created;
            # leave the same cycle and let start_search resume it.
            db.session.commit()
            return cls.start_search(request.public_id)

        if current_cycle is not None and current_cycle.status not in ("expired", "cancelled"):
            raise RideRequestDispatchError(
                "request_not_retryable", "This ride request is not awaiting a retry"
            )

        number = (current_cycle.cycle_number + 1) if current_cycle else 1
        now = _now()
        cycle = SearchCycle(
            ride_request_id=request.id,
            cycle_number=number,
            cycle_key="%s:%s" % (request.idempotency_key, number),
            status="searching",
            started_at=now,
            deadline=now + timedelta(seconds=MatchingService._matching_window_seconds()),
            cycle_metadata={},
        )
        meta = dict(request.request_metadata or {})
        meta["retry_count"] = int(meta.get("retry_count") or 0) + 1
        meta["last_retry_at"] = now.isoformat()
        request.request_metadata = meta
        db.session.add(cycle)
        db.session.commit()
        return cls.start_search(request.public_id)

    @classmethod
    def cancel_request(cls, request_public_id: str, owner_user_id: int) -> Dict[str, Any]:
        """Close a still-searching request without creating a Booking."""
        now = _now()
        request = RideRequest.query.filter_by(
            public_id=request_public_id, is_deleted=False
        ).with_for_update().first()
        if request is None or request.user_id != owner_user_id:
            raise RideRequestDispatchError("request_not_found", "Ride request not found")
        if request.status == "converted":
            raise RideRequestDispatchError(
                "already_assigned",
                "A driver has already accepted this ride. Use the trip cancellation flow instead.",
            )
        if request.status == "cancelled":
            return {"status": "cancelled", "request_reference": request.public_id,
                    "idempotent_replay": True}
        if request.status != "searching":
            raise RideRequestDispatchError(
                "request_not_cancellable", "This ride request can no longer be cancelled"
            )

        cycle = cls._cycle_for_request(request, lock=True)
        if cycle is not None and cycle.status == "searching":
            active_attempts = OfferAttempt.query.filter(
                OfferAttempt.cycle_id == cycle.id,
                OfferAttempt.status.in_(("offered", "accepting")),
            ).with_for_update().all()
            # An accepting offer is still inside the winning acceptance
            # transaction. The request row lock serializes this decision;
            # after it is acquired, a successfully committed acceptance would
            # already have changed request.status to converted.
            for attempt in active_attempts:
                attempt.status = "withdrawn"
                attempt.responded_at = now
                attempt.outcome_detail = {
                    **(attempt.outcome_detail or {}),
                    "reason": "rider_cancelled",
                    "at": now.isoformat(),
                }
            cycle.status = "cancelled"
            cycle.completed_at = now
            cycle.terminal_reason = "rider_cancelled"

        request.status = "cancelled"
        request.cancelled_at = now
        meta = dict(request.request_metadata or {})
        meta["cancelled_at"] = now.isoformat()
        meta["cancelled_by"] = "rider"
        request.request_metadata = meta
        db.session.commit()
        return {"status": "cancelled", "request_reference": request.public_id}

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
        """Recover expired offers/windows and searches with no first offer.

        Each row is revalidated under the parent request lock. The bounded
        queries prioritize stale attempts and, separately, only requests whose
        current active cycle has no attempts, so old active searches cannot
        starve newly committed requests after the first batch.
        """
        now = _now()
        rows = (
            OfferAttempt.query
            .join(SearchCycle, OfferAttempt.cycle_id == SearchCycle.id)
            .filter(
                OfferAttempt.status == "offered",
                or_(
                    OfferAttempt.response_deadline <= now,
                    SearchCycle.deadline <= now,
                ),
            )
            .order_by(SearchCycle.deadline.asc(), OfferAttempt.response_deadline.asc())
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
                    db.session.rollback()
                    continue

                cycle = cls._cycle_for_request(locked_request, lock=True)
                if cycle is None or cycle.status != "searching":
                    db.session.rollback()
                    continue
                # A row from an older cycle must never advance the current cycle.
                attempt = OfferAttempt.query.filter_by(
                    id=row.id, cycle_id=cycle.id, status="offered"
                ).with_for_update().first()
                if attempt is None:
                    db.session.rollback()
                    continue

                current_time = _now()
                if cls._close_cycle_at_deadline(locked_request, cycle, current_time):
                    db.session.commit()
                    expired += 1
                    closed += 1
                    continue

                if attempt.response_deadline and attempt.response_deadline > current_time:
                    db.session.rollback()
                    continue
                next_attempt = cls._advance_locked(
                    locked_request, cycle, attempt, "timed_out"
                )
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

        # Only scan active cycles that have no OfferAttempt at all. The previous
        # request-only LIMIT could repeatedly read the same old active requests
        # and starve newer requests whose initial offer was never persisted.
        try:
            requests = (
                db.session.query(RideRequest)
                .join(SearchCycle, SearchCycle.ride_request_id == RideRequest.id)
                .outerjoin(OfferAttempt, OfferAttempt.cycle_id == SearchCycle.id)
                .filter(
                    RideRequest.status == "searching",
                    RideRequest.is_deleted.is_(False),
                    SearchCycle.status == "searching",
                    SearchCycle.is_deleted.is_(False),
                    OfferAttempt.id.is_(None),
                )
                .order_by(RideRequest.created_at.asc())
                .limit(batch)
                .all()
            )
            for request in requests:
                try:
                    cls.start_search(request.public_id)
                except Exception:
                    db.session.rollback()
                    import logging
                    logging.getLogger(__name__).exception(
                        "Request-first dispatch recovery failed for %s",
                        request.public_id,
                    )
        except Exception:
            db.session.rollback()
            import logging
            logging.getLogger(__name__).exception(
                "Request-first search recovery scan failed"
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
        if cls._close_cycle_at_deadline(request, cycle, now):
            db.session.commit()
            raise RideRequestDispatchError(
                "matching_window_expired",
                "This matching window has expired. The rider can try finding a driver again.",
            )
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

        # The offered vehicle must still be the active driver/vehicle pairing.
        # A driver may switch vehicles while an offer is on screen; do not let
        # an old offer claim the previous vehicle merely because it is still
        # active and unoccupied.
        active_pair = DriverVehicleHistory.query.filter_by(
            driver_id=driver_id,
            vehicle_id=vehicle_id,
            ended_at=None,
            is_deleted=False,
        ).first()
        if active_pair is None:
            next_attempt = cls._advance_locked(
                request, cycle, attempt, "claim_failed"
            )
            db.session.commit()
            if next_attempt:
                cls._notify_driver(request, next_attempt)
            raise RideRequestDispatchError(
                "vehicle_assignment_changed",
                "Your active vehicle changed after this offer. We are checking another driver.",
            )

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
        raw_invoice_id = metadata.get("wallet_invoice_id")
        wallet_invoice_uuid = None
        if raw_invoice_id:
            try:
                wallet_invoice_uuid = uuid.UUID(str(raw_invoice_id))
                from app.wallet.services.marketplace_invoice_service import (
                    MarketplaceInvoiceService,
                )
                invoice = MarketplaceInvoiceService.get_invoice(
                    wallet_invoice_uuid, for_update=True
                )
            except (ValueError, TypeError) as exc:
                raise RideRequestDispatchError(
                    "wallet_invoice_invalid",
                    "This ride has an invalid Wallet invoice reference.",
                ) from exc
            except Exception as exc:
                raise RideRequestDispatchError(
                    "wallet_invoice_unavailable",
                    "Wallet could not validate the ride invoice. Please retry.",
                ) from exc
            if (
                invoice.service_code != "transport"
                or invoice.service_reference != request.public_id
                or int(invoice.payer_user_id) != int(request.user_id)
                or Decimal(str(invoice.amount)).quantize(Decimal("0.01"))
                    != Decimal(str(request.fare_estimate_amount)).quantize(Decimal("0.01"))
                or str(invoice.currency).upper() != str(request.currency_code).upper()
                or str(invoice.payment_method).lower() != str(request.payment_method).lower()
                or invoice.status != "pending"
            ):
                raise RideRequestDispatchError(
                    "wallet_invoice_mismatch",
                    "This ride's Wallet invoice does not match its confirmed fare and payment choice.",
                )
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
                "wallet_invoice_id": str(wallet_invoice_uuid) if wallet_invoice_uuid else None,
                "wallet_invoice_status": "pending" if wallet_invoice_uuid else None,
            },
        )
        db.session.add(booking)
        try:
            db.session.flush()
            # The existing transport payment index is the admin/reconciliation
            # surface. Record the pending obligation in the same transaction as
            # conversion and assignment, so a visible Booking cannot be missing
            # its corresponding payment lifecycle row.
            payment_record = BookingPayment.query.filter_by(
                booking_id=booking.id
            ).with_for_update().first()
            if payment_record is None:
                payment_record = BookingPayment(
                    booking_id=booking.id,
                    payment_reference="",
                    amount=amount,
                    currency=currency,
                    payment_method=request.payment_method,
                    payment_method_details={
                        "timing": "pay_on_completion",
                        "request_reference": request.public_id,
                        "wallet_invoice_id": str(wallet_invoice_uuid) if wallet_invoice_uuid else None,
                    },
                    wallet_invoice_id=wallet_invoice_uuid,
                    payment_status=PaymentStatus.PENDING,
                    initiated_at=now,
                )
                payment_record.generate_payment_reference()
                db.session.add(payment_record)
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
