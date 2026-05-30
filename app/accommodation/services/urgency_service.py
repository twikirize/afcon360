# OTA-grade urgency and social proof signals
from datetime import datetime, timedelta
from app import db


class UrgencyService:

    def get_signals(self, property_id: int) -> dict:
        """Returns urgency signals for property detail page."""
        signals = {}
        try:
            from app.accommodation.models.booking import AccommodationBooking
            
            # Recent confirmed bookings (last 7 days)
            recent = db.session.query(AccommodationBooking).filter(
                AccommodationBooking.property_id == property_id,
                AccommodationBooking.created_at >= datetime.utcnow() - timedelta(days=7),
                AccommodationBooking.status.in_(['confirmed', 'completed'])
            ).count()

            if recent >= 2:
                signals['recently_booked'] = True
                signals['recent_booking_count'] = recent

            # High demand: many bookings in next 30 days
            upcoming = db.session.query(AccommodationBooking).filter(
                AccommodationBooking.property_id == property_id,
                AccommodationBooking.check_out_date >= datetime.utcnow().date(),
                AccommodationBooking.check_in_date <= datetime.utcnow().date() + timedelta(days=30),
                AccommodationBooking.status.in_(['confirmed', 'pending'])
            ).count()

            if upcoming >= 15:
                signals['high_demand'] = True

        except Exception:
            pass  # Never crash the detail page over analytics

        return signals


urgency_service = UrgencyService()
