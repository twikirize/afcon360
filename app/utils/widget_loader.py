"""Module-aware widget loader - prevents dashboard crashes"""
from app.utils.module_guard import module_enabled, safe_import
import logging

logger = logging.getLogger(__name__)

class ModuleWidgetLoader:
    """Load widget data safely - returns empty dicts for disabled modules"""
    
    @staticmethod
    def get_wallet_data(user_id: int) -> dict:
        """Safe wallet widget data"""
        if not module_enabled('wallet') or not user_id:
            return {'enabled': False, 'balance': 0, 'currency': 'USD'}
        
        try:
            # Try different possible service locations
            WalletService = safe_import('app.wallet.services.wallet_service')
            if WalletService and hasattr(WalletService, 'WalletService'):
                service = WalletService.WalletService()
                balance = service.get_balance(user_id)
                return {'enabled': True, 'balance': balance or 0, 'currency': 'USD'}
        except Exception as e:
            logger.warning(f"Wallet widget failed for user {user_id}: {e}")
        
        return {'enabled': False, 'balance': 0, 'currency': 'USD', 'error': True}
    
    @staticmethod
    def get_events_data(limit: int = 5, user_id: int = None) -> dict:
        """Safe events widget data"""
        if not module_enabled('events'):
            return {'enabled': False, 'events': []}
        
        try:
            EventService = safe_import('app.events.services')
            if EventService and hasattr(EventService, 'get_upcoming_events'):
                events = EventService.get_upcoming_events(limit=limit)
                return {'enabled': True, 'events': events or []}
        except Exception as e:
            logger.warning(f"Events widget failed: {e}")
        
        return {'enabled': False, 'events': [], 'error': True}
    
    @staticmethod
    def get_transport_data(user_id: int) -> dict:
        """Safe transport widget data"""
        if not module_enabled('transport') or not user_id:
            return {'enabled': False, 'bookings': [], 'trips': 0}
        
        try:
            # Try to get transport data
            return {'enabled': True, 'bookings': [], 'trips': 0}
        except Exception as e:
            logger.warning(f"Transport widget failed: {e}")
            return {'enabled': False, 'bookings': [], 'error': True}
    
    @staticmethod
    def get_accommodation_data(user_id: int) -> dict:
        """Safe accommodation widget data"""
        if not module_enabled('accommodation') or not user_id:
            return {'enabled': False, 'bookings': [], 'stays': 0}
        
        try:
            return {'enabled': True, 'bookings': [], 'stays': 0}
        except Exception as e:
            logger.warning(f"Accommodation widget failed: {e}")
            return {'enabled': False, 'bookings': [], 'error': True}
    
    @staticmethod
    def get_tourism_data(user_id: int) -> dict:
        """Safe tourism widget data"""
        if not module_enabled('tourism') or not user_id:
            return {'enabled': False, 'destinations': [], 'bookings': 0}
        
        try:
            return {'enabled': True, 'destinations': [], 'bookings': 0}
        except Exception as e:
            logger.warning(f"Tourism widget failed: {e}")
            return {'enabled': False, 'destinations': [], 'error': True}

# Convenience functions
get_wallet_widget_data = ModuleWidgetLoader.get_wallet_data
get_events_widget_data = ModuleWidgetLoader.get_events_data
get_transport_widget_data = ModuleWidgetLoader.get_transport_data
get_accommodation_widget_data = ModuleWidgetLoader.get_accommodation_data
get_tourism_widget_data = ModuleWidgetLoader.get_tourism_data
