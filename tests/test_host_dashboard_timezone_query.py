"""SQL-shape regression test for bounded property-local host dashboard bookings."""
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from app.accommodation.models.booking import AccommodationBooking
from app.accommodation.models.property import Property
from app.accommodation.services.host_service import HostService
# Register the transport relationship target before SQLAlchemy configures all mappers.
from app.geo.models import LocationObservation  # noqa: F401


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



def test_property_move_does_not_reuse_old_coordinates_or_timezone():
    from types import SimpleNamespace

    prop = SimpleNamespace(
        address_line1="Kampala Road",
        city="Kampala",
        state="Central",
        country="UG",
        postal_code="",
        latitude=0.3136,
        longitude=32.5811,
        timezone_name="Africa/Kampala",
    )
    resolved = HostService._resolve_property_timezone_for_update(
        prop,
        {
            "address_line1": "King Street West",
            "city": "Toronto",
            "state": "Ontario",
            "country": "CA",
            "postal_code": "M5H 1A1",
            "timezone_name": "America/Toronto",
        },
    )

    assert resolved["location_changed"] is True
    assert resolved["timezone_name"] == "America/Toronto"
    assert resolved["latitude"] is None
    assert resolved["longitude"] is None


def test_property_move_to_single_zone_country_replaces_old_zone():
    from types import SimpleNamespace

    prop = SimpleNamespace(
        address_line1="Kampala Road",
        city="Kampala",
        state="Central",
        country="UG",
        postal_code="",
        latitude=0.3136,
        longitude=32.5811,
        timezone_name="Africa/Kampala",
    )
    resolved = HostService._resolve_property_timezone_for_update(
        prop,
        {
            "address_line1": "Kimathi Street",
            "city": "Nairobi",
            "state": "Nairobi County",
            "country": "KE",
            "postal_code": "",
        },
    )

    assert resolved["location_changed"] is True
    assert resolved["timezone_name"] == "Africa/Nairobi"
    assert resolved["latitude"] is None
    assert resolved["longitude"] is None
