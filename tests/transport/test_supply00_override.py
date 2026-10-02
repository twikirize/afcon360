"""SUPPLY-00: semantic correction (is_online => is_available) + admin override.

Invariant under test: is_online => is_available on every write path.
Override: per-driver go-live bypass stored in driver_metadata, blocked
states absolute, every change audited.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.extensions import db
from app.identity.models.user import User
from app.transport.models import (
    Booking,
    BookingStatus,
    ComplianceStatus,
    DriverProfile,
    DriverVehicleHistory,
    Vehicle,
)
from app.transport.services.assignment_service import AssignmentService
from app.transport.services.provider_service import get_provider_service
from app.utils.exceptions import ValidationError

from tests.test_transport_concurrent_claim import (
    _create_user,
    _create_booking,
    _make_matchable_driver,
    _delete,
)
from tests.conftest import _login_client


def _driver_data(uid):
    """Minimal payload passing validate_driver_registration.

    Required keys (validators.py): full_name, license_number, phone_number,
    email, date_of_birth (YYYY-MM-DD, 18-100), nationality (AFCON code;
    UG is NOT in the set, use KE).
    """
    return {
        'full_name': 'Test Driver',
        'license_number': 'TEST1234',
        'phone_number': '+256700123456',
        # NOTE: email_validator performs a deliverability check; test/example
        # domains are rejected, so use gmail.com (probe-validated).
        'email': f'driver_{uid}@gmail.com',
        'date_of_birth': '1990-01-01',
        'nationality': 'KE',
        'languages_spoken': ['en'],
        'vehicle_classes': ['comfort'],
        'service_types': ['on_demand'],
        'operational_zones': ['general'],
        'passenger_capacity': 4,
        'luggage_capacity': 2,
        'emergency_contact_name': 'Test Kin',
        'emergency_contact_phone': '+256700999999',
        'emergency_contact_relationship': 'spouse',
    }


def _make_role_user(app, label, role_name):
    """Create a user holding exactly one global role."""
    from app.identity.models.roles_permission import get_or_create_role
    from app.identity.models.user import UserRole

    uid = uuid.uuid4().hex[:8]
    with app.app_context():
        user = User(
            username=f'{label}_{uid}',
            email=f'{label}_{uid}@test.example.com',
            is_verified=True,
            is_active=True,
        )
        user.set_password('TestPass123!')
        db.session.add(user)
        db.session.flush()
        role = get_or_create_role(role_name)
        db.session.add(UserRole(user_id=user.id, role_id=role.id))
        db.session.commit()
        return user.id


# ============================================================================
# T1: claim + release preserves flags
# ============================================================================
def test_T1_claim_release_preserves_flags(app):
    user_id, drv_id, veh_id, hist_id = _make_matchable_driver(app, "drv_T1")
    pax_id = _create_user(app, "pax_T1")
    bk_id, bk_ref = _create_booking(app, pax_id, "T1")

    AssignmentService.claim(bk_ref, drv_id, veh_id, actor=None)
    AssignmentService.release(bk_id, BookingStatus.COMPLETED)

    with app.app_context():
        drv = db.session.get(DriverProfile, drv_id)
        assert drv.is_online is True
        assert drv.is_available is True

    # Claim emits a driver_assigned notification for the passenger; clear
    # notification_logs -> notifications before deleting User rows
    # (FK notifications.user_id, notification_logs.notification_id).
    with app.app_context():
        from app.notifications.models import Notification, NotificationLog
        notif_ids = [
            n.id for n in Notification.query.filter(
                Notification.user_id.in_([user_id, pax_id])
            ).all()
        ]
        if notif_ids:
            NotificationLog.query.filter(
                NotificationLog.notification_id.in_(notif_ids)
            ).delete(synchronize_session=False)
            Notification.query.filter(
                Notification.id.in_(notif_ids)
            ).delete(synchronize_session=False)
            db.session.commit()

    _delete(
        app,
        (DriverVehicleHistory, hist_id),
        (Booking, bk_id),
        (DriverProfile, drv_id),
        (Vehicle, veh_id),
        (User, user_id),
        (User, pax_id),
    )


# ============================================================================
# T2: toggle offline preserves available -> (T, F)
# ============================================================================
def test_T2_offline_toggle_preserves_available(app):
    user_id, drv_id, veh_id, hist_id = _make_matchable_driver(app, "drv_T2")

    with app.app_context():
        drv = db.session.get(DriverProfile, drv_id)
        result = get_provider_service().set_driver_operational_status(
            driver_id=drv_id,
            user_id=drv.user_id,
            is_online=False,
            is_available=None,
        )
        assert result['success'] is True
        drv = db.session.get(DriverProfile, drv_id)
        assert drv.is_online is False
        assert drv.is_available is True

    _delete(
        app,
        (DriverVehicleHistory, hist_id),
        (DriverProfile, drv_id),
        (Vehicle, veh_id),
        (User, user_id),
    )


# ============================================================================
# T3: no vehicle -> online refused, checklist names the vehicle gate
# ============================================================================
def test_T3_online_without_vehicle_refused(app):
    user_id, drv_id, veh_id, hist_id = _make_matchable_driver(app, "drv_T3")

    with app.app_context():
        hist = db.session.get(DriverVehicleHistory, hist_id)
        hist.ended_at = datetime.now(timezone.utc)
        db.session.commit()

    with app.app_context():
        drv = db.session.get(DriverProfile, drv_id)
        before_online = drv.is_online
        before_available = drv.is_available

        with pytest.raises(ValidationError) as exc_info:
            get_provider_service().set_driver_operational_status(
                driver_id=drv_id,
                user_id=drv.user_id,
                is_online=True,
                is_available=None,
            )

        err = exc_info.value
        assert err.details, "ValidationError must carry details"
        go_live = err.details.get("go_live")
        assert go_live is not None
        assert go_live["ready"] is False
        vehicle_check = next(
            (c for c in go_live["checks"] if c["key"] == "vehicle"), None
        )
        assert vehicle_check is not None
        assert vehicle_check["ok"] is False

        db.session.expire_all()
        drv = db.session.get(DriverProfile, drv_id)
        assert drv.is_online is before_online
        assert drv.is_available is before_available

    _delete(
        app,
        (DriverVehicleHistory, hist_id),
        (DriverProfile, drv_id),
        (Vehicle, veh_id),
        (User, user_id),
    )


# ============================================================================
# T4: unqualified driver cannot go online
# ============================================================================
def test_T4_unqualified_cannot_go_online(app):
    user_id, drv_id, veh_id, hist_id = _make_matchable_driver(app, "drv_T4")

    with app.app_context():
        drv = db.session.get(DriverProfile, drv_id)
        drv.is_online = False
        drv.is_available = False
        drv.compliance_status = ComplianceStatus.PENDING_REVIEW
        db.session.commit()

    with app.app_context():
        drv = db.session.get(DriverProfile, drv_id)
        with pytest.raises(ValidationError) as exc_info:
            get_provider_service().set_driver_operational_status(
                driver_id=drv_id,
                user_id=drv.user_id,
                is_online=True,
                is_available=None,
            )

        go_live = exc_info.value.details.get("go_live") if exc_info.value.details else None
        assert go_live is not None
        assert go_live["ready"] is False

        db.session.expire_all()
        drv = db.session.get(DriverProfile, drv_id)
        assert drv.is_online is False
        assert drv.is_available is False

    _delete(
        app,
        (DriverVehicleHistory, hist_id),
        (DriverProfile, drv_id),
        (Vehicle, veh_id),
        (User, user_id),
    )


# ============================================================================
# T5: admin PUT online-without-available -> 422
# ============================================================================
def test_T5_admin_put_online_without_available_rejected(app, admin_client):
    user_id, drv_id, veh_id, hist_id = _make_matchable_driver(app, "drv_T5")

    resp = admin_client.put(
        f"/api/transport/drivers/{drv_id}",
        json={"is_online": True, "is_available": False},
    )
    assert resp.status_code == 422
    body = resp.get_json()
    assert "available" in body["error"].lower()

    with app.app_context():
        drv = db.session.get(DriverProfile, drv_id)
        assert drv.is_online is True
        assert drv.is_available is True

    _delete(
        app,
        (DriverVehicleHistory, hist_id),
        (DriverProfile, drv_id),
        (Vehicle, veh_id),
        (User, user_id),
    )


# ============================================================================
# T6: admin PUT removing available on online driver -> 422
# ============================================================================
def test_T6_admin_put_removing_available_on_online_driver_rejected(app, admin_client):
    user_id, drv_id, veh_id, hist_id = _make_matchable_driver(app, "drv_T6")

    resp = admin_client.put(
        f"/api/transport/drivers/{drv_id}",
        json={"is_available": False},
    )
    assert resp.status_code == 422

    with app.app_context():
        drv = db.session.get(DriverProfile, drv_id)
        assert drv.is_available is True

    _delete(
        app,
        (DriverVehicleHistory, hist_id),
        (DriverProfile, drv_id),
        (Vehicle, veh_id),
        (User, user_id),
    )


# ============================================================================
# T7: register_driver auto_approve=False -> (F, F)
# ============================================================================
def test_T7_register_driver_auto_approve_false_gives_F_F(app, monkeypatch):
    from app.transport.services.settings_service import SettingsService
    monkeypatch.setattr(
        SettingsService,
        "is_feature_enabled",
        staticmethod(lambda key, default=False: False if key == "auto_approve_providers" else True),
    )

    uid = uuid.uuid4().hex[:8]
    user_id = _create_user(app, f"drv_T7_{uid}")
    # register_driver carries @require_permission('provider:register');
    # log in as owner in a request context so only the pre-existing
    # idempotency-decorator behavior under test remains.
    from app.identity.models.roles_permission import get_or_create_role
    from app.identity.models.user import UserRole
    with app.app_context():
        owner_role = get_or_create_role('owner', level=1)
        db.session.add(UserRole(user_id=user_id, role_id=owner_role.id))
        db.session.commit()

    from flask_login import login_user
    with app.test_request_context():
        with app.app_context():
            login_user(db.session.get(User, user_id))
            result = get_provider_service().register_driver(
                user_id, _driver_data(uid)
            )
        assert result['success'] is True
        drv_id = result['data']['driver_id']
    with app.app_context():
        drv = db.session.get(DriverProfile, drv_id)
        assert drv.is_online is False
        assert drv.is_available is False
        assert drv.compliance_status == ComplianceStatus.PENDING_REVIEW

    # register_driver creates a provider_participations row for the user;
    # deleting the User would null its user_id via ORM cascade and trip
    # ck_provider_participations_single_subject. Clear it first.
    with app.app_context():
        from app.identity.models.provider_participation import ProviderParticipation
        ProviderParticipation.query.filter_by(user_id=user_id).delete(
            synchronize_session=False
        )
        db.session.commit()

    _delete(app, (DriverProfile, drv_id), (User, user_id))


# ============================================================================
# T8: register_driver auto_approve=True -> (T, F) marketplace pool
# ============================================================================
def test_T8_register_driver_auto_approve_true_gives_T_F(app, monkeypatch):
    from app.transport.services.settings_service import SettingsService
    monkeypatch.setattr(
        SettingsService,
        "is_feature_enabled",
        staticmethod(lambda key, default=False: True),
    )

    uid = uuid.uuid4().hex[:8]
    user_id = _create_user(app, f"drv_T8_{uid}")
    from app.identity.models.roles_permission import get_or_create_role
    from app.identity.models.user import UserRole
    with app.app_context():
        owner_role = get_or_create_role('owner', level=1)
        db.session.add(UserRole(user_id=user_id, role_id=owner_role.id))
        db.session.commit()

    from flask_login import login_user
    with app.test_request_context():
        with app.app_context():
            login_user(db.session.get(User, user_id))
            result = get_provider_service().register_driver(
                user_id, _driver_data(uid)
            )
        assert result['success'] is True
        drv_id = result['data']['driver_id']
    with app.app_context():
        drv = db.session.get(DriverProfile, drv_id)
        assert drv.is_online is False
        assert drv.is_available is True
        assert drv.compliance_status == ComplianceStatus.APPROVED

    # See T7: clear participations before deleting the User (check constraint).
    with app.app_context():
        from app.identity.models.provider_participation import ProviderParticipation
        ProviderParticipation.query.filter_by(user_id=user_id).delete(
            synchronize_session=False
        )
        db.session.commit()

    _delete(app, (DriverProfile, drv_id), (User, user_id))


# ============================================================================
# T9: admin enables override -> (T, F) + metadata
# ============================================================================
def test_T9_admin_enables_override_populates_metadata(app, admin_client):
    user_id, drv_id, veh_id, hist_id = _make_matchable_driver(app, "drv_T9")
    with app.app_context():
        drv = db.session.get(DriverProfile, drv_id)
        drv.is_online = False
        drv.is_available = False
        drv.compliance_status = ComplianceStatus.PENDING_REVIEW
        db.session.commit()

    resp = admin_client.post(
        f"/api/transport/drivers/{drv_id}/admin-online-override",
        json={"enabled": True, "reason": "test T9"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    assert body["data"]["is_available"] is True
    assert body["data"]["is_online"] is False

    with app.app_context():
        drv = db.session.get(DriverProfile, drv_id)
        assert drv.is_available is True
        ov = (drv.driver_metadata or {}).get("admin_online_override")
        assert ov and ov["enabled"] is True
        assert ov["reason"] == "test T9"
        assert ov["by"] is not None
        assert ov["at"] is not None

    _delete(
        app,
        (DriverVehicleHistory, hist_id),
        (DriverProfile, drv_id),
        (Vehicle, veh_id),
        (User, user_id),
    )


# ============================================================================
# T10: override lets driver go online
# ============================================================================
def test_T10_override_lets_driver_go_online(app, admin_client):
    user_id, drv_id, veh_id, hist_id = _make_matchable_driver(app, "drv_T10")
    with app.app_context():
        drv = db.session.get(DriverProfile, drv_id)
        drv.is_online = False
        drv.is_available = False
        drv.compliance_status = ComplianceStatus.PENDING_REVIEW
        db.session.commit()

    admin_client.post(
        f"/api/transport/drivers/{drv_id}/admin-online-override",
        json={"enabled": True, "reason": "T10"},
    )

    with app.app_context():
        drv = db.session.get(DriverProfile, drv_id)
        result = get_provider_service().set_driver_operational_status(
            driver_id=drv_id,
            user_id=drv.user_id,
            is_online=True,
            is_available=None,
        )
        assert result["success"] is True
        drv = db.session.get(DriverProfile, drv_id)
        assert drv.is_online is True
        assert drv.is_available is True

    _delete(
        app,
        (DriverVehicleHistory, hist_id),
        (DriverProfile, drv_id),
        (Vehicle, veh_id),
        (User, user_id),
    )


# ============================================================================
# T11: disable override forces offline when no longer eligible
# ============================================================================
def test_T11_disable_override_forces_offline_if_no_longer_eligible(app, admin_client):
    user_id, drv_id, veh_id, hist_id = _make_matchable_driver(app, "drv_T11")
    with app.app_context():
        drv = db.session.get(DriverProfile, drv_id)
        drv.compliance_status = ComplianceStatus.PENDING_REVIEW
        drv.is_online = True
        drv.is_available = True
        db.session.commit()

    admin_client.post(
        f"/api/transport/drivers/{drv_id}/admin-online-override",
        json={"enabled": True, "reason": "T11 on"},
    )
    resp = admin_client.post(
        f"/api/transport/drivers/{drv_id}/admin-online-override",
        json={"enabled": False, "reason": "T11 off"},
    )
    assert resp.status_code == 200
    with app.app_context():
        drv = db.session.get(DriverProfile, drv_id)
        assert drv.is_online is False
        assert drv.is_available is False

    _delete(
        app,
        (DriverVehicleHistory, hist_id),
        (DriverProfile, drv_id),
        (Vehicle, veh_id),
        (User, user_id),
    )


# ============================================================================
# T12: override on suspended driver refused
# ============================================================================
def test_T12_override_on_suspended_driver_refused(app, admin_client):
    user_id, drv_id, veh_id, hist_id = _make_matchable_driver(app, "drv_T12")
    with app.app_context():
        drv = db.session.get(DriverProfile, drv_id)
        drv.compliance_status = ComplianceStatus.SUSPENDED
        db.session.commit()

    resp = admin_client.post(
        f"/api/transport/drivers/{drv_id}/admin-online-override",
        json={"enabled": True, "reason": "T12"},
    )
    assert resp.status_code == 422
    with app.app_context():
        drv = db.session.get(DriverProfile, drv_id)
        ov = (drv.driver_metadata or {}).get("admin_online_override")
        assert not (ov and ov.get("enabled"))

    _delete(
        app,
        (DriverVehicleHistory, hist_id),
        (DriverProfile, drv_id),
        (Vehicle, veh_id),
        (User, user_id),
    )


# ============================================================================
# T13: override audit persists in DB
# ============================================================================
def test_T13_override_audit_persists(app, admin_client):
    from app.audit.models import AuditLog as DBAuditLog

    user_id, drv_id, veh_id, hist_id = _make_matchable_driver(app, "drv_T13")
    with app.app_context():
        drv = db.session.get(DriverProfile, drv_id)
        drv.is_available = False
        db.session.commit()

    admin_client.post(
        f"/api/transport/drivers/{drv_id}/admin-online-override",
        json={"enabled": True, "reason": "T13"},
    )

    with app.app_context():
        rows = DBAuditLog.query.filter_by(
            action="driver_admin_online_override_set"
        ).all()
        assert len(rows) >= 1, "audit row must exist in DB"
        assert any(
            r.resource_type == "driver" and str(r.resource_id) == str(drv_id)
            for r in rows
        )

    _delete(
        app,
        (DriverVehicleHistory, hist_id),
        (DriverProfile, drv_id),
        (Vehicle, veh_id),
        (User, user_id),
    )


# ============================================================================
# T14: non-admin cannot use the override endpoint
# ============================================================================
def test_T14_override_requires_admin(app, client):
    user_id, drv_id, veh_id, hist_id = _make_matchable_driver(app, "drv_T14")

    with app.app_context():
        drv = db.session.get(DriverProfile, drv_id)
        _login_client(client, drv.user)

    resp = client.post(
        f"/api/transport/drivers/{drv_id}/admin-online-override",
        json={"enabled": True, "reason": "should fail"},
    )
    # Web-style decorator redirects unauthorized API callers (302) instead
    # of 403; the security property is that no override is written.
    assert resp.status_code in (401, 403, 302)

    with app.app_context():
        drv = db.session.get(DriverProfile, drv_id)
        ov = (drv.driver_metadata or {}).get("admin_online_override")
        assert not (ov and ov.get("enabled"))

    _delete(
        app,
        (DriverVehicleHistory, hist_id),
        (DriverProfile, drv_id),
        (Vehicle, veh_id),
        (User, user_id),
    )


# ============================================================================
# T15: transport_admin and admin roles can use the override endpoint
# ============================================================================
@pytest.mark.parametrize("role_name", ["transport_admin", "admin"])
def test_T15_role_can_use_override(app, client, role_name):
    short = "ta" if role_name == "transport_admin" else "ad"
    user_id, drv_id, veh_id, hist_id = _make_matchable_driver(app, f"T15{short}")
    with app.app_context():
        drv = db.session.get(DriverProfile, drv_id)
        drv.is_available = False
        drv.is_online = False
        drv.compliance_status = ComplianceStatus.PENDING_REVIEW
        db.session.commit()

    role_user_id = _make_role_user(app, f"rl{short}", role_name)
    with app.app_context():
        role_user = db.session.get(User, role_user_id)
        _login_client(client, role_user)

    resp = client.post(
        f"/api/transport/drivers/{drv_id}/admin-online-override",
        json={"enabled": True, "reason": f"T15 {role_name}"},
    )
    assert resp.status_code == 200, f"role {role_name} must be accepted"

    with app.app_context():
        drv = db.session.get(DriverProfile, drv_id)
        assert drv.is_available is True

    _delete(
        app,
        (DriverVehicleHistory, hist_id),
        (DriverProfile, drv_id),
        (Vehicle, veh_id),
        (User, user_id),
        (User, role_user_id),
    )
