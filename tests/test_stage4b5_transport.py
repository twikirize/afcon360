"""
Stage 4B-5 focused tests: transport provider architecture gates.

Covers the approved Stage 4B-5 decisions:
  * Driver onboarding wizard commits DriverProfile + TRANSPORT provider
    intention ONLY — no Vehicle / Booking / Wallet resource is created
    (a Vehicle is a separate, later operation owned by the driver profile).
  * ``get_user_vehicles`` resolves ownership through the user's
    DriverProfile(s) (owner_type='driver') AND through personal ownership
    (owner_type='user', owner_id=user.id).  (Phase C-1 supersedes the
    original Stage 4B-5 single-vocabulary rule: personal owners are valid,
    and assignment never creates ownership.)
  * Organisation identity fails CLOSED when the central organisation
    registry is unavailable — never fabricates active/verified data.
  * ``validate_organisation_eligibility`` requires the organisation to be
    classified transport-enabled (``can_manage_transport()``).

These tests are additive. They do not rewrite any pre-existing test.
"""
import uuid
from datetime import date

import pytest

from app.identity.models import (
    Organisation,
    ProviderCapabilityCode,
    ProviderParticipation,
)
from app.identity.models.organization_types import OrganizationType
from app.transport.models import (
    ComplianceStatus,
    DriverProfile,
    Vehicle,
    VehicleClass,
    VerificationTier,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(db_session, suffix=None):
    from app.identity.models.user import User
    suffix = suffix or uuid.uuid4().hex[:8]
    user = User(
        public_id=str(uuid.uuid4()),
        username=f"s4b5_{suffix}",
        email=f"s4b5_{suffix}@example.com",
    )
    user.set_password("TestPassword123!")
    user.is_active = True
    db_session.add(user)
    db_session.flush()
    return user


def _driver_wizard_data(include_step3_vehicle=True):
    """Mirror the field names / shape produced by the 3-step wizard routes."""
    data = {
        "step1": {
            "full_name": "Stage 4B-5 Driver",
            "date_of_birth": date(1995, 5, 5),
            "nationality": "UG",
            "national_id_number": f"NID-{uuid.uuid4().hex[:8].upper()}",
        },
        "step2": {
            "licence_number": f"LIC-{uuid.uuid4().hex[:8].upper()}",
            "licence_expiry": "2030-12-31",
            "licence_class": "B",
        },
    }
    if include_step3_vehicle:
        data["step3"] = {
            "vehicle_make": "Toyota",
            "vehicle_model": "Corolla",
            "vehicle_year": "2020",
            "plate_number": f"UAY{uuid.uuid4().hex[:4].upper()}",
            "vehicle_type": "sedan",
        }
    return data


def _make_driver_profile(db_session, user, compliance_status=ComplianceStatus.APPROVED):
    driver = DriverProfile(
        user_id=user.id,
        driver_code=f"DRV-{uuid.uuid4().hex[:8].upper()}",
        verification_tier=VerificationTier.BASIC_VERIFIED,
        compliance_status=compliance_status,
    )
    db_session.add(driver)
    db_session.flush()
    return driver


def _make_vehicle(db_session, owner_type, owner_id, plate_suffix=None):
    plate = plate_suffix or f"UAY{uuid.uuid4().hex[:4].upper()}"
    vehicle = Vehicle(
        owner_type=owner_type,
        owner_id=owner_id,
        license_plate=plate,
        make="Toyota",
        model="Corolla",
        year=2020,
        vehicle_type="sedan",
        vehicle_class=VehicleClass.COMFORT,
        passenger_capacity=4,
    )
    db_session.add(vehicle)
    db_session.flush()
    return vehicle


# ---------------------------------------------------------------------------
# Driver onboarding: INTENT only, no domain resources
# ---------------------------------------------------------------------------

def test_driver_wizard_commit_declares_intention_without_vehicles(db_session):
    """Committing driver onboarding must create a DriverProfile and exactly
    one TRANSPORT provider intention — and NO Vehicle / Booking /
    TransportPassenger / Wallet even when the wizard form still carries
    step3 vehicle data."""
    from app.auth.onboarding_routes import _commit_driver_onboarding
    from app.transport.models import Booking, TransportPassenger
    from app.wallet.models.ledger import AccountModel

    user = _make_user(db_session)

    vehicles_before = Vehicle.query.count()
    bookings_before = Booking.query.count()
    passengers_before = TransportPassenger.query.count()
    wallets_before = AccountModel.query.filter_by(user_id=user.id).count()

    _commit_driver_onboarding(user, _driver_wizard_data(include_step3_vehicle=True))
    db_session.flush()

    # DriverProfile created exactly once.
    profiles = DriverProfile.query.filter_by(
        user_id=user.id, is_deleted=False,
    ).all()
    assert len(profiles) == 1

    # Exactly one TRANSPORT INTENT row, subject = individual.
    intentions = ProviderParticipation.query.filter_by(
        user_id=user.id, is_deleted=False,
    ).all()
    assert len(intentions) == 1
    assert intentions[0].capability_code == ProviderCapabilityCode.TRANSPORT.value
    assert intentions[0].organisation_id is None

    # NO vehicle / booking / passenger / wallet resource is created here.
    assert Vehicle.query.count() == vehicles_before
    assert Booking.query.count() == bookings_before
    assert TransportPassenger.query.count() == passengers_before
    assert AccountModel.query.filter_by(user_id=user.id).count() == wallets_before


def test_driver_wizard_commit_guard_prevents_duplicate_driver_profile(db_session):
    """Re-committing driver onboarding must be rejected at the write point."""
    from app.auth.onboarding_routes import _commit_driver_onboarding

    user = _make_user(db_session)
    _commit_driver_onboarding(user, _driver_wizard_data())
    db_session.flush()

    with pytest.raises(ValueError):
        _commit_driver_onboarding(user, _driver_wizard_data())

    assert DriverProfile.query.filter_by(
        user_id=user.id, is_deleted=False,
    ).count() == 1
    assert ProviderParticipation.query.filter_by(
        user_id=user.id,
        capability_code=ProviderCapabilityCode.TRANSPORT.value,
        is_deleted=False,
    ).count() == 1


# ---------------------------------------------------------------------------
# Canonical identity ownership: driver onboarding must NOT mutate UserProfile
# ---------------------------------------------------------------------------

def _make_canonical_profile(db_session, user, **overrides):
    """Create the user's canonical UserProfile with identity fields."""
    from app.profile.models import UserProfile

    fields = {
        "user_id": user.public_id,
        "full_name": "Canonical Full Name",
        "date_of_birth": date(1990, 1, 1),
        "nationality": "UG",
        "id_type": "national_id",
        "id_number": "NID-CANONICAL-001",
    }
    fields.update(overrides)

    profile = UserProfile(**fields)
    db_session.add(profile)
    db_session.flush()
    return profile


def test_driver_commit_preserves_existing_canonical_dob(db_session):
    """Canonical UserProfile.date_of_birth must remain unchanged when driver
    onboarding commits, even when Step 1 carries a different DOB value."""
    from datetime import datetime

    from app.auth.onboarding_routes import _commit_driver_onboarding
    from app.profile.models import get_profile_by_user

    user = _make_user(db_session)
    _make_canonical_profile(db_session, user)

    wizard = _driver_wizard_data()
    wizard["step1"]["date_of_birth"] = "1995-05-05"  # raw HTML string

    _commit_driver_onboarding(user, wizard)
    db_session.flush()

    prof = get_profile_by_user(user.public_id)
    assert prof.date_of_birth == date(1990, 1, 1)


def test_driver_commit_preserves_existing_canonical_id_number(db_session):
    """Canonical UserProfile.id_number must not be overwritten by the driver
    Step 1 national_id_number input."""
    from app.auth.onboarding_routes import _commit_driver_onboarding
    from app.profile.models import get_profile_by_user

    user = _make_user(db_session)
    _make_canonical_profile(db_session, user)

    wizard = _driver_wizard_data()
    wizard["step1"]["national_id_number"] = "NID-DRIVER-INPUT-999"

    _commit_driver_onboarding(user, wizard)
    db_session.flush()

    prof = get_profile_by_user(user.public_id)
    assert prof.id_number == "NID-CANONICAL-001"
    assert prof.id_type == "national_id"


def test_driver_commit_preserves_all_canonical_identity(db_session):
    """full_name, nationality, date_of_birth, id_type and id_number are all
    preserved after driver onboarding commit — driver onboarding consumes
    canonical identity, it does not replace it."""
    from app.auth.onboarding_routes import _commit_driver_onboarding
    from app.profile.models import get_profile_by_user

    user = _make_user(db_session)
    _make_canonical_profile(db_session, user)

    wizard = _driver_wizard_data()
    wizard["step1"].update({
        "full_name": "Submitted Driver Name",
        "nationality": "KE",
        "date_of_birth": "2000-01-01",
        "national_id_number": "NID-SUBMITTED-777",
    })

    _commit_driver_onboarding(user, wizard)
    db_session.flush()

    prof = get_profile_by_user(user.public_id)
    assert prof.full_name == "Canonical Full Name"
    assert prof.nationality == "UG"
    assert prof.date_of_birth == date(1990, 1, 1)
    assert prof.id_type == "national_id"
    assert prof.id_number == "NID-CANONICAL-001"


def test_driver_commit_does_not_create_canonical_profile(db_session):
    """A user with no UserProfile must NOT gain one from driver onboarding.
    Canonical identity creation is not owned by the driver flow."""
    from app.auth.onboarding_routes import _commit_driver_onboarding
    from app.profile.models import UserProfile

    user = _make_user(db_session)
    _commit_driver_onboarding(user, _driver_wizard_data())
    db_session.flush()

    assert UserProfile.query.filter_by(user_id=user.public_id).count() == 0


def test_driver_commit_converts_license_expiry_to_datetime(db_session):
    """Driver-owned licence_expiry (raw form string) must be converted to a
    datetime at the domain boundary before persistence."""
    from app.auth.onboarding_routes import _commit_driver_onboarding

    user = _make_user(db_session)
    _commit_driver_onboarding(user, _driver_wizard_data())
    db_session.flush()

    driver = DriverProfile.query.filter_by(
        user_id=user.id, is_deleted=False,
    ).one()
    assert driver.license_expiry is not None
    assert driver.license_expiry.date() == date(2030, 12, 31)


def test_driver_commit_accepts_string_dob_without_type_error(db_session):
    """Committing driver onboarding with a raw string DOB (the exact HTML
    form shape that previously raised ``TypeError``) must succeed. Driver
    onboarding never assigns the string to UserProfile.date_of_birth."""
    from app.auth.onboarding_routes import _commit_driver_onboarding
    from app.profile.models import get_profile_by_user

    user = _make_user(db_session)
    _make_canonical_profile(db_session, user, date_of_birth=None)

    wizard = _driver_wizard_data()
    wizard["step1"]["date_of_birth"] = "1995-05-05"  # raw HTML string

    _commit_driver_onboarding(user, wizard)
    db_session.flush()

    prof = get_profile_by_user(user.public_id)
    # Missing canonical identity is NOT written by driver onboarding.
    assert prof.date_of_birth is None
    assert DriverProfile.query.filter_by(
        user_id=user.id, is_deleted=False,
    ).count() == 1


# ---------------------------------------------------------------------------
# Uniform vehicle ownership: owner_type='driver'
# ---------------------------------------------------------------------------

def test_get_user_vehicles_resolves_driver_and_personal_ownership(db_session):
    """Vehicles owned by the user's DriverProfile (owner_type='driver') and
    vehicles owned personally by the user (owner_type='user') are both
    returned (Phase C-1 ownership multiplicity)."""
    from app.transport.services.provider_service import ProviderService

    user = _make_user(db_session)
    driver = _make_driver_profile(db_session, user)
    driver_vehicle = _make_vehicle(db_session, "driver", driver.id)
    personal_vehicle = _make_vehicle(db_session, "user", user.id)

    result = ProviderService().get_user_vehicles(user.id)

    by_id = {v.id: v for v in result}
    assert set(by_id) == {driver_vehicle.id, personal_vehicle.id}
    assert by_id[driver_vehicle.id].owner_type == "driver"
    assert by_id[driver_vehicle.id].owner_id == driver.id
    assert by_id[personal_vehicle.id].owner_type == "user"
    assert by_id[personal_vehicle.id].owner_id == user.id


def test_get_user_vehicles_empty_for_non_driver(db_session):
    """A user without a DriverProfile and without personal vehicles owns
    no transport vehicles."""
    from app.transport.services.provider_service import ProviderService

    user = _make_user(db_session)
    assert ProviderService().get_user_vehicles(user.id) == []


# ---------------------------------------------------------------------------
# Organisation transport: identity fail-closed + capability gate
# ---------------------------------------------------------------------------

def test_organisation_identity_fails_closed_without_registry(db_session):
    """With no organisation registry available, transport must refuse to
    fabricate organisation verification (fail-closed)."""
    from app.transport.services.provider_service import ProviderService
    from app.utils.exceptions import ServiceUnavailableError

    with pytest.raises(ServiceUnavailableError):
        ProviderService().get_organisation_identity(999999)


def test_organisation_eligibility_rejects_non_transport_organisation(db_session, monkeypatch):
    """An organisation that is not classified transport-enabled must be
    rejected, even when the identity registry reports it active/verified."""
    from app.transport.services.provider_service import ProviderService
    from app.utils.exceptions import ValidationError

    org = Organisation(
        legal_name="Stage 4B-5 Hotel Co",
        org_id=str(uuid.uuid4()),
        country="UG",
        business_category=OrganizationType.RESTAURANT,
    )
    db_session.add(org)
    db_session.flush()

    svc = ProviderService()

    def _fake_identity(organisation_id):
        return {
            "organisation_id": organisation_id,
            "verified": True,
            "business_registered": True,
            "status": "active",
            "profile": {
                "name": "Stage 4B-5 Restaurant",
                "type": "restaurant",
                "registration_number": "REG-REST-1",
            },
        }

    monkeypatch.setattr(svc, "get_organisation_identity", _fake_identity)

    with pytest.raises(ValidationError) as excinfo:
        svc.validate_organisation_eligibility(org.id)
    assert "not transport-enabled" in str(excinfo.value)


def test_organisation_eligibility_accepts_transport_company(db_session, monkeypatch):
    """A transport-company organisation passes the capability gate."""
    from app.transport.services.provider_service import ProviderService

    org = Organisation(
        legal_name="Stage 4B-5 Transport Co",
        org_id=str(uuid.uuid4()),
        country="UG",
        business_category=OrganizationType.TRANSPORT_COMPANY,
    )
    db_session.add(org)
    db_session.flush()

    svc = ProviderService()

    def _fake_identity(organisation_id):
        return {
            "organisation_id": organisation_id,
            "verified": True,
            "business_registered": True,
            "status": "active",
            "profile": {
                "name": "Stage 4B-5 Transport Co",
                "type": "transport_company",
                "registration_number": "REG-TRANSPORT-1",
            },
        }

    monkeypatch.setattr(svc, "get_organisation_identity", _fake_identity)

    result = svc.validate_organisation_eligibility(org.id)
    assert result["eligible"] is True