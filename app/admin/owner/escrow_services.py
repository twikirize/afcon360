"""
app/admin/owner/escrow_services.py

Escrow Account Management Service
Owner-level operations for creating and managing escrow accounts.
"""

from decimal import Decimal
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from flask import current_app
from app.extensions import db
from app.wallet.models.ledger import AccountModel, AccountOwnerType, AccountType, AccountStatus
from app.wallet.repositories.ledger_repository import LedgerRepository
from app.admin.owner.utils import log_owner_action
import logging
import uuid

logger = logging.getLogger(__name__)


ESCROW_SERVICE_TYPES = {
    'accommodation': {
        'display_name': 'Accommodation',
        'icon': 'fa-bed',
        'default_account_number_prefix': 'ESC-ACC',
        'description': 'Holds guest payments for accommodation bookings until check-out confirmation'
    },
    'transport': {
        'display_name': 'Transport',
        'icon': 'fa-bus',
        'default_account_number_prefix': 'ESC-TRN',
        'description': 'Holds passenger payments for transport bookings until trip completion'
    },
    'events': {
        'display_name': 'Events',
        'icon': 'fa-calendar-alt',
        'default_account_number_prefix': 'ESC-EVT',
        'description': 'Holds ticket payments for events until event completion'
    },
    'tourism': {
        'display_name': 'Tourism',
        'icon': 'fa-umbrella-beach',
        'default_account_number_prefix': 'ESC-TOU',
        'description': 'Holds payments for tourism services until service delivery'
    },
    'tournament': {
        'display_name': 'Tournament',
        'icon': 'fa-trophy',
        'default_account_number_prefix': 'ESC-TRN',
        'description': 'Holds payments for tournament participation and prizes'
    },
    'wallet': {
        'display_name': 'Wallet',
        'icon': 'fa-wallet',
        'default_account_number_prefix': 'ESC-WLT',
        'description': 'Holds wallet deposits and transfers for dispute resolution'
    },
}


class EscrowService:
    """Service for managing escrow accounts across all modules."""

    @staticmethod
    def get_all_escrow_accounts() -> List[Dict[str, Any]]:
        """Get all platform escrow accounts with balances."""
        accounts = AccountModel.query.filter_by(
            platform_account=True,
            account_type=AccountType.ESCROW.value
        ).order_by(AccountModel.account_number).all()

        result = []
        ledger_repo = LedgerRepository(db.session)
        for account in accounts:
            balance = ledger_repo.get_balance(account.id, account.currency)
            service_type = None
            display_name = 'Unknown'
            if account.extra_data:
                service_type = account.extra_data.get('service_type')
                if service_type and service_type in ESCROW_SERVICE_TYPES:
                    display_name = ESCROW_SERVICE_TYPES[service_type]['display_name']
            result.append({
                'account': account,
                'balance': balance,
                'service_type': service_type,
                'display_name': display_name
            })

        return result

    @staticmethod
    def get_escrow_account(account_id: str) -> Optional[AccountModel]:
        """Get a specific escrow account by UUID."""
        return AccountModel.query.filter_by(
            id=account_id,
            platform_account=True,
            account_type=AccountType.ESCROW.value
        ).first()

    @staticmethod
    def get_escrow_account_by_service(service_type: str) -> Optional[AccountModel]:
        """Get escrow account for a specific service type."""
        if service_type not in ESCROW_SERVICE_TYPES:
            return None

        return AccountModel.query.filter(
            AccountModel.platform_account == True,
            AccountModel.account_type == AccountType.ESCROW.value,
            AccountModel.extra_data.contains({'service_type': service_type})
        ).first()

    @staticmethod
    def create_escrow_account(
        service_type: str,
        created_by: int,
        account_name: Optional[str] = None,
        description: Optional[str] = None,
        daily_limit: Optional[Decimal] = None,
        monthly_limit: Optional[Decimal] = None,
        require_dual_auth: bool = True
    ) -> tuple[bool, Optional[AccountModel], Optional[str]]:
        """
        Create a new escrow account for a service type.

        Returns:
            (success, account, error_message)
        """
        if service_type not in ESCROW_SERVICE_TYPES:
            return False, None, f"Invalid service type: {service_type}"

        existing = EscrowService.get_escrow_account_by_service(service_type)
        if existing:
            return False, existing, f"Escrow account already exists for {service_type}"

        service_info = ESCROW_SERVICE_TYPES[service_type]
        account_number = f"{service_info['default_account_number_prefix']}-{datetime.now(timezone.utc).strftime('%Y%m')}-{uuid.uuid4().hex[:4].upper()}"

        platform_org_id = current_app.config.get('PLATFORM_ORG_ID')
        if not platform_org_id:
            return False, None, "Platform organisation not configured. Please set PLATFORM_ORG_ID in .env"

        account = AccountModel(
            account_number=account_number,
            account_name=account_name or f"Escrow - {service_info['display_name']}",
            account_description=description or service_info['description'],
            user_id=platform_org_id,
            owner_type=AccountOwnerType.PLATFORM.value,
            platform_account=True,
            account_type=AccountType.ESCROW.value,
            status=AccountStatus.ACTIVE.value,
            currency='USD',
            daily_volume_limit=daily_limit or Decimal('1000000'),
            monthly_volume_limit=monthly_limit or Decimal('10000000'),
            require_dual_authorization=require_dual_auth,
            extra_data={
                'service_type': service_type,
                'service_display_name': service_info['display_name'],
                'created_by': created_by,
                'created_at': datetime.now(timezone.utc).isoformat(),
                'icon': service_info['icon']
            }
        )

        try:
            db.session.add(account)
            db.session.commit()

            log_owner_action(
                action='escrow_account_created',
                category='financial',
                details={
                    'account_id': str(account.id),
                    'account_number': account_number,
                    'service_type': service_type
                }
            )

            logger.info(f"Escrow account created for {service_type}: {account_number}")
            return True, account, None

        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to create escrow account: {e}")
            return False, None, str(e)

    @staticmethod
    def freeze_account(account_id: str, reason: str, frozen_by: int) -> tuple[bool, str]:
        """Freeze an escrow account."""
        account = EscrowService.get_escrow_account(account_id)
        if not account:
            return False, "Account not found"

        if account.status == AccountStatus.FROZEN.value:
            return False, "Account is already frozen"

        account.freeze(reason, frozen_by)

        try:
            db.session.commit()
            log_owner_action(
                action='escrow_account_frozen',
                category='financial',
                details={
                    'account_number': account.account_number,
                    'account_id': str(account.id),
                    'reason': reason
                }
            )
            return True, "Account frozen successfully"
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to freeze account: {e}")
            return False, str(e)

    @staticmethod
    def unfreeze_account(account_id: str, unfrozen_by: int) -> tuple[bool, str]:
        """Unfreeze an escrow account."""
        account = EscrowService.get_escrow_account(account_id)
        if not account:
            return False, "Account not found"

        if account.status != AccountStatus.FROZEN.value:
            return False, "Account is not frozen"

        account.unfreeze()

        try:
            db.session.commit()
            log_owner_action(
                action='escrow_account_unfrozen',
                category='financial',
                details={
                    'account_number': account.account_number,
                    'account_id': str(account.id)
                }
            )
            return True, "Account unfrozen successfully"
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to unfreeze account: {e}")
            return False, str(e)

    @staticmethod
    def get_account_balance(account_id: str) -> Decimal:
        """Get the balance of an escrow account."""
        account = EscrowService.get_escrow_account(account_id)
        if not account:
            return Decimal('0')
        ledger_repo = LedgerRepository(db.session)
        return ledger_repo.get_balance(account.id, account.currency)

    @staticmethod
    def get_account_transactions(account_id: str, limit: int = 50) -> List[Any]:
        """Get recent transactions for an escrow account."""
        from app.wallet.models.ledger import LedgerEntryModel

        return LedgerEntryModel.query.filter_by(
            account_id=account_id
        ).order_by(LedgerEntryModel.created_at.desc()).limit(limit).all()

    @staticmethod
    def get_service_stats() -> Dict[str, Any]:
        """Get statistics about escrow accounts by service type."""
        accounts = AccountModel.query.filter_by(
            platform_account=True,
            account_type=AccountType.ESCROW.value
        ).all()

        stats = {
            'total_accounts': len(accounts),
            'total_balance': Decimal('0'),
            'by_service': {},
            'frozen_count': 0
        }

        ledger_repo = LedgerRepository(db.session)
        for account in accounts:
            balance = ledger_repo.get_balance(account.id, account.currency)
            stats['total_balance'] += balance

            service_type = account.extra_data.get('service_type') if account.extra_data else 'unknown'
            if service_type not in stats['by_service']:
                stats['by_service'][service_type] = {
                    'account_id': str(account.id),
                    'account_number': account.account_number,
                    'balance': Decimal('0'),
                    'status': account.status,
                    'display_name': ESCROW_SERVICE_TYPES.get(service_type, {}).get('display_name', service_type.title())
                }
            stats['by_service'][service_type]['balance'] += balance

            if account.status == AccountStatus.FROZEN.value:
                stats['frozen_count'] += 1

        return stats
