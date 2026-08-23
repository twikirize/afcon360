# app/identity/services/organisation_kyb_service.py
"""
Organisation KYB (Know Your Business) status service.

Aggregates organisation KYB state from the existing KYB tables
(OrganisationVerification, OrganisationKYBCheck, OrganisationUBO,
OrganisationKYBDocument) into a clear, step-by-step status used by:
  * the organisation KYB dashboard (completed vs pending requirements), and
  * transaction gating in KYCLimitService (basic KYB to transact at all;
    full KYB incl. source of funds only for personal transfers / large-value).

No new PostgreSQL ENUMs are introduced (per project policy); step names are an
application-level registry and source-of-funds is tracked as a KYB document
type rather than a new check_type.
"""

from typing import Dict, Any, List, Optional

from decimal import Decimal

from app.extensions import db
from app.identity.models.organisation import Organisation
from app.identity.models.kyb import (
    OrganisationVerification,
    OrganisationKYBCheck,
    OrganisationUBO,
    OrganisationKYBDocument,
)

# Application-level KYB step registry. "tier" indicates when the step is required:
#   basic  -> required for the organisation to transact at all (L1)
#   full   -> additionally required for personal transfers / large-value (L2)
STEP_REGISTRY = [
    {"key": "business_registration", "label": "Business Registration", "tier": "basic"},
    {"key": "identity", "label": "Identity Verification", "tier": "basic"},
    {"key": "tax", "label": "Tax / TIN Verification", "tier": "basic"},
    {"key": "license", "label": "Operating Licence", "tier": "basic"},   # conditional on org type
    {"key": "ubo", "label": "Ultimate Beneficial Owner (UBO)", "tier": "full"},
    {"key": "sanctions", "label": "Sanctions Screening", "tier": "full"},
    {"key": "source_of_funds", "label": "Source of Funds", "tier": "full"},
]

# Default large-value threshold (overridable per organisation via setting).
DEFAULT_LARGE_TRANSACTION_THRESHOLD = 10000


class OrganisationKYBService:
    """Compute and summarise organisation KYB status from existing records."""

    @classmethod
    def _step_statuses(cls, org: Organisation) -> Dict[str, Dict[str, Any]]:
        """Return raw completion status for every registered step."""
        labels = {s["key"]: s["label"] for s in STEP_REGISTRY}
        org_id = org.id

        reg = OrganisationVerification.query.filter_by(
            organisation_id=org_id, status="verified"
        ).first()
        identity = OrganisationKYBCheck.query.filter_by(
            organisation_id=org_id, check_type="identity", status="passed"
        ).first()
        tax = OrganisationKYBCheck.query.filter_by(
            organisation_id=org_id, check_type="tax", status="passed"
        ).first()
        license_chk = OrganisationKYBCheck.query.filter_by(
            organisation_id=org_id, check_type="license", status="passed"
        ).first()
        ubo = OrganisationUBO.query.filter_by(
            organisation_id=org_id, is_deleted=False
        ).first()
        ubo_done = bool(ubo and ubo.verified_at)
        sanctions = OrganisationKYBCheck.query.filter_by(
            organisation_id=org_id, check_type="sanctions", status="passed"
        ).first()
        sof = OrganisationKYBDocument.query.filter_by(
            organisation_id=org_id, document_type="source_of_funds",
            verification_status="verified"
        ).first()

        license_required = bool(getattr(org, "requires_license", lambda: False)())

        return {
            "business_registration": {
                "label": labels["business_registration"],
                "required": True,
                "done": bool(reg),
                "record": "organisation_verifications" if reg else None,
            },
            "identity": {
                "label": labels["identity"],
                "required": True,
                "done": bool(identity),
                "record": "organisation_kyb_checks" if identity else None,
            },
            "tax": {
                "label": labels["tax"],
                "required": True,
                "done": bool(tax),
                "record": "organisation_kyb_checks" if tax else None,
            },
            "license": {
                "label": labels["license"],
                "required": license_required,
                "done": bool(license_chk) if license_required else True,
                "record": "organisation_kyb_checks" if license_chk else None,
            },
            "ubo": {
                "label": labels["ubo"],
                "required": True,
                "done": ubo_done,
                "record": "organisation_ubos" if ubo else None,
            },
            "sanctions": {
                "label": labels["sanctions"],
                "required": True,
                "done": bool(sanctions),
                "record": "organisation_kyb_checks" if sanctions else None,
            },
            "source_of_funds": {
                "label": labels["source_of_funds"],
                "required": True,
                "done": bool(sof),
                "record": "organisation_kyb_documents" if sof else None,
            },
        }

    @classmethod
    def compute_status(cls, org: Organisation) -> Dict[str, Any]:
        """Compute full KYB status for one organisation."""
        steps = cls._step_statuses(org)

        basic_steps = [s["key"] for s in STEP_REGISTRY if s["tier"] == "basic"]
        full_steps = [s["key"] for s in STEP_REGISTRY if s["tier"] == "full"]

        basic_required = [k for k in basic_steps if steps[k]["required"]]
        full_required = basic_required + [k for k in full_steps if steps[k]["required"]]

        is_operational_kyb = all(steps[k]["done"] for k in basic_required)
        is_full_kyb = all(steps[k]["done"] for k in full_required)

        pending = [
            {"key": k, "label": next(s["label"] for s in STEP_REGISTRY if s["key"] == k)}
            for k in full_required if not steps[k]["done"]
        ]

        kyb_level = 2 if is_full_kyb else (1 if is_operational_kyb else 0)

        return {
            "organisation_id": org.id,
            "org_id": getattr(org, "org_id", None),
            "legal_name": getattr(org, "legal_name", None),
            "verification_status": getattr(org, "verification_status", None),
            "kyb_level": kyb_level,
            "is_operational_kyb": is_operational_kyb,   # L1 complete
            "is_full_kyb": is_full_kyb,                  # L2 complete
            "steps": steps,
            "pending_requirements": pending,
        }

    @classmethod
    def is_personal_transfer(cls, recipient_user_id: Optional[int]) -> bool:
        """True if the recipient is an individual (personal) wallet, not an org."""
        if not recipient_user_id:
            return False
        from app.identity.models.user import User
        from app.wallet.models.ledger import AccountModel, AccountOwnerType
        # A personal transfer is one whose recipient wallet is a USER-owned account.
        if AccountModel.query.filter_by(
            user_id=recipient_user_id, owner_type=AccountOwnerType.USER
        ).first():
            return True
        # Explicitly NOT personal when the recipient is an Organisation (covers the
        # rare case where an org id collides with a user id).
        if db.session.get(Organisation, recipient_user_id):
            return False
        # Otherwise treat a resolved individual user as personal.
        return db.session.get(User, recipient_user_id) is not None

    @classmethod
    def large_value_threshold(cls, org: Organisation, currency: str = "UGX") -> Decimal:
        from decimal import Decimal
        try:
            raw = org.get_setting("large_transaction_threshold", DEFAULT_LARGE_TRANSACTION_THRESHOLD)
        except Exception:
            raw = DEFAULT_LARGE_TRANSACTION_THRESHOLD
        try:
            value = Decimal(str(raw))
        except (TypeError, ValueError):
            return Decimal(str(DEFAULT_LARGE_TRANSACTION_THRESHOLD))
        # A missing/zero/negative threshold is not meaningful; fall back to default.
        if value is None or value <= 0:
            return Decimal(str(DEFAULT_LARGE_TRANSACTION_THRESHOLD))
        return value

    @classmethod
    def requires_full_kyb(cls, org: Organisation, amount, currency: str = "UGX",
                          recipient_user_id: Optional[int] = None) -> bool:
        """Whether this transaction forces full KYB (personal transfer or large-value)."""
        from decimal import Decimal
        try:
            amt = Decimal(str(amount))
        except (TypeError, ValueError):
            amt = Decimal("0")
        is_large = amt >= cls.large_value_threshold(org, currency)
        is_personal = cls.is_personal_transfer(recipient_user_id)
        return is_large or is_personal

    @classmethod
    def get_all_summaries(cls) -> List[Dict[str, Any]]:
        """Compliance/owner overview of KYB status for all registered orgs."""
        orgs = Organisation.query.filter_by(is_deleted=False).all()
        return [cls.compute_status(o) for o in orgs]
