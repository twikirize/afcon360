#!/usr/bin/env python
"""
scripts/setup_platform_escrow.py

Create the platform organisation and all its financial accounts.

This is a one-time setup script. Run it after the database is migrated
and before any accommodation payments are processed.

Usage:
    python scripts/setup_platform_escrow.py

Environment:
    APP_ENV=local|docker|prod   (optional, defaults to local)
    FLASK_ENV=development       (optional)

Output:
    Prints PLATFORM_ORG_ID to stdout. Copy this value into your .env
    or deployment config as PLATFORM_ORG_ID=<id>.
"""

import sys
import os
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app import create_app
from app.extensions import db
from app.identity.models.organisation import Organisation
from app.wallet.models.ledger import AccountModel, AccountOwnerType, AccountType, AccountStatus


PLATFORM_ACCOUNTS = [
    {
        'account_number': '00000001',
        'account_name': 'Platform Revenue Account',
        'account_description': 'Collects platform commissions and fees',
        'account_type': AccountType.REVENUE.value,
        'ifrs_category': 'Revenue',
        'daily_volume_limit': 1000000,
        'monthly_volume_limit': 10000000,
        'chart_of_accounts_code': 'REV-001',
        'require_dual_authorization': False,
    },
    {
        'account_number': '00000002',
        'account_name': 'Platform Escrow Account',
        'account_description': 'Holds guest payments until stay completion',
        'account_type': AccountType.ESCROW.value,
        'ifrs_category': 'Liabilities',
        'daily_volume_limit': 5000000,
        'monthly_volume_limit': 50000000,
        'chart_of_accounts_code': 'LIAB-001',
        'require_dual_authorization': True,
    },
    {
        'account_number': '00000003',
        'account_name': 'Platform Operations Account',
        'account_description': 'Platform operating expenses and payables',
        'account_type': AccountType.OPERATIONS.value,
        'ifrs_category': 'Operating',
        'daily_volume_limit': 500000,
        'monthly_volume_limit': 5000000,
        'chart_of_accounts_code': 'OPEX-001',
        'require_dual_authorization': False,
    },
    {
        'account_number': '00000004',
        'account_name': 'Platform Settlement Account',
        'account_description': 'Bulk payout processing account',
        'account_type': AccountType.SETTLEMENT.value,
        'ifrs_category': 'Payables',
        'daily_volume_limit': 2000000,
        'monthly_volume_limit': 20000000,
        'chart_of_accounts_code': 'LIAB-002',
        'require_dual_authorization': True,
    },
    {
        'account_number': '00000005',
        'account_name': 'Platform Reserve Account',
        'account_description': 'Contingency and reserve funds',
        'account_type': AccountType.RESERVE.value,
        'ifrs_category': 'Reserves',
        'daily_volume_limit': 10000000,
        'monthly_volume_limit': 100000000,
        'chart_of_accounts_code': 'EQTY-001',
        'require_dual_authorization': True,
    },
]


def get_or_create_platform_org() -> tuple[Organisation, bool]:
    """
    Find or create the platform organisation.

    Returns:
        (organisation, created) where created is True if the org was newly created.
    """
    org = Organisation.query.filter_by(legal_name="AFCON360 Platform").first()
    if org:
        return org, False

    org = Organisation(
        org_id=str(uuid.uuid4()),
        legal_name="AFCON360 Platform",
        org_type="platform",
        country="UG",
        verification_status="verified",
        lifecycle_state="approved",
        is_active=True,
        is_operational=True,
        contact_email="platform@afcon360.com",
        contact_phone="+256-700-000000",
        headquarters_address="Kampala, Uganda",
    )
    db.session.add(org)
    db.session.flush()
    return org, True


def setup_platform_accounts(org: Organisation) -> list[AccountModel]:
    """
    Create or update all platform accounts.
    """
    accounts = []
    for data in PLATFORM_ACCOUNTS:
        account = AccountModel.query.filter_by(
            account_number=data['account_number']
        ).first()
        if account:
            account.account_name = data['account_name']
            account.account_description = data['account_description']
            account.account_type = data['account_type']
            account.ifrs_category = data['ifrs_category']
            account.daily_volume_limit = data['daily_volume_limit']
            account.monthly_volume_limit = data['monthly_volume_limit']
            account.chart_of_accounts_code = data['chart_of_accounts_code']
            account.require_dual_authorization = data['require_dual_authorization']
            account.status = AccountStatus.ACTIVE
            account.platform_account = True
            account.owner_type = AccountOwnerType.PLATFORM
            account.user_id = org.id
        else:
            account = AccountModel(
                account_number=data['account_number'],
                account_name=data['account_name'],
                account_description=data['account_description'],
                user_id=org.id,
                owner_type=AccountOwnerType.PLATFORM,
                platform_account=True,
                account_type=data['account_type'],
                status=AccountStatus.ACTIVE,
                currency='USD',
                ifrs_category=data['ifrs_category'],
                daily_volume_limit=data['daily_volume_limit'],
                monthly_volume_limit=data['monthly_volume_limit'],
                chart_of_accounts_code=data['chart_of_accounts_code'],
                require_dual_authorization=data['require_dual_authorization'],
            )
            db.session.add(account)
        db.session.flush()
        accounts.append(account)
    return accounts


def main() -> None:
    app = create_app()
    with app.app_context():
        try:
            org, org_created = get_or_create_platform_org()
            accounts = setup_platform_accounts(org)
            db.session.commit()

            print("=" * 60)
            print("PLATFORM ACCOUNT SETUP COMPLETE")
            print("=" * 60)
            print(f"Organisation ID (internal): {org.id}")
            print(f"Organisation public_id:     {org.org_id}")
            print()
            for acc in accounts:
                print(f"  {acc.account_number}: {acc.account_name} ({acc.account_type})")
            print("=" * 60)
            print("Set this in your .env or deployment config:")
            print(f"PLATFORM_ORG_ID={org.id}")
            print("=" * 60)

        except Exception as exc:
            db.session.rollback()
            print(f"ERROR: {exc}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
