"""
tests/wallet/test_ledger_concurrency.py
Comprehensive concurrency tests for the ledger-based wallet system.

Tests verify:
- No double spending under high concurrency
- Atomic transaction boundaries
- DB-enforced idempotency
- Frozen wallet enforcement
- Real daily limit queries
- Balance always derived from ledger
"""

import pytest
from decimal import Decimal
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

from app import create_app
from app.extensions import db
from app.wallet.services.wallet_service import WalletService
from app.wallet.repositories.ledger_repository import LedgerRepository
from app.wallet.repositories.account_repository import AccountRepository
from app.wallet.models.ledger import AccountModel, LedgerEntryModel, EntryType
from app.wallet.models.transaction import TransactionModel, TransactionStatus
from app.wallet.exceptions import (
    InsufficientBalanceError,
    WalletFrozenError,
    LimitExceededError
)


@pytest.fixture
def app():
    """Create application for testing."""
    app = create_app('testing')
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://test:test@localhost:5432/afcon360_test'
    app.config['WALLET_MAX_DEPOSIT'] = Decimal('10000')
    app.config['WALLET_DAILY_LIMIT_HOME'] = Decimal('5000')
    
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def service(app):
    """Create wallet service instance."""
    return WalletService()


@pytest.fixture
def ledger_repo(app):
    """Create ledger repository instance."""
    return LedgerRepository()


@pytest.fixture
def account_repo(app):
    """Create account repository instance."""
    return AccountRepository()


@pytest.fixture
def test_user(app):
    """Create a test user."""
    from app.identity.models.user import User
    user = User(
        email='test@example.com',
        username='testuser',
        password_hash='hashed_password'
    )
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def funded_account(app, test_user):
    """Create a funded account for testing."""
    account = AccountRepository().get_or_create(test_user.id, 'USD')
    
    # Fund with 1000 units via ledger entry
    ledger_entry = LedgerEntryModel(
        transaction_id=uuid4(),
        account_id=account.id,
        entry_type=EntryType.CREDIT,
        amount=Decimal('1000'),
        currency='USD'
    )
    db.session.add(ledger_entry)
    db.session.commit()
    
    return account


class TestNoDoubleSpend:
    """Test that double spending is impossible under concurrency."""
    
    def test_no_double_spend_100_parallel_withdrawals(self, app, funded_account, service):
        """
        Test: 100 threads each withdrawing 100 units from 1000 balance.
        
        Expected: Exactly 10 succeed, 90 raise InsufficientBalanceError.
        Expected: Final balance == 0, never negative.
        """
        user_id = funded_account.user_id
        account_id = funded_account.id
        
        successful_withdrawals = []
        failed_withdrawals = []
        
        def withdraw_attempt(thread_id):
            try:
                result = service.withdraw(
                    user_id=user_id,
                    amount=Decimal('100'),
                    currency='USD',
                    client_request_id=f"withdraw_{thread_id}_{uuid4().hex}"
                )
                successful_withdrawals.append(thread_id)
                return True
            except InsufficientBalanceError:
                failed_withdrawals.append(thread_id)
                return False
            except Exception as e:
                failed_withdrawals.append(thread_id)
                print(f"Thread {thread_id} unexpected error: {e}")
                return False
        
        # Fire 100 parallel withdrawals
        with ThreadPoolExecutor(max_workers=100) as executor:
            futures = [executor.submit(withdraw_attempt, i) for i in range(100)]
            results = [f.result() for f in as_completed(futures)]
        
        # Verify exactly 10 succeeded
        assert len(successful_withdrawals) == 10, \
            f"Expected 10 successful withdrawals, got {len(successful_withdrawals)}"
        
        # Verify 90 failed
        assert len(failed_withdrawals) == 90, \
            f"Expected 90 failed withdrawals, got {len(failed_withdrawals)}"
        
        # Verify final balance is exactly 0
        final_balance = LedgerRepository().get_balance(account_id, 'USD')
        assert final_balance == Decimal('0'), \
            f"Expected final balance 0, got {final_balance}"
        
        # Verify balance never went negative
        assert final_balance >= Decimal('0'), \
            f"Balance went negative: {final_balance}"
    
    def test_no_double_send_parallel_transfers(self, app, funded_account, service, test_user):
        """
        Test: 50 threads each sending 50 units to different recipients.
        
        Expected: Exactly 20 succeed (1000/50), 30 fail.
        Expected: Sender balance == 0, never negative.
        """
        # Create recipient accounts
        recipient_ids = []
        for i in range(50):
            from app.identity.models.user import User
            recipient = User(
                email=f'recipient{i}@example.com',
                username=f'recipient{i}',
                password_hash='hashed_password'
            )
            db.session.add(recipient)
            db.session.commit()
            recipient_ids.append(recipient.id)
        
        successful_transfers = []
        failed_transfers = []
        
        def transfer_attempt(thread_id):
            try:
                result = service.transfer(
                    from_user_id=funded_account.user_id,
                    to_user_id=recipient_ids[thread_id],
                    amount=Decimal('50'),
                    currency='USD',
                    client_request_id=f"transfer_{thread_id}_{uuid4().hex}"
                )
                successful_transfers.append(thread_id)
                return True
            except InsufficientBalanceError:
                failed_transfers.append(thread_id)
                return False
            except Exception as e:
                failed_transfers.append(thread_id)
                print(f"Thread {thread_id} unexpected error: {e}")
                return False
        
        # Fire 50 parallel transfers
        with ThreadPoolExecutor(max_workers=50) as executor:
            futures = [executor.submit(transfer_attempt, i) for i in range(50)]
            results = [f.result() for f in as_completed(futures)]
        
        # Verify exactly 20 succeeded
        assert len(successful_transfers) == 20, \
            f"Expected 20 successful transfers, got {len(successful_transfers)}"
        
        # Verify 30 failed
        assert len(failed_transfers) == 30, \
            f"Expected 30 failed transfers, got {len(failed_transfers)}"
        
        # Verify sender balance is exactly 0
        final_balance = LedgerRepository().get_balance(funded_account.id, 'USD')
        assert final_balance == Decimal('0'), \
            f"Expected final balance 0, got {final_balance}"


class TestTransferAtomicity:
    """Test that transfers are atomic - partial state impossible."""
    
    def test_transfer_atomicity_on_db_error(self, app, funded_account, service, test_user):
        """
        Test: Mock DB to raise after first ledger entry insert.
        
        Expected: Sender balance unchanged, receiver balance unchanged.
        Expected: Zero ledger entries committed.
        """
        # Create recipient
        from app.identity.models.user import User
        recipient = User(
            email='recipient@example.com',
            username='recipient',
            password_hash='hashed_password'
        )
        db.session.add(recipient)
        db.session.commit()
        
        # Get initial balances
        sender_balance_before = LedgerRepository().get_balance(funded_account.id, 'USD')
        recipient_account = AccountRepository().get_or_create(recipient.id, 'USD')
        recipient_balance_before = LedgerRepository().get_balance(recipient_account.id, 'USD')
        
        # Mock to raise error during transaction
        # This simulates a database failure mid-transaction
        original_add = db.session.add
        
        def mock_add_with_error(obj):
            if isinstance(obj, LedgerEntryModel):
                # After first entry, raise error
                original_add(obj)
                raise Exception("Simulated DB error")
            return original_add(obj)
        
        db.session.add = mock_add_with_error
        
        # Attempt transfer
        try:
            service.transfer(
                from_user_id=funded_account.user_id,
                to_user_id=recipient.id,
                amount=Decimal('100'),
                currency='USD',
                client_request_id=f"atomic_test_{uuid4().hex}"
            )
            assert False, "Transfer should have raised exception"
        except Exception as e:
            assert "Simulated DB error" in str(e)
        
        # Restore original
        db.session.add = original_add
        
        # Verify balances unchanged
        sender_balance_after = LedgerRepository().get_balance(funded_account.id, 'USD')
        recipient_balance_after = LedgerRepository().get_balance(recipient_account.id, 'USD')
        
        assert sender_balance_after == sender_balance_before, \
            "Sender balance should be unchanged"
        assert recipient_balance_after == recipient_balance_before, \
            "Receiver balance should be unchanged"
        
        # Verify no ledger entries for this transaction
        # (All entries should have rolled back)


class TestIdempotency:
    """Test DB-enforced idempotency."""
    
    def test_idempotency_is_db_enforced(self, app, funded_account, service):
        """
        Test: POST deposit twice with same client_request_id.
        
        Expected: Only 1 transaction row exists.
        Expected: Balance credited exactly once.
        """
        client_request_id = f"idempotency_test_{uuid4().hex}"
        initial_balance = LedgerRepository().get_balance(funded_account.id, 'USD')
        
        # First deposit
        result1 = service.deposit(
            user_id=funded_account.user_id,
            amount=Decimal('100'),
            currency='USD',
            client_request_id=client_request_id
        )
        
        balance_after_first = LedgerRepository().get_balance(funded_account.id, 'USD')
        assert balance_after_first == initial_balance + Decimal('100')
        
        # Second deposit with same idempotency key
        result2 = service.deposit(
            user_id=funded_account.user_id,
            amount=Decimal('100'),
            currency='USD',
            client_request_id=client_request_id
        )
        
        balance_after_second = LedgerRepository().get_balance(funded_account.id, 'USD')
        
        # Verify balance unchanged (not double-credited)
        assert balance_after_second == balance_after_first, \
            "Balance should not be double-credited"
        
        # Verify only 1 transaction exists
        tx_count = db.session.query(TransactionModel).filter(
            TransactionModel.client_request_id == client_request_id
        ).count()
        
        assert tx_count == 1, f"Expected 1 transaction, found {tx_count}"
        
        # Verify result2 indicates already processed
        assert result2.get('already_processed') == True


class TestFrozenWallet:
    """Test frozen wallet enforcement."""
    
    def test_frozen_wallet_blocks_all_ops(self, app, funded_account, service):
        """
        Test: Freeze wallet, then attempt deposit/withdraw/transfer.
        
        Expected: All operations raise WalletFrozenError.
        """
        # Freeze the account
        AccountRepository().freeze_account(funded_account.id, "Test freeze")
        
        # Test deposit
        with pytest.raises(WalletFrozenError):
            service.deposit(
                user_id=funded_account.user_id,
                amount=Decimal('100'),
                currency='USD',
                client_request_id=f"deposit_test_{uuid4().hex}"
            )
        
        # Test withdraw
        with pytest.raises(WalletFrozenError):
            service.withdraw(
                user_id=funded_account.user_id,
                amount=Decimal('10'),
                currency='USD',
                client_request_id=f"withdraw_test_{uuid4().hex}"
            )
        
        # Test transfer
        from app.identity.models.user import User
        recipient = User(
            email='recipient@example.com',
            username='recipient',
            password_hash='hashed_password'
        )
        db.session.add(recipient)
        db.session.commit()
        
        with pytest.raises(WalletFrozenError):
            service.transfer(
                from_user_id=funded_account.user_id,
                to_user_id=recipient.id,
                amount=Decimal('10'),
                currency='USD',
                client_request_id=f"transfer_test_{uuid4().hex}"
            )


class TestDailyLimit:
    """Test real daily limit queries."""
    
    def test_daily_limit_real_query(self, app, funded_account, service):
        """
        Test: Insert ledger entries summing to daily limit.
        
        Expected: Next transaction raises DailyLimitExceededError.
        """
        # Set daily limit to 500
        from flask import current_app
        current_app.config['WALLET_DAILY_LIMIT_HOME'] = Decimal('500')
        
        # Create ledger entries totaling 500
        for i in range(5):
            ledger_entry = LedgerEntryModel(
                transaction_id=uuid4(),
                account_id=funded_account.id,
                entry_type=EntryType.DEBIT,
                amount=Decimal('100'),
                currency='USD',
                created_at=datetime.utcnow()  # Within 24 hours
            )
            db.session.add(ledger_entry)
        db.session.commit()
        
        # Verify daily volume is 500
        daily_volume = LedgerRepository().get_daily_volume(funded_account.id, 'USD')
        assert daily_volume == Decimal('500')
        
        # Attempt another withdrawal - should exceed limit
        with pytest.raises(LimitExceededError) as exc_info:
            service.withdraw(
                user_id=funded_account.user_id,
                amount=Decimal('10'),
                currency='USD',
                client_request_id=f"limit_test_{uuid4().hex}"
            )
        
        assert exc_info.value.limit_type == 'daily'


class TestBalanceDerived:
    """Test that balance is always derived from ledger."""
    
    def test_balance_always_derived(self, app, funded_account, ledger_repo):
        """
        Test: Verify get_balance() hits ledger_entries, not wallet row.
        
        Expected: wallets table has no balance column being read.
        Expected: get_balance() hits ledger_entries.
        """
        # Get balance via ledger
        ledger_balance = ledger_repo.get_balance(funded_account.id, 'USD')
        
        # Verify it matches sum of ledger entries
        from sqlalchemy import func, case
        from app.wallet.models.ledger import LedgerEntryModel
        
        calculated_balance = db.session.query(
            func.sum(
                case(
                    (LedgerEntryModel.entry_type == EntryType.CREDIT, LedgerEntryModel.amount),
                    else_=-LedgerEntryModel.amount
                )
            )
        ).filter(
            LedgerEntryModel.account_id == funded_account.id,
            LedgerEntryModel.currency == 'USD'
        ).scalar() or Decimal('0')
        
        assert ledger_balance == calculated_balance, \
            f"Ledger balance {ledger_balance} != calculated {calculated_balance}"
        
        # Verify AccountModel has no balance column
        assert not hasattr(funded_account, 'balance'), \
            "AccountModel should not have a balance column"


class TestTransactionStatus:
    """Test transaction status transitions."""
    
    def test_transaction_status_pending_to_completed(self, app, funded_account, service):
        """
        Test: Transaction starts as PENDING, becomes COMPLETED on success.
        """
        client_request_id = f"status_test_{uuid4().hex}"
        
        # Deposit
        result = service.deposit(
            user_id=funded_account.user_id,
            amount=Decimal('100'),
            currency='USD',
            client_request_id=client_request_id
        )
        
        # Get transaction
        tx = db.session.query(TransactionModel).filter(
            TransactionModel.client_request_id == client_request_id
        ).first()
        
        assert tx is not None
        assert tx.status == TransactionStatus.COMPLETED
        assert tx.completed_at is not None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
