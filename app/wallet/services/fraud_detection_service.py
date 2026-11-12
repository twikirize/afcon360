"""
Fraud Detection Service
Configuration and scoring for ML-based fraud detection
"""

from typing import List, Dict, Any, Optional

from app.extensions import db
from app.wallet.models.fraud_detection import FraudDetectionConfig
from app.wallet.services.admin_audit_service import AdminAuditService


class FraudDetectionService:
    """Service for managing fraud detection configuration and scoring"""
    
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
                db.session.flush()  # Get ID for audit
            
            # Store old value for audit
            old_snapshot = config.to_audit_dict()
            
            for key, value in updates.items():
                if hasattr(config, key):
                    setattr(config, key, value)
            
            with AdminAuditService.audited_change():
                AdminAuditService.log_action(
                    admin_id=admin_id,
                    admin_name=admin_name,
                    admin_role=admin_role,
                    action_type='modify',
                    action_category='fraud_detection',
                    target_type='fraud_config',
                    target_id=str(config.id),
                    target_name='Fraud Detection Configuration',
                    old_value=old_snapshot,
                    new_value=config.to_audit_dict(),
                    reason='Fraud detection configuration updated'
                )
            
            return config
        except Exception as e:
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
                
                txn_count_hour = SuspiciousActivityService._get_recent_transaction_count(user_id, minutes=60)
                if txn_count_hour > config.max_transactions_per_hour:
                    score += 0.3
                    factors.append('high_velocity_hour')
            
            # 3. Geographic checks
            if config.check_ip_location and ip_address:
                # Would integrate with GeoIP service here
                pass
            
            # 4. Behavioral checks
            if config.check_unusual_patterns:
                from app.wallet.services.suspicious_activity_service import SuspiciousActivityService
                
                if SuspiciousActivityService.check_new_account_large_transfer(user_id, amount):
                    score += 0.25
                    factors.append('new_account_large_transfer')
                
                if SuspiciousActivityService.check_multiple_failed_attempts(user_id):
                    score += 0.35
                    factors.append('multiple_failed_attempts')
            
            # 5. Device fingerprint check
            if config.check_device_fingerprint:
                # Would integrate with device fingerprinting service
                pass
            
            # Determine risk level and action
            if score >= config.auto_block_threshold:
                risk_level = 'high'
                action = 'block' if config.auto_block_high_risk else 'review'
            elif score >= config.medium_risk_threshold:
                risk_level = 'medium'
                action = 'review' if config.require_manual_review_medium_risk else 'allow'
            elif score >= config.low_risk_threshold:
                risk_level = 'low'
                action = 'allow'
            else:
                risk_level = 'minimal'
                action = 'allow'
            
            return {
                'score': round(score, 2),
                'risk_level': risk_level,
                'factors': factors,
                'action': action
            }
        except Exception as e:
            current_app.logger.error(f"Fraud scoring error: {e}")
            return {
                'score': 0.0,
                'risk_level': 'unknown',
                'factors': ['scoring_error'],
                'action': 'allow'
            }
    
    @staticmethod
    def get_config() -> Optional[FraudDetectionConfig]:
        """Get current fraud detection configuration"""
        return FraudDetectionConfig.query.first()