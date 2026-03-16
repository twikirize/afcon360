# app/transport/api/analytic_routes.py
"""
AFCON360 Transport — Analytics REST API
Provides summary, revenue, and performance metrics for the admin dashboard
and external reporting tools.

All endpoints are admin-only and return pre-aggregated data.
Heavy queries use SQLAlchemy func aggregations — no raw SQL.
"""
from flask import request
from flask_restful import Resource
from app.extensions import db
from app.transport.models import (
    Booking, BookingPayment, DriverProfile,
    Vehicle, TransportIncident, Rating,
    BookingStatus, PaymentStatus, ComplianceStatus
)
from app.admin.routes import admin_required
from datetime import datetime, timedelta, timezone
from sqlalchemy import func, case, and_
import logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_date_range():
    """
    Parse from_date / to_date from query string.
    Defaults to the last 30 days if not provided.
    Returns (from_dt, to_dt) as timezone-aware datetimes.
    """
    now = datetime.now(timezone.utc)
    default_from = now - timedelta(days=30)

    from_str = request.args.get("from_date")
    to_str = request.args.get("to_date")

    try:
        from_dt = datetime.fromisoformat(from_str).replace(tzinfo=timezone.utc) if from_str else default_from
        to_dt = datetime.fromisoformat(to_str).replace(tzinfo=timezone.utc) if to_str else now
    except ValueError:
        from_dt = default_from
        to_dt = now

    return from_dt, to_dt


def _booking_base(from_dt, to_dt):
    """Base booking query scoped to date range."""
    return Booking.query.filter(
        Booking.is_deleted == False,
        Booking.created_at >= from_dt,
        Booking.created_at <= to_dt,
    )


# ===========================================================================
# Summary Analytics
# ===========================================================================

class AnalyticsSummaryResource(Resource):
    """GET /api/transport/analytics/summary"""

    @admin_required
    def get(self):
        """
        High-level KPI summary:
        - Total bookings, breakdown by status
        - Completion rate, cancellation rate
        - Active drivers and vehicles
        - Open incidents
        """
        from_dt, to_dt = _parse_date_range()

        # --- Booking counts by status ---
        status_counts = (
            db.session.query(Booking.status, func.count(Booking.id))
            .filter(
                Booking.is_deleted == False,
                Booking.created_at.between(from_dt, to_dt),
            )
            .group_by(Booking.status)
            .all()
        )
        by_status = {s.value: c for s, c in status_counts}
        total_bookings = sum(by_status.values())

        completed = by_status.get(BookingStatus.COMPLETED.value, 0)
        cancelled = by_status.get(BookingStatus.CANCELLED.value, 0)

        completion_rate = round((completed / total_bookings * 100), 2) if total_bookings else 0
        cancellation_rate = round((cancelled / total_bookings * 100), 2) if total_bookings else 0

        # --- Driver stats ---
        total_drivers = DriverProfile.query.filter_by(is_deleted=False).count()
        active_drivers = DriverProfile.query.filter_by(
            is_deleted=False, is_online=True
        ).count()
        pending_drivers = DriverProfile.query.filter_by(
            is_deleted=False,
            compliance_status=ComplianceStatus.PENDING_REVIEW,
        ).count()

        # --- Vehicle stats ---
        total_vehicles = Vehicle.query.filter_by(is_deleted=False).count()
        available_vehicles = Vehicle.query.filter_by(
            is_deleted=False, is_available=True
        ).count()

        # --- Incident stats ---
        open_incidents = TransportIncident.query.filter(
            TransportIncident.is_deleted == False,
            TransportIncident.status.in_(["reported", "under_investigation"]),
        ).count()

        # --- Average rating ---
        avg_rating = (
            db.session.query(func.avg(Rating.overall_rating))
            .filter(Rating.is_deleted == False)
            .scalar() or 0
        )

        return {
            "success": True,
            "data": {
                "period": {
                    "from": from_dt.isoformat(),
                    "to": to_dt.isoformat(),
                },
                "bookings": {
                    "total": total_bookings,
                    "by_status": by_status,
                    "completion_rate_pct": completion_rate,
                    "cancellation_rate_pct": cancellation_rate,
                },
                "drivers": {
                    "total": total_drivers,
                    "online": active_drivers,
                    "pending_approval": pending_drivers,
                },
                "vehicles": {
                    "total": total_vehicles,
                    "available": available_vehicles,
                },
                "incidents": {
                    "open": open_incidents,
                },
                "average_rating": round(float(avg_rating), 2),
            },
        }


# ===========================================================================
# Revenue Analytics
# ===========================================================================

class AnalyticsRevenueResource(Resource):
    """GET /api/transport/analytics/revenue"""

    @admin_required
    def get(self):
        """
        Revenue breakdown:
        - Total revenue, platform fees, provider earnings
        - Daily revenue trend for the period
        - Revenue by service type
        - Top earning drivers
        """
        from_dt, to_dt = _parse_date_range()

        # --- Totals ---
        revenue_agg = (
            db.session.query(
                func.sum(Booking.final_price).label("total_revenue"),
                func.sum(Booking.platform_fee).label("total_platform_fee"),
                func.sum(Booking.service_fee).label("total_service_fee"),
                func.sum(Booking.tax_amount).label("total_tax"),
                func.count(Booking.id).label("paid_bookings"),
            )
            .filter(
                Booking.is_deleted == False,
                Booking.payment_status == PaymentStatus.CAPTURED,
                Booking.created_at.between(from_dt, to_dt),
            )
            .one()
        )

        total_revenue = float(revenue_agg.total_revenue or 0)
        total_fees = float(revenue_agg.total_platform_fee or 0)
        provider_earnings = total_revenue - total_fees

        # --- Revenue by service type ---
        by_service = (
            db.session.query(
                Booking.service_type,
                func.count(Booking.id).label("count"),
                func.sum(Booking.final_price).label("revenue"),
            )
            .filter(
                Booking.is_deleted == False,
                Booking.payment_status == PaymentStatus.CAPTURED,
                Booking.created_at.between(from_dt, to_dt),
            )
            .group_by(Booking.service_type)
            .all()
        )

        # --- Daily trend (group by date) ---
        daily_trend = (
            db.session.query(
                func.date(Booking.created_at).label("date"),
                func.count(Booking.id).label("bookings"),
                func.sum(Booking.final_price).label("revenue"),
            )
            .filter(
                Booking.is_deleted == False,
                Booking.payment_status == PaymentStatus.CAPTURED,
                Booking.created_at.between(from_dt, to_dt),
            )
            .group_by(func.date(Booking.created_at))
            .order_by(func.date(Booking.created_at))
            .all()
        )

        # --- Top 10 earning drivers ---
        top_drivers = (
            db.session.query(
                Booking.assigned_driver_id,
                func.count(Booking.id).label("trips"),
                func.sum(Booking.final_price).label("gross_earnings"),
            )
            .filter(
                Booking.is_deleted == False,
                Booking.payment_status == PaymentStatus.CAPTURED,
                Booking.assigned_driver_id.isnot(None),
                Booking.created_at.between(from_dt, to_dt),
            )
            .group_by(Booking.assigned_driver_id)
            .order_by(func.sum(Booking.final_price).desc())
            .limit(10)
            .all()
        )

        return {
            "success": True,
            "data": {
                "period": {
                    "from": from_dt.isoformat(),
                    "to": to_dt.isoformat(),
                },
                "totals": {
                    "revenue": total_revenue,
                    "platform_fees": total_fees,
                    "provider_earnings": round(provider_earnings, 2),
                    "tax_collected": float(revenue_agg.total_tax or 0),
                    "paid_bookings": revenue_agg.paid_bookings,
                    "average_booking_value": round(
                        total_revenue / revenue_agg.paid_bookings, 2
                    ) if revenue_agg.paid_bookings else 0,
                },
                "by_service_type": [
                    {
                        "service_type": row.service_type.value,
                        "bookings": row.count,
                        "revenue": float(row.revenue or 0),
                    }
                    for row in by_service
                ],
                "daily_trend": [
                    {
                        "date": str(row.date),
                        "bookings": row.bookings,
                        "revenue": float(row.revenue or 0),
                    }
                    for row in daily_trend
                ],
                "top_drivers": [
                    {
                        "driver_id": row.assigned_driver_id,
                        "trips": row.trips,
                        "gross_earnings": float(row.gross_earnings or 0),
                    }
                    for row in top_drivers
                ],
            },
        }


# ===========================================================================
# Performance Analytics
# ===========================================================================

class AnalyticsPerformanceResource(Resource):
    """GET /api/transport/analytics/performance"""

    @admin_required
    def get(self):
        """
        Operational performance metrics:
        - On-time rates, average trip duration
        - Driver performance (ratings, reliability)
        - Incident rate
        - Demand by service type and zone
        """
        from_dt, to_dt = _parse_date_range()

        # --- Trip timing performance ---
        timing = (
            db.session.query(
                func.avg(Booking.actual_duration_minutes).label("avg_duration"),
                func.avg(Booking.estimated_duration_minutes).label("avg_estimated"),
                func.avg(Booking.actual_distance_km).label("avg_distance"),
                func.count(
                    case(
                        (
                            and_(
                                Booking.pickup_actual_time.isnot(None),
                                Booking.pickup_estimated_time.isnot(None),
                                Booking.pickup_actual_time <= Booking.pickup_estimated_time,
                            ),
                            1,
                        )
                    )
                ).label("on_time_pickups"),
                func.count(Booking.id).label("completed_total"),
            )
            .filter(
                Booking.is_deleted == False,
                Booking.status == BookingStatus.COMPLETED,
                Booking.created_at.between(from_dt, to_dt),
            )
            .one()
        )

        on_time_rate = round(
            (timing.on_time_pickups / timing.completed_total * 100), 2
        ) if timing.completed_total else 0

        # --- Driver performance ---
        driver_perf = (
            db.session.query(
                func.avg(DriverProfile.average_rating).label("avg_rating"),
                func.avg(DriverProfile.reliability_score).label("avg_reliability"),
                func.avg(DriverProfile.safety_score).label("avg_safety"),
                func.avg(DriverProfile.acceptance_rate).label("avg_acceptance"),
                func.avg(DriverProfile.cancellation_rate).label("avg_cancellation"),
            )
            .filter(DriverProfile.is_deleted == False)
            .one()
        )

        # --- Incident rate ---
        total_completed = (
            Booking.query.filter(
                Booking.is_deleted == False,
                Booking.status == BookingStatus.COMPLETED,
                Booking.created_at.between(from_dt, to_dt),
            ).count()
        )
        incidents_in_period = (
            TransportIncident.query.filter(
                TransportIncident.is_deleted == False,
                TransportIncident.occurred_at.between(from_dt, to_dt),
            ).count()
        )
        incident_rate = round(
            (incidents_in_period / total_completed * 100), 4
        ) if total_completed else 0

        # --- Bookings by service type ---
        by_service = (
            db.session.query(
                Booking.service_type,
                func.count(Booking.id).label("count"),
            )
            .filter(
                Booking.is_deleted == False,
                Booking.created_at.between(from_dt, to_dt),
            )
            .group_by(Booking.service_type)
            .all()
        )

        # --- Rating distribution ---
        rating_dist = (
            db.session.query(
                Rating.overall_rating,
                func.count(Rating.id).label("count"),
            )
            .filter(Rating.is_deleted == False)
            .group_by(Rating.overall_rating)
            .order_by(Rating.overall_rating)
            .all()
        )

        return {
            "success": True,
            "data": {
                "period": {
                    "from": from_dt.isoformat(),
                    "to": to_dt.isoformat(),
                },
                "trip_performance": {
                    "completed_trips": timing.completed_total,
                    "on_time_pickup_rate_pct": on_time_rate,
                    "avg_duration_minutes": round(float(timing.avg_duration or 0), 1),
                    "avg_estimated_minutes": round(float(timing.avg_estimated or 0), 1),
                    "avg_distance_km": round(float(timing.avg_distance or 0), 2),
                },
                "driver_performance": {
                    "avg_rating": round(float(driver_perf.avg_rating or 0), 2),
                    "avg_reliability_score": round(float(driver_perf.avg_reliability or 0), 1),
                    "avg_safety_score": round(float(driver_perf.avg_safety or 0), 1),
                    "avg_acceptance_rate_pct": round(float(driver_perf.avg_acceptance or 0), 2),
                    "avg_cancellation_rate_pct": round(float(driver_perf.avg_cancellation or 0), 2),
                },
                "safety": {
                    "incidents_in_period": incidents_in_period,
                    "incident_rate_pct": incident_rate,
                },
                "demand_by_service_type": [
                    {
                        "service_type": row.service_type.value,
                        "bookings": row.count,
                    }
                    for row in by_service
                ],
                "rating_distribution": {
                    str(row.overall_rating): row.count
                    for row in rating_dist
                },
            },
        }