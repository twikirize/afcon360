# app/transport/cli_driver.py
"""
Driver simulator CLI (dev-only).

Headless counterpart to the driver workspace
(templates/transport/driver/driver_dashboard.html): publishes locations,
lists/accepts offers and advances trips through the SAME canonical
services the HTTP driver endpoints use. Never a second source of
dispatch truth.
"""
import os
import time

import click
from flask import current_app

from app.extensions import db


def _ensure_dev():
    """Refuse to run against production."""
    if current_app.debug or current_app.config.get("TESTING"):
        return
    if os.getenv("FLASK_ENV", "").lower() in (
        "development", "testing", "local", "dev",
    ):
        return
    raise click.ClickException(
        "flask driver commands are dev-only (refusing production)."
    )


def _driver_or_fail(driver_id: int):
    from app.transport.models import DriverProfile

    profile = db.session.get(DriverProfile, driver_id)
    if profile is None:
        raise click.ClickException(f"driver {driver_id} not found")
    return profile


@click.group(name="driver")
def driver_group():
    """Simulate a driver client (dev only)."""


@driver_group.command("ping")
@click.argument("driver_id", type=int)
@click.argument("lat", type=float)
@click.argument("lng", type=float)
def ping(driver_id, lat, lng):
    """One-shot location publish for a driver."""
    _ensure_dev()
    from app.transport.services.tracking_service import TrackingService

    with current_app.app_context():
        profile = _driver_or_fail(driver_id)
        TrackingService.update_location("driver", profile.id, {
            "latitude": lat,
            "longitude": lng,
        })
        db.session.expire_all()
        fresh = db.session.get(type(profile), profile.id)
        click.echo(f"location_updated_at={fresh.location_updated_at}")


@driver_group.command("ping-loop")
@click.argument("driver_id", type=int)
@click.argument("lat", type=float)
@click.argument("lng", type=float)
@click.option("--interval", type=int, default=120, show_default=True,
              help="Seconds between publishes.")
@click.option("--duration", type=int, default=600, show_default=True,
              help="Total run time in seconds.")
def ping_loop(driver_id, lat, lng, interval, duration):
    """Publish a location every N seconds for M seconds."""
    _ensure_dev()
    from app.transport.services.tracking_service import TrackingService

    if interval < 30:
        raise click.ClickException("interval must be >= 30s")
    if interval > 300:
        click.echo("WARNING: interval exceeds the 300s freshness TTL; "
                   "clamping to 300s so the driver stays matchable.")
        interval = 300
    deadline = time.monotonic() + duration
    try:
        with current_app.app_context():
            profile = _driver_or_fail(driver_id)
            pid = profile.id
            while True:
                TrackingService.update_location("driver", pid, {
                    "latitude": lat,
                    "longitude": lng,
                })
                db.session.expire_all()
                fresh = db.session.get(type(profile), pid)
                click.echo(
                    f"ping location_updated_at={fresh.location_updated_at}")
                if time.monotonic() + interval >= deadline:
                    break
                time.sleep(interval)
    except KeyboardInterrupt:
        click.echo("stopped.")


@driver_group.command("offers")
@click.argument("driver_id", type=int)
def offers(driver_id):
    """Print the current live offer list for a driver."""
    _ensure_dev()
    from app.transport.services.offer_service import OfferService

    with current_app.app_context():
        profile = _driver_or_fail(driver_id)
        live = OfferService.list_driver_offers(profile.id)
        if not live:
            click.echo("no live offers")
            return
        for offer in live:
            click.echo(
                f"{offer.get('booking_reference')} "
                f"status={offer.get('status')} "
                f"expires_at={offer.get('expires_at')}"
            )


@driver_group.command("accept")
@click.argument("driver_id", type=int)
@click.argument("booking_reference")
def accept(driver_id, booking_reference):
    """Accept an offer + claim, same as the HTTP accept path."""
    _ensure_dev()
    from app.transport.services.assignment_service import (
        AssignmentService,
        DispatchClaimError,
    )
    from app.transport.services.offer_service import OfferService

    with current_app.app_context():
        profile = _driver_or_fail(driver_id)
        vehicle = profile.current_vehicle
        if vehicle is None:
            raise click.ClickException(
                "driver has no current vehicle to accept with")
        try:
            OfferService.accept_offer(booking_reference, profile.id)
        except DispatchClaimError as e:
            raise click.ClickException(
                f"accept refused: {e.kind}: {e.message}")
        try:
            result = AssignmentService.claim(
                booking_reference, profile.id, vehicle.id, actor=None)
        except DispatchClaimError as e:
            OfferService.cleanup_offer(booking_reference, profile.id)
            raise click.ClickException(
                f"claim refused: {e.kind}: {e.message}")
        click.echo(f"booking status={result['status']} "
                   f"driver={result['driver_id']} "
                   f"vehicle={result['vehicle_id']}")


@driver_group.command("trip")
@click.argument("booking_id", type=int)
@click.argument("action")
def trip(booking_id, action):
    """Advance a trip: en_route | arrive | start | complete.

    Uses BookingService.transition_status — the same canonical guarded
    transition the admin status endpoint and moderation flows share.
    """
    _ensure_dev()
    from app.transport.models import BookingStatus
    from app.transport.services.assignment_service import DispatchClaimError
    from app.transport.services.booking_service import BookingService
    from app.utils.exceptions import NotFoundError, ValidationError

    targets = {
        "en_route": BookingStatus.DRIVER_EN_ROUTE,
        "arrive": BookingStatus.PICKUP_ARRIVED,
        "start": BookingStatus.IN_PROGRESS,
        "complete": BookingStatus.COMPLETED,
    }
    if action not in targets:
        raise click.ClickException(
            "action must be one of: en_route|arrive|start|complete")
    with current_app.app_context():
        try:
            result = BookingService.transition_status(
                booking_id, targets[action], actor=None)
        except (ValidationError, DispatchClaimError, NotFoundError) as e:
            raise click.ClickException(
                f"trip advance refused: {getattr(e, 'kind', None) or getattr(e, 'message', e)}")
        booking = result["booking"]
        click.echo(f"booking status={booking.status.value}")


@driver_group.command("seed-test-driver")
def seed_test_driver():
    """Create (or reuse) the fully verified PWA pilot test driver.

    Idempotent: re-running resets the fixed password, re-ensures every
    verified flag, and prints the same parseable credential block. Refuses
    production via the same dev-only guard as the rest of this group.
    """
    _ensure_dev()
    from datetime import datetime, timedelta, timezone

    from app.identity.individuals.individual_verification import (
        IndividualVerification,
    )
    from app.identity.models.user import User
    from app.profile.models import UserProfile
    from app.transport.models import (
        ComplianceStatus,
        DriverProfile,
        DriverVehicleHistory,
        Vehicle,
        VehicleClass,
        VerificationTier,
    )
    from app.transport.services.go_live_service import can_go_live

    driver_name = "Israeli"
    # Email is the stable idempotency key (username may change; email may not).
    # Login matches username/email exactly (case-sensitive), so "Israeli" must
    # be typed with its exact case; the email always works as an alternative.
    username = driver_name
    email = "afcon_test_driver@example.com"
    password = "Makerere@2026"
    phone = "+256700000001"
    # The fixed pilot phone may already be held by a pre-existing dev user
    # (which this command must never modify). Tier-1 KYC only needs
    # phone_verified + (phone_verified_at OR phone), so fall back through a
    # deterministic candidate list rather than stealing the taken number.
    phone_candidates = (
        phone, "+256700000101", "+256700000201", "+256700000301",
    )
    driver_code = "AFCTESTDRV001"
    license_number = "TEST-DL-2026-0001"
    vehicle_plate = "TEST-DRV-001"

    with current_app.app_context():
        now = datetime.now(timezone.utc)

        # 1. User - create or reuse (matched by fixed email); always reset
        #    the fixed password and enforce the pilot username/display name.
        user = User.query.filter_by(email=email).first()
        if user is None:
            clash = User.query.filter_by(username=username).first()
            if clash is not None:
                raise click.ClickException(
                    f"username {username} already belongs to another user")
            chosen_phone = next(
                (c for c in phone_candidates
                 if User.query.filter_by(phone=c).first() is None),
                None,
            )
            user = User(username=username, email=email, phone=chosen_phone)
            db.session.add(user)
        else:
            taken = User.query.filter_by(username=username).first()
            if taken is not None and taken.id != user.id:
                raise click.ClickException(
                    f"username {username} already belongs to another user")
            user.username = username
        user.set_password(password)
        user.is_active = True
        user.is_verified = True
        user.email_verified = True
        user.email_verified_at = user.email_verified_at or now
        user.phone_verified = True
        user.phone_verified_at = now
        user.failed_logins = 0
        user.locked_until = None
        user.is_deleted = False
        user.deleted_at = None
        if not user.phone:
            user.phone = next(
                (c for c in phone_candidates
                 if User.query.filter_by(phone=c).first() is None),
                None,
            )
        db.session.flush()

        # 1b. UserProfile - makes User.display_name render the pilot name
        #     (precedence: profile.display_name -> profile.full_name ->
        #     username). Marked verified+completed so the post-login banner
        #     (auth/routes.py: verification_status == "pending") stays quiet;
        #     the pilot driver IS verified (IndividualVerification + go-live).
        user_profile = UserProfile.query.filter_by(
            user_id=user.public_id).first()
        if user_profile is None:
            db.session.add(UserProfile(
                user_id=user.public_id,
                full_name=driver_name,
                display_name=driver_name,
                verification_status="verified",
                profile_completed=True,
            ))
        else:
            user_profile.full_name = driver_name
            user_profile.display_name = driver_name
            user_profile.verification_status = "verified"
            user_profile.profile_completed = True
            db.session.add(user_profile)

        # 2. DriverProfile - create or reuse; force the pilot-ready state.
        profile = DriverProfile.query.filter_by(user_id=user.id).first()
        if profile is None:
            taken = DriverProfile.query.filter_by(
                driver_code=driver_code).first()
            if taken is not None:
                raise click.ClickException(
                    f"driver code {driver_code} already belongs to "
                    "another profile")
            profile = DriverProfile(user_id=user.id, driver_code=driver_code)
            db.session.add(profile)
            db.session.flush()
        if not profile.driver_code:
            profile.driver_code = driver_code
        profile.compliance_status = ComplianceStatus.APPROVED
        profile.verification_tier = VerificationTier.PLATFORM_VERIFIED
        profile.license_number = license_number
        profile.license_expiry = now + timedelta(days=365)
        profile.license_verified = True
        profile.license_verified_at = now
        profile.police_clearance_verified = True
        profile.police_clearance_date = now
        profile.is_online = False
        profile.is_available = False
        profile.is_deleted = False
        profile.languages_spoken = ["en"]
        profile.operational_zones = ["general"]
        profile.preferred_zones = []
        profile.vehicle_classes = ["economy", "comfort"]
        profile.service_types = ["on_demand"]
        profile.max_passenger_capacity = 4
        profile.max_luggage_capacity = 2
        profile.commission_rate = 15.00

        # 3. KYC - exactly what driver_go_live_kyc_qualified reads:
        #    calculate_kyc_tier() needs a verified phone (Tier 1) plus a
        #    verified IndividualVerification whose scope carries the Tier 2
        #    requirements (national_id + selfie/biometric). The KYC gate
        #    itself is never weakened.
        kyc_scope = {
            "identity": True,
            "address": True,
            "national_id": True,
            "biometric": True,
        }
        verification = (
            IndividualVerification.query
            .filter_by(user_id=user.id)
            .order_by(IndividualVerification.requested_at.desc())
            .first()
        )
        if verification is None:
            db.session.add(IndividualVerification(
                user_id=user.id,
                status="verified",
                scope=dict(kyc_scope),
            ))
        else:
            merged = dict(verification.scope or {})
            merged.update(kyc_scope)
            verification.scope = merged
            verification.status = "verified"
            db.session.add(verification)

        # 4. Vehicle - find by fixed plate; create only when absent.
        vehicle = Vehicle.query.filter_by(
            license_plate=vehicle_plate).first()
        if vehicle is None:
            vehicle = Vehicle(
                owner_type="driver",
                owner_id=profile.id,
                license_plate=vehicle_plate,
                make="Toyota",
                model="Corolla",
                year=2022,
                vehicle_type="sedan",
                vehicle_class=VehicleClass.COMFORT,
                passenger_capacity=4,
                status="active",
                is_available=True,
            )
            db.session.add(vehicle)
            db.session.flush()
        else:
            if (vehicle.owner_type != "driver"
                    or vehicle.owner_id != profile.id):
                raise click.ClickException(
                    f"vehicle {vehicle_plate} exists but is not owned "
                    "by the test driver; refusing to modify it")
            vehicle.status = "active"
            vehicle.is_available = True
            vehicle.is_deleted = False

        # 5. Active driver-vehicle history link.
        active_link = DriverVehicleHistory.query.filter_by(
            vehicle_id=vehicle.id, ended_at=None).first()
        if active_link is None:
            db.session.add(DriverVehicleHistory(
                driver_id=profile.id,
                vehicle_id=vehicle.id,
                started_at=now,
                ended_at=None,
                assignment_reason="shift_start",
            ))
        elif active_link.driver_id != profile.id:
            raise click.ClickException(
                f"vehicle {vehicle_plate} already has an active "
                "assignment to another driver; refusing to modify it")

        db.session.commit()

        # 6. Verify every required can_go_live gate on committed state.
        db.session.expire_all()
        fresh = db.session.get(DriverProfile, profile.id)
        checklist = can_go_live(fresh)
        if not checklist.ready:
            for check in checklist.checks:
                if not check.ok:
                    click.echo(f"FAIL {check.key}: {check.label} - "
                               f"{check.hint or 'not met'}")
            raise SystemExit(1)

        # 7. Parseable credential block.
        user = db.session.get(User, user.id)
        vehicle = db.session.get(Vehicle, vehicle.id)
        click.echo(f"TEST_DRIVER_USERNAME={user.username}")
        click.echo(f"TEST_DRIVER_NAME={user.display_name}")
        click.echo(f"TEST_DRIVER_EMAIL={user.email}")
        click.echo(f"TEST_DRIVER_PASSWORD={password}")
        click.echo(f"TEST_DRIVER_PROFILE_ID={fresh.id}")
        click.echo(f"TEST_DRIVER_DRIVER_CODE={fresh.driver_code}")
        click.echo(f"TEST_DRIVER_VEHICLE_ID={vehicle.id}")
        click.echo(f"TEST_DRIVER_VEHICLE_PLATE={vehicle.license_plate}")
        click.echo("CAN_GO_LIVE=ready")
