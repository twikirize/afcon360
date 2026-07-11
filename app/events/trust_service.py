# app/events/trust_service.py
"""
Trust-based auto-publish system for events
Determines user trust levels and auto-publish eligibility
"""

from datetime import datetime, timezone, timedelta
from typing import Tuple, Dict, Optional
from sqlalchemy import func
from app.extensions import db
from app.identity.models.user import User
from app.events.models import Event
from app.events.constants import EventStatus
from app.auth.helpers import has_global_role


class TrustLevel:
    HIGH = "high"      # Auto-publish immediately
    MEDIUM = "medium"  # Auto-publish after approval
    LOW = "low"        # Manual publishing required


class EventTrustService:
    
    @staticmethod
    def calculate_trust_level(user: User) -> TrustLevel:
        """
        Calculate trust level based on multiple factors and admin settings
        Returns: TrustLevel enum
        """
        # Load admin settings
        from app.events.settings_model import EventSettings
        settings = EventSettings.get()
        
        # Check if trust-based publishing is disabled
        if not settings.enable_trust_based_publishing:
            return TrustLevel.LOW
        
        score = 0
        
        # 1. Role-based trust (highest weight)
        if settings.enable_role_bypass:
            if has_global_role(user, 'super_admin') or has_global_role(user, 'owner'):
                return TrustLevel.HIGH
            elif has_global_role(user, 'admin'):
                score += 40
            elif has_global_role(user, 'event_manager') or has_global_role(user, 'moderator'):
                score += 25
        
        # 2. KYC verification
        if settings.enable_kyc_boost:
            kyc_level = getattr(user, 'kyc_level', 0)
            if kyc_level >= 2:
                score += 30
            elif kyc_level >= 1:
                score += 15
        
        # 3. Email verification
        if getattr(user, 'is_verified', False):
            score += 15
        
        # 4. Account age
        if settings.enable_account_age_boost:
            now = datetime.now(timezone.utc)
            if user.created_at.tzinfo is None:
                created_at = user.created_at.replace(tzinfo=timezone.utc)
            else:
                created_at = user.created_at
            account_age_days = (now - created_at).days
            if account_age_days >= 30:
                score += 15
            elif account_age_days >= 7:
                score += 8
        
        # 5. Event history
        if settings.enable_event_history_boost:
            successful_events = Event.query.filter_by(
                created_by_id=user.id,
                status=EventStatus.COMPLETED
            ).count()
            
            if successful_events >= 5:
                score += 20
            elif successful_events >= 2:
                score += 10
        
        # 6. No violations (bonus)
        # TODO: Check for content flags, suspensions, etc.
        
        # Determine trust level based on admin-configured thresholds
        if score >= settings.high_trust_threshold:
            return TrustLevel.HIGH
        elif score >= settings.medium_trust_threshold:
            return TrustLevel.MEDIUM
        else:
            return TrustLevel.LOW
    
    @staticmethod
    def should_auto_publish(user: User, trust_level: TrustLevel = None) -> Tuple[bool, str]:
        """
        Determine if user's events should be auto-published
        Returns: (should_auto_publish, reason)
        """
        if trust_level is None:
            trust_level = EventTrustService.calculate_trust_level(user)
        
        if trust_level == TrustLevel.HIGH:
            return True, "High trust user - auto-publishing immediately"
        elif trust_level == TrustLevel.MEDIUM:
            return True, "Medium trust user - auto-publishing after approval"
        else:
            return False, "Low trust user - manual publishing required"
    
    @staticmethod
    def get_trust_analysis(user: User) -> Dict:
        """
        Get detailed trust analysis for debugging/admin purposes
        """
        trust_level = EventTrustService.calculate_trust_level(user)
        should_auto, reason = EventTrustService.should_auto_publish(user, trust_level)
        
        # Calculate account age for the analysis
        now = datetime.now(timezone.utc)
        if user.created_at.tzinfo is None:
            created_at = user.created_at.replace(tzinfo=timezone.utc)
        else:
            created_at = user.created_at
        account_age_days = (now - created_at).days
        
        return {
            'user_id': user.id,
            'username': user.username,
            'trust_level': trust_level,
            'should_auto_publish': should_auto,
            'reason': reason,
            'factors': {
                'roles': [role.role.name for role in user.roles] if hasattr(user, 'roles') else [],
                'kyc_level': getattr(user, 'kyc_level', 0),
                'is_verified': getattr(user, 'is_verified', False),
                'account_age_days': account_age_days,
                'successful_events': Event.query.filter_by(
                    created_by_id=user.id,
                    status=EventStatus.COMPLETED
                ).count()
            }
        }
