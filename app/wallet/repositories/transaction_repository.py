"""
app/wallet/repositories/transaction_repository.py
Database operations for Transaction model.
"""

from decimal import Decimal
from typing import Optional, List, Dict, Any
from datetime import datetime
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.extensions import db
from app.wallet.models import Transaction as TransactionModel
from app.wallet.exceptions import DuplicateTransactionError


class TransactionRepository:
    """
    Repository for transaction database operations.
    """

    def __init__(self, db_session: Session = None):
        self.db = db_session or db.session

    def create(
            self,
            wallet_id: int,
            transaction_type: str,
            amount: Decimal,
            currency: str,
            tx_id: Optional[str] = None,
            client_request_id: Optional[str] = None,
            meta: Optional[Dict] = None
    ) -> TransactionModel:
        """
        Create a new transaction record.

        Args:
            wallet_id: Wallet ID
            transaction_type: deposit, withdraw, send, receive
            amount: Transaction amount
            currency: Currency code
            tx_id: Optional transaction reference (generated if not provided)
            client_request_id: Idempotency key
            meta: Additional metadata

        Returns:
            Created TransactionModel

        Raises:
            DuplicateTransactionError: If client_request_id already exists
        """
        # Check for duplicate idempotency key
        if client_request_id:
            existing = self.get_by_client_request_id(client_request_id)
            if existing:
                raise DuplicateTransactionError(
                    client_request_id,
                    str(existing.tx_id or existing.id)
                )

        # Generate tx_id if not provided
        if not tx_id:
            import uuid
            tx_id = str(uuid.uuid4())

        transaction = TransactionModel(
            wallet_id=wallet_id,
            tx_id=tx_id,
            client_request_id=client_request_id,
            type=transaction_type,
            amount=amount,
            currency=currency,
            meta=meta or {},
            created_at=datetime.utcnow()
        )

        self.db.add(transaction)
        self.db.flush()  # Get ID without committing

        return transaction

    def get_by_client_request_id(self, client_request_id: str) -> Optional[TransactionModel]:
        """
        Get transaction by idempotency key.

        Args:
            client_request_id: Idempotency key from client

        Returns:
            TransactionModel or None
        """
        return self.db.execute(
            select(TransactionModel).where(
                TransactionModel.client_request_id == client_request_id
            )
        ).scalar_one_or_none()

    def get_by_tx_id(self, tx_id: str) -> Optional[TransactionModel]:
        """
        Get transaction by transaction reference.

        Args:
            tx_id: Transaction reference (UUID)

        Returns:
            TransactionModel or None
        """
        return self.db.execute(
            select(TransactionModel).where(TransactionModel.tx_id == tx_id)
        ).scalar_one_or_none()

    def get_by_wallet_id(
            self,
            wallet_id: int,
            limit: int = 50,
            offset: int = 0,
            transaction_type: Optional[str] = None
    ) -> List[TransactionModel]:
        """
        Get transactions for a wallet with pagination.

        Args:
            wallet_id: Wallet ID
            limit: Maximum number of transactions
            offset: Pagination offset
            transaction_type: Optional filter by transaction type

        Returns:
            List of TransactionModel
        """
        query = select(TransactionModel).where(
            TransactionModel.wallet_id == wallet_id
        )

        if transaction_type:
            query = query.where(TransactionModel.type == transaction_type)

        query = query.order_by(TransactionModel.created_at.desc())
        query = query.offset(offset).limit(limit)

        return self.db.execute(query).scalars().all()

    def get_transaction_count(
            self,
            wallet_id: int,
            transaction_type: Optional[str] = None
    ) -> int:
        """
        Get total transaction count for a wallet.

        Args:
            wallet_id: Wallet ID
            transaction_type: Optional filter by transaction type

        Returns:
            Total count
        """
        query = select(func.count()).select_from(TransactionModel).where(
            TransactionModel.wallet_id == wallet_id
        )

        if transaction_type:
            query = query.where(TransactionModel.type == transaction_type)

        return self.db.execute(query).scalar() or 0

    def get_volume_by_currency(
            self,
            wallet_id: int,
            currency: str,
            since: datetime
    ) -> Decimal:
        """
        Get total transaction volume for a currency since a given time.

        Args:
            wallet_id: Wallet ID
            currency: Currency code
            since: Start datetime

        Returns:
            Total volume (sum of amounts)
        """
        result = self.db.execute(
            select(func.sum(TransactionModel.amount))
            .where(
                TransactionModel.wallet_id == wallet_id,
                TransactionModel.currency == currency,
                TransactionModel.created_at >= since,
                TransactionModel.type.in_(['deposit', 'send'])  # Outgoing volume
            )
        ).scalar()

        return result or Decimal("0")