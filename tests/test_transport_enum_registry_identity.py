"""Contract tests for the canonical shared enum source (no database access)."""
from __future__ import annotations

import pytest

from app.utils import enums as shared_enums
from app.transport import models as transport_models


SHARED_ENUM_NAMES = (
    "ServiceType",
    "BookingStatus",
    "ComplianceStatus",
    "PaymentStatus",
    "VehicleClass",
    "IncidentSeverity",
    "Currency",
    "ProviderType",
    "VerificationTier",
    "CompensationModel",
    "ContractStatus",
)


@pytest.mark.parametrize("name", SHARED_ENUM_NAMES)
def test_transport_public_enum_is_the_canonical_shared_object(name: str) -> None:
    """Public imports from transport.models must not shadow shared enum classes."""
    assert getattr(transport_models, name) is getattr(shared_enums, name)
