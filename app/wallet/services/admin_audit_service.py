"""
Admin Audit Service
Manages system-level audit logging for admin actions
"""

from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from flask import request
from sqlalchemy import func

from app.extensions import db
from app.wallet.models.admin_audit import AdminAuditLog


class AdminAuditService:
    """Service for managing admin audit logs"""
    
    @staticmethod
    def log_action(
        admin_id: int,
        admin_name: str,
        admin_role: str,
        action_type: str,
        action_category: str,
        target_type: str,
        target_id: Optional[str] = None,
        target_name: Optional[str] = None,
        old_value: Optional[str] = None,
        new_value: Optional[str] = None,
        reason: Optional[str] = None
    ) -> AdminAuditLog:
        """
        Log an admin action for audit trail
        
        Args:
            admin_id: ID of admin performing action
            admin_name: Name of admin
            admin_role: Role of admin
            action_type: Type of action (approve, reject, configure, modify)
            action_category: Category of action (aggregator, fraud_detection, etc.)
            target_type: Type of target (aggregator, user, transaction)
            target_id: ID of target
            target_name: Name of target
            old_value: Previous state (JSON string)
            new_value: New state (JSON string)
            reason: Reason for action
            
        Returns:
            AdminAuditLog object
        """
        try:
            audit_log = AdminAuditLog(
                admin_id=admin_id,
                admin_name=admin_name,
                admin_role=admin_role,
                action_type=action_type,
                action_category=action_category,
                target_type=target_type,
                target_id=target_id,
                target_name=target_name,
                old_value=old_value,
                new_value=new_value,
                reason=reason,
                ip_address=request.remote_addr if request else None,
                user_agent=request.user_agent.string if request and request.user_agent else None,
                created_at=datetime.now(timezone.utc)
            )
            
            db.session.add(audit_log)
            db.session.commit()
            
            return audit_log
        except Exception as e:
            db.session.rollback()
            raise e
    
    @staticmethod
    def get_audit_logs(
        admin_id: Optional[int] = None,
        action_type: Optional[str] = None,
        action_category: Optional[str] = None,
        target_type: Optional[str] = None,
        days: int = 30,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get audit logs with filters
        
        Args:
            admin_id: Filter by admin ID
            action_type: Filter by action type
            action_category: Filter by action category
            target_type: Filter by target type
            days: Number of days to look back
            limit: Maximum number of results
            
        Returns:
            List of audit log dictionaries
        """
        try:
            query = AdminAuditLog.query
            
            # Apply filters
            if admin_id:
                query = query.filter(AdminAuditLog.admin_id == admin_id)
            if action_type:
                query = query.filter(AdminAuditLog.action_type == action_type)
            if action_category:
                query = query.filter(AdminAuditLog.action_category == action_category)
            if target_type:
                query = query.filter(AdminAuditLog.target_type == target_type)
            
            # Date filter
            date_threshold = datetime.now(timezone.utc) - timedelta(days=days)
            query = query.filter(AdminAuditLog.created_at >= date_threshold)
            
            # Order by most recent
            query = query.order_by(AdminAuditLog.created_at.desc())
            
            # Apply limit
            query = query.limit(limit)
            
            logs = query.all()
            return [log.to_dict() for log in logs]
        except Exception as e:
            raise e
    
    @staticmethod
    def get_audit_summary(days: int = 30) -> Dict[str, Any]:
        """
        Get summary statistics for audit logs
        
        Args:
            days: Number of days to summarize
            
        Returns:
            Dictionary with summary statistics
        """
        try:
            date_threshold = datetime.now(timezone.utc) - timedelta(days=days)
            
            total_actions = AdminAuditLog.query.filter(
                AdminAuditLog.created_at >= date_threshold
            ).count()
            
            actions_by_type = db.session.query(
                AdminAuditLog.action_type,
                func.count(AdminAuditLog.id)
            ).filter(
                AdminAuditLog.created_at >= date_threshold
            ).group_by(AdminAuditLog.action_type).all()
            
            actions_by_category = db.session.query(
                AdminAuditLog.action_category,
                func.count(AdminAuditLog.id)
            ).filter(
                AdminAuditLog.created_at >= date_threshold
            ).group_by(AdminAuditLog.action_category).all()
            
            return {
                'total_actions': total_actions,
                'actions_by_type': dict(actions_by_type),
                'actions_by_category': dict(actions_by_category),
                'days': days
            }
        except Exception as e:
            raise e
