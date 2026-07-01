"""Host-facing operations for the accommodation module."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Dict, Iterable, List, Optional, Tuple

from sqlalchemy import func, and_, desc

from app.extensions import db
from app.accommodation.models.property import (
    AccommodationCancellationPolicy,
    AccommodationPropertyStatus,
    AccommodationPropertyType,
    Property,
    RoomType,
    InventoryBlock,
)
from app.accommodation.models.booking import (
    AccommodationBooking,
    AccommodationBookingStatus,
)
from app.accommodation.models.availability import BlockedDate

# Active booking statuses for availability calculation
ACTIVE_BOOKING_STATUSES = [
    AccommodationBookingStatus.CONFIRMED.value,
    AccommodationBookingStatus.CHECKED_IN.value,
    AccommodationBookingStatus.PENDING.value,
]


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
        """Persist a new property from validated form data.
        
        Auto-creates a default RoomType with total_units=1 for individual hosts.
        For organisation hosts, room_types are created separately via bulk import.
        """
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
        
        # Auto-create default RoomType for individual hosts (total_units=1)
        # Organisation hosts will create room_types via bulk import
        if owner_user_id and not owner_org_id:
            default_room_type = RoomType(
                property_id=prop.id,
                name="Standard Room",
                description="Default room type for this property",
                max_guests=prop.max_guests,
                bedrooms=prop.bedrooms,
                beds=prop.beds,
                bathrooms=prop.bathrooms,
                base_price_per_night=prop.base_price_per_night,
                currency=prop.currency,
                cleaning_fee=prop.cleaning_fee,
                service_fee_pct=prop.service_fee_pct,
                total_units=1,
                is_active=True,
            )
            db.session.add(default_room_type)
        
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
        """Enhanced dashboard with analytics and insights"""
        
        # Base query
        property_query = Property.query.filter(Property.is_deleted.is_(False))
        if owner_user_id:
            property_query = property_query.filter(Property.owner_user_id == owner_user_id)
        if owner_org_id:
            property_query = property_query.filter(Property.owner_org_id == owner_org_id)

        properties = property_query.order_by(Property.created_at.desc()).all()

        # ── Enhanced Stats ───────────────────────────────────────────
        active_properties = [p for p in properties if p.status == AccommodationPropertyStatus.ACTIVE and p.is_active]
        pending_properties = [p for p in properties if p.status == AccommodationPropertyStatus.PENDING_REVIEW]
        draft_properties = [p for p in properties if p.status == AccommodationPropertyStatus.DRAFT]
        suspended_properties = [p for p in properties if p.status == AccommodationPropertyStatus.SUSPENDED]
        total_views = sum(p.views_last_24h for p in properties)

        stats = {
            "total_listings": len(properties),
            "active_listings": len(active_properties),
            "pending_review": len(pending_properties),
            "draft_listings": len(draft_properties),
            "suspended_listings": len(suspended_properties),
            "occupancy_rate": HostService._calculate_occupancy(properties),
            "average_price": HostService._calculate_avg_price(active_properties),
            "total_reviews": sum(p.total_reviews for p in properties),
            "properties_with_reviews": len([p for p in properties if p.total_reviews > 0]),
            "total_views": total_views
        }

        # ── Bookings ──────────────────────────────────────────────────
        bookings_query = AccommodationBooking.query.join(Property, AccommodationBooking.property_id == Property.id)
        if owner_user_id:
            bookings_query = bookings_query.filter(Property.owner_user_id == owner_user_id)
        if owner_org_id:
            bookings_query = bookings_query.filter(Property.owner_org_id == owner_org_id)

        # Upcoming bookings (next 10)
        upcoming_bookings = (
            bookings_query.filter(
                AccommodationBooking.status.in_(
                    [AccommodationBookingStatus.CONFIRMED.value, 
                     AccommodationBookingStatus.PENDING.value]
                ),
                AccommodationBooking.check_in >= date.today(),
            )
            .order_by(AccommodationBooking.check_in.asc())
            .limit(10)
            .all()
        )

        # Recent bookings (last 10)
        recent_bookings = (
            bookings_query.filter(
                AccommodationBooking.status.in_(
                    [AccommodationBookingStatus.CONFIRMED.value,
                     AccommodationBookingStatus.CHECKED_OUT.value,
                     AccommodationBookingStatus.CHECKED_IN.value]
                )
            )
            .order_by(AccommodationBooking.created_at.desc())
            .limit(10)
            .all()
        )

        # ── Revenue Analytics ────────────────────────────────────────
        revenue_totals = (
            bookings_query.filter(
                AccommodationBooking.status.in_([
                    AccommodationBookingStatus.CONFIRMED.value,
                    AccommodationBookingStatus.CHECKED_OUT.value,
                    AccommodationBookingStatus.CHECKED_IN.value,
                ])
            )
            .with_entities(
                func.sum(AccommodationBooking.total_amount).label('total'),
                AccommodationBooking.currency
            )
            .group_by(AccommodationBooking.currency)
            .all()
        )

        revenue_summary = [
            {"currency": currency, "amount": float(total or 0)}
            for total, currency in revenue_totals
        ]

        total_revenue = sum(r["amount"] for r in revenue_summary)

        # ── Monthly Revenue (for chart) ──────────────────────────────
        monthly_revenue = HostService._calculate_monthly_revenue(
            bookings_query, owner_user_id, owner_org_id
        )

        # ── Performance Metrics ──────────────────────────────────────
        avg_rating = HostService._calculate_avg_rating(properties)
        avg_response_rate = HostService._calculate_avg_response_rate(properties)
        total_views = stats["total_views"]
        
        # ── Conversion Rate ──────────────────────────────────────────
        conversion_rate = HostService._calculate_conversion_rate(properties)

        # ── Smart Insights ───────────────────────────────────────────
        insights = HostService._generate_insights(
            properties=properties,
            stats=stats,
            total_revenue=total_revenue,
            avg_rating=avg_rating,
            conversion_rate=conversion_rate
        )

        total_bookings_count = bookings_query.filter(
            AccommodationBooking.status.in_([
                AccommodationBookingStatus.CONFIRMED.value,
                AccommodationBookingStatus.CHECKED_OUT.value,
                AccommodationBookingStatus.CHECKED_IN.value,
                AccommodationBookingStatus.PENDING.value,
            ])
        ).count()

        return {
            "properties": properties,
            "stats": stats,
            "upcoming_bookings": upcoming_bookings,
            "recent_bookings": recent_bookings,
            "revenue_summary": revenue_summary,
            "monthly_revenue": monthly_revenue,
            "total_bookings_count": total_bookings_count,
            "total_revenue": total_revenue,
            "avg_rating": avg_rating,
            "total_reviews": stats["total_reviews"],
            "avg_response_rate": avg_response_rate,
            "total_views": total_views,
            "conversion_rate": conversion_rate,
            "insights": insights,
            "last_updated": datetime.utcnow().isoformat()
        }

    @staticmethod
    def _calculate_occupancy(properties: List[Property]) -> float:
        """Calculate overall occupancy rate"""
        if not properties:
            return 0.0
        
        total_bookings = sum(p.total_bookings for p in properties)
        total_capacity = sum(p.max_guests for p in properties)
        
        if total_capacity == 0:
            return 0.0
        
        return round((total_bookings / total_capacity) * 100, 1)

    @staticmethod
    def _calculate_avg_price(properties: List[Property]) -> float:
        """Calculate average nightly rate"""
        if not properties:
            return 0.0
        
        prices = [float(p.base_price_per_night) for p in properties if p.base_price_per_night]
        if not prices:
            return 0.0
        
        return round(sum(prices) / len(prices), 2)

    @staticmethod
    def _calculate_avg_rating(properties: List[Property]) -> float:
        """Calculate average rating across properties"""
        rated_properties = [p for p in properties if p.overall_rating and p.total_reviews > 0]
        if not rated_properties:
            return 0.0
        return round(sum(p.overall_rating for p in rated_properties) / len(rated_properties), 1)

    @staticmethod
    def _calculate_avg_response_rate(properties: List[Property]) -> Optional[float]:
        """Calculate average host response rate"""
        response_rates = [p.host_response_rate for p in properties if p.host_response_rate is not None]
        if not response_rates:
            return None
        return round(sum(response_rates) / len(response_rates), 1)

    @staticmethod
    def _calculate_conversion_rate(properties: List[Property]) -> float:
        """Calculate view-to-booking conversion rate"""
        total_views = sum(p.views_last_24h for p in properties)
        total_bookings = sum(p.total_bookings for p in properties)
        
        if total_views == 0:
            return 0.0
        
        return round((total_bookings / total_views) * 100, 1)

    @staticmethod
    def _calculate_monthly_revenue(bookings_query, owner_user_id, owner_org_id) -> List[Dict]:
        """Calculate monthly revenue for the last 12 months"""
        months = []
        today = date.today()
        
        for i in range(12):
            month_date = today.replace(day=1) - timedelta(days=30 * i)
            month_start = month_date.replace(day=1)
            
            # Get next month
            if month_date.month == 12:
                month_end = month_date.replace(year=month_date.year + 1, month=1, day=1)
            else:
                month_end = month_date.replace(month=month_date.month + 1, day=1)
            
            # Query revenue for this month
            monthly = bookings_query.filter(
                AccommodationBooking.created_at >= month_start,
                AccommodationBooking.created_at < month_end,
                AccommodationBooking.status.in_([
                    AccommodationBookingStatus.CONFIRMED.value,
                    AccommodationBookingStatus.CHECKED_OUT.value,
                    AccommodationBookingStatus.CHECKED_IN.value,
                ])
            ).with_entities(
                func.sum(AccommodationBooking.total_amount).label('total')
            ).first()
            
            months.append({
                "month": month_start.strftime("%b %Y"),
                "amount": float(monthly.total or 0)
            })
        
        return months

    @staticmethod
    def _generate_insights(
        properties: List[Property],
        stats: Dict,
        total_revenue: float,
        avg_rating: float,
        conversion_rate: float
    ) -> List[Dict]:
        """Generate smart insights for the host"""
        insights = []
        
        # ── Property Insights ────────────────────────────────────────
        if stats["total_listings"] == 0:
            insights.append({
                "type": "action",
                "priority": "high",
                "icon": "🚀",
                "title": "Start hosting today!",
                "description": "Create your first property listing and start earning.",
                "action_text": "Create Listing",
                "action_url": "accommodation.host_create_listing"
            })
        
        elif stats["pending_review"] > 0:
            insights.append({
                "type": "warning",
                "priority": "high",
                "icon": "⏳",
                "title": f"{stats['pending_review']} listing{'s' if stats['pending_review'] > 1 else ''} pending review",
                "description": "Complete the listing details to get approved faster.",
                "action_text": "Review Now",
                "action_url": "accommodation.host_dashboard"
            })
        
        # ── Performance Insights ─────────────────────────────────────
        if total_revenue > 0 and avg_rating > 4.5:
            insights.append({
                "type": "success",
                "priority": "medium",
                "icon": "🌟",
                "title": "Excellent ratings!",
                "description": f"Your average rating of {avg_rating}★ puts you in the top tier of hosts.",
                "action_text": "Share Success",
                "action_url": "#"
            })
        
        elif avg_rating < 4.0 and avg_rating > 0:
            insights.append({
                "type": "warning",
                "priority": "medium",
                "icon": "📝",
                "title": "Rating improvement needed",
                "description": f"Your average rating is {avg_rating}★. Check guest feedback for areas to improve.",
                "action_text": "View Reviews",
                "action_url": "#"
            })
        
        # ── Revenue Insights ─────────────────────────────────────────
        if total_revenue > 10000:
            insights.append({
                "type": "success",
                "priority": "low",
                "icon": "💎",
                "title": "Revenue milestone!",
                "description": f"You've earned ${total_revenue:,.0f} in total revenue. Great work!",
                "action_text": "Track Growth",
                "action_url": "accommodation.host_earnings"
            })
        
        # ── Conversion Insights ──────────────────────────────────────
        if conversion_rate > 5:
            insights.append({
                "type": "success",
                "priority": "low",
                "icon": "📈",
                "title": f"Strong conversion rate: {conversion_rate}%",
                "description": "Your listings are converting views to bookings above average.",
                "action_text": "Learn More",
                "action_url": "#"
            })
        
        elif conversion_rate > 0 and conversion_rate < 2:
            insights.append({
                "type": "warning",
                "priority": "medium",
                "icon": "🎯",
                "title": f"Conversion rate could improve: {conversion_rate}%",
                "description": "Consider updating your listing photos and descriptions.",
                "action_text": "Optimize Listing",
                "action_url": "accommodation.host_dashboard"
            })
        
        # ── Occupancy Insights ──────────────────────────────────────
        if stats["occupancy_rate"] > 80:
            insights.append({
                "type": "success",
                "priority": "medium",
                "icon": "🔥",
                "title": f"High occupancy rate: {stats['occupancy_rate']}%",
                "description": "Your listings are in high demand! Consider dynamic pricing.",
                "action_text": "Adjust Pricing",
                "action_url": "#"
            })
        
        elif stats["occupancy_rate"] < 30 and stats["total_listings"] > 0:
            insights.append({
                "type": "warning",
                "priority": "medium",
                "icon": "📉",
                "title": f"Low occupancy rate: {stats['occupancy_rate']}%",
                "description": "Try adjusting your prices or promoting your listings.",
                "action_text": "Optimize Pricing",
                "action_url": "#"
            })
        
        # ── Engagement Insight ──────────────────────────────────────
        if stats.get("total_views", 0) > 0 and stats.get("total_reviews", 0) == 0:
            insights.append({
                "type": "info",
                "priority": "low",
                "icon": "💬",
                "title": "Time to collect reviews!",
                "description": "You have views but no reviews yet. Encourage guests to leave feedback.",
                "action_text": "Request Reviews",
                "action_url": "#"
            })
        
        return insights

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

    @staticmethod
    def available_units(room_type_id: int, check_in: date, check_out: date) -> int:
        """
        Calculate available units for a room type during a date range.
        
        Uses the formula: total_units - confirmed_bookings - blocked_units
        This is the real availability logic for multi-unit properties.
        """
        room_type = RoomType.query.get(room_type_id)
        if not room_type:
            return 0
        
        # Count confirmed bookings overlapping the date range
        # A booking overlaps if: check_in < check_out AND check_out > check_in
        booked = (
            db.session.query(func.count(AccommodationBooking.id))
            .filter(
                AccommodationBooking.room_type_id == room_type_id,
                AccommodationBooking.status.in_(ACTIVE_BOOKING_STATUSES),
                AccommodationBooking.check_in < check_out,
                AccommodationBooking.check_out > check_in,
            )
            .scalar()
        ) or 0
        
        # Sum blocked units from inventory blocks overlapping the date range
        blocked = (
            db.session.query(func.coalesce(func.sum(InventoryBlock.units_blocked), 0))
            .filter(
                InventoryBlock.room_type_id == room_type_id,
                InventoryBlock.date_range_start < check_out,
                InventoryBlock.date_range_end > check_in,
            )
            .scalar()
        ) or 0
        
        return room_type.total_units - booked - blocked
