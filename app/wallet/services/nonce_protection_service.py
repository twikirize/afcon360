"""
Nonce Replay Protection Service
Manages user-specific nonce counters to prevent transaction replay attacks
"""

import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from flask import current_app

from app.extensions import db
from app.wallet.models.nonce_protection import UserNonce, NonceProtectionConfig
from app.wallet.services.admin_audit_service import AdminAuditService


class NonceProtectionService:
    """Service for managing nonce replay protection"""
    
    @staticmethod
    def get_config() -> Optional[NonceProtectionConfig]:
        """Get current nonce protection configuration"""
        return NonceProtectionConfig.query.first()
    
    @staticmethod
    def update_config(
        admin_id: int,
        admin_name: str,
        admin_role: str,
        **updates
    ) -> NonceProtectionConfig:
        """
        Update nonce protection configuration
        
        Args:
            admin_id: ID of admin making changes
            admin_name: Name of admin
            admin_role: Role of admin
            **updates: Fields to update
            
        Returns:
            Updated configuration
        """
        try:
            config = NonceProtectionConfig.query.first()
            
            if not config:
                # Create default config if none exists
                config = NonceProtectionConfig()
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
                action_category='nonce_protection',
                target_type='nonce_config',
                target_id=str(config.id),
                target_name='Nonce Protection Configuration',
                old_value=str(old_value),
                new_value=config.to_dict(),
                reason='Nonce protection configuration updated'
            )
            
            return config
        except Exception as e:
            db.session.rollback()
            raise e
    
    @staticmethod
    def generate_nonce(
        user_id: int,
        user_type: str = 'user',
        nonce_type: str = 'transaction',
        transaction_type: Optional[str] = None,
        amount: Optional[int] = None,
        currency: Optional[str] = None
    ) -> str:
        """
        Generate a new nonce for a user
        
        Args:
            user_id: User ID
            user_type: Type of user (user, aggregator, admin)
            nonce_type: Type of nonce (transaction, api_call, webhook)
            transaction_type: Type of transaction (deposit, withdraw, transfer)
            amount: Transaction amount in smallest currency unit
            currency: Currency code
            
        Returns:
            Generated nonce string
        """
        try:
            config = NonceProtectionConfig.query.first()
            
            if not config or not config.enabled:
                return None
            
            # Check rate limits
            NonceProtectionService._check_rate_limits(user_id, user_type, config)
            
            # Generate unique nonce
            nonce = str(uuid.uuid4())
            
            # Calculate expiration
            expires_at = datetime.utcnow() + timedelta(minutes=config.nonce_ttl_minutes)
            
            # Create nonce record
            user_nonce = UserNonce(
                user_id=user_id,
                user_type=user_type,
                nonce=nonce,
                nonce_type=nonce_type,
                transaction_type=transaction_type,
                amount=amount,
                currency=currency,
                expires_at=expires_at
            )
            
            db.session.add(user_nonce)
            db.session.commit()
            
            return nonce
        except Exception as e:
            db.session.rollback()
            raise e
    
    @staticmethod
    def validate_nonce(
        nonce: str,
        user_id: int,
        transaction_type: Optional[str] = None,
        amount: Optional[int] = None,
        currency: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Validate a nonce for transaction
        
        Args:
            nonce: Nonce string to validate
            user_id: User ID
            transaction_type: Type of transaction
            amount: Transaction amount
            currency: Currency code
            
        Returns:
            Dictionary with validation result
        """
        try:
            config = NonceProtectionConfig.query.first()
            
            if not config or not config.enabled:
                return {
                    'valid': True,
                    'reason': 'Nonce protection disabled',
                    'action': 'allow'
                }
            
            # Find the nonce
            user_nonce = UserNonce.query.filter_by(
                nonce=nonce,
                user_id=user_id
            ).first()
            
            if not user_nonce:
                return {
                    'valid': False,
                    'reason': 'Nonce not found',
                    'action': 'reject'
                }
            
            # Check if already used
            if user_nonce.used:
                return {
                    'valid': False,
                    'reason': 'Nonce already used',
                    'action': 'reject'
                }
            
            # Check if voided
            if user_nonce.voided:
                return {
                    'valid': False,
                    'reason': 'Nonce voided',
                    'action': 'reject'
                }
            
            # Check expiration
            if datetime.utcnow() > user_nonce.expires_at:
                return {
                    'valid': False,
                    'reason': 'Nonce expired',
                    'action': 'reject'
                }
            
            # Check transaction type match (if specified)
            if transaction_type and user_nonce.transaction_type and user_nonce.transaction_type != transaction_type:
                return {
                    'valid': False,
                    'reason': 'Transaction type mismatch',
                    'action': 'reject'
                }
            
            # Check amount reuse (if not allowed)
            if not config.allow_nonce_reuse_same_amount and amount and user_nonce.amount and user_nonce.amount != amount:
                return {
                    'valid': False,
                    'reason': 'Amount mismatch',
                    'action': 'reject'
                }
            
            # Mark nonce as used
            user_nonce.used = True
            user_nonce.used_at = datetime.utcnow()
            db.session.commit()
            
            return {
                'valid': True,
                'reason': 'Nonce valid',
                'action': 'allow'
            }
        except Exception as e:
            current_app.logger.error(f"Nonce validation error: {e}")
            # Fail open - allow transaction if validation fails
            return {
                'valid': True,
                'reason': 'Validation error - allowed',
                'action': 'allow'
            }
    
    @staticmethod
    def void_nonce(nonce: str, reason: str = 'Manual void') -> bool:
        """
        Void a nonce (mark as invalid)
        
        Args:
            nonce: Nonce to void
            reason: Reason for voiding
            
        Returns:
            True if successful, False otherwise
        """
        try:
            user_nonce = UserNonce.query.filter_by(nonce=nonce).first()
            
            if user_nonce and not user_nonce.used:
                user_nonce.voided = True
                db.session.commit()
                return True
            
            return False
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Nonce void error: {e}")
            return False
    
    @staticmethod
    def cleanup_expired_nonces() -> int:
        """
        Clean up expired nonces
        
        Returns:
            Number of nonces cleaned up
        """
        try:
            expired_count = UserNonce.query.filter(
                UserNonce.expires_at < datetime.utcnow()
            ).count()
            
            UserNonce.query.filter(
                UserNonce.expires_at < datetime.utcnow()
            ).delete()
            
            db.session.commit()
            
            return expired_count
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Nonce cleanup error: {e}")
            return 0
    
    @staticmethod
    def _check_rate_limits(user_id: int, user_type: str, config: NonceProtectionConfig) -> None:
        """Check if user has exceeded rate limits"""
        try:
            one_hour_ago = datetime.utcnow() - timedelta(hours=1)
            
            # Get appropriate rate limit based on user type
            if user_type == 'aggregator':
                max_nonces = config.max_nonces_per_aggregator_per_hour
            else:
                max_nonces = config.max_nonces_per_user_per_hour
            
            # Count nonces in last hour
            nonce_count = UserNonce.query.filter(
                UserNonce.user_id == user_id,
                UserNonce.user_type == user_type,
                UserNonce.created_at >= one_hour_ago
            ).count()
            
            if nonce_count >= max_nonces:
                raise ValueError(f"Rate limit exceeded: {nonce_count}/{max_nonces} nonces per hour")
        except Exception as e:
            raise e
