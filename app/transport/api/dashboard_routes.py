# app/transport/api/dashboard_routes.py
"""
AFCON360 Transport — Admin Dashboard REST API
Single overview endpoint that aggregates everything the admin
dashboard needs in one call: live stats, alerts, recent activity,
and quick-action counts.

Designed to be called on dashboard load — one request, full picture.
"""
from flask import request
from flask_restful import Resource
from app.extensions import db
from app.transport.models import (
    Booking, DriverProfile, Vehicle, TransportIncident,
    Rating, BookingPayment, ScheduledRoute,
    BookingStatus, PaymentStatus, ComplianceStatus,
    VerificationTier, IncidentSeverity
)
from app.admin.routes import admin_required
from datetime import datetime, timedelta, timezone
from sqlalchemy import func, and_, or_
import logging

logger = logging.getLogger(__name__)


class DashboardOverviewResource(Resource):
    """GET /api/transport/dashboard/overview

    Returns a single JSON payload with everything the admin
    dashboard needs:

    - live_operations   : real-time counts (active drivers, live bookings)
    - pending_actions   : things requiring admin attention right now
    - today_summary     : today's booking and revenue snapshot
    - alerts            : critical items needing immediate action
    - recent_activity   : last 10 bookings and last 5 incidents
    - quick_stats       : 7-day and 30-day rolling metrics
    """

    @admin_required
    def get(self):
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_ago = now - timedelta(days=7)
        month_ago = now - timedelta(days=30)

        # ---------------------------------------------------------------
        # 1. Live Operations (real-time state)
        # ---------------------------------------------------------------
        active_drivers = DriverProfile.query.filter_by(
            is_deleted=False, is_online=True
        ).count()

        available_drivers = DriverProfile.query.filter_by(
            is_deleted=False, is_online=True, is_available=True
        ).count()

        live_bookings = Booking.query.filter(
            Booking.is_deleted == False,
            Booking.status.in_([
                BookingStatus.ASSIGNED,
                BookingStatus.DRIVER_EN_ROUTE,
                BookingStatus.PICKUP_ARRIVED,
                BookingStatus.IN_PROGRESS,
            ])
        ).count()

        available_vehicles = Vehicle.query.filter_by(
            is_deleted=False, is_available=True, status="active"
        ).count()

        active_routes = ScheduledRoute.query.filter_by(
            is_deleted=False, is_active=True, is_cancelled=False
        ).count()

        # ---------------------------------------------------------------
        # 2. Pending Actions (items needing admin attention)
        # ---------------------------------------------------------------
        pending_driver_approvals = DriverProfile.query.filter_by(
            is_deleted=False,
            compliance_status=ComplianceStatus.PENDING_REVIEW,
        ).count()

        pending_vehicle_approvals = Vehicle.query.filter(
            Vehicle.is_deleted == False,
            Vehicle.status == "pending_approval",
        ).count()

        unassigned_bookings = Booking.query.filter_by(
            is_deleted=False,
            status=BookingStatus.CONFIRMED,
            assigned_driver_id=None,
        ).count()

        open_incidents = TransportIncident.query.filter(
            TransportIncident.is_deleted == False,
            TransportIncident.status.in_(["reported", "under_investigation"]),
        ).count()

        critical_incidents = TransportIncident.query.filter(
            TransportIncident.is_deleted == False,
            TransportIncident.status.in_(["reported", "under_investigation"]),
            TransportIncident.severity.in_([
                IncidentSeverity.HIGH,
                IncidentSeverity.CRITICAL,
            ]),
        ).count()

        disputed_bookings = Booking.query.filter_by(
            is_deleted=False,
            status=BookingStatus.DISPUTED,
        ).count()

        unreconciled_payments = BookingPayment.query.filter_by(
            is_deleted=False,
            is_reconciled=False,
            payment_status=PaymentStatus.CAPTURED,
        ).count()

        # ---------------------------------------------------------------
        # 3. Today's Summary
        # ---------------------------------------------------------------
        today_bookings = Booking.query.filter(
            Booking.is_deleted == False,
            Booking.created_at >= today_start,
        ).count()

        today_completed = Booking.query.filter(
            Booking.is_deleted == False,
            Booking.status == BookingStatus.COMPLETED,
            Booking.completed_at >= today_start,
        ).count()

        today_cancelled = Booking.query.filter(
            Booking.is_deleted == False,
            Booking.status == BookingStatus.CANCELLED,
            Booking.cancelled_at >= today_start,
        ).count()

        today_revenue = (
            db.session.query(func.sum(Booking.final_price))
            .filter(
                Booking.is_deleted == False,
                Booking.payment_status == PaymentStatus.CAPTURED,
                Booking.payment_captured_at >= today_start,
            )
            .scalar() or 0
        )

        today_new_drivers = DriverProfile.query.filter(
            DriverProfile.is_deleted == False,
            DriverProfile.created_at >= today_start,
        ).count()

        # ---------------------------------------------------------------
        # 4. Alerts (actionable warnings)
        # ---------------------------------------------------------------
        alerts = []

        if critical_incidents > 0:
            alerts.append({
                "level": "critical",
                "type": "incidents",
                "message": f"{critical_incidents} critical incident(s) require immediate attention",
                "count": critical_incidents,
                "action_url": "/api/transport/incidents?severity=critical",
            })

        if unassigned_bookings > 0:
            alerts.append({
                "level": "warning",
                "type": "unassigned_bookings",
                "message": f"{unassigned_bookings} confirmed booking(s) have no driver assigned",
                "count": unassigned_bookings,
                "action_url": "/api/transport/bookings?status=confirmed&driver_id=none",
            })

        if disputed_bookings > 0:
            alerts.append({
                "level": "warning",
                "type": "disputed_bookings",
                "message": f"{disputed_bookings} booking(s) are in disputed state",
                "count": disputed_bookings,
                "action_url": "/api/transport/bookings?status=disputed",
            })

        # Drivers with expiring licenses (next 14 days)
        expiring_soon = DriverProfile.query.filter(
            DriverProfile.is_deleted == False,
            DriverProfile.license_expiry.isnot(None),
            DriverProfile.license_expiry <= now + timedelta(days=14),
            DriverProfile.license_expiry >= now,
        ).count()

        if expiring_soon > 0:
            alerts.append({
                "level": "info",
                "type": "expiring_licenses",
                "message": f"{expiring_soon} driver license(s) expiring within 14 days",
                "count": expiring_soon,
                "action_url": "/api/transport/drivers?expiring_soon=true",
            })

        # ---------------------------------------------------------------
        # 5. Recent Activity
        # ---------------------------------------------------------------
        recent_bookings = (
            Booking.query
            .filter_by(is_deleted=False)
            .order_by(Booking.created_at.desc())
            .limit(10)
            .all()
        )

        recent_incidents = (
            TransportIncident.query
            .filter_by(is_deleted=False)
            .order_by(TransportIncident.created_at.desc())
            .limit(5)
            .all()
        )

        # ---------------------------------------------------------------
        # 6. Quick Stats (rolling 7d vs 30d)
        # ---------------------------------------------------------------
        def _booking_count(from_dt):
            return Booking.query.filter(
                Booking.is_deleted == False,
                Booking.created_at >= from_dt,
            ).count()

        def _revenue(from_dt):
            return float(
                db.session.query(func.sum(Booking.final_price))
                .filter(
                    Booking.is_deleted == False,
                    Booking.payment_status == PaymentStatus.CAPTURED,
                    Booking.payment_captured_at >= from_dt,
                )
                .scalar() or 0
            )

        def _avg_rating(from_dt):
            return round(float(
                db.session.query(func.avg(Rating.overall_rating))
                .filter(
                    Rating.is_deleted == False,
                    Rating.created_at >= from_dt,
                )
                .scalar() or 0
            ), 2)

        logger.info("Admin dashboard overview fetched")

        return {
            "success": True,
            "generated_at": now.isoformat(),
            "data": {
                # Real-time state
                "live_operations": {
                    "active_drivers": active_drivers,
                    "available_drivers": available_drivers,
                    "live_bookings": live_bookings,
                    "available_vehicles": available_vehicles,
                    "active_routes": active_routes,
                },

                # Items needing action
                "pending_actions": {
                    "driver_approvals": pending_driver_approvals,
                    "vehicle_approvals": pending_vehicle_approvals,
                    "unassigned_bookings": unassigned_bookings,
                    "open_incidents": open_incidents,
                    "critical_incidents": critical_incidents,
                    "disputed_bookings": disputed_bookings,
                    "unreconciled_payments": unreconciled_payments,
                    "total": (
                        pending_driver_approvals + pending_vehicle_approvals +
                        unassigned_bookings + critical_incidents + disputed_bookings
                    ),
                },

                # Today snapshot
                "today": {
                    "date": today_start.date().isoformat(),
                    "new_bookings": today_bookings,
                    "completed": today_completed,
                    "cancelled": today_cancelled,
                    "revenue": round(float(today_revenue), 2),
                    "new_drivers": today_new_drivers,
                },

                # Actionable alerts
                "alerts": alerts,
                "alert_count": len(alerts),

                # Recent activity feeds
                "recent_activity": {
                    "bookings": [
                        {
                            "id": b.id,
                            "reference": b.booking_reference,
                            "status": b.status.value,
                            "service_type": b.service_type.value,
                            "final_price": float(b.final_price),
                            "created_at": b.created_at.isoformat(),
                        }
                        for b in recent_bookings
                    ],
                    "incidents": [
                        {
                            "id": i.id,
                            "reference": i.incident_reference,
                            "title": i.title,
                            "severity": i.severity.value,
                            "status": i.status,
                            "occurred_at": i.occurred_at.isoformat(),
                        }
                        for i in recent_incidents
                    ],
                },

                # Rolling metrics
                "quick_stats": {
                    "last_7_days": {
                        "bookings": _booking_count(week_ago),
                        "revenue": _revenue(week_ago),
                        "avg_rating": _avg_rating(week_ago),
                    },
                    "last_30_days": {
                        "bookings": _booking_count(month_ago),
                        "revenue": _revenue(month_ago),
                        "avg_rating": _avg_rating(month_ago),
                    },
                },
            },
        }