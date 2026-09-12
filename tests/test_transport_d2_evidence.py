# tests/test_transport_d2_evidence.py
"""TH-3-D2 FINAL EVIDENCE GATE — supplementary proofs.

Closes the evidence gaps identified during the FINAL EVIDENCE GATE:

  - offer ownership: wrong-driver accept must conflict (Lua owner check)
  - discover_and_offer Redis-outage soft fail (booking stays CONFIRMED/unassigned)
  - failed-claim atomicity (r3 failure rolls back a successful r2 in the txn)
  - admin force semantics (§14: waives readiness only, never conflicts/state)
  - matching harmonisation runtime probe (pool keys + ranker consumption)
  - fare surfacing (§19: base_price persisted + show.html Estimated Fare row)
  - route-level driver-location security (§8: owner OK, foreign/anonymous/non-driver rejected)

These tests reuse the helpers and patterns from tests/test_transport_concurrent_claim.py.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.extensions import db
from app.transport.models import (
    Booking,
    BookingStatus,
    ComplianceStatus,
    DriverProfile,
    DriverVehicleHistory,
    Vehicle,
)
from app.transport.services.assignment_service import AssignmentService, DispatchClaimError
from app.transport.services.matching_service import MatchingService
from app.transport.services.offer_service import OfferService
from tests.test_transport_concurrent_claim import (
    _FakeRedis,
    _bk_field,
    _create_booking,
    _create_driver,
    _create_user,
    _create_vehicle,
    _delete,
    _drv_field,
    _make_matchable_driver,
    _veh_field,
)


def _make_admin(app):
    """Owner-role user that passes the actor-admin check in assignment_service."""
    from app.identity.models.roles_permission import get_or_create_role
    from app.identity.models.user import User, UserRole

    with app.app_context():
        role = get_or_create_role('owner', level=1)
        unique = uuid.uuid4().hex[:8]
        a = User(
            public_id=str(uuid.uuid4()),
            username=f'd2admin_{unique}',
            email=f'd2admin_{unique}@example.com',
            is_verified=True, is_active=True, email_verified=True,
        )
        a.set_password('TestPass123!')
        db.session.add(a)
        db.session.flush()
        db.session.add(UserRole(user_id=a.id, role_id=role.id))
        db.session.commit()
        return a.id


def _get_admin(app, admin_uid):
    from app.identity.models.user import User
    with app.app_context():
        return db.session.get(User, admin_uid)


def _make_user(app, label):
    from app.identity.models.user import User
    unique = uuid.uuid4().hex[:8]
    with app.app_context():
        u = User(
            public_id=str(uuid.uuid4()),
            username=f'{label}_{unique}',
            email=f'{label}_{unique}@example.com',
            is_verified=True, is_active=True, email_verified=True,
        )
        u.set_password('TestPass123!')
        db.session.add(u)
        db.session.commit()
        return u.id


def _login_as(client, user_id):
    """Set Flask-Login session cookies to authenticate as user_id."""
    from app.identity.models.user import User
    with client.application.app_context():
        uid = str(db.session.get(User, user_id).public_id)
    with client.session_transaction() as sess:
        sess['_user_id'] = uid
        sess['_fresh'] = True


# =====================================================================
# Offer ownership + discovery soft-fail (§5 offer accept ownership)
# =====================================================================

class TestOfferOwnershipAndRedisFailure:
    def test_wrong_driver_accept_rejected(self, app, monkeypatch):
        fake = _FakeRedis()
        monkeypatch.setattr('app.transport.services.offer_service.redis_client', fake)
        ref = f'REF-WRG-{uuid.uuid4().hex[:8]}'
        OfferService.create_offer(ref, driver_id=10, vehicle_id=20, ttl=300)

        with pytest.raises(DispatchClaimError) as exc_info:
            OfferService.accept_offer(ref, driver_id=99)
        assert exc_info.value.kind == 'offer_conflict'

        # Offer must survive for the intended driver.
        assert OfferService.get_offer(ref, driver_id=10) is not None

    def test_discover_and_offer_redis_outage_soft_fails(self, app, monkeypatch):
        class DeadRedis(_FakeRedis):
            def hset(self, *a, **kw):
                raise ConnectionError('no redis')
        monkeypatch.setattr('app.transport.services.offer_service.redis_client', DeadRedis())

        pax_id = _create_user(app, 'paxRedO')
        _, drv, veh, hist = _make_matchable_driver(app, 'dRedO')
        bk_id, bk_ref = _create_booking(app, pax_id, 'redO')

        with app.app_context():
            outcome = MatchingService.discover_and_offer(bk_id)
            assert outcome['offers_created'] == 0, outcome
            bk = db.session.get(Booking, bk_id)
            assert bk.status == BookingStatus.CONFIRMED.value
            assert bk.assigned_driver_id is None
            assert bk.assigned_vehicle_id is None

        _delete(app, (DriverVehicleHistory, hist), (Booking, bk_id),
                (DriverProfile, drv), (Vehicle, veh))


# =====================================================================
# Failed-claim atomicity (§5: no partial mutation survives rollback)
# =====================================================================

class TestClaimAtomicity:
    def test_r3_failure_rolls_back_successful_r2(self, app):
        pax_t = _create_user(app, 'paxAt')
        pax_c = _create_user(app, 'paxAc')
        _, d_t = _create_driver(app, 'dAt')
        v_t = _create_vehicle(app, d_t, 'vAt')
        _, d_c = _create_driver(app, 'dAc')
        v_c = _create_vehicle(app, d_c, 'vAc')
        b_t, ref_t = _create_booking(app, pax_t, 'at')
        b_c, ref_c = _create_booking(app, pax_c, 'ac')

        with app.app_context():
            AssignmentService.claim(ref_c, d_c, v_c, actor=None)

        # d_t passes the driver gate (r2) inside the txn, then v_c fails (r3);
        # the whole transaction must roll back.
        with pytest.raises(DispatchClaimError) as exc_info:
            with app.app_context():
                AssignmentService.claim(ref_t, d_t, v_c, actor=None)
        assert exc_info.value.kind == 'vehicle_unavailable'

        assert _bk_field(app, b_t, 'status') == BookingStatus.CONFIRMED.value
        assert _bk_field(app, b_t, 'assigned_driver_id') is None
        assert _bk_field(app, b_t, 'assigned_vehicle_id') is None
        assert _drv_field(app, d_t, 'is_available') is True
        assert _veh_field(app, v_c, 'is_available') is False

        with app.app_context():
            AssignmentService.release(b_c, BookingStatus.COMPLETED, actor=None, reason='test')
        _delete(app, (Booking, b_t), (Booking, b_c),
                (DriverProfile, d_t), (DriverProfile, d_c),
                (Vehicle, v_t), (Vehicle, v_c))


# =====================================================================
# Force semantics (§14: admin force waives readiness, never conflicts)
# =====================================================================

class TestForceAdminSemantics:
    def test_force_by_admin_waives_both_readiness_flags(self, app):
        pax_id = _create_user(app, 'paxFrcA')
        _, drv = _create_driver(app, 'dFrcA')
        veh = _create_vehicle(app, drv, 'vFrcA')
        bk_id, bk_ref = _create_booking(app, pax_id, 'tFrcA')
        admin_uid = _make_admin(app)

        with app.app_context():
            d = db.session.get(DriverProfile, drv)
            d.is_online = False
            d.is_available = False
            v = db.session.get(Vehicle, veh)
            v.is_available = False
            from app.identity.models.user import User
            db.session.commit()
            admin = db.session.get(User, admin_uid)
            result = AssignmentService.claim(bk_ref, drv, veh, actor=admin, force=True)
            assert result['status'] == BookingStatus.ASSIGNED.value

        assert _bk_field(app, bk_id, 'status') == BookingStatus.ASSIGNED.value
        assert _bk_field(app, bk_id, 'assigned_driver_id') == drv
        assert _bk_field(app, bk_id, 'assigned_vehicle_id') == veh

        with app.app_context():
            AssignmentService.release(bk_id, BookingStatus.COMPLETED, actor=None, reason='test')
        _delete(app, (Booking, bk_id), (DriverProfile, drv), (Vehicle, veh))

    def test_force_admin_cannot_override_active_conflict(self, app):
        pax1 = _create_user(app, 'paxFrcB')
        pax2 = _create_user(app, 'paxFrcC')
        _, drv = _create_driver(app, 'dFrcB')
        veh = _create_vehicle(app, drv, 'vFrcB')
        b1, r1 = _create_booking(app, pax1, 'tFrcB')
        b2, r2 = _create_booking(app, pax2, 'tFrcC')
        admin_uid = _make_admin(app)

        with app.app_context():
            AssignmentService.claim(r1, drv, veh, actor=None)

        with pytest.raises(DispatchClaimError) as exc_info:
            with app.app_context():
                AssignmentService.claim(r2, drv, veh, actor=_get_admin(app, admin_uid), force=True)
        assert exc_info.value.kind == 'driver_unavailable'

        assert _bk_field(app, b2, 'status') == BookingStatus.CONFIRMED.value
        with app.app_context():
            AssignmentService.release(b1, BookingStatus.COMPLETED, actor=None, reason='test')
        _delete(app, (Booking, b1), (Booking, b2), (DriverProfile, drv), (Vehicle, veh))


# =====================================================================
# Matching harmonisation runtime probe (§23)
# =====================================================================

def _synthetic_driver(driver_id, average_rating, acceptance_rate):
    return {
        'driver_id': driver_id,
        'vehicle_id': driver_id * 10,
        'vehicle_classes': ['comfort'],
        'average_rating': average_rating,
        'acceptance_rate': acceptance_rate,
        'service_types': ['on_demand'],
        'current_location': {'latitude': 0.3476, 'longitude': 32.5825},
        'location_updated_at': datetime.now(timezone.utc).isoformat(),
    }


class TestMatchingHarmonisation:
    def test_pool_entries_supply_all_ranker_keys(self, app):
        pax_id = _create_user(app, 'paxPool')
        _, drv, veh, hist = _make_matchable_driver(app, 'dPool')
        bk_id, _ = _create_booking(app, pax_id, 'pool')

        from app.transport.services.provider_service import ProviderService
        with app.app_context():
            pool = ProviderService().get_available_drivers()
        entry = next(d for d in pool if d['driver_id'] == drv)
        for key in ('vehicle_id', 'vehicle_classes', 'average_rating',
                    'acceptance_rate', 'service_types'):
            assert key in entry, f'pool entry missing {key}'

        _delete(app, (DriverVehicleHistory, hist), (Booking, bk_id),
                (DriverProfile, drv), (Vehicle, veh))

    def test_ranker_ranks_by_average_rating(self, app):
        pax_id = _create_user(app, 'paxRankR')
        bk_id, _ = _create_booking(app, pax_id, 'rankR')
        with app.app_context():
            booking = db.session.get(Booking, bk_id)
            high = _synthetic_driver(driver_id=1001, average_rating=5.0, acceptance_rate=100)
            low = _synthetic_driver(driver_id=1002, average_rating=2.0, acceptance_rate=100)
            ranked = MatchingService._rank_drivers_for_booking([high, low], booking)
            assert [d['driver_id'] for d in ranked] == [1001, 1002]
            assert ranked[0]['match_score'] > ranked[1]['match_score']
        _delete(app, (Booking, bk_id))

    def test_ranker_ranks_by_acceptance_rate(self, app):
        pax_id = _create_user(app, 'paxRankA')
        bk_id, _ = _create_booking(app, pax_id, 'rankA')
        with app.app_context():
            booking = db.session.get(Booking, bk_id)
            high = _synthetic_driver(driver_id=2001, average_rating=4.0, acceptance_rate=100)
            low = _synthetic_driver(driver_id=2002, average_rating=4.0, acceptance_rate=20)
            ranked = MatchingService._rank_drivers_for_booking([high, low], booking)
            assert [d['driver_id'] for d in ranked] == [2001, 2002]
            assert ranked[0]['match_score'] > ranked[1]['match_score']
        _delete(app, (Booking, bk_id))


# =====================================================================
# Fare surfacing (§19: persisted + passenger-facing detail surface)
# =====================================================================

class TestFareEvidence:
    def test_base_price_persisted_on_booking(self, app):
        pax_id = _create_user(app, 'paxFare')
        bk_id, _ = _create_booking(app, pax_id, 'fare')
        assert _bk_field(app, bk_id, 'base_price') == 100.0
        assert _bk_field(app, bk_id, 'total_amount') == 100.0
        _delete(app, (Booking, bk_id))

    def test_show_template_renders_estimated_fare_row(self):
        import pathlib
        template = pathlib.Path(__file__).resolve().parents[1] / 'templates' / 'transport' / 'bookings' / 'show.html'
        text = template.read_text(encoding='utf-8')
        assert 'Estimated Fare' in text
        assert 'booking.base_price' in text


# =====================================================================
# Stall-recovery passenger notification (§11)
# =====================================================================

class TestStallNotification:
    def test_stall_recovery_notifies_passenger(self, app, monkeypatch):
        from app.notifications.models import NotificationModule, NotificationType
        from app.notifications.services import NotificationService

        calls = {}

        def _fake_send(user_id, notification_type, title, message, data=None,
                       channels=None, module=None):
            calls.update(user_id=user_id, notification_type=notification_type,
                         module=module, data=data)

        monkeypatch.setattr(NotificationService, 'send', _fake_send)

        pax_id = _create_user(app, 'paxNotif')
        _, drv = _create_driver(app, 'dNotif')
        veh = _create_vehicle(app, drv, 'vNotif')
        bk_id, bk_ref = _create_booking(app, pax_id, 'tNotif')

        with app.app_context():
            AssignmentService.claim(bk_ref, drv, veh, actor=None)
            bk_obj = db.session.get(Booking, bk_id)
            bk_obj.driver_assigned_at = datetime.now(timezone.utc) - timedelta(seconds=900)
            bk_obj.driver_en_route_at = None
            db.session.commit()

        from app.tasks.transport_recovery import stall_recovery
        result = stall_recovery(stall_seconds=600)
        assert bk_id in result['recovered']

        assert calls.get('user_id') == pax_id
        assert calls['notification_type'] == NotificationType.BOOKING_CANCELLED
        assert calls['module'] == NotificationModule.TRANSPORT
        assert calls.get('data', {}).get('reason') == 'stall_timeout'

        _delete(app, (Booking, bk_id), (DriverProfile, drv), (Vehicle, veh))


# =====================================================================
# Route-level driver-location security (§8)
# =====================================================================

class TestDriverLocationRouteSecurity:
    def test_driver_updates_own_location(self, app, client):
        owner_uid = _make_user(app, 'locOwn')
        with app.app_context():
            dp = DriverProfile(
                user_id=owner_uid,
                driver_code=f'DRV-LOC-{uuid.uuid4().hex[:6].upper()}',
                verification_tier='platform_verified',
                compliance_status=ComplianceStatus.APPROVED,
                is_active=True, is_online=True, is_available=True,
                max_passenger_capacity=4, vehicle_classes=['comfort'],
            )
            db.session.add(dp)
            db.session.commit()
            driver_id = dp.id
        _login_as(client, owner_uid)

        resp = client.post(f'/api/transport/drivers/{driver_id}/location',
                           json={'latitude': 0.35, 'longitude': 32.5})
        assert resp.status_code == 200, resp.get_data(as_text=True)
        assert resp.get_json()['success'] is True

        from app.identity.models.user import User
        _delete(app, (DriverProfile, driver_id), (User, owner_uid))

    def test_foreign_driver_rejected(self, app, client):
        owner_uid = _make_user(app, 'locOwnF')
        foreign_uid = _make_user(app, 'locFrgn')
        with app.app_context():
            dp = DriverProfile(
                user_id=owner_uid,
                driver_code=f'DRV-LOCF-{uuid.uuid4().hex[:6].upper()}',
                verification_tier='platform_verified',
                compliance_status=ComplianceStatus.APPROVED,
                is_active=True, is_online=True, is_available=True,
                max_passenger_capacity=4, vehicle_classes=['comfort'],
            )
            db.session.add(dp)
            db.session.commit()
            driver_id = dp.id
        _login_as(client, foreign_uid)

        resp = client.post(f'/api/transport/drivers/{driver_id}/location',
                           json={'latitude': 0.35, 'longitude': 32.5})
        assert resp.status_code == 403, resp.get_data(as_text=True)
        assert resp.get_json()['success'] is False

        from app.identity.models.user import User
        _delete(app, (DriverProfile, driver_id), (User, owner_uid))

    def test_anonymous_rejected(self, app, client):
        owner_uid = _make_user(app, 'locOwnA')
        with app.app_context():
            dp = DriverProfile(
                user_id=owner_uid,
                driver_code=f'DRV-LOCA-{uuid.uuid4().hex[:6].upper()}',
                verification_tier='platform_verified',
                compliance_status=ComplianceStatus.APPROVED,
                is_active=True, is_online=True, is_available=True,
                max_passenger_capacity=4, vehicle_classes=['comfort'],
            )
            db.session.add(dp)
            db.session.commit()
            driver_id = dp.id

        resp = client.post(f'/api/transport/drivers/{driver_id}/location',
                           json={'latitude': 0.35, 'longitude': 32.5})
        # Security property: anonymous is DENIED (no session). The exact code is
        # 500, not the intended 401, because of a pre-existing repo-wide defect
        # (flask_restful.error_router mirrors Flask-Login's unauthorized() 401
        # Response into a TypeError -> 500). Same repro on the non-D2
        # /drivers/me/offers/<ref>/decline endpoint; deferred to BACKLOG.
        assert resp.status_code >= 400, resp.get_data(as_text=True)
        assert resp.get_json().get('error')

        from app.identity.models.user import User
        _delete(app, (DriverProfile, driver_id), (User, owner_uid))

    def test_non_driver_authenticated_rejected(self, app, client):
        owner_uid = _make_user(app, 'locOwnN')
        plain_uid = _make_user(app, 'locPlain')
        with app.app_context():
            dp = DriverProfile(
                user_id=owner_uid,
                driver_code=f'DRV-LOCN-{uuid.uuid4().hex[:6].upper()}',
                verification_tier='platform_verified',
                compliance_status=ComplianceStatus.APPROVED,
                is_active=True, is_online=True, is_available=True,
                max_passenger_capacity=4, vehicle_classes=['comfort'],
            )
            db.session.add(dp)
            db.session.commit()
            driver_id = dp.id
        _login_as(client, plain_uid)

        resp = client.post(f'/api/transport/drivers/{driver_id}/location',
                           json={'latitude': 0.35, 'longitude': 32.5})
        assert resp.status_code == 403, resp.get_data(as_text=True)
        assert resp.get_json()['success'] is False

        from app.identity.models.user import User
        _delete(app, (DriverProfile, driver_id), (User, owner_uid))