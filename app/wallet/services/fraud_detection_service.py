"""
Fraud Detection Service
Manages ML-based fraud detection and transaction scoring
"""

from typing import Dict, Any, Optional
from flask import current_app
from decimal import Decimal

from app.extensions import db
from app.wallet.models.fraud_detection import FraudDetectionConfig
from app.wallet.services.admin_audit_service import AdminAuditService


class FraudDetectionService:
    """Service for managing fraud detection configuration and transaction scoring"""
    
    @staticmethod
    def get_config() -> Optional[FraudDetectionConfig]:
        """Get current fraud detection configuration"""
        return FraudDetectionConfig.query.first()
    
    @staticmethod
    def update_config(
        admin_id: int,
        admin_name: str,
        admin_role: str,
        **updates
    ) -> FraudDetectionConfig:
        """
        Update fraud detection configuration
        
        Args:
            admin_id: ID of admin making changes
            admin_name: Name of admin
            admin_role: Role of admin
            **updates: Fields to update
            
        Returns:
            Updated configuration
        """
        try:
            config = FraudDetectionConfig.query.first()
            
            if not config:
                config = FraudDetectionConfig()
                db.session.add(config)
            
            old_value = config.to_dict()
            
            for key, value in updates.items():
                if hasattr(config, key):
                    setattr(config, key, value)
            
            db.session.commit()
            
            AdminAuditService.log_action(
                admin_id=admin_id,
                admin_name=admin_name,
                admin_role=admin_role,
                action_type='modify',
                action_category='fraud_detection',
                target_type='fraud_config',
                target_id=str(config.id),
                target_name='Fraud Detection Configuration',
                old_value=str(old_value),
                new_value=config.to_dict(),
                reason='Fraud detection configuration updated'
            )
            
            return config
        except Exception as e:
            db.session.rollback()
            raise e
    
    @staticmethod
    def score_transaction(
        user_id: int,
        amount: float,
        currency: str,
        recipient_id: Optional[int] = None,
        ip_address: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Score a transaction for fraud risk
        
        Args:
            user_id: User ID initiating transaction
            amount: Transaction amount
            currency: Currency code
            recipient_id: Recipient user ID (for transfers)
            ip_address: IP address of request
            
        Returns:
            Dictionary with risk score and factors
        """
        try:
            config = FraudDetectionConfig.query.first()
            
            if not config or not config.enabled:
                return {
                    'score': 0.0,
                    'risk_level': 'low',
                    'factors': [],
                    'action': 'allow'
                }
            
            score = 0.0
            factors = []
            
            # 1. High amount check
            if amount > config.max_amount_per_transaction:
                score += 0.3
                factors.append('high_amount')
            
            # 2. Velocity checks
            if config.check_velocity:
                from app.wallet.services.suspicious_activity_service import SuspiciousActivityService
                
                txn_count = SuspiciousActivityService._get_recent_transaction_count(user_id, minutes=5)
                if txn_count > config.max_transactions_per_minute:
                    score += 0.4
                    factors.append('high_velocity')
                
                # Hourly volume check
                hourly_volume = SuspiciousActivityService._get_hourly_volume(user_id, currency)
                if hourly_volume > config.max_amount_per_hour:
                    score += 0.3
                    factors.append('hourly_limit_exceeded')
            
            # 3. New account large transfer
            if config.check_new_account_large_transfer and recipient_id:
                from app.wallet.services.suspicious_activity_service import SuspiciousActivityService
                if SuspiciousActivityService._is_new_recipient(user_id, recipient_id):
                    if amount > config.max_amount_per_transaction * 0.5:
                        score += 0.2
                        factors.append('new_recipient_large_amount')
            
            # 4. IP location check (simplified)
            if config.check_ip_location and ip_address:
                if SuspiciousActivityService._is_new_ip(user_id, ip_address):
                    score += 0.1
                    factors.append('new_ip')
            
            # 5. Unusual patterns
            if config.check_unusual_patterns:
                from app.wallet.services.suspicious_activity_service import SuspiciousActivityService
                avg_amount = SuspiciousActivityService._get_average_transaction_amount(user_id, currency)
                if avg_amount > 0 and amount > avg_amount * 3:
                    score += 0.2
                    factors.append('amount_3x_avg')
            
            # 6. Off-hours
            if SuspiciousActivityService._is_off_hours():
                score += 0.1
                factors.append('off_hours')
            
            # Determine risk level
            if score < config.low_risk_threshold:
                risk_level = 'low'
                action = 'allow'
            elif score < config.medium_risk_threshold:
                risk_level = 'medium'
                action = 'review' if config.require_manual_review_medium_risk else 'allow'
            else:
                risk_level = 'high'
                action = 'block' if config.auto_block_high_risk else 'review'
            
            return {
                'score': round(score, 2),
                'risk_level': risk_level,
                'factors': factors,
                'action': action
            }
        except Exception as e:
            current_app.logger.error(f"Fraud detection scoring error: {e}")
            return {
                'score': 0.0,
                'risk_level': 'low',
                'factors': [],
                'action': 'allow'
            }
    
    @staticmethod
    def should_block_transaction(score_result: Dict[str, Any]) -> bool:
        """Determine if transaction should be blocked based on score."""
        return score_result.get('action') == 'block'
    
    @staticmethod
    def should_review_transaction(score_result: Dict[str, Any]) -> bool:
        """Determine if transaction should be flagged for review."""
        return score_result.get('action') == 'review'
