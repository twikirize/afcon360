"""
Event metrics service for analytics and reporting.
"""
from typing import Dict, List, Optional
from datetime import datetime, timedelta, date
from app.extensions import db
from app.events.models import Event, EventRegistration, TicketType, Waitlist
from sqlalchemy import func, and_, case
import logging

logger = logging.getLogger(__name__)

class EventMetricsService:
    """Service for generating event metrics and analytics"""

    @staticmethod
    def get_event_metrics(event_id: int, days: int = 30) -> Dict:
        """Get comprehensive metrics for a specific event"""
        try:
            event = Event.query.get(event_id)
            if not event:
                return {"error": "Event not found"}

            # Calculate date range
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=days)

            # Registration trends
            daily_registrations = db.session.query(
                func.date(EventRegistration.created_at).label('date'),
                func.count(EventRegistration.id).label('count')
            ).filter(
                EventRegistration.event_id == event_id,
                EventRegistration.created_at >= start_date,
                EventRegistration.created_at <= end_date
            ).group_by(
                func.date(EventRegistration.created_at)
            ).order_by('date').all()

            # Payment metrics
            payment_stats = db.session.query(
                EventRegistration.payment_status,
                func.count(EventRegistration.id).label('count'),
                func.sum(EventRegistration.registration_fee).label('total')
            ).filter(
                EventRegistration.event_id == event_id
            ).group_by(
                EventRegistration.payment_status
            ).all()

            # Check-in metrics
            checkin_stats = db.session.query(
                func.count(EventRegistration.id).label('total'),
                func.sum(case((EventRegistration.status == 'checked_in', 1), else_=0)).label('checked_in')
            ).filter(
                EventRegistration.event_id == event_id
            ).first()

            # Ticket type breakdown
            ticket_stats = db.session.query(
                TicketType.name,
                func.count(EventRegistration.id).label('count'),
                func.sum(EventRegistration.registration_fee).label('revenue')
            ).join(
                EventRegistration, TicketType.id == EventRegistration.ticket_type_id
            ).filter(
                EventRegistration.event_id == event_id
            ).group_by(
                TicketType.name
            ).all()

            # Geographic distribution
            geo_distribution = db.session.query(
                EventRegistration.nationality,
                func.count(EventRegistration.id).label('count')
            ).filter(
                EventRegistration.event_id == event_id,
                EventRegistration.nationality.isnot(None)
            ).group_by(
                EventRegistration.nationality
            ).order_by(
                func.count(EventRegistration.id).desc()
            ).limit(10).all()

            # Waitlist metrics
            waitlist_count = Waitlist.query.filter_by(
                event_id=event_id,
                status='pending'
            ).count()

            # Convert to dictionaries
            daily_trend = [{"date": str(date), "count": count} for date, count in daily_registrations]
            payment_breakdown = [{"status": status, "count": count, "total": float(total or 0)}
                                for status, count, total in payment_stats]
            ticket_breakdown = [{"name": name, "count": count, "revenue": float(revenue or 0)}
                               for name, count, revenue in ticket_stats]
            geo_data = [{"country": country, "count": count} for country, count in geo_distribution]

            checkin_rate = 0
            if checkin_stats and checkin_stats.total > 0:
                checkin_rate = (checkin_stats.checked_in or 0) / checkin_stats.total * 100

            return {
                "event_id": event_id,
                "event_name": event.name,
                "period_days": days,
                "total_registrations": checkin_stats.total if checkin_stats else 0,
                "checked_in_count": checkin_stats.checked_in if checkin_stats else 0,
                "checkin_rate": round(checkin_rate, 1),
                "waitlist_count": waitlist_count,
                "daily_trend": daily_trend,
                "payment_breakdown": payment_breakdown,
                "ticket_breakdown": ticket_breakdown,
                "geographic_distribution": geo_data,
                "calculated_at": datetime.utcnow().isoformat()
            }

        except Exception as e:
            logger.error(f"Error getting event metrics for event {event_id}: {e}")
            return {"error": str(e)}

    @staticmethod
    def get_organizer_metrics(organizer_id: int, days: int = 30) -> Dict:
        """Get metrics for all events organized by a user"""
        try:
            # Get all events by this organizer
            events = Event.query.filter_by(organizer_id=organizer_id).all()
            event_ids = [event.id for event in events]

            if not event_ids:
                return {
                    "organizer_id": organizer_id,
                    "total_events": 0,
                    "metrics": {}
                }

            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=days)

            # Overall registration stats
            total_stats = db.session.query(
                func.count(EventRegistration.id).label('total'),
                func.sum(EventRegistration.registration_fee).label('revenue'),
                func.sum(case((EventRegistration.status == 'checked_in', 1), else_=0)).label('checked_in')
            ).filter(
                EventRegistration.event_id.in_(event_ids),
                EventRegistration.created_at >= start_date,
                EventRegistration.created_at <= end_date
            ).first()

            # Event-by-event breakdown
            event_breakdown = []
            for event in events:
                reg_count = EventRegistration.query.filter_by(event_id=event.id).count()
                revenue = db.session.query(
                    func.sum(EventRegistration.registration_fee)
                ).filter(
                    EventRegistration.event_id == event.id,
                    EventRegistration.payment_status == 'paid'
                ).scalar() or 0

                event_breakdown.append({
                    "event_id": event.id,
                    "event_name": event.name,
                    "slug": event.slug,
                    "status": event.status,
                    "registrations": reg_count,
                    "revenue": float(revenue),
                    "start_date": event.start_date.isoformat() if event.start_date else None
                })

            # Sort by registration count
            event_breakdown.sort(key=lambda x: x["registrations"], reverse=True)

            return {
                "organizer_id": organizer_id,
                "total_events": len(events),
                "period_days": days,
                "total_registrations": total_stats.total or 0,
                "total_revenue": float(total_stats.revenue or 0),
                "total_checked_in": total_stats.checked_in or 0,
                "event_breakdown": event_breakdown[:10],  # Top 10 events
                "calculated_at": datetime.utcnow().isoformat()
            }

        except Exception as e:
            logger.error(f"Error getting organizer metrics for organizer {organizer_id}: {e}")
            return {"error": str(e)}

    @staticmethod
    def get_system_wide_metrics(days: int = 30) -> Dict:
        """Get system-wide metrics across all events"""
        try:
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=days)

            # Overall system stats
            system_stats = db.session.query(
                func.count(Event.id).label('total_events'),
                func.count(EventRegistration.id).label('total_registrations'),
                func.sum(EventRegistration.registration_fee).label('total_revenue'),
                func.sum(case((EventRegistration.status == 'checked_in', 1), else_=0)).label('total_checked_in')
            ).outerjoin(
                EventRegistration, Event.id == EventRegistration.event_id
            ).filter(
                Event.created_at >= start_date,
                Event.created_at <= end_date
            ).first()

            # Event status breakdown
            status_breakdown = db.session.query(
                Event.status,
                func.count(Event.id).label('count')
            ).filter(
                Event.created_at >= start_date,
                Event.created_at <= end_date
            ).group_by(
                Event.status
            ).all()

            # Category breakdown
            category_breakdown = db.session.query(
                Event.category,
                func.count(Event.id).label('count')
            ).filter(
                Event.created_at >= start_date,
                Event.created_at <= end_date
            ).group_by(
                Event.category
            ).order_by(
                func.count(Event.id).desc()
            ).limit(10).all()

            # Daily event creation trend
            daily_events = db.session.query(
                func.date(Event.created_at).label('date'),
                func.count(Event.id).label('count')
            ).filter(
                Event.created_at >= start_date,
                Event.created_at <= end_date
            ).group_by(
                func.date(Event.created_at)
            ).order_by('date').all()

            # Convert to dictionaries
            status_data = [{"status": status, "count": count} for status, count in status_breakdown]
            category_data = [{"category": category, "count": count} for category, count in category_breakdown]
            daily_trend = [{"date": str(date), "count": count} for date, count in daily_events]

            return {
                "period_days": days,
                "total_events": system_stats.total_events or 0,
                "total_registrations": system_stats.total_registrations or 0,
                "total_revenue": float(system_stats.total_revenue or 0),
                "total_checked_in": system_stats.total_checked_in or 0,
                "status_breakdown": status_data,
                "category_breakdown": category_data,
                "daily_event_creation": daily_trend,
                "calculated_at": datetime.utcnow().isoformat()
            }

        except Exception as e:
            logger.error(f"Error getting system-wide metrics: {e}")
            return {"error": str(e)}

    @staticmethod
    def get_revenue_metrics(days: int = 30) -> Dict:
        """Get revenue-specific metrics"""
        try:
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=days)

            # Daily revenue
            daily_revenue = db.session.query(
                func.date(EventRegistration.created_at).label('date'),
                func.sum(EventRegistration.registration_fee).label('revenue'),
                func.count(EventRegistration.id).label('transactions')
            ).filter(
                EventRegistration.payment_status == 'paid',
                EventRegistration.created_at >= start_date,
                EventRegistration.created_at <= end_date
            ).group_by(
                func.date(EventRegistration.created_at)
            ).order_by('date').all()

            # Revenue by event category
            category_revenue = db.session.query(
                Event.category,
                func.sum(EventRegistration.registration_fee).label('revenue'),
                func.count(EventRegistration.id).label('transactions')
            ).join(
                Event, EventRegistration.event_id == Event.id
            ).filter(
                EventRegistration.payment_status == 'paid',
                EventRegistration.created_at >= start_date,
                EventRegistration.created_at <= end_date
            ).group_by(
                Event.category
            ).order_by(
                func.sum(EventRegistration.registration_fee).desc()
            ).limit(10).all()

            # Convert to dictionaries
            daily_data = [{
                "date": str(date),
                "revenue": float(revenue or 0),
                "transactions": transactions
            } for date, revenue, transactions in daily_revenue]

            category_data = [{
                "category": category,
                "revenue": float(revenue or 0),
                "transactions": transactions
            } for category, revenue, transactions in category_revenue]

            # Calculate totals
            total_revenue = sum(item["revenue"] for item in daily_data)
            total_transactions = sum(item["transactions"] for item in daily_data)

            return {
                "period_days": days,
                "total_revenue": total_revenue,
                "total_transactions": total_transactions,
                "average_transaction_value": total_revenue / total_transactions if total_transactions > 0 else 0,
                "daily_revenue": daily_data,
                "revenue_by_category": category_data,
                "calculated_at": datetime.utcnow().isoformat()
            }

        except Exception as e:
            logger.error(f"Error getting revenue metrics: {e}")
            return {"error": str(e)}
