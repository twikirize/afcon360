"""Host-facing operations for the accommodation module."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Dict, Iterable, List, Optional, Tuple

from sqlalchemy import func

from app.extensions import db
from app.accommodation.models.property import (
    AccommodationCancellationPolicy,
    AccommodationPropertyStatus,
    AccommodationPropertyType,
    Property,
)
from app.accommodation.models.booking import (
    AccommodationBooking,
    AccommodationBookingStatus,
)
from app.accommodation.models.availability import BlockedDate


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(text: str) -> str:
    """Generate a lowercase slug safe for URLs."""
    base = _SLUG_RE.sub("-", text.lower()).strip("-")
    return base or "listing"


def _ensure_unique_slug(base_slug: str) -> str:
    """Ensure slug uniqueness by appending numeric suffixes when needed."""
    slug = base_slug
    suffix = 2
    while Property.query.filter_by(slug=slug).first() is not None:
        slug = f"{base_slug}-{suffix}"
        suffix += 1
    return slug


def _extract_gallery(main_image: Optional[str], gallery_field: Optional[str]) -> List[str]:
    images: List[str] = []
    if main_image:
        images.append(main_image.strip())
    if gallery_field:
        for line in gallery_field.splitlines():
            line = line.strip()
            if line:
                images.append(line)
    # remove duplicates while preserving order
    seen = set()
    unique: List[str] = []
    for img in images:
        if img not in seen:
            unique.append(img)
            seen.add(img)
    return unique


class HostService:
    """Encapsulates host listing management and dashboard aggregation."""

    @staticmethod
    def create_property(data: Dict, *, owner_user_id: Optional[int], owner_org_id: Optional[int]) -> Property:
        """Persist a new property from validated form data."""
        title = data["title"].strip()
        slug = _ensure_unique_slug(_slugify(title))

        prop = Property(
            owner_user_id=owner_user_id,
            owner_org_id=owner_org_id,
            title=title,
            slug=slug,
            summary=data.get("summary"),
            description=data["description"].strip(),
            property_type=AccommodationPropertyType(data["property_type"]),
            address_line1=data["address_line1"].strip(),
            address_line2=data.get("address_line2") or None,
            city=data["city"].strip(),
            state=data.get("state") or None,
            country=data["country"].upper(),
            postal_code=data.get("postal_code") or None,
            latitude=None,
            longitude=None,
            max_guests=data.get("max_guests", 2),
            bedrooms=data.get("bedrooms") or 0,
            beds=data.get("beds") or 0,
            bathrooms=float(data.get("bathrooms") or 0),
            base_price_per_night=Decimal(str(data.get("base_price_per_night"))).quantize(Decimal("0.01")),
            currency=(data.get("currency") or "USD").upper(),
            cleaning_fee=Decimal(str(data.get("cleaning_fee") or 0)).quantize(Decimal("0.01")),
            service_fee_pct=Decimal(str(data.get("service_fee_pct") or 0)).quantize(Decimal("0.01")),
            min_stay_nights=data.get("min_stay_nights", 1),
            max_stay_nights=data.get("max_stay_nights"),
            cancellation_policy=AccommodationCancellationPolicy(data["cancellation_policy"]),
            check_in_time=data.get("check_in_time") or "14:00",
            check_out_time=data.get("check_out_time") or "11:00",
            instant_book=bool(data.get("instant_book")),
            allow_pets=bool(data.get("allow_pets")),
            allow_smoking=bool(data.get("allow_smoking")),
            allow_events=bool(data.get("allow_events")),
            house_rules=data.get("house_rules"),
            main_image=data.get("main_image"),
            gallery=_extract_gallery(data.get("main_image"), data.get("gallery_urls")),
            meta_title=data.get("meta_title"),
            meta_description=data.get("meta_description"),
            status=AccommodationPropertyStatus.PENDING_REVIEW,
            is_active=False,
            is_verified=False,
        )

        db.session.add(prop)
        db.session.flush()
        return prop

    @staticmethod
    def update_property(prop: Property, data: Dict) -> Property:
        """Update an existing property with validated form data."""
        prop.title = data["title"].strip()
        prop.summary = data.get("summary")
        prop.description = data["description"].strip()
        prop.property_type = AccommodationPropertyType(data["property_type"])
        prop.address_line1 = data["address_line1"].strip()
        prop.address_line2 = data.get("address_line2") or None
        prop.city = data["city"].strip()
        prop.state = data.get("state") or None
        prop.country = data["country"].upper()
        prop.postal_code = data.get("postal_code") or None
        prop.max_guests = data.get("max_guests", prop.max_guests)
        prop.bedrooms = data.get("bedrooms") or 0
        prop.beds = data.get("beds") or 0
        prop.bathrooms = float(data.get("bathrooms") or 0)
        prop.base_price_per_night = Decimal(str(data.get("base_price_per_night"))).quantize(Decimal("0.01"))
        prop.currency = (data.get("currency") or prop.currency).upper()
        prop.cleaning_fee = Decimal(str(data.get("cleaning_fee") or 0)).quantize(Decimal("0.01"))
        prop.service_fee_pct = Decimal(str(data.get("service_fee_pct") or 0)).quantize(Decimal("0.01"))
        prop.min_stay_nights = data.get("min_stay_nights", prop.min_stay_nights)
        prop.max_stay_nights = data.get("max_stay_nights")
        prop.cancellation_policy = AccommodationCancellationPolicy(data["cancellation_policy"])
        prop.check_in_time = data.get("check_in_time") or prop.check_in_time
        prop.check_out_time = data.get("check_out_time") or prop.check_out_time
        prop.instant_book = bool(data.get("instant_book"))
        prop.allow_pets = bool(data.get("allow_pets"))
        prop.allow_smoking = bool(data.get("allow_smoking"))
        prop.allow_events = bool(data.get("allow_events"))
        prop.house_rules = data.get("house_rules")
        prop.main_image = data.get("main_image")
        prop.gallery = _extract_gallery(data.get("main_image"), data.get("gallery_urls"))
        prop.meta_title = data.get("meta_title")
        prop.meta_description = data.get("meta_description")
        return prop

    @staticmethod
    def get_dashboard_data(*, owner_user_id: Optional[int], owner_org_id: Optional[int]) -> Dict:
        """Return listings, bookings, and stats for the given owner."""
        property_query = Property.query.filter(Property.is_deleted.is_(False))
        if owner_user_id:
            property_query = property_query.filter(Property.owner_user_id == owner_user_id)
        if owner_org_id:
            property_query = property_query.filter(Property.owner_org_id == owner_org_id)

        properties = property_query.order_by(Property.created_at.desc()).all()

        stats = {
            "total_listings": len(properties),
            "active_listings": len(
                [p for p in properties if p.status == AccommodationPropertyStatus.ACTIVE and p.is_active]
            ),
            "pending_review": len(
                [p for p in properties if p.status == AccommodationPropertyStatus.PENDING_REVIEW]
            ),
        }

        bookings_query = AccommodationBooking.query.join(Property, AccommodationBooking.property_id == Property.id)
        if owner_user_id:
            bookings_query = bookings_query.filter(Property.owner_user_id == owner_user_id)
        if owner_org_id:
            bookings_query = bookings_query.filter(Property.owner_org_id == owner_org_id)

        upcoming_bookings = (
            bookings_query.filter(
                AccommodationBooking.status.in_(
                    [
                        AccommodationBookingStatus.CONFIRMED.value,
                        AccommodationBookingStatus.PENDING.value,
                    ]
                ),
                AccommodationBooking.check_in >= date.today(),
            )
            .order_by(AccommodationBooking.check_in.asc())
            .limit(5)
            .all()
        )

        revenue_totals = (
            bookings_query.filter(
                AccommodationBooking.status.in_([
                    AccommodationBookingStatus.CONFIRMED.value,
                    AccommodationBookingStatus.CHECKED_OUT.value,
                    AccommodationBookingStatus.CHECKED_IN.value,
                ])
            )
            .with_entities(func.sum(AccommodationBooking.total_amount), AccommodationBooking.currency)
            .group_by(AccommodationBooking.currency)
            .all()
        )

        revenue_summary = [
            {
                "currency": currency,
                "amount": float(total or 0),
            }
            for total, currency in revenue_totals
        ]

        return {
            "properties": properties,
            "stats": stats,
            "upcoming_bookings": upcoming_bookings,
            "revenue_summary": revenue_summary,
        }

    # ------------------------------------------------------------------
    # AVAILABILITY & CALENDAR SUPPORT
    # ------------------------------------------------------------------

    @staticmethod
    def get_properties_for_owner(*, owner_user_id: Optional[int], owner_org_id: Optional[int]) -> List[Dict]:
        """Return lightweight property metadata for availability views."""

        query = Property.query.filter(Property.is_deleted.is_(False))
        if owner_user_id:
            query = query.filter(Property.owner_user_id == owner_user_id)
        if owner_org_id:
            query = query.filter(Property.owner_org_id == owner_org_id)

        properties = query.order_by(Property.created_at.desc()).all()

        return [
            {
                "id": prop.id,
                "title": prop.title,
                "status": prop.status.value if prop.status else None,
                "is_active": prop.is_active,
                "city": prop.city,
                "country": prop.country,
            }
            for prop in properties
        ]

    @staticmethod
    def get_property_calendar_snapshot(
        *,
        property_id: int,
        start_date: date,
        end_date: date,
    ) -> Dict:
        """Return blocked dates, bookings, and availability indicators for UI."""

        if end_date < start_date:
            raise ValueError("end_date must be on or after start_date")

        # Pull property for context
        prop = Property.query.get_or_404(property_id)

        # Collect bookings overlapping window
        bookings = (
            AccommodationBooking.query.filter(
                AccommodationBooking.property_id == property_id,
                AccommodationBooking.check_out >= start_date,
                AccommodationBooking.check_in <= end_date,
                AccommodationBooking.status.in_(
                    [
                        AccommodationBookingStatus.PENDING.value,
                        AccommodationBookingStatus.CONFIRMED.value,
                        AccommodationBookingStatus.CHECKED_IN.value,
                    ]
                ),
            )
            .order_by(AccommodationBooking.check_in.asc())
            .all()
        )

        # Collect manually blocked dates
        blocked_dates = (
            BlockedDate.query.filter(
                BlockedDate.property_id == property_id,
                BlockedDate.blocked_date.between(start_date, end_date),
            )
            .order_by(BlockedDate.blocked_date.asc())
            .all()
        )

        days: List[Dict[str, object]] = []
        cursor = start_date
        while cursor <= end_date:
            day_info: Dict[str, object] = {
                "date": cursor.isoformat(),
                "is_today": cursor == date.today(),
                "status": "available",
                "blocked_reason": None,
                "bookings": [],
            }

            # Check booking coverage
            for booking in bookings:
                if booking.check_in <= cursor < booking.check_out:
                    day_info["status"] = "booked"
                    day_info.setdefault("bookings", []).append(
                        {
                            "id": booking.id,
                            "reference": booking.booking_reference,
                            "guest_name": booking.guest_name,
                            "status": booking.status,
                            "check_in": booking.check_in.isoformat(),
                            "check_out": booking.check_out.isoformat(),
                        }
                    )

            # Check manual blocks
            for block in blocked_dates:
                if block.blocked_date == cursor:
                    if not day_info["bookings"]:
                        day_info["status"] = "blocked"
                    day_info["blocked_reason"] = block.reason.value if block.reason else None
                    break

            days.append(day_info)
            cursor += timedelta(days=1)

        return {
            "property": {
                "id": prop.id,
                "title": prop.title,
                "status": prop.status.value if prop.status else None,
                "is_active": prop.is_active,
                "timezone": getattr(prop, "timezone", None),
            },
            "window": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
            },
            "days": days,
            "bookings": [
                {
                    "id": booking.id,
                    "reference": booking.booking_reference,
                    "guest_name": booking.guest_name,
                    "check_in": booking.check_in.isoformat(),
                    "check_out": booking.check_out.isoformat(),
                    "status": booking.status,
                    "payment_status": booking.payment_status,
                    "total_amount": float(booking.total_amount or 0),
                    "currency": booking.currency,
                }
                for booking in bookings
            ],
            "blocked_dates": [
                {
                    "date": blocked.blocked_date.isoformat(),
                    "reason": blocked.reason.value if blocked.reason else None,
                }
                for blocked in blocked_dates
            ],
        }
