"""Phase 1: String-storage contract verification (test database).

Proves the permanent convention on the real schema built from current
models (VARCHAR + CHECK, no ENUM):

* all 12 valid status strings accepted (incl. no_match with reason)
* invalid status rejected by ck_transport_bookings_status
* NULL status rejected (NOT NULL)
* bare no_match (NULL reason) rejected by chk_no_match_reason
* stored census ⊆ the 12-value set
* legacy UPPER→lower conversion simulation preserves the census
  (the exact USING expression the migration will use)
* downgrade simulation restores UPPER labels (proves §15 semantics)

Scratch objects use unique names and are dropped in finally blocks;
no project table is touched by the simulations.
"""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.extensions import db

pytestmark = pytest.mark.usefixtures("db_session")

ALL_12 = [
    "draft", "pending_payment", "confirmed", "assigned",
    "driver_en_route", "pickup_arrived", "in_progress", "completed",
    "cancelled", "no_show", "disputed", "no_match",
]


def _seed_rider(app):
    from app.identity.models.user import User

    with app.app_context():
        uid = uuid.uuid4().hex[:8]
        user = User(username=f"m1s_{uid}",
                    email=f"m1s_{uid}@test.example.com",
                    is_active=True, is_verified=True)
        user.set_password("TestPassword123!")
        db.session.add(user)
        db.session.commit()
        return user.id


def _insert_with_status(app, rider_id, status, reason=None):
    from app.transport.models import (
        Booking, ProviderType, ServiceType,
    )

    with app.app_context():
        booking = Booking(
            booking_reference=f"S1-{uuid.uuid4().hex[:8].upper()}",
            user_id=rider_id,
            provider_type=ProviderType.INDIVIDUAL_DRIVER,
            service_type=ServiceType.ON_DEMAND,
            pickup_location={"latitude": 0.1, "longitude": 32.5},
            dropoff_location={"latitude": 0.2, "longitude": 32.6},
            pickup_time=datetime.now(timezone.utc) + timedelta(hours=1),
            passenger_count=1, base_price=Decimal("10.00"),
            subtotal=Decimal("10.00"), total_amount=Decimal("10.00"),
            final_price=Decimal("10.00"),
            status=status,
            no_match_reason=reason,
        )
        db.session.add(booking)
        db.session.commit()
        return booking.id


class TestStringStorageContract:
    @pytest.mark.parametrize("status", [s for s in ALL_12 if s != "no_match"])
    def test_all_valid_statuses_accepted(self, app, status):
        from app.transport.models import Booking

        rider_id = _seed_rider(app)
        booking_id = _insert_with_status(app, rider_id, status)
        with app.app_context():
            stored = db.session.get(Booking, booking_id)
            assert stored.status == status
            assert type(stored.status) is str

    def test_no_match_accepted_with_reason(self, app):
        from app.transport.models import Booking

        rider_id = _seed_rider(app)
        booking_id = _insert_with_status(app, rider_id, "no_match",
                                         reason="all_rejected")
        with app.app_context():
            stored = db.session.get(Booking, booking_id)
            assert stored.status == "no_match"
            assert stored.no_match_reason == "all_rejected"

    def test_invalid_status_rejected_by_check(self, app):
        rider_id = _seed_rider(app)
        with app.app_context(), pytest.raises(IntegrityError):
            _insert_with_status(app, rider_id, "bogus_status")
        db.session.rollback()

    def test_null_status_rejected(self, app):
        # NOTE: the ORM Python-side default fills None with 'draft', so a
        # raw INSERT is required to prove the database NOT NULL barrier.
        rider_id = _seed_rider(app)
        with app.app_context():
            ref = f"S1-{uuid.uuid4().hex[:8].upper()}"
            with pytest.raises(IntegrityError):
                db.session.execute(
                    db.text(
                        "INSERT INTO transport_bookings "
                        "(booking_reference, user_id, provider_type, "
                        "service_type, pickup_location, dropoff_location, "
                        "pickup_time, passenger_count, base_price, subtotal, "
                        "total_amount, final_price, status, created_at, "
                        "updated_at, tenant_id, version, is_deleted) "
                        "VALUES (:ref, :uid, 'INDIVIDUAL_DRIVER', "
                        "'ON_DEMAND', '{}', '{}', now(), 1, 10, 10, 10, 10, "
                        "NULL, now(), now(), 'default', 1, false)"
                    ),
                    {"ref": ref, "uid": rider_id},
                )
                db.session.commit()
            db.session.rollback()

    def test_bare_no_match_rejected(self, app):
        rider_id = _seed_rider(app)
        with app.app_context(), pytest.raises(IntegrityError):
            _insert_with_status(app, rider_id, "no_match", reason=None)
        db.session.rollback()

    def test_census_within_valid_set(self, app):
        rider_id = _seed_rider(app)
        for status in ("confirmed", "assigned", "completed"):
            _insert_with_status(app, rider_id, status)
        with app.app_context():
            rows = db.session.execute(
                db.text("SELECT DISTINCT status FROM transport_bookings")
            ).fetchall()
            assert set(r[0] for r in rows) <= set(ALL_12), rows


class TestConversionSimulation:
    """Scratch-table proof of the exact migration expressions.

    UPGRADE: legacy 11-label UPPER ENUM -> VARCHAR(30)
             USING lower(status::text); census preserved.
    DOWNGRADE: VARCHAR -> 12-label ENUM (incl. NO_MATCH, which the live
             type never had) USING status::<type>; UPPER labels restored.
    """

    LEGACY_LABELS = [
        "DRAFT", "PENDING_PAYMENT", "CONFIRMED", "ASSIGNED",
        "DRIVER_EN_ROUTE", "PICKUP_ARRIVED", "IN_PROGRESS", "COMPLETED",
        "CANCELLED", "NO_SHOW", "DISPUTED",
    ]

    def test_using_lower_preserves_census(self, app):
        tag = uuid.uuid4().hex[:8]
        t_enum, t_tbl = f"probe_enum_{tag}", f"probe_conv_{tag}"
        labels_sql = ", ".join(f"'{label}'" for label in self.LEGACY_LABELS)
        try:
            with app.app_context():
                db.session.execute(
                    db.text(f"CREATE TYPE {t_enum} AS ENUM ({labels_sql})"))
                db.session.execute(
                    db.text(f"CREATE TABLE {t_tbl} (s {t_enum})"))
                for label in ("CONFIRMED", "COMPLETED", "CANCELLED"):
                    db.session.execute(
                        db.text(f"INSERT INTO {t_tbl} (s) VALUES ('{label}')"))
                db.session.commit()
                before = db.session.execute(
                    db.text(f"SELECT s::text, count(*) FROM {t_tbl} "
                            "GROUP BY 1 ORDER BY 1")).fetchall()
                # Exact UPGRADE expression from the migration file.
                db.session.execute(
                    db.text(f"ALTER TABLE {t_tbl} ALTER COLUMN s "
                            "TYPE VARCHAR(30) USING lower(s::text)"))
                db.session.commit()
                after = db.session.execute(
                    db.text(f"SELECT s, count(*) FROM {t_tbl} "
                            "GROUP BY 1 ORDER BY 1")).fetchall()
                assert [(s.lower(), c) for s, c in before] == after
                assert [s for s, _ in after] == [
                    "cancelled", "completed", "confirmed"]
        finally:
            with app.app_context():
                db.session.execute(
                    db.text(f"DROP TABLE IF EXISTS {t_tbl}"))
                db.session.execute(
                    db.text(f"DROP TYPE IF EXISTS {t_enum}"))
                db.session.commit()

    def test_downgrade_restores_upper_labels(self, app):
        tag = uuid.uuid4().hex[:8]
        t_enum, t_tbl = f"probe_denum_{tag}", f"probe_down_{tag}"
        # Downgrade must define the 12-label type (live type only ever
        # had 11 — this is the §15 subtlety, proven here, not assumed).
        labels_12 = self.LEGACY_LABELS + ["NO_MATCH"]
        labels_sql = ", ".join(f"'{label}'" for label in labels_12)
        try:
            with app.app_context():
                db.session.execute(
                    db.text(f"CREATE TABLE {t_tbl} (s VARCHAR(30))"))
                for value in ("confirmed", "no_match", "completed"):
                    db.session.execute(
                        db.text(f"INSERT INTO {t_tbl} (s) VALUES ('{value}')"))
                db.session.commit()
                # Exact DOWNGRADE expression from the migration file.
                # lower() values cannot cast to UPPER-label enums directly:
                # upper() first (this is the §15 subtlety, proven here).
                db.session.execute(
                    db.text(f"CREATE TYPE {t_enum} AS ENUM ({labels_sql})"))
                db.session.execute(
                    db.text(f"ALTER TABLE {t_tbl} ALTER COLUMN s "
                            f"TYPE {t_enum} USING upper(s)::{t_enum}"))
                db.session.commit()
                rows = db.session.execute(
                    db.text(f"SELECT s::text FROM {t_tbl} ORDER BY 1")
                ).fetchall()
                assert [r[0] for r in rows] == [
                    "COMPLETED", "CONFIRMED", "NO_MATCH"]
        finally:
            with app.app_context():
                db.session.execute(
                    db.text(f"DROP TABLE IF EXISTS {t_tbl}"))
                db.session.execute(
                    db.text(f"DROP TYPE IF EXISTS {t_enum}"))
                db.session.commit()
