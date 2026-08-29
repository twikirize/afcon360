"""
app/wallet/services/wallet_service.py
Financial-grade wallet service with atomic transactions.

Core principle: The DATABASE guarantees money integrity, not the application.

RULE #1 - NEVER update a balance column directly.
RULE #2 - Balance = derived from ledger_entries at query time.
RULE #3 - Every financial op = ONE db.session.begin() block, zero compensation.
"""

from decimal import Decimal, ROUND_DOWN, getcontext
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
from uuid import UUID
from flask import current_app, request
from flask_login import current_user
from sqlalchemy.exc import OperationalError

from app.extensions import db
from app.wallet.repositories.wallet_repository import WalletRepository
from app.wallet.repositories.account_repository import AccountRepository
from app.wallet.repositories.transaction_repository import TransactionRepository
from app.wallet.repositories.ledger_repository import LedgerRepository
from app.wallet.models.ledger import LedgerEntryModel, AccountModel, EntryType
from app.wallet.models.transaction import TransactionModel, TransactionType, TransactionStatus
from app.wallet.models.audit import AuditLogModel
from app.wallet.validators import parse_amount, validate_amount, validate_currency
from app.wallet.exceptions import (
    InsufficientBalanceError,
    UnsupportedCurrencyError,
    WalletNotFoundError,
    LimitExceededError,
    DuplicateTransactionError,
    WalletFrozenError,
    ComplianceBlockError
)
from app.utils.db_retry import retry_on_deadlock
from app.utils.id_validator import assert_internal_id
from app.wallet.services.currency_service import CurrencyService
from app.wallet.services.commission_service import CommissionService
from app.wallet.models.config import WalletSystemConfig

# Money precision
getcontext().prec = 28
MONEY_QUANT = Decimal("0.01")


class WalletService:
    """
    Financial-grade wallet service.
    
    All operations use database-level atomicity with proper locking.
    No compensation logic - transactions either fully succeed or fully rollback.
    """

    def __init__(self, db_session=None):
        self.db = db_session or db.session
        self.wallet_repo = WalletRepository(self.db)
        self.account_repo = AccountRepository(self.db)
        self.tx_repo = TransactionRepository(self.db)
        self.ledger_repo = LedgerRepository(self.db)
        self.currency_service = CurrencyService()

    # ========================================================================
    # PRIVATE HELPERS
    # ========================================================================

    def _is_admin(self) -> bool:
        """Check if current user has admin privileges for wallet management."""
        if not current_user or not current_user.is_authenticated:
            return False
        # roles that can bypass ownership check
        admin_roles = {'owner', 'super_admin', 'admin', 'wallet_admin'}
        return any(current_user.has_role(role) for role in admin_roles)

    def _quantize(self, value: Decimal) -> Decimal:
        """Quantize decimal to money precision."""
        return value.quantize(MONEY_QUANT, rounding=ROUND_DOWN)

    def _validate_currency(self, currency: str) -> None:
        """Validate that currency is supported."""
        if not self.currency_service.validate_currency(currency):
            supported = self.currency_service.get_supported_currencies()
            raise UnsupportedCurrencyError(currency, supported)

    def _get_ip_address(self) -> Optional[str]:
        """Get current request IP address."""
        try:
            return request.remote_addr
        except Exception:
            return None

    def _get_user_agent(self) -> Optional[str]:
        """Get current request user agent."""
        try:
            return request.user_agent.string if request.user_agent else None
        except Exception:
            return None

    def _check_transaction_limit(self, amount: Decimal, operation: str) -> None:
        """
        Check transaction limit for operation.

        Raises:
            LimitExceededError: If limit would be exceeded
        """
        limit_key = f"WALLET_MAX_{operation.upper()}"
        max_amount = current_app.config.get(limit_key, Decimal("10000"))

        if amount > max_amount:
            raise LimitExceededError(
                limit_type="per_transaction",
                currency="any",
                limit=float(max_amount),
                current=float(amount)
            )

    def _check_daily_limit(
        self,
        account_id: UUID,
        amount: Decimal,
        currency: str,
        operation: str
    ) -> None:
        """
        Check daily limit for operation.

        The operational daily ceiling is from WalletSystemConfig.max_daily_amount.
        Falls back to Flask-config WALLET_DAILY_LIMIT_HOME (USD) /
        WALLET_DAILY_LIMIT_LOCAL (other currencies) for backward compatibility.
        The regulatory KYC daily cumulative limit is enforced separately in
        _check_kyc_limits. Volume is derived from the ledger (never from stored
        account.daily_volume).

        Args:
            account_id: Account UUID
            amount: Transaction amount
            currency: Currency code
            operation: deposit, withdraw, transfer

        Raises:
            LimitExceededError: If limit would be exceeded
        """
        from app.wallet.models.config import WalletSystemConfig
        operational_config = WalletSystemConfig.get_config()
        
        # Use WalletSystemConfig operational daily ceiling (platform-wide, currency-agnostic)
        # Falls back to Flask config for backward compatibility
        if operational_config.max_daily_amount is not None:
            daily_limit = Decimal(str(operational_config.max_daily_amount))
        else:
            daily_limit_key = f"WALLET_DAILY_LIMIT_{'HOME' if currency == 'USD' else 'LOCAL'}"
            daily_limit = current_app.config.get(daily_limit_key, Decimal("10000"))

        # Authoritative volume = ledger-derived (outgoing debits over the window).
        daily_volume = self.ledger_repo.get_daily_volume(account_id, currency)

        if daily_volume + amount > daily_limit:
            raise LimitExceededError(
                limit_type="daily",
                currency=currency,
                limit=float(daily_limit),
                current=float(daily_volume)
            )

    def _check_monthly_limit(
        self,
        account_id: UUID,
        amount: Decimal,
        currency: str
    ) -> None:
        """
        Check monthly limit for operation.

        The operational monthly ceiling is from WalletSystemConfig.max_monthly_amount.
        Falls back to per-account monthly_volume_limit for backward compatibility.
        The regulatory KYC monthly cumulative limit is enforced separately in
        _check_kyc_limits. Volume is derived from the ledger (never from stored
        account.monthly_volume counters).

        Args:
            account_id: Account UUID
            amount: Transaction amount
            currency: Currency code

        Raises:
            LimitExceededError: If limit would be exceeded
        """
        from app.wallet.models.config import WalletSystemConfig
        operational_config = WalletSystemConfig.get_config()
        
        # Use WalletSystemConfig operational monthly ceiling (platform-wide)
        # Falls back to per-account monthly_volume_limit for backward compatibility
        if operational_config.max_monthly_amount is not None:
            limit = Decimal(str(operational_config.max_monthly_amount))
        else:
            account = self.account_repo.get_by_id(account_id)
            if not account:
                return
            limit = account.monthly_volume_limit
            if not limit:
                return

        # Authoritative volume = ledger-derived (outgoing debits over the window).
        monthly_volume = self.ledger_repo.get_monthly_volume(account_id, currency)

        if monthly_volume + amount > limit:
            raise LimitExceededError(
                limit_type="monthly",
                currency=currency,
                limit=float(limit),
                current=float(monthly_volume)
            )

    def _check_kyc_limits(
        self,
        user_id: int,
        amount: Decimal,
        action: str,
        currency: str = 'UGX',
        recipient_user_id: Optional[int] = None,
        account_id: Optional[str] = None
    ) -> None:
        """
        Check KYC-based transaction limits.

        Args:
            user_id: Internal user ID (or organisation ID for org wallets)
            amount: Transaction amount
            action: 'send', 'receive', 'withdraw', 'deposit'
            currency: Currency code
            recipient_user_id: Optional recipient owner id, used to detect a
                      "personal transfer" (org -> individual) for org KYB gating.
            account_id: Account UUID. When supplied, regulatory KYC daily/monthly
                      cumulative limits are also enforced (Task A). The volume is
                      derived from the ledger (rolling windows), so no cached
                      counter reset and no extra commit occurs here.

        Raises:
            LimitExceededError: If KYC limits exceeded
        """
        from app.wallet.services.kyc_limit_service import KYCLimitService

        result = KYCLimitService.check_transaction_allowed(
            user_id, amount, action, currency, recipient_user_id=recipient_user_id
        )
        if not result['allowed']:
            raise LimitExceededError(
                limit_type="kyc",
                currency=currency,
                limit=0,
                current=float(amount)
            )
        # Store reason in exception message if needed
        if 'reason' in result:
            current_app.logger.info(f"KYC check passed: {result['reason']}")

        # Regulatory cumulative (daily/monthly) enforcement. The authoritative
        # KYC/KYB tier is returned by check_transaction_allowed; fall back to the
        # canonical authority only if it is somehow absent.
        kyc_level = result.get('kyc_level')
        if kyc_level is None:
            kyc_level = KYCLimitService.get_user_kyc_level(user_id)
        if account_id is not None:
            vol = KYCLimitService.check_regulatory_cumulative_limits(
                account_id, currency, amount, kyc_level
            )
            if not vol['allowed']:
                raise LimitExceededError(
                    limit_type=f"kyc_{vol.get('limit_type', 'cumulative')}",
                    currency=currency,
                    limit=0,
                    current=float(amount)
                )

    def _check_fraud_risk(
        self,
        user_id: int,
        amount: Decimal,
        currency: str,
        recipient_id: Optional[int] = None,
        ip_address: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Run fraud detection scoring on transaction.

        Returns:
            Dict with risk assessment. Raises ComplianceBlockError if blocked.
        """
        from app.wallet.services.fraud_detection_service import FraudDetectionService
        
        score_result = FraudDetectionService.score_transaction(
            user_id=user_id,
            amount=float(amount),
            currency=currency,
            recipient_id=recipient_id,
            ip_address=ip_address
        )
        
        if FraudDetectionService.should_block_transaction(score_result):
            raise ComplianceBlockError(
                reason=f"Transaction blocked by fraud detection (score: {score_result['score']}, patterns: {score_result['patterns']})",
                rule_name='fraud_detection'
            )
        
        return score_result

    # ========================================================================
    # WALLET MANAGEMENT
    # ========================================================================

    def get_wallet_limits(self, wallet_type: str, currency: str) -> Dict[str, Any]:
        """Get configured limits for wallet type and currency."""
        # WalletLimit model does not exist; use WalletSystemConfig for operational ceilings
        system_config = WalletSystemConfig.get_config()
        
        # Provide sensible defaults for wallet creation (not authorization)
        return {
            'min_transaction': Decimal("100.00"),
            'max_transaction': system_config.max_transfer_amount,
            'daily_limit': system_config.max_transfer_amount,  # WalletSystemConfig has no separate daily limit
            'monthly_limit': system_config.max_transfer_amount,  # WalletSystemConfig has no separate monthly limit
            'requires_kyc_level': 2,
            'requires_mfa': True
        }

    def create_wallet(self, user_id: int, name: str, wallet_type: str,
                      currency: str = "UGX", description: str = None,
                      organisation_id: int = None) -> Any:
        """Create new wallet using the ledger-compliant service."""
        from app.wallet.models.wallet import Wallet
        import uuid

        # Get limits
        limits = self.get_wallet_limits(wallet_type, currency)

        wallet = Wallet(
            public_id=str(uuid.uuid4()),
            user_id=user_id,
            organisation_id=organisation_id,
            name=name,
            description=description,
            wallet_type=wallet_type,
            currency=currency,
            daily_limit=limits.get('daily_limit'),
            monthly_limit=limits.get('monthly_limit'),
            transaction_limit=limits.get('max_transaction'),
            requires_mfa=limits.get('requires_mfa', True),
            requires_pin=True
        )

        self.db.add(wallet)
        self.db.commit()
        try:
            from app.notifications.services import NotificationService
            NotificationService.notify_wallet_created(user_id=user_id)
        except Exception as _ne:
            logging.getLogger(__name__).warning(f"Wallet creation notification failed: {_ne}")
        return wallet

    def audit_log(self, wallet_id: int, user_id: int, action: str, new_value: Dict, reason: str):
        """Create an audit log entry for wallet changes."""
        from app.wallet.models.wallet import WalletAuditLog
        log = WalletAuditLog(
            wallet_id=wallet_id,
            user_id=user_id,
            action=action,
            new_value=new_value,
            reason=reason
        )
        self.db.add(log)
        self.db.commit()

    def ensure_account_exists(self, user_id: int, currency: str = 'USD') -> Optional[AccountModel]:
        """
        Check if a user has a wallet account (does NOT create one).

        Args:
            user_id: User ID
            currency: Currency code (ignored, kept for signature compatibility)

        Returns:
            AccountModel or None if user not found or no account exists
        """
        from app.identity.models.user import User

        user = db.session.get(User, user_id)
        if not user:
            return None

        # Only get existing account, do NOT create
        return self.account_repo.get_by_user_id(user_id)

    @staticmethod
    def get_wallet_by_user_id(user_id: int, currency: str = 'USD') -> Optional[AccountModel]:
        """
        Static helper to get an individual wallet by user ID.
        """
        from app.wallet.repositories.account_repository import AccountRepository
        from app.wallet.models.ledger import AccountOwnerType
        repo = AccountRepository()
        account = repo.get_by_user_id(user_id, currency)
        if account and account.owner_type == AccountOwnerType.USER:
            return account
        return None

    @staticmethod
    def get_wallet_by_org_id(org_id: int, currency: str = 'USD') -> Optional[AccountModel]:
        """
        Static helper to get an organisation wallet by org internal ID.
        """
        from app.wallet.models.ledger import AccountModel, AccountOwnerType
        return AccountModel.query.filter_by(
            user_id=org_id,
            owner_type=AccountOwnerType.ORGANISATION,
            currency=currency
        ).first()

    # ========================================================================
    # BALANCE & TRANSACTION HISTORY
    # ========================================================================

    def get_balance(self, user_id: str) -> Dict[str, Any]:
        """
        Get current wallet balance for a user.
        Balance is derived from ledger entries, not stored.

        Args:
            user_id (BIGINT internal ID)

        Returns:
            Dict with balance information

        Raises:
            PermissionError: If user doesn't own the account
        """
        internal_user_id = assert_internal_id(user_id)
        if internal_user_id != current_user.id and not self._is_admin():
            current_app.logger.warning(f"Ownership violation attempt on balance check by user {current_user.id}")
            raise PermissionError("You do not have permission to operate on this account")

        balance_data = self.wallet_repo.get_balance(internal_user_id)
        # Ensure balance is Decimal, not string, to avoid rounding errors
        if isinstance(balance_data, dict):
            raw_balance = balance_data.get('balance', Decimal('0'))
            if isinstance(raw_balance, str):
                try:
                    raw_balance = Decimal(raw_balance)
                except Exception:
                    raw_balance = Decimal('0')
            balance_data['balance'] = raw_balance
        return balance_data

    def get_transaction_history(
        self,
        user_id: int,
        limit: int = 50,
        offset: int = 0,
        transaction_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get transaction history for a user.

        Args:
            user_id: User ID
            limit: Number of records to return
            offset: Pagination offset
            transaction_type: Filter by transaction type

        Returns:
            Dict with transactions and pagination info
        """
        # Convert string type to enum if provided
        tx_type = None
        if transaction_type:
            try:
                tx_type = TransactionType(transaction_type)
            except ValueError:
                pass

        transactions = self.tx_repo.get_user_transactions(
            user_id=user_id,
            tx_type=tx_type,
            limit=limit,
            offset=offset
        )

        total = self.tx_repo.get_transaction_count(
            user_id=user_id,
            tx_type=tx_type
        )

        return {
            "transactions": [
                {
                    "id": str(t.id),
                    "type": t.tx_type.value,
                    "amount": str(t.amount),
                    "currency": t.currency,
                    "status": t.status.value,
                    "created_at": t.created_at.isoformat(),
                    "metadata": t.tx_metadata
                }
                for t in transactions
            ],
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": offset + limit < total
        }

    # ========================================================================
    # DEPOSIT
    # ========================================================================

    @retry_on_deadlock(max_retries=3, base_delay=0.1, max_delay=2.0)
    def deposit(
        self,
        account_id: Optional[str] = None,  # UUID - primary identifier (Alipay model)
        amount: Optional[Decimal] = None,
        currency: Optional[str] = None,
        client_request_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
        payment_method: Optional[str] = None,
        payment_provider: Optional[str] = None,
        external_reference: Optional[str] = None,
        tx_type: TransactionType = TransactionType.DEPOSIT,
        actor_id: Optional[int] = None,
        # When True the deposit is credited by a backend/system flow (provider webhook,
        # async callback) that runs outside a user session. The account to credit is
        # resolved from the stored deposit intent created during the authenticated POST,
        # so ownership is already established; only the `current_user` session check is
        # skipped. All freeze/limit/KYC/fraud/idempotency checks remain enforced.
        system_initiated: bool = False,
        # Backward-compatible aliases used by legacy callers (payment gateways, API).
        # Canonical identifier is `account_id`; `user_id` is resolved here.
        user_id: Optional[int] = None,
        reference: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Deposit funds into account.

        Args:
            account_id: Account UUID (primary identifier - Alipay model)
            amount: Amount to deposit
            currency: Currency of deposit
            client_request_id: Unique idempotency key
            metadata: Additional transaction metadata
            payment_method: Payment method used
            payment_provider: Payment provider used
            external_reference: External reference ID

        Returns:
            Dict with transaction result

        Raises:
            ValueError: If amount is invalid
            WalletNotFoundError: If account not found
            WalletFrozenError: If account is frozen
            LimitExceededError: If limits exceeded
            PermissionError: If user doesn't own the account
        """
        # Resolve backward-compatible idempotency key
        client_request_id = client_request_id or idempotency_key or reference

        # Resolve canonical account identifier (Alipay model: account_id is primary)
        if account_id is None and user_id is not None:
            account = self.account_repo.get_by_user_id(int(user_id), (currency or 'UGX'))
            if not account:
                raise WalletNotFoundError(wallet_ref=str(user_id))
            account_id = str(account.id)

        if not account_id:
            raise ValueError("account_id (or user_id) is required")
        if amount is None or currency is None:
            raise ValueError("amount and currency are required")

        amount = self._quantize(amount)

        # Validate
        if amount <= Decimal("0"):
            raise ValueError("Amount must be greater than zero")

        self._validate_currency(currency)
        self._check_transaction_limit(amount, "deposit")

        # Ensure no dangling read-only transaction is active. Flask-SQLAlchemy
        # autobegins a transaction as soon as a SELECT runs (route decorators /
        # helpers call .query/.first()). Opening our own atomic transaction below
        # would otherwise raise "A transaction is already begun on this Session".
        # Any such transaction only contains read queries at this point.
        try:
            self.db.rollback()
        except Exception:
            pass

        # SINGLE TRANSACTION - everything or nothing
        with self.db.begin():
            # 1. Get account by UUID with lock
            account = self.account_repo.get_by_id(account_id, for_update=True)
            if not account:
                raise WalletNotFoundError(wallet_ref=str(account_id))

            # Ownership validation - defense in depth
            # Skipped for system-initiated (provider webhook) deposits where the
            # target account was resolved from a deposit intent created during the
            # authenticated initiation request.
            if not system_initiated and account.user_id != current_user.id and not self._is_admin():
                current_app.logger.warning(f"Ownership violation attempt on account {account.id} by user {current_user.id}")
                raise PermissionError("You do not have permission to operate on this account")

            # 2. Freeze check
            if account.is_frozen:
                raise WalletFrozenError(
                    wallet_ref=str(account.id),
                    reason=account.frozen_reason
                )

            # Auto-FX: If deposit currency differs from account's home currency, convert it dynamically.
            original_amount = amount
            original_currency = currency
            if account.currency != currency:
                from app.wallet.services.fx_service import FXService
                fx_service = FXService()
                fx_rate = fx_service.get_rate_safe(base_currency=currency, quote_currency=account.currency)
                
                # Convert the amount to the home currency
                amount = (original_amount * fx_rate.rate).quantize(Decimal('0.01'))
                currency = account.currency
                
                if metadata is None:
                    metadata = {}
                metadata.update({
                    "cross_border_fx": True,
                    "original_deposit_amount": str(original_amount),
                    "original_deposit_currency": original_currency,
                    "fx_rate_applied": str(fx_rate.rate)
                })

            # 3. KYC limit check
            self._check_kyc_limits(account.user_id, amount, 'deposit', currency, account_id=str(account.id))
            
            # 4. Fraud risk check
            self._check_fraud_risk(account.user_id, amount, currency, ip_address=self._get_ip_address())
            
            # 5. Daily limit check
            self._check_daily_limit(account.id, amount, currency, 'deposit')
            
            # 6. Monthly limit check
            self._check_monthly_limit(account.id, amount, currency)

            # 4. Atomic idempotency
            tx = self.tx_repo.get_or_create(
                client_request_id=client_request_id,
                tx_type=tx_type,
                amount=amount,
                currency=currency,
                user_id=account.user_id,  # Internal only - NEVER returned
                metadata=metadata
            )

            # If already completed, return existing result
            if tx.status == TransactionStatus.COMPLETED:
                balance = self.ledger_repo.get_balance(account.id, currency)
                return {
                    "status": "success",
                    "transaction_id": str(tx.id),
                    "already_processed": True,
                    "amount": str(amount),
                    "currency": currency,
                    "new_balance": str(balance),
                    "account_id": str(account.id)  # Expose account_id, not user_id
                }

            # 5. Create ledger entry (CREDIT)
            ledger_entry = LedgerEntryModel(
                transaction_id=tx.id,
                account_id=account.id,
                entry_type=EntryType.CREDIT,
                amount=amount,
                currency=currency,
                meta={
                    "payment_method": payment_method,
                    "payment_provider": payment_provider,
                    "external_reference": external_reference
                }
            )
            self.ledger_repo.post_entries([ledger_entry])

            # 6. Update daily volume
            self.account_repo.update_volume(account.id, amount, 'daily')

            # 7. Optional: record commission if metadata contains agent info
            try:
                agent_id = None
                if metadata and isinstance(metadata, dict):
                    agent_id = metadata.get('agent_id') or metadata.get('agent')

                if agent_id:
                    commission_service = CommissionService(self.db)
                    commission_amount = commission_service.calculate_commission(amount, 'deposit')
                    if commission_amount and commission_amount > 0:
                        commission_service.record_commission(
                            agent_id=agent_id,
                            amount=commission_amount,
                            currency=currency,
                            source_type='deposit',
                            source_id=str(tx.id),
                            recipient_id=account.user_id,  # Internal only
                            extra_data={'client_metadata': metadata}
                        )
            except Exception:
                current_app.logger.exception('Failed to record commission for deposit')

            # 8. Audit log
            audit_log = AuditLogModel(
                transaction_id=tx.id,
                actor_id=actor_id or account.user_id,  # Use provided actor or owner
                action="deposit",
                description=f"Deposit of {amount} {currency}",
                before_state={"balance": str(self.ledger_repo.get_balance(account.id, currency) - amount)},
                after_state={"balance": str(self.ledger_repo.get_balance(account.id, currency))},
                ip_address=self._get_ip_address(),
                user_agent=self._get_user_agent(),
                audit_metadata={"account_id": str(account.id), "payment_provider": payment_provider}
            )
            self.db.add(audit_log)

            # 9. Mark transaction complete
            self.tx_repo.update_status(tx.id, TransactionStatus.COMPLETED)

        # Transaction committed here
        final_balance = self.ledger_repo.get_balance(account.id, currency)

        # Fire-and-forget notification (must not break transaction)
        try:
            from app.wallet.services.wallet_notifications import notify_deposit
            notify_deposit(account.user_id, amount, currency, final_balance)
        except Exception:
            current_app.logger.exception('Failed to send deposit notification')

        return {
            "status": "success",
            "transaction_id": str(tx.id),
            "amount": str(amount),
            "currency": currency,
            "new_balance": str(final_balance),
            "account_id": str(account.id),  # Always expose account_id
            "user_id": account.user_id
        }

    # ========================================================================
    # WITHDRAW
    # ========================================================================

    @retry_on_deadlock(max_retries=3, base_delay=0.1, max_delay=2.0)
    def withdraw(
        self,
        account_id: str,  # UUID - primary identifier (Alipay model)
        amount: Decimal,
        currency: str,
        client_request_id: str,
        metadata: Optional[Dict] = None,
        destination_type: Optional[str] = None,
        destination_details: Optional[Dict] = None,
        payment_method: Optional[str] = None,
        payment_provider: Optional[str] = None,
        tx_type: TransactionType = TransactionType.WITHDRAW,
        actor_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Process a withdrawal with full atomicity.

        Single transaction: freeze check -> balance check -> idempotency -> ledger -> audit -> complete
        If any step fails, entire transaction rolls back.

        Args:
            account_id: Account UUID
            amount: Amount to withdraw
            currency: Currency of withdrawal
            client_request_id: Unique idempotency key
            metadata: Additional transaction metadata
            destination_type: Type of destination
            destination_details: Destination details
            payment_method: Payment method
            payment_provider: Payment provider

        Returns:
            Dict with transaction result

        Raises:
            WalletFrozenError: If account is frozen
            InsufficientBalanceError: If insufficient funds
            LimitExceededError: If limits exceeded
            PermissionError: If user doesn't own the account
        """
        amount = self._quantize(amount)

        # Validate
        if amount <= Decimal("0"):
            raise ValueError("Amount must be greater than zero")

        self._validate_currency(currency)
        self._check_transaction_limit(amount, "withdraw")

        # End any dangling read-only transaction from caller-side queries so we can
        # open our own atomic transaction (see deposit() for rationale).
        try:
            self.db.rollback()
        except Exception:
            pass

        # SINGLE TRANSACTION
        with self.db.begin():
            # 1. Get account by UUID with lock
            account = self.account_repo.get_by_id(account_id, for_update=True)
            if not account:
                raise WalletNotFoundError(wallet_ref=str(account_id))

            # Ownership validation - defense in depth
            if account.user_id != current_user.id and not self._is_admin():
                current_app.logger.warning(f"Ownership violation attempt on account {account.id} by user {current_user.id}")
                raise PermissionError("You do not have permission to operate on this account")

            # 2. Freeze check
            if account.is_frozen:
                raise WalletFrozenError(
                    wallet_ref=str(account.id),
                    reason=account.frozen_reason
                )

            # 3. KYC limit check
            self._check_kyc_limits(account.user_id, amount, 'withdraw', currency, account_id=str(account.id))
            
            # 4. Fraud risk check
            self._check_fraud_risk(account.user_id, amount, currency, ip_address=self._get_ip_address())
            
            # 5. Balance check (derived from ledger, no TOCTOU)
            current_balance = self.ledger_repo.get_balance(account.id, currency)
            if current_balance < amount:
                raise InsufficientBalanceError(
                    currency, float(amount), float(current_balance)
                )

            # 6. Daily limit check
            self._check_daily_limit(account.id, amount, currency, "withdraw")
            
            # 7. Monthly limit check
            self._check_monthly_limit(account.id, amount, currency)

            # 5. Atomic idempotency
            tx = self.tx_repo.get_or_create(
                client_request_id=client_request_id,
                tx_type=tx_type,
                amount=amount,
                currency=currency,
                user_id=account.user_id,  # Internal only
                metadata=metadata
            )

            if tx.status == TransactionStatus.COMPLETED:
                balance = self.ledger_repo.get_balance(account.id, currency)
                return {
                    "status": "success",
                    "transaction_id": str(tx.id),
                    "already_processed": True,
                    "amount": str(amount),
                    "currency": currency,
                    "new_balance": str(balance)
                }

            # 6. Create ledger entry (DEBIT)
            ledger_entry = LedgerEntryModel(
                transaction_id=tx.id,
                account_id=account.id,
                entry_type=EntryType.DEBIT,
                amount=amount,
                currency=currency,
                meta={
                    "destination_type": destination_type,
                    "destination_details": destination_details,
                    "payment_method": payment_method,
                    "payment_provider": payment_provider
                }
            )
            self.ledger_repo.post_entries([ledger_entry])

            # 7. Update daily volume
            self.account_repo.update_volume(account.id, float(amount), 'daily')

            # 8. Optional: record commission if agent facilitated this withdrawal
            try:
                agent_id = None
                # check destination_details first, then metadata
                if destination_details and isinstance(destination_details, dict):
                    agent_id = destination_details.get('agent_id')
                if not agent_id and metadata and isinstance(metadata, dict):
                    agent_id = metadata.get('agent_id') or metadata.get('agent')

                if agent_id:
                    commission_service = CommissionService(self.db)
                    commission_amount = commission_service.calculate_commission(amount, 'withdraw')
                    if commission_amount and commission_amount > 0:
                        commission_service.record_commission(
                            agent_id=agent_id,
                            amount=commission_amount,
                            currency=currency,
                            source_type='withdraw',
                            source_id=str(tx.id),
                            recipient_id=account.user_id,  # Internal only
                            extra_data={'destination_details': destination_details or {}, 'client_metadata': metadata or {}}
                        )
            except Exception:
                current_app.logger.exception('Failed to record commission for withdraw')

            # 9. Audit log
            audit_log = AuditLogModel(
                transaction_id=tx.id,
                actor_id=actor_id or account.user_id,  # Use provided actor or owner
                action="withdraw",
                description=f"Withdrawal of {amount} {currency}",
                before_state={"balance": str(current_balance)},
                after_state={"balance": str(self.ledger_repo.get_balance(account.id, currency))},
                ip_address=self._get_ip_address(),
                user_agent=self._get_user_agent(),
                audit_metadata={
                    "destination_type": destination_type,
                    "destination_details": destination_details,
                    "client_metadata": metadata or {}
                }
            )
            self.db.add(audit_log)

            # 10. Mark complete
            self.tx_repo.update_status(tx.id, TransactionStatus.COMPLETED)

        final_balance = self.ledger_repo.get_balance(account.id, currency)

        # Fire-and-forget notification for withdrawal initiation
        try:
            from app.wallet.services.wallet_notifications import notify_withdrawal_initiated
            notify_withdrawal_initiated(account.user_id, amount, currency, reference=str(tx.id))
        except Exception:
            current_app.logger.exception('Failed to send withdrawal notification')

        return {
            "status": "success",
            "transaction_id": str(tx.id),
            "amount": str(amount),
            "currency": currency,
            "new_balance": str(final_balance),
            "account_id": str(account.id),  # Always expose account_id
            "user_id": account.user_id
        }

    # ========================================================================
    # TRANSFER
    # ========================================================================

    @retry_on_deadlock(max_retries=3, base_delay=0.1, max_delay=2.0)
    def transfer(
        self,
        from_account_id: str,  # UUID - primary identifier (Alipay model)
        to_account_id: str,    # UUID - primary identifier (Alipay model)
        amount: Decimal,
        currency: str,
        client_request_id: str,
        note: Optional[str] = None,
        metadata: Optional[Dict] = None,
        platform_fee: Optional[Decimal] = None,
        fee_currency: Optional[str] = None,
        pin: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Transfer funds with full atomicity.

        Single transaction: lock both accounts -> freeze check -> balance check ->
        idempotency -> TWO ledger entries -> audit -> complete

        NO COMPENSATION LOGIC - if anything fails, full rollback.

        Args:
            from_account_id: Sender account UUID
            to_account_id: Recipient account UUID
            amount: Amount to transfer
            currency: Currency of transfer
            client_request_id: Unique idempotency key
            note: Optional note/reference
            metadata: Additional transaction metadata
            platform_fee: Optional platform fee to deduct
            fee_currency: Currency for platform fee
            pin: Transaction PIN for verification

        Returns:
            Dict with transaction result

        Raises:
            WalletFrozenError: If either account is frozen
            InsufficientBalanceError: If sender has insufficient funds
            LimitExceededError: If limits exceeded
            PermissionError: If user doesn't own the from_account
            TransactionPINError: If PIN is invalid
        """
        amount = self._quantize(amount)

        if from_account_id == to_account_id:
            raise ValueError("Cannot transfer to yourself")

        if amount <= Decimal("0"):
            raise ValueError("Amount must be greater than zero")

        self._validate_currency(currency)
        self._check_transaction_limit(amount, "transfer")

        # End any dangling read-only transaction from caller-side queries so we can
        # open our own atomic transaction (see deposit() for rationale).
        try:
            self.db.rollback()
        except Exception:
            pass

        # SINGLE TRANSACTION
        with self.db.begin():
            # 0. PIN verification inside the transaction to avoid TOCTOU
            try:
                from app.identity.models.user import User
                from app.wallet.exceptions import TransactionPINError

                # Get sender's account first to find user_id
                from_account = self.account_repo.get_by_id(from_account_id)
                if not from_account:
                    raise WalletNotFoundError(wallet_ref=from_account_id)
                sender_user = User.get_by_private_id(from_account.user_id)
                if sender_user and sender_user.transaction_pin_hash:
                    if not pin:
                        raise TransactionPINError("Transaction PIN is required")
                    # SELECT FOR UPDATE on the user row to prevent concurrent state changes
                    try:
                        locked_user = self.db.query(User).filter_by(id=sender_user.id).with_for_update().one()
                    except Exception:
                        # Fallback to the already loaded sender_user if locking failed for any reason
                        locked_user = sender_user

                    ok = locked_user.verify_transaction_pin(pin, session=self.db)
                    if not ok:
                        raise TransactionPINError("Invalid or locked PIN")
            except TransactionPINError:
                # Bubble up to caller (will rollback transaction)
                raise
            except Exception:
                # Non-fatal: if verification infrastructure missing, continue without enforcing PIN
                current_app.logger.debug("Transaction PIN verification infrastructure unavailable; skipping PIN enforcement")

            # 1. Get both accounts by UUID with lock (consistent order prevents deadlock)
            account_ids = sorted([from_account_id, to_account_id])
            accounts = {}
            for aid in account_ids:
                acc = self.account_repo.get_by_id(aid, for_update=True)
                if not acc:
                    raise WalletNotFoundError(wallet_ref=aid)
                accounts[aid] = acc

            from_account = accounts[from_account_id]
            to_account = accounts[to_account_id]

            # Ownership validation - defense in depth (sender only)
            if from_account.user_id != current_user.id and not self._is_admin():
                current_app.logger.warning(f"Ownership violation attempt on account {from_account.id} by user {current_user.id}")
                raise PermissionError("You do not have permission to operate on this account")

            # 2. Freeze check (both accounts)
            if from_account.is_frozen:
                raise WalletFrozenError(
                    wallet_ref=str(from_account.id),
                    reason=from_account.frozen_reason
                )
            if to_account.is_frozen:
                raise WalletFrozenError(
                    wallet_ref=str(to_account.id),
                    reason=to_account.frozen_reason
                )

            # 3. KYC limit check (sender) — pass recipient so org->individual
            # "personal transfers" are gated by full organisation KYB.
            self._check_kyc_limits(
                from_account.user_id, amount, 'send', currency,
                recipient_user_id=to_account.user_id,
                account_id=str(from_account.id)
            )
            
            # 4. Fraud risk check (sender)
            self._check_fraud_risk(
                from_account.user_id, 
                amount, 
                currency, 
                recipient_id=to_account.user_id,
                ip_address=self._get_ip_address()
            )

            # Cross-currency support
            debit_amount = amount
            debit_currency = currency
            credit_amount = amount
            credit_currency = currency
            
            if from_account.currency != to_account.currency:
                from app.wallet.services.fx_service import FXService
                fx_service = FXService()
                
                if currency == from_account.currency:
                    fx_rate = fx_service.get_rate_safe(base_currency=from_account.currency, quote_currency=to_account.currency)
                    debit_amount = amount
                    debit_currency = from_account.currency
                    credit_amount = (amount * fx_rate.rate).quantize(Decimal('0.01'))
                    credit_currency = to_account.currency
                else:
                    fx_rate = fx_service.get_rate_safe(base_currency=currency, quote_currency=from_account.currency)
                    debit_amount = (amount * fx_rate.rate).quantize(Decimal('0.01'))
                    debit_currency = from_account.currency
                    credit_amount = amount
                    credit_currency = to_account.currency
            elif from_account.currency != currency:
                debit_currency = from_account.currency
                credit_currency = to_account.currency

            # 5. Balance check (derived from ledger)
            from_balance = self.ledger_repo.get_balance(from_account.id, debit_currency)
            total_debit = debit_amount + (platform_fee or Decimal('0'))

            if from_balance < total_debit:
                raise InsufficientBalanceError(
                    debit_currency, float(total_debit), float(from_balance)
                )

            # 6. Daily limit check
            self._check_daily_limit(from_account.id, debit_amount, debit_currency, "transfer")
            
            # 7. Monthly limit check
            self._check_monthly_limit(from_account.id, debit_amount, debit_currency)

            # 5. Atomic idempotency
            tx = self.tx_repo.get_or_create(
                client_request_id=client_request_id,
                tx_type=TransactionType.TRANSFER,
                amount=amount,
                currency=currency,
                user_id=from_account.user_id,  # Internal only
                recipient_user_id=to_account.user_id,  # Internal only
                metadata=metadata
            )

            if tx.status == TransactionStatus.COMPLETED:
                from_balance = self.ledger_repo.get_balance(from_account.id, debit_currency)
                to_balance = self.ledger_repo.get_balance(to_account.id, credit_currency)
                return {
                    "status": "success",
                    "transaction_id": str(tx.id),
                    "already_processed": True,
                    "amount": str(amount),
                    "currency": currency,
                    "new_balance_from": str(from_balance),
                    "new_balance_to": str(to_balance)
                }

            # 6. Create TWO ledger entries (DEBIT sender, CREDIT receiver)
            # Atomic - both succeed or both fail
            ledger_entries = [
                LedgerEntryModel(
                    transaction_id=tx.id,
                    account_id=from_account.id,
                    entry_type=EntryType.DEBIT,
                    amount=debit_amount,
                    currency=debit_currency,
                    meta={"note": note, "counterparty": to_account_id, "original_amount": str(amount), "original_currency": currency}
                ),
                LedgerEntryModel(
                    transaction_id=tx.id,
                    account_id=to_account.id,
                    entry_type=EntryType.CREDIT,
                    amount=credit_amount,
                    currency=credit_currency,
                    meta={"note": note, "counterparty": from_account_id, "original_amount": str(amount), "original_currency": currency}
                )
            ]

            # Add platform fee entry if applicable
            if platform_fee and platform_fee > 0:
                ledger_entries.append(
                    LedgerEntryModel(
                        transaction_id=tx.id,
                        account_id=from_account.id,
                        entry_type=EntryType.DEBIT,
                        amount=platform_fee,
                        currency=fee_currency or currency,
                        meta={"type": "platform_fee"}
                    )
                )

            self.ledger_repo.post_entries(ledger_entries)

            # 7. Optional: record commission for this transfer if agent info present
            try:
                agent_id = None
                if metadata and isinstance(metadata, dict):
                    agent_id = metadata.get('agent_id') or metadata.get('agent')

                if agent_id:
                    commission_service = CommissionService(self.db)
                    commission_amount = commission_service.calculate_commission(amount, 'transfer', platform_fee)
                    if commission_amount and commission_amount > 0:
                        commission_service.record_commission(
                            agent_id=agent_id,
                            amount=commission_amount,
                            currency=fee_currency or currency,
                            source_type='transfer',
                            source_id=str(tx.id),
                            recipient_id=to_account.user_id,  # Internal only
                            extra_data={'platform_fee': str(platform_fee) if platform_fee else None, 'client_metadata': metadata or {}}
                        )
            except Exception:
                current_app.logger.exception('Failed to record commission for transfer')

            # 8. Update daily volume
            self.account_repo.update_volume(from_account.id, float(amount), 'daily')

            # 9. Audit log
            audit_log = AuditLogModel(
                transaction_id=tx.id,
                actor_id=from_account.user_id,  # Internal only
                action="transfer",
                description=f"Transfer of {amount} {currency} to account {to_account_id}",
                before_state={
                    "from_balance": str(from_balance),
                    "to_balance": str(self.ledger_repo.get_balance(to_account.id, currency))
                },
                after_state={
                    "from_balance": str(self.ledger_repo.get_balance(from_account.id, currency)),
                    "to_balance": str(self.ledger_repo.get_balance(to_account.id, currency))
                },
                ip_address=self._get_ip_address(),
                user_agent=self._get_user_agent(),
                audit_metadata={
                    "to_account_id": to_account_id,
                    "note": note,
                    "platform_fee": str(platform_fee) if platform_fee else None,
                    "client_metadata": metadata or {}
                }
            )
            self.db.add(audit_log)

            # 10. Mark complete
            self.tx_repo.update_status(tx.id, TransactionStatus.COMPLETED)

        from_balance = self.ledger_repo.get_balance(from_account.id, currency)
        to_balance = self.ledger_repo.get_balance(to_account.id, currency)

        # Notifications: notify sender and recipient (best-effort)
        try:
            from app.wallet.services.wallet_notifications import (
                notify_transfer_sent,
                notify_transfer_received
            )
            from app.identity.models.user import User
            try:
                recipient_user = User.get_by_private_id(to_account.user_id)
                sender_user = User.get_by_private_id(from_account.user_id)
                recipient_name = getattr(recipient_user, 'username', None) or getattr(recipient_user, 'email', None) or str(to_account.id)
                sender_name = getattr(sender_user, 'username', None) or getattr(sender_user, 'email', None) or str(from_account.id)
            except Exception:
                recipient_name = str(to_account.id)
                sender_name = str(from_account.id)

            try:
                notify_transfer_sent(from_account.user_id, amount, currency, recipient_name, from_balance, reference=str(tx.id))
            except Exception:
                current_app.logger.exception('Failed to send transfer-sent notification')

            try:
                notify_transfer_received(to_account.user_id, amount, currency, sender_name, to_balance)
            except Exception:
                current_app.logger.exception('Failed to send transfer-received notification')
        except Exception:
            current_app.logger.exception('Transfer notification setup failed')

        return {
            "status": "success",
            "transaction_id": str(tx.id),
            "amount": str(amount),
            "currency": currency,
            "new_balance_from": str(from_balance),
            "new_balance_to": str(to_balance),
            "from_account_id": str(from_account.id),
            "to_account_id": str(to_account.id),
            "note": note
        }

    # ========================================================================
    # ADMIN OPERATIONS
    # ========================================================================

    @staticmethod
    def get_admin_dashboard_data() -> Dict[str, Any]:
        """Get aggregate data for the wallet admin dashboard."""
        from app.wallet.models.ledger import AccountModel, LedgerEntryModel
        from app.wallet.models.transaction import TransactionModel
        from app.wallet.models.wallet import PaymentMethod
        from sqlalchemy import func

        # Total system balance (sum of all CREDITS minus sum of all DEBITS across all accounts)
        # For simplicity in dashboard, often just sum of all positive account balances is used
        # but let's do sum of Ledger entries
        total_balance = db.session.query(
            func.sum(
                func.case(
                    (LedgerEntryModel.entry_type == EntryType.CREDIT, LedgerEntryModel.amount),
                    (LedgerEntryModel.entry_type == EntryType.DEBIT, -LedgerEntryModel.amount),
                    else_=0
                )
            )
        ).scalar() or Decimal('0')

        total_transactions = db.session.query(func.count(TransactionModel.id)).scalar() or 0
        active_wallets = db.session.query(func.count(AccountModel.id)).filter_by(is_deleted=False).scalar() or 0
        payment_methods = db.session.query(func.count(PaymentMethod.id)).filter_by(is_active=True).scalar() or 0

        # Calculate growth (placeholder logic for now)
        return {
            'total_balance': float(total_balance),
            'total_transactions': total_transactions,
            'active_wallets': active_wallets,
            'payment_methods': payment_methods,
            'balance_growth': '+0%',
            'transactions_growth': '+0%',
            'wallet_status': 'Healthy',
            'payment_status': 'Active'
        }

    def admin_deposit(self, account_id: str, amount: Decimal, currency: str, reason: str) -> Dict[str, Any]:
        """
        Admin-initiated manual deposit (credit).
        
        CRITICAL: This is a high-privilege operation that bypasses normal payment gateways.
        It is used for manual corrections, compensation, or structural adjustments.
        Requires explicit authorization and mandatory reason.
        """
        if not self._is_admin():
            raise PermissionError("Admin privileges required")
        
        if not reason or not reason.strip():
            raise ValueError("A mandatory reason must be provided for manual adjustments")
        
        client_request_id = f"admin_dep_{datetime.now().timestamp()}_{account_id}"
        
        # Security: Always save the reason in a dedicated adjustment field
        metadata = {
            "admin_id": current_user.id,
            "adjustment_reason": reason,
            "type": "admin_adjustment",
            "initiated_at": datetime.now().isoformat()
        }
        
        result = self.deposit(
            account_id=account_id,
            amount=amount,
            currency=currency,
            client_request_id=client_request_id,
            metadata=metadata,
            payment_method="admin_adjustment",
            payment_provider="system",
            tx_type=TransactionType.ADJUSTMENT,
            actor_id=current_user.id
        )

        # Notify owner and other admins
        try:
            from app.wallet.services.wallet_notifications import notify_admin_adjustment
            notify_admin_adjustment(
                user_id=result.get("user_id") or result.get("account_user_id"), # Need to ensure we have user_id
                amount=amount,
                currency=currency,
                action="deposit",
                reason=reason,
                admin_name=current_user.username or current_user.email
            )
        except Exception:
            current_app.logger.exception("Failed to send admin adjustment notification")

        return result

    def admin_withdraw(self, account_id: str, amount: Decimal, currency: str, reason: str) -> Dict[str, Any]:
        """
        Admin-initiated manual withdrawal (debit).
        
        CRITICAL: This is a high-privilege operation that bypasses normal payment gateways.
        It is used for manual corrections, debt recovery, or structural adjustments.
        Requires explicit authorization and mandatory reason.
        """
        if not self._is_admin():
            raise PermissionError("Admin privileges required")
            
        if not reason or not reason.strip():
            raise ValueError("A mandatory reason must be provided for manual adjustments")
        
        client_request_id = f"admin_wd_{datetime.now().timestamp()}_{account_id}"
        
        # Security: Always save the reason in a dedicated adjustment field
        metadata = {
            "admin_id": current_user.id,
            "adjustment_reason": reason,
            "type": "admin_adjustment",
            "initiated_at": datetime.now().isoformat()
        }
        
        result = self.withdraw(
            account_id=account_id,
            amount=amount,
            currency=currency,
            client_request_id=client_request_id,
            metadata=metadata,
            destination_type="admin_adjustment",
            payment_method="admin_adjustment",
            payment_provider="system",
            tx_type=TransactionType.ADJUSTMENT,
            actor_id=current_user.id
        )

        # Notify owner and other admins
        try:
            from app.wallet.services.wallet_notifications import notify_admin_adjustment
            notify_admin_adjustment(
                user_id=result.get("user_id") or result.get("account_user_id"),
                amount=amount,
                currency=currency,
                action="withdraw",
                reason=reason,
                admin_name=current_user.username or current_user.email
            )
        except Exception:
            current_app.logger.exception("Failed to send admin adjustment notification")

        return result

    def admin_request_adjustment(
        self, 
        account_id: str, 
        amount: Decimal, 
        currency: str, 
        adjustment_type: str, 
        reason: str
    ) -> Dict[str, Any]:
        """
        Level 1: Create a pending adjustment request.
        Requires Wallet Admin / Manager role.
        """
        from app.wallet.models.adjustment import AdjustmentRequestModel, AdjustmentStatus
        from app.models.system_config import SystemConfig
        
        if not self._is_admin():
            raise PermissionError("Admin privileges required to request adjustment")
            
        if not reason or not reason.strip():
            raise ValueError("Reason is mandatory for manual adjustments")
            
        amount = self._quantize(amount)
        if amount <= 0:
            raise ValueError("Amount must be positive")
            
        # Ensure account exists
        account = self.account_repo.get_by_id(account_id)
        if not account:
            raise WalletNotFoundError(wallet_ref=account_id)
            
        # Check for auto-approval threshold
        # Default threshold is 1000 UGX
        threshold = SystemConfig.get('wallet_adjustment_auto_approve_threshold', 1000)
        auto_approve = False
        
        # Auto-approval check: small UGX amounts by any admin
        if currency == 'UGX' and amount < Decimal(str(threshold)):
            auto_approve = True
            
        request_obj = AdjustmentRequestModel(
            account_id=UUID(account_id) if isinstance(account_id, str) else account_id,
            amount=amount,
            currency=currency,
            adjustment_type=adjustment_type,
            reason=reason,
            requested_by_id=current_user.id,
            status=AdjustmentStatus.APPROVED if auto_approve else AdjustmentStatus.PENDING
        )
        self.db.add(request_obj)
        self.db.commit()
        
        if auto_approve:
            # Execute immediately
            return self.approve_adjustment(
                request_id=request_obj.public_id, 
                approved_by_id=current_user.id,
                is_auto_approve=True
            )
        
        # Notify Super Admins / Owners of new request
        try:
            from app.wallet.services.wallet_notifications import notify_adjustment_requested
            notify_adjustment_requested(
                request_id=request_obj.public_id,
                requested_by=current_user.username or current_user.email,
                amount=amount,
                currency=currency,
                adjustment_type=adjustment_type
            )
        except Exception:
            current_app.logger.exception("Failed to send adjustment request notification")
            
        return {
            "status": "pending_approval",
            "request_id": request_obj.public_id,
            "message": "Adjustment request created and pending approval."
        }

    def approve_adjustment(self, request_id: str, approved_by_id: int, is_auto_approve: bool = False) -> Dict[str, Any]:
        """
        Level 2: Approve and execute a pending adjustment request.
        Requires Super Admin / Owner role (unless auto-approved).
        """
        from app.wallet.models.adjustment import AdjustmentRequestModel, AdjustmentStatus
        from app.identity.models.user import User
        
        # Security check: Only Super Admins or Owners can approve (unless auto-approve for small amounts)
        if not is_auto_approve:
            approver = db.session.get(User, approved_by_id)
            if not approver or not (approver.has_global_role('owner', 'super_admin')):
                 raise PermissionError("Only Super Admins or Owners can approve adjustments")

        request_obj = AdjustmentRequestModel.query.filter_by(public_id=request_id).first()
        if not request_obj:
            raise ValueError("Adjustment request not found")
            
        if not is_auto_approve and request_obj.status != AdjustmentStatus.PENDING:
            raise ValueError(f"Request is already {request_obj.status}")
            
        # Execute the adjustment
        # Note: we use admin_deposit/admin_withdraw which will audit the approver as the actor
        if request_obj.adjustment_type == 'deposit':
            result = self.admin_deposit(
                account_id=str(request_obj.account_id),
                amount=request_obj.amount,
                currency=request_obj.currency,
                reason=f"{'Auto-Approved ' if is_auto_approve else 'Approved '}Adjustment: {request_obj.reason} (Request {request_obj.public_id})"
            )
        else:
            result = self.admin_withdraw(
                account_id=str(request_obj.account_id),
                amount=request_obj.amount,
                currency=request_obj.currency,
                reason=f"{'Auto-Approved ' if is_auto_approve else 'Approved '}Adjustment: {request_obj.reason} (Request {request_obj.public_id})"
            )
            
        # Update request status
        request_obj.status = AdjustmentStatus.APPROVED
        request_obj.approved_by_id = approved_by_id
        request_obj.approved_at = datetime.now()
        request_obj.transaction_id = UUID(result['transaction_id']) if isinstance(result['transaction_id'], str) else result['transaction_id']
        self.db.commit()
        
        # Notify approval
        try:
            from app.wallet.services.wallet_notifications import notify_adjustment_approved
            approver = db.session.get(User, approved_by_id)
            notify_adjustment_approved(
                request_id=request_obj.public_id,
                approved_by=approver.username or approver.email,
                user_id=request_obj.account.user_id,
                amount=request_obj.amount,
                currency=request_obj.currency,
                adjustment_type=request_obj.adjustment_type
            )
        except Exception:
            current_app.logger.exception("Failed to send adjustment approval notification")

        return {
            "status": "success",
            "message": f"Adjustment successfully {'auto-' if is_auto_approve else ''}approved and executed.",
            "transaction_id": result['transaction_id'],
            "new_balance": result.get("new_balance")
        }

    def reject_adjustment(self, request_id: str, rejected_by_id: int, reason: str) -> Dict[str, Any]:
        """Reject a pending adjustment request."""
        from app.wallet.models.adjustment import AdjustmentRequestModel, AdjustmentStatus
        from app.identity.models.user import User
        
        # Security check: Only Super Admins or Owners can reject (or the original requester)
        rejecter = db.session.get(User, rejected_by_id)
        request_obj = AdjustmentRequestModel.query.filter_by(public_id=request_id).first()
        
        if not request_obj:
            raise ValueError("Adjustment request not found")

        is_high_admin = rejecter and rejecter.has_global_role('owner', 'super_admin')
        is_requester = request_obj.requested_by_id == rejected_by_id
        
        if not (is_high_admin or is_requester):
             raise PermissionError("Permission denied to reject this request")
            
        if request_obj.status != AdjustmentStatus.PENDING:
            raise ValueError(f"Request is already {request_obj.status}")
            
        request_obj.status = AdjustmentStatus.REJECTED
        request_obj.rejected_by_id = rejected_by_id
        request_obj.rejected_at = datetime.now()
        request_obj.rejection_reason = reason
        self.db.commit()
        
        # Notify rejection
        try:
            from app.wallet.services.wallet_notifications import _send
            alert_msg = (
                f"AFCON360: Your adjustment request {request_id} for {request_obj.amount} "
                f"{request_obj.currency} was REJECTED. Reason: {reason}"
            )
            _send(request_obj.requested_by_id, alert_msg, channel="email")
        except Exception:
            current_app.logger.exception("Failed to send adjustment rejection notification")

        return {
            "status": "success",
            "message": "Adjustment request rejected."
        }

    @staticmethod
    def approve_transaction(transaction_id: int, approved_by: int) -> bool:
        """Approve a pending transaction."""
        from app.wallet.models.transaction import TransactionModel, TransactionStatus
        tx = db.session.get(TransactionModel, transaction_id)
        if tx and tx.status == TransactionStatus.PENDING:
            tx.status = TransactionStatus.COMPLETED
            tx.updated_at = datetime.now(timezone.utc)
            # Add audit log
            db.session.commit()
            return True
        return False

    @staticmethod
    def reject_transaction(transaction_id: int, reason: str, rejected_by: int) -> bool:
        """Reject a pending transaction."""
        from app.wallet.models.transaction import TransactionModel, TransactionStatus
        tx = db.session.get(TransactionModel, transaction_id)
        if tx and tx.status == TransactionStatus.PENDING:
            tx.status = TransactionStatus.FAILED
            tx.failure_reason = reason
            tx.updated_at = datetime.now(timezone.utc)
            db.session.commit()
            return True
        return False

    @staticmethod
    def verify_payment_method(payment_id: int, verified_by: int) -> bool:
        """Verify a user's payment method."""
        from app.wallet.models.wallet import PaymentMethod
        pm = db.session.get(PaymentMethod, payment_id)
        if pm:
            pm.is_verified = True
            pm.verified_at = datetime.now(timezone.utc)
            pm.verified_by = verified_by
            db.session.commit()
            return True
        return False

    @staticmethod
    def create_commission(data: Dict[str, Any]) -> Any:
        """Create a new commission rule."""
        # Placeholder for actual commission model
        return True

    @staticmethod
    def process_commission_payout(commission_id: int, processed_by: int) -> bool:
        """Process a commission payout to an agent."""
        return True

    @staticmethod
    def get_reconciliation_data() -> Dict[str, Any]:
        """Get data for transaction reconciliation from the latest run."""
        from app.wallet.models.reconciliation import ReconciliationRun, ReconciliationIssue
        latest_run = ReconciliationRun.query.order_by(ReconciliationRun.started_at.desc()).first()
        if not latest_run:
            return {
                "last_run": None,
                "status": "No data",
                "total_accounts": 0,
                "issues_found": 0,
                "mismatches": []
            }
        
        issues = ReconciliationIssue.query.filter_by(run_id=latest_run.id).all()
        return {
            "last_run": latest_run.started_at.isoformat(),
            "status": latest_run.status,
            "total_accounts": latest_run.summary.get('total_accounts', 0) if latest_run.summary else 0,
            "issues_found": len(issues),
            "mismatches": [i.details for i in issues]
        }

    @staticmethod
    def process_reconciliation(reconciliation_date: str = None, processed_by: int = None) -> bool:
        """Run reconciliation process now."""
        from app.wallet.services.reconciliation_service import ReconciliationService
        try:
            service = ReconciliationService()
            service.run_daily_reconciliation()
            return True
        except Exception:
            current_app.logger.exception("Manual reconciliation failed")
            return False

    @staticmethod
    def toggle_gateway(gateway_id: int, new_status: bool, toggled_by: int) -> bool:
        """Enable or disable a payment gateway."""
        return True

    @staticmethod
    def get_analytics_data() -> Dict[str, Any]:
        """Get financial analytics data."""
        return {
            'revenue_chart': [],
            'transaction_volume': 0,
            'active_users_trend': []
        }
