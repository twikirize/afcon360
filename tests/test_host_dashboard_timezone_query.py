"""SQL-shape regression test for bounded property-local host dashboard bookings."""
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from app.accommodation.models.booking import AccommodationBooking
from app.accommodation.models.property import Property
from app.accommodation.services.host_service import HostService


def test_host_dashboard_upcoming_query_is_bounded_and_property_timezone_aware():
    session = Session()
    try:
        query = session.query(AccommodationBooking).join(
            Property,
            AccommodationBooking.property_id == Property.id,
        )
        bounded = HostService._build_upcoming_bookings_query(query)
        sql = str(bounded.statement.compile(dialect=postgresql.dialect()))

        assert "LIMIT" in sql.upper()
        assert "10" in sql
        assert "timezone(" in sql.lower()
        assert "accommodation_properties.timezone_name" in sql
        assert "accommodation_properties.timezone_name IS NOT NULL" in sql
        assert "accommodation_bookings.check_in >=" in sql
    finally:
        session.close()
