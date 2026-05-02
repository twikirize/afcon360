"""
app/wallet/repositories/transaction_repository.py
Transaction repository with atomic idempotency (DB-enforced).
"""

from typing import Optional, List
from uuid import UUID
from datetime import datetime
from decimal import Decimal
from sqlalchemy import select, and_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session
from app.extensions import db
from app.wallet.models.transaction import TransactionModel, TransactionType, TransactionStatus
from app.wallet.exceptions import DuplicateTransactionError


class TransactionRepository:
    """
    Repository for transaction database operations.
    
    Idempotency is enforced at the database level via UNIQUE constraint
    on client_request_id - no TOCTOU races possible.
    """

    def __init__(self, db_session: Session = None):
        self.db = db_session or db.session

    def get_or_create(
        self,
        client_request_id: str,
        tx_type: TransactionType,
        amount: Decimal,
        currency: str,
        user_id: Optional[int] = None,
        recipient_user_id: Optional[int] = None,
        metadata: Optional[dict] = None
    ) -> TransactionModel:
        """
        Get or create transaction atomically.
        
        Uses PostgreSQL ON CONFLICT to eliminate TOCTOU race conditions.
        If client_request_id already exists, returns the existing transaction.
        Otherwise, creates a new one.
        
        Args:
            client_request_id: Unique idempotency key
            tx_type: Transaction type
            amount: Transaction amount
            currency: Currency code
            user_id: Primary user ID
            recipient_user_id: Recipient user ID (for transfers)
            metadata: Additional metadata
            
        Returns:
            TransactionModel (existing or newly created)
        """
        # Try to insert with ON CONFLICT DO NOTHING
        stmt = pg_insert(TransactionModel).values(
            client_request_id=client_request_id,
            tx_type=tx_type,
            status=TransactionStatus.PENDING,
            amount=amount,
            currency=currency,
            user_id=user_id,
            recipient_user_id=recipient_user_id,
            tx_metadata=metadata or {},
            created_at=datetime.utcnow()
        ).on_conflict_do_nothing(
            index_elements=['client_request_id']
        ).returning(TransactionModel)
        
        result = self.db.execute(stmt)
        self.db.flush()
        
        # If insert succeeded, return the new transaction
        new_tx = result.scalar_one_or_none()
        if new_tx:
            return new_tx
        
        # Transaction already exists - fetch it
        existing = self.get_by_client_request_id(client_request_id)
        if existing:
            return existing
        
        # Should never reach here if ON CONFLICT worked correctly
        raise DuplicateTransactionError(
            client_request_id,
            "unknown"
        )

    def get_by_id(self, tx_id: UUID) -> Optional[TransactionModel]:
        """
        Get transaction by ID.
        
        Args:
            tx_id: Transaction UUID
            
        Returns:
            TransactionModel or None
        """
        return self.db.execute(
            select(TransactionModel).where(TransactionModel.id == tx_id)
        ).scalar_one_or_none()

    def get_by_client_request_id(
        self, 
        client_request_id: str
    ) -> Optional[TransactionModel]:
        """
        Get transaction by idempotency key.
        
        Args:
            client_request_id: Idempotency key
            
        Returns:
            TransactionModel or None
        """
        return self.db.execute(
            select(TransactionModel).where(
                TransactionModel.client_request_id == client_request_id
            )
        ).scalar_one_or_none()

    def get_by_external_reference(
        self, 
        external_reference: str
    ) -> Optional[TransactionModel]:
        """
        Get transaction by external payment provider reference.
        
        Args:
            external_reference: Provider's transaction ID
            
        Returns:
            TransactionModel or None
        """
        return self.db.execute(
            select(TransactionModel).where(
                TransactionModel.external_reference == external_reference
            )
        ).scalar_one_or_none()

    def update_status(
        self,
        tx_id: UUID,
        status: TransactionStatus,
        failure_reason: Optional[str] = None
    ) -> bool:
        """
        Update transaction status.
        
        Args:
            tx_id: Transaction UUID
            status: New status
            failure_reason: Optional failure reason if status is FAILED
            
        Returns:
            True if updated, False if not found
        """
        tx = self.get_by_id(tx_id)
        if not tx:
            return False
        
        tx.status = status
        
        if status == TransactionStatus.COMPLETED:
            tx.completed_at = datetime.utcnow()
        elif status == TransactionStatus.FAILED:
            tx.failed_at = datetime.utcnow()
            tx.failure_reason = failure_reason
        
        return True

    def get_user_transactions(
        self,
        user_id: int,
        tx_type: Optional[TransactionType] = None,
        status: Optional[TransactionStatus] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[TransactionModel]:
        """
        Get transactions for a user.
        
        Args:
            user_id: User ID
            tx_type: Optional transaction type filter
            status: Optional status filter
            limit: Maximum transactions
            offset: Pagination offset
            
        Returns:
            List of TransactionModel ordered by created_at DESC
        """
        query = select(TransactionModel).where(
            TransactionModel.user_id == user_id
        )
        
        if tx_type:
            query = query.where(TransactionModel.tx_type == tx_type)
        
        if status:
            query = query.where(TransactionModel.status == status)
        
        query = (
            query.order_by(TransactionModel.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        
        return self.db.execute(query).scalars().all()

    def get_transaction_count(
        self,
        user_id: int,
        tx_type: Optional[TransactionType] = None,
        status: Optional[TransactionStatus] = None
    ) -> int:
        """
        Get total transaction count for a user.
        
        Args:
            user_id: User ID
            tx_type: Optional transaction type filter
            status: Optional status filter
            
        Returns:
            Total count
        """
        from sqlalchemy import func
        
        query = select(func.count()).select_from(TransactionModel).where(
            TransactionModel.user_id == user_id
        )
        
        if tx_type:
            query = query.where(TransactionModel.tx_type == tx_type)
        
        if status:
            query = query.where(TransactionModel.status == status)
        
        return self.db.execute(query).scalar() or 0
