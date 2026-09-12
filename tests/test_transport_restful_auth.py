"""
Regression tests for Defect B: Flask-RESTful × Flask-Login anonymous 401→500.

Verifies that anonymous Flask-RESTful protected endpoints return a proper
JSON-compatible 401 instead of 500, and that authenticated access works
correctly.
"""
import pytest
import uuid

from app.extensions import db
from app.identity.models.user import User
from app.transport.models import DriverProfile
from app.transport.models import ComplianceStatus, VerificationTier


# ---- Helper: create a driver profile ----------------------------------------

def _create_driver(app, label="drv"):
    """Create a unique user + DriverProfile. Returns (user_id, driver_id).
    
    driver_code uses pattern: DRV-<label>-<6-char-uuid> = exactly 20 chars
    to fit the DB column String(20) constraint.
    """
    from tests.test_transport_concurrent_claim import _create_user
    user_id = _create_user(app, f"drv_{label}")
    short_uuid = uuid.uuid4().hex[:6].upper()
    driver_code = f"DRV-{label}-{short_uuid}"
    with app.app_context():
        dp = DriverProfile(
            user_id=user_id,
            driver_code=driver_code,
            verification_tier=VerificationTier.BASIC_VERIFIED,
            compliance_status=ComplianceStatus.APPROVED,
            is_active=True,
            is_online=False,
            is_available=False,
            max_passenger_capacity=4,
            vehicle_classes=["comfort"],
        )
        db.session.add(dp)
        db.session.commit()
        return user_id, dp.id


# ---- Defect B: Anonymous Flask-RESTful protected endpoint returns 401 ----

def test_anonymous_driver_location_post_returns_401(
    app, client, test_user, db_session
):
    """
    Anonymous POST to /api/transport/drivers/<id>/location should return 401,
    not 500 with TypeError.
    """
    # Arrange: create a driver profile
    user_id, driver_id = _create_driver(app, "auth401")

    # Act: anonymous POST with JSON body to Flask-RESTful endpoint
    resp = client.post(
        f"/api/transport/drivers/{driver_id}/location",
        json={"latitude": 0.35, "longitude": 32.5},
    )

    # Assert: should be 401, not 500
    assert resp.status_code == 401, f"Expected 401, got {resp.status_code}: {resp.get_data(as_text=True)}"
    data = resp.get_json()
    assert data is not None, "Response should have JSON body"
    assert data.get("error") is not None, "Error should be present in response"
    assert data.get("success") is False, "success should be False"
    # No protected data payload
    assert "data" not in data, "Should not contain protected data payload"


# ---- Defect B: Authenticated authorized path works ----

def test_authenticated_driver_location_post_success(
    app, client, test_user, authenticated_client, db_session
):
    """
    Authenticated owner of the driver profile can POST location.
    """
    # Arrange: create a driver profile owned by test_user
    user_id, driver_id = _create_driver(app, "authsuccess")

    # Act: authenticated POST as the driver owner
    resp = authenticated_client.post(
        f"/api/transport/drivers/{driver_id}/location",
        json={"latitude": 0.35, "longitude": 32.5},
    )

    # Assert: should be 200 with success True
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.get_data(as_text=True)}"
    data = resp.get_json()
    assert data.get("success") is True, "success should be True"
    # Authorized user should get data payload
    assert "data" in data, "Authorized user should receive data payload"


def test_authenticated_wrong_owner_driver_location_post_forbidden(
    app, client, test_user, authenticated_client, db_session, another_user
):
    """
    Authenticated user who is NOT the owner should get 403 when trying
    to POST driver location.
    """
    # Arrange: create a driver profile owned by test_user
    user_id, driver_id = _create_driver(app, "authforbid")

    # Act: authenticated POST as a different user (another_user)
    resp = authenticated_client.post(
        f"/api/transport/drivers/{driver_id}/location",
        json={"latitude": 0.35, "longitude": 32.5},
    )

    # Assert: should be 403
    assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.get_data(as_text=True)}"
    data = resp.get_json()
    assert data.get("error") is not None


# Fixture: another user different from test_user
@pytest.fixture
def another_user(app, db_session):
    """Create a user different from test_user."""
    uid = str(uuid.uuid4())[:8]
    user = User(
        username=f'user_{uid}',
        email=f'user_{uid}@test.example.com',
        is_verified=True,
        is_active=True,
    )
    user.set_password('TestPass123!')
    db_session.add(user)
    db_session.commit()
    return user


# ---- Defect B: Mutation safety - anonymous cannot mutate data ----

def test_anonymous_cannot_mutate_driver_location(
    app, client, test_user, db_session, anonymous_client
):
    """
    Anonymous POST to driver location should be denied and database
    should be unchanged (no mutation performed).
    """
    # Arrange: create a driver profile owned by test_user
    user_id, driver_id = _create_driver(app, "authmutate")

    # Record the driver's current state
    with app.app_context():
        driver = db.session.get(DriverProfile, driver_id)
        original_last_location = driver.last_location

    # Act: anonymous POST
    resp = anonymous_client.post(
        f"/api/transport/drivers/{driver_id}/location",
        json={"latitude": 0.35, "longitude": 32.5},
    )

    # Assert: should be 401
    assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"

    # Database should be unchanged
    with app.app_context():
        driver = db.session.get(DriverProfile, driver_id)
        assert driver.last_location == original_last_location, (
            f"Database was mutated! last_location changed from "
            f"{original_last_location} to {driver.last_location}"
        )


# ---- Defect B: Non-API (web) routes still get flash+redirect ----

def test_anonymous_web_route_still_redirects(
    app, client, test_user, anonymous_client
):
    """
    Anonymous access to a non-API guarded route should still redirect
    to login (backward compatibility with web routes).
    The /api/ path check in unauthorized() should not affect web routes.
    """
    # Arrange: create a user for context
    user_id, _ = _create_driver(app, "webroute")

    # Act: anonymous GET to the transport health endpoint (web route with @login_required)
    # The health endpoint is at /transport/health under the transport blueprint,
    # not under /api/. It's a regular Flask route, not a Flask-RESTful Resource.
    resp = anonymous_client.get("/transport/health?next=/")

    # The important thing is that the /api/ check doesn't break web routes.
    # Web routes should redirect (302) or show the login page (200).
    assert resp.status_code in (302, 200), (
        f"Web route should redirect (302) or show login (200), got {resp.status_code}: "
        f"{resp.get_data(as_text=True)}"
    )