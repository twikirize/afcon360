
from decimal import Decimal
from datetime import datetime, timezone
from typing import List, Dict, Any
import logging
from app.extensions import db
from app.wallet.models.ledger import AccountModel, LedgerEntryModel, EntryType
from app.wallet.models.transaction import TransactionModel, TransactionStatus
from app.wallet.models.reconciliation import ReconciliationRun, ReconciliationIssue
from app.wallet.services.wallet_notifications import notify_reconciliation_alert

logger = logging.getLogger(__name__)

class ReconciliationService:
    """
    Service for daily wallet reconciliation.
    Compares derived ledger balance against transaction history.
    """

    def __init__(self, session=None):
        self.db = session or db.session

    def run_daily_reconciliation(self) -> Dict[str, Any]:
        """
        Run a full platform reconciliation.
        Checks every account for drift between transactions and ledger.
        """
        run = ReconciliationRun(status="running")
        self.db.add(run)
        self.db.commit()

        stats = {
            "total_accounts": 0,
            "mismatches": [],
            "checked_at": datetime.now(timezone.utc).isoformat()
        }

        try:
            accounts = AccountModel.query.all()
            stats["total_accounts"] = len(accounts)

            for account in accounts:
                # 1. Get ledger balance
                ledger_balance = self._get_ledger_balance(account.id, account.currency)
                
                # 2. Get transaction sum (source of truth for intended balance)
                tx_balance = self._get_transaction_balance(account.id, account.currency)

                if ledger_balance != tx_balance:
                    issue = {
                        "account_id": str(account.id),
                        "user_id": account.user_id,
                        "ledger_balance": str(ledger_balance),
                        "transaction_balance": str(tx_balance),
                        "drift": str(ledger_balance - tx_balance)
                    }
                    stats["mismatches"].append(issue)
                    
                    # Log issue to database
                    reconciliation_issue = ReconciliationIssue(
                        run_id=run.id,
                        issue_type="BALANCE_MISMATCH",
                        details=issue
                    )
                    self.db.add(reconciliation_issue)

            run.mark_completed(summary=stats, session=self.db)
            self.db.commit()

            if stats["mismatches"]:
                logger.error(f"Reconciliation found {len(stats['mismatches'])} mismatches!")
                notify_reconciliation_alert(stats["mismatches"])

            return stats

        except Exception as e:
            logger.exception("Reconciliation failed")
            run.status = "failed"
            run.notes = str(e)
            self.db.commit()
            raise

    def _get_ledger_balance(self, account_id, currency) -> Decimal:
        """Calculate balance from ledger entries."""
        # Sum credits - sum debits
        credits = self.db.query(db.func.sum(LedgerEntryModel.amount)).filter(
            LedgerEntryModel.account_id == account_id,
            LedgerEntryModel.currency == currency,
            LedgerEntryModel.entry_type == EntryType.CREDIT
        ).scalar() or Decimal('0')

        debits = self.db.query(db.func.sum(LedgerEntryModel.amount)).filter(
            LedgerEntryModel.account_id == account_id,
            LedgerEntryModel.currency == currency,
            LedgerEntryModel.entry_type == EntryType.DEBIT
        ).scalar() or Decimal('0')

        return credits - debits

    def _get_transaction_balance(self, account_id, currency) -> Decimal:
        """Calculate intended balance from COMPLETED transactions."""
        # This is more complex because transactions have different types
        # Deposits/Adjustments(+) vs Withdrawals/Fees(-)
        
        deposits = self.db.query(db.func.sum(TransactionModel.amount)).filter(
            TransactionModel.account_id == account_id,
            TransactionModel.currency == currency,
            TransactionModel.status == TransactionStatus.COMPLETED,
            TransactionModel.tx_type.in_(['deposit', 'adjustment', 'refund'])
        ).scalar() or Decimal('0')

        withdrawals = self.db.query(db.func.sum(TransactionModel.amount)).filter(
            TransactionModel.account_id == account_id,
            TransactionModel.currency == currency,
            TransactionModel.status == TransactionStatus.COMPLETED,
            TransactionModel.tx_type.in_(['withdraw', 'fee'])
        ).scalar() or Decimal('0')

        # Handle transfers (sender - / recipient +)
        sent_transfers = self.db.query(db.func.sum(TransactionModel.amount)).filter(
            TransactionModel.account_id == account_id,
            TransactionModel.currency == currency,
            TransactionModel.status == TransactionStatus.COMPLETED,
            TransactionModel.tx_type == 'transfer'
        ).scalar() or Decimal('0')
        
        # Recipient transfers are trickier if account_id is not set for recipient in the same row
        # Usually one transaction row per transfer, but ledger has 2 entries.
        # Let's check how transfers are stored.
        # In this system, one transaction row exists, but it references the sender.
        # For recipient, we might need a separate query or a different schema.
        # However, for RECONCILIATION of a specific ACCOUNT:
        # If I am the recipient, I should have COMPLETED transactions where recipient_user_id == my_user_id.
        
        from app.wallet.models.ledger import AccountModel
        account = AccountModel.query.get(account_id)
        received_transfers = self.db.query(db.func.sum(TransactionModel.amount)).filter(
            TransactionModel.recipient_user_id == account.user_id,
            TransactionModel.currency == currency,
            TransactionModel.status == TransactionStatus.COMPLETED,
            TransactionModel.tx_type == 'transfer'
        ).scalar() or Decimal('0')

        return (deposits + received_transfers) - (withdrawals + sent_transfers)
