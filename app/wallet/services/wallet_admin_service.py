"""
app/wallet/services/wallet_admin_service.py
Admin service for wallet management operations.
Provides freeze/unfreeze, balance adjustment, and wallet listing for admins.
"""

from decimal import Decimal
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from flask import current_app, request
from sqlalchemy import func, and_, or_
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.wallet.models import Wallet as WalletModel, Transaction as TransactionModel
from app.wallet.repositories.wallet_repository import WalletRepository
from app.wallet.services.wallet_service import WalletService
from app.wallet.exceptions import WalletNotFoundError, WalletFrozenError, WalletError
from app.audit.comprehensive_audit import AuditService, AuditSeverity, DataAccessType


class WalletAdminService:
    """
    Admin service for wallet management.

    Features:
    - List all wallets with filtering and pagination
    - Get wallet details for any user
    - Freeze/unfreeze wallets with reason
    - Manual balance adjustment (with audit)
    - Wallet statistics and analytics
    """

    def __init__(self):
        self.wallet_repo = WalletRepository()
        self.wallet_service = WalletService()

    def list_all_wallets(
            self,
            page: int = 1,
            per_page: int = 50,
            search: Optional[str] = None,
            status: Optional[str] = None,
            verified: Optional[bool] = None,
            frozen: Optional[bool] = None,
            sort_by: str = "created_at",
            sort_order: str = "desc"
    ) -> Dict[str, Any]:
        """
        List all wallets with pagination and filters.

        Args:
            page: Page number
            per_page: Items per page
            search: Search by username, email, or wallet_ref
            status: Filter by status (active, inactive)
            verified: Filter by verification status
            frozen: Filter by frozen status
            sort_by: Sort field (balance_home, balance_local, created_at, updated_at)
            sort_order: asc or desc

        Returns:
            Dict with wallets, pagination info, and totals
        """
        try:
            query = WalletModel.query

            # Join with User to get user details
            from app.identity.models.user import User
            query = query.outerjoin(User, WalletModel.user_id == User.id)

            # Apply search filter
            if search:
                search_term = f"%{search}%"
                query = query.filter(
                    or_(
                        User.username.ilike(search_term),
                        User.email.ilike(search_term),
                        WalletModel.wallet_ref.ilike(search_term)
                    )
                )

            # Apply status filter (based on user is_active)
            if status == "active":
                query = query.filter(User.is_active == True)
            elif status == "inactive":
                query = query.filter(User.is_active == False)

            # Apply verified filter
            if verified is not None:
                query = query.filter(WalletModel.verified == verified)

            # Apply frozen filter
            if frozen is not None:
                query = query.filter(WalletModel.is_frozen == frozen)

            # Apply sorting
            if sort_by == "balance_home":
                order_col = WalletModel.balance_home
            elif sort_by == "balance_local":
                order_col = WalletModel.balance_local
            elif sort_by == "created_at":
                order_col = WalletModel.created_at
            elif sort_by == "updated_at":
                order_col = WalletModel.updated_at
            else:
                order_col = WalletModel.created_at

            if sort_order == "asc":
                query = query.order_by(order_col.asc())
            else:
                query = query.order_by(order_col.desc())

            # Get totals for statistics
            total_wallets = WalletModel.query.count()
            total_frozen = WalletModel.query.filter_by(is_frozen=True).count()
            total_verified = WalletModel.query.filter_by(verified=True).count()
            total_balance_home = db.session.query(func.sum(WalletModel.balance_home)).scalar() or 0
            total_balance_local = db.session.query(func.sum(WalletModel.balance_local)).scalar() or 0

            # Paginate
            paginated = query.paginate(page=page, per_page=per_page, error_out=False)

            # Build response
            wallets = []
            for wallet in paginated.items:
                from app.identity.models.user import User
                user = User.query.get(wallet.user_id) if wallet.user_id else None

                wallets.append({
                    "id": wallet.id,
                    "user_id": wallet.user_id,
                    "username": user.username if user else None,
                    "email": user.email if user else None,
                    "wallet_ref": wallet.wallet_ref,
                    "balance_home": str(wallet.balance_home),
                    "balance_local": str(wallet.balance_local),
                    "home_currency": wallet.home_currency,
                    "local_currency": wallet.local_currency,
                    "verified": wallet.verified,
                    "is_frozen": wallet.is_frozen,
                    "frozen_reason": wallet.frozen_reason,
                    "frozen_at": wallet.frozen_at.isoformat() if wallet.frozen_at else None,
                    "created_at": wallet.created_at.isoformat(),
                    "updated_at": wallet.updated_at.isoformat(),
                })

            return {
                "wallets": wallets,
                "total": paginated.total,
                "page": page,
                "per_page": per_page,
                "pages": paginated.pages,
                "has_prev": paginated.has_prev,
                "has_next": paginated.has_next,
                "stats": {
                    "total_wallets": total_wallets,
                    "total_frozen": total_frozen,
                    "total_verified": total_verified,
                    "total_balance_home": str(total_balance_home),
                    "total_balance_local": str(total_balance_local),
                }
            }

        except Exception as e:
            current_app.logger.error(f"Error listing wallets: {e}")
            raise WalletError(f"Failed to list wallets: {str(e)}")

    def get_wallet_details(self, user_id: int) -> Dict[str, Any]:
        """
        Get detailed wallet information for a specific user.

        Args:
            user_id: User ID

        Returns:
            Dict with wallet details, transactions, and statistics
        """
        try:
            wallet = self.wallet_repo.get_by_user_id(user_id)

            if not wallet:
                raise WalletNotFoundError(user_id=user_id)

            from app.identity.models.user import User
            user = User.query.get(user_id)

            # Get transaction statistics
            thirty_days_ago = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

            # Deposit total (last 30 days)
            deposit_total = db.session.query(func.sum(TransactionModel.amount)).filter(
                TransactionModel.wallet_id == wallet.id,
                TransactionModel.type == "deposit",
                TransactionModel.created_at >= thirty_days_ago
            ).scalar() or 0

            # Withdrawal total (last 30 days)
            withdrawal_total = db.session.query(func.sum(TransactionModel.amount)).filter(
                TransactionModel.wallet_id == wallet.id,
                TransactionModel.type == "withdrawal",
                TransactionModel.created_at >= thirty_days_ago
            ).scalar() or 0

            # Transfer totals
            sent_total = db.session.query(func.sum(TransactionModel.amount)).filter(
                TransactionModel.wallet_id == wallet.id,
                TransactionModel.type == "send",
                TransactionModel.created_at >= thirty_days_ago
            ).scalar() or 0

            received_total = db.session.query(func.sum(TransactionModel.amount)).filter(
                TransactionModel.wallet_id == wallet.id,
                TransactionModel.type == "receive",
                TransactionModel.created_at >= thirty_days_ago
            ).scalar() or 0

            # Transaction count
            transaction_count = TransactionModel.query.filter_by(wallet_id=wallet.id).count()

            # Recent transactions
            recent_transactions = TransactionModel.query.filter_by(
                wallet_id=wallet.id
            ).order_by(
                TransactionModel.created_at.desc()
            ).limit(20).all()

            return {
                "wallet": {
                    "id": wallet.id,
                    "user_id": wallet.user_id,
                    "username": user.username if user else None,
                    "email": user.email if user else None,
                    "wallet_ref": wallet.wallet_ref,
                    "balance_home": str(wallet.balance_home),
                    "balance_local": str(wallet.balance_local),
                    "home_currency": wallet.home_currency,
                    "local_currency": wallet.local_currency,
                    "verified": wallet.verified,
                    "is_frozen": wallet.is_frozen,
                    "frozen_reason": wallet.frozen_reason,
                    "frozen_at": wallet.frozen_at.isoformat() if wallet.frozen_at else None,
                    "nationality": wallet.nationality,
                    "location": wallet.location,
                    "created_at": wallet.created_at.isoformat(),
                    "updated_at": wallet.updated_at.isoformat(),
                },
                "statistics": {
                    "deposit_total_30d": str(deposit_total),
                    "withdrawal_total_30d": str(withdrawal_total),
                    "sent_total_30d": str(sent_total),
                    "received_total_30d": str(received_total),
                    "transaction_count": transaction_count,
                },
                "recent_transactions": [
                    {
                        "id": t.tx_id or str(t.id),
                        "type": t.type,
                        "amount": str(t.amount),
                        "currency": t.currency,
                        "created_at": t.created_at.isoformat(),
                        "meta": t.meta,
                    }
                    for t in recent_transactions
                ]
            }

        except WalletNotFoundError:
            raise
        except Exception as e:
            current_app.logger.error(f"Error getting wallet details for user {user_id}: {e}")
            raise WalletError(f"Failed to get wallet details: {str(e)}")

    def freeze_wallet(
            self,
            user_id: int,
            admin_user_id: int,
            reason: str,
            notes: Optional[str] = None
    ) -> bool:
        """
        Freeze a wallet, preventing all transactions.

        Args:
            user_id: User ID of wallet owner
            admin_user_id: Admin user ID performing the action
            reason: Reason for freezing
            notes: Additional notes

        Returns:
            True if successful
        """
        from flask import request

        try:
            wallet = self.wallet_repo.get_by_user_id(user_id, for_update=True)

            if not wallet:
                raise WalletNotFoundError(user_id=user_id)

            if wallet.is_frozen:
                raise WalletFrozenError(wallet.wallet_ref or str(wallet.id), "Wallet is already frozen")

            # Update wallet
            wallet.is_frozen = True
            wallet.frozen_reason = reason
            wallet.frozen_at = datetime.utcnow()

            db.session.commit()

            # Audit the freeze action
            try:
                AuditService.security(
                    event_type="wallet_frozen",
                    severity=AuditSeverity.WARNING,
                    description=f"Wallet for user {user_id} frozen by admin {admin_user_id}. Reason: {reason}",
                    user_id=user_id,
                    ip_address=request.remote_addr if request else None,
                    metadata={
                        "admin_user_id": admin_user_id,
                        "reason": reason,
                        "notes": notes,
                        "wallet_id": wallet.id,
                        "wallet_ref": wallet.wallet_ref
                    }
                )
            except Exception as e:
                current_app.logger.error(f"Failed to audit wallet freeze: {e}")

            current_app.logger.warning(
                f"Wallet for user {user_id} frozen by admin {admin_user_id}. Reason: {reason}"
            )

            return True

        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"Database error freezing wallet for user {user_id}: {e}")
            raise WalletError(f"Failed to freeze wallet: {str(e)}")

    def unfreeze_wallet(
            self,
            user_id: int,
            admin_user_id: int,
            reason: Optional[str] = None
    ) -> bool:
        """
        Unfreeze a wallet, restoring transaction capabilities.

        Args:
            user_id: User ID of wallet owner
            admin_user_id: Admin user ID performing the action
            reason: Reason for unfreezing

        Returns:
            True if successful
        """
        from flask import request

        try:
            wallet = self.wallet_repo.get_by_user_id(user_id, for_update=True)

            if not wallet:
                raise WalletNotFoundError(user_id=user_id)

            if not wallet.is_frozen:
                raise WalletError("Wallet is not frozen")

            # Update wallet
            wallet.is_frozen = False
            wallet.frozen_reason = None
            wallet.frozen_at = None

            db.session.commit()

            # Audit the unfreeze action
            try:
                AuditService.security(
                    event_type="wallet_unfrozen",
                    severity=AuditSeverity.INFO,
                    description=f"Wallet for user {user_id} unfrozen by admin {admin_user_id}. Reason: {reason or 'No reason provided'}",
                    user_id=user_id,
                    ip_address=request.remote_addr if request else None,
                    metadata={
                        "admin_user_id": admin_user_id,
                        "reason": reason,
                        "wallet_id": wallet.id,
                        "wallet_ref": wallet.wallet_ref
                    }
                )
            except Exception as e:
                current_app.logger.error(f"Failed to audit wallet unfreeze: {e}")

            current_app.logger.info(
                f"Wallet for user {user_id} unfrozen by admin {admin_user_id}"
            )

            return True

        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"Database error unfreezing wallet for user {user_id}: {e}")
            raise WalletError(f"Failed to unfreeze wallet: {str(e)}")

    def adjust_balance(
            self,
            user_id: int,
            admin_user_id: int,
            amount: Decimal,
            currency: str,
            reason: str,
            notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Manually adjust wallet balance (admin only, with audit).

        Args:
            user_id: User ID of wallet owner
            admin_user_id: Admin user ID performing the action
            amount: Amount to adjust (positive for credit, negative for debit)
            currency: Currency to adjust (home or local)
            reason: Reason for adjustment
            notes: Additional notes

        Returns:
            Dict with new balances
        """
        from flask import request

        try:
            wallet = self.wallet_repo.get_by_user_id(user_id, for_update=True)

            if not wallet:
                raise WalletNotFoundError(user_id=user_id)

            if wallet.is_frozen:
                raise WalletFrozenError(wallet.wallet_ref or str(wallet.id), wallet.frozen_reason)

            # Capture balances before
            home_balance_before = wallet.balance_home
            local_balance_before = wallet.balance_local

            # Determine which balance to adjust
            if currency.upper() == wallet.home_currency:
                new_home_balance = wallet.balance_home + amount
                new_local_balance = wallet.balance_local
                if new_home_balance < 0:
                    raise ValueError(f"Cannot adjust below zero. Current balance: {wallet.balance_home}")
                wallet.balance_home = new_home_balance
                adjustment_type = "home_currency_adjustment"
            elif currency.upper() == wallet.local_currency:
                new_local_balance = wallet.balance_local + amount
                new_home_balance = wallet.balance_home
                if new_local_balance < 0:
                    raise ValueError(f"Cannot adjust below zero. Current balance: {wallet.balance_local}")
                wallet.balance_local = new_local_balance
                adjustment_type = "local_currency_adjustment"
            else:
                raise ValueError(
                    f"Currency {currency} not supported. Use {wallet.home_currency} or {wallet.local_currency}")

            # Increment version for optimistic lock
            wallet.version += 1
            wallet.updated_at = datetime.utcnow()

            db.session.commit()

            # Create transaction record for the adjustment
            import uuid
            tx_id = f"ADJ-{uuid.uuid4().hex[:12].upper()}"

            transaction = TransactionModel(
                wallet_id=wallet.id,
                tx_id=tx_id,
                type="admin_adjustment",
                amount=abs(amount),
                currency=currency,
                meta={
                    "adjustment_type": adjustment_type,
                    "admin_user_id": admin_user_id,
                    "reason": reason,
                    "notes": notes,
                    "amount": str(amount),
                    "balance_before_home": str(home_balance_before),
                    "balance_before_local": str(local_balance_before),
                    "balance_after_home": str(new_home_balance),
                    "balance_after_local": str(new_local_balance),
                }
            )
            db.session.add(transaction)
            db.session.commit()

            # Audit the adjustment
            try:
                severity = AuditSeverity.WARNING if amount < 0 else AuditSeverity.INFO
                AuditService.security(
                    event_type="wallet_balance_adjustment",
                    severity=severity,
                    description=f"Wallet balance adjusted by admin {admin_user_id}. Amount: {amount} {currency}. Reason: {reason}",
                    user_id=user_id,
                    ip_address=request.remote_addr if request else None,
                    metadata={
                        "admin_user_id": admin_user_id,
                        "amount": str(amount),
                        "currency": currency,
                        "reason": reason,
                        "notes": notes,
                        "balance_before_home": str(home_balance_before),
                        "balance_before_local": str(local_balance_before),
                        "balance_after_home": str(new_home_balance),
                        "balance_after_local": str(new_local_balance),
                        "transaction_id": tx_id
                    }
                )
            except Exception as e:
                current_app.logger.error(f"Failed to audit balance adjustment: {e}")

            current_app.logger.warning(
                f"Wallet for user {user_id} adjusted by admin {admin_user_id}: {amount} {currency}. Reason: {reason}"
            )

            return {
                "success": True,
                "transaction_id": tx_id,
                "new_balance_home": str(new_home_balance),
                "new_balance_local": str(new_local_balance),
                "amount_adjusted": str(amount),
                "currency": currency
            }

        except (WalletNotFoundError, WalletFrozenError, ValueError) as e:
            raise
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"Database error adjusting balance for user {user_id}: {e}")
            raise WalletError(f"Failed to adjust balance: {str(e)}")

    def get_wallet_stats(self) -> Dict[str, Any]:
        """
        Get comprehensive wallet statistics for admin dashboard.

        Returns:
            Dict with various wallet statistics
        """
        try:
            from datetime import datetime, timedelta

            today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            week_ago = today - timedelta(days=7)
            month_ago = today - timedelta(days=30)

            # Basic counts
            total_wallets = WalletModel.query.count()
            frozen_wallets = WalletModel.query.filter_by(is_frozen=True).count()
            verified_wallets = WalletModel.query.filter_by(verified=True).count()
            unverified_wallets = total_wallets - verified_wallets

            # Balance totals
            balance_result = db.session.query(
                func.sum(WalletModel.balance_home).label('total_home'),
                func.sum(WalletModel.balance_local).label('total_local')
            ).first()

            # New wallets this week/month
            new_wallets_week = WalletModel.query.filter(WalletModel.created_at >= week_ago).count()
            new_wallets_month = WalletModel.query.filter(WalletModel.created_at >= month_ago).count()

            # Transaction volume by type
            volume_by_type = db.session.query(
                TransactionModel.type,
                func.sum(TransactionModel.amount).label('total'),
                func.count(TransactionModel.id).label('count')
            ).filter(
                TransactionModel.created_at >= month_ago
            ).group_by(TransactionModel.type).all()

            volume_by_currency = db.session.query(
                TransactionModel.currency,
                func.sum(TransactionModel.amount).label('total'),
                func.count(TransactionModel.id).label('count')
            ).filter(
                TransactionModel.created_at >= month_ago
            ).group_by(TransactionModel.currency).all()

            # Daily transaction volume (last 7 days)
            daily_volume = []
            for i in range(7):
                day_start = today - timedelta(days=i)
                day_end = day_start + timedelta(days=1)
                day_volume = db.session.query(
                    func.sum(TransactionModel.amount).label('total')
                ).filter(
                    TransactionModel.created_at >= day_start,
                    TransactionModel.created_at < day_end
                ).scalar() or 0

                daily_volume.append({
                    "date": day_start.strftime("%Y-%m-%d"),
                    "volume": str(day_volume)
                })

            # Top users by balance
            top_users_by_balance = WalletModel.query.order_by(
                WalletModel.balance_home.desc()
            ).limit(10).all()

            top_users = []
            for wallet in top_users_by_balance:
                from app.identity.models.user import User
                user = User.query.get(wallet.user_id) if wallet.user_id else None
                top_users.append({
                    "user_id": wallet.user_id,
                    "username": user.username if user else "Unknown",
                    "balance_home": str(wallet.balance_home),
                    "balance_local": str(wallet.balance_local)
                })

            return {
                "total_wallets": total_wallets,
                "frozen_wallets": frozen_wallets,
                "verified_wallets": verified_wallets,
                "unverified_wallets": unverified_wallets,
                "total_balance_home": str(balance_result.total_home or 0),
                "total_balance_local": str(balance_result.total_local or 0),
                "new_wallets_week": new_wallets_week,
                "new_wallets_month": new_wallets_month,
                "volume_by_type": [
                    {"type": v.type, "total": str(v.total or 0), "count": v.count}
                    for v in volume_by_type
                ],
                "volume_by_currency": [
                    {"currency": v.currency, "total": str(v.total or 0), "count": v.count}
                    for v in volume_by_currency
                ],
                "daily_volume_last_7_days": daily_volume,
                "top_users_by_balance": top_users
            }

        except Exception as e:
            current_app.logger.error(f"Error getting wallet stats: {e}")
            raise WalletError(f"Failed to get wallet statistics: {str(e)}")