"""Canonical identity read contract (Identity Center rule §5).

ONE canonical identity, MANY consumers: Profile, Account, KYC and
identity-dependent onboarding (Driver / Host) all read person data from
UserProfile (the canonical person store) and verification / KYC state from
the canonical authorities (calculate_kyc_tier, KycRecord,
IndividualVerification).

This service composes those authoritative sources. It creates NO stored copy
of identity data and never mutates state; consumers must not snapshot
identity into their own tables.
"""
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, FrozenSet, List, Optional

from app.profile.models import IMMUTABLE_AFTER_VERIFICATION, get_profile_by_user


@dataclass(frozen=True)
class CanonicalIdentity:
    """Read-only projection of a System User's canonical identity."""

    public_id: str
    profile: Optional[Any] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    email_verified: bool = False
    phone_verified: bool = False
    full_name: Optional[str] = None
    date_of_birth: Optional[str] = None
    gender: Optional[str] = None
    nationality: Optional[str] = None
    id_type: Optional[str] = None
    id_number: Optional[str] = None
    verification_status: str = "pending"
    kyc_tier: int = 0
    kyc_decisions: Dict[str, Any] = field(default_factory=dict)
    immutable_fields: FrozenSet[str] = field(default_factory=frozenset)
    missing_immutable_fields: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "public_id": self.public_id,
            "email": self.email,
            "phone": self.phone,
            "email_verified": self.email_verified,
            "phone_verified": self.phone_verified,
            "full_name": self.full_name,
            "date_of_birth": self.date_of_birth,
            "gender": self.gender,
            "nationality": self.nationality,
            "id_type": self.id_type,
            "id_number": self.id_number,
            "verification_status": self.verification_status,
            "kyc_tier": self.kyc_tier,
            "immutable_fields": sorted(self.immutable_fields),
            "missing_immutable_fields": self.missing_immutable_fields,
        }

    def is_verified(self) -> bool:
        return self.verification_status == "verified"


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def get_canonical_identity(user) -> CanonicalIdentity:
    """Compose canonical identity from the authoritative sources.

    Args:
        user: a User instance or a public_id (UUID) string.

    Returns:
        CanonicalIdentity projection. KYC tier is always derived from
        calculate_kyc_tier() (the canonical KYC authority), never from the
        User.kyc_level / UserProfile.kyc_level snapshots.
    """
    # Public_id strings are resolved to the real User row so the canonical
    # KYC authority can be queried by internal id and user-linked fields
    # (email, phone flags) are still readable.
    if isinstance(user, str):
        from app.identity.models.user import User

        user = User.query.filter_by(public_id=user).first()

    profile = get_profile_by_user(user)
    public_id = getattr(user, "public_id", None)

    def _profile_value(field_name):
        return getattr(profile, field_name, None) if profile is not None else None

    email = _profile_value("email") or getattr(user, "email", None)
    phone = _profile_value("phone_number") or getattr(user, "phone", None)
    # User flags are canonical for email/phone verification because the
    # verification flows update the User row while legacy UserProfile copies
    # may lag (see kyc_compliance.calculate_kyc_tier).
    user_email_verified = getattr(user, "email_verified", None)
    user_phone_verified = getattr(user, "phone_verified", None)
    email_verified = (
        user_email_verified
        if user_email_verified is not None
        else bool(_profile_value("email_verified"))
    )
    phone_verified = (
        user_phone_verified
        if user_phone_verified is not None
        else bool(_profile_value("phone_verified"))
    )

    verification_status = _profile_value("verification_status") or "pending"
    verified = verification_status == "verified"
    immutable = frozenset(IMMUTABLE_AFTER_VERIFICATION) if verified else frozenset()

    missing = sorted(
        f for f in IMMUTABLE_AFTER_VERIFICATION
        if verified and not _profile_value(f)
    )

    kyc_tier = 0
    kyc_decisions: Dict[str, Any] = {}
    if getattr(user, "id", None) is not None:
        try:
            from app.auth.kyc_compliance import calculate_kyc_tier

            kyc = calculate_kyc_tier(user.id)
            kyc_tier = int(kyc.get("tier", 0) or 0)
            kyc_decisions = kyc
        except Exception:
            # Evaluation failure never blocks a read-only projection; the
            # same authority is enforced at gate sites which fail closed.
            kyc_decisions = {"error": "unavailable"}

    return CanonicalIdentity(
        public_id=str(public_id) if public_id is not None else "",
        profile=profile,
        email=email,
        phone=phone,
        email_verified=bool(email_verified),
        phone_verified=bool(phone_verified),
        full_name=_profile_value("full_name"),
        date_of_birth=_iso(_profile_value("date_of_birth")),
        gender=_profile_value("gender"),
        nationality=_profile_value("nationality"),
        id_type=_profile_value("id_type"),
        id_number=_profile_value("id_number"),
        verification_status=verification_status,
        kyc_tier=kyc_tier,
        kyc_decisions=kyc_decisions,
        immutable_fields=immutable,
        missing_immutable_fields=missing,
    )