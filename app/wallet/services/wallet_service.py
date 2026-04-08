"""
app/wallet/services/wallet_service.py
UNIFIED WALLET SERVICE - Single source of truth for all wallet operations.

This replaces the old wallet.py but works alongside it during migration.
"""

from decimal import Decimal, ROUND_DOWN, getcontext
from datetime import datetime
from typing import Optional, Dict, Any, Tuple
import uuid
from flask import current_app
from sqlalchemy.exc import OperationalError

from app.extensions import db
from app.wallet.repositories.wallet_repository import WalletRepository
from app.wallet.repositories.transaction_repository import TransactionRepository
from app.wallet.services.currency_service import CurrencyService
from app.wallet.exceptions import (
    InsufficientBalanceError,
    UnsupportedCurrencyError,
    WalletNotFoundError,
    LimitExceededError,
    DuplicateTransactionError,
    ComplianceBlockError
)

# Money precision
getcontext().prec = 28
MONEY_QUANT = Decimal("0.01")


class WalletService:
    """
    Unified wallet service - single source of truth for all wallet operations.

    Features:
    - Atomic balance updates with optimistic locking
    - Idempotency via client_request_id
    - Daily/monthly limit checking
    - Currency conversion
    - Audit trail via transaction records
    - Deadlock retry logic
    """

    def __init__(self, db_session=None):
        self.db = db_session or db.session
        self.wallet_repo = WalletRepository(self.db)
        self.tx_repo = TransactionRepository(self.db)
        self.currency_service = CurrencyService()

    def _quantize(self, value: Decimal) -> Decimal:
        """Quantize decimal to money precision."""
        return value.quantize(MONEY_QUANT, rounding=ROUND_DOWN)

    def _generate_tx_id(self) -> str:
        """Generate unique transaction ID."""
        return f"tx_{uuid.uuid4().hex}"

    def _check_daily_limit(
            self,
            wallet,
            amount: Decimal,
            currency: str,
            operation: str
    ) -> None:
        """
        Check daily limit for operation.

        Args:
            wallet: Wallet model instance
            amount: Transaction amount
            currency: Currency code
            operation: deposit, withdraw, transfer

        Raises:
            LimitExceededError: If limit would be exceeded
        """
        # Get daily volume from wallet (will be implemented after adding columns)
        # For now, skip check until columns are added
        daily_limit_key = f"WALLET_DAILY_LIMIT_{'HOME' if currency == wallet.home_currency else 'LOCAL'}"
        daily_limit = current_app.config.get(daily_limit_key, Decimal("10000"))

        # TODO: Get actual daily volume from wallet.daily_volume_home/local
        # current_volume = wallet.daily_volume_home if currency == wallet.home_currency else wallet.daily_volume_local

        # Placeholder - always passes
        pass

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

    def _execute_with_retry(self, func, max_retries=3):
        """
        Execute a function with deadlock retry logic.

        Args:
            func: Function to execute (must use db session)
            max_retries: Maximum number of retry attempts

        Returns:
            Result of func

        Raises:
            The original exception after max retries
        """
        retries = 0
        while retries < max_retries:
            try:
                return func()
            except OperationalError as e:
                if "deadlock" in str(e).lower() and retries < max_retries - 1:
                    retries += 1
                    current_app.logger.warning(
                        f"Deadlock detected, retrying ({retries}/{max_retries}): {e}"
                    )
                    self.db.rollback()
                    import time
                    time.sleep(0.1 * (2 ** retries))  # Exponential backoff
                else:
                    raise
        return None

    def get_balance(self, user_id: int) -> Dict[str, Any]:
        """
        Get current wallet balance for a user.

        Args:
            user_id: Internal user ID

        Returns:
            Dict with balance information
        """
        wallet = self.wallet_repo.get_by_user_id(user_id)

        if not wallet:
            return {
                "exists": False,
                "balance_home": "0.00",
                "balance_local": "0.00",
                "home_currency": current_app.config.get("HOME_CURRENCY_DEFAULT", "USD"),
                "local_currency": current_app.config.get("LOCAL_CURRENCY_DEFAULT", "UGX"),
            }

        return {
            "exists": True,
            "wallet_ref": getattr(wallet, 'wallet_ref', None),
            "balance_home": str(self._quantize(wallet.balance_home)),
            "balance_local": str(self._quantize(wallet.balance_local)),
            "home_currency": wallet.home_currency,
            "local_currency": wallet.local_currency,
            "verified": wallet.verified,
            "updated_at": wallet.updated_at.isoformat() if wallet.updated_at else None,
        }

    def deposit(
            self,
            user_id: int,
            amount: Decimal,
            currency: str,
            idempotency_key: Optional[str] = None,
            metadata: Optional[Dict] = None,
            payment_method: Optional[str] = None,
            payment_provider: Optional[str] = None,
            external_reference: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Process a deposit into a user's wallet with full audit trail.

        Args:
            user_id: Internal user ID
            amount: Amount to deposit
            currency: Currency of deposit
            idempotency_key: Unique key to prevent duplicate processing
            metadata: Additional transaction metadata
            payment_method: mobile_money, bank_transfer, card, etc.
            payment_provider: MTN, Airtel, Flutterwave, etc.
            external_reference: Provider's transaction ID

        Returns:
            Dict with transaction result

        Raises:
            DuplicateTransactionError: If idempotency_key already used
            UnsupportedCurrencyError: If currency not supported
            LimitExceededError: If deposit exceeds limits
        """
        from app.audit.comprehensive_audit import AuditService, TransactionType, AuditSeverity
        from flask import request

        amount = self._quantize(amount)
        audit_transaction_id = None

        # Validate
        if amount <= Decimal("0"):
            raise ValueError("Amount must be greater than zero")

        self._validate_currency(currency)
        self._check_transaction_limit(amount, "deposit")

        # Check idempotency
        if idempotency_key:
            existing = self.tx_repo.get_by_client_request_id(idempotency_key)
            if existing:
                raise DuplicateTransactionError(idempotency_key, existing.tx_id or str(existing.id))

        def _do_deposit():
            nonlocal audit_transaction_id

            # Get wallet with row lock and capture balance snapshot
            wallet = self.wallet_repo.get_or_create_by_user_id(user_id)
            original_version = wallet.version

            # Capture balances BEFORE transaction (critical for audit)
            home_balance_before = wallet.balance_home
            local_balance_before = wallet.balance_local

            # Check daily limit
            self._check_daily_limit(wallet, amount, currency, "deposit")

            # Determine which balance to update
            amount_home_delta = Decimal("0")
            amount_local_delta = Decimal("0")
            settled_amount = amount
            settled_currency = currency
            conversion_rate = None
            conversion_fee = Decimal("0")
            tx_detail = "deposit"

            if currency == wallet.home_currency:
                amount_home_delta = amount
                tx_detail = "deposit_home"
            elif currency == wallet.local_currency:
                amount_local_delta = amount
                tx_detail = "deposit_local"
            else:
                # Convert to home currency
                converted_home, rate, fee = self.currency_service.convert(
                    amount, currency, wallet.home_currency, apply_fee=True
                )
                amount_home_delta = converted_home
                conversion_rate = rate
                conversion_fee = fee

                # Also convert to local for tracking
                converted_local, _, _ = self.currency_service.convert(
                    amount, currency, wallet.local_currency, apply_fee=False
                )
                amount_local_delta = converted_local
                tx_detail = "deposit_foreign"
                settled_amount = converted_home
                settled_currency = wallet.home_currency

            # Generate audit transaction ID BEFORE balance change
            import uuid
            audit_transaction_id = f"DEP-{uuid.uuid4().hex[:12].upper()}"

            # Log financial transaction INITIATION (before balance change)
            try:
                AuditService.financial(
                    transaction_id=audit_transaction_id,
                    transaction_type=TransactionType.DEPOSIT,
                    amount=amount,
                    currency=currency,
                    status="pending",
                    to_user_id=user_id,
                    to_balance_before=float(home_balance_before),
                    payment_method=payment_method or metadata.get('payment_method', 'unknown'),
                    payment_provider=payment_provider,
                    external_reference=external_reference,
                    ip_address=request.remote_addr if request else None,
                    user_agent=request.user_agent.string if request else None,
                    metadata={
                        "idempotency_key": idempotency_key,
                        "conversion_rate": str(conversion_rate) if conversion_rate else None,
                        "conversion_fee": str(conversion_fee),
                        "settled_currency": settled_currency,
                        "client_metadata": metadata or {},
                    }
                )
            except Exception as e:
                # Log audit failure but continue - don't block transaction
                current_app.logger.error(f"Failed to create audit record: {e}")

            # Update balance with optimistic lock
            success, updated_wallet = self.wallet_repo.update_balance(
                wallet.id,
                amount_home_delta,
                amount_local_delta,
                original_version
            )

            if not success:
                # Log failed update
                try:
                    AuditService.financial(
                        transaction_id=audit_transaction_id,
                        transaction_type=TransactionType.DEPOSIT,
                        amount=amount,
                        currency=currency,
                        status="failed",
                        to_user_id=user_id,
                        payment_method=payment_method or metadata.get('payment_method', 'unknown'),
                        payment_provider=payment_provider,
                        external_reference=external_reference,
                        ip_address=request.remote_addr if request else None,
                        metadata={"error": "Concurrent modification detected"}
                    )
                except Exception:
                    pass
                raise RuntimeError("Concurrent modification detected, please retry")

            # Capture balances AFTER transaction
            home_balance_after = updated_wallet.balance_home
            local_balance_after = updated_wallet.balance_local

            # Calculate risk score (simple version - enhance as needed)
            risk_score = self._calculate_deposit_risk(user_id, amount, currency, payment_method)
            aml_flagged = risk_score > 70

            # UPDATE audit record with completion status
            try:
                AuditService.financial(
                    transaction_id=audit_transaction_id,
                    transaction_type=TransactionType.DEPOSIT,
                    amount=amount,
                    currency=currency,
                    status="completed",
                    to_user_id=user_id,
                    to_balance_before=float(home_balance_before),
                    to_balance_after=float(home_balance_after),
                    fee_amount=float(conversion_fee) if conversion_fee else None,
                    fee_currency=settled_currency,
                    payment_method=payment_method or metadata.get('payment_method', 'unknown'),
                    payment_provider=payment_provider,
                    external_reference=external_reference,
                    risk_score=float(risk_score),
                    aml_flagged=aml_flagged,
                    requires_review=aml_flagged,
                    ip_address=request.remote_addr if request else None,
                    user_agent=request.user_agent.string if request else None,
                    metadata={
                        "idempotency_key": idempotency_key,
                        "conversion_rate": str(conversion_rate) if conversion_rate else None,
                        "conversion_fee": str(conversion_fee),
                        "settled_amount": str(settled_amount),
                        "settled_currency": settled_currency,
                        "client_metadata": metadata or {},
                    }
                )
            except Exception as e:
                current_app.logger.error(f"Failed to update audit record: {e}")

            # Log security alert for high-risk deposits
            if aml_flagged:
                try:
                    AuditService.security(
                        event_type="high_risk_deposit",
                        severity=AuditSeverity.WARNING,
                        description=f"High-risk deposit: {amount} {currency} (risk score: {risk_score})",
                        user_id=user_id,
                        ip_address=request.remote_addr if request else None,
                        metadata={
                            "transaction_id": audit_transaction_id,
                            "amount": float(amount),
                            "currency": currency,
                            "risk_score": float(risk_score),
                            "payment_method": payment_method
                        }
                    )
                except Exception as e:
                    current_app.logger.error(f"Failed to log security alert: {e}")

            # Create transaction record
            tx_meta = {
                "detail": tx_detail,
                "audit_transaction_id": audit_transaction_id,
                "conversion_rate": str(conversion_rate) if conversion_rate else None,
                "conversion_fee": str(conversion_fee),
                "settled_amount": str(settled_amount),
                "settled_currency": settled_currency,
                "balance_before_home": str(home_balance_before),
                "balance_after_home": str(home_balance_after),
                "balance_before_local": str(local_balance_before),
                "balance_after_local": str(local_balance_after),
                "risk_score": str(risk_score),
                "aml_flagged": aml_flagged,
                "client_metadata": metadata or {},
            }

            transaction = self.tx_repo.create(
                wallet_id=wallet.id,
                transaction_type="deposit",
                amount=amount,
                currency=currency,
                tx_id=audit_transaction_id,  # Use same ID for consistency
                client_request_id=idempotency_key,
                meta=tx_meta
            )

            self.db.commit()

            return {
                "status": "success",
                "transaction_id": transaction.tx_id,
                "audit_id": audit_transaction_id,
                "amount": str(amount),
                "currency": currency,
                "settled_amount": str(settled_amount),
                "settled_currency": settled_currency,
                "new_balance_home": str(self._quantize(updated_wallet.balance_home)),
                "new_balance_local": str(self._quantize(updated_wallet.balance_local)),
                "risk_flagged": aml_flagged,
            }

        return self._execute_with_retry(_do_deposit)

    def _calculate_deposit_risk(
            self,
            user_id: int,
            amount: Decimal,
            currency: str,
            payment_method: Optional[str] = None
    ) -> Decimal:
        """
        Calculate risk score for a deposit transaction.

        Returns score from 0-100 where higher = more risky.
        """
        from decimal import Decimal

        risk_score = Decimal("0")

        # Factor 1: Amount size (large deposits are riskier)
        config = current_app.config
        large_threshold = Decimal(config.get("AML_LARGE_DEPOSIT_THRESHOLD", "10000"))
        if amount > large_threshold:
            risk_score += Decimal("30")
        elif amount > large_threshold / 2:
            risk_score += Decimal("15")

        # Factor 2: New user risk
        try:
            from app.identity.models.user import User
            user = User.query.get(user_id)
            if user:
                account_age_days = (datetime.utcnow() - user.created_at).days if user.created_at else 0
                if account_age_days < 7:
                    risk_score += Decimal("25")
                elif account_age_days < 30:
                    risk_score += Decimal("10")
        except Exception:
            pass

        # Factor 3: Payment method risk
        high_risk_methods = ['crypto', 'prepaid_card', 'virtual_card']
        if payment_method and payment_method.lower() in high_risk_methods:
            risk_score += Decimal("20")

        # Factor 4: Currency risk (if unusual for user's location)
        # This would need user's country data

        return min(risk_score, Decimal("100"))

    def _get_ip_address(self) -> Optional[str]:
        """Get current request IP address."""
        try:
            from flask import request
            return request.remote_addr
        except Exception:
            return None

    def _get_user_agent(self) -> Optional[str]:
        """Get current request user agent."""
        try:
            from flask import request
            return request.user_agent.string if request.user_agent else None
        except Exception:
            return None

    def withdraw(
            self,
            user_id: int,
            amount: Decimal,
            currency: str,
            idempotency_key: Optional[str] = None,
            metadata: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Process a withdrawal from a user's wallet.

        Args:
            user_id: Internal user ID
            amount: Amount to withdraw
            currency: Currency of withdrawal
            idempotency_key: Unique key to prevent duplicate processing
            metadata: Additional transaction metadata

        Returns:
            Dict with transaction result
        """
        amount = self._quantize(amount)

        # Validate
        if amount <= Decimal("0"):
            raise ValueError("Amount must be greater than zero")

        self._validate_currency(currency)
        self._check_transaction_limit(amount, "withdraw")

        # Check idempotency
        if idempotency_key:
            existing = self.tx_repo.get_by_client_request_id(idempotency_key)
            if existing:
                raise DuplicateTransactionError(idempotency_key, existing.tx_id or str(existing.id))

        def _do_withdraw():
            wallet = self.wallet_repo.get_by_user_id(user_id, for_update=True)
            if not wallet:
                raise WalletNotFoundError(user_id=user_id)

            original_version = wallet.version

            # Check balance
            if currency == wallet.home_currency:
                if wallet.balance_home < amount:
                    raise InsufficientBalanceError(
                        currency, float(amount), float(wallet.balance_home)
                    )
                amount_home_delta = -amount
                amount_local_delta = Decimal("0")
            elif currency == wallet.local_currency:
                if wallet.balance_local < amount:
                    raise InsufficientBalanceError(
                        currency, float(amount), float(wallet.balance_local)
                    )
                amount_home_delta = Decimal("0")
                amount_local_delta = -amount
            else:
                raise UnsupportedCurrencyError(currency, [wallet.home_currency, wallet.local_currency])

            # Update balance
            success, updated_wallet = self.wallet_repo.update_balance(
                wallet.id,
                amount_home_delta,
                amount_local_delta,
                original_version
            )

            if not success:
                raise RuntimeError("Concurrent modification detected, please retry")

            # Create transaction
            transaction = self.tx_repo.create(
                wallet_id=wallet.id,
                transaction_type="withdrawal",
                amount=amount,
                currency=currency,
                tx_id=self._generate_tx_id(),
                client_request_id=idempotency_key,
                meta={"client_metadata": metadata or {}}
            )

            self.db.commit()

            return {
                "status": "success",
                "transaction_id": transaction.tx_id,
                "amount": str(amount),
                "currency": currency,
                "new_balance_home": str(self._quantize(updated_wallet.balance_home)),
                "new_balance_local": str(self._quantize(updated_wallet.balance_local)),
            }

        return self._execute_with_retry(_do_withdraw)

    def transfer(
            self,
            from_user_id: int,
            to_user_id: int,
            amount: Decimal,
            currency: str,
            idempotency_key: Optional[str] = None,
            note: Optional[str] = None,
            metadata: Optional[Dict] = None,
            platform_fee: Optional[Decimal] = None,
            fee_currency: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Transfer funds between two users with full audit trail and compensation.

        Args:
            from_user_id: Sender's user ID
            to_user_id: Recipient's user ID
            amount: Amount to transfer
            currency: Currency of transfer
            idempotency_key: Unique key to prevent duplicate processing
            note: Optional note/reference
            metadata: Additional transaction metadata
            platform_fee: Optional platform fee to deduct
            fee_currency: Currency for platform fee

        Returns:
            Dict with transaction result

        Raises:
            InsufficientBalanceError: If sender has insufficient funds
            DuplicateTransactionError: If idempotency_key already used
            UnsupportedCurrencyError: If currency not supported
            LimitExceededError: If transfer exceeds limits
        """
        from app.audit.comprehensive_audit import AuditService, TransactionType, AuditSeverity
        from flask import request
        import uuid

        amount = self._quantize(amount)
        audit_transaction_id = f"P2P-{uuid.uuid4().hex[:12].upper()}"
        compensation_required = False
        sender_compensation_delta = Decimal("0")

        if from_user_id == to_user_id:
            raise ValueError("Cannot transfer to yourself")

        if amount <= Decimal("0"):
            raise ValueError("Amount must be greater than zero")

        self._validate_currency(currency)
        self._check_transaction_limit(amount, "transfer")

        # Check idempotency
        if idempotency_key:
            existing = self.tx_repo.get_by_client_request_id(idempotency_key)
            if existing:
                raise DuplicateTransactionError(idempotency_key, existing.tx_id or str(existing.id))

        def _do_transfer():
            nonlocal compensation_required, sender_compensation_delta

            # Get wallets with locks in consistent order (by ID to prevent deadlock)
            sender = self.wallet_repo.get_or_create_by_user_id(from_user_id)
            receiver = self.wallet_repo.get_or_create_by_user_id(to_user_id)

            # Capture sender balances BEFORE transaction
            sender_home_before = sender.balance_home
            sender_local_before = sender.balance_local

            # Capture receiver balances BEFORE transaction
            receiver_home_before = receiver.balance_home
            receiver_local_before = receiver.balance_local

            # Lock in consistent order (critical for deadlock prevention)
            if sender.id < receiver.id:
                locked_sender = self.wallet_repo.get_by_user_id(from_user_id, for_update=True)
                locked_receiver = self.wallet_repo.get_by_user_id(to_user_id, for_update=True)
            else:
                locked_receiver = self.wallet_repo.get_by_user_id(to_user_id, for_update=True)
                locked_sender = self.wallet_repo.get_by_user_id(from_user_id, for_update=True)

            sender_version = locked_sender.version
            receiver_version = locked_receiver.version

            # Calculate platform fee if applicable
            fee_amount = Decimal("0")
            if platform_fee and platform_fee > 0:
                fee_amount = self._quantize(platform_fee)
                fee_currency_code = fee_currency or currency

            # Check sender balance (including fee)
            total_debit = amount + fee_amount
            if currency == locked_sender.home_currency:
                if locked_sender.balance_home < total_debit:
                    raise InsufficientBalanceError(
                        currency, float(total_debit), float(locked_sender.balance_home)
                    )
                sender_home_delta = -total_debit
                sender_local_delta = Decimal("0")
                sender_debit_currency = locked_sender.home_currency
            elif currency == locked_sender.local_currency:
                if locked_sender.balance_local < total_debit:
                    raise InsufficientBalanceError(
                        currency, float(total_debit), float(locked_sender.balance_local)
                    )
                sender_home_delta = Decimal("0")
                sender_local_delta = -total_debit
                sender_debit_currency = locked_sender.local_currency
            else:
                raise UnsupportedCurrencyError(currency, [locked_sender.home_currency, locked_sender.local_currency])

            # Determine receiver credit (may need conversion)
            if currency == locked_receiver.local_currency:
                receiver_amount = amount
                receiver_local_delta = amount
                conversion_rate = None
                conversion_fee = Decimal("0")
            else:
                receiver_amount, conversion_rate, conversion_fee = self.currency_service.convert(
                    amount, currency, locked_receiver.local_currency, apply_fee=True
                )
                receiver_local_delta = receiver_amount

            # Log transfer INITIATION before any balance changes
            try:
                AuditService.financial(
                    transaction_id=audit_transaction_id,
                    transaction_type=TransactionType.TRANSFER,
                    amount=amount,
                    currency=currency,
                    status="pending",
                    from_user_id=from_user_id,
                    to_user_id=to_user_id,
                    from_balance_before=float(
                        sender_home_before if currency == locked_sender.home_currency else sender_local_before),
                    to_balance_before=float(receiver_local_before),
                    fee_amount=float(fee_amount) if fee_amount else None,
                    fee_currency=fee_currency_code if fee_amount else None,
                    payment_method="internal_transfer",
                    ip_address=request.remote_addr if request else None,
                    user_agent=request.user_agent.string if request else None,
                    metadata={
                        "idempotency_key": idempotency_key,
                        "note": note,
                        "conversion_rate": str(conversion_rate) if conversion_rate else None,
                        "conversion_fee": str(conversion_fee),
                        "platform_fee": str(fee_amount) if fee_amount else None,
                        "client_metadata": metadata or {},
                    }
                )
            except Exception as e:
                current_app.logger.error(f"Failed to create audit record for transfer: {e}")

            # Update sender balance (DEBIT)
            sender_success, updated_sender = self.wallet_repo.update_balance(
                locked_sender.id,
                sender_home_delta,
                sender_local_delta,
                sender_version
            )

            if not sender_success:
                # Log failed sender update
                try:
                    AuditService.financial(
                        transaction_id=audit_transaction_id,
                        transaction_type=TransactionType.TRANSFER,
                        amount=amount,
                        currency=currency,
                        status="failed",
                        from_user_id=from_user_id,
                        to_user_id=to_user_id,
                        payment_method="internal_transfer",
                        metadata={"error": "Concurrent modification on sender"}
                    )
                except Exception:
                    pass
                raise RuntimeError("Concurrent modification detected on sender, please retry")

            # Mark that compensation may be needed if receiver fails
            compensation_required = True
            sender_compensation_delta = -sender_home_delta if sender_home_delta != 0 else -sender_local_delta

            # Update receiver balance (CREDIT)
            receiver_success, updated_receiver = self.wallet_repo.update_balance(
                locked_receiver.id,
                Decimal("0"),  # No home currency change for receiver (local only)
                receiver_local_delta,
                receiver_version
            )

            if not receiver_success:
                # COMPENSATION: Rollback sender's balance
                current_app.logger.warning(
                    f"Transfer failed at receiver stage, compensating sender {from_user_id}"
                )

                # Reverse the sender's debit
                compensation_success, _ = self.wallet_repo.update_balance(
                    locked_sender.id,
                    -sender_home_delta,  # Reverse home delta
                    -sender_local_delta,  # Reverse local delta
                    updated_sender.version  # Use updated version
                )

                if not compensation_success:
                    # CRITICAL: Manual intervention required
                    current_app.logger.critical(
                        f"COMPENSATION FAILED for transfer {audit_transaction_id}. "
                        f"Sender {from_user_id} debited but receiver {to_user_id} not credited. "
                        f"Amount: {amount} {currency}. Manual intervention required."
                    )

                    # Log critical security event
                    try:
                        AuditService.security(
                            event_type="transfer_compensation_failed",
                            severity=AuditSeverity.CRITICAL,
                            description=f"Transfer compensation failed: sender debited but receiver not credited",
                            user_id=from_user_id,
                            ip_address=request.remote_addr if request else None,
                            metadata={
                                "transaction_id": audit_transaction_id,
                                "amount": float(amount),
                                "currency": currency,
                                "from_user_id": from_user_id,
                                "to_user_id": to_user_id,
                                "sender_delta_home": float(sender_home_delta),
                                "sender_delta_local": float(sender_local_delta)
                            }
                        )
                    except Exception:
                        pass

                    raise RuntimeError(
                        f"Transfer failed and compensation failed. Transaction {audit_transaction_id} "
                        f"requires manual review."
                    )

                # Log compensation success
                current_app.logger.info(
                    f"Compensation successful for transfer {audit_transaction_id}. "
                    f"Sender {from_user_id} balance restored."
                )

                raise RuntimeError("Transfer failed at receiver stage, sender balance restored")

            # Capture balances AFTER transaction
            sender_home_after = updated_sender.balance_home
            sender_local_after = updated_sender.balance_local
            receiver_local_after = updated_receiver.balance_local

            # Calculate risk score for this transfer
            risk_score = self._calculate_transfer_risk(from_user_id, to_user_id, amount, currency)
            aml_flagged = risk_score > 80

            # UPDATE audit record with completion status
            try:
                AuditService.financial(
                    transaction_id=audit_transaction_id,
                    transaction_type=TransactionType.TRANSFER,
                    amount=amount,
                    currency=currency,
                    status="completed",
                    from_user_id=from_user_id,
                    to_user_id=to_user_id,
                    from_balance_before=float(
                        sender_home_before if currency == locked_sender.home_currency else sender_local_before),
                    from_balance_after=float(
                        sender_home_after if currency == locked_sender.home_currency else sender_local_after),
                    to_balance_before=float(receiver_local_before),
                    to_balance_after=float(receiver_local_after),
                    fee_amount=float(fee_amount) if fee_amount else None,
                    fee_currency=fee_currency_code if fee_amount else None,
                    payment_method="internal_transfer",
                    risk_score=float(risk_score),
                    aml_flagged=aml_flagged,
                    requires_review=aml_flagged,
                    ip_address=request.remote_addr if request else None,
                    user_agent=request.user_agent.string if request else None,
                    metadata={
                        "idempotency_key": idempotency_key,
                        "note": note,
                        "conversion_rate": str(conversion_rate) if conversion_rate else None,
                        "conversion_fee": str(conversion_fee),
                        "platform_fee": str(fee_amount) if fee_amount else None,
                        "client_metadata": metadata or {},
                    }
                )
            except Exception as e:
                current_app.logger.error(f"Failed to update audit record for transfer: {e}")

            # Log security alert for suspicious transfers
            if aml_flagged:
                try:
                    AuditService.security(
                        event_type="suspicious_transfer",
                        severity=AuditSeverity.WARNING,
                        description=f"Suspicious transfer: {amount} {currency} from user {from_user_id} to {to_user_id}",
                        user_id=from_user_id,
                        ip_address=request.remote_addr if request else None,
                        metadata={
                            "transaction_id": audit_transaction_id,
                            "to_user_id": to_user_id,
                            "amount": float(amount),
                            "currency": currency,
                            "risk_score": float(risk_score),
                            "note": note
                        }
                    )
                except Exception as e:
                    current_app.logger.error(f"Failed to log security alert: {e}")

            # Create sender transaction record
            sender_tx = self.tx_repo.create(
                wallet_id=locked_sender.id,
                transaction_type="send",
                amount=amount,
                currency=currency,
                tx_id=audit_transaction_id,  # Use same ID for consistency
                client_request_id=idempotency_key,
                meta={
                    "to_user_id": to_user_id,
                    "note": note,
                    "conversion_rate": str(conversion_rate) if conversion_rate else None,
                    "conversion_fee": str(conversion_fee),
                    "platform_fee": str(fee_amount) if fee_amount else None,
                    "balance_before_home": str(sender_home_before),
                    "balance_after_home": str(sender_home_after),
                    "balance_before_local": str(sender_local_before),
                    "balance_after_local": str(sender_local_after),
                    "risk_score": str(risk_score),
                    "aml_flagged": aml_flagged,
                    "client_metadata": metadata or {},
                }
            )

            # Create receiver transaction record
            receiver_tx = self.tx_repo.create(
                wallet_id=locked_receiver.id,
                transaction_type="receive",
                amount=receiver_amount,
                currency=locked_receiver.local_currency,
                tx_id=f"{audit_transaction_id}-RECV",
                client_request_id=None,
                meta={
                    "from_user_id": from_user_id,
                    "note": note,
                    "original_amount": str(amount),
                    "original_currency": currency,
                    "conversion_rate": str(conversion_rate) if conversion_rate else None,
                    "conversion_fee": str(conversion_fee),
                    "balance_before": str(receiver_local_before),
                    "balance_after": str(receiver_local_after),
                }
            )

            self.db.commit()

            return {
                "status": "success",
                "transaction_id": sender_tx.tx_id,
                "audit_id": audit_transaction_id,
                "amount": str(amount),
                "currency": currency,
                "receiver_amount": str(receiver_amount),
                "receiver_currency": locked_receiver.local_currency,
                "new_balance_home": str(self._quantize(updated_sender.balance_home)),
                "new_balance_local": str(self._quantize(updated_sender.balance_local)),
                "fee_amount": str(fee_amount) if fee_amount else None,
                "note": note,
                "risk_flagged": aml_flagged,
            }

        return self._execute_with_retry(_do_transfer)

    def _calculate_transfer_risk(
            self,
            from_user_id: int,
            to_user_id: int,
            amount: Decimal,
            currency: str
    ) -> Decimal:
        """
        Calculate risk score for a transfer transaction.

        Returns score from 0-100 where higher = more risky.
        """
        from decimal import Decimal

        risk_score = Decimal("0")

        # Factor 1: Amount size
        large_threshold = Decimal(current_app.config.get("AML_LARGE_TRANSFER_THRESHOLD", "5000"))
        if amount > large_threshold:
            risk_score += Decimal("25")
        elif amount > large_threshold / 2:
            risk_score += Decimal("10")

        # Factor 2: Rapid succession (would need to check recent transactions)
        # This requires querying recent transfers from this user

        # Factor 3: New recipient (no previous transactions between these users)
        try:
            from app.wallet.models import Transaction as TransactionModel
            sender_wallet = self.wallet_repo.get_by_user_id(from_user_id)
            if sender_wallet:
                # Use == (scalar) not .in_() — .in_() requires an iterable
                previous_tx = TransactionModel.query.filter(
                    TransactionModel.wallet_id == sender_wallet.id,
                    TransactionModel.meta['to_user_id'].astext.cast(db.Integer) == to_user_id
                ).first()

                if not previous_tx:
                    risk_score += Decimal("15")  # First time sending to this recipient
        except Exception:
            pass

        # Factor 4: Account age
        try:
            from app.identity.models.user import User
            user = User.query.get(from_user_id)
            if user:
                account_age_days = (datetime.utcnow() - user.created_at).days if user.created_at else 0
                if account_age_days < 7:
                    risk_score += Decimal("20")
                elif account_age_days < 30:
                    risk_score += Decimal("10")
        except Exception:
            pass

        # Factor 5: Unusual hour (e.g., 2 AM - 5 AM local time)
        # Would need user's timezone

        return min(risk_score, Decimal("100"))

    def _calculate_withdrawal_risk(
            self,
            user_id: int,
            amount: Decimal,
            currency: str,
            destination_type: str
    ) -> Decimal:
        """
        Calculate risk score for a withdrawal transaction.

        Returns score from 0-100 where higher = more risky.
        """
        from decimal import Decimal

        risk_score = Decimal("0")

        # Factor 1: Amount size
        large_threshold = Decimal(current_app.config.get("AML_LARGE_WITHDRAWAL_THRESHOLD", "3000"))
        if amount > large_threshold:
            risk_score += Decimal("35")
        elif amount > large_threshold / 2:
            risk_score += Decimal("15")

        # Factor 2: Destination type risk
        high_risk_destinations = ['crypto_wallet', 'foreign_bank', 'prepaid_card']
        if destination_type.lower() in high_risk_destinations:
            risk_score += Decimal("25")

        # Factor 3: Account age
        try:
            from app.identity.models.user import User
            user = User.query.get(user_id)
            if user:
                account_age_days = (datetime.utcnow() - user.created_at).days if user.created_at else 0
                if account_age_days < 14:  # Withdrawals require older accounts
                    risk_score += Decimal("30")
                elif account_age_days < 60:
                    risk_score += Decimal("15")
        except Exception:
            pass

        # Factor 4: KYC level
        try:
            if hasattr(user, 'kyc_level') and user.kyc_level < 2:
                risk_score += Decimal("20")
        except Exception:
            pass

        return min(risk_score, Decimal("100"))

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
            user_id: Internal user ID
            limit: Number of transactions to return
            offset: Pagination offset
            transaction_type: Optional filter by type

        Returns:
            Dict with transactions and pagination info
        """
        wallet = self.wallet_repo.get_by_user_id(user_id)

        if not wallet:
            return {
                "transactions": [],
                "total": 0,
                "limit": limit,
                "offset": offset,
                "has_more": False
            }

        transactions = self.tx_repo.get_by_wallet_id(
            wallet.id, limit, offset, transaction_type
        )
        total = self.tx_repo.get_transaction_count(wallet.id, transaction_type)

        return {
            "transactions": [
                {
                    "id": t.tx_id or str(t.id),
                    "type": t.type,
                    "amount": str(t.amount),
                    "currency": t.currency,
                    "status": "completed",  # All transactions are immutable
                    "created_at": t.created_at.isoformat(),
                    "metadata": t.meta,
                }
                for t in transactions
            ],
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": offset + limit < total
        }
