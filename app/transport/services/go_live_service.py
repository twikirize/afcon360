# app/transport/services/go_live_service.py
"""
AFCON360 Transport - Driver GO-LIVE capability service.

The Driver Workspace is a *participation* surface: any authenticated user with
their own live DriverProfile (and not blocked) may enter it.  Going *live*
(switching ``is_online`` so dispatch / offers can reach the driver) is a
separate, stricter capability that composes the existing authoritative gates —
it does not invent new rules.

``can_go_live`` composes (in priority order):

1. KYC capability   — ``driver_go_live_kyc_qualified`` (canonical KYC
   authority at the driver capability threshold, see KYC compliance).
2. Not blocked      — compliance not in the blocked states used by the
   workspace context gate (suspended / revoked / blacklisted).
3. Admin approval   — ``compliance_status == APPROVED`` (the same gate the
   dispatch/claim contract enforces).
4. Valid licence    — a licence number is present and not expired.
5. Vehicle          — required only when the driver's operating mode needs one
   (on-demand dispatch rejects offer-accept without a current vehicle).

Verification tier (``platform_verified`` / ``event_certified``) and document
verification are intentionally NOT hard requirements here: the general
dispatch claim does not require them, and the event-service coordination
contract keeps its own stricter tier requirement unchanged.

Changes to the composed rule set are BEHAVIORAL and must be specified before
implementation.  This module is read-mostly; treat it as a single source of
truth for the go-live answer that the dashboard, template, and REST endpoint
all consume.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, List


@dataclass(frozen=True)
class GoLiveCheckItem:
    """A single composed go-live gate check (render-ready)."""

    key: str
    label: str
    ok: bool
    required: bool = True
    hint: str = ""


@dataclass(frozen=True)
class GoLiveChecklist:
    """Read-only go-live result: ``ready`` is the composed boolean answer and
    ``checks`` lets the UI / API render the reason it is (not) ready."""

    ready: bool
    checks: List[GoLiveCheckItem]

    def to_dict(self) -> dict:
        return {
            "ready": self.ready,
            "checks": [
                {
                    "key": c.key,
                    "label": c.label,
                    "ok": c.ok,
                    "required": c.required,
                    "hint": c.hint,
                }
                for c in self.checks
            ],
        }


def service_requires_own_vehicle(driver: Any) -> bool:
    """Whether the driver's operating mode requires an assigned vehicle.

    Only on-demand dispatch makes offer-accept impossible without a vehicle
    (``DriverOfferAcceptResource`` requires ``profile.current_vehicle``).
    All other service types (shuttle, hire, charter, etc.) may operate
    without one, so the vehicle check is not a hard requirement there.
    """
    from app.transport.models import ServiceType

    try:
        service_types = list(driver.service_types or [])
    except Exception:
        service_types = []
    on_demand_value = ServiceType.ON_DEMAND.value
    for s in service_types:
        value = s.value if hasattr(s, "value") else s
        if value == on_demand_value:
            return True
    return False


def can_go_live(driver: Any) -> GoLiveChecklist:
    """Compose the authoritative go-live gates for a DriverProfile.

    Never raises for a partial/namespace driver (the workspace unit tests use
    lightweight driver objects); missing data closes a gate via its
    required-not-met path rather than an exception.
    """
    from app.auth.context import _BLOCKED_DRIVER_STATES

    now = datetime.now(timezone.utc)

    # --- 1. Participation / live profile ---------------------------------
    profile_ok = bool(getattr(driver, "id", None)) and not bool(
        getattr(driver, "is_deleted", False)
    )

    # --- 2. KYC capability (go-live threshold) ---------------------------
    try:
        from app.auth.kyc_compliance import driver_go_live_kyc_qualified

        kyc_ok = bool(driver_go_live_kyc_qualified(getattr(driver, "user_id", None)))
    except Exception:
        kyc_ok = False

    # --- 3. Blocked states ------------------------------------------------
    compliance_raw = getattr(getattr(driver, "compliance_status", None), "value", None)
    compliance_raw = compliance_raw or getattr(driver, "compliance_status", None)
    blocked_ok = str(compliance_raw or "").lower() not in _BLOCKED_DRIVER_STATES

    # --- 4. Compliance approved (same gate as dispatch claim) -------------
    approved_ok = str(compliance_raw or "").lower() == "approved"

    # --- 5. Valid licence --------------------------------------------------
    licence_number = getattr(driver, "license_number", None)
    licence_expiry = getattr(driver, "license_expiry", None)
    licence_present = bool(licence_number)
    if licence_expiry is not None:
        try:
            if licence_expiry.tzinfo is None:
                licence_expiry = licence_expiry.replace(tzinfo=timezone.utc)
            licence_not_expired = licence_expiry >= now
        except Exception:
            licence_not_expired = False
    else:
        licence_not_expired = False
    licence_ok = licence_present and licence_not_expired

    # --- 6. Vehicle (only where the operating mode requires one) ----------
    requires_vehicle = service_requires_own_vehicle(driver)
    current_vehicle = getattr(driver, "current_vehicle", None)
    vehicle_ok = (not requires_vehicle) or current_vehicle is not None
    vehicle_required = requires_vehicle

    checks: List[GoLiveCheckItem] = [
        GoLiveCheckItem(
            key="profile",
            label="Active driver profile",
            ok=profile_ok,
            required=True,
            hint="Register as a driver to continue." if not profile_ok else "",
        ),
        GoLiveCheckItem(
            key="kyc",
            label="Identity verification (KYC)",
            ok=kyc_ok,
            required=True,
            hint=(
                "Complete identity (KYC) verification to meet the driver "
                "capability threshold."
                if not kyc_ok
                else ""
            ),
        ),
        GoLiveCheckItem(
            key="blocked",
            label="Not suspended or blocked",
            ok=blocked_ok,
            required=True,
            hint="Contact support - your driver account is blocked." if not blocked_ok else "",
        ),
        GoLiveCheckItem(
            key="approval",
            label="Compliance approval",
            ok=approved_ok,
            required=True,
            hint=(
                "Your driver account is pending review / not yet approved by support."
                if not approved_ok
                else ""
            ),
        ),
        GoLiveCheckItem(
            key="licence",
            label="Valid driver licence",
            ok=licence_ok,
            required=True,
            hint=(
                "Add your driver licence number and ensure it is not expired."
                if not licence_ok
                else ""
            ),
        ),
        GoLiveCheckItem(
            key="vehicle",
            label="Assigned vehicle",
            ok=vehicle_ok,
            required=vehicle_required,
            hint=(
                "Your current operating mode requires an assigned vehicle (on-demand)."
                if requires_vehicle and not vehicle_ok
                else ""
            ),
        ),
    ]

    required_failures = [c for c in checks if c.required and not c.ok]
    return GoLiveChecklist(ready=not required_failures, checks=checks)