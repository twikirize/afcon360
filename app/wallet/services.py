# app/wallet/services.py
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from app.extensions import db
from app.wallet.models import Wallet, WalletTransaction, WalletLimit, WalletAuditLog, WalletType, WalletStatus, TransactionCategory
from app.identity.models.user import User
from sqlalchemy import and_, or_, func
import uuid
import logging


class WalletService:
    """Core wallet service - modular and shippable as separate product"""
    
    @staticmethod
    def create_wallet(user_id: int, name: str, wallet_type: WalletType, 
                    currency: str = "UGX", description: str = None,
                    organisation_id: int = None) -> Wallet:
        """Create new wallet"""
        
        # Generate unique public ID
        public_id = str(uuid.uuid4())
        
        # Get wallet limits for this type
        limits = WalletService.get_wallet_limits(wallet_type, currency)
        
        wallet = Wallet(
            public_id=public_id,
            user_id=user_id,
            organisation_id=organisation_id,
            name=name,
            description=description,
            wallet_type=wallet_type,
            currency=currency,
            daily_limit=limits.get('daily_limit'),
            monthly_limit=limits.get('monthly_limit'),
            transaction_limit=limits.get('transaction_limit'),
            requires_mfa=limits.get('requires_mfa', True),
            requires_pin=limits.get('requires_pin', True)
        )
        
        db.session.add(wallet)
        
        # Log wallet creation
        WalletService.audit_log(
            wallet_id=wallet.id,
            user_id=user_id,
            action="create",
            new_value={"name": name, "type": wallet_type.value, "currency": currency},
            reason="New wallet creation"
        )
        
        db.session.commit()
        return wallet
    
    @staticmethod
    def get_user_wallets(user_id: int, include_inactive: bool = False) -> List[Wallet]:
        """Get all wallets for user"""
        query = Wallet.query.filter_by(user_id=user_id)
        
        if not include_inactive:
            query = query.filter_by(status=WalletStatus.ACTIVE)
        
        return query.order_by(Wallet.created_at.desc()).all()
    
    @staticmethod
    def get_wallet_by_public_id(public_id: str, user_id: int = None) -> Optional[Wallet]:
        """Get wallet by public ID with optional user verification"""
        query = Wallet.query.filter_by(public_id=public_id)
        
        if user_id:
            query = query.filter_by(user_id=user_id)
        
        return query.first()
    
    @staticmethod
    def get_wallet_limits(wallet_type: WalletType, currency: str) -> Dict[str, Any]:
        """Get configured limits for wallet type and currency"""
        limits = WalletLimit.query.filter_by(
            wallet_type=wallet_type,
            currency=currency
        ).first()
        
        if not limits:
            # Default limits
            return {
                'min_transaction': 100.0,
                'max_transaction': 10000000.0,
                'daily_limit': 5000000.0,
                'weekly_limit': 10000000.0,
                'monthly_limit': 20000000.0,
                'requires_kyc_level': 2,
                'requires_mfa': True,
                'max_daily_transactions': 50
            }
        
        return {
            'min_transaction': limits.min_transaction,
            'max_transaction': limits.max_transaction,
            'daily_limit': limits.daily_limit,
            'weekly_limit': limits.weekly_limit,
            'monthly_limit': limits.monthly_limit,
            'requires_kyc_level': limits.requires_kyc_level,
            'requires_mfa': limits.requires_mfa,
            'max_daily_transactions': limits.max_daily_transactions
        }
    
    @staticmethod
    def initiate_transaction(from_wallet_id: int, amount: float, category: TransactionCategory,
                         description: str = None, to_wallet_id: int = None,
                         reference: str = None, metadata: Dict[str, Any] = None,
                         ip_address: str = None, user_agent: str = None,
                         device_id: str = None) -> Tuple[bool, str, Optional[WalletTransaction]]:
        """Initiate wallet transaction"""
        
        from_wallet = Wallet.query.get(from_wallet_id)
        if not from_wallet:
            return False, "Source wallet not found", None
        
        # Check wallet status
        if not from_wallet.is_active:
            return False, "Wallet is not active", None
        
        # Check limits
        can_transact, message = from_wallet.check_limits(amount, category.value)
        if not can_transact:
            return False, message, None
        
        # Check balance
        if from_wallet.available_balance < amount:
            return False, "Insufficient balance", None
        
        # Generate transaction ID
        transaction_id = f"WTX{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}{str(uuid.uuid4())[:8].upper()}"
        
        # Create transaction
        transaction = WalletTransaction(
            transaction_id=transaction_id,
            wallet_id=from_wallet_id,
            from_wallet_id=from_wallet_id,
            to_wallet_id=to_wallet_id,
            amount=amount,
            currency=from_wallet.currency,
            category=category,
            description=description,
            reference=reference,
            metadata=metadata or {},
            ip_address=ip_address,
            user_agent=user_agent,
            device_id=device_id,
            status="pending"
        )
        
        # Update wallet available balance
        from_wallet.available_balance -= amount
        
        db.session.add(transaction)
        db.session.flush()  # Get transaction ID
        
        # Log transaction initiation
        WalletService.audit_log(
            wallet_id=from_wallet_id,
            user_id=from_wallet.user_id,
            action="transaction_initiate",
            new_value={
                "transaction_id": transaction_id,
                "amount": amount,
                "category": category.value,
                "to_wallet_id": to_wallet_id
            },
            reason=f"Transaction initiated: {description or 'No description'}"
        )
        
        db.session.commit()
        return True, "Transaction initiated successfully", transaction
    
    @staticmethod
    def complete_transaction(transaction_id: str, metadata: Dict[str, Any] = None) -> Tuple[bool, str]:
        """Complete pending transaction"""
        
        transaction = WalletTransaction.query.filter_by(
            transaction_id=transaction_id,
            status="pending"
        ).first()
        
        if not transaction:
            return False, "Transaction not found or already processed", None
        
        wallet = Wallet.query.get(transaction.wallet_id)
        
        # Update transaction
        transaction.mark_completed()
        if metadata:
            if not transaction.metadata:
                transaction.metadata = {}
            transaction.metadata.update(metadata)
        
        # Update wallet balance
        wallet.balance -= transaction.amount
        wallet.last_activity = datetime.now(timezone.utc)
        
        # If transfer, update destination wallet
        if transaction.to_wallet_id and transaction.category == TransactionCategory.TRANSFER:
            to_wallet = Wallet.query.get(transaction.to_wallet_id)
            if to_wallet:
                to_wallet.balance += transaction.amount
                to_wallet.last_activity = datetime.now(timezone.utc)
                db.session.add(to_wallet)
        
        # Log completion
        WalletService.audit_log(
            wallet_id=wallet.id,
            user_id=wallet.user_id,
            action="transaction_complete",
            old_value={"balance": wallet.balance + transaction.amount},
            new_value={"balance": wallet.balance},
            reason=f"Transaction completed: {transaction.description or 'No description'}"
        )
        
        db.session.commit()
        return True, "Transaction completed successfully"
    
    @staticmethod
    def freeze_wallet(wallet_id: int, amount: float, reason: str, user_id: int) -> Tuple[bool, str]:
        """Freeze amount in wallet"""
        
        wallet = Wallet.query.get(wallet_id)
        if not wallet:
            return False, "Wallet not found"
        
        if wallet.available_balance < amount:
            return False, "Insufficient available balance"
        
        wallet.freeze_amount(amount, reason)
        
        WalletService.audit_log(
            wallet_id=wallet_id,
            user_id=user_id,
            action="freeze",
            old_value={"frozen_balance": wallet.frozen_balance - amount},
            new_value={"frozen_balance": wallet.frozen_balance},
            reason=reason
        )
        
        db.session.commit()
        return True, "Amount frozen successfully"
    
    @staticmethod
    def unfreeze_wallet(wallet_id: int, amount: float, user_id: int) -> Tuple[bool, str]:
        """Unfreeze amount in wallet"""
        
        wallet = Wallet.query.get(wallet_id)
        if not wallet:
            return False, "Wallet not found"
        
        if wallet.frozen_balance < amount:
            return False, "Insufficient frozen balance"
        
        wallet.unfreeze_amount(amount)
        
        WalletService.audit_log(
            wallet_id=wallet_id,
            user_id=user_id,
            action="unfreeze",
            old_value={"frozen_balance": wallet.frozen_balance + amount},
            new_value={"frozen_balance": wallet.frozen_balance},
            reason="Amount unfrozen"
        )
        
        db.session.commit()
        return True, "Amount unfrozen successfully"
    
    @staticmethod
    def get_wallet_balance(wallet_id: int) -> Dict[str, float]:
        """Get detailed wallet balance information"""
        
        wallet = Wallet.query.get(wallet_id)
        if not wallet:
            return {}
        
        return {
            "total_balance": float(wallet.balance),
            "available_balance": float(wallet.available_balance),
            "frozen_balance": float(wallet.frozen_balance),
            "currency": wallet.currency
        }
    
    @staticmethod
    def get_transaction_history(wallet_id: int, limit: int = 50, offset: int = 0,
                              status: str = None, category: str = None) -> List[WalletTransaction]:
        """Get wallet transaction history"""
        
        query = WalletTransaction.query.filter_by(wallet_id=wallet_id)
        
        if status:
            query = query.filter_by(status=status)
        
        if category:
            query = query.filter_by(category=category)
        
        return query.order_by(WalletTransaction.initiated_at.desc()).offset(offset).limit(limit).all()
    
    @staticmethod
    def audit_log(wallet_id: int, user_id: int, action: str,
                 old_value: Dict[str, Any] = None, new_value: Dict[str, Any] = None,
                 reason: str = None, ip_address: str = None, user_agent: str = None):
        """Create audit log entry"""
        
        audit_log = WalletAuditLog(
            wallet_id=wallet_id,
            user_id=user_id,
            action=action,
            old_value=old_value,
            new_value=new_value,
            reason=reason,
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        db.session.add(audit_log)
    
    @staticmethod
    def get_wallet_statistics(wallet_id: int, days: int = 30) -> Dict[str, Any]:
        """Get wallet statistics for specified period"""
        
        wallet = Wallet.query.get(wallet_id)
        if not wallet:
            return {}
        
        start_date = datetime.now(timezone.utc) - timedelta(days=days)
        
        # Transaction statistics
        transactions = WalletTransaction.query.filter(
            and_(
                WalletTransaction.wallet_id == wallet_id,
                WalletTransaction.initiated_at >= start_date,
                WalletTransaction.status == "completed"
            )
        ).all()
        
        total_sent = sum(t.amount for t in transactions if t.category in [TransactionCategory.TRANSFER, TransactionCategory.PAYMENT, TransactionCategory.WITHDRAWAL])
        total_received = sum(t.amount for t in transactions if t.category in [TransactionCategory.DEPOSIT])
        total_fees = sum(t.fee_amount for t in transactions)
        
        # Category breakdown
        category_stats = {}
        for transaction in transactions:
            cat = transaction.category.value
            if cat not in category_stats:
                category_stats[cat] = {"count": 0, "total": 0.0}
            category_stats[cat]["count"] += 1
            category_stats[cat]["total"] += float(transaction.amount)
        
        return {
            "wallet_id": wallet_id,
            "wallet_name": wallet.name,
            "currency": wallet.currency,
            "period_days": days,
            "total_transactions": len(transactions),
            "total_sent": float(total_sent),
            "total_received": float(total_received),
            "total_fees": float(total_fees),
            "current_balance": float(wallet.balance),
            "available_balance": float(wallet.available_balance),
            "frozen_balance": float(wallet.frozen_balance),
            "category_breakdown": category_stats
        }
    
    @staticmethod
    def update_wallet_settings(wallet_id: int, settings: Dict[str, Any], user_id: int) -> Tuple[bool, str]:
        """Update wallet settings"""
        
        wallet = Wallet.query.get(wallet_id)
        if not wallet:
            return False, "Wallet not found"
        
        old_metadata = wallet.metadata.copy() if wallet.metadata else {}
        
        if not wallet.metadata:
            wallet.metadata = {}
        
        wallet.metadata.update(settings)
        wallet.updated_at = datetime.now(timezone.utc)
        
        # Log settings update
        WalletService.audit_log(
            wallet_id=wallet_id,
            user_id=user_id,
            action="settings_update",
            old_value=old_metadata,
            new_value=wallet.metadata,
            reason="Wallet settings updated"
        )
        
        db.session.commit()
        return True, "Wallet settings updated successfully"
    
    @staticmethod
    def close_wallet(wallet_id: int, reason: str, user_id: int) -> Tuple[bool, str]:
        """Close wallet"""
        
        wallet = Wallet.query.get(wallet_id)
        if not wallet:
            return False, "Wallet not found"
        
        if wallet.balance != 0:
            return False, "Cannot close wallet with non-zero balance"
        
        old_status = wallet.status
        wallet.status = WalletStatus.CLOSED
        wallet.updated_at = datetime.now(timezone.utc)
        
        # Log wallet closure
        WalletService.audit_log(
            wallet_id=wallet_id,
            user_id=user_id,
            action="close",
            old_value={"status": old_status.value},
            new_value={"status": wallet.status.value},
            reason=reason
        )
        
        db.session.commit()
        return True, "Wallet closed successfully"


class WalletLimitService:
    """Service for managing wallet limits"""
    
    @staticmethod
    def update_limits(wallet_type: WalletType, currency: str, limits: Dict[str, Any]) -> Tuple[bool, str]:
        """Update wallet limits"""
        
        limit_record = WalletLimit.query.filter_by(
            wallet_type=wallet_type,
            currency=currency
        ).first()
        
        if not limit_record:
            limit_record = WalletLimit(
                wallet_type=wallet_type,
                currency=currency,
                **limits
            )
            db.session.add(limit_record)
        else:
            for key, value in limits.items():
                if hasattr(limit_record, key):
                    setattr(limit_record, key, value)
            limit_record.updated_at = datetime.now(timezone.utc)
        
        db.session.commit()
        return True, "Limits updated successfully"
    
    @staticmethod
    def get_all_limits() -> List[WalletLimit]:
        """Get all wallet limits"""
        return WalletLimit.query.order_by(WalletLimit.wallet_type, WalletLimit.currency).all()
