"""Host-facing operations for the accommodation module."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, date, timezone
from decimal import Decimal
from typing import Dict, Iterable, List, Optional, Tuple

from sqlalchemy import func, and_, desc

from app.extensions import db
from app.accommodation.utils import enum_value
from app.utils.slugs import slugify, ensure_unique_slug
from app.accommodation.models.property import (
    AccommodationCancellationPolicy,
    AccommodationPropertyStatus,
    AccommodationPropertyType,
    Property,
)
from app.accommodation.models.room import Room, RoomType, InventoryBlock
from app.accommodation.models.booking import (
    AccommodationBooking,
    AccommodationBookingStatus,
)
from app.accommodation.models.property_payment_method import PropertyPaymentMethod
from app.wallet import PaymentMethodConfig

# Active booking statuses for availability calculation
ACTIVE_BOOKING_STATUSES = [
    AccommodationBookingStatus.CONFIRMED.value,
    AccommodationBookingStatus.CHECKED_IN.value,
    AccommodationBookingStatus.PENDING.value,
]


_SLUG_RE = re.compile(r"[^a-z0-9]+")


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


def convert_enum_values(data):
    """Recursively convert Python Enum objects to their string values.

    SQLAlchemy cannot adapt Enum members to the String columns used in this
    project (no PostgreSQL ENUM types), so any enum must be reduced to .value
    before hitting the session. Handles nested dicts and lists.
    """
    import enum

    if isinstance(data, dict):
        return {k: convert_enum_values(v) for k, v in data.items()}
    if isinstance(data, (list, tuple)):
        return [convert_enum_values(v) for v in data]
    if isinstance(data, enum.Enum):
        return data.value
    return data


class HostService:
    """Encapsulates host listing management and dashboard aggregation."""

    @staticmethod
    def create_property(data: Dict, *, owner_user_id: Optional[int], owner_org_id: Optional[int]) -> Property:
        """Persist a new property from validated form data.
        
        Auto-creates a default RoomType with total_units=1 for every property,
        individual or organisation-owned, so it is immediately bookable.
        Organisation hosts can add additional RoomTypes afterward via Room Type
        Management or bulk import.
        """
        title = data["title"].strip()
        slug = ensure_unique_slug(slugify(title), db.session, Property)

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
            status="pending_review",
            is_active=False,
            is_verified=False,
        )

        db.session.add(prop)
        db.session.flush()
        
        # Auto-create a default RoomType for every new property (total_units=1).
        # Organisation hosts can add more RoomTypes afterward via Room Type Management
        # or bulk import — this just guarantees every property is bookable from creation.
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

        # Auto-create default property payment methods so every new property
        # is immediately bookable. Start with wallet; additional methods are
        # only enabled globally if PaymentMethodConfig.initialize_defaults()
        # has run in the environment.
        enabled_methods = PropertyPaymentMethod.query.filter_by(
            property_id=prop.id, enabled=True
        ).all()
        if not enabled_methods:
            wallet_method = PaymentMethodConfig.query.filter_by(
                method_id='wallet',
                is_enabled=True,
                is_active=True,
            ).first()
            if wallet_method:
                db.session.add(
                    PropertyPaymentMethod(
                        property_id=prop.id,
                        wallet_method_id=wallet_method.id,
                        enabled=True,
                    )
                )

        return prop

    @staticmethod
    def update_property(prop: Property, data: Dict) -> Property:
        """Update an existing property with validated form data."""
        # Reduce any Enum members to their string .value before persistence.
        # The project stores these as String columns (no PostgreSQL ENUM types),
        # so SQLAlchemy would otherwise fail to adapt the enum objects.
        data = convert_enum_values(data)

        prop.title = data["title"].strip()
        prop.summary = data.get("summary")
        prop.description = data["description"].strip()
        prop.property_type = data["property_type"]
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
        prop.cancellation_policy = data["cancellation_policy"]
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
        
        # Sync default RoomType if there is exactly one single-unit room type
        default_rt = RoomType.query.filter_by(property_id=prop.id).order_by(RoomType.id.asc()).first()
        if default_rt and default_rt.total_units == 1 and RoomType.query.filter_by(property_id=prop.id).count() == 1:
            default_rt.max_guests = prop.max_guests
            default_rt.bedrooms = prop.bedrooms
            default_rt.beds = prop.beds
            default_rt.bathrooms = prop.bathrooms
            default_rt.base_price_per_night = prop.base_price_per_night
            default_rt.currency = prop.currency
            default_rt.cleaning_fee = prop.cleaning_fee
            default_rt.service_fee_pct = prop.service_fee_pct

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
        active_properties = [p for p in properties if p.status == "active" and p.is_active]
        pending_properties = [p for p in properties if p.status == "pending_review"]
        draft_properties = [p for p in properties if p.status == "draft"]
        suspended_properties = [p for p in properties if p.status == "suspended"]
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
                     AccommodationBookingStatus.PENDING.value,
                     AccommodationBookingStatus.PENDING_APPROVAL.value]
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
                AccommodationBookingStatus.PENDING_APPROVAL.value,
            ])
        ).count()

        # ── Advanced Analytics ───────────────────────────────────────
        advanced_analytics = HostService.get_advanced_analytics(
            owner_user_id=owner_user_id,
            owner_org_id=owner_org_id,
            properties=properties,
        )

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
            # Advanced analytics
            "advanced_metrics": advanced_analytics["advanced_metrics"],
            "performance_metrics": advanced_analytics["performance_metrics"],
            "guest_intelligence": advanced_analytics["guest_intelligence"],
            "competitive_intelligence": advanced_analytics["competitive_intelligence"],
            "ai_insights": advanced_analytics["ai_insights"],
            "revenue_forecast": advanced_analytics["revenue_forecast"],
            "channel_performance": advanced_analytics["channel_performance"],
            "seasonal_trends": advanced_analytics["seasonal_trends"],
            "booking_velocity": advanced_analytics["booking_velocity"],
            "last_updated": datetime.now(timezone.utc).isoformat()
        }

    @staticmethod
    def get_admin_dashboard_stats() -> Dict:
        """Return platform-wide accommodation stats for the admin dashboard."""
        # Base queries without owner filters
        properties = Property.query.filter(Property.is_deleted.is_(False)).all()
        active_properties = [p for p in properties if p.status == "active" and p.is_active]

        total_properties = len(properties)
        total_bookings = AccommodationBooking.query.count()
        active_hosts = (
            db.session.query(func.count(func.distinct(Property.owner_user_id)))
            .filter(Property.is_deleted.is_(False), Property.is_active.is_(True), Property.owner_user_id.is_not(None))
            .scalar()
            or 0
        )

        rated = [p for p in properties if p.overall_rating and p.total_reviews > 0]
        average_rating = round(sum(p.overall_rating for p in rated) / len(rated), 1) if rated else 4.5

        # Simple month-over-month growth placeholders
        this_month = date.today().replace(day=1)
        last_month = (this_month - timedelta(days=1)).replace(day=1)
        next_month = (this_month.replace(day=28) + timedelta(days=4)).replace(day=1)
        last_month_end = this_month - timedelta(days=1)

        properties_this_month = (
            Property.query.filter(
                Property.is_deleted.is_(False),
                Property.created_at >= this_month,
                Property.created_at < next_month,
            ).count()
            if 'created_at' in Property.__table__.c else 0
        )
        properties_last_month = (
            Property.query.filter(
                Property.is_deleted.is_(False),
                Property.created_at >= last_month,
                Property.created_at < this_month,
            ).count()
            if 'created_at' in Property.__table__.c else 0
        )

        bookings_this_month = (
            AccommodationBooking.query.filter(
                AccommodationBooking.created_at >= this_month,
                AccommodationBooking.created_at < next_month,
            ).count()
            if 'created_at' in AccommodationBooking.__table__.c else 0
        )
        bookings_last_month = (
            AccommodationBooking.query.filter(
                AccommodationBooking.created_at >= last_month,
                AccommodationBooking.created_at < this_month,
            ).count()
            if 'created_at' in AccommodationBooking.__table__.c else 0
        )

        def _growth(current: int, previous: int) -> str:
            if previous <= 0:
                return "+0%" if current >= 0 else "0%"
            change = ((current - previous) / previous) * 100
            sign = "+" if change >= 0 else ""
            return f"{sign}{change:.1f}%"

        property_growth = _growth(properties_this_month, properties_last_month)
        bookings_growth = _growth(bookings_this_month, bookings_last_month)

        if active_hosts > 0 and bookings_this_month > 0:
            host_status = "Growing"
        elif active_hosts > 0:
            host_status = "Stable"
        else:
            host_status = "New"

        rating_change = "+0.2"

        return {
            "total_properties": total_properties,
            "total_bookings": total_bookings,
            "active_hosts": active_hosts,
            "average_rating": average_rating,
            "property_growth": property_growth,
            "bookings_growth": bookings_growth,
            "host_status": host_status,
            "rating_change": rating_change,
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

    # ------------------------------------------------------------------
    # ADVANCED ANALYTICS
    # ------------------------------------------------------------------

    @staticmethod
    def get_advanced_analytics(
        *,
        owner_user_id: Optional[int],
        owner_org_id: Optional[int],
        properties: List[Property],
    ) -> Dict:
        """
        Compute all advanced analytics for the host dashboard.

        Returns a single dict with the following keys:
          - performance_metrics  (ADR, RevPAR, lead_time, cancellation_rate)
          - guest_intelligence   (repeat_guest_rate, guest_ltv, satisfaction_trend)
          - competitive_intelligence (market_avg_rate, market_occupancy, etc.)
          - revenue_forecast     (next 30/60/90 day projections)
          - channel_performance  (per-channel booking & revenue breakdown)
          - seasonal_trends      (high / shoulder / low months)
          - booking_velocity     (daily / weekly / monthly booking cadence)
          - advanced_metrics     (avg booking value, length of stay, distribution)
          - ai_insights          (smart recommendations list)
        """
        if not properties:
            return HostService._empty_analytics()

        property_ids = [p.id for p in properties]

        # ── Build the base booking queryset once ─────────────────────
        bq = AccommodationBooking.query.filter(
            AccommodationBooking.property_id.in_(property_ids)
        )

        # Completed/revenue-generating bookings
        revenue_statuses = [
            AccommodationBookingStatus.CONFIRMED.value,
            AccommodationBookingStatus.CHECKED_IN.value,
            AccommodationBookingStatus.CHECKED_OUT.value,
        ]
        revenue_bookings = bq.filter(
            AccommodationBooking.status.in_(revenue_statuses)
        ).all()

        all_bookings = bq.all()

        performance_metrics = HostService._calc_performance_metrics(
            properties, revenue_bookings, all_bookings
        )
        guest_intelligence = HostService._calc_guest_intelligence(
            properties, revenue_bookings
        )
        competitive_intelligence = HostService._calc_competitive_intelligence(
            properties, performance_metrics
        )
        booking_velocity = HostService._calc_booking_velocity(
            property_ids
        )
        advanced_metrics = HostService._calc_advanced_metrics(
            properties, revenue_bookings
        )
        revenue_forecast = HostService._calc_revenue_forecast(revenue_bookings)
        channel_performance = HostService._calc_channel_performance(revenue_bookings)
        seasonal_trends = HostService._calc_seasonal_trends(revenue_bookings)
        ai_insights = HostService._generate_ai_insights(
            advanced_metrics=advanced_metrics,
            performance_metrics=performance_metrics,
            competitive_intelligence=competitive_intelligence,
            guest_intelligence=guest_intelligence,
        )

        return {
            "performance_metrics": performance_metrics,
            "guest_intelligence": guest_intelligence,
            "competitive_intelligence": competitive_intelligence,
            "revenue_forecast": revenue_forecast,
            "channel_performance": channel_performance,
            "seasonal_trends": seasonal_trends,
            "booking_velocity": booking_velocity,
            "advanced_metrics": advanced_metrics,
            "ai_insights": ai_insights,
        }

    # ── Performance Metrics ──────────────────────────────────────────

    @staticmethod
    def _calc_performance_metrics(
        properties: List[Property],
        revenue_bookings: list,
        all_bookings: list,
    ) -> Dict:
        """ADR, RevPAR, avg lead time, cancellation rate."""
        total_properties = len(properties)

        # ADR: average of active properties' base nightly rates
        active_prices = [
            float(p.base_price_per_night)
            for p in properties
            if p.status == "active"
            and p.base_price_per_night
        ]
        avg_daily_rate = round(sum(active_prices) / len(active_prices), 2) if active_prices else 0.0

        # RevPAR: total revenue / total properties (simplified)
        total_revenue = sum(float(b.total_amount or 0) for b in revenue_bookings)
        revpar = round(total_revenue / total_properties, 2) if total_properties else 0.0

        # Avg booking lead time
        lead_times = []
        for b in revenue_bookings:
            if b.created_at and b.check_in:
                check_in_dt = (
                    datetime.combine(b.check_in, datetime.min.time())
                    if isinstance(b.check_in, date) and not isinstance(b.check_in, datetime)
                    else b.check_in
                )
                created = b.created_at.replace(tzinfo=None) if b.created_at.tzinfo else b.created_at
                delta = (check_in_dt - created).days
                if delta >= 0:
                    lead_times.append(delta)
        avg_lead_time = round(sum(lead_times) / len(lead_times), 1) if lead_times else 0.0

        # Cancellation rate
        total_all = len(all_bookings)
        cancelled = sum(
            1 for b in all_bookings
            if b.status == AccommodationBookingStatus.CANCELLED.value
        )
        cancellation_rate = round((cancelled / total_all * 100), 1) if total_all else 0.0

        return {
            "avg_daily_rate": avg_daily_rate,
            "revenue_per_available_room": revpar,
            "booking_lead_time": avg_lead_time,
            "cancellation_rate": cancellation_rate,
        }

    # ── Guest Intelligence ───────────────────────────────────────────

    @staticmethod
    def _calc_guest_intelligence(
        properties: List[Property],
        revenue_bookings: list,
    ) -> Dict:
        """Repeat guest rate, guest LTV, satisfaction trend."""
        # Repeat guest rate
        guest_counts: Dict[int, int] = {}
        for b in revenue_bookings:
            if b.guest_user_id:
                guest_counts[b.guest_user_id] = guest_counts.get(b.guest_user_id, 0) + 1

        total_guests = len(guest_counts)
        repeat_guests = sum(1 for cnt in guest_counts.values() if cnt > 1)
        repeat_guest_rate = round((repeat_guests / total_guests * 100), 1) if total_guests else 0.0

        # Guest LTV: average total spend per guest
        guest_spend: Dict[int, float] = {}
        for b in revenue_bookings:
            if b.guest_user_id:
                guest_spend[b.guest_user_id] = (
                    guest_spend.get(b.guest_user_id, 0.0) + float(b.total_amount or 0)
                )
        guest_ltv = (
            round(sum(guest_spend.values()) / len(guest_spend), 2)
            if guest_spend
            else 0.0
        )

        # Satisfaction trend via reviews
        property_ids = [p.id for p in properties]
        try:
            from app.accommodation.models.review import Review, AccommodationReviewStatus
            reviews = (
                Review.query.filter(
                    Review.property_id.in_(property_ids),
                    Review.is_published.is_(True),
                )
                .order_by(Review.created_at.asc())
                .all()
            )
        except Exception:
            reviews = []

        if len(reviews) >= 2:
            half = len(reviews) // 2
            avg_first = sum(r.overall_rating for r in reviews[:half]) / half
            avg_second = sum(r.overall_rating for r in reviews[half:]) / (len(reviews) - half)
            change = round(avg_second - avg_first, 2)
            current_rating = round(avg_second, 2)
            trend = "up" if change > 0.2 else ("down" if change < -0.2 else "stable")
        elif reviews:
            current_rating = round(reviews[-1].overall_rating, 2)
            change = 0.0
            trend = "stable"
        else:
            current_rating = 0.0
            change = 0.0
            trend = "stable"

        return {
            "repeat_guest_rate": repeat_guest_rate,
            "guest_lifetime_value": guest_ltv,
            "satisfaction_trend": {
                "trend": trend,
                "current_rating": current_rating,
                "change": change,
            },
        }

    # ── Competitive Intelligence ─────────────────────────────────────

    @staticmethod
    def _calc_competitive_intelligence(
        properties: List[Property],
        performance_metrics: Dict,
    ) -> Dict:
        """
        Market benchmarks derived from other active listings in the same cities.
        Falls back to sensible placeholders when no peer data exists.
        """
        cities = list({p.city for p in properties if p.city})

        peers: List[Property] = []
        if cities:
            try:
                peers = (
                    Property.query.filter(
                        Property.city.in_(cities),
                        Property.status == "active",
                        Property.is_active.is_(True),
                        Property.is_deleted.is_(False),
                        Property.id.notin_([p.id for p in properties]),
                    )
                    .all()
                )
            except Exception:
                peers = []

        if peers:
            peer_prices = [float(p.base_price_per_night) for p in peers if p.base_price_per_night]
            market_avg_rate = round(sum(peer_prices) / len(peer_prices), 2) if peer_prices else 120.0
            competitor_count = len(peers)
            # Simplified occupancy: use total_bookings / total_capacity ratio
            total_cap = sum(p.max_guests for p in peers)
            total_bkd = sum(p.total_bookings for p in peers)
            market_occupancy = round((total_bkd / total_cap * 100), 1) if total_cap else 65.0
        else:
            market_avg_rate = 120.0
            competitor_count = 0
            market_occupancy = 65.0

        # Demand index (0-100): based on competitor bookings density
        market_demand_index = min(100, round(market_occupancy * 1.3)) if market_occupancy else 70

        # Price positioning
        adr = performance_metrics.get("avg_daily_rate", 0.0)
        if market_avg_rate > 0 and adr > 0:
            diff_pct = round(((adr - market_avg_rate) / market_avg_rate) * 100, 1)
            if diff_pct > 5:
                position = "above_average"
                description = f"Your rates are {abs(diff_pct)}% above the local market average."
            elif diff_pct < -5:
                position = "below_average"
                description = f"Your rates are {abs(diff_pct)}% below the local market average."
            else:
                position = "at_market"
                description = "Your rates are in line with the local market average."
        else:
            diff_pct = 0.0
            position = "unknown"
            description = "Not enough market data to assess price positioning."

        return {
            "market_avg_rate": market_avg_rate,
            "market_occupancy": market_occupancy,
            "competitor_count": competitor_count,
            "market_demand_index": market_demand_index,
            "price_positioning": {
                "position": position,
                "difference": diff_pct,
                "description": description,
            },
        }

    # ── Booking Velocity ─────────────────────────────────────────────

    @staticmethod
    def _calc_booking_velocity(property_ids: List[int]) -> Dict:
        """Bookings created in the last 30 days expressed as daily/weekly/monthly rate."""
        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
        count = (
            AccommodationBooking.query.filter(
                AccommodationBooking.property_id.in_(property_ids),
                AccommodationBooking.created_at >= thirty_days_ago,
            ).count()
            if property_ids
            else 0
        )
        daily = round(count / 30, 2)
        weekly = round(count / (30 / 7), 1)
        return {
            "daily": daily,
            "weekly": weekly,
            "monthly": count,
        }

    # ── Advanced Metrics ─────────────────────────────────────────────

    @staticmethod
    def _calc_advanced_metrics(
        properties: List[Property],
        revenue_bookings: list,
    ) -> Dict:
        """Avg booking value, avg length of stay, weekday/weekend split, revenue growth."""
        total = len(revenue_bookings)

        if total == 0:
            return {
                "avg_booking_value": 0.0,
                "avg_length_of_stay": 0.0,
                "weekday_bookings": 0,
                "weekend_bookings": 0,
                "revenue_growth": 0.0,
            }

        avg_value = round(sum(float(b.total_amount or 0) for b in revenue_bookings) / total, 2)

        los_list = [
            (
                (b.check_out - b.check_in).days
                if isinstance(b.check_out, date) and isinstance(b.check_in, date)
                else b.num_nights or 0
            )
            for b in revenue_bookings
        ]
        avg_los = round(sum(los_list) / len(los_list), 1) if los_list else 0.0

        weekday = sum(1 for b in revenue_bookings if isinstance(b.check_in, date) and b.check_in.weekday() < 5)
        weekend = total - weekday

        # Month-over-month revenue growth
        now = datetime.now(timezone.utc)
        this_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        prev_month_end = this_month_start - timedelta(seconds=1)
        prev_month_start = prev_month_end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        def _month_rev(start: datetime, end: datetime) -> float:
            # Make both boundaries naive for consistent comparisons
            start = start.replace(tzinfo=None)
            end = end.replace(tzinfo=None)
            return sum(
                float(b.total_amount or 0)
                for b in revenue_bookings
                if b.created_at and start <= b.created_at.replace(tzinfo=None) <= end
            )

        rev_this = _month_rev(this_month_start, now)
        rev_prev = _month_rev(prev_month_start, prev_month_end)
        revenue_growth = (
            round(((rev_this - rev_prev) / rev_prev) * 100, 1) if rev_prev > 0 else 0.0
        )

        return {
            "avg_booking_value": avg_value,
            "avg_length_of_stay": avg_los,
            "weekday_bookings": weekday,
            "weekend_bookings": weekend,
            "revenue_growth": revenue_growth,
        }

    # ── Revenue Forecast ─────────────────────────────────────────────

    @staticmethod
    def _calc_revenue_forecast(revenue_bookings: list) -> Dict:
        """
        Project revenue for the next 30 / 60 / 90 days based on the average
        daily revenue observed over the trailing 90-day window.
        """
        ninety_days_ago = (datetime.now(timezone.utc) - timedelta(days=90)).replace(tzinfo=None)
        trailing = [
            float(b.total_amount or 0)
            for b in revenue_bookings
            if b.created_at and b.created_at.replace(tzinfo=None) >= ninety_days_ago
        ]
        daily_avg = sum(trailing) / 90 if trailing else 0.0

        confidence = "high" if len(trailing) >= 20 else ("medium" if len(trailing) >= 5 else "low")

        return {
            "next_30_days": round(daily_avg * 30, 2),
            "next_60_days": round(daily_avg * 60, 2),
            "next_90_days": round(daily_avg * 90, 2),
            "confidence": confidence,
        }

    # ── Channel Performance ──────────────────────────────────────────

    @staticmethod
    def _calc_channel_performance(revenue_bookings: list) -> List[Dict]:
        """
        Break down bookings and revenue by booking source.
        We use the `context_type` field as a proxy for channel.
        """
        channels: Dict[str, Dict] = {}
        for b in revenue_bookings:
            channel = (b.context_type or "direct").replace("_", " ").title()
            if channel == "None":
                channel = "Direct"
            if channel not in channels:
                channels[channel] = {"bookings": 0, "revenue": 0.0}
            channels[channel]["bookings"] += 1
            channels[channel]["revenue"] += float(b.total_amount or 0)

        if not channels:
            return [{"channel": "Direct", "bookings": 0, "revenue": 0.0}]

        total_revenue = sum(c["revenue"] for c in channels.values()) or 1
        result = []
        for name, data in sorted(channels.items(), key=lambda x: -x[1]["revenue"]):
            result.append({
                "channel": name,
                "bookings": data["bookings"],
                "revenue": round(data["revenue"], 2),
                "pct": round(data["revenue"] / total_revenue * 100),
            })
        return result

    # ── Seasonal Trends ──────────────────────────────────────────────

    @staticmethod
    def _calc_seasonal_trends(revenue_bookings: list) -> Dict:
        """
        Rank each calendar month by total revenue and classify the top third as
        high season, bottom third as low season, and the rest as shoulder.
        Falls back to a sensible default when there is no historical data.
        """
        import calendar as _calendar

        month_revenue: Dict[int, float] = {m: 0.0 for m in range(1, 13)}
        for b in revenue_bookings:
            if b.check_in and isinstance(b.check_in, date):
                month_revenue[b.check_in.month] += float(b.total_amount or 0)

        total = sum(month_revenue.values())
        if total == 0:
            # Default pattern for a football-tournament platform
            return {
                "high_season": ["June", "July", "August"],
                "shoulder_season": ["April", "May", "September", "October"],
                "low_season": ["January", "February", "March", "November", "December"],
            }

        sorted_months = sorted(month_revenue.items(), key=lambda x: -x[1])
        n = 4  # approx 1/3 of 12 months
        high = [_calendar.month_name[m] for m, _ in sorted_months[:n]]
        low = [_calendar.month_name[m] for m, _ in sorted_months[-n:]]
        shoulder = [
            _calendar.month_name[m]
            for m, _ in sorted_months[n:-n]
        ]

        return {
            "high_season": high,
            "shoulder_season": shoulder,
            "low_season": low,
        }

    # ── AI Insights ──────────────────────────────────────────────────

    @staticmethod
    def _generate_ai_insights(
        *,
        advanced_metrics: Dict,
        performance_metrics: Dict,
        competitive_intelligence: Dict,
        guest_intelligence: Dict,
    ) -> List[Dict]:
        """Generate smart, context-driven recommendations for the host."""
        insights: List[Dict] = []

        # Revenue growth
        growth = advanced_metrics.get("revenue_growth", 0)
        if growth >= 10:
            insights.append({
                "icon": "🚀",
                "type": "success",
                "title": f"Revenue up {growth}% this month",
                "description": "Excellent momentum! Consider raising rates slightly to maximise returns.",
                "action_text": "Adjust Pricing",
                "action_url": "accommodation.host_dashboard",
            })
        elif growth < -10:
            insights.append({
                "icon": "📉",
                "type": "warning",
                "title": f"Revenue down {abs(growth)}% this month",
                "description": "Review your pricing and listing quality to recover bookings.",
                "action_text": "Review Listings",
                "action_url": "accommodation.host_dashboard",
            })

        # Price positioning
        pos = competitive_intelligence.get("price_positioning", {})
        if pos.get("position") == "above_average" and pos.get("difference", 0) > 15:
            insights.append({
                "icon": "💰",
                "type": "warning",
                "title": "Rates significantly above market",
                "description": pos.get("description", ""),
                "action_text": "Review Pricing",
                "action_url": "accommodation.host_dashboard",
            })
        elif pos.get("position") == "below_average":
            insights.append({
                "icon": "📈",
                "type": "info",
                "title": "Opportunity to raise rates",
                "description": pos.get("description", ""),
                "action_text": "Optimise Pricing",
                "action_url": "accommodation.host_dashboard",
            })

        # Cancellation rate
        cancel_rate = performance_metrics.get("cancellation_rate", 0)
        if cancel_rate > 15:
            insights.append({
                "icon": "⚠️",
                "type": "warning",
                "title": f"High cancellation rate: {cancel_rate}%",
                "description": "Consider reviewing your cancellation policy or listing accuracy.",
                "action_text": "Edit Listings",
                "action_url": "accommodation.host_dashboard",
            })

        # Repeat guests
        repeat_rate = guest_intelligence.get("repeat_guest_rate", 0)
        if repeat_rate >= 25:
            insights.append({
                "icon": "🔄",
                "type": "success",
                "title": f"{repeat_rate}% of guests return",
                "description": "Strong guest loyalty! Keep delivering great experiences.",
                "action_text": "View Bookings",
                "action_url": "accommodation.host_bookings",
            })
        elif repeat_rate < 10 and repeat_rate >= 0:
            insights.append({
                "icon": "💌",
                "type": "info",
                "title": "Low repeat guest rate",
                "description": "Personal thank-you messages and special return offers can build loyalty.",
                "action_text": "View Bookings",
                "action_url": "accommodation.host_bookings",
            })

        # Satisfaction trend
        sat = guest_intelligence.get("satisfaction_trend", {})
        if sat.get("trend") == "up":
            insights.append({
                "icon": "⭐",
                "type": "success",
                "title": "Guest satisfaction is improving",
                "description": f"Ratings trending up by {sat.get('change', 0):.2f} stars. Great work!",
                "action_text": "See Reviews",
                "action_url": "accommodation.host_dashboard",
            })
        elif sat.get("trend") == "down":
            insights.append({
                "icon": "📝",
                "type": "warning",
                "title": "Guest satisfaction is declining",
                "description": f"Ratings down by {abs(sat.get('change', 0)):.2f} stars. Review recent feedback.",
                "action_text": "See Reviews",
                "action_url": "accommodation.host_dashboard",
            })

        # Demand index
        demand = competitive_intelligence.get("market_demand_index", 0)
        if demand >= 80:
            insights.append({
                "icon": "🔥",
                "type": "success",
                "title": "High market demand in your area",
                "description": f"Demand index is {demand}/100. Ensure your calendar is up to date.",
                "action_text": "Open Calendar",
                "action_url": "accommodation.host_calendar",
            })

        # Fallback
        if not insights:
            insights.append({
                "icon": "🎉",
                "type": "success",
                "title": "Everything looks great!",
                "description": "Your property is performing well. Keep monitoring your analytics.",
                "action_text": "View Dashboard",
                "action_url": "accommodation.host_dashboard",
            })

        return insights

    # ── Empty fallback ───────────────────────────────────────────────

    @staticmethod
    def _empty_analytics() -> Dict:
        return {
            "performance_metrics": {
                "avg_daily_rate": 0.0,
                "revenue_per_available_room": 0.0,
                "booking_lead_time": 0.0,
                "cancellation_rate": 0.0,
            },
            "guest_intelligence": {
                "repeat_guest_rate": 0.0,
                "guest_lifetime_value": 0.0,
                "satisfaction_trend": {"trend": "stable", "current_rating": 0.0, "change": 0.0},
            },
            "competitive_intelligence": {
                "market_avg_rate": 0.0,
                "market_occupancy": 0.0,
                "competitor_count": 0,
                "market_demand_index": 0,
                "price_positioning": {"position": "unknown", "difference": 0.0, "description": "No data yet."},
            },
            "revenue_forecast": {"next_30_days": 0.0, "next_60_days": 0.0, "next_90_days": 0.0, "confidence": "low"},
            "channel_performance": [{"channel": "Direct", "bookings": 0, "revenue": 0.0, "pct": 100}],
            "seasonal_trends": {"high_season": [], "shoulder_season": [], "low_season": []},
            "booking_velocity": {"daily": 0.0, "weekly": 0.0, "monthly": 0},
            "advanced_metrics": {
                "avg_booking_value": 0.0,
                "avg_length_of_stay": 0.0,
                "weekday_bookings": 0,
                "weekend_bookings": 0,
                "revenue_growth": 0.0,
            },
            "ai_insights": [{
                "icon": "🚀",
                "type": "info",
                "title": "Start hosting today!",
                "description": "Create your first listing to unlock analytics.",
                "action_text": "Create Listing",
                "action_url": "accommodation.host_create_listing",
            }],
        }

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
                "status": enum_value(prop.status) if prop.status else None,
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
        room_type_id: Optional[int] = None,
    ) -> Dict:
        """Return blocked dates, bookings, and availability indicators for UI."""

        if end_date < start_date:
            raise ValueError("end_date must be on or after start_date")

        # Pull property for context
        prop = Property.query.get_or_404(property_id)

        # Collect bookings overlapping window (property-level)
        bookings = (
            AccommodationBooking.query.filter(
                AccommodationBooking.property_id == property_id,
                AccommodationBooking.check_out >= start_date,
                AccommodationBooking.check_in <= end_date,
                AccommodationBooking.status.in_(ACTIVE_BOOKING_STATUSES),
            )
            .order_by(AccommodationBooking.check_in.asc())
            .all()
        )

        # Collect room types for the property (optionally scoped)
        room_types_q = RoomType.query.filter_by(property_id=property_id, is_active=True)
        if room_type_id:
            room_types_q = room_types_q.filter_by(id=room_type_id)
        room_types = room_types_q.all()

        # If scoping by room types, also scope bookings to those room types
        if room_types:
            room_type_ids = [rt.id for rt in room_types]
            bookings = [b for b in bookings if b.room_type_id in room_type_ids]

            # Collect inventory blocks overlapping window for selected room types
            inventory_blocks = (
                InventoryBlock.query.filter(
                    InventoryBlock.room_type_id.in_(room_type_ids),
                    InventoryBlock.date_range_start <= end_date,
                    InventoryBlock.date_range_end >= start_date,
                )
                .all()
            )
        else:
            inventory_blocks = []

        # Property-level manual blocks (owner blocked / maintenance / seasonal / holds)
        from app.accommodation.models.availability import BlockedDate

        blocked_rows = (
            BlockedDate.query.filter(
                BlockedDate.property_id == property_id,
                BlockedDate.blocked_date >= start_date,
                BlockedDate.blocked_date <= end_date,
            ).all()
        )
        blocked_map = {row.blocked_date: row for row in blocked_rows}

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

            # 1. Determine availability status using RoomType/InventoryBlock if room types exist
            if room_types:
                total_available = 0
                for rt in room_types:
                    day_bookings_count = sum(
                        1 for b in bookings 
                        if b.room_type_id == rt.id and b.check_in <= cursor < b.check_out
                    )
                    day_blocks = sum(
                        ib.units_blocked for ib in inventory_blocks
                        if ib.room_type_id == rt.id and ib.date_range_start <= cursor <= ib.date_range_end
                    )
                    total_available += max(0, rt.total_units - day_bookings_count - day_blocks)
                
                if total_available <= 0:
                    day_bookings = [b for b in bookings if b.check_in <= cursor < b.check_out]
                    if day_bookings:
                        day_info["status"] = "booked"
                    else:
                        day_info["status"] = "blocked"
                        blocks_on_day = [ib for ib in inventory_blocks if ib.date_range_start <= cursor <= ib.date_range_end]
                        if blocks_on_day:
                            day_info["blocked_reason"] = blocks_on_day[0].reason if blocks_on_day[0].reason else "Inventory Block"
                        else:
                            day_info["blocked_reason"] = "Inventory Block"
            else:
                # Fallback if no room types
                day_bookings = [b for b in bookings if b.check_in <= cursor < b.check_out]
                if day_bookings:
                    day_info["status"] = "booked"

            # 2. Property-level manual blocks override "available"
            manual_block = blocked_map.get(cursor)
            if manual_block is not None:
                reason_value = enum_value(manual_block.reason) or "owner_blocked"
                if reason_value == "booked":
                    day_info["status"] = "booked"
                else:
                    day_info["status"] = "blocked"
                    day_info["blocked_reason"] = reason_value

            # 3. Populate detailed bookings for that day
            for booking in bookings:
                if booking.check_in <= cursor < booking.check_out:
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

            days.append(day_info)
            cursor += timedelta(days=1)

        return {
            "property": {
                "id": prop.id,
                "title": prop.title,
                "status": enum_value(prop.status) if prop.status else None,
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
                    "date": row.blocked_date.isoformat(),
                    "reason": enum_value(row.reason),
                    "note": row.note,
                    "booking_id": row.booking_id,
                }
                for row in sorted(blocked_rows, key=lambda r: r.blocked_date)
            ],
        }

    @staticmethod
    def available_units(room_type_id: int, check_in: date, check_out: date, exclude_booking_id: Optional[int] = None) -> int:
        """
        Calculate available units for a room type during a date range.
        
        Uses the formula: total_units - confirmed_bookings - blocked_units
        This is the real availability logic for multi-unit properties.
        """
        room_type = db.session.get(RoomType, room_type_id)
        if not room_type:
            return 0
        
        # Count confirmed bookings overlapping the date range
        # A booking overlaps if: check_in < check_out AND check_out > check_in
        bookings_query = db.session.query(func.count(AccommodationBooking.id)).filter(
            AccommodationBooking.room_type_id == room_type_id,
            AccommodationBooking.status.in_(ACTIVE_BOOKING_STATUSES),
            AccommodationBooking.check_in < check_out,
            AccommodationBooking.check_out > check_in,
        )
        if exclude_booking_id:
            bookings_query = bookings_query.filter(AccommodationBooking.id != exclude_booking_id)
            
        booked = bookings_query.scalar() or 0
        
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

    @staticmethod
    def sync_room_type_inventory(property_id: int) -> None:
        room_types = RoomType.query.filter_by(property_id=property_id).all()

        for rt in room_types:
            count = Room.query.filter_by(property_id=property_id, room_type_id=rt.id).count()
            rt.total_units = count

        db.session.commit()

