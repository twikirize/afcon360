"""
Aggregator Service
Manages third-party aggregators for bulk wallet operations
"""

from typing import List, Dict, Any, Optional
from flask import current_app

from app.extensions import db
from app.wallet.models.aggregator import Aggregator
from app.wallet.services.admin_audit_service import AdminAuditService


class AggregatorService:
    """Service for managing aggregators"""
    
    @staticmethod
    def create_aggregator(
        name: str,
        display_name: str,
        api_key: str,
        api_secret: str,
        description: Optional[str] = None,
        tier: str = 'standard',
        mode: str = 'testing',
        sandbox_api_key: Optional[str] = None,
        sandbox_api_secret: Optional[str] = None,
        live_api_key: Optional[str] = None,
        live_api_secret: Optional[str] = None,
        admin_id: Optional[int] = None,
        admin_name: Optional[str] = None,
        admin_role: Optional[str] = None
    ) -> Aggregator:
        """
        Create a new aggregator
        
        Args:
            name: Unique identifier for aggregator
            display_name: Human-readable name
            api_key: API key for authentication (fallback/primary)
            api_secret: API secret (will be encrypted)
            description: Description of aggregator
            tier: Aggregator tier (standard, premium, enterprise)
            mode: Operating mode ('testing' or 'live')
            sandbox_api_key: Sandbox API key
            sandbox_api_secret: Sandbox API secret
            live_api_key: Live API key
            live_api_secret: Live API secret
            admin_id: ID of admin creating aggregator
            admin_name: Name of admin
            admin_role: Role of admin
            
        Returns:
            Aggregator object
        """
        try:
            aggregator = Aggregator(
                name=name,
                display_name=display_name,
                description=description,
                api_key=api_key,
                api_secret=api_secret,
                tier=tier,
                mode=mode,
                sandbox_api_key=sandbox_api_key or api_key,
                sandbox_api_secret=sandbox_api_secret or api_secret,
                live_api_key=live_api_key,
                live_api_secret=live_api_secret,
                status='active'
            )
            
            db.session.add(aggregator)
            db.session.commit()
            
            # Log the action
            if admin_id and admin_name:
                AdminAuditService.log_action(
                    admin_id=admin_id,
                    admin_name=admin_name,
                    admin_role=admin_role,
                    action_type='create',
                    action_category='aggregator',
                    target_type='aggregator',
                    target_id=str(aggregator.id),
                    target_name=display_name,
                    new_value=aggregator.to_dict(exclude_secret=False),
                    reason='New aggregator created'
                )
            
            return aggregator
        except Exception as e:
            db.session.rollback()
            raise e
    
    @staticmethod
    def get_aggregator(aggregator_id: int) -> Optional[Aggregator]:
        """Get aggregator by ID"""
        return db.session.get(Aggregator, aggregator_id)
    
    @staticmethod
    def get_all_aggregators(status: Optional[str] = None) -> List[Aggregator]:
        """Get all aggregators, optionally filtered by status"""
        query = Aggregator.query
        if status:
            query = query.filter(Aggregator.status == status)
        return query.all()
    
    @staticmethod
    def update_aggregator(
        aggregator_id: int,
        admin_id: int,
        admin_name: str,
        admin_role: str,
        **updates
    ) -> Aggregator:
        """
        Update aggregator configuration
        
        Args:
            aggregator_id: ID of aggregator to update
            admin_id: ID of admin making changes
            admin_name: Name of admin
            admin_role: Role of admin
            **updates: Fields to update
            
        Returns:
            Updated aggregator
        """
        try:
            aggregator = db.session.get(Aggregator, aggregator_id)
            if not aggregator:
                raise ValueError(f"Aggregator {aggregator_id} not found")
            
            # Store old value for audit
            old_value = aggregator.to_dict(exclude_secret=False)
            
            # Update fields
            for key, value in updates.items():
                if hasattr(aggregator, key):
                    setattr(aggregator, key, value)
            
            db.session.commit()
            
            # Log the action
            AdminAuditService.log_action(
                admin_id=admin_id,
                admin_name=admin_name,
                admin_role=admin_role,
                action_type='modify',
                action_category='aggregator',
                target_type='aggregator',
                target_id=str(aggregator.id),
                target_name=aggregator.display_name,
                old_value=str(old_value),
                new_value=aggregator.to_dict(exclude_secret=False),
                reason='Aggregator configuration updated'
            )
            
            return aggregator
        except Exception as e:
            db.session.rollback()
            raise e
    
    @staticmethod
    def suspend_aggregator(
        aggregator_id: int,
        admin_id: int,
        admin_name: str,
        admin_role: str,
        reason: str
    ) -> Aggregator:
        """Suspend an aggregator"""
        try:
            aggregator = db.session.get(Aggregator, aggregator_id)
            if not aggregator:
                raise ValueError(f"Aggregator {aggregator_id} not found")
            
            aggregator.status = 'suspended'
            db.session.commit()
            
            # Log the action
            AdminAuditService.log_action(
                admin_id=admin_id,
                admin_name=admin_name,
                admin_role=admin_role,
                action_type='suspend',
                action_category='aggregator',
                target_type='aggregator',
                target_id=str(aggregator.id),
                target_name=aggregator.display_name,
                reason=reason
            )
            
            return aggregator
        except Exception as e:
            db.session.rollback()
            raise e
    
    @staticmethod
    def activate_aggregator(
        aggregator_id: int,
        admin_id: int,
        admin_name: str,
        admin_role: str,
        reason: str
    ) -> Aggregator:
        """Activate a suspended aggregator"""
        try:
            aggregator = db.session.get(Aggregator, aggregator_id)
            if not aggregator:
                raise ValueError(f"Aggregator {aggregator_id} not found")
            
            aggregator.status = 'active'
            db.session.commit()
            
            # Log the action
            AdminAuditService.log_action(
                admin_id=admin_id,
                admin_name=admin_name,
                admin_role=admin_role,
                action_type='activate',
                action_category='aggregator',
                target_type='aggregator',
                target_id=str(aggregator.id),
                target_name=aggregator.display_name,
                reason=reason
            )
            
            return aggregator
        except Exception as e:
            db.session.rollback()
            raise e

    @staticmethod
    def set_aggregator_mode(
        aggregator_id: int,
        mode: str,
        admin_id: int,
        admin_name: str,
        admin_role: str,
        reason: str
    ) -> Aggregator:
        """Switch aggregator operating mode between 'testing' (sandbox) and 'live'"""
        try:
            if mode not in ('testing', 'live'):
                raise ValueError("Invalid mode. Must be 'testing' or 'live'.")
            
            aggregator = db.session.get(Aggregator, aggregator_id)
            if not aggregator:
                raise ValueError(f"Aggregator {aggregator_id} not found")
            
            old_mode = aggregator.mode
            aggregator.mode = mode
            
            # If switching to live, ensure live credentials exist or copy primary if set
            if mode == 'live' and not aggregator.live_api_key and aggregator.api_key:
                aggregator.live_api_key = aggregator.api_key
                aggregator.live_api_secret = aggregator.api_secret
            
            db.session.commit()
            
            # Log the action
            AdminAuditService.log_action(
                admin_id=admin_id,
                admin_name=admin_name,
                admin_role=admin_role,
                action_type='set_mode',
                action_category='aggregator',
                target_type='aggregator',
                target_id=str(aggregator.id),
                target_name=aggregator.display_name,
                old_value=old_mode,
                new_value=mode,
                reason=reason
            )
            
            return aggregator
        except Exception as e:
            db.session.rollback()
            raise e

