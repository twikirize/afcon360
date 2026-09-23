"""Fix 2.5 — booking_request_points scalar/streaming proof.

Guarantee under test (and nothing else):
  booking_request_points() returns the same (points, skipped) as the
  legacy ORM implementation, but selects only the two coordinate
  scalars per row (native JSON type preserved via `->`) and streams
  via yield_per=1000.

Correction history: the first implementation used `->>` text
extraction, which converts JSON true/false to "true"/"false" text and
flips legacy 1.0/0.0 points into skips. `->` preserves the JSON scalar
type so the existing Python float()/range/skip logic is authoritative.

Row-construction pattern copied from the proven
test_moderator_actions.py::_booking helper (same field set that
commits in-suite today). No fixture, seed, or shared-file changes.
"""

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import event
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.elements import BinaryExpression

from app.extensions import db
from app.identity.models.user import User
from app.transport.models import (
    Booking,
    BookingStatus,
    ProviderType,
    ServiceType,
)
from app.transport.services.booking_service import booking_request_points


def _user(db_session, tag):
    user = User(
        username=f"brp_{tag}",
        email=f"brp_{tag}@example.com",
        is_verified=True,
        is_active=True,
    )
    user.set_password("TestPass123!")
    db_session.add(user)
    db_session.flush()
    return user


def _booking(db_session, uid, pickup_location,
             status=BookingStatus.CONFIRMED, is_deleted=False,
             created_at=None):
    # DB check chk_pickup_time_future requires pickup_time > created_at,
    # so the pickup derives from each row's own created_at.
    base = created_at if created_at is not None else datetime.now(timezone.utc)
    booking = Booking(
        user_id=uid,
        provider_type=ProviderType.INDIVIDUAL_DRIVER,
        service_type=ServiceType.ON_DEMAND,
        pickup_location=pickup_location,
        dropoff_location={"latitude": 0.0, "longitude": 0.0},
        pickup_time=base + timedelta(hours=2),
        passenger_count=1,
        base_price=100.00,
        currency="USD",
        status=status,
        is_deleted=is_deleted,
    )
    if created_at is not None:
        booking.created_at = created_at
    db_session.add(booking)
    return booking


def _legacy_reference(loc: Any) -> Optional[tuple]:
    """Test-only oracle replicating the pre-Fix-2.5 Python semantics.

    Operates on the Python-side value exactly as the legacy loop did
    after ORM materialization. Returns the (lat, lng, None) tuple or
    None when the legacy code would have counted a skip.
    """
    if not isinstance(loc, dict):
        return None
    try:
        lat = float(loc.get("latitude"))
        lng = float(loc.get("longitude"))
    except (TypeError, ValueError):
        return None
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
        return None
    return (lat, lng, None)


def _matrix(since, until, old):
    C = BookingStatus.CONFIRMED
    return [
        # (pickup_location, status, is_deleted, created_at)
        ({"latitude": 0.3476, "longitude": 32.5825}, C, False, None),
        ({"latitude": "0.3476", "longitude": "32.5825"}, C, False, None),
        ({"latitude": " 0.3476 ", "longitude": "32.5825"}, C, False, None),
        ({"latitude": True, "longitude": True}, C, False, None),
        ({"latitude": False, "longitude": False}, C, False, None),
        ({"latitude": "true", "longitude": 0.0}, C, False, None),
        ({"latitude": 0.0, "longitude": "false"}, C, False, None),
        ({"latitude": None, "longitude": 0.0}, C, False, None),
        ({"latitude": 1.0}, C, False, None),
        ({"longitude": 1.0}, C, False, None),
        ({"latitude": "abc", "longitude": 0.0}, C, False, None),
        ({"latitude": "12km", "longitude": 0.0}, C, False, None),
        ({"latitude": 90, "longitude": 0.0}, C, False, None),
        ({"latitude": -90, "longitude": 0.0}, C, False, None),
        ({"latitude": 0.0, "longitude": 180}, C, False, None),
        ({"latitude": 0.0, "longitude": -180}, C, False, None),
        ({"latitude": 90.0001, "longitude": 0.0}, C, False, None),
        ({"latitude": -90.0001, "longitude": 0.0}, C, False, None),
        ({"latitude": 0.0, "longitude": 180.0001}, C, False, None),
        ({"latitude": 0.0, "longitude": -180.0001}, C, False, None),
        ([1.0, 2.0], C, False, None),
        ("Kampala Road", C, False, None),
        (5, C, False, None),
        ({"latitude": 6.0, "longitude": 3.0}, BookingStatus.CANCELLED, False, None),
        ({"latitude": 6.0, "longitude": 3.0}, BookingStatus.DRAFT, False, None),
        ({"latitude": 6.0, "longitude": 3.0}, C, True, None),
        ({"latitude": 6.0, "longitude": 3.0}, C, False, old),
        ({"latitude": 0.5, "longitude": 0.5}, C, False, since),
        ({"latitude": -0.5, "longitude": -0.5}, C, False, until),
    ]


def test_same_output_as_legacy_for_controlled_fixture(app, db_session, unique_id):
    """Differential test: reference legacy semantics VS new DB extraction."""
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=1)
    until = now + timedelta(days=1)
    old = now - timedelta(days=60)

    booker = _user(db_session, unique_id)
    uid = booker.id
    matrix = _matrix(since, until, old)
    for loc, status, deleted, created in matrix:
        _booking(db_session, uid, loc, status, deleted, created)
    db_session.commit()

    # Oracle expectation from the legacy semantics, per row. Rows with
    # created_at=None land inside the +/-1-day window by construction.
    expected_points = []
    expected_skipped = 0
    for loc, status, deleted, created in matrix:
        if deleted or status in (BookingStatus.DRAFT, BookingStatus.CANCELLED):
            continue
        if created is not None and not (since <= created <= until):
            continue
        ref = _legacy_reference(loc)
        if ref is None:
            expected_skipped += 1
        else:
            expected_points.append(ref)

    points, skipped = booking_request_points(since, until)

    # No ORDER BY in either implementation, so order is unspecified:
    # compare as sorted lists (exact multiset match).
    assert sorted(points) == sorted(expected_points)
    assert skipped == expected_skipped
    assert len(points) + skipped == len(expected_points) + expected_skipped


def test_query_selects_only_two_scalars(app, db_session):
    """Capture the ACTUAL statement passed to db.session.execute."""
    captured = {}
    real_execute = db.session.execute

    def fake_execute(*args: Any, **kwargs: Any) -> Any:
        captured["stmt"] = args[0]
        return []

    now = datetime.now(timezone.utc)
    try:
        db.session.execute = fake_execute
        points, skipped = booking_request_points(
            now - timedelta(days=1), now + timedelta(days=1)
        )
    finally:
        db.session.execute = real_execute
    assert points == []
    assert skipped == 0

    stmt = captured["stmt"]
    cols = list(stmt.selected_columns)
    assert len(cols) == 2
    assert all(isinstance(col, BinaryExpression) for col in cols)

    sql = str(stmt.compile(
        dialect=postgresql.dialect(),
        compile_kwargs={"literal_binds": True},
    ))
    # Native JSON scalar extraction: exactly two single-arrow uses...
    assert len(re.findall(r"(?<!>)->(?!>)", sql)) == 2
    # ...and zero text-extraction operators (would erase scalar types).
    assert "->>" not in sql
    assert "latitude" in sql
    assert "longitude" in sql

    assert stmt.get_execution_options().get("yield_per") == 1000


def test_one_database_query_issued(app, db_session, unique_id):
    """Exactly 1 SELECT for multiple matching rows; listener removed after."""
    now = datetime.now(timezone.utc)
    booker = _user(db_session, unique_id)
    uid = booker.id
    for i in range(3):
        _booking(db_session, uid, {"latitude": 1.0 + i, "longitude": 2.0 + i})
    db_session.commit()

    seen = []

    def listener(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            seen.append(statement)

    try:
        event.listen(db.engine, "before_cursor_execute", listener)
        booking_request_points(now - timedelta(days=1), now + timedelta(days=1))
    finally:
        event.remove(db.engine, "before_cursor_execute", listener)
    assert len(seen) == 1
