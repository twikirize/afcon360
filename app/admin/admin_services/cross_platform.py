"""
Cross-Platform Moderation Tools and APIs

Enterprise-level cross-platform moderation system supporting
multiple content platforms with unified moderation workflows.
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum
import json
import requests
from abc import ABC, abstractmethod

from sqlalchemy import func, and_, or_, desc
from app.extensions import db


class PlatformType(Enum):
    """Supported content platforms"""
    WEB = "web"
    MOBILE_IOS = "mobile_ios"
    MOBILE_ANDROID = "mobile_android"
    API = "api"
    WEBHOOK = "webhook"
    EMAIL = "email"
    SOCIAL_MEDIA = "social_media"
    MESSAGING = "messaging"


class ModerationAction(Enum):
    """Cross-platform moderation actions"""
    HIDE_CONTENT = "hide_content"
    REMOVE_CONTENT = "remove_content"
    SUSPEND_USER = "suspend_user"
    BAN_USER = "ban_user"
    WARN_USER = "warn_user"
    QUARANTINE_CONTENT = "quarantine_content"
    FLAG_CONTENT = "flag_content"


@dataclass
class PlatformConfig:
    """Platform configuration"""
    platform_id: str
    platform_type: PlatformType
    name: str
    api_endpoint: Optional[str]
    auth_method: str
    rate_limits: Dict[str, int]
    supported_actions: List[ModerationAction]
    webhook_url: Optional[str]
    custom_headers: Dict[str, str]


@dataclass
class CrossPlatformContent:
    """Content representation across platforms"""
    content_id: str
    platform_id: str
    platform_type: PlatformType
    content_type: str
    content_data: Dict[str, Any]
    user_id: str
    user_data: Dict[str, Any]
    metadata: Dict[str, Any]
    created_at: datetime
    platform_specific: Dict[str, Any]


class PlatformAdapter(ABC):
    """Abstract base class for platform adapters"""
    
    @abstractmethod
    def authenticate(self) -> bool:
        """Authenticate with the platform"""
        pass
    
    @abstractmethod
    def fetch_content(self, content_id: str) -> Optional[CrossPlatformContent]:
        """Fetch content from platform"""
        pass
    
    @abstractmethod
    def apply_action(self, content_id: str, action: ModerationAction, 
                    reason: str, moderator_id: str) -> bool:
        """Apply moderation action to content"""
        pass
    
    @abstractmethod
    def get_user_info(self, user_id: str) -> Dict[str, Any]:
        """Get user information from platform"""
        pass
    
    @abstractmethod
    def send_notification(self, user_id: str, message: str, 
                         notification_type: str) -> bool:
        """Send notification to user"""
        pass


class WebPlatformAdapter(PlatformAdapter):
    """Web platform adapter for internal content"""
    
    def __init__(self, config: PlatformConfig):
        self.config = config
        self.authenticated = False
    
    def authenticate(self) -> bool:
        """Web platform uses internal authentication"""
        self.authenticated = True
        return True
    
    def fetch_content(self, content_id: str) -> Optional[CrossPlatformContent]:
        """Fetch content from web platform"""
        # In production, this would query the actual content
        return CrossPlatformContent(
            content_id=content_id,
            platform_id=self.config.platform_id,
            platform_type=PlatformType.WEB,
            content_type='text',
            content_data={'text': 'Sample content'},
            user_id='user_123',
            user_data={'username': 'sample_user'},
            metadata={'source': 'web'},
            created_at=datetime.now(timezone.utc),
            platform_specific={}
        )
    
    def apply_action(self, content_id: str, action: ModerationAction, 
                    reason: str, moderator_id: str) -> bool:
        """Apply moderation action on web platform"""
        # In production, this would update the actual content
        return True
    
    def get_user_info(self, user_id: str) -> Dict[str, Any]:
        """Get user information from web platform"""
        return {
            'user_id': user_id,
            'username': f'user_{user_id}',
            'email': f'user_{user_id}@example.com',
            'registration_date': datetime.now(timezone.utc) - timedelta(days=30)
        }
    
    def send_notification(self, user_id: str, message: str, 
                         notification_type: str) -> bool:
        """Send notification via web platform"""
        # In production, this would send actual notification
        return True


class MobilePlatformAdapter(PlatformAdapter):
    """Mobile platform adapter for iOS/Android apps"""
    
    def __init__(self, config: PlatformConfig):
        self.config = config
        self.authenticated = False
        self.api_key = None
    
    def authenticate(self) -> bool:
        """Authenticate with mobile platform API"""
        # In production, this would use actual API authentication
        self.api_key = "mock_api_key"
        self.authenticated = True
        return True
    
    def fetch_content(self, content_id: str) -> Optional[CrossPlatformContent]:
        """Fetch content from mobile platform"""
        return CrossPlatformContent(
            content_id=content_id,
            platform_id=self.config.platform_id,
            platform_type=PlatformType.MOBILE_IOS if 'ios' in self.config.platform_id else PlatformType.MOBILE_ANDROID,
            content_type='mobile_post',
            content_data={'text': 'Mobile content', 'media_urls': []},
            user_id='mobile_user_123',
            user_data={'device_id': 'device_123', 'app_version': '2.1.0'},
            metadata={'source': 'mobile_app'},
            created_at=datetime.now(timezone.utc),
            platform_specific={'push_notification_enabled': True}
        )
    
    def apply_action(self, content_id: str, action: ModerationAction, 
                    reason: str, moderator_id: str) -> bool:
        """Apply moderation action on mobile platform"""
        # Send push notification for immediate actions
        if action in [ModerationAction.REMOVE_CONTENT, ModerationAction.SUSPEND_USER]:
            self._send_push_notification(content_id, action, reason)
        return True
    
    def get_user_info(self, user_id: str) -> Dict[str, Any]:
        """Get user information from mobile platform"""
        return {
            'user_id': user_id,
            'username': f'mobile_{user_id}',
            'device_info': {'platform': 'iOS', 'version': '15.0'},
            'app_usage': {'last_active': datetime.now(timezone.utc)}
        }
    
    def send_notification(self, user_id: str, message: str, 
                         notification_type: str) -> bool:
        """Send push notification to mobile user"""
        return self._send_push_notification(user_id, notification_type, message)
    
    def _send_push_notification(self, target: str, action_or_type: str, message: str) -> bool:
        """Send push notification (mock implementation)"""
        # In production, this would use actual push notification service
        return True


class APIPlatformAdapter(PlatformAdapter):
    """API platform adapter for external integrations"""
    
    def __init__(self, config: PlatformConfig):
        self.config = config
        self.authenticated = False
        self.api_client = None
    
    def authenticate(self) -> bool:
        """Authenticate with external API"""
        try:
            # Mock API authentication
            self.api_client = requests.Session()
            self.api_client.headers.update(self.config.custom_headers)
            
            # In production, this would make actual authentication request
            self.authenticated = True
            return True
        except Exception:
            return False
    
    def fetch_content(self, content_id: str) -> Optional[CrossPlatformContent]:
        """Fetch content from external API"""
        if not self.authenticated:
            return None
        
        try:
            # Mock API call
            response = self.api_client.get(f"{self.config.api_endpoint}/content/{content_id}")
            if response.status_code == 200:
                data = response.json()
                return CrossPlatformContent(
                    content_id=content_id,
                    platform_id=self.config.platform_id,
                    platform_type=PlatformType.API,
                    content_type=data.get('type', 'unknown'),
                    content_data=data.get('content', {}),
                    user_id=data.get('user_id'),
                    user_data=data.get('user', {}),
                    metadata=data.get('metadata', {}),
                    created_at=datetime.fromisoformat(data.get('created_at')),
                    platform_specific=data.get('platform_specific', {})
                )
        except Exception:
            pass
        
        return None
    
    def apply_action(self, content_id: str, action: ModerationAction, 
                    reason: str, moderator_id: str) -> bool:
        """Apply moderation action via API"""
        if not self.authenticated:
            return False
        
        try:
            payload = {
                'action': action.value,
                'reason': reason,
                'moderator_id': moderator_id,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
            
            response = self.api_client.post(
                f"{self.config.api_endpoint}/content/{content_id}/moderate",
                json=payload
            )
            
            return response.status_code in [200, 201]
        except Exception:
            return False
    
    def get_user_info(self, user_id: str) -> Dict[str, Any]:
        """Get user information from API"""
        if not self.authenticated:
            return {}
        
        try:
            response = self.api_client.get(f"{self.config.api_endpoint}/users/{user_id}")
            if response.status_code == 200:
                return response.json()
        except Exception:
            pass
        
        return {}
    
    def send_notification(self, user_id: str, message: str, 
                         notification_type: str) -> bool:
        """Send notification via API"""
        if not self.authenticated:
            return False
        
        try:
            payload = {
                'user_id': user_id,
                'message': message,
                'type': notification_type,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
            
            response = self.api_client.post(
                f"{self.config.api_endpoint}/notifications",
                json=payload
            )
            
            return response.status_code in [200, 201]
        except Exception:
            return False


class CrossPlatformModeration:
    """Enterprise cross-platform moderation system"""
    
    def __init__(self):
        self.platforms = self._initialize_platforms()
        self.adapters = self._initialize_adapters()
        self.unified_actions = self._initialize_unified_actions()
        self.sync_manager = PlatformSyncManager()
        
    def _initialize_platforms(self) -> Dict[str, PlatformConfig]:
        """Initialize platform configurations"""
        platforms = {}
        
        # Web platform
        platforms['web_main'] = PlatformConfig(
            platform_id='web_main',
            platform_type=PlatformType.WEB,
            name='Main Web Platform',
            api_endpoint=None,
            auth_method='internal',
            rate_limits={'requests_per_minute': 1000},
            supported_actions=list(ModerationAction),
            webhook_url=None,
            custom_headers={}
        )
        
        # iOS mobile app
        platforms['mobile_ios'] = PlatformConfig(
            platform_id='mobile_ios',
            platform_type=PlatformType.MOBILE_IOS,
            name='iOS Mobile App',
            api_endpoint='https://api.mobile.example.com/ios',
            auth_method='api_key',
            rate_limits={'requests_per_minute': 500},
            supported_actions=[
                ModerationAction.HIDE_CONTENT,
                ModerationAction.REMOVE_CONTENT,
                ModerationAction.SUSPEND_USER,
                ModerationAction.WARN_USER
            ],
            webhook_url='https://webhook.example.com/ios',
            custom_headers={'X-API-Version': '2.0'}
        )
        
        # Android mobile app
        platforms['mobile_android'] = PlatformConfig(
            platform_id='mobile_android',
            platform_type=PlatformType.MOBILE_ANDROID,
            name='Android Mobile App',
            api_endpoint='https://api.mobile.example.com/android',
            auth_method='api_key',
            rate_limits={'requests_per_minute': 500},
            supported_actions=[
                ModerationAction.HIDE_CONTENT,
                ModerationAction.REMOVE_CONTENT,
                ModerationAction.SUSPEND_USER,
                ModerationAction.WARN_USER
            ],
            webhook_url='https://webhook.example.com/android',
            custom_headers={'X-API-Version': '2.0'}
        )
        
        # External API platform
        platforms['external_api'] = PlatformConfig(
            platform_id='external_api',
            platform_type=PlatformType.API,
            name='External API Integration',
            api_endpoint='https://api.partner.example.com',
            auth_method='oauth2',
            rate_limits={'requests_per_minute': 100},
            supported_actions=[
                ModerationAction.FLAG_CONTENT,
                ModerationAction.QUARANTINE_CONTENT
            ],
            webhook_url='https://webhook.example.com/partner',
            custom_headers={'Authorization': 'Bearer token_placeholder'}
        )
        
        return platforms
    
    def _initialize_adapters(self) -> Dict[str, PlatformAdapter]:
        """Initialize platform adapters"""
        adapters = {}
        
        for platform_id, config in self.platforms.items():
            if config.platform_type == PlatformType.WEB:
                adapters[platform_id] = WebPlatformAdapter(config)
            elif config.platform_type in [PlatformType.MOBILE_IOS, PlatformType.MOBILE_ANDROID]:
                adapters[platform_id] = MobilePlatformAdapter(config)
            elif config.platform_type == PlatformType.API:
                adapters[platform_id] = APIPlatformAdapter(config)
        
        return adapters
    
    def _initialize_unified_actions(self) -> Dict[ModerationAction, Dict[str, Any]]:
        """Initialize unified action mappings"""
        return {
            ModerationAction.HIDE_CONTENT: {
                'description': 'Hide content from public view',
                'reversible': True,
                'notification_required': True,
                'platform_support': 'all'
            },
            ModerationAction.REMOVE_CONTENT: {
                'description': 'Permanently remove content',
                'reversible': False,
                'notification_required': True,
                'platform_support': 'all'
            },
            ModerationAction.SUSPEND_USER: {
                'description': 'Temporarily suspend user account',
                'reversible': True,
                'notification_required': True,
                'platform_support': 'all'
            },
            ModerationAction.BAN_USER: {
                'description': 'Permanently ban user account',
                'reversible': False,
                'notification_required': True,
                'platform_support': 'web_main'
            },
            ModerationAction.WARN_USER: {
                'description': 'Send warning to user',
                'reversible': True,
                'notification_required': True,
                'platform_support': 'all'
            },
            ModerationAction.QUARANTINE_CONTENT: {
                'description': 'Place content in quarantine for review',
                'reversible': True,
                'notification_required': False,
                'platform_support': 'api'
            },
            ModerationAction.FLAG_CONTENT: {
                'description': 'Flag content for manual review',
                'reversible': True,
                'notification_required': False,
                'platform_support': 'all'
            }
        }
    
    def get_cross_platform_content(self, content_id: str, platform_id: str) -> Optional[CrossPlatformContent]:
        """Get content from any platform"""
        adapter = self.adapters.get(platform_id)
        if not adapter:
            return None
        
        if not adapter.authenticate():
            return None
        
        return adapter.fetch_content(content_id)
    
    def apply_cross_platform_action(self, content_id: str, platform_id: str, 
                                  action: ModerationAction, reason: str, 
                                  moderator_id: str) -> Dict[str, Any]:
        """Apply moderation action across platforms"""
        result = {
            'success': False,
            'platform': platform_id,
            'action': action.value,
            'content_id': content_id,
            'applied_at': datetime.now(timezone.utc).isoformat(),
            'platform_results': [],
            'sync_results': [],
            'errors': []
        }
        
        # Apply action on primary platform
        adapter = self.adapters.get(platform_id)
        if adapter and adapter.authenticate():
            try:
                success = adapter.apply_action(content_id, action, reason, moderator_id)
                result['platform_results'].append({
                    'platform': platform_id,
                    'success': success
                })
                result['success'] = success
                
                # Sync action to other platforms if needed
                if success:
                    sync_results = self.sync_manager.sync_action(
                        content_id, platform_id, action, reason, moderator_id
                    )
                    result['sync_results'] = sync_results
                    
            except Exception as e:
                result['errors'].append(f"Platform {platform_id}: {str(e)}")
        else:
            result['errors'].append(f"Failed to authenticate with platform {platform_id}")
        
        return result
    
    def get_unified_user_view(self, user_id: str) -> Dict[str, Any]:
        """Get unified view of user across all platforms"""
        user_view = {
            'user_id': user_id,
            'platforms': {},
            'total_content': 0,
            'violations': 0,
            'account_status': 'active',
            'last_activity': None
        }
        
        for platform_id, adapter in self.adapters.items():
            try:
                if adapter.authenticate():
                    user_info = adapter.get_user_info(user_id)
                    user_view['platforms'][platform_id] = user_info
                    
                    # Update aggregate stats
                    if user_info:
                        user_view['total_content'] += user_info.get('content_count', 0)
                        user_view['violations'] += user_info.get('violation_count', 0)
                        
                        # Update last activity
                        last_active = user_info.get('last_active')
                        if last_active and (not user_view['last_activity'] or last_active > user_view['last_activity']):
                            user_view['last_activity'] = last_active
                            
            except Exception as e:
                user_view['platforms'][platform_id] = {'error': str(e)}
        
        return user_view
    
    def send_cross_platform_notification(self, user_id: str, message: str, 
                                       notification_type: str, 
                                       target_platforms: List[str] = None) -> Dict[str, Any]:
        """Send notification across platforms"""
        results = {
            'user_id': user_id,
            'message': message,
            'type': notification_type,
            'sent_at': datetime.now(timezone.utc).isoformat(),
            'platform_results': {}
        }
        
        platforms_to_notify = target_platforms or list(self.adapters.keys())
        
        for platform_id in platforms_to_notify:
            adapter = self.adapters.get(platform_id)
            if adapter and adapter.authenticate():
                try:
                    success = adapter.send_notification(user_id, message, notification_type)
                    results['platform_results'][platform_id] = {
                        'success': success,
                        'sent_at': datetime.now(timezone.utc).isoformat()
                    }
                except Exception as e:
                    results['platform_results'][platform_id] = {
                        'success': False,
                        'error': str(e)
                    }
        
        return results
    
    def get_platform_analytics(self, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Get cross-platform analytics"""
        analytics = {
            'period': f"{start_date.date()} to {end_date.date()}",
            'platforms': {},
            'total_actions': 0,
            'action_breakdown': {},
            'success_rate': 0,
            'response_times': {}
        }
        
        total_actions = 0
        successful_actions = 0
        
        for platform_id, adapter in self.adapters.items():
            try:
                # Mock platform analytics
                platform_analytics = {
                    'platform_id': platform_id,
                    'platform_type': self.platforms[platform_id].platform_type.value,
                    'total_actions': 100,
                    'successful_actions': 95,
                    'avg_response_time': 2.5,
                    'action_breakdown': {
                        'hide_content': 40,
                        'remove_content': 30,
                        'warn_user': 20,
                        'suspend_user': 10
                    }
                }
                
                analytics['platforms'][platform_id] = platform_analytics
                total_actions += platform_analytics['total_actions']
                successful_actions += platform_analytics['successful_actions']
                
            except Exception as e:
                analytics['platforms'][platform_id] = {'error': str(e)}
        
        analytics['total_actions'] = total_actions
        analytics['success_rate'] = (successful_actions / total_actions * 100) if total_actions > 0 else 0
        
        return analytics


class PlatformSyncManager:
    """Manager for synchronizing actions across platforms"""
    
    def __init__(self):
        self.sync_rules = self._initialize_sync_rules()
        
    def _initialize_sync_rules(self) -> Dict[str, Dict]:
        """Initialize synchronization rules"""
        return {
            'user_suspension': {
                'trigger_actions': ['suspend_user'],
                'sync_actions': {
                    'mobile_ios': 'suspend_user',
                    'mobile_android': 'suspend_user',
                    'web_main': 'suspend_user'
                },
                'delay_seconds': 0
            },
            'content_removal': {
                'trigger_actions': ['remove_content'],
                'sync_actions': {
                    'mobile_ios': 'remove_content',
                    'mobile_android': 'remove_content',
                    'web_main': 'remove_content'
                },
                'delay_seconds': 5
            },
            'user_warning': {
                'trigger_actions': ['warn_user'],
                'sync_actions': {
                    'mobile_ios': 'warn_user',
                    'mobile_android': 'warn_user',
                    'web_main': 'warn_user'
                },
                'delay_seconds': 0
            }
        }
    
    def sync_action(self, content_id: str, source_platform: str, 
                   action: ModerationAction, reason: str, 
                   moderator_id: str) -> List[Dict[str, Any]]:
        """Synchronize action across platforms"""
        sync_results = []
        
        # Find applicable sync rule
        sync_rule = None
        for rule_name, rule in self.sync_rules.items():
            if action.value in rule['trigger_actions']:
                sync_rule = rule
                break
        
        if not sync_rule:
            return sync_results
        
        # Apply sync to target platforms
        for target_platform, target_action in sync_rule['sync_actions'].items():
            if target_platform == source_platform:
                continue  # Skip source platform
            
            try:
                # Mock sync implementation
                sync_result = {
                    'target_platform': target_platform,
                    'target_action': target_action,
                    'success': True,
                    'synced_at': datetime.now(timezone.utc).isoformat()
                }
                sync_results.append(sync_result)
                
            except Exception as e:
                sync_results.append({
                    'target_platform': target_platform,
                    'target_action': target_action,
                    'success': False,
                    'error': str(e)
                })
        
        return sync_results


# Global cross-platform moderation instance
cross_platform_moderation = CrossPlatformModeration()
