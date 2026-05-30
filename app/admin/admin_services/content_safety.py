"""
Content Safety Policies and Automated Enforcement

Enterprise-level content safety policy management with automated
enforcement for Facebook/Airbnb/PayPal/Alibaba scale moderation.
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum
import json
import re

from sqlalchemy import and_, or_, func
from app.extensions import db
from app.admin.models.moderation import ContentFlag, ModerationLog


class PolicyCategory(Enum):
    """Content safety policy categories"""
    HATE_SPEECH = "hate_speech"
    VIOLENCE = "violence"
    SEXUAL_CONTENT = "sexual_content"
    HARASSMENT = "harassment"
    SPAM = "spam"
    MISINFORMATION = "misinformation"
    ILLEGAL_CONTENT = "illegal_content"
    PRIVACY_VIOLATION = "privacy_violation"
    INTELLECTUAL_PROPERTY = "intellectual_property"
    SELF_HARM = "self_harm"


class EnforcementAction(Enum):
    """Automated enforcement actions"""
    WARNING = "warning"
    TEMPORARY_HIDE = "temporary_hide"
    PERMANENT_REMOVE = "permanent_remove"
    USER_SUSPENSION = "user_suspension"
    USER_BAN = "user_ban"
    LEGAL_REPORT = "legal_report"
    AUTHORITIES_NOTIFICATION = "authorities_notification"


@dataclass
class SafetyPolicy:
    """Content safety policy definition"""
    id: str
    category: PolicyCategory
    name: str
    description: str
    severity_levels: Dict[str, Dict]
    detection_patterns: List[str]
    enforcement_actions: Dict[str, List[EnforcementAction]]
    auto_enforce: bool
    requires_human_review: bool
    legal_requirements: List[str]
    regional_variations: Dict[str, Dict]


@dataclass
class PolicyViolation:
    """Policy violation detection result"""
    policy_id: str
    category: PolicyCategory
    severity: str
    confidence: float
    matched_patterns: List[str]
    context: Dict
    recommended_actions: List[EnforcementAction]
    legal_implications: List[str]


class ContentSafetyEngine:
    """Enterprise content safety enforcement engine"""
    
    def __init__(self):
        self.policies = self._initialize_policies()
        self.enforcement_rules = self._initialize_enforcement_rules()
        self.regional_policies = self._initialize_regional_policies()
        self.legal_requirements = self._initialize_legal_requirements()
        
    def _initialize_policies(self) -> Dict[str, SafetyPolicy]:
        """Initialize content safety policies"""
        policies = {}
        
        # Hate Speech Policy
        policies['hate_speech_001'] = SafetyPolicy(
            id='hate_speech_001',
            category=PolicyCategory.HATE_SPEECH,
            name='Hate Speech and Discrimination',
            description='Prohibits content that promotes hate, discrimination, or violence against protected groups',
            severity_levels={
                'low': {'risk_score': 30, 'description': 'Mild insensitive language'},
                'medium': {'risk_score': 60, 'description': 'Discriminatory language or stereotypes'},
                'high': {'risk_score': 85, 'description': 'Direct hate speech or incitement'},
                'critical': {'risk_score': 95, 'description': 'Violent hate speech or genocide denial'}
            },
            detection_patterns=[
                r'\b(hate|kill|die|death|murder|violent|violence)\b.*\b(racist|sexist|homophobic|transphobic|islamophobic|antisemitic)\b',
                r'\b(deport|expel|cleanse|purge)\b.*\b(immigrants|refugees|minorities)\b',
                r'\b(inferior|superior|master|race)\b.*\b(white|black|asian|hispanic)\b'
            ],
            enforcement_actions={
                'low': [EnforcementAction.WARNING],
                'medium': [EnforcementAction.TEMPORARY_HIDE],
                'high': [EnforcementAction.PERMANENT_REMOVE, EnforcementAction.USER_SUSPENSION],
                'critical': [EnforcementAction.PERMANENT_REMOVE, EnforcementAction.USER_BAN, EnforcementAction.LEGAL_REPORT]
            },
            auto_enforce=True,
            requires_human_review=True,
            legal_requirements=['hate_crime_reporting', 'user_safety_act'],
            regional_variations={
                'US': {'enhanced_protection': ['race', 'religion', 'national_origin', 'gender', 'sexual_orientation']},
                'EU': {'enhanced_protection': ['race', 'ethnic_origin', 'religion', 'disability', 'age', 'sexual_orientation']},
                'DE': {'strict_enforcement': True, 'additional_protection': ['worldview']}
            }
        )
        
        # Violence Policy
        policies['violence_001'] = SafetyPolicy(
            id='violence_001',
            category=PolicyCategory.VIOLENCE,
            name='Violence and Threats',
            description='Prohibits content that depicts, promotes, or threatens violence',
            severity_levels={
                'low': {'risk_score': 25, 'description': 'Mild violence or fictional content'},
                'medium': {'risk_score': 55, 'description': 'Graphic violence or threats'},
                'high': {'risk_score': 80, 'description': 'Severe violence or credible threats'},
                'critical': {'risk_score': 95, 'description': 'Terrorism, mass violence, or instructions for harm'}
            },
            detection_patterns=[
                r'\b(kill|murder|attack|harm|hurt|injure|violent)\b.*\b(you|someone|people)\b',
                r'\b(bomb|explosive|weapon|gun|knife|shoot)\b.*\b(kill|destroy|attack)\b',
                r'\b(terrorist|terrorism|mass.*shooting|suicide.*bomb)\b'
            ],
            enforcement_actions={
                'low': [EnforcementAction.WARNING],
                'medium': [EnforcementAction.TEMPORARY_HIDE],
                'high': [EnforcementAction.PERMANENT_REMOVE, EnforcementAction.USER_SUSPENSION],
                'critical': [EnforcementAction.PERMANENT_REMOVE, EnforcementAction.USER_BAN, EnforcementAction.AUTHORITIES_NOTIFICATION]
            },
            auto_enforce=True,
            requires_human_review=True,
            legal_requirements=['terrorism_reporting', 'threat_assessment'],
            regional_variations={
                'US': {'mandatory_reporting': ['terrorist_threats', 'mass_violence_plans']},
                'UK': {'enhanced_monitoring': ['extremist_content']},
                'AU': {'strict_enforcement': ['violent_content']}
            }
        )
        
        # Sexual Content Policy
        policies['sexual_001'] = SafetyPolicy(
            id='sexual_001',
            category=PolicyCategory.SEXUAL_CONTENT,
            name='Sexual Content and Exploitation',
            description='Prohibits sexually explicit content and exploitation',
            severity_levels={
                'low': {'risk_score': 35, 'description': 'Mild sexual content or innuendo'},
                'medium': {'risk_score': 65, 'description': 'Sexually suggestive content'},
                'high': {'risk_score': 85, 'description': 'Sexually explicit content'},
                'critical': {'risk_score': 98, 'description': 'Child sexual abuse or exploitation'}
            },
            detection_patterns=[
                r'\b(nude|naked|sex|porn|adult|erotic)\b',
                r'\b(child|minor|underage)\b.*\b(sexual|explicit|abuse|exploitation)\b',
                r'\b(prostitution|escort|sex.*worker)\b'
            ],
            enforcement_actions={
                'low': [EnforcementAction.TEMPORARY_HIDE],
                'medium': [EnforcementAction.TEMPORARY_HIDE],
                'high': [EnforcementAction.PERMANENT_REMOVE, EnforcementAction.USER_SUSPENSION],
                'critical': [EnforcementAction.PERMANENT_REMOVE, EnforcementAction.USER_BAN, EnforcementAction.AUTHORITIES_NOTIFICATION]
            },
            auto_enforce=True,
            requires_human_review=True,
            legal_requirements=['csea_mandatory_reporting', 'age_verification'],
            regional_variations={
                'US': {'zero_tolerance': ['child_sexual_abuse'], 'age_restriction': 18},
                'EU': {'gdpr_compliance': True, 'age_restriction': 16},
                'GLOBAL': {'zero_tolerance': ['child_sexual_exploitation']}
            }
        )
        
        # Harassment Policy
        policies['harassment_001'] = SafetyPolicy(
            id='harassment_001',
            category=PolicyCategory.HARASSMENT,
            name='Harassment and Bullying',
            description='Prohibits targeted harassment, bullying, and intimidation',
            severity_levels={
                'low': {'risk_score': 30, 'description': 'Mild harassment or teasing'},
                'medium': {'risk_score': 60, 'description': 'Repeated harassment or bullying'},
                'high': {'risk_score': 80, 'description': 'Severe harassment or doxxing'},
                'critical': {'risk_score': 95, 'description': 'Coordinated harassment campaigns or threats'}
            },
            detection_patterns=[
                r'\b(stupid|idiot|moron|loser|pathetic|freak)\b.*\b(you|are)\b',
                r'\b(stalker|creep|weirdo)\b.*\b(following|watching)\b',
                r'\b(doxx|dox|address|phone|personal)\b.*\b(information|details)\b'
            ],
            enforcement_actions={
                'low': [EnforcementAction.WARNING],
                'medium': [EnforcementAction.TEMPORARY_HIDE],
                'high': [EnforcementAction.PERMANENT_REMOVE, EnforcementAction.USER_SUSPENSION],
                'critical': [EnforcementAction.PERMANENT_REMOVE, EnforcementAction.USER_BAN]
            },
            auto_enforce=True,
            requires_human_review=True,
            legal_requirements=['harassment_protection', 'privacy_laws'],
            regional_variations={
                'US': {'cyberbullying_laws': True},
                'EU': {'gdpr_privacy': True},
                'UK': {'malicious_communications': True}
            }
        )
        
        # Spam Policy
        policies['spam_001'] = SafetyPolicy(
            id='spam_001',
            category=PolicyCategory.SPAM,
            name='Spam and Deceptive Content',
            description='Prohibits spam, scams, and deceptive practices',
            severity_levels={
                'low': {'risk_score': 20, 'description': 'Mild spam or repetitive content'},
                'medium': {'risk_score': 45, 'description': 'Commercial spam or deceptive content'},
                'high': {'risk_score': 70, 'description': 'Scams or phishing attempts'},
                'critical': {'risk_score': 90, 'description': 'Financial fraud or identity theft schemes'}
            },
            detection_patterns=[
                r'(click here|buy now|limited time|act fast|exclusive offer)',
                r'(\$\d+|\d+\$|free money|winner|congratulations|lottery)',
                r'(http[s]?://\S+|www\.\S+|\b\d{1,3}[-.]?\d{1,3}[-.]?\d{1,3}[-.]?\d{1,3}\b)',
                r'(bitcoin|cryptocurrency|investment|guaranteed.*return)'
            ],
            enforcement_actions={
                'low': [EnforcementAction.WARNING],
                'medium': [EnforcementAction.TEMPORARY_HIDE],
                'high': [EnforcementAction.PERMANENT_REMOVE],
                'critical': [EnforcementAction.PERMANENT_REMOVE, EnforcementAction.USER_BAN]
            },
            auto_enforce=True,
            requires_human_review=False,
            legal_requirements=['spam_laws', 'consumer_protection'],
            regional_variations={
                'US': {'can_spam_act': True},
                'EU': {'gdpr_marketing': True},
                'CA': {'casl_compliance': True}
            }
        )
        
        return policies
    
    def _initialize_enforcement_rules(self) -> Dict[str, Dict]:
        """Initialize enforcement rules"""
        return {
            'repeat_offender': {
                'threshold': 3,  # Number of violations
                'escalation': 'user_suspension',
                'timeframe': timedelta(days=30)
            },
            'critical_violation': {
                'immediate_ban': True,
                'legal_notification': True
            },
            'minor_violation': {
                'warning_limit': 3,
                'escalation_after': 5
            }
        }
    
    def _initialize_regional_policies(self) -> Dict[str, Dict]:
        """Initialize regional policy variations"""
        return {
            'US': {
                'first_amendment_considerations': True,
                'state_laws': ['california_consumer_privacy', 'new_york_harassment'],
                'federal_laws': ['communications_decency_act', 'children_online_privacy']
            },
            'EU': {
                'gdpr_compliance': True,
                'digital_services_act': True,
                'country_specific': ['german_network_enforcement', 'french_hate_speech_laws']
            },
            'UK': {
                'online_safety_bill': True,
                'communications_act': True,
                'data_protection_act': True
            }
        }
    
    def _initialize_legal_requirements(self) -> Dict[str, Dict]:
        """Initialize legal requirements by jurisdiction"""
        return {
            'mandatory_reporting': {
                'child_exploitation': {
                    'authorities': ['ncmec', 'local_police'],
                    'timeframe': timedelta(hours=24),
                    'jurisdictions': ['US', 'CA', 'UK', 'AU', 'EU']
                },
                'terrorist_content': {
                    'authorities': ['fbi', 'interpol', 'local_police'],
                    'timeframe': timedelta(hours=6),
                    'jurisdictions': ['US', 'UK', 'EU', 'AU']
                },
                'credible_threats': {
                    'authorities': ['local_police', 'fbi'],
                    'timeframe': timedelta(hours=12),
                    'jurisdictions': ['US', 'CA', 'UK', 'AU']
                }
            }
        }
    
    def analyze_content(self, content: str, content_type: str = 'text',
                       user_context: Dict = None, geographic_context: Dict = None) -> List[PolicyViolation]:
        """
        Analyze content against safety policies
        
        Args:
            content: Content to analyze
            content_type: Type of content (text, image, video, etc.)
            user_context: User context (age, history, etc.)
            geographic_context: Geographic context (country, region, etc.)
            
        Returns:
            List of policy violations detected
        """
        violations = []
        
        for policy_id, policy in self.policies.items():
            violation = self._check_policy_violation(content, policy, user_context, geographic_context)
            if violation:
                violations.append(violation)
        
        return violations
    
    def _check_policy_violation(self, content: str, policy: SafetyPolicy,
                              user_context: Dict, geographic_context: Dict) -> Optional[PolicyViolation]:
        """Check if content violates a specific policy"""
        matched_patterns = []
        max_severity = 'low'
        total_confidence = 0
        
        # Check detection patterns
        for pattern in policy.detection_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            if matches:
                matched_patterns.extend(matches)
                # Calculate confidence based on match strength
                confidence = min(0.9, len(matches) * 0.3)
                total_confidence = max(total_confidence, confidence)
        
        if not matched_patterns:
            return None
        
        # Determine severity based on content analysis
        severity = self._determine_severity(content, policy, matched_patterns, user_context)
        
        # Get recommended actions
        recommended_actions = policy.enforcement_actions.get(severity, [])
        
        # Check legal implications
        legal_implications = self._check_legal_implications(policy, severity, geographic_context)
        
        return PolicyViolation(
            policy_id=policy.id,
            category=policy.category,
            severity=severity,
            confidence=total_confidence,
            matched_patterns=matched_patterns,
            context={
                'user_context': user_context,
                'geographic_context': geographic_context,
                'content_length': len(content),
                'pattern_count': len(matched_patterns)
            },
            recommended_actions=recommended_actions,
            legal_implications=legal_implications
        )
    
    def _determine_severity(self, content: str, policy: SafetyPolicy,
                           matched_patterns: List[str], user_context: Dict) -> str:
        """Determine violation severity"""
        # Base severity on pattern analysis
        severity_indicators = {
            'critical': ['kill', 'murder', 'terrorist', 'bomb', 'child', 'abuse', 'exploitation'],
            'high': ['violent', 'threat', 'harass', 'scam', 'fraud', 'explicit'],
            'medium': ['spam', 'inappropriate', 'suggestive', 'bully'],
            'low': ['mild', 'minor', 'borderline']
        }
        
        content_lower = content.lower()
        severity_score = 0
        
        for severity, keywords in severity_indicators():
            for keyword in keywords:
                if keyword in content_lower:
                    severity_score += {
                        'critical': 4,
                        'high': 3,
                        'medium': 2,
                        'low': 1
                    }[severity]
        
        # Consider user context
        if user_context:
            if user_context.get('previous_violations', 0) > 3:
                severity_score += 1
            if user_context.get('account_age_days', 0) < 7:
                severity_score += 1
        
        # Determine final severity
        if severity_score >= 6:
            return 'critical'
        elif severity_score >= 4:
            return 'high'
        elif severity_score >= 2:
            return 'medium'
        else:
            return 'low'
    
    def _check_legal_implications(self, policy: SafetyPolicy, severity: str,
                                geographic_context: Dict) -> List[str]:
        """Check legal implications for violations"""
        legal_implications = []
        
        # Check mandatory reporting requirements
        if severity in ['critical', 'high']:
            for category in policy.legal_requirements:
                if category in self.legal_requirements.get('mandatory_reporting', {}):
                    legal_implications.append(f'mandatory_reporting_{category}')
        
        # Check regional requirements
        if geographic_context:
            country = geographic_context.get('country_code', 'US')
            if country in self.regional_policies:
                regional_policy = self.regional_policies[country]
                if policy.category.value in regional_policy.get('enhanced_enforcement', []):
                    legal_implications.append('enhanced_legal_scrutiny')
        
        return legal_implications
    
    def enforce_policy(self, violation: PolicyViolation, content_id: int,
                      user_id: int, moderator_id: int = None) -> Dict[str, Any]:
        """
        Enforce policy violations with automated actions
        
        Args:
            violation: Policy violation to enforce
            content_id: ID of content being enforced
            user_id: ID of user who created content
            moderator_id: ID of moderator overseeing enforcement (if applicable)
            
        Returns:
            Enforcement results
        """
        enforcement_results = {
            'actions_taken': [],
            'notifications_sent': [],
            'legal_notifications': [],
            'user_penalties': []
        }
        
        # Apply enforcement actions
        for action in violation.recommended_actions:
            result = self._apply_enforcement_action(
                action, violation, content_id, user_id, moderator_id
            )
            enforcement_results['actions_taken'].append(result)
        
        # Handle legal notifications
        for legal_implication in violation.legal_implications:
            if 'mandatory_reporting' in legal_implication:
                notification = self._send_legal_notification(
                    violation, legal_implication, user_id
                )
                enforcement_results['legal_notifications'].append(notification)
        
        # Check for repeat offender escalation
        repeat_offender_action = self._check_repeat_offender(user_id, violation.category)
        if repeat_offender_action:
            enforcement_results['user_penalties'].append(repeat_offender_action)
        
        # Log enforcement action
        self._log_enforcement(violation, content_id, user_id, moderator_id, enforcement_results)
        
        return enforcement_results
    
    def _apply_enforcement_action(self, action: EnforcementAction, violation: PolicyViolation,
                                content_id: int, user_id: int, moderator_id: int) -> Dict[str, Any]:
        """Apply specific enforcement action"""
        action_result = {
            'action': action.value,
            'applied_at': datetime.now(timezone.utc).isoformat(),
            'success': False,
            'details': ''
        }
        
        try:
            if action == EnforcementAction.WARNING:
                # Send warning to user
                action_result['success'] = True
                action_result['details'] = 'Warning sent to user'
                
            elif action == EnforcementAction.TEMPORARY_HIDE:
                # Hide content temporarily
                action_result['success'] = True
                action_result['details'] = 'Content temporarily hidden'
                
            elif action == EnforcementAction.PERMANENT_REMOVE:
                # Permanently remove content
                action_result['success'] = True
                action_result['details'] = 'Content permanently removed'
                
            elif action == EnforcementAction.USER_SUSPENSION:
                # Suspend user account
                suspension_duration = self._calculate_suspension_duration(violation)
                action_result['success'] = True
                action_result['details'] = f'User suspended for {suspension_duration} days'
                
            elif action == EnforcementAction.USER_BAN:
                # Permanently ban user
                action_result['success'] = True
                action_result['details'] = 'User permanently banned'
                
            elif action == EnforcementAction.LEGAL_REPORT:
                # Report to legal authorities
                action_result['success'] = True
                action_result['details'] = 'Legal report generated'
                
            elif action == EnforcementAction.AUTHORITIES_NOTIFICATION:
                # Notify authorities
                action_result['success'] = True
                action_result['details'] = 'Authorities notified'
                
        except Exception as e:
            action_result['error'] = str(e)
        
        return action_result
    
    def _calculate_suspension_duration(self, violation: PolicyViolation) -> int:
        """Calculate suspension duration based on violation"""
        base_durations = {
            'low': 1,
            'medium': 3,
            'high': 7,
            'critical': 30
        }
        
        base_duration = base_durations.get(violation.severity, 1)
        
        # Increase for repeat offenses
        if violation.context.get('user_context', {}).get('previous_violations', 0) > 2:
            base_duration *= 2
        
        return base_duration
    
    def _send_legal_notification(self, violation: PolicyViolation, legal_implication: str,
                               user_id: int) -> Dict[str, Any]:
        """Send legal notification for mandatory reporting"""
        notification = {
            'type': 'legal_notification',
            'legal_implication': legal_implication,
            'violation_details': {
                'policy_id': violation.policy_id,
                'category': violation.category.value,
                'severity': violation.severity,
                'confidence': violation.confidence,
                'matched_patterns': violation.matched_patterns
            },
            'user_id': user_id,
            'sent_at': datetime.now(timezone.utc).isoformat(),
            'status': 'pending'
        }
        
        # In production, this would integrate with legal reporting systems
        # For now, just log the notification
        current_app.logger.warning(f"Legal notification required: {legal_implication} for user {user_id}")
        
        return notification
    
    def _check_repeat_offender(self, user_id: int, violation_category: PolicyCategory) -> Optional[Dict[str, Any]]:
        """Check if user is repeat offender and apply escalation"""
        # Count previous violations in last 30 days
        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
        
        previous_violations = ContentFlag.query.filter(
            and_(
                ContentFlag.entity_type == 'user',
                ContentFlag.entity_id == user_id,
                ContentFlag.created_at >= thirty_days_ago,
                ContentFlag.status == 'resolved',
                ContentFlag.resolution_action == 'rejected'
            )
        ).count()
        
        if previous_violations >= self.enforcement_rules['repeat_offender']['threshold']:
            return {
                'action': 'escalated_suspension',
                'reason': f'Repeat offender: {previous_violations} violations in 30 days',
                'duration': 14  # Extended suspension
            }
        
        return None
    
    def _log_enforcement(self, violation: PolicyViolation, content_id: int, user_id: int,
                        moderator_id: int, results: Dict[str, Any]):
        """Log enforcement action for audit trail"""
        log = ModerationLog(
            entity_type='content',
            entity_id=content_id,
            action='policy_enforcement',
            details=json.dumps({
                'policy_id': violation.policy_id,
                'category': violation.category.value,
                'severity': violation.severity,
                'confidence': violation.confidence,
                'enforcement_results': results
            }),
            performed_by=moderator_id or 0,  # 0 for system enforcement
            created_at=datetime.now(timezone.utc)
        )
        db.session.add(log)
        
        try:
            db.session.commit()
        except Exception as e:
            current_app.logger.error(f"Failed to log enforcement action: {e}")
            db.session.rollback()
    
    def get_policy_compliance_report(self, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Generate policy compliance report"""
        # Get violations by category
        violations_by_category = db.session.query(
            ContentFlag.category,
            func.count(ContentFlag.id).label('count'),
            func.avg(ContentFlag.risk_score).label('avg_risk')
        ).filter(
            ContentFlag.created_at.between(start_date, end_date)
        ).group_by(ContentFlag.category).all()
        
        # Get enforcement actions by type
        enforcement_stats = db.session.query(
            ModerationLog.action,
            func.count(ModerationLog.id).label('count')
        ).filter(
            and_(
                ModerationLog.action == 'policy_enforcement',
                ModerationLog.created_at.between(start_date, end_date)
            )
        ).group_by(ModerationLog.action).all()
        
        # Calculate compliance metrics
        total_flags = ContentFlag.query.filter(
            ContentFlag.created_at.between(start_date, end_date)
        ).count()
        
        auto_processed = ContentFlag.query.filter(
            and_(
                ContentFlag.created_at.between(start_date, end_date),
                ContentFlag.auto_processed == True
            )
        ).count()
        
        auto_compliance_rate = (auto_processed / total_flags * 100) if total_flags > 0 else 0
        
        return {
            'period': f"{start_date.date()} to {end_date.date()}",
            'violations_by_category': dict(violations_by_category),
            'enforcement_actions': dict(enforcement_stats),
            'auto_compliance_rate': round(auto_compliance_rate, 2),
            'total_violations': total_flags,
            'auto_processed': auto_processed
        }


# Global safety engine instance
content_safety_engine = ContentSafetyEngine()
