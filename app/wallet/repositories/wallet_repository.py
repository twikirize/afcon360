"""
app/wallet/repositories/wallet_repository.py
Database operations for Wallet model.

This repository wraps the existing WalletModel from models.py.
It does NOT change how data is stored - just provides a clean interface.
"""

from decimal import Decimal
from typing import Optional, Tuple, Dict, Any
from datetime import datetime, date
from sqlalchemy import update, select
from sqlalchemy.orm import Session
from app.extensions import db
from app.wallet.models import Wallet as WalletModel
from app.wallet.exceptions import WalletNotFoundError, WalletFrozenError


class WalletRepository:
    """
    Repository for wallet database operations.

    All methods work with the existing WalletModel. No schema changes required yet.
    """

    def __init__(self, db_session: Session = None):
        """
        Initialize repository with database session.

        Args:
            db_session: SQLAlchemy session (defaults to db.session)
        """
        self.db = db_session or db.session

    def get_by_user_id(self, user_id: int, for_update: bool = False) -> Optional[WalletModel]:
        """
        Get wallet by user ID.

        Args:
            user_id: Internal user ID (BIGINT from users table)
            for_update: If True, locks the row for update (SELECT ... FOR UPDATE)

        Returns:
            WalletModel instance or None if not found
        """
        query = select(WalletModel).where(WalletModel.user_id == user_id)

        if for_update:
            query = query.with_for_update()

        return self.db.execute(query).scalar_one_or_none()

    def get_by_org_id(self, org_id: int, for_update: bool = False) -> Optional[WalletModel]:
        """
        Get wallet by organisation ID.

        Args:
            org_id: Internal organisation ID
            for_update: If True, locks the row for update

        Returns:
            WalletModel instance or None if not found
        """
        query = select(WalletModel).where(WalletModel.organisation_id == org_id)

        if for_update:
            query = query.with_for_update()

        return self.db.execute(query).scalar_one_or_none()

    def get_or_create_by_user_id(self, user_id: int) -> WalletModel:
        """
        Get wallet by user ID, creating one if it doesn't exist.

        Args:
            user_id: Internal user ID

        Returns:
            WalletModel instance (new or existing)
        """
        wallet = self.get_by_user_id(user_id, for_update=True)

        if wallet:
            return wallet

        # Create new wallet
        wallet = WalletModel(
            user_id=user_id,
            home_currency="USD",
            local_currency="UGX",
            balance_home=Decimal("0"),
            balance_local=Decimal("0"),
        )
        self.db.add(wallet)
        self.db.flush()  # Get ID without committing

        return wallet

    def get_or_create_by_org_id(self, org_id: int) -> WalletModel:
        """
        Get wallet by organisation ID, creating one if it doesn't exist.

        Args:
            org_id: Internal organisation ID

        Returns:
            WalletModel instance (new or existing)
        """
        wallet = self.get_by_org_id(org_id, for_update=True)

        if wallet:
            return wallet

        # Create new wallet
        wallet = WalletModel(
            organisation_id=org_id,
            home_currency="USD",
            local_currency="UGX",
            balance_home=Decimal("0"),
            balance_local=Decimal("0"),
        )
        self.db.add(wallet)
        self.db.flush()

        return wallet

    def update_balance(
            self,
            wallet_id: int,
            amount_home_delta: Decimal,
            amount_local_delta: Decimal,
            expected_version: int
    ) -> Tuple[bool, Optional[WalletModel]]:
        """
        Atomically update wallet balance with version check (optimistic locking).

        Args:
            wallet_id: Wallet ID to update
            amount_home_delta: Change to home balance (positive or negative)
            amount_local_delta: Change to local balance (positive or negative)
            expected_version: Expected version number (for optimistic lock)

        Returns:
            Tuple of (success, updated_wallet)
            success=True if update succeeded, False if version mismatch
        """
        # Atomic update with version check
        result = self.db.execute(
            update(WalletModel)
            .where(
                WalletModel.id == wallet_id,
                WalletModel.version == expected_version
            )
            .values(
                balance_home=WalletModel.balance_home + amount_home_delta,
                balance_local=WalletModel.balance_local + amount_local_delta,
                version=WalletModel.version + 1,
                updated_at=datetime.utcnow()
            )
        )

        if result.rowcount == 0:
            # Version mismatch - someone else updated
            return False, None

        # Refresh the updated wallet
        wallet = self.db.execute(
            select(WalletModel).where(WalletModel.id == wallet_id)
        ).scalar_one()

        return True, wallet

    def get_balance_summary(self, user_id: int) -> Dict[str, Any]:
        """
        Get balance summary for a user.

        Args:
            user_id: Internal user ID

        Returns:
            Dict with balance information
        """
        wallet = self.get_by_user_id(user_id)

        if not wallet:
            return {
                "exists": False,
                "balance_home": "0.00",
                "balance_local": "0.00",
                "home_currency": "USD",
                "local_currency": "UGX",
                "verified": False,
            }

        return {
            "exists": True,
            "wallet_id": wallet.id,
            "balance_home": str(wallet.balance_home),
            "balance_local": str(wallet.balance_local),
            "home_currency": wallet.home_currency,
            "local_currency": wallet.local_currency,
            "verified": wallet.verified,
            "updated_at": wallet.updated_at.isoformat() if wallet.updated_at else None,
        }

    def check_frozen(self, user_id: int = None, org_id: int = None) -> bool:
        """
        Check if wallet is frozen.

        Note: This reads the 'is_frozen' column we'll add later.
        For now, returns False (not frozen).
        """
        # TODO: After adding is_frozen column to WalletModel, implement this
        # For now, assume not frozen
        return False

    def get_frozen_reason(self, user_id: int = None, org_id: int = None) -> Optional[str]:
        """Get reason wallet is frozen, if any."""
        # TODO: Implement after adding frozen_reason column
        return None

    def record_daily_volume(
            self,
            wallet_id: int,
            amount_home: Decimal,
            amount_local: Decimal
    ) -> None:
        """
        Record transaction volume for daily limit tracking.

        TODO: Implement after adding daily_volume columns to WalletModel
        """
        # Placeholder - will implement in Phase 2
        pass

    def get_daily_volume(self, wallet_id: int) -> Dict[str, Decimal]:
        """
        Get today's transaction volume.

        TODO: Implement after adding daily_volume columns
        """
        return {"home": Decimal("0"), "local": Decimal("0")}
