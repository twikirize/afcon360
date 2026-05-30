"""
Multi-Tier Moderation Workflow System

Enterprise-level escalation workflows for content moderation
with Level 1-3 escalation paths and automated routing.
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from sqlalchemy import and_, or_, func

from app.extensions import db
from app.admin.models.moderation import ContentFlag, ModerationLog


class ModerationLevel(Enum):
    """Moderation escalation levels"""
    LEVEL_1 = "level_1"  # Basic moderation (auto-approved moderators)
    LEVEL_2 = "level_2"  # Advanced moderation (experienced moderators)
    LEVEL_3 = "level_3"  # Expert moderation (senior moderators, legal team)


class EscalationTrigger(Enum):
    """Reasons for escalation"""
    HIGH_RISK_SCORE = "high_risk_score"
    APPEAL_FILED = "appeal_filed"
    SLA_BREACH = "sla_breach"
    COMPLEX_CASE = "complex_case"
    LEGAL_REQUIRED = "legal_required"
    REPEAT_OFFENDER = "repeat_offender"
    MANUAL_ESCALATION = "manual_escalation"


@dataclass
class EscalationRule:
    """Rule for automatic escalation"""
    trigger: EscalationTrigger
    from_level: ModerationLevel
    to_level: ModerationLevel
    conditions: Dict
    auto_escalate: bool = True


class EscalationWorkflow:
    """Enterprise escalation workflow manager"""
    
    def __init__(self):
        self.escalation_rules = self._initialize_rules()
        self.level_permissions = self._initialize_permissions()
        self.escalation_history = {}
        
    def _initialize_rules(self) -> List[EscalationRule]:
        """Initialize escalation rules"""
        return [
            # High risk score escalations
            EscalationRule(
                trigger=EscalationTrigger.HIGH_RISK_SCORE,
                from_level=ModerationLevel.LEVEL_1,
                to_level=ModerationLevel.LEVEL_2,
                conditions={'risk_score': 70},
                auto_escalate=True
            ),
            EscalationRule(
                trigger=EscalationTrigger.HIGH_RISK_SCORE,
                from_level=ModerationLevel.LEVEL_2,
                to_level=ModerationLevel.LEVEL_3,
                conditions={'risk_score': 85},
                auto_escalate=True
            ),
            
            # Appeal escalations
            EscalationRule(
                trigger=EscalationTrigger.APPEAL_FILED,
                from_level=ModerationLevel.LEVEL_1,
                to_level=ModerationLevel.LEVEL_2,
                conditions={'appeal_count': 1},
                auto_escalate=True
            ),
            EscalationRule(
                trigger=EscalationTrigger.APPEAL_FILED,
                from_level=ModerationLevel.LEVEL_2,
                to_level=ModerationLevel.LEVEL_3,
                conditions={'appeal_count': 2},
                auto_escalate=True
            ),
            
            # SLA breach escalations
            EscalationRule(
                trigger=EscalationTrigger.SLA_BREACH,
                from_level=ModerationLevel.LEVEL_1,
                to_level=ModerationLevel.LEVEL_2,
                conditions={'hours_overdue': 2},
                auto_escalate=True
            ),
            EscalationRule(
                trigger=EscalationTrigger.SLA_BREACH,
                from_level=ModerationLevel.LEVEL_2,
                to_level=ModerationLevel.LEVEL_3,
                conditions={'hours_overdue': 4},
                auto_escalate=True
            ),
            
            # Legal requirement escalations
            EscalationRule(
                trigger=EscalationTrigger.LEGAL_REQUIRED,
                from_level=ModerationLevel.LEVEL_1,
                to_level=ModerationLevel.LEVEL_3,
                conditions={'legal_review_required': True},
                auto_escalate=True
            ),
            EscalationRule(
                trigger=EscalationTrigger.LEGAL_REQUIRED,
                from_level=ModerationLevel.LEVEL_2,
                to_level=ModerationLevel.LEVEL_3,
                conditions={'legal_review_required': True},
                auto_escalate=True
            ),
        ]
    
    def _initialize_permissions(self) -> Dict[ModerationLevel, List[str]]:
        """Initialize permissions for each level"""
        return {
            ModerationLevel.LEVEL_1: [
                'view_content', 'approve_content', 'reject_content',
                'request_changes', 'assign_to_team', 'basic_filtering'
            ],
            ModerationLevel.LEVEL_2: [
                'view_content', 'approve_content', 'reject_content',
                'request_changes', 'assign_to_team', 'escalate_case',
                'handle_appeals', 'advanced_filtering', 'view_user_history'
            ],
            ModerationLevel.LEVEL_3: [
                'view_content', 'approve_content', 'reject_content',
                'request_changes', 'assign_to_team', 'escalate_case',
                'handle_appeals', 'advanced_filtering', 'view_user_history',
                'legal_review', 'permanent_ban', 'compliance_reporting',
                'override_decisions', 'system_configuration'
            ]
        }
    
    def check_escalation_needed(self, flag: ContentFlag) -> List[EscalationRule]:
        """
        Check if a flag needs escalation based on rules
        
        Args:
            flag: ContentFlag to check
            
        Returns:
            List of applicable escalation rules
        """
        applicable_rules = []
        current_level = ModerationLevel(flag.moderation_level)
        
        for rule in self.escalation_rules:
            if rule.from_level == current_level and self._evaluate_conditions(rule, flag):
                applicable_rules.append(rule)
        
        return applicable_rules
    
    def _evaluate_conditions(self, rule: EscalationRule, flag: ContentFlag) -> bool:
        """Evaluate if rule conditions are met"""
        conditions = rule.conditions
        
        if rule.trigger == EscalationTrigger.HIGH_RISK_SCORE:
            return flag.risk_score >= conditions.get('risk_score', 0)
        
        elif rule.trigger == EscalationTrigger.APPEAL_FILED:
            return flag.appeal_count >= conditions.get('appeal_count', 0)
        
        elif rule.trigger == EscalationTrigger.SLA_BREACH:
            if flag.sla_breached:
                hours_overdue = (datetime.now(timezone.utc) - flag.sla_due_at).total_seconds() / 3600
                return hours_overdue >= conditions.get('hours_overdue', 0)
            return False
        
        elif rule.trigger == EscalationTrigger.LEGAL_REQUIRED:
            return flag.legal_review_required
        
        elif rule.trigger == EscalationTrigger.REPEAT_OFFENDER:
            # Check if user has multiple flags
            user_flags = ContentFlag.query.filter(
                and_(
                    ContentFlag.entity_type == 'user',
                    ContentFlag.entity_id == flag.entity_id,
                    ContentFlag.status == 'resolved',
                    ContentFlag.resolution_action == 'rejected'
                )
            ).count()
            return user_flags >= conditions.get('previous_violations', 3)
        
        return False
    
    def escalate_flag(self, flag: ContentFlag, to_level: ModerationLevel, 
                     reason: str, escalated_by: int) -> bool:
        """
        Escalate a flag to a higher level
        
        Args:
            flag: ContentFlag to escalate
            to_level: Target moderation level
            reason: Reason for escalation
            escalated_by: User ID of person escalating
            
        Returns:
            True if escalation successful
        """
        try:
            old_level = flag.moderation_level
            
            # Update flag
            flag.moderation_level = to_level.value
            flag.escalated_from_level = old_level
            flag.escalated_to_level = to_level.value
            flag.escalation_reason = reason
            flag.escalation_count += 1
            flag.escalated_at = datetime.now(timezone.utc)
            
            # Update SLA for higher priority
            if to_level == ModerationLevel.LEVEL_3:
                flag.sla_due_at = datetime.now(timezone.utc) + timedelta(hours=1)
                flag.sla_priority = 'critical'
            elif to_level == ModerationLevel.LEVEL_2:
                flag.sla_due_at = datetime.now(timezone.utc) + timedelta(hours=4)
                flag.sla_priority = 'high'
            
            # Assign to appropriate team
            flag.assigned_team = self._get_team_for_level(to_level)
            
            # Log escalation
            self._log_escalation(flag, old_level, to_level, reason, escalated_by)
            
            db.session.commit()
            
            # Track escalation history
            self.escalation_history[flag.id] = {
                'escalations': self.escalation_history.get(flag.id, {}).get('escalations', []) + [{
                    'from_level': old_level,
                    'to_level': to_level.value,
                    'reason': reason,
                    'escalated_by': escalated_by,
                    'escalated_at': flag.escalated_at.isoformat()
                }]
            }
            
            return True
            
        except Exception as e:
            current_app.logger.error(f"Failed to escalate flag {flag.id}: {e}")
            db.session.rollback()
            return False
    
    def _get_team_for_level(self, level: ModerationLevel) -> str:
        """Get appropriate team for moderation level"""
        team_mapping = {
            ModerationLevel.LEVEL_1: 'content_review',
            ModerationLevel.LEVEL_2: 'safety_team',
            ModerationLevel.LEVEL_3: 'escalation_team'
        }
        return team_mapping.get(level, 'content_review')
    
    def _log_escalation(self, flag: ContentFlag, old_level: str, 
                       new_level: ModerationLevel, reason: str, escalated_by: int):
        """Log escalation action"""
        log = ModerationLog(
            entity_type=flag.entity_type,
            entity_id=flag.entity_id,
            action='escalate',
            details=f"Escalated from {old_level} to {new_level.value}: {reason}",
            performed_by=escalated_by,
            created_at=datetime.now(timezone.utc)
        )
        db.session.add(log)
    
    def process_appeal(self, flag: ContentFlag, appeal_reason: str, 
                      appealed_by: int) -> Tuple[bool, str]:
        """
        Process an appeal on a moderation decision
        
        Args:
            flag: ContentFlag being appealed
            appeal_reason: Reason for appeal
            appealed_by: User ID filing appeal
            
        Returns:
            Tuple of (success, message)
        """
        try:
            # Increment appeal count
            flag.appeal_count += 1
            
            # Check if appeal triggers escalation
            escalation_rules = self.check_escalation_needed(flag)
            
            for rule in escalation_rules:
                if rule.trigger == EscalationTrigger.APPEAL_FILED and rule.auto_escalate:
                    self.escalate_flag(
                        flag, rule.to_level, 
                        f"Appeal #{flag.appeal_count}: {appeal_reason}",
                        escalated_by=0  # System escalation
                    )
                    
                    return True, f"Appeal filed and escalated to {rule.to_level.value}"
            
            # Log appeal
            log = ModerationLog(
                entity_type=flag.entity_type,
                entity_id=flag.entity_id,
                action='appeal',
                details=f"Appeal #{flag.appeal_count}: {appeal_reason}",
                performed_by=appealed_by,
                created_at=datetime.now(timezone.utc)
            )
            db.session.add(log)
            
            db.session.commit()
            
            return True, "Appeal filed successfully"
            
        except Exception as e:
            current_app.logger.error(f"Failed to process appeal for flag {flag.id}: {e}")
            db.session.rollback()
            return False, "Failed to process appeal"
    
    def get_user_permissions(self, user_id: int, level: ModerationLevel) -> List[str]:
        """Get permissions for user at specific level"""
        # In a real implementation, this would check user's actual level
        # For now, return level permissions
        return self.level_permissions.get(level, [])
    
    def can_perform_action(self, user_id: int, action: str, 
                          flag_level: str) -> bool:
        """
        Check if user can perform action on flag at specific level
        
        Args:
            user_id: User ID to check
            action: Action to perform
            flag_level: Current flag moderation level
            
        Returns:
            True if action is permitted
        """
        # Get user's moderation level (simplified)
        user_level = self._get_user_level(user_id)
        
        if not user_level:
            return False
        
        # Check if user level is high enough
        level_hierarchy = {
            ModerationLevel.LEVEL_1: 1,
            ModerationLevel.LEVEL_2: 2,
            ModerationLevel.LEVEL_3: 3
        }
        
        user_rank = level_hierarchy.get(user_level, 0)
        flag_rank = level_hierarchy.get(ModerationLevel(flag_level), 0)
        
        if user_rank < flag_rank:
            return False
        
        # Check specific permissions
        user_permissions = self.level_permissions.get(user_level, [])
        return action in user_permissions
    
    def _get_user_level(self, user_id: int) -> Optional[ModerationLevel]:
        """Get user's moderation level (simplified implementation)"""
        # In a real implementation, this would query user roles/permissions
        # For now, return a default level
        return ModerationLevel.LEVEL_1
    
    def get_escalation_stats(self) -> Dict:
        """Get escalation statistics"""
        stats = {
            'total_escalations': 0,
            'escalations_by_level': {},
            'escalations_by_reason': {},
            'average_resolution_time': 0,
            'escalation_success_rate': 0
        }
        
        # Count escalations by level
        for level in ModerationLevel:
            count = ContentFlag.query.filter(
                ContentFlag.escalated_to_level == level.value
            ).count()
            stats['escalations_by_level'][level.value] = count
            stats['total_escalations'] += count
        
        # Count escalations by reason
        escalation_reasons = db.session.query(
            ContentFlag.escalation_reason,
            func.count(ContentFlag.id)
        ).filter(
            ContentFlag.escalation_reason.isnot(None)
        ).group_by(ContentFlag.escalation_reason).all()
        
        for reason, count in escalation_reasons:
            stats['escalations_by_reason'][reason] = count
        
        # Calculate average resolution time for escalated items
        escalated_flags = ContentFlag.query.filter(
            ContentFlag.escalation_count > 0,
            ContentFlag.status == 'resolved'
        ).all()
        
        if escalated_flags:
            total_time = sum(
                (flag.resolved_at - flag.escalated_at).total_seconds()
                for flag in escalated_flags
                if flag.resolved_at and flag.escalated_at
            )
            stats['average_resolution_time'] = total_time / len(escalated_flags) / 3600  # hours
        
        return stats


class WorkflowManager:
    """Main workflow manager for moderation processes"""
    
    def __init__(self):
        self.escalation_workflow = EscalationWorkflow()
        
    def process_flag_lifecycle(self, flag: ContentFlag) -> Dict:
        """
        Process a flag through its complete lifecycle
        
        Args:
            flag: ContentFlag to process
            
        Returns:
            Processing results and actions taken
        """
        results = {
            'actions_taken': [],
            'escalations': [],
            'notifications_sent': [],
            'final_status': flag.status
        }
        
        # Check for automatic escalations
        escalation_rules = self.escalation_workflow.check_escalation_needed(flag)
        
        for rule in escalation_rules:
            if rule.auto_escalate:
                success = self.escalation_workflow.escalate_flag(
                    flag, rule.to_level, f"Auto-escalation: {rule.trigger.value}", 0
                )
                if success:
                    results['escalations'].append({
                        'to_level': rule.to_level.value,
                        'reason': rule.trigger.value,
                        'auto': True
                    })
                    results['actions_taken'].append('auto_escalated')
        
        # Check for SLA issues
        if flag.sla_breached:
            results['actions_taken'].append('sla_breached_notified')
            # In real implementation, send notifications
        
        # Check for legal review requirements
        if flag.legal_review_required and not flag.legal_review_completed:
            results['actions_taken'].append('legal_review_required')
            # In real implementation, notify legal team
        
        return results
    
    def assign_flag_optimally(self, flag: ContentFlag) -> Optional[int]:
        """
        Assign flag to optimal moderator based on workload and expertise
        
        Args:
            flag: ContentFlag to assign
            
        Returns:
            Moderator ID or None if no suitable moderator found
        """
        # This is a simplified implementation
        # In production, this would consider moderator workload, expertise, availability
        
        from app.identity.models.user import User
        from app.identity.models.roles_permission import UserRole
        
        # Get moderators for the flag's level
        level = ModerationLevel(flag.moderation_level)
        team = self.escalation_workflow._get_team_for_level(level)
        
        # Find available moderators (simplified)
        available_moderators = User.query.join(UserRole).join(
            UserRole.role
        ).filter(
            and_(
                User.is_active == True,
                UserRole.role.name == 'moderator'
            )
        ).limit(10).all()
        
        if available_moderators:
            # Return first available moderator (simplified)
            return available_moderators[0].id
        
        return None


# Global workflow manager instance
workflow_manager = WorkflowManager()
