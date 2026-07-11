"""
Fraud Detection Service
Manages ML-based fraud detection and transaction scoring
"""

from typing import Dict, Any, Optional
from flask import current_app

from app.extensions import db
from app.wallet.models.fraud_detection import FraudDetectionConfig
from app.wallet.services.admin_audit_service import AdminAuditService


class FraudDetectionService:
    """Service for managing fraud detection configuration"""
    
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
                # Create default config if none exists
                config = FraudDetectionConfig()
                db.session.add(config)
            
            # Store old value for audit
            old_value = config.to_dict()
            
            # Update fields
            for key, value in updates.items():
                if hasattr(config, key):
                    setattr(config, key, value)
            
            db.session.commit()
            
            # Log the action
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
            
            # Check transaction amount
            if amount > config.max_amount_per_transaction:
                score += 0.3
                factors.append('high_amount')
            
            # Check velocity (simplified - would need actual history)
            # This is a placeholder - real implementation would query transaction history
            if config.check_velocity:
                # Simplified velocity check
                pass
            
            # Check IP location (simplified)
            if config.check_ip_location and ip_address:
                # Would implement IP geolocation check
                pass
            
            # Check new account large transfer
            if config.check_new_account_large_transfer:
                # Would implement account age check
                pass
            
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
                'score': score,
                'risk_level': risk_level,
                'factors': factors,
                'action': action
            }
        except Exception as e:
            current_app.logger.error(f"Fraud detection scoring error: {e}")
            # Fail open - allow transaction if scoring fails
            return {
                'score': 0.0,
                'risk_level': 'low',
                'factors': [],
                'action': 'allow'
            }
