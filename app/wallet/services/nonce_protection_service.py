"""
Nonce Replay Protection Service
Manages user-specific nonce counters to prevent transaction replay attacks
"""

from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
import uuid

from app.extensions import db
from app.wallet.models.nonce_protection import UserNonce, NonceProtectionConfig
from app.wallet.services.admin_audit_service import AdminAuditService


class NonceProtectionService:
    """Service for managing nonce replay protection"""
    
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
                config = NonceProtectionConfig()
                db.session.add(config)
                db.session.flush()  # Get ID for audit
            
            # Store old value for audit
            old_snapshot = config.to_audit_dict()
            
            # Update fields
            for key, value in updates.items():
                if hasattr(config, key):
                    setattr(config, key, value)
            
            with AdminAuditService.audited_change():
                AdminAuditService.log_action(
                    admin_id=admin_id,
                    admin_name=admin_name,
                    admin_role=admin_role,
                    action_type='modify',
                    action_category='nonce_protection',
                    target_type='nonce_config',
                    target_id=str(config.id),
                    target_name='Nonce Protection Configuration',
                    old_value=old_snapshot,
                    new_value=config.to_audit_dict(),
                    reason='Nonce protection configuration updated'
                )
            
            return config
        except Exception as e:
            raise e
    
    @staticmethod
    def generate_nonce(
        user_id: int,
        user_type: str = 'user',
        nonce_type: str = 'transaction',
        transaction_type: Optional[str] = None,
        amount: Optional[int] = None,
        currency: Optional[str] = None
    ) -> Optional[str]:
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
            Generated nonce string or None if disabled
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
            expires_at = datetime.now(timezone.utc) + timedelta(minutes=config.nonce_ttl_minutes)
            
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
            current_app.logger.error(f"Nonce generation error: {e}")
            return None
    
    @staticmethod
    def validate_nonce(
        nonce: str,
        user_id: int,
        user_type: str = 'user',
        transaction_type: Optional[str] = None,
        amount: Optional[int] = None,
        currency: Optional[str] = None
    ) -> bool:
        """
        Validate and consume a nonce
        
        Args:
            nonce: Nonce string to validate
            user_id: User ID
            user_type: Type of user
            transaction_type: Type of transaction
            amount: Transaction amount
            currency: Currency code
            
        Returns:
            True if nonce is valid and consumed, False otherwise
        """
        try:
            config = NonceProtectionConfig.query.first()
            
            if not config or not config.enabled:
                return True  # Nonce validation disabled
            
            # Find the nonce record
            user_nonce = UserNonce.query.filter_by(
                nonce=nonce,
                user_id=user_id,
                user_type=user_type
            ).first()
            
            if not user_nonce:
                return False
            
            # Check expiration
            if user_nonce.expires_at < datetime.now(timezone.utc):
                return False
            
            # Check if already used
            if user_nonce.used:
                return False
            
            # Check if voided
            if user_nonce.voided:
                return False
            
            # Validate transaction type if specified
            if transaction_type and user_nonce.transaction_type != transaction_type:
                return False
            
            # Validate amount if specified
            if amount is not None and user_nonce.amount != amount:
                if not config.allow_nonce_reuse_same_amount:
                    return False
            
            # Validate currency if specified
            if currency and user_nonce.currency != currency:
                return False
            
            # Mark as used
            user_nonce.used = True
            user_nonce.used_at = datetime.now(timezone.utc)
            db.session.commit()
            
            return True
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Nonce validation error: {e}")
            return False
    
    @staticmethod
    def _check_rate_limits(user_id: int, user_type: str, config: NonceProtectionConfig):
        """Check nonce generation rate limits"""
        from datetime import datetime, timezone, timedelta
        
        hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
        
        if user_type == 'aggregator':
            limit = config.max_nonces_per_aggregator_per_hour
        else:
            limit = config.max_nonces_per_user_per_hour
        
        count = UserNonce.query.filter(
            UserNonce.user_id == user_id,
            UserNonce.user_type == user_type,
            UserNonce.created_at >= hour_ago
        ).count()
        
        if count >= limit:
            raise Exception(f"Rate limit exceeded: max {limit} nonces per hour for {user_type}")
    
    @staticmethod
    def cleanup_expired_nonces():
        """Clean up expired nonces (should be run periodically)"""
        try:
            config = NonceProtectionConfig.query.first()
            
            if not config or not config.enabled:
                return 0
            
            expired = UserNonce.query.filter(
                UserNonce.expires_at < datetime.now(timezone.utc)
            ).delete()
            
            db.session.commit()
            return expired
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Nonce cleanup error: {e}")
            return 0
    
    @staticmethod
    def get_user_nonces(user_id: int, user_type: str = 'user', limit: int = 100) -> List[UserNonce]:
        """Get recent nonces for a user"""
        return UserNonce.query.filter_by(
            user_id=user_id,
            user_type=user_type
        ).order_by(UserNonce.created_at.desc()).limit(limit).all()
    
    @staticmethod
    def get_config() -> Optional[NonceProtectionConfig]:
        """Get current nonce protection configuration"""
        return NonceProtectionConfig.query.first()