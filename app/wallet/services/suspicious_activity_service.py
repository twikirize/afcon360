"""
Suspicious activity monitoring and fraud alert service.

Detects anomalous transaction patterns, creates fraud alerts, and
notifies users and admins of potentially fraudulent activity.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from flask import current_app
from flask_login import current_user

from app.extensions import db
from app.wallet.models.transaction import TransactionModel, TransactionStatus
from app.wallet.models.ledger import AccountModel
from app.wallet.models.audit import AuditLogModel
from app.identity.models.user import User


class SuspiciousActivityService:
    """
    Service for monitoring suspicious transaction patterns.
    
    Analyzes transaction history, user behavior, and risk factors
    to detect potential fraud.
    """

    @classmethod
    def analyze_transaction(
        cls,
        user_id: int,
        amount: Decimal,
        currency: str,
        recipient_id: Optional[int] = None,
        ip_address: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Analyze a transaction for suspicious patterns.
        
        Returns:
            Dict with 'risk_score', 'patterns', 'status', and 'action'
        """
        risk_score = 0
        patterns = []
        
        # 1. Large transaction relative to user history
        avg_amount = cls._get_average_transaction_amount(user_id, currency)
        if avg_amount > 0 and amount > avg_amount * Decimal('3'):
            risk_score += 20
            patterns.append('amount_3x_avg')
        
        # 2. New recipient (for transfers)
        if recipient_id and cls._is_new_recipient(user_id, recipient_id):
            risk_score += 15
            patterns.append('new_recipient')
        
        # 3. Rapid consecutive transactions
        recent_count = cls._get_recent_transaction_count(user_id, minutes=5)
        if recent_count > 5:
            risk_score += 25
            patterns.append('rapid_transactions')
        
        # 4. New device / IP (simplified)
        if ip_address and cls._is_new_ip(user_id, ip_address):
            risk_score += 10
            patterns.append('new_device')
        
        # 5. Off-hours transaction
        if cls._is_off_hours():
            risk_score += 10
            patterns.append('off_hours')
        
        # 6. KYC level vs amount
        kyc_level = cls._get_user_kyc_level(user_id)
        kyc_limit = cls._get_kyc_per_txn_limit(kyc_level)
        if kyc_limit > 0 and amount > kyc_limit:
            risk_score += 20
            patterns.append('amount_exceeds_kyc')
        
        # Determine status
        if risk_score >= 70:
            status = 'block'
        elif risk_score >= 50:
            status = 'flag'
        elif risk_score >= 30:
            status = 'monitor'
        else:
            status = 'normal'
        
        return {
            'risk_score': risk_score,
            'patterns': patterns,
            'status': status,
            'action': 'block' if risk_score >= 70 else 'review' if risk_score >= 50 else 'allow'
        }

    @classmethod
    def _get_average_transaction_amount(cls, user_id: int, currency: str) -> Decimal:
        """Get average transaction amount for user in currency."""
        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
        
        result = db.session.query(
            db.func.avg(TransactionModel.amount)
        ).filter(
            TransactionModel.user_id == user_id,
            TransactionModel.currency == currency,
            TransactionModel.status == TransactionStatus.COMPLETED,
            TransactionModel.created_at >= thirty_days_ago
        ).scalar()
        
        return Decimal(str(result)) if result else Decimal('0')

    @classmethod
    def _is_new_recipient(cls, user_id: int, recipient_id: int) -> bool:
        """Check if recipient is new to user."""
        recent = db.session.query(TransactionModel).filter(
            db.or_(
                db.and_(
                    TransactionModel.user_id == user_id,
                    TransactionModel.recipient_user_id == recipient_id
                ),
                db.and_(
                    TransactionModel.recipient_user_id == user_id,
                    TransactionModel.user_id == recipient_id
                )
            ),
            TransactionModel.status == TransactionStatus.COMPLETED
        ).first()
        
        return recent is None

    @classmethod
    def _get_recent_transaction_count(cls, user_id: int, minutes: int = 5) -> int:
        """Count recent transactions within time window."""
        window_start = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        
        return db.session.query(TransactionModel).filter(
            TransactionModel.user_id == user_id,
            TransactionModel.created_at >= window_start
        ).count()

    @classmethod
    def _get_hourly_volume(cls, user_id: int, currency: str) -> Decimal:
        """Get transaction volume in the last hour."""
        one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
        
        result = db.session.query(
            db.func.sum(TransactionModel.amount)
        ).filter(
            TransactionModel.user_id == user_id,
            TransactionModel.currency == currency,
            TransactionModel.status == TransactionStatus.COMPLETED,
            TransactionModel.created_at >= one_hour_ago
        ).scalar()
        
        return Decimal(str(result)) if result else Decimal('0')

    @classmethod
    def _is_new_ip(cls, user_id: int, ip_address: str) -> bool:
        """Check if IP address is new for user (simplified)."""
        recent = db.session.query(AuditLogModel).filter(
            AuditLogModel.actor_id == user_id,
            AuditLogModel.ip_address == ip_address,
            AuditLogModel.created_at >= datetime.now(timezone.utc) - timedelta(days=30)
        ).first()
        
        return recent is None

    @classmethod
    def _is_off_hours(cls) -> bool:
        """Check if current time is off-hours (simplified: 12AM-5AM)."""
        hour = datetime.now(timezone.utc).hour
        return hour >= 0 and hour < 5

    @classmethod
    def _get_user_kyc_level(cls, user_id: int) -> int:
        """Get user's KYC level."""
        user = db.session.get(User, user_id)
        return getattr(user, 'kyc_level', 0) or 0

    @classmethod
    def _get_kyc_per_txn_limit(cls, kyc_level: int) -> Decimal:
        """Get per-transaction limit for KYC level."""
        from app.wallet.services.kyc_limit_service import KYCLimitService
        limits = KYCLimitService.get_limits(kyc_level)
        return limits.get('per_txn_limit', Decimal('0'))

    @classmethod
    def create_fraud_alert(
        cls,
        user_id: int,
        action: str,
        risk_score: int,
        patterns: List[str],
        details: Dict[str, Any],
        transaction_id: Optional[str] = None
    ) -> Optional['FraudAlert']:
        """
        Create a fraud alert for review.
        
        Args:
            user_id: User ID
            action: Action that triggered alert
            risk_score: Calculated risk score
            patterns: List of suspicious patterns detected
            details: Additional context
            transaction_id: Related transaction ID
            
        Returns:
            FraudAlert model instance
        """
        try:
            from app.wallet.models.fraud_alert import FraudAlert, FraudAlertStatus
            
            alert = FraudAlert(
                user_id=user_id,
                action=action,
                risk_score=risk_score,
                patterns=patterns,
                details=details,
                transaction_id=transaction_id,
                status=FraudAlertStatus.OPEN
            )
            db.session.add(alert)
            db.session.commit()
            
            # Notify user
            try:
                from app.wallet.services.wallet_notifications import notify_suspicious_activity
                notify_suspicious_activity(user_id, alert)
            except Exception:
                current_app.logger.exception('Failed to send suspicious activity notification')
            
            return alert
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Failed to create fraud alert: {e}")
            return None

    @classmethod
    def get_open_alerts(cls, user_id: Optional[int] = None) -> List['FraudAlert']:
        """Get open fraud alerts, optionally filtered by user."""
        try:
            from app.wallet.models.fraud_alert import FraudAlert, FraudAlertStatus
            
            query = FraudAlert.query.filter_by(status=FraudAlertStatus.OPEN)
            if user_id:
                query = query.filter_by(user_id=user_id)
            
            return query.order_by(FraudAlert.created_at.desc()).all()
        except Exception:
            return []

