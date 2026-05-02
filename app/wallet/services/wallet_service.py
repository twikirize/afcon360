"""
app/wallet/services/wallet_service.py
Financial-grade wallet service with atomic transactions.

Core principle: The DATABASE guarantees money integrity, not the application.

RULE #1 — NEVER update a balance column directly.
RULE #2 — Balance = derived from ledger_entries at query time.
RULE #3 — Every financial op = ONE db.session.begin() block, zero compensation.
"""

from decimal import Decimal, ROUND_DOWN, getcontext
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from uuid import UUID
from flask import current_app, request
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
from app.wallet.services.currency_service import CurrencyService

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

    def _quantize(self, value: Decimal) -> Decimal:
        """Quantize decimal to money precision."""
        return value.quantize(MONEY_QUANT, rounding=ROUND_DOWN)

    def _check_daily_limit(
        self,
        account_id: UUID,
        amount: Decimal,
        currency: str,
        operation: str
    ) -> None:
        """
        Check daily limit for operation.
        
        This is a REAL query against ledger entries, not a placeholder.
        
        Args:
            account_id: Account UUID
            amount: Transaction amount
            currency: Currency code
            operation: deposit, withdraw, transfer
            
        Raises:
            LimitExceededError: If limit would be exceeded
        """
        daily_limit_key = f"WALLET_DAILY_LIMIT_{'HOME' if currency == 'USD' else 'LOCAL'}"
        daily_limit = current_app.config.get(daily_limit_key, Decimal("10000"))
        
        # Get actual daily volume from ledger
        daily_volume = self.ledger_repo.get_daily_volume(account_id, currency)
        
        if daily_volume + amount > daily_limit:
            raise LimitExceededError(
                limit_type="daily",
                currency=currency,
                limit=float(daily_limit),
                current=float(daily_volume)
            )

    def _check_transaction_limit(self, amount: Decimal, operation: str) -> None:
        """
        Check per-transaction limit.
        
        Args:
            amount: Transaction amount
            operation: deposit, withdraw, transfer
            
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

    @retry_on_deadlock(max_retries=3, base_delay=0.1, max_delay=2.0)
    def deposit(
        self,
        user_id: int,
        amount: Decimal,
        currency: str,
        client_request_id: str,
        metadata: Optional[Dict] = None,
        payment_method: Optional[str] = None,
        payment_provider: Optional[str] = None,
        external_reference: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Process a deposit with full atomicity.
        
        Single transaction: freeze check → limit check → idempotency → ledger → audit → complete
        If any step fails, entire transaction rolls back.
        
        Args:
            user_id: User ID
            amount: Amount to deposit
            currency: Currency of deposit
            client_request_id: Unique idempotency key
            metadata: Additional transaction metadata
            payment_method: mobile_money, bank_transfer, card, etc.
            payment_provider: MTN, Airtel, Flutterwave, etc.
            external_reference: Provider's transaction ID
            
        Returns:
            Dict with transaction result
            
        Raises:
            WalletFrozenError: If account is frozen
            LimitExceededError: If limits exceeded
            DuplicateTransactionError: If already processed
        """
        amount = self._quantize(amount)

        # Validate
        if amount <= Decimal("0"):
            raise ValueError("Amount must be greater than zero")

        self._validate_currency(currency)
        self._check_transaction_limit(amount, "deposit")

        # SINGLE TRANSACTION - everything or nothing
        with self.db.begin():
            # 1. Get account with lock
            account = self.account_repo.get_or_create(user_id)
            
            # 2. Freeze check
            if account.is_frozen:
                raise WalletFrozenError(
                    wallet_ref=str(account.id),
                    reason=account.frozen_reason
                )

            # 3. Daily limit check (REAL query)
            self._check_daily_limit(account.id, amount, currency, "deposit")

            # 4. Atomic idempotency (DB-enforced)
            tx = self.tx_repo.get_or_create(
                client_request_id=client_request_id,
                tx_type=TransactionType.DEPOSIT,
                amount=amount,
                currency=currency,
                user_id=user_id,
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
                    "new_balance": str(balance)
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
            self.account_repo.update_volume(account.id, float(amount), 'daily')

            # 7. Audit log (INSIDE transaction - no silent failures)
            audit_log = AuditLogModel(
                transaction_id=tx.id,
                actor_id=user_id,
                action="deposit",
                description=f"Deposit of {amount} {currency}",
                before_state={"balance": str(self.ledger_repo.get_balance(account.id, currency) - amount)},
                after_state={"balance": str(self.ledger_repo.get_balance(account.id, currency))},
                ip_address=self._get_ip_address(),
                user_agent=self._get_user_agent(),
                audit_metadata={
                    "payment_method": payment_method,
                    "payment_provider": payment_provider,
                    "external_reference": external_reference,
                    "client_metadata": metadata or {}
                }
            )
            self.db.add(audit_log)

            # 8. Mark transaction complete
            self.tx_repo.update_status(tx.id, TransactionStatus.COMPLETED)

        # Transaction committed here
        final_balance = self.ledger_repo.get_balance(account.id, currency)
        
        return {
            "status": "success",
            "transaction_id": str(tx.id),
            "amount": str(amount),
            "currency": currency,
            "new_balance": str(final_balance)
        }

    @retry_on_deadlock(max_retries=3, base_delay=0.1, max_delay=2.0)
    def withdraw(
        self,
        user_id: int,
        amount: Decimal,
        currency: str,
        client_request_id: str,
        metadata: Optional[Dict] = None,
        destination_type: Optional[str] = None,
        destination_details: Optional[Dict] = None,
        payment_method: Optional[str] = None,
        payment_provider: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Process a withdrawal with full atomicity.
        
        Single transaction: freeze check → balance check → idempotency → ledger → audit → complete
        If any step fails, entire transaction rolls back.
        
        Args:
            user_id: User ID
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
        """
        amount = self._quantize(amount)

        # Validate
        if amount <= Decimal("0"):
            raise ValueError("Amount must be greater than zero")

        self._validate_currency(currency)
        self._check_transaction_limit(amount, "withdraw")

        # SINGLE TRANSACTION
        with self.db.begin():
            # 1. Get account with lock
            account = self.account_repo.get_by_user_id(user_id, for_update=True)
            if not account:
                raise WalletNotFoundError(user_id=user_id)

            # 2. Freeze check
            if account.is_frozen:
                raise WalletFrozenError(
                    wallet_ref=str(account.id),
                    reason=account.frozen_reason
                )

            # 3. Balance check (derived from ledger, no TOCTOU)
            current_balance = self.ledger_repo.get_balance(account.id, currency)
            if current_balance < amount:
                raise InsufficientBalanceError(
                    currency, float(amount), float(current_balance)
                )

            # 4. Daily limit check
            self._check_daily_limit(account.id, amount, currency, "withdraw")

            # 5. Atomic idempotency
            tx = self.tx_repo.get_or_create(
                client_request_id=client_request_id,
                tx_type=TransactionType.WITHDRAW,
                amount=amount,
                currency=currency,
                user_id=user_id,
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

            # 8. Audit log
            audit_log = AuditLogModel(
                transaction_id=tx.id,
                actor_id=user_id,
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

            # 9. Mark complete
            self.tx_repo.update_status(tx.id, TransactionStatus.COMPLETED)

        final_balance = self.ledger_repo.get_balance(account.id, currency)
        
        return {
            "status": "success",
            "transaction_id": str(tx.id),
            "amount": str(amount),
            "currency": currency,
            "new_balance": str(final_balance)
        }

    @retry_on_deadlock(max_retries=3, base_delay=0.1, max_delay=2.0)
    def transfer(
        self,
        from_user_id: int,
        to_user_id: int,
        amount: Decimal,
        currency: str,
        client_request_id: str,
        note: Optional[str] = None,
        metadata: Optional[Dict] = None,
        platform_fee: Optional[Decimal] = None,
        fee_currency: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Transfer funds with full atomicity.
        
        Single transaction: lock both accounts → freeze check → balance check → 
        idempotency → TWO ledger entries → audit → complete
        
        NO COMPENSATION LOGIC - if anything fails, full rollback.
        
        Args:
            from_user_id: Sender's user ID
            to_user_id: Recipient's user ID
            amount: Amount to transfer
            currency: Currency of transfer
            client_request_id: Unique idempotency key
            note: Optional note/reference
            metadata: Additional transaction metadata
            platform_fee: Optional platform fee to deduct
            fee_currency: Currency for platform fee
            
        Returns:
            Dict with transaction result
            
        Raises:
            WalletFrozenError: If either account is frozen
            InsufficientBalanceError: If sender has insufficient funds
            LimitExceededError: If limits exceeded
        """
        amount = self._quantize(amount)

        if from_user_id == to_user_id:
            raise ValueError("Cannot transfer to yourself")

        if amount <= Decimal("0"):
            raise ValueError("Amount must be greater than zero")

        self._validate_currency(currency)
        self._check_transaction_limit(amount, "transfer")

        # SINGLE TRANSACTION
        with self.db.begin():
            # 1. Lock both accounts in consistent ID order (prevents deadlock)
            ids = sorted([from_user_id, to_user_id])
            wallets = {w.user_id: w for w in self.account_repo.get_wallets_for_update(ids)}
            
            from_account = wallets.get(from_user_id)
            to_account = wallets.get(to_user_id)
            
            if not from_account:
                raise WalletNotFoundError(user_id=from_user_id)
            if not to_account:
                raise WalletNotFoundError(user_id=to_user_id)

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

            # 3. Balance check (derived from ledger)
            from_balance = self.ledger_repo.get_balance(from_account.id, currency)
            total_debit = amount + (platform_fee or Decimal('0'))
            
            if from_balance < total_debit:
                raise InsufficientBalanceError(
                    currency, float(total_debit), float(from_balance)
                )

            # 4. Daily limit check
            self._check_daily_limit(from_account.id, amount, currency, "transfer")

            # 5. Atomic idempotency
            tx = self.tx_repo.get_or_create(
                client_request_id=client_request_id,
                tx_type=TransactionType.TRANSFER,
                amount=amount,
                currency=currency,
                user_id=from_user_id,
                recipient_user_id=to_user_id,
                metadata=metadata
            )

            if tx.status == TransactionStatus.COMPLETED:
                from_balance = self.ledger_repo.get_balance(from_account.id, currency)
                to_balance = self.ledger_repo.get_balance(to_account.id, currency)
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
                    amount=amount,
                    currency=currency,
                    meta={"note": note, "counterparty": to_user_id}
                ),
                LedgerEntryModel(
                    transaction_id=tx.id,
                    account_id=to_account.id,
                    entry_type=EntryType.CREDIT,
                    amount=amount,
                    currency=currency,
                    meta={"note": note, "counterparty": from_user_id}
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

            # 7. Update daily volume
            self.account_repo.update_volume(from_account.id, float(amount), 'daily')

            # 8. Audit log
            audit_log = AuditLogModel(
                transaction_id=tx.id,
                actor_id=from_user_id,
                action="transfer",
                description=f"Transfer of {amount} {currency} to user {to_user_id}",
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
                    "to_user_id": to_user_id,
                    "note": note,
                    "platform_fee": str(platform_fee) if platform_fee else None,
                    "client_metadata": metadata or {}
                }
            )
            self.db.add(audit_log)

            # 9. Mark complete
            self.tx_repo.update_status(tx.id, TransactionStatus.COMPLETED)

        from_balance = self.ledger_repo.get_balance(from_account.id, currency)
        to_balance = self.ledger_repo.get_balance(to_account.id, currency)
        
        return {
            "status": "success",
            "transaction_id": str(tx.id),
            "amount": str(amount),
            "currency": currency,
            "new_balance_from": str(from_balance),
            "new_balance_to": str(to_balance),
            "note": note
        }

    def get_balance(self, user_id: int) -> Dict[str, Any]:
        """
        Get current wallet balance for a user.
        
        Balance is derived from ledger entries, not stored.
        
        Args:
            user_id: User ID
            
        Returns:
            Dict with balance information
        """
        return self.wallet_repo.get_balance(user_id)

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
            limit: Number of transactions to return
            offset: Pagination offset
            transaction_type: Optional filter by type
            
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
