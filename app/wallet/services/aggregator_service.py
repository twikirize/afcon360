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
        admin_id: Optional[int] = None,
        admin_name: Optional[str] = None,
        admin_role: Optional[str] = None
    ) -> Aggregator:
        """
        Create a new aggregator
        
        Args:
            name: Unique identifier for aggregator
            display_name: Human-readable name
            api_key: API key for authentication
            api_secret: API secret (will be encrypted)
            description: Description of aggregator
            tier: Aggregator tier (standard, premium, enterprise)
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
                api_secret=api_secret,  # Should be encrypted at storage time
                tier=tier,
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
        return Aggregator.query.get(aggregator_id)
    
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
            aggregator = Aggregator.query.get(aggregator_id)
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
            aggregator = Aggregator.query.get(aggregator_id)
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
            aggregator = Aggregator.query.get(aggregator_id)
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
