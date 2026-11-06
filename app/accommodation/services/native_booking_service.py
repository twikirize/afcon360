"""Bearer-native accommodation discovery, quote, booking and cancellation.

This module is a thin API orchestration layer. Availability, pricing, booking
state, inventory, wallet escrow, commissions and refunds remain owned by the
existing accommodation and wallet services.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import or_

from flask import current_app, request

from app.extensions import db


class NativeAccommodationError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class NativeAccommodationService:
    QUOTE_MAX_AGE_SECONDS = 600
    QUOTE_VERSION = 1

    @staticmethod
    def _serializer():
        if not current_app.secret_key:
            raise NativeAccommodationError(
                "accommodation_unavailable",
                "AFCON360 cannot securely prepare a booking quote right now.",
                503,
            )
        return URLSafeTimedSerializer(
            current_app.secret_key,
            salt="afcon360-native-accommodation-quote-v1",
        )

    @classmethod
    def _room_type_serializer(cls):
        if not current_app.secret_key:
            raise NativeAccommodationError(
                "accommodation_unavailable",
                "AFCON360 cannot securely prepare room selections right now.",
                503,
            )
        return URLSafeTimedSerializer(
            current_app.secret_key,
            salt="afcon360-native-accommodation-room-type-v1",
        )

    @classmethod
    def _room_type_token(cls, prop, room):
        return cls._room_type_serializer().dumps({
            "property_public_id": str(prop.public_id),
            "room_type_id": int(room.id),
        })

    @classmethod
    def _load_room_type_token(cls, prop, token):
        try:
            payload = cls._room_type_serializer().loads(
                str(token or ""),
                max_age=24 * 60 * 60,
            )
        except SignatureExpired as exc:
            raise NativeAccommodationError(
                "room_selection_expired",
                "This room selection has expired. Reload the property and choose a room again.",
                409,
            ) from exc
        except BadSignature as exc:
            raise NativeAccommodationError(
                "room_selection_invalid",
                "This room selection is invalid. Reload the property and choose a room again.",
                400,
            ) from exc
        if payload.get("property_public_id") != str(prop.public_id):
            raise NativeAccommodationError(
                "room_selection_property_mismatch",
                "This room selection does not belong to the selected property.",
                403,
            )
        from app.accommodation.models.room import RoomType
        room = RoomType.query.filter_by(
            id=payload.get("room_type_id"),
            property_id=prop.id,
            is_active=True,
        ).first()
        if room is None:
            raise NativeAccommodationError(
                "room_type_unavailable",
                "This room type is no longer available at the selected property.",
                409,
            )
        return room

    @classmethod
    def _public_property(cls, prop, include_description=False):
        room_types = [
            {
                "room_token": cls._room_type_token(prop, room),
                "name": room.name,
                "description": room.description,
                "max_guests": int(room.max_guests or 1),
                "bedrooms": int(room.bedrooms or 0),
                "beds": int(room.beds or 0),
                "bathrooms": float(room.bathrooms or 0),
                "base_price_per_night": str(room.base_price_per_night),
                "currency": str(room.currency or prop.currency or "USD").upper(),
                "total_units": int(room.total_units or 0),
            }
            for room in (prop.room_types or [])
            if room.is_active
        ]
        data = {
            "public_id": str(prop.public_id),
            "title": prop.title,
            "summary": prop.summary or (prop.description or "")[:320],
            "city": prop.city,
            "state": prop.state,
            "country": prop.country,
            "address": prop.full_address,
            "property_type": prop.property_type,
            "listing_type": prop.listing_type,
            "currency": str(prop.currency or "USD").upper(),
            "starting_price": str(prop.base_price_per_night),
            "max_guests": int(prop.max_guests or 1),
            "main_image": prop.main_image,
            "rating": float(prop.overall_rating or 0),
            "review_count": int(prop.total_reviews or 0),
            "featured": bool(prop.is_featured),
            "verified": bool(prop.is_verified),
            "room_types": room_types,
        }
        if include_description:
            data["description"] = prop.description or ""
            data["house_rules"] = prop.house_rules
            data["allow_pets"] = bool(prop.allow_pets)
            data["allow_smoking"] = bool(prop.allow_smoking)
            data["allow_events"] = bool(prop.allow_events)
            data["cancellation_policy"] = str(prop.cancellation_policy or "flexible")
        return data

    @staticmethod
    def _bookable_property(public_id):
        from app.accommodation.models.property import Property

        prop = Property.query.filter_by(
            public_id=str(public_id),
            is_publicly_visible=True,
            is_deleted=False,
        ).first()
        if prop is None or not prop.can_be_booked():
            raise NativeAccommodationError(
                "property_unavailable",
                "This property is not currently available for public booking.",
                404,
            )
        return prop

    @classmethod
    def list_properties(cls, *, query=None, city=None, country=None, limit=20, offset=0):
        from app.accommodation.models.property import Property

        limit = max(1, min(int(limit or 20), 50))
        offset = max(0, int(offset or 0))
        q = Property.query.filter(
            Property.is_active.is_(True),
            Property.is_verified.is_(True),
            Property.is_publicly_visible.is_(True),
            Property.status.in_(("active", "published")),
            Property.is_deleted.is_(False),
        )
        if city:
            q = q.filter(Property.city.ilike(f"%{str(city).strip()[:100]}%"))
        if country:
            q = q.filter(Property.country.ilike(str(country).strip()[:2]))
        if query:
            term = f"%{str(query).strip()[:100]}%"
            q = q.filter(or_(
                Property.title.ilike(term),
                Property.summary.ilike(term),
                Property.city.ilike(term),
                Property.country.ilike(term),
            ))
        q = q.order_by(Property.is_featured.desc(), Property.overall_rating.desc(), Property.title.asc())
        rows = q.offset(offset).limit(limit + 1).all()
        has_more = len(rows) > limit
        rows = rows[:limit]
        return {
            "items": [cls._public_property(item) for item in rows if item.can_be_booked()],
            "limit": limit,
            "offset": offset,
            "has_more": has_more,
        }

    @classmethod
    def get_property(cls, public_id):
        return cls._public_property(cls._bookable_property(public_id), include_description=True)

    @staticmethod
    def _parse_dates(check_in_value, check_out_value):
        try:
            check_in = date.fromisoformat(str(check_in_value))
            check_out = date.fromisoformat(str(check_out_value))
        except (TypeError, ValueError) as exc:
            raise NativeAccommodationError(
                "booking_dates_invalid",
                "Enter valid check-in and check-out dates.",
                400,
            ) from exc
        if check_in < date.today():
            raise NativeAccommodationError("booking_date_in_past", "Check-in must be today or later.", 400)
        if check_out <= check_in:
            raise NativeAccommodationError("booking_dates_invalid", "Check-out must be after check-in.", 400)
        if (check_out - check_in).days > 90:
            raise NativeAccommodationError("booking_dates_too_long", "A single booking cannot exceed 90 nights.", 400)
        return check_in, check_out

    @classmethod
    def _validate_stay(cls, prop, check_in, check_out, num_guests, rooms_requested, room_type_id):
        from app.accommodation.services.availability_service import AvailabilityService
        from app.accommodation.services.host_service import HostService

        active_room_types = [room for room in (prop.room_types or []) if room.is_active]
        selected = None
        if active_room_types:
            if room_type_id is None:
                if len(active_room_types) == 1:
                    selected = active_room_types[0]
                else:
                    raise NativeAccommodationError(
                        "room_type_required",
                        "Choose a room type before requesting a booking quote.",
                        400,
                    )
            else:
                selected = next((room for room in active_room_types if int(room.id) == int(room_type_id)), None)
                if selected is None:
                    raise NativeAccommodationError(
                        "room_type_invalid",
                        "The selected room type does not belong to this property.",
                        400,
                    )
            capacity = int(selected.max_guests or 1) * int(rooms_requested)
            if int(num_guests) > capacity:
                raise NativeAccommodationError(
                    "guest_capacity_exceeded",
                    f"This room selection accommodates up to {capacity} guests.",
                    400,
                )
            available_units = HostService.available_units(
                selected.id, check_in, check_out
            )
            if available_units < int(rooms_requested):
                raise NativeAccommodationError(
                    "room_not_available",
                    f"Only {available_units} room(s) are available for those dates.",
                    409,
                )
        else:
            is_available, _blocked, reason = AvailabilityService.is_range_available(
                prop.id, check_in, check_out
            )
            if not is_available:
                raise NativeAccommodationError(
                    "dates_not_available",
                    reason or "The property is not available for those dates.",
                    409,
                )
        return selected

    @classmethod
    def quote_booking(
        cls,
        user,
        *,
        property_public_id,
        check_in_value,
        check_out_value,
        num_guests,
        rooms_requested=1,
        room_type_token=None,
    ):
        from app.accommodation.services.pricing_service import PricingService

        prop = cls._bookable_property(property_public_id)
        check_in, check_out = cls._parse_dates(check_in_value, check_out_value)
        try:
            guests = int(num_guests)
            rooms = int(rooms_requested)
        except (TypeError, ValueError) as exc:
            raise NativeAccommodationError("booking_guests_invalid", "Guest and room counts must be whole numbers.", 400) from exc
        if not 1 <= guests <= 32 or not 1 <= rooms <= 10:
            raise NativeAccommodationError("booking_guests_invalid", "Choose 1–32 guests and 1–10 rooms.", 400)

        selected_from_token = (
            cls._load_room_type_token(prop, room_type_token)
            if room_type_token
            else None
        )
        selected = cls._validate_stay(
            prop,
            check_in,
            check_out,
            guests,
            rooms,
            int(selected_from_token.id) if selected_from_token else None,
        )
        try:
            pricing = PricingService.calculate_total(
                prop,
                check_in,
                check_out,
                guests,
                room_type_id=selected.id if selected else None,
                num_rooms=rooms,
            )
        except ValueError as exc:
            raise NativeAccommodationError("booking_price_unavailable", str(exc), 400) from exc

        currency = str(prop.currency or "USD").upper()
        total = Decimal(str(pricing["total"]))
        from app.wallet.services.wallet_service import WalletService
        from app.wallet.repositories.ledger_repository import LedgerRepository

        account = WalletService.get_wallet_by_user_id(user.id, currency)
        balance = None
        if account is not None:
            balance = LedgerRepository().get_balance(account.id, currency)

        quote_id = uuid.uuid4().hex
        now = datetime.now(timezone.utc)
        payload = {
            "version": cls.QUOTE_VERSION,
            "quote_id": quote_id,
            "user_public_id": str(user.public_id),
            "property_public_id": str(prop.public_id),
            "room_type_id": int(selected.id) if selected else None,
            "check_in": check_in.isoformat(),
            "check_out": check_out.isoformat(),
            "num_guests": guests,
            "rooms_requested": rooms,
            "currency": currency,
            "nightly_rate": str(pricing["nightly_rate"]),
            "nights": int(pricing["nights"]),
            "subtotal": str(pricing["subtotal"]),
            "cleaning_fee": str(pricing["cleaning_fee"]),
            "service_fee": str(pricing["service_fee"]),
            "taxes": str(pricing["taxes"]),
            "total": str(total),
            "issued_at": now.isoformat(),
        }
        token = cls._serializer().dumps(payload)
        return {
            "quote_id": quote_id,
            "quote_token": token,
            "property": cls._public_property(prop),
            "check_in": payload["check_in"],
            "check_out": payload["check_out"],
            "num_guests": guests,
            "rooms_requested": rooms,
            "nights": payload["nights"],
            "currency": currency,
            "nightly_rate": payload["nightly_rate"],
            "subtotal": payload["subtotal"],
            "cleaning_fee": payload["cleaning_fee"],
            "service_fee": payload["service_fee"],
            "taxes": payload["taxes"],
            "total": str(total),
            "wallet_available_balance": str(balance) if balance is not None else None,
            "wallet_payment_available": bool(account and not account.is_frozen and balance is not None and balance >= total),
            "expires_at": (now + timedelta(seconds=cls.QUOTE_MAX_AGE_SECONDS)).isoformat(),
        }

    @classmethod
    def _load_quote(cls, user, quote_token):
        try:
            payload = cls._serializer().loads(str(quote_token or ""), max_age=cls.QUOTE_MAX_AGE_SECONDS)
        except SignatureExpired as exc:
            raise NativeAccommodationError("booking_quote_expired", "This booking quote has expired. Request a new quote.", 409) from exc
        except BadSignature as exc:
            raise NativeAccommodationError("booking_quote_invalid", "This booking quote is invalid. Request a new quote.", 400) from exc
        if (
            payload.get("version") != cls.QUOTE_VERSION
            or payload.get("user_public_id") != str(user.public_id)
        ):
            raise NativeAccommodationError("booking_quote_owner_mismatch", "This quote does not belong to your account.", 403)
        return payload

    @classmethod
    def confirm_wallet_booking(cls, user, *, quote_token, pin, ip_address=None, user_agent=None, special_requests=None):
        from app.accommodation.services.booking_service import BookingService
        from app.accommodation.services.marketplace_service import MarketplaceService
        from app.wallet.services.wallet_service import WalletService
        from app.wallet.repositories.ledger_repository import LedgerRepository
        from app.accommodation.models.booking import AccommodationBooking

        if not str(pin or "").strip():
            raise NativeAccommodationError("transaction_pin_required", "Enter your transaction PIN to pay for this booking.", 403)
        payload = cls._load_quote(user, quote_token)
        prop = cls._bookable_property(payload.get("property_public_id"))
        check_in, check_out = cls._parse_dates(payload.get("check_in"), payload.get("check_out"))
        selected = cls._validate_stay(
            prop, check_in, check_out, int(payload["num_guests"]),
            int(payload["rooms_requested"]), payload.get("room_type_id"),
        )

        from app.accommodation.services.pricing_service import PricingService
        pricing = PricingService.calculate_total(
            prop,
            check_in,
            check_out,
            int(payload["num_guests"]),
            room_type_id=selected.id if selected else None,
            num_rooms=int(payload["rooms_requested"]),
        )
        currency = str(prop.currency or "USD").upper()
        total = Decimal(str(pricing["total"]))
        if currency != payload["currency"] or total != Decimal(str(payload["total"])):
            raise NativeAccommodationError(
                "booking_quote_changed",
                "The property's price or currency changed. Request a fresh quote before paying.",
                409,
            )

        wallet_account = WalletService.get_wallet_by_user_id(user.id, currency)
        if wallet_account is None or str(wallet_account.status).lower() != "active":
            raise NativeAccommodationError("wallet_not_found", f"You need an active {currency} Wallet to pay for this booking.", 409)
        if wallet_account.is_frozen:
            raise NativeAccommodationError("wallet_frozen", "Your Wallet is restricted. Contact AFCON360 support.", 403)
        balance = LedgerRepository().get_balance(wallet_account.id, currency)
        if balance < total:
            raise NativeAccommodationError(
                "insufficient_wallet_balance",
                f"Your available balance is {balance} {currency}; this booking requires {total} {currency}.",
                402,
            )

        host_user_id = prop.owner_user_id
        if not host_user_id and prop.owner_org_id:
            host_user_id = getattr(prop.owner_org, "primary_contact_user_id", None)
        if not host_user_id:
            raise NativeAccommodationError(
                "property_host_unavailable",
                "This property's booking contact is not configured. Please contact AFCON360 support.",
                409,
            )

        from app.profile.services.canonical_identity import get_canonical_identity
        identity = get_canonical_identity(user)
        guest_name = identity.full_name or getattr(user, "username", None) or user.email
        guest_email = identity.email or user.email
        guest_phone = identity.phone or getattr(user, "phone", None)
        idempotency_key = "NATACCOM" + str(payload["quote_id"])

        existing = AccommodationBooking.query.filter_by(
            idempotency_key=idempotency_key,
            guest_user_id=user.id,
        ).first()
        if existing and existing.wallet_txn_id and str(existing.payment_status).lower() in {"paid", "completed"}:
            return cls._serialize_booking(existing)

        booking, error = BookingService.create_booking(
            property_id=prop.id,
            guest_user_id=user.id,
            host_user_id=int(host_user_id),
            check_in=check_in,
            check_out=check_out,
            num_guests=int(payload["num_guests"]),
            rooms_requested=int(payload["rooms_requested"]),
            guest_name=guest_name,
            guest_email=guest_email,
            guest_phone=guest_phone,
            special_requests=str(special_requests or "")[:1000] or None,
            idempotency_key=idempotency_key,
            ip_address=ip_address,
            user_agent=user_agent,
            booked_by_user_id=user.id,
            primary_guest_id=user.id,
            primary_guest_name=guest_name,
            primary_guest_email=guest_email,
            primary_guest_phone=guest_phone,
            booking_type="self",
            room_type_id=selected.id if selected else None,
            payment_method="wallet",
            payment_timing="pay_now",
            payment_guaranteed=True,
            guarantee_type="wallet_balance",
        )
        if error or booking is None:
            raise NativeAccommodationError("booking_create_failed", error or "AFCON360 could not create this booking.", 409)

        if booking.wallet_txn_id and str(booking.payment_status).lower() == "paid":
            return cls._serialize_booking(booking)

        paid, transaction_id, payment_error = MarketplaceService.charge_guest(
            booking=booking,
            total_amount=total,
            currency=currency,
            idempotency_key=idempotency_key,
            transaction_pin=str(pin),
            authorized_user_id=int(user.id),
        )
        if not paid or not transaction_id:
            try:
                BookingService.cancel_booking(
                    booking.id,
                    cancelled_by_user_id=user.id,
                    reason="Native wallet payment failed",
                    ip_address=ip_address,
                    user_agent=user_agent,
                    idempotency_key=f"{idempotency_key}-PAYFAIL",
                )
            except Exception:
                db.session.rollback()
                current_app.logger.exception("Could not release inventory after native accommodation payment failure")
            raise NativeAccommodationError(
                "booking_payment_failed",
                payment_error or "Wallet payment was not completed. Your booking was not confirmed.",
                402,
            )

        confirmed, confirm_error = BookingService.confirm_booking(
            booking.id,
            wallet_transaction_id=transaction_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        if not confirmed:
            # Compensate only through the canonical marketplace escrow refund.
            refund_ok, refund_error = MarketplaceService.refund_guest(booking.id, total)
            BookingService.cancel_booking(
                booking.id,
                cancelled_by_user_id=user.id,
                reason="Booking confirmation failed after wallet payment",
                ip_address=ip_address,
                user_agent=user_agent,
                idempotency_key=f"{idempotency_key}-CONFIRMFAIL",
            )
            if not refund_ok:
                current_app.logger.critical(
                    "Native accommodation booking %s could not be confirmed or refunded: %s",
                    booking.booking_reference,
                    refund_error,
                )
                raise NativeAccommodationError(
                    "booking_needs_support",
                    "Payment was received but the booking could not be confirmed. AFCON360 support must reconcile this payment; do not pay again.",
                    503,
                )
            raise NativeAccommodationError(
                "booking_confirmation_failed",
                "The booking could not be confirmed. The wallet payment was reversed.",
                409,
            )

        return cls._serialize_booking(booking)

    @staticmethod
    def _serialize_booking(booking):
        prop = booking.accommodation_property
        return {
            "booking_reference": booking.booking_reference,
            "property": {
                "public_id": str(prop.public_id) if prop else None,
                "title": prop.title if prop else None,
                "city": prop.city if prop else None,
                "country": prop.country if prop else None,
                "image": prop.main_image if prop else None,
            },
            "check_in": booking.check_in.isoformat() if booking.check_in else None,
            "check_out": booking.check_out.isoformat() if booking.check_out else None,
            "nights": int(booking.num_nights or 0),
            "num_guests": int(booking.num_guests or 1),
            "rooms_requested": int(booking.rooms_requested or 1),
            "amount": str(booking.total_amount),
            "currency": str(booking.currency or "USD").upper(),
            "payment_status": str(getattr(booking.payment_status, "value", booking.payment_status)).lower(),
            "status": str(getattr(booking.status, "value", booking.status)).lower(),
            "payment_method": booking.payment_method,
            "cancellation_policy": (booking.policy_snapshot or {}).get("cancellation_policy"),
            "created_at": booking.created_at.isoformat() if booking.created_at else None,
        }

    @classmethod
    def list_bookings(cls, user, *, limit=20, offset=0):
        from app.accommodation.services.booking_service import BookingService
        rows = BookingService.get_user_bookings(
            int(user.id),
            limit=max(1, min(int(limit or 20), 50)),
            offset=max(0, int(offset or 0)),
        )
        return {
            "items": [cls._serialize_booking(item) for item in rows],
            "limit": max(1, min(int(limit or 20), 50)),
            "offset": max(0, int(offset or 0)),
        }

    @classmethod
    def get_booking(cls, user, reference):
        from app.accommodation.models.booking import AccommodationBooking

        booking = AccommodationBooking.query.filter_by(
            booking_reference=str(reference),
            is_deleted=False,
        ).first()
        if booking is None:
            raise NativeAccommodationError("booking_not_found", "Booking not found.", 404)
        allowed = {
            int(booking.guest_user_id or 0),
            int(booking.booked_by_user_id or 0),
            int(booking.primary_guest_id or 0),
            int(booking.booking_owner_id or 0),
        }
        if int(user.id) not in allowed:
            raise NativeAccommodationError("booking_not_found", "Booking not found.", 404)
        return cls._serialize_booking(booking)

    @classmethod
    def cancel_booking(cls, user, reference, *, reason=None, ip_address=None, user_agent=None, idempotency_key=None):
        from app.accommodation.models.booking import AccommodationBooking
        from app.accommodation.services.booking_service import BookingService
        from app.accommodation.services.marketplace_service import MarketplaceService

        booking = AccommodationBooking.query.filter_by(
            booking_reference=str(reference),
            is_deleted=False,
        ).first()
        if booking is None:
            raise NativeAccommodationError("booking_not_found", "Booking not found.", 404)
        allowed = {
            int(booking.guest_user_id or 0),
            int(booking.booked_by_user_id or 0),
            int(booking.primary_guest_id or 0),
            int(booking.booking_owner_id or 0),
        }
        if int(user.id) not in allowed:
            raise NativeAccommodationError("booking_not_found", "Booking not found.", 404)

        success, message, refund = BookingService.cancel_booking(
            booking.id,
            cancelled_by_user_id=int(user.id),
            reason=str(reason or "Cancelled by guest")[:500],
            ip_address=ip_address,
            user_agent=user_agent,
            idempotency_key=idempotency_key,
        )
        if not success:
            raise NativeAccommodationError("booking_cancel_rejected", message or "This booking cannot be cancelled.", 409)

        refund_result = None
        if refund and Decimal(str(refund)) > 0:
            ok, error = MarketplaceService.refund_guest(booking.id, Decimal(str(refund)))
            refund_result = {
                "status": "completed" if ok else "needs_reconciliation",
                "amount": str(refund),
                "currency": str(booking.currency or "USD").upper(),
                "error": None if ok else "AFCON360 could not complete the refund automatically. Support must reconcile it.",
            }
            if not ok:
                current_app.logger.error("Native accommodation refund pending for %s: %s", booking.booking_reference, error)

        return {
            "booking": cls._serialize_booking(booking),
            "cancellation_message": message,
            "refund": refund_result,
        }
