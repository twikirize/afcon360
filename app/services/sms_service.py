"""
SMS Service for sending OTP and verification codes.
Supports multiple providers (Twilio, Africa's Talking, console logging for development).
"""
import logging
import time
from typing import Optional, Dict, Any
from flask import current_app
import secrets

logger = logging.getLogger(__name__)

# In-memory storage for OTPs (for development)
# In production, use a database or Redis
_otp_storage = {}

class SMSService:
    """Service for sending SMS messages with pluggable providers."""

    def __init__(self, provider: Optional[str] = None):
        """
        Initialize SMS service with a specific provider.

        Args:
            provider: Provider name (twilio, africas_talking, console).
                      If None, uses SMS_PROVIDER from config.
        """
        self.provider = provider or current_app.config.get('SMS_PROVIDER', 'console')
        self._provider_instance = self._get_provider()

    def _get_provider(self):
        """Get the appropriate provider instance based on configuration."""
        if self.provider == 'twilio':
            return TwilioProvider()
        elif self.provider == 'africas_talking':
            return AfricaTalkingProvider()
        else:
            # Default to console provider for development
            return ConsoleProvider()

    def send_otp(self, phone_number: str, otp: Optional[str] = None) -> Dict[str, Any]:
        """
        Send OTP code to the given phone number.

        Args:
            phone_number: Recipient's phone number in E.164 format
            otp: The OTP code to send. If None, generate a random 6-digit code.

        Returns:
            Dictionary with provider response details
        """
        if otp is None:
            otp = self._generate_otp()

        # Store OTP with expiration (5 minutes)
        _otp_storage[phone_number] = {
            'otp': otp,
            'expires_at': time.time() + 300,  # 5 minutes
            'attempts': 0
        }

        logger.info(f"Sending OTP {otp} to {phone_number} via {self.provider}")
        return self._provider_instance.send_sms(
            phone_number=phone_number,
            message=f"Your verification code is: {otp}"
        )

    def verify_otp(self, phone_number: str, code: str) -> bool:
        """
        Verify an OTP code for a phone number.

        Args:
            phone_number: Phone number to verify
            code: OTP code entered by user

        Returns:
            True if verification succeeds, False otherwise
        """
        logger.info(f"Verifying OTP {code} for {phone_number}")

        # Check if OTP exists for this phone number
        if phone_number not in _otp_storage:
            logger.warning(f"No OTP found for phone number: {phone_number}")
            return False

        otp_data = _otp_storage[phone_number]

        # Check if OTP has expired
        if time.time() > otp_data['expires_at']:
            logger.warning(f"OTP expired for phone number: {phone_number}")
            del _otp_storage[phone_number]
            return False

        # Increment attempts
        otp_data['attempts'] += 1

        # Check if too many attempts
        if otp_data['attempts'] > 5:
            logger.warning(f"Too many OTP attempts for phone number: {phone_number}")
            del _otp_storage[phone_number]
            return False

        # Verify the code
        if otp_data['otp'] == code:
            # OTP is valid, remove it from storage
            del _otp_storage[phone_number]
            logger.info(f"OTP verified successfully for phone number: {phone_number}")
            return True
        else:
            logger.warning(f"Invalid OTP for phone number: {phone_number}")
            return False

    def _generate_otp(self, length: int = 6) -> str:
        """Generate a random numeric OTP."""
        return ''.join(secrets.choice('0123456789') for _ in range(length))


class BaseSMSProvider:
    """Base class for SMS providers."""

    def send_sms(self, phone_number: str, message: str) -> Dict[str, Any]:
        """
        Send an SMS message.

        Args:
            phone_number: Recipient's phone number
            message: Text message to send

        Returns:
            Dictionary with provider response details
        """
        raise NotImplementedError("Subclasses must implement send_sms method")


class ConsoleProvider(BaseSMSProvider):
    """Development provider that logs SMS to console."""

    def send_sms(self, phone_number: str, message: str) -> Dict[str, Any]:
        """Log SMS to console instead of actually sending."""
        print(f"[SMS to {phone_number}]: {message}")
        return {
            'success': True,
            'provider': 'console',
            'message': 'SMS logged to console (development mode)',
            'phone_number': phone_number
        }


class TwilioProvider(BaseSMSProvider):
    """Twilio SMS provider implementation."""

    def __init__(self):
        from flask import current_app
        self.account_sid = current_app.config.get('TWILIO_ACCOUNT_SID')
        self.auth_token = current_app.config.get('TWILIO_AUTH_TOKEN')
        self.phone_number = current_app.config.get('TWILIO_PHONE_NUMBER')

        if not all([self.account_sid, self.auth_token, self.phone_number]):
            logger.warning(
                "Twilio credentials not fully configured. "
                "Falling back to console provider."
            )
            raise ValueError("Twilio credentials not configured")

    def send_sms(self, phone_number: str, message: str) -> Dict[str, Any]:
        """Send SMS using Twilio API."""
        try:
            from twilio.rest import Client

            client = Client(self.account_sid, self.auth_token)
            response = client.messages.create(
                body=message,
                from_=self.phone_number,
                to=phone_number
            )

            return {
                'success': True,
                'provider': 'twilio',
                'message_sid': response.sid,
                'status': response.status,
                'phone_number': phone_number
            }
        except ImportError:
            logger.error("Twilio library not installed. Install with: pip install twilio")
            raise
        except Exception as e:
            logger.error(f"Twilio SMS sending failed: {e}")
            return {
                'success': False,
                'provider': 'twilio',
                'error': str(e),
                'phone_number': phone_number
            }


class AfricaTalkingProvider(BaseSMSProvider):
    """Africa's Talking SMS provider implementation."""

    def __init__(self):
        from flask import current_app
        self.username = current_app.config.get('AFRICAS_TALKING_USERNAME')
        self.api_key = current_app.config.get('AFRICAS_TALKING_API_KEY')
        self.sender_id = current_app.config.get('AFRICAS_TALKING_SENDER_ID')

        if not all([self.username, self.api_key]):
            logger.warning(
                "Africa's Talking credentials not fully configured. "
                "Falling back to console provider."
            )
            raise ValueError("Africa's Talking credentials not configured")

    def send_sms(self, phone_number: str, message: str) -> Dict[str, Any]:
        """Send SMS using Africa's Talking API."""
        try:
            import africastalking

            # Initialize SDK
            africastalking.initialize(self.username, self.api_key)
            sms = africastalking.SMS

            # Prepare options
            options = {
                'to': [phone_number],
                'message': message,
            }
            if self.sender_id:
                options['from'] = self.sender_id

            # Send message
            response = sms.send(**options)

            return {
                'success': True,
                'provider': 'africas_talking',
                'response': response,
                'phone_number': phone_number
            }
        except ImportError:
            logger.error(
                "Africa's Talking library not installed. "
                "Install with: pip install africastalking"
            )
            raise
        except Exception as e:
            logger.error(f"Africa's Talking SMS sending failed: {e}")
            return {
                'success': False,
                'provider': 'africas_talking',
                'error': str(e),
                'phone_number': phone_number
            }
