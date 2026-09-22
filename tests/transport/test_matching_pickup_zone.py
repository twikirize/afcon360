"""S-13 behavioral proof: zone extraction survives all JSONB shapes.

Booking.pickup_location is JSONB and the writer produces either a dict
(map pin placed) or a plain string (typed address), or None. The old
inline `booking.pickup_location.get('zone')` raised AttributeError on
anything but a dict, crashing dispatch.
"""
from types import SimpleNamespace

from app.transport.services.matching_service import _pickup_zone


def test_string_pickup_location_yields_no_zone():
    assert _pickup_zone(SimpleNamespace(pickup_location="Nakawa")) is None


def test_dict_pickup_location_yields_zone():
    assert (
        _pickup_zone(SimpleNamespace(pickup_location={"zone": "cbd"}))
        == "cbd"
    )


def test_none_pickup_location_yields_no_zone():
    assert _pickup_zone(SimpleNamespace(pickup_location=None)) is None
