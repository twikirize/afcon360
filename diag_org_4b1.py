"""Diagnostic: capture the exact IntegrityError / constraint during org creation."""
import os
import sys
import uuid
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.extensions import db

app = create_app("testing")
os.environ["APP_ENV"] = "testing"


def main():
    with app.app_context():
        from app.identity.models.user import User
        from app.identity.services.organization_registration import (
            OrganizationRegistrationService,
        )

        # must be phone/email verified + KYC tier 2
        with patch(
            "app.auth.kyc_compliance.calculate_kyc_tier",
            return_value={"tier": 2},
        ), patch(
            "app.identity.services.organization_registration.OrganizationRegistrationService.generate_org_id",
            side_effect=lambda: str(uuid.uuid4()),
        ):
            user = User(
                public_id=str(uuid.uuid4()),
                email=f"diag-{uuid.uuid4().hex[:8]}@example.com",
                password_hash="hashed",
                is_active=True,
                phone_verified=True,
                email_verified=True,
            )
            db.session.add(user)
            db.session.flush()

            data = {
                "legal_name": f"Diag Org {uuid.uuid4().hex[:8]}",
                "org_type": "hotel",
                "country": "UG",
                "tax_id": str(uuid.uuid4()),
                "vat_number": f"VAT-{uuid.uuid4().hex[:8]}",
                "contact_email": f"org-{uuid.uuid4().hex[:8]}@example.com",
                "contact_phone": "+256700000000",
            }

            from app.utils.transactions import db_transaction
            from app.identity.models.organisation import Organisation

            # Try the full service first, capturing the error message
            try:
                org, errors = OrganizationRegistrationService.create_organization(
                    data, user, {"registration_mode": "testing"}
                )
                print("SERVICE result org:", org, "errors:", errors)
            except Exception as e:
                print("SERVICE raised:", type(e).__name__, e)

            # Now try raw inserts step-by-step with a real transaction to find
            # the exact failing constraint.
            try:
                with db_transaction("diag"):
                    org = Organisation(
                        org_id=OrganizationRegistrationService.generate_org_id(),
                        legal_name=data["legal_name"],
                        org_type=data["org_type"],
                        business_category=__import__(
                            "app.identity.models.organization_types",
                            fromlist=["OrganizationType"],
                        ).OrganizationType(data["org_type"]),
                        country=data["country"],
                        tax_id=data["tax_id"],
                        vat_number=data["vat_number"],
                        contact_email=data["contact_email"],
                        contact_phone=data["contact_phone"],
                        verification_status="pending",
                        lifecycle_state="registered",
                        is_active=True,
                        is_operational=False,
                    )
                    db.session.add(org)
                    db.session.flush()
                    print("STEP1 org insert OK, org.id =", org.id)
                print("STEP1 commit OK")
            except Exception as e:
                print("STEP1 FAILED:", type(e).__name__, e)

        db.session.remove()


if __name__ == "__main__":
    main()
